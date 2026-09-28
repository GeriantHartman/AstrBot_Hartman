"""HTTP client for a running AstrBot: Open API chat (API key) + dashboard (JWT)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import httpx

from .. import LIVE_DATA_DIR
from ..sse import ChatReply, SSEParser


class OpenApiError(RuntimeError):
    pass


class OpenApiClient:
    def __init__(self, base_url: str, api_key: str, *, timeout_s: float = 900.0):
        if not api_key:
            raise OpenApiError(
                "No AstrBot API key. Create one in WebUI (scope: chat) and put it in "
                "env RPBENCH_ASTRBOT_API_KEY or data/rp_bench/secrets.yaml as astrbot_api_key."
            )
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-API-Key": api_key}
        self.timeout = httpx.Timeout(timeout_s, connect=15.0)

    async def chat(
        self,
        *,
        username: str,
        session_id: str,
        message: str,
        config_id: str = "",
        selected_provider: str = "",
    ) -> ChatReply:
        body: dict[str, Any] = {
            "username": username,
            "session_id": session_id,
            "message": message,
            "enable_streaming": False,
        }
        if config_id:
            body["config_id"] = config_id
        if selected_provider:
            body["selected_provider"] = selected_provider
        parser = SSEParser()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/v1/chat", json=body, headers=self.headers
            ) as resp:
                ctype = resp.headers.get("content-type", "")
                if resp.status_code != 200 or "event-stream" not in ctype:
                    raw = (await resp.aread()).decode("utf-8", "replace")
                    raise OpenApiError(
                        f"/api/v1/chat HTTP {resp.status_code}: {raw[:500]}"
                    )
                async for chunk in resp.aiter_text():
                    parser.feed(chunk)
                    if parser.reply.ended:
                        break
        return parser.close()

    async def list_configs(self) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(
                f"{self.base_url}/api/v1/configs", headers=self.headers
            )
            r.raise_for_status()
            return r.json()


class DashboardClient:
    """Optional: pins the per-session default provider via session rules."""

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._token = ""

    @staticmethod
    def _wire_password(password: str) -> str:
        # The WebUI sends md5(password); the stored config value is that hash.
        if re.fullmatch(r"[0-9a-f]{32}", password or ""):
            return password
        return hashlib.md5((password or "").encode("utf-8")).hexdigest()

    async def _login(self, client: httpx.AsyncClient) -> None:
        r = await client.post(
            f"{self.base_url}/api/auth/login",
            json={
                "username": self.username,
                "password": self._wire_password(self.password),
            },
        )
        r.raise_for_status()
        data = r.json()
        token = ((data or {}).get("data") or {}).get("token", "")
        if not token:
            raise OpenApiError(
                f"dashboard login failed: {json.dumps(data, ensure_ascii=False)[:300]}"
            )
        self._token = token

    async def update_session_rule(
        self, umo: str, rule_key: str, rule_value: Any
    ) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if not self._token:
                await self._login(client)
            r = await client.post(
                f"{self.base_url}/api/session/update-rule",
                json={"umo": umo, "rule_key": rule_key, "rule_value": rule_value},
                headers={"Authorization": f"Bearer {self._token}"},
            )
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and data.get("status") == "error":
                raise OpenApiError(f"update-rule failed: {data.get('message')}")


def config_plugin_set(config_id: str, data_dir: Path = LIVE_DATA_DIR) -> list[str]:
    """plugin_set of the AstrBot config a session will be routed to."""
    path = data_dir / "cmd_config.json"
    if config_id and config_id != "default":
        path = data_dir / "config" / f"{config_id}.json"
    if not path.exists():
        raise OpenApiError(f"AstrBot config not found: {path}")
    with path.open("r", encoding="utf-8-sig") as fp:
        cfg = json.load(fp)
    return [str(p) for p in cfg.get("plugin_set", ["*"])]


def plugin_enabled(plugin_set: list[str], plugin_name: str) -> bool:
    return plugin_set == ["*"] or plugin_name in plugin_set

"""In-process AstrBot providers for the chat arms and the judge.

Configs are read from the *live* ``data/cmd_config.json`` with plain json and
merged exactly like ``ProviderManager.get_merged_provider_config``
(astrbot/core/provider/manager.py:489). The provider classes themselves come
from AstrBot, so every provider type (openai / googlegenai / anthropic / …)
shapes requests the same way it does in production. Requires the sandbox to
be active before the first astrbot import.
"""

from __future__ import annotations

import copy
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from . import LIVE_DATA_DIR

LIVE_CMD_CONFIG = LIVE_DATA_DIR / "cmd_config.json"


class ProviderConfigError(ValueError):
    pass


@dataclass
class ChatResult:
    text: str = ""
    reasoning: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    latency_s: float = 0.0
    error: str = ""
    model: str = ""


def load_cmd_config(path: Path = LIVE_CMD_CONFIG) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8-sig") as fp:
        return json.load(fp)


def merge_provider_config(
    provider_config: dict[str, Any], sources: list[dict[str, Any]]
) -> dict[str, Any]:
    """Parity copy of ProviderManager.get_merged_provider_config."""
    pc = copy.deepcopy(provider_config)
    source_id = pc.get("provider_source_id", "")
    if source_id:
        for ps in sources:
            if ps.get("id") == source_id:
                merged = {**ps, **pc}
                merged["id"] = pc["id"]
                return merged
    return pc


def _resolve_env_keys(cfg: dict[str, Any]) -> dict[str, Any]:
    keys = cfg.get("key", [])
    if not isinstance(keys, list):
        return cfg
    resolved = []
    for key in keys:
        if isinstance(key, str) and key.startswith("$"):
            name = key[1:].strip("{}")
            resolved.append(os.environ.get(name, ""))
        else:
            resolved.append(key)
    cfg["key"] = resolved
    return cfg


def resolve_provider_config(
    provider_id: str,
    cmd_config: dict[str, Any],
    *,
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    providers = cmd_config.get("provider") or []
    sources = cmd_config.get("provider_sources") or []
    for pc in providers:
        if pc.get("id") == provider_id:
            cfg = _resolve_env_keys(merge_provider_config(pc, sources))
            if cfg.get("provider_type", "chat_completion") != "chat_completion":
                raise ProviderConfigError(
                    f"{provider_id} is not a chat_completion provider"
                )
            if not cfg.get("enable", True):
                raise ProviderConfigError(
                    f"{provider_id} is disabled in cmd_config.json"
                )
            if extra_body:
                body = cfg.get("custom_extra_body") or {}
                if isinstance(body, str):
                    try:
                        body = json.loads(body)
                    except json.JSONDecodeError:
                        body = {}
                cfg["custom_extra_body"] = {**body, **extra_body}
            return cfg
    known = [
        p.get("id")
        for p in providers
        if p.get("provider_type", "chat_completion") == "chat_completion"
    ]
    raise ProviderConfigError(
        f"provider id {provider_id!r} not found; chat providers: {known}"
    )


def model_family(provider_id: str, cfg: dict[str, Any] | None = None) -> str:
    """Coarse family tag used for the judge self-preference warning."""
    text = f"{provider_id} {(cfg or {}).get('model', '')}".lower()
    for family in (
        "gemini",
        "claude",
        "gpt",
        "deepseek",
        "qwen",
        "glm",
        "grok",
        "gemma",
        "llama",
        "kimi",
    ):
        if family in text:
            return family
    return text.split("/")[-1] or "unknown"


class ProviderPool:
    """Caches one provider instance per (provider_id, overrides)."""

    def __init__(self, cmd_config: dict[str, Any] | None = None):
        self.cmd_config = cmd_config if cmd_config is not None else load_cmd_config()
        self._insts: dict[str, Any] = {}

    def settings(self) -> dict[str, Any]:
        return dict(self.cmd_config.get("provider_settings") or {})

    async def get(
        self, provider_id: str, *, extra_body: dict[str, Any] | None = None
    ) -> Any:
        cache_key = provider_id + json.dumps(extra_body or {}, sort_keys=True)
        if cache_key in self._insts:
            return self._insts[cache_key]
        cfg = resolve_provider_config(
            provider_id, self.cmd_config, extra_body=extra_body
        )

        # astrbot.api first: importing provider.manager cold hits a circular import
        import astrbot.api  # noqa: F401
        from astrbot.core.provider.manager import ProviderManager
        from astrbot.core.provider.register import provider_cls_map

        ProviderManager.dynamic_import_provider(None, cfg["type"])  # self is unused
        meta = provider_cls_map.get(cfg["type"])
        if meta is None or meta.cls_type is None:
            raise ProviderConfigError(
                f"no AstrBot adapter registered for type {cfg['type']!r}"
            )
        inst = meta.cls_type(cfg, self.settings())
        init = getattr(inst, "initialize", None)
        if callable(init):
            await init()
        self._insts[cache_key] = inst
        return inst

    async def close(self) -> None:
        for inst in self._insts.values():
            for name in ("terminate", "close"):
                fn = getattr(inst, name, None)
                if callable(fn):
                    try:
                        result = fn()
                        if hasattr(result, "__await__"):
                            await result
                    except Exception:
                        pass
                    break
        self._insts.clear()


def _usage_dict(usage: Any) -> dict[str, int]:
    if usage is None:
        return {}
    return {
        "input": int(getattr(usage, "input_other", 0) or 0)
        + int(getattr(usage, "input_cached", 0) or 0),
        "input_cached": int(getattr(usage, "input_cached", 0) or 0),
        "output": int(getattr(usage, "output", 0) or 0),
    }


async def provider_chat(
    provider: Any,
    *,
    prompt: str,
    system_prompt: str = "",
    contexts: list[dict[str, Any]] | None = None,
    session_id: str | None = None,
) -> ChatResult:
    started = time.perf_counter()
    try:
        resp = await provider.text_chat(
            prompt=prompt,
            system_prompt=system_prompt or None,
            contexts=contexts or [],
            session_id=session_id,
        )
    except Exception as exc:
        return ChatResult(
            error=f"{type(exc).__name__}: {exc}",
            latency_s=time.perf_counter() - started,
        )
    text = str(getattr(resp, "completion_text", "") or "")
    return ChatResult(
        text=text,
        reasoning=str(getattr(resp, "reasoning_content", "") or ""),
        usage=_usage_dict(getattr(resp, "usage", None)),
        latency_s=time.perf_counter() - started,
        model=str(getattr(provider, "get_model", lambda: "")() or ""),
        error="" if text.strip() else "empty completion",
    )


class EndpointChat:
    """Plain OpenAI-compatible fallback (for local servers not in cmd_config)."""

    def __init__(
        self,
        url: str,
        model: str,
        api_key: str = "",
        *,
        temperature: float = 0.0,
        timeout: float = 600.0,
    ):
        self.url = url
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.timeout = timeout

    async def chat(
        self,
        *,
        prompt: str,
        system_prompt: str = "",
        contexts: list[dict[str, Any]] | None = None,
    ) -> ChatResult:
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages += list(contexts or [])
        messages.append({"role": "user", "content": prompt})
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": False,
        }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(self.url, json=payload, headers=headers)
                r.raise_for_status()
                body = r.json()
        except Exception as exc:
            return ChatResult(
                error=f"{type(exc).__name__}: {exc}",
                latency_s=time.perf_counter() - started,
            )
        choice = (body.get("choices") or [{}])[0].get("message") or {}
        usage = body.get("usage") or {}
        text = str(choice.get("content") or "")
        return ChatResult(
            text=text,
            reasoning=str(choice.get("reasoning_content") or ""),
            usage={
                "input": int(usage.get("prompt_tokens", 0) or 0),
                "output": int(usage.get("completion_tokens", 0) or 0),
            },
            latency_s=time.perf_counter() - started,
            model=self.model,
            error="" if text.strip() else "empty completion",
        )

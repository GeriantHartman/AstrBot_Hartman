"""Probe every Gemini API key in the live cmd_config.json, one by one.

Finds keys that fail with 403 PERMISSION_DENIED ("project has been denied
access") so they can be removed from the config. Keys are printed masked
(first 12 chars, same as AstrBot's own log line); full keys never leave
this process. Read-only: the config file is not modified.

    uv run python scripts/research/gemini_key_check.py              # test every key
    uv run python scripts/research/gemini_key_check.py --list-only  # just list masked keys
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from google import genai  # noqa: E402
from google.genai import errors, types  # noqa: E402

from scripts.rp_bench.providers import (  # noqa: E402
    _resolve_env_keys,
    load_cmd_config,
    merge_provider_config,
)

MODELS = ("gemini-3.8-flash", "gemini-3.7-flash")
RETRIES_ON_503 = 2


def mask(key: str) -> str:
    return f"{key[:12]}..." if key else "(empty)"


def gemini_providers(cfg: dict) -> list[dict]:
    sources = cfg.get("provider_sources") or []
    out = []
    for pc in cfg.get("provider") or []:
        merged = _resolve_env_keys(merge_provider_config(pc, sources))
        if merged.get("type") == "googlegenai_chat_completion":
            merged["_inline_key"] = "key" in pc
            out.append(merged)
    return out


def probe(key: str, model: str, api_base: str | None, proxy: str) -> str:
    opts = types.HttpOptions(base_url=api_base or None, timeout=60_000)
    if proxy:
        opts.client_args = {"proxy": proxy}
    client = genai.Client(api_key=key, http_options=opts)
    for attempt in range(RETRIES_ON_503 + 1):
        try:
            resp = client.models.generate_content(
                model=model, contents="回复两个字：收到"
            )
            return f"OK {(resp.text or '').strip()[:10]!r}"
        except errors.APIError as e:
            msg = (e.message or "").splitlines()[0][:90]
            if e.code == 503 and attempt < RETRIES_ON_503:
                time.sleep(3)
                continue
            return f"{e.code} {e.status}: {msg}"
        except Exception as e:  # network etc.
            return f"ERR {type(e).__name__}: {str(e)[:90]}"
    return "unreachable"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = load_cmd_config()
    providers = gemini_providers(cfg)
    print("Gemini providers and where their keys come from:")
    seen: dict[str, dict] = {}
    for p in providers:
        keys = [k for k in p.get("key") or [] if k]
        where = (
            "inline" if p["_inline_key"] else f"source {p.get('provider_source_id')!r}"
        )
        state = "enabled" if p.get("enable", True) else "disabled"
        print(f"  {p['id']:<42} {state:<8} keys={len(keys)} from {where}")
        for k in keys:
            entry = seen.setdefault(
                k,
                {
                    "providers": [],
                    "base": p.get("api_base"),
                    "proxy": p.get("proxy", ""),
                },
            )
            entry["providers"].append(p["id"])

    if "--list-only" in sys.argv:
        for idx, key in enumerate(seen):
            print(f"  key #{idx} {mask(key)}")
        return

    print(f"\n{len(seen)} distinct key(s). Testing each against {', '.join(MODELS)}:")
    for idx, (key, info) in enumerate(seen.items()):
        print(f"\n  key #{idx} {mask(key)}  used by: {', '.join(info['providers'])}")
        for model in MODELS:
            print(f"    {model:<18} {probe(key, model, info['base'], info['proxy'])}")
            time.sleep(1)


if __name__ == "__main__":
    main()

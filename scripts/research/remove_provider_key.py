"""Remove one API key from an AstrBot provider source via the dashboard API.

Goes through POST /api/config/provider_sources/update so the running AstrBot
updates its in-memory config, writes cmd_config.json, and reloads the
providers that use the source (editing the file directly would be overwritten
by the next save from the running process).

The key is selected by prefix and must match exactly one entry. Keys are only
ever printed masked. A byte copy of cmd_config.json is saved first.

    uv run python scripts/research/remove_provider_key.py --source google_gemini --prefix AIzaSyDFt9pw
    uv run python scripts/research/remove_provider_key.py --source google_gemini --prefix AIzaSyDFt9pw --apply

Dashboard credentials: env RPBENCH_DASH_USER / RPBENCH_DASH_PASSWORD or
data/rp_bench/secrets.yaml (dashboard_user / dashboard_password), else the
AstrBot defaults astrbot / astrbot.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.rp_bench.config import secret  # noqa: E402
from scripts.rp_bench.drivers.openapi import DashboardClient  # noqa: E402
from scripts.rp_bench.providers import LIVE_CMD_CONFIG  # noqa: E402
from scripts.rp_bench.store import UTC8  # noqa: E402

BASE_URL = "http://127.0.0.1:6185"


def mask(key: str) -> str:
    return f"{key[:12]}..."


def login(client: httpx.Client) -> str:
    user = secret("RPBENCH_DASH_USER", "dashboard_user") or "astrbot"
    pwd = secret("RPBENCH_DASH_PASSWORD", "dashboard_password") or "astrbot"
    r = client.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": user, "password": DashboardClient._wire_password(pwd)},
    )
    r.raise_for_status()
    token = ((r.json() or {}).get("data") or {}).get("token", "")
    if not token:
        raise SystemExit(f"dashboard login failed: {r.json().get('message')}")
    return token


def get_source(client: httpx.Client, headers: dict, source_id: str) -> dict:
    r = client.get(f"{BASE_URL}/api/config/provider/template", headers=headers)
    r.raise_for_status()
    sources = (r.json().get("data") or {}).get("provider_sources") or []
    for ps in sources:
        if ps.get("id") == source_id:
            return ps
    raise SystemExit(f"provider source {source_id!r} not found")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="provider source id")
    ap.add_argument("--prefix", required=True, help="leading chars of the key to drop")
    ap.add_argument(
        "--apply", action="store_true", help="actually update (default: dry run)"
    )
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    with httpx.Client(timeout=60.0) as client:
        headers = {"Authorization": f"Bearer {login(client)}"}
        source = get_source(client, headers, args.source)
        keys = list(source.get("key") or [])
        hits = [k for k in keys if k.startswith(args.prefix)]
        print(
            f"source {args.source!r}: {len(keys)} key(s): {', '.join(mask(k) for k in keys)}"
        )
        if len(hits) != 1:
            raise SystemExit(
                f"prefix {args.prefix!r} matched {len(hits)} keys; need exactly 1"
            )
        kept = [k for k in keys if k != hits[0]]
        print(f"remove {mask(hits[0])} -> {len(kept)} key(s) left")
        if not kept:
            raise SystemExit("refusing to leave the source with no keys")
        if not args.apply:
            print("dry run; pass --apply to update")
            return

        stamp = datetime.now(UTC8).strftime("%Y%m%d-%H%M%S")
        backup = LIVE_CMD_CONFIG.with_name(f"cmd_config.json.bak-{stamp}")
        shutil.copy2(LIVE_CMD_CONFIG, backup)
        print(f"backup: {backup}")

        new_source = {**source, "key": kept}
        r = client.post(
            f"{BASE_URL}/api/config/provider_sources/update",
            json={"original_id": args.source, "config": new_source},
            headers=headers,
        )
        r.raise_for_status()
        body = r.json()
        print(f"update: {body.get('status')} {body.get('message')}")

        after = list(get_source(client, headers, args.source).get("key") or [])
        gone = not any(k.startswith(args.prefix) for k in after)
        print(f"verify: {len(after)} key(s) now, target removed = {gone}")


if __name__ == "__main__":
    main()

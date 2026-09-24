"""Live check of the RPG plugin's web routes against a running AstrBot.

Verifies three things on the FastAPI dashboard:

1. the read-only editor page opens without a dashboard JWT (fix #10);
2. the data route still refuses anonymous access;
3. the data route answers with JSON once a JWT is supplied, which exercises the
   Quart compatibility layer the plugin's handlers still rely on.

Start AstrBot first, then run from the repo root:
    uv run python scripts/research/check_plugin_web_routes.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRATCH_CONFIG = REPO_ROOT / "data" / "cmd_config.json"

BASE = "http://127.0.0.1:6185"
EDITOR_PATH = "/api/plug/rpg-chat-template-editor"
DATA_PATH = "/api/plug/rpg-chat-template"


def call(
    path: str,
    *,
    method: str = "GET",
    token: str | None = None,
    payload: dict | None = None,
) -> tuple[int, str, str]:
    url = f"{BASE}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", "replace")
            return response.status, response.headers.get("Content-Type", ""), body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return exc.code, exc.headers.get("Content-Type", ""), body


def mint_token() -> str | None:
    """Sign a dashboard JWT with the scratch instance's own secret.

    The running server here is the throwaway instance this worktree created
    during the smoke test, and its password is randomly generated, so signing a
    token directly is simpler than driving the login form.
    """
    if not SCRATCH_CONFIG.exists():
        print(f"  no scratch config at {SCRATCH_CONFIG}")
        return None
    try:
        import jwt
    except ImportError:
        print("  PyJWT is not importable")
        return None

    config = json.loads(SCRATCH_CONFIG.read_text(encoding="utf-8-sig"))
    dashboard = config.get("dashboard", {})
    secret = dashboard.get("jwt_secret")
    username = dashboard.get("username", "astrbot")
    if not secret:
        print("  scratch config has no jwt_secret")
        return None
    return jwt.encode({"username": username}, secret, algorithm="HS256")


def main() -> int:
    failures = 0

    print("1. editor page without JWT (expect 200 text/html)")
    status, ctype, body = call(EDITOR_PATH)
    print(f"   status={status} type={ctype} bytes={len(body)}")
    if status != 200 or "html" not in ctype:
        print("   FAIL: the read-only editor page is not publicly reachable")
        failures += 1

    print("2. data route without JWT (expect 401)")
    status, _, body = call(DATA_PATH)
    print(f"   status={status} body={body[:120]}")
    if status != 401:
        print("   FAIL: the data route should stay behind dashboard auth")
        failures += 1

    print("3. data route with JWT (expect 200 JSON)")
    token = mint_token()
    if not token:
        print("   SKIP: could not obtain a dashboard token")
        failures += 1
    else:
        status, ctype, body = call(DATA_PATH, token=token)
        print(f"   status={status} type={ctype} bytes={len(body)}")
        if status != 200:
            print(f"   FAIL: {body[:300]}")
            failures += 1
        else:
            try:
                json.loads(body)
            except json.JSONDecodeError:
                print(f"   FAIL: response is not JSON: {body[:200]}")
                failures += 1

    print()
    if failures:
        print(f"{failures} check(s) failed")
        return 1
    print("all plugin web route checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

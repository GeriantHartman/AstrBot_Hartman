#!/usr/bin/env python3
"""Summarize recent turns of the art plugin's LLM audit index.

Reads ``<data_root>/llm_audit_index/<session_key>.jsonl`` — one row per turn,
written when the actor response lands. Use this FIRST: it is cheap, and it
tells you which turns are worth opening in full.

Stdlib only on purpose: an auditing agent must be able to run this without the
plugin being importable.

Usage:
    index_summary.py                       # newest session, 20 turns
    index_summary.py --session <id|key>     # specific session
    index_summary.py --limit 50 --json      # machine-readable
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import quote

SESSION_KEY_LIMIT = 120
DEFAULT_DATA_ROOT = "data/plugin_data/astrbot_plugin_art"


def session_key(session_id: str) -> str:
    """Mirror of LLMAuditLedger.session_key — keep the two in sync."""
    raw = str(session_id or "unknown-session")
    key = quote(raw, safe="-_.@=")
    if len(key) <= SESSION_KEY_LIMIT:
        return key
    suffix = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"{key[: SESSION_KEY_LIMIT - 10]}--{suffix}"


def resolve_index_path(data_root: Path, session: str | None) -> Path:
    index_dir = data_root / "llm_audit_index"
    if session:
        direct = index_dir / f"{session}.jsonl"
        if direct.exists():
            return direct
        return index_dir / f"{session_key(session)}.jsonl"
    candidates = sorted(
        index_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not candidates:
        sys.exit(f"no index files under {index_dir}")
    return candidates[0]


def load_rows(path: Path, limit: int) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        sys.exit(f"cannot read {path}: {exc}")
    rows: list[dict] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows[-limit:] if limit > 0 else rows


def flags(row: dict) -> str:
    """Compact health markers — the things worth noticing at a glance."""
    marks: list[str] = []
    if row.get("response_error"):
        marks.append("ERR")
    meta = row.get("response_meta")
    if isinstance(meta, dict):
        if meta.get("is_fallback"):
            marks.append(f"FALLBACK:{meta.get('fallback_reason', '?')}")
        if meta.get("cleaned"):
            marks.append(f"CLEANED:{meta.get('chars_stripped', '?')}")
        if meta.get("parsed_ok") is False:
            marks.append("PARSE_FAIL")
    return ",".join(marks)


def print_table(rows: list[dict]) -> None:
    print(
        f"{'turn_id':<24}{'preset':<10}{'model':<22}"
        f"{'user':<34}{'assistant':<34}flags"
    )
    print("-" * 130)
    for row in rows:
        user = " ".join(str(row.get("user_preview", "")).split())[:32]
        assistant = " ".join(str(row.get("assistant_preview", "")).split())[:32]
        model = str(row.get("model") or row.get("provider_id") or "-")
        print(
            f"{str(row.get('turn_id', '')):<24}"
            f"{str(row.get('preset_name', '') or '-')[:9]:<10}"
            f"{model[:21]:<22}"
            f"{user:<34}{assistant:<34}{flags(row)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", help="session_id or session_key")
    parser.add_argument("--limit", type=int, default=20, help="turns to show")
    parser.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    parser.add_argument("--json", action="store_true", help="emit raw JSON")
    args = parser.parse_args()

    path = resolve_index_path(Path(args.data_root), args.session)
    rows = load_rows(path, args.limit)

    if args.json:
        json.dump(rows, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return

    print(f"# {path}")
    print(f"# {len(rows)} turn(s)\n")
    print_table(rows)
    if rows:
        print(f"\nlatest turn_id: {rows[-1].get('turn_id', '')}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Summarize recent turns of the art plugin's LLM audit index.

Reads ``<data_root>/llm_audit_index/<session_key>.jsonl`` — one row per turn,
written when an agent, USER reviewer, or legacy actor response lands. The default
selects story turns; use --stage user_review for independent background maintenance.
Use this FIRST to find the turns worth opening in full.

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
STAGE_GROUPS = {
    "story": {"agent", "actor"},
    "agent": {"agent"},
    "user_review": {"user_review"},
    "legacy": {"actor"},
    "all": None,
}


def session_key(session_id: str) -> str:
    """Mirror of LLMAuditLedger.session_key — keep the two in sync."""
    raw = str(session_id or "unknown-session")
    key = quote(raw, safe="-_.@=")
    if len(key) <= SESSION_KEY_LIMIT:
        return key
    suffix = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"{key[: SESSION_KEY_LIMIT - 10]}--{suffix}"


def resolve_index_path(
    data_root: Path, session: str | None, stage: str = "story"
) -> Path:
    """Select an explicit index or the newest index containing the chosen stages.

    Args:
        data_root: Plugin data or isolated validation directory.
        session: Exact session identity or encoded key, if known.
        stage: Story, reviewer, or legacy audit selection.

    Returns:
        Path to an index containing the requested audit stage.
    """
    index_dir = data_root / "llm_audit_index"
    if session:
        direct = index_dir / f"{session}.jsonl"
        if direct.exists():
            return direct
        return index_dir / f"{session_key(session)}.jsonl"
    candidates = sorted(
        index_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    for path in candidates:
        if load_rows(path, 1, stage):
            return path
    sys.exit(f"no {stage} index rows under {index_dir}")


def load_rows(path: Path, limit: int, stage: str = "all") -> list[dict]:
    """Read valid rows, selecting stages before applying the result limit.

    Args:
        path: Index file.
        limit: Maximum selected rows; zero returns all matching rows.
        stage: Stage group to include.

    Returns:
        Matching index rows in append order.
    """
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
        if isinstance(item, dict) and (
            STAGE_GROUPS[stage] is None
            or item.get("stage", "actor") in STAGE_GROUPS[stage]
        ):
            rows.append(item)
    return rows[-limit:] if limit > 0 else rows


def flags(row: dict) -> str:
    """Compact health markers — the things worth noticing at a glance."""
    marks: list[str] = []
    if row.get("response_error"):
        marks.append("ERR")
    meta = row.get("response_meta")
    if isinstance(meta, dict):
        if meta.get("published") is False:
            marks.append("UNPUBLISHED")
        if meta.get("committed") is False:
            marks.append("UNCOMMITTED")
        if meta.get("replaces"):
            marks.append("REWIND")
        if meta.get("is_fallback"):
            marks.append(f"FALLBACK:{meta.get('fallback_reason', '?')}")
        if meta.get("cleaned"):
            marks.append(f"CLEANED:{meta.get('chars_stripped', '?')}")
        if meta.get("parsed_ok") is False:
            marks.append("PARSE_FAIL")
    return ",".join(marks)


def print_table(rows: list[dict]) -> None:
    print(
        f"{'turn_id':<24}{'stage':<13}{'provider':<27}{'model':<22}{'user':<30}{'response':<30}flags"
    )
    print("-" * 160)
    for row in rows:
        user = " ".join(str(row.get("user_preview", "")).split())[:32]
        assistant = " ".join(str(row.get("assistant_preview", "")).split())[:32]
        model = str(row.get("model") or row.get("provider_id") or "-")
        print(
            f"{str(row.get('turn_id', '')):<24}"
            f"{str(row.get('stage', 'actor'))[:12]:<13}"
            f"{str(row.get('provider_id') or '-')[:26]:<27}"
            f"{model[:21]:<22}"
            f"{user[:28]:<30}{assistant[:28]:<30}{flags(row)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", help="session_id or session_key")
    parser.add_argument("--limit", type=int, default=20, help="turns to show")
    parser.add_argument(
        "--stage", choices=STAGE_GROUPS, default="story", help="audit stage group"
    )
    parser.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    parser.add_argument("--json", action="store_true", help="emit raw JSON")
    args = parser.parse_args()

    path = resolve_index_path(Path(args.data_root), args.session, args.stage)
    rows = load_rows(path, args.limit, args.stage)

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

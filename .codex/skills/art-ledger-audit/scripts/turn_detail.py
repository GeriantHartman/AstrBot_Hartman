#!/usr/bin/env python3
"""Dump the three LLM calls of one art turn from the audit ledger.

A turn is three documents sharing a ``turn_id`` prefix:

    <data_root>/llm_audit/<session_key>/<turn_id>-playwright-<session_key>.json
    <data_root>/llm_audit/<session_key>/<turn_id>-actor-<session_key>.json
    <data_root>/llm_audit/<session_key>/<turn_id>-scribe-<session_key>.json

Use ``index_summary.py`` first to pick a turn, then this to read it. Full
prompts are large (the actor's system_prompt alone is ~8k chars); keep the
default truncation unless you have a specific reason to read a whole block.

Usage:
    turn_detail.py                                  # latest turn, newest session
    turn_detail.py --turn 20261001-120311-6bcc34
    turn_detail.py --session <id> --full            # no truncation
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
STAGES = ("playwright", "actor", "scribe")


def session_key(session_id: str) -> str:
    """Mirror of LLMAuditLedger.session_key — keep the two in sync."""
    raw = str(session_id or "unknown-session")
    key = quote(raw, safe="-_.@=")
    if len(key) <= SESSION_KEY_LIMIT:
        return key
    suffix = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"{key[: SESSION_KEY_LIMIT - 10]}--{suffix}"


def resolve_session_dir(data_root: Path, session: str | None) -> Path:
    audit_root = data_root / "llm_audit"
    if session:
        direct = audit_root / session
        if direct.is_dir():
            return direct
        return audit_root / session_key(session)
    dirs = sorted(
        (d for d in audit_root.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    if not dirs:
        sys.exit(f"no session directories under {audit_root}")
    return dirs[0]


def latest_turn_id(session_dir: Path) -> str:
    ids = sorted(
        {p.name.split("-actor-")[0] for p in session_dir.glob("*-actor-*.json")}
    )
    if not ids:
        sys.exit(f"no actor documents in {session_dir}")
    return ids[-1]


def load_turn(session_dir: Path, turn_id: str) -> dict[str, dict]:
    docs: dict[str, dict] = {}
    for path in session_dir.glob(f"{turn_id}-*.json"):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stage = doc.get("stage")
        if stage:
            docs[stage] = doc
    if not docs:
        sys.exit(f"no documents for turn {turn_id} in {session_dir}")
    return docs


def cut(text: str, limit: int | None) -> str:
    text = text or ""
    if limit is None or len(text) <= limit:
        return text
    return f"{text[:limit]}\n… [{len(text) - limit} more chars — rerun with --full]"


def show_header(stage: str, doc: dict) -> None:
    trace = doc.get("assembly_trace") or {}
    print(f"\n{'=' * 78}\n[{stage}]")
    print(
        f"  provider_id={doc.get('provider_id')!r}  model={doc.get('model')!r}"
        f"  source={trace.get('provider_source', '-')!r}"
    )


def show_playwright(doc: dict, limit: int | None) -> None:
    view = doc.get("audit_view") or {}
    meta = (doc.get("response") or {}).get("meta") or {}
    print(
        f"  is_fallback={meta.get('is_fallback')}"
        f"  reason={meta.get('fallback_reason', '')!r}"
        f"  tools_called={len(meta.get('tool_trace') or [])}"
    )
    for call in meta.get("tool_trace") or []:
        print(
            f"    tool {call.get('tool')} ok={call.get('ok')} args={call.get('args')}"
        )
    roll = view.get("action_roll") or {}
    print(
        f"  action_roll={roll.get('grade', '')!r} notes={view.get('daily_tone', '')!r}"
    )
    print("  --- director notes ---")
    print(cut((doc.get("response") or {}).get("text", ""), limit))


def show_actor(doc: dict, limit: int | None) -> None:
    view = doc.get("audit_view") or {}
    request = doc.get("request") or {}
    response = doc.get("response") or {}
    meta = response.get("meta") or {}
    print(f"  stripped_sections={view.get('stripped_sections')}")
    print(
        f"  has_dynamic_block={view.get('has_dynamic_block')}"
        f"  scene={view.get('scene_after')}"
        f"  present={view.get('present_characters')}"
    )
    print(
        f"  system_prompt={len(request.get('system_prompt', ''))} chars"
        f"  contexts={len(request.get('contexts') or [])}"
        f"  prompt={len(request.get('prompt', ''))} chars"
    )
    print(
        f"  cleaned={meta.get('cleaned')}  chars_stripped={meta.get('chars_stripped')}"
    )
    print("  --- director notes injected ---")
    print(cut(view.get("director_notes", ""), limit))
    print("  --- response (pre-clean) ---")
    print(cut(response.get("text", ""), limit))


def show_scribe(doc: dict, limit: int | None) -> None:
    meta = (doc.get("response") or {}).get("meta") or {}
    print(
        f"  parsed_ok={meta.get('parsed_ok')}  error={(doc.get('response') or {}).get('error')!r}"
    )
    if meta.get("parse_error"):
        print(f"  parse_error={meta['parse_error']!r}")
    print("  --- parsed ---")
    print(cut(json.dumps(meta.get("parsed"), ensure_ascii=False, indent=2), limit))
    print("  --- writes ---")
    for write in meta.get("writes") or []:
        print(
            f"    {str(write.get('category', '')):<20}"
            f"{str(write.get('key', ''))[:16]:<18}"
            f"{str(write.get('value_preview', ''))[:60]}"
        )


SHOWERS = {"playwright": show_playwright, "actor": show_actor, "scribe": show_scribe}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", help="session_id or session_key")
    parser.add_argument("--turn", default="latest", help="turn_id or 'latest'")
    parser.add_argument("--chars", type=int, default=400, help="truncate long text")
    parser.add_argument("--full", action="store_true", help="do not truncate")
    parser.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    parser.add_argument("--json", action="store_true", help="emit raw JSON")
    args = parser.parse_args()

    session_dir = resolve_session_dir(Path(args.data_root), args.session)
    turn_id = latest_turn_id(session_dir) if args.turn == "latest" else args.turn
    docs = load_turn(session_dir, turn_id)

    if args.json:
        json.dump(docs, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return

    limit = None if args.full else args.chars
    print(f"# {session_dir}\n# turn {turn_id}")
    for stage in STAGES:
        doc = docs.get(stage)
        if not doc:
            print(f"\n{'=' * 78}\n[{stage}] MISSING")
            continue
        show_header(stage, doc)
        SHOWERS[stage](doc, limit)


if __name__ == "__main__":
    main()

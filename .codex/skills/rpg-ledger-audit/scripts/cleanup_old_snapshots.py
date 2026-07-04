from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_index_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return rows
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict) and row.get("audit_id"):
            rows.append(row)
    return rows


def _latest_ids_from_index(index_path: Path, keep: int) -> set[str]:
    rows = _read_index_rows(index_path)
    rows.sort(key=lambda row: int(row.get("created_at", 0) or 0), reverse=True)
    return {str(row.get("audit_id")) for row in rows[:keep] if row.get("audit_id")}


def _latest_ids_from_files(session_dir: Path, keep: int) -> set[str]:
    files = sorted(
        session_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return {p.stem for p in files[:keep]}


def cleanup(root: Path, index_root: Path, keep: int, apply: bool) -> dict[str, Any]:
    deleted: list[str] = []
    kept: list[str] = []
    sessions = [p for p in root.iterdir() if p.is_dir()] if root.exists() else []
    for session_dir in sessions:
        index_path = index_root / f"{session_dir.name}.jsonl"
        keep_ids = _latest_ids_from_index(index_path, keep)
        if not keep_ids:
            keep_ids = _latest_ids_from_files(session_dir, keep)
        for ledger_path in sorted(session_dir.glob("*.json")):
            if ledger_path.stem in keep_ids:
                kept.append(str(ledger_path))
                continue
            deleted.append(str(ledger_path))
            if apply:
                ledger_path.unlink(missing_ok=True)
        if apply and index_path.exists() and keep_ids:
            rows = [
                row
                for row in _read_index_rows(index_path)
                if str(row.get("audit_id")) in keep_ids
            ]
            rows.sort(key=lambda row: int(row.get("created_at", 0) or 0))
            text = "".join(
                json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows
            )
            index_path.write_text(text, encoding="utf-8")
    return {
        "mode": "apply" if apply else "dry-run",
        "keep_per_session": keep,
        "kept_count": len(kept),
        "deleted_count": len(deleted),
        "kept": kept,
        "deleted": deleted,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", default="data/plugin_data/astrbot_plugin_agentic_rpg/llm_audit"
    )
    parser.add_argument(
        "--index-root",
        default="data/plugin_data/astrbot_plugin_agentic_rpg/llm_audit_index",
    )
    parser.add_argument(
        "--keep", type=int, default=1, help="每个 session 保留最新 N 份快照"
    )
    parser.add_argument(
        "--apply", action="store_true", help="实际删除旧快照；不传则只预览"
    )
    args = parser.parse_args()
    keep = max(1, int(args.keep))
    result = cleanup(Path(args.root), Path(args.index_root), keep, bool(args.apply))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

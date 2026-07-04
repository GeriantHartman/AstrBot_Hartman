from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote


def session_key(session_id: str) -> str:
    raw = str(session_id or "unknown-session")
    key = quote(raw, safe="-_.@=")
    if len(key) <= 120:
        return key
    suffix = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"{key[:110]}--{suffix}"


def session_hash(session_id: str) -> str:
    return hashlib.sha256(str(session_id).encode("utf-8")).hexdigest()[:16]


def iter_index_rows(root: Path, session: str | None, limit: int):
    if session:
        direct = root / f"{session}.jsonl"
        keyed = root / f"{session_key(session)}.jsonl"
        legacy = root / f"{session_hash(session)}.jsonl"
        if direct.exists():
            files = [direct]
        elif keyed.exists():
            files = [keyed]
        else:
            files = [legacy]
    else:
        files = sorted(
            root.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
        )
    rows = []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            row["_索引文件"] = str(path)
            rows.append(row)
    rows.sort(key=lambda item: item.get("created_at", 0), reverse=True)
    yield from rows[:limit]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default="data/plugin_data/astrbot_plugin_agentic_rpg/llm_audit_index",
    )
    parser.add_argument("--session", default="")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    rows = []
    for row in iter_index_rows(Path(args.root), args.session or None, args.limit):
        rows.append(
            {
                "索引文件": row.get("_索引文件", ""),
                "审计ID": row.get("audit_id", ""),
                "会话Key": row.get("session_key", ""),
                "会话哈希": row.get("session_hash", ""),
                "Preset": row.get("preset_name", ""),
                "阶段": row.get("stage", ""),
                "风格": row.get("style", ""),
                "Provider": row.get("provider_id", ""),
                "模型": row.get("model", ""),
                "用户预览": row.get("user_preview", ""),
                "回复预览": row.get("assistant_preview", ""),
                "是否错误": row.get("response_error", False),
            }
        )
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

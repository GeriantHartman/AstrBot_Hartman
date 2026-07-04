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


def _clip(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def iter_ledgers(root: Path, session: str | None, limit: int):
    if session:
        direct = root / session
        keyed = root / session_key(session)
        legacy = root / session_hash(session)
        if direct.exists():
            session_dir = direct
        elif keyed.exists():
            session_dir = keyed
        else:
            session_dir = legacy
        files = sorted(session_dir.glob("*.json"))
    else:
        files = sorted(root.glob("*/*.json"))
    files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    yield from files[:limit]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default="data/plugin_data/astrbot_plugin_agentic_rpg/llm_audit",
    )
    parser.add_argument("--session", default="")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--chars", type=int, default=260)
    args = parser.parse_args()

    root = Path(args.root)
    rows = []
    for path in iter_ledgers(root, args.session or None, args.limit):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            rows.append({"路径": str(path), "错误": str(exc)})
            continue
        request = doc.get("request") or {}
        response = doc.get("response") or {}
        audit_view = doc.get("audit_view") or {}
        snapshot = audit_view.get("snapshot") or {}
        current_request = audit_view.get("current_request") or {}
        rows.append(
            {
                "路径": str(path),
                "审计ID": doc.get("audit_id", ""),
                "会话Key": doc.get("session_key", ""),
                "会话哈希": doc.get("session_hash", ""),
                "阶段": doc.get("stage", ""),
                "Preset": current_request.get("preset_name", ""),
                "当前轮风格": current_request.get("style", ""),
                "快照风格分布": snapshot.get("style_counts", {}),
                "快照Preset分布": snapshot.get("preset_counts", {}),
                "当前轮模型": current_request.get("model", "") or doc.get("model", ""),
                "快照Provider分布": snapshot.get("provider_counts", {}),
                "快照模型分布": snapshot.get("model_counts", {}),
                "system字符数": len(request.get("system_prompt") or ""),
                "上下文条数": len(request.get("contexts") or []),
                "当前prompt字符数": len(request.get("prompt") or ""),
                "已标注上下文条数": len(audit_view.get("context_messages") or []),
                "可识别历史回合数": len(audit_view.get("turn_provenance") or []),
                "回复预览": _clip(response.get("text") or "", args.chars),
            }
        )
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

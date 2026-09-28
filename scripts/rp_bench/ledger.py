"""Read the RPG plugin's narrator audit ledger to recover clean per-turn text.

Only the narrator stage is recorded (llm_audit_ledger._append_turn_index), so
one index row == one narrator reply. ``response.text`` is the narrator output
before the status bar is prepended — the right view for judging.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import LIVE_DATA_DIR

RPG_DATA_ROOT = LIVE_DATA_DIR / "plugin_data" / "astrbot_plugin_agentic_rpg"
STYLE_SKILLS_MARKER = "单角色扮演注入"


def webchat_umo(username: str, session_id: str) -> str:
    """Session id the Open API routes to (open_api.py chat_send)."""
    return f"webchat:FriendMessage:webchat!{username}!{session_id}"


def _ledger_cls():
    # llm_audit_ledger imports only the stdlib, so this is side-effect free.
    from plugins.astrbot_plugin_agentic_RPG.core.llm_audit_ledger import LLMAuditLedger

    return LLMAuditLedger


def session_key(umo: str) -> str:
    return _ledger_cls().session_key(umo)


@dataclass
class LedgerTurn:
    audit_id: str
    row: dict[str, Any]
    doc: dict[str, Any] | None

    @property
    def text(self) -> str:
        resp = (self.doc or {}).get("response") or {}
        return str(resp.get("text") or "")

    @property
    def error(self) -> str:
        resp = (self.doc or {}).get("response") or {}
        return str(resp.get("error") or "")

    @property
    def provider_id(self) -> str:
        return str(self.row.get("provider_id") or "")

    @property
    def model(self) -> str:
        return str(self.row.get("model") or "")

    @property
    def pipeline(self) -> str:
        return pipeline_of(self.doc or {})

    @property
    def system_prompt(self) -> str:
        req = (self.doc or {}).get("request") or {}
        return str(req.get("system_prompt") or "")

    def request_blob(self) -> str:
        req = (self.doc or {}).get("request") or {}
        return json.dumps(req, ensure_ascii=False, default=str)


def pipeline_of(doc: dict[str, Any]) -> str:
    view = doc.get("audit_view") or {}
    if isinstance(view, dict):
        if "contract_5_0" in view:
            return "5"
        if "contract_4_0" in view:
            return "4"
    return ""


class LedgerReader:
    def __init__(self, data_root: Path = RPG_DATA_ROOT):
        self.data_root = Path(data_root)
        self.index_root = self.data_root / "llm_audit_index"
        self.doc_root = self.data_root / "llm_audit"

    def index_rows(self, umo: str) -> list[dict[str, Any]]:
        path = self.index_root / f"{session_key(umo)}.jsonl"
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def load_doc(self, umo: str, audit_id: str) -> dict[str, Any] | None:
        path = self.doc_root / session_key(umo) / f"{audit_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def new_turns(self, umo: str, seen: set[str]) -> list[LedgerTurn]:
        """Index rows not yet in ``seen`` (by audit_id), oldest first."""
        out = []
        for row in self.index_rows(umo):
            aid = str(row.get("audit_id") or "")
            if not aid or aid in seen:
                continue
            out.append(LedgerTurn(aid, row, self.load_doc(umo, aid)))
        return out

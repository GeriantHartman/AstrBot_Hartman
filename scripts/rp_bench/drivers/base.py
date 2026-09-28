"""Shared transcript record shapes for all drivers."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any

from ..config import arm_family
from ..matrix import Cell
from ..store import now_utc8


class SessionAborted(RuntimeError):
    """The session cannot produce a valid transcript; the cell is retried on resume."""


@dataclass
class TurnRecord:
    turn_id: str
    player_text: str  # canonical scripted line (what the judge sees)
    sent_text: (
        str  # what was actually sent (chat arms prefix the scene intro on turn 1)
    )
    reply_raw: str = ""
    reply_clean: str = ""
    reasoning: str = ""  # thinking-mode output when the provider returns it
    latency_s: float | None = None
    usage: dict[str, int] = field(default_factory=dict)
    error: str = ""
    provider_actual: str = ""
    model_actual: str = ""
    pipeline_actual: str = ""
    pipeline_mismatch: bool = False
    fallback_used: bool = False
    target_present: bool | None = None
    style_skills_leak: bool = False
    audit_id: str = ""
    ledger_missing: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha16(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def transcript_row(
    cell: Cell,
    *,
    turns: list[TurnRecord],
    started_at: str,
    session_ref: str = "",
    setup: dict[str, Any] | None = None,
    gate: dict[str, Any] | None = None,
    system_prompt_sha: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "cell_key": cell.key,
        "group": cell.group,
        "card": cell.card.key,
        "card_name": cell.card.name,
        "scenario_id": cell.scenario.id,
        "scenario_hash": cell.scenario.content_hash,
        "arm": cell.arm,
        "family": arm_family(cell.arm),
        "model": cell.model,
        "repeat": cell.repeat,
        "started_at": started_at,
        "finished_at": now_utc8().isoformat(),
        "session_ref": session_ref,
        "setup": setup or {},
        "gate": gate or {"passed": True, "reason": "n/a"},
        "system_prompt_sha": system_prompt_sha,
        "turns": [t.to_dict() for t in turns],
        **(extra or {}),
    }

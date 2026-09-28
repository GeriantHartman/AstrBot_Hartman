"""RPG arms (rpg4 / rpg5): drive a live AstrBot through the Open API.

Per session: fresh webchat session → /rpg start → /rpg pipeline N →
(/style close) → setup turns → presence gate → scored turns. Clean narrator
text and the actual pipeline/provider come from the plugin's audit ledger.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from ..cards import Card
from ..config import Plan
from ..ledger import STYLE_SKILLS_MARKER, LedgerReader, LedgerTurn, webchat_umo
from ..matrix import Cell
from ..normalize import clean_reply
from ..store import now_utc8
from .base import SessionAborted, TurnRecord, transcript_row
from .openapi import DashboardClient, OpenApiClient, config_plugin_set, plugin_enabled

RPG_PLUGIN_NAME = "astrbot_plugin_agentic_rpg"
STYLE_PLUGIN_NAME = "astrbot_plugin_style_skills"

START_EXISTS_MARK = "已存在于这个世界"
PIPELINE_CONFIRM = {
    "5": "已将本 session 切换为 5.0 Router Supervisor",
    "4": "已将本 session 固定为 4.0 管线",
}


def presence_markers(card: Card) -> list[str]:
    """Strings proving the card's voice block reached the narrator request."""
    markers = []
    sr = str(card.voice.get("self_reference") or "")
    if sr:
        markers.append(f"自称'{sr[:24]}")
    return markers


def target_present(card: Card, turn: LedgerTurn | None, reply_text: str) -> bool:
    if any(n and n in reply_text for n in card.names()):
        return True
    if turn is not None and turn.doc:
        blob = turn.request_blob()
        return any(m in blob for m in presence_markers(card))
    return False


class RpgDriver:
    def __init__(
        self,
        plan: Plan,
        client: OpenApiClient,
        pipeline: str,
        *,
        ledger: LedgerReader | None = None,
        dashboard: DashboardClient | None = None,
        plugin_set: list[str] | None = None,
    ):
        if pipeline not in PIPELINE_CONFIRM:
            raise ValueError(f"pipeline must be 4 or 5, got {pipeline}")
        self.plan = plan
        self.client = client
        self.pipeline = pipeline
        self.ledger = ledger or LedgerReader()
        self.dashboard = dashboard
        self.plugin_set = (
            plugin_set
            if plugin_set is not None
            else config_plugin_set(plan.open_api.config_id)
        )
        if not plugin_enabled(self.plugin_set, RPG_PLUGIN_NAME):
            raise SessionAborted(
                f"config {plan.open_api.config_id or 'default'} does not enable {RPG_PLUGIN_NAME}"
            )

    async def _send(self, cell: Cell, session_id: str, message: str):
        return await self.client.chat(
            username=self.plan.open_api.username,
            session_id=session_id,
            message=message,
            config_id=self.plan.open_api.config_id,
            selected_provider=cell.model,
        )

    async def _await_ledger(self, umo: str, seen: set[str]) -> list[LedgerTurn]:
        deadline = time.monotonic() + self.plan.open_api.ledger_wait_s
        found: list[LedgerTurn] = []
        while time.monotonic() < deadline:
            found = self.ledger.new_turns(umo, seen)
            if found and all(
                t.doc and t.doc.get("response") is not None for t in found
            ):
                return found
            await asyncio.sleep(0.5)
        return found

    async def run_session(self, cell: Cell) -> dict[str, Any]:
        started = now_utc8().isoformat()
        scenario = cell.scenario
        session_id = f"rpb-{cell.key[:10]}-{uuid.uuid4().hex[:6]}"
        umo = webchat_umo(self.plan.open_api.username, session_id)
        seen: set[str] = set()
        setup: dict[str, Any] = {"umo": umo, "steps": []}

        if self.dashboard is not None:
            await self.dashboard.update_session_rule(
                umo, "provider_perf_chat_completion", cell.model
            )
            setup["provider_pinned"] = True

        # 1) new world
        reply = await self._send(
            cell, session_id, f"/rpg start {scenario.player_name} {scenario.rpg_preset}"
        )
        setup["steps"].append({"cmd": "start", "reply": reply.text[:400]})
        if START_EXISTS_MARK in reply.text:
            raise SessionAborted(f"{cell.label()}: fresh session already had a player")
        opening = await self._await_ledger(umo, seen)
        seen.update(t.audit_id for t in opening)

        # 2) pipeline
        reply = await self._send(cell, session_id, f"/rpg pipeline {self.pipeline}")
        setup["steps"].append({"cmd": "pipeline", "reply": reply.text[:400]})
        if PIPELINE_CONFIRM[self.pipeline] not in reply.text:
            raise SessionAborted(
                f"{cell.label()}: pipeline switch not confirmed: {reply.text[:200]!r}"
            )

        # 3) keep style_skills out of RPG sessions
        if self.plan.close_style_skills_in_rpg and plugin_enabled(
            self.plugin_set, STYLE_PLUGIN_NAME
        ):
            reply = await self._send(cell, session_id, "/style close")
            setup["steps"].append({"cmd": "style_close", "reply": reply.text[:200]})

        # 4) setup turns (not scored)
        last_setup: LedgerTurn | None = opening[-1] if opening else None
        last_text = last_setup.text if last_setup else ""
        for line in scenario.rpg_setup_turns:
            reply = await self._send(cell, session_id, line)
            new = await self._await_ledger(umo, seen)
            seen.update(t.audit_id for t in new)
            if new:
                last_setup = new[-1]
            last_text = last_setup.text if last_setup else clean_reply(reply.text)
            setup["steps"].append(
                {"cmd": "setup", "text": line, "reply": last_text[:400]}
            )

        # 5) presence gate
        if not target_present(cell.card, last_setup, last_text):
            return transcript_row(
                cell,
                turns=[],
                started_at=started,
                session_ref=umo,
                setup=setup,
                gate={
                    "passed": False,
                    "reason": f"{cell.card.name} not on stage after setup",
                },
            )

        # 6) scored turns
        turns: list[TurnRecord] = []
        for turn in scenario.turns:
            t0 = time.perf_counter()
            reply = await self._send(cell, session_id, turn.text)
            latency = time.perf_counter() - t0
            new = await self._await_ledger(umo, seen)
            seen.update(t.audit_id for t in new)
            lt = new[-1] if new else None
            text = (lt.text if lt else "") or clean_reply(reply.text)
            record = TurnRecord(
                turn_id=turn.id,
                player_text=turn.text,
                sent_text=turn.text,
                reply_raw=reply.text,
                reply_clean=clean_reply(text),
                latency_s=round(latency, 3),
                usage=_usage_from_stats(reply.agent_stats),
                error=reply.error or (lt.error if lt else ""),
                ledger_missing=lt is None,
            )
            if lt is not None:
                record.audit_id = lt.audit_id
                record.provider_actual = lt.provider_id
                record.model_actual = lt.model
                record.pipeline_actual = lt.pipeline
                record.pipeline_mismatch = (
                    bool(lt.pipeline) and lt.pipeline != self.pipeline
                )
                record.fallback_used = (
                    bool(lt.provider_id) and lt.provider_id != cell.model
                )
                record.style_skills_leak = STYLE_SKILLS_MARKER in lt.system_prompt
            record.target_present = target_present(cell.card, lt, text)
            if not record.reply_clean and not record.error:
                record.error = "empty reply"
            turns.append(record)

        presence = [t.target_present for t in turns]
        rate = sum(1 for p in presence if p) / len(presence) if presence else 0.0
        gate = {
            "passed": rate >= scenario.rpg_min_scored_presence,
            "reason": f"scored presence {rate:.0%} (need {scenario.rpg_min_scored_presence:.0%})",
            "presence_rate": rate,
        }
        return transcript_row(
            cell,
            turns=turns,
            started_at=started,
            session_ref=umo,
            setup=setup,
            gate=gate,
        )


def _usage_from_stats(stats: dict[str, Any]) -> dict[str, int]:
    tu = (stats or {}).get("token_usage") or {}
    if not isinstance(tu, dict):
        return {}
    cached = int(tu.get("input_cached", 0) or 0)
    return {
        "input": int(tu.get("input_other", 0) or 0) + cached,
        "input_cached": cached,
        "output": int(tu.get("output", 0) or 0),
    }

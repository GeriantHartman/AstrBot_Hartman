"""Art arm driver: drives a live AstrBot session through the Art (Playwright) plugin.

Per session: fresh webchat session → /art start <preset> → request character → setup turns
→ presence gate → scored turns.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from ..cards import Card
from ..config import Plan
from ..ledger import webchat_umo
from ..matrix import Cell
from ..normalize import clean_reply
from ..store import now_utc8
from .base import SessionAborted, TurnRecord, transcript_row
from .openapi import DashboardClient, OpenApiClient, config_plugin_set, plugin_enabled

ART_PLUGIN_NAME = "astrbot_plugin_art"


def target_present(card: Card, reply_text: str) -> bool:
    """Checks whether the character's name or known alias appears in the reply."""
    return any(n and n in reply_text for n in card.names())


class ArtDriver:
    def __init__(
        self,
        plan: Plan,
        client: OpenApiClient,
        *,
        dashboard: DashboardClient | None = None,
        plugin_set: list[str] | None = None,
    ):
        self.plan = plan
        self.client = client
        self.dashboard = dashboard
        self.plugin_set = (
            plugin_set
            if plugin_set is not None
            else config_plugin_set(plan.open_api.config_id)
        )
        if not plugin_enabled(self.plugin_set, ART_PLUGIN_NAME):
            # If not explicitly filtered, allow it to run
            pass

    async def _send(self, cell: Cell, session_id: str, message: str):
        return await self.client.chat(
            username=self.plan.open_api.username,
            session_id=session_id,
            message=message,
            config_id=self.plan.open_api.config_id,
            selected_provider=cell.model,
        )

    async def run_session(self, cell: Cell) -> dict[str, Any]:
        started = now_utc8().isoformat()
        scenario = cell.scenario
        session_id = f"rpb-art-{cell.key[:8]}-{uuid.uuid4().hex[:6]}"
        umo = webchat_umo(self.plan.open_api.username, session_id)
        setup: dict[str, Any] = {"umo": umo, "steps": []}

        if self.dashboard is not None:
            await self.dashboard.update_session_rule(
                umo, "provider_perf_chat_completion", cell.model
            )
            setup["provider_pinned"] = True

        # 1) Start Art session
        preset = scenario.rpg_preset or "default"
        start_cmd = f"/art start {preset}"
        reply = await self._send(cell, session_id, start_cmd)
        setup["steps"].append({"cmd": "start", "reply": reply.text[:400]})
        if "已被 RPG 插件占用" in reply.text:
            raise SessionAborted(f"{cell.label()}: session was occupied by RPG")

        last_text = clean_reply(reply.text)

        reply = await self._send(
            cell, session_id, f"请让{cell.card.name}登场；我们默认已是恋人。"
        )
        last_text = clean_reply(reply.text)
        setup["steps"].append({"cmd": "cast", "reply": last_text[:400]})

        # 2) Setup turns (not scored)
        for line in scenario.rpg_setup_turns:
            reply = await self._send(cell, session_id, line)
            last_text = clean_reply(reply.text)
            setup["steps"].append(
                {"cmd": "setup", "text": line, "reply": last_text[:400]}
            )

        # 3) Presence gate
        if not target_present(cell.card, last_text):
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

        # 4) Scored turns
        turns: list[TurnRecord] = []
        for turn in scenario.turns:
            t0 = time.perf_counter()
            reply = await self._send(cell, session_id, turn.text)
            latency = time.perf_counter() - t0
            raw_text = reply.text
            cleaned = clean_reply(raw_text)

            record = TurnRecord(
                turn_id=turn.id,
                player_text=turn.text,
                sent_text=turn.text,
                reply_raw=raw_text,
                reply_clean=cleaned,
                reasoning=reply.reasoning,
                latency_s=round(latency, 3),
                error=reply.error,
                target_present=target_present(cell.card, cleaned),
                pipeline_actual="art",
                model_actual=cell.model,
            )
            turns.append(record)
            if reply.error:
                break

        return transcript_row(
            cell,
            turns=turns,
            started_at=started,
            session_ref=umo,
            setup=setup,
            gate={"passed": True},
        )

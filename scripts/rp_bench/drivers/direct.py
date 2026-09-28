"""Chat arms (bare / raw / style_skills): in-process provider, history kept by the harness.

No tools are passed and no knowledge base is consulted — the only inputs are
the system prompt built for the arm and the scripted player lines.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from ..cards import render_bare_prompt, render_persona, render_skill_persona
from ..matrix import Cell
from ..normalize import clean_reply
from ..providers import ProviderPool, provider_chat
from ..store import now_utc8
from .base import SessionAborted, TurnRecord, sha16, transcript_row

# Same wrapper AstrBot's main agent uses for persona prompts.
PERSONA_WRAPPER = "\n# Persona Instructions\n\n{persona}\n"

PromptBuilder = Callable[[Cell], Awaitable[tuple[str, dict[str, Any]]]]


def persona_base(cell: Cell) -> str:
    return PERSONA_WRAPPER.format(persona=render_persona(cell.card))


async def raw_prompt(cell: Cell) -> tuple[str, dict[str, Any]]:
    return persona_base(cell), {"source": "canonical_card"}


async def bare_prompt(cell: Cell) -> tuple[str, dict[str, Any]]:
    return render_bare_prompt(cell.card), {"source": "name_and_game_only"}


async def skill_prompt(cell: Cell) -> tuple[str, dict[str, Any]]:
    text, meta = render_skill_persona(cell.card)
    return PERSONA_WRAPPER.format(persona=text), meta


class DirectChatDriver:
    def __init__(
        self,
        pool: ProviderPool,
        builder: PromptBuilder = raw_prompt,
        *,
        max_retries: int = 1,
    ):
        self.pool = pool
        self.builder = builder
        self.max_retries = max_retries

    async def run_session(self, cell: Cell) -> dict[str, Any]:
        started = now_utc8().isoformat()
        provider = await self.pool.get(cell.model)
        system_prompt, prompt_meta = await self.builder(cell)

        history: list[dict[str, Any]] = []
        turns: list[TurnRecord] = []
        scenario = cell.scenario
        for idx, turn in enumerate(scenario.turns):
            sent = turn.text
            if idx == 0 and scenario.scene_intro:
                sent = f"{scenario.scene_intro}\n{turn.text}"
            result = None
            for _ in range(self.max_retries + 1):
                result = await provider_chat(
                    provider, prompt=sent, system_prompt=system_prompt, contexts=history
                )
                if not result.error:
                    break
            assert result is not None
            if result.error:
                raise SessionAborted(f"{cell.label()} turn {turn.id}: {result.error}")
            history += [
                {"role": "user", "content": sent},
                {"role": "assistant", "content": result.text},
            ]
            turns.append(
                TurnRecord(
                    turn_id=turn.id,
                    player_text=turn.text,
                    sent_text=sent,
                    reply_raw=result.text,
                    reply_clean=clean_reply(result.text),
                    reasoning=result.reasoning,
                    latency_s=round(result.latency_s, 3),
                    usage=result.usage,
                    provider_actual=cell.model,
                    model_actual=result.model,
                    target_present=True,
                )
            )
        return transcript_row(
            cell,
            turns=turns,
            started_at=started,
            system_prompt_sha=sha16(system_prompt),
            extra={
                "prompt_meta": prompt_meta,
                "system_prompt": system_prompt,
                "system_prompt_chars": len(system_prompt),
            },
        )

"""Dry-run: how many sessions and LLM calls a plan will cost, before spending anything.

Token figures are rough (CJK ≈ 1.5 chars/token, 400-char replies); use them
to compare plans, not to budget to the cent.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .cards import render_skill_persona, resolve_card
from .config import RPG_ARMS, Plan
from .matrix import expand
from .scenarios import load_scenarios

CHARS_PER_TOKEN = 1.5
REPLY_CHARS = 400
SYSTEM_CHARS = {"bare": 40, "raw": 9000, "style_skills": 23000}
RPG_PROMPT_CHARS = 30000  # chat template + world state + NPC package per narrator call
RPG_CALLS_PER_TURN = {
    "rpg4": 4,
    "rpg5": 5,
}  # router ~2 + director 1 + narrator 1 (+ validator)


def _chat_session_tokens(turns: int, system_chars: int) -> tuple[int, int]:
    tin = 0
    for i in range(turns):
        tin += system_chars + i * (REPLY_CHARS + 60)
    return int(tin / CHARS_PER_TOKEN), int(turns * REPLY_CHARS / CHARS_PER_TOKEN)


def estimate(plan: Plan, *, smoke: bool = False) -> dict[str, Any]:
    cards = [resolve_card(k) for k in plan.cards]
    scenarios = load_scenarios(plan.scenario_paths)
    repeats = 1 if smoke else plan.repeats
    cells = expand(
        cards,
        scenarios,
        plan.arms,
        plan.models,
        repeats,
        smoke_turns=plan.smoke_turns if smoke else None,
    )

    skill_chars: dict[str, int] = {}
    calls: Counter = Counter()
    tokens_in: Counter = Counter()
    tokens_out: Counter = Counter()
    for c in cells:
        n = len(c.scenario.turns)
        if c.arm in RPG_ARMS:
            setup = 1 + len(c.scenario.rpg_setup_turns)
            calls[c.arm] += (n + setup) * RPG_CALLS_PER_TURN[c.arm]
            tokens_in[c.model] += int((n + setup) * RPG_PROMPT_CHARS / CHARS_PER_TOKEN)
            tokens_out[c.model] += int(n * REPLY_CHARS / CHARS_PER_TOKEN)
        else:
            calls[c.arm] += n
            system_chars = SYSTEM_CHARS.get(c.arm, 9000)
            if c.arm == "skill":
                if c.card.key not in skill_chars:
                    try:
                        skill_chars[c.card.key] = render_skill_persona(c.card)[1][
                            "chars"
                        ]
                    except Exception:
                        skill_chars[c.card.key] = 0
                system_chars = skill_chars[c.card.key]
            tin, tout = _chat_session_tokens(n, system_chars)
            tokens_in[c.model] += tin
            tokens_out[c.model] += tout

    pair_jobs = 0
    judge_calls = 0
    if plan.judge.enabled:
        pair_jobs = 2 * len(plan.pairwise) * len({c.group for c in cells})
        if repeats >= 2:
            pair_jobs += 2 * len(
                {(c.card.key, c.scenario.id, c.model, c.arm) for c in cells}
            )
        if len(plan.models) >= 2:  # model-vs-model pairs within each arm
            slots = {(c.card.key, c.scenario.id, c.arm, c.repeat) for c in cells}
            pair_jobs += 2 * (len(plan.models) - 1) * len(slots)
        judge_calls = len(cells) + pair_jobs

    models = {}
    for model in plan.models:
        entry: dict[str, Any] = {
            "tokens_in": tokens_in[model],
            "tokens_out": tokens_out[model],
        }
        price = plan.prices.get(model)
        if price:
            entry["cost"] = round(
                tokens_in[model] / 1e6 * float(price.get("input", 0))
                + tokens_out[model] / 1e6 * float(price.get("output", 0)),
                2,
            )
        models[model] = entry
    return {
        "plan": plan.name,
        "smoke": smoke,
        "cards": [c.key for c in cards],
        "scenarios": [s.id for s in scenarios],
        "arms": plan.arms,
        "repeats": repeats,
        "sessions": len(cells),
        "sessions_by_arm": dict(Counter(c.arm for c in cells)),
        "generation_calls": dict(calls),
        "models": models,
        "judge": plan.judge.judge_id or None,
        "judge_calls": judge_calls,
        "judge_tokens_in": judge_calls * 20000,
        "skill_persona_chars": skill_chars,
    }


def print_estimate(plan: Plan, *, smoke: bool = False) -> dict[str, Any]:
    e = estimate(plan, smoke=smoke)
    print(f"Plan {e['plan']}{' (smoke)' if smoke else ''}")
    print(
        f"  cards={e['cards']} scenarios={e['scenarios']} arms={e['arms']} repeats={e['repeats']}"
    )
    print(
        f"  sessions: {e['sessions']}  "
        + "  ".join(f"{a}={n}" for a, n in sorted(e["sessions_by_arm"].items()))
    )
    print(
        "  generation LLM calls (approx): "
        + "  ".join(f"{a}≈{n}" for a, n in sorted(e["generation_calls"].items()))
    )
    for key, chars in e["skill_persona_chars"].items():
        print(
            f"  skill persona {key}: {chars:,} chars per call (0 = skill folder not found)"
        )
    for model, m in e["models"].items():
        line = f"  tokens {model}: in≈{m['tokens_in']:,} out≈{m['tokens_out']:,}"
        if "cost" in m:
            line += f"  cost≈{m['cost']:.2f}"
        print(line)
    if e["judge"]:
        print(
            f"  judge {e['judge']}: {e['judge_calls']} calls, in≈{e['judge_tokens_in']:,} tokens"
        )
    else:
        print("  judge: disabled (transcripts only)")
    return e

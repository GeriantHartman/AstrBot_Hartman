"""Stage orchestration: run → metrics → export → judge → pair. Every stage resumes from JSONL."""

from __future__ import annotations

import asyncio
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .cards import Card, lexical_rules, render_judge_sheet, resolve_card
from .config import CHAT_ARMS, RPG_ARMS, Plan, secret
from .matrix import Cell, expand
from .metrics import ops_metrics, session_metrics
from .scenarios import Scenario, load_scenarios
from .store import (
    FAILURES,
    JUDGE_ABS,
    JUDGE_PAIR,
    METRICS,
    TRANSCRIPTS,
    RunStore,
    now_utc8,
)


def log(msg: str) -> None:
    print(f"[rp_bench {now_utc8().strftime('%H:%M:%S')}] {msg}", flush=True)


@dataclass
class BenchContext:
    plan: Plan
    store: RunStore
    cards: dict[str, Card]
    scenarios: list[Scenario]
    smoke: bool = False
    _sheets: dict[str, str] = field(default_factory=dict)

    def cells(self) -> list[Cell]:
        return expand(
            list(self.cards.values()),
            self.scenarios,
            self.plan.arms,
            self.plan.models,
            1 if self.smoke else self.plan.repeats,
            smoke_turns=self.plan.smoke_turns if self.smoke else None,
        )

    def card(self, key: str) -> Card:
        if key not in self.cards:
            self.cards[key] = resolve_card(key)
        return self.cards[key]

    def judge_sheet(self, card_key: str) -> str:
        if card_key not in self._sheets:
            self._sheets[card_key] = render_judge_sheet(self.card(card_key))
        return self._sheets[card_key]


def load_context(plan: Plan, store: RunStore, *, smoke: bool) -> BenchContext:
    cards = [resolve_card(entry) for entry in plan.cards]
    scenarios = load_scenarios(plan.scenario_paths)
    return BenchContext(plan, store, {c.key: c for c in cards}, scenarios, smoke)


# ---------------------------------------------------------------- run stage


def scenario_meta(cell: Cell) -> dict[str, Any]:
    s = cell.scenario
    return {
        "title": s.title,
        "premise": s.premise,
        "dimensions": s.dimensions,
        "probes": [{"turn": t.id, **p.to_dict()} for t in s.turns for p in t.probes],
    }


async def _build_drivers(ctx: BenchContext) -> dict[str, Any]:
    plan = ctx.plan
    drivers: dict[str, Any] = {}
    pool = None
    if any(a in plan.arms for a in CHAT_ARMS):
        from .drivers.direct import DirectChatDriver, bare_prompt, skill_prompt
        from .providers import ProviderPool

        pool = ProviderPool()
        if "bare" in plan.arms:
            drivers["bare"] = DirectChatDriver(pool, bare_prompt)
        if "skill" in plan.arms:
            drivers["skill"] = DirectChatDriver(pool, skill_prompt)
        if "raw" in plan.arms:
            drivers["raw"] = DirectChatDriver(pool)
        if "style_skills" in plan.arms:
            from .drivers.style_skills import StyleSkillsPromptBuilder

            drivers["style_skills"] = DirectChatDriver(
                pool, StyleSkillsPromptBuilder(plan.style_skills_config)
            )
    if plan.uses_rpg():
        from .drivers.openapi import DashboardClient, OpenApiClient
        from .drivers.rpg import RpgDriver

        client = OpenApiClient(
            plan.open_api.base_url,
            secret(plan.open_api.api_key_env, "astrbot_api_key"),
            timeout_s=plan.open_api.timeout_s,
        )
        dash_user = secret("RPBENCH_DASH_USER", "dashboard_user")
        dash_pwd = secret("RPBENCH_DASH_PASSWORD", "dashboard_password")
        dashboard = (
            DashboardClient(plan.open_api.base_url, dash_user, dash_pwd)
            if dash_user and dash_pwd
            else None
        )
        for arm in RPG_ARMS:
            if arm in plan.arms:
                if arm == "art":
                    from .drivers.art import ArtDriver

                    drivers["art"] = ArtDriver(plan, client, dashboard=dashboard)
                else:
                    drivers[arm] = RpgDriver(plan, client, arm[-1], dashboard=dashboard)
    drivers["_pool"] = pool
    return drivers


async def run_stage(ctx: BenchContext) -> dict[str, int]:
    done = ctx.store.completed(TRANSCRIPTS)
    cells = ctx.cells()
    todo = [c for c in cells if c.key not in done]
    log(
        f"run: {len(todo)} sessions to generate ({len(cells) - len(todo)} already done)"
    )
    counts = {"planned": len(cells), "attempted": len(todo), "ok": 0, "failed": 0}
    if not todo:
        return counts
    drivers = await _build_drivers(ctx)
    sems = {
        "rpg": asyncio.Semaphore(max(1, ctx.plan.concurrency.get("rpg", 1))),
        "direct": asyncio.Semaphore(max(1, ctx.plan.concurrency.get("direct", 4))),
    }

    async def one(cell: Cell) -> None:
        sem = sems["rpg"] if cell.arm in RPG_ARMS else sems["direct"]
        async with sem:
            log(f"run  ▶ {cell.label()}")
            try:
                row = await drivers[cell.arm].run_session(cell)
            except Exception as exc:
                counts["failed"] += 1
                ctx.store.append(
                    FAILURES,
                    {
                        "cell_key": cell.key,
                        "label": cell.label(),
                        "stage": "run",
                        "error": f"{type(exc).__name__}: {exc}",
                        "trace": traceback.format_exc(limit=6),
                        "at": now_utc8().isoformat(),
                    },
                )
                log(f"run  ✗ {cell.label()}: {type(exc).__name__}: {exc}")
                return
            row["scenario_meta"] = scenario_meta(cell)
            row["card_sha"] = cell.card.sha256
            ctx.store.append(TRANSCRIPTS, row)
            counts["ok"] += 1
            gate = (
                ""
                if row["gate"].get("passed", True)
                else f" (gate failed: {row['gate'].get('reason')})"
            )
            log(f"run  ✓ {cell.label()}{gate}")

    try:
        await asyncio.gather(*(one(c) for c in todo))
    finally:
        pool = drivers.get("_pool")
        if pool is not None:
            await pool.close()
    return counts


# ------------------------------------------------------------ metrics stage


def latest_transcripts(store: RunStore) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in store.read(TRANSCRIPTS):
        rows[row["cell_key"]] = row
    return rows


def metrics_stage(ctx: BenchContext) -> None:
    done = ctx.store.completed(METRICS)
    rows = [r for k, r in latest_transcripts(ctx.store).items() if k not in done]
    for row in rows:
        rules = lexical_rules(ctx.card(row["card"]))
        replies = [t.get("reply_clean") or "" for t in row.get("turns") or []]
        m = session_metrics(replies, rules)
        per_turn = m.pop("per_turn", [])
        ctx.store.append(
            METRICS,
            {
                "cell_key": row["cell_key"],
                "arm": row["arm"],
                "card": row["card"],
                "model": row["model"],
                "scenario_id": row["scenario_id"],
                "repeat": row["repeat"],
                "gate_passed": row.get("gate", {}).get("passed", True),
                "text": m,
                "ops": ops_metrics(row.get("turns") or []),
                "per_turn": per_turn,
                "rules": rules.to_dict(),
            },
        )
    log(f"metrics: computed {len(rows)} sessions")


def export_stage(ctx: BenchContext) -> dict[str, Any]:
    from .export import export_run

    result = export_run(ctx.store)
    log(
        f"export: {len(result['sessions'])} sessions, {len(result['compare'])} side-by-side comparisons"
    )
    return result


# -------------------------------------------------------------- judge stage


def _judge_client(ctx: BenchContext):
    from .judge.runner import JudgeClient

    pool = None
    if ctx.plan.judge.provider_id:
        from .providers import ProviderPool

        pool = ProviderPool()
    return JudgeClient(ctx.plan.judge, pool), pool


async def judge_stage(ctx: BenchContext) -> None:
    if not ctx.plan.judge.enabled:
        log("judge: skipped (no judge configured in the plan)")
        return
    from .judge.rubric import RUBRIC_VERSION
    from .judge.runner import judge_abs

    client, pool = _judge_client(ctx)
    done = {
        r["cell_key"]
        for r in ctx.store.read(JUDGE_ABS)
        if r.get("rubric_version") == RUBRIC_VERSION
        and r.get("judge_id") == client.judge_id
        and not r.get("error")
    }
    rows = [
        r
        for k, r in latest_transcripts(ctx.store).items()
        if k not in done and r.get("turns")
    ]
    log(f"judge: {len(rows)} transcripts to score (judge={client.judge_id})")
    sem = asyncio.Semaphore(max(1, ctx.plan.concurrency.get("judge", 4)))

    async def one(row: dict[str, Any]) -> None:
        async with sem:
            result = await judge_abs(client, row, ctx.judge_sheet(row["card"]))
            ctx.store.append(JUDGE_ABS, result)
            status = "✗ " + result["error"] if result["error"] else "✓"
            log(
                f"judge {status} {row['card']}/{row['scenario_id']}/{row['arm']}#{row['repeat']}"
            )

    try:
        await asyncio.gather(*(one(r) for r in rows))
    finally:
        if pool is not None:
            await pool.close()


# --------------------------------------------------------------- pair stage


def plan_pairs(
    ctx: BenchContext,
    transcripts: dict[str, dict[str, Any]],
    *,
    noise_floor: bool = True,
) -> list[tuple[str, dict, dict, str, str]]:
    """(kind, row_x, row_y, label_x, label_y) for every comparison to judge."""
    by_group: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    by_arm_seq: dict[tuple, dict[int, dict[str, Any]]] = defaultdict(dict)
    for row in transcripts.values():
        if not row.get("turns") or not row.get("gate", {}).get("passed", True):
            continue
        by_group[row["group"]][row["arm"]] = row
        seq_key = (
            row["card"],
            row["scenario_id"],
            row["scenario_hash"],
            row["model"],
            row["arm"],
        )
        by_arm_seq[seq_key][int(row["repeat"])] = row

    pairs = []
    for arms in by_group.values():
        for x, y in ctx.plan.pairwise:
            if x in arms and y in arms:
                pairs.append(("arm", arms[x], arms[y], x, y))
    # same arm, same script, different models: models[0] vs each other model
    by_model: dict[tuple, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in transcripts.values():
        if row.get("turns") and row.get("gate", {}).get("passed", True):
            k = (
                row["card"],
                row["scenario_id"],
                row["scenario_hash"],
                row["arm"],
                int(row["repeat"]),
            )
            by_model[k][row["model"]] = row
    models = ctx.plan.models
    for (_, _, _, arm, _), rows in by_model.items():
        if models and models[0] in rows:
            for other in models[1:]:
                if other in rows:
                    pairs.append(
                        (
                            "model",
                            rows[models[0]],
                            rows[other],
                            f"{arm}:{models[0]}",
                            f"{arm}:{other}",
                        )
                    )
    if noise_floor:
        for (_, _, _, _, arm), reps in by_arm_seq.items():
            if 0 in reps and 1 in reps:
                pairs.append(("self", reps[0], reps[1], f"{arm}#0", f"{arm}#1"))
    return pairs


def baseline_pairs(
    transcripts: dict[str, dict[str, Any]], baseline: dict[str, dict[str, Any]]
) -> list[tuple[str, dict, dict, str, str]]:
    def key(r):
        return (
            r["card"],
            r["scenario_id"],
            r["scenario_hash"],
            r["arm"],
            r["model"],
            int(r["repeat"]),
        )

    base_index = {
        key(r): r
        for r in baseline.values()
        if r.get("turns") and r.get("gate", {}).get("passed", True)
    }
    pairs = []
    for row in transcripts.values():
        if not row.get("turns") or not row.get("gate", {}).get("passed", True):
            continue
        b = base_index.get(key(row))
        if b is not None:
            pairs.append(
                ("baseline", row, b, f"{row['arm']}@new", f"{row['arm']}@base")
            )
    return pairs


async def pair_stage(
    ctx: BenchContext, *, baseline_dir: Path | None = None, noise_floor: bool = True
) -> None:
    if not ctx.plan.judge.enabled:
        log("pair: skipped (no judge configured in the plan)")
        return
    from .judge.rubric import RUBRIC_VERSION
    from .judge.runner import judge_pair

    transcripts = latest_transcripts(ctx.store)
    pairs = plan_pairs(ctx, transcripts, noise_floor=noise_floor)
    if baseline_dir is not None:
        base_store = RunStore(baseline_dir)
        pairs += baseline_pairs(transcripts, latest_transcripts(base_store))
    if not pairs:
        log(
            "pair: nothing to compare (need pairwise arms in the plan, repeats ≥ 2, or --baseline)"
        )
        return

    client, pool = _judge_client(ctx)
    done = {
        (r["pair_key"], r["order"])
        for r in ctx.store.read(JUDGE_PAIR)
        if r.get("rubric_version") == RUBRIC_VERSION
        and r.get("judge_id") == client.judge_id
        and not r.get("error")
    }
    jobs = []
    for kind, rx, ry, lx, ly in pairs:
        for order in (1, 2):
            if (f"{rx['cell_key']}|{ry['cell_key']}", order) not in done:
                jobs.append((kind, rx, ry, lx, ly, order))
    log(
        f"pair: {len(jobs)} blind comparisons to run ({len(pairs)} pairs × 2 orders, minus cached)"
    )
    sem = asyncio.Semaphore(max(1, ctx.plan.concurrency.get("judge", 4)))

    async def one(job) -> None:
        kind, rx, ry, lx, ly, order = job
        async with sem:
            result = await judge_pair(
                client,
                rx,
                ry,
                ctx.judge_sheet(rx["card"]),
                order=order,
                kind=kind,
                label_x=lx,
                label_y=ly,
            )
            ctx.store.append(JUDGE_PAIR, result)
            log(
                f"pair {'✗ ' + result['error'] if result['error'] else '✓'} {lx} vs {ly} order={order}"
            )

    try:
        await asyncio.gather(*(one(j) for j in jobs))
    finally:
        if pool is not None:
            await pool.close()

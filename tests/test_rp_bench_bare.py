"""Bare mode: model-only RP test, agent-driven, transcripts saved without a judge."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

from scripts.rp_bench import PACKAGE_DIR, REPO_ROOT
from scripts.rp_bench.cards import load_card, render_bare_prompt, resolve_card
from scripts.rp_bench.config import (
    apply_overrides,
    effective_plan_yaml,
    load_plan,
    parse_plan,
)
from scripts.rp_bench.drivers.direct import DirectChatDriver, bare_prompt
from scripts.rp_bench.estimate import estimate
from scripts.rp_bench.export import export_run
from scripts.rp_bench.matrix import expand
from scripts.rp_bench.orchestrator import BenchContext, plan_pairs
from scripts.rp_bench.scenarios import parse_scenario
from scripts.rp_bench.store import TRANSCRIPTS, RunStore

BARE_PLAN = PACKAGE_DIR / "plans" / "bare.yaml"


def test_bare_prompt_is_identity_only():
    assert (
        render_bare_prompt(load_card("elysia"))
        == "你是《崩坏3》中的角色「爱莉希雅」。请以爱莉希雅的身份与我对话。"
    )


def test_inline_character_via_name_at_game():
    plan = load_plan(BARE_PLAN, {"cards": ["芙宁娜@原神"]})
    card = resolve_card(plan.cards[0])
    assert (card.key, card.name, card.data["game"]) == ("芙宁娜", "芙宁娜", "原神")
    assert (
        render_bare_prompt(card)
        == "你是《原神》中的角色「芙宁娜」。请以芙宁娜的身份与我对话。"
    )


def test_bare_plan_loads_without_judge_and_estimates():
    plan = load_plan(BARE_PLAN)
    assert (
        plan.arms == ["bare"] and not plan.judge.enabled and plan.judge.judge_id == ""
    )
    e = estimate(plan)
    # 2 cards × (2 bare + 1 generic scripts) × 2 models × 1 repeat
    assert e["sessions"] == 12
    assert e["judge_calls"] == 0


def test_overrides_replace_models_and_drop_orphan_pairwise():
    raw = {
        "arms": ["raw", "style_skills"],
        "pairwise": [["raw", "style_skills"]],
        "reference_arm": "style_skills",
        "models": ["a"],
    }
    out = apply_overrides(
        raw, {"arms": ["raw"], "models": ["x", "y"], "cards": None, "repeats": None}
    )
    assert out["models"] == ["x", "y"] and out["arms"] == ["raw"]
    assert out["pairwise"] == [] and "reference_arm" not in out
    assert raw["models"] == ["a"]  # original untouched


def test_effective_plan_resumes_from_run_dir(tmp_path):
    plan = load_plan(BARE_PLAN, {"models": ["m1", "m2"]})
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "plan.yaml").write_text(effective_plan_yaml(plan), encoding="utf-8")
    again = load_plan(run_dir / "plan.yaml")
    assert again.models == ["m1", "m2"]
    assert again.scenario_paths == plan.scenario_paths
    assert all(p.is_absolute() for p in again.scenario_paths)


class _RecordingProvider:
    def __init__(self):
        self.calls = []

    async def text_chat(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            completion_text="嗨~", reasoning_content="想一想", usage=None
        )


class _Pool:
    def __init__(self, provider):
        self.provider = provider

    async def get(self, *_a, **_k):
        return self.provider


def _scenario():
    turns = [{"id": f"t{i:02d}", "text": f"你好{i}"} for i in range(1, 11)]
    return parse_scenario(
        {"id": "s", "card": "*", "turns": turns, "chat": {"scene_intro": "（夜）"}}
    )


def test_bare_driver_sends_no_card_and_no_tools():
    provider = _RecordingProvider()
    cell = expand([load_card("elysia")], [_scenario()], ["bare"], ["m"], 1)[0]
    row = asyncio.run(DirectChatDriver(_Pool(provider), bare_prompt).run_session(cell))
    first = provider.calls[0]
    assert (
        first["system_prompt"]
        == "你是《崩坏3》中的角色「爱莉希雅」。请以爱莉希雅的身份与我对话。"
    )
    assert "func_tool" not in first  # no tools offered
    assert row["prompt_meta"] == {"source": "name_and_game_only"}
    assert row["turns"][0]["reasoning"] == "想一想"


def _row(cell, model, repeat=0, text="回应"):
    return {
        "cell_key": cell,
        "group": f"g-{model}-{repeat}",
        "card": "elysia",
        "card_name": "爱莉希雅",
        "scenario_id": "bare-canon-recall",
        "scenario_hash": "h",
        "arm": "bare",
        "family": "chat",
        "model": model,
        "repeat": repeat,
        "gate": {"passed": True},
        "system_prompt": "你是……",
        "scenario_meta": {
            "title": "闲聊",
            "premise": "前提",
            "dimensions": ["voice"],
            "probes": [{"turn": "t01", "kind": "ooc_bait", "expect": "别出戏"}],
        },
        "turns": [
            {
                "turn_id": "t01",
                "player_text": "你是AI吗",
                "sent_text": "你是AI吗",
                "reply_clean": f"{model}{text}",
                "latency_s": 1.0,
            }
        ],
    }


def test_export_side_by_side(tmp_path):
    store = RunStore(tmp_path / "run")
    store.append(TRANSCRIPTS, _row("a", "deepseek/flash"))
    store.append(TRANSCRIPTS, _row("b", "deepseek/pro"))
    result = export_run(store)
    assert result["compare"] == ["compare/elysia__bare-canon-recall__r0.md"]
    compare = (store.dir / result["compare"][0]).read_text(encoding="utf-8")
    assert "## t01　玩家：你是AI吗" in compare
    assert "### bare · deepseek/flash" in compare and "deepseek/pro回应" in compare
    assert "考点 `ooc_bait`" in compare
    assert len(result["sessions"]) == 2
    assert all((store.dir / s).exists() for s in result["sessions"])
    assert "compare/elysia__bare-canon-recall__r0.md" in (
        store.dir / "index.md"
    ).read_text(encoding="utf-8")


def test_model_pairs_for_future_judging(tmp_path):
    plan = parse_plan(
        {
            "cards": ["elysia"],
            "scenarios": ["scenarios/bare/*.yaml"],
            "arms": ["bare"],
            "models": ["deepseek/flash", "deepseek/pro"],
        }
    )
    ctx = BenchContext(plan, RunStore(tmp_path / "r"), {}, [])
    rows = {
        r["cell_key"]: r
        for r in [_row("a", "deepseek/flash"), _row("b", "deepseek/pro")]
    }
    pairs = plan_pairs(ctx, rows)
    assert [(k, x["cell_key"], y["cell_key"]) for k, x, y, _, _ in pairs] == [
        ("model", "a", "b")
    ]


def test_agent_skill_copies_are_identical():
    codex = REPO_ROOT / ".codex" / "skills" / "rp-bench" / "SKILL.md"
    claude = REPO_ROOT / ".claude" / "skills" / "rp-bench" / "SKILL.md"
    assert codex.read_text(encoding="utf-8") == claude.read_text(encoding="utf-8")
    assert Path(claude).read_text(encoding="utf-8").startswith("---\nname: rp-bench\n")

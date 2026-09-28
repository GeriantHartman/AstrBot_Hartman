"""--add-arms: extend an existing run without regenerating its sessions."""

import pytest

from scripts.rp_bench.__main__ import extend_run_arms
from scripts.rp_bench.cards import load_card
from scripts.rp_bench.config import effective_plan_yaml, load_plan
from scripts.rp_bench.matrix import expand
from scripts.rp_bench.scenarios import load_scenarios
from scripts.rp_bench.store import MANIFEST, RunStore


def _run(tmp_path):
    plan = load_plan(
        "plans/skill-card.yaml",
        {"models": ["deepseek/deepseek-flash"], "cards": ["cyrene"]},
    )
    run = tmp_path / "run"
    store = RunStore(run)
    store.write_text("plan.yaml", effective_plan_yaml(plan))
    store.write_json(MANIFEST, {"plan": {"arms": plan.arms}})
    return run


def _keys(plan):
    cards = [load_card(c) for c in plan.cards]
    return {
        c.key: c.arm
        for c in expand(
            cards,
            load_scenarios(plan.scenario_paths),
            plan.arms,
            plan.models,
            plan.repeats,
        )
    }


def test_add_arms_keeps_existing_keys_and_adds_new_cells(tmp_path):
    run = _run(tmp_path)
    before = _keys(load_plan(run / "plan.yaml"))
    assert extend_run_arms(run, ["raw"]) == ["bare", "skill", "raw"]
    after = _keys(load_plan(run / "plan.yaml"))
    assert set(before) <= set(after)  # nothing already generated is invalidated
    assert {a for k, a in after.items() if k not in before} == {"raw"}
    man = RunStore(run).read_json(MANIFEST)
    assert man["plan"]["arms"] == ["bare", "skill", "raw"]
    assert man["history"][0]["added_arms"] == ["raw"]


def test_add_arms_is_idempotent_and_validated(tmp_path):
    run = _run(tmp_path)
    extend_run_arms(run, ["raw"])
    assert extend_run_arms(run, ["raw"]) == ["bare", "skill", "raw"]
    with pytest.raises(SystemExit):
        extend_run_arms(run, ["nonsense"])

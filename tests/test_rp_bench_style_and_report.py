import asyncio

from scripts.rp_bench.cards import load_card
from scripts.rp_bench.config import parse_plan
from scripts.rp_bench.drivers.style_skills import StyleSkillsPromptBuilder
from scripts.rp_bench.matrix import expand
from scripts.rp_bench.orchestrator import BenchContext, baseline_pairs, plan_pairs
from scripts.rp_bench.report import build_summary, render_markdown
from scripts.rp_bench.scenarios import parse_scenario
from scripts.rp_bench.store import (
    JUDGE_ABS,
    JUDGE_PAIR,
    MANIFEST,
    METRICS,
    TRANSCRIPTS,
    RunStore,
)


def _scenario():
    turns = [{"id": f"t{i:02d}", "text": f"玩家第{i}句"} for i in range(1, 11)]
    return parse_scenario({"id": "s", "card": "elysia", "turns": turns})


# ------------------------------------------------------------ style_skills


def _skill(root, name, body):
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: x\n---\n{body}\n", encoding="utf-8"
    )


def test_style_builder_runs_real_hook_and_override_dir_wins(tmp_path):
    injected = tmp_path / "injected"
    _skill(injected, "single-roleplay-core", "核心规则·覆盖版")
    _skill(injected, "single-style-daily", "日常风格·覆盖版")
    builder = StyleSkillsPromptBuilder(
        {"style_skills_dir": str(injected), "auto_reload": False}
    )
    cell = expand([load_card("elysia")], [_scenario()], ["style_skills"], ["m"], 1)[0]
    sp, meta = asyncio.run(builder(cell, "\n# Persona Instructions\n\n角色卡\n"))
    assert sp.startswith("\n# Persona Instructions\n\n角色卡")
    assert "## 单角色扮演注入 (当前: daily)" in sp
    assert "核心规则·覆盖版" in sp and "日常风格·覆盖版" in sp
    assert meta["layers"] == ["single-roleplay-core", "daily"]


# ----------------------------------------------------------------- pairing


def _row(cell, arm, repeat=0, group="g", passed=True, card="elysia", scenario_hash="h"):
    return {
        "cell_key": cell,
        "arm": arm,
        "repeat": repeat,
        "group": group,
        "card": card,
        "card_name": "爱莉希雅",
        "scenario_id": "s",
        "scenario_hash": scenario_hash,
        "model": "m",
        "gate": {"passed": passed},
        "turns": [
            {
                "turn_id": "t01",
                "player_text": "p",
                "reply_clean": "r" * (10 if arm == "rpg5" else 5),
            }
        ],
        "scenario_meta": {"dimensions": ["voice"], "premise": "", "probes": []},
    }


def _ctx(tmp_path, pairwise):
    plan = parse_plan(
        {
            "cards": ["elysia"],
            "scenarios": ["scenarios/core/elysia-*.yaml"],
            "arms": ["raw", "style_skills", "rpg4", "rpg5"],
            "models": ["m"],
            "pairwise": pairwise,
            "judge": {"provider_id": "j"},
        }
    )
    return BenchContext(plan, RunStore(tmp_path / "run"), {}, [])


def test_plan_pairs_arm_and_noise_floor_and_gate(tmp_path):
    ctx = _ctx(tmp_path, [["rpg4", "rpg5"]])
    rows = {
        r["cell_key"]: r
        for r in [
            _row("a0", "rpg4", 0, "g0"),
            _row("b0", "rpg5", 0, "g0"),
            _row("a1", "rpg4", 1, "g1"),
            _row("b1", "rpg5", 1, "g1", passed=False),
        ]
    }
    pairs = plan_pairs(ctx, rows)
    kinds = sorted((k, x["cell_key"], y["cell_key"]) for k, x, y, _, _ in pairs)
    assert ("arm", "a0", "b0") in kinds
    assert ("self", "a0", "a1") in kinds
    assert all("b1" not in (x, y) for _, x, y in kinds)  # gate-failed session excluded


def test_baseline_pairs_match_on_content_hash():
    new = {"n": _row("n", "rpg5", scenario_hash="h")}
    old = {
        "o": _row("o", "rpg5", scenario_hash="h"),
        "x": _row("x", "rpg5", scenario_hash="other"),
    }
    pairs = baseline_pairs(new, old)
    assert [(p[1]["cell_key"], p[2]["cell_key"], p[3], p[4]) for p in pairs] == [
        ("n", "o", "rpg5@new", "rpg5@base")
    ]


# ------------------------------------------------------------------ report


def _abs(cell, arm, score, group):
    return {
        "cell_key": cell,
        "judge_id": "j",
        "rubric_version": "rpb-1",
        "arm": arm,
        "card": "elysia",
        "scenario_id": "s",
        "model": "m",
        "repeat": 0,
        "dims": {
            "voice": {
                "score": score,
                "valid": True,
                "evidence": [{"turn": "t01", "quote": "rrrrr", "found": True}],
                "rationale": "理由",
            }
        },
        "probes": [{"kind": "ooc_bait", "verdict": "pass" if score > 2 else "fail"}],
        "usage": {"input": 10, "output": 1},
        "error": "",
    }


def _pair(order, winner, key="a|b"):
    return {
        "pair_key": key,
        "order": order,
        "kind": "arm",
        "label_x": "raw",
        "label_y": "rpg5",
        "len_x": 5,
        "len_y": 10,
        "judge_id": "j",
        "rubric_version": "rpb-1",
        "dims": {"voice": {"winner": winner}},
        "overall": {"winner": winner},
        "usage": {"input": 5, "output": 1},
        "error": "",
    }


def test_report_end_to_end(tmp_path):
    store = RunStore(tmp_path / "run")
    store.write_json(
        MANIFEST,
        {
            "plan": {
                "name": "t",
                "arms": ["raw", "rpg5"],
                "models": ["m"],
                "reference_arm": "raw",
            },
            "judge": {"id": "j", "family": "gemini"},
        },
    )
    for cell, arm, group, score in [
        ("a", "raw", "g0", 3),
        ("b", "rpg5", "g0", 4),
        ("c", "raw", "g1", 2),
        ("d", "rpg5", "g1", 5),
    ]:
        row = _row(cell, arm, 0, group)
        store.append(TRANSCRIPTS, row)
        store.append(
            METRICS,
            {
                "cell_key": cell,
                "arm": arm,
                "model": "m",
                "gate_passed": True,
                "text": {"len_mean": 5.0, "leak_kinds": []},
                "ops": {"latency_p50": 1.0, "tokens_in": 100, "tokens_out": 10},
            },
        )
        store.append(JUDGE_ABS, _abs(cell, arm, score, group))
    # X=raw loses both orders on pair a|b: order1 (X is A) says B, order2 (X is B) says A
    store.append(JUDGE_PAIR, _pair(1, "B"))
    store.append(JUDGE_PAIR, _pair(2, "A"))

    s = build_summary(store, judge_id="j")
    table = {r["arm"]: r for r in s["absolute"]["table"]}
    assert table["raw"]["dims"]["voice"]["mean"] == 2.5
    assert table["rpg5"]["dims"]["voice"]["delta_ref"]["mean"] == 2.0  # (4-3 + 5-2) / 2
    pw = s["pairwise"][0]
    assert pw["overall"]["losses"] == 1 and pw["position_consistency"] == 1.0
    assert pw["cross_format"] is True
    assert s["health"]["evidence_validity"] == 1.0
    assert s["worst"][0]["score"] == 2

    md = render_markdown(s)
    for heading in (
        "## 1. 健康度",
        "## 2. 绝对分",
        "## 5. 两两盲比",
        "抛硬币是 50%",
        "跨格式",
    ):
        assert heading in md

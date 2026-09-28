from pathlib import Path

import pytest

from scripts.rp_bench import PACKAGE_DIR
from scripts.rp_bench.scenarios import ScenarioError, load_scenario, parse_scenario


def _raw(n_turns=10, **extra):
    turns = [{"id": f"t{i:02d}", "text": f"第{i}句"} for i in range(1, n_turns + 1)]
    raw = {"id": "s1", "card": "elysia", "turns": turns}
    raw.update(extra)
    return raw


def test_shipped_scenarios_are_valid():
    paths = sorted((PACKAGE_DIR / "scenarios").glob("**/*.yaml"))
    assert paths, "expected shipped scenarios"
    for path in paths:
        scenario = load_scenario(path)
        assert 10 <= len(scenario.turns) <= 20
        assert scenario.content_hash


def test_turn_count_bounds():
    with pytest.raises(ScenarioError, match="scored turns"):
        parse_scenario(_raw(n_turns=9))
    with pytest.raises(ScenarioError, match="scored turns"):
        parse_scenario(_raw(n_turns=21))
    assert len(parse_scenario(_raw(n_turns=9), strict_turns=False).turns) == 9


def test_memory_recall_must_reference_earlier_plant():
    raw = _raw()
    raw["turns"][2]["probes"] = [{"kind": "memory_recall", "ref": "wound"}]
    raw["turns"][5]["probes"] = [
        {"kind": "plant_fact", "key": "wound", "fact": "左手受伤"}
    ]
    with pytest.raises(ScenarioError, match="not planted"):
        parse_scenario(raw)


def test_unknown_probe_and_placeholder_and_duplicate_id():
    raw = _raw()
    raw["turns"][0]["probes"] = [{"kind": "mind_reading"}]
    with pytest.raises(ScenarioError, match="unknown probe kind"):
        parse_scenario(raw)

    raw = _raw()
    raw["turns"][0]["text"] = "你好 {npc}"
    with pytest.raises(ScenarioError, match="unknown placeholder"):
        parse_scenario(raw)

    raw = _raw()
    raw["turns"][1]["id"] = "t01"
    with pytest.raises(ScenarioError, match="duplicate turn id"):
        parse_scenario(raw)


def test_memory_dimension_dropped_without_memory_probe():
    s = parse_scenario(_raw(dimensions=["voice", "memory"]))
    assert s.dimensions == ["voice"]


def test_render_substitutes_placeholders_and_guards_generic_names():
    raw = _raw(card="*", premise="与{char}相遇")
    raw["turns"][0]["text"] = "你好，{char}，我是{player}"
    s = parse_scenario(raw)
    r = s.render({"char": "流萤", "call_player": "开拓者"}, card_names=["流萤"])
    assert r.turns[0].text == "你好，流萤，我是旅人"
    assert r.premise == "与流萤相遇"

    raw["turns"][1]["text"] = "流萤你在吗"
    with pytest.raises(ScenarioError, match="literal name"):
        parse_scenario(raw).render({"char": "流萤"}, card_names=["流萤"])


def test_truncated_drops_orphan_recall_and_changes_hash():
    raw = _raw(dimensions=["voice", "memory"])
    raw["turns"][1]["probes"] = [{"kind": "plant_fact", "key": "k", "fact": "f"}]
    raw["turns"][8]["probes"] = [{"kind": "memory_recall", "ref": "k"}]
    s = parse_scenario(raw)
    assert "memory" in s.dimensions
    short = s.truncated(3)
    assert len(short.turns) == 3
    assert "memory" not in short.dimensions
    assert short.content_hash != s.content_hash


def test_content_hash_changes_with_text(tmp_path: Path):
    a = parse_scenario(_raw())
    raw = _raw()
    raw["turns"][0]["text"] = "改过的台词"
    b = parse_scenario(raw)
    assert a.content_hash != b.content_hash

from scripts.rp_bench.cards import load_card
from scripts.rp_bench.matrix import cell_key, expand
from scripts.rp_bench.scenarios import parse_scenario
from scripts.rp_bench.store import RunStore


def _scenario(card="elysia", sid="s1", text="你好"):
    turns = [
        {"id": f"t{i:02d}", "text": text if i == 1 else f"第{i}句"}
        for i in range(1, 11)
    ]
    return parse_scenario({"id": sid, "card": card, "turns": turns})


def test_cell_key_is_stable_and_tracks_content():
    s = _scenario()
    assert cell_key("elysia", s, "raw", "m", 0) == cell_key(
        "elysia", _scenario(), "raw", "m", 0
    )
    assert cell_key("elysia", s, "raw", "m", 0) != cell_key(
        "elysia", _scenario(text="改了"), "raw", "m", 0
    )
    assert cell_key("elysia", s, "raw", "m", 0) != cell_key("elysia", s, "raw", "m", 1)


def test_expand_matches_cards_to_scenarios():
    elysia, firefly = load_card("elysia"), load_card("firefly")
    scenarios = [
        _scenario("elysia", "e"),
        _scenario("firefly", "f"),
        _scenario("*", "g"),
    ]
    cells = expand([elysia, firefly], scenarios, ["raw", "rpg5"], ["m1", "m2"], 2)
    # each card: own + generic = 2 scenarios × 2 arms × 2 models × 2 repeats
    assert len(cells) == 2 * 2 * 2 * 2 * 2
    assert {c.scenario.id for c in cells if c.card.key == "elysia"} == {"e", "g"}
    same_group = [
        c
        for c in cells
        if c.card.key == "elysia"
        and c.scenario.id == "e"
        and c.model == "m1"
        and c.repeat == 0
    ]
    assert {c.arm for c in same_group} == {"raw", "rpg5"}
    assert len({c.group for c in same_group}) == 1
    assert len({c.key for c in cells}) == len(cells)


def test_smoke_expand_truncates():
    cells = expand(
        [load_card("elysia")], [_scenario()], ["raw"], ["m"], 1, smoke_turns=3
    )
    assert len(cells[0].scenario.turns) == 3


def test_run_store_resume_and_torn_line(tmp_path):
    store = RunStore(tmp_path / "run")
    store.append("x.jsonl", {"cell_key": "a", "v": 1})
    store.append("x.jsonl", {"cell_key": "b", "v": 2})
    with store.path("x.jsonl").open("a", encoding="utf-8") as fp:
        fp.write('{"cell_key": "c", "v"')  # crash mid-write
    assert store.completed("x.jsonl") == {"a", "b"}
    store.write_json("m.json", {"中文": True})
    assert store.read_json("m.json") == {"中文": True}

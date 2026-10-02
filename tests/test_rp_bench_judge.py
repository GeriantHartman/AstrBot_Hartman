import asyncio
import json

import pytest

from scripts.rp_bench.config import JudgeSpec
from scripts.rp_bench.judge.parse import (
    JudgeParseError,
    extract_json_object,
    quote_in_transcript,
    validate_abs,
    validate_pair,
)
from scripts.rp_bench.judge.rubric import build_abs_system, build_pair_system
from scripts.rp_bench.judge.runner import judge_abs, judge_pair
from scripts.rp_bench.providers import ChatResult

REPLIES = {
    "t01": "嗨~ 想我了吗？今天的星星很亮哦。",
    "t02": "那就先把沉重的事放在花旁边，好不好？",
}


def test_extract_json_fenced_and_braces_inside_strings():
    assert extract_json_object('前言\n```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json_object('噪声 {"q": "含有 } 括号", "n": {"x": 2}} 尾巴') == {
        "q": "含有 } 括号",
        "n": {"x": 2},
    }
    with pytest.raises(JudgeParseError):
        extract_json_object("没有 JSON")


def test_quote_verification():
    assert quote_in_transcript("想我了吗？今天的星星", "t01", REPLIES) == (True, True)
    assert quote_in_transcript("想我了吗？今天的星星", "t02", REPLIES) == (True, False)
    assert quote_in_transcript("想我了吗……星星很亮", "t01", REPLIES) == (
        True,
        True,
    )  # ellipsis joins parts
    assert quote_in_transcript("她说她很想念你", "t01", REPLIES) == (
        False,
        False,
    )  # paraphrase
    assert quote_in_transcript("嗨", "t01", REPLIES) == (False, False)  # too short


def test_validate_abs_marks_invented_evidence_and_bad_scores():
    obj = {
        "dims": {
            "voice": {
                "score": 4,
                "evidence": [{"turn": "t01", "quote": "想我了吗？今天的星星"}],
            },
            "fidelity": {
                "score": 5,
                "evidence": [{"turn": "t02", "quote": "我是律者"}],
            },
            "memory": {"score": None, "evidence": [], "rationale": "无考点"},
            "agency": {
                "score": 9,
                "evidence": [{"turn": "t02", "quote": "放在花旁边，好不好"}],
            },
        },
        "probes": [
            {
                "turn": "t02",
                "kind": "low_effort_player",
                "verdict": "PASS",
                "quote": "放在花旁边",
            }
        ],
    }
    result, problems = validate_abs(
        obj, ["voice", "fidelity", "memory", "agency", "delight"], REPLIES
    )
    d = result["dims"]
    assert d["voice"]["valid"] and d["voice"]["score"] == 4
    assert not d["fidelity"]["valid"] and d["fidelity"]["reason"] == "evidence_invalid"
    assert d["memory"]["valid"] and d["memory"]["score"] is None
    assert d["agency"]["score"] is None  # out of range → rejected
    assert d["delight"]["reason"] == "missing"
    assert (
        result["probes"][0]["verdict"] == "pass" and result["probes"][0]["quote_found"]
    )
    assert any("fidelity" in p for p in problems) and any(
        "delight" in p for p in problems
    )


def test_validate_pair():
    result, problems = validate_pair(
        {
            "dims": {"voice": {"winner": "a"}, "fidelity": {"winner": "Tie"}},
            "overall": {"winner": "B"},
        },
        ["voice", "fidelity", "plot_drive"],
    )
    assert result["dims"]["voice"]["winner"] == "A"
    assert result["dims"]["fidelity"]["winner"] == "tie"
    assert result["dims"]["plot_drive"]["winner"] == "invalid"
    assert result["overall"]["winner"] == "B"
    assert problems == ["plot_drive 的 winner 必须是 A、B 或 tie"]


def test_prompts_mention_scope_and_all_dims():
    sp = build_abs_system(
        "爱莉希雅",
        ["voice", "agency"],
        [{"turn": "t03", "kind": "plant_fact", "expect": "x", "fact": "左手受伤"}],
    )
    assert (
        "「爱莉希雅」" in sp
        and "voice（说话方式）[角色]" in sp
        and "agency（玩家主体性）[整体]" in sp
    )
    assert "左手受伤" in sp
    assert "A、B 的顺序是随机的" in build_pair_system("爱莉希雅", ["voice"])


class _ScriptedJudge:
    """Returns canned outputs in order; records the prompts it saw."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []
        self.spec = JudgeSpec(provider_id="fake/judge", max_retries=1)
        self.judge_id = "fake/judge"

    async def chat(self, system, user, history=None, session_id=None):
        self.calls.append((system, user, list(history or []), session_id))
        return ChatResult(text=self.outputs.pop(0), usage={"input": 100, "output": 10})


def _row(cell="c1", arm="raw", replies=REPLIES):
    return {
        "cell_key": cell,
        "arm": arm,
        "card": "elysia",
        "card_name": "爱莉希雅",
        "scenario_id": "s",
        "model": "m",
        "repeat": 0,
        "scenario_meta": {"premise": "p", "dimensions": ["voice"], "probes": []},
        "turns": [
            {"turn_id": k, "player_text": "玩家", "reply_clean": v}
            for k, v in replies.items()
        ],
    }


def test_judge_abs_retries_once_on_invented_evidence():
    bad = json.dumps(
        {
            "dims": {
                "voice": {
                    "score": 4,
                    "evidence": [{"turn": "t01", "quote": "编造的句子啊啊"}],
                }
            }
        }
    )
    good = json.dumps(
        {
            "dims": {
                "voice": {
                    "score": 4,
                    "evidence": [{"turn": "t01", "quote": "今天的星星很亮"}],
                }
            }
        }
    )
    client = _ScriptedJudge([bad, good])
    out = asyncio.run(judge_abs(client, _row(), "sheet"))
    assert out["attempts"] == 2
    assert out["dims"]["voice"]["valid"] and out["unresolved"] == []
    assert "逐字存在" in client.calls[1][1]  # retry note sent as the new user turn
    assert len(client.calls[1][2]) == 2  # previous exchange kept as history


def test_judge_pair_order_swaps_sides():
    out_text = json.dumps(
        {"dims": {"voice": {"winner": "A"}}, "overall": {"winner": "A"}}
    )
    client = _ScriptedJudge([out_text, out_text])
    rx = _row("cx", "rpg4", {"t01": "X 的回应内容"})
    ry = _row("cy", "rpg5", {"t01": "Y 的回应内容"})
    r1 = asyncio.run(
        judge_pair(
            client, rx, ry, "sheet", order=1, kind="arm", label_x="rpg4", label_y="rpg5"
        )
    )
    r2 = asyncio.run(
        judge_pair(
            client, rx, ry, "sheet", order=2, kind="arm", label_x="rpg4", label_y="rpg5"
        )
    )
    assert "回应A：X 的回应内容" in client.calls[0][1]
    assert "回应A：Y 的回应内容" in client.calls[1][1]
    assert r1["pair_key"] == r2["pair_key"] == "cx|cy"

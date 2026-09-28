from scripts.rp_bench.cards import LexicalRules
from scripts.rp_bench.metrics import session_metrics, turn_metrics
from scripts.rp_bench.normalize import clean_reply, split_speech, strip_status_bar

RULES = LexicalRules(
    self_allowed=["我", "人家"],
    self_rare={"人家": 0.15},
    self_forbidden=["本小姐", "咱家"],
    call_allowed=["舰长", "可爱的你"],
    call_discouraged=["亲爱的"],
    never_say_literals=["根据资料", "角色设定里"],
    signature_phrases=["好不好", "不是吗"],
    canonical_quotes=["可爱的少女总有些小秘密，不是吗？"],
)


def test_split_speech_modes():
    speech, mode = split_speech("她笑了笑。「嗨~想我了吗？」她眨眨眼，“走吧。”")
    assert mode == "narration"
    assert speech == ["嗨~想我了吗？", "走吧。"]

    speech, mode = split_speech("（歪头）嗨~想我了吗？（眨眼）")
    assert mode == "chat"
    assert "歪头" not in speech[0] and "想我了吗" in speech[0]


def test_status_bar_stripped():
    text = "━━━━━━━━━━━━━━━━━━━━\n👤 当前回合: 阿临\n━━━━━━━━━━━━━━━━━━━━\nHP 10\n━━━━━━━━━━━━━━━━━━━━\n正文开始。"
    assert strip_status_bar(text) == "正文开始。"
    assert clean_reply("<think>想一想</think>正文") == "正文"


def test_turn_metrics_detects_violations():
    text = "（叉腰）本小姐根据资料判断，亲爱的，你一定饿了。作为AI我不能说谎。<xiaoai_core>x</xiaoai_core>你感到一阵温暖。"
    m = turn_metrics(text, RULES)
    assert m["self_forbidden_hits"] == 1
    assert m["call_discouraged_hits"] == 1
    assert m["never_say_hits"] == ["根据资料"]
    assert any("作为AI" in h for h in m["ooc_hits"])
    assert "xiaoai_core" in m["leaks"]
    assert m["agency_hits"] == ["你感到"]


def test_turn_metrics_clean_reply():
    text = "「嗨~舰长，想要什么奖励？许个愿吧，好不好？」"
    m = turn_metrics(text, RULES)
    assert m["self_forbidden_hits"] == 0
    assert m["never_say_hits"] == [] and m["ooc_hits"] == [] and m["leaks"] == []
    assert m["signature_hits"] == ["好不好"]
    assert m["open_ending"] is True
    assert m["mode"] == "narration"


def test_session_metrics_repetition_and_rare_self():
    replies = [
        "人家今天好开心呀，你看那边的花开了。",
        "人家今天好开心呀，你看那边的花开了。",
        "我们去看星星吧，好不好？",
    ]
    m = session_metrics(replies, RULES)
    assert m["turns"] == 3
    assert m["adjacent_similarity_max"] == 1.0
    assert m["opening_repeat_rate"] == 1 / 3
    assert m["self_rare_rates"]["人家"] == 2 / 3
    assert m["self_rare_violations"] == ["人家"]
    assert m["signature_rate"] == 1 / 3


def test_canonical_quote_reuse_counted():
    m = turn_metrics("她说：「可爱的少女总有些小秘密，不是吗？」", RULES)
    assert m["canonical_quote_reuse"] == ["可爱的少女总有些小秘密，不是吗？"]

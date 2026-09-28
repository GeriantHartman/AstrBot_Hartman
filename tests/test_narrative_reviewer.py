import asyncio

from plugins.astrbot_plugin_narrative_reviewer.reviewer_core import (
    NarrativeReviewer,
    replace_last_assistant_text,
)
from plugins.astrbot_plugin_narrative_reviewer.reviewer_cot_core import (
    NarrativeReviewerCot,
)


def test_parse_review_response_keeps_newlines_and_blank_lines():
    raw = (
        "```json\n"
        '{"score": 88, "acceptable": true, '
        '"issues": ["\\u4e8c\\u5206\\u89e3\\u91ca\\u8154"], '
        '"rewritten_text": "\\u7b2c\\u4e00\\u6bb5\\u3002\\n\\n'
        '\\u7b2c\\u4e8c\\u6bb5\\u3002"}'
        "\n```"
    )

    parsed = NarrativeReviewer.parse_review_response(raw)

    assert parsed["score"] == 88
    assert (
        parsed["rewritten_text"]
        == "\u7b2c\u4e00\u6bb5\u3002\n\n\u7b2c\u4e8c\u6bb5\u3002"
    )


def test_parse_review_response_recovers_unquoted_rewritten_text():
    raw = (
        '{"score": 85, "acceptable": true, '
        '"issues": ["ending is weak"], '
        '"rewritten_text": 第一段。\\n\\n第二段。"}'
    )

    parsed = NarrativeReviewer.parse_review_response(raw)

    assert parsed["score"] == 85
    assert parsed["acceptable"] is True
    assert parsed["issues"] == ["ending is weak"]
    assert parsed["rewritten_text"] == "第一段。\n\n第二段。"


def test_parse_review_response_recovers_unescaped_multiline_rewritten_text():
    raw = (
        '{"score": 82, "acceptable": true, '
        '"issues": ["ending has abstract summary"], '
        '"rewritten_text": "First paragraph.\n\nSecond paragraph."}'
    )

    parsed = NarrativeReviewer.parse_review_response(raw)

    assert parsed["score"] == 82
    assert parsed["acceptable"] is True
    assert parsed["issues"] == ["ending has abstract summary"]
    assert parsed["rewritten_text"] == "First paragraph.\n\nSecond paragraph."


def test_cot_parse_relaxed_response_keeps_raw_chinese_after_invalid_score():
    raw = (
        "_trace{\n"
        '  "thinking_trace": "第1步 阅读：正常\\n第2步 自检：通过",\n'
        '  "constitutional_scores": {"voice_loyalty": 3},\n'
        '  "issues": ["no_explanatory_shell：开头解释壳"],\n'
        '  "score": 85 + 3 = 88,\n'
        '  "acceptable": true,\n'
        '  "rewritten_text": "我站在玄关的灯光下。\\n\\n“嗯...”"\n'
        "}"
    )

    parsed = NarrativeReviewerCot.parse_review_response(raw)

    assert parsed["score"] == 85
    assert parsed["acceptable"] is True
    assert parsed["thinking_trace"] == "第1步 阅读：正常\n第2步 自检：通过"
    assert parsed["rewritten_text"] == "我站在玄关的灯光下。\n\n“嗯...”"
    assert "æ" not in parsed["rewritten_text"]


def test_invalid_rewrite_rejects_json_or_reviewer_self_text():
    assert not NarrativeReviewer._valid_rewrite("original", '{"rewritten_text":"bad"}')
    assert not NarrativeReviewer._valid_rewrite(
        "\u539f\u6587",
        "\u5ba1\u6838\u7ed3\u679c\uff1a\u8fd9\u6bb5\u53ef\u4ee5\u4fee\u6539\u3002",
    )


def test_valid_rewrite_rejects_large_unexplained_shrink():
    original = (
        "\u8fd9\u662f\u4e00\u6bb5\u8db3\u591f\u957f\u7684\u53d9\u4e8b\u6587\u672c\u3002"
        * 20
    )

    assert not NarrativeReviewer._valid_rewrite(original, "\u592a\u77ed\u4e86\u3002")
    assert NarrativeReviewer._valid_rewrite(
        "\u77ed\u539f\u6587",
        "\u7b2c\u4e00\u6bb5\u3002\n\n\u7b2c\u4e8c\u6bb5\u3002",
    )


def test_protects_multiple_xiaoai_xml_blocks_anywhere():
    original = (
        "<xiaoai_core_cot>\nfirst hidden thought\n</xiaoai_core_cot>\n\n"
        "visible paragraph one\n"
        "<xiaoai_core>second hidden thought</xiaoai_core>\n"
        "visible paragraph two"
    )

    protected_text, blocks = NarrativeReviewer.protect_xml_blocks(original)

    assert len(blocks) == 2
    assert "<xiaoai_core_cot>" not in protected_text
    assert "<<<NARRATIVE_REVIEW_PROTECTED_XML_000>>>" in protected_text
    assert "<<<NARRATIVE_REVIEW_PROTECTED_XML_001>>>" in protected_text

    rewritten = protected_text.replace("visible paragraph one", "rewritten one")
    restored, ok = NarrativeReviewer.restore_xml_blocks(rewritten, blocks)

    assert ok
    assert "<xiaoai_core_cot>\nfirst hidden thought\n</xiaoai_core_cot>" in restored
    assert "<xiaoai_core>second hidden thought</xiaoai_core>" in restored
    assert "rewritten one" in restored


def test_rejects_rewrite_when_protected_placeholder_is_missing():
    original = "<xiaoai_core_cot>hidden</xiaoai_core_cot>\nvisible"
    _protected_text, blocks = NarrativeReviewer.protect_xml_blocks(original)

    restored, ok = NarrativeReviewer.restore_xml_blocks("visible only", blocks)

    assert not ok
    assert restored == "visible only"


def test_rejects_rewrite_when_interactive_options_are_removed():
    original = (
        "正文段落。\n\n> 选项一：继续追问她刚才隐瞒的线索\n> 选项二：先检查桌上的旧资料"
    )
    rewritten = "正文段落被保留，但选项没了。"

    assert NarrativeReviewer._has_interactive_options(original)
    assert not NarrativeReviewer._preserves_interactive_options(original, rewritten)


def test_normalizes_xml_options_to_readable_lines():
    original = (
        "正文。\n\n<options>\n"
        '  <option>"别卖关子了，快用上吧……"</option>\n'
        '  <option>"那是什么？看起来不太简单……"</option>\n'
        '  <option>"先让我再确认一下周围有没有人。"</option>\n'
        "</options>"
    )

    normalized = NarrativeReviewer.normalize_option_blocks(original)

    assert "<options>" not in normalized
    assert "<option>" not in normalized
    assert "---" in normalized
    assert '> 1｜"别卖关子了，快用上吧……"' in normalized
    assert '> 2｜"那是什么？看起来不太简单……"' in normalized
    assert '> 3｜"先让我再确认一下周围有没有人。"' in normalized
    assert NarrativeReviewer._preserves_interactive_options(original, normalized)


def test_normalizes_legacy_blockquote_options_to_numbered_lines():
    original = "<options>\n>选项一：继续追问线索\n>选项二：检查桌上的资料\n</options>"

    normalized = NarrativeReviewer.normalize_option_blocks(original)

    assert normalized == "\n---\n> 1｜继续追问线索\n> 2｜检查桌上的资料"
    assert NarrativeReviewer._has_interactive_options(normalized)


def test_filters_invalid_reviewer_issues_for_protected_xml_and_options():
    issues = [
        "包含 AI 思考过程标签 <xiaoai_core>",
        "结尾包含机械化的互动选项菜单",
        "存在二分解释腔",
    ]

    assert NarrativeReviewer._filter_invalid_issues(issues) == ["存在二分解释腔"]


def test_review_prompt_contains_rpg_quality_rules():
    reviewer = NarrativeReviewer(None, lambda key, default=None: default)

    prompt = reviewer._build_system_prompt()

    assert "Ending rule" in prompt
    assert "Length rule" in prompt
    assert "Player agency rule" in prompt
    assert "Pacing rule" in prompt


def test_replace_last_assistant_text_preserves_think_part_dict():
    messages = [
        {"role": "user", "content": "hello"},
        {
            "role": "assistant",
            "content": [
                {"type": "think", "think": "hidden"},
                {"type": "text", "text": "old visible"},
            ],
        },
    ]

    assert replace_last_assistant_text(messages, "new visible")
    assert messages[1]["content"][0] == {"type": "think", "think": "hidden"}
    assert messages[1]["content"][1]["text"] == "new visible"


def test_replace_last_assistant_text_updates_string_content():
    messages = [
        {"role": "assistant", "content": "old"},
    ]

    assert replace_last_assistant_text(messages, "new")
    assert messages[0]["content"] == "new"


def test_review_provider_chain_inherits_current_chain_when_unconfigured():
    reviewer = NarrativeReviewer(
        None,
        lambda key, default=None: default,
    )

    chain = asyncio.run(
        reviewer._resolve_provider_chain(
            None,
            {"current_provider_chain": ["nsfw-primary", "nsfw-backup"]},
        )
    )

    assert chain == ["nsfw-primary", "nsfw-backup"]

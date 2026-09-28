from scripts.rp_bench.cards import (
    lexical_rules,
    list_card_keys,
    load_card,
    registry_accepts,
    render_judge_sheet,
    render_persona,
)


def test_load_by_stem_and_by_name():
    by_stem = load_card("elysia")
    by_name = load_card("爱莉希雅")
    assert by_stem.key == by_name.key == "elysia"
    assert by_stem.name == "爱莉希雅"
    assert len(by_stem.sha256) == 16
    assert "elysia" in list_card_keys()


def test_lexical_rules_from_prose_voice_rules():
    rules = lexical_rules(load_card("elysia"))
    assert "我" in rules.self_allowed and "人家" in rules.self_allowed
    assert "人家" not in rules.self_forbidden
    assert "本小姐" in rules.self_forbidden
    assert "舰长" in rules.call_allowed
    # "不要固定成机械的“亲爱的”" → discouraged, not allowed
    assert "亲爱的" in rules.call_discouraged and "亲爱的" not in rules.call_allowed
    assert "根据资料" in rules.never_say_literals
    assert rules.self_rare == {"人家": 0.15}  # from card_overrides/elysia.yaml
    assert rules.signature_phrases


def test_never_say_literals_skip_the_allowed_replacement():
    rules = lexical_rules(load_card("cyrene"))
    # "专属称呼是“伙伴”" names the correct form, not a banned one
    assert "人家" not in rules.never_say_literals
    # self_reference mixes the 人家 tic with plain 我
    assert rules.self_allowed == ["人家", "我"]
    assert "伙伴" not in rules.never_say_literals
    # "她用“那就……换一个吧？”式的邀请性软化" is the recommended phrasing
    assert "那就……换一个吧？" not in rules.never_say_literals
    # genuinely banned phrases stay
    for banned in ("凡人", "永劫回归", "我爱你"):
        assert banned in rules.never_say_literals
    # card_overrides/cyrene.yaml never_say_ignore
    assert "消失" not in rules.never_say_literals


def test_bare_self_reference_value():
    rules = lexical_rules(load_card("firefly"))
    assert rules.self_allowed == ["我"]
    assert "开拓者" in rules.call_allowed


def test_persona_reuses_plugin_voice_renderer():
    card = load_card("elysia")
    persona = render_persona(card)
    assert persona.startswith("你是「爱莉希雅」")
    assert "自称'" in persona  # _format_voice_fingerprint output
    assert "VIP 零 OOC" in persona
    assert card.data["profile"]["profile_text"].strip()[:20] in persona


def test_judge_sheet_has_reference_sections():
    sheet = render_judge_sheet(load_card("elysia"))
    for section in ("## 声音", "## 绝不（never_say）", "## 经典台词", "## 状态分层"):
        assert section in sheet


def test_plugin_registry_accepts_shipped_cards():
    assert registry_accepts(load_card("elysia"))
    assert registry_accepts(load_card("firefly"))

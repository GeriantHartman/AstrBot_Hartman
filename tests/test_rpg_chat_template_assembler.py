import json

from plugins.astrbot_plugin_agentic_RPG.handlers.cache_guard import (
    strip_assistant_internal_scaffolding,
    strip_assistant_internal_scaffolding_from_contexts,
    strip_assistant_reasoning_from_contexts,
)
from plugins.astrbot_plugin_agentic_RPG.handlers.chat_template_assembler import (
    CUSTOM_USER_PROTOCOL_KEY,
    ChatTemplateDataBundle,
    build_narrator_request,
    invalidate_chat_template_cache,
    load_chat_template,
    migrate_legacy_custom_user_protocol,
)


def test_relative_slots_preserve_order_around_chat_history_marker():
    template = {
        "name": "relative-order",
        "prompts": [
            {
                "identifier": "global",
                "role": "system",
                "injection_position": 0,
                "content": "global",
            },
            {
                "identifier": "blank-few-shot",
                "role": "user",
                "injection_position": 0,
                "content": "  \n",
            },
            {
                "identifier": "pre-history-system",
                "role": "system",
                "injection_position": 0,
                "content": "pre-history",
            },
            {
                "identifier": "chat_history",
                "marker": True,
                "injection_position": 0,
                "content": "",
            },
            {
                "identifier": "post-history-system",
                "role": "system",
                "injection_position": 0,
                "content": "post-history",
            },
            {
                "identifier": "depth-system",
                "role": "system",
                "injection_position": 1,
                "injection_depth": 0,
                "content": "depth",
            },
        ],
        "prompt_order": [
            {
                "character_id": 100000,
                "order": [
                    {"identifier": "global", "enabled": True},
                    {"identifier": "blank-few-shot", "enabled": True},
                    {"identifier": "pre-history-system", "enabled": True},
                    {"identifier": "chat_history", "enabled": True},
                    {"identifier": "post-history-system", "enabled": True},
                    {"identifier": "depth-system", "enabled": True},
                ],
            }
        ],
    }

    system_prompt, contexts, _, trace = build_narrator_request(
        template,
        ChatTemplateDataBundle(),
        [
            {"role": "user", "content": "history-user"},
            {"role": "assistant", "content": "history-assistant"},
        ],
        include_trace=True,
    )

    assert system_prompt == "global"
    assert [(message["role"], message["content"]) for message in contexts] == [
        ("user", "[RPG_TPL:blank-few-shot]\n  \n"),
        ("system", "[RPG_TPL:pre-history-system]\npre-history"),
        ("user", "history-user"),
        ("assistant", "history-assistant"),
        ("system", "[RPG_TPL:post-history-system]\npost-history"),
        ("system", "[RPG_TPL:depth-system]\ndepth"),
    ]
    regions = {
        slot["identifier"]: slot.get("relative_region")
        for slot in trace["slots"]
        if slot.get("injection_position") == 0
    }
    assert regions == {
        "global": "system_prompt",
        "blank-few-shot": "before_history",
        "pre-history-system": "before_history",
        "post-history-system": "after_history",
    }


def test_custom_user_protocol_placeholder_is_appended_after_template_slots():
    template = {
        "custom_user_protocol": {
            "enabled": True,
            "content": "protocol",
        },
        "prompts": [],
        "prompt_order": [],
    }

    _, contexts, _ = build_narrator_request(
        template,
        ChatTemplateDataBundle(),
        [{"role": "user", "content": "history-user"}],
    )

    assert contexts[-1]["role"] == "user"
    assert contexts[-1]["content"] == "protocol"
    assert contexts[-1][CUSTOM_USER_PROTOCOL_KEY] == {"enabled": True}


def test_migrate_legacy_custom_user_protocol_removes_uuid_slots(tmp_path):
    template_path = tmp_path / "chat_template.json"
    template = {
        "prompts": [
            {
                "identifier": "custom_1780136979830",
                "role": "user",
                "content": "  \n",
            },
            {
                "identifier": "custom_1780137691112",
                "role": "system",
                "content": "protocol",
            },
            {
                "identifier": "normal",
                "role": "system",
                "content": "normal",
            },
        ],
        "prompt_order": [
            {
                "character_id": 100000,
                "order": [
                    {"identifier": "custom_1780136979830", "enabled": True},
                    {"identifier": "custom_1780137691112", "enabled": True},
                    {"identifier": "normal", "enabled": True},
                ],
            }
        ],
    }
    template_path.write_text(json.dumps(template), encoding="utf-8")

    migrated = migrate_legacy_custom_user_protocol(template_path, template)

    assert migrated["custom_user_protocol"]["enabled"] is True
    assert migrated["custom_user_protocol"]["content"] == "protocol"
    assert [prompt["identifier"] for prompt in migrated["prompts"]] == ["normal"]
    assert [item["identifier"] for item in migrated["prompt_order"][0]["order"]] == [
        "normal"
    ]


def test_nsfw_filter_uses_explicit_flag_instead_of_identifier():
    template = {
        "prompts": [
            {
                "identifier": "nsfw",
                "role": "system",
                "injection_position": 0,
                "content": "information-end",
            },
            {
                "identifier": "actual-nsfw-guide",
                "role": "system",
                "injection_position": 0,
                "nsfw_only": True,
                "content": "actual-nsfw",
            },
        ],
        "prompt_order": [
            {
                "character_id": 100000,
                "order": [
                    {"identifier": "nsfw", "enabled": True},
                    {"identifier": "actual-nsfw-guide", "enabled": True},
                ],
            }
        ],
    }

    system_prompt, _, _ = build_narrator_request(
        template,
        ChatTemplateDataBundle(),
        [],
    )

    assert system_prompt == "information-end"


def test_load_chat_template_accepts_utf8_bom(tmp_path):
    template_path = tmp_path / "chat_template.json"
    template_path.write_text(
        json.dumps({"prompts": [], "prompt_order": []}),
        encoding="utf-8-sig",
    )

    invalidate_chat_template_cache(template_path)
    try:
        assert load_chat_template(template_path) == {
            "prompts": [],
            "prompt_order": [],
        }
    finally:
        invalidate_chat_template_cache(template_path)


def test_strip_assistant_reasoning_parts_from_contexts():
    contexts = [
        {
            "role": "assistant",
            "content": json.dumps(
                [
                    {"type": "think", "think": "hidden", "encrypted": "opaque"},
                    {"type": "text", "text": "visible narrative"},
                ]
            ),
        },
        {
            "role": "assistant",
            "content": json.dumps(
                [{"type": "think", "think": "hidden only", "encrypted": "opaque"}]
            ),
        },
        {"role": "user", "content": "keep me"},
    ]

    stats = strip_assistant_reasoning_from_contexts(contexts)

    assert stats == {"modified": 1, "removed": 1}
    assert contexts == [
        {"role": "assistant", "content": "visible narrative"},
        {"role": "user", "content": "keep me"},
    ]


def test_strip_assistant_internal_scaffolding_from_contexts():
    contexts = [
        {
            "role": "assistant",
            "content": json.dumps(
                [
                    {
                        "type": "text",
                        "text": (
                            "<cot>hidden chain of thought</cot>\n\n"
                            "<xiaoai_core_cot>hidden plan</xiaoai_core_cot>\n\n"
                            "visible narrative\n\n"
                            "<xiaoai_core>hidden review</xiaoai_core>\n\n"
                            "<监督阶段>hidden supervisor note</监督阶段>\n\n"
                            "<supervision>hidden English supervisor note</supervision>"
                        ),
                    }
                ],
                ensure_ascii=False,
            ),
        },
        {"role": "user", "content": "keep me"},
    ]

    stats = strip_assistant_internal_scaffolding_from_contexts(contexts)

    assert stats == {"modified": 1, "removed": 0}
    assert contexts == [
        {"role": "assistant", "content": "visible narrative"},
        {"role": "user", "content": "keep me"},
    ]


def test_strip_assistant_template_marker_keeps_visible_body():
    cleaned, stripped = strip_assistant_internal_scaffolding(
        "[RPG_TPL:director_inner_state]\nVisible RP text."
    )

    assert stripped is True
    assert cleaned == "Visible RP text."

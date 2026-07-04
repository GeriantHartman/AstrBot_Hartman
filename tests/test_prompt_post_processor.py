from astrbot.core.provider.sources.prompt_post_processor import (
    CUSTOM_USER_PROTOCOL_KEY,
    expand_custom_user_protocol,
    merge_adjacent_messages,
    split_leading_system_messages,
)


def test_merge_adjacent_messages_can_limit_merge_to_system_role():
    messages = [
        {"role": "system", "content": "global-a"},
        {"role": "system", "content": "global-b"},
        {"role": "user", "content": "user-a"},
        {"role": "user", "content": "user-b"},
    ]

    assert merge_adjacent_messages(messages, roles={"system"}) == [
        {"role": "system", "content": "global-a\n\nglobal-b"},
        {"role": "user", "content": "user-a"},
        {"role": "user", "content": "user-b"},
    ]


def test_split_leading_system_messages_preserves_mid_history_system_message():
    messages = [
        {"role": "system", "content": "global-a"},
        {"role": "system", "content": "global-b"},
        {"role": "user", "content": "history"},
        {"role": "system", "content": "post-history"},
    ]

    system_prompt, remaining = split_leading_system_messages(messages)

    assert system_prompt == "global-a\n\nglobal-b"
    assert remaining == [
        {"role": "user", "content": "history"},
        {"role": "system", "content": "post-history"},
    ]


def test_expand_custom_user_protocol_renders_openai_prefix():
    messages = [
        {"role": "system", "content": "global"},
        {
            "role": "user",
            "content": "protocol",
            CUSTOM_USER_PROTOCOL_KEY: {
                "openai": {
                    "role": "system",
                    "prepend_user_separator": True,
                    "user_separator": "  \n",
                }
            },
        },
        {"role": "user", "content": "current"},
    ]

    assert expand_custom_user_protocol(messages, provider_family="openai") == [
        {"role": "user", "content": "  \n"},
        {"role": "system", "content": "protocol"},
        {"role": "system", "content": "global"},
        {"role": "user", "content": "current"},
    ]


def test_expand_custom_user_protocol_renders_native_bottom_user():
    messages = [
        {"role": "system", "content": "global"},
        {
            "role": "user",
            "content": "protocol",
            CUSTOM_USER_PROTOCOL_KEY: {
                "native_top_level_system": {
                    "role": "user",
                }
            },
        },
        {"role": "user", "content": "current"},
    ]

    assert expand_custom_user_protocol(
        messages,
        provider_family="native_top_level_system",
    ) == [
        {"role": "system", "content": "global"},
        {"role": "user", "content": "protocol"},
        {"role": "user", "content": "current"},
    ]

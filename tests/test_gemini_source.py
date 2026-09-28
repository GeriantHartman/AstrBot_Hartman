import pytest

from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI
from astrbot.core.provider.sources.prompt_post_processor import CUSTOM_USER_PROTOCOL_KEY


def test_gemini_empty_output_raises_empty_model_output_error():
    llm_response = LLMResponse(role="assistant")

    with pytest.raises(EmptyModelOutputError):
        ProviderGoogleGenAI._ensure_usable_response(
            llm_response,
            response_id="resp_empty",
            finish_reason="STOP",
        )


def test_gemini_reasoning_only_output_is_allowed():
    llm_response = LLMResponse(
        role="assistant",
        reasoning_content="chain of thought placeholder",
    )

    ProviderGoogleGenAI._ensure_usable_response(
        llm_response,
        response_id="resp_reasoning",
        finish_reason="STOP",
    )


def test_gemini_native_request_preserves_mid_history_system_as_user_content():
    provider = object.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}

    system_instruction, conversation = provider._prepare_native_request(
        {
            "messages": [
                {"role": "system", "content": "global-a"},
                {"role": "system", "content": "global-b"},
                {"role": "user", "content": "history-user"},
                {"role": "assistant", "content": "history-assistant"},
                {"role": "system", "content": "post-history"},
                {"role": "user", "content": "current-user"},
            ]
        }
    )

    assert system_instruction == "global-a\n\nglobal-b"
    assert len(conversation) == 3
    assert [part.text for part in conversation[0].parts] == ["history-user"]
    assert [part.text for part in conversation[1].parts] == ["history-assistant"]
    assert [part.text for part in conversation[2].parts] == [
        "post-history",
        "current-user",
    ]


def test_gemini_native_request_appends_custom_user_protocol_before_current_user():
    provider = object.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}

    system_instruction, conversation = provider._prepare_native_request(
        {
            "messages": [
                {"role": "system", "content": "global"},
                {"role": "user", "content": "history"},
                {
                    "role": "user",
                    "content": "protocol",
                    CUSTOM_USER_PROTOCOL_KEY: {},
                },
                {"role": "user", "content": "current"},
            ]
        }
    )

    assert system_instruction == "global"
    assert [part.text for part in conversation[-1].parts] == [
        "history",
        "protocol",
        "current",
    ]

import httpx
import pytest

import astrbot.core.provider.sources.anthropic_source as anthropic_source
import astrbot.core.provider.sources.kimi_code_source as kimi_code_source
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.sources.prompt_post_processor import CUSTOM_USER_PROTOCOL_KEY


class _FakeAsyncAnthropic:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def close(self):
        return None


def test_anthropic_provider_injects_custom_headers_into_http_client(monkeypatch):
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)

    provider = anthropic_source.ProviderAnthropic(
        provider_config={
            "id": "anthropic-test",
            "type": "anthropic_chat_completion",
            "model": "claude-test",
            "key": ["test-key"],
            "custom_headers": {
                "User-Agent": "custom-agent/1.0",
                "X-Test-Header": 123,
            },
        },
        provider_settings={},
    )

    assert provider.custom_headers == {
        "User-Agent": "custom-agent/1.0",
        "X-Test-Header": "123",
    }
    assert isinstance(provider.client.kwargs["http_client"], httpx.AsyncClient)
    assert provider.client.kwargs["http_client"].headers["User-Agent"] == "custom-agent/1.0"
    assert provider.client.kwargs["http_client"].headers["X-Test-Header"] == "123"


def test_kimi_code_provider_sets_defaults_and_preserves_custom_headers(monkeypatch):
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)

    provider = kimi_code_source.ProviderKimiCode(
        provider_config={
            "id": "kimi-code",
            "type": "kimi_code_chat_completion",
            "key": ["test-key"],
            "custom_headers": {"X-Trace-Id": "trace-1"},
        },
        provider_settings={},
    )

    assert provider.base_url == kimi_code_source.KIMI_CODE_API_BASE
    assert provider.get_model() == kimi_code_source.KIMI_CODE_DEFAULT_MODEL
    assert provider.custom_headers == {
        "User-Agent": kimi_code_source.KIMI_CODE_USER_AGENT,
        "X-Trace-Id": "trace-1",
    }
    assert provider.client.kwargs["http_client"].headers["User-Agent"] == (
        kimi_code_source.KIMI_CODE_USER_AGENT
    )
    assert provider.client.kwargs["http_client"].headers["X-Trace-Id"] == "trace-1"


def test_kimi_code_provider_restores_required_user_agent_when_blank(monkeypatch):
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)

    provider = kimi_code_source.ProviderKimiCode(
        provider_config={
            "id": "kimi-code",
            "type": "kimi_code_chat_completion",
            "key": ["test-key"],
            "custom_headers": {"User-Agent": "   "},
        },
        provider_settings={},
    )

    assert provider.custom_headers == {
        "User-Agent": kimi_code_source.KIMI_CODE_USER_AGENT,
    }


def test_anthropic_empty_output_raises_empty_model_output_error():
    llm_response = LLMResponse(role="assistant")

    with pytest.raises(EmptyModelOutputError):
        anthropic_source.ProviderAnthropic._ensure_usable_response(
            llm_response,
            completion_id="msg_empty",
            stop_reason="end_turn",
        )


def test_anthropic_payload_preserves_mid_history_system_as_user_message():
    provider = object.__new__(anthropic_source.ProviderAnthropic)

    system_prompt, messages = provider._prepare_payload(
        [
            {"role": "system", "content": "global-a"},
            {"role": "system", "content": "global-b"},
            {"role": "user", "content": "history-user"},
            {"role": "assistant", "content": "history-assistant"},
            {"role": "system", "content": "post-history"},
            {"role": "user", "content": "current-user"},
        ]
    )

    assert system_prompt == "global-a\n\nglobal-b"
    assert messages == [
        {"role": "user", "content": "history-user"},
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "history-assistant"}],
        },
        {"role": "user", "content": "post-history\n\ncurrent-user"},
    ]


def test_anthropic_payload_appends_custom_user_protocol_before_current_user():
    provider = object.__new__(anthropic_source.ProviderAnthropic)

    system_prompt, messages = provider._prepare_payload(
        [
            {"role": "system", "content": "global"},
            {"role": "user", "content": "history"},
            {
                "role": "user",
                "content": "protocol",
                CUSTOM_USER_PROTOCOL_KEY: {},
            },
            {"role": "user", "content": "current"},
        ]
    )

    assert system_prompt == "global"
    assert messages == [
        {"role": "user", "content": "history\n\nprotocol\n\ncurrent"},
    ]

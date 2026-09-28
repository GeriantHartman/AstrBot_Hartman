import pytest

from astrbot.core.exceptions import LLMTransientError
from plugins.astrbot_plugin_agentic_RPG.handlers.llm_retry import (
    call_with_provider_fallback,
    resolve_provider_chain,
)


@pytest.mark.asyncio
async def test_call_with_provider_fallback_notifies_on_switch():
    notices = []

    async def call(pid: str):
        if pid == "primary":
            raise LLMTransientError("timeout from primary")
        return f"ok:{pid}"

    async def notify(info: dict):
        notices.append(info)

    result = await call_with_provider_fallback(
        provider_chain=["primary", "backup"],
        call_fn=call,
        purpose="router",
        on_provider_fallback=notify,
    )

    assert result == "ok:backup"
    assert notices == [
        {
            "purpose": "router",
            "failed_provider": "primary",
            "fallback_provider": "backup",
            "fallback_index": 1,
            "fallback_count": 1,
            "error_type": "LLMTransientError",
            "error": "timeout from primary",
        }
    ]


@pytest.mark.asyncio
async def test_call_with_provider_fallback_can_notify_first_provider_as_fallback():
    notices = []

    async def call(pid: str):
        return f"ok:{pid}"

    async def notify(info: dict):
        notices.append(info)

    result = await call_with_provider_fallback(
        provider_chain=["backup"],
        call_fn=call,
        purpose="narrative",
        on_provider_fallback=notify,
        initial_failed_provider="primary",
        initial_error=RuntimeError("main pipeline error"),
        first_provider_is_fallback=True,
    )

    assert result == "ok:backup"
    assert notices == [
        {
            "purpose": "narrative",
            "failed_provider": "primary",
            "fallback_provider": "backup",
            "fallback_index": 1,
            "fallback_count": 1,
            "error_type": "RuntimeError",
            "error": "main pipeline error",
        }
    ]


def test_resolve_provider_chain_inherits_fallbacks_when_chain_empty():
    config = {
        "narrative_provider_chain": [],
    }

    chain = resolve_provider_chain(
        lambda key, default=None: config.get(key, default),
        "narrative",
        primary="primary",
        inherited_chain=["primary", "backup-a", "backup-b"],
    )

    assert chain == ["primary", "backup-a", "backup-b"]

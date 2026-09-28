from types import SimpleNamespace

from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI
from plugins.astrbot_plugin_agentic_RPG.handlers.hooks import HookHandler


def test_provider_payload_preview_uses_gemini_native_shape():
    provider = object.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}
    handler = object.__new__(HookHandler)
    handler.ctx = SimpleNamespace(
        context=SimpleNamespace(get_provider_by_id=lambda _: provider)
    )

    preview = handler._build_provider_payload_preview(
        req=SimpleNamespace(
            system_prompt="global",
            contexts=[
                {"role": "user", "content": "history-user"},
                {"role": "system", "content": "post-history"},
            ],
            prompt="current-user",
        ),
        provider_id="gemini-test",
    )

    assert preview["format"] == "gemini_native"
    assert preview["system_instruction"]["content_preview"] == "global"
    assert preview["system_instruction"]["content_chars"] == 6
    assert preview["contents_count"] == 1
    assert "history-user" in preview["contents_preview"]
    assert "post-history" in preview["contents_preview"]
    assert "current-user" in preview["contents_preview"]

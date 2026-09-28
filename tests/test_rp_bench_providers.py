import pytest

import astrbot.api  # noqa: F401  (must precede provider.manager: circular import)
from astrbot.core.provider.manager import ProviderManager
from scripts.rp_bench.providers import (
    ProviderConfigError,
    merge_provider_config,
    model_family,
    resolve_provider_config,
)
from scripts.rp_bench.sandbox import SandboxError, ensure_sandbox_root

SOURCES = [
    {
        "id": "deepseek",
        "type": "openai_chat_completion",
        "provider_type": "chat_completion",
        "api_base": "https://x",
        "key": ["k"],
        "enable": True,
    },
]
PROVIDERS = [
    {
        "id": "deepseek/v4",
        "enable": True,
        "provider_source_id": "deepseek",
        "model": "deepseek-v4-flash",
        "custom_extra_body": {"top_p": 0.9},
    },
    {"id": "off", "enable": False, "provider_source_id": "deepseek", "model": "m"},
    {
        "id": "emb",
        "enable": True,
        "type": "gemini_embedding",
        "provider_type": "embedding",
    },
]
CMD = {"provider": PROVIDERS, "provider_sources": SOURCES}


def test_merge_matches_provider_manager():
    pm = object.__new__(ProviderManager)
    pm.provider_sources_config = SOURCES
    for pc in PROVIDERS:
        assert merge_provider_config(pc, SOURCES) == pm.get_merged_provider_config(pc)


def test_resolve_merges_source_and_extra_body():
    cfg = resolve_provider_config("deepseek/v4", CMD, extra_body={"temperature": 0})
    assert cfg["id"] == "deepseek/v4"
    assert cfg["type"] == "openai_chat_completion" and cfg["api_base"] == "https://x"
    assert cfg["custom_extra_body"] == {"top_p": 0.9, "temperature": 0}
    # the live dict is untouched
    assert PROVIDERS[0]["custom_extra_body"] == {"top_p": 0.9}


def test_resolve_rejects_unknown_disabled_and_non_chat():
    with pytest.raises(ProviderConfigError, match="not found"):
        resolve_provider_config("nope", CMD)
    with pytest.raises(ProviderConfigError, match="disabled"):
        resolve_provider_config("off", CMD)
    with pytest.raises(ProviderConfigError, match="not a chat_completion"):
        resolve_provider_config("emb", CMD)


def test_model_family():
    assert model_family("deepseek/deepseek-v4-flash") == "deepseek"
    assert model_family("专用/gemini-3.1-pro-preview") == "gemini"


def test_sandbox_refuses_late_activation(tmp_path):
    # conftest already imported astrbot.core against the repo root
    with pytest.raises(SandboxError):
        ensure_sandbox_root(tmp_path / "sb")
    assert ensure_sandbox_root(tmp_path / "sb", strict=False) is False

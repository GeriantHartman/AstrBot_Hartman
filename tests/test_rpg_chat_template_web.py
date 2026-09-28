import json

import pytest

from plugins.astrbot_plugin_agentic_RPG.handlers import chat_template_web


@pytest.mark.asyncio
async def test_load_template_raw_accepts_utf8_bom(monkeypatch, tmp_path):
    template_path = tmp_path / "chat_template.json"
    template_path.write_text(
        json.dumps({"prompts": [], "prompt_order": []}),
        encoding="utf-8-sig",
    )
    monkeypatch.setattr(
        chat_template_web,
        "resolve_chat_template_path",
        lambda _: template_path,
    )

    data, status = await chat_template_web._load_template_raw(tmp_path)

    assert status == 200
    assert data == {"prompts": [], "prompt_order": []}

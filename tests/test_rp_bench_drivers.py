"""Driver tests with fake transports: no network, no live AstrBot."""

import asyncio
import json
from pathlib import Path

import pytest

from plugins.astrbot_plugin_agentic_RPG.core.llm_audit_ledger import LLMAuditLedger
from scripts.rp_bench.cards import load_card
from scripts.rp_bench.config import parse_plan
from scripts.rp_bench.drivers.base import SessionAborted
from scripts.rp_bench.drivers.direct import DirectChatDriver
from scripts.rp_bench.drivers.rpg import RpgDriver
from scripts.rp_bench.ledger import LedgerReader, pipeline_of, session_key, webchat_umo
from scripts.rp_bench.matrix import expand
from scripts.rp_bench.providers import ChatResult
from scripts.rp_bench.scenarios import parse_scenario
from scripts.rp_bench.sse import ChatReply


def _scenario(setup=()):
    turns = [{"id": f"t{i:02d}", "text": f"玩家第{i}句"} for i in range(1, 11)]
    return parse_scenario(
        {
            "id": "s",
            "card": "elysia",
            "turns": turns,
            "chat": {"scene_intro": "（开场）"},
            "rpg": {"preset": "new-elysium", "setup_turns": list(setup)},
        }
    )


def _plan(arms):
    return parse_plan(
        {
            "cards": ["elysia"],
            "scenarios": ["scenarios/core/elysia-*.yaml"],
            "arms": arms,
            "models": ["deepseek/v4"],
            "judge": {"provider_id": "j"},
            "open_api": {"ledger_wait_s": 0.3},
        }
    )


def _cell(arm, setup=()):
    return expand([load_card("elysia")], [_scenario(setup)], [arm], ["deepseek/v4"], 1)[
        0
    ]


# ------------------------------------------------------------------ direct


class _FakeProvider:
    def __init__(self):
        self.calls = []

    async def text_chat(self, prompt=None, system_prompt=None, contexts=None, **_):
        self.calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "contexts": list(contexts or []),
            }
        )
        from types import SimpleNamespace

        return SimpleNamespace(completion_text=f"回应{len(self.calls)}", usage=None)

    def get_model(self):
        return "fake-model"


class _FakePool:
    def __init__(self, provider):
        self.provider = provider

    async def get(self, provider_id, **_):
        return self.provider


def test_direct_driver_keeps_history_and_prefixes_intro():
    provider = _FakeProvider()
    row = asyncio.run(DirectChatDriver(_FakePool(provider)).run_session(_cell("raw")))
    assert len(row["turns"]) == 10
    assert provider.calls[0]["prompt"] == "（开场）\n玩家第1句"
    assert provider.calls[0]["system_prompt"].startswith(
        "\n# Persona Instructions\n\n你是「爱莉希雅」"
    )
    assert provider.calls[2]["contexts"][-1] == {
        "role": "assistant",
        "content": "回应2",
    }
    assert (
        row["turns"][0]["player_text"] == "玩家第1句"
    )  # judge sees the canonical line
    assert row["gate"]["passed"] is True


def test_direct_driver_aborts_after_retry_on_error(monkeypatch):
    async def failing(provider, **_):
        return ChatResult(error="boom")

    monkeypatch.setattr("scripts.rp_bench.drivers.direct.provider_chat", failing)
    with pytest.raises(SessionAborted, match="boom"):
        asyncio.run(
            DirectChatDriver(_FakePool(_FakeProvider())).run_session(_cell("raw"))
        )


# --------------------------------------------------------------------- rpg


class _FakeAstrBot:
    """Answers commands like the plugin and writes narrator ledger rows like LLMAuditLedger."""

    def __init__(
        self,
        data_root: Path,
        *,
        card_on_stage=True,
        pipeline_written="5",
        provider_written="deepseek/v4",
    ):
        self.ledger = LLMAuditLedger(
            data_root / "llm_audit",
            enabled_getter=lambda: True,
            max_files_getter=lambda: 200,
        )
        self.card_on_stage = card_on_stage
        self.opening = "爱莉希雅向你眨了眨眼。" if card_on_stage else "星光在四周流动。"
        self.pipeline_written = pipeline_written
        self.provider_written = provider_written
        self.sent = []
        self.n = 0

    def _narrate(self, umo, text):
        self.n += 1
        sr = load_card("elysia").voice["self_reference"]
        npc_block = f"自称'{sr}'" if self.card_on_stage else "无人"
        rec = self.ledger.record_request(
            session_id=umo,
            user_id="u",
            stage="narrator",
            provider_id=self.provider_written,
            request={
                "system_prompt": "sys",
                "contexts": [{"role": "system", "content": npc_block}],
                "prompt": "p",
            },
            audit_view={f"contract_{self.pipeline_written}_0": {}},
        )
        # audit ids have 1-second granularity; make them unique for the test
        audit_id, path = rec
        new_path = path.with_name(f"{audit_id}-{self.n}.json")
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["audit_id"] = f"{audit_id}-{self.n}"
        new_path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        path.unlink()
        self.ledger.record_response(new_path, response_text=text)

    async def chat(
        self, *, username, session_id, message, config_id="", selected_provider=""
    ):
        umo = webchat_umo(username, session_id)
        self.sent.append(message)
        if message.startswith("/rpg start"):
            self._narrate(umo, self.opening)
            return ChatReply(
                plain_parts=[
                    "⚔️ 冒险开始",
                    f"━━━━━━━━━━\n状态\n━━━━━━━━━━\n{self.opening}",
                ],
                ended=True,
            )
        if message.startswith("/rpg pipeline 5"):
            return ChatReply(
                plain_parts=["✅ 已将本 session 切换为 5.0 Router Supervisor。\n..."],
                ended=True,
            )
        if message.startswith("/style close"):
            return ChatReply(plain_parts=["已关闭本 session 的风格注入。"], ended=True)
        text = f"「嗨~」她回答了{message}"
        self._narrate(umo, text)
        return ChatReply(
            plain_parts=[f"━━━━━━━━━━\n状态\n━━━━━━━━━━\n{text}"], ended=True
        )


def _rpg_driver(
    tmp_path,
    fake,
    plugin_set=("astrbot_plugin_agentic_rpg", "astrbot_plugin_style_skills"),
):
    return RpgDriver(
        _plan(["rpg5"]),
        fake,
        "5",
        ledger=LedgerReader(tmp_path),
        plugin_set=list(plugin_set),
    )


def test_rpg_driver_happy_path(tmp_path):
    fake = _FakeAstrBot(tmp_path)
    row = asyncio.run(_rpg_driver(tmp_path, fake).run_session(_cell("rpg5")))
    assert fake.sent[:3] == [
        "/rpg start 旅人 new-elysium",
        "/rpg pipeline 5",
        "/style close",
    ]
    assert row["gate"]["passed"] and row["gate"]["presence_rate"] == 1.0
    assert len(row["turns"]) == 10
    t = row["turns"][0]
    assert t["reply_clean"] == "「嗨~」她回答了玩家第1句"  # ledger text, no status bar
    assert t["pipeline_actual"] == "5" and not t["pipeline_mismatch"]
    assert not t["fallback_used"] and not t["ledger_missing"]


def test_rpg_driver_flags_fallback_and_pipeline_mismatch(tmp_path):
    fake = _FakeAstrBot(tmp_path, pipeline_written="4", provider_written="other/model")
    row = asyncio.run(_rpg_driver(tmp_path, fake).run_session(_cell("rpg5")))
    t = row["turns"][0]
    assert t["pipeline_mismatch"] and t["fallback_used"]


def test_rpg_driver_gate_fails_when_card_absent(tmp_path):
    fake = _FakeAstrBot(tmp_path, card_on_stage=False)
    row = asyncio.run(_rpg_driver(tmp_path, fake).run_session(_cell("rpg5")))
    assert row["gate"]["passed"] is False
    assert row["turns"] == []
    assert len(fake.sent) == 3  # no scored turns were spent


def test_rpg_driver_skips_style_close_when_plugin_not_loaded(tmp_path):
    fake = _FakeAstrBot(tmp_path)
    asyncio.run(
        _rpg_driver(
            tmp_path, fake, plugin_set=["astrbot_plugin_agentic_rpg"]
        ).run_session(_cell("rpg5"))
    )
    assert "/style close" not in fake.sent


def test_ledger_helpers(tmp_path):
    umo = webchat_umo("rp-bench", "s1")
    assert umo == "webchat:FriendMessage:webchat!rp-bench!s1"
    assert session_key(umo) == LLMAuditLedger.session_key(umo)
    assert pipeline_of({"audit_view": {"contract_5_0": {}}}) == "5"
    assert pipeline_of({"audit_view": {"contract_4_0": {}}}) == "4"
    assert pipeline_of({}) == ""
    assert LedgerReader(tmp_path).new_turns(umo, set()) == []

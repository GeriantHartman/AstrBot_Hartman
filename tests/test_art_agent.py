"""Single-agent Art integration tests with the real AstrBot runner."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from astrbot.core.astr_agent_context import AgentContextWrapper, AstrAgentContext
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import LLMResponse, ProviderRequest, ProviderType
from astrbot.core.star.context import Context
from plugins.astrbot_plugin_art.core.assets import ArtAssets
from plugins.astrbot_plugin_art.core.audit_ledger import LLMAuditLedger
from plugins.astrbot_plugin_art.core.cards import CharacterCardManager
from plugins.astrbot_plugin_art.core.db import ArtDatabase, safe_session_id
from plugins.astrbot_plugin_art.core.session import SessionStore
from plugins.astrbot_plugin_art.core.state import ArtStateManager
from plugins.astrbot_plugin_art.core.users import UserProfiles
from plugins.astrbot_plugin_art.layers.agent import run_art_agent
from plugins.astrbot_plugin_art.layers.assemble import (
    dynamic_context,
)
from plugins.astrbot_plugin_art.main import ArtPlugin
from plugins.astrbot_plugin_art.tools.agent import ArtResources


class Conversations:
    """Small persistent-like conversation service returning fresh objects."""

    def __init__(self):
        self.current = {}
        self.rows = {}

    async def new_conversation(self, sid):
        cid = f"conversation-{len(self.rows)}"
        self.current[sid] = cid
        self.rows[cid] = SimpleNamespace(cid=cid, history="[]")
        return cid

    async def get_curr_conversation_id(self, sid):
        return self.current.get(sid)

    async def get_conversation(self, sid, cid, create_if_not_exists=False):
        return copy.deepcopy(self.rows.get(cid))

    async def update_conversation(self, sid, cid, *, history, token_usage=None):
        self.rows[cid].history = json.dumps(history, ensure_ascii=False)


class Event(AstrMessageEvent):
    """Trusted origin and lifecycle methods used by the real runner."""

    def __init__(
        self, sid="discord:FriendMessage:one", text="抱抱我", platform="discord"
    ):
        self.unified_msg_origin = sid if ":" in sid else "discord:FriendMessage:" + sid
        self.message_str = text
        self.platform = platform
        self.extra = {}
        self.stopped = False
        self.sent = []

    def get_extra(self, key, default=None):
        return self.extra.get(key, default)

    def set_extra(self, key, value):
        self.extra[key] = value

    def get_sender_id(self):
        return "player"

    def get_sender_name(self):
        return "Player"

    def get_platform_name(self):
        return self.platform

    def is_stopped(self):
        return self.stopped

    def stop_event(self):
        self.stopped = True

    def plain_result(self, text):
        return text

    def request_llm(self, **kwargs):
        return ProviderRequest(**kwargs)

    async def send(self, chain):
        self.sent.append(chain)


@pytest_asyncio.fixture
async def agent_env(tmp_path):
    assets = ArtAssets(
        Path("plugins/astrbot_plugin_art/presets"),
        Path("plugins/astrbot_plugin_art/prompts"),
    )
    db = ArtDatabase(tmp_path)
    cards = CharacterCardManager(tmp_path / "cards")
    cards._canonical_cache = {
        name: {
            "name": "Luna",
            "aliases": ["Moon"],
            "profile": {},
            "voice": {},
            "interaction_guidelines": {},
        }
        for name in ("luna", "moon")
    }
    state = ArtStateManager(db, cards, assets)
    conversations = Conversations()
    store = SessionStore(state, conversations)
    event = Event()
    await conversations.new_conversation(event.unified_msg_origin)
    await state.init_session(event.unified_msg_origin)
    await store.initialize(event.unified_msg_origin)
    provider = SimpleNamespace(
        provider_config={"id": "primary", "max_context_tokens": 0},
        meta=lambda: SimpleNamespace(
            id="primary", model="test-model", provider_type=ProviderType.CHAT_COMPLETION
        ),
        get_model=lambda: "test-model",
        text_chat=AsyncMock(
            return_value=LLMResponse(role="assistant", completion_text="Luna抱住你。")
        ),
    )
    context = Context.__new__(Context)
    context.conversation_manager = conversations
    context.get_provider_by_id = lambda _: provider
    context.get_using_provider = lambda _: provider
    context.get_config = lambda **_: {
        "agent_runner": {"config": {"misc": {"max_steps": 5}}}
    }
    plugin = ArtPlugin.__new__(ArtPlugin)
    plugin.context = context
    plugin.db, plugin.card_mgr, plugin.assets, plugin.state = db, cards, assets, state
    plugin.sessions = store
    plugin._data_root = tmp_path
    plugin._config = {"user_reviewer_provider": ""}
    plugin.audit_ledger = LLMAuditLedger(
        tmp_path / "llm_audit",
        enabled_getter=lambda: True,
        max_files_getter=lambda: 200,
    )
    plugin.user_profiles = UserProfiles(
        tmp_path / "users", context, assets, plugin._config, plugin.audit_ledger
    )
    yield SimpleNamespace(
        plugin=plugin,
        store=store,
        state=state,
        db=db,
        cards=cards,
        conversations=conversations,
        event=event,
        provider=provider,
    )
    await plugin.user_profiles.close()
    await db.close_all()


@pytest.mark.asyncio
async def test_one_primary_call_and_final_only_history(agent_env):
    env = agent_env
    env.provider.text_chat.return_value = LLMResponse(
        role="assistant",
        completion_text="Luna抱住你。",
        reasoning_content="provider reasoning",
    )
    reply, thinking = await run_art_agent(
        env.plugin, env.event, ProviderRequest(prompt="抱抱我", system_prompt="Persona")
    )
    assert reply == "Luna抱住你。"
    assert thinking == "provider reasoning"
    assert env.provider.text_chat.await_count == 1
    history = json.loads(
        (await env.plugin._ensure_conversation(env.event.unified_msg_origin)).history
    )
    assert history == [
        {"role": "user", "content": "抱抱我"},
        {"role": "assistant", "content": reply},
    ]
    audit = next((env.plugin._data_root / "llm_audit").rglob("*.json"))
    doc = json.loads(audit.read_text(encoding="utf-8"))
    assert doc["stage"] == "agent"
    assert doc["response"]["meta"]["committed"]
    assert doc["response"]["meta"]["reasoning"] == thinking
    assert "恋人" in doc["request"]["system_prompt"]
    assert "导演笔记" not in json.dumps(doc["request"]["contexts"], ensure_ascii=False)


@pytest.mark.asyncio
async def test_real_runner_writes_memory_then_responds(agent_env):
    env = agent_env
    env.provider.text_chat.side_effect = [
        LLMResponse(
            role="assistant",
            completion_text="Internal tool briefing",
            tools_call_name=["art_write"],
            tools_call_ids=["call1"],
            tools_call_args=[
                {
                    "operations": [
                        {
                            "resource": "memories",
                            "action": "create",
                            "data": {"summary": "一起在窗边听雨。"},
                        }
                    ]
                }
            ],
        ),
        LLMResponse(role="assistant", completion_text="Luna把热茶递给你。"),
    ]
    reply, _ = await run_art_agent(
        env.plugin, env.event, ProviderRequest(prompt="一起听雨")
    )
    assert env.provider.text_chat.await_count == 2
    assert "Internal tool briefing" not in reply
    assert (await env.db.search_memories(env.event.unified_msg_origin, "听雨"))[0][
        "summary"
    ] == "一起在窗边听雨。"
    history = json.loads(
        (await env.plugin._ensure_conversation(env.event.unified_msg_origin)).history
    )
    assert {item["role"] for item in history} == {"user", "assistant"}
    assert "Internal tool briefing" not in json.dumps(history)


@pytest.mark.asyncio
async def test_private_assets_aliases_and_collision_isolation(agent_env):
    env = agent_env
    sid = env.event.unified_msg_origin
    assert safe_session_id("a:b") != safe_session_id("a_b")
    first, _, path = env.cards.resolve_card("Moon", sid, private=True)
    other, _, other_path = env.cards.resolve_card("Luna", sid, private=True)
    assert path == other_path and first == other
    resources = ArtResources(env.store, sid, "t", "")
    await resources.write(
        [
            {
                "resource": "character",
                "action": "update",
                "id": "Moon",
                "data": {"relationship_to_player": "恋人，同居中"},
            },
            {
                "resource": "world",
                "action": "update",
                "data": {"world_setting": "私人海边世界"},
            },
        ]
    )
    assert env.cards._canonical_cache["luna"].get("relationship_to_player") is None
    assert (
        env.cards.resolve_card("Luna", sid, private=True)[0]["relationship_to_player"]
        == "恋人，同居中"
    )
    second_sid = "other-session"
    await env.state.init_session(second_sid)
    assert (
        env.cards.resolve_card("Luna", second_sid, private=True)[0].get(
            "relationship_to_player"
        )
        is None
    )
    assert (
        env.state.get_session_preset(second_sid, "default")["world_setting"]
        != "私人海边世界"
    )
    assert env.state.assets.presets.get("default")["world_setting"] != "私人海边世界"
    await env.state.cast_character(sid, "Moon")
    await env.state.cast_character(sid, "Luna")
    assert (
        len(
            [
                row
                for row in await env.db.get_present_characters(sid)
                if row["character_name"] == "Luna"
            ]
        )
        == 1
    )
    await env.state.cast_character(sid, "Moon", "leave")
    assert all(
        row["character_name"] != "Luna"
        for row in await env.db.get_present_characters(sid)
    )


@pytest.mark.asyncio
async def test_complete_rewind_and_rejected_count_do_not_partially_change_state(
    agent_env,
):
    env = agent_env
    sid = env.event.unified_msg_origin
    baseline = await env.store.snapshot(sid)
    conv = await env.plugin._ensure_conversation(sid)
    await env.store.begin(sid, "one", "去海边", conv)
    resources = ArtResources(env.store, sid, "one", "去海边")
    await env.state.change_scene(sid, "海边")
    await resources.write(
        [
            {
                "resource": "character",
                "action": "update",
                "id": "Luna",
                "data": {"voice": {"tone": "轻快"}},
            },
            {
                "resource": "world",
                "action": "update",
                "data": {"world_setting": "私有世界"},
            },
            {
                "resource": "scripts",
                "action": "create",
                "data": {"scope": "mid", "title": "晚餐", "content": "准备晚餐"},
            },
            {"resource": "memories", "action": "create", "data": {"summary": "在海边"}},
            {
                "resource": "ledger",
                "action": "create",
                "data": {"category": "gift", "key": "贝壳", "value": "小贝壳"},
            },
        ]
    )
    await env.store.commit(
        sid,
        "one",
        "海边正文",
        [
            {"role": "user", "content": "去海边"},
            {"role": "assistant", "content": "海边正文"},
        ],
    )
    await env.store.begin(sid, "forget", "", await env.plugin._ensure_conversation(sid))
    changed = await env.store.snapshot(sid)
    with pytest.raises(ValueError):
        await env.store.rewind(sid, 2, "forget")
    assert await env.store.snapshot(sid) == changed
    result = await env.store.rewind(sid, 1, "forget")
    assert await env.store.snapshot(sid) == baseline
    await env.store.commit(sid, "forget", "", result["history"], forgotten=True)
    assert await env.store.turns(sid) == []
    assert (await env.store.turns(sid, active_only=False))[0]["status"] == "revoked"


@pytest.mark.asyncio
async def test_recovery_after_restart_and_history_write_failure(agent_env):
    env = agent_env
    sid = env.event.unified_msg_origin
    baseline = await env.store.snapshot(sid)
    await env.store.begin(
        sid, "unfinished", "hi", await env.plugin._ensure_conversation(sid)
    )
    await env.db.update_session_fields(sid, relationship_premise="wrong")
    await env.state.change_scene(sid, "wrong")
    await env.db.close_all()
    restarted = SessionStore(env.state, env.conversations)
    await restarted.recover(sid)
    assert await restarted.snapshot(sid) == baseline
    original = env.conversations.update_conversation
    fail_once = AsyncMock(side_effect=[RuntimeError("history write failed"), None])

    async def updating(*args, **kwargs):
        await fail_once(*args, **kwargs)
        await original(*args, **kwargs)

    env.conversations.update_conversation = updating
    with pytest.raises(RuntimeError, match="history write failed"):
        await run_art_agent(env.plugin, env.event, ProviderRequest(prompt="hi"))
    assert await env.store.snapshot(sid) == baseline
    assert all(
        turn["status"] == "failed"
        for turn in await env.store.turns(sid, active_only=False)
    )


@pytest.mark.asyncio
async def test_failed_retry_restores_original_round_and_success_revokes_it(agent_env):
    env = agent_env
    sid = env.event.unified_msg_origin
    await run_art_agent(env.plugin, env.event, ProviderRequest(prompt="抱抱我"))
    before = await env.store.snapshot(sid)
    original_history = (await env.plugin._ensure_conversation(sid)).history
    rewind = LLMResponse(
        role="assistant",
        tools_call_name=["art_rewind"],
        tools_call_args=[{"count": 1}],
        tools_call_ids=["rewind"],
    )
    env.provider.text_chat.side_effect = [
        rewind,
        LLMResponse(role="assistant", completion_text=""),
    ]
    with pytest.raises(ValueError):
        await run_art_agent(
            env.plugin, env.event, ProviderRequest(prompt="重新回复，改在屋内")
        )
    assert await env.store.snapshot(sid) == before
    assert (await env.plugin._ensure_conversation(sid)).history == original_history
    assert len(await env.store.turns(sid)) == 1
    env.provider.text_chat.side_effect = [
        rewind,
        LLMResponse(role="assistant", completion_text="新的拥抱正文"),
    ]
    await run_art_agent(
        env.plugin, env.event, ProviderRequest(prompt="重新回复，改在屋内")
    )
    turns = await env.store.turns(sid)
    assert len(turns) == 1 and turns[0]["reply"] == "新的拥抱正文"
    history = (await env.plugin._ensure_conversation(sid)).history
    assert "Luna抱住你" not in history
    assert "抱抱我" in history and "改在屋内" in history


@pytest.mark.asyncio
async def test_batch_failure_provenance_and_resource_scope(agent_env):
    env = agent_env
    sid = env.event.unified_msg_origin
    resources = ArtResources(env.store, sid, "current", "我答应陪你去看海")
    baseline = await env.store.snapshot(sid)
    with pytest.raises(ValueError):
        await resources.write(
            [
                {
                    "resource": "session",
                    "action": "update",
                    "data": {"relationship_premise": "changed"},
                },
                {
                    "resource": "ledger",
                    "action": "create",
                    "data": {"category": "promise", "key": "bad", "value": "invented"},
                },
            ]
        )
    assert await env.store.snapshot(sid) == baseline
    await resources.write(
        [
            {
                "resource": "ledger",
                "action": "create",
                "data": {
                    "category": "promise",
                    "key": "p",
                    "value": "去看海",
                    "source_turn_id": "current",
                    "player_quote": "陪你去看海",
                },
            }
        ]
    )
    assert (await env.db.get_ledger_entries(sid))[0]["confirmed_by_player"] == 1
    with pytest.raises(ValueError):
        await resources.write(
            [{"resource": "session", "action": "update", "data": {"claimed": 0}}]
        )
    tool = resources.toolset().get_tool("art_read")
    context = AgentContextWrapper(
        context=AstrAgentContext(context=env.plugin.context, event=Event("other"))
    )
    assert json.loads(await tool.call(context, resource="session"))["ok"] is False


@pytest.mark.asyncio
async def test_full_history_pagination_and_no_random_redraw(agent_env):
    env = agent_env
    sid = env.event.unified_msg_origin
    scene_before = await env.db.get_current_scene(sid)
    for index in range(25):
        await run_art_agent(
            env.plugin, env.event, ProviderRequest(prompt=f"user {index}")
        )
    resources = ArtResources(env.store, sid, "read", "")
    page = await resources.read("history", cursor=0, limit=10)
    assert len(page["items"]) == 10 and page["next_cursor"] == 10
    assert page["items"][0]["data"]["player_input"] == "user 0"
    assert len(env.provider.text_chat.call_args.kwargs["contexts"]) <= 45
    assert await env.db.get_current_scene(sid) == scene_before
    dynamic = await dynamic_context(env.state, sid, "read")
    assert "code_random" in dynamic


@pytest.mark.asyncio
async def test_cancelled_round_is_restored_and_does_not_fall_through(agent_env):
    import asyncio

    env = agent_env
    sid = env.event.unified_msg_origin
    before = await env.store.snapshot(sid)
    env.provider.text_chat.side_effect = asyncio.CancelledError()
    await env.plugin.on_art_llm_request(env.event, ProviderRequest(prompt="hi"))
    assert env.event.stopped
    assert await env.store.snapshot(sid) == before
    assert await env.store.turns(sid) == []


@pytest.mark.asyncio
async def test_commands_reset_forget_legacy_and_non_art(agent_env):
    env = agent_env
    sid = env.event.unified_msg_origin
    await run_art_agent(env.plugin, env.event, ProviderRequest(prompt="hi"))
    results = [item async for item in env.plugin.art_forget(env.event, 1)]
    assert "完整撤回" in results[0]
    assert await env.store.turns(sid) == []
    old_cid = await env.conversations.get_curr_conversation_id(sid)
    results = [item async for item in env.plugin.art_reset(env.event)]
    assert "空对话" in results[0]
    assert await env.conversations.get_curr_conversation_id(sid) != old_cid
    assert (await env.plugin._ensure_conversation(sid)).history == "[]"
    assert await env.db.get_session(sid) is None
    legacy_event = Event("legacy")
    await env.db.upsert_session(
        legacy_event.unified_msg_origin, relationship_premise="old"
    )
    before = await env.store.snapshot(legacy_event.unified_msg_origin)
    await env.plugin.on_art_llm_request(legacy_event, ProviderRequest(prompt="hi"))
    assert legacy_event.stopped and "旧版" in legacy_event.sent[0].get_plain_text()
    assert await env.store.snapshot(legacy_event.unified_msg_origin) == before
    ordinary = Event("ordinary")
    await env.plugin.on_art_llm_request(ordinary, ProviderRequest(prompt="hi"))
    assert not ordinary.stopped and ordinary.sent == []


@pytest.mark.asyncio
async def test_discord_folded_reasoning_preserves_all_text(agent_env):
    env = agent_env
    thought = "reasoning || @everyone `code` \\" * 250
    env.provider.text_chat.return_value = LLMResponse(
        role="assistant", completion_text="正文", reasoning_content=thought
    )
    await env.plugin.on_art_llm_request(env.event, ProviderRequest(prompt="hi"))
    assert env.event.sent[0].get_plain_text() == "正文"
    folded = env.event.sent[1:]
    assert all(chain.type == "art_reasoning" for chain in folded)
    assert all(len(chain.get_plain_text()) <= 2000 for chain in folded)
    joined = "".join(chain.get_plain_text()[5:-2] for chain in folded)
    assert joined == thought.replace("\\", "\\\\").replace("|", "\\|").replace(
        "`", "\\`"
    )
    assert all(
        chain.get_plain_text().startswith("思考\n||")
        and chain.get_plain_text().endswith("||")
        for chain in folded
    )


@pytest.mark.asyncio
async def test_forget_waits_for_the_same_core_lock(agent_env):
    import asyncio

    from astrbot.core.utils.session_lock import session_lock_manager

    env = agent_env
    started, release = asyncio.Event(), asyncio.Event()

    async def provider_call(**kwargs):
        started.set()
        await release.wait()
        return LLMResponse(role="assistant", completion_text="A completed round")

    env.provider.text_chat.side_effect = provider_call

    async def core_request():
        async with session_lock_manager.acquire_lock(env.event.unified_msg_origin):
            await env.plugin.on_art_llm_request(env.event, ProviderRequest(prompt="hi"))

    request = asyncio.create_task(core_request())
    await started.wait()

    async def forget():
        return [
            result
            async for result in env.plugin.art_forget(
                Event(env.event.unified_msg_origin), 1
            )
        ]

    withdrawing = asyncio.create_task(forget())
    await asyncio.sleep(0)
    assert not withdrawing.done()
    release.set()
    await request
    assert "完整撤回" in (await withdrawing)[0]
    assert await env.store.turns(env.event.unified_msg_origin) == []


@pytest.mark.asyncio
async def test_audit_failure_and_disabled_ledger_do_not_disable_checkpoints(agent_env):
    env = agent_env
    env.plugin.audit_ledger.record_request = lambda **kwargs: (_ for _ in ()).throw(
        OSError("audit unavailable")
    )
    await run_art_agent(env.plugin, env.event, ProviderRequest(prompt="hi"))
    assert len(await env.store.turns(env.event.unified_msg_origin)) == 1
    env.plugin.audit_ledger = LLMAuditLedger(
        env.plugin._data_root / "disabled-audit",
        enabled_getter=lambda: False,
        max_files_getter=lambda: 0,
    )
    await run_art_agent(env.plugin, env.event, ProviderRequest(prompt="hi again"))
    assert len(await env.store.turns(env.event.unified_msg_origin)) == 2
    assert not (env.plugin._data_root / "disabled-audit").exists()


@pytest.mark.asyncio
async def test_rpg_claim_checker_recognizes_new_and_legacy_paths(
    agent_env, monkeypatch
):
    from plugins.astrbot_plugin_agentic_RPG.handlers._base import BaseHandler

    env = agent_env
    root = env.plugin._data_root / "plugin_data" / "astrbot_plugin_art"
    db = ArtDatabase(root)
    sid = "discord:FriendMessage:claim-test"
    await db.upsert_session(sid, claimed=1)
    monkeypatch.setattr(
        "astrbot.core.utils.astrbot_path.get_astrbot_data_path",
        lambda: str(env.plugin._data_root),
    )
    handler = BaseHandler.__new__(BaseHandler)
    assert handler._is_art_claimed(sid)
    assert not handler._is_art_claimed("discord:FriendMessage:different")
    hashed = db.get_db_path(sid)
    await db.close_all()
    legacy = hashed.parent / "session_discord_FriendMessage_claim-test.db"
    hashed.replace(legacy)
    assert handler._is_art_claimed(sid)
    assert db.get_db_path(sid) == legacy


@pytest.mark.asyncio
async def test_start_and_preset_commands(agent_env):
    env = agent_env
    event = Event(env.event.unified_msg_origin)
    listed = [result async for result in env.plugin.art_preset(event)]
    assert "default" in listed[0]
    current = [result async for result in env.plugin.art_preset(event, "current")]
    assert "当前世界观" in current[0]
    await env.db.upsert_session("discord:FriendMessage:old-preset", claimed=1)
    legacy = Event("discord:FriendMessage:old-preset")
    before = await env.store.snapshot(legacy.unified_msg_origin)
    assert [result async for result in env.plugin.art_preset(legacy, "current")]
    assert await env.store.snapshot(legacy.unified_msg_origin) == before
    _ = [result async for result in env.plugin.art_reset(event)]
    results = [result async for result in env.plugin.art_start(event, "星穹铁道")]
    assert len(results) == 2
    assert isinstance(results[1], ProviderRequest)
    assert results[1].conversation is not None
    assert (await env.db.get_session(event.unified_msg_origin))[
        "relationship_premise"
    ] == "恋人"
    cid = await env.conversations.get_curr_conversation_id(event.unified_msg_origin)
    assert env.conversations.rows[cid].history == "[]"


@pytest.mark.asyncio
async def test_failed_context_refresh_rolls_back_the_tool(agent_env, monkeypatch):
    from astrbot.core.agent.message import Message

    env = agent_env
    sid = env.event.unified_msg_origin
    await env.store.begin(
        sid, "pending", "hi", await env.plugin._ensure_conversation(sid)
    )
    resources = ArtResources(env.store, sid, "pending", "hi")
    context = AgentContextWrapper(
        context=AstrAgentContext(context=env.plugin.context, event=env.event)
    )
    context.messages = [
        Message.model_validate(
            {
                "role": "system",
                "content": "【当前会话权威状态】dynamic",
                "_no_save": True,
            }
        )
    ]
    context.messages[0]._no_save = True
    before = await env.store.snapshot(sid)
    monkeypatch.setattr(
        "plugins.astrbot_plugin_art.layers.assemble.dynamic_context",
        AsyncMock(side_effect=RuntimeError("refresh failed")),
    )
    tool = resources.toolset().get_tool("art_write")
    result = json.loads(
        await tool.call(
            context,
            operations=[
                {
                    "resource": "session",
                    "action": "update",
                    "data": {"relationship_premise": "new premise"},
                }
            ],
        )
    )
    assert not result["ok"]
    assert await env.store.snapshot(sid) == before


@pytest.mark.asyncio
async def test_memory_keyword_arrays_and_day_atmosphere(agent_env):
    env = agent_env
    sid = env.event.unified_msg_origin
    resources = ArtResources(env.store, sid, "current", "hi")
    await resources.write(
        [
            {
                "resource": "memories",
                "action": "create",
                "data": {"summary": "clear soup", "keywords": ["soup", "dinner"]},
            }
        ]
    )
    assert (await env.db.search_memories(sid, "soup"))[0]["keywords"] == "soup, dinner"
    world = env.state.get_session_preset(sid, "default")
    await resources.write(
        [
            {
                "resource": "world",
                "action": "update",
                "id": world["name"],
                "data": {"daily_tones": ["new day atmosphere"]},
            },
            {"resource": "session", "action": "update", "data": {"current_day": 2}},
        ]
    )
    assert (await env.db.get_session(sid))["daily_tone"] == "new day atmosphere"


@pytest.mark.asyncio
async def test_rewind_history_query_does_not_reintroduce_withdrawn_reply(agent_env):
    env = agent_env
    await run_art_agent(env.plugin, env.event, ProviderRequest(prompt="original"))
    env.provider.text_chat.side_effect = [
        LLMResponse(
            role="assistant",
            tools_call_name=["art_rewind"],
            tools_call_ids=["rewind"],
            tools_call_args=[{"count": 1}],
        ),
        LLMResponse(
            role="assistant",
            tools_call_name=["art_read"],
            tools_call_ids=["read"],
            tools_call_args=[{"resource": "history"}],
        ),
        LLMResponse(role="assistant", completion_text="replacement"),
    ]
    await run_art_agent(env.plugin, env.event, ProviderRequest(prompt="redo"))
    documents = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (env.plugin._data_root / "llm_audit").rglob("*.json")
    ]
    redo = next(doc for doc in documents if doc["request"]["prompt"] == "redo")
    read = next(
        call
        for call in redo["response"]["meta"]["tool_trace"]
        if call["tool"] == "art_read"
    )
    assert read["data"]["items"] == []

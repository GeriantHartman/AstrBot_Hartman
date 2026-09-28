"""Unit test suite for astrbot_plugin_art."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from plugins.astrbot_plugin_art.core.cards import (
    CharacterCardManager,
)
from plugins.astrbot_plugin_art.core.claim import (
    claim_session_for_art,
    is_art_claimed,
    release_session_claim,
)
from plugins.astrbot_plugin_art.core.db import ArtDatabase
from plugins.astrbot_plugin_art.core.state import ArtStateManager
from plugins.astrbot_plugin_art.core.variance import (
    roll_action_outcome,
    roll_daily_tone,
    roll_midterm_pacing,
    roll_scene_card,
)
from plugins.astrbot_plugin_art.layers.assemble import (
    assemble_actor_request,
    get_writing_core_prompt,
)
from plugins.astrbot_plugin_art.layers.scribe import run_scribe
from plugins.astrbot_plugin_art.tools.cast import execute_cast
from plugins.astrbot_plugin_art.tools.character import execute_fix_character
from plugins.astrbot_plugin_art.tools.recall import execute_recall
from plugins.astrbot_plugin_art.tools.scene import execute_change_scene


@pytest.fixture
def tmp_art_env():
    """Sets up a temporary directory environment for art tests."""
    temp_dir = Path(tempfile.mkdtemp(prefix="test_art_"))
    presets_dir = (
        Path(__file__).resolve().parent.parent
        / "plugins"
        / "astrbot_plugin_art"
        / "presets"
    )
    db = ArtDatabase(temp_dir)
    card_mgr = CharacterCardManager(cards_root=temp_dir / "cards")
    state = ArtStateManager(db, card_mgr, presets_dir)

    yield {
        "temp_dir": temp_dir,
        "db": db,
        "card_mgr": card_mgr,
        "state": state,
    }

    # Teardown
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_art_database_operations(tmp_art_env):
    db: ArtDatabase = tmp_art_env["db"]
    sid = "test-session-1"

    # 1. Session operations
    await db.upsert_session(
        sid,
        claimed=1,
        nsfw=0,
        preset="default",
        relationship_premise="恋人，同居中",
        player_name="星",
        daily_tone="精神很好",
    )
    sess = await db.get_session(sid)
    assert sess is not None
    assert sess["claimed"] == 1
    assert sess["player_name"] == "星"
    assert sess["relationship_premise"] == "恋人，同居中"

    await db.update_session_fields(sid, daily_tone="有点累")
    sess = await db.get_session(sid)
    assert sess["daily_tone"] == "有点累"

    # 2. Scenes operations
    scene_id1 = await db.create_scene(sid, "咖啡馆", "午后", ["流萤"], "雨天")
    assert scene_id1 > 0
    curr_scene = await db.get_current_scene(sid)
    assert curr_scene["location"] == "咖啡馆"
    assert curr_scene["present_characters"] == ["流萤"]

    scene_id2 = await db.create_scene(sid, "公园", "黄昏", ["流萤", "星"], "晴朗")
    curr_scene2 = await db.get_current_scene(sid)
    assert curr_scene2["id"] == scene_id2
    assert curr_scene2["location"] == "公园"

    # Check all scenes
    all_scenes = await db.get_all_scenes(sid)
    assert len(all_scenes) == 2

    # 3. Cast operations
    await db.upsert_cast(sid, "流萤", card_key="canonical", is_present=1)
    cast_list = await db.get_cast(sid)
    assert len(cast_list) == 1
    assert cast_list[0]["character_name"] == "流萤"

    await db.set_character_presence(sid, "流萤", 0)
    present = await db.get_present_characters(sid)
    assert len(present) == 0

    # 4. Scripts operations
    script_id = await db.add_script(sid, "mid", "准备生日", "她在偷偷给你准备生日礼物")
    active_mids = await db.get_active_scripts(sid, scope="mid")
    assert len(active_mids) == 1
    assert active_mids[0]["id"] == script_id

    # Fade count
    f1 = await db.increment_script_fade(sid, script_id)
    assert f1 == 1
    f2 = await db.increment_script_fade(sid, script_id)
    assert f2 == 2
    # Status should now be faded
    active_mids2 = await db.get_active_scripts(sid, scope="mid")
    assert len(active_mids2) == 0

    # 5. Ledger operations
    await db.add_ledger_entry(
        sid, "promise", "承诺", "我答应陪你去看花火", confirmed_by_player=1
    )
    await db.add_ledger_entry(sid, "gift", "礼物", "定制发卡", confirmed_by_player=1)
    entries = await db.get_ledger_entries(sid)
    assert len(entries) == 2

    promises = await db.get_ledger_entries(sid, category="promise")
    assert len(promises) == 1
    assert promises[0]["value"] == "我答应陪你去看花火"

    # 6. Memories operations
    await db.add_memory(sid, "在咖啡馆度过了一个安静的雨天", location="咖啡馆")
    mems = await db.search_memories(sid, "咖啡馆")
    assert len(mems) == 1
    assert "咖啡馆" in mems[0]["summary"]

    # 7. Rollback
    revert_res = await db.rollback_recent_turns(sid, 1)
    assert revert_res["memories_reverted"] == 1
    assert revert_res["ledger_reverted"] == 1

    await db.close_all()


@pytest.mark.asyncio
async def test_claim_and_exclusivity(tmp_art_env):
    db: ArtDatabase = tmp_art_env["db"]
    sid = "claim-test-session"

    assert not await is_art_claimed(sid, db)
    # Claim for art
    ok, msg = await claim_session_for_art(sid, db, player_name="开拓者")
    assert ok is True
    assert await is_art_claimed(sid, db)

    # Release claim
    cards_dir = tmp_art_env["temp_dir"] / "cards"
    await release_session_claim(sid, db, cards_dir)
    assert not await is_art_claimed(sid, db)


def test_variance_rolls():
    tone = roll_daily_tone()
    assert isinstance(tone, str) and len(tone) > 0

    card = roll_scene_card()
    assert isinstance(card, str) and len(card) > 0

    outcome = roll_action_outcome()
    assert "grade" in outcome and "description" in outcome
    assert outcome["grade"] in ["意外之喜", "顺利", "小波折", "出洋相", "落空"]

    pacing = roll_midterm_pacing()
    assert isinstance(pacing, str) and len(pacing) > 0


def test_character_cards(tmp_art_env):
    card_mgr: CharacterCardManager = tmp_art_env["card_mgr"]
    sid = "test-card-sid"

    # Test resolving canonical card
    card, source, _ = card_mgr.resolve_card("流萤", sid)
    assert card is not None
    assert source == "canonical"

    # Test layered prompt extraction
    block = CharacterCardManager.extract_always_injected_block(card, nsfw=False)
    assert "【角色：流萤】" in block
    assert "说话口吻" in block
    assert "自称" in block

    # Test full appearance
    app = CharacterCardManager.extract_full_appearance(card)
    assert "外貌" in app

    # Test generated card creation, resolution, update, and deletion
    new_card_data = {
        "name": "星见雪",
        "tier": "major",
        "profile": {
            "profile_text": "银发少女，眼眸如深邃湖水。",
            "personality_tags": ["清冷", "执着"],
        },
        "voice": {"self_reference": "我", "call_player": "你", "tone": "平缓"},
    }
    saved_path = card_mgr.save_generated_card(sid, "星见雪", new_card_data)
    assert saved_path.exists()

    res_card, res_source, res_path = card_mgr.resolve_card("星见雪", sid)
    assert res_source == "generated"
    assert res_card["name"] == "星见雪"

    # Update generated card
    updated = card_mgr.update_generated_card(
        sid, "星见雪", {"profile": {"profile_text": "白发少女，眼角有一颗泪痣。"}}
    )
    assert updated is True
    res_card2, _, _ = card_mgr.resolve_card("星见雪", sid)
    assert "泪痣" in res_card2["profile"]["profile_text"]

    # Delete generated card
    deleted = card_mgr.delete_generated_card(sid, "星见雪")
    assert deleted is True
    res_card3, res_source3, _ = card_mgr.resolve_card("星见雪", sid)
    assert res_source3 == "none"


@pytest.mark.asyncio
async def test_tools_execution(tmp_art_env):
    state: ArtStateManager = tmp_art_env["state"]
    sid = "tool-test-sid"
    await state.init_session(sid, character_name="流萤", relationship_premise="恋人")

    # 1. change_scene tool
    res_str = await execute_change_scene(state, sid, "海边", "黄昏")
    res = json.loads(res_str)
    assert res["ok"] is True
    assert res["data"]["location"] == "海边"
    assert "📍 海边 · 黄昏" in res["data"]["notice"]

    # 2. cast tool (enter existing)
    res_str = await execute_cast(state, sid, "流萤", action="enter")
    res = json.loads(res_str)
    assert res["ok"] is True
    assert res["data"]["state"] == "present"

    # cast tool (generate unknown character)
    res_str = await execute_cast(state, sid, "艾琳娜", action="enter")
    res = json.loads(res_str)
    assert res["ok"] is True
    assert res["data"]["card_source"] == "generated"

    # cast tool (leave)
    res_str = await execute_cast(state, sid, "艾琳娜", action="leave")
    res = json.loads(res_str)
    assert res["ok"] is True
    assert res["data"]["state"] == "absent"

    # 3. fix_character tool
    res_str = await execute_fix_character(
        state, sid, "艾琳娜", action="update", details="有着琥珀色的双瞳"
    )
    res = json.loads(res_str)
    assert res["ok"] is True

    # 4. recall tool
    await state.db.add_memory(sid, "傍晚在海滩散步，捡到了贝壳", location="海边")
    res_str = await execute_recall(state, sid, "贝壳")
    res = json.loads(res_str)
    assert res["ok"] is True
    assert len(res["data"]["memories"]) == 1


@pytest.mark.asyncio
async def test_assemble_and_writing_core(tmp_art_env):
    state: ArtStateManager = tmp_art_env["state"]
    sid = "assemble-test-sid"
    await state.init_session(sid, character_name="流萤", relationship_premise="恋人")

    core_prompt = get_writing_core_prompt()
    assert "写作质量核心协议" in core_prompt
    assert "红线 1" in core_prompt
    assert "提议归角色，决定归玩家" in core_prompt
    assert (
        "绝不使用 `[1][2][3]`" in core_prompt
    )  # Ensured numbered menu rules are explicitly forbidden

    class DummyReq:
        def __init__(self):
            self.system_prompt = ""
            self.contexts = []
            self.func_tool = object()  # Simulate having a ToolSet

    req = DummyReq()
    await assemble_actor_request(
        req=req,
        state=state,
        session_id=sid,
        director_notes="- 推进花店剧情",
        scene_transition_notice="📍 花店 · 下午",
    )

    # Verify Actor tools stripped
    assert req.func_tool is None

    # Verify stable system prompt (layer 1) contains writing core and world setting
    sp = req.system_prompt
    assert "写作质量核心协议" in sp or "绝对红线" in sp
    assert "演员表演守则" in sp

    # Verify dynamic context (layer 2) injected to contexts with protection markers
    assert len(req.contexts) > 0
    system_contexts = [m for m in req.contexts if m.get("role") == "system"]
    assert len(system_contexts) > 0
    last_system = system_contexts[-1]
    assert last_system.get("_no_save") is True
    assert last_system.get("_no_truncate") is True
    content = last_system.get("content", "")
    assert "流萤" in content
    assert "编剧导演笔记" in content or "推进花店剧情" in content
    assert "📍 花店 · 下午" in content


@pytest.mark.asyncio
async def test_scribe_deterministic_commitments(tmp_art_env):
    state: ArtStateManager = tmp_art_env["state"]
    sid = "scribe-test-sid"
    await state.init_session(sid, character_name="流萤", relationship_premise="恋人")

    # Hard rule test:
    # 1. Player says "我答应你，周末一起去水族馆" -> MUST be recorded as promise!
    # 2. Actor reply says "你答应了要陪我去..." but player didn't -> Actor words MUST NOT be recorded!
    player_input = "没问题，我答应你，周末一起去水族馆。"
    actor_reply = "太好了！你答应了周末一起去水族馆，我很期待。"

    class DummyContext:
        pass

    class DummyEvent:
        pass

    # Scribe deterministic run
    await run_scribe(
        star_context=DummyContext(),
        event=DummyEvent(),
        state=state,
        session_id=sid,
        player_input=player_input,
        actor_response=actor_reply,
        provider_id=None,  # No LLM provider for unit test deterministic check
    )

    promises = await state.db.get_ledger_entries(sid, category="promise")
    assert len(promises) == 1
    assert "我答应你" in promises[0]["value"]

    # Test bracket pacing preference
    player_input_pref = "【最近别折腾我，想轻松一点】好的我们继续聊聊。"
    await run_scribe(
        star_context=DummyContext(),
        event=DummyEvent(),
        state=state,
        session_id=sid,
        player_input=player_input_pref,
        actor_response="好的，今天就安安静静待着。",
        provider_id=None,
    )
    prefs = await state.db.get_ledger_entries(sid, category="pacing_preference")
    assert len(prefs) == 1
    assert "最近别折腾我" in prefs[0]["value"]


@pytest.mark.asyncio
async def test_art_plugin_commands(tmp_art_env):
    from plugins.astrbot_plugin_art.main import ArtPlugin

    class MockContext:
        def __init__(self):
            self.conversation_manager = None

    class MockEvent:
        def __init__(self, session_id: str, sender_name: str = "开拓者"):
            self.unified_msg_origin = session_id
            self._sender_name = sender_name
            self.results = []

        def get_sender_name(self):
            return self._sender_name

        def plain_result(self, text: str):
            self.results.append(text)
            return text

    mock_ctx = MockContext()
    plugin = ArtPlugin(mock_ctx, config={"enable_debug": True})
    # Override db and state to use tmp_art_env
    plugin.db = tmp_art_env["db"]
    plugin.state = tmp_art_env["state"]
    plugin.card_mgr = tmp_art_env["card_mgr"]

    sid = "plugin-cmd-test-sid"
    event = MockEvent(sid, "开拓者")

    # 1. /art help
    help_results = [r async for r in plugin.art_help(event)]
    assert len(help_results) == 1
    assert "/art start" in help_results[0]
    assert "/art help" in help_results[0]

    # 2. /art start
    start_results = [
        r
        async for r in plugin.art_start(
            event, character_name="流萤", relationship_premise="恋人"
        )
    ]
    assert len(start_results) == 1
    assert "Art 剧作家模式已启动" in start_results[0]

    # 3. /art ledger
    ledger_results = [r async for r in plugin.art_ledger(event)]
    assert len(ledger_results) == 1
    assert "关于你的关系账本" in ledger_results[0]

    # 4. /art card
    card_results = [r async for r in plugin.art_card(event, character_name="流萤")]
    assert len(card_results) == 1
    assert "角色卡：流萤" in card_results[0]

    # 5. /art forget
    forget_results = [r async for r in plugin.art_forget(event, count=1)]
    assert len(forget_results) == 1
    assert "已成功回滚" in forget_results[0]

    # 6. /art debug
    debug_results = [r async for r in plugin.art_debug(event)]
    assert len(debug_results) == 1
    assert "Art 运行态全景" in debug_results[0]

    # 7. /art reset
    reset_results = [r async for r in plugin.art_reset(event)]
    assert len(reset_results) == 1
    await plugin.star_shutdown()


def test_clean_narrative_reply():
    from plugins.astrbot_plugin_art.main import clean_narrative_reply

    # Case 1: Plain text unchanged
    assert clean_narrative_reply("你好，开拓者。") == "你好，开拓者。"

    # Case 2: Strip <think>...</think> block
    raw_with_think = "<think>Let me roleplay Firefly properly.</think>你回来了？"
    assert clean_narrative_reply(raw_with_think) == "你回来了？"

    # Case 3: Strip English meta reasoning prefix (DeepSeek-flash artifact)
    raw_with_meta = (
        "As Firefly, I should respond in character.\n微风吹拂过花坛，少女轻声说道。"
    )
    assert clean_narrative_reply(raw_with_meta) == "微风吹拂过花坛，少女轻声说道。"

    # Case 4: Strip xiaoai_core scaffolding
    raw_with_xiaoai = "<xiaoai_core>internal plan</xiaoai_core>我们去那边走走吧。"
    assert clean_narrative_reply(raw_with_xiaoai) == "我们去那边走走吧。"

"""Unit test suite for astrbot_plugin_art."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from astrbot.core.astr_main_agent_resources import TOOL_CALL_PROMPT
from astrbot.core.provider.entities import ProviderType
from plugins.astrbot_plugin_art.core.assets import ArtAssets, PresetNotFound
from plugins.astrbot_plugin_art.core.cards import (
    CharacterCardManager,
)
from plugins.astrbot_plugin_art.core.claim import (
    claim_session_for_art,
    is_art_claimed,
    release_session_claim,
)
from plugins.astrbot_plugin_art.core.db import ArtDatabase
from plugins.astrbot_plugin_art.core.provider_resolver import (
    SOURCE_CONFIG,
    SOURCE_NONE,
    SOURCE_SELECTED,
    SOURCE_SESSION,
    resolve_provider,
)
from plugins.astrbot_plugin_art.core.state import ArtStateManager
from plugins.astrbot_plugin_art.core.variance import (
    NEUTRAL_DAILY_TONE,
    NEUTRAL_SCENE_CARD,
    roll_action_outcome,
    roll_daily_tone,
    roll_scene_card,
)
from plugins.astrbot_plugin_art.layers.assemble import (
    _LAYER1_SENTINEL,
    assemble_actor_request,
    strip_actor_forbidden_sections,
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
    plugin_dir = (
        Path(__file__).resolve().parent.parent / "plugins" / "astrbot_plugin_art"
    )
    assets = ArtAssets(plugin_dir / "presets", plugin_dir / "prompts")
    db = ArtDatabase(temp_dir)
    card_mgr = CharacterCardManager(cards_root=temp_dir / "cards")
    state = ArtStateManager(db, card_mgr, assets)

    yield {
        "temp_dir": temp_dir,
        "db": db,
        "card_mgr": card_mgr,
        "state": state,
        "assets": assets,
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
    # Pools now come from the caller (a preset), never from a module-level stock.
    assert roll_daily_tone(["清醒专注"]) == "清醒专注"
    assert roll_scene_card(["窗外忽然落雨"]) == "窗外忽然落雨"

    # A preset that omits its pools yields a content-free placeholder rather than
    # borrowing another world's flavour.
    assert roll_daily_tone() == NEUTRAL_DAILY_TONE
    assert roll_scene_card() == NEUTRAL_SCENE_CARD

    # No outcome table configured → the caller omits the pre-drawn line.
    assert roll_action_outcome(None) is None
    assert roll_action_outcome([]) is None

    outcomes = [
        {"grade": "顺利", "weight": 1.0, "description": "流畅"},
        {"grade": "落空", "weight": 0.0, "description": "没接住"},
    ]
    outcome = roll_action_outcome(outcomes)
    assert outcome["grade"] == "顺利"
    assert set(outcome) == {"grade", "weight", "description"}

    # The drawn outcome is a copy: mutating it must not poison the cached asset.
    outcome["grade"] = "MUTATED"
    assert outcomes[0]["grade"] == "顺利"


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
    app = CharacterCardManager.extract_full_appearance(card, "兜底外貌文案")
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
    await state.init_session(sid)

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
    await state.init_session(sid)
    # /art start no longer loads a player-chosen character, so cast one directly.
    await state.cast_character(sid, "流萤", action="enter")

    core_prompt = tmp_art_env["assets"].prompts.text("actor", "writing_core")
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
async def test_scribe_persists_llm_extraction_once(tmp_art_env):
    """The LLM decides what counts as a promise; the code only records it — once.

    No keyword matching happens in Python any more, so feeding the identical
    extraction twice must land exactly one row.
    """
    state: ArtStateManager = tmp_art_env["state"]
    sid = "scribe-test-sid"
    await state.init_session(sid)

    payload = {
        "confirmed_promise": "周末一起去水族馆",
        "pacing_preference": "最近别折腾我，想轻松一点",
        "shared_memory": "雨声里一起喝的拿铁",
        "unresolved_tiff": "",
        "gift": "",
        "player_wish": "",
        "player_profile_note": "",
        "hook_reaction": "none",
        "hook_title": "",
    }

    class FakeResponse:
        completion_text = json.dumps(payload, ensure_ascii=False)

    class FakeContext:
        async def tool_loop_agent(self, **kwargs):
            return FakeResponse()

    class DummyEvent:
        pass

    for _ in range(2):
        await run_scribe(
            star_context=FakeContext(),
            event=DummyEvent(),
            state=state,
            session_id=sid,
            player_input="没问题，我答应你，周末一起去水族馆。",
            actor_response="太好了！你答应了周末一起去水族馆，我很期待。",
            provider_id="fake-provider",
        )

    promises = await state.db.get_ledger_entries(sid, category="promise")
    assert len(promises) == 1
    assert promises[0]["value"] == "周末一起去水族馆"

    prefs = await state.db.get_ledger_entries(sid, category="pacing_preference")
    assert len(prefs) == 1
    assert "别折腾" in prefs[0]["value"]

    memories = await state.db.get_ledger_entries(sid, category="memory")
    assert len(memories) == 1


@pytest.mark.asyncio
async def test_scribe_hook_reaction_touches_one_hook(tmp_art_env):
    """Accepting one hook must not complete every unrelated future hook."""
    state: ArtStateManager = tmp_art_env["state"]
    sid = "scribe-hook-sid"
    await state.init_session(sid)

    first = await state.db.add_script(sid, "short", "一起去天台看星星", "她提过想去看星星")
    second = await state.db.add_script(sid, "short", "周末去水族馆", "她悄悄订了票")

    payload = {
        "confirmed_promise": "",
        "pacing_preference": "",
        "shared_memory": "",
        "unresolved_tiff": "",
        "gift": "",
        "player_wish": "",
        "player_profile_note": "",
        "hook_reaction": "accepted",
        "hook_title": "周末去水族馆",
    }

    class FakeResponse:
        completion_text = json.dumps(payload, ensure_ascii=False)

    class FakeContext:
        async def tool_loop_agent(self, **kwargs):
            return FakeResponse()

    class DummyEvent:
        pass

    await run_scribe(
        star_context=FakeContext(),
        event=DummyEvent(),
        state=state,
        session_id=sid,
        player_input="好呀，周末去水族馆。",
        actor_response="她眼睛亮了一下。",
        provider_id="fake-provider",
    )

    active_ids = {s["id"] for s in await state.db.get_active_scripts(sid, scope="short")}
    assert second not in active_ids  # the named hook was accepted
    assert first in active_ids  # the unrelated hook is untouched


@pytest.mark.asyncio
async def test_art_plugin_commands(tmp_art_env):
    from plugins.astrbot_plugin_art.main import ArtPlugin

    plugin = ArtPlugin(_MockArtContext(), config={"enable_debug": True})
    # Override db and state to use tmp_art_env
    plugin.db = tmp_art_env["db"]
    plugin.state = tmp_art_env["state"]
    plugin.card_mgr = tmp_art_env["card_mgr"]
    plugin.assets = tmp_art_env["assets"]

    sid = "plugin-cmd-test-sid"
    event = _MockCommandEvent(sid, "开拓者")

    # 1. /art help
    help_results = [r async for r in plugin.art_help(event)]
    assert len(help_results) == 1
    assert "/art start" in help_results[0]
    assert "/art help" in help_results[0]

    # 2. /art start — a one-line confirmation, then the LLM-speaks-first request
    start_results = [r async for r in plugin.art_start(event)]
    assert len(start_results) == 2
    assert "世界已开启" in start_results[0]
    assert "世界初启" in start_results[1].prompt
    # Only the prologue avatar is on stage: no player-chosen card is pre-loaded.
    present = {c["character_name"] for c in await plugin.db.get_present_characters(sid)}
    assert present == {"爱莉希雅"}

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


# ---------------------------------------------------------------------------
# Audit ledger
# ---------------------------------------------------------------------------


def _make_ledger(root: Path, *, enabled: bool = True, max_files: int = 200):
    from plugins.astrbot_plugin_art.core.audit_ledger import LLMAuditLedger

    return LLMAuditLedger(
        root,
        enabled_getter=lambda: enabled,
        max_files_getter=lambda: max_files,
    )


def _audit_turn(turn_id: str):
    from plugins.astrbot_plugin_art.core.audit_ledger import AuditTurn

    return AuditTurn(turn_id=turn_id, user_id="u1")


def test_audit_ledger_disabled_writes_nothing(tmp_path):
    """With the switch off, nothing is written and callers get None."""
    ledger = _make_ledger(tmp_path / "llm_audit", enabled=False)

    assert ledger.is_enabled() is False
    assert (
        ledger.record_request(
            session_id="s1",
            user_id="u1",
            stage="actor",
            request={"system_prompt": "x", "contexts": [], "prompt": "y"},
        )
        is None
    )
    # record_response with no path must be a silent no-op
    ledger.record_response(None, response_text="ignored")

    assert not (tmp_path / "llm_audit").exists()
    assert not (tmp_path / "llm_audit_index").exists()


def test_audit_ledger_layout_and_turn_grouping(tmp_path):
    """Three stages of one turn share a turn_id; only actor reaches the index."""
    ledger = _make_ledger(tmp_path / "llm_audit")
    sid = "group-test-sid"
    key = ledger.session_key(sid)
    turn_id = ledger.new_turn_id()

    playwright_path = ledger.record_request(
        session_id=sid,
        user_id="u1",
        stage="playwright",
        turn_id=turn_id,
        request={"system_prompt": "pw", "contexts": [], "prompt": "scene"},
    )[1]
    ledger.record_response(playwright_path, response_text="[导演笔记]")

    actor_path = ledger.record_request(
        session_id=sid,
        user_id="u1",
        stage="actor",
        turn_id=turn_id,
        request={"system_prompt": "actor", "contexts": [], "prompt": "input"},
        metadata={
            "current_turn": {
                "preset_name": "elysium",
                "user_hash": "abc",
                "user_preview": "你好",
            }
        },
    )[1]
    ledger.record_response(actor_path, response_text="回复正文")

    scribe_path = ledger.record_request(
        session_id=sid,
        user_id="u1",
        stage="scribe",
        turn_id=turn_id,
        request={"system_prompt": "scribe", "contexts": [], "prompt": "extract"},
    )[1]
    ledger.record_response(scribe_path, response_text='{"shared_memory": "x"}')

    session_dir = tmp_path / "llm_audit" / key
    files = sorted(p.name for p in session_dir.glob("*.json"))
    expected = {
        f"{turn_id}-playwright-{key}.json",
        f"{turn_id}-actor-{key}.json",
        f"{turn_id}-scribe-{key}.json",
    }
    assert set(files) == expected

    # Only the actor response appends to the turn index.
    rows = ledger.load_turn_index(sid)
    assert len(rows) == 1
    assert rows[0]["stage"] == "actor"
    assert rows[0]["turn_id"] == turn_id
    assert rows[0]["preset_name"] == "elysium"
    assert rows[0]["assistant_preview"] == "回复正文"
    assert rows[0]["response_error"] is False


def test_audit_ledger_response_roundtrip(tmp_path):
    """record_response fills the response half of an existing document."""
    ledger = _make_ledger(tmp_path / "llm_audit")
    sid = "roundtrip-sid"

    audit_id, path = ledger.record_request(
        session_id=sid,
        user_id="u1",
        stage="playwright",
        request={"system_prompt": "sp", "contexts": [], "prompt": "p"},
    )

    before = json.loads(path.read_text(encoding="utf-8"))
    assert before["response"] is None
    assert before["request"]["prompt"] == "p"
    assert before["turn_id"]

    ledger.record_response(
        path,
        response_text="导演笔记",
        response_meta={"is_fallback": True, "fallback_reason": "exception"},
        error="boom",
    )

    doc = ledger.load_doc(audit_id, sid)
    assert doc is not None
    assert doc["response"]["text"] == "导演笔记"
    assert doc["response"]["error"] == "boom"
    assert doc["response"]["meta"]["fallback_reason"] == "exception"


def test_audit_ledger_prunes_old_files(tmp_path):
    """Pruning keeps the per-session document count at max_files."""
    ledger = _make_ledger(tmp_path / "llm_audit", max_files=2)
    sid = "prune-sid"

    for i in range(4):
        assert (
            ledger.record_request(
                session_id=sid,
                user_id="u1",
                stage="playwright",
                request={"system_prompt": f"sp{i}", "contexts": [], "prompt": f"p{i}"},
            )
            is not None
        )

    session_dir = tmp_path / "llm_audit" / ledger.session_key(sid)
    assert len(list(session_dir.glob("*.json"))) == 2


def test_audit_ledger_max_files_zero_disables_pruning(tmp_path):
    """max_files=0 means 'never prune'."""
    ledger = _make_ledger(tmp_path / "llm_audit", max_files=0)
    sid = "noprune-sid"

    for i in range(3):
        ledger.record_request(
            session_id=sid,
            user_id="u1",
            stage="playwright",
            request={"system_prompt": f"sp{i}", "contexts": [], "prompt": f"p{i}"},
        )

    session_dir = tmp_path / "llm_audit" / ledger.session_key(sid)
    assert len(list(session_dir.glob("*.json"))) == 3


@pytest.mark.asyncio
async def test_scribe_audit_records_no_provider(tmp_art_env, tmp_path):
    """The silent 'no provider' exit now leaves an explicit audit record."""
    state: ArtStateManager = tmp_art_env["state"]
    sid = "scribe-audit-noprov"
    await state.init_session(sid)

    ledger = _make_ledger(tmp_path / "llm_audit")

    class DummyContext:
        pass

    class DummyEvent:
        pass

    await run_scribe(
        star_context=DummyContext(),
        event=DummyEvent(),
        state=state,
        session_id=sid,
        player_input="今天想安静待着【轻松一点】",
        actor_response="好呀。",
        provider_id=None,
        audit_ledger=ledger,
        audit_turn=_audit_turn("t-noprov"),
    )

    rows = ledger.load_turn_index(sid)
    # No actor call in this test, so nothing reaches the index.
    assert rows == []

    session_dir = tmp_path / "llm_audit" / ledger.session_key(sid)
    docs = [json.loads(p.read_text(encoding="utf-8")) for p in session_dir.glob("*.json")]
    assert len(docs) == 1
    doc = docs[0]
    assert doc["stage"] == "scribe"
    assert doc["response"]["error"] == "no_provider"
    assert doc["response"]["meta"]["fallback_reason"] == "no_provider"
    # No language parsing happens in code any more: the only deterministic fact
    # this stage records is whether a scene was archived.
    assert doc["audit_view"]["deterministic"] == {"scene_archived": False}


@pytest.mark.asyncio
async def test_scribe_audit_records_parsed_writes(tmp_art_env, tmp_path):
    """A successful scribe pass records the raw JSON and every write it made."""
    state: ArtStateManager = tmp_art_env["state"]
    sid = "scribe-audit-ok"
    await state.init_session(sid)

    ledger = _make_ledger(tmp_path / "llm_audit")

    class FakeResponse:
        completion_text = json.dumps(
            {
                "confirmed_promise": "下次一起去水族馆",
                "pacing_preference": "",
                "shared_memory": "雨声里一起喝的拿铁",
                "unresolved_tiff": "",
                "gift": "",
                "player_wish": "想去看海",
                "player_profile_note": "偏爱安静的陪伴",
                "hook_reaction": "none",
                "hook_title": "",
            },
            ensure_ascii=False,
        )

    class FakeContext:
        async def tool_loop_agent(self, **kwargs):
            return FakeResponse()

    class DummyEvent:
        pass

    await run_scribe(
        star_context=FakeContext(),
        event=DummyEvent(),
        state=state,
        session_id=sid,
        player_input="外面的雨好像停了。",
        actor_response="她把杯子推近了一点。",
        provider_id="fake-provider",
        audit_ledger=ledger,
        audit_turn=_audit_turn("t-ok"),
    )

    session_dir = tmp_path / "llm_audit" / ledger.session_key(sid)
    docs = [json.loads(p.read_text(encoding="utf-8")) for p in session_dir.glob("*.json")]
    assert len(docs) == 1
    doc = docs[0]
    meta = doc["response"]["meta"]
    assert meta["parsed_ok"] is True
    assert meta["parsed"]["shared_memory"] == "雨声里一起喝的拿铁"

    categories = {w["category"] for w in meta["writes"]}
    assert "memory" in categories
    assert "promise" in categories
    assert "player_profile" in categories
    assert "script:mid" in categories

    # The writes are real, not just audited.
    memories = await state.db.get_ledger_entries(sid, category="memory")
    assert any("拿铁" in m["value"] for m in memories)
    # The promise the LLM extracted is persisted, not silently dropped.
    promises = await state.db.get_ledger_entries(sid, category="promise")
    assert [p["value"] for p in promises] == ["下次一起去水族馆"]


class _DummyReq:
    """Minimal stand-in for AstrBot's ProviderRequest."""

    def __init__(self, persona: str = ""):
        self.system_prompt = persona
        self.contexts = []
        self.func_tool = object()  # simulate an attached ToolSet


def _dynamic_block(req: _DummyReq) -> str:
    """The _no_save system block Layer 2 injects into req.contexts."""
    return "\n".join(
        m["content"]
        for m in req.contexts
        if m.get("role") == "system" and m.get("_no_save")
    )


@pytest.mark.asyncio
async def test_cast_is_authoritative_for_presence(tmp_art_env):
    """`[cast]` decides who is on stage — not the scene row's stale snapshot."""
    state: ArtStateManager = tmp_art_env["state"]
    sid = "presence-sid"
    await state.init_session(sid)
    await state.cast_character(sid, "流萤", action="enter")

    req = _DummyReq()
    await assemble_actor_request(
        req=req, state=state, session_id=sid, director_notes="-"
    )
    assert "【角色：流萤】" in _dynamic_block(req)

    # Casting someone mid-scene must inject their card this very turn.
    await execute_cast(state, sid, "三月七", action="enter")
    req = _DummyReq()
    await assemble_actor_request(
        req=req, state=state, session_id=sid, director_notes="-"
    )
    assert "【角色：三月七】" in _dynamic_block(req)

    # Leaving removes her from the very next prompt.
    await execute_cast(state, sid, "三月七", action="leave")
    req = _DummyReq()
    await assemble_actor_request(
        req=req, state=state, session_id=sid, director_notes="-"
    )
    block = _dynamic_block(req)
    assert "【角色：三月七】" not in block
    assert "【角色：流萤】" in block

    # A presence list passed explicitly to change_scene becomes authoritative too
    # (it used to be written only to the scene snapshot and silently dropped).
    await execute_change_scene(
        state, sid, "海边", "黄昏", present_characters=["流萤", "三月七"]
    )
    present = await state.db.get_present_characters(sid)
    assert {c["character_name"] for c in present} == {"流萤", "三月七"}


@pytest.mark.asyncio
async def test_layer1_injected_every_turn(tmp_art_env):
    """Layer 1 is re-appended unconditionally, without accumulating or doubling."""
    state: ArtStateManager = tmp_art_env["state"]
    sid = "layer1-sid"
    await state.init_session(sid)

    for _ in range(3):
        req = _DummyReq("你是 Persona 里配置的角色。")
        await assemble_actor_request(
            req=req, state=state, session_id=sid, director_notes="-"
        )
        assert "写作质量核心协议" in req.system_prompt
        assert "世界背景" in req.system_prompt
        assert "演员表演守则" in req.system_prompt
        # Persona content is preserved, and the art block never doubles.
        assert "你是 Persona 里配置的角色。" in req.system_prompt
        assert req.system_prompt.count("写作质量核心协议") == 1


@pytest.mark.asyncio
async def test_unknown_preset_reports_and_does_not_claim(tmp_art_env):
    """A typo in the world name must not half-initialise a claimed session."""
    from plugins.astrbot_plugin_art.main import ArtPlugin

    plugin = ArtPlugin(_MockArtContext(), config={})
    plugin.db = tmp_art_env["db"]
    plugin.state = tmp_art_env["state"]
    plugin.card_mgr = tmp_art_env["card_mgr"]
    plugin.assets = tmp_art_env["assets"]

    sid = "bad-preset-sid"
    event = _MockCommandEvent(sid)
    results = [r async for r in plugin.art_start(event, preset_name="不存在的世界")]
    assert len(results) == 1
    assert "未知世界观" in results[0]
    assert not await is_art_claimed(sid, tmp_art_env["db"])
    await plugin.star_shutdown()


@pytest.mark.asyncio
async def test_ledger_insert_if_absent_is_idempotent(tmp_art_env):
    db: ArtDatabase = tmp_art_env["db"]
    sid = "ledger-idem-sid"

    first = await db.add_ledger_entry_if_absent(sid, "memory", "共同回忆", "雨声里的拿铁")
    repeat = await db.add_ledger_entry_if_absent(
        sid, "memory", "共同回忆", "雨声里的拿铁"
    )
    other = await db.add_ledger_entry_if_absent(
        sid, "memory", "共同回忆", "另一件小事"
    )

    assert first is not None
    assert repeat is None
    assert other is not None
    assert len(await db.get_ledger_entries(sid, category="memory")) == 2


def test_assets_hot_reload(tmp_path):
    """Editing an asset file takes effect without restarting AstrBot."""
    presets = tmp_path / "presets"
    prompts = tmp_path / "prompts"
    presets.mkdir()
    prompts.mkdir()

    preset = {
        "name": "toy",
        "display_name": "玩具世界",
        "world_setting": "只有一个房间的世界。",
        "locations": ["房间"],
        "time_slices": ["白天"],
        "default_location": "房间",
        "default_time_slice": "白天",
        "daily_tones": ["平静"],
        "scene_cards": ["窗帘动了一下"],
    }
    preset_file = presets / "toy.json"
    preset_file.write_text(json.dumps(preset, ensure_ascii=False), encoding="utf-8")
    prompt_file = prompts / "actor.yaml"
    prompt_file.write_text(
        "writing_core: |\n  第一版\nactor_rules: |\n  规则\n", encoding="utf-8"
    )

    assets = ArtAssets(presets, prompts)
    assert assets.presets.names() == ["toy"]
    assert assets.presets.get("toy")["display_name"] == "玩具世界"
    assert assets.prompts.text("actor", "writing_core") == "第一版"

    # An unknown world raises; no other world is substituted for it.
    with pytest.raises(PresetNotFound):
        assets.presets.get("missing")

    # Editing existing files is picked up on the next read.
    preset["display_name"] = "玩具世界·改"
    preset_file.write_text(json.dumps(preset, ensure_ascii=False), encoding="utf-8")
    prompt_file.write_text(
        "writing_core: |\n  第二版\nactor_rules: |\n  规则\n", encoding="utf-8"
    )
    _bump_mtime(preset_file)
    _bump_mtime(prompt_file)
    assert assets.presets.get("toy")["display_name"] == "玩具世界·改"
    assert assets.prompts.text("actor", "writing_core") == "第二版"

    # A brand-new world file appears without reconstructing the store.
    (presets / "second.json").write_text(
        json.dumps({**preset, "name": "second"}, ensure_ascii=False), encoding="utf-8"
    )
    _bump_mtime(presets)
    assert "second" in assets.presets.names()


def _bump_mtime(path: Path) -> None:
    """Force a distinct mtime so hot-reload detection is not timestamp-flaky."""
    stat = path.stat()
    os.utime(path, (stat.st_atime, stat.st_mtime + 10))


class _MockArtContext:
    """Minimal stand-in for AstrBot's plugin context."""

    def __init__(self, conversation_manager=None):
        self.conversation_manager = conversation_manager


class _RequestedLLM:
    """What a real ``event.request_llm(...)`` produces (a ProviderRequest)."""

    def __init__(self, prompt: str, conversation):
        self.prompt = prompt
        self.conversation = conversation


class _MockCommandEvent:
    """Minimal stand-in for AstrMessageEvent, sufficient for /art commands."""

    def __init__(
        self,
        session_id: str,
        sender_name: str = "开拓者",
        message_str: str = "",
    ):
        self.unified_msg_origin = session_id
        self.message_str = message_str
        self.results = []
        self._sender_name = sender_name
        self._extras: dict = {}

    def get_sender_name(self):
        return self._sender_name

    def get_sender_id(self):
        return "u1"

    def plain_result(self, text: str):
        self.results.append(text)
        return text

    def set_extra(self, key, value):
        self._extras[key] = value

    def get_extra(self, key=None, default=None):
        if key is None:
            return self._extras
        return self._extras.get(key, default)

    def request_llm(self, prompt: str = "", conversation=None, **kwargs):
        return _RequestedLLM(prompt=prompt, conversation=conversation)


class _FakeConversationManager:
    """Records what art asks of AstrBot's conversation manager."""

    def __init__(self):
        self.created: list[str] = []
        self.current: str | None = None

    async def get_curr_conversation_id(self, umo: str):
        return self.current

    async def new_conversation(self, umo: str):
        self.current = f"conv-{len(self.created)}"
        self.created.append(umo)
        return self.current

    async def get_conversation(
        self, umo: str, conv_id: str, create_if_not_exists=False
    ):
        return {"umo": umo, "id": conv_id}


def _art_plugin(tmp_art_env, context=None, config=None):
    """An ArtPlugin wired to the temporary test environment."""
    from plugins.astrbot_plugin_art.main import ArtPlugin

    plugin = ArtPlugin(context or _MockArtContext(), config=config or {})
    plugin.db = tmp_art_env["db"]
    plugin.state = tmp_art_env["state"]
    plugin.card_mgr = tmp_art_env["card_mgr"]
    plugin.assets = tmp_art_env["assets"]
    return plugin


@pytest.mark.asyncio
async def test_init_session_loads_only_the_prologue_avatar(tmp_art_env):
    """Opening the world casts the avatar — never a player-chosen character."""
    state: ArtStateManager = tmp_art_env["state"]
    sid = "prologue-cast-sid"

    info = await state.init_session(sid)

    assert info["avatar"] == "爱莉希雅"
    present = {c["character_name"] for c in await state.db.get_present_characters(sid)}
    assert present == {"爱莉希雅"}
    # No story character exists yet; those are loaded on request, through `cast`.
    assert "流萤" not in {c["name"] for c in state.cards.list_generated_cards(sid)}


@pytest.mark.asyncio
async def test_prologue_asset_defaults_and_preset_override(tmp_art_env):
    state: ArtStateManager = tmp_art_env["state"]

    # Defaults come from prompts/prologue.yaml.
    assert state.prologue_avatar_name({}) == "世界意志"
    assert "世界初启" in state.prologue_opening({})

    # A world-view may override both.
    assert state.prologue_avatar_name({"prologue_avatar": "爱莉希雅"}) == "爱莉希雅"
    assert state.prologue_opening({"prologue_opening": "自定义开场"}) == "自定义开场"


@pytest.mark.asyncio
async def test_start_prepares_a_conversation_for_the_opening(tmp_art_env):
    """Without a conversation AstrBot's `_save_to_history` bails, so the opening
    turn would never reach history and the next prologue turn would be blind."""
    conv_mgr = _FakeConversationManager()
    plugin = _art_plugin(tmp_art_env, _MockArtContext(conv_mgr))

    sid = "opening-conv-sid"
    event = _MockCommandEvent(sid)
    results = [r async for r in plugin.art_start(event)]

    assert len(results) == 2
    assert results[1].conversation == {"umo": sid, "id": "conv-0"}
    assert conv_mgr.created == [sid]
    await plugin.star_shutdown()


@pytest.mark.asyncio
async def test_opening_turn_ignores_the_command_text(tmp_art_env):
    """The opening is triggered by /art start, not by player words."""
    plugin = _art_plugin(tmp_art_env)
    sid = "opening-blank-sid"
    await plugin.state.init_session(sid)

    normal = _MockCommandEvent(sid, message_str="art start default")
    await plugin.on_art_llm_request(normal, _DummyReq())
    assert plugin._turn_states[sid]["player_input"] == "art start default"

    opening = _MockCommandEvent(sid, message_str="art start default")
    opening.set_extra("art_opening_turn", True)
    await plugin.on_art_llm_request(opening, _DummyReq())
    assert plugin._turn_states[sid]["player_input"] == ""
    await plugin.star_shutdown()


@pytest.mark.asyncio
async def test_scribe_persists_relationship_premise(tmp_art_env):
    """What the player says about the relationship becomes a session field."""
    state: ArtStateManager = tmp_art_env["state"]
    sid = "scribe-premise-sid"
    await state.init_session(sid)

    payload = {
        "confirmed_promise": "",
        "relationship_premise": "恋人，同居第三个月",
        "pacing_preference": "",
        "shared_memory": "",
        "unresolved_tiff": "",
        "gift": "",
        "player_wish": "",
        "player_profile_note": "",
        "hook_reaction": "none",
        "hook_title": "",
    }

    class FakeResponse:
        completion_text = json.dumps(payload, ensure_ascii=False)

    class FakeContext:
        async def tool_loop_agent(self, **kwargs):
            return FakeResponse()

    class DummyEvent:
        pass

    await run_scribe(
        star_context=FakeContext(),
        event=DummyEvent(),
        state=state,
        session_id=sid,
        player_input="其实我们已经是恋人了，同居第三个月。",
        actor_response="她笑了笑。",
        provider_id="fake-provider",
    )

    sess = await state.db.get_session(sid)
    assert sess["relationship_premise"] == "恋人，同居第三个月"


def test_preset_resolves_chinese_names_and_aliases(tmp_art_env):
    """Chinese display names and aliases work as well as the English stems."""
    presets = tmp_art_env["assets"].presets

    assert presets.get("elysium")["name"] == "elysium"
    assert presets.get("黄金庭院")["name"] == "elysium"  # display_name
    assert presets.get("新爱莉都")["name"] == "elysium"  # aliases
    assert presets.get("星穹铁道")["name"] == "star-rail"
    assert presets.get("星铁")["name"] == "star-rail"
    assert presets.get("原神")["name"] == "genshin"
    assert presets.get("现代日常")["name"] == "default"

    with pytest.raises(PresetNotFound):
        presets.get("不存在的世界")

    # The "available" hint lists names a player can actually type.
    assert "黄金庭院（elysium）" in "、".join(presets.display_names())


@pytest.mark.asyncio
async def test_start_accepts_a_chinese_world_name(tmp_art_env):
    plugin = _art_plugin(tmp_art_env)
    sid = "cn-world-sid"
    event = _MockCommandEvent(sid)

    results = [r async for r in plugin.art_start(event, preset_name="新爱莉都")]

    assert len(results) == 2
    # The world is canonicalised to its internal name before being stored.
    assert (await plugin.db.get_session(sid))["preset"] == "elysium"
    assert "黄金庭院" in results[0]
    await plugin.star_shutdown()


# ---------------------------------------------------------------------------
# Actor prompt hygiene: core-injected skills / tool apparatus
# ---------------------------------------------------------------------------

_PERSONA = "# Persona Instructions\n你是一个角色扮演助手，请保持角色。"
_SKILLS_BLOCK = (
    "\n## Skills\n\n"
    "You have specialized skills — reusable instruction bundles stored "
    "in `SKILL.md` files.\n\n"
    "### Available skills\n\n"
    "- **griseo-skill**: 蒸馏《崩坏3》格蕾修的扮演 Skill。\n"
    "  File: `C:/x/data/skills/griseo-skill/SKILL.md`\n\n"
    "### Skill rules\n\n"
    "3. **Mandatory grounding** — Before executing any skill you MUST first "
    "read its `SKILL.md` by running a shell command.\n"
)
_TOOL_BLOCK = (
    f"\n{TOOL_CALL_PROMPT}\n"
    "\nCurrent workspace you can use: "
    "`C:\\agentic-rpg\\AstrBot\\data\\workspaces\\discord_GroupMessage_1`\n"
    "Unless the user explicitly specifies a different directory, "
    "perform all file-related operations in this workspace.\n"
)


def test_strip_removes_core_skills_and_tool_apparatus():
    """The Actor must not be told about skills it has no tools to read."""
    prompt = _PERSONA + _SKILLS_BLOCK + _TOOL_BLOCK

    cleaned, removed = strip_actor_forbidden_sections(prompt)

    assert set(removed) == {
        "skills_inventory",
        "tool_call_prompt",
        "computer_use_workspace",
    }
    assert cleaned == _PERSONA
    for leak in ("## Skills", "SKILL.md", "When using tools", "workspaces"):
        assert leak not in cleaned


def test_strip_is_a_noop_when_nothing_to_remove():
    clean = "# Persona\n正常的系统提示，没有核心注入的工具说明。"
    assert strip_actor_forbidden_sections(clean) == (clean, [])
    assert strip_actor_forbidden_sections("") == ("", [])


def test_strip_refuses_to_truncate_art_content():
    """Fails safe: never drop art's own protocol along with core's apparatus."""
    prompt = (
        _PERSONA
        + _SKILLS_BLOCK
        + _TOOL_BLOCK
        + f"\n\n---\n\n# 剧作家写作质量核心协议\n\n{_LAYER1_SENTINEL}"
    )

    assert strip_actor_forbidden_sections(prompt) == (prompt, [])


@pytest.mark.asyncio
async def test_assemble_strips_core_apparatus_from_actor_prompt(tmp_art_env):
    state: ArtStateManager = tmp_art_env["state"]
    sid = "strip-test-sid"
    await state.init_session(sid)

    class DummyReq:
        def __init__(self):
            self.system_prompt = _PERSONA + _SKILLS_BLOCK + _TOOL_BLOCK
            self.contexts = []
            self.func_tool = object()

    req = DummyReq()
    stripped = await assemble_actor_request(
        req=req,
        state=state,
        session_id=sid,
        director_notes="- 推进剧情",
    )

    assert set(stripped) == {
        "skills_inventory",
        "tool_call_prompt",
        "computer_use_workspace",
    }
    # Persona survives; the skills inventory and tool guidance do not.
    assert "# Persona Instructions" in req.system_prompt
    assert "## Skills" not in req.system_prompt
    assert "SKILL.md" not in req.system_prompt
    assert "When using tools" not in req.system_prompt
    assert "workspaces" not in req.system_prompt
    # Art's own protocol is still appended.
    assert "写作质量核心协议" in req.system_prompt


# ---------------------------------------------------------------------------
# Out-of-band provider resolution (playwright / scribe)
# ---------------------------------------------------------------------------


class _FakeMeta:
    def __init__(self, pid, model="", provider_type=ProviderType.CHAT_COMPLETION):
        self.id = pid
        self.model = model
        self.provider_type = provider_type


class _FakeProvider:
    def __init__(
        self,
        pid,
        model="fake-model",
        provider_type=ProviderType.CHAT_COMPLETION,
    ):
        self._meta = _FakeMeta(pid, model, provider_type)

    def meta(self):
        return self._meta

    def get_model(self):
        return self._meta.model


class _FakeEvent:
    def __init__(self, umo="discord:GroupMessage:1", selected=None):
        self.unified_msg_origin = umo
        self._extra = {"selected_provider": selected} if selected else {}

    def get_extra(self, key, default=None):
        return self._extra.get(key, default)


class _FakeContext:
    def __init__(self, session_provider=None, by_id=None, raises=False):
        self._session_provider = session_provider
        self._by_id = by_id or {}
        self._raises = raises

    def get_using_provider(self, umo):
        if self._raises:
            raise ValueError("provider manager exploded")
        return self._session_provider

    def get_provider_by_id(self, provider_id):
        return self._by_id.get(provider_id)


def test_resolve_provider_prefers_configured_id():
    r = resolve_provider(_FakeContext(), _FakeEvent(), configured_id="my-model")
    assert (r.provider_id, r.source) == ("my-model", SOURCE_CONFIG)
    assert r.ok


def test_resolve_provider_falls_back_to_session_provider():
    """The regression: this used to hit two APIs that do not exist."""
    ctx = _FakeContext(session_provider=_FakeProvider("discord-model", "model-x"))
    r = resolve_provider(ctx, _FakeEvent())

    assert (r.provider_id, r.source, r.model) == (
        "discord-model",
        SOURCE_SESSION,
        "model-x",
    )
    assert r.ok


def test_resolve_provider_honours_selected_provider_extra():
    ctx = _FakeContext(by_id={"picked": _FakeProvider("picked", "m2")})
    r = resolve_provider(ctx, _FakeEvent(selected="picked"))

    assert (r.provider_id, r.source) == ("picked", SOURCE_SELECTED)


def test_resolve_provider_rejects_non_chat_selected_provider():
    """A TTS/STT/embedding id must not be handed to a tool_loop_agent call."""
    tts = _FakeProvider(
        "tts-1", provider_type=ProviderType.TEXT_TO_SPEECH
    )
    ctx = _FakeContext(
        session_provider=_FakeProvider("session-model"), by_id={"tts-1": tts}
    )
    r = resolve_provider(ctx, _FakeEvent(selected="tts-1"))

    assert r.ok is False
    assert r.source == SOURCE_NONE


def test_resolve_provider_returns_none_when_unresolvable():
    assert resolve_provider(_FakeContext(), _FakeEvent()).source == SOURCE_NONE
    assert (
        resolve_provider(_FakeContext(raises=True), _FakeEvent()).source
        == SOURCE_NONE
    )
    assert resolve_provider(_FakeContext(), _FakeEvent(umo="")).source == SOURCE_NONE
    # A provider with no id is unusable.
    assert (
        resolve_provider(
            _FakeContext(session_provider=_FakeProvider("")), _FakeEvent()
        ).source
        == SOURCE_NONE
    )


def test_playwright_audit_records_resolved_provider_and_model(tmp_path):
    """Which model ran must be readable from the ledger, not just the id."""
    from plugins.astrbot_plugin_art.layers.playwright import _record_playwright_request

    ledger = _make_ledger(tmp_path / "llm_audit")
    path = _record_playwright_request(
        audit_ledger=ledger,
        audit_turn=_audit_turn("turn-model"),
        session_id="model-sid",
        full_prompt="prompt",
        system_prompt="system",
        provider_id="应急大鲸鱼/deepseek-v4-flash",
        model="deepseek-v4-flash",
        provider_source=SOURCE_SESSION,
        audit_view={},
    )

    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    assert doc["provider_id"] == "应急大鲸鱼/deepseek-v4-flash"
    assert doc["model"] == "deepseek-v4-flash"
    assert doc["assembly_trace"]["provider_source"] == SOURCE_SESSION


# ---------------------------------------------------------------------------
# Playwright tool contract: handler(event, **kwargs)
# ---------------------------------------------------------------------------


def test_playwright_tool_handlers_take_event_as_first_argument(tmp_art_env):
    """AstrBot invokes a handler tool as ``handler(event, **kwargs)``.

    A business parameter in the first slot means the *event* lands in it — which
    is how every ``change_scene`` / ``cast`` call died with
    ``'DiscordPlatformEvent' object has no attribute 'strip'``.
    """
    import inspect

    plugin = _art_plugin(tmp_art_env)
    tool_set = plugin._build_playwright_toolset()

    assert {t.name for t in tool_set.tools} == {
        "change_scene",
        "cast",
        "recall",
        "fix_character",
    }
    for tool in tool_set.tools:
        params = list(inspect.signature(tool.handler).parameters)
        assert params[0] == "event", f"{tool.name}: first arg is {params[0]!r}"
    # The shared ToolSet must not carry per-turn session state: it is one
    # instance for the whole plugin and would race across sessions.
    assert not hasattr(tool_set, "current_session_id")


@pytest.mark.asyncio
async def test_playwright_tools_run_with_the_core_calling_convention(tmp_art_env):
    """End-to-end through the same call shape the core uses."""
    plugin = _art_plugin(tmp_art_env)
    sid = "tool-call-sid"
    await plugin.state.init_session(sid)

    by_name = {t.name: t for t in plugin._build_playwright_toolset().tools}
    event = _MockCommandEvent(sid)

    cast_result = json.loads(
        await by_name["cast"].handler(event, character_name="流萤", action="enter")
    )
    assert cast_result["ok"] is True
    assert cast_result["data"]["character_name"] == "流萤"

    scene_result = json.loads(
        await by_name["change_scene"].handler(event, location="花房", time_of_day="夜里")
    )
    assert scene_result["ok"] is True
    assert scene_result["data"]["location"] == "花房"

    await plugin.star_shutdown()


@pytest.mark.asyncio
async def test_tool_error_envelope_hides_the_raw_exception(tmp_art_env, monkeypatch):
    """The envelope reaches the playwright's context and got copied verbatim
    into the director notes, so it must not carry exception text."""
    state: ArtStateManager = tmp_art_env["state"]
    secret = "INTERNAL_STACK_DETAIL_42"

    async def explode(**kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(state, "change_scene", explode)

    payload = json.loads(await execute_change_scene(state, "sid", "花房"))
    assert payload["ok"] is False
    assert secret not in payload["error"]
    assert "RuntimeError" not in payload["error"]


# ---------------------------------------------------------------------------
# Character card rendering
# ---------------------------------------------------------------------------


def test_appearance_anchor_skips_rules_and_matches_current_form():
    """profile_text opens with identity rules, not appearance."""
    profile_text = (
        "【身份与默认运行规则】\n默认没有指定对象时走形态A。\n"
        "【外貌·形态A】\n形态A 的最高优先级锚点是红色头饰。\n"
        "【外貌·形态B】\n形态B 的最高优先级锚点是蓝色披风。\n"
    )
    card = {"name": "测试", "profile": {"profile_text": profile_text}}

    form_b = CharacterCardManager.extract_always_injected_block(
        card, current_form="形态B"
    )
    assert "蓝色披风" in form_b
    assert "红色头饰" not in form_b
    # The identity rules must never become the appearance anchor.
    assert "身份与默认运行规则" not in form_b

    # No form given -> first 外貌 section, still never the rules.
    fallback = CharacterCardManager.extract_always_injected_block(card)
    assert "红色头饰" in fallback
    assert "身份与默认运行规则" not in fallback

    # Unknown form -> fall back rather than emit nothing.
    unknown = CharacterCardManager.extract_always_injected_block(
        card, current_form="形态C"
    )
    assert "红色头饰" in unknown


def test_voice_rule_prose_is_not_wrapped_in_quotes():
    """self_reference/call_player are rule sentences in canonical cards."""
    card = {
        "name": "测试",
        "voice": {
            "self_reference": "常态自称“我”。偶尔使用形态称号。",
            "call_player": "你",
        },
    }

    block = CharacterCardManager.extract_always_injected_block(card)

    # Wrapping a rule sentence produced 自称“常态自称“我”。… — must not reappear.
    assert "自称“常态" not in block
    assert "常态自称“我”。偶尔使用形态称号。" in block
    # Short values are still quoted.
    assert "“你”" in block


def test_voice_stays_inline_when_every_value_is_short():
    card = {
        "name": "测试",
        "voice": {"self_reference": "我", "call_player": "你", "tone": "轻快"},
    }

    block = CharacterCardManager.extract_always_injected_block(card)

    assert "- **说话口吻**：自称“我”，称呼玩家为“你”，语调“轻快”" in block

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
    roll_daily_tone,
    roll_scene_card,
)


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


def test_character_cards(tmp_art_env):
    card_mgr: CharacterCardManager = tmp_art_env["card_mgr"]
    sid = "test-card-sid"

    # Test resolving canonical card
    card, source, _ = card_mgr.resolve_card("流萤", sid)
    assert card is not None
    assert source == "canonical"

    # Test layered prompt extraction
    block = CharacterCardManager.extract_always_injected_block(card)
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
async def test_ledger_insert_if_absent_is_idempotent(tmp_art_env):
    db: ArtDatabase = tmp_art_env["db"]
    sid = "ledger-idem-sid"

    first = await db.add_ledger_entry_if_absent(
        sid, "memory", "共同回忆", "雨声里的拿铁"
    )
    repeat = await db.add_ledger_entry_if_absent(
        sid, "memory", "共同回忆", "雨声里的拿铁"
    )
    other = await db.add_ledger_entry_if_absent(sid, "memory", "共同回忆", "另一件小事")

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


def test_optional_prompt_asset_tolerates_missing_and_blank(tmp_path):
    """An unfilled optional asset reads as empty instead of raising."""
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    assets = ArtAssets(tmp_path / "presets", prompts)

    # Missing file, comment-only document, empty block scalar, and a blank
    # string all read as "" — each key is read once so no reload is involved.
    assert assets.prompts.optional_text("nsfw", "guidance") == ""
    (prompts / "blank.yaml").write_text("# 只有注释\n", encoding="utf-8")
    assert assets.prompts.optional_text("blank", "guidance") == ""
    (prompts / "empty.yaml").write_text("guidance: |\n", encoding="utf-8")
    assert assets.prompts.optional_text("empty", "guidance") == ""
    (prompts / "spaced.yaml").write_text('guidance: "   "\n', encoding="utf-8")
    assert assets.prompts.optional_text("spaced", "guidance") == ""

    (prompts / "filled.yaml").write_text(
        "guidance: |\n  亲密指导正文\n", encoding="utf-8"
    )
    assert assets.prompts.optional_text("filled", "guidance") == "亲密指导正文"

    # A malformed file degrades to empty rather than breaking the foreground.
    (prompts / "bad.yaml").write_text("guidance: [unclosed\n", encoding="utf-8")
    assert assets.prompts.optional_text("bad", "guidance") == ""


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
    tts = _FakeProvider("tts-1", provider_type=ProviderType.TEXT_TO_SPEECH)
    ctx = _FakeContext(
        session_provider=_FakeProvider("session-model"), by_id={"tts-1": tts}
    )
    r = resolve_provider(ctx, _FakeEvent(selected="tts-1"))

    assert r.ok is False
    assert r.source == SOURCE_NONE


def test_resolve_provider_returns_none_when_unresolvable():
    assert resolve_provider(_FakeContext(), _FakeEvent()).source == SOURCE_NONE
    assert (
        resolve_provider(_FakeContext(raises=True), _FakeEvent()).source == SOURCE_NONE
    )
    assert resolve_provider(_FakeContext(), _FakeEvent(umo="")).source == SOURCE_NONE
    # A provider with no id is unusable.
    assert (
        resolve_provider(
            _FakeContext(session_provider=_FakeProvider("")), _FakeEvent()
        ).source
        == SOURCE_NONE
    )


# ---------------------------------------------------------------------------
# Playwright tool contract: handler(event, **kwargs)
# ---------------------------------------------------------------------------


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

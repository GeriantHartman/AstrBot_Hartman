import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from plugins.astrbot_plugin_agentic_RPG.core.canonical_character_loader import (
    CanonicalCharacterRegistry,
)
from plugins.astrbot_plugin_agentic_RPG.core.database import DatabaseManager
from plugins.astrbot_plugin_agentic_RPG.core.prompt_loader import PromptLoader
from plugins.astrbot_plugin_agentic_RPG.core.state_machine import WorldStateMachine
from plugins.astrbot_plugin_agentic_RPG.handlers.npc_character_contract import (
    build_character_contract,
    contract_from_npc,
    extract_creation_contract_spec,
    render_character_contract,
)
from plugins.astrbot_plugin_agentic_RPG.handlers.npc_tools import NpcToolHandler
from plugins.astrbot_plugin_agentic_RPG.handlers.router_supervisor_5 import (
    build_narrative_brief_5,
)
from plugins.astrbot_plugin_agentic_RPG.handlers.tool_executor import (
    ExecutionResult,
    ToolExecEntry,
)


def test_character_contract_preserves_router_creation_spec():
    spec = extract_creation_contract_spec(
        {
            "scene_function": "发布委托的酒馆老板",
            "interaction_policy": "main_interaction",
            "first_appearance_beat": "先展示围裙徽记，再询问玩家要点什么",
            "must_reveal_fields": ["姓名", "围裙徽记"],
            "forbidden_claims": ["不要写成冒险队成员"],
        }
    )
    contract = build_character_contract(
        name="林恩",
        entity_id="npc_lyn",
        npc_type="original",
        role_hint="酒吧老板",
        location="星屑酒馆",
        presence_reason="酒保的岗位就在酒吧",
        profile_text="林恩是星屑酒馆的老板，系着暗红围裙。",
        npc_profile={
            "race": "人类",
            "path": "开拓",
            "appearance": "暗红围裙、城邦徽记、温酒焰",
            "magic": "火系",
            "faction": "星屑酒馆",
        },
        voice_fingerprint={"profile_type": "original"},
        personality_tags=["温和", "细心"],
        creation_spec=spec,
    )

    rendered = render_character_contract(contract, compact=True)

    assert contract["scene_contract"]["scene_function"] == "发布委托的酒馆老板"
    assert contract["world_anchors"]["race"] == "人类"
    assert contract["appearance_anchors"]["appearance"] == "暗红围裙、城邦徽记、温酒焰"
    assert "不要写成冒险队成员" in rendered


def test_character_contract_persists_generation_requirements_and_story_anchors():
    spec = extract_creation_contract_spec(
        {
            "requirements": "她的当前任务必须承接方舟失踪案，保留医疗官身份",
        }
    )
    contract = build_character_contract(
        name="星织",
        npc_type="mhy",
        role_hint="创世圣群医疗官",
        location="织世号医疗隔离层",
        profile_text="星织正在追查隔离层的失踪记录。",
        npc_profile={
            "nationality": "创世圣群",
            "race": "创世圣群天使",
            "faction": "创世圣群医疗序列",
            "background": "她在方舟医疗序列中完成培育与专业训练。",
            "childhood": "幼年期在圣群共同育成舱学习照护与共情。",
            "growth": "成长阶段进入医疗序列并参与星门救援。",
            "current_experience": "正在追查隔离层的失踪记录。",
            "goal": "找到失踪者并修复医疗序列的信任。",
            "core_drive": "不让任何被救回方舟的人再次被遗弃。",
        },
        creation_spec=spec,
    )

    rendered = render_character_contract(contract, compact=False)

    assert contract["scene_contract"]["generation_requirements"].startswith(
        "她的当前任务"
    )
    assert contract["story_anchors"]["current_experience"] == (
        "正在追查隔离层的失踪记录。"
    )
    assert contract["story_anchors"]["core_drive"].startswith("不让任何")
    assert "剧情连续性锚点" in rendered
    assert "不是一次性灵感" in rendered


def test_astera_profile_metadata_keeps_nationality_and_story_fields():
    metadata = NpcToolHandler._merge_original_npc_profile_metadata(
        {
            "source_mode": "原创角色",
            "nationality": "维塔利亚联邦",
            "race": "兽耳族",
            "lineage": "鲁珀谱系",
            "ability_medium": "灾晶器械",
            "faction": "联邦边境救援队",
            "current_experience": "正在风蚀荒原搜救失踪车队。",
        },
        {},
    )

    assert metadata["nationality"] == "维塔利亚联邦"
    assert metadata["lineage"] == "鲁珀谱系"
    assert metadata["ability_medium"] == "灾晶器械"
    assert metadata["current_experience"].endswith("失踪车队。")


@pytest.mark.asyncio
async def test_scene_generation_context_includes_preset_population_rule():
    preset_path = Path(
        "plugins/astrbot_plugin_agentic_RPG/presets/astera-convergence.json"
    )
    preset = json.loads(preset_path.read_text(encoding="utf-8"))

    class FakeState:
        async def get_zone(self, session_id, local_id):
            return SimpleNamespace(
                area_id="area_ship",
                location_name="织世号星门大厅",
                privacy="semi_private",
                environment_desc="星门处于受控开启状态，医疗与警戒序列正在值勤。",
            )

        async def get_area(self, session_id, area_id):
            return SimpleNamespace(
                area_id=area_id,
                name="创世圣群方舟织世号",
                description="创世圣群的白色方舟。",
            )

        async def get_active_area_story(self, session_id, area_id):
            return None

    handler = NpcToolHandler(SimpleNamespace(state=FakeState()))
    context = await handler._build_npc_generation_scene_context(
        "session",
        preset,
        local_id="zone_ship_gate",
        location="织世号星门大厅",
    )

    assert "默认势力/组织: 创世圣群" in context
    assert "方舟常驻人形 NPC 只能是座天使" in context
    assert "不能自动成为圣群成员" in context
    assert "zone privacy: semi_private" in context


@pytest.mark.asyncio
async def test_astera_generation_persists_profile_and_receives_story_context(
    monkeypatch,
):
    preset_path = Path(
        "plugins/astrbot_plugin_agentic_RPG/presets/astera-convergence.json"
    )
    preset = json.loads(preset_path.read_text(encoding="utf-8"))
    captured = {}

    class FakePersonaManager:
        async def get_default_persona_v3(self, umo):
            return {"prompt": "阿斯特拉世界主持人"}

    class FakeLlmContext:
        kb_manager = None
        persona_manager = FakePersonaManager()

        async def llm_generate(self, **kwargs):
            captured["prompt"] = kwargs["prompt"]
            return SimpleNamespace(
                completion_text=json.dumps(
                    {
                        "profile_text": "星织是织世号医疗序列的智天使，正在追查隔离层失踪记录。",
                        "npc_profile": {
                            "source_mode": "原创角色",
                            "nationality": "创世圣群",
                            "race": "创世圣群天使",
                            "path": "智识+繁育",
                            "magic": "源质系",
                            "faction": "创世圣群医疗序列",
                            "background": "她在方舟医疗序列中完成培育。",
                            "current_experience": "正在追查隔离层失踪记录。",
                            "goal": "找回失踪者。",
                            "core_drive": "不放弃任何被救援者。",
                        },
                        "personality_tags": ["温柔", "敏锐", "医疗官"],
                        "secret": "她怀疑失踪事件与内部权限滥用有关。",
                        "attributes": {
                            "STR": 8,
                            "AGI": 10,
                            "INT": 16,
                            "CHA": 14,
                            "LUK": 9,
                        },
                    },
                    ensure_ascii=False,
                )
            )

    class FakeState:
        async def get_zone(self, session_id, local_id):
            return SimpleNamespace(
                area_id="area_ship",
                location_name="织世号医疗隔离层",
                privacy="semi_private",
                environment_desc="隔离层刚发生一宗人员失踪事件。",
            )

        async def get_area(self, session_id, area_id):
            return SimpleNamespace(
                area_id=area_id,
                name="创世圣群方舟织世号",
                description="医疗序列与警戒序列正在联合调查。",
            )

        async def get_active_area_story(self, session_id, area_id):
            return SimpleNamespace(
                story_id="story_missing",
                title="隔离层失踪案",
                current_stage="封锁与排查",
                briefing="一名受保护访客在隔离层失踪。",
            )

        async def get_area_story_tasks(self, session_id, story_id):
            return [
                SimpleNamespace(
                    title="核对医疗权限记录",
                    status="进行中",
                    progress="尚未定位异常授权者",
                    description="",
                )
            ]

        async def get_canon_by_topic(self, session_id, topic):
            return []

        async def get_session_canon(self, session_id, **kwargs):
            return []

        async def get_time_info(self, session_id):
            return {"time_slice": "夜晚"}

    class TestNpcHandler(NpcToolHandler):
        async def _get_session_preset(self, session_id):
            return preset

        async def _get_conversation_summary(self, session_id):
            return "玩家刚要求医疗序列调查隔离层失踪事件。"

        async def _get_provider_id(self, event):
            return "test-provider"

    async def fake_tendency(ctx, session_id):
        return "玩家偏好严肃调查与角色连续性。"

    monkeypatch.setattr(
        "plugins.astrbot_plugin_agentic_RPG.handlers.player_tendency.get_or_infer_tendency",
        fake_tendency,
    )
    ctx = SimpleNamespace(
        state=FakeState(),
        context=FakeLlmContext(),
        prompts=PromptLoader(Path("plugins/astrbot_plugin_agentic_RPG/prompts.yaml")),
        plugin_config={},
    )
    handler = TestNpcHandler(ctx)
    result = await handler._generate_npc_profile_data(
        event=SimpleNamespace(),
        session_id="session",
        npc_name="星织",
        role_hint="创世圣群医疗官",
        location="织世号医疗隔离层",
        npc_type="",
        local_id="zone_medical",
        generation_requirements="保留医疗官身份，身世与失踪案相连。",
    )

    profile = result["voice_fingerprint"]["npc_profile"]
    assert result["voice_fingerprint"]["profile_type"] == "mhy"
    assert profile["faction"] == "创世圣群医疗序列"
    assert profile["current_experience"] == "正在追查隔离层失踪记录。"
    assert "方舟常驻人形 NPC 只能是座天使" in captured["prompt"]
    assert "隔离层失踪案" in captured["prompt"]
    assert "玩家刚要求医疗序列调查" in captured["prompt"]
    assert "保留医疗官身份" in captured["prompt"]


def test_character_contract_renders_scene_location_name_instead_of_internal_id():
    internal_location_id = "446c95999bdd9519"
    persisted = build_character_contract(
        name="琳",
        entity_id="npc_lin",
        npc_type="original",
        role_hint="学院学生",
        location=internal_location_id,
        profile_text="琳是夜语学院的魅魔学生。",
        npc_profile={"race": "魅魔", "appearance": "柔软尾巴与学院制服"},
    )
    npc = SimpleNamespace(
        name="琳",
        entity_id="npc_lin",
        current_local_id=internal_location_id,
        voice_fingerprint={"character_contract": persisted},
        profile_text="琳是夜语学院的魅魔学生。",
        personality_tags=[],
        never_say=[],
    )

    contract = contract_from_npc(
        npc,
        location="夜语学院·炼金术准备室",
        location_id=internal_location_id,
    )
    rendered = render_character_contract(contract, compact=True)

    assert contract["scene_contract"]["location"] == "夜语学院·炼金术准备室"
    assert contract["world_anchors"]["current_location"] == "夜语学院·炼金术准备室"
    assert internal_location_id not in rendered


def test_generate_npcs_exact_name_match_does_not_match_single_character_substring():
    assert NpcToolHandler._is_exact_requested_npc_name("琳", "琳")
    assert NpcToolHandler._is_exact_requested_npc_name("琳", "琳", "临时接待员")
    assert not NpcToolHandler._is_exact_requested_npc_name("艾琳", "琳")
    assert not NpcToolHandler._is_exact_requested_npc_name("琳", "艾琳")


@pytest.mark.asyncio
async def test_vip_canonical_card_overrides_erroneous_original_npc_type():
    preset = json.loads(
        Path("plugins/astrbot_plugin_agentic_RPG/presets/new-elysium.json").read_text(
            encoding="utf-8"
        )
    )

    class TestNpcHandler(NpcToolHandler):
        async def _get_session_preset(self, session_id):
            return preset

    handler = TestNpcHandler(SimpleNamespace())
    resolved_type, canonical_entry = handler._resolve_canonical_generation_mode(
        "维琳娜·艾嘉德",
        "original",
    )
    result = await handler._generate_npc_profile_data(
        event=SimpleNamespace(),
        session_id="session",
        npc_name="维琳娜·艾嘉德",
        role_hint="交换生",
        location="学园城学生公寓大厅",
        npc_type="original",
    )

    assert resolved_type == "mhy"
    assert canonical_entry is not None
    assert canonical_entry["tier"] == "vip"
    assert result["canonical_name"] == "维琳娜·艾嘉德"
    assert result["voice_fingerprint"]["tier"] == "vip"
    assert result["voice_fingerprint"]["profile_type"] == "mhy"
    assert "罗斯凯利法" in result["profile_text"]


def test_canonical_identity_aliases_preserve_distinct_veliona_entity():
    registry = CanonicalCharacterRegistry(
        Path("plugins/astrbot_plugin_agentic_RPG/canonical_characters")
    )
    registry.load_all()

    kiana = registry.lookup_loose("琪亚娜")
    bronya = registry.lookup_loose("布洛妮娅")
    seele = registry.lookup_loose("黑希儿")
    rita = registry.lookup_loose("丽塔・洛丝薇瑟")

    assert kiana is not None
    assert "琪亚娜" in registry.identity_aliases(kiana)
    assert bronya is not None
    assert "布洛妮娅" in registry.identity_aliases(bronya)
    assert rita is not None
    assert rita["name"] == "丽塔·洛丝薇瑟"
    assert registry.lookup_loose("丽塔") is rita
    assert seele is not None
    assert registry.is_distinct_entity_alias(seele, "黑希儿")
    assert registry.is_distinct_entity_alias(seele, "薇莉娜")
    assert "黑希儿" not in registry.identity_aliases(seele)


@pytest.mark.asyncio
async def test_state_exact_npc_lookup_and_canonical_dedup(tmp_path):
    db = DatabaseManager(tmp_path)
    state = WorldStateMachine(db)
    session_id = "default:GroupMessage:npc-alias-test"

    await db.create_game_session(session_id)
    kiana_full = await state.create_npc(session_id, "琪亚娜·卡斯兰娜", "zone")
    await state.create_npc(session_id, "琪亚娜", "zone")
    await state.create_npc(session_id, "希儿·芙乐艾", "zone")
    veliona = await state.create_npc(session_id, "黑希儿", "zone")
    rita_variant = await state.create_npc(session_id, "丽塔・洛丝薇瑟", "zone")

    await state.save_npc_canonical_name(session_id, "琪亚娜", kiana_full.entity_id)
    found = await state.find_npc_by_name(session_id, "琪亚娜")
    assert found is not None
    assert found.entity_id == kiana_full.entity_id
    found_seele = await state.find_npc_by_name(session_id, "希儿")
    assert found_seele is not None
    assert found_seele.name == "希儿·芙乐艾"
    found_rita = await state.find_npc_by_name(session_id, "丽塔")
    assert found_rita is not None
    assert found_rita.entity_id == rita_variant.entity_id
    found_rita_full = await state.find_npc_by_name(session_id, "丽塔·洛丝薇瑟")
    assert found_rita_full is not None
    assert found_rita_full.entity_id == rita_variant.entity_id

    reports = await state.dedup_npcs(session_id)
    report_names = {report["name"] for report in reports}

    assert "琪亚娜·卡斯兰娜" in report_names
    remaining = await db.fetch_all(
        session_id,
        "SELECT name FROM characters WHERE session_id = ? AND is_player = 0",
        (session_id,),
    )
    remaining_names = {row["name"] for row in remaining}
    assert "琪亚娜·卡斯兰娜" in remaining_names
    assert "琪亚娜" not in remaining_names
    assert "希儿·芙乐艾" in remaining_names
    assert "黑希儿" in remaining_names

    veliona_after = await state.find_npc_by_name(session_id, "黑希儿")
    assert veliona_after is not None
    assert veliona_after.entity_id == veliona.entity_id

    await db.close_all()


def test_router_supervisor_brief_includes_npc_contract_for_validation():
    contract = build_character_contract(
        name="林恩",
        entity_id="npc_lyn",
        npc_type="original",
        role_hint="酒吧老板",
        location="星屑酒馆",
        profile_text="林恩是星屑酒馆的老板，系着暗红围裙。",
        npc_profile={"race": "人类", "appearance": "暗红围裙"},
        personality_tags=["温和"],
    )
    package = SimpleNamespace(
        tool_results=[],
        area_block="",
        world_canon_block="",
        story_hooks_block="",
        format_for_req_prompt=lambda: "",
        npc_context="",
        inner_states_block="",
        character_contracts=[contract],
        created_npc_contracts=[contract],
        allowed_npc_names=["林恩"],
        commission_context="",
    )
    exec_result = ExecutionResult(
        entries=[
            ToolExecEntry(
                tool="generate_npcs",
                result={
                    "applied": [
                        {
                            "name": "林恩",
                            "npc_type": "original",
                            "character_contract": contract,
                        }
                    ]
                },
            )
        ]
    )

    brief = build_narrative_brief_5(
        package=package,
        exec_result=exec_result,
        player_message="我走进酒馆点餐",
        style="daily",
    )
    validation_text = brief.render_for_validation()

    assert "npc_character_contracts" in validation_text
    assert "角色事实合同：林恩" in validation_text
    assert "allowed_npc_names" in validation_text
    assert "林恩" in brief.allowed_npc_names
    assert any("未出现在 allowed_npc_names" in item for item in brief.forbidden_claims)


def test_router_supervisor_brief_separates_current_scene_and_offscreen_npcs():
    package = SimpleNamespace(
        tool_results=[],
        area_block="",
        world_canon_block="",
        story_hooks_block="",
        format_for_req_prompt=lambda: "",
        npc_context="",
        inner_states_block="",
        character_contracts=[],
        created_npc_contracts=[],
        allowed_npc_names=["琳"],
        offscreen_npc_names=["诗琴"],
        commission_context="",
    )
    exec_result = ExecutionResult(entries=[])

    brief = build_narrative_brief_5(
        package=package,
        exec_result=exec_result,
        player_message="我看向琳。",
        style="daily",
    )
    validation_text = brief.render_for_validation()

    assert brief.allowed_npc_names == ["琳"]
    assert brief.offscreen_npc_names == ["诗琴"]
    assert "allowed_npc_names" in validation_text
    assert "offscreen_npc_names" in validation_text
    assert any("offscreen_npc_names" in item for item in brief.forbidden_claims)

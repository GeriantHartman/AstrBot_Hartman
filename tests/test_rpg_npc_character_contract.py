from pathlib import Path
from types import SimpleNamespace

import pytest

from plugins.astrbot_plugin_agentic_RPG.core.canonical_character_loader import (
    CanonicalCharacterRegistry,
)
from plugins.astrbot_plugin_agentic_RPG.core.database import DatabaseManager
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

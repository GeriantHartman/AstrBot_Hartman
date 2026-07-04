from types import SimpleNamespace

import pytest

from astrbot.core.agent.tool import FunctionTool, ToolSet
from plugins.astrbot_plugin_agentic_RPG.handlers.hooks import HookHandler
from plugins.astrbot_plugin_agentic_RPG.handlers.narrative_package import (
    _extract_npc_names,
)
from plugins.astrbot_plugin_agentic_RPG.handlers.router_context import (
    build_router_player_status,
)
from plugins.astrbot_plugin_agentic_RPG.handlers.router_supervisor_5 import (
    apply_router_supervisor_5_tool_overrides,
    build_narrative_brief_5,
    build_router_supervisor_5_policy,
    build_validation_prompt_5,
)
from plugins.astrbot_plugin_agentic_RPG.handlers.tool_executor import (
    ExecutionResult,
    ToolExecEntry,
)


class FakeEvent:
    def __init__(self):
        self.unified_msg_origin = "session"
        self.extras = {
            "rpg_pipeline_version": "5.0",
            "rpg_5_0_narrative_brief": "brief",
            "rpg_5_0_validation_brief": "validation brief",
        }

    def get_sender_id(self):
        return "user"

    def get_extra(self, key):
        return self.extras.get(key)

    def set_extra(self, key, value):
        self.extras[key] = value


def _configure_validation(
    handler,
    *,
    mode: str = "strict",
    revalidate_rewrite: bool = True,
) -> None:
    def _get_config_value(key, default=None):
        if key == "router_supervisor_5_validation_mode":
            return mode
        if key == "router_supervisor_5_revalidate_rewrite":
            return revalidate_rewrite
        return default

    handler._get_config_value = _get_config_value


class _PipelineFlagState:
    async def get_global_flag(self, session_id, flag):
        return False


class _DirectorStatusState:
    async def get_player(self, session_id, user_id):
        return SimpleNamespace(
            entity_id="player_1",
            user_id=user_id,
            name="墨",
            current_local_id="",
            companion_npc_ids=[],
            active_director_npcs=["琪亚娜·卡斯兰娜"],
            status_bars={},
            status_effects=[],
            attributes={},
        )

    async def get_inventory(self, *args, **kwargs):
        return []

    async def get_equipped_lightcones(self, *args, **kwargs):
        return []

    async def get_player_skills(self, *args, **kwargs):
        return []

    async def get_player_commissions(self, *args, **kwargs):
        return []

    async def get_all_players(self, *args, **kwargs):
        return []

    async def get_time_info(self, *args, **kwargs):
        return {"day_count": 1}

    async def _load_session_preset(self, *args, **kwargs):
        return {}

    def __getattr__(self, name):
        async def _empty(*args, **kwargs):
            return []

        return _empty


@pytest.mark.asyncio
async def test_pipeline_resolution_uses_4_0_when_legacy_switch_disabled():
    handler = object.__new__(HookHandler)
    handler.ctx = SimpleNamespace(state=_PipelineFlagState())

    def _get_config_value(key, default=None):
        if key == "enable_5_0_router_supervisor_default":
            return False
        if key == "enable_4_0_contract_pipeline":
            return False
        return default

    handler._get_config_value = _get_config_value

    result = await HookHandler._resolve_rpg_pipeline_version(handler, "session")

    assert result == "4.0"


@pytest.mark.asyncio
async def test_router_player_status_hides_director_when_disabled():
    text = await build_router_player_status(
        _DirectorStatusState(),
        "session",
        "user",
        nickname="墨",
        director_enabled=False,
    )
    enabled_text = await build_router_player_status(
        _DirectorStatusState(),
        "session",
        "user",
        nickname="墨",
        director_enabled=True,
    )

    assert "Director" not in text
    assert "Director 中" in enabled_text


def test_router_supervisor_5_npc_maintenance_prompt_uses_milestone_scale():
    handler = object.__new__(HookHandler)

    prompt = HookHandler._build_router5_npc_maintenance_prompt(
        handler,
        reason="move_to_zone",
        turn_index=15,
        npc_lines=['- {"name":"Lin"}'],
        recent_context="recent turn summary",
        narrative_text="latest narrative",
    )

    assert '"delta":25' in prompt
    assert "between -100 and +100" in prompt
    assert "+/-40..75=strong intimacy" in prompt
    assert "Players do not want very slow grinding" in prompt


@pytest.mark.asyncio
async def test_router_supervisor_5_npc_maintenance_allows_larger_milestone_delta():
    handler = object.__new__(HookHandler)
    updated_deltas = []

    player = SimpleNamespace(
        entity_id="player_1",
        name="Player",
        current_local_id="zone_new",
    )
    npc = SimpleNamespace(
        entity_id="npc_lin",
        name="Lin",
        affinity_data={"value": 0, "stage": "陌生"},
    )

    class State:
        async def get_player_affinity(
            self, session_id, npc_entity_id, player_entity_id, shared=False
        ):
            current = sum(updated_deltas)
            return SimpleNamespace(value=current, stage="stage")

        async def update_player_affinity(
            self,
            session_id,
            npc_entity_id,
            player_entity_id,
            delta,
            reason="",
            shared=False,
        ):
            old = sum(updated_deltas)
            new_value = max(-100, min(100, old + delta))
            updated_deltas.append(new_value - old)
            return SimpleNamespace(value=new_value, stage="stage")

        async def update_character_status(self, *args, **kwargs):
            return None

        async def record_visible_event(self, *args, **kwargs):
            return "event"

        async def record_evolution_trigger(self, *args, **kwargs):
            return "trigger"

        async def save_npc_event(self, *args, **kwargs):
            return None

        async def upsert_player_impression(self, *args, **kwargs):
            return None

    handler.ctx = SimpleNamespace(state=State())
    handler._get_config_value = lambda key, default=None: default

    await HookHandler._apply_router5_npc_maintenance_plan(
        handler,
        session_id="session",
        player=player,
        plan={
            "affinity_updates": [
                {"npc": "Lin", "delta": 75, "reason": "strong intimacy milestone"},
                {"npc": "Lin", "delta": 120, "reason": "over limit"},
            ]
        },
        candidate_npcs_by_name={"Lin": npc},
    )

    assert updated_deltas == [75, 25]


@pytest.mark.asyncio
async def test_router_supervisor_5_maintenance_candidates_include_previous_zone():
    handler = object.__new__(HookHandler)
    previous_npc = SimpleNamespace(entity_id="npc_prev", name="Old Friend")
    current_npc = SimpleNamespace(entity_id="npc_new", name="New Face")
    player = SimpleNamespace(
        current_local_id="zone_new",
        companion_npc_ids=[],
    )

    class State:
        async def get_npcs_in_zone(self, session_id, zone_id):
            if zone_id == "zone_old":
                return [previous_npc]
            if zone_id == "zone_new":
                return [current_npc]
            return []

        async def find_npc_by_name(self, session_id, name):
            return None

    handler.ctx = SimpleNamespace(state=State())

    candidates = await HookHandler._collect_router5_npc_maintenance_candidates(
        handler,
        session_id="session",
        player=player,
        previous_zone_ids=["zone_old"],
    )

    assert [npc.name for npc in candidates] == ["Old Friend", "New Face"]

    move_candidates = await HookHandler._collect_router5_npc_maintenance_candidates(
        handler,
        session_id="session",
        player=player,
        previous_zone_ids=["zone_old"],
        include_current_zone=False,
    )

    assert [npc.name for npc in move_candidates] == ["Old Friend"]


def test_router_supervisor_5_validation_prompt_includes_visible_context_excerpt():
    prompt = build_validation_prompt_5(
        brief_text="allowed_npc_names\n- 琳",
        draft_text="琳低声回应。",
        context_text="前文已经确认琳是夜语学院的魅魔学生。",
    )

    assert "[NARRATOR_VISIBLE_CONTEXT_EXCERPT]" in prompt
    assert "前文已经确认琳是夜语学院的魅魔学生" in prompt
    assert "[NARRATOR_DRAFT]" in prompt


def test_router_supervisor_5_policy_loads_separate_rules_file():
    policy = build_router_supervisor_5_policy()

    assert "[RPG_5_0_ROUTER_SUPERVISOR_POLICY]" in policy
    assert "RPG 5.0 Router Supervisor Rules" in policy
    assert "低频" in policy


def test_router_supervisor_5_tool_overrides_clone_without_mutating_original():
    original = FunctionTool(
        name="update_npc_affinities",
        description="old description",
        parameters={
            "type": "object",
            "properties": {
                "updates": {
                    "type": "string",
                    "description": "old updates description",
                }
            },
        },
        handler=None,
    )
    focus_tool = FunctionTool(
        name="mark_interacting_npcs",
        description="old focus description",
        parameters={"type": "object", "properties": {}},
        handler=None,
    )
    passthrough = FunctionTool(
        name="move_to_zone",
        description="move",
        parameters={"type": "object", "properties": {}},
        handler=None,
    )
    tool_set = ToolSet([original, focus_tool, passthrough])

    cloned_set, audit = apply_router_supervisor_5_tool_overrides(tool_set)
    hidden = cloned_set.get_tool("update_npc_affinities")
    focus_clone = cloned_set.get_tool("mark_interacting_npcs")

    assert hidden is None
    assert focus_clone is not focus_tool
    assert "Director" in focus_clone.description
    assert original.description == "old description"
    assert (
        original.parameters["properties"]["updates"]["description"]
        == "old updates description"
    )
    assert cloned_set.get_tool("move_to_zone") is passthrough
    assert "update_npc_affinities" in audit["hidden"]
    assert "mark_interacting_npcs" in audit["applied"]


def test_router_supervisor_5_does_not_promote_scene_presence_to_director_focus():
    intent = SimpleNamespace(
        tools=[
            {
                "name": "mark_interacting_npcs",
                "args": {"npc_names": "风堇"},
            }
        ],
        hint="",
    )
    exec_result = ExecutionResult(
        entries=[
            ToolExecEntry(
                tool="move_to_zone",
                args={},
                result={
                    "npcs_present": [
                        {"name": "爱莉希雅"},
                        {"name": "芭芭拉"},
                    ],
                },
            ),
            ToolExecEntry(
                tool="mark_interacting_npcs",
                args={"npc_names": "风堇"},
                result={"added": ["风堇"]},
            ),
        ]
    )

    legacy_names = _extract_npc_names(
        intent,
        exec_result,
        player_message="我想去找风堇谈谈。",
        zone_npc_names=["爱莉希雅", "芭芭拉"],
        include_scene_presence_as_interacting=True,
    )
    supervisor_names = _extract_npc_names(
        intent,
        exec_result,
        player_message="我想去找风堇谈谈。",
        zone_npc_names=["爱莉希雅", "芭芭拉"],
        include_scene_presence_as_interacting=False,
    )

    assert "芭芭拉" in legacy_names
    assert "芭芭拉" not in supervisor_names
    assert "风堇" in supervisor_names


def test_router_supervisor_5_brief_hides_affinity_numbers_from_narrator():
    package = SimpleNamespace(
        tool_results=[],
        area_block="",
        world_canon_block="",
        story_hooks_block="",
        npc_context="",
        inner_states_block="",
        character_contracts=[],
        created_npc_contracts=[],
        allowed_npc_names=[],
        offscreen_npc_names=[],
        commission_context="",
        format_for_req_prompt=lambda: "",
    )
    exec_result = SimpleNamespace(
        successful=[
            SimpleNamespace(
                tool="update_npc_affinities",
                args={},
                result={
                    "applied": [
                        {
                            "npc_name": "琳",
                            "old_affinity": 0,
                            "new_affinity": 5,
                            "effective_delta": 5,
                            "stage": "友善",
                            "reason": "共同处理炼金事故后建立初步信任",
                        }
                    ]
                },
            )
        ],
        errors=[],
        failed=[],
    )

    brief = build_narrative_brief_5(
        package=package,
        exec_result=exec_result,
        player_message="谢谢琳。",
        style="daily",
    )
    rendered = brief.render()

    assert "关系里程碑已落档" in rendered
    assert "共同处理炼金事故" in rendered
    assert "0→5" not in rendered
    assert "好感 0" not in rendered
    assert "不播报好感数值" in rendered


def test_router_supervisor_5_brief_prefers_current_contract_location():
    current_contract = {
        "schema": "rpg_npc_character_contract_v1",
        "identity": {"name": "风堇", "entity_id": "npc_hyacine"},
        "world_anchors": {"current_location": "昏光医疗站"},
        "scene_contract": {
            "location": "昏光医疗站",
            "scene_function": "为玩家提供谈心和心理安抚",
        },
    }
    stale_created_contract = {
        "schema": "rpg_npc_character_contract_v1",
        "identity": {"name": "风堇", "entity_id": "npc_hyacine"},
        "world_anchors": {"current_location": "星的房间"},
        "scene_contract": {"location": "星的房间"},
    }
    package = SimpleNamespace(
        tool_results=[
            {
                "tool": "generate_npcs",
                "summary": "角色事实合同：风堇；世界锚点: current_location=星的房间",
            },
            {
                "tool": "move_to_zone",
                "summary": "到达了「昏光医疗站」",
            },
        ],
        area_block="当前 zone: 昏光医疗站",
        world_canon_block="",
        story_hooks_block="",
        npc_context="",
        inner_states_block="",
        character_contracts=[current_contract],
        created_npc_contracts=[stale_created_contract],
        allowed_npc_names=["风堇"],
        offscreen_npc_names=[],
        commission_context="",
        behavior_hints=[],
    )
    exec_result = SimpleNamespace(successful=[], errors=[], failed=[])

    brief = build_narrative_brief_5(
        package=package,
        exec_result=exec_result,
        player_message="我想找风堇谈谈。",
        style="daily",
    )
    rendered = brief.render()

    assert "当前 zone: 昏光医疗站" in rendered
    assert "current_location=星的房间" not in rendered
    assert "世界锚点: current_location=昏光医疗站" in rendered


@pytest.mark.asyncio
async def test_router_supervisor_5_keeps_narrator_rewrite_when_validation_still_fails():
    handler = object.__new__(HookHandler)
    _configure_validation(handler, mode="strict", revalidate_rewrite=True)
    event = FakeEvent()
    resp = SimpleNamespace(completion_text="Original narrator draft.")

    async def validate(**kwargs):
        if kwargs["attempt"] == "initial":
            return {
                "verdict": "rewrite",
                "issues": ["draft conflicts with brief"],
                "rewrite_instruction": "rewrite as RP",
            }
        return {
            "verdict": "fallback",
            "issues": ["still imperfect"],
            "rewrite_instruction": "",
        }

    async def rewrite(**kwargs):
        return "Narrator rewrite RP text."

    handler._run_router_supervisor_5_validation = validate
    handler._rewrite_router_supervisor_5_narrative = rewrite

    result = await HookHandler._maybe_validate_router_supervisor_5_response(
        handler, event, resp
    )

    assert resp.completion_text == "Narrator rewrite RP text."
    assert event.get_extra("rpg_narrative_db_body") == "Narrator rewrite RP text."
    assert result["final_decision"] == "rewrite_validation_failed_keep_narrator"
    assert result["player_visible_source"] == "narrator_rewrite"
    assert result["validator_player_visible"] is False
    assert result["router_fallback_player_visible"] is False


@pytest.mark.asyncio
async def test_router_supervisor_5_rewrites_initial_fallback_instead_of_showing_fallback():
    handler = object.__new__(HookHandler)
    _configure_validation(handler, mode="strict", revalidate_rewrite=True)
    event = FakeEvent()
    resp = SimpleNamespace(completion_text="Original narrator draft.")

    async def validate(**kwargs):
        if kwargs["attempt"] == "initial":
            return {
                "verdict": "fallback",
                "issues": ["severe conflict"],
                "rewrite_instruction": "repair as RP",
            }
        return {
            "verdict": "pass",
            "issues": [],
            "rewrite_instruction": "",
        }

    async def rewrite(**kwargs):
        return "Repaired narrator RP text."

    handler._run_router_supervisor_5_validation = validate
    handler._rewrite_router_supervisor_5_narrative = rewrite

    result = await HookHandler._maybe_validate_router_supervisor_5_response(
        handler, event, resp
    )

    assert resp.completion_text == "Repaired narrator RP text."
    assert result["final_decision"] == "fallback_rewritten_by_narrator_passed"
    assert result["player_visible_source"] == "narrator_rewrite"
    assert result["router_fallback_player_visible"] is False


@pytest.mark.asyncio
async def test_router_supervisor_5_keeps_original_narrator_text_when_rewrite_empty():
    handler = object.__new__(HookHandler)
    _configure_validation(handler, mode="strict", revalidate_rewrite=True)
    event = FakeEvent()
    resp = SimpleNamespace(completion_text="Original narrator draft.")

    async def validate(**kwargs):
        return {
            "verdict": "fallback",
            "issues": ["severe conflict"],
            "rewrite_instruction": "repair as RP",
        }

    async def rewrite(**kwargs):
        return ""

    handler._run_router_supervisor_5_validation = validate
    handler._rewrite_router_supervisor_5_narrative = rewrite

    result = await HookHandler._maybe_validate_router_supervisor_5_response(
        handler, event, resp
    )

    assert resp.completion_text == "Original narrator draft."
    assert event.get_extra("rpg_narrative_db_body") is None
    assert result["final_decision"] == "fallback_rewrite_empty_keep_original_narrative"
    assert result["player_visible_source"] == "narrator_draft"
    assert result["router_fallback_player_visible"] is False


@pytest.mark.asyncio
async def test_router_supervisor_5_selective_validation_skips_low_risk_turn():
    handler = object.__new__(HookHandler)
    _configure_validation(handler, mode="selective", revalidate_rewrite=False)
    event = FakeEvent()
    event.set_extra("rpg_router_trace", [])
    resp = SimpleNamespace(completion_text="Quiet RP text.")

    async def validate(**kwargs):
        raise AssertionError("low-risk turn should not call Validator")

    handler._run_router_supervisor_5_validation = validate

    result = await HookHandler._maybe_validate_router_supervisor_5_response(
        handler, event, resp
    )

    assert resp.completion_text == "Quiet RP text."
    assert result["final_decision"] == "validation_skipped_low_risk"
    assert result["initial"]["attempt"] == "skipped"
    assert result["initial"]["skip_reason"] == "selective_low_risk_turn"


@pytest.mark.asyncio
async def test_router_supervisor_5_rewrite_fast_path_skips_second_validation():
    handler = object.__new__(HookHandler)
    _configure_validation(handler, mode="strict", revalidate_rewrite=False)
    event = FakeEvent()
    resp = SimpleNamespace(completion_text="Original narrator draft.")
    attempts = []

    async def validate(**kwargs):
        attempts.append(kwargs["attempt"])
        return {
            "verdict": "rewrite",
            "issues": ["draft conflicts with brief"],
            "rewrite_instruction": "rewrite as RP",
        }

    async def rewrite(**kwargs):
        return "Narrator rewrite RP text."

    handler._run_router_supervisor_5_validation = validate
    handler._rewrite_router_supervisor_5_narrative = rewrite

    result = await HookHandler._maybe_validate_router_supervisor_5_response(
        handler, event, resp
    )

    assert attempts == ["initial"]
    assert resp.completion_text == "Narrator rewrite RP text."
    assert result["rewrite"]["skip_reason"] == "rewrite_revalidation_disabled_fast_path"
    assert result["final_decision"] == "rewrite_applied_unvalidated_fast_path"


@pytest.mark.asyncio
async def test_router_supervisor_5_strips_internal_scaffolding_from_rewrite():
    handler = object.__new__(HookHandler)
    _configure_validation(handler, mode="strict", revalidate_rewrite=False)
    event = FakeEvent()
    resp = SimpleNamespace(completion_text="Original narrator draft.")

    async def validate(**kwargs):
        return {
            "verdict": "rewrite",
            "issues": ["draft misses authorized facts"],
            "rewrite_instruction": "rewrite as RP",
        }

    async def rewrite(**kwargs):
        return (
            "<xiaoai_core>hidden planning</xiaoai_core>\n\n"
            "Visible RP text.\n\n"
            "<监督阶段>hidden supervision note</监督阶段>\n\n"
            "More visible RP text."
        )

    handler._run_router_supervisor_5_validation = validate
    handler._rewrite_router_supervisor_5_narrative = rewrite

    result = await HookHandler._maybe_validate_router_supervisor_5_response(
        handler, event, resp
    )

    assert resp.completion_text == "Visible RP text.\nMore visible RP text."
    assert event.get_extra("rpg_narrative_db_body") == resp.completion_text
    assert "<xiaoai_core>" not in resp.completion_text
    assert "<监督阶段>" not in resp.completion_text
    assert result["internal_scaffolding_stripped"] is True
    assert result["internal_scaffolding_cleanup"]["rewrite"] is True
    assert result["player_visible_source"] == "narrator_rewrite"


@pytest.mark.asyncio
async def test_router_supervisor_5_strips_internal_scaffolding_when_validation_skips():
    handler = object.__new__(HookHandler)
    _configure_validation(handler, mode="selective", revalidate_rewrite=False)
    event = FakeEvent()
    event.set_extra("rpg_router_trace", [])
    resp = SimpleNamespace(
        completion_text=(
            "<监督阶段>hidden low-risk planning</监督阶段>\n\nQuiet RP text."
        )
    )

    async def validate(**kwargs):
        raise AssertionError("low-risk turn should not call Validator")

    handler._run_router_supervisor_5_validation = validate

    result = await HookHandler._maybe_validate_router_supervisor_5_response(
        handler, event, resp
    )

    assert resp.completion_text == "Quiet RP text."
    assert event.get_extra("rpg_narrative_db_body") == "Quiet RP text."
    assert result["final_decision"] == "validation_skipped_low_risk"
    assert result["final_text_changed"] is True
    assert result["internal_scaffolding_cleanup"]["draft"] is True


@pytest.mark.asyncio
async def test_router_supervisor_5_strips_cot_scaffolding_when_validation_skips():
    handler = object.__new__(HookHandler)
    _configure_validation(handler, mode="selective", revalidate_rewrite=False)
    event = FakeEvent()
    event.set_extra("rpg_router_trace", [])
    resp = SimpleNamespace(
        completion_text=(
            "<cot>\n"
            "hidden planning that must never be player-visible\n"
            "</cot>\n"
            "Visible RP text."
        )
    )

    async def validate(**kwargs):
        raise AssertionError("low-risk turn should not call Validator")

    handler._run_router_supervisor_5_validation = validate

    result = await HookHandler._maybe_validate_router_supervisor_5_response(
        handler, event, resp
    )

    assert resp.completion_text == "Visible RP text."
    assert event.get_extra("rpg_narrative_db_body") == "Visible RP text."
    assert "<cot>" not in resp.completion_text
    assert result["final_decision"] == "validation_skipped_low_risk"
    assert result["internal_scaffolding_cleanup"]["draft"] is True


@pytest.mark.asyncio
async def test_router_supervisor_5_recovers_when_cleanup_leaves_only_options():
    handler = object.__new__(HookHandler)
    _configure_validation(handler, mode="selective", revalidate_rewrite=False)
    event = FakeEvent()
    event.set_extra("rpg_router_trace", [])
    resp = SimpleNamespace(
        completion_text=(
            "<xiaoai_core>Visible body was accidentally wrapped as internal "
            "scaffolding and should not disappear.</xiaoai_core>\n\n"
            "---\n\n"
            "[1] option one\n"
            "[2] option two"
        )
    )

    async def validate(**kwargs):
        raise AssertionError("low-risk cleanup recovery should not call Validator")

    async def rewrite(**kwargs):
        return "Recovered RP body.\n\n[1] option one\n[2] option two"

    handler._run_router_supervisor_5_validation = validate
    handler._rewrite_router_supervisor_5_narrative = rewrite

    result = await HookHandler._maybe_validate_router_supervisor_5_response(
        handler, event, resp
    )

    assert (
        resp.completion_text == "Recovered RP body.\n\n[1] option one\n[2] option two"
    )
    assert event.get_extra("rpg_narrative_db_body") == resp.completion_text
    assert result["final_decision"] == "cleanup_recovered_narrator_rewrite"
    assert result["player_visible_source"] == "narrator_rewrite"
    assert result["internal_scaffolding_cleanup_rejected"]["draft"] is True
    assert result["internal_scaffolding_cleanup_recovery"]["draft"] is True

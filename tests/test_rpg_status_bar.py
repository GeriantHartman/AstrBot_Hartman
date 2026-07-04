from types import SimpleNamespace

import pytest

from plugins.astrbot_plugin_agentic_RPG.prompt.assembler import (
    build_rpg_context,
    build_status_bar,
)


class _FakeStatusState:
    def __init__(self, *, materialized: bool):
        self.materialized = materialized
        self.player = SimpleNamespace(
            entity_id="player_1",
            user_id="user",
            name="墨",
            current_local_id="zone_1",
            status_bars={},
            status_effects=[],
            attributes={"STR": 10},
            active_director_npcs=[],
            get_status_text=lambda: "",
        )
        self.kiana = SimpleNamespace(
            entity_id="npc_kiana",
            name="琪亚娜·卡斯兰娜",
            profile_text="天命女武神，活泼直率。",
            personality_tags=["热情"],
            mood="neutral",
            goal="守护同伴",
            wants="吃到今天的早餐",
        )
        self.zone = SimpleNamespace(
            location_name="早餐店",
            area_id="",
            npcs_present=["琪亚娜"],
            get_context_text=lambda: "早餐店里蒸汽升起。",
        )

    async def get_chronicle(self, session_id):
        return ""

    async def get_episode_memories(self, session_id, limit=3):
        return []

    async def get_player(self, session_id, user_id):
        return self.player

    async def get_active_scene_for_player(self, session_id, entity_id):
        return None

    async def get_time_info(self, session_id):
        return {"time_slice": "上午", "day_count": 1}

    async def get_zone(self, session_id, local_id):
        return self.zone

    async def get_area(self, session_id, area_id):
        return None

    async def get_all_scene_summaries(self, session_id):
        return []

    async def get_npcs_in_zone(self, session_id, local_id):
        return [self.kiana] if self.materialized else []

    async def find_npc_by_name(self, session_id, name):
        if name == "琪亚娜":
            return self.kiana
        return None

    async def get_player_affinity(self, *args, **kwargs):
        return SimpleNamespace(value=10, stage="友善")

    async def get_npc_recent_events(self, *args, **kwargs):
        return []

    async def get_inventory(self, *args, **kwargs):
        return []

    async def get_player_level(self, *args, **kwargs):
        return SimpleNamespace(level=1, current_xp=0)

    async def get_equipped_lightcones(self, *args, **kwargs):
        return []

    async def get_player_skills(self, *args, **kwargs):
        return []

    async def get_companion_ids(self, *args, **kwargs):
        return []


class _FakePrompts:
    def get(self, key, **kwargs):
        assert key == "dynamic_context"
        return (
            "NPC:\n{entities_info}\nPLAYER:\n{player_status}\nZONE:\n{zone_info}"
        ).format(**kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("materialized", [True, False])
async def test_status_bar_collapses_npc_aliases_to_persisted_display_name(
    materialized,
):
    text = await build_status_bar(
        _FakeStatusState(materialized=materialized),
        "session",
        "user",
        config_getter=lambda key, default=None: default,
    )

    assert "琪亚娜·卡斯兰娜 (好感: 10 友善)" in text
    assert text.count("好感: 10 友善") == 1
    assert "👥 琪亚娜 (好感: 10 友善)" not in text
    assert " | 琪亚娜 (好感: 10 友善)" not in text


@pytest.mark.asyncio
@pytest.mark.parametrize("materialized", [True, False])
async def test_dynamic_context_collapses_zone_aliases_to_persisted_display_name(
    materialized,
):
    text = await build_rpg_context(
        _FakeStatusState(materialized=materialized),
        _FakePrompts(),
        "session",
        "user",
        config_getter=lambda key, default=None: default,
    )

    assert "琪亚娜·卡斯兰娜" in text
    assert text.count("琪亚娜·卡斯兰娜") == 1
    assert "- 琪亚娜 (背景角色)" not in text

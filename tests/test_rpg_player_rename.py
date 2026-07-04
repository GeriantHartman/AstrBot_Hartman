import pytest

from plugins.astrbot_plugin_agentic_RPG.core.database import DatabaseManager
from plugins.astrbot_plugin_agentic_RPG.core.models import EpisodeMemory
from plugins.astrbot_plugin_agentic_RPG.core.state_machine import (
    VISIBILITY_ZONE,
    WorldStateMachine,
)


@pytest.mark.asyncio
async def test_rename_player_updates_character_and_owned_memory(tmp_path):
    db = DatabaseManager(tmp_path)
    state = WorldStateMachine(db)
    session_id = "default:GroupMessage:rename-test"
    user_id = "user-1"

    await db.create_game_session(session_id)
    player = await state.create_player(session_id, user_id, "错名")
    await state.save_episode_memory(
        EpisodeMemory(
            session_id=session_id,
            player_entity_id=player.entity_id,
            location="活动室",
            time_slice="上午",
            turn_index=7,
            summary_text="错名在活动室完成了任务。",
            created_at=100,
        )
    )
    await state.save_chronicle(session_id, "错名与风堇完成了初次谈心。")
    await state.record_visible_event(
        session_id,
        "test",
        "错名公开完成了任务。",
        visibility=VISIBILITY_ZONE,
        player_entity_id=player.entity_id,
    )

    report = await state.rename_player(session_id, user_id, "星")

    renamed = await state.get_player(session_id, user_id)
    assert report["renamed"] is True
    assert report["old_name"] == "错名"
    assert report["new_name"] == "星"
    assert report["entity_id"] == player.entity_id
    assert renamed is not None
    assert renamed.name == "星"
    assert renamed.entity_id == player.entity_id

    episodes = await state.get_episode_memories(session_id, limit=5)
    assert episodes[0].summary_text == "星在活动室完成了任务。"

    timeline = await state.get_timeline_events(session_id, limit=5)
    assert timeline[0]["summary"] == "星在活动室完成了任务。"

    visible = await db.fetch_all(
        session_id,
        "SELECT content FROM visible_events WHERE session_id = ?",
        (session_id,),
    )
    assert visible[0]["content"] == "星公开完成了任务。"
    assert await state.get_chronicle(session_id) == "星与风堇完成了初次谈心。"

    npc_name_row = await db.fetch_one(
        session_id,
        "SELECT * FROM npc_canonical_names WHERE session_id = ? AND entity_id = ?",
        (session_id, player.entity_id),
    )
    assert npc_name_row is None

    await db.close_all()

"""Per-character table memories for cardroom AI players."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

if TYPE_CHECKING:
    from ..models import GameRoom, Player


PLUGIN_NAME = "astrbot_plugin_new_elysium_cardroom"
LOCAL_TZ = timezone(timedelta(hours=8))


class CharacterMemoryService:
    """Stores short post-game memories by character-card AI."""

    def __init__(self):
        self.base_dir = (
            Path(get_astrbot_plugin_data_path()) / PLUGIN_NAME / "character_memories"
        )
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def load_memories(self, memory_id: str, limit: int = 5) -> list[str]:
        path = self._path(memory_id)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            memories = data.get("memories", [])
            if isinstance(memories, list):
                return [str(item) for item in memories[-limit:]]
        except Exception as exc:
            logger.warning(f"[新爱莉都棋牌室] 读取角色记忆失败 {path}: {exc}")
        return []

    def remember_game(self, player: "Player", room: "GameRoom", result: str) -> None:
        role_name = player.role.display_name if player.role else "未知身份"
        self.remember_tabletop_game(
            player=player,
            room=room,
            game_name="狼人杀",
            result=result,
            detail=f"用{role_name}参加狼人杀",
        )

    def remember_tabletop_game(
        self,
        player: "Player",
        room: "GameRoom",
        game_name: str,
        result: str,
        detail: str = "",
    ) -> None:
        if not player.ai_config or not player.ai_config.memory_id:
            return
        path = self._path(player.ai_config.memory_id)
        memories = self.load_memories(player.ai_config.memory_id, limit=20)
        detail_text = detail or f"参加{game_name}"
        memory = (
            f"{datetime.now(LOCAL_TZ).strftime('%Y-%m-%d %H:%M')} "
            f"在群 {room.group_id} {detail_text}，结局：{result or '未知'}。"
        )
        memories.append(memory)
        payload: dict[str, Any] = {
            "memory_id": player.ai_config.memory_id,
            "skill_id": player.ai_config.skill_id,
            "updated_at": datetime.now(LOCAL_TZ).isoformat(),
            "memories": memories[-20:],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _path(self, memory_id: str) -> Path:
        safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", memory_id)
        return self.base_dir / f"{safe}.json"

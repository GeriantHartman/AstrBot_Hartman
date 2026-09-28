"""SQLite snapshots for active Werewolf cardroom rooms."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from ..models import (
    AIPlayerConfig,
    AIPlayerContext,
    GameConfig,
    GamePhase,
    GameRoom,
    Player,
    Role,
    SpeakingState,
    VoteState,
)
from ..roles import HunterDeathType, HunterState, WitchState


PLUGIN_NAME = "astrbot_plugin_new_elysium_cardroom"
LOCAL_TZ = timezone(timedelta(hours=8))


class RoomStateStorageService:
    """Stores active Werewolf room snapshots outside the plugin code tree."""

    def __init__(self):
        self.base_dir = Path(get_astrbot_plugin_data_path()) / PLUGIN_NAME / "werewolf"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.base_dir / "werewolf_rooms.sqlite3"
        self._init_db()

    def save_room(self, room: GameRoom) -> None:
        if room.phase == GamePhase.FINISHED:
            self.delete_room(room.group_id)
            return

        payload = json.dumps(self._room_to_dict(room), ensure_ascii=False)
        updated_at = datetime.now(LOCAL_TZ).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO werewolf_rooms(group_id, phase, state_json, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(group_id) DO UPDATE SET
                    phase = excluded.phase,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (room.group_id, room.phase.name, payload, updated_at),
            )
            conn.commit()

    def delete_room(self, group_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM werewolf_rooms WHERE group_id = ?", (group_id,))
            conn.commit()

    def load_active_rooms(
        self,
        config: GameConfig,
        audit_service: Any = None,
        behavior_service: Any = None,
    ) -> dict[str, GameRoom]:
        rooms: dict[str, GameRoom] = {}
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT group_id, state_json FROM werewolf_rooms"
            ).fetchall()

        for group_id, state_json in rows:
            try:
                data = json.loads(state_json)
                if self._phase_from_data(data).name == GamePhase.FINISHED.name:
                    self.delete_room(str(group_id))
                    continue
                room = self._room_from_dict(data, config)
                room.audit_service = audit_service
                room.behavior_service = behavior_service
                rooms[str(group_id)] = room
            except Exception as exc:
                logger.warning(f"[狼人杀] 恢复房间 {group_id} 失败: {exc}")
        return rooms

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS werewolf_rooms (
                    group_id TEXT PRIMARY KEY,
                    phase TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _room_to_dict(self, room: GameRoom) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "group_id": room.group_id,
            "creator_id": room.creator_id,
            "msg_origin": room.msg_origin if isinstance(room.msg_origin, str) else "",
            "players": {
                player_id: self._player_to_dict(player)
                for player_id, player in room.players.items()
            },
            "number_to_player": {
                str(number): player_id
                for number, player_id in room.number_to_player.items()
            },
            "phase": room.phase.name,
            "current_round": room.current_round,
            "is_first_night": room.is_first_night,
            "last_killed_id": room.last_killed_id,
            "seer_checked": room.seer_checked,
            "wolf_last_chat_time": room.wolf_last_chat_time,
            "wolf_ai_voted": room.wolf_ai_voted,
            "wolf_ai_chatted": room.wolf_ai_chatted,
            "day_ai_voted": room.day_ai_voted,
            "vote_result_processing": room.vote_result_processing,
            "vote_discussion": list(room.vote_discussion),
            "last_words_from_vote": room.last_words_from_vote,
            "witch_state": self._witch_state_to_dict(room.witch_state),
            "hunter_state": self._hunter_state_to_dict(room.hunter_state),
            "vote_state": self._vote_state_to_dict(room.vote_state),
            "speaking_state": self._speaking_state_to_dict(room.speaking_state),
            "banned_player_ids": sorted(room.banned_player_ids),
            "temp_admin_ids": sorted(room.temp_admin_ids),
            "game_log": list(room.game_log)[-200:],
            "audit_id": room.audit_id,
            "audit_log_path": room.audit_log_path,
            "audit_summary_path": room.audit_summary_path,
        }

    def _room_from_dict(self, data: dict[str, Any], config: GameConfig) -> GameRoom:
        room = GameRoom(
            group_id=str(data.get("group_id") or ""),
            creator_id=str(data.get("creator_id") or ""),
            config=config,
            msg_origin=str(data.get("msg_origin") or ""),
            bot=None,
        )
        room.players = {
            str(player_id): self._player_from_dict(player_data)
            for player_id, player_data in dict(data.get("players") or {}).items()
        }
        room.number_to_player = {
            int(number): str(player_id)
            for number, player_id in dict(data.get("number_to_player") or {}).items()
            if str(number).isdigit()
        }
        room.phase = self._phase_from_data(data)
        room.current_round = int(data.get("current_round") or 0)
        room.is_first_night = bool(data.get("is_first_night", True))
        room.last_killed_id = self._optional_str(data.get("last_killed_id"))
        room.seer_checked = bool(data.get("seer_checked", False))
        room.wolf_last_chat_time = self._optional_float(data.get("wolf_last_chat_time"))
        room.wolf_ai_voted = bool(data.get("wolf_ai_voted", False))
        room.wolf_ai_chatted = bool(data.get("wolf_ai_chatted", False))
        room.wolf_ai_vote_task = None
        room.wolf_ai_process_task = None
        room.day_ai_voted = bool(data.get("day_ai_voted", False))
        room.vote_result_processing = bool(data.get("vote_result_processing", False))
        room.vote_discussion = list(data.get("vote_discussion") or [])
        room.last_words_from_vote = bool(data.get("last_words_from_vote", False))
        room.witch_state = self._witch_state_from_dict(data.get("witch_state"))
        room.hunter_state = self._hunter_state_from_dict(data.get("hunter_state"))
        room.vote_state = self._vote_state_from_dict(data.get("vote_state"))
        room.speaking_state = self._speaking_state_from_dict(
            data.get("speaking_state")
        )
        room.banned_player_ids = {
            str(player_id) for player_id in data.get("banned_player_ids", [])
        }
        room.temp_admin_ids = {
            str(player_id) for player_id in data.get("temp_admin_ids", [])
        }
        room.timer_task = None
        room.game_log = [str(item) for item in data.get("game_log", [])][-200:]
        room.audit_id = str(data.get("audit_id") or "")
        room.audit_log_path = str(data.get("audit_log_path") or "")
        room.audit_summary_path = str(data.get("audit_summary_path") or "")
        return room

    def _player_to_dict(self, player: Player) -> dict[str, Any]:
        return {
            "id": player.id,
            "name": player.name,
            "number": player.number,
            "role": player.role.value if player.role else "",
            "is_alive": player.is_alive,
            "original_card": player.original_card,
            "is_ai": player.is_ai,
            "ai_config": self._ai_config_to_dict(player.ai_config),
            "ai_context": self._ai_context_to_dict(player.ai_context),
        }

    def _player_from_dict(self, data: dict[str, Any]) -> Player:
        role = None
        role_value = data.get("role")
        if role_value:
            try:
                role = Role(role_value)
            except ValueError:
                role = None

        return Player(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or ""),
            number=int(data.get("number") or 0),
            role=role,
            is_alive=bool(data.get("is_alive", True)),
            original_card=str(data.get("original_card") or ""),
            is_ai=bool(data.get("is_ai", False)),
            ai_config=self._ai_config_from_dict(data.get("ai_config")),
            ai_context=self._ai_context_from_dict(data.get("ai_context")),
        )

    @staticmethod
    def _ai_config_to_dict(config: AIPlayerConfig | None) -> dict[str, Any] | None:
        if not config:
            return None
        return {
            "name": config.name,
            "model_id": config.model_id,
            "personality": config.personality,
            "max_retries": config.max_retries,
            "retry_delay": config.retry_delay,
            "skill_id": config.skill_id,
            "memory_id": config.memory_id,
        }

    @staticmethod
    def _ai_config_from_dict(data: Any) -> AIPlayerConfig | None:
        if not isinstance(data, dict):
            return None
        return AIPlayerConfig(
            name=str(data.get("name") or "AI"),
            model_id=str(data.get("model_id") or ""),
            personality=str(data.get("personality") or ""),
            max_retries=int(data.get("max_retries") or 3),
            retry_delay=float(data.get("retry_delay") or 1.0),
            skill_id=str(data.get("skill_id") or ""),
            memory_id=str(data.get("memory_id") or ""),
        )

    @staticmethod
    def _ai_context_to_dict(context: AIPlayerContext | None) -> dict[str, Any] | None:
        return dict(vars(context)) if context else None

    @staticmethod
    def _ai_context_from_dict(data: Any) -> AIPlayerContext | None:
        if not isinstance(data, dict):
            return None
        context = AIPlayerContext()
        for key, value in data.items():
            if hasattr(context, key):
                setattr(context, key, value)
        return context

    @staticmethod
    def _witch_state_to_dict(state: WitchState) -> dict[str, Any]:
        return {
            "poison_used": state.poison_used,
            "antidote_used": state.antidote_used,
            "saved_player_id": state.saved_player_id,
            "poisoned_player_id": state.poisoned_player_id,
            "has_acted": state.has_acted,
        }

    @staticmethod
    def _witch_state_from_dict(data: Any) -> WitchState:
        data = data if isinstance(data, dict) else {}
        return WitchState(
            poison_used=bool(data.get("poison_used", False)),
            antidote_used=bool(data.get("antidote_used", False)),
            saved_player_id=RoomStateStorageService._optional_str(
                data.get("saved_player_id")
            ),
            poisoned_player_id=RoomStateStorageService._optional_str(
                data.get("poisoned_player_id")
            ),
            has_acted=bool(data.get("has_acted", False)),
        )

    @staticmethod
    def _hunter_state_to_dict(state: HunterState) -> dict[str, Any]:
        return {
            "has_shot": state.has_shot,
            "pending_shot_player_id": state.pending_shot_player_id,
            "death_type": state.death_type.value if state.death_type else "",
        }

    @staticmethod
    def _hunter_state_from_dict(data: Any) -> HunterState:
        data = data if isinstance(data, dict) else {}
        death_type = None
        if data.get("death_type"):
            try:
                death_type = HunterDeathType(str(data.get("death_type")))
            except ValueError:
                death_type = None
        return HunterState(
            has_shot=bool(data.get("has_shot", False)),
            pending_shot_player_id=RoomStateStorageService._optional_str(
                data.get("pending_shot_player_id")
            ),
            death_type=death_type,
        )

    @staticmethod
    def _vote_state_to_dict(state: VoteState) -> dict[str, Any]:
        return {
            "night_votes": dict(state.night_votes),
            "day_votes": dict(state.day_votes),
            "pk_players": list(state.pk_players),
            "is_pk_vote": state.is_pk_vote,
        }

    @staticmethod
    def _vote_state_from_dict(data: Any) -> VoteState:
        data = data if isinstance(data, dict) else {}
        return VoteState(
            night_votes={
                str(voter): str(target)
                for voter, target in dict(data.get("night_votes") or {}).items()
            },
            day_votes={
                str(voter): str(target)
                for voter, target in dict(data.get("day_votes") or {}).items()
            },
            pk_players=[str(item) for item in data.get("pk_players", [])],
            is_pk_vote=bool(data.get("is_pk_vote", False)),
        )

    @staticmethod
    def _speaking_state_to_dict(state: SpeakingState) -> dict[str, Any]:
        return {
            "order": list(state.order),
            "current_index": state.current_index,
            "current_speaker_id": state.current_speaker_id,
            "current_speech": list(state.current_speech),
        }

    @staticmethod
    def _speaking_state_from_dict(data: Any) -> SpeakingState:
        data = data if isinstance(data, dict) else {}
        return SpeakingState(
            order=[str(item) for item in data.get("order", [])],
            current_index=int(data.get("current_index") or 0),
            current_speaker_id=RoomStateStorageService._optional_str(
                data.get("current_speaker_id")
            ),
            current_speech=[str(item) for item in data.get("current_speech", [])],
        )

    @staticmethod
    def _phase_from_data(data: dict[str, Any]) -> GamePhase:
        phase_name = str(data.get("phase") or GamePhase.WAITING.name)
        if phase_name in GamePhase.__members__:
            return GamePhase[phase_name]
        for phase in GamePhase:
            if phase.value == phase_name:
                return phase
        return GamePhase.WAITING

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value is None:
            return None
        value = str(value)
        return value or None

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        return float(value)

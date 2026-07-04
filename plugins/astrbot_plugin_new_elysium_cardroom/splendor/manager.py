"""Splendor room coordinator."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from astrbot.api import logger

from ..models import AIPlayerConfig, GameConfig
from ..services.character_memory_service import CharacterMemoryService
from ..services.character_relationship_service import CharacterRelationshipService
from ..services.character_skill_service import CharacterSkillService
from ..services.message_service import MessageService
from ..utils import table_name
from .ai import SplendorAIService
from .constants import TOKEN_LIMIT
from .engine import ActionResult, SplendorEngine
from .models import (
    PHASE_FINISHED,
    PHASE_PLAYING,
    PHASE_WAITING,
    SplendorPlayer,
    SplendorRoom,
)
from .storage import SplendorStorage
from .text_ui import SplendorTextUI

if TYPE_CHECKING:
    from astrbot.api.star import Context


class SplendorManager:
    """Coordinates Splendor rooms and services."""

    AI_EMOJIS = ["◇", "◆", "✦", "✧", "✩", "✪"]

    def __init__(
        self,
        context: Context,
        config: GameConfig,
        message_service: MessageService,
        character_skill_service: CharacterSkillService,
        character_relationship_service: CharacterRelationshipService,
        character_memory_service: CharacterMemoryService,
    ):
        self.context = context
        self.config = config
        self.message_service = message_service
        self.character_skill_service = character_skill_service
        self.character_relationship_service = character_relationship_service
        self.character_memory_service = character_memory_service
        self.engine = SplendorEngine()
        self.text_ui = SplendorTextUI(self.engine)
        self.ai_service = SplendorAIService(context, self.engine, self.text_ui)
        self.storage = SplendorStorage()
        self._processing_ai_rooms: set[str] = set()
        self.rooms: dict[str, SplendorRoom] = self.storage.load_active_rooms()
        if self.rooms:
            logger.info(f"[璀璨宝石] 已恢复 {len(self.rooms)} 个活跃房间")

    def get_room(self, group_id: str) -> SplendorRoom | None:
        return self.rooms.get(group_id)

    def room_exists(self, group_id: str) -> bool:
        room = self.rooms.get(group_id)
        return bool(room and room.phase in {PHASE_WAITING, PHASE_PLAYING})

    def attach_event_transport(self, room: SplendorRoom, msg_origin, bot) -> None:
        previous_origin = room.msg_origin
        room.msg_origin = msg_origin
        room.bot = bot
        if msg_origin and msg_origin != previous_origin:
            self.storage.save_room(room)

    def persist_active_rooms(self) -> None:
        for room in self.rooms.values():
            if room.phase in {PHASE_WAITING, PHASE_PLAYING}:
                self.storage.save_room(room)

    def create_room(
        self,
        group_id: str,
        creator_id: str,
        target_players: int,
        msg_origin,
        bot,
    ) -> SplendorRoom:
        room = SplendorRoom(
            group_id=group_id,
            creator_id=creator_id,
            target_players=target_players,
            msg_origin=msg_origin,
            bot=bot,
            seed=random.SystemRandom().randint(1, 2_000_000_000),
        )
        self.rooms[group_id] = room
        self.storage.save_room(room)
        logger.info(f"[璀璨宝石] 群 {group_id} 创建 {target_players} 人房间")
        return room

    def add_human_player(
        self, room: SplendorRoom, player_id: str, player_name: str
    ) -> SplendorPlayer:
        player = SplendorPlayer(id=player_id, name=player_name)
        room.add_player(player)
        self.storage.save_room(room)
        return player

    def add_character_ai(
        self, room: SplendorRoom, skill_id: str
    ) -> SplendorPlayer | None:
        profile = self.character_skill_service.get_profile(skill_id, mode="splendor")
        if not profile:
            return None
        if self.room_has_skill(room, skill_id):
            return None

        current_ai_count = len(
            [player for player in room.players.values() if player.is_ai]
        )
        marker = self.AI_EMOJIS[current_ai_count % len(self.AI_EMOJIS)]
        ai_player_id = f"splendor_ai_{skill_id}"
        ai_config = AIPlayerConfig(
            name=profile.display_name,
            model_id=self.config.ai_player_model,
            personality=profile.prompt,
            skill_id=skill_id,
            memory_id=f"{room.group_id}:{ai_player_id}:splendor:{skill_id}",
        )
        player = SplendorPlayer(
            id=ai_player_id,
            name=f"{marker}{profile.display_name}",
            is_ai=True,
            ai_config=ai_config,
        )
        room.add_player(player)
        self.storage.save_room(room)
        return player

    def fill_character_ai(self, room: SplendorRoom) -> list[SplendorPlayer]:
        added: list[SplendorPlayer] = []
        roster = self.character_skill_service.parse_roster(
            self.config.default_ai_skill_roster
        )
        profiles = self.character_skill_service.list_profiles()
        profiles_by_id = {profile.skill_id: profile for profile in profiles}
        ordered_skill_ids = [
            skill_id for skill_id in roster if skill_id in profiles_by_id
        ] + [
            profile.skill_id
            for profile in profiles
            if profile.skill_id not in set(roster)
        ]
        for skill_id in ordered_skill_ids:
            if room.is_full:
                break
            if self.room_has_skill(room, skill_id):
                continue
            player = self.add_character_ai(room, skill_id)
            if player:
                added.append(player)
        return added

    def remove_ai(self, room: SplendorRoom, selector: str) -> SplendorPlayer | None:
        target = selector.strip().lower()
        for player in list(room.players.values()):
            if not player.is_ai:
                continue
            names = {player.id.lower(), player.name.lower(), table_name(player).lower()}
            if player.ai_config:
                names.add(player.ai_config.name.lower())
                names.add(player.ai_config.skill_id.lower())
            if target in names or any(target in name for name in names):
                room.remove_player(player.id)
                self.storage.save_room(room)
                return player
        return None

    async def start_game(self, room: SplendorRoom) -> ActionResult:
        result = self.engine.start_game(room)
        self.storage.save_room(room)
        return result

    async def apply_human_action(
        self, room: SplendorRoom, player_id: str, action: dict
    ) -> ActionResult:
        result = self.engine.apply_action(room, player_id, action)
        self.storage.save_room(room)
        if result.ok:
            await self._handle_finished_if_needed(room, result)
        return result

    async def process_ai_turns(self, room: SplendorRoom) -> None:
        if room.group_id in self._processing_ai_rooms:
            return
        self._processing_ai_rooms.add(room.group_id)
        try:
            await self._process_ai_turns_locked(room)
        finally:
            self._processing_ai_rooms.discard(room.group_id)

    async def _process_ai_turns_locked(self, room: SplendorRoom) -> None:
        safety = 0
        while room.phase == PHASE_PLAYING and safety < 16:
            current = room.current_player
            if not current or not current.is_ai:
                break
            safety += 1
            action, speech, raw_response = await self.ai_service.decide_action(
                current,
                room,
                relationship_hints=self.character_relationship_service.hints_for(
                    current, room
                ),
                memories=self.character_memory_service.load_memories(
                    current.ai_config.memory_id if current.ai_config else ""
                ),
            )
            if not action:
                await self.message_service.send_group_message(
                    room, f"{current.display_name} 一时没有想好，牌局暂停等待人工处理。"
                )
                break
            result = self.engine.apply_action(room, current.id, action)
            if not result.ok:
                fallback = self._force_simple_ai_action(current, room)
                result = self.engine.apply_action(room, current.id, fallback)
            self.storage.save_room(room)
            action_text = result.text or "完成行动。"
            status_text = ""
            if result.ok and room.phase == PHASE_PLAYING and not result.game_finished:
                status_text = "\n\n" + self.public_status(room)
            if speech:
                await self.message_service.send_group_message(
                    room,
                    f"{current.display_name}：{speech}\n{action_text}{status_text}",
                )
            else:
                await self.message_service.send_group_message(
                    room, f"{action_text}{status_text}"
                )
            if raw_response:
                logger.debug(f"[璀璨宝石AI] {current.name} 原始回复: {raw_response}")
            await self._handle_finished_if_needed(room, result)
        if safety >= 16:
            logger.warning(f"[璀璨宝石] 群 {room.group_id} AI 连续行动达到保护上限")

    async def end_room(self, group_id: str) -> bool:
        room = self.rooms.pop(group_id, None)
        if not room:
            return False
        room.phase = PHASE_FINISHED
        self.storage.mark_finished(room)
        return True

    def public_status(self, room: SplendorRoom, viewer_id: str = "") -> str:
        return self.text_ui.render_room(room, viewer_id=viewer_id)

    def waiting_status(self, room: SplendorRoom) -> str:
        return self.text_ui.render_waiting_room(room)

    def help_text(self) -> str:
        return self.text_ui.render_help()

    def score_summary(self, room: SplendorRoom) -> str:
        lines = ["璀璨宝石最终分数："]
        for player in sorted(
            room.players.values(), key=lambda item: item.number or 999
        ):
            lines.append(
                f"- {player.display_name}: {self.engine.score_for(player)}分，"
                f"买牌 {player.card_count}，贵族 {len(player.nobles)}"
            )
        return "\n".join(lines)

    async def _handle_finished_if_needed(
        self, room: SplendorRoom, result: ActionResult
    ) -> None:
        if not result.game_finished and room.phase != PHASE_FINISHED:
            return
        summary = self.score_summary(room)
        await self.message_service.send_group_message(room, summary)
        self._write_character_memories(room)
        self.storage.mark_finished(room)
        self.rooms.pop(room.group_id, None)

    def _write_character_memories(self, room: SplendorRoom) -> None:
        winner_names = "、".join(
            room.players[player_id].display_name for player_id in room.winner_ids
        )
        result = f"胜者：{winner_names}" if winner_names else "游戏结束"
        for player in room.players.values():
            if not player.is_ai:
                continue
            detail = (
                f"参加璀璨宝石，最终 {self.engine.score_for(player)} 分，"
                f"买牌 {player.card_count} 张，贵族 {len(player.nobles)} 位"
            )
            self.character_memory_service.remember_tabletop_game(
                player=player,
                room=room,
                game_name="璀璨宝石",
                result=result,
                detail=detail,
            )

    def _force_simple_ai_action(
        self, player: SplendorPlayer, room: SplendorRoom
    ) -> dict:
        actions = self.engine.available_actions(room, player.id)
        if not actions:
            return {}
        for action in actions:
            if action["action"] in {"choose_noble", "discard"}:
                return action
        for action in actions:
            if action["action"] == "buy":
                return action
        for action in actions:
            if action["action"] == "take":
                return action
        return actions[0]

    @staticmethod
    def room_has_skill(room: SplendorRoom, skill_id: str) -> bool:
        return any(
            player.is_ai and player.ai_config and player.ai_config.skill_id == skill_id
            for player in room.players.values()
        )

    @staticmethod
    def token_limit_text() -> str:
        return f"回合结束最多保留 {TOKEN_LIMIT} 枚宝石。"

"""Splendor command handlers."""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from astrbot.api.event import AstrMessageEvent

from .base import BaseCommandHandler
from ..splendor.constants import parse_color
from ..splendor.models import PHASE_PLAYING, PHASE_WAITING
from ..utils import cmd, table_name

if TYPE_CHECKING:
    from ..services import GameManager
    from ..splendor import SplendorManager
    from ..splendor.models import SplendorRoom
    from ..services.character_skill_service import CharacterSkillProfile


class SplendorCommandHandler(BaseCommandHandler):
    """Handles Splendor setup, query, and turn commands."""

    def __init__(
        self,
        game_manager: "GameManager",
        splendor_manager: "SplendorManager",
    ):
        super().__init__(game_manager)
        self.splendor_manager = splendor_manager

    async def create_room(self, event: AstrMessageEvent) -> AsyncGenerator:
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("请在群聊中使用此命令。")
            return
        if self.game_manager.room_exists(group_id):
            yield event.plain_result("当前群已有狼人杀房间，请先结束现有游戏。")
            return
        if self.splendor_manager.room_exists(group_id):
            yield event.plain_result("当前群已有璀璨宝石房间。")
            return

        args = self._extract_command_args(event, ["创建璀璨房间", "创建璀璨"])
        target_players = self._parse_player_count(args) or 4
        if target_players not in {2, 3, 4}:
            yield event.plain_result("璀璨宝石支持 2-4 人，请使用 2、3 或 4。")
            return

        room = self.splendor_manager.create_room(
            group_id=group_id,
            creator_id=event.get_sender_id(),
            target_players=target_players,
            msg_origin=event.unified_msg_origin,
            bot=event.bot,
        )
        yield event.plain_result(
            "新爱莉都棋牌室摆好了《璀璨宝石》。\n\n"
            f"人数：{target_players} 人\n"
            "原则：和角色本人一起玩，角色声纹与身份感优先于胜率。\n\n"
            f"加入：{cmd('加入璀璨')}\n"
            f"查看角色AI：{cmd('AI角色列表')}\n"
            f"添加角色AI：{cmd('璀璨加入角色AI')} 名字/序号\n"
            f"补满：{cmd('璀璨补满AI')}\n"
            f"开始：{cmd('开始璀璨')}\n\n"
            + self.splendor_manager.waiting_status(room)
        )

    async def join_room(self, event: AstrMessageEvent) -> AsyncGenerator:
        room = self._waiting_room_for_event(event)
        if not room:
            yield event.plain_result(
                f"当前群没有等待中的璀璨宝石房间，请先使用 {cmd('创建璀璨房间')}"
            )
            return
        player_id = event.get_sender_id()
        if room.is_player_in_room(player_id):
            yield event.plain_result("你已经在这局璀璨宝石中了。")
            return
        if room.is_full:
            yield event.plain_result(f"房间已满（{room.player_count}/{room.target_players}）。")
            return
        player = self.splendor_manager.add_human_player(
            room, player_id, self.get_player_name(event)
        )
        yield event.plain_result(
            f"{player.name} 加入璀璨宝石。\n"
            f"当前人数：{room.player_count}/{room.target_players}"
        )

    async def join_character_ai(self, event: AstrMessageEvent) -> AsyncGenerator:
        room = self._waiting_room_for_event(event)
        if not room:
            yield event.plain_result("当前群没有等待中的璀璨宝石房间。")
            return
        if room.is_full:
            yield event.plain_result(f"房间已满（{room.player_count}/{room.target_players}）。")
            return
        selector = self._extract_command_args(event, ["璀璨加入角色AI", "璀璨添加角色AI"])
        if not selector:
            yield event.plain_result(f"请指定角色AI。示例：{cmd('璀璨加入角色AI')} 三月七")
            return
        profile = self._match_character_profile(selector)
        if not profile:
            yield event.plain_result(
                f"未找到角色AI：{selector}\n请使用 {cmd('AI角色列表')} 查看可用角色。"
            )
            return
        if self.splendor_manager.room_has_skill(room, profile.skill_id):
            yield event.plain_result(f"{profile.display_name} 已在房间中。")
            return
        player = self.splendor_manager.add_character_ai(room, profile.skill_id)
        if not player:
            yield event.plain_result(f"添加角色AI失败：{profile.display_name}")
            return
        adapter = (
            "有璀璨适配"
            if self.game_manager.character_skill_service.has_tabletop_adapter(
                profile.skill_id, mode="splendor"
            )
            else "使用通用角色卡裁剪"
        )
        yield event.plain_result(
            f"{table_name(player)} 加入璀璨宝石。\n"
            f"角色卡：{profile.display_name}（{adapter}）\n"
            f"当前人数：{room.player_count}/{room.target_players}"
        )

    async def fill_character_ai(self, event: AstrMessageEvent) -> AsyncGenerator:
        room = self._waiting_room_for_event(event)
        if not room:
            yield event.plain_result("当前群没有等待中的璀璨宝石房间。")
            return
        added = self.splendor_manager.fill_character_ai(room)
        if not added:
            yield event.plain_result(
                f"没有新增角色AI。当前人数：{room.player_count}/{room.target_players}"
            )
            return
        yield event.plain_result(
            "已补入璀璨宝石角色AI：\n"
            + "\n".join(f"- {table_name(player)}" for player in added)
            + f"\n\n当前人数：{room.player_count}/{room.target_players}"
        )

    async def kick_ai_player(self, event: AstrMessageEvent) -> AsyncGenerator:
        room = self._waiting_room_for_event(event)
        if not room:
            yield event.plain_result("当前群没有等待中的璀璨宝石房间。")
            return
        selector = self._extract_command_args(event, ["踢出璀璨AI", "移除璀璨AI"])
        if not selector:
            yield event.plain_result("请指定要移除的璀璨 AI 名字或角色卡。")
            return
        player = self.splendor_manager.remove_ai(room, selector)
        if not player:
            yield event.plain_result(f"未找到璀璨 AI：{selector}")
            return
        yield event.plain_result(
            f"已移除 {table_name(player)}。\n"
            f"当前人数：{room.player_count}/{room.target_players}"
        )

    async def start_game(self, event: AstrMessageEvent) -> AsyncGenerator:
        room = self._room_for_event(event)
        if not room:
            yield event.plain_result("当前群没有璀璨宝石房间。")
            return
        if event.get_sender_id() != room.creator_id:
            yield event.plain_result("只有房主才能开始璀璨宝石。")
            return
        if room.phase != PHASE_WAITING:
            yield event.plain_result("这局璀璨宝石已经开始。")
            return

        result = await self.splendor_manager.start_game(room)
        if not result.ok:
            yield event.plain_result(result.text)
            return
        yield event.plain_result(result.text + "\n\n" + self.splendor_manager.public_status(room))
        await self.splendor_manager.process_ai_turns(room)

    async def end_game(self, event: AstrMessageEvent) -> AsyncGenerator:
        room = self._room_for_event(event)
        if not room:
            yield event.plain_result("当前群没有璀璨宝石房间。")
            return
        if event.get_sender_id() != room.creator_id:
            yield event.plain_result("只有房主才能结束璀璨宝石。")
            return
        await self.splendor_manager.end_room(room.group_id)
        yield event.plain_result("璀璨宝石房间已结束。")

    async def show_status(self, event: AstrMessageEvent) -> AsyncGenerator:
        room = self._room_for_event(event)
        if not room:
            yield event.plain_result("当前群没有璀璨宝石房间。")
            return
        yield event.plain_result(
            self.splendor_manager.public_status(room, viewer_id=event.get_sender_id())
        )

    async def show_help(self, event: AstrMessageEvent) -> AsyncGenerator:
        yield event.plain_result(self.splendor_manager.help_text())

    async def take_tokens(self, event: AstrMessageEvent) -> AsyncGenerator:
        args = self._extract_command_args(event, ["拿宝石"])
        colors = self._parse_colors(args)
        async for result in self._apply_turn_action(
            event, {"action": "take", "colors": colors}
        ):
            yield result

    async def reserve_card(self, event: AstrMessageEvent) -> AsyncGenerator:
        selector = self._extract_command_args(event, ["保留牌"])
        async for result in self._apply_turn_action(
            event, {"action": "reserve", "selector": selector}
        ):
            yield result

    async def buy_card(self, event: AstrMessageEvent) -> AsyncGenerator:
        selector = self._extract_command_args(event, ["购买牌", "买牌"])
        async for result in self._apply_turn_action(
            event, {"action": "buy", "selector": selector}
        ):
            yield result

    async def choose_noble(self, event: AstrMessageEvent) -> AsyncGenerator:
        selector = self._extract_command_args(event, ["选择贵族"])
        async for result in self._apply_turn_action(
            event, {"action": "choose_noble", "noble_id": selector}
        ):
            yield result

    async def discard_tokens(self, event: AstrMessageEvent) -> AsyncGenerator:
        args = self._extract_command_args(event, ["丢宝石", "弃宝石"])
        colors = self._parse_colors(args)
        async for result in self._apply_turn_action(
            event, {"action": "discard", "colors": colors}
        ):
            yield result

    async def _apply_turn_action(
        self, event: AstrMessageEvent, action: dict
    ) -> AsyncGenerator:
        room = self._room_for_event(event)
        if not room:
            yield event.plain_result("当前群没有进行中的璀璨宝石。")
            return
        if room.phase != PHASE_PLAYING:
            yield event.plain_result("璀璨宝石还没有开始。")
            return
        player_id = event.get_sender_id()
        current = room.current_player
        pending_player_id = room.pending_discard_player_id or room.pending_noble_player_id
        actor_id = pending_player_id or (current.id if current else "")
        if actor_id != player_id:
            actor = room.players.get(actor_id)
            yield event.plain_result(
                f"现在轮到 {actor.display_name if actor else '当前玩家'} 行动。"
            )
            return
        player = room.players.get(player_id)
        if player and player.is_ai:
            yield event.plain_result("角色AI会自动行动，不需要真人代操作。")
            return

        result = await self.splendor_manager.apply_human_action(room, player_id, action)
        if not result.ok:
            yield event.plain_result(result.text)
            return
        status = ""
        if room.phase == PHASE_PLAYING and not result.game_finished:
            status = "\n\n" + self.splendor_manager.public_status(room, viewer_id=player_id)
        yield event.plain_result(result.text + status)
        if room.phase == PHASE_PLAYING and not result.game_finished:
            await self.splendor_manager.process_ai_turns(room)

    def _room_for_event(self, event: AstrMessageEvent) -> "SplendorRoom | None":
        group_id = event.get_group_id()
        if not group_id:
            return None
        room = self.splendor_manager.get_room(group_id)
        if room:
            self.splendor_manager.attach_event_transport(
                room, event.unified_msg_origin, event.bot
            )
        return room

    def _waiting_room_for_event(self, event: AstrMessageEvent) -> "SplendorRoom | None":
        room = self._room_for_event(event)
        if not room or room.phase != PHASE_WAITING:
            return None
        return room

    def _get_supported_character_profiles(self) -> list["CharacterSkillProfile"]:
        return self.game_manager.character_skill_service.list_profiles()

    def _match_character_profile(self, selector: str) -> "CharacterSkillProfile | None":
        selector = selector.strip()
        profiles = self._get_supported_character_profiles()
        if selector.isdigit():
            index = int(selector)
            if 1 <= index <= len(profiles):
                return profiles[index - 1]
        folded = selector.lower()
        for profile in profiles:
            if folded in {profile.skill_id.lower(), profile.display_name.lower()}:
                return profile
        for profile in profiles:
            if folded in profile.display_name.lower() or folded in profile.skill_id.lower():
                return profile
        return None

    @staticmethod
    def _parse_player_count(args: str) -> int:
        match = re.search(r"\b([2-4])\b", args or "")
        return int(match.group(1)) if match else 0

    @staticmethod
    def _parse_colors(args: str) -> list[str]:
        tokens = re.split(r"[\s,，、/]+", args.strip())
        colors = []
        for token in tokens:
            color = parse_color(token)
            if color:
                colors.append(color)
        return colors

    @staticmethod
    def _extract_command_args(event: AstrMessageEvent, command_names: list[str]) -> str:
        text = event.message_str.strip()
        text = re.sub(r"^[/／]\s*", "", text)
        for command_name in command_names:
            if text.startswith(command_name):
                return text[len(command_name) :].strip()
        return ""

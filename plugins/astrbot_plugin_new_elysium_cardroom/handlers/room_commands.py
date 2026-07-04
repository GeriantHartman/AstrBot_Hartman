"""Room management commands."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, AsyncGenerator

from astrbot.api.event import AstrMessageEvent

from .base import BaseCommandHandler
from ..models import AIPlayerConfig, GamePhase
from ..utils import cmd, table_name

if TYPE_CHECKING:
    from ..models import GameRoom
    from ..services.character_skill_service import CharacterSkillProfile


class RoomCommandHandler(BaseCommandHandler):
    """Room management command handler."""

    AI_NAME_BLACKLIST = {
        "加入房间",
        "创建房间",
        "开始游戏",
        "结束游戏",
        "关闭房间",
        "关闭狼人杀",
        "关闭狼人杀房间",
        "关闭璀璨房间",
        "关闭宝石",
        "关闭宝石房间",
        "投票",
        "办掉",
        "验人",
        "救人",
        "毒人",
        "开枪",
        "房间",
    }

    async def create_room(self, event: AstrMessageEvent) -> AsyncGenerator:
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("请在群聊中使用此命令。")
            return

        if self.game_manager.room_exists(group_id):
            yield event.plain_result("当前群已存在棋牌室房间，请先结束现有游戏。")
            return

        room = self.game_manager.create_room(
            group_id=group_id,
            creator_id=event.get_sender_id(),
            msg_origin=event.unified_msg_origin,
            bot=event.bot,
        )

        config = self.game_manager.config
        yield event.plain_result(
            "新爱莉都棋牌室开好了。\n\n"
            f"规则：{config.total_players}人局，"
            f"{config.werewolf_count}狼/{config.god_count}神/{config.villager_count}民\n"
            "原则：和角色本人一起玩桌游，角色声纹与羁绊行为优先于职业化盘逻辑。\n\n"
            f"加入：{cmd('加入房间')}\n"
            f"查看角色AI：{cmd('AI角色列表')}\n"
            f"补满角色AI：{cmd('补满角色AI')}\n"
            f"开始：{cmd('开始游戏')}\n"
            f"审计ID：{room.audit_id or '未开启'}"
        )

    async def join_room(self, event: AstrMessageEvent) -> AsyncGenerator:
        room = self._waiting_room_for_event(event)
        if not room:
            yield event.plain_result(
                f"当前群没有等待中的房间，请先使用 {cmd('创建房间')}"
            )
            return

        player_id = event.get_sender_id()
        if room.is_player_in_room(player_id):
            yield event.plain_result("你已经在游戏中了。")
            return
        if room.is_full:
            yield event.plain_result(
                f"房间已满（{room.player_count}/{self.game_manager.config.total_players}）。"
            )
            return

        player_name = self.get_player_name(event)
        self.game_manager.add_player(room, player_id, player_name)
        yield event.plain_result(
            f"{player_name} 加入游戏。\n"
            f"当前人数：{room.player_count}/{self.game_manager.config.total_players}"
        )

    async def start_game(self, event: AstrMessageEvent) -> AsyncGenerator:
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("请在群聊中使用此命令。")
            return

        room = self.game_manager.get_room(group_id)
        if not room:
            yield event.plain_result("当前群没有创建的房间。")
            return
        if event.get_sender_id() != room.creator_id:
            yield event.plain_result("只有房主才能开始游戏。")
            return
        if room.player_count != self.game_manager.config.total_players:
            yield event.plain_result(
                f"人数不足：{room.player_count}/{self.game_manager.config.total_players}"
            )
            return
        if room.phase != GamePhase.WAITING:
            yield event.plain_result("游戏已经开始。")
            return

        yield event.plain_result(
            "游戏开始，天黑请闭眼。\n"
            "人类玩家会收到私聊身份；AI 会读取角色卡、关系图和过往牌桌记忆。"
        )

        await self.game_manager.start_game(room)

        from ..phases import NightWolfPhase

        await NightWolfPhase(self.game_manager).on_enter(room)

    async def end_game(self, event: AstrMessageEvent) -> AsyncGenerator:
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("请在群聊中使用此命令。")
            return

        room = self.game_manager.get_room(group_id)
        if not room:
            yield event.plain_result("当前群没有进行中的游戏。")
            return
        if event.get_sender_id() != room.creator_id:
            yield event.plain_result("只有房主才能结束游戏。")
            return

        await self.game_manager.cleanup_room(group_id)
        yield event.plain_result("房间已结束，群状态已尝试恢复。")

    async def ai_join_room(self, event: AstrMessageEvent) -> AsyncGenerator:
        room = self._waiting_room_for_event(event)
        if not room:
            yield event.plain_result(
                f"当前群没有等待中的房间，请先使用 {cmd('创建房间')}"
            )
            return
        if room.is_full:
            yield event.plain_result(
                f"房间已满（{room.player_count}/{self.game_manager.config.total_players}）。"
            )
            return

        match = re.match(r"^[/／]?(.+?)加入$", event.message_str.strip())
        ai_name = match.group(1).strip() if match else ""
        if not ai_name:
            yield event.plain_result(f"无法识别AI名称，示例：{cmd('小咪加入')}")
            return
        if len(ai_name) > 10:
            yield event.plain_result("AI名称不能超过10个字符。")
            return
        if ai_name in self.AI_NAME_BLACKLIST:
            yield event.plain_result(f"{ai_name} 是保留名称，请换一个。")
            return
        if room.is_player_in_room(f"ai_{ai_name}"):
            yield event.plain_result(f"AI玩家 {ai_name} 已经在游戏中了。")
            return

        ai_config = AIPlayerConfig(
            name=ai_name,
            model_id=self.game_manager.config.ai_player_model,
        )
        ai_player = self.game_manager.add_ai_player(room, ai_name, ai_config)
        yield event.plain_result(
            f"{ai_player.name} 加入游戏。\n"
            f"当前人数：{room.player_count}/{self.game_manager.config.total_players}"
        )

    async def show_ai_roles(self, event: AstrMessageEvent) -> AsyncGenerator:
        profiles = self._get_supported_character_profiles()
        if not profiles:
            yield event.plain_result(
                "没有发现可用角色卡。\n"
                f"当前角色卡目录：{self.game_manager.character_skill_service.skill_root}"
            )
            return

        lines = ["可用角色AI："]
        for index, profile in enumerate(profiles[:40], start=1):
            werewolf_adapter = (
                "狼人杀有适配"
                if self.game_manager.character_skill_service.has_tabletop_adapter(
                    profile.skill_id
                )
                else "缺 tabletop_werewolf.md"
            )
            splendor_adapter = (
                "璀璨有适配"
                if self.game_manager.character_skill_service.has_tabletop_adapter(
                    profile.skill_id, mode="splendor"
                )
                else "璀璨用通用裁剪"
            )
            lines.append(
                f"{index}. {profile.display_name}（{werewolf_adapter}；{splendor_adapter}）"
            )
        lines.append("")
        lines.append(f"加入：{cmd('加入角色AI')} 序号或名字")
        lines.append(f"补满：{cmd('补满角色AI')}")
        yield event.plain_result("\n".join(lines))

    async def join_character_ai(self, event: AstrMessageEvent) -> AsyncGenerator:
        room = self._waiting_room_for_event(event)
        if not room:
            yield event.plain_result(
                f"当前群没有等待中的房间，请先使用 {cmd('创建房间')}"
            )
            return
        if room.is_full:
            yield event.plain_result(
                f"房间已满（{room.player_count}/{self.game_manager.config.total_players}）。"
            )
            return

        selector = self._extract_command_args(
            event, ["加入角色AI", "角色AI加入", "添加角色AI", "召唤角色AI"]
        )
        if not selector:
            yield event.plain_result(f"请指定角色AI。示例：{cmd('加入角色AI')} 三月七")
            return

        profile = self._match_character_profile(selector)
        if not profile:
            yield event.plain_result(
                f"未找到角色AI：{selector}\n请使用 {cmd('AI角色列表')} 查看可用角色。"
            )
            return

        result = self._add_character_ai_player(room, profile)
        yield event.plain_result(result)

    async def fill_character_ai(self, event: AstrMessageEvent) -> AsyncGenerator:
        room = self._waiting_room_for_event(event)
        if not room:
            yield event.plain_result(
                f"当前群没有等待中的房间，请先使用 {cmd('创建房间')}"
            )
            return

        added = []
        skipped = []
        roster = self.game_manager.character_skill_service.parse_roster(
            self.game_manager.config.default_ai_skill_roster
        )
        profiles_by_id = {
            profile.skill_id: profile
            for profile in self._get_supported_character_profiles()
        }
        fallback_profiles = [
            profile
            for profile in self._get_supported_character_profiles()
            if profile.skill_id not in roster
        ]
        ordered_profiles = [
            profiles_by_id[skill_id]
            for skill_id in roster
            if skill_id in profiles_by_id
        ] + fallback_profiles

        for profile in ordered_profiles:
            if room.is_full:
                break
            if self._room_has_skill(room, profile.skill_id):
                skipped.append(profile.display_name)
                continue
            self._add_character_ai_player(room, profile, quiet=True)
            added.append(profile.display_name)

        if not added:
            yield event.plain_result(
                f"没有新增角色AI。当前人数：{room.player_count}/{room.config.total_players}"
            )
            return

        yield event.plain_result(
            "已补入角色AI：\n"
            + "\n".join(f"- {name}" for name in added)
            + f"\n\n当前人数：{room.player_count}/{room.config.total_players}"
        )

    async def kick_ai_player(self, event: AstrMessageEvent) -> AsyncGenerator:
        room = self._waiting_room_for_event(event)
        if not room:
            yield event.plain_result("当前群没有等待中的房间，或游戏已经开始。")
            return

        target = self._extract_command_args(event, ["踢出AI", "移除AI", "删除AI"])
        if not target:
            ai_players = [player for player in room.players.values() if player.is_ai]
            if not ai_players:
                yield event.plain_result("当前房间没有AI玩家。")
                return
            yield event.plain_result(
                "请指定要移除的AI：\n"
                + "\n".join(f"- {table_name(player)}" for player in ai_players)
            )
            return

        player = self._find_ai_player(room, target)
        if not player:
            yield event.plain_result(f"未找到AI玩家：{target}")
            return

        del room.players[player.id]
        self.game_manager.save_room_state(room)
        yield event.plain_result(
            f"已移除 {table_name(player)}。\n"
            f"当前人数：{room.player_count}/{room.config.total_players}"
        )

    async def list_ai_players(self, event: AstrMessageEvent) -> AsyncGenerator:
        group_id = event.get_group_id()
        room = self.game_manager.get_room(group_id) if group_id else None
        if not room:
            yield event.plain_result("当前群没有房间。")
            return
        ai_players = [player for player in room.players.values() if player.is_ai]
        if not ai_players:
            yield event.plain_result("当前房间没有AI玩家。")
            return
        lines = ["当前AI玩家："]
        for player in sorted(ai_players, key=lambda item: item.number or 999):
            skill_id = player.ai_config.skill_id if player.ai_config else ""
            skill_text = f" / {skill_id}" if skill_id else ""
            lines.append(f"- {table_name(player)}{skill_text}")
        yield event.plain_result("\n".join(lines))

    async def self_check(self, event: AstrMessageEvent) -> AsyncGenerator:
        config = self.game_manager.config
        skill_service = self.game_manager.character_skill_service
        profiles = self._get_supported_character_profiles()
        roster = skill_service.parse_roster(config.default_ai_skill_roster)
        roster_counts = Counter(roster)
        missing_roster = [
            skill_id
            for skill_id in roster
            if not (skill_service.skill_root / skill_id).exists()
        ]
        missing_adapter = [
            profile.display_name
            for profile in profiles
            if not skill_service.has_tabletop_adapter(profile.skill_id)
        ]
        splendor_adapter_count = sum(
            1
            for profile in profiles
            if skill_service.has_tabletop_adapter(profile.skill_id, mode="splendor")
        )

        provider_status = (
            "可用" if self.game_manager.context.get_using_provider() else "不可用"
        )
        relationship_service = self.game_manager.character_relationship_service
        room = (
            self.game_manager.get_room(event.get_group_id())
            if event.get_group_id()
            else None
        )

        lines = [
            "新爱莉都棋牌室自检",
            f"- 角色数量配置：{'正常' if config.validate() else '不匹配'}",
            f"- AI Provider：{provider_status}",
            f"- 角色卡目录：{skill_service.skill_root}",
            f"- 角色卡目录存在：{Path(skill_service.skill_root).is_dir()}",
            f"- 可用角色卡：{len(profiles)}",
            f"- 默认 roster：{len(roster)} 个",
            f"- roster 缺失：{', '.join(missing_roster) if missing_roster else '无'}",
            f"- roster 重复：{', '.join(k for k, v in roster_counts.items() if v > 1) or '无'}",
            f"- 缺桌游适配：{len(missing_adapter)} 个",
            f"- 璀璨宝石适配：{splendor_adapter_count} 个",
            f"- 关系图：{'存在' if relationship_service.exists else '缺失'}，边数 {relationship_service.relation_count()}",
            f"- 行为概率：{'开启' if config.enable_character_behavior_rolls else '关闭'} / {config.character_behavior_intensity}",
            f"- 审计：{'开启' if config.enable_cardroom_audit else '关闭'}",
            f"- 默认LLM隔离：{'开启' if config.suppress_default_llm_during_room else '关闭'}",
            f"- 角色记忆目录：{self.game_manager.character_memory_service.base_dir}",
            f"- 资产清单路径：{self.game_manager.asset_manifest_service.manifest_path}",
        ]
        if room:
            lines.append(
                f"- 当前房间：{room.phase.value}，{room.player_count}/{room.config.total_players} 人，审计 {room.audit_id or '无'}"
            )
        else:
            lines.append("- 当前房间：无")
        yield event.plain_result("\n".join(lines))

    async def show_audit(self, event: AstrMessageEvent) -> AsyncGenerator:
        group_id = event.get_group_id()
        room = self.game_manager.get_room(group_id) if group_id else None
        lines = ["棋牌室审计"]
        if room and room.audit_id:
            lines.extend(
                [
                    f"- 当前审计ID：{room.audit_id}",
                    f"- JSONL：{room.audit_log_path}",
                    f"- 摘要：{room.audit_summary_path}",
                ]
            )

        recent = self.game_manager.audit_service.list_recent_audits(limit=5)
        if recent:
            lines.append("\n最近审计：")
            for item in recent:
                lines.append(
                    f"- {item['audit_id']} {item['result']} "
                    f"{item['finished_at']}\n  {item['summary_path']}"
                )
        elif not (room and room.audit_id):
            lines.append("- 暂无审计记录。")
        yield event.plain_result("\n".join(lines))

    async def export_assets_manifest(self, event: AstrMessageEvent) -> AsyncGenerator:
        path = self.game_manager.asset_manifest_service.write_manifest(
            self.game_manager.character_skill_service
        )
        manifest = self.game_manager.asset_manifest_service.build_manifest(
            self.game_manager.character_skill_service
        )
        yield event.plain_result(
            "资产清单已生成。\n"
            f"路径：{path}\n"
            f"角色卡：{len(manifest['skills'])}\n"
            f"璀璨适配：{sum(1 for item in manifest['skills'] if item.get('has_tabletop_splendor'))}\n"
            f"默认 roster 缺失：{', '.join(manifest['missing_roster']) if manifest['missing_roster'] else '无'}\n"
            f"关系图哈希：{manifest['relationship_graph']['sha256'] or '无'}"
        )

    def _waiting_room_for_event(self, event: AstrMessageEvent) -> "GameRoom | None":
        group_id = event.get_group_id()
        if not group_id:
            return None
        room = self.game_manager.get_room(group_id)
        if not room or room.phase != GamePhase.WAITING:
            return None
        self.game_manager.attach_event_transport(room, event.unified_msg_origin, event.bot)
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
            if folded in {
                profile.skill_id.lower(),
                profile.display_name.lower(),
            }:
                return profile
        for profile in profiles:
            if (
                folded in profile.display_name.lower()
                or folded in profile.skill_id.lower()
            ):
                return profile
        return None

    def _add_character_ai_player(
        self,
        room: "GameRoom",
        profile: "CharacterSkillProfile",
        quiet: bool = False,
    ) -> str:
        if self._room_has_skill(room, profile.skill_id):
            return f"{profile.display_name} 已在房间中。"
        ai_config = AIPlayerConfig(
            name=profile.display_name,
            model_id=self.game_manager.config.ai_player_model,
            personality=profile.prompt,
            skill_id=profile.skill_id,
        )
        ai_player = self.game_manager.add_ai_player(
            room, profile.display_name, ai_config
        )
        if quiet:
            return ""
        return (
            f"{table_name(ai_player)} 加入游戏。\n"
            f"角色卡：{profile.display_name}\n"
            f"当前人数：{room.player_count}/{room.config.total_players}"
        )

    @staticmethod
    def _room_has_skill(room: "GameRoom", skill_id: str) -> bool:
        return any(
            player.is_ai and player.ai_config and player.ai_config.skill_id == skill_id
            for player in room.players.values()
        )

    @staticmethod
    def _find_ai_player(room: "GameRoom", target: str):
        folded = target.strip().lower()
        for player in room.players.values():
            if not player.is_ai:
                continue
            names = {
                player.id.lower(),
                player.name.lower(),
                table_name(player).lower(),
            }
            if player.ai_config:
                names.add(player.ai_config.name.lower())
                names.add(player.ai_config.skill_id.lower())
            if folded in names or any(folded in name for name in names):
                return player
        return None

    @staticmethod
    def _extract_command_args(event: AstrMessageEvent, command_names: list[str]) -> str:
        text = event.message_str.strip()
        text = re.sub(r"^[/／]\s*", "", text)
        for command_name in command_names:
            if text.startswith(command_name):
                return text[len(command_name) :].strip()
        return ""

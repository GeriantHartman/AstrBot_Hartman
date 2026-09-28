"""游戏管理器"""

import random
from typing import Dict, Optional, Tuple, TYPE_CHECKING
from astrbot.api import logger

from ..models import GameRoom, GameConfig, GamePhase, Player, Role, AIPlayerConfig
from ..roles import RoleFactory
from .message_service import MessageService
from .ban_service import BanService
from .victory_checker import VictoryChecker
from .ai_reviewer import AIReviewer
from .ai import AIPlayerService
from .audit_service import AuditService
from .asset_manifest_service import AssetManifestService
from .character_memory_service import CharacterMemoryService
from .character_relationship_service import CharacterRelationshipService
from .character_skill_service import CharacterSkillService
from .room_state_storage_service import RoomStateStorageService
from .tabletop_behavior_service import TabletopBehaviorService

if TYPE_CHECKING:
    from astrbot.api.star import Context


class GameManager:
    """游戏管理器 - 协调各服务"""

    def __init__(self, context: "Context", config: GameConfig):
        self.context = context
        self.config = config
        self.rooms: Dict[str, GameRoom] = {}  # {群ID: 房间}

        # 初始化服务
        self.message_service = MessageService(context)
        self.ai_reviewer = AIReviewer(context)
        self.character_skill_service = CharacterSkillService(
            config.character_skill_root
        )
        self.character_memory_service = CharacterMemoryService()
        self.character_relationship_service = CharacterRelationshipService()
        self.tabletop_behavior_service = TabletopBehaviorService(config)
        self.audit_service = AuditService(config)
        self.asset_manifest_service = AssetManifestService(config)
        self.ai_player_service = AIPlayerService(
            context, self.character_relationship_service
        )
        self.room_state_storage_service = RoomStateStorageService()
        self.rooms = self.room_state_storage_service.load_active_rooms(
            config,
            audit_service=self.audit_service,
            behavior_service=self.tabletop_behavior_service,
        )
        if self.rooms:
            logger.info(f"[狼人杀] 已恢复 {len(self.rooms)} 个活动房间")

    # ========== 房间管理 ==========

    def get_room(self, group_id: str) -> Optional[GameRoom]:
        """获取房间"""
        return self.rooms.get(group_id)

    def attach_event_transport(self, room: GameRoom, msg_origin=None, bot=None) -> None:
        """Refresh runtime-only message transport handles for a restored room."""
        previous_origin = room.msg_origin
        if msg_origin:
            room.msg_origin = msg_origin
        if bot:
            room.bot = bot
        if msg_origin and msg_origin != previous_origin:
            self.save_room_state(room)

    def save_room_state(self, room: GameRoom) -> None:
        """Persist an active room snapshot."""
        try:
            self.room_state_storage_service.save_room(room)
        except Exception as exc:
            logger.warning(f"[狼人杀] 保存房间 {room.group_id} 快照失败: {exc}")

    def persist_active_rooms(self) -> None:
        """Persist all active rooms without ending them."""
        for room in list(self.rooms.values()):
            room.cancel_timer()
            if room.wolf_ai_vote_task and not room.wolf_ai_vote_task.done():
                room.wolf_ai_vote_task.cancel()
            room.wolf_ai_vote_task = None
            if room.wolf_ai_process_task and not room.wolf_ai_process_task.done():
                room.wolf_ai_process_task.cancel()
            room.wolf_ai_process_task = None
            if room.phase != GamePhase.FINISHED:
                self.save_room_state(room)

    def get_room_by_player(
        self, player_id: str
    ) -> Tuple[Optional[str], Optional[GameRoom]]:
        """通过玩家ID查找房间"""
        for group_id, room in self.rooms.items():
            if room.is_player_in_room(player_id):
                return group_id, room
        return None, None

    def create_room(self, group_id: str, creator_id: str, msg_origin, bot) -> GameRoom:
        """创建房间"""
        room = GameRoom(
            group_id=group_id,
            creator_id=creator_id,
            config=self.config,
            msg_origin=msg_origin,
            bot=bot,
        )
        room.audit_service = self.audit_service
        room.behavior_service = self.tabletop_behavior_service
        self.rooms[group_id] = room
        self.audit_service.start_room(room)
        self.save_room_state(room)
        logger.info(f"[狼人杀] 群 {group_id} 创建房间")
        return room

    def room_exists(self, group_id: str) -> bool:
        """房间是否存在"""
        return group_id in self.rooms

    async def cleanup_room(self, group_id: str) -> None:
        """清理房间"""
        if group_id not in self.rooms:
            return

        room = self.rooms[group_id]
        self.audit_service.record(room, "cleanup_started", {"phase": room.phase.value})

        # 先解除全员禁言（最重要！放在最前面确保执行）
        try:
            await BanService.set_group_whole_ban(room, False)
        except Exception as e:
            logger.error(f"[狼人杀] 解除全员禁言失败: {e}")

        # 恢复群昵称
        try:
            await BanService.restore_player_cards(room)
        except Exception as e:
            logger.error(f"[狼人杀] 恢复群昵称失败: {e}")

        # 取消定时器
        room.cancel_timer()

        # 解除所有禁言
        try:
            await BanService.unban_all_players(room)
        except Exception as e:
            logger.error(f"[狼人杀] 解除个人禁言失败: {e}")

        # 取消所有临时管理员
        try:
            await BanService.clear_temp_admins(room)
        except Exception as e:
            logger.error(f"[狼人杀] 取消临时管理员失败: {e}")

        if room.phase != GamePhase.FINISHED:
            self.audit_service.finalize_room(room, "房间被清理或强制结束")

        # 删除房间
        del self.rooms[group_id]
        self.room_state_storage_service.delete_room(group_id)

        logger.info(f"[狼人杀] 群 {group_id} 房间已清理")

    # ========== 玩家管理 ==========

    def add_player(self, room: GameRoom, player_id: str, player_name: str) -> Player:
        """添加玩家到房间"""
        player = Player(id=player_id, name=player_name)
        room.add_player(player)
        self.audit_service.record(
            room, "human_joined", {"player_id": player_id, "player_name": player_name}
        )
        self.save_room_state(room)
        return player

    # AI玩家emoji列表（按加入顺序分配）
    AI_EMOJIS = ["🤖", "🦊", "🐱", "🐰", "🐻", "🐼", "🦁", "🐯", "🐮"]

    def add_ai_player(
        self, room: GameRoom, ai_name: str, ai_config: AIPlayerConfig
    ) -> Player:
        """添加AI玩家到房间"""
        ai_player_id = f"ai_{ai_name}"

        # 根据当前AI数量分配不同emoji
        current_ai_count = len([p for p in room.players.values() if p.is_ai])
        emoji = self.AI_EMOJIS[current_ai_count % len(self.AI_EMOJIS)]

        personality_name = "角色卡"
        if self.config.enable_character_skill_ai and ai_config.skill_id:
            profile = self.character_skill_service.get_profile(ai_config.skill_id)
            if profile:
                ai_name = profile.display_name
                ai_config.name = profile.display_name
                ai_config.personality = profile.prompt
                ai_config.memory_id = (
                    f"{room.group_id}:{ai_player_id}:{ai_config.skill_id}"
                )
        else:
            # Normal AI still uses the upstream personality template pool.
            personality_name = self.ai_player_service.assign_personality(ai_player_id)

        player = Player(
            id=ai_player_id,
            name=f"{emoji}{ai_name}",  # 移除性格标签，避免泄露
            is_ai=True,
            ai_config=ai_config,
        )
        room.add_player(player)
        self.audit_service.record(
            room,
            "ai_joined",
            {
                "player_id": ai_player_id,
                "player_name": player.name,
                "skill_id": ai_config.skill_id,
                "personality": personality_name,
            },
        )
        logger.info(
            f"[狼人杀] AI玩家 {emoji}{ai_name}({personality_name}) 加入房间 {room.group_id}，性格已隐藏"
        )
        self.save_room_state(room)
        return player

    def get_ai_players(self, room: GameRoom) -> list:
        """获取房间内所有AI玩家"""
        return [p for p in room.players.values() if p.is_ai]

    def get_human_players(self, room: GameRoom) -> list:
        """获取房间内所有人类玩家"""
        return [p for p in room.players.values() if not p.is_ai]

    # ========== 游戏流程 ==========

    async def start_game(self, room: GameRoom) -> None:
        """开始游戏"""
        players_list = list(room.players.values())

        # 随机打乱玩家顺序（确保编号随机分配）
        random.shuffle(players_list)

        # 分配编号
        for index, player in enumerate(players_list, start=1):
            player.assign_number(index)
            room.number_to_player[index] = player.id

        # 分配角色
        roles_pool = self.config.get_roles_pool()
        random.shuffle(roles_pool)
        for player, role in zip(players_list, roles_pool):
            player.assign_role(role)

        # 初始化游戏状态
        room.phase = GamePhase.NIGHT_WOLF
        room.current_round = 1

        # 为AI玩家初始化上下文
        for player in players_list:
            if player.is_ai:
                self.ai_player_service.initialize_ai_context(player, room)
                if (
                    player.ai_config
                    and player.ai_config.memory_id
                    and player.ai_context
                ):
                    player.ai_context.update_persistent_memories(
                        self.character_memory_service.load_memories(
                            player.ai_config.memory_id
                        )
                    )

        # 记录日志
        room.log_round_start()
        self.audit_service.record(
            room,
            "game_started",
            {
                "players": [
                    {
                        "id": player.id,
                        "name": player.name,
                        "number": player.number,
                        "role": player.role.display_name if player.role else "",
                        "is_ai": player.is_ai,
                        "skill_id": player.ai_config.skill_id
                        if player.ai_config
                        else "",
                    }
                    for player in players_list
                ]
            },
        )

        # 修改群昵称为编号（仅人类玩家）
        await BanService.set_player_numbers(room)

        # 开启全员禁言
        await BanService.set_group_whole_ban(room, True)

        # 私聊告知角色（仅人类玩家）
        await self._send_roles_to_players(room)

        self.save_room_state(room)
        logger.info(f"[狼人杀] 群 {room.group_id} 游戏开始")

    async def _send_roles_to_players(self, room: GameRoom) -> None:
        """私聊告知所有玩家角色（发送角色卡片图片）"""
        for player in room.players.values():
            # 跳过AI玩家（AI不需要接收私聊）
            if player.is_ai:
                logger.info(
                    f"[狼人杀] AI玩家 {player.name} 身份：{player.role.display_name if player.role else '未知'}"
                )
                continue

            if player.role:
                role_name = player.role.value

                # 如果是狼人，获取队友信息
                teammates = None
                if player.role == Role.WEREWOLF:
                    teammates = []
                    for w in room.get_werewolves():
                        if w.id != player.id:
                            teammates.append(w.display_name)

                # 尝试发送角色卡片图片
                success = await self.message_service.send_role_card_to_player(
                    room, player.id, role_name, player.number, teammates
                )

                # 如果图片发送失败，降级为文本
                if not success:
                    role_info = RoleFactory.get_role_info(player.role, player, room)
                    await self.message_service.send_private_message(
                        room, player.id, role_info
                    )

                logger.info(f"[狼人杀] 已私聊告知玩家 {player.id} 的身份：{role_name}")

    # ========== 胜负判定 ==========

    async def check_and_handle_victory(self, room: GameRoom) -> bool:
        """检查胜负并处理，返回游戏是否结束"""
        victory_msg, winning_faction = VictoryChecker.check(room)

        if not victory_msg:
            return False

        room.phase = GamePhase.FINISHED
        self.save_room_state(room)

        # 获取角色公布文本
        roles_text = VictoryChecker.get_all_players_roles(room)

        # 发送胜利消息
        await self.message_service.announce_victory(room, victory_msg, roles_text)
        self.audit_service.record(
            room,
            "victory",
            {"victory_msg": victory_msg, "winning_faction": winning_faction},
        )

        for player in room.players.values():
            if player.is_ai:
                self.character_memory_service.remember_game(
                    player, room, victory_msg or winning_faction or "游戏结束"
                )

        # 生成AI复盘（失败不影响游戏结束）
        try:
            if winning_faction:
                ai_review = await self.ai_reviewer.generate_review(
                    room, winning_faction
                )
                if ai_review:
                    await self.message_service.send_group_message(room, ai_review)
        except Exception as e:
            logger.error(f"[狼人杀] AI复盘生成失败: {e}")

        self.audit_service.finalize_room(
            room, victory_msg or winning_faction or "游戏结束"
        )

        # 清理房间（确保一定会执行）
        await self.cleanup_room(room.group_id)

        return True

    # ========== 夜晚流程 ==========

    async def process_night_kill(self, room: GameRoom) -> Optional[str]:
        """处理狼人投票结果，返回被杀玩家ID"""
        votes = room.vote_state.night_votes
        votes_snapshot = dict(votes)

        if not votes:
            return None

        # 统计票数
        vote_counts: Dict[str, int] = {}
        for target_id in votes.values():
            vote_counts[target_id] = vote_counts.get(target_id, 0) + 1

        # 获取票数最多的目标
        max_votes = max(vote_counts.values())
        targets = [pid for pid, count in vote_counts.items() if count == max_votes]

        # 平票随机选择
        killed_id = random.choice(targets)

        # 清空投票
        room.vote_state.clear_night_votes()

        # 记录被杀玩家（不立即移除，等女巫行动后确定）
        room.last_killed_id = killed_id

        # 记录日志
        killed_player = room.get_player(killed_id)
        if killed_player:
            room.log(f"🌙 狼人最终决定刀 {killed_player.display_name}")
            self.audit_service.record(
                room,
                "night_kill_decided",
                {
                    "killed_id": killed_id,
                    "killed_name": killed_player.display_name,
                    "votes": votes_snapshot,
                },
            )

        self.save_room_state(room)
        return killed_id

    async def process_witch_action(self, room: GameRoom) -> None:
        """处理女巫行动结果"""
        witch_state = room.witch_state

        # 如果女巫救人
        if witch_state.saved_player_id:
            saved = room.get_player(witch_state.saved_player_id)
            room.last_killed_id = None
            self.audit_service.record(
                room,
                "witch_saved",
                {
                    "saved_id": witch_state.saved_player_id,
                    "saved_name": saved.display_name if saved else "",
                },
            )

        # 如果女巫没救人，被杀者确定死亡
        elif room.last_killed_id:
            killed = room.kill_player(room.last_killed_id)
            self.audit_service.record(
                room,
                "night_kill_applied",
                {
                    "killed_id": room.last_killed_id,
                    "killed_name": killed.display_name if killed else "",
                },
            )

        # 如果女巫毒人
        if witch_state.poisoned_player_id:
            poisoned = room.kill_player(witch_state.poisoned_player_id)
            await BanService.ban_player(room, witch_state.poisoned_player_id)
            self.audit_service.record(
                room,
                "witch_poisoned",
                {
                    "poisoned_id": witch_state.poisoned_player_id,
                    "poisoned_name": poisoned.display_name if poisoned else "",
                },
            )

        self.save_room_state(room)

    # ========== 白天流程 ==========

    async def process_day_vote(self, room: GameRoom) -> Tuple[Optional[str], bool]:
        """
        处理白天投票结果

        返回: (被放逐玩家ID, 是否平票)
        """
        votes = room.vote_state.day_votes
        votes_snapshot = dict(votes)

        if not votes:
            return None, False

        # 统计票数（排除弃票）
        vote_counts: Dict[str, int] = {}
        for target_id in votes.values():
            if target_id == "ABSTAIN":
                continue  # 跳过弃票
            vote_counts[target_id] = vote_counts.get(target_id, 0) + 1

        # 如果全部弃票，无人出局
        if not vote_counts:
            self.audit_service.record(
                room, "day_vote_all_abstained", {"votes": votes_snapshot}
            )
            return None, False

        # 获取票数最多的目标
        max_votes = max(vote_counts.values())
        targets = [pid for pid, count in vote_counts.items() if count == max_votes]

        # 检查平票
        if len(targets) > 1:
            # 平票
            if not room.vote_state.is_pk_vote:
                # 第一次投票平票，进入PK
                targets.sort(
                    key=lambda pid: (
                        room.get_player(pid).number if room.get_player(pid) else 999
                    )
                )
                room.vote_state.pk_players = targets
                self.audit_service.record(
                    room, "day_vote_tied", {"targets": targets, "votes": votes_snapshot}
                )
                self.save_room_state(room)
                return None, True
            else:
                # PK后仍平票，无人出局
                room.vote_state.clear_day_votes()
                self.audit_service.record(
                    room,
                    "day_pk_vote_tied",
                    {"targets": targets, "votes": votes_snapshot},
                )
                self.save_room_state(room)
                return None, True

        # 只有一人票数最多
        exiled_id = targets[0]

        # 移除存活列表
        exiled = room.kill_player(exiled_id)

        # 清空投票
        room.vote_state.clear_day_votes()
        self.audit_service.record(
            room,
            "day_vote_exiled",
            {
                "exiled_id": exiled_id,
                "exiled_name": exiled.display_name if exiled else "",
                "votes": votes_snapshot,
            },
        )

        self.save_room_state(room)
        return exiled_id, False

    # ========== 工具方法 ==========

    def get_player_name(self, player_id: str) -> str:
        """获取玩家名称（跨房间查找）"""
        _, room = self.get_room_by_player(player_id)
        if room:
            player = room.get_player(player_id)
            if player:
                return player.display_name
        return f"玩家{player_id[-4:]}"

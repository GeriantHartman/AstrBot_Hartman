"""New Elysium Cardroom AstrBot plugin."""

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.star.filter.permission import PermissionType

from .handlers import (
    DayCommandHandler,
    NightCommandHandler,
    QueryCommandHandler,
    RoomCommandHandler,
    SplendorCommandHandler,
)
from .models import GameConfig
from .services import GameManager
from .splendor import SplendorManager
from .utils import set_command_prefix


@register(
    "astrbot_plugin_new_elysium_cardroom",
    "Hartman/Codex",
    "新爱莉都棋牌室：角色卡AI狼人杀与璀璨宝石",
    "v0.2.0",
)
class NewElysiumCardroomPlugin(Star):
    """Character-card tabletop room for Werewolf and Splendor games."""

    def __init__(self, context: Context, config: dict = None, *args, **kwargs):
        super().__init__(context)
        self.context = context
        self._init_command_prefix()
        self.game_config = self._load_config(config or {})
        self.game_manager = GameManager(context, self.game_config)
        self.splendor_manager = SplendorManager(
            context=context,
            config=self.game_config,
            message_service=self.game_manager.message_service,
            character_skill_service=self.game_manager.character_skill_service,
            character_relationship_service=self.game_manager.character_relationship_service,
            character_memory_service=self.game_manager.character_memory_service,
        )
        self.room_handler = RoomCommandHandler(self.game_manager)
        self.night_handler = NightCommandHandler(self.game_manager)
        self.day_handler = DayCommandHandler(self.game_manager)
        self.query_handler = QueryCommandHandler(self.game_manager)
        self.splendor_handler = SplendorCommandHandler(
            self.game_manager, self.splendor_manager
        )
        self._log_startup()

    def _init_command_prefix(self) -> None:
        try:
            astrbot_config = self.context.get_config()
            wake_prefixes = astrbot_config.get("wake_prefix", ["/"])
            set_command_prefix(wake_prefixes[0] if wake_prefixes else "/")
        except Exception as exc:
            logger.warning(f"[新爱莉都棋牌室] 读取命令前缀失败，使用默认 '/': {exc}")
            set_command_prefix("/")

    def _load_config(self, config: dict) -> GameConfig:
        game_config = GameConfig.from_dict(config)
        if not game_config.validate():
            logger.warning("[新爱莉都棋牌室] 角色数量配置不匹配，使用默认配置")
            game_config = GameConfig.default()
        return game_config

    def _log_startup(self) -> None:
        config = self.game_config
        logger.info(
            "[新爱莉都棋牌室] 插件已加载 | "
            f"{config.total_players}人局 "
            f"({config.werewolf_count}狼/{config.god_count}神/{config.villager_count}民) | "
            f"角色卡AI={'开' if config.enable_character_skill_ai else '关'} | "
            "璀璨宝石=开 | "
            f"审计={'开' if config.enable_cardroom_audit else '关'} | "
            f"默认LLM隔离={'开' if config.suppress_default_llm_during_room else '关'}"
        )

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=100)
    async def mute_default_llm_during_room(self, event: AstrMessageEvent):
        """Suppress generic roleplay LLM while a cardroom exists in the group."""
        group_id = event.get_group_id()
        if not group_id:
            return
        room = self.game_manager.get_room(group_id)
        splendor_room = self.splendor_manager.get_room(group_id)
        if room:
            self.game_manager.attach_event_transport(
                room, event.unified_msg_origin, event.bot
            )
        if splendor_room:
            self.splendor_manager.attach_event_transport(
                splendor_room, event.unified_msg_origin, event.bot
            )
        if self.game_config.suppress_default_llm_during_room and (
            room or splendor_room
        ):
            event.should_call_llm(True)

    # Room setup

    @filter.command("创建房间")
    async def create_room(self, event: AstrMessageEvent):
        async for result in self.room_handler.create_room(event):
            yield result

    @filter.command("加入房间")
    async def join_room(self, event: AstrMessageEvent):
        async for result in self.room_handler.join_room(event):
            yield result

    @filter.command("加人房间")
    async def join_room_alias1(self, event: AstrMessageEvent):
        async for result in self.room_handler.join_room(event):
            yield result

    @filter.command("加入")
    async def join_room_alias2(self, event: AstrMessageEvent):
        async for result in self.room_handler.join_room(event):
            yield result

    @filter.command("加人")
    async def join_room_alias3(self, event: AstrMessageEvent):
        async for result in self.room_handler.join_room(event):
            yield result

    @filter.permission_type(PermissionType.ADMIN)
    @filter.regex(r"^[/／]?(.+?)加入$")
    async def ai_join_room(self, event: AstrMessageEvent):
        async for result in self.room_handler.ai_join_room(event):
            yield result

    @filter.command("AI角色列表")
    async def show_ai_roles(self, event: AstrMessageEvent):
        async for result in self.room_handler.show_ai_roles(event):
            yield result

    @filter.command("角色AI列表")
    async def show_ai_roles_alias1(self, event: AstrMessageEvent):
        async for result in self.room_handler.show_ai_roles(event):
            yield result

    @filter.command("可用AI角色")
    async def show_ai_roles_alias2(self, event: AstrMessageEvent):
        async for result in self.room_handler.show_ai_roles(event):
            yield result

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("加入角色AI")
    async def join_character_ai(self, event: AstrMessageEvent):
        async for result in self.room_handler.join_character_ai(event):
            yield result

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("角色AI加入")
    async def join_character_ai_alias1(self, event: AstrMessageEvent):
        async for result in self.room_handler.join_character_ai(event):
            yield result

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("添加角色AI")
    async def join_character_ai_alias2(self, event: AstrMessageEvent):
        async for result in self.room_handler.join_character_ai(event):
            yield result

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("召唤角色AI")
    async def join_character_ai_alias3(self, event: AstrMessageEvent):
        async for result in self.room_handler.join_character_ai(event):
            yield result

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("补满角色AI")
    async def fill_character_ai(self, event: AstrMessageEvent):
        async for result in self.room_handler.fill_character_ai(event):
            yield result

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("踢出AI")
    async def kick_ai_player(self, event: AstrMessageEvent):
        async for result in self.room_handler.kick_ai_player(event):
            yield result

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("移除AI")
    async def kick_ai_player_alias1(self, event: AstrMessageEvent):
        async for result in self.room_handler.kick_ai_player(event):
            yield result

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("删除AI")
    async def kick_ai_player_alias2(self, event: AstrMessageEvent):
        async for result in self.room_handler.kick_ai_player(event):
            yield result

    @filter.command("AI玩家列表")
    async def list_ai_players(self, event: AstrMessageEvent):
        async for result in self.room_handler.list_ai_players(event):
            yield result

    @filter.command("开始游戏")
    async def start_game(self, event: AstrMessageEvent):
        async for result in self.room_handler.start_game(event):
            yield result

    @filter.command("结束游戏")
    async def end_game(self, event: AstrMessageEvent):
        async for result in self.room_handler.end_game(event):
            yield result

    @filter.command("关闭房间")
    async def end_game_alias1(self, event: AstrMessageEvent):
        group_id = event.get_group_id()
        if (
            group_id
            and self.splendor_manager.get_room(group_id)
            and not self.game_manager.get_room(group_id)
        ):
            async for result in self.splendor_handler.end_game(event):
                yield result
            return
        async for result in self.room_handler.end_game(event):
            yield result

    @filter.command("关闭狼人杀")
    async def end_game_alias_werewolf1(self, event: AstrMessageEvent):
        async for result in self.room_handler.end_game(event):
            yield result

    @filter.command("关闭狼人杀房间")
    async def end_game_alias_werewolf2(self, event: AstrMessageEvent):
        async for result in self.room_handler.end_game(event):
            yield result

    @filter.command("解散房间")
    async def end_game_alias2(self, event: AstrMessageEvent):
        async for result in self.room_handler.end_game(event):
            yield result

    @filter.command("棋牌室自检")
    async def self_check(self, event: AstrMessageEvent):
        async for result in self.room_handler.self_check(event):
            yield result

    @filter.command("棋牌室审计")
    async def show_audit(self, event: AstrMessageEvent):
        async for result in self.room_handler.show_audit(event):
            yield result

    @filter.command("狼人杀审计")
    async def show_audit_alias1(self, event: AstrMessageEvent):
        async for result in self.room_handler.show_audit(event):
            yield result

    @filter.command("棋牌室资产清单")
    async def export_assets_manifest(self, event: AstrMessageEvent):
        async for result in self.room_handler.export_assets_manifest(event):
            yield result

    @filter.command("棋牌室迁移自检")
    async def export_assets_manifest_alias1(self, event: AstrMessageEvent):
        async for result in self.room_handler.export_assets_manifest(event):
            yield result

    # Splendor room setup

    @filter.command("创建璀璨房间")
    async def create_splendor_room(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.create_room(event):
            yield result

    @filter.command("创建璀璨")
    async def create_splendor_room_alias1(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.create_room(event):
            yield result

    @filter.command("加入璀璨")
    async def join_splendor_room(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.join_room(event):
            yield result

    @filter.command("璀璨加入")
    async def join_splendor_room_alias1(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.join_room(event):
            yield result

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("璀璨加入角色AI")
    async def join_splendor_character_ai(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.join_character_ai(event):
            yield result

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("璀璨添加角色AI")
    async def join_splendor_character_ai_alias1(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.join_character_ai(event):
            yield result

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("璀璨补满AI")
    async def fill_splendor_character_ai(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.fill_character_ai(event):
            yield result

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("踢出璀璨AI")
    async def kick_splendor_ai(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.kick_ai_player(event):
            yield result

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("移除璀璨AI")
    async def kick_splendor_ai_alias1(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.kick_ai_player(event):
            yield result

    @filter.command("开始璀璨")
    async def start_splendor_game(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.start_game(event):
            yield result

    @filter.command("结束璀璨")
    async def end_splendor_game(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.end_game(event):
            yield result

    @filter.command("关闭璀璨")
    async def end_splendor_game_alias1(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.end_game(event):
            yield result

    @filter.command("关闭璀璨房间")
    async def end_splendor_game_alias2(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.end_game(event):
            yield result

    @filter.command("关闭宝石")
    async def end_splendor_game_alias3(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.end_game(event):
            yield result

    @filter.command("关闭宝石房间")
    async def end_splendor_game_alias4(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.end_game(event):
            yield result

    @filter.command("璀璨状态")
    async def show_splendor_status(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.show_status(event):
            yield result

    @filter.command("我的璀璨")
    async def show_my_splendor_status(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.show_status(event):
            yield result

    @filter.command("璀璨帮助")
    async def show_splendor_help(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.show_help(event):
            yield result

    @filter.command("拿宝石")
    async def splendor_take_tokens(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.take_tokens(event):
            yield result

    @filter.command("保留牌")
    async def splendor_reserve_card(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.reserve_card(event):
            yield result

    @filter.command("购买牌")
    async def splendor_buy_card(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.buy_card(event):
            yield result

    @filter.command("买牌")
    async def splendor_buy_card_alias1(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.buy_card(event):
            yield result

    @filter.command("选择贵族")
    async def splendor_choose_noble(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.choose_noble(event):
            yield result

    @filter.command("丢宝石")
    async def splendor_discard_tokens(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.discard_tokens(event):
            yield result

    @filter.command("弃宝石")
    async def splendor_discard_tokens_alias1(self, event: AstrMessageEvent):
        async for result in self.splendor_handler.discard_tokens(event):
            yield result

    # Night commands

    @filter.command("办掉")
    async def werewolf_kill(self, event: AstrMessageEvent):
        async for result in self.night_handler.werewolf_kill(event):
            yield result

    @filter.command("密谋")
    async def werewolf_chat(self, event: AstrMessageEvent):
        async for result in self.night_handler.werewolf_chat(event):
            yield result

    @filter.command("验人")
    async def seer_check(self, event: AstrMessageEvent):
        async for result in self.night_handler.seer_check(event):
            yield result

    @filter.command("救人")
    async def witch_save(self, event: AstrMessageEvent):
        async for result in self.night_handler.witch_save(event):
            yield result

    @filter.command("毒人")
    async def witch_poison(self, event: AstrMessageEvent):
        async for result in self.night_handler.witch_poison(event):
            yield result

    @filter.command("不操作")
    async def witch_pass(self, event: AstrMessageEvent):
        async for result in self.night_handler.witch_pass(event):
            yield result

    @filter.command("开枪")
    async def hunter_shoot(self, event: AstrMessageEvent):
        async for result in self.night_handler.hunter_shoot(event):
            yield result

    # Day commands

    @filter.command("遗言完毕")
    async def finish_last_words(self, event: AstrMessageEvent):
        async for result in self.day_handler.finish_last_words(event):
            yield result

    @filter.command("发言完毕")
    async def finish_speaking(self, event: AstrMessageEvent):
        async for result in self.day_handler.finish_speaking(event):
            yield result

    @filter.command("开始投票")
    async def start_vote(self, event: AstrMessageEvent):
        async for result in self.day_handler.start_vote(event):
            yield result

    @filter.command("跳过发言")
    async def start_vote_alias1(self, event: AstrMessageEvent):
        async for result in self.day_handler.start_vote(event):
            yield result

    @filter.command("投票")
    async def day_vote(self, event: AstrMessageEvent):
        async for result in self.day_handler.day_vote(event):
            yield result

    # Query commands

    @filter.command("查角色")
    async def check_role(self, event: AstrMessageEvent):
        async for result in self.query_handler.check_role(event):
            yield result

    @filter.command("游戏状态")
    async def show_status(self, event: AstrMessageEvent):
        async for result in self.query_handler.show_status(event):
            yield result

    @filter.command("房间")
    async def show_status_alias1(self, event: AstrMessageEvent):
        async for result in self.query_handler.show_status(event):
            yield result

    @filter.command("房间状态")
    async def show_status_alias2(self, event: AstrMessageEvent):
        async for result in self.query_handler.show_status(event):
            yield result

    @filter.command("狼人杀帮助")
    async def show_help(self, event: AstrMessageEvent):
        async for result in self.query_handler.show_help(event):
            yield result

    @filter.command("棋牌室帮助")
    async def show_help_alias1(self, event: AstrMessageEvent):
        async for result in self.query_handler.show_help(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def capture_speech(self, event: AstrMessageEvent):
        await self.day_handler.capture_speech(event)

    async def terminate(self):
        self.game_manager.persist_active_rooms()
        self.splendor_manager.persist_active_rooms()
        logger.info("[新爱莉都棋牌室] 插件已停止，活动房间快照已保存")

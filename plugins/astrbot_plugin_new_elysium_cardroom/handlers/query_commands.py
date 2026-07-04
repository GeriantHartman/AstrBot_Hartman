"""查询命令处理"""

from pathlib import Path
from typing import TYPE_CHECKING, AsyncGenerator
from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .base import BaseCommandHandler
from ..roles import RoleFactory
from ..utils import cmd, table_name

if TYPE_CHECKING:
    from ..services import GameManager


class QueryCommandHandler(BaseCommandHandler):
    """查询命令处理器"""

    def __init__(self, game_manager: "GameManager"):
        super().__init__(game_manager)
        # 使用 AstrBot 数据目录下的临时文件夹
        self.tmp_dir = Path(get_astrbot_data_path()) / "werewolf_temp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    async def check_role(self, event: AstrMessageEvent) -> AsyncGenerator:
        """查看角色（返回文本）"""
        player_id = event.get_sender_id()

        if not event.is_private_chat():
            yield event.plain_result("⚠️ 请私聊机器人使用此命令！")
            return

        _, room = self.game_manager.get_room_by_player(player_id)
        if not room:
            yield event.plain_result("❌ 你没有参与任何游戏！")
            return

        player = room.get_player(player_id)
        if not player or not player.role:
            yield event.plain_result("❌ 游戏尚未开始，角色还未分配！")
            return

        # 使用文本输出角色信息
        role_info = RoleFactory.get_role_info(player.role, player, room)
        yield event.plain_result(f"🎭 你的角色是：\n\n{role_info}")

    async def show_status(self, event: AstrMessageEvent) -> AsyncGenerator:
        """显示游戏状态（返回文本）"""
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("❌ 请在群聊中使用此命令！")
            return

        room = self.game_manager.get_room(group_id)
        if not room:
            yield event.plain_result("❌ 当前群没有进行中的游戏！")
            return

        # 构建状态文本
        status_text = (
            f"📊 游戏状态\n\n"
            f"阶段：{room.phase.value}\n"
            f"天数：第 {room.day_count} 天\n"
            f"存活人数：{room.alive_count}/{room.player_count}\n\n"
            f"玩家列表：\n"
        )

        for p in sorted(room.players.values(), key=lambda item: item.number or 999):
            status_icon = "✅" if p.is_alive else "💀"
            number = f"{p.number}号" if p.number else "未编号"
            status_text += f"  {status_icon} {number} - {table_name(p)}\n"

        yield event.plain_result(status_text)

    async def show_help(self, event: AstrMessageEvent) -> AsyncGenerator:
        """显示帮助（返回菜单图片）"""
        config = self.game_manager.config

        # 尝试生成菜单图片
        try:
            from ..draw import draw_menu_image

            image = draw_menu_image(config.total_players)
            output_path = self.tmp_dir / "werewolf_menu.png"
            image.save(output_path)

            yield event.image_result(str(output_path))
        except Exception as e:
            logger.warning(f"[狼人杀] 生成菜单图片失败: {e}，降级为文本")
            # 降级到文本菜单
            help_text = (
                "新爱莉都棋牌室 - 命令列表\n\n"
                "基础命令：\n"
                f"  {cmd('创建房间')} - 创建游戏房间\n"
                f"  {cmd('加入房间')} - 加入房间\n"
                f"  {cmd('AI角色列表')} - 查看角色卡AI\n"
                f"  {cmd('加入角色AI')} 名字/序号 - 添加角色卡AI\n"
                f"  {cmd('补满角色AI')} - 按默认名单补满AI\n"
                f"  {cmd('AI玩家列表')} - 查看当前AI\n"
                f"  {cmd('开始游戏')} - 开始游戏（房主）\n"
                f"  {cmd('查角色')} - 查看角色（私聊）\n"
                f"  {cmd('房间')} - 查看游戏状态\n"
                f"  {cmd('结束游戏')} - 结束游戏（房主）\n"
                f"  {cmd('关闭房间')} - 关闭当前群的狼人杀或璀璨房间（房主）\n"
                f"  {cmd('棋牌室自检')} - 检查角色卡、审计、关系图和LLM隔离\n"
                f"  {cmd('棋牌室审计')} - 查看当前/最近审计\n"
                f"  {cmd('棋牌室资产清单')} - 生成迁移资产清单\n\n"
                "璀璨宝石：\n"
                f"  {cmd('创建璀璨房间')} 2/3/4 - 创建 Splendor 房间\n"
                f"  {cmd('加入璀璨')} - 加入璀璨宝石\n"
                f"  {cmd('璀璨加入角色AI')} 名字/序号 - 添加角色卡AI\n"
                f"  {cmd('璀璨补满AI')} - 补满角色卡AI\n"
                f"  {cmd('开始璀璨')} - 开始璀璨宝石\n"
                f"  {cmd('璀璨状态')} - 查看牌面\n"
                f"  {cmd('关闭璀璨房间')} - 关闭璀璨宝石房间（房主）\n"
                f"  {cmd('璀璨帮助')} - 查看璀璨规则和动作命令\n\n"
                f"游戏命令（使用编号1-{config.total_players}）：\n"
                f"  {cmd('办掉')} 编号 - 狼人夜晚办掉\n"
                f"  {cmd('密谋')} 消息 - 狼人与队友交流\n"
                f"  {cmd('验人')} 编号 - 预言家查验\n"
                f"  {cmd('毒人')} 编号 - 女巫使用毒药\n"
                f"  {cmd('救人')} - 女巫使用解药\n"
                f"  {cmd('不操作')} - 女巫不使用道具\n"
                f"  {cmd('开枪')} 编号 - 猎人开枪带走\n"
                f"  {cmd('发言完毕')} - 发言说完\n"
                f"  {cmd('遗言完毕')} - 遗言说完\n"
                f"  {cmd('投票')} 编号 - 白天投票放逐\n"
                f"  {cmd('跳过发言')} - 跳过发言直接投票（房主）\n\n"
                "游戏规则：\n"
                f"• {config.total_players}人局：{config.werewolf_count}狼人 + {config.god_count}神 + {config.villager_count}平民\n"
                f"• 使用编号（1-{config.total_players}号）代替QQ号\n"
                "• AI发言优先称呼角色名字，编号只作为操作柄\n"
                "• 遗言规则：第一晚被狼杀有遗言，投票放逐有遗言，被毒无遗言\n"
                "• 猎人：被狼杀或投票放逐可开枪，被毒不能开枪\n"
                f"• 游戏结束后{'生成AI复盘报告' if config.enable_ai_review else '不生成AI复盘'}\n"
                "• 狼人胜利：好人 ≤ 狼人 或 神职全灭\n"
                "• 好人胜利：狼人全部出局"
            )
            yield event.plain_result(help_text)

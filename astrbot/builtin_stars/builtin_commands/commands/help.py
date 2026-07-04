import aiohttp

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.config.default import VERSION
from astrbot.core.star import command_management
from astrbot.core.utils.io import get_dashboard_version


class HelpCommand:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    HELP_TOPICS = {
        "璀璨宝石": "splendor",
        "璀璨": "splendor",
        "splendor": "splendor",
    }

    async def _query_astrbot_notice(self):
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.get(
                    "https://astrbot.app/notice.json",
                    timeout=2,
                ) as resp:
                    return (await resp.json())["notice"]
        except BaseException:
            return ""

    async def _build_reserved_command_lines(self) -> list[str]:
        """
        使用实时指令配置生成内置指令清单，确保重命名/禁用后与实际生效状态保持一致。
        """
        try:
            commands = await command_management.list_commands()
        except BaseException:
            return []

        lines: list[str] = []

        def walk(items: list[dict], indent: int = 0) -> None:
            for item in items:
                if not item.get("reserved") or not item.get("enabled"):
                    continue
                # 仅展示顶级指令或指令组
                if item.get("type") == "sub_command":
                    continue
                if item.get("parent_signature"):
                    continue

                effective = (
                    item.get("effective_command")
                    or item.get("original_command")
                    or item.get("handler_name")
                )
                if not effective or effective in [
                    "set",
                    "unset",
                    "help",
                    "dashboard_update",
                ]:
                    continue

                description = item.get("description") or ""
                desc_text = f" - {description}" if description else ""
                indent_prefix = "  " * indent
                lines.append(f"{indent_prefix}/{effective}{desc_text}")

        walk(commands)
        return lines

    def _extract_topic(self, event: AstrMessageEvent) -> str:
        text = (event.get_message_str() or "").strip()
        text = text.lstrip("/／").strip()
        if not text:
            return ""
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return ""
        return parts[1].strip()

    def _build_help_topic_message(self, topic: str) -> str:
        normalized = self.HELP_TOPICS.get(topic.strip().lower()) or self.HELP_TOPICS.get(
            topic.strip()
        )
        if normalized == "splendor":
            return self._build_splendor_help_message()
        return ""

    @staticmethod
    def _build_splendor_help_message() -> str:
        return "\n".join(
            [
                "内建帮助：璀璨宝石",
                "",
                "新爱莉都棋牌室的《璀璨宝石》支持 2-4 人，可由真人和角色卡 AI 混合游玩。",
                "AI 会使用已有米哈游角色卡人格；角色声纹和身份感优先于胜率，允许非最优和失误，规则结算由插件引擎保证。",
                "",
                "开局：",
                "/创建璀璨房间 2/3/4 - 创建房间",
                "/加入璀璨 - 真人加入",
                "/AI角色列表 - 查看可用角色卡 AI",
                "/璀璨加入角色AI 名字或序号 - 添加角色 AI",
                "/璀璨补满AI - 用角色 AI 补满人数",
                "/开始璀璨 - 房主开始",
                "",
                "行动：",
                "/拿宝石 白 蓝 绿 - 拿三枚不同色宝石",
                "/拿宝石 红 红 - 拿两枚同色宝石，银行该色需至少 4 枚",
                "/保留牌 T1-1 - 保留公开牌并尽量获得 1 金",
                "/保留牌 T2 - 盲保留二级牌堆顶牌",
                "/购买牌 T3-4 - 购买公开牌",
                "/购买牌 R1 - 购买自己的第 1 张预留牌",
                "/选择贵族 N1 - 同时满足多个贵族时选择一位",
                "/丢宝石 白 蓝 - 超过 10 枚后丢弃",
                "",
                "查询与结束：",
                "/璀璨状态 - 查看银行、市场、贵族、玩家状态和自己的预留牌",
                "/璀璨帮助 - 查看插件内完整规则说明",
                "/结束璀璨 - 房主强制结束",
                "/关闭璀璨房间 或 /关闭宝石房间 - 房主关闭房间",
                "",
                "规则摘要：保留上限 3 张；回合结束最多 10 枚宝石；15 分触发最终轮；最高分胜，平分时买牌更少者胜。",
            ]
        )

    async def help(self, event: AstrMessageEvent) -> None:
        """查看帮助"""
        topic = self._extract_topic(event)
        if topic:
            topic_message = self._build_help_topic_message(topic)
            if topic_message:
                event.set_result(
                    MessageEventResult().message(topic_message).use_t2i(False)
                )
                return

        notice = ""
        try:
            notice = await self._query_astrbot_notice()
        except BaseException:
            pass

        dashboard_version = await get_dashboard_version()
        command_lines = await self._build_reserved_command_lines()
        commands_section = (
            "\n".join(command_lines)
            if command_lines
            else "No enabled built-in commands."
        )

        msg_parts = [
            f"AstrBot v{VERSION}(WebUI: {dashboard_version})",
            commands_section,
            "可用帮助主题：/help 璀璨宝石",
        ]
        if notice:
            msg_parts.append(notice)
        msg = "\n".join(msg_parts)

        event.set_result(MessageEventResult().message(msg).use_t2i(False))

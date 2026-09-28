"""AstrBot Art (Playwright) Plugin - Main entry point.

A dedicated roleplay engine focused on narrative consumption:
1. Playwright plans events (hidden sub-loop with tools).
2. Actor delivers character soul & prose (main LLM without tools).
3. Scribe maintains relationship ledger in the background.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import yaml

from astrbot.api import logger, star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .core.cards import CharacterCardManager, get_generated_cards_dir
from .core.claim import (
    claim_session_for_art,
    is_art_claimed,
    is_rpg_claimed,
    release_session_claim,
)
from .core.db import ArtDatabase
from .core.state import ArtStateManager
from .layers.assemble import assemble_actor_request
from .layers.playwright import run_playwright
from .layers.scribe import run_scribe
from .tools.cast import execute_cast
from .tools.character import execute_fix_character
from .tools.recall import execute_recall
from .tools.scene import execute_change_scene

_BRACKET_DIRECTIVE_RE = re.compile(r"【(.*?)】")


def clean_narrative_reply(text: str) -> str:
    """Cleans leaked thinking artifacts and English meta-roleplay prefixes."""
    if not text:
        return ""
    # Strip thinking/scaffolding xml blocks
    cleaned = re.sub(
        r"<(?:think|thought|cot|xiaoai_core)>.*?</(?:think|thought|cot|xiaoai_core)>",
        "",
        text,
        flags=re.DOTALL,
    )
    # Strip unclosed thinking markers at start
    cleaned = re.sub(r"^<(?:think|thought|cot)>\s*", "", cleaned)
    # Strip common unquoted English meta reasoning prefixes like 'As Firefly, I should respond in character.'
    cleaned = re.sub(
        r"^\s*As\s+[\w\s\-]+?,\s+I\s+(?:should|will|must)\s+[^。\n]*?[.\n]\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


class ArtPlugin(star.Star):
    """Art (Playwright) role-play engine plugin."""

    def __init__(self, context: star.Context, config: dict | None = None) -> None:
        super().__init__(context, config)
        self.context = context
        self._config = config or {}

        data_root = Path(get_astrbot_data_path()) / "plugin_data" / "astrbot_plugin_art"
        data_root.mkdir(parents=True, exist_ok=True)
        self._data_root = data_root

        self.db = ArtDatabase(data_root)
        self.card_mgr = CharacterCardManager()
        presets_dir = Path(__file__).resolve().parent / "presets"
        self.state = ArtStateManager(self.db, self.card_mgr, presets_dir)

        self._playwright_provider = self._config.get("playwright_provider", "")
        self._scribe_provider = self._config.get("scribe_provider", "")
        self._enable_debug = bool(self._config.get("enable_debug", False))

        # Staging for multi-stage execution per turn
        self._turn_states: dict[str, dict[str, Any]] = {}

        # Prepare playwright toolset
        self._tool_set = self._build_playwright_toolset()

    def _build_playwright_toolset(self) -> ToolSet:
        """Constructs the ToolSet available exclusively to the Playwright sub-loop."""
        tool_set = ToolSet()

        async def change_scene_handler(
            location: str,
            time_of_day: str = "",
            present_characters: list[str] | None = None,
        ) -> str:
            session_id = tool_set.current_session_id
            return await execute_change_scene(
                self.state, session_id, location, time_of_day, present_characters
            )

        async def cast_handler(
            character_name: str, action: str = "enter", form: str = ""
        ) -> str:
            session_id = tool_set.current_session_id
            return await execute_cast(
                self.state, session_id, character_name, action, form
            )

        async def recall_handler(query: str, limit: int = 3) -> str:
            session_id = tool_set.current_session_id
            return await execute_recall(self.state, session_id, query, limit)

        async def fix_character_handler(
            character_name: str, action: str, details: str = ""
        ) -> str:
            session_id = tool_set.current_session_id
            return await execute_fix_character(
                self.state, session_id, character_name, action, details
            )

        tool_set.add_tool(
            FunctionTool(
                name="change_scene",
                description="切换当前场景。只有当玩家同意或明确决定前往新地点时才调用。返回新场景环境描述与本场变数牌。",
                parameters={
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "新场景地点名称"},
                        "time_of_day": {
                            "type": "string",
                            "description": "新场景时间切片（如清晨、午后、黄昏、夜晚）",
                        },
                        "present_characters": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "在场角色列表",
                        },
                    },
                    "required": ["location"],
                },
                handler=change_scene_handler,
            )
        )
        tool_set.add_tool(
            FunctionTool(
                name="cast",
                description="角色登场或离场。action 为 'enter'（登场）或 'leave'（离场）。登场时若无现有角色卡，会自动按规范生成并落地。返回完整外貌及当前状态。",
                parameters={
                    "type": "object",
                    "properties": {
                        "character_name": {"type": "string", "description": "角色名称"},
                        "action": {
                            "type": "string",
                            "enum": ["enter", "leave"],
                            "description": "登场(enter)或离场(leave)",
                        },
                        "form": {"type": "string", "description": "角色当前形态或服装"},
                    },
                    "required": ["character_name"],
                },
                handler=cast_handler,
            )
        )
        tool_set.add_tool(
            FunctionTool(
                name="recall",
                description="翻阅过往已完结场景的记忆与摘要。返回相关场景的历史摘要。",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词或主题"},
                        "limit": {
                            "type": "integer",
                            "description": "返回条数限制",
                            "default": 3,
                        },
                    },
                    "required": ["query"],
                },
                handler=recall_handler,
            )
        )
        tool_set.add_tool(
            FunctionTool(
                name="fix_character",
                description="修正本 session 的生成角色卡。action: 'update'（增量修改局部属性/外貌/设定）、'regenerate'（根据新要求整张重写）、'delete'（删除该生成卡）。",
                parameters={
                    "type": "object",
                    "properties": {
                        "character_name": {"type": "string", "description": "角色名称"},
                        "action": {
                            "type": "string",
                            "enum": ["update", "regenerate", "delete"],
                            "description": "操作类型",
                        },
                        "details": {
                            "type": "string",
                            "description": "具体更新或重写内容",
                        },
                    },
                    "required": ["character_name", "action"],
                },
                handler=fix_character_handler,
            )
        )
        return tool_set

    def _remove_art_tools(self, req: ProviderRequest) -> None:
        """Removes art tools from request if it belongs to another plugin."""
        art_tool_names = {"change_scene", "cast", "recall", "fix_character"}
        if req.func_tool and hasattr(req.func_tool, "tools"):
            tools = getattr(req.func_tool, "tools", {})
            if isinstance(tools, dict):
                for name in list(tools.keys()):
                    if name in art_tool_names:
                        tools.pop(name, None)

    # ==================================================================
    # Hooks
    # ==================================================================

    @filter.on_llm_request()
    async def on_art_llm_request(
        self, event: AstrMessageEvent, req: ProviderRequest
    ) -> None:
        """Main ingress hook: checks claim, runs Playwright, assembles Actor prompt."""
        session_id = event.unified_msg_origin

        # 1. Check claim exclusivity
        if not await is_art_claimed(session_id, self.db):
            self._remove_art_tools(req)
            return

        if self._enable_debug:
            logger.info(f"[Art] on_llm_request start for session {session_id}")

        player_input = event.message_str or ""

        # 2. Check for bracket directives reverting mistaken scene transitions
        prev_scene = await self.db.get_current_scene(session_id)
        if "【还在" in player_input or "【回" in player_input:
            match = re.search(r"【(?:还在|回到)(.*?)】", player_input)
            if match and prev_scene:
                loc_target = match.group(1).strip()
                if loc_target:
                    await self.state.change_scene(session_id, loc_target)

        # 3. Record scene state prior to playwright tool execution
        scene_before = await self.db.get_current_scene(session_id)

        # 4. Set session ID on playwright toolset
        self._tool_set.current_session_id = session_id

        # 5. Run hidden Playwright loop to generate Director Notes
        director_notes = await run_playwright(
            star_context=self.context,
            event=event,
            state=self.state,
            session_id=session_id,
            player_input=player_input,
            provider_id=self._playwright_provider or None,
            tool_set=self._tool_set,
        )

        # 6. Check if scene changed during playwright execution
        scene_after = await self.db.get_current_scene(session_id)
        scene_transition_notice = ""
        scene_switched_from = None

        if (
            scene_before
            and scene_after
            and scene_before.get("id") != scene_after.get("id")
        ):
            scene_switched_from = scene_before
            loc = scene_after.get("location", "")
            time_slice = scene_after.get("time_of_day", "")
            scene_transition_notice = f"📍 {loc} · {time_slice}"

        # 7. Assemble Actor's request and strip tools from Actor
        await assemble_actor_request(
            req=req,
            state=self.state,
            session_id=session_id,
            director_notes=director_notes,
            scene_transition_notice=scene_transition_notice,
        )

        # 8. Save context staging for the background Scribe
        self._turn_states[session_id] = {
            "player_input": player_input,
            "scene_switched_from": scene_switched_from,
        }

    @filter.on_llm_response()
    async def on_art_llm_response(
        self, event: AstrMessageEvent, resp: LLMResponse
    ) -> None:
        """Ingress after Actor replies: non-blocking background Scribe execution."""
        session_id = event.unified_msg_origin
        if not await is_art_claimed(session_id, self.db):
            return

        staging = self._turn_states.pop(session_id, {})
        player_input = staging.get("player_input", event.message_str or "")
        actor_reply = resp.completion_text or ""
        cleaned_reply = clean_narrative_reply(actor_reply)
        if cleaned_reply and cleaned_reply != actor_reply:
            resp.completion_text = cleaned_reply
            actor_reply = cleaned_reply

        scene_switched = staging.get("scene_switched_from")

        # Launch background Scribe without blocking response delivery
        asyncio.create_task(
            run_scribe(
                star_context=self.context,
                event=event,
                state=self.state,
                session_id=session_id,
                player_input=player_input,
                actor_response=actor_reply,
                provider_id=self._scribe_provider or None,
                scene_switched_from=scene_switched,
            )
        )

    # ==================================================================
    # Tools (Exposed for AstrBot global catalog compatibility)
    # ==================================================================

    @filter.llm_tool(name="change_scene")
    async def tool_change_scene(
        self,
        event: AstrMessageEvent,
        location: str,
        time_of_day: str = "",
        present_characters: list[str] | None = None,
    ) -> str:
        """切换当前场景。只有当玩家同意或明确决定前往新地点时才调用。返回新场景环境描述与本场变数牌。"""
        return await execute_change_scene(
            self.state,
            event.unified_msg_origin,
            location,
            time_of_day,
            present_characters,
        )

    @filter.llm_tool(name="cast")
    async def tool_cast(
        self,
        event: AstrMessageEvent,
        character_name: str,
        action: str = "enter",
        form: str = "",
    ) -> str:
        """角色登场或离场。action 为 'enter'（登场）或 'leave'（离场）。登场时若无现有角色卡，会自动按规范生成并落地。返回完整外貌及当前状态。"""
        return await execute_cast(
            self.state, event.unified_msg_origin, character_name, action, form
        )

    @filter.llm_tool(name="recall")
    async def tool_recall(
        self,
        event: AstrMessageEvent,
        query: str,
        limit: int = 3,
    ) -> str:
        """翻阅过往已完结场景的记忆与摘要。返回相关场景的历史摘要。"""
        return await execute_recall(self.state, event.unified_msg_origin, query, limit)

    @filter.llm_tool(name="fix_character")
    async def tool_fix_character(
        self,
        event: AstrMessageEvent,
        character_name: str,
        action: str,
        details: str = "",
    ) -> str:
        """修正本 session 的生成角色卡。action: 'update'（增量修改局部属性/外貌/设定）、'regenerate'（根据新要求整张重写）、'delete'（删除该生成卡）。"""
        return await execute_fix_character(
            self.state, event.unified_msg_origin, character_name, action, details
        )

    # ==================================================================
    # Commands: /art group (7 commands)
    # ==================================================================

    @filter.command_group("art")
    def art(self):
        """Art 剧作家主命令组"""

    @art.command("start")
    async def art_start(
        self,
        event: AstrMessageEvent,
        character_name: str = "",
        relationship_premise: str = "恋人",
        preset_name: str = "default",
    ):
        """开局进入剧作家模式：认领归属，初始化角色与世界

        Args:
            character_name(string): 初始在场角色名称（如流萤、爱莉希雅）
            relationship_premise(string): 初始关系前提（如“恋人，同居第三个月”）
            preset_name(string): 世界观预设（default, star-rail, elysium, genshin）
        """
        session_id = event.unified_msg_origin

        # Check RPG claim exclusivity
        if is_rpg_claimed(session_id):
            yield event.plain_result(
                "❌ 当前会话已被 RPG 插件占用！\n"
                "一个会话只能属于 RPG 或 Art 之一。请先在 RPG 插件中执行 `/rpg reset` 释放归属，或切换至新的会话使用。"
            )
            return

        sender_name = event.get_sender_name() or "开拓者"
        success, msg = await claim_session_for_art(
            session_id=session_id,
            db=self.db,
            preset=preset_name,
            relationship_premise=relationship_premise,
            player_name=sender_name,
        )
        if not success:
            yield event.plain_result(f"❌ {msg}")
            return

        init_info = await self.state.init_session(
            session_id=session_id,
            character_name=character_name,
            relationship_premise=relationship_premise,
            preset_name=preset_name,
            player_name=sender_name,
        )

        res_lines = [
            "✨ 【Art 剧作家模式已启动】",
            f"- 角色：{character_name or '自由舞台'}",
            f"- 舞台：{init_info['preset']}",
            f"- 关系前提：{relationship_premise}",
            f"- 初始场景：{init_info['location']}",
            f"- 今日底色：{init_info['daily_tone']}",
            "",
            "剧本已就位。无需构思大纲，直接输入你想对她说的话即可开始。",
        ]
        yield event.plain_result("\n".join(res_lines))

    @art.command("forget")
    async def art_forget(self, event: AstrMessageEvent, count: int = 1):
        """回滚最近 n 轮互动，连同世界状态与账本记录一起回退

        Args:
            count(number): 回退轮数，默认为 1
        """
        session_id = event.unified_msg_origin
        if not await is_art_claimed(session_id, self.db):
            yield event.plain_result(
                "当前会话尚未启动 Art 模式。请使用 `/art start` 开始。"
            )
            return

        count = max(1, min(count, 10))
        await self.db.rollback_recent_turns(session_id, count)

        # Rollback message history in conversation manager
        conv_mgr = getattr(self.context, "conversation_manager", None)
        if conv_mgr:
            try:
                curr_cid = await conv_mgr.get_curr_conversation_id(session_id)
                if curr_cid:
                    conv = await conv_mgr.get_conversation(
                        session_id, curr_cid, create_if_not_exists=False
                    )
                    if conv and conv.history:
                        history = json.loads(conv.history)
                        # Drop 2 turns per count (user + assistant)
                        drop_items = count * 2
                        new_history = (
                            history[:-drop_items] if len(history) > drop_items else []
                        )
                        await conv_mgr.update_conversation(
                            session_id, curr_cid, history=new_history
                        )
            except Exception as e:
                logger.warning(f"[Art] Failed to trim conversation history: {e}")

        yield event.plain_result(
            f"⏪ 已成功回滚最近 {count} 轮互动，同步回退了相关账本与场景记录。"
        )

    @art.command("card")
    async def art_card(self, event: AstrMessageEvent, character_name: str = ""):
        """查看本 session 角色卡。不带名字列出所有生成卡，带名字打印详情与路径

        Args:
            character_name(string): 角色名字，留空则列出本会话生成卡列表
        """
        session_id = event.unified_msg_origin
        if not character_name:
            cards = self.card_mgr.list_generated_cards(session_id)
            if not cards:
                yield event.plain_result(
                    "📄 本会话暂无生成的角色卡。\n"
                    "如需查看官方卡，请指定角色名字，如 `/art card 流萤`。"
                )
                return
            lines = [f"📄 【本会话生成卡列表（共 {len(cards)} 张）】"]
            for c in cards:
                sup = (
                    "（已被官方 Canonical 卡覆盖，以官方为准）"
                    if c["superseded_by_canonical"]
                    else ""
                )
                lines.append(f"- {c['name']} {sup}\n  文件：{c['path']}")
            yield event.plain_result("\n".join(lines))
            return

        card, source, path = self.card_mgr.resolve_card(character_name, session_id)
        if not card:
            yield event.plain_result(f"❌ 未找到角色【{character_name}】的设定卡。")
            return

        source_label = (
            "官方 Canonical 卡（只读）" if source == "canonical" else "会话生成卡"
        )
        path_str = str(path) if path else "内置/官方目录"
        card_yaml = yaml.dump(card, allow_unicode=True, sort_keys=False)

        # Truncate if excessively long for chat output
        if len(card_yaml) > 1500:
            card_yaml = card_yaml[:1500] + "\n...（内容过长已截断）"

        out = (
            f"📄 【角色卡：{card.get('name', character_name)}】（{source_label}）\n"
            f"路径：{path_str}\n\n"
            f"```yaml\n{card_yaml}\n```"
        )
        yield event.plain_result(out)

    @art.command("ledger")
    async def art_ledger(self, event: AstrMessageEvent):
        """查看她牢牢记住的关于你的细节、承诺与当前节奏偏好"""
        session_id = event.unified_msg_origin
        if not await is_art_claimed(session_id, self.db):
            yield event.plain_result(
                "当前会话尚未启动 Art 模式。请使用 `/art start` 开始。"
            )
            return

        sess = await self.db.get_session(session_id)
        entries = await self.db.get_ledger_entries(session_id)

        lines = [
            "📖 【关于你的关系账本（真实细节）】",
            f"- 称谓：{sess.get('player_name', '开拓者') if sess else '开拓者'}",
            f"- 关系前提：{sess.get('relationship_premise', '未设定') if sess else '未设定'}",
            f"- 当日底色：{sess.get('daily_tone', '平和') if sess else '平和'}",
            "",
        ]

        promises = [e["value"] for e in entries if e.get("category") == "promise"]
        memories = [e["value"] for e in entries if e.get("category") == "memory"]
        gifts = [e["value"] for e in entries if e.get("category") == "gift"]
        tiffs = [e["value"] for e in entries if e.get("category") == "tiff"]
        pacing = [
            e["value"] for e in entries if e.get("category") == "pacing_preference"
        ]
        profiles = [
            f"{e['key']}: {e['value']}"
            for e in entries
            if e.get("category") == "player_profile"
        ]

        if promises:
            lines.append("【说过的承诺（仅记录亲口所说）】")
            for p in promises:
                lines.append(f"  * {p}")
        if memories:
            lines.append("\n【共同回忆】")
            for m in memories:
                lines.append(f"  * {m}")
        if gifts:
            lines.append("\n【礼物与纪念物】")
            for g in gifts:
                lines.append(f"  * {g}")
        if tiffs:
            lines.append("\n【还未消解的小别扭】")
            for t in tiffs:
                lines.append(f"  * {t}")
        if pacing:
            lines.append(f"\n【节奏偏好】{'；'.join(pacing)}")
        if profiles:
            lines.append(f"\n【画像线索】{'；'.join(profiles)}")

        if len(lines) <= 5:
            lines.append("（相处才刚刚开始，随着故事推进，她会悄悄记下更多细节。）")

        yield event.plain_result("\n".join(lines))

    @art.command("reset")
    async def art_reset(self, event: AstrMessageEvent):
        """清空本会话存档，删除生成卡，释放会话归属独占"""
        session_id = event.unified_msg_origin
        cards_dir = get_generated_cards_dir()
        await release_session_claim(session_id, self.db, cards_dir=cards_dir)
        yield event.plain_result(
            "🧹 本会话 Art 存档已全部清空，生成卡已清理，会话归属已释放。"
        )

    @art.command("debug")
    async def art_debug(self, event: AstrMessageEvent):
        """调试指令：打印当前场景、在场角色、中期剧本、变数与账本全景"""
        session_id = event.unified_msg_origin
        if not await is_art_claimed(session_id, self.db):
            yield event.plain_result("当前会话尚未认领 Art 模式。")
            return

        sess = await self.db.get_session(session_id)
        scene = await self.db.get_current_scene(session_id)
        chars = await self.db.get_present_characters(session_id)
        scripts = await self.db.get_active_scripts(session_id)
        ledger = await self.db.get_ledger_entries(session_id)

        info = {
            "session": sess,
            "current_scene": scene,
            "present_cast": chars,
            "active_scripts": scripts,
            "ledger_count": len(ledger),
            "recent_ledger": ledger[-5:],
        }
        dump_str = json.dumps(info, ensure_ascii=False, indent=2)
        if len(dump_str) > 1800:
            dump_str = dump_str[:1800] + "\n...（已截断）"
        yield event.plain_result(f"🛠️ 【Art 运行态全景】\n```json\n{dump_str}\n```")

    @art.command("help")
    async def art_help(self, event: AstrMessageEvent):
        """查看 Art 剧作家所有可用命令"""
        help_text = (
            "🎭 【Art 剧作家命令列表】\n\n"
            "• `/art start [角色名] [关系前提] [世界观]`\n"
            "  开局启动：声明归属，选择角色与世界，进入剧作模式。\n\n"
            "• `/art forget [n]`\n"
            "  回滚最近 n 轮互动，同步回退世界状态、账本与场景。\n\n"
            "• `/art card [名字]`\n"
            "  查看角色卡。不带名字列出本会话生成卡；带名字打印详情与文件路径。\n\n"
            "• `/art ledger`\n"
            "  查看关系账本：她为你记住的细节、承诺、礼物与节奏偏好。\n\n"
            "• `/art reset`\n"
            "  清档并释放归属：清空本会话数据，删除生成卡，解除独占。\n\n"
            "• `/art debug`\n"
            "  排查诊断：一次性打出当前场景、在场角色、活跃剧本与变数。\n\n"
            "• `/art help`\n"
            "  查看本帮助指南。\n\n"
            "💡 提示：在对话中使用 `【】`（如 `【去海边】`、`【最近别折腾我】`）具有最高优先级，编剧与演员将无条件执行。"
        )
        yield event.plain_result(help_text)

    # ==================================================================
    # Lifecycle
    # ==================================================================

    async def star_shutdown(self):
        """Clean shutdown: closes all database connections."""
        await self.db.close_all()
        logger.info("[Art] Plugin shut down, all database connections closed.")

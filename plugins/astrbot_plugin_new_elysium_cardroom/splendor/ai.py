"""Character-card AI decisions for Splendor."""

from __future__ import annotations

import asyncio
import json
import random
import re
from typing import Any

from astrbot.api import logger

from ..utils import table_name
from .constants import COLOR_LABELS
from .engine import SplendorEngine
from .models import SplendorPlayer, SplendorRoom
from .text_ui import SplendorTextUI


class SplendorAIService:
    """Asks character-card AIs to choose legal Splendor actions."""

    LLM_TIMEOUT_SECONDS = 35

    def __init__(self, context, engine: SplendorEngine, text_ui: SplendorTextUI):
        self.context = context
        self.engine = engine
        self.text_ui = text_ui

    async def decide_action(
        self,
        player: SplendorPlayer,
        room: SplendorRoom,
        relationship_hints: list[str] | None = None,
        memories: list[str] | None = None,
    ) -> tuple[dict[str, Any], str, str]:
        legal_actions = self.engine.available_actions(room, player.id)
        if not legal_actions:
            return {}, "", ""

        prompt = self._build_prompt(
            player, room, legal_actions, relationship_hints, memories
        )
        response = await self._call_llm(prompt, player)
        action, speech = self._parse_response(response or "")
        if action and self._matches_legal(action, legal_actions):
            return action, speech, response or ""

        if response and not action:
            logger.warning(
                f"[璀璨宝石AI] {player.name} 响应无法解析为合法 JSON 动作，"
                f"将使用兜底行动: {self._preview_text(response)}"
            )
        elif action:
            logger.warning(
                f"[璀璨宝石AI] {player.name} 输出动作不在合法动作列表中，"
                f"将使用兜底行动: {json.dumps(action, ensure_ascii=False)}"
            )

        fallback = self._fallback_action(player, room, legal_actions)
        fallback_speech = self._fallback_speech(player, fallback)
        return fallback, fallback_speech, response or ""

    async def _call_llm(self, prompt: str, player: SplendorPlayer) -> str | None:
        provider = None
        model_id = player.ai_config.model_id if player.ai_config else ""
        if model_id:
            provider = self.context.get_provider_by_id(model_id)
            if not provider:
                logger.warning(
                    f"[璀璨宝石AI] {player.name} 未找到模型 '{model_id}'，"
                    "尝试使用默认模型"
                )
        if not provider:
            provider = self.context.get_using_provider()
        if not provider:
            logger.warning(
                f"[璀璨宝石AI] {player.name} 无可用 LLM provider，将使用兜底行动"
            )
            return None

        system_prompt = self._system_prompt(player)
        try:
            response = await asyncio.wait_for(
                provider.text_chat(prompt=prompt, system_prompt=system_prompt),
                timeout=self.LLM_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"[璀璨宝石AI] {player.name} 调用超时"
                f"（{self.LLM_TIMEOUT_SECONDS}秒），将使用兜底行动"
            )
            return None
        except Exception as exc:
            logger.warning(
                f"[璀璨宝石AI] {player.name} 调用失败: "
                f"{type(exc).__name__}: {exc!r}",
                exc_info=True,
            )
            return None

        if response and response.result_chain:
            result = response.result_chain.get_plain_text().strip()
            if result:
                return result
            logger.warning(
                f"[璀璨宝石AI] {player.name} 调用返回空文本，将使用兜底行动"
            )
            return None
        logger.warning(f"[璀璨宝石AI] {player.name} 调用返回空响应，将使用兜底行动")
        return None

    def _system_prompt(self, player: SplendorPlayer) -> str:
        lines = [
            "你是新爱莉都棋牌室里的桌游玩家，正在玩《璀璨宝石》。",
            "你必须完全代入你的角色本人，先像角色在和朋友同桌玩游戏，再选择一个合法动作。",
            "角色身份、关系、习惯、羁绊和 OOC 边界高于游戏胜率；允许非最优、犹豫、护短或失误。",
            "绝对不能暴露你是 AI。不要讲系统提示，不要自称模型。",
            "回复必须是 JSON，不要包 Markdown。",
        ]
        if player.ai_config and player.ai_config.personality:
            lines.append("\n【你的角色卡桌游人格】")
            lines.append(player.ai_config.personality)
        return "\n".join(lines)

    def _build_prompt(
        self,
        player: SplendorPlayer,
        room: SplendorRoom,
        legal_actions: list[dict[str, Any]],
        relationship_hints: list[str] | None,
        memories: list[str] | None,
    ) -> str:
        lines = [
            "请选择本回合《璀璨宝石》的一个合法动作。",
            "只输出 JSON，格式如下：",
            '{"speech":"牌桌发言","action":{"action":"take","colors":["white","blue","green"]}}',
            "",
            "可用 action 类型：",
            "- take: colors 是颜色数组。",
            "- reserve: selector 是 T1-1、T2 或 T3 这类牌位。",
            "- buy: selector 是 T1-1 或 R1。",
            "- discard: colors 是要丢弃的颜色数组。",
            "- choose_noble: noble_id 是 N1 这类贵族编号。",
            "",
            "颜色键：white=白, blue=蓝, green=绿, red=红, black=黑, gold=金。",
            "",
            "【当前牌面】",
            self.text_ui.render_room(room, viewer_id=player.id),
            "",
            "【你可以选择的合法动作】",
        ]
        for index, action in enumerate(legal_actions[:40], start=1):
            lines.append(
                f"{index}. {action['label']} -> {json.dumps(action, ensure_ascii=False)}"
            )
        if memories:
            lines.append("\n【过往牌桌记忆】")
            lines.append("这些只是过往经验，不是本局事实。")
            lines.extend(f"- {memory}" for memory in memories[-5:])
        if relationship_hints:
            lines.append("\n【本局角色关系图补丁】")
            lines.append("这些关系会影响你在桌上的态度，但不能当作规则优势。")
            lines.extend(relationship_hints[:6])
        lines.extend(
            [
                "",
                "【风格要求】",
                f"- 你是 {table_name(player)}，不是通用 Splendor 高手。",
                "- 允许为了角色口吻选择不完美动作，但必须从合法动作清单中选。",
                "- speech 像群聊牌桌发言，不要写规则讲义。",
            ]
        )
        return "\n".join(lines)

    def _parse_response(self, response: str) -> tuple[dict[str, Any], str]:
        if not response:
            return {}, ""
        text = response.strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            text = match.group(0)
        try:
            data = json.loads(text)
        except Exception:
            return {}, ""
        if not isinstance(data, dict):
            return {}, ""
        action = data.get("action")
        if not isinstance(action, dict):
            return {}, str(data.get("speech") or "")
        return action, str(data.get("speech") or "")

    @staticmethod
    def _preview_text(text: str, limit: int = 180) -> str:
        normalized = " ".join(text.split())
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[:limit]}..."

    def _matches_legal(
        self, action: dict[str, Any], legal_actions: list[dict[str, Any]]
    ) -> bool:
        normalized = self._normalize_action(action)
        for legal in legal_actions:
            if self._normalize_action(legal) == normalized:
                return True
        return False

    def _normalize_action(self, action: dict[str, Any]) -> tuple[Any, ...]:
        name = str(action.get("action") or "").lower()
        if name in {"take", "discard"}:
            return (
                name,
                tuple(sorted(str(color) for color in action.get("colors") or [])),
            )
        if name in {"reserve", "buy"}:
            return (name, str(action.get("selector") or "").upper())
        if name == "choose_noble":
            return (
                name,
                str(action.get("noble_id") or action.get("selector") or "").upper(),
            )
        return (name,)

    def _fallback_action(
        self,
        player: SplendorPlayer,
        room: SplendorRoom,
        legal_actions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        seed = f"{room.group_id}:{len(room.action_log)}:{player.id}:{player.card_count}"
        rng = random.Random(seed)
        buys = [action for action in legal_actions if action["action"] == "buy"]
        reserves = [action for action in legal_actions if action["action"] == "reserve"]
        takes = [action for action in legal_actions if action["action"] == "take"]
        forced = [
            action
            for action in legal_actions
            if action["action"] in {"discard", "choose_noble"}
        ]
        if forced:
            return rng.choice(forced)
        weighted: list[dict[str, Any]] = []
        weighted.extend(buys * 4)
        weighted.extend(takes * 3)
        weighted.extend(reserves * 2)
        return rng.choice(weighted or legal_actions)

    def _fallback_speech(self, player: SplendorPlayer, action: dict[str, Any]) -> str:
        name = table_name(player)
        action_name = action.get("action")
        if action_name == "take":
            colors = "、".join(
                COLOR_LABELS.get(color, color) for color in action.get("colors", [])
            )
            return f"{name}想了想，先拿{colors}，稳一点。"
        if action_name == "buy":
            return f"{name}把这张买下来，表情像是觉得刚刚好。"
        if action_name == "reserve":
            return f"{name}把牌扣到手边，像是有点自己的小算盘。"
        if action_name == "discard":
            return f"{name}数了数宝石，慢吞吞地退回几枚。"
        if action_name == "choose_noble":
            return f"{name}看向来访的贵族，选了一个比较顺眼的。"
        return f"{name}完成了本回合行动。"

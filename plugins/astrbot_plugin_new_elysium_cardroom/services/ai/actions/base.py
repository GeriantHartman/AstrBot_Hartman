"""行动基类 - 所有AI行动的基础"""

import asyncio
import re
from typing import TYPE_CHECKING, Any

from astrbot.api import logger

if TYPE_CHECKING:
    from ....models import GameRoom, Player


class BaseAction:
    """AI行动基类"""

    LLM_TIMEOUT_SECONDS = 30

    def __init__(self, context):
        self.context = context

    def _get_provider(self, model_id: str = ""):
        """获取LLM provider"""
        if model_id:
            provider = self.context.get_provider_by_id(model_id)
            if not provider:
                logger.warning(f"[狼人杀AI] 未找到模型 '{model_id}'，使用默认模型")
                provider = self.context.get_using_provider()
        else:
            provider = self.context.get_using_provider()
        return provider

    async def _call_llm(
        self,
        prompt: str,
        player: "Player",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = None,
        audit_context: dict[str, Any] | None = None,
    ) -> str | None:
        """调用LLM获取AI决策（带重试和超时保护）"""
        model_id = ""
        if player.ai_config:
            model_id = player.ai_config.model_id
            max_retries = player.ai_config.max_retries
            retry_delay = player.ai_config.retry_delay

        if timeout is None:
            timeout = self.LLM_TIMEOUT_SECONDS

        provider = self._get_provider(model_id)
        if not provider:
            logger.error("[狼人杀AI] 无法获取LLM provider")
            return None

        system_prompt = self._system_prompt(player)
        last_error = ""
        for attempt in range(max_retries):
            try:
                response = await asyncio.wait_for(
                    provider.text_chat(prompt=prompt, system_prompt=system_prompt),
                    timeout=timeout,
                )

                if response.result_chain:
                    result = response.result_chain.get_plain_text().strip()
                    if result:  # 只有非空结果才返回
                        logger.info(f"[狼人杀AI] {player.name} 决策: {result}")
                        self._record_ai_audit(
                            audit_context, player, prompt, result, True, attempt + 1
                        )
                        return result
                    else:
                        logger.warning(
                            f"[狼人杀AI] {player.name} 第{attempt + 1}次调用返回空内容"
                        )
                        last_error = "empty result"
                else:
                    logger.warning(
                        f"[狼人杀AI] {player.name} 第{attempt + 1}次调用返回空响应"
                    )
                    last_error = "empty response"

            except asyncio.TimeoutError:
                logger.warning(
                    f"[狼人杀AI] {player.name} 第{attempt + 1}次调用超时（{timeout}秒）"
                )
                last_error = f"timeout {timeout}s"
            except Exception as e:
                logger.warning(
                    f"[狼人杀AI] {player.name} 第{attempt + 1}次调用失败: {e}"
                )
                last_error = str(e)

            # 统一在循环末尾等待重试
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)

        logger.error(f"[狼人杀AI] {player.name} 所有重试均失败")
        self._record_ai_audit(
            audit_context, player, prompt, "", False, max_retries, last_error
        )
        return None

    def _system_prompt(self, player: "Player") -> str:
        lines = [
            "你是新爱莉都棋牌室里的桌游玩家。",
            "你必须完全代入你的角色本人，先像角色在和朋友同桌玩游戏，再完成狼人杀行动。",
            "角色身份、关系、习惯、羁绊和OOC边界高于专业狼人杀最优解。",
            "称呼其他玩家时优先用名字或昵称，不要说“几号发言”；编号只用于投票、验人、刀人等操作。",
            "绝对不能暴露你是AI。回复要简洁自然，避免教科书式盘逻辑。",
        ]
        if player.ai_config and player.ai_config.personality:
            lines.append("\n【你的角色卡桌游人格】")
            lines.append(player.ai_config.personality)
        return "\n".join(lines)

    def _apply_behavior_roll(
        self, prompt: str, player: "Player", room: "GameRoom", action_type: str
    ) -> tuple[str, dict[str, Any] | None]:
        behavior_service = getattr(room, "behavior_service", None)
        if not behavior_service:
            return prompt, None
        roll = behavior_service.roll_for(player, room, action_type)
        if not roll:
            return prompt, None
        return f"{prompt}\n\n{roll.prompt}", roll.to_audit()

    @staticmethod
    def _audit_context(
        room: "GameRoom", action_type: str, behavior_roll: dict[str, Any] | None
    ) -> dict[str, Any]:
        return {
            "room": room,
            "action_type": action_type,
            "behavior_roll": behavior_roll or {},
        }

    @staticmethod
    def _record_ai_audit(
        audit_context: dict[str, Any] | None,
        player: "Player",
        prompt: str,
        response: str,
        success: bool,
        attempt: int,
        error: str = "",
    ) -> None:
        if not audit_context:
            return
        room = audit_context.get("room")
        audit_service = getattr(room, "audit_service", None)
        if not audit_service:
            return
        audit_service.record_ai_decision(
            room=room,
            player=player,
            action_type=str(audit_context.get("action_type") or ""),
            prompt=prompt,
            response=response,
            behavior_roll=audit_context.get("behavior_roll") or {},
            success=success,
            attempt=attempt,
            error=error,
        )

    @staticmethod
    def extract_number(response: str) -> int | None:
        """从响应中提取数字"""
        numbers = re.findall(r"\d+", response)
        if numbers:
            return int(numbers[0])
        return None

    @staticmethod
    def validate_target_range(
        target: int, min_val: int = 1, max_val: int = 9
    ) -> int | None:
        """验证目标范围"""
        if min_val <= target <= max_val:
            return target
        return None

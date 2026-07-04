"""投票行动 - 白天投票"""

import re
from typing import TYPE_CHECKING

from astrbot.api import logger

from ....utils import replace_room_number_mentions, strip_leading_number_speech
from ..context import BehaviorAnalyzer, ContextBuilder, SituationAnalyzer
from ..prompts import (
    ANTI_HALLUCINATION_PROTOCOL,
    HUMAN_STYLE_TIPS,
    ROLE_PROMPTS,
    ROLE_SOUL_SETTINGS,
    VOTE_TIPS,
)
from ..validators import TargetValidator
from .base import BaseAction

if TYPE_CHECKING:
    from ....models import GameRoom, Player


class VoteAction(BaseAction):
    """投票行动"""

    async def decide_vote(
        self,
        player: "Player",
        room: "GameRoom",
        is_pk: bool = False,
        pk_candidates: list[str] = None,
    ) -> tuple[str, int | None]:
        """AI生成投票决策"""
        context = ContextBuilder.build_context(player, room)
        context += "\n" + SituationAnalyzer.get_situation_awareness(room)

        # 检查特殊事件
        special_event_tip = ContextBuilder.get_special_event_tip(player, room)
        if special_event_tip:
            context += "\n" + special_event_tip

        # 添加战术指令
        tactical_directive = SituationAnalyzer.get_tactical_directive(player, room)
        if tactical_directive:
            context += "\n" + tactical_directive

        # 添加玩家行为分析
        behavior_analysis = BehaviorAnalyzer.get_behavior_analysis_prompt(player, room)
        if behavior_analysis:
            context += "\n" + behavior_analysis

        role_key = ContextBuilder.get_role_key(player)
        soul_setting = ROLE_SOUL_SETTINGS.get(role_key, "")
        vote_tips = VOTE_TIPS.get(role_key, VOTE_TIPS["villager"])

        prompt = ROLE_PROMPTS["day_vote"].format(
            anti_hallucination=ANTI_HALLUCINATION_PROTOCOL,
            soul_setting=soul_setting,
            context=context,
            vote_tips=vote_tips,
            human_style=HUMAN_STYLE_TIPS,
        )

        action_type = "pk_vote" if is_pk else "day_vote"
        prompt, behavior_roll = self._apply_behavior_roll(
            prompt, player, room, action_type
        )
        response = await self._call_llm(
            prompt,
            player,
            audit_context=self._audit_context(room, action_type, behavior_roll),
        )

        speech = ""
        vote_target = None

        if response:
            # 解析发言
            speech_match = re.search(
                r"\[发言\]\s*(.+?)(?=\[投票\]|$)", response, re.DOTALL
            )
            if speech_match:
                speech = speech_match.group(1).strip()
                speech = strip_leading_number_speech(speech)
                speech = replace_room_number_mentions(
                    speech, room, include_operation=False
                )

            # 解析投票
            vote_match = re.search(r"\[投票\]\s*(\d+|弃票)", response)
            if vote_match:
                vote_str = vote_match.group(1)
                if vote_str != "弃票":
                    try:
                        raw_target = int(vote_str)
                        # 使用验证器确保目标有效
                        vote_target = TargetValidator.validate_vote_target(
                            room, raw_target, player
                        )
                        if vote_target is None:
                            logger.warning(
                                f"[狼人杀AI] {player.name} 投票目标 {raw_target} 无效（死亡或不存在）"
                            )
                    except ValueError:
                        pass

            # 如果没有找到格式化内容，尝试直接提取
            if not speech and vote_target is None:
                numbers = re.findall(r"\d+", response)
                if numbers:
                    raw_target = int(numbers[0])
                    vote_target = TargetValidator.validate_vote_target(
                        room, raw_target, player
                    )
                speech = response
                speech = strip_leading_number_speech(speech)
                speech = replace_room_number_mentions(
                    speech, room, include_operation=False
                )

        return (speech, vote_target)

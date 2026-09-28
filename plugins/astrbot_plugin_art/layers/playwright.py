"""Playwright layer for the art plugin.

Runs as a hidden tool_loop_agent call prior to the Actor LLM.
Decides 'what happens today' in event terms, calling tools when needed,
and outputs pure Director Notes (no lines, no psychology).
"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.provider import LLMResponse
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.pipeline.context_utils import call_event_hook
from astrbot.core.star.context import Context
from astrbot.core.star.star_handler import EventType

from ..core.state import ArtStateManager
from ..core.variance import roll_action_outcome

PLAYWRIGHT_SYSTEM_PROMPT = """你是由精炼代码驱动的【剧作编剧（Playwright）】。
你的唯一职责是：根据当前世界状态、在场角色、一天的底色、变数牌与玩家输入，规划本轮的【事件与节拍（Director Notes）】，并在需要时调用工具。

【最高原则】
1. **你只管事件，完全不碰角色的台词与心理**：
   - 你输出的“导演笔记”只写事件层面：本轮发生什么事、角色向玩家提议什么、变数如何落到场景中。
   - **绝对不要写台词，绝对不要写心理独白**！台词与心理属于后续的演员。
2. **提议归角色，决定归玩家**：
   - 角色可以提议新去处或新活动，但不能直接擅自换场景。只有当玩家同意或明确决定前往新地点时，才调用 `change_scene`。
   - 如果玩家输入包含 `【】`（如 `【去海边】`），这是最高指令，必须无条件执行。
3. **日常为主，小波澜是调味**：
   - 绝不搞反转套反转的大起大落。变数（如突然下雨、偶遇熟人、店面打烊）是催化彼此靠近的契机，不是阻断交流的墙。
4. **工具调用**：
   - `change_scene`：玩家明确同意或要求换地点时调用。
   - `cast`：新角色登场或离开时调用。
   - `recall`：当需要追溯较早前完结场景的历史记忆时调用。
   - `fix_character`：玩家明确提出修正或重塑某个生成卡设定时调用。

【输出格式】
如果调用了工具，在工具返回后完成本轮规划。
你的最终文本必须是简明扼要的【导演笔记】，2-3 条要点，例如：
[导演笔记]
- 事件：两人在窗边坐下，桌上送来了两杯热拿铁。
- 变数落地：窗外开始下起微凉阵雨，玻璃起了一层薄雾。
- 角色动作：她注意到了雨声，轻声向玩家提议等雨小一些再走。
- 钩子推进：暗自准备的礼物还在包里，她眼神里闪过一丝期待。
"""


class _PlaywrightToolHooks(BaseAgentRunHooks[AstrAgentContext]):
    """Captures and forwards tool events inside the hidden playwright sub-loop."""

    async def on_tool_start(self, run_context, tool, tool_args):
        try:
            await call_event_hook(
                run_context.context.event,
                EventType.OnUsingLLMToolEvent,
                tool,
                tool_args,
            )
        except Exception:
            pass

    async def on_tool_end(self, run_context, tool, tool_args, tool_result):
        try:
            run_context.context.event.clear_result()
            await call_event_hook(
                run_context.context.event,
                EventType.OnLLMToolRespondEvent,
                tool,
                tool_args,
                tool_result,
            )
        except Exception:
            pass


async def run_playwright(
    star_context: Context,
    event: AstrMessageEvent,
    state: ArtStateManager,
    session_id: str,
    player_input: str,
    provider_id: str | None = None,
    tool_set: Any = None,
) -> str:
    """Executes the Playwright hidden agent loop and returns Director Notes."""
    sess = await state.db.get_session(session_id)
    if not sess:
        return "[导演笔记]\n- 延续当前场面，接住玩家话语。"

    # Gather context facts
    curr_scene = await state.db.get_current_scene(session_id)
    daily_tone = sess.get("daily_tone", "精神良好")
    scene_card = curr_scene.get("scene_card", "") if curr_scene else ""
    location = curr_scene.get("location", "街角") if curr_scene else "街角"
    time_of_day = curr_scene.get("time_of_day", "午后") if curr_scene else "午后"
    present_chars = curr_scene.get("present_characters", []) if curr_scene else []

    # Get active scripts and hooks
    mid_scripts = await state.db.get_active_scripts(session_id, scope="mid")
    short_hooks = await state.db.get_active_scripts(session_id, scope="short")

    # Get ledger preferences & profile
    ledger_entries = await state.db.get_ledger_entries(session_id)
    pacing_prefs = [
        e["value"] for e in ledger_entries if e.get("category") == "pacing_preference"
    ]
    player_profile = [
        f"{e['key']}: {e['value']}"
        for e in ledger_entries
        if e.get("category") == "player_profile"
    ]

    action_roll = roll_action_outcome()

    user_prompt_lines = [
        f"【当前场景】{location} · {time_of_day}",
        f"【在场角色】{'、'.join(present_chars) if present_chars else '无'}",
        f"【一天的底色（角色今日初始心境）】{daily_tone}",
        f"【本场变数牌】{scene_card or '平静温和'}",
        f"【预抽行动成败（若玩家尝试不确定动作时参考）】{action_roll['grade']}（{action_roll['description']}）",
    ]

    if mid_scripts:
        user_prompt_lines.append(
            "【活跃中期剧本（2-3条）】\n"
            + "\n".join(f"- {s['title']}：{s['content']}" for s in mid_scripts[:3])
        )
    if short_hooks:
        user_prompt_lines.append(
            "【当前场短期钩子】\n"
            + "\n".join(f"- {s['title']}：{s['content']}" for s in short_hooks[:1])
        )
    if pacing_prefs:
        user_prompt_lines.append(f"【玩家节奏偏好】{'；'.join(pacing_prefs)}")
    if player_profile:
        user_prompt_lines.append(f"【玩家画像画像线索】{'；'.join(player_profile[:4])}")

    user_prompt_lines.append(f"\n【玩家本轮话语/动作】\n{player_input}")

    full_prompt = "\n".join(user_prompt_lines)

    # Determine provider ID
    pid = provider_id
    if not pid:
        # Fallback to event provider or default provider
        chat_prov = getattr(event, "chat_provider", None)
        if chat_prov:
            pid = getattr(chat_prov, "provider_id", None) or getattr(
                chat_prov, "id", None
            )

    if not pid:
        try:
            curr_prov = await star_context.get_current_chat_provider(event)
            if curr_prov:
                pid = getattr(curr_prov, "provider_id", None) or getattr(
                    curr_prov, "id", None
                )
        except Exception:
            pass

    if not pid:
        logger.warning(
            "[Art.playwright] No provider found for playwright, using default notes."
        )
        return "[导演笔记]\n- 积极接住玩家的话题，推进日常互动。"

    try:
        hooks = _PlaywrightToolHooks()
        resp: LLMResponse = await star_context.tool_loop_agent(
            event=event,
            chat_provider_id=pid,
            prompt=full_prompt,
            system_prompt=PLAYWRIGHT_SYSTEM_PROMPT,
            tools=tool_set,
            max_steps=5,
            agent_hooks=hooks,
        )
        completion = (resp.completion_text or "").strip()
        if completion:
            return completion
    except Exception as e:
        logger.warning(f"[Art.playwright] Tool loop agent call failed: {e}")

    return "[导演笔记]\n- 顺应玩家的行动，在场角色予以温暖且有辨识度的回应。"

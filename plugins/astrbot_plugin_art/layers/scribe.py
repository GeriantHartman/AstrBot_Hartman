"""Background Scribe layer for the art plugin.

Runs non-blocking after the Actor LLM replies.
Maintains relationship ledger, player profile, and archives scene summaries.

HARD RULE: Promises, confessions, and commitments are ONLY recorded
if they originated in the player's direct words.
"""

from __future__ import annotations

import json
import re
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.core.star.context import Context

from ..core.state import ArtStateManager

_BRACKET_DIRECTIVE_RE = re.compile(r"【(.*?)】")
_COMMITMENT_KEYWORDS = [
    "我答应",
    "答应你",
    "我保证",
    "保证会",
    "我发誓",
    "我喜欢你",
    "在一起",
    "我陪你",
    "我们去看",
    "一言为定",
]

SCRIBE_ANALYSIS_PROMPT = """你是由精炼代码驱动的【剧作书记（Scribe）】。
你的职责是：从本轮【玩家话语】与【演员回复】中，提取真实落盘的细节与玩家偏好。

【最高硬规矩】
1. **承诺与告白只能来自玩家原话**：
   - 只有在【玩家话语】中明确做出的承诺、约定、告白或确认，才能记录为 promise。
   - 演员回复中声称“你已经答应了”、“你承诺过”等，哪怕写在正文里，也**绝对严禁**当作既成事实记录！
2. **提取内容纯净、无任何数值**：
   - 不提取好感度，不计算数值。只记录具体的细节记忆。
3. **玩家画像与愿望**：
   - 玩家戏里随口说的心愿（如“好想去看海”、“想吃那家可丽饼”），直接提取为 player_wish，将成为新中期剧本种子。
   - 玩家明显的回应信号（如回复长、主动追问特定话题），提炼为 profile_tag。

请严格返回以下 JSON 格式（不要包含任何 markdown 代码块外部的文字）：
{
  "confirmed_promise": "玩家亲口做出的承诺（若无则为空字符串）",
  "shared_memory": "本轮值得记忆的一个具体细节（若无则为空字符串）",
  "unresolved_tiff": "尚未消解的小别扭或情绪小分歧（若无则为空字符串）",
  "gift": "送出或收到的礼物（若无则为空字符串）",
  "player_wish": "玩家随口提及的愿望或感兴趣的事物（若无则为空字符串）",
  "player_profile_note": "对玩家偏好的一句提炼（若无则为空字符串）",
  "hook_reaction": "accepted | ignored | none"
}
"""


async def run_scribe(
    star_context: Context,
    event: AstrMessageEvent,
    state: ArtStateManager,
    session_id: str,
    player_input: str,
    actor_response: str,
    provider_id: str | None = None,
    scene_switched_from: dict[str, Any] | None = None,
) -> None:
    """Executes the non-blocking background scribe duties."""
    try:
        # 1. Deterministic Extraction from Player Input
        # (a) Check 【】 directives for pacing preferences
        directives = _BRACKET_DIRECTIVE_RE.findall(player_input)
        for d in directives:
            d_clean = d.strip()
            if any(
                k in d_clean
                for k in ["别折腾", "轻松", "慢点", "想休息", "甜一点", "日常"]
            ):
                await state.db.add_ledger_entry(
                    session_id=session_id,
                    category="pacing_preference",
                    key="节奏偏好",
                    value=d_clean,
                    confirmed_by_player=1,
                )

        # (b) Deterministic check on player's own words for commitments
        for kw in _COMMITMENT_KEYWORDS:
            if kw in player_input:
                # Find the sentence containing the keyword
                sentences = re.split(r"[，。！？\n；,!?;]", player_input)
                for s in sentences:
                    if kw in s and len(s.strip()) >= 3:
                        await state.db.add_ledger_entry(
                            session_id=session_id,
                            category="promise",
                            key="承诺",
                            value=s.strip(),
                            confirmed_by_player=1,
                        )
                        break
                break

        # (c) If scene was switched during this turn, archive previous scene summary
        if scene_switched_from:
            prev_loc = scene_switched_from.get("location", "之前场景")
            prev_time = scene_switched_from.get("time_of_day", "")
            summary = f"在【{prev_loc}（{prev_time}）】的相处时光已收束。"
            await state.db.add_memory(
                session_id=session_id,
                summary=summary,
                location=prev_loc,
                scene_id=scene_switched_from.get("id"),
            )

        # 2. LLM Scribe Extraction
        pid = provider_id
        if not pid:
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
            return

        scribe_user_text = (
            f"【玩家话语】\n{player_input}\n\n【演员回复】\n{actor_response[:1000]}"
        )

        resp = await star_context.tool_loop_agent(
            event=event,
            chat_provider_id=pid,
            prompt=scribe_user_text,
            system_prompt=SCRIBE_ANALYSIS_PROMPT,
            tools=None,
            max_steps=1,
        )

        text = (resp.completion_text or "").strip()
        # Parse JSON
        parsed: dict[str, Any] = {}
        try:
            if "```" in text:
                match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
                if match:
                    text = match.group(1).strip()
            parsed = json.loads(text)
        except Exception:
            pass

        if not parsed:
            return

        # Record shared memory
        memory = parsed.get("shared_memory", "").strip()
        if memory:
            await state.db.add_ledger_entry(
                session_id=session_id,
                category="memory",
                key="共同回忆",
                value=memory,
                confirmed_by_player=1,
            )

        # Record unresolved tiff
        tiff = parsed.get("unresolved_tiff", "").strip()
        if tiff:
            await state.db.add_ledger_entry(
                session_id=session_id,
                category="tiff",
                key="小别扭",
                value=tiff,
                confirmed_by_player=1,
            )

        # Record gift
        gift = parsed.get("gift", "").strip()
        if gift:
            await state.db.add_ledger_entry(
                session_id=session_id,
                category="gift",
                key="收到/送出礼物",
                value=gift,
                confirmed_by_player=1,
            )

        # Record player profile note
        prof_note = parsed.get("player_profile_note", "").strip()
        if prof_note:
            await state.db.add_ledger_entry(
                session_id=session_id,
                category="player_profile",
                key="互动画像",
                value=prof_note,
                confirmed_by_player=1,
            )

        # If player made a wish, plant it as a mid-term script seed!
        wish = parsed.get("player_wish", "").strip()
        if wish:
            # Check how many active mid scripts exist
            active_mids = await state.db.get_active_scripts(session_id, scope="mid")
            if len(active_mids) < 3:
                await state.db.add_script(
                    session_id=session_id,
                    scope="mid",
                    title=f"心愿：{wish[:12]}",
                    content=f"她悄悄记下了你的心愿“{wish}”，准备在合适的时机给你一个惊喜。",
                )

        # Handle hook reaction fading
        reaction = parsed.get("hook_reaction", "").strip().lower()
        if reaction == "ignored":
            # Increment fade count on active hooks
            active_hooks = await state.db.get_active_scripts(session_id, scope="short")
            for h in active_hooks:
                await state.db.increment_script_fade(session_id, h["id"])
        elif reaction == "accepted":
            active_hooks = await state.db.get_active_scripts(session_id, scope="short")
            for h in active_hooks:
                await state.db.update_script_status(session_id, h["id"], "completed")

    except Exception as e:
        logger.warning(
            f"[Art.scribe] Background scribe processing encountered error: {e}"
        )

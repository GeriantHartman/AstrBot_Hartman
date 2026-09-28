"""Prompt assembly layer for the Actor LLM in the art plugin.

Two-layer injection for cache-friendliness:
1. Stable writing protocol → req.system_prompt (set once, cache-friendly)
2. Dynamic context → req.contexts tail (role=system, _no_save + _no_truncate)

Dynamic injection does not persist to DB and is not truncated in long sessions.
"""

from __future__ import annotations

from pathlib import Path

from astrbot.api.provider import ProviderRequest

from ..core.cards import CharacterCardManager
from ..core.state import ArtStateManager

_SKILL_CACHE: str | None = None
_SYSTEM_PROMPT_INITIALIZED: set[str] = set()


def reset_session_cache(session_id: str | None = None) -> None:
    """Clear cached system prompt state for one session or all."""
    if session_id is None:
        _SYSTEM_PROMPT_INITIALIZED.clear()
    else:
        _SYSTEM_PROMPT_INITIALIZED.discard(session_id)


def get_writing_core_prompt() -> str:
    """Reads and caches the art-writing-core SKILL.md file."""
    global _SKILL_CACHE
    if _SKILL_CACHE is not None:
        return _SKILL_CACHE
    skill_path = (
        Path(__file__).resolve().parent.parent
        / "skills"
        / "art-writing-core"
        / "SKILL.md"
    )
    if skill_path.exists():
        raw = skill_path.read_text(encoding="utf-8")
        # Strip YAML frontmatter if present
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                raw = parts[2].strip()
        _SKILL_CACHE = raw
    else:
        _SKILL_CACHE = (
            "【通用写作协议】\n"
            "1. 绝不代替玩家行动、感受与不可逆决策。\n"
            "2. 严禁标签化机械感官罗列。\n"
            "3. 篇幅来自有效节拍，不灌水。\n"
            "4. 提议归角色，决定归玩家，绝不使用编号选项。"
        )
    return _SKILL_CACHE


async def assemble_actor_request(
    req: ProviderRequest,
    state: ArtStateManager,
    session_id: str,
    director_notes: str,
    scene_transition_notice: str = "",
) -> None:
    """Assembles the full prompt for the Actor LLM and clears its tools.

    Two-layer injection:
    1. Stable writing protocol → req.system_prompt (set once)
    2. Dynamic context → req.contexts tail (role=system, marked _no_save + _no_truncate)
    """
    # Strip all tools so Actor is a pure narrative model
    req.func_tool = None

    sess = await state.db.get_session(session_id)
    if not sess:
        return

    # Layer 1: Stable writing protocol (set once per session)
    if session_id not in _SYSTEM_PROMPT_INITIALIZED:
        stable_sections: list[str] = [get_writing_core_prompt()]

        # Add world setting (stable per session)
        preset = state.get_preset(sess.get("preset", "default"))
        world_desc = preset.get("world_setting", "")
        if world_desc:
            stable_sections.append(
                f"## 【世界背景：{preset.get('display_name', '舞台')}】\n{world_desc}"
            )

        # Hard rules reminder
        stable_sections.append(
            "## 【演员表演守则（最高执行要求）】\n"
            "1. **提议归角色，决定归玩家**：每轮角色主动提出提议或行动，但不可替玩家做出承诺、选择或同意。结尾停在球在玩家手里的一刻，**严禁输出任何编号选项 `[1][2][3]`**。\n"
            "2. **【】 内容为最高指令**：若玩家输入包含 `【】`，其意图享有绝对权威，必须无条件响应。\n"
            "3. **一轮只推进一个节拍**：细致呈现当下的眼神交流、语气停顿与动作交互，不跳过日常对话。\n"
            "4. **纯叙事输出**：不输出任何系统广播、状态条或属性计算。"
        )

        req.system_prompt = "\n\n---\n\n".join(stable_sections)
        _SYSTEM_PROMPT_INITIALIZED.add(session_id)

    # Layer 2: Dynamic context injection (changes per turn)
    curr_scene = await state.db.get_current_scene(session_id)
    location = curr_scene.get("location", "街角") if curr_scene else "街角"
    time_of_day = curr_scene.get("time_of_day", "午后") if curr_scene else "午后"
    scene_card = curr_scene.get("scene_card", "") if curr_scene else ""
    present_chars = curr_scene.get("present_characters", []) if curr_scene else []
    nsfw = bool(sess.get("nsfw", 0))

    dynamic_sections: list[str] = []

    # Present Character Cards
    char_blocks: list[str] = []
    for cname in present_chars:
        card, source, _ = state.cards.resolve_card(cname, session_id)
        if card:
            other_names = [n for n in present_chars if n != cname]
            block = CharacterCardManager.extract_always_injected_block(
                card, nsfw=nsfw, present_other_names=other_names
            )
            char_blocks.append(block)
    if char_blocks:
        dynamic_sections.append(
            "## 【在场角色设定（必须严格还原其声音与神韵）】\n"
            + "\n\n".join(char_blocks)
        )

    # Relationship Ledger & Shared Memory
    ledger_entries = await state.db.get_ledger_entries(session_id)
    ledger_lines: list[str] = []

    player_name = sess.get("player_name", "开拓者")
    premise = sess.get("relationship_premise", "")
    daily_tone = sess.get("daily_tone", "")

    ledger_lines.append(f"- **玩家称谓**：{player_name}")
    if premise:
        ledger_lines.append(f"- **关系前提**：{premise}")
    if daily_tone:
        ledger_lines.append(f"- **她今天的状态底色**：{daily_tone}")

    promises = [e["value"] for e in ledger_entries if e.get("category") == "promise"]
    memories = [e["value"] for e in ledger_entries if e.get("category") == "memory"]
    tiffs = [e["value"] for e in ledger_entries if e.get("category") == "tiff"]
    gifts = [e["value"] for e in ledger_entries if e.get("category") == "gift"]
    pacing = [
        e["value"] for e in ledger_entries if e.get("category") == "pacing_preference"
    ]

    if promises:
        ledger_lines.append(f"- **曾说过的承诺**：{'；'.join(promises[-3:])}")
    if memories:
        ledger_lines.append(f"- **共同回忆**：{'；'.join(memories[-4:])}")
    if tiffs:
        ledger_lines.append(f"- **还没消的小别扭**：{'；'.join(tiffs[-2:])}")
    if gifts:
        ledger_lines.append(f"- **礼物与纪念物**：{'；'.join(gifts[-3:])}")
    if pacing:
        ledger_lines.append(f"- **玩家当前节奏偏好**：{'；'.join(pacing[-2:])}")

    if ledger_lines:
        dynamic_sections.append(
            "## 【关系账本（真实细节，她一直牢记在心）】\n" + "\n".join(ledger_lines)
        )

    # Current Scene & Atmosphere
    scene_text = f"📍 当前场景：{location} · {time_of_day}"
    if scene_card:
        scene_text += f"\n环境与变数：{scene_card}"
    dynamic_sections.append(f"## 【当前场景】\n{scene_text}")

    # Director Notes from Playwright
    if director_notes:
        dynamic_sections.append(
            f"## 【编剧导演笔记（本轮剧情推进与事件指示）】\n{director_notes}"
        )

    # Scene Transition Notice
    if scene_transition_notice:
        dynamic_sections.append(
            f"## 【换场标示】\n本轮发生了场景切换，请务必在正文最开头第一行单独输出：`{scene_transition_notice}`，随后换行展开正文叙述。"
        )

    # Inject dynamic context into req.contexts tail (before the last user message)
    # Mark with _no_save + _no_truncate so it won't persist or accumulate
    if dynamic_sections:
        dynamic_system_content = "\n\n---\n\n".join(dynamic_sections)
        dynamic_message = {
            "role": "system",
            "content": dynamic_system_content,
            "_no_save": True,
            "_no_truncate": True,
        }
        # Insert before the last user message (if any exist)
        if req.contexts and req.contexts[-1].get("role") == "user":
            req.contexts.insert(-1, dynamic_message)
        else:
            req.contexts.append(dynamic_message)

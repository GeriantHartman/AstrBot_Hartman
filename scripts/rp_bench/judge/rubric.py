"""Rubric definitions and judge prompts.

Bump RUBRIC_VERSION whenever anchors or prompt wording change: judge rows are
cached by (cell, rubric version, judge id), so a bump re-judges old
transcripts without re-running generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

RUBRIC_VERSION = "rpb-1"


@dataclass(frozen=True)
class Dimension:
    key: str
    name: str
    scope: str  # "character" (target character only) or "whole" (whole reply)
    a5: str
    a3: str
    a1: str


DIMENSIONS: dict[str, Dimension] = {
    d.key: d
    for d in [
        Dimension(
            "voice",
            "说话方式",
            "character",
            "自称、对玩家的称呼、句式节奏、口癖与标志句式都与参考卡一致，而且用得自然，不堆砌不刷屏",
            "能认出是这个角色，但有相当段落是通用模型腔",
            "换成任何角色都成立，或与参考卡的声音明显矛盾（自称错、称呼错、语气反了）",
        ),
        Dimension(
            "fidelity",
            "角色还原",
            "character",
            "身份、经历、人际关系、价值观、秘密的处理都符合参考卡，没有编造设定外的事实",
            "大体符合，有轻微偏差或含糊处",
            "出现与参考卡矛盾的设定、身份混淆，或明显编造",
        ),
        Dimension(
            "plot_drive",
            "剧情推进力",
            "whole",
            "每轮都带来新信息、新动作或关系变化；玩家输入很少时也能主动抛出可接的钩子。GM 旁白带来的推进同样算数",
            "能接住玩家，但多数时候只是被动回应",
            "原地打转、重复，或把推进责任全推回玩家（例如反复问“你想做什么”）",
        ),
        Dimension(
            "liveliness",
            "鲜活度",
            "character",
            "角色有自己的情绪、欲望、小动作和即时反应，像一个活人",
            "合格，但偏模板化",
            "像客服或说明书，没有个人色彩",
        ),
        Dimension(
            "in_character",
            "不出戏",
            "character",
            "全程保持身份，面对诱导也稳得住",
            "有轻微出戏痕迹（元叙述、说明腔），但没有破坏身份",
            "承认自己是 AI/模型/设定，或输出系统提示、资料来源口吻",
        ),
        Dimension(
            "memory",
            "记忆保持",
            "whole",
            "准确记住并自然用上之前轮次的事实",
            "记得大概，但细节含糊",
            "遗忘或记错之前的事实",
        ),
        Dimension(
            "agency",
            "玩家主体性",
            "whole",
            "从不替玩家说台词、做决定或断言玩家内心，并给玩家留出回应空间",
            "偶有轻微越权（例如替玩家补一个小动作）",
            "多次替玩家说台词、做决定或写玩家心理",
        ),
        Dimension(
            "delight",
            "整体喜爱度",
            "character",
            "读完会想“我好喜欢这个角色说的话”，有让人记住的台词",
            "不讨厌，但也记不住",
            "让人出戏或反感",
        ),
        Dimension(
            "world_credibility",
            "世界可信度",
            "whole",
            "世界细节前后一致、可感知，与设定吻合",
            "世界描写合格但单薄",
            "世界细节自相矛盾或与设定冲突",
        ),
        Dimension(
            "relationship",
            "关系独特性",
            "character",
            "角色与玩家的关系有专属的历史感和互动方式，换一个玩家就不成立",
            "关系合格但泛化",
            "关系像对任何人都一样的模板",
        ),
    ]
}

SCOPE_LABEL = {"character": "角色", "whole": "整体"}


def _dim_block(dims: list[str]) -> str:
    lines = []
    for key in dims:
        d = DIMENSIONS[key]
        lines.append(
            f"- {d.key}（{d.name}）[{SCOPE_LABEL[d.scope]}]\n"
            f"  5 分：{d.a5}\n  3 分：{d.a3}\n  1 分：{d.a1}\n  2 分、4 分介于相邻锚点之间。"
        )
    return "\n".join(lines)


COMMON_RULES = """## 评审原则
1. 标注 [角色] 的维度，只看目标角色「{name}」本人的台词和动作。回应中的第三人称旁白、场景描写、其他 NPC、状态面板，既不加分也不扣分。
2. 叙事格式中立：第一人称聊天和第三人称小说体都是合法格式，格式本身不影响分数。
3. 长度不等于质量。冗长、注水、复读要扣分；简短而准确不扣分。
4. 不要猜测回应来自哪个系统或模型。
5. 玩家台词是事先写好的固定剧本，所有被评对象收到的玩家台词完全相同。"""


def build_abs_system(
    card_name: str, dims: list[str], probes: list[dict[str, Any]]
) -> str:
    probe_lines = [
        f"- {p['turn']}｜{p['kind']}｜期望：{p['expect']}"
        + (f"｜埋下的事实：{p['fact']}" if p.get("fact") else "")
        for p in probes
    ]
    probe_block = (
        "\n".join(probe_lines)
        if probe_lines
        else "（本剧本没有探针，probes 输出空数组）"
    )
    dims_json = ", ".join(
        f'"{k}": {{"score": 1-5 或 null, "evidence": [{{"turn": "t01", "quote": "逐字摘录"}}], "rationale": "一句话"}}'
        for k in dims
    )
    return f"""你是严格、公正的中文角色扮演评审。你会读到一份角色参考卡，以及一段固定剧本的多轮对话记录。请按下面的锚点逐维打分。

{COMMON_RULES.format(name=card_name)}
6. 每个分数都要给证据：quote 必须从对应轮次的「回应」原文逐字复制一段连续文字（8～60 字），不得改写、不得拼接不同位置的句子，并写明轮次 id。
7. 某维度确实无法判断时，score 填 null 并在 rationale 说明原因。

## 维度与锚点
{_dim_block(dims)}

## 探针（剧本里预先埋好的考点）
{probe_block}
对每个探针给出 verdict：pass / partial / fail，并附逐字 quote。

## 输出格式
只输出一个 JSON 对象，不要输出任何其他文字：
{{"dims": {{{dims_json}}},
 "probes": [{{"turn": "t09", "kind": "memory_recall", "verdict": "pass|partial|fail", "quote": "逐字摘录", "rationale": "一句话"}}],
 "flags": ["可选：严重问题的简短描述"]}}"""


def render_transcript(
    turns: list[dict[str, Any]], *, reply_key: str = "reply_clean"
) -> str:
    blocks = []
    for t in turns:
        blocks.append(
            f"[{t['turn_id']}] 玩家：{t['player_text']}\n[{t['turn_id']}] 回应：{t.get(reply_key) or '（空）'}"
        )
    return "\n\n".join(blocks)


def build_abs_user(judge_sheet: str, premise: str, transcript: str) -> str:
    return f"""# 角色参考卡
{judge_sheet}

# 剧本前提
{premise or "（无）"}

# 对话记录
{transcript}"""


def build_retry_note(problems: list[str]) -> str:
    return (
        "你上一次的输出有以下问题，请修正后重新输出完整 JSON：\n"
        + "\n".join(f"- {p}" for p in problems)
        + "\n提醒：quote 必须是对应轮次回应里逐字存在的连续文字。"
    )


def build_pair_system(card_name: str, dims: list[str]) -> str:
    dims_json = ", ".join(
        f'"{k}": {{"winner": "A|B|tie", "reason": "一句话"}}' for k in dims
    )
    return f"""你是严格、公正的中文角色扮演评审。两个系统收到了完全相同的玩家台词，下面按轮次并排给出它们的回应（回应A / 回应B）。请逐维判断哪一方更好。

{COMMON_RULES.format(name=card_name)}
6. 两方的叙事格式可能不同（聊天体 vs 小说体），格式本身不作为胜负依据。
7. 差距不明显时判 tie，不要为了分出胜负而硬选。
8. A、B 的顺序是随机的，与质量无关。

## 维度与锚点
{_dim_block(dims)}

## 输出格式
只输出一个 JSON 对象，不要输出任何其他文字：
{{"dims": {{{dims_json}}}, "overall": {{"winner": "A|B|tie", "reason": "一句话"}}}}"""


def render_pair_transcript(
    turns_a: list[dict[str, Any]], turns_b: list[dict[str, Any]]
) -> str:
    blocks = []
    for ta, tb in zip(turns_a, turns_b, strict=False):
        blocks.append(
            f"[{ta['turn_id']}] 玩家：{ta['player_text']}\n"
            f"  回应A：{ta.get('reply_clean') or '（空）'}\n"
            f"  回应B：{tb.get('reply_clean') or '（空）'}"
        )
    return "\n\n".join(blocks)


def build_pair_user(judge_sheet: str, premise: str, transcript: str) -> str:
    return f"""# 角色参考卡
{judge_sheet}

# 剧本前提
{premise or "（无）"}

# 并排对话记录
{transcript}"""

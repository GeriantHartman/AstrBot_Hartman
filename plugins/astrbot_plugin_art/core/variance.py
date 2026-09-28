"""Four-layer variance generator for the art playwright plugin.

Code-rolled, non-deterministic narrative spice.
Incorporates a timestamp factor so regenerating rolls a new outcome.
"""

from __future__ import annotations

import random
import time

# Default daily tones (一天的底色)
DEFAULT_DAILY_TONES = [
    "精神很好，眼神亮晶晶的，对什么都充满兴趣",
    "略显慵懒，脚步慢吞吞的，想找个舒服的姿势靠着你",
    "心里藏着一点微小的心事，偶尔会看着某处轻轻出神",
    "格外黏人，说话语调比平时更轻软，下意识跟着你的步伐",
    "兴致勃勃，拉着你想要尝试新点子或去没去过的地方",
    "有些困倦，反应慢半拍，但无论你说什么都很顺从地点头",
    "心绪温软敏感，特别留意你随口说过的每一句话",
    "敏锐且有些俏皮，总想抓你话里的小破绽逗逗你",
]

# Default scene cards (场景牌)
DEFAULT_SCENE_CARDS = [
    "细密轻柔的雨丝悄然落下，两人不得不凑得更近些躲避水汽",
    "周围人流熙熙攘攘，喧闹的声浪把两人的私语包裹成独立的世界",
    "阳光穿过枝叶或玻璃斜斜照下，在彼此衣服上洒下斑驳暖光",
    "迎面遇到了熟识的朋友，打过招呼后相视一笑",
    "店里的背景音乐切到了一首极具氛围感的舒缓老歌",
    "店面恰好客满或正在整理，需要稍作等候或另找个角落",
    "一阵微凉的清风吹起发丝，空气中飘来一阵诱人的现烤点心香气",
    "周围环境忽然格外安静下来，能清晰听见彼此的呼吸与脚步声",
]

# Action outcome tiers (行动结果 5 档)
ACTION_OUTCOMES = [
    {
        "grade": "意外之喜",
        "description": "举动不仅顺利，还意外收获了意料之外的美妙反馈或惊喜发现。",
    },
    {
        "grade": "顺利",
        "description": "过程流畅自然，意图完全达成，在彼此预期之内妥善解决。",
    },
    {
        "grade": "小波折",
        "description": "遇到了一点不影响大局的小小阻碍或插曲，却成为了增进亲近的调味品。",
    },
    {
        "grade": "出洋相",
        "description": "动作略微笨拙或小动作没算准，惹得对方忍俊不禁，化作轻松愉快的欢笑。",
    },
    {
        "grade": "落空",
        "description": "设想暂时没有得到预计的回应，需要换个角度、另寻时机或被对方自然化解。",
    },
]

# Mid-term pacing rhythms (中期节奏)
MIDTERM_PACING_RHYTHMS = [
    "细水长流：在日常细节中隐晦铺垫，不急于挑明",
    "小起波澜：浮现一点小悬念或欲言又止的微妙气氛",
    "暗自期待：正在偷偷筹划某件关于你的小惊喜",
    "温情显露：在微小的互动中不经意吐露真情实感",
]


def _seeded_random() -> random.Random:
    """Creates a Random instance salted with the current sub-millisecond timestamp."""
    seed = time.time_ns() ^ id(object())
    return random.Random(seed)


def roll_daily_tone(
    preset_tones: list[str] | None = None,
    character_tones: list[str] | None = None,
) -> str:
    """Roll the character's daily mood/state for today."""
    rng = _seeded_random()
    candidates: list[str] = []
    if character_tones:
        candidates.extend(character_tones)
    if preset_tones:
        candidates.extend(preset_tones)
    if not candidates:
        candidates = DEFAULT_DAILY_TONES
    return rng.choice(candidates)


def roll_scene_card(
    preset_cards: list[str] | None = None,
    character_surprises: list[str] | None = None,
) -> str:
    """Roll a scene card (environment / third-party occurrence) upon changing scene."""
    rng = _seeded_random()
    candidates: list[str] = []
    if character_surprises:
        candidates.extend(character_surprises)
    if preset_cards:
        candidates.extend(preset_cards)
    if not candidates:
        candidates = DEFAULT_SCENE_CARDS
    return rng.choice(candidates)


def roll_action_outcome() -> dict[str, str]:
    """Roll a pre-drawn action outcome grade for uncertain actions in the current turn."""
    rng = _seeded_random()
    # Weights: 顺利 (40%), 小波折 (25%), 意外之喜 (15%), 出洋相 (10%), 落空 (10%)
    weights = [0.15, 0.40, 0.25, 0.10, 0.10]
    choice = rng.choices(ACTION_OUTCOMES, weights=weights, k=1)[0]
    return choice


def roll_midterm_pacing() -> str:
    """Roll an event pacing suggestion for the playwright when scheduling scripts."""
    rng = _seeded_random()
    return rng.choice(MIDTERM_PACING_RHYTHMS)

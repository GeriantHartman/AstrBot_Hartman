"""Character-first tabletop behavior rolls for AI players."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..models import GameConfig, GameRoom, Player


@dataclass(frozen=True)
class BehaviorRoll:
    """A reproducible behavior posture for one AI action."""

    seed: str
    posture: str
    prompt: str
    action_type: str
    probability_profile: str

    def to_audit(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "posture": self.posture,
            "action_type": self.action_type,
            "probability_profile": self.probability_profile,
            "prompt": self.prompt,
        }


POSTURE_PROMPTS = {
    "table_chat": "【本轮桌游姿态】像角色本人和朋友同桌玩游戏，少一点专业复盘，多一点自然反应。",
    "bond_softening": "【本轮桌游姿态】如果场上有羁绊对象，可以略微软化、护短、放水或露出一点破绽，但仍要合法完成行动。",
    "bond_pressure": "【本轮桌游姿态】如果场上有熟人或宿敌，可以更认真地试探、严打、逼问或用熟悉的小动作施压。",
    "quirk": "【本轮桌游姿态】让角色习惯短暂压过最优解：犯呆、嘴硬、逗弄、紧张、装镇定都可以，但不要持续犯傻。",
    "competitive": "【本轮桌游姿态】这一轮认真竞技，但表达仍必须是角色本人，不要变成通用狼人杀指挥官。",
}

PROFILES = {
    "soft": [
        ("table_chat", 45),
        ("bond_softening", 15),
        ("bond_pressure", 10),
        ("quirk", 10),
        ("competitive", 20),
    ],
    "balanced": [
        ("table_chat", 30),
        ("bond_softening", 20),
        ("bond_pressure", 15),
        ("quirk", 15),
        ("competitive", 20),
    ],
    "dramatic": [
        ("table_chat", 20),
        ("bond_softening", 25),
        ("bond_pressure", 20),
        ("quirk", 20),
        ("competitive", 15),
    ],
}


class TabletopBehaviorService:
    """Rolls a prompt-level posture for character-card actions."""

    def __init__(self, config: "GameConfig"):
        self.config = config

    def roll_for(
        self, player: "Player", room: "GameRoom", action_type: str
    ) -> BehaviorRoll | None:
        if not getattr(self.config, "enable_character_behavior_rolls", True):
            return None
        if not player.ai_config or not player.ai_config.skill_id:
            return None
        profile = getattr(self.config, "character_behavior_intensity", "balanced")
        weights = PROFILES.get(profile, PROFILES["balanced"])
        seed = self._seed(player, room, action_type)
        rng = random.Random(seed)
        posture = self._weighted_choice(rng, weights)
        return BehaviorRoll(
            seed=seed,
            posture=posture,
            prompt=POSTURE_PROMPTS[posture],
            action_type=action_type,
            probability_profile=profile,
        )

    @staticmethod
    def _weighted_choice(rng: random.Random, weights: list[tuple[str, int]]) -> str:
        total = sum(weight for _key, weight in weights)
        cursor = rng.randint(1, total)
        upto = 0
        for key, weight in weights:
            upto += weight
            if cursor <= upto:
                return key
        return weights[-1][0]

    @staticmethod
    def _seed(player: "Player", room: "GameRoom", action_type: str) -> str:
        raw = (
            f"{room.group_id}:{room.current_round}:{room.phase.value}:"
            f"{player.id}:{player.number}:{action_type}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

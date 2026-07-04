"""游戏配置"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

from astrbot.core.utils.astrbot_path import get_astrbot_skills_path

from .enums import Role

DEFAULT_AI_SKILL_ROSTER = [
    "elysia.skill",
    "silver-wolf-lv999-skill",
    "firefly-skill-1.1.0-beta",
    "seele-vollerei-skill",
    "bronya-zaychik-skill",
    "march-7th-skill",
    "castorice-skill",
]


def default_character_skill_root() -> str:
    return str(Path(get_astrbot_skills_path()))


def resolve_character_skill_root(value: Any) -> str:
    if not value:
        return default_character_skill_root()
    configured = Path(str(value))
    if configured.exists():
        return str(configured)
    default_root = Path(default_character_skill_root())
    if default_root.exists():
        return str(default_root)
    return str(configured)


@dataclass
class GameConfig:
    """游戏配置"""

    # 玩家数量配置
    total_players: int = 9
    werewolf_count: int = 3
    seer_count: int = 1
    witch_count: int = 1
    hunter_count: int = 1
    villager_count: int = 3

    # 超时配置（秒）
    timeout_wolf: int = 120
    timeout_seer: int = 120
    timeout_witch: int = 120
    timeout_hunter: int = 120
    timeout_speaking: int = 120
    timeout_vote: int = 120
    timeout_dead_min: int = 10
    timeout_dead_max: int = 15

    # 禁言配置
    ban_duration_days: int = 30

    # AI玩家配置
    ai_player_model: str = ""
    character_skill_root: str = field(default_factory=default_character_skill_root)
    default_ai_skill_roster: List[str] = field(
        default_factory=lambda: DEFAULT_AI_SKILL_ROSTER.copy()
    )
    enable_character_skill_ai: bool = True
    enable_character_behavior_rolls: bool = True
    character_behavior_intensity: str = "balanced"
    suppress_default_llm_during_room: bool = True

    # AI复盘配置
    enable_ai_review: bool = True
    ai_review_model: str = ""
    ai_review_prompt: str = ""

    # Audit and portability
    enable_cardroom_audit: bool = True
    audit_prompt_max_chars: int = 12000
    audit_response_max_chars: int = 4000

    def get_roles_pool(self) -> List[Role]:
        """获取角色池"""
        return (
            [Role.WEREWOLF] * self.werewolf_count
            + [Role.SEER] * self.seer_count
            + [Role.WITCH] * self.witch_count
            + [Role.HUNTER] * self.hunter_count
            + [Role.VILLAGER] * self.villager_count
        )

    def validate(self) -> bool:
        """验证配置是否有效"""
        role_sum = (
            self.werewolf_count
            + self.seer_count
            + self.witch_count
            + self.hunter_count
            + self.villager_count
        )
        return role_sum == self.total_players

    @property
    def god_count(self) -> int:
        """神职数量"""
        return self.seer_count + self.witch_count + self.hunter_count

    def get_role_description(self) -> str:
        """获取角色配置描述"""
        god_roles = []
        if self.seer_count > 0:
            god_roles.append(
                f"预言家×{self.seer_count}" if self.seer_count > 1 else "预言家"
            )
        if self.witch_count > 0:
            god_roles.append(
                f"女巫×{self.witch_count}" if self.witch_count > 1 else "女巫"
            )
        if self.hunter_count > 0:
            god_roles.append(
                f"猎人×{self.hunter_count}" if self.hunter_count > 1 else "猎人"
            )
        return " + ".join(god_roles)

    @staticmethod
    def normalize_roster(value: Any) -> List[str]:
        """兼容旧版逗号字符串和新版列表配置。"""
        if value is None:
            return DEFAULT_AI_SKILL_ROSTER.copy()
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return DEFAULT_AI_SKILL_ROSTER.copy()

    @classmethod
    def from_dict(cls, config: dict) -> "GameConfig":
        """从字典创建配置"""
        return cls(
            total_players=config.get("total_players", 9),
            werewolf_count=config.get("werewolf_count", 3),
            seer_count=config.get("seer_count", 1),
            witch_count=config.get("witch_count", 1),
            hunter_count=config.get("hunter_count", 1),
            villager_count=config.get("villager_count", 3),
            timeout_wolf=config.get("timeout_wolf", 120),
            timeout_seer=config.get("timeout_seer", 120),
            timeout_witch=config.get("timeout_witch", 120),
            timeout_hunter=config.get("timeout_hunter", 120),
            timeout_speaking=config.get("timeout_speaking", 120),
            timeout_vote=config.get("timeout_vote", 120),
            timeout_dead_min=config.get("timeout_dead_min", 10),
            timeout_dead_max=config.get("timeout_dead_max", 15),
            ban_duration_days=config.get("ban_duration_days", 30),
            ai_player_model=config.get("ai_player_model", ""),
            character_skill_root=resolve_character_skill_root(
                config.get("character_skill_root")
            ),
            default_ai_skill_roster=cls.normalize_roster(
                config.get("default_ai_skill_roster")
            ),
            enable_character_skill_ai=config.get("enable_character_skill_ai", True),
            enable_character_behavior_rolls=config.get(
                "enable_character_behavior_rolls", True
            ),
            character_behavior_intensity=config.get(
                "character_behavior_intensity", "balanced"
            ),
            suppress_default_llm_during_room=config.get(
                "suppress_default_llm_during_room", True
            ),
            enable_ai_review=config.get("enable_ai_review", True),
            ai_review_model=config.get("ai_review_model", ""),
            ai_review_prompt=config.get("ai_review_prompt", ""),
            enable_cardroom_audit=config.get("enable_cardroom_audit", True),
            audit_prompt_max_chars=config.get("audit_prompt_max_chars", 12000),
            audit_response_max_chars=config.get("audit_response_max_chars", 4000),
        )

    @classmethod
    def default(cls) -> "GameConfig":
        """获取默认配置"""
        return cls()

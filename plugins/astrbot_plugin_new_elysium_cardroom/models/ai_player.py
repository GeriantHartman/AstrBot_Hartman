"""AI player data models."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


DISPLAY_LABEL_RE = re.compile(r"(?<!第)(\d{1,2})号[.．·]\s*([^，,：:、；;\s）)]+)")
NUMBER_LABEL_RE = re.compile(r"(?<!第)(\d{1,2})号(?:玩家)?")


@dataclass
class AIPlayerConfig:
    """Configuration for one AI player."""

    name: str
    model_id: str = ""
    personality: str = ""
    max_retries: int = 3
    retry_delay: float = 1.0
    skill_id: str = ""
    memory_id: str = ""

    def __post_init__(self):
        if not self.name:
            raise ValueError("AI玩家名称不能为空")


@dataclass
class AIPlayerContext:
    """Runtime context rendered into each AI prompt."""

    player_number: int = 0
    role_name: str = ""
    is_werewolf: bool = False
    werewolf_teammates: list[str] = field(default_factory=list)
    seer_results: list[dict] = field(default_factory=list)
    alive_players: list[str] = field(default_factory=list)
    dead_players: list[str] = field(default_factory=list)
    current_round: int = 1
    current_phase: str = ""
    game_events: list[str] = field(default_factory=list)
    speeches: list[dict] = field(default_factory=list)
    vote_history: list[dict] = field(default_factory=list)
    witch_antidote_used: bool = False
    witch_poison_used: bool = False
    last_killed_player: Optional[str] = None
    witch_saved_player: Optional[str] = None
    witch_poisoned_player: Optional[str] = None
    can_shoot: bool = False
    wolf_chat_messages: list[dict] = field(default_factory=list)
    vote_discussions: list[dict] = field(default_factory=list)
    player_name_map: dict[int, str] = field(default_factory=dict)
    persistent_memories: list[str] = field(default_factory=list)
    relationship_hints: list[str] = field(default_factory=list)

    def update_player_names(self, name_map: dict[int, str]) -> None:
        self.player_name_map = dict(name_map)

    def update_persistent_memories(self, memories: list[str]) -> None:
        self.persistent_memories = list(memories or [])

    def update_relationship_hints(self, hints: list[str]) -> None:
        self.relationship_hints = list(hints or [])

    def add_wolf_chat(self, sender_name: str, content: str, round_num: int) -> None:
        self.wolf_chat_messages.append(
            {"sender": sender_name, "content": content, "round": round_num}
        )

    def add_event(self, event: str) -> None:
        self.game_events.append(event)

    def add_speech(self, player_name: str, content: str, is_pk: bool = False) -> None:
        self.speeches.append(
            {
                "player": player_name,
                "content": content,
                "is_pk": is_pk,
                "round": self.current_round,
            }
        )

    def add_vote(self, voter: str, target: str, is_pk: bool = False) -> None:
        self.vote_history.append(
            {
                "voter": voter,
                "target": target,
                "is_pk": is_pk,
                "round": self.current_round,
            }
        )

    def add_seer_result(self, target_name: str, is_werewolf: bool) -> None:
        self.seer_results.append(
            {
                "target": target_name,
                "is_werewolf": is_werewolf,
                "round": self.current_round,
            }
        )

    def add_vote_discussion(self, player_name: str, content: str) -> None:
        self.vote_discussions.append(
            {"player": player_name, "content": content, "round": self.current_round}
        )

    def update_alive_players(self, alive_list: list[str], dead_list: list[str]) -> None:
        self.alive_players = alive_list
        self.dead_players = dead_list

    def _name_first(self, text: object, include_operation: bool = True) -> str:
        value = str(text or "")
        if not self.player_name_map:
            return value

        def render(number: int, fallback: str = "") -> str:
            name = self.player_name_map.get(number) or fallback
            if not name:
                return f"{number}号玩家"
            if include_operation:
                return f"{name}（操作编号{number}）"
            return name

        def replace_display(match: re.Match[str]) -> str:
            return render(int(match.group(1)), match.group(2))

        value = DISPLAY_LABEL_RE.sub(replace_display, value)
        return NUMBER_LABEL_RE.sub(lambda m: render(int(m.group(1))), value)

    def to_prompt_context(self) -> str:
        """Render a name-first prompt context."""
        from ..services.ai.prompts import GAME_RULES

        lines: list[str] = [GAME_RULES, ""]

        if self.current_round == 1 and len(self.speeches) == 0:
            lines.extend(
                [
                    "【重要】这是游戏第一天。",
                    "昨晚只分配了身份，没有任何玩家发言，也没有公开信息。",
                    "严禁编造“昨天某人说了”之类不存在的信息。",
                    "",
                ]
            )

        last_night_deaths = [
            event
            for event in self.game_events
            if f"第{self.current_round}夜死亡" in event
        ]
        last_night_peaceful = [
            event
            for event in self.game_events
            if f"第{self.current_round}夜：平安夜" in event
        ]

        if last_night_deaths:
            lines.append("【昨晚死亡公告】")
            lines.extend(f"- {self._name_first(event)}" for event in last_night_deaths)
            lines.append("昨晚有人死亡，不要说成平安夜。")
            lines.append("")
        elif last_night_peaceful:
            lines.extend(["【昨晚是平安夜】", "昨晚没有人死亡，女巫可能救了人。", ""])

        if self.current_phase:
            lines.extend(["【当前阶段】", self.current_phase, ""])

        lines.extend(
            [
                "【你的身份】",
                f"你是 {self.player_name_map.get(self.player_number, '自己')}（操作编号{self.player_number}），身份是 {self.role_name}",
                "称呼别人时优先用名字或昵称；编号只用于投票、验人、刀人等必须输出数字的操作。",
            ]
        )

        if self.player_name_map:
            lines.append("\n【玩家称呼表】")
            for number, name in sorted(self.player_name_map.items()):
                lines.append(f"- 操作编号{number}: {name}")

        if self.persistent_memories:
            lines.append("\n【过往牌桌记忆】")
            lines.append("这些只是过往经验，不是本局事实。")
            lines.extend(f"- {memory}" for memory in self.persistent_memories[-5:])

        if self.relationship_hints:
            lines.append("\n【本局角色关系图补丁】")
            lines.append("这些关系会影响你在桌上的态度，但不能当作本局阵营证据。")
            lines.extend(self.relationship_hints)

        if self.is_werewolf and self.werewolf_teammates:
            lines.append(
                f"\n你的狼人队友是：{', '.join(self._name_first(name) for name in self.werewolf_teammates)}"
            )

        if self.is_werewolf and self.wolf_chat_messages:
            lines.append("\n【狼人密谋记录 - 绝密，白天不能透露】")
            for msg in self.wolf_chat_messages[-10:]:
                sender = self._name_first(msg.get("sender"), include_operation=False)
                lines.append(f"[第{msg.get('round')}晚] {sender}: {msg.get('content')}")

        if self.seer_results:
            lines.append("\n【验人结果】")
            for result in self.seer_results:
                status = "狼人" if result.get("is_werewolf") else "好人"
                target = self._name_first(result.get("target"))
                lines.append(f"第{result.get('round')}晚：{target} 是 {status}")

        lines.append("\n【当前存活玩家】")
        lines.append(
            ", ".join(self._name_first(name) for name in self.alive_players)
            if self.alive_players
            else "无"
        )

        if self.dead_players:
            lines.append("\n【已死亡玩家】")
            lines.append(
                ", ".join(self._name_first(name) for name in self.dead_players)
            )

        if self.role_name == "女巫":
            lines.append("\n【你的女巫技能信息 - 仅你可见】")
            lines.append(f"解药：{'已用' if self.witch_antidote_used else '可用'}")
            lines.append(f"毒药：{'已用' if self.witch_poison_used else '可用'}")
            if self.last_killed_player:
                lines.append(
                    f"今晚被狼人杀死的是：{self._name_first(self.last_killed_player)}"
                )
            if self.witch_saved_player:
                lines.append(f"你救过的人：{self._name_first(self.witch_saved_player)}")
            if self.witch_poisoned_player:
                lines.append(
                    f"你毒过的人：{self._name_first(self.witch_poisoned_player)}"
                )
            lines.append("公开说出女巫私密视角会暴露身份，除非你决定跳女巫。")

        if self.game_events:
            lines.append("\n【重要事件】")
            for event in self.game_events[-10:]:
                lines.append(f"- {self._name_first(event)}")

        if self.speeches:
            lines.append("\n【发言记录】")
            for speech in self.speeches[-15:]:
                prefix = "[PK]" if speech.get("is_pk") else ""
                speaker = self._name_first(
                    speech.get("player"), include_operation=False
                )
                lines.append(
                    f"{prefix}{speaker}: {str(speech.get('content', ''))[:100]}"
                )

        if self.vote_history:
            lines.append("\n【投票记录】")
            prev_round_votes = [
                vote
                for vote in self.vote_history
                if vote.get("round") != self.current_round
            ]
            current_round_votes = [
                vote
                for vote in self.vote_history
                if vote.get("round") == self.current_round
            ]
            if prev_round_votes:
                lines.append("历史投票：")
                for vote in prev_round_votes[-5:]:
                    prefix = "[PK]" if vote.get("is_pk") else ""
                    voter = self._name_first(vote.get("voter"), include_operation=False)
                    target = self._name_first(
                        vote.get("target"), include_operation=False
                    )
                    lines.append(
                        f"  {prefix}第{vote.get('round')}轮: {voter} -> {target}"
                    )
            if current_round_votes:
                lines.append("本轮投票：")
                for vote in current_round_votes:
                    prefix = "[PK]" if vote.get("is_pk") else ""
                    voter = self._name_first(vote.get("voter"), include_operation=False)
                    target = self._name_first(
                        vote.get("target"), include_operation=False
                    )
                    lines.append(f"  {prefix}{voter} -> {target}")

        if self.vote_discussions:
            current_discussions = [
                discussion
                for discussion in self.vote_discussions
                if discussion.get("round") == self.current_round
            ]
            if current_discussions:
                lines.append("\n【投票期间讨论】")
                for discussion in current_discussions:
                    speaker = self._name_first(
                        discussion.get("player"), include_operation=False
                    )
                    lines.append(
                        f"- {speaker}: {str(discussion.get('content', ''))[:120]}"
                    )

        return "\n".join(lines)

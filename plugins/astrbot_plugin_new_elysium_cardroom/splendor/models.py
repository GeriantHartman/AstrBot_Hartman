"""State models for Splendor rooms."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import AIPlayerConfig
from .constants import COLORS, TOKEN_COLORS


PHASE_WAITING = "waiting"
PHASE_PLAYING = "playing"
PHASE_FINISHED = "finished"


def empty_color_counts(include_gold: bool = False) -> dict[str, int]:
    colors = TOKEN_COLORS if include_gold else COLORS
    return {color: 0 for color in colors}


@dataclass
class SplendorPlayer:
    """A human or character-card AI player in a Splendor room."""

    id: str
    name: str
    number: int = 0
    is_ai: bool = False
    ai_config: AIPlayerConfig | None = None
    tokens: dict[str, int] = field(default_factory=lambda: empty_color_counts(True))
    bonuses: dict[str, int] = field(default_factory=empty_color_counts)
    purchased_cards: list[str] = field(default_factory=list)
    reserved_cards: list[str] = field(default_factory=list)
    nobles: list[str] = field(default_factory=list)

    @property
    def token_total(self) -> int:
        return sum(self.tokens.values())

    @property
    def card_count(self) -> int:
        return len(self.purchased_cards)

    @property
    def display_name(self) -> str:
        return f"{self.number}号.{self.name}" if self.number else self.name

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "number": self.number,
            "is_ai": self.is_ai,
            "ai_config": self._ai_config_to_dict(),
            "tokens": dict(self.tokens),
            "bonuses": dict(self.bonuses),
            "purchased_cards": list(self.purchased_cards),
            "reserved_cards": list(self.reserved_cards),
            "nobles": list(self.nobles),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SplendorPlayer":
        player = cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or ""),
            number=int(data.get("number") or 0),
            is_ai=bool(data.get("is_ai", False)),
            ai_config=cls._ai_config_from_dict(data.get("ai_config")),
        )
        player.tokens.update(_normalize_counts(data.get("tokens"), include_gold=True))
        player.bonuses.update(_normalize_counts(data.get("bonuses")))
        player.purchased_cards = [str(item) for item in data.get("purchased_cards", [])]
        player.reserved_cards = [str(item) for item in data.get("reserved_cards", [])]
        player.nobles = [str(item) for item in data.get("nobles", [])]
        return player

    def _ai_config_to_dict(self) -> dict[str, Any] | None:
        if not self.ai_config:
            return None
        return {
            "name": self.ai_config.name,
            "model_id": self.ai_config.model_id,
            "personality": self.ai_config.personality,
            "max_retries": self.ai_config.max_retries,
            "retry_delay": self.ai_config.retry_delay,
            "skill_id": self.ai_config.skill_id,
            "memory_id": self.ai_config.memory_id,
        }

    @staticmethod
    def _ai_config_from_dict(data: Any) -> AIPlayerConfig | None:
        if not isinstance(data, dict):
            return None
        return AIPlayerConfig(
            name=str(data.get("name") or "AI"),
            model_id=str(data.get("model_id") or ""),
            personality=str(data.get("personality") or ""),
            max_retries=int(data.get("max_retries") or 3),
            retry_delay=float(data.get("retry_delay") or 1.0),
            skill_id=str(data.get("skill_id") or ""),
            memory_id=str(data.get("memory_id") or ""),
        )


@dataclass
class SplendorRoom:
    """A persistent Splendor game room."""

    group_id: str
    creator_id: str
    target_players: int = 4
    msg_origin: Any = None
    bot: Any = None
    phase: str = PHASE_WAITING
    seed: int = 0
    players: dict[str, SplendorPlayer] = field(default_factory=dict)
    turn_order: list[str] = field(default_factory=list)
    current_player_index: int = 0
    bank: dict[str, int] = field(default_factory=lambda: empty_color_counts(True))
    decks: dict[int, list[str]] = field(
        default_factory=lambda: {1: [], 2: [], 3: []}
    )
    market: dict[int, list[str]] = field(
        default_factory=lambda: {1: [], 2: [], 3: []}
    )
    nobles: list[str] = field(default_factory=list)
    pending_discard_player_id: str = ""
    pending_noble_player_id: str = ""
    pending_noble_ids: list[str] = field(default_factory=list)
    final_round_active: bool = False
    final_round_trigger_player_id: str = ""
    winner_ids: list[str] = field(default_factory=list)
    action_log: list[str] = field(default_factory=list)

    def add_player(self, player: SplendorPlayer) -> None:
        self.players[player.id] = player

    def remove_player(self, player_id: str) -> None:
        self.players.pop(player_id, None)

    def get_player(self, player_id: str) -> SplendorPlayer | None:
        return self.players.get(player_id)

    def player_by_number(self, number: int) -> SplendorPlayer | None:
        for player in self.players.values():
            if player.number == number:
                return player
        return None

    def is_player_in_room(self, player_id: str) -> bool:
        return player_id in self.players

    @property
    def player_count(self) -> int:
        return len(self.players)

    @property
    def is_full(self) -> bool:
        return self.player_count >= self.target_players

    @property
    def current_player(self) -> SplendorPlayer | None:
        if self.phase != PHASE_PLAYING or not self.turn_order:
            return None
        if self.current_player_index >= len(self.turn_order):
            self.current_player_index = 0
        return self.players.get(self.turn_order[self.current_player_index])

    def log(self, message: str) -> None:
        self.action_log.append(message)
        self.action_log = self.action_log[-80:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "creator_id": self.creator_id,
            "target_players": self.target_players,
            "msg_origin": self.msg_origin if isinstance(self.msg_origin, str) else "",
            "phase": self.phase,
            "seed": self.seed,
            "players": {
                player_id: player.to_dict()
                for player_id, player in self.players.items()
            },
            "turn_order": list(self.turn_order),
            "current_player_index": self.current_player_index,
            "bank": dict(self.bank),
            "decks": {str(tier): list(cards) for tier, cards in self.decks.items()},
            "market": {str(tier): list(cards) for tier, cards in self.market.items()},
            "nobles": list(self.nobles),
            "pending_discard_player_id": self.pending_discard_player_id,
            "pending_noble_player_id": self.pending_noble_player_id,
            "pending_noble_ids": list(self.pending_noble_ids),
            "final_round_active": self.final_round_active,
            "final_round_trigger_player_id": self.final_round_trigger_player_id,
            "winner_ids": list(self.winner_ids),
            "action_log": list(self.action_log),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SplendorRoom":
        room = cls(
            group_id=str(data.get("group_id") or ""),
            creator_id=str(data.get("creator_id") or ""),
            target_players=int(data.get("target_players") or 4),
            msg_origin=str(data.get("msg_origin") or ""),
            phase=str(data.get("phase") or PHASE_WAITING),
            seed=int(data.get("seed") or 0),
        )
        room.players = {
            str(player_id): SplendorPlayer.from_dict(player_data)
            for player_id, player_data in dict(data.get("players") or {}).items()
        }
        room.turn_order = [str(item) for item in data.get("turn_order", [])]
        room.current_player_index = int(data.get("current_player_index") or 0)
        room.bank.update(_normalize_counts(data.get("bank"), include_gold=True))
        room.decks = _normalize_card_piles(data.get("decks"))
        room.market = _normalize_card_piles(data.get("market"))
        room.nobles = [str(item) for item in data.get("nobles", [])]
        room.pending_discard_player_id = str(data.get("pending_discard_player_id") or "")
        room.pending_noble_player_id = str(data.get("pending_noble_player_id") or "")
        room.pending_noble_ids = [str(item) for item in data.get("pending_noble_ids", [])]
        room.final_round_active = bool(data.get("final_round_active", False))
        room.final_round_trigger_player_id = str(
            data.get("final_round_trigger_player_id") or ""
        )
        room.winner_ids = [str(item) for item in data.get("winner_ids", [])]
        room.action_log = [str(item) for item in data.get("action_log", [])][-80:]
        return room


def _normalize_counts(data: Any, include_gold: bool = False) -> dict[str, int]:
    result = empty_color_counts(include_gold)
    if isinstance(data, dict):
        for color in result:
            result[color] = max(0, int(data.get(color) or 0))
    return result


def _normalize_card_piles(data: Any) -> dict[int, list[str]]:
    result = {1: [], 2: [], 3: []}
    if isinstance(data, dict):
        for tier in result:
            result[tier] = [str(item) for item in data.get(str(tier), [])]
    return result

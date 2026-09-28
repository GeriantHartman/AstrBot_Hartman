"""Expand a plan into run cells: card × scenario × arm × model × repeat."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .cards import Card
from .scenarios import Scenario


def cell_key(
    card_key: str, scenario: Scenario, arm: str, model: str, repeat: int
) -> str:
    raw = f"{card_key}|{scenario.id}@{scenario.content_hash}|{arm}|{model}|{repeat}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def pair_group_key(card_key: str, scenario: Scenario, model: str, repeat: int) -> str:
    """Cells sharing this key saw identical player input, only the arm differs."""
    return f"{card_key}|{scenario.id}@{scenario.content_hash}|{model}|{repeat}"


@dataclass
class Cell:
    card: Card
    scenario: Scenario  # already rendered for this card
    arm: str
    model: str
    repeat: int

    @property
    def key(self) -> str:
        return cell_key(self.card.key, self.scenario, self.arm, self.model, self.repeat)

    @property
    def group(self) -> str:
        return pair_group_key(self.card.key, self.scenario, self.model, self.repeat)

    def label(self) -> str:
        return (
            f"{self.card.key}/{self.scenario.id}/{self.arm}/{self.model}#{self.repeat}"
        )


def expand(
    cards: list[Card],
    scenarios: list[Scenario],
    arms: list[str],
    models: list[str],
    repeats: int,
    *,
    smoke_turns: int | None = None,
) -> list[Cell]:
    cells: list[Cell] = []
    for card in cards:
        values = {"char": card.name, "call_player": card.call_player_placeholder()}
        for scenario in scenarios:
            if not scenario.applies_to(card.key):
                continue
            rendered = scenario.render(values, card_names=card.names())
            if smoke_turns:
                rendered = rendered.truncated(smoke_turns)
            for model in models:
                for repeat in range(repeats):
                    for arm in arms:
                        cells.append(Cell(card, rendered, arm, model, repeat))
    return cells

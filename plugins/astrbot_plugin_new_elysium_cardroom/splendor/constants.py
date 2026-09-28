"""Static mechanical data for classic Splendor."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO


COLORS = ("white", "blue", "green", "red", "black")
TOKEN_COLORS = COLORS + ("gold",)

COLOR_LABELS = {
    "white": "白",
    "blue": "蓝",
    "green": "绿",
    "red": "红",
    "black": "黑",
    "gold": "金",
}

COLOR_ICONS = {
    "white": "白",
    "blue": "蓝",
    "green": "绿",
    "red": "红",
    "black": "黑",
    "gold": "金",
}

COLOR_ALIASES = {
    "w": "white",
    "white": "white",
    "白": "white",
    "白色": "white",
    "钻石": "white",
    "b": "blue",
    "u": "blue",
    "blue": "blue",
    "蓝": "blue",
    "蓝色": "blue",
    "g": "green",
    "green": "green",
    "绿": "green",
    "绿色": "green",
    "r": "red",
    "red": "red",
    "红": "red",
    "红色": "red",
    "k": "black",
    "black": "black",
    "黑": "black",
    "黑色": "black",
    "gold": "gold",
    "黄": "gold",
    "金": "gold",
    "黄金": "gold",
    "万能": "gold",
}

TOKEN_BANK_BY_PLAYER_COUNT = {
    2: {"white": 4, "blue": 4, "green": 4, "red": 4, "black": 4, "gold": 5},
    3: {"white": 5, "blue": 5, "green": 5, "red": 5, "black": 5, "gold": 5},
    4: {"white": 7, "blue": 7, "green": 7, "red": 7, "black": 7, "gold": 5},
}

NOBLE_COUNT_BY_PLAYER_COUNT = {2: 3, 3: 4, 4: 5}
MARKET_SIZE_PER_TIER = 4
RESERVE_LIMIT = 3
TOKEN_LIMIT = 10
WIN_SCORE = 15


@dataclass(frozen=True)
class CardSpec:
    """A development card's deterministic rules data."""

    card_id: str
    tier: int
    color: str
    points: int
    cost: dict[str, int]


@dataclass(frozen=True)
class NobleSpec:
    """A noble tile's deterministic rules data."""

    noble_id: str
    points: int
    requirement: dict[str, int]


DEVELOPMENT_CARDS_CSV = """Level,Color,PV,Black,Blue,Green,Red,White
1,Black,0,0,1,1,1,1
1,Black,0,0,2,1,1,1
1,Black,0,0,2,0,1,2
1,Black,0,1,0,1,3,0
1,Black,0,0,0,2,1,0
1,Black,0,0,0,2,0,2
1,Black,0,0,0,3,0,0
1,Black,1,0,4,0,0,0
1,Blue,0,1,0,1,1,1
1,Blue,0,1,0,1,2,1
1,Blue,0,0,0,2,2,1
1,Blue,0,0,1,3,1,0
1,Blue,0,2,0,0,0,1
1,Blue,0,2,0,2,0,0
1,Blue,0,3,0,0,0,0
1,Blue,1,0,0,0,4,0
1,White,0,1,1,1,1,0
1,White,0,1,1,2,1,0
1,White,0,1,2,2,0,0
1,White,0,1,1,0,0,3
1,White,0,1,0,0,2,0
1,White,0,2,2,0,0,0
1,White,0,0,3,0,0,0
1,White,1,0,0,4,0,0
1,Green,0,1,1,0,1,1
1,Green,0,2,1,0,1,1
1,Green,0,2,1,0,2,0
1,Green,0,0,3,1,0,1
1,Green,0,0,1,0,0,2
1,Green,0,0,2,0,2,0
1,Green,0,0,0,0,3,0
1,Green,1,4,0,0,0,0
1,Red,0,1,1,1,0,1
1,Red,0,1,1,1,0,2
1,Red,0,2,0,1,0,2
1,Red,0,3,0,0,1,1
1,Red,0,0,2,1,0,0
1,Red,0,0,0,0,2,2
1,Red,0,0,0,0,0,3
1,Red,1,0,0,0,0,4
2,Black,1,0,2,2,0,3
2,Black,1,2,0,3,0,3
2,Black,2,0,1,4,2,0
2,Black,2,0,0,5,3,0
2,Black,2,0,0,0,0,5
2,Black,3,6,0,0,0,0
2,Blue,1,0,2,2,3,0
2,Blue,1,3,2,3,0,0
2,Blue,2,0,3,0,0,5
2,Blue,2,4,0,0,1,2
2,Blue,2,0,5,0,0,0
2,Blue,3,0,6,0,0,0
2,White,1,2,0,3,2,0
2,White,1,0,3,0,3,2
2,White,2,2,0,1,4,0
2,White,2,3,0,0,5,0
2,White,2,0,0,0,5,0
2,White,3,0,0,0,0,6
2,Green,1,0,0,2,3,3
2,Green,1,2,3,0,0,2
2,Green,2,1,2,0,0,4
2,Green,2,0,5,3,0,0
2,Green,2,0,0,5,0,0
2,Green,3,0,0,6,0,0
2,Red,1,3,0,0,2,2
2,Red,1,3,3,0,2,0
2,Red,2,0,4,2,0,1
2,Red,2,5,0,0,0,3
2,Red,2,5,0,0,0,0
2,Red,3,0,0,0,6,0
3,Black,3,0,3,5,3,3
3,Black,4,0,0,0,7,0
3,Black,4,3,0,3,6,0
3,Black,5,3,0,0,7,0
3,Blue,3,5,0,3,3,3
3,Blue,4,0,0,0,0,7
3,Blue,4,3,3,0,0,6
3,Blue,5,0,3,0,0,7
3,White,3,3,3,3,5,0
3,White,4,7,0,0,0,0
3,White,4,6,0,0,3,3
3,White,5,7,0,0,0,3
3,Green,3,3,3,0,3,5
3,Green,4,0,7,0,0,0
3,Green,4,0,6,3,0,3
3,Green,5,0,7,3,0,0
3,Red,3,3,5,3,0,3
3,Red,4,0,0,7,0,0
3,Red,4,0,3,6,3,0
3,Red,5,0,0,7,3,0
"""

NOBLES_CSV = """id,white,blue,green,red,black,points
1,3,3,0,0,3,3
2,0,3,3,3,0,3
3,3,0,0,3,3,3
4,0,0,4,4,0,3
5,0,4,4,0,0,3
6,0,0,0,4,4,3
7,4,0,0,0,4,3
8,3,3,3,0,0,3
9,0,0,3,3,3,3
10,4,4,0,0,0,3
"""


def parse_color(value: str) -> str:
    """Resolve a user-facing color token to the canonical color key."""
    key = str(value or "").strip().lower()
    return COLOR_ALIASES.get(key, "")


def parse_development_cards() -> dict[str, CardSpec]:
    """Build the card spec table from compact CSV data."""
    cards: dict[str, CardSpec] = {}
    tier_counts: dict[int, int] = {1: 0, 2: 0, 3: 0}
    for row in csv.DictReader(StringIO(DEVELOPMENT_CARDS_CSV)):
        tier = int(row["Level"])
        tier_counts[tier] += 1
        card_id = f"T{tier}-{tier_counts[tier]:02d}"
        cost = {
            "white": int(row["White"]),
            "blue": int(row["Blue"]),
            "green": int(row["Green"]),
            "red": int(row["Red"]),
            "black": int(row["Black"]),
        }
        cards[card_id] = CardSpec(
            card_id=card_id,
            tier=tier,
            color=row["Color"].strip().lower(),
            points=int(row["PV"]),
            cost=cost,
        )
    return cards


def parse_nobles() -> dict[str, NobleSpec]:
    """Build the noble spec table from compact CSV data."""
    nobles: dict[str, NobleSpec] = {}
    for row in csv.DictReader(StringIO(NOBLES_CSV)):
        noble_id = f"N{row['id']}"
        nobles[noble_id] = NobleSpec(
            noble_id=noble_id,
            points=int(row["points"]),
            requirement={color: int(row[color]) for color in COLORS},
        )
    return nobles


CARD_SPECS = parse_development_cards()
NOBLE_SPECS = parse_nobles()

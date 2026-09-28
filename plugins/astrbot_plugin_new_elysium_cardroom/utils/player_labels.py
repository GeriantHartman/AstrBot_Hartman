"""Name-first labels for table prompts and AI speech."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import GameRoom, Player


DISPLAY_LABEL_RE = re.compile(r"(?<!第)(\d{1,2})号[.．·]\s*[^，,：:、；;\s）)]+")
NUMBER_LABEL_RE = re.compile(r"(?<!第)(\d{1,2})号(?:玩家)?")
LEADING_NUMBER_SPEECH_RE = re.compile(
    r"^\s*(?:我)?\s*\d{1,2}\s*号(?:玩家)?"
    r"(?:发言|说话|先说|说两句)?[，,。:：\s-]*"
)


def table_name(player: "Player") -> str:
    raw_name = ""
    if player.is_ai and player.ai_config and player.ai_config.name:
        raw_name = player.ai_config.name
    else:
        raw_name = player.name

    name = str(raw_name or "").strip()
    while name and not name[0].isalnum():
        name = name[1:].strip()
    return name or str(player.name or "").strip() or f"{player.number}号玩家"


def operation_label(player: "Player") -> str:
    name = table_name(player)
    if player.number:
        return f"{name}（操作编号{player.number}）"
    return name


def build_player_name_map(room: "GameRoom") -> dict[int, str]:
    return {
        player.number: table_name(player)
        for player in room.players.values()
        if player.number
    }


def replace_number_labels(
    text: str, name_map: dict[int, str], include_operation: bool = True
) -> str:
    if not text or not name_map:
        return text

    def render(number: int) -> str:
        name = name_map.get(number)
        if not name:
            return f"{number}号"
        if include_operation:
            return f"{name}（操作编号{number}）"
        return name

    def replace_display(match: re.Match[str]) -> str:
        return render(int(match.group(1)))

    def replace_number(match: re.Match[str]) -> str:
        return render(int(match.group(1)))

    text = DISPLAY_LABEL_RE.sub(replace_display, text)
    return NUMBER_LABEL_RE.sub(replace_number, text)


def replace_room_number_mentions(
    text: str, room: "GameRoom", include_operation: bool = False
) -> str:
    return replace_number_labels(
        text, build_player_name_map(room), include_operation=include_operation
    )


def strip_leading_number_speech(text: str) -> str:
    return LEADING_NUMBER_SPEECH_RE.sub("", text or "").strip()

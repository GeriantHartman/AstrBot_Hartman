"""Plugin-level relationship graph for character-card tabletop play."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astrbot.api import logger

from ..utils.player_labels import table_name

if TYPE_CHECKING:
    from ..models import GameRoom, Player


DEFAULT_RELATIONSHIP_GRAPH_PATH = (
    Path(__file__).resolve().parents[1] / "assets" / "character_relationships.json"
)


class CharacterRelationshipService:
    """Loads relationship hints that should not live in one-sided character cards."""

    def __init__(self, graph_path: Path | None = None):
        self.graph_path = graph_path or DEFAULT_RELATIONSHIP_GRAPH_PATH
        self._graph: dict[str, Any] | None = None

    @property
    def exists(self) -> bool:
        return self.graph_path.is_file()

    def relation_count(self) -> int:
        return len(self._relationships())

    def hints_for(
        self, player: "Player", room: "GameRoom", limit: int = 6
    ) -> list[str]:
        skill_id = self._skill_id(player)
        if not skill_id:
            return []

        hints: list[str] = []
        for other in room.players.values():
            if other.id == player.id:
                continue
            other_skill_id = self._skill_id(other)
            if not other_skill_id:
                continue

            for edge, is_reverse in self._matching_edges(skill_id, other_skill_id):
                hints.append(self._format_hint(edge, other, is_reverse))
                if len(hints) >= limit:
                    return hints
        return hints

    def _graph_data(self) -> dict[str, Any]:
        if self._graph is not None:
            return self._graph
        if not self.graph_path.is_file():
            self._graph = {}
            return self._graph
        try:
            self._graph = json.loads(self.graph_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(
                f"[新爱莉都棋牌室] 读取角色关系图失败 {self.graph_path}: {exc}"
            )
            self._graph = {}
        return self._graph

    def _relationships(self) -> list[dict[str, Any]]:
        relationships = self._graph_data().get("relationships", [])
        if not isinstance(relationships, list):
            return []
        return [edge for edge in relationships if isinstance(edge, dict)]

    def _matching_edges(
        self, player_skill_id: str, other_skill_id: str
    ) -> list[tuple[dict[str, Any], bool]]:
        matches = []
        for edge in self._relationships():
            source = str(edge.get("source", "")).strip()
            target = str(edge.get("target", "")).strip()
            bidirectional = bool(edge.get("bidirectional", False))
            if source == player_skill_id and target == other_skill_id:
                matches.append((edge, False))
            elif (
                bidirectional and source == other_skill_id and target == player_skill_id
            ):
                matches.append((edge, True))
        return matches

    @staticmethod
    def _skill_id(player: "Player") -> str:
        if not player.is_ai or not player.ai_config:
            return ""
        return player.ai_config.skill_id.strip()

    @staticmethod
    def _format_hint(edge: dict[str, Any], other: "Player", is_reverse: bool) -> str:
        label = str(edge.get("label", "")).strip()
        note_key = "target_note" if is_reverse else "source_note"
        note = str(edge.get(note_key) or edge.get("mutual_note") or "").strip()
        behavior = str(edge.get("tabletop_behavior", "")).strip()
        boundaries = edge.get("boundaries", [])
        if isinstance(boundaries, list):
            boundary_text = "；".join(str(item).strip() for item in boundaries if item)
        else:
            boundary_text = str(boundaries or "").strip()

        parts = [f"- 你与{table_name(other)}"]
        if label:
            parts.append(f"：{label}")
        if note:
            parts.append(f"。{note}")
        if behavior:
            parts.append(f" 桌上表现：{behavior}")
        if boundary_text:
            parts.append(f" 边界：{boundary_text}")
        return "".join(parts)

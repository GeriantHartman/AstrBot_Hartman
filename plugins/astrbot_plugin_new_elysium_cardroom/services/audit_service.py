"""JSONL audit ledger for New Elysium Cardroom games."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

if TYPE_CHECKING:
    from ..models import GameRoom, Player


PLUGIN_NAME = "astrbot_plugin_new_elysium_cardroom"
LOCAL_TZ = timezone(timedelta(hours=8))


class AuditService:
    """Writes replayable audit data outside the plugin code directory."""

    def __init__(self, config):
        self.config = config
        self.base_dir = Path(get_astrbot_plugin_data_path()) / PLUGIN_NAME / "audits"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def start_room(self, room: "GameRoom") -> None:
        if not getattr(self.config, "enable_cardroom_audit", True):
            return
        stamp = datetime.now(LOCAL_TZ).strftime("%Y%m%d_%H%M%S")
        room.audit_id = f"{room.group_id}_{stamp}"
        room.audit_log_path = str(self.base_dir / f"{room.audit_id}.jsonl")
        room.audit_summary_path = str(self.base_dir / f"{room.audit_id}_summary.json")
        self.record(
            room,
            "room_started",
            {
                "group_id": room.group_id,
                "creator_id": room.creator_id,
                "total_players": room.config.total_players,
            },
        )

    def record(
        self, room: "GameRoom", event: str, payload: dict[str, Any] | None = None
    ) -> None:
        if not getattr(self.config, "enable_cardroom_audit", True):
            return
        if not getattr(room, "audit_log_path", ""):
            return
        entry = {
            "ts": datetime.now(LOCAL_TZ).isoformat(),
            "event": event,
            "phase": room.phase.value if room.phase else "",
            "round": room.current_round,
            "payload": payload or {},
        }
        try:
            with Path(room.audit_log_path).open("a", encoding="utf-8") as file:
                file.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning(f"[新爱莉都棋牌室] 写入审计失败: {exc}")

    def record_ai_decision(
        self,
        room: "GameRoom",
        player: "Player",
        action_type: str,
        prompt: str,
        response: str,
        behavior_roll: dict[str, Any] | None,
        success: bool,
        attempt: int,
        error: str = "",
    ) -> None:
        self.record(
            room,
            "ai_decision",
            {
                "player_id": player.id,
                "player_name": player.name,
                "player_number": player.number,
                "skill_id": player.ai_config.skill_id if player.ai_config else "",
                "role": player.role.display_name if player.role else "",
                "action_type": action_type,
                "success": success,
                "attempt": attempt,
                "error": error,
                "behavior_roll": behavior_roll or {},
                "prompt": self._truncate(
                    prompt, getattr(self.config, "audit_prompt_max_chars", 12000)
                ),
                "response": self._truncate(
                    response, getattr(self.config, "audit_response_max_chars", 4000)
                ),
            },
        )

    def finalize_room(self, room: "GameRoom", result: str = "") -> None:
        if not getattr(self.config, "enable_cardroom_audit", True):
            return
        if not getattr(room, "audit_summary_path", ""):
            return
        payload = {
            "audit_id": room.audit_id,
            "finished_at": datetime.now(LOCAL_TZ).isoformat(),
            "group_id": room.group_id,
            "result": result,
            "round": room.current_round,
            "phase": room.phase.value if room.phase else "",
            "players": [
                {
                    "id": player.id,
                    "name": player.name,
                    "number": player.number,
                    "role": player.role.display_name if player.role else "",
                    "alive": player.is_alive,
                    "is_ai": player.is_ai,
                    "skill_id": player.ai_config.skill_id if player.ai_config else "",
                }
                for player in sorted(
                    room.players.values(), key=lambda p: p.number or 999
                )
            ],
            "game_log": room.game_log,
            "audit_log_path": room.audit_log_path,
        }
        try:
            Path(room.audit_summary_path).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            logger.warning(f"[新爱莉都棋牌室] 写入审计摘要失败: {exc}")

    def list_recent_audits(self, limit: int = 5) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        for path in sorted(
            self.base_dir.glob("*_summary.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )[:limit]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            items.append(
                {
                    "audit_id": str(data.get("audit_id") or path.stem),
                    "result": str(data.get("result") or ""),
                    "finished_at": str(data.get("finished_at") or ""),
                    "summary_path": str(path),
                    "log_path": str(data.get("audit_log_path") or ""),
                }
            )
        return items

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        value = str(text or "")
        if max_chars <= 0 or len(value) <= max_chars:
            return value
        return value[:max_chars] + "\n...[truncated]"

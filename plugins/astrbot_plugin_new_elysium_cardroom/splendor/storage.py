"""SQLite persistence for Splendor rooms."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from .models import PHASE_FINISHED, PHASE_PLAYING, PHASE_WAITING, SplendorRoom


PLUGIN_NAME = "astrbot_plugin_new_elysium_cardroom"
LOCAL_TZ = timezone(timedelta(hours=8))


class SplendorStorage:
    """Stores active and recently finished Splendor room snapshots."""

    def __init__(self):
        self.base_dir = Path(get_astrbot_plugin_data_path()) / PLUGIN_NAME / "splendor"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.base_dir / "splendor.sqlite3"
        self._init_db()

    def save_room(self, room: SplendorRoom) -> None:
        payload = json.dumps(room.to_dict(), ensure_ascii=False)
        updated_at = datetime.now(LOCAL_TZ).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO splendor_rooms(group_id, phase, state_json, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(group_id) DO UPDATE SET
                    phase = excluded.phase,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (room.group_id, room.phase, payload, updated_at),
            )
            conn.commit()

    def mark_finished(self, room: SplendorRoom) -> None:
        room.phase = PHASE_FINISHED
        self.save_room(room)

    def delete_room(self, group_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM splendor_rooms WHERE group_id = ?", (group_id,))
            conn.commit()

    def load_active_rooms(self) -> dict[str, SplendorRoom]:
        rooms: dict[str, SplendorRoom] = {}
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT group_id, state_json FROM splendor_rooms
                WHERE phase IN (?, ?)
                """,
                (PHASE_WAITING, PHASE_PLAYING),
            ).fetchall()
        for group_id, state_json in rows:
            try:
                room = SplendorRoom.from_dict(json.loads(state_json))
                rooms[str(group_id)] = room
            except Exception as exc:
                logger.warning(f"[璀璨宝石] 恢复房间 {group_id} 失败: {exc}")
        return rooms

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS splendor_rooms (
                    group_id TEXT PRIMARY KEY,
                    phase TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

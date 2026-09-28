"""Database layer for the art playwright plugin.

Manages one SQLite database file per session containing six tables:
session, scenes, cast, scripts, ledger, and memories.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import aiosqlite

from astrbot.api import logger

_SAFE_CHARS_PATTERN = re.compile(r"[^a-zA-Z0-9_\-]")


def safe_session_id(session_id: str) -> str:
    """Normalize session_id for use in safe filenames."""
    return _SAFE_CHARS_PATTERN.sub("_", session_id)


_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS session (
    session_id TEXT PRIMARY KEY,
    claimed INTEGER DEFAULT 1,
    nsfw INTEGER DEFAULT 0,
    preset TEXT DEFAULT 'default',
    relationship_premise TEXT DEFAULT '',
    current_day INTEGER DEFAULT 1,
    current_date_str TEXT DEFAULT '第1天 · 晨',
    daily_tone TEXT DEFAULT '',
    player_name TEXT DEFAULT '开拓者',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS scenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    location TEXT NOT NULL,
    time_of_day TEXT DEFAULT '',
    present_characters TEXT DEFAULT '[]',
    scene_card TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    is_current INTEGER DEFAULT 1,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scenes_session ON scenes(session_id, is_current);

CREATE TABLE IF NOT EXISTS [cast] (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    character_name TEXT NOT NULL,
    card_key TEXT DEFAULT '',
    is_present INTEGER DEFAULT 1,
    current_form TEXT DEFAULT '',
    passerby_note TEXT DEFAULT '',
    first_appeared INTEGER DEFAULT 1,
    created_at REAL NOT NULL,
    UNIQUE(session_id, character_name)
);
CREATE INDEX IF NOT EXISTS idx_cast_session ON [cast](session_id, is_present);

CREATE TABLE IF NOT EXISTS scripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    fade_count INTEGER DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scripts_session ON scripts(session_id, status);

CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    confirmed_by_player INTEGER DEFAULT 1,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_session ON ledger(session_id, category);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    scene_id INTEGER,
    location TEXT DEFAULT '',
    summary TEXT NOT NULL,
    keywords TEXT DEFAULT '',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id);
"""


class ArtDatabase:
    """Manages SQLite connections and queries for art plugin sessions."""

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._db_dir = data_dir / "databases"
        self._db_dir.mkdir(parents=True, exist_ok=True)
        self._connections: dict[str, aiosqlite.Connection] = {}

    def get_db_path(self, session_id: str) -> Path:
        safe_id = safe_session_id(session_id)
        return self._db_dir / f"session_{safe_id}.db"

    async def get_connection(self, session_id: str) -> aiosqlite.Connection:
        if session_id not in self._connections:
            db_path = self.get_db_path(session_id)
            conn = await aiosqlite.connect(str(db_path))
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA foreign_keys=ON")
            await conn.executescript(_CREATE_TABLES_SQL)
            await conn.commit()
            self._connections[session_id] = conn
        return self._connections[session_id]

    async def close_session(self, session_id: str) -> None:
        conn = self._connections.pop(session_id, None)
        if conn:
            try:
                await conn.close()
            except Exception as e:
                logger.warning(f"[Art] Error closing DB for {session_id}: {e}")

    async def close_all(self) -> None:
        for sid, conn in list(self._connections.items()):
            try:
                await conn.close()
            except Exception as e:
                logger.warning(f"[Art] Error closing DB for {sid}: {e}")
        self._connections.clear()

    # ----------------------------------------------------------------------
    # Session table operations
    # ----------------------------------------------------------------------

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        conn = await self.get_connection(session_id)
        async with conn.execute(
            "SELECT * FROM session WHERE session_id = ?", (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def upsert_session(
        self,
        session_id: str,
        *,
        claimed: int = 1,
        nsfw: int = 0,
        preset: str = "default",
        relationship_premise: str = "",
        current_day: int = 1,
        current_date_str: str = "第1天 · 晨",
        daily_tone: str = "",
        player_name: str = "开拓者",
    ) -> None:
        conn = await self.get_connection(session_id)
        now = time.time()
        await conn.execute(
            """
            INSERT INTO session (
                session_id, claimed, nsfw, preset, relationship_premise,
                current_day, current_date_str, daily_tone, player_name,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                claimed = excluded.claimed,
                nsfw = excluded.nsfw,
                preset = excluded.preset,
                relationship_premise = excluded.relationship_premise,
                current_day = excluded.current_day,
                current_date_str = excluded.current_date_str,
                daily_tone = excluded.daily_tone,
                player_name = excluded.player_name,
                updated_at = excluded.updated_at
            """,
            (
                session_id,
                claimed,
                nsfw,
                preset,
                relationship_premise,
                current_day,
                current_date_str,
                daily_tone,
                player_name,
                now,
                now,
            ),
        )
        await conn.commit()

    async def update_session_fields(self, session_id: str, **fields: Any) -> None:
        if not fields:
            return
        conn = await self.get_connection(session_id)
        fields["updated_at"] = time.time()
        set_clauses = [f"{k} = ?" for k in fields]
        values = list(fields.values()) + [session_id]
        sql = f"UPDATE session SET {', '.join(set_clauses)} WHERE session_id = ?"
        await conn.execute(sql, tuple(values))
        await conn.commit()

    # ----------------------------------------------------------------------
    # Scenes table operations
    # ----------------------------------------------------------------------

    async def get_current_scene(self, session_id: str) -> dict[str, Any] | None:
        conn = await self.get_connection(session_id)
        async with conn.execute(
            "SELECT * FROM scenes WHERE session_id = ? AND is_current = 1 ORDER BY id DESC LIMIT 1",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            try:
                res["present_characters"] = json.loads(
                    res.get("present_characters") or "[]"
                )
            except Exception:
                res["present_characters"] = []
            return res

    async def get_all_scenes(self, session_id: str) -> list[dict[str, Any]]:
        conn = await self.get_connection(session_id)
        async with conn.execute(
            "SELECT * FROM scenes WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                try:
                    item["present_characters"] = json.loads(
                        item.get("present_characters") or "[]"
                    )
                except Exception:
                    item["present_characters"] = []
                results.append(item)
            return results

    async def create_scene(
        self,
        session_id: str,
        location: str,
        time_of_day: str = "",
        present_characters: list[str] | None = None,
        scene_card: str = "",
    ) -> int:
        conn = await self.get_connection(session_id)
        # Mark existing current scenes as not current
        await conn.execute(
            "UPDATE scenes SET is_current = 0 WHERE session_id = ? AND is_current = 1",
            (session_id,),
        )
        chars_json = json.dumps(present_characters or [], ensure_ascii=False)
        cursor = await conn.execute(
            """
            INSERT INTO scenes (
                session_id, location, time_of_day, present_characters,
                scene_card, summary, is_current, created_at
            ) VALUES (?, ?, ?, ?, ?, '', 1, ?)
            """,
            (
                session_id,
                location,
                time_of_day,
                chars_json,
                scene_card,
                time.time(),
            ),
        )
        await conn.commit()
        return cursor.lastrowid or 0

    async def update_scene_summary(
        self, session_id: str, scene_id: int, summary: str
    ) -> None:
        conn = await self.get_connection(session_id)
        await conn.execute(
            "UPDATE scenes SET summary = ? WHERE id = ? AND session_id = ?",
            (summary, scene_id, session_id),
        )
        await conn.commit()

    # ----------------------------------------------------------------------
    # Cast table operations
    # ----------------------------------------------------------------------

    async def get_cast(self, session_id: str) -> list[dict[str, Any]]:
        conn = await self.get_connection(session_id)
        async with conn.execute(
            "SELECT * FROM [cast] WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_present_characters(self, session_id: str) -> list[dict[str, Any]]:
        conn = await self.get_connection(session_id)
        async with conn.execute(
            "SELECT * FROM [cast] WHERE session_id = ? AND is_present = 1 ORDER BY id ASC",
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_character_cast(
        self, session_id: str, character_name: str
    ) -> dict[str, Any] | None:
        conn = await self.get_connection(session_id)
        async with conn.execute(
            "SELECT * FROM [cast] WHERE session_id = ? AND character_name = ?",
            (session_id, character_name),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def upsert_cast(
        self,
        session_id: str,
        character_name: str,
        card_key: str = "",
        is_present: int = 1,
        current_form: str = "",
        passerby_note: str = "",
        first_appeared: int = 1,
    ) -> None:
        conn = await self.get_connection(session_id)
        now = time.time()
        await conn.execute(
            """
            INSERT INTO [cast] (
                session_id, character_name, card_key, is_present,
                current_form, passerby_note, first_appeared, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, character_name) DO UPDATE SET
                card_key = CASE WHEN excluded.card_key != '' THEN excluded.card_key ELSE [cast].card_key END,
                is_present = excluded.is_present,
                current_form = CASE WHEN excluded.current_form != '' THEN excluded.current_form ELSE [cast].current_form END,
                passerby_note = CASE WHEN excluded.passerby_note != '' THEN excluded.passerby_note ELSE [cast].passerby_note END,
                first_appeared = 0
            """,
            (
                session_id,
                character_name,
                card_key,
                is_present,
                current_form,
                passerby_note,
                first_appeared,
                now,
            ),
        )
        await conn.commit()

    async def set_character_presence(
        self, session_id: str, character_name: str, is_present: int
    ) -> None:
        conn = await self.get_connection(session_id)
        await conn.execute(
            "UPDATE [cast] SET is_present = ? WHERE session_id = ? AND character_name = ?",
            (is_present, session_id, character_name),
        )
        await conn.commit()

    # ----------------------------------------------------------------------
    # Scripts table operations (Mid-term scripts & Short-term hooks)
    # ----------------------------------------------------------------------

    async def get_active_scripts(
        self, session_id: str, scope: str | None = None
    ) -> list[dict[str, Any]]:
        conn = await self.get_connection(session_id)
        if scope:
            query = "SELECT * FROM scripts WHERE session_id = ? AND status = 'active' AND scope = ? ORDER BY id ASC"
            params = (session_id, scope)
        else:
            query = "SELECT * FROM scripts WHERE session_id = ? AND status = 'active' ORDER BY id ASC"
            params = (session_id,)
        async with conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def add_script(
        self, session_id: str, scope: str, title: str, content: str
    ) -> int:
        conn = await self.get_connection(session_id)
        cursor = await conn.execute(
            """
            INSERT INTO scripts (
                session_id, scope, title, content, status, fade_count, created_at
            ) VALUES (?, ?, ?, ?, 'active', 0, ?)
            """,
            (session_id, scope, title, content, time.time()),
        )
        await conn.commit()
        return cursor.lastrowid or 0

    async def update_script_status(
        self, session_id: str, script_id: int, status: str
    ) -> None:
        conn = await self.get_connection(session_id)
        await conn.execute(
            "UPDATE scripts SET status = ? WHERE id = ? AND session_id = ?",
            (status, script_id, session_id),
        )
        await conn.commit()

    async def increment_script_fade(self, session_id: str, script_id: int) -> int:
        conn = await self.get_connection(session_id)
        await conn.execute(
            "UPDATE scripts SET fade_count = fade_count + 1 WHERE id = ? AND session_id = ?",
            (script_id, session_id),
        )
        # Check if >= 2 ignores, then fade out
        async with conn.execute(
            "SELECT fade_count FROM scripts WHERE id = ? AND session_id = ?",
            (script_id, session_id),
        ) as cursor:
            row = await cursor.fetchone()
            count = row[0] if row else 0
            if count >= 2:
                await conn.execute(
                    "UPDATE scripts SET status = 'faded' WHERE id = ? AND session_id = ?",
                    (script_id, session_id),
                )
            await conn.commit()
            return count

    # ----------------------------------------------------------------------
    # Ledger table operations
    # ----------------------------------------------------------------------

    async def get_ledger_entries(
        self, session_id: str, category: str | None = None
    ) -> list[dict[str, Any]]:
        conn = await self.get_connection(session_id)
        if category:
            query = "SELECT * FROM ledger WHERE session_id = ? AND category = ? ORDER BY id ASC"
            params = (session_id, category)
        else:
            query = "SELECT * FROM ledger WHERE session_id = ? ORDER BY id ASC"
            params = (session_id,)
        async with conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def add_ledger_entry(
        self,
        session_id: str,
        category: str,
        key: str,
        value: str,
        confirmed_by_player: int = 1,
    ) -> int:
        conn = await self.get_connection(session_id)
        cursor = await conn.execute(
            """
            INSERT INTO ledger (
                session_id, category, key, value, confirmed_by_player, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, category, key, value, confirmed_by_player, time.time()),
        )
        await conn.commit()
        return cursor.lastrowid or 0

    async def remove_ledger_entry(self, session_id: str, entry_id: int) -> None:
        conn = await self.get_connection(session_id)
        await conn.execute(
            "DELETE FROM ledger WHERE id = ? AND session_id = ?",
            (entry_id, session_id),
        )
        await conn.commit()

    # ----------------------------------------------------------------------
    # Memories table operations
    # ----------------------------------------------------------------------

    async def add_memory(
        self,
        session_id: str,
        summary: str,
        location: str = "",
        scene_id: int | None = None,
        keywords: str = "",
    ) -> int:
        conn = await self.get_connection(session_id)
        cursor = await conn.execute(
            """
            INSERT INTO memories (
                session_id, scene_id, location, summary, keywords, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, scene_id, location, summary, keywords, time.time()),
        )
        await conn.commit()
        return cursor.lastrowid or 0

    async def search_memories(
        self, session_id: str, query: str, limit: int = 3
    ) -> list[dict[str, Any]]:
        conn = await self.get_connection(session_id)
        # Search by keyword match or order by recent
        tokens = [t.strip() for t in query.split() if t.strip()]
        if not tokens:
            async with conn.execute(
                "SELECT * FROM memories WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

        clauses = []
        params: list[Any] = [session_id]
        for t in tokens:
            clauses.append("(summary LIKE ? OR location LIKE ? OR keywords LIKE ?)")
            pat = f"%{t}%"
            params.extend([pat, pat, pat])
        params.append(limit)

        sql = f"SELECT * FROM memories WHERE session_id = ? AND ({' OR '.join(clauses)}) ORDER BY id DESC LIMIT ?"
        async with conn.execute(sql, tuple(params)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # ----------------------------------------------------------------------
    # Maintenance / Reset / Rollback
    # ----------------------------------------------------------------------

    async def delete_session_files(self, session_id: str) -> None:
        await self.close_session(session_id)
        db_path = self.get_db_path(session_id)
        for p in [
            db_path,
            db_path.parent / f"{db_path.name}-wal",
            db_path.parent / f"{db_path.name}-shm",
        ]:
            if p.exists():
                try:
                    p.unlink()
                except Exception as e:
                    logger.warning(f"[Art] Error deleting file {p}: {e}")

    async def rollback_recent_turns(
        self, session_id: str, count: int
    ) -> dict[str, int]:
        """Rolls back the last n entries across memories and recent scenes."""
        conn = await self.get_connection(session_id)
        # Delete recent memories
        mem_cursor = await conn.execute(
            """
            DELETE FROM memories WHERE id IN (
                SELECT id FROM memories WHERE session_id = ? ORDER BY id DESC LIMIT ?
            )
            """,
            (session_id, count),
        )
        mem_deleted = mem_cursor.rowcount

        # Delete recent ledger entries that were added recently
        led_cursor = await conn.execute(
            """
            DELETE FROM ledger WHERE id IN (
                SELECT id FROM ledger WHERE session_id = ? ORDER BY id DESC LIMIT ?
            )
            """,
            (session_id, count),
        )
        led_deleted = led_cursor.rowcount
        await conn.commit()

        return {"memories_reverted": mem_deleted, "ledger_reverted": led_deleted}

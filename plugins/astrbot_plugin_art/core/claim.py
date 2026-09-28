"""Session claim exclusivity manager between RPG and Art plugins.

A session can only belong to either RPG or Art exclusively.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .db import ArtDatabase, safe_session_id

_SAFE_CHARS_PATTERN = re.compile(r"[^a-zA-Z0-9_\-]")


def get_rpg_db_path(session_id: str) -> Path:
    """Return the database path for RPG plugin for this session."""
    safe = _SAFE_CHARS_PATTERN.sub("_", session_id)
    data_dir = (
        Path(get_astrbot_data_path()) / "plugin_data" / "astrbot_plugin_agentic_rpg"
    )
    return data_dir / f"world_{safe}.db"


def is_rpg_claimed(session_id: str) -> bool:
    """Check whether the given session is currently claimed/active in Agentic RPG."""
    db_path = get_rpg_db_path(session_id)
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT game_active FROM game_sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cur.fetchone()
            if row and row[0] == 1:
                return True
        finally:
            conn.close()
    except Exception as e:
        logger.debug(f"[Art.claim] Failed to query RPG db for {session_id}: {e}")
    return False


async def is_art_claimed(session_id: str, db: ArtDatabase) -> bool:
    """Check whether the given session is currently claimed by Art."""
    try:
        sess = await db.get_session(session_id)
        if sess and sess.get("claimed", 0) == 1:
            return True
    except Exception as e:
        logger.debug(f"[Art.claim] Failed to query Art session for {session_id}: {e}")
    return False


async def claim_session_for_art(
    session_id: str,
    db: ArtDatabase,
    *,
    preset: str = "default",
    relationship_premise: str = "",
    player_name: str = "开拓者",
    daily_tone: str = "",
) -> tuple[bool, str]:
    """Attempts to claim the session for Art.

    Returns:
        (success, message)
    """
    if is_rpg_claimed(session_id):
        return (
            False,
            "当前会话已被 RPG 插件占用。请先在 RPG 插件中执行 `/rpg reset` 清空存档并释放归属，或切换至新的会话使用。",
        )

    await db.upsert_session(
        session_id=session_id,
        claimed=1,
        preset=preset,
        relationship_premise=relationship_premise,
        player_name=player_name,
        daily_tone=daily_tone,
    )
    return True, "成功认领会话，已进入剧作家模式。"


async def release_session_claim(
    session_id: str,
    db: ArtDatabase,
    cards_dir: Path | None = None,
) -> None:
    """Releases the session claim and cleans up session database and generated cards."""
    await db.delete_session_files(session_id)
    if cards_dir:
        safe_id = safe_session_id(session_id)
        session_card_dir = cards_dir / safe_id
        if session_card_dir.exists():
            import shutil

            try:
                shutil.rmtree(session_card_dir)
            except Exception as e:
                logger.warning(
                    f"[Art.claim] Failed to delete generated cards dir {session_card_dir}: {e}"
                )

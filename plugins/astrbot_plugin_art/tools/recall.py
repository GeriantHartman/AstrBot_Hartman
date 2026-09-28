"""Tool: recall for retrieving summaries of completed past scenes."""

from __future__ import annotations

import json

from ..core.state import ArtStateManager


async def execute_recall(
    state: ArtStateManager,
    session_id: str,
    query: str,
    limit: int = 3,
) -> str:
    """Searches memory archive for past scene summaries and shared history."""
    try:
        query = (query or "").strip()
        limit = max(1, min(limit, 10))
        memories = await state.db.search_memories(session_id, query, limit=limit)
        return json.dumps(
            {"ok": True, "data": {"memories": memories}, "error": None},
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps(
            {"ok": False, "error": f"翻阅回忆失败: {e}", "data": None},
            ensure_ascii=False,
        )

"""Tool: change_scene for switching location, time, and atmosphere."""

from __future__ import annotations

import json

from ..core.state import ArtStateManager


async def execute_change_scene(
    state: ArtStateManager,
    session_id: str,
    location: str,
    time_of_day: str = "",
    present_characters: list[str] | None = None,
) -> str:
    """Switches the current scene.

    Should ONLY be called when the player agrees or explicitly decides to go somewhere new.
    """
    try:
        location = location.strip()
        if not location:
            return json.dumps(
                {"ok": False, "error": "地点不能为空", "data": None},
                ensure_ascii=False,
            )

        res = await state.change_scene(
            session_id=session_id,
            location=location,
            time_of_day=time_of_day,
            present_characters=present_characters,
        )
        return json.dumps({"ok": True, "data": res, "error": None}, ensure_ascii=False)
    except Exception as e:
        return json.dumps(
            {"ok": False, "error": f"切换场景失败: {e}", "data": None},
            ensure_ascii=False,
        )

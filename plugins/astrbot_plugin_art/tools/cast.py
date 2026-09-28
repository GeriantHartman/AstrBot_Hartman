"""Tool: cast for character entrance/exit and automatic card generation."""

from __future__ import annotations

import json

from ..core.state import ArtStateManager


async def execute_cast(
    state: ArtStateManager,
    session_id: str,
    character_name: str,
    action: str = "enter",
    form: str = "",
) -> str:
    """Manages character entrance or departure.

    If a character enters and has no card, automatically generates one and persists it.
    Returns the character's full appearance and current status.
    """
    try:
        character_name = character_name.strip()
        if not character_name:
            return json.dumps(
                {"ok": False, "error": "角色名称不能为空", "data": None},
                ensure_ascii=False,
            )

        res = await state.cast_character(
            session_id=session_id,
            character_name=character_name,
            action=action,
            form=form,
        )
        return json.dumps({"ok": True, "data": res, "error": None}, ensure_ascii=False)
    except Exception as e:
        return json.dumps(
            {"ok": False, "error": f"角色调度失败: {e}", "data": None},
            ensure_ascii=False,
        )

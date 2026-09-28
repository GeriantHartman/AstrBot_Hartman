"""Tool: fix_character for updating, regenerating, or deleting generated cards."""

from __future__ import annotations

import json

from ..core.state import ArtStateManager


async def execute_fix_character(
    state: ArtStateManager,
    session_id: str,
    character_name: str,
    action: str,
    details: str = "",
) -> str:
    """Modifies a generated character card (update partial, regenerate full, delete)."""
    try:
        character_name = character_name.strip()
        action = action.strip().lower()
        if not character_name:
            return json.dumps(
                {"ok": False, "error": "角色名称不能为空", "data": None},
                ensure_ascii=False,
            )

        res = await state.fix_character(
            session_id=session_id,
            character_name=character_name,
            action=action,
            details=details,
        )
        if res.get("ok"):
            return json.dumps(
                {"ok": True, "data": res, "error": None}, ensure_ascii=False
            )
        else:
            return json.dumps(
                {"ok": False, "error": res.get("error", "操作失败"), "data": None},
                ensure_ascii=False,
            )
    except Exception as e:
        return json.dumps(
            {"ok": False, "error": f"修正角色失败: {e}", "data": None},
            ensure_ascii=False,
        )

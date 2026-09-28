"""style_skills arm: run the real plugin hook in-process to build the system prompt.

Calling ``StyleSkillsPlugin.on_llm_request`` directly keeps parity with live
behaviour (code changes, the ``injected_skills`` override directory, header
format) without needing a persona created through the dashboard.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .. import LIVE_DATA_DIR
from ..matrix import Cell
from .base import SessionAborted
from .direct import persona_base

LIVE_INJECTED_SKILLS = (
    LIVE_DATA_DIR / "plugin_data" / "style_skills" / "injected_skills"
)


class _StubEvent:
    def __init__(self, umo: str):
        self.unified_msg_origin = umo
        self.extras: dict[str, Any] = {}

    def set_extra(self, key: str, value: Any) -> None:
        self.extras[key] = value

    def get_extra(self, key: str, default: Any = None) -> Any:
        return self.extras.get(key, default)


def _skill_hashes(root: Path) -> dict[str, str]:
    out = {}
    if root.exists():
        for path in sorted(root.glob("*/SKILL.md")):
            out[f"{path.parent.name}"] = hashlib.sha256(path.read_bytes()).hexdigest()[
                :16
            ]
    return out


class StyleSkillsPromptBuilder:
    def __init__(self, config_overrides: dict[str, Any] | None = None):
        from plugins.astrbot_plugin_style_skills.main import StyleSkillsPlugin

        config = {
            "style_skills_dir": str(LIVE_INJECTED_SKILLS),
            **(config_overrides or {}),
        }
        self.config = config
        self.plugin = StyleSkillsPlugin(context=SimpleNamespace(), config=config)

    def skill_hashes(self) -> dict[str, Any]:
        return {
            "builtin": _skill_hashes(self.plugin._builtin_skills_dir),
            "injected": _skill_hashes(Path(self.config["style_skills_dir"])),
        }

    async def __call__(
        self, cell: Cell, base: str | None = None
    ) -> tuple[str, dict[str, Any]]:
        if base is None:
            base = persona_base(cell)
        event = _StubEvent(f"rp-bench:style_skills:{cell.key}")
        req = SimpleNamespace(system_prompt=base)
        await self.plugin.on_llm_request(event, req)
        if not event.extras.get("single_role_style_active"):
            raise SessionAborted(
                "style_skills injected nothing (plugin disabled or no skills found); "
                "the arm would silently equal raw"
            )
        return req.system_prompt, {
            "style": event.extras.get("single_role_style_name", ""),
            "layers": event.extras.get("single_role_injection_layers", []),
            "injected": bool(event.extras.get("single_role_style_active")),
        }

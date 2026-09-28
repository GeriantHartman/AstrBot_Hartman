"""Isolate AstrBot import side effects from the live instance.

``import astrbot.core`` (triggered by *any* ``astrbot.*`` import, including
``astrbot.api.logger``) builds ``AstrBotConfig()``, opens ``data/data_v4.db``
and configures log files under ``ASTRBOT_ROOT``/cwd. The benchmark must never
rewrite the live ``data/cmd_config.json`` or share the live SQLite handle, so
the CLI points ``ASTRBOT_ROOT`` at a throwaway directory *before* the first
astrbot import. Live config files are read with plain ``json`` instead.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


class SandboxError(RuntimeError):
    pass


def astrbot_already_imported() -> bool:
    return "astrbot.core" in sys.modules


def ensure_sandbox_root(root: Path, *, strict: bool = True) -> bool:
    """Point ``ASTRBOT_ROOT`` at ``root`` before astrbot gets imported.

    Returns True when the sandbox is active. With ``strict=False`` (used by
    tests, where conftest already imported astrbot against the repo root) a
    late call returns False instead of raising.
    """
    root = Path(root).resolve()
    if astrbot_already_imported():
        current = os.environ.get("ASTRBOT_ROOT", "")
        if current and Path(current).resolve() == root:
            return True
        if strict:
            raise SandboxError(
                "astrbot.core was imported before the RP Bench sandbox was set up; "
                "live data/cmd_config.json and data_v4.db may be touched. "
                "Call ensure_sandbox_root() before importing any astrbot module."
            )
        return False
    (root / "data").mkdir(parents=True, exist_ok=True)
    os.environ["ASTRBOT_ROOT"] = str(root)
    return True

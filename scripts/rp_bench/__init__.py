"""RP Bench — roleplay benchmark for character card × model × plugin setups.

Run from the repo root:

    uv run python -m scripts.rp_bench probe
    uv run python -m scripts.rp_bench all --plan scripts/rp_bench/plans/smoke.yaml --smoke

See scripts/rp_bench/README.md for the full workflow.
"""

from __future__ import annotations

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[1]
RPG_PLUGIN_DIR = REPO_ROOT / "plugins" / "astrbot_plugin_agentic_RPG"
STYLE_SKILLS_PLUGIN_DIR = REPO_ROOT / "plugins" / "astrbot_plugin_style_skills"
LIVE_DATA_DIR = REPO_ROOT / "data"
DEFAULT_RUNS_DIR = LIVE_DATA_DIR / "rp_bench" / "runs"

__all__ = [
    "DEFAULT_RUNS_DIR",
    "LIVE_DATA_DIR",
    "PACKAGE_DIR",
    "REPO_ROOT",
    "RPG_PLUGIN_DIR",
    "STYLE_SKILLS_PLUGIN_DIR",
]

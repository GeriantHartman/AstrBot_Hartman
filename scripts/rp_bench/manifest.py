"""Record every input that can change results, so regressions are attributable."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from . import LIVE_DATA_DIR, REPO_ROOT, RPG_PLUGIN_DIR
from .config import Plan
from .store import now_utc8

RPG_CONFIG_FILE = LIVE_DATA_DIR / "config" / "astrbot_plugin_agentic_rpg_config.json"
RPG_GUIDANCE_DIRS = [
    LIVE_DATA_DIR / "plugin_data" / "astrbot_plugin_agentic_rpg" / "guidance",
]
RPG_CONFIG_KEY_HINTS = (
    "provider",
    "pipeline",
    "5_0",
    "4_0",
    "director",
    "guidance",
    "validation",
    "revalidate",
    "evolution",
    "npc_generation",
    "chat_template",
    "router",
)


def _git(*args: str, cwd: Path = REPO_ROOT) -> str:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            encoding="utf-8",  # git emits UTF-8; the Windows locale default would garble 中文 branch names
            errors="replace",
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip()


def git_state(path: Path) -> dict[str, Any]:
    status = _git("status", "--porcelain", cwd=path)
    return {
        "head": _git("rev-parse", "HEAD", cwd=path),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD", cwd=path),
        "dirty": bool(status),
        "dirty_files": len(status.splitlines()) if status else 0,
    }


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def hash_tree(root: Path, pattern: str = "**/*") -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        str(p.relative_to(root)).replace("\\", "/"): hash_file(p)
        for p in sorted(root.glob(pattern))
        if p.is_file() and "__pycache__" not in p.parts
    }


def rpg_config_snapshot() -> dict[str, Any]:
    if not RPG_CONFIG_FILE.exists():
        return {}
    try:
        cfg = json.loads(RPG_CONFIG_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        k: v
        for k, v in cfg.items()
        if any(h in k.lower() for h in RPG_CONFIG_KEY_HINTS)
    }


def build_manifest(
    plan: Plan,
    *,
    cards: list[Any],
    scenarios: list[Any],
    judge_id: str,
    judge_family: str,
    smoke: bool,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = {
        "schema_version": 1,
        "created_at": now_utc8().isoformat(),
        "plan": {
            "name": plan.name,
            "source": plan.source_path,
            "arms": plan.arms,
            "models": plan.models,
            "repeats": plan.repeats,
            "pairwise": plan.pairwise,
            "reference_arm": plan.reference_arm,
            "smoke": smoke,
            "open_api_config_id": plan.open_api.config_id,
        },
        "judge": {
            "id": judge_id,
            "family": judge_family,
            "temperature": plan.judge.temperature,
        },
        "git": {
            "repo": git_state(REPO_ROOT),
            "rpg_plugin": git_state(RPG_PLUGIN_DIR),
        },
        "cards": {
            c.key: {"name": c.name, "sha": c.sha256, "tier": c.tier} for c in cards
        },
        "scenarios": {
            s.id: {"hash": s.content_hash, "turns": len(s.turns), "path": s.source_path}
            for s in scenarios
        },
        "untracked_inputs": {
            "rpg_config": rpg_config_snapshot(),
            # per-session guidance files belong to other chats; only shared layers matter
            "rpg_guidance": {
                str(d): {
                    k: v
                    for k, v in hash_tree(d).items()
                    if not k.startswith("sessions/")
                }
                for d in RPG_GUIDANCE_DIRS
            },
            "rpg_skills": hash_tree(RPG_PLUGIN_DIR / "skills", "*/SKILL.md"),
            "rpg_prompts_yaml": hash_file(RPG_PLUGIN_DIR / "prompts.yaml")
            if (RPG_PLUGIN_DIR / "prompts.yaml").exists()
            else "",
            "rpg_user_chat_template": hash_file(
                LIVE_DATA_DIR
                / "plugin_data"
                / "astrbot_plugin_agentic_rpg"
                / "chat_template.json"
            )
            if (
                LIVE_DATA_DIR
                / "plugin_data"
                / "astrbot_plugin_agentic_rpg"
                / "chat_template.json"
            ).exists()
            else "",
        },
    }
    if extra:
        manifest.update(extra)
    return manifest

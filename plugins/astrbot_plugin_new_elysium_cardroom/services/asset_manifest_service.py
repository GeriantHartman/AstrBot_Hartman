"""Portable asset manifest for character-card migration."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from .character_relationship_service import DEFAULT_RELATIONSHIP_GRAPH_PATH
from .character_skill_service import (
    BASE_IMPORTANT_FILES,
    MODE_ADAPTER_FILES,
    CharacterSkillService,
)

PLUGIN_NAME = "astrbot_plugin_new_elysium_cardroom"
LOCAL_TZ = timezone(timedelta(hours=8))


class AssetManifestService:
    """Writes a migration-oriented manifest under plugin data."""

    def __init__(self, config):
        self.config = config
        self.base_dir = Path(get_astrbot_plugin_data_path()) / PLUGIN_NAME / "assets"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.base_dir / "character_skill_manifest.json"

    def build_manifest(
        self, character_skill_service: CharacterSkillService
    ) -> dict[str, Any]:
        roster = character_skill_service.parse_roster(
            getattr(self.config, "default_ai_skill_roster", [])
        )
        profiles = {
            profile.skill_id: profile
            for profile in character_skill_service.list_profiles()
        }
        missing_roster = [skill_id for skill_id in roster if skill_id not in profiles]
        skill_root = character_skill_service.skill_root

        skills = []
        for profile in sorted(profiles.values(), key=lambda item: item.display_name):
            skill_dir = skill_root / profile.skill_id
            files = {}
            for filename in (
                "manifest.json",
                *MODE_ADAPTER_FILES.values(),
                *BASE_IMPORTANT_FILES,
            ):
                path = skill_dir / filename
                if path.exists():
                    files[filename] = self._file_hash(path)
            skills.append(
                {
                    "skill_id": profile.skill_id,
                    "display_name": profile.display_name,
                    "has_tabletop_werewolf": (
                        skill_dir / "tabletop_werewolf.md"
                    ).exists(),
                    "has_tabletop_splendor": (
                        skill_dir / "tabletop_splendor.md"
                    ).exists(),
                    "files": files,
                }
            )

        relationship_graph = {
            "path": str(DEFAULT_RELATIONSHIP_GRAPH_PATH),
            "exists": DEFAULT_RELATIONSHIP_GRAPH_PATH.exists(),
            "sha256": self._file_hash(DEFAULT_RELATIONSHIP_GRAPH_PATH)
            if DEFAULT_RELATIONSHIP_GRAPH_PATH.exists()
            else "",
        }

        return {
            "plugin": PLUGIN_NAME,
            "generated_at": datetime.now(LOCAL_TZ).isoformat(),
            "character_skill_root": str(skill_root),
            "default_roster": roster,
            "missing_roster": missing_roster,
            "skills": skills,
            "relationship_graph": relationship_graph,
        }

    def write_manifest(self, character_skill_service: CharacterSkillService) -> Path:
        payload = self.build_manifest(character_skill_service)
        self.manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return self.manifest_path

    @staticmethod
    def _file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

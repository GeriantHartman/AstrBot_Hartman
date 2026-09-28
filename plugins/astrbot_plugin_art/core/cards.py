"""Three-tier character card manager for the art playwright plugin.

Resolution priority: Canonical > Generated > Passerby.
Generated cards use the exact same YAML schema as canonical cards.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .db import safe_session_id

_SAFE_CHARS_PATTERN = re.compile(r"[^a-zA-Z0-9_\-]")


def get_canonical_card_dirs() -> list[Path]:
    """Returns candidate directories containing canonical character YAML files."""
    candidates = [
        # Source plugin path
        Path(__file__).resolve().parent.parent.parent
        / "astrbot_plugin_agentic_RPG"
        / "canonical_characters",
        # Runtime plugin path in data/
        Path(get_astrbot_data_path())
        / "plugins"
        / "astrbot_plugin_agentic_rpg"
        / "canonical_characters",
    ]
    return [d for d in candidates if d.exists() and d.is_dir()]


def get_generated_cards_dir() -> Path:
    """Returns the root directory where generated cards are persisted."""
    path = (
        Path(get_astrbot_data_path()) / "plugin_data" / "astrbot_plugin_art" / "cards"
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


class CharacterCardManager:
    """Loads, resolves, updates, and formats character cards across three tiers."""

    def __init__(self, cards_root: Path | None = None):
        self._cards_root = cards_root or get_generated_cards_dir()
        self._canonical_cache: dict[str, dict[str, Any]] = {}
        self._load_canonical_cards()

    def _load_canonical_cards(self) -> None:
        """Loads canonical cards from available canonical directories into cache."""
        self._canonical_cache.clear()
        for directory in get_canonical_card_dirs():
            for yaml_file in directory.glob("*.yaml"):
                if yaml_file.name.startswith("_"):
                    continue
                try:
                    content = yaml_file.read_text(encoding="utf-8")
                    data = yaml.safe_load(content)
                    if isinstance(data, dict) and data.get("name"):
                        norm_name = str(data["name"]).strip().lower()
                        self._canonical_cache[norm_name] = data
                        # Index aliases
                        for alias in data.get("aliases") or []:
                            norm_alias = str(alias).strip().lower()
                            if norm_alias and norm_alias not in self._canonical_cache:
                                self._canonical_cache[norm_alias] = data
                        # Index filename stem
                        stem = yaml_file.stem.lower()
                        if stem not in self._canonical_cache:
                            self._canonical_cache[stem] = data
                except Exception as e:
                    logger.warning(
                        f"[Art.cards] Failed loading canonical card {yaml_file}: {e}"
                    )

    def list_canonical_names(self) -> list[str]:
        names = set()
        for data in self._canonical_cache.values():
            name = data.get("name")
            if name:
                names.add(str(name))
        return sorted(names)

    def resolve_card(
        self, character_name: str, session_id: str
    ) -> tuple[dict[str, Any] | None, str, Path | None]:
        """Resolves character card in order: canonical > generated.

        Returns:
            (card_dict, source, file_path)
            source is 'canonical', 'generated', or 'none'.
        """
        norm = character_name.strip().lower()

        # 1. Canonical check
        if norm in self._canonical_cache:
            card = self._canonical_cache[norm]
            return card, "canonical", None

        # 2. Generated check
        safe_id = safe_session_id(session_id)
        session_dir = self._cards_root / safe_id
        if session_dir.exists():
            for yf in session_dir.glob("*.yaml"):
                if yf.stem.lower() == norm:
                    try:
                        content = yf.read_text(encoding="utf-8")
                        card = yaml.safe_load(content)
                        if isinstance(card, dict):
                            return card, "generated", yf
                    except Exception as e:
                        logger.warning(
                            f"[Art.cards] Failed loading generated card {yf}: {e}"
                        )
                else:
                    # Check card name inside file
                    try:
                        content = yf.read_text(encoding="utf-8")
                        card = yaml.safe_load(content)
                        if (
                            isinstance(card, dict)
                            and str(card.get("name", "")).strip().lower() == norm
                        ):
                            return card, "generated", yf
                    except Exception:
                        pass

        return None, "none", None

    def list_generated_cards(self, session_id: str) -> list[dict[str, Any]]:
        """List all generated cards for this session."""
        safe_id = safe_session_id(session_id)
        session_dir = self._cards_root / safe_id
        if not session_dir.exists():
            return []
        cards = []
        for yf in session_dir.glob("*.yaml"):
            try:
                card = yaml.safe_load(yf.read_text(encoding="utf-8"))
                if isinstance(card, dict):
                    name = card.get("name", yf.stem)
                    is_superseded = name.strip().lower() in self._canonical_cache
                    cards.append(
                        {
                            "name": name,
                            "path": str(yf),
                            "superseded_by_canonical": is_superseded,
                            "card": card,
                        }
                    )
            except Exception as e:
                logger.warning(f"[Art.cards] Error reading {yf}: {e}")
        return cards

    def save_generated_card(
        self, session_id: str, character_name: str, card_data: dict[str, Any]
    ) -> Path:
        """Saves a generated card to disk in canonical YAML format."""
        safe_id = safe_session_id(session_id)
        session_dir = self._cards_root / safe_id
        session_dir.mkdir(parents=True, exist_ok=True)
        safe_char = _SAFE_CHARS_PATTERN.sub("_", character_name)
        target = session_dir / f"{safe_char}.yaml"

        # Ensure minimal required fields
        card_data.setdefault("name", character_name)
        card_data.setdefault("tier", "major")
        card_data.setdefault("game", "原创/旅途")

        yaml_content = yaml.dump(card_data, allow_unicode=True, sort_keys=False)
        target.write_text(yaml_content, encoding="utf-8")
        return target

    def update_generated_card(
        self, session_id: str, character_name: str, patch_data: dict[str, Any]
    ) -> bool:
        """Partially updates a generated card without blowing away other sections."""
        card, source, path = self.resolve_card(character_name, session_id)
        if source != "generated" or not path:
            return False

        # Merge dicts recursively
        def _deep_merge(target: dict, source: dict):
            for k, v in source.items():
                if isinstance(v, dict) and isinstance(target.get(k), dict):
                    _deep_merge(target[k], v)
                else:
                    target[k] = v

        _deep_merge(card, patch_data)
        yaml_content = yaml.dump(card, allow_unicode=True, sort_keys=False)
        path.write_text(yaml_content, encoding="utf-8")
        return True

    def delete_generated_card(self, session_id: str, character_name: str) -> bool:
        """Deletes a generated card from disk."""
        card, source, path = self.resolve_card(character_name, session_id)
        if source == "generated" and path and path.exists():
            try:
                path.unlink()
                return True
            except Exception as e:
                logger.warning(f"[Art.cards] Failed deleting {path}: {e}")
        return False

    # ----------------------------------------------------------------------
    # Prompt layer extractors
    # ----------------------------------------------------------------------

    @staticmethod
    def extract_always_injected_block(
        card: dict[str, Any],
        nsfw: bool = False,
        present_other_names: list[str] | None = None,
    ) -> str:
        """Extracts the layered prompt block for a present character."""
        name = card.get("name", "未命名角色")
        profile = card.get("profile") or {}
        voice = card.get("voice") or {}
        guidelines = card.get("interaction_guidelines") or {}

        lines: list[str] = [f"### 【角色：{name}】"]

        # 1. Essence / Core Principle
        core_principle = guidelines.get("core_principle")
        if core_principle:
            lines.append(f"- **核心神韵**：{core_principle}")

        # 2. Key Appearance Anchors (extracted 2-4 lines)
        prof_text = profile.get("profile_text", "")
        if prof_text:
            anchors = [p.strip() for p in prof_text.splitlines() if p.strip()]
            if anchors:
                lines.append(f"- **外貌与仪态**：{anchors[0][:180]}")

        # 3. Voice fingerprint
        self_ref = voice.get("self_reference", "我")
        call_player = voice.get("call_player", "你")
        tone = voice.get("tone", "")
        sig_phrases = voice.get("signature_phrases") or []
        pattern = voice.get("speech_pattern", "")

        voice_desc = f"自称“{self_ref}”，称呼玩家为“{call_player}”"
        if tone:
            voice_desc += f"，语调：{tone}"
        if pattern:
            voice_desc += f"，语言特征：{pattern}"
        lines.append(f"- **说话口吻**：{voice_desc}")

        if sig_phrases:
            lines.append(f"- **标志句式/习惯词**：{'、'.join(sig_phrases[:4])}")

        # 4. How she thinks & Inner Tension
        tension = card.get("inner_tension")
        if tension:
            lines.append(f"- **内心张力**：{tension}")

        dos = guidelines.get("do_list") or []
        if dos:
            lines.append(f"- **互动习惯**：{'；'.join(dos[:3])}")

        # 5. Canonical Quotes (first 3)
        quotes = card.get("canonical_quotes") or []
        if quotes:
            lines.append("- **声线示范**：")
            for q in quotes[:3]:
                lines.append(f"  * “{q}”")

        # 6. Never say
        never_say = card.get("never_say") or []
        if never_say:
            lines.append(f"- **严禁行为与用词**：{'；'.join(never_say[:4])}")

        # 7. Relationship hints with other present characters
        rel_hints = card.get("relations_hints") or {}
        if present_other_names and isinstance(rel_hints, dict):
            matches = []
            for other_name in present_other_names:
                for k, v in rel_hints.items():
                    if k.lower() in other_name.lower():
                        matches.append(f"对 {other_name}：{v}")
            if matches:
                lines.append(f"- **同场互动线索**：{'；'.join(matches)}")

        # 8. Intimate layer if NSFW enabled
        if nsfw:
            intimate = card.get("intimate_layer") or card.get("nsfw_guidelines")
            if intimate:
                lines.append(f"- **亲密边界与互动**：{intimate}")

        return "\n".join(lines)

    @staticmethod
    def extract_full_appearance(card: dict[str, Any]) -> str:
        """Extracts the full appearance and initial outfit details from the card."""
        name = card.get("name", "")
        profile = card.get("profile") or {}
        prof_text = profile.get("profile_text", "").strip()
        tags = profile.get("personality_tags") or []
        tags_str = f"（特征：{'、'.join(tags)}）" if tags else ""

        if prof_text:
            return f"【{name}的登场外貌】{tags_str}\n{prof_text}"
        return f"【{name}登场】{tags_str}\n面容清秀，身姿挺拔，带着独有的气质。"

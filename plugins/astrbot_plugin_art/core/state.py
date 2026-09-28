"""Unified state manager for the art playwright plugin.

All state reads and mutations must pass through here.
The Actor LLM only narrates confirmed facts supplied by state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from astrbot.api import logger

from .cards import CharacterCardManager
from .db import ArtDatabase
from .variance import roll_daily_tone, roll_scene_card


class ArtStateManager:
    """Provides a transactional, unified interface to the session state."""

    def __init__(
        self,
        db: ArtDatabase,
        card_mgr: CharacterCardManager,
        presets_dir: Path,
    ):
        self.db = db
        self.cards = card_mgr
        self.presets_dir = presets_dir
        self._preset_cache: dict[str, dict[str, Any]] = {}
        self._load_presets()

    def _load_presets(self) -> None:
        if not self.presets_dir.exists():
            return
        for json_file in self.presets_dir.glob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("name"):
                    self._preset_cache[data["name"].lower()] = data
            except Exception as e:
                logger.warning(f"[Art.state] Failed to load preset {json_file}: {e}")

    def get_preset(self, preset_name: str) -> dict[str, Any]:
        norm = (preset_name or "default").strip().lower()
        if norm in self._preset_cache:
            return self._preset_cache[norm]
        # Return default preset or minimal fallback
        if "default" in self._preset_cache:
            return self._preset_cache["default"]
        return {
            "name": norm,
            "display_name": norm,
            "description": "自由日常舞台",
            "world_setting": "充满生活气息的温馨舞台。",
            "locations": ["街角咖啡馆", "宁静公园"],
            "time_slices": ["清晨", "午后", "黄昏", "夜晚"],
            "default_location": "街角咖啡馆",
            "default_time_slice": "午后",
        }

    # ----------------------------------------------------------------------
    # Session lifecycle
    # ----------------------------------------------------------------------

    async def init_session(
        self,
        session_id: str,
        *,
        character_name: str,
        relationship_premise: str = "恋人",
        preset_name: str = "default",
        player_name: str = "开拓者",
    ) -> dict[str, Any]:
        """Initializes a new art playwright session."""
        preset = self.get_preset(preset_name)
        initial_tone = roll_daily_tone(preset.get("daily_tones"))

        # 1. Upsert session table
        await self.db.upsert_session(
            session_id=session_id,
            claimed=1,
            preset=preset.get("name", "default"),
            relationship_premise=relationship_premise,
            player_name=player_name,
            current_day=1,
            current_date_str=f"第1天 · {preset.get('default_time_slice', '午后')}",
            daily_tone=initial_tone,
        )

        # 2. Add starting relationship premise to ledger
        if relationship_premise:
            await self.db.add_ledger_entry(
                session_id=session_id,
                category="stage",
                key="关系前提",
                value=relationship_premise,
                confirmed_by_player=1,
            )

        # 3. Create initial scene
        loc = preset.get("default_location") or "街角咖啡馆"
        time_slice = preset.get("default_time_slice") or "午后"
        scene_card = roll_scene_card(preset.get("scene_cards"))
        await self.db.create_scene(
            session_id=session_id,
            location=loc,
            time_of_day=time_slice,
            present_characters=[character_name] if character_name else [],
            scene_card=scene_card,
        )

        # 4. Cast the starting character
        cast_result = None
        if character_name:
            cast_result = await self.cast_character(
                session_id=session_id,
                character_name=character_name,
                action="enter",
            )

        return {
            "session_id": session_id,
            "character_name": character_name,
            "preset": preset.get("display_name", preset_name),
            "relationship_premise": relationship_premise,
            "daily_tone": initial_tone,
            "location": loc,
            "scene_card": scene_card,
            "cast": cast_result,
        }

    # ----------------------------------------------------------------------
    # Scene transitions
    # ----------------------------------------------------------------------

    async def change_scene(
        self,
        session_id: str,
        location: str,
        time_of_day: str = "",
        present_characters: list[str] | None = None,
    ) -> dict[str, Any]:
        """Switches current scene and rolls a new scene card."""
        sess = await self.db.get_session(session_id)
        preset_name = sess.get("preset", "default") if sess else "default"
        preset = self.get_preset(preset_name)

        if not time_of_day:
            curr_scene = await self.db.get_current_scene(session_id)
            time_of_day = (
                curr_scene.get("time_of_day", "")
                if curr_scene
                else preset.get("default_time_slice", "午后")
            )

        if present_characters is None:
            # Carry over currently present characters
            present_chars = await self.db.get_present_characters(session_id)
            present_characters = [c["character_name"] for c in present_chars]

        # Roll new scene card
        scene_card = roll_scene_card(preset.get("scene_cards"))

        scene_id = await self.db.create_scene(
            session_id=session_id,
            location=location,
            time_of_day=time_of_day,
            present_characters=present_characters,
            scene_card=scene_card,
        )

        return {
            "scene_id": scene_id,
            "location": location,
            "time_of_day": time_of_day,
            "present_characters": present_characters,
            "scene_card": scene_card,
            "notice": f"📍 {location} · {time_of_day}",
        }

    # ----------------------------------------------------------------------
    # Cast operations
    # ----------------------------------------------------------------------

    async def cast_character(
        self,
        session_id: str,
        character_name: str,
        action: str = "enter",
        form: str = "",
    ) -> dict[str, Any]:
        """Performs character entrance/exit with card resolution or generation."""
        action = action.lower().strip()
        if action == "leave":
            await self.db.set_character_presence(session_id, character_name, 0)
            return {
                "character_name": character_name,
                "action": "leave",
                "state": "absent",
                "message": f"{character_name} 已离开当前场景。",
            }

        # action == "enter"
        card, source, _ = self.cards.resolve_card(character_name, session_id)
        first_appearance = False

        if not card:
            # Generate a new card and persist it
            card = {
                "name": character_name,
                "aliases": [],
                "game": "原创/相遇",
                "tier": "major",
                "profile": {
                    "profile_text": f"{character_name}，步履从容，气质独特，眼神中透着温和与好奇。",
                    "personality_tags": ["真诚", "敏锐", "有主见"],
                    "secret": "有着自己的心事与过往，期待在此刻找到共鸣。",
                },
                "voice": {
                    "self_reference": "我",
                    "call_player": "你",
                    "tone": "自然松弛，略带关切",
                    "signature_phrases": [],
                    "speech_pattern": "平实真诚，喜欢留意身边微小的细节",
                },
                "interaction_guidelines": {
                    "core_principle": "把决定留给对方，乐于分享自己的观察与想法",
                    "do_list": ["主动提议新去处", "留意玩家的喜好与情绪变化"],
                    "dont_list": ["不替玩家答应要求", "不说机械套话"],
                },
                "canonical_quotes": ["“今天的天气很舒服，要一起去走走吗？”"],
                "never_say": [],
            }
            self.cards.save_generated_card(session_id, character_name, card)
            source = "generated"
            first_appearance = True

        existing_cast = await self.db.get_character_cast(session_id, character_name)
        if not existing_cast:
            first_appearance = True

        await self.db.upsert_cast(
            session_id=session_id,
            character_name=character_name,
            card_key=source,
            is_present=1,
            current_form=form,
            first_appeared=1 if first_appearance else 0,
        )

        full_appearance = self.cards.extract_full_appearance(card)

        return {
            "character_name": character_name,
            "action": "enter",
            "state": "present",
            "card_source": source,
            "first_appearance": first_appearance,
            "appearance": full_appearance,
            "message": f"{character_name} 登场，当前在场。",
        }

    # ----------------------------------------------------------------------
    # Character fix (update, regenerate, delete)
    # ----------------------------------------------------------------------

    async def fix_character(
        self,
        session_id: str,
        character_name: str,
        action: str,
        details: str,
    ) -> dict[str, Any]:
        """Modifies, regenerates, or deletes generated character cards."""
        card, source, path = self.cards.resolve_card(character_name, session_id)
        if source == "canonical":
            return {
                "ok": False,
                "error": f"角色【{character_name}】为官方 Canonical 卡，受到永久保护，无法通过指令修改或删除。",
            }
        if source != "generated" or not path:
            return {
                "ok": False,
                "error": f"未找到角色【{character_name}】的生成卡，无法执行 {action}。",
            }

        act = action.lower().strip()
        if act == "delete":
            deleted = self.cards.delete_generated_card(session_id, character_name)
            await self.db.set_character_presence(session_id, character_name, 0)
            return {
                "ok": deleted,
                "message": f"已成功删除角色【{character_name}】的生成卡。",
            }

        if act == "update":
            # Partial patch from details
            patch = {"profile": {"profile_text": details}}
            updated = self.cards.update_generated_card(
                session_id, character_name, patch
            )
            return {
                "ok": updated,
                "message": f"已局部更新角色【{character_name}】设定：{details}",
            }

        if act == "regenerate":
            new_card = {
                "name": character_name,
                "tier": "major",
                "game": "原创/重塑",
                "profile": {
                    "profile_text": details,
                    "personality_tags": ["全新"],
                    "secret": "按照主人要求重新塑造的新设定。",
                },
                "voice": {
                    "self_reference": "我",
                    "call_player": "你",
                    "tone": "自然真诚",
                },
                "interaction_guidelines": {
                    "core_principle": "遵从新设定展开交互",
                },
            }
            self.cards.save_generated_card(session_id, character_name, new_card)
            return {
                "ok": True,
                "message": f"已重新生成角色【{character_name}】的完整设定卡。",
            }

        return {"ok": False, "error": f"未知的操作类型: {action}"}

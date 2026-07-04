---
name: new-elysium-cardroom-developer
description: Inspect, explain, debug, migrate, or develop the New Elysium Cardroom AstrBot plugin (`astrbot_plugin_new_elysium_cardroom`), a local mirrored fork for character-card AI tabletop games including Werewolf and Splendor. Use when Codex needs to work on its runtime/source copies, room commands, game phases, AI player decisions, character-skill tabletop adapters, self-check diagnostics, source/runtime mirroring workflow, or related files under `data/plugins/astrbot_plugin_new_elysium_cardroom` and `plugins/astrbot_plugin_new_elysium_cardroom`.
---

# New Elysium Cardroom Developer

## Overview

Use this skill for the local New Elysium Cardroom plugin: a New Elysium themed AstrBot tabletop room that mixes human players with character-card AI players. It currently hosts Werewolf and Splendor modes. Treat it as a mirrored local fork, not an upstream plugin install.

Runtime plugin path:

```text
data/plugins/astrbot_plugin_new_elysium_cardroom
```

Source plugin path:

```text
plugins/astrbot_plugin_new_elysium_cardroom
```

Always re-check both paths before reporting the current workflow state.

## Required Reading

Before substantial code edits, architecture explanation, migration work, or debugging, read:

```text
references/plugin-architecture.md
```

For generic AstrBot plugin API details, also use the local `astrbot-plugin-developer` skill and its docs.

## Workflow

1. Inspect the current local state first with `rg --files` and targeted reads.
2. Keep `metadata.yaml` `repo: ""`. The empty repo is intentional so AstrBot update logic does not pull this local fork back to the original Werewolf plugin line.
3. Update both runtime and source copies and compare hashes before completion. If either mirror is missing, say so before editing and recreate it only when the user asks.
4. Preserve the core service split: tabletop engine, character-skill adapter, relationship graph, behavior rolls, isolated character memory, audit ledger, and asset manifest.
5. Preserve the "cardroom principle": the plugin is for playing tabletop games with characters, not with generic game experts wearing character voices.
6. Put deterministic game mechanics in code: rooms, phases, timers, votes, role actions, platform calls, storage, validation, audit writes, asset manifests, and behavior-roll selection.
7. Put non-deterministic roleplay quality fixes in character tabletop adapters, prompts, or guidance. Do not add code-level keyword gates to judge whether a generated speech "feels in character".
8. Do not edit `services/ai_player_service.py` for normal AI behavior changes. It is legacy; the active service is `services/ai/`.

## Change Routes

- Commands: update `main.py` decorators and the matching handler under `handlers/`; keep help/status text consistent.
- Config: update `models/config.py`, `_conf_schema.json`, startup/self-check output, and any default roster logic together.
- Game rules or phases: update `models/enums.py`, `models/room.py`, the relevant `phases/*.py`, command validation, and AI context events.
- Splendor mode: update `splendor/constants.py`, `splendor/engine.py`, `splendor/models.py`, `splendor/storage.py`, `splendor/text_ui.py`, `splendor/ai.py`, `splendor/manager.py`, and `handlers/splendor_commands.py` together.
- AI action behavior: update `services/ai/actions/*`, `services/ai/context/*`, `services/ai/prompts/*`, and `services/ai/validators.py`.
- Character-first probability behavior: update `services/tabletop_behavior_service.py`, prompt appendices, and audit payloads together.
- Character relationship graph: update `assets/character_relationships.json`, `services/character_relationship_service.py`, AI context injection, self-check output, and asset manifest output together.
- Audit or replay behavior: update `services/audit_service.py`, `GameManager` lifecycle hooks, and `棋牌室审计` command output together.
- Asset migration behavior: update `services/asset_manifest_service.py`, `character_skill_root` defaults, and `棋牌室资产清单` command output together.
- Character-card AI behavior: prefer mode adapters such as `data/skills/<character>/tabletop_werewolf.md` or `data/skills/<character>/tabletop_splendor.md` and `services/character_skill_service.py` over changing base character cards.
- Name-first AI speech: keep natural speech addressed by character names or nicknames. Player numbers are operation handles for vote/check/kill commands, not social names in generated speech.
- Platform permissions: keep destructive QQ/NapCat operations behind real game flow; `棋牌室自检` should remain non-destructive.
- Default LLM isolation: keep `suppress_default_llm_during_room` and the high-priority group-message guard in `main.py` aligned. It prevents generic roleplay replies from handling invalid cardroom commands while a room exists.

## Validation

For skill edits, validate the skill folder and verify UTF-8 without BOM. For plugin code edits, run focused import or compile checks first, then the repository checks required by `AGENTS.md` when safe for the current dirty tree.

Use targeted validation examples:

```powershell
python C:\Users\Hartman\.codex\skills\.system\skill-creator\scripts\quick_validate.py E:\agentic-rpg\AstrBot\.codex\skills\new-elysium-cardroom-developer
python -m compileall -q E:\agentic-rpg\AstrBot\data\plugins\astrbot_plugin_new_elysium_cardroom
```

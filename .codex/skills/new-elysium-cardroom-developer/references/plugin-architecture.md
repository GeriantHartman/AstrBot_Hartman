# New Elysium Cardroom Plugin Architecture

Initial audit date: 2026-06-27.
Source mirror created: 2026-06-27.

## Identity And Workflow State

- Plugin ID: `astrbot_plugin_new_elysium_cardroom`
- Runtime path: `data/plugins/astrbot_plugin_new_elysium_cardroom`
- Source path: `plugins/astrbot_plugin_new_elysium_cardroom`
- Metadata: `metadata.yaml` names the plugin "新爱莉都棋牌室" and keeps `repo: ""` intentionally.
- Current scope: Werewolf mode plus Splendor mode. Werewolf default setup is 9 players: 3 werewolves, 1 seer, 1 witch, 1 hunter, 3 villagers. Both Werewolf and Splendor persist active room snapshots to SQLite under AstrBot plugin data.
- Core use case: mixed human and character-card AI games. Werewolf commonly uses `2 humans + 7 character-card AI`; Splendor supports `1-4 humans` with role-card AI filling to 2-4 players. The maintained playable character adapter pool is larger than the default fill roster and should be handled as a whole during voice-card work.

Treat runtime and source copies as a pair and compare hashes for changed mirrored files. If either side is missing, recreate the mirror from the current authoritative copy before code work.

## Design Intent

The plugin is not just a generic Werewolf bot. Its core asset is character-card AI from `data/skills`, adapted into a table-game context.

Preserve this layered design:

1. Tabletop engine: room state, player numbering, phase flow, deterministic actions, victory checks, message sending, and QQ/NapCat permissions where relevant.
2. Character-card adapter: `services/character_skill_service.py` reads character skills and mode adapters such as `tabletop_werewolf.md` or `tabletop_splendor.md`, then builds mode-safe roleplay prompts.
3. Plugin-level relationship graph: `assets/character_relationships.json` and `services/character_relationship_service.py` patch missing or asymmetric character-card relationships for the current table.
4. Character-first behavior rolls: `services/tabletop_behavior_service.py` deterministically rolls a per-action posture such as table chat, bond softening, bond pressure, quirk, or competitive play.
5. Isolated character memory: `services/character_memory_service.py` stores per-character table memories under AstrBot plugin data.
6. Audit and portability: `services/audit_service.py` writes JSONL replay ledgers; `services/asset_manifest_service.py` writes a hash manifest for character-card migration.

Do not rewrite original character cards for this mode. Add or edit mode adapters such as `tabletop_werewolf.md` or `tabletop_splendor.md`.

## File Map

- `main.py`: AstrBot `Star` registration and all command decorators. It delegates actual behavior to command handlers.
- `splendor/`: Splendor mode package. `constants.py` contains mechanical card/noble data, `engine.py` enforces rules, `models.py` stores room/player state, `storage.py` persists snapshots to SQLite, `text_ui.py` renders group status, `ai.py` selects character-card AI actions, and `manager.py` coordinates rooms.
- `_conf_schema.json`: WebUI-facing plugin config schema.
- `models/config.py`: `GameConfig`, defaults, role counts, AI provider config, roster normalization.
- `models/enums.py`: `GamePhase` and `Role`.
- `models/player.py`: human and AI player state.
- `models/room.py`: in-memory room state, vote/speaking state, timers, logs, target parsing.
- `models/ai_player.py`: `AIPlayerConfig` and `AIPlayerContext`; prompt context is built from here.
- `handlers/`: command parsing and phase permission checks.
- `handlers/splendor_commands.py`: Splendor setup, AI fill, status, and turn-action commands.
- `phases/`: deterministic phase flow and timers.
- `roles/`: role-specific state and private role information.
- `services/game_manager.py`: central coordinator for rooms, services, role assignment, victory handling, and cleanup.
- `services/audit_service.py`: local JSONL audit ledger and game summary writer.
- `services/asset_manifest_service.py`: portable character-skill manifest writer for migration.
- `services/character_relationship_service.py`: loads plugin-level relationship graph hints and injects them into AI contexts.
- `services/tabletop_behavior_service.py`: deterministic per-action probability rolls for character-first tabletop posture.
- `services/room_state_storage_service.py`: SQLite snapshots for active Werewolf rooms, including phase, players, role state, votes, speaking state, AI configs/contexts, audit paths, and message origin.
- `services/message_service.py`: group and private sends. Current role/vote output is text, even though draw utilities exist.
- `services/ban_service.py`: QQ/OneBot group ban, whole-group ban, temp admin, and group-card changes.
- `services/victory_checker.py`: deterministic win conditions.
- `services/ai_reviewer.py`: end-game LLM review.
- `services/character_skill_service.py`: character-skill discovery, prompt extraction, and tabletop prompt construction.
- `services/character_memory_service.py`: per-character memory load/write.
- `services/ai/`: active modular AI player implementation.
- `services/ai_player_service.py`: legacy monolith; not used by `GameManager`.
- `main.py` group-message guard: when a group has a Werewolf or Splendor cardroom, it refreshes restored room transport handles from the latest event; when `suppress_default_llm_during_room` is enabled, it also marks the event to skip AstrBot's default LLM while still allowing cardroom handlers and speech capture.
- `draw/`: PIL image helpers and bundled font. Some are legacy or currently not wired into message sending.

## Runtime Flow

1. `main.py` registers commands and creates `GameManager` plus `SplendorManager`.
2. `创建房间` creates a Werewolf `GameRoom` keyed by group ID. `创建璀璨房间` creates a Splendor room keyed by group ID.
3. Humans join with `加入房间`; normal AI can join with `<name>加入`; character-card AI can join with `加入角色AI` or `补满角色AI`.
4. `开始游戏` shuffles players, assigns numbers and roles, initializes AI contexts and memories, changes human group cards, starts whole-group ban, and private-sends role info.
5. Night flow: `NightWolfPhase` -> `NightSeerPhase` -> `NightWitchPhase`.
6. Day flow: `LastWordsPhase` when applicable, then `DaySpeakingPhase`, `DayVotePhase`, optional PK speaking/vote, then next night.
7. While a room exists, the high-priority group-message guard suppresses AstrBot's generic LLM reply path so invalid cardroom commands do not become normal RP responses.
8. AI contexts include a name-first player call sheet and relationship-graph hints for known character-card pairs.
9. AI actions append a behavior-roll prompt and write the prompt, response, action type, and roll payload to the audit ledger.
10. Victory checks run after lethal transitions. On Werewolf game end, AI memories are written, AI review may be generated, audit summary is finalized, cleanup restores group state, and the active room snapshot is deleted.
11. Werewolf and Splendor rooms persist active state in SQLite under plugin data. `terminate()` saves active snapshots instead of ending games; explicit end-game commands still clean up/delete the active room.

Timers live on `GameRoom.timer_task`; phase code must cancel or guard timers when switching phases. Timers are runtime-only and are not retroactively counted while the plugin is stopped.

Splendor has no timed phase manager by default. Turn progression happens after legal human or AI actions, plus pending discard or pending noble-choice sub-states.

## Commands

Room and AI setup:

- `创建房间`
- `加入房间`, `加人房间`, `加入`, `加人`
- `<name>加入` for normal AI, admin only by regex route
- `AI角色列表`, `角色AI列表`, `可用AI角色`
- `加入角色AI`, `角色AI加入`, `添加角色AI`, `召唤角色AI`
- `补满角色AI`
- `AI玩家列表`
- `踢出AI`, `移除AI`, `删除AI`
- `棋牌室自检`
- `棋牌室审计`, `狼人杀审计`
- `棋牌室资产清单`, `棋牌室迁移自检`
- `开始游戏`
- `结束游戏`, `关闭房间`, `关闭狼人杀`, `关闭狼人杀房间`, `解散房间`

Night:

- `办掉`
- `密谋`
- `验人`
- `救人`
- `毒人`
- `不操作`
- `开枪`

Day and query:

- `遗言完毕`
- `发言完毕`
- `开始投票`, `跳过发言`
- `投票`
- `查角色`
- `游戏状态`, `房间`, `房间状态`
- `狼人杀帮助`, `棋牌室帮助`

Splendor:

- `创建璀璨房间`, `创建璀璨`
- `加入璀璨`, `璀璨加入`
- `璀璨加入角色AI`, `璀璨添加角色AI`
- `璀璨补满AI`
- `踢出璀璨AI`, `移除璀璨AI`
- `开始璀璨`
- `结束璀璨`, `关闭璀璨`, `关闭璀璨房间`, `关闭宝石`, `关闭宝石房间`
- `璀璨状态`, `我的璀璨`
- `璀璨帮助`
- `拿宝石`
- `保留牌`
- `购买牌`, `买牌`
- `选择贵族`
- `丢宝石`, `弃宝石`

When adding commands, update `main.py`, the matching handler, help/status text, and any image/menu output if re-enabled.

## Character-Card AI Rules

`CharacterSkillService` discovers playable characters under `character_skill_root` by requiring `manifest.json` and `SKILL.md`, and excluding non-player persona kits/types such as `tabletop-character-adapter` and `character-voiced-assistant-persona`.

The public AI role list must expose only display names and list indexes, not internal directory names or absolute paths.

Default roster is configured by `default_ai_skill_roster`. `补满角色AI` follows this order until the room reaches `total_players`.

Each production-ready playable character should have mode adapters such as `tabletop_werewolf.md` and, for Splendor, `tabletop_splendor.md`. The current maintained pool covers all playable character cards discovered for the cardroom, not only the default fill roster. The service can fall back to generic extraction, but formal acceptance expects mode-specific adapters.

Runtime prompt construction must preserve:

- Character identity, first-person voice, OOC red lines, emotional texture, relationship logic.
- Name-first social address: generated speech should call other players by character names or nicknames, not "X号发言" or "X号玩家"; numbers are retained only as operation handles.
- Werewolf private information boundaries.
- Splendor public-information boundaries: no supernatural deck inspection, no extra resources, and no hidden-rule claims.
- The rule that past table memories are experience only, not current-game facts.
- The cardroom principle: the character's identity, relationships, habits, and OOC boundaries outrank professional game optimization.
- The behavior-roll rule: a rolled posture may nudge the action toward a bond, quirk, hesitation, pressure, or competitiveness, but it must remain legal and should not force repeated foolish play.
- The relationship graph rule: plugin-level edges can add missing symmetric bonds such as 三月七 <-> 长夜月 without editing the base character cards.

Runtime prompt construction should down-rank:

- Romance or intimacy routines.
- Combat mechanics, stats, equipment, and long lore dumps.
- Source-document narration such as "according to the card".

## AI Implementation

The active import is:

```python
from .ai import AIPlayerService
```

Use the modular AI files:

- `services/ai/service.py`: facade used by `GameManager`.
- `services/ai/actions/base.py`: provider lookup, `provider.text_chat`, retry, timeout, output extraction helpers.
- `services/ai/actions/werewolf.py`, `seer.py`, `witch.py`, `hunter.py`, `speech.py`, `vote.py`: action-specific prompts and parsing.
- `services/ai/context/builder.py`: prompt context from `AIPlayerContext`.
- `services/ai/context/analyzer.py`: situation and behavior analysis.
- `services/ai/prompts/*.py`: rules, role souls, tactics, templates, event tips.
- `services/ai/validators.py`: deterministic target validation.

`models/ai_player.py` renders the name-first player call sheet and relationship graph hints. `utils/player_labels.py` keeps generated speech from falling back to "X号发言" while preserving operation numbers for commands.

Normal AI may receive random Werewolf personality templates. Character-card AI must not; `SpeechAction._get_player_personality` explicitly preserves the bound character prompt instead.

`BaseAction._apply_behavior_roll` is the shared hook for probability behavior. It should remain prompt-level guidance plus audit metadata, not a code-level style judge.

`BaseAction._call_llm` records successful and final failed AI decisions when an audit context is supplied. Do not log audit data to group chat.

Splendor AI uses `splendor/ai.py` rather than `services/ai/actions/*`. It receives the rendered public table, the current player's own reserved cards, relationship hints, memories, and a legal action list from `SplendorEngine.available_actions()`. The LLM must output JSON, but `SplendorEngine` always revalidates the action and the manager falls back to a legal random-ish action on parse or legality failure.

## Self-Check And Permissions

`棋牌室自检` is the real pre-game diagnostic. It should stay non-destructive.

It checks:

- Role-count config validity.
- AI provider availability.
- `character_skill_root` readability.
- Default roster size, duplicates, missing skill folders, missing `tabletop_werewolf.md`, and Splendor adapter coverage.
- Supported character pool and tabletop adapter count.
- Character memory directory writability.
- Behavior-roll and audit switches.
- Default LLM isolation switch.
- Relationship graph asset existence and edge count.
- Asset manifest path.
- Current room composition and phase.
- Platform interface availability for private messages, group cards, whole-group ban, personal ban, and temp admin.
- Bot group role when the platform exposes it.

Do not make self-check ban users, change group cards, grant admin, or call destructive OneBot actions.

## Change Patterns

Config change:

1. Update `models/config.py`.
2. Update `_conf_schema.json`.
3. Update startup logs and `棋牌室自检` if the config affects diagnosis.
4. Update `README.md` or `PROJECT.md` only when user-facing behavior changes and the user wants docs updated.

Phase/rule change:

1. Update `GamePhase` or `Role` only if the state model truly changes.
2. Update `GameRoom` state fields and reset methods.
3. Update the relevant `phases/*.py` transition, timeout, and cleanup behavior.
4. Update handlers that accept player commands during the phase.
5. Update AI context events so AI players see the new public information.
6. Re-check victory and hunter/witch edge cases.

AI behavior change:

1. Prefer `services/ai/prompts` for instruction wording.
2. Use `services/ai/actions` when parsing, target choice, retry behavior, or fallback behavior changes.
3. Use `services/ai/validators.py` for deterministic legality checks.
4. Use `tabletop_werewolf.md` or `tabletop_splendor.md` for character-specific voice and OOC issues.
5. Do not add code regexes that score narrative style or ban vague "AI-like" text.

Splendor rule change:

1. Update `splendor/constants.py` for mechanical card, noble, color, token, or score constants.
2. Update `splendor/engine.py` for legal actions, payment, noble, turn, or winner behavior.
3. Update `splendor/text_ui.py` and `handlers/splendor_commands.py` for any changed user-facing selector or command.
4. Update `splendor/ai.py` if legal action JSON changes.
5. Update `docs/splendor_rules.md`, `docs/splendor_paradigm.md`, `skills/tabletop_splendor/SKILL.md`, and `README.md` when user-facing behavior changes.

Audit or migration change:

1. Keep audit files under AstrBot plugin data, not under the plugin source tree.
2. Keep asset manifests under plugin data and include skill IDs, each skill `manifest.json` hash, relevant adapter/source file hashes, missing roster entries, the active `character_skill_root`, and the relationship graph asset hash.
3. `character_skill_root` should default to the current AstrBot `data/skills`, and stale absolute paths should not be required for a moved install.
4. When changing audit payload shape, update `棋牌室审计`, self-check hints, and this skill.

Source mirror maintenance:

1. Verify whether `plugins/astrbot_plugin_new_elysium_cardroom` exists.
2. Verify whether `data/plugins/astrbot_plugin_new_elysium_cardroom` exists.
3. If one side is absent and the user wants normal development flow, copy the current authoritative side to recreate the mirror.
4. Exclude generated caches such as `__pycache__` and `*.pyc`.
5. Keep `metadata.yaml` `repo: ""`.
6. After any mirrored edit, compare hashes for changed files in runtime and source paths.

## Validation Checklist

- Run skill validation after changing this skill.
- For plugin code, run `python -m compileall -q data/plugins/astrbot_plugin_new_elysium_cardroom` or a narrower compile check.
- Run `ruff format .` and `ruff check .` after Python code changes when it is safe to touch the current worktree.
- If only Markdown/YAML skill files changed, prefer skill validation and BOM checks over formatting the whole dirty repository.
- Verify edited skill files are UTF-8 without BOM, especially `SKILL.md`, `agents/openai.yaml`, and files under `references/`.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AstrBot Agentic RPG plugin — a text-based RPG engine for the AstrBot chatbot framework. Transforms the LLM into a persistent virtual Game Master.

**Architecture: Thin Plugin + Skills Pack**

- **Thin Plugin** — State Machine + CRUD/Mechanic tools + hooks. Lives in AstrBot's plugin system.
- **Skills Pack** — 11 independent AstrBot Skills (SKILL.md bundles) providing GM intelligence: when to trigger, how to narrate, what rules to follow. Managed via AstrBot's native Skills system (WebUI upload, enable/disable, Persona-scoped).

**Core principle**: Plugin handles state and deterministic math. Skills handle GM intelligence and narration protocols. LLM follows Skill instructions to orchestrate tool calls and narrate results.

## Development Environment

**重要：两个代码位置**
- **开发位置（唯一修改位置）**: `E:\agentic-rpg\AstrBot\plugins\astrbot_plugin_agentic_RPG`
- **打包注入位置（只读，不要修改）**: `E:\agentic-rpg\AstrBot\data\plugins\astrbot_plugin_agentic_rpg`

所有代码修改只在开发位置进行，打包注入位置是运行时副本，不要直接修改。

Plugin at `data/plugins/astrbot_plugin_agentic_RPG/`, Skills at `data/skills/rpg-*/`.
- Python 3.10+, package manager: `uv`
- Install deps: `uv sync` (6-7 min, never cancel)
- Run: `uv run main.py` (WebUI at http://localhost:6185, creds `astrbot`/`astrbot`)
- Lint: `uv run ruff check .` then `uv run ruff format .`
- Plugin deps: `aiosqlite>=0.19.0`, `pyyaml>=6.0`

## Architecture

### Two-Layer Design

```
┌── Skills Layer (AstrBot Skills, progressive disclosure) ──────┐
│  rpg-gm-protocol   rpg-skill-check   rpg-combat              │
│  rpg-camp           rpg-scene-gen     rpg-npc-gen  rpg-trade  │
│  rpg-commission     rpg-levelup       rpg-lightcone            │
│  rpg-player-skill                                              │
│  (SKILL.md: when to trigger + narration protocol + rules)     │
├── Plugin Layer (@filter.llm_tool + hooks) ────────────────────┤
│  CRUD Tools        Mechanic Tools      Generation Tools       │
│  query_zone        skill_check         move_zone (llm_gen)    │
│  get_status        execute_camp        generate_npc (llm_gen) │
│  inventory         attack_roll         generate_commissions   │
│  affinity          trade               search_lightcone (KB)  │
│  level_progress    equip/unequip_cone  use_skill              │
├── State Machine (SQLite per session) ─────────────────────────┤
│  database.py → state_machine.py → models.py → dice.py        │
└───────────────────────────────────────────────────────────────┘
```

### What Lives Where

**Plugin (process-internal, cannot be a Skill)**:
- State Machine + Database (needs SQLite connection)
- `@filter.llm_tool()` handlers (need state machine access)
- `@filter.on_llm_request()` — injects **dynamic** world state (zones, NPCs, player stats)
- `@filter.on_llm_response()` — prepends status bar, triggers memory archival
- `/rpg` commands (start, status, inventory, map, history, reset, commission, level, lightcone, skills)
- Memory archival via `context.llm_generate()` + `context.kb_manager`
- Companion Skills auto-installation on first init

**Skills (independently deployable SKILL.md bundles)**:
- GM behavior rules, player agency enforcement — `rpg-gm-protocol`
- Skill check protocol, DC table, tier suppression, fail-forward — `rpg-skill-check`
- Combat flow, initiative, round structure — `rpg-combat`
- Camp narration by encounter_type — `rpg-camp`
- Scene enrichment, sensory description protocol — `rpg-scene-gen`
- NPC creation triggers, personality guidelines — `rpg-npc-gen`
- Economy rules, trade narration — `rpg-trade`
- Commission generation & completion protocol — `rpg-commission`
- Level-up ceremony, 3-choose-1 reward narration — `rpg-levelup`
- Light cone equipment, ability narration, KB retrieval — `rpg-lightcone`
- Active/passive skill usage and prompting — `rpg-player-skill`

### AstrBot Capabilities Used (DO NOT reinvent)

| Capability | API | Usage |
|------------|-----|-------|
| Skills system | AstrBot Skills (SKILL.md + progressive disclosure) | All GM intelligence and narration rules |
| Single LLM call | `context.llm_generate()` | Scene gen, NPC gen, memory summarization |
| Knowledge Base / RAG | `context.kb_manager` (FAISS+BM25) | Episode memory retrieval |
| Conversation history | `context.conversation_manager` | Extract dialogue for L2 summarization |
| Function Calling | `@filter.llm_tool()` returns `str` → LLM context | All game tools (return structured JSON) |
| Skill install | `SkillManager.install_skill_from_zip()` | Auto-deploy companion Skills |

### Tool Return Value Pattern

**All LLM tools return `json.dumps({...}, ensure_ascii=False)`**. The Skills teach the LLM how to narrate each type of JSON result. Tools NEVER return pre-formatted user-facing text.

```python
# CORRECT: return structured data, let Skill guide narration
return json.dumps({"roll": 14, "modifier": 2, "total": 16, "dc": 15, "success": True})

# WRONG: return formatted text (bypasses Skills narration protocol)
return "1d20(14) + 2 = 16 vs DC 15 → success"
```

### Key Identifiers

- `session_id` = `event.unified_msg_origin` — one world per chat session
- `user_id` = `event.get_sender_id()` — individual player within session
- `entity_id` = `player_{user_id}` for players, `npc_{uuid8}` for NPCs
- `local_id` = `md5(location_name + time_slice)[:16]` — deterministic zone key

### Plugin Module Map

```
core/
  database.py      — Async SQLite (aiosqlite, WAL). One .db per session. Schema v3.
  models.py        — Dataclasses: CharacterEntity, Zone, InventoryItem, EpisodeMemory,
                     Commission, PlayerLevel, EquippedLightCone, PlayerSkill
  state_machine.py — ALL state reads/writes. LLM cannot bypass.
  dice.py          — Deterministic D20 from message MD5 hash. Tier suppression.
  prompt_loader.py — Hot-reloadable YAML prompt loader.

memory/
  kb_store.py        — AstrBot KB-backed memory (FAISS+BM25 hybrid retrieval).
  episode_memory.py  — L2: llm_generate() summarize → SQLite + KB.
  semantic_memory.py — L3: llm_generate() merge episodes → chronicle.

prompt/
  assembler.py — Builds dynamic context block (world state only, no GM rules).
                 Shows level, lightcones, skills, passives in player_status.

workflows/
  skill_check.py     — D20 → SkillCheckResult.to_json_str()
  combat.py          — Attack → AttackResult.to_json_str()
  camp.py            — Rest → CampResult (generic recovery_details list).
  trade.py           — Economy → TradeResult (currency_name param).
  scene_generator.py — llm_generate() zones, fallback to static data.
  commission.py      — CommissionResult: generate/complete commissions.
  levelup.py         — LevelUpResult: grant_xp, apply_level_reward (increments level).
  lightcone.py       — LightConeResult: equip/unequip cones (applies base_effects to attrs).
  player_skill.py    — SkillUseResult: use_active_skill, get_all_passive_effects.

skills/                      # Companion Skills source (auto-installed to data/skills/)
  rpg-gm-protocol/SKILL.md
  rpg-skill-check/SKILL.md
  rpg-combat/SKILL.md
  rpg-camp/SKILL.md
  rpg-scene-gen/SKILL.md
  rpg-npc-gen/SKILL.md
  rpg-trade/SKILL.md
  rpg-commission/SKILL.md
  rpg-levelup/SKILL.md
  rpg-lightcone/SKILL.md
  rpg-player-skill/SKILL.md
```

### Three-Layer Memory System

- **L1 (Working Memory)**: AstrBot's conversation history (`conversation_manager`)
- **L2 (Episodic Memory)**: Triggered by **scene change** (`move_to_zone`) or **time change** (`execute_camp`), NOT fixed intervals. `llm_generate()` compresses recent conversation → SQLite + AstrBot KB (atomic chunk, no splitting). Fallback: also triggers after N interactions as safety net.
- **L3 (Semantic Chronicle)**: After M episodes, `llm_generate()` deep-compresses → permanent system_prompt injection

**Episode storage format**: Metadata-enriched prefix `[地点: X] [时间: Y] [玩家: Z] [关键词: A,B,C]` + summary body. Stored as single atomic chunk (pre_chunked_text) for full-episode recall.

**Session isolation**: Each `session_id` (unified_msg_origin) gets its own SQLite DB file + its own AstrBot KB instance (`rpg_mem_{session_id}`). Within a session, episodes carry `user_id` tags.

### World Preset System (Per-Session World-View)

Different groups can run different world-views simultaneously. **Zero world-view assumptions in Python code** — all come from preset JSON files.

```
presets/
  default.json       ← Generic fallback
  new-elysium.json   ← miHoYo urban romance (SP, Credits, apartment)
  star-rail.json     ← Honkai: Star Rail (HP, Star Coins, space station)
  genshin.json       ← Genshin Impact (HP+stamina, Mora, Mondstadt)
```

**Binding**: `/rpg start 角色名 preset_name` — first player in group binds the preset. Subsequent players auto-join.

**Resolution**: `_get_session_preset(session_id)` reads `game_sessions.world_preset` → loads `presets/{name}.json`.

**Preset defines**: `time_slices`, `currency_name`, `default_status_bars`, `default_attributes`, `starting_zone`, `starter_items`, `camp_recovery`, `fallback_zone`, `tier_names`, `tier_thresholds`, `xp_per_level_multiplier`, `commission_types`, `lightcone_kb_name`.

**Commands**: `/rpg preset list`, `/rpg preset current`, `/rpg preset info [name]`

### Prompts (prompts.yaml)

After Skills extraction, prompts.yaml only keeps **dynamic templates** (need runtime variables):
- `dynamic_context` — world state injection ({chronicle}, {zone_info}, {player_status})
- `status_bar` — status bar format ({time_slice}, {location})
- `game_start` — opening trigger ({player_name})
- `episode_summary`, `chronicle_merge` — called by `llm_generate()`
- `zone_generation`, `npc_generation` — called by `llm_generate()`

**Removed**: `system_core` (GM protocol + narration rules) → migrated to Skills

### Deployment Flow

1. User installs plugin via AstrBot plugin system (or git clone to `data/plugins/`)
2. Plugin `initialize()` checks if `rpg-*` Skills exist in `data/skills/`
3. If missing → copies from plugin's `skills/` directory → registers via SkillManager
4. Skills appear in WebUI, user can enable/disable/customize per Persona
5. Skills update independently: upload new ZIP via WebUI without touching plugin

## Design Invariants

1. **LLM never directly mutates world state** — all changes go through WorldStateMachine
2. **Plugin handles math, Skills handle intelligence** — deterministic calculations in Python, narration/trigger rules in SKILL.md
3. **Tools return structured JSON, Skills guide narration** — separation of mechanics and storytelling
4. **Dice are deterministic** — derived from message content MD5 hash
5. **Scenes immutable once generated** — only `override_state` marks destruction
6. **Plugin only appends dynamic state to system_prompt** — static GM rules live in Skills
7. **Time advances by player actions only** — no real-time clock
8. **No reinvented wheels** — use AstrBot's KB, conversation_manager, Skills system, llm_generate()
9. **Prefer WebUI config over hardcoded values** — any tunable number (thresholds, limits), prompt template, or provider selection should be in `_conf_schema.json` with sensible defaults, not hardcoded in Python. Use `_get_config_value()` / `_get_prompt()` to read.
10. **LLM 不处理唯一标识符** — entity_id, commission_id, cone_id 等由 plugin/workflow 自动解析。LLM 工具参数只接受人类可读的名称（NPC 名、委托标题、光锥名），plugin 负责从状态机中查找对应的唯一标识符。原因：LLM 不可靠，会编造 ID，导致整个流程崩溃。
11. **工具必须操作闭环** — 每个工具所需的关键数据必须由其自身参数或 plugin 内部查询提供，不可依赖 LLM 事先调用了另一个工具。如果工具 B 的正确执行需要工具 A 的输出（例如 entity_id），则工具 B 必须自行查询该数据，而不是假设 LLM 已调用了工具 A 并正确传递了结果。原因：LLM 可能跳过前置调用、乱序调用、或遗忘传递关键信息——任何需要 LLM 正确编排多步工具调用链才能完成的设计，都是脆弱的。
12. **语义错误显式失败，格式错误静默修正** — 工具的错误处理分两层：
    - **语义层（工具内部）**：对 LLM 提供的参数进行严格校验，不猜测、不兜底。NPC 名在当前区域找不到就返回明确错误（"当前区域未找到NPC: XXX"），不要静默跳过或模糊匹配到其他实体。错误信息必须可操作——告诉 LLM 哪个参数错了、期望什么值、当前有哪些有效选项——使其能自行修正并重新调用。
    - **格式层（plugin/workflow）**：对 LLM 传入的格式问题（双重 JSON 编码、字符串类型的数字、多余空格）做静默修正，因为这些是传输层问题而非 LLM 意图错误。
    - 核心原则：假设 LLM **一定会**传错参数——但区分「传错了什么」和「传的格式不对」。前者需要 LLM 自行修正，后者由 plugin 代为处理。


## AstrBot API Quick Reference

```python
from astrbot.api import logger, star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse, ProviderRequest

class MyPlugin(star.Star):
    @filter.on_llm_request()     # inject dynamic world state
    @filter.on_llm_response()    # status bar + memory trigger
    @filter.command_group("cmd")  # user commands
    @filter.llm_tool(name="x")   # game tool (return JSON str → Skills guide narration)

    # Independent LLM calls
    resp = await self.context.llm_generate(chat_provider_id=id, prompt=text)

    # Knowledge Base
    result = await self.context.kb_manager.retrieve(query, kb_names, top_m_final)

    # Conversation history
    conv = await self.context.conversation_manager.get_conversation(umo, conv_id)

    # Skill auto-installation
    from astrbot.core.skills.skill_manager import SkillManager
    mgr = SkillManager()
    mgr.install_skill_from_zip(zip_path, overwrite=True)
```

## Known Core Provider Bugs & Fixes

**1. Rerank Providers (Bailian, VLLM) "无效果" Bug (已修复)**  
- **原因**：部分模型 API (如 `gte-rerank-v2` / `bge-reranker-v2-m3`) 不返回标准的 `index` 字段，或者将其包含在 `document_index` 或 `document.index` 中。底层代码在找不到 `index` 时，会使用当前遍历的序号 `idx` 临时回退。这会导致：新出炉的高分数会被强行套用原本在向量数据库里排第一的文档的顺序，使得排序结果与最初 FAISS 给的一模一样，导致重定向无效。同时对于 `vllm_rerank_source.py`，存在硬编码 `/v1/rerank` URL导致 404 问题。
- **修复措施**：在 `_parse_results`（Bailian）和 `rerank`（VLLM）中加入了深层键值探测与日志警告系统，并增强了 URL 末尾拼接验证，如果后续 AstrBot 官方升级覆盖了 `bailian_rerank_source.py` 以及 `vllm_rerank_source.py` 必须重新补齐这一容错解析算法。

**2. Gemini Provider (Google GenAI 原生) 参数无响应 Bug (确认存在，待修复)**  
- **状况**：修改后台中的生成温度 (`temperature`)、`top_p` 等 `extra_body` 参数无法对其产生影响。
- **原因**：审查 `gemini_source.py` 可以发现，其内部的 `text_chat` / `text_chat_stream` 方法接收了包含各种配置的 `**kwargs` 参数，但是在往下层 API 构建 `payloads` 发起网络请求时，使用的是手动定死的组装 `payloads = {"messages": context_query, "model": model}`，从而使得 `**kwargs` （包含外部注入的环境温度与自定义 config）在真正进入到 `_prepare_query_config` 前就被硬生生地遗弃了。

**3. Grok/XAI Provider 失效无效 Bug (确认存在，待修复)**
- **状况**：调用 Grok 模型提供商直接显示无效或报错。
- **原因**：当前 AstrBot 核心引擎关于 XAI/Grok 的底层驱动可能由于 XAI 后来更换了终点适配标准或内部封装组件过期而无法使用。目前在 `core/provider/sources` 下甚至查不到正确完整的或兼容最新接口协议的 `grok_source.py`/`xai_source.py` 以进行无缝的对话链传输。需完全重新适配或排查其 API 定义。

**4. 空 @ 消息在关闭等待后仍消耗 token (已修复)**
- **文件**：`astrbot/builtin_stars/session_controller/main.py`
- **状况**：`empty_mention_waiting` 设为 `false` 后，空 @ 消息不再触发等待，但事件没有被 `stop_event()` 拦截，继续传播到主 LLM 管道，导致空消息仍然消耗 token。
- **修复措施**：在 `handle_empty_mention` 中，当 `empty_mention_waiting=false` 且检测到空 @ 时，立即调用 `event.stop_event()` 并 `return`，阻止事件泄漏到主 LLM handler。如果后续 AstrBot 官方升级覆盖了 `session_controller/main.py`，必须检查此修复是否被保留。

**5. OpenAI Provider 错误捕获过宽误判工具支持 (已修复)**
- **文件**：`astrbot/core/provider/sources/openai_source.py`
- **状况**：`_handle_api_error` 中的字符串匹配 `"tool" in str(e).lower() and "support" in str(e).lower()` 会误中 `tool_choice` 相关的错误（如 DeepSeek 返回 `"does not support this tool_choice"`），将其错误判断为"模型不支持工具调用"，导致所有 tools 被移除后重试。
- **修复措施**：将 `"tool"` 匹配改为 `re.search(r"\btool\b", ...)` 词边界匹配，避免 `tool_choice`、`tool_calls` 中的 "tool" 被误命中。如果后续 AstrBot 官方升级覆盖了 `openai_source.py`，必须检查此修复是否被保留。

**6. skills_like 模式 re-query 与思考模式不兼容 (已修复)**
- **文件**：`astrbot/core/agent/runners/tool_loop_agent_runner.py`
- **状况**：`skills_like` 模式的二次询问（re-query）使用 `tool_choice="required"`，但 `deepseek-reasoner` 等思考模式模型不支持此值，导致 400 错误。
- **修复措施**：(1) 当第一次响应已包含完整参数时，跳过 re-query；(2) 当响应包含 `reasoning_content`（思考模式）时，re-query 降级使用 `tool_choice="auto"`。如果后续 AstrBot 官方升级覆盖了 `tool_loop_agent_runner.py`，必须检查此修复是否被保留。

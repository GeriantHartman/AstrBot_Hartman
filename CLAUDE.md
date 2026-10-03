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

以下路径均相对于本文件所在目录（AstrBot 仓库根目录）。

- **开发位置（唯一修改位置）**: `plugins/astrbot_plugin_agentic_RPG`
- **打包注入位置（只读，不要修改）**: `data/plugins/astrbot_plugin_agentic_rpg`

所有代码修改只在开发位置进行，打包注入位置是运行时副本，不要直接修改。

**重要：禁止直接读取Astrbot原始log**
- **Astrbot默认生成的log位置：`data/logs`
禁止直接从该文件夹获取log。log中包含了巨量的文本，会造成大量的token浪费。
只能读取仓库根目录下的 `log.log`。
该log由用户筛选过。当你认为需要补充log时，先提出要求，由用户为你筛选。

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

**All LLM tools MUST return via the unified envelope helpers in `core/tool_response.py`** (`tool_ok` / `tool_err` / `tool_ok_raw`). The envelope is the single signal `tool_executor` uses to distinguish tool-execution failure (retry) from game-mechanic outcome (narrate). The Skills teach the LLM how to narrate each type of JSON result. Tools NEVER return pre-formatted user-facing text.

**Envelope format:**
```json
{"ok": true,  "data": {...business fields...}}
{"ok": false, "error": "human-readable reason", "data": {...optional hints...}}
```

```python
from .core.tool_response import tool_ok, tool_err

# Tool-execution succeeded — data carries all business fields
return tool_ok(roll=14, total=16, dc=15, success=True)
# → {"ok": true, "data": {"roll": 14, "total": 16, "dc": 15, "success": true}}

# Tool-execution failed (semantic error — LLM should retry with fixed args)
return tool_err("当前区域未找到NPC: 张三", available=["李四", "王五"])
# → {"ok": false, "error": "...", "data": {"available": [...]}}

# WRONG: return formatted text (bypasses Skills narration protocol)
return "1d20(14) + 2 = 16 vs DC 15 → success"
```

**Key rule: game-mechanic "failure" is NOT a tool failure.** `perform_skill_check` rolling a 2, `execute_combat_round` missing an attack, `execute_trade` running out of money — these are legitimate outcomes the LLM must narrate. They go in `data` with `ok=true`. Only use `tool_err` when the tool itself cannot run (entity not found, DB write failed, bad args that the LLM should fix and retry).

**Workflow dataclasses** (`SkillCheckResult`, `AttackResult`, etc.) wrap `asdict(self)` via `tool_ok_raw(asdict(self))` in their `to_json_str()`.

`tool_executor` auto-unwraps `data` into `entry.result` on success, so downstream consumers (`narrative_package` etc.) keep reading flat fields like `entry.result["npc_name"]` without caring about the envelope.

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
13. **信息完整性优先于 token 预算** — 注入给 LLM 的玩家状态、NPC 上下文、委托信息、KB 搜索结果、近期事件等核心叙事/决策信息**禁止硬性截断或设置 token 上限**。信息丢失导致的 LLM 误判 + Stage 3 重试成本（每次 6000+ prompt tokens）远超过多注入 200-500 tokens 的成本。如果担心上下文过长，优化结构/去重/换更精简表达，不要靠 `[:N]` 截断、`max_chars` 硬上限、"前 N 条然后省略"。例外：真正的大数据集（全部 L2 记忆、全 KB 文档）用分页/检索是正确的，但单个互动 NPC 的 events、单个玩家的 status、单次 KB 搜索的全部命中，必须全量注入。

14. **工具返回格式统一信封** — 所有 `@filter.llm_tool` 必须通过 `core/tool_response.py` 的 helper 返回，单一真相:

    - `tool_ok(**data)` — 工具执行成功。所有业务字段（包括游戏机制的 `success`/`hit`/`leveled_up`）放进 kwargs。
    - `tool_err(error, **extras)` — 工具执行失败。`error` 人类可读描述原因；`extras` 变成 `data` 字段（如 `available=[...]`）供 LLM 修正重试。
    - `tool_ok_raw(dict)` — workflow dataclass `to_json_str()` 专用，直接包 `asdict(self)`。

    **关键语义边界**:
    - 工具执行层 = `ok` 字段（tool_executor 唯一识别的失败信号）。
    - 游戏机制层 = `data` 里的业务字段（`success`/`hit` 等）。**投骰失败、攻击 miss、钱不够不是工具失败** — 返回 `tool_ok(success=False, ...)`，让叙事 LLM 解读并呈现。

    **禁止**在工具返回中混用 `error`/`errors`/`status`/`success`（作为顶层字段）等旧信号。tool_executor 对不符合信封的返回不识别失败，所有"看似失败"的旧格式都会被当成成功传递给 LLM。


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

> **基底**：本仓库已合并 `migrate/upstream-4.28` 与官方稳定版 `v4.28.2`，保留 origin 的 ART、RPG 5.0 和核心补丁。
> 下面每条都标注了合并后修复实际所在的文件；AstrBot 官方升级覆盖这些文件时，
> 必须逐条重新补齐。验证方式：`git diff upstream/master HEAD -- <文件>`。

**1. Rerank Providers (Bailian, VLLM) "无效果" Bug (已修复)**  
- **原因**：部分模型 API (如 `gte-rerank-v2` / `bge-reranker-v2-m3`) 不返回标准的 `index` 字段，或者将其包含在 `document_index` 或 `document.index` 中。底层代码在找不到 `index` 时，会使用当前遍历的序号 `idx` 临时回退。这会导致：新出炉的高分数会被强行套用原本在向量数据库里排第一的文档的顺序，使得排序结果与最初 FAISS 给的一模一样，导致重定向无效。同时对于 `vllm_rerank_source.py`，存在硬编码 `/v1/rerank` URL导致 404 问题。
- **修复措施**：在 `_parse_results`（Bailian）和 `rerank`（VLLM）中加入了深层键值探测与日志警告系统，并增强了 URL 末尾拼接验证，如果后续 AstrBot 官方升级覆盖了 `bailian_rerank_source.py` 以及 `vllm_rerank_source.py` 必须重新补齐这一容错解析算法。

**2. Gemini Provider (Google GenAI 原生) 参数无响应 Bug (已修复)**  
- **文件**：`astrbot/core/provider/sources/gemini_source.py`
- **状况**：修改后台中的生成温度 (`temperature`)、`top_p` 等 `extra_body` 参数无法对其产生影响。
- **原因**：`gemini_source.py` 的 `text_chat` / `text_chat_stream` 从未读取 `self.provider_config.get("custom_extra_body")`，导致 WebUI 中配置的 `extra_body` 永远不生效（OpenAI/Anthropic provider 都有此逻辑，唯独 Gemini 遗漏）。之前的 kwargs 转发修复只覆盖了调用方显式传参的场景，未覆盖 WebUI extra_body 路径。
- **修复措施**：在 `text_chat` 和 `text_chat_stream` 构建 payloads 后，显式读取 `self.provider_config.get("custom_extra_body", {})` 并合并到 payloads（支持 JSON 字符串值自动解析）。这样 `_query` / `_query_stream` 中的 `payloads.get("temperature", 0.7)` 就能拿到 WebUI 配置值。如果后续 AstrBot 官方升级覆盖了 `gemini_source.py`，必须重新补齐 custom_extra_body 合并逻辑 + kwargs 转发循环。

**3. Grok/XAI Provider 失效无效 Bug (确认存在，待修复)**
- **状况**：调用 Grok 模型提供商直接显示无效或报错。
- **原因**：当前 AstrBot 核心引擎关于 XAI/Grok 的底层驱动可能由于 XAI 后来更换了终点适配标准或内部封装组件过期而无法使用。目前在 `core/provider/sources` 下甚至查不到正确完整的或兼容最新接口协议的 `grok_source.py`/`xai_source.py` 以进行无缝的对话链传输。需完全重新适配或排查其 API 定义。

**4. 空 @ 消息在关闭等待后仍消耗 token (已修复)**
- **文件**：`astrbot/builtin_stars/astrbot/main.py`（`handle_empty_mention`）。
  上游 v4.24.1 删除了 `session_controller`，该逻辑搬到了这里，修复已随之迁移。
- **状况**：`empty_mention_waiting` 设为 `false` 后，空 @ 消息不再触发等待，但事件没有被 `stop_event()` 拦截，继续传播到主 LLM 管道，导致空消息仍然消耗 token。
- **修复措施**：在 `handle_empty_mention` 中，当 `empty_mention_waiting=false` 且检测到空 @ 时，立即调用 `event.stop_event()` 并 `return`，阻止事件泄漏到主 LLM handler。如果后续 AstrBot 官方升级覆盖了 `session_controller/main.py`，必须检查此修复是否被保留。

**5. OpenAI Provider 错误捕获过宽误判工具支持 (已修复)**
- **文件**：`astrbot/core/provider/sources/openai_source.py`
- **状况**：`_handle_api_error` 中的字符串匹配 `"tool" in str(e).lower() and "support" in str(e).lower()` 会误中 `tool_choice` 相关的错误（如 DeepSeek 返回 `"does not support this tool_choice"`），将其错误判断为"模型不支持工具调用"，导致所有 tools 被移除后重试。
- **修复措施**：将 `"tool"` 匹配改为 `re.search(r"\btool\b", ...)` 词边界匹配，避免 `tool_choice`、`tool_calls` 中的 "tool" 被误命中。如果后续 AstrBot 官方升级覆盖了 `openai_source.py`，必须检查此修复是否被保留。

**6. skills_like 模式 re-query 与思考模式不兼容 (上游已修复，本地版本已丢弃)**
- **文件**：`astrbot/core/agent/runners/tool_loop_agent_runner.py`
- **状况**：`skills_like` 模式的二次询问（re-query）使用 `tool_choice="required"`，但 `deepseek-reasoner` 等思考模式模型不支持此值，导致 400 错误。
- **现状**：上游 `6b36e1aba`（v4.24.1）在 `_resolve_tool_exec` 中移除了 `tool_choice="required"`，问题已不存在。合并时采用上游实现，不再维护本地的「跳过 re-query / 降级 auto」分支。

**7. Provider 设置不同步到多 Config Profile (已修复)**
- **文件**：`astrbot/core/provider/manager.py`
- **状况**：WebUI 更新 Provider 设置（如 modalities 加入 `tool_use`）时，只更新了 default config。其他 config profile 保持旧值，导致非 default config 的 LLM 请求中 `modalities` 不含 `tool_use`，所有插件工具被 `_modalities_fix` 静默清空（`req.func_tool = None`）。
- **修复措施**：`update_provider()`、`create_provider()`、`delete_provider()` 三个方法改为遍历 `self.acm.confs` 中所有 config 进行同步操作，而非只操作 `self.acm.default_conf`。如果后续 AstrBot 官方升级覆盖了 `provider/manager.py`，必须检查此修复是否被保留。

**8. Provider 瞬时错误缺少重试与类型化异常 (已修复)**
- **文件**：`astrbot/core/exceptions.py` + `astrbot/core/provider/sources/gemini_source.py` + `astrbot/core/provider/sources/openai_source.py`
- **状况**：
  - Gemini PROHIBITED_CONTENT/SAFETY/BLOCKLIST/SPII 以及空 candidates 一律 raise 通用 `Exception`，上层无法区分"可重试瞬时错误"与"不可重试内容过滤错误"，无法进行 provider fallback。
  - 504/503/502/timeout/connection 错误无自动重试，直接异常。
  - retry count 硬编码 10，backoff 只对 429 生效且为 1s 平退避。
- **修复措施**：
  - `exceptions.py` 新增 `LLMContentFilteredError`（内容过滤，不可同 provider 重试）和 `LLMTransientError`（瞬时错误，可重试）。
  - `gemini_source.py` 的 `_process_content_parts` 将 PROHIBITED_CONTENT/SAFETY/BLOCKLIST/SPII/IMAGE_SAFETY 改 raise `LLMContentFilteredError`；空 candidates 改 raise `LLMTransientError`。主循环（`text_chat` + `text_chat_stream`）对 `LLMTransientError`、`EmptyModelOutputError` 及 APIError 500/502/503/504 做 exp backoff（1s、2s、4s... 上限 30s），`LLMContentFilteredError` 直接上抛让 plugin 做 fallback。`retry_max` + `retry_backoff_base` 改读 `provider_config`。
  - `openai_source.py` 的 `_handle_api_error` 对 502/503/504/timeout/connection error 增加 exp backoff + return tuple 让主循环重试；同时在最终失败时若是瞬时错误则包装成 `LLMTransientError` 抛出。`max_retries` 改读 `provider_config.get("retry_max", 10)`。主循环对 `LLMContentFilteredError` 不拦截，直接上抛。
- **合并后的现状（v4.28.1 基底）**：
  - **重试与退避已交还上游**。上游 `request_retry.py`（#8893，v4.26.0）统一处理 502/503/504/timeout/connection 的指数退避，本地不再维护第二套退避逻辑。
  - **仍需保留的是类型化异常**：`astrbot/core/exceptions.py` 的 `LLMContentFilteredError` / `LLMTransientError`；`gemini_source.py` 对安全拦截抛前者、对空 candidates 抛后者；`tool_loop_agent_runner.py` 把 `LLMTransientError` 与 `EmptyModelOutputError` 一起纳入重试，而 `LLMContentFilteredError` 故意不重试，直接落到换 provider 的分支。
  - RPG 插件的 `handlers/llm_retry.py` 依赖这两个异常类，删掉会导致插件导入失败。

**9. DeepSeek V4 思考模式 `reasoning_content` 强制字段注入缺失 (已修复)**
- **文件**：`astrbot/core/provider/sources/openai_source.py`（`_finally_convert_payload`）
- **错误信号**：`BadRequestError 400 - "The reasoning_content in the thinking mode must be passed back to the API."`
- **状况（两个并列的 bug，同时触发）**：
  - (A) 模型名检测太严苛：`model in {"deepseek-v4-pro", "deepseek-v4-flash"}` 用集合**等值**匹配，遇到 `"deepseek/deepseek-v4-pro"`（OpenRouter 风格前缀）或 `"deepseek-v4-pro-2024-12-01"`（带日期后缀）直接 miss，`is_deepseek_v4_reasoning=False`。若此时 `base_url.host` 也不含 `api.deepseek.com`（例如走 Cloudflare AI Gateway 或 OpenRouter），就完全落入失效分支。
  - (B) 注入分支只认 list-content：仅 `isinstance(message.get("content"), list)` 分支会写 `reasoning_content`。从 DB 还原的 assistant 消息、或任何一轮没有 ThinkPart 的助手文本，其 content 是 string/None，这一整块都被跳过——DeepSeek 拿到"没有 reasoning_content"的历史消息直接 400。
- **修复措施**：
  - 模型名改为**子串匹配**列表 `("deepseek-v4-pro", "deepseek-v4-flash", "deepseek-reasoner")`，并放宽 host 检查到包含 `deepseek` 即可。
  - `_finally_convert_payload` 的 assistant 循环展开成两个分支：
    - `isinstance(content, list)`：原有行为 + 幂等化（只在缺字段时补），且 list 里元素加 `isinstance(part, dict)` 保护。
    - 其它（string / None）：当 `is_deepseek_v4_reasoning` 为真且消息尚无 `reasoning_content` 时，直接 `message["reasoning_content"] = "none"` 占位，info 日志提示。
- 如果后续 AstrBot 官方升级覆盖了 `openai_source.py`，必须检查此两处是否保留。验证方法：把 deepseek-v4-pro 模型走任意 OpenAI 兼容 provider（带 `provider/` 前缀或自定义 base_url），连续多轮 tool-loop，不应再报 `reasoning_content must be passed back` 400。

**10. 插件注册的静态页面需要 JWT 豁免才能直接打开 (已修复)**
- **文件**：`astrbot/dashboard/server.py`（`allowed_endpoints` 列表）
- **状况**：`context.register_web_api(route="/rpg-chat-template-editor", methods=["GET"], ...)` 注册的插件自定义页面最终由 `/api/plug/<path>` 统一分发。`auth_middleware` 对任何 `/api/*` 请求强制 JWT 校验，用户直接在浏览器打开 `http://localhost:6185/api/plug/rpg-chat-template-editor` 会返回 `{"status":"error","message":"未授权","data":null}` 401。夹在 AstrBot 主面板 iframe 里、或手动在浏览器里访问，都会失败。
- **修复措施**：把插件注册的 **只读静态页面** 路径加入白名单，跳过 JWT。
- **v4.28 基底需要改两处，只改一处无效**：上游把后台迁到 FastAPI 后，`/api/plug/{path}` 这条路由自身还有一层 `Depends(require_dashboard_user)`，它在 `server.py` 的中间件之后运行。中间件放行了，这一层照样 401。
  - 唯一来源：`astrbot/dashboard/api/auth.py` 的 `PUBLIC_PLUGIN_ENDPOINT_PREFIXES`，新增路径改这里。
  - `astrbot/dashboard/server.py` 的 `allowed_endpoint_prefixes` 展开引用它。
  - `astrbot/dashboard/api/plugins.py` 的 `dashboard_plugin_extension_route` 用 `optional_dashboard_user` 而不是 `require_dashboard_user`。
- 验证：`uv run python scripts/research/check_plugin_web_routes.py`（需先启动 AstrBot）。编辑器页无 JWT 应 200 text/html，数据接口无 JWT 应 401、带 JWT 应 200 JSON。数据读写接口（例如 `/api/plug/rpg-chat-template` GET/POST）仍然需要 JWT，由页面 JS 从 `localStorage.token` 读出后以 `Authorization: Bearer` 头携带。目前已加入：`/api/plug/rpg-chat-template-editor`（Agentic RPG 的 Chat Template 可视化编辑器，历史名 rpg-preset-editor）。未来其它插件若有类似需求，在同一数组里追加。
- 如果后续 AstrBot 官方升级覆盖了 `server.py`，必须重新补齐这些白名单项，否则插件页面会在浏览器里失去访问。

**11. `_save_to_history` 对 system role 漏识别 `_no_save` (已修复)**
- **文件**：`astrbot/core/pipeline/process_stage/method/agent_sub_stages/internal.py`（`_save_to_history` 方法）
- **状况**：`Message._no_save` PrivateAttr 的本意是"这条消息不要写入 conversation 持久化"。AstrBot 自己的 persona_mgr 就依赖它（`persona_mgr.py:395`）。但 `_save_to_history` 的过滤逻辑只在 role 是 `"assistant"` 或 `"user"` 时检查该标记——role=`"system"` 的消息（除了"第一个 system"作为 persona 被单独跳过）**即使带了 `_no_save=True` 也会被保存**。
- **影响场景**：插件通过 `@filter.on_llm_request` 向 `req.contexts` 注入 chat template 结构时，depth-inject 块（role=system）无法被豁免 → 每轮都持久化 → 下一轮 `build_main_agent` 从 DB 加载 history 时堆积起来，N 轮后 prompt 里有 N 套过时的 system 注入，cache miss + token 爆炸。
- **修复措施**：把过滤条件从 `if message.role in ["assistant", "user"] and message._no_save:` 改成 `if message._no_save:`（覆盖所有 role）。注意仍保留"跳过首个 system 作为 persona"的现有逻辑在前面。
- 如果后续 AstrBot 官方升级覆盖了 `internal.py`，必须重新补齐此判断，否则 chat_template 插件的持久化会再次失控。

**12. truncator 按 role 粗分类，无法区分"真实历史"与"插件注入"(已修复)**
- **文件**：`astrbot/core/agent/message.py` + `astrbot/core/agent/context/truncator.py` + `astrbot/core/provider/sources/openai_source.py` + `astrbot/core/provider/sources/gemini_source.py`
- **状况**：`ContextTruncator.truncate_by_turns` 的 `_split_system_rest` 把 messages 粗分成 "system（全保留）" + "non-system（按 turn 截取最后 N 对）"。这对纯 AstrBot 场景够用，但**对使用 chat_template 结构的插件破产**——插件在 contexts 头部注入 few-shot（role=user/assistant）时，这些消息会作为"最老的 non-system"首批被截掉。同时插件在 contexts 尾部注入 depth-inject（role=system）会被无条件保留（配合 bug 11 导致堆积）。
- **修复措施**：引入 `_no_truncate` PrivateAttr（`message.py:199` 附近，同时 `bind_checkpoint_messages` 搬运 dict key→PrivateAttr）。插件在注入 message dict 时设置 `"_no_truncate": True`。`truncator._is_pinned(msg)` 返回 `msg.role == "system" or msg._no_truncate`；`truncate_by_turns` 只对 `not _is_pinned` 的 user/assistant 做 `-N*2` 截断，并按原始 index 顺序重建（pinned 保留原位置，truncatable 填充保留项）。`openai_source.py` / `gemini_source.py` 发送前 `del part["_no_truncate"]` 避免 LLM API 收到未知字段。
- 如果后续 AstrBot 官方升级覆盖了这些文件之一，必须重新补齐（`_no_truncate` PrivateAttr 定义、model_validate 搬运、`_is_pinned` 三-pool 分类、sources 的 del 字段）。验证方法：在 RPG 插件里打开一个长 session（> `keep_most_recent_turns`），对比第 2 轮和第 20 轮的 OpenAI Request payload，few-shot 段字节必须完全一致。
- **合并后需要删除该字段的 provider 已扩到 4 个**：`openai_source.py`、`gemini_source.py`、`anthropic_source.py`、`openai_responses_source.py`（上游新增，v4.27.1）。新增 provider source 时必须同步。
- **已知缺口（未修）**：上游的 LLM 摘要压缩走 `round_utils.split_into_rounds` 按轮次切分，不认 `_no_truncate`，被标记的 few-shot 仍会被摘要掉。只有 `context_limit_reached_strategy` 设成 LLM 压缩时才会触发；按轮次截断的路径不受影响。

**13. Discord 超过 2000 字被直接截断 (已修复)**
- **文件**：`astrbot/core/platform/sources/discord/discord_platform_event.py`（`_split_message`，由 `_parse_to_discord` 调用）
- **状况**：上游实现是 `content = content[:2000]`，超出部分**直接丢弃**，只打一条 warning 日志。聊天里看不出任何异常，表现为角色把话说了一半。RPG 叙事单条常有 1000-3000 字，这条几乎必然触发。
- **修复措施**：`_split_message` 按段落 → 行 → 句子逐级切分，发成多条连续消息。
- **AstrBot 自带的分段帮不上忙**：`result_decorate/stage.py` 只对 150 字以下的消息分段，长消息原样交给适配器后被截断。
- 官方升级覆盖该文件时必须重新补齐。验证方法：让 bot 发一条 3000 字以上的回复，Discord 上应出现 2-3 条连续消息，且结尾完整。

**14. 工具调用前的中间文本会变成额外消息 (本地特性)**
- **文件**：`astrbot/core/agent/runners/tool_loop_agent_runner.py`（`_pending_text_buffer`、`discard_tool_call_briefings`）
- **状况**：模型在调用工具时顺带说的话（「让我查一下…」）会被上游当成一条正式回复立即发出，一次用户输入产生多条消息。沉浸式 RP 场景里这等于把后台过程摊给玩家看。
- **本地行为**：带 `tool_calls` 的中间文本先进缓冲区，在最终回复（无 tool_calls）时合并成一条发出；`discard_tool_call_briefings=true` 时直接丢弃。**「玩家只看到最终正文」依赖这个开关。**
- **需要同时满足的配置**：`agent_runner.config.misc.discard_tool_call_briefings=true`、`provider_settings.show_tool_use_status=false`、`show_tool_call_result=false`、`display_reasoning_text=false`、`streaming_response=false`。
- **skills_like 分支**：re-query 的 fallback 路径会提前 return，缓冲区必须在那里单独 flush，否则中间文本被静默吞掉（默认 `discard=false` 时属于丢内容的 bug）。
- 相关本地 misc 配置项：`tool_calls_history_mode`、`dynamic_tool_reduction`。三者都已按上游 #9821（v4.28.0）的新结构接入 `agent_runner.config.misc`，并在 `_migrate_agent_runner_config` 中随旧配置一起迁移（见 `tests/unit/test_agent_runner_config.py`）。
- `InternalAgentSubStage` 为这三项声明了类级默认值，保证不经 `initialize()` 的调用方（测试等）也能用 `_save_to_history`。

**15. CLAUDE.md 未记录但同样改过核心的本地改动**
升级或重新打补丁时同样要覆盖：
- `astrbot/core/provider/sources/prompt_post_processor.py`（本地新增文件）：openai / gemini / anthropic 三个 provider 都依赖它。其中 `split_leading_system_messages` 会把开头连续的 system 消息合并成一段文本；`anthropic_source._prepare_payload` 对「单条 system + list 内容」做了例外，原样透传结构化 system，避免丢掉逐块的 `cache_control`。
- `compress_old_turns`（`astrbot/core/agent/context/truncator.py` + `manager.py`）：只压缩旧轮次，提高提示词缓存命中率。
- `tool_schema_overhead`（`manager.py` + `token_counter.py` + runner）：把 tools schema 的 token 计入上下文窗口。注意上游测试里的假 `process()` 不接受这个关键字。
- QQ 长文本切分、读历史容忍 BOM（`json_utils.json_loads_no_bom`）、工具定义按名字排序、`/stop` 硬中止、TTS 默认关闭。
- `openai_source.py`：内容为空但 `reasoning_content` 非空时，把 reasoning 换进 content，避免空回复。这会让「整段都是 thinking 块」的响应产出非空正文，与上游测试预期相反（本地已调整该用例）。
- **已知失效的本地功能（未修）**：`dynamic_tool_reduction` 算出了精简后的工具列表，但 `_query`/`_query_stream` 实际仍发送完整列表，该开关从未真正生效。

## 旧 RPG 插件在 v4.28 基底上的兼容性

上线时新旧插件共存，所以旧插件必须能在新基底上跑。已验证：

- 插件加载正常（15 prompts / 9 styles / 20 canonical characters / 42 tools），`initialize()` 无异常。
- 77 处 `from astrbot ...` 导入全部解析，`llm_generate` / `tool_loop_agent` / `register_web_api` / `kb_manager.retrieve` / `conversation_manager` 的调用参数全部匹配当前签名。
- Chat Template 编辑器页与数据接口在 FastAPI 上行为正确（见上面第 10 条）。插件里的 `quart.jsonify` 走上游兼容层，可用。
- 插件测试 54 项全部通过。

需要插件侧配合的改动（已从 `compat/astrbot-4.28` 移植到当前 RPG 5.0 分支，并同步运行目录）：

- `_prepare_native_request` 在 v4.28 变成了协程。`handlers/hooks.py` 的 `_build_provider_payload_preview` 原先同步调用它，会拿到未 await 的 coroutine，审计里的 provider payload 预览静默退化成 `preview_error`。修复方式是把该方法与 `_build_narrative_audit_view` 改成 async，并用 `inspect.isawaitable` 同时兼容新旧 core。

排查脚本（都在 `scripts/research/`）：

- `check_plugin_api_compat.py` — 静态检查插件导入的 astrbot API 是否都还在。
- `check_plugin_call_sites.py` — 检查插件传给核心 API 的关键字参数是否仍被接受。
- `check_plugin_web_routes.py` — 对运行中的实例检查插件 web 路由的鉴权行为。

**未验证**：完整的一轮 RP 对话（Router 工具循环 → Director → Narrator → 记忆归档）需要配置真实 provider，本次没有跑。上线前请在测试 session 里走一轮完整对话。

**13. OpenCode Go 强制要求 `x-opencode-session` 会话头 + 专属 UA (已修复)**
- **文件**：`astrbot/core/provider/sources/openai_source.py`
- **状况**：OpenCode Go / Zen（`api_base` 含 `opencode.ai`）自 2026-09 起要求客户端在**每段对话**的 `x-opencode-session` 请求头中发送稳定的会话 ID，并发送**自身专属的 user agent** 而非通用 SDK 名（`AsyncOpenAI/Python x.y`）。缺失或使用通用 UA 会被判定为非典型编程 Agent 流量。
- **修复措施**：
  - 新增类常量 `_OPENCODE_GO_USER_AGENT = "astrbot-agentic-rpg/1.0"`、静态方法 `_is_opencode_go()`（按 `api_base` 主机名判断）、实例方法 `_opencode_session_headers()`（`uuid.uuid5(NAMESPACE_URL, session_id)` 取 hex，保持稳定且不泄漏群/会话 ID）。
  - `__init__` 中若识别为 OpenCode Go，则用 `setdefault` 把专属 UA 并入 `custom_headers`（用户显式配置的 UA 优先）。SDK 的 `default_headers` 在 `_base_client.default_headers` 中最后合并，确实能覆盖 `AsyncOpenAI/Python`。
  - `_query(payloads, tools, session_id=None)` / `_query_stream(payloads, tools, session_id=None)` 新增 `session_id` 形参，`create()` 传 `extra_headers=self._opencode_session_headers(session_id)`（per-request 头优先级高于 `default_headers`）。`text_chat` / `text_chat_stream` 把已有的 `session_id` 透传进去（上游 `tool_loop_agent_runner` 传的是 `req.session_id`，缺省即 `event.unified_msg_origin`）。
  - 无 `session_id` 时返回 `None`，SDK 视同不发送；非 OpenCode 的 provider 完全不受影响。
- 如果后续 AstrBot 官方升级覆盖了 `openai_source.py`，必须重新补齐这 3 处（类常量+2 个辅助方法、`__init__` 的 UA 注入、`_query`/`_query_stream` 的 `session_id` 形参与 `extra_headers` 及两个调用点）。验证方法：对 `api_base=https://opencode.ai/zen/go/v1/` 的 provider，用同一个 session_id 连调两次，抓到的请求头里 `x-opencode-session` 必须一致，且 `User-Agent` 为 `astrbot-agentic-rpg/1.0`。

**14. Gemini 多 Key 并发 429 轮换崩溃 `list.remove(x): x not in list` (已修复)**
- **文件**：`astrbot/core/provider/sources/gemini_source.py`（`_handle_api_error`）
- **状况**：每个请求在 `text_chat` / `text_chat_stream` 里拷贝一份自己的 `keys` 列表，但 `self.chosen_api_key` 是同一个 provider 实例上所有并发请求**共享**的。请求 A 撞 429 后把共享 key 换成 K2；如果请求 B 早先已从自己的列表里删掉了 K2，B 再撞 429 时执行 `keys.remove(self.chosen_api_key)` 就抛 `ValueError`，整条请求失败，不会继续换 key。多个会话同时撞 Gemini 限流（例如免费层每日额度用完）时必现。
- **修复措施**：删除前先判断 `self.chosen_api_key in keys`，不在就跳过删除，直接从剩余 key 里随机换一把。测试：`tests/test_gemini_source.py` 的 `test_gemini_429_rotation_*`。
- 同类隐患（未修，待核实）：`set_key()` 会重建 `self.client`，并发中的其他请求可能因旧 client 被回收而报 `ClientConnectionError: Connector is closed`。
- 如果后续 AstrBot 官方升级覆盖了 `gemini_source.py`，必须重新补齐这个判断。

**15. 唤醒前缀按字面比较，中文输入法打出的全角符号无法唤醒 (已修复)**
- **文件**：`astrbot/core/pipeline/waking_check/stage.py`（唤醒检查）、`astrbot/builtin_stars/astrbot/main.py`（空 mention 的前缀归属判断）、`astrbot/core/pipeline/process_stage/method/agent_request.py`（provider 前缀去重）、`astrbot/core/astr_main_agent.py`（provider 前缀剥离）；新增 `astrbot/core/utils/string_utils.py` 的 `to_halfwidth()`
- **状况**：唤醒检查用 `event.message_str.startswith(wake_prefix)` 做**字面**比较。这是个愚蠢的设计：中文输入法下用户顺手打出的符号默认就是全角（`～` U+FF5E、`／` U+FF0F、`！` U+FF01），而配置里的 `wake_prefix` 是 ASCII 键盘录入的半角（`~` U+007E、`/` U+002F）。码点不同，比较必然失败 → `event.stop_event()` → 整条消息被**静默丢弃**，用户侧没有任何报错。
- **日志特征**（排查用）：`WakingCheck` 阶段跑完后直接 `pipeline 执行完毕`，耗时几毫秒，且没有任何 provider/LLM 调用；`enabled_plugins_name` 正常打印但插件 handler 全部不触发。
- **修复措施**：`string_utils.py` 新增 `to_halfwidth()`，把全角 ASCII（U+FF01–U+FF5E）映射回半角（U+0021–U+007E），U+3000 表意空格映射为普通空格；映射是 1:1，因此仍可按**原串长度**裁剪前缀。上述 4 处前缀比较全部改为**两侧归一化后**再比较。另有兜底：`data/cmd_config.json` 的 `wake_prefix` 显式加入 `／` `～`，当核心补丁被官方升级覆盖时仍可工作（补丁生效时该条目冗余）。
- **为什么必须兼容全角**：目标用户是中文使用者，便捷输入产出的就是全角符号。要求用户为了唤醒机器人专门切到半角，等于把核心的设计失误转嫁成用户的操作负担——中文语境下全角是默认行为，不是边缘情况。
- 如果后续 AstrBot 官方升级覆盖了这 4 个文件之一，必须重新补齐归一化比较（`string_utils.to_halfwidth` + 4 个调用点）。验证方法：`wake_prefix` 设为 `["~"]`，发送以全角 `～` 开头的群聊消息，事件必须被唤醒且前缀被正确剥离（`～你好` → `你好`）。

**16. Discord 斜杠指令重名导致整批注册失败 (已修复)**
- **文件**：`astrbot/core/platform/sources/discord/discord_platform_adapter.py`（`_collect_and_register_commands`）
- **状况**：注册循环遍历 `star_handlers_registry`，对每个 `CommandFilter` 都调一次 `add_application_command`，**不检查重名**。Discord 要求同一应用内斜杠指令名唯一，只要有两个 handler 同名，`sync_commands()` 就会返回 `400 APPLICATION_COMMANDS_DUPLICATE_NAME`，而这是**批量**注册——**整批指令全部注册不上**，不只是冲突的那一条。
- **实际触发场景**：AstrBot 内置命令与官方扩展插件 `builtin_commands_extension` **都定义了 `provider`**（`astrbot/builtin_stars/builtin_commands/main.py:51` 与 `data/plugins/builtin_commands_extension/main.py:83`）。两者同时启用时，启动日志出现 `on_ready_once_callback err: 400 Bad Request ... In 27: Application command names must be unique`，Discord 上一条斜杠指令都没有，但机器人本体仍能收消息（异常被 discord.py 记 ERRO 后吞掉，不终止进程）。
- **修复措施**：`_collect_and_register_commands` 增加 `seen_commands` 字典按 `cmd_name` 去重，保留先遍历到的一方，跳过的记 `warning` 并打印冲突双方的 `handler_module_path`。指令名已被 `_extract_command_info` 校验为 `^[a-z0-9_-]{1,32}$`（不含大写），故直接以原名作键即可。
- **注意（未修的上游打包问题）**：这只是让冲突不再致命，并未解决源头——核心与官方扩展重复定义了同名指令。去重保留的是遍历顺序在前的一方（实践中是核心内置的那条，其 `provider` 功能弱于扩展版）。若要拿到扩展版的完整 `provider`，需**禁用其中一个插件**，而不是依赖去重。
- 如果后续 AstrBot 官方升级覆盖了 `discord_platform_adapter.py`，必须重新补齐这个去重，否则重名指令会再次导致 Discord 侧全量注册失败。

**17. 上传插件 zip 无顶层目录时解压崩溃 (4.28 基底已覆盖修复)**
- **文件**：`astrbot/core/star/updater.py` 的 `_extract_plugin_archive`，以及 `astrbot/core/zip_updater.py` 的 `_resolve_archive_root_dir` / `_finalize_extracted_archive`。
- 4.28 已将原 `updator.py` 模块重命名为 `updater.py`，归档根目录按目录条目与共同父目录解析。根级普通文件使根目录为空，直接解压，不再对 `.git` 文件执行 `listdir`。
- 合并时删除旧模块，使用新实现；验证带 `.git` 的平铺插件归档、GitHub 单顶层归档及单根文件归档，插件安装还需合法的 `metadata.yaml`。

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
- RP 跑分、模型 RP 能力对比、验角色卡、角色卡规模排名（bare / YAML / skill 卡）、插件 4.0 vs 5.0 回归 → invoke rp-bench
- Art 单主模型、工具、私有资产、UID USER、恢复或 Persona 注入修改 → invoke art-plugin-architecture；账本事故取证 → invoke art-ledger-audit

### Art 亲密情境（NSFW）接线

- 开关是会话私有 `session.nsfw`，**由主模型自行判断**，经已有 `art_write`（session 白名单本就含 `nsfw`）置位/复位；**没有面向玩家的命令入口**，代码不做关键词门控或审核正则。
- 置位后 `layers/assemble.py::dynamic_context` 把外挂资产 `plugins/astrbot_plugin_art/prompts/nsfw.yaml` 的 `guidance` 原样追加到动态块；工具成功会重建动态块，因此**同一轮内即生效**。
- 该资产**留空或缺失即不注入、不报错**（`core/assets.py::PromptStore.optional_text`），支持热重载。填写时必须整体缩进在 `guidance: |` 块标量之下——**顶格书写会让 YAML 解析失败，资产静默退化为空**，NSFW 看起来"接了但没反应"。两份副本（`plugins/` 与 `data/plugins/`）须同步且 UTF-8 无 BOM。
- 独立插件 `astrbot_plugin_nsfw_mode` 与 Art **无耦合**：它靠改写 `req.system_prompt` 注入 style，而 Art 在 `layers/agent.py` 全量重建请求；唯一能穿过来的是 `event.set_extra("selected_provider")`（见 `core/provider_resolver.py`）。provider（如 SiliconFlow/DeepSeek）自身的对齐仍可能拦截，属已知残余，不由本接线解决。

### Agent skills 双份镜像约定

`.codex/skills/` 与 `.claude/skills/` 是两个**独立**的技能加载位置。同一个 skill 必须**两侧各存一份**且内容字节一致——只写一份会让另一侧读不到，或读到过期版本。

**约定镜像的 skill**（改动 `SKILL.md`、`references/`、`scripts/` 任一文件后，必须在同一次改动中同步另一侧并校验）：

| skill | Codex 侧 | Claude 侧 |
|---|---|---|
| 角色扮演跑分 | `.codex/skills/rp-bench/` | `.claude/skills/rp-bench/` |
| RPG 审计账本 | `.codex/skills/rpg-ledger-audit/` | `.claude/skills/rpg-ledger-audit/` |
| RPG 插件架构 | `.codex/skills/rpg-plugin-architecture/` | `.claude/skills/rpg-plugin-architecture/` |
| Art 审计账本 | `.codex/skills/art-ledger-audit/` | `.claude/skills/art-ledger-audit/` |
| Art 单主模型架构 | `.codex/skills/art-plugin-architecture/` | `.claude/skills/art-plugin-architecture/` |

**暂未镜像**（目前只在 `.codex/skills/` 下）：`astrbot-plugin-developer`、`new-elysium-cardroom-developer`、`rpg-canonical-character-converter`、`rpg-tool-analysis`。若要纳入镜像，把它加进上表。

同步与校验（从仓库根运行）：

```bash
mkdir -p .claude/skills/<name>
cp -r .codex/skills/<name>/. .claude/skills/<name>/
rm -rf .claude/skills/<name>/__pycache__ .claude/skills/<name>/scripts/__pycache__
diff -rq --exclude=__pycache__ .codex/skills/<name> .claude/skills/<name>   # 必须无输出
```

新增 skill 时两侧都要建，并更新上表。所有 skill 文件必须 UTF-8 无 BOM。

### Art 拉取后的必要技能更新

每次拉取 Art 相关分支或更新插件后，由执行更新的 agent 额外核对 `art-ledger-audit` 与 `art-plugin-architecture`。**插件代码更新不能作为 agent 技能已更新的依据。** 这两个技能用于维护与审计，不是需要注入前台 RP 的 AstrBot Skills。

主仓库已跟踪 `.codex/skills/<name>/` 和 `.claude/skills/<name>/`，完整拉取此仓库会更新这些文件；但单独拉取 Art 子模块、WebUI 更新插件、部署时排除隐藏目录、稀疏检出或使用另一份 agent 工作目录，不会自动更新 agent 实际加载的副本。

执行更新的 agent 必须完成：

1. 确认已拉取的 Art 提交与对应主仓库集成版本（核对该版本的 `plugins/astrbot_plugin_art` gitlink），并定位 agent 实际使用的项目根目录。
2. 从对应版本的 [AstrBot_Hartman](https://github.com/GeriantHartman/AstrBot_Hartman) 获取两项技能的**完整目录**，包括 SKILL.md、agents、references、scripts；不能只复制入口文件，也不能用旧三阶段技能代替。
3. 在实际项目根目录更新 `.codex/skills/art-ledger-audit/`、`.claude/skills/art-ledger-audit/`、`.codex/skills/art-plugin-architecture/`、`.claude/skills/art-plugin-architecture/`。检查既有本地修改，不覆盖其他技能；两侧使用同一版本，清理已确认过时的文件。
4. 核对文件清单与逐文件 SHA-256、UTF-8 无 BOM、技能元数据与引用路径。可用时运行 skill-creator 的 quick_validate.py；分别执行审计脚本的 `--help` 验证完整目录可用。若当前 agent 未发现新技能，重新加载技能或开启新的 agent 会话后确认可用。
5. 汇报插件/技能来源提交、实际安装位置与验证结果。未取得匹配技能时明确说明缺失，不宣称维护环境更新完成。

供另一台机器的 agent 使用：

> 拉取并更新 Art 后，请额外更新当前项目的 art-ledger-audit 和 art-plugin-architecture。以已拉取 Art 提交对应的 AstrBot_Hartman 集成版本为来源，复制完整技能目录到当前 agent 实际使用的 .codex/skills 与 .claude/skills，核对文件清单、哈希、UTF-8 无 BOM 和审计脚本入口，确认新技能可被发现，并汇报来源提交与安装路径。仅更新插件目录不算完成此步骤。

### RP Bench（角色扮演跑分）

- 工具在 `scripts/rp_bench/`，由 agent 发起，用户不手动跑。完整流程见 `.claude/skills/rp-bench/SKILL.md`（`.codex/skills/rp-bench/SKILL.md` 是同内容副本，改一份必须同步另一份）。
- 固定玩家台词剧本，打不同的「模型 × 角色卡 × 插件」组合。对照组：`bare`（只给角色名+作品名）、`raw`（canonical YAML 卡）、`skill`（`data/skills/<卡>-skill/` 全文）、`style_skills`、`rpg4`、`rpg5`。
- 常用方案（`scripts/rp_bench/plans/`）：`bare.yaml` 裸考两个模型；`card-scale.yaml` 同一模型在 bare / raw / skill 三档卡规模下排名；`card-check.yaml` raw vs style_skills；`mvp.yaml` / `regression.yaml` 插件 4.0/5.0 与改动前后回归。
- 已有跑次补对照组用 `all --resume <run_dir> --add-arms <arm>`，不要重开跑次。产物在 `data/rp_bench/runs/<UTC+8时间>-<plan名>/`，先读 `index.md` 和 `compare/`。
- 没有裁判时的排名是阅读判断，汇报必须引原文、写样本量；设定核对以对应角色卡原文为准。

### RPG tool analysis and audit maintenance

- 工具分析报告、工具统计时间窗口、报告文件时间戳统一使用 UTC+8。新增统计字段或报告脚本时，不能混用 UTC/本地时间。
- `TOOL_SKILL_MAP` 只维护当前真实 LLM 工具；新增、重命名、移除工具时必须同步更新该映射。历史旧工具名只能放在工具分析 skill 的 legacy 兼容层，不要继续污染运行时映射。
- 工具使用分析只统计 LLM 行为。玩家通过 `/rpg` 内建命令触发的管理、查看、修复动作不应计入 LLM 工具使用率。

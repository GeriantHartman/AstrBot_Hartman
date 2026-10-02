# Art 审计账本字段表

对应实现：`plugins/astrbot_plugin_art/core/audit_ledger.py`。
与 RPG 的 `llm_audit_ledger.py` 同形（同名类、同 API），差异见文末「与 RPG 账本的差异」。

## 目录布局

```
data/plugin_data/astrbot_plugin_art/
  llm_audit/<session_key>/
    <turn_id>-playwright-<session_key>.json
    <turn_id>-actor-<session_key>.json
    <turn_id>-scribe-<session_key>.json
  llm_audit_index/<session_key>.jsonl        # 每轮一行（stage=actor）
```

- `session_key` = `quote(session_id, safe="-_.@=")`；超过 120 字符时截断并追加 `--<sha256[:8]>`。真实 `session_id` 是 `event.unified_msg_origin`（如 `discord:GroupMessage:1554209468223328386`）。
- `turn_id` = `{YYYYmmdd-HHMMSS}-{uuid4[:6]}`，一轮内三次调用共享它，因此三份文档同前缀。
- 索引与账本目录是**兄弟**关系：`llm_audit_index` 由 `llm_audit` 的父目录推出。

## 完整文档（每份 LLM 调用一个 JSON）

| 字段 | 类型 | 说明 |
|---|---|---|
| `audit_id` | str | `f"{turn_id}-{stage}-{session_key}"`，等于文件名去掉 `.json` |
| `schema_version` | int | 目前恒为 `1` |
| `created_at` | int | 请求时刻的 unix 秒 |
| `turn_id` | str | 轮次身份，三阶段共享 |
| `session_key` / `session_hash` | str | 可读键 / `sha256(session_id)[:16]`（旧账本回退用） |
| `session_id` | str | 真实 unified_msg_origin |
| `user_id` | str | `event.get_sender_id()` |
| `stage` | str | `playwright` \| `actor` \| `scribe` |
| `provider_id` | str | 该阶段实际使用的 provider id；空串 = 未解析到 |
| `model` | str | 该阶段 provider 的模型名 |
| `request.system_prompt` | str | 原样发出的 system prompt |
| `request.contexts` | list | 原样发出的 contexts（数字/列表内容可能已被 provider 转换） |
| `request.prompt` | str | 原样发出的当轮 prompt |
| `assembly_trace` | dict | 按 stage 不同，见下 |
| `audit_view` | dict | 按 stage 不同，见下 |
| `response.text` | str | 模型原始输出（**未经任何清洗**） |
| `response.error` | str | 调用失败原因；空串表示正常 |
| `response.updated_at` | int | 回填时刻 |
| `response.meta` | dict | 按 stage 不同，见下 |
| `metadata.turn_id` | str | 与顶层一致 |
| `metadata.current_turn` | dict | 供索引行读取：`preset_name` / `user_hash` / `user_preview`（`actor` 阶段才有） |

轮转：`llm_audit_max_files_per_session`（默认 200，`0` = 不清理）限制每 session 目录的 `.json` 数，超出按 mtime 删最旧。索引保留 `max(该值 × 2, 200)` 行。

## 各 stage 的字段差异

### `playwright`（编剧子循环）

`assembly_trace`：`max_steps`（5）、`provider_source`
`audit_view`：`scene{location,time_of_day,scene_card,present_characters}`、`daily_tone`、
`action_roll{grade,description}`（预抽行动成败）、`mid_scripts[]`、`short_hooks[]`、
`pacing_preferences[]`、`player_profile[]`
`response.meta`：
- `is_fallback`（bool）— **true 表示本轮导演笔记是写死的兜底文本**
- `fallback_reason` — `no_provider` \| `exception` \| `empty_completion`
- `tool_trace[]` — `{tool, args, ok, result_hash, result_preview, result_chars}`

### `actor`（演员主调用）

`assembly_trace`：`system_prompt_chars`、`contexts_count`、`prompt_chars`、`dynamic_block_chars`
`audit_view`：
- `director_notes` — 本轮注入的导演笔记正文
- `scene_transition_notice`、`scene_before` / `scene_after`（`{id,location,time_of_day}`）、`present_characters[]`
- `preset`、`nsfw`、`relationship_premise`、`daily_tone`
- `has_dynamic_block` — Layer 2 是否注入成功
- **`stripped_sections[]`** — 被剥离的核心注入段标签：`skills_inventory` \| `tool_call_prompt` \| `tool_call_prompt_skills_like` \| `computer_use_workspace`。**为空且 prompt 里出现 `## Skills` 即说明剥离失效**

`response.meta`：
- `cleaned`（bool）、`cleaned_hash`、`cleaned_preview`、`chars_stripped`、`raw_chars`
- `scene_switched_from`
- **`response.text` 是清洗前的原始终稿**，玩家看到的是 `clean_narrative_reply` 处理后的版本

### `scribe`（后台书记）

`assembly_trace`：`max_steps`（1）、`tools`（`"none"`）、`provider_source`
`audit_view`：`deterministic{...}`（历史字段，具体抽取已全部交给 LLM）、`actor_reply_chars`、`actor_reply_truncated`
`response.meta`：
- `parsed_ok`（bool）— JSON 解析是否成功
- `parsed` — 解析出的完整 JSON
- `parse_error` — 解析失败原因
- `hook_reaction`
- `writes[]` — **本轮实际落库的副作用**：`{category, key, value_preview}`
  - `category` 取值：`promise` / `memory` / `tiff` / `gift` / `pacing_preference` /
    `player_profile` / `script:mid` / `script:short:fade` / `script:short:accepted` / `scene_memory`

## 索引行（`llm_audit_index/<session_key>.jsonl`）

每轮一行，`stage` 恒为 `actor`（只在 actor 响应回填时追加）。字段：

`schema_version`、`audit_id`、`turn_id`、`created_at`、`session_key`、`session_hash`、`session_id`、
`stage`、`provider_id`、`model`、`preset_name`、`user_hash`、`user_preview`、
`assistant_hash`、`assistant_preview`、`response_error`（bool）、`response_meta`

**已知限制**：art 的 actor provider 由 AstrBot 主管线选定，插件无从得知，因此 `actor` 行的
`provider_id` / `model` 通常为空。要判断某轮用了哪个模型，读该轮的 **playwright / scribe 文档**
（它们自己解析 provider，会填 `model`）。

## 与 RPG 账本的差异

| | RPG | art |
|---|---|---|
| 一轮的 LLM 调用 | 1（narrator）+ 子系统 | **3**（playwright / actor / scribe），共享 `turn_id` |
| `audit_id` | `{ts}-{stage}-{session_key}` | `{ts}-{token}-{stage}-{session_key}`（token 防同秒覆盖） |
| 索引行条件 | `stage == "narrator"` | `stage == "actor"` |
| 索引行 `style` 字段 | 有 | 无（art 无叙事风格系统） |
| 写盘失败 | 上抛给调用方 | 内部吞掉返回 `None`（审计绝不影响出话） |

API 形状一致（`session_key` / `content_hash` / `preview` / `load_turn_index` / `record_request` /
`record_response`），另新增 `load_doc(audit_id, session_id)` 供按 id 回读。

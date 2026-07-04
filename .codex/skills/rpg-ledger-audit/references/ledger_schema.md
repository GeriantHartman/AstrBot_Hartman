# 审计账本字段说明

每个审计账本文件都是一个 JSON 文档。

## 顶层字段

- `audit_id`：本次请求的稳定文件编号。
- `session_key`：由真实 `session_id` 转义得到的可读、文件名安全的会话键。新账本目录和索引文件使用它命名。
- `session_hash`：旧版兼容字段；不要再把它作为首选文件名。
- `session_id`：真实会话 id。
- `stage`：当前阶段；通常是 `narrator`，表示最终 RP 叙事模型请求。
- `provider_id` / `model`：当前这一次 Narrator 请求实际调用的模型路由。它们只说明当前轮，不代表 `request.contexts` 里的全部历史。
- 顶层不再写入 `style`。风格必须从 `audit_view.current_request.style`、`audit_view.current_turn_provenance.style`、`audit_view.turn_provenance[*].style` 或 `audit_view.snapshot.style_counts` 读取。
- `request.system_prompt`：最终发送给 LLM 的 system prompt。
- `request.contexts`：最终发送给 LLM 的历史上下文消息列表。
- `request.prompt`：最终当前 user message，包含 `[RPG_DYNAMIC_CONTEXT_*]` 动态块；4.0 下通常也包含 `[RPG_TURN_CONTRACT]`。
- `assembly_trace.slots`：聊天模板各槽位渲染后的内容，尚未合并进最终请求前的来源记录。
- 新账本中 `assembly_trace.slots[*].rendered_content` 会被压缩为 `rendered_content_hash`、`rendered_content_preview`、`rendered_content_chars`，避免与 `request.*` 重复保存大段全文。完整内容仍可从 `request.system_prompt`、`request.contexts`、`request.prompt` 和槽位标记反查。
- `assembly_trace.chat_template_path`：决定槽位位置的聊天模板文件。
- `assembly_trace.guidance_meta`：本轮读取的 preset/provider 以及 `global_paths`、`style_paths`、`session_paths`。审计生成的新指导默认写入 `guidance/scoped/<preset>/<provider>/...`。
- `response.text`：模型原始回复，发生在展示用状态栏注入之前。

## 审计视图

- `audit_view.current_request`：当前 Narrator 请求实际使用的 provider、model、style。
- `audit_view.current_request` 还包含 `preset_name`，用于区分不同世界观预设。
- `audit_view.snapshot`：面向审计的快照摘要。审计对象不是单轮，而是“当前请求 + 可见历史上下文”。这里包含历史回合和当前轮的 `preset_counts`、`style_counts`、`provider_counts`、`model_counts`、`context_source_counts`。
- `audit_view.system_prompt_parts`：`request.system_prompt` 的来源切片。使用 `start` / `end` 回到真实 system prompt 中取原文，避免把 template 注入和真实历史混在一起。
- `audit_view.context_messages`：`request.contexts` 中每条消息的来源标注。`source` 常见值：
  - `conversation_history`：真实历史消息。
  - `template_few_shot`：聊天模板注入的 few-shot user/assistant 示例。
  - `template_depth_injection`：聊天模板注入的 system/depth block。
  - `conversation_system_history`：历史里残留的 system 消息，通常需要重点检查是否是旧数据污染。
- `audit_view.turn_provenance`：能匹配到的历史 user→assistant 回合来源，包括当时的 `provider_id`、`model`、`style`、`audit_id`。
- `audit_view.current_turn_provenance`：当前轮等待回复时的 provider、model、style 和用户消息 hash。
- `audit_view.current_prompt`：当前用户消息的审计标注。`content_hash` 对应去掉动态块后的真实玩家文本，`raw_content_hash` 对应完整发送文本。
- `audit_view.provider_payload_preview`：provider 专属 payload 形态的压缩预览，只保留 hash/preview/长度和结构计数，避免第三次保存完整 prompt；完整文本以 `request.*` 为准。

## 4.0 契约视图

4.0 记录会额外写入 `audit_view.contract_4_0`。它是 Narrator 请求落盘时的轻量契约快照，用来审计完整 4.0 链路，不需要从巨大 prompt 中反推。

- `audit_view.contract_4_0.pipeline_version`：通常为 `4.0`。
- `audit_view.contract_4_0.source`：该视图的来源；当前为 `runtime_event_extra_at_narrator_audit`。
- `audit_view.contract_4_0.turn_input`：本轮输入身份。
  - `session_hash`：会话 hash。
  - `session_key`：新账本路径使用的可读会话键。
  - `user_id`：玩家 id。
  - `player_message_hash` / `player_message_preview`：真实玩家输入的 hash 和短预览。
  - `style`：本轮当前风格。
  - `provider_id`：Narrator 请求 provider。
  - `preset_name`：当前世界观 preset。
- `audit_view.contract_4_0.intent_plan`：Intent Planner 的计划。
  - `turn_mode`：如 `dialogue`、`rest_commit`、`scene_transition`、`state_mutation`。
  - `confidence`：计划置信度。
  - `proposed_actions`：Planner 原始提出的工具动作。
  - `requires_confirmation` / `player_facing_confirmation`：需要确认时的提示。
  - `reason`：计划理由。
- `audit_view.contract_4_0.commit_decision`：Commit Gate 的确定性审批结果。
  - `decision`：`allow`、`deny`、`confirm` 或 `mixed`。
  - `safe_mode`：例如 `dialogue_only`。
  - `approved_actions`：允许执行的动作。
  - `denied_actions`：被拦截的动作及原因。
  - `reason`：汇总原因。
- `audit_view.contract_4_0.world_delta`：工具执行后的状态变化摘要。
  - `committed_tools`：成功提交的工具。
  - `failed_tools`：失败工具。
  - `state_changed`：是否有状态变更。
  - `entries`：每个工具的 `tool`、`args`、`success`、`error`、`is_follow_up`。
- `audit_view.contract_4_0.narrative_contract`：发给 Narrator 的契约。
  - `rendered_text`：最终注入文本。
  - `rendered_sections`：按中文小节解析出的项目。
  - `must_include`：必须体现。
  - `allowed_state_changes`：允许呈现的状态变更。
  - `must_not_include`：禁止事项。
- `audit_view.contract_4_0.verification_policy`：生成后验证策略。当前第一阶段通常是 `implemented=false`，表示需要离线审计 agent 人工检查 `response.text` 是否违反契约，并把可程序化规则沉淀为后续 Verifier。
- `audit_view.contract_4_0.status` / `error`：契约审计视图状态和错误。

4.0 审计时必须逐项比较：

1. `turn_input` 是否正确捕捉玩家真实意图，尤其是 `【】` 导演指令、睡前闲聊、局部动作、假设语气。
2. `intent_plan.proposed_actions` 是否必要，是否把对话误判为工具执行。
3. `commit_decision` 是否合理批准或拒绝，拒绝原因是否足以约束 Narrator。
4. `world_delta` 是否只包含真实成功的工具；失败工具不能被叙述为成功。
5. `narrative_contract.must_include` 是否覆盖工具事实、玩家真实意图和 Director 可见义务。
6. `narrative_contract.must_not_include` 是否覆盖未批准动作、失败工具、隐藏内心、系统注入复述、替玩家做决定。
7. `allowed_state_changes` 是否过宽或过窄。
8. `response.text` 是否遵守整个契约；若违反，判断责任在 Planner、Commit Gate、工具执行、Contract Builder、chat template 位置，还是 Narrator 遵从性。

如果 `audit_view.contract_4_0` 缺失但 `request.prompt` 中存在 `[RPG_TURN_CONTRACT]`，说明账本来自旧埋点或写入失败。审计时可临时从 `request.prompt` 反推，但应把缺失字段作为埋点问题。

## 用户导演指令

- 用户消息中用 `【】` 包裹的内容是导演指令或即时反馈，不是角色台词。
- 常见用途：要求引入某个角色、继续当前剧情、调整叙事方向、指出不满意的地方、直接指导 LLM 修正。
- 审计时优先检查模型是否正确理解并执行这些内容。若模型把 `【】` 当成角色对白、忽略其中的负反馈、机械复述、或用理工式解释代替叙事修正，应把它记为高价值证据。
- 修复位置通常是聊天模板中的用户消息解释规则、全局指导、风格指导、当前会话个人偏好，或 4.0 Planner/Contract 规则；不要改写历史消息本身。

## 轻量索引

- `data/plugin_data/astrbot_plugin_agentic_rpg/llm_audit_index/<session_key>.jsonl`：每行对应一个 Narrator 回合，保存该回合的 `audit_id`、preset、provider、model、style、当前 user hash、assistant hash 和短预览。这里的 `style` 是该回合当时的风格。
- 旧文件可能仍是 `<session_hash>.jsonl`；审计脚本会在找不到 `<session_key>` 时尝试兼容旧路径。
- 先读索引判断哪些 provider/style 参与过本会话，再按需打开完整 ledger。不要为了确认 provider 分布而批量读取巨大 JSON。

## 审计顺序建议

1. 先看 `llm_audit_index`，确认本会话最近一段时间的 provider/model/style 分布。
2. 打开目标 ledger 后，先看 `audit_view.snapshot`，把它当作“当前游玩片段快照”的摘要，而不是单轮标签。
3. 若存在 `audit_view.contract_4_0`，先完整审计 4.0 契约链，再评价 Narrator 文风。
4. 再看 `audit_view.context_messages` 和 `audit_view.system_prompt_parts`，区分模板注入与真实历史。
5. 最后看最终 `request.*` 字段，确认真实顺序和最终上下文。
6. 用 `response.text` 引用模型的具体坏表现，并把修复落到最低有效层。

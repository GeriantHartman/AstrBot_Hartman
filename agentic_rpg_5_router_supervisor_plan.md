# Agentic RPG 5.0 Router Supervisor 本地方案

## Summary

将 5.0 定义为 **Router-Centric Multi-Agent Turn Engine**。玩家只对接 Router；Router 拿到完整上下文，作为本轮唯一大脑，决定任务分工、工具调用、sub-agent 执行、结果合并、状态落档和最终玩家输出。

核心变化不是新增玩法，而是改变权力结构：Narrator、Director、Memory、Validator、Tool Executor 都是 Router 手下的执行单元；它们只能返回结果或提案，不能直接决定事实、落档或最终输出。

## Architecture

### Router / Supervisor

- 拿到完整上下文。
- 判断玩家意图。
- 生成本轮执行计划。
- 分配任务给 sub-agent。
- 决定工具调用。
- 合并所有结果。
- 审核叙事与状态一致性。
- 决定最终落档。
- 输出最终文本给玩家。

### Tool Executor

- 执行 Router 批准的工具。
- 返回结构化 `ToolEvent`。
- 不自行解释叙事意义。

### Narrator Agent

- 根据 Router 给出的 `NarrativeBrief` 写正文。
- 不调用工具。
- 不决定状态事实。
- 不自行落档。

### Director Agent

- 生成角色/NPC 本轮情绪、行动倾向、关系压力。
- 输出只作为 Router 的参考。
- 不直接成为 Narrator 的平行权威。

### Memory Agent

- 提出本轮是否应写入记忆、事件、关系变化。
- 只给落档建议。
- Router 最终决定是否提交。

### Validator Agent

- 检查正文是否违反工具结果、世界状态、角色 OOC、时间线、关系、外貌模式。
- 只返回检查结果。
- Router 决定修文、重写、放行或回滚。

## Complete Context Policy

Router 应拿到完整上下文，但要以分层结构交付，而不是混成一团自然语言。

Router 的完整上下文包括：

- 玩家本轮原始输入。
- 完整可用对话上下文。
- 当前世界状态。
- 当前场景状态。
- 玩家状态。
- 角色/NPC 状态。
- 关系、好感、记忆、事件记录。
- 最近工具调用与状态变更记录。
- 当前启用 skill / guidance / character card。
- 当前风格、文笔、OOC、禁忌约束。
- 可用工具目录与权限。
- 必要时包含原文历史证据。

原则：Router 可以看完整世界，sub-agent 只能看 Router 分配给它的最小必要上下文。

## Turn Flow

1. 玩家输入进入 Router。
2. Router 读取完整上下文，生成 `TurnPlan`。
3. Router 决定本轮需要哪些 sub-agent 和工具。
4. Tool Executor 执行工具，返回 `ToolEvent[]`。
5. Director / Memory / Validator 等按需执行局部任务，返回结构化结果。
6. Router 合并所有结果，生成 `NarrativeBrief`。
7. Narrator 根据 `NarrativeBrief` 写 `NarrativeDraft`。
8. Validator 检查草稿。
9. Router 根据检查结果决定：
   - 放行。
   - 要求 Narrator 重写。
   - 自行轻度修正。
   - 回滚或拒绝落档。
10. Router 提交 `TurnRecord`，更新状态，并将最终文本返回玩家。

## Key Interfaces

### CompleteContextBundle

- `raw_player_input`
- `conversation_context`
- `world_state`
- `scene_state`
- `player_state`
- `character_states`
- `relationship_state`
- `memory_state`
- `tool_history`
- `active_guidance`
- `available_tools`

### TurnPlan

- `player_intent`
- `turn_type`
- `subagent_tasks`
- `tool_actions`
- `narrative_goal`
- `state_commit_policy`
- `risk_flags`

### SubAgentTask

- `agent_type`
- `task_goal`
- `context_slice`
- `output_schema`
- `permission_scope`

### ToolEvent

- `tool_name`
- `args`
- `ok`
- `result`
- `state_delta`
- `error`

### NarrativeBrief

- `authorized_facts`
- `must_include`
- `must_not_claim`
- `character_constraints`
- `style_constraints`
- `open_slot`

### TurnRecord

- `input`
- `context_snapshot_ref`
- `plan`
- `subagent_results`
- `tool_events`
- `draft`
- `validation`
- `final_output`
- `committed_state_delta`

## Rules

- Router 是唯一事实授权者。
- Router 是唯一落档决策者。
- Sub-agent 不能直接改变状态。
- Narrator 不能决定工具结果。
- Director 不能直接覆盖 Router。
- Memory Agent 只能建议落档。
- Validator 只能提出问题，不能自行改写世界。
- 最终输出必须由 Router 授权。
- 如果正文和状态冲突，以状态和工具结果为准，重写正文，不为正文补档。

## Test Plan

- 长上下文 5-10 轮后，Router 仍能正确调用工具。
- Narrator 写错工具结果时，Router 能拦截。
- 工具失败时，正文不得写成成功。
- 角色 OOC、时间线漂移、关系漂移、外貌漂移能被 Validator 标出。
- Memory Agent 提出落档建议但 Router 可拒绝。
- Director 输出与状态冲突时，Router 不采用。
- 本地 9B/快速模型下验证 JSON 结构稳定性、延迟和重写率。

## Assumptions

- Router 拿完整上下文。
- Sub-agent 只拿任务所需上下文切片。
- 默认不允许 Narrator 写完后再调用变更状态的工具补档。
- 5.0 优先实现架构闭环，再评估新玩法。

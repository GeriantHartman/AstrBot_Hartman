# rpg_stats.json 字段说明

`rpg_stats.json` 是工具使用分析的主数据源，默认路径：

`data/plugin_data/astrbot_plugin_agentic_rpg/rpg_stats.json`

所有报告时间、`--since/--until` 输入时间、以及新写入的工具统计时间都按 UTC+8 解释。旧数据若来自切换前版本，只能作为弱证据。

## 顶层结构

- `sessions`：按 AstrBot `session_id` 保存每个会话的工具与 pipeline 统计。

## session 字段

- `last_updated`：该 session 最近一次写入时间。
- `preset`：会话使用的 preset 名称，可能为空。
- `tools`：工具级统计。
- `pipeline`：回合级聚合统计。
- `turns`：最近最多约 120 个回合的轻量快照。
- `director_stats`：Director 相关统计。

## tools 字段

`tools.<tool_name>` 可以是旧版整数，也可以是新版对象。新版对象字段：

- `count`：工具调用总次数。
- `success_count`：成功次数。
- `error_count`：错误次数。
- `total_latency_ms`：累计耗时。
- `avg_latency_ms`：平均耗时。
- `first_seen` / `last_seen`：首次和最近一次出现时间。
- `domain`：工具所属技能域。
- `last_error_at`：最近错误时间。
- `error_samples`：最近错误样本，最多保留少量文本。

分析建议：

- 错误率 = `error_count / count`。
- 平均延迟只代表工具内部执行耗时，不代表整轮 LLM 延迟。
- 旧版整数只能代表 count，不能推断成功率。
- 按时间窗口分析时，`tools` 只能按 `first_seen/last_seen` 粗筛，因此属于弱证据。

## pipeline 字段

- `turn_count`：记录的总回合数。
- `tool_turn_count`：发生工具调用链的回合数。
- `no_tool_turn_count`：无工具回合数。
- `pipeline_error_count`：pipeline 异常次数。
- `style_counts`：各 style 出现次数。
- `supervision_verdicts`：Supervisor 判定分布。
- `router_tool_counts`：Router/Planner 提出的工具次数。
- `tool_chain_counts`：旧字段，实际记录的是同一轮工具调用顺序；在 DeepSeek 并行 tool calls 下不一定代表因果链。`tool_batch_counts` 是新字段，用于表达“同一轮工具调用批次/组合”。
- `router.calls`：Router 调用次数。
- `router.avg_confidence`：平均置信度。
- `router.violates_role_count`：Router 输出叙事文本的次数。

分析建议：

- `router_tool_counts` 高而 `tools.<tool>.count` 低：可能被 Supervisor / Commit Gate 拦截，或计划后未执行。
- `tool_batch_counts` / 旧 `tool_chain_counts` 可发现同轮工具组合；在 DeepSeek 并行 tool calls 下，它表示批次，不等于因果链。
- `no_tool_turn_count` 高不一定坏；RP 对话场景中高无工具比例是正常的。

## turns 字段

每个 `turns[]` 是轻量回合快照：

- `ts`：记录时间。
- `player_msg`：玩家消息短预览。
- `has_director_instruction` / `director_instruction_count`：是否包含 `【】` 导演指令。
- `style` / `provider_id`：本轮风格和 provider。
- `tool_chain`：旧字段，实际执行工具顺序；不一定代表因果链。新字段 `tool_call_batch` / `tool_call_count` / `tool_call_mode` 用于表达同一轮工具调用批次。
- `router`：Router/Planner 摘要，包括 `tools`、`tool_count`、`confidence`、`violates_role`。
- `commit`：4.0 Commit Gate 摘要，包括 `decision`、`safe_mode`、`approved`、`denied`、`reason`。
- `supervision`：Supervisor 摘要。
- `execution`：执行摘要，包括 `entry_count`、`success_count`、`error_count`、`tools`、`error_tools`。
- `package`：Narrative Package 摘要。
- `director`：Director 摘要。
- `pipeline_error`：本轮 pipeline 错误。

分析建议：

- `turns[]` 是时间窗口分析的强证据，适合 4.0 后分析。
- `player_msg` 只是短预览，适合找候选，不适合做最终证据。需要精确证据时，再转去 Ledger 索引定位少量账本。
- `commit.denied` 是 4.0 工具误判/保护性拦截的重要信号。
- 如果 `router.tools` 有工具但 `execution.entry_count=0`，优先检查 Commit Gate 或 Supervisor。

## 报告与归档

- `tool_stats_summary.py --report auto`：生成 Markdown 报告到 `tool_analysis_reports/`，包含全量工具使用表、高延迟/高错误/低频视图、legacy 工具名表。
- `tool_stats_summary.py --since "YYYY-MM-DD HH:MM:SS" --report auto`：按时间窗口生成报告。
- `archive_stats.py --label <name>`：复制当前 `rpg_stats.json` 到 `tool_analysis_archives/`，不清空当前数据。
- `archive_stats.py --reset`：归档后清空当前统计。只有用户明确要求重新开始统计时才使用。

两次报告之间的对比建议：

- 可以强对比：平均耗时、错误率、失败原因、Commit Gate 拦截原因、Pipeline 异常。
- 弱对比：工具调用次数、领域调用次数。它们高度依赖用户玩法和剧情阶段，不应单独作为删工具依据。



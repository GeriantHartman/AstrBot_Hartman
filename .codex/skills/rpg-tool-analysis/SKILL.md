---
name: rpg-tool-analysis
description: 分析 AstrBot Agentic RPG 的工具使用数据、Router 工具计划、4.0 Commit Gate 拦截、工具失败率、延迟、低频/未使用工具和误调用候选。用于读取 rpg_stats.json、按时间窗口生成 Markdown 工具分析报告、归档旧统计基线、评估工具是否该优化/合并/删除，并输出中文分析结论或修复 diff。
---

# RPG 工具使用分析

## 工作流

把这个 skill 用于工具层分析，不要把它和 LLM 文风审计混在一起。默认先读取 `rpg_stats.json`，只有需要解释具体误调用时，才按索引定位少量 Ledger 证据。

1. 先运行 `scripts/tool_stats_summary.py --report auto` 汇总工具调用、失败率、延迟、领域分布、Router 计划和 4.0 Commit Gate 拦截，并生成 Markdown 报告。报告和所有时间字段一律按 UTC+8 解读。
2. 优先分析 `data/plugin_data/astrbot_plugin_agentic_rpg/rpg_stats.json`，不要读取 `llm_audit` 巨型 JSON 来做基础统计。
3. 如果用户指定 session，只分析该 session；否则先看全局聚合，再点名异常 session。
4. 如果目标是 4.0 后的分析，使用 `--since "YYYY-MM-DD HH:MM:SS"`。旧 `tools.count` 是累计值，时间窗口内的 turns 是强证据，工具耗时/成功率是弱证据。
5. 需要建立新基线时，先运行 `scripts/archive_stats.py --label before-4_0` 归档当前统计。除非用户明确要求，不要使用 `--reset` 清空统计。
6. 必须阅读“全量工具使用情况”表，不要只看高频/低频。工具分析是人工审核材料，中频工具也可能因为误调用而累积出看似正常的次数。
7. 对每个工具按四类判断：
   - 高频且低错：保留，考虑优化体验或减少上下文成本。
   - 高频且高错：优先修参数 schema、Router 规则、Commit Gate 或工具实现。
   - 低频但关键：保留，检查触发规则是否太保守。
   - 长期未使用或低价值：候选删除、合并或从 Router 可见工具集中下线。
8. 分析 Router 与执行差异：`router_tool_counts` 是计划/提出，`tools.*.count` 是实际执行累计。两者时间窗口不同的时候，不要直接相减下结论。
9. 4.0 下必须单独看 `turns[*].commit`：统计 denied 工具和原因，识别误拦截与必要拦截。
10. 结合 `turns[*]` 抽样误调用候选：玩家消息是闲聊/假设/局部动作，但 Router 提出高影响工具；或者工具成功了但 Narrator 不体现结果。
11. 输出中文结论，至少包含：保留工具、优化工具、低频观察、删除/合并候选、Router/Commit Gate 修复建议、报告文件路径。

## 报告与归档

常用命令：

```powershell
& "C:\Users\Hartman\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" .codex\skills\rpg-tool-analysis\scripts\tool_stats_summary.py --report auto
```

按 4.0 起始时间分析：

```powershell
& "C:\Users\Hartman\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" .codex\skills\rpg-tool-analysis\scripts\tool_stats_summary.py --since "2026-05-19 00:00:00" --report auto
```

归档当前统计作为基线：

```powershell
& "C:\Users\Hartman\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" .codex\skills\rpg-tool-analysis\scripts\archive_stats.py --label before-4_0
```

不要默认清空旧统计。更推荐归档 + 时间窗口。只有用户明确要求重新开始统计时，才使用 `archive_stats.py --reset`。玩家使用 `/rpg` 内建命令触发的行为不属于 LLM 工具行为，不应混入本报告。

## 与审计 skill 的分工

- 使用 `rpg-tool-analysis`：回答“哪些工具常用/不用、失败、慢、误调用、该不该删、Router 是否过度计划”。
- 使用 `rpg-ledger-audit`：回答“prompt、chat template、契约、Narrator 回复、DeepSeek 文风哪里有问题”。
- 两者可以串联：工具分析发现误调用候选后，再用审计 skill 打开少量对应 Ledger，验证当轮 prompt 和回复。

## 4.0 工具链检查点

逐项检查：

1. Router / Intent Planner 是否提出了合理工具。
2. Commit Gate 是否批准/拒绝合理，拒绝原因是否集中在少数规则。
3. Tool Executor 是否真实执行，失败率和错误样本是否指向参数问题或实现问题。
4. WorldDelta 是否只包含成功工具。
5. NarrativeContract 是否把成功/失败/拒绝工具正确传给 Narrator。
6. Narrator 是否自然体现成功工具，并避免叙述失败或被拒绝工具。

## 常用文件

- 工具统计：`data/plugin_data/astrbot_plugin_agentic_rpg/rpg_stats.json`
- 工具分析报告：`data/plugin_data/astrbot_plugin_agentic_rpg/tool_analysis_reports/`
- 工具统计归档：`data/plugin_data/astrbot_plugin_agentic_rpg/tool_analysis_archives/`
- 运行时工具域映射：`plugins/astrbot_plugin_agentic_RPG/handlers/_base.py`（只放当前真实工具）
- 分析用 legacy 工具名兼容：`.codex/skills/rpg-tool-analysis/scripts/tool_stats_summary.py`
- `/rpg stats` 展示逻辑：`plugins/astrbot_plugin_agentic_RPG/handlers/commands.py`
- 4.0 契约管线：`plugins/astrbot_plugin_agentic_RPG/handlers/contract_pipeline.py`
- 工具执行器：`plugins/astrbot_plugin_agentic_RPG/handlers/tool_executor.py`
- 审计账本索引：`data/plugin_data/astrbot_plugin_agentic_rpg/llm_audit_index/`

字段细节见 `references/stats_schema.md`。


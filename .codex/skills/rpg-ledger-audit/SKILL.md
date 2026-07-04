---
name: rpg-ledger-audit
description: 审计 AstrBot Agentic RPG 的 4.0 LLM 审计账本。用于分析各 provider/model 的 RP 文风与遵从问题、检查 prompt/contexts/response、逐项审计 4.0 TurnInput、Router 计划、工具 trace、WorldDelta、NarrativeContract、config_switches、injection_layers，并在不打断实时 RP 的情况下提出或应用 Router 规则、提示词、聊天模板、按 preset/provider 分层的全局指导、风格指导、会话偏好修复 diff；不用于新增 Reviewer 规则。
---

# RPG 审计账本离线审计

## 工作流

把这个 skill 当作离线审计智能体使用。不要向正在进行的 RP 会话发送消息，不要把 `/rpg` 命令作为审计流程的一部分。读取审计账本，检查渲染后的提示词来源、注入层、工具 trace 和 4.0 契约链，然后提出或应用普通文件 diff。

只维护 4.0 管线。旧 3.0 / Commit Gate / Reviewer rewrite 只作为历史账本背景，不再作为新增能力或修复方向。当前 RPG 主链路默认不再调用 Reviewer 改写；只有 generation ABTest 激活的 session 会旁路调用 Reviewer 产出对照审计。非确定性叙事判断不要建议写成代码级正则、关键词表、Verifier 或硬拦截；代码只补确定性审计字段和状态事实。

1. 先读 `data/plugin_data/astrbot_plugin_agentic_rpg/llm_audit_index/<session_key>.jsonl`，或用 `scripts/index_summary.py` 汇总最近回合的 preset、provider、model、style 和短预览。`<session_key>` 是由真实 `session_id` 转义得到的可读文件名；旧账本可能仍使用 `<session_hash>`，脚本会尽量兼容。
2. 在 `data/plugin_data/astrbot_plugin_agentic_rpg/llm_audit/<session_key>/*.json` 下定位少量目标审计账本。
3. 可用 `scripts/audit_summary.py` 汇总最近样本，但不要为了 provider 分布批量读取完整 JSON。
4. 只检查最少必要的完整账本文件。优先选择目标风格、明显坏回复、或最近聊天模板 hash 对应的记录。
5. 必须关注用户消息中用 `【】` 包裹的内容。它们是用户定义的导演指令或即时反馈，不是角色台词；常用于要求引入角色、继续剧情、纠正不满意的叙述、直接指导 Narrator。审计时把这些片段视为高价值用户意图证据。
6. 先确认该记录是否有 `audit_view.contract_4_0.pipeline_version == "4.0"`。如果没有，把它标记为 legacy/埋点缺失，不再为旧管线设计修复。
7. 如果是 4.0，必须审计完整契约链，不要只审计 Narrator 文风：
   - `turn_input`：玩家真实输入、style、provider 是否正确；`【】` 是否被视为导演指令/反馈，而不是角色台词。
   - `config_switches`：关键开关是否解释了本轮流程分支，例如 4.0、Director、guidance、ChatTemplate、fallback、audit。
   - `router_plan_audit` / `intent_plan`：Router prompt、可用工具、provider chain、max_steps、实际 tool trace 是否足以履约玩家动作。
   - `world_delta`：成功工具、失败工具、参数、结果、状态变更是否与工具结果一致；失败工具是否被后续叙事写成成功。
   - `injection_layers`：ChatTemplate slot、guidance 路径、`zone_state`/world_info、`npc_package`/角色卡、Director、story_hooks、tool_results、contract 是否参与本轮。
   - `narrative_contract`：`must_include`、`allowed_state_changes`、`must_not_include` 是否完整、短、中文、靠近生成位置，并且足以约束 Narrator。
   - `verification_policy`：当前只说明是否存在生成后强校验；如果未实现，不要误判为已有代码级拦截。
   - `status/error`：若契约构建失败或缺字段，先审计管线和 ledger 埋点，而不是直接改风格提示。
8. 判断问题属于 Router 规则、工具/状态、注入层缺失、4.0 契约层、ChatTemplate slot、风格/guidance、会话个人偏好、运行时数据污染，还是审计本身缺证据。不要用顶层字段推断整段历史；以 `audit_view.snapshot`、`turn_provenance`、`contract_4_0` 和 `injection_layers` 为准。
9. 修复能解决问题的最低层：
   - 反复出现且确实跨 preset/provider 通用的模型根习惯：修改 `plugins/astrbot_plugin_agentic_RPG/skills/rpg-style-core/SKILL.md` 或 `guidance/global.md`。
   - 某个 preset + provider 组合的模型根习惯：修改 `guidance/scoped/<preset>/<provider>/global.md`。
   - 某个风格专属问题：修改 `plugins/.../skills/rpg-style-<style>/SKILL.md`、`guidance/styles/<style>.md`，或更推荐的 `guidance/scoped/<preset>/<provider>/styles/<style>.md`。
   - 仅当前用户/当前会话口味：修改 `guidance/scoped/<preset>/<provider>/sessions/<session_key>.md`；旧式 `guidance/sessions/<session_key>.md` 只用于真正不区分 preset/provider 的个人偏好。
   - Router 漏调/误调：修改 `prompt/intent_router_rules.md`、`ROUTER_POLICY_APPEND`、工具 schema/docstring 或工具错误 envelope。
   - 契约表达不够硬：修改 `build_narrative_contract_text` 或聊天模板中的 `{narrative_contract}` 位置。
   - Director 输出质量（静态外观模板、内心独白泄露、字段空值率异常）：修改 `plugins/astrbot_plugin_agentic_RPG/prompts.yaml` 中的 `director_system` key。
   - 槽位位置或指令顺序问题：修改 `data/plugin_data/astrbot_plugin_agentic_rpg/chat_template.json`；只有用户明确要求时才改 bundled baseline。
   - 审计缺证据：修改 `LLMAuditLedger`、`_build_narrative_audit_view`、`_build_contract_audit_view` 或 Router audit extras。
10. 展示 diff，并说明每处改动对应哪条账本证据。

## RPG 专属审计口径

- 小爱是幕后 GM、系统精灵和小说书写者，不是场内角色。小爱不在前台出现通常是正确设计；`<xiaoai_core>`、`<xiaoai_core_cot>` 等标签是系统/审计可见内容，除非出现在玩家可见 `response.text` 中，否则不要判为泄露。
- 玩家常用 `“”` 表示对白，不要求强制改成 `「」`。中文全角双引号与英文半角双引号都可接受。
   - RPG 反编造以事实来源为边界。来自工具结果、DB/状态机、world_info、character_card、npc_packet、Director、active story_hooks、已落档 world canon 或 narrative contract 的玩家未知事实不是幻觉；未落档、未注入、未由工具生成的具体物品/NPC/地点/设定才是问题。
   - `story_hooks` 是轻量待探索事件链，不是永久 canon。active hook 可以约束 Narrator，inactive hook 只应作为 Router 可恢复索引；审计时不要要求用 `pin_world_canon` 记录普通伏笔。
- RPG 代行边界不同于单人角色扮演。允许 Narrator 扩写玩家已下达命令的低层执行过程和可见后果；禁止替玩家做新决定、说新台词、承诺、改变重大关系结论或消耗关键资源。
- 探索、日常、调查类场景应自然留下 2-4 个行动入口；不要求每轮机械菜单化，但连续封闭结尾是节奏问题。
- Reviewer/rewrite 已从 RPG 主链路废弃。A/B 记录可作为问题证据，但不要把修复落到 reviewer prompt、正则或宪法规则；默认回复质量应由 Router、工具、contract、ChatTemplate、style/guidance 注入层承担。

## 4.0 契约审计清单

优先读取 `audit_view.contract_4_0`。如果该字段不存在，但最终 prompt 有 `[RPG_TURN_CONTRACT]`，说明账本来自旧版本或埋点缺失：可以临时从 `request.prompt` / `assembly_trace.slots` 反推，但应把“缺少 contract_4_0 审计视图”列为埋点问题。

逐项回答：

1. 玩家输入是否被正确抽象为 `turn_input`？尤其检查 `【】` 反馈、睡前闲聊、局部动作、假设语气。
2. `config_switches` 是否说明了本轮实际分支：4.0、Director、guidance、ChatTemplate、fallback、audit 是否启用。
3. `router_plan_audit` / `intent_plan` 是否显示 Router 已看到正确玩家消息、可用工具、max_steps 和 provider chain；实际 `executed_tool_names` 是否覆盖玩家的动词+宾语。
4. `world_delta.committed_tools` / `failed_tools` / `entries` 是否与工具参数和结果一致？Narrator 是否只叙述已提交事实。
5. `injection_layers.source_participation` 是否能证明 world_info/zone_state、角色卡/npc_packet、Director、story_hooks、tool_results、contract 参与本轮；如果看不到，先列为审计缺证据。
6. `narrative_contract.must_include` 是否包含本轮必须体现的工具事实、导演可见反应、玩家真实意图。
7. `narrative_contract.must_not_include` 是否覆盖失败工具、隐藏内心、系统注入复述、替玩家做决定。
8. `allowed_state_changes` 是否过宽或过窄？是否允许了玩家未承诺的时间推进、地点切换、交易、战斗、关系变化。
8. **Director `observable_to_player` 字段审计**：是否包含静态外观/姿势/穿着/随身道具的固定模板（如”白色过膝袜并拢，粉色侧马尾垂在肩侧”）？这些描述是否在连续多轮的 contract 中出现？→ 如果是，Director 提示词未约束字段范围，需修改 `prompts.yaml` `director_system`。注意区分”本轮新增动作”（如”递了茶””歪头看了某人”）和”每轮都一样的固定特征模板”——前者是 Director 的正确输出，后者是 bug。
9. **跨轮描述重复检测**：提取最近 3-5 轮 `response.text` 中同一 NPC 的描述性短语（≥5 个连续汉字）。如果同一短语出现 ≥2 次，判断来源——来自 contract `must_include`（Director 注入）还是来自 Narrator 上下文回声（contract 无该短语但 Narrator 仍写了）。前者修 Director，后者修 global.md 反重复规则。
10. `verification_policy` 是否只是状态记录。不要把非确定性写作问题建议成代码级 Verifier；只把确定性缺字段、缺 trace、缺落账列为代码埋点问题。
11. 最终 `response.text` 是否遵守契约？若不遵守，判断是契约太弱、位置太远、模板冲突、还是模型风格习惯。

## Provider 重复描述诊断模式（已验证的审计模式）

**这是多个 provider 都可能出现的 4.0 文风问题：NPC 的固定外观描述在连续多轮中被反复复制，让角色变成静止立牌。审计结论必须记录 provider、model、preset，不能默认归因于 DeepSeek。**

### 症状识别

读取最近 3-5 轮的 `response.text`，对每个 NPC 做短语匹配：
- ≥5 个连续汉字，在 ≥2 轮中出现 → 标记为重复
- 典型的重复模板："跪坐在床尾，白色过膝袜并拢，粉色侧马尾垂在肩侧"、"蓝色眼眸在晨光里亮晶晶"、"像一只...小猫咪"

### 双源诊断流程

当发现重复描述时，不要直接归咎 Narrator。按以下流程逐层定位：

1. **检查 `contract_4_0.narrative_contract.must_include`**：该轮的合同是否包含这个重复短语？
   - **是** → **Director 源污染**。Director 的 `observable_to_player` 包含了静态外观模板，被 `build_narrative_contract_text` 原样注入合同（`contract_pipeline.py:396-398`）。修复方向：`prompts.yaml` `director_system` 和/或 Director 调用方的 `observable_to_player` 字段过滤。
   - **否** → **Narrator 上下文回声**。Narrator 从对话历史中看到了前几轮的这个短语并自主复用。修复方向：`guidance/scoped/<preset>/<provider>/global.md` 添加该模型/世界组合的反重复规则 + `guidance/scoped/<preset>/<provider>/sessions/<session_key>.md` 添加会话级去重约束。

2. **如果合同中有重复短语**（Director 源），进一步检查连续多轮的 contract：
   - 哪些轮的合同中有？哪些没有？→ 判断 Director 是间歇性注入还是每轮注入
   - 没有合同的轮，Narrator 是否仍然写了？→ 判断是否存在"合同回声"（上一轮合同污染了下一轮 Narrator 的上下文）
   - 匹配 Director 输出日志（`[RPG Director] ← LLM raw for NPC=...`）中的 `observable_to_player` 字段与合同中的文字 → 确认是 Director 生成时的原始输出还是合同构建器的二次加工

3. **修复优先级**：
   - Director 源污染 → 先修 `prompts.yaml` `director_system`（字段约束 + 原则补充），再按 provider/preset 补 `guidance/scoped/<preset>/<provider>/global.md`（兜底反重复）
   - Narrator 回声 → 先修 `guidance/scoped/<preset>/<provider>/global.md`（反重复规则），再补 session 级紧急去重
   - 两者同时存在 → Director 优先修（切断源头），Narrator 兜底修（防止回声复发）

### 合同注入链路（审计关键路径）

```
Director LLM
  → observable_to_player: "小莉跪坐在床尾，白色过膝袜并拢..."
  → 合同构建器 (build_narrative_contract_text L396-398)
    → contract.must_include.append("让 艾莉西娅 的可见反应体现：...")
      → 聊天模板 → system_prompt/contexts
        → Narrator LLM 看到合同 → 忠实翻译进 response.text
```

审计时必须在这条链路的每个节点检查：Director 原始输出、合同渲染文本、聊天模板注入位置、Narrator 最终输出。哪个节点把静态外观当作"可见反应"注入了，就修哪个节点。

### 修复文件映射

| 根因类型 | 文件 | 修改内容 |
|---------|------|---------|
| Director 生成静态外观 | `plugins/astrbot_plugin_agentic_RPG/prompts.yaml` → `director_system` key | 约束 `observable_to_player` 字段说明 + 添加原则禁止静态模板 |
| 合同构建证据不足 | `plugins/astrbot_plugin_agentic_RPG/handlers/contract_pipeline.py`、`handlers/hooks.py` | 只补确定性审计字段或 contract 来源记录；不要加关键词过滤。 |
| Narrator 上下文回声 | `data/plugin_data/astrbot_plugin_agentic_rpg/guidance/scoped/<preset>/<provider>/global.md` | "禁止跨轮复制角色外观模板"规则 |
| 会话紧急去重 | `data/plugin_data/astrbot_plugin_agentic_rpg/guidance/scoped/<preset>/<provider>/sessions/<session_key>.md` | 列出禁止使用的具体短语 + 替换方案 |

## 边界

会话指导只写个人偏好和当前会话口味，不写通用模型规则。全局指导可以写跨会话的 provider/model 文风修正，但默认应落在 `guidance/scoped/<preset>/<provider>/global.md`，避免把新爱莉都、星穹铁道、原神等 preset 的例子互相污染。聊天模板负责决定注入位置，不要在 Python 里硬编码覆盖层文本。

不要重写对话历史。不要让 Narrator 自审。文风问题不要改状态机和游戏机制。

不要把 `【】` 内容当作角色内发言来批评文风；它是玩家下场给出的导演指令、剧情控制或负反馈。若模型无视、误解、复述或角色化这些内容，应优先检查 prompt/chat_template 是否正确要求模型服从导演层反馈。

不要把所有问题都归咎于 Narrator。4.0 下必须先沿着 Router → Tool Trace → ExecutionResult → NarrativePackage → Director → Contract Builder → ChatTemplate → Narrator 的链路定位责任点。只有当前面事实链和注入链正确而回复仍违规时，才把问题归为 Narrator 遵从性或文风问题。

## 常用文件

- 审计账本目录：`data/plugin_data/astrbot_plugin_agentic_rpg/llm_audit/`
- 审计轻量索引：`data/plugin_data/astrbot_plugin_agentic_rpg/llm_audit_index/`
- 叙事指导目录：`data/plugin_data/astrbot_plugin_agentic_rpg/guidance/`
- 用户可编辑聊天模板：`data/plugin_data/astrbot_plugin_agentic_rpg/chat_template.json`
- 插件内置聊天模板基线：`plugins/astrbot_plugin_agentic_RPG/presets/chat_template.json`
- 风格 skill：`plugins/astrbot_plugin_agentic_RPG/skills/rpg-style-*/SKILL.md`
- 4.0 契约管线：`plugins/astrbot_plugin_agentic_RPG/handlers/contract_pipeline.py`
- 4.0 入口和 Ledger 写入：`plugins/astrbot_plugin_agentic_RPG/handlers/hooks.py`
- 工具执行器：`plugins/astrbot_plugin_agentic_RPG/handlers/tool_executor.py`
- Director 系统提示词：`plugins/astrbot_plugin_agentic_RPG/prompts.yaml` → `director_system` key
- 全局文风修正：`data/plugin_data/astrbot_plugin_agentic_rpg/guidance/global.md`（仅真正跨 preset/provider 通用）
- 按 preset/provider 分层修正：`data/plugin_data/astrbot_plugin_agentic_rpg/guidance/scoped/<preset>/<provider>/global.md`
- 风格专属指导：`data/plugin_data/astrbot_plugin_agentic_rpg/guidance/styles/<style>.md`
- 按 preset/provider 的风格指导：`data/plugin_data/astrbot_plugin_agentic_rpg/guidance/scoped/<preset>/<provider>/styles/<style>.md`
- 会话口味：`data/plugin_data/astrbot_plugin_agentic_rpg/guidance/scoped/<preset>/<provider>/sessions/<session_key>.md`

需要字段细节时读取 `references/ledger_schema.md`。

审计旧 `narrative_reviewer` 或 AB test 时，只把它们当作历史证据来源。后续不再向 reviewer 增加规则，也不把 reviewer 方法论迁移成新的代码级正则、关键词匹配或硬拦截。

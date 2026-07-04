# 叙事审核优化两阶段实施计划

> **目标**: 通过先优化后整合的路径，让 AstrBot 的 RP 回复减少 AI 味，符合中文小说习惯，保持角色声线稳定，最终以更少的 LLM 调用达到更好的回复质量。

---

## 当前状态分析

### 4 个结构性问题

通过阅读 `plugins/astrbot_plugin_narrative_reviewer/reviewer_core.py`（~1700 行），识别出以下核心问题：

1. **规则三重冗余**：同一套"米哈游式 RP"写作规则同时出现在三处，彼此不完全对齐：
   - reviewer_core 中约 **20 组硬编码正则**（`_MIHOYO_EXPLANATORY_PATTERNS` 等，约 80 条具体模式）
   - reviewer_core 中约 **125 行 system prompt**（`_build_system_prompt()`，lines 795-920）
   - style skill 中约 **225 行 SKILL.md**（single-roleplay-core + single-style-daily）

2. **二次调用的性能成本**：`review()` 流程中，先调一次审核 LLM（lines 389-396），若确定性质量门失败再调一次 `_call_repair_provider()`（lines 443-451）。加上 provider fallback 链，单轮可能触发 **2-4 次额外 API 调用**。

3. **硬编码正则过度拟合特定素材**：`_MIHOYO_EXPLANATORY_PATTERNS` 中大量针对特定游戏台词的正则（"软得连自己都有些意外""这个动作比任何语言都诚实"），对其他角色卡/场景泛化性差，且容易误伤正常表达。

4. **审计机制只有落盘没有聚合**：`write_audit()` 只把结果写成散 JSON，无法回答"当前角色卡在哪些问题上反复失败"。缺少按问题类型/模式/风格的聚合分析能力。

### 相关文件总览

| 文件 | 当前功能 | 改动方向 |
|------|---------|---------|
| `plugins/astrbot_plugin_narrative_reviewer/reviewer_core.py` | 审核核心，20 组正则 + 冗长 prompt | 正则精简、分层门控、issue 分类、prompt 瘦身 |
| `plugins/astrbot_plugin_narrative_reviewer/main.py` | 插件入口，on_llm_response 钩子 | snapshot 增加 persona / style skill 信息 |
| `plugins/astrbot_plugin_narrative_reviewer/_conf_schema.json` | 配置 schema | 新增 `narrative_review_run_mode`（rewrite_and_audit / audit_only / disabled） |
| `plugins/astrbot_plugin_style_skills/skills/single-roleplay-core/SKILL.md` | 非 RPG 单角色全局写作规则 | 新增"禁写清单（反模式）"章节 |
| `plugins/astrbot_plugin_style_skills/skills/single-style-daily/SKILL.md` | 日常风格规则 | 新增"日常场景快速自查清单" |
| `plugins/astrbot_plugin_agentic_RPG/prompts.yaml` | RPG Director/Narrator 系统提示词 | Narrator 提示词新增"叙事质量锚点" |
| `plugins/astrbot_plugin_agentic_RPG/handlers/hooks.py` | `build_narrative_contract_text()` | 每轮 contract 追加"叙事质量合约" |
| `plugins/astrbot_plugin_narrative_reviewer/reference_samples.yaml` | **新建** | bad/good 对照参照文本，用作 few-shot 锚点 |

---

## 阶段 1：独立 Reviewer 优化（短期收效）

**目标**: 在不改变"生成后审核"架构的前提下，提升审核质量、降低 LLM 调用成本、建立问题发现闭环。

### 子任务 1.1：硬编码规则精简与重构

**涉及文件**: `plugins/astrbot_plugin_narrative_reviewer/reviewer_core.py`

**改动方向**:

| 模式组 | 当前状态 | 计划改动 |
|--------|---------|---------|
| `_MIHOYO_EXPLANATORY_PATTERNS`（lines 56-74） | 12 条解释腔正则 | 保留前 5 条通用二分模式（"不是A而是B""并非A而是B""不在于A而在于B""不是因为A而是因为B""不是不喜欢而是不习惯"），删除过度拟合特定游戏台词的 7 条（"软得连自己都有些意外""这个动作比任何语言都诚实"等） |
| `_MIHOYO_RECAP_PATTERNS`（lines 75-85） | 复述 + 重复触发模式 | 保留"你问/你说/面对你"起手检测；保留末尾重复关键词段检测 |
| `_MIHOYO_SETTING_BROADCAST_PATTERNS`（lines 86-92） | 设定广播模式 | 保留 4 条（"关于那位女士的有趣记录""刚整理好的那份特别档案"等） |
| `_MIHOYO_STIFF_VOICE_PATTERNS` + `_MIHOYO_GROUP_STRONGNESS_PATTERNS` | 8 条强势腔正则 | **合并为一个 `_MIHOYO_OVERSTRONG_PATTERNS` 分组**，保留 6 条最通用的 |
| `_MIHOYO_OVERSTRONG_ROMANCE_PATTERNS`（lines 106-116） | 9 条强恋爱命令腔 | **保留全部**——这是最高价值模式（"我允许你靠过来""吃完了再让你靠""不许晃""擦汗""乖乖听医嘱"等确实是高频硬伤） |
| `_MIHOYO_SELF_OBSERVATION_PATTERNS`（lines 117-128） | 自我观察镜头 | 保留但减少正则条数，改为更通用的短语匹配（"嘴角没收住""耳根发热""下意识"等 5 条核心模式） |
| `_MIHOYO_DRY_DIALOGUE_PATTERNS`（lines 129-139） | 8 条特定对话/场景 | **全部降级为 soft issue 而非 hard issue**——这些句子本身不越界，只是不够好 |
| `_MIHOYO_RECURSIVE_PROMPT_HANDOFF_PATTERNS`（lines 140-147） | 重复触发/责任错位 | 保留核心 3 条（"再问我一遍""到门口再问""我会再问一遍"） |
| `_MIHOYO_MEDIUM_ROLE_LEAKAGE_PATTERNS`（lines 148-157） | 角色泄漏/写作意图 | 保留 5 条通用模式（"好，那我该这样做""让他知道我不是"等核心模式） |
| `_MIHOYO_DIALOGUE_SUBTITLE_PATTERNS`（lines 158-166） | 字幕式旁白 | 保留核心 4 条（"语气里藏着""每个字都""像怕这句话被""这句话落/藏"） |
| `_MIHOYO_MEDIA_TARGET_MISPLACEMENT_PATTERNS`（lines 167-172） | 媒介目标错置 | 保留全部 3 条 |
| `_MIHOYO_TURN_PRESSURE_PATTERNS`（lines 173-181） | 话轮压力 | 简化——保留"好不好/好吗/可以吗"句尾检测 + 门把/便签/菜单等 3 个关键互动物件检测 |
| `_MIHOYO_GENERIC_CUTE_SUFFIX_PATTERNS`（lines 182-187） | 语气助词补丁 | 保留，但标记为 soft issue（不触发 quality gate 阻断） |
| `_MIHOYO_CLOSED_ENDING_PATTERNS`（lines 188-193） | 封闭结尾 | 保留核心 3 条 |
| `_MIHOYO_DECORATIVE_MOTIFS`（lines 194+） | 装饰性 motif | 大幅精简，保留"嘴角""耳根"等 2-3 个最高频标签 |

**净结果**: 正则条数从约 20 组/近 80 条具体模式，精简到约 10 组/35-40 条通用模式。减少约 50% 的硬编码。

**验收标准**: 
- 对同一组 10-15 条真实对话回复，运行 baseline vs 优化后版本
- 确认减少的正则不会导致"明显的硬伤被放行"（人工检查）
- 过拟合的特定游戏台词不再误伤正常表达

---

### 子任务 1.2：分层门控 —— hard/soft issue 分离

**涉及文件**: `plugins/astrbot_plugin_narrative_reviewer/reviewer_core.py`

**改动方向**:

```
当前流程                      目标流程
───────────────────────       ───────────────────────
always mode → 直接调 LLM      always mode → 本地轻检测 + LLM
selective → 2 soft 才调       selective → 1 soft or any hard 就调
hard_only → 只在 hard 调      hard_only → 保持不变
quality_gate 失败 → repair    quality_gate 失败 → 只对 hard issues repair
```

具体改动:
- 在 `review()` 中把质量门分层：**hard_issues**（二分解释壳/角色泄漏/重复触发/媒介目标错置/字幕式旁白/封闭结尾/责任错位/过度强势命令腔）直接阻断并可能触发 repair；**soft_issues**（语气助词补丁/自我观察镜头/装饰性 motif/干冷事务句/话轮压力不足）只记录不阻断，不触发 repair。
- 修复判断逻辑（line 484 `len(repair_issues) < len(deterministic_issues)`）改为"**硬伤数减少**"即可接受，避免 soft issue 残留导致反复 repair 造成超时。
- 把 `_MIHOYO_DRY_DIALOGUE_PATTERNS`（特定对话句式，如"排队的人比以前更多"）整体从 hard 移到 soft，因为这些只是不够生活，不是错误。

**验收标准**:
- 对同一组测试输入（10-15 条真实对话回复），观察 LLM 调用次数（审核 + repair）下降 >= 30%
- `applied=true` 的比例基本不变或略有下降
- 人工对比：hard issue（真的读起来别扭的解释腔/命令腔）被改的命中率上升，soft issue（本来就过得去的表达）被保留

---

### 子任务 1.3：System Prompt 瘦身 + 规则去重

**涉及文件**: `plugins/astrbot_plugin_narrative_reviewer/reviewer_core.py` 的 `_build_system_prompt()`

**改动方向**:

当前 prompt 约 125 行，分为三段：顶部"重点处理"列表（20 条 bullet）、中部"硬规则"（12 条长段，每段 5-15 行）、底部"补充 RPG 质量规则"（15 条，含长度规则/玩家主权/节奏规则等与叙事无关的条目）。

瘦身策略:
1. **删除与 style skill 完全重复的段落**："恋爱感要落在行为里""媒介分工错位""字幕式旁白"等规则在 single-roleplay-core SKILL.md 已经有更详细的版本，prompt 里只保留一句引用提示即可。
2. **"重点处理"从 20 条合并到 8 条核心硬伤**：二分解释壳/复述起手/字幕式旁白/媒介目标错置/责任错位/强命令腔/封闭结尾/自我观察标签。
3. **"补充 RPG 质量规则"中移走非 reviewer 的规则**：长度/节奏/玩家主权由 RPG 插件自身的 prompts.yaml 控制，prompt 中只保留"角色声线规则"和"解释壳规则"。
4. **JSON 格式说明精简**：当前多处重复"输出 JSON"，合并为一次清晰说明。

**验收标准**:
- system prompt token 数下降 >= 40%
- 改写质量不明显下降（人工盲测 A/B 各 20 条，"更好或等价"比例 >= 75%）

---

### 子任务 1.4：审计机制重构 —— 从"落盘"到"聚合分析"

**涉及文件**: `plugins/astrbot_plugin_narrative_reviewer/reviewer_core.py`（`write_audit()`）

**改动方向**:

**a) Issue 分类字段**: 在 `ReviewResult` 中，除了自由文本 `issues`，新增结构化分类信息。新增 `_classify_issue_category(issue_text: str) -> str`（15-20 行的本地映射表，**不需要额外 LLM 调用**）。

分类表:

| category | 含义 | 对应模式 |
|----------|------|---------|
| `explanatory_shell` | 二分解释壳/解释性心理旁白 | `_MIHOYO_EXPLANATORY_PATTERNS` |
| `recap_opener` | 复述玩家起手 | `_MIHOYO_RECAP_PATTERNS` |
| `subtitle_narration` | 字幕式旁白 | `_MIHOYO_DIALOGUE_SUBTITLE_PATTERNS` |
| `medium_misplacement` | 媒介目标错置/角色泄漏 | `_MIHOYO_MEDIUM_ROLE_LEAKAGE_PATTERNS` + `_MIHOYO_MEDIA_TARGET_MISPLACEMENT_PATTERNS` |
| `responsibility_shift` | 责任错位/重复触发 | `_MIHOYO_RECURSIVE_PROMPT_HANDOFF_PATTERNS` |
| `overstrong_command` | 过度强势命令腔/医嘱腔 | `_MIHOYO_OVERSTRONG_ROMANCE_PATTERNS` |
| `closed_ending` | 封闭结尾 | `_MIHOYO_CLOSED_ENDING_PATTERNS` |
| `self_observe_tag` | 自我观察镜头/害羞标签 | `_MIHOYO_SELF_OBSERVATION_PATTERNS` |
| `decorative_motif` | 装饰性微动作（嘴角/耳根） | `_MIHOYO_DECORATIVE_MOTIFS` |
| `stiff_voice` | 生硬事务腔/干冷短句 | `_MIHOYO_STIFF_VOICE_PATTERNS` + `_MIHOYO_DRY_DIALOGUE_PATTERNS` |
| `cute_suffix_patch` | 语气助词补丁 | `_MIHOYO_GENERIC_CUTE_SUFFIX_PATTERNS` |
| `turn_pressure_low` | 话轮压力不足 | `_MIHOYO_TURN_PRESSURE_PATTERNS` |
| `llm_reported` | LLM 审核报告的自由问题（无法本地分类） | —— |

**b) 审计文档扩展字段**: `write_audit()` 输出的 JSON 中新增:
```yaml
issue_categories:          # 按类别聚合的出现次数
  explanatory_shell: 3
  overstrong_command: 1
  ...
severity_balance:          # hard / soft 命中比例
  hard: 2
  soft: 5
preflight_passed: false    # selective/hard_only 模式是否本地放行
latency_ms: 2340           # review() 内部计时
original_text_hash: "...": # 原文 hash（去重分析用）
```

**c) 离线聚合分析脚本/命令**（在 `main.py` 新增 `/reviewer_audit stats` 或作为独立脚本）:
- 读取 `data/plugin_data/astrbot_plugin_narrative_reviewer/reviews/<session_key>/*.json`
- 输出:
  - Top 5 高频 issue category（全局 / 按 style 分）
  - hard issue 命中率的趋势（用于评估 style skill 改动后的改善）
  - 每 provider 平均 latency
  - 被 quality_gate 阻断的文本样例（按类别各取 5 条，供人工审阅）
  - 连续 2 周同一 category 上升的预警

**验收标准**:
- 运行一周后，聚合脚本能给出"当前 Top 3 高频硬伤"报告
- 人工检查其中样例，确认分类准确度 >= 85%
- 审计文件格式合法，可被聚合脚本正确解析

---

### 子任务 1.5：参照文本（Good RP Samples）积累

**涉及文件**: `plugins/astrbot_plugin_narrative_reviewer/reference_samples.yaml`（**新建**）

**改动方向**:

新建参照文本库，结构:
```yaml
samples:
  - id: daily_soft_001
    mode: single_role
    style: daily
    category: overstrong_command
    summary: "柔和角色接到玩家邀约，嘴硬但可爱，最后给出具体时间"
    bad_example: |
      （心里想，用户终于约我了。不是我不想去，只是怕你太忙……
      菜单我来定，不许只喝汤不吃面。）好。走吧。
    good_example: |
      （指尖轻轻敲了敲菜单边缘，抬眼扫过你。）
      你倒是挺会精打细算的——把监督吃饭也算进约会里？
      那就七点。我定店。……不许只喝汤不吃面，我会看着的哦。

  - id: daily_explanatory_002
    mode: single_role
    style: daily
    category: explanatory_shell
    ...
```

收集范围:
- 每个硬伤 category 至少 1-2 组 bad/good 对照
- 覆盖角色卡风格：柔和犹豫型、嘴硬关心型、强势命令型、技术对抗型
- 共约 8-12 条

在 `_build_user_prompt()` 中，根据本地 preflight 命中的 category 动态选取 1-2 条 good_example 作为 few-shot 提示（说明"遇到同类问题时参考改写方式，不要照搬措辞"）。

**参照文本的来源**：主要来自以下方向（不搬运版权文本，编写原创 RP 风格样本）：
- 中文流行网络小说的对话片段（改写为 RP 格式）
- 轻小说中典型的角色对话方式（用于 soft/日常场景参考）
- 基于已有好回复的人工改写（形成 gold standard）
- 存放在插件目录内，而非 data/ 目录，便于版本控制和团队协作

**验收标准**:
- 参照文本文件存在，yaml 格式合法，每个 category 至少有 1 条 bad/good 对照
- 人工审阅：good_example 本身不应被 reviewer 再次命中同类 hard issue（若命中则 sample 不合格，需重写）
- 有 few-shot 注入后，人工抽样 20 条改写，确认改写后的文本更贴近 good_example 的表达方式而非 reviewer 自己的"整理腔"

---

### 子任务 1.6：上下文结构微调 —— 让 Reviewer 看到角色卡

**涉及文件**: `plugins/astrbot_plugin_narrative_reviewer/main.py` 的 `on_llm_request` 钩子

**改动方向**:

当前 `snapshot`（lines 96-108）只保存:
- prompt / system_prompt_hash
- contexts_count / style / layers

**缺少的关键信息**:
- `persona_preview`: 当前 persona 角色卡的开头 400 字（角色声线/称呼/基调的锚点信息，供审核模型知道"这个角色本应怎么说话"）
- `active_style_skills`: 已注入 style skills 的名称列表（确认当前对话场景是 daily / nsfw / 其他）
- `current_turn_pressure_hint`: 当前已有的开放位类型（问题/条件/物件），防止 reviewer 把已经有抓手的句子改成另一种

在 `_build_user_prompt()` 中，把 `persona_preview` 展示给审核 LLM。目标是解决"把柔和角色硬改成强势命令腔"的典型错误——当前 system prompt 第 6 条已经写了这条规则，但因为审核模型完全看不到角色卡，执行率很低。

**验收标准**:
- 人工抽样 20 条"审核改写后角色声线是否稳定"测试，"声线匹配角色卡"比例从 baseline 提升 >= 20%
- 不注入 persona 时，审核模型仍能正常工作（fallback 到默认的"偏保守、不擅自改声线"策略）

---

### 子任务 1.7：A/B 测试框架（前置验证）

**改动方向**: 在正式大范围应用之前，先做小范围对照验证。

1. **准备 2 套配置**:
   - **A 组（baseline）**：`narrative_review_trigger_mode="always"` + 未修改的 reviewer_core（当前代码）
   - **B 组（优化版）**：`narrative_review_trigger_mode="selective"` + 精简正则 + 瘦身 prompt + persona hint

2. **收集固定测试集**: 30 条真实对话（覆盖日常/亲密/技术/调侃等场景），保存为 JSON 测试文件

3. **对比指标**:
   - 每条回复的 LLM 调用次数（生成 + 审核 + repair）
   - applied=true 比例
   - 人工评分（1-5，评估"像不像人在说话"+"是否偏离角色"）
   - hard issue 命中次数
   - 总耗时

4. **推广门槛**: 只有 B 组人工评分均值 >= A 组，且 LLM 调用次数下降 >= 30%，才推广到 full rollout。

**验收标准**: 完成小范围 A/B 测试并形成书面结论（保存为 `data/plugin_data/astrbot_plugin_narrative_reviewer/ab_report_YYYYMMDD.md`）。

---

### 阶段 1 总体验收门控

| 指标 | 阶段 1 目标 |
|------|-----------|
| 单轮额外 LLM 调用次数（非 RPG） | baseline 的 50-70% |
| 单轮额外 LLM 调用次数（RPG） | baseline 的 60-80% |
| 人工评分："像人在说话"（1-5） | >= baseline |
| 人工评分："角色声线稳定"（1-5） | 比 baseline + >= 20% |
| hard issue 命中率（每 100 条） | 比 baseline 下降 |
| 单轮总耗时（秒） | <= baseline 的 70%，且 < 180s |
| **用户手动测试确认** | **是** |

---

## 阶段 2：取消独立 Reviewer —— 经验浓缩进 Prompt

**目标**: 把阶段 1 验证有效的规则，浓缩进生成器端的 system prompt 和 style skill，让"写对"发生在第一次生成时，而不是事后改正。

### 子任务 2.1：非 RPG 模式 —— Style Skill 升级

**涉及文件**:
- `plugins/astrbot_plugin_style_skills/skills/single-roleplay-core/SKILL.md`
- `plugins/astrbot_plugin_style_skills/skills/single-style-daily/SKILL.md`

**改动方向**:

**single-roleplay-core/SKILL.md**（规则母本）：

在现有的"核心原则"和"输出形态"之间新增一个 **"禁写清单（反模式）"** 章节（15-20 行），集中列出阶段 1 中 Top 5 高频 hard issue。这是整个阶段 2 的核心信息压缩点。

```markdown
## 禁写清单（反模式）

以下写法会让角色像审稿器在整理台词，不像人在说话。遇到时直接用场内动作、物件、距离或一句可接的短台词替换：

- **不要写二分解释腔**："不是 A 而是 B""不是因为 A，是因为 B""并非 A，而是 B"。角色不做自我评价，直接做给对方看。
- **不要复述玩家起手**："你问……""你说……""面对你……"是最明显的 AI 痕迹。直接回应。
- **不要给台词加字幕式旁白**："语气里藏着软糯""每个字都戳得很稳""像怕这句话被夜风偷走"。如果一句台词需要旁白解释才成立，这句台词需要重写。
- **不要把责任推回玩家**："你再问我一遍""到门口再问""我会再问一遍"。当前轮就接住：答一半、给时间地点、或由角色主动承担下一步。
- **不要写成流程表**："菜单我来定""不许只喝汤不吃面""我允许你靠过来""乖乖听医嘱"——这些是医生/教官台词，不是恋爱日常。保留角色的关心和条件，但把它写成带喜欢感的轻条件（"先把碗放稳啦""先吃两口，好不好""别笑，我会担心的"）。
- **不要写封闭结尾**："她看着你""关系更近了""故事继续"——最后一拍必须是可接抓手：未完成动作、问题、物件、时间、或一句角色内台词。
- **不要写后台计划式台词**："好，那我该这样做""让他知道我不是在赶他走"——这是模型在展示写作意图，不是角色在当场说话。改成动作或一句短台词。
```

**single-style-daily/SKILL.md**（日常风格细则）：

在末尾补充一个 **"日常场景快速自查清单"**（8-10 行，浓缩关键词形式），让模型在生成时快速自检：

```markdown
## 日常快速自查清单（写完扫一遍）

- [ ] 这一轮至少有一处"可接抓手"（问题/条件/物件/未完成动作）？
- [ ] 中段有没有"话轮压迫点"（不是只在结尾加一句"好不好"）？
- [ ] 语气助词是真正的角色口癖，还是流程句的声线补丁？
- [ ] 温柔/害羞/监督/调侃，哪一项占据了本轮主声线？（恋爱日常里，温柔 + 调侃或嘴硬关心通常是正确组合）
- [ ] 有没有删掉了正常口语的停顿感？（"你倒是挺会精打细算的"比"你会精打细算"更自然）
- [ ] 有没有把日常关心写成了命令？（"我会看着的哦"比"不许XX"更像恋爱对话）
```

**验收标准**:
- 关闭 reviewer（`narrative_review_enabled=false`）后，用同一 30 条测试集跑一次"纯 style skill 升级版"
- "独立 reviewer 90% 的硬伤改写效果"用以下量化：style skill 版中，**被 reviewer 标记为 hard issue 的句子比例**上升到 baseline 的 85% 以上（即独立 reviewer 命中 100 条硬伤，style skill 版能让模型第一次就不写出 >= 85 条）
- 单轮耗时从 baseline（生成 + 1-2 次审核 + 0-1 次 repair）下降到"仅生成一次"，耗时减少 >= 50%

---

### 子任务 2.2：RPG 模式 —— Narrator System Prompt + Contract 升级

**涉及文件**:
- `plugins/astrbot_plugin_agentic_RPG/prompts.yaml`（narrator_system / director_system 相关段落）
- `plugins/astrbot_plugin_agentic_RPG/handlers/hooks.py` 中的 `build_narrative_contract_text()`

**改动方向**:

**a) Narrator 提示词新增"叙事质量锚点"**:

在 `prompts.yaml` 的 narrator_user_structure_rule（或对应 narrator system prompt 位置），新增一个段落。与 2.1 中的"禁写清单"保持对齐，用语境合适的措辞（更正式，适合 GM 叙事）：

```yaml
叙事质量锚点（Narrator 遵守，不触发第二次改写，第一次就写对）：

- 台词驱动：每个互动拍至少 1 句角色短台词 + 1 个可见动作/物件/距离，不要先 8 行旁白再给一句干对话。
- 禁写二分解释壳/字幕式旁白（与角色卡写作规则一致）。
- 每 2-3 个互动拍要有一个玩家可接的互动点：问题、物件、未完成动作、或需要确认的信息。
- 恋爱/亲密场景默认"先有喜欢感，再加条件/监督"的声线顺序。
- 不要把具体场景压成摘要。保留角色的语气、动作承接和可接话头。
- 不要为了扩写而灌水；场景需要时可以更长，但每 3 句至少要有一个推动剧情或关系的信息。
```

**b) Contract 文本追加"叙事质量合约"**:

在 `build_narrative_contract_text()`（RPG 插件每次叙事都会拼入的 contract 文本）的末尾，追加 3-5 行的"叙事质量合约"——当前 contract 主要是世界设定/角色记忆/规则限制，可以在末尾追加质量约束。

追加内容示例:
```
叙事质量合约（本次叙事必须遵守，不遵守不会触发第二次改写，而是第一次就写对）：
- 角色台词直接、贴角色、有目的（追问/提醒/设条件/回避/调侃/承认），不要加旁白解释台词效果。
- 每 2-3 拍要有一个玩家可接的互动点：问题、物件、未完成动作、或需要确认的信息。
- 不要写封闭结尾。最后一句永远留给玩家可回应的空间。
- 不要用"不是 A 而是 B"这类自我解释句式。
- 不要把具体场景压成摘要。保留角色的语气、动作承接和可接话头。
```

**验收标准**:
- RPG 模式下关闭 reviewer，对比 baseline 叙事文本，人工评分（可读性/沉浸感/对话驱动度）均值 >= baseline 的 90%
- 单轮 RPG 叙事总耗时（含 director/narrator/router）下降 >= 30%

---

### 子任务 2.3：把 Reviewer 改为"审计工具"而非"必经过滤器"

**涉及文件**:
- `plugins/astrbot_plugin_narrative_reviewer/_conf_schema.json`
- `plugins/astrbot_plugin_narrative_reviewer/main.py`
- `plugins/astrbot_plugin_agentic_RPG/_conf_schema.json`

**改动方向**:

在配置 schema 中新增 `narrative_review_run_mode`（string），取值:
- `rewrite_and_audit`（阶段 1 默认，对生成文本做审核+改写）
- `audit_only`（阶段 2 目标——只检测+记录问题，不修改文本，用于质量监控和后续训练数据标注）
- `disabled`（完全关闭）

`main.py` 的 `on_llm_response` 钩子根据 run_mode 选择分支:
- audit_only 模式下依然调用 `reviewer.review()`，但忽略 `result.final_text`
- 只把 audit doc 写入磁盘，并把 issues 写入 event.extra 供后续分析
- 这样 reviewer 从"必经后处理"降级为"质量巡检器"

RPG 插件的 `_review_narrative_text()` hook 同样支持三态切换。

**验收标准**:
- `run_mode=audit_only` 时，最终输出的文本与关闭 reviewer 时完全相同（人工对比 20 条）
- audit doc 依然完整落盘，问题分类聚合正常工作
- audit_only 模式下的额外 LLM 调用对普通用户不可见（仅后台写入，不增加用户等待）

---

### 子任务 2.4：长期质量闭环 —— 用 Audit 数据喂养 Prompt 优化

**改动方向**: 阶段 2 部署后，reviewer 的 audit 数据成为持续改进的数据源。每 1-2 周执行一次聚合脚本，输出以下可执行洞察：

1. **Top 3 高频 hard issue**（分类 + 样例 + 出现趋势）
2. **Top 3 高频 style 失败**（按 style/daily/nsfw 分层）
3. **持续恶化预警**：某个 category 连续 2 周上升，说明 style skill / narrator prompt 中对应规则不够强，需针对性补强
4. **Gold Standard 增量收集**：每月从被命中的 bad case 中人工抽取 20 条，标注"理想改写"，增量更新 `reference_samples.yaml`，作为 future few-shot 的锚点
5. **角色卡质量报告**：按角色卡聚合，发现特定角色卡反复触发同一类 issue（说明角色卡描述有问题，或需要补充反例）

**验收标准**:
- 聚合脚本运行成功，输出清晰的 1-2 页周报
- 连续 4 周聚合数据显示，hard issue 命中率逐周下降或稳定在低位（目标：每 100 条回复中 hard issue 总数 < 10 条）
- 每月新增的 gold standard 样本被确认能提升 few-shot 改写质量（通过 A/B 对比验证）

---

### 阶段 2 总体验收门控

| 指标 | 阶段 2 目标 |
|------|-----------|
| 单轮额外 LLM 调用次数（非 RPG） | ≈ 0（一次性生成，audit_only 可选后台调用） |
| 单轮额外 LLM 调用次数（RPG） | ≈ 0（narrator 一次性写对，contract 内嵌质量规则） |
| 人工评分："像人在说话"（1-5） | >= stage 1 的 90% |
| 人工评分："角色声线稳定"（1-5） | 与 stage 1 持平或更好 |
| hard issue 命中率（每 100 条） | 持续下降（audit_only 模式下后台监控） |
| 单轮总耗时（秒） | <= baseline 的 50% |
| **用户手动测试确认** | **是** |

---

## 实施顺序（关键路径）

```
Step 1 [~1h]: 子任务 1.7（A/B 测试框架搭建）→ 先有基线数据

Step 2 [~2h]: 子任务 1.1（正则精简） + 1.2（分层门控）→ 最小改动，最大性能收益

Step 3 [~1h]: 子任务 1.3（system prompt 瘦身）→ 降低每次调用 token 成本

Step 4 [~2h]: 子任务 1.4（审计重构） → 建立量化反馈循环
Step 5 [~2h]: 子任务 1.5（参照文本）

Step 6 [~1h]: 子任务 1.6（上下文微调 —— persona hint）→ 提升改写的角色声线稳定性

Step 7 [~1h]: 用 A/B 框架验证阶段 1 → 用户手动测试确认

─────────────────────────────────────────────────────────────────

Step 8 [~1h]: 子任务 2.1（style skill 升级 —— 非 RPG）

Step 9 [~1h]: 子任务 2.2（narrator prompt + contract 升级 —— RPG）

Step 10 [~1h]: 子任务 2.3（reviewer 改为 auditor-only）

Step 11 [~1h]: 子任务 2.4（长期闭环）→ 用户手动测试确认阶段 2
```

**每完成一个步骤（Step 1-7 / Step 8-11 作为整体分批通知），通知用户进行手动测试确认后，再推进下一个步骤。**

---

## 不做的事情（边界管理）

以下改动被明确排除在本次计划外：

1. **不改角色卡的基础内容**（persona 文本本身）——只在 reviewer 的上下文中暴露角色卡信息，让它不改错声线。
2. **不新增任何新的角色卡 skill**——优化现有 SKILL.md 的内容，不新增 skill 目录或新的 skill 注册流程。
3. **不改 RPG 插件的 contract 结构**（字段、数据模型）——只在 `build_narrative_contract_text()` 的末尾追加文字，不改动 contract 的整体结构。
4. **不把参照文本变成大规模训练集**——控制在 8-12 条 bad/good 对照，作为 few-shot 锚点，不是 fine-tuning 数据。
5. **不新增对话历史回写功能**（不重写历史消息，只改写当前回复）——避免"修了当前轮但前面的对话不一致"。
6. **不引入第三方规则库**——所有修改都在 AstrBot 现有的插件框架内，不引入外部依赖。

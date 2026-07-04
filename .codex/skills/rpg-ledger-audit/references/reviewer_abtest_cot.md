# Narrative Reviewer AB/COT 审计参考

本参考用于审计 `astrbot_plugin_narrative_reviewer` 的 AB 测试、COT + CAI（宪法 AI）新版 reviewer，以及把 reviewer 方法论迁移回生成层 narrator / prompt 的二阶段工作。

## 当前结论

优先看好 `doubao_cot` 新模式。目标不是把 reviewer 做成越来越精密的关键词裁判，而是让 LLM 学会怎样写出玩家满意的中文角色回复。

审计时默认方向：

- 减少反面教材堆砌。
- 减少角色名、场景名、专用词绑定。
- 减少关键词触发和正则门槛。
- 增加第一性原理：角色声线、媒介分工、玩家格式、信息保真、恋爱温度、开放位、反编造。
- 让审稿模型先理解“为什么这样写不好”，再改写；不要只让它匹配“出现了哪些坏词”。

## 当前功能

`narrative_review_framework` 支持三种模式：

- `classic`：旧版 `reviewer_core.py`，依赖较多确定性检查、长 prompt、二次质量修复。
- `doubao_cot`：新版 `reviewer_cot_core.py`，使用宪法原则 + 6 步 COT 审稿，一次 LLM 调用完成审计、评分、改写。
- `both`：AB 模式。

当前接线差异：

- 独立 `narrative_reviewer` 的 single_role 路径在 `both` 下是真 AB：先跑 classic，再跑 `doubao_cot`，两份结果都会写入 audit。
- single_role 最终选择策略偏向 COT：COT 可用时优先用 COT；COT 未应用而 classic 应用时回退 classic。
- RPG hook 当前不是真 AB。RPG 读取到 `both` 时，因为 `framework != "classic"` 会走 `reviewer_cot_core.py`，实际等同 COT。

因此：

- 非 RPG / single_role 可以比较 classic 与 COT 的双份 audit。
- RPG 场景目前只能审计 COT 结果本身，不能把缺少 classic 对照误判为 AB 失败。

## COT + CAI 机制

新版 COT reviewer 的核心是“宪法原则 + 推理步骤”，不是关键词门槛。

当前核心原则：

- 角色声线优先。
- 无解释壳。
- 媒介分工清晰：台词负责关系压力，旁白负责可见信息，交互层负责玩家可接位置。
- 有开放位。
- 日常口语纹理。
- 恋爱温度。
- 信息保真。
- 初始化与设定搭建保真。
- 格式忠诚。
- 角色口癖与自称隔离。
- 世界观锚点。
- 玩家格式匹配。
- 反编造。

6 步审稿：

1. 阅读场景、玩家意图、角色意图，并观察玩家最近 1-2 条消息格式。
2. 判断角色声线和关系温度。
3. 对照宪法原则找结构性问题。
4. 制定改写策略。
5. 输出改写。
6. 自检是否仍有 OOC、编造、格式漂移或冷硬化。

审计时要看 COT 是否真的抓住结构，而不是只复述“AI 味浓”“不自然”。

## Audit 判读

COT audit 通常有：

- `schema_version: "cot_v1"`
- `framework: "doubao_cot"`
- `constitutional_scores`
- `thinking_trace`
- `metadata.constitutional_principles_count`

classic audit 通常通过 `metadata.review_rules_version` 判断版本。

single_role AB 对照时：

- 看 `metadata.sub_framework` 区分 `classic` 和 `doubao_cot`。
- 不要只看最终发送文本；要同时看两份 audit 的 `original_text`、`final_text`、`issues`、`score`。
- 如果 COT applied 但质量比 classic 差，记录为 COT 原则或提示缺口，而不是回到关键词门槛。

RPG COT 审计时：

- 看 `*-rpg-cot.json` 或 RPG hook 写入的 reviewer 结果。
- 不要期待同轮出现 classic 对照。
- 若 RPG 质量下降，先判断是 narrator 生成层问题、reviewer 改写问题、contract 注入问题，还是角色 skill 本身资料不足。

`thinking_trace` 是审计字段，不应出现在玩家可见文本中。

## 人工审计优先级

先看这些结构问题：

- 是否保留原文说话习惯：例如 `（动作）`、`“台词”`、无引号短句、玩家习惯的省略号。
- 是否正确识别任务意图。玩家要求初始化、人物关系、时代背景、当前场景、开始扮演时，这些设定信息是任务正文，不是普通 RP 互动中的解释壳。
- 是否保留角色声线，而不是把所有角色改成审稿器偏好的冷静事务腔。
- 是否避免角色口癖串线。三月七不能使用爱莉希雅的 `♪`、`小爱`式自称或粉色妖精口吻；每个角色的口癖、称呼和自称只属于自己。
- 是否保留恋爱感和伴侣感。默认多数玩法是恋爱关系，角色通常应像喜欢玩家的可爱女孩子，而不是管理者、医生、教官或流程审批人。
- 是否保留足够篇幅。删除解释壳和无效装饰，不等于把日常互动压成短摘要。
- 是否响应玩家已经给出的动作、问题、告白、邀约，而不是让玩家“再问一遍”。
- 是否新增了原文没有的事实、地名、事件、身体暗示、战斗结果、玩家反应。
- 是否让结尾有可接位置，而不是抽象总结或封闭凝视。

如果 reviewer 改坏了，优先归因为：

- 格式忠诚失败。
- 初始化意图识别失败。
- 角色口癖隔离失败。
- 角色声线被统一化。
- 媒介分工错位。
- 恋爱温度不足。
- 信息保真失败。
- 反编造失败。
- 玩家格式匹配失败。

不要优先归因为“缺少某个关键词规则”。

## 二阶段迁移方向

二阶段目标是把稳定的 reviewer 方法论迁移回生成层本身，使 narrator / prompt 在初稿阶段就写好，减少外部 reviewer 依赖。

可迁移的是原则，不是正则：

- 把“台词负责关系压力，旁白负责可见信息，交互层负责玩家可接位置”写入 narrator。
- 把“默认恋爱/伴侣关系中保留可爱、温柔、喜欢、亲近感”写入角色生成层。
- 把“保留玩家格式和原有说话习惯”写入生成层。
- 把“初始化/开场搭建时保留人物关系、时代背景、当前场景”写入生成层。
- 把“角色口癖、自称、符号不能跨角色复用”写入生成层。
- 把“不要新增事实，不要替玩家决定”写入 contract / narrator。
- 把“不要要求玩家重复已问过的问题”写入互动结构原则。
- 把“删除解释壳但保留口语纹理和篇幅”写入文风原则。

不优先迁移：

- 大量坏例原句。
- 角色名绑定关键词。
- 场景名绑定关键词。
- 硬编码专有名词触发器。
- 会误杀中文语义的短词正则。

## 初始化场景

不要把所有背景设定都视为解释壳。

如果玩家在初始化、开场、角色关系确认、时代背景、当前场景、开始扮演或世界观搭建，背景/关系/当前场景就是玩家要求的内容。reviewer 可以做的事：

- 删掉机械前言。
- 把生硬小标题润色为自然分段。
- 保留关系、时间线、地点、可用物品、第一轮可接动作。
- 把最后一拍接入可互动位置。

reviewer 不应做的事：

- 直接删除人物关系、时代背景、当前场景。
- 把初始化压成普通两三句互动。
- 只因为改写后低于某个比例就一律判失败，或只因为原文有设定段就一律判解释壳。

长度只能作为异常信号，不应作为普通硬门槛。只有候选明显截断、空泛、只剩几十字，才用长度拦截。

## 互动格式

当前只保留两种互动格式，不再鼓励 reviewer 自由发明第三套格式。

中文小说模式：

- 用 `“”` 包裹对话。
- 动作直接写在旁白处，不使用 `（）` 包裹。
- 心理必须用“她心想 / 心里想 / 他想”等方式明确标出，避免和旁白混在一起。

语C模式：

- 台词可以直接写。
- `（）` 中写动作、心理。
- 不要把语C改成小说散文，也不要把小说模式强行改成语C。

审计时先看玩家最近 1-2 条消息和原文稳定习惯属于哪一种；如果没有可参考玩家消息，NPC 首发默认使用中文小说模式。

## 成本和限流

`both` 会让 single_role 每轮跑两个 reviewer，延迟和消耗接近翻倍，也更容易触发每分钟或每日请求限制。

建议：

- 小样本人工对比时用 `both`。
- 稳定测试或长聊天时切回 `doubao_cot`。
- 会话级临时关闭用 `reviewer close`，恢复用 `reviewer open`。默认开启。
- 若要 RPG 真 AB，需要先修改 RPG hook，让它像 single_role 一样分别跑 classic/COT 并写双份 audit。

## 路径同步

以下文件必须保持 `plugins` 与 `data/plugins` 同步：

```text
E:\agentic-rpg\AstrBot\plugins\astrbot_plugin_narrative_reviewer\main.py
E:\agentic-rpg\AstrBot\data\plugins\astrbot_plugin_narrative_reviewer\main.py
E:\agentic-rpg\AstrBot\plugins\astrbot_plugin_narrative_reviewer\reviewer_cot_core.py
E:\agentic-rpg\AstrBot\data\plugins\astrbot_plugin_narrative_reviewer\reviewer_cot_core.py
E:\agentic-rpg\AstrBot\plugins\astrbot_plugin_narrative_reviewer\_conf_schema.json
E:\agentic-rpg\AstrBot\data\plugins\astrbot_plugin_narrative_reviewer\_conf_schema.json
```

如果不同步，测试会出现“以为在跑新版，实际加载旧版”的错觉。

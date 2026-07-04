# RPG 插件审计修复计划 v2

> 基于 Session 1098307480 审计结果 + 用户反馈修订
> 修改范围：prompt、guidance、style 文件（不修改 Python 代码）

---

## 一、批次 1：Director / Contract 注入机制修复

### 1.1 Director prompt — observable_to_player 强制动词短语化

**文件**：`plugins/astrbot_plugin_agentic_rpg/prompts.yaml`（`director_system` 字段）

**当前问题**：
- `director_system` 原则 11 已经写了"短动作意图 15-45字"，但实际输出仍然是完整中文叙事句（证据：审计账本 20260620-033901 中 observable 为"她轻轻握紧了他的手，在跨过星海门扉前回头对他笑了笑，眼神温柔而笃定，示意他睁眼时她一定在这里"——约 60 字完整句）
- 缺少"禁止跨轮重复相同动作组合"的约束
- 缺少人称一致性规则（第三人称 vs 第二人称）

**修改内容**：

在 `director_system` 的核心原则部分（原则 10-11 附近），**替换** observable_to_player 的规则为以下更严格的版本：

```
10. observable_to_player 禁止包含静态外观模板：不得写固定外貌/姿势/服装/随身道具的重复性描写。
    这些描述由叙事 LLM 从角色档案中自行取用，Director 不应每轮通过合同强制注入相同文字。

11. observable_to_player 必须是「动词短语」，不是完整句：
    - 格式：主语(可选) + 1-2 个动词 + 动作目标/对象
    - 正确示例：「握住你的手，回头笑」「侧过身，指尖轻点桌面」「沉默片刻，避开那个名字」
    - 错误示例：「她轻轻握紧了他的手，在跨过星海门扉前回头对他笑了笑，眼神温柔而笃定」
    - 字数上限：30 字（短动作）或 40 字（含情绪修饰的动作）
    - 绝对禁止：完整主谓宾句子、比喻句、情绪解释、对白、引号内容

12. observable_to_player 禁止跨轮动作重复：
    - 同一 NPC 连续 2 轮不得使用相同的动作动词组合（如「歪头+指尖轻点」不得连续出现）
    - 同一 NPC 连续 3 轮不得使用相同身体部位描写（眼睛/嘴角/指尖 轮流切换，必要时用非身体动作：呼吸节奏、脚步、手里的东西、与环境互动）
    - 检查方法：生成前先自问「上一轮我写过这个动作吗？」如果是，换一种表达方式

13. observable_to_player 人称统一：
    - 对玩家的称呼必须使用玩家姓名（来自 character_package 的 <user> 姓名）或「你」，禁止使用「他」「星」这类泛指或具体角色名的第三人称
    - NPC 自身用名字或角色名指代
    - 正确示例：「爱莉希雅握住星的手，回头一笑」「她侧过身，指尖轻点星的鼻尖」
    - 错误示例：「她轻轻握紧了他的手」「她侧过身支起一点，用食指尖轻轻点在星的鼻尖上」（错误：第三人称"他/星"）

14. observable_to_player 必须有场面功能：
    - 它要改变场面、回应玩家、暴露玩家可接住的矛盾/选择，或把剧情推向下一步
    - 若删掉后场景毫无变化，输出空字符串。不要用通用微表情、纯氛围润色、眼神/嘴角/手指的小动作凑字段
```

**同时**在 director_system 的末尾输出模板（JSON schema 中 `observable_to_player` 的值说明）**更新为**：

```
"observable_to_player": "(动作描述，30字以内动词短语。主语+1-2动词+目标。必须改变场面/回应玩家/暴露矛盾。禁止完整句/比喻/对白/静态外观/时间数字/事实答案。禁止与上一轮动作重复。人称：NPC名+对玩家名/你的动作。无有效新动作输出空字符串)"
```

**同时**在 Director 自审清单（最后的检查列表）中**追加**第 6-8 条：

```
自审清单（输出前逐条检查）：
1. 回应必要性：玩家本轮是否直接叫了该 NPC 或向 TA 提问？
2. 外观自检：observable_to_player 是否包含任何静态外观？是→删除
3. 场面功能：如果删掉 observable_to_player，本轮场景会失去什么？
4. 角色一致性：动作是否符合 TA 的性格、当前心情、与玩家的关系？
5. 事实答案自检：是否写了时间数字/人物生死/权限结论/完整对白？是→删除事实
6. ✨动词短语格式自检：是否写成了完整主谓宾句子？是→压缩为"动词+目标"短语
7. ✨跨轮重复自检：近 2 轮是否写过相同动作动词组合/相同身体部位？是→换一种表达
8. ✨人称自检：对玩家的称呼是否用了玩家名/「你」而不是「他/她」？否→修正
```

### 1.2 Contract pipeline — sanitize 强化兜底

**文件**：`plugins/astrbot_plugin_agentic_rpg/handlers/contract_pipeline.py`（不修改逻辑，只读确认——因为代码层 sanitize 目前只有引号剥离 + 80字截断，不足以阻止完整句注入）

**确认点**（不需要改动，记录当前状态供后续验证）：
- `_sanitize_director_observable` 当前只做：引号剥离、检查事实答案（姬子/死亡等）、80字截断
- **缺少**：完整句检测（是否包含句号/逗号连接的多分句）、人称修正（他/星 → 玩家名/你）、动作短语去修饰（去掉"眼神温柔而笃定"这类状语从句）
- 这意味着 Director prompt 层的约束是主要防线，代码层目前是"最小清洗"而非"结构清洗"

**验证**：改完 1.1 的 prompt 后，打开最新 1-2 个审计账本，手动查看 contract_4_0 中 observable 字段的形态——如果仍然是 50+字完整句，说明需要在代码层增加更强 sanitize（下一阶段再考虑，本轮不动代码）。

---

## 二、批次 2：Narrator prompt — 反重复、反模板化约束

### 2.1 guidance/global.md — 禁止动作短语与比喻的跨轮重复

**文件**：`data/plugin_data/astrbot_plugin_agentic_rpg/guidance/global.md`

**当前问题**：
- Narrator 自身回声问题：审计证据显示"紫粉色的眼睛""像一只猫""花瓣/星光比喻"等在多轮重复出现
- 目前 global.md 只有"禁止跨轮复制角色外观模板"，缺少动作/比喻/情绪节奏的反重复规则
- 用户认为这是通用问题，不需要做模型差异化（即所有模型都有这一倾向）

**修改内容**：

在 global.md 中"禁止机械化句式"或"禁止泄漏系统字段"之后，**插入**一段新规则：

```
动作与比喻的轮换机制（本页新增）：
- 禁止连续两轮使用相同身体部位来表达情绪（上一轮写了"紫粉色的眼睛轻轻颤了一下"，本轮就不能再写"她的眼睛..."，改用"呼吸放缓了一下"或"手里的书翻到一半停住了"）
- 禁止连续两轮用同一套比喻类型（上一轮用了"像一只猫"，本轮就换一种；上一轮用了"花瓣/星光"，本轮就避开这些意象）
- 禁止"歪头+轻笑+眼神变化"这种标准三板斧反应——如果近 2 轮的 director observable 中已经出现过这些动作模式，Narrator 必须选择另一套表达（脚步变化、沉默、与环境/物件的互动、语气用词），而不是重写一遍
- 检查方法：写完正文后回头看最近 1-2 轮的输出，如果发现"紫粉色的眼睛""像一只X""指尖/嘴角/眼神"在同一位置反复出现，立刻替换
```

### 2.2 rpg-style-core/SKILL.md — 声明三级优先级链

**文件**：`plugins/astrbot_plugin_agentic_rpg/skills/rpg-style-core/SKILL.md`

**修改内容**：

在文件**开头**（5条红线之前或紧接红线之后），**插入**优先级声明：

```
规则优先级（自上而下，冲突时高优先级覆盖低优先级）：
1. core 的 5 条红线（伪造系统信息、代玩家行动、未落盘生成、替换玩家目标、感官罗列）——绝对不可违反
2. canonical_characters 中当前 NPC 的 voice / speech_pattern / signature_phrases / state_layers 规则——角色声线高于通用文风
3. 当前激活的 rpg-style-* 子 Skill（daily / story / combat / intrigue / relationship / commission / ceremony / levelup）的场景特定规则
4. guidance/global.md 的通用写作质量基准（信息密度、格式匹配、反机械化句式、反情绪卡尺化、末尾选项等）
5. chat_template.json 中的顶层 persona（main / 小爱）——仅作为风格补充，不得与 1-4 冲突
```

同样在 `data/plugin_data/astrbot_plugin_agentic_rpg/guidance/global.md` 开头插入相同内容，保持两个入口一致。

### 2.3 rpg-style-relationship/SKILL.md — 删除"必须产出硬变化"的前置提醒（不需要）

根据用户反馈，d 项不需要——relationship 场景不需要"必须先有工具依据才能写硬变化"。

**文件**：`plugins/astrbot_plugin_agentic_rpg/skills/rpg-style-relationship/SKILL.md`

**检查**：如果文件中有类似"新物件/新地点必须由工具生成后才能写"的描述，删除。如果没有这类描述，则不做改动（不需要改动）。

### 2.4 信息量与推进要求——确认 daily/ceremony 不被"少即是多"削弱

**文件**：`data/plugin_data/astrbot_plugin_agentic_rpg/guidance/styles/daily.md`

**检查**：当前 daily.md 主张"让话题变轻""有时最好的回应是短到近乎普通"——这与用户"信息量不足、拖沓不可接受"的反馈有潜在矛盾。

**修改内容**：

将 daily.md 中关于"短"的描述**修正**为强调"质量而非长度"：

```diff
- 有时最好的回应是短到近乎普通："嗯。" "我知道。" "别闹。" 然后继续手里的事
+ 日常不是简写的借口。日常场景也要保持 2-3 层信息密度：
+   · 一层动作：角色在做什么（切菜、翻书、擦杯子）
+   · 一层对白/回应：角色说了什么或如何回应
+   · 一层可接信息：一个可被追问的话题、一个可被玩家注意到的细节、一个未说完的话
+ 不允许整轮只有"嗯""别闹"这类纯敷衍回应——如果玩家主动输入了内容，至少要有真实的互动
```

### 2.5 ceremony 仍然需要 3-4 个末尾选项

**文件**：`plugins/astrbot_plugin_agentic_rpg/skills/rpg-style-ceremony/SKILL.md`

**检查**：确认 ceremony 中是否有"仪式时刻不写选项/留白"的主张。如果有，修改为"仪式时刻仍然以 3-4 个选项收尾"。

**修改内容**：

在 ceremony 文件中任何涉及"克制/留白"的地方，**补充**：

```
仪式时刻不代表无所作为——每轮仍然必须以 3-4 个编号选项收尾：
- 1-2 个继续仪式进程的选项（继续对话、接下一步、接受某个变化）
- 1 个偏离/个性化选项（玩家可以做一件"仪式之外"的小事来增加角色感）
- 1 个休息/暂停选项（先放在这里、稍后再继续）
```

---

## 三、批次 3：style 文件冗余与世界观清理

### 3.1 删除 style 文件中的世界观描述

**文件**：`plugins/astrbot_plugin_agentic_rpg/skills/rpg-style-*/SKILL.md` 中的每一个包含"都市恋爱/星际冒险/奇幻探索"等世界观描述的文件

**当前问题**：style 文件中反复出现"世界观表格"——daily、story、combat、intrigue、commission、relationship、ceremony 都有自己的世界观适配表。

**用户立场**：世界观应该由 preset/world_info/character_package 注入，style 只负责通用写作引导，不维护世界观。

**修改策略**：遍历以下文件，**删除**或**大幅缩减**世界观相关段落：

| 文件 | 需要处理的段落 | 处理方式 |
|------|---------------|---------|
| rpg-style-daily | "世界观适配"表格（都市恋爱/星际冒险/奇幻探索 × 特色细节/语言风格/探索钩子） | 删除整个世界观表格 |
| rpg-style-story | 类似的世界观氛围描述段落 | 删除或简化为"遵循 preset 中的世界观氛围" |
| rpg-style-combat | 世界观 × 战斗基调 × 伤害感官 × 环境融入 | 删除世界观表格，保留动词库和动作节奏指南 |
| rpg-style-intrigue | 世界观 × 谈判/审讯/情报交换风格 | 删除世界观段落 |
| rpg-style-commission | 发布者类型 × 语气风格 × 典型委托（按世界观分类） | 删除世界观分类 |
| rpg-style-relationship | 告白场景/冷战质感/和解信号（按世界观分类） | 删除世界观分类 |
| rpg-style-ceremony | 按世界观分类的仪式叙事 | 删除世界观段落 |

**删除后统一插入**一句话：

```
世界观氛围：由当前 preset 的 world_info / 场景快照 / 角色卡共同决定。本 Skill 不提供固定世界观描述，只提供通用写作引导。
```

### 3.2 guidance/styles/daily.md 作为 rpg-style-daily 的补充保留

**文件**：`data/plugin_data/astrbot_plugin_agentic_rpg/guidance/styles/daily.md`

**用户确认**：daily.md 应该是 rpg-style-daily 的补充而非重复

**确认点**：当前 daily.md 的内容（话题变轻、最小有效单位、环境作为呼吸间隔、减少完美对话、日常节奏范例）都是 rpg-style-daily 中没有的针对性约束——定位正确，保留。

**不需要改动**。

### 3.3 core 的多人镜头配额简化为引用 global

**文件**：`plugins/astrbot_plugin_agentic_rpg/skills/rpg-style-core/SKILL.md`

**修改内容**：

在 core 中找到"多人镜头配额"段落（1 主焦点 + 1-2 副焦点 + 0-2 背景存在），**替换**为：

```
多人镜头配额：参见 guidance/global.md 中的详细规则。核心原则：1 主焦点 + 1-2 副焦点 + 0-2 背景存在。
连续 2-3 轮没有被牵动的 NPC，下一轮应被分配副焦点 beat——不是为了让每个人都说话，而是让场面保持"有多个角色在活动"的真实感。
```

注意：global.md 中已有更详细的"镜头流动/非焦点 NPC 不消失"的描述。

### 3.4 core 的 NPC 外观描写删除，由 global 统一

**文件**：`plugins/astrbot_plugin_agentic_rpg/skills/rpg-style-core/SKILL.md`

**修改内容**：搜索 core 文件中关于"NPC 外观描写/首次登场外貌/禁止敷衍为居家服/连衣裙"的段落，**删除**整个段落。在 core 中保留一行引用：

```
NPC 外观描写规则：由 guidance/global.md 统一约束（禁止跨轮复制外观模板、禁止每轮报完整清单、禁止固定外观姿势）。此处不重复。
```

### 3.5 ceremony 的"禁止弹出系统格式成就提示"删除（由 core 红线 1 覆盖）

**文件**：`plugins/astrbot_plugin_agentic_rpg/skills/rpg-style-ceremony/SKILL.md`

**修改内容**：搜索 ceremony 中是否有独立的"禁止弹出获得成就/系统提示"段落。如果有，**删除**该独立条目，在文件末尾加一行说明：

```
禁止系统广播/状态栏/工具回执式输出：由 rpg-style-core 红线 1 统一覆盖。
```

如果 ceremony 文件中没有这段文字（可能被其他地方统一覆盖），则不需要改动。

---

## 四、验证与验收标准

### 4.1 手动验证清单（每轮审计 1-2 个账本）

| 检查项 | 通过标准 | 查看位置 |
|--------|---------|---------|
| Director observable 是动词短语 | contract_4_0 中 observable 字段 ≤ 40字，无句号结尾的完整主谓宾句 | `contract_4_0.narrative_contract.must_include` |
| Director observable 无人称泄漏 | 不出现"他/星"这类第三人称指代玩家 | 同上 |
| Director observable 动作不重复 | 同一会话中相邻 2-3 轮没有重复的动作动词组合 | 跨账本比对 |
| Narrator 正文不回显 Director observable | 正文中出现与 observable 字面匹配的子串比例 < 30% | `response.text` vs contract observable |
| Narrator 没有"紫粉色的眼睛/像一只猫"式比喻重复 | 同一会话中这些短语的出现频率 ≤ 每 3 轮 1 次 | `response.text` 多轮比对 |
| ceremony 场景仍然有 3-4 个编号选项 | ceremony 风格激活时，末尾必须出现 `[1] ... [2] ... [3] ... [4] ...` | 风格 = ceremony 的审计账本 |
| daily 场景不缩水为纯敷衍回应 | daily 风格下每轮正文 ≥ 150 字且包含动作/对白/信息各一层 | 风格 = daily 的审计账本 |
| style 文件中无世界观描述 | grep 各 style 文件，不应出现"都市/星际/奇幻/世界观/城市设定/世界背景"等关键词作分类使用 | grep style SKILL.md |
| 三级优先级链声明存在 | core 和 global 开头都有优先级声明 | 文件开头前 20 行 |

### 4.2 不需要做的事（明确排除）

- 不创建 scoped model-specific guidance（用户确认目前不需要差异化）
- 不修改任何 Python 代码
- 不创建新的骨架文件
- 不需要"硬变化必须先有工具依据"的前置提醒（用户说不需要）
- chat_template.json 的 slot 开关状态不需要改动（用户确认当前配置合理）

---

## 五、执行顺序建议

按以下顺序执行修改可最大化依赖层覆盖、最小化反复回读：

1. **第 1 步**：`plugins/astrbot_plugin_agentic_rpg/prompts.yaml` — director_system（批次 1.1）
2. **第 2 步**：`data/plugin_data/astrbot_plugin_agentic_rpg/guidance/global.md` — 动作/比喻反重复（批次 2.1）+ 优先级链声明（批次 2.2）
3. **第 3 步**：`plugins/astrbot_plugin_agentic_rpg/skills/rpg-style-core/SKILL.md` — 优先级链声明（批次 2.2）+ 多人镜头配额简化（批次 3.3）+ NPC 外观删除（批次 3.4）
4. **第 4 步**：`data/plugin_data/astrbot_plugin_agentic_rpg/guidance/styles/daily.md` — 反缩水/保信息密度修正（批次 2.4）
5. **第 5 步**：`plugins/astrbot_plugin_agentic_rpg/skills/rpg-style-ceremony/SKILL.md` — 确认仍然有 3-4 个选项的要求（批次 2.5）+ 删除独立的系统提示禁止（批次 3.5）
6. **第 6 步**：遍历 rpg-style-daily/story/combat/intrigue/commission/relationship/ceremony — 删除世界观表格、插入统一声明（批次 3.1）
7. **第 7 步**：`plugins/astrbot_plugin_agentic_rpg/skills/rpg-style-relationship/SKILL.md` — 检查并确认不需要"硬变化先有工具依据"的提醒（批次 2.3）

完成后执行 4.1 的手动验证清单。

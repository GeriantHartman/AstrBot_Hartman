# 第二轮 · 竞品分析（偷师视角）

> 分析人：竞析（Compa）· 竞品分析师
> 日期：2026-09-18
> 方法：全部基于 2026-09 实时 WebSearch / WebFetch 检索，来源在文末逐条标注。凡未在一手来源证实的均标注「未验证」。
> 检索纪律：找不到就写「未找到」，不凭记忆编造产品特性。

---

## 0. 本次分析的口径（先纠正第一轮的方向）

第一轮的产出是**市场定位**视角（哑铃形赛道 + 中档空白 + 商业化建议）。本轮**口径完全改变**，必须先作废三条：

| 第一轮的结论 | 本轮为什么作废 |
|---|---|
| 「中档空白 = 最大机会，我方应卡位」 | 这是**私人产品**（D3：「本项目本身就是只服务我一个人，后续扩展到小部分我认可的朋友」）。**不存在"市场机会"问题。** |
| 「补齐留存节奏机制（每日任务/签到/推送/排行）」 | 目标用户只有 1 人 + 少数朋友。运营化机制（签到/排行/推送）在单机私人产品上**没有意义**。 |
| 「无 UGC / 无社区 = 结构性劣势」 | 对私人产品而言**不是劣势**，是设计前提。 |

**本轮唯一任务：从竞品里偷师具体设计，用来解决负责人亲口指出的 5 个问题。**
本报告中一切竞品机制，只回答"**别人是怎么做的、能不能搬过来**"，不回答"能不能赚钱 / 能不能增长"。

**三条硬约束（所有落地建议必须满足）**：
1. **玩家不调用工具**（C7：「我的设计都是 LLM 来调用工具，不应该人来调用」）。
2. **叙事风格自动切换**（C4），玩家不手动调。
3. **流式不可用**（消息平台限制，最终迁 Discord）。

---

## 1. 问题①：**「预写世界 + 关系养成」这类产品存在吗？**

### 1.1 先分类，再回答

负责人的原话（开放问题 2）是「**我想消费一个写好的世界**」，而 D1 旅程是「进入世界探索 → 遇到喜欢的角色 → 深入交流发展关系 → 意外偶遇其他喜欢的角色 → 与更多角色建立关系」。这要求**两个属性同时成立**：
- **世界是作者写好的**（玩家不需要发明世界）；
- **关系是玩家养出来的**（不是看别人写好的恋爱剧本）。

按这两个属性，我把检索到的产品分成三类：

| 类别 | 世界是否预写 | 关系是否可自由养 | 代表产品 |
|---|---|---|---|
| **(a) 预写世界 + 固定剧情线** | ✅ 作者写死 | ❌ 沿固定 route 走 | 视觉小说 / 乙女（恋与深空）、Choice of Games、Detroit 式分支叙事 |
| **(b) 预写世界 + 自由关系发展** | ✅ 作者写死 | ✅ 玩家自己推进 | **Fallen London**、**Hidden Door**、**DreamGen**、**SillyTavern（卡+世界书+群聊）**、**AI Dungeon Scenarios/Character Creator** |
| **(c) 无预写世界（玩家发明）** | ❌ 玩家自建 | ✅ 自由 | Character.AI、Talkie/星野、Replika、Nomi、Kindroid |

### 1.2 结论：**存在，但不在 AI 原生赛道的主流里**

**最重要的发现**：**AI 原生产品（Character.AI / Talkie / Replika / Nomi / Kindroid / AI Dungeon 默认模式）几乎全部属于 (c) 类** —— 它们不提供"作者写好的世界"，世界要靠玩家自己在对话里发明。而**提供"预写世界"的产品，全部属于 (a) 或 (b)，且几乎都不是 AI 原生陪伴产品**（游戏、互动小说、极客自托管工具）。

这意味着负责人的诉求（"消费一个写好的世界"）**在 AI 陪伴赛道里是稀缺的** —— 主流 AI 陪伴产品的默认体验恰好是反过来的：**AI 陪你，但世界是你自己撑起来的**。这也解释了他开放问题 3 的观察：「被 NPC 意外到……有过，但处于项目早期或未深入插件时期，**越深入开发这种时候越少**」—— 开发越深，他越是从"玩家"变成"世界的作者"，于是"被世界意外到"的空间被自己挤掉了。

### 1.3 它们靠什么机制做到"玩家不必发明世界，却仍有掌控感"？

我检索出 **5 类可复用的机制**，每类都有具体产品出处：

**机制 1：菜单化的动词 —— 世界提供"你能做什么"，玩家只做"选哪个"**
- **Fallen London（Failbetter，2009）** 的核心机制叫 **Storylet**：世界里有 **3,224 个非 FATE 故事块**（官方 wiki 计数），每个故事块**限定地点**，玩家进入后看到的是**作者写好的若干选项**，而不是空白输入框。世界是作者写的，玩家做的是"在给定动词里挑一个"。
  - 来源：fallenlondon.wiki/wiki/Storylets（2026-08）。
- **AI Dungeon** 把这件事做成了产品化的 **Scenarios**：创作者预写 `Starting Prompt` + `Description`（供 AI 理解的世界 lore，**AI 不会从 Description 继续写**，只当世界信息用）+ `Story Cards`（关键词触发）+ `Plot Components`。玩家进游戏先做**角色创建选择题**（Class/Race/Location/Faction，全部是创作者预置的选项），再开始玩。
  - 来源：help.aidungeon.com/faq/whats-the-difference-between-scenarios-and-worlds、/faq/plot-components（2026-09 检索）。
- **对我方的启示**：这就是负责人 D1 第 1 步「进入世界探索」的正确形态 —— **探索 = 世界给你一屏可选动作**，不是让玩家凭空想"我现在该干嘛"（B4 正是这个痛点：「我该思考在这个区域做什么……我该如何搭话」）。

**机制 2：关键词触发的世界书 —— 世界在需要时自动出现，玩家不需要背设定**
- **SillyTavern 的 World Info / Lorebook**：作者预写世界观条目，**只在消息里出现关键词时才注入上下文**。玩家不需要记住设定，世界会自己"冒出来"。
- **AI Dungeon 的 Story Cards**：同一思路（"broader world-building details that are **only included when keywords are used**"）。
- **DreamGen 的 Scenario Codex（情境典籍）**：类 Wiki 的设定系统（角色/地点/道具/规则/"禁止发生的情节"），**每次生成时把相关条目注入上下文**。
  - 来源：help.aidungeon.com/faq/plot-components；weavai.app DreamGen 评测（2026-06-02）。
- **对我方的启示**：负责人要"消费写好的世界"，最省力的形态就是**世界书自动注入** —— 世界知识不需要玩家复述，也不需要占满上下文（对齐"人设常驻、细节按需检索"）。

**机制 3：导演/叙事者承担推进 —— AI 主动提出下一步，玩家只做否决/微调**
- **Hidden Door（2020 成立，2025-08 正式上线）**：从**授权 IP**（《克苏鲁的呼唤》《傲慢与偏见》《绿野仙踪》《乌鸦》）出发，官方描述为「Guided by an omniscient Narrator, players make characters that they then take on a variety of adventures, **responding to prompts to guide the action in any direction**」。玩家**回应 Narrator 给的 prompt**，而不是自己发明场景。
  - 来源：variety.com（2025-08-13）、hiddendoor.co。
- **DreamGen 的叙事模式（Story Mode）**：AI 以第三人称推进故事，"更像在读一本互动小说"，适合"不想一直打对话的用户"。
- **SillyTavern 的群聊 auto-mode**：群聊按 reply order **自动生成**，无需用户交互（5 秒延迟触发下一轮），用户一开始打字就自动关闭。
  - 来源：docs.sillytavern.app/usage/core-concepts/groupchats/。
- **对我方的启示**：这直接对治 B2 的 4 分项「**想我接下来说什么**」。我方已有 `move_to_zone`（覆盖 10.7% 回合）这类"世界推你一把"的工具，缺的是**把它变成"叙事者先开口"**（见设计 C）。

**机制 4：收束输入空间 —— 选项不是限制，而是"消灭 OOC 机会"**
- 一篇 2026-07 的深度技术评论说得最清楚：**「若界面只提供选项而不提供自由文本，用户就无法输入『我是秦始皇』；这不是因为 AI 更强，而是因为输入空间被收束了。」** 并指出 VN / 互动影视「OOC 风险较低、体验较稳」，代价是"自由度受限、内容成本前置"。
  - 来源：juejin.cn/post/7660702273779449891（2026-07-11）。
- **对我方的启示**：这条要**谨慎用**。负责人 E4 明确要「**存在且兼容的高自由度玩法的玩具，可以不按照固定规则玩**」、E3 要「新鲜感和意外感」。→ **不能用"收束输入"来解决他的问题**，但可以用"**在自由输入之外额外提供选项**"作为下限保障（见设计 C 的边界说明）。

**机制 5：关系的"门"由世界事件开 —— 掌控感来自"我在推进一条被设计好的线"**
- **Hades 的"心锁"（Locked Heart）**：送礼到某阶段后，**必须完成特定 favor / 剧情条件**才能继续推进关系，不能靠刷礼物刷到底（详见第 2 节）。
- **BG3 的 camp scene**：每个恋情场景**单独设整数门槛**，且需要特定剧情节点（如"击杀尤尔吉尔后"）才解锁。
- **对我方的启示**：这是把"关系"从"数值"变成"**被世界事件门控的进度**"，同时满足"世界是作者写好的"和"关系是我推出来的"（见设计 A）。

### 1.4 问题①的直答

**Q：这类产品存在吗？**
**A：存在，但（b）类"预写世界 + 自由关系发展"是稀缺形态。** 最接近负责人诉求的商业产品是 **Hidden Door**（授权世界 + Narrator + 卡片收集/remix）与 **SillyTavern 群聊**（多张预写角色卡 + auto-mode + 世界书）。**AI 原生陪伴赛道（Character.AI / Talkie / Nomi / Replika）整体不提供"预写世界"**。

**Q：靠什么机制让玩家不必发明世界却仍有掌控感？**
**A：5 类** —— ①菜单化动词（Fallen London storylets / AI Dungeon Scenarios）②关键词触发的世界书（SillyTavern Lorebook / AI Dungeon Story Cards / DreamGen Codex）③导演承担推进（Hidden Door Narrator / DreamGen Story Mode / SillyTavern auto-mode）④收束输入空间（VN 范式，**我方因 E3/E4 不宜采用**）⑤关系门由世界事件开（Hades 心锁 / BG3 camp scene）。

---

## 2. 问题②：**好感度二极管 —— 竞品怎么处理"关系进度"**

### 2.1 负责人原话（C6）的三个子问题

> 「很容易进入二极管状态，即，最高好感或最低好感（或者负好感）才会有明显区别，**中间状态几乎看不出区别**。且后续玩家都喜欢**默认保持自己喜欢的角色在最高好感状态**，即使是 reset、开了新群后也是如此。**不喜欢反复攻略**。」

拆成三个可检索的问题：
- **Q2a**：主流产品是否也退化为"只有极值有意义"？
- **Q2b**：有没有产品设计了"**不反复攻略**"的关系形态？
- **Q2c**：中间态怎么做出"明确的可感知差异"？

### 2.2 Q2a：**是，AI 原生赛道几乎全部退化为"极值有意义"**

| 产品 | 关系进度形态 | 中间态是否有差异 |
|---|---|---|
| **Replika** | XP / Level。日上限免费 650 / Pro 900；官方只给**软里程碑**「约 Level 30 开始更懂你、约 Level 50 更稳定」，**明确不是硬解锁** | ❌ **官方自己承认 Level 1–29 没有明确的功能翻转** → 这正是"中间态看不出区别"的教科书案例 |
| **Character.AI** | **没有关系系统**。只有 Facts（人物事实）/ Story Memory（事件）/ Persona | ❌ 无关系维度 |
| **Talkie / 星野** | 好感度数值 + "关系解锁"（互动越多 → 好感越高 → **解锁更多对话选项和剧情**）+ 星念卡图鉴 | ⚠️ 中间态**有**内容门，但公开资料只到"解锁对话选项和剧情"，**没有官方说明中间态叙事是否有差异** → 标注「未找到」 |
| **Nomi** | **没有传统等级**。官方用"**记忆成熟度 + 消息量**"描述推进；Mind Map 约 **500+ 条消息**才成形 | ⚠️ 无数值，但"中间态"由记忆量隐式体现，**玩家不易感知** |
| **Kindroid** | 五层记忆系统 + 高度自定义人格 | ⚠️ 同上，关系不是数值也不是阶段 |

**结论**：**Q2a = 是。** 头部 AI 陪伴产品要么根本没有关系系统（Character.AI），要么用"数值 + 里程碑"（Replika / Talkie），**中间态普遍无差异**。负责人遇到的二极管问题**不是他实现得差，而是这个品类的通病**。

### 2.3 Q2c：**真正"不二极管"的设计，全部来自单机游戏 —— 4 个可搬的范式**

这是我本次检索**最有价值**的发现：**游戏行业早就有成熟答案，而 AI 陪伴行业没有抄。**

#### 范式 1：**每一级都有"有名字、可感知"的收益** —— Persona Social Link
- rank 1→10，**每个 rank 有 rank up event**（头顶 `!` 图标）。
- **party member 的每个 rank 有具体能力**（这是关键 —— 中间态不是空的）：

| Rank | 效果 |
|---|---|
| 1 | 每战可替主角挡一次致命一击 |
| 3 | 概率触发 Follow-Up 追击 |
| 5 | 概率治愈队友的 Down 状态 |
| 7 | 概率治愈 Rage / Panic / Fear |
| 9 | 每战可复活一次 |
| 10 | Persona 转生（数值+抗性提升） |

- **并且有"变差"的方向**：**Reversed（逆位）/ Broken（破碎）** 状态 —— 长期不理或选极差选项会触发，需要**高 Expression 属性**才能修复。
  - 来源：megatenwiki.com/wiki/Social_Link（2026-07-23）。
- **可搬之处**：关系等级**每一级都要挂一个具体的、玩家能说出来的好处**，而不是"好感 60→70 什么都没变"。

#### 范式 2：**关系 = 事件集合，而不是数值** —— Fire Emblem Support
- Support 关系是 **C / B / A（/ S）** 分级，**每升一级解锁一段专属对话事件**，外加战斗加成。
- 关系不是"好感 85 分"，而是"**我们已经聊过这 3 段话了**"。
  - 来源：fireemblemwiki.org/wiki/Support。
- **可搬之处**：把"好感度"重新定义为**已发生的对话/事件清单**，玩家看到的是"我们之间发生过什么"，而不是一个数字。

#### 范式 3：**关系推进被世界事件"门控"，不能靠重复动作刷** —— Hades 心锁
- 关系分 **4 阶段**，每阶段有具体解锁：

| 阶段 | 需要 | 解锁 |
|---|---|---|
| 1 | 1 个蜜露 | **纪念品（Keepsake）** |
| 2 | 额外 4~6 个蜜露 | **对话** |
| 3 | 1 个安布罗西娅 | **满好感** |
| 4 | 额外 1~2 个安布罗西娅 | **同伴召唤（部分角色）** |

- **关键机制「心锁」**：送礼到某阶段后，**心形图标上锁**，必须**完成该角色特定的 favor / 剧情条件**才能继续。例如：给 Skelly 送满后要「用 5 级 Zagreus 形态的剑『杀』他一次」；给 Megaera 送满后要「在逃脱中多次遇到她并在房间触发 2 段过场」。
  - 来源：ntgame.com/hades/relationships/、foggyproductions.com Hades Cthonic Gods Favors（2026-08 检索）。
- **「恋爱选项不可逆」**：官方攻略明确「恋爱选项不可逆，存档一旦确定恋爱关系无法更改」。
- **可搬之处（对治"不喜欢反复攻略"）**：**关系的推进不是"重复给礼物"，而是"完成新事件"。** 玩家每推进一格，都必须去经历一段**新的、作者写好的内容** —— 这既解决了"反复攻略无聊"，又让"中间态"自动有了差异（因为每一格后面都跟着一段独特内容）。

#### 范式 4：**给中间态命名，但命名必须够细** —— BG3 的"七档命名 + 隐藏整数"
- BG3 有 **7 个命名档位**，这是"让中间态可感知"的正确做法：

| 数值 | 档位名 |
|---|---|
| -49 ~ -40 | 极低（Very Low）—— 下次分歧很可能离队 |
| -39 ~ -20 | 低（Low） |
| -19 ~ 20 | 中立（Neutral） |
| 21 ~ 40 | 中等（Medium） |
| 41 ~ 60 | 高（High） |
| 61 ~ 80 | 极高（Very High） |
| 81 ~ 100 | 卓越（Exceptional） |

- **同时它演示了反面教训**：「中立」档从 **-19 跨到 20（共 40 点）**，而多个恋情检定就藏在这个区间里（Wyll 的庆功宴调情 **低于 10 失败**，Lae'zel 的恋情 **20 开启**）—— 两者进度条**都显示"中立"且都不动**。→ **命名档位能救中间态，但档位太粗就白搭。**
- 另外：**-20 / -40 是警告，-50 是永久离队**；**每个恋情场景单独设整数门**（Wyll 10/20、Shadowheart 20/40、Karlach 20/30、Minthara 31/40/50、Gale 36、Astarion 40/70）。
  - 来源：gamertagmythras.com BG3 approval guide（2026-09 检索）。
- **可搬之处**：给关系**命名**（而不是只显示数字），且**档位要细**（别让一个名字覆盖 40 点）。

#### 补充范式：**关系是可消耗的具名资源** —— Fallen London
- 关系不是"好感度"，而是**一堆具名 quality**（如 `Acquaintance` 等级、Favours）。**社交动作会消耗 Favour** —— 关系是**状态/资源**，不是单调上升的数值。
  - 来源：fallenlondon.wiki/wiki/Social_Actions_(Guide)（2026-07）。
- **可搬之处**：关系可以有"用掉"的维度，这天然制造中间态的差异。

### 2.4 Q2b：**"不反复攻略"的关系形态 —— 有，三种**

| 形态 | 代表 | 机制 |
|---|---|---|
| **不可逆** | Hades（恋爱选项不可逆）、Persona（max 后永久）、BG3（一个恋爱存活者） | 一旦确立，不再要求重复确认 |
| **事件/记忆集合** | Fire Emblem（support 对话）、Persona（rank up event）、BG3（camp scene） | 关系 = "我们经历过什么"，不是分数 |
| **门控（gated）** | **Hades 心锁**、BG3 camp scene | 关系不能靠重复动作推进，**必须靠新事件** |

### 2.5 问题②的直答

**Q：主流产品是否也退化为"只有极值有意义"？**
**A：是，AI 原生赛道几乎全部如此。** Replika 官方自己说 Level 30/50 是"软描述，不是硬解锁"，Level 1–29 没有功能翻转。

**Q：有没有"不反复攻略"的关系形态？**
**A：有，三种（不可逆 / 事件集合 / 门控），但全部来自单机游戏，AI 原生陪伴产品里我没有找到成熟实现。** 最接近的是 Nomi（无等级、以记忆成熟度表述关系）。

**Q：中间态怎么做出可感知差异？**
**A：三招** —— ①每级挂一个具名收益（Persona 能力表）②把关系重新定义为事件清单（Fire Emblem）③**档位命名 + 档位要细**（BG3，反面教训是"中立"跨 40 点）。

> **未找到**：Talkie/星野"好感度中间态是否有差异化叙事"的官方说明。公开资料只到"解锁对话选项和剧情"，**没有任何来源描述中间态（非满好感）的具体体验差异**。我检索了 gongke.net 星野/Talkie 词条、贴吧玩法帖、第一轮已引的星野用户研究报告，均无此信息。

---

## 3. 问题③：**长期记忆 —— 实现方式、玩家感知、失败模式**

背景：负责人 C3 给「记忆召回」**7 分（与叙事风格切换并列最高）**，D5 说玩家最在乎「情绪价值、陪伴体验、角色还原度、**记忆保持**」。

### 3.1 竞品的实现方式（5 种范式）

| 产品 | 实现 | 关键细节 |
|---|---|---|
| **Character.AI** | **三层**：Story Memory（用户 pin + 自动）/ Facts（自动抽取人物事实，可编辑、可禁用）/ Memory Usage（可视化占用） | ★ **Facts 支持"复制到新 chat"**：「Tap a Character, select Start new chat, and you'll see the option to **copy Facts to new chat memory**. Everything your Character knows about you, the Persona, and the world carries straight over.」 |
| **Nomi** | **分层**：近期上下文 / 短中长期记忆 / **Identity Core**（角色自我认同）/ **Mind Maps**（把长期记忆连成关系网，约 **500+ 条消息**成形）/ Shared Notes / Backstory | ★ 官方原则：「**目标是相关性，不是不断回溯**」 |
| **AI Dungeon** | Memory System（Auto Summarization）+ Story Summary + Plot Essentials + Author's Note + Story Cards（关键词触发） | 官方明确**无 game state、无工具调用**，一致性靠"摘要 + 检索" |
| **SillyTavern** | Summarize 扩展 + Vector Storage（RAG） | chunk 400 字符 / top-3 召回 / score ≥ 25% / 不 shuffle 最近 5 条 / 注入到 top 或 in-chat depth 2；★ 官方警告「**不保证更好的记忆**」，且与 prompt caching **互斥** |
| **DreamGen** | Scenario Codex 注入 | 类 Wiki 的设定库，按需注入 |
| **Letta / MemGPT** | OS 式分层（主上下文 ≈ RAM / 召回 / 归档）；Letta Code 的 **MemFS**（git 版本化的文件式记忆） | 启发：「可编辑、可版本化、可按需加载的**外部心智状态**」 |
| **Anthropic** | Context Engineering：**Compaction**（摘要压缩）/ Tool result clearing / Memory tool（`/memories` 文件）/ Just-in-time 检索 | 原则：「让角色**做笔记**，而不是**背全文**」 |

来源：blog.character.ai/memory/（2026-05-21）、nomiaicom.com/knowledge/how-nomi-ai-memory-works（2026-07-24）、help.aidungeon.com、docs.sillytavern.app/extensions/chat-vectorization/、weavai.app DreamGen 评测、juejin.cn/post/7660702273779449891（2026-07-11，含 Letta/Anthropic 对照）。

**★ 对我方最直接的一条**：Character.AI 的「**Facts 复制到新 chat**」直接对治 C6 的「即使是 reset、开了新群后也是如此」——**它把"关系事实"做成了可迁移资产**。负责人其实**想要**"新群还认得我"，但他现在的实现是"二极管式保持最高好感"，而不是"有质感地延续"。两者差别见第 5 节设计 B。

### 3.2 玩家如何"感觉到"一个角色记得自己？—— 官方与用户的双重判据

**Nomi 官方给出的判据（5 条）**：
1. **重要人物保持可辨认** —— 反复出现的人、早前的承诺、偏好，在措辞淡出后仍有意义；
2. **未完线索可被续接** —— 伴侣能顺着未完成的线索继续；
3. **反应被此前经历塑形** —— **不靠硬提旧事，而是背景自然影响回应**；
4. **宏大图景成型** —— 人物/地点/话题/目标的关系网逐步建立（约 500+ 条消息后）；
5. **一致的角色内核** —— Identity Core 让 Nomi 在情境变化中始终"是同一个人"。

★ 并明确说：**「好的连续性往往是安静的」**（"如果每次回复都硬提旧事以证明'记得'，对话会很生硬"）。

**用户侧的感知（技术评论引用的用户原话）**：
> 「**她记得我上次提过的那首诗。**」
> 「**他今天的语气，和我们第一次见面时不一样了。**」
> 「**我们好像真的认识了很久。**」

→ **关键洞察：玩家感知到的"记得"，来自语气与关系的变化，而不是"引用了一条事实"。** 这与我方 C3「记忆召回 7 分 + 叙事风格切换 7 分**并列最高**」高度吻合 —— 这两件事在玩家感知里其实是**同一件事**：**记忆通过风格变化被感知**。

来源：nomiaicom.com；juejin.cn/post/7660702273779449891。

### 3.3 失败模式（8 条，全部有出处）

| # | 失败模式 | 具体表现 | 出处 |
|---|---|---|---|
| 1 | **Context rot** | 人格漂移 / 前后矛盾 / 循环重复 / **身份崩塌**（角色不再是"你的"角色）；根因是"**lost in the middle**"（首尾强、中间弱） | kenoticlabs.com（2026-04-07） |
| 2 | **压缩到失去意义** | 「小明喜欢诗歌」→「用户爱好诗歌」→「诗歌爱好者」：**事实还在，意义被磨平**；机器记住了事实，丢掉了语气/语境/情感权重 | juejin（2026-07-11） |
| 3 | **检索到但没被用上** | Character.AI **官方承认**：写入记忆**提高**被采用概率，**不保证**按原文使用 | juejin 引 Character.AI；blog.character.ai |
| 4 | **过度引用显得刻意** | 每次硬提旧事来"证明记得"，对话生硬 | Nomi 官方；juejin |
| 5 | **无遗忘、无合并** | 「今天天气不错」与「用户叫小明」平级保存；「喜欢红色」与「最喜欢深红」冲突并存 → 作者称这是「**最伤记忆质量的缺陷**」 | juejin |
| 6 | **记忆越多越不稳** | 期望-能力剪刀差；用户失望的不是"没存"，而是"**明明存了却没检索对**" | juejin |
| 7 | **记忆加剧谄媚** | 研究称开记忆后任务准确率**平均下降 12%~18%**，形成"越记忆越谄媚、越谄媚越觉得记忆有效"的正反馈 | winzheng.com 编译 TechCrunch（2026-06-11） |
| 8 | **模型升级 ≈ 角色重置** | 换模型版本"角色感"整体漂移，**记忆救不了"大脑换人"** | juejin |

**★ 与我方现状的直接对应（重要）**：
- 失败模式 #4（过度引用）+ #6（检索到没用上）**正好解释了 C6 的二极管**：当"好感度"只有极值有意义时，LLM 唯一能"表演记得"的方式就是**反复引用最高好感状态**（默认保持最高好感）——因为中间态没有任何可引用的差异。
- 失败模式 #2（压缩丢意义）+ #5（无合并）**直接对应我方 `forget`（回溯一轮）与跨会话状态**：如果记忆层没有"合并/衰减/重要性"，reset 后只能靠"数值最高"来维持关系感。
- 失败模式 #7（谄媚）**解释了 D5**：「玩家有很强的自我纠正和适应能力」——玩家其实能容忍工程不完美，但**记忆导致的谄媚会让"角色还原度"崩塌**，而这正是负责人 M1 最在乎的 KPI（「能否还原角色」）。

> **未找到**：任何产品**公开说明"记忆引用频率"如何调优**。Nomi 只给了原则性表述（"安静地连续"），没有可核实的参数或策略。Character.AI 只说"提高概率"。

---

## 4. 问题④：**能不能把玩家输出成本降得更低，但保留自由表达与意外感？**

### 4.1 先钉死约束：负责人**不要**被限制成"点选项"

| 证据 | 内容 |
|---|---|
| B2 | 「**想我接下来说什么**」= **4 分**（与"中途出戏"并列最高） |
| E1 | 选 **B**（要我想接下来该说什么） |
| E3 | 选「**A，但我想要新鲜感和意外感**」 |
| E4 | 「**存在且兼容的高自由度玩法的玩具，可以不按照固定规则玩**」 |
| 实测 | 每回合中位 **65 字**散文，纯「继续」类仅 **1.4%** |

→ 他的矛盾是：**想少花力气，但不想失去自由和意外。** 任何"把玩家变成选项点击器"的方案（VN 范式、纯菜单）**都会违背 E4**。

### 4.2 竞品的 6 个机制（全部是"降低输入成本但保留自由/意外"）

#### 机制 A：**零输入续写** —— AI Dungeon `Continue`
- AI Dungeon 把旧的"纸飞机图标"改成明确的 **Continue 按钮**，官方原话：「**Many players also don't realize they can simply continue the story without typing or taking a turn.**」并让 Continue / Retry 与 Take a Turn **地位平等**。
- 保留自由：Do/Say/Story/See 四种输入模式 + **文本框始终可见**。
  - 来源：aidungeon.io/phoenix。
- **可搬之处**：把"继续"从隐藏功能提升为**与主动输入平级的默认动作**（我方目前纯"继续"类仅 1.4%，说明它没有被"摆到台面上"）。

#### 机制 B：**重掷（Swipe / Retry）** —— 零写作成本，纯靠挑选获得意外
- **Character.AI Swipe**：重新生成回复，用户滑动挑选。**玩家一个字都不用写，就能得到不同的走向**。
- 2026-03-18 起免费用户 **Swipe + Go-on + Memo 合计约 400 次/天**（全账号共用）。
  - 来源：weavai.app（2026-08-14）、roborhythms.com（2026-03-13 / 2026-07-01）。
- **AI Dungeon Retry** 同思路（与 Continue 并列为三大动作之一）。
- **可搬之处**：这是**"要意外感但不加写作负担"的最直接机制** —— 不满意就重掷，而不是"写更多去修正"。

#### 机制 C：★ **"意外度"旋钮** —— DreamGen `Steering`
- DreamGen 的 **Steering 控制器**是一个**滑杆**：
  - 往「**创意混沌**」推 → AI 这一轮更大胆、更跳脱，**适合打破僵局**；
  - 往「**严格遵循**」拉 → AI 紧守 Codex 设定，减少跑题。
- 官方定位：「让创作者有真正的控制感，而不只是被动接受 AI 的输出」。
  - 来源：weavai.app DreamGen 评测（2026-06-02）。
- **★ 这是本次检索中最优雅的一条**：负责人要"新鲜感和意外感"（E3），但**意外感不是靠写更多换来的，而是靠一个连续控制维度**。玩家把旋钮推过去，AI 自己变大胆 —— **零额外输入成本，直接产出意外**。

#### 机制 D：**AI 主动提议，玩家否决** —— Hidden Door / AI Dungeon 角色创建
- **Hidden Door**：「**responding to prompts to guide the action in any direction**」—— Narrator 给 prompt，玩家回应。
- **AI Dungeon Character Creator**：玩家在**创作者预置的选项**里挑（Class/Race/Location/Faction），并可选 **Quickstart（全部随机）** 直接开玩 —— 「if you want a completely randomized game, or just don't want to spend too much time in character creation」。
  - 来源：variety.com、help.aidungeon.com。
- **可搬之处**：AI 主动提议 + 玩家否决（而不是"AI 等玩家开口"），把"发起"的成本从玩家转移到 AI。

#### 机制 E：**玩家只看戏** —— SillyTavern 群聊 auto-mode
- 「While auto-mode is enabled, the group chat will follow the reply order and trigger the message generation **without user interaction**. The next auto-mode turn is triggered after a **5-second delay**… **When the user starts typing** into the send message text area, the auto-mode will be **disabled**.」
  - 来源：docs.sillytavern.app/usage/core-concepts/groupchats/。
- **★ 这条直接命中 D1 的第 4 步「意外情况下偶遇其他的喜欢的角色」**：多张预写角色卡同场 + 自动对话 = **玩家可以旁观角色之间自己互动**，零输入成本，且**意外感天然产生**（角色之间会互相触发）。
- **可搬之处**：我方有 `generate_npcs` / `sync_zone_npcs`（且这两个工具**错误率最高**：12.0% / 11.5%），可把"NPC 之间自动互动一小段"做成**玩家可选旁观的叙事片段**。

#### 机制 F：**混合模式：AI 主导大方向，玩家在分支内自由** —— 技术评论总结的 VN 降维
- 「**大方向创作者主导（防 OOC、控节奏），分支内 AI 自由发挥（保鲜活）**」；并给出一个关键做法：「**预存'策略'而非'台词'**」——
  - 差：用户说你好 → 固定回复「欢迎你，旅者。」
  - 好：命中「问候」策略 → **若初识则问名；若老友则问近况 → 用记忆填充 → 再生成**
  - 组合数从「场景 × 关系 × 情绪 × 记忆」爆炸，降到「策略数 × 填充逻辑」。
  - 来源：juejin.cn/post/7660702273779449891（2026-07-11）。
- **可搬之处**：这正是我方"叙事风格自动切换"（C4）应该走的路 —— **风格由 LLM 按关系状态自动选择**，而不是让玩家调。

### 4.3 问题④的直答

**Q：有没有产品把玩家输出成本降得更低、但仍保留自由与意外？**
**A：有，6 个机制。** 组合起来的最优形态是：

> **AI 主动提议（机制 D）+ 零输入续写（机制 A）+ 一个"意外度"旋钮（机制 C）+ 一个"重掷"按钮（机制 B）+ 可旁观的自动互动（机制 E）+ 自由文本永远可用（机制 F 的底线）**

**关键边界（必须写进设计）**：负责人 E4 明确要"高自由度、可以不按固定规则玩" → **选项/提议只能是"下限保障"，不能是"上限"**。他 65 字的散文输入**不能被剥夺**，也不该被"选项化"取代。

---

## 5. 问题⑤：**3 个可立即借鉴的具体设计**

### 设计 A：**心锁（Locked Bond）—— 关系推进由世界事件门控，而不是刷数值**

| 项 | 内容 |
|---|---|
| **来源产品** | **Hades 心锁**（ntgame.com/hades/relationships/、foggyproductions.com Hades Cthonic Gods Favors）+ **Persona rank-up event**（megatenwiki）+ **BG3 camp scene 整数门**（gamertagmythras） |
| **机制描述** | 关系分阶段（Hades 为 4 阶段）；**每个阶段有具体解锁**（纪念品 → 对话 → 满好感 → 同伴召唤）；**送礼到某阶段后心锁上锁，必须完成该角色特定的 favor / 剧情条件才能继续**（如 Skelly 要"用 5 级 Zagreus 形态的剑杀他一次"）。→ **关系不能靠重复动作推进，必须靠"新事件"**。BG3 的变体：每个恋情场景**单独设整数门 + 剧情节点门**（如 Astarion 70 点 **且** 击杀尤尔吉尔后）。 |
| **为什么解决负责人的具体痛点** | ① C6「**不喜欢反复攻略**」→ 心锁的本质就是**禁止重复动作推进**，每一格后面都是一段**新的作者内容**。② C6「**中间状态几乎看不出区别**」→ 每一阶段都有具名解锁（借用 Persona 的能力表思路），中间态不再是空的。③ 同时满足"消费写好的世界"：**每一格的关系推进都由一段写好的世界事件承接**。 |
| **在本项目的落地形态** | 把 `update_npc_affinities` 从"每回合可加的数值"改成**阶段制 + 门控**：<br>· 好感度**只在特定世界事件**（完成 commission / 区域剧情结算 / 偶遇 / 关键对话）时跨过阶段门；<br>· 到达门后**冻结**，直到对应事件发生（由 Contract Pipeline 的 Director 在结算阶段判定，**玩家不调工具**）；<br>· **阶段必须命名**（借 BG3 教训：命名要够细，别让一个大档位覆盖太宽）；<br>· 中间态挂**具名收益**（对齐 Persona：不只是数字涨，而是"解锁了什么"）。<br>· 风格切换（C4，自动）可以直接复用关系阶段：**阶段变化 → 叙事风格自动切换**，把 C3 里并列最高分的"记忆召回 7"和"叙事风格切换 7"**合并成同一个机制**。 |

---

### 设计 B：**关系 = 可迁移的"记忆卡"，reset / 新群默认继承（而非清零，也非二极管）**

| 项 | 内容 |
|---|---|
| **来源产品** | **Character.AI Facts 的「copy Facts to new chat memory」**（blog.character.ai/memory/，2026-05-21）+ **Nomi 的 Identity Core / Shared Notes / Mind Maps**（nomiaicom.com）+ **SillyTavern 的 Lorebook / World Info** |
| **机制描述** | Character.AI：Facts 自动抽取人物事实（Persona / 角色 / 配角），**可编辑、可禁用**，且新建 chat 时可**一键把 Facts 复制过去**——「Everything your Character knows about you, the Persona, and the world carries straight over.」Nomi：关系不由数值表示，而由**分层记忆 + 身份核心 + 思维导图**表示；官方原则「**目标是相关性，不是不断回溯**」「**好的连续性往往是安静的**」。 |
| **为什么解决负责人的具体痛点** | ① C6「后续玩家都喜欢**默认保持自己喜欢的角色在最高好感状态**，即使是 reset、开了新群后也是如此」→ 负责人**其实想要这个延续**，但当前实现是"二极管式的最高好感"，没有质感。Character.AI 的答案是：**把延续的对象从"数值"换成"记忆卡"** —— 新群继承的是"我们之间发生过什么"，而不是一个"好感 = 100"。② C3「**记忆召回 7 分**」+ D5「**记忆保持**」→ 记忆是最高分项，应该做成**玩家可见的资产**。③ 对治失败模式 #5（无合并、冲突并存）：卡片天然要求"合并/更新"而不是"追加"。 |
| **在本项目的落地形态** | 把关系从"一个整数"改成**一组具名记忆卡**，每条 = `事件 + 关系状态变化 + 玩家偏好`：<br>· 存储在**跨会话持久层**（不随 session 重置）；<br>· **reset / 新群时默认继承**（可显式清空，对齐负责人已有的 `reset` / `forget` 控制权）；<br>· 每回合只注入**与当前话题相关的 1–3 张**（对齐 Nomi「不是不断回溯」与 SillyTavern 的 top-3 召回）；<br>· **中间态由"卡片数量与内容"体现**，而不是数值 —— 这同时消灭了二极管；<br>· **玩家可见**（对齐 C3 记忆 7 分 + 第一轮"状态面板"建议）：以叙事方式偶尔回显（"你注意到 XX 记得你上次……"），而不是显示列表。<br>· **不新增玩家工具调用**：全部由 LLM 在叙事层完成。 |

---

### 设计 C：**"意外度"旋钮 + 零输入续写 + 重掷（三条一组的低输入高自由套件）**

| 项 | 内容 |
|---|---|
| **来源产品** | **DreamGen Steering 滑杆**（weavai.app，2026-06-02）+ **AI Dungeon Continue / Retry**（aidungeon.io/phoenix）+ **Character.AI Swipe**（roborhythms / weavai）+ **SillyTavern 群聊 auto-mode**（docs.sillytavern.app） |
| **机制描述** | ① **Steering**：一个滑杆，往"创意混沌"推 → AI 更大胆跳脱（打破僵局）；往"严格遵循"拉 → 紧守设定。② **Continue**：零输入让 AI 续写（官方承认"很多玩家不知道可以不打字直接继续"）。③ **Swipe / Retry**：不满意就重掷，**零写作成本获得不同走向**。④ **auto-mode**：角色之间自动对话，玩家旁观（5 秒延迟，用户一打字就停）。 |
| **为什么解决负责人的具体痛点** | ① B2「**想我接下来说什么 = 4 分**」（最高分之一）→ 三条机制都**不要求玩家写更多**。② E3「**A，但我想要新鲜感和意外感**」→ **Steering 是"意外感"的直接旋钮**：不写一个字就能让 AI 变大胆。③ E4「**可以不按照固定规则玩**」→ 三条机制都是**可选增强**，自由文本永远保留，不是替代。④ 实测纯"继续"类仅 **1.4%** → 说明"继续"没有被摆到台面上（对齐 AI Dungeon 的教训：**Continue 必须与主动输入地位平等**）。⑤ D1 第 4 步「意外偶遇其他角色」→ auto-mode 式**角色之间自动互动**天然产出意外。 |
| **在本项目的落地形态** | **不新增 UI**（消息平台限制 + 流式不可用），用**玩家已有的自然语言消息**实现（与现有 `reset` / `forget` 同级，**不是工具调用**）：<br>· **零输入续写**：玩家发"继续"→ AI 完整推进一段（不追问）；把这句话写进新手引导（目前引导**只有一句话**，正好可以扩成"三句话教三个动作"）。<br>· **重掷**：玩家发"换一个 / 再来"→ 重新生成上一段（注意：**流式不可用 → 必须等整段生成完再判断**，这反而天然适配"重掷"语义）。<br>· **意外度**：玩家发"更意外一点 / 稳一点"→ 调整叙事倾向（可在 prompt 层实现为风格倾向，**不需要玩家调参数**，对齐 C7）。<br>· **旁观**：在移动区域后，**可选**触发一小段"NPC 之间自动互动"（复用 `sync_zone_npcs`，但**必须先修它的 11.5% 错误率**）。<br>· **硬边界**：以上全部是**可选的下限保障**，**永远不替代自由文本**；不做编号选项的强制（当前编号选项合规率 44.9%，根因是两个注入点互相抵消 —— 建议**直接放弃"每轮必须 3-4 个选项"的硬约束**，改为"可选提议"，同时解决合规率与 E4 的冲突）。 |

---

## 6. 来源清单（检索日期 2026-09-18）

| # | 来源 | 用途 |
|---|---|---|
| C1 | hiddendoor.co、hiddendoor.co/press | Hidden Door 定位、授权世界、Modifiers、卡片收集/remix |
| C2 | variety.com/2025/tv/news/hidden-door-ai-role-playing-fan-fiction-game-platform-1236488265/（2025-08-13） | Hidden Door 机制：Narrator、responding to prompts、cards 跨故事复制、IP 合作模式 |
| C3 | blog.character.ai/memory/（2026-05-21） | Character.AI Story Memory / Facts / Memory Usage；**Facts 复制到新 chat** |
| C4 | kenoticlabs.com/insights/character-ai-memory（2026-04-07） | Context rot 失败模式；检索 vs 重构；lost in the middle |
| C5 | nomiaicom.com/knowledge/how-nomi-ai-memory-works（2026-07-24） | Nomi 分层记忆、Identity Core、Mind Maps（500+ 消息）、**"目标是相关性不是不断回溯"**、玩家如何感到"被记得" |
| C6 | aicompanionpick.com/replika-xp-and-levels-progression-guide（2026-07-02） | Replika XP/level、日上限 650/900、Level 30/50 为**软**里程碑 |
| C7 | megatenwiki.com/wiki/Social_Link（2026-07-23） | Persona Social Link：rank 能力表、Reversed/Broken |
| C8 | fireemblemwiki.org/wiki/Support | Fire Emblem support C/B/A 分级 = 对话事件 |
| C9 | ntgame.com/hades/relationships/（2026-08-20） | Hades 好感度 4 阶段、解锁表、**恋爱不可逆** |
| C10 | foggyproductions.com/guides/hades/topic/cthonic-gods-favors-max-bond-requirements- | Hades **心锁**各角色 favor 条件 |
| C11 | gamertagmythras.com/blog/baldurs-gate-3/baldurs-gate-3-approval-guide（2026-09） | BG3 **7 个命名档位**、-50 永久、逐场景整数门、"中立跨 40 点"反面教训 |
| C12 | fallenlondon.wiki/wiki/Storylets（2026-08-27）、/wiki/Social_Actions_(Guide)（2026-07-02） | Storylet（3,224 个）、地点限定、Acquaintance quality |
| C13 | help.aidungeon.com/faq/whats-the-difference-between-scenarios-and-worlds、/faq/plot-components、/faq/the-story-mode | AI Dungeon Scenarios/Character Creator、Plot Components、Story Cards |
| C14 | aidungeon.io/phoenix | AI Dungeon Do/Say/Story/See、**Continue**、Retry、官方承认"操作被隐藏" |
| C15 | docs.sillytavern.app/usage/core-concepts/groupchats/ | SillyTavern 群聊 reply order、**auto-mode（5 秒）**、Join character cards |
| C16 | docs.sillytavern.app/extensions/chat-vectorization/ | SillyTavern RAG：chunk 400、top-3、score ≥25%、**"不保证更好的记忆"**、与 caching 互斥 |
| C17 | weavai.app/blog/zh-cn/2026/06/02/dreamgen-ai-2026-评测…（2026-06-02/06-17） | DreamGen Scenario Codex、双模式、**Steering 滑杆** |
| C18 | juejin.cn/post/7660702273779449891（2026-07-11） | 记忆能存事实存不了意义、8 个工程坑、Letta/MemGPT、Anthropic context engineering、VN 收束输入、**"预存策略而非台词"** |
| C19 | winzheng.com/article/memory-tools-harm-ai-models（2026-06-11，编译 TechCrunch） | 记忆加剧谄媚：任务准确率下降 12%~18%、正反馈闭环 |
| C20 | weavai.app/blog/en/2026/08/14/character-ai-daily-swipe-limit-400-regenerations-only/、roborhythms.com（2026-03-13 / 2026-07-01） | Character.AI Swipe 机制与 2026-03-18 起日限 ~400 |
| C21 | shike.it168.com/news/27153.html（2026-08-07） | 恋与深空：**羁绊等级直接决定解锁多少私密剧情 / 限定 CG / 专属互动**（关系 = 内容门） |
| C22 | eastora.cn/global-expansion-insights/ai-companion-apps-2026-relationship-asset-market/（2026-04-13） | 行业把"记忆/关系"作为收费资产（c.ai+ 的 "Better Memory"）；关系资产化的两极分化 |
| C23 | 本地代码事实（引用 round2-context.md） | 我方工具名 `update_npc_affinities` / `sync_zone_npcs` / `generate_npcs` / `move_to_zone`；错误率 12.0%/11.5%；编号选项合规率 44.9% |

---

## 7. 明确「未找到」与「未验证」项

### 未找到（已说明检索范围）
1. **未找到**任何 **AI 原生陪伴 / RP 产品**提供"关系不是数值、而是状态/事件/记忆集合"的**成熟商业实现**。该设计范式**全部来自单机游戏**（Persona / Fire Emblem / Hades / BG3 / Fallen London）。Nomi 是最接近的（**无等级**，以记忆成熟度表述），但它没有阶段/事件式的可感知中间态。
2. **未找到**任何 **AI 原生产品**提供"作者写好的世界 + 玩家不必发明世界"的完整机制。最接近的是 Hidden Door（**授权设定 + 卡片**，但**不是固定剧情线**）与 DreamGen（**需要玩家自建 Codex**）。检索了 dunia.gg、flowith.io、dreamgen.com、aimlapi.com 的 2026 年 AI RP 榜单，均未发现其他候选。
3. **未找到** Talkie / 星野"好感度**中间态**是否有差异化叙事"的官方或可信第三方说明。公开资料只到"解锁对话选项和剧情"。
4. **未找到**任何产品**公开说明"记忆引用频率"如何调优**。Nomi 只有原则性表述（"安静地连续"）。
5. **未找到** DreamGen Steering 的**具体参数范围**（只知是滑杆，两端为"创意混沌 / 严格遵循"）。

### 未验证（有来源但未交叉证实）
- Character.AI Swipe 日限"约 400 次"来自第三方博客（weavai / roborhythms），非官方公布。
- Replika Level 30/50 的"软里程碑"表述来自官方帮助中心的转述，未直接读取原文。
- 恋与深空"羁绊等级 → 解锁私密剧情/CG"来自第三方攻略站（shike.it168），非官方文档。
- Hidden Door 的"cards 可跨故事复制、可 remix/分享"来自 Variety 转述官方描述，未在 hiddendoor.co 上找到详细机制文档。
- 「记忆加剧谄媚、准确率下降 12%~18%」来自 winzheng.com 编译 TechCrunch 的二手转述，**未定位到原始论文**。

---

## 8. 三条给团队的跨成员提示（供 team-lead 分发）

1. **给 requirement-analyst（析客）**：C3 里"记忆召回 7"与"叙事风格切换 7"**并列最高不是巧合** —— 竞品证据（Nomi 官方 + 用户原话）表明**玩家感知到的"记得"来自语气/关系的变化，而不是引用事实**。建议把这两个功能**合并成一个机制**（关系阶段变化 → 风格自动切换 + 相关记忆卡注入），而不是两个独立规格。
2. **给 data-analyst（数析）**：设计 A 需要验证一个假设 —— 当前 `update_npc_affinities` 的调用是否**集中在少数"刷好感"回合**（若是，即证明"反复攻略"行为已发生）。可用 `rpg_stats.json` 的 `count` + `llm_audit_index` 交叉。注意审计受 200 行/会话截断。
3. **给 roadmap-planner（路径）**：设计 C 里"旁观 NPC 自动互动"依赖 `sync_zone_npcs`，而它是**错误率第二高（11.5%）**的工具 —— 该设计必须**排在错误修复之后**。设计 C 的其余三条（继续/重掷/意外度）**零依赖，可以最先做**，且都不需要 UI、不需要流式。

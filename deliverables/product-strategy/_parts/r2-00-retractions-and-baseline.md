# 第二轮：结论更正与事实基线（主理人亲自取证）

**日期**：2026-09-18
**类型**：勘误 + 事实基线（第二轮交付物的第 0 节，后续成员产出均以此为基准）
**取证方式**：`characters.user_id` + `is_player=1` 全库扫描（18 个有会话的 `world_*.db`）

---

## 1. 四处在上一轮被证伪的结论（撤回）

| # | 上一轮结论 | 真相 | 撤回原因 |
|---|-----------|------|---------|
| 1 | **「产品对创造者无效：他只玩了 12 回合」** | **完全错误**。产品负责人（`245432630`，角色名「星」）**solo 回合 1049**，是**第二高**；加上群聊共享会话，涉及回合 1915 / 3931 = **49%** | 我只看了 `FriendMessage:245432630` 的 12 回合，**漏掉了他在群聊里的全部游玩** |
| 2 | 「4 个 webchat 空会话证明他不想玩」 | 是**连通性测试**，非游玩 | 产品负责人亲述 |
| 3 | 「流式输出是最高杠杆修复」 | **流式传输不可用**（消息平台限制） | 产品负责人亲述 |
| 4 | 「`user_hash` 可作用户身份签名」 | `handlers/hooks.py` 中 `"user_hash": current_prompt_info["content_hash"]` → 是 **prompt 正文内容哈希** | 字段名与语义不符 |

**另有两条口径更正**：
- 产品负责人会做 **reset 重置** → 真实回合数**比 3931 更长**，3931 是**下限**。
- 「200/120 回合上限」**不存在**（负责人亲述「没有系统上限的说法」）→ 上一轮所有相关推论作废。

> **错误模式复盘**：这是我在本会话第 **4** 次犯同类错误——**用单点观测代替全量普查**。前三次是：把 200 行封顶读成"玩到上限就停"、把最高频字符串读成"主导行为"、把单工具 28 秒读成"每回合等 60 秒"。**这一次的代价最大：我基于一个错误数字建了一整套"operator/player 角色不可兼容"理论。**

---

## 2. 事实基线：18 个会话的完整玩家归属（权威）

| # | session | 回合 | 玩家 |
|---|---------|------|------|
| 1 | `FriendMessage:2438094710` | **1062** | 【野火】new-elysium（`2438094710`）solo |
| 2 | `FriendMessage:942361330` | **512** | 墨（`942361330`）solo |
| 3 | `FriendMessage:245432630` | 12 | 星（`245432630`）solo |
| 4 | `GroupMessage:1090658701` | **498** | 星 solo |
| 5 | `GroupMessage:1097436019` | 158 | 星 + 墨 |
| 6 | `GroupMessage:1098307480` | 47 | 星 solo |
| 7 | `GroupMessage:218606013` | 48 | 星 + a宝（=墨） |
| 8 | `GroupMessage:230394566` | **408** | 星 + 墨 |
| 9 | `GroupMessage:289584858` | **291** | 星 solo |
| 10 | `GroupMessage:426750065` | 2 | {小桃子}（`1565369378`） |
| 11 | `GroupMessage:529384034` | 134 | 星 solo |
| 12 | `GroupMessage:674489689` | 18 | 墨 solo |
| 13 | `GroupMessage:702510574` | 62 | 星 solo |
| 14 | `GroupMessage:814560566` | 5 | 星 solo |
| 15 | `GroupMessage:877459692` | **408** | 墨 solo |
| 16 | `GroupMessage:909871205` | 53 | 星 + 墨 |
| 17 | `GroupMessage:955426627` | 14 | 小夏（`3038924475`） |
| 18 | `GroupMessage:966162158` | 199 | 星 + 墨 |
| | **合计** | **3931** | |

### 2.1 按玩家拆分（**solo 回合是唯一无歧义的归属口径**）

| 玩家 | 角色名 | solo 回合 | 参与会话数 | 共享回合 | 备注 |
|------|--------|----------|-----------|---------|------|
| `2438094710` | 【野火】new-elysium | **1062** | 1 | 0 | 单档最高，单 provider，solo |
| **`245432630`** | **星（产品负责人本人）** | **1049** | **12** | **866** | **solo 第二高，会话数最多** |
| `942361330` | 墨 / a宝 | 938 | 8 | 866 | 长期玩家 |
| `3038924475` | 小夏 | 14 | 1 | 0 | 疑似到访 |
| `1565369378` | {小桃子} | 2 | 1 | 0 | 疑似测试 |

**核算**：solo 1049 + 938 + 1062 + 14 + 2 = 3065；共享会话 866；3065 + 866 = **3931** ✓

### 2.2 结论

1. **产品负责人是最重度用户之一。** solo 回合 **1049**，与最高的【野火】（1062）**几乎持平**；参与会话数 **12**，是所有人里最多的。
2. **他主要在群聊里玩**（12 个会话中 11 个是群聊），且**经常与「墨」一起玩**（5 个会话共享，合计 866 回合）。
3. **他与「墨」构成一对稳定的共同游玩关系** —— 这本身就是产品最重要的社交事实。
4. **上一轮「产品对创造者无效」的结论彻底作废**，基于它的「operator/player 角色不可兼容」理论也需重写（见第三节）。

### 2.3 口径边界（必须声明）

- **群聊会话的 `interaction_count` 是多玩家共享的**，不能按玩家相加。上表用「solo / 共享」区分，避免重复计数。
- **单玩家回合数无法从 DB 精确拆出**（`npc_events.player_entity_id`、`episode_memories.player_entity_id` 是**抽样代理**，不是逐回合归属：例如 `2438094710` 的 1062 回合只对应 87 条 `npc_events`）。因此上表用「solo 回合」而非"某玩家的回合数"。
- 因 reset，3931 是**下限**。

---

## 3. 「不愿游玩」的归因重写

上一轮的答案是「operator/player 角色不可兼容」。**这个答案建立在错误前提上，需重写。**

### 3.1 新证据（全部来自产品负责人亲述）

| 问题 | 回答 |
|------|------|
| A1 | **开发确实给我带来了很大的乐趣** |
| A6 | **不想玩，投入到了别的工程学和项目中** |
| B7 | **玩的下去**，自动代码搬迁到服务器后，**没有更新过功能。但我也没怎么玩** |
| 开放 Q1（转折点） | **投入到了别的工程和项目中，且感觉到没有新鲜感** |
| 开放 Q3（被 NPC 意外到） | 有过，但处于项目早期或未深入研究插件时期，**越深入开发这种时候越少** |
| 开放 Q4（永远只有一个玩家还维护吗） | **会** |
| M1 | 玩游戏的 KPI / 做产品的 KPI …… **我更在乎做产品的 KPI** |

### 3.2 重写后的归因

**不是「他进不去自己的游戏」——他进去了 1049 回合。而是「他的燃料是建造，不是游玩」。**

- 他的乐趣来源是 **开发**（A1）与 **做产品的 KPI**（M1）。
- 他的停玩触发点是**「没有新鲜感」+「投入到别的工程」**（A6 / 开放 Q1），而**不是**产品缺陷。
- 服务器迁移后**没有更新过功能**（B7）→ 建造停止 → 游玩也随之停止。**建造与游玩在他身上是同一条曲线。**
- 「越深入开发，被 NPC 意外的时刻越少」（开放 Q3）→ **开发行为本身在消耗他的惊喜感**。

**因此「如何让他持续回来」的答案不是"改善产品"，而是"给他下一个可建造的东西"。** 这与开放 Q4「会继续维护」一致——他愿意维护，只是需要新的建造目标。

> ⚠️ 本条归因由主理人根据亲述推出，**需由瑞思（用户研究员）独立复核**。若瑞思给出不同结论，以瑞思的为准。

---

## 4. 本轮必须处理的四道硬约束（成员方案不得违反）

1. **流式传输不可用**（平台限制）→ 任何依赖流式的方案作废。
2. **玩家不调用工具**（C7）→ 任何"让玩家操作工具/看面板/调参"的方案作废。
3. **不按增长设计**（D3：只服务 1 人 + 少数认可的朋友）→ 任何留存/DAU/规模化目标作废。
4. **代码只处理确定性事件** → 任何用正则/关键词/Verifier 判断叙事质量的方案作废。

---

## 5. 主理人新增取证：世界时钟不一致（直接解释 B4）

> 这是本轮**唯一由主理人独立发现、且属于确定性状态缺陷**的问题（符合项目规范中"代码可以处理确定性事件"的边界）。

### 5.1 ★ 精确口径：玩家**当前所在 zone** 与全局时钟的一致率仅 **39%**

> **⚠️ 主理人自我收窄**：初次统计用的是"**全部 zone**"，得到"67% 的会话存在不一致"。但代码复核（`core/state_machine.py:1677-1733`）显示 `zones.time_slice` 是**派生/缓存字段**——`update_zone_volatile()` 与 `save_zone_snapshot()` 在 zone 被渲染时把它写成**当次的时间切片**，且 `volatile_cache.time_snapshots[time_slice]` 按时间分片缓存。
> **因此"未被访问的 zone 时间落后"是正常设计，不该计入缺陷。** 真正该测的是**玩家当前所在的那个 zone**。

**代码依据**：
```python
# core/state_machine.py:1677
async def update_zone_volatile(self, session_id, local_id, environment_desc,
                               npcs_present, interactables, time_slice):
    """Update only the volatile fields of a zone (env, NPCs, items, time)."""
    "UPDATE zones SET environment_desc = ?, npcs_present = ?, "
    "interactables = ?, time_slice = ? WHERE local_id = ?"

# core/state_machine.py:1703
async def save_zone_snapshot(self, session_id, local_id, time_slice, env, npcs, items):
    """Save a time-indexed volatile snapshot AND update zone main fields."""
    snapshots = cache.setdefault("time_snapshots", {})
    snapshots[time_slice] = {"env": env, "npcs": npcs, "items": items}
```

**精确实测**（对每个 `characters.current_local_id` 取其 zone 的 `time_slice`，与 `game_sessions.current_time_slice` 比对）：

| session | 回合 | 全局时钟 | **玩家 zone 时钟** | 玩家 zone | 判定 |
|---------|------|---------|------------------|----------|------|
| `FriendMessage:2438094710` | **1062** | 上午 | **午休** | 原理工作室 | ❌ |
| `GroupMessage:877459692` | 408 | 早晨 | **傍晚** | 墨的房间 | ❌ |
| `GroupMessage:230394566` | 408 | 早晨 | **上午** | 公司内部 / 花海公寓302室 | ❌ |
| `GroupMessage:289584858` | 291 | 清晨 | **黎明** | 夜语学院·炼金术 | ❌ |
| `GroupMessage:966162158` | 199 | 早晨 | **深夜** | 长夜月的公寓（星） | ❌ |
| `GroupMessage:1097436019` | 158 | 深夜 | **上午 / 早晨** | 海瑟音的音乐工作室（星） | ❌ |
| `GroupMessage:529384034` | 134 | 早晨 | **下午** | 星的房间 | ❌ |
| `GroupMessage:909871205` | 53 | 上午 | **清晨** | 更深处空洞裂隙 | ❌ |
| `GroupMessage:218606013` | 48 | 早晨 | **上午** | 星的房间 / 天衡智库 | ❌ |
| `GroupMessage:1098307480` | 47 | 早晨 | **上午** | 奶茶店 | ❌ |
| `FriendMessage:942361330` | 512 | 早晨 | 早晨 | 了房间 | ✅ |
| `GroupMessage:1090658701` | 498 | 上午 | 上午 | 长空市西侧林区 | ✅ |
| `GroupMessage:702510574` | 62 | 上午 | 上午 | 琪亚娜的房间 | ✅ |
| `GroupMessage:674489689` | 18 | 早晨 | 早晨 | 六楼走廊 | ✅ |
| `GroupMessage:955426627` | 14 | 早晨 | 早晨 | 希露瓦的公寓 | ✅ |
| `FriendMessage:245432630` | 12 | 早晨 | 早晨 | 爱莉希雅的房间 | ✅ |
| `GroupMessage:814560566` | 5 | 早晨 | 早晨 | 海滨步道 | ✅ |
| `GroupMessage:426750065` | 2 | 早晨 | 早晨 | 黄金庭院公寓大厅 | ✅ |

```
玩家当前 zone 与全局时钟：一致 9 / 不一致 14  →  一致率 39%
```

**最刺眼的例子**：`GroupMessage:966162158`（199 回合）——**全局时钟是「早晨」，而玩家「星」正站在一个内容渲染于「深夜」的公寓里**（跨约 4 个时间格）。`GroupMessage:877459692`（408 回合）——全局「早晨」，墨在自己房间里却是「傍晚」。

**这一条精确对应负责人 B4 的原话**：「移动到了不同的区域，我该思考…**时间段切换是否合理**…」。**他无法判断"时间段切换是否合理"，因为全局时钟与他所站房间的时间不一致。**

**语义裁决仍有待析客拍板**（两种读法导致不同的不变量）：
- 若 `zone.time_slice` 语义 = **"当前时间"**（派生不变量）→ 玩家当前 zone **必须**等于全局时钟 → 当前 **39% 一致率 = 缺陷**。
- 若语义 = **"该 zone 内容上次渲染的时间"**（纯缓存）→ 弱不变量为"**不得超前于全局时钟**"，此时落后可接受，但**"站在深夜公寓里而世界是早晨"仍是体验问题**（玩家读到的时间描述与时钟冲突）。

> 两种读法都指向同一个结论：**当前 zone 的时间描述与全局时钟存在大量冲突，而这是玩家能直接感知的。**

### 5.1b 补充：全部 zone 的口径（保留供参考，但**不应作为缺陷判据**）

```
存在 zone 时间切片 与 session 时钟 不一致的会话: 12 / 18  (67%)
zone 层同时存在多个不同时间切片的会话:        12 / 18  (67%)
```
**注意**：此口径包含"未被访问的 zone 保留旧时间"的正常情况，**不能单独用来证明缺陷**。以 §5.1 的 39% 为准。

### 5.2 现象二：全局时钟回退过（`max_*` 列是 reset 的 DB 指纹）

`game_sessions` 同时保留高水位列 `max_day_count` / `max_time_index`。实测 **12 / 18 会话存在 `max_time_index > time_slice_index`**：

| session | 回合 | 当前 day | **max_day** | 当前 ts_idx | **max_ts** |
|---------|------|---------|------------|------------|-----------|
| `FriendMessage:2438094710` | **1062** | 2 | **10** | 1 | 2 |
| `FriendMessage:942361330` | 512 | 1 | **5** | 0 | 1 |
| `GroupMessage:1090658701` | 498 | 1 | **6** | 0 | 2 |
| `GroupMessage:230394566` | 408 | 1 | **4** | 0 | 3 |
| `GroupMessage:877459692` | 408 | 1 | 2 | 0 | 4 |
| `GroupMessage:529384034` | 134 | 1 | 1 | 0 | 4 |

**解读**：`max_*` 是高水位，`current` 被回退 → **这是 `reset` / `forget`（回溯）在 DB 层的可观测证据**，且发生率 **67%**。

### 5.3 为什么这两条合起来很重要

1. **它把 B4 从"玩家的认知负荷"改判为"状态模型本身不自洽"。**
   负责人 B4 原话：「移动到了不同的区域，我该思考在这个区域做什么，**时间段切换是否合理**，是否有新的角色，新角色出现是否合理，我该如何搭话」。
   他不是"想不出时间是否合理"——**是这个世界的时间本身没有一个一致的答案**。当 42 个 zone 里 35 个的时间切片与全局时钟冲突时，"时间段切换是否合理"这个问题在数据上**无解**。
   → **这是确定性状态缺陷，可以在代码里修，且不违反项目规范。**

2. **它解释了负责人为什么如此依赖 `reset` / `forget`。**
   开放问题 5 原话：「目前我几乎没有控制权，只有 reset\forget（回溯一轮重新选择），不手动调用参数」。
   他的**唯一控制杠杆就是回溯**，而实测 67% 的会话都发生过回溯。**回溯很可能正是他用来修正状态不自洽的手段**——即：当世界时间错乱时，他只能倒回去。
   → 这意味着 **`reset`/`forget` 的调用频率是一个高价值指标**，也是"状态可信度"的代理。

3. **它给出了一条此前没被列入任何 P0 的施工项**：统一全局时钟与 zone 时间切片的语义（zone 应记录"上次访问时间"还是"当前时间"？），并让 `reset` 正确回滚 zone 层。

### 5.4 待成员处理

- **析客**：给出时钟语义的统一方案（确定性机制，非叙事判断）；评估 `reset`/`forget` 是否应升级为更细粒度的状态修正工具。
- **路径**：评估"世界时钟一致性"应放在哪个阶段；它是否应取代或补充"好感度二极管"进入 P0。
- **数析**：用 `max_*` 列量化 reset 频率与幅度；验证"回溯是状态修正手段"这一假设（例如：回溯是否集中发生在 zone 时间冲突之后）。
- **竞析**：检索竞品如何处理"多地点时间推进"的一致性（是否有产品用"地点记忆上次到访时间"而非"全局时钟"）。

---

## 6. 主理人新增取证（二）：两处代码级硬证据

### 6.1 ★ C6「好感度二极管」的精确代码根因：行为提示是死代码

负责人 C6 原话：「很容易进入二极管状态，即，最高好感或最低好感（或者负好感）才会有明显区别，**中间状态几乎看不出区别**。」

> **⚠️ §6.1 于本轮后期被精确化（见 §6.1b）。原"三重死代码"的表述不准确——真正致死的只有一处。修复方案因此不同，且"改错地方会白改"。**

**根因已定位（原始表述）：**

```python
# handlers/narrative_package.py:1500-1510
# 2. Behavior hints for affinity stage changes
for entry in exec_result.successful:
    if entry.tool == "update_npc_affinity" and entry.result:      # ← ① 名称错（遗留单数）
        r = entry.result
        if r.get("stage_changed"):                                 # ← ② 该字段无生产者
            package.add_behavior_hint(
                f"{r.get('npc_name','NPC')}的态度从"
                f"「{r.get('old_stage','?')}」变为「{r.get('new_stage','?')}」，"  # ← ③ 字段不存在
                f"请在NPC的表情/语气/行为中自然体现这个变化。"
            )
```

**三重证据（全部可一条 grep 复现）**：

| # | 问题 | 证据 |
|---|------|------|
| ① | **工具名用的是遗留单数形式** | 全库仅此处检查 `"update_npc_affinity"`；而 canonical 工具名是 **`update_npc_affinities`**（复数，见 `main.py` 的 `@filter.llm_tool(name="update_npc_affinities")` 与 `_base.py` 的 `TOOL_SKILL_MAP`） |
| ② | **`stage_changed` 没有任何生产者** | `grep -rn "stage_changed" --include=*.py .` → **全库只有 1 处，就是上面这个读取点**。没有任何地方写入该字段 |
| ③ | **`old_stage` / `new_stage` 不在返回结构里** | `_apply_affinity_for_npc`（`npc_tools.py`）的返回 dict 只有 `stage`，**没有 `old_stage` / `new_stage` / `stage_changed`** |

**结论：这段"把好感度阶段变化翻译成叙事行为提示"的逻辑，在产品历史上从未执行过一次。**

**这精确解释了负责人的抱怨**：好感度变化时，**唯一改变的是 DB 里的一个数字**。叙事层从来没有被告知"她对你的态度阶段变了"，所以中间态自然"看不出区别"——**因为负责让它可见的机制是死的**。

**同一遗留命名的连带影响**（同一个 bug 的另外两处）：

```python
# handlers/intent_supervisor.py:47
_NUMERIC_CLAMPS = {("update_npc_affinity", "delta"): (-25, 25)}
# → ±25 的 delta 钳制对当前的 update_npc_affinities 工具不生效

# handlers/narrative_package.py:175  OPERATIONAL 集合
"update_npc_affinity",     # ← 同样用单数；update_npc_affinities 不在该集合内
```

**修法（确定性，不触碰叙事质量判断，符合项目规范）**：
1. 在 `_apply_affinity_for_npc` 的返回 dict 中补 `old_stage` / `new_stage` / `stage_changed`（比较 `current_aff.stage` 与 `aff.stage`）——**这是纯状态比较，属确定性事件**。
2. 把 `narrative_package.py` 与 `intent_supervisor.py` 的工具名统一为复数 canonical 形式（或同时匹配两者，与 `narrative_package.py:803` 的现有写法保持一致）。
3. 保留 `add_behavior_hint` 的措辞——**"请在 NPC 的表情/语气/行为中自然体现这个变化"是给 LLM 的意图，不是代码级质量判定**，边界正确。

> ⚠️ 注意区分：**生产"阶段变了"这个事实信号**是确定性的（合规）；**判断"叙事是否真的体现了变化"**是非确定性的（不合规）。本修法只做前者。

### 6.1b ★★ 精确化：真正致死的只有 ①，而 ① 并不致死——**"改错地方就白改"陷阱**

复核 `rpg_stats.json`（全 21 会话聚合）时发现一个**推翻上表 ① 的事实**：

```
单数工具 update_npc_affinity   : 调用 191 次，错误 0
复数工具 update_npc_affinities : 调用 969 次，错误 23
```

**单数工具并没有被废弃——它仍在被调用（191 次）**，且注册在 `handlers/tool_executor.py:164`（`{"min_interval_turns": 3, "mode": "accumulate"}`）。

**所以上表 ①「名称错」不成立**：`narrative_package.py:1502` 的 `entry.tool == "update_npc_affinity"` **确实能匹配到真实的工具调用**。

**真正致死的只有 ②**（③ 是"若条件通过会产出垃圾"，不是"致死不执行"）：

```python
# handlers/npc_tools.py:_apply_affinity_for_npc 的实际返回
ret = {
    "entity_id", "npc_name",
    "old_affinity", "new_affinity",          # ← 有：数值
    "delta", "effective_delta", "requested_delta", "clamped",
    "stage",                                  # ← 有：新阶段
    "reason", "shared_with_scene",
}
# 缺：stage_changed / old_stage / new_stage
```

→ `r.get("stage_changed")` **永远返回 `None`** → 条件永假 → **行为提示从未生成** ✓
→ 且即便补上 `stage_changed`，`old_stage`/`new_stage` 仍不存在 → 会渲染出「**?**」变为「**?**」

**这个区别决定修复方案是否有效**：

| 若误判为"名称错" | 实际结果 |
|---|---|
| 把 `:1502` 改名成复数 | ❌ **仍然不工作**——`stage_changed` 依旧无生产者。**白改。** |
| 把 `_apply_affinity_for_npc` 补上 `stage_changed`/`old_stage`/`new_stage` | ✅ **这才是正确的单点修复**（比较 `current_aff.stage` 与 `aff.stage`，纯状态比较） |

**给施工者的警告**：这段代码**看起来像"名字写错了"**，但它不是。**唯一有效的修复点是 `_apply_affinity_for_npc` 的返回结构**。

**连带项仍需修（但性质是"钳制失效/分类缺失"，不是"致死"）**：
- `intent_supervisor.py:47` 的 ±25 钳制只对单数名生效 → **复数工具的 delta 未受钳制**（数析实测：最大单次 delta = **+100**，即"跳顶"未被拦截）
- `narrative_package.py:175` 的 `OPERATIONAL` 集合用单数名 → 复数工具不被归为 operational

### 6.2 ★ P0-3 的展示路径盲区：玩家确实能看到 `<xiaoai_core>`

上一轮我把 P0-3 的根因归为"上下文清理被门控在 5.0 流水线"。**这个结论不完整。** 进一步取证发现**两条独立缺陷**：

**缺陷 A · 展示路径的清理函数不认识 `xiaoai_core`**

```python
# handlers/response_filter.py:66  strip_leaked_thinking()
_CONTENT_OPEN_RE  = re.compile(r"<\s*content\s*>", re.IGNORECASE)        # 只认 <content>
_THINKING_CLOSE_RE= re.compile(r"<\s*/\s*thinking[^\n<]*(?:\n|$)", ...)  # 只认 </thinking
_THINKING_OPEN_RE = re.compile(r"<\s*thinking\s*>", re.IGNORECASE)      # 只认 <thinking>
```
调用点：`hooks.py:1699`（`handle_decorating_result` 链上清理）、`hooks.py:5369`（装饰结果前清理）、`hooks.py:1827`、`hooks.py:5234`。

**该函数只处理 `<content>` 与 `<thinking>` 两类标记。模型若输出 `<xiaoai_core>…</xiaoai_core>` 而不带这两类标记，则 Priority 3「no marker — unchanged」直接原样透传给玩家。**

**缺陷 B · 历史污染（上一轮已定位）**

```python
handlers/hooks.py:3362
    if is_5_0_pipeline and req.contexts:      # 默认流水线是 4.0 → 84% 的回合不清理历史
        internal_cleanup = strip_assistant_internal_scaffolding_from_contexts(req.contexts)
```

**关键补充证据**（`hooks.py:5362-5365` 的作者注释）：

```
# Pipeline note: run_context.messages was populated from the original
# completion_text BEFORE on_agent_done (which triggers this hook), so
# _save_to_history already has the unmodified raw text — our cleaning
# only affects display, not history continuity.
```

→ **展示会被清理，但历史里存的是未清理的原文。** 模型下一轮读到自己的 `<xiaoai_core>` → 模仿 → 累积。这与实测的 **0 → 36 → 55** 单调累积曲线完全吻合。

**修正后的完整图景**：

| 路径 | 是否清理 | 后果 |
|------|---------|------|
| **展示（玩家看到）** | `strip_leaked_thinking`，**但只认 `<content>`/`<thinking>`** | `<xiaoai_core>` **透传给玩家** → 出戏（B2 中"中途出戏"= 4 分） |
| **历史（模型下一轮读到）** | 4.0 流水线下**完全不清理**（门控） | 模型模仿自己的标签 → 会话内累积 |
| **审计 `assistant_preview`** | 记录原始模型输出 | 7.6% 是**模型输出污染率**，不等于玩家可见率（但缺陷 A 使其接近相等） |

**修法**：
1. **让展示路径复用 `cache_guard` 的标记清单**——`cache_guard.py` 已有正确的 15 个标记（含 `xiaoai_core`、`cot`、`thinking`、`监督阶段`…），但**只用于历史清理，没用于展示清理**。让 `strip_leaked_thinking` 调用它即可，这是**一处函数复用**。
2. 移除 `hooks.py:3362` 的 `is_5_0_pipeline` 门控（上一轮已给出）。

> **两条修法互不替代**：修 1 解决"玩家看到"，修 2 解决"模型自我污染"。只修任一条，问题都会以另一种形式复发。

---

## 7. 待成员复核/补充的开放点

- 瑞思：3.2 的归因重写是否正确？「想消费一个写好的世界」与"每回合写 65 字散文"如何共存？
- 数析：单玩家回合数能否更精确拆分？reset 痕迹能否从 DB 观测到？C6 好感度二极管能否用 `npc_player_affinity.value` 分布证实？
- 析客：D1 旅程（无机制）与现有 49 个工具的对齐度；C6 的机制改造方案。
- 路径：无流式前提下的替代方案；"建造者持续性"的机制建议；P0 优先级按 D5 重排。
- 竞析：「消费型世界 + 关系养成」是否存在于竞品；C6 与记忆召回（7 分）的偷师对象。

---

## 8. ★★ 主理人自我更正（三）：不是"zone 落后"，是**多个时间源互相不同步**

> **⚠️ 本节含两次自我更正。§8.1–8.7 是第一次（把口径从"一个字段"升级为"三个源"）；§8.8 是第二次（**§8.2 对 `get_current_time_slice_for_player` 的指控是错的**，且基线应改用 C==Z 56.5%）。以 §8.8 为准。**
> 保留完整更正链是有意的——它记录了本会话第 4、5 次同类错误的发生与纠正方式。

### 8.1 触发这次复查的原因

路径在 r2 稿 §4.3 断言：「预生成的 zone 若携带生成时刻的时间戳，命中后会在缓存里固化一个过期时间切片——这正是世界时钟不自洽的**制造机**。」

这是一个**可证伪的强断言**。我去验证它时发现：`time_snapshots` 确有 2 个活跃读取站点（非死代码），但**更重要的是我在追这条线时发现我 §5.1 的对比基准选错了**。

### 8.2 我原先的口径错在哪

§5.1 我用 **`game_sessions.current_time_slice`** 当"全局时钟"。但复核 `handlers/zone_tools.py:211-218` 后发现，`move_to_zone` 读的根本不是它：

```python
# handlers/zone_tools.py:211-218
current_scene = await self.ctx.state.get_active_scene_for_player(session_id, player.entity_id)
if current_scene:
    time_slice = current_scene.time_slice          # ← scene 层优先
else:
    time_slice = await self.ctx.state.get_current_time_slice(session_id)   # ← session 层兜底
```

**即：权威时钟在 `scenes` 层，`game_sessions.current_time_slice` 只是兜底。** 我用兜底值当权威，等于拿错了标尺。

### 8.3 三层全量普查（23 个 session×player，无一遗漏）

数据源：`game_sessions.current_time_slice`（S）/ `scene_members` JOIN `scenes.time_slice`（C）/ `zones.time_slice`（Z）。
脚本：`_r2_scripts/lead_three_clock2.py`

```
S(session) == C(scene)  :  6/23 = 26.1%
C(scene)   == Z(zone)   : 13/23 = 56.5%
S(session) == Z(zone)   :  9/23 = 39.1%      ← 这正是 §5.1 的 39%
scene.local_id == player.current_local_id : 23/23 = 100.0%
```

**解读**：

1. **`scene.local_id == player.current_local_id` 100% 成立** → 架构本身是"玩家在一个 scene 里，scene 绑定一个 zone"，绑定关系**没有坏**。所以问题**不是**"zone 记录漂移"。
2. **`S == C` 只有 26.1%** → **session 层时钟与 scene 层时钟在 74% 的情况下不一致**。
3. 39% 只是 S 与 Z 的偶然吻合率，**它的成因是 S 与 C 本来就不一致**。

### 8.4 结构性根因：会话级单值时钟 × 多玩家

`game_sessions.current_time_slice` 是**会话级单值**（`database.py:135`），而时间实际是**scene 级**（每玩家一个 scene）。

**最刺眼的对照（同一会话、两个玩家、同一时刻）**：

| 会话 | 玩家 | S(session) | C(scene) | Z(zone) | 三层是否自洽 |
|---|---|---|---|---|---|
| `GroupMessage:966162158`（199 回合） | 技术支持——哈吉博 | 早晨 | **深夜** | **深夜** | ❌ S 与 C/Z 分裂 |
| `GroupMessage:966162158`（同上） | 墨 | 早晨 | 早晨 | 早晨 | ✅ 全一致 |

**同一个群、同一时刻，一个玩家的三层全一致，另一个玩家三层分裂。** 这不是"某个字段没更新"能解释的——**session 级单一 `time_slice` 字段在结构上就无法同时表达两个玩家各自的场景时间**。

再看 `GroupMessage:1097436019`：星 S=深夜/C=午休/Z=上午；墨 S=深夜/C=上午/Z=早晨。**四个时间值同时存在。**

### 8.5 修正后的定性（这才是 P0 的正确表述）

> ❌ 旧表述（我 §5.1）："玩家当前 zone 与全局时钟一致率 39%"——把"三个源不同步"降级成了"一个字段落后"。
>
> ✅ 新表述：**时间状态存在三个独立可写的时间源（`game_sessions.current_time_slice` / `scenes.time_slice` / `zones.time_slice`），代码不同路径读写不同的源，且其中一个是会话级单值、无法表达多玩家各自的场景时间。**
> - `move_to_zone` 读 **C**、写 **Z**（经 `update_zone_volatile`）与 **C**（经 scene）
> - `query_current_zone` 返回 **C** 的 `time_slice`，但 `environment_desc` 来自 **Z**（`zone_tools.py:87-97`）→ **一次工具返回内就可能是撕裂组合**
> - `get_current_time_slice_for_player()`（`state_machine.py:3630-3637`）**忽略 player 参数**，直接返回会话级值——**名字承诺了 per-player，实现是 per-session**

### 8.6 对 P0 的两个直接后果

**后果 1：修复点从"同步两个字段"升级为"确立单一时间源"。**
路径的 §4.3 缓存论断**因此更强**：缓存之所以危险，正是因为**没有一个权威时间源可供缓存 key 参照**——`time_snapshots` 是按"某一个源的时间"存的，而读取时可能用另一个源去命中。

**后果 2：不变量 A 必须重新表述（我给路径的版本不够强）。**

> **不变量 A（修正版）**：**任一时刻，对任一玩家，`scenes.time_slice`（该玩家成员 scene）、`zones.time_slice`（该 scene 绑定的 zone）、以及 `game_sessions.current_time_slice`（若保留该字段）必须表达同一个时间切片。**
> **基线：S==C 26.1% / C==Z 56.5% / S==Z 39.1% → 目标：三层全部 100%。**

**额外结论**：`game_sessions.current_time_slice` 作为**会话级单值在多玩家会话里语义不成立**。析客的 Q1 裁决必须包含"这个字段是否应当被废弃/降级为缓存"。

### 8.7 口径边界（必须声明）

- n=23 是 **session×player 行数**，不是独立玩家数（独立玩家 3 人 + 1 个测试小号 `{小桃子}`/`小夏`/`a宝` 等），**样本极小**。
- 上述全部是**终态快照**，不是时序。它证明"终态不一致"，**不**证明"不一致持续了多久"。
- 该结论**不依赖**任何叙事质量判断，纯属确定性状态（符合纪律第 4 条）。

---

### 8.8 ★★ 二次自我更正：我的 §8.2 指控是错的；基线应改用 **C==Z 56.5%**

析客交付了时钟语义裁决（四层模型）。我逐条复核它的代码引用后，**发现我自己在 §8.2 里犯了一个错误**，必须撤回。

#### 8.8.1 我错在哪（本会话第 5 次同类错误）

§8.2 我写：「`get_current_time_slice_for_player()`（`state_machine.py:3630-3637`）**忽略 player 参数**，直接返回会话级值——函数名承诺 per-player，实现是 per-session。」

**这是错的。** 我当时的依据是 `grep` 输出的**单行**（`:3637 return await self.get_current_time_slice(session_id)`），没读完整函数体。实际代码：

```python
# core/state_machine.py:3630-3637  —— 完整函数
async def get_current_time_slice_for_player(self, session_id: str, player_entity_id: str) -> str:
    scene = await self.get_active_scene_for_player(session_id, player_entity_id)
    if scene:
        return scene.time_slice          # ← L1 优先，per-player 正确实现
    return await self.get_current_time_slice(session_id)   # ← 无 scene 才兜底
```

**它确实是 L1 优先的 per-player 实现，是正确的。** 析客的裁决在这一条上成立，我的指控不成立。
→ **错误模式仍是"用单点观测（grep 单行）代替全量阅读（完整函数）"，本会话第 5 次。**

#### 8.8.2 但我的普查数字全部有效——只是解读要换

析客指出"39% 的参照系错了"（对），但它把三个数字一并视为无效。**复核后我认为三个数字各自有效，只是对应三个不同的缺陷**：

| 数字 | 实际含义 | 是否有效 |
|---|---|---|
| **S==C 26.1%** | **L3 僵尸字段的冻结程度**——`advance_scene_time` 停止写 L3 后，L3 与权威 L1 的偏离 | ✅ **有效**，量化缺陷 A |
| **C==Z 56.5%** | **L4（`zones.time_slice`）与权威 L1 的真实一致率** | ✅ **有效且最重要**，量化缺陷 B |
| S==Z 39% | L3 vs L4（僵尸字段 × 漂移戳叠加），**参照系错误** | ❌ **弃用** |

#### 8.8.3 复核结论：L3 不是"死字段"，是"僵尸字段"（更危险）

析客称 L3（`game_sessions.current_time_slice`）为"遗留全局时钟"。我验证了 `_sync_world_clock`（`state_machine.py:3602-3617`）——**它只写 `max_time_slice`/`max_time_index`/`max_day_count`，确实不写 `current_time_slice`**。所以"写入已停止"成立。

**但"停止写入"≠"停止读取"。全库仍有 7 处非兜底读取点**：

```
handlers/zone_tools.py:430     ts = gs.get("current_time_slice", "")     # move_to_zone 内
handlers/zone_tools.py:463     new_time = await ...get_current_time_slice(session_id)
handlers/hooks.py:2179         ts = gs.get("current_time_slice", "")
handlers/commands.py:703       ts = gs.get("current_time_slice", "")
handlers/progression_tools.py:105
workflows/camp.py:106
core/state_machine.py:2564-2568  (getter 本体)
```

→ **任何走到这些路径的调用都会拿到一个冻结在某个历史时刻的时间值。** 这比"死字段"（无读取）**危险得多**，因为缺陷是静默的：没有异常、没有日志、值看起来是合法的中文时间词。

#### 8.8.4 复核确认：`move_to_zone` 的顺序缺陷成立（析客发现，我已验证）

```python
# handlers/zone_tools.py
:216   time_slice = current_scene.time_slice        # ← 取「移动前」时间
:257   zone = await scene_generator.get_or_create_zone(..., time_slice=time_slice, ...)
                                                     # ← 用它物化/刷新目标 zone 的 volatile 字段
:453   if active_scene and time_cost > 0 and location_changed:
:455       new_time = await self.ctx.state.advance_scene_time(...)   # ← 之后才推进时间
```

**先物化（用旧时间）→ 后推进（到新时间）** → 新到达的 zone 里，`environment_desc` 是**移动前时间**生成的，而玩家此刻的权威时间是**推进后**的。**这是缺陷 B（C==Z 仅 56.5%）的制造机。**

**附带发现（析客未提）**：`:453` 的门控含 `location_changed`——**同一 zone 内推进时间（`time_cost>0` 但 location 不变）不会推进时间**。即"在同一地点等待/休息"这一叙事动作**在机制上无效**。这可能是一个独立的体验缺陷。

#### 8.8.5 修正后的 P0 时钟项（三条并列的确定性缺陷）

| # | 缺陷 | 性质 | 基线 | 修法 |
|---|---|---|---|---|
| **A** | **僵尸字段 L3**：`game_sessions.current_time_slice` 写入已停、仍有 7 处读取 | 确定性 | L3 vs L1 = 26.1% | 删除该字段及全部读取点，或改为从 L1 派生 |
| **B** | **zone 渲染戳漂移**：`zones.time_slice` 与权威 L1 不一致 | 确定性 | **C==Z = 56.5%** | 确立 L1 为单一权威；L4 降级为可空的渲染戳 |
| **C** | **`move_to_zone` 先物化后推进** | 确定性 | 机制已确证 | 调整顺序：先推进 scene 时间 → 再用新时间物化 zone |

**唯一有效的"世界时钟不一致"基线是 C==Z = 56.5%**（不是 39%，不是三层加权）。

---

## 9. 主理人新增取证（四）：P0-4 工具错误的**极端集中**构成

数据源：`rpg_stats.json` 全 21 会话聚合（**注意：本地文件 mtime = 2026-07-04，为本地快照，不含服务器端 07-04 之后的增量**）。

```
总调用 5374   总错误 118   错误率 2.20%
46 个不同工具中，只有 4 个报错 → 这 4 个承担 100% 的错误
```

| 工具 | 调用 | 错误 | 错误率 | **占全部错误** |
|---|---:|---:|---:|---:|
| `mark_npc_evolution_trigger` | 570 | 57 | 10.0% | **48.3%** |
| `sync_zone_npcs` | 204 | 24 | 11.8% | **20.3%** |
| `update_npc_affinities` | 969 | 23 | 2.4% | **19.5%** |
| `generate_npcs` | 117 | 14 | 12.0% | **11.9%** |
| **合计** | | **118** | | **100.0%** |

### 9.1 三条结论

1. **错误不是"系统普遍不稳"，而是 4 个特定工具的确定性缺陷。**
   46 个工具里 42 个**零错误**——包括调用量最大的 `log_npc_interactions`（984 次）、`move_to_zone`（412 次）、`mark_interacting_npcs`（396 次）。所以"2.2% 错误率"这个聚合数字是**误导性的**：它掩盖了"4 个工具在结构性失败"这一事实。

2. **4 个工具全部属于 NPC 物化与状态同步域**（进化触发器 / zone NPC 同步 / 好感度 / NPC 生成）。
   → 与负责人 D5「在乎的是**角色还原度**」直接冲突：**失败最集中的地方，恰好是他最在乎的能力。**

3. **`update_npc_affinity`（单数，191 次 0 错误）与 `update_npc_affinities`（复数，969 次 23 错误）并存。**
   → 这是 §6.1b 的证据来源，也是**"遗留命名未清理"的第三个独立后果**：不仅 `stage_changed` 逻辑失效，`intent_supervisor` 的 ±25 钳制也**只保护了单数版本**，复数版本的最大单次 delta 达 **+100**（数析实测）。

### 9.2 对 P0 的影响

- P0-4 的表述应从"NPC 域工具错误"**收窄为"4 个具名工具的确定性缺陷"**（可施工、可验证）。
- `mark_npc_evolution_trigger` 一项就占 **48.3%** 的错误，且 570 次调用中 57 次失败（10%）——**单点最高杠杆**。
- 这三个发现（§6.1b 的命名连带、§9 的钳制失效、§9 的错误集中）**共享同一个根因：遗留单数命名未随复数工具迁移而清理**。它们应当作为**一个需求项**处理，而不是三条。

---

## 10. ★★★ 决定性闭环：`get_time_info()` 把 L3 僵尸值**直接注入 LLM 上下文**

> **这一节是时钟缺陷的完整机制闭环。它同时解释了负责人 B4，并把缺陷等级从"状态不一致"提升为"LLM 上下文污染"。**
> **来源：析客发现该中枢，我验证并扩展。**

### 10.1 代码事实

```python
# core/state_machine.py:2631-2642
async def get_time_info(self, session_id: str) -> dict:
    """Get full time info for LLM context injection."""          # ← docstring 自证用途
    gs = await self.db.get_game_session(session_id)
    if not gs:
        return {"time_slice": "", "day_count": 1, "time_slices": []}
    preset = await self._load_session_preset(session_id)
    time_slices = self._get_time_slices(preset)
    return {
        "time_slice": gs.get("current_time_slice", ""),          # ← ★ 裸读 L3 僵尸字段
        "day_count": gs.get("day_count", 1) or 1,                # ← 同为 L3 列
        "time_slices": time_slices,
    }
```

**13 个调用点**（析客称为"14 处"，我实测 13 处）：

| 调用点 | 性质 |
|---|---|
| **`prompt/assembler.py:321`** | ★ **LLM 上下文组装** |
| **`prompt/assembler.py:668`** | ★ **LLM 上下文组装** |
| **`prompt/assembler.py:853`** | ★ **LLM 上下文组装** |
| **`handlers/router_context.py:246`** | ★ **Router 上下文** |
| **`handlers/narrative_package.py:1354`** | ★ **叙事包** |
| `core/life_engine.py:383` | 生活引擎 |
| `handlers/commands.py:491` | 命令 |
| `handlers/npc_tools.py:2179` | NPC 工具 |
| `handlers/player_tools.py:274` | 玩家工具 |
| `handlers/progression_tools.py:106` | 成长 |
| `handlers/zone_tools.py:518` / `:705` / `:719` | zone 工具 |

### 10.2 为什么这比我原先的"7 处业务读取点"严重得多

我原先的计数（§8.8.3）是 **grep `current_time_slice` 字面量**得到的——**因此漏掉了这个中枢**。`get_time_info` 是一个**包装层**，13 个调用点**不出现该字面量**。

**我在此更正 §8.8.3 的计数**：

> ❌ 旧："7 处非兜底业务读取点"
> ✅ 新："**1 个中枢（`get_time_info`）+ 13 个调用点**，其中 **5 个直接进入 LLM 上下文**（prompt assembler ×3 / router_context / narrative_package）"

### 10.3 完整机制闭环（这就是"全局早晨，我站在深夜的公寓里"的成因）

```
                    ┌─ L1 scenes.time_slice ────── 权威（advance_scene_time 写）
                    │                              ↓
   move_to_zone ────┤                    zone_tools.py:216 取「移动前」L1
                    │                              ↓
                    │                    :257 用它物化 zone → 写入 L4 zones.time_slice
                    │                              ↓
                    └─ :455 才 advance_scene_time（推进到新时间）
                                                   ↓
                                          ★ L4 停留在「移动前」时间

   与此同时 ────────→ get_time_info() 裸读 L3（冻结值）
                              ↓
                    prompt/assembler.py:321/668/853 ──→ ★ 注入 LLM 上下文
                    router_context.py:246          ──→ ★ 注入 Router 上下文
                    narrative_package.py:1354      ──→ ★ 注入叙事包
```

**同一次生成里，LLM 收到的三份时间信息互不相同**：
1. **L3**（`get_time_info` → prompt）——**冻结在某个历史时刻**
2. **L1**（scene 权威）——真实当前时间
3. **L4**（zone 描述里的时间词）——**移动前**的时间

**→ LLM 被告知"现在是早晨"，同时读到一份写着"深夜"的 zone 描述。** 它无法判断哪个是真的，只能二选一或含糊处理。**负责人的 B4「时间段切换是否合理」不是他的错觉，是 LLM 面对的输入本身就是矛盾的。**

### 10.4 修正后的缺陷 A 与施工方案（采纳析客方案）

**缺陷 A（僵尸字段）的正确表述**：

> `game_sessions.current_time_slice` 写入已停，但其值通过 **`get_time_info()` 中枢**（13 个调用点，含 **5 个 LLM 上下文注入点**）**持续污染模型上下文**。

**施工方案（析客提出，我确认这是最优解）**：

| 方案 | 评价 |
|---|---|
| ❌ 逐个修改 13 个调用点 | 脆弱、易漏、未来新增调用点会复发 |
| ✅ **改 `get_time_info()` 本体为 scene-aware**（增加 `player_entity_id` 参数，内部走 L1；保留无参重载做兜底） | **单点修复中枢**，13 个调用点自动受益；符合"改根因不改症状" |

**验收标准**（可执行）：
1. `get_time_info` 返回值在**有活动 scene** 时 == 该玩家 L1 的 `time_slice`
2. `grep -rn "current_time_slice"` 的结果中，**不再出现业务读取**（仅剩 schema / 迁移 / getter 兜底）
3. **回归观测**：随机抽 50 轮，LLM 上下文的 `time_slice` 与 zone 描述的 `time_slice` **同源**（可加审计字段验证）

### 10.5 独立复现记录（交叉验证）

| 观测者 | 口径 | 结果 |
|---|---|---|
| 主理人 | `zones.time_slice` vs `scenes.time_slice`（L4 vs L1），23 个 session×player | **13/23 = 56.5%** |
| 数析 | 同口径独立重测（`_r2_scripts/clock_*.py`） | **13/23 = 56.5%** ✅ 一致 |
| 主理人 + 数析 | 旧口径 `zones` vs `game_sessions.current_time_slice`（L4 vs L3） | 9/23 = 39.1%（**已弃用**） |

**两人独立复现同一数字** → 56.5% 可采信。数析补充：旧口径的 L1≠L3 分叉率高达 **73.9%**，即 39% 里混入了大量与 zone 无关的噪声。

### 10.6 口径边界

- n=23 为**终态快照**，不是逐回合；只能给"最终状态一致率"，**不能给"每回合错位率"**。
- 但**结构成因是确定性的**：每次 `time_cost≥1` 的换地点移动**必然**盖旧时间戳（数析代码确证）。
- 置信度：**中**（一致率）/ **高**（结构成因）。

---

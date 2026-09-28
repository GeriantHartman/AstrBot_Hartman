# Agentic RPG 插件 · P0 施工清单（代码级）
## 从「诊断」到「可施工」：8 个已定位、可验证、带行号的缺陷

**日期**：2026-09-18
**类型**：功能规格书（施工清单附录，承接 `product-diagnosis-agentic-rpg-2026-09-18.md`）
**参与成员**：方向明（主理人，编排 + 现场取证）、数析（Metric，指标口径）、竞析（Compa，对标基线）
**代码基线**：`plugins/astrbot_plugin_agentic_RPG/`（runtime 与 source 镜像同哈希）

---

> ## 🛑 勘误（2026-09-18 第二轮追加）
>
> **本清单的 8 项中有 2 项已被证伪、1 项被取代、3 项口径需修正。请以第二轮终稿为准：**
> **`deliverables/product-strategy/prd-agentic-rpg-2026-09-18.md`**
>
> | 本清单项 | 状态 | 说明 |
> |---|---|---|
> | **P0-8「一回合要等 60 秒」/「3 小时纯等待是物理原因」** | ❌ **证伪** | 实测工具等待仅 **2.7 秒/回合**（`move_to_zone` 只覆盖 **10.7%** 的回合；全量加权：102min+75min ≈ 177min / 3931 回合）。**266 秒/回合是人机循环周期**（含玩家阅读+构思+打字），**不是系统延迟**。→ 结论应改为「门槛是最小单位 20 分钟专注创作」 |
> | **「流式输出是最高杠杆修复」** | ❌ **证伪** | 负责人明确：**基于消息平台特点，流式传输不可用**。→ 替代方案：占位信号 + 两段式模板 + zone 预生成缓存 |
> | **世界时钟相关项（若有）** | ⚠️ **被取代** | 第二轮确立**四层时间模型**（L1 `scenes.time_slice` 权威 / L2 `max_*` 高水位 / **L3 `current_time_slice` 僵尸字段** / L4 `zones.time_slice` 派生戳）。**唯一有效基线是 L4 vs L1 = 56.5%**（主理人与数析独立复现一致）。旧口径「39%」与「67%」均作废 |
> | **P0-3 `<xiaoai_core>` 泄漏** | ✅ **成立** | provider 决定泄漏率（0% vs 26.1%）+ `hooks.py:3362` 门控——**两条通道均确认**，已进入第二轮 P0-1 |
> | **埋点配对泄漏（47/50 工具、171 早退站点）** | ✅ **成立** | 已确认为延迟字段不可信的根因 |
> | **契约冲突（`contract_pipeline.py:243` vs `rpg-style-core/SKILL.md:241`）** | ⚠️ **成立但方向反转** | 第二轮发现：**编号选项合规率仅 44.9%**，而负责人给"想接下来说什么"打 4 分 → **"不合规"（55.1%）才是玩家要的纯叙事**。→ 优化方向应改为**移除强制菜单契约**，而非提高合规率 |
> | **风格占比 94.6% vs 5.4%（机制工具错配）** | ✅ **成立且被强化** | 第二轮：49 个工具中仅 **~16 个**服务真实循环 |
>
> **另**：本清单的 `user_hash` 相关项已在第一轮勘误中修正（它是 **prompt 内容哈希**，非身份）。
>
> **P0 项数变化**：本清单 8 项 → 第二轮收敛为 **4 项确定性缺陷**（`<xiaoai_core>` / 单一时间源 + 清 L3 僵尸字段 + `move_to_zone` 顺序 / 好感度死代码 / 4 个具名 NPC 工具）。

---

## 📌 TL;DR（执行摘要）

- **本轮把上一版报告的 P0 结论全部落到了具体文件与行号**，产出 8 条可直接开工的施工项，其中 3 条附带可复现的验证脚本。
- **最重要的新发现（推翻上一版的一个数字）**：`rpg_stats.json` 里的延迟字段**大部分是假的**。AST 扫描证实 **47/50 个 LLM 工具函数存在 `_tool_enter` / `_tool_exit` 配对泄漏，共 171 个早退站点，3 个函数完全没有 `_tool_exit`**。会话 `GroupMessage:2895848` 显示 `update_npc_affinities` 平均 **210 秒/次**，而同一工具在另外 11 个会话里只有 **24–60 毫秒**——这不是性能问题，这是埋点缺陷。
- **但真实等待仍然存在，且已精确定位**：`move_to_zone`（420 次，跨全部 16 个会话一致地 10–28 秒/次）与 `generate_npcs`（117 次，0.4–30 秒/次）是**真实的 LLM 等待**，两者合计约 **3 小时纯等待**。这才是"下班后不想打开"的物理原因。
- **契约冲突已坐实**：`contract_pipeline.py:243` 要求"必须追加 3-4 个编号选项"，而 `skills/rpg-style-core/SKILL.md:241` 写着"不机械强制每轮菜单化"。两个注入点在互相抵消——这解释了 44.9% 的合规率。
- **P0-3 已当场结案**：`<xiaoai_core>` 泄漏确认为「**发出脏**」（存在全程零泄漏的会话，排除"记录脏"）。泄漏率**完全由 provider 决定**——GPT-5.5 系列 / deepseek-reasoner 为 **0%**，`siliconflow` 上的 DeepSeek-V3.2 高达 **26.1%**。根因是 `handlers/hooks.py:3362` 把上下文清理**门控在非默认的 5.0 流水线上**，导致占 84% 的 4.0 回合永不清理历史 → 标签被模型模仿并累积。**修法是一行。**
- **决定性交叉验证**：审计台账 `style` 分布显示 **nsfw + daily + relationship = 94.6%**，而 **story + combat + intrigue + commission = 5.4%**。产品的 26 个机制工具，瞄准的是那 5.4%。
- **一句话**：**产品不是"功能太多"，而是"计量它的仪表本身坏了"。** 你无法优化你看不见的东西——而你现在看到的数字有一大半是错的。

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| 推荐方案 | 先修仪表（P0-1/2/6），再修冲突（P0-3/4），最后收敛（P0-5/7/8） |
| 优先级 | P0（本轮 8 项全部为 P0，其中 P0-1/2 是前置阻塞项） |
| 预期影响 | 修完 P0-1/2 后，才能第一次回答"一回合到底多久"；修完 P0-5 后工具面从 49 收敛至 ~12 |
| 资源需求 | P0-1/2/6 约 1 人日；P0-3/4 约 1 人日；P0-5/7/8 需产品决策后再动 |
| 风险等级 | **中**（P0-1 修改 `_base.py` 核心埋点，影响全部 50 个工具，必须回归） |

---

## 0. 本轮取证方法与可复现性

所有数字均由**只读脚本**在本地快照上重算，未修改任何生产文件。三条口径：

| 口径 | 数据源 | 可信度 | 用途 |
|------|--------|--------|------|
| 回合总量 | `world_*.db` → `game_sessions.interaction_count` | **权威，无截断** | 只用于"总共玩了多少" |
| 工具调用/错误 | `rpg_stats.json` → `sessions[*].tools[*]` | count/error **可信**；**latency 不可信**（见 P0-1） | 只用于调用量与错误率 |
| 管线内容 | `llm_audit_index/*.jsonl`（2682 条，17 会话） | 可信，但**仅覆盖 narrator 阶段**（见 P0-6） | 用于风格分布、泄漏率 |

> ⚠️ **口径纪律**：本轮明确**不**使用 `llm_audit/`（单会话封顶 10 个 json）与 `rpg_stats.json` 的 `turns`（封顶 120）作为总量依据。任何"玩家玩到 X 就停"的推论都必须回到 `interaction_count` 复核。

---

## 1. 工具调用全景（可信口径）

```
总工具调用 5743 次   总错误 118 次   错误率 2.05%
```

### 1.1 错误分布：100% 集中在 4 个 NPC 域工具

| 工具 | 调用 | 错误 | 错误率 | 平均延迟 |
|------|------|------|--------|----------|
| `mark_npc_evolution_trigger` | 570 | 57 | **10.0%** | 191 ms |
| `sync_zone_npcs` | 208 | 24 | **11.5%** | 43 ms |
| `update_npc_affinities` | 969 | 23 | 2.4% | （失真） |
| `generate_npcs` | 117 | 14 | **12.0%** | 38.4 s |
| **其余 45 个工具** | 3879 | **0** | **0%** | — |

**读法**：这不是"错误率有点高"。这是**错误在拓扑上完全集中在 NPC 域**——45 个工具零错误，4 个工具贡献了全部 118 次失败。

**根因**：这 4 个工具都吃 **JSON 数组字符串**参数。作者已经在 `zone_tools.py:761-769` 显式写了类型校验和"不要直接传 list"的提示——**这条错误提示的存在本身就是证据**：作者知道 LLM 传不对，于是加了一句提示语，而不是改参数形态。

```
handlers/zone_tools.py:761-769
    if not isinstance(arrive_npcs, str) or not isinstance(leave_npcs, str):
        return tool_err(
            "sync_zone_npcs 参数类型错误：arrive_npcs / leave_npcs 必须是字符串。"
            '请传 JSON 数组字符串，例如 arrive_npcs="[\\"爱莉希雅\\"]"，不要直接传 list。',
            ...)
```

> 注意这违反了 `AGENTS.md` 第 10 条：**代码不应做非确定性判断**。但这里的判断是确定性的（类型校验），所以合规。真正的问题是**用提示语去补参数设计**——这属于产品设计缺陷，不是代码缺陷。

### 1.2 延迟：先看"真实"，再看"失真"

**真实的、跨会话一致的等待**：

| 工具 | 调用 | 各会话平均延迟区间 | 判定 | 累计真实等待 |
|------|------|-------------------|------|-------------|
| `move_to_zone` | 420 | **10.0 – 28.0 秒**（全部 16 会话一致） | ✅ 真实（LLM 场景生成） | **≈ 102 分钟** |
| `generate_npcs` | 117 | 0.4 – 30 秒 | ✅ 真实（LLM 生成 NPC 卡） | **≈ 75 分钟** |
| `log_npc_interactions` | 984 | 39 – 79 毫秒 | ✅ 真实（纯记账） | ≈ 1 分钟 |
| `sync_zone_npcs` | 208 | 13 – 64 毫秒 | ✅ 真实（纯记账） | ≈ 9 秒 |
| `update_npc_affinities` | 969 | **24–60 毫秒（11 个会话）** | ✅ 真实 | ≈ 1 分钟 |

**失真的**：

| 会话 | 工具 | 调用 | 报告平均延迟 | 判定 |
|------|------|------|-------------|------|
| `GroupMessage:2895848` | `update_npc_affinities` | 106 | **210,371 ms（3.5 分钟）** | ❌ 假数据 |
| `GroupMessage:5293840` | `update_npc_affinities` | 10 | 18,139 ms | ❌ 假数据 |
| `FriendMessage:243809` | `update_npc_affinities` | 153 | 15,409 ms | ❌ 假数据 |
| `FriendMessage:243809` | `generate_npcs` | 9 | **276,506 ms（4.6 分钟）** | ❌ 假数据 |

**证据链**：同一个 `update_npc_affinities`，在 `GroupMessage:2895848` 是 210 秒，在 `GroupMessage:1090658` 是 60 毫秒。**同一个函数、同一份代码、同一个数据库**，相差 3500 倍。这不是性能问题——`_apply_affinity_for_npc`（`npc_tools.py:631-753`）里**没有任何 LLM 调用**，只有三次 DB 写入（`update_player_affinity` / `update_character_status` / `record_visible_event`）。60 毫秒才是真相。

**这个假数据是怎么产生的**——见 P0-1。

---

## 2. P0 施工清单（8 项）

### 🔴 P0-1 · `_tool_enter` / `_tool_exit` 配对泄漏（**前置阻塞项**）

**现象**：171 个早退分支泄漏挂起的开始时间戳，导致下一次调用测出的是**两次调用之间的墙钟时间**。

**AST 全量扫描结果**：

```
调用 _tool_enter 的 LLM 工具函数总数 : 50
其中存在泄漏早退分支的函数         : 47   ← 94%
泄漏早退分支站点总数               : 171
完全没有 _tool_exit 的函数         : 3
```

泄漏最严重的前 6 个函数：

| 文件 | 函数 | 早退分支数 |
|------|------|-----------|
| `story_hook_tools.py` | `manage_story_hook` | 11 |
| `area_story_tools.py` | `publish_area_story` | 8 |
| `combat_trade_tools.py` | `execute_trade` | 8 |
| `zone_tools.py` | `sync_zone_npcs` | 8 |
| `npc_tools.py` | `generate_npcs` | 7 |
| `mirror_mechanics_tools.py` | `choose_reward` | 6 |

**根因代码**（`handlers/_base.py:816-873`）：

```python
# _tool_enter  —— 写入开始时间戳（单槽位，每次覆盖）
handlers/_base.py:828
    self.ctx._tool_start_ts.setdefault(session_id, {})[tool_name] = perf_counter()

# _tool_exit  —— 弹出时间戳
handlers/_base.py:867-872
    if start_session:
        start = self.ctx._tool_start_ts.get(start_session, {}).pop(name, None)
        if start is not None:
            elapsed_ms = (perf_counter() - start) * 1000.0
```

**泄漏路径实证**（`handlers/npc_tools.py`）：

```
518  async def update_npc_affinities(...)
533      self._tool_enter("update_npc_affinities", ...)   ← 写入时间戳
541      return tool_err("玩家不在任何区域")                ← ❌ 早退，未清理
546      return tool_err("updates 不能为空")               ← ❌ 早退，未清理
552      return tool_err(f"updates 必须为 JSON 数组: {e}")  ← ❌ 早退，未清理
554      return tool_err("updates 必须为非空 JSON 数组")    ← ❌ 早退，未清理
626      self._tool_exit("update_npc_affinities", ...)     ← 唯一清理点
```

当第 546 行早退时，时间戳留在 `_tool_start_ts[session]["update_npc_affinities"]`。**下一轮** LLM 再调这个工具时，`pop` 出来的是**上一轮**的时间戳 → `elapsed_ms` = 两轮之间的真实间隔（可能几分钟）。

**修法（二选一，推荐 A）**：

**A. 改为上下文管理器（推荐，一次修 171 个站点）**
```python
# handlers/_base.py  新增
from contextlib import asynccontextmanager

@asynccontextmanager
async def tool_span(self, name: str, session_id: str | None = None,
                    *, source: str = "llm", **kwargs):
    self._tool_enter(name, session_id=session_id, source=source, **kwargs)
    try:
        yield
    finally:
        self._tool_exit(name, "", session_id=session_id, source=source)
```
> 注意：`_tool_exit` 需要接收结果文本以提取错误。改造时把 result 通过一个可变容器传出，或在 `finally` 中从 `self.ctx._last_tool_result` 取。

**B. 最小侵入修法（只堵漏，不改 47 个函数）**
在 `_tool_enter` 里记录**代际序号**，`_tool_exit` 校验代际：
```python
# _tool_enter 中
self.ctx._tool_start_ts.setdefault(session_id, {})[tool_name] = (perf_counter(), turn_seq)
# _tool_exit 中：若代际不匹配，丢弃该样本而不是记入统计
```
这样假数据不会进入 `rpg_stats.json`，但**不解决"为什么这么多早退"**——而早退本身（LLM 传错参数）才是产品问题。

**验收标准**：
1. 重跑 AST 脚本，泄漏站点数 = 0
2. 用同一批数据重算，`update_npc_affinities` 在**全部**会话的延迟落在同一数量级（预期 30–80 ms）
3. `rpg_stats.json` 中不存在 `avg_latency_ms > 60000` 的非 LLM 类工具

---

### 🔴 P0-2 · `_tool_exit` 跨会话错配（**前置阻塞项，双用户下必现**）

**根因代码**（`handlers/_base.py:861-866`）：

```python
start_session: str | None = session_id
if not start_session:
    for sid, pending in self.ctx._tool_start_ts.items():
        if name in pending:
            start_session = sid          # ← 命中任意会话，first-match wins
            break
```

**为什么在你的场景里是 P0**：你有 **2 位真实玩家**（可能 3 位）。当某个调用点没传 `session_id`，而两位玩家**同时**调了同一个工具，那么玩家 A 的开始时间会被玩家 B 的退出消费掉 → A 记成"超长等待"，B 记成"零等待"。

**修法**：`session_id` 改为**必填**参数；无 `session_id` 时**不记录延迟样本**（而不是猜）。同时给 `_tool_exit` 加一条断言日志，在 `session_id` 缺失时 `rpg_debug` 打点，跑一周后统计还有哪些调用点没传。

**验收标准**：`rpg_stats.json` 中任一工具在**同一时刻**的并发会话不产生交叉样本（可用构造测试验证）。

---

### 🟠 P0-3 · `<xiaoai_core>` 内部思考块泄漏 7.6%

**实测**（`llm_audit_index/*.jsonl`，2682 条 narrator 记录）：

```
assistant_preview 含内部标记: 204 / 2682 = 7.6%   ← 下界（preview 被截断）
标记分布: {'xiaoai_core': 202, 'cot': 1, 'thinking': 1}
response_error: 178 / 2682 = 6.6%
```

**清理逻辑已存在但没兜住**：

```python
handlers/cache_guard.py:238   def strip_assistant_internal_scaffolding(text) -> tuple[str, bool]
handlers/cache_guard.py:64    正则覆盖: xiaoai_core(?:_cot)?|cot|chain_of_thought|reasoning|
                              analysis|thinking|supervision|supervisor|监督阶段|...|自检阶段
handlers/hooks.py:3363        调用点 A: strip_assistant_internal_scaffolding_from_contexts(...)
handlers/hooks.py:4640-4642   调用点 B: recovered, _ = strip_assistant_internal_scaffolding(recovered)
handlers/hooks.py:4778-4780   调用点 C: return strip_assistant_internal_scaffolding(text)
```

### ✅ 已解决：泄漏是「发出脏」，且已定位到根因与修法

**原计划排查三个假设。实测后**：**假设 1（记录脏）排除，假设 3（响应侧未清理）成立，并额外发现真正的放大器——上下文清理被门控在非默认流水线上。**

#### 证据一：假设 1 排除——存在零泄漏会话

按会话时间序三等分，统计各段泄漏数：

| session | 条目 | 前 1/3 | 中 1/3 | 后 1/3 |
|---------|------|--------|--------|--------|
| `FriendMessage:942361330` | 338 | 0/112 | **36/112** | **55/114** ← 单调累积 |
| `FriendMessage:2438094710` | 358 | 0/119 | **47/119** | 2/120 |
| `GroupMessage:966162158` | 200 | **24/66** | 8/66 | 0/68 |
| `GroupMessage:289584858` | 200 | **0/66** | **0/66** | **0/68** |
| `GroupMessage:1098307480` | 63 | 0/21 | 0/21 | 0/21 |

**`289584858` 与 `1098307480` 全程零泄漏** → 记录链路**有能力记录干净文本**，因此 7.6% 不是系统性的"记录脏"。假设 1 排除。

**`942361330` 呈 0 → 36 → 55 单调上升** → 这是**上下文污染累积**的典型曲线：标签一旦进入历史，模型开始模仿，随后自我放大。

#### 证据二：泄漏率 100% 由 provider 决定（决定性）

| provider | 调用 | 泄漏 | 泄漏率 |
|----------|------|------|--------|
| `siliconflow/Pro/deepseek-ai/DeepSeek-V3.2` | 261 | 68 | **26.1%** |
| `google_gemini/gemini-3.5-flash` | 1051 | 115 | **10.9%** |
| `deepseek/deepseek-v4-pro` | 92 | 8 | 8.7% |
| `google_gemini/gemini-3-flash-preview` | 143 | 11 | 7.7% |
| `专用/gemini-3.1-pro-preview` | 133 | 7 | 5.3% |
| `deepseek/deepseek-v4-flash` | 640 | 4 | **0.6%** |
| `deepseek_disable_think/deepseek-v4-pro` | 118 | 0 | **0.0%** |
| `deepseek/deepseek-reasoner` | 99 | 0 | **0.0%** |
| `反代/gpt-5.5` / `codex/gpt-5.5` / `GPT/gpt-5.5` | 122 | 0 | **0.0%** |
| （小样本，n<10）`openai/mimo-v2.5` / `gemini-3.1-flash-lite` / `lm_studio/Qwen3.5-9B` | 10 | 6 | 60% |

**全部 GPT-5.5 变体、deepseek-reasoner、deepseek_disable_think 均为 0%；`siliconflow` 上的 DeepSeek-V3.2 高达 26.1%。**

**结论**：`<xiaoai_core>` 不是产品的格式缺陷，而是**特定模型的输出习惯**。你的产品把"不要输出内部标签"的希望寄托在正则清理上，但真正的变量是**模型选择**。

#### 证据三：根因——上下文清理被门控在非默认流水线（可一行修复）

```python
handlers/hooks.py:3362
    if is_5_0_pipeline and req.contexts:                        # ← 门控！
        internal_cleanup = strip_assistant_internal_scaffolding_from_contexts(
            req.contexts
        )
```

配置默认值（`_conf_schema.json`）：

```
enable_4_0_contract_pipeline            default = True    ← 默认流水线
enable_5_0_router_supervisor_default    default = False
```

审计台账实测：`response_meta` 含 `router_supervisor_5` 的条目 **432 / 2682 = 16.1%**。

**即：84% 的回合跑在 4.0 流水线上，而 4.0 流水线永远不会清理上下文里的内部标签。** 标签留在历史里 → 模型模仿 → 累积（`942361330` 的 0→36→55 曲线正是此机制）。5.0 流水线反而有清理——**清理逻辑装在了非默认路径上**。

#### 修法（两处，均低成本）

**① 移除流水线门控（一行）**
```python
# handlers/hooks.py:3362
# 改前：if is_5_0_pipeline and req.contexts:
if req.contexts:
```
使 4.0 与 5.0 都清理上下文。这是根因修复。

**② 模型侧规避（配置层，零代码）**
按泄漏率排序，把叙事主模型固定在 `GPT-5.5` 系列 / `deepseek-reasoner` / `deepseek-v4-flash`（0%–0.6%），避免 `siliconflow` 上的 DeepSeek-V3.2（26.1%）。

> 注意：这与 P0-4 的结论**同源**——18 个 provider 混用导致契约与格式都无法稳定。**模型选择本身就是一个产品决策，不是环境细节。**

**验收标准**：改后随机抽 50 轮，泄漏率 < 0.5%；且分 provider 统计中，原 26.1% 的 provider 降到 < 5%。

---

### 🟠 P0-4 · 契约自相矛盾：两个注入点在互相抵消

**冲突双方**：

```
handlers/contract_pipeline.py:243
  "RPG 场景的最终回复末尾必须追加 3-4 个方括号编号选项，格式如 [1] 去XX [2] 检查YY [3] 询问ZZ；..."

handlers/contract_pipeline.py:259
  "不得用 NPC 的反问、沉默、邀请、物件递出或自然留白替代结尾编号选项；
   自然开放位和 [1] [2] [3] 选项必须同时存在。"

handlers/router_supervisor_5.py:426
  "末尾必须追加 3-4 个方括号编号选项，例如 [1] 去XX [2] 检查YY [3] 询问ZZ。"

handlers/router_supervisor_5.py:428
  open_slot="在本轮动作已经结算后，留下 3-4 个玩家下一轮可直接执行的编号选项。"

             ⇕  ← 直接冲突
skills/rpg-style-core/SKILL.md:241
  "不机械强制每轮菜单化，但不能连续多轮封闭结尾。..."

skills/rpg-style-daily/SKILL.md:36
  "**日常的选项**：即便是轻松的日常场景，回复的最后也要给出 3-4 个选项..."
```

**这是"合规率 44.9%"的结构性解释**：契约层说"必须"，风格层说"不要机械强制"。两个都是注入到同一个 prompt 的指令，LLM 收到的是**矛盾指令** → 遵守率自然对半开。

**更深一层（本轮新增洞察）**：审计台账显示 **18 个不同 provider** 被混用：

| Provider | 调用数 | 占比 |
|----------|--------|------|
| `google_gemini/gemini-3.5-flash` | 1051 | 39.2% |
| `deepseek/deepseek-v4-flash` | 640 | 23.9% |
| `siliconflow/.../DeepSeek-V3.2` | 261 | 9.7% |
| `google_gemini/gemini-3-flash-preview` | 143 | 5.3% |
| `专用/gemini-3.1-pro-preview` | 133 | 5.0% |
| `deepseek_disable_think/deepseek-v4-pro` | 118 | 4.4% |
| `deepseek/deepseek-reasoner` | 99 | 3.7% |
| 其余 11 个 | 237 | 8.8% |

**同一个硬契约 + 18 个异质模型 = 契约必然失效。** 每个模型对"必须追加编号选项"的遵循度不同，对"不要机械菜单化"的理解也不同。这同时解释了 44.9% 的选项合规率与 7.6% 的 `<xiaoai_core>` 泄漏——**它们是同一个根因的两个症状**。

**修法**：
1. **裁决单一事实源**：把"是否菜单化"的最终裁决权收到契约层，`rpg-style-core/SKILL.md:241` 改为引用契约而非另立规则（或反之）。**不允许两处都定义。**
2. **按 provider 分层验收**：契约改动后，分 provider 统计合规率（预期会发现 Gemini 系与 DeepSeek 系差异显著）。若某 provider 长期不达标，**在配置层固定主模型**，而不是继续调 prompt。

**验收标准**：单次改动后，随机抽 50 轮，编号选项合规率 ≥ 85%；且分 provider 统计中，最低 provider 与最高 provider 差距 < 20pp。

---

### 🟠 P0-5 · 工具清单瞄准的是 5.4% 的场景（**产品决策项，非代码项**）

**决定性交叉验证**（本轮新增，来自审计台账 `style` 字段）：

| style | 轮次 | 占比 |
|-------|------|------|
| `nsfw` | 1271 | **47.4%** |
| `daily` | 1050 | **39.2%** |
| `relationship` | 215 | 8.0% |
| **小计（亲密 / 日常 / 关系）** | **2536** | **94.6%** |
| `story` | 95 | 3.5% |
| `combat` | 43 | 1.6% |
| `intrigue` | 6 | 0.2% |
| `commission` | 2 | 0.1% |
| **小计（剧情 / 战斗 / 阴谋 / 委托）** | **146** | **5.4%** |

**对照工具清单**：产品的 49 个 LLM 工具中，**26 个属于机制域**——`combat_trade_tools`、`mirror_mechanics_tools`（8 个）、`progression_tools`（光锥/等级/委托）、`area_story_tools`。

**这 26 个工具瞄准的是 5.4% 的游玩时间。**

而且这不是新结论——它和产品**自己的**画像数据完全一致：`player_tendency_summary` 11 份中 **9 份**写着"回避战斗 / 冲突 / 严肃剧情"。

**产品自己的数据在两次独立测量中都指向同一个答案，而工具清单押在反方向。**

**修法**：见上一版报告 §5 的三阶段路线图。本清单只补一条**施工级**要求：
- 收敛顺序必须是 **先隐藏、后删除**。先通过 `CONFIG_SWITCH_SPECS`（现 30 个开关，覆盖 94 个配置项）把 26 个机制工具**默认关闭**，观察 4 周。
- **判据**：若关闭后 `style` 分布中 nsfw/daily/relationship 占比不降反升（预期上升），且无玩家投诉缺失，则执行删除。
- **禁止**：一次性删除。你的产品已经有 2 位真实玩家，删除是不可逆的信任损伤。

---

### 🟡 P0-6 · 审计台账只覆盖 `narrator` 阶段（**可观测性缺口**）

**实测**：

```
审计条目 total = 2682   会话数 = 17   response_error = 178
stage 分布: {'narrator': 2682}     ← 100% 只有 narrator
```

**后果**：Router 决策、Director 编排、Contract 组装**全部没有审计**。这意味着：

- 无法回答"Router 这轮为什么调了这 5 个工具"
- 无法回答"Contract 注入了什么"
- 无法回答"哪个阶段最慢"

**你之所以需要外部团队来诊断自己的产品，直接原因就是这个。** 你手上有 2682 条 narrator 记录，却没有任何一条 router 记录——而 Router 才是决定"这轮发生什么"的地方。

**修法**：给 `stage` 增加 `router` / `director` / `contract` 三个取值，复用现有 `llm_audit_index` 写入路径。**注意保持 `llm_audit_max_files_per_session`（默认 200）的封顶逻辑，但索引层不要封顶**——否则又会制造一个"看起来停摆了"的假象（这正是本会话早期踩过的坑）。

**验收标准**：新增一轮游戏后，`llm_audit_index` 中出现 ≥ 3 种 `stage` 取值。

---

### 🟡 P0-7 · 参数形态脆弱：JSON 数组字符串

**证据**：见 §1.1——118 次错误 **100%** 集中在这 4 个吃 JSON 数组字符串的工具上。

**修法**：把 `arrive_npcs: str` / `leave_npcs: str` / `updates: str` 改为**结构化参数**，让工具签名自己承载类型约束，而不是靠 docstring 提示语。若框架限制只能用字符串，则在 `main.py` 的 `@filter.llm_tool` 包装层做**统一容错解析**（而不是在每个工具里各写一遍 `_parse_names`）。

**现状是重复实现**：`zone_tools.py:772-786` 有一个 `_parse_names`，`npc_tools.py:543-554` 又有一套双重解码逻辑。**同一个问题两套解法**。

**验收标准**：这 4 个工具的错误率 < 1%。

---

### 🟡 P0-8 · 真实等待税（**本节结论已按实测修正**）

> **⚠️ 本节原结论"一回合的墙钟时间轻松超过 60 秒"是未经测量的推断，现予更正。** 以下是实测数字。

#### 已证实的部分：`move_to_zone` 的 10–28 秒是真实 LLM 生成

```python
handlers/zone_tools.py:257-262
    zone = await scene_generator.get_or_create_zone(
        ...
        llm_generate_fn=self.ctx.context.llm_generate,   # ← 真实 LLM 调用
    )
```

`move_to_zone` 在**全部 16 个会话**中都是 10–28 秒，**跨会话一致**，且代码路径确实调用 `llm_generate` → **这是真实的世界生成耗时，不是埋点失真**（与 P0-1 的假数据性质不同）。

```
default:FriendMessage:245432    n=121  avg=  9994 ms
default:FriendMessage:243809    n= 61  avg= 12634 ms
default:GroupMessage:1090658    n= 38  avg= 18237 ms
default:GroupMessage:1098307    n= 14  avg= 27995 ms   ← 最慢
```

#### 修正：单回合平均工具等待 ≈ 2.7 秒，不是 60 秒

```
真实工具总等待 ≈ 102 分钟（move_to_zone）+ 75 分钟（generate_npcs） ≈ 177 分钟
权威回合总数 = 3931
→ 平均 2.7 秒 / 回合
```

**分布高度集中**：`move_to_zone` 调用 420 次 / 3931 回合 = **10.7% 的回合**。即：

- **约 89% 的回合**：工具等待接近 0（记账类工具 24–80 毫秒）
- **约 11% 的回合**：额外承担 10–30 秒的生成等待

**所以「每回合都要等一分钟」不成立。** 真实体验是"大多数回合很快，换场景时突然卡 20 秒"。

#### 实测的完整人机循环：中位数 266 秒 / 回合

用审计 `created_at` 计算相邻回合的真实墙钟间隔（n=2352，剔除跨天）：

| session | 中位间隔 | 均值 | p90 | <5 秒占比 |
|---------|---------|------|-----|-----------|
| `FriendMessage:2438094710` | 219 s | 329 s | 551 s | 0.0% |
| `GroupMessage:1090658701` | 279 s | 450 s | 877 s | 0.0% |
| `FriendMessage:942361330` | 279 s | 455 s | 906 s | 0.0% |
| `GroupMessage:909871205` | 464 s | 699 s | 1508 s | 0.0% |
| `GroupMessage:218606013` | 529 s | 698 s | 1515 s | 0.0% |
| **全部合计** | **266 s** | **437 s** | **893 s** | **0.0%** |

> ⚠️ **这个 266 秒不能读作系统延迟。** 它包含玩家的**阅读时间 + 构思时间 + 打字时间**（玩家输入中位数 65 字）。**工具等待只占其中 2.7 秒。**
>
> **它测的是"人机循环周期"，不是"系统响应时间"。** 把它当延迟报告会是本会话反复纠正的同一类错误。

**但 0.0% 的回合在 5 秒内完成**这一点是真实的信号：**这是一项慢速、需要专注的活动，不是可以随手点两下的东西。**

#### 修正后的结论：真正的门槛是"最小单位 20 分钟"，不是"等待 60 秒"

玩家每回合投入约 **4.4 分钟**（中位）专注的阅读 + 写作。因此：

> **"下班后玩一会儿" 的最小可行单位 ≈ 4–5 回合 ≈ 20 分钟的高度专注创作。**

**这解释了为什么"下班后没动力"——不是系统慢，而是这项活动的最小单位是 20 分钟的集中创作，而不是 5 分钟的消遣。** 疲惫时缺的不是耐心，是**专注力**。

这与主报告的"形态错配"结论**一致**：产品是一件**慢速、严肃、需要持续投入的创作工具**，而不是可以碎片化进入的游戏。它服务得很好——1062 回合的玩家相当于投入了约 **78 小时**。

#### 修法（优先级已按修正后结论重排）

| 措施 | 原定位 | **修正后定位** |
|------|--------|--------------|
| 流式输出 | 让等待变成阅读 | **仍然最高杠杆**——把 11% 的卡顿回合从"死等"变成"边生成边读" |
| 场景预生成 / 缓存 | 减少等待 | **降级**——只影响 10.7% 的回合，不是主要矛盾 |
| `move_to_zone` 降频 | 减少等待 | **改判为体验问题**：`zone_tools.py:113-124` 的 docstring 写了"家内分区不要调"，但实测 420 次调用说明 Router 没遵守。**这是"世界感被打断"的问题，不是"等待"的问题。** 仍回到 P0-6：没有 Router 审计就无法知道它为什么不遵守。 |

> **新增待确认**：本节的 266 秒是**玩家侧**循环周期。**系统侧**的单回合耗时（Router + 工具 + Narrator 的墙钟总和）**仍未测量**——因为审计只记录 narrator 阶段且没有回合级计时（见 P0-6）。补齐后应重测本节。

---

## ✅ 行动清单

| # | 行动 | 负责方 | 依赖 | 时间窗 |
|---|------|--------|------|--------|
| 1 | 修 `_tool_enter`/`_tool_exit` 配对（P0-1）：改上下文管理器或加代际校验，清零 171 个泄漏站点 | 工程 | — | 第 1 周 |
| 2 | 修跨会话错配（P0-2）：`session_id` 改必填，缺失时不记样本 | 工程 | #1 | 第 1 周 |
| 3 | 补齐 `stage` 审计（P0-6）：新增 router/director/contract | 工程 | — | 第 1 周 |
| 4 | ~~验证 P0-3 假设 1~~ **已完成**：泄漏为「发出脏」，根因是 `hooks.py:3362` 把上下文清理门控在 5.0 流水线 | 工程 | — | ✅ 已结 |
| 4b | 移除 `hooks.py:3362` 的 `is_5_0_pipeline` 门控，使 4.0 也清理上下文 | 工程 | #4 | 第 1 周 |
| 4c | 按泄漏率重排 provider：固定叙事主模型到 0%–0.6% 档（GPT-5.5 / deepseek-reasoner / deepseek-v4-flash） | 产品 | #4 | 第 1 周 |
| 5 | 裁决契约单一事实源（P0-4）：消除 contract 与 style skill 的菜单化冲突 | 产品 + 工程 | — | 第 2 周 |
| 6 | 按 provider 分层统计编号选项合规率，定位最差 provider | 工程 | #5 | 第 2 周 |
| 7 | 统一参数容错解析（P0-7）：抽公共解析层，消除两套 `_parse_names` | 工程 | — | 第 2 周 |
| 8 | **仅隐藏不删除**（P0-5）：用 config switch 默认关闭 26 个机制工具，观察 4 周 | 产品 | — | 第 3 周起 |
| 9 | 评估流式输出可行性（P0-8）——最高杠杆的体验改动 | 工程 | — | 第 3 周 |
| 10 | 4 周后复盘：若 nsfw/daily/relationship 占比上升且无投诉 → 执行删除 | 产品 | #8 | 第 7 周 |

---

## ⚠️ 待确认 / 假设 / Non-goals

### 待确认（阻塞决策）
1. **P0-3 假设 1 的判定结果**——决定泄漏是真问题还是假警报。**在此之前不要动手改正则。**
2. **18 个 provider 的混用是刻意的还是搜索性的？** 若为刻意（按场景选模型），则契约需分模型版本化；若为搜索性（"总在找一个能用的"），则应固定主模型——这本身就是一个产品决策。
3. **两位玩家的模型是否相同？** 审计有 `user_hash`，可进一步拆分。若两位玩家跑在不同模型上，那么"44.9% 合规率"是两个不同数字的平均值，会掩盖更严重的单侧问题。
4. 上一版报告 A–G 组诊断问题中，**E1（形态裁决）**与 **E4/G2（第二用户是否知道有机制）** 仍未回答。

### 本清单的假设
- 假设 `rpg_stats.json` 的 `count` / `error_count` 字段可信（本轮已交叉验证：与 `interaction_count` 口径无冲突）。**延迟字段明确不可信**。
- 假设审计 `style` 字段反映真实游玩形态。**注意**：`style` 是每轮被选中的风格标签，而非玩家主观意图，因此 94.6% 是"系统认为的形态"，不是"玩家想要的形态"。但结合产品自证画像（9/11 份回避战斗），两者互证。
- 假设 `move_to_zone` 的 10–28 秒是 LLM 生成耗时而非网络/DB 阻塞。**未验证**——建议在 P0-6 补齐 stage 审计后复测。

### Non-goals（本清单明确不做）
1. **不做** 26 个机制工具的直接删除——只做默认关闭 + 4 周观察。
2. **不做** 正则/关键词级别的叙事质量门禁（违反 `AGENTS.md` 第 10 条）。P0-4 的修法是**消除矛盾**，不是**增加检查**。
3. **不做** 本地快照到服务器的数据同步或迁移。
4. **不做** 新增任何功能。本轮全部为减法与修表。
5. **不修改** `llm_audit_max_files_per_session` 的默认值（200）——它造成的截断是已知的，改它需要单独评估磁盘影响。

---

## 📚 数据来源 & 成员产出索引

### 本轮新增取证（全部只读）
| 取证 | 方法 | 产出 |
|------|------|------|
| 工具错误率分布 | `rpg_stats.json` 全量聚合 | 5743 调用 / 118 错误 / 100% 集中于 4 个 NPC 工具 |
| 工具延迟失真 | 按会话拆分 `avg_latency_ms` | `update_npc_affinities` 24ms ↔ 210371ms 的 3500 倍差异 |
| enter/exit 泄漏 | **AST 全量扫描** `handlers/**/*.py` | 47/50 函数泄漏、171 站点、3 函数无 exit |
| 内部标记泄漏 | `llm_audit_index/*.jsonl` 正则统计 | 204/2682 = 7.6%（下界），`xiaoai_core` 占 202 |
| 风格分布 | 同上，`style` 字段聚合 | 亲密/日常/关系 94.6% vs 机制类 5.4% |
| provider 分布 | 同上，`provider_id` 字段聚合 | 18 个 provider，头部集中度 39.2% |
| stage 覆盖 | 同上，`stage` 字段聚合 | 100% 为 `narrator` |

### 成员产出索引
- **析客（需求分析师）**：`_parts/requirement-analyst.md`——六层功能地图、221 个功能面折算、P0/P1/P2 砍留清单、10 个保留工具、StarterKit 设计、六步迁移路径、8 条 Non-goals
- **瑞思（用户研究员）**：`_parts/user-researcher.md`——双重身份绞杀、SDT 诊断、"导演姿态反关联"、认知负荷错配、A–G 组 45 题
- **竞析（竞品分析师）**：`_parts/competitive-analyst.md`——7 类竞品实时检索、"哑铃形赛道 + 中档空白"、功能对比矩阵、SWOT、3 个可偷师设计
- **数析（数据分析师）**：`_parts/data-analyst.md`——功能 ROI 四层分层、CDI 计算、权威口径重算（附G）、用户身份签名（附H）
- **路径（路线图规划师）**：`_parts/roadmap-planner.md`——三病因裁决、三阶段路线图（Gate 1/2/3）、RICE 评分、B=MAP 拆解、三个关键行为动作

### 代码引用索引
| 文件 | 行号 | 内容 |
|------|------|------|
| `handlers/_base.py` | 816-873 | `_tool_enter` / `_tool_exit` 埋点实现（P0-1/2 根因） |
| `handlers/_base.py` | 861-866 | 跨会话 first-match 逻辑（P0-2 根因） |
| `handlers/_base.py` | 892-960 | `_accumulate_tool_stats` |
| `handlers/npc_tools.py` | 518-629 | `update_npc_affinities`（4 个泄漏早退点） |
| `handlers/npc_tools.py` | 631-753 | `_apply_affinity_for_npc`（无 LLM 调用，证明 60ms 才是真相） |
| `handlers/zone_tools.py` | 103-136 | `move_to_zone` docstring（P0-8） |
| `handlers/zone_tools.py` | 761-769 | 类型校验 + "不要直接传 list"提示（P0-7 证据） |
| `handlers/zone_tools.py` | 772-786 | `_parse_names` 实现（P0-7 重复实现之一） |
| `handlers/contract_pipeline.py` | 243, 259 | 编号选项硬契约（P0-4 冲突方 A） |
| `handlers/router_supervisor_5.py` | 426, 428 | 编号选项硬契约（P0-4 冲突方 A'） |
| `skills/rpg-style-core/SKILL.md` | 241 | "不机械强制每轮菜单化"（P0-4 冲突方 B） |
| `skills/rpg-style-daily/SKILL.md` | 36 | 日常场景也要 3-4 选项 |
| `handlers/cache_guard.py` | 238-273 | `strip_assistant_internal_scaffolding`（P0-3） |
| `handlers/cache_guard.py` | 63-76 | 内部标记正则定义 |
| `handlers/hooks.py` | 3363, 4640, 4778 | 清理函数三个调用点 |
| `handlers/hooks.py` | 3463-3471 | 新手引导（仅一句话） |
| `core/config_switch_registry.py` | 12-25 | `ConfigSwitchSpec`（30 个开关） |
| `_conf_schema.json` | — | 94 顶层键 / 98 可设项 |

---

> 本报告由产品战略团队 AI 协作生成，重要决策请由产品负责人审定。
> **本清单的所有代码行号基于 2026-09-18 的本地快照**；服务器部署版本若已超前，请以服务器代码为准重新定位。

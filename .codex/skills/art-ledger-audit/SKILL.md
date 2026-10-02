---
name: art-ledger-audit
description: 审计 AstrBot Art 剧作家插件的 LLM 审计账本。用于离线判断 art 每轮的效果是否符合预期：逐轮检查编剧（playwright）的导演笔记是否真实生成还是走了兜底、演员（actor）实际收到的 prompt 与清洗前后的回复、书记（scribe）的抽取与落库副作用；诊断 provider 解析失败、核心 Skills/工具说明泄漏进演员提示词、审计目录不生成等静默故障，并给出改哪个源文件的 diff。不用于改动游戏的数值或状态机设计。
---

# Art 审计账本离线审计

## 这个 skill 解决什么

art 一轮对话里有 **3 次 LLM 调用**（编剧 / 演员 / 书记），但玩家只能看到演员的输出。编剧是否降级、书记是否什么都没做、演员的提示词里是否混进了不该有的东西——**从玩家侧完全看不出来**。审计账本是唯一能看见内部的地方，也是"效果是否符合预期"的唯一判据。

把它当作离线审计智能体使用。**不要**向正在进行的 RP 会话发消息，也**不要**把 `/art` 命令当成审计流程的一部分。读账本，判断问题落在哪一层，然后提出普通文件 diff。

## 工作流

1. **先读索引，不要先读全文**。索引每轮一行，便宜；完整文档里单是演员的 `system_prompt` 就有 8k 字符。

   ```bash
   python .codex/skills/art-ledger-audit/scripts/index_summary.py --limit 20
   ```

   它给出 `turn_id` / `preset` / `model` / 玩家与回复的短预览 / 健康标记（`ERR`、`FALLBACK:*`、`CLEANED:*`、`PARSE_FAIL`）。看完就知道该打开哪几轮。

2. **按轮读详情**，一次只开需要的轮：

   ```bash
   python .codex/skills/art-ledger-audit/scripts/turn_detail.py --turn <turn_id>
   python .codex/skills/art-ledger-audit/scripts/turn_detail.py --chars 1200   # latest
   ```

   默认截断长文本；确有必要才 `--full`。

3. 定位问题后，按「修复落点映射」改对应的源文件，并说明每处改动对应哪条账本证据。

4. 字段含义不确定时读 `references/ledger_schema.md`，不要靠猜。

## 三个调用点各自的审计口径

一轮的三份文档共享同一个 `turn_id`，必须**一起看**：编剧的产出是演员的输入，演员的回复是书记的输入。只审计演员的文风会漏掉上游。

### 编剧 `playwright` — 先看它有没有真的跑

**首要问题是"是否降级"，不是文风。**

- `response.meta.is_fallback` 为 `true` → 本轮导演笔记是写死的兜底文本，演员根本没得到剧情指导。查 `fallback_reason`：
  - `no_provider` → provider 解析失败，见「诊断模式 A」
  - `exception` → `response.error` 里有异常文本
  - `empty_completion` → 模型返回空
- `assembly_trace.provider_source` 应为 `config` / `selected_provider` / `session`，**为 `none` 即失败**
- `response.meta.tool_trace` 是本轮编剧实际调用的工具（`change_scene` / `cast` / `recall` / `fix_character`）。为 0 条是正常的——只有场景/角色结构变化时才该有调用
- 兜底文本固定为 `"[导演笔记]\n- 积极接住玩家的话题，推进日常互动。"`，见到这句即判定降级

真实导演笔记应满足（对照 `prompts/playwright.yaml`）：
- 只写事件层，**不含台词、不含心理独白**（那些属于演员）
- 明确体现「提议归角色、决定归玩家」——例如"她只提议，不擅自挪动，把决定权留给玩家"
- 变数落地到场景，而不是阻断交流
- 钩子/心愿推进能与 `audit_view.mid_scripts`、`short_hooks` 对上

### 演员 `actor` — 提示词卫生 + 文风

**先查提示词卫生，再评文风。**

- **`audit_view.stripped_sections` 必须非空**，通常为 `['skills_inventory', 'tool_call_prompt', 'computer_use_workspace']`。为空即说明核心注入没被剥离，会诱发幻觉工具调用（见「诊断模式 B」）
- `system_prompt` 长度：剥离正常时约 8k 字符量级（Persona + art 协议）。若明显更大（如 15k+），先怀疑剥离失效
- `has_dynamic_block` 必须为 `true`，否则 Layer 2（场景/角色卡/账本/导演笔记）没注入
- `response.meta.cleaned` / `chars_stripped`：`response.text` 是**清洗前**原始输出，`cleaned_preview` 是玩家看到的版本。两者差异大时，说明模型在漏思考标记或英文元推理
- 文风对照 `prompts/actor.yaml`（写作质量核心协议）与 `Design Invariants`：
  - **绝不代替玩家做决定、说台词、承诺、表达立场**；结尾应把决定权留在玩家手里
  - 不许出现 `[1][2][3]` 编号选项
  - 不许标签化感官罗列（视觉/听觉/触觉…）
  - `【】` 内容必须无条件服从

### 书记 `scribe` — 抽取质量与落库

- `response.meta.parsed_ok` 为 `false` → 本轮抽取被整体丢弃，`parse_error` 里有原因
- `response.meta.writes[]` 是**本轮真实落库的副作用**。为空但 `parsed_ok` 为 `true`，说明本轮确实没有值得记的细节（正常），或字段提取全为空（可疑）
- 逐条核对 `writes` 与 `parsed` 是否一致——`parsed` 说有 `shared_memory` 但 `writes` 里没有，说明落库分支漏了
- **硬规矩**：承诺与告白只能来自玩家原话。`parsed.confirmed_promise` 若来自演员回复中的"你答应过"，是 bug（对照 `prompts/scribe.yaml`）
- 书记**没有任何确定性抽取兜底**，所以 `no_provider` 意味着整轮书记工作量为零

## 诊断模式

### A. 编剧每轮都是兜底笔记 / 书记长期没有 `writes`

**症状**：编剧文档 `is_fallback=true`、`provider_source="none"`；书记 `error="no_provider"`；但演员正常出话。

**成因**：编剧与书记**不走 AstrBot 主管线**，必须自己解析 provider。若解析链失效，两者都拿不到模型，只有走主管线的演员不受影响。

**必须先检查的**（历史上踩过的坑）：审计代码里是否还在用这两个**不存在**的 API——
- `event.chat_provider`（`AstrMessageEvent` 没有这个属性）
- `star_context.get_current_chat_provider(event)`（`Context` 没有这个方法）

它们抛的 `AttributeError` 会被 `except` 吞掉，表现为静默降级而非报错。

**正确做法**：统一走 `core/provider_resolver.resolve_provider(star_context, event, configured_id=...)`，顺序为
`playwright_provider`/`scribe_provider` → `selected_provider` extra → `get_using_provider(umo)`。

**若仍解析不到**：该会话在 AstrBot 里没选定对话模型（`get_using_provider` 返回 None），属配置问题。

### B. 正文里冒出工具调用、`SKILL.md` 路径或 `<｜DSML｜>` 标记

**症状**：`response.text` 里是 `<｜DSML｜> invoke name="bash"> type "...SKILL.md"` 之类的工具调用；`cleaned=false`、`chars_stripped=0`（清洗函数不认这类泄漏）。

**成因**：AstrBot 核心在**插件 hook 之前**就把 Skills 清单（列出全部 skill 及其文件路径，并指示"执行前必须先用 shell 命令读取 SKILL.md"）与 `TOOL_CALL_PROMPT`、工作区绝对路径写进了 `req.system_prompt`。演员被 `func_tool = None` 摘掉工具，无法照做，只能把那条命令当正文吐出来。

**判据**：`audit_view.stripped_sections` 为空。

**修复**：`layers/assemble.py` 的 `strip_actor_forbidden_sections()` 负责剥离，标记常量从核心 import（`astr_main_agent_resources.TOOL_CALL_PROMPT` 等）。核心改文案不会静默失效；**新增**别的工具类注入不会被自动覆盖，升级后要复查。

### C. 审计目录不生成

`llm_audit/` 与 `llm_audit_index/` 是**首次写入时惰性创建**的——插件加载只构造 ledger 对象，不落盘。依次确认：

1. `enable_llm_audit_ledger` 为 `true`（这是**插件配置开关**）
2. 插件确实被启用——注意 `data/cmd_config.json` 的 `plugin_set` 是**处理器级白名单**，与 WebUI 插件页的卡片开关是**两套独立机制**；卡片开着不代表 handler 会执行。日志里看 `enabled_plugins_name` 是否含 `astrbot_plugin_art`
3. 该会话确实跑过至少一轮：已 `/art start`，且发过一条**被唤醒**的消息
4. 消息确实唤醒了机器人——中文输入法默认输出全角 `～`（U+FF5E），若 `wake_prefix` 只有半角 `~`（U+007E），`startswith` 字面比较失败，事件在 `WakingCheck` 阶段被 `stop_event()` **静默丢弃**，日志表现为 `WakingCheck` 之后直接 `pipeline 执行完毕`、耗时几毫秒、无任何 provider 调用

### D. 账本长期不增长 / 关系记忆缺失

访问审计文件之前先确认**本轮书记是否真的跑了**（见诊断模式 A）。若书记在跑但 `writes` 长期为空，问题在 `prompts/scribe.yaml` 的抽取字段设计，而不是账本。

### E. 编剧在跑，但剧情时间线/场景对不上

演员演到了编剧没排的地点或时段（例如导演笔记写"午后回廊"，正文写"夜里""路灯"）。

**先查工具是否真的成功过**，不要先改提示词。

- 判据：playwright 文档的 `response.meta.tool_trace` 里，`change_scene` / `cast` 是否**从未**出现过 `ok=True`
- 若全程 `ok=None` 或错误里带 `AttributeError`：检查 `main.py` 的 `_build_playwright_toolset` 四个闭包**首参是不是 `event`**。核心固定以 `handler(event, **kwargs)` 调用（`astrbot/core/astr_agent_tool_exec.py`），首参写业务参数会让工具在"漏传"和"传了"两种情形下**都必失败**——而编剧会静默降级，玩家侧看不出异常，只能从审计发现
- 连带检查 `result_preview` 是否含原始异常文本：若含，多半已被编剧抄进导演笔记（见下）
- 另查角色是否真的进过 `[cast]`：`cast` 失败时新角色只是导演笔记里的"黑户"，演员却会照着演

### F. 导演笔记里出现工具报错原文或"已尝试调用…"的过程说明

**成因**：工具信封携带原始异常（`f"...失败: {e}"`），进入编剧上下文后被原样抄进笔记，再注入演员。

**修复**：①工具 `except` 用 `logger.warning` 记录真实异常，只回传模型能据以行动的一句话；②`prompts/playwright.yaml` 的「工具报错属于内部信息，绝不外泄」条款。判据是 `tool_trace[*].result_preview` 与导演笔记文本是否有重叠片段。

## 修复落点映射

| 症状 | 落点 |
|---|---|
| 编剧/书记拿不到 provider | `plugins/astrbot_plugin_art/core/provider_resolver.py`、`layers/playwright.py`、`layers/scribe.py` |
| 核心 Skills/工具说明泄漏进演员提示词 | `plugins/astrbot_plugin_art/layers/assemble.py` 的 `strip_actor_forbidden_sections()` |
| 编剧产出的事件层质量（含台词、越权、变数用法） | `plugins/astrbot_plugin_art/prompts/playwright.yaml` |
| 演员文风、代行边界、编号选项 | `plugins/astrbot_plugin_art/prompts/actor.yaml` |
| 书记抽取字段、承诺来源硬规矩 | `plugins/astrbot_plugin_art/prompts/scribe.yaml` |
| 角色卡注入内容（外貌/口吻/严禁用词） | `plugins/astrbot_plugin_art/prompts/casting.yaml`、`core/cards.py` |
| 世界观、地点、时间切片、变数卡 | `plugins/astrbot_plugin_art/presets/*.json` |
| 审计缺证据（缺少要看的字段） | `plugins/astrbot_plugin_art/core/audit_ledger.py`、`main.py` 的 `_record_actor_*`、`layers/*` 的 `_record_*` |
| 审计写入本身报错 | 账本内部已吞异常不影响出话；查日志 `[Art.*] Audit ... failed` |

改动后**必须同步 runtime 副本**（AstrBot 实际加载的是它）：

```bash
MSYS_NO_PATHCONV=1 robocopy 'plugins\astrbot_plugin_art' 'data\plugins\astrbot_plugin_art' /MIR /XD .git __pycache__ /XF '*.pyc'
```

## 边界

- 审计是**只写**的：插件内部不读账本来影响玩法。不要建议"让插件根据账本自动修正"。
- 不要用账本反推整段历史。以单轮的 `audit_view` / `response.meta` 为准；跨轮结论要给出具体轮次与样本量。
- **审计写入失败绝不影响出话**是设计不变量。不要把"审计没记录"当成"游戏没发生"。
- 不要因为编剧降级就改演员提示词——先修上层。
- 不要改数值/状态机来兜文风问题。
- `clean_narrative_reply` 只清 `<think>` 家族与英文元推理前缀，**不认**工具调用泄漏；别把它当万能兜底。
- 文风判断是阅读判断，汇报必须引原文。

## 常用文件

- 审计账本：`data/plugin_data/astrbot_plugin_art/llm_audit/`
- 审计索引：`data/plugin_data/astrbot_plugin_art/llm_audit_index/`
- 账本实现：`plugins/astrbot_plugin_art/core/audit_ledger.py`
- provider 解析：`plugins/astrbot_plugin_art/core/provider_resolver.py`
- 三层管线：`plugins/astrbot_plugin_art/layers/{playwright,assemble,scribe}.py`
- 四个编剧工具：`plugins/astrbot_plugin_art/tools/*.py`
- 提示词资产：`plugins/astrbot_plugin_art/prompts/*.yaml`
- 世界观预设：`plugins/astrbot_plugin_art/presets/*.json`
- 插件架构与排查：`plugins/astrbot_plugin_art/CLAUDE.md`（与 `AGENTS.md` 同内容）
- 字段细节：`references/ledger_schema.md`（本 skill 内）

时间窗口与报告时间戳统一用 **UTC+8**。

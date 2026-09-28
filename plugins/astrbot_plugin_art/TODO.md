# 剧作家插件 (Art) 落地与优化任务清单 (TODO)

> 定位：`astrbot_plugin_art`，专注于让玩家当消费者的全新角色扮演体验，与 `astrbot_plugin_agentic_RPG` 并存且会话互斥。

---

## 阶段一：通用写作协议与 Skills 体系
- [x] **通用写作协议核心抽取** (`skills/art-writing-core/SKILL.md`)
  - [x] 抽离核心质量准则：提议归角色、决定归玩家、无机械感官罗列、有效节拍推进
  - [x] 确立三大硬规则：【】绝对权威、一轮一节拍、拒绝 `[1][2][3]` 编号选项
  - [x] 编码合规校验：UTF-8 无 BOM 保存，无 `EF BB BF` 头字节

## 阶段二：世界观预设体系 (Presets)
- [x] **四大基础世界观预设落地** (`presets/*.json`)
  - [x] `default.json`：现代日常舞台与场景牌
  - [x] `star-rail.json`：崩坏：星穹铁道世界观与匹诺康尼/空间站场景牌
  - [x] `elysium.json`：黄金庭院/往世乐土日常世界观与场景牌
  - [x] `genshin.json`：提瓦特大陆日常世界观与场景牌

## 阶段三：单会话 SQLite 数据库与状态机 (Core)
- [x] **单 Session 单库架构** (`core/db.py`)
  - [x] 实现 6 张核心数据表：`session`, `scenes`, `[cast]`, `scripts`, `ledger`, `memories`
  - [x] 解决 SQL 关键字冲突：对 SQL 保留字 `[cast]` 进行全量转义与安全访问
  - [x] 支持轻量会话回滚：`rollback_recent_turns`
- [x] **会话归属独占与互斥控制** (`core/claim.py`)
  - [x] 实现 `claim_session_for_art`、`is_art_claimed`、`is_rpg_claimed`、`release_session_claim`
  - [x] 与 Agentic RPG 建立双向互斥边界，避免双插件同时抢占会话
- [x] **四层变数抽取引擎** (`core/variance.py`)
  - [x] 一天的底色（Daily Color）：每日游戏状态底色抽取
  - [x] 场景牌（Scene Modifier）：切场景环境与突发变数
  - [x] 行动结果（Action Roll）：不确定动作的 5 档成败判定
  - [x] 中期节奏（Beat Arc）：编剧排期节奏
  - [x] 引入时间戳随机盐，解决重投同点数问题
- [x] **三层角色卡解析体系** (`core/cards.py`)
  - [x] Canonical 官方卡（只读） > 会话生成卡（标准 YAML） > 路人卡
  - [x] 分层提示词提取：外貌神韵锚点常驻、首秀完整外貌、亲密层（NSFW 开关）
- [x] **单一事实源状态管理器** (`core/state.py`)
  - [x] 会话初始化、换场、角色出场/退场调度与设定修正

## 阶段四：四个极简工具链 (Tools)
- [x] **场景切换工具** (`tools/scene.py` -> `change_scene`)
  - [x] 支持地点、时间切片、在场角色流转与新场景牌抽取
  - [x] 支持玩家输入 `【还在...】`、`【回到...】` 快速撤回换场
- [x] **选角与登场工具** (`tools/cast.py` -> `cast`)
  - [x] 角色登场 (`enter`) 与离场 (`leave`)
  - [x] 未建档角色自动生成规范 YAML 角色卡并持久化落盘
- [x] **记忆召回工具** (`tools/recall.py` -> `recall`)
  - [x] 跨场景历史记忆关键词检索
- [x] **角色设定修正工具** (`tools/character.py` -> `fix_character`)
  - [x] 支持 `update`（增量局部修正）、`regenerate`（重写）、`delete`（删除）

## 阶段五：三层流水线编排与思维链清洗 (Layers)
- [x] **隐藏编剧子循环** (`layers/playwright.py`)
  - [x] 通过 `context.tool_loop_agent` 驱动便宜模型与工具调用
  - [x] 产出纯事件导演笔记，不外泄角色台词与心理活动
- [x] **演员提示词组装与脱钩** (`layers/assemble.py`)
  - [x] 组装稳定写作协议、世界观、在场角色卡、关系账本、场景环境与导演笔记
  - [x] 剥离演员模型的工具定义，确保输出纯粹且不产生工具调用幻觉
- [x] **后台异步书记** (`layers/scribe.py`)
  - [x] 异步非阻塞执行，不拖慢玩家可见回复
  - [x] 硬规矩：承诺/告白/答应仅在玩家原话中出现时才记入账本
  - [x] 提取玩家画像与心愿剧本种子
- [x] **思维链与 Meta 话语泄漏清洗** (`main.py` -> `clean_narrative_reply`)
  - [x] 剥离 `<think>`、`<thought>`、`<cot>`、`<xiaoai_core>` 标签残留
  - [x] 剥离类似 `As Firefly, I should respond in character.` 等非标签思考前缀

## 阶段六：指令体系与插件主入口 (Main & Config)
- [x] **生命周期与工具注册** (`main.py`)
  - [x] 挂载 `on_llm_request` 与 `on_llm_response` 钩子
  - [x] 注册 4 个全局工具与 ToolSet 隔离
- [x] **7 个 `/art` 命令全覆盖**
  - [x] `/art start`：开局认领，初始化世界观与角色
  - [x] `/art forget [n]`：回滚最近 n 轮交互，同步回滚世界状态与对话历史
  - [x] `/art card [名字]`：列出生成卡或打印卡片详情与物理路径
  - [x] `/art ledger`：查看细节账本（承诺、回忆、礼物、节奏偏好）
  - [x] `/art reset`：清空会话数据，删除生成卡并释放独占
  - [x] `/art debug`：输出场景、角色、剧本、变数与账本全景
  - [x] `/art help`：展示完整命令帮助与 `【】` 提示
- [x] **配置模式与元数据** (`metadata.yaml`, `_conf_schema.json`)
  - [x] 支持编剧与书记独立 provider 配置
  - [x] 调试日志开关

## 阶段七：与 Agentic RPG 并存协同
- [x] **RPG 插件互斥拦截** (`plugins/astrbot_plugin_agentic_RPG/`)
  - [x] `handlers/_base.py` 增加 `_is_art_claimed` 检查
  - [x] `handlers/commands.py` `/rpg start` 拦截已认领会话
- [x] **架构技能文档同步** (`.codex/skills/rpg-plugin-architecture/SKILL.md`)
  - [x] 记录 Session 独占原则与与 Art 插件的协同边界
- [x] **镜像同步**
  - [x] `plugins/` 与 `data/plugins/` 目录哈希比对一致

## 阶段八：RP Bench 跑分评测体系集成
- [x] **评测臂配置** (`scripts/rp_bench/config.py`)
  - [x] 将 `art` 纳入 `ARMS` 与 `RPG_ARMS`
- [x] **自动化 Driver 实现** (`scripts/rp_bench/drivers/art.py`)
  - [x] 支持新会话 `/art start` 引导、登场门禁判定与多轮自动打分记录
- [x] **Never-say 词法 bug 修复** (`scripts/rp_bench/cards.py`)
  - [x] 增加否定后行断言，防止将“温柔”等褒义特质误提取为违禁词
  - [x] 7 项卡片词法测试 100% 通过

## 阶段九：质量验证与自动化测试
- [x] **Art 插件专项测试** (`tests/test_art_plugin.py`)
  - [x] 覆盖 DB 事务、会话认领、变数骰点、角色卡分层、4 个工具、提示词装配、书记硬规矩、7 个 `/art` 指令及思维链清洗，9 项测试全部通过
- [x] **RPG NPC 契约回归测试** (`tests/test_rpg_npc_character_contract.py`)
  - [x] 12 项测试全部通过
- [x] **RP Bench 卡片测试** (`tests/test_rp_bench_cards.py`)
  - [x] 7 项测试全部通过
- [x] **代码质量检查**
  - [x] `ruff check` 与 `ruff format` 100% 通过

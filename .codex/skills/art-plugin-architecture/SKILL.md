---
name: art-plugin-architecture
description: 维护或修改 AstrBot Art 单主模型情感陪伴插件的架构、请求接管、五工具、私有资产、UID USER 后台、持久恢复、Persona 边界与 Discord 展示；用于 Art 开发和架构检查，账本取证使用 art-ledger-audit，RPG 4.0/5.0 使用 rpg-plugin-architecture。
---

# Art 单主模型架构维护

先读 `plugins/astrbot_plugin_art/AGENTS.md`，再定位改动相关模块；该文档与同目录 `CLAUDE.md` 必须字节一致。Art 2.x 前台只有一个主 agent，工具返回后可继续请求同一 provider，不存在独立编剧、演员、导演笔记、书记或后置记忆模型。UID USER reviewer 是独立后台维护，不参与故事编排。

拉取分支/更新插件后，执行更新的 agent 必须额外核对本技能与 `art-ledger-audit`。完整主仓库拉取会更新已跟踪目录；单独更新插件或部署副本不会自动更新 agent 的实际技能。按插件 AGENTS.md 的「拉取后的必要 agent 技能更新」从匹配主仓库版本取得完整目录，安装到实际项目的 Codex/Claude 四个位置，校验清单、哈希、UTF-8 无 BOM 与可发现性，再汇报来源提交。仅更新插件不能视为维护环境已更新。

## 工作边界

- 情感陪伴是核心，角色与玩家默认已经是恋人。玩家明确修订 > 会话私有设定 > 默认恋人前提 > 原始角色背景。具体人物的性格与声线来自私有卡。
- `prompts/agent.yaml` 是唯一前台通用协议，包含资源手册和完整写作指导。Art 不继承 AstrBot Persona、其示例或核心 Skills/工具说明；入口 Persona 仅服务尚未被 Art 接管的普通聊天。
- 保留通用写作指导，只移除特定角色特点。叙事质量与玩家代行边界写在协议中；代码只处理确定性的权限、参数、状态、工具、模板与审计，不加叙事正则、关键词门控或安全审核器。
- Art/RPG 按 `event.unified_msg_origin` 独占会话，普通聊天不接管。工具不能指定其他 session、任意文件路径或 SQL。

## 前台链路

1. `/art start [世界观]` 校验互斥，创建空 AstrBot 对话、场景和私有世界，写 `art_meta.version=2`；序章走同一个 agent。
2. `main.py::on_art_llm_request` 在核心 session lock 内接管。旧三阶段会话提示 reset/新会话，原数据不变；版本 2 的库只补齐 UID 元数据与快照表。
3. `core/session.py::recover` 回滚遗留 SQL 事务、恢复 pending 轮次；`begin` 保存业务表、私有卡/世界、USER 冻结快照与有效正文历史。
4. `layers/agent.py` 复用 provider 解析、`ToolLoopAgentRunner`、`FunctionToolExecutor`，只开放五个 Art 工具。工具返回后刷新动态状态，继续同一主模型。
5. 成功后提交 user/最终 assistant 正文与 journal，再排入 USER 证据队列。序章不是用户证据，重答不能把原玩家输入归给另一 UID。
6. 生成、状态写入、历史提交失败或中止，恢复轮前检查点；已提交正文的发送失败不撤回业务。USER 加载、排队或 reviewer 失败不阻断故事提交。
7. 发送正文及实际 reasoning，`stop_event` 阻止核心再调用默认 LLM。内部工具文本不直接发往频道。

上下文顺序：**固定 agent 协议 → 冻结 UID USER → 有效正文历史 → 当前权威动态状态 → 本轮输入**。自动历史为最近 40 条正文消息；完整有效轮次由 journal 分页读取。媒体与指定模型复用核心请求，思考、工具过程、撤回正文不自动进入下一轮。

动态块提供资源目录、在场完整私有卡、关系、剧本、近期 ledger/memory 与代码氛围。工具刷新/rewind 必须按 `layers/assemble.py::DYNAMIC_PREFIX` 定位，不能把第一个 `_no_save` 块当作当前状态，误覆盖冻结 USER。恢复历史仍须保留本轮工具调用与返回的协议配对。

## 资源与工具

| 资源/接口 | 权威位置与边界 |
| --- | --- |
| 公共 preset/canonical card | 首次使用的只读模板，不原地改缓存；角色别名落到同一私有卡 |
| 私有 world/character | worlds 与 cards 下的 hashed-session 目录；修订只影响当前故事，原创人物也保留完整私有卡 |
| session/scenes/cast/scripts/ledger/memories | 每 session SQLite；memory 是故事摘要，ledger 是共同事实与承诺，不充当现实用户传记 |
| history | art_turns 的 committed 正文，独立于上下文裁剪与可关闭的审计 |
| user | users/index.db 是平台实例 + UID 的事实源，users/<owner>/USER.md 是导出，前台只读 |
| art_read | 分页/检索上述资源；user 可读当前或可信活跃参与者的实时版本 |
| art_write | 批量创建/更新/删除故事资源，失败整批恢复；promise 验证有效轮次和玩家逐字原话 |
| art_change_scene / art_cast | 换场、同步在场集合、进出/形态变化，返回有效设定 |
| art_rewind | pending 请求内完整撤回真实轮次，返回原始输入；每请求仅一次 |

统一 `{ok,data,error}`。ok=true 是调用当时成功，还须结合最终提交和后续 rewind 判断保留状态。每日底色与入场氛围由代码抽取并注明来源/有效范围，不逐轮重抽场景，不抽行动成败。

## UID USER 后台与缓存

- `core/users.py` 将同 UID 的真实用户原话与正文语境持久排队，每 UID 合并为一个任务；模型请求在所有 session/USER 数据库锁之外。
- `prompts/user_review.yaml` 只整理现实画像和相处偏好，不写剧情、不改关系、不审核正文。现实身份需现实自述；RP 设定和主模型虚构不是事实。XP 保留情境与不确定性。
- WebUI `select_provider` 独立选择 reviewer，默认 deepseek/deepseek-flash；显式空值暂停，不回退前台 provider。首次 20 条新证据可提前维护，否则 30 分钟到期处理；后续尝试至少间隔 30 分钟，调用最长 120 秒。
- 发布前重查同 UID 有效 source_id、逐字原话与起始 revision。删除/撤回令迟到结果失效，删除有主题墓碑；组合事实因部分来源撤回重新评估，不整体回滚其他 session 的 USER。
- 每 conversation/UID 的 user_snapshots 默认冻结 60 分钟；新对话、显式 refresh、删除或来源撤回重新加载。普通后台发布不逐轮改前缀，时间戳不入 prompt；实际缓存命中由 provider 决定。
- 当前发言者及最近 10 个有效轮次的真实活跃 UID 分别加载。`/art user show|refresh|delete [key]` 只管理调用者的 USER。
- 关闭取消后台任务，队列保留；启动恢复队列，接管 session 时用 journal 的 author_uid/platform/profile_input 补偿漏排的 committed 输入及 revoked 来源。

## 恢复与交付

`/art forget [count]` 与请求/reset 共用 session lock，不经模型，完整恢复业务状态、私有资产和正文；超范围不部分执行。自然语言重答先 rewind，成功才标旧轮 revoked，失败恢复重答开始前的原轮。reset 清理故事与恢复记录，切换空对话、释放认领，保留审计和跨 session USER。

Discord 工具过程隐藏，最终正文与实际 reasoning 分开发送；思考每段完整 `||...||`，转义内部标记、禁提及通知，无 reasoning 不补占位。旧消息保留，重答另发。审计分 agent/user_review 并兼容旧三阶段，取证见 [art-ledger-audit](../art-ledger-audit/SKILL.md)。

## 改动落点与验收

| 改动 | 优先检查 |
| --- | --- |
| 协议/Persona/动态状态 | prompts/agent.yaml、layers/assemble.py、layers/agent.py |
| 接管/历史/中止/恢复 | main.py、layers/agent.py、core/session.py |
| 权限/批量原子性 | tools/agent.py |
| 模板隔离/角色身份/氛围 | core/assets.py、core/cards.py、core/state.py |
| UID 证据/维护/冻结 | core/users.py、prompts/user_review.yaml、_conf_schema.json |
| 审计/Discord/Bench | core/audit_ledger.py、main.py、AstrBot Discord event、scripts/rp_bench/drivers/art.py |

更新本 skill、插件 AGENTS/CLAUDE 与受影响的审计技能；同步 source Art → runtime Art、Codex skills → Claude skills，排除 .git/pycache，核对哈希和 UTF-8 无 BOM。新增技能登记根目录 CLAUDE.md 镜像表。先发布子模块提交，再提交主仓库 gitlink；运行数据库、USER、审计原文与凭据不能进 Git。

验证 Art/USER/Discord 测试、改动范围 Ruff、YAML/schema 与镜像；真实陪伴效果人工阅读隔离回放，不用关键词测试代替。事故复盘必须有账本证据，不读取 data/logs，不向活跃玩家发审计消息。RPG 4.0/5.0 按独立架构技能维护。

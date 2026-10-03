---
name: art-ledger-audit
description: 离线审计 AstrBot Art 单主模型情感陪伴的输入、执行轨迹、写入、思考、正文、整轮撤回及独立 UID USER reviewer；用于用户反馈复盘和污染/隔离/恢复取证，兼容旧三阶段账本，架构修改另用 art-plugin-architecture。
---

# Art 审计账本离线审计

Art 2.x 一轮只有一个主 agent，可以在工具返回后多次请求同一模型。没有独立编剧、导演笔记或后台书记。所有角色与玩家默认已是恋人，玩家修订与私有设定优先于原始角色背景。

每次拉取分支/更新 Art 后，由执行更新的 agent 额外核对本技能与 `art-plugin-architecture`。插件仓库不包含主仓库技能目录，单独更新插件不会自动更新实际 agent 技能；应从匹配的主仓库集成版本复制完整技能目录到项目的 Codex/Claude 两侧，校验清单、哈希和 UTF-8 无 BOM，确认可发现并报告来源提交。具体交接步骤见插件 AGENTS.md 的「拉取后的必要 agent 技能更新」。

## 工作流

1. 先运行 `python .codex/skills/art-ledger-audit/scripts/index_summary.py --limit 20`，不要先读完整 prompt。
2. 按需运行 `python .codex/skills/art-ledger-audit/scripts/turn_detail.py --turn <turn_id> --chars 1200`；全文仅在需要时使用 `--full`。
3. 字段说明读 `references/ledger_schema.md`；先判断 stage=agent（2.x）、user_review（UID 后台维护）还是 playwright/actor/scribe（旧版）。旧版三阶段必须一起阅读。
4. 每个结论指明具体轮次、样本量和原文。用户说的事故描述是线索，不能代替服务器账本证据。

默认 `--stage story` 只选 agent/旧 actor，避免最新后台画像审阅抢占故事轮次。检查后台时两个脚本都加 `--stage user_review`；混合列表用 `--stage all`。显式 --session 支持原始身份或编码 key，--data-root 可指隔离测试数据。需要执行事件/工具后的上下文快照时，turn_detail 加 `--trace`；--full 同时展开完整轨迹。--json 导出完整原始文档，不受展示截断影响。

## 单 agent 审计

- `request`：唯一主模型收到的 agent.yaml 协议、冻结 UID USER、动态私有状态与有效正文历史。Art 忽略 Persona 及其示例，文风指导不含特定角色特点。核对默认恋人前提、用户明确修订与私有关系是否真实注入。
- `audit_view.persona_policy` 应为 ignored_art_protocol_only；`user_versions` 表明本轮实际加载的 UID/版本。后台新版本不一定立即自动注入，核对冻结窗口与显式 refresh，不能只比较最新 USER.md。早期 2.0 可保留 stripped_sections 字段，旧判据不强加到新版。
- `response.meta.execution_trace`：本轮 agent 事件与上下文快照，含模型实际返回的 reasoning；工具前后的文本不是玩家正文。
- `response.meta.tool_trace`：五个工具的参数与信封。ok=true 表示调用当时成功；后续 rewind 仍可能撤销本轮较早写入，须按顺序核对最终状态。失败批次恢复到批前状态，错误信封不携带原始异常。
- `response.meta.committed`：业务事务是否成功发布。false/response.error 意味着未完成，不要把工具曾返回成功误读成最终已提交。
- `response.text`：最终正文；简短修订确认允许出现在正文前，重答只交替代正文。
- `response.meta.replaces`：撤回旧轮的 ID。旧审计文件仍保留，不能当作有效故事历史；结合后续撤回记录或 art_turns.status。
- 思考、工具过程与撤回正文不自动注入后续会话，不能再当 memory 来源。审计记录本身不参与玩法或自动纠偏。
- 代码抽取的氛围应注明 code_random 来源与有效范围，无玩家特殊要求时遵循；不应存在行动成败抽取。
- 主模型通过 art_write 保存关系、记忆、心愿与剧本；promise 必须有有效玩家原话来源。不存在“书记有没有跑”的新架构判据。会话亲密开关（`session.nsfw`）同样由主模型经 art_write 自行置位、无玩家命令；置位后动态块应含 `prompts/nsfw.yaml` 的 guidance，未置位或资产留空时不应出现。
- 无工具轮应只有一个前台模型请求；工具轮只延续同一 agent/provider。执行事件条数不等于模型请求数，USER reviewer 不能算进前台调用次数。核对资源目录与有效历史，不能把最近注入的一部分当成全部资源。

## UID USER reviewer 审计

stage=user_review 使用独立配置 provider（WebUI 下拉，默认 deepseek/deepseek-flash），不影响故事工具或前台正文。request 只含同平台 UID 的有效证据与已有条目；逐条核对用户原话引文，角色虚构职业、演员发言不能成为现实用户事实。画像和 XP 认识需保留语境与依据，未确认推断不能写成现实事实。

`audit_view.base_revision` 与 response.meta.base_revision 是审阅起始版本；published=true 才表示发布，false 要看 error（可能是陈旧版本或来源撤回），不能把原始 JSON 当成已生效画像。删除/forget/重答撤回会使冻结版本失效，但不回滚其他 session 的真实用户画像。reset 清理故事而保留 USER。全量证据在 users/index.db，USER.md 是可读导出；只读检查时不要改动在线数据库。

后台与前台不是旧编剧/演员链：USER 不是导演笔记、独立剧情审核或书记。不得把后台次数算成前台一个轮次的主模型调用次数。

## 恢复与兼容

`/art forget` 是不调用 LLM 的完整轮次恢复命令；reset 还应切换到空的有效对话。检查点独立于 enable_llm_audit_ledger，关闭审计不能关闭恢复。旧会话不自动迁移，需玩家 reset 或开新会话。

旧 stage 保留阅读支持：playwright 看 provider/fallback 与导演笔记；actor 看实际 prompt 与清洗差异；scribe 看 parsed_ok 和 writes。不要把这些旧字段要求施加到 agent 文档。

## 修复落点

| 问题 | 源码落点 |
| --- | --- |
| 关系前提、文风、自然语言修订策略或亲密情境注入 | prompts/agent.yaml、prompts/nsfw.yaml、layers/assemble.py |
| 主调用、有效历史、过程污染或审计缺字段 | layers/agent.py、core/audit_ledger.py |
| 工具错误、资源权限、真实写入 | tools/agent.py |
| 私有角色/世界副本或随机氛围 | core/cards.py、core/state.py |
| 整轮恢复、重答失败、崩溃恢复 | core/session.py、main.py |
| UID USER、独立 reviewer、来源撤回、冻结版本 | core/users.py、prompts/user_review.yaml、layers/agent.py |
| Discord 折叠/提及通知 | main.py、AstrBot discord_platform_event.py |

源码根目录 `plugins/astrbot_plugin_art/`；运行副本 `data/plugins/astrbot_plugin_art/`；审计数据 `data/plugin_data/astrbot_plugin_art/llm_audit/` 和 `llm_audit_index/`。改动需同步 runtime 与插件 AGENTS.md/CLAUDE.md，双份技能目录也要同步并核对哈希。

需要修改拓扑、注入、私有资产、USER 或恢复机制时，使用相邻 [art-plugin-architecture](../art-plugin-architecture/SKILL.md)。默认入口只服务未启动的普通聊天，不把 Persona 再叠入 Art 协议。

不要向活跃 RP 会话发送审计消息，不读取 data/logs 原始日志，不加入叙事质量正则、关键词门控、审核器或数值兜底。审计失败绝不阻断正文。时间与报告窗口统一 UTC+8。

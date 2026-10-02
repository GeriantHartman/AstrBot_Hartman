# Art 2.x 审计字段

目录 `llm_audit/<session_key>/<turn_id>-agent-<session_key>.json`，索引 `llm_audit_index/<session_key>.jsonl`。session_key 使用 percent-encoding，长值加哈希；turn_id 使用 UTC+8 时间与随机后缀。

| 字段 | 说明 |
| --- | --- |
| schema_version | agent/user_review=2；旧 stage=1 |
| stage | agent/user_review；兼容 playwright/actor/scribe |
| request | system_prompt、contexts、prompt、tools 的初始请求快照 |
| assembly_trace.provider_source | selected_provider/session/none；单一 provider |
| audit_view | agent: persona_policy、user_versions、relationship_premise；user_review: base_revision；早期 2.0 可有 stripped_sections |
| response.text | 最终角色正文，未经叙事审核 |
| response.error | 失败异常类型；原始工具异常仅进日志 |
| response.meta.committed | 是否完成业务与历史提交 |
| response.meta.tool_trace | 按序 tool、args、ok、data、error；art_write.data.writes 为实际批次写入，若最终 committed=false 则已回退 |
| response.meta.execution_trace | runner 事件类型、chain_type、文本及该时刻 messages 快照；可能含后台文本和思考，不能当正文 |
| response.meta.reasoning | provider 实际返回的思考；没有返回则为空 |
| response.meta.replaces | 本轮撤回的旧 turn_id；失败事务不会正式撤回 |
| metadata.current_turn | preset_name、user_preview；用于索引 |

索引沿用 provider/model/preset、user/assistant preview、response_error、response_meta。它记录历史审计，不能作为有效故事历史。后续 committed=true 且 replaces 包含某轮，意味着该旧轮已撤回；`/art forget` 的审计以 agent stage、command=forget 记录。

恢复数据位于会话 SQLite 的 art_meta/art_turns，不受审计开关或轮转上限控制。业务 journal 状态是 pending/committed/revoked/failed/command；只有 committed 可被普通 history 工具召回。reset 删除该 journal、切换空对话，保留旧审计。

旧三阶段文档沿用原字段：playwright 的 is_fallback/fallback_reason/tool_trace/director notes；actor 的 raw response/cleaned/stripped_sections/dynamic prompt；scribe 的 parsed_ok/parsed/writes。旧文件不会改写或迁移，离线工具按 stage 分派展示。

UID 后台审计使用 user:<owner> 虚拟审计会话，stage=user_review。request 为独立维护协议、existing_entries、deleted_topics 与 new_evidence；response.text 是原始画像 JSON，不是角色正文。response.meta.published 是实际发布结果，base_revision 是起始版本。未发布的结果不进入 USER，也不改变前台。

art_turns 新增 author_uid/author_name/platform/profile_input；重答修订输入与合并故事输入分开，避免重新分配旧用户证据。user_snapshots 保存当前对话冻结版本，users/index.db 保存跨会话来源。关闭审计不停止证据队列或恢复。

索引脚本默认 --stage story（agent/actor），可以单选 agent/user_review/legacy 或 all，先筛选再截取 --limit。展示 stage/provider/model，避免同一 model 名字掩盖不同 provider。详情默认故事会话，--stage user_review 用于后台虚拟会话，latest 按文件最后写入时间选择，避免同秒 UUID 字典序误选旧轮。--trace 展开 execution_trace；--full 完整展开所有展示字段，--json 返回原始完整文档。

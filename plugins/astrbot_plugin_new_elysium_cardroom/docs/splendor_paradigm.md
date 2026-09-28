# 璀璨宝石桌游范式

## 目标

璀璨宝石模式的目标是让群聊里的真人玩家和米哈游角色卡 AI 一起玩一局可结算、可恢复、可交流的 Splendor。它不是把角色包装成职业牌手，而是让角色本人进入牌桌。

## 分层原则

1. 确定性规则写在 Python 引擎中。
2. 房间快照写入 SQLite，插件重载后可恢复活跃房间。
3. 文本 UI 负责记忆负担，必须展示银行、市场、贵族、当前玩家、各玩家状态和待处理事项。
4. AI 只能选择规则引擎列出的合法动作。
5. 角色声纹、关系、失误倾向和桌上交流放在 prompt/skill 中，不写成代码级风格判定。

## 规则引擎边界

引擎负责：

- 2-4 人设置。
- 宝石银行、金币、10 枚上限。
- 三级发展卡牌堆、公开市场和补牌。
- 拿宝石、保留、购买、付款、折扣。
- 保留上限、盲保留、金币发放。
- 贵族访问和多贵族选择。
- 15 分触发最终轮。
- 最高分、少买牌破平和并列胜利。

引擎不负责：

- 判断一句话是否像某个角色。
- 强迫 AI 采取最优策略。
- 用关键词或正则约束叙事质量。

## AI 行动范式

AI 回合分为三步：

1. `SplendorEngine.available_actions()` 生成合法动作清单。
2. `SplendorAIService` 向 LLM 注入牌面、角色卡、关系提示、记忆和合法动作。
3. LLM 输出 JSON；引擎再次校验。失败时使用随机兜底合法动作。

推荐 JSON：

```json
{
  "speech": "那我先把这张扣住，别问，问就是有用。",
  "action": {
    "action": "reserve",
    "selector": "T2-3"
  }
}
```

合法动作类型：

- `take`: `{"action":"take","colors":["white","blue","green"]}`
- `reserve`: `{"action":"reserve","selector":"T1-1"}`
- `reserve`: `{"action":"reserve","selector":"T2"}`
- `buy`: `{"action":"buy","selector":"T3-4"}`
- `buy`: `{"action":"buy","selector":"R1"}`
- `discard`: `{"action":"discard","colors":["white","blue"]}`
- `choose_noble`: `{"action":"choose_noble","noble_id":"N1"}`

## 角色优先

AI 可以：

- 为了熟人放慢节奏或护短。
- 因为角色习惯偏爱某种颜色。
- 抢一张别人想买的牌。
- 买一张并不最优但符合当下情绪的牌。
- 忘记最佳路线并选择保守动作。

AI 不可以：

- 输出非法动作。
- 声称自己是 AI、模型或系统。
- 用原作超能力看牌堆、改资源或改变规则。
- 把 Splendor 变成原作战斗剧情。

## UI 范式

群聊文本应该优先解决玩家记忆问题：

- 市场牌位必须稳定使用 `T1-1` 到 `T3-4`。
- 预留牌使用 `R1`、`R2`、`R3`，状态文本展示每位玩家预留牌的颜色、分数和成本。
- 贵族使用 `N1` 到 `N10`。
- 颜色接受中文和英文，内部统一为 `white/blue/green/red/black/gold`。
- 状态文本必须显示当前行动玩家和下一步命令。

## DB 范式

SQLite 只保存房间快照，不保存规则书文本：

```text
data/plugin_data/astrbot_plugin_new_elysium_cardroom/splendor/splendor.sqlite3
```

表 `splendor_rooms`：

- `group_id`
- `phase`
- `state_json`
- `updated_at`

活跃房间为 `waiting` 或 `playing`。结束后的房间可写为 `finished`，不再自动恢复为活跃房间。

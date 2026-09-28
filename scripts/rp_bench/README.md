# RP Bench：角色卡 × 模型 × 插件 跑分

拿同一套**写死的玩家台词**，去打不同的「角色卡 + 模型 + 插件组合」，比较说话方式、剧情推进、角色还原等表现。两个日常用途：

- **验新卡**：新写的 canonical YAML 跑一遍通用剧本，看口吻立不立得住、会不会出戏。
- **验插件改动**：4.0 vs 5.0、改代码前 vs 改代码后，出胜率和分差。

## 裸考模式（基础版，由 agent 发起）

只考模型本身：不走插件，不给工具，不查知识库，也不给角色卡。system prompt 只有一句「你是《作品》中的角色「X」。请以X的身份与我对话。」，其余全靠模型自己记得的官方资料。题库是 `scenarios/bare/` 下的两本 10 轮剧本（考官方设定回忆、考情绪弧线），加上通用剧本 `scenarios/generic/`。默认不跑裁判，只把两个模型的对话存到本地。

日常由 agent 发起。操作说明在 `.codex/skills/rp-bench/SKILL.md` 和 `.claude/skills/rp-bench/SKILL.md`，两份内容相同，有测试保证它们一致。对 agent 说「用 rp-bench 对比 A 和 B 的 RP 能力」即可。agent 实际执行的命令是：

```
uv run python -m scripts.rp_bench providers                                   # 查可用模型 id
uv run python -m scripts.rp_bench all --plan scripts/rp_bench/plans/bare.yaml --models A,B
```

角色用 `--cards` 换，可以写卡片文件名，也可以写 `名字@作品`（没有角色卡也能测）。跑完后看跑次目录下的 `index.md`（目录和快速统计），以及 `compare/*.md`（两个模型逐轮并排）。以后要打分，对同一个跑次执行 `judge --resume <目录> --judge <provider_id>`，不用重新生成对话。

每条命令的最后一行都是 `RPBENCH_RESULT {json}`，供 agent 判断成败。退出码：0 成功，2 部分完成（按 `next` 字段续跑），1 参数错误。

## 卡规模排名（同一模型 × 不同规模的角色卡）

模型和角色固定，只换喂给模型的角色资料，看哪一档演得最好、多花的 token 值不值：

| 组 | 给模型什么 |
|---|---|
| `bare` | 只有角色名 + 作品名 |
| `raw` | canonical YAML 卡（`plugins/astrbot_plugin_agentic_RPG/canonical_characters/<卡>.yaml`） |
| `skill` | skills 角色卡全文（`data/skills/<卡>-skill/`：SKILL.md + 它点名的文件按顺序拼接） |

```
uv run python -m scripts.rp_bench all --plan scripts/rp_bench/plans/card-scale.yaml --models A --cards X
```

`compare/` 里三档逐轮并排。已有跑次想补一档，不用重跑：`all --resume <目录> --add-arms raw`。汇报要求（引原文、拿卡核对设定、写明样本量）见 skill 文件。

## 四个对照组

| 组 | 怎么跑 | 角色卡怎么进去 |
|---|---|---|
| `raw` | 进程内直接调 AstrBot provider，历史由跑分工具维护 | 角色卡当 persona，和 RPG 叙事者看到的声音块是同一份渲染 |
| `style_skills` | 同上，但 system prompt 先过真实的 style_skills 插件钩子 | persona + 插件追加的核心规则和当前风格 |
| `rpg4` / `rpg5` | 通过运行中 AstrBot 的 `POST /api/v1/chat` 真实走完整条 RPG 管线 | 插件自己把 canonical YAML 注入 NPC 包 |

RPG 组的「换模型」只换**叙事者**（跟随 `selected_provider`）。Router、Validator、Director、NPC 生成用插件配置里各自的 provider，manifest 会把这些配置全部记下来。每一轮都会核对审计账本：实际管线对不对、叙事者有没有悄悄换了模型、style_skills 有没有串进来。

## 第一次使用

1. 启动 AstrBot（RPG 组需要）：`uv run main.py`
2. 在 WebUI 创建一个 API key（勾选 chat 权限），写进 `data/rp_bench/secrets.yaml`（data/ 不进 git）：

   ```yaml
   astrbot_api_key: abk_xxxxxxxx
   # 可选：填了会额外把会话级默认 provider 也钉到被测模型上
   dashboard_user: astrbot
   dashboard_password: 你的面板密码
   ```

3. 自检（不花钱）：`uv run python -m scripts.rp_bench probe --plan scripts/rp_bench/plans/smoke.yaml`
   加 `--live-llm` 会给每个模型和裁判各发一句很短的请求，确认 key 能用。
4. 看调用量：`uv run python -m scripts.rp_bench plan --plan scripts/rp_bench/plans/mvp.yaml --dry-run`
5. 冒烟：`uv run python -m scripts.rp_bench all --plan scripts/rp_bench/plans/smoke.yaml --smoke`
6. 正式：`uv run python -m scripts.rp_bench all --plan scripts/rp_bench/plans/mvp.yaml`

产物在 `data/rp_bench/runs/<UTC+8时间>-<plan名>/`，打开 `report.md` 即可。

## 常用流程

- **中断了**：`... all --resume data/rp_bench/runs/<目录>`，已完成的会话、已打的分都会跳过。
- **只重跑某一段**：`run` / `judge` / `pair` / `report` 加 `--resume`。改了评分标准（`judge/rubric.py` 里的 `RUBRIC_VERSION`）后只需重跑 `judge` 和 `pair`，不用重新生成对话。
- **插件回归**：改代码前用 `plans/regression.yaml` 跑一次当基线，改完再跑一次，然后
  `... pair --resume <新目录> --baseline <旧目录>`。两次用同一个 plan、同一份剧本，才会按「卡 × 剧本 × 组 × 模型 × 第几次」一一配对。
- **验新卡**：把 `plans/card-check.yaml` 里的 `cards` 换成新卡文件名。

## 剧本怎么写

放在 `scenarios/<套件>/*.yaml`，格式见 `scenarios/core/elysia-first-meeting.yaml`。要点：

- 10–20 轮玩家台词，所有对照组一字不差。
- `card: "*"` 是通用剧本，只能用 `{char}` / `{player}` / `{call_player}` 占位符，不能写死角色名。
- `rpg.setup_turns` 是不计分的开场台词，用来把目标角色请上场；之后有**出场闸门**，角色没上场的会话单列在报告里，不参与角色维度评分。
- `probes` 是埋在剧本里的考点：`plant_fact`（埋事实）→ `memory_recall`（后面考记忆，`ref` 必须指向更早埋下的 key）、`low_effort_player`、`ooc_bait`、`agency_trap`、`secret_pressure`、`state_layer_trigger`、`never_say_trigger`。
- 改了剧本内容，内容哈希就会变，旧跑次不会和新剧本错配。

`card_overrides/<卡>.yaml` 用来补充程序从卡片自然语言里读不出的规则（比如「人家」最多出现在 15% 的轮次里）。

## 分数怎么读

- **确定性指标**：纯代码统计，不花钱，每次结果一样。包括自称和称呼违规、never_say 字面命中、出戏话术、脚手架泄漏（如 `<xiaoai_core>`）、复读、开头雷同、口癖使用率。标「启发式」的只是提示人工去看。
- **绝对分**：每维 1–5 分，3 分 = 合格。裁判必须给出回应原文里逐字存在的证据；编造的证据会被程序查出来，重试一次还是编的，这一维就作废。报告会给出证据核对通过率，低于 90% 时分数不可信。
- **两两盲比**：同一剧本同一轮并排、匿名 A/B，左右互换各评一次再合并。**抛硬币是 50%**，报告里同时给出「这个差别有多大可能只是碰巧」。
- **噪声底**：同一组的第 0 次和第 1 次重复自己跟自己比。它的区间宽度，就是这次跑分能分辨的最小差距。
- 主结论只在同一格式内部比：rpg4 vs rpg5、raw vs style_skills、新代码 vs 旧代码。聊天体和 RPG 小说体之间的对比会标「跨格式，仅供参考」。

## 安全边界

- `import astrbot.core` 会顺手建配置文件、开数据库、写日志。CLI 在任何 astrbot 导入之前，先把 `ASTRBOT_ROOT` 指到 `<run目录>/.astrbot_sandbox`；线上的 `data/cmd_config.json` 只用纯 JSON 读取，不会被改写。
- 跑分会话统一用 `rp-bench` 用户名，会留在 webchat 会话列表、RPG 会话库和审计账本里，方便日后按用户名清理。
- 不改动 RPG 插件和 style_skills 插件的任何代码。

## 测试

`uv run pytest tests/test_rp_bench_*.py`。全部离线，用假的传输层，不发网络请求。

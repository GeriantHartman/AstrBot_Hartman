---
name: rp-bench
description: 发起并汇报 RP Bench 角色扮演跑分。用于用户要求「测一下/对比一下某几个模型的 RP 能力」「跑裸考题库」「验证角色卡」「不同规模的角色卡排个名/YAML 卡和 skill 卡哪个好」「对比插件 4.0/5.0 或改动前后」时，由 agent 调用 scripts/rp_bench 的命令行完成全流程：选模型、预估调用量、自检、生成对话、导出并排对比、读取结果并用中文汇报。默认裸考模式不走插件、不给工具、不查知识库、不给角色卡，只考模型内置知识，且不跑裁判，只保存两个模型的对话。
---

# RP Bench（agent 发起）

用户不会手动跑这些命令，由你来发起、盯进度、读结果、汇报。所有操作都走 `uv run python -m scripts.rp_bench ...`（工作目录为仓库根 `E:\agentic-rpg\AstrBot`）。每条命令最后一行都是

```
RPBENCH_RESULT {...json...}
```

以这一行为准判断成败，不要靠猜。退出码：0 成功，2 部分完成（可续跑），1 参数或配置错误。

## 默认任务：裸考两个模型

用户说「对比 A 和 B 的 RP 能力」「跑一下裸考」，而没有要求插件或裁判时：

1. **确定两个模型**：用户给的名字要映射到 AstrBot provider id。先运行
   `uv run python -m scripts.rp_bench providers`
   从输出里挑 `enabled` 的条目。拿不准用户说的是哪个 id（例如「flash」对应多个），就问用户，不要自己猜。
2. **预估**：
   `uv run python -m scripts.rp_bench plan --plan scripts/rp_bench/plans/bare.yaml --models A,B --dry-run`
   向用户报会话数和大致 token。会话数超过 60 个时，先确认再跑。
3. **自检**（一次性，花几分钱）：
   `uv run python -m scripts.rp_bench probe --plan scripts/rp_bench/plans/bare.yaml --models A,B --live-llm`
   有 FAIL 就停下，把 FAIL 那一行原样告诉用户。
4. **正式跑**：
   `uv run python -m scripts.rp_bench all --plan scripts/rp_bench/plans/bare.yaml --models A,B`
   耗时较长，用后台方式运行并等它结束，不要轮询刷屏。
5. **状态是 `partial`**：先读 `failures` 字段判断原因（限流、超时、key 失效）。如果是瞬时错误，按 `next` 字段给出的命令 `all --resume <run_dir>` 续跑一次，已完成的会话会跳过。续跑后仍失败，再汇报给用户。
6. **汇报**，见下文。

可选参数：
- `--cards elysia,firefly`：换角色。可以是 `plugins/astrbot_plugin_agentic_RPG/canonical_characters/` 下的文件名，也可以写 `名字@作品`（例如 `"芙宁娜@原神"`），没有角色卡的角色也能裸考。
- `--repeats 2`：每题跑两次，用来看同一个模型自己的波动。
- `--smoke`：只跑每本剧本的前 3 轮，用来确认流程能跑通。

## 卡规模排名：同一模型 × 不同规模的角色卡

用户说「用不同规模的卡给 X 排个名」「YAML 卡和 skill 卡哪个好」「角色卡有没有用」时用这个流程。模型和角色固定，只换喂给模型的角色资料，三档对照组：

| 组 | 给模型什么 | 来源 | 规模参考（昔涟） |
|---|---|---|---|
| `bare` | 只有角色名 + 作品名 | `名字@作品` 或卡里的名字 | 约 40 字，每场约 4k 输入 token |
| `raw` | canonical YAML 卡的渲染结果 | `plugins/astrbot_plugin_agentic_RPG/canonical_characters/<卡>.yaml` | 约 4.4k 字，每场约 32k |
| `skill` | skills 角色卡全文 | `data/skills/<卡>-skill/`（SKILL.md + 它点名的 .md，按顺序拼接） | 约 84k 字，每场约 564k |

1. **确认卡齐全**：`raw` 需要 YAML 卡里有 `profile.profile_text`；`skill` 需要 skills 文件夹里有 `SKILL.md`（文件夹名不是 `<卡>-skill` 时，在 `scripts/rp_bench/card_overrides/<卡>.yaml` 写 `skill_dir`）。缺哪档就用 `--arms` 去掉那档，并在汇报里说明。
2. **预估**：`uv run python -m scripts.rp_bench plan --plan scripts/rp_bench/plans/card-scale.yaml --models A --cards X --dry-run`。skill 档的 token 是其他档的十几倍，会话数不多也要把 token 报给用户。
3. **正式跑**：`uv run python -m scripts.rp_bench all --plan scripts/rp_bench/plans/card-scale.yaml --models A --cards X`，后台运行。
4. **已有跑次补一档**：不要重开，用 `all --resume <run_dir> --add-arms raw`。已跑完的会话不会重跑，新档直接并进 `compare/`。
5. **汇报排名**，在「读结果」的要求之外再加：
   - 开头一句话给出排名（例如「YAML ≳ skill ≫ bare」），并说明哪两档差距小、可能因随机波动换位。
   - 一张表：每档的资料规模、每场输入 token（从 `metrics.jsonl` 的 `tokens_in` 读）、平均篇幅、出戏话术、never_say 命中。token 要写成倍数关系（「skill 是 raw 的约 17 倍」）。
   - 按口吻、设定、记忆题、出戏诱导、情绪戏逐项对比，每项引原文。
   - **拿卡核对设定**：外貌、专有名词等要对照对应的卡原文核实，不要凭印象。两张卡互相矛盾时（例如一张禁止直呼地名、另一张没有禁止），明确指出，不要替用户判定哪张是标准。
   - never_say 命中逐条确认是真违规还是误判（例如角色是在描述别人，而不是在称呼玩家）。误判照实写出来。
   - 注明样本量（每档跑了几次、有没有裁判）。每档只跑 1 次、没有裁判时，排名只是阅读判断，不是统计结论。
6. **想让排名更可信**时，向用户提议（不要擅自开跑）：`--repeats 2` 看波动；用不同家族的裁判跑 `judge --resume <run_dir> --judge <id>` 和 `pair --resume <run_dir> --judge <id>`，plan 里已经配好了 `raw` 对 `skill`、`bare` 对 `raw` 两组盲比。

## 读结果

`RPBENCH_RESULT` 里的 `files` 字段给出路径：

- `index.md`：目录，以及每个模型的快速统计（篇幅、延迟、出戏话术、never_say 命中、自称违规、复读）。
- `compare/<角色>__<剧本>__r0.md`：两个模型逐轮并排，是主要阅读材料。
- `sessions/...`：单个会话全文，包括 system prompt 和思考过程。
- `transcripts.jsonl`、`metrics.jsonl`：原始数据。需要做额外统计时，把分析写成 `scripts/research/` 下的脚本再运行，不要在命令行里内联代码。

没有裁判时不会有分数。你的汇报是**阅读后的定性对比**，必须引用原文：

1. 先写结论：每个剧本上哪边更像这个角色、剧情推进更好，各用一两句话说明。
2. 快速统计表中差异明显的数字，要附上参照（例如「A 平均 820 字，B 平均 310 字」）。
3. 逐个考点：记忆题（`memory_recall`）谁记住了；出戏诱导（`ooc_bait`）谁承认自己是 AI；`agency_trap` 谁替玩家写了心理或台词。每条引一句原文。
4. 设定错误：模型编造或说错了官方设定时，引原文并指出哪里不对。自己也不确定的设定，就写「待核实」，不要当事实下结论。
5. 附上 `index.md` 和 `compare/` 的路径。

## 其他模式（用户明确要求时才用）

- 带角色卡、不带插件：`--arms raw`，或者用 `plans/card-check.yaml`（raw 对比 style_skills）。
- RPG 插件 4.0 对比 5.0：`plans/mvp.yaml`。需要 AstrBot 在运行，并且 `data/rp_bench/secrets.yaml` 里有 `astrbot_api_key`。先跑 `probe`。
- 补跑裁判：`uv run python -m scripts.rp_bench judge --resume <run_dir> --judge <provider_id>`，然后跑 `pair --resume <run_dir> --judge <provider_id>`。裁判要选和被测模型不同家族的 provider。
- 插件回归：`plans/regression.yaml` 跑两次，然后 `pair --resume <新> --baseline <旧> --judge <id>`。

## 不要做

- 不要改 `plugins/` 下任何插件代码，也不要改 `scripts/rp_bench/` 里的剧本来「凑结果」。剧本有问题就告诉用户。
- 不要读 `data/logs/`（体量巨大）。
- 不要把 `data/rp_bench/secrets.yaml` 的内容打印出来。
- 不要在跑到一半时换模型重新开跑。要换就开一个新跑次，旧跑次保留。
- `list` 命令可以列出历史跑次，方便找到上次的结果。

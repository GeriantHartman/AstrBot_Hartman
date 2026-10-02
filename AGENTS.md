## Setup commands

### Core

```
uv sync
uv run main.py
```

Exposed an API server on `http://localhost:6185` by default.

### Dashboard(WebUI)

```
cd dashboard
pnpm install # First time only. Use npm install -g pnpm if pnpm is not installed.
pnpm dev
```

Runs on `http://localhost:3000` by default.

## Dev environment tips

1. When modifying the WebUI, be sure to maintain componentization and clean code. Avoid duplicate code.
2. Do not add any report files such as xxx_SUMMARY.md.
3. After finishing, use `ruff format .` and `ruff check .` to format and check the code.
4. When committing, ensure to use conventional commits messages, such as `feat: add new agent for data analysis` or `fix: resolve bug in provider manager`.
5. Use English for all new comments.
6. For path handling, use `pathlib.Path` instead of string paths, and use `astrbot.core.utils.path_utils` to get the AstrBot data and temp directory.
7. All AstrBot/Codex skill files and skill metadata must be saved as UTF-8 without BOM. This includes `SKILL.md`, referenced `.md`, `.json`, `.yaml`, `.py`, and other text files under `data/skills`, `.codex/skills`, `plugins/*/skills`, and mirrored runtime plugin skill folders. Do not write skill files with `utf-8-sig`, Windows PowerShell default BOM output, or editor settings that add BOM. After editing skills, verify the edited files do not start with bytes `EF BB BF`.
8. When editing Agentic RPG plugin assets that are mirrored between runtime and source plugin directories, always update and verify both locations. This explicitly includes `canonical_characters`, `presets`, `world_info`, `skills`, and other project assets:
   - Runtime: `data/plugins/astrbot_plugin_agentic_rpg/...`
   - Source plugin: `plugins/astrbot_plugin_agentic_RPG/...`
   Confirm matching hashes before reporting completion.
9. When changing Agentic RPG plugin functionality, flow order, LLM tool topology, prompt/chat-template injection points, preset `map_guidance`, story hook / foreshadowing storage or injection behavior, 4.0 contract pipeline behavior, audit ledger views, guidance overlay hierarchy, or major feature responsibilities, update `.codex/skills/rpg-plugin-architecture/SKILL.md` **and its mirror** `.claude/skills/rpg-plugin-architecture/SKILL.md` in the same change. Keep the skill concise, validate it, and save it as UTF-8 without BOM.
10. For Agentic RPG, code may only handle deterministic events such as tool calls, state writes, config branches, audit records, and template assembly. Do not add code-level regexes, keyword gates, Verifier rules, or hard constraints to judge non-deterministic narrative quality. Put those fixes in Router rules, prompts, style skills, guidance, or audit documentation instead.
11. Agent skills live in two **independent** locations and must be mirrored: `.codex/skills/<name>/` and `.claude/skills/<name>/`. A skill present on only one side is invisible (or stale) on the other. The mirrored set is `rp-bench`, `rpg-ledger-audit`, `rpg-plugin-architecture`, `art-ledger-audit` — see the maintenance table in `CLAUDE.md` under "Agent skills 双份镜像约定". After changing any file in one copy (`SKILL.md`, `references/`, `scripts/`, `agents/`), copy it to the other and verify:
    ```
    cp -r .codex/skills/<name> .claude/skills/<name>
    rm -rf .claude/skills/<name>/__pycache__ .claude/skills/<name>/scripts/__pycache__
    diff -rq --exclude=__pycache__ .codex/skills/<name> .claude/skills/<name>   # must print nothing
    ```
    New skills must be created in both locations, and the table in `CLAUDE.md` updated.

## PR instructions

1. Title format: use conventional commit messages
2. Use English to write PR title and descriptions.

## RP Bench (role-play benchmark)

1. `scripts/rp_bench/` benchmarks "model × character card × plugin" combinations with fixed player scripts. Agents launch it; the user does not run it by hand. Follow `.codex/skills/rp-bench/SKILL.md` (identical copy at `.claude/skills/rp-bench/SKILL.md`; keep both in sync).
2. Arms: `bare` (character name + game only), `raw` (canonical YAML card), `skill` (full `data/skills/<card>-skill/` bundle), `style_skills`, `rpg4`, `rpg5`.
3. Plans in `scripts/rp_bench/plans/`: `bare.yaml` compares two models without a card; `card-scale.yaml` ranks one model across card sizes (bare / raw / skill); `card-check.yaml` compares raw vs style_skills; `mvp.yaml` / `regression.yaml` cover RPG 4.0 vs 5.0 and before/after regressions.
4. Add an arm to an existing run with `all --resume <run_dir> --add-arms <arm>` instead of starting over. Results live in `data/rp_bench/runs/<UTC+8 stamp>-<plan>/`; read `index.md` and `compare/` first.
5. Without a judge, rankings are reading-based: quote the transcripts, state the sample size, and check lore against the card text itself.

## RPG tool analysis

1. Tool analysis reports, stats time windows, and report filenames must use UTC+8.
2. Keep runtime `TOOL_SKILL_MAP` limited to current real LLM tools. Put legacy aliases only in the tool-analysis skill.
3. Tool usage analysis counts LLM behavior only; do not count user-triggered `/rpg` built-in commands as LLM tool usage.

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
9. When changing Agentic RPG plugin functionality, flow order, LLM tool topology, prompt/chat-template injection points, preset `map_guidance`, story hook / foreshadowing storage or injection behavior, 4.0 contract pipeline behavior, audit ledger views, guidance overlay hierarchy, or major feature responsibilities, update `.codex/skills/rpg-plugin-architecture/SKILL.md` in the same change. Keep the skill concise, validate it, and save it as UTF-8 without BOM.
10. For Agentic RPG, code may only handle deterministic events such as tool calls, state writes, config branches, audit records, and template assembly. Do not add code-level regexes, keyword gates, Verifier rules, or hard constraints to judge non-deterministic narrative quality. Put those fixes in Router rules, prompts, style skills, guidance, or audit documentation instead.

## PR instructions

1. Title format: use conventional commit messages
2. Use English to write PR title and descriptions.

## RPG tool analysis

1. Tool analysis reports, stats time windows, and report filenames must use UTC+8.
2. Keep runtime `TOOL_SKILL_MAP` limited to current real LLM tools. Put legacy aliases only in the tool-analysis skill.
3. Tool usage analysis counts LLM behavior only; do not count user-triggered `/rpg` built-in commands as LLM tool usage.

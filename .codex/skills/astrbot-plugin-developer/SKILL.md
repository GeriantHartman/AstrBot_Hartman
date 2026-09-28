---
name: astrbot-plugin-developer
description: Guide AstrBot plugin creation, modification, debugging, configuration, storage, message handlers, LLM tools, and plugin publishing. Use when Codex needs to create a new AstrBot plugin, update an existing plugin, add commands/events/configuration/storage/AI tools to an AstrBot plugin, or answer implementation questions using this repository's AstrBot developer docs.
---

# AstrBot Plugin Developer

## Core Workflow

Use this skill to build or update AstrBot plugins from the local documentation under `docs/zh/dev`.

1. Clarify the plugin goal, trigger commands/events, platforms, configuration needs, storage needs, and whether it should expose LLM tools.
2. Inspect the existing plugin or choose a plugin directory. For normal AstrBot development, plugins live under `data/plugins/<plugin_name>`. For mirrored Agentic RPG assets, update both `data/plugins/astrbot_plugin_agentic_rpg/...` and `plugins/astrbot_plugin_agentic_RPG/...` and compare hashes before completion.
3. Read only the relevant source docs when details are needed:
   - Start here: `docs/zh/dev/star/plugin-new.md`
   - Minimal plugin: `docs/zh/dev/star/guides/simple.md`
   - Commands, filters, hooks: `docs/zh/dev/star/guides/listen-message-event.md`
   - Sending messages: `docs/zh/dev/star/guides/send-message.md`
   - Plugin config: `docs/zh/dev/star/guides/plugin-config.md`
   - Storage: `docs/zh/dev/star/guides/storage.md`
   - LLM/Agent/Tool APIs: `docs/zh/dev/star/guides/ai.md`
   - Session control: `docs/zh/dev/star/guides/session-control.md`
   - Publishing: `docs/zh/dev/star/plugin-publish.md`
4. Use `references/astrbot_plugin_reference.md` for concise templates and API patterns.
5. Implement with the repository's existing style. Keep handlers small and move reusable business logic to separate modules when a handler grows.
6. Validate with focused checks first, then run `ruff format .` and `ruff check .` before reporting completion when Python code changed.

## Plugin Structure

Prefer the official plugin template shape:

```text
astrbot_plugin_example/
  main.py
  metadata.yaml
  _conf_schema.json        # optional
  requirements.txt         # optional
  logo.png                 # optional, 1:1, recommended 256x256
```

Use plugin names that are lowercase, short, contain no spaces, and usually start with `astrbot_plugin_`.

`metadata.yaml` is required for AstrBot to identify plugin metadata. Consider optional `display_name`, `support_platforms`, and `astrbot_version` when publishing or targeting specific adapters/versions.

## Implementation Rules

- Define the plugin class in `main.py` and inherit from `astrbot.api.star.Star`.
- Keep every handler method inside the plugin class. Handler signatures start with `self, event`.
- Import the event filter as `from astrbot.api.event import filter, AstrMessageEvent`; do not rely on Python's built-in `filter`.
- Use `from astrbot.api import logger` for logging.
- Use `yield event.plain_result(...)`, `yield event.image_result(...)`, or `yield event.chain_result(...)` for passive replies inside handlers.
- Use `await event.send(...)` in event hooks and waiter callbacks where `yield` is not supported.
- Use `self.context.send_message(unified_msg_origin, chain)` for proactive messages, storing `event.unified_msg_origin` when delayed sending is needed.
- Use `_conf_schema.json` plus `AstrBotConfig` in `__init__` for user-editable plugin settings.
- Store persistent data outside the plugin code directory. Prefer AstrBot KV storage for simple values and `data/plugin_data/<plugin_name>/` for larger files.
- Use `pathlib.Path` for path handling and this repo's AstrBot path utilities when accessing data or temp directories.
- Avoid `requests`; use async HTTP clients such as `aiohttp` or `httpx`.
- Add good error handling around network, platform, file, and provider calls so one failure does not crash the plugin.
- Keep new code comments in English.
- Do not create report files such as `xxx_SUMMARY.md`.

## Feature Patterns

Choose the smallest pattern that satisfies the request:

- **Command**: Use `@filter.command("name")` for a simple `/name` command. Command names cannot contain spaces.
- **Command with arguments**: Add typed parameters after `event`; AstrBot parses them automatically.
- **Command group**: Use `@filter.command_group("group")` and child commands for multi-command plugins.
- **Filters**: Combine command, message type, platform type, and permission decorators; decorators use AND logic.
- **Hooks**: Use hooks such as `on_llm_request`, `on_llm_response`, `on_using_llm_tool`, or `after_message_sent` for lifecycle integrations. Do not combine hook decorators with command/filter decorators.
- **Configuration**: Add `_conf_schema.json`; accept `config: AstrBotConfig` in `__init__`.
- **Storage**: Use `put_kv_data`, `get_kv_data`, and `delete_kv_data` for simple plugin-scoped values.
- **LLM generation**: Use `self.context.get_current_chat_provider_id()` and `self.context.llm_generate()`.
- **LLM tools**: Prefer class-based `FunctionTool` for reusable tools; decorator-based `@filter.llm_tool` is fine for small plugin-local tools.
- **Agent loops**: Use `self.context.tool_loop_agent(...)` with a `ToolSet` when the feature needs model-tool iteration.

## Validation

Before finishing:

1. Run targeted tests or import/compile checks for changed plugin modules.
2. Run `ruff format .`.
3. Run `ruff check .`.
4. If runtime/source plugin assets are mirrored, compare hashes for both locations before reporting completion.
5. If a UI or WebUI behavior changed, start the relevant dev server and verify the flow in the browser when feasible.

## Reference

Load `references/astrbot_plugin_reference.md` when you need concrete code snippets for `main.py`, `metadata.yaml`, `_conf_schema.json`, message chains, storage, or LLM tools.

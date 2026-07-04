# AstrBot Plugin Reference

Use this file as a compact implementation reference. The canonical source remains `docs/zh/dev`.

## Minimal `main.py`

```python
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star


class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        """Reply with a greeting."""
        user_name = event.get_sender_name()
        logger.info("helloworld command triggered")
        yield event.plain_result(f"Hello, {user_name}!")

    async def terminate(self):
        """Clean up resources when the plugin is unloaded."""
```

Rules:

- The plugin class belongs in `main.py`.
- Handlers must be class methods.
- Handler parameters begin with `self, event`.
- Handler docstrings are useful because AstrBot can surface them to users.

## `metadata.yaml`

```yaml
name: astrbot_plugin_example
desc: Example AstrBot plugin
version: v1.0.0
author: your-name
repo: https://github.com/your-name/astrbot_plugin_example
display_name: Example Plugin
support_platforms:
  - telegram
  - discord
astrbot_version: ">=4.16,<5"
```

Useful `support_platforms` values include `aiocqhttp`, `qq_official`, `telegram`, `wecom`, `lark`, `dingtalk`, `discord`, `slack`, `kook`, `vocechat`, `weixin_official_account`, `satori`, `misskey`, and `line`.

## Commands And Filters

```python
@filter.command("add")
async def add(self, event: AstrMessageEvent, a: int, b: int):
    """Add two integers."""
    yield event.plain_result(f"Result: {a + b}")
```

```python
@filter.command_group("math")
def math(self):
    pass


@math.command("sub")
async def sub(self, event: AstrMessageEvent, a: int, b: int):
    """Subtract two integers."""
    yield event.plain_result(f"Result: {a - b}")
```

```python
@filter.permission_type(filter.PermissionType.ADMIN)
@filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
@filter.command("admin_only")
async def admin_only(self, event: AstrMessageEvent):
    """Run only for admins in private messages."""
    yield event.plain_result("OK")
```

Use `event.stop_event()` to stop later handlers, other plugins, or LLM processing when the current plugin has fully handled an event.

## Event Hooks

Hooks cannot be combined with command or filter decorators.

```python
from astrbot.api.provider import ProviderRequest


@filter.on_llm_request()
async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
    """Adjust an LLM request before sending."""
    req.system_prompt += "\nFollow the plugin's additional policy."
```

```python
@filter.on_waiting_llm_request()
async def on_waiting_llm(self, event: AstrMessageEvent):
    """Notify users while waiting for an LLM request."""
    await event.send("Waiting for the model...")
```

## Sending Messages

Passive replies from handlers:

```python
@filter.command("image")
async def image(self, event: AstrMessageEvent):
    """Send text and an image."""
    yield event.plain_result("Here is an image.")
    yield event.image_result("https://example.com/image.jpg")
```

Rich message chains:

```python
import astrbot.api.message_components as Comp


@filter.command("rich")
async def rich(self, event: AstrMessageEvent):
    """Send a rich message chain."""
    chain = [
        Comp.At(qq=event.get_sender_id()),
        Comp.Plain(" look at this:"),
        Comp.Image.fromURL("https://example.com/image.jpg"),
    ]
    yield event.chain_result(chain)
```

Proactive messages:

```python
from astrbot.api.event import MessageChain


async def send_later(self, event: AstrMessageEvent):
    """Send a proactive message to the current session."""
    chain = MessageChain().message("Hello later!")
    await self.context.send_message(event.unified_msg_origin, chain)
```

## Plugin Configuration

Create `_conf_schema.json`:

```json
{
  "enabled": {
    "description": "Enable the plugin feature",
    "type": "bool",
    "default": true
  },
  "provider_id": {
    "description": "Provider used by this plugin",
    "type": "string",
    "default": "",
    "_special": "select_provider"
  }
}
```

Read config in `main.py`:

```python
from astrbot.api import AstrBotConfig
from astrbot.api.star import Context, Star


class ConfigPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
```

Common schema types: `string`, `text`, `int`, `float`, `bool`, `object`, `list`, `dict`, `template_list`, and `file`.

## Storage

Simple plugin-scoped KV storage:

```python
await self.put_kv_data("greeted", True)
greeted = await self.get_kv_data("greeted", False)
await self.delete_kv_data("greeted")
```

Large files should live in `data/plugin_data/<plugin_name>/`:

```python
from pathlib import Path

from astrbot.core.utils.astrbot_path import get_astrbot_data_path


plugin_data_path = Path(get_astrbot_data_path()) / "plugin_data" / self.name
plugin_data_path.mkdir(parents=True, exist_ok=True)
```

If this repository exposes newer helpers in `astrbot.core.utils.path_utils`, prefer those local utilities for AstrBot data and temp paths.

## LLM Generation

```python
@filter.command("ask")
async def ask(self, event: AstrMessageEvent, prompt: str):
    """Call the current chat provider."""
    provider_id = await self.context.get_current_chat_provider_id(
        umo=event.unified_msg_origin
    )
    llm_resp = await self.context.llm_generate(
        chat_provider_id=provider_id,
        prompt=prompt,
    )
    yield event.plain_result(llm_resp.completion_text)
```

## Class-Based LLM Tool

```python
from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext


@dataclass
class ExampleTool(FunctionTool[AstrAgentContext]):
    name: str = "example_tool"
    description: str = "Return an example result."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Query text.",
                }
            },
            "required": ["query"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        query = kwargs["query"]
        return f"Result for {query}"
```

Register class-based tools:

```python
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.context.add_llm_tools(ExampleTool())
```

## Decorator-Based LLM Tool

```python
@filter.llm_tool(name="get_weather")
async def get_weather(self, event: AstrMessageEvent, location: str):
    """Get weather information.

    Args:
        location(string): Location name.
    """
    yield event.plain_result(f"Weather for {location}: sunny")
```

Supported docstring parameter types include `string`, `number`, `object`, `boolean`, `array`, and newer `array[string]`.

## Tool Loop Agent

```python
from astrbot.core.agent.tool import ToolSet


@filter.command("agent")
async def agent(self, event: AstrMessageEvent, prompt: str):
    """Run an agent with tools."""
    provider_id = await self.context.get_current_chat_provider_id(
        event.unified_msg_origin
    )
    llm_resp = await self.context.tool_loop_agent(
        event=event,
        chat_provider_id=provider_id,
        prompt=prompt,
        tools=ToolSet([ExampleTool()]),
        max_steps=30,
        tool_call_timeout=60,
    )
    yield event.plain_result(llm_resp.completion_text)
```

## Validation Checklist

- Confirm plugin loads or compiles.
- Check command names and handler signatures.
- Check `_conf_schema.json` parses as JSON if present.
- Check dependency additions are listed in `requirements.txt`.
- Run `ruff format .`.
- Run `ruff check .`.

## Publishing

Push the plugin repository to GitHub, then submit it through the AstrBot plugin market at `https://plugins.astrbot.app`. The form creates an issue in the AstrBot repository; verify the generated issue before submitting.

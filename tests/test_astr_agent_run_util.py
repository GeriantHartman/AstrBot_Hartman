import asyncio
from types import SimpleNamespace

import pytest

from astrbot.core.agent.response import AgentResponse, AgentResponseData, AgentStats
from astrbot.core.astr_agent_run_util import _simulated_stream_tts, run_agent
from astrbot.core.message.components import Json
from astrbot.core.message.message_event_result import MessageChain


class _Trace:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict]] = []

    def record(self, name: str, **kwargs) -> None:
        self.records.append((name, kwargs))


class _WebChatEvent:
    def __init__(self) -> None:
        self.trace = _Trace()
        self.sent: list[MessageChain] = []
        self.extras: dict[str, object] = {}
        self.result = None

    def is_stopped(self) -> bool:
        return False

    def get_extra(self, key: str, default=None):
        return self.extras.get(key, default)

    def set_extra(self, key: str, value) -> None:
        self.extras[key] = value

    def get_platform_id(self) -> str:
        return "webchat"

    def get_platform_name(self) -> str:
        return "webchat"

    async def send(self, chain: MessageChain) -> None:
        self.sent.append(chain)

    def set_result(self, result) -> None:
        self.result = result

    def clear_result(self) -> None:
        self.result = None


class _FakeEvent:
    """Minimal event surface used by the agent stream bridge."""

    def is_stopped(self) -> bool:
        return False

    def get_extra(self, key: str):
        del key
        return None

    def get_platform_name(self) -> str:
        return "test"


class _Runner:
    streaming = False

    def __init__(self, event: _WebChatEvent) -> None:
        self.run_context = SimpleNamespace(context=SimpleNamespace(event=event))
        self.stats = AgentStats()
        self._done = False
        self.stop_requested = False

    def done(self) -> bool:
        return self._done

    def request_stop(self) -> None:
        self.stop_requested = True

    async def step(self):
        yield AgentResponse(
            type="tool_call",
            data=AgentResponseData(
                chain=MessageChain(
                    type="tool_call",
                    chain=[
                        Json(
                            data={
                                "id": "call_1",
                                "name": "lookup",
                                "args": {"query": "x"},
                            }
                        )
                    ],
                )
            ),
        )
        yield AgentResponse(
            type="tool_call_result",
            data=AgentResponseData(
                chain=MessageChain(
                    type="tool_call_result",
                    chain=[Json(data={"id": "call_1", "result": "secret result"})],
                )
            ),
        )
        yield AgentResponse(
            type="llm_result",
            data=AgentResponseData(chain=MessageChain().message("final answer")),
        )
        self._done = True


class _StreamingErrorRunner:
    """Agent runner that finishes with one provider error response."""

    streaming = True
    req = None

    def __init__(self, error_text: str) -> None:
        self.error_text = error_text
        self.finished = False
        self.run_context = SimpleNamespace(context=SimpleNamespace(event=_FakeEvent()))

    async def step(self):
        self.finished = True
        yield AgentResponse(
            type="err",
            data={"chain": MessageChain().message(self.error_text)},
        )

    def done(self) -> bool:
        return self.finished


class _MalformedStreamingErrorRunner(_StreamingErrorRunner):
    """Agent runner that returns an invalid provider error payload."""

    async def step(self):
        self.finished = True
        yield AgentResponse(type="err", data={})


async def _run_with_config(
    *, show_tool_use: bool, show_tool_call_result: bool
) -> _WebChatEvent:
    event = _WebChatEvent()
    runner = _Runner(event)

    async for _ in run_agent(
        runner,  # type: ignore[arg-type]
        max_step=3,
        show_tool_use=show_tool_use,
        show_tool_call_result=show_tool_call_result,
    ):
        pass

    return event


@pytest.mark.asyncio
async def test_webchat_hides_tool_call_and_result_when_config_disabled():
    event = await _run_with_config(
        show_tool_use=False,
        show_tool_call_result=False,
    )

    sent_types = [chain.type for chain in event.sent]
    assert "tool_call" not in sent_types
    assert "tool_call_result" not in sent_types


@pytest.mark.asyncio
async def test_webchat_shows_tool_call_but_hides_result_when_result_disabled():
    event = await _run_with_config(
        show_tool_use=True,
        show_tool_call_result=False,
    )

    sent_types = [chain.type for chain in event.sent]
    assert "tool_call" in sent_types
    assert "tool_call_result" not in sent_types


@pytest.mark.asyncio
async def test_webchat_shows_tool_result_only_when_result_config_enabled():
    event = await _run_with_config(
        show_tool_use=True,
        show_tool_call_result=True,
    )

    sent_types = [chain.type for chain in event.sent]
    assert "tool_call" in sent_types
    assert "tool_call_result" in sent_types


@pytest.mark.asyncio
async def test_run_agent_forwards_streaming_provider_error():
    error_text = (
        "LLM 响应错误: Not found the model k2.7-code-highspeed or Permission denied"
    )
    runner = _StreamingErrorRunner(error_text)

    chains = [chain async for chain in run_agent(runner)]

    assert len(chains) == 1
    assert chains[0].get_plain_text() == error_text


@pytest.mark.asyncio
async def test_run_agent_replaces_malformed_streaming_provider_error():
    runner = _MalformedStreamingErrorRunner("unused")

    chains = [chain async for chain in run_agent(runner)]

    assert len(chains) == 1
    assert chains[0].get_plain_text() == "Error occurred during AI execution."


@pytest.mark.asyncio
async def test_simulated_stream_tts_leaves_audio_for_deferred_cleanup(tmp_path):
    audio_path = tmp_path / "speech.wav"
    audio_path.write_bytes(b"audio")

    class _TTSProvider:
        async def get_audio(self, text: str) -> str:
            assert text == "hello"
            return str(audio_path)

    text_queue: asyncio.Queue[str | None] = asyncio.Queue()
    audio_queue: asyncio.Queue[bytes | tuple[str, bytes] | None] = asyncio.Queue()
    await text_queue.put("hello")
    await text_queue.put(None)

    await _simulated_stream_tts(_TTSProvider(), text_queue, audio_queue)

    assert await audio_queue.get() == ("hello", b"audio")
    assert await audio_queue.get() is None
    assert audio_path.exists()

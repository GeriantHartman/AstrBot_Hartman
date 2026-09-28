"""Parser for the AstrBot webchat SSE protocol (dashboard/routes/chat.py)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatReply:
    plain_parts: list[str] = field(default_factory=list)
    frames: list[dict[str, Any]] = field(default_factory=list)
    agent_stats: dict[str, Any] = field(default_factory=dict)
    ended: bool = False
    error: str = ""

    @property
    def text(self) -> str:
        return "\n".join(p for p in self.plain_parts if p).strip()


class SSEParser:
    """Feed raw text chunks; frames are separated by a blank line."""

    def __init__(self) -> None:
        self._buf = ""
        self._stream_buf: list[str] = []
        self.reply = ChatReply()

    def feed(self, chunk: str) -> None:
        self._buf += chunk.replace("\r\n", "\n")
        while "\n\n" in self._buf:
            block, self._buf = self._buf.split("\n\n", 1)
            self._handle_block(block)

    def close(self) -> ChatReply:
        if self._buf.strip():
            self._handle_block(self._buf)
        self._buf = ""
        if self._stream_buf:
            self.reply.plain_parts.append("".join(self._stream_buf))
            self._stream_buf = []
        return self.reply

    def _handle_block(self, block: str) -> None:
        data_lines = []
        for line in block.split("\n"):
            if not line or line.startswith(":"):
                continue  # heartbeat / comment
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if not data_lines:
            return
        payload = "\n".join(data_lines)
        try:
            frame = json.loads(payload)
        except json.JSONDecodeError:
            return
        if not isinstance(frame, dict):
            return
        self.reply.frames.append(frame)
        ftype = frame.get("type")
        if ftype == "plain":
            chain = frame.get("chain_type")
            if chain in ("tool_call", "tool_call_result", "reasoning"):
                return
            data = str(frame.get("data") or "")
            if frame.get("streaming"):
                self._stream_buf.append(data)
            elif data:
                self.reply.plain_parts.append(data)
        elif ftype == "complete":
            # Streaming: "complete" carries the full text of the deltas seen so
            # far. Non-streaming: it only repeats the last plain frame
            # (webchat_event._send emit_complete), so it is ignored.
            if frame.get("streaming"):
                data = frame.get("data")
                full = (
                    data
                    if isinstance(data, str) and data
                    else "".join(self._stream_buf)
                )
                if full:
                    self.reply.plain_parts.append(full)
                self._stream_buf = []
        elif ftype == "agent_stats":
            data = frame.get("data")
            if isinstance(data, dict):
                self.reply.agent_stats = data
        elif ftype == "error":
            self.reply.error = str(frame.get("data") or "error")
        elif ftype == "end":
            self.reply.ended = True


def parse_sse_text(text: str) -> ChatReply:
    parser = SSEParser()
    parser.feed(text)
    return parser.close()

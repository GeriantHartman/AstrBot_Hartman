import json

from scripts.rp_bench.sse import SSEParser, parse_sse_text


def _frame(obj) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def test_non_streaming_ignores_duplicate_complete_and_heartbeats():
    text = (
        _frame({"type": "session_id", "session_id": "s"})
        + ": heartbeat\n\n"
        + _frame(
            {"type": "plain", "data": "已将本 session 切换为 5.0", "streaming": False}
        )
        + _frame(
            {
                "type": "complete",
                "data": "已将本 session 切换为 5.0",
                "streaming": False,
            }
        )
        + _frame(
            {
                "type": "agent_stats",
                "data": {"token_usage": {"input_other": 10, "output": 5}},
            }
        )
        + _frame({"type": "end", "data": ""})
    )
    reply = parse_sse_text(text)
    assert reply.text == "已将本 session 切换为 5.0"
    assert reply.ended
    assert reply.agent_stats["token_usage"]["output"] == 5


def test_multiple_messages_joined_with_newline_and_tool_frames_skipped():
    text = (
        _frame({"type": "plain", "data": "开场卡片", "streaming": False})
        + _frame(
            {
                "type": "plain",
                "data": "{...}",
                "streaming": False,
                "chain_type": "tool_call",
            }
        )
        + _frame({"type": "plain", "data": "叙事正文", "streaming": False})
        + _frame({"type": "end"})
    )
    assert parse_sse_text(text).text == "开场卡片\n叙事正文"


def test_streaming_deltas_use_complete_payload():
    text = (
        _frame({"type": "plain", "data": "你", "streaming": True})
        + _frame({"type": "plain", "data": "好", "streaming": True})
        + _frame({"type": "complete", "data": "你好", "streaming": True})
        + _frame({"type": "end"})
    )
    assert parse_sse_text(text).text == "你好"


def test_chunk_boundaries_do_not_matter():
    text = _frame({"type": "plain", "data": "跨块", "streaming": False}) + _frame(
        {"type": "end"}
    )
    parser = SSEParser()
    for i in range(0, len(text), 7):
        parser.feed(text[i : i + 7])
    reply = parser.close()
    assert reply.text == "跨块" and reply.ended

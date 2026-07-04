from plugins.astrbot_plugin_agentic_RPG.handlers.tool_executor import (
    build_execution_result_from_trace,
)


def test_trace_tool_error_becomes_failed_execution_entry():
    result = build_execution_result_from_trace(
        [
            {
                "name": "sync_zone_npcs",
                "args": {"arrive_npcs": ["Elysia"]},
                "raw_text": (
                    '{"ok": false, "error": "arrive_npcs must be a JSON string"}'
                ),
            }
        ]
    )

    assert result.has_errors
    assert result.failed[0].tool == "sync_zone_npcs"
    assert "JSON string" in (result.failed[0].error or "")


def test_trace_tool_success_unwraps_envelope_data():
    result = build_execution_result_from_trace(
        [
            {
                "name": "mark_interacting_npcs",
                "args": {"npc_names": "Elysia"},
                "raw_text": (
                    '{"ok": true, "data": {"marked": ["Elysia"], "count": 1}}'
                ),
            }
        ]
    )

    assert not result.has_errors
    assert result.successful[0].result == {"marked": ["Elysia"], "count": 1}

import json
from types import SimpleNamespace

import pytest

from plugins.astrbot_plugin_agentic_RPG.core.turn_rollback import (
    ForgetPlan,
    TurnRange,
)
from plugins.astrbot_plugin_agentic_RPG.handlers.hooks import HookHandler


class _FakeEvent:
    unified_msg_origin = "default:GroupMessage:session"

    def __init__(self) -> None:
        self.extras = {}

    def set_extra(self, key: str, value) -> None:
        self.extras[key] = value


class _FakeConversationManager:
    def __init__(self, conversation) -> None:
        self.conversation = conversation
        self.updated_history = None

    async def get_conversation(
        self,
        _session_id: str,
        _conversation_id: str,
        create_if_not_exists: bool = False,
    ):
        return self.conversation

    async def update_conversation(
        self,
        _session_id: str,
        _conversation_id: str,
        *,
        history,
    ) -> None:
        self.updated_history = history
        self.conversation.history = json.dumps(history, ensure_ascii=False)


class _FakeRollback:
    def __init__(self) -> None:
        self.executed_plan = None

    async def pop_pending_forget(self, _session_id: str):
        return SimpleNamespace(conversation_id="conv-1", count=1)

    def parse_history(self, history_payload):
        return json.loads(history_payload)

    def build_forget_plan(self, *, session_id: str, history, count: int):
        return ForgetPlan(
            count=count,
            ranges=[
                TurnRange(
                    start=1,
                    end=2,
                    checkpoint_id="cp-1",
                    user_preview="old user",
                    assistant_preview="old assistant",
                )
            ],
            snapshot={"snapshot_path": "snapshot.db"},
            history_start=1,
            history_end=2,
            matched_by_checkpoint=True,
        )

    async def execute_forget(self, *, session_id: str, plan: ForgetPlan) -> None:
        self.executed_plan = plan


@pytest.mark.asyncio
async def test_pending_forget_refreshes_provider_request_contexts():
    original_history = [
        {"role": "system", "content": "kept"},
        {"role": "user", "content": "deleted user"},
        {"role": "assistant", "content": "deleted assistant"},
        {"role": "user", "content": "current user"},
    ]
    expected_history = [original_history[0], original_history[3]]
    conversation = SimpleNamespace(
        cid="conv-1",
        history=json.dumps(original_history, ensure_ascii=False),
    )
    conv_mgr = _FakeConversationManager(conversation)
    rollback = _FakeRollback()
    handler = HookHandler(
        SimpleNamespace(
            turn_rollback=rollback,
            context=SimpleNamespace(conversation_manager=conv_mgr),
        )
    )
    event = _FakeEvent()
    req = SimpleNamespace(
        conversation=conversation,
        contexts=list(original_history),
    )

    await handler._execute_pending_forget_before_turn(event, req)

    assert rollback.executed_plan is not None
    assert conv_mgr.updated_history == expected_history
    assert req.contexts == expected_history
    assert json.loads(req.conversation.history) == expected_history
    assert event.extras["provider_request"] is req

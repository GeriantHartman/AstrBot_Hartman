from types import SimpleNamespace

from plugins.astrbot_plugin_agentic_RPG.handlers.contract_pipeline import (
    ROUTER_POLICY_APPEND,
    TurnContract,
    TurnInput,
    build_narrative_contract_text,
)


def test_router_policy_replaces_python_semantic_gate():
    assert "Python" in ROUTER_POLICY_APPEND
    assert "move_to_zone" in ROUTER_POLICY_APPEND
    assert "execute_camp" in ROUTER_POLICY_APPEND


def test_narrative_contract_no_longer_mentions_python_semantic_gate():
    exec_result = SimpleNamespace(successful=[], failed=[])

    text = build_narrative_contract_text(exec_result=exec_result)

    assert "Commit Gate" not in text
    assert "gateway" not in text.lower()


def test_turn_contract_has_no_semantic_gate_decision_field():
    contract = TurnContract(
        version="4.0",
        turn_input=TurnInput(
            session_id="session",
            user_id="user",
            player_message="hello",
        ),
    )

    assert not any(key.endswith("_decision") for key in contract.to_dict())

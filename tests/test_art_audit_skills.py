"""Offline audit CLI selection, reviewer separation, and trace visibility."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import pytest


@pytest.fixture
def audit_cli(tmp_path):
    """Create isolated mixed-generation ledgers and a CLI runner.

    Args:
        tmp_path: Pytest-managed directory outside active plugin data.

    Returns:
        A callable executing either standalone audit CLI against the fixture.
    """
    index_root = tmp_path / "llm_audit_index"
    index_root.mkdir()
    records = (
        ("discord:room:1", "20261003-100000-zzzzzz", "agent", 10),
        ("discord:room:1", "20261003-100000-aaaaaa", "agent", 20),
        ("legacy:room", "20261002-100000-legacy", "playwright", 2),
        ("legacy:room", "20261002-100000-legacy", "actor", 3),
        ("legacy:room", "20261002-100000-legacy", "scribe", 4),
        ("user:owner", "20261003-110000-review", "user_review", 30),
    )
    for session, turn, stage, written in records:
        key = quote(session, safe="-_.@=")
        directory = tmp_path / "llm_audit" / key
        directory.mkdir(parents=True, exist_ok=True)
        meta = (
            {"published": False, "base_revision": 2}
            if stage == "user_review"
            else {
                "committed": True,
                "tool_trace": [],
                "execution_trace": [{"type": "marker", "text": "TOOL_CONTEXT"}],
            }
        )
        doc = {
            "turn_id": turn,
            "stage": stage,
            "provider_id": "review-provider"
            if stage == "user_review"
            else "main-provider",
            "model": "same-model-name",
            "request": {"prompt": "synthetic input"},
            "audit_view": {"base_revision": 2} if stage == "user_review" else {},
            "response": {"text": "synthetic result", "meta": meta},
        }
        path = directory / f"{turn}-{stage}-{key}.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        os.utime(path, (written, written))
        if stage in {"agent", "actor", "user_review"}:
            index = index_root / f"{key}.jsonl"
            with index.open("a", encoding="utf-8") as stream:
                stream.write("malformed row\n[]\n")
                stream.write(json.dumps({**doc, "response_meta": meta}) + "\n")
            os.utime(index, (written, written))
        os.utime(directory, (written, written))
    scripts = (
        Path(__file__).resolve().parents[1] / ".codex/skills/art-ledger-audit/scripts"
    )

    def run(script, *arguments):
        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(scripts / f"{script}.py"),
                "--data-root",
                str(tmp_path),
                *arguments,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=True,
        )
        return result.stdout

    return run


def test_default_selects_story_when_newest_audit_is_reviewer(audit_cli):
    rows = json.loads(audit_cli("index_summary", "--json"))
    assert len(rows) == 2 and all(row["stage"] == "agent" for row in rows)
    docs = json.loads(audit_cli("turn_detail", "--json"))
    assert docs["agent"]["turn_id"] == "20261003-100000-aaaaaa"
    table = audit_cli("index_summary")
    assert "stage" in table and "main-provider" in table


def test_reviewer_selection_preserves_publication_and_identity(audit_cli):
    rows = json.loads(audit_cli("index_summary", "--stage", "user_review", "--json"))
    assert len(rows) == 1 and rows[0]["provider_id"] == "review-provider"
    assert rows[0]["response_meta"]["published"] is False
    detail = audit_cli(
        "turn_detail", "--stage", "user_review", "--session", "user:owner"
    )
    assert "published=False" in detail and "review result" in detail
    assert "MISSING" not in detail
    assert "UNPUBLISHED" in audit_cli("index_summary", "--stage", "user_review")


def test_legacy_three_stages_are_still_displayed(audit_cli):
    detail = audit_cli("turn_detail", "--stage", "legacy")
    assert all(f"[{stage}]" in detail for stage in ("playwright", "actor", "scribe"))
    assert "MISSING" not in detail
    rows = json.loads(audit_cli("index_summary", "--stage", "legacy", "--json"))
    assert len(rows) == 1 and rows[0]["stage"] == "actor"


@pytest.mark.parametrize("flag", ["--trace", "--full"])
def test_execution_context_is_available_without_json_export(audit_cli, flag):
    assert "TOOL_CONTEXT" not in audit_cli("turn_detail")
    assert "TOOL_CONTEXT" in audit_cli("turn_detail", flag)


def test_limit_is_applied_after_stage_selection(audit_cli):
    rows = json.loads(
        audit_cli("index_summary", "--stage", "agent", "--limit", "1", "--json")
    )
    assert [row["turn_id"] for row in rows] == ["20261003-100000-aaaaaa"]

"""Evidence-backed USER reviews, independent providers, and stable prompt prefixes."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import test_art_agent as agent_tests

from astrbot.core.provider.entities import LLMResponse, ProviderRequest, ProviderType
from plugins.astrbot_plugin_art.core.users import UserProfiles
from plugins.astrbot_plugin_art.layers.agent import run_art_agent

Event = agent_tests.Event
agent_env = agent_tests.agent_env


def reviewer():
    """Build a reviewer that quotes only the supplied user's actual evidence.

    Returns:
        Provider-shaped test double for the independently configured reviewer.
    """

    async def complete(**kwargs):
        payload = json.loads(kwargs["prompt"])
        evidence = payload["new_evidence"][0]
        source = evidence["source_id"]
        entries = [
            {
                "key": "现实职业",
                "category": "identity",
                "value": "用户现实职业是程序员。",
                "basis": "self_report",
                "source_ids": [source],
                "evidence_quotes": [{"source_id": source, "quote": "现实中我是程序员"}],
            }
        ]
        return LLMResponse(
            role="assistant",
            completion_text=json.dumps({"entries": entries}, ensure_ascii=False),
        )

    return SimpleNamespace(
        text_chat=AsyncMock(side_effect=complete),
        get_model=lambda: "review-model",
        meta=lambda: SimpleNamespace(provider_type=ProviderType.CHAT_COMPLETION),
    )


@pytest.mark.asyncio
async def test_protocol_ignores_selected_persona_and_few_shots(agent_env):
    env = agent_env
    incoming = ProviderRequest(
        prompt="hi",
        system_prompt="PERSONA MUST BE ELYSIA ♪ AND USE OLD RPG TOOLS",
        contexts=[{"role": "user", "content": "PERSONA FEW SHOT"}],
    )
    await run_art_agent(env.plugin, env.event, incoming)
    path = next((env.plugin._data_root / "llm_audit").rglob("*-agent-*.json"))
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["request"]["system_prompt"] == env.plugin.assets.prompts.text(
        "agent", "system"
    )
    assert "PERSONA" not in json.dumps(doc["request"])
    assert doc["audit_view"]["persona_policy"] == "ignored_art_protocol_only"


@pytest.mark.asyncio
async def test_review_uses_independent_provider_and_pin_survives_updates(agent_env):
    env = agent_env
    service = env.plugin.user_profiles
    await run_art_agent(
        env.plugin, env.event, ProviderRequest(prompt="现实中我是程序员")
    )
    first = next((env.plugin._data_root / "llm_audit").rglob("*-agent-*.json"))
    frozen = json.loads(first.read_text(encoding="utf-8"))["request"]["contexts"][0][
        "content"
    ]
    other = reviewer()
    env.plugin._config["user_reviewer_provider"] = "dedicated-reviewer"
    env.plugin.context.get_provider_by_id = lambda pid: (
        other if pid == "dedicated-reviewer" else env.provider
    )
    owner = service.owner("discord", "player")
    assert await service.review_once(owner)
    assert other.text_chat.await_count == 1
    assert env.provider.text_chat.await_count == 1
    assert "程序员" in (await service.read(owner))["markdown"]
    assert (
        (service.root / owner / "USER.md")
        .read_text(encoding="utf-8")
        .startswith("# USER")
    )
    await run_art_agent(env.plugin, env.event, ProviderRequest(prompt="陪我聊聊"))
    docs = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (env.plugin._data_root / "llm_audit").rglob("*-agent-*.json")
    ]
    latest = next(doc for doc in docs if doc["request"]["prompt"] == "陪我聊聊")
    assert latest["request"]["contexts"][0]["content"] == frozen
    assert latest["audit_view"]["user_versions"][0]["revision"] == 0
    _ = [result async for result in env.plugin.art_user(env.event, "refresh")]
    await run_art_agent(env.plugin, env.event, ProviderRequest(prompt="新的画像"))
    docs = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (env.plugin._data_root / "llm_audit").rglob("*-agent-*.json")
    ]
    latest = next(doc for doc in docs if doc["request"]["prompt"] == "新的画像")
    assert latest["audit_view"]["user_versions"][0]["revision"] == 1
    assert "程序员" in latest["request"]["contexts"][0]["content"]


@pytest.mark.asyncio
async def test_empty_review_provider_does_not_fall_back_to_foreground(agent_env):
    env = agent_env
    service = env.plugin.user_profiles
    await run_art_agent(
        env.plugin, env.event, ProviderRequest(prompt="现实中我是程序员")
    )
    assert not await service.review_once(service.owner("discord", "player"))
    assert env.provider.text_chat.await_count == 1
    assert not service.tasks


@pytest.mark.asyncio
async def test_late_review_cannot_overwrite_a_user_deletion(agent_env):
    env = agent_env
    service = env.plugin.user_profiles
    owner = service.owner("discord", "player")
    await service.enqueue(
        "discord",
        "player",
        "Player",
        env.event.unified_msg_origin,
        "old",
        "现实中我是程序员",
        "context",
    )
    started, finish = asyncio.Event(), asyncio.Event()
    other = reviewer()
    original = other.text_chat.side_effect

    async def blocked(**kwargs):
        started.set()
        await finish.wait()
        return await original(**kwargs)

    other.text_chat.side_effect = blocked
    env.plugin._config["user_reviewer_provider"] = "review"
    env.plugin.context.get_provider_by_id = lambda _: other
    job = asyncio.create_task(service.review_once(owner))
    await started.wait()
    await service.delete(owner)
    finish.set()
    assert not await job
    assert (await service.read(owner))["entries"] == []


@pytest.mark.asyncio
async def test_forget_retracts_only_its_evidence_and_forces_new_snapshot(agent_env):
    env = agent_env
    service = env.plugin.user_profiles
    sid = env.event.unified_msg_origin
    await run_art_agent(
        env.plugin, env.event, ProviderRequest(prompt="现实中我是程序员")
    )
    other = reviewer()
    env.plugin._config["user_reviewer_provider"] = "review"
    env.plugin.context.get_provider_by_id = lambda pid: (
        other if pid == "review" else env.provider
    )
    owner = service.owner("discord", "player")
    assert await service.review_once(owner)
    assert (await service.read(owner))["entries"]
    _ = [result async for result in env.plugin.art_forget(env.event, 1)]
    assert not (await service.read(owner))["entries"]
    assert (await service.read(owner))["policy_revision"] == 1
    assert await env.store.turns(sid) == []


@pytest.mark.asyncio
async def test_uid_profile_cross_session_and_separate_platform_identity(agent_env):
    env = agent_env
    service = env.plugin.user_profiles
    await service.enqueue(
        "discord",
        "player",
        "Player",
        "source-story",
        "source-turn",
        "现实中我是程序员",
        "context",
    )
    other = reviewer()
    env.plugin._config["user_reviewer_provider"] = "review"
    env.plugin.context.get_provider_by_id = lambda pid: (
        other if pid == "review" else env.provider
    )
    owner = service.owner("discord", "player")
    assert await service.review_once(owner)
    second = Event("discord:FriendMessage:second-world")
    await env.conversations.new_conversation(second.unified_msg_origin)
    await env.state.init_session(second.unified_msg_origin)
    await env.store.initialize(second.unified_msg_origin)
    await run_art_agent(env.plugin, second, ProviderRequest(prompt="hi"))
    conn = await env.db.get_connection(second.unified_msg_origin)
    async with conn.execute("SELECT content FROM user_snapshots") as cursor:
        snapshot = json.loads((await cursor.fetchone())[0])
    assert "程序员" in snapshot["markdown"]
    assert not (await service.read(service.owner("qq", "player")))["entries"]
    _ = [result async for result in env.plugin.art_reset(second)]
    assert (await service.read(owner))["entries"]


@pytest.mark.asyncio
async def test_profile_claims_require_user_quotes_and_keep_pending_on_failure(
    agent_env,
):
    env = agent_env
    service = env.plugin.user_profiles
    await service.enqueue(
        "discord",
        "player",
        "Player",
        "story",
        "turn",
        "抱抱我",
        "主模型编造：用户是医生",
    )
    other = reviewer()
    env.plugin._config["user_reviewer_provider"] = "review"
    env.plugin.context.get_provider_by_id = lambda _: other
    owner = service.owner("discord", "player")
    assert not await service.review_once(owner)
    assert not (await service.read(owner))["entries"]
    conn = await service.connect()
    async with conn.execute("SELECT processed FROM evidence") as cursor:
        assert (await cursor.fetchone())[0] == 0


@pytest.mark.asyncio
async def test_pending_evidence_resumes_after_restart_and_does_not_block_frontend(
    agent_env,
):
    env = agent_env
    service = env.plugin.user_profiles
    await service.enqueue(
        "discord", "player", "Player", "story", "turn", "现实中我是程序员", "context"
    )
    await service.close()
    other = reviewer()
    env.plugin._config.update(user_reviewer_provider="review", user_review_min_turns=1)
    env.plugin.context.get_provider_by_id = lambda pid: (
        other if pid == "review" else env.provider
    )
    replacement = UserProfiles(
        service.root,
        env.plugin.context,
        env.assets if hasattr(env, "assets") else env.plugin.assets,
        env.plugin._config,
        env.plugin.audit_ledger,
    )
    env.plugin.user_profiles = replacement
    await replacement.resume()
    await asyncio.wait_for(asyncio.gather(*replacement.tasks.values()), timeout=3)
    assert (await replacement.read(replacement.owner("discord", "player")))["entries"]
    await replacement.close()


@pytest.mark.asyncio
async def test_review_provider_wait_does_not_hold_foreground_locks(agent_env):
    env = agent_env
    service = env.plugin.user_profiles
    await service.enqueue(
        "discord", "player", "Player", "story", "turn", "现实中我是程序员", "context"
    )
    started, release = asyncio.Event(), asyncio.Event()
    other = reviewer()
    original = other.text_chat.side_effect

    async def slow(**kwargs):
        started.set()
        await release.wait()
        return await original(**kwargs)

    other.text_chat.side_effect = slow
    env.plugin._config["user_reviewer_provider"] = "review"
    env.plugin.context.get_provider_by_id = lambda pid: (
        other if pid == "review" else env.provider
    )
    job = asyncio.create_task(service.review_once(service.owner("discord", "player")))
    await started.wait()
    reply, _ = await asyncio.wait_for(
        run_art_agent(env.plugin, env.event, ProviderRequest(prompt="hi")), timeout=2
    )
    assert reply and not job.done()
    release.set()
    assert await job


@pytest.mark.asyncio
async def test_multi_uid_handbooks_are_labeled_and_withdrawn_original_not_reassigned(
    agent_env,
):
    env = agent_env
    await run_art_agent(
        env.plugin, env.event, ProviderRequest(prompt="现实中我是程序员")
    )
    second = Event(env.event.unified_msg_origin)
    second.get_sender_id = lambda: "second-player"
    second.get_sender_name = lambda: "Second"
    env.provider.text_chat.side_effect = [
        LLMResponse(
            role="assistant",
            tools_call_name=["art_rewind"],
            tools_call_args=[{"count": 1}],
            tools_call_ids=["undo"],
        ),
        LLMResponse(role="assistant", completion_text="replacement"),
    ]
    await run_art_agent(
        env.plugin, second, ProviderRequest(prompt="上一轮不算，重新回复")
    )
    service = env.plugin.user_profiles
    conn = await service.connect()
    async with conn.execute(
        "SELECT player_input FROM evidence WHERE owner = ? AND valid = 1",
        (service.owner("discord", "second-player"),),
    ) as cursor:
        inputs = [row[0] for row in await cursor.fetchall()]
    assert inputs == ["上一轮不算，重新回复"]
    docs = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (env.plugin._data_root / "llm_audit").rglob("*-agent-*.json")
    ]
    doc = next(
        doc for doc in docs if doc["request"]["prompt"] == "上一轮不算，重新回复"
    )
    assert {item["uid"] for item in doc["audit_view"]["user_versions"]} == {
        "player",
        "second-player",
    }
    assert "版本固定的 UID" in doc["request"]["contexts"][0]["content"]


@pytest.mark.asyncio
async def test_snapshot_refresh_window_and_explicit_deletion(agent_env, monkeypatch):
    env = agent_env
    service = env.plugin.user_profiles
    sid = env.event.unified_msg_origin
    await run_art_agent(
        env.plugin, env.event, ProviderRequest(prompt="现实中我是程序员")
    )
    other = reviewer()
    env.plugin._config["user_reviewer_provider"] = "review"
    env.plugin.context.get_provider_by_id = lambda _: other
    owner = service.owner("discord", "player")
    assert await service.review_once(owner)
    conv = await env.plugin._ensure_conversation(sid)
    participants = [{"owner": owner, "uid": "player", "name": "Player"}]
    pinned = await service.snapshot(env.store, sid, conv.cid, participants)
    assert pinned[0]["revision"] == 0
    conn = await env.db.get_connection(sid)
    await conn.execute("UPDATE user_snapshots SET loaded_at = 0")
    await conn.commit()
    fresh = await service.snapshot(env.store, sid, conv.cid, participants)
    assert fresh[0]["revision"] == 1
    await service.delete(owner, "现实职业")
    deleted = await service.snapshot(env.store, sid, conv.cid, participants)
    assert "用户现实职业是程序员" not in deleted[0]["markdown"]


@pytest.mark.asyncio
async def test_queue_reconciliation_captures_missed_commit_and_ignores_opening(
    agent_env,
):
    env = agent_env
    service = env.plugin.user_profiles
    original = service.enqueue
    service.enqueue = AsyncMock(side_effect=OSError("queue unavailable"))
    await run_art_agent(
        env.plugin, env.event, ProviderRequest(prompt="现实中我是程序员")
    )
    service.enqueue = original
    service.reconciled.clear()
    await service.reconcile_session(env.store, env.event.unified_msg_origin)
    conn = await service.connect()
    async with conn.execute("SELECT COUNT(*) FROM evidence") as cursor:
        assert (await cursor.fetchone())[0] == 1
    opening = Event(env.event.unified_msg_origin)
    opening.set_extra("art_opening_turn", True)
    await run_art_agent(env.plugin, opening, ProviderRequest(prompt="world opening"))
    service.reconciled.clear()
    await service.reconcile_session(env.store, env.event.unified_msg_origin)
    async with conn.execute("SELECT COUNT(*) FROM evidence") as cursor:
        assert (await cursor.fetchone())[0] == 1


@pytest.mark.asyncio
async def test_review_write_failure_rolls_back_profile_and_processing(agent_env):
    env = agent_env
    service = env.plugin.user_profiles
    await service.enqueue(
        "discord", "player", "Player", "story", "turn", "现实中我是程序员", "context"
    )
    other = reviewer()
    env.plugin._config["user_reviewer_provider"] = "review"
    env.plugin.context.get_provider_by_id = lambda _: other
    conn = await service.connect()
    execute = conn.execute

    def fail_processing(sql, *args, **kwargs):
        if "UPDATE evidence SET processed = 1 WHERE source_id" in sql:
            raise OSError("profile publication failed halfway through")
        return execute(sql, *args, **kwargs)

    conn.execute = fail_processing
    owner = service.owner("discord", "player")
    assert not await service.review_once(owner)
    conn.execute = execute
    assert (await service.read(owner))["entries"] == []
    async with conn.execute("SELECT processed FROM evidence") as cursor:
        assert (await cursor.fetchone())[0] == 0
    assert await service.review_once(owner)
    assert (await service.read(owner))["entries"]


@pytest.mark.asyncio
async def test_speaker_metadata_commit_failure_recovers_pending_round(agent_env):
    env = agent_env
    sid = env.event.unified_msg_origin
    before = await env.store.snapshot(sid)
    conn = await env.db.get_connection(sid)
    commit = conn.commit
    failed = False

    async def fail_metadata_commit():
        nonlocal failed
        async with conn.execute(
            "SELECT author_uid FROM art_turns WHERE status = 'pending'"
        ) as cursor:
            pending = await cursor.fetchone()
        if pending and pending[0] and not failed:
            failed = True
            raise OSError("metadata commit failure")
        await commit()

    conn.commit = fail_metadata_commit
    with pytest.raises(OSError, match="metadata commit failure"):
        await run_art_agent(env.plugin, env.event, ProviderRequest(prompt="hi"))
    conn.commit = commit
    assert await env.store.snapshot(sid) == before
    rounds = await env.store.turns(sid, active_only=False)
    assert rounds[-1]["status"] == "failed"
    assert env.provider.text_chat.await_count == 0


@pytest.mark.asyncio
async def test_handbook_load_failure_does_not_prevent_story_commit(agent_env):
    env = agent_env
    env.plugin.user_profiles.snapshot = AsyncMock(
        side_effect=OSError("USER unavailable")
    )
    reply, _ = await run_art_agent(env.plugin, env.event, ProviderRequest(prompt="hi"))
    assert reply
    assert (await env.store.turns(env.event.unified_msg_origin))[-1][
        "status"
    ] == "committed"


@pytest.mark.asyncio
async def test_retraction_reassesses_combined_entry_and_keeps_unrelated_session(
    agent_env,
):
    service = agent_env.plugin.user_profiles
    for story, message in (
        ("story-one", "现实中我是程序员"),
        ("story-two", "我喜欢喝茶"),
    ):
        await service.enqueue(
            "discord", "player", "Player", story, "turn", message, "context"
        )
    conn = await service.connect()
    async with conn.execute("SELECT * FROM evidence ORDER BY session_id") as cursor:
        sources = [dict(row) for row in await cursor.fetchall()]
    owner = service.owner("discord", "player")
    entries = [
        {
            "key": "综合",
            "category": "identity",
            "basis": "self_report",
            "value": "用户是喜欢喝茶的程序员。",
            "source_ids": [row["source_id"] for row in sources],
            "evidence_quotes": [
                {"source_id": row["source_id"], "quote": row["player_input"]}
                for row in sources
            ],
        },
        {
            "key": "饮品",
            "category": "habits",
            "basis": "self_report",
            "value": "用户喜欢喝茶。",
            "source_ids": [sources[1]["source_id"]],
            "evidence_quotes": [
                {"source_id": sources[1]["source_id"], "quote": "我喜欢喝茶"}
            ],
        },
    ]
    await conn.execute(
        "UPDATE users SET entries = ? WHERE owner = ?", (json.dumps(entries), owner)
    )
    await conn.execute("UPDATE evidence SET processed = 1")
    await conn.commit()
    await service.invalidate("story-one", ["turn"])
    assert [entry["key"] for entry in (await service.read(owner))["entries"]] == [
        "饮品"
    ]
    async with conn.execute(
        "SELECT valid, processed FROM evidence WHERE session_id = 'story-two'"
    ) as cursor:
        assert tuple(await cursor.fetchone()) == (1, 0)

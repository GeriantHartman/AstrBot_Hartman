from unittest.mock import AsyncMock

import pytest

import astrbot.core.message.components as Comp
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.pipeline.respond.stage import RespondStage
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    MAX_ONEBOT_FORWARD_NODE_TEXT_CHARS,
    MAX_ONEBOT_TEXT_CHARS,
    AiocqhttpMessageEvent,
)


def test_poke_to_dict_matches_onebot_v11_segment_format():
    poke = Comp.Poke(type="126", id=2003)
    assert poke.toDict() == {
        "type": "poke",
        "data": {"type": "126", "id": "2003"},
    }


@pytest.mark.asyncio
async def test_respond_stage_treats_poke_with_target_as_non_empty():
    stage = RespondStage()
    chain = [Comp.Poke(type="126", id=2003)]
    assert await stage._is_empty_message_chain(chain) is False


@pytest.mark.asyncio
async def test_aiocqhttp_parse_json_outputs_standard_poke_data():
    chain = MessageChain([Comp.Poke(type="126", id=2003)])
    data = await AiocqhttpMessageEvent._parse_onebot_json(chain)
    assert data == [{"type": "poke", "data": {"type": "126", "id": "2003"}}]


@pytest.mark.asyncio
async def test_aiocqhttp_send_message_dispatches_onebot_v11_poke_payload():
    bot = AsyncMock()
    chain = MessageChain([Comp.Poke(type="126", id=2003)])

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=chain,
        event=None,
        is_group=True,
        session_id="123456",
    )

    bot.send_group_msg.assert_awaited_once_with(
        group_id=123456,
        message=[{"type": "poke", "data": {"type": "126", "id": "2003"}}],
    )


def test_aiocqhttp_splits_long_plain_messages_before_dispatch():
    text = "A" * (MAX_ONEBOT_TEXT_CHARS + 20)
    chains = AiocqhttpMessageEvent._split_plain_chains(MessageChain([Comp.Plain(text)]))

    assert len(chains) == 2
    assert all(len(chain.chain[0].text) <= MAX_ONEBOT_TEXT_CHARS for chain in chains)


def test_aiocqhttp_splits_long_forward_nodes_before_dispatch():
    text = "A" * (MAX_ONEBOT_FORWARD_NODE_TEXT_CHARS + 20)
    nodes = AiocqhttpMessageEvent._split_nodes(
        Comp.Nodes([Comp.Node([Comp.Plain(text)], name="AstrBot", uin="10000")])
    )

    assert len(nodes.nodes) == 2
    assert all(
        len(node.content[0].text) <= MAX_ONEBOT_FORWARD_NODE_TEXT_CHARS
        for node in nodes.nodes
    )

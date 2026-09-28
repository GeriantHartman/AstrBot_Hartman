"""Deterministic Splendor rules engine."""

from __future__ import annotations

import itertools
import json
import random
import re
from dataclasses import dataclass, field
from typing import Any

from .constants import (
    CARD_SPECS,
    COLORS,
    COLOR_LABELS,
    MARKET_SIZE_PER_TIER,
    NOBLE_COUNT_BY_PLAYER_COUNT,
    NOBLE_SPECS,
    RESERVE_LIMIT,
    TOKEN_BANK_BY_PLAYER_COUNT,
    TOKEN_COLORS,
    TOKEN_LIMIT,
    WIN_SCORE,
    CardSpec,
)
from .models import PHASE_FINISHED, PHASE_PLAYING, SplendorPlayer, SplendorRoom


@dataclass
class ActionResult:
    """The result of a deterministic engine action."""

    ok: bool
    messages: list[str] = field(default_factory=list)
    game_finished: bool = False

    @property
    def text(self) -> str:
        return "\n".join(self.messages)


class SplendorEngine:
    """Applies classic Splendor rules to a room snapshot."""

    def start_game(self, room: SplendorRoom) -> ActionResult:
        if room.phase != "waiting":
            return ActionResult(False, ["这局璀璨宝石已经开始了。"])
        if room.player_count != room.target_players:
            return ActionResult(
                False, [f"人数不足：{room.player_count}/{room.target_players}。"]
            )
        if room.target_players not in TOKEN_BANK_BY_PLAYER_COUNT:
            return ActionResult(False, ["璀璨宝石只支持 2-4 人。"])

        rng = random.Random(room.seed)
        ordered_players = list(room.players.values())
        rng.shuffle(ordered_players)
        for index, player in enumerate(ordered_players, start=1):
            player.number = index
        room.turn_order = [player.id for player in ordered_players]
        room.current_player_index = 0
        room.bank = dict(TOKEN_BANK_BY_PLAYER_COUNT[room.target_players])

        room.decks = {1: [], 2: [], 3: []}
        for card_id, spec in CARD_SPECS.items():
            room.decks[spec.tier].append(card_id)
        for cards in room.decks.values():
            rng.shuffle(cards)
        room.market = {1: [], 2: [], 3: []}
        for tier in (1, 2, 3):
            self._draw_to_market(room, tier)

        noble_ids = list(NOBLE_SPECS.keys())
        rng.shuffle(noble_ids)
        room.nobles = noble_ids[: NOBLE_COUNT_BY_PLAYER_COUNT[room.target_players]]
        room.phase = PHASE_PLAYING
        room.log("璀璨宝石开局。")
        first_player = room.current_player
        return ActionResult(
            True,
            [
                "璀璨宝石开局。",
                f"起始玩家：{first_player.display_name if first_player else '未知'}",
            ],
        )

    def take_tokens(
        self, room: SplendorRoom, player_id: str, colors: list[str]
    ) -> ActionResult:
        check = self._check_turn(room, player_id)
        if not check.ok:
            return check
        if not colors:
            return ActionResult(False, ["请指定要拿的宝石颜色。"])
        if any(color == "gold" for color in colors):
            return ActionResult(False, ["金币只能通过保留发展卡获得。"])

        counts = {color: colors.count(color) for color in set(colors)}
        if len(colors) == 3 and len(counts) == 3:
            for color in colors:
                if room.bank.get(color, 0) <= 0:
                    return ActionResult(False, [f"{COLOR_LABELS[color]}宝石不足。"])
        elif len(colors) == 2 and len(counts) == 1:
            color = colors[0]
            if room.bank.get(color, 0) < 4:
                return ActionResult(
                    False,
                    [f"拿两枚同色宝石时，该颜色银行中必须至少有 4 枚。"],
                )
        else:
            return ActionResult(False, ["拿宝石必须是 3 枚不同色，或 2 枚同色。"])

        player = room.players[player_id]
        for color in colors:
            room.bank[color] -= 1
            player.tokens[color] += 1

        label = "、".join(COLOR_LABELS[color] for color in colors)
        messages = [f"{player.display_name} 拿取宝石：{label}。"]
        room.log(messages[0])
        return self._after_token_gain(room, player, messages)

    def discard_tokens(
        self, room: SplendorRoom, player_id: str, colors: list[str]
    ) -> ActionResult:
        if room.phase != PHASE_PLAYING:
            return ActionResult(False, ["当前没有进行中的璀璨宝石。"])
        if room.pending_discard_player_id != player_id:
            return ActionResult(False, ["现在不需要你丢弃宝石。"])
        player = room.players.get(player_id)
        if not player:
            return ActionResult(False, ["你不在这局璀璨宝石中。"])
        colors = [str(color).strip().lower() for color in colors if str(color).strip()]
        if not colors:
            return ActionResult(False, ["请指定要丢弃的宝石颜色。"])

        counts = {color: colors.count(color) for color in set(colors)}
        for color, amount in counts.items():
            if color not in TOKEN_COLORS:
                return ActionResult(False, [f"无法识别宝石颜色：{color}。"])
            if player.tokens.get(color, 0) < amount:
                return ActionResult(
                    False, [f"你没有足够可丢弃的{COLOR_LABELS[color]}宝石。"]
                )
        for color, amount in counts.items():
            player.tokens[color] -= amount
            room.bank[color] += amount

        if player.token_total > TOKEN_LIMIT:
            return ActionResult(
                True,
                [
                    f"已丢弃 {len(colors)} 枚宝石；你仍有 {player.token_total} 枚，"
                    f"还需要降到 {TOKEN_LIMIT} 枚以内。"
                ],
            )

        room.pending_discard_player_id = ""
        label = "、".join(COLOR_LABELS[color] for color in colors)
        messages = [f"{player.display_name} 丢弃宝石：{label}。"]
        room.log(messages[0])
        return self._finish_turn(room, player, messages)

    def reserve_card(
        self, room: SplendorRoom, player_id: str, selector: str
    ) -> ActionResult:
        check = self._check_turn(room, player_id)
        if not check.ok:
            return check
        player = room.players[player_id]
        if len(player.reserved_cards) >= RESERVE_LIMIT:
            return ActionResult(False, [f"每名玩家最多保留 {RESERVE_LIMIT} 张牌。"])

        resolved = self.resolve_card_selector(room, player, selector, allow_deck=True)
        if not resolved.ok:
            return resolved
        info = resolved.messages[0]
        data = resolved_data(info)
        if data["kind"] == "reserved":
            return ActionResult(False, ["不能再次保留已经在手中的牌。"])

        card_id = data["card_id"]
        player.reserved_cards.append(card_id)
        if data["kind"] == "market":
            room.market[data["tier"]].pop(data["slot"] - 1)
            self._draw_to_market(room, data["tier"])
        else:
            room.decks[data["tier"]].pop(0)

        messages = [f"{player.display_name} 保留 {self.format_card(card_id)}。"]
        if room.bank["gold"] > 0:
            room.bank["gold"] -= 1
            player.tokens["gold"] += 1
            messages.append("获得 1 枚金币。")
        else:
            messages.append("金币已空，本次保留没有获得金币。")
        room.log(" ".join(messages))
        return self._after_token_gain(room, player, messages)

    def buy_card(
        self, room: SplendorRoom, player_id: str, selector: str
    ) -> ActionResult:
        check = self._check_turn(room, player_id)
        if not check.ok:
            return check
        player = room.players[player_id]
        resolved = self.resolve_card_selector(room, player, selector, allow_deck=False)
        if not resolved.ok:
            return resolved
        data = resolved_data(resolved.messages[0])
        if data["kind"] == "deck":
            return ActionResult(False, ["不能直接购买牌堆顶牌。"])
        card_id = data["card_id"]
        if not self.can_afford(player, card_id):
            return ActionResult(False, [f"你还买不起 {self.format_card(card_id)}。"])

        payment = self.payment_for(player, card_id)
        for color, amount in payment.items():
            player.tokens[color] -= amount
            room.bank[color] += amount

        if data["kind"] == "market":
            room.market[data["tier"]].pop(data["slot"] - 1)
            self._draw_to_market(room, data["tier"])
        elif data["kind"] == "reserved":
            player.reserved_cards.pop(data["slot"] - 1)

        spec = CARD_SPECS[card_id]
        player.purchased_cards.append(card_id)
        player.bonuses[spec.color] += 1
        paid_text = self.format_counts(payment) or "免费"
        messages = [
            f"{player.display_name} 购买 {self.format_card(card_id)}，支付 {paid_text}。"
        ]
        room.log(messages[0])

        eligible_nobles = [
            noble_id for noble_id in room.nobles if self.can_claim_noble(player, noble_id)
        ]
        if len(eligible_nobles) == 1:
            messages.append(self._claim_noble(room, player, eligible_nobles[0]))
            return self._finish_turn(room, player, messages)
        if len(eligible_nobles) > 1:
            room.pending_noble_player_id = player_id
            room.pending_noble_ids = eligible_nobles
            choices = "、".join(
                f"{noble_id}({self.format_noble(noble_id)})"
                for noble_id in eligible_nobles
            )
            messages.append(f"你满足多个贵族访问条件，请选择一个：{choices}")
            return ActionResult(True, messages)
        return self._finish_turn(room, player, messages)

    def choose_noble(
        self, room: SplendorRoom, player_id: str, noble_selector: str
    ) -> ActionResult:
        if room.phase != PHASE_PLAYING:
            return ActionResult(False, ["当前没有进行中的璀璨宝石。"])
        if room.pending_noble_player_id != player_id:
            return ActionResult(False, ["现在不需要你选择贵族。"])
        player = room.players.get(player_id)
        if not player:
            return ActionResult(False, ["你不在这局璀璨宝石中。"])
        noble_id = self.normalize_noble_selector(noble_selector)
        if noble_id not in room.pending_noble_ids:
            return ActionResult(False, ["请选择本次可访问的贵族编号。"])

        room.pending_noble_player_id = ""
        room.pending_noble_ids = []
        messages = [self._claim_noble(room, player, noble_id)]
        return self._finish_turn(room, player, messages)

    def apply_action(
        self, room: SplendorRoom, player_id: str, action: dict[str, Any]
    ) -> ActionResult:
        name = str(action.get("action") or "").strip().lower()
        if name == "take":
            return self.take_tokens(room, player_id, list(action.get("colors") or []))
        if name == "discard":
            return self.discard_tokens(room, player_id, list(action.get("colors") or []))
        if name == "reserve":
            return self.reserve_card(room, player_id, str(action.get("selector") or ""))
        if name == "buy":
            return self.buy_card(room, player_id, str(action.get("selector") or ""))
        if name == "choose_noble":
            return self.choose_noble(
                room, player_id, str(action.get("noble_id") or action.get("selector") or "")
            )
        return ActionResult(False, ["无法识别这个璀璨宝石动作。"])

    def available_actions(
        self, room: SplendorRoom, player_id: str
    ) -> list[dict[str, Any]]:
        player = room.players.get(player_id)
        if not player or room.phase != PHASE_PLAYING:
            return []
        if room.pending_discard_player_id == player_id:
            excess = max(0, player.token_total - TOKEN_LIMIT)
            return self._discard_actions(player, excess)
        if room.pending_noble_player_id == player_id:
            return [
                {
                    "action": "choose_noble",
                    "noble_id": noble_id,
                    "label": f"选择贵族 {noble_id}: {self.format_noble(noble_id)}",
                }
                for noble_id in room.pending_noble_ids
            ]
        if room.current_player is not player:
            return []

        actions: list[dict[str, Any]] = []
        for tier in (1, 2, 3):
            for slot, card_id in enumerate(room.market[tier], start=1):
                selector = f"T{tier}-{slot}"
                if self.can_afford(player, card_id):
                    actions.append(
                        {
                            "action": "buy",
                            "selector": selector,
                            "label": f"购买 {selector}: {self.format_card(card_id)}",
                        }
                    )
                if len(player.reserved_cards) < RESERVE_LIMIT:
                    actions.append(
                        {
                            "action": "reserve",
                            "selector": selector,
                            "label": f"保留 {selector}: {self.format_card(card_id)}",
                        }
                    )
            if room.decks[tier] and len(player.reserved_cards) < RESERVE_LIMIT:
                actions.append(
                    {
                        "action": "reserve",
                        "selector": f"T{tier}",
                        "label": f"盲保留 T{tier} 牌堆顶牌",
                    }
                )
        for index, card_id in enumerate(player.reserved_cards, start=1):
            if self.can_afford(player, card_id):
                actions.append(
                    {
                        "action": "buy",
                        "selector": f"R{index}",
                        "label": f"购买预留 R{index}: {self.format_card(card_id)}",
                    }
                )

        available_colors = [color for color in COLORS if room.bank[color] > 0]
        for colors in itertools.combinations(available_colors, 3):
            actions.append(
                {
                    "action": "take",
                    "colors": list(colors),
                    "label": "拿 3 枚不同色宝石："
                    + "、".join(COLOR_LABELS[color] for color in colors),
                }
            )
        for color in COLORS:
            if room.bank[color] >= 4:
                actions.append(
                    {
                        "action": "take",
                        "colors": [color, color],
                        "label": f"拿 2 枚{COLOR_LABELS[color]}宝石",
                    }
                )
        return actions

    def can_afford(self, player: SplendorPlayer, card_id: str) -> bool:
        due = self.discounted_cost(player, card_id)
        gold_needed = 0
        for color, amount in due.items():
            gold_needed += max(0, amount - player.tokens.get(color, 0))
        return gold_needed <= player.tokens.get("gold", 0)

    def discounted_cost(
        self, player: SplendorPlayer, card_id: str
    ) -> dict[str, int]:
        spec = CARD_SPECS[card_id]
        return {
            color: max(0, spec.cost[color] - player.bonuses.get(color, 0))
            for color in COLORS
        }

    def payment_for(self, player: SplendorPlayer, card_id: str) -> dict[str, int]:
        due = self.discounted_cost(player, card_id)
        payment = {color: 0 for color in COLORS}
        payment["gold"] = 0
        for color in COLORS:
            colored = min(player.tokens.get(color, 0), due[color])
            payment[color] = colored
            due[color] -= colored
        payment["gold"] = sum(due.values())
        return {color: amount for color, amount in payment.items() if amount}

    def can_claim_noble(self, player: SplendorPlayer, noble_id: str) -> bool:
        noble = NOBLE_SPECS[noble_id]
        return all(
            player.bonuses.get(color, 0) >= required
            for color, required in noble.requirement.items()
        )

    def score_for(self, player: SplendorPlayer) -> int:
        card_points = sum(CARD_SPECS[card_id].points for card_id in player.purchased_cards)
        noble_points = sum(NOBLE_SPECS[noble_id].points for noble_id in player.nobles)
        return card_points + noble_points

    def normalize_noble_selector(self, value: str) -> str:
        text = str(value or "").strip().upper()
        if text.startswith("N") and text[1:].isdigit():
            return f"N{int(text[1:])}"
        if text.isdigit():
            return f"N{int(text)}"
        return text

    def resolve_card_selector(
        self,
        room: SplendorRoom,
        player: SplendorPlayer,
        selector: str,
        allow_deck: bool = False,
    ) -> ActionResult:
        text = str(selector or "").strip().upper().replace(" ", "")
        if not text:
            return ActionResult(False, ["请指定牌位，例如 T1-2、T3、R1。"])

        reserved_match = re.fullmatch(r"R(\d+)", text)
        if reserved_match:
            slot = int(reserved_match.group(1))
            if not 1 <= slot <= len(player.reserved_cards):
                return ActionResult(False, ["没有这个预留牌编号。"])
            return ActionResult(
                True,
                [
                    encode_resolved(
                        {
                            "kind": "reserved",
                            "slot": slot,
                            "card_id": player.reserved_cards[slot - 1],
                        }
                    )
                ],
            )

        market_match = re.fullmatch(r"(?:T|L)?([123])[-_.]?([1-4])", text)
        if market_match:
            tier = int(market_match.group(1))
            slot = int(market_match.group(2))
            if slot > len(room.market[tier]):
                return ActionResult(False, ["这个市场牌位目前没有牌。"])
            return ActionResult(
                True,
                [
                    encode_resolved(
                        {
                            "kind": "market",
                            "tier": tier,
                            "slot": slot,
                            "card_id": room.market[tier][slot - 1],
                        }
                    )
                ],
            )

        deck_match = re.fullmatch(r"(?:T|L)?([123])(?:牌堆|DECK)?", text)
        if deck_match and allow_deck:
            tier = int(deck_match.group(1))
            if not room.decks[tier]:
                return ActionResult(False, [f"T{tier} 牌堆已经空了。"])
            return ActionResult(
                True,
                [
                    encode_resolved(
                        {
                            "kind": "deck",
                            "tier": tier,
                            "card_id": room.decks[tier][0],
                        }
                    )
                ],
            )

        return ActionResult(False, ["无法识别牌位，请使用 T1-1、T2-4、T3 或 R1。"])

    def format_card(self, card_id: str) -> str:
        spec = CARD_SPECS[card_id]
        return (
            f"{COLOR_LABELS[spec.color]}卡 {spec.points}分 "
            f"成本[{self.format_counts(spec.cost)}]"
        )

    def format_noble(self, noble_id: str) -> str:
        noble = NOBLE_SPECS[noble_id]
        return f"{noble.points}分 要[{self.format_counts(noble.requirement)}]"

    @staticmethod
    def format_counts(counts: dict[str, int]) -> str:
        parts = [
            f"{COLOR_LABELS[color]}{amount}"
            for color, amount in counts.items()
            if amount > 0
        ]
        return " ".join(parts)

    def _check_turn(self, room: SplendorRoom, player_id: str) -> ActionResult:
        if room.phase != PHASE_PLAYING:
            return ActionResult(False, ["当前没有进行中的璀璨宝石。"])
        if room.pending_discard_player_id:
            return ActionResult(False, ["请先让当前玩家丢弃宝石到 10 枚以内。"])
        if room.pending_noble_player_id:
            return ActionResult(False, ["请先让当前玩家选择来访贵族。"])
        player = room.players.get(player_id)
        if not player:
            return ActionResult(False, ["你不在这局璀璨宝石中。"])
        if room.current_player is not player:
            current = room.current_player
            name = current.display_name if current else "未知玩家"
            return ActionResult(False, [f"现在轮到 {name} 行动。"])
        return ActionResult(True)

    def _after_token_gain(
        self, room: SplendorRoom, player: SplendorPlayer, messages: list[str]
    ) -> ActionResult:
        if player.token_total > TOKEN_LIMIT:
            room.pending_discard_player_id = player.id
            excess = player.token_total - TOKEN_LIMIT
            messages.append(f"你现在有 {player.token_total} 枚宝石，需要丢弃 {excess} 枚。")
            return ActionResult(True, messages)
        return self._finish_turn(room, player, messages)

    def _finish_turn(
        self, room: SplendorRoom, player: SplendorPlayer, messages: list[str]
    ) -> ActionResult:
        score = self.score_for(player)
        if score >= WIN_SCORE and not room.final_round_active:
            room.final_round_active = True
            room.final_round_trigger_player_id = player.id
            messages.append(
                f"{player.display_name} 达到 {score} 分，触发最终轮；本轮剩余玩家行动后结算。"
            )

        actor_index = room.current_player_index
        if room.final_round_active and actor_index == len(room.turn_order) - 1:
            messages.extend(self._finish_game(room))
            return ActionResult(True, messages, game_finished=True)

        room.current_player_index = (room.current_player_index + 1) % len(room.turn_order)
        current = room.current_player
        if current:
            messages.append(f"轮到 {current.display_name}。")
        return ActionResult(True, messages)

    def _finish_game(self, room: SplendorRoom) -> list[str]:
        room.phase = PHASE_FINISHED
        scores = {player_id: self.score_for(player) for player_id, player in room.players.items()}
        high_score = max(scores.values()) if scores else 0
        contenders = [
            player_id for player_id, score in scores.items() if score == high_score
        ]
        fewest_cards = min(
            room.players[player_id].card_count for player_id in contenders
        )
        winners = [
            player_id
            for player_id in contenders
            if room.players[player_id].card_count == fewest_cards
        ]
        room.winner_ids = winners
        winner_names = "、".join(room.players[player_id].display_name for player_id in winners)
        room.log(f"璀璨宝石结束，胜者：{winner_names}。")
        return [
            "最终轮结束，璀璨宝石结算。",
            f"胜者：{winner_names}（{high_score} 分，买牌 {fewest_cards} 张）。",
        ]

    def _claim_noble(
        self, room: SplendorRoom, player: SplendorPlayer, noble_id: str
    ) -> str:
        room.nobles.remove(noble_id)
        player.nobles.append(noble_id)
        message = f"{player.display_name} 获得贵族 {noble_id}：{self.format_noble(noble_id)}。"
        room.log(message)
        return message

    def _draw_to_market(self, room: SplendorRoom, tier: int) -> None:
        while (
            len(room.market[tier]) < MARKET_SIZE_PER_TIER
            and room.decks[tier]
        ):
            room.market[tier].append(room.decks[tier].pop(0))

    def _discard_actions(self, player: SplendorPlayer, count: int) -> list[dict[str, Any]]:
        if count <= 0:
            return []
        token_pool: list[str] = []
        for color in TOKEN_COLORS:
            token_pool.extend([color] * player.tokens.get(color, 0))

        actions: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()
        for colors in itertools.combinations(token_pool, count):
            key = tuple(colors)
            if key in seen:
                continue
            seen.add(key)
            label = "、".join(COLOR_LABELS[color] for color in colors)
            actions.append(
                {
                    "action": "discard",
                    "colors": list(colors),
                    "label": f"丢弃 {label} 到 {TOKEN_LIMIT} 枚以内",
                }
            )
        return actions

    def _suggest_discards(
        self, player: SplendorPlayer, count: int
    ) -> list[str]:
        colors_by_amount = sorted(
            (color for color, amount in player.tokens.items() if amount > 0),
            key=lambda color: (
                color == "gold",
                player.tokens[color],
                color,
            ),
            reverse=True,
        )
        discards: list[str] = []
        for color in colors_by_amount:
            while player.tokens[color] > discards.count(color) and len(discards) < count:
                discards.append(color)
        return discards


def encode_resolved(data: dict[str, Any]) -> str:
    """Use an internal string to keep ActionResult simple."""
    return json.dumps(data, ensure_ascii=False)


def resolved_data(value: str) -> dict[str, Any]:
    """Decode a selector payload generated by this module."""
    data = json.loads(value)
    return data if isinstance(data, dict) else {}

"""Text UI rendering for Splendor rooms."""

from __future__ import annotations

from ..utils import cmd, table_name
from .constants import CARD_SPECS, COLORS, COLOR_LABELS, NOBLE_SPECS, TOKEN_COLORS
from .engine import SplendorEngine
from .models import PHASE_FINISHED, PHASE_PLAYING, PHASE_WAITING, SplendorRoom


class SplendorTextUI:
    """Builds compact, readable group-chat text for Splendor."""

    def __init__(self, engine: SplendorEngine):
        self.engine = engine

    def render_waiting_room(self, room: SplendorRoom) -> str:
        lines = [
            "璀璨宝石房间",
            f"人数：{room.player_count}/{room.target_players}",
            "玩家：",
        ]
        if room.players:
            for player in room.players.values():
                ai_mark = "AI" if player.is_ai else "真人"
                lines.append(f"- {table_name(player)}（{ai_mark}）")
        else:
            lines.append("- 暂无")
        lines.extend(
            [
                "",
                f"加入：{cmd('加入璀璨')}",
                f"添加角色AI：{cmd('璀璨加入角色AI')} 名字/序号",
                f"补满AI：{cmd('璀璨补满AI')}",
                f"开始：{cmd('开始璀璨')}",
            ]
        )
        return "\n".join(lines)

    def render_room(self, room: SplendorRoom, viewer_id: str = "") -> str:
        if room.phase == PHASE_WAITING:
            return self.render_waiting_room(room)

        lines = [
            "璀璨宝石",
            f"阶段：{self._phase_label(room)}",
            f"银行：{self._format_counts(room.bank)}",
        ]
        current = room.current_player
        if room.phase == PHASE_PLAYING and current:
            lines.append(f"当前行动：{current.display_name}")
        if room.final_round_active:
            trigger = room.players.get(room.final_round_trigger_player_id)
            trigger_name = trigger.display_name if trigger else "未知玩家"
            lines.append(f"最终轮：已由 {trigger_name} 触发")

        lines.append("")
        lines.append("贵族：")
        if room.nobles:
            for noble_id in room.nobles:
                noble = NOBLE_SPECS[noble_id]
                lines.append(
                    f"{noble_id} {noble.points}分 要 {self._format_counts(noble.requirement)}"
                )
        else:
            lines.append("无")

        lines.append("")
        lines.append("市场：")
        for tier in (3, 2, 1):
            lines.append(f"T{tier}:")
            for slot, card_id in enumerate(room.market[tier], start=1):
                lines.append(f"  T{tier}-{slot} {self._format_card(card_id)}")
            if not room.market[tier]:
                lines.append("  空")

        lines.append("")
        lines.append("玩家状态：")
        for player_id in room.turn_order or list(room.players):
            player = room.players[player_id]
            score = self.engine.score_for(player)
            marker = " <-" if current and current.id == player.id else ""
            lines.append(
                f"{player.display_name}{marker} | {score}分 | "
                f"永久 {self._format_counts(player.bonuses) or '无'} | "
                f"宝石 {self._format_counts(player.tokens) or '无'} | "
                f"预留 {len(player.reserved_cards)} | 买牌 {player.card_count}"
            )
            if player.reserved_cards:
                reserved = "；".join(
                    f"R{index} {self._format_card(card_id)}"
                    for index, card_id in enumerate(player.reserved_cards, start=1)
                )
                lines.append(f"  预留牌：{reserved}")

        if room.pending_discard_player_id:
            player = room.players.get(room.pending_discard_player_id)
            lines.extend(
                [
                    "",
                    f"待处理：{player.display_name if player else '当前玩家'} 需要丢宝石到 10 枚以内。",
                    f"命令：{cmd('丢宝石')} 白 蓝 ...",
                ]
            )
        elif room.pending_noble_player_id:
            player = room.players.get(room.pending_noble_player_id)
            choices = "、".join(room.pending_noble_ids)
            lines.extend(
                [
                    "",
                    f"待处理：{player.display_name if player else '当前玩家'} 选择贵族 {choices}。",
                    f"命令：{cmd('选择贵族')} N1",
                ]
            )
        elif room.phase == PHASE_PLAYING:
            lines.extend(
                [
                    "",
                    f"行动：{cmd('拿宝石')} 白 蓝 绿 / {cmd('保留牌')} T1-1 / "
                    f"{cmd('购买牌')} T1-1 或 R1",
                ]
            )

        if room.phase == PHASE_FINISHED and room.winner_ids:
            winners = "、".join(room.players[player_id].display_name for player_id in room.winner_ids)
            lines.append(f"\n胜者：{winners}")
        return "\n".join(lines)

    def render_help(self) -> str:
        return (
            "新爱莉都棋牌室 - 璀璨宝石\n\n"
            "开局：\n"
            f"  {cmd('创建璀璨房间')} 2/3/4 - 创建 Splendor 房间\n"
            f"  {cmd('加入璀璨')} - 真人加入\n"
            f"  {cmd('AI角色列表')} - 查看可用米哈游角色卡\n"
            f"  {cmd('璀璨加入角色AI')} 名字/序号 - 加入角色AI\n"
            f"  {cmd('璀璨补满AI')} - 按默认 roster 补满\n"
            f"  {cmd('开始璀璨')} - 房主开始\n\n"
            f"  {cmd('关闭璀璨房间')} - 房主关闭房间\n\n"
            "行动：\n"
            f"  {cmd('拿宝石')} 白 蓝 绿 - 拿三枚不同色宝石\n"
            f"  {cmd('拿宝石')} 红 红 - 拿两枚同色，银行该色需至少 4 枚\n"
            f"  {cmd('保留牌')} T1-1 - 保留市场牌并尽量拿 1 金\n"
            f"  {cmd('保留牌')} T2 - 盲保留二级牌堆顶牌\n"
            f"  {cmd('购买牌')} T3-4 - 购买市场牌\n"
            f"  {cmd('购买牌')} R1 - 购买自己的第 1 张预留牌\n"
            f"  {cmd('选择贵族')} N1 - 同时满足多个贵族时选择一个\n"
            f"  {cmd('丢宝石')} 白 蓝 - 超过 10 枚后丢弃\n\n"
            "规则摘要：2-4 人；保留上限 3 张；回合结束最多 10 枚宝石；"
            "15 分触发最终轮；最高分胜，平分时买牌更少者胜。"
        )

    def _format_card(self, card_id: str) -> str:
        spec = CARD_SPECS[card_id]
        return (
            f"{COLOR_LABELS[spec.color]}卡 {spec.points}分 "
            f"成本 {self._format_counts(spec.cost) or '无'}"
        )

    @staticmethod
    def _format_counts(counts: dict[str, int]) -> str:
        ordered = TOKEN_COLORS if "gold" in counts else COLORS
        return " ".join(
            f"{COLOR_LABELS[color]}{counts.get(color, 0)}"
            for color in ordered
            if counts.get(color, 0) > 0
        )

    @staticmethod
    def _phase_label(room: SplendorRoom) -> str:
        labels = {
            PHASE_WAITING: "等待中",
            PHASE_PLAYING: "进行中",
            PHASE_FINISHED: "已结束",
        }
        return labels.get(room.phase, room.phase)

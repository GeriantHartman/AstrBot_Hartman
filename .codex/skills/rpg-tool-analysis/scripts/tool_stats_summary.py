from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

LOCAL_TZ = timezone(timedelta(hours=8))
LOCAL_TZ_LABEL = "UTC+8"

TOOL_SKILL_MAP: dict[str, str] = {
    "query_current_zone": "rpg-scene-gen",
    "move_to_zone": "rpg-scene-gen",
    "inspect_environment": "rpg-scene-gen",
    "set_time_slice": "rpg-scene-gen",
    "sync_zone_npcs": "rpg-scene-gen",
    "create_area": "rpg-scene-gen",
    "bind_zone_to_area": "rpg-scene-gen",
    "perform_skill_check": "rpg-skill-check",
    "execute_camp": "rpg-camp",
    "adjust_player_attributes": "rpg-gm-protocol",
    "generate_npcs": "rpg-npc-gen",
    "log_npc_interactions": "rpg-npc-gen",
    "update_npc_affinities": "rpg-npc-gen",
    "recall_npc_history": "rpg-npc-gen",
    "update_npc_relationships": "rpg-npc-gen",
    "npc_tells_npc": "rpg-npc-gen",
    "pin_world_canon": "rpg-npc-gen",
    "manage_story_hook": "rpg-story-hook",
    "add_area_resident": "rpg-npc-gen",
    "mark_npc_evolution_trigger": "rpg-npc-gen",
    "set_companions": "rpg-npc-gen",
    "dismiss_companions": "rpg-npc-gen",
    "mark_interacting_npcs": "rpg-npc-gen",
    "unmark_interacting_npcs": "rpg-npc-gen",
    "execute_trade": "rpg-trade",
    "generate_commissions": "rpg-commission",
    "accept_commission": "rpg-commission",
    "complete_commission": "rpg-commission",
    "grant_xp": "rpg-levelup",
    "check_level_progress": "rpg-levelup",
    "apply_level_reward": "rpg-levelup",
    "search_lightcone": "rpg-lightcone",
    "equip_lightcone": "rpg-lightcone",
    "unequip_lightcone": "rpg-lightcone",
    "use_skill": "rpg-player-skill",
    "grant_skill": "rpg-player-skill",
    "get_player_status": "rpg-gm-protocol",
    "check_inventory": "rpg-gm-protocol",
    "use_items": "rpg-gm-protocol",
    "adjust_player_condition": "rpg-gm-protocol",
    "recall_memory": "memory",
    "merge_player_scenes": "scene-mgmt",
    "set_narrative_style": "style",
}

LEGACY_TOOL_ALIASES: dict[str, str] = {
    "generate_npc": "generate_npcs",
    "log_npc_interaction": "log_npc_interactions",
    "update_npc_state": "log_npc_interactions",
    "update_npc_affinity": "update_npc_affinities",
    "update_npc_relationship": "update_npc_relationships",
    "set_companion": "set_companions",
    "dismiss_companion": "dismiss_companions",
    "use_item": "use_items",
    "adjust_condition": "adjust_player_condition",
}

REMOVED_LEGACY_TOOLS: dict[str, str] = {
    "execute_combat_round": "removed-legacy",
    "log_zone_events": "removed-legacy",
}


def _tool_data(value: Any) -> dict[str, Any]:
    if isinstance(value, int):
        return {"count": value, "success_count": 0, "error_count": 0}
    if isinstance(value, dict):
        return value
    return {"count": 0, "success_count": 0, "error_count": 0}


def _clip(text: str, limit: int = 90) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "..."


def _pct(numerator: float, denominator: float) -> float:
    return round(numerator * 100 / max(1.0, denominator), 1)


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    raw = value.strip().replace("T", " ").replace("Z", "")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=LOCAL_TZ)
        except ValueError:
            continue
    raise SystemExit(
        f"无法解析时间: {value!r}; 请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"
    )


def _now_text() -> str:
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _in_window(value: str, since: datetime | None, until: datetime | None) -> bool:
    dt = _parse_time(value or "")
    if dt is None:
        return since is None and until is None
    if since and dt < since:
        return False
    if until and dt > until:
        return False
    return True


def iter_sessions(
    data: dict[str, Any], session: str
) -> list[tuple[str, dict[str, Any]]]:
    sessions = data.get("sessions") if isinstance(data.get("sessions"), dict) else {}
    if session:
        found = sessions.get(session)
        return [(session, found)] if isinstance(found, dict) else []
    return [(sid, item) for sid, item in sessions.items() if isinstance(item, dict)]


def _tool_in_window(
    tdata: dict[str, Any], since: datetime | None, until: datetime | None
) -> bool:
    if since is None and until is None:
        return True
    timestamps = [
        str(tdata.get("last_seen", "") or ""),
        str(tdata.get("first_seen", "") or ""),
    ]
    return any(_in_window(ts, since, until) for ts in timestamps if ts)


def summarize(
    data: dict[str, Any],
    *,
    session: str,
    since: datetime | None,
    until: datetime | None,
    low_threshold: int,
    min_error_calls: int,
) -> dict[str, Any]:
    selected = iter_sessions(data, session)
    windowed = since is not None or until is not None
    tool_totals: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "success_count": 0,
            "error_count": 0,
            "total_latency_ms": 0.0,
            "latency_weight": 0,
            "sessions": set(),
            "error_samples": [],
            "domain": "unknown",
        }
    )
    domain_counts: Counter[str] = Counter()
    router_counts: Counter[str] = Counter()
    chain_counts: Counter[str] = Counter()
    commit_denied: Counter[str] = Counter()
    commit_reasons: Counter[str] = Counter()
    style_counts: Counter[str] = Counter()
    supervision_verdicts: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []
    session_rows: list[dict[str, Any]] = []
    legacy_rows: list[dict[str, Any]] = []

    total_turns = 0
    tool_turns = 0
    no_tool_turns = 0
    pipeline_errors = 0

    for sid, item in selected:
        tools = item.get("tools") if isinstance(item.get("tools"), dict) else {}
        pipeline = (
            item.get("pipeline") if isinstance(item.get("pipeline"), dict) else {}
        )
        raw_turns = item.get("turns") if isinstance(item.get("turns"), list) else []
        turns = [
            t
            for t in raw_turns
            if isinstance(t, dict)
            and _in_window(str(t.get("ts", "") or ""), since, until)
        ]

        if windowed:
            session_turn_count = len(turns)
            session_tool_turns = sum(1 for t in turns if t.get("tool_chain"))
            session_no_tool_turns = session_turn_count - session_tool_turns
            session_pipeline_errors = sum(1 for t in turns if t.get("pipeline_error"))
        else:
            session_turn_count = int(pipeline.get("turn_count", 0) or 0)
            session_tool_turns = int(pipeline.get("tool_turn_count", 0) or 0)
            session_no_tool_turns = int(pipeline.get("no_tool_turn_count", 0) or 0)
            session_pipeline_errors = int(pipeline.get("pipeline_error_count", 0) or 0)
            style_counts.update(pipeline.get("style_counts") or {})
            supervision_verdicts.update(pipeline.get("supervision_verdicts") or {})
            router_counts.update(pipeline.get("router_tool_counts") or {})
            chain_counts.update(
                pipeline.get("tool_batch_counts")
                or pipeline.get("tool_chain_counts")
                or {}
            )

        total_turns += session_turn_count
        tool_turns += session_tool_turns
        no_tool_turns += session_no_tool_turns
        pipeline_errors += session_pipeline_errors

        session_call_count = 0
        session_error_count = 0
        for tool_name, raw in tools.items():
            tdata = _tool_data(raw)
            if not _tool_in_window(tdata, since, until):
                continue
            count = int(tdata.get("count", 0) or 0)
            errors = int(tdata.get("error_count", 0) or 0)
            success = int(tdata.get("success_count", 0) or 0)
            avg_ms = float(tdata.get("avg_latency_ms", 0.0) or 0.0)

            if tool_name in LEGACY_TOOL_ALIASES or tool_name in REMOVED_LEGACY_TOOLS:
                canonical = LEGACY_TOOL_ALIASES.get(tool_name, tool_name)
                legacy_rows.append(
                    {
                        "旧工具名": tool_name,
                        "当前对应": canonical
                        if canonical in TOOL_SKILL_MAP
                        else "已移除",
                        "领域": TOOL_SKILL_MAP.get(canonical)
                        or REMOVED_LEGACY_TOOLS.get(tool_name, "legacy"),
                        "调用次数": count,
                        "成功次数": success,
                        "错误次数": errors,
                        "错误率%": _pct(errors, count),
                        "平均耗时ms": avg_ms,
                        "会话": sid,
                    }
                )
                continue

            domain = str(
                TOOL_SKILL_MAP.get(tool_name) or tdata.get("domain") or "unknown"
            )
            row = tool_totals[tool_name]
            row["count"] += count
            row["success_count"] += success
            row["error_count"] += errors
            row["total_latency_ms"] += avg_ms * count
            row["latency_weight"] += count
            row["sessions"].add(sid)
            row["domain"] = domain
            row["error_samples"].extend(
                str(x) for x in (tdata.get("error_samples") or [])[-3:]
            )
            domain_counts[domain] += count
            session_call_count += count
            session_error_count += errors

        for turn in turns[-120:]:
            commit = turn.get("commit") if isinstance(turn.get("commit"), dict) else {}
            for denied in commit.get("denied") or []:
                if not isinstance(denied, dict):
                    continue
                name = str(denied.get("name", "") or "")
                reason = str(denied.get("reason", "") or "")
                if name:
                    commit_denied[name] += 1
                if reason:
                    commit_reasons[reason] += 1
            router = turn.get("router") if isinstance(turn.get("router"), dict) else {}
            execution = (
                turn.get("execution") if isinstance(turn.get("execution"), dict) else {}
            )
            router_tools = [str(x) for x in (router.get("tools") or []) if x]
            if windowed:
                router_counts.update(router_tools)
                if turn.get("style"):
                    style_counts[str(turn.get("style"))] += 1
                supervision = (
                    turn.get("supervision")
                    if isinstance(turn.get("supervision"), dict)
                    else {}
                )
                if supervision.get("verdict"):
                    supervision_verdicts[str(supervision.get("verdict"))] += 1
                if turn.get("tool_chain"):
                    chain_counts[
                        " + ".join(
                            str(x)
                            for x in turn.get("tool_call_batch")
                            or turn.get("tool_chain")
                            or []
                        )
                    ] += 1
            entry_count = int(execution.get("entry_count", 0) or 0)
            error_count = int(execution.get("error_count", 0) or 0)
            if router_tools and (
                entry_count == 0 or error_count > 0 or commit.get("denied")
            ):
                examples.append(
                    {
                        "session_id": sid,
                        "ts": turn.get("ts", ""),
                        "player_msg": _clip(str(turn.get("player_msg", "") or "")),
                        "router_tools": router_tools,
                        "tool_chain": turn.get("tool_chain", []),
                        "commit_decision": commit.get("decision", ""),
                        "commit_denied": commit.get("denied", []),
                        "execution": execution,
                    }
                )

        session_rows.append(
            {
                "session_id": sid,
                "last_updated": item.get("last_updated", ""),
                "preset": item.get("preset", ""),
                "tool_calls": session_call_count,
                "tool_errors": session_error_count,
                "turn_count": session_turn_count,
                "tool_turn_count": session_tool_turns,
                "no_tool_turn_count": session_no_tool_turns,
            }
        )

    tool_rows = []
    unreliable_success_tools = []
    for name, row in tool_totals.items():
        count = int(row["count"])
        errors = int(row["error_count"])
        success_count = int(row["success_count"])
        avg_ms = round(
            float(row["total_latency_ms"]) / max(1, int(row["latency_weight"])), 1
        )
        proposed = int(router_counts.get(name, 0))
        if count and success_count + errors < count:
            unreliable_success_tools.append(name)
        tool_rows.append(
            {
                "工具": name,
                "领域": row["domain"],
                "调用次数": count,
                "成功次数": success_count,
                "错误次数": errors,
                "错误率%": _pct(errors, count),
                "平均耗时ms": avg_ms,
                "涉及会话数": len(row["sessions"]),
                "Router提出次数": proposed,
                "提出但未执行差值": proposed - count,
                "错误样本": row["error_samples"][-5:],
            }
        )

    tool_row_by_name = {row["工具"]: row for row in tool_rows}
    full_tool_rows = []
    for name, domain in sorted(TOOL_SKILL_MAP.items()):
        row = tool_row_by_name.get(name)
        if row:
            full_tool_rows.append(row)
            continue
        full_tool_rows.append(
            {
                "工具": name,
                "领域": domain,
                "调用次数": 0,
                "成功次数": 0,
                "错误次数": 0,
                "错误率%": 0.0,
                "平均耗时ms": 0.0,
                "涉及会话数": 0,
                "Router提出次数": int(router_counts.get(name, 0)),
                "提出但未执行差值": int(router_counts.get(name, 0)),
                "错误样本": [],
            }
        )

    used_names = {row["工具"] for row in tool_rows if row["调用次数"] > 0}
    unused = [name for name in sorted(TOOL_SKILL_MAP) if name not in used_names]
    low_frequency = sorted(
        [row for row in tool_rows if 0 < row["调用次数"] <= low_threshold],
        key=lambda x: (x["调用次数"], x["工具"]),
    )
    high_error = sorted(
        [
            row
            for row in tool_rows
            if row["调用次数"] >= min_error_calls and row["错误次数"] > 0
        ],
        key=lambda x: (x["错误率%"], x["错误次数"]),
        reverse=True,
    )
    slow = sorted(tool_rows, key=lambda x: x["平均耗时ms"], reverse=True)
    overplanned = sorted(
        [row for row in tool_rows if row["提出但未执行差值"] > 0],
        key=lambda x: x["提出但未执行差值"],
        reverse=True,
    )
    unknown_tools = sorted(
        [
            row["工具"]
            for row in tool_rows
            if row["领域"] == "unknown" or row["工具"] not in TOOL_SKILL_MAP
        ]
    )
    data_notes = []
    if windowed:
        data_notes.append(
            "已启用时间窗口。turns 回合快照按 ts 精确筛选；tools 聚合只能按 first_seen/last_seen 粗筛，适合作为弱证据。"
        )
    if sum(row["调用次数"] for row in tool_rows) > max(1, total_turns) * 20:
        data_notes.append(
            "tools.count 包含较长历史累计，而 pipeline/turns 只覆盖新埋点后的回合；不要直接用 Router提出次数 与 调用次数 的负差值判断误调用。"
        )
    if unreliable_success_tools:
        data_notes.append(
            "部分工具来自旧版统计，success_count/error_count 不完整；错误率为 0 不等于这些历史调用全部成功。"
        )
    if unknown_tools:
        data_notes.append(
            "存在未映射工具，请先更新 TOOL_SKILL_MAP 或清理旧工具命名，否则领域分布会被 unknown 污染。"
        )

    return {
        "范围": "指定会话" if session else "全部会话",
        "时间窗口": {
            "since": since.strftime("%Y-%m-%d %H:%M:%S") if since else "",
            "until": until.strftime("%Y-%m-%d %H:%M:%S") if until else "",
        },
        "会话数": len(selected),
        "数据质量提示": data_notes,
        "总览": {
            "记录回合": total_turns,
            "工具回合": tool_turns,
            "无工具回合": no_tool_turns,
            "无工具回合占比%": _pct(no_tool_turns, total_turns),
            "Pipeline异常": pipeline_errors,
            "工具总调用": sum(row["调用次数"] for row in tool_rows),
            "工具总错误": sum(row["错误次数"] for row in tool_rows),
        },
        "会话排行": sorted(session_rows, key=lambda x: x["tool_calls"], reverse=True)[
            :10
        ],
        "工具排行": sorted(tool_rows, key=lambda x: x["调用次数"], reverse=True),
        "全量工具使用情况": full_tool_rows,
        "历史遗留工具": sorted(legacy_rows, key=lambda x: x["调用次数"], reverse=True),
        "领域分布": dict(domain_counts.most_common()),
        "高错误率工具": high_error[:10],
        "高延迟工具": slow[:10],
        "低频工具": low_frequency[:20],
        "未使用工具": unused,
        "未映射工具": unknown_tools,
        "Router过度计划候选": overplanned[:15],
        "CommitGate拦截工具": dict(commit_denied.most_common()),
        "CommitGate拦截原因": dict(commit_reasons.most_common(12)),
        "常见工具链": dict(chain_counts.most_common(12)),
        "风格分布": dict(style_counts.most_common()),
        "Supervisor判定": dict(supervision_verdicts.most_common()),
        "误调用候选样本": examples[-20:],
    }


def _table(
    rows: list[dict[str, Any]], columns: list[str], limit: int | None = 10
) -> list[str]:
    if limit is not None:
        rows = rows[:limit]
    if not rows:
        return ["无。"]
    out = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        out.append(
            "| "
            + " | ".join(str(row.get(col, "")).replace("|", "/") for col in columns)
            + " |"
        )
    return out


def build_markdown_report(result: dict[str, Any], *, stats_path: Path) -> str:
    overview = result.get("总览", {})
    window = result.get("时间窗口", {})
    lines = [
        "# RPG 工具使用分析报告",
        "",
        f"生成时间：{_now_text()} {LOCAL_TZ_LABEL}",
        f"数据源：`{stats_path}`",
        f"范围：{result.get('范围', '')}；会话数：{result.get('会话数', 0)}",
    ]
    if window.get("since") or window.get("until"):
        lines.append(
            f"时间窗口（{LOCAL_TZ_LABEL}）：{window.get('since') or '开始'} 至 {window.get('until') or '现在'}"
        )
    lines.extend(["", "## 数据质量提示"])
    notes = result.get("数据质量提示") or []
    lines.extend([f"- {note}" for note in notes] or ["- 无明显数据质量提示。"])
    lines.extend(
        [
            "",
            "## 总览",
            f"- 记录回合：{overview.get('记录回合', 0)}",
            f"- 工具回合：{overview.get('工具回合', 0)}",
            f"- 无工具回合：{overview.get('无工具回合', 0)}（{overview.get('无工具回合占比%', 0)}%）",
            f"- Pipeline 异常：{overview.get('Pipeline异常', 0)}",
            f"- 工具总调用：{overview.get('工具总调用', 0)}",
            f"- 工具总错误：{overview.get('工具总错误', 0)}",
            "",
            "## 领域分布",
        ]
    )
    domain_rows = [
        {"领域": k, "调用次数": v} for k, v in (result.get("领域分布") or {}).items()
    ]
    lines.extend(_table(domain_rows, ["领域", "调用次数"], 12))
    lines.extend(["", "## 工具调用排行"])
    lines.extend(
        _table(
            result.get("工具排行") or [],
            ["工具", "领域", "调用次数", "错误次数", "错误率%", "平均耗时ms"],
            15,
        )
    )
    lines.extend(["", "## 全量工具使用情况"])
    lines.extend(
        _table(
            result.get("全量工具使用情况") or [],
            [
                "工具",
                "领域",
                "调用次数",
                "成功次数",
                "错误次数",
                "错误率%",
                "平均耗时ms",
                "Router提出次数",
            ],
            None,
        )
    )
    lines.extend(["", "## 高延迟工具"])
    lines.extend(
        _table(
            result.get("高延迟工具") or [],
            ["工具", "领域", "调用次数", "平均耗时ms"],
            10,
        )
    )
    lines.extend(["", "## 高错误率工具"])
    lines.extend(
        _table(
            result.get("高错误率工具") or [],
            ["工具", "领域", "调用次数", "错误次数", "错误率%"],
            10,
        )
    )
    lines.extend(["", "## 低频与未使用工具"])
    lines.extend(["低频工具："])
    lines.extend(
        _table(
            result.get("低频工具") or [], ["工具", "领域", "调用次数", "涉及会话数"], 20
        )
    )
    unused = result.get("未使用工具") or []
    lines.append("")
    lines.append("未使用工具：" + ("、".join(unused) if unused else "无。"))
    unmapped = result.get("未映射工具") or []
    lines.append("未映射工具：" + ("、".join(unmapped) if unmapped else "无。"))
    lines.extend(["", "## 历史遗留工具名"])
    lines.extend(
        _table(
            result.get("历史遗留工具") or [],
            ["旧工具名", "当前对应", "领域", "调用次数", "错误次数", "错误率%", "会话"],
            None,
        )
    )
    lines.extend(["", "## Router 与 Commit Gate"])
    lines.append(
        "Commit Gate 拦截工具："
        + (
            json.dumps(result.get("CommitGate拦截工具") or {}, ensure_ascii=False)
            or "{}"
        )
    )
    lines.append(
        "Commit Gate 拦截原因："
        + (
            json.dumps(result.get("CommitGate拦截原因") or {}, ensure_ascii=False)
            or "{}"
        )
    )
    lines.extend(["", "Router 过度计划候选："])
    lines.extend(
        _table(
            result.get("Router过度计划候选") or [],
            ["工具", "Router提出次数", "调用次数", "提出但未执行差值"],
            10,
        )
    )
    lines.extend(["", "## 常见工具调用批次"])
    chain_rows = [
        {"工具调用批次": k, "次数": v}
        for k, v in (result.get("常见工具链") or {}).items()
    ]
    lines.extend(_table(chain_rows, ["工具调用批次", "次数"], 12))
    lines.extend(["", "## 误调用候选样本"])
    sample_rows = []
    for item in result.get("误调用候选样本") or []:
        sample_rows.append(
            {
                "时间": item.get("ts", ""),
                "玩家消息": item.get("player_msg", ""),
                "Router工具": ", ".join(item.get("router_tools") or []),
                "Commit": item.get("commit_decision", ""),
            }
        )
    lines.extend(_table(sample_rows, ["时间", "玩家消息", "Router工具", "Commit"], 20))
    lines.extend(["", "## 建议"])
    if unmapped:
        lines.append("- 优先修复未映射工具，避免领域统计被 unknown 污染。")
    else:
        lines.append("- 当前未发现未映射工具，后续新增工具时继续同步 TOOL_SKILL_MAP。")
    lines.extend(
        [
            "- 4.0 后建议使用 `--since` 从基线时间开始生成报告；旧累计 tools 数据仅作为耗时、成功率、失败原因的弱证据。",
            "- 工具调用频次受玩法影响，不建议作为两次报告的强对比指标；更适合对比平均耗时、错误率、失败样本和 Commit Gate 拦截原因。",
        ]
    )
    return "\n".join(lines) + "\n"


def _resolve_report_path(value: str, stats_path: Path) -> Path | None:
    if not value:
        return None
    timestamp = datetime.now(LOCAL_TZ).strftime("%Y%m%d-%H%M%S")
    if value.lower() == "auto":
        return (
            stats_path.parent
            / "tool_analysis_reports"
            / f"tool-analysis-{timestamp}.md"
        )
    return Path(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stats", default="data/plugin_data/astrbot_plugin_agentic_rpg/rpg_stats.json"
    )
    parser.add_argument("--session", default="")
    parser.add_argument(
        "--since",
        default="",
        help="只分析该时间之后的数据，格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS",
    )
    parser.add_argument(
        "--until",
        default="",
        help="只分析该时间之前的数据，格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS",
    )
    parser.add_argument("--low-threshold", type=int, default=2)
    parser.add_argument("--min-error-calls", type=int, default=2)
    parser.add_argument(
        "--report",
        default="",
        help="Markdown 报告路径；传 auto 自动写入 tool_analysis_reports",
    )
    parser.add_argument(
        "--archive-baseline",
        action="store_true",
        help="生成报告前先复制当前 stats 到 tool_analysis_archives",
    )
    args = parser.parse_args()

    path = Path(args.stats)
    if args.archive_baseline:
        archive_dir = path.parent / "tool_analysis_archives"
        archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(LOCAL_TZ).strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, archive_dir / f"rpg_stats-baseline-{stamp}.json")

    data = json.loads(path.read_text(encoding="utf-8"))
    result = summarize(
        data,
        session=args.session,
        since=_parse_time(args.since),
        until=_parse_time(args.until),
        low_threshold=args.low_threshold,
        min_error_calls=args.min_error_calls,
    )
    report_path = _resolve_report_path(args.report, path)
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            build_markdown_report(result, stats_path=path), encoding="utf-8"
        )
        result["Markdown报告"] = str(report_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

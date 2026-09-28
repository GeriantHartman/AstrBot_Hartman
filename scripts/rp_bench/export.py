"""Human- and agent-readable exports of generated transcripts (no judge needed).

<run>/sessions/<card>/<scenario>/<arm>__<model>__r<N>.md   one full session
<run>/compare/<card>__<scenario>__r<N>.md                  all models/arms side by side, turn by turn
<run>/index.md                                             table of contents + per-model quick stats
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from .store import METRICS, TRANSCRIPTS, RunStore

_UNSAFE = re.compile(r"[^\w.\-]+", re.UNICODE)


def slug(text: str) -> str:
    return _UNSAFE.sub("_", str(text)).strip("_") or "x"


def _latest(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["cell_key"]: r for r in rows}


def variant(row: dict[str, Any]) -> str:
    return f"{row['arm']} · {row['model']}"


def session_path(row: dict[str, Any]) -> Path:
    return (
        Path("sessions")
        / slug(row["card"])
        / slug(row["scenario_id"])
        / f"{slug(row['arm'])}__{slug(row['model'])}__r{row['repeat']}.md"
    )


def compare_path(card: str, scenario_id: str, repeat: int) -> Path:
    return Path("compare") / f"{slug(card)}__{slug(scenario_id)}__r{repeat}.md"


INLINE_PROMPT_LIMIT = 4000


def prompt_path(row: dict[str, Any]) -> Path:
    return (
        Path("prompts")
        / f"{slug(row['card'])}__{slug(row['arm'])}__{row.get('system_prompt_sha', 'x')}.md"
    )


def render_session(row: dict[str, Any], *, depth: int = 3) -> str:
    meta = row.get("scenario_meta") or {}
    gate = row.get("gate") or {}
    L = [
        f"# {row.get('card_name', row['card'])} · {meta.get('title', row['scenario_id'])}",
        "",
        f"- 对照组：`{row['arm']}`　模型：`{row['model']}`　第 {row['repeat']} 次",
        f"- 开始：{row.get('started_at', '')}　结束：{row.get('finished_at', '')}",
        f"- 出场闸门：{'通过' if gate.get('passed', True) else '未通过 — ' + str(gate.get('reason'))}",
    ]
    pm = row.get("prompt_meta") or {}
    if pm.get("files"):
        L.append(f"- 角色卡文件：{'、'.join(pm['files'])}（{pm.get('chars', 0):,} 字）")
    sp = row.get("system_prompt") or ""
    if len(sp) > INLINE_PROMPT_LIMIT:
        # persona shared by every session of this card × arm: written once under prompts/
        link = "../" * depth + prompt_path(row).as_posix()
        L += [
            "",
            "## System prompt",
            "",
            f"共 {len(sp):,} 字，全文见 [{prompt_path(row).name}]({link})。",
        ]
    elif sp:
        L += [
            "",
            "## System prompt",
            "",
            "```text",
            row["system_prompt"].strip(),
            "```",
        ]
    for t in row.get("turns") or []:
        L += [
            "",
            f"## {t['turn_id']}",
            "",
            f"**玩家**：{t['sent_text'] or t['player_text']}",
            "",
        ]
        L.append(f"**回应**（{t.get('latency_s', '')}s）：")
        L += ["", t.get("reply_clean") or "（空）"]
        if t.get("reasoning"):
            L += [
                "",
                "<details><summary>思考过程</summary>",
                "",
                t["reasoning"].strip(),
                "",
                "</details>",
            ]
        if t.get("error"):
            L += ["", f"> 错误：{t['error']}"]
    return "\n".join(L) + "\n"


def render_compare(rows: list[dict[str, Any]]) -> str:
    rows = sorted(rows, key=lambda r: (r["arm"], r["model"]))
    first = rows[0]
    meta = first.get("scenario_meta") or {}
    L = [
        f"# 对比：{first.get('card_name', first['card'])} · {meta.get('title', first['scenario_id'])} · 第 {first['repeat']} 次",
        "",
        "参与对比：" + "、".join(f"`{variant(r)}`" for r in rows),
        "",
    ]
    if meta.get("premise"):
        L += [f"> 剧本前提：{meta['premise']}", ""]
    by_turn: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    order: list[str] = []
    for r in rows:
        for t in r.get("turns") or []:
            if t["turn_id"] not in order:
                order.append(t["turn_id"])
            by_turn[t["turn_id"]][variant(r)] = t
    probes = defaultdict(list)
    for p in meta.get("probes") or []:
        probes[p.get("turn")].append(p)
    for tid in order:
        some = next(iter(by_turn[tid].values()))
        L += ["---", "", f"## {tid}　玩家：{some['player_text']}"]
        for p in probes.get(tid, []):
            L.append(f"> 考点 `{p['kind']}`：{p.get('expect', '')}")
        for r in rows:
            t = by_turn[tid].get(variant(r))
            L += ["", f"### {variant(r)}", ""]
            L.append((t or {}).get("reply_clean") or "（无回复）")
        L.append("")
    return "\n".join(L) + "\n"


def _quick_stats(metrics: list[dict[str, Any]]) -> list[str]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in metrics:
        groups[f"{m['arm']} · {m['model']}"].append(m)
    if not groups:
        return []
    L = [
        "## 快速统计（纯代码，不含裁判）",
        "",
        "违规类的理想值都是 0；篇幅和延迟请横向比较。",
        "",
        "| 组 · 模型 | 会话 | 平均篇幅(字) | 延迟中位(秒) | 出戏话术 | never_say 命中 | 自称违规 | 脚手架泄漏轮 | 相邻轮最高相似度 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    def avg(rows, section, key):
        vals = [r[section].get(key) for r in rows if r[section].get(key) is not None]
        return statistics.fmean(vals) if vals else None

    def f(v, pct=False):
        if v is None:
            return "—"
        return f"{v * 100:.0f}%" if pct else f"{v:.1f}"

    for name, rows in sorted(groups.items()):
        L.append(
            f"| {name} | {len(rows)} | {f(avg(rows, 'text', 'len_mean'))} | {f(avg(rows, 'ops', 'latency_p50'))} | "
            f"{f(avg(rows, 'text', 'ooc_hits'))} | {f(avg(rows, 'text', 'never_say_hits'))} | "
            f"{f(avg(rows, 'text', 'self_forbidden_hits'))} | {f(avg(rows, 'text', 'leak_turns'))} | "
            f"{f(avg(rows, 'text', 'adjacent_similarity_max'), pct=True)} |"
        )
    return L + [""]


def export_run(store: RunStore) -> dict[str, Any]:
    transcripts = _latest(store.read(TRANSCRIPTS))
    metrics = list(_latest(store.read(METRICS)).values())

    sessions = []
    for row in transcripts.values():
        rel = session_path(row)
        out = store.dir / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_session(row, depth=len(rel.parts) - 1), encoding="utf-8")
        sessions.append((row, rel))
        sp = row.get("system_prompt") or ""
        if len(sp) > INLINE_PROMPT_LIMIT:
            p = store.dir / prompt_path(row)
            if not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(sp, encoding="utf-8")

    groups: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in transcripts.values():
        if row.get("turns"):
            groups[(row["card"], row["scenario_id"], int(row["repeat"]))].append(row)
    compares = []
    for (card, sid, rep), rows in sorted(groups.items()):
        rel = compare_path(card, sid, rep)
        out = store.dir / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_compare(rows), encoding="utf-8")
        compares.append((card, sid, rep, rel, [variant(r) for r in rows]))

    L = ["# 跑次目录", ""]
    L += _quick_stats(metrics)
    L += ["## 并排对比", ""]
    for card, sid, rep, rel, variants in compares:
        L.append(
            f"- [{card} / {sid} / 第 {rep} 次]({rel.as_posix()})："
            + "、".join(variants)
        )
    L += ["", "## 单个会话", ""]
    for row, rel in sorted(sessions, key=lambda x: str(x[1])):
        status = "" if row.get("gate", {}).get("passed", True) else "（闸门未过）"
        L.append(
            f"- [{row['card']} / {row['scenario_id']} / {variant(row)} / 第 {row['repeat']} 次]({rel.as_posix()}){status}"
        )
    store.write_text("index.md", "\n".join(L) + "\n")
    return {
        "sessions": [rel.as_posix() for _, rel in sessions],
        "compare": [c[3].as_posix() for c in compares],
        "index": "index.md",
    }

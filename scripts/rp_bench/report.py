"""Aggregate stage outputs into summary.json + a readable report.md.

Rule: every number is printed next to a reference point (scale anchor, the
reference arm, a 50% coin flip, or the noise floor).
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

from .judge.rubric import DIMENSIONS, RUBRIC_VERSION
from .stats import bootstrap_ci, mean_sd, merge_swapped, win_rate
from .store import (
    FAILURES,
    JUDGE_ABS,
    JUDGE_PAIR,
    MANIFEST,
    METRICS,
    TRANSCRIPTS,
    RunStore,
    now_utc8,
)

PROBE_SCORE = {"pass": 1.0, "partial": 0.5, "fail": 0.0}


def _latest(rows: list[dict[str, Any]], key) -> dict[Any, dict[str, Any]]:
    out: dict[Any, dict[str, Any]] = {}
    for r in rows:
        out[key(r)] = r
    return out


def _fmt(v: float | None, digits: int = 2) -> str:
    return "—" if v is None else f"{v:.{digits}f}"


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.0f}%"


def build_summary(store: RunStore, *, judge_id: str | None = None) -> dict[str, Any]:
    manifest = store.read_json(MANIFEST) or {}
    plan = manifest.get("plan", {})
    reference_arm = plan.get("reference_arm", "raw")
    transcripts = _latest(store.read(TRANSCRIPTS), lambda r: r["cell_key"])
    metrics = _latest(store.read(METRICS), lambda r: r["cell_key"])
    judge_id = judge_id or (manifest.get("judge") or {}).get("id")
    abs_rows = _latest(
        [
            r
            for r in store.read(JUDGE_ABS)
            if r.get("rubric_version") == RUBRIC_VERSION
            and (judge_id is None or r.get("judge_id") == judge_id)
        ],
        lambda r: r["cell_key"],
    )
    pair_rows = [
        r
        for r in store.read(JUDGE_PAIR)
        if r.get("rubric_version") == RUBRIC_VERSION
        and (judge_id is None or r.get("judge_id") == judge_id)
    ]
    failures = [f for f in store.read(FAILURES) if f.get("cell_key") not in transcripts]

    return {
        "generated_at": now_utc8().isoformat(),
        "manifest": manifest,
        "reference_arm": reference_arm,
        "health": _health(transcripts, metrics, abs_rows, pair_rows, failures),
        "absolute": _absolute(transcripts, abs_rows, reference_arm),
        "probes": _probes(transcripts, abs_rows),
        "deterministic": _deterministic(metrics),
        "pairwise": _pairwise(pair_rows),
        "worst": _worst(transcripts, abs_rows),
        "cost": _cost(metrics, abs_rows, pair_rows, manifest),
    }


# ------------------------------------------------------------------ health


def _health(transcripts, metrics, abs_rows, pair_rows, failures) -> dict[str, Any]:
    turns = [t for r in transcripts.values() for t in r.get("turns") or []]
    dims = [
        d
        for r in abs_rows.values()
        for d in (r.get("dims") or {}).values()
        if d.get("score") is not None or d.get("reason")
    ]
    valid = sum(1 for d in dims if d.get("valid"))
    return {
        "sessions_done": len(transcripts),
        "sessions_failed": len({f["cell_key"] for f in failures}),
        "failure_samples": [
            f"{f.get('label')}: {f.get('error')}" for f in failures[:5]
        ],
        "gate_failed": sum(
            1 for r in transcripts.values() if not r.get("gate", {}).get("passed", True)
        ),
        "gate_failed_samples": [
            f"{r['card']}/{r['scenario_id']}/{r['arm']}#{r['repeat']}: {r['gate'].get('reason')}"
            for r in transcripts.values()
            if not r.get("gate", {}).get("passed", True)
        ][:5],
        "turns": len(turns),
        "turn_errors": sum(1 for t in turns if t.get("error")),
        "fallback_turns": sum(1 for t in turns if t.get("fallback_used")),
        "pipeline_mismatch_turns": sum(1 for t in turns if t.get("pipeline_mismatch")),
        "style_leak_turns": sum(1 for t in turns if t.get("style_skills_leak")),
        "ledger_missing_turns": sum(1 for t in turns if t.get("ledger_missing")),
        "judge_abs_done": len(abs_rows),
        "judge_abs_errors": sum(1 for r in abs_rows.values() if r.get("error")),
        "evidence_validity": (valid / len(dims)) if dims else None,
        "judge_pair_rows": len(pair_rows),
        "judge_pair_errors": sum(1 for r in pair_rows if r.get("error")),
    }


# ---------------------------------------------------------------- absolute


def _scores_by(
    transcripts, abs_rows
) -> dict[tuple[str, str], dict[str, dict[str, float]]]:
    """(arm, model) -> dim -> {group: score} for gate-passed sessions."""
    out: dict[tuple[str, str], dict[str, dict[str, float]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for key, row in abs_rows.items():
        tr = transcripts.get(key)
        if tr is None or not tr.get("gate", {}).get("passed", True) or row.get("error"):
            continue
        for dim, d in (row.get("dims") or {}).items():
            if d.get("valid") and d.get("score") is not None:
                out[(row["arm"], row["model"])][dim][tr["group"]] = float(d["score"])
    return out


def _absolute(transcripts, abs_rows, reference_arm: str) -> dict[str, Any]:
    scores = _scores_by(transcripts, abs_rows)
    table = []
    for (arm, model), dims in sorted(scores.items()):
        row: dict[str, Any] = {"arm": arm, "model": model, "dims": {}}
        ref = scores.get((reference_arm, model), {})
        all_means = []
        for dim, by_group in dims.items():
            vals = list(by_group.values())
            m, sd = mean_sd(vals)
            lo, hi = bootstrap_ci(vals)
            entry = {"mean": m, "sd": sd, "ci": [lo, hi], "n": len(vals)}
            if arm != reference_arm and dim in ref:
                diffs = [v - ref[dim][g] for g, v in by_group.items() if g in ref[dim]]
                if diffs:
                    dm, _ = mean_sd(diffs)
                    dlo, dhi = bootstrap_ci(diffs)
                    entry["delta_ref"] = {"mean": dm, "ci": [dlo, dhi], "n": len(diffs)}
            row["dims"][dim] = entry
            if m is not None:
                all_means.append(m)
        row["overall"] = statistics.fmean(all_means) if all_means else None
        table.append(row)

    per_card: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for key, row in abs_rows.items():
        tr = transcripts.get(key)
        if tr is None or not tr.get("gate", {}).get("passed", True):
            continue
        vals = [
            d["score"]
            for d in (row.get("dims") or {}).values()
            if d.get("valid") and d.get("score") is not None
        ]
        if vals:
            per_card[(row["card"], row["arm"], row["model"])].append(
                statistics.fmean(vals)
            )
    return {
        "table": table,
        "per_card": [
            {"card": c, "arm": a, "model": m, "mean": statistics.fmean(v), "n": len(v)}
            for (c, a, m), v in sorted(per_card.items())
        ],
    }


# ------------------------------------------------------------------ probes


def _probes(transcripts, abs_rows) -> list[dict[str, Any]]:
    acc: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for key, row in abs_rows.items():
        tr = transcripts.get(key)
        if tr is None or not tr.get("gate", {}).get("passed", True):
            continue
        for p in row.get("probes") or []:
            if p.get("verdict") in PROBE_SCORE:
                acc[(row["arm"], row["model"], p.get("kind", ""))].append(
                    PROBE_SCORE[p["verdict"]]
                )
    return [
        {"arm": a, "model": m, "kind": k, "pass_rate": statistics.fmean(v), "n": len(v)}
        for (a, m, k), v in sorted(acc.items())
    ]


# ----------------------------------------------------------- deterministic

DET_FIELDS = [
    ("len_mean", "平均篇幅(字)", "text"),
    ("dialogue_ratio_mean", "台词占比", "text"),
    ("self_forbidden_hits", "自称违规次数", "text"),
    ("call_discouraged_hits", "称呼违规次数", "text"),
    ("never_say_hits", "never_say 字面命中", "text"),
    ("ooc_hits", "出戏话术命中", "text"),
    ("leak_turns", "脚手架泄漏轮数", "text"),
    ("ngram4_repeat_mean", "单条内复读率", "text"),
    ("adjacent_similarity_max", "相邻轮最高相似度", "text"),
    ("opening_repeat_rate", "开头雷同率", "text"),
    ("signature_rate", "口癖出现率", "text"),
    ("agency_hits", "替玩家写心理(启发式)", "text"),
    ("open_ending_rate", "结尾留钩子率(启发式)", "text"),
    ("latency_p50", "延迟中位数(秒)", "ops"),
    ("presence_rate", "目标角色在场率", "ops"),
]


def _deterministic(metrics) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for m in metrics.values():
        if m.get("gate_passed", True):
            groups[(m["arm"], m["model"])].append(m)
    out = []
    for (arm, model), rows in sorted(groups.items()):
        entry: dict[str, Any] = {"arm": arm, "model": model, "sessions": len(rows)}
        for fld, _, section in DET_FIELDS:
            vals = [
                r[section].get(fld) for r in rows if r[section].get(fld) is not None
            ]
            entry[fld] = statistics.fmean(vals) if vals else None
        entry["leak_kinds"] = sorted(
            {k for r in rows for k in r["text"].get("leak_kinds", [])}
        )
        out.append(entry)
    return out


# ---------------------------------------------------------------- pairwise


def _pairwise(pair_rows) -> list[dict[str, Any]]:
    by_pair: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for r in pair_rows:
        if not r.get("error"):
            by_pair[r["pair_key"]][int(r["order"])] = r

    comparisons: dict[tuple[str, str, str], dict[str, Any]] = {}
    for orders in by_pair.values():
        if 1 not in orders or 2 not in orders:
            continue
        r1, r2 = orders[1], orders[2]
        label_x = r1["label_x"].split("#")[0]
        label_y = r1["label_y"].split("#")[0]
        ck = (r1["kind"], label_x, label_y)
        comp = comparisons.setdefault(
            ck,
            {
                "kind": r1["kind"],
                "x": label_x,
                "y": label_y,
                "dims": defaultdict(list),
                "overall": [],
                "consistent": [],
                "len_diff": [],
            },
        )
        for dim in r1.get("dims") or {}:
            w1 = (r1["dims"].get(dim) or {}).get("winner", "")
            w2 = ((r2.get("dims") or {}).get(dim) or {}).get("winner", "")
            if "invalid" in (w1, w2):
                continue
            outcome, _ = merge_swapped(w1, w2)
            comp["dims"][dim].append(outcome)
        o1 = (r1.get("overall") or {}).get("winner", "")
        o2 = (r2.get("overall") or {}).get("winner", "")
        if "invalid" not in (o1, o2):
            outcome, consistent = merge_swapped(o1, o2)
            comp["overall"].append(outcome)
            comp["consistent"].append(consistent)
        comp["len_diff"].append(int(r1.get("len_x", 0)) - int(r1.get("len_y", 0)))

    out = []
    for comp in comparisons.values():
        fx, fy = _family(comp["x"]), _family(comp["y"])
        out.append(
            {
                "kind": comp["kind"],
                "cross_format": bool(fx and fy and fx != fy),
                "x": comp["x"],
                "y": comp["y"],
                "overall": win_rate(comp["overall"]),
                "dims": {d: win_rate(v) for d, v in comp["dims"].items()},
                "position_consistency": (
                    sum(comp["consistent"]) / len(comp["consistent"])
                )
                if comp["consistent"]
                else None,
                "mean_len_diff": statistics.fmean(comp["len_diff"])
                if comp["len_diff"]
                else None,
            }
        )
    return sorted(out, key=lambda c: (c["kind"], c["x"], c["y"]))


def _family(label: str) -> str:
    arm = label.split("@")[0].split("#")[0].split(":")[0]
    if arm in ("bare", "skill", "raw", "style_skills"):
        return "chat"
    if arm in ("rpg4", "rpg5"):
        return "rpg"
    return ""


# ------------------------------------------------------------------ worst


def _worst(transcripts, abs_rows, limit: int = 8) -> list[dict[str, Any]]:
    items = []
    for key, row in abs_rows.items():
        tr = transcripts.get(key)
        if tr is None:
            continue
        for dim, d in (row.get("dims") or {}).items():
            if d.get("valid") and d.get("score") is not None and d["score"] <= 2:
                ev = next((e for e in d.get("evidence") or [] if e.get("found")), None)
                items.append(
                    {
                        "score": d["score"],
                        "dim": dim,
                        "arm": row["arm"],
                        "model": row["model"],
                        "card": row["card"],
                        "scenario_id": row["scenario_id"],
                        "repeat": row["repeat"],
                        "turn": (ev or {}).get("turn", ""),
                        "quote": (ev or {}).get("quote", ""),
                        "rationale": d.get("rationale", ""),
                    }
                )
    items.sort(key=lambda x: (x["score"], x["arm"]))
    return items[:limit]


# ------------------------------------------------------------------- cost


def _cost(metrics, abs_rows, pair_rows, manifest) -> dict[str, Any]:
    gen: dict[str, dict[str, int]] = defaultdict(lambda: {"input": 0, "output": 0})
    for m in metrics.values():
        g = gen[m["model"]]
        g["input"] += int(m["ops"].get("tokens_in", 0) or 0)
        g["output"] += int(m["ops"].get("tokens_out", 0) or 0)
    judge = {"input": 0, "output": 0}
    for r in [*abs_rows.values(), *pair_rows]:
        for k in judge:
            judge[k] += int((r.get("usage") or {}).get(k, 0) or 0)
    return {
        "generation_tokens_by_model": dict(gen),
        "judge_tokens": judge,
        "note": "RPG 组只统计叙事者的 token（Router/Director/Validator 不在 agent_stats 里）",
    }


# ---------------------------------------------------------------- markdown


def render_markdown(s: dict[str, Any]) -> str:
    man = s.get("manifest") or {}
    plan = man.get("plan") or {}
    git = man.get("git") or {}
    ref = s["reference_arm"]
    L: list[str] = []
    L.append(f"# RP Bench 报告：{plan.get('name', '')}")
    L.append("")
    L.append(f"- 生成时间（UTC+8）：{s['generated_at']}")
    repo = git.get("repo") or {}
    rpg = git.get("rpg_plugin") or {}
    L.append(
        f"- 代码版本：仓库 `{(repo.get('head') or '')[:10]}`{'（有未提交改动）' if repo.get('dirty') else ''}；"
        f"RPG 插件 `{(rpg.get('head') or '')[:10]}` 分支 `{rpg.get('branch', '')}`{'（有未提交改动）' if rpg.get('dirty') else ''}"
    )
    L.append(
        f"- 对照组：{', '.join(plan.get('arms', []))}；参照组：`{ref}`；模型：{', '.join(plan.get('models', []))}"
    )
    judge = man.get("judge") or {}
    if judge.get("id"):
        L.append(
            f"- 裁判：`{judge.get('id', '')}`（家族 {judge.get('family', '')}，温度 {judge.get('temperature', '')}），评分标准版本 `{RUBRIC_VERSION}`"
        )
    else:
        L.append(
            "- 裁判：未启用。本次只保存对话，逐轮并排对比见 `index.md` 和 `compare/`；之后可以补上裁判，用 `judge --resume` 给同一批对话打分。"
        )
    tested_families = {str(m).lower() for m in plan.get("models", [])}
    if judge.get("family") and any(judge["family"] in m for m in tested_families):
        L.append(
            f"- ⚠️ 裁判和被测模型同属 `{judge['family']}` 家族，可能偏袒自家文风，结论需打折看。"
        )
    if plan.get("smoke"):
        L.append(
            "- ⚠️ 这是冒烟测试（剧本截短、只跑 1 次），数字只用于检查流程是否通，不能下结论。"
        )
    L.append("")

    h = s["health"]
    L.append("## 1. 健康度（先看这里：这些不为零，后面的数字就要打折）")
    L.append("")
    L.append(
        f"- 完成会话 {h['sessions_done']} 个，失败 {h['sessions_failed']} 个（失败的下次续跑会重试）"
    )
    for f in h["failure_samples"]:
        L.append(f"  - {f}")
    L.append(
        f"- 出场闸门没过：{h['gate_failed']} 个（目标角色没被请上场，这些会话不参与角色维度评分）"
    )
    for g in h["gate_failed_samples"]:
        L.append(f"  - {g}")
    L.append(
        f"- 共 {h['turns']} 轮：报错 {h['turn_errors']}，叙事者静默换模型 {h['fallback_turns']}，"
        f"管线与要求不符 {h['pipeline_mismatch_turns']}，style_skills 串进 RPG {h['style_leak_turns']}，账本缺失 {h['ledger_missing_turns']}"
    )
    L.append(
        f"- 裁判：绝对分 {h['judge_abs_done']} 份（报错 {h['judge_abs_errors']}），"
        f"证据原文核对通过率 {_pct(h['evidence_validity'])}（低于 90% 说明裁判在编证据，分数不可信）；"
        f"盲比 {h['judge_pair_rows']} 次（报错 {h['judge_pair_errors']}）"
    )
    L.append("")

    L.append("## 2. 绝对分（1–5 分，3 分 = 合格）")
    L.append("")
    L.append(
        f"每格是「平均分 ± 各会话之间的波动」。Δ 是与参照组 `{ref}` 在同一剧本同一轮次上的平均差值，括号里是 95% 区间：区间跨过 0 就说明差别可能只是碰巧。"
    )
    L.append("")
    table = s["absolute"]["table"]
    if table:
        dims = [d for d in DIMENSIONS if any(d in r["dims"] for r in table)]
        L.append(
            "| 组 | 模型 | 综合 | "
            + " | ".join(DIMENSIONS[d].name for d in dims)
            + " |"
        )
        L.append("|---|---|---|" + "---|" * len(dims))
        for r in table:
            cells = []
            for d in dims:
                e = r["dims"].get(d)
                if not e or e["mean"] is None:
                    cells.append("—")
                    continue
                txt = f"{e['mean']:.2f}±{_fmt(e['sd'], 1)}"
                dr = e.get("delta_ref")
                if dr and dr["mean"] is not None:
                    txt += f"<br>Δ{dr['mean']:+.2f} ({_fmt(dr['ci'][0])}, {_fmt(dr['ci'][1])})"
                cells.append(txt)
            L.append(
                f"| {r['arm']} | {r['model']} | {_fmt(r['overall'])} | "
                + " | ".join(cells)
                + " |"
            )
        L.append("")
        if s["absolute"]["per_card"]:
            L.append("按角色卡拆开（各维平均）：")
            L.append("")
            L.append("| 角色卡 | 组 | 模型 | 平均分 | 会话数 |")
            L.append("|---|---|---|---|---|")
            for r in s["absolute"]["per_card"]:
                L.append(
                    f"| {r['card']} | {r['arm']} | {r['model']} | {r['mean']:.2f} | {r['n']} |"
                )
            L.append("")
    else:
        L.append("（还没有绝对分。运行 `judge` 阶段。）")
        L.append("")

    L.append("## 3. 探针通过率（通过=1，部分=0.5，失败=0）")
    L.append("")
    if s["probes"]:
        L.append("| 组 | 模型 | 考点 | 通过率 | 样本 |")
        L.append("|---|---|---|---|---|")
        for p in s["probes"]:
            L.append(
                f"| {p['arm']} | {p['model']} | {p['kind']} | {_pct(p['pass_rate'])} | {p['n']} |"
            )
    else:
        L.append("（无探针结果）")
    L.append("")

    L.append("## 4. 确定性指标（纯代码统计，不花钱，每次都一样）")
    L.append("")
    det = s["deterministic"]
    if det:
        L.append(
            "违规类指标的理想值是 0；比例类指标请和参照组那一行对比。标「启发式」的只用来提示人工复查。"
        )
        L.append("")
        L.append(
            "| 指标 | " + " | ".join(f"{r['arm']}·{r['model']}" for r in det) + " |"
        )
        L.append("|---|" + "---|" * len(det))
        for fld, label, _ in DET_FIELDS:
            row = []
            for r in det:
                v = r.get(fld)
                if v is None:
                    row.append("—")
                elif fld.endswith("_rate") or fld in (
                    "dialogue_ratio_mean",
                    "ngram4_repeat_mean",
                    "adjacent_similarity_max",
                ):
                    row.append(_pct(v))
                else:
                    row.append(f"{v:.1f}")
            L.append(f"| {label} | " + " | ".join(row) + " |")
        leaks = {
            f"{r['arm']}·{r['model']}": r["leak_kinds"] for r in det if r["leak_kinds"]
        }
        if leaks:
            L.append("")
            L.append(
                "泄漏类型："
                + "；".join(f"{k}: {', '.join(v)}" for k, v in leaks.items())
            )
    else:
        L.append("（还没有指标。运行 `run` 阶段后会自动计算。）")
    L.append("")

    L.append("## 5. 两两盲比（同一剧本同一轮，匿名 A/B，左右互换各评一次）")
    L.append("")
    L.append(
        "胜率 = (胜 + 0.5×平) ÷ 总数。**抛硬币是 50%**。「碰巧概率」是两边其实一样好时出现这么悬殊结果的可能性，小于 5% 才算站得住。位置一致率是左右互换后裁判给出相同结论的比例，低于 70% 说明裁判受摆放位置影响大。"
    )
    L.append("")
    pw = [p for p in s["pairwise"] if p["kind"] != "self"]
    noise = [p for p in s["pairwise"] if p["kind"] == "self"]
    if pw:
        L.append(
            "| 类型 | X | Y | X 胜率 | 95% 区间 | 胜/平/负 | 碰巧概率 | 位置一致率 | 平均长度差(X−Y) |"
        )
        L.append("|---|---|---|---|---|---|---|---|---|")
        for p in pw:
            o = p["overall"]
            warn = (
                " ⚠️"
                if (
                    p["position_consistency"] is not None
                    and p["position_consistency"] < 0.7
                )
                else ""
            )
            kind = p["kind"] + ("（跨格式，仅供参考）" if p.get("cross_format") else "")
            L.append(
                f"| {kind} | {p['x']} | {p['y']} | {_pct(o['win_rate'])} | {_pct(o['ci_lo'])}–{_pct(o['ci_hi'])} | "
                f"{o['wins']}/{o['ties']}/{o['losses']} | {_pct(o['p_chance'])} | {_pct(p['position_consistency'])}{warn} | "
                f"{_fmt(p['mean_len_diff'], 0)} |"
            )
        L.append("")
        L.append("分维度 X 胜率：")
        L.append("")
        for p in pw:
            parts = [
                f"{DIMENSIONS[d].name if d in DIMENSIONS else d} {_pct(w['win_rate'])}(n={w['n']})"
                for d, w in p["dims"].items()
            ]
            L.append(f"- {p['x']} vs {p['y']}：" + "，".join(parts))
        L.append("")
    else:
        L.append(
            "（没有盲比结果。需要在 plan 里配 pairwise，或用 `--baseline` 对比旧跑次。）"
        )
        L.append("")

    L.append("## 6. 噪声底（同一组自己跟自己比）")
    L.append("")
    if noise:
        L.append(
            "同一组的第 0 次和第 1 次重复互相比较，理论上应该在 50% 左右。它的区间有多宽，这次跑分就只能分辨出多大的差距；上面的盲比结果如果落在这个宽度以内，就不要下结论。"
        )
        L.append("")
        for p in noise:
            o = p["overall"]
            half = (o["ci_hi"] - o["ci_lo"]) / 2
            L.append(
                f"- {p['x']}：胜率 {_pct(o['win_rate'])}，区间 {_pct(o['ci_lo'])}–{_pct(o['ci_hi'])}（半宽 ±{half * 100:.0f} 个百分点，样本 {o['n']}）"
            )
    else:
        L.append("（需要 repeats ≥ 2 才有噪声底。）")
    L.append("")

    L.append("## 7. 最差轮次摘录（分数 ≤ 2，供人工复核）")
    L.append("")
    if s["worst"]:
        for w in s["worst"]:
            L.append(
                f"- **{w['score']} 分 · {DIMENSIONS[w['dim']].name if w['dim'] in DIMENSIONS else w['dim']}** · "
                f"{w['card']}/{w['scenario_id']}/{w['arm']}#{w['repeat']} {w['turn']}：「{w['quote']}」 — {w['rationale']}"
            )
    else:
        L.append("（没有 ≤2 分的维度）")
    L.append("")

    c = s["cost"]
    L.append("## 8. 用量")
    L.append("")
    for model, t in c["generation_tokens_by_model"].items():
        L.append(f"- 生成 `{model}`：输入 {t['input']:,} / 输出 {t['output']:,} tokens")
    L.append(
        f"- 裁判：输入 {c['judge_tokens']['input']:,} / 输出 {c['judge_tokens']['output']:,} tokens"
    )
    L.append(f"- 注：{c['note']}")
    L.append("")
    return "\n".join(L)

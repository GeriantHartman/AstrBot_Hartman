"""Deterministic metrics — pure functions, no LLM, no network.

Everything here is cheap and repeatable, so it runs on every transcript.
Heuristic metrics are labelled as such in the report; they flag turns for a
human to look at rather than grade quality on their own.
"""

from __future__ import annotations

import re
import statistics
from typing import Any

from .cards import LexicalRules
from .normalize import char_len, normalize_ws, split_speech, squash

OOC_RE = re.compile(
    r"作为(?:一个|一名)?\s*(?:AI|人工智能|语言模型|AI助手|助手)"
    r"|我(?:只)?是(?:一个|一名)?\s*(?:AI|人工智能|语言模型|程序|聊天机器人|AI助手)"
    r"|根据(?:资料|设定|提示|你的要求)"
    r"|角色设定"
    r"|system\s*prompt"
    r"|系统提示"
    r"|提示词",
    re.I,
)

LEAK_PATTERNS: dict[str, re.Pattern[str]] = {
    "xiaoai_core": re.compile(r"</?xiaoai_core>", re.I),
    "think_tag": re.compile(r"</?think(?:ing)?>", re.I),
    "xml_tag": re.compile(r"</?[a-z][a-z_]{2,}>"),
    "scene_state": re.compile(r"\[/?SCENE_STATE\]"),
    "rpg_marker": re.compile(r"\[/?RPG_[A-Z_]+\]"),
    "contract": re.compile(r"Narrative\s*Contract|NarrativeBrief|必须体现|叙事契约"),
    "director": re.compile(r"\bDirector\b|内心投影"),
    "tool_call": re.compile(r"tool_call|function_call|```"),
    "markdown_header": re.compile(r"^\s{0,3}#{1,6}\s", re.M),
    "status_bar": re.compile(r"━{8,}"),
}

AGENCY_RE = re.compile(r"你(?:感到|觉得|心想|决定|不由得|不禁|心里一|暗自|忍不住)")
OPEN_END_RE = re.compile(
    r"[？?]|[吗呢吧呀]\s*[~～♪。！!…]*\s*$|好不好|要不要|怎么样|对吧"
)


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return float(ordered[idx])


def ngram_repeat_ratio(text: str, n: int = 4) -> float:
    s = squash(text)
    grams = [s[i : i + n] for i in range(len(s) - n + 1)]
    if not grams:
        return 0.0
    return 1.0 - len(set(grams)) / len(grams)


def shingles(text: str, n: int = 5) -> set[str]:
    s = squash(text)
    return {s[i : i + n] for i in range(len(s) - n + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def count_tokens(segments: list[str], token: str) -> int:
    return sum(seg.count(token) for seg in segments)


def turn_metrics(text: str, rules: LexicalRules) -> dict[str, Any]:
    """Metrics for a single reply."""
    speech, mode = split_speech(text)
    speech_len = sum(char_len(s) for s in speech)
    total_len = char_len(text)
    flat = normalize_ws(text)

    self_counts = {
        tok: count_tokens(speech, tok)
        for tok in [*rules.self_allowed, *rules.self_forbidden]
    }
    call_counts = {
        tok: count_tokens(speech, tok)
        for tok in [*rules.call_allowed, *rules.call_discouraged]
    }
    never_hits = [lit for lit in rules.never_say_literals if normalize_ws(lit) in flat]
    ooc_hits = [m.group(0) for m in OOC_RE.finditer(text)]
    leaks = sorted(name for name, pat in LEAK_PATTERNS.items() if pat.search(text))
    sig_hits = [s for s in rules.signature_phrases if s in squash(text)]
    quote_reuse = [
        q
        for q in rules.canonical_quotes
        if len(squash(q)) >= 8 and squash(q) in squash(text)
    ]
    tail = text.strip()[-40:]
    return {
        "mode": mode,
        "len": total_len,
        "dialogue_ratio": (speech_len / total_len) if total_len else 0.0,
        "self_counts": self_counts,
        "self_forbidden_hits": sum(self_counts.get(t, 0) for t in rules.self_forbidden),
        "call_counts": call_counts,
        "call_discouraged_hits": sum(
            call_counts.get(t, 0) for t in rules.call_discouraged
        ),
        "never_say_hits": never_hits,
        "ooc_hits": ooc_hits,
        "leaks": leaks,
        "ngram4_repeat": ngram_repeat_ratio(text, 4),
        "signature_hits": sig_hits,
        "canonical_quote_reuse": quote_reuse,
        "agency_hits": [m.group(0) for m in AGENCY_RE.finditer(text)],
        "open_ending": bool(OPEN_END_RE.search(tail)),
        "empty": total_len == 0,
    }


def session_metrics(replies: list[str], rules: LexicalRules) -> dict[str, Any]:
    """Aggregate per-turn metrics over one scored session."""
    per_turn = [turn_metrics(r, rules) for r in replies]
    n = len(per_turn)
    if n == 0:
        return {"turns": 0, "per_turn": []}

    lens = [t["len"] for t in per_turn]
    sh = [shingles(r) for r in replies]
    adjacent = [jaccard(sh[i - 1], sh[i]) for i in range(1, n)]
    openings = [squash(r)[:8] for r in replies]
    repeated_openings = sum(
        1 for i, o in enumerate(openings) if o and len(o) >= 4 and o in openings[:i]
    )
    rare_rates = {
        tok: sum(1 for t in per_turn if t["self_counts"].get(tok, 0) > 0) / n
        for tok in rules.self_rare
    }
    rare_violations = sorted(
        tok
        for tok, limit in rules.self_rare.items()
        if rare_rates.get(tok, 0.0) > limit
    )

    def turns_with(key: str) -> list[int]:
        return [i for i, t in enumerate(per_turn) if t[key]]

    return {
        "turns": n,
        "len_mean": statistics.fmean(lens),
        "len_p50": _pct(lens, 0.5),
        "len_max": max(lens),
        "dialogue_ratio_mean": statistics.fmean(t["dialogue_ratio"] for t in per_turn),
        "narration_mode_rate": sum(1 for t in per_turn if t["mode"] == "narration") / n,
        "self_forbidden_hits": sum(t["self_forbidden_hits"] for t in per_turn),
        "self_rare_rates": rare_rates,
        "self_rare_violations": rare_violations,
        "call_discouraged_hits": sum(t["call_discouraged_hits"] for t in per_turn),
        "never_say_hits": sum(len(t["never_say_hits"]) for t in per_turn),
        "ooc_hits": sum(len(t["ooc_hits"]) for t in per_turn),
        "leak_turns": len(turns_with("leaks")),
        "leak_kinds": sorted({k for t in per_turn for k in t["leaks"]}),
        "ngram4_repeat_mean": statistics.fmean(t["ngram4_repeat"] for t in per_turn),
        "adjacent_similarity_mean": statistics.fmean(adjacent) if adjacent else 0.0,
        "adjacent_similarity_max": max(adjacent) if adjacent else 0.0,
        "opening_repeat_rate": repeated_openings / n,
        "signature_rate": sum(1 for t in per_turn if t["signature_hits"]) / n,
        "canonical_quote_reuse": sum(len(t["canonical_quote_reuse"]) for t in per_turn),
        "agency_hits": sum(len(t["agency_hits"]) for t in per_turn),
        "open_ending_rate": sum(1 for t in per_turn if t["open_ending"]) / n,
        "empty_turns": len(turns_with("empty")),
        "per_turn": per_turn,
    }


def ops_metrics(turns: list[dict[str, Any]]) -> dict[str, Any]:
    """Operational health from transcript turn records."""
    lat = [
        float(t.get("latency_s") or 0.0)
        for t in turns
        if t.get("latency_s") is not None
    ]
    presence = [
        t.get("target_present") for t in turns if t.get("target_present") is not None
    ]
    return {
        "errors": sum(1 for t in turns if t.get("error")),
        "latency_p50": _pct(lat, 0.5),
        "latency_p95": _pct(lat, 0.95),
        "fallback_turns": sum(1 for t in turns if t.get("fallback_used")),
        "pipeline_mismatch_turns": sum(1 for t in turns if t.get("pipeline_mismatch")),
        "style_leak_turns": sum(1 for t in turns if t.get("style_skills_leak")),
        "presence_rate": (sum(1 for p in presence if p) / len(presence))
        if presence
        else None,
        "tokens_in": sum(
            int((t.get("usage") or {}).get("input", 0) or 0) for t in turns
        ),
        "tokens_out": sum(
            int((t.get("usage") or {}).get("output", 0) or 0) for t in turns
        ),
    }

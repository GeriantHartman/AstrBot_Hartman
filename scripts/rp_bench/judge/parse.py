"""Parse judge JSON and verify that evidence quotes really exist in the transcript."""

from __future__ import annotations

import json
import re
from typing import Any

from ..normalize import normalize_ws

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)
_QUOTE_TRIM = "\"'“”‘’「」『』…. "
MIN_QUOTE_CHARS = 4
VERDICTS = ("pass", "partial", "fail")
PAIR_WINNERS = ("A", "B", "tie")


class JudgeParseError(ValueError):
    pass


def extract_json_object(text: str) -> dict[str, Any]:
    """First JSON object in ``text``: fenced block, else first balanced {...}."""
    text = text or ""
    candidates = [m.group(1) for m in _FENCE_RE.finditer(text)] + [text]
    for cand in candidates:
        start = cand.find("{")
        while start != -1:
            depth = 0
            in_str = False
            esc = False
            for i in range(start, len(cand)):
                ch = cand[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(cand[start : i + 1])
                        except json.JSONDecodeError:
                            break
                        if isinstance(obj, dict):
                            return obj
                        break
            start = cand.find("{", start + 1)
    raise JudgeParseError("no JSON object found in judge output")


def _norm_quote(q: str) -> str:
    return normalize_ws(str(q or "")).strip(_QUOTE_TRIM)


def quote_in_transcript(
    quote: str, turn_id: str, replies: dict[str, str]
) -> tuple[bool, bool]:
    """(found anywhere, found in the named turn). Ellipses split a quote into parts."""
    q = _norm_quote(quote)
    if len(q) < MIN_QUOTE_CHARS:
        return False, False
    parts = [p for p in re.split(r"…+|\.{3,}", q) if len(p) >= MIN_QUOTE_CHARS] or [q]
    norm_replies = {k: normalize_ws(v) for k, v in replies.items()}

    def found_in(text: str) -> bool:
        return all(p in text for p in parts)

    in_turn = turn_id in norm_replies and found_in(norm_replies[turn_id])
    anywhere = in_turn or any(found_in(t) for t in norm_replies.values())
    return anywhere, in_turn


def _clamp_score(value: Any) -> int | None:
    if value is None:
        return None
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    if score < 1 or score > 5:
        return None
    return score


def validate_abs(
    obj: dict[str, Any], dims: list[str], replies: dict[str, str]
) -> tuple[dict[str, Any], list[str]]:
    """Normalise an absolute-score result. Returns (result, problems for a retry note)."""
    problems: list[str] = []
    raw_dims = obj.get("dims") if isinstance(obj.get("dims"), dict) else {}
    out_dims: dict[str, Any] = {}
    for key in dims:
        entry = raw_dims.get(key)
        if not isinstance(entry, dict):
            problems.append(f"缺少维度 {key}")
            out_dims[key] = {
                "score": None,
                "valid": False,
                "evidence": [],
                "rationale": "",
                "reason": "missing",
            }
            continue
        raw_score = entry.get("score")
        score = _clamp_score(raw_score)
        if raw_score is not None and score is None:
            problems.append(f"{key} 的 score 必须是 1-5 的整数或 null")
        evidence = []
        valid_quotes = 0
        for ev in entry.get("evidence") or []:
            if not isinstance(ev, dict):
                continue
            turn = str(ev.get("turn") or "")
            quote = str(ev.get("quote") or "")
            anywhere, in_turn = quote_in_transcript(quote, turn, replies)
            evidence.append(
                {"turn": turn, "quote": quote, "found": anywhere, "turn_match": in_turn}
            )
            valid_quotes += int(anywhere)
        valid = score is None or valid_quotes > 0
        if not valid:
            problems.append(f"{key} 的证据在对话记录中找不到原文")
        out_dims[key] = {
            "score": score,
            "valid": valid,
            "evidence": evidence,
            "rationale": str(entry.get("rationale") or ""),
            "reason": "" if valid else "evidence_invalid",
        }

    probes = []
    for p in obj.get("probes") or []:
        if not isinstance(p, dict):
            continue
        verdict = str(p.get("verdict") or "").lower()
        anywhere, _ = quote_in_transcript(
            str(p.get("quote") or ""), str(p.get("turn") or ""), replies
        )
        probes.append(
            {
                "turn": str(p.get("turn") or ""),
                "kind": str(p.get("kind") or ""),
                "verdict": verdict if verdict in VERDICTS else "invalid",
                "quote": str(p.get("quote") or ""),
                "quote_found": anywhere,
                "rationale": str(p.get("rationale") or ""),
            }
        )
    flags = [str(f) for f in obj.get("flags") or [] if f]
    return {"dims": out_dims, "probes": probes, "flags": flags}, problems


def validate_pair(
    obj: dict[str, Any], dims: list[str]
) -> tuple[dict[str, Any], list[str]]:
    problems: list[str] = []
    raw_dims = obj.get("dims") if isinstance(obj.get("dims"), dict) else {}
    out: dict[str, Any] = {}
    for key in dims:
        entry = raw_dims.get(key)
        winner = (
            str((entry or {}).get("winner") or "") if isinstance(entry, dict) else ""
        )
        winner = "tie" if winner.lower() == "tie" else winner.upper()
        if winner not in PAIR_WINNERS:
            problems.append(f"{key} 的 winner 必须是 A、B 或 tie")
            winner = "invalid"
        out[key] = {
            "winner": winner,
            "reason": str((entry or {}).get("reason") or "")
            if isinstance(entry, dict)
            else "",
        }
    overall = obj.get("overall") if isinstance(obj.get("overall"), dict) else {}
    ow = str(overall.get("winner") or "")
    ow = "tie" if ow.lower() == "tie" else ow.upper()
    if ow not in PAIR_WINNERS:
        problems.append("overall.winner 必须是 A、B 或 tie")
        ow = "invalid"
    return {
        "dims": out,
        "overall": {"winner": ow, "reason": str(overall.get("reason") or "")},
    }, problems

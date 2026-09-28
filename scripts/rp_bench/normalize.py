"""Text normalisation shared by metrics and the judge view."""

from __future__ import annotations

import re

_BAR_LINE_RE = re.compile(r"^\s*━{8,}\s*$")
_THINK_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.S | re.I)
_DYNAMIC_RE = re.compile(
    r"\[RPG_DYNAMIC_CONTEXT_START\].*?\[RPG_DYNAMIC_CONTEXT_END\]", re.S
)

# Quoted speech in narration: 「…」 『…』 “…” "…"
_QUOTE_RE = re.compile(r"「([^」]*)」|『([^』]*)』|“([^”]*)”|\"([^\"\n]*)\"")
# Stage directions in chat-style replies: （…） (…) *…*
_ACTION_RE = re.compile(r"（[^）]*）|\([^)]*\)|\*[^*\n]+\*")
_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[\s\W_]+", re.UNICODE)


def strip_status_bar(text: str) -> str:
    """Remove the RPG status bar block (lines of ━ delimiting the panel)."""
    lines = (text or "").splitlines()
    bar_idx = [i for i, line in enumerate(lines) if _BAR_LINE_RE.match(line)]
    if len(bar_idx) >= 2:
        lines = lines[: bar_idx[0]] + lines[bar_idx[-1] + 1 :]
    return "\n".join(lines).strip()


def clean_reply(text: str) -> str:
    """Judge/metrics view of a reply: no status bar, no thinking, no dynamic block."""
    text = _THINK_RE.sub("", text or "")
    text = _DYNAMIC_RE.sub("", text)
    return strip_status_bar(text)


def char_len(text: str) -> int:
    """Visible length: characters excluding whitespace."""
    return len(_WS_RE.sub("", text or ""))


def squash(text: str) -> str:
    """Drop whitespace and punctuation; used for n-gram and substring matching."""
    return _PUNCT_RE.sub("", text or "")


def normalize_ws(text: str) -> str:
    return _WS_RE.sub("", text or "")


def split_speech(text: str) -> tuple[list[str], str]:
    """Return (speech segments, mode).

    If the reply contains quoted speech it is treated as narration and only
    quoted segments count as speech (mode ``narration``). Otherwise it is a
    chat-style reply: everything except stage directions is speech
    (mode ``chat``). Speaker attribution inside multi-NPC narration is not
    attempted — metrics built on this are approximate by design.
    """
    text = text or ""
    quoted = ["".join(g for g in m.groups() if g) for m in _QUOTE_RE.finditer(text)]
    quoted = [q for q in quoted if q.strip()]
    if quoted:
        return quoted, "narration"
    stripped = _ACTION_RE.sub(" ", text)
    return ([stripped] if stripped.strip() else []), "chat"

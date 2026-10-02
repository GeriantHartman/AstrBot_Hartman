from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def normalize_and_dedupe_strings(items: Iterable[Any] | None) -> list[str]:
    if items is None:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def to_halfwidth(text: str) -> str:
    """Map full-width ASCII forms back to their half-width equivalents.

    Chinese IMEs emit full-width punctuation by default, so a user typing
    ``～`` produces U+FF5E where a config file written by an ASCII keyboard
    holds ``~`` U+007E. Any literal comparison between the two silently fails.

    The mapping is 1 character to 1 character, so callers may still slice the
    *original* string by the matched prefix's length.
    """
    if not text:
        return ""

    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            # Full-width ！-～ (U+FF01-U+FF5E) -> ASCII !-~ (U+0021-U+007E)
            out.append(chr(code - 0xFEE0))
        elif code == 0x3000:
            # Ideographic space -> ASCII space
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)

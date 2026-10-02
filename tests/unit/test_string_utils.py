"""Tests for astrbot.core.utils.string_utils."""

from __future__ import annotations

from astrbot.core.utils.string_utils import to_halfwidth

WAKE_PREFIX = "~"
FULLWIDTH_PREFIX = "～"


def test_fullwidth_punctuation_maps_to_ascii():
    assert to_halfwidth("～") == "~"
    assert to_halfwidth("／") == "/"
    assert to_halfwidth("！") == "!"
    assert to_halfwidth("？") == "?"
    assert to_halfwidth("Ａ１") == "A1"


def test_ideographic_space_maps_to_ascii_space():
    assert to_halfwidth("　") == " "


def test_ascii_and_cjk_ideographs_pass_through_unchanged():
    assert to_halfwidth("abcXYZ019") == "abcXYZ019"
    assert to_halfwidth("你好世界") == "你好世界"
    assert to_halfwidth("") == ""


def test_fullwidth_cjk_punctuation_also_normalizes():
    """The whole U+FF01-U+FF5E block maps, CJK punctuation included.

    This is broader than strictly needed for wake prefixes, but harmless: the
    result is only ever used for a prefix comparison, never echoed back.
    """
    assert to_halfwidth("，") == ","
    assert to_halfwidth("：") == ":"


def test_length_is_preserved_one_to_one():
    """Callers slice the *original* string, so the mapping must not change length."""
    for text in ("～你好", "／去海边", "　abc", "混合ＡＢ～!"):
        assert len(to_halfwidth(text)) == len(text)


def test_fullwidth_wake_prefix_matches_halfwidth_config():
    """Regression: a Chinese IME emits `～` (U+FF5E) where the config holds `~`.

    The old literal comparison dropped such messages silently in WakingCheck.
    """
    message = f"{FULLWIDTH_PREFIX}爱莉，好久不见"

    # The bug: raw comparison fails.
    assert not message.startswith(WAKE_PREFIX)

    # The fix: normalize both sides.
    assert to_halfwidth(message).startswith(to_halfwidth(WAKE_PREFIX))

    # And the prefix is still strippable from the original by length.
    assert message[len(WAKE_PREFIX) :] == "爱莉，好久不见"

"""skill arm: a character skill folder inlined as the persona (no tools to read files)."""

import pytest

from scripts.rp_bench.cards import (
    CardError,
    find_skill_dir,
    inline_card,
    render_skill_persona,
    skill_files,
)
from scripts.rp_bench.config import ARMS, CHAT_ARMS
from scripts.rp_bench.export import render_session


def _skill(tmp_path, name="cyrene-skill"):
    d = tmp_path / name
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: cyrene\n---\n# 昔涟\n\n## 运行规则\n"
        "1. 先读 `profile.md`。\n2. 再读 `personality.md`。\n3. 参考 `missing.md`。\n"
        "4. 见 `README.md`，然后再看一次 `profile.md`。\n",
        encoding="utf-8",
    )
    (d / "profile.md").write_text("身份：哀丽秘榭的女儿", encoding="utf-8")
    (d / "personality.md").write_text("温柔诗意", encoding="utf-8")
    (d / "README.md").write_text("仓库说明", encoding="utf-8")
    (d / "tabletop_werewolf.md").write_text("狼人杀规则", encoding="utf-8")
    return d


def test_skill_arm_registered_as_chat_arm():
    assert "skill" in ARMS and "skill" in CHAT_ARMS


def test_skill_files_follow_referenced_order_and_skip_meta(tmp_path):
    d = _skill(tmp_path)
    assert [p.name for p in skill_files(d)] == ["profile.md", "personality.md"]


def test_render_skill_persona_inlines_verbatim(tmp_path):
    _skill(tmp_path)
    card = inline_card({"key": "cyrene", "name": "昔涟", "game": "崩坏：星穹铁道"})
    text, meta = render_skill_persona(card, skills_dir=tmp_path)
    assert text.startswith("# 昔涟")  # frontmatter stripped
    assert "## 附录：profile.md\n\n身份：哀丽秘榭的女儿" in text
    assert text.index("profile.md\n\n身份") < text.index("personality.md\n\n温柔")
    assert "狼人杀" not in text and "仓库说明" not in text
    assert meta["files"] == ["SKILL.md", "profile.md", "personality.md"]
    assert meta["chars"] == len(text)


def test_missing_skill_folder_is_a_clear_error(tmp_path):
    card = inline_card({"key": "nobody", "name": "无名"})
    with pytest.raises(CardError, match="no character skill folder"):
        find_skill_dir(card, skills_dir=tmp_path)


def test_long_prompt_is_linked_not_inlined():
    row = {
        "card": "cyrene",
        "card_name": "昔涟",
        "arm": "skill",
        "model": "m",
        "repeat": 0,
        "scenario_id": "s",
        "system_prompt": "卡" * 5000,
        "system_prompt_sha": "abc",
        "prompt_meta": {"files": ["SKILL.md", "profile.md"], "chars": 5000},
        "turns": [],
    }
    md = render_session(row, depth=3)
    assert "卡" * 100 not in md
    assert "../../../prompts/cyrene__skill__abc.md" in md
    assert "SKILL.md、profile.md" in md

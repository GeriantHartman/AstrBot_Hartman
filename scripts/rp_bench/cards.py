"""Character cards: canonical YAML → persona prompt, judge sheet, lexical rules.

The persona block reuses the RPG plugin's own renderers
(``build_profile_payload`` + ``_format_voice_fingerprint``) so the raw /
style_skills arms see the same voice block the RPG narrator sees. Those
imports pull in ``astrbot.api`` — call ``sandbox.ensure_sandbox_root`` first.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

from . import LIVE_DATA_DIR, PACKAGE_DIR, RPG_PLUGIN_DIR

SKILLS_DIR = LIVE_DATA_DIR / "skills"
# Files in a character skill folder that describe the skill rather than the character.
SKILL_META_FILES = {
    "README.md",
    "LICENSE",
    "manifest.json",
    "quality-report.md",
    "roleplay-test-report.md",
}
_SKILL_REF_RE = re.compile(r"`([\w\-.]+\.md)`")

CARDS_DIR = RPG_PLUGIN_DIR / "canonical_characters"
OVERRIDES_DIR = PACKAGE_DIR / "card_overrides"

# First-person forms a character might wrongly adopt. Anything here that the
# card does not list as allowed counts as a forbidden self-reference.
GENERIC_SELF_FORMS = (
    "人家",
    "本小姐",
    "本姑娘",
    "咱家",
    "俺",
    "本座",
    "老娘",
    "妾身",
    "本王",
    "朕",
    "本宫",
    "小女子",
    "本大爷",
)

_QUOTED_RE = re.compile(r"[“\"「『]([^”\"」』]{1,24})[”\"」』]")
_NEGATION_RE = re.compile(
    r"(不要|不可|不能|禁止|别|绝不|避免|不用|勿)[^。；;，,]{0,10}$"
)


# Phrases in a never_say rule that introduce the allowed alternative, not the banned one.
_REPLACEMENT_RE = re.compile(
    r"(专属称呼是|固定用|改用|应该用|应称|必须依然称呼他为|她用|他用)\s*$"
)


class CardError(ValueError):
    pass


@dataclass
class LexicalRules:
    self_allowed: list[str] = field(default_factory=list)
    self_rare: dict[str, float] = field(default_factory=dict)
    self_forbidden: list[str] = field(default_factory=list)
    call_allowed: list[str] = field(default_factory=list)
    call_discouraged: list[str] = field(default_factory=list)
    never_say_literals: list[str] = field(default_factory=list)
    signature_phrases: list[str] = field(default_factory=list)
    canonical_quotes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class Card:
    key: str
    name: str
    aliases: list[str]
    data: dict[str, Any]
    path: Path
    sha256: str
    overrides: dict[str, Any] = field(default_factory=dict)

    @property
    def tier(self) -> str:
        return str(self.data.get("tier") or "minor")

    @property
    def voice(self) -> dict[str, Any]:
        v = self.data.get("voice") or {}
        return v if isinstance(v, dict) else {}

    def names(self) -> list[str]:
        return [self.name, *[a for a in self.aliases if a]]

    def call_player_placeholder(self) -> str:
        """Value for the {call_player} scenario placeholder."""
        if self.overrides.get("call_player_placeholder"):
            return str(self.overrides["call_player_placeholder"])
        rules = lexical_rules(self)
        return rules.call_allowed[0] if rules.call_allowed else "你"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _load_overrides(key: str) -> dict[str, Any]:
    path = OVERRIDES_DIR / f"{key}.yaml"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}
    if not isinstance(data, dict):
        raise CardError(f"{path}: override file must be a mapping")
    return data


def load_card(key: str, *, cards_dir: Path = CARDS_DIR) -> Card:
    """Load a card by file stem (``elysia``) or by name/alias (``爱莉希雅``)."""
    path = cards_dir / f"{key}.yaml"
    if not path.exists():
        path = _find_by_name(key, cards_dir)
    with path.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp)
    if not isinstance(data, dict) or not data.get("name"):
        raise CardError(f"{path}: not a canonical character card")
    return Card(
        key=path.stem,
        name=str(data["name"]).strip(),
        aliases=[str(a) for a in (data.get("aliases") or []) if a],
        data=data,
        path=path,
        sha256=_sha256_file(path),
        overrides=_load_overrides(path.stem),
    )


def _find_by_name(name: str, cards_dir: Path) -> Path:
    target = name.strip().lower()
    for path in sorted(cards_dir.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        names = [
            str(data.get("name") or ""),
            *[str(a) for a in data.get("aliases") or []],
        ]
        if any(n.strip().lower() == target for n in names if n):
            return path
    raise CardError(f"no canonical card matches {name!r} in {cards_dir}")


def list_card_keys(cards_dir: Path = CARDS_DIR) -> list[str]:
    return [
        p.stem for p in sorted(cards_dir.glob("*.yaml")) if not p.name.startswith("_")
    ]


def inline_card(spec: dict[str, Any]) -> Card:
    """Card for a character that has no canonical YAML (bare arm only).

    Only name/game/aliases exist, so persona-based arms will abort on it and
    lexical metrics fall back to generic checks.
    """
    data = {
        "name": spec["name"],
        "game": spec.get("game", ""),
        "aliases": list(spec.get("aliases") or []),
    }
    raw = f"{data['name']}|{data['game']}"
    return Card(
        key=str(spec.get("key") or spec["name"]),
        name=str(spec["name"]),
        aliases=[str(a) for a in data["aliases"]],
        data=data,
        path=Path(f"<inline:{spec['name']}>"),
        sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16],
        overrides=_load_overrides(str(spec.get("key") or ""))
        if spec.get("key")
        else {},
    )


def resolve_card(entry: Any) -> Card:
    """Plan ``cards`` entry → Card: a canonical key/name, or an inline {name, game}."""
    if isinstance(entry, dict):
        key = str(entry.get("key") or "")
        if key and (CARDS_DIR / f"{key}.yaml").exists():
            return load_card(key)
        return inline_card(entry)
    return load_card(str(entry))


def _strip_frontmatter(text: str) -> str:
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                return "\n".join(lines[i + 1 :]).strip()
    return text.strip()


def find_skill_dir(card: Card, *, skills_dir: Path = SKILLS_DIR) -> Path:
    """Character skill folder: card_overrides ``skill_dir``, else ``<key>-skill`` / ``<key>``."""
    override = card.overrides.get("skill_dir")
    candidates = [Path(override)] if override else []
    candidates += [skills_dir / f"{card.key}-skill", skills_dir / card.key]
    for path in candidates:
        path = path if path.is_absolute() else skills_dir / path
        if (path / "SKILL.md").exists():
            return path
    raise CardError(
        f"{card.key}: no character skill folder with SKILL.md; tried "
        + ", ".join(str(c) for c in candidates)
        + " (set skill_dir in card_overrides/<card>.yaml)"
    )


def skill_files(skill_dir: Path) -> list[Path]:
    """Files SKILL.md tells the model to read, in the order it lists them.

    A bare-model run has no file tools, so the persona must carry them inline.
    """
    body = _strip_frontmatter((skill_dir / "SKILL.md").read_text(encoding="utf-8"))
    out: list[Path] = []
    for name in _SKILL_REF_RE.findall(body):
        path = skill_dir / name
        if name in SKILL_META_FILES or name == "SKILL.md" or path in out:
            continue
        if path.exists():
            out.append(path)
    return out


def render_skill_persona(
    card: Card, *, skills_dir: Path = SKILLS_DIR
) -> tuple[str, dict[str, Any]]:
    """SKILL.md body + every file it references, inlined verbatim."""
    skill_dir = find_skill_dir(card, skills_dir=skills_dir)
    skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    parts = [_strip_frontmatter(skill_md)]
    files = skill_files(skill_dir)
    for path in files:
        parts.append(
            f"## 附录：{path.name}\n\n{path.read_text(encoding='utf-8').strip()}"
        )
    text = "\n\n---\n\n".join(parts) + "\n"
    meta = {
        "source": "character_skill",
        "skill_dir": str(skill_dir),
        "files": ["SKILL.md", *[p.name for p in files]],
        "file_sha": {p.name: _sha256_file(p) for p in [skill_dir / "SKILL.md", *files]},
        "chars": len(text),
    }
    return text, meta


def render_bare_prompt(card: Card) -> str:
    """System prompt for the bare arm: identity only, everything else from the model."""
    game = str(card.data.get("game") or "").strip()
    who = f"《{game}》中的角色「{card.name}」" if game else f"「{card.name}」"
    return f"你是{who}。请以{card.name}的身份与我对话。"


def registry_accepts(card: Card) -> bool:
    """True when the RPG plugin's own loader would register this card."""
    from plugins.astrbot_plugin_agentic_RPG.core.canonical_character_loader import (
        CanonicalCharacterRegistry,
    )

    registry = CanonicalCharacterRegistry(card.path.parent)
    return registry._validate(card.path.name, dict(card.data))


def _plugin_payload(card: Card) -> dict[str, Any]:
    from plugins.astrbot_plugin_agentic_RPG.core.canonical_character_loader import (
        build_profile_payload,
    )

    payload = build_profile_payload(card.data)
    if payload is None:
        raise CardError(
            f"{card.key}: card has no profile.profile_text; the RPG plugin would fall back "
            "to LLM generation, so there is no fixed persona to benchmark"
        )
    return payload


def render_voice_block(card: Card) -> str:
    from plugins.astrbot_plugin_agentic_RPG.prompt.assembler import (
        _format_voice_fingerprint,
    )

    payload = _plugin_payload(card)
    npc = SimpleNamespace(
        voice_fingerprint=payload["voice_fingerprint"],
        canonical_quotes=payload["canonical_quotes"],
        never_say=payload["never_say"],
    )
    return _format_voice_fingerprint(npc).strip("\n")


def render_persona(card: Card) -> str:
    """Persona prompt for chat arms (raw / style_skills)."""
    payload = _plugin_payload(card)
    tags = "、".join(str(t) for t in payload.get("personality_tags") or [])
    lines = [
        f"你是「{payload['name']}」。以下是你的完整角色卡，请始终以该角色的身份与用户对话。",
        "",
        "## 人物档案",
        payload["profile_text"].strip(),
    ]
    if tags:
        lines += ["", f"性格标签：{tags}"]
    if payload.get("secret"):
        lines += [
            "",
            "## 隐藏设定（用于扮演，不要直接说出）",
            payload["secret"].strip(),
        ]
    lines += ["", "## 声音与互动细则", render_voice_block(card)]
    return "\n".join(lines).strip() + "\n"


def render_judge_sheet(card: Card) -> str:
    """Reference sheet the judge scores against. Judge-only; never sent to arms."""
    data = card.data
    profile = data.get("profile") or {}
    voice = card.voice
    guide = data.get("interaction_guidelines") or {}
    out = [f"# 角色：{card.name}（{data.get('game', '')}，tier={card.tier}）"]
    if card.aliases:
        out.append("别名：" + "、".join(card.aliases))
    if profile.get("profile_text"):
        out += ["", "## 人物档案", str(profile["profile_text"]).strip()]
    if profile.get("secret"):
        out += ["", "## 隐藏设定", str(profile["secret"]).strip()]
    out += ["", "## 声音"]
    for key, label in (
        ("self_reference", "自称"),
        ("call_player", "称呼玩家"),
        ("tone", "语气"),
        ("speech_pattern", "说话模式"),
    ):
        if voice.get(key):
            out.append(f"- {label}：{voice[key]}")
    if voice.get("signature_phrases"):
        out.append("- 标志句式：" + " / ".join(map(str, voice["signature_phrases"])))
    if voice.get("imagery_words"):
        out.append("- 意象词：" + " / ".join(map(str, voice["imagery_words"])))
    if isinstance(guide, dict) and guide:
        out += ["", "## 互动细则"]
        out += [f"- {k}：{v}" for k, v in guide.items() if v]
    for layer in data.get("state_layers") or []:
        if isinstance(layer, dict) and layer.get("name"):
            if "## 状态分层" not in out:
                out += ["", "## 状态分层"]
            out.append(
                f"- 【{layer.get('name')}】触发：{layer.get('trigger', '')}；语气：{layer.get('tone_shift', '')}"
            )
    if data.get("inner_tension"):
        out += ["", f"## 内在张力\n{data['inner_tension']}"]
    if data.get("never_say"):
        out += ["", "## 绝不（never_say）"] + [f"- {x}" for x in data["never_say"]]
    if data.get("canonical_quotes"):
        out += ["", "## 经典台词（参照口吻，不要求照抄）"] + [
            f"- {x}" for x in data["canonical_quotes"]
        ]
    return "\n".join(out).strip() + "\n"


def _quoted_tokens(text: str) -> tuple[list[str], list[str]]:
    """Split quoted tokens in a descriptive rule into (allowed, discouraged).

    Card voice rules are prose such as ``不要固定成机械的“亲爱的”``; a token
    whose preceding clause carries a negation is treated as discouraged.
    """
    allowed: list[str] = []
    discouraged: list[str] = []
    text = text or ""
    if not _QUOTED_RE.search(text) and 0 < len(text.strip()) <= 6:
        return [text.strip()], []  # bare value such as ``self_reference: 我``
    for m in _QUOTED_RE.finditer(text):
        token = m.group(1).strip()
        if not token:
            continue
        before = text[max(0, m.start() - 12) : m.start()]
        target = discouraged if _NEGATION_RE.search(before) else allowed
        if token not in target:
            target.append(token)
    return allowed, discouraged


def _signature_core(phrase: str) -> str:
    core = re.sub(r"[~～♪♥…。，,！!？?\s\.]+", "", str(phrase))
    return core


def lexical_rules(card: Card) -> LexicalRules:
    voice = card.voice
    ov = card.overrides
    self_allowed, _ = _quoted_tokens(str(voice.get("self_reference") or ""))
    call_allowed, call_discouraged = _quoted_tokens(str(voice.get("call_player") or ""))

    self_allowed = _dedup(self_allowed + list(ov.get("allowed_self") or []))
    call_allowed = _dedup(
        [t for t in call_allowed if t not in (ov.get("forbidden_call") or [])]
        + list(ov.get("allowed_call") or [])
    )
    call_discouraged = _dedup(call_discouraged + list(ov.get("forbidden_call") or []))
    self_forbidden = _dedup(
        [f for f in GENERIC_SELF_FORMS if f not in self_allowed]
        + list(ov.get("forbidden_self") or [])
    )
    self_forbidden = [f for f in self_forbidden if f not in self_allowed]

    # never_say entries are prose; a quoted token can be the forbidden phrase
    # ("称呼用户为“凡人”") or the *correct* replacement ("她固定用“人家”").
    literals: list[str] = []
    allowed = set(self_allowed) | set(call_allowed)
    ignore = set(ov.get("never_say_ignore") or [])
    for entry in card.data.get("never_say") or []:
        entry = str(entry)
        for m in _QUOTED_RE.finditer(entry):
            token = m.group(1).strip()
            before = entry[max(0, m.start() - 10) : m.start()]
            if len(token) < 2 or token in allowed or token in ignore:
                continue
            if _REPLACEMENT_RE.search(before):
                continue
            after = entry[m.end() : min(len(entry), m.end() + 10)]
            if re.search(r"(把|将)\s*$", before) and re.search(
                r"^\s*(演成|当成|当作|理解为|写成|变成|当作)", after
            ):
                continue
            literals.append(token)
    literals += list(ov.get("never_say_literals") or [])

    sigs = [
        s
        for s in (_signature_core(p) for p in voice.get("signature_phrases") or [])
        if len(s) >= 2
    ]

    return LexicalRules(
        self_allowed=self_allowed,
        self_rare={str(k): float(v) for k, v in (ov.get("rare_self") or {}).items()},
        self_forbidden=self_forbidden,
        call_allowed=call_allowed,
        call_discouraged=call_discouraged,
        never_say_literals=_dedup(literals),
        signature_phrases=_dedup(sigs),
        canonical_quotes=[str(q) for q in card.data.get("canonical_quotes") or []],
    )


def _dedup(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        item = str(item).strip()
        if item and item not in out:
            out.append(item)
    return out

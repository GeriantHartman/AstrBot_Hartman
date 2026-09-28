"""Scenario scripts: fixed player lines + embedded probes, identical across arms."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

MIN_SCORED_TURNS = 10
MAX_SCORED_TURNS = 20

PLACEHOLDERS = ("char", "player", "call_player")
_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")

# kind -> default expectation shown to the judge when the scenario gives none.
PROBE_KINDS: dict[str, str] = {
    "plant_fact": "玩家在这一轮埋下一个事实，后续轮次会考察角色是否记得。本轮只需角色合理接住。",
    "memory_recall": "角色应准确记起先前埋下的事实，不遗忘、不编造细节。",
    "ooc_bait": "玩家诱导出戏。角色必须保持身份，不承认是 AI/模型/设定，不输出系统或资料口吻。",
    "never_say_trigger": "玩家诱导角色说出卡片 never_say 中禁止的内容。角色不应落入。",
    "low_effort_player": "玩家只给了很少的输入。角色应主动推进或抛出可接的钩子，而不是反问“你想做什么”或原地重复。",
    "agency_trap": "玩家的输入给了替玩家行动的机会。回应不应替玩家说话、做决定或断言玩家内心感受。",
    "state_layer_trigger": "输入触发角色卡中的状态切换。角色语气与句式应按卡片的状态分层切换。",
    "secret_pressure": "玩家逼问角色的秘密。角色应符合卡片的秘密设定与性格来处理，不能直接当资料全盘托出，也不能编造设定外的秘密。",
}

DEFAULT_DIMENSIONS = [
    "voice",
    "fidelity",
    "plot_drive",
    "liveliness",
    "in_character",
    "memory",
    "agency",
    "delight",
]


class ScenarioError(ValueError):
    pass


@dataclass
class Probe:
    kind: str
    key: str = ""
    fact: str = ""
    ref: str = ""
    expect: str = ""

    def expectation(self) -> str:
        return self.expect or PROBE_KINDS.get(self.kind, "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "key": self.key,
            "fact": self.fact,
            "ref": self.ref,
            "expect": self.expectation(),
        }


@dataclass
class Turn:
    id: str
    text: str
    probes: list[Probe] = field(default_factory=list)


@dataclass
class Scenario:
    id: str
    version: int
    card: str
    title: str
    player_name: str
    premise: str
    dimensions: list[str]
    scene_intro: str
    rpg_preset: str
    rpg_setup_turns: list[str]
    rpg_min_scored_presence: float
    turns: list[Turn]
    content_hash: str
    source_path: str = ""

    @property
    def is_generic(self) -> bool:
        return self.card == "*"

    def applies_to(self, card_key: str) -> bool:
        return self.is_generic or self.card == card_key

    def truncated(self, n_turns: int) -> Scenario:
        """Smoke-mode copy with the first ``n_turns`` scored turns only."""
        keep = self.turns[: max(1, n_turns)]
        planted = set()
        kept_turns = []
        for turn in keep:
            probes = []
            for probe in turn.probes:
                if probe.kind == "memory_recall" and probe.ref not in planted:
                    continue
                if probe.kind == "plant_fact":
                    planted.add(probe.key)
                probes.append(probe)
            kept_turns.append(Turn(id=turn.id, text=turn.text, probes=probes))
        dims = self.dimensions
        if not any(p.kind == "memory_recall" for t in kept_turns for p in t.probes):
            dims = [d for d in dims if d != "memory"]
        # distinct hash so smoke cells never pair with full-length cells
        return Scenario(
            **{
                **self.__dict__,
                "turns": kept_turns,
                "dimensions": dims,
                "content_hash": f"{self.content_hash}-s{len(kept_turns)}",
            }
        )

    def render(
        self, values: dict[str, str], *, card_names: list[str] | None = None
    ) -> Scenario:
        """Substitute {char}/{player}/{call_player} into every player-facing string."""
        values = {"player": self.player_name, **values}
        if self.is_generic and card_names:
            raw = json.dumps(
                [
                    self.premise,
                    self.scene_intro,
                    self.rpg_setup_turns,
                    [t.text for t in self.turns],
                ],
                ensure_ascii=False,
            )
            for name in card_names:
                if name and name in raw:
                    raise ScenarioError(
                        f"{self.id}: generic scenario (card: '*') must use {{char}} "
                        f"instead of the literal name {name!r}"
                    )

        def sub(text: str) -> str:
            return _PLACEHOLDER_RE.sub(
                lambda m: values.get(m.group(1), m.group(0)), text
            )

        turns = [
            Turn(
                id=t.id,
                text=sub(t.text),
                probes=[
                    Probe(p.kind, p.key, sub(p.fact), p.ref, sub(p.expect))
                    for p in t.probes
                ],
            )
            for t in self.turns
        ]
        return Scenario(
            **{
                **self.__dict__,
                "premise": sub(self.premise),
                "scene_intro": sub(self.scene_intro),
                "rpg_setup_turns": [sub(s) for s in self.rpg_setup_turns],
                "turns": turns,
            }
        )


def _content_hash(raw: dict[str, Any]) -> str:
    encoded = json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]


def _check_placeholders(sid: str, text: str) -> None:
    for name in _PLACEHOLDER_RE.findall(text or ""):
        if name not in PLACEHOLDERS:
            raise ScenarioError(f"{sid}: unknown placeholder {{{name}}} in {text!r}")


def parse_scenario(
    raw: dict[str, Any], *, source_path: str = "", strict_turns: bool = True
) -> Scenario:
    if not isinstance(raw, dict):
        raise ScenarioError(f"{source_path}: scenario must be a mapping")
    sid = str(raw.get("id") or "").strip()
    if not sid:
        raise ScenarioError(f"{source_path}: missing id")
    card = str(raw.get("card") or "").strip()
    if not card:
        raise ScenarioError(
            f"{sid}: missing card (use '*' for card-agnostic scenarios)"
        )

    chat = raw.get("chat") or {}
    rpg = raw.get("rpg") or {}
    gate = rpg.get("presence_gate") or {}

    dims = list(raw.get("dimensions") or DEFAULT_DIMENSIONS)

    turns: list[Turn] = []
    seen_ids: set[str] = set()
    planted: set[str] = set()
    for idx, item in enumerate(raw.get("turns") or [], start=1):
        if isinstance(item, str):
            item = {"text": item}
        if not isinstance(item, dict):
            raise ScenarioError(f"{sid}: turn #{idx} must be a mapping or string")
        tid = str(item.get("id") or f"t{idx:02d}")
        if tid in seen_ids:
            raise ScenarioError(f"{sid}: duplicate turn id {tid}")
        seen_ids.add(tid)
        text = str(item.get("text") or "").strip()
        if not text:
            raise ScenarioError(f"{sid}: turn {tid} has empty text")
        _check_placeholders(sid, text)
        probes: list[Probe] = []
        for p in item.get("probes") or []:
            if not isinstance(p, dict):
                raise ScenarioError(f"{sid}: probe in {tid} must be a mapping")
            kind = str(p.get("kind") or "")
            if kind not in PROBE_KINDS:
                raise ScenarioError(
                    f"{sid}: unknown probe kind {kind!r} in {tid}; expected one of {sorted(PROBE_KINDS)}"
                )
            probe = Probe(
                kind=kind,
                key=str(p.get("key") or ""),
                fact=str(p.get("fact") or ""),
                ref=str(p.get("ref") or ""),
                expect=str(p.get("expect") or ""),
            )
            if kind == "plant_fact":
                if not probe.key or not probe.fact:
                    raise ScenarioError(
                        f"{sid}: plant_fact in {tid} needs key and fact"
                    )
                if probe.key in planted:
                    raise ScenarioError(f"{sid}: duplicate plant_fact key {probe.key}")
                planted.add(probe.key)
            if kind == "memory_recall":
                if probe.ref not in planted:
                    raise ScenarioError(
                        f"{sid}: memory_recall in {tid} refers to {probe.ref!r}, "
                        "which is not planted by an earlier plant_fact"
                    )
            _check_placeholders(sid, probe.fact + probe.expect)
            probes.append(probe)
        turns.append(Turn(id=tid, text=text, probes=probes))

    if strict_turns and not (MIN_SCORED_TURNS <= len(turns) <= MAX_SCORED_TURNS):
        raise ScenarioError(
            f"{sid}: has {len(turns)} scored turns; expected {MIN_SCORED_TURNS}-{MAX_SCORED_TURNS}"
        )

    premise = str(raw.get("premise") or "")
    scene_intro = str(chat.get("scene_intro") or "")
    setup_turns = [str(s) for s in (rpg.get("setup_turns") or [])]
    for text in [premise, scene_intro, *setup_turns]:
        _check_placeholders(sid, text)

    has_memory_probe = any(p.kind == "memory_recall" for t in turns for p in t.probes)
    if "memory" in dims and not has_memory_probe:
        dims = [d for d in dims if d != "memory"]

    return Scenario(
        id=sid,
        version=int(raw.get("version") or 1),
        card=card,
        title=str(raw.get("title") or sid),
        player_name=str(raw.get("player_name") or "旅人"),
        premise=premise,
        dimensions=dims,
        scene_intro=scene_intro,
        rpg_preset=str(rpg.get("preset") or "default"),
        rpg_setup_turns=setup_turns,
        rpg_min_scored_presence=float(gate.get("min_scored_presence", 0.8)),
        turns=turns,
        content_hash=_content_hash(raw),
        source_path=source_path,
    )


def load_scenario(path: Path | str, *, strict_turns: bool = True) -> Scenario:
    path = Path(path)
    with path.open("r", encoding="utf-8") as fp:
        raw = yaml.safe_load(fp)
    return parse_scenario(raw, source_path=str(path), strict_turns=strict_turns)


def load_scenarios(paths: list[Path]) -> list[Scenario]:
    scenarios = [load_scenario(p) for p in paths]
    ids = [s.id for s in scenarios]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ScenarioError(f"duplicate scenario ids: {sorted(dupes)}")
    return scenarios

"""Benchmark plan (YAML) loading, CLI overrides and secret resolution."""

from __future__ import annotations

import copy
import glob
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import LIVE_DATA_DIR, PACKAGE_DIR

# bare  = model only: one-line "you are <name> from <game>", no card, no plugin,
#         no tools, no knowledge base — tests what the model itself knows.
# skill = the character skill folder (data/skills/<key>-skill) inlined as the
#         persona, still no plugin / tools / knowledge base.
# raw   = the RPG plugin's canonical YAML card rendered as the persona.
ARMS = ("bare", "skill", "raw", "style_skills", "rpg4", "rpg5", "art")
CHAT_ARMS = ("bare", "skill", "raw", "style_skills")
RPG_ARMS = ("rpg4", "rpg5", "art")
SECRETS_FILE = LIVE_DATA_DIR / "rp_bench" / "secrets.yaml"


class PlanError(ValueError):
    pass


def arm_family(arm: str) -> str:
    return "chat" if arm in CHAT_ARMS else "rpg"


@dataclass
class JudgeSpec:
    provider_id: str = ""
    temperature: float = 0.0
    endpoint_url: str = ""
    endpoint_model: str = ""
    endpoint_api_key_env: str = ""
    max_retries: int = 1

    @property
    def enabled(self) -> bool:
        return bool(self.provider_id or self.endpoint_url)

    @property
    def judge_id(self) -> str:
        if not self.enabled:
            return ""
        return self.provider_id or f"endpoint:{self.endpoint_model}"


@dataclass
class OpenApiSpec:
    base_url: str = "http://127.0.0.1:6185"
    api_key_env: str = "RPBENCH_ASTRBOT_API_KEY"
    config_id: str = ""
    username: str = "rp-bench"
    timeout_s: float = 900.0
    ledger_wait_s: float = 15.0


@dataclass
class Plan:
    name: str
    cards: list[
        Any
    ]  # canonical card key, or {key, name, game, aliases} for bare-only characters
    scenario_paths: list[Path]
    arms: list[str]
    models: list[str]
    repeats: int = 3
    judge: JudgeSpec = field(default_factory=JudgeSpec)
    pairwise: list[tuple[str, str]] = field(default_factory=list)
    reference_arm: str = "raw"
    open_api: OpenApiSpec = field(default_factory=OpenApiSpec)
    close_style_skills_in_rpg: bool = True
    style_skills_config: dict[str, Any] = field(default_factory=dict)
    concurrency: dict[str, int] = field(
        default_factory=lambda: {"rpg": 1, "direct": 4, "judge": 4}
    )
    prices: dict[str, dict[str, float]] = field(default_factory=dict)
    smoke_turns: int = 3
    source_path: str = ""
    raw: dict[str, Any] = field(default_factory=dict)  # effective YAML after overrides

    def uses_rpg(self) -> bool:
        return any(a in RPG_ARMS for a in self.arms)


def _resolve_globs(patterns: list[str], base: Path) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        p = Path(pattern)
        full = str(p if p.is_absolute() else base / p)
        matches = sorted(Path(m).resolve() for m in glob.glob(full, recursive=True))
        if not matches:
            raise PlanError(f"scenario pattern matched nothing: {pattern}")
        for m in matches:
            if m not in paths:
                paths.append(m)
    return paths


def apply_overrides(
    raw: dict[str, Any], overrides: dict[str, Any] | None
) -> dict[str, Any]:
    """CLI overrides (--models/--cards/--arms/--repeats) on top of the plan YAML."""
    raw = copy.deepcopy(raw)
    for key, value in (overrides or {}).items():
        if value is None or value == []:
            continue
        raw[key] = value
    # a pairwise entry that references an arm no longer in the plan is dropped
    arms = set(raw.get("arms") or [])
    raw["pairwise"] = [p for p in raw.get("pairwise") or [] if set(p) <= arms]
    if raw.get("reference_arm") and raw["reference_arm"] not in arms:
        raw.pop("reference_arm")
    return raw


def load_plan(path: Path | str, overrides: dict[str, Any] | None = None) -> Plan:
    path = Path(path)
    if not path.is_absolute() and not path.exists():
        path = PACKAGE_DIR / path
    with path.open("r", encoding="utf-8") as fp:
        raw = yaml.safe_load(fp) or {}
    return parse_plan(apply_overrides(raw, overrides), source_path=str(path))


def effective_plan_yaml(plan: Plan) -> str:
    """Plan as run, with absolute scenario paths so it can be resumed from the run dir."""
    raw = copy.deepcopy(plan.raw)
    raw["name"] = plan.name
    raw["scenarios"] = [str(p) for p in plan.scenario_paths]
    return yaml.safe_dump(raw, allow_unicode=True, sort_keys=False)


def _card_entry(entry: Any) -> Any:
    if isinstance(entry, str) and "@" in entry:
        # "芙宁娜@原神" → a character with no canonical card (bare arm only)
        name, _, game = entry.partition("@")
        if not name.strip():
            raise PlanError(f"card entry {entry!r} has an empty name")
        return {
            "key": name.strip(),
            "name": name.strip(),
            "game": game.strip(),
            "aliases": [],
        }
    if isinstance(entry, str) and entry.strip():
        return entry.strip()
    if isinstance(entry, dict) and entry.get("name"):
        return {
            "key": str(entry.get("key") or entry["name"]),
            "name": str(entry["name"]),
            "game": str(entry.get("game") or ""),
            "aliases": [str(a) for a in entry.get("aliases") or []],
        }
    raise PlanError(
        f"cards entries must be a card key or {{name, game}}; got {entry!r}"
    )


def parse_plan(raw: dict[str, Any], *, source_path: str = "") -> Plan:
    if not isinstance(raw, dict):
        raise PlanError("plan must be a mapping")
    arms = [str(a) for a in raw.get("arms") or []]
    bad = [a for a in arms if a not in ARMS]
    if bad or not arms:
        raise PlanError(f"arms must be a non-empty subset of {ARMS}; got {arms}")
    models = [str(m) for m in raw.get("models") or []]
    if not models:
        raise PlanError("models: list at least one AstrBot provider id")
    cards = [_card_entry(c) for c in raw.get("cards") or []]
    if not cards:
        raise PlanError("cards: list at least one card key")

    j = raw.get("judge") or {}
    endpoint = j.get("endpoint") or {}
    judge = JudgeSpec(
        provider_id=str(j.get("provider_id") or ""),
        temperature=float(j.get("temperature", 0.0)),
        endpoint_url=str(endpoint.get("url") or ""),
        endpoint_model=str(endpoint.get("model") or ""),
        endpoint_api_key_env=str(endpoint.get("api_key_env") or ""),
        max_retries=int(j.get("max_retries", 1)),
    )

    pairs: list[tuple[str, str]] = []
    for pair in raw.get("pairwise") or []:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise PlanError(f"pairwise entries must be [armA, armB]; got {pair}")
        a, b = str(pair[0]), str(pair[1])
        if a not in arms or b not in arms:
            raise PlanError(f"pairwise arms {a}/{b} must both be listed in arms")
        pairs.append((a, b))

    oa = raw.get("open_api") or {}
    open_api = OpenApiSpec(
        base_url=str(oa.get("base_url") or OpenApiSpec.base_url).rstrip("/"),
        api_key_env=str(oa.get("api_key_env") or OpenApiSpec.api_key_env),
        config_id=str(oa.get("config_id") or ""),
        username=str(oa.get("username") or OpenApiSpec.username),
        timeout_s=float(oa.get("timeout_s") or OpenApiSpec.timeout_s),
        ledger_wait_s=float(oa.get("ledger_wait_s") or OpenApiSpec.ledger_wait_s),
    )

    base = Path(source_path).parent.parent if source_path else PACKAGE_DIR
    scenario_patterns = [str(s) for s in raw.get("scenarios") or []]
    if not scenario_patterns:
        raise PlanError("scenarios: list at least one path or glob")

    concurrency = {"rpg": 1, "direct": 4, "judge": 4}
    concurrency.update({k: int(v) for k, v in (raw.get("concurrency") or {}).items()})

    return Plan(
        name=str(raw.get("name") or Path(source_path).stem or "plan"),
        cards=cards,
        scenario_paths=_resolve_globs(scenario_patterns, base),
        arms=arms,
        models=models,
        repeats=max(1, int(raw.get("repeats", 3))),
        judge=judge,
        pairwise=pairs,
        reference_arm=str(
            raw.get("reference_arm") or ("raw" if "raw" in arms else arms[0])
        ),
        open_api=open_api,
        close_style_skills_in_rpg=bool(
            (raw.get("rpg") or {}).get("close_style_skills", True)
        ),
        style_skills_config=dict((raw.get("style_skills") or {}).get("config") or {}),
        concurrency=concurrency,
        prices={str(k): dict(v) for k, v in (raw.get("prices") or {}).items()},
        smoke_turns=int(raw.get("smoke_turns", 3)),
        source_path=source_path,
        raw=raw,
    )


def load_secrets() -> dict[str, str]:
    if not SECRETS_FILE.exists():
        return {}
    with SECRETS_FILE.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}
    return {str(k): str(v) for k, v in data.items() if v is not None}


def secret(env_name: str, file_key: str) -> str:
    """Env var first, then the gitignored data/rp_bench/secrets.yaml."""
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    return load_secrets().get(file_key, "")

"""RP Bench CLI — designed to be driven by an agent, not by hand.

    uv run python -m scripts.rp_bench providers
    uv run python -m scripts.rp_bench probe --plan scripts/rp_bench/plans/bare.yaml --models A,B [--live-llm]
    uv run python -m scripts.rp_bench plan  --plan ... --models A,B --dry-run
    uv run python -m scripts.rp_bench all   --plan ... --models A,B [--cards elysia,firefly] [--repeats 2] [--smoke]
    uv run python -m scripts.rp_bench all   --resume data/rp_bench/runs/<dir>      # continue after a crash
    uv run python -m scripts.rp_bench list
    uv run python -m scripts.rp_bench pair  --resume <new_run> --baseline <old_run>

Every command that touches a run ends with exactly one machine-readable line:

    RPBENCH_RESULT {"status": "ok" | "partial" | "error", ...}

Exit codes: 0 ok, 2 partial (some sessions failed or missing — rerun with
--resume), 1 error (bad arguments/config, nothing usable produced).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from . import DEFAULT_RUNS_DIR, REPO_ROOT
from .sandbox import ensure_sandbox_root

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RESULT_FILE = "run_result.json"


def _csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [v.strip() for v in value.split(",") if v.strip()]


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="rp_bench", description="Roleplay benchmark: card × model × plugin"
    )
    p.add_argument(
        "command",
        choices=[
            "providers",
            "list",
            "probe",
            "plan",
            "run",
            "judge",
            "pair",
            "report",
            "all",
        ],
    )
    p.add_argument("--plan", help="plan YAML (not needed with --resume)")
    p.add_argument("--resume", type=Path, help="existing run directory to continue")
    p.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    p.add_argument(
        "--models", help="comma-separated AstrBot provider ids (overrides plan)"
    )
    p.add_argument("--cards", help="comma-separated card keys (overrides plan)")
    p.add_argument("--arms", help="comma-separated arms (overrides plan)")
    p.add_argument("--repeats", type=int, help="repeats per cell (overrides plan)")
    p.add_argument(
        "--add-arms",
        help="with --resume: add arms to an existing run; existing sessions are kept, "
        "only the new arm's sessions are generated",
    )
    p.add_argument(
        "--judge",
        help="judge provider id (overrides plan; allowed with --resume to score an existing run)",
    )
    p.add_argument("--smoke", action="store_true", help="1 repeat, first N turns only")
    p.add_argument("--dry-run", action="store_true", help="plan: estimate only")
    p.add_argument("--baseline", type=Path, help="pair: old run directory")
    p.add_argument(
        "--no-noise-floor", action="store_true", help="pair: skip self pairs"
    )
    p.add_argument(
        "--live-llm", action="store_true", help="probe: one tiny call per model"
    )
    return p.parse_args()


def _emit(result: dict[str, Any]) -> None:
    print("RPBENCH_RESULT " + json.dumps(result, ensure_ascii=False), flush=True)


def _overrides(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "models": _csv(args.models),
        "cards": _csv(args.cards),
        "arms": _csv(args.arms),
        "repeats": args.repeats,
    }


def extend_run_arms(run_dir: Path, new_arms: list[str]) -> list[str]:
    """Append arms to a run's plan.yaml and manifest.

    Session keys depend on (card, scenario@hash, arm, model, repeat) only, so
    existing sessions keep their keys and the next ``run`` generates just the
    new arm's cells.
    """
    import yaml

    from .config import ARMS
    from .store import MANIFEST, RunStore

    bad = [a for a in new_arms if a not in ARMS]
    if bad or not new_arms:
        raise SystemExit(f"--add-arms must be a subset of {ARMS}; got {new_arms}")
    plan_file = run_dir / "plan.yaml"
    raw = yaml.safe_load(plan_file.read_text(encoding="utf-8")) or {}
    arms = list(raw.get("arms") or [])
    added = [a for a in new_arms if a not in arms]
    if not added:
        return arms
    arms += added
    raw["arms"] = arms
    plan_file.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    store = RunStore(run_dir)
    man = store.read_json(MANIFEST) or {}
    man.setdefault("plan", {})["arms"] = arms
    from .store import now_utc8

    man.setdefault("history", []).append(
        {"added_arms": added, "at": now_utc8().isoformat()}
    )
    store.write_json(MANIFEST, man)
    return arms


def _resolve_plan_path(args: argparse.Namespace) -> Path:
    if args.resume:
        if not (args.resume / "plan.yaml").exists():
            raise SystemExit(f"{args.resume} has no plan.yaml; is it a run directory?")
        if any(v for v in _overrides(args).values()):
            raise SystemExit(
                "--models/--cards/--arms/--repeats cannot be combined with --resume "
                "(they would change every session key); start a new run instead, "
                "or use --add-arms to extend this one"
            )
        if args.add_arms:
            extend_run_arms(args.resume, _csv(args.add_arms) or [])
        return args.resume / "plan.yaml"
    if args.add_arms:
        raise SystemExit("--add-arms needs --resume <run_dir>")
    if args.plan:
        return Path(args.plan)
    raise SystemExit("--plan is required unless --resume is given")


def cmd_providers() -> int:
    from .providers import load_cmd_config

    cfg = load_cmd_config()
    sources = {s.get("id"): s for s in cfg.get("provider_sources") or []}
    rows = []
    for p in cfg.get("provider") or []:
        src = sources.get(p.get("provider_source_id"), {})
        ptype = p.get("provider_type") or src.get("provider_type") or "chat_completion"
        if ptype != "chat_completion":
            continue
        rows.append(
            {
                "id": p.get("id"),
                "model": p.get("model", ""),
                "type": p.get("type") or src.get("type", ""),
                "enabled": bool(p.get("enable", True)),
            }
        )
    for r in rows:
        flag = "" if r["enabled"] else "  (disabled)"
        print(f"  {r['id']:<48} {r['type']:<32} {r['model']}{flag}")
    _emit({"status": "ok", "providers": rows})
    return 0


def cmd_list(runs_dir: Path) -> int:
    from .store import FAILURES, MANIFEST, TRANSCRIPTS, RunStore

    runs = []
    if runs_dir.exists():
        for d in sorted(runs_dir.iterdir()):
            if not d.is_dir() or not (d / MANIFEST).exists():
                continue
            store = RunStore(d)
            man = store.read_json(MANIFEST) or {}
            result = store.read_json(RESULT_FILE) or {}
            done = store.completed(TRANSCRIPTS)
            failed = {f.get("cell_key") for f in store.read(FAILURES)} - done
            runs.append(
                {
                    "run_dir": str(d),
                    "plan": man.get("plan", {}).get("name"),
                    "created_at": man.get("created_at"),
                    "models": man.get("plan", {}).get("models"),
                    "arms": man.get("plan", {}).get("arms"),
                    "sessions_done": len(done),
                    "sessions_planned": (result.get("sessions") or {}).get("planned"),
                    "sessions_failed": len(failed),
                    "status": result.get("status", "unknown"),
                }
            )
    for r in runs:
        print(
            f"  {Path(r['run_dir']).name}  {r['status']:<8} {r['sessions_done']}/{r['sessions_planned']}  models={r['models']}"
        )
    _emit({"status": "ok", "runs": runs})
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = _args()

    if args.command == "providers":
        return cmd_providers()
    if args.command == "list":
        return cmd_list(args.runs_dir)

    try:
        plan_path = _resolve_plan_path(args)
    except SystemExit as exc:
        _emit({"status": "error", "error": str(exc)})
        return 1

    if args.resume:
        run_dir = args.resume.resolve()
    elif args.command in ("probe", "plan"):
        run_dir = (args.runs_dir / "_scratch").resolve()
    else:
        from .store import stamp_utc8

        name = Path(plan_path).stem + ("-smoke" if args.smoke else "")
        run_dir = (args.runs_dir / f"{stamp_utc8()}+0800-{name}").resolve()

    # Must happen before anything imports astrbot (cards/providers/drivers do, lazily).
    ensure_sandbox_root(run_dir / ".astrbot_sandbox")

    from .config import PlanError, effective_plan_yaml, load_plan

    overrides = {} if args.resume else _overrides(args)
    if args.judge:
        overrides["judge"] = {"provider_id": args.judge, "temperature": 0}
    try:
        plan = load_plan(plan_path, overrides)
    except (PlanError, OSError) as exc:
        _emit({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
        return 1

    if args.command == "probe":
        from .probe import run_probe

        rc = asyncio.run(run_probe(plan, live_llm=args.live_llm))
        _emit(
            {
                "status": "ok" if rc == 0 else "error",
                "probe": "all checks passed" if rc == 0 else "see FAIL lines above",
                "models": plan.models,
                "live_llm": args.live_llm,
            }
        )
        return rc
    if args.command == "plan":
        from .estimate import print_estimate

        try:
            e = print_estimate(plan, smoke=args.smoke)
        except Exception as exc:
            _emit({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
            return 1
        _emit({"status": "ok", "estimate": e})
        return 0

    from .orchestrator import load_context, log
    from .store import FAILURES, MANIFEST, REPORT, SUMMARY, TRANSCRIPTS, RunStore

    store = RunStore(run_dir)
    smoke = args.smoke or bool(
        (store.read_json(MANIFEST) or {}).get("plan", {}).get("smoke")
    )
    try:
        ctx = load_context(plan, store, smoke=smoke)
    except Exception as exc:
        _emit(
            {
                "status": "error",
                "run_dir": str(run_dir),
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        return 1

    if store.read_json(MANIFEST) is None:
        from .manifest import build_manifest

        judge_family = ""
        if plan.judge.enabled:
            try:
                from .judge.runner import JudgeClient
                from .providers import ProviderPool

                judge_family = JudgeClient(
                    plan.judge, ProviderPool() if plan.judge.provider_id else None
                ).family()
            except Exception:
                judge_family = "unknown"
        store.write_json(
            MANIFEST,
            build_manifest(
                plan,
                cards=list(ctx.cards.values()),
                scenarios=ctx.scenarios,
                judge_id=plan.judge.judge_id,
                judge_family=judge_family,
                smoke=smoke,
            ),
        )
        store.write_text("plan.yaml", effective_plan_yaml(plan))
    elif args.judge:
        # scoring an existing run with a judge chosen later
        man = store.read_json(MANIFEST)
        man["judge"] = {"id": plan.judge.judge_id, "family": "", "temperature": 0}
        try:
            from .providers import (
                load_cmd_config,
                model_family,
                resolve_provider_config,
            )

            man["judge"]["family"] = model_family(
                args.judge, resolve_provider_config(args.judge, load_cmd_config())
            )
        except Exception:
            man["judge"]["family"] = "unknown"
        store.write_json(MANIFEST, man)
    log(f"run dir: {run_dir}")

    counts: dict[str, int] = {}

    async def pipeline() -> None:
        from .orchestrator import (
            judge_stage,
            metrics_stage,
            pair_stage,
            run_stage,
        )

        if args.command in ("run", "all"):
            counts.update(await run_stage(ctx))
            metrics_stage(ctx)
        if args.command in ("judge", "all"):
            metrics_stage(ctx)
            await judge_stage(ctx)
        if args.command in ("pair", "all"):
            await pair_stage(
                ctx, baseline_dir=args.baseline, noise_floor=not args.no_noise_floor
            )

    asyncio.run(pipeline())

    from .orchestrator import export_stage
    from .report import build_summary, render_markdown

    exported = export_stage(ctx)
    summary = build_summary(store, judge_id=plan.judge.judge_id or None)
    store.write_json(SUMMARY, summary)
    store.write_text(REPORT, render_markdown(summary))

    planned = len(ctx.cells())
    done = store.completed(TRANSCRIPTS)
    failures = [f for f in store.read(FAILURES) if f.get("cell_key") not in done]
    gate_failed = summary["health"]["gate_failed"]
    missing = planned - len(done)
    status = "ok" if missing == 0 else "partial"
    result = {
        "status": status,
        "run_dir": str(run_dir),
        "plan": plan.name,
        "models": plan.models,
        "arms": plan.arms,
        "cards": list(ctx.cards),
        "judge": plan.judge.judge_id or None,
        "sessions": {
            "planned": planned,
            "done": len(done),
            "missing": missing,
            "failed_this_invocation": counts.get("failed", 0),
            "gate_failed": gate_failed,
        },
        "failures": [f"{f.get('label')}: {f.get('error')}" for f in failures[-5:]],
        "files": {
            "index": str(store.path("index.md")),
            "report": str(store.path(REPORT)),
            "transcripts_jsonl": str(store.path(TRANSCRIPTS)),
            "compare": [str(store.dir / c) for c in exported["compare"]],
        },
        "next": (
            "done"
            if status == "ok"
            else f"uv run python -m scripts.rp_bench all --resume {run_dir}"
        ),
    }
    store.write_json(RESULT_FILE, result)
    log(f"index: {store.path('index.md')}")
    _emit(result)
    return 0 if status == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())

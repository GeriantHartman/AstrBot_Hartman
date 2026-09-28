"""Phase-0 self check: verify every assumption the harness depends on.

Each check prints PASS / FAIL / SKIP with a one-line reason. Nothing here
spends tokens unless --live-llm is given (then: one tiny call per model).
"""

from __future__ import annotations

import time
import uuid

from .config import RPG_ARMS, Plan, secret


class _Checks:
    def __init__(self) -> None:
        self.failed = 0

    def ok(self, name: str, detail: str = "") -> None:
        print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))

    def bad(self, name: str, detail: str) -> None:
        self.failed += 1
        print(f"  FAIL  {name} — {detail}")

    def skip(self, name: str, detail: str) -> None:
        print(f"  SKIP  {name} — {detail}")


async def run_probe(plan: Plan, *, live_llm: bool = False) -> int:
    c = _Checks()
    print(f"RP Bench probe — plan {plan.name}")

    # 1. providers resolvable from the live cmd_config.json
    from .providers import (
        ProviderConfigError,
        ProviderPool,
        provider_chat,
        resolve_provider_config,
    )

    pool = ProviderPool()
    for pid in [
        *plan.models,
        *([plan.judge.provider_id] if plan.judge.provider_id else []),
    ]:
        try:
            cfg = resolve_provider_config(pid, pool.cmd_config)
            c.ok(f"provider {pid}", f"{cfg.get('type')} model={cfg.get('model')}")
        except ProviderConfigError as exc:
            c.bad(f"provider {pid}", str(exc))

    # 2. cards
    from .cards import (
        lexical_rules,
        registry_accepts,
        render_bare_prompt,
        render_persona,
        resolve_card,
    )

    needs_persona = any(a != "bare" for a in plan.arms)
    cards = []
    for key in plan.cards:
        try:
            card = resolve_card(key)
            rules = lexical_rules(card)
            if not needs_persona:
                c.ok(f"card {card.key}", f"bare prompt: {render_bare_prompt(card)}")
                cards.append(card)
                continue
            persona = render_persona(card)
            accepted = registry_accepts(card)
            detail = (
                f"{card.name} tier={card.tier} persona={len(persona)} chars "
                f"self={rules.self_allowed} call={rules.call_allowed} never_say_literals={len(rules.never_say_literals)}"
            )
            if accepted:
                c.ok(f"card {key}", detail)
            else:
                c.bad(
                    f"card {key}",
                    "the RPG plugin's loader would reject this card; " + detail,
                )
            cards.append(card)
        except Exception as exc:
            c.bad(f"card {key}", f"{type(exc).__name__}: {exc}")

    # 3. scenarios
    from .matrix import expand
    from .scenarios import load_scenarios

    try:
        scenarios = load_scenarios(plan.scenario_paths)
        cells = expand(cards, scenarios, plan.arms, plan.models, plan.repeats)
        c.ok(
            "scenarios", f"{len(scenarios)} loaded, {len(cells)} sessions in the matrix"
        )
        for card in cards:
            if not any(s.applies_to(card.key) for s in scenarios):
                c.bad(
                    f"scenarios for {card.key}",
                    "no scenario targets this card (use card: '*' or add one)",
                )
    except Exception as exc:
        c.bad("scenarios", f"{type(exc).__name__}: {exc}")
        cells = []

    # 4. style_skills builder
    if "style_skills" in plan.arms and cells:
        try:
            from .drivers.style_skills import StyleSkillsPromptBuilder

            builder = StyleSkillsPromptBuilder(plan.style_skills_config)
            cell = next(x for x in cells if x.arm == "style_skills")
            sp, meta = await builder(cell, "\n# Persona Instructions\n\nX\n")
            c.ok(
                "style_skills hook",
                f"layers={meta['layers']} +{len(sp)} chars; skills={builder.skill_hashes()}",
            )
        except Exception as exc:
            c.bad("style_skills hook", f"{type(exc).__name__}: {exc}")

    # 5. RPG via Open API
    if plan.uses_rpg():
        from .drivers.openapi import (
            OpenApiClient,
            OpenApiError,
            config_plugin_set,
            plugin_enabled,
        )
        from .drivers.rpg import RPG_PLUGIN_NAME, STYLE_PLUGIN_NAME
        from .ledger import RPG_DATA_ROOT, LedgerReader, webchat_umo

        try:
            ps = config_plugin_set(plan.open_api.config_id)
            if plugin_enabled(ps, RPG_PLUGIN_NAME):
                c.ok(
                    "config plugin_set", f"{plan.open_api.config_id or 'default'}: {ps}"
                )
            else:
                c.bad("config plugin_set", f"{RPG_PLUGIN_NAME} not enabled in {ps}")
            if plugin_enabled(ps, STYLE_PLUGIN_NAME):
                note = (
                    "will send /style close in RPG sessions"
                    if plan.close_style_skills_in_rpg
                    else "NOT closing it (rpg.close_style_skills=false)"
                )
                c.skip("style_skills in RPG config", note)
        except OpenApiError as exc:
            c.bad("config plugin_set", str(exc))

        if (RPG_DATA_ROOT / "llm_audit_index").exists():
            c.ok("audit ledger dir", str(RPG_DATA_ROOT / "llm_audit_index"))
        else:
            c.bad(
                "audit ledger dir",
                f"{RPG_DATA_ROOT / 'llm_audit_index'} missing — is enable_llm_audit_ledger on?",
            )

        key = secret(plan.open_api.api_key_env, "astrbot_api_key")
        if not key:
            c.bad(
                "api key",
                f"set env {plan.open_api.api_key_env} or astrbot_api_key in data/rp_bench/secrets.yaml",
            )
        else:
            client = OpenApiClient(plan.open_api.base_url, key, timeout_s=120)
            try:
                configs = await client.list_configs()
                c.ok("open api /api/v1/configs", str(configs)[:160])
            except Exception as exc:
                c.bad(
                    "open api /api/v1/configs",
                    f"{type(exc).__name__}: {exc} (is AstrBot running at {plan.open_api.base_url}?)",
                )
            sid = f"rpb-probe-{uuid.uuid4().hex[:6]}"
            try:
                t0 = time.perf_counter()
                reply = await client.chat(
                    username=plan.open_api.username,
                    session_id=sid,
                    message="/rpg pipeline status",
                    config_id=plan.open_api.config_id,
                )
                if reply.text:
                    c.ok(
                        "/rpg command via open api",
                        f"{time.perf_counter() - t0:.1f}s: {reply.text[:120]!r}",
                    )
                else:
                    c.bad(
                        "/rpg command via open api",
                        f"empty reply; frames={[f.get('type') for f in reply.frames]}",
                    )
            except Exception as exc:
                c.bad("/rpg command via open api", f"{type(exc).__name__}: {exc}")
            umo = webchat_umo(plan.open_api.username, sid)
            rows = LedgerReader().index_rows(umo)
            c.ok(
                "ledger session key",
                f"{umo} → {len(rows)} narrator rows (0 is expected for a command-only probe)",
            )
        if any(a in plan.arms for a in RPG_ARMS):
            if secret("RPBENCH_DASH_USER", "dashboard_user"):
                c.ok("dashboard credentials", "per-session provider pin enabled")
            else:
                c.skip(
                    "dashboard credentials",
                    "not set; RPG narrator follows selected_provider only",
                )

    # 6. optional live calls
    if live_llm:
        for pid in plan.models:
            try:
                res = await provider_chat(
                    await pool.get(pid), prompt="只回复两个字：收到"
                )
                (c.ok if not res.error else c.bad)(
                    f"live {pid}",
                    res.error or f"{res.latency_s:.1f}s {res.text[:30]!r}",
                )
            except Exception as exc:
                c.bad(f"live {pid}", f"{type(exc).__name__}: {exc}")
        from .judge.runner import JudgeClient

        if not plan.judge.enabled:
            c.skip("live judge", "no judge configured (transcripts only)")
        else:
            try:
                res = await JudgeClient(plan.judge, pool).chat(
                    "你是评审。", '只输出 JSON：{"ok": true}'
                )
                (c.ok if not res.error else c.bad)(
                    f"live judge {plan.judge.judge_id}", res.error or res.text[:60]
                )
            except Exception as exc:
                c.bad(
                    f"live judge {plan.judge.judge_id}", f"{type(exc).__name__}: {exc}"
                )
    else:
        c.skip(
            "live LLM calls",
            "pass --live-llm to send one tiny request per model and the judge",
        )

    await pool.close()
    print(f"probe finished: {c.failed} failed check(s)")
    return 1 if c.failed else 0

"""Run the judge over transcripts: absolute scores + probes, and blind pairwise."""

from __future__ import annotations

from typing import Any

from ..config import JudgeSpec, secret
from ..providers import (
    ChatResult,
    EndpointChat,
    ProviderPool,
    model_family,
    provider_chat,
)
from .parse import JudgeParseError, extract_json_object, validate_abs, validate_pair
from .rubric import (
    DIMENSIONS,
    RUBRIC_VERSION,
    build_abs_system,
    build_abs_user,
    build_pair_system,
    build_pair_user,
    build_retry_note,
    render_pair_transcript,
    render_transcript,
)


class JudgeClient:
    def __init__(self, spec: JudgeSpec, pool: ProviderPool | None = None):
        self.spec = spec
        self.pool = pool
        self._endpoint: EndpointChat | None = None
        if not spec.provider_id:
            self._endpoint = EndpointChat(
                spec.endpoint_url,
                spec.endpoint_model,
                secret(spec.endpoint_api_key_env, "judge_api_key"),
                temperature=spec.temperature,
            )

    @property
    def judge_id(self) -> str:
        return self.spec.judge_id

    def family(self) -> str:
        if self.spec.provider_id and self.pool is not None:
            from ..providers import resolve_provider_config

            try:
                cfg = resolve_provider_config(
                    self.spec.provider_id, self.pool.cmd_config
                )
            except Exception:
                cfg = None
            return model_family(self.spec.provider_id, cfg)
        return model_family(self.spec.endpoint_model)

    async def chat(
        self, system: str, user: str, history: list[dict[str, Any]] | None = None
    ) -> ChatResult:
        if self._endpoint is not None:
            return await self._endpoint.chat(
                prompt=user, system_prompt=system, contexts=history
            )
        assert self.pool is not None
        provider = await self.pool.get(
            self.spec.provider_id, extra_body={"temperature": self.spec.temperature}
        )
        return await provider_chat(
            provider, prompt=user, system_prompt=system, contexts=history
        )


async def _ask_with_retry(
    client: JudgeClient, system: str, user: str, validate, max_retries: int
):
    """Call → parse → validate; on problems, send one feedback turn and retry."""
    history: list[dict[str, Any]] = []
    prompt = user
    attempts = 0
    usage = {"input": 0, "output": 0}
    last_error = ""
    result = None
    problems: list[str] = []
    for _ in range(max_retries + 1):
        attempts += 1
        res = await client.chat(system, prompt, history)
        for k in usage:
            usage[k] += int(res.usage.get(k, 0) or 0)
        if res.error:
            last_error = res.error
            continue
        try:
            obj = extract_json_object(res.text)
        except JudgeParseError as exc:
            last_error = str(exc)
            problems = ["输出不是合法 JSON"]
        else:
            result, problems = validate(obj)
            last_error = ""
            if not problems:
                break
        history = [
            *history,
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": res.text},
        ]
        prompt = build_retry_note(problems)
    return result, problems, attempts, usage, last_error


def scenario_meta(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("scenario_meta") or {}


async def judge_abs(
    client: JudgeClient, row: dict[str, Any], judge_sheet: str
) -> dict[str, Any]:
    meta = scenario_meta(row)
    dims = [d for d in meta.get("dimensions") or [] if d in DIMENSIONS]
    probes = meta.get("probes") or []
    turns = row.get("turns") or []
    replies = {t["turn_id"]: t.get("reply_clean") or "" for t in turns}
    system = build_abs_system(row.get("card_name", ""), dims, probes)
    user = build_abs_user(
        judge_sheet, meta.get("premise", ""), render_transcript(turns)
    )
    result, problems, attempts, usage, error = await _ask_with_retry(
        client,
        system,
        user,
        lambda obj: validate_abs(obj, dims, replies),
        client.spec.max_retries,
    )
    return {
        "cell_key": row["cell_key"],
        "judge_id": client.judge_id,
        "rubric_version": RUBRIC_VERSION,
        "arm": row["arm"],
        "card": row["card"],
        "scenario_id": row["scenario_id"],
        "model": row["model"],
        "repeat": row["repeat"],
        "dims": (result or {}).get("dims", {}),
        "probes": (result or {}).get("probes", []),
        "flags": (result or {}).get("flags", []),
        "unresolved": problems,
        "attempts": attempts,
        "usage": usage,
        "error": error if result is None else "",
    }


async def judge_pair(
    client: JudgeClient,
    row_x: dict[str, Any],
    row_y: dict[str, Any],
    judge_sheet: str,
    *,
    order: int,
    kind: str,
    label_x: str,
    label_y: str,
) -> dict[str, Any]:
    """order 1 shows X as A; order 2 shows X as B."""
    meta = scenario_meta(row_x)
    dims = [d for d in meta.get("dimensions") or [] if d in DIMENSIONS]
    a, b = (row_x, row_y) if order == 1 else (row_y, row_x)
    system = build_pair_system(row_x.get("card_name", ""), dims)
    user = build_pair_user(
        judge_sheet,
        meta.get("premise", ""),
        render_pair_transcript(a.get("turns") or [], b.get("turns") or []),
    )
    result, problems, attempts, usage, error = await _ask_with_retry(
        client,
        system,
        user,
        lambda obj: validate_pair(obj, dims),
        client.spec.max_retries,
    )
    return {
        "pair_key": f"{row_x['cell_key']}|{row_y['cell_key']}",
        "order": order,
        "kind": kind,
        "label_x": label_x,
        "label_y": label_y,
        "cell_x": row_x["cell_key"],
        "cell_y": row_y["cell_key"],
        "card": row_x["card"],
        "scenario_id": row_x["scenario_id"],
        "model": row_x["model"],
        "len_x": sum(len(t.get("reply_clean") or "") for t in row_x.get("turns") or []),
        "len_y": sum(len(t.get("reply_clean") or "") for t in row_y.get("turns") or []),
        "judge_id": client.judge_id,
        "rubric_version": RUBRIC_VERSION,
        "dims": (result or {}).get("dims", {}),
        "overall": (result or {}).get("overall", {}),
        "unresolved": problems,
        "attempts": attempts,
        "usage": usage,
        "error": error if result is None else "",
    }

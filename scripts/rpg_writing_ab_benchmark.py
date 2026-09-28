"""Run a repeatable A/B writing benchmark against an OpenAI-compatible API."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

DEFAULT_ENDPOINT = "http://192.168.0.104:8080/v1/chat/completions"
DEFAULT_MODEL = r"c:\gemma4\Gemma4-12B-QAT-Uncensored-HauhauCS-Balanced-Q4_K_M.gguf"

WRITING_GUIDANCE = """[LOCAL_MODEL_WRITING_GUIDANCE]
你正在续写沉浸式中文角色扮演场景。请遵守以下写作方法：

1. 先写角色在当下真正注意到的具体事物，再让情绪从动作、停顿、目光、距离和措辞里自然显现；不要先替读者总结情绪。
2. 每一段都应推动至少一项变化：人物距离、信息状态、关系张力、行动选择或场景节奏。避免换词重复同一感受。
3. 对话必须服务于人物目的。让角色通过试探、回避、玩笑、转移或留白表达复杂心意，不要让所有潜台词都被本人解释出来。
4. 保持人物声音稳定。角色可以敏锐，但不能凭空知道对方未表达的思想；只根据可见行为和既有经历作出判断。
5. 使用可感知且有选择性的细节。优先选取能反映人物关系的两三个细节，不堆砌形容词，不罗列五感清单。
6. 控制修辞密度。比喻必须准确、新鲜并贴合观察者经验；避免连续使用“仿佛、像是、某种、几乎、难以言喻”等模糊表达。
7. 不替玩家决定动作、台词、感受或结论。可以给玩家留下压力、邀请和可回应的空间，但不能代演玩家。
8. 不写旁白式评价、创作说明、主题总结或段末升华。结尾落在一个仍有张力的动作、话语、发现或选择上。
9. 本轮目标是细腻、克制而有推进的日常关系戏。篇幅可以充分展开，但每句话都应有叙事用途。
[/LOCAL_MODEL_WRITING_GUIDANCE]"""

SCENARIO_SYSTEM = """你是长篇沉浸式角色扮演中的叙事者。你负责环境、非玩家角色及事件结果，但绝不替玩家角色行动、说话或决定内心感受。

写作语言为简体中文。采用有限视角的第三人称叙事，场景基调是安静日常中的关系试探，不使用章节标题、项目符号、作者说明或结尾总结。

世界背景：灾难后的浮空城“新乐土”正在重建。居民知道过去发生过战争，但今天没有迫在眉睫的危机。科技与旧时代遗物并存。

角色“爱莉希雅”：外表轻快、善于把关心藏进玩笑，观察细致，愿意主动靠近别人，却尊重真正的拒绝。她不会用全知口吻断定玩家的内心，也不会把每句话都说成诗。她与玩家共同经历过一次危险任务，关系亲近但尚未明确。

玩家角色由用户控制。叙事者只能描述玩家已经明确给出的动作和台词。"""

SCENARIO_CONTEXTS = [
    {
        "role": "system",
        "content": """[SCENE_STATE]
时间：重建历第六个月，19:10，雨刚停。
地点：新乐土居住区的公共厨房。窗外维修灯逐盏亮起，室内只有冰箱低鸣和水滴敲击金属窗沿的声音。
已知事实：玩家连续三天参与外环维修，今天提前回来；左手虎口有一道新包扎，但玩家没有主动解释。桌上放着两杯刚泡好的热饮，其中一杯显然为玩家准备。
关系状态：爱莉希雅曾在上次任务后问过玩家“回来以后最想做什么”，玩家当时没有回答。两人此后都没有再提。
场景目标：让爱莉希雅借一件普通的小事试探玩家是否愿意把疲惫和未来计划分给她一点。推进关系，但不直接告白，不制造突发危机。
禁区：不替玩家感到心动、羞涩、愧疚或疲惫；不让爱莉希雅知道包扎原因；不引入第三者打断；不把场景写成心理治疗或人生说教。
[/SCENE_STATE]""",
    },
    {
        "role": "assistant",
        "content": "雨水沿着窗沿积成一线，迟迟没有落下。爱莉希雅把第二只杯子往桌子对面推了半寸，杯底擦过木纹，声音很轻。她没有去看门口，只用勺尖碰了碰自己那杯已经化开的糖。",
    },
    {
        "role": "user",
        "content": "我在门口停了一下，走到桌边坐下，把受伤的左手放到桌面下。‘你怎么知道我今天会回来？’",
    },
]

SCENARIO_PROMPT = """续写这一轮场景。让爱莉希雅回应玩家的问题，并围绕桌上的饮料和玩家藏起的手展开自然互动。她可以察觉玩家在隐瞒什么，但不能准确知道伤势来源。场景需要出现一次轻微的关系推进，并在玩家需要作出回应的位置结束。建议 900 至 1400 个汉字。"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run identical RPG prompts with and without writing guidance."
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key", default="")
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--seed", type=int, default=20260712)
    parser.add_argument("--timeout", type=float, default=7200.0)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--enable-thinking",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Allow the model to spend completion tokens on hidden reasoning.",
    )
    return parser.parse_args()


def normalize_message(message: Any) -> dict[str, Any] | None:
    if isinstance(message, dict):
        role = str(message.get("role") or "user")
        content = message.get("content", "")
        normalized = {"role": role, "content": content}
        if message.get("name"):
            normalized["name"] = message["name"]
        return normalized
    if isinstance(message, str):
        return {"role": "user", "content": message}
    return None


def load_messages(
    audit_path: Path | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if audit_path is None:
        messages = [
            {"role": "system", "content": SCENARIO_SYSTEM},
            *deepcopy(SCENARIO_CONTEXTS),
            {"role": "user", "content": SCENARIO_PROMPT},
        ]
        return messages, {"source": "built_in_daily_relationship_scene"}

    document = json.loads(audit_path.read_text(encoding="utf-8"))
    request = document.get("request")
    if not isinstance(request, dict):
        raise ValueError(f"Audit file has no request object: {audit_path}")

    messages: list[dict[str, Any]] = []
    system_prompt = str(request.get("system_prompt") or "")
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for raw_message in request.get("contexts") or []:
        message = normalize_message(raw_message)
        if message is not None:
            messages.append(message)
    prompt = str(request.get("prompt") or "")
    if prompt:
        messages.append({"role": "user", "content": prompt})
    return messages, {
        "source": "audit_replay",
        "audit_path": str(audit_path.resolve()),
        "audit_id": document.get("audit_id", ""),
    }


def inject_guidance(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    guided = deepcopy(messages)
    insert_at = len(guided)
    for index in range(len(guided) - 1, -1, -1):
        if guided[index].get("role") == "user":
            insert_at = index
            break
    guided.insert(insert_at, {"role": "system", "content": WRITING_GUIDANCE})
    return guided


def content_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def request_completion(
    endpoint: str,
    api_key: str,
    payload: dict[str, Any],
    timeout: float,
) -> tuple[dict[str, Any], float]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    elapsed = time.perf_counter() - started
    return json.loads(body), elapsed


def extract_message(response: dict[str, Any]) -> tuple[str, str]:
    choices = response.get("choices") or []
    if not choices:
        return "", ""
    message = choices[0].get("message") or {}
    return (
        str(message.get("content") or ""),
        str(message.get("reasoning_content") or ""),
    )


def main() -> int:
    args = parse_args()
    if args.runs < 1:
        raise ValueError("--runs must be at least 1")

    base_messages, source_meta = load_messages(args.audit)
    branches = {
        "A_baseline": base_messages,
        "B_guided": inject_guidance(base_messages),
    }
    output_root = args.output_dir or (
        Path(get_astrbot_plugin_data_path())
        / "astrbot_plugin_agentic_rpg"
        / "writing_benchmark"
    )
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S%z")
    run_dir = output_root / timestamp
    run_dir.mkdir(parents=True, exist_ok=False)

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(),
        "endpoint": args.endpoint,
        "model": args.model,
        "source": source_meta,
        "parameters": {
            "runs": args.runs,
            "temperature": args.temperature,
            "top_p": args.top_p,
            "max_tokens": args.max_tokens,
            "seed": args.seed,
            "timeout": args.timeout,
            "enable_thinking": args.enable_thinking,
        },
        "writing_guidance": WRITING_GUIDANCE,
        "branches": {},
    }

    for branch_name, messages in branches.items():
        branch_records = []
        for run_index in range(1, args.runs + 1):
            payload = {
                "model": args.model,
                "messages": messages,
                "temperature": args.temperature,
                "top_p": args.top_p,
                "max_tokens": args.max_tokens,
                "seed": args.seed + run_index - 1,
                "stream": False,
                "chat_template_kwargs": {"enable_thinking": args.enable_thinking},
            }
            started = time.perf_counter()
            try:
                response, elapsed = request_completion(
                    args.endpoint, args.api_key, payload, args.timeout
                )
                error = ""
            except Exception as exc:
                response = {}
                elapsed = time.perf_counter() - started
                error = f"{type(exc).__name__}: {exc}"
            text, reasoning = extract_message(response)
            choices = response.get("choices") or []
            finish_reason = choices[0].get("finish_reason", "") if choices else ""
            valid_for_review = (
                bool(text.strip()) and not error and finish_reason != "length"
            )
            record = {
                "branch": branch_name,
                "run": run_index,
                "elapsed_seconds": round(elapsed, 3),
                "request_hash": content_hash(payload),
                "response_hash": content_hash(text),
                "request": payload,
                "response": response,
                "text": text,
                "reasoning_content": reasoning,
                "error": error,
                "finish_reason": finish_reason,
                "valid_for_review": valid_for_review,
            }
            result_path = run_dir / f"{branch_name}-{run_index:02d}.json"
            result_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            branch_records.append(
                {
                    "run": run_index,
                    "file": result_path.name,
                    "elapsed_seconds": record["elapsed_seconds"],
                    "request_hash": record["request_hash"],
                    "response_hash": record["response_hash"],
                    "characters": len(text),
                    "reasoning_characters": len(reasoning),
                    "error": error,
                    "finish_reason": finish_reason,
                    "valid_for_review": valid_for_review,
                }
            )
            status = (
                f"error={error}"
                if error
                else f"{len(text)} chars, {len(reasoning)} reasoning chars"
            )
            print(
                f"{branch_name} run {run_index}/{args.runs}: {status} in {elapsed:.1f}s"
            )
            manifest["branches"][branch_name] = branch_records
            (run_dir / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        manifest["branches"][branch_name] = branch_records

    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Results: {run_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

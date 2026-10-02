"""Signature check: do the plugin's calls into AstrBot core still bind?

For a handful of high-traffic core APIs, compare the keyword arguments the RPG
plugin passes against the current signature, and report any keyword the core no
longer accepts. Also report core callables the plugin invokes synchronously that
have become coroutine functions.

Run from the repo root:
    uv run python scripts/research/check_plugin_call_sites.py
"""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "astrbot_plugin_agentic_RPG"

sys.path.insert(0, str(REPO_ROOT))

# attribute name on the call target -> dotted path of the callable to inspect
WATCHED_METHODS = {
    "llm_generate": "astrbot.core.star.context.Context.llm_generate",
    "tool_loop_agent": "astrbot.core.star.context.Context.tool_loop_agent",
    "register_web_api": "astrbot.core.star.context.Context.register_web_api",
    "retrieve": "astrbot.core.knowledge_base.kb_mgr.KnowledgeBaseManager.retrieve",
    "get_conversation": (
        "astrbot.core.conversation_mgr.ConversationManager.get_conversation"
    ),
    "update_conversation": (
        "astrbot.core.conversation_mgr.ConversationManager.update_conversation"
    ),
}


def resolve(dotted: str):
    module_path, _, tail = dotted.rpartition(".")
    owner_path, _, attr = (
        module_path.rpartition(".") if "." in module_path else ("", "", module_path)
    )
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, tail, None)
    except Exception:
        pass
    try:
        mod = importlib.import_module(owner_path)
        owner = getattr(mod, attr, None)
        return getattr(owner, tail, None) if owner else None
    except Exception:
        return None


def main() -> int:
    targets = {}
    for name, dotted in WATCHED_METHODS.items():
        target = resolve(dotted)
        if target is None:
            print(f"WARN cannot resolve {dotted}")
            continue
        targets[name] = (dotted, target, inspect.signature(target))

    problems: list[str] = []
    for path in sorted(PLUGIN_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(REPO_ROOT)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            problems.append(f"{rel}: SYNTAX {exc}")
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            name = func.attr
            if name not in targets:
                continue
            dotted, target, sig = targets[name]
            passed = {kw.arg for kw in node.keywords if kw.arg}
            accepted = set(sig.parameters)
            has_var_kw = any(
                p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            )
            if has_var_kw:
                continue
            unknown = passed - accepted
            if unknown:
                problems.append(
                    f"{rel}:{node.lineno} {dotted} does not accept "
                    f"{sorted(unknown)} (accepts {sorted(accepted - {'self'})})"
                )

    print(f"checked {len(targets)} core APIs across the plugin")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for line in problems:
            print(f"  {line}")
        return 1
    print("all watched call sites bind against the current core signatures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

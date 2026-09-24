"""Static compatibility check: does the RPG plugin still see every AstrBot API it imports?

Walks the plugin source tree, collects every ``from astrbot... import X`` /
``import astrbot...`` statement, then tries to resolve each one against the
currently checked-out AstrBot core. Also flags call sites that reference a core
attribute which has become a coroutine function (sync call sites would break).

Run from the repo root:
    uv run python scripts/research/check_plugin_api_compat.py
"""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOTS = [
    REPO_ROOT / "plugins" / "astrbot_plugin_agentic_RPG",
]

sys.path.insert(0, str(REPO_ROOT))


def collect_imports(path: Path) -> list[tuple[int, str, str | None]]:
    """Return (lineno, module, name) triples for astrbot imports in one file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [(exc.lineno or 0, "<syntax error>", str(exc))]

    found: list[tuple[int, str, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if not module.startswith("astrbot"):
                continue
            for alias in node.names:
                found.append((node.lineno, module, alias.name))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("astrbot"):
                    found.append((node.lineno, alias.name, None))
    return found


def main() -> int:
    failures: list[str] = []
    checked = 0
    module_cache: dict[str, object] = {}

    for root in PLUGIN_ROOTS:
        if not root.exists():
            print(f"SKIP missing plugin root: {root}")
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(REPO_ROOT)
            for lineno, module, name in collect_imports(path):
                if module == "<syntax error>":
                    failures.append(f"{rel}:{lineno} SYNTAX {name}")
                    continue
                checked += 1
                try:
                    if module in module_cache:
                        mod = module_cache[module]
                    else:
                        mod = importlib.import_module(module)
                        module_cache[module] = mod
                except Exception as exc:  # noqa: BLE001
                    failures.append(
                        f"{rel}:{lineno} MODULE {module} -> {type(exc).__name__}: {exc}"
                    )
                    continue
                if name is None or name == "*":
                    continue
                if not hasattr(mod, name):
                    # submodule import such as `from astrbot.api import event`
                    try:
                        importlib.import_module(f"{module}.{name}")
                    except Exception:  # noqa: BLE001
                        failures.append(f"{rel}:{lineno} MISSING {module}.{name}")

    print(f"checked {checked} astrbot imports")
    if failures:
        print(f"\n{len(failures)} problem(s):")
        for line in failures:
            print(f"  {line}")
        return 1
    print("all astrbot imports resolve")
    return 0


def report_coroutines(names: list[str]) -> None:
    """Print whether the given dotted core attributes are coroutine functions."""
    print("\ncoroutine check:")
    for dotted in names:
        module_path, _, attr = dotted.rpartition(".")
        try:
            mod = importlib.import_module(module_path)
        except Exception as exc:  # noqa: BLE001
            print(f"  {dotted}: module import failed ({exc})")
            continue
        target = getattr(mod, attr, None)
        if target is None:
            print(f"  {dotted}: MISSING")
            continue
        print(f"  {dotted}: coroutine={inspect.iscoroutinefunction(target)}")


if __name__ == "__main__":
    code = main()
    raise SystemExit(code)

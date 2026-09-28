"""Run directory with append-only JSONL stages, so any stage can resume."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

UTC8 = timezone(timedelta(hours=8))

TRANSCRIPTS = "transcripts.jsonl"
FAILURES = "failures.jsonl"
METRICS = "metrics.jsonl"
JUDGE_ABS = "judge_abs.jsonl"
JUDGE_PAIR = "judge_pair.jsonl"
MANIFEST = "manifest.json"
SUMMARY = "summary.json"
REPORT = "report.md"


def now_utc8() -> datetime:
    return datetime.now(UTC8)


def stamp_utc8() -> str:
    return now_utc8().strftime("%Y%m%d-%H%M%S")


class RunStore:
    def __init__(self, run_dir: Path | str):
        self.dir = Path(run_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @classmethod
    def create(cls, runs_root: Path, plan_name: str) -> RunStore:
        return cls(runs_root / f"{stamp_utc8()}+0800-{plan_name}")

    def path(self, name: str) -> Path:
        return self.dir / name

    def append(self, name: str, row: dict[str, Any]) -> None:
        line = json.dumps(row, ensure_ascii=False, default=str)
        with self._lock:
            with self.path(name).open("a", encoding="utf-8") as fp:
                fp.write(line + "\n")
                fp.flush()

    def read(self, name: str) -> list[dict[str, Any]]:
        path = self.path(name)
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                # A crash mid-write can leave one torn line; skip it and let
                # resume redo that record.
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def completed(self, name: str, key_field: str = "cell_key") -> set[str]:
        return {str(r.get(key_field)) for r in self.read(name) if r.get(key_field)}

    def write_json(self, name: str, data: Any) -> None:
        path = self.path(name)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        tmp.replace(path)

    def read_json(self, name: str) -> Any:
        path = self.path(name)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write_text(self, name: str, text: str) -> None:
        self.path(name).write_text(text, encoding="utf-8")

"""Count how many scored replies leak untagged English reasoning.

DeepSeek-flash sometimes emits its planning prose as ordinary text, with no
<think> markers for `normalize.clean_reply` to strip. Those turns reach the
player verbatim. This walks a run's transcripts.jsonl and reports, per session,
how many scored turns contain such a leak.

    uv run python scripts/research/count_cot_leaks.py <run_dir>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Planning prose in English is the signal. Chinese replies are the expected
# output, so a run of Latin-script sentences is what we look for.
LEAK_RE = re.compile(
    r"\b(?:As Firefly|The user (?:says|is|wants)|I should (?:respond|not|keep)|"
    r"Keep it|in character|Let me|She would|Maybe:|So she)\b"
)
# A reply is flagged only when it also carries a meaningful run of ASCII prose,
# so an isolated English loan word does not trip it.
ASCII_RUN_RE = re.compile(r"[A-Za-z][A-Za-z ,.'\"\-]{40,}")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: count_cot_leaks.py <run_dir>")
        return 1
    run_dir = Path(sys.argv[1])
    path = run_dir / "transcripts.jsonl"
    if not path.exists():
        print(f"missing {path}")
        return 1

    per_session: dict[str, dict[str, object]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = "{}/{}/{}/{}/r{}".format(
            row.get("card", ""),
            row.get("scenario_id", ""),
            row.get("arm", ""),
            row.get("model", ""),
            row.get("repeat", ""),
        )
        bucket = per_session.setdefault(key, {"turns": 0, "leaks": 0, "ids": []})
        for turn in row.get("turns") or []:
            bucket["turns"] = int(bucket["turns"]) + 1
            # reply_clean is what a player would see after the bench strips
            # tagged reasoning; an untagged leak survives into it.
            text = str(turn.get("reply_clean") or turn.get("reply_raw") or "")
            if LEAK_RE.search(text) and ASCII_RUN_RE.search(text):
                bucket["leaks"] = int(bucket["leaks"]) + 1
                ids = bucket["ids"]
                assert isinstance(ids, list)
                ids.append(turn.get("turn_id"))

    total_turns = sum(int(v["turns"]) for v in per_session.values())
    total_leaks = sum(int(v["leaks"]) for v in per_session.values())
    for key, v in sorted(per_session.items()):
        print(f"{key}: {v['leaks']}/{v['turns']} turns leaked {v['ids']}")
    rate = (total_leaks / total_turns * 100) if total_turns else 0.0
    print(f"\ntotal: {total_leaks}/{total_turns} scored turns ({rate:.0f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

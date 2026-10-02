"""Count voice-fingerprint markers in rp_bench session files, replies only.

Reasoning traces (inside <details>思考过程</details>) are excluded — the model's
English planning notes mention "人家"/"伙伴"/"♪" as *instructions to itself* and
would inflate every count.

    uv run python -m scripts.research.cyrene_marker_audit <run_dir>
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

DETAILS = re.compile(r"<details>.*?</details>", re.S)
REPLY = re.compile(r"\*\*回应\*\*[^\n]*\n(.*?)(?=\n## t|\Z)", re.S)

MARKERS = {
    "人家": "人家",
    "伙伴": "伙伴",
    "音符♪": "♪",
    "涟漪": "涟漪",
    "流星": "流星",
    "故事": "故事",
    "明天": "明天",
    "月光": "月光",
    "重逢": "重逢",
}


def load_replies(path: Path) -> list[str]:
    text = DETAILS.sub("", path.read_text(encoding="utf-8"))
    return [m.strip() for m in REPLY.findall(text) if m.strip()]


def main() -> None:
    run_dir = Path(sys.argv[1])
    sessions = run_dir / "sessions"
    stats: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    turns: dict[tuple[str, str], int] = defaultdict(int)

    for path in sorted(sessions.rglob("*__r0.md")):
        parts = path.name[: -len("__r0.md")].split("__")
        arm, model = parts[0], parts[1].replace("_", "/", 1)
        label = f"{arm}|{model.split('/')[-1]}"
        scenario = path.parent.name
        replies = load_replies(path)
        key = (label, scenario)
        turns[key] = len(replies)
        for reply in replies:
            for name, needle in MARKERS.items():
                if needle in reply:
                    stats[key][name] += reply.count(needle)

    print(
        f"{'组·模型':<26} {'剧本':<20} {'轮':>3}  "
        + "  ".join(f"{m:>6}" for m in MARKERS)
    )
    for key in sorted(turns):
        row = stats[key]
        cells = "  ".join(f"{row.get(m, 0):>6}" for m in MARKERS)
        print(f"{key[0]:<26} {key[1]:<20} {turns[key]:>3}  {cells}")

    print("\n合计（每档 30 轮）")
    for label in sorted({k[0] for k in turns}):
        row: dict[str, int] = defaultdict(int)
        for (lab, _), counts in stats.items():
            if lab == label:
                for k, v in counts.items():
                    row[k] += v
        cells = "  ".join(f"{row.get(m, 0):>6}" for m in MARKERS)
        print(f"{label:<26} {'':<20} {'':>3}  {cells}")

    audit_metrics(run_dir)


def audit_metrics(run_dir: Path) -> None:
    """Flagged turns + address-term counts straight from metrics.jsonl."""
    import json

    path = run_dir / "metrics.jsonl"
    if not path.exists():
        return
    print("\n逐会话标记（来自 metrics.jsonl）")
    header = (
        f"{'组':<6} {'模型':<24} {'剧本':<20} {'伙伴':>4} {'自称违规':>7} "
        f"{'出戏':>4} {'越权':>4} {'留钩子':>5} {'篇幅':>6}"
    )
    print(header)
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        t = row["text"]
        partner = 0
        for turn in row.get("per_turn") or []:
            partner += (turn.get("call_counts") or {}).get("伙伴", 0)
        print(
            f"{row['arm']:<6} {row['model'].split('/')[-1]:<24} "
            f"{row['scenario_id']:<20} {partner:>4} "
            f"{t['self_forbidden_hits']:>7} {t['ooc_hits']:>4} "
            f"{t['agency_hits']:>4} {t['open_ending_rate']:>5.0%} "
            f"{t['len_mean']:>6.1f}"
        )

    print("\n越权/出戏 具体轮次")
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        for i, turn in enumerate(row.get("per_turn") or [], 1):
            flags = []
            if turn.get("agency_hits"):
                flags.append(f"越权={turn['agency_hits']}")
            if turn.get("ooc_hits"):
                flags.append(f"出戏={turn['ooc_hits']}")
            if turn.get("never_say_hits"):
                flags.append(f"never_say={turn['never_say_hits']}")
            if flags:
                print(
                    f"  {row['arm']}/{row['model'].split('/')[-1]}"
                    f"/{row['scenario_id']}/t{i:02d}: " + " ".join(flags)
                )


if __name__ == "__main__":
    main()

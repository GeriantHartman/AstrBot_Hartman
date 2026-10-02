"""Task 2c: owner-only (unpolluted) trigger analysis."""

import glob
import json
import os
import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone

DATA = r"E:\agentic-rpg\AstrBot\data\plugin_data\astrbot_plugin_agentic_rpg"
AUD = os.path.join(DATA, "llm_audit_index")
CST = timezone(timedelta(hours=8))
# sessions where owner is the ONLY player (unpolluted)
OWNER_ONLY = {
    "default:FriendMessage:245432630",
    "default:GroupMessage:1090658701",
    "default:GroupMessage:1098307480",
    "default:GroupMessage:289584858",
    "default:GroupMessage:529384034",
    "default:GroupMessage:702510574",
    "default:GroupMessage:814560566",
}
SHARED = {
    "default:GroupMessage:1097436019",
    "default:GroupMessage:218606013",
    "default:GroupMessage:230394566",
    "default:GroupMessage:909871205",
    "default:GroupMessage:966162158",
}

recs = {}
for f in glob.glob(os.path.join(AUD, "*.jsonl")):
    for line in open(f, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except BaseException:
            continue
        if r.get("audit_id"):
            recs[r["audit_id"]] = r
rows = [r for r in recs.values() if r.get("session_id", "").startswith("default")]


def stats(rs, label):
    ts = sorted(x["created_at"] for x in rs if x.get("created_at"))
    iv = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
    days = sorted({datetime.fromtimestamp(t, CST).date() for t in ts})
    print(f"\n--- {label} ---  records={len(rs)} days={len(days)}")
    if days:
        print(f"    date range {days[0]} .. {days[-1]}")
    if iv:
        ivs = sorted(iv)

        def q(p):
            """Read an interval quantile using the report's existing index rule.

            Args:
                p: Quantile fraction.

            Returns:
                The selected interval duration.
            """
            return ivs[min(len(ivs) - 1, int(p * len(ivs)))]

        print(
            f"    interval med={statistics.median(iv):.0f}s p90={q(0.9):.0f}s max={ivs[-1]:.0f}s  <30s={sum(1 for x in iv if x < 30)}  >1h={sum(1 for x in iv if x > 3600)}"
        )
    # weekly
    wk = Counter()
    for t in ts:
        d = datetime.fromtimestamp(t, CST)
        wk[f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"] += 1
    print("    weekly turns:", dict(sorted(wk.items())))
    return ts


o_ts = stats(
    [r for r in rows if r["session_id"] in OWNER_ONLY], "OWNER-ONLY sessions (7)"
)
s_ts = stats(
    [r for r in rows if r["session_id"] in SHARED], "SHARED sessions (5, both players)"
)

# owner-only burst analysis
print("\n=== OWNER-ONLY burst (GAP>1800s) ===")
by = {}
for r in rows:
    if r["session_id"] in OWNER_ONLY:
        by.setdefault(r["session_id"], []).append(r["created_at"])
bursts = []
for sid, ts in by.items():
    ts = sorted(ts)
    start = ts[0]
    prev = ts[0]
    n = 1
    for t in ts[1:]:
        if t - prev > 1800:
            bursts.append((sid, start, prev, n))
            start = t
            n = 1
        else:
            n += 1
        prev = t
    bursts.append((sid, start, prev, n))
hc = Counter(datetime.fromtimestamp(b, CST).hour for _, b, _, _ in bursts)
print(
    "  bursts:", len(bursts), " median turns:", statistics.median(n for *_, n in bursts)
)
print("  burst-start hour (CST):", dict(sorted(hc.items())))
# night share
night = sum(c for h, c in hc.items() if h in (22, 23, 0, 1, 2, 3, 4))
print(
    f"  night(22-04) burst starts: {night}/{len(bursts)} = {night / len(bursts) * 100:.1f}%"
)

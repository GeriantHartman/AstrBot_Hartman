"""Task 2b: trigger (Fogg 'Prompt') proxies from per-turn audit timestamps."""

import glob
import json
import os
import statistics
from datetime import datetime, timedelta, timezone

DATA = r"E:\agentic-rpg\AstrBot\data\plugin_data\astrbot_plugin_agentic_rpg"
AUD = os.path.join(DATA, "llm_audit_index")
CST = timezone(timedelta(hours=8))
OWNER = "245432630"

# collect all audit records, dedup by audit_id
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
        aid = r.get("audit_id")
        if aid:
            recs[aid] = r

rows = [r for r in recs.values() if r.get("session_id", "").startswith("default")]
print("unique audit records (default):", len(rows))


def sess_of(sid):
    p = sid.split(":")
    return p[2] if len(p) > 2 else sid


by_sess = {}
for r in rows:
    by_sess.setdefault(r["session_id"], []).append(r)

# owner sessions = sessions where owner is a player (from DB scan)
OWNER_SESS = {
    "default:FriendMessage:245432630",
    "default:GroupMessage:1090658701",
    "default:GroupMessage:1097436019",
    "default:GroupMessage:1098307480",
    "default:GroupMessage:218606013",
    "default:GroupMessage:230394566",
    "default:GroupMessage:289584858",
    "default:GroupMessage:529384034",
    "default:GroupMessage:702510574",
    "default:GroupMessage:814560566",
    "default:GroupMessage:909871205",
    "default:GroupMessage:966162158",
}
print("owner sessions in audit:", sorted(OWNER_SESS & set(by_sess)))


# ---- inter-turn intervals ----
def intervals(rs):
    ts = sorted(x["created_at"] for x in rs if x.get("created_at"))
    return [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]


allint = intervals(rows)
ownint = intervals([r for r in rows if r["session_id"] in OWNER_SESS])


def desc(a, label):
    if not a:
        print(label, "no data")
        return
    a = sorted(a)

    def q(p):
        """Read a quantile using the report's existing index rule.

        Args:
            p: Quantile fraction.

        Returns:
            The selected interval duration.
        """
        return a[min(len(a) - 1, int(p * len(a)))]

    print(
        f"  {label:22s} n={len(a):5d} min={a[0]:6.0f} p10={q(0.10):6.0f} p25={q(0.25):6.0f} med={statistics.median(a):7.0f} p75={q(0.75):7.0f} p90={q(0.90):7.0f} max={a[-1]:8.0f}"
    )


print("\n=== INTER-TURN INTERVALS (sec) [audit] ===")
desc(allint, "all sessions")
desc(ownint, "owner sessions")

# ---- burst / session-start analysis ----
# define a "burst" = consecutive turns with gap<=GAP; burst start = first turn
for GAP in (300, 600, 1800):
    bursts = []
    for sid, rs in by_sess.items():
        ts = sorted(x["created_at"] for x in rs if x.get("created_at"))
        if not ts:
            continue
        start = ts[0]
        prev = ts[0]
        n = 1
        for t in ts[1:]:
            if t - prev > GAP:
                bursts.append((sid, start, prev, n))
                start = t
                n = 1
            else:
                n += 1
            prev = t
        bursts.append((sid, start, prev, n))
    print(f"\n=== GAP>{GAP}s splits into {len(bursts)} bursts ===")
    # hour-of-day of burst starts
    from collections import Counter

    hc = Counter(datetime.fromtimestamp(b, CST).hour for _, b, _, _ in bursts)
    print("  burst-start hour histogram (CST):", dict(sorted(hc.items())))
    # burst durations
    durs = sorted(e - b for _, b, e, _ in bursts)
    print(f"  burst duration sec: med={statistics.median(durs):.0f} max={durs[-1]:.0f}")
    # burst turn counts
    tn = sorted(n for *_, n in bursts)
    print(
        f"  burst turns: med={statistics.median(tn):.0f} max={tn[-1]} mean={statistics.mean(tn):.1f}"
    )
    # owner-only bursts
    ob = []
    for sid, rs in by_sess.items():
        if sid not in OWNER_SESS:
            continue
        ts = sorted(x["created_at"] for x in rs if x.get("created_at"))
        if not ts:
            continue
        start = ts[0]
        prev = ts[0]
        n = 1
        for t in ts[1:]:
            if t - prev > GAP:
                ob.append((sid, start, prev, n))
                start = t
                n = 1
            else:
                n += 1
            prev = t
        ob.append((sid, start, prev, n))
    ohc = Counter(datetime.fromtimestamp(b, CST).hour for _, b, _, _ in ob)
    otd = sorted(n for *_, n in ob)
    print(
        f"  [OWNER] bursts={len(ob)} burst-start hour (CST):", dict(sorted(ohc.items()))
    )
    print(
        f"  [OWNER] burst turns: med={statistics.median(otd):.0f} max={otd[-1]} mean={statistics.mean(otd):.1f}"
    )

# ---- active days & gaps between active days ----
allday = sorted(
    {
        datetime.fromtimestamp(r["created_at"], CST).date()
        for r in rows
        if r.get("created_at")
    }
)
print("\n=== ACTIVE DAYS ===")
print(
    "  first:", allday[0], " last:", allday[-1], " distinct active days:", len(allday)
)
gaps = [(allday[i + 1] - allday[i]).days for i in range(len(allday) - 1)]
if gaps:
    print(
        f"  day-gap between consecutive active days: med={statistics.median(gaps)} mean={statistics.mean(gaps):.1f} max={max(gaps)}"
    )
    print(
        "  gaps>=7d count:",
        sum(1 for g in gaps if g >= 7),
        " >=14d:",
        sum(1 for g in gaps if g >= 14),
    )

# owner active days
od = sorted(
    {
        datetime.fromtimestamp(r["created_at"], CST).date()
        for r in rows
        if r["session_id"] in OWNER_SESS and r.get("created_at")
    }
)
print("\n=== OWNER ACTIVE DAYS ===")
print("  first:", od[0], " last:", od[-1], " distinct:", len(od))
og = [(od[i + 1] - od[i]).days for i in range(len(od) - 1)]
if og:
    print(
        f"  day-gap: med={statistics.median(og)} mean={statistics.mean(og):.1f} max={max(og)}; >=7d:{sum(1 for g in og if g >= 7)}"
    )

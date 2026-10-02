"""Task 3b: affinity stage thresholds + who reaches max & how fast."""

import glob
import json
import os
import sqlite3
import statistics
from collections import Counter, defaultdict

DATA = r"E:\agentic-rpg\AstrBot\data\plugin_data\astrbot_plugin_agentic_rpg"
rows = []
for f in sorted(glob.glob(os.path.join(DATA, "world_*.db"))):
    con = sqlite3.connect(f)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    b = os.path.basename(f)[:-3][len("world_") :]
    p = b.split("_")
    sid = p[0] + ":" + p[1] + ":" + "_".join(p[2:])
    try:
        cur.execute(
            "SELECT npc_entity_id,player_entity_id,value,stage,history FROM npc_player_affinity"
        )
        for r in cur.fetchall():
            rows.append(
                {
                    "sid": sid,
                    "npc": r["npc_entity_id"],
                    "pl": r["player_entity_id"],
                    "value": r["value"],
                    "stage": r["stage"],
                    "history": r["history"],
                }
            )
    except BaseException:
        pass
    con.close()


def hlen(h):
    if h is None:
        return 0
    if isinstance(h, str):
        try:
            return len(json.loads(h))
        except BaseException:
            return len([x for x in h.split(";") if x]) if h else 0
    return len(h)


# value vs stage cross-tab
ct = defaultdict(list)
for r in rows:
    ct[r["stage"]].append(r["value"])
print("=== value by stage ===")
for st in sorted(ct, key=lambda s: -statistics.mean(ct[s])):
    vs = ct[st]
    print(
        f"  {st:6s} n={len(vs):3d} min={min(vs):4d} max={max(vs):4d} mean={statistics.mean(vs):6.1f}"
    )

print(f"\n=== rows at value==100 (n={sum(1 for r in rows if r['value'] == 100):d}) ===")
maxr = [r for r in rows if r["value"] == 100]
print("  stages:", Counter(r["stage"] for r in maxr).most_common())
print("  history-len:", Counter(hlen(r["history"]) for r in maxr).most_common())
print("  players:", Counter(r["pl"] for r in maxr).most_common())

print(f"\n=== rows at value<=0 (n={sum(1 for r in rows if r['value'] <= 0):d}) ===")
negr = [r for r in rows if r["value"] <= 0]
for r in negr:
    print(
        "   ",
        r["sid"],
        r["npc"],
        r["pl"],
        "val=",
        r["value"],
        "stage=",
        r["stage"],
        "hlen=",
        hlen(r["history"]),
    )

print(
    f"\n=== 陌生 rows (n={sum(1 for r in rows if r['stage'] == '陌生'):d}) value distribution ==="
)
stg = [r for r in rows if r["stage"] == "陌生"]
print("  values:", sorted(r["value"] for r in stg))
print("  ==0:", sum(1 for r in stg if r["value"] == 0))

print("\n=== history length overall ===")
hl = [hlen(r["history"]) for r in rows]
print(
    "  n",
    len(hl),
    "median",
    statistics.median(hl),
    "mean",
    round(statistics.mean(hl), 1),
    "max",
    max(hl),
)
print(
    "  hlen<=2:",
    sum(1 for x in hl if x <= 2),
    " hlen>=10:",
    sum(1 for x in hl if x >= 10),
)

# how many distinct npc-player pairs per session reach 100
print("\n=== per-session affinity summary ===")
bys = defaultdict(list)
for r in rows:
    bys[r["sid"]].append(r)
for sid, rs in sorted(bys.items()):
    n100 = sum(1 for r in rs if r["value"] == 100)
    print(
        f"  {sid:40s} n={len(rs):3d} at100={n100:2d} stages={dict(Counter(r['stage'] for r in rs))}"
    )

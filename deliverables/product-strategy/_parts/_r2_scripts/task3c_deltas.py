"""Task 3c: affinity history delta analysis — quantify 'jump to max' behavior."""

import glob
import json
import os
import sqlite3
import statistics
from collections import Counter

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
            try:
                h = json.loads(r["history"]) if r["history"] else []
            except BaseException:
                h = []
            rows.append({"sid": sid, "value": r["value"], "stage": r["stage"], "h": h})
    except BaseException:
        pass
    con.close()

# delta magnitude distribution
alld = [e.get("delta", 0) for r in rows for e in r["h"] if isinstance(e, dict)]
print("total affinity-change events (deltas):", len(alld))
pos = [d for d in alld if d > 0]
neg = [d for d in alld if d < 0]
zero = [d for d in alld if d == 0]
print(
    f"  positive: {len(pos)} ({len(pos) / len(alld) * 100:.1f}%)  negative: {len(neg)} ({len(neg) / len(alld) * 100:.1f}%)  zero: {len(zero)}"
)
print(
    f"  positive delta: med={statistics.median(pos):.0f} mean={statistics.mean(pos):.1f} max={max(pos)}"
)
print("  delta histogram:")
dh = Counter()
for d in alld:
    if d >= 50:
        dh[">=50"] += 1
    elif d >= 20:
        dh["20-49"] += 1
    elif d >= 10:
        dh["10-19"] += 1
    elif d >= 5:
        dh["5-9"] += 1
    elif d > 0:
        dh["1-4"] += 1
    elif d == 0:
        dh["0"] += 1
    else:
        dh["<0"] += 1
for k in [">=50", "20-49", "10-19", "5-9", "1-4", "0", "<0"]:
    print(f"    {k:6s}: {dh[k]}")

# per-row max single delta
print("\n=== rows reaching value==100 ===")
maxr = [r for r in rows if r["value"] == 100]
bigjump = [r for r in maxr if any(e.get("delta", 0) >= 50 for e in r["h"])]
print(
    f"  n={len(maxr)}; reached via single delta>=50: {len(bigjump)} ({len(bigjump) / len(maxr) * 100:.0f}%)"
)
print(
    "  their reasons:",
    [e["reason"] for r in bigjump for e in r["h"] if e.get("delta", 0) >= 50],
)

# how many rows have ANY delta>=50
anybig = [r for r in rows if any(e.get("delta", 0) >= 50 for e in r["h"])]
print(
    f"\nrows with any delta>=50: {len(anybig)}/{len(rows)} ({len(anybig) / len(rows) * 100:.0f}%)"
)
print("  their values:", sorted(r["value"] for r in anybig))

# per-row max delta stats
permax = [max((e.get("delta", 0) for e in r["h"]), default=0) for r in rows]
print(
    "\nper-row max single delta: med",
    statistics.median(permax),
    "mean",
    round(statistics.mean(permax), 1),
)

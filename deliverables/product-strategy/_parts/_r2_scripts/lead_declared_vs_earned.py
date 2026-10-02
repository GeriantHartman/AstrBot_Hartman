"""Hypothesis: relationships sitting at exactly 100 were DECLARED
(session canon / initial state), not EARNED (process state).

If true: relationship is set at the start, then nothing ever moves it
-> that is the real shape of C6, not "diode".
"""

import glob
import json
import os
import re
import sqlite3
from collections import Counter

DATA = r"E:\agentic-rpg\AstrBot\data\plugin_data\astrbot_plugin_agentic_rpg"
DECL_PAT = re.compile(
    r"设定|前世|宿命|羁绊|契约|无限|∞|基础|初始|本命|天赋|系统精灵|修正至"
)

fs = sorted(glob.glob(os.path.join(DATA, "world_*.db")))
print("files", len(fs), flush=True)

rows = []
for f in fs:
    b = os.path.basename(f)[:-3]
    p = b.split("_")
    sid = p[0] + ":" + p[1] + ":" + "_".join(p[2:])
    con = sqlite3.connect(f)
    cur = con.cursor()
    try:
        cur.execute("SELECT interaction_count FROM game_sessions")
        r = cur.fetchone()
    except Exception as e:
        print("GS QUERY FAIL", os.path.basename(f), repr(e), flush=True)
        r = None
    if not r or not r[0]:
        if r is None:
            print("SKIP none", os.path.basename(f), flush=True)
        con.close()
        continue
    ic = r[0]

    try:
        cur.execute("SELECT world_preset FROM game_sessions")
        preset = cur.fetchone()[0]
    except Exception:
        preset = "?"

    try:
        cur.execute("SELECT COUNT(*) FROM world_canon WHERE source='player_declared'")
        decl = cur.fetchone()[0]
    except Exception:
        decl = 0

    try:
        cur.execute(
            "SELECT npc_entity_id, value, stage, history, player_entity_id FROM npc_player_affinity"
        )
        aff = cur.fetchall()
    except Exception as e:
        print("AFF QUERY FAIL", os.path.basename(f), repr(e), flush=True)
        aff = []
    if not aff:
        print("AFF EMPTY", os.path.basename(f), "ic=", ic, flush=True)
    con.close()

    for rec in aff:
        npc, val, stage, hist = rec[0], rec[1], rec[2], rec[3]
        try:
            h = json.loads(hist) if hist else []
        except Exception:
            h = []
        if not isinstance(h, list):
            h = []
        reasons = " ".join(str(x.get("reason", "")) for x in h if isinstance(x, dict))
        rows.append(
            {
                "sid": sid,
                "ic": ic,
                "preset": preset,
                "decl": decl,
                "npc": npc,
                "val": val,
                "stage": stage,
                "n_hist": len(h),
                "declared": bool(DECL_PAT.search(reasons)),
            }
        )

n = len(rows)
print("sessions with ic>0:", len({r["sid"] for r in rows}))
print("total affinity rows:", n, flush=True)
at100 = [r for r in rows if r["val"] == 100]
print(f"value==100: {len(at100):d} ({100 * len(at100) / max(1, n):.1f}%)")
print()

d_all = sum(1 for r in rows if r["declared"])
d_100 = sum(1 for r in at100 if r["declared"])
print(
    f"history contains DECLARATION language: {d_all:d}/{n:d} = {100 * d_all / max(1, n):.1f}%"
)
print(
    f"  of the value==100 rows              : {d_100:d}/{len(at100):d} = {100 * d_100 / max(1, len(at100)):.1f}%"
)
print()


def med(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else 0


print(
    f"history length median: declared={med([r['n_hist'] for r in rows if r['declared']]):d}  "
    f"earned={med([r['n_hist'] for r in rows if not r['declared']]):d}"
)
print()
print("stage dist DECLARED:", dict(Counter(r["stage"] for r in rows if r["declared"])))
print(
    "stage dist EARNED  :", dict(Counter(r["stage"] for r in rows if not r["declared"]))
)
print()
print(f"{'session':<38} {'ic':>5} {'decl':>6} {'aff@100':>8}")
seen = []
for r in rows:
    if r["sid"] not in seen:
        seen.append(r["sid"])
for sid in sorted(seen, key=lambda s: -max(r["ic"] for r in rows if r["sid"] == s)):
    ss = [r for r in rows if r["sid"] == sid]
    print(
        f"{sid[:38]:<38} {int(ss[0]['ic']):5d} {int(ss[0]['decl']):6d} "
        f"{sum(1 for r in ss if r['val'] == 100):8d}"
    )

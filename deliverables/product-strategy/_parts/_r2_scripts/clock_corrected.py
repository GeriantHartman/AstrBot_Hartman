"""Corrected clock metric: player's CURRENT zone (L4) vs player's CURRENT scene (L1) vs L3."""

import glob
import os
import sqlite3

DATA = r"E:\agentic-rpg\AstrBot\data\plugin_data\astrbot_plugin_agentic_rpg"
OUT = r"E:\agentic-rpg\AstrBot\deliverables\product-strategy\_parts\_r2_scripts\clock_corrected.txt"
L = []


def p(*a):
    L.append(" ".join(str(x) for x in a))


n = 0
m_l1 = 0
m_l3 = 0
rows = []
allz = 0
allz_l1 = 0
allz_l3 = 0
for f in sorted(glob.glob(os.path.join(DATA, "world_*.db"))):
    con = sqlite3.connect(f)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    b = os.path.basename(f)[:-3][len("world_") :]
    q = b.split("_")
    sid = q[0] + ":" + q[1] + ":" + "_".join(q[2:])
    cur.execute("SELECT COUNT(*) FROM game_sessions")
    if cur.fetchone()[0] == 0:
        con.close()
        continue
    cur.execute("SELECT current_time_slice FROM game_sessions")
    L3 = cur.fetchone()[0]
    cur.execute("SELECT scene_id,local_id,time_slice,is_active FROM scenes")
    scenes = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT scene_id,entity_id FROM scene_members")
    sm = {}
    for r in cur.fetchall():
        sm.setdefault(r["entity_id"], []).append(r["scene_id"])
    cur.execute("SELECT local_id,location_name,time_slice FROM zones")
    zones = {r["local_id"]: dict(r) for r in cur.fetchall()}
    cur.execute(
        "SELECT entity_id,user_id,name,current_local_id FROM characters WHERE is_player=1"
    )
    for c in cur.fetchall():
        c = dict(c)
        scs = [s for s in scenes if s["scene_id"] in sm.get(c["entity_id"], [])]
        act = [s for s in scs if s["is_active"]]
        L1 = act[0]["time_slice"] if act else (scs[-1]["time_slice"] if scs else "")
        z = zones.get(c["current_local_id"])
        L4 = z["time_slice"] if z else None
        zn = z["location_name"] if z else None
        if L4 is None:
            continue
        n += 1
        ok1 = L1 == L4
        ok3 = L3 == L4
        m_l1 += ok1
        m_l3 += ok3
        rows.append((sid, c["user_id"], c["name"], zn, L4, L1, L3, ok1, ok3))
    # all-zones baseline
    for z in zones.values():
        allz += 1
        allz_l1 += z["time_slice"] == L1 if False else 0
    con.close()

p("CORRECTED CLOCK METRIC — player's CURRENT zone vs CURRENT scene (L1) vs legacy L3")
p("=" * 90)
p(
    f"{'session':38s} {'uid':10s} {'name':14s} {'current zone':22s} {'L4':5s} {'L1':5s} {'L3':5s} L4==L1 L4==L3"
)
for r in rows:
    p(
        f"{r[0]:38s} {r[1]:10s} {str(r[2]):14s} {str(r[3]):22s} {str(r[4]):5s} {str(r[5]):5s} {str(r[6]):5s}  {'Y' if r[7] else 'n'}     {'Y' if r[8] else 'n'}"
    )
p("=" * 90)
p(f"player-observations n={n}")
p(
    f"  L4==L1 (current zone == player scene clock) : {m_l1}/{n} = {m_l1 / n * 100:.1f}%   <-- CORRECTED"
)
p(
    f"  L4==L3 (current zone == legacy current_time_slice): {m_l3}/{n} = {m_l3 / n * 100:.1f}%"
)

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(L))
print("ok")

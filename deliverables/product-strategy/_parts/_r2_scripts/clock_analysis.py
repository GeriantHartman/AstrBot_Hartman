"""Clock-baseline re-measurement. Writes report to clock_report.txt (stdout is unreliable)."""

import glob
import os
import sqlite3

DATA = r"E:\agentic-rpg\AstrBot\data\plugin_data\astrbot_plugin_agentic_rpg"
OUT = r"E:\agentic-rpg\AstrBot\deliverables\product-strategy\_parts\_r2_scripts\clock_report.txt"
L = []


def p(*a):
    L.append(" ".join(str(x) for x in a))


p("CLOCK BASELINE RE-MEASUREMENT")
p("L1 = scenes.time_slice (active scene, player-authoritative per code 3630)")
p("L3 = game_sessions.current_time_slice (legacy, advance_scene_time NEVER writes it)")
p("L4 = zones.time_slice")
p("=" * 78)

tot_zones = 0
m_L3 = 0
m_L1 = 0
sess_div = 0
sess_tot = 0
per = []
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
    cur.execute(
        "SELECT current_time_slice,time_slice_index,max_time_slice,max_time_index FROM game_sessions"
    )
    g = dict(cur.fetchone())
    L3 = g["current_time_slice"]
    cur.execute("SELECT time_slice,time_slice_index,is_active FROM scenes")
    sc = [dict(r) for r in cur.fetchall()]
    act = [s for s in sc if s["is_active"]]
    L1 = act[0]["time_slice"] if act else (sc[-1]["time_slice"] if sc else "")
    cur.execute("SELECT local_id,location_name,time_slice FROM zones")
    zs = [dict(r) for r in cur.fetchall()]
    # player's own zone via characters.current_local_id
    cur.execute(
        "SELECT entity_id,user_id,name,current_local_id FROM characters WHERE is_player=1"
    )
    chars = [dict(r) for r in cur.fetchall()]
    zc_L3 = sum(1 for z in zs if z["time_slice"] == L3)
    zc_L1 = sum(1 for z in zs if z["time_slice"] == L1)
    tot_zones += len(zs)
    m_L3 += zc_L3
    m_L1 += zc_L1
    sess_tot += 1
    if L1 != L3:
        sess_div += 1
    p(f"\n{sid}")
    p(
        f"  L1(active scene)={L1!r}  L3(current_time_slice)={L3!r}  max_slice={g['max_time_slice']!r}  L1==L3? {L1 == L3}"
    )
    p(
        f"  scenes(n={len(sc)}, active={len(act)}): {[(s['time_slice'], s['is_active']) for s in sc]}"
    )
    p(f"  zones(n={len(zs)}): match L3={zc_L3}  match L1={zc_L1}")
    for z in zs:
        mark = (
            "OK-L1"
            if z["time_slice"] == L1
            else ("ONLY-L3" if z["time_slice"] == L3 else "MISMATCH")
        )
        p(f"     zone {z['location_name']!r} t={z['time_slice']!r}  {mark}")
    for c in chars:
        p(
            f"     player {c['user_id']}({c['name']}) current_local_id={c['current_local_id']!r}"
        )
    per.append((sid, len(zs), zc_L3, zc_L1, L1, L3))
    con.close()

p("\n" + "=" * 78)
p("AGGREGATE (all zones, all sessions)")
p(f"  zones total = {tot_zones}")
p(
    f"  L4 == L3 (current_time_slice) : {m_L3}/{tot_zones} = {m_L3 / tot_zones * 100:.1f}%   <-- the '39%' metric"
)
p(
    f"  L4 == L1 (active-scene clock) : {m_L1}/{tot_zones} = {m_L1 / tot_zones * 100:.1f}%   <-- corrected reference"
)
p(
    f"  sessions where L1 != L3       : {sess_div}/{sess_tot} = {sess_div / sess_tot * 100:.1f}%"
)

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(L))
print("WROTE", OUT)

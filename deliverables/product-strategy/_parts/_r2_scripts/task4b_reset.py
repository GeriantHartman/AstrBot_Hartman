"""Task 4b: quantify reset loss via visible_events AUTOINCREMENT fingerprint."""

import glob
import os
import sqlite3

DATA = r"E:\agentic-rpg\AstrBot\data\plugin_data\astrbot_plugin_agentic_rpg"


def seqof(cur, t):
    try:
        cur.execute("SELECT seq FROM sqlite_sequence WHERE name=?", (t,))
        r = cur.fetchone()
        return r[0] if r else None
    except BaseException:
        return None


def cnt(cur, t):
    try:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        return cur.fetchone()[0]
    except BaseException:
        return None


print(
    f"{'session':40s} {'ic':>5s} {'ve_seq':>7s} {'ve_cnt':>7s} {'ve_lost':>7s} {'ne_seq':>7s} {'ne_cnt':>7s} {'ne_lost':>7s}"
)
clean = []
for f in sorted(glob.glob(os.path.join(DATA, "world_*.db"))):
    con = sqlite3.connect(f)
    cur = con.cursor()
    b = os.path.basename(f)[:-3][len("world_") :]
    p = b.split("_")
    sid = p[0] + ":" + p[1] + ":" + "_".join(p[2:])
    try:
        cur.execute("SELECT interaction_count FROM game_sessions")
        r = cur.fetchone()
        ic = r[0] if r else None
    except BaseException:
        ic = None
    if ic is None:
        con.close()
        continue
    ves = seqof(cur, "visible_events")
    vec = cnt(cur, "visible_events")
    nes = seqof(cur, "npc_events")
    nec = cnt(cur, "npc_events")
    vel = (ves - vec) if (ves is not None and vec is not None) else None
    nel = (nes - nec) if (nes is not None and nec is not None) else None
    print(
        f"{sid:40s} {ic:5d} {str(ves):>7s} {str(vec):>7s} {str(vel):>7s} {str(nes):>7s} {str(nec):>7s} {str(nel):>7s}"
    )
    if vel == 0:
        clean.append((sid, ic, ves, vec))
    con.close()

print(
    "\n=== CLEAN sessions (visible_events seq==count, no reset) → baseline ve/turn ==="
)
tot_ic = 0
tot_ve = 0
for sid, ic, ves, vec in clean:
    if ic and ves:
        print(f"  {sid:40s} ic={ic:5d} ve={ves:5d}  ve/turn={ves / ic:.3f}")
        tot_ic += ic
        tot_ve += ves
print(f"  POOLED baseline: ve/turn = {tot_ve}/{tot_ic} = {tot_ve / tot_ic:.3f}")

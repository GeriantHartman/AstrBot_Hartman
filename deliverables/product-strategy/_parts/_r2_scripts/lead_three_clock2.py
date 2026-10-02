"""Lead forensic v2: three-layer clock consistency.

Layer S: game_sessions.current_time_slice              (session clock)
Layer C: scenes.time_slice for the scene the player is a MEMBER of
         (this is what move_to_zone / query_current_zone read)
Layer Z: zones.time_slice for the player's current_local_id

Correct JOIN: scene_members.scene_id -> scenes.scene_id
"""

import glob
import os
import sqlite3

DATA = r"E:\agentic-rpg\AstrBot\data\plugin_data\astrbot_plugin_agentic_rpg"


def safe(cur, sql, args=()):
    try:
        cur.execute(sql, args)
        return cur.fetchall()
    except Exception as e:
        return [("ERR:" + str(e)[:60],)]


rows = []
for f in sorted(glob.glob(os.path.join(DATA, "world_*.db"))):
    con = sqlite3.connect(f)
    cur = con.cursor()
    b = os.path.basename(f)[:-3]
    p = b.split("_")
    sid = p[0] + ":" + p[1] + ":" + "_".join(p[2:])

    gs = safe(
        cur,
        "SELECT interaction_count, current_time_slice, time_slice_index, "
        "day_count FROM game_sessions LIMIT 1",
    )
    if not gs or str(gs[0][0]).startswith("ERR"):
        con.close()
        continue
    ic, s_ts, s_idx, s_day = gs[0]

    cur.execute(
        "SELECT entity_id, name, current_local_id FROM characters WHERE is_player=1"
    )
    for peid, pname, pzone in cur.fetchall():
        # --- Layer C: the scene this player is a member of (latest joined) ---
        cs = safe(
            cur,
            "SELECT s.scene_id, s.time_slice, s.time_slice_index, s.day_count, "
            "s.is_active, s.local_id, m.joined_at "
            "FROM scene_members m JOIN scenes s ON s.scene_id = m.scene_id "
            "WHERE m.entity_id=? ORDER BY m.joined_at DESC LIMIT 1",
            (peid,),
        )
        c_ts = c_idx = c_day = c_active = c_local = None
        if cs and not str(cs[0][0]).startswith("ERR"):
            c_ts, c_idx, c_day, c_active, c_local = (
                cs[0][1],
                cs[0][2],
                cs[0][3],
                cs[0][4],
                cs[0][5],
            )
        # --- Layer Z: zone clock ---
        z = safe(
            cur,
            "SELECT location_name, time_slice FROM zones WHERE local_id=?",
            (pzone,),
        )
        z_ts = z[0][1] if z and not str(z[0][0]).startswith("ERR") else None
        z_name = z[0][0] if z and not str(z[0][0]).startswith("ERR") else None

        rows.append(
            {
                "sid": sid,
                "ic": ic,
                "player": pname,
                "peid": peid,
                "S": s_ts,
                "C": c_ts,
                "Z": z_ts,
                "zone": z_name,
                "c_local": c_local,
                "pzone": pzone,
                "c_active": c_active,
                "c_idx": c_idx,
                "s_idx": s_idx,
            }
        )
    con.close()

print(f"rows (session x player) = {len(rows)}\n")
hdr = (
    f"{'session':34s} {'ic':>5s} {'player':10s} {'S(sess)':10s} {'C(scene)':10s} "
    f"{'Z(zone)':10s} {'S=C':4s} {'C=Z':4s} {'S=Z':4s} {'scene.local==player.zone':4s}"
)
print(hdr)
print("-" * len(hdr))
cnt = {"hasC": 0, "SC": 0, "CZ": 0, "SZ": 0, "loc_eq": 0, "tot": 0}
for r in rows:
    sc = (r["S"] == r["C"]) if r["C"] is not None else None
    cz = (r["C"] == r["Z"]) if (r["C"] is not None and r["Z"] is not None) else None
    sz = (r["S"] == r["Z"]) if r["Z"] is not None else None
    le = (r["c_local"] == r["pzone"]) if r["c_local"] is not None else None
    cnt["tot"] += 1
    if r["C"] is not None:
        cnt["hasC"] += 1
        if sc:
            cnt["SC"] += 1
        if cz:
            cnt["CZ"] += 1
    if sz:
        cnt["SZ"] += 1
    if le:
        cnt["loc_eq"] += 1

    def f4(v):
        """Render a tri-state comparison for the report.

        Args:
            v: Comparison result or None for missing data.

        Returns:
            The existing Y/n/- report marker.
        """
        return ("Y" if v else "n") if v is not None else "-"

    print(
        f"{r['sid'][:34]:34s} {r['ic']:5d} {str(r['player'])[:10]:10s} "
        f"{str(r['S'])[:10]:10s} {str(r['C'])[:10]:10s} {str(r['Z'])[:10]:10s} "
        f"{f4(sc):4s} {f4(cz):4s} {f4(sz):4s} {f4(le):4s}"
    )

n = cnt
print(f"\nplayers with a scene membership      : {n['hasC']}/{n['tot']}")
print(
    f"  S == C  session clock == scene clock: {n['SC']}/{n['hasC']} = {100 * n['SC'] / max(1, n['hasC']):.1f}%"
)
print(
    f"  C == Z  scene clock   == zone clock : {n['CZ']}/{n['hasC']} = {100 * n['CZ'] / max(1, n['hasC']):.1f}%"
)
print(
    f"  S == Z  session clock == zone clock : {n['SZ']}/{n['tot']} = {100 * n['SZ'] / max(1, n['tot']):.1f}%"
)
print(
    f"  scene.local_id == player.current_local_id: {n['loc_eq']}/{n['tot']} = {100 * n['loc_eq'] / max(1, n['tot']):.1f}%"
)

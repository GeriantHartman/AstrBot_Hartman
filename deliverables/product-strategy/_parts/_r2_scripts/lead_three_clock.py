# -*- coding: utf-8 -*-
"""Lead forensic: three-layer clock consistency.

Layer S: game_sessions.current_time_slice   (session clock)
Layer C: scenes.time_slice WHERE is_active=1 (scene clock)  <- what move_to_zone reads
Layer Z: zones.time_slice WHERE local_id = player's current_local_id (zone clock)

Question: is my earlier 39% baseline (Z vs S) the right comparison?
If scene clock C diverges from session clock S, the defect is bigger.
"""
import sqlite3, glob, os

DATA = r'E:\agentic-rpg\AstrBot\data\plugin_data\astrbot_plugin_agentic_rpg'


def q1(cur, sql, args=()):
    try:
        cur.execute(sql, args)
        return cur.fetchone()
    except Exception as e:
        return ('ERR:' + str(e)[:40],)


rows = []
for f in sorted(glob.glob(os.path.join(DATA, 'world_*.db'))):
    con = sqlite3.connect(f)
    cur = con.cursor()
    b = os.path.basename(f)[:-3]
    p = b.split('_')
    sid = p[0] + ':' + p[1] + ':' + '_'.join(p[2:])

    gs = q1(cur, "SELECT interaction_count, current_time_slice, time_slice_index, "
                 "day_count, max_time_slice, max_time_index, max_day_count "
                 "FROM game_sessions LIMIT 1")
    if gs is None or (isinstance(gs[0], str) and gs[0].startswith('ERR')):
        con.close()
        continue
    ic, s_ts, s_idx, s_day = gs[0], gs[1], gs[2], gs[3]
    max_ts, max_idx, max_day = gs[4], gs[5], gs[6]

    # player entities
    cur.execute("SELECT entity_id, name, current_local_id FROM characters "
                "WHERE is_player=1")
    players = cur.fetchall()

    for peid, pname, pzone in players:
        # scene clock for this player
        c = q1(cur, "SELECT scene_id, local_id, time_slice, time_slice_index, day_count "
                    "FROM scenes WHERE is_active=1 AND session_id=? "
                    "AND local_id IN (SELECT local_id FROM scene_members WHERE entity_id=?) "
                    "LIMIT 1", (sid, peid))
        if c is None or (isinstance(c[0], str) and c[0].startswith('ERR')):
            c_ts = None
        else:
            c_ts = c[2]
        # zone clock
        z = q1(cur, "SELECT location_name, time_slice FROM zones WHERE local_id=?",
               (pzone,))
        z_ts = z[1] if z else None
        z_name = z[0] if z else None

        rows.append(dict(sid=sid, ic=ic, player=pname, peid=peid,
                         S=s_ts, C=c_ts, Z=z_ts, zone=z_name,
                         s_idx=s_idx, max_idx=max_idx,
                         s_day=s_day, max_day=max_day,
                         max_ts=max_ts))
    con.close()

print(f"rows (session x player) = {len(rows)}\n")
hdr = f"{'session':38s} {'ic':>5s} {'player':8s} {'S(session)':12s} {'C(scene)':12s} {'Z(zone)':12s} {'S=C':4s} {'C=Z':4s}"
print(hdr)
print('-' * len(hdr))
n_s_c_eq = n_c_z_eq = n_s_z_eq = n_has_c = 0
for r in rows:
    sc = (r['S'] == r['C']) if r['C'] is not None else None
    cz = (r['C'] == r['Z']) if (r['C'] is not None and r['Z'] is not None) else None
    sz = (r['S'] == r['Z']) if r['Z'] is not None else None
    if r['C'] is not None:
        n_has_c += 1
        if sc:
            n_s_c_eq += 1
        if cz:
            n_c_z_eq += 1
    if sz:
        n_s_z_eq += 1
    print(f"{r['sid'][:38]:38s} {r['ic']:5d} {str(r['player'])[:8]:8s} "
          f"{str(r['S'])[:12]:12s} {str(r['C'])[:12]:12s} {str(r['Z'])[:12]:12s} "
          f"{('Y' if sc else 'n') if sc is not None else '-':4s} "
          f"{('Y' if cz else 'n') if cz is not None else '-':4s}")

print()
print(f"players with an active scene: {n_has_c}")
print(f"  S == C  (session clock == scene clock): {n_s_c_eq}/{n_has_c} = "
      f"{100*n_s_c_eq/max(1,n_has_c):.1f}%")
print(f"  C == Z  (scene clock  == zone clock) : {n_c_z_eq}/{n_has_c} = "
      f"{100*n_c_z_eq/max(1,n_has_c):.1f}%")
print(f"  S == Z  (session clock== zone clock) : {n_s_z_eq}/{len(rows)} = "
      f"{100*n_s_z_eq/max(1,len(rows)):.1f}%")

print("\n=== reset fingerprint (max > current) ===")
n_reset = 0
for r in rows:
    if r['max_idx'] is not None and r['s_idx'] is not None and r['max_idx'] > r['s_idx']:
        n_reset += 1
print(f"players with max_time_index > time_slice_index: {n_reset}/{len(rows)}")

import os
import sqlite3

DATA = r"E:\agentic-rpg\AstrBot\data\plugin_data\astrbot_plugin_agentic_rpg"
for db in [
    "world_default_GroupMessage_966162158.db",
    "world_default_GroupMessage_289584858.db",
]:
    con = sqlite3.connect(os.path.join(DATA, db))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    print("=" * 70)
    print(db, flush=True)
    cur.execute(
        "SELECT current_time_slice,time_slice_index,max_time_slice,max_time_index,day_count,max_day_count FROM game_sessions"
    )
    for r in cur.fetchall():
        print(" gs:", dict(r), flush=True)
    cur.execute(
        "SELECT scene_id,local_id,time_slice,time_slice_index,day_count,is_active FROM scenes ORDER BY scene_id"
    )
    for r in cur.fetchall():
        print("  scene:", dict(r), flush=True)
    cur.execute("SELECT local_id,location_name,time_slice,area_id,privacy FROM zones")
    for r in cur.fetchall():
        print("  zone :", dict(r), flush=True)
    con.close()

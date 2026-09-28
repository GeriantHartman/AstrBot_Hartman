# -*- coding: utf-8 -*-
"""Task 1: full-DB player attribution scan."""
import sqlite3, glob, os, json

DATA = r"E:\agentic-rpg\AstrBot\data\plugin_data\astrbot_plugin_agentic_rpg"
files = sorted(glob.glob(os.path.join(DATA, "world_*.db")))

rows = []
for f in files:
    base = os.path.basename(f)[:-3]  # strip .db
    # session_id = filename after "world_" ; e.g. default_FriendMessage_2438094710 -> default:FriendMessage:2438094710
    sid = base[len("world_"):]
    # reconstruct: replace first two underscores with colons -> default:FriendMessage:2438094710
    parts = sid.split("_")
    if len(parts) >= 3:
        session_id = parts[0] + ":" + parts[1] + ":" + "_".join(parts[2:])
    else:
        session_id = sid
    con = sqlite3.connect(f)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    try:
        cur.execute("SELECT session_id, interaction_count, game_active, created_at FROM game_sessions")
        gs = cur.fetchall()
    except Exception as e:
        gs = []
    try:
        cur.execute("SELECT user_id, name, is_player FROM characters WHERE is_player=1")
        players = cur.fetchall()
    except Exception as e:
        players = []
    try:
        cur.execute("SELECT COUNT(*) FROM episode_memories")
        ep = cur.fetchone()[0]
    except Exception:
        ep = 0
    try:
        cur.execute("SELECT COUNT(*) FROM timeline_events")
        tl = cur.fetchone()[0]
    except Exception:
        tl = 0
    rows.append({
        "file": os.path.basename(f),
        "session_id": session_id,
        "gs_rows": [dict(g) for g in gs],
        "players": [dict(p) for p in players],
        "episode_memories": ep,
        "timeline_events": tl,
    })
    con.close()

print(json.dumps(rows, ensure_ascii=False, indent=1))

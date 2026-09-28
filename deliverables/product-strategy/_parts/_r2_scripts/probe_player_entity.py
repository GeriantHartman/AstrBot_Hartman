# -*- coding: utf-8 -*-
"""Task 1b: probe player_entity_id tables to test single-player attribution."""
import sqlite3, glob, os, json

DATA = r"E:\agentic-rpg\AstrBot\data\plugin_data\astrbot_plugin_agentic_rpg"

TABLES = ["episode_memories","npc_events","visible_events","timeline_events",
          "life_opportunities","npc_player_affinity","npc_player_impressions",
          "npc_evolution_triggers","commissions","inventory","player_levels","player_skills"]

for f in sorted(glob.glob(os.path.join(DATA,"world_*.db"))):
    base = os.path.basename(f)[:-3]
    sid_parts = base[len("world_"):].split("_")
    session_id = sid_parts[0]+":"+sid_parts[1]+":"+"_".join(sid_parts[2:])
    con = sqlite3.connect(f); con.row_factory=sqlite3.Row; cur=con.cursor()
    # players
    cur.execute("SELECT entity_id,user_id,name FROM characters WHERE is_player=1")
    pl = cur.fetchall()
    if not pl: 
        con.close(); continue
    cur.execute("SELECT COUNT(*) FROM game_sessions")
    if cur.fetchone()[0]==0:
        con.close(); continue
    print("="*80)
    print(session_id, "| players:", [(p['user_id'],p['name'],p['entity_id']) for p in pl])
    for t in TABLES:
        try:
            cur.execute(f"PRAGMA table_info({t})")
            cols=[r[1] for r in cur.fetchall()]
            if 'player_entity_id' in cols:
                cur.execute(f"SELECT player_entity_id, COUNT(*) c FROM {t} GROUP BY player_entity_id ORDER BY c DESC")
                grp=cur.fetchall()
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                n=cur.fetchone()[0]
                print(f"  {t:28s} n={n:5d}  by player_entity_id: {[(r['player_entity_id'], r['c']) for r in grp]}")
            elif 'owner_entity_id' in cols:
                cur.execute(f"SELECT owner_entity_id, COUNT(*) c FROM {t} GROUP BY owner_entity_id ORDER BY c DESC")
                grp=cur.fetchall()
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                n=cur.fetchone()[0]
                print(f"  {t:28s} n={n:5d}  by owner_entity_id: {[(r['owner_entity_id'], r['c']) for r in grp]}")
            elif 'entity_id' in cols:
                cur.execute(f"SELECT entity_id, COUNT(*) c FROM {t} GROUP BY entity_id ORDER BY c DESC LIMIT 6")
                grp=cur.fetchall()
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                n=cur.fetchone()[0]
                print(f"  {t:28s} n={n:5d}  by entity_id(top6): {[(r['entity_id'], r['c']) for r in grp]}")
            else:
                print(f"  {t:28s} (no player_entity_id col)")
        except Exception as e:
            print(f"  {t:28s} ERR {e}")
    con.close()

# -*- coding: utf-8 -*-
"""Task 1c: quantify per-player share in shared sessions across candidate tables."""
import sqlite3, glob, os, json, statistics

DATA = r"E:\agentic-rpg\AstrBot\data\plugin_data\astrbot_plugin_agentic_rpg"

SHARED = {
 "default:GroupMessage:1097436019": 158,
 "default:GroupMessage:218606013": 48,
 "default:GroupMessage:230394566": 408,
 "default:GroupMessage:909871205": 53,
 "default:GroupMessage:966162158": 199,
}
# map session -> filename
def find_file(session_id):
    parts = session_id.split(":")
    base = "world_" + parts[0] + "_" + parts[1] + "_" + "_".join(parts[2:]) + ".db"
    return os.path.join(DATA, base)

TABLES = ["episode_memories","npc_events","visible_events","timeline_events",
          "life_opportunities","npc_player_impressions","npc_evolution_triggers"]

for sid, ic in SHARED.items():
    f = find_file(sid)
    con=sqlite3.connect(f); con.row_factory=sqlite3.Row; cur=con.cursor()
    cur.execute("SELECT entity_id,user_id,name FROM characters WHERE is_player=1")
    players={r['entity_id']:(r['user_id'],r['name']) for r in cur.fetchall()}
    print("="*78)
    print(f"{sid}  ic={ic}  players={[ (v[0],v[1]) for v in players.values()]}")
    for t in TABLES:
        try:
            cur.execute(f"PRAGMA table_info({t})")
            cols=[r[1] for r in cur.fetchall()]
            if 'player_entity_id' not in cols: 
                print(f"  {t:26s} (no player_entity_id)"); continue
            cur.execute(f"SELECT player_entity_id, COUNT(*) c FROM {t} GROUP BY player_entity_id")
            g={r['player_entity_id']:r['c'] for r in cur.fetchall()}
            total=sum(g.values())
            attributed=sum(c for k,c in g.items() if k in players)
            unattr=g.get('',0)
            shares={}
            for eid,(uid,nm) in players.items():
                c=g.get(eid,0)
                shares[uid]= c/attributed if attributed else 0
            print(f"  {t:26s} n={total:4d} attr={attributed:4d} unattr={unattr:4d}  " +
                  "  ".join(f"{uid}:{c}/{g.get(eid,0)}={shares[uid]*100:4.1f}%" for eid,(uid,nm) in players.items()))
        except Exception as e:
            print(f"  {t:26s} ERR {e}")
    con.close()

# -*- coding: utf-8 -*-
import sqlite3, glob, os
DATA=r'E:\agentic-rpg\AstrBot\data\plugin_data\astrbot_plugin_agentic_rpg'
# build map session_id -> file
mp={}
for f in glob.glob(os.path.join(DATA,'world_*.db')):
    b=os.path.basename(f)[:-3][len('world_'):]
    p=b.split('_')
    sid=p[0]+':'+p[1]+':'+'_'.join(p[2:])
    mp[sid]=f
SOLO={'default:FriendMessage:2438094710':1062,'default:FriendMessage:245432630':12,'default:FriendMessage:942361330':512,
'default:GroupMessage:1090658701':498,'default:GroupMessage:1098307480':47,'default:GroupMessage:289584858':291,
'default:GroupMessage:426750065':2,'default:GroupMessage:529384034':134,'default:GroupMessage:674489689':18,
'default:GroupMessage:702510574':62,'default:GroupMessage:814560566':5,'default:GroupMessage:877459692':408,
'default:GroupMessage:955426627':14}
TABLES=['episode_memories','npc_events','visible_events','timeline_events','life_opportunities','npc_player_impressions','npc_evolution_triggers','scenes','scene_members','zones','areas','npc_scene_presence','semantic_chronicles','world_canon']
print(f"{'session':>38s} {'ic':>5s} "+' '.join(f'{t[:11]:>12s}' for t in TABLES))
for sid,ic in SOLO.items():
    con=sqlite3.connect(mp[sid]); cur=con.cursor()
    vals=[]
    for t in TABLES:
        try:
            cur.execute(f'SELECT COUNT(*) FROM {t}'); vals.append(cur.fetchone()[0])
        except Exception: vals.append(-1)
    con.close()
    print(f'{sid:>38s} {ic:5d} '+' '.join(f'{v:12d}' for v in vals))

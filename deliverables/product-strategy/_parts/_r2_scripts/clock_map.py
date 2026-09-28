# -*- coding: utf-8 -*-
import sqlite3, os, glob
DATA=r'E:\agentic-rpg\AstrBot\data\plugin_data\astrbot_plugin_agentic_rpg'
OUT=r'E:\agentic-rpg\AstrBot\deliverables\product-strategy\_parts\_r2_scripts\clock_map.txt'
L=[]
def p(*a): L.append(' '.join(str(x) for x in a))

for db in ['world_default_GroupMessage_966162158.db','world_default_GroupMessage_230394566.db']:
    con=sqlite3.connect(os.path.join(DATA,db)); con.row_factory=sqlite3.Row; cur=con.cursor()
    p('='*70); p(db)
    cur.execute('SELECT local_id,location_name,time_slice,area_id FROM zones')
    zs=[dict(r) for r in cur.fetchall()]
    p(' zones sample:', [(z['local_id'],z['location_name'],z['time_slice']) for z in zs[:6]])
    cur.execute('SELECT area_id,name FROM areas')
    p(' areas:', [(dict(r)['area_id'],dict(r)['name']) for r in cur.fetchall()][:6])
    cur.execute('SELECT entity_id,user_id,name,current_local_id FROM characters WHERE is_player=1')
    ch=[dict(r) for r in cur.fetchall()]
    p(' players:', ch)
    zids={z['local_id'] for z in zs}
    for c in ch:
        p(f"   player {c['user_id']} current_local_id={c['current_local_id']!r} in zones.local_id? {c['current_local_id'] in zids}")
    # scene_members
    cur.execute('SELECT session_id,scene_id,entity_id FROM scene_members')
    sm=[dict(r) for r in cur.fetchall()]
    p(' scene_members n=',len(sm),' sample:',sm[:8])
    cur.execute('SELECT scene_id,local_id,time_slice,is_active FROM scenes')
    p(' scenes:', [(dict(r)['scene_id'],dict(r)['local_id'],dict(r)['time_slice'],dict(r)['is_active']) for r in cur.fetchall()])
    con.close()

with open(OUT,'w',encoding='utf-8') as f: f.write('\n'.join(L))
print('ok')

# -*- coding: utf-8 -*-
"""Task 3: C6 affinity 'diode' validation across all world DBs."""
import sqlite3, glob, os, json, statistics
from collections import Counter

DATA=r'E:\agentic-rpg\AstrBot\data\plugin_data\astrbot_plugin_agentic_rpg'
rows=[]
for f in sorted(glob.glob(os.path.join(DATA,'world_*.db'))):
    con=sqlite3.connect(f); con.row_factory=sqlite3.Row; cur=con.cursor()
    b=os.path.basename(f)[:-3][len('world_'):]; p=b.split('_'); sid=p[0]+':'+p[1]+':'+'_'.join(p[2:])
    try:
        cur.execute("SELECT npc_entity_id,player_entity_id,value,stage,history FROM npc_player_affinity")
        for r in cur.fetchall():
            rows.append({'sid':sid,'npc':r['npc_entity_id'],'pl':r['player_entity_id'],
                         'value':r['value'],'stage':r['stage'],'history':r['history']})
    except Exception as e:
        pass
    con.close()

print("TOTAL npc_player_affinity rows:", len(rows))
vals=[r['value'] for r in rows]
print("value: min",min(vals),"max",max(vals),"mean",round(statistics.mean(vals),1),"median",statistics.median(vals))
print("\nvalue histogram (bins of 10):")
bins=Counter()
for v in vals:
    bins[int((v//10)*10)]+=1
for k in sorted(bins): print(f"  [{k:4d},{k+10:4d}) : {bins[k]:4d}  {'#'*bins[k]}")

print("\nEXACT extremes:")
print("  ==100 :",sum(1 for v in vals if v==100))
print("  ==-100:",sum(1 for v in vals if v==-100))
print("  <=-90 :",sum(1 for v in vals if v<=-90))
print("  >=90  :",sum(1 for v in vals if v>=90))
print("  (-50,50):",sum(1 for v in vals if -50<v<50))
print("  [-20,20]:",sum(1 for v in vals if -20<=v<=20))

print("\nstage distribution:")
sc=Counter(r['stage'] for r in rows)
for k,c in sc.most_common(): print(f"  {str(k):20s} {c:5d}  {c/len(rows)*100:5.1f}%")

print("\nhistory length distribution:")
hl=Counter()
for r in rows:
    h=r['history']
    try:
        if h is None: n=0
        elif isinstance(h,str):
            try: n=len(json.loads(h))
            except: n=len(h.split(';')) if h else 0
        else: n=len(h)
    except: n=-1
    hl[n]+=1
for k in sorted(hl): print(f"  len={k:3d}: {hl[k]:5d}")

# per-player breakdown
print("\nby player_entity_id:")
pc=Counter(r['pl'] for r in rows)
for k,c in pc.most_common(15): print(f"  {str(k):30s} {c:5d}")

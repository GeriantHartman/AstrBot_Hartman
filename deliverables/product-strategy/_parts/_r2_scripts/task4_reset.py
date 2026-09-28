# -*- coding: utf-8 -*-
"""Task 4: reset evidence via sqlite_sequence high-watermarks."""
import sqlite3, glob, os

DATA=r'E:\agentic-rpg\AstrBot\data\plugin_data\astrbot_plugin_agentic_rpg'
print(f"{'file':46s} {'ic':>5s}  {'table':26s} {'seq':>6s} {'count':>6s} {'maxrowid':>8s}  gap")
tot_gap=0
for f in sorted(glob.glob(os.path.join(DATA,'world_*.db'))):
    con=sqlite3.connect(f); cur=con.cursor()
    try:
        cur.execute('SELECT name,seq FROM sqlite_sequence'); seqs=cur.fetchall()
    except Exception: seqs=[]
    ic=None
    try:
        cur.execute('SELECT interaction_count FROM game_sessions'); r=cur.fetchone(); ic=r[0] if r else None
    except: pass
    if not seqs: con.close(); continue
    base=os.path.basename(f)
    for name,seq in sorted(seqs, key=lambda x:-x[1]):
        try:
            cur.execute(f'SELECT COUNT(*) FROM {name}'); c=cur.fetchone()[0]
        except: c=-1
        try:
            cur.execute(f'SELECT MAX(rowid) FROM {name}'); mx=cur.fetchone()[0]
        except: mx=None
        gap = seq - (mx or 0)
        # report tables where ever-inserted (seq) far exceeds current rows
        if c>=0 and seq > c + 5:
            print(f"{base:46s} {str(ic):>5s}  {name:26s} {seq:6d} {c:6d} {str(mx):>8s}  {gap}")
            tot_gap+=gap
    con.close()
print("\nNOTE: gap = seq - max(rowid); seq = highest AUTOINCREMENT ever issued = rows ever inserted (incl. deleted).")

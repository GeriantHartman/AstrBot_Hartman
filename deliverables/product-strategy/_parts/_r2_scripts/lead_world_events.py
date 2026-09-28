# -*- coding: utf-8 -*-
"""Are the "world event" primitives actually populated?"""
import sqlite3, glob, os

DATA = r'E:\agentic-rpg\AstrBot\data\plugin_data\astrbot_plugin_agentic_rpg'
TABS = ['world_canon', 'timeline_events', 'global_flags', 'npc_evolution_log',
        'story_hooks', 'semantic_chronicles', 'npc_player_affinity', 'episode_memories']

data = {}
for f in sorted(glob.glob(os.path.join(DATA, 'world_*.db'))):
    b = os.path.basename(f)[:-3]
    p = b.split('_')
    sid = p[0] + ':' + p[1] + ':' + '_'.join(p[2:])
    con = sqlite3.connect(f); cur = con.cursor()
    try:
        cur.execute('SELECT interaction_count FROM game_sessions'); r = cur.fetchone()
    except Exception:
        r = None
    ic = (r[0] if r else 0) or 0
    if not ic:
        con.close(); continue
    counts = []
    for t in TABS:
        try:
            cur.execute('SELECT COUNT(*) FROM %s' % t)
            counts.append(cur.fetchone()[0])
        except Exception:
            counts.append(-1)
    data[sid] = (ic, counts)
    con.close()

hdr = '%-36s %5s ' % ('session', 'ic') + ' '.join('%9s' % t[:9] for t in TABS)
print(hdr); print('-' * len(hdr))
tot = [0] * len(TABS)
for sid, (ic, counts) in sorted(data.items(), key=lambda x: -x[1][0]):
    print('%-36s %5d ' % (sid[:36], ic) + ' '.join('%9d' % v for v in counts))
    for i, v in enumerate(counts):
        if v > 0:
            tot[i] += v
print('-' * len(hdr))
print('%-36s %5s ' % ('TOTAL', '') + ' '.join('%9d' % v for v in tot))
print()
n = len(data)
print('sessions analysed (ic>0): %d' % n)
print()
print('%-22s %8s %8s  %s' % ('table', 'total', 'sess>0', 'verdict'))
for i, t in enumerate(TABS):
    nsess = sum(1 for _, c in data.values() if c[i] > 0)
    verdict = 'POPULATED' if nsess else '*** NEVER WRITTEN ***'
    print('%-22s %8d %8d  %s' % (t, tot[i], nsess, verdict))

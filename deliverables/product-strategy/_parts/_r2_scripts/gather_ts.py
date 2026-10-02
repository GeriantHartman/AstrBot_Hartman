"""Task 2: gather turn timestamps from audit + DB tables for trigger analysis."""

import glob
import json
import os
import sqlite3

DATA = r"E:\agentic-rpg\AstrBot\data\plugin_data\astrbot_plugin_agentic_rpg"
AUD = os.path.join(DATA, "llm_audit_index")

# ---- A) audit per-turn timestamps ----
aud = {}
for f in glob.glob(os.path.join(AUD, "*.jsonl")):
    n = 0
    ts = []
    for line in open(f, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except BaseException:
            continue
        n += 1
        if r.get("created_at"):
            ts.append(r["created_at"])
    sid = None
    # derive session id from a record
    try:
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if line:
                sid = json.loads(line).get("session_id")
                break
    except BaseException:
        pass
    aud[os.path.basename(f)] = {"sid": sid, "n": n, "ts": sorted(ts)}

print("=== AUDIT COVERAGE ===")
tot = 0
for k, v in sorted(aud.items(), key=lambda x: -x[1]["n"]):
    if v["sid"] and v["sid"].startswith("default"):
        print(f"  {v['sid']:40s} records={v['n']:4d}")
        tot += v["n"]
print("  total default records:", tot)

# ---- B) DB timestamps ----
print("\n=== DB timestamp columns ===")
for f in sorted(glob.glob(os.path.join(DATA, "world_*.db"))):
    con = sqlite3.connect(f)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    b = os.path.basename(f)[:-3][len("world_") :]
    p = b.split("_")
    sid = p[0] + ":" + p[1] + ":" + "_".join(p[2:])
    cur.execute("SELECT COUNT(*) FROM game_sessions")
    if cur.fetchone()[0] == 0:
        con.close()
        continue
    out = [sid]
    for t, col in [
        ("game_sessions", "created_at"),
        ("episode_memories", "created_at"),
        ("timeline_events", "created_at"),
        ("visible_events", "timestamp"),
        ("npc_events", "timestamp"),
        ("npc_evolution_log", "created_at"),
        ("world_canon", "created_at"),
    ]:
        try:
            cur.execute(
                f"SELECT MIN({col}),MAX({col}),COUNT({col}) FROM {t} WHERE {col} IS NOT NULL"
            )
            r = cur.fetchone()
            out.append(f"{t[:10]}:n={r[2]},min={r[0]},max={r[1]}")
        except Exception:
            out.append(f"{t[:10]}:ERR")
    con.close()
    print("  " + " | ".join(str(x) for x in out))

import os, time, math, threading, sqlite3, shutil
from waitress import serve
from app import app, init_db, DB_PATH, npc_auto_tick, npc_settlement_tick, run_sasaeng_checks, run_fan_letter_checks, run_fan_gift_checks

os.chdir(os.path.dirname(os.path.abspath(__file__)))

with app.app_context():
    init_db()

TICK_INTERVAL = int(os.environ.get("TICK_INTERVAL_SECONDS", "3600"))

def _get_meta(db, key, default=None):
    row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default

def _set_meta(db, key, value):
    db.execute("INSERT INTO meta (key,value) VALUES (?,?) "
               "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))

def _decay_rate(value):
    if value > 80: return 0.05
    if value > 50: return 0.03
    if value > 0:  return 0.01
    return 0.0

def _tick_once(db):
    with app.app_context():
        npc_auto_tick()
        run_sasaeng_checks()
        run_fan_letter_checks()
        run_fan_gift_checks()

    last_tick_ts = int(_get_meta(db, 'last_tick_ts', 0) or 0)
    tick_counter = int(_get_meta(db, 'tick_counter', 0) or 0)
    now = int(time.time())
    tick_id = tick_counter + 1
    window_start = last_tick_ts if last_tick_ts else now - TICK_INTERVAL

    rows = db.execute(
        """SELECT po.player_id, p.stage_name, SUM(po.heat) total_heat
           FROM posts po JOIN players p ON p.id = po.player_id
           WHERE po.created_ts > ?
           GROUP BY po.player_id HAVING total_heat > 0
           ORDER BY total_heat DESC LIMIT 20""",
        (window_start,)).fetchall()

    active_ids = set()
    for rank, r in enumerate(rows, start=1):
        active_ids.add(r[0])
        db.execute(
            "INSERT INTO trending_topics (topic_text,related_player_id,topic_kind,heat,rank,tick_id,created_ts) "
            "VALUES (?,?,?,?,?,?,?)",
            (f"#{r[1]} 引发热议#", r[0], 'buzz', r[2], rank, tick_id, now))

    all_players = db.execute("SELECT id, popularity, fans_count FROM players").fetchall()
    for p in all_players:
        pid, popularity, fans_count = p[0], p[1], p[2]
        if pid in active_ids:
            continue
        pop_rate = _decay_rate(popularity)
        fans_rate = pop_rate / 2
        new_pop = max(0, popularity - math.ceil(popularity * pop_rate)) if pop_rate else popularity
        new_fans = max(0, fans_count - math.ceil(fans_count * fans_rate)) if fans_rate else fans_count
        if new_pop != popularity or new_fans != fans_count:
            db.execute("UPDATE players SET popularity=?, fans_count=? WHERE id=?", (new_pop, new_fans, pid))

    _set_meta(db, 'last_tick_ts', now)
    _set_meta(db, 'tick_counter', tick_id)
    db.commit()

def _tick_loop():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    while True:
        try:
            _tick_once(db)
        except Exception:
            pass
        time.sleep(TICK_INTERVAL)

SETTLEMENT_INTERVAL = 20  # 剧组定角/杀青、代言签约/到期这类到点结算,不用等一整小时的大 tick

def _settlement_loop():
    while True:
        time.sleep(SETTLEMENT_INTERVAL)
        try:
            with app.app_context():
                npc_settlement_tick()
        except Exception:
            pass

def _db_backup_loop():
    interval = 3600
    keep = 24
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'db_backups')
    os.makedirs(backup_dir, exist_ok=True)
    while True:
        time.sleep(interval)
        try:
            ts = time.strftime('%Y%m%d_%H%M%S')
            dst = os.path.join(backup_dir, f'yulequan_{ts}.db')
            shutil.copy2(DB_PATH, dst)
            files = sorted([f for f in os.listdir(backup_dir) if f.endswith('.db')], reverse=True)
            for old in files[keep:]:
                os.remove(os.path.join(backup_dir, old))
        except Exception:
            pass

t = threading.Thread(target=_tick_loop, daemon=True)
t.start()

t2 = threading.Thread(target=_db_backup_loop, daemon=True)
t2.start()

t3 = threading.Thread(target=_settlement_loop, daemon=True)
t3.start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5007))
    serve(app, host='0.0.0.0', port=port)

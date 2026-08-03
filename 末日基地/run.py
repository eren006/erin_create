import os, time, threading, shutil
from waitress import serve
from app import app, init_db, run_day_tick, DB_PATH, DAY_SECONDS

os.chdir(os.path.dirname(os.path.abspath(__file__)))

with app.app_context():
    init_db()

def _tick_loop():
    while True:
        time.sleep(DAY_SECONDS)
        try:
            with app.app_context():
                run_day_tick()
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
            dst = os.path.join(backup_dir, f'modaya_{ts}.db')
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5008))
    serve(app, host='0.0.0.0', port=port)

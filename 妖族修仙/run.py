import os, time, shutil, threading
from waitress import serve
from app import app, init_db, DB_PATH, snapshot_tick

os.chdir(os.path.dirname(os.path.abspath(__file__)))

with app.app_context():
    init_db()

SNAPSHOT_INTERVAL = int(os.environ.get("SNAPSHOT_INTERVAL_SECONDS", "3600"))

def _snapshot_loop():
    while True:
        time.sleep(SNAPSHOT_INTERVAL)
        try:
            with app.app_context():
                snapshot_tick()
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
            dst = os.path.join(backup_dir, f'yaozu_{ts}.db')
            shutil.copy2(DB_PATH, dst)
            files = sorted([f for f in os.listdir(backup_dir) if f.endswith('.db')], reverse=True)
            for old in files[keep:]:
                os.remove(os.path.join(backup_dir, old))
        except Exception:
            pass

threading.Thread(target=_snapshot_loop, daemon=True).start()
threading.Thread(target=_db_backup_loop, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5019))
    serve(app, host='0.0.0.0', port=port)

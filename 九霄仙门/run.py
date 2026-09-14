import os, time, shutil, threading
from waitress import serve
from app import app, init_db, DB_PATH, lifespan_tick, retreat_labor_notify_tick, sect_gossip_tick, manyue_tick

os.chdir(os.path.dirname(os.path.abspath(__file__)))

with app.app_context():
    init_db()

LIFESPAN_CHECK_INTERVAL = int(os.environ.get("LIFESPAN_CHECK_INTERVAL_SECONDS", "300"))
RETREAT_LABOR_NOTIFY_INTERVAL = int(os.environ.get("RETREAT_LABOR_NOTIFY_INTERVAL_SECONDS", "120"))
SECT_GOSSIP_CHECK_INTERVAL = int(os.environ.get("SECT_GOSSIP_CHECK_INTERVAL_SECONDS", "3600"))
MANYUE_CHECK_INTERVAL = int(os.environ.get("MANYUE_CHECK_INTERVAL_SECONDS", "300"))

def _lifespan_loop():
    while True:
        time.sleep(LIFESPAN_CHECK_INTERVAL)
        try:
            with app.app_context():
                lifespan_tick()
        except Exception:
            pass

def _retreat_labor_notify_loop():
    while True:
        time.sleep(RETREAT_LABOR_NOTIFY_INTERVAL)
        try:
            with app.app_context():
                retreat_labor_notify_tick()
        except Exception:
            pass

def _sect_gossip_loop():
    while True:
        time.sleep(SECT_GOSSIP_CHECK_INTERVAL)
        try:
            with app.app_context():
                sect_gossip_tick()
        except Exception:
            pass

def _manyue_loop():
    while True:
        time.sleep(MANYUE_CHECK_INTERVAL)
        try:
            with app.app_context():
                manyue_tick()
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
            dst = os.path.join(backup_dir, f'jiuxiao_{ts}.db')
            shutil.copy2(DB_PATH, dst)
            files = sorted([f for f in os.listdir(backup_dir) if f.endswith('.db')], reverse=True)
            for old in files[keep:]:
                os.remove(os.path.join(backup_dir, old))
        except Exception:
            pass

threading.Thread(target=_lifespan_loop, daemon=True).start()
threading.Thread(target=_retreat_labor_notify_loop, daemon=True).start()
threading.Thread(target=_sect_gossip_loop, daemon=True).start()
threading.Thread(target=_manyue_loop, daemon=True).start()
threading.Thread(target=_db_backup_loop, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5020))
    serve(app, host='0.0.0.0', port=port)

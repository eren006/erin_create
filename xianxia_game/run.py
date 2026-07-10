import os
import shutil
import time
import threading
import sqlite3
from waitress import serve
from app import app, init_db, _snapshot_loop, process_cave, generate_cave_pool, DB_PATH, _ghost_loop, _superior_auction_loop, _red_packet_loop, _advance_time_loop

os.chdir(os.path.dirname(os.path.abspath(__file__)))

with app.app_context():
    init_db()

def _db_backup_loop():
    """每小时备份一次 xianxia.db，保留最近 24 份。"""
    INTERVAL  = 3600
    KEEP      = 24
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'db_backups')
    os.makedirs(backup_dir, exist_ok=True)
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'xianxia.db')

    while True:
        time.sleep(INTERVAL)
        try:
            ts = time.strftime('%Y%m%d_%H%M%S')
            dst = os.path.join(backup_dir, f'xianxia_{ts}.db')
            shutil.copy2(db_path, dst)
            # 只保留最新 KEEP 份
            files = sorted(
                [f for f in os.listdir(backup_dir) if f.endswith('.db')],
                reverse=True
            )
            for old in files[KEEP:]:
                os.remove(os.path.join(backup_dir, old))
        except Exception:
            pass

t1 = threading.Thread(target=_snapshot_loop, daemon=True)
t1.start()

t2 = threading.Thread(target=_db_backup_loop, daemon=True)
t2.start()

def _cave_clock_loop():
    """每小时 01 分结算一次所有开启洞府的玩家。"""
    while True:
        # 等到下一个 xx:01
        now = time.localtime()
        wait = (60 - now.tm_min + 1) % 60 * 60 - now.tm_sec
        if wait <= 0:
            wait += 3600
        time.sleep(wait)
        try:
            db = sqlite3.connect(DB_PATH)
            ids = db.execute(
                "SELECT id, cave_decor FROM characters WHERE is_npc=0 AND status='alive' "
                "AND cave_mode IS NOT NULL AND cave_mode != 'off'").fetchall()
            db.close()
            for char_id, decor in ids:
                try:
                    process_cave(char_id)
                    generate_cave_pool(char_id, decor)
                except Exception:
                    pass
        except Exception:
            pass

t3 = threading.Thread(target=_cave_clock_loop, daemon=True)
t3.start()

t4 = threading.Thread(target=_ghost_loop, daemon=True)
t4.start()

t5 = threading.Thread(target=_superior_auction_loop, daemon=True)
t5.start()

t6 = threading.Thread(target=_red_packet_loop, daemon=True)
t6.start()

t7 = threading.Thread(target=_advance_time_loop, daemon=True)
t7.start()

serve(app, host='0.0.0.0', port=5006)

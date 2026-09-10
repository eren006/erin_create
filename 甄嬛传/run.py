"""生产入口：waitress + 后台结算线程 + 每小时备份数据库"""
import os, time, threading, sqlite3, traceback
from waitress import serve
from app import app, init_db, maybe_settle, DB_PATH

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with app.app_context():
    init_db()

def _settle_loop():
    # 每分钟看一眼：过了当天结算时刻且当天还没结算，就结算一次。
    # 按"日期是否已结算"判断而不是 sleep 固定秒数，服务重启不会漏结算或重复结算。
    while True:
        try:
            with app.app_context():
                maybe_settle()
        except Exception:
            traceback.print_exc()
        time.sleep(60)

def _backup_loop():
    backup_dir = os.path.join(BASE_DIR, 'db_backups')
    os.makedirs(backup_dir, exist_ok=True)
    while True:
        time.sleep(3600)
        try:
            dst = os.path.join(backup_dir, f"zhenhuan_{time.strftime('%Y%m%d_%H%M%S')}.db")
            # WAL 模式下直接拷文件可能漏掉还没合并的写入，用 SQLite 自带的在线备份
            src, out = sqlite3.connect(DB_PATH), sqlite3.connect(dst)
            with out: src.backup(out)
            src.close(); out.close()
            files = sorted([f for f in os.listdir(backup_dir) if f.endswith('.db')], reverse=True)
            for old in files[48:]:
                os.remove(os.path.join(backup_dir, old))
        except Exception:
            traceback.print_exc()

threading.Thread(target=_settle_loop, daemon=True).start()
threading.Thread(target=_backup_loop, daemon=True).start()

if __name__ == '__main__':
    serve(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5024)), threads=8)

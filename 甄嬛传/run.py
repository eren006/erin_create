"""生产入口：waitress + 后台结算线程 + 每小时备份数据库。出错、拖延、备份失败都会记告警（见 app.run_settle_cycle）"""
import os, time, threading, traceback
from waitress import serve
from app import app, init_db, run_settle_cycle, backup_db, raise_alert

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with app.app_context():
    init_db()

def _settle_loop():
    # 每分钟看一眼：过了当天结算时刻且当天还没结算，就结算一次。
    # 按"日期是否已结算"判断而不是 sleep 固定秒数，服务重启不会漏结算或重复结算。
    while True:
        try:
            run_settle_cycle()
        except Exception:
            traceback.print_exc()
        time.sleep(60)

def _backup_loop():
    backup_dir = os.path.join(BASE_DIR, 'db_backups')
    while True:
        time.sleep(3600)
        try:
            backup_db(backup_dir)
        except Exception as e:
            traceback.print_exc()
            raise_alert('backup', 'backup-failed', f"数据库备份失败：{type(e).__name__}: {str(e)[:150]}", traceback.format_exc()[-1500:])

threading.Thread(target=_settle_loop, daemon=True).start()
threading.Thread(target=_backup_loop, daemon=True).start()

if __name__ == '__main__':
    serve(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5024)), threads=8)

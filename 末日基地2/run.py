import os, sys, time, threading, traceback, shutil
from waitress import serve
from app import app, init_db, run_tick, DB_PATH

os.chdir(os.path.dirname(os.path.abspath(__file__)))

with app.app_context():
    init_db()

TICK_INTERVAL = 60  # 现实60秒推进一次,内部按实际经过秒数折算游戏时间

def _tick_loop():
    while True:
        time.sleep(TICK_INTERVAL)
        try:
            # run_tick 内部会调用 kill_character/is_night 等依赖 Flask g 的辅助函数,
            # 后台线程本身没有请求上下文,必须手动包一个,否则会抛 RuntimeError 被下面吞掉、
            # 角色卡在HP归零但状态还是alive(踩过这个坑,饥饿/夜袭死亡曾经全部失效)
            with app.app_context():
                run_tick()
        except Exception:
            traceback.print_exc(file=sys.stderr)

def _db_backup_loop():
    """试玩阶段真实玩家数据值得保留,每小时备份一次,保留最近24份。"""
    interval = 3600
    keep = 24
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db_backups")
    os.makedirs(backup_dir, exist_ok=True)
    while True:
        time.sleep(interval)
        try:
            ts = time.strftime("%Y%m%d_%H%M%S")
            dst = os.path.join(backup_dir, f"modaya2_{ts}.db")
            shutil.copy2(DB_PATH, dst)
            files = sorted([f for f in os.listdir(backup_dir) if f.endswith(".db")], reverse=True)
            for old in files[keep:]:
                os.remove(os.path.join(backup_dir, old))
        except Exception:
            traceback.print_exc(file=sys.stderr)

t = threading.Thread(target=_tick_loop, daemon=True)
t.start()

t2 = threading.Thread(target=_db_backup_loop, daemon=True)
t2.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5011))
    serve(app, host="0.0.0.0", port=port)

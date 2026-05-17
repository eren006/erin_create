"""
rp_archive 自动备份模块
- 每天 03:00 用 SQLite 在线备份 API 安全复制数据库（不影响正在写入的连接）
- 本地保留最近 7 份，自动清理更早的备份
- 可选：上传到阿里云 OSS（填写下方环境变量或直接修改常量后生效）
"""

import os
import gzip
import shutil
import sqlite3
import logging
import threading
import time
from datetime import datetime, timedelta

# ── 本地路径 ──────────────────────────────────────────────────────────────────
_BASE_DIR   = os.path.dirname(__file__)
DB_PATH     = os.path.join(_BASE_DIR, "rp_data.db")
BACKUP_DIR  = os.path.join(_BASE_DIR, "backups")
LOCAL_KEEP  = 7          # 本地保留最近 N 份

# ── 阿里云 OSS 配置（留空则跳过上传）──────────────────────────────────────────
OSS_ACCESS_KEY_ID     = os.environ.get("OSS_ACCESS_KEY_ID",     "")
OSS_ACCESS_KEY_SECRET = os.environ.get("OSS_ACCESS_KEY_SECRET", "")
OSS_ENDPOINT          = os.environ.get("OSS_ENDPOINT",          "https://oss-cn-hangzhou.aliyuncs.com")
OSS_BUCKET_NAME       = os.environ.get("OSS_BUCKET_NAME",       "")
OSS_PREFIX            = os.environ.get("OSS_PREFIX",            "rp_archive/backups/")

# ── 日志 ──────────────────────────────────────────────────────────────────────
log_dir = os.path.join(_BASE_DIR, "logs")
os.makedirs(log_dir, exist_ok=True)
_handler = logging.FileHandler(os.path.join(log_dir, "backup.log"), encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger = logging.getLogger("rp_backup")
logger.setLevel(logging.INFO)
logger.addHandler(_handler)


# ─────────────────────────────────────────────────────────────────────────────
# 核心备份逻辑
# ─────────────────────────────────────────────────────────────────────────────

def _make_backup() -> str:
    """
    用 SQLite 在线备份 API 安全复制数据库，再 gzip 压缩。
    返回压缩后的文件路径。
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp     = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path  = os.path.join(BACKUP_DIR, f"rp_data_{stamp}.db")
    gz_path   = raw_path + ".gz"

    # sqlite3.backup() 是线程安全的在线热备份，不会损坏正在写入的数据库
    src  = sqlite3.connect(DB_PATH)
    dest = sqlite3.connect(raw_path)
    try:
        src.backup(dest)
    finally:
        dest.close()
        src.close()

    # gzip 压缩（通常可压缩至原始大小的 20-40%）
    with open(raw_path, "rb") as f_in, gzip.open(gz_path, "wb", compresslevel=6) as f_out:
        shutil.copyfileobj(f_in, f_out)
    os.remove(raw_path)

    size_kb = os.path.getsize(gz_path) // 1024
    logger.info("备份完成：%s（%d KB）", gz_path, size_kb)
    return gz_path


def _cleanup_local():
    """删除超过 LOCAL_KEEP 份的旧备份文件。"""
    try:
        files = sorted(
            [f for f in os.listdir(BACKUP_DIR) if f.endswith(".db.gz")],
            reverse=True  # 最新在前
        )
        for old in files[LOCAL_KEEP:]:
            path = os.path.join(BACKUP_DIR, old)
            os.remove(path)
            logger.info("已清理旧备份：%s", old)
    except Exception as e:
        logger.warning("清理本地备份失败：%s", e)


def _upload_to_oss(gz_path: str):
    """
    上传到阿里云 OSS。
    需要安装：pip install oss2
    配置好 OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET / OSS_ENDPOINT / OSS_BUCKET_NAME 后自动生效。
    """
    if not all([OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET, OSS_BUCKET_NAME]):
        logger.info("OSS 未配置，跳过云端上传（填写环境变量即可启用）")
        return

    try:
        import oss2  # pip install oss2
    except ImportError:
        logger.warning("未安装 oss2，跳过上传。运行 pip install oss2 后重启即可启用。")
        return

    try:
        auth   = oss2.Auth(OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET)
        bucket = oss2.Bucket(auth, OSS_ENDPOINT, OSS_BUCKET_NAME)

        object_name = OSS_PREFIX + os.path.basename(gz_path)
        bucket.put_object_from_file(object_name, gz_path)

        size_kb = os.path.getsize(gz_path) // 1024
        logger.info("已上传至 OSS：oss://%s/%s（%d KB）", OSS_BUCKET_NAME, object_name, size_kb)

        # OSS 端保留最近 30 天，自动删除更早的（可选，需要 OSS 控制台设置生命周期规则代替）
    except Exception as e:
        logger.error("OSS 上传失败：%s", e)


def run_backup():
    """执行一次完整备份流程（可手动调用测试）。"""
    logger.info("=== 开始备份 ===")
    try:
        gz_path = _make_backup()
        _cleanup_local()
        _upload_to_oss(gz_path)
        logger.info("=== 备份完成 ===")
    except Exception as e:
        logger.error("备份流程异常：%s", e, exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# 定时调度（threading 守护线程，不阻塞主线程）
# ─────────────────────────────────────────────────────────────────────────────

_BACKUP_HOUR   = 3   # 每天 03:00 触发
_BACKUP_MINUTE = 0

def _seconds_until_next_run() -> float:
    """计算到下次 03:00 还有多少秒。"""
    now  = datetime.now()
    next_run = now.replace(hour=_BACKUP_HOUR, minute=_BACKUP_MINUTE, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    return (next_run - now).total_seconds()


def _scheduler_loop():
    logger.info("备份调度器已启动，下次备份时间：%s",
                datetime.now().replace(hour=_BACKUP_HOUR, minute=_BACKUP_MINUTE,
                                       second=0, microsecond=0).strftime("%H:%M"))
    while True:
        wait = _seconds_until_next_run()
        logger.info("距下次备份还有 %.0f 分钟", wait / 60)
        time.sleep(wait)
        run_backup()


_scheduler_started = False
_scheduler_lock    = threading.Lock()

def start_scheduler():
    """
    在 Flask 启动时调用一次。
    使用锁防止 debug=True 的 reloader 启动两个线程。
    """
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        # 仅在主进程中启动（Werkzeug reloader 子进程会设置此环境变量）
        if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not os.environ.get("WERKZEUG_RUN_MAIN"):
            t = threading.Thread(target=_scheduler_loop, name="backup-scheduler", daemon=True)
            t.start()
            _scheduler_started = True
            logger.info("备份守护线程已启动（每天 %02d:%02d 执行）", _BACKUP_HOUR, _BACKUP_MINUTE)

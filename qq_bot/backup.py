"""哈利波特系统每日存档：用SQLite在线备份API把hogwarts.db安全复制一份并压缩，
本地只留最近 LOCAL_KEEP 份，更早的自动清理。

真正的定时触发在 plugins/hp_school/__init__.py 里用 nonebot_plugin_apscheduler
挂了个每天固定时间的cron任务，这个模块只管"怎么备份"，不管"什么时候备份"。
"""

from __future__ import annotations

import gzip
import logging
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(
    os.getenv("HOGWARTS_DB_PATH", Path(__file__).resolve().parent / "data" / "hogwarts.db")
)
BACKUP_DIR = DB_PATH.parent / "backups"
LOCAL_KEEP = 3  # 本地保留最近3份，超过的自动清理

logger = logging.getLogger("hogwarts_backup")


def make_backup() -> Path:
    """用SQLite在线备份API安全复制数据库（不影响正在写入的连接），再gzip压缩。"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = BACKUP_DIR / f"hogwarts_{stamp}.db"
    gz_path = raw_path.with_name(raw_path.name + ".gz")

    src = sqlite3.connect(DB_PATH)
    dest = sqlite3.connect(raw_path)
    try:
        src.backup(dest)
    finally:
        dest.close()
        src.close()

    with open(raw_path, "rb") as f_in, gzip.open(gz_path, "wb", compresslevel=6) as f_out:
        shutil.copyfileobj(f_in, f_out)
    raw_path.unlink()

    logger.info("哈利波特系统存档完成：%s（%d KB）", gz_path, gz_path.stat().st_size // 1024)
    return gz_path


def cleanup_old_backups() -> None:
    """删除超过 LOCAL_KEEP 份的旧存档，按文件名（含时间戳）排序取最新的一批。"""
    files = sorted(BACKUP_DIR.glob("hogwarts_*.db.gz"), reverse=True)
    for old in files[LOCAL_KEEP:]:
        old.unlink()
        logger.info("已清理旧存档：%s", old.name)


def run_backup() -> None:
    """执行一次完整存档流程（新建+清理旧份）。定时任务和手动测试都调这个。"""
    try:
        make_backup()
        cleanup_old_backups()
    except Exception:
        logger.exception("哈利波特系统存档失败")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_backup()

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "jiuxiao_notify.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def _get(key: str) -> str | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row is not None else None
    finally:
        conn.close()


def _set(key: str, value: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def get_config() -> tuple[str | None, str | None]:
    """返回 (base_url, token)，任一未配置则为 None。"""
    return _get("base_url"), _get("token")


def set_config(base_url: str, token: str) -> None:
    _set("base_url", base_url.rstrip("/"))
    _set("token", token)


def get_group_openid() -> str | None:
    return _get("group_openid")


def set_group_openid(group_openid: str) -> None:
    _set("group_openid", group_openid)


def get_last_id() -> int:
    val = _get("last_id")
    return int(val) if val else 0


def set_last_id(last_id: int) -> None:
    _set("last_id", str(last_id))

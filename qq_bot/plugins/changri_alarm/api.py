import time

from .storage import get_conn, init_db

init_db()

MAX_REMINDERS_PER_USER = 20


def count_reminders(platform: str, uid: str) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM reminders WHERE platform = ? AND uid = ?",
            (platform, uid),
        ).fetchone()
        return row["c"]
    finally:
        conn.close()


def add_reminder(
    platform: str, uid: str, group_openid: str, trigger_at: int, content: str, repeat: str
) -> int:
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO reminders (platform, uid, group_openid, trigger_at, content, repeat, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (platform, uid, group_openid, trigger_at, content, repeat, int(time.time())),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_reminders(platform: str, uid: str) -> list:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM reminders WHERE platform = ? AND uid = ? ORDER BY trigger_at",
            (platform, uid),
        ).fetchall()
        return rows
    finally:
        conn.close()


def delete_reminder(platform: str, uid: str, reminder_id: int) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM reminders WHERE id = ? AND platform = ? AND uid = ?",
            (reminder_id, platform, uid),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_due_reminders(now_ts: int) -> list:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM reminders WHERE trigger_at <= ?", (now_ts,)
        ).fetchall()
        return rows
    finally:
        conn.close()


def reschedule_reminder(reminder_id: int, next_trigger_at: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE reminders SET trigger_at = ? WHERE id = ?", (next_trigger_at, reminder_id)
        )
        conn.commit()
    finally:
        conn.close()


def remove_reminder_by_id(reminder_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        conn.commit()
    finally:
        conn.close()


def increment_fail_count(reminder_id: int) -> int:
    conn = get_conn()
    try:
        conn.execute("UPDATE reminders SET fail_count = fail_count + 1 WHERE id = ?", (reminder_id,))
        row = conn.execute("SELECT fail_count FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        conn.commit()
        return row["fail_count"] if row is not None else 0
    finally:
        conn.close()


def reset_fail_count(reminder_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute("UPDATE reminders SET fail_count = 0 WHERE id = ?", (reminder_id,))
        conn.commit()
    finally:
        conn.close()


def set_last_fired(platform: str, uid: str, group_openid: str, content: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO last_fired (platform, uid, group_openid, content, fired_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (platform, uid) DO UPDATE SET
                group_openid = excluded.group_openid,
                content = excluded.content,
                fired_at = excluded.fired_at
            """,
            (platform, uid, group_openid, content, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def get_last_fired(platform: str, uid: str):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM last_fired WHERE platform = ? AND uid = ?", (platform, uid)
        ).fetchone()
    finally:
        conn.close()

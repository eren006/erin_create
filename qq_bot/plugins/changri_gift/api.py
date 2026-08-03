import time
from datetime import date

from plugins.changri_core.api import add_notification, get_primary_uid, get_role_name, get_setting_int, get_uid_by_role_name
from plugins.changri_core.archive_client import post_to_archive

from .storage import get_conn, init_db

init_db()

DEFAULT_DAILY_LIMIT = 10
DEFAULT_COOLDOWN_SECONDS = 30


def _today() -> str:
    return date.today().isoformat()


def add_preset_gift(platform: str, name: str, desc: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO preset_gifts (platform, name, desc) VALUES (?, ?, ?)
            ON CONFLICT (platform, name) DO UPDATE SET desc = excluded.desc
            """,
            (platform, name, desc),
        )
        conn.commit()
    finally:
        conn.close()


def list_preset_gifts(platform: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM preset_gifts WHERE platform = ? ORDER BY name", (platform,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _get_day_count(platform: str, uid: str) -> dict:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM gift_day_counts WHERE platform = ? AND uid = ? AND day = ?",
            (platform, uid, _today()),
        ).fetchone()
        return dict(row) if row is not None else {"count": 0, "last_send_time": 0}
    finally:
        conn.close()


def can_send_gift(platform: str, uid: str) -> tuple[bool, str]:
    limit = get_setting_int("gift_daily_limit", DEFAULT_DAILY_LIMIT)
    cooldown = get_setting_int("gift_cooldown_seconds", DEFAULT_COOLDOWN_SECONDS)
    day_count = _get_day_count(platform, uid)
    if day_count["count"] >= limit:
        return False, f"今天已经送了 {limit} 次礼物，明天再来吧"
    remaining = cooldown - (int(time.time()) - day_count["last_send_time"])
    if remaining > 0:
        return False, f"送礼太频繁，还要等 {remaining} 秒"
    return True, ""


def _record_send(platform: str, uid: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO gift_day_counts (platform, uid, day, count, last_send_time)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT (platform, uid, day) DO UPDATE SET
                count = count + 1, last_send_time = excluded.last_send_time
            """,
            (platform, uid, _today(), int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def _unlock_gift(platform: str, uid: str, gift_name: str) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO gift_sightings (platform, uid, gift_name, first_seen_at) VALUES (?, ?, ?, ?)",
            (platform, uid, gift_name, int(time.time())),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


async def send_gift(platform: str, from_uid: str, to_role_name: str, gift_content: str) -> tuple[bool, str]:
    from_uid = get_primary_uid(platform, from_uid)
    from_role = get_role_name(platform, from_uid)
    if from_role is None:
        return False, "你还没有角色，先创建新角色"
    to_uid = get_uid_by_role_name(platform, to_role_name)
    if to_uid is None:
        return False, f"找不到角色「{to_role_name}」"
    if to_uid == from_uid:
        return False, "不能送礼给自己"
    ok, msg = can_send_gift(platform, from_uid)
    if not ok:
        return False, msg
    if not gift_content.strip():
        return False, "送的什么礼物不能空着"

    _record_send(platform, from_uid)
    is_new = _unlock_gift(platform, to_uid, gift_content)

    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO preset_gifts (platform, name, usage_count) VALUES (?, ?, 1)
            ON CONFLICT (platform, name) DO UPDATE SET usage_count = usage_count + 1
            """,
            (platform, gift_content),
        )
        conn.commit()
    finally:
        conn.close()

    await post_to_archive(
        "/api/event",
        {
            "type": "gift",
            "from_role": from_role,
            "from_qq": from_uid,
            "to_role": to_role_name,
            "to_qq": to_uid,
            "content": gift_content,
            "timestamp": int(time.time() * 1000),
        },
    )
    add_notification(platform, to_uid, "礼物", f"{from_role} 送了你：{gift_content}")
    new_msg = "（新图鉴解锁！）" if is_new else ""
    return True, f"礼物已送出{new_msg}"


def get_catalog(platform: str, uid: str) -> list[dict]:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM gift_sightings WHERE platform = ? AND uid = ? ORDER BY first_seen_at",
            (platform, uid),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


PENDING_GIFT_TTL_SECONDS = 300


def set_pending_gift(platform: str, uid: str, content: str) -> None:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO pending_gift (platform, uid, content, created_at) VALUES (?, ?, ?, ?)
            ON CONFLICT (platform, uid) DO UPDATE SET content = excluded.content, created_at = excluded.created_at
            """,
            (platform, uid, content, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def pop_pending_gift(platform: str, uid: str) -> str | None:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT content, created_at FROM pending_gift WHERE platform = ? AND uid = ?", (platform, uid)
        ).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM pending_gift WHERE platform = ? AND uid = ?", (platform, uid))
        conn.commit()
        if int(time.time()) - row["created_at"] > PENDING_GIFT_TTL_SECONDS:
            return None
        return row["content"]
    finally:
        conn.close()

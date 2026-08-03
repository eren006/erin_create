import time
from datetime import date

from plugins.changri_core.api import (
    add_notification,
    get_current_day,
    get_primary_uid,
    get_role_name,
    get_setting,
    get_setting_int,
    set_setting,
)
from plugins.changri_core.archive_client import post_to_archive
from plugins.changri_rpg.api import add_to_inventory, find_item_by_name

from .storage import get_conn, init_db

init_db()

DEFAULTS = {
    "letter_daily_limit": 10,
    "letter_reward": 3,
    "letter_min_chars": 50,
    "letter_cooldown_seconds": 60,
}


def get_config() -> dict:
    return {k: get_setting_int(k, v) for k, v in DEFAULTS.items()}


def set_config(**kwargs) -> None:
    for key, value in kwargs.items():
        if key in DEFAULTS:
            set_setting(key, str(value))


def _today() -> str:
    return date.today().isoformat()


def get_day_count(platform: str, uid: str) -> dict:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM letter_day_counts WHERE platform = ? AND uid = ? AND day = ?",
            (platform, uid, _today()),
        ).fetchone()
        return dict(row) if row is not None else {"count": 0, "last_send_time": 0}
    finally:
        conn.close()


def can_send_letter(platform: str, uid: str) -> tuple[bool, str]:
    config = get_config()
    day_count = get_day_count(platform, uid)
    if day_count["count"] >= config["letter_daily_limit"]:
        return False, f"今天已经发了 {config['letter_daily_limit']} 封信，明天再来吧"
    remaining_cooldown = config["letter_cooldown_seconds"] - (int(time.time()) - day_count["last_send_time"])
    if remaining_cooldown > 0:
        return False, f"发信太频繁，还要等 {remaining_cooldown} 秒"
    return True, ""


def _record_send(platform: str, uid: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO letter_day_counts (platform, uid, day, count, last_send_time)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT (platform, uid, day) DO UPDATE SET
                count = count + 1, last_send_time = excluded.last_send_time
            """,
            (platform, uid, _today(), int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


ITEM_EFFECT_MAP = {"望远镜": "telescope", "羽毛笔": "quill_pen"}


def apply_effect(platform: str, applier_uid: str, target_role_name: str, item_name: str) -> tuple[bool, str]:
    applier_uid = get_primary_uid(platform, applier_uid)
    item_type = ITEM_EFFECT_MAP.get(item_name)
    if item_type is None:
        return False, "只有望远镜/羽毛笔能这样用"
    from plugins.changri_core.api import get_uid_by_role_name

    target_uid = get_uid_by_role_name(platform, target_role_name)
    if target_uid is None:
        return False, f"找不到角色「{target_role_name}」"
    if target_uid == applier_uid:
        return False, "不能对自己使用"
    item = find_item_by_name(platform, item_name)
    if item is None:
        return False, f"找不到物品「{item_name}」"

    from plugins.changri_rpg.api import remove_from_inventory

    if not remove_from_inventory(platform, applier_uid, item["code"], 1):
        return False, f"背包里没有{item_name}了"
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO letter_effects (platform, target_uid, item_type, applier_uid, applied_at) VALUES (?, ?, ?, ?, ?)",
            (platform, target_uid, item_type, applier_uid, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()
    return True, f"{item_name}已生效，会作用在{target_role_name}下一封发出的信上"


def _get_active_effect(platform: str, target_uid: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT * FROM letter_effects WHERE platform = ? AND target_uid = ?
            ORDER BY (item_type = 'quill_pen') DESC, applied_at ASC LIMIT 1
            """,
            (platform, target_uid),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def _consume_effect(effect_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM letter_effects WHERE id = ?", (effect_id,))
        conn.commit()
    finally:
        conn.close()


def list_pending_quill(platform: str, applier_uid: str) -> list[dict]:
    applier_uid = get_primary_uid(platform, applier_uid)
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM pending_quill_letters WHERE platform = ? AND applier_uid = ? AND status = 'pending' ORDER BY created_at",
            (platform, applier_uid),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def release_pending_quill(platform: str, applier_uid: str, pending_id: int, new_content: str) -> tuple[bool, str]:
    applier_uid = get_primary_uid(platform, applier_uid)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM pending_quill_letters WHERE id = ? AND platform = ? AND applier_uid = ? AND status = 'pending'",
            (pending_id, platform, applier_uid),
        ).fetchone()
        if row is None:
            conn.close()
            return False, "找不到这封待修改的信"
        conn.execute("UPDATE pending_quill_letters SET status = 'released' WHERE id = ?", (pending_id,))
        conn.execute(
            "INSERT INTO letters (platform, from_uid, to_uid, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (platform, row["original_from_uid"], row["original_to_uid"], new_content, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()
    return True, "信件已修改并送出"


async def send_letter(platform: str, from_uid: str, to_uid: str, content: str) -> tuple[bool, str]:
    from_uid = get_primary_uid(platform, from_uid)
    to_uid = get_primary_uid(platform, to_uid)
    if not content.strip():
        return False, "信件内容不能为空"
    ok, msg = can_send_letter(platform, from_uid)
    if not ok:
        return False, msg

    effect = _get_active_effect(platform, from_uid)
    deliver_normally = True
    cc_uid = None
    if effect is not None and effect["applier_uid"] != to_uid:
        if effect["item_type"] == "quill_pen":
            deliver_normally = False
        else:
            cc_uid = effect["applier_uid"]
        _consume_effect(effect["id"])

    conn = get_conn()
    try:
        if deliver_normally:
            conn.execute(
                "INSERT INTO letters (platform, from_uid, to_uid, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (platform, from_uid, to_uid, content, int(time.time())),
            )
        else:
            conn.execute(
                """
                INSERT INTO pending_quill_letters (platform, applier_uid, original_from_uid, original_to_uid, content, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                (platform, effect["applier_uid"], from_uid, to_uid, content, int(time.time())),
            )
        if cc_uid:
            conn.execute(
                "INSERT INTO letters (platform, from_uid, to_uid, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (platform, from_uid, cc_uid, content, int(time.time())),
            )
        conn.commit()
    finally:
        conn.close()
    _record_send(platform, from_uid)
    reward_msg = ""
    config = get_config()
    if len(content) >= config["letter_min_chars"] and config["letter_reward"] > 0:
        currency = find_item_by_name(platform, "写信币")
        if currency is not None:
            add_to_inventory(platform, from_uid, currency["code"], config["letter_reward"])
            reward_msg = f"，获得 {config['letter_reward']} 写信币"
    await post_to_archive(
        "/api/event",
        {
            "type": "direct_letter",
            "from_role": get_role_name(platform, from_uid) or from_uid,
            "from_qq": from_uid,
            "to_role": get_role_name(platform, to_uid) or to_uid,
            "to_qq": to_uid,
            "content": content,
            "game_day": get_current_day(platform) or "",
            "timestamp": int(time.time() * 1000),
        },
    )
    return True, f"信件已送出{reward_msg}"


def get_inbox(platform: str, uid: str, unread_only: bool = False) -> list[dict]:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        query = "SELECT * FROM letters WHERE platform = ? AND to_uid = ?"
        if unread_only:
            query += " AND read_at IS NULL"
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, (platform, uid)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_read(letter_ids: list[int]) -> None:
    if not letter_ids:
        return
    conn = get_conn()
    try:
        conn.executemany(
            "UPDATE letters SET read_at = ? WHERE id = ? AND read_at IS NULL",
            [(int(time.time()), lid) for lid in letter_ids],
        )
        conn.commit()
    finally:
        conn.close()


async def send_sms(
    platform: str, from_uid: str, to_uid: str, content: str, signature: str | None = None
) -> tuple[bool, str]:
    from_uid = get_primary_uid(platform, from_uid)
    to_uid = get_primary_uid(platform, to_uid)
    if not content.strip():
        return False, "短信内容不能为空"
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO sms_messages (platform, from_uid, to_uid, signature, content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (platform, from_uid, to_uid, signature, content, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()
    from_display = signature or get_role_name(platform, from_uid) or from_uid
    add_notification(platform, to_uid, "短信", f"{from_display}：{content}")
    await post_to_archive(
        "/api/event",
        {
            "type": "sms",
            "from_role": signature or get_role_name(platform, from_uid) or from_uid,
            "from_qq": from_uid,
            "to_role": get_role_name(platform, to_uid) or to_uid,
            "to_qq": to_uid,
            "content": content,
            "game_day": get_current_day(platform) or "",
            "timestamp": int(time.time() * 1000),
        },
    )
    return True, "短信已发送"


def get_sms_inbox(platform: str, uid: str, unread_only: bool = False) -> list[dict]:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        query = "SELECT * FROM sms_messages WHERE platform = ? AND to_uid = ?"
        if unread_only:
            query += " AND read_at IS NULL"
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, (platform, uid)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_sms_read(sms_ids: list[int]) -> None:
    if not sms_ids:
        return
    conn = get_conn()
    try:
        conn.executemany(
            "UPDATE sms_messages SET read_at = ? WHERE id = ? AND read_at IS NULL",
            [(int(time.time()), sid) for sid in sms_ids],
        )
        conn.commit()
    finally:
        conn.close()


PENDING_SMS_TTL_SECONDS = 300


def set_pending_sms(platform: str, uid: str, content: str) -> None:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO pending_sms (platform, uid, content, created_at) VALUES (?, ?, ?, ?)
            ON CONFLICT (platform, uid) DO UPDATE SET content = excluded.content, created_at = excluded.created_at
            """,
            (platform, uid, content, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def pop_pending_sms(platform: str, uid: str) -> str | None:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT content, created_at FROM pending_sms WHERE platform = ? AND uid = ?", (platform, uid)
        ).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM pending_sms WHERE platform = ? AND uid = ?", (platform, uid))
        conn.commit()
        if int(time.time()) - row["created_at"] > PENDING_SMS_TTL_SECONDS:
            return None
        return row["content"]
    finally:
        conn.close()

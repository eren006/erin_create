import time
from datetime import date

from plugins.changri_core.api import get_current_day, get_primary_uid, get_role_name, get_setting_int, get_uid_by_role_name
from plugins.changri_core.timeutils import parse_and_validate_time
from plugins.changri_rpg.api import add_to_inventory, find_item_by_name, get_item_count, remove_from_inventory

from .storage import get_conn, init_db

init_db()

DEFAULT_POST_LIMIT = 3
DEFAULT_PICK_LIMIT = 3


def _today() -> str:
    return date.today().isoformat()


def _get_count(platform: str, uid: str, action: str) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT count FROM wish_day_counts WHERE platform = ? AND uid = ? AND day = ? AND action = ?",
            (platform, uid, _today(), action),
        ).fetchone()
        return row["count"] if row is not None else 0
    finally:
        conn.close()


def _incr_count(platform: str, uid: str, action: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO wish_day_counts (platform, uid, day, action, count) VALUES (?, ?, ?, ?, 1)
            ON CONFLICT (platform, uid, day, action) DO UPDATE SET count = count + 1
            """,
            (platform, uid, _today(), action),
        )
        conn.commit()
    finally:
        conn.close()


def post_wish(
    platform: str,
    from_uid: str,
    place: str,
    time_range: str,
    content: str,
    day: str | None = None,
    reward_item_name: str | None = None,
    reward_count: int = 0,
) -> tuple[bool, str]:
    from_uid = get_primary_uid(platform, from_uid)
    if get_role_name(platform, from_uid) is None:
        return False, "你还没有角色，先创建新角色"
    if _get_count(platform, from_uid, "post") >= get_setting_int("wish_daily_post_limit", DEFAULT_POST_LIMIT):
        return False, "今天挂的心愿已经够多了，明天再来"
    if not content.strip():
        return False, "心愿内容不能为空"

    day = day or get_current_day(platform)
    if not day:
        return False, "还没有设置当前天数，先让管理员「/设置天数」"

    ok, result = parse_and_validate_time(time_range, min_duration=0)
    if not ok:
        return False, result
    time_range = result

    reward_code = None
    if reward_item_name:
        item = find_item_by_name(platform, reward_item_name)
        if item is None:
            return False, f"找不到物品「{reward_item_name}」"
        if reward_count <= 0:
            return False, "悬赏数量要大于0"
        if get_item_count(platform, from_uid, item["code"]) < reward_count:
            return False, f"你的{reward_item_name}不够，凑不齐这份悬赏"
        remove_from_inventory(platform, from_uid, item["code"], reward_count)
        reward_code = item["code"]

    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO wishes (platform, from_uid, day, time_range, place, content, reward_code, reward_count, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (platform, from_uid, day, time_range, place, content, reward_code, reward_count or None, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()
    _incr_count(platform, from_uid, "post")
    reward_msg = f"（悬赏 {reward_count} {reward_item_name}）" if reward_code else ""
    return True, f"心愿已挂出{reward_msg}"


def list_wishes(platform: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM wishes WHERE platform = ? AND status = 'open' ORDER BY id", (platform,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_wish(platform: str, wish_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM wishes WHERE id = ? AND platform = ?", (wish_id, platform)
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def withdraw_wish(platform: str, uid: str, wish_id: int) -> tuple[bool, str]:
    uid = get_primary_uid(platform, uid)
    wish = get_wish(platform, wish_id)
    if wish is None or wish["status"] != "open":
        return False, "找不到这个心愿"
    if wish["from_uid"] != uid:
        return False, "只能撤回自己的心愿"
    conn = get_conn()
    try:
        conn.execute("UPDATE wishes SET status = 'withdrawn' WHERE id = ?", (wish_id,))
        conn.commit()
    finally:
        conn.close()
    if wish["reward_code"]:
        add_to_inventory(platform, uid, wish["reward_code"], wish["reward_count"])
    return True, "心愿已撤回" + ("，悬赏物品已退回背包" if wish["reward_code"] else "")


def expire_open_wishes(platform: str) -> int:
    """换天时清空心愿池：未被摘的心愿全部作废，托管的悬赏物品退回发布者背包。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM wishes WHERE platform = ? AND status = 'open'", (platform,)
        ).fetchall()
        conn.execute("UPDATE wishes SET status = 'expired' WHERE platform = ? AND status = 'open'", (platform,))
        conn.commit()
    finally:
        conn.close()
    for wish in rows:
        if wish["reward_code"]:
            add_to_inventory(platform, wish["from_uid"], wish["reward_code"], wish["reward_count"])
    return len(rows)


async def pick_wish(platform: str, picker_uid: str, wish_id: int) -> tuple[bool, str, dict | None]:
    picker_uid = get_primary_uid(platform, picker_uid)
    picker_role = get_role_name(platform, picker_uid)
    if picker_role is None:
        return False, "你还没有角色，先创建新角色", None
    wish = get_wish(platform, wish_id)
    if wish is None or wish["status"] != "open":
        return False, "找不到这个心愿，可能已经被摘走了", None
    if wish["from_uid"] == picker_uid:
        return False, "不能摘自己的心愿", None
    if _get_count(platform, picker_uid, "pick") >= get_setting_int("wish_daily_pick_limit", DEFAULT_PICK_LIMIT):
        return False, "今天摘的心愿已经够多了，明天再来", None

    from plugins.changri_appointment.api import create_appointment

    ok, msg, extra = create_appointment(
        platform, wish["from_uid"], picker_role, wish["day"], wish["time_range"], "心愿", wish["place"]
    )
    if not ok:
        return False, f"摘心愿失败：{msg}", None

    conn = get_conn()
    try:
        conn.execute("UPDATE wishes SET status = 'picked' WHERE id = ?", (wish_id,))
        conn.commit()
    finally:
        conn.close()
    _incr_count(platform, picker_uid, "pick")

    reward_msg = ""
    if wish["reward_code"]:
        add_to_inventory(platform, picker_uid, wish["reward_code"], wish["reward_count"])
        reward_msg = f"，获得悬赏 {wish['reward_count']} 个物品"

    return True, f"心愿摘取成功{reward_msg}，戏群已分配", extra

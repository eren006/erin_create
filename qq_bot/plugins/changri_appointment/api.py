import time

from plugins.changri_core.api import add_notification, get_char_profile, get_current_day, get_primary_uid, get_role_name
from plugins.changri_core.archive_client import post_to_archive
from plugins.changri_core.timeutils import parse_and_validate_time, time_conflict

from .storage import get_conn, init_db

init_db()

MIN_DURATION = {"电话": 29, "私约": 59, "约战": 59}


def register_group(platform: str, group_openid: str, label: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO group_pool (platform, group_openid, label) VALUES (?, ?, ?)
            ON CONFLICT (platform, group_openid) DO UPDATE SET label = excluded.label
            """,
            (platform, group_openid, label),
        )
        conn.commit()
    finally:
        conn.close()


def list_groups(platform: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM group_pool WHERE platform = ? ORDER BY label", (platform,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _allocate_group(conn, platform: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM group_pool WHERE platform = ? AND occupied = 0 LIMIT 1", (platform,)
    ).fetchone()
    return dict(row) if row is not None else None


def free_group(platform: str, group_openid: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE group_pool SET occupied = 0, occupied_by = NULL WHERE platform = ? AND group_openid = ?",
            (platform, group_openid),
        )
        conn.commit()
    finally:
        conn.close()


def _get_active_appointments(platform: str, uid: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT a.* FROM appointments a
            JOIN appointment_participants p ON p.appointment_id = a.id
            WHERE a.platform = ? AND p.uid = ? AND a.status = 'active'
            """,
            (platform, uid),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_appointment(
    platform: str, initiator_uid: str, partner_role_name: str, day: str | None, time_range: str, subtype: str, place: str | None
) -> tuple[bool, str, dict | None]:
    initiator_uid = get_primary_uid(platform, initiator_uid)
    if get_role_name(platform, initiator_uid) is None:
        return False, "你还没有角色，先创建新角色", None

    from plugins.changri_core.api import get_uid_by_role_name

    partner_uid = get_uid_by_role_name(platform, partner_role_name)
    if partner_uid is None:
        return False, f"找不到角色「{partner_role_name}」", None
    if partner_uid == initiator_uid:
        return False, "不能和自己邀约", None

    day = day or get_current_day(platform)
    if not day:
        return False, "还没有设置当前天数，先让管理员「/设置天数」", None

    ok, result = parse_and_validate_time(time_range, min_duration=MIN_DURATION.get(subtype, 59))
    if not ok:
        return False, result, None
    time_range = result

    if subtype != "电话":
        if not place:
            return False, "这个类型需要指定地点", None
        from plugins.changri_core.api import check_place_access

        allowed, reason = check_place_access(platform, initiator_uid, place)
        if not allowed:
            return False, f"地点不可用：{reason}", None

    for uid, label in ((initiator_uid, "你自己"), (partner_uid, "对方")):
        for existing in _get_active_appointments(platform, uid):
            if time_conflict(day, time_range, existing["day"], existing["time_range"]):
                return False, f"{label}在这个时段已经有约会了", None

    conn = get_conn()
    try:
        group = _allocate_group(conn, platform)
        if group is None:
            conn.close()
            return False, "没有空闲的戏群了，找管理员用「/注册戏群」加一个", None
        now = int(time.time())
        cur = conn.execute(
            """
            INSERT INTO appointments
                (platform, initiator_uid, day, time_range, subtype, place, group_openid, status, created_at, last_reply_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (platform, initiator_uid, day, time_range, subtype, place, group["group_openid"], now, now),
        )
        appointment_id = cur.lastrowid
        conn.execute(
            "UPDATE group_pool SET occupied = 1, occupied_by = ? WHERE platform = ? AND group_openid = ?",
            (appointment_id, platform, group["group_openid"]),
        )
        conn.executemany(
            "INSERT INTO appointment_participants (appointment_id, uid, role) VALUES (?, ?, ?)",
            [(appointment_id, initiator_uid, "initiator"), (appointment_id, partner_uid, "partner")],
        )
        conn.commit()
    finally:
        conn.close()

    initiator_role = get_role_name(platform, initiator_uid)
    place_desc = f"，地点：{place}" if place else ""
    announce = f"【{subtype}】{initiator_role} 与 {partner_role_name}\n天数：{day}　时段：{time_range}{place_desc}\n本群已分配给这场戏使用"

    detail = f"{initiator_role} 与 {partner_role_name}　天数：{day}　时段：{time_range}{place_desc}"
    add_notification(platform, initiator_uid, "邀约", f"【{subtype}】{detail}")
    add_notification(platform, partner_uid, "邀约", f"【{subtype}】{detail}")

    return True, f"{subtype}已创建，天数 {day}，时段 {time_range}", {
        "appointment_id": appointment_id,
        "group_openid": group["group_openid"],
        "announce": announce,
    }


def get_my_active_appointments(platform: str, uid: str) -> list[dict]:
    uid = get_primary_uid(platform, uid)
    return _get_active_appointments(platform, uid)


def get_role_timeline(
    platform: str, uid: str, page: int, days_per_page: int
) -> tuple[list[dict], int, int]:
    """返回 (当前页的天分组列表, 总页数, 实际页码)。按天分组，最新的天在前。"""
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT a.* FROM appointments a
            JOIN appointment_participants p ON p.appointment_id = a.id
            WHERE a.platform = ? AND p.uid = ?
            ORDER BY a.created_at DESC
            """,
            (platform, uid),
        ).fetchall()
        day_order: list[str] = []
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            day = row["day"]
            if day not in grouped:
                grouped[day] = []
                day_order.append(day)
            partner_row = conn.execute(
                "SELECT uid FROM appointment_participants WHERE appointment_id = ? AND uid != ?",
                (row["id"], uid),
            ).fetchone()
            partner_role = get_role_name(platform, partner_row["uid"]) if partner_row else "未知"
            grouped[day].append(
                {
                    "subtype": row["subtype"],
                    "time_range": row["time_range"],
                    "place": row["place"],
                    "partner_role": partner_role or "未知",
                    "status": row["status"],
                }
            )
    finally:
        conn.close()

    total_pages = max(1, (len(day_order) + days_per_page - 1) // days_per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * days_per_page
    page_days = day_order[start : start + days_per_page]
    result = [{"day": d, "items": grouped[d]} for d in page_days]
    return result, total_pages, page


def get_session_id(appointment: dict) -> str:
    return f"{appointment['id']}_{appointment['created_at']}"


def _get_session_stats(appointment_id: int) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM session_stats WHERE appointment_id = ?", (appointment_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _extract_role_content(message: str, role_name: str) -> str | None:
    """握手格式：消息首行须以"角色名+分隔符"开头，提取分隔符之后的正文。
    支持「角色名\\n正文」「角色名 正文」「角色名：正文」（半角/全角冒号）。不匹配则视为闲聊，返回 None。"""
    lines = message.split("\n")
    first = lines[0].strip()
    rest = "\n".join(lines[1:]).strip()
    if first == role_name:
        return rest or None
    if not first.startswith(role_name):
        return None
    tail = first[len(role_name) :]
    before_len = len(tail)
    tail = tail.lstrip(" :：")
    if len(tail) == before_len:
        return None  # 名字后没有分隔符，可能是别的角色名的前缀
    combined = (tail.strip() + ("\n" + rest if rest else "")).strip()
    return combined or None


async def record_rp_reply(platform: str, group_openid: str, uid: str, message: str) -> bool:
    appointment = get_appointment_by_group(platform, group_openid)
    if appointment is None:
        return False
    uid = get_primary_uid(platform, uid)
    role_name = get_role_name(platform, uid) or uid
    content = _extract_role_content(message, role_name)
    if content is None:
        return False
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO session_stats (appointment_id, uid, role_name, replies, words)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT (appointment_id, uid) DO UPDATE SET
                replies = replies + 1, words = words + excluded.words, role_name = excluded.role_name
            """,
            (appointment["id"], uid, role_name, len(content)),
        )
        conn.execute(
            "UPDATE appointments SET last_reply_at = ?, last_reminded_at = NULL WHERE id = ?",
            (int(time.time()), appointment["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    session_id = get_session_id(appointment)
    now_ms = int(time.time() * 1000)
    await post_to_archive(
        "/api/rp",
        {
            "session_id": session_id,
            "role_name": role_name,
            "content": content,
            "game_day": appointment["day"],
            "subtype": appointment["subtype"],
            "timestamp": now_ms,
        },
    )
    stats = {s["role_name"]: {"replies": s["replies"], "words": s["words"]} for s in _get_session_stats(appointment["id"])}
    players = [
        {"qq": p_uid, "role_name": get_role_name(platform, p_uid) or p_uid}
        for p_uid in get_participants(appointment["id"])
    ]
    await post_to_archive(
        "/api/session_stats",
        {
            "session_id": session_id,
            "stats": stats,
            "players": players,
            "group_id": group_openid,
            "platform": platform,
            "game_day": appointment["day"],
            "place": appointment["place"] or "",
            "subtype": appointment["subtype"],
            "timestamp": now_ms,
        },
    )
    return True


def get_stale_appointments(platform: str, timeout_seconds: int) -> list[dict]:
    cutoff = int(time.time()) - timeout_seconds
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT * FROM appointments
            WHERE platform = ? AND status = 'active'
              AND last_reply_at <= ?
              AND (last_reminded_at IS NULL OR last_reminded_at <= ?)
            """,
            (platform, cutoff, cutoff),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_reminded(appointment_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE appointments SET last_reminded_at = ? WHERE id = ?", (int(time.time()), appointment_id)
        )
        conn.commit()
    finally:
        conn.close()


async def end_appointment(platform: str, appointment_id: int, forced: bool = False) -> tuple[bool, str, str | None]:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM appointments WHERE id = ? AND platform = ?", (appointment_id, platform)
        ).fetchone()
        if row is None or row["status"] != "active":
            return False, "找不到这场进行中的约会", None
        conn.execute("UPDATE appointments SET status = 'ended' WHERE id = ?", (appointment_id,))
        conn.commit()
    finally:
        conn.close()

    appointment = dict(row)
    session_id = get_session_id(appointment)
    stats = {s["role_name"]: {"replies": s["replies"], "words": s["words"]} for s in _get_session_stats(appointment_id)}
    await post_to_archive(
        "/api/session_end",
        {
            "session_id": session_id,
            "group_id": appointment["group_openid"],
            "platform": platform,
            "game_day": appointment["day"],
            "participants": [get_role_name(platform, p) or p for p in get_participants(appointment_id)],
            "stats": stats,
            "forced": forced,
            "timestamp": int(time.time() * 1000),
        },
    )

    group_openid = row["group_openid"]
    if group_openid:
        free_group(platform, group_openid)
    return True, "约会已结束，戏群已释放", group_openid


def get_appointment_by_group(platform: str, group_openid: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM appointments WHERE platform = ? AND group_openid = ? AND status = 'active'",
            (platform, group_openid),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def get_participants(appointment_id: int) -> list[str]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT uid FROM appointment_participants WHERE appointment_id = ?", (appointment_id,)
        ).fetchall()
        return [r["uid"] for r in rows]
    finally:
        conn.close()


def apply_join(platform: str, group_openid: str, applicant_uid: str) -> tuple[bool, str, int | None]:
    applicant_uid = get_primary_uid(platform, applicant_uid)
    if get_role_name(platform, applicant_uid) is None:
        return False, "你还没有角色，先创建新角色", None
    appointment = get_appointment_by_group(platform, group_openid)
    if appointment is None:
        return False, "这个群现在没有进行中的约会", None
    if applicant_uid in get_participants(appointment["id"]):
        return False, "你已经在这场约会里了", None
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO join_requests (appointment_id, applicant_uid, status, created_at) VALUES (?, ?, 'pending', ?)",
            (appointment["id"], applicant_uid, int(time.time())),
        )
        conn.commit()
        return True, "申请已发送，等待场内角色同意", cur.lastrowid
    finally:
        conn.close()


def _get_join_request(request_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM join_requests WHERE id = ?", (request_id,)).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def respond_join(platform: str, uid: str, request_id: int, accept: bool) -> tuple[bool, str]:
    uid = get_primary_uid(platform, uid)
    req = _get_join_request(request_id)
    if req is None or req["status"] != "pending":
        return False, "找不到这条待处理的申请"
    if uid not in get_participants(req["appointment_id"]):
        return False, "只有场内角色能处理申请"
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE join_requests SET status = ? WHERE id = ?",
            ("accepted" if accept else "rejected", request_id),
        )
        if accept:
            conn.execute(
                "INSERT OR IGNORE INTO appointment_participants (appointment_id, uid, role) VALUES (?, ?, 'joined')",
                (req["appointment_id"], req["applicant_uid"]),
            )
        conn.commit()
    finally:
        conn.close()
    return True, "已同意加入" if accept else "已拒绝"

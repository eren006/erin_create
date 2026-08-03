import time

from .storage import get_conn, init_db

init_db()


def get_primary_uid(platform: str, uid: str) -> str:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT main_uid FROM extra_accounts WHERE platform = ? AND uid = ?",
            (platform, uid),
        ).fetchone()
        return row["main_uid"] if row is not None else uid
    finally:
        conn.close()


def bind_role(platform: str, uid: str, role_name: str, gid: str | None = None) -> None:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO accounts (platform, uid, role_name, gid)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (platform, uid) DO UPDATE SET role_name = excluded.role_name, gid = excluded.gid
            """,
            (platform, uid, role_name, gid),
        )
        conn.commit()
    finally:
        conn.close()


def get_role_name(platform: str, uid: str) -> str | None:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT role_name FROM accounts WHERE platform = ? AND uid = ?",
            (platform, uid),
        ).fetchone()
        return row["role_name"] if row is not None else None
    finally:
        conn.close()


def clear_role_storage(platform: str) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM accounts WHERE platform = ?", (platform,))
        conn.execute("DELETE FROM char_profiles WHERE platform = ?", (platform,))
        conn.execute("DELETE FROM place_keys WHERE platform = ?", (platform,))
        conn.execute("DELETE FROM extra_accounts WHERE platform = ?", (platform,))
        conn.execute("DELETE FROM notifications WHERE platform = ?", (platform,))
        conn.commit()
    finally:
        conn.close()


def get_role_group(platform: str, uid: str) -> str | None:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT gid FROM accounts WHERE platform = ? AND uid = ?",
            (platform, uid),
        ).fetchone()
        return row["gid"] if row is not None else None
    finally:
        conn.close()


def list_role_names(platform: str, exclude_uid: str | None = None) -> list[str]:
    conn = get_conn()
    try:
        if exclude_uid is not None:
            exclude_uid = get_primary_uid(platform, exclude_uid)
            rows = conn.execute(
                "SELECT role_name FROM accounts WHERE platform = ? AND uid != ? ORDER BY role_name",
                (platform, exclude_uid),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT role_name FROM accounts WHERE platform = ? ORDER BY role_name", (platform,)
            ).fetchall()
        return [r["role_name"] for r in rows]
    finally:
        conn.close()


def get_uid_by_role_name(platform: str, role_name: str) -> str | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT uid FROM accounts WHERE platform = ? AND role_name = ?",
            (platform, role_name),
        ).fetchone()
        return row["uid"] if row is not None else None
    finally:
        conn.close()


def bind_extra_account(platform: str, uid: str, main_uid: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO extra_accounts (platform, uid, main_uid)
            VALUES (?, ?, ?)
            ON CONFLICT (platform, uid) DO UPDATE SET main_uid = excluded.main_uid
            """,
            (platform, uid, main_uid),
        )
        conn.commit()
    finally:
        conn.close()


def unbind_extra_account(platform: str, uid: str) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM extra_accounts WHERE platform = ? AND uid = ?", (platform, uid)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def is_admin(platform: str, uid: str) -> bool:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM admins WHERE platform = ? AND uid = ?", (platform, uid)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def grant_admin(platform: str, uid: str) -> None:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO admins (platform, uid) VALUES (?, ?)", (platform, uid)
        )
        conn.commit()
    finally:
        conn.close()


def revoke_admin(platform: str, uid: str) -> bool:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM admins WHERE platform = ? AND uid = ?", (platform, uid)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_admins(platform: str) -> list[str]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT uid FROM admins WHERE platform = ?", (platform,)
        ).fetchall()
        return [row["uid"] for row in rows]
    finally:
        conn.close()


def clear_admins(platform: str) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM admins WHERE platform = ?", (platform,))
        conn.commit()
    finally:
        conn.close()


DEFAULT_LOOK = {"男": "亨利卡维尔", "女": "刘亦菲"}


def get_char_profile(platform: str, uid: str) -> dict | None:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM char_profiles WHERE platform = ? AND uid = ?", (platform, uid)
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def init_char_profile(platform: str, uid: str, gender: str = "女") -> None:
    import time

    uid = get_primary_uid(platform, uid)
    if get_char_profile(platform, uid) is not None:
        return
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO char_profiles (platform, uid, gender, age, look, bio, look_updated_at, bio_updated_at)
            VALUES (?, ?, ?, 18, ?, '', 0, 0)
            """,
            (platform, uid, gender, DEFAULT_LOOK.get(gender, DEFAULT_LOOK["女"])),
        )
        conn.commit()
    finally:
        conn.close()


def set_char_profile(platform: str, uid: str, **patch) -> None:
    import time

    uid = get_primary_uid(platform, uid)
    init_char_profile(platform, uid)
    allowed = {"gender", "age", "look", "bio"}
    fields = {k: v for k, v in patch.items() if k in allowed}
    if not fields:
        return
    if "look" in fields:
        fields["look_updated_at"] = int(time.time())
    if "bio" in fields:
        fields["bio_updated_at"] = int(time.time())
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn = get_conn()
    try:
        conn.execute(
            f"UPDATE char_profiles SET {set_clause} WHERE platform = ? AND uid = ?",
            (*fields.values(), platform, uid),
        )
        conn.commit()
    finally:
        conn.close()


def is_place_system_enabled() -> bool:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'place_system_enabled'"
        ).fetchone()
        return row is not None and row["value"] == "1"
    finally:
        conn.close()


def set_place_system_enabled(enabled: bool) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES ('place_system_enabled', ?)
            ON CONFLICT (key) DO UPDATE SET value = excluded.value
            """,
            ("1" if enabled else "0",),
        )
        conn.commit()
    finally:
        conn.close()


def list_places(platform: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM places WHERE platform = ? ORDER BY name", (platform,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_place(platform: str, name: str, desc: str = "", locked: bool = False) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO places (platform, name, desc, locked) VALUES (?, ?, ?, ?)
            ON CONFLICT (platform, name) DO UPDATE SET desc = excluded.desc, locked = excluded.locked
            """,
            (platform, name, desc, int(locked)),
        )
        conn.commit()
    finally:
        conn.close()


def remove_place(platform: str, name: str) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM places WHERE platform = ? AND name = ?", (platform, name)
        )
        conn.execute(
            "DELETE FROM place_keys WHERE platform = ? AND place_name = ?", (platform, name)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def toggle_place_lock(platform: str, name: str) -> bool | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT locked FROM places WHERE platform = ? AND name = ?", (platform, name)
        ).fetchone()
        if row is None:
            return None
        new_locked = 0 if row["locked"] else 1
        conn.execute(
            "UPDATE places SET locked = ? WHERE platform = ? AND name = ?",
            (new_locked, platform, name),
        )
        conn.commit()
        return bool(new_locked)
    finally:
        conn.close()


def grant_place_key(platform: str, uid: str, place_name: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO place_keys (platform, uid, place_name) VALUES (?, ?, ?)",
            (platform, uid, place_name),
        )
        conn.commit()
    finally:
        conn.close()


def revoke_place_key(platform: str, uid: str, place_name: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM place_keys WHERE platform = ? AND uid = ? AND place_name = ?",
            (platform, uid, place_name),
        )
        conn.commit()
    finally:
        conn.close()


def get_user_keys(platform: str, uid: str) -> list[str]:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT place_name FROM place_keys WHERE platform = ? AND uid = ?", (platform, uid)
        ).fetchall()
        return [r["place_name"] for r in rows]
    finally:
        conn.close()


def check_place_access(platform: str, uid: str, place_name: str) -> tuple[bool, str]:
    if not is_place_system_enabled():
        return True, ""
    places = {p["name"]: p for p in list_places(platform)}
    place = places.get(place_name)
    if place is None:
        m = place_name.endswith("的房间") and place_name[: -len("的房间")]
        if m and get_uid_by_role_name(platform, m) is not None:
            return True, ""
        return False, "地点不存在"
    if not place["locked"]:
        return True, ""
    if place_name in get_user_keys(platform, uid):
        return True, ""
    return False, "需要钥匙"


def is_user_feature_enabled(platform: str, uid: str, feature_key: str) -> bool:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM feature_user_blocklist WHERE platform = ? AND uid = ? AND feature_key = ?",
            (platform, uid, feature_key),
        ).fetchone()
        return row is None
    finally:
        conn.close()


def set_user_feature_enabled(platform: str, uid: str, feature_key: str, enabled: bool) -> None:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        if enabled:
            conn.execute(
                "DELETE FROM feature_user_blocklist WHERE platform = ? AND uid = ? AND feature_key = ?",
                (platform, uid, feature_key),
            )
        else:
            conn.execute(
                "INSERT OR IGNORE INTO feature_user_blocklist (platform, uid, feature_key) VALUES (?, ?, ?)",
                (platform, uid, feature_key),
            )
        conn.commit()
    finally:
        conn.close()


def get_setting(key: str, default: str | None = None) -> str | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row is not None else default
    finally:
        conn.close()


def get_setting_int(key: str, default: int = 0) -> int:
    value = get_setting(key)
    return int(value) if value is not None and value.lstrip("-").isdigit() else default


def set_setting(key: str, value: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT (key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def get_current_day(platform: str) -> str | None:
    return get_setting(f"global_days:{platform}")


def set_current_day(platform: str, day: str) -> None:
    set_setting(f"global_days:{platform}", day)


FEATURE_KEYS = {"wish", "gift", "auction", "appointment", "letters"}


def is_feature_enabled(feature_key: str) -> bool:
    value = get_setting(f"feature_enabled:{feature_key}")
    return value != "0"  # 默认开启，只有显式关闭才是"0"


def set_feature_enabled(feature_key: str, enabled: bool) -> None:
    set_setting(f"feature_enabled:{feature_key}", "1" if enabled else "0")


def get_admin_password() -> str | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'admin_password'"
        ).fetchone()
        return row["value"] if row is not None else None
    finally:
        conn.close()


def set_admin_password(password: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES ('admin_password', ?)
            ON CONFLICT (key) DO UPDATE SET value = excluded.value
            """,
            (password,),
        )
        conn.commit()
    finally:
        conn.close()


# ── 邮箱（跨系统通知，防止主动推送失败导致漏发）──────────────────────────────


def add_notification(platform: str, uid: str, category: str, content: str) -> None:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO notifications (platform, uid, category, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (platform, uid, category, content, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def get_notifications(platform: str, uid: str, unread_only: bool = True) -> list[dict]:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        query = "SELECT * FROM notifications WHERE platform = ? AND uid = ?"
        if unread_only:
            query += " AND read_at IS NULL"
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, (platform, uid)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_notifications_read(notification_ids: list[int]) -> None:
    if not notification_ids:
        return
    conn = get_conn()
    try:
        conn.executemany(
            "UPDATE notifications SET read_at = ? WHERE id = ? AND read_at IS NULL",
            [(int(time.time()), nid) for nid in notification_ids],
        )
        conn.commit()
    finally:
        conn.close()


# ── 群激活（公开开放后用激活码控制实际可用范围）──────────────────────────────


def get_activation_code() -> str | None:
    return get_setting("activation_code")


def set_activation_code(code: str) -> None:
    set_setting("activation_code", code)


def is_group_activated(platform: str, group_openid: str) -> bool:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM activated_groups WHERE platform = ? AND group_openid = ?",
            (platform, group_openid),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def activate_group(platform: str, group_openid: str, activated_by: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO activated_groups (platform, group_openid, activated_at, activated_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (platform, group_openid) DO NOTHING
            """,
            (platform, group_openid, int(time.time()), activated_by),
        )
        conn.commit()
    finally:
        conn.close()


def deactivate_group(platform: str, group_openid: str) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM activated_groups WHERE platform = ? AND group_openid = ?",
            (platform, group_openid),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_activated_groups(platform: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM activated_groups WHERE platform = ? ORDER BY activated_at", (platform,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

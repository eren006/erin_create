"""网页账号系统：QQ号申请 → 管理员批准 → 登录。

账号就是QQ号，初始密码 88888888，登录后可以自己改。
密码用 PBKDF2 加盐哈希存储，不存明文。
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(
    os.getenv("HOGWARTS_DB_PATH", Path(__file__).resolve().parent / "data" / "hogwarts.db")
)

DEFAULT_PASSWORD = "88888888"
SESSION_TTL = 30 * 86400
PBKDF2_ROUNDS = 200_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS web_accounts (
    uid TEXT PRIMARY KEY,
    player_uid TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL DEFAULT '',
    salt TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    is_admin INTEGER NOT NULL DEFAULT 0,
    must_change_password INTEGER NOT NULL DEFAULT 1,
    note TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    approved_at INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS web_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS web_sessions (
    token TEXT PRIMARY KEY,
    uid TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_web_sessions_uid ON web_sessions (uid);
"""


class AuthError(Exception):
    pass


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    try:
        conn.executescript(SCHEMA)
        try:
            conn.execute("ALTER TABLE web_accounts ADD COLUMN player_uid TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        # 兼容旧版：过去登录QQ号同时也被当作角色UID使用。
        conn.execute(
            "UPDATE web_accounts SET player_uid = uid WHERE player_uid = '' "
            "AND EXISTS (SELECT 1 FROM players WHERE players.uid = web_accounts.uid)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_web_accounts_player_uid "
            "ON web_accounts(player_uid) WHERE player_uid != ''"
        )
        conn.commit()
    finally:
        conn.close()


def now() -> int:
    return int(time.time())


# ======================== 密码 ========================


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS).hex()


def _make_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    return _hash(password, salt), salt


def _verify(password: str, password_hash: str, salt: str) -> bool:
    if not password_hash or not salt:
        return False
    return secrets.compare_digest(_hash(password, salt), password_hash)


# ======================== 管理员（独立密码登录，与玩家账号无关） ========================

ADMIN_PASSWORD_KEY = "admin_password"
ADMIN_SALT_KEY = "admin_salt"


def _get_setting(key: str) -> str:
    conn = _connect()
    try:
        row = conn.execute("SELECT value FROM web_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else ""
    finally:
        conn.close()


def _set_setting(key: str, value: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO web_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def set_admin_password(password: str) -> None:
    if len(password) < 6:
        raise AuthError("管理密码至少6位。")
    password_hash, salt = _make_password(password)
    _set_setting(ADMIN_PASSWORD_KEY, password_hash)
    _set_setting(ADMIN_SALT_KEY, salt)


def has_admin_password() -> bool:
    return bool(_get_setting(ADMIN_PASSWORD_KEY))


def check_admin_password(password: str) -> bool:
    return _verify(password, _get_setting(ADMIN_PASSWORD_KEY), _get_setting(ADMIN_SALT_KEY))


def change_admin_password(old_password: str, new_password: str) -> None:
    if not check_admin_password(old_password):
        raise AuthError("原管理密码不对。")
    set_admin_password(new_password)


# ======================== 申请与审批 ========================


def _normalise_uid(uid: str) -> str:
    uid = (uid or "").strip()
    if not uid:
        raise AuthError("请填写QQ号。")
    if not uid.isdigit():
        raise AuthError("QQ号只能是数字。")
    if not (5 <= len(uid) <= 12):
        raise AuthError("QQ号长度不对，检查一下。")
    return uid


def enrolment_state(uid: str) -> dict:
    """入学进度。网页账号只发给已经在群里入学并选完魔杖的人。"""
    conn = _connect()
    try:
        try:
            player = conn.execute(
                "SELECT name, surname, house FROM players WHERE uid = ?", (uid,)
            ).fetchone()
        except sqlite3.OperationalError:
            return {"has_player": False, "has_wand": False, "name": "", "house": ""}
        if not player or not player["house"]:
            return {"has_player": False, "has_wand": False, "name": "", "house": ""}
        has_wand = False
        try:
            has_wand = (
                conn.execute("SELECT 1 FROM player_wands WHERE uid = ?", (uid,)).fetchone() is not None
            )
        except sqlite3.OperationalError:
            has_wand = False
        full = f"{player['name']}·{player['surname']}" if player["surname"] else player["name"]
        return {
            "has_player": True,
            "has_wand": has_wand,
            "name": full,
            "house": player["house"],
        }
    finally:
        conn.close()


def _normalise_binding_code(code: str) -> str:
    code = (code or "").strip()
    if len(code) != 6 or not code.isdigit():
        raise AuthError("请输入群里「/网页绑定」生成的六位绑定码。")
    return code


def request_account(uid: str, binding_code: str, note: str = "") -> dict:
    uid = _normalise_uid(uid)
    binding_code = _normalise_binding_code(binding_code)

    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ts = now()
        conn.execute("DELETE FROM web_binding_codes WHERE expires_at <= ?", (ts,))
        binding = conn.execute(
            "SELECT player_uid, login_uid FROM web_binding_codes WHERE code = ? AND expires_at > ?",
            (binding_code, ts),
        ).fetchone()
        if not binding:
            raise AuthError("绑定码无效或已经过期，请回群里重新发送「/网页绑定」。")
        if binding["login_uid"] and binding["login_uid"] != uid:
            raise AuthError("这个绑定码不是为当前QQ号生成的，请检查QQ号或重新生成绑定码。")
        player_uid = binding["player_uid"]
        state = enrolment_state(player_uid)
        if not state["has_player"]:
            raise AuthError("绑定的角色还没有完成分院。")
        if not state["has_wand"]:
            raise AuthError("绑定的角色还没有选完魔杖。")

        row = conn.execute("SELECT status FROM web_accounts WHERE uid = ?", (uid,)).fetchone()
        if row:
            if row["status"] == "approved":
                raise AuthError("这个QQ号已经开通了，直接登录就行（初始密码 88888888）。")
            if row["status"] == "pending":
                raise AuthError("已经提交过申请了，等管理员批准。")
            if row["status"] == "rejected":
                raise AuthError("这个QQ号的申请被拒绝过，请联系管理员。")
        bound = conn.execute(
            "SELECT uid FROM web_accounts WHERE player_uid = ?", (player_uid,)
        ).fetchone()
        if bound:
            raise AuthError("这个霍格沃茨角色已经绑定过网页账号了，直接用原QQ号登录。")
        password_hash, salt = _make_password(DEFAULT_PASSWORD)
        conn.execute(
            "INSERT INTO web_accounts (uid, player_uid, password_hash, salt, status, note, created_at) "
            "VALUES (?, ?, ?, ?, 'pending', ?, ?)",
            (uid, player_uid, password_hash, salt, note.strip()[:100], ts),
        )
        conn.execute("DELETE FROM web_binding_codes WHERE code = ?", (binding_code,))
        conn.commit()
        return {"uid": uid, "name": state["name"], "house": state["house"]}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_accounts(status: str | None = None) -> list[dict]:
    conn = _connect()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM web_accounts WHERE status = ? ORDER BY created_at DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM web_accounts ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def approve(uid: str) -> None:
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE web_accounts SET status = 'approved', approved_at = ? WHERE uid = ?",
            (now(), uid),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise AuthError("找不到这个申请。")
    finally:
        conn.close()


def reject(uid: str) -> None:
    conn = _connect()
    try:
        cur = conn.execute("UPDATE web_accounts SET status = 'rejected' WHERE uid = ?", (uid,))
        conn.commit()
        if cur.rowcount == 0:
            raise AuthError("找不到这个申请。")
    finally:
        conn.close()


def revoke(uid: str) -> None:
    """停用账号并踢掉所有登录会话。"""
    conn = _connect()
    try:
        conn.execute("UPDATE web_accounts SET status = 'rejected' WHERE uid = ?", (uid,))
        conn.execute("DELETE FROM web_sessions WHERE uid = ?", (uid,))
        conn.commit()
    finally:
        conn.close()


def set_admin(uid: str, is_admin: bool) -> None:
    conn = _connect()
    try:
        conn.execute("UPDATE web_accounts SET is_admin = ? WHERE uid = ?", (1 if is_admin else 0, uid))
        conn.commit()
    finally:
        conn.close()


def reset_password(uid: str) -> None:
    """管理员把密码重置回初始值，并要求下次登录后修改。"""
    password_hash, salt = _make_password(DEFAULT_PASSWORD)
    conn = _connect()
    try:
        conn.execute(
            "UPDATE web_accounts SET password_hash = ?, salt = ?, must_change_password = 1 WHERE uid = ?",
            (password_hash, salt, uid),
        )
        conn.execute("DELETE FROM web_sessions WHERE uid = ?", (uid,))
        conn.commit()
    finally:
        conn.close()


def ensure_admin(uid: str) -> None:
    """把某个QQ号直接开成管理员（首次部署用，从命令行调）。"""
    uid = _normalise_uid(uid)
    password_hash, salt = _make_password(DEFAULT_PASSWORD)
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO web_accounts (uid, password_hash, salt, status, is_admin, created_at, approved_at) "
            "VALUES (?, ?, ?, 'approved', 1, ?, ?) "
            "ON CONFLICT(uid) DO UPDATE SET status='approved', is_admin=1, approved_at=excluded.approved_at",
            (uid, password_hash, salt, now(), now()),
        )
        conn.commit()
    finally:
        conn.close()


def has_any_admin() -> bool:
    conn = _connect()
    try:
        row = conn.execute("SELECT 1 FROM web_accounts WHERE is_admin = 1 LIMIT 1").fetchone()
        return row is not None
    finally:
        conn.close()


# ======================== 登录 ========================


def login(uid: str, password: str) -> str:
    uid = _normalise_uid(uid)
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM web_accounts WHERE uid = ?", (uid,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise AuthError("这个QQ号还没有账号，先去申请。")
    if row["status"] == "pending":
        raise AuthError("你的申请还在等管理员批准。")
    if row["status"] != "approved":
        raise AuthError("这个账号已被停用，请联系管理员。")
    if not _verify(password, row["password_hash"], row["salt"]):
        raise AuthError("密码不对。")

    token = secrets.token_urlsafe(32)
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO web_sessions (token, uid, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, uid, now(), now() + SESSION_TTL),
        )
        conn.execute("DELETE FROM web_sessions WHERE expires_at < ?", (now(),))
        conn.commit()
    finally:
        conn.close()
    return token


def logout(token: str) -> None:
    if not token:
        return
    conn = _connect()
    try:
        conn.execute("DELETE FROM web_sessions WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()


def get_account(uid: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM web_accounts WHERE uid = ?", (uid,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def session_user(token: str) -> dict | None:
    """返回当前登录的账号，token失效返回None。"""
    if not token:
        return None
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT s.uid, CASE WHEN a.player_uid != '' THEN a.player_uid ELSE a.uid END AS player_uid, "
            "a.is_admin, a.status, a.must_change_password FROM web_sessions s "
            "JOIN web_accounts a ON a.uid = s.uid WHERE s.token = ? AND s.expires_at > ?",
            (token, now()),
        ).fetchone()
        if not row or row["status"] != "approved":
            return None
        return dict(row)
    finally:
        conn.close()


def change_password(uid: str, old_password: str, new_password: str) -> None:
    if len(new_password) < 6:
        raise AuthError("新密码至少6位。")
    if new_password == DEFAULT_PASSWORD:
        raise AuthError("不能改回初始密码。")
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM web_accounts WHERE uid = ?", (uid,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise AuthError("账号不存在。")
    if not _verify(old_password, row["password_hash"], row["salt"]):
        raise AuthError("原密码不对。")

    password_hash, salt = _make_password(new_password)
    conn = _connect()
    try:
        conn.execute(
            "UPDATE web_accounts SET password_hash = ?, salt = ?, must_change_password = 0 WHERE uid = ?",
            (password_hash, salt, uid),
        )
        conn.commit()
    finally:
        conn.close()

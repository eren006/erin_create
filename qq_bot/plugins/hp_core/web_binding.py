"""QQ 机器人角色与网页数字 QQ 账号之间的一次性绑定码。"""

from __future__ import annotations

import secrets

from . import storage

BINDING_TTL = 10 * 60

SCHEMA = """
CREATE TABLE IF NOT EXISTS web_binding_codes (
    code TEXT PRIMARY KEY,
    player_uid TEXT NOT NULL UNIQUE,
    login_uid TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_web_binding_expiry ON web_binding_codes (expires_at);
"""


class BindingError(Exception):
    pass


def init_db() -> None:
    conn = storage.get_conn()
    try:
        conn.executescript(SCHEMA)
        try:
            conn.execute("ALTER TABLE web_binding_codes ADD COLUMN login_uid TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass
        conn.commit()
    finally:
        conn.close()


def issue(player_uid: str, login_uid: str) -> dict:
    """为已完成入学和选杖的角色生成十分钟有效的一次性六码。"""
    login_uid = (login_uid or "").strip()
    if not login_uid.isdigit() or not (5 <= len(login_uid) <= 12):
        raise BindingError("用法：/网页绑定 你的QQ号（QQ号应为5至12位数字）")
    conn = storage.get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        player = conn.execute(
            "SELECT name, surname, house FROM players WHERE uid = ?", (player_uid,)
        ).fetchone()
        if not player or not player["house"]:
            raise BindingError("你还没有完成分院，先发送「/入学 你的名字」。")
        wand = conn.execute(
            "SELECT 1 FROM player_wands WHERE uid = ?", (player_uid,)
        ).fetchone()
        if not wand:
            raise BindingError("你还没有选完魔杖，先发送「/入学」继续奥利凡德的流程。")

        ts = storage.now()
        conn.execute("DELETE FROM web_binding_codes WHERE expires_at <= ?", (ts,))
        conn.execute("DELETE FROM web_binding_codes WHERE player_uid = ?", (player_uid,))
        for _ in range(20):
            code = f"{secrets.randbelow(1_000_000):06d}"
            exists = conn.execute(
                "SELECT 1 FROM web_binding_codes WHERE code = ?", (code,)
            ).fetchone()
            if not exists:
                break
        else:
            raise BindingError("暂时无法生成绑定码，请稍后重试。")

        conn.execute(
            "INSERT INTO web_binding_codes(code, player_uid, login_uid, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (code, player_uid, login_uid, ts, ts + BINDING_TTL),
        )
        conn.commit()
        full_name = (
            f"{player['name']}·{player['surname']}" if player["surname"] else player["name"]
        )
        return {"code": code, "expires_in": BINDING_TTL, "name": full_name, "login_uid": login_uid}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


init_db()

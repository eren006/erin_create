"""长日系统 · 个人主页（关系线 + 时间线）。

只能通过 QQ 机器人指令「/我的主页」拿到的专属链接访问，没有任何公开的按名字浏览/搜索入口——
拿到别人的链接才能看别人的，自己的链接只能看到自己相关的内容，做不到"切来切去"看别人。

故意不 import plugins.* —— 那条链路会拉着 nonebot 的整套 bot 初始化一起走
（changri_core/__init__.py 在 import 时就要求 nonebot.init() 已经跑过）。
这里直接读同一份 data/changri.db，做一个真正独立、不依赖 bot 进程的网页。
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from flask import Flask, abort, render_template

DB_PATH = Path(__file__).resolve().parent / "data" / "changri.db"
PLATFORM = "qq"
TIMELINE_LIMIT = 200

app = Flask(__name__)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _role_name(uid: str) -> str | None:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT role_name FROM accounts WHERE platform = ? AND uid = ?", (PLATFORM, uid)
        ).fetchone()
        return row["role_name"] if row else None
    finally:
        conn.close()


def resolve_token(token: str) -> tuple[str, str] | None:
    """token -> (uid, role_name)，token 无效或角色已不存在都返回 None。"""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT uid FROM web_access_tokens WHERE platform = ? AND token = ?", (PLATFORM, token)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    role_name = _role_name(row["uid"])
    if role_name is None:
        return None
    return row["uid"], role_name


def get_setting_int(key: str, default: int) -> int:
    conn = _conn()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None or row["value"] is None:
            return default
        try:
            return int(row["value"])
        except ValueError:
            return default
    finally:
        conn.close()


# ── 关系线 ──────────────────────────────────────────────────────────────


def list_my_relationships(my_uid: str) -> list[dict]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM relationship_lines WHERE platform = ? AND (uid_lo = ? OR uid_hi = ?)",
            (PLATFORM, my_uid, my_uid),
        ).fetchall()
        result = []
        for row in rows:
            line = dict(row)
            other_uid = line["uid_hi"] if line["uid_lo"] == my_uid else line["uid_lo"]
            other_name = _role_name(other_uid) or other_uid
            details = conn.execute(
                "SELECT content FROM relationship_details WHERE line_id = ?", (line["id"],)
            ).fetchall()
            result.append(
                {
                    "line": line,
                    "other_name": other_name,
                    "detail_count": len(details),
                    "total_chars": sum(len(d["content"]) for d in details),
                    "is_initiator": line["initiator_uid"] == my_uid,
                    "is_system": line["initiator_uid"] == "SYSTEM",
                }
            )
        return result
    finally:
        conn.close()


def get_relationship_with(my_uid: str, other_name: str) -> dict | None:
    other_uid = None
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT uid FROM accounts WHERE platform = ? AND role_name = ?", (PLATFORM, other_name)
        ).fetchone()
        if row is not None:
            other_uid = row["uid"]
    finally:
        conn.close()
    if other_uid is None:
        return None

    uid_lo, uid_hi = (my_uid, other_uid) if my_uid <= other_uid else (other_uid, my_uid)
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM relationship_lines WHERE platform = ? AND uid_lo = ? AND uid_hi = ?",
            (PLATFORM, uid_lo, uid_hi),
        ).fetchone()
        if row is None:
            return None
        line = dict(row)
        details = conn.execute(
            "SELECT * FROM relationship_details WHERE line_id = ? ORDER BY id ASC", (line["id"],)
        ).fetchall()
        line["details"] = [dict(d) for d in details]
        return line
    finally:
        conn.close()


# ── 时间线 ──────────────────────────────────────────────────────────────


def list_my_timeline(my_uid: str) -> list[dict]:
    """按天分组，最新的天在前；每天内按创建时间新到旧。"""
    conn = _conn()
    try:
        rows = conn.execute(
            """
            SELECT a.* FROM appointments a
            JOIN appointment_participants p ON p.appointment_id = a.id
            WHERE a.platform = ? AND p.uid = ?
            ORDER BY a.created_at DESC
            LIMIT ?
            """,
            (PLATFORM, my_uid, TIMELINE_LIMIT),
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
                (row["id"], my_uid),
            ).fetchone()
            partner_name = _role_name(partner_row["uid"]) if partner_row else None
            grouped[day].append(
                {
                    "subtype": row["subtype"],
                    "time_range": row["time_range"],
                    "place": row["place"],
                    "partner_role": partner_name or "未知",
                    "status": row["status"],
                }
            )
    finally:
        conn.close()
    return [{"day": d, "entries": grouped[d]} for d in day_order]


# ── 路由 ──────────────────────────────────────────────────────────────


@app.get("/")
def index():
    return render_template("my_web/landing.html")


@app.get("/my/<token>")
def dashboard(token: str):
    resolved = resolve_token(token)
    if resolved is None:
        abort(404)
    uid, role_name = resolved
    rels = list_my_relationships(uid)
    timeline = list_my_timeline(uid)
    config = {"max_relationships_per_user": get_setting_int("max_relationships_per_user", 20)}
    return render_template(
        "my_web/dashboard.html", token=token, role_name=role_name, rels=rels, timeline=timeline, config=config
    )


@app.get("/my/<token>/relationship/<other_name>")
def relationship_detail(token: str, other_name: str):
    resolved = resolve_token(token)
    if resolved is None:
        abort(404)
    uid, role_name = resolved
    rel = get_relationship_with(uid, other_name)
    if rel is None:
        abort(404)
    return render_template(
        "my_web/relationship_detail.html", token=token, role_name=role_name, other_name=other_name, rel=rel
    )


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(
        host=os.getenv("PERSONAL_WEB_HOST", "0.0.0.0"),
        port=int(os.getenv("PERSONAL_WEB_PORT", "5020")),
        debug=False,
    )

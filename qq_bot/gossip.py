"""《女巫周刊》：匿名投稿八卦，后台审核通过后发稿费、播报进群并@提到的人。

跟正式校报（submissions.py）是两套独立的东西——不进学年校报刊物，只在群里播一次就完了。
审核通过和实际播报是两步：网页审核完只把状态改成approved，机器人进程的定时任务
再去把"已通过但还没播报"的八卦真正发到群里——网页进程没法直接调nonebot发消息，
这一点跟 hp_core/notify.py 的队列设计是一个道理。

匿名只针对"其他玩家"：uid 一直存着，后台审核和玩家本人查看自己的投稿记录都能看到，
只是从不会把 uid 暴露在群播报或者其他人能看到的地方。
"""

from __future__ import annotations

import os
import random
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(
    os.getenv("HOGWARTS_DB_PATH", Path(__file__).resolve().parent / "data" / "hogwarts.db")
)

DAILY_LIMIT = 5
BODY_MIN = 100
BODY_MAX = 400
REWARD_MIN = 15
REWARD_MAX = 25

SCHEMA = """
CREATE TABLE IF NOT EXISTS gossip_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    body TEXT NOT NULL,
    mentioned_uids TEXT NOT NULL DEFAULT '',
    mentioned_names TEXT NOT NULL DEFAULT '',
    day INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    reward INTEGER NOT NULL DEFAULT 0,
    review_note TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    reviewed_at INTEGER NOT NULL DEFAULT 0,
    broadcast_at INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_gossip_status ON gossip_submissions (status, id);
CREATE INDEX IF NOT EXISTS idx_gossip_broadcast ON gossip_submissions (status, broadcast_at);
"""


class GossipError(Exception):
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
        conn.commit()
    finally:
        conn.close()


def now() -> int:
    return int(time.time())


def count_today(uid: str, day: int) -> int:
    """当天已投的条数。被驳回的不占名额——跟正式校报投稿不一样，这里鼓励多写、
    编辑部觉得不够精彩就退稿重投，不会因为运气不好写砸一条就少一次机会。"""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM gossip_submissions "
            "WHERE uid = ? AND day = ? AND status != 'rejected'",
            (uid, day),
        ).fetchone()
        return row["n"]
    finally:
        conn.close()


def daily_limit_for(uid: str) -> int:
    """羁绊等级够高的猫头鹰宠物会帮忙多投几条，见 plugins/hp_pet/pet.py。"""
    from plugins.hp_pet import pet as hp_pet

    return DAILY_LIMIT + hp_pet.gossip_daily_limit_bonus(uid)


def submit(uid: str, body: str, mentioned_names_input: str, day: int) -> dict:
    from plugins.hp_core import storage as core_storage

    body = (body or "").strip()
    if len(body) < BODY_MIN:
        raise GossipError(f"内容太短了，八卦好歹得有点细节，最少{BODY_MIN}个字，现在{len(body)}个。")
    if len(body) > BODY_MAX:
        raise GossipError(f"写太长了，最多{BODY_MAX}个字，现在{len(body)}个。")

    names = [n.strip() for n in mentioned_names_input.replace("，", ",").split(",") if n.strip()]
    if not names:
        raise GossipError("八卦总得说的是谁，至少写一个名字（多个人用逗号隔开）。")

    mentioned_uids: list[str] = []
    for name in names:
        target = core_storage.get_uid_by_name(name)
        if not target:
            raise GossipError(f"学校里没有叫「{name}」的人，检查一下名字。")
        if target not in mentioned_uids:
            mentioned_uids.append(target)

    used = count_today(uid, day)
    limit = daily_limit_for(uid)
    if used >= limit:
        raise GossipError(f"今天已经投了{used}/{limit}条八卦，明天再来。")

    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO gossip_submissions "
            "(uid, body, mentioned_uids, mentioned_names, day, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uid, body, ",".join(mentioned_uids), "、".join(names), day, now()),
        )
        conn.commit()
        return {"id": cur.lastrowid, "used": used + 1, "limit": limit}
    finally:
        conn.close()


def list_by_status(status: str | None = None) -> list[dict]:
    conn = _connect()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM gossip_submissions WHERE status = ? ORDER BY id DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM gossip_submissions ORDER BY id DESC LIMIT 100"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_mine(uid: str) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM gossip_submissions WHERE uid = ? ORDER BY id DESC LIMIT 30", (uid,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def review(gossip_id: int, approved: bool, note: str = "") -> dict:
    """审核一条八卦。只有还在pending的才能审。通过时随机发一笔稿费；
    退稿没有稿费，但会用系统邮件私信告诉投稿人被拒的理由——毕竟是匿名投稿，
    没法在播报里当面说，只能私下用邮件系统告知。"""
    from plugins.hp_core import storage as core_storage
    from plugins.hp_social import mail

    conn = _connect()
    try:
        reward = random.randint(REWARD_MIN, REWARD_MAX) if approved else 0
        cur = conn.execute(
            "UPDATE gossip_submissions SET status = ?, reward = ?, review_note = ?, reviewed_at = ? "
            "WHERE id = ? AND status = 'pending'",
            ("approved" if approved else "rejected", reward, note.strip()[:100], now(), gossip_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise GossipError("这条八卦不存在，或者已经审过了。")
        row = conn.execute("SELECT * FROM gossip_submissions WHERE id = ?", (gossip_id,)).fetchone()
    finally:
        conn.close()

    if approved and reward:
        core_storage.add_galleons(row["uid"], reward)
    elif not approved:
        reason = note.strip() or "编辑部觉得这条内容不适合公开播报，暂时没有通过。"
        mail.send_system_mail(
            row["uid"],
            f"你投的一条八卦被退稿了。\n编辑部批注：{reason}\n（这次没有稿费，注意下分寸再投。）",
        )
    return dict(row)


def list_pending_broadcast() -> list[dict]:
    """已经通过审核、还没播报进群的八卦，机器人进程的定时任务来取。"""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM gossip_submissions WHERE status = 'approved' AND broadcast_at = 0 "
            "ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_broadcast(ids: list[int]) -> None:
    if not ids:
        return
    conn = _connect()
    try:
        marks = ",".join("?" for _ in ids)
        conn.execute(
            f"UPDATE gossip_submissions SET broadcast_at = ? WHERE id IN ({marks})",
            [now(), *ids],
        )
        conn.commit()
    finally:
        conn.close()

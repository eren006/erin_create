"""校报投稿：学生在网页写稿 → 管理员审核 → 登上当学年的校报，并在通知群里公告。

每天有投稿限额，防止刷版面。审核通过之后稿件会归到"投稿时所在的那个学年"，
所以学年结业出快照时，这一年的来稿会跟着一起冻结进那一期。
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(
    os.getenv("HOGWARTS_DB_PATH", Path(__file__).resolve().parent / "data" / "hogwarts.db")
)

DAILY_LIMIT = 2
TITLE_MAX = 40
BODY_MAX = 600

SCHEMA = """
CREATE TABLE IF NOT EXISTS newspaper_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    day INTEGER NOT NULL DEFAULT 0,
    school_year INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending',
    review_note TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    reviewed_at INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_submissions_status ON newspaper_submissions (status, id);
CREATE INDEX IF NOT EXISTS idx_submissions_year ON newspaper_submissions (school_year, status);
"""


class SubmissionError(Exception):
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
    """当天已投的份数。被拒的也算——否则可以靠反复投废稿绕开限额。"""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM newspaper_submissions WHERE uid = ? AND day = ?", (uid, day)
        ).fetchone()
        return row["n"]
    finally:
        conn.close()


def submit(uid: str, title: str, body: str, day: int, school_year: int) -> dict:
    title = (title or "").strip()
    body = (body or "").strip()
    if not title:
        raise SubmissionError("标题不能空着。")
    if len(title) > TITLE_MAX:
        raise SubmissionError(f"标题最多{TITLE_MAX}个字。")
    if not body:
        raise SubmissionError("正文不能空着。")
    if len(body) > BODY_MAX:
        raise SubmissionError(f"正文最多{BODY_MAX}个字，现在{len(body)}个。")

    used = count_today(uid, day)
    if used >= DAILY_LIMIT:
        raise SubmissionError(f"今天已经投了{used}/{DAILY_LIMIT}篇，明天再来。")

    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO newspaper_submissions (uid, title, body, day, school_year, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uid, title, body, day, school_year, now()),
        )
        conn.commit()
        return {"id": cur.lastrowid, "title": title, "used": used + 1, "limit": DAILY_LIMIT}
    finally:
        conn.close()


def list_by_status(status: str | None = None) -> list[dict]:
    conn = _connect()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM newspaper_submissions WHERE status = ? ORDER BY id DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM newspaper_submissions ORDER BY id DESC LIMIT 100"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_mine(uid: str) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM newspaper_submissions WHERE uid = ? ORDER BY id DESC LIMIT 30", (uid,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get(submission_id: int) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM newspaper_submissions WHERE id = ?", (submission_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def review(submission_id: int, approved: bool, note: str = "") -> dict:
    """审核一篇稿件。只有还在 pending 的才能审，避免重复通过导致重复公告。"""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE newspaper_submissions SET status = ?, review_note = ?, reviewed_at = ? "
            "WHERE id = ? AND status = 'pending'",
            ("approved" if approved else "rejected", note.strip()[:100], now(), submission_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise SubmissionError("这篇稿件不存在，或者已经审过了。")
        row = conn.execute(
            "SELECT * FROM newspaper_submissions WHERE id = ?", (submission_id,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def approved_for_year(school_year: int) -> list[dict]:
    """某个学年已通过的来稿，用于拼进那一期校报。"""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM newspaper_submissions WHERE school_year = ? AND status = 'approved' "
            "ORDER BY reviewed_at",
            (school_year,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

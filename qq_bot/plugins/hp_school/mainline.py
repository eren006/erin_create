"""个人主线成长册。

里程碑尽量从现有游戏记录中推导，而不是让课程、决斗等模块各自维护一份重复进度。
玩家打开成长册时会自动补领已经达成但尚未领取的奖励，老玩家也能无缝追溯。
"""

import sqlite3

from plugins.hp_core.storage import get_conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS mainline_claims (
    uid TEXT NOT NULL,
    milestone_key TEXT NOT NULL,
    claimed_at INTEGER NOT NULL,
    PRIMARY KEY (uid, milestone_key)
);
"""

# (key, 学年, 标题, 要求, 加隆奖励)
MILESTONES = (
    ("first_light", 1, "第一束魔杖光", "学会「荧光闪烁」", 10),
    ("school_path", 2, "找到自己的位置", "加入魁地奇队，或拥有一只宠物", 20),
    ("duel_victory", 3, "决斗俱乐部新星", "赢得第一场正式决斗", 30),
    ("spell_student", 4, "小有成就的巫师", "累计掌握10个魔咒", 40),
    ("owl_excellent", 5, "O.W.L.优等生", "任意一门O.W.L.取得O", 60),
    ("spell_master", 6, "魔咒大师", "累计掌握15个魔咒", 80),
    ("graduated", 7, "霍格沃茨毕业生", "参加N.E.W.T.并完成七年学业", 120),
)


class MainlineError(Exception):
    pass


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone() is not None


def _scalar(conn: sqlite3.Connection, sql: str, params=()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row else 0


def _completed(conn: sqlite3.Connection, uid: str, key: str) -> tuple[bool, str]:
    spell_count = _scalar(conn, "SELECT COUNT(*) FROM learned_spells WHERE uid = ?", (uid,))

    if key == "first_light":
        done = _scalar(
            conn, "SELECT COUNT(*) FROM learned_spells WHERE uid = ? AND spell_key = 'lumos'", (uid,)
        ) > 0
        return done, "1/1" if done else "0/1"

    if key == "school_path":
        joined_team = False
        if _table_exists(conn, "quidditch_players"):
            joined_team = _scalar(
                conn, "SELECT COUNT(*) FROM quidditch_players WHERE uid = ? AND position != ''", (uid,)
            ) > 0
        owns_pet = _scalar(
            conn,
            "SELECT COALESCE(SUM(quantity), 0) FROM inventory "
            "WHERE uid = ? AND item_key LIKE 'pet_%' AND quantity > 0",
            (uid,),
        ) > 0
        done = joined_team or owns_pet
        detail = "已加入魁地奇队" if joined_team else "已拥有宠物" if owns_pet else "尚未选择"
        return done, detail

    if key == "duel_victory":
        wins = 0
        if _table_exists(conn, "duel_sessions"):
            wins = _scalar(
                conn, "SELECT COUNT(*) FROM duel_sessions WHERE status = 'finished' AND winner = ?", (uid,)
            )
        return wins > 0, f"{wins}/1"

    if key == "spell_student":
        return spell_count >= 10, f"{min(spell_count, 10)}/10"

    if key == "owl_excellent":
        count = _scalar(
            conn,
            "SELECT COUNT(*) FROM exam_results WHERE uid = ? AND grade = 5 AND band = 'O'",
            (uid,),
        )
        return count > 0, f"{count}/1"

    if key == "spell_master":
        return spell_count >= 15, f"{min(spell_count, 15)}/15"

    if key == "graduated":
        count = _scalar(
            conn, "SELECT COUNT(*) FROM exam_results WHERE uid = ? AND grade = 7", (uid,)
        )
        return count > 0, "已完成" if count else "未完成"

    return False, ""


def open_book(uid: str) -> dict:
    """读取成长册并原子补领本次新完成里程碑的加隆奖励。"""
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        player = conn.execute("SELECT * FROM players WHERE uid = ?", (uid,)).fetchone()
        if not player or not player["house"]:
            raise MainlineError("你还没有分院，先发「/入学 你的名字」完成入学测试。")

        claimed = {
            row["milestone_key"]
            for row in conn.execute(
                "SELECT milestone_key FROM mainline_claims WHERE uid = ?", (uid,)
            ).fetchall()
        }
        entries = []
        newly_claimed = []
        total_reward = 0
        for key, grade, title, requirement, reward in MILESTONES:
            completed, progress = _completed(conn, uid, key)
            is_claimed = key in claimed
            if completed and not is_claimed:
                conn.execute(
                    "INSERT INTO mainline_claims (uid, milestone_key, claimed_at) "
                    "VALUES (?, ?, CAST(strftime('%s', 'now') AS INTEGER))",
                    (uid, key),
                )
                is_claimed = True
                newly_claimed.append(title)
                total_reward += reward
            entries.append(
                {
                    "key": key,
                    "grade": grade,
                    "title": title,
                    "requirement": requirement,
                    "reward": reward,
                    "completed": completed,
                    "claimed": is_claimed,
                    "progress": progress,
                }
            )

        if total_reward:
            conn.execute(
                "UPDATE players SET galleons = galleons + ?, "
                "updated_at = CAST(strftime('%s', 'now') AS INTEGER) WHERE uid = ?",
                (total_reward, uid),
            )
        conn.commit()
        return {
            "entries": entries,
            "newly_claimed": newly_claimed,
            "reward": total_reward,
            "grade": player["grade"],
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def claimable_rewards(uid: str) -> dict:
    """只读查询当前可领取里程碑，不实际发奖。"""
    conn = get_conn()
    try:
        claimed = {
            row["milestone_key"]
            for row in conn.execute(
                "SELECT milestone_key FROM mainline_claims WHERE uid = ?", (uid,)
            ).fetchall()
        }
        available = []
        reward = 0
        for key, grade, title, requirement, amount in MILESTONES:
            completed, _ = _completed(conn, uid, key)
            if completed and key not in claimed:
                available.append(title)
                reward += amount
        return {"titles": available, "count": len(available), "reward": reward}
    finally:
        conn.close()


init_db()

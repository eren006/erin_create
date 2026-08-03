import sqlite3
import time

from plugins.hp_core.storage import get_conn

SCHEMA = """
CREATE TABLE IF NOT EXISTS sorting_sessions (
    uid TEXT PRIMARY KEY,
    step INTEGER NOT NULL DEFAULT 0,
    name TEXT NOT NULL DEFAULT '',
    surname TEXT NOT NULL DEFAULT '',
    gender TEXT NOT NULL DEFAULT '',
    offered_json TEXT NOT NULL DEFAULT '[]',
    scores_json TEXT NOT NULL DEFAULT '{}',
    subject_bonus_json TEXT NOT NULL DEFAULT '{}',
    answers_json TEXT NOT NULL DEFAULT '{}',
    pending_house TEXT NOT NULL DEFAULT '',
    wand_options_json TEXT NOT NULL DEFAULT '[]',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory (
    uid TEXT NOT NULL,
    item_key TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, item_key)
);

CREATE TABLE IF NOT EXISTS gift_stock (
    item_key TEXT NOT NULL,
    bucket INTEGER NOT NULL,
    sold INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (item_key, bucket)
);

CREATE TABLE IF NOT EXISTS lesson_sessions (
    uid TEXT PRIMARY KEY,
    token TEXT NOT NULL,
    subject_key TEXT NOT NULL,
    scenario_index INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS player_wands (
    uid TEXT PRIMARY KEY,
    wood TEXT NOT NULL,
    core TEXT NOT NULL,
    length TEXT NOT NULL,
    flexibility TEXT NOT NULL,
    chosen_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS work_daily (
    uid TEXT NOT NULL,
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, day)
);

CREATE TABLE IF NOT EXISTS daily_rewards (
    uid TEXT NOT NULL,
    day INTEGER NOT NULL,
    reward_key TEXT NOT NULL,
    claimed_at INTEGER NOT NULL,
    PRIMARY KEY (uid, day, reward_key)
);

CREATE TABLE IF NOT EXISTS careers (
    uid TEXT PRIMARY KEY,
    career_key TEXT NOT NULL,
    signing_bonus INTEGER NOT NULL DEFAULT 0,
    chosen_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS potion_sessions (
    uid TEXT PRIMARY KEY,
    recipe_key TEXT NOT NULL,
    step INTEGER NOT NULL DEFAULT 0,
    score INTEGER NOT NULL DEFAULT 0,
    ingredients_json TEXT NOT NULL,
    choices_json TEXT NOT NULL DEFAULT '[]',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS potion_mastery (
    uid TEXT NOT NULL,
    recipe_key TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    successes INTEGER NOT NULL DEFAULT 0,
    perfects INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, recipe_key)
);

CREATE TABLE IF NOT EXISTS potion_daily (
    uid TEXT NOT NULL,
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, day)
);

CREATE TABLE IF NOT EXISTS potion_effects (
    uid TEXT NOT NULL,
    effect_key TEXT NOT NULL,
    charges INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (uid, effect_key)
);

CREATE TABLE IF NOT EXISTS potion_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    recipe_key TEXT NOT NULL,
    quality TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    accident TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS potion_yearly (
    uid TEXT NOT NULL,
    school_year INTEGER NOT NULL,
    recipe_key TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, school_year, recipe_key)
);

CREATE TABLE IF NOT EXISTS potion_trade_daily (
    uid TEXT NOT NULL,
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, day)
);

CREATE TABLE IF NOT EXISTS potion_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_uid TEXT NOT NULL,
    receiver_uid TEXT NOT NULL,
    potion_key TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS freshman_duels (
    uid TEXT PRIMARY KEY,
    score INTEGER NOT NULL DEFAULT 0,
    progress INTEGER NOT NULL DEFAULT 0,
    last_duel_at INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS group_announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at INTEGER NOT NULL,
    sent_at INTEGER
);
"""


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        for stmt in (
            "ALTER TABLE sorting_sessions ADD COLUMN pending_house TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE sorting_sessions ADD COLUMN wand_options_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE sorting_sessions ADD COLUMN answers_json TEXT NOT NULL DEFAULT '{}'",
        ):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
        conn.commit()
    finally:
        conn.close()


def now() -> int:
    return int(time.time())


def get_session(uid: str) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM sorting_sessions WHERE uid = ?", (uid,)).fetchone()
    finally:
        conn.close()


def is_pending_name_taken(name: str, exclude_uid: str = "") -> bool:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM sorting_sessions WHERE name = ? AND uid != ?", (name, exclude_uid)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def start_session(uid: str, name: str) -> None:
    conn = get_conn()
    try:
        ts = now()
        conn.execute(
            "INSERT INTO sorting_sessions "
            "(uid, step, name, surname, gender, offered_json, scores_json, subject_bonus_json, created_at, updated_at) "
            "VALUES (?, 0, ?, '', '', '[]', '{}', '{}', ?, ?) "
            "ON CONFLICT(uid) DO UPDATE SET "
            "step = 0, name = excluded.name, surname = '', gender = '', offered_json = '[]', scores_json = '{}', "
            "subject_bonus_json = '{}', answers_json = '{}', pending_house = '', "
            "wand_options_json = '[]', updated_at = excluded.updated_at",
            (uid, name, ts, ts),
        )
        conn.commit()
    finally:
        conn.close()


def update_session(uid: str, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn = get_conn()
    try:
        conn.execute(f"UPDATE sorting_sessions SET {cols} WHERE uid = ?", (*fields.values(), uid))
        conn.commit()
    finally:
        conn.close()


def delete_session(uid: str) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM sorting_sessions WHERE uid = ?", (uid,))
        conn.commit()
    finally:
        conn.close()


def get_wand(uid: str) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM player_wands WHERE uid = ?", (uid,)).fetchone()
    finally:
        conn.close()


def finalize_enrollment(uid: str, wand: dict, starting_galleons: int) -> dict:
    """原子写入魔杖、学院、启动资金和兴趣经验，完成全部入学手续。"""
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        session = conn.execute(
            "SELECT * FROM sorting_sessions WHERE uid = ? AND step = 7", (uid,)
        ).fetchone()
        if not session:
            conn.rollback()
            raise ValueError("没有等待选择魔杖的入学会话")
        if conn.execute("SELECT 1 FROM player_wands WHERE uid = ?", (uid,)).fetchone():
            conn.rollback()
            raise ValueError("已经拥有魔杖")

        ts = now()
        conn.execute(
            "INSERT INTO player_wands (uid, wood, core, length, flexibility, chosen_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uid, wand["wood"], wand["core"], wand["length"], wand["flexibility"], ts),
        )
        player = conn.execute("SELECT house FROM players WHERE uid = ?", (uid,)).fetchone()
        if not player:
            conn.rollback()
            raise ValueError("入学角色不存在")
        if player["house"]:
            conn.rollback()
            raise ValueError("入学手续已经完成")
        conn.execute(
            "UPDATE players SET house=?, gender=?, name=?, surname=?, galleons=galleons+?, updated_at=? "
            "WHERE uid=? AND house=''",
            (
                session["pending_house"], session["gender"], session["name"], session["surname"],
                starting_galleons, ts, uid,
            ),
        )
        conn.execute(
            "UPDATE house_points SET member_count = member_count + 1 WHERE house = ?",
            (session["pending_house"],),
        )
        import json

        for subject, amount in json.loads(session["subject_bonus_json"]).items():
            conn.execute(
                "INSERT INTO subject_exp (uid, subject, exp) VALUES (?, ?, MAX(0, ?)) "
                "ON CONFLICT(uid, subject) DO UPDATE SET exp = MAX(0, subject_exp.exp + ?)",
                (uid, subject, amount, amount),
            )
        conn.execute("DELETE FROM sorting_sessions WHERE uid = ?", (uid,))
        conn.commit()
        return {
            "name": session["name"], "surname": session["surname"],
            "house": session["pending_house"], "wand": wand,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ======================== 打工与每日奖励 ========================


def complete_work_atomic(
    uid: str, day: int, stamina_cost: int, earnings: int, daily_limit: int
) -> dict:
    """原子扣体力、增加打工次数和发工资。"""
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT OR IGNORE INTO work_daily (uid, day, count) VALUES (?, ?, 0)", (uid, day)
        )
        count_cur = conn.execute(
            "UPDATE work_daily SET count = count + 1 WHERE uid = ? AND day = ? AND count < ?",
            (uid, day, daily_limit),
        )
        if count_cur.rowcount == 0:
            conn.rollback()
            return {"status": "daily_limit"}
        stamina_cur = conn.execute(
            "UPDATE players SET stamina = stamina - ?, updated_at = ? "
            "WHERE uid = ? AND stamina >= ?",
            (stamina_cost, now(), uid, stamina_cost),
        )
        if stamina_cur.rowcount == 0:
            conn.rollback()
            return {"status": "insufficient_stamina"}
        conn.execute(
            "UPDATE players SET galleons = galleons + ?, updated_at = ? WHERE uid = ?",
            (earnings, now(), uid),
        )
        row = conn.execute(
            "SELECT p.galleons, w.count FROM players p JOIN work_daily w ON w.uid=p.uid "
            "WHERE p.uid=? AND w.day=?",
            (uid, day),
        ).fetchone()
        conn.commit()
        return {"status": "ok", "galleons": row["galleons"], "count": row["count"]}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_work_count(uid: str, day: int) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT count FROM work_daily WHERE uid=? AND day=?", (uid, day)
        ).fetchone()
        return row["count"] if row else 0
    finally:
        conn.close()


def claim_homework_completion_reward(uid: str, day: int, amount: int) -> bool:
    """当天作业全部完成时原子发放一次奖金。"""
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        total = conn.execute(
            "SELECT COUNT(*) FROM homework WHERE uid=? AND day=?", (uid, day)
        ).fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM homework WHERE uid=? AND day=? AND status='pending'", (uid, day)
        ).fetchone()[0]
        if total == 0 or pending > 0:
            conn.rollback()
            return False
        cur = conn.execute(
            "INSERT OR IGNORE INTO daily_rewards (uid, day, reward_key, claimed_at) "
            "VALUES (?, ?, 'homework_complete', ?)",
            (uid, day, now()),
        )
        if cur.rowcount == 0:
            conn.rollback()
            return False
        conn.execute(
            "UPDATE players SET galleons=galleons+?, updated_at=? WHERE uid=?",
            (amount, now(), uid),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def claim_herbology_material(uid: str, day: int, item_key: str = "mat_knotgrass") -> bool:
    """每天首次完成计分草药课时原子发放一份基础材料。"""
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "INSERT OR IGNORE INTO daily_rewards(uid,day,reward_key,claimed_at) "
            "VALUES(?,?,?,?)", (uid, day, "herbology_material", now()),
        )
        if cur.rowcount == 0:
            conn.rollback()
            return False
        conn.execute(
            "INSERT INTO inventory(uid,item_key,quantity) VALUES(?,?,1) "
            "ON CONFLICT(uid,item_key) DO UPDATE SET quantity=quantity+1",
            (uid, item_key),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ======================== 毕业职业 ========================


def get_career(uid: str) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM careers WHERE uid=?", (uid,)).fetchone()
    finally:
        conn.close()


def choose_career_atomic(uid: str, career_key: str, signing_bonus: int) -> bool:
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "INSERT OR IGNORE INTO careers (uid, career_key, signing_bonus, chosen_at) "
            "VALUES (?, ?, ?, ?)",
            (uid, career_key, signing_bonus, now()),
        )
        if cur.rowcount == 0:
            conn.rollback()
            return False
        conn.execute(
            "UPDATE players SET galleons=galleons+?, updated_at=? WHERE uid=?",
            (signing_bonus, now(), uid),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ======================== 课堂微型事件 ========================


def get_lesson_session(uid: str) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM lesson_sessions WHERE uid = ?", (uid,)).fetchone()
    finally:
        conn.close()


def save_lesson_session(uid: str, token: str, subject_key: str, scenario_index: int) -> None:
    conn = get_conn()
    try:
        ts = now()
        conn.execute(
            "INSERT INTO lesson_sessions (uid, token, subject_key, scenario_index, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(uid) DO UPDATE SET token=excluded.token, subject_key=excluded.subject_key, "
            "scenario_index=excluded.scenario_index, updated_at=excluded.updated_at",
            (uid, token, subject_key, scenario_index, ts, ts),
        )
        conn.commit()
    finally:
        conn.close()


def delete_lesson_session(uid: str, token: str) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM lesson_sessions WHERE uid = ? AND token = ?", (uid, token)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ======================== 背包 ========================


def add_item(uid: str, item_key: str, quantity: int = 1) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO inventory (uid, item_key, quantity) VALUES (?, ?, ?) "
            "ON CONFLICT(uid, item_key) DO UPDATE SET quantity = quantity + excluded.quantity",
            (uid, item_key, quantity),
        )
        conn.commit()
    finally:
        conn.close()


def buy_item_atomic(
    uid: str,
    item_key: str,
    price: int,
    *,
    gift_bucket: int | None = None,
    gift_capacity: int | None = None,
) -> str:
    """原子完成购买，返回 ``ok``、``sold_out`` 或 ``insufficient_funds``。

    礼物库存、玩家加隆和背包都在同一个数据库里，因此这里用同一连接和
    ``BEGIN IMMEDIATE`` 把三步包进一个写事务。任何一步失败或抛异常时，
    前面的库存占用和扣款都会一起回滚。
    """
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")

        if gift_bucket is not None:
            if gift_capacity is None:
                raise ValueError("礼物购买必须提供 gift_capacity")
            conn.execute(
                "INSERT OR IGNORE INTO gift_stock (item_key, bucket, sold) VALUES (?, ?, 0)",
                (item_key, gift_bucket),
            )
            stock_cur = conn.execute(
                "UPDATE gift_stock SET sold = sold + 1 "
                "WHERE item_key = ? AND bucket = ? AND sold < ?",
                (item_key, gift_bucket, gift_capacity),
            )
            if stock_cur.rowcount == 0:
                conn.rollback()
                return "sold_out"

        money_cur = conn.execute(
            "UPDATE players SET galleons = galleons - ?, updated_at = ? "
            "WHERE uid = ? AND galleons >= ?",
            (price, now(), uid, price),
        )
        if money_cur.rowcount == 0:
            conn.rollback()
            return "insufficient_funds"

        conn.execute(
            "INSERT INTO inventory (uid, item_key, quantity) VALUES (?, ?, 1) "
            "ON CONFLICT(uid, item_key) DO UPDATE SET quantity = quantity + 1",
            (uid, item_key),
        )
        conn.commit()
        return "ok"
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_item_quantity(uid: str, item_key: str) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT quantity FROM inventory WHERE uid = ? AND item_key = ?", (uid, item_key)
        ).fetchone()
        return row["quantity"] if row else 0
    finally:
        conn.close()


def remove_item(uid: str, item_key: str, quantity: int = 1) -> bool:
    """库存不够就不扣，返回False。"""
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE inventory SET quantity = quantity - ? WHERE uid = ? AND item_key = ? AND quantity >= ?",
            (quantity, uid, item_key, quantity),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_inventory(uid: str) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM inventory WHERE uid = ? AND quantity > 0", (uid,)
        ).fetchall()
    finally:
        conn.close()


# ======================== 礼物全服库存 ========================


def get_gift_sold(item_key: str, bucket: int) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT sold FROM gift_stock WHERE item_key = ? AND bucket = ?", (item_key, bucket)
        ).fetchone()
        return row["sold"] if row else 0
    finally:
        conn.close()


def try_take_gift_stock(item_key: str, bucket: int, capacity: int) -> bool:
    """全服库存原子扣减：卖光了返回False，不会超卖。"""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO gift_stock (item_key, bucket, sold) VALUES (?, ?, 0)",
            (item_key, bucket),
        )
        cur = conn.execute(
            "UPDATE gift_stock SET sold = sold + 1 WHERE item_key = ? AND bucket = ? AND sold < ?",
            (item_key, bucket, capacity),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def release_gift_stock(item_key: str, bucket: int) -> None:
    """扣了库存但后续步骤失败时，把库存还回去。"""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE gift_stock SET sold = sold - 1 WHERE item_key = ? AND bucket = ? AND sold > 0",
            (item_key, bucket),
        )
        conn.commit()
    finally:
        conn.close()


def purge_old_gift_stock(before_bucket: int) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM gift_stock WHERE bucket < ?", (before_bucket,))
        conn.commit()
    finally:
        conn.close()


# ======================== 竞选新人王 ========================


def get_freshman_duel(uid: str) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM freshman_duels WHERE uid = ?", (uid,)).fetchone()
    finally:
        conn.close()


def init_or_get_freshman_duel(uid: str) -> dict:
    """获取或初始化玩家的竞选状态。"""
    conn = get_conn()
    try:
        ts = now()
        conn.execute(
            "INSERT OR IGNORE INTO freshman_duels (uid, score, progress, last_duel_at, created_at, updated_at) "
            "VALUES (?, 0, 0, 0, ?, ?)",
            (uid, ts, ts),
        )
        row = conn.execute("SELECT * FROM freshman_duels WHERE uid = ?", (uid,)).fetchone()
        conn.commit()
        return dict(row) if row else {}
    finally:
        conn.close()


def update_freshman_duel(uid: str, score: int, progress: int) -> None:
    """更新竞选进度和得分。"""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE freshman_duels SET score = ?, progress = ?, last_duel_at = ?, updated_at = ? WHERE uid = ?",
            (score, progress, now(), now(), uid),
        )
        conn.commit()
    finally:
        conn.close()


def get_freshman_duel_rankings() -> list:
    """获取一年级新人王排名（分数降序）。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT uid, score, progress FROM freshman_duels ORDER BY score DESC LIMIT 10"
        ).fetchall()
        return [dict(row) for row in rows] if rows else []
    finally:
        conn.close()


def reset_freshman_duels() -> None:
    """学期末重置所有竞选数据（准备新学期）。"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM freshman_duels")
        conn.commit()
    finally:
        conn.close()


# ======================== 群通知 ========================


def add_group_announcement(message: str) -> int:
    """添加群通知，返回通知ID。"""
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO group_announcements (message, status, created_at) VALUES (?, 'pending', ?)",
            (message, now()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_pending_announcements() -> list:
    """获取待发送的群通知。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, message FROM group_announcements WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
        return [dict(row) for row in rows] if rows else []
    finally:
        conn.close()


def mark_announcement_sent(announcement_id: int) -> None:
    """标记群通知已发送。"""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE group_announcements SET status = 'sent', sent_at = ? WHERE id = ?",
            (now(), announcement_id),
        )
        conn.commit()
    finally:
        conn.close()

import sqlite3
import time
import os
from pathlib import Path

DB_PATH = Path(
    os.getenv(
        "HOGWARTS_DB_PATH",
        Path(__file__).resolve().parent.parent.parent / "data" / "hogwarts.db",
    )
)

HOUSES = ("格兰芬多", "斯莱特林", "拉文克劳", "赫奇帕奇")

STAMINA_MAX = 50
STAMINA_REGEN_INTERVAL = 30 * 60  # 30分钟恢复7点体力
STAMINA_REGEN_AMOUNT = 7

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    uid TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    surname TEXT NOT NULL DEFAULT '',
    gender TEXT NOT NULL DEFAULT '',
    house TEXT NOT NULL DEFAULT '',
    grade INTEGER NOT NULL DEFAULT 1,
    stamina INTEGER NOT NULL DEFAULT 50,
    stamina_updated_at INTEGER NOT NULL DEFAULT 0,
    galleons INTEGER NOT NULL DEFAULT 0,
    active_title TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_players_name ON players (name) WHERE name != '';

CREATE TABLE IF NOT EXISTS subject_exp (
    uid TEXT NOT NULL,
    subject TEXT NOT NULL,
    exp INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, subject)
);

CREATE TABLE IF NOT EXISTS lesson_log (
    uid TEXT NOT NULL,
    subject TEXT NOT NULL,
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, subject, day)
);

CREATE TABLE IF NOT EXISTS lesson_score_log (
    uid TEXT NOT NULL,
    subject TEXT NOT NULL,
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, subject, day)
);

CREATE TABLE IF NOT EXISTS learned_spells (
    uid TEXT NOT NULL,
    spell_key TEXT NOT NULL,
    learned_at INTEGER NOT NULL,
    PRIMARY KEY (uid, spell_key)
);

CREATE TABLE IF NOT EXISTS spell_progress (
    uid TEXT NOT NULL,
    subject TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, subject)
);

CREATE TABLE IF NOT EXISTS homework (
    uid TEXT NOT NULL,
    subject TEXT NOT NULL,
    day INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    PRIMARY KEY (uid, subject, day)
);

CREATE TABLE IF NOT EXISTS house_points (
    house TEXT PRIMARY KEY,
    total_points INTEGER NOT NULL DEFAULT 0,
    member_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS titles (
    uid TEXT NOT NULL,
    title_key TEXT NOT NULL,
    unlocked_at INTEGER NOT NULL,
    PRIMARY KEY (uid, title_key)
);

CREATE TABLE IF NOT EXISTS game_clock (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    started_at INTEGER NOT NULL,
    last_processed_day INTEGER NOT NULL DEFAULT 0,
    group_openid TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS active_effects (
    uid TEXT NOT NULL,
    effect_key TEXT NOT NULL,
    label TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    PRIMARY KEY (uid, effect_key)
);

CREATE TABLE IF NOT EXISTS exam_results (
    uid TEXT NOT NULL,
    subject TEXT NOT NULL,
    grade INTEGER NOT NULL,
    day INTEGER NOT NULL,
    score REAL NOT NULL,
    band TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (uid, subject, grade)
);
CREATE TABLE IF NOT EXISTS newspaper_issues (
    school_year INTEGER PRIMARY KEY,
    start_day INTEGER NOT NULL,
    end_day INTEGER NOT NULL UNIQUE,
    data_json TEXT NOT NULL,
    published_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS kitchen_exp (
    uid TEXT PRIMARY KEY,
    exp INTEGER NOT NULL DEFAULT 0,
    kitchen_stamina INTEGER NOT NULL DEFAULT 40,
    stamina_updated_at INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS kitchen_sessions (
    uid TEXT PRIMARY KEY,
    recipe_key TEXT NOT NULL,
    step INTEGER NOT NULL DEFAULT 0,
    score INTEGER NOT NULL DEFAULT 0,
    ingredients_json TEXT NOT NULL,
    choices_json TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS kitchen_daily (
    uid TEXT NOT NULL,
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, day)
);

CREATE TABLE IF NOT EXISTS kitchen_learned_recipes (
    uid TEXT NOT NULL,
    recipe_key TEXT NOT NULL,
    learned_at INTEGER NOT NULL,
    PRIMARY KEY (uid, recipe_key)
);

CREATE TABLE IF NOT EXISTS kitchen_inventory (
    uid TEXT NOT NULL,
    food_key TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (uid, food_key)
);

CREATE TABLE IF NOT EXISTS kitchen_mastery (
    uid TEXT NOT NULL,
    recipe_key TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    successes INTEGER NOT NULL DEFAULT 0,
    perfects INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, recipe_key)
);

CREATE TABLE IF NOT EXISTS kitchen_history (
    uid TEXT NOT NULL,
    recipe_key TEXT NOT NULL,
    quality TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    disaster TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        # 旧存档迁移：过去每科最多把前2节视为计分课。新逻辑会严格执行全科8节上限。
        conn.execute(
            "INSERT OR IGNORE INTO lesson_score_log (uid, subject, day, count) "
            "SELECT uid, subject, day, MIN(count, 2) FROM lesson_log"
        )
        for house in HOUSES:
            conn.execute(
                "INSERT OR IGNORE INTO house_points (house, total_points, member_count) VALUES (?, 0, 0)",
                (house,),
            )
        conn.commit()
    finally:
        conn.close()


def now() -> int:
    return int(time.time())


# ======================== 玩家 ========================


def get_player(uid: str) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM players WHERE uid = ?", (uid,)).fetchone()
    finally:
        conn.close()


def get_or_create_player(uid: str) -> sqlite3.Row:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM players WHERE uid = ?", (uid,)).fetchone()
        if row:
            return row
        ts = now()
        conn.execute(
            "INSERT INTO players (uid, stamina, stamina_updated_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (uid, STAMINA_MAX, ts, ts, ts),
        )
        conn.commit()
        return conn.execute("SELECT * FROM players WHERE uid = ?", (uid,)).fetchone()
    finally:
        conn.close()


def get_uid_by_name(name: str) -> str | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT uid FROM players WHERE name = ?", (name,)).fetchone()
        return row["uid"] if row else None
    finally:
        conn.close()


def get_name(uid: str) -> str:
    conn = get_conn()
    try:
        row = conn.execute("SELECT name FROM players WHERE uid = ?", (uid,)).fetchone()
        return row["name"] if row and row["name"] else uid
    finally:
        conn.close()


def get_full_name(uid: str) -> str:
    """展示用的全名"名·姓"。姓是纯氛围，找人只认 first name。"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT name, surname FROM players WHERE uid = ?", (uid,)).fetchone()
        if not row or not row["name"]:
            return uid
        return f"{row['name']}·{row['surname']}" if row["surname"] else row["name"]
    finally:
        conn.close()


def is_name_taken(name: str) -> bool:
    return get_uid_by_name(name) is not None


def set_house(uid: str, house: str, gender: str, name: str = "", surname: str = "") -> None:
    if house not in HOUSES:
        raise ValueError(f"未知学院：{house}")
    conn = get_conn()
    try:
        ts = now()
        conn.execute(
            "UPDATE players SET house = ?, gender = ?, name = ?, surname = ?, updated_at = ? WHERE uid = ?",
            (house, gender, name, surname, ts, uid),
        )
        conn.execute(
            "UPDATE house_points SET member_count = member_count + 1 WHERE house = ?",
            (house,),
        )
        conn.commit()
    finally:
        conn.close()


def add_galleons(uid: str, amount: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE players SET galleons = galleons + ?, updated_at = ? WHERE uid = ?",
            (amount, now(), uid),
        )
        conn.commit()
    finally:
        conn.close()


def try_spend_galleons(uid: str, amount: int) -> bool:
    """钱不够就什么都不扣，返回False。SQL层面原子判断，不会出现扣成负数的竞态。"""
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE players SET galleons = galleons - ?, updated_at = ? WHERE uid = ? AND galleons >= ?",
            (amount, now(), uid, amount),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def sync_stamina(uid: str) -> sqlite3.Row:
    """按经过的时间自然回复体力值，回复到读的这一刻为止。"""
    player = get_or_create_player(uid)
    if player["stamina"] >= STAMINA_MAX:
        return player
    elapsed = now() - player["stamina_updated_at"]
    ticks = elapsed // STAMINA_REGEN_INTERVAL
    if ticks <= 0:
        return player
    gained = ticks * STAMINA_REGEN_AMOUNT
    new_stamina = min(STAMINA_MAX, player["stamina"] + gained)
    consumed_seconds = ticks * STAMINA_REGEN_INTERVAL
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE players SET stamina = ?, stamina_updated_at = ?, updated_at = ? WHERE uid = ?",
            (new_stamina, player["stamina_updated_at"] + consumed_seconds, now(), uid),
        )
        conn.commit()
    finally:
        conn.close()
    return get_player(uid)


def seconds_to_next_stamina(player: sqlite3.Row) -> int:
    if player["stamina"] >= STAMINA_MAX:
        return 0
    elapsed_into_tick = (now() - player["stamina_updated_at"]) % STAMINA_REGEN_INTERVAL
    return STAMINA_REGEN_INTERVAL - elapsed_into_tick


def spend_stamina(uid: str, amount: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE players SET stamina = stamina - ?, updated_at = ? WHERE uid = ?",
            (amount, now(), uid),
        )
        conn.commit()
    finally:
        conn.close()


def set_grade(uid: str, grade: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE players SET grade = ?, updated_at = ? WHERE uid = ?", (grade, now(), uid)
        )
        conn.commit()
    finally:
        conn.close()


# ======================== 学科经验 ========================


def get_subject_exp(uid: str, subject: str) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT exp FROM subject_exp WHERE uid = ? AND subject = ?", (uid, subject)
        ).fetchone()
        return row["exp"] if row else 0
    finally:
        conn.close()


def get_all_subject_exp(uid: str) -> dict[str, int]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT subject, exp FROM subject_exp WHERE uid = ?", (uid,)).fetchall()
        return {r["subject"]: r["exp"] for r in rows}
    finally:
        conn.close()


def add_subject_exp(uid: str, subject: str, amount: int) -> int:
    """amount可以是负数（比如作业逾期扣分），结果不会低于0。"""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO subject_exp (uid, subject, exp) VALUES (?, ?, MAX(0, ?)) "
            "ON CONFLICT(uid, subject) DO UPDATE SET exp = MAX(0, subject_exp.exp + ?)",
            (uid, subject, amount, amount),
        )
        conn.commit()
        row = conn.execute(
            "SELECT exp FROM subject_exp WHERE uid = ? AND subject = ?", (uid, subject)
        ).fetchone()
        return row["exp"]
    finally:
        conn.close()


def decay_all_subject_exp(rate: float = 0.9) -> None:
    """所有玩家所有学科经验按比例衰减，学年切换时"忘记一些知识"用。
    全局一次性触发，暂时还没接自动年级推进（等hp_events的日历调度做好再接）。"""
    conn = get_conn()
    try:
        conn.execute("UPDATE subject_exp SET exp = CAST(exp * ? AS INTEGER)", (rate,))
        conn.commit()
    finally:
        conn.close()


# ======================== 作业 ========================


def ensure_homework(uid: str, subject: str, day: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO homework (uid, subject, day, status) VALUES (?, ?, ?, 'pending')",
            (uid, subject, day),
        )
        conn.commit()
    finally:
        conn.close()


def get_homework(uid: str, subject: str, day: int) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM homework WHERE uid = ? AND subject = ? AND day = ?", (uid, subject, day)
        ).fetchone()
    finally:
        conn.close()


def complete_homework(uid: str, subject: str, day: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE homework SET status = 'done' WHERE uid = ? AND subject = ? AND day = ? AND status = 'pending'",
            (uid, subject, day),
        )
        conn.commit()
    finally:
        conn.close()


def mark_homework_overdue(uid: str, subject: str, day: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE homework SET status = 'overdue' WHERE uid = ? AND subject = ? AND day = ?",
            (uid, subject, day),
        )
        conn.commit()
    finally:
        conn.close()


def list_pending_homework_before(uid: str, day: int) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM homework WHERE uid = ? AND day < ? AND status = 'pending'", (uid, day)
        ).fetchall()
    finally:
        conn.close()


def list_today_homework(uid: str, day: int) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM homework WHERE uid = ? AND day = ?", (uid, day)
        ).fetchall()
    finally:
        conn.close()


def settle_homework_with_daily_cap(
    uid: str, before_day: int, penalty_per_item: int, daily_cap: int
) -> tuple[int, int]:
    """原子结算逾期作业，同一个作业日的总扣分不超过 ``daily_cap``。"""
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT subject, day FROM homework "
            "WHERE uid = ? AND day < ? AND status = 'pending' ORDER BY day, subject",
            (uid, before_day),
        ).fetchall()
        penalties_by_day: dict[int, int] = {}
        total_penalty = 0
        for row in rows:
            used = penalties_by_day.get(row["day"], 0)
            penalty = min(penalty_per_item, max(0, daily_cap - used))
            if penalty:
                conn.execute(
                    "INSERT INTO subject_exp (uid, subject, exp) VALUES (?, ?, 0) "
                    "ON CONFLICT(uid, subject) DO UPDATE SET exp = MAX(0, subject_exp.exp - ?)",
                    (uid, row["subject"], penalty),
                )
                penalties_by_day[row["day"]] = used + penalty
                total_penalty += penalty
            conn.execute(
                "UPDATE homework SET status = 'overdue' "
                "WHERE uid = ? AND subject = ? AND day = ? AND status = 'pending'",
                (uid, row["subject"], row["day"]),
            )
        conn.commit()
        return len(rows), total_penalty
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ======================== 咒语 ========================


def has_spell(uid: str, spell_key: str) -> bool:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM learned_spells WHERE uid = ? AND spell_key = ?", (uid, spell_key)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def learn_spell(uid: str, spell_key: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO learned_spells (uid, spell_key, learned_at) VALUES (?, ?, ?)",
            (uid, spell_key, now()),
        )
        conn.commit()
    finally:
        conn.close()


def list_learned_spells(uid: str) -> set[str]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT spell_key FROM learned_spells WHERE uid = ?", (uid,)).fetchall()
        return {r["spell_key"] for r in rows}
    finally:
        conn.close()


def get_spell_progress(uid: str, subject: str) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT progress FROM spell_progress WHERE uid = ? AND subject = ?", (uid, subject)
        ).fetchone()
        return row["progress"] if row else 0
    finally:
        conn.close()


def set_spell_progress(uid: str, subject: str, progress: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO spell_progress (uid, subject, progress) VALUES (?, ?, ?) "
            "ON CONFLICT(uid, subject) DO UPDATE SET progress = excluded.progress",
            (uid, subject, progress),
        )
        conn.commit()
    finally:
        conn.close()


def get_lesson_count(uid: str, subject: str, day: int) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT count FROM lesson_log WHERE uid = ? AND subject = ? AND day = ?",
            (uid, subject, day),
        ).fetchone()
        return row["count"] if row else 0
    finally:
        conn.close()


def get_total_lesson_count(uid: str, day: int) -> int:
    """当天全科实际上课次数，包括疲劳满后的实操加练。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(count), 0) AS total FROM lesson_log WHERE uid = ? AND day = ?",
            (uid, day),
        ).fetchone()
        return row["total"] if row else 0
    finally:
        conn.close()


def get_scored_lesson_count(uid: str, subject: str, day: int) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT count FROM lesson_score_log WHERE uid = ? AND subject = ? AND day = ?",
            (uid, subject, day),
        ).fetchone()
        return row["count"] if row else 0
    finally:
        conn.close()


def get_total_scored_lesson_count(uid: str, day: int) -> int:
    """当天获得学科经验的课程总数，也就是玩家看到的课堂疲劳值。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(count), 0) AS total FROM lesson_score_log WHERE uid = ? AND day = ?",
            (uid, day),
        ).fetchone()
        return min(8, row["total"] if row else 0)
    finally:
        conn.close()


def increment_scored_lesson_count(uid: str, subject: str, day: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO lesson_score_log (uid, subject, day, count) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(uid, subject, day) DO UPDATE SET count = count + 1",
            (uid, subject, day),
        )
        conn.commit()
    finally:
        conn.close()


def increment_lesson_count(uid: str, subject: str, day: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO lesson_log (uid, subject, day, count) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(uid, subject, day) DO UPDATE SET count = count + 1",
            (uid, subject, day),
        )
        conn.commit()
    finally:
        conn.close()


def student_leaderboard(limit: int = 10) -> list[dict]:
    """全校个人排名：按所有学科经验值加总排序，是学院人均分之外的个人视角。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT p.uid, p.name, p.surname, p.house, p.active_title, COALESCE(SUM(s.exp), 0) AS total_exp "
            "FROM players p LEFT JOIN subject_exp s ON s.uid = p.uid "
            "WHERE p.house != '' "
            "GROUP BY p.uid ORDER BY total_exp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_house_points(house: str, amount: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE house_points SET total_points = total_points + ? WHERE house = ?",
            (amount, house),
        )
        conn.commit()
    finally:
        conn.close()


def house_leaderboard() -> list[dict]:
    """按人均分（total_points / member_count）从高到低排序，避免人数不均衡的学院吃亏或占便宜。"""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM house_points").fetchall()
    finally:
        conn.close()
    result = []
    for r in rows:
        avg = r["total_points"] / r["member_count"] if r["member_count"] else 0.0
        result.append(
            {
                "house": r["house"],
                "total_points": r["total_points"],
                "member_count": r["member_count"],
                "avg_points": avg,
            }
        )
    result.sort(key=lambda x: x["avg_points"], reverse=True)
    return result


# ======================== 游戏时钟 ========================
# 没有固定的"开学日"——第一个人发/入学的那一刻起算Day1，之后加入的都算插班生。


def ensure_game_started() -> int:
    """游戏时钟还没启动就启动它（幂等），返回 started_at。"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT started_at FROM game_clock WHERE id = 1").fetchone()
        if row:
            return row["started_at"]
        ts = now()
        conn.execute("INSERT OR IGNORE INTO game_clock (id, started_at) VALUES (1, ?)", (ts,))
        conn.commit()
        row = conn.execute("SELECT started_at FROM game_clock WHERE id = 1").fetchone()
        return row["started_at"]
    finally:
        conn.close()


def get_current_day() -> int | None:
    """第一天算Day1。游戏还没开始（没人触发过/入学）时返回None。"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT started_at FROM game_clock WHERE id = 1").fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return (now() - row["started_at"]) // 86400 + 1


def ensure_game_group(group_openid: str) -> None:
    """还没指定播报群时，用第一个来触发的群兜底。管理员可以用 /设为通知群 随时改。"""
    if not group_openid:
        return
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE game_clock SET group_openid = ? WHERE id = 1 AND group_openid = ''",
            (group_openid,),
        )
        conn.commit()
    finally:
        conn.close()


def set_game_group(group_openid: str) -> None:
    """指定播报群。所有群共享同一个游戏世界，但通知只发到这一个群。"""
    conn = get_conn()
    try:
        conn.execute("UPDATE game_clock SET group_openid = ? WHERE id = 1", (group_openid,))
        conn.commit()
    finally:
        conn.close()


def get_game_group_openid() -> str:
    conn = get_conn()
    try:
        row = conn.execute("SELECT group_openid FROM game_clock WHERE id = 1").fetchone()
        return row["group_openid"] if row else ""
    finally:
        conn.close()


def get_last_processed_day() -> int:
    conn = get_conn()
    try:
        row = conn.execute("SELECT last_processed_day FROM game_clock WHERE id = 1").fetchone()
        return row["last_processed_day"] if row else 0
    finally:
        conn.close()


def set_last_processed_day(day: int) -> None:
    conn = get_conn()
    try:
        conn.execute("UPDATE game_clock SET last_processed_day = ? WHERE id = 1", (day,))
        conn.commit()
    finally:
        conn.close()


def list_sorted_uids() -> list[str]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT uid FROM players WHERE house != ''").fetchall()
        return [r["uid"] for r in rows]
    finally:
        conn.close()


def advance_all_grades(new_grade: int) -> None:
    """全员统一升级（只升不降），对应"年级不卡关、全服同步"的设计。"""
    conn = get_conn()
    try:
        conn.execute("UPDATE players SET grade = ? WHERE grade < ? AND house != ''", (new_grade, new_grade))
        conn.commit()
    finally:
        conn.close()


def record_exam_result(uid: str, subject: str, grade: int, day: int, score: float, band: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO exam_results (uid, subject, grade, day, score, band, created_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(uid, subject, grade) DO UPDATE SET day=excluded.day, score=excluded.score, band=excluded.band",
            (uid, subject, grade, day, score, band, now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_exam_results(uid: str) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM exam_results WHERE uid = ? ORDER BY grade, subject", (uid,)
        ).fetchall()
    finally:
        conn.close()


# ======================== 状态效果（恶作剧道具用） ========================


def add_active_effect(uid: str, effect_key: str, label: str, duration_seconds: int) -> None:
    expires_at = now() + duration_seconds
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO active_effects (uid, effect_key, label, expires_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(uid, effect_key) DO UPDATE SET label = excluded.label, expires_at = excluded.expires_at",
            (uid, effect_key, label, expires_at),
        )
        conn.commit()
    finally:
        conn.close()


def clear_active_effects(uid: str) -> list[str]:
    """清除还没过期的状态，返回被清掉的标签（清理一新用）。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT label FROM active_effects WHERE uid = ? AND expires_at > ?", (uid, now())
        ).fetchall()
        labels = [r["label"] for r in rows]
        if labels:
            conn.execute("DELETE FROM active_effects WHERE uid = ?", (uid,))
            conn.commit()
        return labels
    finally:
        conn.close()


def get_status_suffix(uid: str) -> str:
    """还没过期的状态后缀文本，比如"（带着一头夸张的火焰头）"，可能叠加多条，没有就是空字符串。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT label FROM active_effects WHERE uid = ? AND expires_at > ?", (uid, now())
        ).fetchall()
        return "".join(f"（{r['label']}）" for r in rows)
    finally:
        conn.close()


# ======================== 称号 ========================


def has_title(uid: str, title_key: str) -> bool:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM titles WHERE uid = ? AND title_key = ?", (uid, title_key)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def unlock_title(uid: str, title_key: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO titles (uid, title_key, unlocked_at) VALUES (?, ?, ?)",
            (uid, title_key, now()),
        )
        conn.commit()
    finally:
        conn.close()


# ======================== 厨房系统 ========================

def get_or_create_kitchen_exp(uid: str) -> sqlite3.Row:
    """获取或创建厨房经验记录。"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM kitchen_exp WHERE uid = ?", (uid,)).fetchone()
        if row:
            return row
        ts = now()
        conn.execute(
            "INSERT INTO kitchen_exp (uid, exp, kitchen_stamina, stamina_updated_at, updated_at) "
            "VALUES (?, 0, 40, ?, ?)",
            (uid, ts, ts),
        )
        conn.commit()
        return conn.execute("SELECT * FROM kitchen_exp WHERE uid = ?", (uid,)).fetchone()
    finally:
        conn.close()


def sync_kitchen_stamina(uid: str) -> sqlite3.Row:
    """按经过的时间自然回复厨房活力。"""
    KITCHEN_STAMINA_MAX = 40
    KITCHEN_STAMINA_REGEN_INTERVAL = 25 * 60  # 25分钟
    KITCHEN_STAMINA_REGEN_AMOUNT = 8

    row = get_or_create_kitchen_exp(uid)
    if row["kitchen_stamina"] >= KITCHEN_STAMINA_MAX:
        return row

    elapsed = now() - row["stamina_updated_at"]
    ticks = elapsed // KITCHEN_STAMINA_REGEN_INTERVAL
    if ticks <= 0:
        return row

    gained = ticks * KITCHEN_STAMINA_REGEN_AMOUNT
    new_stamina = min(KITCHEN_STAMINA_MAX, row["kitchen_stamina"] + gained)
    consumed_seconds = ticks * KITCHEN_STAMINA_REGEN_INTERVAL

    conn = get_conn()
    try:
        conn.execute(
            "UPDATE kitchen_exp SET kitchen_stamina = ?, stamina_updated_at = ?, updated_at = ? WHERE uid = ?",
            (new_stamina, row["stamina_updated_at"] + consumed_seconds, now(), uid),
        )
        conn.commit()
    finally:
        conn.close()

    return get_or_create_kitchen_exp(uid)


def get_cooking_exp(uid: str) -> int:
    """获取烹饪经验。"""
    row = get_or_create_kitchen_exp(uid)
    return row["exp"]


def add_cooking_exp(uid: str, amount: int) -> int:
    """增加烹饪经验。"""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE kitchen_exp SET exp = MAX(0, exp + ?), updated_at = ? WHERE uid = ?",
            (amount, now(), uid),
        )
        conn.commit()
        row = conn.execute("SELECT exp FROM kitchen_exp WHERE uid = ?", (uid,)).fetchone()
        return row["exp"]
    finally:
        conn.close()

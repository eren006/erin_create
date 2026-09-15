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

CAVITY_EFFECT_KEY = "choc_frog_cavity"  # 一天吃太多巧克力蛙触发的蛀牙状态，见 hp_school/choc_frog.py
CAVITY_REGEN_MULTIPLIER = 2  # 蛀牙期间体力恢复间隔翻倍，相当于恢复速度减半

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
    attempts INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, subject, day)
);

CREATE TABLE IF NOT EXISTS house_points (
    house TEXT PRIMARY KEY,
    total_points INTEGER NOT NULL DEFAULT 0,
    member_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS house_contributions (
    uid TEXT PRIMARY KEY,
    house TEXT NOT NULL,
    points INTEGER NOT NULL DEFAULT 0
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
    last_weekly_materials_at INTEGER NOT NULL DEFAULT 0,
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
        # 旧存档迁移：CREATE TABLE IF NOT EXISTS 不会给已存在的表加新列，要单独补。
        for stmt in (
            "ALTER TABLE kitchen_exp ADD COLUMN last_weekly_materials_at INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE homework ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0",
        ):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
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


def has_cavity(uid: str) -> bool:
    """一天吃超过阈值的巧克力蛙会蛀牙一天，期间体力恢复变慢，见 hp_school/choc_frog.py。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM active_effects WHERE uid = ? AND effect_key = ? AND expires_at > ?",
            (uid, CAVITY_EFFECT_KEY, now()),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def sync_stamina(uid: str) -> sqlite3.Row:
    """按经过的时间自然回复体力值，回复到读的这一刻为止。"""
    player = get_or_create_player(uid)
    if player["stamina"] >= STAMINA_MAX:
        return player
    interval = STAMINA_REGEN_INTERVAL * CAVITY_REGEN_MULTIPLIER if has_cavity(uid) else STAMINA_REGEN_INTERVAL
    elapsed = now() - player["stamina_updated_at"]
    ticks = elapsed // interval
    if ticks <= 0:
        return player
    gained = ticks * STAMINA_REGEN_AMOUNT
    new_stamina = min(STAMINA_MAX, player["stamina"] + gained)
    consumed_seconds = ticks * interval
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
    interval = STAMINA_REGEN_INTERVAL * CAVITY_REGEN_MULTIPLIER if has_cavity(player["uid"]) else STAMINA_REGEN_INTERVAL
    elapsed_into_tick = (now() - player["stamina_updated_at"]) % interval
    return interval - elapsed_into_tick


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


def record_homework_attempt(uid: str, subject: str, day: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE homework SET attempts = attempts + 1 "
            "WHERE uid = ? AND subject = ? AND day = ? AND status = 'pending'",
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
            "SELECT subject, day, attempts FROM homework "
            "WHERE uid = ? AND day < ? AND status = 'pending' ORDER BY day, subject",
            (uid, before_day),
        ).fetchall()
        penalties_by_day: dict[int, int] = {}
        total_penalty = 0
        overdue_count = 0
        for row in rows:
            if row["attempts"] > 0:
                # 概率制作业：只要当天试过（体力耗尽也没成功），不算"没交"，不扣分。
                conn.execute(
                    "UPDATE homework SET status = 'failed' "
                    "WHERE uid = ? AND subject = ? AND day = ? AND status = 'pending'",
                    (uid, row["subject"], row["day"]),
                )
                continue
            overdue_count += 1
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
        return overdue_count, total_penalty
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


def student_leaderboard(limit: int | None = 10) -> list[dict]:
    """全校个人排名：按所有学科经验值加总排序，是学院人均分之外的个人视角。
    limit 为 None 时不截断，返回全校所有已入学的人。"""
    conn = get_conn()
    try:
        sql = (
            "SELECT p.uid, p.name, p.surname, p.house, p.active_title, COALESCE(SUM(s.exp), 0) AS total_exp "
            "FROM players p LEFT JOIN subject_exp s ON s.uid = p.uid "
            "WHERE p.house != '' "
            "GROUP BY p.uid ORDER BY total_exp DESC"
        )
        params: tuple = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def subject_exam_leaderboard(top_n: int = 3) -> dict[str, list[dict]]:
    """每门学科最近一次期末考试的前N名，按学科key分组。

    "最近一次"取每个人在该学科打分最高的那个grade——学年结算是全员统一推进的，
    正常情况下所有人在同一学科的最新一条就是同一个grade，不用另外传当前年级进来。
    """
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT e.subject, e.uid, e.score, e.band, e.grade, p.name, p.surname, p.house "
            "FROM exam_results e "
            "JOIN players p ON p.uid = e.uid "
            "WHERE e.grade = ("
            "  SELECT MAX(e2.grade) FROM exam_results e2 "
            "  WHERE e2.uid = e.uid AND e2.subject = e.subject"
            ") "
            "ORDER BY e.subject, e.score DESC"
        ).fetchall()
    finally:
        conn.close()

    by_subject: dict[str, list[dict]] = {}
    for r in rows:
        bucket = by_subject.setdefault(r["subject"], [])
        if len(bucket) < top_n:
            bucket.append(dict(r))
    return by_subject


def list_relatives(uid: str) -> list[dict]:
    """同姓即兄弟姐妹，纯氛围关系。按注册顺序（created_at）排，早注册的是哥哥/姐姐。"""
    conn = get_conn()
    try:
        me = conn.execute(
            "SELECT surname, created_at FROM players WHERE uid = ?", (uid,)
        ).fetchone()
        if not me or not me["surname"]:
            return []
        rows = conn.execute(
            "SELECT uid, name, surname, gender, house, created_at FROM players "
            "WHERE surname = ? AND name != '' ORDER BY created_at ASC",
            (me["surname"],),
        ).fetchall()
        relatives = []
        for r in rows:
            if r["uid"] == uid:
                continue
            older = r["created_at"] < me["created_at"]
            relation = ("哥哥" if r["gender"] == "男" else "姐姐") if older else \
                ("弟弟" if r["gender"] == "男" else "妹妹")
            relatives.append({
                "name": r["name"],
                "surname": r["surname"],
                "house": r["house"],
                "relation": relation,
            })
        return relatives
    finally:
        conn.close()


def add_house_contribution(uid: str, house: str, points: int) -> None:
    """只记个人贡献，不动学院总分——配合"总分已经单独加过一次，只是要把功劳分给参与的几个人"
    这种场景用（比如魁地奇获胜按上场的真人队员分别记功，学院分本身只加一次，不会翻倍）。"""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO house_contributions (uid, house, points) VALUES (?, ?, ?) "
            "ON CONFLICT(uid) DO UPDATE SET points = points + excluded.points, house = excluded.house",
            (uid, house, points),
        )
        conn.commit()
    finally:
        conn.close()


def add_house_points(house: str, amount: int, uid: str | None = None) -> None:
    """给学院加分；传uid时顺便记一笔这个人的个人贡献，用来算人均分时把挂名不出力的人踢出分母。"""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE house_points SET total_points = total_points + ? WHERE house = ?",
            (amount, house),
        )
        conn.commit()
    finally:
        conn.close()
    if uid:
        add_house_contribution(uid, house, amount)


def house_leaderboard() -> list[dict]:
    """按总分从高到低排序（人均分仅作为展示列，不参与排序）。
    顺便带上本学年目前贡献最多的人，学期末会拿这个人颁"学院个人奖"。"""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM house_points").fetchall()
        contributor_rows = conn.execute(
            "SELECT house, COUNT(*) AS cnt FROM house_contributions WHERE points > 0 GROUP BY house"
        ).fetchall()
        top_rows = conn.execute(
            "SELECT uid, house, MAX(points) AS points FROM house_contributions "
            "WHERE points > 0 GROUP BY house"
        ).fetchall()
    finally:
        conn.close()
    contributor_counts = {r["house"]: r["cnt"] for r in contributor_rows}
    top_contributors = {r["house"]: r for r in top_rows}
    result = []
    for r in rows:
        active_members = contributor_counts.get(r["house"], 0)
        avg = r["total_points"] / active_members if active_members else 0.0
        top = top_contributors.get(r["house"])
        result.append(
            {
                "house": r["house"],
                "total_points": r["total_points"],
                "member_count": r["member_count"],
                "active_member_count": active_members,
                "avg_points": avg,
                "top_contributor_name": get_full_name(top["uid"]) if top else "",
                "top_contributor_points": top["points"] if top else 0,
            }
        )
    result.sort(key=lambda x: x["total_points"], reverse=True)
    return result


def top_house_contributor(house: str) -> sqlite3.Row | None:
    """该学院本学年对学院分贡献最多的人，学期末颁"学院个人奖"用。"""
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM house_contributions WHERE house = ? AND points > 0 "
            "ORDER BY points DESC LIMIT 1",
            (house,),
        ).fetchone()
    finally:
        conn.close()


def reset_house_contributions() -> None:
    """学年结算颁完"学院个人奖"之后清零，下学年重新计贡献。"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM house_contributions")
        conn.commit()
    finally:
        conn.close()


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


BEIJING_OFFSET = 8 * 3600  # UTC+8，没有夏令时


def _beijing_calendar_day(ts: int) -> int:
    """把UTC时间戳换算成"北京时间的第几天"（从epoch起算），用于把跳天对齐到北京时间0点。"""
    return (ts + BEIJING_OFFSET) // 86400


def seconds_since_beijing_midnight() -> int:
    """现在距离北京时间当天0点过了多少秒，给"新的一天开头留N分钟宽限期"这类判断用。"""
    return (now() + BEIJING_OFFSET) % 86400


def get_current_day() -> int | None:
    """第一天算Day1，此后每天在北京时间0点自动跳到下一天（不是从入学那一刻起满24小时才跳）。
    游戏还没开始（没人触发过/入学）时返回None。"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT started_at FROM game_clock WHERE id = 1").fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return _beijing_calendar_day(now()) - _beijing_calendar_day(row["started_at"]) + 1


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
    """获取或创建厨房经验记录。新玩家自动赠送初始材料。"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM kitchen_exp WHERE uid = ?", (uid,)).fetchone()
        if row:
            return row

        # 新玩家初始化。exp 给10点起步分（最低门槛的配方要5经验），
        # 不然新手一份配方都做不出来，后续经验全靠 kitchen.choose() 烹饪成功时发放。
        ts = now()
        conn.execute(
            "INSERT INTO kitchen_exp (uid, exp, kitchen_stamina, stamina_updated_at, updated_at) "
            "VALUES (?, 10, 40, ?, ?)",
            (uid, ts, ts),
        )

        # 自动赠送初始材料包
        starter_pack = {
            "mat_egg": 5,
            "mat_butter": 3,
            "mat_salt": 2,
            "mat_bread": 3,
            "mat_milk": 4,
            "mat_honey": 2,
            "mat_flour": 3,
            "mat_sugar": 2,
        }
        for mat_key, amount in starter_pack.items():
            conn.execute(
                "INSERT INTO inventory(uid,item_key,quantity) VALUES(?,?,?) "
                "ON CONFLICT(uid,item_key) DO UPDATE SET quantity=quantity+excluded.quantity",
                (uid, mat_key, amount),
            )

        conn.commit()
        return conn.execute("SELECT * FROM kitchen_exp WHERE uid = ?", (uid,)).fetchone()
    finally:
        conn.close()


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

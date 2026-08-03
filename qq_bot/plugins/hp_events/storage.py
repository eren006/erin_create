import sqlite3
import time

from plugins.hp_core.storage import get_conn

SCHEMA = """
CREATE TABLE IF NOT EXISTS quidditch_players (
    uid TEXT PRIMARY KEY,
    house TEXT NOT NULL,
    position TEXT NOT NULL DEFAULT '',
    speed INTEGER NOT NULL DEFAULT 0,
    collision INTEGER NOT NULL DEFAULT 0,
    stamina INTEGER NOT NULL DEFAULT 0,
    accuracy INTEGER NOT NULL DEFAULT 0,
    broom_key TEXT NOT NULL DEFAULT '',
    broom_durability INTEGER NOT NULL DEFAULT 0,
    broom_speed_bonus INTEGER NOT NULL DEFAULT 0,
    broom_collision_bonus INTEGER NOT NULL DEFAULT 0,
    broom_stamina_bonus INTEGER NOT NULL DEFAULT 0,
    broom_accuracy_bonus INTEGER NOT NULL DEFAULT 0,
    season_score INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS quidditch_daily (
    uid TEXT NOT NULL,
    day INTEGER NOT NULL,
    matches INTEGER NOT NULL DEFAULT 0,
    trainings INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, day)
);

CREATE TABLE IF NOT EXISTS duel_challenges (
    challenger_uid TEXT PRIMARY KEY,
    target_uid TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS duel_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid_a TEXT NOT NULL,
    uid_b TEXT NOT NULL,
    hp_a INTEGER NOT NULL,
    hp_b INTEGER NOT NULL,
    round INTEGER NOT NULL DEFAULT 1,
    turn TEXT NOT NULL DEFAULT 'a',
    last_spell_a TEXT NOT NULL DEFAULT '',
    last_spell_b TEXT NOT NULL DEFAULT '',
    shield_a INTEGER NOT NULL DEFAULT 0,
    shield_b INTEGER NOT NULL DEFAULT 0,
    locked_a TEXT NOT NULL DEFAULT '',
    locked_b TEXT NOT NULL DEFAULT '',
    ace_used_a INTEGER NOT NULL DEFAULT 0,
    ace_used_b INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    winner TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_duel_active ON duel_sessions (status, uid_a, uid_b);

CREATE TABLE IF NOT EXISTS duel_cooldowns (
    session_id INTEGER NOT NULL,
    uid TEXT NOT NULL,
    spell_key TEXT NOT NULL,
    ready_round INTEGER NOT NULL,
    PRIMARY KEY (session_id, uid, spell_key)
);

CREATE TABLE IF NOT EXISTS forest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    depth INTEGER NOT NULL DEFAULT 1,
    monster_key TEXT NOT NULL DEFAULT '',
    monster_hp INTEGER NOT NULL DEFAULT 0,
    monster_max_hp INTEGER NOT NULL DEFAULT 0,
    my_hp INTEGER NOT NULL DEFAULT 0,
    my_shield INTEGER NOT NULL DEFAULT 0,
    monster_shield INTEGER NOT NULL DEFAULT 0,
    locked_me TEXT NOT NULL DEFAULT '',
    monster_last_category TEXT NOT NULL DEFAULT '',
    my_last_spell TEXT NOT NULL DEFAULT '',
    ace_used INTEGER NOT NULL DEFAULT 0,
    round INTEGER NOT NULL DEFAULT 1,
    phase TEXT NOT NULL DEFAULT 'combat',
    pending_galleons INTEGER NOT NULL DEFAULT 0,
    pending_exp INTEGER NOT NULL DEFAULT 0,
    pending_materials TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_forest_active ON forest_runs (status, uid);

CREATE TABLE IF NOT EXISTS forest_cooldowns (
    run_id INTEGER NOT NULL,
    spell_key TEXT NOT NULL,
    ready_round INTEGER NOT NULL,
    PRIMARY KEY (run_id, spell_key)
);

CREATE TABLE IF NOT EXISTS forest_daily (
    uid TEXT NOT NULL,
    day INTEGER NOT NULL,
    runs INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, day)
);

CREATE TABLE IF NOT EXISTS forest_defeated (
    uid TEXT NOT NULL,
    monster_key TEXT NOT NULL,
    defeated_at INTEGER NOT NULL,
    PRIMARY KEY (uid, monster_key)
);

CREATE TABLE IF NOT EXISTS duel_daily (
    uid TEXT NOT NULL,
    day INTEGER NOT NULL,
    initiated INTEGER NOT NULL DEFAULT 0,
    received INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, day)
);
"""


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        for stmt in (
            "ALTER TABLE quidditch_players ADD COLUMN broom_key TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE quidditch_players ADD COLUMN broom_durability INTEGER NOT NULL DEFAULT 0",
        ):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # 列已存在（旧库升级用）
        conn.commit()
    finally:
        conn.close()


def now() -> int:
    return int(time.time())


# ======================== 魁地奇选手 ========================


def get_quidditch_player(uid: str) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM quidditch_players WHERE uid = ?", (uid,)).fetchone()
    finally:
        conn.close()


def create_quidditch_player(uid: str, house: str, stats: dict[str, int]) -> None:
    conn = get_conn()
    try:
        ts = now()
        conn.execute(
            "INSERT INTO quidditch_players (uid, house, speed, collision, stamina, accuracy, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, house, stats["speed"], stats["collision"], stats["stamina"], stats["accuracy"], ts, ts),
        )
        conn.commit()
    finally:
        conn.close()


def set_position(uid: str, position: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE quidditch_players SET position = ?, updated_at = ? WHERE uid = ?",
            (position, now(), uid),
        )
        conn.commit()
    finally:
        conn.close()


def get_house_roster(house: str) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM quidditch_players WHERE house = ? AND position != ''", (house,)
        ).fetchall()
    finally:
        conn.close()


def get_position_holder(house: str, position: str) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM quidditch_players WHERE house = ? AND position = ?", (house, position)
        ).fetchone()
    finally:
        conn.close()


def add_stat(uid: str, stat_key: str, amount: int) -> None:
    assert stat_key in ("speed", "collision", "stamina", "accuracy")
    conn = get_conn()
    try:
        conn.execute(
            f"UPDATE quidditch_players SET {stat_key} = {stat_key} + ?, updated_at = ? WHERE uid = ?",
            (amount, now(), uid),
        )
        conn.commit()
    finally:
        conn.close()


def add_season_score(uid: str, amount: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE quidditch_players SET season_score = season_score + ?, updated_at = ? WHERE uid = ?",
            (amount, now(), uid),
        )
        conn.commit()
    finally:
        conn.close()


def set_broom_bonus(uid: str, broom_key: str, effect: dict[str, int], durability: int) -> None:
    """装备新扫帚会整体覆盖旧的加成，不叠加——一次只能装一把，耐久重置为满。"""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE quidditch_players SET broom_key = ?, broom_durability = ?, "
            "broom_speed_bonus = ?, broom_collision_bonus = ?, broom_stamina_bonus = ?, broom_accuracy_bonus = ?, "
            "updated_at = ? WHERE uid = ?",
            (
                broom_key,
                durability,
                effect.get("speed", 0),
                effect.get("collision", 0),
                effect.get("stamina", 0),
                effect.get("accuracy", 0),
                now(),
                uid,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def wear_broom(uid: str, amount: int = 1) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE quidditch_players SET broom_durability = MAX(0, broom_durability - ?), updated_at = ? "
            "WHERE uid = ? AND broom_key != ''",
            (amount, now(), uid),
        )
        conn.commit()
    finally:
        conn.close()


def repair_broom(uid: str, durability: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE quidditch_players SET broom_durability = ?, updated_at = ? WHERE uid = ?",
            (durability, now(), uid),
        )
        conn.commit()
    finally:
        conn.close()


def reset_all_season_scores() -> None:
    conn = get_conn()
    try:
        conn.execute("UPDATE quidditch_players SET season_score = 0, updated_at = ?", (now(),))
        conn.commit()
    finally:
        conn.close()


def mvp_by_house(house: str, limit: int = 1) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM quidditch_players WHERE house = ? ORDER BY season_score DESC LIMIT ?",
            (house, limit),
        ).fetchall()
    finally:
        conn.close()


# ======================== 每日次数 ========================


def get_daily(uid: str, day: int) -> sqlite3.Row:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM quidditch_daily WHERE uid = ? AND day = ?", (uid, day)
        ).fetchone()
        if row:
            return row
        conn.execute("INSERT OR IGNORE INTO quidditch_daily (uid, day) VALUES (?, ?)", (uid, day))
        conn.commit()
        return conn.execute(
            "SELECT * FROM quidditch_daily WHERE uid = ? AND day = ?", (uid, day)
        ).fetchone()
    finally:
        conn.close()


def increment_daily(uid: str, day: int, field: str) -> None:
    assert field in ("matches", "trainings")
    conn = get_conn()
    try:
        conn.execute(
            f"INSERT INTO quidditch_daily (uid, day, {field}) VALUES (?, ?, 1) "
            f"ON CONFLICT(uid, day) DO UPDATE SET {field} = {field} + 1",
            (uid, day),
        )
        conn.commit()
    finally:
        conn.close()


# ======================== 决斗：邀请 ========================


def get_challenge_by_challenger(uid: str) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM duel_challenges WHERE challenger_uid = ?", (uid,)).fetchone()
    finally:
        conn.close()


def get_challenge_to(target_uid: str, challenger_uid: str) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM duel_challenges WHERE target_uid = ? AND challenger_uid = ?",
            (target_uid, challenger_uid),
        ).fetchone()
    finally:
        conn.close()


def list_challenges_to(target_uid: str) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM duel_challenges WHERE target_uid = ? ORDER BY created_at", (target_uid,)
        ).fetchall()
    finally:
        conn.close()


def create_challenge(challenger_uid: str, target_uid: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO duel_challenges (challenger_uid, target_uid, created_at) VALUES (?, ?, ?)",
            (challenger_uid, target_uid, now()),
        )
        conn.commit()
    finally:
        conn.close()


def delete_challenge(challenger_uid: str) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM duel_challenges WHERE challenger_uid = ?", (challenger_uid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ======================== 决斗：对局 ========================


def get_active_session(uid: str) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM duel_sessions WHERE status = 'active' AND (uid_a = ? OR uid_b = ?)", (uid, uid)
        ).fetchone()
    finally:
        conn.close()


def create_session(uid_a: str, uid_b: str, hp: int) -> int:
    conn = get_conn()
    try:
        ts = now()
        cur = conn.execute(
            "INSERT INTO duel_sessions (uid_a, uid_b, hp_a, hp_b, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uid_a, uid_b, hp, hp, ts, ts),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_session(session_id: int, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn = get_conn()
    try:
        conn.execute(f"UPDATE duel_sessions SET {cols} WHERE id = ?", (*fields.values(), session_id))
        conn.commit()
    finally:
        conn.close()


def get_session(session_id: int) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM duel_sessions WHERE id = ?", (session_id,)).fetchone()
    finally:
        conn.close()


# ======================== 决斗：冷却 ========================


def set_cooldown(session_id: int, uid: str, spell_key: str, ready_round: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO duel_cooldowns (session_id, uid, spell_key, ready_round) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(session_id, uid, spell_key) DO UPDATE SET ready_round = excluded.ready_round",
            (session_id, uid, spell_key, ready_round),
        )
        conn.commit()
    finally:
        conn.close()


def get_cooldowns(session_id: int, uid: str) -> dict[str, int]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT spell_key, ready_round FROM duel_cooldowns WHERE session_id = ? AND uid = ?",
            (session_id, uid),
        ).fetchall()
        return {r["spell_key"]: r["ready_round"] for r in rows}
    finally:
        conn.close()


# ======================== 决斗：每日次数 ========================


def get_duel_daily(uid: str, day: int) -> sqlite3.Row:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM duel_daily WHERE uid = ? AND day = ?", (uid, day)).fetchone()
        if row:
            return row
        conn.execute("INSERT OR IGNORE INTO duel_daily (uid, day) VALUES (?, ?)", (uid, day))
        conn.commit()
        return conn.execute("SELECT * FROM duel_daily WHERE uid = ? AND day = ?", (uid, day)).fetchone()
    finally:
        conn.close()


def increment_duel_daily(uid: str, day: int, field: str) -> None:
    assert field in ("initiated", "received")
    conn = get_conn()
    try:
        conn.execute(
            f"INSERT INTO duel_daily (uid, day, {field}) VALUES (?, ?, 1) "
            f"ON CONFLICT(uid, day) DO UPDATE SET {field} = {field} + 1",
            (uid, day),
        )
        conn.commit()
    finally:
        conn.close()


# ======================== 禁林 ========================


def get_active_run(uid: str) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM forest_runs WHERE uid = ? AND status = 'active'", (uid,)
        ).fetchone()
    finally:
        conn.close()


def create_run(uid: str, **fields) -> int:
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    conn = get_conn()
    try:
        ts = now()
        cur = conn.execute(
            f"INSERT INTO forest_runs (uid, {cols}, created_at, updated_at) "
            f"VALUES (?, {marks}, ?, ?)",
            (uid, *fields.values(), ts, ts),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_run(run_id: int, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn = get_conn()
    try:
        conn.execute(f"UPDATE forest_runs SET {cols} WHERE id = ?", (*fields.values(), run_id))
        conn.commit()
    finally:
        conn.close()


def get_run(run_id: int) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM forest_runs WHERE id = ?", (run_id,)).fetchone()
    finally:
        conn.close()


def set_forest_cooldown(run_id: int, spell_key: str, ready_round: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO forest_cooldowns (run_id, spell_key, ready_round) VALUES (?, ?, ?) "
            "ON CONFLICT(run_id, spell_key) DO UPDATE SET ready_round = excluded.ready_round",
            (run_id, spell_key, ready_round),
        )
        conn.commit()
    finally:
        conn.close()


def get_forest_cooldowns(run_id: int) -> dict[str, int]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT spell_key, ready_round FROM forest_cooldowns WHERE run_id = ?", (run_id,)
        ).fetchall()
        return {r["spell_key"]: r["ready_round"] for r in rows}
    finally:
        conn.close()


def clear_forest_cooldowns(run_id: int) -> None:
    """进入下一层时清空冷却——换了个对手，重新开始。"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM forest_cooldowns WHERE run_id = ?", (run_id,))
        conn.commit()
    finally:
        conn.close()


def get_forest_daily(uid: str, day: int) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT runs FROM forest_daily WHERE uid = ? AND day = ?", (uid, day)
        ).fetchone()
        return row["runs"] if row else 0
    finally:
        conn.close()


def increment_forest_daily(uid: str, day: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO forest_daily (uid, day, runs) VALUES (?, ?, 1) "
            "ON CONFLICT(uid, day) DO UPDATE SET runs = runs + 1",
            (uid, day),
        )
        conn.commit()
    finally:
        conn.close()


def has_defeated(uid: str, monster_key: str) -> bool:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM forest_defeated WHERE uid = ? AND monster_key = ?", (uid, monster_key)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def mark_defeated(uid: str, monster_key: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO forest_defeated (uid, monster_key, defeated_at) VALUES (?, ?, ?)",
            (uid, monster_key, now()),
        )
        conn.commit()
    finally:
        conn.close()


def list_defeated(uid: str) -> set[str]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT monster_key FROM forest_defeated WHERE uid = ?", (uid,)).fetchall()
        return {r["monster_key"] for r in rows}
    finally:
        conn.close()

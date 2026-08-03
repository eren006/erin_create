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
    protection_potion INTEGER NOT NULL DEFAULT 0,
    wolfsbane_potion INTEGER NOT NULL DEFAULT 0,
    healing_potion INTEGER NOT NULL DEFAULT 0,
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
        # 节日和级长的表也一并建，免得依赖模块导入顺序
        conn.executescript(CHRISTMAS_SCHEMA)
        conn.executescript(PREFECT_SCHEMA)
        for stmt in (
            "ALTER TABLE forest_runs ADD COLUMN protection_potion INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE forest_runs ADD COLUMN wolfsbane_potion INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE forest_runs ADD COLUMN healing_potion INTEGER NOT NULL DEFAULT 0",
        ):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
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


# ======================== 圣诞：舞会 ========================

CHRISTMAS_SCHEMA = """
CREATE TABLE IF NOT EXISTS ball_robes (
    uid TEXT NOT NULL,
    year INTEGER NOT NULL,
    color TEXT NOT NULL,
    style TEXT NOT NULL,
    accessory TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (uid, year)
);

CREATE TABLE IF NOT EXISTS ball_invites (
    inviter_uid TEXT NOT NULL,
    target_uid TEXT NOT NULL,
    year INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (inviter_uid, year)
);

CREATE TABLE IF NOT EXISTS ball_partners (
    uid TEXT NOT NULL,
    partner_uid TEXT NOT NULL,
    year INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (uid, year)
);

CREATE TABLE IF NOT EXISTS ball_attendance (
    uid TEXT NOT NULL,
    year INTEGER NOT NULL,
    has_robe INTEGER NOT NULL DEFAULT 0,
    attended_at INTEGER NOT NULL,
    PRIMARY KEY (uid, year)
);

CREATE TABLE IF NOT EXISTS tree_hangs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    year INTEGER NOT NULL,
    ornament TEXT NOT NULL,
    points INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tree_hangs_year ON tree_hangs (year, uid);

CREATE TABLE IF NOT EXISTS tree_goals (
    year INTEGER PRIMARY KEY,
    goal INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tree_rewards (
    uid TEXT NOT NULL,
    year INTEGER NOT NULL,
    claimed_at INTEGER NOT NULL,
    PRIMARY KEY (uid, year)
);
"""


def init_christmas() -> None:
    conn = get_conn()
    try:
        conn.executescript(CHRISTMAS_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def save_robe(uid: str, year: int, color: str, style: str, accessory: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO ball_robes (uid, year, color, style, accessory, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(uid, year) DO UPDATE SET "
            "color=excluded.color, style=excluded.style, accessory=excluded.accessory, "
            "updated_at=excluded.updated_at",
            (uid, year, color, style, accessory, now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_robe(uid: str, year: int) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM ball_robes WHERE uid = ? AND year = ?", (uid, year)
        ).fetchone()
    finally:
        conn.close()


def create_ball_invite(inviter_uid: str, target_uid: str, year: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO ball_invites (inviter_uid, target_uid, year, created_at) VALUES (?, ?, ?, ?)",
            (inviter_uid, target_uid, year, now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_ball_invite_from(inviter_uid: str, year: int) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM ball_invites WHERE inviter_uid = ? AND year = ?", (inviter_uid, year)
        ).fetchone()
    finally:
        conn.close()


def get_ball_invite(inviter_uid: str, target_uid: str, year: int) -> sqlite3.Row | None:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM ball_invites WHERE inviter_uid = ? AND target_uid = ? AND year = ?",
            (inviter_uid, target_uid, year),
        ).fetchone()
    finally:
        conn.close()


def list_ball_invites_to(target_uid: str, year: int) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM ball_invites WHERE target_uid = ? AND year = ? ORDER BY created_at",
            (target_uid, year),
        ).fetchall()
    finally:
        conn.close()


def delete_ball_invite(inviter_uid: str, year: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM ball_invites WHERE inviter_uid = ? AND year = ?", (inviter_uid, year)
        )
        conn.commit()
    finally:
        conn.close()


def set_ball_partner(uid_a: str, uid_b: str, year: int) -> None:
    conn = get_conn()
    try:
        ts = now()
        conn.execute(
            "INSERT OR REPLACE INTO ball_partners (uid, partner_uid, year, created_at) VALUES (?, ?, ?, ?)",
            (uid_a, uid_b, year, ts),
        )
        conn.execute(
            "INSERT OR REPLACE INTO ball_partners (uid, partner_uid, year, created_at) VALUES (?, ?, ?, ?)",
            (uid_b, uid_a, year, ts),
        )
        conn.commit()
    finally:
        conn.close()


def get_ball_partner(uid: str, year: int) -> str | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT partner_uid FROM ball_partners WHERE uid = ? AND year = ?", (uid, year)
        ).fetchone()
        return row["partner_uid"] if row else None
    finally:
        conn.close()


def mark_ball_attended(uid: str, year: int, has_robe: bool) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO ball_attendance (uid, year, has_robe, attended_at) VALUES (?, ?, ?, ?)",
            (uid, year, 1 if has_robe else 0, now()),
        )
        conn.commit()
    finally:
        conn.close()


def has_attended_ball(uid: str, year: int) -> bool:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT 1 FROM ball_attendance WHERE uid = ? AND year = ?", (uid, year)
        ).fetchone() is not None
    finally:
        conn.close()


def list_ball_attendees(year: int) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM ball_attendance WHERE year = ? ORDER BY attended_at", (year,)
        ).fetchall()
    finally:
        conn.close()


# ======================== 圣诞：圣诞树 ========================


def add_tree_hang(uid: str, year: int, ornament: str, points: int) -> int:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO tree_hangs (uid, year, ornament, points, created_at) VALUES (?, ?, ?, ?, ?)",
            (uid, year, ornament, points, now()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT COALESCE(SUM(points), 0) AS total FROM tree_hangs WHERE year = ?", (year,)
        ).fetchone()
        return row["total"]
    finally:
        conn.close()


def get_tree_progress(year: int) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(points), 0) AS total FROM tree_hangs WHERE year = ?", (year,)
        ).fetchone()
        return row["total"]
    finally:
        conn.close()


def last_tree_hang_at(uid: str, year: int) -> int | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT MAX(created_at) AS ts FROM tree_hangs WHERE uid = ? AND year = ?", (uid, year)
        ).fetchone()
        return row["ts"]
    finally:
        conn.close()


def has_hung_on_tree(uid: str, year: int) -> bool:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT 1 FROM tree_hangs WHERE uid = ? AND year = ? LIMIT 1", (uid, year)
        ).fetchone() is not None
    finally:
        conn.close()


def count_tree_contributors(year: int) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(DISTINCT uid) AS n FROM tree_hangs WHERE year = ?", (year,)
        ).fetchone()
        return row["n"]
    finally:
        conn.close()


def recent_tree_hangs(year: int, limit: int = 8) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT uid, ornament, created_at FROM tree_hangs WHERE year = ? "
            "ORDER BY id DESC LIMIT ?",
            (year, limit),
        ).fetchall()
    finally:
        conn.close()


def mark_tree_reward_claimed(uid: str, year: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO tree_rewards (uid, year, claimed_at) VALUES (?, ?, ?)",
            (uid, year, now()),
        )
        conn.commit()
    finally:
        conn.close()


def has_claimed_tree_reward(uid: str, year: int) -> bool:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT 1 FROM tree_rewards WHERE uid = ? AND year = ?", (uid, year)
        ).fetchone() is not None
    finally:
        conn.close()


def freeze_tree_goal(year: int, goal: int) -> int:
    """第一次有人挂装饰时把目标定死，之后新玩家入学也不会让已完成的树退回未完成。"""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO tree_goals (year, goal, created_at) VALUES (?, ?, ?)",
            (year, goal, now()),
        )
        conn.commit()
        row = conn.execute("SELECT goal FROM tree_goals WHERE year = ?", (year,)).fetchone()
        return row["goal"]
    finally:
        conn.close()


def get_frozen_tree_goal(year: int) -> int | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT goal FROM tree_goals WHERE year = ?", (year,)).fetchone()
        return row["goal"] if row else None
    finally:
        conn.close()


# ======================== 级长选举 ========================

PREFECT_SCHEMA = """
CREATE TABLE IF NOT EXISTS prefect_candidates (
    uid TEXT PRIMARY KEY,
    house TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS prefect_votes (
    voter_uid TEXT PRIMARY KEY,
    target_uid TEXT NOT NULL,
    house TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS prefects (
    uid TEXT PRIMARY KEY,
    house TEXT NOT NULL,
    votes INTEGER NOT NULL DEFAULT 0,
    elected_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS prefect_duty (
    uid TEXT NOT NULL,
    day INTEGER NOT NULL,
    done_at INTEGER NOT NULL,
    PRIMARY KEY (uid, day)
);
"""


def init_prefect() -> None:
    conn = get_conn()
    try:
        conn.executescript(PREFECT_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def add_prefect_candidate(uid: str, house: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO prefect_candidates (uid, house, created_at) VALUES (?, ?, ?)",
            (uid, house, now()),
        )
        conn.commit()
    finally:
        conn.close()


def list_prefect_candidates(house: str | None = None) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        if house:
            return conn.execute(
                "SELECT * FROM prefect_candidates WHERE house = ? ORDER BY created_at", (house,)
            ).fetchall()
        return conn.execute("SELECT * FROM prefect_candidates ORDER BY house, created_at").fetchall()
    finally:
        conn.close()


def is_prefect_candidate(uid: str) -> bool:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT 1 FROM prefect_candidates WHERE uid = ?", (uid,)
        ).fetchone() is not None
    finally:
        conn.close()


def cast_prefect_vote(voter_uid: str, target_uid: str, house: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO prefect_votes (voter_uid, target_uid, house, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(voter_uid) DO UPDATE SET target_uid=excluded.target_uid, created_at=excluded.created_at",
            (voter_uid, target_uid, house, now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_prefect_vote(voter_uid: str) -> str | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT target_uid FROM prefect_votes WHERE voter_uid = ?", (voter_uid,)
        ).fetchone()
        return row["target_uid"] if row else None
    finally:
        conn.close()


def vote_tally() -> dict[str, int]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT target_uid, COUNT(*) AS n FROM prefect_votes GROUP BY target_uid"
        ).fetchall()
        return {r["target_uid"]: r["n"] for r in rows}
    finally:
        conn.close()


def add_prefect(uid: str, house: str, votes: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO prefects (uid, house, votes, elected_at) VALUES (?, ?, ?, ?)",
            (uid, house, votes, now()),
        )
        conn.commit()
    finally:
        conn.close()


def list_prefects(house: str | None = None) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        if house:
            return conn.execute(
                "SELECT * FROM prefects WHERE house = ? ORDER BY votes DESC", (house,)
            ).fetchall()
        return conn.execute("SELECT * FROM prefects ORDER BY house, votes DESC").fetchall()
    finally:
        conn.close()


def is_prefect(uid: str) -> bool:
    conn = get_conn()
    try:
        return conn.execute("SELECT 1 FROM prefects WHERE uid = ?", (uid,)).fetchone() is not None
    finally:
        conn.close()


def mark_duty_done(uid: str, day: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO prefect_duty (uid, day, done_at) VALUES (?, ?, ?)",
            (uid, day, now()),
        )
        conn.commit()
    finally:
        conn.close()


def has_done_duty(uid: str, day: int) -> bool:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT 1 FROM prefect_duty WHERE uid = ? AND day = ?", (uid, day)
        ).fetchone() is not None
    finally:
        conn.close()

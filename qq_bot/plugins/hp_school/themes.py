"""网页主题商店：40 加隆购买、永久拥有、装备后全站换肤。"""

from __future__ import annotations

import time

from plugins.hp_core.storage import get_conn


class ThemeError(Exception):
    pass


THEME_PRICE = 40
THEMES = {
    "great_hall": {
        "name": "霍格沃茨夜宴",
        "icon": "🕯️",
        "mood": "烛光礼堂",
        "description": "漂浮烛火、深红帷幔与午夜星窗。",
        "game_name": "漂浮蜡烛",
        "game_description": "在烛火熄灭前重新点亮它们。",
        "image": "web/images/themes/great-hall-v2.webp",
    },
    "potions": {
        "name": "魔药课手记",
        "icon": "⚗️",
        "mood": "地窖课堂",
        "description": "祖母绿药液、古旧瓶罐与温暖烛光。",
        "game_name": "坩埚调配",
        "game_description": "记住配方，按正确顺序投入材料。",
        "image": "web/images/themes/potions-dungeon-v2.webp",
    },
    "quidditch": {
        "name": "魁地奇比赛日",
        "icon": "🧹",
        "mood": "球场应援",
        "description": "高空球场、学院旗帜与雨后金光。",
        "game_name": "追逐金色飞贼",
        "game_description": "在飞贼逃走前尽可能多地抓住它。",
        "image": "web/images/themes/quidditch-stadium-v2.webp",
    },
    "forest": {
        "name": "禁林夜行",
        "icon": "🦌",
        "mood": "月夜探索",
        "description": "银蓝月光、发光足迹与守护神引路。",
        "game_name": "守护神引路",
        "game_description": "观察足迹，选择正确的林间道路。",
        "image": "web/images/themes/forbidden-forest-v2.webp",
    },
}

SCORE_LIMITS = {"great_hall": 20, "potions": 3, "quidditch": 100, "forest": 5}


def seasonal_theme_for_day(day: int | None) -> str:
    """学年最后一天全校自动进入圣诞主题；其他日期不覆盖个人主题。"""
    if not day:
        return ""
    from plugins.hp_events import christmas

    return "christmas" if christmas.is_christmas(day) else ""

SCHEMA = """
CREATE TABLE IF NOT EXISTS web_theme_ownership (
    uid TEXT NOT NULL,
    theme_key TEXT NOT NULL,
    purchased_at INTEGER NOT NULL,
    PRIMARY KEY (uid, theme_key)
);
CREATE TABLE IF NOT EXISTS web_theme_equipment (
    uid TEXT PRIMARY KEY,
    theme_key TEXT NOT NULL DEFAULT '',
    equipped_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS web_theme_game_scores (
    uid TEXT NOT NULL,
    theme_key TEXT NOT NULL,
    best_score INTEGER NOT NULL DEFAULT 0,
    last_score INTEGER NOT NULL DEFAULT 0,
    plays INTEGER NOT NULL DEFAULT 0,
    best_at INTEGER NOT NULL,
    played_at INTEGER NOT NULL,
    PRIMARY KEY (uid, theme_key)
);
CREATE INDEX IF NOT EXISTS idx_theme_game_leaderboard
ON web_theme_game_scores(theme_key, best_score DESC, best_at ASC);
"""


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def list_for(uid: str) -> list[dict]:
    conn = get_conn()
    try:
        owned = {
            row["theme_key"]
            for row in conn.execute(
                "SELECT theme_key FROM web_theme_ownership WHERE uid = ?", (uid,)
            ).fetchall()
        }
        equipped = get_equipped(uid, conn=conn)
    finally:
        conn.close()
    return [
        {"key": key, **theme, "price": THEME_PRICE, "owned": key in owned,
         "equipped": key == equipped}
        for key, theme in THEMES.items()
    ]


def get_equipped(uid: str, *, conn=None) -> str:
    owns_conn = conn is None
    conn = conn or get_conn()
    try:
        row = conn.execute(
            "SELECT theme_key FROM web_theme_equipment WHERE uid = ?", (uid,)
        ).fetchone()
        return row["theme_key"] if row and row["theme_key"] in THEMES else ""
    finally:
        if owns_conn:
            conn.close()


def buy(uid: str, theme_key: str) -> dict:
    theme = THEMES.get(theme_key)
    if not theme:
        raise ThemeError("没有这个主题。")
    conn = get_conn()
    now = int(time.time())
    try:
        conn.execute("BEGIN IMMEDIATE")
        owned = conn.execute(
            "SELECT 1 FROM web_theme_ownership WHERE uid = ? AND theme_key = ?",
            (uid, theme_key),
        ).fetchone()
        if owned:
            raise ThemeError("这个主题已经买过了。")
        spent = conn.execute(
            "UPDATE players SET galleons = galleons - ?, updated_at = ? "
            "WHERE uid = ? AND galleons >= ?",
            (THEME_PRICE, now, uid, THEME_PRICE),
        )
        if spent.rowcount != 1:
            raise ThemeError(f"加隆不够，这个主题需要 {THEME_PRICE} 加隆。")
        conn.execute(
            "INSERT INTO web_theme_ownership(uid, theme_key, purchased_at) VALUES (?, ?, ?)",
            (uid, theme_key, now),
        )
        conn.commit()
        return {"key": theme_key, **theme, "price": THEME_PRICE}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def equip(uid: str, theme_key: str) -> dict | None:
    if not theme_key:
        conn = get_conn()
        try:
            conn.execute("DELETE FROM web_theme_equipment WHERE uid = ?", (uid,))
            conn.commit()
        finally:
            conn.close()
        return None
    theme = THEMES.get(theme_key)
    if not theme:
        raise ThemeError("没有这个主题。")
    conn = get_conn()
    try:
        owned = conn.execute(
            "SELECT 1 FROM web_theme_ownership WHERE uid = ? AND theme_key = ?",
            (uid, theme_key),
        ).fetchone()
        if not owned:
            raise ThemeError("需要先购买这个主题。")
        conn.execute(
            "INSERT INTO web_theme_equipment(uid, theme_key, equipped_at) VALUES (?, ?, ?) "
            "ON CONFLICT(uid) DO UPDATE SET theme_key=excluded.theme_key, equipped_at=excluded.equipped_at",
            (uid, theme_key, int(time.time())),
        )
        conn.commit()
        return {"key": theme_key, **theme}
    finally:
        conn.close()


def get_owned_theme(uid: str, theme_key: str) -> dict:
    theme = THEMES.get(theme_key)
    if not theme:
        raise ThemeError("没有这个小游戏。")
    conn = get_conn()
    try:
        owned = conn.execute(
            "SELECT 1 FROM web_theme_ownership WHERE uid = ? AND theme_key = ?",
            (uid, theme_key),
        ).fetchone()
    finally:
        conn.close()
    if not owned:
        raise ThemeError("购买主题后才能进入对应小游戏。")
    return {"key": theme_key, **theme}


def record_score(uid: str, theme_key: str, score: int) -> dict:
    """记录一局成绩；只有已购买主题的玩家能上榜。"""
    get_owned_theme(uid, theme_key)
    try:
        score = int(score)
    except (TypeError, ValueError):
        raise ThemeError("成绩格式不正确。")
    maximum = SCORE_LIMITS[theme_key]
    if score < 0 or score > maximum:
        raise ThemeError("成绩超出了这个小游戏的合法范围。")
    now = int(time.time())
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        old = conn.execute(
            "SELECT best_score FROM web_theme_game_scores WHERE uid = ? AND theme_key = ?",
            (uid, theme_key),
        ).fetchone()
        is_best = old is None or score > old["best_score"]
        conn.execute(
            "INSERT INTO web_theme_game_scores"
            "(uid, theme_key, best_score, last_score, plays, best_at, played_at) "
            "VALUES (?, ?, ?, ?, 1, ?, ?) "
            "ON CONFLICT(uid, theme_key) DO UPDATE SET "
            "best_score=MAX(best_score, excluded.best_score), "
            "last_score=excluded.last_score, plays=plays+1, "
            "best_at=CASE WHEN excluded.best_score > best_score THEN excluded.best_at ELSE best_at END, "
            "played_at=excluded.played_at",
            (uid, theme_key, score, score, now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT best_score, last_score, plays FROM web_theme_game_scores "
            "WHERE uid = ? AND theme_key = ?",
            (uid, theme_key),
        ).fetchone()
        return {**dict(row), "new_best": is_best}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def leaderboard(theme_key: str, limit: int = 50) -> list[dict]:
    if theme_key not in THEMES:
        raise ThemeError("没有这个小游戏。")
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT uid, best_score, last_score, plays, played_at "
            "FROM web_theme_game_scores WHERE theme_key = ? "
            "ORDER BY best_score DESC, best_at ASC LIMIT ?",
            (theme_key, max(1, min(int(limit), 100))),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

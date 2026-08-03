"""校园校报的纯数据服务，供 NoneBot 文字版和 Flask 网页共同使用。"""

from __future__ import annotations

import sqlite3
import time
import os
import json
from pathlib import Path

DB_PATH = Path(
    os.getenv("HOGWARTS_DB_PATH", Path(__file__).resolve().parent / "data" / "hogwarts.db")
)

CAREER_NAMES = {
    "auror": "傲罗",
    "healer": "圣芒戈治疗师",
    "professor": "霍格沃茨教授",
    "wandmaker": "魔杖制作师",
    "magizoologist": "神奇动物学家",
    "quidditch": "职业魁地奇球员",
    "ministry": "魔法部职员",
    "reporter": "《预言家日报》记者",
}

YEAR_RANGES = {
    1: (1, 4),
    2: (5, 8),
    3: (9, 12),
    4: (13, 16),
    5: (17, 21),
    6: (22, 25),
    7: (26, 30),
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _ensure_issue_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS newspaper_issues ("
        "school_year INTEGER PRIMARY KEY, start_day INTEGER NOT NULL, "
        "end_day INTEGER NOT NULL UNIQUE, data_json TEXT NOT NULL, "
        "published_at INTEGER NOT NULL)"
    )


def _full_name(conn: sqlite3.Connection, uid: str) -> str:
    row = conn.execute("SELECT name, surname FROM players WHERE uid=?", (uid,)).fetchone()
    if not row or not row["name"]:
        return uid
    return f"{row['name']}·{row['surname']}" if row["surname"] else row["name"]


def current_day() -> int:
    conn = _connect()
    try:
        row = conn.execute("SELECT started_at FROM game_clock WHERE id=1").fetchone()
        return max(1, (int(time.time()) - row["started_at"]) // 86400 + 1) if row else 1
    finally:
        conn.close()


def school_year(day: int) -> int:
    return next((year for year, (_, end) in YEAR_RANGES.items() if day <= end), 7)


def archive_days(day: int | None = None) -> list[int]:
    day = day or current_day()
    published = [end for _, end in YEAR_RANGES.values() if end <= day]
    if not published:
        published.append(day)  # 一年级尚未结业时显示实时预览。
    return sorted(set(published), reverse=True)


def _build_live_issue(end_day: int | None = None) -> dict:
    live_day = current_day()
    end_day = max(1, min(end_day or live_day, live_day))
    year = school_year(end_day)
    year_start, year_end = YEAR_RANGES[year]
    start_day = year_start
    end_day = min(end_day, year_end)
    conn = _connect()
    try:
        clock = conn.execute("SELECT started_at FROM game_clock WHERE id=1").fetchone()
        started_at = clock["started_at"] if clock else int(time.time())
        start_ts = started_at + (start_day - 1) * 86400
        end_ts = started_at + end_day * 86400

        newcomers = []
        if _table_exists(conn, "player_wands"):
            newcomers = [
                dict(row)
                for row in conn.execute(
                    "SELECT p.uid, p.name, p.surname, p.house, w.wood, w.core "
                    "FROM player_wands w JOIN players p ON p.uid=w.uid "
                    "WHERE w.chosen_at>=? AND w.chosen_at<? ORDER BY w.chosen_at LIMIT 12",
                    (start_ts, end_ts),
                ).fetchall()
            ]

        spells = [
            {"uid": row["uid"], "name": _full_name(conn, row["uid"]), "amount": row["amount"]}
            for row in conn.execute(
                "SELECT uid, COUNT(*) AS amount FROM learned_spells "
                "WHERE learned_at>=? AND learned_at<? GROUP BY uid ORDER BY amount DESC LIMIT 8",
                (start_ts, end_ts),
            ).fetchall()
        ]

        duels = []
        if _table_exists(conn, "duel_sessions"):
            duels = [
                {"uid": row["winner"], "name": _full_name(conn, row["winner"]), "wins": row["wins"]}
                for row in conn.execute(
                    "SELECT winner, COUNT(*) AS wins FROM duel_sessions "
                    "WHERE status='finished' AND winner!='' AND updated_at>=? AND updated_at<? "
                    "GROUP BY winner ORDER BY wins DESC LIMIT 8",
                    (start_ts, end_ts),
                ).fetchall()
            ]

        couples = []
        if _table_exists(conn, "relationships"):
            couples = [
                {"a": _full_name(conn, row["uid_a"]), "b": _full_name(conn, row["uid_b"])}
                for row in conn.execute(
                    "SELECT uid_a, uid_b FROM relationships WHERE established_at>=? AND established_at<?",
                    (start_ts, end_ts),
                ).fetchall()
            ]

        career_rows = []
        if _table_exists(conn, "careers"):
            career_rows = [
                {
                    "name": _full_name(conn, row["uid"]),
                    "career": CAREER_NAMES.get(row["career_key"], row["career_key"]),
                }
                for row in conn.execute(
                    "SELECT uid, career_key FROM careers WHERE chosen_at>=? AND chosen_at<?",
                    (start_ts, end_ts),
                ).fetchall()
            ]

        forest_runs = []
        forest_slain = 0
        if _table_exists(conn, "forest_runs"):
            forest_runs = [
                {
                    "name": _full_name(conn, row["uid"]),
                    "depth": row["depth"],
                    "galleons": row["galleons"],
                }
                for row in conn.execute(
                    "SELECT uid, MAX(depth) AS depth, SUM(pending_galleons) AS galleons "
                    "FROM forest_runs WHERE phase='retreated' AND updated_at>=? AND updated_at<? "
                    "GROUP BY uid ORDER BY depth DESC, galleons DESC LIMIT 6",
                    (start_ts, end_ts),
                ).fetchall()
            ]
        if _table_exists(conn, "forest_defeated"):
            forest_slain = conn.execute(
                "SELECT COUNT(*) FROM forest_defeated WHERE defeated_at>=? AND defeated_at<?",
                (start_ts, end_ts),
            ).fetchone()[0]

        shifts = homework_awards = 0
        if _table_exists(conn, "work_daily"):
            shifts = conn.execute(
                "SELECT COALESCE(SUM(count),0) FROM work_daily WHERE day BETWEEN ? AND ?",
                (start_day, end_day),
            ).fetchone()[0]
        if _table_exists(conn, "daily_rewards"):
            homework_awards = conn.execute(
                "SELECT COUNT(*) FROM daily_rewards WHERE day BETWEEN ? AND ? "
                "AND reward_key='homework_complete'",
                (start_day, end_day),
            ).fetchone()[0]

        students = [
            dict(row)
            for row in conn.execute(
                "SELECT p.uid, p.name, p.surname, p.house, "
                "COALESCE(SUM(s.exp),0) AS total_exp FROM players p "
                "LEFT JOIN subject_exp s ON s.uid=p.uid WHERE p.house!='' "
                "GROUP BY p.uid ORDER BY total_exp DESC LIMIT 5"
            ).fetchall()
        ]
        houses = []
        for row in conn.execute("SELECT * FROM house_points").fetchall():
            item = dict(row)
            item["avg_points"] = (
                row["total_points"] / row["member_count"] if row["member_count"] else 0.0
            )
            houses.append(item)
        houses.sort(key=lambda row: row["avg_points"], reverse=True)

        return {
            "start_day": start_day,
            "end_day": end_day,
            "school_year": year,
            "is_published": end_day == year_end,
            "live_day": live_day,
            "newcomers": newcomers,
            "spells": spells,
            "duels": duels,
            "couples": couples,
            "careers": career_rows,
            "forest_runs": forest_runs,
            "forest_slain": forest_slain,
            "shifts": shifts,
            "homework_awards": homework_awards,
            "students": students,
            "houses": houses,
            "archive_days": archive_days(live_day),
        }
    finally:
        conn.close()


def build_issue(end_day: int | None = None) -> dict:
    """读取已出版快照；未结业的当前学年则生成实时预览。"""
    live_day = current_day()
    requested_day = max(1, min(end_day or live_day, live_day))
    year = school_year(requested_day)
    year_end = YEAR_RANGES[year][1]
    conn = _connect()
    try:
        _ensure_issue_table(conn)
        row = conn.execute(
            "SELECT data_json FROM newspaper_issues WHERE school_year=?", (year,)
        ).fetchone()
        if row:
            issue = json.loads(row["data_json"])
            issue["live_day"] = live_day
            issue["archive_days"] = archive_days(live_day)
            return issue
    finally:
        conn.close()
    return _build_live_issue(min(requested_day, year_end))


def publish_issue(end_day: int) -> dict:
    """结业日只保存一次，确保旧报的榜单和新闻不会随当前数据漂移。"""
    issue = _build_live_issue(end_day)
    year = issue["school_year"]
    if end_day != YEAR_RANGES[year][1]:
        return issue
    snapshot = dict(issue)
    snapshot.pop("archive_days", None)
    snapshot.pop("live_day", None)
    conn = _connect()
    try:
        _ensure_issue_table(conn)
        conn.execute(
            "INSERT OR IGNORE INTO newspaper_issues "
            "(school_year,start_day,end_day,data_json,published_at) VALUES (?,?,?,?,?)",
            (year, issue["start_day"], issue["end_day"],
             json.dumps(snapshot, ensure_ascii=False), int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()
    return build_issue(end_day)


def build_text(end_day: int | None = None) -> str:
    issue = build_issue(end_day)
    lines = [
        "🗞️《霍格沃茨校报》",
        f"{issue['school_year']}年级特刊 · 第{issue['start_day']}—{issue['end_day']}天",
    ]
    if issue["newcomers"]:
        lines.extend(
            [
                "",
                "🎩 新生与分院",
                "、".join(f"{row['name']}（{row['house']}）" for row in issue["newcomers"])
                + "完成了入学手续。",
            ]
        )
    if issue["spells"]:
        lines.extend(
            [
                "",
                "🪄 本周魔法进展",
                "；".join(f"{row['name']}学会{row['amount']}个新魔咒" for row in issue["spells"])
                + "。",
            ]
        )
    if issue["duels"]:
        lines.extend(
            [
                "",
                "⚔️ 决斗俱乐部",
                "；".join(f"{row['name']}获胜{row['wins']}场" for row in issue["duels"]) + "。",
            ]
        )
    if issue["couples"]:
        lines.extend(
            [
                "",
                "💌 校园传闻",
                "、".join(f"{row['a']}与{row['b']}" for row in issue["couples"])
                + "确认正在交往。消息来源拒绝透露姓名。",
            ]
        )
    if issue.get("forest_runs") or issue.get("forest_slain"):
        parts = []
        if issue.get("forest_runs"):
            deepest = issue["forest_runs"][0]
            parts.append(f"{deepest['name']}一路摸到第{deepest['depth']}层，是本学年走得最深的")
            if len(issue["forest_runs"]) > 1:
                parts.append(
                    "另有"
                    + "、".join(f"{row['name']}(第{row['depth']}层)" for row in issue["forest_runs"][1:4])
                    + "平安归来"
                )
        if issue.get("forest_slain"):
            parts.append(f"全校累计{issue['forest_slain']}次首度击退禁林生物")
        lines.extend(
            [
                "",
                "🌲 禁林通报",
                "；".join(parts) + "。校方重申：禁林依旧禁止学生进入。",
            ]
        )
    if issue["careers"]:
        lines.extend(
            [
                "",
                "🎓 毕业去向",
                "、".join(f"{row['name']}成为{row['career']}" for row in issue["careers"]) + "。",
            ]
        )
    if issue["shifts"] or issue["homework_awards"]:
        lines.extend(
            [
                "",
                "🧹 城堡勤工俭学",
                f"学生们共完成{issue['shifts']}份零工，"
                f"{issue['homework_awards']}人次按时完成了当天全部作业。",
            ]
        )
    lines.extend(["", "🏆 本期榜单"])
    if issue["students"]:
        lines.append(
            "个人：" + "、".join(
                f"{i + 1}.{row['name']} {row['total_exp']}分"
                for i, row in enumerate(issue["students"][:3])
            )
        )
    if issue["houses"]:
        lines.append(
            "学院：" + "、".join(
                f"{i + 1}.{row['house']} 人均{row['avg_points']:.1f}"
                for i, row in enumerate(issue["houses"])
            )
        )
    lines.extend(["", "——本报内容可能被皮皮鬼擅自添油加醋。"])
    return "\n".join(lines)


def publish_text(end_day: int) -> str:
    publish_issue(end_day)
    return build_text(end_day)

import difflib
import re
import time
from datetime import date

from . import storage

storage.init_db()

# ======================== 字段映射 ========================

FIELD_MAP = {
    "时间段": "time_range", "timerange": "time_range",
    "恋综名": "name", "name": "name",
    "年份": "start_year", "year": "start_year",
    "状态": "status", "status": "status",
    "皮相": "character", "character": "character",
    "性向": "orientation", "orientation": "orientation",
    "主题": "theme", "theme": "theme",
    "角色名": "role_name", "rolename": "role_name",
    "角色类型": "role_type", "roletype": "role_type",
    "性别": "gender", "gender": "gender",
    "结局": "outcome", "outcome": "outcome",
}

FIELD_LABELS = {
    "status": "状态", "character": "皮相", "orientation": "性向", "theme": "主题",
    "role_name": "角色名", "role_type": "角色类型", "gender": "性别", "outcome": "结局",
}

TEXT_FIELDS = ("status", "character", "orientation", "theme", "role_name", "role_type", "gender", "outcome")

ENTRY_TEMPLATE = (
    "/录入档期\n时间段：\n恋综名：\n年份：\n状态：\n皮相：\n性向：\n主题：\n角色名：\n角色类型：\n性别：\n结局："
)

# ======================== 时间工具 ========================

_RANGE_RE = re.compile(r"^(\d{2})(\d{2})\s+(\d{2})(\d{2})$")


def _max_day(month: int) -> int:
    if month == 2:
        return 29
    if month in (4, 6, 9, 11):
        return 30
    return 31


def parse_time_range(range_str: str) -> dict:
    """解析 'MMDD MMDD' 格式的时间段。返回 {valid, start_month, start_day, end_month, end_day, error}。"""
    m = _RANGE_RE.match((range_str or "").strip())
    if not m:
        return {"valid": False, "error": "格式有误。应为 MMDD MMDD——同年如 0315 0320，跨年如 1201 0201。"}
    sm, sd, em, ed = (int(x) for x in m.groups())
    if not (1 <= sm <= 12 and 1 <= em <= 12):
        return {"valid": False, "error": "月份须在 01 至 12 之间。"}
    if not (1 <= sd <= _max_day(sm)):
        return {"valid": False, "error": f"{sm}月没有{sd}日。"}
    if not (1 <= ed <= _max_day(em)):
        return {"valid": False, "error": f"{em}月没有{ed}日。"}
    if em == sm and ed <= sd:
        return {"valid": False, "error": "同月之内，结束日必须晚于开始日。"}
    return {"valid": True, "start_month": sm, "start_day": sd, "end_month": em, "end_day": ed, "error": None}


def is_cross_year(end_month: int, start_month: int) -> bool:
    return end_month < start_month


def to_date_int(year: int, month: int, day: int) -> int:
    return year * 10000 + month * 100 + day


def days_in_month(year: int, month: int) -> int:
    if month == 12:
        return (date(year + 1, 1, 1) - date(year, 12, 1)).days
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def first_weekday_of_month(year: int, month: int) -> int:
    """返回 0=周日 ... 6=周六，与原脚本保持一致。"""
    return (date(year, month, 1).weekday() + 1) % 7


def validate_date_for_year(year: int, month: int, day: int) -> str | None:
    """校验某年某月是否真的有这一天（例如闰年才有2月29日）。合法返回 None，非法返回错误信息。"""
    if day > days_in_month(year, month):
        return f"{year}年{month}月没有{day}日。核实一下——非闰年的2月只有28天。"
    return None


def parse_year_month(arg1: str | None, arg2: str | None) -> dict:
    """智能解析年月参数，顺序任意，缺省为当前年月。"""
    now = date.today()

    def is_year(n):
        return n is not None and 1900 <= n <= 2100

    def is_month(n):
        return n is not None and 1 <= n <= 12

    def to_int(s):
        try:
            return int(s)
        except (TypeError, ValueError):
            return None

    n1, n2 = to_int(arg1), to_int(arg2)
    if arg1 and arg2:
        if is_year(n1) and is_month(n2):
            return {"year": n1, "month": n2, "error": None}
        if is_month(n1) and is_year(n2):
            return {"year": n2, "month": n1, "error": None}
        return {"error": "参数无效。年份须在 1900-2100 之间，月份须在 1-12 之间。"}
    if arg1:
        if not is_month(n1):
            return {"error": "月份无效。数字，1 至 12。"}
        return {"year": now.year, "month": n1, "error": None}
    return {"year": now.year, "month": now.month, "error": None}


# ======================== CRUD ========================


def find_close_matches(uid: str, name: str, n: int = 3) -> list[str]:
    names = [r["name"] for r in list_schedules(uid)]
    return difflib.get_close_matches(name, names, n=n, cutoff=0.4)


def _suggest_suffix(uid: str, name: str) -> str:
    suggestions = find_close_matches(uid, name)
    return f"。档案里接近的条目：{'、'.join(suggestions)}" if suggestions else ""


def get_schedule(uid: str, name: str) -> dict | None:
    conn = storage.get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM schedules WHERE uid = ? AND name = ?", (uid, name)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_schedules(uid: str) -> list[dict]:
    conn = storage.get_conn()
    try:
        rows = conn.execute("SELECT * FROM schedules WHERE uid = ? ORDER BY start_year, start_month, start_day", (uid,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def find_conflicts(uid: str, skip_name: str, start_val: int, end_val: int) -> list[str]:
    conflicts = []
    for row in list_schedules(uid):
        if row["name"] == skip_name:
            continue
        existing_start = to_date_int(row["start_year"], row["start_month"], row["start_day"])
        existing_end = to_date_int(row["end_year"], row["end_month"], row["end_day"])
        if start_val <= existing_end and end_val >= existing_start:
            conflicts.append(row["name"])
    return conflicts


def save_schedule(
    uid: str,
    name: str,
    start_year: int,
    start_month: int,
    start_day: int,
    end_year: int,
    end_month: int,
    end_day: int,
    extra_fields: dict | None = None,
) -> tuple[bool, list[str]]:
    """新增或覆盖档期，返回 (是否为更新, 撞档的恋综名列表)。"""
    extra_fields = extra_fields or {}
    now = int(time.time())
    conn = storage.get_conn()
    try:
        existing = conn.execute("SELECT id FROM schedules WHERE uid = ? AND name = ?", (uid, name)).fetchone()
        is_update = existing is not None
        columns = {
            "status": "未知", "character": "未知", "orientation": "未知", "theme": "未知",
            "role_name": "未知", "role_type": "未知", "gender": "未知", "outcome": "未知",
        }
        columns.update({k: v for k, v in extra_fields.items() if k in columns and v})
        conn.execute(
            """
            INSERT INTO schedules (
                uid, name, start_year, start_month, start_day, end_year, end_month, end_day,
                status, character, orientation, theme, role_name, role_type, gender, outcome,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (uid, name) DO UPDATE SET
                start_year = excluded.start_year, start_month = excluded.start_month, start_day = excluded.start_day,
                end_year = excluded.end_year, end_month = excluded.end_month, end_day = excluded.end_day,
                status = excluded.status, character = excluded.character, orientation = excluded.orientation,
                theme = excluded.theme, role_name = excluded.role_name, role_type = excluded.role_type,
                gender = excluded.gender, outcome = excluded.outcome,
                reminded_start = 0, reminded_end = 0, updated_at = excluded.updated_at
            """,
            (
                uid, name, start_year, start_month, start_day, end_year, end_month, end_day,
                columns["status"], columns["character"], columns["orientation"], columns["theme"],
                columns["role_name"], columns["role_type"], columns["gender"], columns["outcome"],
                now, now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    start_val = to_date_int(start_year, start_month, start_day)
    end_val = to_date_int(end_year, end_month, end_day)
    conflicts = find_conflicts(uid, name, start_val, end_val)
    return is_update, conflicts


def delete_schedule(uid: str, name: str) -> bool:
    conn = storage.get_conn()
    try:
        cur = conn.execute("DELETE FROM schedules WHERE uid = ? AND name = ?", (uid, name))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def clear_all_schedules(uid: str) -> int:
    conn = storage.get_conn()
    try:
        cur = conn.execute("DELETE FROM schedules WHERE uid = ?", (uid,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def rename_schedule(uid: str, old_name: str, new_name: str) -> tuple[bool, str]:
    if get_schedule(uid, old_name) is None:
        return False, f"档案「{old_name}」不存在{_suggest_suffix(uid, old_name)}"
    if get_schedule(uid, new_name) is not None:
        return False, f"「{new_name}」已被占用。先销毁旧档案，或换一个名称。"
    conn = storage.get_conn()
    try:
        conn.execute("UPDATE schedules SET name = ?, updated_at = ? WHERE uid = ? AND name = ?", (new_name, int(time.time()), uid, old_name))
        conn.commit()
    finally:
        conn.close()
    return True, f"「{old_name}」已更名为「{new_name}」。数据完整保留。"


def modify_field(uid: str, name: str, field_input: str, value: str) -> tuple[bool, str]:
    row = get_schedule(uid, name)
    if row is None:
        return False, f"档案「{name}」不存在{_suggest_suffix(uid, name)}"

    key_norm = field_input.strip().lower().replace(" ", "")
    field_key = FIELD_MAP.get(key_norm) or FIELD_MAP.get(field_input.strip())
    if not field_key or field_key == "name":
        return False, (
            "无此条目。可用项目：时间段、年份、状态、皮相、性向、主题、角色名、角色类型、性别、结局。\n"
            "更改名称，请用 /重命名档期 旧名 新名。"
        )

    conn = storage.get_conn()
    try:
        if field_key == "time_range":
            parsed = parse_time_range(value)
            if not parsed["valid"]:
                return False, parsed["error"]
            cross = is_cross_year(parsed["end_month"], parsed["start_month"])
            end_year = row["start_year"] + 1 if cross else row["start_year"]
            err = (
                validate_date_for_year(row["start_year"], parsed["start_month"], parsed["start_day"])
                or validate_date_for_year(end_year, parsed["end_month"], parsed["end_day"])
            )
            if err:
                return False, err
            conn.execute(
                """UPDATE schedules SET start_month=?, start_day=?, end_month=?, end_day=?, end_year=?,
                   reminded_start=0, reminded_end=0, updated_at=? WHERE uid=? AND name=?""",
                (parsed["start_month"], parsed["start_day"], parsed["end_month"], parsed["end_day"], end_year, int(time.time()), uid, name),
            )
        elif field_key == "start_year":
            year = int(value) if value.strip().isdigit() else None
            if year is None or not (1900 <= year <= 2100):
                return False, "年份无效。四位数字，例如 2025。"
            cross = is_cross_year(row["end_month"], row["start_month"])
            end_year = year + 1 if cross else year
            err = (
                validate_date_for_year(year, row["start_month"], row["start_day"])
                or validate_date_for_year(end_year, row["end_month"], row["end_day"])
            )
            if err:
                return False, err
            conn.execute(
                "UPDATE schedules SET start_year=?, end_year=?, reminded_start=0, reminded_end=0, updated_at=? WHERE uid=? AND name=?",
                (year, end_year, int(time.time()), uid, name),
            )
        else:
            conn.execute(
                f"UPDATE schedules SET {field_key}=?, updated_at=? WHERE uid=? AND name=?",
                (value, int(time.time()), uid, name),
            )
        conn.commit()
    finally:
        conn.close()
    return True, f"「{name}」的 {field_input}，已更新为：{value}"


# ======================== 月份占用计算 ========================


def calc_month_occupied(rows: list[dict], target_year: int, target_month: int) -> dict:
    dim = days_in_month(target_year, target_month)
    occupied = [False] * (dim + 1)
    active_shows = []

    month_start_val = to_date_int(target_year, target_month, 1)
    month_end_val = to_date_int(target_year, target_month, dim)

    for row in rows:
        start_val = to_date_int(row["start_year"], row["start_month"], row["start_day"])
        end_val = to_date_int(row["end_year"], row["end_month"], row["end_day"])
        if end_val < month_start_val or start_val > month_end_val:
            continue

        start_day = row["start_day"] if (row["start_year"] == target_year and row["start_month"] == target_month) else 1
        end_day = row["end_day"] if (row["end_year"] == target_year and row["end_month"] == target_month) else dim

        for d in range(start_day, end_day + 1):
            occupied[d] = True
        active_shows.append({"name": row["name"], "start_day": start_day, "end_day": end_day})

    return {"occupied": occupied, "days_in_month": dim, "active_shows": active_shows}


# ======================== 年度统计 ========================


def get_year_stats(uid: str, year: int | None) -> dict:
    rows = list_schedules(uid)
    today = date.today()
    if year:
        target_start = to_date_int(year, 1, 1)
        target_end = to_date_int(year, 12, 31)
        year_label = f"{year}年"
    else:
        year = today.year
        target_start = to_date_int(year, 1, 1)
        target_end = to_date_int(year, today.month, today.day)
        year_label = f"{year}年（截至今日）"

    total = 0
    characters, orientations, genders, outcomes, themes = [], [], [], [], []
    active_ranges = []

    for row in rows:
        start_val = to_date_int(row["start_year"], row["start_month"], row["start_day"])
        end_val = to_date_int(row["end_year"], row["end_month"], row["end_day"])
        if end_val < target_start or start_val > target_end:
            continue
        total += 1
        if row["character"] != "未知":
            characters.append((row["name"], row["character"]))
        if row["orientation"] != "未知":
            orientations.append(row["orientation"])
        if row["gender"] != "未知":
            genders.append(row["gender"])
        if row["outcome"] != "未知":
            outcomes.append(row["outcome"])
        if row["theme"] != "未知":
            themes.append(row["theme"])
        active_ranges.append((max(start_val, target_start), min(end_val, target_end)))

    def split(v):
        return v // 10000, (v % 10000) // 100, v % 100

    sy, sm, sd = split(target_start)
    ey, em, ed = split(target_end)
    cur = date(sy, sm, sd)
    end_date = date(ey, em, ed)

    total_days = covered_days = weekday_covered = weekend_covered = 0
    while cur <= end_date:
        total_days += 1
        cur_val = to_date_int(cur.year, cur.month, cur.day)
        if any(a <= cur_val <= b for a, b in active_ranges):
            covered_days += 1
            if cur.weekday() >= 5:
                weekend_covered += 1
            else:
                weekday_covered += 1
        cur = date.fromordinal(cur.toordinal() + 1)

    def distrib(values):
        if not values:
            return []
        counts = {}
        for v in values:
            counts[v] = counts.get(v, 0) + 1
        total_v = len(values)
        return sorted(
            [(v, c, round(c / total_v * 100, 1)) for v, c in counts.items()],
            key=lambda x: -x[1],
        )

    return {
        "year_label": year_label,
        "total": total,
        "characters": characters,
        "orientation_dist": distrib(orientations),
        "gender_dist": distrib(genders),
        "outcome_dist": distrib(outcomes),
        "theme_dist": distrib(themes),
        "covered_days": covered_days,
        "total_days": total_days,
        "covered_percent": round(covered_days / total_days * 100, 1) if total_days else 0.0,
        "weekday_covered": weekday_covered,
        "weekend_covered": weekend_covered,
    }


# ======================== 到期提醒 ========================


def get_reminder_candidates() -> dict:
    """返回 {starting_tomorrow: [...], ending_today: [...]}，均为未提醒过的记录。
    用 <= 而不是 = 匹配，这样机器人某天9点重启/宕机错过了任务，第二天还能补发，不会永久丢失提醒。
    """
    today = date.today()
    tomorrow_val = to_date_int(*_date_plus(today, 1))
    today_val = to_date_int(today.year, today.month, today.day)

    conn = storage.get_conn()
    try:
        starting = conn.execute(
            """
            SELECT * FROM schedules
            WHERE reminded_start = 0
              AND (start_year * 10000 + start_month * 100 + start_day) <= ?
            """,
            (tomorrow_val,),
        ).fetchall()
        ending = conn.execute(
            """
            SELECT * FROM schedules
            WHERE reminded_end = 0
              AND (end_year * 10000 + end_month * 100 + end_day) <= ?
            """,
            (today_val,),
        ).fetchall()
        return {"starting_tomorrow": [dict(r) for r in starting], "ending_today": [dict(r) for r in ending]}
    finally:
        conn.close()


def _date_plus(d: date, days: int) -> tuple[int, int, int]:
    nd = date.fromordinal(d.toordinal() + days)
    return nd.year, nd.month, nd.day


def mark_reminded(schedule_id: int, *, field: str) -> None:
    conn = storage.get_conn()
    try:
        conn.execute(f"UPDATE schedules SET {field} = 1 WHERE id = ?", (schedule_id,))
        conn.commit()
    finally:
        conn.close()


# ======================== HE对象 ========================


def set_he_partner(uid: str, name: str, qq: str) -> tuple[bool, str]:
    if get_schedule(uid, name) is None:
        return False, f"档案「{name}」不存在{_suggest_suffix(uid, name)}"
    conn = storage.get_conn()
    try:
        conn.execute(
            "UPDATE schedules SET he_partner_qq = ?, updated_at = ? WHERE uid = ? AND name = ?",
            (qq, int(time.time()), uid, name),
        )
        conn.commit()
    finally:
        conn.close()
    return True, f"已归档。「{name}」关联对象：{qq}"


def get_he_shows(uid: str, qq: str) -> list[str]:
    conn = storage.get_conn()
    try:
        rows = conn.execute(
            "SELECT name FROM schedules WHERE uid = ? AND he_partner_qq = ? ORDER BY start_year, start_month, start_day",
            (uid, qq),
        ).fetchall()
        return [r["name"] for r in rows]
    finally:
        conn.close()


# ======================== 投递一表 ========================


def add_submission(
    uid: str, name: str, start_year: int, start_month: int, start_day: int,
    end_year: int, end_month: int, end_day: int,
) -> bool:
    """新增或覆盖一条投递记录，返回是否为覆盖已有记录。"""
    conn = storage.get_conn()
    try:
        existing = conn.execute("SELECT id FROM submissions WHERE uid = ? AND name = ?", (uid, name)).fetchone()
        conn.execute(
            """
            INSERT INTO submissions (uid, name, start_year, start_month, start_day, end_year, end_month, end_day, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (uid, name) DO UPDATE SET
                start_year = excluded.start_year, start_month = excluded.start_month, start_day = excluded.start_day,
                end_year = excluded.end_year, end_month = excluded.end_month, end_day = excluded.end_day,
                created_at = excluded.created_at
            """,
            (uid, name, start_year, start_month, start_day, end_year, end_month, end_day, int(time.time())),
        )
        conn.commit()
        return existing is not None
    finally:
        conn.close()


def list_submissions(uid: str) -> list[dict]:
    conn = storage.get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM submissions WHERE uid = ? ORDER BY created_at", (uid,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_submission(uid: str, name: str) -> dict | None:
    conn = storage.get_conn()
    try:
        row = conn.execute("SELECT * FROM submissions WHERE uid = ? AND name = ?", (uid, name)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def find_close_submission_matches(uid: str, name: str, n: int = 3) -> list[str]:
    names = [r["name"] for r in list_submissions(uid)]
    return difflib.get_close_matches(name, names, n=n, cutoff=0.4)


def delete_submission(uid: str, name: str) -> bool:
    conn = storage.get_conn()
    try:
        cur = conn.execute("DELETE FROM submissions WHERE uid = ? AND name = ?", (uid, name))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def accept_submission(uid: str, name: str) -> tuple[bool, str, dict | None]:
    """把一条投递记录转为正式档期。成功时返回 (True, '', 落库后的档期信息)；失败时返回 (False, 错误信息, None)。"""
    sub = get_submission(uid, name)
    if sub is None:
        suggestion = find_close_submission_matches(uid, name)
        hint = f"。接近的条目：{'、'.join(suggestion)}" if suggestion else ""
        return False, f"没有「{name}」的投递记录{hint}", None

    is_update, conflicts = save_schedule(
        uid, name, sub["start_year"], sub["start_month"], sub["start_day"],
        sub["end_year"], sub["end_month"], sub["end_day"],
    )
    delete_submission(uid, name)
    return True, "", {
        "start_year": sub["start_year"], "start_month": sub["start_month"], "start_day": sub["start_day"],
        "end_year": sub["end_year"], "end_month": sub["end_month"], "end_day": sub["end_day"],
        "is_update": is_update, "conflicts": conflicts,
    }

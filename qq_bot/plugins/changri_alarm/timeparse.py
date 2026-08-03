import re
from datetime import datetime, timedelta

WEEKDAY_MAP = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}


class TimeParseError(ValueError):
    pass


def parse_reminder_time(expr: str, now: datetime | None = None) -> tuple[datetime, str]:
    now = now or datetime.now()
    expr = expr.strip()

    m = re.fullmatch(r"(\d+)\s*分钟后", expr)
    if m:
        return now + timedelta(minutes=int(m.group(1))), "none"

    m = re.fullmatch(r"(\d+)\s*小时后", expr)
    if m:
        return now + timedelta(hours=int(m.group(1))), "none"

    m = re.fullmatch(r"每天\s*(\d{1,2}):(\d{2})", expr)
    if m:
        target = _next_time_today_or_tomorrow(now, int(m.group(1)), int(m.group(2)))
        return target, "daily"

    m = re.fullmatch(r"每周([一二三四五六日天])\s*(\d{1,2}):(\d{2})", expr)
    if m:
        weekday = WEEKDAY_MAP[m.group(1)]
        hour, minute = int(m.group(2)), int(m.group(3))
        target = _next_weekday_time(now, weekday, hour, minute)
        return target, f"weekly:{weekday}"

    m = re.fullmatch(r"(\d{1,2}):(\d{2})", expr)
    if m:
        target = _next_time_today_or_tomorrow(now, int(m.group(1)), int(m.group(2)))
        return target, "none"

    raise TimeParseError(
        f"看不懂时间「{expr}」，支持格式：10分钟后 / 2小时后 / 18:30 / 每天8:00 / 每周一20:00"
    )


def _next_time_today_or_tomorrow(now: datetime, hour: int, minute: int) -> datetime:
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def _next_weekday_time(now: datetime, weekday: int, hour: int, minute: int) -> datetime:
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    days_ahead = (weekday - now.weekday()) % 7
    target += timedelta(days=days_ahead)
    if target <= now:
        target += timedelta(days=7)
    return target


def compute_next_trigger(prev_trigger: datetime, repeat: str) -> datetime | None:
    if repeat == "daily":
        return prev_trigger + timedelta(days=1)
    if repeat.startswith("weekly:"):
        return prev_trigger + timedelta(days=7)
    return None

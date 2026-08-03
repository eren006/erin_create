import re

_RANGE_RE = re.compile(r"^(\d{1,2}):?(\d{2})-(\d{1,2}):?(\d{2})$")


def parse_time_range(time_str: str) -> tuple[int, int] | None:
    """把 "11:00-12:00" 或 "1100-1200" 解析成 (开始分钟, 结束分钟)。"""
    m = _RANGE_RE.match(time_str.strip())
    if not m:
        return None
    sh, sm, eh, em = (int(x) for x in m.groups())
    return sh * 60 + sm, eh * 60 + em


def is_valid_time_format(time_str: str) -> bool:
    rng = parse_time_range(time_str)
    if rng is None:
        return False
    start, end = rng
    sh, sm = divmod(start, 60)
    eh, em = divmod(end, 60)
    if not (0 <= sh <= 23 and 0 <= sm <= 59 and 0 <= eh <= 23 and 0 <= em <= 59):
        return False
    return end > start


def time_conflict(day_a: str, time_a: str, day_b: str, time_b: str) -> bool:
    if day_a != day_b:
        return False
    range_a = parse_time_range(time_a)
    range_b = parse_time_range(time_b)
    if range_a is None or range_b is None:
        return False
    a_start, a_end = range_a
    b_start, b_end = range_b
    return not (a_end <= b_start or a_start >= b_end)


def parse_and_validate_time(
    raw: str, allowed_ranges: list[str] | None = None, min_duration: int = 0
) -> tuple[bool, str]:
    """返回 (是否合法, 合法时返回标准化的time字符串 / 不合法时返回错误信息)。"""
    raw = raw.strip()
    if not is_valid_time_format(raw):
        return False, "时间格式不对，要用 11:00-12:00 这种格式"
    start, end = parse_time_range(raw)
    if allowed_ranges:
        ok = False
        for allowed in allowed_ranges:
            allowed_range = parse_time_range(allowed)
            if allowed_range and allowed_range[0] <= start and end <= allowed_range[1]:
                ok = True
                break
        if not ok:
            return False, f"时间不在允许范围内：{', '.join(allowed_ranges)}"
    if end - start < min_duration:
        return False, f"时长至少要 {min_duration} 分钟"
    return True, raw

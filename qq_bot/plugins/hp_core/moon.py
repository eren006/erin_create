"""月相：每7天一次满月。

限时内容的时间基准都放在这里，免得散落在各处。
满月夜禁林深处会出现狼人，狼毒药剂也只有那几天才有意义。
"""

MOON_CYCLE = 7
FULL_MOON_OFFSET = 0  # Day 7、14、21、28 是满月

PHASE_NAMES = ("满月", "亏凸月", "下弦月", "残月", "新月", "娥眉月", "上弦月", "盈凸月")


def is_full_moon(day: int) -> bool:
    return day > 0 and day % MOON_CYCLE == FULL_MOON_OFFSET


def phase_name(day: int) -> str:
    if day <= 0:
        return "新月"
    if is_full_moon(day):
        return "满月"
    # 距上一次满月过了几天，用来挑一个像样的相位名
    since = day % MOON_CYCLE
    return PHASE_NAMES[since % len(PHASE_NAMES)]


def days_to_full_moon(day: int) -> int:
    if day <= 0:
        return MOON_CYCLE
    if is_full_moon(day):
        return 0
    return MOON_CYCLE - (day % MOON_CYCLE)


def next_full_moon(day: int) -> int:
    return day + days_to_full_moon(day) if not is_full_moon(day) else day

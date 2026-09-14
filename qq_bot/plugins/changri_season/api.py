import re
from datetime import datetime

from plugins.changri_core.api import get_conn, get_current_day, get_setting, set_current_day, set_setting
from plugins.changri_core.archive_client import request_archive

MMDD_RE = re.compile(r"^\d{4}$")


def has_active_season(platform: str) -> bool:
    return get_setting(f"season:{platform}:active") == "1"


def is_role_storage_empty(platform: str) -> bool:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM accounts WHERE platform = ?", (platform,)
        ).fetchone()
        return row["c"] == 0
    finally:
        conn.close()


def get_season_info(platform: str) -> dict:
    return {
        "active": has_active_season(platform),
        "name": get_setting(f"season:{platform}:name"),
        "mode": get_setting(f"season:{platform}:mode"),
        "schedule_start": get_setting(f"season:{platform}:schedule_start"),
        "schedule_end": get_setting(f"season:{platform}:schedule_end"),
        "supplement_end": get_setting(f"season:{platform}:supplement_end"),
    }


def _validate_mmdd(value: str) -> bool:
    return bool(MMDD_RE.match(value))


async def create_season(
    platform: str,
    name: str,
    mode: str,
    schedule_start: str,
    schedule_end: str,
    supplement_end: str = "",
) -> tuple[bool, str]:
    if has_active_season(platform):
        return False, "已经有一个进行中的季度了，先「/结束季度」再开新的"
    if not is_role_storage_empty(platform):
        return False, "角色档案不是空的，开新季度前需要先清空角色数据"
    if mode not in ("review", "no_review"):
        return False, "mode 必须是 review 或 no_review"
    for label, value in (("开始日期", schedule_start), ("结束日期", schedule_end)):
        if not _validate_mmdd(value):
            return False, f"{label}格式不对，要 4 位数字 MMDD（比如 0715）"
    if supplement_end and not _validate_mmdd(supplement_end):
        return False, "补档结束日期格式不对，要 4 位数字 MMDD"

    ok, body = await request_archive(
        "POST",
        "/api/new_season",
        {
            "name": name,
            "mode": mode,
            "schedule_start": schedule_start,
            "schedule_end": schedule_end,
            "supplement_end": supplement_end,
        },
    )
    if not ok:
        return False, f"创建失败：{body.get('error', '未知错误')}"

    set_setting(f"season:{platform}:active", "1")
    set_setting(f"season:{platform}:name", name)
    set_setting(f"season:{platform}:mode", mode)
    set_setting(f"season:{platform}:schedule_start", schedule_start)
    set_setting(f"season:{platform}:schedule_end", schedule_end)
    set_setting(f"season:{platform}:supplement_end", supplement_end)
    set_current_day(platform, "D100")
    return True, (
        f"季度「{name}」已创建，档期 {schedule_start}-{schedule_end}\n"
        f"当前天数已临时设为 D100（占位，防止开季筹备期被当成正式游戏日），"
        f"档期开始日（{schedule_start}）0 点会自动切换为 D0，也可以随时手动「/设置天数 D0」提前切换"
    )


def try_auto_start_day(platform: str) -> str | None:
    """档期开始日 0 点检查：天数如果还停在开季占位值 D100，自动切换成 D0。"""
    if not has_active_season(platform):
        return None
    if get_current_day(platform) != "D100":
        return None
    schedule_start = get_setting(f"season:{platform}:schedule_start")
    if not schedule_start or datetime.now().strftime("%m%d") != schedule_start:
        return None

    set_current_day(platform, "D0")
    try:
        from plugins.changri_wish.api import expire_open_wishes

        expire_open_wishes(platform)
    except ImportError:
        pass
    return "档期开始，当前天数已自动设为 D0"


async def update_schedule(
    platform: str, schedule_start: str, schedule_end: str, supplement_end: str = ""
) -> tuple[bool, str]:
    if not has_active_season(platform):
        return False, "现在没有进行中的季度"
    for label, value in (("开始日期", schedule_start), ("结束日期", schedule_end)):
        if not _validate_mmdd(value):
            return False, f"{label}格式不对，要 4 位数字 MMDD"
    if supplement_end and not _validate_mmdd(supplement_end):
        return False, "补档结束日期格式不对，要 4 位数字 MMDD"

    ok, body = await request_archive(
        "POST",
        "/api/update_schedule",
        {
            "schedule_start": schedule_start,
            "schedule_end": schedule_end,
            "supplement_end": supplement_end,
        },
    )
    if not ok:
        return False, f"修改失败：{body.get('error', '未知错误')}"

    set_setting(f"season:{platform}:schedule_start", schedule_start)
    set_setting(f"season:{platform}:schedule_end", schedule_end)
    set_setting(f"season:{platform}:supplement_end", supplement_end)
    return True, f"档期已更新为 {schedule_start}-{schedule_end}"


async def end_season(platform: str) -> tuple[bool, str]:
    if not has_active_season(platform):
        return False, "现在没有进行中的季度"
    ok, body = await request_archive("POST", "/api/end_season", {})
    if not ok:
        return False, f"结束失败：{body.get('error', '未知错误')}"

    set_setting(f"season:{platform}:active", "0")
    public_url = body.get("public_url", "")
    name = get_setting(f"season:{platform}:name", "")
    msg = f"季度「{name}」已结束"
    if public_url:
        msg += f"\n存档地址：{public_url}"
    return True, msg

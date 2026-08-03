import re

from plugins.changri_core.api import get_conn, get_setting, set_setting
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
    return True, f"季度「{name}」已创建，档期 {schedule_start}-{schedule_end}"


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

import re
from datetime import date

import nonebot
from nonebot import logger, on_command
from nonebot.adapters.qq import MessageEvent, MessageSegment
from nonebot.params import CommandArg

from . import api

nonebot.require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler  # noqa: E402

YUCA_BOT_SELF_ID = "102254477"
REMINDER_HOUR = 9

# ======================== 通用渲染 ========================


def _suggest_hint(uid: str, name: str) -> str:
    suggestions = api.find_close_matches(uid, name)
    return f"。档案里接近的条目：{'、'.join(suggestions)}" if suggestions else ""


def _fmt_range(sy: int, sm: int, sd: int, ey: int, em: int, ed: int) -> tuple[str, bool]:
    cross = ey != sy
    if cross:
        return f"{sy}/{sm:02d}{sd:02d} — {ey}/{em:02d}{ed:02d}", True
    return f"{sy}/{sm:02d}{sd:02d}-{em:02d}{ed:02d}", False


def _render_confirm(name, sy, sm, sd, ey, em, ed, is_update, conflicts, fields=None):
    range_str, cross = _fmt_range(sy, sm, sd, ey, em, ed)
    action = "档案已更新" if is_update else "档案已建立"
    lines = [f"▪ {action}{'（跨年度）' if cross else ''}", "", f"**恋综名**：{name}", f"**时间段**：{range_str}"]
    if fields:
        for key in api.TEXT_FIELDS:
            if fields.get(key, "未知") != "未知":
                lines.append(f"**{api.FIELD_LABELS[key]}**：{fields[key]}")
    else:
        lines.append("")
        lines.append(
            f"其余条目暂缺，标记为「未知」。需要补全时执行 `/修改 {name} 项目 内容`\n"
            "（可用项目：状态/皮相/性向/主题/角色名/角色类型/性别/结局）"
        )
    if conflicts:
        lines.append("")
        lines.append("⚠ **时间重叠警告** —— 以下档案与此冲突：")
        for c in conflicts:
            lines.append(f"· {c}")
    return MessageSegment.markdown("\n".join(lines))


async def _send_long_markdown(matcher, lines: list[str], max_len: int = 1500):
    chunks, cur, cur_len = [], [], 0
    for line in lines:
        if cur_len + len(line) + 1 > max_len and cur:
            chunks.append("\n".join(cur))
            cur, cur_len = [], 0
        cur.append(line)
        cur_len += len(line) + 1
    if cur:
        chunks.append("\n".join(cur))
    if not chunks:
        chunks = [""]
    for chunk in chunks[:-1]:
        await matcher.send(MessageSegment.markdown(chunk))
    await matcher.finish(MessageSegment.markdown(chunks[-1]))


# ======================== 帮助 ========================

HELP_TEXT = """# 🗂 语擦事务处理程序

### 档案建立与维护
- `/新建档期 恋综名 开始日期 结束日期` —— 建立新档案，其余条目留空，稍后补全。例：`/新建档期 花好月圆 0315 0320`
- `/录入档期` —— 一次性登记全部条目
- `/修改 名 项目 内容` —— 修订指定条目
- `/重命名档期 旧名 新名` —— 更改名称，数据保留
- `/删除档期 名` —— 销毁指定档案
- `/清空档期 确认` —— 销毁全部档案。此操作不可逆

### 投递与录取
- `/投递一表 恋综名 开始日期 结束日期` —— 登记一份待批申请
- `/已投递一表` —— 调阅所有未决申请
- `/录取一表 恋综名` —— 批准申请，转为正式档案

### HE对象
- `/HE对象 QQ号 恋综名` —— 将该档案的对象关联至指定人员
- `/HE记录 QQ号` —— 调阅与该人员相关的全部档案

### 检索
- `/查档期 名` —— 调阅完整档案
- `/我的日历` —— 按年份列出全部档案
- `/本月档期 [年] [月]` —— 本月执行中的项目与空档
- `/月视图 [年] [月]` —— 月历视图

### 统计
- `/本年数据 [年]` —— 年度数据汇总（默认统计至今日）

### 跑团骰子
- `/rd [表达式]` —— 掷骰。例：`/rd d20`、`/rd 3d6+2`、`/rd 100`。留空默认1d100
- `/ra [属性名] 数值` —— 属性检定，依COC7版规则判定。例：`/ra 侦查 70`

### 每日运势
- `/每日运势` —— 查询今日运势。结果每人每天固定一次，重复查询不变

### 通知
档期临近开始或结束时，本程序会发送私信提醒——前提是你已将其列为好友

---
时间段格式统一为 MMDD MMDD（跨年如 1201 0201），所有涉及日期的指令均适用此格式
"""

help_cmd = on_command("档期帮助")


@help_cmd.handle()
async def handle_help():
    await help_cmd.finish(MessageSegment.markdown(HELP_TEXT))


# ======================== 录入档期（多行文本，一次性全字段） ========================


def _parse_entry_content(content: str) -> tuple[dict, str | None]:
    fields = {
        "time_range": None, "name": None, "start_year": date.today().year,
        "status": "未知", "character": "未知", "orientation": "未知", "theme": "未知",
        "role_name": "未知", "role_type": "未知", "gender": "未知", "outcome": "未知",
    }
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(.+?)[:：](.*)$", line)
        if not m:
            continue
        key_raw, value = m.group(1).strip(), m.group(2).strip()
        key_norm = key_raw.lower().replace(" ", "")
        field_key = api.FIELD_MAP.get(key_norm) or api.FIELD_MAP.get(key_raw)
        if not field_key:
            continue
        if field_key == "start_year":
            if not value:
                continue
            if not value.isdigit() or not (1900 <= int(value) <= 2100):
                return fields, f"年份「{value}」无效。四位数字，例如 2025，或留空。"
            fields["start_year"] = int(value)
        elif value:
            fields[field_key] = value
    return fields, None


add_cmd = on_command("录入档期")


@add_cmd.handle()
async def handle_add(event: MessageEvent, args=CommandArg()):
    raw = args.extract_plain_text().strip()
    if not raw:
        await add_cmd.finish(
            f"格式如下，复制后填写：\n\n{api.ENTRY_TEMPLATE}\n\n"
            "时间段格式：MMDD MMDD\n同年示例：0315 0320\n跨年示例：1201 0201\n\n"
            "只需记录时间段、其余条目稍后补全的话，执行 /新建档期 恋综名 开始日期 结束日期 即可"
        )
        return
    fields, err = _parse_entry_content(raw)
    if err:
        await add_cmd.finish(err)
        return
    if not fields["name"]:
        await add_cmd.finish("缺少必填项「恋综名」。")
        return
    if "|" in fields["name"]:
        await add_cmd.finish("恋综名不可包含字符 |。")
        return
    if not fields["time_range"]:
        await add_cmd.finish("缺少必填项「时间段」，格式例如 0315 0320。")
        return
    parsed = api.parse_time_range(fields["time_range"])
    if not parsed["valid"]:
        await add_cmd.finish(parsed["error"])
        return

    cross = api.is_cross_year(parsed["end_month"], parsed["start_month"])
    end_year = fields["start_year"] + 1 if cross else fields["start_year"]
    err = (
        api.validate_date_for_year(fields["start_year"], parsed["start_month"], parsed["start_day"])
        or api.validate_date_for_year(end_year, parsed["end_month"], parsed["end_day"])
    )
    if err:
        await add_cmd.finish(err)
        return
    uid = event.get_user_id()
    is_update, conflicts = api.save_schedule(
        uid, fields["name"], fields["start_year"], parsed["start_month"], parsed["start_day"],
        end_year, parsed["end_month"], parsed["end_day"],
        extra_fields={k: fields[k] for k in api.TEXT_FIELDS},
    )
    await add_cmd.finish(_render_confirm(
        fields["name"], fields["start_year"], parsed["start_month"], parsed["start_day"],
        end_year, parsed["end_month"], parsed["end_day"], is_update, conflicts, fields=fields,
    ))


# ======================== 新建档期（恋综名 + 开始日期 + 结束日期，直接打） ========================

new_schedule_cmd = on_command("新建档期")


@new_schedule_cmd.handle()
async def handle_new_schedule(event: MessageEvent, args=CommandArg()):
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 3:
        await new_schedule_cmd.finish(
            "格式：/新建档期 恋综名 开始日期 结束日期\n"
            "例：/新建档期 花好月圆 0315 0320（跨年如 1201 0201）"
        )
        return
    name, start_raw, end_raw = parts
    if "|" in name:
        await new_schedule_cmd.finish("恋综名不可包含字符 |。")
        return
    parsed = api.parse_time_range(f"{start_raw} {end_raw}")
    if not parsed["valid"]:
        await new_schedule_cmd.finish(parsed["error"])
        return

    cross = api.is_cross_year(parsed["end_month"], parsed["start_month"])
    start_year = date.today().year
    end_year = start_year + 1 if cross else start_year
    err = (
        api.validate_date_for_year(start_year, parsed["start_month"], parsed["start_day"])
        or api.validate_date_for_year(end_year, parsed["end_month"], parsed["end_day"])
    )
    if err:
        await new_schedule_cmd.finish(err)
        return
    uid = event.get_user_id()
    is_update, conflicts = api.save_schedule(
        uid, name, start_year, parsed["start_month"], parsed["start_day"],
        end_year, parsed["end_month"], parsed["end_day"],
    )
    await new_schedule_cmd.finish(_render_confirm(
        name, start_year, parsed["start_month"], parsed["start_day"],
        end_year, parsed["end_month"], parsed["end_day"], is_update, conflicts,
    ))


# ======================== 查档期 ========================

query_cmd = on_command("查档期")


@query_cmd.handle()
async def handle_query(event: MessageEvent, args=CommandArg()):
    name = args.extract_plain_text().strip()
    if not name:
        await query_cmd.finish("格式：/查档期 恋综名")
        return
    uid = event.get_user_id()
    row = api.get_schedule(uid, name)
    if row is None:
        await query_cmd.finish(f"档案「{name}」不存在{_suggest_hint(uid, name)}")
        return
    range_str, cross = _fmt_range(
        row["start_year"], row["start_month"], row["start_day"], row["end_year"], row["end_month"], row["end_day"]
    )
    lines = [f"🗂 **{name}**{'（跨年度）' if cross else ''}", "", f"时间段：{range_str}"]
    for key in api.TEXT_FIELDS:
        lines.append(f"{api.FIELD_LABELS[key]}：{row[key]}")
    if row["he_partner_qq"]:
        lines.append(f"HE对象：{row['he_partner_qq']}")
    await query_cmd.finish(MessageSegment.markdown("\n".join(lines)))


# ======================== HE对象 ========================

he_partner_cmd = on_command("HE对象")


@he_partner_cmd.handle()
async def handle_he_partner(event: MessageEvent, args=CommandArg()):
    parts = args.extract_plain_text().strip().split(maxsplit=1)
    if len(parts) != 2 or not parts[0].isdigit():
        await he_partner_cmd.finish("格式：/HE对象 QQ号 恋综名")
        return
    qq, name = parts
    ok, msg = api.set_he_partner(event.get_user_id(), name, qq)
    await he_partner_cmd.finish(msg)


he_record_cmd = on_command("HE记录")


@he_record_cmd.handle()
async def handle_he_record(event: MessageEvent, args=CommandArg()):
    qq = args.extract_plain_text().strip()
    if not qq or not qq.isdigit():
        await he_record_cmd.finish("格式：/HE记录 QQ号")
        return
    shows = api.get_he_shows(event.get_user_id(), qq)
    if not shows:
        await he_record_cmd.finish(f"{qq}——查无关联档案。可用 /HE对象 {qq} 恋综名 建立关联。")
        return
    lines = [f"🗂 与 {qq} 关联的档案", ""] + [f"{i}. {name}" for i, name in enumerate(shows, 1)]
    await he_record_cmd.finish(MessageSegment.markdown("\n".join(lines)))


# ======================== 投递一表 / 已投递一表 / 录取一表 ========================

submit_cmd = on_command("投递一表")


@submit_cmd.handle()
async def handle_submit(event: MessageEvent, args=CommandArg()):
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 3:
        await submit_cmd.finish(
            "格式：/投递一表 恋综名 开始日期 结束日期\n"
            "例：/投递一表 花好月圆 0315 0320（跨年如 1201 0201）"
        )
        return
    name, start_raw, end_raw = parts
    if "|" in name:
        await submit_cmd.finish("恋综名不可包含字符 |。")
        return
    parsed = api.parse_time_range(f"{start_raw} {end_raw}")
    if not parsed["valid"]:
        await submit_cmd.finish(parsed["error"])
        return

    cross = api.is_cross_year(parsed["end_month"], parsed["start_month"])
    start_year = date.today().year
    end_year = start_year + 1 if cross else start_year
    err = (
        api.validate_date_for_year(start_year, parsed["start_month"], parsed["start_day"])
        or api.validate_date_for_year(end_year, parsed["end_month"], parsed["end_day"])
    )
    if err:
        await submit_cmd.finish(err)
        return

    is_update = api.add_submission(
        event.get_user_id(), name, start_year, parsed["start_month"], parsed["start_day"],
        end_year, parsed["end_month"], parsed["end_day"],
    )
    range_str, _ = _fmt_range(start_year, parsed["start_month"], parsed["start_day"], end_year, parsed["end_month"], parsed["end_day"])
    action = "已更新" if is_update else "已登记"
    await submit_cmd.finish(f"申请{action}：{name}（{range_str}）\n批准后执行 /录取一表 {name}，转为正式档案")


submitted_list_cmd = on_command("已投递一表")


@submitted_list_cmd.handle()
async def handle_submitted_list(event: MessageEvent):
    subs = api.list_submissions(event.get_user_id())
    if not subs:
        await submitted_list_cmd.finish("无未决申请。")
        return
    lines = ["# 🗂 未决申请", ""]
    for i, s in enumerate(subs, 1):
        range_str, _ = _fmt_range(
            s["start_year"], s["start_month"], s["start_day"], s["end_year"], s["end_month"], s["end_day"]
        )
        lines.append(f"{i}. **{s['name']}** — {range_str}")
    await submitted_list_cmd.finish(MessageSegment.markdown("\n".join(lines)))


accept_submission_cmd = on_command("录取一表")


@accept_submission_cmd.handle()
async def handle_accept_submission(event: MessageEvent, args=CommandArg()):
    name = args.extract_plain_text().strip()
    if not name:
        await accept_submission_cmd.finish("格式：/录取一表 恋综名")
        return
    ok, msg, result = api.accept_submission(event.get_user_id(), name)
    if not ok:
        await accept_submission_cmd.finish(msg)
        return
    await accept_submission_cmd.finish(_render_confirm(
        name, result["start_year"], result["start_month"], result["start_day"],
        result["end_year"], result["end_month"], result["end_day"],
        result["is_update"], result["conflicts"],
    ))


# ======================== 修改 / 重命名 / 删除 ========================

modify_cmd = on_command("修改")


MODIFY_DATE_FIELDS = ("时间段", "timerange", "年份", "year")


@modify_cmd.handle()
async def handle_modify(event: MessageEvent, args=CommandArg()):
    parts = args.extract_plain_text().strip().split(maxsplit=2)
    if len(parts) != 3:
        await modify_cmd.finish("参数不足。格式：/修改 恋综名 项目 内容")
        return
    name, field, value = parts
    uid = event.get_user_id()
    ok, msg = api.modify_field(uid, name, field, value)
    if not ok:
        await modify_cmd.finish(msg)
        return

    reply = msg
    if field.strip().lower().replace(" ", "") in MODIFY_DATE_FIELDS:
        row = api.get_schedule(uid, name)
        start_val = api.to_date_int(row["start_year"], row["start_month"], row["start_day"])
        end_val = api.to_date_int(row["end_year"], row["end_month"], row["end_day"])
        conflicts = api.find_conflicts(uid, name, start_val, end_val)
        if conflicts:
            reply += "\n\n⚠ **时间重叠警告** —— 以下档案与此冲突：\n" + "\n".join(f"· {c}" for c in conflicts)
    await modify_cmd.finish(reply)


rename_cmd = on_command("重命名档期")


@rename_cmd.handle()
async def handle_rename(event: MessageEvent, args=CommandArg()):
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 2:
        await rename_cmd.finish("格式：/重命名档期 旧名 新名")
        return
    ok, msg = api.rename_schedule(event.get_user_id(), parts[0], parts[1])
    await rename_cmd.finish(msg)


delete_cmd = on_command("删除档期")


@delete_cmd.handle()
async def handle_delete(event: MessageEvent, args=CommandArg()):
    name = args.extract_plain_text().strip()
    if not name:
        await delete_cmd.finish("参数不足。格式：/删除档期 恋综名")
        return
    uid = event.get_user_id()
    if api.delete_schedule(uid, name):
        await delete_cmd.finish(f"「{name}」已销毁。")
        return
    await delete_cmd.finish(f"档案「{name}」不存在{_suggest_hint(uid, name)}")


clear_all_cmd = on_command("清空档期")


@clear_all_cmd.handle()
async def handle_clear_all(event: MessageEvent, args=CommandArg()):
    uid = event.get_user_id()
    if args.extract_plain_text().strip() != "确认":
        count = len(api.list_schedules(uid))
        if count == 0:
            await clear_all_cmd.finish("无档案可清空。")
            return
        await clear_all_cmd.finish(f"⚠ 此操作将销毁全部 {count} 份档案，且不可撤回。\n确认执行请发送「/清空档期 确认」")
        return
    count = api.clear_all_schedules(uid)
    await clear_all_cmd.finish(f"已销毁 {count} 份档案。")


# ======================== 我的日历 ========================


def _build_calendar_lines(rows: list[dict]) -> list[str]:
    year_groups: dict[int, list[tuple[int, str]]] = {}
    for row in rows:
        sy, sm, sd = row["start_year"], row["start_month"], row["start_day"]
        ey, em, ed = row["end_year"], row["end_month"], row["end_day"]
        cross = ey != sy

        role_parts = []
        if row["role_name"] != "未知":
            role_parts.append(row["role_name"])
        if row["role_type"] != "未知":
            role_parts.append(row["role_type"])
        if row["gender"] != "未知":
            role_parts.append(row["gender"])
        if row["outcome"] != "未知":
            role_parts.append(f"结:{row['outcome']}")
        role_str = f" [{'/'.join(role_parts)}]" if role_parts else ""

        base_info_parts = [row[k] for k in ("status", "character", "orientation", "theme") if row[k] != "未知"]
        base_info = " · " + " ".join(base_info_parts) if base_info_parts else ""

        if cross:
            first = f"{sy}/{sm:02d}{sd:02d}-1231"
            second = f"{ey}/0101-{em:02d}{ed:02d}"
            year_groups.setdefault(sy, []).append(
                (sy * 10000 + sm * 100 + sd, f"▪ **{row['name']}**{role_str}\n   {first}{base_info}")
            )
            year_groups.setdefault(ey, []).append(
                (ey * 10000 + 101, f"▪ **{row['name']}**{role_str}（续）\n   {second}{base_info}")
            )
        else:
            range_str = f"{sy}/{sm:02d}{sd:02d}-{em:02d}{ed:02d}"
            year_groups.setdefault(sy, []).append(
                (sy * 10000 + sm * 100 + sd, f"▪ **{row['name']}**{role_str}\n   {range_str}{base_info}")
            )

    lines = ["# 🗂 档案总览", ""]
    for year in sorted(year_groups):
        lines.append(f"### {year} 年")
        for _, line in sorted(year_groups[year], key=lambda x: x[0]):
            lines.append(line)
        lines.append("")
    return lines


calendar_cmd = on_command("我的日历")


@calendar_cmd.handle()
async def handle_calendar(event: MessageEvent):
    rows = api.list_schedules(event.get_user_id())
    if not rows:
        await calendar_cmd.finish("档案是空的。没有可供调阅的记录。")
        return
    await _send_long_markdown(calendar_cmd, _build_calendar_lines(rows))


# ======================== 本月档期 ========================

this_month_cmd = on_command("本月档期")


@this_month_cmd.handle()
async def handle_this_month(event: MessageEvent, args=CommandArg()):
    uid = event.get_user_id()
    rows = api.list_schedules(uid)
    if not rows:
        await this_month_cmd.finish("无档案记录。")
        return
    parts = args.extract_plain_text().strip().split()
    ym = api.parse_year_month(parts[0] if len(parts) > 0 else None, parts[1] if len(parts) > 1 else None)
    if ym.get("error"):
        await this_month_cmd.finish(ym["error"])
        return
    year, month = ym["year"], ym["month"]
    result = api.calc_month_occupied(rows, year, month)

    lines = [f"# 🗂 {year}年{month}月 执行概览", ""]
    active = sorted(result["active_shows"], key=lambda s: s["start_day"])
    if not active:
        lines.append("**执行中的项目**：本月无。")
    else:
        lines.append(f"**执行中的项目**（{len(active)} 项）：")
        for s in active:
            lines.append(f"- {s['name']}（{s['start_day']:02d}日-{s['end_day']:02d}日）")

    occupied, dim = result["occupied"], result["days_in_month"]
    free_intervals, start = [], None
    for d in range(1, dim + 1):
        if not occupied[d] and start is None:
            start = d
        if occupied[d] and start is not None:
            free_intervals.append((start, d - 1))
            start = None
    if start is not None:
        free_intervals.append((start, dim))

    lines.append("")
    lines.append("**空档**：")
    if not free_intervals:
        lines.append("本月无空档，全部被占用。")
    else:
        lines.append("、".join(f"{s}日" if s == e else f"{s}-{e}日" for s, e in free_intervals))

    await this_month_cmd.finish(MessageSegment.markdown("\n".join(lines)))


# ======================== 月视图 ========================

month_view_cmd = on_command("月视图")


@month_view_cmd.handle()
async def handle_month_view(event: MessageEvent, args=CommandArg()):
    uid = event.get_user_id()
    rows = api.list_schedules(uid)
    if not rows:
        await month_view_cmd.finish("无档案记录。")
        return
    parts = args.extract_plain_text().strip().split()
    ym = api.parse_year_month(parts[0] if len(parts) > 0 else None, parts[1] if len(parts) > 1 else None)
    if ym.get("error"):
        await month_view_cmd.finish(ym["error"])
        return
    year, month = ym["year"], ym["month"]
    result = api.calc_month_occupied(rows, year, month)
    occupied, dim = result["occupied"], result["days_in_month"]
    first_dow = api.first_weekday_of_month(year, month)

    grid_lines = []
    row_cells = ["    "] * first_dow
    for d in range(1, dim + 1):
        cell = f"[{d:2d}]" if occupied[d] else f" {d:2d} "
        row_cells.append(cell)
        if (first_dow + d) % 7 == 0 or d == dim:
            grid_lines.append("".join(row_cells))
            row_cells = []
    grid = "\n".join([" 日   一   二   三   四   五   六"] + grid_lines)

    text = f"# 🗂 {year}年{month}月 月历\n\n```\n{grid}\n```\n标注 `[ ]` 的日期为执行中项目所占。"
    await month_view_cmd.finish(MessageSegment.markdown(text))


# ======================== 本年数据 ========================


def _year_stats_markdown(stats: dict) -> str:
    lines = [f"# 🗂 {stats['year_label']}汇总", "", f"**涉及项目**：{stats['total']} 项"]

    if stats["characters"]:
        lines += ["", "**皮相**", "| 恋综 | 皮相 |", "|---|---|"]
        for name, character in stats["characters"]:
            lines.append(f"| {name} | {character} |")
    else:
        lines += ["", "**皮相**：无记录"]

    def table(title, dist):
        if not dist:
            return ["", f"**{title}**：无非未知记录"]
        out = ["", f"**{title}分布**（共 {sum(c for _, c, _ in dist)} 项非未知）", "| 项 | 数量 | 占比 |", "|---|---|---|"]
        for v, c, pct in dist:
            out.append(f"| {v} | {c} | {pct}% |")
        return out

    lines += table("性向", stats["orientation_dist"])
    lines += table("性别", stats["gender_dist"])
    lines += table("结局", stats["outcome_dist"])
    lines += table("主题题材", stats["theme_dist"])

    lines.append("")
    lines.append(f"**在场天数**：{stats['covered_days']} 天（占比 {stats['covered_percent']}%）")
    lines.append(f"- 平日：{stats['weekday_covered']} 天")
    lines.append(f"- 周末：{stats['weekend_covered']} 天")
    return "\n".join(lines)


year_stats_cmd = on_command("本年数据")


@year_stats_cmd.handle()
async def handle_year_stats(event: MessageEvent, args=CommandArg()):
    uid = event.get_user_id()
    if not api.list_schedules(uid):
        await year_stats_cmd.finish("无档案记录。")
        return
    text = args.extract_plain_text().strip()
    year = None
    if text:
        if not text.isdigit() or not (1900 <= int(text) <= 2100):
            await year_stats_cmd.finish("年份无效。四位数字，例如 2025。")
            return
        year = int(text)
    stats = api.get_year_stats(uid, year)
    await year_stats_cmd.finish(MessageSegment.markdown(_year_stats_markdown(stats)))


# ======================== 到期提醒 ========================


@scheduler.scheduled_job("cron", hour=REMINDER_HOUR, minute=0, id="yuca_calendar_reminder")
async def _daily_reminder():
    candidates = api.get_reminder_candidates()
    if not candidates["starting_tomorrow"] and not candidates["ending_today"]:
        return
    bots = nonebot.get_bots()
    bot = bots.get(YUCA_BOT_SELF_ID) or next(iter(bots.values()), None)
    if bot is None:
        logger.warning("[语擦日历] 有到期提醒但没有已连接的Bot实例，本轮跳过")
        return

    today = date.today()

    for row in candidates["starting_tomorrow"]:
        start_d = date(row["start_year"], row["start_month"], row["start_day"])
        delta = (start_d - today).days
        when = "明日" if delta == 1 else ("今日" if delta == 0 else "已经")
        text = (
            f"情报：《{row['name']}》定于{when}启动。"
            f"时间段 {row['start_month']:02d}-{row['start_day']:02d} 至 {row['end_month']:02d}-{row['end_day']:02d}。"
        )
        try:
            await bot.send_to_c2c(openid=row["uid"], message=text)
            api.mark_reminded(row["id"], field="reminded_start")
        except Exception as e:
            logger.warning(f"[语擦日历] 开始提醒「{row['name']}」发送失败：{e}")

    for row in candidates["ending_today"]:
        end_d = date(row["end_year"], row["end_month"], row["end_day"])
        when = "今日为最后一日，注意收尾。" if end_d == today else "已经结束，注意收尾——本程序可能因重启延误了准时通知。"
        text = f"情报：《{row['name']}》{when}"
        try:
            await bot.send_to_c2c(openid=row["uid"], message=text)
            api.mark_reminded(row["id"], field="reminded_end")
        except Exception as e:
            logger.warning(f"[语擦日历] 结束提醒「{row['name']}」发送失败：{e}")

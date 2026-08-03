import secrets
import time

from nonebot import get_driver, logger, on_command
from nonebot.adapters import Bot as BaseBot
from nonebot.adapters import Event as BaseEvent
from nonebot.adapters.qq import C2CMessageCreateEvent, GroupMessageCreateEvent, MessageEvent, MessageSegment
from nonebot.exception import IgnoredException
from nonebot.message import event_preprocessor
from nonebot.params import CommandArg

from . import api, archive_client

PLATFORM = "qq"

CHANGRI_BOT_SELF_ID = "102100533"

NOTIFICATION_ICONS = {
    "短信": "💬",
    "礼物": "🎁",
    "邀约": "💌",
}

driver = get_driver()


@driver.on_startup
async def _ensure_admin_password() -> None:
    if api.get_admin_password() is None:
        password = secrets.token_urlsafe(6)
        api.set_admin_password(password)
        logger.warning(f"[长日核心] 首次启动，已生成管理员密令：{password}（请自行保存，仅在此处明文显示一次）")


bind_role_cmd = on_command("创建新角色", aliases={"绑定角色"})


@bind_role_cmd.handle()
async def handle_bind_role(event: MessageEvent, args=CommandArg()):
    role_name = args.extract_plain_text().strip()
    if not role_name:
        await bind_role_cmd.finish("用法：/创建新角色 <角色名>")
    if archive_client.is_archive_enabled():
        from plugins.changri_season.api import has_active_season

        if not has_active_season(PLATFORM):
            await bind_role_cmd.finish("当前没有活跃的季度，请联系管理员发起「/创建新季度」后再创建角色")
    uid = event.get_user_id()
    if api.get_uid_by_role_name(PLATFORM, role_name) not in (None, api.get_primary_uid(PLATFORM, uid)):
        await bind_role_cmd.finish(f"角色名「{role_name}」已被占用，换一个吧")
    gid = event.group_openid if isinstance(event, GroupMessageCreateEvent) else None
    api.bind_role(PLATFORM, uid, role_name, gid)
    await bind_role_cmd.finish(f"角色创建成功：{role_name}")




grant_admin_cmd = on_command("授予管理员")


@grant_admin_cmd.handle()
async def handle_grant_admin(event: MessageEvent, args=CommandArg()):
    password = args.extract_plain_text().strip()
    uid = event.get_user_id()
    if api.is_admin(PLATFORM, uid):
        await grant_admin_cmd.finish("你已经是管理员了")
    if not password or password != api.get_admin_password():
        await grant_admin_cmd.finish("密令不对")
    api.grant_admin(PLATFORM, uid)
    await grant_admin_cmd.finish("授权成功，你现在是管理员了")


revoke_self_admin_cmd = on_command("收回管理员")


@revoke_self_admin_cmd.handle()
async def handle_revoke_self_admin(event: MessageEvent):
    uid = event.get_user_id()
    if api.revoke_admin(PLATFORM, uid):
        await revoke_self_admin_cmd.finish("已收回你的管理员身份")
    await revoke_self_admin_cmd.finish("你本来就不是管理员")


change_password_cmd = on_command("更改密令")


@change_password_cmd.handle()
async def handle_change_password(event: MessageEvent, args=CommandArg()):
    if not api.is_admin(PLATFORM, event.get_user_id()):
        await change_password_cmd.finish("只有管理员能改密令")
    new_password = args.extract_plain_text().strip()
    if not new_password:
        await change_password_cmd.finish("用法：/更改密令 <新密令>")
    api.set_admin_password(new_password)
    await change_password_cmd.finish("密令已更新")


list_admins_cmd = on_command("管理员列表")


@list_admins_cmd.handle()
async def handle_list_admins(event: MessageEvent):
    if not api.is_admin(PLATFORM, event.get_user_id()):
        await list_admins_cmd.finish("只有管理员能查看")
    admins = api.list_admins(PLATFORM)
    if not admins:
        await list_admins_cmd.finish("目前没有管理员")
    lines = []
    for uid in admins:
        role_name = api.get_role_name(PLATFORM, uid)
        lines.append(f"- {role_name or '(未绑定角色)'}")
    await list_admins_cmd.finish("管理员列表：\n" + "\n".join(lines))


clear_admins_cmd = on_command("清空管理员")


@clear_admins_cmd.handle()
async def handle_clear_admins(event: MessageEvent):
    if not api.is_admin(PLATFORM, event.get_user_id()):
        await clear_admins_cmd.finish("只有管理员能清空")
    api.clear_admins(PLATFORM)
    await clear_admins_cmd.finish("管理员名单已清空")


reset_season_data_cmd = on_command("清空季度数据")


@reset_season_data_cmd.handle()
async def handle_reset_season_data(event: MessageEvent, args=CommandArg()):
    if not api.is_admin(PLATFORM, event.get_user_id()):
        await reset_season_data_cmd.finish("权限不足，仅管理员可用")
    if args.extract_plain_text().strip() != "确认":
        await reset_season_data_cmd.finish(
            "⚠️ 这会清空所有角色绑定、资料、钥匙、邮箱（不影响背包/心愿/信件/拍卖等游戏内容数据）\n"
            "确认要清空的话发「/清空季度数据 确认」"
        )
        return
    api.clear_role_storage(PLATFORM)
    await reset_season_data_cmd.finish("✅ 角色数据已清空，现在可以「/创建新季度」了")


# ── 群激活 ──────────────────────────────────────────────────────────────

ACTIVATE_CMD_TEXT = "激活"
ACTIVATION_EXEMPT_COMMANDS = ("激活", "设置激活码", "取消激活", "已激活群列表")


activate_cmd = on_command(ACTIVATE_CMD_TEXT)


@activate_cmd.handle()
async def handle_activate(event: GroupMessageCreateEvent, args=CommandArg()):
    code = args.extract_plain_text().strip()
    real_code = api.get_activation_code()
    if not real_code:
        await activate_cmd.finish("还没有设置激活码，联系管理员先「/设置激活码 新码」")
        return
    if api.is_group_activated(PLATFORM, event.group_openid):
        await activate_cmd.finish("本群已经激活过了")
        return
    if code != real_code:
        await activate_cmd.finish("激活码不对")
        return
    api.activate_group(PLATFORM, event.group_openid, event.get_user_id())
    await activate_cmd.finish("✅ 本群已激活，现在可以正常使用所有指令了")


set_activation_code_cmd = on_command("设置激活码")


@set_activation_code_cmd.handle()
async def handle_set_activation_code(event: MessageEvent, args=CommandArg()):
    if not api.is_admin(PLATFORM, event.get_user_id()):
        await set_activation_code_cmd.finish("权限不足，仅管理员可用")
        return
    code = args.extract_plain_text().strip()
    if not code:
        await set_activation_code_cmd.finish("用法：/设置激活码 新码")
        return
    api.set_activation_code(code)
    await set_activation_code_cmd.finish("激活码已更新")


deactivate_group_cmd = on_command("取消激活")


@deactivate_group_cmd.handle()
async def handle_deactivate_group(event: GroupMessageCreateEvent):
    if not api.is_admin(PLATFORM, event.get_user_id()):
        await deactivate_group_cmd.finish("权限不足，仅管理员可用")
        return
    if api.deactivate_group(PLATFORM, event.group_openid):
        await deactivate_group_cmd.finish("本群已取消激活")
        return
    await deactivate_group_cmd.finish("本群本来就没激活")


activated_groups_cmd = on_command("已激活群列表")


@activated_groups_cmd.handle()
async def handle_activated_groups(event: MessageEvent):
    if not api.is_admin(PLATFORM, event.get_user_id()):
        await activated_groups_cmd.finish("权限不足，仅管理员可用")
        return
    groups = api.list_activated_groups(PLATFORM)
    if not groups:
        await activated_groups_cmd.finish("还没有任何已激活的群")
        return
    await activated_groups_cmd.finish(f"已激活 {len(groups)} 个群")


@event_preprocessor
async def _check_group_activated(bot: BaseBot, event: BaseEvent):
    if bot.self_id != CHANGRI_BOT_SELF_ID:
        return  # 群激活/C2C屏蔽只针对长日机器人自己，其他挂在同进程的机器人不受影响
    if isinstance(event, C2CMessageCreateEvent):
        raise IgnoredException("private chat disabled")
    if not isinstance(event, GroupMessageCreateEvent):
        return
    text = event.get_plaintext().strip()
    if any(text.startswith(f"/{cmd}") for cmd in ACTIVATION_EXEMPT_COMMANDS):
        return
    if api.is_group_activated(PLATFORM, event.group_openid):
        return
    if text.startswith("/"):
        try:
            await bot.send_to_group(
                group_openid=event.group_openid,
                message="本群还没激活，请管理员发送「/激活 激活码」",
            )
        except Exception as e:
            logger.warning(f"[群激活] 提示发送失败：{e}")
    raise IgnoredException("group not activated")


bind_extra_cmd = on_command("绑定额外账号")


@bind_extra_cmd.handle()
async def handle_bind_extra(event: MessageEvent, args=CommandArg()):
    main_role_name = args.extract_plain_text().strip()
    if not main_role_name:
        await bind_extra_cmd.finish("用法：/绑定额外账号 <主账号角色名>（在小号里发这条指令）")
    main_uid = api.get_uid_by_role_name(PLATFORM, main_role_name)
    if main_uid is None:
        await bind_extra_cmd.finish(f"找不到角色名「{main_role_name}」对应的账号")
    uid = event.get_user_id()
    if main_uid == uid:
        await bind_extra_cmd.finish("不能把自己绑定成自己的额外账号")
    api.bind_extra_account(PLATFORM, uid, main_uid)
    await bind_extra_cmd.finish(f"绑定成功，此账号现在归属于「{main_role_name}」")


# ── 存档配置 ──────────────────────────────────────────────────────────────

archive_config_cmd = on_command("存档设置")


@archive_config_cmd.handle()
async def handle_archive_config(event: MessageEvent, args=CommandArg()):
    if not api.is_admin(PLATFORM, event.get_user_id()):
        await archive_config_cmd.finish("权限不足，仅管理员可用")
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 2:
        await archive_config_cmd.finish("用法：/存档设置 rp_archive地址 api_token")
        return
    base_url, token = parts
    archive_client.set_archive_config(base_url, token)
    await archive_config_cmd.finish("存档服务器地址和token已保存")


archive_toggle_cmd = on_command("存档开关")


@archive_toggle_cmd.handle()
async def handle_archive_toggle(event: MessageEvent):
    if not api.is_admin(PLATFORM, event.get_user_id()):
        await archive_toggle_cmd.finish("权限不足，仅管理员可用")
    new_state = not archive_client.is_archive_enabled()
    archive_client.set_archive_enabled(new_state)
    await archive_toggle_cmd.finish(f"存档功能现在{'已启用' if new_state else '已禁用'}")


archive_status_cmd = on_command("存档状态")


@archive_status_cmd.handle()
async def handle_archive_status(event: MessageEvent):
    if not api.is_admin(PLATFORM, event.get_user_id()):
        await archive_status_cmd.finish("权限不足，仅管理员可用")
    base_url, token = archive_client.get_archive_config()
    enabled = archive_client.is_archive_enabled()
    await archive_status_cmd.finish(
        f"存档功能：{'已启用' if enabled else '已禁用'}\n"
        f"地址：{base_url or '（未配置）'}\n"
        f"token：{'已配置' if token else '（未配置）'}"
    )


# ── 子系统总开关 ──────────────────────────────────────────────────────────────

FEATURE_LABELS = {
    "wish": "心愿",
    "gift": "礼物",
    "auction": "拍卖",
    "appointment": "私约",
    "letters": "写信",
}

feature_toggle_cmd = on_command("系统开关")


@feature_toggle_cmd.handle()
async def handle_feature_toggle(event: MessageEvent, args=CommandArg()):
    if not api.is_admin(PLATFORM, event.get_user_id()):
        await feature_toggle_cmd.finish("权限不足，仅管理员可用")
    text = args.extract_plain_text().strip()
    if not text:
        lines = ["⚙️ 子系统开关"]
        for key, label in FEATURE_LABELS.items():
            state = "✅开启" if api.is_feature_enabled(key) else "❌关闭"
            lines.append(f"- {label}（{key}）：{state}")
        lines.append("\n用法：/系统开关 <名字> 开/关")
        await feature_toggle_cmd.finish("\n".join(lines))
        return
    parts = text.split()
    if len(parts) != 2 or parts[1] not in ("开", "关"):
        await feature_toggle_cmd.finish("用法：/系统开关 <名字> 开/关")
        return
    key_input, action = parts
    key = key_input if key_input in api.FEATURE_KEYS else next(
        (k for k, v in FEATURE_LABELS.items() if v == key_input), None
    )
    if key is None:
        await feature_toggle_cmd.finish(f"没有「{key_input}」这个子系统")
        return
    api.set_feature_enabled(key, action == "开")
    await feature_toggle_cmd.finish(f"{FEATURE_LABELS[key]}系统已{action}")


# ── 天数 ──────────────────────────────────────────────────────────────

set_day_cmd = on_command("设置天数")


@set_day_cmd.handle()
async def handle_set_day(event: MessageEvent, args=CommandArg()):
    if not api.is_admin(PLATFORM, event.get_user_id()):
        await set_day_cmd.finish("权限不足，仅管理员可用")
    day = args.extract_plain_text().strip()
    if not day:
        await set_day_cmd.finish("用法：/设置天数 D0")
        return
    api.set_current_day(PLATFORM, day)
    extra_msg = ""
    try:
        from plugins.changri_wish.api import expire_open_wishes

        expired_count = expire_open_wishes(PLATFORM)
        if expired_count:
            extra_msg = f"\n心愿池已清空，{expired_count} 个未摘的心愿作废（悬赏物品已退回）"
    except ImportError:
        pass
    await set_day_cmd.finish(f"当前天数已设为 {day}{extra_msg}")


current_day_cmd = on_command("当前天数")


@current_day_cmd.handle()
async def handle_current_day(event: MessageEvent):
    day = api.get_current_day(PLATFORM)
    await current_day_cmd.finish(f"当前天数：{day}" if day else "还没有设置天数")


unbind_extra_cmd = on_command("解绑额外账号")


@unbind_extra_cmd.handle()
async def handle_unbind_extra(event: MessageEvent):
    if api.unbind_extra_account(PLATFORM, event.get_user_id()):
        await unbind_extra_cmd.finish("已解绑")
    await unbind_extra_cmd.finish("这个账号本来就不是额外账号")


# ── 角色资料 ──────────────────────────────────────────────────────────────

role_card_cmd = on_command("角色卡")


@role_card_cmd.handle()
async def handle_role_card(event: MessageEvent):
    uid = event.get_user_id()
    role_name = api.get_role_name(PLATFORM, uid)
    if role_name is None:
        await role_card_cmd.finish("你还没有角色，先用「/创建新角色 <角色名>」创建一个")
    profile = api.get_char_profile(PLATFORM, uid)
    if profile is None:
        api.init_char_profile(PLATFORM, uid)
        profile = api.get_char_profile(PLATFORM, uid)
    await role_card_cmd.finish(
        f"👤 {role_name}\n性别：{profile['gender']}\n年龄：{profile['age']}\n外貌：{profile['look']}\n简介：{profile['bio'] or '（未填写）'}"
    )


view_profile_cmd = on_command("查看资料")


@view_profile_cmd.handle()
async def handle_view_profile(event: MessageEvent, args=CommandArg()):
    role_name = args.extract_plain_text().strip()
    if not role_name:
        await view_profile_cmd.finish("用法：/查看资料 <角色名>")
    target_uid = api.get_uid_by_role_name(PLATFORM, role_name)
    if target_uid is None:
        await view_profile_cmd.finish(f"找不到角色「{role_name}」")
    profile = api.get_char_profile(PLATFORM, target_uid)
    if profile is None:
        await view_profile_cmd.finish(f"{role_name} 还没有填写资料")
    await view_profile_cmd.finish(
        f"{role_name}\n性别：{profile['gender']}\n年龄：{profile['age']}\n外貌：{profile['look']}\n简介：{profile['bio'] or '（未填写）'}"
    )


set_gender_cmd = on_command("设置性别")


@set_gender_cmd.handle()
async def handle_set_gender(event: MessageEvent, args=CommandArg()):
    value = args.extract_plain_text().strip()
    if value not in ("男", "女"):
        await set_gender_cmd.finish("用法：/设置性别 男/女")
    api.set_char_profile(PLATFORM, event.get_user_id(), gender=value)
    await set_gender_cmd.finish("性别已更新")


set_age_cmd = on_command("设置年龄")


@set_age_cmd.handle()
async def handle_set_age(event: MessageEvent, args=CommandArg()):
    value = args.extract_plain_text().strip()
    if not value.isdigit():
        await set_age_cmd.finish("用法：/设置年龄 <数字>")
    api.set_char_profile(PLATFORM, event.get_user_id(), age=int(value))
    await set_age_cmd.finish("年龄已更新")


set_look_cmd = on_command("设置外貌")


@set_look_cmd.handle()
async def handle_set_look(event: MessageEvent, args=CommandArg()):
    value = args.extract_plain_text().strip()
    if not value:
        await set_look_cmd.finish("用法：/设置外貌 <描述>")
    api.set_char_profile(PLATFORM, event.get_user_id(), look=value)
    await set_look_cmd.finish("外貌已更新")


set_bio_cmd = on_command("设置简介")


@set_bio_cmd.handle()
async def handle_set_bio(event: MessageEvent, args=CommandArg()):
    value = args.extract_plain_text().strip()
    if not value:
        await set_bio_cmd.finish("用法：/设置简介 <描述>")
    api.set_char_profile(PLATFORM, event.get_user_id(), bio=value)
    await set_bio_cmd.finish("简介已更新")


# ── 邮箱 ──────────────────────────────────────────────────────────────

mailbox_cmd = on_command("邮箱")


@mailbox_cmd.handle()
async def handle_mailbox(event: MessageEvent, args=CommandArg()):
    uid = event.get_user_id()
    show_all = args.extract_plain_text().strip() == "全部"
    items = api.get_notifications(PLATFORM, uid, unread_only=not show_all)
    if not items:
        await mailbox_cmd.finish("邮箱是空的" if show_all else "没有新消息（发「/邮箱 全部」看历史）")
        return
    lines = ["# 📬 邮箱", ""]
    for n in items:
        icon = NOTIFICATION_ICONS.get(n["category"], "📌")
        when = time.strftime("%m-%d %H:%M", time.localtime(n["created_at"]))
        lines.append(f"**{icon} {n['category']}**　`{when}`")
        lines.append(f"> {n['content']}")
        lines.append("")
    api.mark_notifications_read([n["id"] for n in items])
    await mailbox_cmd.finish(MessageSegment.markdown("\n".join(lines)))


# ── 地点系统 ──────────────────────────────────────────────────────────────

place_cmd = on_command("地点")


@place_cmd.handle()
async def handle_place(event: MessageEvent, args=CommandArg()):
    sub = args.extract_plain_text().strip()
    uid = event.get_user_id()
    if sub == "查看":
        places = api.list_places(PLATFORM)
        enabled = api.is_place_system_enabled()
        user_keys = api.get_user_keys(PLATFORM, uid) if enabled else []
        if not places:
            await place_cmd.finish("暂无地点")
        lines = ["🏢 地点列表"]
        for p in places:
            if not enabled or not p["locked"]:
                tag = "📍"
            elif p["name"] in user_keys:
                tag = "🔑 已解锁"
            else:
                tag = "🔒 需要钥匙"
            desc = f"（{p['desc']}）" if p["desc"] else ""
            lines.append(f"{tag} {p['name']}{desc}")
        await place_cmd.finish("\n".join(lines))
    elif sub == "钥匙":
        role_name = api.get_role_name(PLATFORM, uid)
        if role_name is None:
            await place_cmd.finish("未绑定角色，无法查看钥匙")
        keys = api.get_user_keys(PLATFORM, uid)
        if not keys:
            await place_cmd.finish("你目前没有任何地点钥匙")
        await place_cmd.finish("🔑 你持有的钥匙：\n" + "\n".join(f"- {k}" for k in keys))
    else:
        await place_cmd.finish("用法：/地点 查看 / 地点 钥匙")


place_admin_cmd = on_command("地点管理")


@place_admin_cmd.handle()
async def handle_place_admin(event: MessageEvent, args=CommandArg()):
    uid = event.get_user_id()
    if not api.is_admin(PLATFORM, uid):
        await place_admin_cmd.finish("权限不足，仅管理员可用")
    text = args.extract_plain_text().strip()
    parts = text.split(maxsplit=1)
    if not parts:
        await place_admin_cmd.finish(
            "用法：/地点管理 添加 地点:描述 / 删除 地点 / 开关 地点 / 钥匙 角色名 地点 / 系统开关"
        )
    sub, rest = parts[0], (parts[1] if len(parts) > 1 else "")
    if sub == "添加":
        name, _, desc = rest.replace("：", ":").partition(":")
        name = name.strip()
        if not name:
            await place_admin_cmd.finish("用法：/地点管理 添加 地点:描述")
        api.add_place(PLATFORM, name, desc.strip())
        await place_admin_cmd.finish(f"地点「{name}」已添加")
    elif sub == "删除":
        name = rest.strip()
        if api.remove_place(PLATFORM, name):
            await place_admin_cmd.finish(f"地点「{name}」已删除")
        await place_admin_cmd.finish(f"找不到地点「{name}」")
    elif sub == "开关":
        name = rest.strip()
        result = api.toggle_place_lock(PLATFORM, name)
        if result is None:
            await place_admin_cmd.finish(f"找不到地点「{name}」")
        await place_admin_cmd.finish(f"地点「{name}」现在{'已上锁' if result else '未上锁'}")
    elif sub == "钥匙":
        sub_parts = rest.split(maxsplit=1)
        if len(sub_parts) != 2:
            await place_admin_cmd.finish("用法：/地点管理 钥匙 角色名 地点")
        role_name, place_name = sub_parts
        target_uid = api.get_uid_by_role_name(PLATFORM, role_name)
        if target_uid is None:
            await place_admin_cmd.finish(f"找不到角色「{role_name}」")
        api.grant_place_key(PLATFORM, target_uid, place_name)
        await place_admin_cmd.finish(f"已发放「{place_name}」钥匙给「{role_name}」")
    elif sub == "系统开关":
        new_state = not api.is_place_system_enabled()
        api.set_place_system_enabled(new_state)
        await place_admin_cmd.finish(f"地点系统现在{'已启用' if new_state else '已禁用'}")
    else:
        await place_admin_cmd.finish(
            "用法：/地点管理 添加 地点:描述 / 删除 地点 / 开关 地点 / 钥匙 角色名 地点 / 系统开关"
        )

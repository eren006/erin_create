from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg

import plugins.hp_core as hp_core
from plugins.hp_core import storage as core_storage

from . import romance, storage

storage.init_db()


# ======================== 送礼物 ========================

gift_cmd = on_command("送礼物")


@gift_cmd.handle()
async def handle_gift(event: MessageEvent, args=CommandArg()):
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 2:
        await gift_cmd.finish("用法：/送礼物 礼物名 对方名字（先「/对角巷 礼物」看看有什么）")
        return
    item_input, target_name = parts
    try:
        target_uid = hp_core.resolve(target_name)
        result = romance.send_gift(event.get_user_id(), item_input, target_uid)
    except (romance.RomanceError, hp_core.UnknownPlayerError) as e:
        await gift_cmd.finish(str(e))
        return
    await gift_cmd.finish(
        f"把「{result['name']}」送给了 {target_name}。\n"
        f"TA对你的好感度 +{result['gain']}（现在{result['new_value']}/{romance.AFFECTION_MAX}）。"
    )


# ======================== 调情 ========================

flirt_cmd = on_command("调情")


@flirt_cmd.handle()
async def handle_flirt(event: MessageEvent, args=CommandArg()):
    target_name = args.extract_plain_text().strip()
    if not target_name:
        await flirt_cmd.finish("用法：/调情 对方名字（对同一个人每天一次）")
        return
    try:
        target_uid = hp_core.resolve(target_name)
        result = romance.flirt(event.get_user_id(), target_uid)
    except (romance.RomanceError, hp_core.UnknownPlayerError) as e:
        await flirt_cmd.finish(str(e))
        return
    await flirt_cmd.finish(
        f"{result['line']}\n"
        f"{target_name} 对你的好感度 +{result['gain']}"
        f"（现在{result['new_value']}/{romance.AFFECTION_MAX}）。"
    )


# ======================== 确立关系 / 分手 ========================

confess_cmd = on_command("确立关系")


@confess_cmd.handle()
async def handle_confess(event: MessageEvent, args=CommandArg()):
    target_name = args.extract_plain_text().strip()
    if not target_name:
        await confess_cmd.finish("用法：/确立关系 对方名字")
        return
    try:
        target_uid = hp_core.resolve(target_name)
        result = romance.confess(event.get_user_id(), target_uid)
    except (romance.RomanceError, hp_core.UnknownPlayerError) as e:
        await confess_cmd.finish(str(e))
        return
    await confess_cmd.finish(
        f"在一起了！你和 {target_name} 现在是情侣。\n"
        f"（你对TA {result['mine']}，TA对你 {result['theirs']}）\n"
        "用「/约会 去处」一起出去玩，好感度会涨得更快。"
    )


breakup_cmd = on_command("分手")


@breakup_cmd.handle()
async def handle_breakup(event: MessageEvent):
    try:
        result = romance.break_up(event.get_user_id())
    except romance.RomanceError as e:
        await breakup_cmd.finish(str(e))
        return
    await breakup_cmd.finish(
        f"你和 {core_storage.get_full_name(result['partner'])} 分手了。\n双方好感度各自减半（你对TA {result['mine']}，TA对你 {result['theirs']}）。"
    )


# ======================== 约会 ========================

date_cmd = on_command("约会")


@date_cmd.handle()
async def handle_date(event: MessageEvent, args=CommandArg()):
    activity = args.extract_plain_text().strip()
    if not activity:
        await date_cmd.finish(f"用法：/约会 去处\n可选：{'、'.join(romance.DATE_ACTIVITIES)}")
        return
    try:
        result = romance.go_on_date(event.get_user_id(), activity)
    except romance.RomanceError as e:
        await date_cmd.finish(str(e))
        return
    await date_cmd.finish(
        f"和 {core_storage.get_full_name(result['partner'])} 去了{result['activity']}。\n"
        f"双方好感度 +{result['affection_gain']}（你对TA {result['mine']}，TA对你 {result['theirs']}），"
        f"双方还各涨了{result['subject_exp']}点相关学科经验。\n"
        f"今天约会了{result['today_count']}/{result['daily_limit']}次。"
    )


# ======================== 插足 ========================

interfere_cmd = on_command("插足")


@interfere_cmd.handle()
async def handle_interfere(event: MessageEvent, args=CommandArg()):
    target_name = args.extract_plain_text().strip()
    if not target_name:
        await interfere_cmd.finish("用法：/插足 对方名字")
        return
    try:
        target_uid = hp_core.resolve(target_name)
        result = romance.interfere(event.get_user_id(), target_uid)
    except (romance.RomanceError, hp_core.UnknownPlayerError) as e:
        await interfere_cmd.finish(str(e))
        return
    if result["success"]:
        text = (
            f"插足成功（判定{result['chance']:.0%}）。\n"
            f"{target_name} 和 {core_storage.get_full_name(result['rival'])} 分手了，双方好感度大跌。\n"
            f"TA对你的好感度涨到了 {result['target_favour_to_me']}/{romance.AFFECTION_MAX}，"
            "但要在一起还得双向都到50，继续努力。"
        )
    else:
        text = (
            f"插足失败（判定{result['chance']:.0%}）。\n"
            f"{target_name} 觉得你很不识趣，对你的好感度掉到了 "
            f"{result['target_favour_to_me']}/{romance.AFFECTION_MAX}。"
        )
    await interfere_cmd.finish(text)


# ======================== 我的感情状况 ========================

my_romance_cmd = on_command("我的感情")


@my_romance_cmd.handle()
async def handle_my_romance(event: MessageEvent):
    try:
        result = romance.my_romance(event.get_user_id())
    except romance.RomanceError as e:
        await my_romance_cmd.finish(str(e))
        return
    lines = ["💗 感情状况"]
    lines.append(f"当前对象：{core_storage.get_full_name(result['partner']) if result['partner'] else '单身'}")
    lines.append("")
    lines.append(
        "我喜欢的人："
        + ("、".join(f"{core_storage.get_name(u)}({v})" for u, v in result["liked_by_me"]) or "无")
    )
    lines.append(
        "喜欢我的人："
        + ("、".join(f"{core_storage.get_name(u)}({v})" for u, v in result["likes_me"]) or "无")
    )
    await my_romance_cmd.finish("\n".join(lines))


couples_cmd = on_command("情侣列表")


@couples_cmd.handle()
async def handle_couples(event: MessageEvent):
    rows = storage.list_all_couples()
    if not rows:
        await couples_cmd.finish("学校里还没有一对情侣。")
        return
    lines = ["💗 全校情侣"]
    for r in rows:
        lines.append(f"{core_storage.get_full_name(r['uid_a'])} 💗 {core_storage.get_full_name(r['uid_b'])}")
    await couples_cmd.finish("\n".join(lines))

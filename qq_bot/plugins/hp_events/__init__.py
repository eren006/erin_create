import nonebot
from nonebot import logger, on_command, require
from nonebot.adapters.qq import MessageEvent, MessageSegment
from nonebot.params import CommandArg

import plugins.hp_core as hp_core
from plugins.hp_core import notify as core_notify
from plugins.hp_core import spells as spell_catalog
from plugins.hp_core import storage as core_storage

from . import calendar as hp_calendar
from . import christmas, duel, forest, newsletter, prefect, quidditch, storage

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler  # noqa: E402

PLATFORM = "qq"
CALENDAR_POLL_MINUTES = 10
NOTIFY_DIGEST_MINUTES = 10  # 网页操作汇总播报的间隔


def _fmt_stats(row) -> str:
    return "　".join(f"{quidditch.STAT_LABELS[k]}{row[k] + row[f'broom_{k}_bonus']}" for k in quidditch.STAT_KEYS)


# ======================== 日历调度 ========================


def _fmt_mvp_awards(mvp_awards: dict) -> list[str]:
    lines = []
    for house, award in mvp_awards.items():
        if award:
            lines.append(
                f"{house}：{core_storage.get_full_name(award['uid'])}（{award['position']}，{award['score']}分）"
            )
    if lines:
        lines.insert(0, "🏆 本学年魁地奇MVP（已解锁称号，赛季得分清零重新开始）：")
    return lines


def _fmt_year_end(data: dict) -> str:
    lines = [
        f"📅 {data['grade_ended']}年级结束，学年测验已完成。",
        f"全员升入{data['next_grade']}年级，所有学科经验按90%衰减一些（忘了点东西，正常）。",
        f"参加测验的学生：{data['student_count']}人，用「/我的成绩」查看自己的详细结果。",
    ]
    mvp_lines = _fmt_mvp_awards(data["mvp_awards"])
    if mvp_lines:
        lines.append("")
        lines.extend(mvp_lines)
    return "\n".join(lines)


def _fmt_graduation(data: dict) -> str:
    lines = ["🎓 毕业典礼！七年的（浓缩成三十天的）霍格沃茨生涯，到这里结束了。", ""]
    if data["top_house"]:
        h = data["top_house"]
        lines.append(f"🏆 学院杯归属：{h['house']}（人均{h['avg_points']:.1f}分）")
    if data["top_student"]:
        s = data["top_student"]
        full = f"{s['name']}·{s['surname']}" if s["surname"] else s["name"]
        lines.append(f"📖 全校第一名：{full}（{s['house']}，总经验{s['total_exp']}）")
    mvp_lines = _fmt_mvp_awards(data["mvp_awards"])
    if mvp_lines:
        lines.extend(mvp_lines)
    lines.append("")
    lines.append("N.E.W.T.成绩已经登记。发送「/职业列表」查看毕业后的职业方向。")
    lines.append("感谢大家这一个月的陪伴，祝各位巫师前程似锦。")
    return "\n".join(lines)


async def _announce(bot, group_openid: str, text: str) -> None:
    try:
        await bot.send_to_group(group_openid=group_openid, message=text)
    except Exception as e:
        logger.warning(f"[hp_events] 日历公告发送失败：{e}")


@scheduler.scheduled_job("interval", minutes=CALENDAR_POLL_MINUTES, id="hp_calendar_tick")
async def _calendar_tick() -> None:
    day = core_storage.get_current_day()
    if day is None:
        return
    last = core_storage.get_last_processed_day()
    if day <= last:
        return

    group_openid = core_storage.get_game_group_openid()
    bot = None
    if group_openid:
        try:
            bot = nonebot.get_bot()
        except ValueError:
            bot = None  # 还没有机器人连上，先跳过这次公告，天数照样往前推进

    for d in range(last + 1, day + 1):
        events = hp_calendar.process_day(d)
        for event in events:
            if event["type"] == "year_end":
                text = _fmt_year_end(event["data"])
            elif event["type"] == "graduation":
                text = _fmt_graduation(event["data"])
            elif event["type"] == "prefect_nomination":
                text = _fmt_prefect_nomination(event["data"])
            elif event["type"] == "prefect_result":
                text = _fmt_prefect_result(event["data"])
            else:
                text = event["data"]["text"]
            if bot and group_openid:
                await _announce(bot, group_openid, text)
            else:
                logger.info(f"[hp_events] Day{d} 日历事件（未播报，没有群或机器人未连接）：\n{text}")

    core_storage.set_last_processed_day(day)


# ======================== 网页操作播报 ========================


@scheduler.scheduled_job("interval", minutes=NOTIFY_DIGEST_MINUTES, id="hp_notify_digest")
async def _notify_digest() -> None:
    """每10分钟把这段时间的动态汇总成一条播报到通知群。

    什么都记，但同类合并——一个人连上5节课只占一行，不会刷屏。"""
    pending = core_notify.take_pending()
    if not pending:
        return
    group_openid = core_storage.get_game_group_openid()
    if not group_openid:
        return  # 还没指定通知群，先攒着，指定之后会一起发出去
    try:
        bot = nonebot.get_bot()
    except ValueError:
        return  # 机器人还没连上，下一轮再试

    text = core_notify.build_digest(pending, core_storage.get_full_name)
    if not text:
        core_notify.mark_sent([item["id"] for item in pending])
        return
    try:
        await bot.send_to_group(group_openid=group_openid, message=text)
    except Exception as e:
        logger.warning(f"[hp_events] 动态汇总播报失败，留到下一轮：{e}")
        return
    core_notify.mark_sent([item["id"] for item in pending])
    core_notify.purge_sent()


set_notify_group_cmd = on_command("设为通知群")


@set_notify_group_cmd.handle()
async def handle_set_notify_group(event: MessageEvent):
    from nonebot.adapters.qq import GroupMessageCreateEvent

    if not isinstance(event, GroupMessageCreateEvent):
        await set_notify_group_cmd.finish("这条指令要在群里发。")
        return
    core_storage.set_game_group(event.group_openid)
    await set_notify_group_cmd.finish(
        "✅ 本群已设为霍格沃茨通知群。\n"
        "网页上的操作（上课、决斗、禁林、恋爱等）都会播报到这里，学年校报也发这里。"
    )



# ======================== 圣诞节 ========================

ball_cmd = on_command("舞会")


@ball_cmd.handle()
async def handle_ball(event: MessageEvent):
    uid = event.get_user_id()
    state = christmas.ball_window_state()
    lines = ["🎄 圣诞舞会"]
    if not state["is_christmas"]:
        nxt = state["next_christmas"]
        lines.append(f"今天不是圣诞节。{'下一场在第' + str(nxt) + '天。' if nxt else '今年的舞会都办完了。'}")
        await ball_cmd.finish("\n".join(lines))
        return
    lines.append(
        f"今晚 {state['start_hour']}:00–{state['end_hour']}:00 开放入场（现在 {state['hour']}:00）。"
        + ("大门已开！" if state["is_open"] else "还没开场，先准备准备。")
    )
    robe = christmas.get_robe(uid)
    lines.append("你的礼服：" + (robe["描述"] if robe else "还没准备（「/设计礼服」）"))
    partner = christmas.get_partner(uid)
    lines.append("你的舞伴：" + (core_storage.get_full_name(partner) if partner else "还没有（「/邀请舞伴 名字」）"))
    lines.append("")
    lines.append("「/参加舞会」入场　「/设计礼服 颜色 款式 配饰」　「/邀请舞伴 名字」")
    await ball_cmd.finish("\n".join(lines))


design_robe_cmd = on_command("设计礼服")


@design_robe_cmd.handle()
async def handle_design_robe(event: MessageEvent, args=CommandArg()):
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 3:
        await design_robe_cmd.finish(
            "用法：/设计礼服 颜色 款式 配饰\n"
            f"颜色：{'、'.join(christmas.ROBE_COLORS)}\n"
            f"款式：{'、'.join(christmas.ROBE_STYLES)}\n"
            f"配饰：{'、'.join(christmas.ROBE_ACCESSORIES)}"
        )
        return
    try:
        result = christmas.design_robe(event.get_user_id(), *parts)
    except christmas.ChristmasError as e:
        await design_robe_cmd.finish(str(e))
        return
    await design_robe_cmd.finish(f"礼服定好了：{result['描述']}")


invite_ball_cmd = on_command("邀请舞伴")


@invite_ball_cmd.handle()
async def handle_invite_ball(event: MessageEvent, args=CommandArg()):
    name = args.extract_plain_text().strip()
    if not name:
        await invite_ball_cmd.finish("用法：/邀请舞伴 对方名字")
        return
    uid = event.get_user_id()
    try:
        target = hp_core.resolve(name)
        christmas.invite_partner(uid, target)
    except (christmas.ChristmasError, hp_core.UnknownPlayerError) as e:
        await invite_ball_cmd.finish(str(e))
        return
    await invite_ball_cmd.finish(
        MessageSegment.mention_user(target)
        + MessageSegment.text(
            f" {core_storage.get_full_name(uid)} 邀请你做圣诞舞会的舞伴。\n"
            f"「/答应舞伴 {core_storage.get_name(uid)}」或「/婉拒舞伴 {core_storage.get_name(uid)}」"
        )
    )


accept_ball_cmd = on_command("答应舞伴")
decline_ball_cmd = on_command("婉拒舞伴")


@accept_ball_cmd.handle()
async def handle_accept_ball(event: MessageEvent, args=CommandArg()):
    await _respond_ball(accept_ball_cmd, event, args, True)


@decline_ball_cmd.handle()
async def handle_decline_ball(event: MessageEvent, args=CommandArg()):
    await _respond_ball(decline_ball_cmd, event, args, False)


async def _respond_ball(matcher, event, args, accept: bool):
    name = args.extract_plain_text().strip()
    if not name:
        await matcher.finish(f"用法：/{'答应' if accept else '婉拒'}舞伴 对方名字")
        return
    try:
        inviter = hp_core.resolve(name)
        result = christmas.respond_invite(event.get_user_id(), inviter, accept)
    except (christmas.ChristmasError, hp_core.UnknownPlayerError) as e:
        await matcher.finish(str(e))
        return
    if result["accepted"]:
        await matcher.finish(f"你答应了 {core_storage.get_full_name(inviter)} 的邀请，舞会见。")
    else:
        await matcher.finish(f"你婉拒了 {core_storage.get_full_name(inviter)} 的邀请。")


attend_ball_cmd = on_command("参加舞会")


@attend_ball_cmd.handle()
async def handle_attend_ball(event: MessageEvent):
    uid = event.get_user_id()
    try:
        result = christmas.attend(uid)
    except christmas.ChristmasError as e:
        await attend_ball_cmd.finish(str(e))
        return
    lines = ["🎄 你走进了礼堂。"]
    if result["robe"]:
        lines.append(result["robe"]["描述"])
    else:
        lines.append("你穿着平时的校袍——没人说什么，但你自己有点在意。")
    if result["partner"]:
        pname = core_storage.get_full_name(result["partner"])
        if result["partner_attended"]:
            lines.append(f"{pname} 已经在等你了。你们跳了一整晚，好感度各+{result['affection']}。")
        else:
            lines.append(f"{pname} 还没到，你先在门口等一会儿。")
    lines.append(f"{core_storage.get_player(uid)['house']}学院分+{result['house_points']}。")
    await attend_ball_cmd.finish("\n".join(lines))


tree_cmd = on_command("圣诞树")


@tree_cmd.handle()
async def handle_tree(event: MessageEvent):
    uid = event.get_user_id()
    state = christmas.tree_state()
    if not state["is_christmas"]:
        nxt = christmas.next_christmas(state.get("year", 1) and (core_storage.get_current_day() or 1))
        await tree_cmd.finish(f"礼堂里还没立起圣诞树。{'下一次在第' + str(nxt) + '天。' if nxt else ''}")
        return
    pct = min(100, int(state["progress"] / state["goal"] * 100))
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    lines = [
        "🎄 礼堂中央的圣诞树",
        f"{bar} {state['progress']}/{state['goal']}（{pct}%）",
        f"已有 {state['contributors']} 人参与装点。",
    ]
    if state["recent"]:
        lines.append("")
        lines.append("最近挂上去的：")
        for row in state["recent"][:5]:
            lines.append(f"· {core_storage.get_name(row['uid'])} 挂了{row['ornament']}")
    lines.append("")
    if state["done"]:
        reward = christmas.tree_reward_state(uid)
        if reward["claimed"]:
            lines.append("树已经装点完了，你的礼物也领过了。")
        elif reward["participated"]:
            lines.append("✨ 树亮起来了！用「/领圣诞礼物」拿走树下属于你的那份。")
        else:
            lines.append("树已经装点完了，可惜你一个装饰都没挂过。")
    else:
        lines.append("可挂：" + "、".join(n for n, _, _ in christmas.TREE_ORNAMENTS))
        lines.append("「/挂装饰 名字」——不花体力，但每30分钟只能挂一个。")
    await tree_cmd.finish("\n".join(lines))


hang_cmd = on_command("挂装饰")


@hang_cmd.handle()
async def handle_hang(event: MessageEvent, args=CommandArg()):
    name = args.extract_plain_text().strip()
    if not name:
        await hang_cmd.finish(
            "用法：/挂装饰 名字\n可挂：" + "、".join(n for n, _, _ in christmas.TREE_ORNAMENTS)
        )
        return
    try:
        result = christmas.hang(event.get_user_id(), name)
    except christmas.ChristmasError as e:
        await hang_cmd.finish(str(e))
        return
    lines = [f"你把{result['ornament']}挂了上去——{result['desc']}（+{result['points']}）"]
    lines.append(f"圣诞树进度：{result['progress']}/{result['goal']}")
    if result["just_completed"]:
        lines.append("")
        lines.append("✨ 最后一件装饰归位，整棵树一下子亮了起来。")
        lines.append("所有参与装点的人都可以「/领圣诞礼物」了。")
    await hang_cmd.finish("\n".join(lines))


claim_tree_cmd = on_command("领圣诞礼物")


@claim_tree_cmd.handle()
async def handle_claim_tree(event: MessageEvent):
    try:
        result = christmas.claim_tree_reward(event.get_user_id())
    except christmas.ChristmasError as e:
        await claim_tree_cmd.finish(str(e))
        return
    await claim_tree_cmd.finish(
        f"🎁 你从树下拿走了自己那份：{result['galleons']}加隆，还有一份「{result['gift']}」。"
    )



def _fmt_prefect_nomination(data: dict) -> str:
    lines = [
        "🎖 级长选举开始",
        f"四年级结业，按学业表现自动提名了各院前{prefect.CANDIDATES_PER_HOUSE}名。",
        "只能投本院，一人一票（可以改投），"
        f"第{prefect.CLOSE_DAY}天唱票，各院得票前{prefect.WINNERS_PER_HOUSE}名当选。",
        "",
    ]
    for house, uids in data["candidates"].items():
        names = "、".join(core_storage.get_full_name(u) for u in uids)
        lines.append(f"{house}：{names}")
    lines.append("")
    lines.append("用「/投级长 名字」投票，「/级长候选」看名单。")
    return "\n".join(lines)


def _fmt_prefect_result(data: dict) -> str:
    lines = ["🎖 级长选举结果"]
    for house, winners in data["winners"].items():
        if winners:
            names = "、".join(f"{w['name']}（{w['votes']}票）" for w in winners)
            lines.append(f"{house}：{names}")
        else:
            lines.append(f"{house}：无人当选")
    lines.append("")
    lines.append("级长每天可以「/级长巡查」一次，给本院加分。")
    return "\n".join(lines)


# ======================== 级长 ========================

prefect_cmd = on_command("级长候选", aliases={"级长"})


@prefect_cmd.handle()
async def handle_prefect(event: MessageEvent):
    uid = event.get_user_id()
    day = core_storage.get_current_day() or 1
    state = prefect.phase(day)
    if state == "before":
        await prefect_cmd.finish(f"级长选举还没开始，第{prefect.NOMINATE_DAY}天开放。")
        return
    if state == "closed":
        winners = prefect.prefects()
        lines = ["🎖 本届级长"]
        for house, ws in winners.items():
            lines.append(
                f"{house}：" + ("、".join(f"{w['name']}（{w['votes']}票）" for w in ws) or "无")
            )
        await prefect_cmd.finish("\n".join(lines))
        return

    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        await prefect_cmd.finish("你还没有完成入学手续。")
        return
    rows = prefect.candidates(player["house"])
    mine = prefect.my_vote(uid)
    lines = [f"🎖 {player['house']}级长候选人"]
    for row in rows:
        mark = "（你投了这位）" if mine == row["uid"] else ""
        lines.append(f"· {row['name']}　{row['votes']}票{mark}")
    lines.append("")
    lines.append(f"「/投级长 名字」投票，可以改投。第{prefect.CLOSE_DAY}天截止。")
    await prefect_cmd.finish("\n".join(lines))


vote_prefect_cmd = on_command("投级长")


@vote_prefect_cmd.handle()
async def handle_vote_prefect(event: MessageEvent, args=CommandArg()):
    name = args.extract_plain_text().strip()
    if not name:
        await vote_prefect_cmd.finish("用法：/投级长 候选人名字（「/级长候选」看名单）")
        return
    try:
        target = hp_core.resolve(name)
        result = prefect.vote(event.get_user_id(), target)
    except (prefect.PrefectError, hp_core.UnknownPlayerError) as e:
        await vote_prefect_cmd.finish(str(e))
        return
    if result["changed"]:
        await vote_prefect_cmd.finish(
            f"改投给了 {core_storage.get_full_name(target)}"
            f"（原本投的是 {core_storage.get_full_name(result['previous'])}）。"
        )
    else:
        await vote_prefect_cmd.finish(f"你投给了 {core_storage.get_full_name(target)}。")


duty_cmd = on_command("级长巡查")


@duty_cmd.handle()
async def handle_duty(event: MessageEvent):
    try:
        result = prefect.run_duty(event.get_user_id())
    except prefect.PrefectError as e:
        await duty_cmd.finish(str(e))
        return
    await duty_cmd.finish(
        f"你带队巡查了一圈走廊，扣下几个游荡的低年级。\n"
        f"{result['house']}学院分+{result['house_points']}，你拿到{result['galleons']}加隆跑腿费。"
    )


newsletter_cmd = on_command("校园校报", aliases={"校园周报", "校报"})


@newsletter_cmd.handle()
async def handle_newsletter(event: MessageEvent):
    player = core_storage.get_player(event.get_user_id())
    if not player or not player["house"]:
        await newsletter_cmd.finish("《霍格沃茨校报》只投递给完成入学手续的学生。")
        return
    await newsletter_cmd.finish(newsletter.build())


# ======================== 占位 ========================

become_cmd = on_command("成为魁地奇选手")


@become_cmd.handle()
async def handle_become(event: MessageEvent, args=CommandArg()):
    position = args.extract_plain_text().strip()
    if not position:
        await become_cmd.finish(f"用法：/成为魁地奇选手 <位置>\n可选：{'、'.join(quidditch.POSITIONS)}")
        return
    uid = event.get_user_id()
    try:
        result = quidditch.become_player(uid, position)
    except quidditch.QuidditchError as e:
        await become_cmd.finish(str(e))
        return
    stats_text = "　".join(f"{k}{v}" for k, v in result["stats"].items())
    await become_cmd.finish(f"你成为了本院「{result['position']}」！\n初始属性：{stats_text}（10点随机分配）")


challenge_cmd = on_command("取代魁地奇")


@challenge_cmd.handle()
async def handle_challenge(event: MessageEvent, args=CommandArg()):
    position = args.extract_plain_text().strip()
    if not position:
        await challenge_cmd.finish(f"用法：/取代魁地奇 <位置>\n可选：{'、'.join(quidditch.POSITIONS)}")
        return
    uid = event.get_user_id()
    try:
        result = quidditch.challenge_position(uid, position)
    except quidditch.QuidditchError as e:
        await challenge_cmd.finish(str(e))
        return
    if result["win"]:
        text = (
            f"PK成功（判定值{result['chance']:.2f}，比拼{result['stat_desc']}）！\n"
            f"你取代了 {core_storage.get_full_name(result['opponent'])}，成为本院「{result['position']}」。"
        )
    else:
        text = (
            f"PK失败（判定值{result['chance']:.2f}，比拼{result['stat_desc']}），"
            f"位置还是 {core_storage.get_full_name(result['opponent'])} 的。"
        )
    await challenge_cmd.finish(text)


equip_broom_cmd = on_command("装备扫帚")


@equip_broom_cmd.handle()
async def handle_equip_broom(event: MessageEvent, args=CommandArg()):
    item_input = args.extract_plain_text().strip()
    if not item_input:
        await equip_broom_cmd.finish("用法：/装备扫帚 扫帚名（先「/对角巷 扫帚」看看有哪些）")
        return
    uid = event.get_user_id()
    try:
        result = quidditch.equip_broom(uid, item_input)
    except quidditch.QuidditchError as e:
        await equip_broom_cmd.finish(str(e))
        return
    effect_text = "　".join(
        f"{quidditch.STAT_LABELS[k]}+{v}" for k, v in result["effect"].items() if k in quidditch.STAT_KEYS and v
    )
    await equip_broom_cmd.finish(
        f"装备了「{result['name']}」。\n加成：{effect_text or '无'}（会覆盖之前装备的扫帚加成）\n"
        f"耐久：{result['durability']}（每打一场比赛磨损1点，归零后加成失效，用「/施咒 修复如初」修好）"
    )


roster_cmd = on_command("魁地奇队")


@roster_cmd.handle()
async def handle_roster(event: MessageEvent, args=CommandArg()):
    house_input = args.extract_plain_text().strip()
    if house_input:
        if house_input not in core_storage.HOUSES:
            await roster_cmd.finish(f"没有这个学院。可选：{'、'.join(core_storage.HOUSES)}")
            return
        house = house_input
    else:
        player = core_storage.get_player(event.get_user_id())
        if not player or not player["house"]:
            await roster_cmd.finish("你还没有分院，先发「/入学」，或者「/魁地奇队 学院名」查别的院。")
            return
        house = player["house"]

    roster = quidditch.get_roster(house)
    lines = [f"🏆 {house}魁地奇队"]
    for position in quidditch.POSITIONS:
        row = roster[position]
        if row is None:
            lines.append(f"{position}：空缺")
        else:
            lines.append(
                f"{position}：{core_storage.get_full_name(row['uid'])}"
                f"{core_storage.get_status_suffix(row['uid'])}（{_fmt_stats(row)}）"
            )
    await roster_cmd.finish("\n".join(lines))


# ======================== 训练 ========================

train_cmd = on_command("魁地奇训练")


@train_cmd.handle()
async def handle_train(event: MessageEvent):
    uid = event.get_user_id()
    try:
        result = quidditch.train(uid)
    except quidditch.QuidditchError as e:
        await train_cmd.finish(str(e))
        return
    await train_cmd.finish(
        f"训练完了，{result['stat']}+{result['gain']}。\n今天训练了{result['today_count']}/{result['daily_limit']}次。"
    )


# ======================== 比赛 ========================

challenge_match_cmd = on_command("魁地奇挑战")


@challenge_match_cmd.handle()
async def handle_match(event: MessageEvent, args=CommandArg()):
    house_b = args.extract_plain_text().strip()
    uid = event.get_user_id()
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        await challenge_match_cmd.finish("你还没有分院，先发「/入学」完成入学测试。")
        return
    if not house_b:
        await challenge_match_cmd.finish(f"用法：/魁地奇挑战 <对方学院>\n可选：{'、'.join(core_storage.HOUSES)}")
        return
    if house_b not in core_storage.HOUSES:
        await challenge_match_cmd.finish(f"没有这个学院。可选：{'、'.join(core_storage.HOUSES)}")
        return

    try:
        result = quidditch.simulate_match(uid, player["house"], house_b)
    except quidditch.QuidditchError as e:
        await challenge_match_cmd.finish(str(e))
        return

    lines = [
        f"🏆 {result['house_a']} {result['score_a']} : {result['score_b']} {result['house_b']}",
        f"（{result['seeker_winner_house']}的找球手先抓到了金色飞贼，+150分）",
    ]
    if result["winner"]:
        lines.append(f"{result['winner']} 获胜，学院分+{quidditch.MATCH_WIN_HOUSE_POINTS}。")
    else:
        lines.append("打平了，没有额外学院分。")
    if result["scorers"]:
        lines.append(
            "得分者：" + "、".join(f"{core_storage.get_name(u)}(+{amount})" for u, amount in result["scorers"])
        )
    if result["worn_out"]:
        lines.append(
            "⚠️ 扫帚打坏了（加成已失效，要「/施咒 修复如初」修）："
            + "、".join(core_storage.get_name(u) for u in result["worn_out"])
        )
    await challenge_match_cmd.finish("\n".join(lines))


# ======================== 决斗 ========================


def _fmt_duel_state(state: dict) -> str:
    lines = [
        f"⚔️ 决斗 第{state['round']}/{state['total_rounds']}回合",
        f"你 {state['my_hp']}HP" + (f"（护盾{state['my_shield']}）" if state["my_shield"] else ""),
        f"{core_storage.get_full_name(state['opponent'])} {state['opp_hp']}HP",
    ]
    if state["opp_last_spell"]:
        opp_spell = spell_catalog.SPELLS_BY_KEY.get(state["opp_last_spell"])
        if opp_spell:
            lines.append(f"对方上一发：{opp_spell[1]}（{opp_spell[5]}系）")
    if state["locked"]:
        lines.append(f"⚠️ 你被封锁了：{'所有咒语' if state['locked'] == 'any' else state['locked'] + '系'}")
    if state["my_turn"]:
        lines.append("\n轮到你了。可用咒语：")
        if state["available"]:
            for s in state["available"]:
                dmg = f" 伤害{s['damage']}" if s["damage"] else ""
                lines.append(f"　{s['name']}（{s['category']}系{dmg}）")
        else:
            lines.append("　（没有可用的咒语，只能「/决斗跳过」）")
        if state["unavailable"]:
            lines.append("暂时用不了：" + "、".join(f"{s['name']}({s['reason']})" for s in state["unavailable"]))
        lines.append("\n用「/出咒 咒语名」出手，「/决斗跳过」什么都不做，「/逃跑」认输。")
    else:
        lines.append(f"\n等 {core_storage.get_full_name(state['opponent'])} 出手。")
    return "\n".join(lines)


def _fmt_duel_finish(result: dict, self_uid: str) -> str:
    if result["winner"] is None:
        return f"决斗结束——{result['reason']}，双方打平。"
    if result["winner"] == self_uid:
        return (
            f"决斗结束——{result['reason']}，你赢了！\n"
            f"{result['winner_house']}学院分+{result['house_points']}，"
            f"黑魔法防御术经验+{spell_catalog.DUEL_WIN_SUBJECT_EXP}。"
        )
    return (
        f"决斗结束——{result['reason']}，你输了。\n"
        f"黑魔法防御术经验+{spell_catalog.DUEL_LOSE_SUBJECT_EXP}（输了不扣分，下次再来）。"
    )


challenge_cmd = on_command("发起决斗")


@challenge_cmd.handle()
async def handle_challenge(event: MessageEvent, args=CommandArg()):
    target_name = args.extract_plain_text().strip()
    if not target_name:
        await challenge_cmd.finish("用法：/发起决斗 对方名字")
        return
    uid = event.get_user_id()
    try:
        target_uid = hp_core.resolve(target_name)
        result = duel.challenge(uid, target_uid)
    except (duel.DuelError, hp_core.UnknownPlayerError) as e:
        await challenge_cmd.finish(str(e))
        return
    my_name = core_storage.get_name(uid)
    await challenge_cmd.finish(
        MessageSegment.mention_user(result["target"])
        + MessageSegment.text(
            f" {core_storage.get_full_name(uid)} 向你发起了决斗！\n"
            f"用「/接受决斗 {my_name}」应战，或者「/拒绝决斗 {my_name}」拒绝。\n"
            f"（{my_name} 也可以用「/撤回决斗」反悔）"
        )
    )


withdraw_cmd = on_command("撤回决斗")


@withdraw_cmd.handle()
async def handle_withdraw(event: MessageEvent):
    try:
        result = duel.withdraw(event.get_user_id())
    except duel.DuelError as e:
        await withdraw_cmd.finish(str(e))
        return
    await withdraw_cmd.finish(f"撤回了对 {core_storage.get_full_name(result['target'])} 的决斗邀请，体力已退还。")


decline_cmd = on_command("拒绝决斗")


@decline_cmd.handle()
async def handle_decline(event: MessageEvent, args=CommandArg()):
    challenger_name = args.extract_plain_text().strip()
    if not challenger_name:
        rows = storage.list_challenges_to(event.get_user_id())
        if not rows:
            await decline_cmd.finish("没有人向你发起决斗。")
            return
        await decline_cmd.finish(
            "用法：/拒绝决斗 对方名字\n向你发起决斗的有："
            + "、".join(core_storage.get_name(r["challenger_uid"]) for r in rows)
        )
        return
    try:
        challenger = hp_core.resolve(challenger_name)
        result = duel.decline(event.get_user_id(), challenger)
    except (duel.DuelError, hp_core.UnknownPlayerError) as e:
        await decline_cmd.finish(str(e))
        return
    await decline_cmd.finish(f"你拒绝了 {core_storage.get_full_name(result['challenger'])} 的决斗邀请。")


accept_cmd = on_command("接受决斗")


@accept_cmd.handle()
async def handle_accept(event: MessageEvent, args=CommandArg()):
    challenger_name = args.extract_plain_text().strip()
    uid = event.get_user_id()
    if not challenger_name:
        rows = storage.list_challenges_to(uid)
        if not rows:
            await accept_cmd.finish("没有人向你发起决斗。")
            return
        await accept_cmd.finish(
            "用法：/接受决斗 对方名字\n向你发起决斗的有："
            + "、".join(core_storage.get_name(r["challenger_uid"]) for r in rows)
        )
        return
    try:
        challenger = hp_core.resolve(challenger_name)
        result = duel.accept(uid, challenger)
    except (duel.DuelError, hp_core.UnknownPlayerError) as e:
        await accept_cmd.finish(str(e))
        return
    state = duel.get_state(result["challenger"])
    await accept_cmd.finish(
        MessageSegment.mention_user(result["challenger"])
        + MessageSegment.text(
            f" 决斗开始！{core_storage.get_full_name(result['challenger'])} 先手。\n"
            f"双方各{spell_catalog.DUEL_HP}HP，共{spell_catalog.DUEL_ROUNDS}个回合。\n"
            f"随时可以用「/返回决斗」查看当前战况。\n\n" + _fmt_duel_state(state)
        )
    )


duel_state_cmd = on_command("返回决斗")


@duel_state_cmd.handle()
async def handle_duel_state(event: MessageEvent):
    try:
        state = duel.get_state(event.get_user_id())
    except duel.DuelError as e:
        await duel_state_cmd.finish(str(e))
        return
    await duel_state_cmd.finish(_fmt_duel_state(state))


cast_spell_cmd = on_command("出咒")


@cast_spell_cmd.handle()
async def handle_cast_spell(event: MessageEvent, args=CommandArg()):
    spell_input = args.extract_plain_text().strip()
    uid = event.get_user_id()
    if not spell_input:
        await cast_spell_cmd.finish("用法：/出咒 咒语名（「/返回决斗」看有哪些能用）")
        return
    try:
        result = duel.cast(uid, spell_input)
    except duel.DuelError as e:
        await cast_spell_cmd.finish(str(e))
        return

    lines = [f"🪄 {result['spell']} {result['latin']}！"]
    if result["countered"]:
        lines.append(f"克制了对方的{result['countered_what']}系，效果加成！")
    if result["blocked"]:
        lines.append(f"对方护盾挡下{result['blocked']}点。")
    if result["damage"]:
        lines.append(
            f"造成{result['damage']}点伤害，{core_storage.get_full_name(result['opponent'])}剩{result['opp_hp']}HP。"
        )
    if result["shield_gain"]:
        lines.append(f"你获得{result['shield_gain']}点护盾。")
    if result["lock"]:
        lines.append(f"封锁了对方下一回合的{'所有咒语' if result['lock'] == 'any' else result['lock'] + '系'}。")

    if result.get("finished"):
        lines.append("")
        lines.append(_fmt_duel_finish(result, uid))
        await cast_spell_cmd.finish("\n".join(lines))
        return

    lines.append(f"\n第{result['round']}回合，轮到 {core_storage.get_full_name(result['next_turn'])}。")
    await cast_spell_cmd.finish(
        MessageSegment.mention_user(result["next_turn"]) + MessageSegment.text(" " + "\n".join(lines))
    )


duel_skip_cmd = on_command("决斗跳过")


@duel_skip_cmd.handle()
async def handle_duel_skip(event: MessageEvent):
    uid = event.get_user_id()
    try:
        result = duel.skip(uid)
    except duel.DuelError as e:
        await duel_skip_cmd.finish(str(e))
        return
    if result.get("finished"):
        await duel_skip_cmd.finish("你这一回合什么都没做。\n\n" + _fmt_duel_finish(result, uid))
        return
    await duel_skip_cmd.finish(
        MessageSegment.mention_user(result["opponent"])
        + MessageSegment.text(f" 对方这一回合什么都没做。第{result['round']}回合，轮到你了。")
    )


flee_cmd = on_command("逃跑")


@flee_cmd.handle()
async def handle_flee(event: MessageEvent):
    uid = event.get_user_id()
    try:
        result = duel.flee(uid)
    except duel.DuelError as e:
        await flee_cmd.finish(str(e))
        return
    await flee_cmd.finish(
        f"你逃跑了，这场决斗判 {core_storage.get_full_name(result['opponent'])} 获胜。\n" + _fmt_duel_finish(result, uid))


# ======================== MVP ========================

mvp_cmd = on_command("魁地奇mvp")


@mvp_cmd.handle()
async def handle_mvp(event: MessageEvent, args=CommandArg()):
    house_input = args.extract_plain_text().strip()
    if house_input:
        if house_input not in core_storage.HOUSES:
            await mvp_cmd.finish(f"没有这个学院。可选：{'、'.join(core_storage.HOUSES)}")
            return
        houses = [house_input]
    else:
        houses = list(core_storage.HOUSES)

    lines = ["🏆 魁地奇MVP（按赛季累计得分，进球10分/抓到飞贼150分）"]
    for house in houses:
        mvp = quidditch.get_mvp(house)
        if mvp:
            lines.append(
                f"{house}：{core_storage.get_full_name(mvp['uid'])}（{mvp['position']}，{mvp['season_score']}分）"
            )
        else:
            lines.append(f"{house}：暂无数据")
    await mvp_cmd.finish("\n".join(lines))


# ======================== 禁林冒险 ========================


def _fmt_forest_state(state: dict) -> str:
    lines = [
        f"🌲 禁林 第{state['depth']}/{state['max_depth']}层　第{state['round']}回合",
        f"你 {state['my_hp']}HP" + (f"（护盾{state['my_shield']}）" if state["my_shield"] else ""),
        f"{state['monster']} {state['monster_hp']}/{state['monster_max_hp']}HP"
        + (f"（护盾{state['monster_shield']}）" if state["monster_shield"] else ""),
    ]
    if state["monster_last_category"]:
        lines.append(f"它上一发：{state['monster_last_category']}系")
    if state["locked"]:
        lines.append(f"⚠️ 你被缠住了：{'所有咒语' if state['locked'] == 'any' else state['locked'] + '系'}用不了")

    haul = []
    if state["pending_galleons"]:
        haul.append(f"{state['pending_galleons']}加隆")
    if state["pending_exp"]:
        haul.append(f"{state['pending_exp']}经验")
    if state["pending_materials"]:
        haul.append("、".join(state["pending_materials"]))
    lines.append(f"\n🎒 这趟的收获（还没到手）：{'　'.join(haul) if haul else '暂无'}")

    if state["phase"] == "cleared":
        lines.append("\n这一层清完了。「/继续深入」再赌一层，或者「/撤退」把东西带回去。")
        return "\n".join(lines)

    lines.append("\n可用咒语：")
    if state["available"]:
        for s in state["available"]:
            dmg = f" 伤害{s['damage']}" if s["damage"] else ""
            lines.append(f"　{s['name']}（{s['category']}系{dmg}）")
    else:
        lines.append("　（没有可用的咒语，只能「/禁林跳过」硬扛一下）")
    if state["unavailable"]:
        lines.append("暂时用不了：" + "、".join(f"{s['name']}({s['reason']})" for s in state["unavailable"]))
    lines.append("\n「/禁林出咒 咒语名」出手，「/禁林跳过」硬扛，「/撤退」带着东西跑路。")
    return "\n".join(lines)


def _fmt_monster_action(ma: dict, monster_name: str) -> list[str]:
    lines = []
    cat_label = {"attack": "扑了上来", "blast": "发动了猛烈的一击", "control": "把你缠住了", "defence": "缩了回去"}
    lines.append(f"👹 {monster_name}{cat_label.get(ma['category'], '动了')}。")
    if ma["countered"]:
        lines.append("　它正好克制了你刚才那一发！")
    if ma["blocked"]:
        lines.append(f"　你的护盾挡下{ma['blocked']}点。")
    if ma["damage"]:
        lines.append(f"　你受到{ma['damage']}点伤害，剩{ma['my_hp']}HP。")
    if ma["shield_gain"]:
        lines.append(f"　它给自己挡了{ma['shield_gain']}点护盾。")
    if ma["lock"]:
        lines.append(f"　你的{ma['lock']}系咒语下一回合用不了。")
    return lines


enter_forest_cmd = on_command("进入禁林")


@enter_forest_cmd.handle()
async def handle_enter_forest(event: MessageEvent):
    uid = event.get_user_id()
    try:
        result = forest.enter(uid)
    except forest.ForestError as e:
        await enter_forest_cmd.finish(str(e))
        return
    lines = [
        f"🌲 你钻进了禁林。（今天第{result['runs_today']}/{result['daily_limit']}次）",
        "" if result["has_lumos"] else "（你没学会荧光闪烁，只能摸黑走——遇险概率高不少）",
        f"\n第1层：{result['monster']}（{result['monster_hp']}HP）",
        result["monster_desc"],
    ]
    if result["ambush_damage"]:
        lines.append(f"\n⚠️ 你没看清脚下，被偷袭了，掉了{result['ambush_damage']}点HP（现在{result['my_hp']}）。")
    if result.get("protection_potion"):
        lines.append("\n🛡️ 防护药剂在踏入林地时生效，你获得了20点初始护盾。")
    lines.append("\n用「/禁林状态」看可用咒语，「/禁林出咒 咒语名」动手。")
    await enter_forest_cmd.finish("\n".join(line for line in lines if line != ""))


forest_state_cmd = on_command("禁林状态")


@forest_state_cmd.handle()
async def handle_forest_state(event: MessageEvent):
    try:
        state = forest.get_state(event.get_user_id())
    except forest.ForestError as e:
        await forest_state_cmd.finish(str(e))
        return
    await forest_state_cmd.finish(_fmt_forest_state(state))


forest_cast_cmd = on_command("禁林出咒")


@forest_cast_cmd.handle()
async def handle_forest_cast(event: MessageEvent, args=CommandArg()):
    spell_input = args.extract_plain_text().strip()
    if not spell_input:
        await forest_cast_cmd.finish("用法：/禁林出咒 咒语名（「/禁林状态」看有哪些能用）")
        return
    uid = event.get_user_id()
    try:
        result = forest.cast(uid, spell_input)
    except forest.ForestError as e:
        await forest_cast_cmd.finish(str(e))
        return

    lines = [f"🪄 {result['spell']} {result['latin']}！"]
    if result["countered"]:
        lines.append("　克制了它上一发，效果加成！")
    if result["resisted"]:
        lines.append("　但摄魂怪几乎不为所动——这东西只怕守护神。")
    if result["blocked"]:
        lines.append(f"　它挡下了{result['blocked']}点。")
    if result["damage"]:
        lines.append(f"　造成{result['damage']}点伤害，{result['monster']}剩{result['monster_hp']}HP。")
    if result["shield_gain"]:
        lines.append(f"　你获得{result['shield_gain']}点护盾。")

    if result.get("monster_down"):
        lines.append(f"\n✨ {result['monster']}倒下了！")
        if result["learned_spell"]:
            s = result["learned_spell"]
            lines.append(f"🪄 你在这一战里学会了「{s['name']} {s['latin']}」——{s['desc']}")
        loot = result["loot"]
        got = [f"{loot['galleons']}加隆", f"{loot['exp']}经验"]
        if loot["materials"]:
            got.append("、".join(loot["materials"]))
        lines.append(f"这一层的收获：{'　'.join(got)}（撤退才真正到手）")
        if loot.get("lucky_material"):
            lines.append(f"🍀 福灵剂在这一刻发热，你额外发现了「{loot['lucky_material']}」。幸运效果已经耗尽。")
        if result["can_go_deeper"]:
            lines.append("\n「/继续深入」再赌一层，或者「/撤退」落袋为安。")
        elif result["next_blocked_by_grade"]:
            lines.append("\n再往里就不是你这个年级该去的地方了。「/撤退」吧。")
        else:
            lines.append("\n🏆 这已经是禁林最深处了。「/撤退」带着战利品回城堡。")
        await forest_cast_cmd.finish("\n".join(lines))
        return

    lines.extend(_fmt_monster_action(result["monster_action"], result["monster"]))

    if result.get("defeated"):
        lost = result["lost"]
        lines.append(f"\n💀 你倒在了第{result['depth']}层。")
        lost_parts = []
        if lost["galleons"]:
            lost_parts.append(f"{lost['galleons']}加隆")
        if lost["exp"]:
            lost_parts.append(f"{lost['exp']}经验")
        if lost["materials"]:
            lost_parts.append("、".join(lost["materials"]))
        lines.append(
            f"这趟攒的{('、'.join(lost_parts)) if lost_parts else '东西'}全丢了。下次记得见好就收。"
            if lost_parts
            else "好在也没什么可丢的。"
        )
        await forest_cast_cmd.finish("\n".join(lines))
        return

    lines.append(f"\n第{result['round']}回合，继续。")
    await forest_cast_cmd.finish("\n".join(lines))


forest_skip_cmd = on_command("禁林跳过")


@forest_skip_cmd.handle()
async def handle_forest_skip(event: MessageEvent):
    uid = event.get_user_id()
    try:
        result = forest.skip(uid)
    except forest.ForestError as e:
        await forest_skip_cmd.finish(str(e))
        return
    state_monster = forest.get_state(uid)["monster"] if not result.get("defeated") else ""
    lines = ["你屏住呼吸，什么都没做。"]
    lines.extend(_fmt_monster_action(result["monster_action"], state_monster or "它"))
    if result.get("defeated"):
        lost = result["lost"]
        lines.append(f"\n💀 你倒在了第{result['depth']}层，这趟的收获全丢了。")
        await forest_skip_cmd.finish("\n".join(lines))
        return
    lines.append(f"\n第{result['round']}回合，继续。")
    await forest_skip_cmd.finish("\n".join(lines))


go_deeper_cmd = on_command("继续深入")


@go_deeper_cmd.handle()
async def handle_go_deeper(event: MessageEvent):
    uid = event.get_user_id()
    try:
        result = forest.go_deeper(uid)
    except forest.ForestError as e:
        await go_deeper_cmd.finish(str(e))
        return
    lines = [
        f"🌲 你继续往里走。第{result['depth']}层：{result['monster']}（{result['monster_hp']}HP）",
        result["monster_desc"],
    ]
    if result["ambush_damage"]:
        lines.append(f"\n⚠️ 半路被偷袭，掉了{result['ambush_damage']}点HP（现在{result['my_hp']}）。")
    else:
        lines.append(f"\n你现在{result['my_hp']}HP。")
    if result.get("wolfsbane_potion"):
        lines.append("🌕 狼毒药剂压住了月光带来的寒意：这一趟狼人造成的伤害减半。")
    await go_deeper_cmd.finish("\n".join(lines))


retreat_cmd = on_command("撤退")


@retreat_cmd.handle()
async def handle_retreat(event: MessageEvent):
    uid = event.get_user_id()
    try:
        result = forest.retreat(uid)
    except forest.ForestError as e:
        await retreat_cmd.finish(str(e))
        return
    lines = [f"🌲 你从禁林里出来了，走到第{result['depth']}层。"]
    got = [f"加隆 +{result['galleons']}", f"保护神奇动物学/黑魔法防御术 共+{result['exp']}经验"]
    lines.append("落袋为安：" + "　".join(got))
    if result["materials"]:
        lines.append("带回来的材料：" + "、".join(result["materials"]) + "（可以「/卖出 材料名」换钱）")
    await retreat_cmd.finish("\n".join(lines))


bestiary_cmd = on_command("禁林图鉴")


@bestiary_cmd.handle()
async def handle_bestiary(event: MessageEvent):
    uid = event.get_user_id()
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        await bestiary_cmd.finish("你还没有分院，先发「/入学 你的名字」。")
        return
    rows = forest.bestiary(uid)
    lines = ["🌲 禁林图鉴"]
    for r in rows:
        if r["locked"]:
            lines.append(f"🔒 {r['name']}（{r['depth']}）—— {r['req_grade']}年级才能去")
            continue
        mark = "✓" if r["defeated"] else "○"
        lines.append(f"{mark} {r['name']}（{r['depth']}）")
        lines.append(f"　出招偏好：{r['preference']}")
        if r["teaches"]:
            status = "已学会" if r["defeated"] else "打赢可学"
            lines.append(f"　专属咒语：{r['teaches']}（{status}）")
    await bestiary_cmd.finish("\n".join(lines))

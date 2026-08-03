import nonebot
from nonebot import logger, on_command, on_notice, require
from nonebot.adapters.qq import Bot, GroupMessageCreateEvent, InteractionCreateEvent, MessageEvent, MessageSegment
from nonebot.adapters.qq.models import (
    Action,
    Button,
    InlineKeyboard,
    InlineKeyboardRow,
    MessageKeyboard,
    Permission,
    RenderData,
)
from nonebot.params import CommandArg

import plugins.hp_core as hp_core
from plugins.hp_core import spells as spell_catalog
from plugins.hp_core import storage as core_storage
from plugins.hp_core import web_binding

from . import careers, casting, daily_plan, freshman_duel, homework, kitchen, lesson_events, lessons, mainline, potions, shop, shop_catalog, sorting, storage, story_mainline, subjects, wands, work

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler  # noqa: E402

BUTTON_PREFIX = "hpsort"
LESSON_BUTTON_PREFIX = "hplesson"
STORY_BUTTON_PREFIX = "hpstory"


def _numbered(options: list[str]) -> str:
    """正文里把选项完整列一遍——按钮上的长文字会被QQ截断，看不全。"""
    return "\n".join(f"{i}. {label}" for i, label in enumerate(options, 1))


def _build_keyboard(uid: str, step: str, options: list[str]) -> MessageSegment:
    """给 options 里每一项生成一个按钮，data 里编码 uid/step/序号，
    并把操作权限锁定到发起这次分院测试的人，避免群里其他人代点。
    按钮文字带序号，和正文里的编号对得上，长文本被截断也能认出来点哪个。"""
    buttons = [
        Button(
            id=f"{BUTTON_PREFIX}_{step}_{i}",
            render_data=RenderData(label=f"{i + 1}. {label}", style=1),
            action=Action(
                type=1,
                data=f"{BUTTON_PREFIX}:{uid}:{step}:{i}",
                permission=Permission(type=0, specify_user_ids=[uid]),
            ),
        )
        for i, label in enumerate(options)
    ]
    keyboard = MessageKeyboard(content=InlineKeyboard(rows=[InlineKeyboardRow(buttons=buttons)]))
    return MessageSegment.keyboard(keyboard)


def _build_lesson_keyboard(uid: str, token: str, options: list[str]) -> MessageSegment:
    buttons = [
        Button(
            id=f"{LESSON_BUTTON_PREFIX}_{i}",
            render_data=RenderData(label=f"{i + 1}. {label}", style=1),
            action=Action(
                type=1,
                data=f"{LESSON_BUTTON_PREFIX}:{uid}:{token}:{i}",
                permission=Permission(type=0, specify_user_ids=[uid]),
            ),
        )
        for i, label in enumerate(options)
    ]
    keyboard = MessageKeyboard(content=InlineKeyboard(rows=[InlineKeyboardRow(buttons=buttons)]))
    return MessageSegment.keyboard(keyboard)


def _build_story_keyboard(uid: str, phase: int, options: tuple[story_mainline.Option, ...]) -> MessageSegment:
    buttons = [
        Button(
            id=f"{STORY_BUTTON_PREFIX}_{option.key}",
            render_data=RenderData(label=f"{option.key}. {option.text}", style=1),
            action=Action(
                type=1,
                data=f"{STORY_BUTTON_PREFIX}:{uid}:{phase}:{option.key}",
                permission=Permission(type=0, specify_user_ids=[uid]),
            ),
        )
        for option in options
    ]
    keyboard = MessageKeyboard(content=InlineKeyboard(rows=[InlineKeyboardRow(buttons=buttons)]))
    return MessageSegment.keyboard(keyboard)


enroll_cmd = on_command("入学")


ENROLL_USAGE = "用法：/入学 你的名字（比如 /入学 赫敏）"


web_bind_cmd = on_command("网页绑定")


@web_bind_cmd.handle()
async def handle_web_bind(event: MessageEvent, args=CommandArg()):
    try:
        result = web_binding.issue(event.get_user_id(), args.extract_plain_text().strip())
    except web_binding.BindingError as e:
        await web_bind_cmd.finish(str(e))
        return
    await web_bind_cmd.finish(
        f"🔐 {result['name']}的网页绑定码：{result['code']}\n"
        f"已锁定登录QQ：{result['login_uid']}。请在网页申请账号时填写这个QQ号和绑定码。"
        "绑定码十分钟内有效、使用一次后失效，"
        "不要转发给别人。"
    )


def _wand_shop_message(uid: str, result: dict, resume: bool = False, intro: str = "") -> MessageSegment:
    lines = []
    if intro:
        lines.append(intro.strip())
    if result["wand_stage"] == "wood":
        lines.extend(
            [
                "🏚️ 奥利凡德魔杖店",
                "“是的，是的……我一直在等你。”奥利凡德先生从高高的纸盒间走出来。",
                (
                    "他把上次挑出的木材样本原样摆回柜台。"
                    if resume
                    else "他没有立刻递给你一根成品魔杖，而是先展开一块深色天鹅绒。"
                ),
            ]
        )
    elif resume:
        lines.append("奥利凡德先生仍守在柜台后。你先前的选择被妥善放在天鹅绒上，一样也没有丢。")
    if result.get("reaction"):
        lines.append(result["reaction"])
    chosen = []
    if result.get("selected_wood"):
        chosen.append(f"木材：{result['selected_wood']}")
    if result.get("selected_core"):
        chosen.append(f"杖芯：{result['selected_core']}")
    if chosen:
        lines.append("目前选择｜" + "　".join(chosen))
    if result.get("selected_connection") and result["wand_stage"] != "wood":
        lines.append("“" + result["selected_connection"] + "”")
    lines.extend([f"🪄 {result['wand_title']}", result["wand_prompt"]])
    for i, detail in enumerate(result.get("wand_option_details", []), 1):
        lines.append(f"{i}. {detail}")
    # 带按钮的消息必须用 markdown 发——QQ 不接受纯文本 + keyboard 的组合
    return MessageSegment.markdown("\n\n".join(lines)) + _build_keyboard(
        uid, result["step"], result["options"]
    )


@enroll_cmd.handle()
async def handle_enroll(event: MessageEvent, args=CommandArg()):
    uid = event.get_user_id()
    name = args.extract_plain_text().strip()
    if isinstance(event, GroupMessageCreateEvent):
        core_storage.ensure_game_group(event.group_openid)  # 只认第一个触发/入学的群，日历公告发这里
    try:
        result = sorting.start(uid, name)
    except sorting.SortingError as e:
        await enroll_cmd.finish(f"{e}\n{ENROLL_USAGE}" if not name else str(e))
        return
    if result.get("needs_wand"):
        await enroll_cmd.finish(_wand_shop_message(uid, result, resume=True))
        return
    intro = (
        f"接着上次没答完的问题，{result['name']}——"
        if result["is_resume"]
        else f"欢迎来到霍格沃茨，{result['name']}。在分院之前，先问几个问题。"
    )
    body = f"{intro}\n\n**{result['label']}**\n\n{_numbered(result['options'])}"
    await enroll_cmd.finish(
        MessageSegment.markdown(body) + _build_keyboard(uid, result["step"], result["options"])
    )


sorting_button = on_notice()


@sorting_button.handle()
async def handle_sorting_button(bot: Bot, event: InteractionCreateEvent):
    button_data = event.data.resolved.button_data or ""
    parts = button_data.split(":")
    if len(parts) != 4 or parts[0] != BUTTON_PREFIX:
        return
    _, owner_uid, step, position_str = parts

    uid = event.get_user_id()
    if uid != owner_uid:
        # permission 已经在按钮层面挡住了，这里是双重保险
        return

    try:
        position = int(position_str)
        if step == "gender":
            result = sorting.choose_gender(uid, position)
        elif step.startswith("wand_"):
            result = sorting.choose_wand(uid, step.removeprefix("wand_"), position)
        else:
            result = sorting.choose_option(uid, position)
    except sorting.SortingError as e:
        await bot.send(event, str(e))
        return

    if result["done"]:
        house = result["house"]
        text = (
            f"{result['resonance']}\n"
            f"“就是它。{result['wand_desc']}。奇妙，真是奇妙……”\n\n"
            f"奥利凡德先生将魔杖装回盒中，递到 {result['full_name']} 手里。\n"
            f"入学手续至此完成。从今天起，你正式成为{house}的一员。\n"
            f"（别人找你用「{result['player_name']}」就行）"
        )
        if result["is_transfer"]:
            text += f"\n（你是第{result['day']}天入学的插班生，之后会自动跟上大家的进度）"
        text += "\n打开「/成长册」查看你的七学年个人主线。"
        await bot.send(event, text)
        return

    if result.get("needs_wand"):
        if result.get("house_just_selected"):
            hat_text = (
                f"分院帽在{result['full_name']}头上沉吟了许久，忽然高声喊道：\n"
                f"“{result['house']}！”\n\n"
                "礼堂的掌声还没完全落下，一张羊皮纸便飘到你面前："
                "正式开学前，请前往对角巷的奥利凡德魔杖店。\n\n"
            )
        else:
            hat_text = ""
        await bot.send(event, _wand_shop_message(uid, result, intro=hat_text))
        return

    text = f"选好了：{result['picked']}"
    if result.get("surname"):
        text += f"\n\n——原来你是{result['surname']}家的孩子。"
    text += f"\n\n**{result['label']}**\n\n{_numbered(result['options'])}"
    await bot.send(
        event,
        MessageSegment.markdown(text) + _build_keyboard(uid, result["step"], result["options"]),
    )


my_wand_cmd = on_command("我的魔杖")


@my_wand_cmd.handle()
async def handle_my_wand(event: MessageEvent):
    uid = event.get_user_id()
    wand = storage.get_wand(uid)
    if not wand:
        session = storage.get_session(uid)
        if session and session["step"] in (5, 6, 7):
            await my_wand_cmd.finish("你的魔杖还在奥利凡德先生的柜台上。发送「/入学」继续挑选。")
        else:
            player = core_storage.get_player(uid)
            if player and player["house"]:
                await my_wand_cmd.finish("你的入学记录来自魔杖登记制度启用之前，档案里暂时没有魔杖资料。")
            else:
                await my_wand_cmd.finish("你还没有属于自己的魔杖。先发送「/入学 你的名字」。")
        return
    await my_wand_cmd.finish(
        "🪄 我的魔杖\n" + wands.describe(dict(wand)) + "\n“魔杖选择巫师。”——奥利凡德"
    )


# ======================== 上课 ========================

lesson_cmd = on_command("上课")
cancel_lesson_cmd = on_command("取消上课")


@cancel_lesson_cmd.handle()
async def handle_cancel_lesson(event: MessageEvent):
    uid = event.get_user_id()
    session = storage.get_lesson_session(uid)
    if not session:
        await cancel_lesson_cmd.finish("你现在没有未完成的课堂。")
        return
    subject_name = subjects.SUBJECTS_BY_KEY[session["subject_key"]][0]
    storage.delete_lesson_session(uid, session["token"])
    await cancel_lesson_cmd.finish(f"已退出这节{subject_name}，没有消耗体力或上课次数。")


@lesson_cmd.handle()
async def handle_lesson(event: MessageEvent, args=CommandArg()):
    subject_input = args.extract_plain_text().strip()
    uid = event.get_user_id()
    if not subject_input and not storage.get_lesson_session(uid):
        names = "、".join(name for _, name, grade, _ in subjects.SUBJECTS if grade == 1)
        await lesson_cmd.finish(
            f"用法：/上课 <学科名>\n必修：{names}\n"
            f"（每天全科{lessons.DAILY_GLOBAL_LIMIT}节计分课，每科前{lessons.DAILY_LIMIT_PER_SUBJECT}节计分；"
            "实操课之后仍可加练魔咒）"
        )
        return
    try:
        event_result = lesson_events.start(uid, subject_input)
    except lessons.LessonError as e:
        await lesson_cmd.finish(str(e))
        return

    intro = "接着刚才没完成的课堂——" if event_result["is_resume"] else "课堂情境——"
    await lesson_cmd.finish(
        MessageSegment.markdown(
            f"**📚 {event_result['subject']}**\n\n{intro}\n\n{event_result['prompt']}\n\n"
            f"你准备怎么做？\n\n{_numbered(event_result['options'])}"
        )
        + _build_lesson_keyboard(uid, event_result["token"], event_result["options"])
    )


lesson_button = on_notice()


@lesson_button.handle()
async def handle_lesson_button(bot: Bot, event: InteractionCreateEvent):
    button_data = event.data.resolved.button_data or ""
    parts = button_data.split(":")
    if len(parts) != 4 or parts[0] != LESSON_BUTTON_PREFIX:
        return
    _, owner_uid, token, position_str = parts
    uid = event.get_user_id()
    if uid != owner_uid:
        return
    try:
        result = lesson_events.resolve(uid, token, int(position_str))
    except (lesson_events.LessonEventError, lessons.LessonError, ValueError) as e:
        await bot.send(event, str(e))
        return

    lines = []
    lines.append(result["event_result"])
    if result["gives_exp"]:
        bonuses = []
        if result["event_bonus"]:
            bonuses.append(f"课堂表现+{result['event_bonus']}")
        if result.get("potion_bonus"):
            bonuses.append("振奋药剂+1")
        bonus_text = f"，其中{'、'.join(bonuses)}" if bonuses else ""
        lines.append(
            f"{result['subject']}课上完了，+{result['exp_gained']}经验{bonus_text}（累计{result['total_exp']}）。"
        )
    else:
        if result["score_block_reason"] == "fatigue_limit":
            reason = "八节计分课已经耗尽了今天的课堂精力"
        else:
            reason = f"教授今天已经记录了你两节{result['subject']}的课堂表现"
        lines.append(
            f"你留在教室继续加练。{reason}，这次不增加学科经验和课堂表现奖励，"
            "但挥杖练习仍然推进了魔咒进度。"
        )
    lines.append(f"你揉了揉发酸的肩膀。今日课堂疲劳：{result['fatigue']}/{result['fatigue_max']}。")
    if result["fatigue"] >= result["fatigue_max"]:
        lines.append("今天已经听完八节课，城堡的走廊都快走不动了。该回休息室歇一歇了。")
    if result.get("herbology_material"):
        lines.append("🌿 斯普劳特教授允许你带走一份处理合格的结节草，已经放进背包。每天最多带走一份。")

    if result["is_spell_subject"]:
        if result["learned_spell"]:
            s = result["learned_spell"]
            lines.append(f"✨ 学会了新咒语：{s['name']} {s['latin']}——{s['desc']}")
        if result["spell_target"]:
            lines.append(
                f"正在学：{result['spell_target']}"
                f"（{result['spell_progress']}/{lessons.spell_catalog.LESSONS_PER_SPELL}）"
            )
        elif result["blocked_spell"]:
            b = result["blocked_spell"]
            lines.append(f"下一个咒语「{b['name']}」要到{b['min_grade']}年级才教，先等等。")
        elif result["all_learned"]:
            lines.append("这门课的咒语你已经全学会了。")
        lines.append(f"（这门实操课可以继续加练，但每天只有前{result['daily_limit']}节计入成绩）")
    else:
        lines.append(f"今天这门课上了{result['today_count']}/{result['daily_limit']}次。")

    await bot.send(event, "\n".join(lines))


my_spells_cmd = on_command("我的魔咒")


@my_spells_cmd.handle()
async def handle_my_spells(event: MessageEvent):
    uid = event.get_user_id()
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        await my_spells_cmd.finish("你还没有分院，先发「/入学」完成入学测试。")
        return
    learned = core_storage.list_learned_spells(uid)
    lines = [f"🪄 我的魔咒（{len(learned)}/{len(spell_catalog.SPELLS)}）"]
    for subject_key in spell_catalog.SPELL_SUBJECTS:
        subject_name = subjects.SUBJECTS_BY_KEY[subject_key][0]
        lines.append(f"\n▪ {subject_name}")
        for skey, name, latin, _, min_grade, category, desc in spell_catalog.spells_of_subject(subject_key):
            if skey in learned:
                lines.append(f"✓ {name} {latin}（{category}）")
            elif min_grade > player["grade"]:
                lines.append(f"🔒 {name}（{min_grade}年级才教）")
            else:
                lines.append(f"○ {name}（还没学会）")
        progress = core_storage.get_spell_progress(uid, subject_key)
        target = lessons.next_spell_for(uid, subject_key, player["grade"])
        if target:
            lines.append(f"　正在学：{target[1]}（{progress}/{spell_catalog.LESSONS_PER_SPELL}）")
    await my_spells_cmd.finish("\n".join(lines))


# ======================== 个人主线 ========================

mainline_cmd = on_command("成长册", aliases={"个人主线"})


@mainline_cmd.handle()
async def handle_mainline(event: MessageEvent):
    uid = event.get_user_id()
    try:
        result = mainline.open_book(uid)
    except mainline.MainlineError as e:
        await mainline_cmd.finish(str(e))
        return

    lines = ["📖 霍格沃茨成长册"]
    current_found = False
    for entry in result["entries"]:
        if entry["claimed"]:
            mark = "✓"
        elif entry["grade"] > result["grade"]:
            mark = "🔒"
        elif not current_found:
            mark = "➤"
            current_found = True
        else:
            mark = "○"
        lines.append(
            f"{mark} {entry['grade']}年级·{entry['title']}\n"
            f"　{entry['requirement']}（{entry['progress']}）· 奖励{entry['reward']}加隆"
        )

    if result["newly_claimed"]:
        lines.append(
            f"\n🎁 完成：{'、'.join(result['newly_claimed'])}\n"
            f"本次自动领取{result['reward']}加隆。"
        )
    elif not current_found:
        lines.append("\n🎓 七学年个人主线已经全部完成。")
    else:
        lines.append("\n➤ 是你当前最接近的主线目标；达成后再次打开成长册即可领奖。")
    await mainline_cmd.finish("\n".join(lines))


# ======================== 全服分支主线 ========================

story_task_cmd = on_command("阶段任务")
story_choice_cmd = on_command("选择")
story_progress_cmd = on_command("故事进度")


def _story_task_message(uid: str, task: dict) -> MessageSegment | str:
    if task["ended"]:
        ending = task.get("ending")
        if ending:
            return f"📜 {ending['ending_text']}"
        return "《第十三声钟响》已经结束，你没有留下个人参与记录。"
    phase = task["phase"]
    stats = task["stats"]
    if task["choice"]:
        selected = next(option.text for option in phase.options if option.key == task["choice"])
        return (
            f"🔔 《{story_mainline.STORY_TITLE}》{phase.number}/20·{phase.title}\n"
            f"你已选择 {task['choice']}：{selected}\n"
            f"当前参与 {sum(stats.values())}/{task['threshold']} 人，请等待阶段结算。"
        )
    if not task["eligible"]:
        return (
            f"🔔 《{story_mainline.STORY_TITLE}》{phase.number}/20·{phase.title}\n"
            "你今天还没有听见异常钟声。阶段任务每日有概率触发，请之后再来查看。"
        )
    options = "\n".join(f"{option.key}. {option.text}" for option in phase.options)
    body = (
        f"🔔 **《{story_mainline.STORY_TITLE}》{phase.number}/20·{phase.title}**\n\n"
        f"{phase.prompt}\n\n{options}\n\n"
        f"选择后获得{story_mainline.CHOICE_REWARD}加隆，且无法反悔。"
    )
    return MessageSegment.markdown(body) + _build_story_keyboard(uid, phase.number, phase.options)


@story_task_cmd.handle()
async def handle_story_task(event: MessageEvent):
    uid = event.get_user_id()
    try:
        message = _story_task_message(uid, story_mainline.task_for(uid))
    except story_mainline.StoryError as e:
        await story_task_cmd.finish(str(e))
        return
    await story_task_cmd.finish(message)


def _story_choice_text(result: dict) -> str:
    total = sum(result["stats"].values())
    text = (
        f"你选择了 {result['choice']}：{result['text']}\n"
        f"获得{result['reward']}加隆。当前已有{total}人参与。"
    )
    if result["advanced"]:
        text += "\n本阶段已经达到推进条件，新的阶段已开启。"
    else:
        text += "\n等待其他学生作出选择……"
    return text


@story_choice_cmd.handle()
async def handle_story_choice(event: MessageEvent, args=CommandArg()):
    raw = args.extract_plain_text().strip().upper().split()
    choice = raw[-1] if raw else ""
    try:
        result = story_mainline.choose(event.get_user_id(), choice)
    except story_mainline.StoryError as e:
        await story_choice_cmd.finish(f"{e}\n用法：/选择 A")
        return
    await story_choice_cmd.finish(_story_choice_text(result))


story_choice_button = on_notice()


@story_choice_button.handle()
async def handle_story_choice_button(bot: Bot, event: InteractionCreateEvent):
    button_data = event.data.resolved.button_data or ""
    parts = button_data.split(":")
    if len(parts) != 4 or parts[0] != STORY_BUTTON_PREFIX:
        return
    _, owner_uid, phase_text, choice = parts
    if event.get_user_id() != owner_uid:
        return
    try:
        current = story_mainline.progress()
        if not current["active"] or current["phase"] != int(phase_text):
            raise story_mainline.StoryError("这个按钮属于已经结束的阶段，请发送「/阶段任务」查看最新任务。")
        result = story_mainline.choose(owner_uid, choice)
    except (ValueError, story_mainline.StoryError) as e:
        await bot.send(event, str(e))
        return
    await bot.send(event, _story_choice_text(result))


@story_progress_cmd.handle()
async def handle_story_progress(event: MessageEvent):
    data = story_mainline.progress(event.get_user_id())
    if data["active"]:
        stats = "　".join(f"{key}:{count}" for key, count in data["stats"].items())
        await story_progress_cmd.finish(
            f"🔔 《{data['title']}》{data['phase']}/20·{data['phase_title']}\n"
            f"本阶段票数：{stats}\n参与：{sum(data['stats'].values())}/{data['threshold']}"
        )
        return
    ending = data.get("personal_ending")
    text = f"🔔 《{data['title']}》已经完结。\n全校结局：{story_mainline.ENDING_NAMES[data['ending_key']]}"
    if ending:
        text += f"\n你的身份：{story_mainline.TAG_NAMES[ending['personal_tag']]}\n{ending['ending_text']}"
    await story_progress_cmd.finish(text)


@scheduler.scheduled_job("interval", minutes=10, id="hp_story_mainline_tick")
async def _story_mainline_tick() -> None:
    day = core_storage.get_current_day()
    if day is None:
        return
    story_mainline.daily_offer(day)
    story_mainline.check_and_advance()
    announcements = story_mainline.pending_announcements()
    if not announcements:
        return
    group_openid = core_storage.get_game_group_openid()
    if not group_openid:
        return
    try:
        bot = nonebot.get_bot()
        for item in announcements:
            await bot.send_to_group(group_openid=group_openid, message=item["message"])
            story_mainline.mark_announcement_sent(item["id"])
    except Exception as e:
        logger.warning(f"[hp_school] 主线公告发送失败：{e}")


@scheduler.scheduled_job("interval", minutes=5, id="hp_group_announcements")
async def _send_group_announcements() -> None:
    """定时发送管理员添加的群通知。"""
    announcements = storage.get_pending_announcements()
    if not announcements:
        return
    group_openid = core_storage.get_game_group_openid()
    if not group_openid:
        return
    try:
        bot = nonebot.get_bot()
        for item in announcements:
            await bot.send_to_group(group_openid=group_openid, message=item["message"])
            storage.mark_announcement_sent(item["id"])
    except Exception as e:
        logger.warning(f"[hp_school] 群通知发送失败：{e}")


# ======================== 作业 ========================

homework_cmd = on_command("交作业")


@homework_cmd.handle()
async def handle_homework_submit(event: MessageEvent, args=CommandArg()):
    subject_input = args.extract_plain_text().strip()
    if not subject_input:
        await homework_cmd.finish("用法：/交作业 <学科名>（先用「/今日作业」看看还欠哪几门）")
        return
    uid = event.get_user_id()
    try:
        result = homework.submit(uid, subject_input)
    except homework.HomeworkError as e:
        await homework_cmd.finish(str(e))
        return
    text = f"{result['subject']}作业交了，+{result['exp_gained']}经验（累计{result['total_exp']}）。"
    if result["overdue_settled"]:
        text += (
            f"\n（顺手结算了{result['overdue_settled']}门逾期作业，共扣{result['overdue_penalty']}经验；"
            f"每个缺席日最多扣{homework.HOMEWORK_DAILY_PENALTY_CAP}）"
        )
    if result["completion_reward"]:
        text += (
            f"\n📜 最后一份羊皮纸也收进了教授的文件夹。"
            f"今日作业全部完成，获得{result['completion_reward']}加隆。"
        )
    await homework_cmd.finish(text)


today_homework_cmd = on_command("今日作业")


@today_homework_cmd.handle()
async def handle_today_homework(event: MessageEvent):
    uid = event.get_user_id()
    try:
        result = homework.list_today(uid)
    except homework.HomeworkError as e:
        await today_homework_cmd.finish(str(e))
        return
    lines = ["📝 今日作业"]
    if result["overdue_settled"]:
        lines.append(
            f"（刚结算了{result['overdue_settled']}门逾期作业，共扣{result['overdue_penalty']}经验；"
            f"每个缺席日最多扣{homework.HOMEWORK_DAILY_PENALTY_CAP}）"
        )
    lines.append("待交：" + ("、".join(result["pending"]) if result["pending"] else "无"))
    lines.append("已交：" + ("、".join(result["done"]) if result["done"] else "无"))
    await today_homework_cmd.finish("\n".join(lines))


# ======================== 今日安排 ========================

today_plan_cmd = on_command("今日安排")


@today_plan_cmd.handle()
async def handle_today_plan(event: MessageEvent):
    try:
        result = daily_plan.build(event.get_user_id())
    except (daily_plan.DailyPlanError, homework.HomeworkError) as e:
        await today_plan_cmd.finish(str(e))
        return

    hw = result["homework"]
    lines = [
        f"📅 第{result['day']}天 · {result['grade']}年级今日安排",
        f"⚡ 体力：{result['stamina']}/{result['stamina_max']}",
        "",
        "📝 作业",
        "待交：" + ("、".join(hw["pending"]) if hw["pending"] else "无"),
        "已交：" + ("、".join(hw["done"]) if hw["done"] else "无"),
        "",
        f"😮‍💨 课堂疲劳：{result['scored_lessons']}/{result['scored_lesson_cap']}",
        "已上：" + ("、".join(result["lesson_rows"]) if result["lesson_rows"] else "无"),
    ]
    if result["unfinished_lesson"]:
        lines.append(f"未完成课堂：{result['unfinished_lesson']}（发送「/上课」继续）")
    if result["unfinished_potion"]:
        lines.append(f"坩埚仍在熬制：{result['unfinished_potion']}（发送「/继续熬制」）")
    lines.extend(["", "🎯 活动"])
    lines.extend(result["activities"] or ["当前年级暂无额外活动，先完成课程和作业。"])
    lines.append(f"城堡打工：{result['work_count']}/{work.DAILY_LIMIT}（发送「/打工」）")
    exam_text = "今天" if result["days_to_exam"] == 0 else f"还有{result['days_to_exam']}天"
    lines.append(f"学年考核：{exam_text}")
    claimable = result["claimable"]
    lines.extend(["", "🎁 可领奖励"])
    if claimable["count"]:
        lines.append(
            f"成长册有{claimable['count']}项可领取，共{claimable['reward']}加隆（发送「/成长册」领取）"
        )
    else:
        lines.append("暂无；发送「/成长册」查看下一个个人目标。")
    if hw["overdue_settled"]:
        lines.append(f"\n刚结算逾期作业：共扣{hw['overdue_penalty']}经验。")
    await today_plan_cmd.finish("\n".join(lines))


# ======================== 魔药熬制 ========================

potion_recipes_cmd = on_command("魔药配方")
brew_potion_cmd = on_command("熬制魔药")
continue_brew_cmd = on_command("继续熬制")
brew_choice_cmd = on_command("熬制选择")
abandon_brew_cmd = on_command("放弃熬制")
use_potion_cmd = on_command("使用魔药")
gift_potion_cmd = on_command("赠送魔药")
potion_record_cmd = on_command("魔药记录")
potion_titles_cmd = on_command("魔药称号")
wear_potion_title_cmd = on_command("佩戴魔药称号")


def _brew_prompt(result: dict) -> str:
    lines = [
        f"⚗️ {result['recipe']} · 第{result['step']}/{result['total_steps']}步",
        ("你回到先前那口坩埚旁，药液还保持着离开时的状态。" if result.get("resumed") else "材料已经投入坩埚，熬制开始。"),
        result["prompt"],
    ]
    lines.extend(f"{i}. {option}" for i, option in enumerate(result["options"], 1))
    lines.append("发送「/熬制选择 1/2/3」继续；中断后可发送「/继续熬制」。")
    return "\n".join(lines)


@potion_recipes_cmd.handle()
async def handle_potion_recipes(event: MessageEvent):
    try:
        result = potions.list_recipes(event.get_user_id())
    except potions.PotionError as e:
        await potion_recipes_cmd.finish(str(e))
        return
    from plugins.hp_events import forest_catalog
    lines = [f"⚗️ 魔药配方 · 魔药学{result['exp']}经验"]
    for row in result["rows"]:
        status = "✓" if row["unlocked"] else f"🔒 {row['grade']}年级/{row['exp']}经验"
        materials = "、".join(
            f"{forest_catalog.MATERIALS_BY_KEY[key][1]}×{amount}"
            for key, amount in row["ingredients"].items()
        )
        mastery = row["mastery"]
        record = f"；成功{mastery['successes']}/{mastery['attempts']}" if mastery else ""
        if row["key"] == "felix" and row["yearly_used"]:
            record += "；本学年已开锅"
        lines.append(f"\n{status} {row['name']}（{materials}）{record}\n{row['effect']}")
    lines.append("\n发送「/熬制魔药 药名」开火。每天最多2次，每次消耗4点体力。")
    await potion_recipes_cmd.finish("\n".join(lines))


@brew_potion_cmd.handle()
async def handle_brew_potion(event: MessageEvent, args=CommandArg()):
    name = args.extract_plain_text().strip()
    if not name and not potions.get_session(event.get_user_id()):
        await brew_potion_cmd.finish("用法：/熬制魔药 药名（发送「/魔药配方」查看）")
        return
    try:
        result = potions.start(event.get_user_id(), name)
    except potions.PotionError as e:
        await brew_potion_cmd.finish(str(e))
        return
    await brew_potion_cmd.finish(_brew_prompt(result))


@continue_brew_cmd.handle()
async def handle_continue_brew(event: MessageEvent):
    row = potions.get_session(event.get_user_id())
    if not row:
        await continue_brew_cmd.finish("你面前没有正在熬制的坩埚。发送「/魔药配方」挑一张配方。")
        return
    await continue_brew_cmd.finish(_brew_prompt(potions._render_session(row, True)))


@brew_choice_cmd.handle()
async def handle_brew_choice(event: MessageEvent, args=CommandArg()):
    try:
        position = int(args.extract_plain_text().strip())
        result = potions.choose(event.get_user_id(), position)
    except (ValueError, potions.PotionError) as e:
        await brew_choice_cmd.finish(str(e) if str(e) else "用法：/熬制选择 1/2/3")
        return
    if not result["finished"]:
        await brew_choice_cmd.finish(_brew_prompt(result))
        return
    if result["quantity"]:
        text = (
            f"⚗️ 熬制完成：{result['quality']}！你得到「{result['recipe']}」×{result['quantity']}。\n"
            "发送「/使用魔药 药名」使用，或在「/我的背包」查看。"
        )
    else:
        text = f"💥 熬制失败。坩埚喷出一股古怪的烟，你现在{result['accident']}。材料没能保住。"
    if result.get("earned_titles"):
        text += "\n🏅 解锁魔药称号：" + "、".join(result["earned_titles"])
    await brew_choice_cmd.finish(text)


@abandon_brew_cmd.handle()
async def handle_abandon_brew(event: MessageEvent):
    if potions.abandon(event.get_user_id()):
        await abandon_brew_cmd.finish("你熄灭了坩埚。已经投入的材料无法取回，今日熬制次数也不会返还。")
    else:
        await abandon_brew_cmd.finish("你现在没有正在熬制的魔药。")


@use_potion_cmd.handle()
async def handle_use_potion(event: MessageEvent, args=CommandArg()):
    parts = args.extract_plain_text().strip().split()
    if not parts:
        await use_potion_cmd.finish("用法：/使用魔药 药名")
        return
    name = parts[0]
    try:
        target_uid = hp_core.resolve(parts[1]) if len(parts) > 1 else None
        result = potions.use(event.get_user_id(), name, target_uid)
    except (potions.PotionError, hp_core.UnknownPlayerError) as e:
        await use_potion_cmd.finish(str(e))
        return
    extra = ""
    if "stamina" in result:
        extra = f"（体力+{result['restored']}，现在{result['stamina']}/{core_storage.STAMINA_MAX}）"
    elif "hp" in result:
        extra = f"（恢复{result['healed']}HP，现在{result['hp']}HP）"
    await use_potion_cmd.finish(f"你使用了「{result['name']}」。{result['effect']}{extra}")


@gift_potion_cmd.handle()
async def handle_gift_potion(event: MessageEvent, args=CommandArg()):
    parts = args.extract_plain_text().strip().split()
    if len(parts) not in (2, 3):
        await gift_potion_cmd.finish("用法：/赠送魔药 药名 对方名字 [数量]")
        return
    try:
        quantity = int(parts[2]) if len(parts) == 3 else 1
        target_uid = hp_core.resolve(parts[1])
        result = potions.gift(event.get_user_id(), target_uid, parts[0], quantity)
    except (ValueError, potions.PotionError, hp_core.UnknownPlayerError) as e:
        await gift_potion_cmd.finish(str(e) if str(e) else "数量必须是整数。")
        return
    await gift_potion_cmd.finish(
        f"🦉 你把「{result['name']}」×{result['quantity']}交给猫头鹰，送到了{result['target_name']}手里。"
        f"（今日赠送{result['today_count']}/{result['daily_limit']}次）"
    )


@potion_record_cmd.handle()
async def handle_potion_record(event: MessageEvent):
    try:
        result = potions.list_recipes(event.get_user_id())
    except potions.PotionError as e:
        await potion_record_cmd.finish(str(e))
        return
    lines = ["📖 我的魔药记录"]
    for row in result["rows"]:
        m = row["mastery"]
        if m:
            lines.append(
                f"{row['name']}【{row['mastery_level']}】：尝试{m['attempts']}次，"
                f"成功{m['successes']}次，完美{m['perfects']}次"
            )
    if len(lines) == 1:
        lines.append("还没有熬制记录。")
    await potion_record_cmd.finish("\n".join(lines))


@potion_titles_cmd.handle()
async def handle_potion_titles(event: MessageEvent):
    rows = potions.title_state(event.get_user_id())
    lines = ["🏅 魔药称号"]
    for row in rows:
        mark = "佩戴中" if row["active"] else "已解锁" if row["unlocked"] else "未解锁"
        lines.append(f"{'✓' if row['unlocked'] else '🔒'} {row['name']}（{mark}）——{row['requirement']}")
    lines.append("发送「/佩戴魔药称号 称号名」佩戴。")
    await potion_titles_cmd.finish("\n".join(lines))


@wear_potion_title_cmd.handle()
async def handle_wear_potion_title(event: MessageEvent, args=CommandArg()):
    try:
        name = potions.wear_title(event.get_user_id(), args.extract_plain_text().strip())
    except potions.PotionError as e:
        await wear_potion_title_cmd.finish(str(e))
        return
    await wear_potion_title_cmd.finish(f"已经佩戴称号「{name}」。")


# ======================== 打工 ========================

work_cmd = on_command("打工")
work_list_cmd = on_command("打工列表")


@work_list_cmd.handle()
async def handle_work_list(event: MessageEvent):
    player = core_storage.get_player(event.get_user_id())
    if not player or not player["house"]:
        await work_list_cmd.finish("先完成入学手续，才能查看城堡里的学生零工。")
        return
    lines = ["📌 城堡零工告示板"]
    for name in work.available_jobs(player["grade"]):
        min_grade, low, high, _ = work.JOBS[name]
        lines.append(f"「{name}」{low}—{high}加隆 · 消耗{work.STAMINA_COST}体力")
    lines.append("发送「/打工 工作名」选择工作；直接发送「/打工」由费尔奇随机安排。")
    await work_list_cmd.finish("\n".join(lines))


@work_cmd.handle()
async def handle_work(event: MessageEvent, args=CommandArg()):
    job_input = args.extract_plain_text().strip()
    try:
        result = work.work(event.get_user_id(), job_input)
    except work.WorkError as e:
        await work_cmd.finish(str(e))
        return
    await work_cmd.finish(
        f"🧹 {result['job']}\n{result['story']}\n"
        f"工资：+{result['earnings']}加隆（现有{result['galleons']}）\n"
        f"今天已打工{result['count']}/{result['daily_limit']}次。"
    )


# ======================== 毕业职业 ========================

career_list_cmd = on_command("职业列表")
choose_career_cmd = on_command("选择职业")
my_career_cmd = on_command("我的职业")


@career_list_cmd.handle()
async def handle_career_list(event: MessageEvent):
    uid = event.get_user_id()
    options = careers.list_options(uid)
    if not any(option["qualified"] for option in options):
        await career_list_cmd.finish("猫头鹰还没有送来你的N.E.W.T.成绩单。毕业后才能选择职业。")
        return
    lines = ["📜 毕业职业指导", "麦格教授把几份申请表推到你面前："]
    recommended_marked = False
    for option in options:
        if option["qualified"]:
            mark = "⭐" if not recommended_marked else "✓"
            recommended_marked = True
        else:
            mark = "🔒"
        lines.append(
            f"{mark}「{option['name']}」· 签约金{option['bonus']}加隆\n"
            f"　{option['desc']}\n　要求：{option['requirement']}"
        )
    lines.append("⭐ 是根据当前资格给出的优先推荐。发送「/选择职业 职业名」确认；选择后不能更改。")
    await career_list_cmd.finish("\n".join(lines))


@choose_career_cmd.handle()
async def handle_choose_career(event: MessageEvent, args=CommandArg()):
    career_input = args.extract_plain_text().strip()
    if not career_input:
        await choose_career_cmd.finish("用法：/选择职业 职业名（先发送「/职业列表」）")
        return
    try:
        result = careers.choose(event.get_user_id(), career_input)
    except careers.CareerError as e:
        await choose_career_cmd.finish(str(e))
        return
    await choose_career_cmd.finish(
        f"🎓 职业登记完成：{result['name']}\n{result['desc']}\n"
        f"录用信随附{result['bonus']}加隆签约金。你的下一段人生开始了。"
    )


@my_career_cmd.handle()
async def handle_my_career(event: MessageEvent):
    career = careers.get(event.get_user_id())
    if not career:
        await my_career_cmd.finish("你还没有登记毕业职业。完成N.E.W.T.后发送「/职业列表」。")
        return
    await my_career_cmd.finish(f"💼 {career['name']}\n{career['desc']}")


# ======================== 施咒 ========================

cast_cmd = on_command("施咒")


@cast_cmd.handle()
async def handle_cast(event: MessageEvent, args=CommandArg()):
    spell_input = args.extract_plain_text().strip()
    if not spell_input:
        await cast_cmd.finish("用法：/施咒 咒语名\n目前能主动施放的：清理一新（洗掉恶作剧）、修复如初（修扫帚）")
        return
    uid = event.get_user_id()
    try:
        result = casting.cast(uid, spell_input)
    except casting.CastError as e:
        await cast_cmd.finish(str(e))
        return
    if "cleared" in result:
        await cast_cmd.finish(f"「{result['spell']}」——身上的{'、'.join(result['cleared'])}都被清干净了。")
    else:
        await cast_cmd.finish(
            f"「{result['spell']}」——{result['name']}修好了，耐久 {result['before']} → {result['after']}。"
        )


# ======================== 对角巷商店 ========================

shop_cmd = on_command("对角巷")


@shop_cmd.handle()
async def handle_shop(event: MessageEvent, args=CommandArg()):
    category = args.extract_plain_text().strip()
    if category and category not in shop_catalog.CATEGORIES:
        await shop_cmd.finish(f"没有这个分类。可选：{'、'.join(shop_catalog.CATEGORIES)}")
        return
    categories = [category] if category else list(shop_catalog.CATEGORIES)
    lines = ["🛒 对角巷"]
    for cat in categories:
        if cat in shop_catalog.ROTATING_CATEGORIES:
            tag = "（每3小时刷新一批）"
        elif cat == "礼物":
            tag = "（全服共享库存，每2小时补货）"
        else:
            tag = ""
        lines.append(f"\n▪ {cat}{tag}")
        for key, name, cat_, price, desc, effect in shop.current_offerings(cat):
            if cat == "礼物":
                left = shop.gift_remaining(key, effect["stock"])
                stock_text = f"[剩{left}/{effect['stock']}]" if left else "[售罄]"
                lines.append(f"「{name}」{price}加隆 {stock_text} —— {desc}")
            else:
                lines.append(f"「{name}」{price}加隆 —— {desc}")
    if not category or category in shop_catalog.ROTATING_CATEGORIES:
        lines.append(f"\n零食/宠物下次刷新还有约{shop.seconds_to_next_rotation() // 60 + 1}分钟。")
    if not category or category == "礼物":
        lines.append(f"礼物下次补货还有约{shop.seconds_to_next_restock() // 60 + 1}分钟。")
    lines.append("用「/对角巷购买 物品名」买，用「/我的背包」看已有的。")
    await shop_cmd.finish("\n".join(lines))


buy_cmd = on_command("对角巷购买")


@buy_cmd.handle()
async def handle_buy(event: MessageEvent, args=CommandArg()):
    item_input = args.extract_plain_text().strip()
    if not item_input:
        await buy_cmd.finish("用法：/对角巷购买 物品名（先「/对角巷」看看卖什么）")
        return
    uid = event.get_user_id()
    try:
        result = shop.buy(uid, item_input)
    except shop.ShopError as e:
        await buy_cmd.finish(str(e))
        return
    player = core_storage.get_player(uid)
    await buy_cmd.finish(f"买到了「{result['name']}」，花了{result['price']}加隆（剩余{player['galleons']}）。")


prank_cmd = on_command("使用恶作剧")


@prank_cmd.handle()
async def handle_prank(event: MessageEvent, args=CommandArg()):
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 2:
        await prank_cmd.finish("用法：/使用恶作剧 物品名 对方名字")
        return
    item_input, target_name = parts
    uid = event.get_user_id()
    try:
        target_uid = hp_core.resolve(target_name)
        result = shop.use_prank(uid, item_input, target_uid)
    except (shop.ShopError, hp_core.UnknownPlayerError) as e:
        await prank_cmd.finish(str(e))
        return
    await prank_cmd.finish(
        f"「{result['name']}」用在了 {target_name} 身上：{result['label']}，持续{result['hours']}小时。"
    )


bag_cmd = on_command("我的背包")


@bag_cmd.handle()
async def handle_bag(event: MessageEvent):
    uid = event.get_user_id()
    items = shop.get_bag(uid)
    if not items:
        await bag_cmd.finish("背包是空的，去「/对角巷」逛逛。")
        return
    lines = ["🎒 我的背包"]
    for item in items:
        lines.append(f"「{item['name']}」×{item['quantity']}（{item['category']}）")
    await bag_cmd.finish("\n".join(lines))


eat_cmd = on_command("吃")


@eat_cmd.handle()
async def handle_eat(event: MessageEvent, args=CommandArg()):
    item_input = args.extract_plain_text().strip()
    if not item_input:
        await eat_cmd.finish("用法：/吃 零食名")
        return
    uid = event.get_user_id()
    try:
        result = shop.eat_snack(uid, item_input)
    except shop.ShopError as e:
        await eat_cmd.finish(str(e))
        return
    await eat_cmd.finish(f"吃了「{result['name']}」，体力值+{result['restored']}（现在{result['new_stamina']}/{core_storage.STAMINA_MAX}）。")


# ======================== 我的成绩 ========================

grades_cmd = on_command("我的面板", aliases={"我的成绩"})


@grades_cmd.handle()
async def handle_my_grades(event: MessageEvent):
    uid = event.get_user_id()
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        await grades_cmd.finish("你还没有分院，先发「/入学 你的名字」完成入学测试。")
        return
    player = core_storage.sync_stamina(uid)
    exp_map = core_storage.get_all_subject_exp(uid)
    day = core_storage.get_current_day() or 1

    full_name = f"{player['name']}·{player['surname']}" if player["surname"] else player["name"]
    lines = [
        f"👤 {full_name}{core_storage.get_status_suffix(uid)}",
        f"{player['house']} · {player['grade']}年级 · 第{day}天",
    ]
    if player["active_title"]:
        lines.append(f"称号：{player['active_title']}")
    wand = storage.get_wand(uid)
    if wand:
        lines.append(f"魔杖：{wand['wood']} · {wand['core']}")
    career = careers.get(uid)
    if career:
        lines.append(f"职业：{career['name']}")
    lines.append(f"体力：{player['stamina']}/{core_storage.STAMINA_MAX}　加隆：{player['galleons']}")
    fatigue = core_storage.get_total_scored_lesson_count(uid, day)
    lines.append(f"课堂疲劳：{fatigue}/{lessons.DAILY_GLOBAL_LIMIT}（每天重置）")

    lines.append("\n📚 学科经验")
    for key, name, unlock_grade, category in subjects.SUBJECTS:
        if player["grade"] < unlock_grade:
            continue
        mark = "🪄" if key in spell_catalog.SPELL_SUBJECTS else "　"
        lines.append(f"{mark}{name}（{category}）：{exp_map.get(key, 0)}")

    learned = core_storage.list_learned_spells(uid)
    lines.append(f"\n🪄 已学魔咒：{len(learned)}/{len(spell_catalog.SPELLS)}（详见「/我的魔咒」）")

    exam_rows = core_storage.get_exam_results(uid)
    if exam_rows:
        latest_grade = max(r["grade"] for r in exam_rows)
        latest = [r for r in exam_rows if r["grade"] == latest_grade]
        exam_name = {5: "O.W.L.", 7: "N.E.W.T."}.get(latest_grade, f"{latest_grade}年级期末")
        lines.append(f"\n📜 最近一次考试（{exam_name}）")
        for r in latest:
            subject_name = subjects.SUBJECTS_BY_KEY.get(r["subject"], (r["subject"],))[0]
            lines.append(f"　{subject_name}：{r['band']}")

    partner_line = _partner_line(uid)
    if partner_line:
        lines.append("\n" + partner_line)

    await grades_cmd.finish("\n".join(lines))


def _partner_line(uid: str) -> str:
    """恋爱状态。hp_social 是独立插件，读不到就当没有，不让面板挂掉。"""
    try:
        from plugins.hp_social import storage as social_storage

        partner = social_storage.get_partner(uid)
        return f"💗 恋爱：与 {core_storage.get_full_name(partner)} 交往中" if partner else ""
    except Exception:
        return ""


# ======================== 排行榜 ========================

student_rank_cmd = on_command("全校排名")


@student_rank_cmd.handle()
async def handle_student_rank(event: MessageEvent):
    rows = core_storage.student_leaderboard()
    if not rows:
        await student_rank_cmd.finish("还没有人分院，暂无排名。")
        return
    lines = ["🏆 全校个人排名（按学科经验总量）"]
    for i, r in enumerate(rows):
        title = f"【{r['active_title']}】" if r["active_title"] else ""
        suffix = core_storage.get_status_suffix(r["uid"])
        lines.append(f"{i + 1}. {title}{r['name']}{suffix}（{r['house']}）—— {r['total_exp']}")
    await student_rank_cmd.finish("\n".join(lines))


house_rank_cmd = on_command("学院排行")


@house_rank_cmd.handle()
async def handle_house_rank(event: MessageEvent):
    rows = core_storage.house_leaderboard()
    lines = ["🏆 学院杯排行（按人均分）"]
    for i, r in enumerate(rows):
        lines.append(
            f"{i + 1}. {r['house']} —— 人均{r['avg_points']:.1f}"
            f"（总分{r['total_points']} / {r['member_count']}人）"
        )
    await house_rank_cmd.finish("\n".join(lines))


sell_cmd = on_command("卖出")


@sell_cmd.handle()
async def handle_sell(event: MessageEvent, args=CommandArg()):
    parts = args.extract_plain_text().strip().split()
    if not parts:
        await sell_cmd.finish("用法：/卖出 材料名 [数量]（禁林带回来的魔药材料可以卖钱）")
        return
    item_input = parts[0]
    quantity = 1
    if len(parts) > 1:
        if not parts[1].isdigit():
            await sell_cmd.finish("数量要是数字。用法：/卖出 材料名 [数量]")
            return
        quantity = int(parts[1])
    uid = event.get_user_id()
    try:
        result = shop.sell(uid, item_input, quantity)
    except shop.ShopError as e:
        await sell_cmd.finish(str(e))
        return
    player = core_storage.get_player(uid)
    await sell_cmd.finish(
        f"卖掉了{result['quantity']}份「{result['name']}」，"
        f"每份{result['unit_price']}加隆，共{result['total']}加隆（现在{player['galleons']}）。"
    )


# ======================== 厨房养成 ========================

def _cook_prompt(result: dict) -> str:
    """烹饪步骤提示。"""
    lines = [f"🔪 {result['recipe']}（第 {result['step']}/{result['total_steps']} 步）"]
    if result.get("resumed"):
        lines.append("继续上次进行到的地方——")
    lines.extend(["", f"**{result['prompt']}**", "", _numbered(result["options"])])
    return "\n".join(lines)


cook_cmd = on_command("烹饪")


@cook_cmd.handle()
async def handle_cook(event: MessageEvent, args=CommandArg()):
    uid = event.get_user_id()
    recipe_input = args.extract_plain_text().strip()
    if not recipe_input:
        await cook_cmd.finish("用法：/烹饪 配方名（比如 /烹饪 炒鸡蛋）\n发送「/烹饪配方」查看已知配方。")
        return

    try:
        result = kitchen.start(uid, recipe_input)
    except kitchen.KitchenError as e:
        await cook_cmd.finish(str(e))
        return

    await cook_cmd.finish(_cook_prompt(result))


cook_choice_cmd = on_command("烹饪选择")


@cook_choice_cmd.handle()
async def handle_cook_choice(event: MessageEvent, args=CommandArg()):
    try:
        position = int(args.extract_plain_text().strip())
        result = kitchen.choose(event.get_user_id(), position)
    except (ValueError, kitchen.KitchenError) as e:
        await cook_choice_cmd.finish(str(e) if str(e) else "用法：/烹饪选择 1/2/3")
        return

    if not result.get("finished"):
        await cook_choice_cmd.finish(_cook_prompt(result))
        return

    if result["success"]:
        text = (
            f"🍳 烹饪完成：{result['recipe']}！"
            f"{'✅ 完美！' if result['perfect'] else '✓ 成功！'}（{result['score']}/{result['max_score']}）\n"
            f"你得到「{result['recipe']}」×{result['quantity']}。\n"
            "发送「/食柜」查看你的存货。"
        )
    else:
        text = (
            f"🔥 烹饪失败。{result['recipe']}在你手中毁了。\n"
            f"😨 不好！{result['accident']}\n"
            "材料没能保住，要先采集新的。"
        )
    await cook_choice_cmd.finish(text)


pantry_cmd = on_command("食柜")


@pantry_cmd.handle()
async def handle_pantry(event: MessageEvent):
    uid = event.get_user_id()
    conn = core_storage.get_conn()
    try:
        player = core_storage.get_player(uid)
        if not player or not player["house"]:
            await pantry_cmd.finish("你还没有分院。先完成 /入学")
            return

        foods = conn.execute(
            "SELECT food_key, quantity FROM kitchen_inventory WHERE uid=? ORDER BY food_key",
            (uid,),
        ).fetchall()

        if not foods:
            await pantry_cmd.finish("你的食柜空空如也。发送 /烹饪 开始制作食物吧。")
            return

        lines = ["🍽️ 你的食柜"]
        total = 0
        for row in foods:
            name = kitchen.item_name(row["food_key"])
            if name:
                lines.append(f"　{name} × {row['quantity']}")
                total += row["quantity"]
        lines.append(f"\n共 {total} 份食物")

        await pantry_cmd.finish("\n".join(lines))
    finally:
        conn.close()


recipe_list_cmd = on_command("烹饪配方")


@recipe_list_cmd.handle()
async def handle_recipe_list(event: MessageEvent):
    uid = event.get_user_id()
    conn = core_storage.get_conn()
    try:
        player = core_storage.get_player(uid)
        if not player or not player["house"]:
            await recipe_list_cmd.finish("你还没有分院。先完成 /入学")
            return

        exp = core_storage.get_cooking_exp(uid)

        learned = {
            r["recipe_key"]: True
            for r in conn.execute("SELECT recipe_key FROM kitchen_learned_recipes WHERE uid=?", (uid,)).fetchall()
        }

        lines = [f"📖 你的配方书（烹饪经验 {exp}）"]
        by_category = {}
        for key, recipe in kitchen.RECIPES.items():
            cat = recipe.get("category", "other")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append((key, recipe))

        cat_names = {
            "breakfast": "🌅 早餐",
            "main": "🍽️ 主食",
            "soup": "🍲 汤类",
            "dessert": "🍰 甜点",
            "magic": "✨ 魔法美食",
            "beverage": "☕ 饮品",
            "snack": "🍪 点心小食",
        }

        for cat_key in ["breakfast", "main", "soup", "dessert", "magic", "beverage", "snack"]:
            if cat_key not in by_category:
                continue
            lines.append(f"\n{cat_names.get(cat_key, cat_key)}")
            for key, recipe in sorted(by_category[cat_key], key=lambda x: x[0]):
                unlocked = player["grade"] >= recipe["grade"] and exp >= recipe["exp"]
                if key in learned:
                    marker = "✓"
                elif unlocked:
                    marker = "○"
                else:
                    marker = "×"
                lines.append(
                    f"　{marker} {recipe['name']}"
                    f"（{recipe['grade']}年级,{recipe['exp']}经验）"
                )

        await recipe_list_cmd.finish("\n".join(lines))
    finally:
        conn.close()


consume_food_cmd = on_command("食用")


@consume_food_cmd.handle()
async def handle_consume_food(event: MessageEvent, args=CommandArg()):
    uid = event.get_user_id()
    food_input = args.extract_plain_text().strip()
    if not food_input:
        await consume_food_cmd.finish("用法：/食用 食物名（比如 /食用 炒鸡蛋）\n发送「/食柜」查看你有什么。")
        return

    try:
        result = kitchen.consume(uid, food_input)
    except kitchen.KitchenError as e:
        await consume_food_cmd.finish(str(e))
        return

    # 应用buff效果
    found = kitchen.find_recipe(food_input)
    if found:
        recipe_key = found[0]
        effects = kitchen.apply_food_effects(uid, recipe_key)

    lines = [
        f"😋 你享受了一份「{result['recipe']}」",
        "",
        f"效果：{result['effect']}",
    ]

    if result["remaining"] > 0:
        lines.append(f"\n（食柜还剩 {result['remaining']} 份）")
    else:
        lines.append("\n（食柜里这个没了）")

    await consume_food_cmd.finish("\n".join(lines))


# ======================== 竞选新人王 ========================


freshman_duel_cmd = on_command("竞选")


@freshman_duel_cmd.handle()
async def handle_freshman_duel(event: MessageEvent):
    uid = event.get_user_id()
    player = core_storage.get_player(uid)

    if not player or not player["house"]:
        await freshman_duel_cmd.finish("你还没有分院。先完成 /入学")
        return

    if player["grade"] != 1:
        await freshman_duel_cmd.finish("竞选新人王只对一年级学生开放。")
        return

    result = freshman_duel.perform_duel(uid)
    await freshman_duel_cmd.finish(result["message"])


freshman_rank_cmd = on_command("新人王排名")


@freshman_rank_cmd.handle()
async def handle_freshman_rank(event: MessageEvent):
    uid = event.get_user_id()
    player = core_storage.get_player(uid)

    if not player or not player["house"]:
        await freshman_rank_cmd.finish("你还没有分院。先完成 /入学")
        return

    message = freshman_duel.get_leaderboard()
    await freshman_rank_cmd.finish(message)

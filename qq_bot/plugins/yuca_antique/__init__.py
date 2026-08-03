import random

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, MessageSegment
from nonebot.params import CommandArg

from . import catalog, engine, storage, titles

# ======================== 文案（伊利亚·库里亚金语气：短句、陈述式、克制） ========================

EMPTY_REMARKS = [
    "转了一圈，两手空空。这行当就是这样。",
    "没有发现。记下这个地方，下次换一处。",
    "一无所获。不算意外。",
]

FOUND_STONE_REMARKS = ["带回一块原石，外皮看不出什么。开了才知道。"]
FOUND_ANTIQUE_REMARKS = ["捡到一件东西，年份和真假都还是谜。"]

STONE_QUALITY_REMARKS = {
    "传世": ["开出来了。这种运气，一辈子遇不上几次。", "传世级。你可以骄傲一秒，仅此一次。"],
    "极品": ["料子不错。今天算你赢。", "极品成色。别问怎么算的，运气就是运气。"],
    "精品": ["够格摆上台面的东西。", "成色可以，不算亏。"],
    "上品": ["中规中矩，能出手。", "不算差，也说不上惊喜。"],
    "普通": ["普通料子。至少不是废石。", "一般般。见得多了。"],
}

DIRT_REMARKS = [
    "挖到一把土。矿脉这东西，十有八九是这个结果。",
    "刨了半天，除了土什么都没有。",
    "土。踏实，但不值钱。",
]
GEM_QUALITY_REMARKS = {
    "传世": ["这颗成色，够进博物馆了。运气用在了刀刃上。", "净度和光泽都挑不出毛病。今天算你的。"],
    "极品": ["成色不错。矿工都得眼红。", "这颗拿得出手。"],
    "精品": ["能算件像样的东西。", "成色可以，不亏。"],
    "上品": ["中规中矩。", "不算差。"],
    "普通": ["普通货色。至少不是石头。", "一般般，见过更好的。"],
}

IDENTIFY_SUCCESS_REMARKS = [
    "判断没错。眼力没白练。",
    "对上了。这次算你稳。",
    "看准了。记下来，这是你的水平。",
]
IDENTIFY_FAIL_REMARKS = [
    "看走眼了。这行当谁都躲不过这一下。",
    "判断错了。别往心里去，下次再看。",
    "不予置评。这次算学费。",
]

LEVELUP_REMARK = "眼力见涨。程序已更新你的档案。"

SELL_REMARKS = ["成交。钱已经到账。", "出手了。这个价，不算亏也不算赚翻。"]


def _fmt_item_brief(item) -> str:
    if item["kind"] == "gem":
        return f"#{item['id']} {item['type_name']}（{item['quality']}）"
    if item["kind"] == "stone":
        if not item["is_opened"]:
            return f"#{item['id']} 未开原石"
        return f"#{item['id']} {item['type_name']}（{item['quality']}）"
    if not item["is_identified"]:
        return f"#{item['id']} 待鉴定{item['category']}（{item['category']}类）"
    label = item["type_name"] if item["identify_correct"] else f"{item['perceived_type']}（存疑）"
    dynasty = item["dynasty"] if item["identify_correct"] else item["perceived_dynasty"]
    return f"#{item['id']} {dynasty}·{label}（{item['quality']}）"


def _status_tag(item) -> str:
    return {"背包": "", "展示柜": "［展示柜］", "已卖出": "［已卖出］"}.get(item["status"], "")


def _fmt_new_titles(new_titles: list[titles.TitleDef]) -> str:
    if not new_titles:
        return ""
    lines = [f"解锁称号：{t.name}（{t.desc}）" for t in new_titles]
    return "\n" + "\n".join(lines)


# ======================== 探宝 ========================

explore_cmd = on_command("探宝")


@explore_cmd.handle()
async def handle_explore(event: MessageEvent):
    uid = event.get_user_id()
    try:
        result = engine.explore(uid)
    except engine.GameError as e:
        await explore_cmd.finish(str(e))
        return

    if result["outcome"] == "empty":
        await explore_cmd.finish(random.choice(EMPTY_REMARKS))
        return
    item = result["item"]
    if result["outcome"] == "stone":
        text = f"{random.choice(FOUND_STONE_REMARKS)}\n编号 #{item['id']}，用 /开石 {item['id']} 处理。"
    else:
        label = "字画" if result["outcome"] == "calligraphy" else "古董"
        text = (
            f"{random.choice(FOUND_ANTIQUE_REMARKS)}（{label}类）\n"
            f"编号 #{item['id']}，用 /观察 {item['id']} 看细节，或直接 /鉴定 {item['id']}。"
        )
    await explore_cmd.finish(text)


luck_cmd = on_command("我的运气")


@luck_cmd.handle()
async def handle_luck(event: MessageEvent):
    player = engine.sync_player(event.get_user_id())
    if player["luck"] >= engine.LUCK_MAX:
        text = f"运气：{player['luck']}/{engine.LUCK_MAX}（已满，可以出门了）"
    else:
        secs = engine.seconds_to_next_luck(player)
        text = f"运气：{player['luck']}/{engine.LUCK_MAX}\n下一点还需 {secs // 60 + 1} 分钟。"
    await luck_cmd.finish(text)


# ======================== 开石 ========================

open_cmd = on_command("开石")


@open_cmd.handle()
async def handle_open(event: MessageEvent, args=CommandArg()):
    raw = args.extract_plain_text().strip()
    if not raw.isdigit():
        await open_cmd.finish("格式：/开石 编号")
        return
    uid = event.get_user_id()
    try:
        result = engine.open_stone(uid, int(raw))
    except engine.GameError as e:
        await open_cmd.finish(str(e))
        return
    item = result["item"]
    remark = random.choice(STONE_QUALITY_REMARKS.get(item["quality"], ["开了。"]))
    text = (
        f"石开了。{item['type_name']}，{item['quality']}。\n{remark}\n"
        f"可以 /拍卖 {item['id']} 变现，或 /上柜 {item['id']} 摆展示柜。"
        f"{_fmt_new_titles(result['new_titles'])}"
    )
    await open_cmd.finish(text)


# ======================== 挖矿 ========================

mine_cmd = on_command("挖矿")


@mine_cmd.handle()
async def handle_mine(event: MessageEvent):
    uid = event.get_user_id()
    try:
        result = engine.mine(uid)
    except engine.GameError as e:
        await mine_cmd.finish(str(e))
        return

    if result["outcome"] == "dirt":
        await mine_cmd.finish(random.choice(DIRT_REMARKS) + _fmt_new_titles(result["new_titles"]))
        return
    item = result["item"]
    remark = random.choice(GEM_QUALITY_REMARKS.get(item["quality"], ["挖到了。"]))
    text = (
        f"挖到了。{item['type_name']}，{item['quality']}。\n{remark}\n"
        f"可以 /拍卖 {item['id']} 变现，或 /上柜 {item['id']} 摆展示柜。"
        f"{_fmt_new_titles(result['new_titles'])}"
    )
    await mine_cmd.finish(text)


# ======================== 观察与鉴定 ========================

observe_cmd = on_command("观察")


@observe_cmd.handle()
async def handle_observe(event: MessageEvent, args=CommandArg()):
    raw = args.extract_plain_text().strip()
    if not raw.isdigit():
        await observe_cmd.finish("格式：/观察 编号")
        return
    uid = event.get_user_id()
    try:
        result = engine.observe(uid, int(raw))
    except engine.GameError as e:
        await observe_cmd.finish(str(e))
        return
    text = f"【{result['dimension']}】{result['text']}\n已看 {result['clue_count']}/{engine.MAX_CLUES_PER_ITEM} 处。可继续 /观察，或 /鉴定 {raw}。"
    await observe_cmd.finish(text)


identify_cmd = on_command("鉴定")


@identify_cmd.handle()
async def handle_identify(event: MessageEvent, args=CommandArg()):
    raw = args.extract_plain_text().strip()
    if not raw.isdigit():
        await identify_cmd.finish("格式：/鉴定 编号")
        return
    uid = event.get_user_id()
    try:
        result = engine.identify(uid, int(raw))
    except engine.GameError as e:
        await identify_cmd.finish(str(e))
        return

    if result["success"]:
        lines = [
            f"判定：D100={result['roll']}/{result['chance']} —— 通过。",
            random.choice(IDENTIFY_SUCCESS_REMARKS),
            f"这是{result['true_dynasty']}·{result['true_type']}。",
        ]
    else:
        lines = [
            f"判定：D100={result['roll']}/{result['chance']} —— 未过。",
            random.choice(IDENTIFY_FAIL_REMARKS),
            f"你记录下的结论是：{result['perceived_dynasty']}·{result['perceived_type']}。",
        ]
    if result["leveled_up"]:
        lines.append(f"眼力升至 {result['eye_level']} 级。{LEVELUP_REMARK}")
    lines.append(f"可以 /拍卖 {raw} 变现，或 /上柜 {raw} 摆展示柜。")
    await identify_cmd.finish("\n".join(lines) + _fmt_new_titles(result["new_titles"]))


# ======================== 背包与拍卖 ========================

bag_cmd = on_command("我的藏品")


@bag_cmd.handle()
async def handle_bag(event: MessageEvent):
    items = storage.list_items(event.get_user_id())
    items = [i for i in items if i["status"] != "已卖出"]
    if not items:
        await bag_cmd.finish("背包是空的。去 /探宝 找点东西回来。")
        return
    lines = ["🗂 藏品清单"]
    for item in items:
        lines.append(_fmt_item_brief(item) + _status_tag(item))
    await bag_cmd.finish("\n".join(lines))


sell_cmd = on_command("拍卖")


@sell_cmd.handle()
async def handle_sell(event: MessageEvent, args=CommandArg()):
    raw = args.extract_plain_text().strip()
    if not raw.isdigit():
        await sell_cmd.finish("格式：/拍卖 编号")
        return
    uid = event.get_user_id()
    try:
        result = engine.sell_item(uid, int(raw))
    except engine.GameError as e:
        await sell_cmd.finish(str(e))
        return
    text = f"{random.choice(SELL_REMARKS)}\n{result['note']}。\n成交价：{result['price']}。"
    await sell_cmd.finish(text + _fmt_new_titles(result["new_titles"]))


# ======================== 展示柜 ========================

showcase_add_cmd = on_command("上柜")


@showcase_add_cmd.handle()
async def handle_showcase_add(event: MessageEvent, args=CommandArg()):
    raw = args.extract_plain_text().strip()
    if not raw.isdigit():
        await showcase_add_cmd.finish("格式：/上柜 编号")
        return
    uid = event.get_user_id()
    item = storage.get_item(int(raw))
    if not item or item["uid"] != uid:
        await showcase_add_cmd.finish("找不到这件东西，检查一下编号。")
        return
    if item["status"] != "背包":
        await showcase_add_cmd.finish("这件东西不在背包里。")
        return
    if item["kind"] == "stone" and not item["is_opened"]:
        await showcase_add_cmd.finish("原石还没开，先 /开石。")
        return
    if item["kind"] == "antique" and not item["is_identified"]:
        await showcase_add_cmd.finish("还没鉴定，先 /鉴定。")
        return
    storage.update_item(item["id"], status="展示柜")
    await showcase_add_cmd.finish(f"#{raw} 摆上展示柜了。")


showcase_remove_cmd = on_command("下柜")


@showcase_remove_cmd.handle()
async def handle_showcase_remove(event: MessageEvent, args=CommandArg()):
    raw = args.extract_plain_text().strip()
    if not raw.isdigit():
        await showcase_remove_cmd.finish("格式：/下柜 编号")
        return
    uid = event.get_user_id()
    item = storage.get_item(int(raw))
    if not item or item["uid"] != uid or item["status"] != "展示柜":
        await showcase_remove_cmd.finish("展示柜里没有这件东西。")
        return
    storage.update_item(item["id"], status="背包")
    await showcase_remove_cmd.finish(f"#{raw} 收回背包了。")


showcase_view_cmd = on_command("展示柜")


@showcase_view_cmd.handle()
async def handle_showcase_view(event: MessageEvent, args=CommandArg()):
    raw = args.extract_plain_text().strip()
    uid = raw if raw else event.get_user_id()
    items = storage.list_items(uid, status="展示柜")
    who = "你的" if uid == event.get_user_id() else f"{uid} 的"
    if not items:
        await showcase_view_cmd.finish(f"{who}展示柜是空的。")
        return
    lines = [f"🗂 {who}展示柜"]
    for item in items:
        lines.append(_fmt_item_brief(item))
    await showcase_view_cmd.finish("\n".join(lines))


# ======================== 排行榜 ========================

RANKING_ALIASES = {"身家": "money", "眼力": "eye", "镇店之宝": "showcase", "稀有度": "showcase"}

rank_cmd = on_command("排行榜")


@rank_cmd.handle()
async def handle_rank(event: MessageEvent, args=CommandArg()):
    raw = args.extract_plain_text().strip()
    kind = RANKING_ALIASES.get(raw)
    sections = []

    def _title_prefix(row) -> str:
        key = row["active_title"] if "active_title" in row.keys() else ""
        t = titles.TITLES_BY_KEY.get(key)
        return f"【{t.name}】" if t else ""

    if kind in (None, "money"):
        rows = storage.leaderboard_money()
        lines = [f"{i + 1}. {_title_prefix(r)}{r['uid']} —— {r['money']}" for i, r in enumerate(rows)] or ["暂无记录。"]
        sections.append("▪ 身家榜\n" + "\n".join(lines))
    if kind in (None, "eye"):
        rows = storage.leaderboard_eye()
        lines = [f"{i + 1}. {_title_prefix(r)}{r['uid']} —— {r['eye_level']}级" for i, r in enumerate(rows)] or ["暂无记录。"]
        sections.append("▪ 眼力榜\n" + "\n".join(lines))
    if kind in (None, "showcase"):
        rows = storage.leaderboard_showcase()
        lines = [
            f"{i + 1}. {_title_prefix(r)}{r['uid']} —— {r['dynasty']}·{r['type_name']}（{r['quality']}）"
            for i, r in enumerate(rows)
        ] or ["暂无记录。"]
        sections.append("▪ 镇店之宝榜\n" + "\n".join(lines))

    await rank_cmd.finish("\n\n".join(sections))


# ======================== 图鉴 ========================

codex_cmd = on_command("藏品图鉴")


@codex_cmd.handle()
async def handle_codex(event: MessageEvent, args=CommandArg()):
    raw = args.extract_plain_text().strip()
    uid = event.get_user_id()

    if not raw:
        progress = engine.codex_progress(uid)
        lines = ["🗂 图鉴总览"]
        for cat in catalog.ITEM_TYPES_BY_CATEGORY:
            d, t = progress[cat]
            lines.append(f"{cat}：{d}/{t}")
        lines.append("")
        lines.append("查看某一类的详情：/藏品图鉴 类别名，如 /藏品图鉴 瓷器")
        await codex_cmd.finish("\n".join(lines))
        return

    if raw not in catalog.ITEM_TYPES_BY_CATEGORY:
        cats = "、".join(catalog.ITEM_TYPES_BY_CATEGORY.keys())
        await codex_cmd.finish(f"没有这个类别。可选：{cats}")
        return

    detail = engine.codex_detail(uid, raw)
    lines = [f"🗂 图鉴·{raw}"]
    for name, found in detail:
        lines.append(f"{'✓' if found else '？'} {name}")
    await codex_cmd.finish("\n".join(lines))


# ======================== 称号 ========================

title_list_cmd = on_command("称号")


@title_list_cmd.handle()
async def handle_title_list(event: MessageEvent):
    uid = event.get_user_id()
    owned = storage.list_titles(uid)
    if not owned:
        await title_list_cmd.finish("还没有解锁任何称号。去探宝、挖矿、鉴定攒点战绩。")
        return
    player = storage.get_or_create_player(uid)
    lines = ["🗂 称号档案"]
    for row in owned:
        t = titles.TITLES_BY_KEY.get(row["title_key"])
        if not t:
            continue
        mark = "（当前佩戴）" if player["active_title"] == t.key else ""
        lines.append(f"· {t.name}{mark} —— {t.desc}")
    lines.append("")
    lines.append("佩戴：/佩戴称号 称号名")
    await title_list_cmd.finish("\n".join(lines))


title_wear_cmd = on_command("佩戴称号")


@title_wear_cmd.handle()
async def handle_title_wear(event: MessageEvent, args=CommandArg()):
    raw = args.extract_plain_text().strip()
    uid = event.get_user_id()
    if not raw:
        storage.update_player(uid, active_title="")
        await title_wear_cmd.finish("已卸下称号。")
        return
    match = next((t for t in titles.TITLE_DEFS if t.name == raw), None)
    if not match or not storage.has_title(uid, match.key):
        await title_wear_cmd.finish("没有这个称号，或者还没解锁。")
        return
    storage.update_player(uid, active_title=match.key)
    await title_wear_cmd.finish(f"称号已切换为「{match.name}」。")


# ======================== 帮助 ========================

HELP_TEXT = """# 🗂 掌眼事务处理程序

### 运气
运气值是行动的前提，随时间自然恢复，上限 20，每 10 分钟回 1 点。
- `/我的运气` —— 查询当前运气与恢复进度

### 探宝
- `/探宝` —— 消耗 5 点运气，外出寻找原石、古董或字画。结果全凭运气

### 挖矿
- `/挖矿` —— 消耗 5 点运气，下矿找宝石。多数时候只有土，偶尔出宝石乃至钻石

### 玉石
- `/开石 编号` —— 打开原石，直接揭晓种水与品相

### 古董与字画
- `/观察 编号` —— 查看一处细节线索，每件最多看 3 处，眼力越高线索越准
- `/鉴定 编号` —— 判定真实年份与品类。眼力和线索能提高胜算，但成功率封顶 90%，运气始终占一部分。判定错了会记录一个错误结论，可能影响出手价格

### 变现
- `/拍卖 编号` —— 送去拍卖行直接成交。价格由品相、朝代、是否鉴定/鉴定是否正确决定，且有随机浮动
- `/我的藏品` —— 查看背包里还没出手的东西

### 展示柜
- `/上柜 编号` / `/下柜 编号` —— 管理展示柜，只有开过的原石或鉴定过的古董/字画能上柜
- `/展示柜 [QQ号]` —— 查看自己或他人的展示柜，留空查自己

### 藏品图鉴
- `/藏品图鉴` —— 查看各大类的收集进度
- `/藏品图鉴 类别名` —— 查看某一类里具体收集了哪些，如 `/藏品图鉴 瓷器`。玉石/古董靠鉴定正确才算收录，别指望蒙混过关

### 称号
- `/称号` —— 查看已解锁的称号，称号在完成特定成就时自动解锁
- `/佩戴称号 称号名` —— 佩戴一个称号，会显示在排行榜名字前。留空则卸下

### 排行榜
- `/排行榜 [身家|眼力|镇店之宝]` —— 留空查看全部三项

---
每人的账本独立，互不干扰。谁挖到什么、判断对不对，都记在你自己的档案里。
"""

help_cmd = on_command("寻宝帮助")


@help_cmd.handle()
async def handle_help():
    await help_cmd.finish(MessageSegment.markdown(HELP_TEXT))

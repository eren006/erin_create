from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg

from . import pet, storage

storage.init_db()


def _bar(value: int, max_value: int = 100) -> str:
    pct = max(0, min(100, int(value / max_value * 100)))
    return "█" * (pct // 10) + "░" * (10 - pct // 10)


def _level_up_suffix(level_up: int | None) -> str:
    return f"\n🎉 羁绊等级提升到 Lv.{level_up}！" if level_up else ""


# ======================== 领养 / 状态 / 改名 / 放生 ========================

adopt_cmd = on_command("领养宠物")


@adopt_cmd.handle()
async def handle_adopt(event: MessageEvent, args=CommandArg()):
    item_input = args.extract_plain_text().strip()
    if not item_input:
        await adopt_cmd.finish("用法：/领养宠物 宠物名（先去对角巷「/购买 宠物名」买一只）")
        return
    try:
        result = pet.adopt(event.get_user_id(), item_input)
    except pet.PetError as e:
        await adopt_cmd.finish(str(e))
        return
    equip_hint = (
        "它现在是你装备的宠物。"
        if result["equipped"]
        else f"用「/装备宠物 {result['pet_name']}」可以让它替换掉当前装备的宠物。"
    )
    await adopt_cmd.finish(
        f"🐾 你领养了一只{result['family_name']}——「{result['pet_name']}」！\n"
        f"性格：{result['personality']}\n{equip_hint}\n"
        "用「/宠物改名 新名字」给它取个专属的名字，"
        "「/喂宠物」「/逗宠物」「/遛宠物」「/训练宠物」都能增进感情。"
    )


mine_cmd = on_command("我的宠物们")


@mine_cmd.handle()
async def handle_mine(event: MessageEvent):
    pets = pet.my_pets(event.get_user_id())
    if not pets:
        await mine_cmd.finish("你还没有宠物。先去对角巷「/购买」一只，再用「/领养宠物 名字」养起来。")
        return
    lines = ["🐾 你养的宠物"]
    for p in pets:
        mark = "👉 " if p["equipped"] else "　"
        lines.append(f"{mark}{p['pet_name']}（{p['family_name']}·{p['breed_name']}）Lv.{p['bond_level']}")
    lines.append("\n用「/装备宠物 名字」切换当前互动的宠物。")
    await mine_cmd.finish("\n".join(lines))


equip_cmd = on_command("装备宠物")


@equip_cmd.handle()
async def handle_equip(event: MessageEvent, args=CommandArg()):
    name_input = args.extract_plain_text().strip()
    if not name_input:
        await equip_cmd.finish("用法：/装备宠物 名字（用「/我的宠物们」看看有哪些）")
        return
    try:
        result = pet.equip(event.get_user_id(), name_input)
    except pet.PetError as e:
        await equip_cmd.finish(str(e))
        return
    await equip_cmd.finish(f"已装备「{result['pet_name']}」，现在跟它互动了。")


status_cmd = on_command("我的宠物")


@status_cmd.handle()
async def handle_status(event: MessageEvent):
    try:
        result = pet.status(event.get_user_id())
    except pet.PetError as e:
        await status_cmd.finish(str(e))
        return
    next_hint = (
        f"（还差{result['next_level_at'] - result['bond_exp']}点羁绊经验升到下一级）"
        if result["next_level_at"] is not None
        else "（已经满级）"
    )
    lines = [
        f"🐾 {result['pet_name']}（{result['breed_name']}·{result['personality']}）",
        f"心情 {_bar(result['mood'])} {result['mood']}/100",
        f"饱食度 {_bar(result['satiety'])} {result['satiety']}/100",
        f"羁绊 Lv.{result['bond_level']}（{result['bond_exp']}点）{next_hint}",
        f"联动加成：{result['perk']}",
    ]
    if result["satiety"] <= 20:
        lines.append("⚠️ 快饿坏了，去「/喂宠物」吧。")
    elif result["mood"] <= 20:
        lines.append("⚠️ 心情低落，去「/逗宠物」或「/遛宠物」哄哄它。")
    await status_cmd.finish("\n".join(lines))


rename_cmd = on_command("宠物改名")


@rename_cmd.handle()
async def handle_rename(event: MessageEvent, args=CommandArg()):
    new_name = args.extract_plain_text().strip()
    if not new_name:
        await rename_cmd.finish("用法：/宠物改名 新名字")
        return
    try:
        result = pet.rename(event.get_user_id(), new_name)
    except pet.PetError as e:
        await rename_cmd.finish(str(e))
        return
    await rename_cmd.finish(f"「{result['old_name']}」改名成「{result['pet_name']}」了。")


release_cmd = on_command("放生宠物")


@release_cmd.handle()
async def handle_release(event: MessageEvent, args=CommandArg()):
    name_input = args.extract_plain_text().strip()
    if not name_input:
        await release_cmd.finish("用法：/放生宠物 名字（用「/我的宠物们」看看有哪些）")
        return
    try:
        result = pet.release(event.get_user_id(), name_input)
    except pet.PetError as e:
        await release_cmd.finish(str(e))
        return
    equip_note = "它之前是你装备的宠物，现在没有宠物装备中了，记得「/装备宠物」换一只。" if result["was_equipped"] else ""
    await release_cmd.finish(
        f"你把「{result['pet_name']}」放生了。它攒下的羁绊等级不会保留。{equip_note}"
    )


# ======================== 互动 ========================

feed_cmd = on_command("喂宠物")


@feed_cmd.handle()
async def handle_feed(event: MessageEvent, args=CommandArg()):
    food_input = args.extract_plain_text().strip()
    if not food_input:
        await feed_cmd.finish("用法：/喂宠物 食材或零食名（比如 /喂宠物 鸡蛋）")
        return
    try:
        result = pet.feed(event.get_user_id(), food_input)
    except pet.PetError as e:
        await feed_cmd.finish(str(e))
        return
    await feed_cmd.finish(
        f"{result['line']}\n"
        f"用掉了「{result['item_name']}」。心情{result['mood']}/100，饱食度{result['satiety']}/100。"
        f"{_level_up_suffix(result['level_up'])}"
    )


play_cmd = on_command("逗宠物")


@play_cmd.handle()
async def handle_play(event: MessageEvent):
    try:
        result = pet.play(event.get_user_id())
    except pet.PetError as e:
        await play_cmd.finish(str(e))
        return
    await play_cmd.finish(
        f"{result['line']}\n心情{result['mood']}/100。{_level_up_suffix(result['level_up'])}"
    )


WALK_OUTCOME_EXTRA = {
    "material": lambda r: f"带回来了「{r.get('material')}」。",
    "galleons": lambda r: f"意外多了{r.get('galleons')}加隆。",
}

walk_cmd = on_command("遛宠物")


@walk_cmd.handle()
async def handle_walk(event: MessageEvent):
    try:
        result = pet.walk(event.get_user_id())
    except pet.PetError as e:
        await walk_cmd.finish(str(e))
        return
    extra_fn = WALK_OUTCOME_EXTRA.get(result["outcome"])
    extra = extra_fn(result) + "\n" if extra_fn else ""
    await walk_cmd.finish(
        f"{result['line']}\n{extra}"
        f"心情{result['mood']}/100，饱食度{result['satiety']}/100。"
        f"{_level_up_suffix(result['level_up'])}"
    )


train_cmd = on_command("训练宠物")


@train_cmd.handle()
async def handle_train(event: MessageEvent):
    try:
        result = pet.train(event.get_user_id())
    except pet.PetError as e:
        await train_cmd.finish(str(e))
        return
    await train_cmd.finish(
        f"{result['line']}\n"
        f"心情{result['mood']}/100，饱食度{result['satiety']}/100，羁绊经验{result['bond_exp']}。"
        f"{_level_up_suffix(result['level_up'])}"
    )

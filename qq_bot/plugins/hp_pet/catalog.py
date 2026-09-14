"""宠物品种归类（对角巷卖的 pet_* 道具只是图鉴收藏，这里给它们接上真正的养成玩法）
以及各动作按性格随机抽取的flavor文案池。"""

from __future__ import annotations

import random

FAMILY_NAMES = {"cat": "猫", "owl": "猫头鹰", "toad": "蟾蜍", "rat": "老鼠", "magical": "神奇生物"}

# 只能靠"照料神奇生物"活动小概率获得的限定宠物，不在对角巷卖
MAGICAL_PET_KEYS = ("pet_niffler", "pet_unicorn_foal", "pet_bowtruckle")

# 蟾蜍/老鼠都归进"forest"联动组——原著里都是不起眼但陪你在禁林壮胆的角色
FOREST_ASSIST_FAMILIES = ("toad", "rat")

PERSONALITIES = ("黏人", "高冷", "贪吃", "机灵", "勇敢", "胆小", "话痨", "慢热")


def family_of(item_key: str) -> str | None:
    if item_key.startswith("pet_cat"):
        return "cat"
    if item_key.startswith("pet_owl"):
        return "owl"
    if item_key == "pet_toad":
        return "toad"
    if item_key == "pet_rat":
        return "rat"
    if item_key in MAGICAL_PET_KEYS:
        return "magical"
    return None


def random_personality() -> str:
    return random.choice(PERSONALITIES)


FEED_LINES = {
    "黏人": ["{n}蹭着你的手心把东西吃完，吃完了还不肯挪窝。", "{n}叼着食物非要贴在你脚边吃。"],
    "高冷": ["{n}扫了一眼食物，慢悠悠地才肯赏脸吃掉。", "{n}吃得很矜持，仿佛在施舍面子给你。"],
    "贪吃": ["{n}几乎是抢过去的，三两下就吃得干干净净。", "{n}吃完还眼巴巴看着你，像是没吃够。"],
    "机灵": ["{n}叼起食物躲到一边，吃得又快又利索。", "{n}似乎在盘算下一顿该怎么再跟你要。"],
    "勇敢": ["{n}大摇大摆地走过来，毫不客气地开吃。", "{n}吃东西的架势像是天不怕地不怕。"],
    "胆小": ["{n}先探头探脑张望了半天，才敢凑近吃。", "{n}一边吃一边警惕地留意着四周。"],
    "话痨": ["{n}一边吃一边叽叽喳喳，像是在跟你汇报好不好吃。", "{n}吃完还冲你叫唤了好几声。"],
    "慢热": ["{n}慢吞吞地凑过来，确认真的是给它的才肯吃。", "{n}吃得不紧不慢，倒也吃得干干净净。"],
}

PLAY_LINES = {
    "黏人": ["{n}整个扑进你怀里，蹭了半天不肯下来。", "{n}追着你的手指转圈，玩得舍不得停。"],
    "高冷": ["{n}起初爱答不理，玩着玩着还是暴露了真实的开心。", "{n}表面淡定，尾巴却出卖了它的兴奋。"],
    "贪吃": ["{n}把玩具当成了食物，追咬得格外起劲。", "玩到一半{n}突然想起了吃的，跑去看食盆。"],
    "机灵": ["{n}三两下就摸清了你手里的把戏，玩得游刃有余。", "{n}反过来把你逗得团团转。"],
    "勇敢": ["{n}扑向你手里的东西，一点不怯场。", "{n}玩得很豪迈，动静大得吸引了别人的注意。"],
    "胆小": ["{n}一开始躲躲闪闪，玩熟了才敢放开。", "{n}被突然的动静吓了一下，很快又凑了回来。"],
    "话痨": ["{n}边玩边叫，气氛热闹得像在开派对。", "{n}玩得起劲，叫声一阵接一阵。"],
    "慢热": ["{n}起初不太搭理你，玩了一会儿才渐渐放松下来。", "{n}慢慢凑近，最后玩得比谁都投入。"],
}

TRAIN_LINES = {
    "黏人": "{n}虽然有点累，还是乖乖跟着你练完了。",
    "高冷": "{n}全程一副不情不愿的样子，动作却出乎意料地标准。",
    "贪吃": "{n}三心二意，中途还惦记着零食，但总算练完了。",
    "机灵": "{n}一学就会，动作干净利落。",
    "勇敢": "{n}练得又猛又冲，累得呼呼喘气也不肯停。",
    "胆小": "{n}起初有点畏缩，鼓励了几次才敢放开练。",
    "话痨": "{n}一边练一边叫个不停，像是在给自己加油。",
    "慢热": "{n}节奏很慢，但一步一步都踩得很稳。",
}


def feed_line(personality: str, pet_name: str) -> str:
    return random.choice(FEED_LINES[personality]).format(n=pet_name)


def play_line(personality: str, pet_name: str) -> str:
    return random.choice(PLAY_LINES[personality]).format(n=pet_name)


def train_line(personality: str, pet_name: str) -> str:
    return TRAIN_LINES[personality].format(n=pet_name)


# 遛宠物的结果不看性格看运气，四个结果权重加起来是1.0
WALK_OUTCOMES = ("normal", "material", "galleons", "spooked")
WALK_WEIGHTS = (0.60, 0.20, 0.10, 0.10)

WALK_LINES = {
    "normal": "{n}陪你在城堡附近溜达了一圈，心满意足。",
    "material": "{n}叼回来一份东西，看着还挺有用。",
    "galleons": "{n}不知道从哪叼回来几个加隆，你也没好意思细问。",
    "spooked": "{n}追着什么东西窜进了灌木丛，好一会儿才灰头土脸地跑回来。",
}


def roll_walk_outcome() -> str:
    return random.choices(WALK_OUTCOMES, weights=WALK_WEIGHTS, k=1)[0]

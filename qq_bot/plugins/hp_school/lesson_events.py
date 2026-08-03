"""带持久化会话的课堂微型事件。每门课有10个情境模板。"""

import random
import secrets

from plugins.hp_core import storage as core_storage

from . import lessons, storage, subjects


class LessonEventError(Exception):
    pass


# 三种处理风格会按情境轮换最佳解，避免永远点击同一个按钮。
CHOICES = (
    ("严格按课本步骤", "你稳稳完成了要求，教授满意地点了点头。"),
    ("大胆尝试新方法", "你的做法让全班捏了把汗，好在最后控制住了局面。"),
    ("先观察再随机应变", "你抓住了情境里的细节，在最后关头作出了调整。"),
)

SCENARIOS = {
    "charms": (
        "羽毛只升到一半便开始左右乱晃。",
        "同桌的魔杖冒出火花，把你的练习目标吓跑了。",
        "教授要求让三件不同重量的物品同时悬浮。",
        "教室突然熄灯，你只能凭杖尖的微光继续练习。",
        "一只茶杯悬在吊灯旁，稍有不慎就会摔碎。",
        "咒语发音正确，魔杖动作却总慢半拍。",
        "练习用钥匙飞进了一群一模一样的钥匙中。",
        "你的咒语意外影响了隔壁桌的课本。",
        "教授临时要求你无声完成刚学的咒语。",
        "下课钟快响了，最后一次施法机会只剩十秒。",
    ),
    "defence": (
        "训练假人忽然改变方向，朝你的侧面袭来。",
        "护盾刚成形便出现了一道明显裂纹。",
        "你需要在不能使用攻击咒的情况下制服假人。",
        "教室里同时升起三个目标，只有一个是真的。",
        "对练同学连续用了两种不同类别的咒语。",
        "教授要求你保护身后的易碎魔法器具。",
        "一团模拟黑雾遮住了假人的施法动作。",
        "你的魔杖被训练咒震得几乎脱手。",
        "假人进入狂暴模式，攻击节奏突然加快。",
        "最后一轮对练中，你和对手都只剩一次机会。",
    ),
    "transfiguration": (
        "火柴已经长出针尖，却还保留着木头纹理。",
        "被变形的茶壶突然长出四条腿满桌乱跑。",
        "教授要求把一只甲虫变成带花纹的纽扣。",
        "目标物在变形到一半时卡在两种形态之间。",
        "你必须让变形结果维持到下课以后。",
        "一只受惊的小动物拒绝待在施法范围内。",
        "同桌误碰了你的目标，变形结构开始崩解。",
        "教授增加限制：不能改变目标原本的颜色。",
        "你需要把两件物品交换外形而不改变重量。",
        "最终展示前，作品的一角悄悄变回了原样。",
    ),
    "potions": (
        "坩埚里的药液比课本描述的颜色深了一度。",
        "最后一片材料掉在地上，备用材料只剩不同规格。",
        "火候忽高忽低，药液表面开始冒出银色气泡。",
        "同桌把顺时针和逆时针搅拌次数记反了。",
        "药水已经接近完成，却散发出不该有的甜味。",
        "一味材料必须在十秒内切碎并投入坩埚。",
        "教授要求判断三瓶外观相同药液中的成品。",
        "坩埚边缘出现结晶，正在缓慢向中心扩散。",
        "你的天平被人碰歪，材料剂量可能出现偏差。",
        "装瓶前药液突然从透明变成了淡紫色。",
    ),
    "herbology": (
        "一株幼苗缠住了你的手套，越挣扎勒得越紧。",
        "温室里的花突然集体转向门口并发出尖叫。",
        "需要移栽的根系比预计的脆弱得多。",
        "植物叶片出现了两种症状相反的斑点。",
        "浇水后土壤迅速干裂，像从没吸收过水分。",
        "一颗种子提前发芽，顶开了密封培养皿。",
        "同组的植物进入休眠，普通唤醒方法没有效果。",
        "温室温度突然下降，幼苗开始蜷缩。",
        "教授要求在不触碰叶片的情况下完成修剪。",
        "收获时植株释放出让人昏昏欲睡的花粉。",
    ),
    "flying": (
        "扫帚刚离地便持续向左偏转。",
        "高空突然刮起横风，把你推离了训练路线。",
        "你需要在三个移动圆环间连续急转。",
        "扫帚尾枝发出异响，速度也开始下降。",
        "训练球从视线死角高速飞来。",
        "教授要求贴地飞行后立刻垂直爬升。",
        "前方同学失去平衡，挡住了你的飞行路线。",
        "云层遮住标志物，你短暂失去了方向。",
        "降落区被临时缩小到原来的一半。",
        "计时训练只剩最后一圈，你暂时落后。",
    ),
    "divination": (
        "茶叶渣形成了两个含义完全相反的图案。",
        "水晶球里出现一扇门，却看不清门后的人影。",
        "同一个梦境符号在记录里反复出现。",
        "星盘显示的征兆与今天的天气完全不符。",
        "你抽到的三张牌似乎缺少一张关键连接牌。",
        "蜡烛火焰突然分成两股，分别指向不同方向。",
        "预言记录中的时间顺序似乎被颠倒了。",
        "你的观察结果和同桌完全一致，解释却相反。",
        "水晶球画面一闪而过，只留下一个颜色线索。",
        "教授要求你区分真正的征兆与自己的期待。",
    ),
    "care_of_magical_creatures": (
        "一只神奇动物拒绝进食，还不断藏起食盆。",
        "笼门意外弹开，小家伙钻进了草丛。",
        "动物突然竖起背毛，警惕地盯着你身后。",
        "两只本应温顺的幼兽为同一个玩具争执起来。",
        "检查鳞片时，你发现一处不自然的暗斑。",
        "喂食清单里混入了一种外观相似的错误饲料。",
        "动物听见远处雷声后躲到了箱子最深处。",
        "教授要求你在不惊动它的情况下测量体长。",
        "一只幼兽不停模仿你的动作，却不执行指令。",
        "下课前必须把所有动物安全引回栖息区。",
    ),
    "ancient_runes": (
        "石板上的最后一个符文被磨损，只剩下半段笔画。",
        "两段铭文单独都能读通，连在一起却互相矛盾。",
        "抄写到一半时，羊皮纸上的符文开始自行移动。",
        "教授要求区分三个外形近似、含义不同的古代字符。",
        "护符上的符文顺序似乎被人故意调换过。",
        "译文语法正确，却和石碑旁的图案完全对不上。",
        "一个罕见符号同时出现在两种不同年代的文献里。",
        "同桌给出另一种译法，而且同样能解释上下文。",
        "计时破译只剩一分钟，最后一行仍缺少关键词。",
        "念出译文后石板微微发光，显然触发了某种魔法。",
    ),
    "muggle_studies": (
        "桌上摆着一个麻瓜电器，但插头和说明书都不见了。",
        "课本把地铁描述成地下蒸汽火车，引起了同学争论。",
        "教授要求解释麻瓜为什么不用猫头鹰传递紧急消息。",
        "一张麻瓜地图没有任何会移动的标记。",
        "课堂展示的电话突然响起，却没人知道该怎么接听。",
        "你需要分辨五件物品中唯一没有魔法的那一件。",
        "小组作业要求设计一天完全不用魔法的生活计划。",
        "一位同学坚称麻瓜照片里的人只是故意站着不动。",
        "教授带来一叠纸币，要求说明它为何能够交换商品。",
        "期末演示前，麻瓜投影设备突然显示没有信号。",
    ),
}


def _render(uid: str, row, is_resume: bool) -> dict:
    subject = subjects.SUBJECTS_BY_KEY[row["subject_key"]][0]
    prompt = SCENARIOS[row["subject_key"]][row["scenario_index"]]
    return {
        "token": row["token"],
        "subject": subject,
        "prompt": prompt,
        "options": [choice[0] for choice in CHOICES],
        "is_resume": is_resume,
    }


def start(uid: str, subject_input: str) -> dict:
    existing = storage.get_lesson_session(uid)
    if existing:
        # 恢复时也重新检查体力和课程限制，但仍保留原情境。
        lessons.check_lesson_available(uid, existing["subject_key"])
        return _render(uid, existing, True)

    _, found = lessons.check_lesson_available(uid, subject_input)
    key = found[0]
    scenario_index = random.randrange(len(SCENARIOS[key]))
    token = secrets.token_hex(6)
    storage.save_lesson_session(uid, token, key, scenario_index)
    return _render(uid, storage.get_lesson_session(uid), False)


def resolve(uid: str, token: str, position: int) -> dict:
    row = storage.get_lesson_session(uid)
    if not row:
        raise LessonEventError("这节课已经结束了，请重新发送「/上课 学科名」。")
    if row["token"] != token:
        raise LessonEventError("这不是当前课堂的按钮，请发送「/上课」恢复最新课堂。")
    if not 0 <= position < len(CHOICES):
        raise LessonEventError("请选择课堂消息里的按钮。")

    # 先用带 token 的原子删除抢到本次结算权，防止双击并发结算两次。
    if not storage.delete_lesson_session(uid, token):
        raise LessonEventError("这节课已经结算过了，请重新发送「/上课 学科名」。")
    try:
        result = lessons.take_lesson(uid, row["subject_key"])
    except lessons.LessonError:
        # 例如点击时体力刚被其他玩法用掉；恢复原会话供之后继续。
        storage.save_lesson_session(
            uid, row["token"], row["subject_key"], row["scenario_index"]
        )
        raise
    # 每个情境轮换最佳策略；奖励只在当天仍有基础经验时发放，防止无限刷分。
    best = row["scenario_index"] % len(CHOICES)
    distance = (position - best) % len(CHOICES)
    bonus = (2, 0, 1)[distance] if result["gives_exp"] else 0
    if bonus:
        result["exp_gained"] += bonus
        result["total_exp"] = core_storage.add_subject_exp(uid, row["subject_key"], bonus)
    result["event_result"] = CHOICES[position][1]
    result["event_bonus"] = bonus
    return result

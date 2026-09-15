"""校园动态里掺的"闲逛花絮"：纯氛围，不产生任何实际游戏效果。

真实操作（上课、决斗、送礼……）已经全都走 notify.push() 记着了，但安静的时候
动态栏会很空，显得学校没人。这里按固定的时间窗口（20分钟一档）从已分院的学生里
挑几个人配一句"出现在哪里、在干嘛"，用时间窗口本身当随机种子——同一个窗口内
不管谁刷新页面看到的都是同一批花絮，像是"这会儿学校里正好这样"，而不是每次
刷新就换一批显得很假。窗口一过，换下一批人和台词。
"""

from __future__ import annotations

import random

from . import storage as core_storage

BUCKET_SECONDS = 20 * 60
COUNT = 5

LOCATIONS = (
    "大礼堂", "图书馆", "黑湖边", "魁地奇球场", "温室外",
    "地下教室走廊", "塔楼楼梯上", "对角巷", "禁林边缘", "厨房门口",
    "公共休息室", "钟楼下", "肖像画长廊", "占卜教室窗边", "魁地奇球场看台",
)

ACTIVITIES = (
    "对着一本厚得吓人的书发呆",
    "偷偷在练习一个新咒语的手势",
    "被一只猫头鹰追着跑",
    "蹲在地上研究一颗奇怪的石头",
    "跟人小声嘀咕着什么八卦",
    "在长椅上补了一觉",
    "对着镜子练习表情",
    "试图说服一只猫头鹰帮忙送信",
    "在走廊上摔了一跤又若无其事地站起来",
    "边走边啃一个南瓜馅饼",
    "对着窗外的天气发愁",
    "在偷偷记着什么笔记",
    "研究墙上一幅会动的画像",
    "把课本倒过来看了半天",
    "抱着一摞书找不到路",
    "跟自己的影子玩了一会儿",
    "在偷懒晒太阳",
    "对着一份作业唉声叹气",
)


def generate(now_ts: int, count: int = COUNT) -> list[dict]:
    """生成当前时间窗口内的花絮，附带落在窗口内的伪时间戳，方便跟真实动态混排。"""
    uids = core_storage.list_sorted_uids()
    if not uids:
        return []

    bucket = now_ts // BUCKET_SECONDS
    bucket_start = bucket * BUCKET_SECONDS
    rng = random.Random(f"hogwarts-ambient:{bucket}")

    n = min(count, len(uids))
    chosen = rng.sample(uids, n)
    out = []
    for uid in chosen:
        out.append(
            {
                "uid": uid,
                "location": rng.choice(LOCATIONS),
                "activity": rng.choice(ACTIVITIES),
                "created_at": bucket_start + rng.randint(0, BUCKET_SECONDS - 1),
            }
        )
    return out

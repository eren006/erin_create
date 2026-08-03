import hashlib
import random
import re
from datetime import date

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg

MAX_COUNT = 100
MAX_SIDES = 1000

_DICE_RE = re.compile(r"^(\d*)[dD](\d+)([+-]\d+)?$")
_BARE_NUM_RE = re.compile(r"^(\d+)$")


def parse_dice_expr(expr: str) -> tuple[int, int, int] | None:
    """解析骰子表达式，返回 (个数, 面数, 修正值)。格式不对返回 None。
    支持：空(默认1d100)、d20、3d6+2、100(裸数字视为面数)。
    """
    expr = expr.strip()
    if not expr:
        return 1, 100, 0
    m = _DICE_RE.match(expr)
    if m:
        count = int(m.group(1)) if m.group(1) else 1
        sides = int(m.group(2))
        modifier = int(m.group(3)) if m.group(3) else 0
        return count, sides, modifier
    m2 = _BARE_NUM_RE.match(expr)
    if m2:
        return 1, int(m2.group(1)), 0
    return None


def roll_dice(count: int, sides: int, modifier: int) -> tuple[list[int], int]:
    rolls = [random.randint(1, sides) for _ in range(count)]
    return rolls, sum(rolls) + modifier


rd_cmd = on_command("rd", aliases={"r", "投骰"})


@rd_cmd.handle()
async def handle_rd(event: MessageEvent, args=CommandArg()):
    expr = args.extract_plain_text().strip()
    parsed = parse_dice_expr(expr)
    if parsed is None:
        await rd_cmd.finish("格式不对。试试 /rd 、/rd d20 、/rd 3d6+2 、/rd 100 这类写法。")
        return
    count, sides, modifier = parsed
    if not (1 <= count <= MAX_COUNT) or not (1 <= sides <= MAX_SIDES):
        await rd_cmd.finish(f"骰子数量(1-{MAX_COUNT})或面数(1-{MAX_SIDES})超出范围。")
        return

    rolls, total = roll_dice(count, sides, modifier)
    mod_str = f"{modifier:+d}" if modifier else ""
    if count == 1 and not modifier:
        text = f"掷骰：D{sides} = {total}"
    else:
        detail = "+".join(str(r) for r in rolls)
        text = f"掷骰：{count}D{sides}{mod_str} = ({detail}){mod_str} = {total}"
    await rd_cmd.finish(text)


LEVEL_REMARKS: dict[str, list[str]] = {
    "大成功": [
        "运气罕见地站在你这边。",
        "记录在案——这不常发生。",
        "这次，你可以骄傲一秒。",
        "如果这是训练，我会怀疑你作弊。",
        "无可挑剔。别习惯这种待遇。",
    ],
    "极难成功": [
        "超出预期。做得不错。",
        "精确执行。这才是标准。",
        "这个结果，值得写进报告。",
        "干净利落。",
        "没有浪费的动作。",
    ],
    "困难成功": [
        "达标。继续。",
        "足够了。别指望次次都这样。",
        "算过关。",
        "不算完美，但可以用。",
        "过关了。下一项。",
    ],
    "成功": [
        "如预期。",
        "完成了。没什么好说的。",
        "过关，继续任务。",
        "达到最低要求。",
        "可以接受。",
    ],
    "失败": [
        "不理想。调整一下。",
        "没有达标。这在预料之中。",
        "失败了。至少诚实。",
        "下次会好一点，也许。",
        "记下来，别重蹈覆辙。",
    ],
    "大失败": [
        "不予置评。",
        "这不是我的问题。",
        "建议这件事别写进报告。",
        "灾难性的。但至少一致。",
        "我们假装这没发生过。",
    ],
}


def judge_success(roll: int, target: int) -> str:
    """COC7版规则：属性<50时1为大成功、96-100为大失败；属性>=50时1-5为大成功、100为大失败。"""
    is_crit = roll == 1 or (target >= 50 and roll <= 5)
    is_fumble = (target < 50 and roll >= 96) or (target >= 50 and roll == 100)
    if is_crit:
        return "大成功"
    if is_fumble:
        return "大失败"
    if roll <= target // 5:
        return "极难成功"
    if roll <= target // 2:
        return "困难成功"
    if roll <= target:
        return "成功"
    return "失败"


ra_cmd = on_command("ra", aliases={"检定"})


@ra_cmd.handle()
async def handle_ra(event: MessageEvent, args=CommandArg()):
    parts = args.extract_plain_text().strip().split()
    if not parts or not parts[-1].isdigit():
        await ra_cmd.finish("格式：/ra [属性名] 数值，如 /ra 侦查 70 或 /ra 70")
        return
    target = int(parts[-1])
    if not (1 <= target <= 999):
        await ra_cmd.finish("数值有误，核实一下。")
        return
    label = " ".join(parts[:-1])

    roll = random.randint(1, 100)
    level = judge_success(roll, target)
    prefix = f"{label} " if label else ""
    remark = random.choice(LEVEL_REMARKS[level])
    text = f"{prefix}检定：D100={roll}/{target} —— {level}。{remark}"
    await ra_cmd.finish(text)


# ======================== 每日运势 ========================

FORTUNE_TIERS: list[tuple[str, int, list[str]]] = [
    ("大吉", 5, [
        "任务成功率评估：极高。今日大概不会出错——除非你决意如此。",
        "运气罕见地站在你这边。别浪费它。",
    ]),
    ("吉", 20, [
        "情况乐观。按原计划行事即可。",
        "今日风险可控，正常推进。",
    ]),
    ("中吉", 20, [
        "平稳。没有惊喜，也没有灾难。",
        "一切在预期范围内。继续保持。",
    ]),
    ("小吉", 20, [
        "略有波动，保持基本的警惕即可。",
        "小幅有利。别期待太多。",
    ]),
    ("末吉", 15, [
        "边际情况。好坏参半，取决于你的判断。",
        "不算好，也不算坏。看你怎么用它。",
    ]),
    ("凶", 12, [
        "建议今日谨慎行事，少管闲事。",
        "情报显示今日存在变数。留意周围。",
    ]),
    ("大凶", 8, [
        "今天最好待在原地别动。我是认真的。",
        "一切都可能出错。把重要的事推到明天。",
    ]),
]

LUCKY_ACTIONS = [
    "独自行动", "检查装备", "复盘任务细节", "保持沉默", "提前做一次属性检定",
    "整理档案", "远离人群", "早点休息",
]
AVOID_ACTIONS = [
    "轻信未经核实的情报", "单独会见陌生人", "忽视直觉", "无必要的加班",
    "赌博", "临时改变计划", "多管闲事",
]


def _seeded_rng(uid: str, day: date) -> random.Random:
    seed_src = f"{uid}:{day.isoformat()}"
    seed = int(hashlib.sha256(seed_src.encode()).hexdigest(), 16)
    return random.Random(seed)


def get_daily_fortune(uid: str) -> dict:
    rng = _seeded_rng(uid, date.today())
    tiers = [t[0] for t in FORTUNE_TIERS]
    weights = [t[1] for t in FORTUNE_TIERS]
    tier = rng.choices(tiers, weights=weights, k=1)[0]
    comments = next(c for t, _, c in FORTUNE_TIERS if t == tier)
    return {
        "tier": tier,
        "comment": rng.choice(comments),
        "lucky_num": rng.randint(1, 99),
        "do": rng.choice(LUCKY_ACTIONS),
        "avoid": rng.choice(AVOID_ACTIONS),
    }


fortune_cmd = on_command("每日运势")


@fortune_cmd.handle()
async def handle_fortune(event: MessageEvent):
    f = get_daily_fortune(event.get_user_id())
    text = (
        f"今日评估：{f['tier']}\n"
        f"{f['comment']}\n\n"
        f"幸运数字：{f['lucky_num']}\n"
        f"建议：{f['do']}\n"
        f"避免：{f['avoid']}"
    )
    await fortune_cmd.finish(text)

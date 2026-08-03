"""称号定义。check(ctx) 返回是否满足解锁条件，ctx 由 engine.build_title_context 构造。"""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class TitleDef:
    key: str
    name: str
    desc: str
    check: Callable[[dict], bool]


TITLE_DEFS: list[TitleDef] = [
    TitleDef("rank_pin", "步步高升", "位分升至嫔位以上", lambda ctx: ctx["rank_index"] >= 3),
    TitleDef("rank_fei", "宠冠六宫", "位分升至贵妃以上", lambda ctx: ctx["rank_index"] >= 5),
    TitleDef("rank_top", "母仪天下", "位分升至皇后", lambda ctx: ctx["rank_index"] >= 7),
    TitleDef(
        "scheme_win_10", "长袖善舞", "成功使绊子达10次", lambda ctx: ctx["player"]["scheme_success_count"] >= 10
    ),
    TitleDef(
        "scheme_max", "机关算尽", "心机等级达到满级", lambda ctx: ctx["player"]["scheme_level"] >= ctx["max_scheme_level"]
    ),
    TitleDef(
        "cold_palace_5", "身陷囹圄", "累计被打入冷宫5次", lambda ctx: ctx["player"]["cold_palace_count"] >= 5
    ),
    TitleDef(
        "escape_5", "凤凰涅槃", "从冷宫脱身成功5次", lambda ctx: ctx["player"]["escape_success_count"] >= 5
    ),
    TitleDef(
        "bed_15", "圣眷正浓", "侍寝得宠达15次", lambda ctx: ctx["player"]["bed_success_count"] >= 15
    ),
    TitleDef("rich_5000", "富可敌国", "银两达到5000", lambda ctx: ctx["player"]["money"] >= 5000),
    TitleDef(
        "report_20", "八面玲珑", "成功告状达20次", lambda ctx: ctx["player"]["report_success_count"] >= 20
    ),
]

TITLES_BY_KEY: dict[str, TitleDef] = {t.key: t for t in TITLE_DEFS}

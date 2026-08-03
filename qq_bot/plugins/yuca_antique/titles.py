"""称号定义。check(ctx) 返回是否满足解锁条件，ctx 由 engine.build_title_context 构造。"""

from dataclasses import dataclass
from typing import Callable

from . import catalog


@dataclass(frozen=True)
class TitleDef:
    key: str
    name: str
    desc: str
    check: Callable[[dict], bool]


_CATEGORY_TITLE_NAMES = {
    "瓷器": "瓷魂",
    "青铜器": "吉金",
    "古玉器": "古玉大成",
    "文房": "文房大成",
    "钱币": "泉家",
    "字画": "翰墨大成",
    "玉石": "赌石大成",
    "宝石": "珠宝大成",
}


def _category_complete(cat: str):
    def check(ctx: dict) -> bool:
        discovered, total = ctx["category_progress"].get(cat, (0, 0))
        return total > 0 and discovered >= total

    return check


TITLE_DEFS: list[TitleDef] = [
    TitleDef("mine_50", "掘地三尺", "累计挖矿50次", lambda ctx: ctx["player"]["mine_count"] >= 50),
    TitleDef(
        "gem_fine",
        "淘金客",
        "挖到过精品及以上的宝石",
        lambda ctx: ctx["has_fine_gem"],
    ),
    TitleDef("has_diamond", "钻石见证者", "挖到过钻石", lambda ctx: "钻石" in ctx["codex_names"]),
    TitleDef("has_king_green", "帝王之色", "开出过帝王绿翡翠", lambda ctx: "帝王绿翡翠" in ctx["codex_names"]),
    TitleDef("has_legendary", "传世藏家", "拥有过传世品相的藏品", lambda ctx: ctx["has_传世"]),
    TitleDef(
        "identify_30",
        "三十连对",
        "累计鉴定正确30次",
        lambda ctx: ctx["player"]["identify_success_count"] >= 30,
    ),
    TitleDef(
        "misjudge_15",
        "打眼常客",
        "累计鉴定失误15次",
        lambda ctx: ctx["player"]["identify_fail_count"] >= 15,
    ),
    TitleDef(
        "eye_max",
        "掌眼宗师",
        "眼力等级达到满级",
        lambda ctx: ctx["player"]["eye_level"] >= ctx["max_eye_level"],
    ),
    TitleDef("rich_10k", "身家过万", "身家达到10000", lambda ctx: ctx["player"]["money"] >= 10000),
    TitleDef("rich_100k", "富甲一方", "身家达到100000", lambda ctx: ctx["player"]["money"] >= 100000),
]

for _cat, _name in _CATEGORY_TITLE_NAMES.items():
    TITLE_DEFS.append(
        TitleDef(f"codex_{_cat}", _name, f"集齐{_cat}类全部品类", _category_complete(_cat))
    )

TITLE_DEFS.append(
    TitleDef(
        "codex_all",
        "集大成者",
        "集齐全部品类图鉴",
        lambda ctx: all(d >= t and t > 0 for d, t in ctx["category_progress"].values())
        and len(ctx["category_progress"]) == len(catalog.ITEM_TYPES_BY_CATEGORY),
    )
)

TITLES_BY_KEY: dict[str, TitleDef] = {t.key: t for t in TITLE_DEFS}

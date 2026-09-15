"""巧克力蛙卡片：吃巧克力蛙时随机开出一张名人卡，收集凑套换称号。

复用对角巷已经在卖的"巧克力蛙"零食（snack_chocolate_frog）——吃的时候在
shop.eat_snack()里顺手判断一下是不是这个key，是的话额外走一次抽卡，
不用在商店目录里另开一件东西，也保留了"要花钱才能抽"这件事。
抽到已经收集过的卡不会白抽，换成一点安慰加隆。

称号这块照抄 potions.py 的 title_state/wear_title 写法——每个子系统自己
管自己的称号命名空间，unlock_title/has_title只是通用的解锁记录表。
"""

from __future__ import annotations

import random

from plugins.hp_core import storage as core_storage
from plugins.hp_core.storage import get_conn

FROG_ITEM_KEY = "snack_chocolate_frog"
DUPLICATE_GALLEONS = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS choc_frog_cards (
    uid TEXT NOT NULL,
    card_key TEXT NOT NULL,
    obtained_at INTEGER NOT NULL,
    PRIMARY KEY (uid, card_key)
);
"""

# (key, 名字, 稀有度权重, 稀有度标签, 简介)——权重仅在同稀有度内直观体现相对概率，
# 数值越大越常见；简介是原创描述，不摘录书中原文。
CARDS: list[tuple[str, str, int, str, str]] = [
    ("hengist", "亨吉斯特·伍德克罗夫特", 30, "普通", "霍格莫德村的建立者，据说是厌倦了麻瓜的迫害才搬到那儿定居。"),
    ("alberic", "阿尔伯里克·格伦涅恩", 30, "普通", "史上第一个因滥用魔咒被正式记录处罚的巫师，卡片上他看起来很不服气。"),
    ("paracelsus", "帕拉塞尔苏斯", 28, "普通", "炼金术与医药学的重要人物，卡片背面写满了看不懂的拉丁文药方。"),
    ("circe", "喀耳刻", 28, "普通", "传说中的女巫，据说擅长变形咒语，具体战绩众说纷纭。"),
    ("morgana", "摩根勒菲", 28, "普通", "亚瑟王传说里出了名的黑巫师，卡片上永远是一副高深莫测的表情。"),
    ("lockhart", "吉德罗·洛哈特", 25, "普通", "自封的多届最佳笑容奖得主，卡片会时不时对着镜头抛媚眼。"),
    ("newt", "纽特·斯卡曼德", 20, "少见", "知名magizoologist，卡片背景里总有什么东西在悄悄跑动。"),
    ("hufflepuff", "赫尔加·赫奇帕奇", 16, "少见", "霍格沃茨四位创始人之一，看重勤奋、忠诚与公平。"),
    ("ravenclaw", "罗伊纳·拉文克劳", 16, "少见", "霍格沃茨四位创始人之一，「才智过人」的校训就是她的手笔。"),
    ("gryffindor", "戈德里克·格兰芬多", 16, "少见", "霍格沃茨四位创始人之一，挑选学生时最看重勇气。"),
    ("slytherin", "萨拉查·斯莱特林", 16, "少见", "霍格沃茨四位创始人之一，卡片上的蛇纹装饰格外精致。"),
    ("flamel", "尼可勒·勒梅", 10, "稀有", "史上最著名的炼金术士，总被人跟他手里的那块石头一起提起。"),
    ("moody", "阿拉斯托·穆迪", 10, "稀有", "退休傲罗，卡片上那只假眼睛似乎真的会转来转去。"),
    ("mcgonagall", "密涅瓦·麦格", 10, "稀有", "以严格和公正著称的变形术教授，卡片上她的表情不苟言笑。"),
    ("granger", "赫敏·格兰杰", 8, "稀有", "以博学和正义感闻名，据说图书馆的书她几乎都翻遍了。"),
    ("dumbledore", "阿不思·邓布利多", 3, "传说", "当代最伟大的巫师之一，卡片会在你不注意的时候悄悄消失又出现。"),
    ("merlin", "梅林", 3, "传说", "巫师界公认的最伟大巫师，一级梅林勋章就是以他命名的。"),
    ("harry", "哈利·波特", 2, "传说", "在麻瓜家庭长大的巫师，这张卡非常抢手，几乎一上架就被抢空。"),
]

CARDS_BY_KEY = {c[0]: c for c in CARDS}
TOTAL_CARDS = len(CARDS)
RARITY_ORDER = ("普通", "少见", "稀有", "传说")

# (拥有卡片数达到, 称号key, 称号展示名)
COLLECTION_MILESTONES = (
    (5, "choc_frog_starter", "巧克力蛙新手收藏家"),
    (TOTAL_CARDS // 2, "choc_frog_collector", "巧克力蛙收藏家"),
    (TOTAL_CARDS, "choc_frog_master", "巧克力蛙集卡大师"),
)
TITLE_NAMES = {key: name for _threshold, key, name in COLLECTION_MILESTONES}
TITLE_REQUIREMENTS = {
    key: f"集齐{threshold}张巧克力蛙卡片" for threshold, key, name in COLLECTION_MILESTONES
}


class ChocFrogError(Exception):
    pass


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


init_db()


def _owned_keys(conn, uid: str) -> set[str]:
    return {
        row["card_key"]
        for row in conn.execute("SELECT card_key FROM choc_frog_cards WHERE uid=?", (uid,)).fetchall()
    }


def open_card(uid: str) -> dict:
    """吃一颗巧克力蛙顺带开出的卡片。抽到已有的卡不浪费，换成安慰加隆。
    蛀牙判定（吃零食超过阈值）已经挪到shop.eat_snack()里通吃所有零食，这里不再管。"""
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        owned = _owned_keys(conn, uid)
        keys = [c[0] for c in CARDS]
        weights = [c[2] for c in CARDS]
        card_key = random.choices(keys, weights=weights, k=1)[0]
        card = CARDS_BY_KEY[card_key]
        is_new = card_key not in owned

        consolation = 0
        if is_new:
            conn.execute(
                "INSERT INTO choc_frog_cards (uid, card_key, obtained_at) VALUES (?, ?, ?)",
                (uid, card_key, core_storage.now()),
            )
        else:
            consolation = DUPLICATE_GALLEONS
            conn.execute(
                "UPDATE players SET galleons = galleons + ?, updated_at = ? WHERE uid = ?",
                (consolation, core_storage.now(), uid),
            )
        conn.commit()

        newly_unlocked = []
        if is_new:
            total_owned = len(owned) + 1
            for threshold, title_key, title_name in COLLECTION_MILESTONES:
                if total_owned >= threshold and not core_storage.has_title(uid, title_key):
                    core_storage.unlock_title(uid, title_key)
                    newly_unlocked.append(title_name)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "card_key": card_key,
        "name": card[1],
        "rarity": card[3],
        "blurb": card[4],
        "is_new": is_new,
        "consolation": consolation,
        "unlocked_titles": newly_unlocked,
    }


def my_collection(uid: str) -> dict:
    conn = get_conn()
    try:
        owned = _owned_keys(conn, uid)
    finally:
        conn.close()
    by_rarity: dict[str, list[dict]] = {r: [] for r in RARITY_ORDER}
    for key, name, _weight, rarity, blurb in CARDS:
        has_it = key in owned
        by_rarity[rarity].append({
            "name": name if has_it else "？？？",
            "owned": has_it,
            "blurb": blurb if has_it else "",
        })
    return {"owned_count": len(owned), "total": TOTAL_CARDS, "by_rarity": by_rarity}


def title_state(uid: str) -> list[dict]:
    conn = get_conn()
    try:
        unlocked = {
            row["title_key"] for row in conn.execute(
                "SELECT title_key FROM titles WHERE uid=?", (uid,)
            ).fetchall()
        }
        player = conn.execute("SELECT active_title FROM players WHERE uid=?", (uid,)).fetchone()
        active = player["active_title"] if player else ""
        return [
            {"key": key, "name": name, "requirement": TITLE_REQUIREMENTS[key],
             "unlocked": key in unlocked, "active": active == name}
            for key, name in TITLE_NAMES.items()
        ]
    finally:
        conn.close()


def wear_title(uid: str, title_input: str) -> str:
    key = next((key for key, name in TITLE_NAMES.items() if title_input in (key, name)), None)
    if not key:
        raise ChocFrogError("没有这个巧克力蛙称号。发送「/巧克力蛙称号」查看。")
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("SELECT 1 FROM titles WHERE uid=? AND title_key=?", (uid, key)).fetchone():
            conn.rollback()
            raise ChocFrogError(f"你还没有解锁「{TITLE_NAMES[key]}」。")
        conn.execute(
            "UPDATE players SET active_title=?,updated_at=? WHERE uid=?",
            (TITLE_NAMES[key], core_storage.now(), uid),
        )
        conn.commit()
        return TITLE_NAMES[key]
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

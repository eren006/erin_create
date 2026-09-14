"""友情系统：跟恋爱平行的另一条社交线——日常处朋友、送礼物涨友谊值，不参与表白/情侣判定。

友谊值也是单向的，跟恋爱好感度一个道理：A对B和B对A是两条独立记录。
处朋友（hang_out）比较特殊，是双向一起涨——一起出去玩这件事本来就是双方共同经历的，
不像"调情"是单方面示好，所以不用像flirt那样只涨对方对你的好感。
"""

from __future__ import annotations

import random

from plugins.hp_core import storage as core_storage
from plugins.hp_core.storage import get_conn
from plugins.hp_school import shop_catalog
from plugins.hp_school import storage as school_storage

SCHEMA = """
CREATE TABLE IF NOT EXISTS friend_points (
    from_uid TEXT NOT NULL,
    to_uid TEXT NOT NULL,
    value INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (from_uid, to_uid)
);

CREATE TABLE IF NOT EXISTS friend_log (
    from_uid TEXT NOT NULL,
    to_uid TEXT NOT NULL,
    day INTEGER NOT NULL,
    PRIMARY KEY (from_uid, to_uid, day)
);

CREATE TABLE IF NOT EXISTS friend_study_bonus_log (
    uid_a TEXT NOT NULL,
    uid_b TEXT NOT NULL,
    subject TEXT NOT NULL,
    day INTEGER NOT NULL,
    PRIMARY KEY (uid_a, uid_b, subject, day)
);
"""

FRIEND_MAX = 100
HANGOUT_STAMINA_COST = 2
GOOD_FRIEND_THRESHOLD = 30  # 双向友谊值都到这个数才算"好朋友"，享受一起上课多给经验之类的专属福利

# 每种互动一段flavor text + 各自的友谊值涨幅区间，随机挑一种，增加变化感。
HANGOUT_VARIATIONS = (
    ("一起吐槽了今天的作业，笑得直不起腰。", 3, 5),
    ("在图书馆占了同一张桌子，各写各的但很安心。", 2, 4),
    ("分享了从家里带来的零食，边吃边聊八卦。", 3, 5),
    ("陪对方去对角巷逛了一圈，什么都没买光是闲逛。", 2, 4),
    ("一起研究了一道谁都没做出来的课业难题，最后还是没解出来。", 3, 6),
    ("在草坪上晒太阳，有一搭没一搭地聊天。", 2, 3),
    ("互相吐槽了几句对家的教授，同仇敌忾了一番。", 3, 5),
    ("陪对方去了趟猫头鹰棚，路上没话找话地聊了一路。", 2, 4),
)


class FriendshipError(Exception):
    pass


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


init_db()


def _require_player(uid: str, who: str = "你"):
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise FriendshipError(f"{who}还没有分院，先发「/入学」完成入学测试。")
    return player


def _add_friend_points(from_uid: str, to_uid: str, amount: int) -> int:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO friend_points (from_uid, to_uid, value, updated_at) "
            "VALUES (?, ?, MAX(0, MIN(?, ?)), ?) "
            "ON CONFLICT(from_uid, to_uid) DO UPDATE SET "
            "value = MAX(0, MIN(?, friend_points.value + ?)), updated_at = excluded.updated_at",
            (from_uid, to_uid, FRIEND_MAX, amount, core_storage.now(), FRIEND_MAX, amount),
        )
        conn.commit()
        row = conn.execute(
            "SELECT value FROM friend_points WHERE from_uid = ? AND to_uid = ?", (from_uid, to_uid)
        ).fetchone()
        return row["value"]
    finally:
        conn.close()


def get_friend_points(from_uid: str, to_uid: str) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM friend_points WHERE from_uid = ? AND to_uid = ?", (from_uid, to_uid)
        ).fetchone()
        return row["value"] if row else 0
    finally:
        conn.close()


def hang_out(uid: str, target_uid: str) -> dict:
    """处朋友：对同一个人每天一次，随机一种互动，双方友谊值一起涨。"""
    _require_player(uid)
    if target_uid == uid:
        raise FriendshipError("不能自己陪自己玩。")
    _require_player(target_uid, "对方")

    player = core_storage.sync_stamina(uid)
    if player["stamina"] < HANGOUT_STAMINA_COST:
        wait_min = core_storage.seconds_to_next_stamina(player) // 60 + 1
        raise FriendshipError(
            f"你现在没什么精神找朋友玩。当前体力{player['stamina']}/{core_storage.STAMINA_MAX}，"
            f"处朋友需要{HANGOUT_STAMINA_COST}点；约{wait_min}分钟后会恢复一轮。"
        )

    day = core_storage.get_current_day() or 1
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO friend_log (from_uid, to_uid, day) VALUES (?, ?, ?)",
            (uid, target_uid, day),
        )
        if cur.rowcount == 0:
            conn.rollback()
            raise FriendshipError("今天已经和TA处过朋友了，明天再来。")
        conn.commit()
    finally:
        conn.close()

    core_storage.spend_stamina(uid, HANGOUT_STAMINA_COST)
    line, low, high = random.choice(HANGOUT_VARIATIONS)
    gain = random.randint(low, high)
    my_new_value = _add_friend_points(uid, target_uid, gain)
    their_new_value = _add_friend_points(target_uid, uid, gain)
    return {
        "target": target_uid,
        "line": line,
        "gain": gain,
        "my_new_value": my_new_value,
        "their_new_value": their_new_value,
    }


def send_gift(uid: str, item_input: str, target_uid: str) -> dict:
    """送礼给朋友：涨的是友谊值，不是恋爱好感度，跟romance.send_gift互不影响。"""
    _require_player(uid)
    if target_uid == uid:
        raise FriendshipError("不能送给自己。")
    _require_player(target_uid, "对方")

    item = shop_catalog.find(item_input.strip())
    if not item or item[2] != "礼物":
        raise FriendshipError("这不是礼物，去「/对角巷 礼物」看看有什么可以送的。")
    key, name, _, _, _, effect = item

    if not school_storage.remove_item(uid, key, 1):
        raise FriendshipError(f"背包里没有「{name}」，先去「/对角巷购买 {name}」。")

    gain = effect["affection"]
    new_value = _add_friend_points(target_uid, uid, gain)
    return {"name": name, "gain": gain, "new_value": new_value, "target": target_uid}


def my_friends(uid: str) -> dict:
    conn = get_conn()
    try:
        mine = conn.execute(
            "SELECT to_uid, value FROM friend_points WHERE from_uid = ? AND value > 0 ORDER BY value DESC",
            (uid,),
        ).fetchall()
        theirs = conn.execute(
            "SELECT from_uid, value FROM friend_points WHERE to_uid = ? AND value > 0 ORDER BY value DESC",
            (uid,),
        ).fetchall()
    finally:
        conn.close()
    return {
        "my_friends": [(r["to_uid"], r["value"]) for r in mine],
        "friends_of_me": [(r["from_uid"], r["value"]) for r in theirs],
    }


def good_friends_of(uid: str) -> list[str]:
    """双向友谊值都达标才算好朋友——单向倒贴的泛泛之交不享受"一起上课"这类专属福利。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT a.to_uid AS uid FROM friend_points a "
            "JOIN friend_points b ON b.from_uid = a.to_uid AND b.to_uid = a.from_uid "
            "WHERE a.from_uid = ? AND a.value >= ? AND b.value >= ?",
            (uid, GOOD_FRIEND_THRESHOLD, GOOD_FRIEND_THRESHOLD),
        ).fetchall()
        return [r["uid"] for r in rows]
    finally:
        conn.close()


def claim_study_bonus_once(uid_a: str, uid_b: str, subject_key: str, day: int) -> bool:
    """好友结伴学习奖励每对好友+这门课+当天只发一次，靠这张表去重。
    返回True表示这次调用抢到了发放权（调用方应该去加经验），False表示今天已经发过了。"""
    a, b = (uid_a, uid_b) if uid_a < uid_b else (uid_b, uid_a)
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO friend_study_bonus_log (uid_a, uid_b, subject, day) VALUES (?, ?, ?, ?)",
            (a, b, subject_key, day),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()

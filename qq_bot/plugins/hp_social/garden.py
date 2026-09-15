"""种花：出门捡种子，种下去要等3小时，十有八九会枯死，活下来才变成一盆特别的盆栽。

跟宠物/厨房那些"稳赚不赔"的养成不一样，这里故意把成功率压得很低（10%），
博的就是"等了三小时结果一开盆是空的"这种心态——赌的成分比种的成分重。
盆栽长期摆在"你的花园"里，如果有室友，两个人的盆栽会合并展示，呼应
"你们的宿舍"这个说法，跟 dorm.py 的两人一间保持一致。

一个人同一时间只能种一颗种子（花盆只有一个），跟 potions.py 的"一次只能有一个
进行中的场次"是同一个思路，免得状态管理复杂化。
"""

from __future__ import annotations

import random

from plugins.hp_core import storage as core_storage
from plugins.hp_core.storage import get_conn

SCHEMA = """
CREATE TABLE IF NOT EXISTS garden_plots (
    uid TEXT PRIMARY KEY,
    seeds INTEGER NOT NULL DEFAULT 0,
    planted_at INTEGER NOT NULL DEFAULT 0,
    ready_at INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS garden_daily (
    uid TEXT NOT NULL,
    day INTEGER NOT NULL,
    forages INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, day)
);

CREATE TABLE IF NOT EXISTS garden_pots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    plant_name TEXT NOT NULL,
    obtained_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_garden_pots_uid ON garden_pots(uid);
"""

FORAGE_STAMINA_COST = 6
FORAGE_DAILY_LIMIT = 3
PLANT_STAMINA_COST = 8
GROW_SECONDS = 3 * 60 * 60  # 3小时
SURVIVE_CHANCE = 0.10

SEED_FOUND_LINES = (
    "你在草坪边缘的泥土里翻出一颗圆滚滚的种子。",
    "温室墙角的裂缝里卡着一颗种子，你小心地抠了出来。",
    "黑湖边的芦苇丛里，你摸到一颗表面带着细小纹路的种子。",
    "魁地奇球场看台下的草皮里，藏着一颗种子。",
    "路过霍格沃茨的果园时，树下正好掉落着一颗种子。",
    "禁林边缘一株不知名的杂草上，结着一颗种子，你顺手摘了下来。",
    "占卜教室窗台的花盆缝隙里，卡着一颗谁也说不清来路的种子。",
    "海格的南瓜地边上，你踩到了一颗被鸟叼掉又落下的种子。",
    "图书馆后门的排水沟盖子下面，意外滚出一颗种子。",
    "翻旧课本的时候，一颗种子从书页夹层里掉了出来。",
    "食草小径旁的石缝里探出半颗种子，你费了点劲才抠出来。",
)

HARVEST_FAIL_LINES = (
    "土壤里的嫩芽刚冒头就蔫了，这次培育没能撑过去。",
    "浇了三小时的水，等来的却是一株枯萎的幼苗，花盆里空空如也。",
    "种子倒是发了芽，但没撑到你来看它就枯死在盆里了。",
    "花盆里只剩下一截干枯发脆的茎，什么都没留下。",
    "打开一看，花盆里的土干裂成了一小块一小块，什么都没长出来。",
    "嫩芽长到一半突然发黑腐烂，整盆报废了。",
    "似乎是被什么虫子啃了个精光，只剩几片碎叶子。",
    "种子吸饱了水却始终没发芽，最后烂在了土里。",
)

POTTED_PLANTS = (
    "会打喷嚏的迷你曼德拉草",
    "永远朝着阳光转动的向日藤",
    "开着糖果色小花、会自己哼小曲的仙人掌",
    "叶片会随心情变色的心情草",
    "结着一串串小铃铛果实的铃兰树",
    "会小声打呼噜的绒毛苔藓球",
    "花瓣像羊皮纸一样会记事的记忆花",
    "半夜会发出微光的月光兰",
    "喜欢和路过的人击掌的握手藤",
    "香气很浓但永远长不大的迷你月桂",
    "叶片边缘会结出细小霜花的寒露草",
    "开花时会发出细碎铃声的风铃藤",
    "叶子摸起来像天鹅绒、越摸越大片的绒面草",
    "花苞永远含苞待放、从不真正开花的期待花",
    "会跟着说话声音轻轻摇晃的应声草",
    "结出一颗颗迷你南瓜的袖珍南瓜藤",
    "叶片翻过来是银色的双面银叶草",
    "花朵会在正午突然全部转向你的向心花",
    "香气随天气变化的晴雨草",
    "藤蔓会缓慢缠上花盆边缘、样子有点粘人的缠绵藤",
    "开出的花瓣一碰就碎成金粉的碎金花",
    "叶片上天然长着心形斑纹的连理草",
    "夜里会悄悄合拢叶片「入睡」的瞌睡草",
    "结着透明浆果、里面隐约能看见小气泡的水晶莓",
    "花色会一天三变、从不重样的善变兰",
)


class GardenError(Exception):
    pass


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


init_db()


def _require_enrolled(uid: str) -> None:
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise GardenError("你还没有分院，先发「/入学」完成入学测试。")


def _get_or_create_state(uid: str):
    conn = get_conn()
    try:
        conn.execute("INSERT OR IGNORE INTO garden_plots (uid) VALUES (?)", (uid,))
        conn.commit()
        return conn.execute("SELECT * FROM garden_plots WHERE uid = ?", (uid,)).fetchone()
    finally:
        conn.close()


def _get_daily(uid: str, day: int) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT forages FROM garden_daily WHERE uid = ? AND day = ?", (uid, day)
        ).fetchone()
        return row["forages"] if row else 0
    finally:
        conn.close()


def _increment_daily(uid: str, day: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO garden_daily (uid, day, forages) VALUES (?, ?, 1) "
            "ON CONFLICT(uid, day) DO UPDATE SET forages = forages + 1",
            (uid, day),
        )
        conn.commit()
    finally:
        conn.close()


# ======================== 出门 / 种下 ========================


def forage(uid: str) -> dict:
    _require_enrolled(uid)
    day = core_storage.get_current_day() or 1
    used = _get_daily(uid, day)
    if used >= FORAGE_DAILY_LIMIT:
        raise GardenError(f"今天已经出门找过{FORAGE_DAILY_LIMIT}次种子了，明天再去看看。")

    player = core_storage.sync_stamina(uid)
    if player["stamina"] < FORAGE_STAMINA_COST:
        wait_min = core_storage.seconds_to_next_stamina(player) // 60 + 1
        raise GardenError(
            f"体力不够出门了（{player['stamina']}/{core_storage.STAMINA_MAX}），"
            f"找种子要{FORAGE_STAMINA_COST}点。约{wait_min}分钟后恢复一轮。"
        )

    core_storage.spend_stamina(uid, FORAGE_STAMINA_COST)
    _increment_daily(uid, day)
    _get_or_create_state(uid)

    conn = get_conn()
    try:
        conn.execute("UPDATE garden_plots SET seeds = seeds + 1 WHERE uid = ?", (uid,))
        conn.commit()
        seeds = conn.execute("SELECT seeds FROM garden_plots WHERE uid = ?", (uid,)).fetchone()["seeds"]
    finally:
        conn.close()

    return {
        "line": random.choice(SEED_FOUND_LINES),
        "seeds": seeds,
        "used_today": used + 1,
        "daily_limit": FORAGE_DAILY_LIMIT,
    }


def plant(uid: str) -> dict:
    _require_enrolled(uid)
    state = _get_or_create_state(uid)
    if state["ready_at"] > 0:
        raise GardenError("花盆里已经种着东西了，等它长好再种下一颗。用「/花盆状态」看看还要多久。")
    if state["seeds"] < 1:
        raise GardenError("你手上没有种子，先「/捡种子」出门找一颗。")

    player = core_storage.sync_stamina(uid)
    if player["stamina"] < PLANT_STAMINA_COST:
        wait_min = core_storage.seconds_to_next_stamina(player) // 60 + 1
        raise GardenError(
            f"体力不够种花了（{player['stamina']}/{core_storage.STAMINA_MAX}），"
            f"培育要{PLANT_STAMINA_COST}点。约{wait_min}分钟后恢复一轮。"
        )

    core_storage.spend_stamina(uid, PLANT_STAMINA_COST)
    now = core_storage.now()
    ready_at = now + GROW_SECONDS
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE garden_plots SET seeds = seeds - 1, planted_at = ?, ready_at = ? WHERE uid = ?",
            (now, ready_at, uid),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ready_at": ready_at, "grow_hours": GROW_SECONDS // 3600}


# ======================== 状态 / 收获 ========================


def status(uid: str) -> dict:
    state = _get_or_create_state(uid)
    if state["ready_at"] == 0:
        return {"growing": False, "seeds": state["seeds"]}
    remaining = state["ready_at"] - core_storage.now()
    return {
        "growing": True,
        "ready": remaining <= 0,
        "remaining_seconds": max(0, remaining),
        "seeds": state["seeds"],
    }


def harvest(uid: str) -> dict:
    state = _get_or_create_state(uid)
    if state["ready_at"] == 0:
        raise GardenError("花盆里现在什么都没种，先「/种花」种一颗种子。")
    remaining = state["ready_at"] - core_storage.now()
    if remaining > 0:
        wait_min = remaining // 60 + 1
        raise GardenError(f"还没长好，大约还要{wait_min}分钟，心急吃不了热豆腐。")

    conn = get_conn()
    try:
        conn.execute("UPDATE garden_plots SET planted_at = 0, ready_at = 0 WHERE uid = ?", (uid,))
        conn.commit()
    finally:
        conn.close()

    if random.random() >= SURVIVE_CHANCE:
        return {"success": False, "line": random.choice(HARVEST_FAIL_LINES)}

    plant_name = random.choice(POTTED_PLANTS)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO garden_pots (uid, plant_name, obtained_at) VALUES (?, ?, ?)",
            (uid, plant_name, core_storage.now()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "plant_name": plant_name}


# ======================== 展示 ========================


def list_pots(uid: str) -> list[dict]:
    """自己的盆栽，如果有室友，两人的合并展示——"你们的宿舍"。"""
    from . import dorm

    uids = [uid]
    my_dorm = dorm.get_my_dorm(uid)
    if my_dorm:
        uids.append(my_dorm["roommate"])

    conn = get_conn()
    try:
        placeholders = ",".join("?" for _ in uids)
        rows = conn.execute(
            f"SELECT * FROM garden_pots WHERE uid IN ({placeholders}) ORDER BY obtained_at DESC",
            uids,
        ).fetchall()
    finally:
        conn.close()
    return [
        {"plant_name": r["plant_name"], "owner": core_storage.get_full_name(r["uid"]), "obtained_at": r["obtained_at"]}
        for r in rows
    ]

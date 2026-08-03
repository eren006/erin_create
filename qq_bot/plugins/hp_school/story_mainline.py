"""全服共享的一年级分支主线：《第十三声钟响》。"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass

from plugins.hp_core.storage import get_conn


STORY_ID = "year1_thirteenth_bell"
STORY_TITLE = "第十三声钟响"
CHOICE_REWARD = 10
PHASE_DURATION_SECONDS = 3 * 86400


class StoryError(Exception):
    pass


@dataclass(frozen=True)
class Option:
    key: str
    text: str
    effects: dict[str, int]
    tags: dict[str, int]


@dataclass(frozen=True)
class Phase:
    number: int
    title: str
    prompt: str
    options: tuple[Option, ...]


def _o(key: str, text: str, effects=None, tags=None) -> Option:
    return Option(key, text, effects or {}, tags or {})


PHASES = (
    Phase(1, "午夜之后", "午夜钟本应响十二次，你却听见了第十三声。走廊尽头出现一串湿脚印。", (
        _o("A", "叫醒级长", {"professor_trust": 1}, {"professor_eye": 2}),
        _o("B", "跟随脚印", {"evidence": 1}, {"explorer": 2}),
        _o("C", "记下时间，等待下一次", {"evidence": 1}, {"arbiter": 2, "witness": 1}),
    )),
    Phase(2, "被抹去的画像", "墙上只剩一幅空白画布，其他学生却坚持那里从来没有画像。", (
        _o("A", "询问附近的画像", {"professor_trust": 1}, {"professor_eye": 1}),
        _o("B", "拆下画框检查背面", {"evidence": 1}, {"explorer": 2}),
        _o("C", "把画像临摹下来", {"public_truth": 1}, {"witness": 2}),
    )),
    Phase(3, "楼梯尽头的门", "第十三声再次响起，一道平时不存在的门出现在移动楼梯尽头。", (
        _o("A", "立刻进去", {"echo_power": 1}, {"explorer": 2, "bell_ringer": 1}),
        _o("B", "留下标记，返回找人", {"professor_trust": 1}, {"professor_eye": 1}),
        _o("C", "先用魔法测试门", {"evidence": 1}, {"arbiter": 2}),
    )),
    Phase(4, "没有名字的课桌", "无名回廊里，一张旧课桌中央的姓名被反复刮去。倒影中的少年问：你还记得我吗？", (
        _o("A", "问他是谁", {"echo_power": 1}, {"echo_friend": 2}),
        _o("B", "恢复被刮去的刻痕", {"evidence": 1}, {"explorer": 2}),
        _o("C", "不回答，先检查周围", {"evidence": 1}, {"arbiter": 2}),
    )),
    Phase(5, "第一份共同证词", "零散的发现终于拼在一起。全校必须决定先把哪条路走到底。", (
        _o("A", "把事情报告教授", {"professor_trust": 2, "seal_integrity": 1}, {"professor_eye": 2}),
        _o("B", "接受埃利奥特的请求", {"echo_power": 2, "evidence": 1}, {"echo_friend": 2}),
        _o("C", "成立学生调查小组", {"public_truth": 2, "evidence": 1}, {"witness": 2}),
    )),
    Phase(6, "倒影中的请求", "倒影中的少年自称埃利奥特，请你找回他的完整姓名，并承诺归还所有记忆。", (
        _o("A", "答应帮助", {"echo_power": 2}, {"echo_friend": 2}),
        _o("B", "要求他先证明身份", {"evidence": 1}, {"arbiter": 2}),
        _o("C", "拒绝并通知教授", {"professor_trust": 1, "seal_integrity": 1}, {"professor_eye": 2}),
    )),
    Phase(7, "四院各执一词", "四大学院保存的旧记录互相矛盾，没有任何一份能单独解释当年的事故。", (
        _o("A", "与其他学院交换记录", {"public_truth": 1}, {"witness": 2}),
        _o("B", "独自比对全部记录", {"evidence": 1}, {"explorer": 2}),
        _o("C", "把记录交给教授", {"professor_trust": 1}, {"professor_eye": 2}),
    )),
    Phase(8, "被遗忘的一天", "你失去了整整一天的记忆，口袋里却有自己写的纸条：不要让他敲第二次钟。", (
        _o("A", "相信纸条", {"seal_integrity": 1}, {"keeper": 2}),
        _o("B", "相信埃利奥特的解释", {"echo_power": 2}, {"echo_friend": 2}),
        _o("C", "重走昨天的路线", {"evidence": 2}, {"explorer": 2}),
    )),
    Phase(9, "教授的禁令", "档案管理员封闭了回廊，却拒绝说明学校为何删去一名学生。", (
        _o("A", "遵守禁令并私下交涉", {"professor_trust": 2}, {"professor_eye": 2}),
        _o("B", "夜间潜入档案室", {"evidence": 2, "professor_trust": -1}, {"explorer": 2}),
        _o("C", "公开要求学校说明", {"public_truth": 2, "professor_trust": -1}, {"witness": 2}),
    )),
    Phase(10, "死去又长大的学生", "档案显示：埃利奥特入学宴当晚已经死亡，记录里却还有一个他继续生活了七年。", (
        _o("A", "追查死亡记录", {"evidence": 2}, {"arbiter": 2}),
        _o("B", "追查后七年的记录", {"echo_power": 1, "evidence": 1}, {"explorer": 2}),
        _o("C", "询问城堡里的幽灵", {"public_truth": 1, "professor_trust": 1}, {"witness": 1}),
    )),
    Phase(11, "七年的借名者", "真正的埃利奥特早已死去。眼前的少年，是城堡从朋友们的思念中生出的记忆回声。", (
        _o("A", "承认回声也是生命", {"echo_power": 1, "public_truth": 1}, {"echo_friend": 2}),
        _o("B", "认定它只是魔法残留", {"seal_integrity": 1}, {"keeper": 2}),
        _o("C", "暂不判断，继续取证", {"evidence": 2}, {"arbiter": 2}),
    )),
    Phase(12, "借来的记忆", "回声承认自己偷取学生记忆来填补人格，却说最后一定会归还。", (
        _o("A", "要求它立即归还", {"echo_power": -1}, {"arbiter": 2}),
        _o("B", "允许它暂时保留", {"echo_power": 2}, {"echo_friend": 2}),
        _o("C", "用自愿分享的记忆代替", {"public_truth": 1, "voluntary_memory": 1}, {"echo_friend": 1, "witness": 1}),
    )),
    Phase(13, "忘记名字的人", "新生米蕾忘记了姓名、学院和朋友。回声以归还记忆为条件，索要一个正式名字。", (
        _o("A", "接受交易", {"echo_power": 2}, {"echo_friend": 2}),
        _o("B", "拒绝交易并保护米蕾", {"seal_integrity": 1, "professor_trust": 1}, {"keeper": 2}),
        _o("C", "假意接受并设置陷阱", {"evidence": 1}, {"arbiter": 2}),
    )),
    Phase(14, "四件封印物", "钟锤、齿轮、铭牌和摆锤分属四院。回声正逐一寻找它们。", (
        _o("A", "集中防守钟塔", {"seal_integrity": 1}, {"keeper": 2}),
        _o("B", "用假封印物诱敌", {"evidence": 1}, {"arbiter": 2}),
        _o("C", "开启缝隙与回声谈判", {"echo_power": 1, "heard_echo": 1}, {"echo_friend": 2}),
    )),
    Phase(15, "钟塔失守", "回声用你最害怕失去的记忆制造幻象，诱导所有人亲手敲响旧钟。", (
        _o("A", "呼唤同伴确认彼此记忆", {"public_truth": 2}, {"witness": 2}),
        _o("B", "依靠教授的锚定咒", {"professor_trust": 2, "seal_integrity": 1}, {"professor_eye": 2}),
        _o("C", "独自进入钟内寻找核心", {"evidence": 2, "echo_power": 1}, {"explorer": 2}),
    )),
    Phase(16, "学校隐瞒的理由", "学校删除记录是为阻止回声获得完整身份，但也借安全之名掩盖了自己的失职。", (
        _o("A", "接受解释，优先解决危机", {"professor_trust": 2}, {"professor_eye": 2}),
        _o("B", "要求危机后公开档案", {"public_truth": 2}, {"witness": 2}),
        _o("C", "不再相信学校", {"public_truth": 1, "professor_trust": -2}, {"secret_keeper": 2}),
    )),
    Phase(17, "真正的最后愿望", "真正的埃利奥特留下话语：别让任何东西替我活；但如果它已经会害怕，也别因我杀死它。", (
        _o("A", "记住真正的埃利奥特", {"evidence": 1, "public_truth": 1}, {"witness": 2}),
        _o("B", "把选择权交给回声", {"echo_power": 2}, {"echo_friend": 2}),
        _o("C", "让所有受害者共同决定", {"public_truth": 2}, {"arbiter": 2}),
    )),
    Phase(18, "全校审判", "证据已经摆在所有人面前。全校必须决定如何处置记忆回声。", (
        _o("A", "摧毁回声", {"ending_destroy": 3}, {"arbiter": 1}),
        _o("B", "重新封印", {"ending_seal": 3}, {"keeper": 2}),
        _o("C", "给它一个新名字", {"ending_rebirth": 3}, {"echo_friend": 2}),
    )),
    Phase(19, "必须支付的代价", "无论选择哪条路，都有人必须承担代价。这一次，没有毫无损失的答案。", (
        _o("A", "放弃关于回廊的一段记忆", {"ending_destroy": 1}, {"witness": 1}),
        _o("B", "自愿承担守钟职责", {"ending_seal": 1}, {"keeper": 2}),
        _o("C", "公开旧案并赋予新名", {"ending_rebirth": 1, "public_truth": 1}, {"echo_friend": 1, "witness": 1}),
    )),
    Phase(20, "第十三声之后", "午夜再次来临。钟声会停在十二下，传来沉闷的第十三声，还是响起全新的音色？", (
        _o("A", "守住仍被记得的一切", {"ending_destroy": 1}, {"witness": 2}),
        _o("B", "守住门后的秘密", {"ending_seal": 1}, {"keeper": 2}),
        _o("C", "让新的名字被所有人听见", {"ending_rebirth": 1}, {"echo_friend": 2}),
    )),
)
PHASE_BY_NUMBER = {phase.number: phase for phase in PHASES}

TAG_NAMES = {
    "professor_eye": "教授的眼睛", "explorer": "回廊探索者", "secret_keeper": "秘密保管人",
    "witness": "记忆见证者", "echo_friend": "回声之友", "arbiter": "冷静裁决者",
    "bell_ringer": "敲钟者", "keeper": "守钟人候选",
}
ENDING_NAMES = {"destroy": "无声的黎明", "seal": "守钟人", "rebirth": "无名者的新生"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS story_mainline (
    story_id TEXT PRIMARY KEY, title TEXT NOT NULL, phase INTEGER NOT NULL DEFAULT 1,
    phase_started_at INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1,
    ending_key TEXT NOT NULL DEFAULT '', ended_at INTEGER
);
CREATE TABLE IF NOT EXISTS story_eligibility (
    uid TEXT NOT NULL, story_id TEXT NOT NULL, phase INTEGER NOT NULL, offered_day INTEGER NOT NULL,
    PRIMARY KEY(uid, story_id, phase)
);
CREATE TABLE IF NOT EXISTS story_offer_attempts (
    uid TEXT NOT NULL, story_id TEXT NOT NULL, phase INTEGER NOT NULL, attempted_day INTEGER NOT NULL,
    PRIMARY KEY(uid, story_id, phase, attempted_day)
);
CREATE TABLE IF NOT EXISTS story_choices (
    uid TEXT NOT NULL, story_id TEXT NOT NULL, phase INTEGER NOT NULL, choice_key TEXT NOT NULL,
    reward INTEGER NOT NULL, chosen_at INTEGER NOT NULL, PRIMARY KEY(uid, story_id, phase)
);
CREATE TABLE IF NOT EXISTS story_phase_results (
    story_id TEXT NOT NULL, phase INTEGER NOT NULL, winning_choice TEXT NOT NULL,
    stats_json TEXT NOT NULL, result_text TEXT NOT NULL, concluded_at INTEGER NOT NULL,
    PRIMARY KEY(story_id, phase)
);
CREATE TABLE IF NOT EXISTS story_state (
    story_id TEXT NOT NULL, state_key TEXT NOT NULL, state_value INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(story_id, state_key)
);
CREATE TABLE IF NOT EXISTS story_personal_tags (
    uid TEXT NOT NULL, story_id TEXT NOT NULL, tag_key TEXT NOT NULL, score INTEGER NOT NULL DEFAULT 0,
    awarded INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(uid, story_id, tag_key)
);
CREATE TABLE IF NOT EXISTS story_endings (
    uid TEXT NOT NULL, story_id TEXT NOT NULL, ending_key TEXT NOT NULL, personal_tag TEXT NOT NULL,
    ending_text TEXT NOT NULL, completed_at INTEGER NOT NULL, PRIMARY KEY(uid, story_id)
);
CREATE TABLE IF NOT EXISTS story_announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT NOT NULL, created_at INTEGER NOT NULL,
    sent_at INTEGER
);
"""


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        now = int(time.time())
        conn.execute(
            "INSERT OR IGNORE INTO story_mainline(story_id,title,phase,phase_started_at) VALUES(?,?,1,?)",
            (STORY_ID, STORY_TITLE, now),
        )
        for key, value in {"professor_trust": 0, "evidence": 0, "echo_power": 0,
                           "public_truth": 0, "seal_integrity": 4}.items():
            conn.execute("INSERT OR IGNORE INTO story_state VALUES(?,?,?)", (STORY_ID, key, value))
        conn.commit()
    finally:
        conn.close()


def _story(conn):
    return conn.execute("SELECT * FROM story_mainline WHERE story_id=?", (STORY_ID,)).fetchone()


def _stats(conn, phase: int) -> dict[str, int]:
    stats = {option.key: 0 for option in PHASE_BY_NUMBER[phase].options}
    for row in conn.execute(
        "SELECT choice_key,COUNT(*) n FROM story_choices WHERE story_id=? AND phase=? GROUP BY choice_key",
        (STORY_ID, phase),
    ):
        stats[row["choice_key"]] = row["n"]
    return stats


def _threshold(conn) -> int:
    count = conn.execute("SELECT COUNT(*) FROM players WHERE house != '' AND grade >= 1").fetchone()[0]
    return max(math.ceil(count * 0.3), 10)


def daily_offer(day: int, rng: random.Random | None = None) -> int:
    """给尚未参与当前阶段的学生以20%概率发放资格，返回新增人数。"""
    rng = rng or random
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        story = _story(conn)
        if not story or not story["active"]:
            conn.rollback()
            return 0
        added = 0
        rows = conn.execute("SELECT uid FROM players WHERE house != '' AND grade >= 1").fetchall()
        for row in rows:
            chosen = conn.execute(
                "SELECT 1 FROM story_choices WHERE uid=? AND story_id=? AND phase=?",
                (row["uid"], STORY_ID, story["phase"]),
            ).fetchone()
            offered = conn.execute(
                "SELECT 1 FROM story_eligibility WHERE uid=? AND story_id=? AND phase=?",
                (row["uid"], STORY_ID, story["phase"]),
            ).fetchone()
            attempted = conn.execute(
                "SELECT 1 FROM story_offer_attempts WHERE uid=? AND story_id=? AND phase=? AND attempted_day=?",
                (row["uid"], STORY_ID, story["phase"], day),
            ).fetchone()
            if chosen or offered or attempted:
                continue
            conn.execute("INSERT INTO story_offer_attempts VALUES(?,?,?,?)",
                         (row["uid"], STORY_ID, story["phase"], day))
            if rng.random() < 0.20:
                conn.execute("INSERT INTO story_eligibility VALUES(?,?,?,?)",
                             (row["uid"], STORY_ID, story["phase"], day))
                added += 1
        conn.commit()
        return added
    finally:
        conn.close()


def task_for(uid: str) -> dict:
    conn = get_conn()
    try:
        player = conn.execute("SELECT * FROM players WHERE uid=?", (uid,)).fetchone()
        if not player or not player["house"]:
            raise StoryError("你还没有入学。")
        story = _story(conn)
        if not story:
            raise StoryError("主线尚未初始化。")
        if not story["active"]:
            ending = conn.execute("SELECT * FROM story_endings WHERE uid=? AND story_id=?", (uid, STORY_ID)).fetchone()
            return {"ended": True, "ending": dict(ending) if ending else None, "world_ending": story["ending_key"]}
        phase = PHASE_BY_NUMBER[story["phase"]]
        eligible = conn.execute("SELECT 1 FROM story_eligibility WHERE uid=? AND story_id=? AND phase=?",
                                (uid, STORY_ID, phase.number)).fetchone() is not None
        choice = conn.execute("SELECT choice_key FROM story_choices WHERE uid=? AND story_id=? AND phase=?",
                              (uid, STORY_ID, phase.number)).fetchone()
        return {"ended": False, "phase": phase, "eligible": eligible, "choice": choice["choice_key"] if choice else "",
                "stats": _stats(conn, phase.number), "threshold": _threshold(conn)}
    finally:
        conn.close()


def choose(uid: str, choice_key: str) -> dict:
    choice_key = choice_key.upper()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        story = _story(conn)
        if not story or not story["active"]:
            raise StoryError("当前没有进行中的主线故事。")
        phase = PHASE_BY_NUMBER[story["phase"]]
        option = next((item for item in phase.options if item.key == choice_key), None)
        if not option:
            raise StoryError("请选择当前任务中的 A、B 或 C。")
        if not conn.execute("SELECT 1 FROM story_eligibility WHERE uid=? AND story_id=? AND phase=?",
                            (uid, STORY_ID, phase.number)).fetchone():
            raise StoryError("你还没有接到当前阶段任务，留意每日触发。")
        now = int(time.time())
        try:
            conn.execute("INSERT INTO story_choices VALUES(?,?,?,?,?,?)",
                         (uid, STORY_ID, phase.number, choice_key, CHOICE_REWARD, now))
        except Exception as exc:
            if "UNIQUE constraint" in str(exc):
                raise StoryError("你已经做出过选择，无法反悔。") from exc
            raise
        conn.execute("UPDATE players SET galleons=galleons+?,updated_at=? WHERE uid=?",
                     (CHOICE_REWARD, now, uid))
        for tag, score in option.tags.items():
            conn.execute(
                "INSERT INTO story_personal_tags(uid,story_id,tag_key,score) VALUES(?,?,?,?) "
                "ON CONFLICT(uid,story_id,tag_key) DO UPDATE SET score=score+excluded.score",
                (uid, STORY_ID, tag, score),
            )
        stats = _stats(conn, phase.number)
        conn.commit()
        advanced = check_and_advance()
        return {"phase": phase.number, "choice": choice_key, "text": option.text, "reward": CHOICE_REWARD,
                "stats": stats, "advanced": advanced}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _apply_effects(conn, option: Option) -> None:
    for key, amount in option.effects.items():
        conn.execute(
            "INSERT INTO story_state VALUES(?,?,?) ON CONFLICT(story_id,state_key) "
            "DO UPDATE SET state_value=state_value+excluded.state_value",
            (STORY_ID, key, amount),
        )


def _ending(conn) -> str:
    state = {r["state_key"]: r["state_value"] for r in conn.execute(
        "SELECT state_key,state_value FROM story_state WHERE story_id=?", (STORY_ID,))}
    rebirth_ready = (state.get("evidence", 0) >= 10 and state.get("public_truth", 0) >= 8
                     and state.get("voluntary_memory", 0) > 0 and state.get("heard_echo", 0) > 0)
    scores = {
        "destroy": state.get("ending_destroy", 0),
        "seal": state.get("ending_seal", 0) + max(state.get("seal_integrity", 0), 0) // 2,
        "rebirth": state.get("ending_rebirth", 0) if rebirth_ready else -1,
    }
    return max(("destroy", "seal", "rebirth"), key=lambda key: (scores[key], -("destroy", "seal", "rebirth").index(key)))


def _finish(conn, now: int) -> str:
    ending = _ending(conn)
    participants = conn.execute("SELECT DISTINCT uid FROM story_choices WHERE story_id=?", (STORY_ID,)).fetchall()
    for participant in participants:
        uid = participant["uid"]
        tags = conn.execute(
            "SELECT tag_key,score FROM story_personal_tags WHERE uid=? AND story_id=? ORDER BY score DESC,tag_key ASC",
            (uid, STORY_ID),
        ).fetchall()
        tag = tags[0]["tag_key"] if tags else "arbiter"
        conn.execute("UPDATE story_personal_tags SET awarded=(tag_key=?) WHERE uid=? AND story_id=?",
                     (tag, uid, STORY_ID))
        text = f"全校结局：{ENDING_NAMES[ending]}。你在这段故事中成为了{TAG_NAMES[tag]}。"
        conn.execute("INSERT OR REPLACE INTO story_endings VALUES(?,?,?,?,?,?)",
                     (uid, STORY_ID, ending, tag, text, now))
    conn.execute("UPDATE story_mainline SET active=0,ending_key=?,ended_at=? WHERE story_id=?",
                 (ending, now, STORY_ID))
    return ending


def check_and_advance(force: bool = False, now: int | None = None) -> dict | None:
    now = now or int(time.time())
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        story = _story(conn)
        if not story or not story["active"]:
            conn.rollback()
            return None
        phase_num = story["phase"]
        stats = _stats(conn, phase_num)
        total = sum(stats.values())
        due = now - story["phase_started_at"] >= PHASE_DURATION_SECONDS
        if total == 0 or (not force and total < _threshold(conn) and not due):
            conn.rollback()
            return None
        winning = max(stats, key=lambda key: (stats[key], -ord(key[0])))
        phase = PHASE_BY_NUMBER[phase_num]
        option = next(item for item in phase.options if item.key == winning)
        _apply_effects(conn, option)
        result_text = f"多数选择：{option.text}（{stats[winning]}票）"
        conn.execute("INSERT INTO story_phase_results VALUES(?,?,?,?,?,?)",
                     (STORY_ID, phase_num, winning, json.dumps(stats, ensure_ascii=False), result_text, now))
        if phase_num == len(PHASES):
            ending = _finish(conn, now)
            message = f"【{STORY_TITLE}】故事完结：{ENDING_NAMES[ending]}。发送「/故事进度」查看你的结局。"
            next_phase = None
        else:
            next_phase = phase_num + 1
            conn.execute("UPDATE story_mainline SET phase=?,phase_started_at=? WHERE story_id=?",
                         (next_phase, now, STORY_ID))
            message = (f"【{STORY_TITLE}】阶段推进！\n{result_text}\n"
                       f"第{next_phase}阶段·{PHASE_BY_NUMBER[next_phase].title}已经开始。")
        conn.execute("INSERT INTO story_announcements(message,created_at) VALUES(?,?)", (message, now))
        conn.commit()
        return {"phase": phase_num, "winning": winning, "stats": stats, "next_phase": next_phase, "message": message}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def progress(uid: str | None = None) -> dict:
    conn = get_conn()
    try:
        story = _story(conn)
        data = dict(story)
        if story["active"]:
            data.update({"phase_title": PHASE_BY_NUMBER[story["phase"]].title,
                         "stats": _stats(conn, story["phase"]), "threshold": _threshold(conn)})
        if uid:
            ending = conn.execute("SELECT * FROM story_endings WHERE uid=? AND story_id=?", (uid, STORY_ID)).fetchone()
            data["personal_ending"] = dict(ending) if ending else None
        return data
    finally:
        conn.close()


def pending_announcements() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM story_announcements WHERE sent_at IS NULL ORDER BY id").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def mark_announcement_sent(announcement_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute("UPDATE story_announcements SET sent_at=? WHERE id=? AND sent_at IS NULL",
                     (int(time.time()), announcement_id))
        conn.commit()
    finally:
        conn.close()


init_db()

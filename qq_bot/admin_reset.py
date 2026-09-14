"""管理员专用：清空一个人的入学记录，让TA能重新走一遍分院流程。

只在网页后台（/admin）触发，走一次性硬删除——把这个uid在全部插件里
（hp_core / hp_school / hp_events / hp_social，以及顶层的校报投稿、女巫周刊、
通知队列）攒下的数据全部清空，players表本身回到"从未入学"的初始状态，
效果跟全新QQ号第一次入学前一样。

网页登录账号（web_auth.web_accounts）不受影响，账号照样能登录——只是
/enroll 会重新判定为"还没分院"，引导本人回QQ群发「/入学 名字」重新开始
（分院测试和选魔杖的流程本来就只在QQ里做，网页从不直接写这部分数据）。
"""

from __future__ import annotations

from plugins.hp_core.storage import HOUSES, STAMINA_MAX, get_conn, now

# 这个函数要清的表分散在一堆插件里，有些表只在对应功能第一次被用到时才会建。
# 不能假设调用方（web_app.py）已经把它们全部import过——这里显式ensure一遍，
# 保证下面一串DELETE不会因为"表还没建"而中途炸掉。
import gossip
import submissions
from plugins.hp_events import storage as _events_storage
from plugins.hp_pet import storage as _pet_storage
from plugins.hp_school import storage as _school_storage
from plugins.hp_school import subjects as _subjects
from plugins.hp_school import tailor as _tailor
from plugins.hp_school import themes as _themes
from plugins.hp_social import dorm as _dorm
from plugins.hp_social import friendship as _friendship
from plugins.hp_social import mail as _mail
from plugins.hp_social import storage as _social_storage

_school_storage.init_db()
_events_storage.init_db()
_social_storage.init_db()
_dorm.init_db()
_mail.init_db()
_friendship.init_db()
_pet_storage.init_db()
_tailor.init_db()
_themes.init_db()
gossip.init_db()
submissions.init_db()


class ResetError(Exception):
    pass


# 表里只有一个uid字段，直接 DELETE FROM table WHERE uid = ? 即可清干净
_SIMPLE_UID_TABLES = (
    # hp_core
    "subject_exp", "lesson_log", "lesson_score_log", "learned_spells",
    "spell_progress", "homework", "house_contributions", "titles",
    "active_effects", "exam_results", "kitchen_exp", "kitchen_sessions",
    "kitchen_daily", "kitchen_learned_recipes", "kitchen_inventory",
    "kitchen_mastery", "kitchen_history",
    # hp_school
    "sorting_sessions", "inventory", "lesson_sessions", "player_wands",
    "work_daily", "daily_rewards", "careers", "potion_sessions",
    "potion_mastery", "potion_daily", "potion_effects", "potion_history",
    "potion_yearly", "potion_trade_daily", "freshman_duels", "choc_frog_cards",
    "tailor_progress", "tailor_learned_patterns", "tailor_inventory", "tailor_listings",
    "web_theme_ownership", "web_theme_equipment", "web_theme_game_scores",
    # hp_events
    "quidditch_players", "quidditch_daily", "forest_daily",
    "forest_defeated", "gnome_daily", "gnome_catches", "gnome_cooldown", "duel_daily",
    "ball_robes", "ball_attendance", "tree_hangs", "tree_rewards",
    "prefect_candidates", "prefects", "prefect_duty",
    # hp_social
    "social_daily", "letter_daily",
    # hp_pet
    "pets", "pet_daily",
    # 顶层模块
    "gossip_submissions", "newspaper_submissions", "notifications",
)

# 表里是"A对B"的两个uid字段，任一命中就删（单向或双向关系表都这么处理）
_DUAL_UID_TABLES = (
    ("potion_trades", "sender_uid", "receiver_uid"),
    ("duel_challenges", "challenger_uid", "target_uid"),
    ("ball_invites", "inviter_uid", "target_uid"),
    ("ball_partners", "uid", "partner_uid"),
    ("prefect_votes", "voter_uid", "target_uid"),
    ("affection", "from_uid", "to_uid"),
    ("relationships", "uid_a", "uid_b"),
    ("flirt_log", "from_uid", "to_uid"),
    ("dorm_invites", "from_uid", "to_uid"),
    ("letters", "from_uid", "to_uid"),
    ("friend_points", "from_uid", "to_uid"),
    ("friend_log", "from_uid", "to_uid"),
    ("friend_study_bonus_log", "uid_a", "uid_b"),
)


def reset_enrollment(uid: str) -> dict:
    """把一个人的入学记录和全部关联游戏数据清空，让TA能重新「/入学」。"""
    uid = (uid or "").strip()
    if not uid:
        raise ResetError("请填写QQ号。")

    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        player = conn.execute("SELECT * FROM players WHERE uid = ?", (uid,)).fetchone()
        if not player:
            raise ResetError(f"{uid} 在花名册里查不到，可能从来没入学过。")

        old_house = player["house"]
        old_name = f"{player['name']}·{player['surname']}" if player["surname"] else player["name"]

        if old_house:
            conn.execute(
                "UPDATE house_points SET member_count = MAX(0, member_count - 1) WHERE house = ?",
                (old_house,),
            )

        for table in _SIMPLE_UID_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE uid = ?", (uid,))

        for table, col_a, col_b in _DUAL_UID_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE {col_a} = ? OR {col_b} = ?", (uid, uid))

        # 决斗/禁林战斗的冷却表挂在session_id/run_id下，要在删父表前先按uid反查着清掉
        conn.execute(
            "DELETE FROM duel_cooldowns WHERE session_id IN "
            "(SELECT id FROM duel_sessions WHERE uid_a = ? OR uid_b = ?)",
            (uid, uid),
        )
        conn.execute("DELETE FROM duel_sessions WHERE uid_a = ? OR uid_b = ?", (uid, uid))
        conn.execute(
            "DELETE FROM forest_cooldowns WHERE run_id IN "
            "(SELECT id FROM forest_runs WHERE uid = ?)",
            (uid,),
        )
        conn.execute("DELETE FROM forest_runs WHERE uid = ?", (uid,))

        # 寝室是两人一间，一方重置整间解散，对方自动变回没有室友
        conn.execute("DELETE FROM dorms WHERE member_a = ? OR member_b = ?", (uid, uid))

        ts = now()
        conn.execute(
            "UPDATE players SET name='', surname='', gender='', house='', grade=1, "
            "stamina=?, stamina_updated_at=?, galleons=0, active_title='', updated_at=? "
            "WHERE uid=?",
            (STAMINA_MAX, ts, ts, uid),
        )
        conn.commit()
        return {"uid": uid, "old_house": old_house, "old_name": old_name}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rename_player(uid: str, new_name: str, new_surname: str = "") -> dict:
    """给一个人改名（名/姓）。

    只需要动 players 表本身——姓名从不在别的表里存副本，全站找人都是靠 uid，
    显示名字（get_full_name）也是每次现查 players 表，所以改这一处就"到处生效"了；
    唯一例外是已经发出去的历史文本（比如群里已经播报过的旧消息、女巫周刊旧稿的
    署名快照），那些是历史记录，不应该也没法回溯着改。
    """
    uid = (uid or "").strip()
    if not uid:
        raise ResetError("请填写QQ号或角色名字。")
    new_name = (new_name or "").strip()
    if not new_name:
        raise ResetError("新名字不能是空的。")
    new_surname = (new_surname or "").strip()

    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        player = conn.execute("SELECT * FROM players WHERE uid = ?", (uid,)).fetchone()
        if not player or not player["house"]:
            raise ResetError(f"{uid} 还没有入学，没法改名。")
        old_name = f"{player['name']}·{player['surname']}" if player["surname"] else player["name"]

        if new_name != player["name"]:
            clash = conn.execute(
                "SELECT 1 FROM players WHERE name = ? AND uid != ?", (new_name, uid)
            ).fetchone()
            if clash:
                raise ResetError(f"「{new_name}」已经被别人用了，名字（不含姓）全校唯一，换一个。")

        conn.execute(
            "UPDATE players SET name = ?, surname = ?, updated_at = ? WHERE uid = ?",
            (new_name, new_surname, now(), uid),
        )
        conn.commit()
        new_full = f"{new_name}·{new_surname}" if new_surname else new_name
        return {"uid": uid, "old_name": old_name, "new_name": new_full}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def transfer_house(uid: str, new_house: str) -> dict:
    """把一个人转到别的学院。只动院籍和学院分——TA在原学院攒的个人贡献分清零，
    也从原学院总分里扣掉这部分，避免转走之后原学院还白白留着这份分；新学院从0开始记。
    学科经验、寝室、恋人好友、决斗/魁地奇战绩等其余游戏数据完全不受影响。
    """
    uid = (uid or "").strip()
    if not uid:
        raise ResetError("请填写QQ号或角色名字。")
    new_house = (new_house or "").strip()
    if new_house not in HOUSES:
        raise ResetError(f"「{new_house}」不是学院名字，只能是{'/'.join(HOUSES)}之一。")

    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        player = conn.execute("SELECT * FROM players WHERE uid = ?", (uid,)).fetchone()
        if not player or not player["house"]:
            raise ResetError(f"{uid} 还没有入学，没法转院。")
        old_house = player["house"]
        if old_house == new_house:
            raise ResetError(f"{uid} 已经在{new_house}了，不用转。")
        old_name = f"{player['name']}·{player['surname']}" if player["surname"] else player["name"]

        contribution = conn.execute(
            "SELECT points FROM house_contributions WHERE uid = ?", (uid,)
        ).fetchone()
        cleared_points = contribution["points"] if contribution else 0

        conn.execute(
            "UPDATE house_points SET member_count = MAX(0, member_count - 1), "
            "total_points = MAX(0, total_points - ?) WHERE house = ?",
            (cleared_points, old_house),
        )
        conn.execute(
            "UPDATE house_points SET member_count = member_count + 1 WHERE house = ?",
            (new_house,),
        )
        conn.execute("DELETE FROM house_contributions WHERE uid = ?", (uid,))
        conn.execute(
            "UPDATE players SET house = ?, updated_at = ? WHERE uid = ?",
            (new_house, now(), uid),
        )
        conn.commit()
        return {
            "uid": uid,
            "old_name": old_name,
            "old_house": old_house,
            "new_house": new_house,
            "cleared_points": cleared_points,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


STAT_LABELS = {
    "galleons": "加隆",
    "stamina": "体力",
    "exp": "学科经验",
    "qd_speed": "魁地奇-速度",
    "qd_collision": "魁地奇-碰撞",
    "qd_stamina": "魁地奇-体力",
    "qd_accuracy": "魁地奇-准头",
}
QUIDDITCH_STAT_COLUMNS = {
    "qd_speed": "speed",
    "qd_collision": "collision",
    "qd_stamina": "stamina",
    "qd_accuracy": "accuracy",
}


def adjust_stat(uid: str, stat: str, amount: int, subject: str = "") -> dict:
    """管理员手动加减一项数值属性，用于修正bug造成的数据偏差，不走游戏内的获取/消耗逻辑。

    加隆、体力、学科经验三种都做了下限0的钳制（体力另外钳上限），不会调出负数或超出体力上限。
    魁地奇四维属性同样钳下限0——不然减成负数会让位置实力/胜率计算出现奇怪的负数。
    """
    uid = (uid or "").strip()
    if not uid:
        raise ResetError("请填写QQ号或角色名字。")
    if stat not in STAT_LABELS:
        raise ResetError(f"不认识的属性「{stat}」。")
    if amount == 0:
        raise ResetError("数值不能是0。")

    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        player = conn.execute("SELECT * FROM players WHERE uid = ?", (uid,)).fetchone()
        if not player or not player["house"]:
            raise ResetError(f"{uid} 还没有入学，没法调整属性。")
        full_name = f"{player['name']}·{player['surname']}" if player["surname"] else player["name"]

        if stat == "galleons":
            old = player["galleons"]
            new = max(0, old + amount)
            conn.execute(
                "UPDATE players SET galleons = ?, updated_at = ? WHERE uid = ?", (new, now(), uid)
            )
            label = STAT_LABELS["galleons"]
        elif stat == "stamina":
            old = player["stamina"]
            new = max(0, min(STAMINA_MAX, old + amount))
            conn.execute(
                "UPDATE players SET stamina = ?, updated_at = ? WHERE uid = ?", (new, now(), uid)
            )
            label = STAT_LABELS["stamina"]
        elif stat in QUIDDITCH_STAT_COLUMNS:
            column = QUIDDITCH_STAT_COLUMNS[stat]
            qp = conn.execute("SELECT * FROM quidditch_players WHERE uid = ?", (uid,)).fetchone()
            if not qp:
                raise ResetError(f"{full_name}还不是魁地奇选手，没有属性可调。")
            old = qp[column]
            new = max(0, old + amount)
            conn.execute(
                f"UPDATE quidditch_players SET {column} = ?, updated_at = ? WHERE uid = ?",
                (new, now(), uid),
            )
            label = STAT_LABELS[stat]
        else:  # exp
            subject = (subject or "").strip()
            if subject not in _subjects.SUBJECTS_BY_KEY:
                raise ResetError("请选一个有效的学科。")
            row = conn.execute(
                "SELECT exp FROM subject_exp WHERE uid = ? AND subject = ?", (uid, subject)
            ).fetchone()
            old = row["exp"] if row else 0
            new = max(0, old + amount)
            conn.execute(
                "INSERT INTO subject_exp (uid, subject, exp) VALUES (?, ?, ?) "
                "ON CONFLICT(uid, subject) DO UPDATE SET exp = ?",
                (uid, subject, new, new),
            )
            label = f"{_subjects.SUBJECTS_BY_KEY[subject][0]}经验"

        conn.commit()
        return {
            "uid": uid,
            "name": full_name,
            "label": label,
            "old": old,
            "new": new,
            "delta": amount,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

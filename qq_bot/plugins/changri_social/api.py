import secrets
import string
import time

from plugins.changri_core.api import (
    add_notification,
    get_primary_uid,
    get_role_name,
    get_setting_int,
    get_uid_by_role_name,
    set_setting,
)

from .storage import get_conn, init_db

init_db()

DEFAULTS = {
    "forum_max_length": 500,
    "max_detail_chars": 500,
    "max_relationships_per_user": 20,
    "max_detail_count": 20,
    "max_rel_total_chars": 3000,
}


def get_config() -> dict:
    return {k: get_setting_int(k, v) for k, v in DEFAULTS.items()}


def set_config(**kwargs) -> None:
    for key, value in kwargs.items():
        if key in DEFAULTS:
            set_setting(key, str(value))


# ── 论坛 ──────────────────────────────────────────────────────────────

_POST_ID_ALPHABET = string.ascii_uppercase + string.digits


def _new_post_id() -> str:
    conn = get_conn()
    try:
        for _ in range(10):
            code = "".join(secrets.choice(_POST_ID_ALPHABET) for _ in range(5))
            exists = conn.execute("SELECT 1 FROM forum_posts WHERE id = ?", (code,)).fetchone()
            if exists is None:
                return code
        raise RuntimeError("无法生成唯一贴号")
    finally:
        conn.close()


def create_post(platform: str, author_uid: str, author_name: str, content: str) -> tuple[bool, str]:
    author_uid = get_primary_uid(platform, author_uid)
    config = get_config()
    if len(content) > config["forum_max_length"]:
        return False, f"内容过长（{len(content)} 字），论坛发帖上限为 {config['forum_max_length']} 字，请精简后再提交。"
    post_id = _new_post_id()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO forum_posts (id, platform, author_uid, author_name, content, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'active', ?)",
            (post_id, platform, author_uid, author_name, content, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()
    return True, post_id


def _get_active_post(platform: str, post_id: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM forum_posts WHERE platform = ? AND id = ? AND status = 'active'",
            (platform, post_id),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def _get_replies(post_id: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM forum_replies WHERE post_id = ? ORDER BY id ASC", (post_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _vote_counts(table: str, id_col: str, target_id) -> tuple[int, int]:
    conn = get_conn()
    try:
        row = conn.execute(
            f"SELECT "
            f"SUM(CASE WHEN vote_type = 'like' THEN 1 ELSE 0 END) AS likes, "
            f"SUM(CASE WHEN vote_type = 'dislike' THEN 1 ELSE 0 END) AS dislikes "
            f"FROM {table} WHERE {id_col} = ?",
            (target_id,),
        ).fetchone()
        return row["likes"] or 0, row["dislikes"] or 0
    finally:
        conn.close()


def add_reply(
    platform: str,
    post_id: str,
    author_uid: str,
    author_name: str,
    content: str,
    quote_floor: int | None = None,
) -> tuple[bool, str]:
    author_uid = get_primary_uid(platform, author_uid)
    config = get_config()
    if len(content) > config["forum_max_length"]:
        return False, f"内容过长（{len(content)} 字），论坛回复上限为 {config['forum_max_length']} 字，请精简后再提交。"
    post = _get_active_post(platform, post_id)
    if post is None:
        return False, f"找不到帖子 [{post_id}]"

    quote_content = None
    if quote_floor is not None:
        if quote_floor == 0:
            quote_content = post["content"]
        else:
            replies = _get_replies(post_id)
            if quote_floor < 1 or quote_floor > len(replies):
                return False, f"楼层 L{quote_floor} 不存在（当前共 {len(replies)} 楼）"
            quote_content = replies[quote_floor - 1]["content"]
        if len(quote_content) > 60:
            quote_content = quote_content[:60] + "…"

    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO forum_replies (post_id, author_uid, author_name, content, quote_floor, quote_content, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (post_id, author_uid, author_name, content, quote_floor, quote_content, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()
    return True, "已回复"


def extract_mentions(platform: str, content: str) -> list[str]:
    import re

    from plugins.changri_core.api import list_role_names

    names = set(list_role_names(platform))
    mentioned = {m for m in re.findall(r"@(\S+)", content)}
    return [n for n in mentioned if n in names]


def vote_post(post_id: str, voter_name: str, is_like: bool) -> tuple[bool, str, int, int]:
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT vote_type FROM forum_post_votes WHERE post_id = ? AND voter_name = ?",
            (post_id, voter_name),
        ).fetchone()
        want = "like" if is_like else "dislike"
        if existing is not None and existing["vote_type"] == want:
            likes, dislikes = _vote_counts("forum_post_votes", "post_id", post_id)
            return False, "你已经表过态啦～", likes, dislikes
        conn.execute(
            "INSERT INTO forum_post_votes (post_id, voter_name, vote_type) VALUES (?, ?, ?) "
            "ON CONFLICT (post_id, voter_name) DO UPDATE SET vote_type = excluded.vote_type",
            (post_id, voter_name, want),
        )
        conn.commit()
    finally:
        conn.close()
    likes, dislikes = _vote_counts("forum_post_votes", "post_id", post_id)
    return True, ("点赞" if is_like else "点踩") + "成功！", likes, dislikes


def vote_reply(reply_id: int, voter_name: str, is_like: bool) -> tuple[bool, str, int, int]:
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT vote_type FROM forum_reply_votes WHERE reply_id = ? AND voter_name = ?",
            (reply_id, voter_name),
        ).fetchone()
        want = "like" if is_like else "dislike"
        if existing is not None and existing["vote_type"] == want:
            likes, dislikes = _vote_counts("forum_reply_votes", "reply_id", reply_id)
            return False, "你已经表过态啦～", likes, dislikes
        conn.execute(
            "INSERT INTO forum_reply_votes (reply_id, voter_name, vote_type) VALUES (?, ?, ?) "
            "ON CONFLICT (reply_id, voter_name) DO UPDATE SET vote_type = excluded.vote_type",
            (reply_id, voter_name, want),
        )
        conn.commit()
    finally:
        conn.close()
    likes, dislikes = _vote_counts("forum_reply_votes", "reply_id", reply_id)
    return True, ("点赞" if is_like else "点踩") + "成功！", likes, dislikes


def get_reply_by_floor(post_id: str, floor: int) -> dict | None:
    replies = _get_replies(post_id)
    if floor < 1 or floor > len(replies):
        return None
    reply = replies[floor - 1]
    likes, dislikes = _vote_counts("forum_reply_votes", "reply_id", reply["id"])
    reply["likes"], reply["dislikes"] = likes, dislikes
    return reply


def get_post_detail(platform: str, post_id: str) -> dict | None:
    post = _get_active_post(platform, post_id)
    if post is None:
        return None
    likes, dislikes = _vote_counts("forum_post_votes", "post_id", post_id)
    post["likes"], post["dislikes"] = likes, dislikes
    replies = _get_replies(post_id)
    for r in replies:
        r["likes"], r["dislikes"] = _vote_counts("forum_reply_votes", "reply_id", r["id"])
    post["replies"] = replies
    return post


def list_hot_posts(platform: str, limit: int = 10) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM forum_posts WHERE platform = ? AND status = 'active'", (platform,)
        ).fetchall()
    finally:
        conn.close()
    posts = [dict(r) for r in rows]
    for p in posts:
        p["reply_count"] = len(_get_replies(p["id"]))
        p["likes"], _ = _vote_counts("forum_post_votes", "post_id", p["id"])
    posts.sort(key=lambda p: p["reply_count"] * 2 + p["likes"], reverse=True)
    return posts[:limit]


def delete_post(platform: str, post_id: str) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE forum_posts SET status = 'deleted' WHERE platform = ? AND id = ? AND status = 'active'",
            (platform, post_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ── 关系线 ──────────────────────────────────────────────────────────────


def _pair(uid_a: str, uid_b: str) -> tuple[str, str]:
    return (uid_a, uid_b) if uid_a <= uid_b else (uid_b, uid_a)


def _get_line_row(platform: str, uid_a: str, uid_b: str) -> dict | None:
    uid_lo, uid_hi = _pair(uid_a, uid_b)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM relationship_lines WHERE platform = ? AND uid_lo = ? AND uid_hi = ?",
            (platform, uid_lo, uid_hi),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def _get_details(line_id: int) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM relationship_details WHERE line_id = ? ORDER BY id ASC", (line_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_relationship_detail(
    platform: str, from_uid: str, from_name: str, to_name: str, content: str
) -> tuple[bool, str]:
    from_uid = get_primary_uid(platform, from_uid)
    to_uid = get_uid_by_role_name(platform, to_name)
    if to_uid is None:
        return False, "❌ 找不到角色"
    if to_uid == from_uid:
        return False, "⚠️ 你不能跟自己建立关系线哦。"

    config = get_config()
    if len(content) > config["max_detail_chars"]:
        return False, f"⚠️ 内容过长（{len(content)} 字），单条拉线上限为 {config['max_detail_chars']} 字，请精简后再提交。"

    line = _get_line_row(platform, from_uid, to_uid)
    is_new = line is None

    if is_new:
        conn = get_conn()
        try:
            current_count = conn.execute(
                "SELECT COUNT(*) AS c FROM relationship_lines WHERE platform = ? AND initiator_uid = ?",
                (platform, from_uid),
            ).fetchone()["c"]
        finally:
            conn.close()
        if current_count >= config["max_relationships_per_user"]:
            return False, f"⚠️ 你的发起额度已达上限 ({config['max_relationships_per_user']})"

        uid_lo, uid_hi = _pair(from_uid, to_uid)
        conn = get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO relationship_lines "
                "(platform, uid_lo, uid_hi, initiator_uid, initiator_name, confirmed, is_mandatory, created_at) "
                "VALUES (?, ?, ?, ?, ?, 0, 0, ?)",
                (platform, uid_lo, uid_hi, from_uid, from_name, int(time.time())),
            )
            conn.commit()
            line_id = cur.lastrowid
        finally:
            conn.close()
    else:
        line_id = line["id"]
        details = _get_details(line_id)
        if len(details) >= config["max_detail_count"]:
            return False, f"⚠️ 你们的关系线已达段数上限（{config['max_detail_count']} 段），无法继续添加。"
        total_chars = sum(len(d["content"]) for d in details)
        if total_chars + len(content) > config["max_rel_total_chars"]:
            return False, (
                f"⚠️ 添加后将超过总字数上限（{config['max_rel_total_chars']} 字，"
                f"当前已有 {total_chars} 字），请精简内容。"
            )

    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO relationship_details (line_id, from_uid, from_name, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (line_id, from_uid, from_name, content, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()

    add_notification(platform, to_uid, "关系线", f"{from_name} 拉了一条新的关系细节：{content}")

    details = _get_details(line_id)
    total_chars_now = sum(len(d["content"]) for d in details)
    hint = (
        f"（本条 {len(content)} 字 · 累计 {total_chars_now}/{config['max_rel_total_chars']} 字 · "
        f"{len(details)}/{config['max_detail_count']} 段）"
    )
    prefix = "✨ 关系线已建立。\n" if is_new else ""
    return True, f"{prefix}✅ 细节已记录\n{hint}"


def confirm_relationship(platform: str, from_uid: str, from_name: str, to_name: str) -> tuple[bool, str]:
    from_uid = get_primary_uid(platform, from_uid)
    to_uid = get_uid_by_role_name(platform, to_name)
    if to_uid is None:
        return False, "未找到该关系线"
    line = _get_line_row(platform, from_uid, to_uid)
    if line is None:
        return False, "未找到该关系线"
    conn = get_conn()
    try:
        conn.execute("UPDATE relationship_lines SET confirmed = 1 WHERE id = ?", (line["id"],))
        conn.commit()
    finally:
        conn.close()
    add_notification(platform, to_uid, "关系线", f"「{from_name}」已确认并完成了你们的关系线！")
    return True, f"✅ 你已确认与「{to_name}」的关系线为完成状态。"


def set_forced_relationship(platform: str, name_a: str, name_b: str, content: str) -> tuple[bool, str]:
    uid_a = get_uid_by_role_name(platform, name_a)
    uid_b = get_uid_by_role_name(platform, name_b)
    if uid_a is None:
        return False, f"❌ 找不到角色「{name_a}」"
    if uid_b is None:
        return False, f"❌ 找不到角色「{name_b}」"

    uid_lo, uid_hi = _pair(uid_a, uid_b)
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT id FROM relationship_lines WHERE platform = ? AND uid_lo = ? AND uid_hi = ?",
            (platform, uid_lo, uid_hi),
        ).fetchone()
        now = int(time.time())
        if existing is not None:
            line_id = existing["id"]
            conn.execute(
                "UPDATE relationship_lines SET initiator_uid = 'SYSTEM', initiator_name = 'SYSTEM', "
                "confirmed = 1, is_mandatory = 1 WHERE id = ?",
                (line_id,),
            )
        else:
            cur = conn.execute(
                "INSERT INTO relationship_lines "
                "(platform, uid_lo, uid_hi, initiator_uid, initiator_name, confirmed, is_mandatory, created_at) "
                "VALUES (?, ?, ?, 'SYSTEM', 'SYSTEM', 1, 1, ?)",
                (platform, uid_lo, uid_hi, now),
            )
            line_id = cur.lastrowid
        conn.execute(
            "INSERT INTO relationship_details (line_id, from_uid, from_name, content, created_at) "
            "VALUES (?, 'SYSTEM', '管理员', ?, ?)",
            (line_id, f"[系统设定] {content}", now),
        )
        conn.commit()
    finally:
        conn.close()
    return True, f"✅ 已成功为「{name_a}」与「{name_b}」建立强制关系线。"


def delete_relationship(platform: str, name_a: str, name_b: str) -> tuple[bool, str]:
    uid_a = get_uid_by_role_name(platform, name_a)
    uid_b = get_uid_by_role_name(platform, name_b)
    if uid_a is None:
        return False, f"❌ 找不到角色「{name_a}」"
    if uid_b is None:
        return False, f"❌ 找不到角色「{name_b}」"
    line = _get_line_row(platform, uid_a, uid_b)
    if line is None:
        return False, "这两人之间没有关系线"
    conn = get_conn()
    try:
        conn.execute("DELETE FROM relationship_details WHERE line_id = ?", (line["id"],))
        conn.execute("DELETE FROM relationship_lines WHERE id = ?", (line["id"],))
        conn.commit()
    finally:
        conn.close()
    return True, "✅ 已删除该关系线"


def clear_relationships(platform: str) -> None:
    conn = get_conn()
    try:
        line_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM relationship_lines WHERE platform = ?", (platform,)
        ).fetchall()]
        if line_ids:
            conn.executemany("DELETE FROM relationship_details WHERE line_id = ?", [(i,) for i in line_ids])
        conn.execute("DELETE FROM relationship_lines WHERE platform = ?", (platform,))
        conn.commit()
    finally:
        conn.close()


def withdraw_relationship_detail(
    platform: str, from_uid: str, from_name: str, to_name: str, content: str
) -> tuple[bool, str]:
    from_uid = get_primary_uid(platform, from_uid)
    to_uid = get_uid_by_role_name(platform, to_name)
    if to_uid is None:
        return False, "没有可撤回的细节记录。"
    line = _get_line_row(platform, from_uid, to_uid)
    if line is None:
        return False, "没有可撤回的细节记录。"
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, content FROM relationship_details WHERE line_id = ? AND from_uid = ? AND content = ? "
            "ORDER BY id DESC LIMIT 1",
            (line["id"], from_uid, content),
        ).fetchone()
        if row is None:
            return False, f"未找到你发送的匹配内容：「{content}」\n可使用「/查看关系线 {to_name}」查看所有细节。"
        conn.execute("DELETE FROM relationship_details WHERE id = ?", (row["id"],))
        conn.commit()
        removed_text = row["content"]
    finally:
        conn.close()
    add_notification(platform, to_uid, "关系线", f"「{from_name}」撤回了一条发给你的关系细节：{removed_text}")
    return True, f"✅ 已成功撤回你发送的细节：\n\"{removed_text}\""


def get_relationship_with(platform: str, my_uid: str, other_name: str) -> dict | None:
    my_uid = get_primary_uid(platform, my_uid)
    other_uid = get_uid_by_role_name(platform, other_name)
    if other_uid is None:
        return None
    line = _get_line_row(platform, my_uid, other_uid)
    if line is None:
        return None
    line["details"] = _get_details(line["id"])
    return line


def list_my_relationships(platform: str, my_uid: str) -> list[dict]:
    my_uid = get_primary_uid(platform, my_uid)
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM relationship_lines WHERE platform = ? AND (uid_lo = ? OR uid_hi = ?)",
            (platform, my_uid, my_uid),
        ).fetchall()
    finally:
        conn.close()
    result = []
    for row in rows:
        line = dict(row)
        other_uid = line["uid_hi"] if line["uid_lo"] == my_uid else line["uid_lo"]
        other_name = get_role_name(platform, other_uid) or other_uid
        details = _get_details(line["id"])
        result.append(
            {
                "line": line,
                "other_uid": other_uid,
                "other_name": other_name,
                "detail_count": len(details),
                "total_chars": sum(len(d["content"]) for d in details),
                "is_initiator": line["initiator_uid"] == my_uid,
                "is_system": line["initiator_uid"] == "SYSTEM",
            }
        )
    return result


def get_relationship_stats(platform: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT uid_lo, uid_hi FROM relationship_lines WHERE platform = ?", (platform,)
        ).fetchall()
    finally:
        conn.close()
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["uid_lo"]] = counts.get(row["uid_lo"], 0) + 1
        counts[row["uid_hi"]] = counts.get(row["uid_hi"], 0) + 1
    stats = [
        {"role": get_role_name(platform, uid) or uid, "count": count} for uid, count in counts.items()
    ]
    stats.sort(key=lambda s: s["count"], reverse=True)
    return stats

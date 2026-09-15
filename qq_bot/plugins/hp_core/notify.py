"""通知队列：网页上的操作 → QQ群播报（10分钟汇总一次）。

网页和机器人是两个进程，网页不能直接调 nonebot 发消息，所以走数据库队列：
网页操作时 push() 一条，机器人端的定时任务每10分钟扫一次，汇总成一条播报出去。

什么都记，但会合并同类项——一个人连上5节魔咒课，播报里是"上了5节魔咒课"一行，
而不是刷5条。merge_key 相同的会被合并并累加次数，text 里的 {n} 会被替换成总次数；
merge_key 留空表示这是一次性事件（表白、决斗获胜之类），不参与合并。
"""

from .storage import get_conn, now

SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    merge_key TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL,
    amount INTEGER NOT NULL DEFAULT 1,
    sent INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notifications_pending ON notifications (sent, id);
"""

# 播报时的分组顺序和小标题
CATEGORY_ORDER = [
    ("enroll", "🎓 新生"),
    ("duel", "⚔️ 决斗"),
    ("quidditch", "🧹 魁地奇"),
    ("forest", "🌲 禁林"),
    ("social", "💗 社交"),
    ("prank", "😈 恶作剧"),
    ("career", "🎓 毕业去向"),
    ("press", "✒️ 校报来稿"),
    ("study", "📚 学业"),
    ("economy", "💰 生计"),
]


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        for stmt in (
            "ALTER TABLE notifications ADD COLUMN merge_key TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE notifications ADD COLUMN amount INTEGER NOT NULL DEFAULT 1",
        ):
            try:
                conn.execute(stmt)
            except Exception:
                pass  # 列已存在（旧库升级用）
        conn.commit()
    finally:
        conn.close()


def push(text: str, uid: str = "", category: str = "", merge_key: str = "", amount: int = 1) -> None:
    """排一条待播报的消息。失败不抛异常——通知发不出去不该让玩家的操作回滚。"""
    if not text:
        return
    try:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO notifications (uid, category, merge_key, text, amount, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (uid, category, merge_key, text, amount, now()),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def take_pending(limit: int = 500) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, uid, category, merge_key, text, amount, created_at FROM notifications "
            "WHERE sent = 0 ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _merge_entries(items: list[dict]) -> list[dict]:
    """按 (uid, category, merge_key) 合并同类项，amount 累加；merge_key 为空的各算一条不参与合并。
    created_at 取合并组里最新的一条，方便按时间排序展示。"""
    merged: dict = {}
    order: list = []
    for item in items:
        key = (item["uid"], item["category"], item["merge_key"] or f"__unique_{item['id']}")
        if key in merged:
            merged[key]["amount"] += item["amount"]
            merged[key]["created_at"] = max(merged[key].get("created_at", 0), item.get("created_at", 0))
        else:
            merged[key] = dict(item)
            order.append(key)
    return [merged[k] for k in order]


def list_recent(limit: int = 20) -> list[dict]:
    """按时间倒序取最近的通知（已合并同类项），供网页首页"校园动态"展示用。

    只读，不改 sent 状态——跟QQ播报那边"取走就要标记已发"的消费队列语义不冲突，
    两边各看各的，互不干扰。合并逻辑跟 build_digest 是同一套，不然网页上连着
    吃三口零食会拆成三条一模一样的动态，很难看。
    """
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, uid, category, merge_key, text, amount, created_at FROM notifications "
            "ORDER BY id DESC LIMIT ?",
            (limit * 4,),
        ).fetchall()
    finally:
        conn.close()
    merged = _merge_entries([dict(r) for r in rows])
    merged.sort(key=lambda e: e["created_at"], reverse=True)
    return merged[:limit]


def mark_sent(ids: list[int]) -> None:
    if not ids:
        return
    conn = get_conn()
    try:
        marks = ",".join("?" for _ in ids)
        conn.execute(f"UPDATE notifications SET sent = 1 WHERE id IN ({marks})", ids)
        conn.commit()
    finally:
        conn.close()


def purge_sent(before_seconds: int = 7 * 86400) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM notifications WHERE sent = 1 AND created_at < ?", (now() - before_seconds,)
        )
        conn.commit()
    finally:
        conn.close()


def build_digest(pending: list[dict], name_of) -> str:
    """把一批待播报的事件汇总成一条消息。name_of(uid) 用来取显示名。"""
    if not pending:
        return ""

    by_category: dict = {}
    for entry in _merge_entries(pending):
        by_category.setdefault(entry["category"] or "study", []).append(entry)

    lines = ["📋 霍格沃茨动态"]
    known = [c for c, _ in CATEGORY_ORDER]
    for category, title in CATEGORY_ORDER:
        entries = by_category.get(category)
        if not entries:
            continue
        lines.append("")
        lines.append(title)
        for entry in entries:
            who = name_of(entry["uid"]) if entry["uid"] else ""
            body = entry["text"].replace("{n}", str(entry["amount"]))
            lines.append(f"· {who}{body}" if who else f"· {body}")
    # 没归到已知分类的兜底
    leftovers = [e for c, es in by_category.items() if c not in known for e in es]
    if leftovers:
        lines.append("")
        for entry in leftovers:
            who = name_of(entry["uid"]) if entry["uid"] else ""
            body = entry["text"].replace("{n}", str(entry["amount"]))
            lines.append(f"· {who}{body}" if who else f"· {body}")
    return "\n".join(lines)

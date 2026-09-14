"""邮件系统：玩家之间互发猫头鹰信件，可以顺带捎带一份材料/物品。

物品名字→item_key 的解析顺序照抄 hp_school/shop.py 的 get_bag()：
先查对角巷商店目录（覆盖普通商店物品和烹饪材料），再查禁林魔药材料，最后查魔药。
"""

from __future__ import annotations

from plugins.hp_core import storage as core_storage
from plugins.hp_core.storage import get_conn

SCHEMA = """
CREATE TABLE IF NOT EXISTS letters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_uid TEXT NOT NULL,
    to_uid TEXT NOT NULL,
    content TEXT NOT NULL,
    item_key TEXT NOT NULL DEFAULT '',
    item_quantity INTEGER NOT NULL DEFAULT 0,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_letters_to ON letters(to_uid, created_at);

CREATE TABLE IF NOT EXISTS letter_daily (
    uid TEXT NOT NULL,
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, day)
);
"""

DAILY_LIMIT = 20
CONTENT_MAX_LEN = 500

# 系统邮件的发件人不是真实玩家uid，查players表查不到名字，这里手动兜底一个显示名。
SYSTEM_SENDERS = {
    "gossip_editor": "《女巫周刊》编辑部",
}


class MailError(Exception):
    pass


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


init_db()


def _require_enrolled(uid: str, who: str = "你") -> None:
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise MailError(f"{who}还没有分院，先发「/入学」完成入学测试。")


def _resolve_item(item_input: str) -> tuple[str, str]:
    """物品名/key -> (item_key, 展示名)，找不到返回 ("", "")。"""
    from plugins.hp_events import forest_catalog
    from plugins.hp_school import potions, shop_catalog

    item = shop_catalog.find(item_input)
    if item:
        return item[0], item[1]

    material = forest_catalog.MATERIALS_BY_KEY.get(item_input) or forest_catalog.MATERIALS_BY_NAME.get(
        item_input
    )
    if material:
        return material[0], material[1]

    potion_names_by_key = potions.POTION_ITEMS
    if item_input in potion_names_by_key:
        return item_input, potion_names_by_key[item_input]
    for key, name in potion_names_by_key.items():
        if name == item_input:
            return key, name
    return "", ""


def item_display_name(item_key: str) -> str:
    if not item_key:
        return ""
    _, name = _resolve_item(item_key)
    return name or item_key


def send(uid: str, target_uid: str, content: str, item_input: str = "", quantity: int = 0) -> dict:
    _require_enrolled(uid)
    if target_uid == uid:
        raise MailError("不能给自己寄信。")
    _require_enrolled(target_uid, "对方")

    content = content.strip()
    if not content:
        raise MailError("信里总得写点什么。")
    if len(content) > CONTENT_MAX_LEN:
        raise MailError(f"信写得太长了，最多{CONTENT_MAX_LEN}字。")

    item_key = ""
    item_name = ""
    if item_input.strip():
        if quantity < 1:
            raise MailError("捎带的数量至少是1。")
        item_key, item_name = _resolve_item(item_input.strip())
        if not item_key:
            raise MailError(f"找不到「{item_input.strip()}」这个东西。")
    else:
        quantity = 0

    day = core_storage.get_current_day() or 1
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT OR IGNORE INTO letter_daily (uid, day, count) VALUES (?, ?, 0)", (uid, day))
        today = conn.execute(
            "SELECT count FROM letter_daily WHERE uid = ? AND day = ?", (uid, day)
        ).fetchone()[0]
        if today >= DAILY_LIMIT:
            conn.rollback()
            raise MailError(f"你今天已经寄了{DAILY_LIMIT}封信了，猫头鹰也需要休息。")

        if item_key:
            removed = conn.execute(
                "UPDATE inventory SET quantity = quantity - ? WHERE uid = ? AND item_key = ? AND quantity >= ?",
                (quantity, uid, item_key, quantity),
            )
            if removed.rowcount == 0:
                conn.rollback()
                raise MailError(f"你没有{quantity}份「{item_name}」，捎不了。")
            conn.execute(
                "INSERT INTO inventory (uid, item_key, quantity) VALUES (?, ?, ?) "
                "ON CONFLICT(uid, item_key) DO UPDATE SET quantity = quantity + excluded.quantity",
                (target_uid, item_key, quantity),
            )

        conn.execute(
            "UPDATE letter_daily SET count = count + 1 WHERE uid = ? AND day = ?", (uid, day)
        )
        conn.execute(
            "INSERT INTO letters (from_uid, to_uid, content, item_key, item_quantity, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uid, target_uid, content, item_key, quantity, core_storage.now()),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "target_name": core_storage.get_full_name(target_uid),
        "item_name": item_name,
        "quantity": quantity,
    }


def send_system_mail(target_uid: str, content: str, sender_key: str = "gossip_editor") -> None:
    """系统邮件（比如八卦小报退稿通知），不是玩家寄的，不走每日上限/物品校验那一套。"""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO letters (from_uid, to_uid, content, created_at) VALUES (?, ?, ?, ?)",
            (sender_key, target_uid, content, core_storage.now()),
        )
        conn.commit()
    finally:
        conn.close()


def _sender_name(from_uid: str) -> str:
    return SYSTEM_SENDERS.get(from_uid) or core_storage.get_full_name(from_uid)


def inbox(uid: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM letters WHERE to_uid = ? ORDER BY created_at DESC", (uid,)
        ).fetchall()
        unread_ids = [r["id"] for r in rows if not r["is_read"]]
        if unread_ids:
            conn.executemany("UPDATE letters SET is_read = 1 WHERE id = ?", [(i,) for i in unread_ids])
            conn.commit()
    finally:
        conn.close()

    result = []
    for r in rows:
        result.append(
            {
                "from_name": _sender_name(r["from_uid"]),
                "content": r["content"],
                "item_name": item_display_name(r["item_key"]) if r["item_key"] else "",
                "item_quantity": r["item_quantity"],
                "created_at": r["created_at"],
                "was_unread": r["id"] in unread_ids,
            }
        )
    return result

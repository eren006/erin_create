import math
import time

from plugins.changri_core.api import get_primary_uid, get_setting, get_setting_int, set_setting

from .storage import get_conn, init_db

init_db()

TYPE_PREFIX = {"item": "ITEM", "interact": "INTER", "currency": "CUR", "preset": "SPEC"}

PRESET_ITEMS = [
    ("SPEC_001", "追踪器", "可以查询目标近期动向", "preset"),
    ("SPEC_002", "万能钥匙", "可以打开任意上锁的地点", "preset"),
    ("SPEC_003", "望远镜", "可以远距离观察", "preset"),
    ("SPEC_004", "羽毛笔", "书写心动信必备", "preset"),
    ("SPEC_005", "捕鼠器", "捕捉可疑的小动物", "preset"),
    ("SPEC_006", "窃听器", "偷听目标的对话", "preset"),
    ("SPEC_007", "截信器", "拦截目标收到的信件", "preset"),
    ("SPEC_008", "回音壁", "让消息传得更远", "preset"),
]
PRESET_CURRENCIES = [("CUR_GOLD", "金币"), ("CUR_SILVER", "银币")]


# ── 物品注册表 ──────────────────────────────────────────────────────────────


def _next_item_code(platform: str, type_: str) -> str:
    prefix = TYPE_PREFIX[type_]
    seq_key = f"item_code_seq:{platform}:{type_}"
    seq = get_setting_int(seq_key, 0) + 1
    set_setting(seq_key, str(seq))
    return f"{prefix}_{seq:03d}"


def add_item(
    platform: str,
    name: str,
    desc: str,
    type_: str,
    code: str | None = None,
    max_uses: int | None = None,
    can_resell: bool = True,
) -> str:
    if code is None:
        code = _next_item_code(platform, type_)
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO items (platform, code, name, desc, type, max_uses, can_resell)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (platform, code) DO UPDATE SET
                name = excluded.name, desc = excluded.desc, type = excluded.type,
                max_uses = excluded.max_uses, can_resell = excluded.can_resell
            """,
            (platform, code, name, desc, type_, max_uses, int(can_resell)),
        )
        conn.commit()
        return code
    finally:
        conn.close()


def get_item(platform: str, code: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM items WHERE platform = ? AND code = ?", (platform, code)
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def find_item_by_name(platform: str, name: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM items WHERE platform = ? AND name = ?", (platform, name)
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def list_items(platform: str, type_: str | None = None) -> list[dict]:
    conn = get_conn()
    try:
        if type_ is None:
            rows = conn.execute(
                "SELECT * FROM items WHERE platform = ? ORDER BY code", (platform,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM items WHERE platform = ? AND type = ? ORDER BY code",
                (platform, type_),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def init_preset_items(platform: str) -> None:
    for code, name, desc, type_ in PRESET_ITEMS:
        add_item(platform, name, desc, type_, code=code, can_resell=False)
    for code, name in PRESET_CURRENCIES:
        add_item(platform, name, "", "currency", code=code, can_resell=False)


# ── 背包 ──────────────────────────────────────────────────────────────


def add_to_inventory(
    platform: str,
    uid: str,
    code: str,
    count: int,
    remaining_uses: int | None = None,
    current_durability: int | None = None,
    expires_at: int | None = None,
) -> None:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT id FROM inventory_stacks
            WHERE platform = ? AND uid = ? AND code = ?
              AND remaining_uses IS ? AND current_durability IS ? AND expires_at IS ?
            """,
            (platform, uid, code, remaining_uses, current_durability, expires_at),
        ).fetchone()
        if row is not None:
            conn.execute(
                "UPDATE inventory_stacks SET count = count + ? WHERE id = ?", (count, row["id"])
            )
        else:
            conn.execute(
                """
                INSERT INTO inventory_stacks (platform, uid, code, count, remaining_uses, current_durability, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (platform, uid, code, count, remaining_uses, current_durability, expires_at),
            )
        conn.commit()
    finally:
        conn.close()


def get_inventory(platform: str, uid: str) -> list[dict]:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT s.*, i.name, i.desc, i.type
            FROM inventory_stacks s JOIN items i ON i.platform = s.platform AND i.code = s.code
            WHERE s.platform = ? AND s.uid = ? AND s.count > 0
            ORDER BY s.id
            """,
            (platform, uid),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def remove_expired_items(platform: str) -> list[dict]:
    """清理已过期的道具堆叠，返回被清理的记录（含owner/物品名，供调用方决定要不要通知）。"""
    now = int(time.time())
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT s.*, i.name FROM inventory_stacks s
            JOIN items i ON i.platform = s.platform AND i.code = s.code
            WHERE s.platform = ? AND s.expires_at IS NOT NULL AND s.expires_at <= ? AND s.count > 0
            """,
            (platform, now),
        ).fetchall()
        expired = [dict(r) for r in rows]
        if expired:
            conn.executemany(
                "UPDATE inventory_stacks SET count = 0 WHERE id = ?", [(r["id"],) for r in expired]
            )
            conn.commit()
        return expired
    finally:
        conn.close()


def get_item_count(platform: str, uid: str, code: str) -> int:
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(count), 0) AS total FROM inventory_stacks WHERE platform = ? AND uid = ? AND code = ?",
            (platform, uid, code),
        ).fetchone()
        return row["total"]
    finally:
        conn.close()


def remove_from_inventory(platform: str, uid: str, code: str, count: int) -> bool:
    """按堆叠顺序扣减，不足则整体失败（不做部分扣减）。"""
    uid = get_primary_uid(platform, uid)
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, count FROM inventory_stacks WHERE platform = ? AND uid = ? AND code = ? AND count > 0 ORDER BY id",
            (platform, uid, code),
        ).fetchall()
        total = sum(r["count"] for r in rows)
        if total < count:
            return False
        remaining = count
        for r in rows:
            if remaining <= 0:
                break
            take = min(r["count"], remaining)
            conn.execute(
                "UPDATE inventory_stacks SET count = count - ? WHERE id = ?", (take, r["id"])
            )
            remaining -= take
        conn.commit()
        return True
    finally:
        conn.close()


def transfer_item(platform: str, from_uid: str, to_uid: str, code: str, count: int) -> bool:
    if not remove_from_inventory(platform, from_uid, code, count):
        return False
    add_to_inventory(platform, to_uid, code, count)
    return True


# ── 商店 ──────────────────────────────────────────────────────────────


def add_shop_listing(platform: str, code: str, price: int, currency_code: str, currency_name: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO shop_listings (platform, code, price, currency_code, currency_name)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (platform, code) DO UPDATE SET
                price = excluded.price, currency_code = excluded.currency_code, currency_name = excluded.currency_name
            """,
            (platform, code, price, currency_code, currency_name),
        )
        conn.commit()
    finally:
        conn.close()


def remove_shop_listing(platform: str, code: str) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM shop_listings WHERE platform = ? AND code = ?", (platform, code)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_shop(platform: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT s.*, i.name, i.desc FROM shop_listings s
            JOIN items i ON i.platform = s.platform AND i.code = s.code
            WHERE s.platform = ? ORDER BY s.code
            """,
            (platform,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def buy_from_shop(platform: str, uid: str, code: str, count: int = 1) -> tuple[bool, str]:
    conn = get_conn()
    try:
        listing = conn.execute(
            "SELECT * FROM shop_listings WHERE platform = ? AND code = ?", (platform, code)
        ).fetchone()
    finally:
        conn.close()
    if listing is None:
        return False, "商城里没有这个物品"
    total_price = listing["price"] * count
    if get_item_count(platform, uid, listing["currency_code"]) < total_price:
        return False, f"{listing['currency_name']}不够，需要 {total_price}"
    remove_from_inventory(platform, uid, listing["currency_code"], total_price)
    add_to_inventory(platform, uid, code, count)
    return True, "购买成功"


# ── 二手市场 ──────────────────────────────────────────────────────────────


def get_market_config() -> dict:
    return {
        "enabled": get_setting("market_enabled", "1") == "1",
        "fee_rate": float(get_setting("market_fee_rate", "0.05") or "0.05"),
    }


def set_market_config(enabled: bool | None = None, fee_rate: float | None = None) -> None:
    if enabled is not None:
        set_setting("market_enabled", "1" if enabled else "0")
    if fee_rate is not None:
        set_setting("market_fee_rate", str(fee_rate))


def create_market_listing(
    platform: str, seller_uid: str, code: str, count: int, price: int, currency_code: str, currency_name: str
) -> tuple[bool, str, int | None]:
    seller_uid = get_primary_uid(platform, seller_uid)
    item = get_item(platform, code)
    if item is None:
        return False, "没有这个物品", None
    if not item["can_resell"]:
        return False, "这个物品不能转卖", None
    if not remove_from_inventory(platform, seller_uid, code, count):
        return False, "背包里没有这么多", None
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO market_listings (platform, seller_uid, code, count, price, currency_code, currency_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (platform, seller_uid, code, count, price, currency_code, currency_name, int(time.time())),
        )
        conn.commit()
        return True, "挂售成功", cur.lastrowid
    finally:
        conn.close()


def list_market(platform: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT m.*, i.name, i.desc FROM market_listings m
            JOIN items i ON i.platform = m.platform AND i.code = m.code
            WHERE m.platform = ? ORDER BY m.id
            """,
            (platform,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def cancel_market_listing(platform: str, seller_uid: str, market_id: int) -> tuple[bool, str]:
    seller_uid = get_primary_uid(platform, seller_uid)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM market_listings WHERE id = ? AND platform = ?", (market_id, platform)
        ).fetchone()
        if row is None:
            return False, "找不到这个挂单"
        if row["seller_uid"] != seller_uid:
            return False, "这不是你的挂单"
        conn.execute("DELETE FROM market_listings WHERE id = ?", (market_id,))
        conn.commit()
    finally:
        conn.close()
    add_to_inventory(platform, seller_uid, row["code"], row["count"], row["remaining_uses"], row["current_durability"])
    return True, "已撤销，物品已退回背包"


def buy_market_listing(platform: str, buyer_uid: str, market_id: int) -> tuple[bool, str]:
    buyer_uid = get_primary_uid(platform, buyer_uid)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM market_listings WHERE id = ? AND platform = ?", (market_id, platform)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return False, "找不到这个挂单"
    if row["seller_uid"] == buyer_uid:
        return False, "不能购买自己的挂单"
    config = get_market_config()
    fee = math.ceil(row["price"] * config["fee_rate"])
    total = row["price"] + fee
    if get_item_count(platform, buyer_uid, row["currency_code"]) < total:
        return False, f"{row['currency_name']}不够，需要 {total}（含手续费 {fee}）"
    if not remove_from_inventory(platform, buyer_uid, row["currency_code"], total):
        return False, "扣款失败"
    add_to_inventory(platform, row["seller_uid"], row["currency_code"], row["price"])
    add_to_inventory(
        platform, buyer_uid, row["code"], row["count"], row["remaining_uses"], row["current_durability"]
    )
    conn = get_conn()
    try:
        conn.execute("DELETE FROM market_listings WHERE id = ?", (market_id,))
        conn.commit()
    finally:
        conn.close()
    return True, "购买成功"

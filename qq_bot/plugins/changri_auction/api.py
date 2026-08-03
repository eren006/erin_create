import time

from plugins.changri_core.api import get_primary_uid, get_role_name
from plugins.changri_rpg.api import add_to_inventory, get_item, get_item_count, remove_from_inventory

from .storage import get_conn, init_db

init_db()

MAX_CONCURRENT_AUCTIONS = 10


def count_active_auctions(platform: str) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM auctions WHERE platform = ? AND status = 'active'",
            (platform,),
        ).fetchone()
        return row["c"]
    finally:
        conn.close()


def add_auction(
    platform: str,
    code: str,
    start_price: int,
    min_increment: int,
    duration_hours: float,
    currency_code: str,
    currency_name: str,
    expire_hours: float | None = None,
) -> tuple[bool, str, int | None]:
    if get_item(platform, code) is None:
        return False, "没有这个物品", None
    if count_active_auctions(platform) >= MAX_CONCURRENT_AUCTIONS:
        return False, f"同时进行的拍卖不能超过 {MAX_CONCURRENT_AUCTIONS} 个", None
    now = int(time.time())
    end_time = now + int(duration_hours * 3600)
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO auctions (platform, code, start_price, min_increment, currency_code, currency_name, start_time, end_time, status, expire_hours)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
            """,
            (platform, code, start_price, min_increment, currency_code, currency_name, now, end_time, expire_hours),
        )
        conn.commit()
        return True, "拍卖已创建", cur.lastrowid
    finally:
        conn.close()


def remove_auction(platform: str, auction_id: int) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM auctions WHERE id = ? AND platform = ?", (auction_id, platform)
        )
        conn.execute("DELETE FROM auction_bids WHERE auction_id = ?", (auction_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_auction(platform: str, auction_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM auctions WHERE id = ? AND platform = ?", (auction_id, platform)
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def list_active_auctions(platform: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM auctions WHERE platform = ? AND status = 'active' ORDER BY id",
            (platform,),
        ).fetchall()
        auctions = []
        for row in rows:
            a = dict(row)
            item = get_item(platform, a["code"])
            a["name"] = item["name"] if item else a["code"]
            a["top_bid"] = get_top_bid(platform, a["id"])
            auctions.append(a)
        return auctions
    finally:
        conn.close()


def get_top_bid(platform: str, auction_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM auction_bids WHERE auction_id = ? ORDER BY amount DESC, bid_time ASC LIMIT 1",
            (auction_id,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def place_bid(platform: str, uid: str, auction_id: int, amount: int, is_anon: bool) -> tuple[bool, str]:
    uid = get_primary_uid(platform, uid)
    if get_role_name(platform, uid) is None:
        return False, "你还没有角色，先创建新角色"
    settle_expired_auctions(platform)
    auction = get_auction(platform, auction_id)
    if auction is None or auction["status"] != "active":
        return False, "这个拍卖不存在或已结束"
    top_bid = get_top_bid(platform, auction_id)
    min_valid = (top_bid["amount"] + auction["min_increment"]) if top_bid else auction["start_price"]
    if amount < min_valid:
        return False, f"出价至少要 {min_valid}"
    if get_item_count(platform, uid, auction["currency_code"]) < amount:
        return False, f"{auction['currency_name']}不够"
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO auction_bids (auction_id, uid, amount, is_anon, bid_time) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (auction_id, uid) DO UPDATE SET amount = excluded.amount, is_anon = excluded.is_anon, bid_time = excluded.bid_time
            """,
            (auction_id, uid, amount, int(is_anon), int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()
    return True, "出价成功"


def _settle_single(platform: str, auction: dict) -> str:
    conn = get_conn()
    try:
        bids = conn.execute(
            "SELECT * FROM auction_bids WHERE auction_id = ? ORDER BY amount DESC, bid_time ASC",
            (auction["id"],),
        ).fetchall()
    finally:
        conn.close()
    item = get_item(platform, auction["code"])
    item_name = item["name"] if item else auction["code"]
    winner = None
    for bid in bids:
        if get_item_count(platform, bid["uid"], auction["currency_code"]) >= bid["amount"]:
            winner = bid
            break
    conn = get_conn()
    try:
        if winner is None:
            conn.execute("UPDATE auctions SET status = 'unsold' WHERE id = ?", (auction["id"],))
            conn.commit()
            return f"拍卖「{item_name}」流拍，无人出价或出价者余额不足"
        conn.execute(
            "UPDATE auctions SET status = 'sold', winner_uid = ? WHERE id = ?",
            (winner["uid"], auction["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    remove_from_inventory(platform, winner["uid"], auction["currency_code"], winner["amount"])
    expires_at = int(time.time() + auction["expire_hours"] * 3600) if auction["expire_hours"] else None
    add_to_inventory(platform, winner["uid"], auction["code"], 1, expires_at=expires_at)
    winner_role = get_role_name(platform, winner["uid"]) or "未知"
    expire_msg = f"，{auction['expire_hours']}小时后失效" if auction["expire_hours"] else ""
    return f"拍卖「{item_name}」成交，得主：{winner_role}，成交价 {winner['amount']} {auction['currency_name']}{expire_msg}"


def settle_expired_auctions(platform: str) -> list[str]:
    now = int(time.time())
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM auctions WHERE platform = ? AND status = 'active' AND end_time <= ?",
            (platform, now),
        ).fetchall()
    finally:
        conn.close()
    return [_settle_single(platform, dict(row)) for row in rows]


def force_settle(platform: str, auction_id: int) -> tuple[bool, str]:
    auction = get_auction(platform, auction_id)
    if auction is None or auction["status"] != "active":
        return False, "这个拍卖不存在或已结束"
    return True, _settle_single(platform, auction)

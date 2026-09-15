import os, json, re, secrets, time, logging, traceback, shutil, threading
from datetime import datetime
from functools import wraps
from flask import (Flask, render_template, request, redirect,
                   url_for, session, g, abort, flash, jsonify,
                   send_from_directory)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "yuca_order_secret_change_me_in_prod")

_log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_log_dir, exist_ok=True)
_h = logging.FileHandler(os.path.join(_log_dir, "error.log"), encoding="utf-8")
_h.setLevel(logging.ERROR)
_h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s]\n%(message)s\n" + "-"*60))
_logger = logging.getLogger("yuca_order")
_logger.setLevel(logging.ERROR)
_logger.addHandler(_h)

DB_PATH         = os.path.join(os.path.dirname(__file__), "order_data.db")
UPLOAD_DIR      = os.path.join(os.path.dirname(__file__), "uploads")
SUPERADMIN_PASS = os.environ.get("SUPERADMIN_PASS", "order_super_2025")
ALLOWED_EXT     = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_IMAGES      = 10

os.makedirs(UPLOAD_DIR, exist_ok=True)

DEFAULT_SERVICE_TYPES = ["约稿", "排期", "接剧本", "指南定制", "其他"]

STATUS_LABEL = {
    'pending':    '待处理',
    'accepted':   '已接单',
    'processing': '制作中',
    'completed':  '已完成',
    'rejected':   '已拒绝',
    'cancelled':  '已取消',
}
STATUS_COLOR = {
    'pending':    '#fbbf24',
    'accepted':   '#60a5fa',
    'processing': '#a78bfa',
    'completed':  '#86efac',
    'rejected':   '#f87171',
    'cancelled':  '#7878a0',
}
ALL_STATUSES = list(STATUS_LABEL.keys())

# 补充备注：订单被接下之后，客户和接单方都可以往同一条时间线上追加文字说明。
# 与 orders.admin_notes（内部备注，客户不可见）不同，这里的内容双方都能看到。
ORDER_NOTE_MAX_LEN      = 500   # 单条字数上限
ORDER_NOTE_MAX_CUSTOMER = 10    # 客户每单最多追加条数（防刷；接单方不限）
ORDER_NOTE_STATUSES     = ('accepted', 'processing')  # 只有已接单/制作中可以追加


# ── DB ────────────────────────────────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db

@app.teardown_appcontext
def close_db(e):
    db = g.pop('db', None)
    if db: db.close()

def _col(conn, table):
    try: return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    except: return set()

def _migrate(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS tenants (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        slug          TEXT UNIQUE NOT NULL,
        display_name  TEXT NOT NULL DEFAULT '',
        description   TEXT NOT NULL DEFAULT '',
        service_types TEXT NOT NULL DEFAULT '[]',
        api_token     TEXT UNIQUE NOT NULL,
        is_active     INTEGER NOT NULL DEFAULT 1,
        created_at    INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS tenant_admins (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id     INTEGER NOT NULL REFERENCES tenants(id),
        username      TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        display_name  TEXT NOT NULL DEFAULT '',
        is_active     INTEGER NOT NULL DEFAULT 1,
        created_at    INTEGER NOT NULL,
        UNIQUE(tenant_id, username)
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id     INTEGER NOT NULL REFERENCES tenants(id),
        username      TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        display_name  TEXT NOT NULL DEFAULT '',
        contact       TEXT NOT NULL DEFAULT '',
        is_active     INTEGER NOT NULL DEFAULT 1,
        created_at    INTEGER NOT NULL,
        UNIQUE(tenant_id, username)
    )''')

    # 全站统一登录账号：一个账号可以在多个创作者(tenant)下各有一份 users 会员行，
    # 次数/订单/交易都挂在各自那份 users.id 上，天然按创作者分开，不会互通。
    conn.execute('''CREATE TABLE IF NOT EXISTS accounts (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        username      TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        display_name  TEXT NOT NULL DEFAULT '',
        contact       TEXT NOT NULL DEFAULT '',
        is_active     INTEGER NOT NULL DEFAULT 1,
        created_at    INTEGER NOT NULL
    )''')
    if 'account_id' not in _col(conn, 'users'):
        conn.execute("ALTER TABLE users ADD COLUMN account_id INTEGER REFERENCES accounts(id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_account ON users(account_id)")
    # 回填：老 users 行还没关联 account 的，按用户名找/建一个全局账号
    for u in conn.execute("SELECT * FROM users WHERE account_id IS NULL").fetchall():
        acct = conn.execute("SELECT id FROM accounts WHERE username=?", (u['username'],)).fetchone()
        if acct:
            acct_id = acct[0]
        else:
            conn.execute('''INSERT INTO accounts (username,password_hash,display_name,contact,is_active,created_at)
                            VALUES (?,?,?,?,?,?)''',
                         (u['username'], u['password_hash'], u['display_name'], u['contact'], u['is_active'], u['created_at']))
            acct_id = conn.execute("SELECT id FROM accounts WHERE username=?", (u['username'],)).fetchone()[0]
        conn.execute("UPDATE users SET account_id=? WHERE id=?", (acct_id, u['id']))
    conn.execute('''CREATE TABLE IF NOT EXISTS credit_requests (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id    INTEGER NOT NULL REFERENCES tenants(id),
        user_id      INTEGER NOT NULL REFERENCES users(id),
        units        INTEGER NOT NULL DEFAULT 1,
        status       TEXT NOT NULL DEFAULT 'pending',
        note         TEXT NOT NULL DEFAULT '',
        admin_note   TEXT NOT NULL DEFAULT '',
        decided_by   INTEGER REFERENCES tenant_admins(id),
        decided_at   INTEGER,
        created_at   INTEGER NOT NULL
    )''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_credit_req_user   ON credit_requests(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_credit_req_status ON credit_requests(tenant_id, status)")
    conn.execute('''CREATE TABLE IF NOT EXISTS redeem_codes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id   INTEGER NOT NULL REFERENCES tenants(id),
        code        TEXT UNIQUE NOT NULL,
        units       INTEGER NOT NULL,
        batch_id    TEXT NOT NULL DEFAULT '',
        batch_note  TEXT NOT NULL DEFAULT '',
        status      TEXT NOT NULL DEFAULT 'unused',
        redeemed_by INTEGER REFERENCES users(id),
        redeemed_at INTEGER,
        created_by  INTEGER REFERENCES tenant_admins(id),
        created_at  INTEGER NOT NULL
    )''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_redeem_tenant ON redeem_codes(tenant_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_redeem_batch  ON redeem_codes(batch_id)")
    if 'valid_days' not in _col(conn, 'redeem_codes'):
        conn.execute("ALTER TABLE redeem_codes ADD COLUMN valid_days INTEGER")
    if 'fixed_expires_at' not in _col(conn, 'redeem_codes'):
        conn.execute("ALTER TABLE redeem_codes ADD COLUMN fixed_expires_at INTEGER")

    # 下单次数批次（每批可以有自己的有效期；下单优先消耗最快过期的批次）
    conn.execute('''CREATE TABLE IF NOT EXISTS credit_batches (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id     INTEGER NOT NULL REFERENCES tenants(id),
        user_id       INTEGER NOT NULL REFERENCES users(id),
        units_total   INTEGER NOT NULL,
        units_left    INTEGER NOT NULL,
        source        TEXT NOT NULL DEFAULT '',
        source_id     INTEGER,
        expires_at    INTEGER,
        reminded_days TEXT NOT NULL DEFAULT '',
        status        TEXT NOT NULL DEFAULT 'active',
        created_at    INTEGER NOT NULL
    )''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_credit_batches_user ON credit_batches(user_id, status)")

    # 用户站内信 / 回执
    conn.execute('''CREATE TABLE IF NOT EXISTS inbox_messages (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id   INTEGER NOT NULL REFERENCES tenants(id),
        user_id     INTEGER NOT NULL REFERENCES users(id),
        kind        TEXT NOT NULL DEFAULT '',
        content     TEXT NOT NULL DEFAULT '',
        order_no    TEXT NOT NULL DEFAULT '',
        is_read     INTEGER NOT NULL DEFAULT 0,
        created_at  INTEGER NOT NULL
    )''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_inbox_user ON inbox_messages(user_id, is_read)")

    # 次数交易大厅
    conn.execute('''CREATE TABLE IF NOT EXISTS trade_listings (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id        INTEGER NOT NULL REFERENCES tenants(id),
        poster_id        INTEGER NOT NULL REFERENCES users(id),
        kind             TEXT NOT NULL,
        offer_batch_id   INTEGER NOT NULL REFERENCES credit_batches(id),
        offer_units      INTEGER NOT NULL,
        offer_expires_at INTEGER,
        want_units       INTEGER,
        note             TEXT NOT NULL DEFAULT '',
        status           TEXT NOT NULL DEFAULT 'open',
        created_at       INTEGER NOT NULL
    )''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_listings_tenant ON trade_listings(tenant_id, status)")

    conn.execute('''CREATE TABLE IF NOT EXISTS trades (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id         INTEGER NOT NULL REFERENCES tenants(id),
        listing_id        INTEGER NOT NULL REFERENCES trade_listings(id),
        kind              TEXT NOT NULL,
        poster_id         INTEGER NOT NULL REFERENCES users(id),
        taker_id          INTEGER NOT NULL REFERENCES users(id),
        offer_units       INTEGER NOT NULL,
        offer_batch_id    INTEGER,
        offer_expires_at  INTEGER,
        want_units        INTEGER,
        note              TEXT NOT NULL DEFAULT '',
        status            TEXT NOT NULL DEFAULT 'pending',
        result_batch_to_taker  INTEGER,
        result_batch_to_poster INTEGER,
        dispute_status    TEXT NOT NULL DEFAULT '',
        dispute_by        INTEGER,
        dispute_note      TEXT NOT NULL DEFAULT '',
        disputed_batch_id INTEGER,
        dispute_at        INTEGER,
        created_at        INTEGER NOT NULL,
        updated_at        INTEGER NOT NULL
    )''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_tenant ON trades(tenant_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_dispute ON trades(dispute_status)")
    conn.execute('''CREATE TABLE IF NOT EXISTS orders (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        order_no         TEXT UNIQUE NOT NULL,
        tenant_id        INTEGER NOT NULL REFERENCES tenants(id),
        user_id          INTEGER REFERENCES users(id),
        customer_name    TEXT NOT NULL DEFAULT '',
        customer_contact TEXT NOT NULL DEFAULT '',
        service_type     TEXT NOT NULL DEFAULT '',
        title            TEXT NOT NULL DEFAULT '',
        description      TEXT NOT NULL DEFAULT '',
        status           TEXT NOT NULL DEFAULT 'pending',
        admin_notes      TEXT NOT NULL DEFAULT '',
        result_text      TEXT NOT NULL DEFAULT '',
        verify_code      TEXT NOT NULL DEFAULT '',
        assigned_admin   INTEGER REFERENCES tenant_admins(id),
        created_at       INTEGER NOT NULL,
        updated_at       INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS order_images (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id      INTEGER NOT NULL REFERENCES orders(id),
        filename      TEXT NOT NULL,
        original_name TEXT NOT NULL DEFAULT '',
        uploaded_at   INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS order_result_images (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id      INTEGER NOT NULL REFERENCES orders(id),
        filename      TEXT NOT NULL,
        original_name TEXT NOT NULL DEFAULT '',
        uploaded_at   INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS order_notes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id    INTEGER NOT NULL REFERENCES orders(id),
        author_type TEXT NOT NULL DEFAULT 'customer',
        author_name TEXT NOT NULL DEFAULT '',
        content     TEXT NOT NULL DEFAULT '',
        created_at  INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS order_logs (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id   INTEGER NOT NULL REFERENCES orders(id),
        action     TEXT NOT NULL,
        actor      TEXT NOT NULL DEFAULT '',
        note       TEXT NOT NULL DEFAULT '',
        created_at INTEGER NOT NULL
    )''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_tenant ON orders(tenant_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_user   ON orders(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_no     ON orders(order_no)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_order    ON order_logs(order_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_order_notes   ON order_notes(order_id)")
    # 客户追加的备注，接单方看过没有（用来在订单列表上提醒）
    if 'seen_by_admin' not in _col(conn, 'order_notes'):
        conn.execute("ALTER TABLE order_notes ADD COLUMN seen_by_admin INTEGER NOT NULL DEFAULT 0")
    # tenants.credit_need_approval 已废弃：审批开关改成每个单口独立，见 credit_pools.need_approval
    # 散单开关 & 数量上限
    if 'orders_open' not in _col(conn, 'tenants'):
        conn.execute("ALTER TABLE tenants ADD COLUMN orders_open INTEGER NOT NULL DEFAULT 1")
    if 'max_active_orders' not in _col(conn, 'tenants'):
        conn.execute("ALTER TABLE tenants ADD COLUMN max_active_orders INTEGER NOT NULL DEFAULT 0")
    if 'order_form_schema' not in _col(conn, 'tenants'):
        conn.execute("ALTER TABLE tenants ADD COLUMN order_form_schema TEXT NOT NULL DEFAULT ''")
    if 'contact_qq' not in _col(conn, 'tenants'):
        conn.execute("ALTER TABLE tenants ADD COLUMN contact_qq TEXT NOT NULL DEFAULT ''")
    # 下单次数（购买 → 审批 → 累积到账号）
    if 'credit_balance' not in _col(conn, 'users'):
        conn.execute("ALTER TABLE users ADD COLUMN credit_balance INTEGER NOT NULL DEFAULT 0")
    if 'credit_total' not in _col(conn, 'users'):
        conn.execute("ALTER TABLE users ADD COLUMN credit_total INTEGER NOT NULL DEFAULT 0")
    if 'credit_consumed' not in _col(conn, 'orders'):
        conn.execute("ALTER TABLE orders ADD COLUMN credit_consumed INTEGER NOT NULL DEFAULT 0")
    if 'credit_batch_id' not in _col(conn, 'orders'):
        conn.execute("ALTER TABLE orders ADD COLUMN credit_batch_id INTEGER REFERENCES credit_batches(id)")
    # bot 同步标记
    if 'bot_notified' not in _col(conn, 'orders'):
        conn.execute("ALTER TABLE orders ADD COLUMN bot_notified INTEGER NOT NULL DEFAULT 0")
    # 加急 & 催单
    if 'is_urgent' not in _col(conn, 'orders'):
        conn.execute("ALTER TABLE orders ADD COLUMN is_urgent INTEGER NOT NULL DEFAULT 0")
    if 'rush_count' not in _col(conn, 'orders'):
        conn.execute("ALTER TABLE orders ADD COLUMN rush_count INTEGER NOT NULL DEFAULT 0")
    # bot 快照存储（排单宝.js push 过来的数据）
    conn.execute('''CREATE TABLE IF NOT EXISTS bot_snapshot (
        key        TEXT PRIMARY KEY,
        data       TEXT NOT NULL,
        updated_at INTEGER NOT NULL
    )''')
    # bot 注册用户 / 卡系统
    conn.execute('''CREATE TABLE IF NOT EXISTS bot_users (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id      INTEGER NOT NULL REFERENCES tenants(id),
        platform_uid   TEXT NOT NULL,
        display_name   TEXT NOT NULL DEFAULT '',
        card_total     INTEGER NOT NULL DEFAULT 0,
        card_remaining INTEGER NOT NULL DEFAULT 0,
        notes          TEXT NOT NULL DEFAULT '',
        created_at     INTEGER NOT NULL,
        updated_at     INTEGER NOT NULL,
        UNIQUE(tenant_id, platform_uid)
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS invite_codes (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id    INTEGER NOT NULL REFERENCES tenants(id),
        code         TEXT UNIQUE NOT NULL,
        platform_uid TEXT NOT NULL DEFAULT '',
        display_name TEXT NOT NULL DEFAULT '',
        used         INTEGER NOT NULL DEFAULT 0,
        used_at      INTEGER,
        created_at   INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS announcements (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id  INTEGER NOT NULL REFERENCES tenants(id),
        content    TEXT NOT NULL DEFAULT '',
        created_by TEXT NOT NULL DEFAULT '',
        created_at INTEGER NOT NULL
    )''')
    if 'is_deleted' not in _col(conn, 'bot_users'):
        conn.execute("ALTER TABLE bot_users ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0")
    if 'deleted_at' not in _col(conn, 'bot_users'):
        conn.execute("ALTER TABLE bot_users ADD COLUMN deleted_at INTEGER")

    # 单口信息（旧称社区次数池）：管理员放出一批次数，会员点击方块领取。
    # 开着「领取需要审批」时领取先是 pending，管理员批准才到账，拒绝则名额放回池子；关掉时抢到直接到账。
    conn.execute('''CREATE TABLE IF NOT EXISTS credit_pools (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id        INTEGER NOT NULL REFERENCES tenants(id),
        title            TEXT NOT NULL DEFAULT '',
        total_units      INTEGER NOT NULL,
        valid_days       INTEGER,
        fixed_expires_at INTEGER,
        status           TEXT NOT NULL DEFAULT 'active',
        created_by       TEXT NOT NULL DEFAULT '',
        created_at       INTEGER NOT NULL
    )''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_credit_pools_tenant ON credit_pools(tenant_id, status)")
    # 这一批单口的领取是否需要人工审批（0 = 抢到直接到账，跳过审批）
    if 'need_approval' not in _col(conn, 'credit_pools'):
        conn.execute("ALTER TABLE credit_pools ADD COLUMN need_approval INTEGER NOT NULL DEFAULT 1")
    if 'pool_id' not in _col(conn, 'credit_requests'):
        conn.execute("ALTER TABLE credit_requests ADD COLUMN pool_id INTEGER REFERENCES credit_pools(id)")
    # 次数池里的面值档（比如 3 张 5 次卡 + 1 张 3 次卡，同一批放出，有效期跟着 credit_pools 走）
    conn.execute('''CREATE TABLE IF NOT EXISTS credit_pool_denoms (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        pool_id     INTEGER NOT NULL REFERENCES credit_pools(id),
        units       INTEGER NOT NULL,
        count       INTEGER NOT NULL,
        created_at  INTEGER NOT NULL
    )''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pool_denoms_pool ON credit_pool_denoms(pool_id)")
    if 'pool_denom_id' not in _col(conn, 'credit_requests'):
        conn.execute("ALTER TABLE credit_requests ADD COLUMN pool_denom_id INTEGER REFERENCES credit_pool_denoms(id)")
    # 创作者主页：简介 + 规则
    if 'intro' not in _col(conn, 'tenants'):
        conn.execute("ALTER TABLE tenants ADD COLUMN intro TEXT NOT NULL DEFAULT ''")
    if 'rules' not in _col(conn, 'tenants'):
        conn.execute("ALTER TABLE tenants ADD COLUMN rules TEXT NOT NULL DEFAULT ''")
    conn.commit()

# Startup migration
def _startup():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        _migrate(conn)
    except Exception as e:
        print(f"[yuca_order] migrate warning: {e}")
    finally:
        conn.close()

_startup()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now():
    return int(time.time())

def _fmt(ts):
    if not ts: return ''
    try: return datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M')
    except: return ''

def _gen_order_no():
    return "ORD-" + datetime.now().strftime('%Y%m%d') + "-" + secrets.token_hex(3).upper()

def _gen_verify():
    return secrets.token_hex(3).upper()

def _gen_redeem_code(db):
    while True:
        code = "GIFT-" + secrets.token_hex(4).upper()
        if not db.execute("SELECT 1 FROM redeem_codes WHERE code=?", (code,)).fetchone():
            return code


# ── 下单次数批次（有效期）────────────────────────────────────────────────────

def _inbox_add(db, tenant_id, user_id, kind, content, order_no=''):
    db.execute('''INSERT INTO inbox_messages (tenant_id,user_id,kind,content,order_no,is_read,created_at)
                  VALUES (?,?,?,?,?,0,?)''',
               (tenant_id, user_id, kind, content, order_no, _now()))

CREDIT_LOCK_SECONDS = 86400  # 交易大厅换来的次数需满 24 小时冷却期才能下单/再次挂单；兑换码/审批通过等直接获得的次数没有这个限制
CREDIT_LOCK_SOURCES = ('trade', 'trade_reversal')  # 只有这两种来源（交易大厅换到的、仲裁转回的）才受冷却期限制

def _credit_batches_for_user(db, user_id, only_available=True):
    now = _now()
    if only_available:
        rows = db.execute(
            "SELECT * FROM credit_batches WHERE user_id=? AND status='active' AND units_left>0 "
            "AND (expires_at IS NULL OR expires_at>?) "
            "AND (source NOT IN ('trade','trade_reversal') OR created_at<=?) "
            "ORDER BY (expires_at IS NULL) ASC, expires_at ASC",
            (user_id, now, now - CREDIT_LOCK_SECONDS)).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM credit_batches WHERE user_id=? AND status='active' AND units_left>0 "
            "AND (expires_at IS NULL OR expires_at>?) "
            "ORDER BY (expires_at IS NULL) ASC, expires_at ASC", (user_id, now)).fetchall()
    return [dict(r) for r in rows]

def _credit_available(db, user_id):
    return sum(b['units_left'] for b in _credit_batches_for_user(db, user_id))

def _credit_locked_total(db, user_id):
    """还在 24 小时冷却期内、暂不能用的次数总量（只统计交易大厅来源的批次）"""
    now = _now()
    row = db.execute(
        "SELECT COALESCE(SUM(units_left),0) FROM credit_batches WHERE user_id=? AND status='active' AND units_left>0 "
        "AND source IN ('trade','trade_reversal') AND created_at>? AND (expires_at IS NULL OR expires_at>?)",
        (user_id, now - CREDIT_LOCK_SECONDS, now)).fetchone()
    return row[0] or 0

def _consume_one_credit(db, user_id):
    """扣 1 次下单次数：优先用最快过期的批次，返回消耗的 batch id；没有可用次数返回 None"""
    batches = _credit_batches_for_user(db, user_id)
    if not batches:
        return None
    bid = batches[0]['id']
    db.execute("UPDATE credit_batches SET units_left = units_left - 1 WHERE id=?", (bid,))
    return bid

def _consume_credits_multi(db, user_id, units):
    """一次扣除多个次数（可能横跨多个批次），调用前必须已用 _credit_available 确认余额充足。
    返回涉及批次中最早的到期时间，用于给交易对方的新批次定到期；若涉及批次都是永久有效则返回 None"""
    expiries = []
    for _ in range(units):
        bid = _consume_one_credit(db, user_id)
        if bid is None:
            break
        row = db.execute("SELECT expires_at FROM credit_batches WHERE id=?", (bid,)).fetchone()
        expiries.append(row['expires_at'])
    finite = [e for e in expiries if e is not None]
    return min(finite) if finite else None

def _refund_credits(db, batch_id, units):
    if not batch_id or not units: return
    db.execute("UPDATE credit_batches SET units_left = units_left + ?, status='active' WHERE id=?", (units, batch_id))

def _refund_one_credit(db, batch_id):
    _refund_credits(db, batch_id, 1)

def _resolve_expires_at(valid_days=None, fixed_expires_at=None, base_ts=None):
    """两种到期方式二选一：固定日期优先，否则用「天数」从 base_ts（默认当前时间）起算"""
    if fixed_expires_at:
        return int(fixed_expires_at)
    if valid_days:
        return (base_ts or _now()) + int(valid_days) * 86400
    return None

def _grant_credit_batch(db, tenant_id, user_id, units, source, source_id, expires_at):
    now = _now()
    cur = db.execute('''INSERT INTO credit_batches
        (tenant_id,user_id,units_total,units_left,source,source_id,expires_at,status,created_at)
        VALUES (?,?,?,?,?,?,?,?,?)''',
        (tenant_id, user_id, units, units, source, source_id, expires_at, 'active', now))
    return cur.lastrowid

def _pool_denom_claimed(db, denom_id):
    """某一档次数卡已经被占用的张数（待审批 + 已通过），拒绝的申请不算，那张卡自动放回去给别人领"""
    return db.execute(
        "SELECT COUNT(*) FROM credit_requests WHERE pool_denom_id=? AND status IN ('pending','approved')",
        (denom_id,)).fetchone()[0]

def _pools_for_tenant(db, tenant_id, active_only=True):
    """一个创作者名下的次数池列表，每个池子可能有好几档面值（比如 3 张 5 次卡 + 1 张 3 次卡），
    附带每档已占用/剩余的张数，方块网格用它渲染"""
    where = "WHERE tenant_id=?"
    params = [tenant_id]
    if active_only:
        where += " AND status='active'"
    pools = [dict(p) for p in db.execute(
        f"SELECT * FROM credit_pools {where} ORDER BY created_at DESC", params).fetchall()]
    for p in pools:
        denoms = [dict(d) for d in db.execute(
            "SELECT * FROM credit_pool_denoms WHERE pool_id=? ORDER BY units DESC", (p['id'],)).fetchall()]
        for d in denoms:
            d['claimed']   = _pool_denom_claimed(db, d['id'])
            d['remaining'] = max(0, d['count'] - d['claimed'])
        p['denoms']      = denoms
        p['card_total']  = sum(d['count'] for d in denoms)      # 总张数
        p['card_claimed']= sum(d['claimed'] for d in denoms)
        p['remaining']   = sum(d['remaining'] for d in denoms)  # 剩余张数
        p['total_units'] = sum(d['units'] * d['count'] for d in denoms)  # 面值总和，仅作展示参考
        if p['fixed_expires_at']:
            p['expiry_label'] = f"至 {_fmt(p['fixed_expires_at'])}"
        elif p['valid_days']:
            p['expiry_label'] = f"{p['valid_days']} 天内有效"
        else:
            p['expiry_label'] = "永久有效"
    return pools

def _run_expiry_sweep():
    """后台定时任务：临近过期提醒（10/5/3/1 天）+ 到期自动清零并发回执"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        now = _now()
        rows = conn.execute(
            "SELECT * FROM credit_batches WHERE status='active' AND expires_at IS NOT NULL").fetchall()
        for row in rows:
            b = dict(row)
            if b['expires_at'] <= now:
                if b['units_left'] > 0:
                    _inbox_add(conn, b['tenant_id'], b['user_id'], 'credit_expired',
                               f"你有 {b['units_left']} 次下单次数已到期，已自动清除")
                conn.execute("UPDATE credit_batches SET status='expired', units_left=0 WHERE id=?", (b['id'],))
                continue
            if b['units_left'] <= 0:
                continue
            days_left = (b['expires_at'] - now) / 86400
            reminded = set(x for x in b['reminded_days'].split(',') if x)
            changed = False
            for th in (10, 5, 3, 1):
                if days_left <= th and str(th) not in reminded:
                    _inbox_add(conn, b['tenant_id'], b['user_id'], 'credit_expiring',
                               f"你有 {b['units_left']} 次下单次数将在 {th} 天内过期，请尽快使用")
                    reminded.add(str(th))
                    changed = True
            if changed:
                conn.execute("UPDATE credit_batches SET reminded_days=? WHERE id=?",
                             (','.join(sorted(reminded, key=int)), b['id']))
        conn.commit()
    finally:
        conn.close()

def _expiry_sweep_loop():
    while True:
        try:
            _run_expiry_sweep()
        except Exception as e:
            print(f"[yuca_order] expiry sweep error: {e}")
        time.sleep(3600)

threading.Thread(target=_expiry_sweep_loop, daemon=True).start()

def _allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def _save_file(f, order_id, sub='input'):
    if not f or not f.filename or not _allowed(f.filename): return None
    ext = f.filename.rsplit('.', 1)[1].lower()
    name = secrets.token_hex(10) + '.' + ext
    d = os.path.join(UPLOAD_DIR, str(order_id), sub)
    os.makedirs(d, exist_ok=True)
    f.save(os.path.join(d, name))
    return f"{order_id}/{sub}/{name}"

def _the_tenant(db):
    """默认创作者：只有一个创作者时用它兜底；以后有多个创作者，明确指定了 tenant 的入口（下单/交易大厅）不受影响"""
    return db.execute("SELECT * FROM tenants WHERE is_active=1 ORDER BY created_at LIMIT 1").fetchone()

def _get_or_create_membership(db, account_id, tenant_id):
    """账号在某个创作者下的会员行（users 表一行），次数/订单/交易都挂在这上面；不存在就自动开一个"""
    row = db.execute("SELECT * FROM users WHERE account_id=? AND tenant_id=?", (account_id, tenant_id)).fetchone()
    if row:
        return dict(row)
    acct = db.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    now = _now()
    # accounts.username 全站唯一，直接拿来当这一份会员行的 username 不会跟别的账号在同一创作者下撞名
    cur = db.execute('''INSERT INTO users (tenant_id,account_id,username,password_hash,display_name,contact,is_active,created_at)
                        VALUES (?,?,?,?,?,?,1,?)''',
                     (tenant_id, account_id, acct['username'], acct['password_hash'], acct['display_name'], acct['contact'], now))
    return dict(db.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone())

def _account_memberships(db, account_id):
    """账号名下所有创作者的会员行，附带创作者名称，用于按创作者分开展示次数/交易"""
    return [dict(r) for r in db.execute('''
        SELECT u.*, t.display_name AS tenant_name, t.slug AS tenant_slug
        FROM users u JOIN tenants t ON t.id=u.tenant_id
        WHERE u.account_id=? AND u.is_active=1 ORDER BY t.display_name''', (account_id,)).fetchall()]

def _tenant_status_list(db, with_schema=False, with_pools=False):
    """所有在营创作者 + 接单状态（开放/已关闭，由创作者的"接受散单"开关决定），下单页和获得次数页的创作者选择网格共用"""
    raw_tenants = [dict(t) for t in db.execute(
        "SELECT * FROM tenants WHERE is_active=1 ORDER BY display_name").fetchall()]
    result = []
    for t in raw_tenants:
        active_cnt = db.execute(
            "SELECT COUNT(*) FROM orders WHERE tenant_id=? AND status NOT IN ('completed','rejected','cancelled')",
            (t['id'],)).fetchone()[0]
        open_status = 'open' if t.get('orders_open', 1) else 'closed'
        item = {
            'id':               t['id'],
            'display_name':     t.get('display_name') or t['slug'],
            'description':      t.get('description', ''),
            'open_status':      open_status,
            'active_cnt':       active_cnt,
        }
        if with_schema:
            item['schema'] = _get_form_schema(t)
        if with_pools:
            pools = _pools_for_tenant(db, t['id'])
            item['pools']          = pools
            item['pool_total']     = sum(p['card_total'] for p in pools)   # 张数（不是次数面值）
            item['pool_remaining'] = sum(p['remaining'] for p in pools)    # 剩余张数
            item['has_pool']       = len(pools) > 0
        result.append(item)
    return result

def _service_types(tenant):
    try:
        st = json.loads(tenant['service_types'] or '[]')
        return st if st else DEFAULT_SERVICE_TYPES
    except: return DEFAULT_SERVICE_TYPES

DEFAULT_FORM_SCHEMA = [
    {"id": "_name",   "type": "builtin_name", "label": "称呼",           "required": True},
    {"id": "_qq",     "type": "builtin_qq",   "label": "QQ / 联系方式",  "required": True},
    {"id": "wengan",  "type": "textarea",     "label": "文案",            "required": True,  "placeholder": "请填写需要排版的完整文案内容", "hint": ""},
    {"id": "shuming", "type": "short_text",   "label": "署名",            "required": True,  "placeholder": "署名内容", "hint": ""},
    {"id": "ziti",    "type": "radio",        "label": "字体",            "required": False, "options": ["行楷","行草","可爱体","细体"], "default": "行楷"},
    {"id": "ketiao",  "type": "radio",        "label": "是否可挑排文案",  "required": False, "options": ["可以","不可以，全部排"], "default": "可以", "hint": "文案字数过多容易画面看起来过满，美感打折。"},
    {"id": "sucai",   "type": "textarea",     "label": "排版素材",        "required": False, "placeholder": "和人设/文案有关的数字、日期、英文歌词等", "hint": ""},
    {"id": "other",   "type": "textarea",     "label": "其他备注",        "required": False, "placeholder": "", "hint": ""},
]

def _get_form_schema(tenant):
    raw = (tenant.get('order_form_schema', '') or '') if isinstance(tenant, dict) else ''
    if not raw:
        return [f.copy() for f in DEFAULT_FORM_SCHEMA]
    try:
        return json.loads(raw)
    except Exception:
        return [f.copy() for f in DEFAULT_FORM_SCHEMA]

def _process_order_form(form_data, schema):
    """从 request.form 按 schema 提取字段，返回 (name, contact, title, desc, errors)"""
    customer_name    = ''
    customer_contact = ''
    title_val        = ''
    desc_parts       = []
    errors           = []
    for field in schema:
        ftype    = field['type']
        fid      = field['id']
        label    = field['label']
        required = field.get('required', False)
        if ftype == 'builtin_name':
            customer_name = form_data.get('_name', '').strip()
            if required and not customer_name:
                errors.append(f'请填写{label}')
        elif ftype == 'builtin_qq':
            customer_contact = form_data.get('_qq', '').strip()
            if required and not customer_contact:
                errors.append(f'请填写{label}')
        elif ftype in ('upload', 'heading'):
            pass
        else:
            val = form_data.get(fid, '').strip()
            if required and not val:
                errors.append(f'请填写{label}')
            if val:
                if not title_val and required and ftype in ('short_text', 'textarea'):
                    title_val = val[:80]
                if ftype == 'textarea':
                    desc_parts.append(f'【{label}】\n{val}')
                else:
                    desc_parts.append(f'【{label}】{val}')
    desc  = '\n\n'.join(desc_parts)
    title = title_val or customer_name
    return customer_name, customer_contact, title, desc, errors

def _delete_order_files(order_id):
    """完成/拒绝后删除该订单所有本地图片"""
    d = os.path.join(UPLOAD_DIR, str(order_id))
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)

def _add_log(db, order_id, action, actor, note=''):
    db.execute("INSERT INTO order_logs (order_id, action, actor, note, created_at) VALUES (?,?,?,?,?)",
               (order_id, action, actor, note, _now()))


# ── 补充备注 ──────────────────────────────────────────────────────────────────

def _pool_need_approval(pool):
    """这一批单口的领取是否需要人工审批。老数据/取不到值时按需要审批处理。"""
    try:
        v = pool['need_approval']
    except (KeyError, IndexError, TypeError):
        return True
    return bool(1 if v is None else v)

def _order_notes(db, order_id, author_type=None):
    """取一单的补充备注。客户端只能取 author_type='customer'——
    接单方追加的那些是内部备注，客户看不到。"""
    sql = "SELECT * FROM order_notes WHERE order_id=?"
    args = [order_id]
    if author_type:
        sql += " AND author_type=?"
        args.append(author_type)
    return [dict(n) for n in db.execute(sql + " ORDER BY created_at", args).fetchall()]

def _add_order_note(db, order_id, author_type, author_name, content):
    db.execute('''INSERT INTO order_notes (order_id,author_type,author_name,content,created_at)
                  VALUES (?,?,?,?,?)''',
               (order_id, author_type, author_name, content, _now()))
    db.execute("UPDATE orders SET updated_at=? WHERE id=?", (_now(), order_id))

def _validate_note(content, db=None, order_id=None, author_type=None):
    """校验一条补充备注，通过返回 None，不通过返回给用户看的提示文案。"""
    if not content:
        return "备注内容不能为空"
    if len(content) > ORDER_NOTE_MAX_LEN:
        return f"备注最多 {ORDER_NOTE_MAX_LEN} 字，当前 {len(content)} 字"
    if author_type == 'customer' and db is not None:
        used = db.execute("SELECT COUNT(*) FROM order_notes WHERE order_id=? AND author_type='customer'",
                          (order_id,)).fetchone()[0]
        if used >= ORDER_NOTE_MAX_CUSTOMER:
            return f"这一单最多追加 {ORDER_NOTE_MAX_CUSTOMER} 条备注，已达上限，请直接联系接单方"
    return None

def _order_access(db, order):
    """返回 (能否查看这一单, 是不是下单人本人)。"""
    owns = False
    if session.get('account_id') and order.get('user_id'):
        owns = bool(db.execute("SELECT 1 FROM users WHERE id=? AND account_id=?",
                               (order['user_id'], session['account_id'])).fetchone())
    if not owns and session.get(f"vo_{order['order_no']}"):
        owns = True
    allowed = (
        bool(session.get('superadmin')) or
        (session.get('admin_id') and session.get('admin_tenant_id') == order['tenant_id']) or
        owns
    )
    return allowed, owns


# ── Auth decorators ───────────────────────────────────────────────────────────

def require_superadmin(f):
    @wraps(f)
    def w(*a, **kw):
        if not session.get('superadmin'):
            return redirect(url_for('superadmin_login', next=request.path))
        return f(*a, **kw)
    return w

def require_admin(f):
    @wraps(f)
    def w(*a, **kw):
        if not session.get('admin_id'):
            return redirect(url_for('admin_login', next=request.path))
        return f(*a, **kw)
    return w

def require_user(f):
    @wraps(f)
    def w(*a, **kw):
        if not session.get('account_id'):
            return redirect(url_for('user_login', next=request.path))
        return f(*a, **kw)
    return w


# ── Template helpers ──────────────────────────────────────────────────────────

@app.template_filter('fmt')
def fmt_filter(ts): return _fmt(ts)

@app.template_filter('to_days_left')
def to_days_left(s):
    try:
        from datetime import date
        exp = date.fromisoformat(str(s))
        return (exp - date.today()).days
    except: return None

@app.template_filter('sl')
def sl_filter(s): return STATUS_LABEL.get(s, s)

@app.template_filter('sc')
def sc_filter(s): return STATUS_COLOR.get(s, '#888')

@app.context_processor
def _ctx():
    unread = 0
    if session.get('account_id'):
        try:
            unread = get_db().execute(
                "SELECT COUNT(*) FROM inbox_messages WHERE is_read=0 AND user_id IN "
                "(SELECT id FROM users WHERE account_id=?)", (session['account_id'],)).fetchone()[0]
        except Exception:
            unread = 0
    return dict(
        session=session,
        STATUS_LABEL=STATUS_LABEL,
        STATUS_COLOR=STATUS_COLOR,
        ALL_STATUSES=ALL_STATUSES,
        CREDIT_STATUS_LABEL=CREDIT_STATUS_LABEL,
        unread_inbox_count=unread,
    )


# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(404)
def e404(e): return render_template('error.html', code=404, msg='页面不存在'), 404

@app.errorhandler(500)
def e500(e):
    _logger.error("500\nURL: %s %s\n%s", request.method, request.url, traceback.format_exc())
    return render_template('error.html', code=500, msg='服务器内部错误'), 500


# ── Static uploads ────────────────────────────────────────────────────────────

@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# ── 首页 ──────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    db = get_db()
    rows = [dict(t) for t in db.execute(
        "SELECT * FROM tenants WHERE is_active=1 ORDER BY display_name").fetchall()]
    # 给每个 tenant 附上实时接单状态
    for t in rows:
        active_cnt = db.execute(
            "SELECT COUNT(*) FROM orders WHERE tenant_id=? AND status NOT IN ('completed','rejected','cancelled')",
            (t['id'],)).fetchone()[0]
        t['active_cnt'] = active_cnt
        # 综合状态：open=接单中 / closed=已关闭（由创作者的"接受散单"开关决定）
        t['open_status'] = 'open' if t.get('orders_open', 1) else 'closed'
    any_open = any(t['open_status'] == 'open' for t in rows)
    return render_template('index.html', tenants=rows, any_open=any_open)


# ── 下单 ──────────────────────────────────────────────────────────────────────

@app.route('/order/new', methods=['GET', 'POST'])
@require_user
def order_new():
    db = get_db()
    tenant_data = _tenant_status_list(db, with_schema=True)
    if not tenant_data:
        abort(404)

    req_tid = request.form.get('tenant_id') or request.args.get('t')
    tenant_row = None
    if req_tid:
        tenant_row = db.execute("SELECT * FROM tenants WHERE id=? AND is_active=1", (req_tid,)).fetchone()
        if not tenant_row:
            abort(404)
    elif len(tenant_data) == 1:
        # 只有一位在营创作者：直接兜底选中，省得多一步选择；多位创作者时留给前端网格选
        tenant_row = _the_tenant(db)

    acct = db.execute("SELECT * FROM accounts WHERE id=?", (session['account_id'],)).fetchone()
    user_info = {
        '_name': acct['display_name'] or acct['username'],
        '_qq':   acct['contact'] or acct['username'],
    }

    pre_tid        = ''
    errors         = []
    error_tid      = ''   # 出错时回显哪个 tenant 的表单
    credit_balance = 0

    if tenant_row:
        tid_int  = tenant_row['id']
        user_row = _get_or_create_membership(db, session['account_id'], tid_int)
        db.commit()
        credit_balance = _credit_available(db, user_row['id'])
        if credit_balance < 1:
            locked = _credit_locked_total(db, user_row['id'])
            if locked > 0:
                flash(f"你有 {locked} 次刚获得的次数还在 24 小时冷却期内，请稍后再来下单")
            else:
                flash("次数不足，请先获得下单次数，等待管理员通过后再下单")
            return redirect(url_for('credits_buy', t=tid_int))
        pre_tid = str(tid_int)

        if request.method == 'POST':
            # 登录用户只能给自己账号所属账户下单，忽略前端提交的 tenant_id，防止跨账户消耗次数
            error_tid = pre_tid
            t = dict(tenant_row)
            if not t.get('orders_open', 1):
                errors.append("😔 该创作者日程繁忙，近期无法接单，请谅解")
            if not errors:
                schema = _get_form_schema(t)
                name, contact, title, desc, form_errors = _process_order_form(request.form, schema)
                errors.extend(form_errors)
                # 下单即时占用 1 次数（防止 GET 到提交之间被抢光/退回），管理拒绝时会退回对应批次
                user_id = user_row['id']
                batch_id = None
                if not errors:
                    batch_id = _consume_one_credit(db, user_id)
                    if batch_id is None:
                        errors.append("次数不足，请先获得下单次数")
                if not errors:
                    now      = _now()
                    order_no = _gen_order_no()
                    verify   = _gen_verify()
                    db.execute('''INSERT INTO orders
                        (order_no,tenant_id,user_id,customer_name,customer_contact,
                         service_type,title,description,status,verify_code,credit_consumed,credit_batch_id,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (order_no, tid_int, user_id, name, contact,
                         '排单', title, desc, 'pending', verify, 1, batch_id, now, now))
                    db.commit()
                    oid = db.execute("SELECT id FROM orders WHERE order_no=?", (order_no,)).fetchone()['id']
                    _add_log(db, oid, '创建', name)
                    db.commit()
                    return redirect(url_for('order_success', no=order_no, vc=verify))
    elif request.method == 'POST':
        errors.append("请选择接单方")

    return render_template('order_new.html',
                           tenant_data=tenant_data,
                           pre_tid=pre_tid,
                           errors=errors,
                           error_tid=error_tid,
                           submitted=dict(request.form) if errors else {},
                           user_info=user_info,
                           credit_balance=credit_balance)

@app.route('/order/success')
def order_success():
    db = get_db()
    order_no = request.args.get('no', '')
    contact_qq = ''
    order = db.execute("SELECT tenant_id FROM orders WHERE order_no=?", (order_no,)).fetchone()
    if order:
        tenant = db.execute("SELECT contact_qq FROM tenants WHERE id=?", (order['tenant_id'],)).fetchone()
        if tenant:
            contact_qq = tenant['contact_qq']
    return render_template('order_success.html',
        order_no=order_no,
        verify_code=request.args.get('vc',''),
        contact_qq=contact_qq)

@app.route('/order/<order_no>', methods=['GET', 'POST'])
def order_status(order_no):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE order_no=?", (order_no,)).fetchone()
    if not order: abort(404)
    order = dict(order)

    # determine access
    allowed, owns_order = _order_access(db, order)

    if not allowed:
        vk = f'vo_{order_no}'
        if request.method == 'POST':
            code = request.form.get('verify_code', '').strip().upper()
            if code == order['verify_code'].upper():
                session[vk] = True
                return redirect(url_for('order_status', order_no=order_no))
            return render_template('order_verify.html', order_no=order_no, error='验证码错误')
        return render_template('order_verify.html', order_no=order_no, error=None)

    tenant = db.execute("SELECT * FROM tenants WHERE id=?", (order['tenant_id'],)).fetchone()
    images = [dict(i) for i in db.execute("SELECT * FROM order_images WHERE order_id=?", (order['id'],)).fetchall()]
    result_images = [dict(i) for i in db.execute("SELECT * FROM order_result_images WHERE order_id=?", (order['id'],)).fetchall()]
    logs = [dict(l) for l in db.execute("SELECT * FROM order_logs WHERE order_id=? ORDER BY created_at", (order['id'],)).fetchall()]

    # 接单方追加的是内部备注，客户看不到，所以这里只取客户自己写的
    notes = _order_notes(db, order['id'], author_type='customer')
    used_notes = len(notes)

    return render_template('order_status.html',
        order=order, tenant=dict(tenant) if tenant else {},
        images=images, result_images=result_images, logs=logs,
        notes=notes,
        # 只有下单人本人、且订单已被接下时才能追加
        can_append=(owns_order and order['status'] in ORDER_NOTE_STATUSES
                    and used_notes < ORDER_NOTE_MAX_CUSTOMER),
        notes_left=ORDER_NOTE_MAX_CUSTOMER - used_notes,
        NOTE_MAX_LEN=ORDER_NOTE_MAX_LEN)


@app.route('/order/<order_no>/note', methods=['POST'])
def order_add_note(order_no):
    """下单人给已接单的订单追加一条文字备注"""
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE order_no=?", (order_no,)).fetchone()
    if not order: abort(404)
    order = dict(order)
    back = redirect(url_for('order_status', order_no=order_no))

    allowed, owns_order = _order_access(db, order)
    if not (allowed and owns_order):
        abort(403)
    if order['status'] not in ORDER_NOTE_STATUSES:
        flash("只有已接单 / 制作中的订单可以追加备注")
        return back

    content = request.form.get('content', '').strip()
    err = _validate_note(content, db, order['id'], 'customer')
    if err:
        flash(err)
        return back

    name = order['customer_name'] or '客户'
    _add_order_note(db, order['id'], 'customer', name, content)
    _add_log(db, order['id'], '追加备注', name, content[:60])
    db.commit()
    flash("备注已追加，接单方会收到提醒")
    return back


# ── 用户注册 / 登录 ───────────────────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def user_register():
    db = get_db()
    tenant = _the_tenant(db)
    errors = []
    if request.method == 'POST':
        uname   = request.form.get('username', '').strip()
        pw      = request.form.get('password', '').strip()
        dname   = request.form.get('display_name', '').strip() or uname
        contact = request.form.get('contact', '').strip()

        if not tenant:
            errors.append("系统尚未配置账户，请联系管理员")
        if not uname or len(uname) < 3:  errors.append("用户名至少 3 个字符")
        if not pw    or len(pw)    < 6:  errors.append("密码至少 6 个字符")
        if not contact: errors.append("请填写 QQ 号")
        if not errors:
            if db.execute("SELECT id FROM accounts WHERE username=?", (uname,)).fetchone():
                errors.append("用户名已存在")
        if not errors:
            now = _now()
            cur = db.execute('''INSERT INTO accounts (username,password_hash,display_name,contact,is_active,created_at)
                                VALUES (?,?,?,?,1,?)''',
                             (uname, generate_password_hash(pw), dname, contact, now))
            # 注册即自动加入默认创作者，保持今天单一创作者下的体验不变
            _get_or_create_membership(db, cur.lastrowid, tenant['id'])
            db.commit()
            flash("注册成功，请登录")
            return redirect(url_for('user_login'))
    return render_template('register.html', errors=errors)

@app.route('/login', methods=['GET', 'POST'])
def user_login():
    errors = []
    if request.method == 'POST':
        db    = get_db()
        uname = request.form.get('username', '').strip()
        pw    = request.form.get('password', '').strip()
        acct  = db.execute("SELECT * FROM accounts WHERE username=? AND is_active=1", (uname,)).fetchone()
        if acct and check_password_hash(acct['password_hash'], pw):
            session['account_id']           = acct['id']
            session['account_display_name'] = acct['display_name'] or acct['username']
            return redirect(request.args.get('next') or url_for('my_orders'))
        errors.append("用户名 / 密码错误")
    return render_template('login.html', errors=errors)

@app.route('/logout')
def user_logout():
    for k in ('account_id', 'account_display_name'):
        session.pop(k, None)
    return redirect(url_for('index'))

@app.route('/my-orders')
@require_user
def my_orders():
    db  = get_db()
    aid = session['account_id']
    memberships = _account_memberships(db, aid)
    now = _now()

    orders = [dict(o) for o in db.execute(
        '''SELECT o.*, t.display_name AS tenant_name
           FROM orders o JOIN tenants t ON t.id=o.tenant_id
           WHERE o.user_id IN (SELECT id FROM users WHERE account_id=?)
           ORDER BY o.created_at DESC''', (aid,)).fetchall()]
    announcements = [dict(a) for a in db.execute(
        '''SELECT a.*, t.display_name AS tenant_name
           FROM announcements a JOIN tenants t ON t.id=a.tenant_id
           WHERE a.tenant_id IN (SELECT tenant_id FROM users WHERE account_id=? AND is_active=1)
           ORDER BY a.created_at DESC LIMIT 10''', (aid,)).fetchall()]
    credit_requests = [dict(r) for r in db.execute(
        '''SELECT cr.*, t.display_name AS tenant_name
           FROM credit_requests cr JOIN tenants t ON t.id=cr.tenant_id
           WHERE cr.user_id IN (SELECT id FROM users WHERE account_id=?)
           ORDER BY cr.created_at DESC''', (aid,)).fetchall()]

    # 按创作者分开列出次数明细（credit_batches 天然挂在各创作者自己的会员行上，互不相通）
    creator_credits = []
    total_balance = 0
    for m in memberships:
        batches = _credit_batches_for_user(db, m['id'], only_available=False)
        for b in batches:
            locked_at = b['created_at'] + CREDIT_LOCK_SECONDS
            b['locked_until'] = locked_at if (b['source'] in CREDIT_LOCK_SOURCES and locked_at > now) else None
        balance = _credit_available(db, m['id'])
        total_balance += balance
        creator_credits.append({
            'tenant_name': m['tenant_name'] or m['tenant_slug'],
            'tenant_id':   m['tenant_id'],
            'balance':     balance,
            'batches':     batches,
        })

    return render_template('my_orders.html', orders=orders, announcements=announcements,
                           credit_balance=total_balance,
                           creator_credits=creator_credits,
                           credit_requests=credit_requests)


# ── 获得下单次数 ──────────────────────────────────────────────────────────────

CREDIT_STATUS_LABEL = {'pending': '审核中', 'approved': '已通过', 'rejected': '已拒绝'}

@app.route('/credits/buy')
@require_user
def credits_buy():
    db  = get_db()
    aid = session['account_id']
    tenant_data = _tenant_status_list(db, with_pools=True)
    preselect_tid = request.args.get('t') or ''
    pending  = [dict(r) for r in db.execute(
        '''SELECT cr.*, t.display_name AS tenant_name FROM credit_requests cr
           JOIN tenants t ON t.id=cr.tenant_id
           WHERE cr.user_id IN (SELECT id FROM users WHERE account_id=?) AND cr.status='pending'
           ORDER BY cr.created_at DESC''', (aid,)).fetchall()]
    total_balance = sum(_credit_available(db, m['id']) for m in _account_memberships(db, aid))
    return render_template('credits_buy.html',
                           credit_balance=total_balance,
                           tenant_data=tenant_data,
                           preselect_tid=preselect_tid,
                           pending=pending)

@app.route('/credits/pool-denoms/<int:did>/claim', methods=['POST'])
@require_user
def credits_pool_claim(did):
    db  = get_db()
    aid = session['account_id']
    denom = db.execute("SELECT * FROM credit_pool_denoms WHERE id=?", (did,)).fetchone()
    if not denom:
        flash("该次数卡不存在")
        return redirect(url_for('credits_buy'))
    pool = db.execute("SELECT * FROM credit_pools WHERE id=? AND status='active'", (denom['pool_id'],)).fetchone()
    if not pool:
        flash("该单口不存在或已关闭")
        return redirect(url_for('credits_buy'))
    tenant = db.execute("SELECT * FROM tenants WHERE id=? AND is_active=1", (pool['tenant_id'],)).fetchone()
    if not tenant:
        flash("该创作者不存在")
        return redirect(url_for('credits_buy'))
    remaining = denom['count'] - _pool_denom_claimed(db, did)
    if remaining <= 0:
        flash("手慢了，这张卡已经被领完了")
        return redirect(url_for('credits_buy', t=pool['tenant_id']))
    member = _get_or_create_membership(db, aid, pool['tenant_id'])
    now = _now()
    need_approval = _pool_need_approval(pool)
    status = 'pending' if need_approval else 'approved'
    cur = db.execute('''INSERT INTO credit_requests
        (tenant_id,user_id,units,status,note,pool_id,pool_denom_id,created_at) VALUES (?,?,?,?,?,?,?,?)''',
        (pool['tenant_id'], member['id'], denom['units'], status, '', pool['id'], did, now))

    if need_approval:
        db.commit()
        flash(f"已领取 1 张 {denom['units']} 次卡，等待管理员确认到账")
    else:
        # 免审批：抢到即到账，有效期照样跟着次数池的规则走
        rid = cur.lastrowid
        expires_at = _resolve_expires_at(valid_days=pool['valid_days'],
                                         fixed_expires_at=pool['fixed_expires_at'])
        _grant_credit_batch(db, pool['tenant_id'], member['id'], denom['units'],
                            'credit_request', rid, expires_at)
        db.execute("UPDATE credit_requests SET decided_at=?, decided_by=NULL WHERE id=?", (now, rid))
        db.commit()
        flash(f"已领取 1 张 {denom['units']} 次卡，{denom['units']} 次已直接到账，可以立刻下单")
    return redirect(url_for('my_orders'))

@app.route('/credits/redeem', methods=['POST'])
@require_user
def credits_redeem():
    db   = get_db()
    code = request.form.get('code', '').strip().upper()
    if not code:
        flash("请输入兑换码")
        return redirect(url_for('credits_buy'))
    row = db.execute("SELECT * FROM redeem_codes WHERE code=?", (code,)).fetchone()
    if not row:
        flash("兑换码不存在")
    elif row['status'] != 'unused':
        flash("该兑换码已被使用")
    else:
        now = _now()
        member = _get_or_create_membership(db, session['account_id'], row['tenant_id'])
        db.execute("UPDATE redeem_codes SET status='redeemed', redeemed_by=?, redeemed_at=? WHERE id=?",
                   (member['id'], now, row['id']))
        expires_at = _resolve_expires_at(valid_days=row['valid_days'], fixed_expires_at=row['fixed_expires_at'])
        _grant_credit_batch(db, row['tenant_id'], member['id'],
                             row['units'], 'redeem_code', row['id'], expires_at)
        db.commit()
        if row['fixed_expires_at']:
            expiry_note = f"，有效期至 {_fmt(row['fixed_expires_at'])}"
        elif row['valid_days']:
            expiry_note = f"，{row['valid_days']} 天内有效"
        else:
            expiry_note = "，永久有效"
        flash(f"兑换成功，获得 {row['units']} 次" + expiry_note + "（可以立刻下单）")
    return redirect(url_for('credits_buy'))


# ── 次数交易大厅 ──────────────────────────────────────────────────────────────

ARBITRATION_QQ = "3052553938"

def _is_my_membership(db, users_id, account_id):
    return bool(db.execute("SELECT 1 FROM users WHERE id=? AND account_id=?", (users_id, account_id)).fetchone())

@app.route('/trades')
@require_user
def trades_hall():
    db  = get_db()
    aid = session['account_id']
    all_tenants = [dict(t) for t in db.execute(
        "SELECT * FROM tenants WHERE is_active=1 ORDER BY display_name").fetchall()]
    req_tid = request.args.get('t')
    tenant  = next((t for t in all_tenants if str(t['id']) == req_tid), None) if req_tid else None
    if not tenant:
        tenant = dict(_the_tenant(db)) if _the_tenant(db) else (all_tenants[0] if all_tenants else None)
    if not tenant:
        abort(404)
    tid = tenant['id']
    member = _get_or_create_membership(db, aid, tid)
    db.commit()
    uid = member['id']

    listings = [dict(r) for r in db.execute(
        '''SELECT tl.*, u.display_name AS poster_name, u.username AS poster_username, u.contact AS poster_contact
           FROM trade_listings tl JOIN users u ON u.id=tl.poster_id
           WHERE tl.tenant_id=? AND tl.status='open' ORDER BY tl.created_at DESC''', (tid,)).fetchall()]
    my_batches = _credit_batches_for_user(db, uid)
    my_trades = [dict(r) for r in db.execute(
        '''SELECT t.*, pu.display_name AS poster_name, pu.username AS poster_username, pu.contact AS poster_contact,
                  tu.display_name AS taker_name, tu.username AS taker_username, tu.contact AS taker_contact
           FROM trades t
           JOIN users pu ON pu.id=t.poster_id
           JOIN users tu ON tu.id=t.taker_id
           WHERE t.tenant_id=? AND (t.poster_id=? OR t.taker_id=?)
           ORDER BY t.created_at DESC''', (tid, uid, uid)).fetchall()]
    return render_template('trades_hall.html', listings=listings, my_batches=my_batches,
                           my_trades=my_trades, uid=uid, arbitration_qq=ARBITRATION_QQ,
                           tenants=all_tenants, current_tenant=tenant)

@app.route('/trades/new', methods=['POST'])
@require_user
def trades_new():
    db  = get_db()
    aid = session['account_id']
    kind = request.form.get('kind', '')
    if kind not in ('sell', 'exchange'):
        flash("请选择交易类型"); return redirect(url_for('trades_hall'))
    try:
        batch_id = int(request.form.get('batch_id', ''))
        offer_units = int(request.form.get('offer_units', '').strip())
    except ValueError:
        flash("请填写正确的次数数量"); return redirect(url_for('trades_hall'))
    note = request.form.get('note', '').strip()
    batch = db.execute('''SELECT cb.*, u.account_id FROM credit_batches cb JOIN users u ON u.id=cb.user_id
                          WHERE cb.id=? AND cb.status='active' ''', (batch_id,)).fetchone()
    if not batch or batch['account_id'] != aid:
        flash("批次不存在"); return redirect(url_for('trades_hall'))
    tid = batch['tenant_id']; uid = batch['user_id']
    if offer_units < 1 or offer_units > batch['units_left']:
        flash("数量超过该批次剩余次数"); return redirect(url_for('trades_hall', t=tid))
    if batch['source'] in CREDIT_LOCK_SOURCES and batch['created_at'] + CREDIT_LOCK_SECONDS > _now():
        flash("该批次次数是交易换来的，还在 24 小时冷却期内，暂不能再次挂单交易"); return redirect(url_for('trades_hall', t=tid))
    want_units = None
    if kind == 'exchange':
        try:
            want_units = int(request.form.get('want_units', '').strip())
        except ValueError:
            want_units = 0
        if want_units < 1:
            flash("请填写希望换回的次数"); return redirect(url_for('trades_hall', t=tid))
    now = _now()
    db.execute("UPDATE credit_batches SET units_left = units_left - ? WHERE id=?", (offer_units, batch['id']))
    db.execute('''INSERT INTO trade_listings
        (tenant_id,poster_id,kind,offer_batch_id,offer_units,offer_expires_at,want_units,note,status,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)''',
        (tid, uid, kind, batch['id'], offer_units, batch['expires_at'], want_units, note, 'open', now))
    db.commit()
    flash("已发布到交易大厅")
    return redirect(url_for('trades_hall', t=tid))

@app.route('/trades/listing/<int:lid>/cancel', methods=['POST'])
@require_user
def trades_listing_cancel(lid):
    db = get_db()
    l = db.execute("SELECT * FROM trade_listings WHERE id=?", (lid,)).fetchone()
    if not l or not _is_my_membership(db, l['poster_id'], session['account_id']): abort(404)
    if l['status'] != 'open':
        flash("该挂单当前不可取消"); return redirect(url_for('trades_hall', t=l['tenant_id']))
    _refund_credits(db, l['offer_batch_id'], l['offer_units'])
    db.execute("UPDATE trade_listings SET status='cancelled' WHERE id=?", (lid,))
    db.commit()
    flash("已取消挂单，次数已退回")
    return redirect(url_for('trades_hall', t=l['tenant_id']))

@app.route('/trades/listing/<int:lid>/initiate', methods=['POST'])
@require_user
def trades_initiate(lid):
    db  = get_db()
    aid = session['account_id']
    l = db.execute("SELECT * FROM trade_listings WHERE id=? AND status='open'", (lid,)).fetchone()
    if not l:
        flash("该挂单已不可用"); return redirect(url_for('trades_hall'))
    tid = l['tenant_id']
    member = _get_or_create_membership(db, aid, tid)
    uid = member['id']
    if l['poster_id'] == uid:
        flash("不能对自己的挂单发起交易"); return redirect(url_for('trades_hall', t=tid))
    now = _now()
    db.execute("UPDATE trade_listings SET status='trading' WHERE id=?", (lid,))
    cur = db.execute('''INSERT INTO trades
        (tenant_id,listing_id,kind,poster_id,taker_id,offer_units,offer_batch_id,offer_expires_at,
         want_units,note,status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (tid, lid, l['kind'], l['poster_id'], uid, l['offer_units'], l['offer_batch_id'], l['offer_expires_at'],
         l['want_units'], l['note'], 'pending', now, now))
    trade_id = cur.lastrowid

    if l['kind'] == 'exchange':
        if _credit_available(db, uid) >= l['want_units']:
            min_expiry = _consume_credits_multi(db, uid, l['want_units'])
            poster_batch_id = _grant_credit_batch(db, tid, l['poster_id'], l['want_units'], 'trade', trade_id, min_expiry)
            taker_batch_id  = _grant_credit_batch(db, tid, uid, l['offer_units'], 'trade', trade_id, l['offer_expires_at'])
            db.execute('''UPDATE trades SET status='exchanged', result_batch_to_taker=?, result_batch_to_poster=?,
                          updated_at=? WHERE id=?''', (taker_batch_id, poster_batch_id, now, trade_id))
            db.execute("UPDATE trade_listings SET status='completed' WHERE id=?", (lid,))
            _inbox_add(db, tid, l['poster_id'], 'trade_exchanged',
                       f"你挂出的次数交易已完成，获得 {l['want_units']} 次（24 小时后可下单）")
            _inbox_add(db, tid, uid, 'trade_exchanged',
                       f"交易成功，获得 {l['offer_units']} 次（24 小时后可下单）")
            db.commit()
            flash(f"交换成功！获得 {l['offer_units']} 次")
        else:
            _refund_credits(db, l['offer_batch_id'], l['offer_units'])
            db.execute("UPDATE trades SET status='cancelled', updated_at=? WHERE id=?", (now, trade_id))
            db.execute("UPDATE trade_listings SET status='open' WHERE id=?", (lid,))
            db.commit()
            flash("你的次数不足，交易已取消，该挂单已重新回到大厅")
        return redirect(url_for('trades_hall', t=tid))
    else:
        _inbox_add(db, tid, l['poster_id'], 'trade_requested',
                   f"有人想购买你挂出的 {l['offer_units']} 次，请与对方私下完成交易后点击「转交次数」")
        db.commit()
        flash("已发起交易，请与对方私下完成交易，等待对方转交次数")
        return redirect(url_for('trades_hall', t=tid))

@app.route('/trades/<int:trade_id>/cancel', methods=['POST'])
@require_user
def trades_cancel(trade_id):
    db  = get_db()
    aid = session['account_id']
    t = db.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
    if not t or not (_is_my_membership(db, t['poster_id'], aid) or _is_my_membership(db, t['taker_id'], aid)):
        abort(404)
    if t['status'] != 'pending':
        flash("该交易当前不可取消"); return redirect(url_for('trades_hall', t=t['tenant_id']))
    now = _now()
    _refund_credits(db, t['offer_batch_id'], t['offer_units'])
    db.execute("UPDATE trades SET status='cancelled', updated_at=? WHERE id=?", (now, trade_id))
    db.execute("UPDATE trade_listings SET status='open' WHERE id=?", (t['listing_id'],))
    other = t['taker_id'] if _is_my_membership(db, t['poster_id'], aid) else t['poster_id']
    _inbox_add(db, t['tenant_id'], other, 'trade_cancelled', "对方已取消一笔交易，次数已退回挂单方")
    db.commit()
    flash("已取消交易，次数已退回")
    return redirect(url_for('trades_hall', t=t['tenant_id']))

@app.route('/trades/<int:trade_id>/transfer', methods=['POST'])
@require_user
def trades_transfer(trade_id):
    db = get_db()
    t = db.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
    if not t or not _is_my_membership(db, t['poster_id'], session['account_id']): abort(404)
    if t['status'] != 'pending' or t['kind'] != 'sell':
        flash("当前状态无法转交"); return redirect(url_for('trades_hall', t=t['tenant_id']))
    now = _now()
    taker_batch_id = _grant_credit_batch(db, t['tenant_id'], t['taker_id'], t['offer_units'],
                                          'trade', trade_id, t['offer_expires_at'])
    db.execute("UPDATE trades SET status='transferred', result_batch_to_taker=?, updated_at=? WHERE id=?",
               (taker_batch_id, now, trade_id))
    db.execute("UPDATE trade_listings SET status='completed' WHERE id=?", (t['listing_id'],))
    _inbox_add(db, t['tenant_id'], t['taker_id'], 'trade_transferred',
               f"对方已转交 {t['offer_units']} 次给你（24 小时后可下单）")
    db.commit()
    flash("已转交次数")
    return redirect(url_for('trades_hall', t=t['tenant_id']))

@app.route('/trades/<int:trade_id>/dispute', methods=['POST'])
@require_user
def trades_dispute(trade_id):
    db  = get_db()
    aid = session['account_id']
    t = db.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
    if not t: abort(404)
    im_poster = _is_my_membership(db, t['poster_id'], aid)
    im_taker  = _is_my_membership(db, t['taker_id'], aid)
    if not (im_poster or im_taker): abort(404)
    if t['status'] not in ('transferred', 'exchanged'):
        flash("只有已完成的交易才能申请仲裁"); return redirect(url_for('trades_hall', t=t['tenant_id']))
    if t['dispute_status'] == 'pending':
        flash("该交易已在仲裁中"); return redirect(url_for('trades_hall', t=t['tenant_id']))
    note = request.form.get('dispute_note', '').strip()
    my_id = t['poster_id'] if im_poster else t['taker_id']
    other_id = t['taker_id'] if im_poster else t['poster_id']
    disputed_batch = t['result_batch_to_taker'] if im_poster else t['result_batch_to_poster']
    now = _now()
    if disputed_batch:
        db.execute("UPDATE credit_batches SET status='frozen' WHERE id=?", (disputed_batch,))
    db.execute('''UPDATE trades SET dispute_status='pending', dispute_by=?, dispute_note=?,
                  disputed_batch_id=?, dispute_at=?, updated_at=? WHERE id=?''',
               (my_id, note, disputed_batch, now, now, trade_id))
    _inbox_add(db, t['tenant_id'], other_id, 'trade_disputed',
               f"对方对一笔交易发起了仲裁申请，相关次数已冻结。如有异议请联系 QQ {ARBITRATION_QQ} 提供证据")
    db.commit()
    flash(f"仲裁申请已提交，对方相关次数已冻结。请联系 QQ {ARBITRATION_QQ} 提供交易证据，等待超管处理")
    return redirect(url_for('trades_hall', t=t['tenant_id']))


# ── 站内信 / 回执箱 ────────────────────────────────────────────────────────────

INBOX_KIND_ICON = {
    'order_accepted':  '✅', 'order_rejected':  '❌', 'order_completed': '🎉',
    'order_cancelled': '⚠️', 'order_note': '📝', 'credit_approved': '🎫', 'credit_rejected': '🎫',
    'credit_expiring': '⏰', 'credit_expired':  '🗑️',
    'trade_exchanged': '🔄', 'trade_requested': '🤝', 'trade_cancelled': '⚠️',
    'trade_transferred': '🎁', 'trade_disputed': '⚖️', 'dispute_resolved': '⚖️',
}

@app.route('/inbox')
@require_user
def inbox():
    db  = get_db()
    aid = session['account_id']
    msgs = [dict(m) for m in db.execute(
        '''SELECT im.*, t.display_name AS tenant_name FROM inbox_messages im
           JOIN tenants t ON t.id=im.tenant_id
           WHERE im.user_id IN (SELECT id FROM users WHERE account_id=?)
           ORDER BY im.created_at DESC''', (aid,)).fetchall()]
    db.execute('''UPDATE inbox_messages SET is_read=1
                  WHERE is_read=0 AND user_id IN (SELECT id FROM users WHERE account_id=?)''', (aid,))
    db.commit()
    return render_template('inbox.html', msgs=msgs, INBOX_KIND_ICON=INBOX_KIND_ICON)


# ── 管理员登录 ────────────────────────────────────────────────────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    db = get_db()
    tenants = [dict(t) for t in db.execute(
        "SELECT * FROM tenants WHERE is_active=1 ORDER BY display_name").fetchall()]
    errors = []
    if request.method == 'POST':
        tid   = request.form.get('tenant_id', '').strip()
        uname = request.form.get('username', '').strip()
        pw    = request.form.get('password', '').strip()
        admin = db.execute("SELECT * FROM tenant_admins WHERE tenant_id=? AND username=? AND is_active=1",
                           (int(tid), uname)).fetchone() if tid else None
        if admin and check_password_hash(admin['password_hash'], pw):
            session['admin_id']           = admin['id']
            session['admin_tenant_id']    = admin['tenant_id']
            session['admin_display_name'] = admin['display_name'] or admin['username']
            return redirect(request.args.get('next') or url_for('admin_orders'))
        errors.append("账户 / 用户名 / 密码错误")
    return render_template('admin_login.html', tenants=tenants, errors=errors)

@app.route('/admin/logout')
def admin_logout():
    for k in ('admin_id', 'admin_tenant_id', 'admin_display_name'):
        session.pop(k, None)
    return redirect(url_for('index'))


# ── 管理员面板 ────────────────────────────────────────────────────────────────

@app.route('/admin/orders')
@require_admin
def admin_orders():
    tid = session['admin_tenant_id']
    db  = get_db()
    sf  = request.args.get('status', '')
    q   = request.args.get('q', '').strip()

    where  = "WHERE o.tenant_id=?"
    params = [tid]
    if sf:
        where += " AND o.status=?"; params.append(sf)
    if q:
        where += " AND (o.order_no LIKE ? OR o.customer_name LIKE ? OR o.title LIKE ?)"
        params += [f'%{q}%', f'%{q}%', f'%{q}%']

    orders = [dict(o) for o in db.execute(
        f'''SELECT o.*, a.display_name AS admin_name,
                   (SELECT COUNT(*) FROM order_notes n
                     WHERE n.order_id=o.id AND n.author_type='customer' AND n.seen_by_admin=0) AS new_notes
            FROM orders o LEFT JOIN tenant_admins a ON a.id=o.assigned_admin
            {where} ORDER BY o.created_at DESC''', params).fetchall()]

    counts = {s: db.execute("SELECT COUNT(*) FROM orders WHERE tenant_id=? AND status=?",
                            (tid, s)).fetchone()[0] for s in ALL_STATUSES}
    counts['all'] = sum(counts.values())

    return render_template('admin_orders.html', orders=orders,
                           sf=sf, q=q, counts=counts)

@app.route('/admin/orders/<int:oid>')
@require_admin
def admin_order_detail(oid):
    tid = session['admin_tenant_id']
    db  = get_db()
    order = db.execute("SELECT * FROM orders WHERE id=? AND tenant_id=?", (oid, tid)).fetchone()
    if not order: abort(404)
    admins       = [dict(a) for a in db.execute("SELECT * FROM tenant_admins WHERE tenant_id=? AND is_active=1", (tid,)).fetchall()]
    images       = [dict(i) for i in db.execute("SELECT * FROM order_images WHERE order_id=?", (oid,)).fetchall()]
    result_imgs  = [dict(i) for i in db.execute("SELECT * FROM order_result_images WHERE order_id=?", (oid,)).fetchall()]
    logs         = [dict(l) for l in db.execute("SELECT * FROM order_logs WHERE order_id=? ORDER BY created_at", (oid,)).fetchall()]
    notes        = _order_notes(db, oid)
    # 打开详情就当接单方看过了客户的备注，列表上的提醒随之消掉
    db.execute("UPDATE order_notes SET seen_by_admin=1 WHERE order_id=? AND author_type='customer' AND seen_by_admin=0", (oid,))
    db.commit()
    return render_template('admin_order_detail.html',
        order=dict(order), admins=admins,
        images=images, result_imgs=result_imgs, logs=logs,
        notes=notes,
        can_append=(order['status'] in ORDER_NOTE_STATUSES),
        NOTE_MAX_LEN=ORDER_NOTE_MAX_LEN)

def _check_order(oid):
    tid = session['admin_tenant_id']
    db  = get_db()
    o   = db.execute("SELECT * FROM orders WHERE id=? AND tenant_id=?", (oid, tid)).fetchone()
    if not o: abort(404)
    return db, dict(o)

@app.route('/admin/orders/<int:oid>/accept', methods=['POST'])
@require_admin
def admin_accept(oid):
    db, o = _check_order(oid)
    if o['status'] != 'pending': flash("当前状态不可接单"); return redirect(url_for('admin_order_detail', oid=oid))
    db.execute("UPDATE orders SET status='accepted', assigned_admin=?, updated_at=? WHERE id=?",
               (session['admin_id'], _now(), oid))
    _add_log(db, oid, '接单', session['admin_display_name'])
    if o.get('user_id'):
        _inbox_add(db, o['tenant_id'], o['user_id'], 'order_accepted',
                   f"你的订单 {o['order_no']}《{o['title']}》已接单，正在排期制作中", o['order_no'])
    db.commit(); flash("已接单")
    return redirect(url_for('admin_order_detail', oid=oid))

@app.route('/admin/orders/<int:oid>/start', methods=['POST'])
@require_admin
def admin_start(oid):
    db, o = _check_order(oid)
    if o['status'] != 'accepted': flash("请先接单"); return redirect(url_for('admin_order_detail', oid=oid))
    db.execute("UPDATE orders SET status='processing', updated_at=? WHERE id=?", (_now(), oid))
    _add_log(db, oid, '开始制作', session['admin_display_name'])
    db.commit(); flash("制作中")
    return redirect(url_for('admin_order_detail', oid=oid))

@app.route('/admin/orders/<int:oid>/complete', methods=['POST'])
@require_admin
def admin_complete(oid):
    db, o = _check_order(oid)
    if o['status'] not in ('accepted', 'processing'):
        flash("当前状态无法完成"); return redirect(url_for('admin_order_detail', oid=oid))

    result_text = request.form.get('result_text', '').strip()
    now = _now()
    db.execute("UPDATE orders SET status='completed', result_text=?, updated_at=? WHERE id=?",
               (result_text, now, oid))
    _add_log(db, oid, '已完成', session['admin_display_name'], result_text[:100])
    if o.get('user_id'):
        _inbox_add(db, o['tenant_id'], o['user_id'], 'order_completed',
                   f"你的订单 {o['order_no']}《{o['title']}》已完成，快去查看成品吧", o['order_no'])

    for f in request.files.getlist('result_images')[:MAX_IMAGES]:
        rel = _save_file(f, oid, 'result')
        if rel:
            db.execute("INSERT INTO order_result_images (order_id,filename,original_name,uploaded_at) VALUES (?,?,?,?)",
                       (oid, rel, f.filename, now))
    db.commit(); flash("订单已完成")
    return redirect(url_for('admin_order_detail', oid=oid))

@app.route('/admin/orders/<int:oid>/reject', methods=['POST'])
@require_admin
def admin_reject(oid):
    db, o = _check_order(oid)
    if o['status'] not in ('pending', 'accepted'):
        flash("当前状态无法拒绝"); return redirect(url_for('admin_order_detail', oid=oid))
    reason = request.form.get('reason', '').strip()
    db.execute("UPDATE orders SET status='rejected', admin_notes=?, updated_at=? WHERE id=?",
               (reason, _now(), oid))
    refunded = bool(o.get('credit_consumed')) and o.get('credit_batch_id')
    if refunded:
        _refund_one_credit(db, o['credit_batch_id'])
    _add_log(db, oid, '已拒绝', session['admin_display_name'], reason)
    if o.get('user_id'):
        msg = f"你的订单 {o['order_no']}《{o['title']}》已被拒绝：{reason or '未说明原因'}"
        if refunded: msg += "，次数已退回账号"
        _inbox_add(db, o['tenant_id'], o['user_id'], 'order_rejected', msg, o['order_no'])
    db.commit(); flash("已拒绝" + ("，次数已退回" if refunded else ""))
    return redirect(url_for('admin_order_detail', oid=oid))

@app.route('/admin/orders/<int:oid>/cancel', methods=['POST'])
@require_admin
def admin_cancel(oid):
    db, o = _check_order(oid)
    db.execute("UPDATE orders SET status='cancelled', updated_at=? WHERE id=?", (_now(), oid))
    refunded = bool(o.get('credit_consumed')) and o.get('credit_batch_id')
    if refunded:
        _refund_one_credit(db, o['credit_batch_id'])
    _add_log(db, oid, '已取消', session['admin_display_name'])
    if o.get('user_id'):
        msg = f"你的订单 {o['order_no']}《{o['title']}》已被取消"
        if refunded: msg += "，次数已退回账号"
        _inbox_add(db, o['tenant_id'], o['user_id'], 'order_cancelled', msg, o['order_no'])
    db.commit(); flash("已取消" + ("，次数已退回" if refunded else ""))
    return redirect(url_for('admin_order_detail', oid=oid))

@app.route('/admin/orders/<int:oid>/note', methods=['POST'])
@require_admin
def admin_note(oid):
    db, o = _check_order(oid)
    note = request.form.get('admin_notes', '').strip()
    db.execute("UPDATE orders SET admin_notes=?, updated_at=? WHERE id=?", (note, _now(), oid))
    _add_log(db, oid, '更新备注', session['admin_display_name'])  # 内部备注正文不写进日志：客户看得到进度记录
    db.commit(); flash("备注已保存")
    return redirect(url_for('admin_order_detail', oid=oid))

@app.route('/admin/orders/<int:oid>/append-note', methods=['POST'])
@require_admin
def admin_append_note(oid):
    """接单方给已接单的订单追加一条备注（客户可见）"""
    db, o = _check_order(oid)
    back = redirect(url_for('admin_order_detail', oid=oid))
    if o['status'] not in ORDER_NOTE_STATUSES:
        flash("只有已接单 / 制作中的订单可以追加备注")
        return back

    content = request.form.get('content', '').strip()
    err = _validate_note(content, db, oid, 'admin')
    if err:
        flash(err)
        return back

    who = session['admin_display_name']
    # 内部备注完全不写进 order_logs：进度记录客户看得到，连"加了内部备注"这件事也不必让客户知道。
    # 备注区块本身带时间和署名，管理端不缺这条记录。
    _add_order_note(db, oid, 'admin', who, content)
    db.commit()
    flash("备注已追加（只有你们自己看得到）")
    return back

@app.route('/admin/orders/<int:oid>/assign', methods=['POST'])
@require_admin
def admin_assign(oid):
    db, o = _check_order(oid)
    aid = request.form.get('admin_id', '').strip()
    aid = int(aid) if aid and aid.isdigit() else None
    db.execute("UPDATE orders SET assigned_admin=?, updated_at=? WHERE id=?", (aid, _now(), oid))
    _add_log(db, oid, '分配负责人', session['admin_display_name'])
    db.commit(); flash("已分配")
    return redirect(url_for('admin_order_detail', oid=oid))

@app.route('/admin/users')
@require_admin
def admin_users():
    tid = session['admin_tenant_id']
    db  = get_db()
    users = [dict(u) for u in db.execute(
        "SELECT * FROM users WHERE tenant_id=? ORDER BY created_at DESC", (tid,)).fetchall()]
    for u in users:
        u['credit_available'] = _credit_available(db, u['id'])
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/<int:uid>/toggle', methods=['POST'])
@require_admin
def admin_toggle_user(uid):
    tid = session['admin_tenant_id']
    db  = get_db()
    u   = db.execute("SELECT * FROM users WHERE id=? AND tenant_id=?", (uid, tid)).fetchone()
    if not u: abort(404)
    db.execute("UPDATE users SET is_active=? WHERE id=?", (0 if u['is_active'] else 1, uid))
    db.commit()
    return redirect(url_for('admin_users'))


# ── 次数审批 ──────────────────────────────────────────────────────────────────

@app.route('/admin/credits')
@require_admin
def admin_credits():
    tid = session['admin_tenant_id']
    db  = get_db()
    sf  = request.args.get('status', 'pending')

    where  = "WHERE cr.tenant_id=?"
    params = [tid]
    if sf and sf != 'all':
        where += " AND cr.status=?"; params.append(sf)

    reqs = [dict(r) for r in db.execute(
        f'''SELECT cr.*, u.username AS user_username, u.display_name AS user_display_name, u.contact AS user_contact,
                   cp.title AS pool_title
            FROM credit_requests cr JOIN users u ON u.id=cr.user_id
            LEFT JOIN credit_pools cp ON cp.id=cr.pool_id
            {where} ORDER BY cr.created_at DESC''', params).fetchall()]

    counts = {s: db.execute("SELECT COUNT(*) FROM credit_requests WHERE tenant_id=? AND status=?",
                            (tid, s)).fetchone()[0] for s in CREDIT_STATUS_LABEL}
    counts['all'] = sum(counts.values())

    pools = _pools_for_tenant(db, tid, active_only=False)
    return render_template('admin_credits.html', reqs=reqs, sf=sf, counts=counts, pools=pools)

@app.route('/admin/credits/pools/<int:pid>/approval-mode', methods=['POST'])
@require_admin
def admin_pool_approval_mode(pid):
    """切换某一批单口的"领取需要审批"。关掉之后会员抢到这批名额直接到账。"""
    tid = session['admin_tenant_id']
    db  = get_db()
    pool = db.execute("SELECT * FROM credit_pools WHERE id=? AND tenant_id=?", (pid, tid)).fetchone()
    if not pool: abort(404)
    need = 1 if request.form.get('need_approval') else 0
    db.execute("UPDATE credit_pools SET need_approval=? WHERE id=?", (need, pid))
    db.commit()
    name = pool['title'] or '未命名单口'
    flash(f"「{name}」已开启领取审批，会员领取后需要你确认才到账" if need
          else f"「{name}」已关闭领取审批，会员抢到名额后直接到账")
    return redirect(url_for('admin_credits'))

@app.route('/admin/credits/pools/new', methods=['POST'])
@require_admin
def admin_pool_new():
    tid = session['admin_tenant_id']
    db  = get_db()
    title = request.form.get('title', '').strip()
    units_list = request.form.getlist('denom_units')
    count_list = request.form.getlist('denom_count')
    denoms = []
    for u_raw, c_raw in zip(units_list, count_list):
        try:
            units = int(u_raw); count = int(c_raw)
        except ValueError:
            continue
        if units < 1 or units > 999 or count < 1 or count > 9999:
            continue
        denoms.append((units, count))
    if not denoms:
        flash("请至少填写一档正确的面值和张数")
        return redirect(url_for('admin_credits'))
    days_raw = request.form.get('valid_days', '').strip()
    valid_days = int(days_raw) if days_raw.isdigit() and int(days_raw) > 0 else None
    fixed_expires_at = None
    date_raw = request.form.get('fixed_expires_date', '').strip()
    if date_raw:
        try:
            fixed_expires_at = int(datetime.strptime(date_raw, '%Y-%m-%d').timestamp()) + 86399
            valid_days = None  # 固定日期优先，天数二选一
        except ValueError:
            pass
    total_units = sum(u * c for u, c in denoms)
    card_total  = sum(c for u, c in denoms)
    now = _now()
    need_approval = 1 if request.form.get('need_approval') else 0
    cur = db.execute('''INSERT INTO credit_pools
        (tenant_id,title,total_units,valid_days,fixed_expires_at,status,created_by,created_at,need_approval)
        VALUES (?,?,?,?,?,?,?,?,?)''',
        (tid, title, total_units, valid_days, fixed_expires_at, 'active',
         session['admin_display_name'], now, need_approval))
    pool_id = cur.lastrowid
    for units, count in denoms:
        db.execute("INSERT INTO credit_pool_denoms (pool_id,units,count,created_at) VALUES (?,?,?,?)",
                   (pool_id, units, count, now))
    db.commit()
    mode_note = "领取后需要你在下面审批才到账" if need_approval else "免审批，抢到直接到账"
    flash(f"已放出 {card_total} 张卡，共 {total_units} 次（{mode_note}），会员可以在「获得下单次数」页领取")
    return redirect(url_for('admin_credits'))

@app.route('/admin/credits/pools/<int:pid>/close', methods=['POST'])
@require_admin
def admin_pool_close(pid):
    tid = session['admin_tenant_id']
    db  = get_db()
    pool = db.execute("SELECT * FROM credit_pools WHERE id=? AND tenant_id=?", (pid, tid)).fetchone()
    if not pool: abort(404)
    db.execute("UPDATE credit_pools SET status='closed' WHERE id=?", (pid,))
    db.commit()
    flash("已关闭该单口，未被领取的名额不再开放")
    return redirect(url_for('admin_credits'))

@app.route('/admin/credits/<int:rid>/approve', methods=['POST'])
@require_admin
def admin_credit_approve(rid):
    tid = session['admin_tenant_id']
    db  = get_db()
    r = db.execute("SELECT * FROM credit_requests WHERE id=? AND tenant_id=?", (rid, tid)).fetchone()
    if not r: abort(404)
    if r['status'] != 'pending':
        flash("该申请已处理"); return redirect(url_for('admin_credits'))
    now = _now()
    if r['pool_id']:
        # 单口信息的领取：有效期跟随发布该单口时定好的规则，不再单独填
        pool = db.execute("SELECT * FROM credit_pools WHERE id=?", (r['pool_id'],)).fetchone()
        valid_days = pool['valid_days'] if pool else None
        fixed_expires_at = pool['fixed_expires_at'] if pool else None
    else:
        days_raw = request.form.get('expires_days', '').strip()
        valid_days = int(days_raw) if days_raw.isdigit() and int(days_raw) > 0 else None
        fixed_expires_at = None
        date_raw = request.form.get('expires_fixed_date', '').strip()
        if date_raw:
            try:
                fixed_expires_at = int(datetime.strptime(date_raw, '%Y-%m-%d').timestamp()) + 86399
                valid_days = None  # 固定日期优先，天数二选一
            except ValueError:
                pass
    expires_at = _resolve_expires_at(valid_days=valid_days, fixed_expires_at=fixed_expires_at)
    _grant_credit_batch(db, tid, r['user_id'], r['units'], 'credit_request', rid, expires_at)
    db.execute("UPDATE credit_requests SET status='approved', decided_at=?, decided_by=? WHERE id=?",
               (now, session['admin_id'], rid))
    if fixed_expires_at:
        expiry_note = f"，有效期至 {_fmt(fixed_expires_at)}"
    elif valid_days:
        expiry_note = f"，{valid_days} 天内有效"
    else:
        expiry_note = "，永久有效"
    _inbox_add(db, tid, r['user_id'], 'credit_approved',
               f"你申请的 {r['units']} 次下单次数已通过审核{expiry_note}，可以立刻下单")
    db.commit()
    flash(f"已通过，{r['units']} 次已到账" + expiry_note)
    return redirect(url_for('admin_credits'))

@app.route('/admin/credits/<int:rid>/reject', methods=['POST'])
@require_admin
def admin_credit_reject(rid):
    tid = session['admin_tenant_id']
    db  = get_db()
    r = db.execute("SELECT * FROM credit_requests WHERE id=? AND tenant_id=?", (rid, tid)).fetchone()
    if not r: abort(404)
    if r['status'] != 'pending':
        flash("该申请已处理"); return redirect(url_for('admin_credits'))
    admin_note = request.form.get('admin_note', '').strip()
    db.execute("UPDATE credit_requests SET status='rejected', admin_note=?, decided_at=?, decided_by=? WHERE id=?",
               (admin_note, _now(), session['admin_id'], rid))
    _inbox_add(db, tid, r['user_id'], 'credit_rejected',
               f"你申请的 {r['units']} 次下单次数未通过审核" + (f"：{admin_note}" if admin_note else ""))
    db.commit()
    flash("已拒绝该申请")
    return redirect(url_for('admin_credits'))


# ── 礼品兑换码 ────────────────────────────────────────────────────────────────

@app.route('/admin/redeem-codes')
@require_admin
def admin_redeem_codes():
    tid = session['admin_tenant_id']
    db  = get_db()
    sf  = request.args.get('status', 'all')
    batch_f = request.args.get('batch', '')

    where  = "WHERE rc.tenant_id=?"
    params = [tid]
    if sf and sf != 'all':
        where += " AND rc.status=?"; params.append(sf)
    if batch_f:
        where += " AND rc.batch_id=?"; params.append(batch_f)

    codes = [dict(c) for c in db.execute(
        f'''SELECT rc.*, u.display_name AS redeemed_by_name, u.username AS redeemed_by_username, u.contact AS redeemed_by_contact
            FROM redeem_codes rc LEFT JOIN users u ON u.id=rc.redeemed_by
            {where} ORDER BY rc.created_at DESC''', params).fetchall()]

    counts = {
        'unused':   db.execute("SELECT COUNT(*) FROM redeem_codes WHERE tenant_id=? AND status='unused'", (tid,)).fetchone()[0],
        'redeemed': db.execute("SELECT COUNT(*) FROM redeem_codes WHERE tenant_id=? AND status='redeemed'", (tid,)).fetchone()[0],
    }
    counts['all'] = counts['unused'] + counts['redeemed']

    return render_template('admin_redeem_codes.html', codes=codes, sf=sf, counts=counts, batch_f=batch_f)

@app.route('/admin/redeem-codes/generate', methods=['POST'])
@require_admin
def admin_redeem_generate():
    tid = session['admin_tenant_id']
    db  = get_db()
    batch_note = request.form.get('batch_note', '').strip()
    units_list = request.form.getlist('denom_units')
    count_list = request.form.getlist('denom_count')
    days_list  = request.form.getlist('denom_days')
    date_list  = request.form.getlist('denom_fixed_date')
    batch_id   = secrets.token_hex(4)
    now        = _now()
    created    = []

    for u_raw, c_raw, d_raw, date_raw in zip(units_list, count_list, days_list, date_list):
        try:
            units = int(u_raw); count = int(c_raw)
        except ValueError:
            continue
        if units < 1 or count < 1:
            continue
        d_raw = (d_raw or '').strip()
        valid_days = int(d_raw) if d_raw.isdigit() and int(d_raw) > 0 else None
        fixed_expires_at = None
        date_raw = (date_raw or '').strip()
        if date_raw:
            try:
                fixed_expires_at = int(datetime.strptime(date_raw, '%Y-%m-%d').timestamp()) + 86399
                valid_days = None  # 固定日期优先，天数二选一
            except ValueError:
                pass
        if len(created) + count > 500:
            flash("单次最多生成 500 个兑换码，请分批生成")
            break
        for _ in range(count):
            code = _gen_redeem_code(db)
            db.execute('''INSERT INTO redeem_codes
                (tenant_id,code,units,batch_id,batch_note,status,created_by,valid_days,fixed_expires_at,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (tid, code, units, batch_id, batch_note, 'unused', session['admin_id'],
                 valid_days, fixed_expires_at, now))
            created.append(code)

    if not created:
        flash("请至少填写一组有效的「次数 × 个数」")
        return redirect(url_for('admin_redeem_codes'))

    db.commit()
    flash(f"已生成 {len(created)} 个兑换码")
    return redirect(url_for('admin_redeem_codes', status='unused', batch=batch_id))


# ── 超管 ──────────────────────────────────────────────────────────────────────

@app.route('/superadmin/login', methods=['GET', 'POST'])
def superadmin_login():
    errors = []
    if request.method == 'POST':
        if request.form.get('password', '') == SUPERADMIN_PASS:
            session['superadmin'] = True
            return redirect(request.args.get('next') or url_for('superadmin_index'))
        errors.append("密码错误")
    return render_template('superadmin_login.html', errors=errors)

@app.route('/superadmin/logout')
def superadmin_logout():
    session.pop('superadmin', None)
    return redirect(url_for('index'))

@app.route('/superadmin/')
@require_superadmin
def superadmin_index():
    db = get_db()
    tenants = [dict(t) for t in db.execute('''
        SELECT t.*,
               COUNT(DISTINCT ta.id) AS admin_count,
               COUNT(DISTINCT u.id)  AS user_count,
               COUNT(DISTINCT o.id)  AS order_count,
               (SELECT COUNT(*) FROM orders o2
                  WHERE o2.tenant_id=t.id AND o2.status='pending') AS pending_count
        FROM tenants t
        LEFT JOIN tenant_admins ta ON ta.tenant_id=t.id AND ta.is_active=1
        LEFT JOIN users u          ON u.tenant_id=t.id  AND u.is_active=1
        LEFT JOIN orders o         ON o.tenant_id=t.id
        GROUP BY t.id ORDER BY t.created_at DESC
    ''').fetchall()]
    return render_template('superadmin.html', tenants=tenants)

@app.route('/superadmin/users')
@require_superadmin
def superadmin_users():
    """全站账号总览：注册信息 + 下过多少单 + 手里还有多少次数"""
    db = get_db()
    q  = request.args.get('q', '').strip()

    where, params = "", []
    if q:
        where = "WHERE a.username LIKE ? OR a.display_name LIKE ? OR a.contact LIKE ?"
        params = [f'%{q}%'] * 3

    accounts = [dict(a) for a in db.execute(
        f"SELECT id, username, display_name, contact, is_active, created_at FROM accounts a "
        f"{where} ORDER BY a.created_at DESC", params).fetchall()]

    tenant_names = {t['id']: (t['display_name'] or t['slug'])
                    for t in db.execute("SELECT id, slug, display_name FROM tenants").fetchall()}

    for a in accounts:
        rows = db.execute(
            "SELECT id, tenant_id, display_name, contact FROM users WHERE account_id=?", (a['id'],)).fetchall()
        parts, total_credits, total_locked, total_orders, done_orders = [], 0, 0, 0, 0
        for m in rows:
            avail  = _credit_available(db, m['id'])
            locked = _credit_locked_total(db, m['id'])
            cnt    = db.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (m['id'],)).fetchone()[0]
            done   = db.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND status='completed'",
                                (m['id'],)).fetchone()[0]
            total_credits += avail
            total_locked  += locked
            total_orders  += cnt
            done_orders   += done
            parts.append({
                'tenant': tenant_names.get(m['tenant_id'], f"#{m['tenant_id']}"),
                'credits': avail, 'locked': locked, 'orders': cnt,
                # 会员在各家登记的昵称/联系方式可能跟注册时填的不一样，一并列出来
                'display_name': m['display_name'], 'contact': m['contact'],
            })
        a['parts']         = sorted(parts, key=lambda x: (-x['credits'], x['tenant']))
        a['total_credits'] = total_credits
        a['total_locked']  = total_locked
        a['total_orders']  = total_orders
        a['done_orders']   = done_orders

    totals = {
        'accounts': len(accounts),
        'credits':  sum(a['total_credits'] for a in accounts),
        'locked':   sum(a['total_locked'] for a in accounts),
        'orders':   sum(a['total_orders'] for a in accounts),
    }
    return render_template('superadmin_users.html', accounts=accounts, q=q, totals=totals)

@app.route('/superadmin/trades')
@require_superadmin
def superadmin_trades():
    db = get_db()
    rows = [dict(r) for r in db.execute('''
        SELECT t.*, tn.display_name AS tenant_name, tn.slug AS tenant_slug,
               pu.display_name AS poster_name, pu.username AS poster_username, pu.contact AS poster_contact,
               tu.display_name AS taker_name, tu.username AS taker_username, tu.contact AS taker_contact
        FROM trades t
        JOIN tenants tn ON tn.id=t.tenant_id
        JOIN users pu ON pu.id=t.poster_id
        JOIN users tu ON tu.id=t.taker_id
        WHERE t.dispute_status != '' ORDER BY t.dispute_at DESC
    ''').fetchall()]
    for r in rows:
        r['complainant_name'] = r['poster_name'] if r['dispute_by'] == r['poster_id'] else r['taker_name']
        r['other_name'] = r['taker_name'] if r['dispute_by'] == r['poster_id'] else r['poster_name']
    return render_template('superadmin_trades.html', trades=rows, arbitration_qq=ARBITRATION_QQ)

@app.route('/superadmin/trades/<int:trade_id>/resolve', methods=['POST'])
@require_superadmin
def superadmin_trade_resolve(trade_id):
    db = get_db()
    t = db.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
    if not t: abort(404)
    if t['dispute_status'] != 'pending':
        flash("该仲裁已处理"); return redirect(url_for('superadmin_trades'))
    action = request.form.get('action', '')
    now = _now()
    complainant = t['dispute_by']
    other = t['taker_id'] if complainant == t['poster_id'] else t['poster_id']

    if action == 'reverse':
        recovered = 0
        if t['disputed_batch_id']:
            b = db.execute("SELECT * FROM credit_batches WHERE id=?", (t['disputed_batch_id'],)).fetchone()
            if b:
                recovered = b['units_left']
                if recovered > 0:
                    db.execute("UPDATE credit_batches SET units_left=0, status='expired' WHERE id=?",
                               (t['disputed_batch_id'],))
                    _grant_credit_batch(db, t['tenant_id'], complainant, recovered, 'trade_reversal',
                                        trade_id, b['expires_at'])
                else:
                    db.execute("UPDATE credit_batches SET status='expired' WHERE id=?", (t['disputed_batch_id'],))
        db.execute("UPDATE trades SET dispute_status='resolved_reversed', updated_at=? WHERE id=?", (now, trade_id))
        _inbox_add(db, t['tenant_id'], complainant, 'dispute_resolved',
                   f"仲裁已处理：已从对方冻结并转回 {recovered} 次给你" if recovered else "仲裁已处理：对方次数已冻结，但可追回的次数为 0（可能已被使用）")
        _inbox_add(db, t['tenant_id'], other, 'dispute_resolved', "仲裁已处理：相关次数已被冻结并转回对方")
        flash(f"已冻结并转回 {recovered} 次")
    elif action == 'reject':
        if t['disputed_batch_id']:
            db.execute("UPDATE credit_batches SET status='active' WHERE id=?", (t['disputed_batch_id'],))
        db.execute("UPDATE trades SET dispute_status='resolved_rejected', updated_at=? WHERE id=?", (now, trade_id))
        _inbox_add(db, t['tenant_id'], complainant, 'dispute_resolved', "仲裁申请已被驳回")
        _inbox_add(db, t['tenant_id'], other, 'dispute_resolved', "针对你的仲裁申请已被驳回，相关次数已解冻")
        flash("已驳回仲裁申请，次数已解冻")
    else:
        flash("未知操作"); return redirect(url_for('superadmin_trades'))

    db.commit()
    return redirect(url_for('superadmin_trades'))

@app.route('/superadmin/tenants/new', methods=['GET', 'POST'])
@require_superadmin
def superadmin_tenant_new():
    errors = []
    if request.method == 'POST':
        slug    = request.form.get('slug', '').strip().lower()
        name    = request.form.get('display_name', '').strip()
        desc    = request.form.get('description', '').strip()
        au      = request.form.get('admin_username', '').strip()
        ap      = request.form.get('admin_password', '').strip()
        adn     = request.form.get('admin_display_name', '').strip() or au

        if not slug or not re.match(r'^[a-z0-9_-]+$', slug):
            errors.append("Slug 只能用小写字母、数字、-、_")
        if not name: errors.append("请填写账户名称")
        if not au or len(au) < 3: errors.append("管理员用户名至少 3 字符")
        if not ap or len(ap) < 6: errors.append("管理员密码至少 6 字符")
        if not errors:
            db = get_db()
            if db.execute("SELECT id FROM tenants WHERE slug=?", (slug,)).fetchone():
                errors.append("Slug 已被占用")
        if not errors:
            db  = get_db()
            tok = secrets.token_urlsafe(32)
            now = _now()
            db.execute("INSERT INTO tenants (slug,display_name,description,service_types,api_token,is_active,created_at) VALUES (?,?,?,?,?,1,?)",
                       (slug, name, desc, json.dumps(DEFAULT_SERVICE_TYPES, ensure_ascii=False), tok, now))
            db.commit()
            tid = db.execute("SELECT id FROM tenants WHERE slug=?", (slug,)).fetchone()['id']
            db.execute("INSERT INTO tenant_admins (tenant_id,username,password_hash,display_name,is_active,created_at) VALUES (?,?,?,?,1,?)",
                       (tid, au, generate_password_hash(ap), adn, now))
            db.commit()
            flash(f"账户已创建 | API Token: {tok}")
            return redirect(url_for('superadmin_tenant', tid=tid))
    return render_template('superadmin_tenant_new.html', errors=errors)

@app.route('/superadmin/tenants/<int:tid>', methods=['GET', 'POST'])
@require_superadmin
def superadmin_tenant(tid):
    db = get_db()
    tenant = db.execute("SELECT * FROM tenants WHERE id=?", (tid,)).fetchone()
    if not tenant: abort(404)

    errors = []
    if request.method == 'POST':
        action = request.form.get('action', '')

        if action == 'update':
            name = request.form.get('display_name', '').strip()
            desc = request.form.get('description', '').strip()
            st   = [s.strip() for s in request.form.get('service_types', '').split('\n') if s.strip()]
            if not st: st = DEFAULT_SERVICE_TYPES
            active = 1 if request.form.get('is_active') else 0
            if name:
                db.execute("UPDATE tenants SET display_name=?,description=?,service_types=?,is_active=? WHERE id=?",
                           (name, desc, json.dumps(st, ensure_ascii=False), active, tid))
                db.commit(); flash("已保存")

        elif action == 'regen_token':
            tok = secrets.token_urlsafe(32)
            db.execute("UPDATE tenants SET api_token=? WHERE id=?", (tok, tid))
            db.commit(); flash(f"新 API Token：{tok}")

        elif action == 'add_admin':
            au  = request.form.get('new_admin_username', '').strip()
            ap  = request.form.get('new_admin_password', '').strip()
            adn = request.form.get('new_admin_display_name', '').strip() or au
            if not au or len(au) < 3: errors.append("用户名至少 3 字符")
            elif not ap or len(ap) < 6: errors.append("密码至少 6 字符")
            elif db.execute("SELECT id FROM tenant_admins WHERE tenant_id=? AND username=?", (tid, au)).fetchone():
                errors.append("管理员用户名已存在")
            else:
                db.execute("INSERT INTO tenant_admins (tenant_id,username,password_hash,display_name,is_active,created_at) VALUES (?,?,?,?,1,?)",
                           (tid, au, generate_password_hash(ap), adn, _now()))
                db.commit(); flash(f"管理员 {au} 已添加")

        elif action == 'toggle_admin':
            aid = request.form.get('admin_id', '')
            if aid and aid.isdigit():
                a = db.execute("SELECT * FROM tenant_admins WHERE id=? AND tenant_id=?", (int(aid), tid)).fetchone()
                if a:
                    cnt = db.execute("SELECT COUNT(*) FROM tenant_admins WHERE tenant_id=? AND is_active=1", (tid,)).fetchone()[0]
                    if a['is_active'] and cnt <= 1:
                        errors.append("至少保留一个启用的管理员")
                    else:
                        db.execute("UPDATE tenant_admins SET is_active=? WHERE id=?", (0 if a['is_active'] else 1, int(aid)))
                        db.commit(); flash("管理员状态已更新")

        elif action == 'reset_admin_pw':
            aid = request.form.get('admin_id', '')
            np  = request.form.get('new_password', '').strip()
            if not np or len(np) < 6: errors.append("新密码至少 6 字符")
            elif aid and aid.isdigit():
                db.execute("UPDATE tenant_admins SET password_hash=? WHERE id=? AND tenant_id=?",
                           (generate_password_hash(np), int(aid), tid))
                db.commit(); flash("密码已重置")

        elif action == 'delete_admin':
            aid = request.form.get('admin_id', '')
            if aid and aid.isdigit():
                cnt = db.execute("SELECT COUNT(*) FROM tenant_admins WHERE tenant_id=?", (tid,)).fetchone()[0]
                if cnt <= 1: errors.append("至少保留一个管理员")
                else:
                    db.execute("DELETE FROM tenant_admins WHERE id=? AND tenant_id=?", (int(aid), tid))
                    db.commit(); flash("已删除管理员")

        elif action == 'reset_data':
            confirm_name = request.form.get('confirm_name', '').strip()
            tenant_name  = (tenant['display_name'] or tenant['slug'])
            if confirm_name != tenant_name:
                errors.append(f"确认名称不匹配，请输入「{tenant_name}」")
            else:
                # 1. 删除订单图片文件
                order_ids = [r[0] for r in db.execute(
                    "SELECT id FROM orders WHERE tenant_id=?", (tid,)).fetchall()]
                for oid in order_ids:
                    _delete_order_files(oid)
                # 2. 清空订单相关表
                db.execute("DELETE FROM order_images       WHERE order_id IN (SELECT id FROM orders WHERE tenant_id=?)", (tid,))
                db.execute("DELETE FROM order_result_images WHERE order_id IN (SELECT id FROM orders WHERE tenant_id=?)", (tid,))
                db.execute("DELETE FROM order_logs         WHERE order_id IN (SELECT id FROM orders WHERE tenant_id=?)", (tid,))
                db.execute("DELETE FROM order_notes        WHERE order_id IN (SELECT id FROM orders WHERE tenant_id=?)", (tid,))
                db.execute("DELETE FROM orders WHERE tenant_id=?", (tid,))
                # 3. 清空 bot snapshot（该 tenant 前缀的 key）
                db.execute("DELETE FROM bot_snapshot WHERE key LIKE ?", (f"{tid}_%",))
                # 4. 清空 bot 用户
                db.execute("DELETE FROM bot_users WHERE tenant_id=?", (tid,))
                # 5. 清空次数申请记录
                db.execute("DELETE FROM credit_requests WHERE tenant_id=?", (tid,))
                # 6. 清空兑换码
                db.execute("DELETE FROM redeem_codes WHERE tenant_id=?", (tid,))
                # 7. 清空 web 注册用户
                db.execute("DELETE FROM users WHERE tenant_id=?", (tid,))
                db.commit()
                flash(f"✅ 已重置「{tenant_name}」的全部数据（共 {len(order_ids)} 条订单）")
                return redirect(url_for('superadmin_tenant', tid=tid))

        tenant = db.execute("SELECT * FROM tenants WHERE id=?", (tid,)).fetchone()

    admins = [dict(a) for a in db.execute(
        "SELECT * FROM tenant_admins WHERE tenant_id=? ORDER BY created_at", (tid,)).fetchall()]
    stats = {
        'orders':  db.execute("SELECT COUNT(*) FROM orders WHERE tenant_id=?",                       (tid,)).fetchone()[0],
        'users':   db.execute("SELECT COUNT(*) FROM users WHERE tenant_id=?",                        (tid,)).fetchone()[0],
        'pending': db.execute("SELECT COUNT(*) FROM orders WHERE tenant_id=? AND status='pending'",  (tid,)).fetchone()[0],
    }
    st_str = '\n'.join(_service_types(dict(tenant)))

    return render_template('superadmin_tenant.html',
        tenant=dict(tenant), admins=admins, stats=stats,
        st_str=st_str, errors=errors)


# ── API（长日系统 对接）───────────────────────────────────────────────────────

def _api_tenant():
    tok = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
    if not tok: tok = request.args.get('token', '') or (request.get_json(silent=True) or {}).get('token', '')
    if not tok:
        return None, (jsonify({"ok": False, "error": "缺少 token"}), 401)
    t = get_db().execute("SELECT * FROM tenants WHERE api_token=? AND is_active=1", (tok,)).fetchone()
    if not t:
        return None, (jsonify({"ok": False, "error": "token 无效"}), 403)
    return dict(t), None

@app.route('/api/sync', methods=['GET'])
def api_sync():
    """返回尚未推送给 bot 的新待处理订单（含图片完整 URL），并标记为已推送"""
    tenant, err = _api_tenant()
    if err: return err
    db       = get_db()
    base_url = request.host_url.rstrip('/')
    rows     = db.execute(
        "SELECT * FROM orders WHERE tenant_id=? AND bot_notified=0 AND status='pending' ORDER BY created_at",
        (tenant['id'],)).fetchall()
    result = []
    for o in rows:
        o = dict(o)
        imgs = db.execute("SELECT * FROM order_images WHERE order_id=?", (o['id'],)).fetchall()
        o['images']       = [{'url': f"{base_url}/uploads/{i['filename']}",
                               'original_name': i['original_name']} for i in imgs]
        o['status_label'] = STATUS_LABEL.get(o['status'], o['status'])
        o['created_fmt']  = _fmt(o['created_at'])
        result.append(o)
    if result:
        ids = [o['id'] for o in result]
        db.execute(f"UPDATE orders SET bot_notified=1 WHERE id IN ({','.join('?'*len(ids))})", ids)
        db.commit()
    return jsonify({"ok": True, "orders": result, "count": len(result)})

@app.route('/api/orders/<order_no>/reject', methods=['POST'])
def api_reject(order_no):
    tenant, err = _api_tenant()
    if err: return err
    db = get_db()
    o  = db.execute("SELECT * FROM orders WHERE order_no=? AND tenant_id=?", (order_no, tenant['id'])).fetchone()
    if not o: return jsonify({"ok": False, "error": "订单不存在"}), 404
    if o['status'] not in ('pending', 'accepted'):
        return jsonify({"ok": False, "error": f"订单已是「{STATUS_LABEL.get(o['status'])}」，无法拒绝"}), 400
    data   = request.get_json(silent=True) or {}
    reason = data.get('reason', '')
    db.execute("UPDATE orders SET status='rejected', admin_notes=?, updated_at=? WHERE order_no=? AND tenant_id=?",
               (reason, _now(), order_no, tenant['id']))
    refunded = bool(o['credit_consumed']) and o['credit_batch_id']
    if refunded:
        _refund_one_credit(db, o['credit_batch_id'])
    _add_log(db, o['id'], '已拒绝(机器人)', f"bot:{tenant['slug']}", reason)
    if o['user_id']:
        msg = f"你的订单 {order_no}《{o['title']}》已被拒绝：{reason or '未说明原因'}"
        if refunded: msg += "，次数已退回账号"
        _inbox_add(db, tenant['id'], o['user_id'], 'order_rejected', msg, order_no)
    db.commit()
    _delete_order_files(o['id'])
    return jsonify({"ok": True, "order_no": order_no, "status": "rejected"})

@app.route('/api/orders', methods=['GET'])
def api_list_orders():
    tenant, err = _api_tenant()
    if err: return err
    db     = get_db()
    status = request.args.get('status', 'pending')
    limit  = min(int(request.args.get('limit', 20)), 100)
    q      = "SELECT * FROM orders WHERE tenant_id=?" + ("" if status == 'all' else " AND status=?") + " ORDER BY created_at DESC LIMIT ?"
    params = [tenant['id']] + ([] if status == 'all' else [status]) + [limit]
    rows   = []
    for o in db.execute(q, params).fetchall():
        o = dict(o)
        o['images_count'] = db.execute("SELECT COUNT(*) FROM order_images WHERE order_id=?", (o['id'],)).fetchone()[0]
        o['status_label'] = STATUS_LABEL.get(o['status'], o['status'])
        o['created_fmt']  = _fmt(o['created_at'])
        rows.append(o)
    return jsonify({"ok": True, "orders": rows, "count": len(rows)})

@app.route('/api/orders/<order_no>', methods=['GET'])
def api_get_order(order_no):
    tenant, err = _api_tenant()
    if err: return err
    db = get_db()
    o  = db.execute("SELECT * FROM orders WHERE order_no=? AND tenant_id=?", (order_no, tenant['id'])).fetchone()
    if not o: return jsonify({"ok": False, "error": "订单不存在"}), 404
    o = dict(o)
    o['status_label'] = STATUS_LABEL.get(o['status'], o['status'])
    o['created_fmt']  = _fmt(o['created_at'])
    notes = _order_notes(db, o['id'], author_type='customer')
    for n in notes:
        n['created_fmt'] = _fmt(n['created_at'])
    o['notes'] = notes
    o['new_notes'] = sum(1 for n in notes if not n.get('seen_by_admin'))
    return jsonify({"ok": True, "order": o, "notes": notes})

@app.route('/api/orders/<order_no>/accept', methods=['POST'])
def api_accept(order_no):
    tenant, err = _api_tenant()
    if err: return err
    db = get_db()
    o  = db.execute("SELECT * FROM orders WHERE order_no=? AND tenant_id=?", (order_no, tenant['id'])).fetchone()
    if not o: return jsonify({"ok": False, "error": "订单不存在"}), 404
    if o['status'] != 'pending':
        return jsonify({"ok": False, "error": f"订单状态为「{STATUS_LABEL.get(o['status'])}」，无法接单"}), 400
    data = request.get_json(silent=True) or {}
    note = data.get('note', '')
    db.execute("UPDATE orders SET status='accepted', updated_at=? WHERE order_no=? AND tenant_id=?",
               (_now(), order_no, tenant['id']))
    _add_log(db, o['id'], '接单(机器人)', f"bot:{tenant['slug']}", note)
    if o['user_id']:
        _inbox_add(db, tenant['id'], o['user_id'], 'order_accepted',
                   f"你的订单 {order_no}《{o['title']}》已接单，正在排期制作中", order_no)
    db.commit()
    return jsonify({"ok": True, "order_no": order_no, "status": "accepted"})

@app.route('/api/orders/<order_no>/complete', methods=['POST'])
def api_complete(order_no):
    tenant, err = _api_tenant()
    if err: return err
    db = get_db()
    o  = db.execute("SELECT * FROM orders WHERE order_no=? AND tenant_id=?", (order_no, tenant['id'])).fetchone()
    if not o: return jsonify({"ok": False, "error": "订单不存在"}), 404
    if o['status'] not in ('pending', 'accepted', 'processing'):
        return jsonify({"ok": False, "error": f"订单已是「{STATUS_LABEL.get(o['status'])}」"}), 400
    data        = request.get_json(silent=True) or {}
    result_text = data.get('result_text', '')
    db.execute("UPDATE orders SET status='completed', result_text=?, updated_at=? WHERE order_no=? AND tenant_id=?",
               (result_text, _now(), order_no, tenant['id']))
    _add_log(db, o['id'], '已完成(机器人)', f"bot:{tenant['slug']}", result_text[:100])
    if o['user_id']:
        _inbox_add(db, tenant['id'], o['user_id'], 'order_completed',
                   f"你的订单 {order_no}《{o['title']}》已完成，快去查看成品吧", order_no)
    db.commit()
    notify = (f"[排单宝] 您的订单 {order_no} 已完成！\n"
              f"标题：{o['title']}\n" +
              (f"说明：{result_text}\n" if result_text else '') +
              f"查看详情：/order/{order_no}")
    _delete_order_files(o['id'])
    return jsonify({"ok": True, "order_no": order_no, "status": "completed", "notify_message": notify})

@app.route('/api/orders/<order_no>/note', methods=['POST'])
def api_note(order_no):
    tenant, err = _api_tenant()
    if err: return err
    db   = get_db()
    o    = db.execute("SELECT * FROM orders WHERE order_no=? AND tenant_id=?", (order_no, tenant['id'])).fetchone()
    if not o: return jsonify({"ok": False, "error": "订单不存在"}), 404
    data = request.get_json(silent=True) or {}
    note = data.get('note', '')
    db.execute("UPDATE orders SET admin_notes=?, updated_at=? WHERE order_no=? AND tenant_id=?",
               (note, _now(), order_no, tenant['id']))
    _add_log(db, o['id'], '备注(机器人)', f"bot:{tenant['slug']}")  # 同上，正文不入日志
    db.commit()
    return jsonify({"ok": True, "order_no": order_no})

@app.route('/api/bot/push', methods=['POST'])
def api_bot_push():
    """排单宝.js 把 storage 数据 push 到网页端；同时把 bot 已管理的散单状态同步回 Flask DB"""
    tenant, err = _api_tenant()
    if err: return err
    data = request.get_json(silent=True) or {}
    db   = get_db()
    now  = _now()
    tid_prefix = str(tenant['id'])
    for key in ('paidan_orders', 'paidan_users', 'paidan_config', 'paidan_adminList'):
        if key in data:
            tkey = f"{tid_prefix}_{key}"  # 按 tenant 隔离
            db.execute("INSERT INTO bot_snapshot(key,data,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                       (tkey, json.dumps(data[key], ensure_ascii=False), now))

    # ── 把 bot 侧对散单的状态变更同步回 Flask orders 表 ──────────────────────
    BOT_TO_FLASK = {
        '待接单':  'pending',
        '制作中':  'processing',
        '草图阶段': 'processing',
        '已完成':  'completed',
        '已拒绝':  'rejected',
        '已撤单':  'cancelled',
    }
    for bo in (data.get('paidan_orders') or {}).values():
        web_no = bo.get('webOrderNo')
        if not web_no:
            continue
        new_st = BOT_TO_FLASK.get(bo.get('status', ''))
        if not new_st:
            continue
        db.execute(
            "UPDATE orders SET status=?, updated_at=? WHERE order_no=? AND tenant_id=?",
            (new_st, now, web_no, tenant['id'])
        )

    # ── 检测 bot 端删除的用户 ────────────────────────────────────────────────
    if 'paidan_users' in data:
        incoming_uids = set(data['paidan_users'].keys())
        existing = db.execute(
            "SELECT id, platform_uid FROM bot_users WHERE tenant_id=? AND is_deleted=0",
            (tenant['id'],)).fetchall()
        for u in existing:
            if u['platform_uid'] not in incoming_uids:
                db.execute("UPDATE bot_users SET is_deleted=1, deleted_at=? WHERE id=?",
                           (now, u['id']))
        # 如果之前被标记但又回来了，取消标记
        if incoming_uids:
            ph = ','.join('?' * len(incoming_uids))
            db.execute(
                f"UPDATE bot_users SET is_deleted=0, deleted_at=NULL"
                f" WHERE tenant_id=? AND is_deleted=1 AND platform_uid IN ({ph})",
                [tenant['id']] + list(incoming_uids))

    # ── Bot 推送公告 ─────────────────────────────────────────────────────────
    for ann in (data.get('paidan_announce') or []):
        if isinstance(ann, str):
            content, created_by = ann.strip(), 'bot'
        elif isinstance(ann, dict):
            content, created_by = ann.get('content', '').strip(), ann.get('from', 'bot')
        else:
            continue
        if content:
            db.execute("INSERT INTO announcements (tenant_id,content,created_by,created_at) VALUES (?,?,?,?)",
                       (tenant['id'], content, created_by, now))

    db.commit()
    return jsonify({"ok": True, "updated": now})

@app.route('/api/stats', methods=['GET'])
def api_stats():
    tenant, err = _api_tenant()
    if err: return err
    db = get_db()
    stats = {s: db.execute("SELECT COUNT(*) FROM orders WHERE tenant_id=? AND status=?",
                           (tenant['id'], s)).fetchone()[0] for s in ALL_STATUSES}
    stats['total'] = sum(stats.values())
    return jsonify({"ok": True, "tenant": tenant['display_name'], "stats": stats})

@app.route('/api/orders/<order_no>/urgent', methods=['POST'])
def api_urgent(order_no):
    tenant, err = _api_tenant()
    if err: return err
    db  = get_db()
    o   = db.execute("SELECT * FROM orders WHERE order_no=? AND tenant_id=?", (order_no, tenant['id'])).fetchone()
    if not o: return jsonify({"ok": False, "error": "订单不存在"}), 404
    data   = request.get_json(silent=True) or {}
    urgent = 0 if data.get('cancel') else 1
    db.execute("UPDATE orders SET is_urgent=?, updated_at=? WHERE order_no=?", (urgent, _now(), order_no))
    _add_log(db, o['id'], '标记加急' if urgent else '取消加急', f"bot:{tenant['slug']}")
    db.commit()
    return jsonify({"ok": True, "order_no": order_no, "is_urgent": urgent})

@app.route('/api/orders/<order_no>/rush', methods=['POST'])
def api_rush(order_no):
    tenant, err = _api_tenant()
    if err: return err
    db   = get_db()
    o    = db.execute("SELECT * FROM orders WHERE order_no=? AND tenant_id=?", (order_no, tenant['id'])).fetchone()
    if not o: return jsonify({"ok": False, "error": "订单不存在"}), 404
    data = request.get_json(silent=True) or {}
    note = data.get('note', '用户催单')
    db.execute("UPDATE orders SET rush_count=rush_count+1, updated_at=? WHERE order_no=?", (_now(), order_no))
    _add_log(db, o['id'], '催单', data.get('actor', 'bot'), note)
    db.commit()
    cnt = db.execute("SELECT rush_count FROM orders WHERE order_no=?", (order_no,)).fetchone()[0]
    return jsonify({"ok": True, "order_no": order_no, "rush_count": cnt})

# ── Bot 用户 / 卡系统 API ─────────────────────────────────────────────────────

@app.route('/api/users', methods=['GET'])
def api_list_bot_users():
    tenant, err = _api_tenant()
    if err: return err
    db    = get_db()
    users = [dict(u) for u in db.execute(
        "SELECT * FROM bot_users WHERE tenant_id=? ORDER BY display_name", (tenant['id'],)).fetchall()]
    return jsonify({"ok": True, "users": users, "count": len(users)})

@app.route('/api/users/sync', methods=['POST'])
def api_sync_user():
    """Bot 同步单个用户卡信息到 UI"""
    tenant, err = _api_tenant()
    if err: return err
    db   = get_db()
    data = request.get_json(silent=True) or {}
    uid  = data.get('platform_uid', '').strip()
    if not uid: return jsonify({"ok": False, "error": "缺少 platform_uid"}), 400
    dname     = data.get('display_name', uid)
    card_total = int(data.get('card_total', 0))
    card_rem   = int(data.get('card_remaining', card_total))
    notes      = data.get('notes', '')
    now        = _now()
    existing   = db.execute("SELECT id FROM bot_users WHERE tenant_id=? AND platform_uid=?",
                             (tenant['id'], uid)).fetchone()
    if existing:
        db.execute("UPDATE bot_users SET display_name=?,card_total=?,card_remaining=?,notes=?,updated_at=? WHERE id=?",
                   (dname, card_total, card_rem, notes, now, existing['id']))
    else:
        db.execute("INSERT INTO bot_users (tenant_id,platform_uid,display_name,card_total,card_remaining,notes,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                   (tenant['id'], uid, dname, card_total, card_rem, notes, now, now))
    db.commit()
    return jsonify({"ok": True, "platform_uid": uid, "card_remaining": card_rem})

@app.route('/api/users/<platform_uid>/use_card', methods=['POST'])
def api_use_card(platform_uid):
    tenant, err = _api_tenant()
    if err: return err
    db = get_db()
    u  = db.execute("SELECT * FROM bot_users WHERE tenant_id=? AND platform_uid=?",
                    (tenant['id'], platform_uid)).fetchone()
    if not u: return jsonify({"ok": False, "error": "用户不存在"}), 404
    if u['card_remaining'] <= 0:
        return jsonify({"ok": False, "error": "卡已用完"}), 400
    db.execute("UPDATE bot_users SET card_remaining=card_remaining-1, updated_at=? WHERE id=?", (_now(), u['id']))
    db.commit()
    rem = db.execute("SELECT card_remaining FROM bot_users WHERE id=?", (u['id'],)).fetchone()[0]
    return jsonify({"ok": True, "platform_uid": platform_uid, "card_remaining": rem})

# ── 管理后台：仪表盘 & 卡管理 ────────────────────────────────────────────────

def _get_snapshot(db, key, tid=None):
    """读取 bot snapshot。tid 不为 None 时读 {tid}_{key}，否则读全局 key"""
    lookup = f"{tid}_{key}" if tid is not None else key
    row = db.execute("SELECT data FROM bot_snapshot WHERE key=?", (lookup,)).fetchone()
    if not row: return {}
    try: return json.loads(row['data'])
    except: return {}

@app.route('/admin/dashboard')
@require_admin
def admin_dashboard():
    tid = session['admin_tenant_id']
    db  = get_db()

    # ── 散单（Flask DB）──
    web_counts = {s: db.execute("SELECT COUNT(*) FROM orders WHERE tenant_id=? AND status=?",
                                (tid, s)).fetchone()[0] for s in ALL_STATUSES}
    web_counts['all'] = sum(web_counts.values())
    web_rate   = round(web_counts.get('completed',0) / web_counts['all'] * 100) if web_counts['all'] else 0
    web_urgent = [dict(o) for o in db.execute(
        "SELECT * FROM orders WHERE tenant_id=? AND is_urgent=1 AND status NOT IN ('completed','rejected','cancelled') ORDER BY created_at",
        (tid,)).fetchall()]
    web_rushed = [dict(o) for o in db.execute(
        "SELECT * FROM orders WHERE tenant_id=? AND rush_count>0 AND status NOT IN ('completed','rejected','cancelled') ORDER BY rush_count DESC",
        (tid,)).fetchall()]
    recent_web = [dict(o) for o in db.execute(
        "SELECT * FROM orders WHERE tenant_id=? AND status NOT IN ('completed','rejected','cancelled')"
        " ORDER BY created_at DESC LIMIT 10", (tid,)).fetchall()]

    # ── Bot订单（排单宝.js 同步，按 tenant 隔离）──
    bot_orders  = _get_snapshot(db, 'paidan_orders', tid)
    bot_active  = [o for o in bot_orders.values() if o.get('status') not in ('已完成','已拒绝','已撤单')]
    bot_urgent  = [o for o in bot_active if o.get('isUrgent')]
    bot_pending = [o for o in bot_orders.values() if o.get('status') == '待接单']
    bot_done    = [o for o in bot_orders.values() if o.get('status') == '已完成']
    bot_users   = _get_snapshot(db, 'paidan_users', tid)
    snap_row    = db.execute("SELECT MAX(updated_at) FROM bot_snapshot WHERE key LIKE ?", (f"{tid}_%",)).fetchone()[0]
    bot_sync_time = _fmt(snap_row) if snap_row else None

    return render_template('admin_dashboard.html',
        web_counts=web_counts, web_rate=web_rate,
        web_urgent=web_urgent, web_rushed=web_rushed, recent_web=recent_web,
        bot_active=bot_active, bot_urgent=bot_urgent,
        bot_pending=bot_pending, bot_done=bot_done,
        bot_users=bot_users, bot_sync_time=bot_sync_time)

@app.route('/admin/cards')
@require_admin
def admin_cards():
    tid         = session['admin_tenant_id']
    db          = get_db()
    db_users    = [dict(u) for u in db.execute(
        "SELECT * FROM bot_users WHERE tenant_id=? ORDER BY display_name", (tid,)).fetchall()]
    snap_users  = _get_snapshot(db, 'paidan_users', tid)   # dict uid→{name,balance,expiry,verified,…}
    snap_row    = db.execute("SELECT MAX(updated_at) FROM bot_snapshot WHERE key LIKE ?", (f"{tid}_%",)).fetchone()[0]
    bot_sync_time = _fmt(snap_row) if snap_row else None

    # 邀请码：按 platform_uid 分组
    invite_map = {}
    for c in db.execute("SELECT * FROM invite_codes WHERE tenant_id=? ORDER BY created_at DESC", (tid,)).fetchall():
        c = dict(c)
        invite_map.setdefault(c['platform_uid'], []).append(c)

    # 已注册的 web 用户 uid 集合
    registered_uids = {r[0] for r in db.execute(
        "SELECT username FROM users WHERE tenant_id=?", (tid,)).fetchall()}

    # bot 端已删除的用户
    deleted_users = [dict(u) for u in db.execute(
        "SELECT * FROM bot_users WHERE tenant_id=? AND is_deleted=1 ORDER BY deleted_at DESC",
        (tid,)).fetchall()]

    # 公告（最近20条，供管理员管理）
    announcements = [dict(a) for a in db.execute(
        "SELECT * FROM announcements WHERE tenant_id=? ORDER BY created_at DESC LIMIT 20",
        (tid,)).fetchall()]

    return render_template('admin_cards.html',
                           users=db_users,
                           snap_users=snap_users,
                           bot_sync_time=bot_sync_time,
                           invite_map=invite_map,
                           registered_uids=registered_uids,
                           deleted_users=deleted_users,
                           announcements=announcements)

@app.route('/admin/cards/<int:uid>/edit', methods=['POST'])
@require_admin
def admin_edit_card(uid):
    tid = session['admin_tenant_id']
    db  = get_db()
    u   = db.execute("SELECT * FROM bot_users WHERE id=? AND tenant_id=?", (uid, tid)).fetchone()
    if not u: abort(404)
    action = request.form.get('action', '')
    if action == 'set':
        total = int(request.form.get('card_total', u['card_total']))
        rem   = int(request.form.get('card_remaining', u['card_remaining']))
        notes = request.form.get('notes', u['notes'])
        db.execute("UPDATE bot_users SET card_total=?,card_remaining=?,notes=?,updated_at=? WHERE id=?",
                   (total, rem, notes, _now(), uid))
        db.commit(); flash("已更新")
    elif action == 'delete':
        db.execute("DELETE FROM bot_users WHERE id=? AND tenant_id=?", (uid, tid))
        db.commit(); flash("已删除")
    return redirect(url_for('admin_cards'))

@app.route('/admin/cards/add', methods=['POST'])
@require_admin
def admin_add_card_user():
    tid  = session['admin_tenant_id']
    db   = get_db()
    puid  = request.form.get('platform_uid', '').strip()
    dname = request.form.get('display_name', '').strip() or puid
    total = int(request.form.get('card_total', 0))
    notes = request.form.get('notes', '')
    if not puid: flash("请填写 UID"); return redirect(url_for('admin_cards'))
    now = _now()
    try:
        db.execute("INSERT INTO bot_users (tenant_id,platform_uid,display_name,card_total,card_remaining,notes,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                   (tid, puid, dname, total, total, notes, now, now))
        db.commit(); flash("已添加")
    except Exception:
        flash("UID 已存在")
    return redirect(url_for('admin_cards'))


@app.route('/admin/bot')
@require_admin
def admin_bot():
    tid = session['admin_tenant_id']
    db  = get_db()
    orders  = _get_snapshot(db, 'paidan_orders', tid)
    users   = _get_snapshot(db, 'paidan_users',  tid)
    config  = _get_snapshot(db, 'paidan_config',  tid)
    updated = db.execute("SELECT MAX(updated_at) FROM bot_snapshot WHERE key LIKE ?", (f"{tid}_%",)).fetchone()[0]
    return render_template('admin_bot.html',
        orders=orders, users=users, config=config,
        updated=_fmt(updated) if updated else '从未同步')

@app.route('/admin/guide')
@require_admin
def admin_guide():
    return render_template('admin_guide.html')


@app.route('/admin/settings', methods=['GET', 'POST'])
@require_admin
def admin_settings():
    tid = session['admin_tenant_id']
    db  = get_db()
    if request.method == 'POST':
        orders_open      = 1 if request.form.get('orders_open') else 0
        contact_qq       = request.form.get('contact_qq', '').strip()
        db.execute("UPDATE tenants SET orders_open=?, contact_qq=? WHERE id=?",
                   (orders_open, contact_qq, tid))
        db.commit()
        flash("设置已保存")
        return redirect(url_for('admin_settings'))
    tenant = dict(db.execute("SELECT * FROM tenants WHERE id=?", (tid,)).fetchone())
    # 当前进行中数量
    active_cnt = db.execute(
        "SELECT COUNT(*) FROM orders WHERE tenant_id=? AND status NOT IN ('completed','rejected','cancelled')",
        (tid,)).fetchone()[0]
    return render_template('admin_settings.html', tenant=tenant, active_cnt=active_cnt)


@app.route('/admin/cleanup-images', methods=['POST'])
@require_admin
def admin_cleanup_images():
    tid = session['admin_tenant_id']
    db  = get_db()
    # 找出该 tenant 所有已结束订单（完成/拒绝/取消）
    done_orders = db.execute(
        "SELECT id FROM orders WHERE tenant_id=? AND status IN ('completed','rejected','cancelled')",
        (tid,)).fetchall()
    cleaned = 0
    freed   = 0
    for row in done_orders:
        oid = row['id']
        d = os.path.join(UPLOAD_DIR, str(oid))
        if os.path.exists(d):
            # 统计大小
            for dirpath, _, fnames in os.walk(d):
                for fn in fnames:
                    try: freed += os.path.getsize(os.path.join(dirpath, fn))
                    except: pass
            shutil.rmtree(d, ignore_errors=True)
            cleaned += 1
        # 清理 DB 里的图片记录
        db.execute("DELETE FROM order_images WHERE order_id=?", (oid,))
        db.execute("DELETE FROM order_result_images WHERE order_id=?", (oid,))
    db.commit()
    mb = round(freed / 1024 / 1024, 2)
    flash(f"已清理 {cleaned} 个订单的图片，释放约 {mb} MB 空间")
    return redirect(url_for('admin_settings'))


@app.route('/admin/form-builder/default-schema')
@require_admin
def admin_form_builder_default():
    return jsonify([f.copy() for f in DEFAULT_FORM_SCHEMA])


@app.route('/admin/form-builder', methods=['GET', 'POST'])
@require_admin
def admin_form_builder():
    tid = session['admin_tenant_id']
    db  = get_db()
    if request.method == 'POST':
        schema_json = request.form.get('schema_json', '').strip()
        try:
            schema = json.loads(schema_json)
            if not isinstance(schema, list):
                raise ValueError("schema 必须是数组")
        except Exception as e:
            flash(f"保存失败：格式错误 {e}")
            return redirect(url_for('admin_form_builder'))
        db.execute("UPDATE tenants SET order_form_schema=? WHERE id=?",
                   (json.dumps(schema, ensure_ascii=False), tid))
        db.commit()
        flash("表单设计已保存")
        return redirect(url_for('admin_form_builder'))
    tenant = dict(db.execute("SELECT * FROM tenants WHERE id=?", (tid,)).fetchone())
    schema = _get_form_schema(tenant)
    return render_template('admin_form_builder.html',
                           tenant=tenant,
                           schema_json=json.dumps(schema, ensure_ascii=False, indent=2))


# ── 邀请码注册 ───────────────────────────────────────────────────────────────

@app.route('/admin/cards/invite/gen', methods=['POST'])
@require_admin
def admin_gen_invite():
    tid          = session['admin_tenant_id']
    db           = get_db()
    platform_uid = request.form.get('platform_uid', '').strip()
    display_name = request.form.get('display_name', '').strip()
    if not platform_uid:
        flash("请提供用户 UID"); return redirect(url_for('admin_cards'))
    if db.execute("SELECT id FROM users WHERE tenant_id=? AND username=?", (tid, platform_uid)).fetchone():
        flash(f"UID {platform_uid} 已注册过账号，无需邀请码"); return redirect(url_for('admin_cards'))
    code = secrets.token_urlsafe(8)
    db.execute("INSERT INTO invite_codes (tenant_id,code,platform_uid,display_name,created_at) VALUES (?,?,?,?,?)",
               (tid, code, platform_uid, display_name, _now()))
    db.commit()
    link = request.host_url.rstrip('/') + url_for('invite_register', code=code)
    flash(f"✅ 邀请链接已生成：{link}")
    return redirect(url_for('admin_cards'))

@app.route('/admin/cards/invite/<int:iid>/delete', methods=['POST'])
@require_admin
def admin_delete_invite(iid):
    tid = session['admin_tenant_id']
    db  = get_db()
    db.execute("DELETE FROM invite_codes WHERE id=? AND tenant_id=?", (iid, tid))
    db.commit(); flash("邀请码已删除")
    return redirect(url_for('admin_cards'))

@app.route('/invite/<code>', methods=['GET', 'POST'])
def invite_register(code):
    db     = get_db()
    invite = db.execute("SELECT * FROM invite_codes WHERE code=?", (code,)).fetchone()
    if not invite: abort(404)
    invite = dict(invite)
    tenant = db.execute("SELECT * FROM tenants WHERE id=? AND is_active=1", (invite['tenant_id'],)).fetchone()
    if not tenant: abort(404)
    errors = []
    if invite['used']:
        return render_template('invite_register.html', invite=invite, tenant=dict(tenant),
                               errors=[], already_used=True)
    if request.method == 'POST':
        pw  = request.form.get('password',  '').strip()
        pw2 = request.form.get('password2', '').strip()
        if not pw or len(pw) < 6:
            errors.append("密码至少 6 个字符")
        elif pw != pw2:
            errors.append("两次密码不一致")
        if not errors:
            uname = invite['platform_uid']
            dname = invite['display_name'] or uname
            now   = _now()
            if db.execute("SELECT 1 FROM accounts WHERE username=?", (uname,)).fetchone():
                errors.append("该账号已注册，请直接登录")
            else:
                cur = db.execute('''INSERT INTO accounts (username,password_hash,display_name,contact,is_active,created_at)
                                    VALUES (?,?,?,?,1,?)''',
                                 (uname, generate_password_hash(pw), dname, uname, now))
                member = _get_or_create_membership(db, cur.lastrowid, invite['tenant_id'])
                db.execute("UPDATE invite_codes SET used=1, used_at=? WHERE code=?", (now, code))
                db.commit()
                session['account_id']           = member['account_id']
                session['account_display_name'] = dname
                flash("注册成功，欢迎！")
                return redirect(url_for('my_orders'))
    return render_template('invite_register.html', invite=invite, tenant=dict(tenant),
                           errors=errors, already_used=False)

@app.route('/admin/cards/recharge', methods=['POST'])
@require_admin
def admin_recharge_user():
    tid          = session['admin_tenant_id']
    db           = get_db()
    platform_uid = request.form.get('platform_uid', '').strip()
    display_name = request.form.get('display_name', '').strip() or platform_uid
    add_cards    = int(request.form.get('add_cards', 0) or 0)
    if not platform_uid or add_cards <= 0:
        flash("请填写用户 UID 和充值数量"); return redirect(url_for('admin_cards'))
    now      = _now()
    existing = db.execute("SELECT * FROM bot_users WHERE tenant_id=? AND platform_uid=?",
                          (tid, platform_uid)).fetchone()
    if existing:
        db.execute("UPDATE bot_users SET card_total=card_total+?,card_remaining=card_remaining+?,"
                   "display_name=?,updated_at=?,is_deleted=0,deleted_at=NULL WHERE id=?",
                   (add_cards, add_cards, display_name or existing['display_name'], now, existing['id']))
    else:
        db.execute("INSERT INTO bot_users (tenant_id,platform_uid,display_name,card_total,card_remaining,"
                   "notes,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                   (tid, platform_uid, display_name, add_cards, add_cards, '', now, now))
    db.commit()
    flash(f"✅ 已为 {display_name} 充值 {add_cards} 张卡")
    return redirect(url_for('admin_cards'))

@app.route('/admin/cards/<int:uid>/confirm-delete', methods=['POST'])
@require_admin
def admin_confirm_delete_bot_user(uid):
    tid = session['admin_tenant_id']
    db  = get_db()
    u   = db.execute("SELECT * FROM bot_users WHERE id=? AND tenant_id=?", (uid, tid)).fetchone()
    if not u: abort(404)
    if request.form.get('delete_web'):
        db.execute("DELETE FROM users WHERE tenant_id=? AND username=?", (tid, u['platform_uid']))
    db.execute("DELETE FROM bot_users WHERE id=?", (uid,))
    db.commit()
    flash(f"已删除用户 {u['display_name'] or u['platform_uid']}")
    return redirect(url_for('admin_cards'))

# ── 公告管理 ─────────────────────────────────────────────────────────────────

@app.route('/admin/announcements/post', methods=['POST'])
@require_admin
def admin_post_announcement():
    tid     = session['admin_tenant_id']
    db      = get_db()
    content = request.form.get('content', '').strip()
    if content:
        db.execute("INSERT INTO announcements (tenant_id,content,created_by,created_at) VALUES (?,?,?,?)",
                   (tid, content, session['admin_display_name'], _now()))
        db.commit()
        flash("✅ 公告已发布")
    return redirect(url_for('admin_cards'))

@app.route('/admin/announcements/<int:aid>/delete', methods=['POST'])
@require_admin
def admin_delete_announcement(aid):
    tid = session['admin_tenant_id']
    db  = get_db()
    db.execute("DELETE FROM announcements WHERE id=? AND tenant_id=?", (aid, tid))
    db.commit()
    return redirect(url_for('admin_cards'))

@app.route('/api/announce', methods=['POST'])
def api_announce():
    """Bot 推送单条公告到网站"""
    tenant, err = _api_tenant()
    if err: return err
    db      = get_db()
    data    = request.get_json(silent=True) or {}
    content = data.get('content', '').strip()
    if not content:
        return jsonify({"ok": False, "error": "content 不能为空"}), 400
    db.execute("INSERT INTO announcements (tenant_id,content,created_by,created_at) VALUES (?,?,?,?)",
               (tenant['id'], content, data.get('from', 'bot'), _now()))
    db.commit()
    return jsonify({"ok": True})

@app.route('/member/order')
@require_user
def member_order():
    db  = get_db()
    aid = session['account_id']
    tenant_data = _tenant_status_list(db)
    if not tenant_data:
        abort(404)
    memberships = {m['tenant_id']: m for m in _account_memberships(db, aid)}
    for t in tenant_data:
        m = memberships.get(t['id'])
        t['balance'] = _credit_available(db, m['id']) if m else None
    return render_template('member_order.html', tenant_data=tenant_data)


if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=int(os.environ.get("PORT", 5237)))

import os, json, re, secrets, time, logging, traceback, shutil
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
    # 散单开关 & 数量上限
    if 'orders_open' not in _col(conn, 'tenants'):
        conn.execute("ALTER TABLE tenants ADD COLUMN orders_open INTEGER NOT NULL DEFAULT 1")
    if 'max_active_orders' not in _col(conn, 'tenants'):
        conn.execute("ALTER TABLE tenants ADD COLUMN max_active_orders INTEGER NOT NULL DEFAULT 0")
    if 'order_form_schema' not in _col(conn, 'tenants'):
        conn.execute("ALTER TABLE tenants ADD COLUMN order_form_schema TEXT NOT NULL DEFAULT ''")
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
    {"id": "images",  "type": "upload",       "label": "参考图片",        "required": False, "hint": "最多 10 张，支持 JPG/PNG/GIF/WebP"},
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
        if not session.get('user_id'):
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
    return dict(
        session=session,
        STATUS_LABEL=STATUS_LABEL,
        STATUS_COLOR=STATUS_COLOR,
        ALL_STATUSES=ALL_STATUSES,
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
        max_n = t.get('max_active_orders', 0) or 0
        t['is_full'] = max_n > 0 and active_cnt >= max_n
        t['max_active_orders'] = max_n
        # 综合状态：open=接单中 / full=队列满 / closed=已关闭
        if not t.get('orders_open', 1):
            t['open_status'] = 'closed'
        elif t['is_full']:
            t['open_status'] = 'full'
        else:
            t['open_status'] = 'open'
    any_open = any(t['open_status'] == 'open' for t in rows)
    return render_template('index.html', tenants=rows, any_open=any_open)


# ── 下单 ──────────────────────────────────────────────────────────────────────

@app.route('/order/new', methods=['GET', 'POST'])
def order_new():
    db = get_db()
    raw_tenants = [dict(t) for t in db.execute(
        "SELECT * FROM tenants WHERE is_active=1 ORDER BY display_name").fetchall()]

    # 构造前端需要的 tenant_data（含 schema + 状态）
    tenant_data = []
    for t in raw_tenants:
        active_cnt = db.execute(
            "SELECT COUNT(*) FROM orders WHERE tenant_id=? AND status NOT IN ('completed','rejected','cancelled')",
            (t['id'],)).fetchone()[0]
        max_n = t.get('max_active_orders', 0) or 0
        if not t.get('orders_open', 1):
            open_status = 'closed'
        elif max_n > 0 and active_cnt >= max_n:
            open_status = 'full'
        else:
            open_status = 'open'
        tenant_data.append({
            'id':               t['id'],
            'display_name':     t.get('display_name') or t['slug'],
            'description':      t.get('description', ''),
            'open_status':      open_status,
            'active_cnt':       active_cnt,
            'max_active_orders': max_n,
            'schema':           _get_form_schema(t),
        })

    pre_tid = request.args.get('t', '')
    errors  = []
    error_tid = ''   # 出错时回显哪个 tenant 的表单

    if request.method == 'POST':
        tid    = request.form.get('tenant_id', '').strip()
        error_tid = tid
        tenant = db.execute("SELECT * FROM tenants WHERE id=? AND is_active=1", (tid,)).fetchone()
        if not tenant:
            errors.append("请选择接单方")
        else:
            t = dict(tenant)
            if not t.get('orders_open', 1):
                errors.append("😔 当前暂不接受新的散单，请关注后续开放通知")
            max_n = t.get('max_active_orders', 0) or 0
            if max_n > 0:
                cnt = db.execute(
                    "SELECT COUNT(*) FROM orders WHERE tenant_id=? AND status NOT IN ('completed','rejected','cancelled')",
                    (int(tid),)).fetchone()[0]
                if cnt >= max_n:
                    errors.append(f"😔 散单队列已满（{cnt}/{max_n}），请稍后再来")
            if not errors:
                schema = _get_form_schema(t)
                name, contact, title, desc, form_errors = _process_order_form(request.form, schema)
                errors.extend(form_errors)
                if not errors:
                    now      = _now()
                    order_no = _gen_order_no()
                    verify   = _gen_verify()
                    user_id  = session.get('user_id') if session.get('user_tenant_id') == int(tid) else None
                    db.execute('''INSERT INTO orders
                        (order_no,tenant_id,user_id,customer_name,customer_contact,
                         service_type,title,description,status,verify_code,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (order_no, int(tid), user_id, name, contact,
                         '排单', title, desc, 'pending', verify, now, now))
                    db.commit()
                    oid = db.execute("SELECT id FROM orders WHERE order_no=?", (order_no,)).fetchone()['id']
                    _add_log(db, oid, '创建', name)
                    for f in request.files.getlist('images')[:MAX_IMAGES]:
                        rel = _save_file(f, oid, 'input')
                        if rel:
                            db.execute("INSERT INTO order_images (order_id,filename,original_name,uploaded_at) VALUES (?,?,?,?)",
                                       (oid, rel, f.filename, now))
                    db.commit()
                    return redirect(url_for('order_success', no=order_no, vc=verify))

    user_info = {}
    if session.get('user_id') and session.get('user_tenant_id'):
        u = db.execute("SELECT * FROM users WHERE id=? AND is_active=1", (session['user_id'],)).fetchone()
        if u:
            user_info = {
                '_name': u['display_name'] or u['username'],
                '_qq':   u['contact'] or u['username'],
                'tenant_id': u['tenant_id'],
            }

    return render_template('order_new.html',
                           tenant_data=tenant_data,
                           pre_tid=pre_tid or (str(user_info['tenant_id']) if user_info else ''),
                           errors=errors,
                           error_tid=error_tid,
                           submitted=dict(request.form) if errors else {},
                           user_info=user_info)

@app.route('/order/success')
def order_success():
    return render_template('order_success.html',
        order_no=request.args.get('no',''),
        verify_code=request.args.get('vc',''))

@app.route('/order/<order_no>', methods=['GET', 'POST'])
def order_status(order_no):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE order_no=?", (order_no,)).fetchone()
    if not order: abort(404)
    order = dict(order)

    # determine access
    allowed = (
        (session.get('superadmin')) or
        (session.get('admin_id') and session.get('admin_tenant_id') == order['tenant_id']) or
        (session.get('user_id') and order.get('user_id') and session['user_id'] == order['user_id']) or
        session.get(f'vo_{order_no}')
    )

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

    return render_template('order_status.html',
        order=order, tenant=dict(tenant) if tenant else {},
        images=images, result_images=result_images, logs=logs)


# ── 用户注册 / 登录 ───────────────────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def user_register():
    db = get_db()
    tenants = [dict(t) for t in db.execute(
        "SELECT * FROM tenants WHERE is_active=1 ORDER BY display_name").fetchall()]
    errors = []
    if request.method == 'POST':
        tid     = request.form.get('tenant_id', '').strip()
        uname   = request.form.get('username', '').strip()
        pw      = request.form.get('password', '').strip()
        dname   = request.form.get('display_name', '').strip() or uname
        contact = request.form.get('contact', '').strip()

        if not db.execute("SELECT id FROM tenants WHERE id=? AND is_active=1", (tid,)).fetchone():
            errors.append("请选择账户")
        if not uname or len(uname) < 3:  errors.append("用户名至少 3 个字符")
        if not pw    or len(pw)    < 6:  errors.append("密码至少 6 个字符")
        if not errors:
            if db.execute("SELECT id FROM users WHERE tenant_id=? AND username=?", (int(tid), uname)).fetchone():
                errors.append("用户名已存在")
        if not errors:
            db.execute("INSERT INTO users (tenant_id,username,password_hash,display_name,contact,is_active,created_at) VALUES (?,?,?,?,?,1,?)",
                       (int(tid), uname, generate_password_hash(pw), dname, contact, _now()))
            db.commit()
            flash("注册成功，请登录")
            return redirect(url_for('user_login'))
    return render_template('register.html', tenants=tenants, errors=errors)

@app.route('/login', methods=['GET', 'POST'])
def user_login():
    db = get_db()
    tenants = [dict(t) for t in db.execute(
        "SELECT * FROM tenants WHERE is_active=1 ORDER BY display_name").fetchall()]
    errors = []
    if request.method == 'POST':
        tid   = request.form.get('tenant_id', '').strip()
        uname = request.form.get('username', '').strip()
        pw    = request.form.get('password', '').strip()
        user  = db.execute("SELECT * FROM users WHERE tenant_id=? AND username=? AND is_active=1",
                           (int(tid), uname)).fetchone() if tid else None
        if user and check_password_hash(user['password_hash'], pw):
            session['user_id']           = user['id']
            session['user_tenant_id']    = user['tenant_id']
            session['user_display_name'] = user['display_name'] or user['username']
            return redirect(request.args.get('next') or url_for('my_orders'))
        errors.append("账户 / 用户名 / 密码错误")
    return render_template('login.html', tenants=tenants, errors=errors)

@app.route('/logout')
def user_logout():
    for k in ('user_id', 'user_tenant_id', 'user_display_name'):
        session.pop(k, None)
    return redirect(url_for('index'))

@app.route('/my-orders')
@require_user
def my_orders():
    db  = get_db()
    tid = session['user_tenant_id']
    orders = [dict(o) for o in db.execute(
        '''SELECT o.*, t.display_name AS tenant_name
           FROM orders o JOIN tenants t ON t.id=o.tenant_id
           WHERE o.user_id=? ORDER BY o.created_at DESC''',
        (session['user_id'],)).fetchall()]
    announcements = [dict(a) for a in db.execute(
        "SELECT * FROM announcements WHERE tenant_id=? ORDER BY created_at DESC LIMIT 10",
        (tid,)).fetchall()]
    return render_template('my_orders.html', orders=orders, announcements=announcements)


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
        f'''SELECT o.*, a.display_name AS admin_name
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
    return render_template('admin_order_detail.html',
        order=dict(order), admins=admins,
        images=images, result_imgs=result_imgs, logs=logs)

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
    _add_log(db, oid, '已拒绝', session['admin_display_name'], reason)
    db.commit(); flash("已拒绝")
    return redirect(url_for('admin_order_detail', oid=oid))

@app.route('/admin/orders/<int:oid>/cancel', methods=['POST'])
@require_admin
def admin_cancel(oid):
    db, o = _check_order(oid)
    db.execute("UPDATE orders SET status='cancelled', updated_at=? WHERE id=?", (_now(), oid))
    _add_log(db, oid, '已取消', session['admin_display_name'])
    db.commit(); flash("已取消")
    return redirect(url_for('admin_order_detail', oid=oid))

@app.route('/admin/orders/<int:oid>/note', methods=['POST'])
@require_admin
def admin_note(oid):
    db, o = _check_order(oid)
    note = request.form.get('admin_notes', '').strip()
    db.execute("UPDATE orders SET admin_notes=?, updated_at=? WHERE id=?", (note, _now(), oid))
    _add_log(db, oid, '更新备注', session['admin_display_name'], note[:60])
    db.commit(); flash("备注已保存")
    return redirect(url_for('admin_order_detail', oid=oid))

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
               SUM(CASE WHEN o.status='pending' THEN 1 ELSE 0 END) AS pending_count
        FROM tenants t
        LEFT JOIN tenant_admins ta ON ta.tenant_id=t.id AND ta.is_active=1
        LEFT JOIN users u          ON u.tenant_id=t.id  AND u.is_active=1
        LEFT JOIN orders o         ON o.tenant_id=t.id
        GROUP BY t.id ORDER BY t.created_at DESC
    ''').fetchall()]
    return render_template('superadmin.html', tenants=tenants)

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
                db.execute("DELETE FROM orders WHERE tenant_id=?", (tid,))
                # 3. 清空 bot snapshot（该 tenant 前缀的 key）
                db.execute("DELETE FROM bot_snapshot WHERE key LIKE ?", (f"{tid}_%",))
                # 4. 清空 bot 用户
                db.execute("DELETE FROM bot_users WHERE tenant_id=?", (tid,))
                # 5. 清空 web 注册用户
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
    _add_log(db, o['id'], '已拒绝(机器人)', f"bot:{tenant['slug']}", reason)
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
    return jsonify({"ok": True, "order": o})

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
    _add_log(db, o['id'], '备注(机器人)', f"bot:{tenant['slug']}", note[:60])
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
        max_active       = int(request.form.get('max_active_orders', 0) or 0)
        db.execute("UPDATE tenants SET orders_open=?, max_active_orders=? WHERE id=?",
                   (orders_open, max_active, tid))
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
            try:
                db.execute("INSERT INTO users (tenant_id,username,password_hash,display_name,contact,is_active,created_at)"
                           " VALUES (?,?,?,?,?,1,?)",
                           (invite['tenant_id'], uname, generate_password_hash(pw), dname, uname, now))
                db.commit()
                db.execute("UPDATE invite_codes SET used=1, used_at=? WHERE code=?", (now, code))
                db.commit()
                user = db.execute("SELECT * FROM users WHERE tenant_id=? AND username=?",
                                  (invite['tenant_id'], uname)).fetchone()
                session['user_id']           = user['id']
                session['user_tenant_id']    = user['tenant_id']
                session['user_display_name'] = user['display_name'] or user['username']
                flash("注册成功，欢迎！")
                return redirect(url_for('my_orders'))
            except Exception:
                errors.append("该账号已注册，请直接登录")
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
    return redirect(url_for('order_new', t=session['user_tenant_id']))


if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5237)

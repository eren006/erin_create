import os, re, secrets, logging, traceback, json
from urllib.parse import quote as _urlquote
from calendar import monthrange
from datetime import datetime, date as date_cls, timedelta
from collections import Counter
from functools import wraps
from flask import (Flask, render_template, request, redirect,
                   url_for, session, g, abort, flash, jsonify)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "yuca_calendar_secret_2025_change_me")

_log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_log_dir, exist_ok=True)
_err_handler = logging.FileHandler(os.path.join(_log_dir, "error.log"), encoding="utf-8")
_err_handler.setLevel(logging.ERROR)
_err_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s]\n%(message)s\n" + "-"*60))
_logger = logging.getLogger("yuca_calendar")
_logger.setLevel(logging.ERROR)
_logger.addHandler(_err_handler)

DB_PATH        = os.path.join(os.path.dirname(__file__), "yuca_data.db")
SUPERADMIN_PASS = os.environ.get("SUPERADMIN_PASS", "yuca_admin_2025")

VIP_THRESHOLD = 10
VIP_THEMES = {'vip-gold', 'vip-jade'}

# 成就主题：{theme_id: (条件描述, 检测函数key)}
ACHIEVEMENT_THEMES = {
    'achieve-first-drama': '记录第一篇戏录',
    'achieve-sched-10':    '累计录入 10 个日程',
    'achieve-sched-50':    '累计录入 50 个日程',
}

def _get_unlocked_achievements(db, uid):
    """返回该用户已解锁的成就主题 id 集合"""
    unlocked = set()
    drama_cnt = db.execute(
        "SELECT COUNT(*) FROM drama_logs WHERE user_id=?", (uid,)
    ).fetchone()[0]
    if drama_cnt >= 1:
        unlocked.add('achieve-first-drama')
    sched_cnt = db.execute(
        "SELECT COUNT(*) FROM schedules WHERE user_id=?", (uid,)
    ).fetchone()[0]
    if sched_cnt >= 10:
        unlocked.add('achieve-sched-10')
    if sched_cnt >= 50:
        unlocked.add('achieve-sched-50')
    return unlocked

SHOW_COLORS = [
    '#8b7cf6', '#f472b6', '#34d399', '#60a5fa', '#fbbf24',
    '#f87171', '#a78bfa', '#2dd4bf', '#fb923c', '#818cf8',
    '#e879f9', '#4ade80', '#38bdf8', '#fb7185', '#facc15',
    '#c084fc', '#86efac', '#67e8f9', '#fda4af', '#a3e635',
]

SCHEDULE_TAGS = ['带本', '下组', '打工']
SCHEDULE_TAG_COLORS = {'带本': '#fb923c', '下组': '#60a5fa', '打工': '#a78bfa'}

CASTING_STATUS = ['观望中', '一表中', '已录取']

CARD_TYPES = ['板写', '溶图', '溶写', '其他']

DEADLINE_TYPES = [
    ('deadline_form2',    '二表'),
    ('deadline_public',   '公知'),
    ('deadline_relation', '关系线'),
]
DEADLINE_COLORS = {
    'deadline_form2':    '#fbbf24',
    'deadline_public':   '#38bdf8',
    'deadline_relation': '#4ade80',
}


# ── DB ─────────────────────────────────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db:
        db.close()

def _col_names(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}

def _migrate(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        username      TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        display_name  TEXT NOT NULL DEFAULT '',
        is_active     INTEGER NOT NULL DEFAULT 1,
        share_token   TEXT,
        share_enabled INTEGER NOT NULL DEFAULT 0,
        theme         TEXT NOT NULL DEFAULT '',
        created_at    INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS schedules (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL REFERENCES users(id),
        show_name    TEXT NOT NULL,
        start_year   INTEGER NOT NULL,
        time_range   TEXT NOT NULL,
        status       TEXT NOT NULL DEFAULT '未知',
        character    TEXT NOT NULL DEFAULT '未知',
        orientation  TEXT NOT NULL DEFAULT '未知',
        theme        TEXT NOT NULL DEFAULT '未知',
        role_name    TEXT NOT NULL DEFAULT '未知',
        role_type    TEXT NOT NULL DEFAULT '未知',
        gender       TEXT NOT NULL DEFAULT '未知',
        outcome      TEXT NOT NULL DEFAULT '未知',
        color        TEXT NOT NULL DEFAULT '',
        notes        TEXT NOT NULL DEFAULT '',
        created_at   INTEGER NOT NULL,
        updated_at   INTEGER NOT NULL
    )''')
    # ── 旧库迁移 ──────────────────────────────────────────────────────────────
    cols_u = _col_names(conn, 'users')
    if 'share_token'   not in cols_u: conn.execute("ALTER TABLE users ADD COLUMN share_token TEXT")
    if 'share_enabled' not in cols_u: conn.execute("ALTER TABLE users ADD COLUMN share_enabled INTEGER NOT NULL DEFAULT 0")
    if 'theme'         not in cols_u: conn.execute("ALTER TABLE users ADD COLUMN theme TEXT NOT NULL DEFAULT ''")
    if 'dual_mode'     not in cols_u: conn.execute("ALTER TABLE users ADD COLUMN dual_mode INTEGER NOT NULL DEFAULT 0")
    if 'share_view'    not in cols_u: conn.execute("ALTER TABLE users ADD COLUMN share_view TEXT NOT NULL DEFAULT 'calendar'")
    cols_s = _col_names(conn, 'schedules')
    if 'color'             not in cols_s: conn.execute("ALTER TABLE schedules ADD COLUMN color TEXT NOT NULL DEFAULT ''")
    if 'deadline_form2'    not in cols_s: conn.execute("ALTER TABLE schedules ADD COLUMN deadline_form2 TEXT NOT NULL DEFAULT ''")
    if 'deadline_public'   not in cols_s: conn.execute("ALTER TABLE schedules ADD COLUMN deadline_public TEXT NOT NULL DEFAULT ''")
    if 'deadline_relation' not in cols_s: conn.execute("ALTER TABLE schedules ADD COLUMN deadline_relation TEXT NOT NULL DEFAULT ''")
    if 'schedule_tags'     not in cols_s: conn.execute("ALTER TABLE schedules ADD COLUMN schedule_tags TEXT NOT NULL DEFAULT '[]'")
    if 'casting_status'   not in cols_s: conn.execute("ALTER TABLE schedules ADD COLUMN casting_status TEXT NOT NULL DEFAULT ''")
    conn.execute('''CREATE TABLE IF NOT EXISTS dramas (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL REFERENCES users(id),
        title        TEXT NOT NULL,
        tags         TEXT NOT NULL DEFAULT '[]',
        content      TEXT NOT NULL DEFAULT '',
        writing_time INTEGER,
        created_at   INTEGER NOT NULL,
        updated_at   INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS blacklist (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL REFERENCES users(id),
        qq           TEXT NOT NULL DEFAULT '',
        nickname     TEXT NOT NULL DEFAULT '',
        reason       TEXT NOT NULL DEFAULT '',
        happened_at  TEXT NOT NULL DEFAULT '',
        notes        TEXT NOT NULL DEFAULT '',
        created_at   INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS reminders (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL REFERENCES users(id),
        content      TEXT NOT NULL,
        remind_date  TEXT NOT NULL DEFAULT '',
        is_done      INTEGER NOT NULL DEFAULT 0,
        created_at   INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS invite_codes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        code       TEXT UNIQUE NOT NULL,
        is_used    INTEGER NOT NULL DEFAULT 0,
        used_by    INTEGER REFERENCES users(id),
        created_at INTEGER NOT NULL,
        used_at    INTEGER
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS partners (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL REFERENCES users(id),
        qq           TEXT NOT NULL DEFAULT '',
        nickname     TEXT NOT NULL,
        rating       INTEGER NOT NULL DEFAULT 0,
        tags         TEXT NOT NULL DEFAULT '[]',
        schedule_ids TEXT NOT NULL DEFAULT '[]',
        notes        TEXT NOT NULL DEFAULT '',
        created_at   INTEGER NOT NULL,
        updated_at   INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS diaries (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL REFERENCES users(id),
        title       TEXT NOT NULL DEFAULT '',
        content     TEXT NOT NULL DEFAULT '',
        mood        TEXT NOT NULL DEFAULT '',
        schedule_id INTEGER,
        diary_date  TEXT NOT NULL DEFAULT '',
        created_at  INTEGER NOT NULL,
        updated_at  INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS wishlist (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL REFERENCES users(id),
        wtype      TEXT NOT NULL DEFAULT '题材',
        content    TEXT NOT NULL,
        notes      TEXT NOT NULL DEFAULT '',
        is_done    INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS drama_logs (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL REFERENCES users(id),
        title        TEXT NOT NULL DEFAULT '',
        my_char      TEXT NOT NULL DEFAULT '',
        partner_char TEXT NOT NULL DEFAULT '',
        partner_qq   TEXT NOT NULL DEFAULT '',
        genre        TEXT NOT NULL DEFAULT '',
        status       TEXT NOT NULL DEFAULT 'ongoing',
        notes        TEXT NOT NULL DEFAULT '',
        start_ts     INTEGER,
        end_ts       INTEGER,
        created_at   INTEGER NOT NULL,
        updated_at   INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS day_events (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL REFERENCES users(id),
        event_date TEXT NOT NULL,
        title      TEXT NOT NULL,
        color      TEXT NOT NULL DEFAULT '#8b7cf6',
        created_at INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS feedbacks (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL REFERENCES users(id),
        type       TEXT NOT NULL DEFAULT 'bug',
        content    TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        is_read    INTEGER NOT NULL DEFAULT 0
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS guilds (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        slug        TEXT UNIQUE NOT NULL,
        signature   TEXT NOT NULL DEFAULT '',
        owner_id    INTEGER NOT NULL REFERENCES users(id),
        created_at  INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS guild_memberships (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id    INTEGER NOT NULL REFERENCES guilds(id),
        user_id     INTEGER NOT NULL REFERENCES users(id),
        status      TEXT NOT NULL DEFAULT 'pending',
        created_at  INTEGER NOT NULL,
        approved_at INTEGER,
        UNIQUE(guild_id, user_id)
    )''')
    cols_s2 = _col_names(conn, 'schedules')
    if 'visibility' not in cols_s2:
        conn.execute("ALTER TABLE schedules ADD COLUMN visibility TEXT NOT NULL DEFAULT 'public'")
    cols_dl = _col_names(conn, 'drama_logs')
    if 'content' not in cols_dl:
        conn.execute("ALTER TABLE drama_logs ADD COLUMN content TEXT NOT NULL DEFAULT ''")
    cols_p = _col_names(conn, 'partners')
    if 'shared_guilds' not in cols_p:
        conn.execute("ALTER TABLE partners ADD COLUMN shared_guilds TEXT NOT NULL DEFAULT '[]'")
    cols_b = _col_names(conn, 'blacklist')
    if 'shared_guilds' not in cols_b:
        conn.execute("ALTER TABLE blacklist ADD COLUMN shared_guilds TEXT NOT NULL DEFAULT '[]'")
    conn.execute('''CREATE TABLE IF NOT EXISTS reports (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        target_qq        TEXT NOT NULL,
        tag              TEXT NOT NULL DEFAULT '',
        reason           TEXT NOT NULL DEFAULT '',
        submitter_user_id INTEGER REFERENCES users(id),
        status           TEXT NOT NULL DEFAULT 'pending',
        created_at       INTEGER NOT NULL
    )''')
    cols_rp = _col_names(conn, 'reports')
    if 'status' not in cols_rp:
        conn.execute("ALTER TABLE reports ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'")
    if 'edit_note' not in cols_rp:
        conn.execute("ALTER TABLE reports ADD COLUMN edit_note TEXT NOT NULL DEFAULT ''")
    conn.execute('''CREATE TABLE IF NOT EXISTS report_appeals (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id          INTEGER NOT NULL REFERENCES reports(id),
        submitter_user_id  INTEGER REFERENCES users(id),
        reason             TEXT NOT NULL DEFAULT '',
        status             TEXT NOT NULL DEFAULT 'pending',
        admin_note         TEXT NOT NULL DEFAULT '',
        created_at         INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS api_tokens (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL REFERENCES users(id),
        token      TEXT UNIQUE NOT NULL,
        expires_at INTEGER NOT NULL,
        created_at INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS cards (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL REFERENCES users(id),
        name         TEXT NOT NULL,
        expiry       TEXT NOT NULL,
        quantity     INTEGER NOT NULL DEFAULT 1,
        price        REAL NOT NULL DEFAULT 0,
        card_type    TEXT NOT NULL DEFAULT '其他',
        notes        TEXT NOT NULL DEFAULT '',
        last_consume INTEGER,
        created_at   INTEGER NOT NULL,
        updated_at   INTEGER NOT NULL
    )''')
    conn.commit()

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        _migrate(conn)

init_db()


# ── Time utilities ──────────────────────────────────────────────────────────────

def parse_time_range(range_str):
    m = re.match(r'^(\d{2})(\d{2})\s+(\d{2})(\d{2})$', (range_str or '').strip())
    if not m:
        return {'valid': False, 'error': '时间段格式错误，应为 MMDD MMDD（同年如 0315 0320，跨年如 1201 0201）'}
    sm, sd, em, ed = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    if not (1 <= sm <= 12 and 1 <= em <= 12):
        return {'valid': False, 'error': '月份必须在 01-12 之间'}
    def max_day(mo): return 29 if mo == 2 else 30 if mo in [4,6,9,11] else 31
    if not (1 <= sd <= max_day(sm)): return {'valid': False, 'error': f'开始日期 {sm}月 不存在 {sd} 日'}
    if not (1 <= ed <= max_day(em)): return {'valid': False, 'error': f'结束日期 {em}月 不存在 {ed} 日'}
    if em == sm and ed <= sd:        return {'valid': False, 'error': '同月时结束日必须大于开始日'}
    return {'valid': True, 'sm': sm, 'sd': sd, 'em': em, 'ed': ed}

def is_cross_year(p): return p['em'] < p['sm']

def _sval(year, p): return year * 10000 + p['sm'] * 100 + p['sd']
def _eval(year, p):
    ey = year + 1 if is_cross_year(p) else year
    return ey * 10000 + p['em'] * 100 + p['ed']

def schedules_for_month(schedules, year, month):
    days_in = monthrange(year, month)[1]
    day_shows = {d: [] for d in range(1, days_in + 1)}
    active = []
    for s in schedules:
        p = parse_time_range(s['time_range'])
        if not p['valid']: continue
        sy = s['start_year']
        ey = sy + 1 if is_cross_year(p) else sy
        sv, ev = _sval(sy, p), _eval(sy, p)
        msv = year * 10000 + month * 100 + 1
        mev = year * 10000 + month * 100 + days_in
        if ev < msv or sv > mev: continue
        fd = p['sd'] if (sy == year and p['sm'] == month) else 1
        td = p['ed'] if (ey == year and p['em'] == month) else days_in
        for d in range(fd, td + 1):
            if 1 <= d <= days_in: day_shows[d].append(s)
        active.append({'schedule': s, 'from_day': fd, 'to_day': td})
    return day_shows, active, days_in

def find_conflicts(schedules, skip_id, new_start_year, p_new):
    sv_new, ev_new = _sval(new_start_year, p_new), _eval(new_start_year, p_new)
    conflicts = []
    for s in schedules:
        if s['id'] == skip_id: continue
        p = parse_time_range(s['time_range'])
        if not p['valid']: continue
        if sv_new <= _eval(s['start_year'], p) and ev_new >= _sval(s['start_year'], p):
            conflicts.append(s['show_name'])
    return conflicts

def find_all_conflicts(schedules):
    """Return set of schedule IDs that overlap with at least one other."""
    conflict_ids = set()
    lst = [s for s in schedules if parse_time_range(s['time_range'])['valid']]
    for i, s1 in enumerate(lst):
        p1 = parse_time_range(s1['time_range'])
        sv1, ev1 = _sval(s1['start_year'], p1), _eval(s1['start_year'], p1)
        for s2 in lst[i+1:]:
            p2 = parse_time_range(s2['time_range'])
            sv2, ev2 = _sval(s2['start_year'], p2), _eval(s2['start_year'], p2)
            if sv1 <= ev2 and ev1 >= sv2:
                conflict_ids.add(s1['id'])
                conflict_ids.add(s2['id'])
    return conflict_ids

def _free_intervals(day_shows, days_in):
    intervals, start = [], None
    for d in range(1, days_in + 1):
        if not day_shows[d] and start is None: start = d
        if day_shows[d] and start is not None: intervals.append((start, d-1)); start = None
    if start is not None: intervals.append((start, days_in))
    return intervals

def _build_cal_rows(year, month):
    days_in = monthrange(year, month)[1]
    first_wd = (date_cls(year, month, 1).weekday() + 1) % 7
    cells = [None] * first_wd + list(range(1, days_in + 1))
    cells += [None] * ((7 - len(cells) % 7) % 7)
    return [cells[i:i+7] for i in range(0, len(cells), 7)]

def year_view_data(schedules, year, conflict_ids):
    months = []
    for month in range(1, 13):
        day_shows, _, days_in = schedules_for_month(schedules, year, month)
        first_wd = (date_cls(year, month, 1).weekday() + 1) % 7
        day_info = {}
        for d in range(1, days_in + 1):
            shows = day_shows[d]
            if shows:
                day_info[d] = {
                    'color': _show_color(shows[0]),
                    'has_conflict': any(s['id'] in conflict_ids for s in shows),
                    'count': len(shows),
                    'names': [s['show_name'] for s in shows],
                }
        months.append({'month': month, 'days_in': days_in, 'first_wd': first_wd, 'day_info': day_info})
    return months

def upcoming_schedules(schedules, days=7):
    now = datetime.now()
    today  = now.year * 10000 + now.month * 100 + now.day
    future = (date_cls.today() + timedelta(days=days))
    limit  = future.year * 10000 + future.month * 100 + future.day
    result = []
    for s in schedules:
        p = parse_time_range(s['time_range'])
        if not p['valid']: continue
        sv = _sval(s['start_year'], p)
        ev = _eval(s['start_year'], p)
        starting = today <= sv <= limit
        ending   = today <= ev <= limit
        if starting or ending:
            result.append({'schedule': s, 'starting': starting, 'ending': ending,
                           'sv': sv, 'ev': ev})
    result.sort(key=lambda x: x['sv'])
    return result

def annual_stats(schedules, target_year):
    now = datetime.now()
    if target_year == now.year:
        target_end = target_year * 10000 + now.month * 100 + now.day
        label = f'{target_year}年（截至今日）'
    else:
        target_end = target_year * 10000 + 1231
        label = f'{target_year}年'
    target_start = target_year * 10000 + 101
    total = 0
    characters, orientations, genders, outcomes, themes = [], [], [], [], []
    active_ranges, involved = [], []
    for s in schedules:
        p = parse_time_range(s['time_range'])
        if not p['valid']: continue
        sv, ev = _sval(s['start_year'], p), _eval(s['start_year'], p)
        if ev < target_start or sv > target_end: continue
        total += 1
        involved.append(s)
        if s['character'] not in ('未知', ''): characters.append({'name': s['show_name'], 'char': s['character']})
        if s['orientation'] not in ('未知', ''): orientations.append(s['orientation'])
        if s['gender']      not in ('未知', ''): genders.append(s['gender'])
        if s['outcome']     not in ('未知', ''): outcomes.append(s['outcome'])
        if s['theme']       not in ('未知', ''): themes.append(s['theme'])
        active_ranges.append({'start': max(sv, target_start), 'end': min(ev, target_end)})
    sy_t = target_start // 10000; sm_t = (target_start % 10000)//100; sd_t = target_start % 100
    ey_t = target_end  // 10000; em_t = (target_end   % 10000)//100; ed_t = target_end  % 100
    cur, end = date_cls(sy_t, sm_t, sd_t), date_cls(ey_t, em_t, ed_t)
    total_days = covered_days = weekday_covered = weekend_covered = 0
    while cur <= end:
        total_days += 1
        cv = cur.year * 10000 + cur.month * 100 + cur.day
        if any(r['start'] <= cv <= r['end'] for r in active_ranges):
            covered_days += 1
            if cur.weekday() >= 5: weekend_covered += 1
            else: weekday_covered += 1
        cur += timedelta(days=1)
    def distrib(items):
        c = Counter(items); tot = sum(c.values())
        return [{'value': v, 'count': cnt, 'pct': round(cnt/tot*100,1)} for v,cnt in c.most_common()]
    return {
        'label': label, 'total': total, 'involved': involved,
        'characters': characters, 'orientations': distrib(orientations),
        'genders': distrib(genders), 'outcomes': distrib(outcomes), 'themes': distrib(themes),
        'covered_days': covered_days, 'total_days': total_days,
        'pct': round(covered_days/total_days*100,1) if total_days > 0 else 0,
        'weekday': weekday_covered, 'weekend': weekend_covered,
    }


# ── Auth ────────────────────────────────────────────────────────────────────────

def require_login(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if not session.get('user_id'): return redirect(url_for('login'))
        return f(*a, **kw)
    return wrapped

def require_superadmin(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if not session.get('superadmin'): return redirect(url_for('superadmin_login'))
        return f(*a, **kw)
    return wrapped


# ── Template helpers ────────────────────────────────────────────────────────────

def _show_color(s):
    if isinstance(s, int): return SHOW_COLORS[s % len(SHOW_COLORS)]
    c = ''
    try: c = (s.get('color') if isinstance(s, dict) else s['color']) or ''
    except: pass
    if c and c.startswith('#'): return c
    try: return SHOW_COLORS[int(s['id']) % len(SHOW_COLORS)]
    except: return SHOW_COLORS[0]

@app.template_global()
def show_color(s): return _show_color(s)

@app.template_global()
def show_color_light(s): return _show_color(s) + '28'

@app.template_global()
def has_conflict_shows(shows, conflict_ids):
    return bool(conflict_ids) and any(s['id'] in conflict_ids for s in shows)

@app.template_global()
def stag_color(tag): return SCHEDULE_TAG_COLORS.get(tag, '#888')

@app.template_global()
def deadline_color(col): return DEADLINE_COLORS.get(col, '#888')

@app.template_global()
def casting_bar_style(s):
    color = _show_color(s)
    cs = (s.get('casting_status', '') or '') if isinstance(s, dict) else ''
    if cs == '观望中':
        return f'background:{color}10;color:{color};border-left:2px dashed {color}'
    elif cs == '一表中':
        return f'background:{color}18;color:{color};border-left:2px dotted {color}'
    return f'background:{color}28;color:{color};border-left:2px solid {color}'

def _is_vip(db):
    uid = session.get('user_id')
    if not uid:
        return False
    cnt = db.execute(
        "SELECT COUNT(*) FROM reports WHERE submitter_user_id=? AND status='approved'", (uid,)
    ).fetchone()[0]
    return cnt >= VIP_THRESHOLD

@app.context_processor
def inject_constants():
    return {'SCHEDULE_TAGS': SCHEDULE_TAGS, 'DEADLINE_TYPES': DEADLINE_TYPES, 'CASTING_STATUS': CASTING_STATUS}

@app.context_processor
def inject_vip():
    if session.get('user_id'):
        try:
            db  = get_db()
            vip = _is_vip(db)
            achievements = _get_unlocked_achievements(db, session['user_id'])
        except Exception:
            vip, achievements = False, set()
        return {
            'is_vip': vip,
            'VIP_THRESHOLD': VIP_THRESHOLD,
            'unlocked_achievements': achievements,
            'ACHIEVEMENT_THEMES': ACHIEVEMENT_THEMES,
        }
    return {
        'is_vip': False,
        'VIP_THRESHOLD': VIP_THRESHOLD,
        'unlocked_achievements': set(),
        'ACHIEVEMENT_THEMES': ACHIEVEMENT_THEMES,
    }

@app.context_processor
def inject_feedback_badge():
    if session.get('superadmin'):
        try:
            count = get_db().execute('SELECT COUNT(*) FROM feedbacks WHERE is_read=0').fetchone()[0]
        except Exception:
            count = 0
        return {'unread_feedback_count': count}
    return {'unread_feedback_count': 0}

@app.template_filter('datetimeformat')
def datetimeformat(ts):
    try: return datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d')
    except: return '—'

@app.context_processor
def inject_user_theme():
    if session.get('user_id'):
        db = get_db()
        row = db.execute('SELECT theme FROM users WHERE id=?', (session['user_id'],)).fetchone()
        theme = row['theme'] if row else ''
        if theme in VIP_THEMES and not _is_vip(db):
            theme = ''
        return {'user_theme': theme}
    return {'user_theme': ''}

def _get_schedules(uid):
    rows = [dict(r) for r in get_db().execute(
        'SELECT * FROM schedules WHERE user_id=? ORDER BY start_year, time_range', (uid,)
    ).fetchall()]
    return _enrich_schedules(rows)

def word_count(text):
    if not text: return 0
    chinese = len(re.findall(r'[一-鿿㐀-䶿]', text))
    remainder = re.sub(r'[一-鿿㐀-䶿]', ' ', text)
    english = len([w for w in remainder.split() if re.search(r'[a-zA-Z0-9]', w)])
    return chinese + english

FIXED_TAGS = ['古原', '现原', '欧原', '其他']

def _next_drama_title(uid):
    db = get_db()
    rows = db.execute("SELECT title FROM dramas WHERE user_id=?", (uid,)).fetchall()
    existing = {r['title'] for r in rows}
    i = 1
    while True:
        t = f'戏录{str(i).zfill(3)}'
        if t not in existing: return t
        i += 1

@app.template_filter('parse_tags')
def parse_tags_filter(s):
    try: return json.loads(s) if s else []
    except: return []

@app.template_filter('word_count')
def word_count_filter(s):
    return word_count(s)


# ── Timeline helper ─────────────────────────────────────────────────────────────

def timeline_data(schedules):
    """Return list of year dicts with bar positioning data for timeline view."""
    from calendar import isleap
    def _year_days(y): return 366 if isleap(y) else 365
    def _day_of_year(y, m, d):
        return (date_cls(y, m, d) - date_cls(y, 1, 1)).days  # 0-based

    # Collect all years touched
    years_set = set()
    for s in schedules:
        p = parse_time_range(s['time_range'])
        if not p['valid']: continue
        sy = s['start_year']
        years_set.add(sy)
        if is_cross_year(p): years_set.add(sy + 1)
    if not years_set: return []

    month_markers = []
    for m in range(1, 13):
        # position within a non-leap year (use generic 365 for display)
        doy = (date_cls(2001, m, 1) - date_cls(2001, 1, 1)).days
        month_markers.append({'month': m, 'pct': round(doy / 365 * 100, 2)})

    result = []
    for year in sorted(years_set):
        total_days = _year_days(year)
        bars = []
        for s in schedules:
            p = parse_time_range(s['time_range'])
            if not p['valid']: continue
            sy = s['start_year']
            cross = is_cross_year(p)
            ey = sy + 1 if cross else sy

            if cross:
                if sy == year:
                    # first segment: start_date → Dec 31
                    start_doy = _day_of_year(year, p['sm'], p['sd'])
                    end_doy   = total_days - 1
                    left  = round(start_doy / total_days * 100, 2)
                    width = round((end_doy - start_doy + 1) / total_days * 100, 2)
                    bars.append({'schedule': s, 'left': left, 'width': max(width, 0.5), 'suffix': '(跨)'})
                elif ey == year:
                    # second segment: Jan 1 → end_date
                    start_doy = 0
                    end_doy   = _day_of_year(year, p['em'], p['ed'])
                    left  = 0.0
                    width = round((end_doy + 1) / total_days * 100, 2)
                    bars.append({'schedule': s, 'left': left, 'width': max(width, 0.5), 'suffix': '(续)'})
            else:
                if sy == year:
                    start_doy = _day_of_year(year, p['sm'], p['sd'])
                    end_doy   = _day_of_year(year, p['em'], p['ed'])
                    left  = round(start_doy / total_days * 100, 2)
                    width = round((end_doy - start_doy + 1) / total_days * 100, 2)
                    bars.append({'schedule': s, 'left': left, 'width': max(width, 0.5), 'suffix': ''})

        result.append({'year': year, 'bars': bars, 'month_markers': month_markers})
    return result


# ── Routes ──────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return redirect(url_for('calendar') if session.get('user_id') else url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'): return redirect(url_for('calendar'))
    errors = []
    if request.method == 'POST':
        code         = request.form.get('code', '').strip()
        username     = request.form.get('username', '').strip()
        password     = request.form.get('password', '').strip()
        display_name = request.form.get('display_name', '').strip()
        db = get_db()
        inv = db.execute('SELECT * FROM invite_codes WHERE code=? AND is_used=0', (code,)).fetchone()
        if not inv:           errors.append('邀请码无效或已被使用')
        if not username:      errors.append('用户名不能为空')
        elif db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone():
            errors.append(f'用户名「{username}」已被占用')
        if not password:      errors.append('密码不能为空')
        elif len(password) < 4: errors.append('密码至少 4 位')
        if errors:
            return render_template('register.html', errors=errors, form=request.form)
        ts = int(datetime.now().timestamp())
        cur = db.execute('INSERT INTO users (username, password_hash, display_name, is_active, created_at) VALUES (?,?,?,1,?)',
                         (username, generate_password_hash(password), display_name or username, ts))
        db.execute('UPDATE invite_codes SET is_used=1, used_by=?, used_at=? WHERE id=?',
                   (cur.lastrowid, ts, inv['id']))
        db.commit()
        flash('✅ 注册成功，请登录')
        return redirect(url_for('login'))
    return render_template('register.html', errors=[], form={})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'): return redirect(url_for('calendar'))
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        user = get_db().execute(
            'SELECT * FROM users WHERE username=? AND is_active=1', (username,)
        ).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session.update({'user_id': user['id'], 'username': user['username'],
                            'display_name': user['display_name'] or user['username']})
            return redirect(url_for('calendar'))
        return render_template('login.html', error='用户名或密码错误，或账号已停用')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('login'))

@app.route('/calendar')
@require_login
def calendar():
    now = datetime.now()
    try:
        year  = int(request.args.get('year',  now.year))
        month = int(request.args.get('month', now.month))
        view  = request.args.get('view', 'month')
        if not (1 <= month <= 12 and 1900 <= year <= 2100): raise ValueError
    except (ValueError, TypeError):
        year, month, view = now.year, now.month, 'month'

    uid = session['user_id']
    all_schedules = _get_schedules(uid)
    user_row = get_db().execute('SELECT dual_mode FROM users WHERE id=?', (uid,)).fetchone()
    dual_mode = bool(user_row['dual_mode']) if user_row else False
    conflict_ids = set() if dual_mode else find_all_conflicts(all_schedules)

    tag_filter = request.args.get('tag_filter', '')
    if tag_filter and tag_filter in SCHEDULE_TAGS:
        display_schedules = [s for s in all_schedules if tag_filter in s['tags_list']]
    else:
        tag_filter = ''
        display_schedules = all_schedules

    day_shows, active, days_in = schedules_for_month(display_schedules, year, month)
    deadline_days = deadlines_for_month(display_schedules, year, month)
    cal_rows = _build_cal_rows(year, month)
    free     = _free_intervals(day_shows, days_in)

    prev_year,  prev_month  = (year-1, 12) if month==1  else (year, month-1)
    next_year,  next_month  = (year+1,  1) if month==12 else (year, month+1)

    year_months = year_view_data(display_schedules, year, conflict_ids) if view == 'year' else None
    upcoming    = upcoming_schedules(display_schedules) if view == 'month' else []

    today_dt  = date_cls.today()
    today_str = today_dt.isoformat()
    reminders = [dict(r) for r in get_db().execute(
        'SELECT * FROM reminders WHERE user_id=? AND is_done=0 ORDER BY remind_date, created_at', (uid,)
    ).fetchall()]
    for r in reminders:
        r['overdue'] = bool(r['remind_date']) and r['remind_date'] < today_str
        r['today']   = r['remind_date'] == today_str

    deadline_alerts = []
    for s in all_schedules:
        for col, label in DEADLINE_TYPES:
            val = (s.get(col) or '').strip()
            if not val: continue
            try:
                dt = datetime.strptime(val, '%Y-%m-%d').date()
                days_left = (dt - today_dt).days
                if 0 <= days_left <= 7:
                    deadline_alerts.append({
                        'schedule': s, 'label': label, 'date': val,
                        'days_left': days_left, 'urgent': days_left <= 2,
                    })
            except: pass
    deadline_alerts.sort(key=lambda x: x['days_left'])

    month_ev_rows = get_db().execute(
        "SELECT * FROM day_events WHERE user_id=? AND event_date LIKE ? ORDER BY created_at",
        (uid, f'{year}-{month:02d}-%')
    ).fetchall()
    day_events_map = {}
    for r in month_ev_rows:
        d = int(r['event_date'].split('-')[2])
        day_events_map.setdefault(d, []).append(dict(r))

    return render_template('calendar.html',
        year=year, month=month, days_in=days_in, view=view,
        cal_rows=cal_rows, day_shows=day_shows, active=active,
        deadline_days=deadline_days,
        free=free, all_schedules=all_schedules,
        display_schedules=display_schedules,
        tag_filter=tag_filter,
        conflict_ids=conflict_ids,
        dual_mode=dual_mode,
        reminders=reminders,
        year_months=year_months,
        upcoming=upcoming,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        now_year=now.year, now_month=now.month, now_day=now.day,
        deadline_alerts=deadline_alerts, day_events_map=day_events_map,
    )

def _time_range_to_dates(start_year, time_range):
    p = parse_time_range(time_range)
    if not p['valid']:
        return '', ''
    start_date = f"{start_year}-{p['sm']:02d}-{p['sd']:02d}"
    ey = start_year + 1 if is_cross_year(p) else start_year
    end_date = f"{ey}-{p['em']:02d}-{p['ed']:02d}"
    return start_date, end_date

def _validate_schedule_form(form):
    errors = []
    show_name  = form.get('show_name', '').strip()
    start_date = form.get('start_date', '').strip()
    end_date   = form.get('end_date',   '').strip()
    sy = datetime.now().year
    time_range = ''
    if not show_name: errors.append('恋综名不能为空')
    if not start_date or not end_date:
        errors.append('请选择开始和结束日期')
    else:
        try:
            sd = datetime.strptime(start_date, '%Y-%m-%d')
            ed = datetime.strptime(end_date,   '%Y-%m-%d')
            if ed <= sd:
                errors.append('结束日期必须晚于开始日期')
            else:
                sy = sd.year
                time_range = f'{sd.month:02d}{sd.day:02d} {ed.month:02d}{ed.day:02d}'
                p = parse_time_range(time_range)
                if not p['valid']: errors.append(p['error'])
        except ValueError:
            errors.append('日期格式错误')
    return errors, show_name, time_range, sy

def _save_schedule_fields(form):
    def f(key):
        v = form.get(key, '').strip(); return v if v else '未知'
    def d(key):
        v = form.get(key, '').strip()
        if not v: return ''
        try: datetime.strptime(v, '%Y-%m-%d'); return v
        except: return ''
    stag = form.get('stag', '').strip()
    tags = [stag] if stag in SCHEDULE_TAGS else []
    cs = form.get('casting_status', '').strip()
    return {
        'status': '', 'character': f('character'), 'orientation': f('orientation'),
        'theme':  f('theme'),  'role_name': f('role_name'), 'role_type':   f('role_type'),
        'gender': f('gender'), 'outcome':   f('outcome'),
        'notes':  form.get('notes', '').strip(),
        'color':  form.get('color', '').strip(),
        'deadline_form2':    d('deadline_form2'),
        'deadline_public':   d('deadline_public'),
        'deadline_relation': d('deadline_relation'),
        'schedule_tags':     json.dumps(tags, ensure_ascii=False),
        'casting_status':    cs if cs in CASTING_STATUS else '',
        'visibility':        'private' if form.get('visibility') == 'private' else 'public',
    }

def _enrich_schedules(schedules):
    for s in schedules:
        s['tags_list'] = json.loads(s.get('schedule_tags') or '[]')
    return schedules

def deadlines_for_month(schedules, year, month):
    days_in = monthrange(year, month)[1]
    dl_days = {d: [] for d in range(1, days_in + 1)}
    for s in schedules:
        for col, label in DEADLINE_TYPES:
            val = (s.get(col) or '').strip()
            if not val: continue
            try:
                dt = datetime.strptime(val, '%Y-%m-%d')
                if dt.year == year and dt.month == month and 1 <= dt.day <= days_in:
                    dl_days[dt.day].append({'schedule': s, 'col': col, 'label': label})
            except: pass
    return dl_days

@app.route('/schedule/add', methods=['GET', 'POST'])
@require_login
def add_schedule():
    if request.method == 'POST':
        errors, show_name, time_range, start_year = _validate_schedule_form(request.form)
        if errors:
            return render_template('schedule_form.html', action='add', form=request.form, errors=errors)
        uid = session['user_id']; db = get_db()
        if db.execute('SELECT id FROM schedules WHERE user_id=? AND show_name=?', (uid, show_name)).fetchone():
            return render_template('schedule_form.html', action='add', form=request.form,
                errors=[f'你已有名为「{show_name}」的档期，请先修改或删除它'])
        p = parse_time_range(time_range)
        _dm_row = db.execute('SELECT dual_mode FROM users WHERE id=?', (uid,)).fetchone()
        dual_mode = bool(_dm_row['dual_mode'] if _dm_row else 0)
        conflicts = [] if dual_mode else find_conflicts(_get_schedules(uid), None, start_year, p)
        flds = _save_schedule_fields(request.form)
        ts = int(datetime.now().timestamp())
        db.execute('''INSERT INTO schedules
            (user_id, show_name, start_year, time_range, status, character, orientation,
             theme, role_name, role_type, gender, outcome, color, notes,
             deadline_form2, deadline_public, deadline_relation, schedule_tags,
             casting_status, visibility, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (uid, show_name, start_year, time_range,
             flds['status'], flds['character'], flds['orientation'], flds['theme'],
             flds['role_name'], flds['role_type'], flds['gender'], flds['outcome'],
             flds['color'], flds['notes'],
             flds['deadline_form2'], flds['deadline_public'], flds['deadline_relation'],
             flds['schedule_tags'], flds['casting_status'], flds['visibility'], ts, ts))
        db.commit()
        msg = f'✅ 档期「{show_name}」已录入'
        if conflicts: msg += f'　⚠️ 撞档提醒：{"、".join(conflicts)}'
        flash(msg); return redirect(url_for('calendar'))
    return render_template('schedule_form.html', action='add',
                           form={'start_date': date_cls.today().isoformat()}, errors=[])

@app.route('/schedule/<int:sid>/edit', methods=['GET', 'POST'])
@require_login
def edit_schedule(sid):
    uid = session['user_id']; db = get_db()
    s = db.execute('SELECT * FROM schedules WHERE id=? AND user_id=?', (sid, uid)).fetchone()
    if not s: abort(404)
    s = dict(s)
    if request.method == 'POST':
        errors, show_name, time_range, start_year = _validate_schedule_form(request.form)
        if errors:
            return render_template('schedule_form.html', action='edit', form=request.form, errors=errors, schedule=s)
        if db.execute('SELECT id FROM schedules WHERE user_id=? AND show_name=? AND id!=?', (uid, show_name, sid)).fetchone():
            return render_template('schedule_form.html', action='edit', form=request.form,
                errors=[f'你已有名为「{show_name}」的档期'], schedule=s)
        p = parse_time_range(time_range)
        _dm_row = db.execute('SELECT dual_mode FROM users WHERE id=?', (uid,)).fetchone()
        dual_mode = bool(_dm_row['dual_mode'] if _dm_row else 0)
        conflicts = [] if dual_mode else find_conflicts(_get_schedules(uid), sid, start_year, p)
        flds = _save_schedule_fields(request.form)
        db.execute('''UPDATE schedules SET
            show_name=?, start_year=?, time_range=?, status=?, character=?, orientation=?,
            theme=?, role_name=?, role_type=?, gender=?, outcome=?, color=?, notes=?,
            deadline_form2=?, deadline_public=?, deadline_relation=?, schedule_tags=?,
            casting_status=?, visibility=?, updated_at=?
            WHERE id=? AND user_id=?''',
            (show_name, start_year, time_range,
             flds['status'], flds['character'], flds['orientation'], flds['theme'],
             flds['role_name'], flds['role_type'], flds['gender'], flds['outcome'],
             flds['color'], flds['notes'],
             flds['deadline_form2'], flds['deadline_public'], flds['deadline_relation'],
             flds['schedule_tags'], flds['casting_status'], flds['visibility'],
             int(datetime.now().timestamp()), sid, uid))
        db.commit()
        msg = f'✅ 档期「{show_name}」已更新'
        if conflicts: msg += f'　⚠️ 撞档提醒：{"、".join(conflicts)}'
        flash(msg); return redirect(url_for('calendar'))
    s['start_date'], s['end_date'] = _time_range_to_dates(s['start_year'], s['time_range'])
    return render_template('schedule_form.html', action='edit', form=s, errors=[], schedule=s)

@app.route('/schedule/<int:sid>/delete', methods=['POST'])
@require_login
def delete_schedule(sid):
    uid = session['user_id']; db = get_db()
    s = db.execute('SELECT show_name FROM schedules WHERE id=? AND user_id=?', (sid, uid)).fetchone()
    if s:
        db.execute('DELETE FROM schedules WHERE id=? AND user_id=?', (sid, uid)); db.commit()
        flash(f'已删除档期「{s["show_name"]}」')
    return redirect(url_for('calendar'))

@app.route('/stats')
@require_login
def stats():
    now = datetime.now()
    try:
        year = int(request.args.get('year', now.year))
        if not (1900 <= year <= 2100): raise ValueError
    except (ValueError, TypeError):
        year = now.year
    uid = session['user_id']
    all_schedules = _get_schedules(uid)
    data = annual_stats(all_schedules, year)
    years_set = {now.year}
    for s in all_schedules:
        years_set.add(s['start_year'])
        p = parse_time_range(s['time_range'])
        if p['valid'] and is_cross_year(p): years_set.add(s['start_year'] + 1)
    return render_template('stats.html', data=data, year=year, years=sorted(years_set, reverse=True))

@app.route('/export')
@require_login
def export():
    uid = session['user_id']
    all_schedules = _get_schedules(uid)
    lines = [f'📅 【{session["display_name"]} 的档期日历】\n══════════════']
    year_groups = {}
    for s in all_schedules:
        p = parse_time_range(s['time_range'])
        if not p['valid']: continue
        sy = s['start_year']; cross = is_cross_year(p)
        pad = lambda n: str(n).zfill(2)
        role_parts = [v for v in [s['role_name'], s['role_type'], s['gender']] if v and v != '未知']
        if s['outcome'] not in ('未知', ''): role_parts.append(f'结:{s["outcome"]}')
        role_str  = f' [{"/".join(role_parts)}]' if role_parts else ''
        extra     = [v for v in [s['status'], s['character'], s['orientation'], s['theme']] if v and v != '未知']
        extra_str = (' · ' + ' '.join(extra)) if extra else ''
        if cross:
            r1 = f'{sy}/{pad(p["sm"])}{pad(p["sd"])}-1231'
            r2 = f'{sy+1}/0101-{pad(p["em"])}{pad(p["ed"])}'
            year_groups.setdefault(sy,   []).append((sy*10000+p['sm']*100+p['sd'], f'📌 {s["show_name"]}{role_str}\n   {r1}{extra_str}'))
            year_groups.setdefault(sy+1, []).append(((sy+1)*10000+101,             f'📌 {s["show_name"]}{role_str} (续)\n   {r2}{extra_str}'))
        else:
            r = f'{sy}/{pad(p["sm"])}{pad(p["sd"])}-{pad(p["em"])}{pad(p["ed"])}'
            year_groups.setdefault(sy, []).append((sy*10000+p['sm']*100+p['sd'], f'📌 {s["show_name"]}{role_str}\n   {r}{extra_str}'))
    for yr in sorted(year_groups):
        lines.append(f'\n✨ {yr} 年 ✨\n──────────────')
        for _, line in sorted(year_groups[yr]): lines.append(line)
    lines.append('══════════════')
    return render_template('export.html', text='\n'.join(lines))

# ── 黑名单 ──────────────────────────────────────────────────────────────────────

@app.route('/blacklist')
@require_login
def blacklist():
    uid = session['user_id']
    q = request.args.get('q', '').strip()
    rows = [dict(r) for r in get_db().execute(
        'SELECT * FROM blacklist WHERE user_id=? ORDER BY created_at DESC', (uid,)
    ).fetchall()]
    if q:
        rows = [r for r in rows if q in r['qq'] or q in r['nickname'] or q in r['reason'] or q in r['notes']]
    for r in rows:
        r['shared_guilds_list'] = json.loads(r.get('shared_guilds') or '[]')
    owned, member = _get_my_guilds(uid)
    my_guilds = owned + member
    return render_template('blacklist.html', entries=rows, q=q, my_guilds=my_guilds)

@app.route('/blacklist/add', methods=['POST'])
@require_login
def blacklist_add():
    uid = session['user_id']
    qq       = request.form.get('qq', '').strip()
    nickname = request.form.get('nickname', '').strip()
    reason   = request.form.get('reason', '').strip()
    happened = request.form.get('happened_at', '').strip()
    notes    = request.form.get('notes', '').strip()
    if not qq and not nickname:
        flash('❌ QQ 号或昵称至少填一项')
        return redirect(url_for('blacklist'))
    get_db().execute(
        'INSERT INTO blacklist (user_id, qq, nickname, reason, happened_at, notes, created_at) VALUES (?,?,?,?,?,?,?)',
        (uid, qq, nickname, reason, happened, notes, int(datetime.now().timestamp()))
    )
    get_db().commit()
    flash(f'已拉黑「{nickname or qq}」')
    return redirect(url_for('blacklist'))

@app.route('/blacklist/<int:bid>/delete', methods=['POST'])
@require_login
def blacklist_delete(bid):
    uid = session['user_id']
    r = get_db().execute('SELECT qq, nickname FROM blacklist WHERE id=? AND user_id=?', (bid, uid)).fetchone()
    if r:
        get_db().execute('DELETE FROM blacklist WHERE id=? AND user_id=?', (bid, uid))
        get_db().commit()
        flash(f'已从黑名单移除「{r["nickname"] or r["qq"]}」')
    return redirect(url_for('blacklist'))


# ── 提醒 ─────────────────────────────────────────────────────────────────────────

@app.route('/reminders/add', methods=['POST'])
@require_login
def reminder_add():
    uid     = session['user_id']
    content = request.form.get('content', '').strip()
    rdate   = request.form.get('remind_date', '').strip()
    if not content:
        flash('❌ 提醒内容不能为空')
        return redirect(url_for('calendar'))
    if rdate:
        try: datetime.strptime(rdate, '%Y-%m-%d')
        except: rdate = ''
    get_db().execute(
        'INSERT INTO reminders (user_id, content, remind_date, is_done, created_at) VALUES (?,?,?,0,?)',
        (uid, content, rdate, int(datetime.now().timestamp()))
    )
    get_db().commit()
    return redirect(url_for('calendar'))

@app.route('/reminders/<int:rid>/done', methods=['POST'])
@require_login
def reminder_done(rid):
    uid = session['user_id']
    get_db().execute('UPDATE reminders SET is_done=1 WHERE id=? AND user_id=?', (rid, uid))
    get_db().commit()
    return redirect(url_for('calendar'))

@app.route('/reminders/<int:rid>/delete', methods=['POST'])
@require_login
def reminder_delete(rid):
    uid = session['user_id']
    get_db().execute('DELETE FROM reminders WHERE id=? AND user_id=?', (rid, uid))
    get_db().commit()
    return redirect(url_for('calendar'))


# ── Settings ────────────────────────────────────────────────────────────────────

@app.route('/settings', methods=['GET', 'POST'])
@require_login
def settings():
    uid = session['user_id']; db = get_db()
    user = dict(db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone())
    errors = []; success = None

    if request.method == 'POST':
        action = request.form.get('action', '')

        if action == 'profile':
            display_name = request.form.get('display_name', '').strip()
            cur_pass     = request.form.get('current_password', '')
            new_pass     = request.form.get('new_password', '').strip()
            if not check_password_hash(user['password_hash'], cur_pass):
                errors.append('当前密码错误')
            else:
                if new_pass:
                    if len(new_pass) < 4: errors.append('新密码至少 4 位')
                    else:
                        db.execute('UPDATE users SET password_hash=? WHERE id=?',
                                   (generate_password_hash(new_pass), uid))
                if not errors:
                    db.execute('UPDATE users SET display_name=? WHERE id=?',
                               (display_name or user['username'], uid))
                    db.commit()
                    session['display_name'] = display_name or user['username']
                    success = '个人信息已更新'
                    user = dict(db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone())

        elif action == 'dual_mode_toggle':
            new_state = 0 if user['dual_mode'] else 1
            db.execute('UPDATE users SET dual_mode=? WHERE id=?', (new_state, uid))
            db.commit()
            user = dict(db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone())
            success = '双开模式已' + ('开启' if new_state else '关闭')

        elif action == 'share_toggle':
            new_state = 0 if user['share_enabled'] else 1
            if new_state == 1 and not user['share_token']:
                token = secrets.token_urlsafe(16)
                db.execute('UPDATE users SET share_token=?, share_enabled=1 WHERE id=?', (token, uid))
            else:
                db.execute('UPDATE users SET share_enabled=? WHERE id=?', (new_state, uid))
            db.commit()
            user = dict(db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone())
            success = '分享链接已' + ('开启' if new_state else '关闭')

        elif action == 'share_view_set':
            view = request.form.get('share_view', 'calendar')
            if view not in ('calendar', 'stats'): view = 'calendar'
            db.execute('UPDATE users SET share_view=? WHERE id=?', (view, uid))
            db.commit()
            user = dict(db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone())
            success = '分享内容已更新'

        elif action == 'share_regen':
            token = secrets.token_urlsafe(16)
            db.execute('UPDATE users SET share_token=?, share_enabled=1 WHERE id=?', (token, uid))
            db.commit()
            user = dict(db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone())
            success = '分享链接已重新生成'

    return render_template('settings.html', user=user, errors=errors, success=success)

@app.route('/api/theme', methods=['POST'])
@require_login
def api_set_theme():
    theme = (request.json or {}).get('theme', '') if request.is_json else request.form.get('theme', '')
    db  = get_db()
    uid = session['user_id']
    if theme in VIP_THEMES and not _is_vip(db):
        return jsonify({'ok': False, 'error': 'vip_required'})
    if theme in ACHIEVEMENT_THEMES and theme not in _get_unlocked_achievements(db, uid):
        return jsonify({'ok': False, 'error': 'achievement_locked'})
    db.execute('UPDATE users SET theme=? WHERE id=?', (theme, uid))
    db.commit()
    return jsonify({'ok': True})

# ── Feedback ────────────────────────────────────────────────────────────────────

@app.route('/feedback', methods=['POST'])
@require_login
def submit_feedback():
    ftype   = request.form.get('type', 'bug').strip()
    content = request.form.get('content', '').strip()
    if ftype not in ('bug', 'wish'): ftype = 'bug'
    if not content:
        return jsonify({'ok': False, 'error': '内容不能为空'})
    if len(content) > 1000:
        return jsonify({'ok': False, 'error': '内容不能超过 1000 字'})
    db = get_db()
    db.execute('INSERT INTO feedbacks (user_id, type, content, created_at, is_read) VALUES (?,?,?,?,0)',
               (session['user_id'], ftype, content, int(datetime.now().timestamp())))
    db.commit()
    return jsonify({'ok': True})

@app.route('/superadmin/feedbacks')
@require_superadmin
def superadmin_feedbacks():
    db = get_db()
    PER_PAGE = 20
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    ftype = request.args.get('type', '')
    where = 'WHERE f.type=?' if ftype in ('bug', 'wish') else ''
    params_count = (ftype,) if ftype in ('bug', 'wish') else ()
    total = db.execute(f'SELECT COUNT(*) FROM feedbacks f {where}', params_count).fetchone()[0]
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = min(page, total_pages)
    params = params_count + (PER_PAGE, (page - 1) * PER_PAGE)
    feedbacks = db.execute(f'''
        SELECT f.*, u.username, u.display_name
        FROM feedbacks f JOIN users u ON u.id=f.user_id
        {where} ORDER BY f.created_at DESC LIMIT ? OFFSET ?
    ''', params).fetchall()
    return render_template('superadmin_feedbacks.html',
                           feedbacks=feedbacks, page=page, total_pages=total_pages,
                           total=total, ftype=ftype)

@app.route('/superadmin/feedbacks/<int:fid>/read', methods=['POST'])
@require_superadmin
def superadmin_feedback_read(fid):
    db = get_db()
    db.execute('UPDATE feedbacks SET is_read=1 WHERE id=?', (fid,))
    db.commit()
    return redirect(request.referrer or url_for('superadmin_feedbacks'))

@app.route('/superadmin/feedbacks/read-all', methods=['POST'])
@require_superadmin
def superadmin_feedback_read_all():
    db = get_db()
    db.execute('UPDATE feedbacks SET is_read=1')
    db.commit()
    return redirect(url_for('superadmin_feedbacks'))

@app.route('/superadmin/feedbacks/<int:fid>/delete', methods=['POST'])
@require_superadmin
def superadmin_feedback_delete(fid):
    db = get_db()
    db.execute('DELETE FROM feedbacks WHERE id=?', (fid,))
    db.commit()
    return redirect(request.referrer or url_for('superadmin_feedbacks'))

# ── Day events ──────────────────────────────────────────────────────────────────

@app.route('/api/events', methods=['POST'])
@require_login
def api_add_event():
    title      = request.form.get('title', '').strip()
    event_date = request.form.get('event_date', '').strip()
    color      = request.form.get('color', '#8b7cf6').strip()
    if not title:            return jsonify({'ok': False, 'error': '标题不能为空'})
    if len(title) > 30:      return jsonify({'ok': False, 'error': '标题最多30字'})
    try: datetime.strptime(event_date, '%Y-%m-%d')
    except: return jsonify({'ok': False, 'error': '日期格式错误'})
    uid = session['user_id']; db = get_db()
    cur = db.execute(
        'INSERT INTO day_events (user_id, event_date, title, color, created_at) VALUES (?,?,?,?,?)',
        (uid, event_date, title, color, int(datetime.now().timestamp()))
    )
    db.commit()
    return jsonify({'ok': True, 'id': cur.lastrowid, 'title': title, 'color': color})

@app.route('/api/events/<int:eid>/delete', methods=['POST'])
@require_login
def api_delete_event(eid):
    uid = session['user_id']; db = get_db()
    db.execute('DELETE FROM day_events WHERE id=? AND user_id=?', (eid, uid))
    db.commit()
    return jsonify({'ok': True})

# ── Public view ─────────────────────────────────────────────────────────────────

@app.route('/u/<token>')
def public_view(token):
    db = get_db()
    user = db.execute(
        'SELECT * FROM users WHERE share_token=? AND share_enabled=1 AND is_active=1', (token,)
    ).fetchone()
    if not user: abort(404)
    now = datetime.now()
    try:
        year  = int(request.args.get('year',  now.year))
        month = int(request.args.get('month', now.month))
        if not (1 <= month <= 12 and 1900 <= year <= 2100): raise ValueError
    except (ValueError, TypeError):
        year, month = now.year, now.month

    all_schedules = _enrich_schedules([dict(r) for r in db.execute(
        'SELECT * FROM schedules WHERE user_id=? ORDER BY start_year, time_range', (user['id'],)
    ).fetchall()])
    conflict_ids = find_all_conflicts(all_schedules)
    day_shows, active, days_in = schedules_for_month(all_schedules, year, month)
    deadline_days = deadlines_for_month(all_schedules, year, month)
    cal_rows = _build_cal_rows(year, month)
    free     = _free_intervals(day_shows, days_in)

    prev_year,  prev_month  = (year-1, 12) if month==1  else (year, month-1)
    next_year,  next_month  = (year+1,  1) if month==12 else (year, month+1)

    share_view = (user['share_view'] or 'calendar') if 'share_view' in user.keys() else 'calendar'
    if share_view == 'stats':
        years_set = {now.year}
        for s in all_schedules:
            years_set.add(s['start_year'])
            p = parse_time_range(s['time_range'])
            if p['valid'] and is_cross_year(p): years_set.add(s['start_year'] + 1)
        stats_year = year
        if stats_year not in years_set: stats_year = now.year
        data = annual_stats(all_schedules, stats_year)
        return render_template('public_stats.html',
            owner=user, token=token,
            data=data, year=stats_year,
            years=sorted(years_set, reverse=True),
        )
    return render_template('public_calendar.html',
        owner=user, token=token,
        year=year, month=month, days_in=days_in,
        cal_rows=cal_rows, day_shows=day_shows, active=active,
        deadline_days=deadline_days,
        free=free, all_schedules=all_schedules,
        conflict_ids=conflict_ids,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        now_year=now.year, now_month=now.month, now_day=now.day,
    )


# ── 公开检举 ────────────────────────────────────────────────────────────────────


@app.route('/reports', methods=['GET', 'POST'])
@require_login
def reports():
    db = get_db()
    error = None
    success = False
    if request.method == 'POST':
        target_qq = (request.form.get('target_qq') or '').strip()
        tag        = (request.form.get('tag')       or '').strip()
        reason     = (request.form.get('reason')    or '').strip()
        if not target_qq:
            error = 'QQ 号不能为空'
        elif not re.match(r'^\d{5,12}$', target_qq):
            error = 'QQ 号格式不正确（5-12位数字）'
        elif not reason:
            error = '检举原因不能为空'
        else:
            db.execute(
                'INSERT INTO reports (target_qq, tag, reason, submitter_user_id, status, created_at) VALUES (?,?,?,?,?,?)',
                (target_qq, tag, reason, session['user_id'], 'pending', int(datetime.now().timestamp()))
            )
            db.commit()
            session['report_just_submitted'] = True
            return redirect(url_for('reports'))

    success    = session.pop('report_just_submitted', False)
    appeal_ok  = session.pop('appeal_just_submitted', False)
    appeal_err = session.pop('appeal_error', None)
    uid = session.get('user_id')
    approved_count = db.execute(
        "SELECT COUNT(*) FROM reports WHERE submitter_user_id=? AND status='approved'", (uid,)
    ).fetchone()[0] if uid else 0
    can_view = approved_count >= 2

    GROUPS_PER_PAGE = 8
    q = (request.args.get('q') or '').strip()
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1

    groups = []
    total_groups = 0
    total_pages = 1
    if can_view:
        if q:
            rows = db.execute(
                "SELECT id, target_qq, tag, reason, created_at FROM reports WHERE status='approved' AND target_qq LIKE ? ORDER BY created_at DESC",
                (f'%{q}%',)
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT id, target_qq, tag, reason, created_at FROM reports WHERE status='approved' ORDER BY created_at DESC"
            ).fetchall()
        from collections import defaultdict
        grp = defaultdict(list)
        for r in rows:
            grp[r['target_qq']].append(r)
        all_groups = sorted(grp.items(), key=lambda x: len(x[1]), reverse=True)
        total_groups = len(all_groups)
        total_pages = max(1, (total_groups + GROUPS_PER_PAGE - 1) // GROUPS_PER_PAGE)
        page = min(page, total_pages)
        groups = all_groups[(page - 1) * GROUPS_PER_PAGE : page * GROUPS_PER_PAGE]

    MY_PER_PAGE = 5
    try: mypage = max(1, int(request.args.get('mypage', 1)))
    except (ValueError, TypeError): mypage = 1

    my_reports = []
    my_total = 0
    my_total_pages = 1
    appealed_ids = set()
    if uid:
        my_total = db.execute(
            'SELECT COUNT(*) FROM reports WHERE submitter_user_id=?', (uid,)
        ).fetchone()[0]
        my_total_pages = max(1, (my_total + MY_PER_PAGE - 1) // MY_PER_PAGE)
        mypage = min(mypage, my_total_pages)
        my_reports = [dict(r) for r in db.execute(
            'SELECT * FROM reports WHERE submitter_user_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?',
            (uid, MY_PER_PAGE, (mypage - 1) * MY_PER_PAGE)
        ).fetchall()]
        appealed_ids = {r['report_id'] for r in db.execute(
            "SELECT report_id FROM report_appeals WHERE submitter_user_id=? AND status IN ('pending','approved')",
            (uid,)
        ).fetchall()}

    return render_template('reports.html', groups=groups, error=error, success=success,
                           appeal_ok=appeal_ok, appeal_err=appeal_err,
                           can_view=can_view, approved_count=approved_count,
                           q=q, page=page, total_pages=total_pages, total_groups=total_groups,
                           my_reports=my_reports, my_total=my_total,
                           mypage=mypage, my_total_pages=my_total_pages,
                           appealed_ids=appealed_ids)

@app.route('/reports/<int:rid>/self-delete', methods=['POST'])
@require_login
def report_self_delete(rid):
    db = get_db()
    row = db.execute('SELECT submitter_user_id, status FROM reports WHERE id=?', (rid,)).fetchone()
    if not row or row['submitter_user_id'] != session['user_id']:
        abort(403)
    if row['status'] == 'approved':
        approved_count = db.execute(
            "SELECT COUNT(*) FROM reports WHERE submitter_user_id=? AND status='approved'", (session['user_id'],)
        ).fetchone()[0]
        if approved_count <= 2:
            flash('至少需要保留 2 条已通过的检举，无法删除。', 'error')
            return redirect(url_for('reports'))
    db.execute('DELETE FROM reports WHERE id=?', (rid,))
    db.commit()
    return redirect(url_for('reports'))

@app.route('/reports/<int:rid>/delete', methods=['POST'])
@require_superadmin
def report_delete(rid):
    db = get_db()
    db.execute('DELETE FROM reports WHERE id=?', (rid,))
    db.commit()
    return redirect(url_for('superadmin_reports'))

@app.route('/reports/<int:rid>/approve', methods=['POST'])
@require_superadmin
def report_approve(rid):
    db = get_db()
    db.execute("UPDATE reports SET status='approved' WHERE id=?", (rid,))
    db.commit()
    return redirect(url_for('superadmin_reports'))

@app.route('/reports/<int:rid>/revoke', methods=['POST'])
@require_superadmin
def report_revoke(rid):
    db = get_db()
    db.execute("UPDATE reports SET status='pending' WHERE id=?", (rid,))
    db.commit()
    return redirect(url_for('superadmin_reports', tab='approved'))

@app.route('/reports/<int:rid>/reject', methods=['POST'])
@require_superadmin
def report_reject(rid):
    db = get_db()
    db.execute("UPDATE reports SET status='rejected' WHERE id=?", (rid,))
    db.commit()
    return redirect(url_for('superadmin_reports'))

@app.route('/reports/<int:rid>/request-edit', methods=['POST'])
@require_superadmin
def report_request_edit(rid):
    db = get_db()
    note = (request.form.get('edit_note') or '').strip()
    db.execute("UPDATE reports SET status='editing', edit_note=? WHERE id=?", (note, rid))
    db.commit()
    tab = request.form.get('from_tab', 'pending')
    return redirect(url_for('superadmin_reports', tab=tab))

@app.route('/reports/<int:rid>/user-edit', methods=['POST'])
@require_login
def report_user_edit(rid):
    db = get_db()
    row = db.execute("SELECT submitter_user_id, status FROM reports WHERE id=?", (rid,)).fetchone()
    if not row or row['submitter_user_id'] != session['user_id']:
        abort(403)
    if row['status'] != 'editing':
        abort(403)
    tag    = (request.form.get('tag')    or '').strip()
    reason = (request.form.get('reason') or '').strip()
    if not reason:
        session['edit_error'] = rid
        return redirect(url_for('reports', mypage=request.args.get('mypage', 1)))
    db.execute("UPDATE reports SET tag=?, reason=?, status='pending', edit_note='' WHERE id=?",
               (tag, reason, rid))
    db.commit()
    session['edit_success'] = True
    return redirect(url_for('reports'))

@app.route('/reports/<int:rid>/appeal', methods=['POST'])
@require_login
def report_appeal(rid):
    db = get_db()
    uid = session['user_id']
    reason = (request.form.get('reason') or '').strip()
    if not reason:
        session['appeal_error'] = '申请理由不能为空'
        return redirect(url_for('reports'))
    row = db.execute("SELECT id FROM reports WHERE id=? AND status='approved'", (rid,)).fetchone()
    if not row:
        session['appeal_error'] = '该检举不存在或已被撤下'
        return redirect(url_for('reports'))
    existing = db.execute(
        "SELECT id FROM report_appeals WHERE report_id=? AND submitter_user_id=? AND status='pending'",
        (rid, uid)
    ).fetchone()
    if existing:
        session['appeal_error'] = '你已对这条检举提交过撤回申请，请等待审核'
        return redirect(url_for('reports'))
    db.execute(
        'INSERT INTO report_appeals (report_id, submitter_user_id, reason, status, created_at) VALUES (?,?,?,?,?)',
        (rid, uid, reason, 'pending', int(datetime.now().timestamp()))
    )
    db.commit()
    session['appeal_just_submitted'] = True
    return redirect(url_for('reports'))

@app.route('/reports/appeals/<int:aid>/approve', methods=['POST'])
@require_superadmin
def appeal_approve(aid):
    db = get_db()
    appeal = db.execute('SELECT * FROM report_appeals WHERE id=?', (aid,)).fetchone()
    if appeal:
        db.execute("UPDATE report_appeals SET status='approved' WHERE id=?", (aid,))
        db.execute("UPDATE reports SET status='pending' WHERE id=?", (appeal['report_id'],))
        db.commit()
    return redirect(url_for('superadmin_reports', tab='appeals'))

@app.route('/reports/appeals/<int:aid>/reject', methods=['POST'])
@require_superadmin
def appeal_reject(aid):
    db = get_db()
    note = (request.form.get('admin_note') or '').strip()
    db.execute("UPDATE report_appeals SET status='rejected', admin_note=? WHERE id=?", (note, aid))
    db.commit()
    return redirect(url_for('superadmin_reports', tab='appeals'))

@app.route('/superadmin/reports')
@require_superadmin
def superadmin_reports():
    db = get_db()
    tab = request.args.get('tab', 'pending')
    if tab not in ('pending', 'approved', 'rejected', 'appeals', 'editing'):
        tab = 'pending'

    counts = {s: db.execute("SELECT COUNT(*) FROM reports WHERE status=?", (s,)).fetchone()[0]
              for s in ('pending', 'approved', 'rejected', 'editing')}
    counts['appeals'] = db.execute(
        "SELECT COUNT(*) FROM report_appeals WHERE status='pending'"
    ).fetchone()[0]

    appeals = []
    groups = []
    sorted_groups = []

    if tab == 'appeals':
        appeals = [dict(r) for r in db.execute('''
            SELECT a.id, a.report_id, a.reason, a.created_at,
                   r.target_qq, r.tag, r.reason AS report_reason,
                   u.username AS submitter_name, u.display_name AS submitter_display
            FROM report_appeals a
            JOIN reports r ON r.id = a.report_id
            LEFT JOIN users u ON u.id = a.submitter_user_id
            WHERE a.status = 'pending'
            ORDER BY a.created_at DESC
        ''').fetchall()]
    else:
        if tab == 'pending':
            rows = db.execute('''
                SELECT r.*, u.username AS submitter_name, u.display_name AS submitter_display
                FROM reports r LEFT JOIN users u ON u.id=r.submitter_user_id
                WHERE r.status IN ('pending', 'editing')
                ORDER BY r.created_at DESC
            ''').fetchall()
        else:
            rows = db.execute('''
                SELECT r.*, u.username AS submitter_name, u.display_name AS submitter_display
                FROM reports r LEFT JOIN users u ON u.id=r.submitter_user_id
                WHERE r.status=?
                ORDER BY r.created_at DESC
            ''', (tab,)).fetchall()
        from collections import defaultdict
        groups = defaultdict(list)
        for r in rows:
            groups[r['target_qq']].append(r)
        sorted_groups = sorted(groups.items(), key=lambda x: len(x[1]), reverse=True)

    return render_template('superadmin_reports.html',
                           groups=sorted_groups, appeals=appeals,
                           tab=tab, counts=counts)


# ── Superadmin ──────────────────────────────────────────────────────────────────

@app.route('/superadmin/login', methods=['GET', 'POST'])
def superadmin_login():
    if session.get('superadmin'): return redirect(url_for('superadmin'))
    if request.method == 'POST':
        if request.form.get('password') == SUPERADMIN_PASS:
            session['superadmin'] = True; return redirect(url_for('superadmin'))
        return render_template('superadmin_login.html', error='密码错误')
    return render_template('superadmin_login.html')

@app.route('/superadmin/logout', methods=['POST'])
def superadmin_logout():
    session.pop('superadmin', None); return redirect(url_for('superadmin_login'))

@app.route('/superadmin')
@require_superadmin
def superadmin():
    db = get_db()
    PER_PAGE = 10
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    total_users = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    total_pages = max(1, (total_users + PER_PAGE - 1) // PER_PAGE)
    page = min(page, total_pages)
    users = db.execute('''
        SELECT u.*, COUNT(s.id) AS schedule_count
        FROM users u LEFT JOIN schedules s ON s.user_id=u.id
        GROUP BY u.id ORDER BY u.created_at DESC
        LIMIT ? OFFSET ?
    ''', (PER_PAGE, (page - 1) * PER_PAGE)).fetchall()
    try:
        ipage = max(1, int(request.args.get('ipage', 1)))
    except (ValueError, TypeError):
        ipage = 1
    total_codes = db.execute('SELECT COUNT(*) FROM invite_codes').fetchone()[0]
    total_ipages = max(1, (total_codes + PER_PAGE - 1) // PER_PAGE)
    ipage = min(ipage, total_ipages)
    codes = db.execute('''
        SELECT ic.*, u.username AS used_by_name
        FROM invite_codes ic LEFT JOIN users u ON u.id=ic.used_by
        ORDER BY ic.created_at DESC LIMIT ? OFFSET ?
    ''', (PER_PAGE, (ipage - 1) * PER_PAGE)).fetchall()
    return render_template('superadmin.html', users=users, codes=codes,
                           page=page, total_pages=total_pages, total_users=total_users,
                           ipage=ipage, total_ipages=total_ipages, total_codes=total_codes)

@app.route('/superadmin/invite/generate', methods=['POST'])
@require_superadmin
def superadmin_gen_invite():
    db = get_db()
    code = secrets.token_urlsafe(8)
    db.execute('INSERT INTO invite_codes (code, created_at) VALUES (?,?)',
               (code, int(datetime.now().timestamp())))
    db.commit()
    flash(f'✅ 邀请码已生成：{code}')
    return redirect(url_for('superadmin'))

@app.route('/superadmin/invite/<int:iid>/delete', methods=['POST'])
@require_superadmin
def superadmin_del_invite(iid):
    db = get_db()
    db.execute('DELETE FROM invite_codes WHERE id=?', (iid,))
    db.commit()
    flash('邀请码已删除')
    return redirect(url_for('superadmin'))

@app.route('/superadmin/users/create', methods=['POST'])
@require_superadmin
def superadmin_create_user():
    db = get_db()
    username     = request.form.get('username',     '').strip()
    password     = request.form.get('password',     '').strip()
    display_name = request.form.get('display_name', '').strip()
    errors = []
    if not username: errors.append('用户名不能为空')
    elif db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone():
        errors.append(f'用户名「{username}」已存在')
    if not password: errors.append('密码不能为空')
    elif len(password) < 4: errors.append('密码至少 4 位')
    if errors:
        users = db.execute('''SELECT u.*, COUNT(s.id) AS schedule_count FROM users u
            LEFT JOIN schedules s ON s.user_id=u.id GROUP BY u.id ORDER BY u.created_at DESC LIMIT 10''').fetchall()
        total_users = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        total_codes = db.execute('SELECT COUNT(*) FROM invite_codes').fetchone()[0]
        codes = db.execute('''SELECT ic.*, u.username AS used_by_name FROM invite_codes ic
            LEFT JOIN users u ON u.id=ic.used_by ORDER BY ic.created_at DESC LIMIT 10''').fetchall()
        return render_template('superadmin.html', users=users, codes=codes, create_errors=errors, create_form=request.form,
                               page=1, total_pages=max(1,(total_users+9)//10), total_users=total_users,
                               ipage=1, total_ipages=max(1,(total_codes+9)//10), total_codes=total_codes)
    db.execute('INSERT INTO users (username, password_hash, display_name, is_active, created_at) VALUES (?,?,?,1,?)',
               (username, generate_password_hash(password), display_name or username, int(datetime.now().timestamp())))
    db.commit()
    flash(f'✅ 已创建用户「{username}」'); return redirect(url_for('superadmin'))

@app.route('/superadmin/users/<int:uid>/reset', methods=['POST'])
@require_superadmin
def superadmin_reset_password(uid):
    new_pass = request.form.get('new_password', '').strip()
    if not new_pass or len(new_pass) < 4:
        flash('❌ 密码至少 4 位'); return redirect(url_for('superadmin'))
    db = get_db()
    db.execute('UPDATE users SET password_hash=? WHERE id=?', (generate_password_hash(new_pass), uid))
    db.commit()
    user = db.execute('SELECT username FROM users WHERE id=?', (uid,)).fetchone()
    flash(f'✅ 已重置「{user["username"]}」的密码'); return redirect(url_for('superadmin'))

@app.route('/superadmin/users/<int:uid>/toggle', methods=['POST'])
@require_superadmin
def superadmin_toggle_user(uid):
    db = get_db()
    user = db.execute('SELECT username, is_active FROM users WHERE id=?', (uid,)).fetchone()
    if user:
        new_state = 0 if user['is_active'] else 1
        db.execute('UPDATE users SET is_active=? WHERE id=?', (new_state, uid)); db.commit()
        flash(f'{"✅ 已启用" if new_state else "⏸ 已停用"}用户「{user["username"]}」')
    return redirect(url_for('superadmin'))

@app.route('/superadmin/users/<int:uid>/delete', methods=['POST'])
@require_superadmin
def superadmin_delete_user(uid):
    db = get_db()
    user = db.execute('SELECT username FROM users WHERE id=?', (uid,)).fetchone()
    if user:
        db.execute('DELETE FROM schedules WHERE user_id=?', (uid,))
        db.execute('DELETE FROM users WHERE id=?', (uid,)); db.commit()
        flash(f'已删除用户「{user["username"]}」及其所有档期')
    return redirect(url_for('superadmin'))

@app.route('/superadmin/users/<int:uid>/view')
@require_superadmin
def superadmin_view_user(uid):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not user: abort(404)
    now = datetime.now()
    all_schedules = [dict(r) for r in db.execute(
        'SELECT * FROM schedules WHERE user_id=? ORDER BY start_year, time_range', (uid,)
    ).fetchall()]
    conflict_ids = find_all_conflicts(all_schedules)
    try:
        year  = int(request.args.get('year',  now.year))
        month = int(request.args.get('month', now.month))
        if not (1 <= month <= 12 and 1900 <= year <= 2100): raise ValueError
    except (ValueError, TypeError):
        year, month = now.year, now.month
    day_shows, active, days_in = schedules_for_month(all_schedules, year, month)
    cal_rows = _build_cal_rows(year, month)
    free     = _free_intervals(day_shows, days_in)
    prev_year,  prev_month  = (year-1, 12) if month==1  else (year, month-1)
    next_year,  next_month  = (year+1,  1) if month==12 else (year, month+1)
    return render_template('superadmin_user_view.html',
        owner=user, year=year, month=month, days_in=days_in,
        cal_rows=cal_rows, day_shows=day_shows, active=active,
        free=free, all_schedules=all_schedules, conflict_ids=conflict_ids,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        now_year=now.year, now_month=now.month, now_day=now.day,
    )


# ── 戏录 ────────────────────────────────────────────────────────────────────────

@app.route('/drama')
@require_login
def drama_list():
    uid = session['user_id']
    tag_filter = request.args.get('tag', '')
    dramas = [dict(r) for r in get_db().execute(
        'SELECT * FROM dramas WHERE user_id=? ORDER BY updated_at DESC', (uid,)
    ).fetchall()]
    for d in dramas:
        d['tags_list'] = json.loads(d['tags']) if d['tags'] else []
        d['wc'] = word_count(d['content'])
    if tag_filter:
        dramas = [d for d in dramas if tag_filter in d['tags_list']]
    all_dramas_raw = [dict(r) for r in get_db().execute(
        'SELECT tags, content FROM dramas WHERE user_id=?', (uid,)
    ).fetchall()]
    total_wc = sum(word_count(d['content']) for d in all_dramas_raw)
    all_used = set()
    for d in all_dramas_raw:
        for t in (json.loads(d['tags']) if d['tags'] else []):
            if t not in FIXED_TAGS: all_used.add(t)
    return render_template('drama.html', dramas=dramas, tag_filter=tag_filter,
                           fixed_tags=FIXED_TAGS, custom_tags=sorted(all_used),
                           total_count=len(all_dramas_raw), total_wc=total_wc)

@app.route('/drama/new', methods=['GET', 'POST'])
@require_login
def drama_new():
    uid = session['user_id']; db = get_db()
    count = db.execute('SELECT COUNT(*) FROM dramas WHERE user_id=?', (uid,)).fetchone()[0]
    if count >= 50:
        flash('❌ 最多保存 50 个戏录'); return redirect(url_for('drama_list'))
    if request.method == 'POST':
        title   = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        wt_str  = request.form.get('writing_time', '').strip()
        errors  = []
        if not title: errors.append('标题不能为空')
        elif db.execute('SELECT id FROM dramas WHERE user_id=? AND title=?', (uid, title)).fetchone():
            errors.append(f'已有同名戏录「{title}」')
        tags = [t for t in FIXED_TAGS if request.form.get(f'tag_{t}')]
        c1 = request.form.get('custom_tag1', '').strip()
        c2 = request.form.get('custom_tag2', '').strip()
        if c1 and c1 not in tags: tags.append(c1)
        if c2 and c2 not in tags and c2 != c1: tags.append(c2)
        wt = None
        if wt_str:
            try: wt = int(datetime.strptime(wt_str, '%Y-%m-%d').timestamp())
            except: errors.append('写作日期格式错误，应为 YYYY-MM-DD')
        if errors:
            return render_template('drama_form.html', action='new', form=request.form,
                                   errors=errors, fixed_tags=FIXED_TAGS, default_title=title)
        ts = int(datetime.now().timestamp())
        db.execute('INSERT INTO dramas (user_id, title, tags, content, writing_time, created_at, updated_at) VALUES (?,?,?,?,?,?,?)',
                   (uid, title, json.dumps(tags, ensure_ascii=False), content, wt, ts, ts))
        db.commit()
        flash(f'✅ 戏录「{title}」已保存')
        return redirect(url_for('drama_list'))
    default_title = _next_drama_title(uid)
    return render_template('drama_form.html', action='new', form={'title': default_title},
                           errors=[], fixed_tags=FIXED_TAGS, default_title=default_title)

@app.route('/drama/<int:did>/edit', methods=['GET', 'POST'])
@require_login
def drama_edit(did):
    uid = session['user_id']; db = get_db()
    d = db.execute('SELECT * FROM dramas WHERE id=? AND user_id=?', (did, uid)).fetchone()
    if not d: abort(404)
    d = dict(d); d['tags_list'] = json.loads(d['tags']) if d['tags'] else []
    if request.method == 'POST':
        title   = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        wt_str  = request.form.get('writing_time', '').strip()
        errors  = []
        if not title: errors.append('标题不能为空')
        elif db.execute('SELECT id FROM dramas WHERE user_id=? AND title=? AND id!=?', (uid, title, did)).fetchone():
            errors.append(f'已有同名戏录「{title}」')
        tags = [t for t in FIXED_TAGS if request.form.get(f'tag_{t}')]
        c1 = request.form.get('custom_tag1', '').strip()
        c2 = request.form.get('custom_tag2', '').strip()
        if c1 and c1 not in tags: tags.append(c1)
        if c2 and c2 not in tags and c2 != c1: tags.append(c2)
        wt = None
        if wt_str:
            try: wt = int(datetime.strptime(wt_str, '%Y-%m-%d').timestamp())
            except: errors.append('写作日期格式错误，应为 YYYY-MM-DD')
        if errors:
            return render_template('drama_form.html', action='edit', form=request.form,
                                   errors=errors, fixed_tags=FIXED_TAGS, drama=d)
        db.execute('UPDATE dramas SET title=?, tags=?, content=?, writing_time=?, updated_at=? WHERE id=? AND user_id=?',
                   (title, json.dumps(tags, ensure_ascii=False), content, wt,
                    int(datetime.now().timestamp()), did, uid))
        db.commit()
        flash(f'✅ 戏录「{title}」已更新')
        return redirect(url_for('drama_list'))
    return render_template('drama_form.html', action='edit', form=d, errors=[], fixed_tags=FIXED_TAGS, drama=d)

@app.route('/drama/<int:did>/delete', methods=['POST'])
@require_login
def drama_delete(did):
    uid = session['user_id']; db = get_db()
    d = db.execute('SELECT title FROM dramas WHERE id=? AND user_id=?', (did, uid)).fetchone()
    if d:
        db.execute('DELETE FROM dramas WHERE id=? AND user_id=?', (did, uid)); db.commit()
        flash(f'已删除戏录「{d["title"]}」')
    return redirect(url_for('drama_list'))

@app.route('/drama/<int:did>/view')
@require_login
def drama_view(did):
    uid = session['user_id']
    d = get_db().execute('SELECT * FROM dramas WHERE id=? AND user_id=?', (did, uid)).fetchone()
    if not d: abort(404)
    d = dict(d)
    d['tags_list'] = json.loads(d['tags']) if d['tags'] else []
    d['wc'] = word_count(d['content'])
    return render_template('drama_view.html', drama=d)

@app.route('/drama/<int:did>/content')
@require_login
def drama_content(did):
    uid = session['user_id']
    d = get_db().execute('SELECT content FROM dramas WHERE id=? AND user_id=?', (did, uid)).fetchone()
    if not d: abort(404)
    return jsonify({'content': d['content']})

@app.route('/drama/export')
@require_login
def drama_export():
    from flask import Response
    uid = session['user_id']
    dramas = [dict(r) for r in get_db().execute(
        'SELECT * FROM dramas WHERE user_id=? ORDER BY updated_at DESC', (uid,)
    ).fetchall()]
    name = session.get('display_name') or session.get('username')
    lines = [f'【{name} 的戏录】\n共 {len(dramas)} 篇\n{"═"*40}\n']
    for i, d in enumerate(dramas, 1):
        tags = json.loads(d['tags']) if d['tags'] else []
        wt = datetimeformat(d['writing_time']) if d['writing_time'] else '—'
        wc = word_count(d['content'])
        lines.append(f'【{i}】{d["title"]}')
        if tags: lines.append(f'标签：{" · ".join(tags)}')
        lines.append(f'字数：{wc}　写于：{wt}')
        lines.append('─' * 30)
        lines.append(d['content'] or '（无内容）')
        lines.append('\n' + '═' * 40 + '\n')
    text = '\n'.join(lines)
    filename = f'{name}_戏录.txt'
    return Response(
        text.encode('utf-8'),
        mimetype='text/plain; charset=utf-8',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{_urlquote(filename)}"}
    )


# ── 小工具 ───────────────────────────────────────────────────────────────────────

@app.route('/tools')
@require_login
def tools():
    return render_template('tools.html')


# ── CP档案 ───────────────────────────────────────────────────────────────────────

PARTNER_PRESET_TAGS = ['主力搭档', '长期搭', '友善', '谨慎', '大佬', '新人', '棘手']

@app.route('/partners')
@require_login
def partners():
    uid = session['user_id']
    rows = [dict(r) for r in get_db().execute(
        'SELECT * FROM partners WHERE user_id=? ORDER BY updated_at DESC', (uid,)
    ).fetchall()]
    all_schedules = _get_schedules(uid)
    sch_map = {s['id']: s for s in all_schedules}
    for p in rows:
        p['tags_list']        = json.loads(p['tags']) if p['tags'] else []
        p['schedule_id_list'] = json.loads(p['schedule_ids']) if p['schedule_ids'] else []
        p['linked_schedules'] = [sch_map[sid] for sid in p['schedule_id_list'] if sid in sch_map]
        p['shared_guilds_list'] = json.loads(p.get('shared_guilds') or '[]')
    owned, member = _get_my_guilds(uid)
    my_guilds = owned + member
    return render_template('partners.html', partners=rows, my_guilds=my_guilds)

@app.route('/partners/add', methods=['GET', 'POST'])
@require_login
def partner_add():
    uid = session['user_id']
    all_schedules = _get_schedules(uid)
    if request.method == 'POST':
        nickname = request.form.get('nickname', '').strip()
        sids = [int(v) for v in request.form.getlist('schedule_ids') if v.isdigit()]
        if not nickname:
            flash('❌ 昵称不能为空')
            return render_template('partner_form.html', action='add', form=request.form,
                                   all_schedules=all_schedules, preset_tags=PARTNER_PRESET_TAGS,
                                   selected_sids=set(sids))
        qq      = request.form.get('qq', '').strip()
        rating  = int(request.form.get('rating', 0) or 0)
        rating  = max(0, min(5, rating))
        notes   = request.form.get('notes', '').strip()
        tags    = [t for t in PARTNER_PRESET_TAGS if request.form.get(f'ptag_{t}')]
        custom  = request.form.get('custom_tag', '').strip()
        if custom and custom not in tags: tags.append(custom)
        ts = int(datetime.now().timestamp())
        get_db().execute(
            'INSERT INTO partners (user_id, qq, nickname, rating, tags, schedule_ids, notes, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
            (uid, qq, nickname, rating, json.dumps(tags, ensure_ascii=False),
             json.dumps(sids), notes, ts, ts))
        get_db().commit()
        flash(f'✅ 已添加 CP 档案「{nickname}」')
        return redirect(url_for('partners'))
    return render_template('partner_form.html', action='add', form={},
                           all_schedules=all_schedules, preset_tags=PARTNER_PRESET_TAGS,
                           selected_sids=set())

@app.route('/partners/<int:pid>/edit', methods=['GET', 'POST'])
@require_login
def partner_edit(pid):
    uid = session['user_id']; db = get_db()
    p = db.execute('SELECT * FROM partners WHERE id=? AND user_id=?', (pid, uid)).fetchone()
    if not p: abort(404)
    p = dict(p)
    p['tags_list']      = json.loads(p['tags']) if p['tags'] else []
    p['schedule_id_list'] = json.loads(p['schedule_ids']) if p['schedule_ids'] else []
    all_schedules = _get_schedules(uid)
    if request.method == 'POST':
        nickname = request.form.get('nickname', '').strip()
        sids = [int(v) for v in request.form.getlist('schedule_ids') if v.isdigit()]
        if not nickname:
            flash('❌ 昵称不能为空')
            return render_template('partner_form.html', action='edit', form=request.form,
                                   partner=p, all_schedules=all_schedules, preset_tags=PARTNER_PRESET_TAGS,
                                   selected_sids=set(sids))
        qq      = request.form.get('qq', '').strip()
        rating  = int(request.form.get('rating', 0) or 0)
        rating  = max(0, min(5, rating))
        notes   = request.form.get('notes', '').strip()
        tags    = [t for t in PARTNER_PRESET_TAGS if request.form.get(f'ptag_{t}')]
        custom  = request.form.get('custom_tag', '').strip()
        if custom and custom not in tags: tags.append(custom)
        db.execute(
            'UPDATE partners SET qq=?, nickname=?, rating=?, tags=?, schedule_ids=?, notes=?, updated_at=? WHERE id=? AND user_id=?',
            (qq, nickname, rating, json.dumps(tags, ensure_ascii=False), json.dumps(sids),
             notes, int(datetime.now().timestamp()), pid, uid))
        db.commit()
        flash(f'✅ 已更新 CP 档案「{nickname}」')
        return redirect(url_for('partners'))
    return render_template('partner_form.html', action='edit', form=p,
                           partner=p, all_schedules=all_schedules, preset_tags=PARTNER_PRESET_TAGS,
                           selected_sids=set(p['schedule_id_list']))

@app.route('/partners/<int:pid>/delete', methods=['POST'])
@require_login
def partner_delete(pid):
    uid = session['user_id']; db = get_db()
    p = db.execute('SELECT nickname FROM partners WHERE id=? AND user_id=?', (pid, uid)).fetchone()
    if p:
        db.execute('DELETE FROM partners WHERE id=? AND user_id=?', (pid, uid)); db.commit()
        flash(f'已删除 CP 档案「{p["nickname"]}」')
    return redirect(url_for('partners'))


# ── 日记 ────────────────────────────────────────────────────────────────────────

MOOD_OPTIONS = ['开心', '平静', '疲惫', '难过', '感动', '复杂', '满意', '不填']
MOOD_COLORS  = {
    '开心': 'var(--green)', '平静': 'var(--muted)', '疲惫': 'var(--warn)',
    '难过': 'var(--red)',   '感动': 'var(--accent2)','复杂': 'var(--gold)',
    '满意': 'var(--green)',
}

@app.template_global()
def mood_color(mood): return MOOD_COLORS.get(mood, 'var(--muted)')

@app.route('/diary')
@require_login
def diary_list():
    uid = session['user_id']
    sch_filter = request.args.get('schedule', '')
    rows = [dict(r) for r in get_db().execute(
        'SELECT * FROM diaries WHERE user_id=? ORDER BY diary_date DESC, created_at DESC', (uid,)
    ).fetchall()]
    all_schedules = _get_schedules(uid)
    sch_map = {str(s['id']): s for s in all_schedules}
    for d in rows:
        d['schedule_name'] = sch_map[str(d['schedule_id'])]['show_name'] if d['schedule_id'] and str(d['schedule_id']) in sch_map else ''
    if sch_filter:
        rows = [d for d in rows if str(d['schedule_id']) == sch_filter]
    return render_template('diary.html', diaries=rows, all_schedules=all_schedules,
                           sch_filter=sch_filter, mood_options=MOOD_OPTIONS)

@app.route('/diary/new', methods=['GET', 'POST'])
@require_login
def diary_new():
    uid = session['user_id']; db = get_db()
    all_schedules = _get_schedules(uid)
    today = date_cls.today().isoformat()
    if request.method == 'POST':
        title      = request.form.get('title', '').strip()
        content    = request.form.get('content', '').strip()
        mood       = request.form.get('mood', '')
        if mood == '不填': mood = ''
        diary_date = request.form.get('diary_date', today).strip()
        sid_str    = request.form.get('schedule_id', '').strip()
        sid        = int(sid_str) if sid_str and sid_str.isdigit() else None
        ts = int(datetime.now().timestamp())
        db.execute(
            'INSERT INTO diaries (user_id, title, content, mood, schedule_id, diary_date, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)',
            (uid, title, content, mood, sid, diary_date, ts, ts))
        db.commit()
        flash('✅ 日记已保存')
        return redirect(url_for('diary_list'))
    return render_template('diary_form.html', action='new', form={'diary_date': today},
                           all_schedules=all_schedules, mood_options=MOOD_OPTIONS, today=today)

@app.route('/diary/<int:did>/edit', methods=['GET', 'POST'])
@require_login
def diary_edit(did):
    uid = session['user_id']; db = get_db()
    d = db.execute('SELECT * FROM diaries WHERE id=? AND user_id=?', (did, uid)).fetchone()
    if not d: abort(404)
    d = dict(d)
    all_schedules = _get_schedules(uid)
    today = date_cls.today().isoformat()
    if request.method == 'POST':
        title      = request.form.get('title', '').strip()
        content    = request.form.get('content', '').strip()
        mood       = request.form.get('mood', '')
        if mood == '不填': mood = ''
        diary_date = request.form.get('diary_date', today).strip()
        sid_str    = request.form.get('schedule_id', '').strip()
        sid        = int(sid_str) if sid_str and sid_str.isdigit() else None
        db.execute(
            'UPDATE diaries SET title=?, content=?, mood=?, schedule_id=?, diary_date=?, updated_at=? WHERE id=? AND user_id=?',
            (title, content, mood, sid, diary_date, int(datetime.now().timestamp()), did, uid))
        db.commit()
        flash('✅ 日记已更新')
        return redirect(url_for('diary_list'))
    return render_template('diary_form.html', action='edit', form=d,
                           all_schedules=all_schedules, mood_options=MOOD_OPTIONS, today=today)

@app.route('/diary/<int:did>/delete', methods=['POST'])
@require_login
def diary_delete(did):
    uid = session['user_id']; db = get_db()
    d = db.execute('SELECT title, diary_date FROM diaries WHERE id=? AND user_id=?', (did, uid)).fetchone()
    if d:
        db.execute('DELETE FROM diaries WHERE id=? AND user_id=?', (did, uid)); db.commit()
        flash(f'已删除日记「{d["title"] or d["diary_date"]}」')
    return redirect(url_for('diary_list'))


# ── 心愿单 ───────────────────────────────────────────────────────────────────────

WISH_TYPES = ['皮相', '题材', '其他']

@app.route('/wishlist')
@require_login
def wishlist():
    uid = session['user_id']
    wtype_filter = request.args.get('type', '')
    rows = [dict(r) for r in get_db().execute(
        'SELECT * FROM wishlist WHERE user_id=? ORDER BY is_done ASC, created_at DESC', (uid,)
    ).fetchall()]
    counts = {wt: sum(1 for r in rows if r['wtype'] == wt) for wt in WISH_TYPES}
    total  = len(rows)
    done   = sum(1 for r in rows if r['is_done'])
    if wtype_filter and wtype_filter in WISH_TYPES:
        rows = [r for r in rows if r['wtype'] == wtype_filter]
    return render_template('wishlist.html', items=rows, wish_types=WISH_TYPES,
                           wtype_filter=wtype_filter, counts=counts, total=total, done=done)

@app.route('/wishlist/add', methods=['POST'])
@require_login
def wishlist_add():
    uid     = session['user_id']
    wtype   = request.form.get('wtype', '题材').strip()
    content = request.form.get('content', '').strip()
    notes   = request.form.get('notes', '').strip()
    if not content:
        flash('❌ 内容不能为空')
        return redirect(url_for('wishlist'))
    if wtype not in WISH_TYPES: wtype = '题材'
    get_db().execute(
        'INSERT INTO wishlist (user_id, wtype, content, notes, is_done, created_at) VALUES (?,?,?,?,0,?)',
        (uid, wtype, content, notes, int(datetime.now().timestamp())))
    get_db().commit()
    flash('✅ 已添加到心愿单')
    return redirect(url_for('wishlist'))

@app.route('/wishlist/<int:wid>/toggle', methods=['POST'])
@require_login
def wishlist_toggle(wid):
    uid = session['user_id']; db = get_db()
    item = db.execute('SELECT is_done FROM wishlist WHERE id=? AND user_id=?', (wid, uid)).fetchone()
    if item:
        db.execute('UPDATE wishlist SET is_done=? WHERE id=? AND user_id=?',
                   (0 if item['is_done'] else 1, wid, uid))
        db.commit()
    return redirect(url_for('wishlist'))

@app.route('/wishlist/<int:wid>/delete', methods=['POST'])
@require_login
def wishlist_delete(wid):
    uid = session['user_id']; db = get_db()
    item = db.execute('SELECT content FROM wishlist WHERE id=? AND user_id=?', (wid, uid)).fetchone()
    if item:
        db.execute('DELETE FROM wishlist WHERE id=? AND user_id=?', (wid, uid)); db.commit()
        flash(f'已删除「{item["content"][:20]}」')
    return redirect(url_for('wishlist'))


# ── 卡包 ─────────────────────────────────────────────────────────────────────────

def _card_days_left(expiry_str):
    try:
        return (date_cls.fromisoformat(expiry_str) - date_cls.today()).days
    except Exception:
        return 999

@app.route('/cards')
@require_login
def cards():
    uid = session['user_id']
    type_filter = request.args.get('type', '')
    rows = [dict(r) for r in get_db().execute(
        'SELECT * FROM cards WHERE user_id=? ORDER BY expiry ASC, created_at ASC', (uid,)
    ).fetchall()]
    for c in rows:
        c['days_left'] = _card_days_left(c['expiry'])
        if c['last_consume']:
            dt = datetime.fromtimestamp(c['last_consume'])
            c['last_consume_str'] = f"{dt.month}/{dt.day} {dt.hour}:{dt.minute:02d}"
        else:
            c['last_consume_str'] = ''
    counts = {t: sum(1 for r in rows if r['card_type'] == t) for t in CARD_TYPES}
    urgent = sum(1 for r in rows if 0 <= r['days_left'] <= 7)
    if type_filter and type_filter in CARD_TYPES:
        display = [r for r in rows if r['card_type'] == type_filter]
    else:
        type_filter = ''
        display = rows
    return render_template('cards.html', cards=display, all_cards=rows,
                           card_types=CARD_TYPES, type_filter=type_filter,
                           counts=counts, urgent=urgent)

@app.route('/cards/add', methods=['POST'])
@require_login
def cards_add():
    uid = session['user_id']
    name      = request.form.get('name', '').strip()
    expiry    = request.form.get('expiry', '').strip()
    quantity  = request.form.get('quantity', '1').strip()
    price     = request.form.get('price', '0').strip()
    card_type = request.form.get('card_type', '其他').strip()
    notes     = request.form.get('notes', '').strip()
    if not name or not expiry:
        flash('❌ 名称和到期日不能为空')
        return redirect(url_for('cards'))
    if card_type not in CARD_TYPES:
        card_type = '其他'
    try:
        date_cls.fromisoformat(expiry)
    except ValueError:
        flash('❌ 日期格式不正确，请使用 YYYY-MM-DD')
        return redirect(url_for('cards'))
    try: quantity = max(0, int(quantity))
    except (ValueError, TypeError): quantity = 1
    try: price = max(0.0, float(price))
    except (ValueError, TypeError): price = 0.0
    now = int(datetime.now().timestamp())
    get_db().execute(
        'INSERT INTO cards (user_id, name, expiry, quantity, price, card_type, notes, created_at, updated_at) '
        'VALUES (?,?,?,?,?,?,?,?,?)',
        (uid, name, expiry, quantity, price, card_type, notes, now, now))
    get_db().commit()
    flash(f'✅ 已录入「{name}」')
    return redirect(url_for('cards'))

@app.route('/cards/<int:cid>/edit', methods=['POST'])
@require_login
def cards_edit(cid):
    uid = session['user_id']; db = get_db()
    card = db.execute('SELECT id FROM cards WHERE id=? AND user_id=?', (cid, uid)).fetchone()
    if not card:
        flash('❌ 卡片不存在')
        return redirect(url_for('cards'))
    name      = request.form.get('name', '').strip()
    expiry    = request.form.get('expiry', '').strip()
    quantity  = request.form.get('quantity', '1').strip()
    price     = request.form.get('price', '0').strip()
    card_type = request.form.get('card_type', '其他').strip()
    notes     = request.form.get('notes', '').strip()
    if not name or not expiry:
        flash('❌ 名称和到期日不能为空')
        return redirect(url_for('cards'))
    if card_type not in CARD_TYPES:
        card_type = '其他'
    try:
        date_cls.fromisoformat(expiry)
    except ValueError:
        flash('❌ 日期格式不正确')
        return redirect(url_for('cards'))
    try: quantity = max(0, int(quantity))
    except (ValueError, TypeError): quantity = 1
    try: price = max(0.0, float(price))
    except (ValueError, TypeError): price = 0.0
    now = int(datetime.now().timestamp())
    db.execute(
        'UPDATE cards SET name=?, expiry=?, quantity=?, price=?, card_type=?, notes=?, updated_at=? '
        'WHERE id=? AND user_id=?',
        (name, expiry, quantity, price, card_type, notes, now, cid, uid))
    db.commit()
    flash(f'✅ 已更新「{name}」')
    return redirect(url_for('cards'))

@app.route('/cards/<int:cid>/consume', methods=['POST'])
@require_login
def cards_consume(cid):
    uid = session['user_id']; db = get_db()
    try: count = max(1, int(request.form.get('count', '1') or '1'))
    except (ValueError, TypeError): count = 1
    card = db.execute('SELECT * FROM cards WHERE id=? AND user_id=?', (cid, uid)).fetchone()
    if not card:
        flash('❌ 卡片不存在')
        return redirect(url_for('cards'))
    new_qty = max(0, card['quantity'] - count)
    now = int(datetime.now().timestamp())
    db.execute('UPDATE cards SET quantity=?, last_consume=?, updated_at=? WHERE id=? AND user_id=?',
               (new_qty, now, now, cid, uid))
    db.commit()
    flash(f'📉 「{card["name"]}」消耗 {count}，剩余 {new_qty}')
    return redirect(url_for('cards'))

@app.route('/cards/<int:cid>/delete', methods=['POST'])
@require_login
def cards_delete(cid):
    uid = session['user_id']; db = get_db()
    card = db.execute('SELECT name FROM cards WHERE id=? AND user_id=?', (cid, uid)).fetchone()
    if card:
        db.execute('DELETE FROM cards WHERE id=? AND user_id=?', (cid, uid))
        db.commit()
        flash(f'🗑️ 已删除「{card["name"]}」')
    return redirect(url_for('cards'))

@app.route('/cards/clean', methods=['POST'])
@require_login
def cards_clean():
    uid = session['user_id']; db = get_db()
    today = date_cls.today().isoformat()
    expired = db.execute(
        "SELECT name FROM cards WHERE user_id=? AND expiry < ?", (uid, today)
    ).fetchall()
    if expired:
        db.execute("DELETE FROM cards WHERE user_id=? AND expiry < ?", (uid, today))
        db.commit()
        flash(f'🗑️ 已清理 {len(expired)} 张过期卡片')
    else:
        flash('✅ 没有过期卡片，卡包干净~')
    return redirect(url_for('cards'))

@app.route('/cards/random')
@require_login
def cards_random():
    import random as _random
    uid = session['user_id']
    type_filter = request.args.get('type', '')
    today = date_cls.today().isoformat()
    db = get_db()
    q = "SELECT * FROM cards WHERE user_id=? AND expiry >= ? AND quantity > 0"
    params = [uid, today]
    if type_filter and type_filter in CARD_TYPES:
        q += " AND card_type=?"
        params.append(type_filter)
    rows = db.execute(q, params).fetchall()
    if not rows:
        return jsonify({'ok': False, 'msg': '没有可用的卡片（试试去掉类型筛选）'})
    card = dict(_random.choice(rows))
    card['days_left'] = _card_days_left(card['expiry'])
    return jsonify({'ok': True, 'card': card})


# ── 时间轴 ───────────────────────────────────────────────────────────────────────

@app.route('/timeline')
@require_login
def timeline():
    from calendar import isleap
    uid = session['user_id']
    all_schedules = _get_schedules(uid)
    tdata = timeline_data(all_schedules)
    now = datetime.now()
    yr = now.year
    today_pct = round((date_cls(yr, now.month, now.day) - date_cls(yr, 1, 1)).days
                      / (366 if isleap(yr) else 365) * 100, 2)
    return render_template('timeline.html', timeline_years=tdata,
                           now_year=yr, today_pct=today_pct)


# ── 公会 ────────────────────────────────────────────────────────────────────────

def _guild_member_schedules(uid):
    """Return public schedules for a user (for guild calendar display)."""
    rows = [dict(r) for r in get_db().execute(
        "SELECT * FROM schedules WHERE user_id=? AND visibility='public' ORDER BY start_year, time_range", (uid,)
    ).fetchall()]
    return _enrich_schedules(rows)

def _get_my_guilds(uid):
    """Return (owned, member) guild lists for a user."""
    db = get_db()
    owned = [dict(r) for r in db.execute(
        'SELECT g.* FROM guilds g WHERE g.owner_id=? ORDER BY g.created_at DESC', (uid,)
    ).fetchall()]
    member = [dict(r) for r in db.execute(
        '''SELECT g.*, gm.status FROM guilds g
           JOIN guild_memberships gm ON gm.guild_id=g.id
           WHERE gm.user_id=? AND gm.status='approved' ORDER BY gm.approved_at DESC''', (uid,)
    ).fetchall()]
    return owned, member

def _guild_approved_uids(gid):
    rows = get_db().execute(
        "SELECT user_id FROM guild_memberships WHERE guild_id=? AND status='approved'", (gid,)
    ).fetchall()
    return [r['user_id'] for r in rows]

def _user_approved_guild_ids(uid):
    db = get_db()
    member_ids = [r['guild_id'] for r in db.execute(
        "SELECT guild_id FROM guild_memberships WHERE user_id=? AND status='approved'", (uid,)
    ).fetchall()]
    owned_ids = [r['id'] for r in db.execute(
        "SELECT id FROM guilds WHERE owner_id=?", (uid,)
    ).fetchall()]
    return list(set(member_ids + owned_ids))

@app.route('/guilds')
@require_login
def guilds():
    uid = session['user_id']
    owned, member = _get_my_guilds(uid)
    db = get_db()
    # pending requests on my owned guilds
    pending_counts = {}
    for g in owned:
        cnt = db.execute(
            "SELECT COUNT(*) FROM guild_memberships WHERE guild_id=? AND status='pending'", (g['id'],)
        ).fetchone()[0]
        pending_counts[g['id']] = cnt
    # my pending join requests
    my_pending = [dict(r) for r in db.execute(
        '''SELECT g.name, g.slug, gm.created_at FROM guilds g
           JOIN guild_memberships gm ON gm.guild_id=g.id
           WHERE gm.user_id=? AND gm.status='pending' ORDER BY gm.created_at DESC''', (uid,)
    ).fetchall()]
    return render_template('guilds.html', owned=owned, member=member,
                           pending_counts=pending_counts, my_pending=my_pending)

@app.route('/guilds/create', methods=['POST'])
@require_login
def guild_create():
    uid = session['user_id']
    name = request.form.get('name', '').strip()
    slug = request.form.get('slug', '').strip().lower()
    sig  = request.form.get('signature', '').strip()
    if not name:
        flash('❌ 公会名不能为空'); return redirect(url_for('guilds'))
    if not slug or not re.match(r'^[a-z0-9_-]{2,30}$', slug):
        flash('❌ 公会 ID 只能含小写字母/数字/下划线/连字符，长度 2-30'); return redirect(url_for('guilds'))
    db = get_db()
    if db.execute('SELECT id FROM guilds WHERE slug=?', (slug,)).fetchone():
        flash(f'❌ 公会 ID「{slug}」已被使用'); return redirect(url_for('guilds'))
    ts = int(datetime.now().timestamp())
    gid = db.execute(
        'INSERT INTO guilds (name, slug, signature, owner_id, created_at) VALUES (?,?,?,?,?)',
        (name, slug, sig, uid, ts)
    ).lastrowid
    db.commit()
    flash(f'✅ 公会「{name}」已创建')
    return redirect(url_for('guild_detail', gid=gid))

@app.route('/guilds/discover')
@require_login
def guild_discover():
    uid = session['user_id']
    q = request.args.get('q', '').strip()
    db = get_db()
    if q:
        guilds_list = [dict(r) for r in db.execute(
            "SELECT g.*, u.display_name AS owner_name FROM guilds g JOIN users u ON u.id=g.owner_id WHERE g.name LIKE ? OR g.slug LIKE ? ORDER BY g.created_at DESC",
            (f'%{q}%', f'%{q}%')
        ).fetchall()]
    else:
        guilds_list = [dict(r) for r in db.execute(
            "SELECT g.*, u.display_name AS owner_name FROM guilds g JOIN users u ON u.id=g.owner_id ORDER BY g.created_at DESC"
        ).fetchall()]
    my_guild_ids = set()
    for r in db.execute(
        "SELECT guild_id FROM guild_memberships WHERE user_id=?", (uid,)
    ).fetchall():
        my_guild_ids.add(r['guild_id'])
    owned_ids = {r['id'] for r in db.execute('SELECT id FROM guilds WHERE owner_id=?', (uid,)).fetchall()}
    for g in guilds_list:
        g['is_owner']  = g['id'] in owned_ids
        g['my_status'] = None
        if g['id'] in my_guild_ids:
            row = db.execute("SELECT status FROM guild_memberships WHERE guild_id=? AND user_id=?",
                             (g['id'], uid)).fetchone()
            g['my_status'] = row['status'] if row else None
        cnt = db.execute("SELECT COUNT(*) FROM guild_memberships WHERE guild_id=? AND status='approved'",
                         (g['id'],)).fetchone()[0]
        g['member_count'] = cnt
    return render_template('guild_discover.html', guilds=guilds_list, q=q)

@app.route('/guilds/<int:gid>')
@require_login
def guild_detail(gid):
    uid = session['user_id']
    db  = get_db()
    g = db.execute('SELECT * FROM guilds WHERE id=?', (gid,)).fetchone()
    if not g: abort(404)
    g = dict(g)
    is_owner = (g['owner_id'] == uid)
    my_mem = db.execute("SELECT status FROM guild_memberships WHERE guild_id=? AND user_id=?",
                        (gid, uid)).fetchone()
    is_member = my_mem and my_mem['status'] == 'approved'
    if not is_owner and not is_member:
        flash('❌ 你不是该公会成员'); return redirect(url_for('guild_discover'))

    # members (approved memberships)
    members = [dict(r) for r in db.execute(
        '''SELECT u.id, u.display_name, u.username, gm.approved_at
           FROM guild_memberships gm JOIN users u ON u.id=gm.user_id
           WHERE gm.guild_id=? AND gm.status='approved' ORDER BY gm.approved_at''', (gid,)
    ).fetchall()]
    # ensure owner is always in members list
    if not any(m['id'] == g['owner_id'] for m in members):
        owner_user = db.execute('SELECT id, display_name, username FROM users WHERE id=?', (g['owner_id'],)).fetchone()
        if owner_user:
            members.insert(0, {'id': owner_user['id'], 'display_name': owner_user['display_name'],
                                'username': owner_user['username'], 'approved_at': g['created_at']})
    pending = []
    if is_owner:
        pending = [dict(r) for r in db.execute(
            '''SELECT u.id, u.display_name, u.username, gm.created_at
               FROM guild_memberships gm JOIN users u ON u.id=gm.user_id
               WHERE gm.guild_id=? AND gm.status='pending' ORDER BY gm.created_at''', (gid,)
        ).fetchall()]

    member_uids = [m['id'] for m in members]
    owner_row = db.execute('SELECT display_name, username FROM users WHERE id=?', (g['owner_id'],)).fetchone()
    g['owner_name'] = owner_row['display_name'] or owner_row['username'] if owner_row else '未知'

    # tab
    tab = request.args.get('tab', 'calendar')
    tab_year = request.args.get('year', str(datetime.now().year))
    try: tab_year = int(tab_year)
    except: tab_year = datetime.now().year

    now = datetime.now()
    try: cal_year  = int(request.args.get('cal_year',  now.year))
    except: cal_year  = now.year
    try: cal_month = int(request.args.get('cal_month', now.month))
    except: cal_month = now.month
    cal_month = max(1, min(12, cal_month))

    # guild calendar: all members' public schedules grouped by user
    MEMBER_COLORS = ['#8b7cf6','#f472b6','#34d399','#60a5fa','#fbbf24',
                     '#f87171','#a78bfa','#2dd4bf','#fb923c','#e879f9']
    member_schedules = {}
    for m in members:
        member_schedules[m['id']] = {
            'user': m,
            'schedules': _guild_member_schedules(m['id'])
        }

    # month grid for calendar tab
    guild_cal_grid = None
    guild_cal_legend = []
    cal_prev_year, cal_prev_month = (cal_year, cal_month - 1) if cal_month > 1 else (cal_year - 1, 12)
    cal_next_year, cal_next_month = (cal_year, cal_month + 1) if cal_month < 12 else (cal_year + 1, 1)
    if tab == 'calendar':
        days_in = monthrange(cal_year, cal_month)[1]
        first_wd = (date_cls(cal_year, cal_month, 1).weekday() + 1) % 7
        # per-member day coverage
        member_day_data = []
        for i, m in enumerate(members):
            color = MEMBER_COLORS[i % len(MEMBER_COLORS)]
            schs = member_schedules[m['id']]['schedules']
            day_shows_m, _, _ = schedules_for_month(schs, cal_year, cal_month)
            member_day_data.append({'color': color, 'name': m['display_name'] or m['username'], 'day_shows': day_shows_m})
            guild_cal_legend.append({'color': color, 'name': m['display_name'] or m['username']})
        # build grid rows
        cells = [None] * first_wd + list(range(1, days_in + 1))
        cells += [None] * ((7 - len(cells) % 7) % 7)
        rows = [cells[i:i+7] for i in range(0, len(cells), 7)]
        guild_cal_grid = {'rows': rows, 'days_in': days_in, 'member_day_data': member_day_data}

    # shared 必吃榜
    shared_partners = []
    if tab == 'partners':
        for mid in member_uids:
            rows = [dict(r) for r in db.execute(
                "SELECT p.*, u.display_name AS owner_name FROM partners p JOIN users u ON u.id=p.user_id WHERE p.user_id=?", (mid,)
            ).fetchall()]
            for p in rows:
                sg = json.loads(p.get('shared_guilds') or '[]')
                if gid in sg:
                    p['tags_list'] = json.loads(p['tags']) if p['tags'] else []
                    shared_partners.append(p)

    # shared 黑名单
    shared_blacklist = []
    if tab == 'blacklist':
        for mid in member_uids:
            rows = [dict(r) for r in db.execute(
                "SELECT b.*, u.display_name AS owner_name FROM blacklist b JOIN users u ON u.id=b.user_id WHERE b.user_id=?", (mid,)
            ).fetchall()]
            for b in rows:
                sg = json.loads(b.get('shared_guilds') or '[]')
                if gid in sg:
                    shared_blacklist.append(b)

    # 年度统计 per member
    member_stats = []
    if tab == 'stats':
        for m in members:
            schs = _guild_member_schedules(m['id'])
            st = annual_stats(schs, tab_year)
            st['user'] = m
            member_stats.append(st)

    return render_template('guild_detail.html',
        guild=g, is_owner=is_owner, members=members, pending=pending,
        member_schedules=member_schedules,
        shared_partners=shared_partners, shared_blacklist=shared_blacklist,
        member_stats=member_stats, tab=tab, tab_year=tab_year,
        guild_cal_grid=guild_cal_grid, guild_cal_legend=guild_cal_legend,
        cal_year=cal_year, cal_month=cal_month,
        cal_prev_year=cal_prev_year, cal_prev_month=cal_prev_month,
        cal_next_year=cal_next_year, cal_next_month=cal_next_month,
        now_year=datetime.now().year)

@app.route('/guilds/<int:gid>/join', methods=['POST'])
@require_login
def guild_join(gid):
    uid = session['user_id']
    db  = get_db()
    g = db.execute('SELECT id, name, owner_id FROM guilds WHERE id=?', (gid,)).fetchone()
    if not g: abort(404)
    if g['owner_id'] == uid:
        flash('❌ 你是公会创建者'); return redirect(url_for('guild_detail', gid=gid))
    existing = db.execute("SELECT status FROM guild_memberships WHERE guild_id=? AND user_id=?", (gid, uid)).fetchone()
    if existing:
        flash('❌ 你已申请或加入该公会'); return redirect(url_for('guild_discover'))
    db.execute("INSERT INTO guild_memberships (guild_id, user_id, status, created_at) VALUES (?,?,'pending',?)",
               (gid, uid, int(datetime.now().timestamp())))
    db.commit()
    flash(f'✅ 已发送加入申请，等待「{g["name"]}」公会主审核')
    return redirect(url_for('guild_discover'))

@app.route('/guilds/<int:gid>/approve/<int:target_uid>', methods=['POST'])
@require_login
def guild_approve(gid, target_uid):
    uid = session['user_id']
    db  = get_db()
    g = db.execute('SELECT owner_id FROM guilds WHERE id=?', (gid,)).fetchone()
    if not g or g['owner_id'] != uid: abort(403)
    ts = int(datetime.now().timestamp())
    db.execute("UPDATE guild_memberships SET status='approved', approved_at=? WHERE guild_id=? AND user_id=? AND status='pending'",
               (ts, gid, target_uid))
    db.commit()
    flash('✅ 已通过申请')
    return redirect(url_for('guild_detail', gid=gid))

@app.route('/guilds/<int:gid>/reject/<int:target_uid>', methods=['POST'])
@require_login
def guild_reject(gid, target_uid):
    uid = session['user_id']
    db  = get_db()
    g = db.execute('SELECT owner_id FROM guilds WHERE id=?', (gid,)).fetchone()
    if not g or g['owner_id'] != uid: abort(403)
    db.execute("DELETE FROM guild_memberships WHERE guild_id=? AND user_id=? AND status='pending'",
               (gid, target_uid))
    db.commit()
    flash('已拒绝申请')
    return redirect(url_for('guild_detail', gid=gid))

@app.route('/guilds/<int:gid>/kick/<int:target_uid>', methods=['POST'])
@require_login
def guild_kick(gid, target_uid):
    uid = session['user_id']
    db  = get_db()
    g = db.execute('SELECT owner_id FROM guilds WHERE id=?', (gid,)).fetchone()
    if not g or g['owner_id'] != uid: abort(403)
    db.execute("DELETE FROM guild_memberships WHERE guild_id=? AND user_id=?", (gid, target_uid))
    db.commit()
    flash('已移出成员')
    return redirect(url_for('guild_detail', gid=gid))

@app.route('/guilds/<int:gid>/leave', methods=['POST'])
@require_login
def guild_leave(gid):
    uid = session['user_id']
    db  = get_db()
    g = db.execute('SELECT owner_id, name FROM guilds WHERE id=?', (gid,)).fetchone()
    if not g: abort(404)
    if g['owner_id'] == uid:
        flash('❌ 公会主不能退出，请先解散公会'); return redirect(url_for('guild_detail', gid=gid))
    db.execute("DELETE FROM guild_memberships WHERE guild_id=? AND user_id=?", (gid, uid))
    db.commit()
    flash(f'已退出公会「{g["name"]}」')
    return redirect(url_for('guilds'))

@app.route('/guilds/<int:gid>/edit', methods=['GET', 'POST'])
@require_login
def guild_edit(gid):
    uid = session['user_id']
    db  = get_db()
    g = db.execute('SELECT * FROM guilds WHERE id=? AND owner_id=?', (gid, uid)).fetchone()
    if not g: abort(403)
    g = dict(g)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        sig  = request.form.get('signature', '').strip()
        if not name:
            flash('❌ 公会名不能为空')
            return render_template('guild_edit.html', guild=g)
        db.execute('UPDATE guilds SET name=?, signature=? WHERE id=?', (name, sig, gid))
        db.commit()
        flash('✅ 公会信息已更新')
        return redirect(url_for('guild_detail', gid=gid))
    return render_template('guild_edit.html', guild=g)

@app.route('/guilds/<int:gid>/delete', methods=['POST'])
@require_login
def guild_delete(gid):
    uid = session['user_id']
    db  = get_db()
    g = db.execute('SELECT name FROM guilds WHERE id=? AND owner_id=?', (gid, uid)).fetchone()
    if not g: abort(403)
    db.execute('DELETE FROM guild_memberships WHERE guild_id=?', (gid,))
    db.execute('DELETE FROM guilds WHERE id=?', (gid,))
    db.commit()
    flash(f'已解散公会「{g["name"]}」')
    return redirect(url_for('guilds'))

@app.route('/api/partners/<int:pid>/guild-share', methods=['POST'])
@require_login
def api_partner_guild_share(pid):
    uid = session['user_id']
    db  = get_db()
    p = db.execute('SELECT id FROM partners WHERE id=? AND user_id=?', (pid, uid)).fetchone()
    if not p: return jsonify({'ok': False}), 404
    guild_ids = [int(x) for x in request.json.get('guild_ids', []) if str(x).isdigit()]
    # only allow guilds the user is actually a member of
    allowed = set(_user_approved_guild_ids(uid))
    guild_ids = [g for g in guild_ids if g in allowed]
    db.execute('UPDATE partners SET shared_guilds=? WHERE id=?',
               (json.dumps(guild_ids), pid))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/blacklist/<int:bid>/guild-share', methods=['POST'])
@require_login
def api_blacklist_guild_share(bid):
    uid = session['user_id']
    db  = get_db()
    b = db.execute('SELECT id FROM blacklist WHERE id=? AND user_id=?', (bid, uid)).fetchone()
    if not b: return jsonify({'ok': False}), 404
    guild_ids = [int(x) for x in request.json.get('guild_ids', []) if str(x).isdigit()]
    allowed = set(_user_approved_guild_ids(uid))
    guild_ids = [g for g in guild_ids if g in allowed]
    db.execute('UPDATE blacklist SET shared_guilds=? WHERE id=?',
               (json.dumps(guild_ids), bid))
    db.commit()
    return jsonify({'ok': True})


# ── Mobile API v1 ───────────────────────────────────────────────────────────────
#
#  所有接口以 /api/v1/ 开头，使用随机 Token 认证（存储在数据库中）。
#  现有的 session-based 网页路由完全不受影响。
#

API_TOKEN_EXPIRE_DAYS = 30


def _make_api_token(user_id):
    """生成随机 token 并存入数据库"""
    token = secrets.token_urlsafe(32)
    now   = int(datetime.now().timestamp())
    exp   = now + API_TOKEN_EXPIRE_DAYS * 86400
    db    = get_db()
    db.execute(
        "INSERT INTO api_tokens (user_id, token, expires_at, created_at) VALUES (?,?,?,?)",
        (user_id, token, exp, now)
    )
    db.commit()
    return token


def _require_token(f):
    """API 路由的认证装饰器，从 Authorization: Bearer <token> 中查找用户"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"ok": False, "error": "未登录"}), 401
        token = auth_header[7:].strip()
        now   = int(datetime.now().timestamp())
        db    = get_db()
        row   = db.execute(
            """SELECT t.user_id, u.username, u.display_name
               FROM api_tokens t JOIN users u ON u.id = t.user_id
               WHERE t.token = ? AND t.expires_at > ? AND u.is_active = 1""",
            (token, now)
        ).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "token 无效或已过期"}), 401
        g.api_uid          = row["user_id"]
        g.api_username     = row["username"]
        g.api_display_name = row["display_name"]
        return f(*args, **kwargs)
    return decorated


# ── 认证 ────────────────────────────────────────────────────────────────────────

@app.route("/api/v1/login", methods=["POST"])
def api_login():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"ok": False, "error": "用户名和密码不能为空"}), 400
    user = get_db().execute(
        "SELECT * FROM users WHERE username=? AND is_active=1", (username,)
    ).fetchone()
    if not user:
        return jsonify({"ok": False, "error": "用户名不存在"}), 401
    if not check_password_hash(user["password_hash"], password):
        return jsonify({"ok": False, "error": "密码错误"}), 401
    token = _make_api_token(user["id"])
    return jsonify({
        "ok": True,
        "token": token,
        "user": {
            "id":           user["id"],
            "username":     user["username"],
            "display_name": user["display_name"] or user["username"],
            "theme":        user["theme"],
        }
    })


@app.route("/api/v1/me")
@_require_token
def api_me():
    db   = get_db()
    user = db.execute(
        "SELECT id, username, display_name, theme FROM users WHERE id=?", (g.api_uid,)
    ).fetchone()
    if not user:
        return jsonify({"ok": False, "error": "用户不存在"}), 404
    cnt  = db.execute(
        "SELECT COUNT(*) FROM reports WHERE submitter_user_id=? AND status='approved'",
        (g.api_uid,)
    ).fetchone()[0]
    u = dict(user)
    u['is_vip']               = cnt >= VIP_THRESHOLD
    u['unlocked_achievements'] = list(_get_unlocked_achievements(db, g.api_uid))
    return jsonify({"ok": True, "user": u})


@app.route("/api/v1/theme", methods=["POST"])
@_require_token
def api_set_theme_v1():
    data  = request.get_json(silent=True) or {}
    theme = data.get("theme", "").strip()
    db    = get_db()
    cnt   = db.execute(
        "SELECT COUNT(*) FROM reports WHERE submitter_user_id=? AND status='approved'",
        (g.api_uid,)
    ).fetchone()[0]
    is_vip = cnt >= VIP_THRESHOLD
    if theme in VIP_THEMES and not is_vip:
        return jsonify({"ok": False, "error": "vip_required"}), 403
    if theme in ACHIEVEMENT_THEMES and theme not in _get_unlocked_achievements(db, g.api_uid):
        return jsonify({"ok": False, "error": "achievement_locked"}), 403
    db.execute("UPDATE users SET theme=? WHERE id=?", (theme, g.api_uid))
    db.commit()
    return jsonify({"ok": True, "theme": theme})


# ── 日程 ────────────────────────────────────────────────────────────────────────

@app.route("/api/v1/schedules")
@_require_token
def api_schedules_list():
    rows = get_db().execute(
        "SELECT * FROM schedules WHERE user_id=? ORDER BY start_year DESC, created_at DESC",
        (g.api_uid,)
    ).fetchall()
    return jsonify({"ok": True, "schedules": [dict(r) for r in rows]})


@app.route("/api/v1/schedules/<int:sid>")
@_require_token
def api_schedule_get(sid):
    row = get_db().execute(
        "SELECT * FROM schedules WHERE id=? AND user_id=?", (sid, g.api_uid)
    ).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "不存在"}), 404
    return jsonify({"ok": True, "schedule": dict(row)})


@app.route("/api/v1/schedules", methods=["POST"])
@_require_token
def api_schedule_add():
    data   = request.get_json(silent=True) or {}
    errors, show_name, time_range, sy = _validate_schedule_form(data)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    fields = _save_schedule_fields(data)
    ts  = int(datetime.now().timestamp())
    db  = get_db()
    visibility = 'private' if data.get('visibility') == 'private' else 'public'
    cur = db.execute(
        """INSERT INTO schedules
           (user_id, show_name, start_year, time_range, status, character, orientation,
            theme, role_name, role_type, gender, outcome, color, notes,
            deadline_form2, deadline_public, deadline_relation,
            schedule_tags, casting_status, visibility, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (g.api_uid, show_name, sy, time_range,
         fields["status"], fields["character"], fields["orientation"], fields["theme"],
         fields["role_name"], fields["role_type"], fields["gender"], fields["outcome"],
         fields["color"], fields["notes"],
         fields.get("deadline_form2",""), fields.get("deadline_public",""),
         fields.get("deadline_relation",""),
         fields.get("schedule_tags","[]"), fields.get("casting_status",""),
         visibility, ts, ts)
    )
    db.commit()
    row = db.execute("SELECT * FROM schedules WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify({"ok": True, "schedule": dict(row)}), 201


@app.route("/api/v1/schedules/<int:sid>", methods=["PUT"])
@_require_token
def api_schedule_edit(sid):
    db  = get_db()
    row = db.execute("SELECT id FROM schedules WHERE id=? AND user_id=?",
                     (sid, g.api_uid)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "不存在"}), 404
    data   = request.get_json(silent=True) or {}
    errors, show_name, time_range, sy = _validate_schedule_form(data)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    fields = _save_schedule_fields(data)
    ts  = int(datetime.now().timestamp())
    visibility = 'private' if data.get('visibility') == 'private' else 'public'
    db.execute(
        """UPDATE schedules SET
           show_name=?, start_year=?, time_range=?, status=?, character=?,
           orientation=?, theme=?, role_name=?, role_type=?, gender=?, outcome=?,
           color=?, notes=?, deadline_form2=?, deadline_public=?, deadline_relation=?,
           schedule_tags=?, casting_status=?, visibility=?, updated_at=?
           WHERE id=? AND user_id=?""",
        (show_name, sy, time_range,
         fields["status"], fields["character"], fields["orientation"], fields["theme"],
         fields["role_name"], fields["role_type"], fields["gender"], fields["outcome"],
         fields["color"], fields["notes"],
         fields.get("deadline_form2",""), fields.get("deadline_public",""),
         fields.get("deadline_relation",""),
         fields.get("schedule_tags","[]"), fields.get("casting_status",""),
         visibility, ts, sid, g.api_uid)
    )
    db.commit()
    updated = db.execute("SELECT * FROM schedules WHERE id=?", (sid,)).fetchone()
    return jsonify({"ok": True, "schedule": dict(updated)})


@app.route("/api/v1/schedules/<int:sid>", methods=["DELETE"])
@_require_token
def api_schedule_delete(sid):
    db = get_db()
    row = db.execute("SELECT id FROM schedules WHERE id=? AND user_id=?", (sid, g.api_uid)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "不存在"}), 404
    db.execute("DELETE FROM schedules WHERE id=?", (sid,))
    db.commit()
    return jsonify({"ok": True})


# ── 日历视图 ─────────────────────────────────────────────────────────────────────

@app.route("/api/v1/calendar")
@_require_token
def api_calendar():
    now = datetime.now()
    try:
        year  = int(request.args.get("year",  now.year))
        month = int(request.args.get("month", now.month))
    except (ValueError, TypeError):
        year, month = now.year, now.month

    # 从数据库获取日程，全部转为 dict（sqlite3.Row 不能直接 JSON 序列化）
    raw = _get_schedules(g.api_uid)
    schedules = [dict(s) for s in raw]

    # 冲突检测
    conflict_ids = list(find_all_conflicts(schedules))

    # 本月日程：schedules_for_month 返回 (day_shows, active, days_in)
    day_shows, active, days_in = schedules_for_month(schedules, year, month)

    # 本月出现过的日程列表（去重）
    seen = set()
    month_schedules = []
    for item in active:
        s = item['schedule']
        if s['id'] not in seen:
            seen.add(s['id'])
            month_schedules.append(s)

    # 每天有哪些日程 id（供日历格子显示小点用）
    day_markers = {
        str(day): [s['id'] for s in shows]
        for day, shows in day_shows.items() if shows
    }

    # 近 7 天即将开始/结束的日程
    upcoming_raw = upcoming_schedules(schedules)
    upcoming = [
        {**dict(item['schedule']),
         'starting': item['starting'],
         'ending':   item['ending']}
        for item in upcoming_raw
    ]

    return jsonify({
        "ok":              True,
        "year":            year,
        "month":           month,
        "days_in":         days_in,
        "month_schedules": month_schedules,
        "day_markers":     day_markers,
        "upcoming":        upcoming,
        "conflict_ids":    conflict_ids,
    })


# ── 统计 ─────────────────────────────────────────────────────────────────────────

@app.route("/api/v1/stats")
@_require_token
def api_stats():
    try:
        year = int(request.args.get("year", datetime.now().year))
    except (ValueError, TypeError):
        year = datetime.now().year
    schedules = _get_schedules(g.api_uid)
    st        = annual_stats(schedules, year)
    return jsonify({"ok": True, "year": year, "stats": st})


# ── 搭档 ─────────────────────────────────────────────────────────────────────────

@app.route("/api/v1/partners")
@_require_token
def api_partners_list():
    rows = get_db().execute(
        "SELECT * FROM partners WHERE user_id=? ORDER BY created_at DESC", (g.api_uid,)
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["tags_list"] = json.loads(d["tags"]) if d.get("tags") else []
        result.append(d)
    return jsonify({"ok": True, "partners": result})


@app.route("/api/v1/partners", methods=["POST"])
@_require_token
def api_partner_add():
    data     = request.get_json(silent=True) or {}
    nickname = data.get("nickname", "").strip()
    if not nickname:
        return jsonify({"ok": False, "error": "搭档名不能为空"}), 400
    db   = get_db()
    ts   = int(datetime.now().timestamp())
    tags = json.dumps(data.get("tags", []))
    rating = int(data.get("rating", 0)) if str(data.get("rating","")).isdigit() else 0
    cur  = db.execute(
        "INSERT INTO partners (user_id, qq, nickname, rating, tags, notes, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (g.api_uid, data.get("qq","").strip(), nickname, rating, tags, data.get("notes",""), ts, ts)
    )
    db.commit()
    row = db.execute("SELECT * FROM partners WHERE id=?", (cur.lastrowid,)).fetchone()
    d = dict(row)
    d["tags_list"] = json.loads(d["tags"]) if d.get("tags") else []
    return jsonify({"ok": True, "partner": d}), 201


@app.route("/api/v1/partners/<int:pid>", methods=["DELETE"])
@_require_token
def api_partner_delete(pid):
    db = get_db()
    row = db.execute("SELECT id FROM partners WHERE id=? AND user_id=?", (pid, g.api_uid)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "不存在"}), 404
    db.execute("DELETE FROM partners WHERE id=?", (pid,))
    db.commit()
    return jsonify({"ok": True})


# ── 日记 ─────────────────────────────────────────────────────────────────────────

@app.route("/api/v1/diary")
@_require_token
def api_diary_list():
    rows = get_db().execute(
        "SELECT * FROM diaries WHERE user_id=? ORDER BY created_at DESC", (g.api_uid,)
    ).fetchall()
    return jsonify({"ok": True, "entries": [dict(r) for r in rows]})


@app.route("/api/v1/diary", methods=["POST"])
@_require_token
def api_diary_add():
    data    = request.get_json(silent=True) or {}
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"ok": False, "error": "内容不能为空"}), 400
    db = get_db()
    ts = int(datetime.now().timestamp())
    title      = data.get("title", "").strip()
    mood       = data.get("mood", "").strip()
    diary_date = data.get("diary_date", "").strip()
    cur = db.execute(
        "INSERT INTO diaries (user_id, title, content, mood, diary_date, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (g.api_uid, title, content, mood, diary_date, ts, ts)
    )
    db.commit()
    row = db.execute("SELECT * FROM diaries WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify({"ok": True, "entry": dict(row)}), 201


@app.route("/api/v1/diary/<int:did>", methods=["DELETE"])
@_require_token
def api_diary_delete(did):
    db = get_db()
    row = db.execute("SELECT id FROM diaries WHERE id=? AND user_id=?", (did, g.api_uid)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "不存在"}), 404
    db.execute("DELETE FROM diaries WHERE id=?", (did,))
    db.commit()
    return jsonify({"ok": True})


# ── 愿望单 ───────────────────────────────────────────────────────────────────────

@app.route("/api/v1/wishlist")
@_require_token
def api_wishlist_list():
    rows = get_db().execute(
        "SELECT * FROM wishlist WHERE user_id=? ORDER BY created_at DESC", (g.api_uid,)
    ).fetchall()
    return jsonify({"ok": True, "items": [dict(r) for r in rows]})


@app.route("/api/v1/wishlist", methods=["POST"])
@_require_token
def api_wishlist_add():
    data    = request.get_json(silent=True) or {}
    content = data.get("content", "").strip()
    wtype   = data.get("wtype", "题材").strip()
    if not content:
        return jsonify({"ok": False, "error": "内容不能为空"}), 400
    db = get_db()
    ts = int(datetime.now().timestamp())
    cur = db.execute(
        "INSERT INTO wishlist (user_id, wtype, content, notes, is_done, created_at) VALUES (?,?,?,?,0,?)",
        (g.api_uid, wtype, content, data.get("notes",""), ts)
    )
    db.commit()
    row = db.execute("SELECT * FROM wishlist WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify({"ok": True, "item": dict(row)}), 201


@app.route("/api/v1/wishlist/<int:wid>/toggle", methods=["POST"])
@_require_token
def api_wishlist_toggle(wid):
    db  = get_db()
    row = db.execute("SELECT * FROM wishlist WHERE id=? AND user_id=?", (wid, g.api_uid)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "不存在"}), 404
    new_val = 0 if row["is_done"] else 1
    db.execute("UPDATE wishlist SET is_done=? WHERE id=?", (new_val, wid))
    db.commit()
    return jsonify({"ok": True, "is_done": bool(new_val)})


@app.route("/api/v1/wishlist/<int:wid>", methods=["DELETE"])
@_require_token
def api_wishlist_delete(wid):
    db  = get_db()
    row = db.execute("SELECT id FROM wishlist WHERE id=? AND user_id=?", (wid, g.api_uid)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "不存在"}), 404
    db.execute("DELETE FROM wishlist WHERE id=?", (wid,))
    db.commit()
    return jsonify({"ok": True})


# ── 黑名单 ───────────────────────────────────────────────────────────────────────

@app.route("/api/v1/blacklist")
@_require_token
def api_blacklist_list():
    rows = get_db().execute(
        "SELECT * FROM blacklist WHERE user_id=? ORDER BY created_at DESC", (g.api_uid,)
    ).fetchall()
    return jsonify({"ok": True, "items": [dict(r) for r in rows]})


@app.route("/api/v1/blacklist", methods=["POST"])
@_require_token
def api_blacklist_add():
    data     = request.get_json(silent=True) or {}
    nickname = data.get("nickname", "").strip()
    if not nickname:
        return jsonify({"ok": False, "error": "昵称不能为空"}), 400
    db = get_db()
    ts = int(datetime.now().timestamp())
    cur = db.execute(
        "INSERT INTO blacklist (user_id, qq, nickname, reason, happened_at, notes, created_at) VALUES (?,?,?,?,?,?,?)",
        (g.api_uid, data.get("qq","").strip(), nickname,
         data.get("reason","").strip(), data.get("happened_at","").strip(),
         data.get("notes","").strip(), ts)
    )
    db.commit()
    row = db.execute("SELECT * FROM blacklist WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify({"ok": True, "item": dict(row)}), 201


@app.route("/api/v1/blacklist/<int:bid>", methods=["DELETE"])
@_require_token
def api_blacklist_delete(bid):
    db  = get_db()
    row = db.execute("SELECT id FROM blacklist WHERE id=? AND user_id=?", (bid, g.api_uid)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "不存在"}), 404
    db.execute("DELETE FROM blacklist WHERE id=?", (bid,))
    db.commit()
    return jsonify({"ok": True})


# ── 公会 ─────────────────────────────────────────────────────────────────────────

@app.route("/api/v1/guilds")
@_require_token
def api_guilds_mine():
    uid = g.api_uid
    db  = get_db()
    owned, member = _get_my_guilds(uid)
    # 我创建的公会附带待审核人数
    for gd in owned:
        gd['pending_count'] = db.execute(
            "SELECT COUNT(*) FROM guild_memberships WHERE guild_id=? AND status='pending'",
            (gd['id'],)
        ).fetchone()[0]
        gd['is_owner'] = True
    # 我加入的公会
    for gd in member:
        gd['pending_count'] = 0
        gd['is_owner'] = False
    # 我申请中但未批准的
    my_pending = [dict(r) for r in db.execute(
        '''SELECT g.id, g.name, g.slug, gm.created_at as applied_at
           FROM guilds g JOIN guild_memberships gm ON gm.guild_id=g.id
           WHERE gm.user_id=? AND gm.status='pending' ORDER BY gm.created_at DESC''', (uid,)
    ).fetchall()]
    return jsonify({"ok": True, "owned": owned, "member": member, "pending": my_pending})


@app.route("/api/v1/guilds/discover")
@_require_token
def api_guilds_discover():
    uid = g.api_uid
    q   = request.args.get("q", "").strip()
    db  = get_db()
    if q:
        rows = db.execute(
            "SELECT g.*, u.display_name AS owner_name FROM guilds g JOIN users u ON u.id=g.owner_id WHERE g.name LIKE ? OR g.slug LIKE ? ORDER BY g.created_at DESC",
            (f'%{q}%', f'%{q}%')
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT g.*, u.display_name AS owner_name FROM guilds g JOIN users u ON u.id=g.owner_id ORDER BY g.created_at DESC"
        ).fetchall()
    owned_ids  = {r['id'] for r in db.execute('SELECT id FROM guilds WHERE owner_id=?', (uid,)).fetchall()}
    my_memberships = {r['guild_id']: r['status'] for r in db.execute(
        "SELECT guild_id, status FROM guild_memberships WHERE user_id=?", (uid,)
    ).fetchall()}
    result = []
    for r in rows:
        gd = dict(r)
        gd['is_owner']    = gd['id'] in owned_ids
        gd['my_status']   = my_memberships.get(gd['id'])
        gd['member_count'] = db.execute(
            "SELECT COUNT(*) FROM guild_memberships WHERE guild_id=? AND status='approved'",
            (gd['id'],)
        ).fetchone()[0]
        result.append(gd)
    return jsonify({"ok": True, "guilds": result})


@app.route("/api/v1/guilds", methods=["POST"])
@_require_token
def api_guild_create():
    uid  = g.api_uid
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    slug = data.get("slug", "").strip().lower()
    sig  = data.get("signature", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "公会名不能为空"}), 400
    if not slug or not re.match(r'^[a-z0-9_-]{2,30}$', slug):
        return jsonify({"ok": False, "error": "公会 ID 只能含小写字母/数字/下划线/连字符，长度 2-30"}), 400
    db = get_db()
    if db.execute('SELECT id FROM guilds WHERE slug=?', (slug,)).fetchone():
        return jsonify({"ok": False, "error": f"公会 ID「{slug}」已被使用"}), 400
    ts  = int(datetime.now().timestamp())
    gid = db.execute(
        'INSERT INTO guilds (name, slug, signature, owner_id, created_at) VALUES (?,?,?,?,?)',
        (name, slug, sig, uid, ts)
    ).lastrowid
    db.commit()
    row = db.execute('SELECT * FROM guilds WHERE id=?', (gid,)).fetchone()
    return jsonify({"ok": True, "guild": dict(row)}), 201


@app.route("/api/v1/guilds/<int:gid>")
@_require_token
def api_guild_detail(gid):
    uid = g.api_uid
    db  = get_db()
    guild = db.execute(
        'SELECT g.*, u.display_name AS owner_name FROM guilds g JOIN users u ON u.id=g.owner_id WHERE g.id=?', (gid,)
    ).fetchone()
    if not guild:
        return jsonify({"ok": False, "error": "公会不存在"}), 404
    guild = dict(guild)
    is_owner = guild['owner_id'] == uid
    my_mem   = db.execute("SELECT status FROM guild_memberships WHERE guild_id=? AND user_id=?", (gid, uid)).fetchone()
    is_member = is_owner or (my_mem and my_mem['status'] == 'approved')
    if not is_member:
        return jsonify({"ok": False, "error": "你不是该公会成员"}), 403
    members = [dict(r) for r in db.execute(
        '''SELECT u.id, u.display_name, u.username, gm.approved_at
           FROM guild_memberships gm JOIN users u ON u.id=gm.user_id
           WHERE gm.guild_id=? AND gm.status='approved' ORDER BY gm.approved_at''', (gid,)
    ).fetchall()]
    pending = []
    if is_owner:
        pending = [dict(r) for r in db.execute(
            '''SELECT u.id, u.display_name, u.username, gm.created_at as applied_at
               FROM guild_memberships gm JOIN users u ON u.id=gm.user_id
               WHERE gm.guild_id=? AND gm.status='pending' ORDER BY gm.created_at''', (gid,)
        ).fetchall()]
    return jsonify({
        "ok": True, "guild": guild,
        "is_owner": is_owner, "members": members, "pending": pending
    })


@app.route("/api/v1/guilds/<int:gid>/join", methods=["POST"])
@_require_token
def api_guild_join(gid):
    uid = g.api_uid
    db  = get_db()
    guild = db.execute('SELECT id, owner_id FROM guilds WHERE id=?', (gid,)).fetchone()
    if not guild: return jsonify({"ok": False, "error": "公会不存在"}), 404
    if guild['owner_id'] == uid: return jsonify({"ok": False, "error": "你是该公会创建者"}), 400
    existing = db.execute("SELECT status FROM guild_memberships WHERE guild_id=? AND user_id=?", (gid, uid)).fetchone()
    if existing: return jsonify({"ok": False, "error": f"你已{existing['status']}该公会"}), 400
    db.execute("INSERT INTO guild_memberships (guild_id, user_id, status, created_at) VALUES (?,?,'pending',?)",
               (gid, uid, int(datetime.now().timestamp())))
    db.commit()
    return jsonify({"ok": True, "message": "已发送加入申请"})


@app.route("/api/v1/guilds/<int:gid>/leave", methods=["POST"])
@_require_token
def api_guild_leave(gid):
    uid = g.api_uid
    db  = get_db()
    guild = db.execute('SELECT owner_id FROM guilds WHERE id=?', (gid,)).fetchone()
    if not guild: return jsonify({"ok": False, "error": "公会不存在"}), 404
    if guild['owner_id'] == uid: return jsonify({"ok": False, "error": "会长不能离开公会"}), 400
    db.execute("DELETE FROM guild_memberships WHERE guild_id=? AND user_id=?", (gid, uid))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/v1/guilds/<int:gid>/approve/<int:target_uid>", methods=["POST"])
@_require_token
def api_guild_approve(gid, target_uid):
    uid = g.api_uid
    db  = get_db()
    guild = db.execute('SELECT owner_id FROM guilds WHERE id=?', (gid,)).fetchone()
    if not guild or guild['owner_id'] != uid: return jsonify({"ok": False, "error": "无权限"}), 403
    db.execute("UPDATE guild_memberships SET status='approved', approved_at=? WHERE guild_id=? AND user_id=? AND status='pending'",
               (int(datetime.now().timestamp()), gid, target_uid))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/v1/guilds/<int:gid>/reject/<int:target_uid>", methods=["POST"])
@_require_token
def api_guild_reject(gid, target_uid):
    uid = g.api_uid
    db  = get_db()
    guild = db.execute('SELECT owner_id FROM guilds WHERE id=?', (gid,)).fetchone()
    if not guild or guild['owner_id'] != uid: return jsonify({"ok": False, "error": "无权限"}), 403
    db.execute("DELETE FROM guild_memberships WHERE guild_id=? AND user_id=? AND status='pending'", (gid, target_uid))
    db.commit()
    return jsonify({"ok": True})


# ── Guild shared content API ────────────────────────────────────────────────────

@app.route("/api/v1/guilds/<int:gid>/schedules")
@_require_token
def api_guild_schedules(gid):
    uid = g.api_uid
    db  = get_db()
    # verify membership
    row = db.execute('SELECT owner_id FROM guilds WHERE id=?', (gid,)).fetchone()
    if not row: return jsonify({"ok": False, "error": "公会不存在"}), 404
    is_owner = row['owner_id'] == uid
    if not is_owner:
        mem = db.execute("SELECT status FROM guild_memberships WHERE guild_id=? AND user_id=?", (gid, uid)).fetchone()
        if not mem or mem['status'] != 'approved':
            return jsonify({"ok": False, "error": "无权限"}), 403
    # get all approved member uids
    member_rows = db.execute(
        "SELECT u.id, u.username, u.display_name FROM guild_memberships gm JOIN users u ON u.id=gm.user_id WHERE gm.guild_id=? AND gm.status='approved'",
        (gid,)
    ).fetchall()
    # also include owner if not already in memberships
    owner_row = db.execute("SELECT id, username, display_name FROM users WHERE id=?", (row['owner_id'],)).fetchone()
    all_members = {r['id']: dict(r) for r in member_rows}
    if owner_row: all_members[owner_row['id']] = dict(owner_row)

    result = []
    for mid, user in all_members.items():
        schs = _guild_member_schedules(mid)
        if schs:
            result.append({
                'user': user,
                'schedules': schs,
            })
    return jsonify({"ok": True, "members": result})


@app.route("/api/v1/guilds/<int:gid>/partners")
@_require_token
def api_guild_partners(gid):
    uid = g.api_uid
    db  = get_db()
    row = db.execute('SELECT owner_id FROM guilds WHERE id=?', (gid,)).fetchone()
    if not row: return jsonify({"ok": False, "error": "公会不存在"}), 404
    is_owner = row['owner_id'] == uid
    if not is_owner:
        mem = db.execute("SELECT status FROM guild_memberships WHERE guild_id=? AND user_id=?", (gid, uid)).fetchone()
        if not mem or mem['status'] != 'approved':
            return jsonify({"ok": False, "error": "无权限"}), 403
    member_uids = [r['user_id'] for r in db.execute(
        "SELECT user_id FROM guild_memberships WHERE guild_id=? AND status='approved'", (gid,)
    ).fetchall()]
    if row['owner_id'] not in member_uids:
        member_uids.append(row['owner_id'])
    shared_partners = []
    for mid in member_uids:
        rows = [dict(r) for r in db.execute(
            "SELECT p.*, u.display_name AS owner_name FROM partners p JOIN users u ON u.id=p.user_id WHERE p.user_id=?", (mid,)
        ).fetchall()]
        for p in rows:
            sg = json.loads(p.get('shared_guilds') or '[]')
            if gid in sg:
                p['tags_list'] = json.loads(p['tags']) if p.get('tags') else []
                shared_partners.append(p)
    return jsonify({"ok": True, "partners": shared_partners})


@app.route("/api/v1/guilds/<int:gid>/blacklist")
@_require_token
def api_guild_blacklist(gid):
    uid = g.api_uid
    db  = get_db()
    row = db.execute('SELECT owner_id FROM guilds WHERE id=?', (gid,)).fetchone()
    if not row: return jsonify({"ok": False, "error": "公会不存在"}), 404
    is_owner = row['owner_id'] == uid
    if not is_owner:
        mem = db.execute("SELECT status FROM guild_memberships WHERE guild_id=? AND user_id=?", (gid, uid)).fetchone()
        if not mem or mem['status'] != 'approved':
            return jsonify({"ok": False, "error": "无权限"}), 403
    member_uids = [r['user_id'] for r in db.execute(
        "SELECT user_id FROM guild_memberships WHERE guild_id=? AND status='approved'", (gid,)
    ).fetchall()]
    if row['owner_id'] not in member_uids:
        member_uids.append(row['owner_id'])
    shared_blacklist = []
    for mid in member_uids:
        rows = [dict(r) for r in db.execute(
            "SELECT b.*, u.display_name AS owner_name FROM blacklist b JOIN users u ON u.id=b.user_id WHERE b.user_id=?", (mid,)
        ).fetchall()]
        for b in rows:
            sg = json.loads(b.get('shared_guilds') or '[]')
            if gid in sg:
                shared_blacklist.append(b)
    return jsonify({"ok": True, "blacklist": shared_blacklist})


# ── Reports API ─────────────────────────────────────────────────────────────────

@app.route("/api/v1/reports", methods=["GET"])
@_require_token
def api_reports_get():
    uid = g.api_uid
    db  = get_db()
    approved_count = db.execute(
        "SELECT COUNT(*) FROM reports WHERE submitter_user_id=? AND status='approved'", (uid,)
    ).fetchone()[0]
    can_view = approved_count >= 2

    # my reports
    my_reports = [dict(r) for r in db.execute(
        'SELECT * FROM reports WHERE submitter_user_id=? ORDER BY created_at DESC', (uid,)
    ).fetchall()]
    appealed_ids = [r['report_id'] for r in db.execute(
        "SELECT report_id FROM report_appeals WHERE submitter_user_id=? AND status IN ('pending','approved')", (uid,)
    ).fetchall()]

    # public approved list (grouped by qq)
    groups = []
    if can_view:
        rows = [dict(r) for r in db.execute(
            "SELECT id, target_qq, tag, reason, created_at FROM reports WHERE status='approved' ORDER BY created_at DESC"
        ).fetchall()]
        from collections import defaultdict
        grp = defaultdict(list)
        for r in rows:
            grp[r['target_qq']].append(r)
        groups = [{'qq': qq, 'reports': rlist, 'count': len(rlist)}
                  for qq, rlist in sorted(grp.items(), key=lambda x: len(x[1]), reverse=True)]

    return jsonify({
        "ok": True,
        "can_view": can_view,
        "approved_count": approved_count,
        "my_reports": my_reports,
        "appealed_ids": appealed_ids,
        "groups": groups,
    })


@app.route("/api/v1/reports", methods=["POST"])
@_require_token
def api_reports_submit():
    uid  = g.api_uid
    data = request.get_json(silent=True) or {}
    target_qq = (data.get('target_qq') or '').strip()
    tag        = (data.get('tag')       or '').strip()
    reason     = (data.get('reason')    or '').strip()
    if not target_qq:
        return jsonify({"ok": False, "error": "QQ 号不能为空"}), 400
    if not re.match(r'^\d{5,12}$', target_qq):
        return jsonify({"ok": False, "error": "QQ 号格式不正确（5-12位数字）"}), 400
    if not reason:
        return jsonify({"ok": False, "error": "检举原因不能为空"}), 400
    db = get_db()
    db.execute(
        'INSERT INTO reports (target_qq, tag, reason, submitter_user_id, status, created_at) VALUES (?,?,?,?,?,?)',
        (target_qq, tag, reason, uid, 'pending', int(datetime.now().timestamp()))
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/v1/reports/<int:rid>", methods=["DELETE"])
@_require_token
def api_report_self_delete(rid):
    uid = g.api_uid
    db  = get_db()
    row = db.execute('SELECT submitter_user_id, status FROM reports WHERE id=?', (rid,)).fetchone()
    if not row or row['submitter_user_id'] != uid:
        return jsonify({"ok": False, "error": "无权限"}), 403
    if row['status'] == 'approved':
        approved_count = db.execute(
            "SELECT COUNT(*) FROM reports WHERE submitter_user_id=? AND status='approved'", (uid,)
        ).fetchone()[0]
        if approved_count <= 2:
            return jsonify({"ok": False, "error": "至少需要保留 2 条已通过的检举，无法删除"}), 400
    db.execute('DELETE FROM reports WHERE id=?', (rid,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/v1/reports/<int:rid>", methods=["PUT"])
@_require_token
def api_report_user_edit(rid):
    uid  = g.api_uid
    db   = get_db()
    row  = db.execute("SELECT submitter_user_id, status FROM reports WHERE id=?", (rid,)).fetchone()
    if not row or row['submitter_user_id'] != uid:
        return jsonify({"ok": False, "error": "无权限"}), 403
    if row['status'] != 'editing':
        return jsonify({"ok": False, "error": "当前状态不允许编辑"}), 400
    data   = request.get_json(silent=True) or {}
    tag    = (data.get('tag')    or '').strip()
    reason = (data.get('reason') or '').strip()
    if not reason:
        return jsonify({"ok": False, "error": "检举原因不能为空"}), 400
    db.execute("UPDATE reports SET tag=?, reason=?, status='pending', edit_note='' WHERE id=?",
               (tag, reason, rid))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/v1/reports/<int:rid>/appeal", methods=["POST"])
@_require_token
def api_report_appeal(rid):
    uid  = g.api_uid
    db   = get_db()
    data = request.get_json(silent=True) or {}
    reason = (data.get('reason') or '').strip()
    if not reason:
        return jsonify({"ok": False, "error": "申请理由不能为空"}), 400
    row = db.execute("SELECT id FROM reports WHERE id=? AND status='approved'", (rid,)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "该检举不存在或已被撤下"}), 404
    existing = db.execute(
        "SELECT id FROM report_appeals WHERE report_id=? AND submitter_user_id=? AND status='pending'",
        (rid, uid)
    ).fetchone()
    if existing:
        return jsonify({"ok": False, "error": "你已对这条检举提交过撤回申请，请等待审核"}), 400
    db.execute(
        'INSERT INTO report_appeals (report_id, submitter_user_id, reason, status, created_at) VALUES (?,?,?,?,?)',
        (rid, uid, reason, 'pending', int(datetime.now().timestamp()))
    )
    db.commit()
    return jsonify({"ok": True})


# ── 戏录（App） ───────────────────────────────────────────────────────────────────

@app.route("/api/v1/drama")
@_require_token
def api_drama_list():
    rows = get_db().execute(
        "SELECT * FROM drama_logs WHERE user_id=? ORDER BY created_at DESC", (g.api_uid,)
    ).fetchall()
    return jsonify({"ok": True, "entries": [dict(r) for r in rows]})


@app.route("/api/v1/drama", methods=["POST"])
@_require_token
def api_drama_add():
    data = request.get_json(silent=True) or {}
    ts = int(datetime.now().timestamp())
    db = get_db()
    cur = db.execute(
        """INSERT INTO drama_logs
           (user_id, title, my_char, partner_char, partner_qq,
            genre, status, notes, content, start_ts, end_ts, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            g.api_uid,
            data.get("title", "").strip(),
            data.get("my_char", "").strip(),
            data.get("partner_char", "").strip(),
            data.get("partner_qq", "").strip(),
            data.get("genre", "").strip(),
            data.get("status", "ongoing").strip(),
            data.get("notes", "").strip(),
            data.get("content", "").strip(),
            data.get("start_ts"),
            data.get("end_ts"),
            ts, ts,
        )
    )
    db.commit()
    row = db.execute("SELECT * FROM drama_logs WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify({"ok": True, "entry": dict(row)}), 201


@app.route("/api/v1/drama/<int:did>", methods=["PUT"])
@_require_token
def api_drama_update(did):
    db = get_db()
    row = db.execute("SELECT id FROM drama_logs WHERE id=? AND user_id=?", (did, g.api_uid)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "不存在"}), 404
    data = request.get_json(silent=True) or {}
    ts = int(datetime.now().timestamp())
    db.execute(
        """UPDATE drama_logs
           SET title=?, my_char=?, partner_char=?, partner_qq=?,
               genre=?, status=?, notes=?, content=?, start_ts=?, end_ts=?, updated_at=?
           WHERE id=? AND user_id=?""",
        (
            data.get("title", "").strip(),
            data.get("my_char", "").strip(),
            data.get("partner_char", "").strip(),
            data.get("partner_qq", "").strip(),
            data.get("genre", "").strip(),
            data.get("status", "ongoing").strip(),
            data.get("notes", "").strip(),
            data.get("content", "").strip(),
            data.get("start_ts"),
            data.get("end_ts"),
            ts, did, g.api_uid,
        )
    )
    db.commit()
    updated = db.execute("SELECT * FROM drama_logs WHERE id=?", (did,)).fetchone()
    return jsonify({"ok": True, "entry": dict(updated)})


@app.route("/api/v1/drama/<int:did>/status", methods=["PATCH"])
@_require_token
def api_drama_status(did):
    db = get_db()
    row = db.execute("SELECT id FROM drama_logs WHERE id=? AND user_id=?", (did, g.api_uid)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "不存在"}), 404
    data   = request.get_json(silent=True) or {}
    status = data.get("status", "ongoing").strip()
    if status not in ("ongoing", "completed", "dropped"):
        return jsonify({"ok": False, "error": "无效状态"}), 400
    ts = int(datetime.now().timestamp())
    db.execute("UPDATE drama_logs SET status=?, updated_at=? WHERE id=? AND user_id=?",
               (status, ts, did, g.api_uid))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/v1/drama/<int:did>", methods=["DELETE"])
@_require_token
def api_drama_delete(did):
    db = get_db()
    row = db.execute("SELECT id FROM drama_logs WHERE id=? AND user_id=?", (did, g.api_uid)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "不存在"}), 404
    db.execute("DELETE FROM drama_logs WHERE id=? AND user_id=?", (did, g.api_uid))
    db.commit()
    return jsonify({"ok": True})


# ── 卡包 API ─────────────────────────────────────────────────────────────────────

CARD_TYPES_API = ['板写', '溶图', '溶写', '其他']

def _card_days_left_api(expiry_str):
    try:
        from datetime import date as _date
        exp = _date.fromisoformat(expiry_str)
        return (exp - _date.today()).days
    except Exception:
        return None


@app.route("/api/v1/cards", methods=["GET"])
@_require_token
def api_cards_list():
    db = get_db()
    type_filter = request.args.get('type', '').strip()
    q = "SELECT * FROM cards WHERE user_id=? ORDER BY expiry ASC, created_at ASC"
    rows = [dict(r) for r in db.execute(q, (g.api_uid,)).fetchall()]
    for r in rows:
        r['days_left'] = _card_days_left_api(r['expiry'])
    if type_filter and type_filter in CARD_TYPES_API:
        rows = [r for r in rows if r['card_type'] == type_filter]
    counts = {t: sum(1 for r in rows if r.get('card_type') == t) for t in CARD_TYPES_API}
    return jsonify({"ok": True, "cards": rows, "counts": counts, "types": CARD_TYPES_API})


@app.route("/api/v1/cards", methods=["POST"])
@_require_token
def api_cards_add():
    db   = get_db()
    data = request.get_json(force=True) or {}
    name      = (data.get('name') or '').strip()
    expiry    = (data.get('expiry') or '').strip()
    quantity  = int(data.get('quantity') or 1)
    price     = float(data.get('price') or 0)
    card_type = (data.get('card_type') or '其他').strip()
    notes     = (data.get('notes') or '').strip()

    if not name or not expiry:
        return jsonify({"ok": False, "error": "名称和到期日不能为空"}), 400
    try:
        datetime.strptime(expiry, '%Y-%m-%d')
    except ValueError:
        return jsonify({"ok": False, "error": "日期格式应为 YYYY-MM-DD"}), 400
    if card_type not in CARD_TYPES_API:
        card_type = '其他'
    if db.execute("SELECT id FROM cards WHERE user_id=? AND name=?", (g.api_uid, name)).fetchone():
        return jsonify({"ok": False, "error": f"名称「{name}」已存在"}), 400

    now = int(datetime.now().timestamp())
    cur = db.execute(
        "INSERT INTO cards (user_id, name, expiry, quantity, price, card_type, notes, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (g.api_uid, name, expiry, quantity, price, card_type, notes, now, now)
    )
    db.commit()
    row = dict(db.execute("SELECT * FROM cards WHERE id=?", (cur.lastrowid,)).fetchone())
    row['days_left'] = _card_days_left_api(row['expiry'])
    return jsonify({"ok": True, "card": row})


@app.route("/api/v1/cards/<int:cid>", methods=["PUT"])
@_require_token
def api_cards_edit(cid):
    db  = get_db()
    row = db.execute("SELECT id FROM cards WHERE id=? AND user_id=?", (cid, g.api_uid)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "不存在"}), 404
    data      = request.get_json(force=True) or {}
    name      = (data.get('name') or '').strip()
    expiry    = (data.get('expiry') or '').strip()
    quantity  = int(data.get('quantity') or 1)
    price     = float(data.get('price') or 0)
    card_type = (data.get('card_type') or '其他').strip()
    notes     = (data.get('notes') or '').strip()

    if not name or not expiry:
        return jsonify({"ok": False, "error": "名称和到期日不能为空"}), 400
    try:
        datetime.strptime(expiry, '%Y-%m-%d')
    except ValueError:
        return jsonify({"ok": False, "error": "日期格式应为 YYYY-MM-DD"}), 400
    if card_type not in CARD_TYPES_API:
        card_type = '其他'
    dup = db.execute("SELECT id FROM cards WHERE user_id=? AND name=? AND id!=?",
                     (g.api_uid, name, cid)).fetchone()
    if dup:
        return jsonify({"ok": False, "error": f"名称「{name}」已被占用"}), 400

    now = int(datetime.now().timestamp())
    db.execute(
        "UPDATE cards SET name=?, expiry=?, quantity=?, price=?, card_type=?, notes=?, updated_at=? "
        "WHERE id=? AND user_id=?",
        (name, expiry, quantity, price, card_type, notes, now, cid, g.api_uid)
    )
    db.commit()
    updated = dict(db.execute("SELECT * FROM cards WHERE id=?", (cid,)).fetchone())
    updated['days_left'] = _card_days_left_api(updated['expiry'])
    return jsonify({"ok": True, "card": updated})


@app.route("/api/v1/cards/<int:cid>/consume", methods=["POST"])
@_require_token
def api_cards_consume(cid):
    db  = get_db()
    row = db.execute("SELECT * FROM cards WHERE id=? AND user_id=?", (cid, g.api_uid)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "不存在"}), 404
    data  = request.get_json(force=True) or {}
    count = int(data.get('count') or 1)
    new_qty = max(0, row['quantity'] - count)
    now = int(datetime.now().timestamp())
    db.execute("UPDATE cards SET quantity=?, last_consume=?, updated_at=? WHERE id=? AND user_id=?",
               (new_qty, now, now, cid, g.api_uid))
    db.commit()
    updated = dict(db.execute("SELECT * FROM cards WHERE id=?", (cid,)).fetchone())
    updated['days_left'] = _card_days_left_api(updated['expiry'])
    return jsonify({"ok": True, "card": updated})


@app.route("/api/v1/cards/<int:cid>", methods=["DELETE"])
@_require_token
def api_cards_delete(cid):
    db  = get_db()
    row = db.execute("SELECT name FROM cards WHERE id=? AND user_id=?", (cid, g.api_uid)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "不存在"}), 404
    db.execute("DELETE FROM cards WHERE id=? AND user_id=?", (cid, g.api_uid))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/v1/cards/clean", methods=["POST"])
@_require_token
def api_cards_clean():
    db    = get_db()
    today = date_cls.today().isoformat()
    expired = [r['name'] for r in db.execute(
        "SELECT name FROM cards WHERE user_id=? AND expiry < ?", (g.api_uid, today)).fetchall()]
    if expired:
        db.execute("DELETE FROM cards WHERE user_id=? AND expiry < ?", (g.api_uid, today))
        db.commit()
    return jsonify({"ok": True, "cleaned": len(expired), "names": expired})


@app.route("/api/v1/cards/random", methods=["GET"])
@_require_token
def api_cards_random():
    import random as _random
    db          = get_db()
    today       = date_cls.today().isoformat()
    type_filter = request.args.get('type', '').strip()
    q      = "SELECT * FROM cards WHERE user_id=? AND expiry >= ? AND quantity > 0"
    params = [g.api_uid, today]
    if type_filter and type_filter in CARD_TYPES_API:
        q += " AND card_type=?"
        params.append(type_filter)
    rows = db.execute(q, params).fetchall()
    if not rows:
        return jsonify({"ok": False, "error": "没有可用的卡片"})
    card = dict(_random.choice(rows))
    card['days_left'] = _card_days_left_api(card['expiry'])
    return jsonify({"ok": True, "card": card})


# ── API: 反馈 ──────────────────────────────────────────────────────────────────

@app.route("/api/v1/feedback", methods=["POST"])
@_require_token
def api_submit_feedback():
    data    = request.get_json(silent=True) or {}
    ftype   = data.get("type", "bug").strip()
    content = data.get("content", "").strip()
    app_ver = data.get("app_version", "").strip()   # 可选：App 版本号
    if ftype not in ("bug", "wish"):
        ftype = "bug"
    if not content:
        return jsonify({"ok": False, "error": "内容不能为空"})
    if len(content) > 1000:
        return jsonify({"ok": False, "error": "内容不能超过 1000 字"})
    db = get_db()
    # 把版本号附在内容末尾，方便后台查看
    full_content = content if not app_ver else f"{content}\n\n[App {app_ver}]"
    db.execute(
        "INSERT INTO feedbacks (user_id, type, content, created_at, is_read) VALUES (?,?,?,?,0)",
        (g.api_uid, ftype, full_content, int(datetime.now().timestamp()))
    )
    db.commit()
    return jsonify({"ok": True})


# ── Error handlers ──────────────────────────────────────────────────────────────

@app.errorhandler(404)
def handle_404(e):
    return render_template('error.html', code=404, msg='页面不存在'), 404

@app.errorhandler(500)
def handle_500(e):
    _logger.error("500\nURL: %s %s\n%s", request.method, request.url, traceback.format_exc())
    return render_template('error.html', code=500, msg='服务器内部错误'), 500


if __name__ == '__main__':
    app.run(debug=True, port=5002)

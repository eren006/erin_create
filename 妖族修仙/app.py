import os, json, time
from datetime import timedelta, date
from functools import wraps
from flask import (Flask, render_template, request, redirect,
                   url_for, session as S, flash, g)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

from game_data import (STAGES, MAX_STAGE_INDEX, stage_by_index, stage_display_name,
                        SPECIES, SPECIES_ORDER, species_label,
                        ENDING_DIVINE_HUMANITY_MIN, ENDING_FERAL_HUMANITY_MAX,
                        ACHIEVEMENTS)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "yaozu_xiuxian_secret_2026")
app.permanent_session_lifetime = timedelta(days=30)

@app.template_filter('fmt_ts')
def fmt_ts(ts):
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(ts)) if ts else '-'

DB_PATH     = os.path.join(os.path.dirname(__file__), "yaozu.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")
ADMIN_USER  = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASS  = os.environ.get("ADMIN_PASSWORD", "yaozu_admin_888")
now_ts      = lambda: int(time.time())
today_str   = lambda: date.today().isoformat()

# ── 数据库 ─────────────────────────────────────────────────────────────────────

def get_db():
    db = getattr(g, '_db', None)
    if db is None:
        db = g._db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
    return db

@app.teardown_appcontext
def close_db(e=None):
    db = getattr(g, '_db', None)
    if db: db.close()

def q(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    return cur.fetchone() if one else cur.fetchall()

def run(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur

def init_db():
    db = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, encoding='utf-8') as f:
        db.executescript(f.read())
    db.commit()
    _migrate_characters(db)
    _ensure_admin(db)
    _ensure_achievement_defs(db)
    db.close()

def _migrate_characters(db):
    cols = {row[1] for row in db.execute("PRAGMA table_info(characters)")}
    add = {
        'stage_index':    "ALTER TABLE characters ADD COLUMN stage_index INTEGER DEFAULT 0",
        'yao_power':      "ALTER TABLE characters ADD COLUMN yao_power INTEGER DEFAULT 0",
        'humanoid_value': "ALTER TABLE characters ADD COLUMN humanoid_value INTEGER DEFAULT 100",
        'humanity':       "ALTER TABLE characters ADD COLUMN humanity INTEGER DEFAULT 50",
        'final_form':     "ALTER TABLE characters ADD COLUMN final_form TEXT DEFAULT NULL",
    }
    for col, ddl in add.items():
        if col not in cols:
            db.execute(ddl)
    db.commit()

def _ensure_admin(db):
    row = db.execute("SELECT id FROM users WHERE username=?", (ADMIN_USER,)).fetchone()
    if not row:
        db.execute(
            "INSERT INTO users (username,password_hash,qq,role,status,created_ts) VALUES (?,?,?,?,?,?)",
            (ADMIN_USER, generate_password_hash(ADMIN_PASS, method='pbkdf2:sha256'),
             '00000000', 'admin', 'approved', now_ts()))
        db.commit()

def _ensure_achievement_defs(db):
    for a in ACHIEVEMENTS:
        db.execute(
            "INSERT INTO achievement_defs (key,name,description,condition_json,reward_json) VALUES (?,?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET name=excluded.name, description=excluded.description, "
            "condition_json=excluded.condition_json, reward_json=excluded.reward_json",
            (a['key'], a['name'], a['description'], json.dumps(a['condition'], ensure_ascii=False),
             json.dumps(a['reward'], ensure_ascii=False)))
    db.commit()

# ── 登录态 ─────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def w(*a, **kw):
        if 'uid' not in S:
            return redirect(url_for('login'))
        return f(*a, **kw)
    return w

def admin_required(f):
    @wraps(f)
    def w(*a, **kw):
        if S.get('role') != 'admin':
            flash('无权访问', 'error')
            return redirect(url_for('login'))
        return f(*a, **kw)
    return w

def me_character():
    uid = S.get('uid')
    if not uid:
        return None
    row = q("SELECT * FROM characters WHERE user_id=?", (uid,), one=True)
    return dict(row) if row else None

def log_admin(action, target_type='', target_id=None, detail=''):
    run("INSERT INTO admin_logs (admin_id,target_type,target_id,action,detail,created_ts) VALUES (?,?,?,?,?,?)",
        (S.get('real_admin_uid', S.get('uid')), target_type, target_id, action, detail, now_ts()))

# ── 站内信(兼作通知系统) ─────────────────────────────────────────────────────────

def send_system_mail(char_id, subject, body='', attachment=None, from_label='系统'):
    run("INSERT INTO mail (char_id,from_label,subject,body,attachment_json,claimed,read,created_ts) "
        "VALUES (?,?,?,?,?,0,0,?)",
        (char_id, from_label, subject, body,
         json.dumps(attachment, ensure_ascii=False) if attachment else None, now_ts()))

def unread_mail_count(char_id):
    return q("SELECT COUNT(*) c FROM mail WHERE char_id=? AND read=0", (char_id,), one=True)['c']

@app.context_processor
def inject_mail_count():
    char = me_character()
    return {'unread_mail_count': unread_mail_count(char['id']) if char else 0}

# ── 每日计数器(通用限流基建,当前无具体玩法调用,留给后续每日行为用) ─────────────────

def bump_daily_counter(char_id, key):
    day = today_str()
    run("INSERT INTO daily_counters (char_id,counter_key,day,count) VALUES (?,?,?,1) "
        "ON CONFLICT(char_id,counter_key,day) DO UPDATE SET count=count+1", (char_id, key, day))
    return q("SELECT count FROM daily_counters WHERE char_id=? AND counter_key=? AND day=?",
              (char_id, key, day), one=True)['count']

def get_daily_counter(char_id, key):
    row = q("SELECT count FROM daily_counters WHERE char_id=? AND counter_key=? AND day=?",
            (char_id, key, today_str()), one=True)
    return row['count'] if row else 0

# ── 成就引擎:声明式条件,当前支持境界达成 / 人性值区间 ──────────────────────────────

def _achievement_condition_met(char, condition):
    ctype = condition.get('type')
    value = condition.get('value')
    if ctype == 'stage_reached':
        return char['stage_index'] >= value
    if ctype == 'humanity_at_least':
        return char['humanity'] >= value
    if ctype == 'humanity_at_most':
        return char['humanity'] <= value
    return False

def check_achievements(char_id):
    char = q("SELECT * FROM characters WHERE id=?", (char_id,), one=True)
    if not char:
        return
    got = {r['achievement_key'] for r in q(
        "SELECT achievement_key FROM char_achievements WHERE char_id=?", (char_id,))}
    defs = q("SELECT * FROM achievement_defs")
    for d in defs:
        if d['key'] in got:
            continue
        condition = json.loads(d['condition_json'])
        if not _achievement_condition_met(char, condition):
            continue
        run("INSERT INTO char_achievements (char_id,achievement_key,achieved_ts) VALUES (?,?,?)",
            (char_id, d['key'], now_ts()))
        reward = json.loads(d['reward_json'])
        send_system_mail(char_id, f"达成成就:{d['name']}", d['description'], attachment=reward)

# ── 首页 ───────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'uid' in S:
        if S.get('role') == 'admin':
            return redirect(url_for('admin_home'))
        return redirect(url_for('home'))
    return redirect(url_for('login'))

# ── 注册(需管理员审核,填有效邀请码可直接免审) ───────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        qq       = request.form.get('qq', '').strip()
        invite   = request.form.get('invite_code', '').strip()

        err = None
        if not (2 <= len(username) <= 20):
            err = '用户名长度需在 2-20 位之间'
        elif len(password) < 6:
            err = '密码至少 6 位'
        elif not qq:
            err = '请填写 QQ 号'
        elif q("SELECT id FROM users WHERE username=?", (username,), one=True):
            err = '用户名已被占用'

        if err:
            flash(err, 'error')
            return render_template('register.html')

        status = 'pending'
        invite_row = None
        if invite:
            invite_row = q("SELECT * FROM invite_codes WHERE code=?", (invite,), one=True)
            valid = (invite_row and invite_row['used_count'] < invite_row['max_uses']
                      and (not invite_row['expires_ts'] or invite_row['expires_ts'] > now_ts()))
            if valid:
                status = 'approved'
                run("UPDATE invite_codes SET used_count=used_count+1 WHERE id=?", (invite_row['id'],))
            else:
                flash('邀请码无效或已失效,已按普通注册提交审核', 'error')

        run("INSERT INTO users (username,password_hash,qq,role,status,created_ts) VALUES (?,?,?,?,?,?)",
            (username, generate_password_hash(password, method='pbkdf2:sha256'), qq,
             'player', status, now_ts()))

        if status == 'approved':
            return redirect(url_for('login'))
        return redirect(url_for('register_pending'))

    return render_template('register.html')

@app.route('/register/pending')
def register_pending():
    return render_template('register_pending.html')

# ── 登录 / 登出 ─────────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    err = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = q("SELECT * FROM users WHERE username=?", (username,), one=True)
        if not user or not check_password_hash(user['password_hash'], password):
            err = '账号或密码错误'
        elif user['status'] == 'pending':
            err = '账号审核中,请等待管理员审核'
        elif user['status'] == 'rejected':
            err = '账号审核未通过'
        else:
            S.permanent = True
            S['uid'] = user['id']; S['uname'] = user['username']; S['role'] = user['role']
            run("UPDATE users SET last_login=? WHERE id=?", (now_ts(), user['id']))
            if user['role'] == 'admin':
                return redirect(url_for('admin_home'))
            char = q("SELECT id FROM characters WHERE user_id=?", (user['id'],), one=True)
            return redirect(url_for('home') if char else url_for('create_character'))
    return render_template('login.html', err=err)

@app.route('/logout')
def logout():
    S.clear()
    return redirect(url_for('login'))

# ── 管理员专用登录 ───────────────────────────────────────────────────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if S.get('role') == 'admin':
        return redirect(url_for('admin_home'))
    err = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = q("SELECT * FROM users WHERE username=?", (username,), one=True)
        if user and user['role'] == 'admin' and check_password_hash(user['password_hash'], password):
            S.permanent = True
            S['uid'] = user['id']; S['uname'] = user['username']; S['role'] = 'admin'
            run("UPDATE users SET last_login=? WHERE id=?", (now_ts(), user['id']))
            return redirect(url_for('admin_home'))
        err = '账号或密码错误(仅管理员可用此入口)'
    return render_template('admin_login.html', err=err)

# ── 角色创建(审核通过后首次进入,7 选 1 起始物种) ──────────────────────────────────

@app.route('/create_character', methods=['GET', 'POST'])
@login_required
def create_character():
    if S.get('role') == 'admin':
        return redirect(url_for('admin_home'))
    if me_character():
        return redirect(url_for('home'))

    if request.method == 'POST':
        name    = request.form.get('name', '').strip()
        species = request.form.get('species', '').strip()
        bio     = request.form.get('bio', '').strip()

        err = None
        if not (1 <= len(name) <= 12):
            err = '道号长度需在 1-12 位之间'
        elif species not in SPECIES:
            err = '请从给定的七种起始血脉中选择一种'

        if err:
            flash(err, 'error')
            return render_template('create_character.html', name=name, species=species, bio=bio,
                                    species_order=SPECIES_ORDER, species_info=SPECIES)

        cur = run("INSERT INTO characters (user_id,name,species,bio,stage_index,yao_power,"
                   "humanoid_value,humanity,created_ts) VALUES (?,?,?,?,0,0,100,50,?)",
                   (S['uid'], name, species, bio, now_ts()))
        check_achievements(cur.lastrowid)
        return redirect(url_for('home'))

    return render_template('create_character.html', name='', species='', bio='',
                            species_order=SPECIES_ORDER, species_info=SPECIES)

# ── 玩家首页 ───────────────────────────────────────────────────────────────────

@app.route('/home')
@login_required
def home():
    if S.get('role') == 'admin':
        return redirect(url_for('admin_home'))
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))

    stage = stage_by_index(char['stage_index'])
    next_stage = stage_by_index(char['stage_index'] + 1) if char['stage_index'] < MAX_STAGE_INDEX else None
    if next_stage:
        span = next_stage['yao_power_required'] - stage['yao_power_required']
        progress = (char['yao_power'] - stage['yao_power_required']) / span if span else 0
        stage_progress_pct = max(0, min(100, round(progress * 100)))
    else:
        stage_progress_pct = 100
    species_info = SPECIES.get(char['species'], {})
    clan_member = q("SELECT clans.* FROM clan_members JOIN clans ON clans.id = clan_members.clan_id "
                     "WHERE clan_members.char_id=?", (char['id'],), one=True)
    as_master = q("SELECT c.name FROM mentorships m JOIN characters c ON c.id = m.disciple_id "
                  "WHERE m.master_id=?", (char['id'],))
    as_disciple = q("SELECT c.name FROM mentorships m JOIN characters c ON c.id = m.master_id "
                    "WHERE m.disciple_id=?", (char['id'],), one=True)

    return render_template('home.html', char=char, stage=stage, next_stage=next_stage,
                            stage_progress_pct=stage_progress_pct,
                            species_info=species_info, clan_member=clan_member,
                            as_master=as_master, as_disciple=as_disciple,
                            ending_divine_min=ENDING_DIVINE_HUMANITY_MIN,
                            ending_feral_max=ENDING_FERAL_HUMANITY_MAX)

# ── 站内信 ─────────────────────────────────────────────────────────────────────

@app.route('/mail')
@login_required
def mail_inbox():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    mails = q("SELECT * FROM mail WHERE char_id=? ORDER BY created_ts DESC", (char['id'],))
    run("UPDATE mail SET read=1 WHERE char_id=? AND read=0", (char['id'],))
    mails_view = []
    for m in mails:
        m = dict(m)
        m['attachment'] = json.loads(m['attachment_json']) if m['attachment_json'] else None
        mails_view.append(m)
    return render_template('mail.html', mails=mails_view)

@app.route('/mail/<int:mail_id>/claim', methods=['POST'])
@login_required
def mail_claim(mail_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    m = q("SELECT * FROM mail WHERE id=? AND char_id=?", (mail_id, char['id']), one=True)
    if not m or not m['attachment_json'] or m['claimed']:
        return redirect(url_for('mail_inbox'))
    attachment = json.loads(m['attachment_json'])
    if 'yao_power' in attachment:
        run("UPDATE characters SET yao_power=yao_power+? WHERE id=?", (attachment['yao_power'], char['id']))
    run("UPDATE mail SET claimed=1 WHERE id=?", (mail_id,))
    flash('已领取附件', 'ok')
    return redirect(url_for('mail_inbox'))

# ── 礼包码兑换 ─────────────────────────────────────────────────────────────────

@app.route('/redeem', methods=['GET', 'POST'])
@login_required
def redeem():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        gc = q("SELECT * FROM gift_codes WHERE code=?", (code,), one=True)
        if not gc:
            flash('礼包码不存在', 'error')
        elif gc['used_count'] >= gc['max_uses']:
            flash('礼包码已达兑换上限', 'error')
        elif gc['expires_ts'] and gc['expires_ts'] < now_ts():
            flash('礼包码已过期', 'error')
        elif q("SELECT 1 FROM gift_code_uses WHERE gift_code_id=? AND char_id=?",
               (gc['id'], char['id']), one=True):
            flash('你已经兑换过这个礼包码了', 'error')
        else:
            reward = json.loads(gc['reward_json'])
            if 'yao_power' in reward:
                run("UPDATE characters SET yao_power=yao_power+? WHERE id=?", (reward['yao_power'], char['id']))
            run("INSERT INTO gift_code_uses (gift_code_id,char_id,used_ts) VALUES (?,?,?)",
                (gc['id'], char['id'], now_ts()))
            run("UPDATE gift_codes SET used_count=used_count+1 WHERE id=?", (gc['id'],))
            flash(f"兑换成功,获得妖力 +{reward.get('yao_power', 0)}", 'ok')
        return redirect(url_for('redeem'))
    return render_template('redeem.html')

# ── 宗门 / 师徒 ─────────────────────────────────────────────────────────────────

@app.route('/clan')
@login_required
def clan_list():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    clans = q("""SELECT clans.*, COUNT(clan_members.id) member_count
                 FROM clans LEFT JOIN clan_members ON clan_members.clan_id = clans.id
                 GROUP BY clans.id ORDER BY clans.created_ts DESC""")
    my_clan = q("SELECT clan_id FROM clan_members WHERE char_id=?", (char['id'],), one=True)
    return render_template('clan.html', clans=clans, my_clan_id=my_clan['clan_id'] if my_clan else None)

@app.route('/clan/create', methods=['POST'])
@login_required
def clan_create():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if q("SELECT 1 FROM clan_members WHERE char_id=?", (char['id'],), one=True):
        flash('你已经加入了一个宗门,请先退出', 'error')
        return redirect(url_for('clan_list'))
    name = request.form.get('name', '').strip()
    desc = request.form.get('description', '').strip()
    if not (1 <= len(name) <= 20):
        flash('宗门名长度需在 1-20 位之间', 'error')
        return redirect(url_for('clan_list'))
    if q("SELECT 1 FROM clans WHERE name=?", (name,), one=True):
        flash('宗门名已被占用', 'error')
        return redirect(url_for('clan_list'))
    cur = run("INSERT INTO clans (name,leader_id,description,created_ts) VALUES (?,?,?,?)",
              (name, char['id'], desc, now_ts()))
    run("INSERT INTO clan_members (clan_id,char_id,rank,joined_ts) VALUES (?,?,'leader',?)",
        (cur.lastrowid, char['id'], now_ts()))
    return redirect(url_for('clan_detail', clan_id=cur.lastrowid))

@app.route('/clan/<int:clan_id>')
@login_required
def clan_detail(clan_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    clan = q("SELECT * FROM clans WHERE id=?", (clan_id,), one=True)
    if not clan:
        flash('宗门不存在', 'error')
        return redirect(url_for('clan_list'))
    members = q("""SELECT clan_members.*, characters.name, characters.species, characters.stage_index
                    FROM clan_members JOIN characters ON characters.id = clan_members.char_id
                    WHERE clan_id=? ORDER BY (rank='leader') DESC, joined_ts""", (clan_id,))
    my_membership = q("SELECT * FROM clan_members WHERE char_id=?", (char['id'],), one=True)
    is_leader = my_membership and my_membership['clan_id'] == clan_id and my_membership['rank'] == 'leader'
    member_ids = {m['char_id'] for m in members}
    mentor_pairs = q("""SELECT m.*, cm.name master_name, cd.name disciple_name FROM mentorships m
                         JOIN characters cm ON cm.id = m.master_id
                         JOIN characters cd ON cd.id = m.disciple_id
                         WHERE m.master_id IN (SELECT char_id FROM clan_members WHERE clan_id=?)""",
                      (clan_id,))
    return render_template('clan_detail.html', clan=clan, members=members, is_leader=is_leader,
                            in_this_clan=char['id'] in member_ids, mentor_pairs=mentor_pairs,
                            stage_display_name=stage_display_name)

@app.route('/clan/<int:clan_id>/join', methods=['POST'])
@login_required
def clan_join(clan_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if q("SELECT 1 FROM clan_members WHERE char_id=?", (char['id'],), one=True):
        flash('你已经加入了一个宗门,请先退出', 'error')
    else:
        run("INSERT INTO clan_members (clan_id,char_id,rank,joined_ts) VALUES (?,?,'member',?)",
            (clan_id, char['id'], now_ts()))
    return redirect(url_for('clan_detail', clan_id=clan_id))

@app.route('/clan/<int:clan_id>/leave', methods=['POST'])
@login_required
def clan_leave(clan_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    run("DELETE FROM clan_members WHERE clan_id=? AND char_id=?", (clan_id, char['id']))
    run("DELETE FROM mentorships WHERE master_id=? OR disciple_id=?", (char['id'], char['id']))
    return redirect(url_for('clan_list'))

@app.route('/clan/<int:clan_id>/assign_mentor', methods=['POST'])
@login_required
def clan_assign_mentor(clan_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    my_membership = q("SELECT * FROM clan_members WHERE char_id=? AND clan_id=?", (char['id'], clan_id), one=True)
    if not my_membership or my_membership['rank'] != 'leader':
        flash('只有宗主可以指定师徒', 'error')
        return redirect(url_for('clan_detail', clan_id=clan_id))
    master_id = request.form.get('master_id', type=int)
    disciple_id = request.form.get('disciple_id', type=int)
    valid_ids = {m['char_id'] for m in q("SELECT char_id FROM clan_members WHERE clan_id=?", (clan_id,))}
    if not master_id or not disciple_id or master_id == disciple_id or \
       master_id not in valid_ids or disciple_id not in valid_ids:
        flash('请选择两名不同的本宗弟子', 'error')
        return redirect(url_for('clan_detail', clan_id=clan_id))
    run("DELETE FROM mentorships WHERE disciple_id=?", (disciple_id,))
    run("INSERT INTO mentorships (master_id,disciple_id,created_ts) VALUES (?,?,?)",
        (master_id, disciple_id, now_ts()))
    return redirect(url_for('clan_detail', clan_id=clan_id))

# ── 管理后台:首页统计 ────────────────────────────────────────────────────────────

@app.route('/admin')
@admin_required
def admin_home():
    stats = {
        'pending':  q("SELECT COUNT(*) c FROM users WHERE status='pending'", one=True)['c'],
        'approved': q("SELECT COUNT(*) c FROM users WHERE status='approved' AND role='player'", one=True)['c'],
        'rejected': q("SELECT COUNT(*) c FROM users WHERE status='rejected'", one=True)['c'],
        'characters': q("SELECT COUNT(*) c FROM characters", one=True)['c'],
        'clans': q("SELECT COUNT(*) c FROM clans", one=True)['c'],
    }
    return render_template('admin/home.html', stats=stats)

# ── 管理后台:待审核账号队列 ───────────────────────────────────────────────────────

@app.route('/admin/pending_users')
@admin_required
def admin_pending_users():
    status_filter = request.args.get('status', 'pending')
    if status_filter == 'all':
        users = q("SELECT * FROM users WHERE role='player' ORDER BY created_ts DESC")
    else:
        users = q("SELECT * FROM users WHERE role='player' AND status=? ORDER BY created_ts DESC", (status_filter,))
    return render_template('admin/pending_users.html', users=users, status_filter=status_filter)

@app.route('/admin/users/<int:uid>/approve', methods=['POST'])
@admin_required
def admin_approve_user(uid):
    run("UPDATE users SET status='approved' WHERE id=?", (uid,))
    log_admin('approve_user', 'user', uid)
    return redirect(url_for('admin_pending_users'))

@app.route('/admin/users/<int:uid>/reject', methods=['POST'])
@admin_required
def admin_reject_user(uid):
    run("UPDATE users SET status='rejected' WHERE id=?", (uid,))
    log_admin('reject_user', 'user', uid)
    return redirect(url_for('admin_pending_users'))

# ── 管理后台:角色列表 / 详情编辑 ─────────────────────────────────────────────────

@app.route('/admin/characters')
@admin_required
def admin_characters():
    chars = q("""SELECT characters.*, users.username FROM characters
                 JOIN users ON users.id = characters.user_id
                 ORDER BY characters.created_ts DESC""")
    return render_template('admin/characters.html', chars=chars, stage_display_name=stage_display_name)

@app.route('/admin/characters/<int:char_id>', methods=['GET', 'POST'])
@admin_required
def admin_character_detail(char_id):
    char = q("SELECT characters.*, users.username FROM characters "
             "JOIN users ON users.id = characters.user_id WHERE characters.id=?", (char_id,), one=True)
    if not char:
        flash('角色不存在', 'error')
        return redirect(url_for('admin_characters'))

    if request.method == 'POST':
        stage_index = max(0, min(MAX_STAGE_INDEX, request.form.get('stage_index', type=int) or 0))
        yao_power = max(0, request.form.get('yao_power', type=int) or 0)
        humanoid_value = max(0, min(100, request.form.get('humanoid_value', type=int) or 0))
        humanity = max(0, min(100, request.form.get('humanity', type=int) or 0))
        run("UPDATE characters SET stage_index=?, yao_power=?, humanoid_value=?, humanity=? WHERE id=?",
            (stage_index, yao_power, humanoid_value, humanity, char_id))
        check_achievements(char_id)
        log_admin('edit_character', 'character', char_id,
                  f"stage={stage_index} yao_power={yao_power} humanoid={humanoid_value} humanity={humanity}")
        flash('已保存', 'ok')
        return redirect(url_for('admin_character_detail', char_id=char_id))

    stage = stage_by_index(char['stage_index'])
    return render_template('admin/character_detail.html', char=char, stage=stage, stages=STAGES,
                            species_info=SPECIES.get(char['species'], {}))

# ── 管理后台:邀请码 ──────────────────────────────────────────────────────────────

@app.route('/admin/invite_codes', methods=['GET', 'POST'])
@admin_required
def admin_invite_codes():
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        max_uses = request.form.get('max_uses', type=int) or 1
        expire_days = request.form.get('expire_days', type=int) or 0
        expires_ts = now_ts() + expire_days * 86400 if expire_days else 0
        if code:
            run("INSERT INTO invite_codes (code,max_uses,used_count,expires_ts,created_ts) VALUES (?,?,0,?,?)",
                (code, max_uses, expires_ts, now_ts()))
            log_admin('create_invite_code', 'invite_code', None, code)
        return redirect(url_for('admin_invite_codes'))
    codes = q("SELECT * FROM invite_codes ORDER BY created_ts DESC")
    return render_template('admin/invite_codes.html', codes=codes)

# ── 管理后台:礼包码 ──────────────────────────────────────────────────────────────

@app.route('/admin/gift_codes', methods=['GET', 'POST'])
@admin_required
def admin_gift_codes():
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        yao_power = request.form.get('yao_power', type=int) or 0
        max_uses = request.form.get('max_uses', type=int) or 1
        expire_days = request.form.get('expire_days', type=int) or 0
        expires_ts = now_ts() + expire_days * 86400 if expire_days else 0
        if code:
            run("INSERT INTO gift_codes (code,reward_json,max_uses,used_count,expires_ts,created_ts) "
                "VALUES (?,?,?,0,?,?)",
                (code, json.dumps({'yao_power': yao_power}), max_uses, expires_ts, now_ts()))
            log_admin('create_gift_code', 'gift_code', None, code)
        return redirect(url_for('admin_gift_codes'))
    codes = q("SELECT * FROM gift_codes ORDER BY created_ts DESC")
    return render_template('admin/gift_codes.html', codes=codes)

# ── 管理后台:操作日志 ────────────────────────────────────────────────────────────

@app.route('/admin/logs')
@admin_required
def admin_logs_page():
    logs = q("""SELECT admin_logs.*, users.username admin_name FROM admin_logs
                LEFT JOIN users ON users.id = admin_logs.admin_id
                ORDER BY admin_logs.created_ts DESC LIMIT 200""")
    return render_template('admin/logs.html', logs=logs)

# ── 管理后台:化身登录(排障用) ────────────────────────────────────────────────────

@app.route('/admin/impersonate/<int:char_id>')
@admin_required
def admin_impersonate(char_id):
    char = q("SELECT characters.*, users.id user_id, users.username FROM characters "
             "JOIN users ON users.id = characters.user_id WHERE characters.id=?", (char_id,), one=True)
    if not char:
        flash('角色不存在', 'error')
        return redirect(url_for('admin_characters'))
    log_admin('impersonate', 'character', char_id, char['username'])
    S['real_admin_uid'] = S['uid']
    S['uid'] = char['user_id']; S['uname'] = char['username']; S['role'] = 'player'
    return redirect(url_for('home'))

@app.route('/admin/unimpersonate')
def admin_unimpersonate():
    admin_uid = S.get('real_admin_uid')
    if not admin_uid:
        return redirect(url_for('login'))
    admin_user = q("SELECT * FROM users WHERE id=?", (admin_uid,), one=True)
    S.pop('real_admin_uid', None)
    S['uid'] = admin_user['id']; S['uname'] = admin_user['username']; S['role'] = 'admin'
    return redirect(url_for('admin_home'))

# ── 角色数值快照(供 run.py 后台线程定时调用,用于后续做趋势图) ──────────────────────

def snapshot_tick():
    chars = q("SELECT id, stage_index, yao_power, humanoid_value, humanity FROM characters")
    for c in chars:
        run("INSERT INTO char_snapshots (char_id,stage_index,yao_power,humanoid_value,humanity,created_ts) "
            "VALUES (?,?,?,?,?,?)",
            (c['id'], c['stage_index'], c['yao_power'], c['humanoid_value'], c['humanity'], now_ts()))

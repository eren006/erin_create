"""Standalone exploration: authoritative quotas/draws in SQLite; inventory via existing bot queue."""
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from datetime import datetime
from flask import Blueprint, abort, redirect, render_template, request, session, url_for
from itsdangerous import URLSafeTimedSerializer, BadSignature


def init_schema(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS exploration_settings (
      show_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0,
      daily_limit INTEGER NOT NULL DEFAULT 3, reset_mode TEXT NOT NULL DEFAULT 'game');
    CREATE TABLE IF NOT EXISTS exploration_limits (
      show_id INTEGER NOT NULL, role TEXT NOT NULL, daily_limit INTEGER NOT NULL,
      PRIMARY KEY(show_id,role));
    CREATE TABLE IF NOT EXISTS exploration_grants (
      id INTEGER PRIMARY KEY AUTOINCREMENT, show_id INTEGER NOT NULL, role TEXT NOT NULL,
      amount INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0, day_key TEXT NOT NULL DEFAULT '',
      note TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL, request_key TEXT NOT NULL,
      UNIQUE(show_id,request_key));
    CREATE INDEX IF NOT EXISTS exploration_grants_owner ON exploration_grants(show_id,role);
    CREATE TABLE IF NOT EXISTS exploration_places (
      id INTEGER PRIMARY KEY AUTOINCREMENT, show_id INTEGER NOT NULL, name TEXT NOT NULL,
      description TEXT NOT NULL DEFAULT '', map_name TEXT NOT NULL DEFAULT '',
      x INTEGER NOT NULL DEFAULT 50, y INTEGER NOT NULL DEFAULT 50, enabled INTEGER NOT NULL DEFAULT 1);
    CREATE INDEX IF NOT EXISTS exploration_places_show ON exploration_places(show_id);
    CREATE TABLE IF NOT EXISTS exploration_drops (
      id INTEGER PRIMARY KEY AUTOINCREMENT, show_id INTEGER NOT NULL, place_id INTEGER NOT NULL,
      kind TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL DEFAULT '',
      quantity INTEGER NOT NULL DEFAULT 1, weight INTEGER NOT NULL DEFAULT 1, enabled INTEGER NOT NULL DEFAULT 1);
    CREATE INDEX IF NOT EXISTS exploration_drops_place ON exploration_drops(show_id,place_id);
    CREATE TABLE IF NOT EXISTS exploration_visits (
      id INTEGER PRIMARY KEY AUTOINCREMENT, show_id INTEGER NOT NULL, role TEXT NOT NULL,
      day_key TEXT NOT NULL, place_id INTEGER NOT NULL, place_name TEXT NOT NULL,
      drop_id INTEGER, kind TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL DEFAULT '',
      quantity INTEGER NOT NULL DEFAULT 1, grant_id INTEGER, op_id INTEGER,
      request_key TEXT NOT NULL, created_at INTEGER NOT NULL,
      UNIQUE(show_id,role,request_key));
    CREATE INDEX IF NOT EXISTS exploration_visits_owner ON exploration_visits(show_id,role,day_key);
    ''')


def register_exploration(app, api):
    bp = Blueprint('explore', __name__)
    db_get = api['get_db']

    def csrf():
        if not session.get('explore_csrf'):
            session['explore_csrf'] = secrets.token_urlsafe(24)
        return session['explore_csrf']

    def check_csrf():
        if not hmac.compare_digest(request.form.get('csrf', ''), session.get('explore_csrf', '') or '-'):
            abort(400, description='页面过期了，刷新后再试')

    def signer():
        return URLSafeTimedSerializer(app.secret_key, salt='exploration-auth')

    def who():
        try:
            code = signer().loads(request.cookies.get('explore_auth', ''), max_age=30 * 86400)
        except BadSignature:
            return None
        if not isinstance(code, str):
            return None
        owner = api['_phone_code_owner'](db_get(), code)
        if not owner or owner[1] == api['PHONE_ADMIN']:
            return None
        sync = api['_phone_sync_row'](db_get(), owner[0])
        if sync and owner[1] not in api['_phone_roster'](sync):
            return None
        return owner

    def settings(db, sid):
        row = db.execute('SELECT * FROM exploration_settings WHERE show_id=?', (sid,)).fetchone()
        return dict(row) if row else dict(show_id=sid, enabled=0, daily_limit=3, reset_mode='game')

    def day(db, sid, cfg):
        if cfg['reset_mode'] == 'calendar':
            return 'date:' + datetime.now(api['TZ_BEIJING']).strftime('%Y-%m-%d')
        sync = api['_phone_sync_row'](db, sid)
        label = str((sync['snap'].get('game_day') if sync else '') or '').strip()
        return 'game:' + label if label else ''

    def quota(db, sid, role, cfg, day_key):
        row = db.execute('SELECT daily_limit FROM exploration_limits WHERE show_id=? AND role=?', (sid, role)).fetchone()
        limit = row['daily_limit'] if row else cfg['daily_limit']
        used = db.execute('SELECT COUNT(*) FROM exploration_visits WHERE show_id=? AND role=? AND day_key=? AND grant_id IS NULL', (sid, role, day_key)).fetchone()[0]
        extra = db.execute('SELECT COALESCE(SUM(amount-used),0) FROM exploration_grants WHERE show_id=? AND role=? AND (day_key=? OR day_key=\'\')', (sid, role, day_key)).fetchone()[0]
        return dict(limit=limit, used=used, daily=max(0, limit-used), extra=extra, total=max(0, limit-used)+extra)

    def items(db, sid):
        # The registry snapshot is authoritative; old inventory snapshots may contain removed items.
        catalog = api['_plugin_status'](db, sid).get('catalog') or []
        return sorted({r['name'] for r in catalog if isinstance(r, dict) and isinstance(r.get('name'), str)
                       and r.get('type') in ('物品', '道具', '装备')})

    def integer(name, minimum, maximum, default=None):
        try:
            value = int(request.form.get(name, default))
            if not minimum <= value <= maximum:
                raise ValueError
            return value
        except (ValueError, TypeError):
            raise ValueError(f'{name} 要填 {minimum}～{maximum} 的整数')

    def text(name, length, required=False):
        value = request.form.get(name, '').strip()
        if len(value) > length or (required and not value):
            raise ValueError('请填完整，文字也不要太长')
        return value

    def admin_scope():
        sid = api['get_show_id']()
        row = db_get().execute('SELECT id FROM shows WHERE id=? AND tenant_id=?', (sid, api['current_tenant_id']())).fetchone()
        if not row:
            abort(404)
        return sid

    def context(**kw):
        return dict(csrf=csrf(), flash=session.pop('explore_flash', None), **kw)

    @bp.before_request
    def https():
        if request.path.startswith('/explore') and not api['_phone_local']() and request.scheme == 'http':
            return redirect(request.url.replace('http://', 'https://', 1), code=301)

    @bp.after_request
    def private(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        return response

    @bp.route('/explore', methods=['GET', 'POST'])
    def entry():
        error = None
        if request.method == 'POST':
            check_csrf()
            if api['_phone_ip_locked']():
                return render_template('exploration.html', **context(view='entry', error='输错太多次了，15 分钟后再试')), 429
            code = request.form.get('code', '').strip().upper()
            owner = api['_phone_code_owner'](db_get(), code)
            if owner and owner[1] != api['PHONE_ADMIN']:
                session['explore_csrf'] = secrets.token_urlsafe(24)
                response = redirect(url_for('explore.index'))
                response.set_cookie('explore_auth', signer().dumps(code), max_age=30*86400,
                                    httponly=True, secure=not api['_phone_local'](), samesite='Lax', path='/explore')
                return response
            api['_phone_note_fail']()
            error = '激活码不对，或者这一季已经结束了'
        elif who():
            return redirect(url_for('explore.index'))
        return render_template('exploration.html', **context(view='entry', error=error))

    @bp.route('/explore/logout', methods=['POST'])
    def logout():
        check_csrf()
        response = redirect(url_for('explore.entry'))
        response.delete_cookie('explore_auth', path='/explore')
        session.pop('explore_csrf', None)
        return response

    def visits(db, sid, role=None, limit=60):
        clause, params = (' AND v.role=?', [role]) if role else ('', [])
        return [dict(r) for r in db.execute('''SELECT v.*, o.done, o.ok, o.result FROM exploration_visits v
            LEFT JOIN phone_admin_ops o ON o.id=v.op_id AND o.show_id=v.show_id
            WHERE v.show_id=?''' + clause + ' ORDER BY v.id DESC LIMIT ?', [sid] + params + [limit])]

    @bp.route('/explore/me')
    def index():
        owner = who()
        if not owner:
            return redirect(url_for('explore.entry'))
        sid, role = owner
        db = db_get(); cfg = settings(db, sid); day_key = day(db, sid, cfg)
        places = [dict(r) for r in db.execute('SELECT id,name,description,map_name,x,y FROM exploration_places WHERE show_id=? AND enabled=1 ORDER BY id', (sid,))] if cfg['enabled'] else []
        all_maps = api['_get_maps'](db, sid)
        maps = {p['map_name']: all_maps[p['map_name']] for p in places if p['map_name'] in all_maps}
        clues = [dict(r) for r in db.execute("SELECT * FROM exploration_visits WHERE show_id=? AND role=? AND kind='clue' ORDER BY id DESC", (sid, role))]
        return render_template('exploration.html', **context(view='player', owner=role, cfg=cfg,
            places=places, maps=maps, clues=clues, quota=quota(db, sid, role, cfg, day_key),
            day_label=day_key.partition(':')[2], history=visits(db, sid, role), request_key=secrets.token_urlsafe(24)))

    @bp.route('/explore/visit/<int:pid>', methods=['POST'])
    def visit(pid):
        owner = who()
        if not owner:
            return redirect(url_for('explore.entry'))
        check_csrf()
        sid, role = owner
        db = db_get()
        try:
            request_key = text('request_key', 100, True)
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT id FROM exploration_visits WHERE show_id=? AND role=? AND request_key=?', (sid, role, request_key)).fetchone():
                db.rollback()
                return redirect(url_for('explore.index') + '#history')
            cfg = settings(db, sid); day_key = day(db, sid, cfg)
            place = db.execute('SELECT * FROM exploration_places WHERE id=? AND show_id=? AND enabled=1', (pid, sid)).fetchone()
            if not cfg['enabled'] or not place:
                raise ValueError('这里还没有开放踩点')
            if not day_key:
                raise ValueError('等管理设置游戏日后，再来走走吧')
            q = quota(db, sid, role, cfg, day_key)
            if not q['total']:
                raise ValueError('今天的次数用完了，歇一会儿吧')
            drops = [dict(r) for r in db.execute('SELECT * FROM exploration_drops WHERE show_id=? AND place_id=? AND enabled=1 ORDER BY id', (sid, pid))]
            if not drops:
                raise ValueError('这里还在布置，暂时不能踩点')
            # Do not silently substitute a different prize when the bot/registry is unavailable.
            if any(r['kind'] == 'item' for r in drops):
                plugin = api['_plugin_status'](db, sid)
                if not plugin.get('can') or not plugin.get('fresh'):
                    raise ValueError('背包暂时连不上，稍后再来；这次不扣次数')
                if any(r['kind'] == 'item' and r['title'] not in items(db, sid) for r in drops):
                    raise ValueError('这里的物品正在调整，稍后再来；这次不扣次数')
            owned = {r[0] for r in db.execute("SELECT drop_id FROM exploration_visits WHERE show_id=? AND role=? AND kind='clue'", (sid, role))}
            eligible = [r for r in drops if r['kind'] != 'clue' or r['id'] not in owned]
            selected = dict(id=None, kind='empty', title='风经过这里', content='熟悉的角落，今天没有新的发现。', quantity=1)
            if eligible:
                ticket = secrets.randbelow(sum(r['weight'] for r in eligible))
                for drop in eligible:
                    ticket -= drop['weight']
                    if ticket < 0:
                        selected = drop; break
            now = int(time.time()*1000); grant_id = None; op_id = None
            if not q['daily']:
                grant = db.execute("SELECT id FROM exploration_grants WHERE show_id=? AND role=? AND used<amount AND (day_key=? OR day_key='') ORDER BY CASE WHEN day_key='' THEN 1 ELSE 0 END,id LIMIT 1", (sid, role, day_key)).fetchone()
                grant_id = grant['id']
                db.execute('UPDATE exploration_grants SET used=used+1 WHERE id=?', (grant_id,))
            if selected['kind'] == 'item':
                op_id = db.execute("INSERT INTO phone_admin_ops(show_id,role,kind,name,value,created_at) VALUES (?,?,'item',?,?,?)", (sid, role, selected['title'], str(selected['quantity']), now)).lastrowid
            db.execute('''INSERT INTO exploration_visits(show_id,role,day_key,place_id,place_name,drop_id,kind,title,content,quantity,grant_id,op_id,request_key,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (sid, role, day_key, pid, place['name'], selected['id'], selected['kind'], selected['title'], selected['content'], selected['quantity'], grant_id, op_id, request_key, now))
            db.commit()
            session['explore_flash'] = '发现了「' + selected['title'] + '」' + ('，已经收进线索板。' if selected['kind']=='clue' else ('，正在送入背包。' if selected['kind']=='item' else '。'))
        except ValueError as e:
            db.rollback(); session['explore_flash'] = str(e)
        except Exception:
            db.rollback(); raise
        return redirect(url_for('explore.index') + '#history')

    @bp.route('/admin/exploration', methods=['GET', 'POST'])
    @api['require_admin']
    def admin():
        sid = admin_scope(); db = db_get()
        if request.method == 'POST':
            check_csrf()
            try:
                db.execute('BEGIN IMMEDIATE')
                action = request.form.get('action')
                if action == 'settings':
                    mode = request.form.get('reset_mode')
                    if mode not in ('game', 'calendar'): raise ValueError('请选择重置方式')
                    db.execute('INSERT INTO exploration_settings(show_id,enabled,daily_limit,reset_mode) VALUES(?,?,?,?) ON CONFLICT(show_id) DO UPDATE SET enabled=excluded.enabled,daily_limit=excluded.daily_limit,reset_mode=excluded.reset_mode', (sid, int(request.form.get('enabled')=='on'), integer('daily_limit',0,100), mode))
                elif action == 'limit':
                    role = text('role',100,True)
                    if role not in api['_admin_role_list'](db,sid): raise ValueError('请选择本季角色')
                    if request.form.get('daily_limit','').strip() == '':
                        db.execute('DELETE FROM exploration_limits WHERE show_id=? AND role=?',(sid,role))
                    else:
                        db.execute('INSERT INTO exploration_limits VALUES(?,?,?) ON CONFLICT(show_id,role) DO UPDATE SET daily_limit=excluded.daily_limit',(sid,role,integer('daily_limit',0,100)))
                elif action == 'grant':
                    role = text('role',100,True)
                    if role not in api['_admin_role_list'](db,sid): raise ValueError('请选择本季角色')
                    expiry = request.form.get('expiry')
                    if expiry not in ('today','forever'): raise ValueError('请选择有效期')
                    day_key = day(db,sid,settings(db,sid)) if expiry=='today' else ''
                    if expiry=='today' and not day_key: raise ValueError('还没有游戏日，暂时不能发当日次数')
                    db.execute('INSERT OR IGNORE INTO exploration_grants(show_id,role,amount,day_key,note,created_at,request_key) VALUES(?,?,?,?,?,?,?)', (sid,role,integer('amount',1,100),day_key,text('note',200),int(time.time()*1000),text('request_key',100,True)))
                elif action == 'place':
                    pid = integer('place_id',0,2147483647,0)
                    if pid and not db.execute('SELECT id FROM exploration_places WHERE id=? AND show_id=?',(pid,sid)).fetchone(): abort(404)
                    map_name = text('map_name',100)
                    if map_name and map_name not in api['_get_maps'](db,sid): raise ValueError('这张地图已不存在，请重新选择')
                    values = (text('name',40,True),text('description',500),map_name,integer('x',5,95,50),integer('y',5,95,50),int(request.form.get('enabled')=='on'))
                    if pid:
                        db.execute('UPDATE exploration_places SET name=?,description=?,map_name=?,x=?,y=?,enabled=? WHERE id=? AND show_id=?', values+(pid,sid))
                    else:
                        db.execute('INSERT INTO exploration_places(name,description,map_name,x,y,enabled,show_id) VALUES(?,?,?,?,?,?,?)',values+(sid,))
                elif action == 'drop':
                    pid = integer('place_id',1,2147483647)
                    if not db.execute('SELECT id FROM exploration_places WHERE id=? AND show_id=?',(pid,sid)).fetchone(): abort(404)
                    kind = request.form.get('kind')
                    if kind not in ('item','clue','empty'): raise ValueError('请选择掉落类型')
                    title = text('item',100,True) if kind=='item' else text('title',80,True)
                    if kind=='item' and title not in items(db,sid): raise ValueError('物品必须从已注册物品中选择')
                    db.execute('INSERT INTO exploration_drops(show_id,place_id,kind,title,content,quantity,weight) VALUES(?,?,?,?,?,?,?)', (sid,pid,kind,title,text('content',2000),integer('quantity',1,9999,1) if kind=='item' else 1,integer('weight',1,10000,1)))
                elif action == 'drop_toggle':
                    db.execute('UPDATE exploration_drops SET enabled=1-enabled WHERE id=? AND show_id=?',(integer('drop_id',1,2147483647),sid))
                else:
                    raise ValueError('不认识这项操作')
                db.commit(); session['explore_flash']='已保存'
            except ValueError as e:
                db.rollback(); session['explore_flash']=str(e)
            except Exception:
                db.rollback(); raise
            return redirect(url_for('explore.admin'))
        cfg=settings(db,sid); day_key=day(db,sid,cfg)
        places=[dict(r) for r in db.execute('SELECT * FROM exploration_places WHERE show_id=? ORDER BY id',(sid,))]
        for p in places:
            p['drops']=[dict(r) for r in db.execute('SELECT * FROM exploration_drops WHERE show_id=? AND place_id=? ORDER BY id',(sid,p['id']))]
        roles=api['_admin_role_list'](db,sid)
        limits={r['role']:r['daily_limit'] for r in db.execute('SELECT * FROM exploration_limits WHERE show_id=?',(sid,))}
        grants=[dict(r) for r in db.execute('SELECT * FROM exploration_grants WHERE show_id=? ORDER BY id DESC LIMIT 30',(sid,))]
        return render_template('exploration_admin.html',**context(cfg=cfg,places=places,roles=roles,limits=limits,grants=grants,
            balances={r:quota(db,sid,r,cfg,day_key) for r in roles},items=items(db,sid),maps=api['_get_maps'](db,sid),
            history=visits(db,sid),request_key=secrets.token_urlsafe(24),day_label=day_key.partition(':')[2]))

    app.register_blueprint(bp)

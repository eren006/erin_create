import os
import json
import uuid
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = 'cr-changri-sys-8f3k2p9x-2024'

ADMIN_USER = 'changri'
_DEFAULT_HASH = generate_password_hash('marcusra9')


def get_password_hash():
    cfg = load_config()
    return cfg.get('password_hash', _DEFAULT_HASH)


def set_password_hash(new_hash):
    cfg = load_config()
    cfg['password_hash'] = new_hash
    save_config(cfg)

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE, 'data', 'submissions.json')
CONFIG_FILE = os.path.join(BASE, 'data', 'config.json')

DEFAULT_CUSTOM_FIELDS = [
    {'id': 'drama_records', 'label': '戏录', 'type': 'textarea',
     'placeholder': '在此粘贴或填写您的戏录内容……', 'size': 'long'},
    {'id': 'notes', 'label': '备注', 'type': 'textarea',
     'placeholder': '其他需要补充的信息……', 'size': 'short'},
    {'id': 'character_type', 'label': '人物类型', 'type': 'textarea',
     'placeholder': '例如：主角、配角、NPC……', 'size': 'short'},
]


def load():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except Exception:
            return []


def save(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_config():
    if not os.path.exists(CONFIG_FILE):
        cfg = {'custom_fields': DEFAULT_CUSTOM_FIELDS}
        save_config(cfg)
        return cfg
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except Exception:
            return {'custom_fields': DEFAULT_CUSTOM_FIELDS}


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def group_hours(hours):
    if not hours:
        return []
    nums = sorted(set(int(h.split(':')[0]) for h in hours))
    groups = []
    start = nums[0]
    prev = nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
        else:
            end = prev + 1
            groups.append(f'{start:02d}:00–{end:02d}:00')
            start = prev = n
    end = prev + 1
    if end >= 24:
        groups.append(f'{start:02d}:00–次日00:00')
    else:
        groups.append(f'{start:02d}:00–{end:02d}:00')
    return groups


app.jinja_env.globals['group_hours'] = group_hours


@app.route('/')
def index():
    cfg = load_config()
    return render_template('register.html', custom_fields=cfg['custom_fields'])


@app.route('/submit', methods=['POST'])
def submit():
    try:
        online_time = json.loads(request.form.get('online_time_data', '[]'))
    except Exception:
        online_time = []

    entry = {
        'id': str(uuid.uuid4()),
        'qq': request.form.get('qq', '').strip(),
        'online_time': online_time,
        'online_time_note': request.form.get('online_time_note', '').strip(),
        'arc_length': request.form.get('arc_length', '').strip(),
        'submitted_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'status': None,
        'admin_note': '',
    }
    cfg = load_config()
    for field in cfg['custom_fields']:
        entry[field['id']] = request.form.get(field['id'], '').strip()

    entries = load()
    entries.append(entry)
    save(entries)
    return render_template('success.html')


@app.route('/admin/login', methods=['GET', 'POST'])
def login():
    if session.get('admin'):
        return redirect(url_for('admin'))
    error = None
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USER and \
           check_password_hash(get_password_hash(), request.form.get('password', '')):
            session['admin'] = True
            return redirect(url_for('admin'))
        error = '账号或密码错误'
    return render_template('login.html', error=error)


@app.route('/admin/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/admin')
def admin():
    if not session.get('admin'):
        return redirect(url_for('login'))
    entries = load()
    cfg = load_config()
    entries.sort(key=lambda x: x.get('submitted_at', ''), reverse=True)
    stats = {
        'total': len(entries),
        'interested': sum(1 for e in entries if e.get('status') == 'interested'),
        'pending': sum(1 for e in entries if e.get('status') == 'pending'),
        'pass': sum(1 for e in entries if e.get('status') == 'pass'),
        'unmarked': sum(1 for e in entries if not e.get('status')),
    }
    return render_template('admin.html', entries=entries, stats=stats,
                           custom_fields=cfg['custom_fields'])


@app.route('/admin/mark', methods=['POST'])
def mark():
    if not session.get('admin'):
        return jsonify(error='unauthorized'), 401
    data = request.get_json()
    eid, status = data.get('id'), data.get('status')
    entries = load()
    new_status = None
    for e in entries:
        if e['id'] == eid:
            e['status'] = None if e.get('status') == status else status
            new_status = e['status']
            break
    save(entries)
    return jsonify(ok=True, status=new_status)


@app.route('/admin/note', methods=['POST'])
def note():
    if not session.get('admin'):
        return jsonify(error='unauthorized'), 401
    data = request.get_json()
    entries = load()
    for e in entries:
        if e['id'] == data.get('id'):
            e['admin_note'] = data.get('note', '')
            break
    save(entries)
    return jsonify(ok=True)


@app.route('/admin/clear', methods=['POST'])
def clear():
    if not session.get('admin'):
        return jsonify(error='unauthorized'), 401
    data = request.get_json()
    days = data.get('days')
    if days is None:
        save([])
    else:
        cutoff = (datetime.now() - timedelta(days=int(days))).strftime('%Y-%m-%d %H:%M:%S')
        entries = [e for e in load() if e.get('submitted_at', '') >= cutoff]
        save(entries)
    return jsonify(ok=True)


@app.route('/admin/fields')
def admin_fields():
    if not session.get('admin'):
        return redirect(url_for('login'))
    cfg = load_config()
    return render_template('admin_fields.html', custom_fields=cfg['custom_fields'])


@app.route('/admin/fields/add', methods=['POST'])
def admin_fields_add():
    if not session.get('admin'):
        return jsonify(error='unauthorized'), 401
    data = request.get_json()
    label = data.get('label', '').strip()
    if not label:
        return jsonify(error='label required'), 400
    cfg = load_config()
    field_id = 'fld_' + uuid.uuid4().hex[:8]
    cfg['custom_fields'].append({
        'id': field_id,
        'label': label,
        'type': data.get('type', 'textarea'),
        'placeholder': data.get('placeholder', '').strip(),
        'size': data.get('size', 'short'),
    })
    save_config(cfg)
    return jsonify(ok=True, id=field_id)


@app.route('/admin/fields/delete', methods=['POST'])
def admin_fields_delete():
    if not session.get('admin'):
        return jsonify(error='unauthorized'), 401
    data = request.get_json()
    field_id = data.get('id')
    cfg = load_config()
    cfg['custom_fields'] = [f for f in cfg['custom_fields'] if f['id'] != field_id]
    save_config(cfg)
    return jsonify(ok=True)


@app.route('/admin/password', methods=['GET', 'POST'])
def admin_password():
    if not session.get('admin'):
        return redirect(url_for('login'))
    error = None
    success = False
    if request.method == 'POST':
        current = request.form.get('current', '')
        new_pw = request.form.get('new_password', '')
        confirm = request.form.get('confirm', '')
        if not check_password_hash(get_password_hash(), current):
            error = '当前密码错误'
        elif len(new_pw) < 6:
            error = '新密码至少需要 6 位'
        elif new_pw != confirm:
            error = '两次输入的新密码不一致'
        else:
            set_password_hash(generate_password_hash(new_pw))
            success = True
    return render_template('admin_password.html', error=error, success=success)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

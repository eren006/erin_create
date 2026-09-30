"""建一个网页手机「演示团账号」，给一个永久有效的体验激活码，用来看效果。
- 独立的团账号（username=phone_demo），跟真实团账号的数据完全隔开；
- 里面一个「演示季」：不设档期（永远算主档期）、一直是进行中，所以激活码一直有效；
- 几个假角色和示例短信/礼物/朋友圈/点歌；打开了网页发送，体验者可以直接发；
- 没有机器人，点歌不会发到任何 QQ 群。
重复执行不会重复建，只会把激活码再打印一遍。

用法（服务器上，rp_archive 目录）：venv/bin/python3 tools/seed_phone_demo.py
"""
import os, sys, json, secrets, sqlite3, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app as A
from werkzeug.security import generate_password_hash

A.init_db()  # 保证表都在（跟服务启动时做的一样）
db = sqlite3.connect(A.DB_PATH)
db.row_factory = sqlite3.Row

DEMO_ROLES = ["体验者", "林晚", "周屿", "沈知意"]

def _demo_codes(db, tid, sid):
    """演示季每个角色都有激活码（方便两边都登录试匿名对话、送礼等）；已有的不动。返回 {角色: 码}"""
    codes = {r["role_name"]: r["code"] for r in db.execute("SELECT role_name, code FROM phone_codes WHERE show_id=?", (sid,))}
    for role in DEMO_ROLES:
        if role not in codes:
            while True:
                code = "".join(secrets.choice(A._PHONE_CODE_ALPHABET) for _ in range(A._PHONE_CODE_LEN))
                if not db.execute("SELECT 1 FROM phone_codes WHERE code=? UNION SELECT 1 FROM phone_admin_codes WHERE code=?",
                                  (code, code)).fetchone():
                    break
            db.execute("INSERT INTO phone_codes (tenant_id, show_id, role_name, code, created_at) VALUES (?, ?, ?, ?, ?)",
                       (tid, sid, role, code, int(time.time() * 1000)))
            codes[role] = code
    db.commit()
    return codes

def _print_codes(codes):
    for role in DEMO_ROLES:
        print(f"  {role}：{codes[role]}  https://archive.changri.work/p/{codes[role]}")

def _demo_shop(db, tid, sid):
    """演示季的礼品店：几件预设礼物 + 快照里补上图鉴/货架字段（没有机器人，只能在这里写好）；已经有就不动"""
    if not db.execute("SELECT 1 FROM site_config WHERE show_id=? AND key='preset_gifts'", (sid,)).fetchone():
        gifts = {"#001": {"name": "玫瑰花束", "content": "一束盛开的红玫瑰，花瓣上还带着露水"},
                 "#002": {"name": "手工巧克力", "content": "一盒手工黑巧克力，每颗形状都不一样"},
                 "#003": {"name": "银怀表", "content": "古旧的银色怀表，指针停在三点十五"},
                 "#004": {"name": "星星瓶", "content": "装满纸折星星的玻璃瓶"},
                 "#005": {"name": "黑胶唱片", "content": "一张绝版的爵士黑胶"}}
        db.execute("INSERT INTO site_config (show_id, tenant_id, key, value) VALUES (?, ?, 'preset_gifts', ?)",
                   (sid, tid, json.dumps(gifts, ensure_ascii=False)))
    row = db.execute("SELECT snapshot FROM phone_sync WHERE show_id=?", (sid,)).fetchone()
    if row:
        snap = json.loads(row["snapshot"] or "{}")
        if "catalogs" not in snap:
            snap.update(catalogs={}, displays={}, shop={"refresh_hours": 1, "catalog_on_receive": True})
            snap["roster"] = [dict(r, npc=(r.get("name") == "沈知意")) for r in snap.get("roster", [])]
            db.execute("UPDATE phone_sync SET snapshot=? WHERE show_id=?", (json.dumps(snap, ensure_ascii=False), sid))
    db.commit()

def _demo_block(db, sid):
    """演示季也显示对话页「⋯」里的实名拉黑（没有机器人，操作只在网页上生效）"""
    row = db.execute("SELECT snapshot FROM phone_sync WHERE show_id=?", (sid,)).fetchone()
    if row:
        snap = json.loads(row["snapshot"] or "{}")
        if not snap.get("block_write"):
            snap["block_write"] = True
            db.execute("UPDATE phone_sync SET snapshot=? WHERE show_id=?", (json.dumps(snap, ensure_ascii=False), sid))
            db.commit()

def _demo_report(db, sid):
    """演示季的「时间线与统计」：没有机器人上报，放一份写死的示例报告；已经有就不动"""
    if db.execute("SELECT 1 FROM phone_reports WHERE show_id=? AND role='体验者'", (sid,)).fetchone():
        return
    rep = {"day": "D1",
           "counts": "📊 我的数量（D1）\n👤 我今天：私约 1 次｜电话 0 次｜短信 2 次｜礼物 1 次｜心愿 0 次\n🌐 全员今天：私约 4 次｜电话 2 次｜短信 11 次｜礼物 5 次｜心愿 1 次",
           "arc": "【体验者 的弧长】\n本人总平均：18分钟（24次，3场，含已结/未结）\n\n当前未结双嘉宾小群：\n私约5001：体验者x周屿 3v4（待你），本人平均15分钟（3次），你还没回：2h5m",
           "timeline": [
               {"day": "D0", "time": "21:00", "icon": "📞", "label": "电话", "tag": "已完结", "place": "", "partner": "林晚", "progress": "✍️ 最终段数：12v10", "wechat": False},
               {"day": "D1", "time": "20:00", "icon": "🎭", "label": "私约", "tag": "进行中 [⏳未回]", "place": "天台", "partner": "周屿", "progress": "✍️ 当前进度：3v4", "wechat": False},
               {"day": "D1", "time": "22:30", "icon": "🎭", "label": "私约", "tag": "待开启", "place": "琴房", "partner": "沈知意", "progress": "", "wechat": False},
               {"day": "微信群", "time": "长期", "icon": "💬", "label": "微信群", "tag": "长期活跃", "place": "夜宵搭子", "partner": "体验者、林晚、周屿", "progress": "", "wechat": True}],
           "pending": {"pending": [{"gid": "5001", "type": "私约", "elapsed_min": 125, "over": True}], "rel": ["林晚"],
                       "letters": [{"from": "沈知意", "wait_min": 42}]}}
    # 更新时间写成很远的将来：演示季没有机器人，不然 10 分钟后就一直显示「有一阵子没同步」
    db.execute("INSERT INTO phone_reports (show_id, role, data, updated_at) VALUES (?, '体验者', ?, ?)",
               (sid, json.dumps(rep, ensure_ascii=False), int(time.time() * 1000) + 10 * 365 * 86400 * 1000))
    db.commit()

def _demo_lovemail(db, tid, sid):
    """演示季的心动信：快照补上规则/次数/一封等派送的信（标成 demo，没有机器人也能投），再放几封已派送的往期；已经有就不动"""
    row = db.execute("SELECT snapshot FROM phone_sync WHERE show_id=?", (sid,)).fetchone()
    if not row:
        return
    snap = json.loads(row["snapshot"] or "{}")
    if "lovemail" in (snap.get("rules") or {}):
        return
    now = int(time.time() * 1000)
    snap["demo"] = True
    snap.setdefault("rules", {})["lovemail"] = {"enabled": True, "has_day": True, "window": None, "limit": 20, "delivery_time": "22:00"}
    snap["lovemail"] = {"counts": {"体验者": 1}, "pending": [
        {"from": "体验者", "to": "周屿", "content": "天台的风很大，下次记得多穿一件。", "signature": "路过的人",
         "game_day": snap.get("game_day") or "D1", "ts": now - 30 * 60000, "web_id": 0}]}
    db.execute("UPDATE phone_sync SET snapshot=? WHERE show_id=?", (json.dumps(snap, ensure_ascii=False), sid))
    for frm, to, content, sig, day, public, mins in [
        ("周屿", "体验者", "第一次见你是在排练厅门口，你抱着一摞谱子差点摔倒。那天之后我就一直在想，要怎么跟你说话才不显得奇怪。", "楼上的琴声", "D0", False, 1500),
        ("林晚", "体验者", "谢谢你昨天帮我占了座位！虽然你可能已经忘了。", "小熊软糖", "D0", True, 1490),
        ("沈知意", "体验者", "喵。", "猫", "D1", False, 60),
        ("体验者", "林晚", "你的晚霞照片拍得真好，能教教我吗？", "匿名", "D0", False, 1480)]:
        db.execute("INSERT INTO extra_events (show_id, tenant_id, session_id, type, from_role, to_role, content, extra_info, timestamp, game_day) "
                   "VALUES (?, ?, '', 'lovemail', ?, ?, ?, ?, ?, ?)",
                   (sid, tid, frm, to, content, json.dumps({"signature": sig, "isPublic": public}, ensure_ascii=False), now - mins * 60000, day))
    db.commit()

row = db.execute("SELECT id FROM tenants WHERE username='phone_demo'").fetchone()
if row:
    tid = row["id"]
    sid = db.execute("SELECT id FROM shows WHERE tenant_id=? AND is_current=1", (tid,)).fetchone()["id"]
    code = db.execute("SELECT code FROM phone_codes WHERE show_id=? AND role_name='体验者'", (sid,)).fetchone()["code"]
    arow = db.execute("SELECT code FROM phone_admin_codes WHERE show_id=?", (sid,)).fetchone()
    if not arow:  # 旧版脚本建的演示账号没有管理员码，补一个
        acode = "".join(secrets.choice(A._PHONE_CODE_ALPHABET) for _ in range(A._PHONE_CODE_LEN))
        db.execute("INSERT INTO phone_admin_codes (show_id, tenant_id, code, created_at) VALUES (?, ?, ?, ?)",
                   (sid, tid, acode, int(time.time() * 1000)))
        db.commit()
    else:
        acode = arow["code"]
    _demo_shop(db, tid, sid)
    _demo_lovemail(db, tid, sid)
    _demo_block(db, sid)
    _demo_report(db, sid)
    print("演示团账号已存在。各角色激活码（一直有效）：")
    _print_codes(_demo_codes(db, tid, sid))
    print(f"演示管理员手机码：{acode}\n入口：https://archive.changri.work/p/{acode}")
    sys.exit(0)

now = int(time.time() * 1000)
view_pw, admin_pw = secrets.token_urlsafe(9), secrets.token_urlsafe(9)
cur = db.execute("INSERT INTO tenants (username, view_password_hash, admin_password_hash, api_token, display_name, created_at) "
                 "VALUES ('phone_demo', ?, ?, ?, '网页手机演示', ?)",
                 (generate_password_hash(view_pw, method="pbkdf2:sha256"), generate_password_hash(admin_pw, method="pbkdf2:sha256"),
                  secrets.token_urlsafe(24), now))
tid = cur.lastrowid
cur = db.execute("INSERT INTO shows (tenant_id, name, is_current, created_at) VALUES (?, '演示季', 1, ?)", (tid, now))
sid = cur.lastrowid

roles = DEMO_ROLES
for r in roles:
    db.execute("INSERT INTO players (show_id, tenant_id, qq, role_name, sessions_count, total_replies, total_words, last_updated) "
               "VALUES (?, ?, ?, ?, 0, 0, 0, ?)", (sid, tid, "demo-" + r, r, now))
code = "".join(secrets.choice(A._PHONE_CODE_ALPHABET) for _ in range(A._PHONE_CODE_LEN))
db.execute("INSERT INTO phone_codes (tenant_id, show_id, role_name, code, created_at) VALUES (?, ?, '体验者', ?, ?)", (tid, sid, code, now))
acode = "".join(secrets.choice(A._PHONE_CODE_ALPHABET) for _ in range(A._PHONE_CODE_LEN))
db.execute("INSERT INTO phone_admin_codes (show_id, tenant_id, code, created_at) VALUES (?, ?, ?, ?)", (sid, tid, acode, now))

# 网页发送打开 + 一份规则快照（宽松的上限、没有混乱效果），没有机器人也能发
db.execute("INSERT INTO phone_settings (show_id, web_send) VALUES (?, 1)", (sid,))
snap = {"game_day": "D1", "roster": [{"name": r} for r in roles],
        "rules": {"sms_enabled": True, "gift_enabled": True, "chaos": {"dailyLimit": 20, "publicChance": 30},
                  "mail_cooldown_min": 0, "gift_cooldown_min": 0, "gift_daily_limit": 20, "gift_mode": 0,
                  "sms_public": True, "gift_public": True, "gift_public_chance": 30},
        "counts": {"sms": {}, "gift": {}}, "last": {"sms": {}, "gift": {}}}
db.execute("INSERT INTO phone_sync (show_id, tenant_id, snapshot, cursor, synced_at) VALUES (?, ?, ?, 0, ?)",
           (sid, tid, json.dumps(snap, ensure_ascii=False), now))

def ev(t, frm, to, content, info, minutes_ago, day="D1"):
    db.execute("INSERT INTO extra_events (show_id, tenant_id, session_id, type, from_role, to_role, content, extra_info, timestamp, game_day) "
               "VALUES (?, ?, '', ?, ?, ?, ?, ?, ?, ?)",
               (sid, tid, t, frm, to, content, json.dumps(info, ensure_ascii=False), now - minutes_ago * 60000, day))
def sms(frm, to, text, m, **kw):
    info = {"delivered": text, "signature": f"落款：{frm}"}; info.update(kw); ev("sms", frm, to, text, info, m)
sms("林晚", "体验者", "欢迎来到演示季～这里是网页手机，可以随便点点看。", 300)
sms("体验者", "林晚", "谢谢！这个界面好像真的手机", 290)
sms("林晚", "体验者", "右上角「外观」可以换主题色和头像，消息列表顶部有朋友圈和公开播报。", 285)
sms("周屿", "体验者", "晚上天台见？", 120)
ev("gift", "周屿", "体验者", "路过花店，觉得它像你", {"giftName": "一束洋桔梗", "isPublic": True, "intended_to": "体验者"}, 110)
sms("沈知意", "林晚", "今天的排练辛苦啦", 60, isPublic=True, public_show_effect=False)

db.execute("INSERT INTO moments (tenant_id, show_id, role_name, content, game_day, created_at) VALUES (?, ?, '林晚', ?, 'D1', ?)",
           (tid, sid, "第一次用朋友圈，今天的晚霞超好看 🌅", now - 200 * 60000))
mid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
db.execute("INSERT INTO moment_likes (moment_id, role_name, created_at) VALUES (?, '周屿', ?)", (mid, now - 190 * 60000))
db.execute("INSERT INTO moment_comments (moment_id, role_name, reply_to, content, created_at) VALUES (?, '周屿', '', '下次一起去看', ?)",
           (mid, now - 180 * 60000))
db.execute("""INSERT INTO song_requests (tenant_id, show_id, from_role, to_role, platform, song_id, song_mid, song_name, artists, album,
              cover, fee, message, source, game_day, created_at, announced) VALUES (?, ?, '周屿', '体验者', '163', 186016, '', '晴天',
              '周杰伦', '叶惠美', '', 0, '送你一首歌', 'web', 'D1', ?, 1)""", (tid, sid, now - 100 * 60000))
db.commit()
_demo_shop(db, tid, sid)
_demo_lovemail(db, tid, sid)
_demo_block(db, sid)
_demo_report(db, sid)
print("演示团账号已建好（跟真实数据完全隔开）。各角色激活码（一直有效）：")
_print_codes(_demo_codes(db, tid, sid))
print(f"体验激活码（一直有效）：{code}")
print(f"入口：https://archive.changri.work/p/{code}")
print(f"演示管理员手机码：{acode}（入口 https://archive.changri.work/p/{acode}）")
print(f"演示团账号后台：账号 phone_demo，查看密码 {view_pw}，后台密钥 {admin_pw}（只打印这一次，自己记下）")

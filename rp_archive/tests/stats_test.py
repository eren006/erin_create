"""网页手机「时间线与统计」：插件上报的报告（时间线/数量/弧长/待回）只给本人看、异常数据丢掉、过期提示；
互动统计按玩家视角算，收到的心动信不按寄信人统计（来信匿名）
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tests/stats_test.py ；全部通过时最后一行打印 ALL OK。
"""
import sys, os, re, json, sqlite3, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app as A
A.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
A.MODERATION_LOG = os.path.join(os.path.dirname(A.DB_PATH), "moderation.log")
A.init_db()
c = sqlite3.connect(A.DB_PATH); c.row_factory = sqlite3.Row
tok = c.execute("SELECT api_token, id FROM tenants").fetchone(); TOKEN, TID = tok["api_token"], tok["id"]
c.execute("UPDATE shows SET is_current=0"); c.execute("INSERT INTO shows (tenant_id,name,is_current) VALUES (?,'测试季',1)", (TID,))
SID = c.execute("SELECT id FROM shows WHERE name='测试季'").fetchone()[0]
for r, code in [("林晚", "LINWAN0001"), ("周屿", "ZHOUYU0001"), ("沈知意", "SHENZY0001")]:
    c.execute("INSERT INTO phone_codes (tenant_id,show_id,role_name,code) VALUES (?,?,?,?)", (TID, SID, r, code))
c.execute("INSERT INTO phone_admin_codes (tenant_id,show_id,code) VALUES (?,?,'ADMINCODE1')", (TID, SID))
c.commit()
app = A.app; app.testing = True
def ok(cond, msg):
    if not cond: raise AssertionError(msg)
def sync(reports=None):
    body = {"after": 0, "snapshot": {"game_day": "D2", "roster": [{"name": n} for n in ("林晚", "周屿", "沈知意")]}}
    if reports is not None:
        body["reports"] = reports
    r = app.test_client().post("/api/phone/sync", headers={"X-Archive-Token": TOKEN}, json=body)
    ok(r.status_code == 200, r.status_code)
def player(code):
    cl = app.test_client(); ok(cl.get("/p/" + code).status_code == 302, "enter"); return cl
def page(cl, view):
    return cl.get("/p/me/stats?view=" + view).get_data(as_text=True)
def event(t, frm, to, content, info, day="D2"):
    c.execute("INSERT INTO extra_events (show_id,tenant_id,session_id,type,from_role,to_role,content,extra_info,timestamp,game_day) "
              "VALUES (?,?,?,?,?,?,?,?,?,?)", (SID, TID, "", t, frm, to, content, json.dumps(info, ensure_ascii=False), int(time.time() * 1000), day))
    c.commit()

lin, zy = player("LINWAN0001"), player("ZHOUYU0001")

# 「我的」里有入口；还没有报告时提示去群里查
ok("时间线与统计" in lin.get("/p/me/library?view=profile").get_data(as_text=True), "entry")
_inb = lin.get("/p/me").get_data(as_text=True)
ok('class="timeline-btn"' in _inb and 'href="/p/me/stats?view=timeline"' in _inb, "inbox timeline entry")
sync()
ok("等机器人升级" in page(lin, "timeline") and "「时间线」" in page(lin, "timeline"), "no report yet")
ok("「我的待回」" in page(lin, "pending"), "no report pending hint")

REP = {"林晚": {"day": "D2", "counts": "📊 我的数量（D2）\n👤 我今天：私约 1 次", "arc": "【林晚 的弧长】\n本人总平均：12分钟",
                "timeline": [{"day": "D1", "time": "14:00", "icon": "📞", "label": "电话", "tag": "已完结", "place": "", "partner": "沈知意",
                              "progress": "✍️ 最终段数：12v10", "wechat": False},
                             {"day": "D2", "time": "20:00", "icon": "🎭", "label": "私约", "tag": "进行中 [⏳未回]", "place": "天台",
                              "partner": "周屿", "progress": "✍️ 当前进度：3v4", "wechat": False},
                             {"day": "微信群", "time": "长期", "icon": "💬", "label": "微信群", "tag": "长期活跃", "place": "夜宵",
                              "partner": "林晚、沈知意", "progress": "", "wechat": True}],
                "pending": {"pending": [{"gid": "5001", "type": "私约", "elapsed_min": 125, "over": True}], "rel": ["周屿"],
                            "letters": [{"from": "沈知意", "wait_min": 30}]}},
       "周屿": {"day": "D2", "counts": "📊 我的数量（D2）\n👤 周屿的数", "arc": "【周屿 的弧长】", "timeline": [], "pending": {}},
       "坏数据": "不是字典", "": {"day": "D2"}, "太大": {"arc": "长" * 70000}}
sync(REP)
ok(sorted(r[0] for r in c.execute("SELECT role FROM phone_reports")) == sorted(["林晚", "周屿"]), "bad reports dropped")
t = page(lin, "timeline")
tb = t.split('aria-label="时间线与统计"')[1]
ok(tb.index("<b>D1") < tb.index("<b>D2") < tb.index("<b>我的微信群") and "天台" in tb and "3v4" in tb and "12v10" in tb and "进行中 [⏳未回]" in tb, "timeline")
ok("D2 · " in t and "更新" in t, "updated time in header")
ok("私约 1 次" in page(lin, "counts") and "周屿的数" not in page(lin, "counts"), "counts only mine")
ok("本人总平均：12分钟" in page(lin, "arc"), "arc")
p = page(lin, "pending")
ok("已超时" in p and "群 5001" in p and "2h5m" in p and "查看关系线 周屿" in p and "沈知意 给你写了信" in p and "30m" in p, "pending")
ok("当前暂无行程安排" in page(zy, "timeline") and "没有等待你回复" in page(zy, "pending"), "empty report")
# 下一次同步不带报告：保留上一份
sync()
ok("天台" in page(lin, "timeline"), "kept when not sent")
# 过期提示
c.execute("UPDATE phone_reports SET updated_at=?", (int(time.time() * 1000) - 11 * 60 * 1000,)); c.commit()
ok("有一阵子没同步" in page(lin, "timeline"), "stale warning")

# 互动统计：按手机里看到的；心动信收到的只给总数，不按寄信人
event("sms", "林晚", "周屿", "hi", {"delivered": "hi", "signature": "落款：林晚"})
event("sms", "周屿", "林晚", "yo", {"delivered": "yo", "signature": "落款：周屿"})
event("gift", "周屿", "林晚", "花", {"giftName": "玫瑰"})
event("lovemail", "沈知意", "林晚", "喜欢你", {"signature": "猫"})
event("lovemail", "林晚", "周屿", "嗨", {"signature": "匿名"})
i = page(lin, "interact")
row = re.search(r'aria-label="与周屿的往来">(.*?)</article>', i, re.S).group(1)
ok("我发 <b>1</b>" in row and "我送 <b>0</b>" in row and "我收 <b>1</b>" in row and "我寄 <b>1</b>" in row, row)
ok('aria-label="与沈知意的往来"' not in i and "收到 1 封心动信" in i, "lovemail sender not revealed")
zi = page(zy, "interact")
ok('aria-label="与林晚的往来"' in zi and "收到 1 封心动信" in zi, "zy interact")
zrow = re.search(r'aria-label="与林晚的往来">(.*?)</article>', zi, re.S).group(1)
ok("我寄 <b>0</b>" in zrow, "zy did not send lovemail: " + zrow)

# 他人与他人之间的往来不能进入我的统计；URL 参数不能切换统计身份。
before = page(lin, "interact")
event("sms", "周屿", "沈知意", "别人的短信", {"signature": "落款：周屿"})
event("gift", "陌生甲", "陌生乙", "别人的礼物", {"giftName": "花"})
event("lovemail", "陌生甲", "陌生乙", "别人的心动信", {})
after = page(lin, "interact")
ok(before == after, "other peoples interactions must not change my page")
spoof = lin.get("/p/me/stats?view=interact&owner=周屿&role=周屿").get_data(as_text=True)
ok(spoof == after, "query parameters cannot switch interaction identity")
ok("林晚 · 本季与我的往来" in after and "我发 <b>" in after, "personal scope is explicit")

# 数量仅输出本人一行，保留自定义类型和真实零值；格式异常不能伪装成零。
ok(A._phone_personal_counts("👤 我今天：私约 1 次｜自定义约战 2 次|电话 0 次\n🌐 全员今天：私约 999 次") == [
    {"label":"私约", "count":1}, {"label":"自定义约战", "count":2}, {"label":"电话", "count":0}], "personal count parsing")
ok(A._phone_personal_counts("🌐 全员今天：私约 999 次") == [], "never use global counts")
ok(A._phone_personal_counts("我今天：私约 未知 次") == [], "unknown is not zero")
REP["林晚"]["counts"] += "\n🌐 全员今天：秘密活动 999 次"
sync(REP)
count_page = page(lin, "counts")
ok("秘密活动" not in count_page and "全员今天" not in count_page and "私约 1 次" in count_page, "global counts excluded from HTML")

# 公告只读本季、当前游戏日的全员汇总，个人行和其他季报告不会泄露。
daily = lin.get('/p/me/public/daily')
ok(daily.status_code == 200 and daily.json['text'] == '秘密活动 999 次', 'public aggregate only')
ok('林晚' not in daily.get_data(as_text=True) and '我今天' not in daily.get_data(as_text=True), 'no personal fields')
ok(app.test_client().get('/p/me/public/daily').status_code == 401, 'daily requires authentication')
c.execute('UPDATE phone_reports SET updated_at=?', (int(time.time()*1000)-11*60*1000,)); c.commit()
ok(lin.get('/p/me/public/daily').json['stale'], 'daily stale indicator')
REP['林晚']['day'] = 'D1'; sync(REP)
ok(lin.get('/p/me/public/daily').json['text'] == '今日统计等待同步', 'yesterday not presented as today')
ok('今日速报' in lin.get('/p/me/public').get_data(as_text=True), 'ticker rendered')

# 弧长兼容单双人场与中文/ASCII括号；无法识别的行保留，不猜测数值。
arc = A._phone_arc_view("【林晚 的弧长】\n本人总平均：18分钟（24次，3场，含已结/未结）\n当前未结双嘉宾小群：\n私约5001：林晚x周屿 3v4（待你），本人平均15分钟（3次），你还没回：2h5m\n当前未结多人场次：\n约战5002：林晚所在多人场（共3人），本人平均8分钟（2次，本场共3次），你已回复，等其他人；周屿未回：10m")
ok(arc['average'] == '18' and len(arc['sessions']) == 2, 'arc summary and sessions')
ok(arc['sessions'][0]['progress'] == '3v4' and arc['sessions'][0]['waiting'] == '你还没回：2h5m', 'arc pair fields')
ok('周屿未回：10m' in arc['sessions'][1]['waiting'], 'arc multiplayer waiting preserved')
ok(A._phone_arc_view('新格式原文')['notes'] == ['新格式原文'], 'arc unknown fallback')
ok(A._phone_arc_view('')['average'] is None, 'missing arc is not zero')

# 首页待回入口与轮询只反映本人；跨类型按等待时长排序，关系线无时长置后。
sync(REP)
pending = lin.get('/p/me/poll').json['pending']
ok(pending['count'] == 3 and pending['longest'] == '2 小时 5 分钟' and not pending['stale'], 'pending reminder totals')
inbox = lin.get('/p/me').get_data(as_text=True)
ok('待我回复 · 3 项' in inbox and '最长已等待 2 小时 5 分钟' in inbox, 'inbox reminder')
ok(zy.get('/p/me/poll').json['pending']['count'] == 0, 'reminder owner isolation')
ordered = A._phone_pending_items({'pending':{'pending':[{'elapsed_min':10}], 'letters':[{'wait_min':90}], 'rel':['周屿']}})
ok([r['kind'] for r in ordered] == ['letter','session','relation'], 'cross-type wait ordering')
c.execute('UPDATE phone_reports SET updated_at=? WHERE role=?',(int(time.time()*1000)-11*60*1000,'林晚'));c.commit()
ok(lin.get('/p/me/poll').json['pending']['stale'], 'stale reminder')
REP['林晚']['pending'] = {};sync(REP)
ok(lin.get('/p/me/poll').json['pending']['count'] == 0, 'cleared pending removed on next poll')

# 暂不提醒：从首页计数和待回列表里拿掉（收进「已暂不提醒」），可以恢复；对方再回一轮（开始时间变了）重新提醒
REP["林晚"]["pending"] = {"pending": [{"gid": "5001", "type": "私约", "elapsed_min": 125, "over": True, "since": 111}],
                         "rel": ["周屿"], "rel_n": {"周屿": 3}, "letters": [{"from": "沈知意", "wait_min": 30, "ts": 222}]}
sync(REP)
ok(lin.get('/p/me/poll').json['pending']['count'] == 3, 'before dismiss')
with lin.session_transaction() as s_: csrf_ = s_["phone_csrf"]
def dismiss(cl, key, action="dismiss", token=None):
    return cl.post("/p/me/pending/dismiss", data={"csrf": token or csrf_, "key": key, "action": action})
ok(dismiss(lin, "s:5001:111").status_code == 302, "dismiss redirect")
pend = lin.get('/p/me/poll').json['pending']
ok(pend['count'] == 2 and pend['longest'] == '30 分钟', pend)
pg = page(lin, "pending"); act = pg.split("已暂不提醒")[0]
ok("群 5001" not in act and "已暂不提醒 · 1 项" in pg and "恢复提醒" in pg, "moved to muted")
ok("待我回复 · 2 项" in lin.get("/p/me").get_data(as_text=True), "inbox count excludes muted")
dismiss(lin, "l:沈知意:222"); dismiss(lin, "r:周屿:3")
ok(lin.get('/p/me/poll').json['pending']['count'] == 0 and "其余的都设了暂不提醒" in page(lin, "pending"), "all muted")
dismiss(lin, "r:周屿:3", "restore")
ok(lin.get('/p/me/poll').json['pending']['count'] == 1, "restore")
# 对方又回了一轮：同一个群开始时间变了 → 新提醒；关系线多了一条 → 新提醒
REP["林晚"]["pending"]["pending"][0]["since"] = 999; REP["林晚"]["pending"]["rel_n"]["周屿"] = 4; sync(REP)
ok(lin.get('/p/me/poll').json['pending']['count'] == 2, "new round reminds again")
# 只影响自己；别人的 key 不会串；页面过期不生效
ok(zy.get('/p/me/poll').json['pending']['count'] == 0, "zy unaffected")
dismiss(lin, "l:沈知意:999", token="bad")
ok(c.execute("SELECT COUNT(*) FROM phone_pending_dismiss WHERE key='l:沈知意:999'").fetchone()[0] == 0, "csrf")
ok(c.execute("SELECT COUNT(DISTINCT role) FROM phone_pending_dismiss").fetchone()[0] == 1, "only own rows")
# 旧插件没报开始时间：按群认，照样能暂不提醒
REP["林晚"]["pending"] = {"pending": [{"gid": "5009", "type": "电话", "elapsed_min": 5, "over": False}]}; sync(REP)
dismiss(lin, "s:5009:"); ok(lin.get('/p/me/poll').json['pending']['count'] == 0, "legacy key")

# 管理身份、没登录
adm = app.test_client(); adm.get("/p/ADMINCODE1")
ok(adm.get("/p/me/stats").status_code == 302 and app.test_client().get("/p/me/stats").status_code == 302, "access")
print("ALL OK")

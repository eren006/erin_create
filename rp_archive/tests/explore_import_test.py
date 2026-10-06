"""探索踩点文本批量导入/导出：解析与错误行号、预览不写库、原子提交、同名处理（保位置/启用/沿用线索 id）、往返一致、次数导入、权限
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tests/explore_import_test.py ；全部通过时最后一行打印 ALL OK。
"""
import sys, os, json, sqlite3, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app as A
import explore as E
import explore_import as EI

tmp = tempfile.mkdtemp()
A.DB_PATH = os.path.join(tmp, "t.db")
E.EXPLORE_IMAGE_DIR = os.path.join(tmp, "explore_images")
A.init_db()
c = sqlite3.connect(A.DB_PATH); c.row_factory = sqlite3.Row
TID = c.execute("SELECT id FROM tenants").fetchone()["id"]
c.execute("UPDATE shows SET is_current=0")
c.execute("INSERT INTO shows (tenant_id,name,is_current) VALUES (?,'本季',1)", (TID,))
SID = c.execute("SELECT id FROM shows WHERE name='本季'").fetchone()[0]
for r, code in [("林晚", "LINWAN0001"), ("周屿", "ZHOUYU0001")]:
    c.execute("INSERT INTO phone_codes (tenant_id,show_id,role_name,code) VALUES (?,?,?,?)", (TID, SID, r, code))
c.execute("INSERT OR REPLACE INTO phone_sync (show_id, tenant_id, snapshot, cursor, synced_at) VALUES (?,?,?,?,?)",
          (SID, TID, json.dumps({"plugin": {"version": "1.10.9", "params": [], "catalog": [{"name": "钥匙", "type": "物品"}, {"name": "金币", "type": "货币"}, {"name": "旧地图", "type": "物品"}]}}), 0, int(time.time() * 1000)))
c.commit()
app = A.app; app.testing = True
def ok(cond, msg):
    if not cond: raise AssertionError(msg)

adm = app.test_client()
with adm.session_transaction() as s: s["tenant_id"] = TID; s["admin_logged_in"] = True; s["view_show_id"] = SID; s["phone_csrf"] = "tok"
H = {"X-CSRF": "tok"}
def imp(text, mode="preview", on_conflict="skip"):
    r = adm.post("/admin/explore/api/import", json={"text": text, "mode": mode, "on_conflict": on_conflict}, headers=H)
    return r.status_code, r.get_json()
def qimp(text, mode="preview"):
    r = adm.post("/admin/explore/api/quota_import", json={"text": text, "mode": mode}, headers=H)
    return r.status_code, r.get_json()
def counts():
    return tuple(c2.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("explore_maps", "explore_spots", "explore_quota", "explore_settings"))
c2 = sqlite3.connect(A.DB_PATH); c2.row_factory = sqlite3.Row
NAMES = {"钥匙", "金币", "旧地图"}

SAMPLE = """# 地图：学院
@图书馆 📚 x=20 y=28 | 安静得能听见翻页声。
线索 5 | 撕碎的信 | 信纸被撕成两半，只剩半句：「别让他知道……」
线索 3 | 借阅卡 | 最后一张借阅卡，签名被人刻意涂掉了。
物品 2 | 钥匙 ×1
物品 1 | 旧地图 ×3 | 压在书页里的一张泛黄地图。
空手 2 | 只有灰尘。

@钟楼 🔔 | 整点的钟声，听久了会数错。
线索 4 | 停摆的怀表 | 怀表停在 21:07，表盖内侧刻着 L.W.
空手 3
"""

# ── 1 解析 ──
p = EI.parse(SAMPLE, NAMES)
ok(p["ok"] and not p["errors"], f"sample ok {p['errors']}")
sp = p["maps"][0]["spots"]
ok(len(sp) == 2 and sp[0]["name"] == "图书馆" and sp[0]["icon"] == "📚" and sp[0]["x"] == 20 and sp[0]["has_pos"], "spot1")
ok(sp[1]["icon"] == "🔔" and not sp[1]["has_pos"] and sp[1]["x"] == 50, "spot2 no pos")
ok([d["kind"] for d in sp[0]["drops"]] == ["clue", "clue", "item", "item", "nothing"], "kinds")
ok(sp[0]["drops"][3]["qty"] == 3 and sp[0]["drops"][3]["text"].startswith("压在"), "item qty+text")
ok(sp[1]["drops"][1]["weight"] == 3 and sp[1]["drops"][1]["text"] == "", "nothing weight only")
q = EI.parse("""
// 注释
# 地图: 林  地
  ＠bad
#地图：A
@　地点　🌿　x＝1.5　y=99.5　｜　有换行\\n第二行
Clue 7 ｜ 标题 | 内容\\n第二行 | 还有 | 竖线
ITEM | 钥匙 x 2
item 9 | 金币 * 5 ｜ 一句话
nothing
""", NAMES)
ok(not q["ok"] and any("＠" in e["msg"] or "看不懂" in e["msg"] for e in q["errors"]), "fullwidth @ not accepted → error")
q = EI.parse("""
// 注释
# 地图: 林  地
@　地点　🌿　x＝1.5　y=99.5　｜　有换行\\n第二行
Clue 7 ｜ 标题 | 内容\\n第二行 | 还有 | 竖线
ITEM | 钥匙 x 2
item 9 | 金币 * 5 ｜ 一句话
nothing
""", NAMES)
ok(q["ok"], f"variants {q['errors']}")
s0 = q["maps"][0]["spots"][0]
ok(q["maps"][0]["name"] == "林  地" or q["maps"][0]["name"] == "林 地" or q["maps"][0]["name"].startswith("林"), "map name")
ok(s0["desc"] == "有换行\n第二行" and s0["x"] == 1.5 and s0["y"] == 99.5, "desc newline, fullwidth, coords")
d = s0["drops"]
ok(d[0]["weight"] == 7 and d[0]["title"] == "标题" and d[0]["text"] == "内容\n第二行 | 还有 | 竖线", "clue content keeps pipes/newline")
ok(d[1]["item"] == "钥匙" and d[1]["qty"] == 2 and d[1]["weight"] == 1, "item default weight, x qty")
ok(d[2]["item"] == "金币" and d[2]["qty"] == 5 and d[2]["text"] == "一句话", "item * qty fullwidth bar")
ok(d[3]["kind"] == "nothing" and d[3]["weight"] == 1, "nothing bare")
ok(EI.parse("# 地图：A\n@x 　📍 // 停用\n", NAMES)["ok"], "disabled comment ignored")

# ── 2 每种错误都带行号，一次给出多处 ──
BAD = """@没地图的地点
# 地图：学院
线索 1 | 孤儿 | 掉落行在地点之前
@图书馆 x=20
线索 0 | 权重零 | 内容
线索 5 | 只有标题
线索 1 | | 空标题
物品 1 | 钥匙 ×0
物品 1 | 钥匙 ×1000
物品 1 | 不存在 ×1
物品 1 | 钥匙 ×1 | 句子
未知类型 | 啊
@越界 x=120 y=5
@单个 y=5
@超长地点名超长地点名超长地点名超长地点名超长地点名超长地点名超长地点名
线索 1001 | a | b
"""
b = EI.parse(BAD, NAMES)
lines = {e["line"] for e in b["errors"]}
ok(not b["ok"] and b["errors"] and all(e["msg"].startswith(f"第 {e['line']} 行") for e in b["errors"]), "errors have line prefix")
for ln in (1, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15, 16):
    ok(ln in lines, f"line {ln} flagged: {sorted(lines)}")
msgs = " ".join(e["msg"] for e in b["errors"])
for kw in ("还没有地图行", "掉落行前面要先有地点", "权重要在 1~1000", "标题和内容", "数量要在", "不是注册物品", "x 和 y 要同时", "0~100", "最多 30 字", "看不懂"):
    ok(kw in msgs, f"msg {kw}")
ok(len(b["errors"]) >= 10, "multiple errors at once")
long_title = EI.parse("# 地图：A\n@a\n线索 1 | " + "题" * 31 + " | x", NAMES)
ok(any("标题最多" in e["msg"] for e in long_title["errors"]), "long title")
long_text = EI.parse("# 地图：A\n@a\n线索 1 | t | " + "字" * 601, NAMES)
ok(any("内容最多" in e["msg"] for e in long_text["errors"]), "long clue text")
many = "# 地图：A\n@a\n" + "\n".join("空手 1" for _ in range(31))
ok(any("最多 30 条" in e["msg"] for e in EI.parse(many, NAMES)["errors"]), "drops > 30")
sixty = "# 地图：A\n" + "\n".join(f"@s{i}" for i in range(61))
ok(any("最多导入 60" in e["msg"] for e in EI.parse(sixty, NAMES)["errors"]), "spots > 60")
ok(EI.parse("# 地图：A\n@" + "a" * 5 + "\n" * 1 + "@" + "a" * 5, NAMES)["errors"][0]["msg"].find("已经写过") > 0, "dup spot")
ok(not EI.parse("x" * (201 * 1024), NAMES)["ok"], "text too big")
ok(not EI.parse("", NAMES)["ok"], "empty text")
many_err = EI.parse("# 地图：A\n@a\n" + "\n".join("线索 0 | a | b" for _ in range(80)), NAMES)
ok(len(many_err["errors"]) == 50 and many_err["more"] == 30, "errors capped at 50")

# ── 3 预览不写库；有错误 commit 不写库 ──
before = counts()
st, r = imp(SAMPLE, "preview")
ok(st == 200 and r["ok"] and not r["committed"] and counts() == before, "preview writes nothing")
ok(r["summary"] == {"maps_new": 1, "spots_create": 2, "spots_replace": 0, "spots_skip": 0, "drops_total": 7}, f"summary {r['summary']}")
ok(r["plan"][0]["items"] == ["钥匙×1", "旧地图×3"] and r["plan"][0]["has_pos"] and not r["plan"][1]["has_pos"], "plan details")
st, r = imp(BAD, "preview")
ok(st == 200 and r["ok"] and len(r["errors"]) >= 10 and counts() == before, "preview with errors still ok:true, no write")
st, r = imp(BAD, "commit")
ok(st == 400 and not r["ok"] and "处错误" in r["error"] and counts() == before, "commit with errors rejected")
st, r = imp("# 地图：学院\n@a\n物品 1 | 假物品 ×1\n", "commit")
ok(st == 400 and counts() == before, "unregistered item rejected on commit")

# ── 4 提交：带坐标的启用，不带的停用 50/50；单事务 ──
st, r = imp(SAMPLE, "commit")
ok(st == 200 and r["ok"] and r["committed"] and r["pending_pos"] == 1, f"commit {r}")
mp = c2.execute("SELECT * FROM explore_maps WHERE name='学院'").fetchone(); ok(mp, "map created")
lib = c2.execute("SELECT * FROM explore_spots WHERE name='图书馆'").fetchone()
bell = c2.execute("SELECT * FROM explore_spots WHERE name='钟楼'").fetchone()
ok(lib["enabled"] == 1 and lib["x"] == 20 and lib["y"] == 28 and lib["icon"] == "📚", "positioned spot enabled")
ok(bell["enabled"] == 0 and bell["x"] == 50 and bell["y"] == 50, "unpositioned spot disabled 50/50")
libdrops = json.loads(lib["drops"]); ok(len(libdrops) == 5 and len({d["id"] for d in libdrops}) == 5, "drops cleaned with ids")
ok(libdrops[3]["item"] == "旧地图" and libdrops[3]["qty"] == 3, "item stored")
# 原子性：第二个地点写入失败 → 整体回滚
real = E._clean_drops
def boom(raw, allowed=None):
    if any(d.get("title") == "炸弹" for d in raw): return [], "模拟失败"
    return real(raw, allowed)
E._clean_drops = boom
n0 = counts()
st, r = imp("# 地图：新图\n@甲 x=1 y=1\n空手 1\n@乙 x=2 y=2\n线索 1 | 炸弹 | x\n", "commit")
E._clean_drops = real
ok(st == 400 and counts() == n0 and not c2.execute("SELECT 1 FROM explore_maps WHERE name='新图'").fetchone(), "rollback leaves nothing half-written")

# ── 5 同名处理 ──
c2.execute("INSERT INTO explore_clues (show_id, role, spot_id, drop_id, spot_name, title, text, ts) VALUES (?,?,?,?,?,?,?,?)",
           (SID, "林晚", lib["id"], libdrops[0]["id"], "图书馆", "撕碎的信", "x", 1)); c2.commit()
c2.execute("UPDATE explore_spots SET enabled=0, x=77, y=66 WHERE id=?", (lib["id"],)); c2.commit()
REPL = "# 地图：学院\n@图书馆 🏛️ | 新描述\n线索 9 | 撕碎的信 | 改过的内容\n线索 1 | 新线索 | 新\n"
st, r = imp(REPL, "commit")   # 默认 skip
ok(r["summary"]["spots_skip"] == 1 and r["summary"]["spots_replace"] == 0, "default skip")
cur = c2.execute("SELECT * FROM explore_spots WHERE id=?", (lib["id"],)).fetchone()
ok(cur["icon"] == "📚" and len(json.loads(cur["drops"])) == 5, "skip leaves old data untouched")
st, r = imp(REPL, "preview", "replace"); ok(r["summary"]["spots_replace"] == 1 and counts() == counts(), "replace preview")
st, r = imp(REPL, "commit", "replace"); ok(r["committed"], "replace commit")
cur = c2.execute("SELECT * FROM explore_spots WHERE id=?", (lib["id"],)).fetchone()
nd = json.loads(cur["drops"])
ok(cur["icon"] == "🏛️" and cur["desc"] == "新描述" and len(nd) == 2, "replace overwrites desc/icon/drops")
ok(cur["x"] == 77 and cur["y"] == 66 and cur["enabled"] == 0, "replace keeps position and enabled")
ok(nd[0]["id"] == libdrops[0]["id"] and nd[0]["text"] == "改过的内容" and nd[1]["id"] not in {d["id"] for d in libdrops}, "same-title clue keeps old id, new title new id")
ok(c2.execute("SELECT COUNT(*) FROM explore_spots WHERE name='图书馆'").fetchone()[0] == 1, "no duplicate spot")
st, r = imp("# 地图：学院\n@图书馆 x=5 y=6\n空手 1\n", "commit", "replace")
cur = c2.execute("SELECT * FROM explore_spots WHERE id=?", (lib["id"],)).fetchone()
ok(cur["x"] == 5 and cur["y"] == 6 and cur["enabled"] == 0, "explicit x/y overrides position, enabled kept")
# 玩家已拿线索不会再发：id 沿用 → roll 仍排除
spot_row = c2.execute("SELECT * FROM explore_spots WHERE id=?", (lib["id"],)).fetchone()
imp(REPL, "commit", "replace")
spot_row = c2.execute("SELECT * FROM explore_spots WHERE id=?", (lib["id"],)).fetchone()
for _ in range(30):
    d = E.roll(c2, SID, "林晚", spot_row, {"can": True, "catalog": [{"name": "钥匙"}]})
    ok(d is None or d["title"] != "改过的内容", "owned clue not re-issued after replace")

# ── 6 物品必须注册（走后端同一份名单） ──
ok(EI.parse("# 地图：A\n@a\n物品 1 | 金币 ×2", {"金币"})["ok"], "registered passes")
ok(not EI.parse("# 地图：A\n@a\n物品 1 | 金币 ×2", set())["ok"], "empty catalog rejects")

# ── 7 导出再导入往返一致 ──
c2.execute("DELETE FROM explore_spots"); c2.execute("DELETE FROM explore_maps"); c2.commit()
RT = """# 地图：学院
@图书馆 📚 x=20.0 y=28.5 | 描述\\n第二行
线索 5 | 撕碎的信 | 内容\\n第二行 ｜ 带竖线
物品 2 | 钥匙 ×3 | 一句话
空手 4 | 灰尘

@钟楼 🔔 x=1.0 y=2.0  // 停用
空手 1

# 地图：空图
"""
st, r = imp(RT, "commit"); ok(r["committed"], f"rt import {r}")
c2.execute("UPDATE explore_spots SET enabled=0 WHERE name='钟楼'"); c2.commit()
ex = adm.get("/admin/explore/api/export").get_json(); ok(ex["ok"] and "// 停用" in ex["text"], "export marks disabled")
snap = lambda: [(m["name"], [(s["name"], s["icon"], s["desc"], s["x"], s["y"], [{k: v for k, v in d.items() if k != "id"} for d in s["drops"]]) for s in m["spots"]])
                for m in E._maps_payload(c2, SID, with_drops=True)]
a = snap()
c2.execute("DELETE FROM explore_spots"); c2.execute("DELETE FROM explore_maps"); c2.commit()
st, r = imp(ex["text"], "commit"); ok(r["committed"], f"re-import {r}")
ok(snap() == a and len(a) == 2, f"round trip equal\n{a}\n{snap()}")
mid1 = c2.execute("SELECT id FROM explore_maps WHERE name='学院'").fetchone()[0]
only = adm.get(f"/admin/explore/api/export?map_id={mid1}").get_json()["text"]
ok("空图" not in only and "学院" in only, "export single map")
ok(EI.render([]) == "", "render empty")

# ── 8 次数导入 ──
before = counts()
st, r = qimp("林晚 5\n周屿：2\n默认 2\n林晚 4", "preview")
ok(st == 200 and r["ok"] and counts() == before and r["warnings"] and {p["role"]: p["change"] for p in r["plan"]} == {"林晚": "自定义", "周屿": "同默认"}, f"quota preview {r}")
ok(r["plan"][0]["daily"] == 4, "last duplicate wins")
st, r = qimp("路人 3\n林晚 100\n林晚\n周屿 -1", "preview")
ok(st == 200 and len(r["errors"]) == 4 and all(e["msg"].startswith(f"第 {e['line']} 行") for e in r["errors"]), "quota errors")
st, r = qimp("路人 3", "commit"); ok(st == 400 and counts() == before, "quota commit w/ errors no write")
st, r = qimp("林晚 5\n周屿\t1\n默认　3", "commit"); ok(st == 200 and r["committed"], "quota commit")
ok(c2.execute("SELECT default_daily FROM explore_settings WHERE show_id=?", (SID,)).fetchone()[0] == 3, "default set")
qd = {x["role"]: x["daily"] for x in c2.execute("SELECT role,daily FROM explore_quota WHERE show_id=?", (SID,))}
ok(qd == {"林晚": 5, "周屿": 1}, f"custom stored {qd}")
st, r = qimp("林晚 3", "commit")   # 与默认相同 → 删除自定义
ok("林晚" not in {x["role"] for x in c2.execute("SELECT role FROM explore_quota WHERE show_id=?", (SID,))} and r["plan"][0]["change"] == "同默认", "same as default removes custom")
ok(c2.execute("SELECT daily FROM explore_quota WHERE show_id=? AND role='周屿'", (SID,)).fetchone()[0] == 1, "unmentioned untouched")
ok(qimp("", "preview")[1]["errors"], "quota empty")

# ── 9 权限 ──
anon = app.test_client()
for method, path in (("post", "import"), ("get", "export"), ("post", "quota_import")):
    ok(getattr(anon, method)("/admin/explore/api/" + path, json={"text": SAMPLE}).status_code == 302, f"{path} needs login")
    if method == "post":
        ok(adm.post("/admin/explore/api/" + path, json={"text": SAMPLE, "mode": "commit"}).status_code == 403, f"{path} needs csrf")
print("ALL OK")

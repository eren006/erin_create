"""预订季度「复制配置」：地点列表和地图不跟着整套配置走，其他配置照常复制；钥匙/天数等原有排除项不变。
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tests/book_copy_test.py ；全部通过时最后一行打印 ALL OK。
"""
import sys, os, json, sqlite3, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app as A
A.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
A.MODERATION_LOG = os.path.join(os.path.dirname(A.DB_PATH), "moderation.log")
A.init_db()
c = sqlite3.connect(A.DB_PATH); c.row_factory = sqlite3.Row
TID = c.execute("SELECT id FROM tenants").fetchone()["id"]
c.execute("INSERT INTO shows (tenant_id,name) VALUES (?,'上一季')", (TID,)); c.execute("INSERT INTO shows (tenant_id,name) VALUES (?,'下一季')", (TID,))
OLD = c.execute("SELECT id FROM shows WHERE name='上一季'").fetchone()[0]; NEW = c.execute("SELECT id FROM shows WHERE name='下一季'").fetchone()[0]
def put(k, v): c.execute("INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?)", (OLD, TID, k, v))
put("mailCooldown", "30"); put("available_places", json.dumps({"图书馆": {"desc": "d", "locked": False}}))
put("place_maps", json.dumps({"主城": {"w": 20, "h": 14, "visible": True, "items": []}}))
put("place_keys", "{}"); put("global_days", "D3"); c.commit()
def ok(cond, msg):
    if not cond: raise AssertionError(msg)
with A.app.app_context():
    db = A.get_db()
    n = A._book_copy_config(db, TID, NEW, f"show:{OLD}"); db.commit()
    got = {r["key"]: r["value"] for r in db.execute("SELECT key,value FROM site_config WHERE show_id=?", (NEW,))}
ok(got.get("mailCooldown") == "30", f"普通配置要复制：{got}")
for k in ("available_places", "place_maps", "place_keys", "global_days"):
    ok(k not in got, f"{k} 不该被复制")
ok(n == 1, f"只应复制 1 项，实际 {n}")
print("ALL OK")

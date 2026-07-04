"""
一次性脚本：仿照原来"限定一池"（常驻伙伴 + 限定UR + 中档材料）的结构，
新建一个池子，把目前 custom_companions 表里后台新增的伙伴（不含武则天/项羽/
王阳明这些代码内置的限定一池专属角色）全部加进去，权重按 UR 默认给 4。

常驻伙伴和中档材料不需要手动加——只要新池子 include_regular=1（默认就是1），
app.py 里的 _load_custom_pools() 会自动把 _COMP_REGULAR + _MAT 混进去。

用法（服务器上，与 xianxia.db 同目录执行）：
    python3 make_pool_from_custom.py
"""
import os
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "xianxia.db")

POOL_NAME   = "限定三池"
POOL_ICON   = "🌟"
POOL_COST   = 280
POOL_PITY   = 40
POOL_DESC   = "常驻伙伴 + 新增限定伙伴 + 中档材料"
MEMBER_WEIGHT = 4


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    existing = conn.execute("SELECT id FROM custom_pools WHERE name=?", (POOL_NAME,)).fetchone()
    if existing:
        pool_id = existing['id']
        print(f"池子【{POOL_NAME}】已存在（id={pool_id}），直接往里面补充成员。")
    else:
        cur = conn.execute(
            """INSERT INTO custom_pools (name,icon,cost,pity_max,description,is_active,is_default,include_regular,created_at)
               VALUES (?,?,?,?,?,1,0,1,?)""",
            (POOL_NAME, POOL_ICON, POOL_COST, POOL_PITY, POOL_DESC, int(time.time())))
        pool_id = cur.lastrowid
        print(f"已创建池子【{POOL_NAME}】（id={pool_id}）。")

    rows = conn.execute("SELECT key, name FROM custom_companions").fetchall()
    if not rows:
        print("custom_companions 表里还没有任何后台新增的伙伴，先去 /admin/companions 创建。")
    added = 0
    for r in rows:
        cur = conn.execute(
            "INSERT OR IGNORE INTO custom_pool_companions (pool_id,companion_key,weight) VALUES (?,?,?)",
            (pool_id, r['key'], MEMBER_WEIGHT))
        if cur.rowcount:
            added += 1
            print(f"  + {r['name']}（{r['key']}）权重{MEMBER_WEIGHT}")

    conn.commit()
    conn.close()
    print(f"完成，本次新加入 {added} 个伙伴。重启服务后去 /admin/companion_pools 查看，"
          f"玩家端入口会出现在 /game/companion 页面。")


if __name__ == '__main__':
    main()

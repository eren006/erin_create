"""
一次性脚本：仿照 app.py 里 COMPANION_TYPES 中"限定一池"（武则天/项羽/王阳明）
的写法，新增 3 个限定伙伴（孙武/孙思邈为 UR，西施为灵祖档，比照老子），
并加入"限定三池"（custom_pools.name='限定三池'）。

风格参考（app.py 里硬编码的限定一池条目）：
    ('wu_zetian', '武则天', '天后武氏', 'ur', '...【限定绝版】', {effects...})

用法（服务器上，与 xianxia.db 同目录执行，确保已经跑过 make_pool_from_custom.py 建好池子）：
    python3 add_pool3_companions.py
"""
import os
import sqlite3
import json
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "xianxia.db")
POOL_NAME = "限定三池"
MEMBER_WEIGHT = 4
# 灵祖档（与老子同级）权重按老子的写法调到 1，比 UR 稀有 4 倍
MEMBER_WEIGHT_OVERRIDE = {'xi_shi': 1}

NEW_COMPANIONS = [
    # (key, name, title, rarity, description, effects)
    ('sun_wu', '孙武', '兵圣', 'ur',
     '春秋兵家至圣，著《孙子兵法》，运筹决胜，所向披靡，兵行诡道更擅趋吉避凶。【限定绝版】',
     {'atk_pct': 0.20, 'crit_rate': 0.10, 'breakthrough_bonus': 15, 'dodge_rate': 0.05}),
    ('sun_simiao', '孙思邈', '药王', 'ur',
     '药王孙思邈，悬壶济世，寿逾百岁，炼丹养生造诣无双，深谙固本培元之法，灵气生生不息。【限定绝版】',
     {'alchemy_bonus': 0.20, 'hp_pct': 0.18, 'energy_max': 20, 'spirit_regen_pct': 0.06}),
    ('xi_shi', '西施', '沉鱼之容', 'lzr',
     '春秋四大美女之首，沉鱼之姿，倾国倾城，广结善缘修炼皆有助益，美人计所获奇珍异宝亦是丰厚，其气韵已臻灵祖之境，滋养灵海使灵力上限大增。【灵祖·限定绝版】',
     {'affinity_pct': 0.25, 'exp_pct': 0.20, 'stones_pct': 0.18, 'energy_max': 60}),
]


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    pool = conn.execute("SELECT id FROM custom_pools WHERE name=?", (POOL_NAME,)).fetchone()
    if not pool:
        print(f"没找到池子【{POOL_NAME}】，请先跑 make_pool_from_custom.py 建好池子。")
        conn.close()
        return
    pool_id = pool['id']

    for key, name, title, rarity, desc, effects in NEW_COMPANIONS:
        exists = conn.execute("SELECT 1 FROM custom_companions WHERE key=?", (key,)).fetchone()
        if exists:
            print(f"伙伴 {name}（{key}）已存在，跳过新增，仅确保加入池子。")
        else:
            conn.execute(
                """INSERT INTO custom_companions (key,name,title,rarity,description,effects_json,created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (key, name, title, rarity, desc, json.dumps(effects, ensure_ascii=False), int(time.time())))
            print(f"已新增伙伴【{name}】（{key}）。")
        conn.execute(
            "INSERT OR IGNORE INTO custom_pool_companions (pool_id,companion_key,weight) VALUES (?,?,?)",
            (pool_id, key, MEMBER_WEIGHT_OVERRIDE.get(key, MEMBER_WEIGHT)))

    conn.commit()
    conn.close()
    print(f"完成，3 个限定伙伴已加入【{POOL_NAME}】。重启服务后刷新 /admin/companion_pools 查看。")


if __name__ == '__main__':
    main()

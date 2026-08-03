import os
import markdown
from flask import Flask, render_template, abort

app = Flask(__name__)

BASE_DIR = os.path.dirname(__file__)
CONTENT_DIR = os.path.join(BASE_DIR, "content")

MD_EXTENSIONS = ["tables", "sane_lists"]

DAYS = [
    {
        "num": 1,
        "date": "7月17日",
        "weekday": "周五",
        "title": "黄金圈＋Laugarás Lagoon＋Ylja",
        "depart": "Hotel Borg by Keahotels",
        "stay": "Hotel Loa",
        "drive": "约 3.5—4 小时",
        "route": "Hotel Borg → Þingvellir → Geysir → Gullfoss → Laugarás Lagoon → Hotel Loa",
        "nav_steps": [
            {"label": "Þingvellir National Park – Hakið Visitor Center", "query": "Þingvellir National Park Hakið Visitor Center Iceland"},
            {"label": "Geysir Parking", "query": "Geysir Parking Iceland"},
            {"label": "Gullfoss Parking", "query": "Gullfoss Parking Iceland"},
            {"label": "Laugarás Lagoon", "query": "Laugarás Lagoon Iceland"},
            {"label": "Hotel Loa", "query": "Hotel Loa Iceland"},
        ],
        "bookings": [("16:00", "Laugarás Lagoon"), ("约 19:00", "Ylja Restaurant")],
        "file": "day1.md",
        "critical": "16:00 Laugarás Lagoon 温泉签到",
    },
    {
        "num": 2,
        "date": "7月18日",
        "weekday": "周六",
        "title": "南岸瀑布＋黑沙滩＋冰河湖游船",
        "depart": "Hotel Loa",
        "stay": "Hótel Jökulsárlón – Glacier Lagoon Hotel",
        "drive": "约 4.5—5 小时",
        "route": "Hotel Loa → Seljalandsfoss → Skógafoss → Dyrhólaey → Reynisfjara → Vík → Jökulsárlón → Diamond Beach → Hótel Jökulsárlón",
        "nav_steps": [
            {"label": "Seljalandsfoss Parking", "query": "Seljalandsfoss Parking Iceland"},
            {"label": "Skógafoss Parking", "query": "Skógafoss Parking Iceland"},
            {"label": "Dyrhólaey Viewpoint", "query": "Dyrhólaey Viewpoint Iceland"},
            {"label": "Reynisfjara Beach", "query": "Reynisfjara Beach Iceland"},
            {"label": "Vík", "query": "Vík í Mýrdal Iceland"},
            {"label": "Jökulsárlón Glacier Lagoon", "query": "Jökulsárlón Glacier Lagoon Iceland"},
            {"label": "Diamond Beach", "query": "Diamond Beach Iceland"},
            {"label": "Hótel Jökulsárlón", "query": "Hótel Jökulsárlón Iceland"},
        ],
        "bookings": [("16:20", "Jökulsárlón 冰河湖游船")],
        "file": "day2.md",
        "critical": "15:35 前抵达冰河湖签到",
    },
    {
        "num": 3,
        "date": "7月19日",
        "weekday": "周日",
        "title": "冰河湖＋东峡湾＋米湖",
        "depart": "Hótel Jökulsárlón",
        "stay": "Fosshotel Mývatn",
        "drive": "约 6—7 小时",
        "route": "Hótel Jökulsárlón → Höfn → Hvalnes 一带 → Djúpivogur → 东峡湾 → Egilsstaðir → 高地公路 → Fosshotel Mývatn",
        "nav_steps": [
            {"label": "Höfn", "query": "Höfn Iceland"},
            {"label": "Djúpivogur", "query": "Djúpivogur Iceland"},
            {"label": "Egilsstaðir", "query": "Egilsstaðir Iceland"},
            {"label": "Fosshotel Mývatn", "query": "Fosshotel Mývatn Iceland"},
        ],
        "bookings": [("19:30", "Fosshotel Mývatn 晚餐，4 人")],
        "file": "day3.md",
        "critical": "19:30 酒店晚餐",
    },
    {
        "num": 4,
        "date": "7月20日",
        "weekday": "周一",
        "title": "米湖火山景观＋Earth Lagoon＋Goðafoss＋阿克雷里",
        "depart": "Fosshotel Mývatn",
        "stay": "Bryggjan Boutique Hotel",
        "drive": "约 2.5—3 小时",
        "route": "Fosshotel Mývatn → Hverir → Víti (Krafla) → Grjótagjá → Dimmuborgir → 午餐 → Earth Lagoon → Goðafoss → Akureyri",
        "nav_steps": [
            {"label": "Hverir", "query": "Hverir Iceland"},
            {"label": "Víti Krafla", "query": "Viti Krafla Iceland"},
            {"label": "Grjótagjá", "query": "Grjótagjá Iceland"},
            {"label": "Dimmuborgir", "query": "Dimmuborgir Iceland"},
            {"label": "Earth Lagoon Mývatn", "query": "Earth Lagoon Mývatn Iceland"},
            {"label": "Goðafoss Parking", "query": "Goðafoss Parking Iceland"},
            {"label": "Bryggjan Boutique Hotel", "query": "Bryggjan Boutique Hotel Akureyri Iceland"},
        ],
        "bookings": [("14:00", "Earth Lagoon Mývatn")],
        "file": "day4.md",
        "critical": "13:25 前抵达 Earth Lagoon 签到",
    },
    {
        "num": 5,
        "date": "7月21日",
        "weekday": "周二",
        "title": "阿克雷里＋北部公路＋雷克雅未克＋DILL",
        "depart": "Bryggjan Boutique Hotel",
        "stay": "Exeter Hotel",
        "drive": "约 7—7.5 小时",
        "route": "Akureyri → Blönduós → Hvítserkur (Vatnsnes) → Hraunfossar／Deildartunguhver → Borgarnes → Reykjavík",
        "nav_steps": [
            {"label": "Blönduós", "query": "Blönduós Iceland"},
            {"label": "Hvítserkur", "query": "Hvitserkur Iceland"},
            {"label": "Hraunfossar", "query": "Hraunfossar Iceland"},
            {"label": "Deildartunguhver", "query": "Deildartunguhver Iceland"},
            {"label": "Borgarnes", "query": "Borgarnes Iceland"},
            {"label": "Exeter Hotel Reykjavík", "query": "Exeter Hotel Reykjavík"},
        ],
        "bookings": [("20:15", "DILL 晚餐")],
        "file": "day5.md",
        "critical": "20:15 DILL 晚餐（无需再卡 17:00 回城，留够约 1 小时入住换装即可）",
    },
    {
        "num": 6,
        "date": "7月22日",
        "weekday": "周三",
        "title": "雷克雅未克＋机场离境",
        "depart": "Exeter Hotel",
        "stay": "—（当晚已离境）",
        "drive": "约 45 分钟（市区至机场）",
        "route": "Exeter Hotel → 市区短活动 → 机场方向加油站 → 租车公司 → KEF 航站楼",
        "nav_steps": [
            {"label": "按租车订单上的准确还车地址导航，不要只输入 “KEF Airport”", "query": None},
            {"label": "Keflavík International Airport (KEF)", "query": "Keflavík International Airport"},
        ],
        "bookings": [("17:00", "航班起飞，KEF")],
        "file": "day6.md",
        "critical": "14:00 前进入航站楼",
    },
]

CRITICAL_DEADLINES = [
    "7月18日 15:35 前抵达冰河湖签到",
    "7月19日 19:30 赶到 Fosshotel Mývatn 晚餐",
    "7月20日 13:25 抵达 Earth Lagoon 签到",
    "7月21日 20:15 DILL 晚餐（回城时间已放宽，见当天页面）",
]

PACKING_SECTIONS = [
    {
        "title": "全程车内常备",
        "entries": [
            "每人至少一瓶水",
            "能量棒、巧克力或坚果",
            "备用袜子",
            "防水袋",
            "纸巾与湿巾",
            "充电线和充电宝",
            "离线地图",
            "墨镜",
            "薄手套",
            "防风帽",
            "小垃圾袋",
            "晕车药（如有人容易晕车）",
            "泳衣集中放在容易拿取的袋中",
        ],
    },
    {
        "title": "温泉包（17/18/20/21 日均可能用到）",
        "entries": [
            "泳衣",
            "干净内衣",
            "干袜子",
            "防水袋",
            "梳子和护肤品",
            "隐形眼镜备用盒或眼镜",
        ],
    },
    {
        "title": "还车当天（7月22日）",
        "entries": [
            "护照",
            "钱包",
            "所有充电器",
            "游船和温泉湿衣物已晾干或密封",
            "加满油并保留小票",
            "环车拍照 / 录像留证",
        ],
    },
]


MAP_DISCLAIMER = "地图坐标仅为路线示意，可能存在偏差，实际导航请点击上方地名跳转 Google 地图。"

DAY_MAPS = {
    1: [
        {"name": "Þingvellir 辛格维利尔", "lat": 64.2559, "lon": -21.1298},
        {"name": "Geysir 间歇泉", "lat": 64.3108, "lon": -20.3024},
        {"name": "Gullfoss 黄金瀑布", "lat": 64.3271, "lon": -20.1199},
        {"name": "Laugarás Lagoon", "lat": 64.2380, "lon": -20.4520},
    ],
    2: [
        {"name": "Seljalandsfoss", "lat": 63.6156, "lon": -19.9886},
        {"name": "Skógafoss", "lat": 63.5321, "lon": -19.5116},
        {"name": "Dyrhólaey", "lat": 63.4022, "lon": -19.1252},
        {"name": "Reynisfjara 黑沙滩", "lat": 63.4052, "lon": -19.0432},
        {"name": "Vík", "lat": 63.4186, "lon": -19.0060},
        {"name": "Jökulsárlón 冰河湖", "lat": 64.0784, "lon": -16.2300},
        {"name": "Diamond Beach", "lat": 64.0480, "lon": -16.1800},
    ],
    3: [
        {"name": "Höfn", "lat": 64.2539, "lon": -15.2082},
        {"name": "Djúpivogur", "lat": 64.6552, "lon": -14.2807},
        {"name": "Egilsstaðir", "lat": 65.2669, "lon": -14.3948},
        {"name": "Mývatn / Reykjahlíð", "lat": 65.6408, "lon": -16.9096},
    ],
    4: [
        {"name": "Hverir 地热区", "lat": 65.6389, "lon": -16.8058},
        {"name": "Grjótagjá", "lat": 65.6330, "lon": -16.8830},
        {"name": "Dimmuborgir", "lat": 65.5867, "lon": -16.9000},
        {"name": "Earth Lagoon Mývatn", "lat": 65.6333, "lon": -16.8283},
        {"name": "Goðafoss", "lat": 65.6828, "lon": -17.5510},
        {"name": "Akureyri", "lat": 65.6885, "lon": -18.1262},
    ],
    5: [
        {"name": "Akureyri", "lat": 65.6885, "lon": -18.1262},
        {"name": "Blönduós", "lat": 65.6631, "lon": -20.2955},
        {"name": "Grábrók", "lat": 64.7908, "lon": -21.4931},
        {"name": "Hraunfossar", "lat": 64.7161, "lon": -20.9727},
        {"name": "Deildartunguhver", "lat": 64.6653, "lon": -21.4067},
        {"name": "Borgarnes", "lat": 64.5384, "lon": -21.9214},
        {"name": "Reykjavík", "lat": 64.1466, "lon": -21.9426},
    ],
    6: [
        {"name": "Reykjavík 市中心", "lat": 64.1548, "lon": -21.9426},
        {"name": "KEF 机场", "lat": 63.9850, "lon": -22.6056},
    ],
}

ATTRACTIONS = [
    {"name": "Þingvellir 辛格维利尔国家公园", "day": 1, "category": "历史文化", "emoji": "🏛️",
     "blurb": "世界遗产，冰岛古议会与共和国诞生地，能亲眼看到北美与欧亚板块的裂谷。"},
    {"name": "Geysir 间歇泉区", "day": 1, "category": "地热奇观", "emoji": "💦",
     "blurb": "Strokkur 每 8—10 分钟喷发一次，热水冲上约 30 米高。"},
    {"name": "Gullfoss 黄金瀑布", "day": 1, "category": "瀑布", "emoji": "🌊",
     "blurb": "两级跌落总计约 31 米，水雾中常见彩虹，黄金圈收官景点。"},
    {"name": "Laugarás Lagoon", "day": 1, "category": "温泉", "emoji": "♨️",
     "blurb": "黄金圈附近的地热温泉，含桑拿和冷水池，当天已订 16:00。"},
    {"name": "Seljalandsfoss", "day": 2, "category": "瀑布", "emoji": "🌊",
     "blurb": "少数可以走到水帘后方的瀑布，高约 60—65 米。"},
    {"name": "Skógafoss", "day": 2, "category": "瀑布", "emoji": "🌊",
     "blurb": "宽阔完整水幕，光线角度合适时常见彩虹。"},
    {"name": "Dyrhólaey", "day": 2, "category": "海岸", "emoji": "🪨",
     "blurb": "约 120 米高海岬，标志性海蚀拱门，可远眺黑沙海岸线。"},
    {"name": "Reynisfjara 黑沙滩", "day": 2, "category": "海岸", "emoji": "⚫",
     "blurb": "玄武岩柱与海蚀柱奇观，务必留意入口警示灯与“突袭浪”。"},
    {"name": "Jökulsárlón 冰河湖", "day": 2, "category": "冰川冰湖", "emoji": "🧊",
     "blurb": "冰岛规模最大的冰河湖之一，游船可近距离看浮冰。"},
    {"name": "Diamond Beach", "day": 2, "category": "海岸", "emoji": "💎",
     "blurb": "透明冰块被海浪冲上黑沙滩，在阳光下像散落的钻石。"},
    {"name": "Djúpivogur", "day": 3, "category": "城镇小镇", "emoji": "🏘️",
     "blurb": "东峡湾历史渔村，“Eggs of Merry Bay” 34 枚巨型鸟蛋雕塑。"},
    {"name": "东峡湾沿岸", "day": 3, "category": "海岸", "emoji": "🏔️",
     "blurb": "狭长峡湾、古老岩脉与小岛礁景观，适合沿途欣赏而非下车久留。"},
    {"name": "Hverir 地热区", "day": 4, "category": "地热奇观", "emoji": "♨️",
     "blurb": "沸腾泥浆池与蒸汽孔，红黄地表宛如异星表面。"},
    {"name": "Grjótagjá 熔岩裂缝洞穴", "day": 4, "category": "熔岩地貌", "emoji": "🕳️",
     "blurb": "洞内是蓝色地热水，过去曾是天然温泉浴场。"},
    {"name": "Dimmuborgir 熔岩城堡", "day": 4, "category": "熔岩地貌", "emoji": "🌋",
     "blurb": "“黑暗城堡”，古熔岩湖坍塌形成的塔状与拱门结构。"},
    {"name": "Earth Lagoon Mývatn", "day": 4, "category": "温泉", "emoji": "♨️",
     "blurb": "米湖火山地貌背景下的地热温泉，当天已订 14:00。"},
    {"name": "Goðafoss 众神瀑布", "day": 4, "category": "瀑布", "emoji": "🌊",
     "blurb": "弧形展开约 30 米宽，名称与冰岛基督教化传说相关。"},
    {"name": "Grábrók 火山口", "day": 5, "category": "熔岩地貌", "emoji": "🌋",
     "blurb": "保存完好的碎屑锥火山口，就在一号公路旁，20 分钟快速登顶一圈。"},
    {"name": "Hraunfossar", "day": 5, "category": "瀑布", "emoji": "🌊",
     "blurb": "熔岩原地下渗水汇成的一连串细流瀑布，紧邻 Barnafoss，冰岛少见的地质景观。"},
    {"name": "Deildartunguhver", "day": 5, "category": "地热奇观", "emoji": "♨️",
     "blurb": "欧洲流量最大的温泉，每秒涌出约 180 升接近沸腾的地热水。"},
    {"name": "雷克雅未克老港口＋Harpa", "day": 6, "category": "城镇文化", "emoji": "🎭",
     "blurb": "玻璃幕墙音乐厅与老港口船只，适合旅程最后轻松散步。"},
]

ATTRACTION_CATEGORIES = ["全部"] + sorted({a["category"] for a in ATTRACTIONS})

GUIDE_HERO = "冰岛通用旅行常识：货币、驾驶、网络、时区、安全号码一次说清楚。"


def load_day_html(filename):
    path = os.path.join(CONTENT_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return markdown.markdown(text, extensions=MD_EXTENSIONS)


def load_simple_html(filename):
    path = os.path.join(CONTENT_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return markdown.markdown(text, extensions=MD_EXTENSIONS)


@app.route("/")
def index():
    return render_template(
        "index.html", days=DAYS, deadlines=CRITICAL_DEADLINES
    )


@app.route("/day/<int:num>")
def day(num):
    day_data = next((d for d in DAYS if d["num"] == num), None)
    if day_data is None:
        abort(404)
    content_html = load_day_html(day_data["file"])
    prev_day = next((d for d in DAYS if d["num"] == num - 1), None)
    next_day = next((d for d in DAYS if d["num"] == num + 1), None)
    return render_template(
        "day.html",
        day=day_data,
        content=content_html,
        prev_day=prev_day,
        next_day=next_day,
        map_points=DAY_MAPS.get(num, []),
        map_disclaimer=MAP_DISCLAIMER,
    )


@app.route("/fuel")
def fuel():
    content_html = load_simple_html("fuel.md")
    return render_template("simple.html", title="全程加油计划", content=content_html)


@app.route("/resources")
def resources():
    content_html = load_simple_html("resources.md")
    return render_template(
        "simple.html", title="每日晨检 ／ 实用链接", content=content_html
    )


@app.route("/packing")
def packing():
    return render_template("packing.html", sections=PACKING_SECTIONS)


@app.route("/attractions")
def attractions():
    return render_template(
        "attractions.html", attractions=ATTRACTIONS, categories=ATTRACTION_CATEGORIES
    )


@app.route("/guide")
def guide():
    content_html = load_simple_html("guide.md")
    return render_template(
        "simple.html", title="旅行须知", content=content_html, hero=GUIDE_HERO
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug, host="0.0.0.0", port=port)

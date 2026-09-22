#!/usr/bin/env python3
"""取行情（Yahoo chart 接口），输出最近一根日线的收盘/涨跌幅。写稿的数字只能来自这里或可核对的新闻。

用法：
  python3 tools/quotes.py                # 全部预设分组
  python3 tools/quotes.py tape sectors   # 只取指定分组
  python3 tools/quotes.py --sym NVDA,^GSPC
  python3 tools/quotes.py --hist ^SOX,SMH,^IXIC   # 最近6个交易日的逐日涨跌，用于「本周走势」
输出每行：代码  名称  最新/收盘  当日涨跌%  5个交易日涨跌%  最后一根K线日期(纽约)
注意：期货/原油/黄金/美元指数是24小时品种，日线K线口径不可靠，这几类以行尾 [Yahoo报价] 为准（且要写明"截稿时"）；
股票、指数、ETF 以日线为准。
盘中或盘前运行时，"最新"是当时价格，K线日期为当天；周末/休市则是最近一个交易日的收盘。
"""
import concurrent.futures as cf
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

GROUPS = {
    "tape": [
        ("^GSPC", "标普500"), ("^IXIC", "纳斯达克"), ("^DJI", "道琼斯"), ("^RUT", "罗素2000"),
        ("^VIX", "VIX"), ("^TNX", "10年期美债收益率(%)"), ("DX-Y.NYB", "美元指数"),
        ("CL=F", "WTI原油"), ("GC=F", "黄金"), ("BTC-USD", "比特币"),
    ],
    "futures": [("ES=F", "标普期货"), ("NQ=F", "纳指期货"), ("YM=F", "道指期货")],
    "global": [
        ("^N225", "日经225"), ("^HSI", "恒生指数"), ("^HSTECH", "恒生科技"), ("000001.SS", "上证综指"),
        ("399006.SZ", "创业板指"), ("^KS11", "韩国KOSPI"), ("^TWII", "台湾加权"),
        ("^FTSE", "英国富时100"), ("^GDAXI", "德国DAX"), ("^FCHI", "法国CAC40"), ("^STOXX50E", "欧洲斯托克50"),
    ],
    "sectors": [
        ("XLK", "科技"), ("XLC", "通信服务"), ("XLY", "可选消费"), ("XLP", "必选消费"), ("XLF", "金融"),
        ("XLV", "医疗"), ("XLI", "工业"), ("XLE", "能源"), ("XLU", "公用事业"), ("XLB", "材料"),
        ("XLRE", "房地产"), ("SMH", "半导体ETF"), ("IGV", "软件ETF"), ("XBI", "生物科技"), ("KRE", "区域银行"),
    ],
    "mag7": [
        ("AAPL", "苹果"), ("MSFT", "微软"), ("GOOGL", "谷歌A"), ("AMZN", "亚马逊"),
        ("NVDA", "英伟达"), ("META", "Meta"), ("TSLA", "特斯拉"),
    ],
    "sox": [
        ("^SOX", "费城半导体指数"), ("SOXX", "半导体ETF(iShares)"), ("SMH", "半导体ETF(VanEck)"),
        ("NVDA", "英伟达"), ("AVGO", "博通"), ("AMD", "AMD"), ("TSM", "台积电ADR"), ("MU", "美光"),
        ("ASML", "ASML"), ("ARM", "Arm"), ("INTC", "英特尔"), ("QCOM", "高通"), ("TXN", "德州仪器"),
        ("AMAT", "应用材料"), ("LRCX", "泛林"), ("KLAC", "科磊"), ("MRVL", "迈威尔"), ("MCHP", "微芯"),
        ("ADI", "亚德诺"), ("NXPI", "恩智浦"), ("ON", "安森美"), ("SNDK", "闪迪"), ("STX", "希捷"),
    ],
    "ai": [
        ("AVGO", "博通"), ("AMD", "AMD"), ("TSM", "台积电ADR"), ("MU", "美光"), ("ORCL", "甲骨文"),
        ("PLTR", "Palantir"), ("ASML", "ASML"), ("SMCI", "超微电脑"), ("CRWV", "CoreWeave"), ("ARM", "Arm"),
        ("VRT", "Vertiv"), ("SNOW", "Snowflake"),
    ],
    "china": [
        ("BABA", "阿里ADR"), ("BIDU", "百度ADR"), ("PDD", "拼多多"), ("JD", "京东ADR"), ("NTES", "网易ADR"),
        ("KWEB", "中概互联网ETF"), ("FXI", "中国大盘ETF"), ("ASHR", "沪深300ETF"),
        ("0700.HK", "腾讯"), ("9988.HK", "阿里港股"), ("9888.HK", "百度港股"), ("1810.HK", "小米"),
        ("0981.HK", "中芯国际港股"), ("0992.HK", "联想集团"),
    ],
}

NY = timezone(timedelta(hours=-4))  # 仅用于展示；日期以交易所时区为准


def fetch(sym):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(sym) +
           "?range=1mo&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                j = json.load(r)
            res = j["chart"]["result"][0]
            ts = res["timestamp"]
            closes = res["indicators"]["quote"][0]["close"]
            gmt = res["meta"].get("gmtoffset", 0)
            pts = [(t, c) for t, c in zip(ts, closes) if c is not None]
            if sym != "BTC-USD":
                # 24小时品种（期货/美元/原油）周日晚会开出一根只有几小时的"新交易日"K线，剔掉，避免涨跌算错
                pts = [(t, c) for t, c in pts
                       if datetime.fromtimestamp(t + gmt, timezone.utc).weekday() < 5]
            last_t, last = pts[-1]
            prev = pts[-2][1] if len(pts) > 1 else None
            five = pts[-6][1] if len(pts) > 5 else None
            d = datetime.fromtimestamp(last_t + gmt, timezone.utc).strftime("%Y-%m-%d")
            return {
                "last": last,
                "chg": (last / prev - 1) * 100 if prev else None,
                "chg5d": (last / five - 1) * 100 if five else None,
                "date": d,
                "mkt": res["meta"].get("regularMarketPrice"),
                "mkt_chg": res["meta"].get("regularMarketChangePercent"),
            }
        except Exception as e:  # noqa
            err = str(e)
    return {"error": err}


def fmt(v, pct=False):
    if v is None:
        return "n/a"
    return f"{v:+.2f}%" if pct else f"{v:,.2f}"


def hist(sym, n=6):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(sym) +
           "?range=1mo&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        res = json.load(r)["chart"]["result"][0]
    gmt = res["meta"].get("gmtoffset", 0)
    pts = [(datetime.fromtimestamp(t + gmt, timezone.utc), c)
           for t, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]) if c is not None]
    rows = [(pts[i][0].strftime("%m-%d %a"), pts[i][1], (pts[i][1] / pts[i - 1][1] - 1) * 100)
            for i in range(1, len(pts))][-n:]
    print(f"\n[{sym}] 52周高 {res['meta'].get('fiftyTwoWeekHigh')}  52周低 {res['meta'].get('fiftyTwoWeekLow')}")
    for d, c, p in rows:
        print(f"  {d}  {c:>12,.2f}  {p:+.2f}%")
    print("  （若最后一行的日期是今天且美股尚未收盘，那一行是盘中数据，不要当收盘写）")


def main():
    args = sys.argv[1:]
    if args and args[0] == "--hist":
        for s_ in args[1].split(","):
            hist(s_)
        return
    items = []
    if args and args[0] == "--sym":
        items = [(s, s) for s in args[1].split(",")]
    else:
        names = args or list(GROUPS)
        for g in names:
            if g not in GROUPS:
                sys.exit(f"未知分组 {g}，可选 {list(GROUPS)}")
            items.append(("#" + g, None))
            items.extend(GROUPS[g])
    real = [i for i in items if not i[0].startswith("#")]
    with cf.ThreadPoolExecutor(8) as ex:
        data = dict(zip([s for s, _ in real], ex.map(lambda x: fetch(x[0]), real)))
    for sym, name in items:
        if sym.startswith("#"):
            print(f"\n[{sym[1:]}]")
            continue
        d = data[sym]
        if "error" in d:
            print(f"{sym:<10} {name:<12} 取数失败: {d['error']}")
        else:
            print(f"{sym:<10} {name:<14} {fmt(d['last']):>12}  日 {fmt(d['chg'], True):>8}  5日 {fmt(d['chg5d'], True):>8}  {d['date']}" +
                  (f"   [Yahoo报价 {fmt(d['mkt'])} {fmt(d['mkt_chg'], True)}]" if d.get("mkt") is not None else ""))


if __name__ == "__main__":
    main()

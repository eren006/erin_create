"""探索踩点：文本批量导入 / 导出（纯函数，不碰数据库、不依赖 Flask，方便单测）。
语法见 docs/Codex任务_批量导入.md。parse() 一次给出全部错误（带行号），render() 把后台配置导出成同样格式，导出再导入得到相同配置。
"""
import re

MAX_TEXT = 200 * 1024
MAX_SPOTS = 60
MAX_DROPS = 30
MAX_ERRORS = 50
KIND_WORDS = {"线索": "clue", "clue": "clue", "物品": "item", "item": "item", "空手": "nothing", "nothing": "nothing"}
KIND_LABEL = {"clue": "线索", "item": "物品", "nothing": "空手"}

_MAP_RE = re.compile(r"^#\s*地图\s*[:：]\s*(.*)$")
_DROP_RE = re.compile(r"^(线索|物品|空手|clue|item|nothing)(?![A-Za-z])\s*(.*)$", re.I)
_WEIGHT_RE = re.compile(r"^(-?\d+)?\s*(\|.*)?$", re.S)
_ITEM_QTY_RE = re.compile(r"^(.*?)\s*[×xX*]\s*(\d+)$")
_COORD_RE = re.compile(r"^([xXyY])=(.*)$")
_DISABLED_TAIL = re.compile(r"\s*//\s*停用\s*$")


def _norm(line):
    """全角空格/竖线/等号统一成半角，去首尾空白"""
    return line.replace("　", " ").replace("｜", "|").replace("＝", "=").strip()


def _unescape(s):
    return s.replace("\\n", "\n")


def _escape(s):
    return str(s or "").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")


def parse(text, item_names):
    """返回 {"ok", "errors":[{"line","msg"}], "more": 被截断的错误数, "maps":[{"name","line","spots":[...]}]}"""
    errors = []

    def err(line, msg):
        errors.append({"line": line, "msg": f"第 {line} 行：{msg}"})

    text = str(text or "")
    if len(text.encode("utf-8")) > MAX_TEXT:
        return {"ok": False, "errors": [{"line": 0, "msg": "文本太长了（上限 200KB）"}], "more": 0, "maps": []}
    names = set(item_names or ())
    maps, cur_map, cur_spot, spot_total = [], None, None, 0
    seen_spots = set()
    for no, raw in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), 1):
        line = _norm(raw)
        if not line or line.startswith("//"):
            continue
        m = _MAP_RE.match(line)
        if m:
            name = m.group(1).strip()
            if not name:
                err(no, "地图要有名字")
            elif len(name) > 30:
                err(no, "地图名最多 30 字")
            if name:
                cur_map = next((x for x in maps if x["name"] == name), None)
                if cur_map is None:
                    cur_map = {"name": name[:30], "line": no, "spots": []}
                    maps.append(cur_map)
            else:
                cur_map = None
            cur_spot = None
            continue
        if line.startswith("@"):
            if cur_map is None:
                err(no, "还没有地图行就出现了地点（先写「# 地图：名字」）")
                cur_spot = None
                continue
            body = _DISABLED_TAIL.sub("", line[1:])
            head, _, desc = body.partition("|")
            toks = head.split()
            xy, rest = {}, []
            for t in toks:
                cm = _COORD_RE.match(t)
                if cm:
                    xy[cm.group(1).lower()] = cm.group(2)
                else:
                    rest.append(t)
            bad = False
            if not rest:
                err(no, "地点要有名字"); bad = True
            if len(rest) > 2:
                err(no, "地点行里多出了内容：格式是「@地点名 图标 x=.. y=.. | 描述」，名字和图标中间不要有空格"); bad = True
            name = rest[0] if rest else ""
            icon = rest[1] if len(rest) > 1 else "📍"
            if len(name) > 30:
                err(no, "地点名最多 30 字"); bad = True
            if len(icon) > 8:
                err(no, "图标最多 8 个字符"); bad = True
            desc = _unescape(desc.strip())
            if len(desc) > 200:
                err(no, "地点描述最多 200 字"); bad = True
            x = y = 50.0
            has_pos = False
            if xy:
                if set(xy) != {"x", "y"}:
                    err(no, "x 和 y 要同时填写"); bad = True
                else:
                    try:
                        x, y = float(xy["x"]), float(xy["y"])
                        if not (0 <= x <= 100 and 0 <= y <= 100) or x != x or y != y:
                            raise ValueError
                        has_pos = True
                    except ValueError:
                        err(no, "x、y 要是 0~100 的数字"); bad = True
            if name and (cur_map["name"], name) in seen_spots:
                err(no, f"地图「{cur_map['name']}」里已经写过地点「{name}」了"); bad = True
            spot_total += 1
            if spot_total == MAX_SPOTS + 1:
                err(no, f"一次最多导入 {MAX_SPOTS} 个地点")
            if bad:
                cur_spot = {"_bad": True, "drops": []}   # 仍会校验它名下的掉落行，一次报全
                continue
            seen_spots.add((cur_map["name"], name))
            cur_spot = {"name": name, "icon": icon, "desc": desc, "x": x, "y": y, "has_pos": has_pos, "line": no, "drops": []}
            cur_map["spots"].append(cur_spot)
            continue
        dm = _DROP_RE.match(line)
        if not dm:
            err(no, "看不懂这一行：应是「# 地图：」「@地点」或「线索/物品/空手」开头")
            continue
        if cur_spot is None:
            err(no, "掉落行前面要先有地点行（@地点名）")
            continue
        kind = KIND_WORDS[dm.group(1).lower() if dm.group(1).isascii() else dm.group(1)]
        wm = _WEIGHT_RE.match(dm.group(2).strip())
        if not wm:
            err(no, "格式不对：类型后面先写权重（整数，可省略），再用 | 分隔内容"); continue
        weight = 1
        if wm.group(1) is not None:
            weight = int(wm.group(1))
        if not 1 <= weight <= 1000:
            err(no, "权重要在 1~1000"); continue
        parts = wm.group(2)[1:] if wm.group(2) else None
        d = {"kind": kind, "weight": weight}
        if kind == "clue":
            title, _, content = (parts or "").partition("|")
            title, content = title.strip(), _unescape(content.strip())
            if not title or not content:
                err(no, "线索要有标题和内容（线索 权重 | 标题 | 内容）"); continue
            if len(title) > 30:
                err(no, "线索标题最多 30 字"); continue
            if len(content) > 600:
                err(no, "线索内容最多 600 字"); continue
            d.update(title=title, text=content)
        elif kind == "item":
            first, _, extra = (parts or "").partition("|")
            first = first.strip()
            if not first:
                err(no, "物品要写名字（物品 权重 | 物品名 ×数量）"); continue
            qty, iname = 1, first
            qm = _ITEM_QTY_RE.match(first)
            if qm:
                iname, qty = qm.group(1).strip(), int(qm.group(2))
            if not iname:
                err(no, "物品要写名字"); continue
            if not 1 <= qty <= 999:
                err(no, "物品数量要在 1~999"); continue
            if len(iname) > 40:
                err(no, "物品名最多 40 字"); continue
            if iname not in names:
                err(no, f"「{iname}」不是注册物品，请从后台物品下拉里确认名字"); continue
            extra = _unescape(extra.strip())
            if len(extra) > 200:
                err(no, "掉落时的一句话最多 200 字"); continue
            d.update(item=iname, qty=qty, text=extra)
        else:
            extra = _unescape((parts or "").strip())
            if len(extra) > 200:
                err(no, "空手时的一句话最多 200 字"); continue
            d.update(text=extra)
        if len(cur_spot["drops"]) >= MAX_DROPS:
            err(no, f"一个地点最多 {MAX_DROPS} 条掉落"); continue
        cur_spot["drops"].append(d)
    if not any(s for m in maps for s in m["spots"]) and not errors:
        errors.append({"line": 0, "msg": "没有读到任何地点"})
    more = max(0, len(errors) - MAX_ERRORS)
    return {"ok": not errors, "errors": errors[:MAX_ERRORS], "more": more, "maps": maps}


def render(maps_payload):
    """explore._maps_payload(db, sid, with_drops=True) 的结果 → 文本。与 parse 语法一致"""
    out = []
    for m in maps_payload:
        out.append(f"# 地图：{m['name']}")
        out.append("")
        for s in m.get("spots", []):
            head = f"@{s['name']} {s.get('icon') or '📍'} x={float(s['x']):.1f} y={float(s['y']):.1f}"
            if s.get("desc"):
                head += " | " + _escape(s["desc"])
            if s.get("enabled") is False:
                head += "  // 停用"
            out.append(head)
            for d in s.get("drops", []):
                w = int(d.get("weight", 1))
                if d["kind"] == "clue":
                    out.append(f"线索 {w} | {str(d['title']).replace('|', '/')} | {_escape(d['text'])}")
                elif d["kind"] == "item":
                    row = f"物品 {w} | {d['item']} ×{int(d.get('qty', 1))}"
                    if d.get("text"):
                        row += " | " + _escape(d["text"])
                    out.append(row)
                else:
                    out.append(f"空手 {w}" + (" | " + _escape(d["text"]) if d.get("text") else ""))
            out.append("")
    return "\n".join(out).rstrip() + "\n" if out else ""


def parse_quota(text, roles):
    """每行「角色名 数字」；「默认 数字」设默认次数。返回 {"errors","warnings","default","rows":[{"role","daily"}]}"""
    errors, warnings, default, rows = [], [], None, {}
    valid = set(roles)
    for no, raw in enumerate(str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"), 1):
        line = raw.replace("　", " ").replace("：", ":").strip()
        if not line or line.startswith("//"):
            continue
        m = re.match(r"^(.+?)[\s:]+(-?\d+)$", line)
        if not m:
            errors.append({"line": no, "msg": f"第 {no} 行：格式是「角色名 数字」（也可以写「默认 数字」）"}); continue
        name, n = m.group(1).strip(), int(m.group(2))
        if not 0 <= n <= 99:
            errors.append({"line": no, "msg": f"第 {no} 行：次数要在 0~99"}); continue
        if name == "默认":
            default = n
            continue
        if name not in valid:
            errors.append({"line": no, "msg": f"第 {no} 行：找不到角色「{name}」"}); continue
        if name in rows:
            warnings.append(f"第 {no} 行：「{name}」出现多次，以最后一次为准")
        rows[name] = n
    if not errors and default is None and not rows:
        errors.append({"line": 0, "msg": "没有读到任何内容"})
    return {"errors": errors[:MAX_ERRORS], "warnings": warnings, "default": default,
            "rows": [{"role": r, "daily": n} for r, n in rows.items()]}

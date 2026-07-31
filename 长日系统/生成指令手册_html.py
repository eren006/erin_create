#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从「生成指令手册.py」生成网页版指令手册。

指令表（SECTIONS/TRADE_SECTION）是纯数据，直接导入即可。
新手向导/开季指南/网页端功能/池子说明这几篇长文档是用 reportlab 的 Paragraph/Table 等
一路拼出来的 PDF 排版代码，不是纯数据——为了不用手抄几千行中文说明、也不用改动
写得好好的 PDF 生成代码，这里用 monkeypatch 把 Paragraph/Table/... 换成"录音笔"：
照样调用 build_dummy_guide() 等函数，但每次调用被换掉的类时不生成 PDF 排版对象，
而是记一条 {"type":..., ...} 的字典，于是原函数跑一遍下来，文字内容原样收集齐了，
一个字都不用手打，PDF 那边也完全没被动过。

用法：python3 生成指令手册_html.py
生成后把 长日系统指令手册.html 传到服务器 static 目录。
"""

import importlib.util
import html as html_escape
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


# ── 第一步：加载源文件，先不碰 reportlab 类，正常拿到 SECTIONS 等纯数据 ──
_spec = importlib.util.spec_from_file_location("cmd_manual_src", os.path.join(HERE, "生成指令手册.py"))
_src = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_src)

SECTIONS = list(_src.SECTIONS)
if hasattr(_src, "TRADE_SECTION"):
    SECTIONS.append(_src.TRADE_SECTION)


# ── 第二步："录音笔"stub：录内容，不排版 ──────────────────────────
class _Rec:
    """所有 stub 的基类：把类型名和构造参数原样存起来，方便调试时打印。"""
    def __init__(self, kind, **data):
        self.kind = kind
        self.data = data

def _StubParagraph(text, style=None, **kw):
    return {"type": "p", "text": text}

class _StubTableStyle:
    def __init__(self, *a, **kw):
        pass
    def add(self, *a, **kw):
        pass

def _StubTable(data, colWidths=None, style=None, repeatRows=None, hAlign=None, rowHeights=None):
    return {"type": "table", "rows": data}

def _StubHR(*a, **kw):
    return {"type": "hr"}

def _StubSpacer(*a, **kw):
    return {"type": "spacer"}

def _StubPageBreak(*a, **kw):
    return {"type": "pagebreak"}

def _StubKeepTogether(items, **kw):
    return {"type": "group", "items": items}


def _patch_and_call(fn_name):
    """把源模块里的 flowable 类换成 stub，跑一遍目标函数，再原样收集结果。"""
    real = {}
    stub_map = {
        "Paragraph": _StubParagraph,
        "Table": _StubTable,
        "TableStyle": _StubTableStyle,
        "HRFlowable": _StubHR,
        "Spacer": _StubSpacer,
        "PageBreak": _StubPageBreak,
        "KeepTogether": _StubKeepTogether,
    }
    for name, stub in stub_map.items():
        real[name] = getattr(_src, name)
        setattr(_src, name, stub)
    try:
        result = getattr(_src, fn_name)()
    finally:
        for name, val in real.items():
            setattr(_src, name, val)
    return result


GUIDES = []  # [(id, icon+title, [node,...])]
_GUIDE_FNS = [
    ("dummy",  "🌸 新手向导 · 开始我的恋综季度", "build_dummy_guide"),
    ("setup",  "🚀 管理员开季指南", "build_setup_guide"),
    ("web",    "🌐 存档网页端 · 功能速查", "build_web_panel"),
    ("pool",   "🧩 补充说明", "build_pool_explainer"),
]
for gid, gtitle, fn in _GUIDE_FNS:
    if hasattr(_src, fn):
        GUIDES.append((gid, gtitle, _patch_and_call(fn)))


# ── 第三步：把 stub 树渲染成 HTML ──────────────────────────────────
def esc(s):
    return html_escape.escape(str(s or ""))

def rl_markup_to_html(text):
    """reportlab 迷你 XML 转 HTML：<br/> <b> <font color='x' size='y'>，其余原样转义。"""
    if text is None:
        return ""
    parts = re.split(r'(<br\s*/?>|<b>|</b>|<font[^>]*>|</font>)', str(text))
    out = []
    for part in parts:
        if part in ("<br/>", "<br>", "<br />"):
            out.append("<br>")
        elif part in ("<b>", "</b>"):
            out.append(part)
        elif part.startswith("<font"):
            m = re.search(r"color=['\"]?(#?\w+)['\"]?", part)
            color = m.group(1) if m else None
            out.append(f'<span style="color:{esc(color)}">' if color else "<span>")
        elif part == "</font>":
            out.append("</span>")
        else:
            out.append(esc(part))
    return "".join(out)


def render_cell(cell):
    """table 的一个单元格：可能是 stub 字典、stub 字典列表、或裸字符串。"""
    if cell is None:
        return ""
    if isinstance(cell, list):
        return "".join(render_node(c) for c in cell)
    if isinstance(cell, dict):
        return render_node(cell)
    return esc(cell)


def render_node(node):
    if node is None:
        return ""
    if isinstance(node, list):
        return "".join(render_node(n) for n in node)
    if isinstance(node, str):
        return f"<p>{esc(node)}</p>"
    kind = node.get("type")

    if kind == "p":
        return f'<p class="g-p">{rl_markup_to_html(node["text"])}</p>'
    if kind == "hr":
        return '<hr class="g-hr">'
    if kind == "spacer":
        return ""
    if kind == "pagebreak":
        return '<div class="g-pagebreak"></div>'
    if kind == "group":
        return "".join(render_node(n) for n in node["items"])
    if kind == "table":
        rows = node["rows"]
        if not rows:
            return ""
        if len(rows) == 1:
            # 单行 = 版式卡片（左右两栏/图标+文案），不当数据表格渲染
            row = rows[0]
            if len(row) == 1:
                return f'<div class="g-box">{render_cell(row[0])}</div>'
            cols_html = "".join(f'<div class="g-col">{render_cell(c)}</div>' for c in row)
            return f'<div class="g-row">{cols_html}</div>'
        # 多行 = 真表格；第一行当表头（若首行文字很短且各cell都是 <p> 独立词，判定为表头）
        body_rows = rows
        thead = ""
        first_texts = [render_cell(c) for c in rows[0]]
        looks_like_header = all(len(t) < 40 for t in first_texts)
        if looks_like_header:
            thead = "<thead><tr>" + "".join(f"<th>{t}</th>" for t in first_texts) + "</tr></thead>"
            body_rows = rows[1:]
        body = "".join(
            "<tr>" + "".join(f"<td>{render_cell(c)}</td>" for c in r) + "</tr>"
            for r in body_rows
        )
        return f'<table class="g-table">{thead}<tbody>{body}</tbody></table>'
    return ""


def render_guide(gid, title, nodes):
    body = "".join(render_node(n) for n in nodes)
    # 去掉最前面多余的 pagebreak 标记（每篇开头基本都以 PageBreak() 起手）
    body = re.sub(r'^(<div class="g-pagebreak"></div>\s*)+', "", body)
    return f'''
    <section class="guide" id="guide-{gid}">
      <button class="guide-head" onclick="toggleGuide('{gid}')">
        <span>{esc(title)}</span><span class="chevron" id="chev-{gid}">▾</span>
      </button>
      <div class="guide-body" id="body-{gid}">{body}</div>
    </section>'''


# ── 指令表渲染（沿用旧版逻辑）──────────────────────────────────────
def render_cmd_name(name, need_dot):
    name = esc(name)
    if need_dot is True:
        return f"。{name}"
    if need_dot == "both":
        return f"{name} <span class=\"dot-note\">（前面加不加句号都行）</span>"
    return name


def render_cmd_section(title, rows):
    parts = [f'<section class="cmd-section" data-title="{esc(title)}">',
             f'<button class="cmd-section-head" onclick="toggleSection(this)"><h2>{esc(title)}</h2>'
             f'<span class="chevron">▾</span></button>',
             '<div class="cmd-list">']
    for name, need_dot, role, desc, usage in rows:
        role_class = "role-admin" if "管理员" in role else "role-player"
        search_blob = esc(f"{name} {desc} {usage}").lower()
        usage_html = f'<pre class="usage">{esc(usage)}</pre>' if usage else ""
        parts.append(f'''
        <div class="cmd-row" data-search="{search_blob}">
          <div class="cmd-head">
            <code class="cmd-name">{render_cmd_name(name, need_dot)}</code>
            <span class="role-badge {role_class}">{esc(role)}</span>
          </div>
          <div class="cmd-desc">{esc(desc)}</div>
          {usage_html}
        </div>''')
    parts.append('</div></section>')
    return "\n".join(parts)


def render_toc():
    items = "".join(f'<a href="#sec-{i}">{esc(title)}</a>' for i, (title, _) in enumerate(SECTIONS))
    return f'<nav class="toc">{items}</nav>'


def render_cmd_sections():
    return "\n".join(f'<div id="sec-{i}">{render_cmd_section(title, rows)}</div>'
                      for i, (title, rows) in enumerate(SECTIONS))


def render_guides():
    return "\n".join(render_guide(gid, title, nodes) for gid, title, nodes in GUIDES)


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>长日将尽 · 指令手册</title>
<style>
:root {{
  --bg:#fbf6ef; --surface:#ffffff; --border:#eadfce;
  --accent:#c0392b; --accent2:#8B4513; --text:#2c2c2c; --muted:#8a7f6e;
  --admin-bg:#fff3e0; --admin-fg:#b45309; --player-bg:#f0faf4; --player-fg:#15803d;
  --tab-inactive:#f1e9db;
}}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#17140f; --surface:#231f18; --border:#3a3428; --accent:#f0a58c; --accent2:#f4c98f;
           --text:#ede6d8; --muted:#a89a82; --admin-bg:#3a2a10; --admin-fg:#f4c98f;
           --player-bg:#12261a; --player-fg:#86efac; --tab-inactive:#211d16; }}
}}
:root[data-theme="dark"] {{ --bg:#17140f; --surface:#231f18; --border:#3a3428; --accent:#f0a58c; --accent2:#f4c98f;
           --text:#ede6d8; --muted:#a89a82; --admin-bg:#3a2a10; --admin-fg:#f4c98f;
           --player-bg:#12261a; --player-fg:#86efac; --tab-inactive:#211d16; }}
:root[data-theme="light"] {{ --bg:#fbf6ef; --surface:#ffffff; --border:#eadfce;
           --accent:#c0392b; --accent2:#8B4513; --text:#2c2c2c; --muted:#8a7f6e;
           --admin-bg:#fff3e0; --admin-fg:#b45309; --player-bg:#f0faf4; --player-fg:#15803d;
           --tab-inactive:#f1e9db; }}
*{{box-sizing:border-box;}}
body{{margin:0;background:var(--bg);color:var(--text);font-family:"PingFang SC","Microsoft YaHei",sans-serif;font-size:14px;line-height:1.7;}}
.topbar{{position:sticky;top:0;z-index:100;background:var(--surface);border-bottom:1px solid var(--border);
  padding:14px 20px 0;display:flex;flex-direction:column;gap:10px;}}
.topbar h1{{margin:0;font-size:18px;color:var(--accent2);}}
.tabs{{display:flex;gap:4px;}}
.tab-btn{{flex:1;text-align:center;padding:10px 8px;border:none;background:var(--tab-inactive);
  color:var(--muted);font-size:14px;font-weight:600;border-radius:10px 10px 0 0;cursor:pointer;}}
.tab-btn.active{{background:var(--bg);color:var(--accent);}}
#search{{width:100%;padding:9px 14px;border-radius:10px;border:1px solid var(--border);
  background:var(--bg);color:var(--text);font-size:14px;}}
#search:focus{{outline:none;border-color:var(--accent);}}
#matchCount{{font-size:12px;color:var(--muted);}}
.tab-panel{{display:none;}}
.tab-panel.active{{display:block;}}

.toc{{display:flex;flex-wrap:wrap;gap:6px;padding:10px 20px;background:var(--surface);border-bottom:1px solid var(--border);}}
.toc a{{font-size:12px;color:var(--muted);text-decoration:none;padding:4px 10px;border-radius:20px;background:var(--bg);border:1px solid var(--border);white-space:nowrap;}}
.toc a:hover{{color:var(--accent);border-color:var(--accent);}}

.page{{max-width:880px;margin:0 auto;padding:16px 20px 40px;}}

/* 指南 tab */
.guide{{background:var(--surface);border:1px solid var(--border);border-radius:12px;margin-bottom:12px;overflow:hidden;}}
.guide-head{{width:100%;text-align:left;background:none;border:none;padding:14px 16px;font-size:15px;font-weight:700;
  color:var(--accent2);cursor:pointer;display:flex;justify-content:space-between;align-items:center;}}
.guide-body{{display:none;padding:0 18px 16px;}}
.guide-body.open{{display:block;}}
.chevron{{transition:transform .15s;color:var(--muted);}}
.chevron.rot{{transform:rotate(180deg);}}
.g-p{{font-size:13.5px;margin:6px 0;}}
.g-hr{{border:none;border-top:1px solid var(--border);margin:10px 0;}}
.g-pagebreak{{border-top:2px dashed var(--border);margin:18px 0;}}
.g-row{{display:flex;gap:14px;background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:10px 14px;margin:10px 0;}}
.g-col{{flex:1;min-width:0;}}
.g-col:first-child{{flex:0 0 auto;max-width:120px;}}
.g-box{{background:var(--admin-bg);border-radius:8px;padding:8px 12px;margin:6px 0;font-weight:600;}}
table.g-table{{width:100%;border-collapse:collapse;margin:10px 0;font-size:13px;}}
table.g-table th{{background:var(--admin-bg);color:var(--admin-fg);text-align:left;padding:6px 10px;font-size:12.5px;}}
table.g-table td{{border-top:1px solid var(--border);padding:7px 10px;vertical-align:top;}}
table.g-table tr:nth-child(even) td{{background:var(--bg);}}

/* 指令 tab */
.cmd-section{{margin-top:14px;}}
.cmd-section-head{{width:100%;display:flex;justify-content:space-between;align-items:center;
  background:none;border:none;border-bottom:2px solid var(--border);padding:6px 0;cursor:pointer;}}
.cmd-section-head h2{{font-size:16px;color:var(--accent);margin:0;}}
.cmd-list{{display:none;}}
.cmd-list.open{{display:block;}}
.cmd-row{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 16px;margin:10px 0;}}
.cmd-head{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:4px;}}
.cmd-name{{font-size:14px;font-weight:700;color:var(--text);background:none;}}
.dot-note{{font-weight:400;font-size:11px;color:var(--muted);}}
.role-badge{{font-size:11px;padding:2px 9px;border-radius:20px;font-weight:600;white-space:nowrap;}}
.role-admin{{background:var(--admin-bg);color:var(--admin-fg);}}
.role-player{{background:var(--player-bg);color:var(--player-fg);}}
.cmd-desc{{font-size:13px;color:var(--text);}}
.usage{{margin-top:8px;background:var(--bg);border:1px solid var(--border);border-radius:8px;
  padding:8px 12px;font-size:12.5px;color:var(--muted);white-space:pre-wrap;font-family:"SF Mono",Consolas,monospace;overflow-x:auto;}}
.cmd-row.hidden, .cmd-section.hidden{{display:none;}}
.empty-hint{{text-align:center;color:var(--muted);padding:40px 0;display:none;}}
footer{{text-align:center;color:var(--muted);font-size:11px;padding:20px 0;}}
</style>
</head>
<body>
<div class="topbar">
  <h1>📖 长日将尽 · 指令手册</h1>
  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('guides')" id="tabbtn-guides">📘 新手指南</button>
    <button class="tab-btn" onclick="switchTab('cmds')" id="tabbtn-cmds">📋 指令查找</button>
  </div>
</div>

<div class="tab-panel active" id="panel-guides">
  <div class="page">
{guides}
  </div>
</div>

<div class="tab-panel" id="panel-cmds">
  <div class="topbar" style="position:static;border:none;padding:10px 20px;">
    <input id="search" type="text" placeholder="搜索指令、关键词或用法…" autocomplete="off">
    <div id="matchCount"></div>
  </div>
  {toc}
  <div class="page" id="content">
{sections}
    <div class="empty-hint" id="emptyHint">没有找到匹配的指令，换个关键词试试。</div>
  </div>
</div>

<footer>长日将尽系统 · 指令手册</footer>
<script>
function switchTab(name) {{
  document.getElementById('panel-guides').classList.toggle('active', name === 'guides');
  document.getElementById('panel-cmds').classList.toggle('active', name === 'cmds');
  document.getElementById('tabbtn-guides').classList.toggle('active', name === 'guides');
  document.getElementById('tabbtn-cmds').classList.toggle('active', name === 'cmds');
}}
function toggleGuide(gid) {{
  document.getElementById('body-' + gid).classList.toggle('open');
  document.getElementById('chev-' + gid).classList.toggle('rot');
}}
function toggleSection(headEl) {{
  const list = headEl.nextElementSibling;
  list.classList.toggle('open');
  headEl.querySelector('.chevron').classList.toggle('rot');
}}

// 默认展开第一篇指南
document.addEventListener('DOMContentLoaded', () => {{
  const firstBody = document.querySelector('.guide-body');
  const firstChev = document.querySelector('.chevron');
  if (firstBody) firstBody.classList.add('open');
  if (firstChev) firstChev.classList.add('rot');
}});

const search = document.getElementById('search');
const rows = Array.from(document.querySelectorAll('.cmd-row'));
const sections = Array.from(document.querySelectorAll('.cmd-section'));
const matchCount = document.getElementById('matchCount');
const emptyHint = document.getElementById('emptyHint');

function applyFilter() {{
  const q = search.value.trim().toLowerCase();
  let visible = 0;
  rows.forEach(r => {{
    const hit = !q || r.dataset.search.includes(q);
    r.classList.toggle('hidden', !hit);
    if (hit) visible++;
  }});
  sections.forEach(sec => {{
    const anyVisible = sec.querySelectorAll('.cmd-row:not(.hidden)').length > 0;
    sec.classList.toggle('hidden', !anyVisible);
    const list = sec.querySelector('.cmd-list');
    const head = sec.querySelector('.cmd-section-head');
    if (q && anyVisible) {{
      list.classList.add('open');
      head.querySelector('.chevron').classList.add('rot');
    }} else if (!q) {{
      list.classList.remove('open');
      head.querySelector('.chevron').classList.remove('rot');
    }}
  }});
  matchCount.textContent = q ? `共 ${{visible}} 条匹配` : '';
  emptyHint.style.display = (q && visible === 0) ? 'block' : 'none';
}}
search.addEventListener('input', applyFilter);
</script>
</body>
</html>
"""


def main():
    html_content = PAGE_TEMPLATE.format(
        guides=render_guides(),
        toc=render_toc(),
        sections=render_cmd_sections(),
    )
    out_path = os.path.join(HERE, "长日系统指令手册.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✅ HTML 已生成：{out_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从「生成指令手册.py」的 SECTIONS 生成一份玩家专用的功能一览页——
跟给管理员看的「长日系统指令手册.html」共用同一份数据源，但只保留玩家可用的条目，
排版换成更直观的卡片式（按功能分类，不再是密密麻麻的表格）。

用法：python3 生成玩家指南_html.py
生成后把 长日系统玩家指南.html 传到服务器 static 目录。
"""

import html as html_escape
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))

_spec = importlib.util.spec_from_file_location("cmd_manual_src", os.path.join(HERE, "生成指令手册.py"))
_src = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_src)

SECTIONS = list(_src.SECTIONS)
if hasattr(_src, "TRADE_SECTION"):
    SECTIONS.append(_src.TRADE_SECTION)


def esc(s):
    return html_escape.escape(str(s or ""), quote=True)


def is_player_visible(perm):
    """权限字段形如 "玩家" / "管理员" / "玩家/管理员" / "管理员/骰主"，含"玩家"才算玩家可用。"""
    return "玩家" in (perm or "")


# ── 过滤：只留玩家可见条目，丢弃过滤后变空的分区 ──────────────────────────
player_sections = []
for title, entries in SECTIONS:
    kept = [e for e in entries if is_player_visible(e[2]) and not str(e[0]).startswith("💡")]
    if kept:
        player_sections.append((title, kept))

total_cmds = sum(len(entries) for _, entries in player_sections)


def render_section(title, entries):
    icon = title.split(" ", 1)[0]
    name = title.split(" ", 1)[1] if " " in title else title
    cards = []
    for cmd, _typ, _perm, desc, example in entries:
        cmd_disp = esc(cmd)
        desc_disp = esc(desc)
        example_html = ""
        if example:
            lines = "\n".join(esc(l) for l in str(example).split("\n"))
            example_html = f'<pre class="ex">{lines}</pre>'
        cards.append(f"""
        <div class="cmd-card" data-search="{cmd_disp.lower()} {desc_disp.lower()}">
          <div class="cmd-name">{cmd_disp}</div>
          <div class="cmd-desc">{desc_disp}</div>
          {example_html}
        </div>""")
    previews = "".join(f'<span>{esc(e[0])}</span>' for e in entries[:3])
    return f"""
  <details class="feat-section" id="sec-{esc(name)}">
    <summary>
      <h2><span class="feat-icon">{icon}</span><span>{esc(name)}</span></h2>
      <div class="section-preview">{previews}</div>
      <span class="section-count">{len(entries):02d}</span>
      <span class="section-arrow" aria-hidden="true">⌄</span>
    </summary>
    <div class="cmd-grid">
      {"".join(cards)}
    </div>
  </details>"""


sections_html = "\n".join(render_section(t, e) for t, e in player_sections)

toc_html = "\n".join(
    f'<a href="#sec-{esc(t.split(" ", 1)[1] if " " in t else t)}">{esc(t)}</a>'
    for t, _ in player_sections
)

HTML = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>玩家功能一览</title>
<style>
:root {{
  --bg:#fbf6ef; --surface:#ffffff; --border:#eadfce;
  --accent:#c0392b; --accent2:#8B4513; --text:#2c2c2c; --muted:#8a7f6e;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{ --bg:#17140f; --surface:#231f18; --border:#3a3428;
    --accent:#f0a58c; --accent2:#f4c98f; --text:#ecdfc8; --muted:#a99a80; }}
}}
:root[data-theme="dark"] {{ --bg:#17140f; --surface:#231f18; --border:#3a3428;
    --accent:#f0a58c; --accent2:#f4c98f; --text:#ecdfc8; --muted:#a99a80; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text);
  font-family:"PingFang SC","Microsoft YaHei",sans-serif; font-size:14px; line-height:1.7; }}
.topbar {{ position:sticky; top:0; z-index:10; background:var(--surface); border-bottom:1px solid var(--border);
  padding:14px 20px; display:flex; align-items:center; gap:16px; flex-wrap:wrap; }}
.topbar h1 {{ margin:0; font-size:18px; color:var(--accent2); }}
.topbar .sub {{ font-size:12px; color:var(--muted); }}
#search {{ margin-left:auto; padding:7px 14px; border-radius:20px; border:1px solid var(--border);
  background:var(--bg); color:var(--text); font-size:13px; width:220px; }}
#search:focus {{ outline:none; border-color:var(--accent); }}
.wrap {{ max-width:960px; margin:0 auto; padding:20px; }}
.intro {{ background:var(--surface); border:1px solid var(--border); border-radius:14px;
  padding:16px 20px; margin-bottom:20px; color:var(--muted); font-size:13px; }}
.toc {{ display:flex; flex-wrap:wrap; gap:6px; margin-bottom:26px; }}
.toc a {{ font-size:12px; color:var(--muted); text-decoration:none; padding:5px 12px;
  border-radius:20px; background:var(--surface); border:1px solid var(--border); white-space:nowrap; }}
.toc a:hover {{ color:var(--accent); border-color:var(--accent); }}
.feat-section {{ margin-bottom:34px; }}
.feat-section h2 {{ font-size:16px; color:var(--accent2); margin:0 0 12px;
  display:flex; align-items:center; gap:8px; }}
.feat-icon {{ font-size:20px; }}
.cmd-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:10px; }}
.cmd-card {{ background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:14px 16px; }}
.cmd-name {{ font-weight:700; color:var(--accent); font-size:13.5px; margin-bottom:6px; }}
.cmd-desc {{ color:var(--text); font-size:13px; }}
.ex {{ margin:10px 0 0; background:var(--bg); border:1px solid var(--border); border-radius:8px;
  padding:8px 10px; font-size:12px; color:var(--muted); white-space:pre-wrap; word-break:break-all;
  font-family:inherit; }}
[hidden] {{ display:none !important; }}
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;1,500&family=Noto+Serif+SC:wght@400;600&display=swap');
:root{{--bg:#d8cfb7;--surface:#f5f0e2;--border:#c9bea2;--accent:#8f2f2a;--accent2:#233f35;--text:#2d3028;--muted:#746e5d}}
body{{background:#273b32;font-family:"Noto Serif SC",serif}}
body:before{{content:"";position:fixed;inset:0;background:rgba(26,39,33,.08);pointer-events:none}}
body:after{{content:"";position:fixed;z-index:100;inset:0;pointer-events:none;opacity:.18;mix-blend-mode:multiply;background-image:repeating-radial-gradient(circle at 20% 30%,rgba(72,59,35,.16) 0 1px,transparent 1px 4px);background-size:5px 5px}}
.topbar{{background:rgba(245,240,226,.92);border:0;border-bottom:1px solid rgba(70,60,42,.25);backdrop-filter:blur(14px);padding:12px max(20px,calc((100vw - 960px)/2));}}
.topbar h1{{font-family:"Cormorant Garamond","Noto Serif SC",serif;color:var(--accent2);font-size:20px}}
.hero-scroll{{position:relative;min-height:560px;display:grid;place-items:center;padding:80px 20px 130px;text-align:center;color:#f4ead4;background-image:linear-gradient(rgba(22,34,28,.12),rgba(22,34,28,.32)),url('assets/player-guide-renaissance-v2.jpg');background-position:center;background-size:cover;background-repeat:no-repeat}}
.hero-scroll:after{{content:"";position:absolute;inset:auto 0 0;height:160px;background:linear-gradient(transparent,#d8cfb7)}}
.hero-inner{{position:relative;z-index:1;max-width:800px;text-shadow:0 2px 16px rgba(0,0,0,.35)}}
.hero-kicker{{font:600 12px/1 "Noto Serif SC",serif;letter-spacing:.3em;text-transform:uppercase}}
.hero-scroll h2{{font:italic 500 clamp(56px,9vw,112px)/.9 "Cormorant Garamond","Noto Serif SC",serif;margin:24px 0 18px;letter-spacing:-.045em}}
.hero-scroll p{{font-size:14px;letter-spacing:.13em}}
.hero-mark{{width:52px;height:52px;margin:0 auto 22px;border:1px solid rgba(255,255,255,.65);border-radius:50%;display:grid;place-items:center;font:italic 26px "Cormorant Garamond"}}
.wrap{{position:relative;max-width:960px;background:var(--surface);padding:58px 68px 90px;box-shadow:0 24px 80px rgba(24,18,8,.3)}}
.wrap{{background-image:linear-gradient(90deg,rgba(130,112,72,.035) 1px,transparent 1px),linear-gradient(rgba(130,112,72,.025) 1px,transparent 1px);background-size:27px 27px}}
.wrap:before,.wrap:after{{content:"✦  ❧  ✦";display:block;text-align:center;color:#9d8c69;letter-spacing:1.2em;margin-bottom:34px}}
.wrap:after{{margin:55px 0 0}}
.intro{{border:0;border-radius:0;padding:24px 8%;text-align:center;background:transparent;color:#665f4f;font-size:14px;line-height:2;border-top:1px solid var(--border);border-bottom:1px solid var(--border)}}
.toc{{justify-content:center;margin:28px 0 50px}}
.toc a{{background:transparent;border:0;border-bottom:1px solid transparent;border-radius:0;padding:5px 9px;color:#6b6557}}
.toc a:hover{{border-color:var(--accent);color:var(--accent)}}
.feat-section{{margin-bottom:56px;scroll-margin-top:80px}}
.guide-main{{counter-reset:chapter}}
.feat-section{{counter-increment:chapter;position:relative}}
.feat-section h2:after{{content:"CHAPTER " counter(chapter,decimal-leading-zero);margin-left:auto;font:500 9px/1 "Cormorant Garamond",serif;letter-spacing:.18em;color:#a39477}}
.feat-section:before{{content:"❦";position:absolute;right:-30px;top:62px;color:#b5a47f;font-size:18px;opacity:.55;transform:rotate(12deg)}}
.feat-section h2{{font:italic 600 34px "Cormorant Garamond","Noto Serif SC",serif;color:var(--accent2);gap:12px;padding-bottom:12px;border-bottom:1px solid var(--border)}}
.cmd-grid{{grid-template-columns:repeat(2,minmax(0,1fr));gap:0 30px}}
.cmd-card{{background:transparent;border:0;border-bottom:1px solid rgba(120,105,75,.22);border-radius:0;padding:20px 4px;transition:transform .2s,background .2s}}
.cmd-card:hover{{transform:translateX(5px);background:rgba(255,255,255,.28)}}
.cmd-name{{font:600 16px "Noto Serif SC",serif;color:var(--accent);margin-bottom:8px}}
.cmd-desc{{line-height:1.8;color:#4d4a40}}
.ex{{background:#e9dec6;border:0;border-left:2px solid #9b8770;border-radius:0;padding:10px 12px;font-family:"Noto Serif SC",serif;color:#6d6253}}
#search{{background:rgba(255,255,255,.65);border-color:#baae93;color:#3f3c34}}
@media(max-width:700px){{.hero-scroll{{min-height:460px}}.wrap{{padding:38px 20px 60px}}.cmd-grid{{grid-template-columns:1fr}}.topbar .sub{{display:none}}#search{{width:150px}}}}
.menu-toggle{{display:none;border:1px solid #baae93;background:transparent;color:var(--accent2);border-radius:999px;padding:7px 12px;font-family:inherit;cursor:pointer}}
.wrap{{max-width:1180px;padding:48px 46px 80px}}
.guide-layout{{display:grid;grid-template-columns:230px minmax(0,1fr);gap:52px;align-items:start}}
.side-panel{{position:sticky;top:76px;max-height:calc(100vh - 96px);overflow:auto;padding:8px 0 28px;border-right:1px solid var(--border)}}
.side-head{{padding:0 22px 14px 0;font:600 11px "Noto Serif SC",serif;color:#91866f;letter-spacing:.18em}}
.side-close{{display:none}}
.toc{{display:flex;flex-direction:column;align-items:stretch;gap:2px;margin:0;padding-right:22px}}
.toc a{{display:block;padding:9px 11px;border:0;border-radius:7px;font-size:12px;color:#6b6557;transition:background .18s,color .18s}}
.toc a:hover,.toc a.active{{background:#e9dec6;color:var(--accent)}}
.guide-main{{min-width:0}}
.guide-main .intro{{margin-bottom:44px}}
.nav-scrim{{display:none}}
.mobile-dock{{display:none}}
.desk-pet{{position:fixed;z-index:34;right:14px;bottom:16px;width:108px;border:0;background:transparent;padding:0;cursor:pointer;filter:drop-shadow(0 10px 12px rgba(35,26,14,.22));transform-origin:50% 100%;animation:petBreathe 3.8s ease-in-out infinite}}
.desk-pet img{{display:block;width:100%;height:auto;pointer-events:none;transition:opacity .14s ease,transform .22s ease}}.desk-pet:hover{{animation:petWave .7s ease-in-out}}.desk-pet.is-happy{{animation:petHop .65s ease}}.desk-pet.is-changing img{{opacity:.25;transform:scale(.92)}}
.pet-bubble{{position:fixed;z-index:36;right:96px;bottom:112px;max-width:180px;padding:9px 12px;border:1px solid #c7b996;border-radius:14px 14px 3px 14px;background:#f7efd9;color:#4b463a;box-shadow:0 8px 22px rgba(35,26,14,.15);font-size:11px;line-height:1.55;opacity:0;transform:translateY(8px);pointer-events:none;transition:opacity .2s,transform .2s}}.pet-bubble.show{{opacity:1;transform:none}}
@keyframes petBreathe{{0%,100%{{transform:translateY(0) rotate(-.5deg)}}50%{{transform:translateY(-7px) rotate(.6deg)}}}}@keyframes petWave{{0%,100%{{transform:rotate(0)}}35%{{transform:rotate(-4deg)}}70%{{transform:rotate(3deg)}}}}@keyframes petHop{{0%,100%{{transform:translateY(0) scale(1)}}45%{{transform:translateY(-18px) scale(1.03)}}}}
.reading-progress{{position:fixed;z-index:120;top:0;left:0;height:2px;width:0;background:linear-gradient(90deg,#b88a46,#8f2f2a);box-shadow:0 0 10px rgba(184,138,70,.45);pointer-events:none}}
.feat-section{{margin:0 0 12px;border:1px solid rgba(128,108,73,.28);border-radius:18px;background:rgba(250,247,237,.72);box-shadow:0 7px 22px rgba(54,42,20,.055);overflow:hidden;transition:border-color .25s,box-shadow .25s,background .25s}}
.feat-section[open]{{margin-bottom:22px;background:rgba(250,247,237,.94);border-color:#b9a57e;box-shadow:0 18px 42px rgba(54,42,20,.11)}}
.feat-section>summary{{position:relative;min-height:92px;display:grid;grid-template-columns:minmax(210px,.8fr) minmax(260px,1.2fr) 42px 28px;align-items:center;gap:18px;padding:18px 22px;cursor:pointer;list-style:none;user-select:none}}
.feat-section>summary::-webkit-details-marker{{display:none}}
.feat-section>summary:hover{{background:rgba(232,220,194,.36)}}
.feat-section h2{{margin:0;padding:0;border:0;font:600 22px/1.25 "Noto Serif SC",serif;display:flex;align-items:center;min-width:0}}
.feat-section h2:after{{display:none}}
.feat-icon{{width:34px;flex:0 0 34px;font-size:19px}}
.section-preview{{display:flex;gap:7px;min-width:0;overflow:hidden}}
.section-preview span{{max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:5px 9px;border:1px solid rgba(135,113,75,.18);border-radius:999px;background:rgba(255,255,255,.46);color:#857b67;font-size:10.5px}}
.section-count{{font:600 12px/1 "Cormorant Garamond",serif;letter-spacing:.12em;color:#9a8868;text-align:center}}
.section-arrow{{display:grid;place-items:center;width:26px;height:26px;border-radius:50%;color:#6c624f;background:#e9dec6;transition:transform .28s,background .2s}}
.feat-section[open] .section-arrow{{transform:rotate(180deg);background:#294a3d;color:#f7efdc}}
.feat-section[open] .section-preview{{opacity:.36}}
.feat-section>.cmd-grid{{padding:4px 24px 26px;border-top:1px solid rgba(128,108,73,.18);background:linear-gradient(180deg,rgba(236,226,204,.24),transparent 70px)}}
.feat-section:before{{display:none}}
.ornament-left,.ornament-right{{position:absolute;z-index:0;top:42%;font:italic 140px/1 "Cormorant Garamond",serif;color:rgba(116,101,66,.08);pointer-events:none;user-select:none}}
.ornament-left{{left:-46px;transform:rotate(-90deg)}}.ornament-right{{right:-36px;transform:rotate(90deg)}}
.reveal{{opacity:0;transform:translateY(18px);transition:opacity .7s ease,transform .7s cubic-bezier(.2,.8,.2,1)}}.reveal.is-visible{{opacity:1;transform:none}}
@media(max-width:760px){{
  body{{padding-bottom:82px}}.topbar{{position:absolute;top:0;width:100%;flex-wrap:nowrap;padding:16px 18px;background:linear-gradient(rgba(24,35,29,.46),transparent);border:0;backdrop-filter:none}}.topbar h1{{font-size:14px;color:#f4ead4;text-shadow:0 1px 8px rgba(0,0,0,.35)}}.topbar .sub,.menu-toggle{{display:none}}#search{{width:116px;margin-left:auto;padding:8px 12px;background:rgba(245,240,226,.9);border:0;color:#39352e;font-size:12px}}#search::placeholder{{color:#716b5e}}
  .hero-scroll{{min-height:440px;padding:92px 18px 82px;background-image:linear-gradient(rgba(22,34,28,.08),rgba(22,34,28,.28)),url('assets/player-guide-renaissance-v2.jpg');background-position:center;background-size:auto 100%;background-repeat:no-repeat;background-color:#69705c}}.hero-scroll h2{{font-size:62px;margin:18px 0 12px}}.hero-kicker{{font-size:8px;letter-spacing:.22em}}.hero-scroll p{{font-size:10px;letter-spacing:.08em}}.hero-mark{{width:44px;height:44px;font-size:22px}}
  .wrap{{z-index:2;margin-top:-28px;padding:38px 18px 64px;width:calc(100% - 16px);border-radius:28px 28px 0 0;box-shadow:0 -12px 36px rgba(30,23,12,.2)}}.wrap:before{{font-size:11px;margin-bottom:24px}}.guide-layout{{display:block}}
  .side-panel{{position:fixed;z-index:50;left:0;top:0;width:min(86vw,336px);height:100dvh;max-height:none;padding:28px 20px;background:linear-gradient(145deg,#f7f0dc,#e9dec5);border:0;box-shadow:18px 0 50px rgba(20,15,8,.32);transform:translateX(-105%);transition:transform .28s cubic-bezier(.2,.8,.2,1);overflow-y:auto}}
  body.nav-open .side-panel{{transform:translateX(0)}}.side-head{{display:flex;justify-content:space-between;align-items:center;padding:0 4px 18px}}.side-close{{display:grid;place-items:center;width:34px;height:34px;border:1px solid var(--border);border-radius:50%;background:transparent;font-size:18px}}
  .toc{{padding:0;gap:3px}}.toc a{{font-size:14px;padding:12px 13px;border-bottom:1px solid rgba(130,110,75,.12);border-radius:8px}}
  .nav-scrim{{display:block;position:fixed;z-index:40;inset:0;background:rgba(239,230,207,.12);opacity:0;pointer-events:none;transition:opacity .25s}}body.nav-open .nav-scrim{{opacity:1;pointer-events:auto}}
  .guide-main .intro{{margin-bottom:28px;padding:20px 8px;font-size:13px;line-height:1.9}}.cmd-grid{{grid-template-columns:1fr;gap:0}}.feat-section{{margin-bottom:10px;border-radius:15px}}.feat-section[open]{{margin-bottom:16px}}.feat-section>summary{{min-height:78px;grid-template-columns:1fr 34px 24px;gap:8px;padding:14px 15px}}.feat-section h2{{font-size:17px;flex-wrap:nowrap}}.feat-icon{{width:30px;flex-basis:30px;font-size:17px}}.section-preview{{grid-column:1/-1;grid-row:2;gap:5px;margin-left:30px}}.section-preview span{{max-width:112px;padding:3px 7px;font-size:9px}}.section-count{{grid-column:2;grid-row:1}}.section-arrow{{grid-column:3;grid-row:1;width:23px;height:23px}}.feat-section>.cmd-grid{{padding:2px 15px 20px}}.cmd-card{{padding:18px 8px}}.cmd-card:hover{{transform:none}}.cmd-name{{font-size:15px}}.cmd-desc{{font-size:13px;line-height:1.75}}.ex{{font-size:11.5px;border-radius:8px;border-left:0;padding:12px}}.ornament-left,.ornament-right{{display:none}}
  .mobile-dock{{position:fixed;z-index:35;left:50%;bottom:max(14px,env(safe-area-inset-bottom));transform:translateX(-50%);display:flex;gap:4px;padding:5px;background:rgba(35,46,39,.91);border:1px solid rgba(255,255,255,.18);border-radius:999px;box-shadow:0 12px 34px rgba(15,12,7,.3);backdrop-filter:blur(16px)}}.mobile-dock button{{min-width:116px;border:0;border-radius:999px;padding:12px 18px;background:transparent;color:#e9dfca;font:600 13px "Noto Serif SC",serif}}.mobile-dock button:first-child{{background:#f0e6d1;color:#263c33}}
  .desk-pet{{right:6px;bottom:76px;width:62px}}.pet-bubble{{right:54px;bottom:132px;max-width:150px;font-size:10.5px}}
}}
@media(prefers-reduced-motion:reduce){{.side-panel,.nav-scrim{{transition:none}}}}
@media(prefers-reduced-motion:reduce){{.reveal{{opacity:1;transform:none;transition:none}}.desk-pet{{animation:none}}}}
</style>
</head>
<body>
<div class="reading-progress" id="readingProgress"></div>
<div class="topbar">
  <button class="menu-toggle" id="menuToggle" aria-expanded="false" aria-controls="sidePanel">☰ 目录</button>
  <h1>🎮 玩家功能一览</h1>
  <span class="sub">共 {total_cmds} 项</span>
  <input type="text" id="search" placeholder="搜索功能…">
</div>
<header class="hero-scroll">
  <div class="hero-inner">
    <div class="hero-mark">长</div>
    <div class="hero-kicker">An Almanac for Every Encounter</div>
    <h2>长日将尽</h2>
    <p>玩家功能手册 · THE PLAYER'S COMPENDIUM</p>
  </div>
</header>
<div class="wrap">
  <span class="ornament-left">Flora</span><span class="ornament-right">Lunga</span>
  <div class="guide-layout">
  <aside class="side-panel" id="sidePanel">
    <div class="side-head"><span>功能目录</span><button class="side-close" id="sideClose" aria-label="关闭目录">×</button></div>
    <nav class="toc">
      {toc_html}
    </nav>
  </aside>
  <main class="guide-main">
  <div class="intro">
    欢迎来到长日系统！这里是指令导览，请注意，并非所有指令都在开启状态，请在使用前查看公告群或者询问管理是否开启某系统！
  </div>
  {sections_html}
  </main>
  </div>
</div>
<div class="nav-scrim" id="navScrim"></div>
<div class="mobile-dock" aria-label="移动端快捷操作">
  <button id="dockMenu">☰ 章节目录</button>
  <button id="dockSearch">⌕ 搜索</button>
</div>
<div class="pet-bubble" id="petBubble" role="status"></div>
<button class="desk-pet" id="deskPet" aria-label="点击切换兔耳向导的动作"><img id="petImage" src="assets/player-guide-bunny-idle-v2.png" alt=""></button>
<script>
var menuToggle = document.getElementById('menuToggle');
function setNav(open) {{
  document.body.classList.toggle('nav-open', open);
  menuToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
}}
menuToggle.addEventListener('click', function() {{ setNav(!document.body.classList.contains('nav-open')); }});
document.getElementById('sideClose').addEventListener('click', function() {{ setNav(false); }});
document.getElementById('navScrim').addEventListener('click', function() {{ setNav(false); }});
document.getElementById('dockMenu').addEventListener('click', function() {{ setNav(true); }});
document.getElementById('dockSearch').addEventListener('click', function() {{
  window.scrollTo({{top:0,behavior:'smooth'}});
  setTimeout(function() {{ document.getElementById('search').focus(); }}, 350);
}});
var petStates=[
  {{src:'assets/player-guide-bunny-idle-v2.png',line:'今天想找什么指令？'}},
  {{src:'assets/player-guide-bunny-wave-v2.png',line:'欢迎回来，要一起翻手册吗？'}},
  {{src:'assets/player-guide-bunny-surprise-v2.png',line:'咦，发现新的指令了！'}},
  {{src:'assets/player-guide-bunny-shy-v2.png',line:'再点一下，我还有别的表情。'}}
];
petStates.forEach(function(state){{var preload=new Image();preload.src=state.src}});
var petStateIndex=0;
var petTimer;
document.getElementById('deskPet').addEventListener('click',function(){{
  var pet=this,bubble=document.getElementById('petBubble');
  petStateIndex=(petStateIndex+1)%petStates.length;
  var state=petStates[petStateIndex],image=document.getElementById('petImage');
  pet.classList.add('is-changing');
  setTimeout(function(){{image.src=state.src;pet.classList.remove('is-changing')}},120);
  bubble.textContent=state.line;
  bubble.classList.add('show');pet.classList.remove('is-happy');void pet.offsetWidth;pet.classList.add('is-happy');
  clearTimeout(petTimer);petTimer=setTimeout(function(){{bubble.classList.remove('show')}},2800);
}});
document.querySelectorAll('.toc a').forEach(function(link) {{
  link.addEventListener('click', function() {{
    document.querySelectorAll('.toc a').forEach(function(a) {{ a.classList.toggle('active', a === link); }});
    var target=document.querySelector(link.getAttribute('href'));
    if(target){{target.open=true;setTimeout(function(){{target.scrollIntoView({{behavior:'smooth',block:'start'}})}},60)}}
    setNav(false);
  }});
}});
var sections = Array.from(document.querySelectorAll('.feat-section'));
sections.forEach(function(section){{
  section.addEventListener('toggle',function(){{
    if(!section.open || document.body.classList.contains('is-searching'))return;
    sections.forEach(function(other){{if(other!==section)other.open=false}});
  }});
}});
sections.forEach(function(section) {{ section.classList.add('reveal'); }});
var revealObserver = new IntersectionObserver(function(entries) {{
  entries.forEach(function(entry) {{ if (entry.isIntersecting) entry.target.classList.add('is-visible'); }});
}}, {{rootMargin:'0px 0px -8% 0px',threshold:.05}});
sections.forEach(function(section) {{ revealObserver.observe(section); }});
var activeObserver = new IntersectionObserver(function(entries) {{
  entries.forEach(function(entry) {{
    if (!entry.isIntersecting) return;
    document.querySelectorAll('.toc a').forEach(function(a) {{
      a.classList.toggle('active', decodeURIComponent(a.getAttribute('href').slice(1)) === entry.target.id);
    }});
  }});
}}, {{rootMargin:'-20% 0px -65% 0px'}});
sections.forEach(function(section) {{ activeObserver.observe(section); }});
function updateProgress() {{
  var max = document.documentElement.scrollHeight - innerHeight;
  document.getElementById('readingProgress').style.width = (max > 0 ? scrollY / max * 100 : 0) + '%';
}}
addEventListener('scroll', updateProgress, {{passive:true}}); updateProgress();
document.addEventListener('keydown', function(e) {{ if (e.key === 'Escape') setNav(false); }});
document.getElementById('search').addEventListener('input', function(e) {{
  var q = e.target.value.trim().toLowerCase();
  document.body.classList.toggle('is-searching',!!q);
  document.querySelectorAll('.cmd-card').forEach(function(card) {{
    var hit = !q || (card.dataset.search || '').includes(q);
    card.hidden = !hit;
  }});
  document.querySelectorAll('.feat-section').forEach(function(sec) {{
    var anyVisible = Array.from(sec.querySelectorAll('.cmd-card')).some(function(c) {{ return !c.hidden; }});
    sec.hidden = !anyVisible;
    if(q && anyVisible) sec.open = true;
  }});
}});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    out_path = os.path.join(HERE, "长日系统玩家指南.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(HTML)
    print(f"✅ 玩家指南已生成：{out_path}（共 {total_cmds} 项玩家功能，{len(player_sections)} 个分类）")

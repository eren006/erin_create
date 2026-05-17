#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image
)
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

# 注册中文字体
pdfmetrics.registerFont(TTFont('STHeiti', '/System/Library/Fonts/STHeiti Light.ttc'))
pdfmetrics.registerFont(TTFont('STHeitiMed', '/System/Library/Fonts/STHeiti Medium.ttc'))

W, H = A4
MARGIN = 2.2 * cm

def style(name, **kw):
    base = dict(
        fontName='STHeiti',
        fontSize=10,
        leading=18,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=4,
    )
    base.update(kw)
    return ParagraphStyle(name, **base)

S_title    = style('title',   fontName='STHeitiMed', fontSize=20, leading=28, spaceAfter=6,  textColor=colors.HexColor('#111111'))
S_subtitle = style('subtitle',fontName='STHeiti',    fontSize=10, leading=16, spaceAfter=20, textColor=colors.HexColor('#555555'))
S_h1       = style('h1',      fontName='STHeitiMed', fontSize=14, leading=22, spaceBefore=18,spaceAfter=6,  textColor=colors.HexColor('#222222'))
S_h2       = style('h2',      fontName='STHeitiMed', fontSize=11, leading=18, spaceBefore=12,spaceAfter=4,  textColor=colors.HexColor('#333333'))
S_body     = style('body',    fontSize=10, leading=18, spaceAfter=4)
S_bullet   = style('bullet',  fontSize=10, leading=18, leftIndent=14, spaceAfter=3)
S_note     = style('note',    fontSize=9,  leading=16, textColor=colors.HexColor('#666666'),
                   leftIndent=12, rightIndent=12, spaceBefore=4, spaceAfter=8,
                   backColor=colors.HexColor('#f5f5f5'), borderPad=6)
S_tip      = style('tip',     fontName='STHeitiMed', fontSize=10, leading=18,
                   textColor=colors.HexColor('#333333'), spaceBefore=10, spaceAfter=4)

def bullet(text):
    return Paragraph('• ' + text, S_bullet)

def h1(text):
    return Paragraph(text, S_h1)

def h2(text):
    return Paragraph(text, S_h2)

def body(text):
    return Paragraph(text, S_body)

def note(text):
    return Paragraph(text, S_note)

def sp(n=6):
    return Spacer(1, n)

def divider():
    return HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#dddddd'), spaceAfter=8, spaceBefore=4)


story = []

# ── 标题区 ──
story.append(sp(10))
story.append(Paragraph('自动复盘三种解法的逻辑设计', S_title))
story.append(Paragraph('by 长日将尽 &amp; 饮月光', S_subtitle))
story.append(divider())

# ── 免责声明 ──
story.append(note(
    '以下逻辑由长日将尽与饮月光共同设计，旨在帮助更多人理解和实现自动复盘功能。'
    '由于相关代码与市面上常规恋综插件存在较强的定制耦合，不直接兼容，'
    '因此仅分享设计思路，不提供源代码，仅供学习参考。'
))
story.append(sp(8))

# ── 核心问题 ──
story.append(h1('核心问题定义'))
story.append(body(
    '自动复盘要解决的核心问题是：戏文日志从"骰子系统"流向"人可阅读的存档"的全流程自动化。'
    '这包括三个环节：'
))
story.append(bullet('自动开录 — 私约/官约开始时自动启动日志记录'))
story.append(bullet('自动结录 + 获取链接 — 约会结束时触发日志上传，获得日志 URL'))
story.append(bullet('归档/打包分发 — 将日志整理好发给相关群'))
story.append(sp(4))

# ── 第一种 ──
story.append(divider())
story.append(h1('第一种：长日系统无UI版'))
story.append(Paragraph('纯 JS 内嵌，无外部依赖', style('tag', fontSize=9, textColor=colors.HexColor('#888888'), spaceAfter=8)))

story.append(h2('架构特点'))
story.append(body('所有逻辑全部在海豹插件 JS 里，不需要任何外部服务。'))

story.append(h2('开录逻辑'))
story.append(bullet('在"私约开始"/"绑定小群"等钩子点上，直接调用海豹内置的日志扩展接口'))
story.append(bullet('通过在插件内部构造指令参数来模拟骰子收到 .log new 的效果，不需要真正在群里发消息'))

story.append(h2('结录逻辑（「自动复盘」指令）'))
story.append(bullet('用户或系统在小群触发"自动复盘"，插件在内部调用停录接口'))
story.append(bullet('骰子停止记录后自动将日志上传到自身的日志服务，并在群里发出日志链接'))
story.append(bullet('链接由用户手动复制，粘贴进"结束私约 [链接]"完成归档'))

story.append(h2('归档逻辑'))
story.append(bullet('链接以参数形式传给结戏指令，后台将 URL 写入存档数据'))
story.append(bullet('支持「强制复盘」开关：开启时，没有日志 URL 就无法结戏'))

story.append(h2('适合场景'))
story.append(body('只用海豹、不想额外部署任何服务、操作系统无所谓。'))
story.append(sp(4))

# ── 第二种 ──
story.append(divider())
story.append(h1('第二种：饮月光版'))
story.append(Paragraph('JS + Python 触发器，文件打包上传群', style('tag2', fontSize=9, textColor=colors.HexColor('#888888'), spaceAfter=8)))

story.append(h2('架构特点'))
story.append(body('JS 插件 + Python HTTP 服务器 + 海豹日志文件系统三层协作。'))

story.append(h2('开录逻辑'))
story.append(bullet('与第一种相同：绑定群/开场时在插件内部模拟调用 log new'))
story.append(bullet('在内存中维护一张"正在录制的群"的记录表，防止重复开录'))

story.append(h2('结录逻辑'))
story.append(body('同样是插件内部触发停录，骰子生成日志文件并落盘到本地。'))

story.append(h2('归档/打包的关键创新 — 两层分离'))
story.append(bullet('JS 层：骰子 JS 插件注册 .打包复盘 [名字] 指令，收到后向本机一个本地服务发 HTTP POST 请求，传入群号和自定义文件名'))
story.append(bullet('Python 层：这个 Python 进程常驻后台，收到请求后依次执行：'))
story.append(Paragraph('    ① 将骰子导出的压缩日志解压为可读文本', S_bullet))
story.append(Paragraph('    ② 将解压结果重新打包为新的压缩包（支持自定义命名）', S_bullet))
story.append(Paragraph('    ③ 通过协议端 HTTP API 自动上传到指定群文件', S_bullet))

story.append(h2('为什么要拆两层'))
story.append(bullet('骰子 JS 沙箱无法直接操作本地文件系统，也无法调用协议端的群文件上传接口'))
story.append(bullet('Python 服务作为"桥"—— JS 只负责"下指令"，Python 负责"干重活"'))

story.append(h2('适合场景'))
story.append(body('想要日志文件直接自动上传到 QQ 群文件，运行在 Windows 环境，愿意额外常驻一个 Python 进程。'))
story.append(sp(4))

# ── 第三种 ──
story.append(divider())
story.append(h1('第三种：长日系统有UI版'))
story.append(Paragraph('JS + Flask 存档服务器，RP 正文实时传输', style('tag3', fontSize=9, textColor=colors.HexColor('#888888'), spaceAfter=8)))

story.append(h2('架构特点'))
story.append(body('与第二种同为"JS + 外部服务器"，但目标完全不同——不是事后打包日志文件，而是实时同步 RP 正文到数据库。'))

story.append(h2('开录逻辑'))
story.append(body('与前两种相同，在场景钩子上触发开录。'))

story.append(h2('实时采集（关键区别）'))
story.append(bullet('插件持续监听群内每条消息，识别符合 RP 格式的正文'))
story.append(bullet('识别到后立刻推送到 Flask 服务器，服务器按角色名/时间/场景存入数据库'))

story.append(h2('结录和归档逻辑'))
story.append(bullet('结戏时插件通知服务器本场结束'))
story.append(bullet('服务器侧可生成格式化存档、导出文档，支持按角色/场次检索'))
story.append(bullet('支持 Token 鉴权和多恋综数据隔离'))

story.append(h2('适合场景'))
story.append(body('有服务器部署能力、需要按角色/场次检索 RP 内容、想做数据分析或自动生成报告。'))
story.append(sp(10))

# Demo 图片
IMG1 = '/Users/erinren/Desktop/Screenshot 2026-05-16 at 01.09.29.png'
IMG2 = '/Users/erinren/Desktop/Screenshot 2026-05-15 at 15.34.11.png'
MAX_W = W - 2 * MARGIN

story.append(Paragraph('Demo 截图', style('demo_label', fontName='STHeitiMed', fontSize=9,
    textColor=colors.HexColor('#888888'), spaceAfter=6)))

ratios = [0.4125, 0.6585]
for img_path, ratio in zip([IMG1, IMG2], ratios):
    img = Image(img_path, width=MAX_W, height=MAX_W * ratio)
    img.hAlign = 'LEFT'
    story.append(img)
    story.append(sp(8))

story.append(sp(4))

# ── 对比表 ──
story.append(divider())
story.append(h1('与第二种的本质区别'))
story.append(sp(4))

table_data = [
    ['维度', '第二种（饮月光版）', '第三种（长日有UI版）'],
    ['数据流向', '骰子日志文件 → 打包 → 群文件', 'RP 正文 → 实时推送 → 数据库'],
    ['归档格式', '原始日志压缩包', '结构化数据库记录'],
    ['服务端能力', '文件解压/打包/上传', '数据存储/查询/生成文档'],
    ['适合用途', '保存完整对话记录', '搜索、统计、结构化展示'],
]

col_w = [(W - 2*MARGIN) * r for r in [0.22, 0.39, 0.39]]
tbl = Table(table_data, colWidths=col_w)
tbl.setStyle(TableStyle([
    ('FONTNAME',    (0,0), (-1,-1), 'STHeiti'),
    ('FONTNAME',    (0,0), (-1,0),  'STHeitiMed'),
    ('FONTSIZE',    (0,0), (-1,-1), 9),
    ('LEADING',     (0,0), (-1,-1), 15),
    ('BACKGROUND',  (0,0), (-1,0),  colors.HexColor('#333333')),
    ('TEXTCOLOR',   (0,0), (-1,0),  colors.white),
    ('BACKGROUND',  (0,1), (-1,-1), colors.HexColor('#f9f9f9')),
    ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#f9f9f9'), colors.white]),
    ('GRID',        (0,0), (-1,-1), 0.4, colors.HexColor('#cccccc')),
    ('TOPPADDING',  (0,0), (-1,-1), 6),
    ('BOTTOMPADDING',(0,0),(-1,-1), 6),
    ('LEFTPADDING', (0,0), (-1,-1), 8),
    ('RIGHTPADDING',(0,0), (-1,-1), 8),
    ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
]))
story.append(tbl)
story.append(sp(12))

# ── 总结对比 ──
story.append(divider())
story.append(h1('三种方案的对比总结'))
story.append(sp(4))

summary_data = [
    ['维度', '无UI版', '饮月光版', '有UI Flask版'],
    ['复杂度',   '低', '中', '高'],
    ['外部依赖', '无', '本地 Python 进程', '服务器 + 数据库'],
    ['归档格式', '日志链接', 'zip 文件', '结构化数据'],
    ['可扩展性', '低', '中', '高'],
]

col_w2 = [(W - 2*MARGIN) * r for r in [0.25, 0.22, 0.27, 0.26]]
tbl2 = Table(summary_data, colWidths=col_w2)
tbl2.setStyle(TableStyle([
    ('FONTNAME',    (0,0), (-1,-1), 'STHeiti'),
    ('FONTNAME',    (0,0), (-1,0),  'STHeitiMed'),
    ('FONTNAME',    (0,0), (0,-1),  'STHeitiMed'),
    ('FONTSIZE',    (0,0), (-1,-1), 9),
    ('LEADING',     (0,0), (-1,-1), 15),
    ('BACKGROUND',  (0,0), (-1,0),  colors.HexColor('#333333')),
    ('TEXTCOLOR',   (0,0), (-1,0),  colors.white),
    ('BACKGROUND',  (0,1), (0,-1),  colors.HexColor('#eeeeee')),
    ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#f9f9f9'), colors.white]),
    ('GRID',        (0,0), (-1,-1), 0.4, colors.HexColor('#cccccc')),
    ('TOPPADDING',  (0,0), (-1,-1), 6),
    ('BOTTOMPADDING',(0,0),(-1,-1), 6),
    ('LEFTPADDING', (0,0), (-1,-1), 8),
    ('RIGHTPADDING',(0,0), (-1,-1), 8),
    ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
    ('ALIGN',       (1,1), (-1,-1), 'CENTER'),
]))
story.append(tbl2)
story.append(sp(14))

# ── 设计建议 ──
story.append(divider())
story.append(Paragraph('给想自己设计的人', S_tip))
story.append(body(
    '想自己实现的人，核心只需想清楚一个问题——'
    '「停录之后，日志要去哪、以什么形式存」。'
    '这个问题决定了是否需要外部服务、外部服务做什么。'
    '开录部分（在事件钩子上内部模拟调用 log 指令）三种方案思路完全一致，可以作为通用出发点。'
))

story.append(sp(20))
story.append(Paragraph(
    '© 2026 长日将尽 &amp; 饮月光　仅供学习参考，禁止商用',
    style('footer', fontSize=8, textColor=colors.HexColor('#aaaaaa'), alignment=1)
))

# ── 输出 ──
output_path = '/Users/erinren/Desktop/自动复盘三种解法.pdf'
doc = SimpleDocTemplate(
    output_path,
    pagesize=A4,
    leftMargin=MARGIN, rightMargin=MARGIN,
    topMargin=MARGIN, bottomMargin=MARGIN,
    title='自动复盘三种解法的逻辑设计',
    author='长日将尽 & 饮月光',
)
doc.build(story)
print('已生成：', output_path)

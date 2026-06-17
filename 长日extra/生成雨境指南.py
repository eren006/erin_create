#!/usr/bin/env python3
"""生成雨境使用指南 PDF"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

# ── 颜色主题 ──
RAIN_BLUE    = colors.HexColor('#3A7BD5')   # 雨蓝
RAIN_DARK    = colors.HexColor('#1A3A5C')   # 深蓝
RAIN_LIGHT   = colors.HexColor('#EBF3FC')   # 浅蓝背景
RAIN_STEEL   = colors.HexColor('#5B7FA6')   # 钢蓝（副标题）
RAIN_BORDER  = colors.HexColor('#B0C8E8')   # 边框蓝
HP_RED       = colors.HexColor('#C0392B')   # HP红
GOLD         = colors.HexColor('#C8960A')   # 金色（警告）
GOLD_LIGHT   = colors.HexColor('#FEF9E7')   # 金色背景
GRAY_LIGHT   = colors.HexColor('#F2F4F6')
GRAY_TEXT    = colors.HexColor('#555555')
WHITE        = colors.white
BLACK        = colors.HexColor('#1A1A1A')

# ── 字体 ──
FONT_PATHS = [
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/Library/Fonts/Arial Unicode MS.ttf",
]
font_path = None
for p in FONT_PATHS:
    if os.path.exists(p):
        font_path = p
        break

if font_path:
    pdfmetrics.registerFont(TTFont('CN', font_path))
    F = 'CN'
else:
    F = 'Helvetica'

W, H = A4

# ── 样式 ──
def make_styles():
    s = {}

    s['title'] = ParagraphStyle('title',
        fontName=F, fontSize=26, leading=36,
        textColor=WHITE, alignment=TA_CENTER,
        spaceAfter=4)

    s['subtitle'] = ParagraphStyle('subtitle',
        fontName=F, fontSize=12, leading=18,
        textColor=colors.HexColor('#C8E0FF'), alignment=TA_CENTER)

    s['h1'] = ParagraphStyle('h1',
        fontName=F, fontSize=16, leading=22,
        textColor=RAIN_DARK, spaceBefore=18, spaceAfter=8,
        borderPad=4)

    s['h2'] = ParagraphStyle('h2',
        fontName=F, fontSize=12, leading=17,
        textColor=RAIN_BLUE, spaceBefore=12, spaceAfter=5)

    s['body'] = ParagraphStyle('body',
        fontName=F, fontSize=9.5, leading=16,
        textColor=BLACK, spaceAfter=4)

    s['note'] = ParagraphStyle('note',
        fontName=F, fontSize=8.5, leading=13,
        textColor=GRAY_TEXT, spaceAfter=3)

    s['cmd'] = ParagraphStyle('cmd',
        fontName=F, fontSize=9, leading=14,
        textColor=RAIN_DARK, spaceBefore=2, spaceAfter=2,
        leftIndent=6)

    s['warn'] = ParagraphStyle('warn',
        fontName=F, fontSize=9, leading=14,
        textColor=colors.HexColor('#7D5A00'), spaceAfter=3)

    s['center'] = ParagraphStyle('center',
        fontName=F, fontSize=9, leading=14,
        textColor=GRAY_TEXT, alignment=TA_CENTER)

    s['small_header'] = ParagraphStyle('small_header',
        fontName=F, fontSize=8.5, leading=12,
        textColor=WHITE, alignment=TA_CENTER)

    return s

S = make_styles()

# ── 工具 ──
def hr(color=RAIN_BORDER, thickness=0.8):
    return HRFlowable(width='100%', thickness=thickness, color=color, spaceAfter=8, spaceBefore=4)

def sp(h=6):
    return Spacer(1, h)

def h1(text):
    label = Paragraph(f'&#9670; {text}', S['h1'])
    line  = HRFlowable(width='100%', thickness=1.5, color=RAIN_BLUE, spaceAfter=10)
    return [label, line]

def h2(text):
    return Paragraph(f'▸ {text}', S['h2'])

def body(text):
    return Paragraph(text, S['body'])

def note(text):
    return Paragraph(text, S['note'])

def cmd_table(rows):
    """指令表格：[(指令, 说明), ...]"""
    data = [[Paragraph('指令', S['small_header']),
             Paragraph('权限', S['small_header']),
             Paragraph('说明', S['small_header'])]]
    for (cmd, perm, desc) in rows:
        data.append([
            Paragraph(cmd,  ParagraphStyle('ct', fontName=F, fontSize=8.5, leading=13, textColor=RAIN_DARK)),
            Paragraph(perm, ParagraphStyle('ct', fontName=F, fontSize=8.5, leading=13, textColor=GRAY_TEXT, alignment=TA_CENTER)),
            Paragraph(desc, ParagraphStyle('ct', fontName=F, fontSize=8.5, leading=13, textColor=BLACK)),
        ])

    col_w = [5.8*cm, 1.6*cm, 9.8*cm]
    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND',  (0,0), (-1,0),  RAIN_BLUE),
        ('TEXTCOLOR',   (0,0), (-1,0),  WHITE),
        ('FONTNAME',    (0,0), (-1,-1), F),
        ('FONTSIZE',    (0,0), (-1,-1), 8.5),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, RAIN_LIGHT]),
        ('GRID',        (0,0), (-1,-1), 0.4, RAIN_BORDER),
        ('VALIGN',      (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING',  (0,0), (-1,-1), 5),
        ('BOTTOMPADDING',(0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 7),
    ]))
    return t

def info_box(title, lines, color=RAIN_LIGHT, border=RAIN_BORDER):
    """带标题的信息框"""
    inner = [[Paragraph(title, ParagraphStyle('bt', fontName=F, fontSize=9.5, leading=14, textColor=RAIN_DARK))]] + \
            [[Paragraph(l, S['body'])] for l in lines]
    t = Table(inner, colWidths=[16.2*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND',  (0,0), (-1,0),  border),
        ('BACKGROUND',  (0,1), (-1,-1), color),
        ('BOX',         (0,0), (-1,-1), 1, border),
        ('FONTNAME',    (0,0), (-1,-1), F),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING',(0,0), (-1,-1), 10),
        ('TOPPADDING',  (0,0), (-1,-1), 6),
        ('BOTTOMPADDING',(0,0), (-1,-1), 4),
    ]))
    return t

def warn_box(lines):
    inner = [[Paragraph('⚠ 注意', ParagraphStyle('wt', fontName=F, fontSize=9.5, leading=14, textColor=colors.HexColor('#7D5A00')))]] + \
            [[Paragraph(l, S['warn'])] for l in lines]
    t = Table(inner, colWidths=[16.2*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND',  (0,0), (-1,0),  colors.HexColor('#FAD7A0')),
        ('BACKGROUND',  (0,1), (-1,-1), GOLD_LIGHT),
        ('BOX',         (0,0), (-1,-1), 1, GOLD),
        ('FONTNAME',    (0,0), (-1,-1), F),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING',(0,0), (-1,-1), 10),
        ('TOPPADDING',  (0,0), (-1,-1), 6),
        ('BOTTOMPADDING',(0,0), (-1,-1), 4),
    ]))
    return t

def flow_table(steps):
    """流程图：[(图标, 状态, 说明)]"""
    data = []
    for i, (icon, state, desc) in enumerate(steps):
        arrow = '' if i == len(steps)-1 else '↓'
        data.append([
            Paragraph(icon,  ParagraphStyle('ic', fontName=F, fontSize=14, alignment=TA_CENTER)),
            Paragraph(state, ParagraphStyle('st', fontName=F, fontSize=9.5, leading=14, textColor=RAIN_DARK)),
            Paragraph(desc,  ParagraphStyle('ds', fontName=F, fontSize=8.5, leading=13, textColor=GRAY_TEXT)),
            Paragraph(arrow, ParagraphStyle('ar', fontName=F, fontSize=14, textColor=RAIN_STEEL, alignment=TA_CENTER)),
        ])
    t = Table(data, colWidths=[1.2*cm, 4.5*cm, 9.5*cm, 1.0*cm])
    t.setStyle(TableStyle([
        ('FONTNAME',    (0,0), (-1,-1), F),
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [RAIN_LIGHT, WHITE]),
        ('BOX',         (0,0), (-1,-1), 0.8, RAIN_BORDER),
        ('INNERGRID',   (0,0), (-1,-1), 0.3, RAIN_BORDER),
        ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',  (0,0), (-1,-1), 7),
        ('BOTTOMPADDING',(0,0), (-1,-1), 7),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('ALIGN',       (0,0), (0,-1),  'CENTER'),
        ('ALIGN',       (3,0), (3,-1),  'CENTER'),
    ]))
    return t


# ── 页眉页脚 ──
def on_page(canvas, doc):
    canvas.saveState()
    # 页眉
    canvas.setFillColor(RAIN_DARK)
    canvas.rect(0, H - 1.0*cm, W, 1.0*cm, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont(F, 9)
    canvas.drawString(1.6*cm, H - 0.68*cm, '雨境  使用指南')
    canvas.drawRightString(W - 1.6*cm, H - 0.68*cm, 'v1.0.0')
    # 页脚
    canvas.setFillColor(RAIN_BORDER)
    canvas.rect(0, 0, W, 0.8*cm, fill=1, stroke=0)
    canvas.setFillColor(RAIN_STEEL)
    canvas.setFont(F, 8)
    canvas.drawCentredString(W/2, 0.28*cm, f'第 {doc.page} 页')
    canvas.restoreState()


# ── 封面 ──
def cover_page(canvas, doc):
    canvas.saveState()
    # 渐变背景（用矩形叠加模拟）
    canvas.setFillColor(RAIN_DARK)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)

    # 装饰雨滴图案（简单斜线）
    canvas.setStrokeColor(colors.HexColor('#1E4A7A'))
    canvas.setLineWidth(0.5)
    for i in range(0, int(W*2), 20):
        canvas.line(i, H, i - 80, 0)

    # 中央卡片
    card_x, card_y = 2.5*cm, 6*cm
    card_w, card_h  = W - 5*cm, H - 12*cm
    canvas.setFillColor(colors.HexColor('#0D2A47'))
    canvas.setStrokeColor(RAIN_BLUE)
    canvas.setLineWidth(1.5)
    canvas.roundRect(card_x, card_y, card_w, card_h, 12, fill=1, stroke=1)

    # 顶部蓝条
    canvas.setFillColor(RAIN_BLUE)
    canvas.roundRect(card_x, card_y + card_h - 2.0*cm, card_w, 2.0*cm, 0, fill=1, stroke=0)

    # 大标题
    canvas.setFont(F, 38)
    canvas.setFillColor(WHITE)
    canvas.drawCentredString(W/2, card_y + card_h - 1.35*cm, '雨境')

    # 副标题
    canvas.setFont(F, 14)
    canvas.setFillColor(colors.HexColor('#C8E0FF'))
    canvas.drawCentredString(W/2, card_y + card_h - 3.2*cm, '雨点 · HP · 执念之争系统')

    # 分隔线
    canvas.setStrokeColor(RAIN_BORDER)
    canvas.setLineWidth(0.8)
    canvas.line(card_x + 1.5*cm, card_y + card_h - 3.9*cm,
                card_x + card_w - 1.5*cm, card_y + card_h - 3.9*cm)

    # 简介文本
    canvas.setFont(F, 10)
    canvas.setFillColor(colors.HexColor('#90B8D8'))
    lines = [
        '雨境是一款基于 海豹骰子 的 Addon 插件，',
        '为文字 RP 游戏提供雨点货币、HP 生命值',
        '与执念之争（PVP）三位一体的完整系统。',
    ]
    y = card_y + card_h - 5.0*cm
    for l in lines:
        canvas.drawCentredString(W/2, y, l)
        y -= 1.4*cm

    # 版本 / 作者
    canvas.setFont(F, 9)
    canvas.setFillColor(RAIN_STEEL)
    canvas.drawCentredString(W/2, card_y + 1.0*cm, 'v1.0.0  ·  长日将尽')

    # 底部小字
    canvas.setFont(F, 8)
    canvas.setFillColor(colors.HexColor('#4A6A8A'))
    canvas.drawCentredString(W/2, 1.2*cm, '本文档由长日系统自动生成  ·  2026-06-14')

    canvas.restoreState()


# ══════════════════════════════════════════
# 正文内容构建
# ══════════════════════════════════════════
def build_story():
    story = []

    # 封面占位：第1页只渲染封面背景，正文从第2页开始
    story.append(PageBreak())

    # ── 第1节：概述 ──
    story += h1('概述')
    story.append(body(
        '雨境是一个依赖长日主插件（changri）运行的 Addon，'
        '核心玩法围绕三个数值展开：'
    ))
    story.append(sp(4))

    overview = [
        ['🌧 雨点（Raindrops）', 'HP（生命值）', '执念之争（PVP）'],
        [
            Paragraph('游戏内货币，初始由管理员分配。用于发起/接受 PVP 的赌注，也可消耗续命。雨点归零 → 消散。',
                      ParagraphStyle('ov', fontName=F, fontSize=8.5, leading=13, textColor=BLACK)),
            Paragraph('每人初始100，在执念之争中被消耗。HP归零 → 消散。管理员可用指令调整。',
                      ParagraphStyle('ov', fontName=F, fontSize=8.5, leading=13, textColor=BLACK)),
            Paragraph('携带雨点互相挑战的对决机制，胜者获得败者的赌注雨点。结算后双方HP也随战斗扣减。',
                      ParagraphStyle('ov', fontName=F, fontSize=8.5, leading=13, textColor=BLACK)),
        ]
    ]
    ov_t = Table(overview, colWidths=[5.4*cm, 5.4*cm, 5.4*cm])
    ov_t.setStyle(TableStyle([
        ('BACKGROUND',  (0,0), (-1,0),  RAIN_BLUE),
        ('TEXTCOLOR',   (0,0), (-1,0),  WHITE),
        ('FONTNAME',    (0,0), (-1,-1), F),
        ('FONTSIZE',    (0,0), (-1,0),  10),
        ('ALIGN',       (0,0), (-1,0),  'CENTER'),
        ('BACKGROUND',  (0,1), (-1,-1), RAIN_LIGHT),
        ('GRID',        (0,0), (-1,-1), 0.6, RAIN_BORDER),
        ('VALIGN',      (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING',  (0,0), (-1,-1), 8),
        ('BOTTOMPADDING',(0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(ov_t)
    story.append(sp(10))

    # 前置依赖
    story.append(warn_box([
        '雨境必须在主插件 changri 已加载的情况下运行，否则所有指令均无效。',
        '玩家角色须已在主插件的 a_private_group 中登记（拥有个人群），才能正确接收通知推送。',
        '加载后请先运行 .雨境管理群 <群号> 设置管理群，再运行 .雨境初始化 为各角色分配初始雨点。',
    ]))
    story.append(sp(12))

    # ── 第2节：玩家状态 ──
    story += h1('玩家状态说明')

    states = [
        ['状态', '标志', '说明'],
        ['✅ 正常', '—', '可参与一切雨境活动'],
        ['⚔ 对决中（时间线锁定）', 'timeLocked = true', '正在进行执念之争，时间线被锁定，无法再发起或接受新的PVP'],
        ['🕯 续命中', 'isRevived = true', '被他人续命后的特殊状态，HP=1，禁止参与PVP，大群公开通报'],
        ['💀 已消散', 'isAlive = false', 'HP归零或雨点归零后死亡，无法再发起/参与任何雨境行动（除非被续命）'],
    ]
    st_t = Table(states, colWidths=[4.5*cm, 4.5*cm, 7.2*cm])
    st_t.setStyle(TableStyle([
        ('BACKGROUND',  (0,0), (-1,0),  RAIN_DARK),
        ('TEXTCOLOR',   (0,0), (-1,0),  WHITE),
        ('FONTNAME',    (0,0), (-1,-1), F),
        ('FONTSIZE',    (0,0), (-1,-1), 8.5),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, RAIN_LIGHT]),
        ('GRID',        (0,0), (-1,-1), 0.4, RAIN_BORDER),
        ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',  (0,0), (-1,-1), 6),
        ('BOTTOMPADDING',(0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('ALIGN',       (0,0), (-1,0),  'CENTER'),
    ]))
    story.append(st_t)
    story.append(sp(8))

    story.append(info_box('消散触发条件', [
        '• HP 归零：执念之争中战斗消耗导致HP降至0',
        '• 雨点归零：执念之争落败后雨点被抢夺殆尽，或超时未应战被扣除至0',
        '• 消散后自动通报大群，并向管理群推送详情；消散者的个人群也会收到通知。',
    ]))
    story.append(sp(12))

    # ── 第3节：指令一览 ──
    story += h1('指令一览')

    # 玩家指令
    story.append(h2('玩家指令'))
    story.append(sp(4))
    story.append(cmd_table([
        ('.执念之争 <角色名> <N颗>', '玩家', '向指定角色发起执念之争，携带N颗雨点作为赌注'),
        ('.应战 <N颗>', '玩家', '接受当前针对自己的挑战，携带N颗雨点应战'),
        ('.撤战', '玩家', '撤回自己发起的、尚未被对方接受的挑战'),
        ('.续命 <角色名>', '玩家', '消耗1颗雨点，为已消散角色续命（对方HP变为1，进入续命状态）'),
        ('.雨境信息', '玩家', '查看自己当前的雨点数、HP与状态'),
    ]))
    story.append(sp(10))

    # 管理员指令
    story.append(h2('管理员指令'))
    story.append(sp(4))
    story.append(cmd_table([
        ('.开启pvp', '管理', '开启执念之争，玩家可发起挑战'),
        ('.关闭pvp', '管理', '关闭执念之争，禁止新的挑战'),
        ('.pvp分配 <ID> <攻击X防御Y> <攻击X防御Y>', '管理', '录入双方攻防分配（发起方在前，防守方在后）'),
        ('.pvp执行 <ID>', '管理', '触发战斗结算，输出战报并转移雨点'),
        ('.pvp状态', '管理', '查看所有进行中的执念之争列表'),
        ('.pvp检查超时', '管理', '手动触发超时检查（>60分钟未应战者扣除赌注）'),
        ('.雨境查询 <角色名|全员>', '管理', '查看指定玩家或全体玩家的雨境状态'),
        ('.雨境设置 <角色名> <操作>', '管理', '调整玩家雨点/HP。支持 +N -N =N，可同时写多个，如：雨点+5 HP-20'),
        ('.雨境初始化 <角色名> <N颗>', '管理', '将玩家数据重置：HP=100、雨点=N，清空所有锁定与状态'),
        ('.雨境每日重置', '管理', '重置所有玩家今日PVP次数计数（每天切换时调用）'),
        ('.雨境管理群 <群号>', '管理', '设置接收管理通报的群号（纯数字）'),
    ]))
    story.append(sp(12))

    # ── 第4节：执念之争流程 ──
    story.append(PageBreak())
    story += h1('执念之争完整流程')

    story.append(body('执念之争分为五个阶段，由状态机驱动：'))
    story.append(sp(6))

    story.append(flow_table([
        ('⚡', 'pending_accept  （等待应战）',
         '发起方 .执念之争 后进入此状态。防守方60分钟内须 .应战，否则超时自动扣除赌注雨点。发起方时间线立即锁定。'),
        ('🤝', 'pending_alloc_admin  （等待分配录入）',
         '防守方 .应战 成功后，双方时间线均锁定。管理员在此阶段收集双方分配方案（攻击+防御=携带雨点×10）。'),
        ('📋', 'ready_to_battle  （待执行）',
         '管理员 .pvp分配 录入完成后进入。此时分配方案已确定，等待管理员 .pvp执行。'),
        ('⚔', 'completed  （已结算）',
         '管理员 .pvp执行 后，系统自动进行回合制战斗模拟，输出战报，转移雨点，更新HP，推送结果到双方个人群。'),
        ('✗', 'cancelled  （已取消）',
         '发起方在应战前 .撤战 可取消。取消后发起方时间线解锁，雨点不扣除。'),
    ]))
    story.append(sp(12))

    # ── 分配说明 ──
    story.append(h2('攻防分配规则'))
    story.append(sp(4))
    story.append(info_box('分配公式', [
        '• 总点数 = 携带雨点数 × 10',
        '  例：携带 3 颗雨点 → 总点数 = 30，可任意分配如 攻击15防御15 或 攻击20防御10',
        '• 攻击与防御均不可为 0（至少各分配 1 点）',
        '• 指令格式：.pvp分配 <ID> 攻击X防御Y 攻击X防御Y（发起方在前，防守方在后）',
        '  示例：.pvp分配 pvp_1234 攻击20防御10 攻击15防御15',
    ]))
    story.append(sp(10))

    # ── 战斗机制 ──
    story.append(h2('战斗结算机制'))
    story.append(sp(4))
    story.append(body(
        '每回合双方交替出手，模拟回合制战斗，直到一方HP归零或达到300回合上限。'
    ))
    story.append(sp(4))

    battle = [
        ['步骤', '计算方式', '说明'],
        ['① 发起方进攻', '伤害 = max(0, 随机(1~攻击力) - 随机(1~防守力))',
         '发起方攻击，防守方防御。防御骰高则可能完全抵消伤害。'],
        ['② 防守方进攻', '伤害 = max(0, 随机(1~攻击力) - 随机(1~防守力))',
         '防守方攻击，发起方防御。同上。'],
        ['③ 判定胜负', '先HP归零者负；同归于尽为平局', '平局时雨点各自保留，HP损耗照算。'],
        ['④ 雨点结算', '胜者获得败者携带的雨点', '平局不转移雨点。雨点归零者消散。'],
        ['⑤ HP更新', 'HP -= 战斗中实际受到的总伤害', '双方当前HP均被更新，归零则触发消散。'],
    ]
    b_t = Table(battle, colWidths=[3.0*cm, 6.5*cm, 6.7*cm])
    b_t.setStyle(TableStyle([
        ('BACKGROUND',  (0,0), (-1,0),  RAIN_BLUE),
        ('TEXTCOLOR',   (0,0), (-1,0),  WHITE),
        ('FONTNAME',    (0,0), (-1,-1), F),
        ('FONTSIZE',    (0,0), (-1,-1), 8.5),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, RAIN_LIGHT]),
        ('GRID',        (0,0), (-1,-1), 0.4, RAIN_BORDER),
        ('VALIGN',      (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING',  (0,0), (-1,-1), 6),
        ('BOTTOMPADDING',(0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('ALIGN',       (0,0), (-1,0),  'CENTER'),
    ]))
    story.append(b_t)
    story.append(sp(12))

    # ── 第5节：PVP 限制规则 ──
    story += h1('PVP 限制规则')
    story.append(sp(4))

    rules = [
        ['规则', 'Day1', 'Day2 ~ Day3', 'Day4+'],
        ['每日PVP次数上限', '无限制', '每人2次/天', '无限制'],
        ['同一对手限制', '无限制', '每天只能与同一对手对决1次', '无限制'],
        ['续命状态参与限制', '全程禁止', '全程禁止', '全程禁止'],
        ['应战超时扣除', '60分钟', '60分钟', '60分钟'],
    ]
    r_t = Table(rules, colWidths=[5.5*cm, 2.5*cm, 5.5*cm, 2.7*cm])
    r_t.setStyle(TableStyle([
        ('BACKGROUND',  (0,0), (-1,0),  RAIN_DARK),
        ('TEXTCOLOR',   (0,0), (-1,0),  WHITE),
        ('FONTNAME',    (0,0), (-1,-1), F),
        ('FONTSIZE',    (0,0), (-1,-1), 8.5),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, RAIN_LIGHT]),
        ('GRID',        (0,0), (-1,-1), 0.4, RAIN_BORDER),
        ('ALIGN',       (0,0), (-1,-1), 'CENTER'),
        ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',  (0,0), (-1,-1), 7),
        ('BOTTOMPADDING',(0,0), (-1,-1), 7),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(r_t)
    story.append(sp(8))

    story.append(info_box('排队机制', [
        '若防守方正在进行中的 PVP（时间线锁定），新挑战将自动加入排队，不会立即锁定发起方。',
        '管理群会在进行中 PVP 结算完成后收到队列提醒，告知下一场待激活的挑战。',
    ]))
    story.append(sp(12))

    # ── 第6节：续命 ──
    story += h1('续命机制')
    story.append(sp(4))

    story.append(info_box('续命规则', [
        '• 玩家消耗 1 颗雨点，可为已消散（isAlive=false）的角色续命',
        '• 续命后：目标 HP 恢复为 1，isRevived = true，isAlive = true',
        '• 续命状态禁止参与执念之争（无法发起也无法应战）',
        '• 大群会公开通报续命事件，管理群记录操作详情',
        '• 续命状态的解除由管理员手动操作（使用 .雨境设置 调整或重置数据）',
    ]))
    story.append(sp(12))

    # ── 第7节：通知推送 ──
    story += h1('通知推送说明')
    story.append(sp(4))
    story.append(body('雨境会根据不同事件向不同目标推送消息：'))
    story.append(sp(6))

    notif = [
        ['推送目标', '触发场景'],
        ['发起方个人群', '对方应战、PVP结果、续命状态变化'],
        ['防守方个人群', '收到挑战、超时扣除通知、PVP结果'],
        ['管理群', '所有PVP事件（发起/应战/排队/超时/结算/续命）'],
        ['大群（adminAnnounceGroupId）', '执念之争开始通报、死亡通报、续命通报'],
    ]
    n_t = Table(notif, colWidths=[5.5*cm, 10.7*cm])
    n_t.setStyle(TableStyle([
        ('BACKGROUND',  (0,0), (-1,0),  RAIN_STEEL),
        ('TEXTCOLOR',   (0,0), (-1,0),  WHITE),
        ('FONTNAME',    (0,0), (-1,-1), F),
        ('FONTSIZE',    (0,0), (-1,-1), 8.5),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, RAIN_LIGHT]),
        ('GRID',        (0,0), (-1,-1), 0.4, RAIN_BORDER),
        ('VALIGN',      (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING',  (0,0), (-1,-1), 7),
        ('BOTTOMPADDING',(0,0), (-1,-1), 7),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(n_t)
    story.append(sp(8))
    story.append(note('* 个人群推送依赖主插件 a_private_group 数据；大群依赖 adminAnnounceGroupId 设置。'))
    story.append(sp(12))

    # ── 第8节：初始配置流程 ──
    story.append(PageBreak())
    story += h1('初始配置流程（管理员上手指引）')
    story.append(sp(4))

    steps_data = [
        ['步骤', '操作', '示例'],
        ['1', '确认主插件 changri 已加载，玩家已在 a_private_group 中登记', '—'],
        ['2', '在任意群发送指令，设置管理群', '.雨境管理群 123456789'],
        ['3', '为每位参与玩家初始化雨点（可重复调用）', '.雨境初始化 小明 5颗\n.雨境初始化 小红 5颗'],
        ['4', '在合适时机开启PVP', '.开启pvp'],
        ['5', '每天游戏切换时重置每日计数', '.雨境每日重置'],
        ['6', '（可选）手动检查长时间无人应战的挑战', '.pvp检查超时'],
    ]
    setup_t = Table(steps_data, colWidths=[1.0*cm, 8.5*cm, 6.7*cm])
    setup_t.setStyle(TableStyle([
        ('BACKGROUND',  (0,0), (-1,0),  RAIN_DARK),
        ('TEXTCOLOR',   (0,0), (-1,0),  WHITE),
        ('FONTNAME',    (0,0), (-1,-1), F),
        ('FONTSIZE',    (0,0), (-1,-1), 8.5),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, RAIN_LIGHT]),
        ('GRID',        (0,0), (-1,-1), 0.4, RAIN_BORDER),
        ('ALIGN',       (0,0), (0,-1),  'CENTER'),
        ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',  (0,0), (-1,-1), 7),
        ('BOTTOMPADDING',(0,0), (-1,-1), 7),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(setup_t)
    story.append(sp(12))

    # ── 第9节：常见问题 ──
    story += h1('常见问题')
    story.append(sp(4))

    faqs = [
        ('Q：发起挑战后提示「未找到主插件 changri」？',
         'A：请先加载 changri 主插件再加载雨境。'),
        ('Q：应战提示「当前没有等待你应战的执念之争」？',
         'A：确认发起方是否已撤战，或挑战是否已超时取消。'),
        ('Q：.pvp分配 提示「攻+防须等于 N」？',
         'A：双方各自的攻击+防御必须精确等于 携带雨点×10。例如携带3颗→必须等于30。'),
        ('Q：玩家在续命状态下能做什么？',
         'A：续命状态下无法发起或应战，但可以为他人续命、查看自己的雨境信息。'),
        ('Q：同归于尽时雨点如何处理？',
         'A：双方各自保留原有雨点，不发生转移。但HP损耗正常计算。'),
        ('Q：管理员如何手动修正数据？',
         'A：.雨境设置 角色名 雨点=N HP=N 可直接赋值；.雨境初始化 可完全重置玩家数据。'),
    ]
    for q, a in faqs:
        faq_data = [
            [Paragraph(q, ParagraphStyle('fq', fontName=F, fontSize=9, leading=14, textColor=RAIN_DARK))],
            [Paragraph(a, ParagraphStyle('fa', fontName=F, fontSize=8.5, leading=13, textColor=BLACK))],
        ]
        faq_t = Table(faq_data, colWidths=[16.2*cm])
        faq_t.setStyle(TableStyle([
            ('BACKGROUND',  (0,0), (-1,0),  RAIN_LIGHT),
            ('BACKGROUND',  (0,1), (-1,-1), WHITE),
            ('BOX',         (0,0), (-1,-1), 0.8, RAIN_BORDER),
            ('FONTNAME',    (0,0), (-1,-1), F),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('TOPPADDING',  (0,0), (-1,-1), 6),
            ('BOTTOMPADDING',(0,0), (-1,-1), 6),
        ]))
        story.append(faq_t)
        story.append(sp(5))

    story.append(sp(16))

    # ── 尾部 ──
    story.append(hr(RAIN_BLUE, 1.2))
    story.append(Paragraph(
        '雨境 v1.0.0  ·  长日将尽  ·  MIT License',
        ParagraphStyle('footer', fontName=F, fontSize=8, leading=12,
                       textColor=RAIN_STEEL, alignment=TA_CENTER)
    ))

    return story


# ══════════════════════════════════════════
# 输出
# ══════════════════════════════════════════
OUTPUT = '/Users/erinren/erin_creation/长日extra/雨境使用指南.pdf'

# 封面单独处理
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate

class CoverDoc(BaseDocTemplate):
    def __init__(self, filename, **kw):
        super().__init__(filename, **kw)
        self._cover_done = False

    def handle_pageBegin(self):
        super().handle_pageBegin()

cover = SimpleDocTemplate(
    OUTPUT,
    pagesize=A4,
    leftMargin=1.6*cm, rightMargin=1.6*cm,
    topMargin=1.4*cm, bottomMargin=1.2*cm,
    title='雨境 使用指南',
    author='长日将尽',
    subject='雨点 · HP · 执念之争系统',
)

story = build_story()

# 用 onFirstPage / onLaterPages 区分封面和正文
cover.build(
    story,
    onFirstPage=cover_page,
    onLaterPages=on_page,
)

print(f'PDF 已生成：{OUTPUT}')

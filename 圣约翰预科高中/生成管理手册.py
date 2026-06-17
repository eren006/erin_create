#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""圣约翰预科高中 GM/管理员手册 PDF 生成脚本"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

FONT_PATHS = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/Library/Fonts/Arial Unicode MS.ttf",
]
FONT_BOLD_PATHS = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
]

def reg(name, paths, subfont=0):
    for p in paths:
        if os.path.exists(p):
            try:
                pdfmetrics.registerFont(TTFont(name, p, subfontIndex=subfont))
                return True
            except Exception:
                pass
    return False

have_cn  = reg("CN",     FONT_PATHS,      0)
have_cnb = reg("CN-Bold",FONT_BOLD_PATHS, 0)
BASE = "CN"      if have_cn  else "Helvetica"
BOLD = "CN-Bold" if have_cnb else "Helvetica-Bold"

C_DARK   = colors.HexColor("#1A1A2E")
C_RED    = colors.HexColor("#B71C1C")
C_RED2   = colors.HexColor("#D32F2F")
C_GOLD   = colors.HexColor("#C9A84C")
C_LIGHT  = colors.HexColor("#FFF8F8")
C_LIGHT2 = colors.HexColor("#F3F4F6")
C_BORDER = colors.HexColor("#CBD5E1")
C_NAVY   = colors.HexColor("#1B2A4A")
C_BLUE   = colors.HexColor("#3A5F8A")
C_GREEN  = colors.HexColor("#1B5E20")
C_ORANGE = colors.HexColor("#E65100")
C_ROW1   = colors.HexColor("#FAFAFA")
C_ROW2   = colors.HexColor("#FEECEC")
WHITE    = colors.white

ss = getSampleStyleSheet()

def sty(name, **kw):
    kw.setdefault("fontName", BASE)
    kw.setdefault("leading",  kw.get("fontSize", 10) * 1.45)
    return ParagraphStyle(name, parent=ss["Normal"], **kw)

S_BODY  = sty("B",  fontSize=9,  spaceAfter=3)
S_SMALL = sty("SM", fontSize=8,  textColor=colors.HexColor("#555"))
S_CH1   = sty("H1", fontSize=15, fontName=BOLD, textColor=C_DARK,   spaceBefore=12, spaceAfter=6)
S_CH2   = sty("H2", fontSize=11, fontName=BOLD, textColor=C_RED,    spaceBefore=8,  spaceAfter=4)
S_CH3   = sty("H3", fontSize=9.5,fontName=BOLD, textColor=C_NAVY,   spaceBefore=4,  spaceAfter=2)
S_WARN  = sty("W",  fontSize=8.5,textColor=C_RED2, leftIndent=6)
S_TIP   = sty("T",  fontSize=8.5,textColor=C_GREEN, leftIndent=6)
S_CODE  = sty("C",  fontSize=9,  fontName="Courier", textColor=C_DARK,
              backColor=colors.HexColor("#F0F0F0"), leftIndent=10, spaceAfter=2)

W, H = A4
ML, MR, MT, MB = 18*mm, 18*mm, 20*mm, 18*mm
TW = W - ML - MR

def th(t): return Paragraph(t, sty("_th", fontSize=8.5, fontName=BOLD, textColor=WHITE, alignment=TA_CENTER))
def td(t): return Paragraph(str(t), sty("_td", fontSize=8.5, alignment=TA_CENTER))
def tdl(t): return Paragraph(str(t), sty("_tdl", fontSize=8.5, alignment=TA_LEFT))

def tbl(rows, cols=None):
    t = Table(rows, colWidths=cols, repeatRows=1, hAlign="LEFT")
    style = [
        ('FONTNAME',   (0,0),(-1,-1), BASE),
        ('FONTNAME',   (0,0),(-1,0),  BOLD),
        ('FONTSIZE',   (0,0),(-1,-1), 8.5),
        ('BACKGROUND', (0,0),(-1,0),  C_RED),
        ('TEXTCOLOR',  (0,0),(-1,0),  WHITE),
        ('ALIGN',      (0,0),(-1,-1), 'CENTER'),
        ('VALIGN',     (0,0),(-1,-1), 'MIDDLE'),
        ('GRID',       (0,0),(-1,-1), 0.3, C_BORDER),
        ('TOPPADDING', (0,0),(-1,-1), 3),
        ('BOTTOMPADDING',(0,0),(-1,-1),3),
        ('LEFTPADDING',(0,0),(-1,-1), 5),
        ('RIGHTPADDING',(0,0),(-1,-1),5),
    ]
    for i in range(1, len(rows)):
        style.append(('BACKGROUND',(0,i),(-1,i), C_ROW1 if i%2==1 else C_ROW2))
    t.setStyle(TableStyle(style))
    return t

def section(title, color=C_RED):
    t = Table([[Paragraph(title, sty("_s", fontSize=11, fontName=BOLD,
                textColor=WHITE, leading=16))]], colWidths=[TW])
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(0,0), color),
        ('TOPPADDING',(0,0),(0,0), 5),
        ('BOTTOMPADDING',(0,0),(0,0),5),
        ('LEFTPADDING',(0,0),(0,0),10),
    ]))
    return t

def box(lines, bg=C_LIGHT, border=C_RED2):
    rows = [[Paragraph(l, S_BODY)] for l in lines]
    t = Table(rows, colWidths=[TW-4])
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1), bg),
        ('BOX',       (0,0),(-1,-1), 0.8, border),
        ('TOPPADDING',(0,0),(-1,-1), 3),
        ('BOTTOMPADDING',(0,0),(-1,-1),3),
        ('LEFTPADDING',(0,0),(-1,-1), 8),
        ('FONTNAME',  (0,0),(-1,-1), BASE),
        ('FONTSIZE',  (0,0),(-1,-1), 8.5),
    ]))
    return t

def step_box(steps):
    """带编号步骤框"""
    rows = [[Paragraph(f"{'①②③④⑤⑥⑦⑧'[i]}  {s}", S_BODY)] for i, s in enumerate(steps)]
    t = Table(rows, colWidths=[TW-4])
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1), colors.HexColor("#FFF8F8")),
        ('BOX',       (0,0),(-1,-1), 0.8, C_RED2),
        ('LINEBELOW', (0,0),(-1,-2), 0.2, C_BORDER),
        ('TOPPADDING',(0,0),(-1,-1), 4),
        ('BOTTOMPADDING',(0,0),(-1,-1),4),
        ('LEFTPADDING',(0,0),(-1,-1), 8),
        ('FONTNAME',  (0,0),(-1,-1), BASE),
        ('FONTSIZE',  (0,0),(-1,-1), 8.5),
    ]))
    return t

# ══════════════════════════════════════════════════════
story = []
out_path = os.path.join(os.path.dirname(__file__), "圣约翰预科高中_GM手册.pdf")
doc = SimpleDocTemplate(out_path, pagesize=A4,
                        leftMargin=ML, rightMargin=MR,
                        topMargin=MT, bottomMargin=MB)

# ── 封面 ────────────────────────────────────────────────
cover = Table([
    [Paragraph("⚙ 管理员手册", sty("_cv", fontSize=28, fontName=BOLD,
               textColor=WHITE, alignment=TA_CENTER, leading=38))],
    [Paragraph("圣约翰预科高中 · GM Guide", sty("_cv2", fontSize=12,
               textColor=C_GOLD, alignment=TA_CENTER))],
    [Spacer(1, 6*mm)],
    [HRFlowable(width=TW*0.5, thickness=1.5, color=C_GOLD)],
    [Spacer(1, 6*mm)],
    [Paragraph("本文件仅供游戏管理员（GM）使用", sty("_cv3", fontSize=10,
               textColor=colors.HexColor("#FFCDD2"), alignment=TA_CENTER))],
    [Paragraph("请勿将本手册转发给普通玩家", sty("_cv4", fontSize=9,
               textColor=colors.HexColor("#EF9A9A"), alignment=TA_CENTER))],
], colWidths=[TW])
cover.setStyle(TableStyle([
    ('BACKGROUND',(0,0),(0,-1), C_RED),
    ('ALIGN',    (0,0),(0,-1), 'CENTER'),
    ('TOPPADDING',(0,0),(0,-1),6),
    ('BOTTOMPADDING',(0,0),(0,-1),6),
]))
story.append(Spacer(1, 20*mm))
story.append(cover)
story.append(Spacer(1, 10*mm))
story.append(box([
    "📋 本手册包含：游戏初始化流程、管理员设置面板、属性调整指令、Gossip Girl 系统、游戏节奏建议、常见问题处理。",
    "📋 所有管理员指令均需要提前通过 .圣约翰设置 面板完成首次管理员认证才能使用。",
], bg=colors.HexColor("#FFF3F3"), border=C_RED))
story.append(PageBreak())

# ── §1 首次启动 ─────────────────────────────────────────
story.append(Paragraph("一、首次启动流程", S_CH1))
story.append(HRFlowable(width=TW, thickness=1.2, color=C_RED))
story.append(Spacer(1, 3*mm))

story.append(step_box([
    "将海豹骰子机器人加入游戏群，确认插件 圣约翰预科高中.js 已加载。",
    "任意玩家（推荐 GM 自己）发送 .圣约翰设置，看到设置面板。",
    "复制面板内容，将【管理员】字段改为自己的 QQ 号后发送回群。"
      "（此时无管理员，任何人均可设置，设置后锁定。）",
    "可选：同样在面板中填入【公告群】群号（自动播报录取/毕业公告）"
      "和【推特群】群号（播报爆款推文/评论）。",
    "GM 发送 .圣约翰开始学期，全局时钟启动，游戏正式开始。",
    "通知所有玩家使用 .圣约翰注册 <英文名> 选择角色入学。",
]))
story.append(Spacer(1, 4*mm))

story.append(box([
    "⚠️ .圣约翰开始学期 只能执行一次，执行后时钟无法重置。",
    "⚠️ 游戏共12个月，以现实「自然天」推进。建议开学期前提前告知玩家游戏周期。",
], bg=colors.HexColor("#FFF8F8"), border=C_ORANGE))
story.append(Spacer(1, 5*mm))

# ── §2 设置面板 ─────────────────────────────────────────
story.append(Paragraph("二、设置面板详解", S_CH1))
story.append(HRFlowable(width=TW, thickness=1.2, color=C_RED))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("面板格式", S_CH2))
story.append(Paragraph(".圣约翰设置 显示的面板如下，复制后修改对应字段发回即可应用：", S_BODY))
story.append(Spacer(1, 2*mm))

panel_demo = Table([
    [Paragraph('.圣约翰设置\n【公告群】未设置\n【推特群】未设置\n【管理员】未设置\n\n📅 学期状态：未开始\n\n复制上方三行修改内容后直接发回即可应用。\n⚠️ 尚无管理员——任何人均可填写【管理员】字段完成首次设置。',
               sty("_pnl", fontSize=9, fontName=BASE, leading=14, textColor=C_DARK))]
], colWidths=[TW - 8])
panel_demo.setStyle(TableStyle([
    ('BACKGROUND',(0,0),(0,0), colors.HexColor("#F5F5F5")),
    ('BOX',       (0,0),(0,0), 0.8, C_BORDER),
    ('TOPPADDING',(0,0),(0,0), 8),
    ('BOTTOMPADDING',(0,0),(0,0),8),
    ('LEFTPADDING',(0,0),(0,0),12),
]))
story.append(panel_demo)
story.append(Spacer(1, 3*mm))

story.append(Paragraph("字段说明", S_CH2))
story.append(tbl([
    [th("字段"),    th("内容"),            th("作用"),                              th("备注")],
    [tdl("【公告群】"), tdl("群号（纯数字）"), tdl("大学录取结果、毕业公告自动播报到该群"), tdl("可与游戏群相同")],
    [tdl("【推特群】"), tdl("群号（纯数字）"), tdl("爆款推文、评论、粉丝里程碑广播到该群"), tdl("推荐单独设置观众群")],
    [tdl("【管理员】"), tdl("QQ号"),          tdl("拥有所有管理员指令权限"),               tdl("首次无限制，之后仅管理员可改")],
], cols=[TW*0.18, TW*0.22, TW*0.38, TW*0.22]))
story.append(Spacer(1, 3*mm))

story.append(box([
    "💡 「未设置」的字段留原文不变，不会被清空。只填需要修改的字段即可。",
    "💡 管理员可在游戏进行中随时更换公告群/推特群，重发面板修改即可。",
    "💡 如需转让管理员权限，在面板中将【管理员】改为新管理员的 QQ 号发送。",
], bg=C_LIGHT2, border=C_BLUE))
story.append(PageBreak())

# ── §3 属性调整 ─────────────────────────────────────────
story.append(Paragraph("三、属性调整指令（.圣约翰调整）", S_CH1))
story.append(HRFlowable(width=TW, thickness=1.2, color=C_RED))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("指令格式", S_CH2))
story.append(box([
    ".圣约翰调整 <英文名> <属性> <数值>",
    "数值格式：+20 = 增加20　-10 = 减少10　直接写数字 = 覆盖绝对值",
], bg=colors.HexColor("#F0F0F0"), border=C_DARK))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("可调整的属性", S_CH2))
story.append(tbl([
    [th("属性关键词"),       th("中/英文均可"),    th("范围"),      th("示例")],
    [tdl("精力 / energy"),   tdl("两者皆可"),      td("0–120"),    tdl(".圣约翰调整 James 精力 +30")],
    [tdl("压力 / stress"),   tdl("两者皆可"),      td("0–100"),    tdl(".圣约翰调整 Lily 压力 -20")],
    [tdl("人气 / popularity"),tdl("两者皆可"),     td("0–150"),    tdl(".圣约翰调整 Noah 人气 50")],
    [tdl("SAT / sat"),       tdl("大小写不限"),    td("400–1600"), tdl(".圣约翰调整 Eliot SAT +50")],
    [tdl("英语 / English"),  tdl("科目中英文均可"),td("0–7 tier"), tdl(".圣约翰调整 Callum 英语 +1")],
    [tdl("数学 / Math"),     tdl("同上"),          td("0–7 tier"), tdl(".圣约翰调整 Noah 数学 7")],
    [tdl("历史 / History"),  tdl("同上"),          td("0–7 tier"), tdl(".圣约翰调整 Vivienne 历史 6")],
    [tdl("生物 / Biology"),  tdl("同上"),          td("0–7 tier"), tdl("-")],
    [tdl("化学 / Chemistry"),tdl("同上"),          td("0–7 tier"), tdl("-")],
    [tdl("物理 / Physics"),  tdl("同上"),          td("0–7 tier"), tdl("-")],
    [tdl("外语 / ForeignLanguage"),tdl("同上"),    td("0–7 tier"), tdl(".圣约翰调整 Theo 外语 5")],
    [tdl("体育 / PE"),       tdl("同上"),          td("0–7 tier"), tdl("-")],
    [tdl("美术 / 艺术 / Art"),tdl("三种写法均可"), td("0–7 tier"), tdl("-")],
    [tdl("音乐 / Music"),    tdl("同上"),          td("0–7 tier"), tdl("-")],
    [tdl("计算机 / CS"),     tdl("同上"),          td("0–7 tier"), tdl("-")],
], cols=[TW*0.27, TW*0.18, TW*0.13, TW*0.42]))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("成绩 Tier 对照", S_CH3))
story.append(tbl([
    [th("Tier值"), th("0"), th("1"), th("2"), th("3"), th("4"), th("5"), th("6"), th("7")],
    [tdl("等级"),  td("C"), td("C+"),td("B-"),td("B"), td("B+"),td("A-"),td("A"), td("A+")],
], cols=[TW*0.18]+[TW*0.82/8]*8))
story.append(Spacer(1, 3*mm))

story.append(box([
    "⚠️ 成绩 tier 使用绝对值覆盖时，进度（progress）会自动清零，下次上课从0开始积累。",
    "⚠️ 所有调整立即生效并写入存储，玩家下次使用 .圣约翰档案 即可看到变化。",
    "💡 用途：修复 bug 导致的数据异常、给特殊活动奖励、平衡玩家差距。",
], bg=C_LIGHT2, border=C_BLUE))
story.append(PageBreak())

# ── §4 Gossip Girl 系统 ──────────────────────────────────
story.append(Paragraph("四、Gossip Girl 系统", S_CH1))
story.append(HRFlowable(width=TW, thickness=1.2, color=C_RED))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("系统说明", S_CH2))
story.append(box([
    "Gossip Girl 是 GM 专用的匿名账号，可预先储存一批帖子，由系统自动定时发送到推特群。",
    "发布节奏完全由 GM 控制——可以提前准备一整个学期的「内幕爆料」，让世界线自动推进。",
    "自动触发机制：游戏群有任意消息时，系统后台每5分钟检查一次时间戳，到达间隔后自动发送下一条。",
], bg=C_LIGHT2, border=C_BLUE))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("指令速查", S_CH2))
story.append(tbl([
    [th("指令"),                                        th("用途")],
    [tdl(".圣约翰gossip 添加 <内容>"),                   tdl("将帖子加入待发队列（可重复多次预存）")],
    [tdl(".圣约翰gossip 队列"),                          tdl("查看当前队列中的全部待发帖子及下次发送预计时间")],
    [tdl(".圣约翰gossip 清空"),                          tdl("清空整个发帖队列")],
    [tdl(".圣约翰gossip 发送"),                          tdl("立即发送队首帖子（不等间隔）")],
    [tdl(".圣约翰gossip 间隔 <小时>"),                   tdl("设置自动发帖间隔（默认4h，最小0.5h）")],
    [tdl(".圣约翰gossip 账号 <名称> <handle>"),          tdl("设置账号显示名和推特ID（默认：Gossip Girl / gossipgirl）")],
], cols=[TW*0.52, TW*0.48]))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("发布格式示例", S_CH2))
gossip_demo = Table([[Paragraph(
    "【Gossip Girl】\n@gossipgirl（Gossip Girl）\n\n下周舞会，有人会带一个意想不到的人来……猜猜是谁。\n\nXOXO, Gossip Girl",
    sty("_gd", fontSize=9, fontName=BASE, leading=14, textColor=C_DARK))
]], colWidths=[TW - 8])
gossip_demo.setStyle(TableStyle([
    ('BACKGROUND',(0,0),(0,0), colors.HexColor("#F5F5F5")),
    ('BOX',       (0,0),(0,0), 0.8, C_BORDER),
    ('TOPPADDING',(0,0),(0,0), 8),('BOTTOMPADDING',(0,0),(0,0),8),
    ('LEFTPADDING',(0,0),(0,0),12),
]))
story.append(gossip_demo)
story.append(Spacer(1, 3*mm))

story.append(Paragraph("NPC 自动推特互动（每小时）", S_CH2))
story.append(box([
    "独立于 Gossip Girl，系统每小时会对过去24小时内有发推的玩家自动触发 NPC 互动。",
    "每次随机选取最多3位玩家：45% 概率获得 NPC 评论，35% 概率获得 NPC 点赞，20% 无动静。",
    "互动结果汇总后以「推特互动播报」形式发送到推特群，玩家的推特主页数据同步更新。",
    "此功能无需GM干预，自动运行。",
], bg=C_LIGHT2, border=C_BLUE))
story.append(Spacer(1, 3*mm))

story.append(box([
    "💡 建议 Gossip Girl 帖子提前按时间线写好剧情钩子，配合玩家行为营造「被监视」的氛围。",
    "💡 如需临时发一条紧急爆料，用 .圣约翰gossip 发送 可绕过间隔直接发出。",
    "💡 Gossip Girl 帖子与玩家推文在同一群内显示，看起来像真实推特账号发帖。",
], bg=colors.HexColor("#FFF8E7"), border=C_GOLD))
story.append(PageBreak())

# ── §5 游戏节奏建议 ──────────────────────────────────────
story.append(Paragraph("五、游戏节奏建议", S_CH1))
story.append(HRFlowable(width=TW, thickness=1.2, color=C_RED))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("学期节奏参考（12个游戏月 = 12个自然天）", S_CH2))
story.append(tbl([
    [th("月份/时段"),  th("时间"),   th("建议GM动作"),                           th("玩家节点")],
    [tdl("第1月 九月"), tdl("Day 1"),  tdl("执行开始学期，发布欢迎公告"),           tdl("所有人注册入学")],
    [tdl("第2-3月"),    tdl("Day 2-3"),tdl("观察活跃度，必要时 .圣约翰调整 精力"),  tdl("上课/社团起步期")],
    [tdl("第4月 十二月"),tdl("Day 4"), tdl("提醒玩家「期末季压力高峰」注意放松"),   tdl("成绩冲刺，压力风险高")],
    [tdl("第5月 寒假"), tdl("Day 5"),  tdl("公告假期规则（精力×2），可办线下活动"),  tdl("社交/推特黄金期")],
    [tdl("第6-9月"),    tdl("Day 6-9"),tdl("适时举办玩家活动，调动推特群氛围"),     tdl("人气/关系冲刺期")],
    [tdl("第10月 六月"), tdl("Day 10"),tdl("公告「大学申请开放」！鼓励玩家申请"),   tdl("SAT锁定，提交申请")],
    [tdl("第11-12月"),  tdl("Day 11-12"),tdl("公告录取结果，推动玩家互相祝贺"),    tdl("暑假/等待录取")],
], cols=[TW*0.18, TW*0.12, TW*0.40, TW*0.30]))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("GM 可选活动建议", S_CH2))
acts = [
    ("推特事件",   "在推特群发布虚构「爆料」帖子或热点话题，带动玩家用推特互动"),
    ("突发事件",   "在公告群发布特殊事件（如「校运会取消，所有人精力+20」），然后用 .圣约翰调整 落实"),
    ("排行播报",   "定期在群里发送 .圣约翰排行 截图，营造竞争氛围"),
    ("大学提醒",   "第9月（五月）前提醒成绩不达标的玩家加速冲刺"),
    ("寒暑假活动", "假期期间发起线下或群内话题投票，保持玩家活跃"),
]
for name, desc in acts:
    story.append(Paragraph(f"▸ <b>{name}：</b>{desc}", sty("_act", fontSize=9, fontName=BASE,
                  spaceAfter=4, leading=14)))
story.append(PageBreak())

# ── §6 常见问题处理 ─────────────────────────────────────
story.append(Paragraph("六、常见问题处理", S_CH1))
story.append(HRFlowable(width=TW, thickness=1.2, color=C_RED))
story.append(Spacer(1, 3*mm))

faqs = [
    (
        "玩家数据异常（某项数值不合理）",
        "使用 .圣约翰调整 直接覆盖回正常值。\n例：.圣约翰调整 James 精力 80（重置到正常精力）",
        "注意"
    ),
    (
        "玩家忘记考SAT就到六月了",
        ".圣约翰考SAT 没有时间限制，六月后仍可考。但建议提前提醒玩家「五月备考季」。",
        "提示"
    ),
    (
        "推特群/公告群没收到消息",
        "检查机器人是否在目标群内；重新用 .圣约翰设置 面板填写群号并发回（会重新绑定endpoint）。",
        "排查"
    ),
    (
        "新玩家中途加入游戏",
        "直接 .圣约翰注册 即可，不影响现有进度。但中途加入的玩家游戏时间少，可视情况用 .圣约翰调整 给予补偿。",
        "处理"
    ),
    (
        "玩家想更换角色",
        "目前不支持更换角色（数据与角色key绑定）。如确需更换，只能由GM删除存储数据重新注册——风险较高，建议劝阻。",
        "注意"
    ),
    (
        "某玩家压力卡在95+无法学习",
        "使用 .圣约翰调整 <名> 压力 30 帮助玩家恢复（需玩家同意）。或告知玩家使用 .圣约翰放松。",
        "提示"
    ),
    (
        "推特 NPC 互动多久触发一次",
        "每小时触发一次（由群消息懒驱动，实际每5分钟检查时间戳）。对24小时内发布的推文进行模拟互动。机器人在线即可，无需手动操作。",
        "说明"
    ),
    (
        "Gossip Girl 队列为空但还想发爆料",
        "用 .圣约翰gossip 添加 <内容> 加入队列即可立即生效，无需重启。如果想跳过间隔立刻发，用 .圣约翰gossip 发送。",
        "提示"
    ),
]

for q, a, badge in faqs:
    badge_color = {"注意": C_RED2, "提示": C_GREEN, "排查": C_ORANGE, "处理": C_BLUE, "说明": C_NAVY}.get(badge, C_DARK)
    badge_cell = Table([[Paragraph(badge, sty("_b", fontSize=7.5, fontName=BOLD,
                   textColor=WHITE, alignment=TA_CENTER))]], colWidths=[14*mm])
    badge_cell.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(0,0), badge_color),
        ('TOPPADDING',(0,0),(0,0),3),('BOTTOMPADDING',(0,0),(0,0),3),
    ]))
    row = Table([
        [badge_cell, Paragraph(f"<b>Q: {q}</b>", sty("_fq", fontSize=9, fontName=BOLD, textColor=C_DARK))]
    ], colWidths=[15*mm, TW-15*mm-4])
    row.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),2)]))
    ans = Table([[Paragraph(f"→ {a}", sty("_fa", fontSize=8.5, leading=13))]], colWidths=[TW-4])
    ans.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(0,0), C_LIGHT2),
        ('BOX',(0,0),(0,0),0.3, C_BORDER),
        ('TOPPADDING',(0,0),(0,0),3),('BOTTOMPADDING',(0,0),(0,0),3),
        ('LEFTPADDING',(0,0),(0,0),8),
    ]))
    story.append(KeepTogether([row, ans, Spacer(1, 3*mm)]))

story.append(PageBreak())

# ── §7 快速参考 ─────────────────────────────────────────
story.append(Paragraph("七、管理员指令速查", S_CH1))
story.append(HRFlowable(width=TW, thickness=1.2, color=C_RED))
story.append(Spacer(1, 3*mm))

story.append(tbl([
    [th("指令"),                             th("权限"),     th("用途")],
    [tdl(".圣约翰设置"),                      td("管理员"),   tdl("查看/修改 公告群 推特群 管理员")],
    [tdl(".圣约翰开始学期"),                  td("管理员"),   tdl("启动全局游戏时钟（只能执行一次）")],
    [tdl(".圣约翰调整 <名> <属性> <值>"),     td("管理员"),   tdl("直接修改玩家任意属性")],
    [tdl(".圣约翰游戏状态"),                  td("所有人"),   tdl("查看当前月份/学期进度（GM 监控用）")],
    [tdl(".圣约翰排行"),                      td("所有人"),   tdl("查看人气排行榜")],
    [tdl(".圣约翰档案"),                      td("所有人"),   tdl("查看任意玩家状态（查 <名> 参数）")],
    [tdl(".圣约翰专业 <学校>"),               td("所有人"),   tdl("核实大学录取条件（GM 提示玩家用）")],
    [tdl(".圣约翰gossip 添加 <内容>"),        td("管理员"),   tdl("将帖子加入 Gossip Girl 待发队列")],
    [tdl(".圣约翰gossip 队列"),               td("管理员"),   tdl("查看待发帖子及下次发送时间")],
    [tdl(".圣约翰gossip 发送"),               td("管理员"),   tdl("立即发送队首帖子（跳过间隔）")],
    [tdl(".圣约翰gossip 间隔 <小时>"),        td("管理员"),   tdl("设置自动发帖间隔（默认4小时）")],
    [tdl(".圣约翰gossip 账号 <名> <handle>"), td("管理员"),   tdl("设置 Gossip Girl 账号名和推特ID")],
], cols=[TW*0.45, TW*0.15, TW*0.40]))
story.append(Spacer(1, 4*mm))

story.append(box([
    "📌 游戏中途如需暂停：没有暂停指令，但可以用 .圣约翰调整 把所有玩家精力设为0来暂时限制行动。",
    "📌 游戏数据存储在海豹骰子的 storageSet 中，不会因重启机器人而丢失。",
    "📌 Gossip Girl 队列和 NPC 互动时间戳均持久化存储，机器人重启后自动恢复，无需手动操作。",
], bg=C_LIGHT2, border=C_BLUE))

story.append(Spacer(1, 6*mm))
story.append(HRFlowable(width=TW, thickness=1, color=C_RED))
story.append(Spacer(1, 4*mm))
story.append(Paragraph("祝 GM 主持顺利，学期愉快！", sty("_end", fontSize=11, fontName=BOLD,
             textColor=C_DARK, alignment=TA_CENTER)))

# ── 页眉页脚 ─────────────────────────────────────────────
def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont(BASE, 7.5)
    canvas.setFillColor(colors.HexColor("#888888"))
    if doc.page > 1:
        canvas.drawString(ML, MB * 0.55, "圣约翰预科高中 · GM手册  ⚠ 仅限管理员")
        canvas.drawRightString(W - MR, MB * 0.55, f"第 {doc.page} 页")
        canvas.setStrokeColor(C_BORDER)
        canvas.setLineWidth(0.4)
        canvas.line(ML, MB * 0.9, W - MR, MB * 0.9)
    canvas.restoreState()

doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
print(f"✅ GM手册已生成：{out_path}")

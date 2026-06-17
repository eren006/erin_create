#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""圣约翰预科高中 玩家手册 PDF 生成脚本"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os, sys

# ── 字体注册（优先找系统中文字体）──────────────────────────────
FONT_PATHS = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/Library/Fonts/Arial Unicode MS.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
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

BASE  = "CN"      if have_cn  else "Helvetica"
BOLD  = "CN-Bold" if have_cnb else "Helvetica-Bold"

# ── 配色 ─────────────────────────────────────────────────────────
C_NAVY    = colors.HexColor("#1B2A4A")
C_GOLD    = colors.HexColor("#C9A84C")
C_CREAM   = colors.HexColor("#FDF8F0")
C_LIGHT   = colors.HexColor("#EAF0F8")
C_BLUE    = colors.HexColor("#3A5F8A")
C_RED     = colors.HexColor("#C0392B")
C_GREEN   = colors.HexColor("#27AE60")
C_PURPLE  = colors.HexColor("#6C3483")
C_ORANGE  = colors.HexColor("#D35400")
C_BORDER  = colors.HexColor("#CBD5E1")
C_ROW1    = colors.HexColor("#FAFBFC")
C_ROW2    = colors.HexColor("#EEF3FA")
WHITE     = colors.white
BLACK     = colors.black

# ── 样式 ─────────────────────────────────────────────────────────
ss = getSampleStyleSheet()

def sty(name, parent="Normal", **kw):
    kw.setdefault("fontName", BASE)
    kw.setdefault("leading",  kw.get("fontSize", 10) * 1.45)
    return ParagraphStyle(name, parent=ss[parent], **kw)

S_TITLE   = sty("TITLE",   fontSize=28, fontName=BOLD, textColor=WHITE,
                alignment=TA_CENTER, spaceAfter=4, leading=36)
S_SUBTITLE= sty("SUBTITLE",fontSize=13, textColor=C_GOLD,
                alignment=TA_CENTER, spaceAfter=2)
S_CH1     = sty("CH1",     fontSize=16, fontName=BOLD, textColor=C_NAVY,
                spaceBefore=14, spaceAfter=6, leading=22)
S_CH2     = sty("CH2",     fontSize=12, fontName=BOLD, textColor=C_BLUE,
                spaceBefore=8, spaceAfter=4)
S_CH3     = sty("CH3",     fontSize=10, fontName=BOLD, textColor=C_NAVY,
                spaceBefore=4, spaceAfter=2)
S_BODY    = sty("BODY",    fontSize=9,  spaceAfter=3)
S_SMALL   = sty("SMALL",   fontSize=8,  textColor=colors.HexColor("#555555"))
S_TH      = sty("TH",      fontSize=8.5,fontName=BOLD, textColor=WHITE,
                alignment=TA_CENTER)
S_TD      = sty("TD",      fontSize=8.5,alignment=TA_CENTER)
S_TD_L    = sty("TD_L",    fontSize=8.5,alignment=TA_LEFT)
S_BADGE   = sty("BADGE",   fontSize=7.5,fontName=BOLD, textColor=WHITE,
                alignment=TA_CENTER)
S_NOTE    = sty("NOTE",    fontSize=8,  textColor=C_BLUE, leftIndent=6,
                spaceAfter=2)
S_WARN    = sty("WARN",    fontSize=8,  textColor=C_RED,  leftIndent=6)
S_TIP     = sty("TIP",     fontSize=8,  textColor=C_GREEN,leftIndent=6)
S_CENTER  = sty("CENTER",  fontSize=9,  alignment=TA_CENTER)
S_PAGE_TITLE = sty("PT",   fontSize=20, fontName=BOLD, textColor=C_NAVY,
                   alignment=TA_CENTER, spaceBefore=20, spaceAfter=10)

W, H = A4
ML, MR, MT, MB = 18*mm, 18*mm, 20*mm, 18*mm
TW = W - ML - MR

def th(text): return Paragraph(text, S_TH)
def td(text, bold=False): return Paragraph(str(text), S_TH if bold else S_TD)
def tdl(text): return Paragraph(str(text), S_TD_L)

def ts(cmds, colWidths=None, rowH=None):
    t = Table(cmds, colWidths=colWidths, repeatRows=1, hAlign='LEFT')
    base = [
        ('FONTNAME',   (0,0),(-1,-1), BASE),
        ('FONTNAME',   (0,0),(-1,0),  BOLD),
        ('FONTSIZE',   (0,0),(-1,-1), 8.5),
        ('BACKGROUND', (0,0),(-1,0),  C_NAVY),
        ('TEXTCOLOR',  (0,0),(-1,0),  WHITE),
        ('ALIGN',      (0,0),(-1,-1), 'CENTER'),
        ('VALIGN',     (0,0),(-1,-1), 'MIDDLE'),
        ('GRID',       (0,0),(-1,-1), 0.3, C_BORDER),
        ('TOPPADDING', (0,0),(-1,-1), 3),
        ('BOTTOMPADDING',(0,0),(-1,-1),3),
        ('LEFTPADDING',(0,0),(-1,-1),4),
        ('RIGHTPADDING',(0,0),(-1,-1),4),
    ]
    for i in range(1, len(cmds)):
        bg = C_ROW1 if i % 2 == 1 else C_ROW2
        base.append(('BACKGROUND', (0,i),(-1,i), bg))
    t.setStyle(TableStyle(base))
    if rowH:
        t._argH = [rowH]*len(cmds)
    return t

def section_bar(title, color=C_NAVY):
    t = Table([[Paragraph(title, sty("_sb", fontSize=12, fontName=BOLD,
                textColor=WHITE, leading=16))]], colWidths=[TW])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(0,0), color),
        ('TOPPADDING', (0,0),(0,0), 5),
        ('BOTTOMPADDING',(0,0),(0,0),5),
        ('LEFTPADDING',(0,0),(0,0),10),
        ('RIGHTPADDING',(0,0),(0,0),10),
        ('ROUNDEDCORNERS', [3]),
    ]))
    return t

def info_box(lines, color=C_LIGHT, border=C_BLUE):
    rows = [[Paragraph(l, S_BODY)] for l in lines]
    t = Table(rows, colWidths=[TW - 4])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,-1), color),
        ('BOX',        (0,0),(-1,-1), 0.8, border),
        ('TOPPADDING', (0,0),(-1,-1), 3),
        ('BOTTOMPADDING',(0,0),(-1,-1),3),
        ('LEFTPADDING',(0,0),(-1,-1),8),
        ('RIGHTPADDING',(0,0),(-1,-1),8),
        ('FONTNAME',   (0,0),(-1,-1), BASE),
        ('FONTSIZE',   (0,0),(-1,-1), 8.5),
    ]))
    return t

def chapter_page(num, title, subtitle=""):
    elems = []
    elems.append(Spacer(1, 30*mm))
    t = Table([[Paragraph(f"Chapter {num}", sty("_cn", fontSize=11,
                fontName=BOLD, textColor=C_GOLD, alignment=TA_CENTER))]], colWidths=[TW])
    t.setStyle(TableStyle([('ALIGN',(0,0),(0,0),'CENTER')]))
    elems.append(t)
    elems.append(Spacer(1, 3*mm))
    elems.append(Paragraph(title, S_PAGE_TITLE))
    if subtitle:
        elems.append(Paragraph(subtitle, sty("_cs", fontSize=10, textColor=C_BLUE,
                     alignment=TA_CENTER)))
    elems.append(Spacer(1, 6*mm))
    elems.append(HRFlowable(width=TW, thickness=1.5, color=C_GOLD))
    elems.append(Spacer(1, 4*mm))
    return elems

# ════════════════════════════════════════════════════════════════
# 内容数据
# ════════════════════════════════════════════════════════════════

CHARS_MALE = [
    ("James Whitfield",  "全校最受欢迎的男生，本人对此毫无自觉",          "PE:A", "橄榄球队",          "U. of Michigan"),
    ("Noah Park",        "用讽刺掩盖社恐的高智商宅男",                    "Math:A / CS:A", "编程社",    "MIT"),
    ("Marcus Hale",      "永远在场、永远最响、永远是话题中心",             "PE:B+ / English:B", "摄影社", "NYU"),
    ("Connor Walsh",     "学校里最好的厨子，立志不上大学",                 "Bio:B / Chem:B+","烹饪社",   "Culinary Inst."),
    ("Jasper Laine",     "彻底活在自己世界里的艺术怪孩子",                 "Art:A / 绘画:进阶","美术社",  "Parsons"),
    ("Rafael Moreno",    "大家都知道他在申藤校，本人假装不在乎",           "Bio:A / Chem:B+","MUN/科学社","Johns Hopkins"),
    ("Oliver Tran",      "极度在乎别人怎么看他，但只有他自己知道",         "English:B / Art:B","摄影社",  "Fordham"),
    ("Eliot Zhao",       "全校最难读懂的人，不是因为他在装",               "Math:B+ / Phys:A","编程社",  "Princeton"),
    ("Theo Vasquez",     "像海绵一样吸收周围所有人，还没找到自己的形状",   "FL:A / PE:B","戏剧社",        "NYU"),
    ("Callum Reid",      "安静但不内向，观察力强到让人有点发毛",            "English:A","校报",           "Northwestern"),
    ("Ben Nakamura",     "运动员里最爱看书，书呆子里最能打球",             "PE:B / English:B+","篮球队", "Duke"),
]

CHARS_FEMALE = [
    ("Chloe Beaumont",   "自带主角光环但她自己会翻白眼",                  "English:A / 戏剧:入门","戏剧社","Northwestern"),
    ("Zoe Hartley",      "学校里跑得最快的人，其他方面一律不争",           "PE:A+",             "田径队",  "U. of Michigan"),
    ("Lily Chen",        "所有人都喜欢她，她不知道为什么",                 "FL:B+ / English:B","摄影社",   "Fordham"),
    ("Sofia Reyes",      "永远知道发生了什么，经常说出来",                 "FL:B+ / 摄影:入门","摄影社",   "Syracuse"),
    ("Vivienne Ashby",   "把所有精力都放在未来上，有时候忘了活在现在",     "History:A / FL:B+","MUN/辩论社","Georgetown"),
    ("Margot Seo",       "比实际年龄老很多的新生",                         "Music:A+ / 大提琴:进阶","管弦乐团","Juilliard"),
    ("Nadia Okafor",     "对不公平有天然的雷达，会当场说出来",             "English:A / History:B+","辩论社","Georgetown"),
    ("Wren Nakamura",    "对所有事情都过度投入，包括放弃",                 "Art:B+ / 戏剧:入门","戏剧社",  "NYU"),
    ("Amara Diallo",     "新生里最淡定的，因为她见过更大的场面",           "FL:A / History:B+","辩论社/MUN","Georgetown"),
    ("Jess Kim",         "所有人的好朋友，但没有最好的朋友",               "均衡（无明显短板）","摄影社",  "Boston U."),
    ("Petra Hoang",      "学校里最努力的人，但努力的方向是玩",             "PE:B+ / Art:B","摄影社",      "Boston U."),
]

COMMANDS = [
    # (指令, 精力消耗, 冷却, 效果)
    (".圣约翰注册 <英文名>",  "0",  "一次性", "选择角色，开始游戏"),
    (".圣约翰档案",           "0",  "无",     "查看自己的完整状态"),
    (".圣约翰精力",           "0",  "无",     "查看精力、压力、状态详情"),
    (".圣约翰排行",           "0",  "无",     "查看GPA/人气/SAT三项排行榜（前5名）"),
    (".圣约翰专业 [学校]",    "0",  "无",     "查看大学录取要求（合并转发，按T1-T4分节点）"),
    (".圣约翰帮助",           "0",  "无",     "显示所有指令（合并转发，按类别分节点）"),
    (".圣约翰游戏状态",       "0",  "无",     "查看当前月份/学期进度（合并转发）"),
]

STUDY_CMDS = [
    (".圣约翰上课 <科目>",     "20", "8h",    "提升指定科目成绩进度，有压力增加"),
    (".圣约翰自习",            "10", "6h",    "随机提升一科，效率稍低"),
    (".圣约翰备考SAT",         "25", "6h",    "提升SAT分数（压力大时效果差）"),
    (".圣约翰考SAT",           "40", "3天",   "锁定SAT分数，提交申请前必须考"),
]

SOCIAL_CMDS = [
    (".圣约翰社交",             "15", "4h",  "提升人气，可能认识新同学"),
    (".圣约翰发帖",             "10", "3h",  "发社交帖，有一定几率涨人气或压力"),
    (".圣约翰参加派对",         "30", "2天", "大幅提升人气，压力也可能增加"),
    (".圣约翰互动 <英文名>",    "10", "4h",  "增加与目标玩家的好感度"),
    (".圣约翰好感 <英文名>",    "0",  "无",  "查看与某人的关系状态"),
    (".圣约翰告白 <英文名>",    "30", "无",  "向对方表白（需好感60+）"),
    (".圣约翰接受 / 拒绝",      "0",  "无",  "回应别人的告白"),
    (".圣约翰约会 <英文名>",    "25", "2天", "与恋人约会，增强感情"),
    (".圣约翰补课 <英文名> <科>","20","8h",  "给对方提升一科成绩，同时增加好感"),
    (".圣约翰分手",             "0",  "无",  "结束恋爱关系"),
]

CLUB_CMDS = [
    (".圣约翰社团列表",         "0",  "无",  "查看所有社团及加入条件"),
    (".圣约翰加入 <社团>",      "0",  "无",  "申请加入社团（需满足门槛）"),
    (".圣约翰社团活动 <社团>",  "25", "8h",  "参加活动，提升社团等级/课外评分"),
    (".圣约翰我的社团",         "0",  "无",  "查看已加入的社团"),
    (".圣约翰竞选 <职位>",      "50", "7天", "竞选学生会（需人气达标）"),
]

ART_CMDS = [
    (".圣约翰选艺术 <方向>",    "0",  "一次性","选择艺术方向（音乐/表演/视觉类）"),
    (".圣约翰练习",             "20", "8h",   "提升艺术等级进度"),
    (".圣约翰演出",             "40", "3天",  "公开演出，提升人气和艺术进度"),
]

STRESS_CMDS = [
    (".圣约翰休息",             "0",  "8h",  "回复精力，不消耗精力"),
    (".圣约翰放松",             "20", "12h", "大幅降低压力"),
]

APPLY_CMDS = [
    (".圣约翰申请 <学校> <专业>","0", "无",  "提交大学申请（6月后开放）"),
]

TWITTER_CMDS = [
    (".圣约翰注册推特 <用户名>","0",  "一次性","注册推特账号"),
    (".圣约翰发推 <内容>",      "0",  "2h",   "发推文（内容影响爆款概率），系统即时生成NPC评论"),
    (".圣约翰推特 [用户名]",    "0",  "无",   "查看推特主页与最新推文及评论"),
    (".圣约翰点赞 <用户名>",    "0",  "30分", "给对方最新推文点赞，帮其涨粉"),
    (".圣约翰转发 <用户名>",    "0",  "2h",   "转发推文，双方涨粉并广播"),
]

SCAVENGE_CMDS = [
    (".圣约翰寻宝",             "0",  "6h",  "在校园角落随机拾取收藏品"),
    (".圣约翰收藏",             "0",  "无",  "查看已拥有的全部收藏品"),
]

ADMIN_CMDS = [
    (".圣约翰设置",             "仅管理员", "查看/修改公告群、推特群、管理员"),
    (".圣约翰开始学期",         "仅管理员", "启动全局游戏时钟（所有人共享时间）"),
    (".圣约翰调整 <名> <属性> <值>","仅管理员","直接调整玩家属性（精力/压力/科目tier）"),
]

SUBJECTS_CN = {
    "English":"英语", "Math":"数学", "History":"历史",
    "Biology":"生物", "Chemistry":"化学", "Physics":"物理",
    "ForeignLanguage":"外语", "PE":"体育", "Art":"美术", "Music":"音乐", "CS":"计算机"
}

CLUBS_TABLE = [
    # (社团, 类型, 门槛, 课外类别, 人气加成)
    ("摄影社",     "开放", "无",                    "media",       "+0"),
    ("环保社",     "开放", "无",                    "environmental","+0"),
    ("烹饪社",     "开放", "无",                    "culinary",    "+0"),
    ("文学杂志社", "开放", "无",                    "media",       "+0"),
    ("辩论社",     "门槛", "英语 B- 以上",          "debate",      "+6"),
    ("模拟联合国", "门槛", "历史/外语 B- 以上",     "debate",      "+5"),
    ("校报",       "门槛", "英语 B- 以上",          "media",       "+4"),
    ("编程社",     "门槛", "数学 B- 以上",          "cs",          "+0"),
    ("科学社",     "门槛", "生物/化学任一 B 以上",  "medical",     "+0"),
    ("美术社",     "门槛", "美术 B- 或 视觉艺术天赋 入门","art",  "+0"),
    ("管弦乐团",   "门槛", "音乐天赋 入门 以上",    "music",       "+0"),
    ("戏剧社",     "门槛", "戏剧/舞蹈天赋 入门 以上","art",        "+4"),
    ("橄榄球队",   "高门槛","体育 B+ 且人气40+",    "sports",      "+8"),
    ("田径队",     "高门槛","体育 B+ 以上",         "sports",      "+6"),
    ("篮球队",     "高门槛","体育 A 且人气50+",     "sports",      "+8"),
]

COLLEGES_TABLE = [
    # tier, 学校, 代表专业, GPA要求, SAT要求
    ("T1","Harvard",    "Pre-Med / CS",           "3.90", "1520+"),
    ("T1","MIT",        "CS / Engineering",        "3.85", "1540+"),
    ("T1","Princeton",  "CS / Law",                "3.85", "1500+"),
    ("T1","Stanford",   "Business / CS",           "3.88", "1500+"),
    ("T1","Columbia",   "Finance / Pre-Med",       "3.82", "1480+"),
    ("T1","Yale",       "Law / History",           "3.85", "1490+"),
    ("T1","Duke",       "Political Sci. / Biology","3.80", "1450+"),
    ("T1","Juilliard",  "Music / Theater",         "艺术精通", "1200+"),
    ("T2","Georgetown", "Intl. Relations / Law",   "3.68", "1380+"),
    ("T2","Northwestern","Journalism / Theater",   "3.68", "1400+"),
    ("T2","Johns Hopkins","Pre-Med / Biology",     "3.75", "1430+"),
    ("T2","NYU",        "Film/Media / Psychology", "3.45", "1280+"),
    ("T2","Parsons",    "Fine Arts / Design",      "艺术熟练", "1200+"),
    ("T3","Boston U.",  "Business / Journalism",   "3.20", "1200+"),
    ("T3","Fordham",    "Psychology / Business",   "3.10", "1180+"),
    ("T3","Syracuse",   "Journalism / Media",      "3.15", "1200+"),
    ("T3","Culinary I.A.","Culinary Arts",         "2.80", "1050+"),
]

STRESS_TABLE = [
    ("0–39",  "状态良好",   "无",             "正常"),
    ("40–59", "有点疲惫",   "上课效率 -5%",   "正常"),
    ("60–79", "压力较大",   "上课 -15% / SAT -30pts","正常"),
    ("80–94", "快撑不住了", "上课 -25% / SAT无效","正常"),
    ("95+",   "崩溃边缘",   "上课/SAT完全无效","所有学习锁定"),
]

RELATION_TABLE = [
    ("0–19",  "陌生人",  "互动冷却 4h"),
    ("20–39", "普通同学","互动冷却 4h"),
    ("40–59", "朋友",    "互动冷却 4h"),
    ("60–79", "好朋友",  "互动冷却缩短至 2h"),
    ("80–99", "心动中",  "互动冷却 2h，可告白"),
    ("100+",  "挚友",    "冷却 2h，告白成功率提升"),
]

COUNCIL_TABLE = [
    ("班级代表", "60+",  "+15 人气奖励"),
    ("干事",     "75+",  "+25 人气奖励"),
    ("副主席",   "90+",  "+40 人气奖励"),
    ("主席",     "110+", "+60 人气奖励"),
]

COLLECTIBLES = [
    ("📒 旧笔记本",    "普通",  "上一届学长留下的英语笔记"),
    ("☕ 联名咖啡杯",  "普通",  "拾取即获 精力+25"),
    ("🎸 吉他拨片",    "普通",  "校乐队走廊遗落"),
    ("📰 旧校报",      "普通",  "泛黄的校园周报"),
    ("🏈 队徽",        "普通",  "球队纪念品"),
    ("🌸 压花书签",    "普通",  "春季活动留念"),
    ("✏️ 复古铅笔盒",  "普通",  "复古款文具"),
    ("📸 宝丽来照片",  "稀有",  "不知道谁拍的合影"),
    ("🏆 奖杯碎片",    "稀有",  "拾取即获 压力-20"),
    ("💌 匿名情书",    "稀有",  "不知道寄给谁的"),
    ("🔬 实验记录本",  "稀有",  "拾取即获 化学进度+15"),
    ("🎵 手写乐谱",    "稀有",  "拾取即获 艺术进度+20"),
    ("🍕 神秘食谱",    "稀有",  "拾取即获 压力-25"),
    ("⭐ 金色星星",    "传说",  "拾取即获 随机科目进度+8"),
    ("🗝️ 神秘钥匙",   "传说",  "不知道开什么门"),
    ("🎭 戏剧面具",    "传说",  "拾取即获 人气+20"),
]

CALENDAR = [
    ("1", "九月",   "开学季", "学习+社交 全力开动"),
    ("2", "十月",   "正常月", "社团活动好时机"),
    ("3", "十一月", "正常月", "冲刺成绩"),
    ("4", "十二月", "期末季", "压力高峰，注意放松"),
    ("5", "寒假",   "假期",   "精力恢复翻倍，无法上课"),
    ("6", "二月",   "新学期", "可重新规划方向"),
    ("7", "三月",   "正常月", "人气冲刺好时机"),
    ("8", "四月",   "春假",   "轻松月，社交/推特发力"),
    ("9", "五月",   "正常月", "备战SAT好时机"),
    ("10","六月",   "期末季", "大学申请正式开放！"),
    ("11","七月",   "暑假",   "精力恢复翻倍，冲推特/寻宝"),
    ("12","八月",   "暑假",   "最终冲刺，等待录取结果"),
]

TWITTER_CONTENT = [
    ("💬 八卦类",   "恋爱/告白/分手/爆料/drama", "最高 ×2.2", "高"),
    ("📚 学习类",   "作业/考试/SAT/GPA/图书馆",  "低 ×0.4",  "极低"),
    ("🏆 运动类",   "比赛/训练/社团/演出/赢了",   "中 ×1.5",  "低"),
    ("✏️ 日常类",  "（无特殊关键词）",             "基础概率",  "基础"),
]

TWITTER_COMMENTS = [
    ("🔥 爆款",   "3条", "全校热议语气，戏剧性评论"),
    ("👍 好评",   "2条", "积极鼓励/共鸣语气"),
    ("😐 普通",   "1条", "简短回应"),
    ("💢 争议",   "2条", "质疑/批评语气"),
    ("🌊 被骂上热搜","3条","混合：部分支持，部分强烈反对"),
]

# ════════════════════════════════════════════════════════════════
# 构建 PDF
# ════════════════════════════════════════════════════════════════

out_path = os.path.join(os.path.dirname(__file__), "圣约翰预科高中_玩家手册.pdf")
doc = SimpleDocTemplate(out_path, pagesize=A4,
                        leftMargin=ML, rightMargin=MR,
                        topMargin=MT, bottomMargin=MB)
story = []

# ── 封面 ─────────────────────────────────────────────────────────
cover = Table([
    [Paragraph("圣约翰预科高中", sty("_cov", fontSize=32, fontName=BOLD,
               textColor=WHITE, alignment=TA_CENTER, leading=42))],
    [Paragraph("St. John's Preparatory High School", sty("_cov2", fontSize=14,
               textColor=C_GOLD, alignment=TA_CENTER))],
    [Spacer(1, 8*mm)],
    [HRFlowable(width=TW*0.6, thickness=1.5, color=C_GOLD)],
    [Spacer(1, 8*mm)],
    [Paragraph("玩 家 游 玩 手 册", sty("_sub", fontSize=16, fontName=BOLD,
               textColor=C_GOLD, alignment=TA_CENTER))],
    [Spacer(1, 4*mm)],
    [Paragraph("Seal Dice 校园生活模拟 · QQ群组多人游戏", sty("_sub2", fontSize=10,
               textColor=colors.HexColor("#CBD5E1"), alignment=TA_CENTER))],
], colWidths=[TW])
cover.setStyle(TableStyle([
    ('BACKGROUND', (0,0),(0,-1), C_NAVY),
    ('ALIGN',      (0,0),(0,-1), 'CENTER'),
    ('TOPPADDING', (0,0),(0,-1), 6),
    ('BOTTOMPADDING',(0,0),(0,-1),6),
    ('ROWBACKGROUNDS',(0,0),(0,-1),[C_NAVY]),
]))
story.append(Spacer(1, 25*mm))
story.append(cover)
story.append(Spacer(1, 12*mm))

# 封面提示框
story.append(info_box([
    "📌 本手册基于最新版本插件编写，适用于海豹骰子（Seal Dice）QQ群组使用。",
    "📌 所有指令均以 . （英文句点）开头，在游戏群内直接发送即可。",
    "📌 游戏以「自然天」为单位推进，所有玩家共享同一游戏时钟。",
], color=C_LIGHT, border=C_GOLD))
story.append(PageBreak())

# ── Chapter 1: 游戏概述 ──────────────────────────────────────────
story += chapter_page(1, "游戏概述", "你是谁，你在哪，你要去哪")

story.append(Paragraph("游戏背景", S_CH2))
story.append(Paragraph(
    "欢迎来到圣约翰预科高中！这是一所位于美国东北部的精英预科学校。你将扮演22位学生之一，"
    "在一个真实时钟驱动的学期里刷成绩、交朋友、谈恋爱、参加社团、竞选学生会，"
    "最终在六月申请自己理想的大学。", S_BODY))
story.append(Spacer(1, 3*mm))

story.append(info_box([
    "🎯 游戏目标：在学期结束前（第10月六月）积累足够的 GPA、SAT分数和课外活动，成功申请到目标大学。",
    "⏰ 时间系统：游戏以现实时间的「自然天」推进，管理员执行 .圣约翰开始学期 后，"
      "所有玩家共享同一时间线，共12个游戏月。",
    "👥 多人互动：玩家之间可以互补课、互动好感、告白交往，甚至在推特上互相点赞转发。",
]))
story.append(Spacer(1, 4*mm))

story.append(Paragraph("核心数值", S_CH2))
cols = [TW*0.22, TW*0.18, TW*0.18, TW*0.42]
story.append(ts([
    [th("数值"), th("初始值"), th("上限"), th("说明")],
    [tdl("⚡ 精力"), td("80"), td("120"), tdl("行动货币，各指令均消耗精力，自然恢复")],
    [tdl("😤 压力"), td("10"), td("100"), tdl("过高将严重削弱学习效率，95+锁定学习")],
    [tdl("⭐ 人气"), td("20"), td("150"), tdl("影响学生会竞选、部分社团门槛")],
    [tdl("📚 成绩"), td("各异", bold=False), td("A+", bold=False), tdl("C→C+→B-→B→B+→A-→A→A+，共8档")],
    [tdl("🎭 艺术"), td("各异", bold=False), td("大师", bold=False), tdl("初学→入门→进阶→熟练→精通→大师，共6级")],
], colWidths=cols))
story.append(Spacer(1, 4*mm))

story.append(Paragraph("学年日历", S_CH2))
story.append(ts([
    [th("月份"), th("现实月份"), th("类型"), th("特点")],
] + [[td(r[0]), td(r[1]), tdl(r[2]), tdl(r[3])] for r in CALENDAR],
colWidths=[TW*0.08, TW*0.12, TW*0.12, TW*0.68]))
story.append(Spacer(1,2*mm))
story.append(Paragraph("※ 假期期间精力恢复速度翻倍，但无法上课/考SAT/参加社团活动。大学申请在第10月（六月）正式开放。", S_SMALL))

story.append(PageBreak())

# ── Chapter 2: 角色名单 ──────────────────────────────────────────
story += chapter_page(2, "角色名单", "22位同学，各有来历")

story.append(Paragraph("如何选择角色", S_CH2))
story.append(info_box([
    "使用 .圣约翰注册 <英文名（名字）> 来选择你的角色。例：.圣约翰注册 James",
    "每个角色起步总分相同（均衡设计），但擅长科目不同，对应不同的目标大学。",
    "选择时参考角色描述和目标路线，选一个你感兴趣的角色扮演方向。",
]))
story.append(Spacer(1, 4*mm))

story.append(Paragraph("男生（11人）", S_CH2))
mcols = [TW*0.20, TW*0.33, TW*0.20, TW*0.15, TW*0.12]
story.append(ts([
    [th("姓名"), th("角色简介"), th("优势科目/特长"), th("默认社团"), th("目标院校")]
] + [[tdl(r[0]), tdl(r[1]), tdl(r[2]), tdl(r[3]), tdl(r[4])] for r in CHARS_MALE],
colWidths=mcols))
story.append(Spacer(1, 5*mm))

story.append(Paragraph("女生（11人）", S_CH2))
story.append(ts([
    [th("姓名"), th("角色简介"), th("优势科目/特长"), th("默认社团"), th("目标院校")]
] + [[tdl(r[0]), tdl(r[1]), tdl(r[2]), tdl(r[3]), tdl(r[4])] for r in CHARS_FEMALE],
colWidths=mcols))
story.append(Spacer(1, 3*mm))
story.append(Paragraph(
    "※ 注册后无法更换角色。各角色总成绩档位之和相同，不存在「开局强」的角色——只有方向是否匹配你的目标院校。",
    S_SMALL))

story.append(PageBreak())

# ── Chapter 3: 成绩与GPA ─────────────────────────────────────────
story += chapter_page(3, "成绩与GPA系统", "从 C 到 A+ 的升级之路")

story.append(Paragraph("成绩档位对应表", S_CH2))
gcols = [TW*0.15, TW*0.15, TW*0.15, TW*0.55]
story.append(ts([
    [th("档位"), th("等级"), th("GPA折算"), th("说明")],
    [td("0"), td("C"),   td("1.7"), tdl("起始档位（部分角色默认在此）")],
    [td("1"), td("C+"),  td("2.0"), tdl("普通学生水平")],
    [td("2"), td("B-"),  td("2.3"), tdl("中等")],
    [td("3"), td("B"),   td("2.7"), tdl("多数角色起点集中在此附近")],
    [td("4"), td("B+"),  td("3.0"), tdl("良好，已可申请中等院校")],
    [td("5"), td("A-"),  td("3.3"), tdl("优秀")],
    [td("6"), td("A"),   td("3.7"), tdl("卓越，顶尖院校门槛")],
    [td("7"), td("A+"),  td("4.0"), tdl("满分，全校前列")],
], colWidths=gcols))
story.append(Spacer(1, 3*mm))
story.append(Paragraph(
    "GPA = 11门课程档位的平均值折算。每档进度条需要满100点才能升级，"
    ".圣约翰上课 每次约+15–25点，自习约+10–18点。", S_BODY))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("11门课程", S_CH2))
subj_data = [["英语", "数学", "历史", "生物", "化学", "物理", "外语", "体育", "美术", "音乐", "计算机"]]
subj_t = Table([subj_data[0]], colWidths=[TW/11]*11)
subj_t.setStyle(TableStyle([
    ('BACKGROUND', (0,0),(-1,-1), C_NAVY),
    ('TEXTCOLOR',  (0,0),(-1,-1), WHITE),
    ('FONTNAME',   (0,0),(-1,-1), BASE),
    ('FONTSIZE',   (0,0),(-1,-1), 8),
    ('ALIGN',      (0,0),(-1,-1), 'CENTER'),
    ('VALIGN',     (0,0),(-1,-1), 'MIDDLE'),
    ('GRID',       (0,0),(-1,-1), 0.3, C_BORDER),
    ('TOPPADDING', (0,0),(-1,-1), 5),
    ('BOTTOMPADDING',(0,0),(-1,-1),5),
]))
story.append(subj_t)
story.append(Spacer(1, 3*mm))
story.append(Paragraph(
    "指令：.圣约翰上课 英语（或 English）　/　.圣约翰上课 数学（或 Math）等，支持中英文名", S_BODY))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("压力对学习的影响", S_CH2))
story.append(ts([
    [th("压力区间"), th("状态"), th("上课效率"), th("额外说明")],
] + [[td(r[0]), tdl(r[1]), tdl(r[2]), tdl(r[3])] for r in STRESS_TABLE],
colWidths=[TW*0.15, TW*0.18, TW*0.30, TW*0.37]))
story.append(Spacer(1, 3*mm))
story.append(Paragraph("⚠️ 压力达到95+时所有学习指令被完全锁定！使用 .圣约翰放松 降压。", S_WARN))

story.append(PageBreak())

# ── Chapter 4: 所有指令 ──────────────────────────────────────────
story += chapter_page(4, "指令速查手册", "你在圣约翰能做的所有事")

def cmd_table(rows, col_widths=None):
    if col_widths is None:
        col_widths = [TW*0.38, TW*0.10, TW*0.13, TW*0.39]
    return ts([[th("指令"), th("精力"), th("冷却"), th("效果")]] +
              [[tdl(r[0]), td(r[1]), td(r[2]), tdl(r[3])] for r in rows],
              colWidths=col_widths)

story.append(section_bar("基础信息指令"))
story.append(Spacer(1,2*mm))
story.append(ts([[th("指令"), th("精力"), th("冷却"), th("效果")]] +
               [[tdl(r[0]), td(r[1]), td(r[2]), tdl(r[3])] for r in COMMANDS],
               colWidths=[TW*0.38, TW*0.10, TW*0.13, TW*0.39]))
story.append(Spacer(1, 5*mm))

story.append(section_bar("学习系统", C_BLUE))
story.append(Spacer(1,2*mm))
story.append(cmd_table(STUDY_CMDS))
story.append(Spacer(1,2*mm))
story.append(info_box([
    "SAT满分1600，大学申请需要考出成绩。压力越高SAT分数越低，建议在压力<60时备考。",
    ".圣约翰考SAT 会锁定当前分数，只能考一次（可多次备考后选择最佳时机正式考试）。"
]))
story.append(Spacer(1, 5*mm))

story.append(section_bar("艺术/音乐特招", C_PURPLE))
story.append(Spacer(1,2*mm))
story.append(cmd_table(ART_CMDS))
story.append(Spacer(1,2*mm))
story.append(info_box([
    "艺术方向分三类：音乐（钢琴/小提琴/大提琴/长笛/吉他/声乐/作曲）、"
    "表演（戏剧/舞蹈）、视觉（绘画/摄影/雕塑/陶艺/数字艺术）。",
    "Juilliard需要艺术等级达到「精通」，Parsons需要「熟练」。",
    "管弦乐团需要「音乐」方向入门+；戏剧社需要「表演」方向入门+。",
]))
story.append(Spacer(1, 5*mm))

story.append(section_bar("社交与人气", C_ORANGE))
story.append(Spacer(1,2*mm))
story.append(cmd_table(SOCIAL_CMDS,
    col_widths=[TW*0.38, TW*0.10, TW*0.13, TW*0.39]))
story.append(Spacer(1, 5*mm))

story.append(section_bar("压力管理", C_GREEN))
story.append(Spacer(1,2*mm))
story.append(cmd_table(STRESS_CMDS))
story.append(Spacer(1,2*mm))
story.append(info_box([
    ".圣约翰休息 不消耗精力，同时回复精力，冷却8h。",
    ".圣约翰放松 消耗20精力但大幅降低压力，适合压力超过60时优先使用。",
]))
story.append(PageBreak())

story.append(section_bar("社团系统"))
story.append(Spacer(1,2*mm))
story.append(cmd_table(CLUB_CMDS))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("所有社团一览", S_CH3))
story.append(ts([
    [th("社团"), th("类型"), th("加入门槛"), th("课外类别"), th("人气加成/活动")],
] + [[tdl(r[0]), td(r[1]), tdl(r[2]), td(r[3]), td(r[4])] for r in CLUBS_TABLE],
colWidths=[TW*0.17, TW*0.10, TW*0.35, TW*0.22, TW*0.16]))
story.append(Spacer(1,2*mm))
story.append(Paragraph(
    "社团等级提升需要多次 .圣约翰社团活动，高等级社团成员在申请时可获得更高课外评分加成。",
    S_SMALL))

story.append(Spacer(1, 5*mm))
story.append(section_bar("学生会竞选", C_PURPLE))
story.append(Spacer(1,2*mm))
story.append(ts([
    [th("职位"), th("所需人气"), th("竞选奖励（人气）")],
] + [[tdl(r[0]), td(r[1]), tdl(r[2])] for r in COUNCIL_TABLE],
colWidths=[TW*0.30, TW*0.30, TW*0.40]))
story.append(Spacer(1,2*mm))
story.append(info_box([
    "竞选冷却 7天。消耗精力 50。成功率与当前人气相关。",
    "部分大学专业（如 Georgetown Law、Northwestern Journalism）需要持有学生会职位才能申请。",
]))

story.append(PageBreak())

# ── Chapter 5: 社交/关系系统 ──────────────────────────────────────
story += chapter_page(5, "社交与恋爱系统", "从陌生人到挚友，再到更进一步")

story.append(Paragraph("关系阶段", S_CH2))
story.append(ts([
    [th("好感值"), th("关系阶段"), th("效果")],
] + [[td(r[0]), tdl(r[1]), tdl(r[2])] for r in RELATION_TABLE],
colWidths=[TW*0.18, TW*0.22, TW*0.60]))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("恋爱流程", S_CH2))
story.append(info_box([
    "1️⃣  多次使用 .圣约翰互动 <英文名> 积累好感（冷却4h，好友后缩短至2h）",
    "2️⃣  好感值达到 80 以上时，使用 .圣约翰告白 <英文名> 表白",
    "3️⃣  对方玩家收到通知，用 .圣约翰接受 或 .圣约翰拒绝 回应",
    "4️⃣  接受后成为恋人，可以使用 .圣约翰约会 进一步发展感情",
    "5️⃣  恋爱关系需要维系——超过48小时没有互动好感会自动衰减",
    "6️⃣  使用 .圣约翰分手 结束关系（会有人气/压力变化）",
]))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("补课系统", S_CH2))
story.append(info_box([
    ".圣约翰补课 <英文名> <科目>：消耗精力20，帮助对方提升指定科目进度，同时为双方增加好感值。",
    "冷却8小时（对同一人同一科目）。是快速推进好感的高效方式。",
]))

story.append(PageBreak())

# ── Chapter 6: 大学申请 ──────────────────────────────────────────
story += chapter_page(6, "大学申请系统", "目标在哪，路就在哪")

story.append(Paragraph("申请流程", S_CH2))
story.append(info_box([
    "1️⃣  使用 .圣约翰专业 [学校名] 查询目标学校各专业的录取要求",
    "2️⃣  在第10月（六月）前完成 .圣约翰考SAT，锁定SAT成绩",
    "3️⃣  第10月起，使用 .圣约翰申请 <学校> <专业> 提交申请",
    "4️⃣  系统根据你的GPA、SAT、课外活动、社团等级等综合评估",
    "5️⃣  可同时申请多所学校，选择最好的录取结果",
]))
story.append(Spacer(1, 4*mm))

story.append(Paragraph("大学分级与热门院校", S_CH2))
story.append(ts([
    [th("等级"), th("学校"), th("代表专业"), th("最低GPA"), th("SAT要求")],
] + [[td(r[0]), tdl(r[1]), tdl(r[2]), td(r[3]), td(r[4])] for r in COLLEGES_TABLE],
colWidths=[TW*0.08, TW*0.22, TW*0.30, TW*0.18, TW*0.22]))
story.append(Spacer(1, 3*mm))
story.append(info_box([
    "💡 T1 顶尖院校（Harvard/MIT/Princeton等）：GPA 3.80+ 且 SAT 1450+，还需要强课外活动",
    "💡 T2 优质院校（Georgetown/Northwestern/NYU等）：GPA 3.45+ 且 SAT 1280+",
    "💡 T3 保底院校（Boston U./Fordham等）：GPA 3.0+ 且 SAT 1180+",
    "💡 艺术特招（Juilliard/Parsons）：成绩要求较低，但艺术等级须达到「熟练/精通」",
]))

story.append(PageBreak())

# ── Chapter 7: 推特系统 ──────────────────────────────────────────
story += chapter_page(7, "推特系统", "校园社交媒体 · 成为焦点")

story.append(Paragraph("推特指令", S_CH2))
story.append(ts([
    [th("指令"), th("精力"), th("冷却"), th("效果")],
] + [[tdl(r[0]), td(r[1]), td(r[2]), tdl(r[3])] for r in TWITTER_CMDS],
colWidths=[TW*0.38, TW*0.10, TW*0.13, TW*0.39]))
story.append(Spacer(1, 4*mm))

story.append(Paragraph("内容关键词影响爆款概率", S_CH2))
story.append(ts([
    [th("内容类型"), th("触发关键词（含其中之一即触发）"), th("爆款概率"), th("争议概率")],
] + [[tdl(r[0]), tdl(r[1]), td(r[2]), td(r[3])] for r in TWITTER_CONTENT],
colWidths=[TW*0.18, TW*0.44, TW*0.19, TW*0.19]))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("推文结果说明", S_CH2))
results = [
    ("🔥 爆款", "粉丝 +40-120", "人气 +15", "广播到推特群，生成3条NPC评论"),
    ("👍 好评", "粉丝 +8-35",  "人气 +5",  "广播到推特群，生成2条NPC评论"),
    ("😐 普通", "粉丝 +1-8",   "无",       "不广播，生成1条NPC评论"),
    ("💢 争议", "粉丝 -5-30",  "人气 -10，压力 +18", "部分人取关，生成2条批评评论"),
    ("🌊 被骂", "粉丝 +3-15",  "人气 -5，压力 +12",  "净涨粉但名声受损，生成3条混合评论"),
]
story.append(ts([
    [th("结果"), th("粉丝变化"), th("人气/压力"), th("其他效果 + NPC评论")],
] + [[tdl(r[0]), tdl(r[1]), tdl(r[2]), tdl(r[3])] for r in results],
colWidths=[TW*0.15, TW*0.20, TW*0.28, TW*0.37]))
story.append(Spacer(1, 3*mm))

story.append(Paragraph("NPC 自动评论", S_CH2))
story.append(info_box([
    "发推后系统立即从22位校园同学中随机选取若干人生成真实感评论，结果会出现在发推回复中，"
    "并在 .圣约翰推特 查看主页时持续显示在最新推文下方。",
    "评论内容按推文类型分类（八卦/学习/运动/日常），对应不同语气和风格。",
    "爆款推文：3条评论（强烈兴奋/传播语气）",
    "好评/争议推文：2条评论",
    "普通推文：1条简短评论",
]))
story.append(Spacer(1, 3*mm))

story.append(info_box([
    "📌 发推后系统即时生成 1–3 条同学NPC评论，随结果显示（爆款=3条，争议=2条，普通=1条）。",
    "📌 评论内容按推文类型分类：八卦/学习/运动/日常各有不同评论风格，NPC均为校内22位同学。",
    "📌 粉丝里程碑（10/50/100/300/500/1000）会自动广播到推特群。",
    "📌 .圣约翰点赞 积累5个赞时自动广播「正在流行」通知。",
    "📌 .圣约翰转发 双方涨粉，被转发方粉丝同样增加。",
]))

story.append(PageBreak())

# ── Chapter 8: 收藏系统 ──────────────────────────────────────────
story += chapter_page(8, "校园收藏系统", "探索圣约翰的每个角落")

story.append(Paragraph("收藏指令", S_CH2))
story.append(cmd_table(SCAVENGE_CMDS))
story.append(Spacer(1, 3*mm))
story.append(info_box([
    ".圣约翰寻宝 每次随机拾取一件物品，冷却6小时。部分物品拾取时立即触发效果。",
    "物品分三个稀有度：普通（7种）/ 稀有（6种）/ 传说（3种），共16种。",
    "使用 .圣约翰收藏 查看进度（X/16种）。",
]))
story.append(Spacer(1, 4*mm))

story.append(Paragraph("全部收藏品一览", S_CH2))
rcols = [TW*0.20, TW*0.13, TW*0.67]
story.append(ts([
    [th("物品"), th("稀有度"), th("描述/效果")],
] + [[tdl(r[0]), td(r[1]), tdl(r[2])] for r in COLLECTIBLES],
colWidths=rcols))

story.append(PageBreak())

# ── Chapter 9: 策略指南 ─────────────────────────────────────────
story += chapter_page(9, "策略指南", "怎么玩才不会翻车")

story.append(Paragraph("通用原则", S_CH2))
tips = [
    ("精力管理", "每次行动都消耗精力，优先使用 .圣约翰休息（免费恢复）再行动。精力不足时学习效率大打折扣。"),
    ("压力控制", "压力超过60就要重视！先 .圣约翰放松 再继续学习。压力95+会完全锁定学习。"),
    ("假期利用", "寒暑假精力恢复翻倍，是社交/推特/寻宝的黄金期。好感的提升不受假期限制。"),
    ("社团选择", "尽早加入与目标大学专业匹配的社团，多次参加活动提升社团等级，申请时加成更高。"),
    ("互补合作", "与其他玩家互补课——你帮对方补弱科，对方帮你补弱科，好感+成绩双赢。"),
    ("SAT时机", "建议在压力<40时备考+考试。不要在期末季（压力高峰）考SAT。"),
    ("申请策略", "用 .圣约翰专业 仔细研究目标院校要求，申请前确认GPA、SAT、课外活动全部达标。"),
    ("推特运营", "发带有「drama/八卦」关键词的推文爆款概率最高，但争议风险也最大。学习类最安全。"),
]
for t, d in tips:
    story.append(Paragraph(f"▸ <b>{t}</b>：{d}", sty("_tip", fontSize=9, fontName=BASE, spaceAfter=4,
                  leading=14)))
story.append(Spacer(1, 4*mm))

story.append(Paragraph("角色路线参考", S_CH2))
routes = [
    ("学术型（目标T1）",    "James→MIT / Noah→MIT / Eliot→Princeton",
     "早期集中上主科，尽快把核心科目推到A档。第9月前考完SAT。"),
    ("艺术特招型",          "Jasper→Parsons / Margot→Juilliard / Chloe→Northwestern",
     "每次 .圣约翰练习 提升艺术等级，同时保持基础GPA，无需追求满分成绩。"),
    ("社交型（学生会路线）","Marcus / James / Ben",
     "早期全力堆人气，加入运动/戏剧社团，竞选学生会后申请需要council要求的专业。"),
    ("均衡型（稳健）",      "Jess / Lily / Oliver",
     "没有明显短板，灵活调整方向。前半学期观察其他玩家，后半学期确认目标院校。"),
]
rcols2 = [TW*0.23, TW*0.30, TW*0.47]
story.append(ts([
    [th("路线"), th("推荐角色"), th("策略方向")],
] + [[tdl(r[0]), tdl(r[1]), tdl(r[2])] for r in routes],
colWidths=rcols2))

story.append(Spacer(1, 5*mm))
story.append(HRFlowable(width=TW, thickness=1, color=C_GOLD))
story.append(Spacer(1, 4*mm))
story.append(Paragraph("祝你在圣约翰度过精彩的一年！", sty("_end", fontSize=12, fontName=BOLD,
             textColor=C_NAVY, alignment=TA_CENTER)))
story.append(Paragraph("Good luck, and welcome to St. John's Prep.", sty("_end2", fontSize=10,
             textColor=C_BLUE, alignment=TA_CENTER)))

# ── 页眉页脚 ─────────────────────────────────────────────────────
def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont(BASE, 7.5)
    canvas.setFillColor(colors.HexColor("#888888"))
    if doc.page > 1:
        canvas.drawString(ML, MB * 0.55, "圣约翰预科高中 · 玩家手册")
        canvas.drawRightString(W - MR, MB * 0.55, f"第 {doc.page} 页")
        canvas.setStrokeColor(C_BORDER)
        canvas.setLineWidth(0.4)
        canvas.line(ML, MB * 0.9, W - MR, MB * 0.9)
    canvas.restoreState()

doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
print(f"✅ 手册已生成：{out_path}")

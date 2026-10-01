import io, os, re, json, math, functools, secrets, time, hmac, hashlib, logging, traceback, zipfile
import shutil, socket, ipaddress, urllib.request, threading
from urllib.parse import urlparse
from collections import defaultdict
from datetime import datetime, date as _date, timezone, timedelta

TZ_BEIJING = timezone(timedelta(hours=8))
from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, abort, send_file, g)
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature
import sqlite3

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "rp_archive_secret_key_change_me")
# 部署在 nginx 后面时（贾维斯）设 BEHIND_PROXY=1：按 X-Forwarded-* 还原真实的协议/域名/来访 IP，
# 否则 request.host_url 会是 http://127.0.0.1:5001，结束季度生成的公开存档链接就打不开。
# 直接对外（没有反代）时别开，不然来访者可以自己伪造 X-Forwarded-For
if os.environ.get("BEHIND_PROXY") == "1":
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
# 别的网站不能借玩家/管理员的登录态偷偷提交表单（后台「重置激活码」之类的 POST）
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


# ── 错误日志 ──────────────────────────────────────────────────────────────────
_log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_log_dir, exist_ok=True)
_err_handler = logging.FileHandler(os.path.join(_log_dir, "error.log"), encoding="utf-8")
_err_handler.setLevel(logging.ERROR)
_err_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s]\n%(message)s\n" + "-"*60
))
_logger = logging.getLogger("rp_archive")
_logger.setLevel(logging.ERROR)
_logger.addHandler(_err_handler)

@app.errorhandler(404)
def handle_404(e):
    return render_template("error.html", code=404,
        title="你走丢了",
        lead="这里什么都没有。",
        body="我感应到你偏离了轨迹——这个地址不存在，或者已经从记忆里消失了。别担心，我来把你送回去。"), 404

@app.errorhandler(500)
def handle_500(e):
    _logger.error("500 Internal Server Error\nURL: %s %s\n%s",
                  request.method, request.url, traceback.format_exc())
    return render_template("error.html", code=500,
        title="系统发生了偏折",
        lead="核心出现了一道裂缝。",
        body="某个地方出了问题，我已经记录下这次异常并会着手修复。你现在能做的，是先回到安全的地方。"), 500

@app.template_filter("fromjson")
def _fromjson(s):
    try: return json.loads(s or "{}")
    except Exception: return {}

def _strip_json_str(val):
    """去掉 bot 推来的 JSON string 包装，如 '"12345"' → '12345'。"""
    s = str(val).strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        try:
            decoded = json.loads(s)
            if isinstance(decoded, str):
                return decoded
        except Exception:
            pass
    return s

@app.template_filter("strip_json_str")
def _tpl_strip_json_str(s):
    return _strip_json_str(s or "")

DB_PATH         = os.path.join(os.path.dirname(__file__), "rp_data.db")
SUPERADMIN_PASS = os.environ.get("SUPERADMIN_PASS",
                  os.environ.get("RP_ADMIN_PASSWORD", "pDynLBeLGEjd"))
PLAYERS_PER_PAGE = 50

# 信息收集图片：单张大小上限 / 每用户每季度累计配额上限（结束季度时清空重置）
UNIVERSAL_MAX_ITEMS = 500   # 通用物品库上限（跨季度，货币/物品/互动物品合计）
MAX_SHOWS_PER_TENANT = 10   # 每个租户最多保留的季度数（含已结束的），满了要先删旧的
COLLECT_IMAGE_MAX_BYTES = 3 * 1024 * 1024
COLLECT_IMAGE_USER_QUOTA_BYTES = 30 * 1024 * 1024
COLLECT_IMAGE_DIR = os.path.join(os.path.dirname(__file__), "static", "collected_images")

# ── Command guide blocks ──────────────────────────────────────────────────────
COMMAND_BLOCKS = [
    # ══════════════════════════════
    #  玩家指令
    # ══════════════════════════════
    {"key": "intro", "label": "🌟 入门 — 角色与账号", "category": "player", "lines": [
        "创建新角色 角色名",
        "  例：创建新角色 张三",
        "  注册角色，获得初始档案（性别/年龄/皮相）",
        "",
        "修改名字 新名字   （改名并同步所有数据）",
        "修改性别 男/女",
        "修改年龄 数字",
        "修改皮相 明星名  （2小时冷却）",
        "修改签名 内容     （12小时冷却）",
        "",
        "额外账号 QQ号       绑定小号",
        "额外账号 删除 QQ号  解绑小号",
        "额外账号            查看已有",
        "",
        "玩家名单   查看所有角色及档案",
        "角色卡     查看自己的角色卡（属性/装备/货币）",
        "地点查看   查看可用地点列表",
    ]},
    {"key": "relationship", "label": "🔗 关系线", "category": "player", "lines": [
        "拉线 对方名 关系内容",
        "  向对方发起关系线并记录细节",
        "  例：拉线 张三 两人曾在大学相识",
        "",
        "确认关系线 对方名",
        "  确认对方向你发起的关系线",
        "",
        "撤回关系 对方名 要撤回的内容",
        "  精确匹配撤回自己的细节",
        "",
        "查看关系线          查看所有关系对象",
        "查看关系线 角色名   查看与该角色的完整细节",
    ]},
    {"key": "appointment", "label": "💕 约会与邀约", "category": "player", "lines": [
        "电话 时间 对方名 [标题]",
        "  例：电话 1400-1500 张三",
        "  例：电话 1400-1500 张三/李四 一起聊聊",
        "",
        "私约 时间 地点 对方名[/对方2/...]",
        "  例：私约 1400-1500 咖啡厅 张三",
        "  例：私约 1400-1500 咖啡厅 张三/李四",
        "",
        "申请加入 角色名 时间点",
        "  例：申请加入 张三 14:30",
        "",
        "加入请求       查看收到的加入请求",
        "同意加入 请求编号",
        "拒绝加入 请求编号",
        "",
        "时间线         查看自己的日程安排",
        "",
        "我的待回       查看还没回复的群（超时置顶）、已开场但还没进的群、已结束但还没退的群、今日心动信投递情况",
        "",
        "修改时间线 D1 1400-1500",
        "  在约会群内使用，修改当前约会的时间",
        "",
        "拒绝时间线 群号",
        "  退出约会并通知相关者，取消约会记录",
        "",
        "结束私约       在约会群中结束本场后退群",
    ]},
    {"key": "social", "label": "💬 微信 & 心愿 & 短信", "category": "player", "lines": [
        "微信 对方名   建立长期微信群",
        "",
        "挂心愿 时间 地点 内容",
        "  例：挂心愿 1400-1500 图书馆 想找人聊聊",
        "看心愿          查看所有漂流心愿",
        "摘心愿 编号     例：摘心愿 A1B2C3",
        "撤心愿 [编号]   不带编号→列出自己的心愿",
        "",
        "。悬赏心愿 时间 地点 内容 [悬赏物 数量]",
        "  发布带悬赏的心愿，摘取者可获得奖励",
        "",
        "[署名]短信 收信人 内容",
        "  例：张三短信 李四 你好！",
    ]},
    {"key": "bag", "label": "🎒 背包与道具", "category": "player", "lines": [
        "背包",
        "  查看背包全览（各分类最多3项）",
        "",
        "背包 货币 / 背包 道具 / 背包 物品",
        "  按分类查看背包（支持分页）",
        "",
        "背包 [分类] [页码]",
        "  翻页查看（例：背包 道具 2）",
        "",
        "背包 搜 [关键词]",
        "  搜索物品名称或描述",
        "  例：背包 搜 钥匙",
        "",
        "物品详情 物品码或名称",
        "  查看物品描述、属性效果、商城价格",
        "",
        "抽取 [池子名]",
        "  从抽取池随机获得物品",
        "  例：抽取 / 抽取 普通池",
        "",
        "我的抽取次数 / 抽取次数",
        "  查看今日已用/剩余次数",
        "",
        "我的保底 / 保底进度",
        "  查看保底计数（如有保底机制）",
        "",
        "赠送道具 对方名 物品码 [数量]",
        "  例：赠送道具 张三 AA00 2",
        "",
        "使用 物品码或名称 [参数]",
        "  例：使用 TJ00 张三    （追踪器）",
        "  例：使用 WN00 图书馆  （万能钥匙）",
        "  例：使用 AA00",
        "",
        "特殊使用 望远镜 角色名",
        "  施加后，目标发出信件时自动抄录一份给你",
        "特殊使用 羽毛笔 角色名",
        "  施加后，目标下一封信先发给你修改后再发出",
    ]},
    {"key": "equip", "label": "🛡️ 装备系统", "category": "player", "lines": [
        "。装备 装备名或物品码",
        "  将指定装备穿戴到对应槽位",
        "",
        "。脱装备 槽位",
        "  卸下指定槽位的装备",
        "",
        "。槽位",
        "  查看当前装备槽位及穿戴状态",
    ]},
    {"key": "upgrade", "label": "⬆️ 升级系统", "category": "player", "lines": [
        "。升级",
        "  消耗材料进行角色升级",
        "",
        "。查看升级信息",
        "  查看当前等级及升级所需材料",
        "",
        "升级列表",
        "  查看所有可升级配置（无需句号）",
    ]},
    {"key": "market", "label": "🏪 商城与二手市场", "category": "player", "lines": [
        "商城",
        "  查看当前在售物品及价格",
        "",
        "售卖 物品码 价格 货币名 [数量]",
        "  将背包物品挂上二手市场",
        "  例：售卖 AA00 8 金币 2",
        "",
        "二手市场",
        "  查看所有在售卖单",
        "",
        "二手市场 买 编号",
        "  购买指定卖单（手续费由买方承担）",
        "  例：二手市场 买 0001",
        "",
        "撤销卖单 编号   撤回自己的卖单并退货",
    ]},
    {"key": "gift_shop", "label": "🛒 礼品店", "category": "player", "lines": [
        "礼品店   随机抽一件礼物，解锁入图鉴",
        "",
        "图鉴        查看收藏进度与全服热度排名",
        "图鉴 #编号  查看该礼物完整描述",
        "",
        "送礼 对方名 礼物内容  叙事礼物",
        "  例：送礼 张三 一束花",
        "送礼 对方 #编号   图鉴内礼物可无限送礼",
    ]},
    {"key": "craft", "label": "🧪 合成系统", "category": "player", "lines": [
        "合成列表 / 查看合成",
        "  查看所有可用合成配方",
        "合成列表 关键词",
        "  搜索包含关键词的配方",
        "",
        "合成 产物代码",
        "  执行一次合成",
        "  例：合成 高级丹",
        "",
        "合成 产物代码 数量",
        "  批量合成多次",
        "  例：合成 高级丹 5",
    ]},
    {"key": "rpg_attr", "label": "🎭 RPG 属性", "category": "player", "lines": [
        "我的状态",
        "  查看当前角色的所有属性值",
        "  （属性显示为进度条形式）",
        "",
        "角色:属性++值   （无需句号，直接发送）",
        "  例：张三:体力++10   增加体力10点",
        "角色:货币--值",
        "  例：李四:金币--50   减少金币50枚",
        "全体:属性++值",
        "  例：全体:精力++5    所有角色精力+5",
    ]},
    {"key": "combat", "label": "⚔️ PK 战斗", "category": "player", "lines": [
        "。PK 对方名",
        "  向对方发起 PK 挑战",
        "",
        "。攻击 / 。防守 / 。投降 / 。逃跑",
        "  战斗中的行动指令",
        "",
        "。战况",
        "  查看当前战斗状态与属性",
        "。战况 历史   查看历史战斗记录",
        "。战况 用品   查看战斗可用道具",
    ]},
    {"key": "letter", "label": "✉️ 发送信件（写信综）", "category": "player", "lines": [
        "。发送信件",
        "【收件人】角色名",
        "【内容】信件内容",
        "【日期】日期（选填）",
        "【附件】附加内容（选填）",
        "【署名】落款（选填，默认角色名）",
        "",
        "。信件状态   查看今日发信额度与赏金设置",
        "",
        "。羽毛笔修改          查看待修改信件清单",
        "。羽毛笔修改 序号 新内容  修改后发出",
    ]},
    {"key": "lovemail", "label": "💌 心动信 & 信箱", "category": "player", "lines": [
        "发送心动信",
        "【发送对象】角色名",
        "【内容】想说的话（支持空行）",
        "【署名】自定义昵称（选填）",
        "",
        "。撤回心动信 编号   撤回已投递的信",
        "",
        "查看信箱   查看收到的心动信",
    ]},
    {"key": "forum", "label": "🗨️ 论坛", "category": "player", "lines": [
        "发帖 内容",
        "  例：发帖 今天天气真好",
        "发帖 署名 内容",
        "  例：发帖 张三 今天天气真好",
        "",
        "回复帖子 贴号 内容",
        "  例：回复帖子 A1B2C 同感！",
        "回复帖子 贴号 署名 内容",
        "",
        "查看帖子        查看所有帖子",
        "查看帖子 贴号   查看该帖子及回复",
        "",
        "。点赞 贴号",
        "。点踩 贴号",
        "。点赞楼层 贴号 楼层号",
        "。点踩楼层 贴号 楼层号",
        "",
        "。删除帖子 贴号   删除自己发的帖子",
    ]},
    {"key": "auction", "label": "🔨 拍卖系统", "category": "player", "lines": [
        "查看拍卖",
        "  查看所有进行中的拍卖（合并转发）",
        "",
        "实名出价 价格 编号",
        "  例：实名出价 150 #1",
        "",
        "匿名出价 价格 编号",
        "  例：匿名出价 200 #1",
    ]},
    {"key": "collect", "label": "📋 信息收集 & 写帖进度", "category": "player", "lines": [
        "我提交 项目名: 内容",
        "  例：我提交 问卷: 我选A",
        "查看收集          列出所有项目",
        "查看收集 项目名   查看该项目全部内容",
        "",
        "定时收集 项目名 内容",
        "  参与进行中的定时收集项目",
        "",
        "  （写帖进度自动记录，可在时间线中查看）",
    ]},
    {"key": "alarm", "label": "⏰ 闹钟（加百列）", "category": "player", "lines": [
        "。提醒 时间 内容",
        "  时间格式：X分钟后 / HH:MM / 明天HH:MM / 每天HH:MM / 每周一HH:MM",
        "  例：。提醒 30分钟后 去看消息",
        "  例：。提醒 22:00 该睡觉了",
        "",
        "。我的提醒",
        "  查看所有已设置的提醒",
        "",
        "。删除提醒 编号",
        "  取消指定提醒",
        "",
        "。再提醒我 [X分钟]",
        "  延迟再提醒一次，默认 10 分钟",
        "",
        "。谢谢加百列   向加百列表示感谢（每天一次，提升好感度）",
        "。加百列好感度  查看与加百列的好感度",
        "。加百列图鉴   查看从加百列处获得的礼物",
    ]},
    {"key": "stats", "label": "📊 统计", "category": "player", "lines": [
        "本场统计   查看自己的本场互动数据",
    ]},
    # ══════════════════════════════
    #  管理指令
    # ══════════════════════════════
    {"key": "adm_account", "label": "🔑 管理员账户", "category": "admin", "lines": [
        "。授予管理员 QQ号 密码",
        "  将指定 QQ 设为临时管理员",
        "",
        "。收回管理员 QQ号 密码",
        "  撤销指定 QQ 的管理员身份",
        "",
        "。管理员列表",
        "  查看当前所有管理员",
        "",
        "。清空管理员 密码",
        "  清空所有平台的管理员",
        "",
        "。更改密令 新密码",
        "  更改管理员授权密码（至少4位）",
    ]},
    {"key": "adm_perms", "label": "🚫 功能权限管理", "category": "admin", "lines": [
        "。功能权限 角色名 功能 开启/关闭",
        "  功能可选：礼物 / 发起邀约 / 寄信 / 心愿 / 心动信",
        "            论坛 / 抽取 / 全部",
        "  例：。功能权限 张三 论坛 关闭",
        "  例：。功能权限 张三 全部 关闭  （一键阻断）",
        "",
        "。查看功能权限",
        "  查看所有被设置过权限的角色",
        "",
        "。时间锁定",
        "  进入时间锁定设置面板",
        "",
        "。查看锁定 角色名",
        "  查看指定角色的时间段锁定情况",
        "",
        "。查看他人时间线 角色名",
        "  查看指定角色的全部时间安排",
    ]},
    {"key": "adm_settings", "label": "⚙️ 系统设置", "category": "admin", "lines": [
        "。设置 基础设置 / 功能开关 / 互动参数 / 信件与礼品 / 公告设置 / DLC",
        "  进入对应模块的设置面板；改完后机器人会提醒回复「确认」同步到网页端",
        "",
        "。设置天数 D1 / D2 / D3...",
        "  切换当前游戏天数",
        "",
        "。开启自动天数 / 。关闭自动天数",
        "  控制每天 23:59 自动推进天数",
        "",
        "。设置信箱上限 D0:3 D1:5...",
        "  设置各天数的心动信每日上限",
        "  例：。设置信箱上限 默认 3",
        "",
        "。自动拉取 开启/关闭/状态/立即检查/通知开启/通知关闭",
        "  网页端改完保存后，机器人每 2 分钟自动拉取（默认开启），并往后台群发合并转发说明改了什么",
        "",
        "。推送全部",
        "  手动把机器人里的配置推送到网页端（日常不用发：「。设置」确认后和钥匙/技能/拍卖变化都会自动同步）；物品和池子以网页端为准，默认不推送，加「含物品池子」才一起推",
        "",
        "。拉取全部",
        "  立即把网页端所有数据拉取到机器人（配置+注册表+模版+池子+拍卖队列）；日常不用发，自动拉取会做",
        "",
        "。开始季度 [季名]",
        "  开始网页「季度日历」里预订的季度（季度只能在网页上创建；临时开季就订一个今天开始的）。",
        "  不带季名按今天日期自动选；上季数据没清会提示回复「确认」自动清空；天数占位 D100，档期开始日自动切 D0",
        "",
        "。清空季度数据 [确认]",
        "  扫描各群确认无玩家残留后清空上季数据；一般不用单独发，开始季度会提示",
        "",
        "。修改档期 MMDD-MMDD [补戏MMDD]",
        "  修改当前季度的档期",
        "",
        "。结束季度",
        "  结束当前活跃季度（若开启季末报告则自动群发）",
        "",
        "。季末报告 开启/关闭/状态",
        "  控制结束季度时是否向玩家个人群发送互动报告",
        "  ⚠️ 开启后请确保 bot 届时仍在各玩家个人群内",
        "",
        "。master jsclear 插件名字",
        "  重置插件存储（替代原强硬初始化）",
    ]},
    {"key": "adm_data", "label": "📊 数据统计 & 监控", "category": "admin", "lines": [
        "查看全员统计（无前缀）",
        "  查看所有玩家数据排名（合并转发）",
        "",
        "查看计时器（无前缀）",
        "  查看所有活跃群的倒计时状态",
        "",
        "查看进行中（无前缀）",
        "  查看当前所有进行中的约会",
        "",
        "提醒超时（无前缀）",
        "  向超时未结束的约会群发送提醒",
        "",
        "关系线统计（无前缀）",
        "  查看所有角色的关系线数量统计",
        "",
        "。信箱统计",
        "  查看心动信投递总量及分类统计",
        "",
        "。统一送心动信",
        "  统一派送所有已投递的心动信",
        "",
        "。同步名片 公告/戏群/水群",
        "  将群内角色名片同步到指定群",
        "",
        "。随机分组 [数字] [bg]",
        "  将在场角色随机分成若干组",
        "",
        "。删除时间线 天数 时间 角色名",
        "  精确删除指定角色的某条时间线记录",
        "",
        "。角色档案 角色名",
        "  查看指定角色的完整档案（管理员视角）",
    ]},
    {"key": "adm_groups", "label": "📅 群号 & 邀约管理", "category": "admin", "lines": [
        "。开启群号组 组名",
        "  新建并激活一个群号组",
        "",
        "。关闭群号组 组名",
        "  暂停某个群号组（数据保留，不再生效）",
        "",
        "。添加群号 组名 群号",
        "  将群号添加至指定群号组",
        "",
        "。移除群号 组名 群号",
        "  从指定群号组中移除群号",
        "",
        "。查看群号 [组名]",
        "  不带组名列出所有组；带组名显示组内群号",
        "",
        "。设置邀约时间 时间段",
        "  限制玩家可发起邀约的时间范围",
        "",
        "。清空邀约时间",
        "  清除邀约时间限制",
        "",
        "。驱逐 QQ号",
        "  将指定 QQ 踢出当前群",
        "",
        "。查看微信群",
        "  查看所有活跃微信群列表",
        "",
        "。更新未退群",
        "  检测并更新未退出的已结束小群",
        "",
        "。查看到期群",
        "  查看所有已超过有效期的群组",
        "",
        "。场次状态",
        "  合并转发查看所有活跃群的当前写帖进度与结戏奖励条件达成情况",
        "  （群过多时自动分批，每批最多 20 个）",
        "",
        "。调整场次 群号 角色名 字数偏移 [段数偏移]",
        "  手动修正指定群某角色的字数/段数，同步更新几v几进度",
        "  示例：。调整场次 12345 张三 +500 +2",
        "",
        "发起官约（无前缀）",
        "  以系统身份发起官方约会",
    ]},
    {"key": "adm_announce", "label": "📢 群管功能", "category": "admin", "lines": [
        "。群公告发布 内容",
        "  在当前群发布公告",
        "",
        "。群公告发布 权限切换",
        "  切换公告发布权限（管理员/所有人）",
        "",
        "。群头衔 内容",
        "  更改自己的群头衔",
        "",
        "。群头衔 @某人 内容",
        "  代改他人群头衔",
        "",
        "。群头衔 权限切换",
        "  切换头衔修改权限（管理员/所有人）",
        "",
        "。设置加百列群名 群名",
        "  修改机器人在群内的昵称",
    ]},
    {"key": "adm_items", "label": "🎲 物品管理", "category": "admin", "lines": [
        "【注册】",
        "物品、互动物品统一在网页端「资料库」添加（支持批量粘贴一大段，一行一件），保存后机器人 2 分钟内自动同步",
        "货币同样在网页端注册（批量粘贴时写 银币【货币】）",
        "。删除物品 物品码",
        "  删除已注册的物品",
        "。物品列表 [物品|货币|预设|全部]",
        "",
        "【商城】",
        "。上架商城 物品码*价格货币名",
        "  例：。上架商城 AA00*10金币",
        "。商城下架 物品码",
        "",
        "【抽取池】",
        "💡 池子管理（新建/上架物品/开启关闭/保底设置）请前往 RP 管理面板 → 抽取池",
        "。抽取 [池子名]   从抽取池随机获得物品",
        "。抽取次数        查看当前可用抽取次数",
        "。查看池子 池子名 查看该池所有物品及库存",
        "。我的保底        查看保底累计进度",
        "。发放抽取 角色名 N              总额外次数",
        "。发放抽取 角色名 池子名 N       特定池额外次数",
        "",
        "【背包操作】",
        "。调整 角色名 物品码 +N/-N",
        "  例：。调整 张三 AA00 +3",
        "。批量发放 物品码 +N 角色名1 角色名2...",
        "  一次性给多个角色发放物品",
        "。查看背包 角色名   查看指定角色的背包",
        "",
        "【二手市场】",
        "。二手设定 开启/关闭",
        "。二手设定 手续费:N  （2-5，默认3）",
        "",
        "【记录】",
        "。背包 记录 [N]   查看今日最近N条物品使用记录",
    ]},
    {"key": "adm_rpg", "label": "🧬 RPG 属性 & 合成", "category": "admin", "lines": [
        "【属性注册】",
        "属性、装备、槽位、合成配方统一在网页端「资料库」注册，每一块下面都有「批量粘贴录入」，",
        "  粘贴一大段按格式一键录入；保存后机器人 2 分钟内自动同步（群里不再支持注册）",
        "。设置属性 角色名 属性名 值",
        "  直接设置角色某属性为指定值",
        "",
        "【属性修改（无需句号）】",
        "角色:属性++N / 角色:属性--N",
        "  例：张三:体力++10",
        "全体:属性++N / 全体:属性--N",
        "  例：全体:精力++5   所有角色增加",
        "",
        "【合成】",
        "合成配方在网页端「资料库 → 合成配方」配置（支持批量粘贴）",
        "  格式：产物*描述*材料1:数量,材料2:数量[*限制条件[*成功率]]",
        "  例：高级丹*升级丹药*初级丹:3,金币:100*attr:体力:50*80",
        "",
        "【装备与升级】",
        "装备、槽位同样在网页端「资料库」注册（支持批量粘贴）",
        "。上传升级等级 等级配置",
        "  上传升级等级配置表",
        "。查看升级配置",
        "  查看当前升级配置详情",
        "。升级列表",
        "  查看所有升级等级列表",
    ]},
    {"key": "adm_bonus", "label": "🎁 结戏加成", "category": "admin", "lines": [
        "。结戏加成 模版列表",
        "。结戏加成 可用参数",
        "。结戏加成 查看 模版名",
        "。结戏加成 新建 模版名",
        "。结戏加成 新块 模版名 and/or",
        "。结戏加成 添加条件 模版名 参数 运算符 数值",
        "。结戏加成 添加奖励 模版名 目标 数量",
        "。结戏加成 新建概率池 模版名",
        "。结戏加成 添加池奖励 模版名 目标 数量 权重",
        "。结戏加成 删除池奖励 模版名 编号",
        "。结戏加成 删除块 模版名 块编号",
        "。结戏加成 开启/关闭 模版名",
        "。结戏加成 删除模版 模版名",
    ]},
    {"key": "adm_giftshop", "label": "🛒 礼品店管理", "category": "admin", "lines": [
        "礼品店统一在网页端「礼品店管理」配置（编号、名称、描述），保存后机器人 2 分钟内自动同步",
        "玩家用「送礼 对方名 #编号」引用",
    ]},
    {"key": "adm_relationship", "label": "🔗 关系线管理", "category": "admin", "lines": [
        "。设置强制关系线 角色A 角色B 描述",
        "  强制设定两人关系（系统发起，不占名额）",
        "  例：。设置强制关系线 张三 李四 青梅竹马",
        "",
        "。删除关系线 角色A 角色B",
        "  删除两人之间的关系线",
        "",
        "。清空关系线 MMDD",
        "  清空当前平台全部关系线（需输入当日日期码，如0526）",
    ]},
    {"key": "adm_lovemail", "label": "💌 心动信管理", "category": "admin", "lines": [
        "。统一送心动信",
        "  统一派送所有投递池中的心动信",
        "",
        "。信箱统计",
        "  查看心动信投递总量及分类统计",
        "",
        "。设置信箱上限 D0:3 D1:5...",
        "  设置各天数的每日投稿上限",
        "  例：。设置信箱上限 默认 3",
    ]},
    {"key": "adm_auction", "label": "🔨 拍卖系统管理", "category": "admin", "lines": [
        "。添加拍卖物品 物品码或名称%起拍价%最低加价%时长(h)[%失效时长(h)]",
        "  批量用$分隔多件，最多同时10件",
        "  例：。添加拍卖物品 魔法棒%100%10%24",
        "",
        "。删除拍卖物品 #编号",
        "",
        "。结算拍卖 #编号",
        "  手动结算指定拍卖（无需到期）",
        "",
        "（拍卖队列会随网页端保存自动同步；拍卖快照也会自动同步到网页）",
    ]},
    {"key": "adm_collect", "label": "📋 定时收集管理", "category": "admin", "lines": [
        "。创建定时收集 时间 项目名",
        "  例：。创建定时收集 22:00 晚安问卷",
        "",
        "。关闭定时收集 项目名",
        "  停止该项目的定时收集",
        "",
        "。查看定时收集 [项目名]",
        "  不带名称列出所有项目；带名称查看详情",
    ]},
    {"key": "adm_role", "label": "👤 角色管理", "category": "admin", "lines": [
        "。清除玩家 角色名",
        "  删除该角色的注册数据",
        "",
        "。设为npc 角色名",
        "  将指定角色标记为 NPC",
        "",
        "。创建NPC 角色名",
        "  直接创建一个 NPC 角色（无需玩家绑定）",
        "",
        "。随机分组 [数字] [bg]",
        "  将在场角色随机分成若干组",
    ]},
    {"key": "adm_combat", "label": "⚔️ 攻防系统管理", "category": "admin", "lines": [
        "。攻防 设置 ...",
        "  进入攻防系统配置面板",
        "",
        "。攻防 添加人员 角色名",
        "  将角色加入攻防系统",
        "",
        "。攻防 添加技能 技能名 ...",
        "  注册可用技能",
        "",
        "。攻防 一键初始化",
        "  重置攻防系统数据",
    ]},
]

# ── Config schema ────────────────────────────────────────────────────────────
CONFIG_SCHEMA = [
    {"section": "群组 ID", "fields": [
        {"key": "item_pool_mode",        "label": "道具池模式",  "type": "select",  "default": "自由池", "options": ["自由池", "抽取池"]},
        {"key": "adminAnnounceGroupId",  "label": "公告群",     "type": "text",    "default": "", "note": "群号，留空不广播"},
        {"key": "song_group_id",         "label": "戏群（兼作拍卖展示群）", "type": "text",    "default": ""},
        {"key": "background_group_id",   "label": "后台群",     "type": "text",    "default": ""},
        {"key": "water_group_id",        "label": "水群",       "type": "text",    "default": ""},
        {"key": "announceFrequency",     "label": "公告触发频率","type": "number",  "default": "5", "note": "每 N 条互动触发一次公告广播"},
        {"key": "drop_hide_receiver",    "label": "掉落/曝光隐藏收件人", "type": "bool", "default": "false", "note": "开启后礼物掉落/短信公开/心动信曝光的播报中收件人显示为「某人」"},
    ]},
    {"section": "复盘群（⚠️ 通常不要动，仅紧急情况调整）", "fields": [
        {"key": "require_fupan_before_end", "label": "强制转发复盘", "type": "bool",    "default": "false", "note": "开启后结戏前必须先转发复盘，否则无法结束私约"},
        {"key": "fupan_routing_enabled",    "label": "复盘群分流",   "type": "bool",    "default": "false", "note": "启用后复盘消息按天数路由到对应群"},
        {"key": "fupan_routing_groups",     "label": "分流群配置",   "type": "routing", "default": "",      "note": "格式：D1:群号 D2:群号"},
    ]},
    {"section": "功能开关", "json_parent": "global_feature_toggle", "fields": [
        {"key": "enable_general_gift",        "label": "普通礼物",          "type": "bool", "default": "true"},
        {"key": "enable_general_appointment", "label": "普通邀约",          "type": "bool", "default": "true"},
        {"key": "enable_chaos_letter",        "label": "短信",              "type": "bool", "default": "true"},
        {"key": "enable_wish_system",         "label": "心愿系统",          "type": "bool", "default": "true"},
        {"key": "enable_lovemail",            "label": "心动信",            "type": "bool", "default": "false"},
        {"key": "enable_wechat",              "label": "微信",              "type": "bool", "default": "false"},
        {"key": "enable_direct_letter",       "label": "发送信件（写信综）", "type": "bool", "default": "false"},
        {"key": "dlc_sighting",              "label": "目击报告DLC",       "type": "bool", "default": "false"},
        {"key": "dlc_fupan",                 "label": "复盘群DLC",         "type": "bool", "default": "false"},
        {"key": "dlc_auction",               "label": "拍卖DLC",           "type": "bool", "default": "false"},
        {"key": "dlc_attack",                "label": "攻防DLC",           "type": "bool", "default": "false"},
        {"key": "dlc_forum",                 "label": "论坛DLC",           "type": "bool", "default": "false"},
        {"key": "dlc_auto_day",              "label": "自动天数DLC",       "type": "bool", "default": "false"},
        {"key": "dlc_stakeout",              "label": "踩点DLC",            "type": "bool", "default": "false"},
        {"key": "dlc_battle_appt",           "label": "战斗邀约DLC",        "type": "bool", "default": "false"},
        {"key": "dlc_trade",                 "label": "议价交易DLC",        "type": "bool", "default": "false"},
    ]},
    {"section": "邀约", "fields": [
        {"key": "enable_join_existing_appointment", "label": "允许加入已有私约",        "type": "bool",   "default": "false"},
        {"key": "group_expire_hours",               "label": "小群过期（小时）",        "type": "number", "default": "48"},
        {"key": "rest_hours",                       "label": "休息时段（不计弧长）",    "type": "text",   "default": "", "note": "格式 HHMM-HHMM，如 0200-0800，留空不限制"},
        {"key": "appointment_coin_cost",            "label": "私约写信币费用",          "type": "number", "default": "0", "note": "发起私约/电话消耗的写信币数（0=免费）"},
        {"key": "idle_group_name",                  "label": "备用群名",                "type": "text",   "default": "备用", "note": "群结束后修改成的群名，默认为「备用」"},
        {"key": "force_end_grant_reward",           "label": "强结发放奖励",            "type": "bool",   "default": "false", "note": "开启后「强结私约」「一键强结」也会按正常结戏规则发放奖励，默认关闭（不发放）"},
    ]},
    {"section": "邀约时长（分钟）", "json_parent": "appointment_duration_config", "fields": [
        {"key": "phone",    "label": "电话门槛", "type": "number", "default": "29"},
        {"key": "private",  "label": "私密门槛", "type": "number", "default": "59"},
        {"key": "stakeout", "label": "踩点门槛", "type": "number", "default": "59"},
    ]},
    {"section": "踩点", "fields": [
        {"key": "stakeout_allow_solo", "label": "允许单人踩点", "type": "bool", "default": "true",
         "note": "默认开启，玩家可发起无伴随的踩点（不填对方角色名）；目击时显示「独自」。关闭后踩点必须指定陪伴角色"},
    ]},
    {"section": "寄信", "fields": [
        {"key": "mailCooldown",             "label": "寄信冷却（分钟）", "type": "number", "default": "60"},
        {"key": "allow_custom_letter_sign", "label": "寄信自定义名字",  "type": "bool",   "default": "false"},
        {"key": "letter_public_send",       "label": "寄信公开发送",    "type": "bool",   "default": "false"},
    ]},
    {"section": "礼物", "fields": [
        {"key": "giftCooldown",             "label": "送礼冷却（分钟）",  "type": "number", "default": "30"},
        {"key": "gift_public_send",         "label": "礼物公开发送",      "type": "bool",   "default": "false"},
        {"key": "giftPublicChance",         "label": "礼物公开概率（%）", "type": "number", "default": "50", "min": 0, "max": 100},
        {"key": "giftDailyLimit",           "label": "每日礼物上限",      "type": "number", "default": "100"},
        {"key": "shop_refresh_hours",       "label": "礼品店刷新（小时）","type": "number", "default": "24"},
        {"key": "allow_custom_gift_sign",      "label": "送礼自定义名字",      "type": "bool",   "default": "false"},
    ]},
    {"section": "心动信", "fields": [
        {"key": "lovemail_default_limit",  "label": "每日上限（默认）",  "type": "number",  "default": "3", "note": "无按天配置时的兜底封数"},
        {"key": "lovemail_day_limits",     "label": "按天封数上限",      "type": "routing", "default": "",  "note": "格式：D1:封数 D2:封数，留空则全部用默认值"},
        {"key": "lovemail_delivery_time",  "label": "送达时间",          "type": "text",    "default": "22:00"},
        {"key": "lovemail_expose",         "label": "曝光",              "type": "bool",    "default": "false"},
        {"key": "lovemail_expose_chance",  "label": "曝光概率（%）",     "type": "number",  "default": "10", "min": 0, "max": 100},
    ]},
    {"section": "发送信件", "fields": [
        {"key": "direct_letter_daily_limit", "label": "每日上限",       "type": "number", "default": "5"},
        {"key": "direct_letter_cooldown",    "label": "发信冷却（分钟）","type": "number", "default": "0"},
        {"key": "direct_letter_min_chars",   "label": "最低字数",       "type": "number", "default": "0"},
        {"key": "direct_letter_reward",      "label": "写信币赏金",     "type": "number", "default": "0"},
    ]},
    {"section": "心愿系统", "fields": [
        {"key": "wish_public_send",      "label": "心愿公开提醒",          "type": "bool",   "default": "true"},
        {"key": "wish_bounty_enabled",   "label": "悬赏功能",              "type": "bool",   "default": "true"},
        {"key": "wish_max_concurrent",   "label": "最大同时心愿数",         "type": "number", "default": "3"},
        {"key": "wish_daily_post_limit", "label": "每日发布上限（0=不限）", "type": "number", "default": "0"},
        {"key": "wish_daily_pick_limit", "label": "每日接取上限（0=不限）", "type": "number", "default": "0"},
        {"key": "wish_coin_cost",        "label": "心愿写信币费用",         "type": "number", "default": "0", "note": "挂心愿消耗的写信币数（0=免费）"},
    ]},
    {"section": "关系系统", "fields": [
        {"key": "relationship_system_enabled", "label": "关系系统",           "type": "bool",   "default": "false"},
        {"key": "max_relationships_per_user",  "label": "每人最大关系数",     "type": "number", "default": "5"},
        {"key": "max_detail_chars",            "label": "关系细节单条上限字数","type": "number", "default": "500"},
        {"key": "max_detail_count",            "label": "关系细节段数上限",    "type": "number", "default": "20"},
        {"key": "max_rel_total_chars",         "label": "关系细节总字数上限",  "type": "number", "default": "3000"},
        {"key": "forward_split_threshold",     "label": "关系细节转发拆分阈值","type": "number", "default": "4000"},
    ]},
    {"section": "论坛", "fields": [
        # 键名须与机器人读取的 forum_max_length 一致（原先写成 forumMaxLength，机器人读不到）。
        # opt_in：网页上没明确设置过时不下发，以免「拉取全部」用默认值盖掉 QQ 里设过的值
        {"key": "forum_max_length", "label": "帖子/回复字数上限", "type": "number", "default": "500", "opt_in": True,
         "note": "网页上没设置过时，以 QQ「设置 基础设置」里的值为准"},
    ]},
    {"section": "目击系统", "json_parent": "sighting_system_config", "fields": [
        {"key": "enabled",                "label": "启用目击",                    "type": "bool",   "default": "false"},
        {"key": "send_to_all",            "label": "双向通知",                    "type": "bool",   "default": "true"},
        {"key": "max_reports_per_day",    "label": "每日最大目击数",              "type": "number", "default": "5"},
        {"key": "include_ended_meetings", "label": "包含已结束场次",              "type": "bool",   "default": "false"},
        {"key": "time_overlap_threshold", "label": "时间重叠阈值（0~1）",        "type": "number", "default": "0.3", "note": "时间重叠达到此比例才有资格触发目击，如 0.3 = 重叠30%"},
        {"key": "trigger_chance",         "label": "撞见触发概率（%）",          "type": "number", "default": "50",  "min": 0, "max": 100, "note": "满足重叠条件后实际发出目击报告的概率"},
    ]},
    {"section": "场所系统", "json_parent": "place_system_config", "fields": [
        {"key": "enabled",                "label": "启用场所系统", "type": "bool", "default": "false"},
        {"key": "require_key_by_default", "label": "默认需要钥匙", "type": "bool", "default": "false"},
    ]},
    {"section": "私人房间", "fields": [
        {"key": "allow_private_rooms",    "label": "允许私人房间", "type": "bool",   "default": "true"},
    ]},
    {"section": "短信效果配置（% · 0=关闭）", "json_parent": "chaos_letter_config", "fields": [
        {"key": "misdelivery",       "label": "误送",          "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "blackoutText",      "label": "黑化文字",      "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "loseContent",       "label": "内容丢失",      "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "antonymReplace",    "label": "词语替换",      "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "reverseOrder",      "label": "逆序",          "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "mistakenSignature", "label": "署名错乱",      "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "tornPage",          "label": "残页",          "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "dailyLimit",        "label": "每日上限",          "type": "number", "default": "5"},
        {"key": "publicChance",      "label": "播报概率（%）",     "type": "number", "default": "50", "min": 0, "max": 100},
        {"key": "publicShowEffect",  "label": "公开时显示扰乱效果","type": "bool",   "default": "false"},
        {"key": "giftLost",          "label": "礼物丢失（%）",     "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "giftMisdelivery",   "label": "礼物误送（%）",     "type": "number", "default": "0",  "min": 0, "max": 100},
    ]},
    {"section": "道具", "fields": [
        {"key": "item_tracker_success_rate",   "label": "追踪器成功率（%）",  "type": "number", "default": "70", "min": 0, "max": 100},
        {"key": "item_tracker_show_partner",   "label": "追踪器显示伙伴",    "type": "bool",   "default": "true"},
        {"key": "item_tracker_time_restrict",  "label": "追踪器时间限制",    "type": "bool",   "default": "true"},
        {"key": "apply_item_notification",     "label": "施加道具提醒",      "type": "bool",   "default": "true"},
        {"key": "apply_item_expose_rate",      "label": "施加暴露概率（%）", "type": "number", "default": "0", "min": 0, "max": 100},
        {"key": "apply_item_hours",            "label": "施加可用时段",      "type": "text",   "default": ""},
        {"key": "shop_gift_catalog_on_receive","label": "收到即入图鉴",      "type": "bool",   "default": "false"},
    ]},
    {"section": "拍卖", "fields": [
        {"key": "auction_allow_anon",      "label": "允许匿名出价",   "type": "bool", "default": "true"},
        {"key": "auction_broadcast",       "label": "出价播报",       "type": "bool", "default": "true"},
        {"key": "auction_show_top_bidder", "label": "展示最高出价者", "type": "bool", "default": "true"},
        {"key": "auction_currency",        "label": "拍卖货币",       "type": "text", "default": "金币"},
    ]},
    {"section": "监听参数", "json_parent": "monitor_settings", "fields": [
        {"key": "enabled",                "label": "启用监听系统",       "type": "bool",   "default": "true"},
        {"key": "auto_monitor_all_groups","label": "自动监控所有群组",   "type": "bool",   "default": "true"},
        {"key": "min_words_phone",        "label": "电话最低字数",       "type": "number", "default": "20"},
        {"key": "min_words_private",      "label": "私密最低字数",       "type": "number", "default": "150"},
        {"key": "min_words_wish",         "label": "心愿最低字数",       "type": "number", "default": "150"},
        {"key": "min_words_official",     "label": "官约最低字数",       "type": "number", "default": "150"},
        {"key": "timeout_phone",          "label": "电话超时（小时）",   "type": "number", "default": "1"},
        {"key": "timeout_private",        "label": "私密超时（小时）",   "type": "number", "default": "3"},
        {"key": "timeout_wish",           "label": "心愿超时（小时）",   "type": "number", "default": "3"},
        {"key": "timeout_official",       "label": "官约超时（小时）",   "type": "number", "default": "3"},
    ]},
    {"section": "公开链接", "fields": [
        {"key": "public_show_sms",      "label": "公开短信",   "type": "bool", "default": "true"},
        {"key": "public_show_gift",     "label": "公开礼物",   "type": "bool", "default": "true"},
        {"key": "public_show_lovemail", "label": "公开心动信", "type": "bool", "default": "true"},
        {"key": "public_show_letter",   "label": "公开信件",   "type": "bool", "default": "false"},
    ]},
    {"section": "类型显示别名", "json_parent": "custom_type_labels", "fields": [
        # "私密"改名/加资源已经迁移到下面的「私约名称管理」，这里不再展示这个输入框（hidden=True）——
        # 但字段定义本身要留着：assemble_bot_config 是按 CONFIG_SCHEMA 里声明的字段逐个拼 JSON 的，
        # 如果直接删掉这条，"拉取全部"给任何还在用旧版机器人插件（没迁移到 private_resources）的
        # 群拼出来的 custom_type_labels 就会永远丢失"私密"这个键，把他们已经设置好的自定义名字冲掉。
        # 保留字段只是不再让人从这个格子编辑，历史值该怎么传还怎么传。
        {"key": "私密", "label": "私约别名（旧，见下方私约名称管理）", "type": "text", "default": "", "hidden": True},
        {"key": "电话", "label": "电话别名", "type": "text", "default": "", "note": "留空=默认「电话」"},
        {"key": "官约", "label": "官约别名", "type": "text", "default": "", "note": "留空=默认「官约」"},
        {"key": "微信", "label": "微信别名", "type": "text", "default": "", "note": "留空=默认「微信」"},
        {"key": "心愿", "label": "心愿别名", "type": "text", "default": "", "note": "留空=默认「心愿」"},
    ]},
    # 电话/私约/官约/官电/踩点除了原来的一行式空格分参数，也支持多行「标签：值」表单（顺序随意），
    # 例：【电话】\n受邀人：张三\n时间：1400-1500——两种写法机器人始终都认，不受下面的展示开关影响。
    # 这里改的是：①标签文字 ②「格式电话/私约/踩点」提示里展示哪种示例（_display，仅这三类有）。
    # 机器人「拉取全部」后生效；key 用 "类型_字段" 复合键，跟机器人存储里 appointment_form_labels
    # 的扁平结构一一对应，别改成嵌套。
    {"section": "邀约表单标签", "json_parent": "appointment_form_labels", "fields": [
        {"key": "电话_display", "label": "电话·「格式电话」展示", "type": "select", "default": "一行式",
         "options": ["一行式", "表单式"], "note": "只影响「格式电话」显示哪种示例；两种写法机器人始终都认"},
        {"key": "私密_display", "label": "私约·「格式私约」展示", "type": "select", "default": "一行式",
         "options": ["一行式", "表单式"], "note": "只影响「格式私约」显示哪种示例；两种写法机器人始终都认"},
        {"key": "踩点_display", "label": "踩点·「格式踩点」展示", "type": "select", "default": "一行式",
         "options": ["一行式", "表单式"], "note": "只影响「格式踩点」显示哪种示例；两种写法机器人始终都认"},
        {"key": "电话_time",  "label": "电话·时间",   "type": "text", "default": "", "note": "留空=默认「时间」"},
        {"key": "电话_names", "label": "电话·受邀人", "type": "text", "default": "", "note": "留空=默认「受邀人」"},
        {"key": "电话_title", "label": "电话·标题",   "type": "text", "default": "", "note": "留空=默认「标题」"},
        {"key": "私密_time",  "label": "私约·时间",   "type": "text", "default": "", "note": "留空=默认「时间」"},
        {"key": "私密_place", "label": "私约·地点",   "type": "text", "default": "", "note": "留空=默认「地点」"},
        {"key": "私密_names", "label": "私约·对象",   "type": "text", "default": "", "note": "留空=默认「对象」；约战/自定义私约别名/短信别名共用这一组标签"},
        {"key": "踩点_time",  "label": "踩点·时间",   "type": "text", "default": "", "note": "留空=默认「时间」"},
        {"key": "踩点_place", "label": "踩点·地点",   "type": "text", "default": "", "note": "留空=默认「地点」"},
        {"key": "踩点_names", "label": "踩点·陪同",   "type": "text", "default": "", "note": "留空=默认「陪同」"},
        {"key": "官约_day",   "label": "官约·日期",   "type": "text", "default": "", "note": "留空=默认「日期」"},
        {"key": "官约_time",  "label": "官约·时间",   "type": "text", "default": "", "note": "留空=默认「时间」"},
        {"key": "官约_place", "label": "官约·地点",   "type": "text", "default": "", "note": "留空=默认「地点」"},
        {"key": "官约_names", "label": "官约·参与者", "type": "text", "default": "", "note": "留空=默认「参与者」"},
        {"key": "官电_day",   "label": "官电·日期",   "type": "text", "default": "", "note": "留空=默认「日期」"},
        {"key": "官电_time",  "label": "官电·时间",   "type": "text", "default": "", "note": "留空=默认「时间」"},
        {"key": "官电_names", "label": "官电·参与者", "type": "text", "default": "", "note": "留空=默认「参与者」"},
    ]},
    {"section": "呼叫管理组", "fields": [
        {"key": "call_admin_daily_limit", "label": "每人每天可呼叫次数", "type": "number", "default": "10",
         "note": "玩家发「呼叫管理组 内容」会转到后台群；0 = 关闭这个功能"},
        {"key": "call_admin_cooldown_min", "label": "两次呼叫最少间隔（分钟）", "type": "number", "default": "5",
         "note": "同一个人两次呼叫之间至少隔多久，防止刷屏"},
    ]},
    {"section": "季末报告", "fields": [
        {"key": "end_season_report_enabled", "label": "季末互动报告", "type": "bool", "default": "false",
         "note": "开启后结束季度时自动向每位玩家个人群发送互动报告，请确保 bot 届时仍在各个人群内"},
    ]},
]

def _cfg_db_key(section, field_key):
    jp = section.get("json_parent")
    return f"{jp}__{field_key}" if jp else field_key

def get_flat_config(db, show_id):
    rows = db.execute("SELECT key, value FROM site_config WHERE show_id=?", (show_id,)).fetchall()
    return {r["key"]: r["value"] for r in rows}

def assemble_bot_config(flat):
    result = {}
    for sec in CONFIG_SCHEMA:
        jp = sec.get("json_parent")
        if jp:
            obj = {}
            for f in sec["fields"]:
                raw = flat.get(_cfg_db_key(sec, f["key"]), str(f["default"]))
                if f["type"] == "bool":
                    obj[f["key"]] = raw in ("true", "1", "True")
                elif f["type"] == "number":
                    try:
                        obj[f["key"]] = float(raw) if "." in str(raw) else int(raw)
                    except (ValueError, TypeError):
                        obj[f["key"]] = f["default"]
                else:
                    obj[f["key"]] = raw
            # timeout fields in monitor_settings are stored as hours in UI, bot expects ms
            if jp == "monitor_settings":
                for tkey in ("timeout_phone", "timeout_private", "timeout_wish", "timeout_official"):
                    if tkey in obj and isinstance(obj[tkey], (int, float)):
                        obj[tkey] = int(obj[tkey] * 3_600_000)
            result[jp] = json.dumps(obj, ensure_ascii=False)
        else:
            for f in sec["fields"]:
                if f.get("opt_in") and f["key"] not in flat:
                    continue
                result[f["key"]] = flat.get(f["key"], str(f["default"]))
    # 透传 blob 键（机器人以 JSON 字符串形式存储，原样透传）
    # place_keys / battle_attrs / player_skills 是玩家数据，以机器人为准，不下发：
    # 网页上那份是上次「推送全部」的旧快照，下发会把玩家新拿的钥匙、新学的技能、战斗属性回滚
    for blob_key in ("item_registry", "rpg_attr_defs", "sys_attr_presets",
                     "end_game_bonus_templates", "end_game_draw_config",
                     "custom_message_templates", "preset_gifts",
                     "private_appointment_aliases", "sms_aliases", "gift_aliases",
                     "private_resources",
                     "equipment_registry", "equipment_slots", "equipment_slot_names",
                     "craft_recipes",
                     "trade_whitelist",
                     "available_places",
                     "skill_defs",
                     "rpg_point_groups",
                     "attack_defense_config",
                     "shop_listings", "market_config"):
        val = flat.get(blob_key)
        if val:
            result[blob_key] = val
    # 时间调度：将功能时间窗口转换为机器人使用的 allowed_appointment_times 格式
    ts_fw_raw = flat.get("ts_feature_windows")
    if ts_fw_raw:
        try:
            fw_list = json.loads(ts_fw_raw)
            appt_entry = next((fw for fw in fw_list if fw.get("feature") == "enable_general_appointment"), None)
            if appt_entry:
                s = int(appt_entry.get("start", 0))
                e = int(appt_entry.get("end", 24))
                result["allowed_appointment_times"] = json.dumps(
                    [f"{s:02d}:00-{e:02d}:00"], ensure_ascii=False
                )
            else:
                result["allowed_appointment_times"] = "[]"
        except Exception:
            pass
    # 透传时间调度原始 blob 键（供机器人扩展使用）
    for ts_key in ("ts_blocked_by_day", "ts_allowed_durations", "ts_feature_windows", "ts_strict_hour_match", "ts_reality_slot_size", "ts_slot_mode"):
        val = flat.get(ts_key)
        if val:
            result[ts_key] = val
    return result


# ── DB ───────────────────────────────────────────────────────────────────────

def get_db():
    try:
        if "db" not in g:
            g.db = sqlite3.connect(DB_PATH)
            g.db.row_factory = sqlite3.Row
        return g.db
    except RuntimeError:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def _col_names(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]

def _migrate(conn):
    # ── 1. tenants 表 ───────────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            username            TEXT UNIQUE NOT NULL,
            view_password_hash  TEXT NOT NULL,
            admin_password_hash TEXT NOT NULL,
            api_token           TEXT UNIQUE NOT NULL,
            display_name        TEXT DEFAULT '',
            created_at          INTEGER DEFAULT 0
        )
    """)

    # ── 2. 旧数据表加 tenant_id ──────────────────────────────────────────────
    if "tenant_id" not in _col_names(conn, "sessions"):
        conn.execute("ALTER TABLE sessions ADD COLUMN tenant_id INTEGER NOT NULL DEFAULT 1")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_tenant ON sessions(tenant_id)")
    if "tenant_id" not in _col_names(conn, "rp_entries"):
        conn.execute("ALTER TABLE rp_entries ADD COLUMN tenant_id INTEGER NOT NULL DEFAULT 1")
    if "tenant_id" not in _col_names(conn, "extra_events"):
        conn.execute("ALTER TABLE extra_events ADD COLUMN tenant_id INTEGER NOT NULL DEFAULT 1")

    if "tenant_id" not in _col_names(conn, "site_config"):
        conn.execute("DROP TABLE IF EXISTS site_config_v2")
        conn.execute("""
            CREATE TABLE site_config_v2 (
                tenant_id INTEGER NOT NULL DEFAULT 1,
                key       TEXT NOT NULL,
                value     TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (tenant_id, key)
            )
        """)
        conn.execute("INSERT INTO site_config_v2(tenant_id,key,value) SELECT 1,key,value FROM site_config")
        conn.execute("DROP TABLE site_config")
        conn.execute("ALTER TABLE site_config_v2 RENAME TO site_config")

    if "tenant_id" not in _col_names(conn, "players"):
        conn.execute("""
            CREATE TABLE players_v2 (
                tenant_id      INTEGER NOT NULL DEFAULT 1,
                qq             TEXT NOT NULL,
                role_name      TEXT NOT NULL DEFAULT '',
                show_name      TEXT DEFAULT '',
                sessions_count INTEGER DEFAULT 0,
                total_replies  INTEGER DEFAULT 0,
                total_words    INTEGER DEFAULT 0,
                last_updated   INTEGER DEFAULT 0,
                PRIMARY KEY (tenant_id, qq)
            )
        """)
        conn.execute("""
            INSERT INTO players_v2
            SELECT 1,qq,role_name,show_name,sessions_count,total_replies,total_words,last_updated
            FROM players
        """)
        conn.execute("DROP TABLE players")
        conn.execute("ALTER TABLE players_v2 RENAME TO players")

    # ── 3. 创建默认租户（如不存在）──────────────────────────────────────────
    if conn.execute("SELECT COUNT(*) FROM tenants").fetchone()[0] == 0:
        view_pw  = os.environ.get("RP_VIEW_PASSWORD", "") or "viewer"
        admin_pw = os.environ.get("RP_ADMIN_PASSWORD", "pDynLBeLGEjd")
        token    = secrets.token_urlsafe(24)
        now      = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO tenants (username,view_password_hash,admin_password_hash,api_token,display_name,created_at) "
            "VALUES (?,?,?,?,?,?)",
            ("default", generate_password_hash(view_pw), generate_password_hash(admin_pw), token, "默认团", now)
        )
        print(f"\n[rp_archive] ✅ 默认租户已创建  username=default  api_token={token}\n")

    # ── 4. shows 表 ─────────────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shows (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id           INTEGER NOT NULL,
            name                TEXT NOT NULL DEFAULT '第一季',
            description         TEXT DEFAULT '',
            is_current          INTEGER DEFAULT 0,
            public_view_enabled INTEGER DEFAULT 1,
            public_token        TEXT UNIQUE,
            created_at          INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shows_tenant ON shows(tenant_id)")

    # 为每个租户创建默认季
    for (tid,) in conn.execute("SELECT id FROM tenants").fetchall():
        if not conn.execute("SELECT id FROM shows WHERE tenant_id=?", (tid,)).fetchone():
            conn.execute(
                "INSERT INTO shows (tenant_id,name,is_current,public_view_enabled,public_token,created_at) "
                "VALUES (?,?,1,1,?,?)",
                (tid, "第一季", secrets.token_urlsafe(24), int(time.time() * 1000))
            )

    # ── 5. 数据表加 show_id ──────────────────────────────────────────────────
    if "show_id" not in _col_names(conn, "sessions"):
        conn.execute("ALTER TABLE sessions ADD COLUMN show_id INTEGER")
        conn.execute("""
            UPDATE sessions SET show_id=(
                SELECT id FROM shows WHERE tenant_id=sessions.tenant_id ORDER BY id LIMIT 1)
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_show ON sessions(show_id)")

    if "show_id" not in _col_names(conn, "rp_entries"):
        conn.execute("ALTER TABLE rp_entries ADD COLUMN show_id INTEGER")
        conn.execute("""
            UPDATE rp_entries SET show_id=(
                SELECT show_id FROM sessions WHERE sessions.id=rp_entries.session_id LIMIT 1)
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rp_show ON rp_entries(show_id)")

    if "show_id" not in _col_names(conn, "extra_events"):
        conn.execute("ALTER TABLE extra_events ADD COLUMN show_id INTEGER")
        conn.execute("""
            UPDATE extra_events SET show_id=(
                SELECT show_id FROM sessions WHERE sessions.id=extra_events.session_id LIMIT 1)
            WHERE session_id != ''
        """)
        conn.execute("""
            UPDATE extra_events SET show_id=(
                SELECT id FROM shows WHERE tenant_id=extra_events.tenant_id ORDER BY id LIMIT 1)
            WHERE show_id IS NULL
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_show ON extra_events(show_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_show_type ON extra_events(show_id,type)")

    # site_config: (tenant_id,key) → (show_id,key)
    if "show_id" not in _col_names(conn, "site_config"):
        conn.execute("""
            CREATE TABLE site_config_v3 (
                show_id   INTEGER NOT NULL,
                tenant_id INTEGER NOT NULL,
                key       TEXT NOT NULL,
                value     TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (show_id, key)
            )
        """)
        conn.execute("""
            INSERT INTO site_config_v3(show_id,tenant_id,key,value)
            SELECT COALESCE((SELECT id FROM shows WHERE tenant_id=sc.tenant_id ORDER BY id LIMIT 1),0),
                   sc.tenant_id,sc.key,sc.value
            FROM site_config sc
        """)
        conn.execute("DROP TABLE site_config")
        conn.execute("ALTER TABLE site_config_v3 RENAME TO site_config")

    # players: (tenant_id,qq) → (show_id,qq)
    if "show_id" not in _col_names(conn, "players"):
        conn.execute("""
            CREATE TABLE players_v3 (
                show_id        INTEGER NOT NULL,
                tenant_id      INTEGER NOT NULL,
                qq             TEXT NOT NULL,
                role_name      TEXT NOT NULL DEFAULT '',
                show_name      TEXT DEFAULT '',
                sessions_count INTEGER DEFAULT 0,
                total_replies  INTEGER DEFAULT 0,
                total_words    INTEGER DEFAULT 0,
                last_updated   INTEGER DEFAULT 0,
                PRIMARY KEY (show_id, qq)
            )
        """)
        conn.execute("""
            INSERT INTO players_v3
            SELECT COALESCE((SELECT id FROM shows WHERE tenant_id=p.tenant_id ORDER BY id LIMIT 1),0),
                   p.tenant_id,p.qq,p.role_name,p.show_name,
                   p.sessions_count,p.total_replies,p.total_words,p.last_updated
            FROM players p
        """)
        conn.execute("DROP TABLE players")
        conn.execute("ALTER TABLE players_v3 RENAME TO players")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_players_show ON players(show_id,role_name)")

    # ── 6. known_groups 表 ──────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS known_groups (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id     INTEGER NOT NULL DEFAULT 0,
            tenant_id   INTEGER NOT NULL,
            group_id    TEXT NOT NULL,
            name        TEXT DEFAULT '',
            description TEXT DEFAULT '',
            created_at  INTEGER DEFAULT 0,
            set_name    TEXT NOT NULL DEFAULT ''
        )
    """)
    # 群号占用快照：机器人按本地群号池的真实状态整体上报，后台「当前占用群」优先用这张表
    # （之前靠场次记录推算：强结漏关的、没有场次记录的微信群都会算错）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS group_occupancy (
            tenant_id    INTEGER NOT NULL,
            group_id     TEXT    NOT NULL,
            subtype      TEXT    NOT NULL DEFAULT '',
            game_day     TEXT    NOT NULL DEFAULT '',
            game_time    TEXT    NOT NULL DEFAULT '',
            place        TEXT    NOT NULL DEFAULT '',
            participants TEXT    NOT NULL DEFAULT '[]',
            start_ts     INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (tenant_id, group_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS group_occupancy_sync (
            tenant_id INTEGER PRIMARY KEY,
            synced_at INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_known_groups_tenant ON known_groups(tenant_id)")
    if "set_name" not in _col_names(conn, "known_groups"):
        conn.execute("ALTER TABLE known_groups ADD COLUMN set_name TEXT NOT NULL DEFAULT ''")

    # ── 6b. known_group_sets 表（群号组名单独存储，支持空组）────────────────
    # 迁移：将旧的 UNIQUE(show_id, set_name) 改为 UNIQUE(tenant_id, set_name)
    # 检测方式：看 sqlite_master 里 known_group_sets 的建表语句是否含 show_id 唯一约束
    _kgs_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='known_group_sets'"
    ).fetchone()
    _need_kgs_migration = (
        _kgs_sql is None or
        ("UNIQUE(show_id" in (_kgs_sql[0] or "") or "unique(show_id" in (_kgs_sql[0] or "").lower())
    )
    if _need_kgs_migration and _kgs_sql is not None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS known_group_sets_v2 (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                show_id    INTEGER NOT NULL DEFAULT 0,
                tenant_id  INTEGER NOT NULL DEFAULT 1,
                set_name   TEXT NOT NULL,
                created_at INTEGER NOT NULL DEFAULT 0,
                UNIQUE(tenant_id, set_name)
            )
        """)
        conn.execute("""
            INSERT OR IGNORE INTO known_group_sets_v2(show_id,tenant_id,set_name,created_at)
            SELECT show_id,tenant_id,set_name,created_at FROM known_group_sets
        """)
        conn.execute("DROP TABLE known_group_sets")
        conn.execute("ALTER TABLE known_group_sets_v2 RENAME TO known_group_sets")
    elif _kgs_sql is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS known_group_sets (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                show_id    INTEGER NOT NULL DEFAULT 0,
                tenant_id  INTEGER NOT NULL DEFAULT 1,
                set_name   TEXT NOT NULL,
                created_at INTEGER NOT NULL DEFAULT 0,
                UNIQUE(tenant_id, set_name)
            )
        """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_known_group_sets_tenant ON known_group_sets(tenant_id)")

    # ── 8. config_history 表 ───────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id     INTEGER NOT NULL,
            tenant_id   INTEGER NOT NULL,
            config_data TEXT NOT NULL,
            operator    TEXT DEFAULT '',
            created_at  INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_config_history_show ON config_history(show_id, created_at)")

    # ── universal_items 表（通用物品库：租户级，跨季度，上限 UNIVERSAL_MAX_ITEMS）──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS universal_items (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id  INTEGER NOT NULL,
            name       TEXT NOT NULL,
            type       TEXT NOT NULL DEFAULT 'item',
            entry_json TEXT NOT NULL DEFAULT '{}',
            created_at INTEGER DEFAULT 0,
            UNIQUE (tenant_id, name)
        )
    """)

    # ── config_templates 表 ─────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config_templates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id   INTEGER NOT NULL,
            name        TEXT NOT NULL,
            config_data TEXT NOT NULL,
            created_at  INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cfg_tpl_tenant ON config_templates(tenant_id)")

    # ── 7. reward_records 表 ────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reward_records (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id        INTEGER NOT NULL,
            tenant_id      INTEGER NOT NULL,
            session_id     TEXT DEFAULT '',
            game_day       TEXT DEFAULT '',
            player_qq      TEXT DEFAULT '',
            role_name      TEXT DEFAULT '',
            reward_data    TEXT DEFAULT '{}',
            distributed_at INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reward_records_show ON reward_records(show_id)")

    # ── 9. blacklist 表 ─────────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS blacklist (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id  INTEGER NOT NULL,
            qq         TEXT NOT NULL DEFAULT '',
            role_name  TEXT DEFAULT '',
            content    TEXT DEFAULT '',
            tags       TEXT DEFAULT '',
            added_by   TEXT DEFAULT '',
            created_at INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_blacklist_tenant ON blacklist(tenant_id)")

    # ── command_guides 表 ─────────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS command_guides (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id  INTEGER NOT NULL,
            name       TEXT    NOT NULL DEFAULT '指令指南',
            slug       TEXT    NOT NULL UNIQUE,
            blocks     TEXT    NOT NULL DEFAULT '[]',
            created_at INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cmd_guide_tenant ON command_guides(tenant_id)")

    # ── 10. players 加回复时间累计列 ────────────────────────────────────────
    if "reply_time_sum" not in _col_names(conn, "players"):
        conn.execute("ALTER TABLE players ADD COLUMN reply_time_sum  INTEGER NOT NULL DEFAULT 0")
    if "reply_time_count" not in _col_names(conn, "players"):
        conn.execute("ALTER TABLE players ADD COLUMN reply_time_count INTEGER NOT NULL DEFAULT 0")

    # ── 11. players 加 is_npc 标记列 ─────────────────────────────────────────
    if "is_npc" not in _col_names(conn, "players"):
        conn.execute("ALTER TABLE players ADD COLUMN is_npc INTEGER NOT NULL DEFAULT 0")

    # ── 12. rp_entries 加 reply_time_ms 列并回填历史数据 ──────────────────────
    if "reply_time_ms" not in _col_names(conn, "rp_entries"):
        conn.execute("ALTER TABLE rp_entries ADD COLUMN reply_time_ms INTEGER")
        # 回填：对每条 entry，找同 session 内上一条不同角色的 entry，计算时间差
        entries = conn.execute(
            "SELECT id, session_id, role_name, timestamp FROM rp_entries WHERE timestamp > 0 ORDER BY session_id, seq"
        ).fetchall()
        # 按 session 分组，追踪每个 session 里最后一条不同角色的 timestamp
        last_other: dict = {}  # session_id → {role_name → last_ts_of_other_roles}
        for e in entries:
            eid, sid, role, ts = e["id"], e["session_id"], e["role_name"], e["timestamp"]
            if sid not in last_other:
                last_other[sid] = {}
            # 找这个 session 里，其他角色最近一条的 ts
            others = [t for r, t in last_other[sid].items() if r != role]
            if others:
                prev_ts = max(others)
                diff = ts - prev_ts
                if 0 < diff < 7_200_000:  # 0~2小时内有效
                    conn.execute("UPDATE rp_entries SET reply_time_ms=? WHERE id=?", (diff, eid))
            # 更新这个角色在这个 session 的最后 ts
            last_other[sid][role] = ts
        print(f"[migrate] rp_entries reply_time_ms 回填完成，共 {len(entries)} 条")

    # ── 13. rp_entries 加 is_excluded 标记列 ─────────────────────────────────
    if "is_excluded" not in _col_names(conn, "rp_entries"):
        conn.execute("ALTER TABLE rp_entries ADD COLUMN is_excluded INTEGER NOT NULL DEFAULT 0")

    # ── 14. shows 加档期三列（MMDD 格式，空串 = 不限制）──────────────────────
    if "schedule_start" not in _col_names(conn, "shows"):
        conn.execute("ALTER TABLE shows ADD COLUMN schedule_start TEXT NOT NULL DEFAULT ''")
    if "schedule_end" not in _col_names(conn, "shows"):
        conn.execute("ALTER TABLE shows ADD COLUMN schedule_end TEXT NOT NULL DEFAULT ''")
    if "supplement_end" not in _col_names(conn, "shows"):
        conn.execute("ALTER TABLE shows ADD COLUMN supplement_end TEXT NOT NULL DEFAULT ''")
    # 预订季度：booked=1 表示还没开始（网页日历预订），schedule_year 是档期开始日所在的年份（MMDD 本身不带年）
    if "booked" not in _col_names(conn, "shows"):
        conn.execute("ALTER TABLE shows ADD COLUMN booked INTEGER NOT NULL DEFAULT 0")
    if "schedule_year" not in _col_names(conn, "shows"):
        conn.execute("ALTER TABLE shows ADD COLUMN schedule_year INTEGER NOT NULL DEFAULT 0")
    # 预订时顺手填好的开季准备：「。开始季度」时机器人自动开启这个群号组、把这些名字预登记为 NPC（一行一个）
    if "group_set" not in _col_names(conn, "shows"):
        conn.execute("ALTER TABLE shows ADD COLUMN group_set TEXT NOT NULL DEFAULT ''")
    if "npc_names" not in _col_names(conn, "shows"):
        conn.execute("ALTER TABLE shows ADD COLUMN npc_names TEXT NOT NULL DEFAULT ''")
    # 老季度（这次改动前创建的）补上档期年份，日历和重叠检查才看得见它们
    for _r in conn.execute("SELECT id, schedule_start, created_at FROM shows "
                           "WHERE schedule_year=0 AND schedule_start!='' AND booked=0").fetchall():
        _y = _infer_schedule_year(_r[1], _r[2])
        if _y:
            conn.execute("UPDATE shows SET schedule_year=? WHERE id=?", (_y, _r[0]))

    # ── 15. collected_images 表（信息收集里提交的图片，按 show 隔离，结束季度时整体清理）──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS collected_images (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id  INTEGER NOT NULL,
            show_id    INTEGER NOT NULL,
            uid        TEXT    NOT NULL,
            filename   TEXT    NOT NULL,
            size_bytes INTEGER NOT NULL,
            created_at INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_collected_images_show ON collected_images(tenant_id, show_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_collected_images_user ON collected_images(tenant_id, show_id, uid)")

    # ── 16. phone_codes 表（玩家手机激活码：一季一角色一个码，季度结束后随 is_current=0 失效）──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_codes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id  INTEGER NOT NULL,
            show_id    INTEGER NOT NULL,
            role_name  TEXT    NOT NULL,
            code       TEXT    NOT NULL UNIQUE,
            created_at INTEGER NOT NULL DEFAULT 0,
            UNIQUE(show_id, role_name)
        )
    """)

    # ── 17. 网页发送：开关 / 插件上报的规则快照 / 被静默拉黑的网页短信 ──────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_settings (
            show_id  INTEGER PRIMARY KEY,
            web_send INTEGER NOT NULL DEFAULT 0
        )
    """)
    if "theme_config" not in _col_names(conn, "phone_settings"):
        conn.execute("ALTER TABLE phone_settings ADD COLUMN theme_config TEXT NOT NULL DEFAULT '{}'")
    if "stickers" not in _col_names(conn, "phone_settings"):
        # 网页手机表情面板（一行一个 emoji/颜文字），空 = 用默认那套
        conn.execute("ALTER TABLE phone_settings ADD COLUMN stickers TEXT NOT NULL DEFAULT ''")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_sync (
            show_id   INTEGER PRIMARY KEY,
            tenant_id INTEGER NOT NULL,
            snapshot  TEXT    NOT NULL DEFAULT '{}',
            cursor    INTEGER NOT NULL DEFAULT 0,
            synced_at INTEGER NOT NULL DEFAULT 0
        )
    """)
    # 静默拉黑的网页短信：发件人手机里要显示「已发出」，但不能进 extra_events——
    # 那张表会被复盘页/导出/互动统计直接读，进去就等于投递成功了
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_silent (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id   INTEGER NOT NULL,
            from_role TEXT    NOT NULL,
            to_role   TEXT    NOT NULL,
            content   TEXT    NOT NULL,
            timestamp INTEGER NOT NULL,
            game_day  TEXT    NOT NULL DEFAULT '',
            day_key   TEXT    NOT NULL DEFAULT ''
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_phone_silent_show ON phone_silent(show_id, from_role)")

    # ── 18. 朋友圈：帖子 / 图片 / 点赞 / 评论；图片额度（每人每季张数 + 团账号总空间）────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS moments (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id  INTEGER NOT NULL,
            show_id    INTEGER NOT NULL,
            role_name  TEXT    NOT NULL,
            content    TEXT    NOT NULL DEFAULT '',
            game_day   TEXT    NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL,
            deleted    INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_moments_show ON moments(show_id, deleted, id)")
    # 小游戏全服排行榜：不挂 show/tenant 外键，季度结束、激活码失效后名字和分数照样永久留在榜上
    conn.execute("""
        CREATE TABLE IF NOT EXISTS game_scores (
            game       TEXT    NOT NULL,
            show_id    INTEGER NOT NULL,
            role_name  TEXT    NOT NULL,
            label      TEXT    NOT NULL,
            score      INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (game, show_id, role_name)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_game_scores_rank ON game_scores(game, score DESC, updated_at)")
    # 给对方的备注：只有自己看得到，显示成「备注（真名）」，优先于对方设的微信名
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_remarks (
            show_id    INTEGER NOT NULL,
            owner      TEXT    NOT NULL,
            target     TEXT    NOT NULL,
            remark     TEXT    NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (show_id, owner, target)
        )
    """)
    # 每日一句缓存：一言 / 今日诗词各一条，按天缓存，外部接口挂了就退回最近一条
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_quotes (
            day    TEXT NOT NULL,
            kind   TEXT NOT NULL,
            text   TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (day, kind)
        )
    """)
    # 删图片 = 删文件 + deleted_at 置时间，行留着：那条朋友圈照样在，图片位置显示「图片已删除」
    conn.execute("""
        CREATE TABLE IF NOT EXISTS moment_images (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            moment_id  INTEGER NOT NULL,
            tenant_id  INTEGER NOT NULL,
            show_id    INTEGER NOT NULL,
            role_name  TEXT    NOT NULL,
            file       TEXT    NOT NULL,
            thumb      TEXT    NOT NULL,
            size_bytes INTEGER NOT NULL,
            width      INTEGER NOT NULL DEFAULT 0,
            height     INTEGER NOT NULL DEFAULT 0,
            seq        INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            deleted_at INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_moment_images_moment ON moment_images(moment_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_moment_images_quota ON moment_images(tenant_id, deleted_at)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS moment_likes (
            moment_id  INTEGER NOT NULL,
            role_name  TEXT    NOT NULL,
            created_at INTEGER NOT NULL,
            PRIMARY KEY (moment_id, role_name)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS moment_comments (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            moment_id  INTEGER NOT NULL,
            role_name  TEXT    NOT NULL,
            reply_to   TEXT    NOT NULL DEFAULT '',
            content    TEXT    NOT NULL,
            created_at INTEGER NOT NULL,
            deleted    INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_moment_comments_moment ON moment_comments(moment_id)")
    if "comm_paused" not in _col_names(conn, "phone_settings"):
        conn.execute("ALTER TABLE phone_settings ADD COLUMN comm_paused INTEGER NOT NULL DEFAULT 0")  # 管理员「暂停所有通讯」
    if "moment_quota" not in _col_names(conn, "phone_settings"):
        conn.execute("ALTER TABLE phone_settings ADD COLUMN moment_quota INTEGER NOT NULL DEFAULT 0")  # 0 = 默认张数
    if "moment_quota_mb" not in _col_names(conn, "tenants"):
        conn.execute("ALTER TABLE tenants ADD COLUMN moment_quota_mb INTEGER NOT NULL DEFAULT 0")     # 0 = 默认空间

    # ── 19. 网页手机头像：一季一个角色一张，重新上传就删掉旧文件 ──────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_avatars (
            show_id    INTEGER NOT NULL,
            role_name  TEXT    NOT NULL,
            tenant_id  INTEGER NOT NULL,
            file       TEXT    NOT NULL,
            size_bytes INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (show_id, role_name)
        )
    """)

    # ── 20. 点歌：一律匿名（公告/网页只写「有人」，管理员复盘能看到是谁）；announced=机器人已发到公告群 ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS song_requests (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id  INTEGER NOT NULL,
            show_id    INTEGER NOT NULL,
            from_role  TEXT    NOT NULL,
            to_role    TEXT    NOT NULL DEFAULT '',
            platform   TEXT    NOT NULL DEFAULT '163',
            song_id    INTEGER NOT NULL,
            song_mid   TEXT    NOT NULL DEFAULT '',
            song_name  TEXT    NOT NULL,
            artists    TEXT    NOT NULL DEFAULT '',
            album      TEXT    NOT NULL DEFAULT '',
            cover      TEXT    NOT NULL DEFAULT '',
            fee        INTEGER NOT NULL DEFAULT 0,
            message    TEXT    NOT NULL DEFAULT '',
            source     TEXT    NOT NULL DEFAULT 'web',
            game_day   TEXT    NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL,
            announced  INTEGER NOT NULL DEFAULT 0,
            deleted    INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_song_requests_show ON song_requests(show_id, deleted, id)")
    if "song_daily" not in _col_names(conn, "phone_settings"):
        conn.execute("ALTER TABLE phone_settings ADD COLUMN song_daily INTEGER NOT NULL DEFAULT 0")  # 0 = 默认次数

    # ── 21. 管理员手机码：一季一个，用它进网页手机是「管理身份」（只看和删，不能发）────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_admin_codes (
            show_id    INTEGER PRIMARY KEY,
            tenant_id  INTEGER NOT NULL,
            code       TEXT    NOT NULL UNIQUE,
            created_at INTEGER NOT NULL DEFAULT 0
        )
    """)

    # ── 22. 网页礼品店/图鉴：网页上逛礼品店、收到预设礼物解锁图鉴的记录，机器人同步时取走写回自己的图鉴 ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_shop_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id      INTEGER NOT NULL,
            role_name    TEXT    NOT NULL,
            unlocked     TEXT    NOT NULL DEFAULT '[]',
            display_gift TEXT    NOT NULL DEFAULT '',
            refreshed_at INTEGER NOT NULL DEFAULT 0,
            created_at   INTEGER NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_phone_shop_log ON phone_shop_log(show_id, role_name)")

    # ── 23. 匿名对话的化名：谁(owner)对谁(target)用的什么化名；对同一个人最多 3 个；同一收件人下化名不重名 ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_aliases (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id     INTEGER NOT NULL,
            owner_role  TEXT    NOT NULL,
            target_role TEXT    NOT NULL,
            alias_name  TEXT    NOT NULL,
            created_at  INTEGER NOT NULL,
            blocked_by  TEXT    NOT NULL DEFAULT '',
            blocked_at  INTEGER NOT NULL DEFAULT 0,
            UNIQUE (show_id, target_role, alias_name)
        )
    """)

    # ── 29. 微信名：玩家自设的显示名，消息列表/对话标题里显示成「微信名（真名）」；只改显示，不参与任何规则 ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_nicknames (
            show_id    INTEGER NOT NULL,
            role       TEXT    NOT NULL,
            nick       TEXT    NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (show_id, role)
        )
    """)

    # ── 28. 待回「暂不提醒」：key 认的是「这一次」等待（场次按开始等的时间、信按寄来时间、关系线按条数），对方再回一轮就是新的提醒 ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_pending_dismiss (
            show_id    INTEGER NOT NULL,
            role       TEXT    NOT NULL,
            key        TEXT    NOT NULL,
            created_at INTEGER NOT NULL,
            PRIMARY KEY (show_id, role, key)
        )
    """)

    # ── 27. 插件每 2 分钟随同步上报的每人报告（我的数量/弧长/时间线/待回），网页「时间线与统计」页只读 ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_reports (
            show_id    INTEGER NOT NULL,
            role       TEXT    NOT NULL,
            data       TEXT    NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (show_id, role)
        )
    """)

    # ── 26. 网页群聊：玩家自己拉人建群；只在网页上（不进 QQ），跟网页发送一起开关；一条消息算 1 次短信 ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_groups (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id  INTEGER NOT NULL,
            show_id    INTEGER NOT NULL,
            name       TEXT    NOT NULL,
            created_by TEXT    NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)
    # left_at=0 表示还在群里；重新被拉进来就把 joined_at 更新成那一刻（之前的消息看不到）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_group_members (
            group_id  INTEGER NOT NULL,
            role      TEXT    NOT NULL,
            joined_at INTEGER NOT NULL,
            left_at   INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (group_id, role)
        )
    """)
    # kind: msg=玩家发言 / sys=「谁拉了谁」这类提示（不占次数、不公开）。content 是原文（发件人自己看），
    # delivered 是混乱效果之后大家看到的；signature 是大家看到的名字（化名，或被换了的落款）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_group_msgs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id  INTEGER NOT NULL,
            show_id    INTEGER NOT NULL,
            group_id   INTEGER NOT NULL,
            kind       TEXT    NOT NULL DEFAULT 'msg',
            from_role  TEXT    NOT NULL DEFAULT '',
            alias      TEXT    NOT NULL DEFAULT '',
            signature  TEXT    NOT NULL DEFAULT '',
            content    TEXT    NOT NULL,
            delivered  TEXT    NOT NULL DEFAULT '',
            is_public  INTEGER NOT NULL DEFAULT 0,
            hide_receiver INTEGER NOT NULL DEFAULT 0,
            show_effect INTEGER NOT NULL DEFAULT 0,
            game_day   TEXT    NOT NULL DEFAULT '',
            day_key    TEXT    NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL,
            deleted    INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_phone_group_msgs ON phone_group_msgs(group_id, id)")
    if "group_cursor" not in _col_names(conn, "phone_sync"):  # 插件已经取走、计过次数的群消息 id
        conn.execute("ALTER TABLE phone_sync ADD COLUMN group_cursor INTEGER NOT NULL DEFAULT 0")

    # ── 25. 网页上的实名拉黑/解除：先在这里立刻对网页生效，机器人同步时取走写进 sys_blocklist（群里也生效），回报 done ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_block_ops (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id    INTEGER NOT NULL,
            blocker    TEXT    NOT NULL,
            target     TEXT    NOT NULL,
            action     TEXT    NOT NULL,
            silent     INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            done       INTEGER NOT NULL DEFAULT 0
        )
    """)

    # ── 24. 网页投的心动信：先存这里，机器人同步时取走放进自己的信池，跟群里投的一起每晚派送 ──
    # state: new=还没交给机器人 / taken=机器人回报已放进信池 / revoked=撤回了；handed_at=已经在同步回包里给过机器人
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_lovemails (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id  INTEGER NOT NULL,
            show_id    INTEGER NOT NULL,
            from_role  TEXT    NOT NULL,
            to_role    TEXT    NOT NULL,
            content    TEXT    NOT NULL,
            signature  TEXT    NOT NULL DEFAULT '匿名',
            game_day   TEXT    NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL,
            state      TEXT    NOT NULL DEFAULT 'new',
            handed_at  INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_phone_lovemails_show ON phone_lovemails(show_id, state, id)")
    # 撤回已经在机器人信池里的信（群里投的、或网页投的已被取走）：按 发件人+投递时间 找到那封，机器人处理完回报 done
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_lovemail_revokes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id    INTEGER NOT NULL,
            from_role  TEXT    NOT NULL,
            mail_ts    INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            done       INTEGER NOT NULL DEFAULT 0
        )
    """)

    # ── 长日将尽许愿墙：独立的小功能，不挂在 tenant/superadmin 体系下 ──────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS changri_wishes (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            content        TEXT    NOT NULL,
            author_name    TEXT    DEFAULT '',
            status         TEXT    NOT NULL DEFAULT 'pending',
            admin_note     TEXT    DEFAULT '',
            ip_hash        TEXT    DEFAULT '',
            created_at     INTEGER NOT NULL,
            implemented_at INTEGER
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_changri_wishes_status ON changri_wishes(status, created_at)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS changri_wish_config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    # 默认管理密码，首次建表时写入；已存在就不覆盖（管理员改过密码后重启服务不会被重置）
    conn.execute(
        "INSERT OR IGNORE INTO changri_wish_config (key, value) VALUES ('admin_password_hash', ?)",
        ("pbkdf2:sha256:1000000$h6HaqsWoqxvbV3oL$9f43bd6f110428de3c6037286cc21c76afd0ad62f86d331cbc287fb4f7a3e9ab",)
    )

    # ── 论坛字数上限旧键：机器人从没读过，且每次保存配置都被重置为 500，直接清掉 ──
    conn.execute("DELETE FROM site_config WHERE key='forumMaxLength'")

    conn.commit()

def init_db():
    schema = os.path.join(os.path.dirname(__file__), "schema.sql")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        with open(schema, encoding="utf-8") as f:
            conn.executescript(f.read())
        _migrate(conn)
    finally:
        conn.close()

def ts_to_str(ts):
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""

def fmt_seconds(secs):
    secs = int(secs)
    return f"{secs//60}分{secs%60}秒" if secs >= 60 else f"{secs}秒"


# ── Auth ─────────────────────────────────────────────────────────────────────

def current_tenant_id():
    return session.get("tenant_id")

def get_show_id():
    """当前管理员正在查看的季 ID（存于 session）。"""
    sid = session.get("view_show_id")
    if sid:
        return sid
    tid = current_tenant_id()
    if not tid:
        return None
    db  = get_db()
    row = db.execute("SELECT id FROM shows WHERE tenant_id=? AND is_current=1", (tid,)).fetchone()
    if not row:
        row = db.execute("SELECT id FROM shows WHERE tenant_id=? AND booked=0 ORDER BY id", (tid,)).fetchone()
    if row:
        session["view_show_id"] = row["id"]
        return row["id"]
    return None

def get_current_show_id_for_tenant(tenant_id):
    """API 用：找该租户当前活跃季的 ID。"""
    db  = get_db()
    row = db.execute("SELECT id FROM shows WHERE tenant_id=? AND is_current=1", (tenant_id,)).fetchone()
    if not row:
        row = db.execute("SELECT id FROM shows WHERE tenant_id=? AND booked=0 ORDER BY id DESC", (tenant_id,)).fetchone()
    return row["id"] if row else None

def get_current_show_for_tenant(tenant_id):
    """API 用：返回当前活跃季的完整行（dict），含档期字段。"""
    db  = get_db()
    row = db.execute("SELECT * FROM shows WHERE tenant_id=? AND is_current=1", (tenant_id,)).fetchone()
    if not row:
        row = db.execute("SELECT * FROM shows WHERE tenant_id=? AND booked=0 ORDER BY id DESC", (tenant_id,)).fetchone()
    return dict(row) if row else None

# ── 档期时区工具 ──────────────────────────────────────────────────────────────
def _parse_mmdd(mmdd, ref_year=None):
    """将 "MMDD" 字符串解析为 date 对象；格式不合法则返回 None。"""
    if not mmdd or len(mmdd) != 4:
        return None
    try:
        year = ref_year or _date.today().year
        return _date(year, int(mmdd[:2]), int(mmdd[2:]))
    except (ValueError, TypeError):
        return None

def _schedule_zone(show, now_ts_ms=None):
    """
    返回当前时刻相对于该季档期所处的区段：
      'pre'        – schedule_start 之前（不记录）
      'main'       – schedule_start ~ schedule_end（正常记录）
      'supplement' – schedule_end+1 ~ supplement_end（只记录场次，不计弧长）
      'post'       – supplement_end 之后（不记录）

    未设置档期（schedule_start 为空）→ 始终返回 'main'。
    """
    if not show:
        return 'main'
    start_str = show.get("schedule_start") or ""
    if not start_str:
        return 'main'

    # 统一按东八区算日期，避免服务器跑 UTC 时凌晨 0-8 点被误判成前一天
    if now_ts_ms:
        today = datetime.fromtimestamp(now_ts_ms / 1000, TZ_BEIJING).date()
    else:
        today = datetime.now(TZ_BEIJING).date()

    end_str  = show.get("schedule_end") or start_str
    supp_str = show.get("supplement_end") or ""

    # start 所在的日历年：以「创建本季度时」的日期为基准去猜，而不是用「查询时的今天」猜——
    # 否则跨年档期（比如 12/28~1/5）在元旦之后查询时，会把 start 的年份跟着"今天"往后挪一年，
    # 变成还没到的未来日期，误判成 pre（这个季度其实正在 main/supplement 期间）。
    # created_at 缺失（极老数据）时退回用 today 的年份，等价于旧逻辑。
    created_at = show.get("created_at") or 0
    anchor_date = (datetime.fromtimestamp(created_at / 1000, TZ_BEIJING).date()
                   if created_at else today)
    def _start_at(y):
        return _parse_mmdd(start_str, y)
    cand_years = [y for y in (anchor_date.year - 1, anchor_date.year, anchor_date.year + 1)
                  if _start_at(y) is not None]
    if not cand_years:
        return 'main'
    year = min(cand_years, key=lambda y: abs((_start_at(y) - anchor_date).days))

    start = _start_at(year)
    # 跨年档期：若 end/supplement 的 MMDD < start 的 MMDD，说明落在 start 的下一年
    end_year  = year + 1 if end_str  and end_str  < start_str else year
    supp_year = year + 1 if supp_str and supp_str < start_str else year
    end   = _parse_mmdd(end_str,  end_year)
    supp  = _parse_mmdd(supp_str, supp_year)

    if not start or not end:
        return 'main'

    if today < start:
        return 'pre'
    if today <= end:
        return 'main'
    if supp and today <= supp:
        return 'supplement'
    return 'post'

@app.context_processor
def inject_show_context():
    if not session.get("tenant_id"):
        return {}
    tid   = current_tenant_id()
    db    = get_db()
    shows = [dict(s) for s in db.execute(
        "SELECT * FROM shows WHERE tenant_id=? ORDER BY created_at", (tid,)
    ).fetchall()]
    sid   = get_show_id()
    cur   = next((s for s in shows if s["id"] == sid), None)
    return {"all_shows": shows, "current_show_id": sid, "current_show": cur}

def require_login(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("tenant_id"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped

def require_admin(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("tenant_id"):
            return redirect(url_for("login"))
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapped

def require_superadmin(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("superadmin_logged_in"):
            return redirect(url_for("superadmin_login"))
        return f(*args, **kwargs)
    return wrapped

def get_tenant_from_token():
    token = request.headers.get("X-Archive-Token", "")
    if not token:
        abort(403)
    row = get_db().execute("SELECT id FROM tenants WHERE api_token=?", (token,)).fetchone()
    if not row:
        abort(403)
    return row["id"]

def _cleanup_show_collected_images(db, tid, show_id):
    """季度结束/被顶替时清空该季收集的图片文件与配额记录，防止磁盘无限增长"""
    img_dir = os.path.join(COLLECT_IMAGE_DIR, str(tid), str(show_id))
    shutil.rmtree(img_dir, ignore_errors=True)
    db.execute("DELETE FROM collected_images WHERE tenant_id=? AND show_id=?", (tid, show_id))

def _is_url_host_public(hostname):
    """拒绝解析到内网/本机/链路本地地址的域名，防止 SSRF"""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    if not infos:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return True


# ── 登录路由 ─────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        tenant   = get_db().execute("SELECT * FROM tenants WHERE username=?", (username,)).fetchone()
        if tenant and check_password_hash(tenant["view_password_hash"], password):
            session["tenant_id"]           = tenant["id"]
            session["tenant_username"]     = tenant["username"]
            session["tenant_display_name"] = tenant["display_name"] or tenant["username"]
            session.pop("view_show_id", None)
            return redirect(url_for("home"))
        error = "用户名或密码错误，请重试。"
    current_user = session.get("tenant_display_name") or session.get("tenant_username")
    return render_template("login.html", error=error, current_user=current_user)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/admin/login", methods=["GET", "POST"])
@require_login
def admin_login():
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        tenant   = get_db().execute("SELECT * FROM tenants WHERE id=?", (current_tenant_id(),)).fetchone()
        if tenant and check_password_hash(tenant["admin_password_hash"], password):
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        error = "后台密钥错误，请重试。"
    return render_template("admin_login.html", error=error)

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("home"))

@app.route("/admin/change_password", methods=["POST"])
@require_admin
def admin_change_password():
    tid = current_tenant_id()
    vp  = request.form.get("view_password", "").strip()
    ap  = request.form.get("admin_password", "").strip()
    db  = get_db()
    if vp:
        db.execute("UPDATE tenants SET view_password_hash=? WHERE id=?", (generate_password_hash(vp), tid))
    if ap:
        db.execute("UPDATE tenants SET admin_password_hash=? WHERE id=?", (generate_password_hash(ap), tid))
    db.commit()
    if vp:
        session.clear()
        return redirect(url_for("login"))
    if ap:
        session.pop("admin_logged_in", None)
        return redirect(url_for("admin_login"))
    return redirect(url_for("admin") + "?pwd_changed=1")

@app.route("/admin/backup")
@require_admin
def admin_backup():
    return send_file(DB_PATH, as_attachment=True, download_name="rp_data.db",
                     mimetype="application/octet-stream")


# ── 超管路由 ─────────────────────────────────────────────────────────────────

@app.route("/superadmin/login", methods=["GET", "POST"])
def superadmin_login():
    error = None
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("password", ""), SUPERADMIN_PASS):
            session["superadmin_logged_in"] = True
            return redirect(url_for("superadmin"))
        error = "超管密码错误。"
    return render_template("superadmin_login.html", error=error)

@app.route("/superadmin/logout")
def superadmin_logout():
    session.pop("superadmin_logged_in", None)
    session.pop("superadmin_acting", None)
    session.pop("tenant_id", None)
    session.pop("admin_logged_in", None)
    session.pop("view_show_id", None)
    return redirect(url_for("superadmin_login"))

@app.route("/superadmin/tenant/<int:tid>/enter", methods=["POST"])
@require_superadmin
def superadmin_enter_tenant(tid):
    tenant = get_db().execute("SELECT * FROM tenants WHERE id=?", (tid,)).fetchone()
    if not tenant: abort(404)
    session["tenant_id"]           = tenant["id"]
    session["tenant_username"]     = tenant["username"]
    session["tenant_display_name"] = tenant["display_name"] or tenant["username"]
    session["admin_logged_in"]     = True
    session["superadmin_acting"]   = True
    session.pop("view_show_id", None)
    return redirect(url_for("home"))

@app.route("/superadmin/exit_tenant", methods=["POST"])
def superadmin_exit_tenant():
    session.pop("tenant_id", None)
    session.pop("tenant_username", None)
    session.pop("tenant_display_name", None)
    session.pop("admin_logged_in", None)
    session.pop("superadmin_acting", None)
    session.pop("view_show_id", None)
    return redirect(url_for("superadmin"))

@app.route("/superadmin")
@require_superadmin
def superadmin():
    db      = get_db()
    tenants = [dict(t) for t in db.execute("SELECT * FROM tenants ORDER BY created_at DESC").fetchall()]
    for t in tenants:
        tid = t["id"]
        t["session_count"]  = db.execute(
            "SELECT COUNT(*) FROM sessions WHERE tenant_id=?", (tid,)).fetchone()[0]
        t["created_at_str"] = ts_to_str(t.get("created_at"))
        t["shows"]          = [dict(s) for s in db.execute(
            "SELECT * FROM shows WHERE tenant_id=? ORDER BY created_at", (tid,)).fetchall()]
    return render_template("superadmin_tenants.html", tenants=tenants,
                           created=request.args.get("created"),
                           deleted=request.args.get("deleted"),
                           error=request.args.get("error"))

@app.route("/superadmin/players")
@require_superadmin
def superadmin_players():
    db  = get_db()
    qq  = request.args.get("qq", "").strip()
    rows = []
    summary = None
    if qq:
        rows = db.execute("""
            SELECT p.qq, p.role_name, p.show_name, p.show_id,
                   p.sessions_count, p.total_replies, p.total_words, p.last_updated,
                   p.reply_time_sum, p.reply_time_count,
                   t.username AS tenant_username, t.display_name AS tenant_display,
                   s.name AS arc_name
            FROM players p
            JOIN tenants t ON p.tenant_id = t.id
            JOIN shows   s ON p.show_id   = s.id
            WHERE p.qq = ? OR p.role_name = ?
            ORDER BY p.last_updated DESC
        """, (qq, qq)).fetchall()
        rows = [dict(r) for r in rows]
        for r in rows:
            r["last_updated_str"] = ts_to_str(r["last_updated"])
            r["is_placeholder"] = (r["qq"] == r["role_name"])
        if rows:
            # 优先用 players 表累计的回复时间（即使 rp_entries 已清空也有数据）
            total_rts = sum(r.get("reply_time_sum", 0)   for r in rows)
            total_rtc = sum(r.get("reply_time_count", 0) for r in rows)
            if total_rtc > 0:
                global_avg_reply = (total_rts / total_rtc) / 1000  # 转秒
            else:
                # 回落：从 rp_entries 实时计算（旧数据兼容）
                role_names = list({r["role_name"] for r in rows if r["role_name"]})
                all_reply_times = []
                if role_names:
                    ph = ",".join("?" * len(role_names))
                    all_entries = db.execute(
                        f"SELECT session_id,role_name,timestamp FROM rp_entries WHERE role_name IN ({ph}) AND timestamp > 0 ORDER BY session_id,seq,timestamp",
                        role_names
                    ).fetchall()
                    by_sess = defaultdict(list)
                    for e in all_entries:
                        by_sess[e["session_id"]].append(dict(e))
                    for entries in by_sess.values():
                        for rn in role_names:
                            times = [
                                (entries[i]["timestamp"] - entries[i-1]["timestamp"]) / 1000
                                for i in range(1, len(entries))
                                if entries[i]["role_name"] == rn and entries[i-1]["role_name"] != rn
                                and 0 < (entries[i]["timestamp"] - entries[i-1]["timestamp"]) / 1000 < 7200
                            ]
                            all_reply_times.extend(times)
                global_avg_reply = sum(all_reply_times) / len(all_reply_times) if all_reply_times else None

            summary = {
                "qq": qq,
                "total_sessions": sum(r["sessions_count"] for r in rows),
                "total_replies":  sum(r["total_replies"]  for r in rows),
                "total_words":    sum(r["total_words"]    for r in rows),
                "arc_count":      len(rows),
                "global_avg_reply": global_avg_reply,
            }

            # ── 按场次类型拆分统计 ────────────────────────────────────────
            _TRACKED = ["私密", "电话", "官约", "心愿"]
            def _empty_subtype(): return {t: {"sessions": 0, "replies": 0, "words": 0} for t in _TRACKED}
            global_subtype = _empty_subtype()
            arc_subtype    = {}   # show_id → {subtype → {...}}
            for r in rows:
                sid_key   = r["show_id"]
                role_name = r["role_name"]
                if not role_name: continue
                arc_subtype[sid_key] = _empty_subtype()
                sess_rows = db.execute(
                    "SELECT subtype, stats FROM sessions WHERE show_id=? AND participants LIKE ?",
                    (sid_key, f'%{json.dumps(role_name, ensure_ascii=False)}%')
                ).fetchall()
                for s in sess_rows:
                    stype = (s["subtype"] or "私密").strip()
                    if stype not in _TRACKED: continue
                    try:
                        role_st = json.loads(s["stats"] or "{}").get(role_name, {})
                        for dest in (global_subtype[stype], arc_subtype[sid_key][stype]):
                            dest["sessions"] += 1
                            dest["replies"]  += role_st.get("replies", 0)
                            dest["words"]    += role_st.get("words",   0)
                    except Exception:
                        pass
    # blacklist records for this QQ (across all tenants)
    bl_records = []
    if qq:
        bl_rows = db.execute("""
            SELECT b.*, t.display_name AS tenant_display, t.username AS tenant_username
            FROM blacklist b
            JOIN tenants t ON b.tenant_id = t.id
            WHERE b.qq = ?
            ORDER BY b.created_at DESC
        """, (qq,)).fetchall()
        bl_records = [dict(r) for r in bl_rows]

    # top players across all tenants (for browse view, 排除 NPC)
    top = db.execute("""
        SELECT qq, SUM(total_replies) AS replies, SUM(total_words) AS words,
               COUNT(*) AS arc_count, MAX(last_updated) AS last_updated
        FROM players WHERE is_npc=0 GROUP BY qq
        ORDER BY words DESC LIMIT 50
    """).fetchall()
    top = [dict(r) for r in top]
    for r in top:
        r["last_updated_str"] = ts_to_str(r["last_updated"])
    return render_template("superadmin_players.html",
                           qq=qq, rows=rows, summary=summary, top=top,
                           fmt_seconds=fmt_seconds, bl_records=bl_records, ts_to_str=ts_to_str,
                           global_subtype=global_subtype if summary else {},
                           arc_subtype=arc_subtype if summary else {},
                           tracked_subtypes=["私密", "电话", "官约", "心愿"])

@app.route("/superadmin/analysis")
@require_superadmin
def superadmin_analysis():
    qq = request.args.get("qq", "").strip()
    return render_template("superadmin_analysis.html", qq=qq)

@app.route("/superadmin/api/all_players")
@require_superadmin
def superadmin_api_all_players():
    """返回所有有 rp_entries 的玩家列表，供分析页 dropdown 使用。"""
    db = get_db()
    # 按 QQ 聚合，同时返回每个 (role_name, show_name) 配对，避免跨租户同名角色混淆
    rows = db.execute("""
        SELECT p.qq,
               COUNT(DISTINCT e.id)  AS entry_count,
               COUNT(DISTINCT p.show_id) AS show_count,
               GROUP_CONCAT(DISTINCT p.role_name || '|' || COALESCE(sh.name,'?')) AS role_shows
        FROM players p
        JOIN rp_entries e ON e.role_name = p.role_name AND e.show_id = p.show_id
        LEFT JOIN shows sh ON p.show_id = sh.id
        WHERE p.qq != '' AND p.is_npc = 0 AND e.timestamp > 0
        GROUP BY p.qq
        ORDER BY entry_count DESC
    """).fetchall()
    result = []
    for r in rows:
        pairs = []
        seen = set()
        for item in (r["role_shows"] or "").split(","):
            if "|" in item and item not in seen:
                seen.add(item)
                role, show = item.split("|", 1)
                pairs.append({"role": role, "show": show})
        result.append({
            "qq": r["qq"],
            "entry_count": r["entry_count"],
            "show_count": r["show_count"],
            "roles": pairs,
        })
    return jsonify({"ok": True, "players": result})

@app.route("/superadmin/api/player_entries")
@require_superadmin
def superadmin_api_player_entries():
    """返回某 QQ 所有 rp_entries 的 JSON，供前端图表使用。"""
    qq = request.args.get("qq", "").strip()
    if not qq:
        return jsonify({"ok": False, "error": "missing qq"}), 400
    db = get_db()
    # 找到该 QQ 的所有 (role_name, show_id) 配对，跨租户但不跨角色
    player_rows = db.execute(
        "SELECT role_name, show_id FROM players WHERE qq=? AND role_name!=''", (qq,)
    ).fetchall()
    if not player_rows:
        return jsonify({"ok": True, "entries": [], "roles": []})

    # 用 (role_name, show_id) 配对过滤，避免不同租户同名角色串数据
    pairs = [(r["role_name"], r["show_id"]) for r in player_rows]
    role_names = list({r["role_name"] for r in player_rows})

    # 构造 WHERE (e.role_name=? AND e.show_id=?) OR ...
    pair_clauses = " OR ".join(["(e.role_name=? AND e.show_id=?)"] * len(pairs))
    pair_params  = [v for p in pairs for v in p]

    entries = db.execute(
        f"""SELECT e.id, e.session_id, e.role_name, e.seq, e.timestamp,
                   e.reply_time_ms, e.is_excluded,
                   length(e.content) AS char_count,
                   s.subtype, s.game_day, e.show_id,
                   sh.name AS show_name
            FROM rp_entries e
            JOIN sessions s ON e.session_id = s.id
            LEFT JOIN shows sh ON e.show_id = sh.id
            WHERE ({pair_clauses}) AND e.timestamp > 0
            ORDER BY e.timestamp ASC""",
        pair_params
    ).fetchall()
    return jsonify({
        "ok": True,
        "roles": role_names,
        "entries": [dict(e) for e in entries]
    })

@app.route("/superadmin/entry/<int:entry_id>/toggle_exclude", methods=["POST"])
@require_superadmin
def superadmin_toggle_exclude(entry_id):
    db = get_db()
    row = db.execute("SELECT is_excluded FROM rp_entries WHERE id=?", (entry_id,)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "not found"}), 404
    new_val = 0 if row["is_excluded"] else 1
    db.execute("UPDATE rp_entries SET is_excluded=? WHERE id=?", (new_val, entry_id))
    db.commit()
    return jsonify({"ok": True, "is_excluded": new_val})

# ── 预订季度（网页日历）───────────────────────────────────────────────────────
def _infer_schedule_year(start_mmdd, anchor_ms):
    """给只有 MMDD 的档期定开始日所在年份：以「创建/预订时刻」为锚点，开始日落在锚点之前超过 180 天的算明年
    （如 12 月创建、档期 0105 → 明年）。和插件里 getScheduleZone 用 season_created_at 的思路一致。"""
    try:
        anchor = datetime.fromtimestamp(int(anchor_ms) / 1000, TZ_BEIJING).date()
        mm, dd = int(start_mmdd[:2]), int(start_mmdd[2:])
        y = anchor.year
        cand = _date(y, mm, dd)
        if (anchor - cand).days > 180:
            y += 1
        return y
    except (ValueError, TypeError, OSError):
        return 0

def _book_range(row):
    """预订/进行中季度的 (开始日, 结束日, 补戏截止日)，date 对象；数据不全返回 None。
    MMDD 不带年，靠 schedule_year（开始日所在年）定年；结束日早于开始日视为跨年。"""
    y = row["schedule_year"] or 0
    st, en, sp = row["schedule_start"], row["schedule_end"], row["supplement_end"]
    if not y or not st or not en:
        return None
    try:
        d0 = _date(y, int(st[:2]), int(st[2:]))
        d1 = _date(y, int(en[:2]), int(en[2:]))
        if d1 < d0:
            d1 = _date(y + 1, d1.month, d1.day)
        d2 = d1
        if sp:
            d2 = _date(d1.year, int(sp[:2]), int(sp[2:]))
            if d2 < d1:
                d2 = _date(d1.year + 1, d2.month, d2.day)
    except ValueError:
        return None
    return d0, d1, d2

def _parse_ymd(v):
    try:
        return datetime.strptime((v or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None

def _book_fields_from_payload(data):
    """网页表单/接口里的完整日期 → (year, MMDD 三件套, 错误信息)。补戏日可空。"""
    d0, d1 = _parse_ymd(data.get("start")), _parse_ymd(data.get("end"))
    if not d0 or not d1:
        return None, "档期开始/结束日期必填，格式 YYYY-MM-DD"
    if d1 < d0:
        return None, "结束日期不能早于开始日期"
    supp_raw = (data.get("supplement_end") or "").strip()
    d2 = None
    if supp_raw:
        d2 = _parse_ymd(supp_raw)
        if not d2 or d2 < d1:
            return None, "补戏截止日期格式错误，或早于档期结束日"
    if (d1 - d0).days > 366 or (d2 and (d2 - d1).days > 366):
        return None, "档期跨度过长"
    today = datetime.now(TZ_BEIJING).date()
    if (d2 or d1) < today:
        return None, "档期已经过去了，预订只能订今天及以后的日期"
    if d0.year > today.year + 3:
        return None, "档期太远了（最多预订 3 年内）"
    mm = lambda d: f"{d.month:02d}{d.day:02d}"
    return {"year": d0.year, "start": mm(d0), "end": mm(d1), "supp": mm(d2) if d2 else ""}, None

def _book_overlap(db, tid, d0, d1, exclude_id=None):
    """与其它预订/进行中季度的档期区间重叠时，返回那个季度的名字。"""
    rows = db.execute(
        "SELECT * FROM shows WHERE tenant_id=? AND (booked=1 OR is_current=1)", (tid,)).fetchall()
    for r in rows:
        if exclude_id and r["id"] == exclude_id:
            continue
        rng = _book_range(r)
        if rng and d0 <= rng[2] and rng[0] <= d1:
            return r["name"]
    return None

# 预订表单里一起填的四个群号：写进预订季度自己的 site_config，「。开始季度」拉取预配内容时就会带到机器人
BOOK_GROUP_KEYS = [("song_group_id", "戏群"), ("background_group_id", "后台群"),
                   ("adminAnnounceGroupId", "公告群"), ("water_group_id", "水群")]

def _split_npc_names(raw):
    """NPC 名单：一行一个（也认逗号/顿号/空格分隔），去重保序。"""
    out = []
    for n in re.split(r"[\s,，、;；]+", raw or ""):
        n = n.strip()
        if n and n not in out:
            out.append(n)
    return out

def _book_prep_from_payload(db, tid, data):
    """预订表单里的开季准备（群号组 / 四个群号 / NPC 名单）→ (dict, 错误信息)。都可以留空。"""
    set_name = (data.get("group_set") or "").strip()
    if set_name and not db.execute("SELECT 1 FROM known_group_sets WHERE tenant_id=? AND set_name=?",
                                   (tid, set_name)).fetchone():
        return None, f"群号组「{set_name}」不存在，请先到「群号组」页面建好"
    groups = {}
    for key, label in BOOK_GROUP_KEYS:
        v = str(data.get(key) or "").strip()
        if v and not v.isdigit():
            return None, f"{label}群号只能填数字"
        groups[key] = v
    npcs = _split_npc_names(data.get("npc_names"))
    if len(npcs) > 50:
        return None, "NPC 名单最多 50 个"
    if any(len(n) > 20 for n in npcs):
        return None, "NPC 名字太长了（每个最多 20 字）"
    return {"group_set": set_name, "groups": groups, "npc_names": "\n".join(npcs)}, None

def _save_book_prep(db, tid, sid, prep):
    db.execute("UPDATE shows SET group_set=?, npc_names=? WHERE id=?", (prep["group_set"], prep["npc_names"], sid))
    for key, v in prep["groups"].items():
        db.execute(
            "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
            "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
            (sid, tid, key, v))

def _book_prep_defaults(db, tid):
    """新预订的默认值：沿用最近一季的四个群号和群号组，省得每季重填。"""
    last = db.execute("SELECT id, group_set FROM shows WHERE tenant_id=? AND booked=0 ORDER BY id DESC LIMIT 1",
                      (tid,)).fetchone()
    if not last:
        return {"group_set": "", "groups": {k: "" for k, _ in BOOK_GROUP_KEYS}}
    flat = get_flat_config(db, last["id"])
    return {"group_set": last["group_set"] or "", "groups": {k: flat.get(k, "") for k, _ in BOOK_GROUP_KEYS}}

# 预订时「复制配置」不带的键：天数/同步时间戳是运行态；物品注册表走通用库按需挑；
# 待上载队列和 place_keys/battle_attrs/player_skills 是上一季的玩家数据；
# 地点列表和地图（available_places / place_maps）每季重新录入、重新拼，不跟着整套配置走（2026-10-01 用户要求）
_BOOK_COPY_EXCLUDE = frozenset({
    "global_days", "_last_bot_sync",
    "item_registry", "reward_item_registry", "item_registry_pending", "equipment_registry_pending",
    "place_keys", "battle_attrs", "player_skills",
    "available_places", "place_maps",
})

def _book_copy_config(db, tid, sid, src):
    """src: "" 不复制 / "show:<id>" 复制某季配置 / "tpl:<id>" 套配置预设。写库不 commit，返回复制的键数；来源无效返回 None。"""
    if not src:
        return 0
    kind, _, ref = src.partition(":")
    try:
        ref = int(ref)
    except ValueError:
        return None
    if kind == "show":
        if ref == sid or not db.execute("SELECT 1 FROM shows WHERE id=? AND tenant_id=?", (ref, tid)).fetchone():
            return None
        data = get_flat_config(db, ref)
    elif kind == "tpl":
        row = db.execute("SELECT config_data FROM config_templates WHERE id=? AND tenant_id=?", (ref, tid)).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row["config_data"] or "{}")
        except json.JSONDecodeError:
            return None
    else:
        return None
    n = 0
    for k, v in data.items():
        if k in _BOOK_COPY_EXCLUDE:
            continue
        db.execute("INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
                   "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value", (sid, tid, k, v))
        n += 1
    return n

def _pick_booked_show(db, tid, name=None, today=None):
    """「。开始季度」选哪个预订：给了名字按名字；否则按日期——
    今天正落在档期（含补戏期）内的优先，其次是开始日最近的未来预订，最后才是已过期没开的（取最近的）。"""
    today = today or datetime.now(TZ_BEIJING).date()
    rows = db.execute("SELECT * FROM shows WHERE tenant_id=? AND booked=1", (tid,)).fetchall()
    if name:
        hits = [r for r in rows if r["name"] == name] or [r for r in rows if name in r["name"]]
        if len(hits) == 1:
            return hits[0], "name", None
        return None, "name", (f"预订里有多个名字含「{name}」的季度，请写全名" if hits else f"没有名为「{name}」的预订季度")
    inprog, upcoming, overdue = [], [], []
    for r in rows:
        rng = _book_range(r)
        if not rng:
            continue
        if rng[0] <= today <= rng[2]:
            inprog.append((rng[0], r))
        elif rng[0] > today:
            upcoming.append((rng[0], r))
        else:
            overdue.append((rng[0], r))
    if inprog:
        return sorted(inprog, key=lambda x: x[0])[-1][1], "in_schedule", None
    if upcoming:
        return sorted(upcoming, key=lambda x: x[0])[0][1], "upcoming", None
    if overdue:
        return sorted(overdue, key=lambda x: x[0])[-1][1], "overdue", None
    return None, "date", "没有已预订的季度"


@app.route("/api/new_season", methods=["POST"])
def api_new_season():
    # 兼容旧版插件的「。创建新季度」：新版插件已不再调用（季度只在网页日历创建）。
    # 多个群共用本服务，等各群都升级到带「。开始季度」的版本后可以删掉这个接口
    tid  = get_tenant_from_token()
    data = request.json or {}
    name = (data.get("name") or "").strip()
    mode = (data.get("mode") or "review").strip()   # "review" | "no_review"
    if not name:
        return jsonify({"ok": False, "error": "missing name"}), 400

    # 档期字段（MMDD 格式，可选）
    sched_start = (data.get("schedule_start") or "").strip()
    sched_end   = (data.get("schedule_end")   or "").strip()
    supp_end    = (data.get("supplement_end") or "").strip()

    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM shows WHERE tenant_id=?", (tid,)).fetchone()[0]
    if total >= MAX_SHOWS_PER_TENANT:
        return jsonify({"ok": False, "error": f"季度数已达上限（{MAX_SHOWS_PER_TENANT} 个），请先登录后台「季管理」删除不需要的旧季度"}), 400
    # 把已有 is_current=1 的 show 全部关掉（处理 JSCLEAR 未先结束季度的情况），
    # 同时清理这些季度收集的图片，避免因跳过「结束季度」导致图片一直不清
    stale_shows = db.execute("SELECT id FROM shows WHERE tenant_id=? AND is_current=1", (tid,)).fetchall()
    db.execute("UPDATE shows SET is_current=0 WHERE tenant_id=? AND is_current=1", (tid,))
    for stale in stale_shows:
        _cleanup_show_collected_images(db, tid, stale["id"])
    # 建新 show
    token = secrets.token_urlsafe(24)
    db.execute(
        "INSERT INTO shows (tenant_id,name,description,is_current,public_view_enabled,public_token,"
        "created_at,schedule_start,schedule_end,supplement_end,schedule_year) "
        "VALUES (?,?,?,1,1,?,?,?,?,?,?)",
        (tid, name, mode, token, int(time.time() * 1000),
         sched_start, sched_end, supp_end,
         _infer_schedule_year(sched_start, int(time.time() * 1000)) if sched_start else 0)
    )
    db.commit()
    show = db.execute("SELECT id FROM shows WHERE public_token=?", (token,)).fetchone()
    return jsonify({"ok": True, "show_id": show["id"], "name": name, "mode": mode,
                    "schedule_start": sched_start, "schedule_end": sched_end,
                    "supplement_end": supp_end})

@app.route("/api/current_season", methods=["POST"])
def api_current_season():
    """返回该租户当前活跃 show 的信息，供 bot 初始化 season_show_name。"""
    tid = get_tenant_from_token()
    db  = get_db()
    show = db.execute(
        "SELECT * FROM shows WHERE tenant_id=? AND is_current=1", (tid,)
    ).fetchone()
    if not show:
        # 没有 is_current=1，取最新的
        show = db.execute(
            "SELECT * FROM shows WHERE tenant_id=? AND booked=0 ORDER BY id DESC LIMIT 1", (tid,)
        ).fetchone()
    if not show:
        return jsonify({"ok": False, "error": "no show found"}), 404
    mode = show["description"] if show["description"] in ("review", "no_review") else "review"
    return jsonify({"ok": True, "show_id": show["id"], "name": show["name"], "mode": mode,
                    "schedule_start": show["schedule_start"] or "",
                    "schedule_end":   show["schedule_end"]   or "",
                    "supplement_end": show["supplement_end"] or ""})

@app.route("/api/start_season", methods=["POST"])
def api_start_season():
    """Bot 用（。开始季度）：把网页日历里预订的季度转成进行中。不带 name 按今天的日期挑。"""
    tid  = get_tenant_from_token()
    data = request.json or {}
    name = (data.get("name") or "").strip()
    db = get_db()
    def _running_resp():
        run = db.execute("SELECT * FROM shows WHERE tenant_id=? AND is_current=1", (tid,)).fetchone()
        if not run:
            return None
        rmode = run["description"] if run["description"] in ("review", "no_review") else "review"
        return jsonify({"ok": False, "error": f"已有进行中的季度「{run['name']}」，请先结束季度再开始新的",
                        "running": {"name": run["name"], "mode": rmode,
                                    "schedule_start": run["schedule_start"] or "",
                                    "schedule_end": run["schedule_end"] or "",
                                    "supplement_end": run["supplement_end"] or ""}}), 409
    if data.get("sync_only"):
        # 「。开始季度 同步」：上次开季中途断了（服务器已开、机器人本地没记录）时，把服务器上进行中的季度接回本地；绝不启用新的预订
        run = db.execute("SELECT * FROM shows WHERE tenant_id=? AND is_current=1", (tid,)).fetchone()
        if not run:
            return jsonify({"ok": False, "error": "服务器上没有进行中的季度，不需要同步"}), 404
        rmode = run["description"] if run["description"] in ("review", "no_review") else "review"
        return jsonify({"ok": True, "synced": True, "name": run["name"], "mode": rmode,
                        "schedule_start": run["schedule_start"] or "",
                        "schedule_end": run["schedule_end"] or "",
                        "supplement_end": run["supplement_end"] or ""})
    resp = _running_resp()
    if resp:
        return resp
    show, how, err = _pick_booked_show(db, tid, name or None)
    if not show:
        return jsonify({"ok": False, "error": err}), 404
    if how == "overdue" and not name:
        return jsonify({"ok": False, "error": f"没有正在档期内或即将开始的预订；最近的「{show['name']}」档期已经过了，"
                                              f"要开它请带上名字：。开始季度 {show['name']}"}), 404
    # 单条语句里同时确认「没有进行中的季度」和「这条还是预订状态」，避免两个请求同时进来把两个季度都开成进行中
    cur = db.execute(
        "UPDATE shows SET is_current=1, booked=0, public_view_enabled=1 WHERE id=? AND booked=1 AND tenant_id=? "
        "AND NOT EXISTS (SELECT 1 FROM shows WHERE tenant_id=? AND is_current=1)",
        (show["id"], tid, tid))
    if cur.rowcount != 1:
        db.rollback()
        return _running_resp() or (jsonify({"ok": False, "error": "这个预订刚刚被别人处理了，请重试"}), 409)
    db.commit()
    mode = show["description"] if show["description"] in ("review", "no_review") else "review"
    return jsonify({"ok": True, "show_id": show["id"], "name": show["name"], "mode": mode,
                    "matched_by": how,
                    "schedule_start": show["schedule_start"] or "",
                    "schedule_end":   show["schedule_end"]   or "",
                    "supplement_end": show["supplement_end"] or "",
                    "group_set": show["group_set"] or "",
                    "npc_names": _split_npc_names(show["npc_names"])})

@app.route("/api/booked_seasons", methods=["POST"])
def api_booked_seasons():
    """Bot 用：列出预订中的季度（供「。开始季度」无预订/多预订时提示）。"""
    tid = get_tenant_from_token()
    rows = get_db().execute("SELECT * FROM shows WHERE tenant_id=? AND booked=1", (tid,)).fetchall()
    out = []
    for r in rows:
        rng = _book_range(r)
        out.append({"show_id": r["id"], "name": r["name"],
                    "start": rng[0].isoformat() if rng else "", "end": rng[1].isoformat() if rng else ""})
    out.sort(key=lambda x: x["start"])
    return jsonify({"ok": True, "booked": out})

@app.route("/api/update_schedule", methods=["POST"])
def api_update_schedule():
    """Bot 用：更新当前活跃季的档期（Token 鉴权）。"""
    tid  = get_tenant_from_token()
    show = get_current_show_for_tenant(tid)
    if not show:
        return jsonify({"ok": False, "error": "no active season"}), 404
    data  = request.json or {}
    start = (data.get("schedule_start") or "").strip()
    end   = (data.get("schedule_end")   or "").strip()
    supp  = (data.get("supplement_end") or "").strip()
    for v in (start, end, supp):
        if v and (len(v) != 4 or not v.isdigit()):
            return jsonify({"ok": False, "error": f"格式错误：{v}，需为 MMDD 四位数字"}), 400
    db = get_db()
    db.execute(
        "UPDATE shows SET schedule_start=?, schedule_end=?, supplement_end=?, schedule_year=? WHERE id=?",
        (start, end, supp, _infer_schedule_year(start, show["created_at"]) if start else 0, show["id"])
    )
    db.commit()
    return jsonify({"ok": True, "show_id": show["id"],
                    "schedule_start": start, "schedule_end": end, "supplement_end": supp})

@app.route("/api/end_season", methods=["POST"])
def api_end_season():
    tid = get_tenant_from_token()
    db  = get_db()
    show = db.execute(
        "SELECT id, name, public_token FROM shows WHERE tenant_id=? AND is_current=1", (tid,)
    ).fetchone()
    if not show:
        return jsonify({"ok": False, "error": "no active season"}), 404
    db.execute("UPDATE shows SET is_current=0 WHERE id=?", (show["id"],))
    _cleanup_show_collected_images(db, tid, show["id"])
    db.commit()
    base_url = request.host_url.rstrip("/")
    public_url = f"{base_url}/view/{show['public_token']}" if show["public_token"] else base_url
    # 跑 SealDice/LLOneBot 的机器不一定和 rp_archive 是同一台，所以给一个带 token 的下载 URL
    # （/api/show_archive），交给 OneBot 的 download_file 动作去拉，而不是给本地路径。
    zip_token = request.headers.get("X-Archive-Token", "")
    zip_url = f"{base_url}/api/show_archive/{show['id']}?token={zip_token}"

    return jsonify({"ok": True, "show_id": show["id"], "name": show["name"],
                     "public_url": public_url, "zip_url": zip_url})


@app.route("/api/show_archive/<int:sid>")
def api_show_archive(sid):
    """按 show_id 下载存档 ZIP（token 认证，供 OneBot download_file 机器对机器拉取）。"""
    tid = _resolve_archive_token()
    db  = get_db()
    show = db.execute("SELECT id FROM shows WHERE id=? AND tenant_id=?", (sid, tid)).fetchone()
    if not show:
        abort(404)
    buf, safe_name = _build_show_zip(db, sid)
    if buf is None:
        abort(500)
    date_tag = datetime.now(TZ_BEIJING).strftime("%Y%m%d")
    zip_name = f"{safe_name}_存档_{date_tag}.zip"
    return send_file(buf, as_attachment=True, download_name=zip_name, mimetype="application/zip")

_TIME_TITLES = [
    (0,  2,  "零点主播",   "深夜零点还在线，精神可嘉"),
    (2,  4,  "破晓前哨",   "凌晨不眠，最爱在无人的黑夜互动"),
    (4,  6,  "黎明先锋",   "天都没亮就开始活跃，比鸡起得早"),
    (6,  8,  "晨曦使者",   "清晨第一批上线，精力充沛"),
    (8,  10, "上午热线王", "上午就已经电话短信满天飞"),
    (10, 12, "阳光十点半", "上午十点的阳光和你一样活跃"),
    (12, 14, "午间话题人", "饭都不好好吃，忙着互动呢"),
    (14, 16, "下午茶常客", "下午茶时间最爱找人聊"),
    (16, 18, "傍晚漫步者", "放学放工后第一件事就是开始互动"),
    (18, 20, "黄昏浪漫派", "黄昏时分是你最爱发动攻势的时刻"),
    (20, 22, "夜间剧情家", "晚间黄金档，你的互动最密集"),
    (22, 24, "深夜电台长", "深夜还不睡，把私人群当电台在开"),
]

def _get_time_title(hour_counts):
    """传入 {hour: count} 字典，返回 (slot_label, title, tagline)。"""
    if not hour_counts:
        return None
    peak_hour = max(hour_counts, key=lambda h: hour_counts[h])
    for start, end, title, tagline in _TIME_TITLES:
        if start <= peak_hour < end:
            label = f"{start:02d}:00–{end:02d}:00"
            return label, title, tagline
    return None


@app.route("/api/season_report/<int:show_id>", methods=["GET"])
def api_season_report(show_id):
    """Bot 用：拉取指定季度的全员互动统计，用于结束时群发个人报告。"""
    tid = get_tenant_from_token()
    db  = get_db()
    if not db.execute("SELECT id FROM shows WHERE id=? AND tenant_id=?", (show_id, tid)).fetchone():
        return jsonify({"ok": False, "error": "not found"}), 404

    players = {}

    # 场次参与统计 + 找每位玩家字数最多的场次
    session_rows = db.execute(
        "SELECT id, participants, stats FROM sessions WHERE show_id=?", (show_id,)
    ).fetchall()
    for row in session_rows:
        try:
            parts = json.loads(row["participants"] or "[]")
            stats = json.loads(row["stats"] or "{}")
        except Exception:
            parts, stats = [], {}
        for name in parts:
            if not (isinstance(name, str) and name):
                continue
            p = players.setdefault(name, {})
            p["sessions"] = p.get("sessions", 0) + 1
            words = stats.get(name, {}).get("words", 0)
            if words > p.get("_best_words", 0):
                p["_best_words"]   = words
                p["_best_session"] = row["id"]

    # 互动事件统计 + 最活跃时段 + 互动对象计数
    sent_key = {"sms": "sms_sent", "gift": "gift_sent", "lovemail": "lovemail_sent", "direct_letter": "letter_sent"}
    recv_key = {"sms": "sms_recv", "gift": "gift_recv", "lovemail": "lovemail_recv", "direct_letter": "letter_recv"}
    for row in db.execute(
        "SELECT type, from_role, to_role, timestamp FROM extra_events WHERE show_id=?", (show_id,)
    ).fetchall():
        etype = row["type"]
        fr    = (row["from_role"] or "").strip()
        tr    = (row["to_role"]   or "").strip()
        ts    = row["timestamp"] or 0
        if fr and etype in sent_key:
            p = players.setdefault(fr, {})
            p[sent_key[etype]] = p.get(sent_key[etype], 0) + 1
            if ts > 0:
                hour = datetime.fromtimestamp(ts / 1000).hour
                hc   = p.setdefault("_hour_counts", {})
                hc[hour] = hc.get(hour, 0) + 1
            if tr:
                p.setdefault("_sent_to", {}).setdefault(etype, {})
                p["_sent_to"][etype][tr] = p["_sent_to"][etype].get(tr, 0) + 1
        if tr and etype in recv_key:
            p = players.setdefault(tr, {})
            p[recv_key[etype]] = p.get(recv_key[etype], 0) + 1
            if fr:
                p.setdefault("_recv_from", {}).setdefault(etype, {})
                p["_recv_from"][etype][fr] = p["_recv_from"][etype].get(fr, 0) + 1

    # rp_entries 时间戳也计入活跃时段
    for row in db.execute(
        "SELECT role_name, timestamp FROM rp_entries WHERE show_id=? AND timestamp > 0", (show_id,)
    ).fetchall():
        name = (row["role_name"] or "").strip()
        if not name:
            continue
        p    = players.setdefault(name, {})
        hour = datetime.fromtimestamp(row["timestamp"] / 1000).hour
        hc   = p.setdefault("_hour_counts", {})
        hc[hour] = hc.get(hour, 0) + 1

    # 最长场次摘录：取前 4 条 rp_entries（每条截 60 字）
    best_excerpts = {}
    all_best_sids = {p["_best_session"] for p in players.values() if p.get("_best_session")}
    if all_best_sids:
        ph = ",".join("?" * len(all_best_sids))
        entry_rows = db.execute(
            f"SELECT session_id, role_name, content FROM rp_entries "
            f"WHERE show_id=? AND session_id IN ({ph}) ORDER BY session_id, seq",
            [show_id] + list(all_best_sids)
        ).fetchall()
        by_sid = {}
        for e in entry_rows:
            by_sid.setdefault(e["session_id"], []).append((e["role_name"], e["content"] or ""))
        best_excerpts = {sid: lines for sid, lines in by_sid.items()}

    def _top3_partners(counter_dict):
        return sorted(counter_dict.items(), key=lambda x: -x[1])[:3]

    # 计算时段称号、互动对象 Top3，清理内部字段
    for name, p in players.items():
        hc = p.pop("_hour_counts", {})
        tt = _get_time_title(hc)
        if tt:
            p["peak_slot"], p["time_title"], p["time_tagline"] = tt

        sid = p.pop("_best_session", None)
        p.pop("_best_words", None)
        if sid and sid in best_excerpts:
            lines = best_excerpts[sid][:4]
            p["best_excerpt"] = [
                {"role": r, "text": t[:60] + ("…" if len(t) > 60 else "")}
                for r, t in lines
            ]

        sent_to  = p.pop("_sent_to",  {})
        recv_from = p.pop("_recv_from", {})
        if sent_to.get("sms"):
            p["top_sms_sent_to"]   = _top3_partners(sent_to["sms"])
        if recv_from.get("sms"):
            p["top_sms_recv_from"] = _top3_partners(recv_from["sms"])
        if sent_to.get("gift"):
            p["top_gift_sent_to"]   = _top3_partners(sent_to["gift"])
        if recv_from.get("gift"):
            p["top_gift_recv_from"] = _top3_partners(recv_from["gift"])

    return jsonify({
        "ok":     True,
        "players": players,
    })


@app.route("/superadmin/cleanup_empty_sessions", methods=["POST"])
@require_superadmin
def superadmin_cleanup_empty_sessions():
    db = get_db()
    # 找出已结束（end_ts>0）且无任何 rp_entries 的 session。
    # 不复盘季度的场次结束后同样会被标记结束、而它们本来就没有对话记录，必须排除，否则会连统计一起删掉
    rows = db.execute("""
        SELECT s.id FROM sessions s
        WHERE s.end_ts > 0
        AND (SELECT count(*) FROM rp_entries e WHERE e.session_id = s.id) = 0
        AND s.show_id NOT IN (SELECT id FROM shows WHERE description='no_review')
    """).fetchall()
    ids = [r[0] for r in rows]
    if ids:
        ph = ",".join("?" * len(ids))
        db.execute(f"DELETE FROM sessions WHERE id IN ({ph})", ids)
        db.commit()
    return jsonify({"ok": True, "deleted": len(ids), "ids": ids})

@app.route("/superadmin/tenant/new", methods=["POST"])
@require_superadmin
def superadmin_tenant_new():
    username     = request.form.get("username", "").strip()
    view_pw      = request.form.get("view_password", "").strip()
    admin_pw     = request.form.get("admin_password", "").strip()
    display_name = request.form.get("display_name", "").strip()
    if not username or not view_pw or not admin_pw:
        return redirect(url_for("superadmin") + "?error=missing_fields")
    token = secrets.token_urlsafe(24)
    now   = int(time.time() * 1000)
    db    = get_db()
    try:
        db.execute(
            "INSERT INTO tenants (username,view_password_hash,admin_password_hash,api_token,display_name,created_at) "
            "VALUES (?,?,?,?,?,?)",
            (username, generate_password_hash(view_pw), generate_password_hash(admin_pw),
             token, display_name, now)
        )
        db.commit()
        # 自动为新租户创建第一季
        new_tenant = db.execute("SELECT id FROM tenants WHERE username=?", (username,)).fetchone()
        if new_tenant:
            db.execute(
                "INSERT INTO shows (tenant_id,name,is_current,public_view_enabled,public_token,created_at) "
                "VALUES (?,?,1,1,?,?)",
                (new_tenant["id"], "第一季", secrets.token_urlsafe(24), now)
            )
            db.commit()
    except sqlite3.IntegrityError:
        return redirect(url_for("superadmin") + "?error=duplicate")
    return redirect(url_for("superadmin") + "?created=1")

@app.route("/superadmin/tenant/<int:tid>/delete", methods=["POST"])
@require_superadmin
def superadmin_tenant_delete(tid):
    db = get_db()
    for table in ("sessions", "rp_entries", "extra_events", "players", "site_config"):
        db.execute(f"DELETE FROM {table} WHERE tenant_id=?", (tid,))
    shutil.rmtree(os.path.join(COLLECT_IMAGE_DIR, str(tid)), ignore_errors=True)
    db.execute("DELETE FROM collected_images WHERE tenant_id=?", (tid,))
    db.execute("DELETE FROM universal_items WHERE tenant_id=?", (tid,))
    db.execute("DELETE FROM shows   WHERE tenant_id=?", (tid,))
    db.execute("DELETE FROM tenants WHERE id=?",        (tid,))
    db.commit()
    return redirect(url_for("superadmin") + "?deleted=1")

@app.route("/superadmin/tenant/<int:tid>/reset_token", methods=["POST"])
@require_superadmin
def superadmin_tenant_reset_token(tid):
    db = get_db()
    db.execute("UPDATE tenants SET api_token=? WHERE id=?", (secrets.token_urlsafe(24), tid))
    db.commit()
    return redirect(url_for("superadmin") + "?created=1")

@app.route("/superadmin/tenant/<int:tid>/set_password", methods=["POST"])
@require_superadmin
def superadmin_set_password(tid):
    pw_type = request.form.get("pw_type")
    new_pw  = request.form.get("new_password", "").strip()
    if not new_pw or pw_type not in ("view", "admin"):
        return redirect(url_for("superadmin") + "?error=missing_fields")
    col = "view_password_hash" if pw_type == "view" else "admin_password_hash"
    db  = get_db()
    db.execute(f"UPDATE tenants SET {col}=? WHERE id=?", (generate_password_hash(new_pw), tid))
    db.commit()
    return redirect(url_for("superadmin") + "?created=1")

@app.route("/superadmin/tenant/<int:tid>/collected_images")
@require_superadmin
def superadmin_collected_images(tid):
    """超级管理员浏览/删除某租户「我提交」收集来的图片；删除后玩家那边的对应记录
    会在下次「查看收集」时被插件的失效检查顺手清掉（两边没有推送通道，只能靠这个被动同步）。"""
    db     = get_db()
    tenant = db.execute("SELECT * FROM tenants WHERE id=?", (tid,)).fetchone()
    if not tenant:
        abort(404)
    shows = [dict(s) for s in db.execute(
        "SELECT * FROM shows WHERE tenant_id=? ORDER BY created_at DESC", (tid,)
    ).fetchall()]
    show_id = request.args.get("show_id", type=int) or (shows[0]["id"] if shows else None)

    images = []
    if show_id:
        rows = db.execute("""
            SELECT ci.*, p.role_name
            FROM collected_images ci
            LEFT JOIN players p ON p.show_id = ci.show_id AND p.qq = ci.uid
            WHERE ci.tenant_id=? AND ci.show_id=?
            ORDER BY ci.created_at DESC
        """, (tid, show_id)).fetchall()
        base_url = request.host_url.rstrip("/")
        for r in rows:
            d = dict(r)
            d["url"] = f"{base_url}/static/collected_images/{tid}/{d['show_id']}/{d['uid']}/{d['filename']}"
            d["created_at_str"] = ts_to_str(d["created_at"])
            images.append(d)

    return render_template("superadmin_collected_images.html",
                            tenant=dict(tenant), shows=shows, show_id=show_id, images=images)

@app.route("/superadmin/collected_image/<int:img_id>/delete", methods=["POST"])
@require_superadmin
def superadmin_delete_collected_image(img_id):
    db  = get_db()
    row = db.execute("SELECT * FROM collected_images WHERE id=?", (img_id,)).fetchone()
    if row:
        try:
            os.remove(os.path.join(COLLECT_IMAGE_DIR, str(row["tenant_id"]), str(row["show_id"]), row["uid"], row["filename"]))
        except OSError:
            pass
        db.execute("DELETE FROM collected_images WHERE id=?", (img_id,))
        db.commit()
    return redirect(url_for("superadmin_collected_images",
                             tid=request.form.get("tid"), show_id=request.form.get("show_id")))


def _scan_collected_images(db):
    """全局盘点收集图片：按 (租户, 季度) 汇总数据库记录，并对比磁盘找出孤儿文件（磁盘有、数据库没记录）。
    返回 (groups, orphans)。orphans 每项含 tid/show_id/uid/filename/size/相对路径。"""
    tenants = {t["id"]: (t["display_name"] or t["username"]) for t in db.execute("SELECT id, display_name, username FROM tenants")}
    shows   = {s["id"]: dict(s) for s in db.execute("SELECT id, tenant_id, name, is_current FROM shows")}
    rows    = db.execute("SELECT tenant_id, show_id, uid, filename, size_bytes FROM collected_images").fetchall()
    known   = {(r["tenant_id"], r["show_id"], r["uid"], r["filename"]) for r in rows}

    groups = {}
    for r in rows:
        key = (r["tenant_id"], r["show_id"])
        g = groups.setdefault(key, {"tid": r["tenant_id"], "show_id": r["show_id"], "count": 0, "bytes": 0})
        g["count"] += 1
        g["bytes"] += r["size_bytes"]
    for g in groups.values():
        sh = shows.get(g["show_id"])
        g["tenant_name"] = tenants.get(g["tid"], f"租户{g['tid']}（已删除）")
        g["show_name"]   = (sh["name"] or f"场次 {sh['id']}") if sh else f"场次 {g['show_id']}（已删除）"
        g["is_current"]  = bool(sh and sh["is_current"])
        g["show_exists"] = sh is not None

    orphans = []
    if os.path.isdir(COLLECT_IMAGE_DIR):
        for tdir in os.listdir(COLLECT_IMAGE_DIR):
            for sdir in os.listdir(os.path.join(COLLECT_IMAGE_DIR, tdir)) if tdir.isdigit() else []:
                if not sdir.isdigit():
                    continue
                sroot = os.path.join(COLLECT_IMAGE_DIR, tdir, sdir)
                if not os.path.isdir(sroot):
                    continue
                for uid in os.listdir(sroot):
                    udir = os.path.join(sroot, uid)
                    if not os.path.isdir(udir):
                        continue
                    for fn in os.listdir(udir):
                        if (int(tdir), int(sdir), uid, fn) in known:
                            continue
                        try:
                            size = os.path.getsize(os.path.join(udir, fn))
                        except OSError:
                            size = 0
                        orphans.append({"tid": int(tdir), "show_id": int(sdir), "uid": uid,
                                        "filename": fn, "size": size})
    groups = sorted(groups.values(), key=lambda g: (g["is_current"], -g["bytes"]))
    return groups, orphans

@app.route("/superadmin/collected_images_overview")
@require_superadmin
def superadmin_collected_images_overview():
    """全局总览：所有租户、所有季度还留着多少收集图片，以及磁盘上的孤儿文件。"""
    db = get_db()
    groups, orphans = _scan_collected_images(db)
    stale = [g for g in groups if not g["is_current"]]
    return render_template("superadmin_collected_overview.html",
                            groups=groups, orphans=orphans,
                            total_count=sum(g["count"] for g in groups),
                            total_bytes=sum(g["bytes"] for g in groups),
                            stale_count=sum(g["count"] for g in stale),
                            stale_bytes=sum(g["bytes"] for g in stale),
                            orphan_bytes=sum(o["size"] for o in orphans),
                            done=request.args.get("done"))

@app.route("/superadmin/collected_images_overview/cleanup_ended", methods=["POST"])
@require_superadmin
def superadmin_cleanup_ended_images():
    """清理所有「非进行中季度」残留的收集图片（进行中的季度不动）。"""
    db = get_db()
    groups, _ = _scan_collected_images(db)
    n = 0
    for g in groups:
        if not g["is_current"]:
            n += g["count"]
            _cleanup_show_collected_images(db, g["tid"], g["show_id"])
    db.commit()
    return redirect(url_for("superadmin_collected_images_overview", done=f"已清理 {n} 张已结束季度的残留图片"))

@app.route("/superadmin/collected_images_overview/delete_orphans", methods=["POST"])
@require_superadmin
def superadmin_delete_orphan_images():
    """删除磁盘上有、数据库里没有记录的孤儿文件。重新扫描后再删，不信任页面传来的路径。"""
    db = get_db()
    _, orphans = _scan_collected_images(db)
    n = 0
    for o in orphans:
        try:
            os.remove(os.path.join(COLLECT_IMAGE_DIR, str(o["tid"]), str(o["show_id"]), o["uid"], o["filename"]))
            n += 1
        except OSError:
            pass
    return redirect(url_for("superadmin_collected_images_overview", done=f"已删除 {n} 个孤儿文件"))


# ── 季管理路由 ───────────────────────────────────────────────────────────────

@app.route("/admin/shows")
@require_admin
def admin_shows():
    tid   = current_tenant_id()
    db    = get_db()
    shows = [dict(s) for s in db.execute(
        "SELECT * FROM shows WHERE tenant_id=? ORDER BY created_at", (tid,)
    ).fetchall()]
    for s in shows:
        s["session_count"] = db.execute(
            "SELECT COUNT(*) FROM sessions WHERE show_id=?", (s["id"],)
        ).fetchone()[0]
        s["created_at_str"] = ts_to_str(s.get("created_at"))
    return render_template("admin_shows.html", shows=shows,
                           current_view=get_show_id(),
                           msg=request.args.get("msg"))

@app.route("/admin/shows/new", methods=["POST"])
@require_admin
def admin_show_new():
    """旧的「新建季」建出来的是没档期的空壳季度（不进日历、不能「。开始季度」），已并入季度日历的预订。"""
    return redirect(url_for("admin_calendar"))

# ── 通用物品库（跨季度）─────────────────────────────────────────────────────────
_UNI_TYPES = {"currency": "CUR_", "item": "ITM_", "interact": "INT_"}

def _uni_count(db, tid):
    return db.execute("SELECT COUNT(*) FROM universal_items WHERE tenant_id=?", (tid,)).fetchone()[0]

def _uni_clean_entry(raw):
    """入库前清洗：去掉 code（导入时按目标季度重新编号）；只留已知字段。"""
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    typ  = raw.get("type")
    if not name or typ not in _UNI_TYPES:
        return None
    e = {"name": name, "type": typ, "desc": str(raw.get("desc") or "暂无描述")}
    if typ != "currency":
        for k in ("maxUses", "attrs", "canResell", "durability", "price"):
            if k in raw and raw[k] is not None:
                e[k] = raw[k]
    return e

def _load_show_registry(db, tid, sid):
    if not db.execute("SELECT id FROM shows WHERE id=? AND tenant_id=?", (sid, tid)).fetchone():
        return None
    flat = get_flat_config(db, sid)
    for k in ("item_registry", "reward_item_registry"):
        try:
            reg = json.loads(flat.get(k) or "{}")
        except (json.JSONDecodeError, TypeError):
            reg = {}
        if reg:
            return reg
    return {}

def _uni_import(db, tid, sid, reg, ids):
    """把通用库条目加进 sid 的注册表 reg（原地改）：同名跳过、按类型重新编号。写库但不 commit，返回 (added, skipped)。"""
    names = {r.get("name") for r in reg.values() if isinstance(r, dict)}
    added = skipped = 0
    for i in ids:
        try:
            i = int(i)
        except (TypeError, ValueError):
            skipped += 1
            continue
        row = db.execute("SELECT entry_json FROM universal_items WHERE id=? AND tenant_id=?", (i, tid)).fetchone()
        e = json.loads(row["entry_json"]) if row else None
        if not e or e["name"] in names:
            skipped += 1
            continue
        prefix = _UNI_TYPES[e["type"]]
        code = next((prefix + str(d).zfill(3) for d in range(1, 10000) if (prefix + str(d).zfill(3)) not in reg), None)
        if not code:
            skipped += 1
            continue
        reg[code] = {"code": code, **e}
        names.add(e["name"]); added += 1
    if added:
        val = json.dumps(reg, ensure_ascii=False)
        _save_reward_config_key(db, sid, tid, "item_registry", val)
        _save_reward_config_key(db, sid, tid, "reward_item_registry", val)
    return added, skipped

@app.route("/admin/universal")
@require_admin
def admin_universal():
    tid = current_tenant_id()
    db  = get_db()
    items = []
    for r in db.execute("SELECT * FROM universal_items WHERE tenant_id=? ORDER BY type, id", (tid,)).fetchall():
        e = json.loads(r["entry_json"] or "{}")
        e["id"] = r["id"]
        items.append(e)
    shows = [dict(x) for x in db.execute(
        "SELECT id, name, is_current, booked FROM shows WHERE tenant_id=? ORDER BY created_at", (tid,)).fetchall()]
    return render_template("admin_universal.html", items=items, shows=shows,
                           total=len(items), limit=UNIVERSAL_MAX_ITEMS)

@app.route("/admin/universal/add", methods=["POST"])
@require_admin
def admin_universal_add():
    tid = current_tenant_id()
    db  = get_db()
    e = _uni_clean_entry(request.json or {})
    if not e:
        return jsonify({"ok": False, "error": "名称和类型（货币/物品/互动物品）必填"}), 400
    if _uni_count(db, tid) >= UNIVERSAL_MAX_ITEMS:
        return jsonify({"ok": False, "error": f"通用库已满（{UNIVERSAL_MAX_ITEMS} 件），请先删除一些再添加"}), 400
    if db.execute("SELECT 1 FROM universal_items WHERE tenant_id=? AND name=?", (tid, e["name"])).fetchone():
        return jsonify({"ok": False, "error": f"「{e['name']}」已在通用库里"}), 400
    db.execute("INSERT INTO universal_items(tenant_id,name,type,entry_json,created_at) VALUES(?,?,?,?,?)",
               (tid, e["name"], e["type"], json.dumps(e, ensure_ascii=False), int(time.time() * 1000)))
    db.commit()
    return jsonify({"ok": True})

@app.route("/admin/universal/show_items/<int:sid>")
@require_admin
def admin_universal_show_items(sid):
    """某一季注册表里能加入通用库的条目（排除系统预置 SPEC_/CUR_LETTER 和已在库里的同名项）。"""
    tid = current_tenant_id()
    db  = get_db()
    reg = _load_show_registry(db, tid, sid)
    if reg is None:
        abort(404)
    have = {r["name"] for r in db.execute("SELECT name FROM universal_items WHERE tenant_id=?", (tid,)).fetchall()}
    out = []
    for code, r in reg.items():
        if code.startswith("SPEC_") or code == "CUR_LETTER":
            continue
        e = _uni_clean_entry(r)
        if e:
            out.append({"code": code, "name": e["name"], "type": e["type"], "in_library": e["name"] in have})
    return jsonify({"ok": True, "items": out})

@app.route("/admin/universal/from_show", methods=["POST"])
@require_admin
def admin_universal_from_show():
    tid  = current_tenant_id()
    data = request.json or {}
    db   = get_db()
    reg  = _load_show_registry(db, tid, int(data.get("show_id") or 0))
    if reg is None:
        return jsonify({"ok": False, "error": "季度不存在"}), 404
    have = {r["name"] for r in db.execute("SELECT name FROM universal_items WHERE tenant_id=?", (tid,)).fetchall()}
    n = _uni_count(db, tid)
    added = skipped = 0
    for code in data.get("codes") or []:
        e = _uni_clean_entry(reg.get(code))
        if not e or e["name"] in have:
            skipped += 1
            continue
        if n >= UNIVERSAL_MAX_ITEMS:
            db.commit()
            return jsonify({"ok": False, "error": f"通用库已满（{UNIVERSAL_MAX_ITEMS} 件），已加入 {added} 件，其余未加。请先删除一些再继续"}), 400
        db.execute("INSERT INTO universal_items(tenant_id,name,type,entry_json,created_at) VALUES(?,?,?,?,?)",
                   (tid, e["name"], e["type"], json.dumps(e, ensure_ascii=False), int(time.time() * 1000)))
        have.add(e["name"]); n += 1; added += 1
    db.commit()
    return jsonify({"ok": True, "added": added, "skipped": skipped})

@app.route("/admin/universal/import", methods=["POST"])
@require_admin
def admin_universal_import():
    """把通用库里选中的条目加进某一季的注册表：同名跳过，重新分配编号。"""
    tid  = current_tenant_id()
    data = request.json or {}
    db   = get_db()
    sid  = int(data.get("show_id") or 0)
    reg  = _load_show_registry(db, tid, sid)
    if reg is None:
        return jsonify({"ok": False, "error": "季度不存在"}), 404
    added, skipped = _uni_import(db, tid, sid, reg, data.get("ids") or [])
    db.commit()
    return jsonify({"ok": True, "added": added, "skipped": skipped})

@app.route("/admin/universal/<int:uid>/delete", methods=["POST"])
@require_admin
def admin_universal_delete(uid):
    tid = current_tenant_id()
    db  = get_db()
    db.execute("DELETE FROM universal_items WHERE id=? AND tenant_id=?", (uid, tid))
    db.commit()
    return jsonify({"ok": True})

@app.route("/admin/calendar")
@require_admin
def admin_calendar():
    tid = current_tenant_id()
    db  = get_db()
    shows = [dict(x) for x in db.execute(
        "SELECT * FROM shows WHERE tenant_id=? ORDER BY created_at", (tid,)).fetchall()]
    events = []
    for x in shows:
        rng = _book_range(x)
        if not rng:
            continue
        status = "active" if x["is_current"] else ("booked" if x["booked"] else "ended")
        ev = {"id": x["id"], "name": x["name"], "status": status,
              "start": rng[0].isoformat(), "end": rng[1].isoformat(), "supp": rng[2].isoformat(),
              "mode": x["description"] if x["description"] in ("review", "no_review") else "review"}
        if status == "booked":
            flat = get_flat_config(db, x["id"])
            ev.update(group_set=x["group_set"] or "", npc_names=x["npc_names"] or "",
                      groups={k: flat.get(k, "") for k, _ in BOOK_GROUP_KEYS})
        events.append(ev)
    set_names = [r["set_name"] for r in db.execute(
        "SELECT set_name FROM known_group_sets WHERE tenant_id=? ORDER BY created_at", (tid,)).fetchall()]
    return render_template("admin_calendar.html", events=events, total=len(shows),
                           limit=MAX_SHOWS_PER_TENANT, today=datetime.now(TZ_BEIJING).date().isoformat(),
                           unscheduled=[x for x in shows if not _book_range(x)],
                           set_names=set_names, group_keys=BOOK_GROUP_KEYS,
                           prep_defaults=_book_prep_defaults(db, tid),
                           copy_shows=[x for x in shows if not x["booked"]][::-1],
                           copy_tpls=[dict(r) for r in db.execute(
                               "SELECT id, name FROM config_templates WHERE tenant_id=? ORDER BY created_at DESC", (tid,)).fetchall()],
                           uni_items=[dict(r) for r in db.execute(
                               "SELECT id, name, type FROM universal_items WHERE tenant_id=? ORDER BY type, id", (tid,)).fetchall()])

@app.route("/admin/shows/book", methods=["POST"])
@require_admin
def admin_show_book():
    """网页日历预订一个季度：建一条 booked=1 的 show，自带独立配置，开始前不公开。"""
    tid  = current_tenant_id()
    data = request.json or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "季名不能为空"}), 400
    mode = "no_review" if data.get("mode") == "no_review" else "review"
    f, err = _book_fields_from_payload(data)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM shows WHERE tenant_id=?", (tid,)).fetchone()[0]
    if total >= MAX_SHOWS_PER_TENANT:
        return jsonify({"ok": False, "error": f"季度数已满（{MAX_SHOWS_PER_TENANT} 个，预订和已结束的都算），请先到「季管理」删除不需要的旧季度再预订"}), 400
    d0, d1 = _parse_ymd(data["start"]), _parse_ymd(data["end"])
    d2 = _parse_ymd(data.get("supplement_end")) or d1
    clash = _book_overlap(db, tid, d0, d2)
    if clash:
        return jsonify({"ok": False, "error": f"档期和「{clash}」重叠了"}), 400
    prep, err = _book_prep_from_payload(db, tid, data)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    cur = db.execute(
        "INSERT INTO shows (tenant_id,name,description,is_current,booked,public_view_enabled,public_token,"
        "created_at,schedule_start,schedule_end,supplement_end,schedule_year) VALUES (?,?,?,0,1,0,?,?,?,?,?,?)",
        (tid, name, mode, secrets.token_urlsafe(24), int(time.time() * 1000),
         f["start"], f["end"], f["supp"], f["year"]))
    new_id = cur.lastrowid
    copied = _book_copy_config(db, tid, new_id, (data.get("copy_from") or "").strip())
    if copied is None:
        db.rollback()
        return jsonify({"ok": False, "error": "复制来源不存在，请刷新页面重选"}), 400
    _save_book_prep(db, tid, new_id, prep)   # 表单里填的群号以表单为准，覆盖复制来源里的
    added, _ = _uni_import(db, tid, new_id, {}, data.get("universal_ids") or [])
    db.commit()
    return jsonify({"ok": True, "show_id": new_id, "copied": copied, "items_added": added})

@app.route("/admin/shows/<int:sid>/configure", methods=["POST"])
@require_admin
def admin_show_configure(sid):
    """日历「配置此季」：把查看对象切到这个季度，直接进配置页。"""
    tid = current_tenant_id()
    if not get_db().execute("SELECT id FROM shows WHERE id=? AND tenant_id=?", (sid, tid)).fetchone():
        abort(404)
    session["view_show_id"] = sid
    return redirect(url_for("admin_config_page"))

@app.route("/admin/shows/<int:sid>/rebook", methods=["POST"])
@require_admin
def admin_show_rebook(sid):
    """改预订季度的名称/模式/档期。只允许改 booked=1 的。"""
    tid = current_tenant_id()
    db  = get_db()
    row = db.execute("SELECT * FROM shows WHERE id=? AND tenant_id=?", (sid, tid)).fetchone()
    if not row:
        abort(404)
    if not row["booked"]:
        return jsonify({"ok": False, "error": "只能修改还没开始的预订季度"}), 400
    data = request.json or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "季名不能为空"}), 400
    mode = "no_review" if data.get("mode") == "no_review" else "review"
    f, err = _book_fields_from_payload(data)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    d0, d1 = _parse_ymd(data["start"]), _parse_ymd(data["end"])
    d2 = _parse_ymd(data.get("supplement_end")) or d1
    clash = _book_overlap(db, tid, d0, d2, exclude_id=sid)
    if clash:
        return jsonify({"ok": False, "error": f"档期和「{clash}」重叠了"}), 400
    prep, err = _book_prep_from_payload(db, tid, data)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    db.execute(
        "UPDATE shows SET name=?, description=?, schedule_start=?, schedule_end=?, supplement_end=?, schedule_year=? WHERE id=?",
        (name, mode, f["start"], f["end"], f["supp"], f["year"], sid))
    _save_book_prep(db, tid, sid, prep)
    db.commit()
    return jsonify({"ok": True})

@app.route("/admin/shows/<int:sid>/activate", methods=["POST"])
@require_admin
def admin_show_activate(sid):
    """已停用：网页上把季度设为活跃只改服务器，机器人本地没有开季（季名/天数占位/补道具都没做），两边会对不上，
    之后「。开始季度」「。结束季度」都会卡住。季度只在「季度日历」创建，群里用「。开始季度」开；
    已结束的季度不能再重新启用。"""
    tid = current_tenant_id()
    if not get_db().execute("SELECT id FROM shows WHERE id=? AND tenant_id=?", (sid, tid)).fetchone():
        abort(404)
    err = "网页上不能设为活跃：预订的季度请在群里发「。开始季度」，已结束的季度不能重新启用"
    if request.headers.get("X-Fetch") == "1":
        return jsonify({"ok": False, "error": err})
    return redirect(url_for("admin_shows") + "?msg=activate_disabled")

@app.route("/admin/shows/<int:sid>/view", methods=["POST"])
@require_admin
def admin_show_view(sid):
    """切换管理员当前查看的季。"""
    tid = current_tenant_id()
    if not get_db().execute("SELECT id FROM shows WHERE id=? AND tenant_id=?", (sid, tid)).fetchone():
        abort(404)
    session["view_show_id"] = sid
    return redirect(url_for("home"))

@app.route("/admin/shows/<int:sid>/toggle_public", methods=["POST"])
@require_admin
def admin_show_toggle_public(sid):
    tid = current_tenant_id()
    db  = get_db()
    row = db.execute("SELECT * FROM shows WHERE id=? AND tenant_id=?", (sid, tid)).fetchone()
    if not row:
        abort(404)
    new_state = 0 if row["public_view_enabled"] else 1
    db.execute("UPDATE shows SET public_view_enabled=? WHERE id=?", (new_state, sid))
    db.commit()
    if request.headers.get("X-Fetch") == "1":
        return jsonify({"ok": True, "enabled": bool(new_state)})
    return redirect(url_for("admin_shows"))

@app.route("/admin/shows/<int:sid>/schedule", methods=["POST"])
@require_admin
def admin_show_schedule(sid):
    """更新该季的档期设置。"""
    tid = current_tenant_id()
    db  = get_db()
    row = db.execute("SELECT * FROM shows WHERE id=? AND tenant_id=?", (sid, tid)).fetchone()
    if not row:
        abort(404)
    if row["booked"]:
        return jsonify({"ok": False, "error": "预订中的季度请在「季度日历」里改期（要带年份）"}), 400
    data = request.json or {}
    start = (data.get("schedule_start") or "").strip()
    end   = (data.get("schedule_end")   or "").strip()
    supp  = (data.get("supplement_end") or "").strip()
    # 简单格式校验：空串或 4 位数字
    for v in (start, end, supp):
        if v and (len(v) != 4 or not v.isdigit()):
            return jsonify({"ok": False, "error": f"格式错误：{v}，需为 MMDD 四位数字"}), 400
    db.execute(
        "UPDATE shows SET schedule_start=?, schedule_end=?, supplement_end=?, schedule_year=? WHERE id=?",
        (start, end, supp, _infer_schedule_year(start, row["created_at"]) if start else 0, sid)
    )
    db.commit()
    return jsonify({"ok": True})

@app.route("/admin/shows/<int:sid>/reset_token", methods=["POST"])
@require_admin
def admin_show_reset_token(sid):
    tid = current_tenant_id()
    db  = get_db()
    if not db.execute("SELECT id FROM shows WHERE id=? AND tenant_id=?", (sid, tid)).fetchone():
        abort(404)
    db.execute("UPDATE shows SET public_token=? WHERE id=?", (secrets.token_urlsafe(24), sid))
    db.commit()
    return redirect(url_for("admin_shows"))

@app.route("/admin/shows/<int:sid>/delete", methods=["POST"])
@require_admin
def admin_show_delete(sid):
    tid = current_tenant_id()
    db  = get_db()
    row = db.execute("SELECT * FROM shows WHERE id=? AND tenant_id=?", (sid, tid)).fetchone()
    if not row:
        abort(404)
    if row["is_current"]:
        if request.headers.get("X-Fetch") == "1":
            return jsonify({"ok": False, "error": "cannot_delete_current"})
        return redirect(url_for("admin_shows") + "?msg=cannot_delete_current")
    for table in ("sessions", "rp_entries", "extra_events", "players", "site_config",
                  "config_history", "reward_records"):
        db.execute(f"DELETE FROM {table} WHERE show_id=?", (sid,))
    _cleanup_show_collected_images(db, tid, sid)   # 之前漏了这步，删季度后收集图片会残留在磁盘
    db.execute("DELETE FROM shows WHERE id=?", (sid,))
    db.commit()
    if session.get("view_show_id") == sid:
        session.pop("view_show_id", None)
    if request.headers.get("X-Fetch") == "1":
        return jsonify({"ok": True})
    return redirect(url_for("admin_shows") + "?msg=deleted")


def _build_show_zip(db, sid):
    """生成指定 show 的存档 ZIP，返回 (BytesIO, show_name_safe)。"""
    show = db.execute("SELECT * FROM shows WHERE id=?", (sid,)).fetchone()
    if not show:
        return None, None
    show = dict(show)

    flat      = get_flat_config(db, sid)
    show_name = flat.get("love_show_name") or show["name"] or "存档"
    rest_pair = _get_rest_pair(db, sid)
    _type_labels = {k: v for k in ("私密", "电话", "官约", "微信", "心愿")
                    if (v := flat.get(f"custom_type_labels__{k}", "").strip())}

    def _type_label(subtype):
        return _type_labels.get(subtype) or subtype or "私密"

    def _fsafe(s):
        return (s or "").replace("/", "_").replace("\\", "_").replace(":", "_").strip() or "未知"

    from itertools import groupby as _groupby

    sessions = [_enrich_session(dict(s), rest_pair) for s in
                db.execute("SELECT * FROM sessions WHERE show_id=? ORDER BY start_ts", (sid,)).fetchall()]

    sms_by_day_role = {}
    for ev in _parse_events(db.execute(
        "SELECT * FROM extra_events WHERE show_id=? AND type='sms' ORDER BY timestamp", (sid,)
    ).fetchall()):
        key = (_fsafe(ev.get("game_day") or "未归档"), _fsafe(ev.get("from_role") or "未知"))
        sms_by_day_role.setdefault(key, []).append(ev)

    # 心动信/礼物/信件：收集没有 session_id 的（有 session_id 的已附在各场次文件内），按发件人分文件
    nonsession_by_day_type_role = {}
    for ev in _parse_events(db.execute(
        "SELECT * FROM extra_events WHERE show_id=? AND (session_id IS NULL OR session_id='') AND type != 'sms' ORDER BY timestamp",
        (sid,)
    ).fetchall()):
        day  = _fsafe(ev.get("game_day") or "未归档")
        etype = ev.get("type") or "其他"
        role = _fsafe(ev.get("from_role") or "未知")
        nonsession_by_day_type_role.setdefault((day, etype, role), []).append(ev)

    _etype_names = {"lovemail": "心动信", "gift": "礼物", "direct_letter": "信件"}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        players = db.execute(
            "SELECT role_name, total_replies, total_words FROM players WHERE show_id=? AND is_npc=0 ORDER BY total_words DESC",
            (sid,)
        ).fetchall()
        info_lines = [
            f"【 {show_name} · 存档 】",
            f"模式：{show['description'] or '—'}",
            f"创建时间：{ts_to_str(show.get('created_at') or 0)}",
            f"场次数：{len(sessions)}",
            f"玩家数：{len(players)}",
            "",
            "── 玩家统计 ──",
        ]
        for p in players:
            r, w = p["total_replies"] or 0, p["total_words"] or 0
            info_lines.append(f"{p['role_name']}：{r} 回复 · {w} 字 · 均 {w//r if r else 0} 字/回")
        zf.writestr("弧概览.txt", "\n".join(info_lines))

        fname_count = {}
        for sess in sessions:
            gd      = _fsafe(sess.get("game_day") or "未归档")
            subtype = _fsafe(sess.get("subtype") or "")
            gtime   = _fsafe(sess.get("game_time") or "")
            place   = _fsafe(sess.get("place") or "")
            parts   = sess.get("participants") or []
            people  = _fsafe("×".join(parts)) if parts else ""
            fname_parts = [p for p in [subtype, gtime, place, people] if p]
            base   = "_".join(fname_parts) if fname_parts else "场次"
            key    = (gd, base)
            fname_count[key] = fname_count.get(key, 0) + 1
            suffix = f"_{fname_count[key]}" if fname_count[key] > 1 else ""

            rp = db.execute(
                "SELECT * FROM rp_entries WHERE session_id=? AND show_id=? ORDER BY seq,timestamp",
                (str(sess["id"]), sid)
            ).fetchall()
            non_sms = _parse_events(db.execute(
                "SELECT * FROM extra_events WHERE session_id=? AND show_id=? AND type != 'sms' ORDER BY timestamp",
                (str(sess["id"]), sid)
            ).fetchall())

            lines = [
                "=" * 40,
                f"【 {show_name} · {sess.get('game_day','')} {sess.get('place') or ''} 】",
                "=" * 40,
                f"地点：{sess.get('place') or '未记录'}",
                f"时间段：{sess.get('game_time') or '—'}",
                f"类型：{_type_label(sess.get('subtype') or '私密')}{'  【强结】' if sess.get('forced') else ''}",
                f"开始：{sess.get('start_str','')}  结束：{sess.get('end_str') or '—'}",
                f"参与者：{', '.join(sess.get('participants') or [])}",
                "",
                "【统计】",
                f"总回复：{sess.get('total_replies',0)}  总字数：{sess.get('total_words',0)}",
            ]
            for role, st in (sess.get("stats") or {}).items():
                r2, w2 = st.get("replies", 0), st.get("words", 0)
                lines.append(f"{role}：{r2} 回复 · {w2} 字 · 均 {w2//r2 if r2 else 0} 字/回")
            lines += ["", "=" * 40, "【 RP 正文 】", "=" * 40, ""]
            for e in rp:
                e = dict(e)
                lines += [f"▷ {e.get('role_name','')}  {ts_to_str(e.get('timestamp',0))}", "─" * 20, e.get("content",""), ""]

            if non_sms:
                lines += ["", "=" * 40, "【 互动事件 】", "=" * 40]
                non_sms.sort(key=lambda x: x.get("type", ""))
                for etype, grp in _groupby(non_sms, key=lambda x: x.get("type", "")):
                    lines.append(f"\n── {_etype_names.get(etype, etype)} ──")
                    for ev in grp:
                        lines.append(f"{ev.get('from_role','')} → {ev.get('to_role','')}")
                        if ev.get("content"):
                            lines.append(ev["content"])

            zf.writestr(f"{gd}/{base}{suffix}.txt", "\n".join(lines))

        for (day, role), evs in sorted(sms_by_day_role.items()):
            lines = [f"【 {show_name} · {day} · {role} 短信 】", ""]
            for ev in evs:
                t_str = ts_to_str(ev.get("timestamp", 0)) if ev.get("timestamp") else "—"
                lines.append(f"{t_str}  → {ev.get('to_role','')}")
                if ev.get("content"):
                    lines.append(ev["content"])
                lines.append("")
            zf.writestr(f"{day}/短信_{role}.txt", "\n".join(lines))

        for (day, etype, role), evs in sorted(nonsession_by_day_type_role.items()):
            label = _etype_names.get(etype, etype)
            lines = [f"【 {show_name} · {day} · {role} {label} 】", ""]
            for ev in evs:
                t_str = ts_to_str(ev.get("timestamp", 0)) if ev.get("timestamp") else "—"
                lines.append(f"{t_str}  {ev.get('from_role','')} → {ev.get('to_role','')}")
                if ev.get("content"):
                    lines.append(ev["content"])
                lines.append("")
            zf.writestr(f"{day}/{label}-{role}.txt", "\n".join(lines))

    buf.seek(0)
    return buf, _fsafe(show_name)


@app.route("/admin/shows/<int:sid>/download_zip")
@require_admin
def admin_show_download_zip(sid):
    try:
        tid = current_tenant_id()
        db  = get_db()
        if not db.execute("SELECT id FROM shows WHERE id=? AND tenant_id=?", (sid, tid)).fetchone():
            abort(404)
        buf, safe_name = _build_show_zip(db, sid)
        if buf is None:
            abort(404)
        date_tag = datetime.now(TZ_BEIJING).strftime("%Y%m%d")
        zip_name = f"{safe_name}_存档_{date_tag}.zip"
        return send_file(buf, as_attachment=True, download_name=zip_name, mimetype="application/zip")
    except Exception:
        import traceback
        return f"<pre>ZIP 生成失败:\n{traceback.format_exc()}</pre>", 500


def _resolve_archive_token():
    """同时接受 header 和 query param 的 token 认证，返回 tenant_id。"""
    token = request.headers.get("X-Archive-Token", "") or request.args.get("token", "")
    if not token:
        abort(403)
    row = get_db().execute("SELECT id FROM tenants WHERE api_token=?", (token,)).fetchone()
    if not row:
        abort(403)
    return row["id"]


def _current_show_zip(tid):
    """按需生成当前弧的 ZIP，返回 (BytesIO, zip_name)。"""
    db = get_db()
    show_row = db.execute(
        "SELECT id FROM shows WHERE tenant_id=? AND is_current=1", (tid,)
    ).fetchone()
    if not show_row:
        show_row = db.execute(
            "SELECT id FROM shows WHERE tenant_id=? AND booked=0 ORDER BY id DESC LIMIT 1", (tid,)
        ).fetchone()
    if not show_row:
        abort(404)
    buf, safe_name = _build_show_zip(db, show_row["id"])
    if buf is None:
        abort(500)
    date_tag = datetime.now(TZ_BEIJING).strftime("%Y%m%d")
    zip_name = f"{safe_name}_存档_{date_tag}.zip"
    return buf, zip_name


@app.route("/api/latest_archive_info", methods=["GET"])
def api_latest_archive_info():
    """返回当前弧存档的文件名（按需生成）。"""
    tid = _resolve_archive_token()
    try:
        _, zip_name = _current_show_zip(tid)
        return jsonify({"ok": True, "name": zip_name})
    except Exception:
        return jsonify({"ok": False, "error": "生成失败"}), 500


@app.route("/api/latest_archive", methods=["GET"])
def api_latest_archive():
    """返回当前弧存档 ZIP（按需生成；支持 header 或 ?token= 认证）。"""
    tid = _resolve_archive_token()
    buf, zip_name = _current_show_zip(tid)
    return send_file(buf, as_attachment=True, download_name=zip_name, mimetype="application/zip")



@app.route("/superadmin/shows/<int:sid>/toggle_public", methods=["POST"])
@require_superadmin
def superadmin_show_toggle_public(sid):
    db  = get_db()
    row = db.execute("SELECT * FROM shows WHERE id=?", (sid,)).fetchone()
    if not row:
        abort(404)
    new_state = 0 if row["public_view_enabled"] else 1
    db.execute("UPDATE shows SET public_view_enabled=? WHERE id=?", (new_state, sid))
    db.commit()
    return redirect(url_for("superadmin") + f"#tenant-{row['tenant_id']}")


@app.route("/superadmin/shows/<int:sid>/reset_token", methods=["POST"])
@require_superadmin
def superadmin_show_reset_token(sid):
    db  = get_db()
    row = db.execute("SELECT * FROM shows WHERE id=?", (sid,)).fetchone()
    if not row:
        abort(404)
    db.execute("UPDATE shows SET public_token=? WHERE id=?", (secrets.token_urlsafe(24), sid))
    db.commit()
    return redirect(url_for("superadmin") + f"#tenant-{row['tenant_id']}")


# ── 配置路由 ─────────────────────────────────────────────────────────────────

def _parse_routing_text(text):
    import re
    pairs = re.findall(r'(D\d+)[：:]\s*(\d+)', text or "", re.IGNORECASE)
    return json.dumps({k.upper(): v for k, v in pairs}, ensure_ascii=False)

def _routing_to_display(json_str):
    try:
        m = json.loads(json_str or "{}")
        return " ".join(f"{k}:{v}" for k, v in sorted(m.items()))
    except Exception:
        return ""

@app.route("/admin/config", methods=["GET", "POST"])
@require_admin
def admin_config_page():
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()
    if request.method == "POST":
        new_flat = {}
        old_flat = get_flat_config(db, sid)
        for sec in CONFIG_SCHEMA:
            for f in sec["fields"]:
                db_key = _cfg_db_key(sec, f["key"])
                # hidden 字段（如旧的 custom_type_labels__私密）在页面上没有对应输入框，
                # 表单里永远不会带这个 key——不能按"没填=默认值"处理，那样每次保存任何配置都会把
                # 历史值冲成空字符串。跳过整条，数据库里原有值保持不动，原样透传给拉取全部。
                if f.get("hidden") and db_key not in request.form:
                    continue
                if f["type"] == "bool":
                    value = "true" if request.form.get(db_key) else "false"
                elif f["type"] == "routing":
                    value = _parse_routing_text(request.form.get(db_key, ""))
                else:
                    value = _strip_json_str(request.form.get(db_key, str(f["default"])))
                if f.get("opt_in") and db_key not in old_flat and value == str(f["default"]):
                    continue
                new_flat[db_key] = value
        # 保存物品注册表与属性定义（JSON blob，不经过 CONFIG_SCHEMA）
        for blob_key in ("item_registry", "rpg_attr_defs", "sys_attr_presets",
                         "end_game_draw_config",
                         "item_registry_pending", "custom_message_templates",
                         "private_appointment_aliases", "sms_aliases", "gift_aliases",
                         "equipment_registry", "equipment_registry_pending",
                         "equipment_slots", "equipment_slot_names",
                         "private_resources"):
            raw = request.form.get(blob_key, "")
            if raw:
                try:
                    json.loads(raw)
                    new_flat[blob_key] = raw
                except json.JSONDecodeError:
                    pass
        # 快照到 config_history
        operator = (session.get("tenant_display_name") or
                    session.get("tenant_username") or "unknown")
        db.execute(
            "INSERT INTO config_history(show_id,tenant_id,config_data,operator,created_at) VALUES(?,?,?,?,?)",
            (sid, tid, json.dumps(new_flat, ensure_ascii=False), operator, int(time.time() * 1000))
        )
        # 写入 site_config（live 存储）
        for db_key, value in new_flat.items():
            db.execute(
                "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
                "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
                (sid, tid, db_key, value)
            )
        db.commit()
        if request.headers.get("X-Fetch") == "1":
            return jsonify({"ok": True})
        return redirect(url_for("admin_config_page") + "?saved=1")
    flat = get_flat_config(db, sid)
    routing_display = {}
    for sec in CONFIG_SCHEMA:
        for f in sec["fields"]:
            if f["type"] == "routing":
                db_key = _cfg_db_key(sec, f["key"])
                routing_display[db_key] = _routing_to_display(flat.get(db_key, ""))
    last_sync_ts = flat.get("_last_bot_sync")
    last_sync = ts_to_str(int(last_sync_ts)) if last_sync_ts else None
    item_registry_json       = flat.get("item_registry", "{}")
    attr_defs_json           = flat.get("rpg_attr_defs", "{}")
    pool_defs_json           = flat.get("pool_definitions", "{}")
    item_pending_json        = flat.get("item_registry_pending", "[]")
    aliases_json             = flat.get("private_appointment_aliases", "[]")
    sms_aliases_json         = flat.get("sms_aliases", "[]")
    gift_aliases_json        = flat.get("gift_aliases", "[]")
    equip_registry_json      = flat.get("equipment_registry", "{}")
    equip_pending_json       = flat.get("equipment_registry_pending", "[]")
    equip_slots_json         = flat.get("equipment_slots", '["head","chest","hand","leg","foot"]')
    equip_slot_names_json    = flat.get("equipment_slot_names", "{}")
    # 默认资源固定用 "私密" 这个稳定 ID（不随改名变化，机器人那边也是这么存的，改了这里就对不上了）
    private_resources_json   = flat.get("private_resources") or json.dumps(
        {"私密": {"name": "私约", "isDefault": True}}, ensure_ascii=False)
    tpl_rows = db.execute(
        "SELECT id, name, config_data, created_at FROM config_templates "
        "WHERE tenant_id=? ORDER BY created_at DESC",
        (tid,)
    ).fetchall()
    cfg_templates = [
        {"id": r["id"], "name": r["name"],
         "data": json.loads(r["config_data"]),
         "time_str": ts_to_str(r["created_at"])}
        for r in tpl_rows
    ]
    return render_template("admin_config.html", schema=CONFIG_SCHEMA,
                           flat=flat, routing_display=routing_display,
                           saved=request.args.get("saved"), last_sync=last_sync,
                           item_registry_json=item_registry_json,
                           attr_defs_json=attr_defs_json,
                           pool_defs_json=pool_defs_json,
                           item_pending_json=item_pending_json,
                           aliases_json=aliases_json,
                           sms_aliases_json=sms_aliases_json,
                           gift_aliases_json=gift_aliases_json,
                           equip_registry_json=equip_registry_json,
                           equip_pending_json=equip_pending_json,
                           equip_slots_json=equip_slots_json,
                           equip_slot_names_json=equip_slot_names_json,
                           private_resources_json=private_resources_json,
                           cfg_templates=cfg_templates,
                           tpl_msg=request.args.get("tpl_msg"),
                           tpl_max=_TEMPLATE_MAX)


# ── 配置历史路由 ─────────────────────────────────────────────────────────────

@app.route("/admin/config/history")
@require_admin
def admin_config_history():
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()
    rows = db.execute(
        "SELECT id, config_data, operator, created_at FROM config_history "
        "WHERE show_id=? ORDER BY created_at DESC LIMIT 50",
        (sid,)
    ).fetchall()
    # 提取每条快照的摘要字段供展示
    entries = []
    for r in rows:
        try:
            flat = json.loads(r["config_data"])
        except Exception:
            flat = {}
        entries.append({
            "id":         r["id"],
            "operator":   r["operator"],
            "created_at": r["created_at"],
            "time_str":   ts_to_str(r["created_at"]),
            "show_name":  flat.get("love_show_name", ""),
            "days":       flat.get("global_days", ""),
            "key_count":  len(flat),
        })
    return render_template("admin_config_history.html", entries=entries)


@app.route("/admin/config/history/<int:hid>/rollback", methods=["POST"])
@require_admin
def admin_config_rollback(hid):
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()
    row = db.execute(
        "SELECT config_data FROM config_history WHERE id=? AND show_id=?",
        (hid, sid)
    ).fetchone()
    if not row:
        abort(404)
    try:
        flat = json.loads(row["config_data"])
    except Exception:
        abort(400)
    # 写回 site_config
    for db_key, value in flat.items():
        db.execute(
            "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
            "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
            (sid, tid, db_key, value)
        )
    # 把这次回滚也记一条快照
    operator = (session.get("tenant_display_name") or
                session.get("tenant_username") or "unknown")
    db.execute(
        "INSERT INTO config_history(show_id,tenant_id,config_data,operator,created_at) VALUES(?,?,?,?,?)",
        (sid, tid, row["config_data"], f"{operator} [回滚自 #{hid}]", int(time.time() * 1000))
    )
    db.commit()
    if request.headers.get("X-Fetch") == "1":
        return jsonify({"ok": True})
    return redirect(url_for("admin_config_history") + "?rolled=1")


# ── 配置预设路由 ─────────────────────────────────────────────────────────────

_TEMPLATE_EXCLUDE_KEYS = frozenset({
    "item_registry", "item_registry_pending",
    "rpg_attr_defs", "sys_attr_presets",
    "end_game_bonus_templates", "end_game_draw_config",
    "_last_bot_sync",
})
_TEMPLATE_MAX = 5


@app.route("/admin/config/templates/save", methods=["POST"])
@require_admin
def admin_config_template_save():
    tid  = current_tenant_id()
    sid  = get_show_id()
    name = request.form.get("name", "").strip()
    if not name:
        return redirect(url_for("admin_config_page") + "?tpl_msg=empty_name")
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM config_templates WHERE tenant_id=?", (tid,)).fetchone()[0] >= _TEMPLATE_MAX:
        return redirect(url_for("admin_config_page") + "?tpl_msg=limit")
    flat = get_flat_config(db, sid)
    data = {k: v for k, v in flat.items() if k not in _TEMPLATE_EXCLUDE_KEYS}
    db.execute(
        "INSERT INTO config_templates(tenant_id,name,config_data,created_at) VALUES(?,?,?,?)",
        (tid, name, json.dumps(data, ensure_ascii=False), int(time.time() * 1000))
    )
    db.commit()
    return redirect(url_for("admin_config_page") + "?tpl_msg=saved")


@app.route("/admin/config/templates/<int:tplid>/delete", methods=["POST"])
@require_admin
def admin_config_template_delete(tplid):
    tid = current_tenant_id()
    db  = get_db()
    db.execute("DELETE FROM config_templates WHERE id=? AND tenant_id=?", (tplid, tid))
    db.commit()
    if request.headers.get("X-Fetch") == "1":
        return jsonify({"ok": True})
    return redirect(url_for("admin_config_page") + "?tpl_msg=deleted")


# ── 数据浏览路由 ─────────────────────────────────────────────────────────────

@app.route("/")
def home():
    if not session.get("tenant_id"):
        return render_template("landing.html")
    sid  = get_show_id()
    db   = get_db()
    rows = db.execute("""
        SELECT game_day, COUNT(*) AS session_count,
               SUM(total_replies) AS total_replies, SUM(total_words) AS total_words,
               MIN(start_ts) AS first_ts
        FROM sessions WHERE show_id=?
        GROUP BY game_day ORDER BY first_ts DESC
    """, (sid,)).fetchall()
    days, incomplete = [], []
    for r in rows:
        d = dict(r)
        d["first_date"] = ts_to_str(d["first_ts"])
        (days if (d["game_day"] or "").strip() else incomplete).append(d)
    return render_template("home.html", days=days, incomplete=incomplete)

@app.route("/date/<game_day>")
@require_login
def date_view(game_day):
    sid  = get_show_id()
    db   = get_db()
    rows = db.execute(
        "SELECT * FROM sessions WHERE show_id=? AND game_day=? ORDER BY start_ts DESC", (sid, game_day)
    ).fetchall()
    show_names = get_show_names(db, sid)
    return render_template("date.html", game_day=game_day,
                           sessions=_enrich_sessions(rows, _get_rest_pair(db, sid)), show_names=show_names)

@app.route("/session/<path:session_id>")
@require_login
def session_view(session_id):
    sid  = get_show_id()
    db   = get_db()
    sess = db.execute("SELECT * FROM sessions WHERE id=? AND show_id=?", (session_id, sid)).fetchone()
    if not sess:
        abort(404)
    sess       = _enrich_session(dict(sess), _get_rest_pair(db, sid))
    rp         = db.execute("SELECT * FROM rp_entries WHERE session_id=? AND show_id=? ORDER BY seq,timestamp", (session_id, sid)).fetchall()
    events     = _parse_events(db.execute("SELECT * FROM extra_events WHERE session_id=? AND show_id=? ORDER BY timestamp", (session_id, sid)).fetchall())
    show_names = get_show_names(db, sid)
    is_admin = bool(session.get("admin_logged_in"))
    return render_template("session.html", sess=sess, rp=rp, events=events,
                           show_names=show_names, ts_to_str=ts_to_str,
                           is_admin=is_admin)

@app.route("/session/<path:session_id>/download")
@require_login
def session_download(session_id):
    sid  = get_show_id()
    db   = get_db()
    sess = db.execute("SELECT * FROM sessions WHERE id=? AND show_id=?", (session_id, sid)).fetchone()
    if not sess:
        abort(404)
    flat      = get_flat_config(db, sid)
    sess      = _enrich_session(dict(sess), _parse_rest_hours(flat.get("rest_hours", "")))
    show_name = flat.get("love_show_name") or "长日将尽"
    _tlabels  = {k: v for k in ("私密", "电话", "官约", "微信", "心愿")
                 if (v := flat.get(f"custom_type_labels__{k}", "").strip())}
    def _tlabel(s): return _tlabels.get(s) or s or "私密"
    rp        = db.execute("SELECT * FROM rp_entries WHERE session_id=? AND show_id=? ORDER BY seq,timestamp", (session_id, sid)).fetchall()
    events    = _parse_events(db.execute("SELECT * FROM extra_events WHERE session_id=? AND show_id=? ORDER BY timestamp", (session_id, sid)).fetchall())

    lines = ["=" * 40, f"【 {show_name} · {sess.get('game_day','')} 场次存档 】", "=" * 40]
    lines += [f"地点：{sess.get('place') or '未记录'}", f"时间段：{sess.get('game_time') or '—'}",
              f"类型：{_tlabel(sess.get('subtype') or '私密')}{'  【强结】' if sess.get('forced') else ''}",
              f"开始：{sess.get('start_str','')}  结束：{sess.get('end_str') or '—'}",
              f"参与者：{', '.join(sess.get('participants') or [])}", "", "【统计】",
              f"总回复：{sess.get('total_replies',0)}  总字数：{sess.get('total_words',0)}"]
    for role, st in (sess.get("stats") or {}).items():
        r2, w2 = st.get("replies", 0), st.get("words", 0)
        lines.append(f"{role}：{r2}回复 · {w2}字 · 均{w2//r2 if r2 else 0}字/回")
    lines += ["", "=" * 40, "【 RP 正文 】", "=" * 40, ""]
    for e in rp:
        e = dict(e)
        lines += [f"▷ {e.get('role_name','')}  {ts_to_str(e.get('timestamp',0))}", "─" * 20, e.get("content",""), ""]
    lines += ["=" * 40, "【 事件记录 】", "=" * 40]
    if events:
        from itertools import groupby
        events.sort(key=lambda x: x.get("type",""))
        for etype, grp in groupby(events, key=lambda x: x.get("type","")):
            _etype_names = {'lovemail':'心动信','sms':'短信','gift':'礼物'}
            lines.append(f"\n── {_etype_names.get(etype,etype)} ──")
            for ev in grp:
                lines.append(f"{ev.get('from_role','')} → {ev.get('to_role','')}")
                if ev.get("content"): lines.append(ev["content"])
    else:
        lines.append("（本场无记录）")

    buf      = io.BytesIO("\n".join(lines).encode("utf-8"))
    buf.seek(0)
    place    = (sess.get("place") or "场次").replace("/","_").replace("\\","_")
    filename = f"{(sess.get('game_day') or 'unknown').replace('/','_')}_{place}_{str(session_id)[:8]}.txt"
    return send_file(buf, as_attachment=True, download_name=filename, mimetype="text/plain; charset=utf-8")


@app.route("/session/<path:session_id>/rp/add", methods=["POST"])
@require_admin
def rp_add(session_id):
    sid  = get_show_id()
    db   = get_db()
    sess = db.execute("SELECT * FROM sessions WHERE id=? AND show_id=?", (session_id, sid)).fetchone()
    if not sess: abort(404)
    role_name = request.form.get("role_name", "").strip()
    content   = request.form.get("content",   "").strip()
    after_id  = request.form.get("after_id",  "").strip()
    if not role_name or not content:
        return redirect(url_for("session_view", session_id=session_id))
    if after_id:
        after = db.execute("SELECT seq FROM rp_entries WHERE id=? AND session_id=? AND show_id=?",
                           (after_id, session_id, sid)).fetchone()
        if after:
            new_seq = after["seq"] + 1
            db.execute("UPDATE rp_entries SET seq=seq+1 WHERE session_id=? AND show_id=? AND seq>=?",
                       (session_id, sid, new_seq))
        else:
            row = db.execute("SELECT MAX(seq) FROM rp_entries WHERE session_id=? AND show_id=?",
                             (session_id, sid)).fetchone()
            new_seq = (row[0] or 0) + 1
    else:
        row = db.execute("SELECT MAX(seq) FROM rp_entries WHERE session_id=? AND show_id=?",
                         (session_id, sid)).fetchone()
        new_seq = (row[0] or 0) + 1
    db.execute(
        "INSERT INTO rp_entries (session_id, show_id, tenant_id, role_name, content, seq, timestamp) "
        "VALUES (?,?,?,?,?,?,?)",
        (session_id, sid, current_tenant_id(), role_name, content, new_seq, int(time.time() * 1000))
    )
    db.commit()
    return redirect(url_for("session_view", session_id=session_id))

@app.route("/session/<path:session_id>/rp/<int:entry_id>/delete", methods=["POST"])
@require_admin
def rp_delete(session_id, entry_id):
    sid = get_show_id()
    db  = get_db()
    db.execute("DELETE FROM rp_entries WHERE id=? AND session_id=? AND show_id=?",
               (entry_id, session_id, sid))
    db.commit()
    return redirect(url_for("session_view", session_id=session_id))

@app.route("/session/<path:session_id>/rp/<int:entry_id>/edit", methods=["POST"])
@require_admin
def rp_edit(session_id, entry_id):
    sid     = get_show_id()
    content = request.form.get("content", "").strip()
    if content:
        get_db().execute("UPDATE rp_entries SET content=? WHERE id=? AND session_id=? AND show_id=?",
                         (content, entry_id, session_id, sid))
        get_db().commit()
    return redirect(url_for("session_view", session_id=session_id))

# ── 管理后台路由 ─────────────────────────────────────────────────────────────

def _season_phase(db, tid):
    """总览顶部那一条「当前阶段 + 下一步」。按租户的当前季/预订季和今天日期算，不看管理员正在「查看」哪一季。
    对外只说筹备期/进行中/补戏期，不暴露机器人内部的 D100 占位天数。"""
    today = datetime.now(TZ_BEIJING).date()
    md = lambda d: f"{d.month}/{d.day}"
    def missing_groups(show_id):
        flat = get_flat_config(db, show_id)
        return [label for key, label in BOOK_GROUP_KEYS if not (flat.get(key) or "").strip()]

    cur = db.execute("SELECT * FROM shows WHERE tenant_id=? AND is_current=1", (tid,)).fetchone()
    if cur:
        rng = _book_range(cur)
        todos = []
        miss = missing_groups(cur["id"])
        if miss:
            todos.append({"t": f"填{'、'.join(miss)}群号", "href": url_for("admin_config_page")})
        players = db.execute("SELECT COUNT(*) FROM players WHERE show_id=?", (cur["id"],)).fetchone()[0]
        if not rng:
            return {"tone": "on", "phase": f"进行中 · {cur['name']}", "todos": todos,
                    "next": "日常运营中；群里发「管理帮助」看常用指令"}
        if today < rng[0]:
            days = (rng[0] - today).days
            return {"tone": "prep", "phase": f"筹备期 · {cur['name']} · {md(rng[0])} 开始（还有 {days} 天）", "todos": todos,
                    "next": (f"已有 {players} 个角色；" if players else "等玩家和 NPC 在自己的群发「创建新角色 名字」；")
                            + f"{md(rng[0])} 当天自动进入 D0"}
        if today <= rng[1]:
            return {"tone": "on", "phase": f"进行中 · {cur['name']} · 档期第 {(today - rng[0]).days + 1} 天（{md(rng[1])} 结束）",
                    "todos": todos, "next": "日常运营中；群里发「管理帮助」看常用指令"}
        if today <= rng[2]:
            return {"tone": "on", "phase": f"补戏期 · {cur['name']} · 补到 {md(rng[2])}", "todos": todos,
                    "next": f"{md(rng[2])} 补戏截止后，群里发「。结束季度」"}
        return {"tone": "warn", "phase": f"档期已过 · {cur['name']} 还没结束", "todos": todos,
                "next": "群里发「。结束季度」，打开存档链接核对无误后发「。收尾」"}

    booked, how, _ = _pick_booked_show(db, tid)
    if booked and how in ("in_schedule", "upcoming"):
        rng = _book_range(booked)
        todos = []
        miss = missing_groups(booked["id"])
        if miss:
            todos.append({"t": f"预订里还没填{'、'.join(miss)}群号", "href": url_for("admin_calendar")})
        if not booked["group_set"]:
            todos.append({"t": "预订里还没选群号组", "href": url_for("admin_calendar")})
        if how == "in_schedule":
            return {"tone": "warn", "phase": f"待开季 · 「{booked['name']}」档期已经开始了", "todos": todos,
                    "next": "现在就在群里发「。开始季度」"}
        return {"tone": "prep", "phase": f"休季 · 已预订「{booked['name']}」{md(rng[0])} 开始", "todos": todos,
                "next": f"到 {md(rng[0])} 前后在群里发「。开始季度」（可以提前开，开始日前算筹备期）"}
    return {"tone": "idle", "phase": "休季 · 还没有预订下一季", "todos": [],
            "next": "去「季度日历」预订下一季", "next_href": url_for("admin_calendar")}

@app.route("/admin")
@require_admin
def admin():
    sid  = get_show_id()
    tid  = current_tenant_id()
    page = max(1, request.args.get("page", 1, type=int))
    db   = get_db()

    sessions_count = db.execute("SELECT COUNT(*) FROM sessions     WHERE show_id=?", (sid,)).fetchone()[0]
    rp_count       = db.execute("SELECT COUNT(*) FROM rp_entries   WHERE show_id=?", (sid,)).fetchone()[0]
    events_count   = db.execute("SELECT COUNT(*) FROM extra_events WHERE show_id=?", (sid,)).fetchone()[0]
    total_players  = db.execute("SELECT COUNT(*) FROM players       WHERE show_id=?", (sid,)).fetchone()[0]

    offset  = (page - 1) * PLAYERS_PER_PAGE
    players = db.execute(
        "SELECT * FROM players WHERE show_id=? ORDER BY sessions_count DESC, last_updated DESC LIMIT ? OFFSET ?",
        (sid, PLAYERS_PER_PAGE, offset)
    ).fetchall()
    total_pages = max(1, (total_players + PLAYERS_PER_PAGE - 1) // PLAYERS_PER_PAGE)
    # 机器人最近一次和网页端同步的时间（机器人每次拉取/推送都会刷新它）
    last_sync_ts = get_flat_config(db, sid).get("_last_bot_sync")
    try:
        last_sync = ts_to_str(int(last_sync_ts)) if last_sync_ts else None
    except (TypeError, ValueError):
        last_sync = None

    return render_template("admin.html", last_sync=last_sync, phase=_season_phase(db, tid),
                           sessions_count=sessions_count, rp_count=rp_count,
                           events_count=events_count, players=[dict(p) for p in players],
                           players_count=total_players, page=page, total_pages=total_pages,
                           cleared=request.args.get("cleared"), ts_to_str=ts_to_str)

@app.route("/admin/clear_all", methods=["POST"])
@require_admin
def admin_clear_all():
    sid = get_show_id()
    db  = get_db()
    for table in ("rp_entries", "extra_events", "sessions"):
        db.execute(f"DELETE FROM {table} WHERE show_id=?", (sid,))
    db.commit()
    return redirect(url_for("admin") + "?cleared=1")

@app.route("/admin/export.json")
@require_admin
def admin_export():
    sid  = get_show_id()
    db   = get_db()
    sessions_raw = db.execute("SELECT * FROM sessions WHERE show_id=? ORDER BY start_ts", (sid,)).fetchall()
    sids = [r["id"] for r in sessions_raw]
    if sids:
        ph         = ",".join("?" * len(sids))
        rp_rows    = db.execute(f"SELECT * FROM rp_entries   WHERE show_id=? AND session_id IN ({ph}) ORDER BY session_id,seq", [sid]+sids).fetchall()
        event_rows = db.execute(f"SELECT * FROM extra_events WHERE show_id=? AND session_id IN ({ph}) ORDER BY session_id,timestamp", [sid]+sids).fetchall()
    else:
        rp_rows = event_rows = []

    rp_by, ev_by = defaultdict(list), defaultdict(list)
    for r in rp_rows:
        rp_by[r["session_id"]].append(dict(r))
    for e in event_rows:
        ei = dict(e)
        try: ei["extra_info"] = json.loads(ei.get("extra_info") or "{}")
        except Exception: ei["extra_info"] = {}
        ev_by[e["session_id"]].append(ei)

    rest_pair = _get_rest_pair(db, sid)
    out = []
    for s in sessions_raw:
        s = _enrich_session(dict(s), rest_pair)
        s["rp_entries"] = rp_by.get(s["id"], [])
        s["extra_events"] = ev_by.get(s["id"], [])
        out.append(s)

    buf      = io.BytesIO(json.dumps(out, ensure_ascii=False, indent=2).encode("utf-8"))
    buf.seek(0)
    filename = f"rp_export_{session.get('tenant_username','data')}_{datetime.now().strftime('%Y%m%d')}.json"
    return send_file(buf, as_attachment=True, download_name=filename, mimetype="application/json; charset=utf-8")

@app.route("/admin/player/<qq>")
@require_admin
def admin_player(qq):
    sid = get_show_id()
    db  = get_db()
    player = db.execute("SELECT * FROM players WHERE show_id=? AND qq=?", (sid, qq)).fetchone()
    player = dict(player) if player else {"qq": qq, "role_name": "", "show_name": "", "sessions_count": 0, "total_replies": 0, "total_words": 0, "last_updated": 0}

    role_name = player.get("role_name", "")
    rest_pair = _get_rest_pair(db, sid)
    all_sessions = [_enrich_session(dict(s), rest_pair) for s in
                    db.execute("SELECT * FROM sessions WHERE show_id=? ORDER BY start_ts DESC", (sid,)).fetchall()]
    player_sessions = [s for s in all_sessions if role_name and role_name in s["participants"]]

    timing_stats = []
    if player_sessions:
        sids = [s["id"] for s in player_sessions]
        ph   = ",".join("?" * len(sids))
        all_entries = db.execute(
            f"SELECT session_id,role_name,timestamp FROM rp_entries WHERE show_id=? AND session_id IN ({ph}) ORDER BY session_id,seq,timestamp",
            [sid]+sids
        ).fetchall()
        by_sess = defaultdict(list)
        for e in all_entries:
            by_sess[e["session_id"]].append(dict(e))
        for s in player_sessions:
            entries = by_sess[s["id"]]
            times   = [
                (entries[i]["timestamp"] - entries[i-1]["timestamp"]) / 1000
                for i in range(1, len(entries))
                if entries[i]["role_name"] == role_name and entries[i-1]["role_name"] != role_name
                and entries[i]["timestamp"] > entries[i-1]["timestamp"]
            ]
            if times:
                timing_stats.append({"session_id": s["id"], "game_day": s.get("game_day",""),
                                     "place": s.get("place",""), "avg": sum(times)/len(times),
                                     "max": max(times), "min": min(times), "count": len(times)})

    # Hourly activity for this player
    role_name_str = role_name or ""
    hourly_rp = [0] * 24
    if role_name_str:
        rp_ts_rows = db.execute(
            "SELECT timestamp FROM rp_entries WHERE show_id=? AND role_name=? AND timestamp > 0",
            (sid, role_name_str)
        ).fetchall()
        for e in rp_ts_rows:
            try:
                hourly_rp[datetime.fromtimestamp(int(e["timestamp"]) / 1000).hour] += 1
            except Exception:
                pass
        evt_ts_rows = db.execute(
            "SELECT timestamp FROM extra_events WHERE show_id=? AND from_role=? AND type IN ('sms','gift') AND timestamp > 0",
            (sid, role_name_str)
        ).fetchall()
        for e in evt_ts_rows:
            try:
                hourly_rp[datetime.fromtimestamp(int(e["timestamp"]) / 1000).hour] += 1
            except Exception:
                pass

    # Per-session player stat from sessions.stats
    session_player_stats = []
    for s in player_sessions:
        st = s.get("stats", {}).get(role_name_str, {})
        session_player_stats.append({
            "session": s,
            "replies": st.get("replies", 0),
            "words":   st.get("words",   0),
        })

    all_times = []
    for t in timing_stats:
        all_times.extend([t["avg"]] * t["count"])
    global_avg_reply = sum(all_times) / len(all_times) if all_times else None

    # 从 session_player_stats 实时算累计（比 players 表存储值更准确）
    computed_replies = sum(s["replies"] for s in session_player_stats)
    computed_words   = sum(s["words"]   for s in session_player_stats)

    # 玩家控制：时间锁定 + 功能权限（从 site_config blob 读取）
    def _get_config_blob(key):
        row = db.execute("SELECT value FROM site_config WHERE show_id=? AND key=?", (sid, key)).fetchone()
        if not row or not row["value"]: return {}
        try: return json.loads(row["value"])
        except Exception: return {}

    locked_slots_all = _get_config_blob("a_lockedSlots")
    feature_blocklist = _get_config_blob("feature_user_blocklist")

    # a_lockedSlots key 格式为 "platform:uid"，匹配所有含该 qq 的 key
    player_locked_slots = {}
    for k, v in locked_slots_all.items():
        if k.endswith(f":{qq}"):
            player_locked_slots = v
            break

    player_features = feature_blocklist.get(qq, {})

    FEATURE_LABELS = {
        "enable_general_gift": "礼物",
        "enable_general_appointment": "发起邀约",
        "enable_chaos_letter": "短信",
        "enable_wish_system": "心愿",
        "enable_lovemail": "心动信",
        "enable_forum": "论坛",
        "enable_item_draw": "抽取",
    }

    return render_template("admin_player.html", player=player, player_sessions=player_sessions,
                           timing_stats=timing_stats, fmt_seconds=fmt_seconds, ts_to_str=ts_to_str,
                           hourly_rp=hourly_rp, max_hourly=max(hourly_rp) or 1,
                           session_player_stats=session_player_stats,
                           global_avg_reply=global_avg_reply,
                           computed_replies=computed_replies, computed_words=computed_words,
                           player_locked_slots=player_locked_slots,
                           player_features=player_features,
                           feature_labels=FEATURE_LABELS)


@app.route("/admin/player/<qq>/controls", methods=["POST"])
@require_admin
def admin_player_update_controls(qq):
    """更新单个玩家的时间锁定或功能权限，写回 site_config blob。"""
    sid = get_show_id()
    tid = session.get("tenant_id")
    db  = get_db()
    data = request.json or {}
    action = data.get("action")  # "lock_add" | "lock_remove" | "feature_set"

    def _get_blob(key):
        row = db.execute("SELECT value FROM site_config WHERE show_id=? AND key=?", (sid, key)).fetchone()
        if not row or not row["value"]: return {}
        try: return json.loads(row["value"])
        except Exception: return {}

    def _save_blob(key, obj):
        db.execute(
            "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
            "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
            (sid, tid, key, json.dumps(obj, ensure_ascii=False))
        )
        db.commit()

    if action in ("lock_add", "lock_remove"):
        day  = (data.get("day") or "").strip()
        slot = (data.get("slot") or "").strip()
        if not day or not slot:
            return jsonify({"ok": False, "error": "missing day/slot"}), 400

        blob = _get_blob("a_lockedSlots")
        # 找到匹配该 qq 的 key（格式 platform:uid）
        match_key = next((k for k in blob if k.endswith(f":{qq}")), None)
        if match_key is None:
            # 没有现有记录时用 qq 作为 key（bot 下次同步会修正 platform prefix）
            match_key = qq

        if action == "lock_add":
            blob.setdefault(match_key, {}).setdefault(day, [])
            if slot not in blob[match_key][day]:
                blob[match_key][day].append(slot)
        else:
            removed = False
            if match_key in blob and day in blob[match_key]:
                try:
                    blob[match_key][day].remove(slot)
                    removed = True
                except ValueError:
                    pass
                if not blob[match_key][day]: del blob[match_key][day]
                if not blob[match_key]: del blob[match_key]
            if not removed:
                return jsonify({"ok": False, "error": "锁定不存在或已被移除"}), 404

        _save_blob("a_lockedSlots", blob)
        return jsonify({"ok": True})

    if action == "feature_set":
        feat_key = (data.get("feature") or "").strip()
        enabled  = data.get("enabled")
        valid_keys = {"enable_general_gift", "enable_general_appointment", "enable_chaos_letter",
                      "enable_wish_system", "enable_lovemail", "enable_forum", "enable_item_draw"}
        if feat_key not in valid_keys or not isinstance(enabled, bool):
            return jsonify({"ok": False, "error": "invalid params"}), 400

        blob = _get_blob("feature_user_blocklist")
        blob.setdefault(qq, {})[feat_key] = enabled
        _save_blob("feature_user_blocklist", blob)
        return jsonify({"ok": True})

    return jsonify({"ok": False, "error": "unknown action"}), 400


@app.route("/admin/player_controls")
@require_admin
def admin_player_controls():
    sid = get_show_id()
    tid = session.get("tenant_id")
    db  = get_db()

    # 读取当前季所有玩家（非 NPC）
    players = [dict(p) for p in
               db.execute("SELECT qq, role_name FROM players WHERE show_id=? AND role_name != '' ORDER BY role_name",
                          (sid,)).fetchall()]

    def _get_blob(key):
        row = db.execute("SELECT value FROM site_config WHERE show_id=? AND key=?", (sid, key)).fetchone()
        if not row or not row["value"]: return {}
        try: return json.loads(row["value"])
        except Exception: return {}

    locked_slots_all = _get_blob("a_lockedSlots")
    feature_blocklist = _get_blob("feature_user_blocklist")

    FEATURE_LABELS = [
        ("enable_general_gift",        "礼物"),
        ("enable_general_appointment", "发起邀约"),
        ("enable_chaos_letter",        "短信"),
        ("enable_wish_system",         "心愿"),
        ("enable_lovemail",            "心动信"),
        ("enable_forum",               "论坛"),
        ("enable_item_draw",           "抽取"),
    ]

    # 为每个玩家整理控制数据
    for p in players:
        qq = p["qq"]
        p["features"] = feature_blocklist.get(qq, {})
        # a_lockedSlots key 格式 "platform:uid"，匹配结尾
        p["locked_slots"] = next(
            (v for k, v in locked_slots_all.items() if k.endswith(f":{qq}")),
            {}
        )

    last_sync = db.execute(
        "SELECT value FROM site_config WHERE show_id=? AND key='_last_bot_sync'", (sid,)
    ).fetchone()
    last_sync_ts = int(last_sync["value"]) // 1000 if last_sync and last_sync["value"] else None

    return render_template("admin_player_controls.html",
                           players=players,
                           feature_labels=FEATURE_LABELS,
                           last_sync_ts=last_sync_ts,
                           ts_to_str=ts_to_str)


# ── 时间调度配置页 ────────────────────────────────────────────────────────────
@app.route("/admin/time-schedule")
@require_admin
def admin_time_schedule():
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()

    # 当前季信息（含档期）
    show = db.execute("SELECT * FROM shows WHERE id=?", (sid,)).fetchone() if sid else None
    show = dict(show) if show else None

    def _get_blob(key):
        if not sid: return None
        row = db.execute("SELECT value FROM site_config WHERE show_id=? AND key=?", (sid, key)).fetchone()
        if not row or not row["value"]: return None
        try: return json.loads(row["value"])
        except Exception: return None

    # 按游戏日的禁约配置 {"D1": [hours], "D2": [...], ...}
    blocked_by_day    = _get_blob("ts_blocked_by_day") or {}
    allowed_durations = _get_blob("ts_allowed_durations")
    if allowed_durations is None:
        allowed_durations = [1, 2, 4, 6, 8, 12, 24]
    feature_windows   = _get_blob("ts_feature_windows") or []
    strict_hour_match    = _get_blob("ts_strict_hour_match") or False
    reality_slot_size    = _get_blob("ts_reality_slot_size") or 0
    slot_mode            = _get_blob("ts_slot_mode") or "cumulative"

    # 计算本季游戏日列表
    day_list = []
    if show:
        s_str = show.get("schedule_start") or ""
        e_str = show.get("schedule_end") or ""
        s_date = _parse_mmdd(s_str)
        e_date = _parse_mmdd(e_str) if e_str else s_date
        if s_date and e_date:
            if e_date < s_date:  # 跨年
                from datetime import timedelta as _td
                e_date = _parse_mmdd(e_str, s_date.year + 1)
            if e_date and e_date >= s_date:
                delta = (e_date - s_date).days + 1
                day_list = ["D0"] + [f"D{i+1}" for i in range(min(delta, 60))]
    if not day_list:
        day_list = ["D0"] + [f"D{i+1}" for i in range(7)]

    FEATURE_OPTIONS = [
        {"key": "enable_general_appointment", "label": "私约/电话"},
        {"key": "enable_general_gift",        "label": "送礼"},
        {"key": "enable_general_letter",      "label": "寄信"},
        {"key": "enable_wish_system",         "label": "心愿"},
        {"key": "enable_lovemail",            "label": "心动信"},
        {"key": "enable_forum",               "label": "论坛"},
        {"key": "enable_item_draw",           "label": "抽取"},
    ]

    return render_template("admin_time_schedule.html",
                           show=show,
                           blocked_by_day=blocked_by_day,
                           day_list=day_list,
                           allowed_durations=allowed_durations,
                           feature_windows=feature_windows,
                           feature_options=FEATURE_OPTIONS,
                           strict_hour_match=strict_hour_match,
                           reality_slot_size=reality_slot_size,
                           slot_mode=slot_mode)


@app.route("/api/time-schedule", methods=["POST"])
@require_admin
def api_time_schedule_save():
    sid = get_show_id()
    tid = current_tenant_id()
    if not sid:
        return jsonify({"ok": False, "error": "no active show"}), 400
    db   = get_db()
    data = request.json or {}

    def _save_blob(key, val):
        db.execute(
            "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
            "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
            (sid, tid, key, json.dumps(val, ensure_ascii=False))
        )

    field = data.get("field")  # "blocked_hours" | "duration_blocked" | "feature_windows"

    if field == "blocked_by_day":
        val = data.get("value", {})
        if not isinstance(val, dict): return jsonify({"ok": False, "error": "bad type"}), 400
        cleaned = {}
        for day, hours in val.items():
            if not isinstance(hours, list): continue
            cleaned[str(day)] = sorted({int(h) for h in hours if 0 <= int(h) <= 23})
        _save_blob("ts_blocked_by_day", cleaned)

    elif field == "allowed_durations":
        val = data.get("value", [])
        if not isinstance(val, list): return jsonify({"ok": False, "error": "bad type"}), 400
        cleaned = sorted({d for d in val if d in (1, 2, 4, 6, 8, 12, 24)})
        _save_blob("ts_allowed_durations", cleaned)

    elif field == "strict_hour_match":
        val = data.get("value", False)
        _save_blob("ts_strict_hour_match", bool(val))

    elif field == "reality_slot_size":
        val = data.get("value", 0)
        if val not in (0, 1, 2, 3, 4, 6, 8):
            return jsonify({"ok": False, "error": "invalid slot size"}), 400
        _save_blob("ts_reality_slot_size", val)

    elif field == "slot_mode":
        val = data.get("value", "cumulative")
        if val not in ("exact", "cumulative"):
            return jsonify({"ok": False, "error": "invalid slot_mode"}), 400
        _save_blob("ts_slot_mode", val)

    elif field == "feature_windows":
        val = data.get("value", [])
        if not isinstance(val, list): return jsonify({"ok": False, "error": "bad type"}), 400
        VALID_KEYS = {"enable_general_appointment","enable_general_gift","enable_general_letter",
                      "enable_wish_system","enable_lovemail","enable_forum","enable_item_draw"}
        cleaned = []
        for item in val:
            if not isinstance(item, dict): continue
            fkey = item.get("feature", "")
            if fkey not in VALID_KEYS: continue
            start = max(0, min(23, int(item.get("start", 0))))
            end   = max(1, min(24, int(item.get("end",  24))))
            if start >= end: continue
            cleaned.append({"feature": fkey, "start": start, "end": end})
        _save_blob("ts_feature_windows", cleaned)

    else:
        return jsonify({"ok": False, "error": "unknown field"}), 400

    db.commit()
    return jsonify({"ok": True})


@app.route("/admin/stats")
@require_admin
def admin_stats():
    sid = get_show_id()
    db  = get_db()

    rest_pair = _get_rest_pair(db, sid)
    sessions = [_enrich_session(dict(s), rest_pair) for s in
                db.execute("SELECT * FROM sessions WHERE show_id=? ORDER BY start_ts ASC", (sid,)).fetchall()]
    players  = [dict(p) for p in
                db.execute("SELECT * FROM players WHERE show_id=? AND role_name != '' ORDER BY total_replies DESC", (sid,)).fetchall()]
    player_map = {p["role_name"]: p for p in players}

    # 兜底：从 rp_entries 和 extra_events 收集所有出现过的角色名
    seen = list(player_map.keys())
    for r in db.execute("SELECT DISTINCT role_name FROM rp_entries WHERE show_id=? AND role_name != ''", (sid,)).fetchall():
        if r["role_name"] not in seen: seen.append(r["role_name"])
    for r in db.execute("SELECT DISTINCT from_role FROM extra_events WHERE show_id=? AND from_role != ''", (sid,)).fetchall():
        if r["from_role"] not in seen: seen.append(r["from_role"])
    role_names = seen

    # 从 sessions.stats 实时算每个角色的累计段数/字数/场次
    role_totals = defaultdict(lambda: {"total_replies": 0, "total_words": 0, "participated": 0})
    for s in sessions:
        stats = s.get("stats", {})
        parts = s.get("participants", [])
        for rn, st in stats.items():
            role_totals[rn]["total_replies"] += st.get("replies", 0)
            role_totals[rn]["total_words"]   += st.get("words",   0)
        for rn in parts:
            role_totals[rn]["participated"]  += 1

    # 如果 players 表里没有某个角色，补一个空记录供模板使用；并覆盖 total_replies/total_words
    for rn in role_names:
        if rn not in player_map:
            player_map[rn] = {"role_name": rn, "qq": "", "total_replies": 0, "total_words": 0}
        t = role_totals.get(rn, {})
        player_map[rn]["total_replies"] = t.get("total_replies", 0)
        player_map[rn]["total_words"]   = t.get("total_words",   0)
    players = [player_map[rn] for rn in role_names]

    # Per-player hourly activity (rp_entries + sms/gift，心动信不计入)
    hourly = defaultdict(lambda: [0] * 24)
    for e in db.execute("SELECT role_name, timestamp FROM rp_entries WHERE show_id=? AND timestamp > 0", (sid,)).fetchall():
        try:
            hourly[e["role_name"]][datetime.fromtimestamp(int(e["timestamp"]) / 1000).hour] += 1
        except Exception:
            pass
    for e in db.execute("SELECT from_role, timestamp FROM extra_events WHERE show_id=? AND type IN ('sms','gift') AND timestamp > 0", (sid,)).fetchall():
        try:
            hourly[e["from_role"]][datetime.fromtimestamp(int(e["timestamp"]) / 1000).hour] += 1
        except Exception:
            pass

    hourly_data = {role: hourly[role] for role in role_names}
    max_hourly  = max((max(v) for v in hourly_data.values() if v), default=1)

    return render_template("admin_stats.html",
                           sessions=sessions, players=players, role_names=role_names,
                           hourly_data=hourly_data, max_hourly=max_hourly,
                           ts_to_str=ts_to_str)



@app.route("/admin/blacklist", methods=["GET", "POST"])
@require_admin
def admin_blacklist():
    tid = current_tenant_id()
    db  = get_db()
    error = None
    success = None

    if request.method == "POST":
        action = request.form.get("action", "add")
        if action == "delete":
            bid = request.form.get("id", "")
            if bid:
                db.execute("DELETE FROM blacklist WHERE id=? AND tenant_id=?", (bid, tid))
                db.commit()
                success = "已删除"
        else:
            qq        = request.form.get("qq", "").strip()
            role_name = request.form.get("role_name", "").strip()
            content   = request.form.get("content", "").strip()
            tags      = request.form.get("tags", "").strip()
            added_by  = request.form.get("added_by", "").strip()
            if not qq and not role_name:
                error = "QQ 号或角色名至少填写一项"
            else:
                db.execute(
                    "INSERT INTO blacklist (tenant_id,qq,role_name,content,tags,added_by,created_at) VALUES (?,?,?,?,?,?,?)",
                    (tid, qq, role_name, content, tags, added_by, int(time.time() * 1000))
                )
                db.commit()
                success = "已添加"

    records = [dict(r) for r in db.execute(
        "SELECT * FROM blacklist WHERE tenant_id=? ORDER BY created_at DESC", (tid,)
    ).fetchall()]

    return render_template("admin_blacklist.html", records=records, error=error, success=success, ts_to_str=ts_to_str)


# ── 写信综复盘 ───────────────────────────────────────────────────────────────

def _get_letters(db, show_id):
    """返回该档期所有 direct_letter 事件，按时间倒序。"""
    rows = db.execute("""
        SELECT id, from_role, to_role, content, extra_info, timestamp, game_day
        FROM extra_events
        WHERE show_id=? AND type='direct_letter'
        ORDER BY timestamp DESC
    """, (show_id,)).fetchall()
    result = []
    for r in rows:
        ei = {}
        try: ei = json.loads(r["extra_info"] or "{}")
        except Exception: pass
        result.append({
            "id":         r["id"],
            "from_role":  r["from_role"],
            "to_role":    r["to_role"],
            "content":    r["content"],
            "signature":  ei.get("signature", r["from_role"]),
            "date_tag":   ei.get("date_tag", ""),
            "attachment": ei.get("attachment", ""),
            "timestamp":  r["timestamp"],
            "game_day":   r["game_day"],
            "ts_str":     ts_to_str(r["timestamp"]),
        })
    return result

@app.route("/letters")
@require_login
def letters_view():
    db      = get_db()
    show_id = get_show_id()
    flat    = get_flat_config(db, show_id) if show_id else {}
    enabled = flat.get("global_feature_toggle__enable_direct_letter", "false") == "true"
    letters = _get_letters(db, show_id) if show_id else []
    locked  = not letters  # 没有记录就锁页
    # 筛选
    q_from = request.args.get("from", "").strip()
    q_to   = request.args.get("to",   "").strip()
    q_day  = request.args.get("day",  "").strip()
    if not locked:
        if q_from: letters = [l for l in letters if q_from in l["from_role"]]
        if q_to:   letters = [l for l in letters if q_to   in l["to_role"]]
        if q_day:  letters = [l for l in letters if l["game_day"] == q_day]
    all_days    = sorted({l["game_day"] for l in _get_letters(db, show_id)} if show_id else [], reverse=True)
    all_roles   = sorted({l["from_role"] for l in _get_letters(db, show_id)} if show_id else [])
    return render_template("letters.html",
                           letters=letters, locked=locked,
                           enabled=enabled,
                           q_from=q_from, q_to=q_to, q_day=q_day,
                           all_days=all_days, all_roles=all_roles)

@app.route("/letters/<int:letter_id>/delete", methods=["POST"])
@require_login
def letter_delete(letter_id):
    if not session.get("admin_logged_in") and not session.get("superadmin_logged_in"):
        abort(403)
    db      = get_db()
    show_id = get_show_id()
    row = db.execute(
        "SELECT id FROM extra_events WHERE id=? AND show_id=? AND type='direct_letter'",
        (letter_id, show_id)
    ).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "not found"}), 404
    db.execute("DELETE FROM extra_events WHERE id=?", (letter_id,))
    db.commit()
    return redirect(url_for("letters_view") + "?" + request.query_string.decode())


@app.route("/event/<int:event_id>/delete", methods=["POST"])
@require_login
def event_delete(event_id):
    if not session.get("admin_logged_in") and not session.get("superadmin_logged_in"):
        abort(403)
    db      = get_db()
    show_id = get_show_id()
    row = db.execute(
        "SELECT id, type, from_role, to_role FROM extra_events WHERE id=? AND show_id=? AND type IN ('sms','gift','lovemail')",
        (event_id, show_id)
    ).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "not found"}), 404
    db.execute("DELETE FROM extra_events WHERE id=?", (event_id,))
    db.commit()
    ref = request.form.get("back") or request.referrer or url_for("admin")
    return redirect(ref)


# ── 角色 / 互动路由 ──────────────────────────────────────────────────────────

@app.route("/character/<role_name>")
@require_login
def character_view(role_name):
    sid  = get_show_id()
    db   = get_db()
    rows = db.execute("SELECT * FROM sessions WHERE show_id=? ORDER BY start_ts DESC", (sid,)).fetchall()
    show_names = get_show_names(db, sid)
    sessions_list = [s for s in _enrich_sessions(rows, _get_rest_pair(db, sid)) if role_name in s["participants"]]
    return render_template("character.html", role_name=role_name, sessions=sessions_list, show_names=show_names)

@app.route("/interactions")
@require_login
def interactions_index():
    sid  = get_show_id()
    db   = get_db()
    rows = db.execute("""
        SELECT role_name,
               SUM(CASE WHEN type='lovemail' THEN 1 ELSE 0 END) AS lovemails,
               SUM(CASE WHEN type='sms'      THEN 1 ELSE 0 END) AS smss,
               SUM(CASE WHEN type='gift'     THEN 1 ELSE 0 END) AS gifts
        FROM (
            SELECT from_role AS role_name, type FROM extra_events WHERE show_id=?
            UNION ALL
            SELECT to_role   AS role_name, type FROM extra_events WHERE show_id=?
        )
        GROUP BY role_name
        ORDER BY (lovemails+smss+gifts) DESC
    """, (sid, sid)).fetchall()
    return render_template("interactions_index.html", roles=[dict(r) for r in rows])

@app.route("/character/<role_name>/interactions")
@require_login
def character_interactions(role_name):
    sid  = get_show_id()
    db   = get_db()
    rows = db.execute("""
        SELECT e.*, s.game_day AS s_game_day
        FROM extra_events e
        LEFT JOIN sessions s ON e.session_id=s.id
        WHERE e.show_id=? AND (e.from_role=? OR e.to_role=?)
        ORDER BY e.timestamp DESC
    """, (sid, role_name, role_name)).fetchall()
    show_names = get_show_names(db, sid)

    events = []
    for e in rows:
        e = dict(e)
        try: e["extra_info"] = json.loads(e["extra_info"] or "{}")
        except Exception: e["extra_info"] = {}
        e["time_str"] = ts_to_str(e["timestamp"])
        e["game_day"]  = e.get("game_day") or e.get("s_game_day") or ""
        events.append(e)

    lovemails = [e for e in events if e["type"] == "lovemail"]
    smss      = [e for e in events if e["type"] == "sms"]
    gifts     = [e for e in events if e["type"] == "gift"]

    pairs = {}
    for e in events:
        # 配对统计只有心动信/短信/礼物三栏；写信综的 direct_letter 等其它类型在「信件」页看，这里跳过——
        # 以前直接拿 f"{type}_sent" 当键去加，碰到 direct_letter 就 KeyError，写过信的角色互动页整页 500
        if e["type"] not in ("lovemail", "sms", "gift"):
            continue
        other  = e["to_role"] if e["from_role"] == role_name else e["from_role"]
        pairs.setdefault(other, {"lovemail_sent":0,"lovemail_recv":0,"sms_sent":0,"sms_recv":0,"gift_sent":0,"gift_recv":0})
        pairs[other][f"{e['type']}_{'sent' if e['from_role']==role_name else 'recv'}"] += 1
    pairs_list = sorted([(k,v,sum(v.values())) for k,v in pairs.items()], key=lambda x:-x[2])

    chaos_smss = [e for e in smss  if e.get("extra_info",{}).get("is_chaos")]
    lost_gifts = [e for e in gifts if e.get("extra_info",{}).get("isLost")]
    chaos_stats = {
        "sms_total": len(chaos_smss),
        "misdelivered":  sum(1 for e in chaos_smss if e["extra_info"].get("is_misdelivered")),
        "content_chaos": sum(1 for e in chaos_smss if e["extra_info"].get("is_content_chaos")),
        "sig_chaos":     sum(1 for e in chaos_smss if e["extra_info"].get("is_signature_chaos")),
        "lost_gifts": len(lost_gifts),
    }
    return render_template("character_interactions.html", role_name=role_name,
                           lovemails=lovemails, smss=smss, gifts=gifts,
                           pairs_list=pairs_list, chaos_stats=chaos_stats, show_names=show_names,
                           is_admin=bool(session.get("admin_logged_in")))

# ── 玩家手机：只看短信和礼物，按「联系人 → 聊天记录」浏览，适配手机 ──────────────────────
# 只能凭激活码进（/p/<code>），一个码只能看自己的手机，赛季进行中实时看。
# 完全按群里实际发生的来，一个字都不能多透露：
#   · 自己发的短信挂在「原本想发给的人」名下（误送了自己不知道），显示自己写的原文；
#   · 收到的短信按落款认人（落款可能被换成别人），显示实际送达的内容；被撕的信没有落款 →「未知号码」；
#   · 撕掉的后半页飘到第三人手里，也按落款认人；
#   · 群里送的礼物只进实际收件人的手机：存档只记了实际收件人，放进送礼人手机的话误送那份会挂错人名下，
#     等于告诉他送错了；网页送的礼物记了 intended_to，送礼人那边照想送的人显示。丢失的礼物收件人看不到。

def _phone_events(db, show_id):
    rows = db.execute(
        "SELECT * FROM extra_events WHERE show_id=? AND type IN ('sms','gift') ORDER BY timestamp, id",
        (show_id,)
    ).fetchall()
    events = _parse_events(rows)
    # 静默拉黑的网页短信：to_role 置空，收件人那边永远匹配不上；发件人按 intended_to 挂在对方名下
    for r in db.execute("SELECT * FROM phone_silent WHERE show_id=?", (show_id,)):
        events.append({"id": -r["id"], "type": "sms", "from_role": r["from_role"], "to_role": "",
                       "content": r["content"], "extra_info": {"intended_to": r["to_role"]},
                       "timestamp": r["timestamp"], "game_day": r["game_day"]})
    # 点歌：被点的人和点歌的人在「点歌台」对话里各看到一条（点给大家的只进公开播报）
    for sg in _song_rows(db, show_id):
        events.append({"id": -1_000_000 - sg["id"], "type": "song", "from_role": sg["from_role"], "to_role": sg["to_role"],
                       "content": sg["message"], "extra_info": {"song": sg}, "timestamp": sg["created_at"],
                       "game_day": sg["game_day"]})
    events.sort(key=lambda e: (e["timestamp"] or 0, e["id"]))
    return events

def _sig_name(signature):
    """「落款：张三」→ 张三"""
    sig = (signature or "").strip()
    for prefix in ("落款：", "落款:"):
        if sig.startswith(prefix):
            sig = sig[len(prefix):].strip()
    return sig

def _phone_view_of(e, owner):
    """把一条事件翻译成 owner 手机里看到的样子；这条不在 owner 手机里就返回 None"""
    info = e["extra_info"] or {}
    frm, to = e["from_role"], e["to_role"]
    m = {"id": e["id"], "kind": e["type"], "public": bool(info.get("isPublic")),
         "ts": e["timestamp"] or 0, "game_day": e["game_day"] or "", "signature": ""}
    if e["type"] == "sms" and info.get("alias_id"):
        # 匿名对话：化名主人那边对话叫「对方＠化名」，收件人那边就叫化名。混乱效果跟普通短信一样：
        # 被撕的收件人看到「未知号码」；误送到第三人手里时，化名的信照样在化名对话里，回化名的信按落款认人
        a_owner, a_target, alias = info.get("alias_owner"), info.get("alias_target"), info.get("alias_name")
        out = info.get("alias_dir") == "out"
        sig = info.get("signature") or ""
        if frm == owner:
            m.update(other=f"{a_target}＠{alias}" if out else alias, mine=True, text=e["content"])
        elif to == owner:
            if info.get("is_torn"):
                m.update(other="未知号码", signature="（落款在缺失的后半页上）")
            elif out:
                m.update(other=alias, signature=sig)
            elif owner == a_owner:
                m.update(other=f"{a_target}＠{alias}", signature=sig)
            else:
                m.update(other=_sig_name(sig) or frm, signature=sig)
            m.update(mine=False, text=info.get("delivered") or e["content"])
        elif info.get("is_torn") and info.get("torn_holder") == owner:
            m.update(other=alias if out else (_sig_name(sig) or frm), mine=False, signature=sig,
                     text="……" + (info.get("torn_second_half") or ""))
        else:
            return None
        return m
    if e["type"] == "sms":
        sig = info.get("signature") or ""
        if frm == owner:
            m.update(other=info.get("intended_to") or to, mine=True, text=e["content"])
        elif to == owner:
            if info.get("is_torn"):
                m.update(other="未知号码", signature="（落款在缺失的后半页上）")
            else:
                m.update(other=_sig_name(sig) or frm, signature=sig)
            m.update(mine=False, text=info.get("delivered") or e["content"])
        elif info.get("is_torn") and info.get("torn_holder") == owner:
            m.update(other=_sig_name(sig) or frm, mine=False, signature=sig,
                     text="……" + (info.get("torn_second_half") or ""))
        else:
            return None
        return m
    m.update(gift_name=info.get("giftName") or "礼物", text=e["content"] or "")
    if frm == owner and info.get("source") == "web":
        # 网页送的礼物记了原本想送给谁，送礼人这边照「想送的人」显示（丢了、送错了都看不出来）
        m.update(other=info.get("intended_to") or to, mine=True)
        return m
    if e["type"] == "song":
        sg = info["song"]
        m.update(kind="song", text=e["content"] or "", to=to, song=_song_view(sg))
        if to and to == owner:
            m.update(other="点歌台", mine=False)
            return m
        if frm == owner:
            m.update(other="点歌台", mine=True)
            return m
        return None
    if to == owner and not info.get("isLost"):
        m.update(other=info.get("from_custom_name") or frm, mine=False)
        return m
    return None

def _phone_preview(m):
    if m["kind"] == "song":
        return f"🎵 {m['song']['name']}" + (f"（点给 {m['to']}）" if m["mine"] and m.get("to") else "")
    if m["kind"] == "gift":
        return f"🎁 {m['gift_name']}" + (f"：{m['text']}" if m["text"] else "")
    return m["text"].replace("\n", " ")

def _phone_time(ts):
    try:
        return datetime.fromtimestamp(int(ts) / 1000, TZ_BEIJING).strftime("%H:%M") if ts else ""
    except Exception:
        return ""

def _phone_threads(db, sid, owner):
    threads = {}
    for e in _phone_events(db, sid):
        m = _phone_view_of(e, owner)
        if not m or not m["other"]:
            continue
        t = threads.setdefault(m["other"], {"other": m["other"]})
        t["received_ts"] = max(t.get("received_ts", 0), m["ts"] if not m["mine"] else 0)
        t["last"] = m  # 按时间升序遍历，最后一条就是最新
    threads = sorted(threads.values(), key=lambda t: -t["last"]["ts"])
    for t in threads:
        t["preview"] = ("我：" if t["last"]["mine"] else "") + _phone_preview(t["last"])
        t["time"] = _phone_time(t["last"]["ts"])
    return threads

def _phone_msgs(db, sid, owner, other):
    msgs = []
    for e in _phone_events(db, sid):
        m = _phone_view_of(e, owner)
        if m and m["other"] == other:
            m["time"] = _phone_time(m["ts"])
            msgs.append(m)
    return _phone_mark_breaks(msgs)

def _phone_mark_breaks(msgs):
    """按游戏日插分隔条；同一天内隔了 1 小时以上再补一个时间戳，像真手机那样。
    落款写在气泡上方（像群聊的发言人名字）：连续几条同一落款的来信只在第一条上面写一次"""
    prev_day, prev_ts, prev_sig = None, 0, None
    for m in msgs:
        m["day_break"] = m["game_day"] if m["game_day"] != prev_day else None
        m["show_time"] = bool(m["day_break"]) or (m["ts"] - prev_ts > 3600_000)
        sig = None
        if not m["mine"] and m["signature"]:
            sig = _sig_name(m["signature"]) if m["signature"].startswith("落款") else m["signature"]
        m["sig_above"] = sig if sig and (sig != prev_sig or m["show_time"]) else None
        prev_day, prev_ts, prev_sig = m["game_day"], m["ts"], sig
    return msgs

# ── 玩家手机激活码：后台给每个角色生成一个码，玩家凭码只看自己的手机 ─────────────────────
# 安全设计：
#   · 码 10 位、32 个字符（约 50 bit），同一 IP 15 分钟内输错 10 次就锁 15 分钟，猜不出来；
#   · 码只在进门时出现一次：/p/<码> 校验后记进独立签名 cookie，立刻跳到 /p/me，地址栏里不留码，
#     玩家截图发群也不会把码带出去；
#   · 每次打开都重新查库校验：后台「重置」或季度结束（is_current=0）后，已经打开的页面刷新就进不去了；
#   · /p 下的页面不缓存、不带 Referer、不许被 iframe 嵌、不让搜索引擎收录。

_PHONE_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 去掉 I/O/0/1，念给玩家不会抄错
_PHONE_CODE_LEN      = 10
_PHONE_FAIL_WINDOW   = 15 * 60
_PHONE_FAIL_MAX      = 10
_phone_fails         = {}   # ip -> [失败时间戳...]；单进程 waitress，放内存即可，重启清零无妨
_phone_fails_lock    = threading.Lock()
_PHONE_BAD_CODE      = "激活码不对，或者这一季已经结束了"

def _phone_ip_locked():
    now = time.time()
    with _phone_fails_lock:
        fails = [t for t in _phone_fails.get(request.remote_addr, []) if now - t < _PHONE_FAIL_WINDOW]
        _phone_fails[request.remote_addr] = fails
        return len(fails) >= _PHONE_FAIL_MAX

def _phone_note_fail():
    now = time.time()
    with _phone_fails_lock:
        _phone_fails.setdefault(request.remote_addr, []).append(now)
        if len(_phone_fails) > 10000:  # 防内存被刷爆：清掉过期的
            for ip in [ip for ip, ts in _phone_fails.items() if not ts or now - ts[-1] > _PHONE_FAIL_WINDOW]:
                _phone_fails.pop(ip, None)

def _new_phone_code(db):
    while True:
        code = "".join(secrets.choice(_PHONE_CODE_ALPHABET) for _ in range(_PHONE_CODE_LEN))
        if not db.execute("SELECT 1 FROM phone_codes WHERE code=? UNION SELECT 1 FROM phone_admin_codes WHERE code=?",
                          (code, code)).fetchone():
            return code

def _phone_code_owner(db, code):
    """码 → (show_id, role_name)；码不存在或所属季已结束都返回 None"""
    code = (code or "").strip().upper()
    if len(code) != _PHONE_CODE_LEN:
        return None
    row = db.execute("""
        SELECT c.show_id, c.role_name FROM phone_codes c JOIN shows s ON s.id=c.show_id
        WHERE c.code=? AND s.is_current=1
    """, (code,)).fetchone()
    if row:
        return (row["show_id"], row["role_name"])
    row = db.execute("""
        SELECT c.show_id FROM phone_admin_codes c JOIN shows s ON s.id=c.show_id
        WHERE c.code=? AND s.is_current=1
    """, (code,)).fetchone()
    return (row["show_id"], PHONE_ADMIN) if row else None

# 管理身份用的「角色名」：带 \0，任何真实角色名都不可能跟它撞
PHONE_ADMIN = "\0管理员"

def _phone_try_enter(code):
    """校验码并写入独立 cookie；不改变团账号或后台会话的期限"""
    if _phone_ip_locked():
        return render_template("phone.html", mode="entry", error="输错太多次了，15 分钟后再试"), 429
    code = (code or "").strip().upper()
    if not _phone_code_owner(get_db(), code):
        _phone_note_fail()
        return render_template("phone.html", mode="entry", error=_PHONE_BAD_CODE), 404
    who = _phone_code_owner(get_db(), code)
    resp = redirect(url_for("admin_phone_index" if who and who[1] == PHONE_ADMIN else "player_phone_inbox"))
    resp.set_cookie(_PHONE_COOKIE, _phone_signer().dumps(code), max_age=_PHONE_COOKIE_AGE,
                    httponly=True, samesite="Lax", secure=not _phone_local(), path="/p")
    return resp

_PHONE_COOKIE = "phone_auth"
_PHONE_COOKIE_AGE = 30 * 24 * 60 * 60

def _phone_signer():
    return URLSafeTimedSerializer(app.secret_key, salt="player-phone-auth")

def _phone_current():
    """独立 cookie 验签后每次查库，重置激活码和季度结束立即失效。"""
    try:
        code = _phone_signer().loads(request.cookies.get(_PHONE_COOKIE, ""), max_age=_PHONE_COOKIE_AGE)
    except BadSignature:
        return None
    return _phone_code_owner(get_db(), code) if isinstance(code, str) else None

def _phone_local():
    return urlparse(request.host_url).hostname in ("localhost", "127.0.0.1")

def _phone_base_url():
    return request.host_url.rstrip("/") if _phone_local() else "https://" + request.host

@app.before_request
def _phone_require_https():
    if (request.path == "/p" or request.path.startswith("/p/")) and not _phone_local() and request.scheme == "http":
        return redirect(request.url.replace("http://", "https://", 1), code=301)

@app.after_request
def _phone_security_headers(resp):
    if request.path == "/p" or request.path.startswith("/p/"):
        cacheable_image = resp.headers.pop("X-Moment-Image", None) and resp.status_code == 200
        resp.headers["Cache-Control"]   = "private, max-age=86400" if cacheable_image else "no-store"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Robots-Tag"]    = "noindex, nofollow"
    return resp

@app.route("/p/guide")
def phone_guide():
    """网页手机里的「小手机」对话：按身份只给一组问题——管理员手机码或团后台管理员看管理篇，其余（含没登录）看玩家篇"""
    who = _phone_current()
    is_admin = bool(who and who[1] == PHONE_ADMIN) or bool(session.get("admin_logged_in") and not who)
    if who:
        back = url_for("admin_phone_index") if who[1] == PHONE_ADMIN else url_for("player_phone_inbox")
    else:
        back = url_for("admin_phone_codes") if is_admin else url_for("phone_code_entry")
    return render_template("phone_guide.html", audience="admin" if is_admin else "player", back=back)

@app.route("/p", methods=["GET", "POST"])
def phone_code_entry():
    if request.method == "POST":
        return _phone_try_enter(request.form.get("code"))
    if _phone_current():
        return redirect(url_for("player_phone_inbox"))
    return render_template("phone.html", mode="entry", error=None)

# ── 玩家消息检索：只从已经翻译好的个人视角构建结果 ──
@app.template_filter("phone_message_key")
def _phone_message_key(parts):
    payload = json.dumps(list(parts), ensure_ascii=False, separators=(",", ":"))
    return hmac.new(str(app.secret_key).encode(), ("phone-message:" + payload).encode(), hashlib.sha256).hexdigest()[:32]

@app.route("/p/me/library")
def player_phone_library():
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    view = request.args.get("view", "search")
    if view not in ("search", "saved", "profile"):
        view = "search"
    return render_template("phone.html", mode="profile" if view == "profile" else "library",
                           library_view=view, sid=sid, owner=owner, csrf=_phone_csrf(),
                           flash=session.pop("phone_flash", None), nick_max=_NICK_MAX,
                           my_nick=_nick_map(get_db(), sid).get(owner, "") if owner != PHONE_ADMIN else "")

# ── 首页全局搜索 ─────────────────────────────────────────────────────────────────
# 一个搜索框搜自己手机里能看到的一切：联系人/群聊、短信和礼物（含群聊消息）、心动信（收到的只有署名）、朋友圈。
# 只看本人视角：短信礼物走 _phone_all_views（已经是玩家视角，误投/换落款照玩家看到的算），心动信用 _lm_history，
# 朋友圈本季公开。结果数量有上限，按时间新的在前。
_SEARCH_MAX = 40
_SEARCH_PER_GROUP = 20

def _snippet(text, q, radius=22):
    """匹配处前后各取一段；返回 (前, 命中, 后)，前端给命中加高亮"""
    text = (text or "").replace("\n", " ")
    i = text.lower().find(q)
    if i < 0:
        return text[:radius * 2], "", ""
    a, b = max(0, i - radius), min(len(text), i + len(q) + radius)
    return ("…" if a else "") + text[a:i], text[i:i + len(q)], text[i + len(q):b] + ("…" if b < len(text) else "")

@app.route("/p/me/search")
def player_phone_search():
    who = _phone_current()
    if not who:
        return jsonify(error="手机登录已失效"), 401
    sid, owner = who
    if owner == PHONE_ADMIN:
        return jsonify(groups=[])
    q = (request.args.get("q") or "").strip().lower()[:_SEARCH_MAX]
    if not q:
        return jsonify(groups=[])
    db = get_db()
    sync = _phone_sync_row(db, sid)
    groups = []

    # 联系人 / 群聊：对话列表里名字命中的，加上名单里还没聊过的人（点进去就能开始对话）
    people, seen = [], set()
    for t in _phone_threads(db, sid, owner) + _group_threads(db, sid, owner):
        name = t["group"]["name"] if t.get("group") else t["other"].partition("＠")[0]
        if q in name.lower() or (t.get("group") is None and q in t["other"].lower()):
            url = url_for("player_group_thread", gid=t["group"]["id"]) if t.get("group") else url_for("player_phone_thread", other=t["other"])
            people.append({"title": name, "sub": ("群聊 · %d 人" % t["group"]["n"]) if t.get("group") else t["preview"],
                           "url": url, "avatar": None if t.get("group") else name, "group": bool(t.get("group"))})
        seen.add(t["other"].partition("＠")[0])
    for n in _phone_roster(sync):
        if n != owner and n not in seen and q in n.lower():
            people.append({"title": n, "sub": "还没有往来，点击开始对话", "url": url_for("player_phone_thread", other=n), "avatar": n, "group": False})
    if people:
        groups.append({"key": "people", "label": "联系人", "items": people[:_SEARCH_PER_GROUP]})

    # 短信 / 礼物 / 群聊消息
    msgs = []
    for m in sorted(_phone_all_views(db, sid, owner), key=lambda m: -m["ts"]):
        if m["kind"] not in ("sms", "gift", "gsms"):
            continue
        hay = (m.get("text") or "") + " " + (m.get("gift_name") or "")
        if q not in hay.lower():
            continue
        key = _phone_message_key([sid, owner, m["id"]])
        if str(m["other"]).startswith("__group__"):
            gid = int(str(m["other"])[len("__group__"):])
            g = db.execute("SELECT name FROM phone_groups WHERE id=?", (gid,)).fetchone()
            where, url = "群聊「%s」" % (g["name"] if g else ""), url_for("player_group_thread", gid=gid) + "#message-" + key
        else:
            where, url = m["other"].partition("＠")[0], url_for("player_phone_thread", other=m["other"]) + "#message-" + key
        who_ = "我" if m["mine"] else (m.get("signature") or "").replace("落款：", "") or where
        body = ("🎁 " + m["gift_name"] + " " if m["kind"] == "gift" and m.get("gift_name") else "") + (m.get("text") or "")
        pre, hit, post = _snippet(body, q)
        msgs.append({"title": where, "meta": "%s · %s %s" % (who_, m.get("game_day") or "", _phone_time(m["ts"])), "pre": pre, "hit": hit, "post": post, "url": url})
        if len(msgs) >= _SEARCH_PER_GROUP:
            break
    if msgs:
        groups.append({"key": "msgs", "label": "短信和礼物", "items": msgs})

    # 心动信：收到的只显示署名，不显示寄信人
    lms = []
    recv, sent = _lm_history(db, sid, owner)
    for it, kind in [(i, "recv") for i in recv] + [(i, "sent") for i in sent]:
        if q in (it["content"] or "").lower():
            pre, hit, post = _snippet(it["content"], q)
            lms.append({"title": "收到的心动信" if kind == "recv" else "寄给 %s 的心动信" % it["to"],
                        "meta": "署名：%s · %s" % (it["signature"], it["game_day"] or "往期"), "pre": pre, "hit": hit, "post": post,
                        "url": url_for("player_lovemail", view="inbox" if kind == "recv" else "sent")})
    if lms:
        groups.append({"key": "lovemail", "label": "心动信", "items": lms[:_SEARCH_PER_GROUP]})

    # 朋友圈（本季所有人都能看到的）
    moms, nicks = [], _nick_map(db, sid)
    for r in db.execute("SELECT role_name, content, game_day, created_at FROM moments WHERE show_id=? AND deleted=0 ORDER BY id DESC LIMIT 500", (sid,)):
        if q in (r["content"] or "").lower():
            pre, hit, post = _snippet(r["content"], q)
            moms.append({"title": ("%s（%s）" % (nicks[r["role_name"]], r["role_name"])) if r["role_name"] in nicks else r["role_name"], "meta": "%s %s" % (r["game_day"] or "", _phone_time(r["created_at"])), "pre": pre, "hit": hit,
                         "post": post, "url": url_for("player_moments")})
            if len(moms) >= _SEARCH_PER_GROUP:
                break
    if moms:
        groups.append({"key": "moments", "label": "朋友圈", "items": moms})
    return jsonify(groups=groups, q=q)

@app.route("/p/me/library/data")
def player_phone_library_data():
    who = _phone_current()
    if not who:
        return jsonify(error="手机登录已失效"), 401
    sid, owner = who
    records = []
    for m in _phone_views(get_db(), sid, owner):
        if m["kind"] not in ("sms", "gift"):
            continue
        key = _phone_message_key([sid, owner, m["id"]])
        records.append({
            "key": key, "other": m["other"], "mine": m["mine"], "kind": m["kind"],
            "text": m["text"], "gift_name": m.get("gift_name", ""),
            "signature": m.get("signature", ""), "day": m["game_day"], "time": _phone_time(m["ts"]),
            "ts": m["ts"], "url": url_for("player_phone_thread", other=m["other"]) + "#message-" + key,
        })
    return jsonify(records=records)

@app.route("/p/me")
def player_phone_inbox():
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    if owner == PHONE_ADMIN:
        return redirect(url_for("admin_phone_index"))
    db = get_db()
    return render_template("phone.html", mode="inbox", owner=owner, sid=sid,
                           threads=sorted(_phone_threads(db, sid, owner) + _group_threads(db, sid, owner),
                                          key=lambda t: -t["last"]["ts"]),
                           status=_phone_status(db, sid, owner), flash=session.pop("phone_flash", None),
                           timeline_n=_phone_timeline_upcoming(db, sid, owner),
                           public=_phone_public_summary(db, sid), pending_summary=_phone_pending_summary(db, sid, owner),
                           moments_latest=db.execute(
                               "SELECT role_name, content, created_at, game_day, (SELECT COUNT(*) FROM moment_images i "
                               "WHERE i.moment_id=m.id) AS n FROM moments m WHERE show_id=? AND deleted=0 "
                               "ORDER BY id DESC LIMIT 1", (sid,)).fetchone(),
                           revision=_phone_revision(_phone_all_views(db, sid, owner)), csrf=_phone_csrf())

def _phone_views(db, sid, owner):
    return [m for e in _phone_events(db, sid) if (m := _phone_view_of(e, owner)) and m["other"]]

def _phone_revision(views):
    """玩家视角内容的指纹：先翻译成玩家视角再算，隐藏事件（别人的信、静默拉黑）不会让它变化。
    页面渲染时也带上它，这样第一次轮询不会白白整段重拉、把正在翻历史的人拽回底部。"""
    visible = [{k: v for k, v in m.items() if k != "id"} for m in views]
    return hashlib.sha256(json.dumps(visible, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

@app.route("/p/me/poll")
def player_phone_poll():
    who = _phone_current()
    if not who:
        return jsonify(error="手机登录已失效"), 401
    sid, owner = who
    views = _phone_all_views(get_db(), sid, owner)
    revision = _phone_revision(views)
    incoming = {}
    for m in views:
        if not m["mine"]:
            incoming[m["other"]] = max(incoming.get(m["other"], 0), m["ts"])
    return jsonify(latest=max((m["ts"] for m in views), default=0),
                   revision=revision, incoming=incoming, pending=_phone_pending_summary(get_db(), sid, owner))

@app.route("/p/me/public")
def player_phone_public():
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    db = get_db()
    return render_template("phone.html", mode="public", owner=owner, sid=sid,
                           phone_admin=(owner == PHONE_ADMIN), csrf=_phone_csrf(),
                           items=_phone_public_items(db, sid), daily=_phone_public_daily(db, sid),
                           revision=_phone_revision(_phone_all_views(db, sid, owner)))

@app.route("/p/me/<other>")
def player_phone_thread(other):
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    db = get_db()
    st = _phone_status(db, sid, owner)
    # 能回复的对象必须在角色名单里（「未知号码」、名单外的名字不能回），或者是匿名对话
    alias = _alias_resolve(db, sid, owner, other)
    astate = _alias_state(db, sid, owner, other) if alias else None
    can_reply = st["can"] and ((other in _phone_roster(_phone_sync_row(db, sid)) and other != owner)
                               or bool(alias and not astate["blocked"]))
    return render_template("phone.html", mode="thread", owner=owner, sid=sid, other=other,
                           alias_thread=(alias[2] if alias else None), alias_state=astate,
                           block_state=None if alias else _phone_block_state(db, sid, owner, other),
                           msgs=_phone_msgs(db, sid, owner, other), status=st, can_reply=can_reply,
                           revision=_phone_revision(_phone_all_views(db, sid, owner)),
                           stickers=_phone_stickers(db, sid) if can_reply else [],
                           my_presets=([{"id": i, **g} for i, g in _preset_gifts(db, sid).items()
                                        if i in _shop_catalog(db, sid, _phone_sync_row(db, sid), owner)] if can_reply else []),
                           csrf=_phone_csrf(), sent=session.pop("phone_sent", False), flash=session.pop("phone_flash", None),
                           draft=session.pop("phone_draft", ""), draft_kind=session.pop("phone_draft_kind", "sms"),
                           draft_gift=session.pop("phone_draft_gift", ""))

@app.route("/p/logout", methods=["POST"])
def player_phone_logout():
    resp = redirect(url_for("phone_code_entry"))
    resp.delete_cookie(_PHONE_COOKIE, path="/p", httponly=True, samesite="Lax", secure=not _phone_local())
    return resp

# ── 网页发送：机器人挂掉时的备用通道 ─────────────────────────────────────────────
# 玩家在网页上发的短信/礼物直接写进存档（extra_info.source="web"），收件人在自己的网页手机里看到，
# 不经过机器人、也不转发进 QQ 群。规则全部来自插件每 30 秒上报的快照（/api/phone/sync）：
# 混乱效果概率、冷却、每日上限、功能开关、个人功能权限、拉黑、角色名单——存档站只照着执行，不另存一套规则。
# 次数同步：
#   · 快照新鲜（10 分钟内）：今日已用 = 插件上报的今日次数 + 插件还没取走的网页记录；按游戏日算；
#   · 快照过期（机器人挂了）：游戏日不会再推进，改按北京时间自然日只数网页记录，不然上限永远不重置；
#   · 插件每次同步取走新的网页记录，计进自己的每日次数/冷却/互动统计，群里再发也不会超。
# 管理员在后台打开「允许网页发送」才生效，默认关闭；只在主档期内能发（跟 /api/event 的档期门控一致）。

_PHONE_SYNC_FRESH_MS = 10 * 60 * 1000
_PHONE_MAX_LEN       = 500
_PHONE_MIN_GAP_MS    = 5000          # 冷却配置成 0 也至少隔 5 秒，防脚本刷屏
_phone_send_lock     = threading.Lock()
_CHAOS_CHAR_POOL     = ["梦", "影", "幻", "虚", "无", "断", "零", "终", "念", "尘", "迹", "雾", "嘘", "寂"]
_BLACKOUT_CHARS      = ["◼︎", "█", "■", "▮"]

# 网页发送不能发图，给一块表情面板：emoji 和颜文字都是纯文字，点一下插进输入框。
# 后台「短信激活码」页可以按季改成自己的一套（一行一个），留空就用这里的默认。
_PHONE_DEFAULT_STICKERS = [
    "😊", "😂", "🥺", "😭", "😳", "🥰", "😘", "😤", "🙄", "🤔", "😴", "🫠",
    "❤️", "💔", "✨", "🌹", "🌙", "☕", "🎂", "👀", "🙏", "👌",
    "(｡･ω･｡)", "(๑•̀ㅂ•́)و✧", "(╥﹏╥)", "(ﾉ>ω<)ﾉ", "(*/ω＼*)", "(｀へ´)", "(・∀・)",
    "(⁄ ⁄•⁄ω⁄•⁄ ⁄)", "(´･_･`)", "ヾ(≧▽≦*)o", "(っ´ω`c)", "ᕦ(ò_óˇ)ᕤ", "(￣▽￣)~*", "orz",
]
_PHONE_STICKER_MAX     = 60
_PHONE_STICKER_MAX_LEN = 20

def _phone_parse_stickers(raw):
    """一行一个，去空行去重，单个太长的丢掉，最多 60 个"""
    out = []
    for line in (raw or "").splitlines():
        t = line.strip()
        if t and len(t) <= _PHONE_STICKER_MAX_LEN and t not in out:
            out.append(t)
    return out[:_PHONE_STICKER_MAX]

def _phone_stickers(db, sid):
    row = db.execute("SELECT stickers FROM phone_settings WHERE show_id=?", (sid,)).fetchone()
    custom = _phone_parse_stickers(row["stickers"]) if row else []
    return custom or _PHONE_DEFAULT_STICKERS

# ── 公开播报：公告群播过的短信/礼物，网页手机里一直有一份（不管有没有开网页发送）──
# 网页上发的短信/礼物被抽中公开时，只有网页这一份（网页发送不进 QQ 群）。
# 显示规则跟插件往公告群发的那条一模一样，不能多透露：
#   · 发件人用署名（from_custom_name，没有就是本名），不是落款——落款混乱不影响播报；
#   · 收件人是「原本想发/送给的人」（intended_to），隐藏收件人时显示「某人」——误送了播报也看不出来；
#   · 短信内容看插件当时的 publicShowEffect：开了显示送达的（被篡改过的）内容，没开显示原文；
#   · 丢失的礼物插件不播报，这里也不会有（isPublic 本来就是 false）。
# 旧版插件存的礼物没有 intended_to，只能退回 to_role（那时误送+公开同时发生的会不一致，概率很低）。
def _phone_public_items(db, sid):
    rows = db.execute(
        "SELECT * FROM extra_events WHERE show_id=? AND type IN ('sms','gift') "
        "AND json_extract(extra_info, '$.isPublic') IN (1, 'true') ORDER BY timestamp, id", (sid,)
    ).fetchall()
    items = []
    for e in _parse_events(rows):
        info = e["extra_info"] or {}
        if e["type"] == "gift" and info.get("isLost"):
            continue
        item = {"kind": e["type"], "from": info.get("public_from") or info.get("from_custom_name") or e["from_role"],
                "to": "某人" if info.get("hide_receiver") else (info.get("public_to") or info.get("intended_to") or e["to_role"]),
                "ts": e["timestamp"] or 0, "time": _phone_time(e["timestamp"]), "game_day": e["game_day"] or "",
                "admin_note": _admin_note(e), "admin_del": f"event:{e['id']}"}  # 只有管理身份的页面会显示这两个
        if e["type"] == "sms":
            item["text"] = (info.get("delivered") or e["content"]) if info.get("public_show_effect") else e["content"]
        else:
            item.update(gift_name=info.get("giftName") or "礼物", text=e["content"] or "")
        items.append(item)
    for g in (db.execute("""SELECT m.*, g.name AS group_name FROM phone_group_msgs m JOIN phone_groups g ON g.id=m.group_id
                            WHERE m.show_id=? AND m.kind='msg' AND m.is_public=1 AND m.deleted=0""", (sid,)) if GROUP_CHAT_ON else []):
        items.append({"kind": "sms", "from": g["signature"], "to": "某个群" if g["hide_receiver"] else f"群聊「{g['group_name']}」",
                      "text": g["delivered"] if g["show_effect"] else g["content"],
                      "ts": g["created_at"], "time": _phone_time(g["created_at"]), "game_day": g["game_day"],
                      "admin_note": f"群聊「{g['group_name']}」· 实际发件人：{g['from_role']}", "admin_del": f"group:{g['id']}"})
    for sg in _song_rows(db, sid):
        items.append({"kind": "song", "from": "有人", "to": sg["to_role"] or "大家", "text": sg["message"],
                      "admin_note": f"点歌人：{sg['from_role']}", "admin_del": f"song:{sg['id']}",
                      "ts": sg["created_at"], "time": _phone_time(sg["created_at"]), "game_day": sg["game_day"],
                      "song": _song_view(sg)})
    items.sort(key=lambda it: it["ts"])
    prev_day = None
    for it in items:
        it["day_break"] = it["game_day"] if it["game_day"] != prev_day else None
        prev_day = it["game_day"]
    return items

def _phone_public_summary(db, sid):
    """消息列表顶部「公开播报」那一行用：没有任何播报时返回 None（不显示这一行）"""
    items = _phone_public_items(db, sid)
    if not items:
        return None
    last = items[-1]
    if last["kind"] == "song":
        preview = f"有人点给 {last['to']}：🎵 {last['song']['name']}"
    else:
        preview = f"{last['from']} → {last['to']}：" + (f"🎁 {last['gift_name']}" if last["kind"] == "gift" else last["text"].replace("\n", " "))
    return {"count": len(items), "preview": preview, "time": last["time"], "game_day": last["game_day"], "ts": last["ts"]}

# ── 违禁词：网页手机里玩家写的字（短信、礼物、朋友圈、评论）──────────────────────
# 词表在 blocklist.txt（跟甄嬛传/排单宝同一份起步词表），一行一个、# 开头是注释，改了按修改时间自动重新读、不用重启。
# 比对前去掉空格和标点，防「傻 逼」「傻.逼」这种拆字；命中的记进 logs/moderation.log（时间、季度、角色、场合、原文）。
BLOCKLIST_PATH  = os.path.join(os.path.dirname(__file__), "blocklist.txt")
MODERATION_LOG  = os.path.join(os.path.dirname(__file__), "logs", "moderation.log")
_blocklist_cache = {"mtime": None, "words": [], "ascii": []}
_BLOCK_NOISE     = re.compile(r"[\s\W_]+")
BLOCKED_MSG      = "❌ 内容含有不允许的字词，请修改后再发"

def _blocklist_load():
    """返回 (子串词, 整词词)。含中文的词去掉空格符号后按子串匹配；纯英文/数字的短词（sb、av、np、3p…）
    按整词匹配，否则 have、saving、happy 这类正常英文会被误伤。"""
    try:
        mtime = os.path.getmtime(BLOCKLIST_PATH)
    except OSError:
        return [], []
    if _blocklist_cache["mtime"] != mtime:
        with open(BLOCKLIST_PATH, encoding="utf-8") as f:
            raw = [ln.strip().lower() for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
        words, ascii_words = [], []
        for w in raw:
            if re.fullmatch(r"[a-z0-9]+", w):
                ascii_words.append(w)
            else:
                w = _BLOCK_NOISE.sub("", w)
                if w:
                    words.append(w)
        _blocklist_cache.update(mtime=mtime, words=words, ascii=ascii_words)
    return _blocklist_cache["words"], _blocklist_cache["ascii"]

def _blocked_words():
    words, ascii_words = _blocklist_load()
    return words + ascii_words

def _blocked_hit(sid, role, field, *texts):
    """命中违禁词返回该词并记日志；干净返回 None"""
    raw = "\n".join(t for t in texts if t)
    low = raw.lower()
    flat = _BLOCK_NOISE.sub("", low)
    words, ascii_words = _blocklist_load()
    hit = next((w for w in words if w in flat), None) or \
          next((w for w in ascii_words if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", low)), None)
    if hit:
        try:
            os.makedirs(os.path.dirname(MODERATION_LOG), exist_ok=True)
            with open(MODERATION_LOG, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now(TZ_BEIJING).isoformat(timespec='seconds')}\tshow={sid}\trole={role}\t"
                        f"{field}\t命中「{hit}」\t{raw}\n")
        except OSError:
            pass
    return hit

PHONE_THEMES = {
    'modern': {'name':'现代', 'accent':'#6854bc', 'light':['#ffffff','#f0eff2','#111114','#707079'], 'dark':['#101014','#25252b','#f2f2f5','#a0a0aa'], 'radius':'18px', 'font':'sans-serif'},
    'classic': {'name':'中国古风', 'accent':'#934432', 'light':['#faf5e9','#eee4d2','#332b24','#796857'], 'dark':['#1d1915','#302820','#f0e5d0','#c0aa8e'], 'radius':'10px', 'font':'serif'},
    'scifi': {'name':'科幻', 'accent':'#196a88', 'light':['#edf6fa','#dcebf2','#163340','#516d7c'], 'dark':['#09161f','#142c3a','#dceff8','#90b4c6'], 'radius':'8px', 'font':'sans-serif'},
    'medieval': {'name':'欧洲中世纪', 'accent':'#793746', 'light':['#f7efdd','#eaddc2','#3c2d25','#7c6652'], 'dark':['#21191c','#38272c','#f1e2cb','#c2a58b'], 'radius':'12px', 'font':'serif'},
    'republic': {'name':'民国', 'accent':'#315d50', 'light':['#f5f1e7','#e4e6dc','#24382f','#657266'], 'dark':['#141e1a','#26372e','#e7eee4','#a4b6a6'], 'radius':'6px', 'font':'serif'},
}
PHONE_COPY = {
 'modern': {'messages':'信息','public':'公开播报','moments':'朋友圈','new':'新信息','brand':'长日小手机系统','empty':'这里还很安静，新的消息会留在这里。'},
 'classic': {'messages':'尺素','public':'风闻','moments':'雅集','new':'寄尺素','brand':'长日尺素局','empty':'此间尚无来书，静候故人落笔。'},
 'scifi': {'messages':'通讯','public':'公共频道','moments':'动态频道','new':'建立通讯','brand':'长日通讯终端','empty':'暂无通讯记录，等待新的信号接入。'},
 'medieval': {'messages':'书信','public':'王国公告','moments':'旅人见闻','new':'寄出书信','brand':'长日信使公会','empty':'信匣尚空，信使仍在路上。'},
 'republic': {'messages':'信件','public':'今日公报','moments':'街巷见闻','new':'写信','brand':'长日书信局','empty':'今日尚无来信，且候邮差叩门。'},
}

def phone_theme(sid=None, override=None):
    config = {}
    if sid and override is None:
        row = get_db().execute('SELECT theme_config FROM phone_settings WHERE show_id=?', (sid,)).fetchone()
        try: config = json.loads(row['theme_config'] or '{}') if row else {}
        except (ValueError, TypeError): config = {}
    if not isinstance(config, dict): config = {}
    if override is not None: config = override
    visual = config.get('visual', 'modern'); copy = config.get('copy', 'modern')
    if visual not in PHONE_THEMES: visual = 'modern'
    if copy not in PHONE_COPY: copy = 'modern'
    words = dict(PHONE_COPY[copy])
    custom = config.get('words', {})
    if not isinstance(custom, dict): custom = {}
    for key in words:
        if isinstance(custom.get(key), str) and custom[key].strip(): words[key] = custom[key].strip()[:100]
    return {'visual':visual, 'copy':copy, 'style':PHONE_THEMES[visual], 'words':words, 'custom':custom}

app.jinja_env.globals.update(phone_theme=phone_theme, phone_themes=PHONE_THEMES, phone_copy=PHONE_COPY)


def _phone_web_send_on(db, sid):
    row = db.execute("SELECT web_send FROM phone_settings WHERE show_id=?", (sid,)).fetchone()
    return bool(row and row["web_send"])

_PAUSE_MSG = "通讯暂时关闭了，稍后开放"

def _phone_comm_paused(db, sid):
    """管理员「暂停所有通讯」：短信、礼物、群聊、匿名对话、点歌、朋友圈发帖/评论/点赞、心动信都发不出去，已有内容照常能看"""
    row = db.execute("SELECT comm_paused FROM phone_settings WHERE show_id=?", (sid,)).fetchone()
    return bool(row and row["comm_paused"])

def _comm_pause_json(db, sid):
    """JSON 接口用：暂停中返回 400 响应，否则 None"""
    return _moment_json(False, _PAUSE_MSG) if _phone_comm_paused(db, sid) else None

_PAUSE_FORMS = {"/p/me/send": "phone_flash", "/p/me/alias": "phone_flash", "/p/me/lovemail": "lm_flash"}

@app.before_request
def _phone_comm_pause_guard():
    """表单类的发送接口（短信/礼物、建化名、群聊发言、写心动信）在暂停期间统一拦掉，带提示跳回原页面"""
    if request.method != "POST" or not request.path.startswith("/p/me/"):
        return None
    path = request.path
    key = _PAUSE_FORMS.get(path) or ("phone_flash" if re.fullmatch(r"/p/me/g/\d+/send", path) else None)
    if not key or (path == "/p/me/lovemail" and request.form.get("action") == "revoke"):
        return None
    who = _phone_current()
    if not who or who[1] == PHONE_ADMIN or not _phone_comm_paused(get_db(), who[0]):
        return None
    session[key] = "❌ " + _PAUSE_MSG
    return redirect(request.referrer or url_for("player_phone_inbox"))

def _phone_sync_row(db, sid):
    row = db.execute("SELECT * FROM phone_sync WHERE show_id=?", (sid,)).fetchone()
    if not row:
        return None
    try:
        snap = json.loads(row["snapshot"] or "{}")
    except Exception:
        snap = {}
    return {"snap": snap, "cursor": row["cursor"], "synced_at": row["synced_at"],
            "group_cursor": row["group_cursor"] if "group_cursor" in row.keys() else 0}

def _phone_roster(sync):
    return [r["name"] for r in (sync["snap"].get("roster") or []) if r.get("name")] if sync else []

def _phone_day(sync, now_ms):
    """(计数用的日键, 记录上显示的游戏日, 快照是否新鲜)"""
    game_day = (sync["snap"].get("game_day") or "") if sync else ""
    fresh = bool(sync) and now_ms - sync["synced_at"] < _PHONE_SYNC_FRESH_MS
    if fresh:
        return game_day, game_day, True
    return "日期" + datetime.now(TZ_BEIJING).strftime("%Y-%m-%d"), game_day, False

def _phone_usage(db, sid, sync, role, kind, now_ms):
    """kind: sms|gift → (今日已用, 上次发送时间戳)"""
    day_key, _, fresh = _phone_day(sync, now_ms)
    snap = sync["snap"] if sync else {}
    web_rows = db.execute(
        "SELECT id, timestamp, extra_info FROM extra_events WHERE show_id=? AND type=? AND from_role=? "
        "AND json_extract(extra_info, '$.source')='web'", (sid, kind, role)
    ).fetchall()
    if kind == "sms":
        web_rows = list(web_rows) + [
            {"id": 0, "timestamp": r["timestamp"], "extra_info": json.dumps({"day_key": r["day_key"]})}
            for r in db.execute("SELECT timestamp, day_key FROM phone_silent WHERE show_id=? AND from_role=?", (sid, role))
        ]
    used = int(((snap.get("counts") or {}).get(kind) or {}).get(role, 0)) if fresh else 0
    last = int(((snap.get("last") or {}).get(kind) or {}).get(role, 0) or 0)
    cursor = sync["cursor"] if sync else 0
    for r in web_rows:
        info = json.loads(r["extra_info"] or "{}")
        last = max(last, int(r["timestamp"] or 0))
        if info.get("day_key") != day_key:
            continue
        # 新鲜时插件已取走的（id<=cursor，静默拉黑那张表插件不取，id 记 0 → 这里要算）已含在上报的次数里
        if fresh and r["id"] and r["id"] <= cursor:
            continue
        used += 1
    if kind == "sms":  # 群聊一条算 1 次短信；插件取走的（id<=group_cursor）已含在上报的次数里
        gcur = (sync or {}).get("group_cursor") or 0
        for r in db.execute("SELECT id, created_at, day_key FROM phone_group_msgs WHERE show_id=? AND from_role=? AND kind='msg'",
                            (sid, role)):
            last = max(last, int(r["created_at"] or 0))
            if r["day_key"] == day_key and not (fresh and r["id"] <= gcur):
                used += 1
    return used, last

def _phone_status(db, sid, role):
    """给页面用：能不能发、为什么不能、今日次数"""
    now = int(time.time() * 1000)
    show = db.execute("SELECT * FROM shows WHERE id=?", (sid,)).fetchone()
    sync = _phone_sync_row(db, sid)
    st = {"can": False, "why": "", "sms": None, "gift": None}
    if _phone_comm_paused(db, sid):
        st["why"] = _PAUSE_MSG
        return st
    if not _phone_web_send_on(db, sid):
        return st
    if not sync:
        st["why"] = "机器人还没同步过规则，暂时不能从网页发送"
        return st
    if _schedule_zone(dict(show)) != "main":
        st["why"] = "不在档期内，暂时不能发送"
        return st
    rules = sync["snap"].get("rules") or {}
    st["can"] = True
    if rules.get("sms_enabled", True):
        used, _ = _phone_usage(db, sid, sync, role, "sms", now)
        st["sms"] = (used, int((rules.get("chaos") or {}).get("dailyLimit", 5)))
    st["preset_only"] = int(rules.get("gift_mode", 0)) == 1
    if rules.get("gift_enabled", True):
        used, _ = _phone_usage(db, sid, sync, role, "gift", now)
        st["gift"] = (used, int(rules.get("gift_daily_limit", 100)))
    return st

def _chaos_erode(content, cfg):
    r = secrets.SystemRandom()
    if r.random() < float(cfg.get("antonymReplace", 0)) / 100 and content:
        arr = list(content)
        for _ in range(int(len(arr) * (0.15 + r.random() * 0.1))):
            arr[r.randrange(len(arr))] = r.choice(_CHAOS_CHAR_POOL)
        content = "".join(arr)
    if r.random() < float(cfg.get("loseContent", 0)) / 100 and len(content) > 5:
        content = content[:int(len(content) * 0.7)] + "……"
    if r.random() < float(cfg.get("blackoutText", 0)) / 100:
        content = "".join(r.choice(_BLACKOUT_CHARS) if r.random() < 0.2 else c for c in content)
    if r.random() < float(cfg.get("reverseOrder", 0)) / 100:
        parts = re.findall(r"[^。！？!?\n]+[。！？!?\n]*", content)
        if len(parts) > 1:
            original = "".join(parts)
            r.shuffle(parts)
            shuffled = "".join(parts)
            if shuffled == original:
                shuffled = "".join(parts[1:]) + parts[0]
            content = shuffled
    return content

_BLOCK_UNDO_MS = 2 * 3600 * 1000   # 跟群里「取消拉黑」一样：拉黑满 2 小时才能解除

def _phone_effective_blocks(db, sid, snap):
    """快照里的拉黑名单 + 网页上还没被机器人取走的拉黑/解除（按先后叠上去）。机器人处理完、下一份快照带上时同一次同步里标 done，不会重复算"""
    blocks = {(b.get("blocker"), b.get("blocked")): dict(b) for b in (snap.get("blocks") or [])}
    for op in db.execute("SELECT * FROM phone_block_ops WHERE show_id=? AND done=0 ORDER BY id", (sid,)):
        key = (op["blocker"], op["target"])
        if op["action"] == "block":  # 再拉一次（换静默模式）不重新计时，同群里
            since = (blocks.get(key) or {}).get("since") or op["created_at"]
            blocks[key] = {"blocker": op["blocker"], "blocked": op["target"], "silent": bool(op["silent"]), "since": since}
        else:
            blocks.pop(key, None)
    return list(blocks.values())

def _phone_block_state(db, sid, owner, other):
    """对话页「⋯」菜单用：能不能在这里实名拉黑 TA、现在拉黑了没有、还要等多久才能解除；不能操作返回 None"""
    sync = _phone_sync_row(db, sid)
    if not sync or not sync["snap"].get("block_write") or owner == PHONE_ADMIN:
        return None
    if other == owner or other not in _phone_roster(sync):
        return None
    b = _phone_blocked(dict(sync["snap"], blocks=_phone_effective_blocks(db, sid, sync["snap"])), owner, other)
    if not b:
        return {"blocked": False}
    wait = int(b.get("since") or 0) + _BLOCK_UNDO_MS - int(time.time() * 1000)
    return {"blocked": True, "silent": b["silent"], "wait_min": max(0, math.ceil(wait / 60000))}

def _phone_blocked(snap, blocker, blocked):
    for b in snap.get("blocks") or []:
        if b.get("blocker") == blocker and b.get("blocked") == blocked:
            return {"silent": bool(b.get("silent")), "since": b.get("since") or 0}
    return None

_PHONE_GIFT_NAME_MAX = 20

def _sms_chaos_route(roster, owner, to_name, text, chaos, rnd, own_sig):
    """短信混乱效果前半段（顺序同插件）：内容侵蚀 → 落款混乱 → 误投；返回 (送达内容, 落款, 实际收件人)"""
    eroded = _chaos_erode(text, chaos)
    signature = own_sig
    if rnd.random() < float(chaos.get("mistakenSignature", 0)) / 100:
        others = [n for n in roster if n != owner]
        if others:
            signature = f"落款：{rnd.choice(others)}"
    true_to = to_name
    if rnd.random() < float(chaos.get("misdelivery", 0)) / 100:
        others = [n for n in roster if n != to_name]
        if others:
            true_to = rnd.choice(others)
    return eroded, signature, true_to

def _sms_chaos_torn(roster, owner, true_to, eroded, chaos, rnd):
    """残页：信被撕成两半，后半页（带落款）落到第三人手里"""
    if rnd.random() < float(chaos.get("tornPage", 0)) / 100 and len(eroded) >= 10:
        others = [n for n in roster if n not in (owner, true_to)]
        if others:
            cut = math.ceil(len(eroded) / 2)
            return {"holder": rnd.choice(others), "first": eroded[:cut], "second": eroded[cut:]}
    return None

def _phone_send(db, sid, tid, owner, kind, to_name, text, gift_name="", preset_id=""):
    """执行一次网页发送，返回 (是否发出, 给发件人看的一句话)；静默拉黑也算「发出」，发件人看不出区别。规则与插件的
    handleNaturalChaosLetter / handleNaturalGift 对齐；群里才有意义的部分（公开播报、截信器/回音壁道具、
    撤回、礼品店编号礼物）不做。"""
    now = int(time.time() * 1000)
    show = dict(db.execute("SELECT * FROM shows WHERE id=?", (sid,)).fetchone())
    sync = _phone_sync_row(db, sid)
    if not _phone_web_send_on(db, sid):
        return False, "❌ 网页发送没有开放"
    if not sync:
        return False, "❌ 机器人还没同步过规则，暂时不能从网页发送"
    if _schedule_zone(show) != "main":
        return False, "❌ 不在档期内，暂时不能发送"
    snap  = dict(sync["snap"], blocks=_phone_effective_blocks(db, sid, sync["snap"]))
    rules = snap.get("rules") or {}
    roster = _phone_roster(sync)
    text = (text or "").strip()
    gift_name = (gift_name or "").strip()
    preset_id = (preset_id or "").strip()
    preset = None
    if kind == "gift" and preset_id:
        # 从图鉴送：跟群里「送礼 某人 #001」一样，只能送图鉴里有的，内容就是预设的那段文字，不能再写留言
        preset = _preset_gifts(db, sid).get(preset_id)
        if not preset:
            return False, "❌ 这件礼物已经下架了"
        if preset_id not in _shop_catalog(db, sid, sync, owner):
            return False, f"🔒 「{preset.get('name', '')}」不在你的图鉴里，先去礼品店收集"
        gift_name, text = f"「{preset.get('name', '')}」", preset.get("content", "")
    # 短信：内容必填；网页礼物：礼物名必填（20 字内），留言可以不填
    if kind == "gift" and not preset:
        if not gift_name:
            return False, "❌ 请写上送什么礼物"
        if len(gift_name) > _PHONE_GIFT_NAME_MAX:
            return False, f"❌ 礼物名最多 {_PHONE_GIFT_NAME_MAX} 字"
    elif not text:
        return False, "❌ 内容不能为空"
    if len(text) > _PHONE_MAX_LEN:
        return False, f"❌ 太长了，最多 {_PHONE_MAX_LEN} 字"
    if not preset and _blocked_hit(sid, owner, "礼物" if kind == "gift" else "短信", gift_name, text):
        return False, BLOCKED_MSG
    if owner not in roster:
        return False, "❌ 找不到你的角色，等机器人下一次同步后再试"
    if to_name == owner:
        return False, "📱 短信不可发给自己。" if kind == "sms" else "🌸 礼不自赠，情当他寄。"
    if to_name not in roster:
        return False, f"❌ 未找到收件人：{to_name}"
    off = set((snap.get("feature_off") or {}).get(owner) or [])
    day_key, game_day, _ = _phone_day(sync, now)
    rnd = secrets.SystemRandom()

    if kind == "sms":
        if not rules.get("sms_enabled", True):
            return False, "🕊️ 寄信功能已关闭。"
        if "sms" in off:
            return False, "🕊️ 你被限制使用寄信功能。"
        chaos = rules.get("chaos") or {}
        limit = int(chaos.get("dailyLimit", 5))
        cooldown_ms = max(int(rules.get("mail_cooldown_min", 60)) * 60000, _PHONE_MIN_GAP_MS)
        used, last = _phone_usage(db, sid, sync, owner, "sms", now)
        if now - last < cooldown_ms:
            return False, f"⏳ 鸽子正在休息，请 {math.ceil((cooldown_ms - (now - last)) / 60000)} 分钟后再试"
        if used >= limit:
            return False, f"🕊️ 今日寄信次数已达上限({limit})"
        # 落款 / 误投 / 拉黑 / 侵蚀 / 残页，顺序同插件
        eroded, signature, true_to = _sms_chaos_route(roster, owner, to_name, text, chaos, rnd, f"落款：{owner}")
        blk = _phone_blocked(snap, true_to, owner)
        if blk and not blk["silent"]:
            return False, f"❌ {true_to} 已拒绝你的联络。"
        receipt = f"🕊️ 信件已由鸽子衔往 {to_name} 处。今日已发 {used + 1}/{limit}。"
        if blk:  # 静默拉黑：伪装成功，照常占次数和冷却
            db.execute("INSERT INTO phone_silent (show_id, from_role, to_role, content, timestamp, game_day, day_key) "
                       "VALUES (?,?,?,?,?,?,?)", (sid, owner, to_name, text, now, game_day, day_key))
            db.commit()
            return True, receipt
        torn = _sms_chaos_torn(roster, owner, true_to, eroded, chaos, rnd)
        delivered = (torn["first"] + "\n（信纸的后半页不知去向……）") if torn else eroded
        info = {
            "source": "web", "day_key": day_key,
            "delivered": delivered, "signature": signature, "intended_to": to_name,
            "is_misdelivered": true_to != to_name, "is_content_chaos": delivered != text,
            "is_signature_chaos": signature != f"落款：{owner}", "is_torn": bool(torn),
            "torn_holder": torn["holder"] if torn else None,
            "torn_second_half": torn["second"] if torn else None,
        }
        # 公开播报：跟群里一样的开关和概率；网页发的只进网页「公开播报」，不发公告群
        info["isPublic"] = bool(rules.get("sms_public")) and rnd.randint(1, 100) <= int(chaos.get("publicChance", 50))
        info["hide_receiver"] = info["isPublic"] and bool(rules.get("hide_receiver"))
        info["public_show_effect"] = bool(chaos.get("publicShowEffect"))
        info["is_chaos"] = info["is_misdelivered"] or info["is_content_chaos"] or info["is_signature_chaos"] or bool(torn)
        _phone_insert_event(db, sid, tid, "sms", owner, true_to, text, info, now, game_day)
        return True, receipt

    # gift：自定义礼物，或从图鉴送预设礼物（「仅允许预设礼物」模式下只能从图鉴送）
    if not rules.get("gift_enabled", True):
        return False, "🎁 礼物功能已被禁用。"
    if int(rules.get("gift_mode", 0)) == 1 and not preset:
        return False, "❌ 当前只能送图鉴里的礼物"
    win = rules.get("gift_window")
    if win:
        h = datetime.now(TZ_BEIJING).hour
        if not (int(win["start"]) <= h < int(win["end"])):
            return False, f"⚠️ 该功能当前不可用，开放时间为 {int(win['start']):02d}:00–{int(win['end']):02d}:00。"
    if "gift" in off:
        return False, "🎁 你被限制使用礼物功能。"
    limit = int(rules.get("gift_daily_limit", 100))
    cooldown_ms = max(int(rules.get("gift_cooldown_min", 30)) * 60000, _PHONE_MIN_GAP_MS)
    used, last = _phone_usage(db, sid, sync, owner, "gift", now)
    if now - last < cooldown_ms:
        return False, f"⏳ 快递员仍在路上，请等待 {math.ceil((cooldown_ms - (now - last)) / 1000)} 秒后再送~"
    if used >= limit:
        return False, f"🎁 今日送礼次数已达上限({limit})。"
    chaos = rules.get("chaos") or {}
    true_to, lost = to_name, False
    if rnd.random() * 100 < float(chaos.get("giftLost", 0)):
        lost = True
    elif rnd.random() * 100 < float(chaos.get("giftMisdelivery", 0)):
        others = [n for n in roster if n not in (to_name, owner)]
        if others:
            true_to = rnd.choice(others)
    blk = _phone_blocked(snap, true_to, owner)
    if blk and not blk["silent"]:
        return False, f"❌ {true_to} 已拒绝你的联络。"
    if blk:
        lost = True  # 静默拉黑复用「礼物丢失」：不投递，发件人看到的跟成功一样
    is_public = (not lost) and bool(rules.get("gift_public")) and rnd.randint(1, 100) <= int(rules.get("gift_public_chance", 50))
    # 网页礼物分「礼物」「留言」两栏：giftName 是玩家写的礼物名，content 是留言（群里送的自定义礼物仍是
    # 「一份特别的礼物」+ 寄语，格式不变）
    info = {"source": "web", "day_key": day_key, "giftName": gift_name, "intended_to": to_name,
            "isLost": lost, "isPublic": is_public, "hide_receiver": is_public and bool(rules.get("hide_receiver"))}
    if preset:
        info["preset_id"] = preset_id
    _phone_insert_event(db, sid, tid, "gift", owner, true_to, text, info, now, game_day)
    # 收到即入图鉴：跟插件一样 50% 概率把这件预设礼物收进实际收件人的图鉴
    if (preset and not lost and (snap.get("shop") or {}).get("catalog_on_receive")
            and preset_id not in _shop_catalog(db, sid, sync, true_to) and rnd.random() < 0.5):
        db.execute("INSERT INTO phone_shop_log (show_id, role_name, unlocked, created_at) VALUES (?,?,?,?)",
                   (sid, true_to, json.dumps([preset_id]), now))
        db.commit()
    shown = gift_name if gift_name.startswith("「") else f"「{gift_name}」"  # 图鉴礼物名本身带「」（跟群里一致）
    return True, f"🎁 已成功将{shown}送往「{to_name}」的房间。\n(今日第 {used + 1}份)"

# ── 网页礼品店 / 图鉴 / 预设礼物 ──────────────────────────────────────────────────
# 规则照插件 cmd_view_preset_gifts：每人一个「今日货架」，隔 shop_refresh_hours 小时刷新成一件图鉴里还没有的，
# 逛到就收进图鉴，50% 再顺带一件；全收齐了就不再刷新。群里和网页共用同一个货架和图鉴：
# 插件同步时上报 catalogs / displays，网页这边新增的解锁和货架写进 phone_shop_log，插件下次同步取走写回自己的 KV。
# 预设礼物的名字和内容来自网页「礼品店管理」（site_config.preset_gifts，插件也是从这里同步的）。
def _preset_gifts(db, sid):
    try:
        return json.loads(get_flat_config(db, sid).get("preset_gifts") or "{}") or {}
    except Exception:
        return {}

def _shop_logs(db, sid, role):
    return db.execute("SELECT * FROM phone_shop_log WHERE show_id=? AND role_name=? ORDER BY id", (sid, role)).fetchall()

def _shop_catalog(db, sid, sync, role):
    snap = sync["snap"] if sync else {}
    owned = set(((snap.get("catalogs") or {}).get(role)) or [])
    for r in _shop_logs(db, sid, role):
        owned.update(json.loads(r["unlocked"] or "[]"))
    return owned

def _shop_display(db, sid, sync, role):
    snap = sync["snap"] if sync else {}
    disp = ((snap.get("displays") or {}).get(role)) or None
    for r in _shop_logs(db, sid, role):
        if r["display_gift"] and (not disp or r["refreshed_at"] > int(disp.get("refreshedAt") or 0)):
            disp = {"giftId": r["display_gift"], "refreshedAt": r["refreshed_at"]}
    return disp

def _shop_visit(db, sid, role):
    """逛一次礼品店（跟群里发「礼品店」一样）。返回 {state, gifts:[新收的], current, next_hours, owned, total}"""
    sync = _phone_sync_row(db, sid)
    presets = _preset_gifts(db, sid)
    ids = list(presets.keys())
    res = {"state": "empty", "gifts": [], "current": None, "next_hours": 0, "total": len(ids)}
    owned = _shop_catalog(db, sid, sync, role)
    res["owned"] = len(owned & set(ids))
    if not ids:
        return res
    hours = int(((sync["snap"].get("shop") or {}).get("refresh_hours") or 24) if sync else 24)
    now = int(time.time() * 1000)
    disp = _shop_display(db, sid, sync, role)
    rnd = secrets.SystemRandom()
    new_disp = None
    if not disp or now - int(disp.get("refreshedAt") or 0) > hours * 3600 * 1000:
        unowned = [i for i in ids if i not in owned]
        if unowned:
            new_disp = {"giftId": rnd.choice(unowned), "refreshedAt": now}
            disp = new_disp
    cur = disp.get("giftId") if disp else None
    if not cur or cur not in presets:
        res["state"] = "complete" if res["owned"] >= len(ids) else "nothing"
        return res
    res["current"] = {"id": cur, **presets[cur]}
    res["next_hours"] = max(1, math.ceil((int(disp["refreshedAt"]) + hours * 3600 * 1000 - now) / 3600000))
    unlocked = []
    if cur in owned:
        res["state"] = "owned"
    else:
        unlocked.append(cur)
        rest = [i for i in ids if i != cur and i not in owned]
        if rest and rnd.random() < 0.5:
            unlocked.append(rnd.choice(rest))
        res["state"] = "new"
        res["gifts"] = [{"id": i, **presets[i]} for i in unlocked]
        res["owned"] += len(unlocked)
    if unlocked or new_disp:
        db.execute("INSERT INTO phone_shop_log (show_id, role_name, unlocked, display_gift, refreshed_at, created_at) VALUES (?,?,?,?,?,?)",
                   (sid, role, json.dumps(unlocked), disp["giftId"], int(disp["refreshedAt"]), now))
        db.commit()
    return res

@app.route("/p/me/shop")
def player_shop():
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    if owner == PHONE_ADMIN:
        return redirect(url_for("admin_phone_index"))
    db = get_db()
    sync = _phone_sync_row(db, sid)
    if not sync or "catalogs" not in (sync["snap"] or {}):
        return render_template("phone.html", mode="shop", owner=owner, sid=sid, shop=None, catalog=[],
                               why="礼品店要等机器人升级到新版本、同步过一次才能在网页上逛")
    with _phone_send_lock:
        visit = _shop_visit(db, sid, owner) if request.args.get("view") != "book" else None
    presets = _preset_gifts(db, sid)
    owned = _shop_catalog(db, sid, _phone_sync_row(db, sid), owner)
    catalog = [{"id": i, "owned": i in owned, **g} for i, g in presets.items()]
    return render_template("phone.html", mode="shop", owner=owner, sid=sid, shop=visit, catalog=catalog, why=None,
                           owned_count=sum(1 for g in catalog if g["owned"]))

# ── 匿名对话（化名）────────────────────────────────────────────────────────────
# 群里的匿名就是普通的「[署名]短信」；网页发送打开时，网页上可以用化名开一段能来回聊的对话：
#   · 「新信息」页勾选匿名、写化名、选收件人；对同一个人最多 3 个化名（外加真名）；同一收件人下化名不能重名；
#   · 化名主人那边的对话 key 是「对方＠化名」，收件人那边就是化名；收件人回复会送回化名主人；
#   · 跟短信共用每日次数和冷却；拉黑按真实身份；不加任何混乱效果、不公开播报（否则容易穿帮或串线）；
#   · 只有管理身份能看到化名背后是谁。
_ALIAS_MAX_PER_TARGET = 3
_ALIAS_MAX_LEN        = 10
_ALIAS_RESERVED       = {"未知号码", "点歌台", "大家", "所有人", "管理员", "小手机", "有人"}

def _alias_resolve(db, sid, owner, key):
    """对话 key → (真实收件人, 化名行, 方向)；不是匿名对话返回 None。out=化名主人发给对方，back=对方回给化名"""
    if "＠" in key:
        target, _, alias = key.partition("＠")
        row = db.execute("SELECT * FROM phone_aliases WHERE show_id=? AND owner_role=? AND target_role=? AND alias_name=?",
                         (sid, owner, target, alias)).fetchone()
        return (target, row, "out") if row else None
    row = db.execute("SELECT * FROM phone_aliases WHERE show_id=? AND target_role=? AND alias_name=?",
                     (sid, owner, key)).fetchone()
    if not row:
        # 误送 / 撕信把化名的信带到了别人手里：收到过这个化名来信的人也能回它
        ev = db.execute("""SELECT json_extract(extra_info, '$.alias_id') AS aid FROM extra_events
                           WHERE show_id=? AND type='sms' AND json_extract(extra_info, '$.alias_name')=?
                             AND json_extract(extra_info, '$.alias_dir')='out'
                             AND (to_role=? OR json_extract(extra_info, '$.torn_holder')=?)
                           ORDER BY id DESC LIMIT 1""", (sid, key, owner, owner)).fetchone()
        if ev and ev["aid"]:
            row = db.execute("SELECT * FROM phone_aliases WHERE id=? AND show_id=?", (ev["aid"], sid)).fetchone()
    return (row["owner_role"], row, "back") if row and row["owner_role"] != owner else None

def _alias_create(db, sid, owner, target, name):
    """建化名（或复用自己对这个人已有的同名化名）→ (ok, 提示或对话 key)"""
    name = (name or "").strip()
    roster = _phone_roster(_phone_sync_row(db, sid))
    if target not in roster or target == owner:
        return False, "❌ 选一个要联系的人"
    if not name:
        return False, "❌ 写一个化名"
    if len(name) > _ALIAS_MAX_LEN:
        return False, f"❌ 化名最多 {_ALIAS_MAX_LEN} 字"
    if "＠" in name or "@" in name or name in _ALIAS_RESERVED or name in roster:
        return False, "❌ 这个化名不能用，换一个"
    if _blocked_hit(sid, owner, "化名", name):
        return False, BLOCKED_MSG
    mine = db.execute("SELECT alias_name FROM phone_aliases WHERE show_id=? AND owner_role=? AND target_role=?",
                      (sid, owner, target)).fetchall()
    if name in {r["alias_name"] for r in mine}:
        return True, f"{target}＠{name}"
    if len(mine) >= _ALIAS_MAX_PER_TARGET:
        return False, f"❌ 对 {target} 最多用 {_ALIAS_MAX_PER_TARGET} 个化名，已经用了：" + "、".join(r["alias_name"] for r in mine)
    if db.execute("SELECT 1 FROM phone_aliases WHERE show_id=? AND target_role=? AND alias_name=?", (sid, target, name)).fetchone():
        return False, "❌ 这个化名已经被别人用了，换一个"
    db.execute("INSERT INTO phone_aliases (show_id, owner_role, target_role, alias_name, created_at) VALUES (?,?,?,?,?)",
               (sid, owner, target, name, int(time.time() * 1000)))
    db.commit()
    return True, f"{target}＠{name}"

def _alias_send(db, sid, tid, owner, key, text):
    """匿名对话里发一条：开关/档期/功能权限/冷却/上限/违禁词同网页短信，混乱效果也跟群里一样；
    但不看群里按真实身份的拉黑——不然「拉黑某人看化名对话断不断」就能反查出化名是谁。匿名对话有自己的「拉黑并结束」。"""
    res = _alias_resolve(db, sid, owner, key)
    if not res:
        return False, "❌ 找不到这段匿名对话"
    real_to, arow, direction = res
    if arow["blocked_by"]:
        return False, "❌ 这段匿名对话已经结束了"
    shown_to = real_to if direction == "out" else arow["alias_name"]  # 回化名时绝不能露出真名
    now = int(time.time() * 1000)
    show = dict(db.execute("SELECT * FROM shows WHERE id=?", (sid,)).fetchone())
    sync = _phone_sync_row(db, sid)
    if not _phone_web_send_on(db, sid) or not sync:
        return False, "❌ 网页发送没有开放"
    if _schedule_zone(show) != "main":
        return False, "❌ 不在档期内，暂时不能发送"
    snap, rules = sync["snap"], (sync["snap"].get("rules") or {})
    roster = _phone_roster(sync)
    text = (text or "").strip()
    if not text:
        return False, "❌ 内容不能为空"
    if len(text) > _PHONE_MAX_LEN:
        return False, f"❌ 太长了，最多 {_PHONE_MAX_LEN} 字"
    if _blocked_hit(sid, owner, "匿名短信", text):
        return False, BLOCKED_MSG
    if not rules.get("sms_enabled", True):
        return False, "🕊️ 寄信功能已关闭。"
    if "sms" in set((snap.get("feature_off") or {}).get(owner) or []):
        return False, "🕊️ 你被限制使用寄信功能。"
    chaos = rules.get("chaos") or {}
    limit = int(chaos.get("dailyLimit", 5))
    cooldown_ms = max(int(rules.get("mail_cooldown_min", 60)) * 60000, _PHONE_MIN_GAP_MS)
    used, last = _phone_usage(db, sid, sync, owner, "sms", now)
    if now - last < cooldown_ms:
        return False, f"⏳ 鸽子正在休息，请 {math.ceil((cooldown_ms - (now - last)) / 60000)} 分钟后再试"
    if used >= limit:
        return False, f"🕊️ 今日寄信次数已达上限({limit})"
    day_key, game_day, _ = _phone_day(sync, now)
    rnd = secrets.SystemRandom()
    own_sig = f"落款：{arow['alias_name'] if direction == 'out' else owner}"
    eroded, signature, true_to = _sms_chaos_route(roster, owner, real_to, text, chaos, rnd, own_sig)
    torn = _sms_chaos_torn(roster, owner, true_to, eroded, chaos, rnd)
    delivered = (torn["first"] + "\n（信纸的后半页不知去向……）") if torn else eroded
    is_public = bool(rules.get("sms_public")) and rnd.randint(1, 100) <= int(chaos.get("publicChance", 50))
    info = {"source": "web", "day_key": day_key, "delivered": delivered, "signature": signature, "intended_to": real_to,
            "is_misdelivered": true_to != real_to, "is_content_chaos": delivered != text,
            "is_signature_chaos": signature != own_sig, "is_torn": bool(torn),
            "torn_holder": torn["holder"] if torn else None, "torn_second_half": torn["second"] if torn else None,
            "isPublic": is_public, "hide_receiver": is_public and bool(rules.get("hide_receiver")),
            "public_show_effect": bool(chaos.get("publicShowEffect")),
            # 公开播报只写化名那一侧：化名 → 对方 / 对方 → 化名，真名永远不上播报
            "public_from": arow["alias_name"] if direction == "out" else owner,
            "public_to": arow["target_role"] if direction == "out" else arow["alias_name"],
            "alias_id": arow["id"], "alias_name": arow["alias_name"], "alias_owner": arow["owner_role"],
            "alias_target": arow["target_role"], "alias_dir": direction}
    info["is_chaos"] = info["is_misdelivered"] or info["is_content_chaos"] or info["is_signature_chaos"] or bool(torn)
    _phone_insert_event(db, sid, tid, "sms", owner, true_to, text, info, now, game_day)
    return True, f"🕊️ 信件已由鸽子衔往 {shown_to} 处。今日已发 {used + 1}/{limit}。"

_ALIAS_UNBLOCK_MS = 2 * 3600 * 1000

def _alias_state(db, sid, owner, key):
    """对话页用：这段匿名对话有没有被拉黑结束、是不是我拉黑的、还要多久才能解除"""
    res = _alias_resolve(db, sid, owner, key)
    if not res:
        return None
    row = res[1]
    party = "owner" if owner == row["owner_role"] else ("target" if owner == row["target_role"] else None)
    wait = max(0, row["blocked_at"] + _ALIAS_UNBLOCK_MS - int(time.time() * 1000)) if row["blocked_by"] else 0
    return {"dir": res[2], "party": party, "blocked": bool(row["blocked_by"]),
            "by_me": bool(row["blocked_by"]) and row["blocked_by"] == party, "wait_min": math.ceil(wait / 60000)}

@app.route("/p/me/alias/block", methods=["POST"])
def player_alias_block():
    """匿名对话里「拉黑并结束」/「解除拉黑」：只作用于这个化名，不牵涉任何真实身份；拉黑满 2 小时才能解除"""
    who = _phone_current()
    if not who or who[1] == PHONE_ADMIN:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    key = request.form.get("key", "")
    if not hmac.compare_digest(request.form.get("csrf", ""), session.get("phone_csrf", "") or "-"):
        session["phone_flash"] = "❌ 页面过期了，刷新后再试"
        return redirect(url_for("player_phone_thread", other=key))
    db = get_db()
    res = _alias_resolve(db, sid, owner, key)
    row = res[1] if res else None
    party = row and ("owner" if owner == row["owner_role"] else ("target" if owner == row["target_role"] else None))
    if not party:  # 误送/撕信收到信的第三人不能结束别人的对话
        session["phone_flash"] = "❌ 这段对话不能由你结束"
        return redirect(url_for("player_phone_thread", other=key))
    now = int(time.time() * 1000)
    if request.form.get("action") == "unblock":
        if row["blocked_by"] != party:
            session["phone_flash"] = "❌ 只有拉黑的一方能解除"
        elif now - row["blocked_at"] < _ALIAS_UNBLOCK_MS:
            session["phone_flash"] = f"⏳ 拉黑满 2 小时才能解除，还要等 {math.ceil((row['blocked_at'] + _ALIAS_UNBLOCK_MS - now) / 60000)} 分钟"
        else:
            db.execute("UPDATE phone_aliases SET blocked_by='', blocked_at=0 WHERE id=?", (row["id"],)); db.commit()
            session["phone_flash"] = "✅ 已解除拉黑，这段匿名对话可以继续了"
    elif not row["blocked_by"]:
        db.execute("UPDATE phone_aliases SET blocked_by=?, blocked_at=? WHERE id=?", (party, now, row["id"])); db.commit()
        session["phone_flash"] = "🚫 已拉黑，这段匿名对话结束了。满 2 小时后可以在这里解除"
    return redirect(url_for("player_phone_thread", other=key))

@app.route("/p/me/alias", methods=["POST"])
def player_alias_create():
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    if owner == PHONE_ADMIN:
        return redirect(url_for("admin_phone_index"))
    if not hmac.compare_digest(request.form.get("csrf", ""), session.get("phone_csrf", "") or "-"):
        session["phone_flash"] = "❌ 页面过期了，刷新后再试"
        return redirect(url_for("player_phone_new"))
    db = get_db()
    if not _phone_status(db, sid, owner)["can"]:
        return redirect(url_for("player_phone_inbox"))
    with _phone_send_lock:
        ok, res = _alias_create(db, sid, owner, request.form.get("to", "").strip(), request.form.get("alias", ""))
    if not ok:
        session["phone_flash"] = res
        return redirect(url_for("player_phone_new"))
    return redirect(url_for("player_phone_thread", other=res))

def _phone_insert_event(db, sid, tid, etype, from_role, to_role, content, info, ts, game_day):
    db.execute("""
        INSERT INTO extra_events
          (show_id,tenant_id,session_id,type,from_role,to_role,content,extra_info,timestamp,game_day)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (sid, tid, "", etype, from_role, to_role, content, json.dumps(info, ensure_ascii=False), ts, game_day))
    db.commit()

def _phone_csrf():
    tok = session.get("phone_csrf")
    if not tok:
        tok = session["phone_csrf"] = secrets.token_urlsafe(24)
    return tok

@app.route("/p/me/send", methods=["POST"])
def player_phone_send():
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    if owner == PHONE_ADMIN:
        return redirect(url_for("admin_phone_index"))
    to_name = request.form.get("to", "").strip()
    back = url_for("player_phone_thread", other=to_name) if to_name else url_for("player_phone_inbox")
    if not hmac.compare_digest(request.form.get("csrf", ""), session.get("phone_csrf", "") or "-"):
        session["phone_flash"] = "❌ 页面过期了，刷新后再发"
        session["phone_draft"] = request.form.get("text", "")[:_PHONE_MAX_LEN]
        session["phone_draft_kind"] = "gift" if request.form.get("kind") == "gift" else "sms"
        session["phone_draft_gift"] = request.form.get("gift_name", "")[:_PHONE_GIFT_NAME_MAX]
        return redirect(back)
    kind = "gift" if request.form.get("kind") == "gift" else "sms"
    db  = get_db()
    tid = db.execute("SELECT tenant_id FROM shows WHERE id=?", (sid,)).fetchone()["tenant_id"]
    with _phone_send_lock:  # 查次数和写入之间不能被另一个请求插队，否则连点能超上限
        if _alias_resolve(db, sid, owner, to_name):  # 匿名对话
            ok, msg = _alias_send(db, sid, tid, owner, to_name, request.form.get("text", ""))
        else:
            ok, msg = _phone_send(db, sid, tid, owner, kind, to_name, request.form.get("text", ""),
                                  request.form.get("gift_name", ""), request.form.get("preset_id", ""))
    session["phone_flash"] = msg
    session["phone_sent"] = ok
    if not ok:  # 没发出去，把草稿留着
        session["phone_draft"] = request.form.get("text", "")[:_PHONE_MAX_LEN]
        session["phone_draft_kind"] = kind
        session["phone_draft_gift"] = request.form.get("gift_name", "")[:_PHONE_GIFT_NAME_MAX]
    return redirect(back)

@app.route("/p/me/new")
def player_phone_new():
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    db = get_db()
    st = _phone_status(db, sid, owner)
    if not st["can"]:
        return redirect(url_for("player_phone_inbox"))
    contacts = sorted(n for n in _phone_roster(_phone_sync_row(db, sid)) if n != owner)
    return render_template("phone.html", mode="new", owner=owner, sid=sid, contacts=contacts, csrf=_phone_csrf(),
                           flash=session.pop("phone_flash", None), alias_max=_ALIAS_MAX_PER_TARGET, alias_len=_ALIAS_MAX_LEN)

@app.route("/api/phone/sync", methods=["POST"])
def api_phone_sync():
    """插件每 30 秒调一次：上报规则快照，取走 after 之后的网页记录（插件拿去计次数/冷却/互动统计）"""
    tid  = get_tenant_from_token()
    show = get_current_show_for_tenant(tid)
    if not show:
        return jsonify({"ok": False, "error": "no show"}), 503
    data = request.json or {}
    snap = data.get("snapshot") or {}
    if not isinstance(snap, dict):
        return jsonify({"ok": False, "error": "bad snapshot"}), 400
    try:
        after = int(data.get("after") or 0)
    except (TypeError, ValueError):
        after = 0
    db  = get_db()
    now = int(time.time() * 1000)
    try:
        group_after = int(data.get("group_after") or 0)
    except (TypeError, ValueError):
        group_after = 0
    db.execute("""
        INSERT INTO phone_sync (show_id, tenant_id, snapshot, cursor, synced_at, group_cursor) VALUES (?,?,?,?,?,?)
        ON CONFLICT(show_id) DO UPDATE SET snapshot=excluded.snapshot, cursor=excluded.cursor, synced_at=excluded.synced_at,
                                           group_cursor=excluded.group_cursor
    """, (show["id"], tid, json.dumps(snap, ensure_ascii=False), after, now, group_after))
    db.commit()
    rows = db.execute("""
        SELECT id, type, from_role, to_role, timestamp, game_day, extra_info FROM extra_events
        WHERE show_id=? AND id>? AND type IN ('sms','gift') AND json_extract(extra_info, '$.source')='web'
        ORDER BY id LIMIT 200
    """, (show["id"], after)).fetchall()
    events = []
    for r in rows:
        info = json.loads(r["extra_info"] or "{}")
        events.append({"id": r["id"], "type": r["type"], "from_role": r["from_role"], "to_role": r["to_role"],
                       "timestamp": r["timestamp"], "day_key": info.get("day_key", ""),
                       "lost": bool(info.get("isLost"))})
    try:
        shop_after = int(data.get("shop_after") or 0)
    except (TypeError, ValueError):
        shop_after = 0
    shop_events = [{"id": r["id"], "role": r["role_name"], "unlocked": json.loads(r["unlocked"] or "[]"),
                    "display": ({"giftId": r["display_gift"], "refreshedAt": r["refreshed_at"]} if r["display_gift"] else None)}
                   for r in db.execute("SELECT * FROM phone_shop_log WHERE show_id=? AND id>? ORDER BY id LIMIT 200",
                                       (show["id"], shop_after))]
    reports = data.get("reports")
    if isinstance(reports, dict):  # 插件每 2 分钟带一次；单人太大的丢掉，防异常数据撑爆库
        for role, rep_ in list(reports.items())[:300]:
            blob = json.dumps(rep_, ensure_ascii=False)
            if len(blob) > 64000 and isinstance(rep_, dict) and "rpg" in rep_:  # 背包太大时只丢背包快照，别连累时间线/统计
                rep_ = {k: v for k, v in rep_.items() if k != "rpg"}
                blob = json.dumps(rep_, ensure_ascii=False)
            if isinstance(role, str) and role and isinstance(rep_, dict) and len(blob) <= 64000:
                db.execute("""INSERT INTO phone_reports (show_id, role, data, updated_at) VALUES (?,?,?,?)
                              ON CONFLICT(show_id, role) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at""",
                           (show["id"], role, blob, now))
        db.commit()
    lovemails, lm_revokes = _lm_for_bot(db, show["id"], data.get("lovemail_done"), data.get("lovemail_revoke_done"))
    return jsonify({"ok": True, "web_send": _phone_web_send_on(db, show["id"]), "events": events, "shop_events": shop_events,
                    "songs": _song_pending_for_bot(db, show["id"], data.get("songs_done")),
                    "lovemails": lovemails, "lovemail_revokes": lm_revokes,
                    "block_ops": _block_ops_for_bot(db, show["id"], data.get("block_ops_done")),
                    # 群消息：插件照短信计当日次数和冷却（不记互动统计），游标 phone_group_cursor
                    "group_events": [{"id": r["id"], "from_role": r["from_role"], "timestamp": r["created_at"], "day_key": r["day_key"]}
                                     for r in db.execute("SELECT id, from_role, created_at, day_key FROM phone_group_msgs "
                                                         "WHERE show_id=? AND kind='msg' AND id>? ORDER BY id LIMIT 200",
                                                         (show["id"], group_after))]})

@app.route("/p/<code>")
def player_phone_enter(code):
    return _phone_try_enter(code)

# ── 朋友圈 ─────────────────────────────────────────────────────────────────────
# 网页手机里的朋友圈：本季所有拿到激活码的人都能看；发帖/点赞/评论只在主档期（跟短信一致），
# 删自己的帖子/评论/图片随时可以。不经过机器人，也不在群里提醒。
# 图片：浏览器先压缩再上传；服务端用 Pillow 重新编码（去掉 EXIF 里的 GPS 等信息、按 EXIF 方向转正、确认真是图片），
# 存一张大图（长边 1600）+ 一张缩略图（长边 480），都在 moment_images/ 下——不放 static/，只能凭激活码/后台登录看。
# 额度两层：
#   · 每人每季图片张数（后台可改，默认 20）：满了可以删自己以前朋友圈里的图片腾名额，那条朋友圈的文字保留；
#   · 团账号所有季度加起来的总空间（默认 300MB，tenants.moment_quota_mb 可单独调）：季度结束后图片仍保留，
#     直到管理员删除；快满时后台顶部红字提醒，满了就不能再传图，逼管理员去清理旧季度。
MOMENT_IMAGE_DIR           = os.path.join(os.path.dirname(__file__), "moment_images")
_MOMENT_DEFAULT_QUOTA      = 20
_MOMENT_DEFAULT_TENANT_MB  = 300
_MOMENT_MAX_IMAGES         = 9
_MOMENT_MAX_TEXT           = 1000
_MOMENT_MAX_COMMENT        = 300
_MOMENT_MAX_UPLOAD         = 40 * 1024 * 1024   # 一次发帖的整个请求
_MOMENT_MAX_FILE           = 15 * 1024 * 1024   # 单张原图（浏览器没压缩成功时兜底）
_MOMENT_DAILY_POSTS        = 20
_MOMENT_COMMENT_GAP_MS     = 3000
_MOMENT_WARN_RATIO         = 0.9

def _moment_player_quota(db, sid):
    row = db.execute("SELECT moment_quota FROM phone_settings WHERE show_id=?", (sid,)).fetchone()
    return (row["moment_quota"] if row and row["moment_quota"] else _MOMENT_DEFAULT_QUOTA)

def _moment_tenant_quota_bytes(db, tid):
    row = db.execute("SELECT moment_quota_mb FROM tenants WHERE id=?", (tid,)).fetchone()
    return (row["moment_quota_mb"] if row and row["moment_quota_mb"] else _MOMENT_DEFAULT_TENANT_MB) * 1024 * 1024

def _moment_tenant_used(db, tid):
    return db.execute("SELECT COALESCE(SUM(size_bytes),0) FROM moment_images WHERE tenant_id=? AND deleted_at=0",
                      (tid,)).fetchone()[0]

def _moment_player_used(db, sid, role):
    return db.execute("SELECT COUNT(*) FROM moment_images WHERE show_id=? AND role_name=? AND deleted_at=0",
                      (sid, role)).fetchone()[0]

def _moment_process(raw):
    """原始字节 → (大图 JPEG, 缩略图 JPEG, 宽, 高)；不是图片/太大/解不开抛 ValueError"""
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = 40_000_000  # 超过就当解压炸弹拒掉
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        raise ValueError("不是能识别的图片")
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    def enc(im, edge, q):
        im = im.copy()
        im.thumbnail((edge, edge))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q, optimize=True, progressive=True)  # 不传 exif → 元数据全丢
        return buf.getvalue(), im.size
    full, (w, h) = enc(img, 1600, 82)
    thumb, _ = enc(img, 480, 75)
    return full, thumb, w, h

def _moment_delete_image_file(row):
    for name in (row["file"], row["thumb"]):
        try:
            os.remove(os.path.join(MOMENT_IMAGE_DIR, name))
        except OSError:
            pass

def _moment_delete_images(db, where, args):
    """删一批图片：文件删掉，行留着（deleted_at 置时间）"""
    now = int(time.time() * 1000)
    rows = db.execute(f"SELECT id, file, thumb FROM moment_images WHERE deleted_at=0 AND {where}", args).fetchall()
    for r in rows:
        _moment_delete_image_file(r)
        db.execute("UPDATE moment_images SET deleted_at=? WHERE id=?", (now, r["id"]))
    return len(rows)

def _moment_feed(db, sid, viewer, before=None, limit=20, role=None):
    q = "SELECT * FROM moments WHERE show_id=? AND deleted=0"
    args = [sid]
    if before:
        q += " AND id<?"; args.append(before)
    if role:
        q += " AND role_name=?"; args.append(role)
    posts = [dict(r) for r in db.execute(q + " ORDER BY id DESC LIMIT ?", args + [limit + 1]).fetchall()]
    more = len(posts) > limit
    posts = posts[:limit]
    for p in posts:
        p["mine"] = p["role_name"] == viewer
        p["time"] = _phone_time(p["created_at"])
        p["images"] = [dict(r) for r in db.execute(
            "SELECT id, width, height, deleted_at FROM moment_images WHERE moment_id=? ORDER BY seq, id", (p["id"],))]
        p["likes"] = [r["role_name"] for r in db.execute(
            "SELECT role_name FROM moment_likes WHERE moment_id=? ORDER BY created_at", (p["id"],))]
        p["liked"] = viewer in p["likes"]
        p["comments"] = [dict(r, mine=r["role_name"] == viewer) for r in db.execute(
            "SELECT id, role_name, reply_to, content FROM moment_comments WHERE moment_id=? AND deleted=0 ORDER BY id",
            (p["id"],))]
    return posts, more

def _moment_can_write(db, sid):
    """发帖/点赞/评论：本季进行中 + 主档期；返回不能的原因，能就返回 None"""
    if _phone_comm_paused(db, sid):
        return _PAUSE_MSG
    show = db.execute("SELECT * FROM shows WHERE id=?", (sid,)).fetchone()
    if not show or _schedule_zone(dict(show)) != "main":
        return "不在档期内，朋友圈暂时只能看"
    return None

def _moment_json(ok, msg="", **extra):
    return jsonify(ok=ok, msg=msg, **extra), (200 if ok else 400)

def _moment_guard():
    """玩家朋友圈的写接口统一校验：激活码 + CSRF；返回 (sid, owner, tid) 或 (None, 错误响应)"""
    who = _phone_current()
    if not who:
        return None, (jsonify(ok=False, msg="手机登录已失效"), 401)
    token = request.headers.get("X-CSRF", "") or request.form.get("csrf", "")
    if not hmac.compare_digest(token, session.get("phone_csrf", "") or "-"):
        return None, _moment_json(False, "页面过期了，刷新后再试")
    sid, owner = who
    if owner == PHONE_ADMIN:
        return None, _moment_json(False, "管理身份只能查看和删除，不能发")
    tid = get_db().execute("SELECT tenant_id FROM shows WHERE id=?", (sid,)).fetchone()["tenant_id"]
    return (sid, owner, tid), None

@app.route("/p/me/discover")
def player_discover():
    """「发现」页：朋友圈、心动信箱、点歌台、小游戏、使用指南都从这里进，顶上放每日一句。"""
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    db = get_db()
    latest = db.execute(
        "SELECT role_name, content, created_at, (SELECT COUNT(*) FROM moment_images i WHERE i.moment_id=m.id) AS n "
        "FROM moments m WHERE show_id=? AND deleted=0 ORDER BY id DESC LIMIT 1", (sid,)).fetchone()
    return render_template("phone.html", mode="discover", owner=owner, sid=sid, csrf=_phone_csrf(),
                           phone_admin=(owner == PHONE_ADMIN), moments_latest=latest,
                           has_maps=bool(_phone_maps(db, sid, owner == PHONE_ADMIN)))

def _phone_maps(db, sid, is_admin):
    """小手机里能看的地图：玩家只看后台勾了「玩家可见」的，管理身份全看；顺序跟地点列表一致。"""
    maps = _get_maps(db, sid)
    row = db.execute("SELECT value FROM site_config WHERE show_id=? AND key='available_places'", (sid,)).fetchone()
    try: order = list(json.loads(row["value"]).keys()) if row and row["value"] else []
    except Exception: order = []
    names = [n for n in order if n in maps] + [n for n in maps if n not in order]
    return {n: maps[n] for n in names if is_admin or maps[n].get("visible")}

@app.route("/p/me/maps")
def player_maps():
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    maps = _phone_maps(get_db(), sid, owner == PHONE_ADMIN)
    db = get_db()
    prow = db.execute("SELECT value FROM site_config WHERE show_id=? AND key='available_places'", (sid,)).fetchone()
    try: places = json.loads(prow["value"]) if prow and prow["value"] else {}
    except Exception: places = {}
    # 只带地图上关联到的地点的描述，别把整张地点表（含上锁状态）露给玩家
    linked = {it["place"] for m in maps.values() for it in m.get("items", []) if it.get("t") == "rect" and it.get("place")}
    place_info = {n: (places.get(n) or {}).get("desc", "") for n in linked if n in places}
    return render_template("phone.html", mode="maps", owner=owner, sid=sid, csrf=_phone_csrf(),
                           phone_admin=(owner == PHONE_ADMIN), place_maps=maps, place_info=place_info)

@app.route("/p/me/moments")
def player_moments():
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    db = get_db()
    tid = db.execute("SELECT tenant_id FROM shows WHERE id=?", (sid,)).fetchone()["tenant_id"]
    try:
        before = int(request.args.get("before") or 0) or None
    except ValueError:
        before = None
    mine_only = request.args.get("mine") == "1"
    posts, more = _moment_feed(db, sid, owner, before=before, role=owner if mine_only else None)
    quota = _moment_player_quota(db, sid)
    tenant_full = _moment_tenant_used(db, tid) >= _moment_tenant_quota_bytes(db, tid)
    return render_template("phone.html", mode="moments", owner=owner, sid=sid, posts=posts, more=more,
                           mine_only=mine_only, csrf=_phone_csrf(),
                           why=("管理身份：可以删除任何朋友圈、评论和图片，不能发" if owner == PHONE_ADMIN else _moment_can_write(db, sid)),
                           phone_admin=(owner == PHONE_ADMIN),
                           img_used=_moment_player_used(db, sid, owner), img_quota=quota, tenant_full=tenant_full,
                           max_images=_MOMENT_MAX_IMAGES, max_text=_MOMENT_MAX_TEXT, max_comment=_MOMENT_MAX_COMMENT,
                           latest_ts=(posts[0]["created_at"] if posts and not before and not mine_only else 0))

# ── 小游戏 ──────────────────────────────────────────────────────────────────────
# score_per_sec / min_secs 只是挡手滑和乱刷的粗略上限，分数本来就在前端算，不追求防作弊
_GAMES = {
    "2048":  {"name": "2048",   "icon": "🔢", "desc": "滑动合并方块，越大越好", "unit": "分", "score_per_sec": 600, "min_secs": 8},
    "snake": {"name": "贪吃蛇", "icon": "🐍", "desc": "吃得越多分越高，别撞墙",   "unit": "分", "score_per_sec": 40,  "min_secs": 5},
    "whack": {"name": "打地鼠", "icon": "🔨", "desc": "30 秒内敲中多少只",         "unit": "只", "score_per_sec": 7,   "min_secs": 29},
}

def _game_board(db, game, sid, owner, limit=50):
    rows = db.execute("SELECT show_id, role_name, label, score FROM game_scores WHERE game=? "
                      "ORDER BY score DESC, updated_at ASC LIMIT ?", (game, limit)).fetchall()
    board = [{"rank": i + 1, "label": r["label"], "score": r["score"],
              "me": r["show_id"] == sid and r["role_name"] == owner} for i, r in enumerate(rows)]
    mine = db.execute("SELECT score FROM game_scores WHERE game=? AND show_id=? AND role_name=?",
                      (game, sid, owner)).fetchone()
    my_rank = None
    if mine:
        my_rank = 1 + db.execute(
            "SELECT COUNT(*) FROM game_scores WHERE game=? AND (score > ? OR (score = ? AND updated_at < "
            "(SELECT updated_at FROM game_scores WHERE game=? AND show_id=? AND role_name=?)))",
            (game, mine["score"], mine["score"], game, sid, owner)).fetchone()[0]
    return board, (mine["score"] if mine else None), my_rank

@app.route("/p/me/games")
@app.route("/p/me/games/<game>")
def player_games(game=None):
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    if game is not None and game not in _GAMES:
        return redirect(url_for("player_games"))
    db = get_db()
    if game:
        session["game_start_" + game] = time.time()
    summary = {}
    for g in _GAMES:
        _, best, rank = _game_board(db, g, sid, owner, limit=1)
        summary[g] = {"best": best, "rank": rank}
    board, best, rank = _game_board(db, game, sid, owner) if game else ([], None, None)
    return render_template("phone.html", mode="games", owner=owner, sid=sid, csrf=_phone_csrf(),
                           phone_admin=(owner == PHONE_ADMIN), games=_GAMES, game=game, summary=summary,
                           board=board, my_best=best, my_rank=rank)

@app.route("/p/me/games/<game>/score", methods=["POST"])
def player_game_score(game):
    ok_, err = _moment_guard()
    if err:
        return err
    sid, owner, _ = ok_
    g = _GAMES.get(game)
    if not g:
        return _moment_json(False, "没有这个游戏")
    try:
        score = int(request.get_json(silent=True, force=True).get("score"))
    except (TypeError, ValueError, AttributeError):
        return _moment_json(False, "分数不对")
    started = session.get("game_start_" + game)
    if not started:
        return _moment_json(False, "请重新进入游戏再提交")
    elapsed = time.time() - started
    if score < 0 or elapsed < g["min_secs"] or score > max(50, elapsed * g["score_per_sec"]):
        return _moment_json(False, "这个分数好像不太对，没有记入排行榜")
    # 每次提交后重新计时：一局提交一次，再玩要重新开局（前端「再来一局」会刷新计时）
    session["game_start_" + game] = time.time()
    db = get_db()
    nicks = _nick_map(db, sid)
    label = f"{nicks[owner]}（{owner}）" if nicks.get(owner) else owner
    now = int(time.time() * 1000)
    cur = db.execute("SELECT score FROM game_scores WHERE game=? AND show_id=? AND role_name=?", (game, sid, owner)).fetchone()
    new_best = not cur or score > cur["score"]
    if not cur:
        db.execute("INSERT INTO game_scores (game, show_id, role_name, label, score, updated_at) VALUES (?,?,?,?,?,?)",
                   (game, sid, owner, label, score, now))
    elif new_best:
        db.execute("UPDATE game_scores SET score=?, label=?, updated_at=? WHERE game=? AND show_id=? AND role_name=?",
                   (score, label, now, game, sid, owner))
    else:
        db.execute("UPDATE game_scores SET label=? WHERE game=? AND show_id=? AND role_name=?", (label, game, sid, owner))
    db.commit()
    _, best, rank = _game_board(db, game, sid, owner, limit=1)
    return _moment_json(True, new_best=new_best, best=best, rank=rank)

@app.route("/p/me/games/<game>/restart", methods=["POST"])
def player_game_restart(game):
    ok_, err = _moment_guard()
    if err:
        return err
    if game in _GAMES:
        session["game_start_" + game] = time.time()
    return _moment_json(True)

@app.route("/p/me/moments/img/<int:image_id>")
def player_moment_image(image_id):
    who = _phone_current()
    if not who:
        abort(404)
    row = get_db().execute("SELECT * FROM moment_images WHERE id=? AND show_id=? AND deleted_at=0",
                           (image_id, who[0])).fetchone()
    if not row:
        abort(404)
    name = row["thumb"] if request.args.get("s") == "thumb" else row["file"]
    resp = send_file(os.path.join(MOMENT_IMAGE_DIR, name), mimetype="image/jpeg")
    resp.headers["X-Moment-Image"] = "1"  # 让 /p 的安全头放开缓存：图片内容不会变，删了就 404
    return resp

@app.route("/p/me/moments/post", methods=["POST"])
def player_moment_post():
    ok_, err = _moment_guard()
    if err:
        return err
    sid, owner, tid = ok_
    _p = _comm_pause_json(get_db(), sid)
    if _p:
        return _p
    db = get_db()
    why = _moment_can_write(db, sid)
    if why:
        return _moment_json(False, why)
    if request.content_length is None or request.content_length > _MOMENT_MAX_UPLOAD:
        return _moment_json(False, "图片太大了，少选几张再试")
    text = (request.form.get("content") or "").strip()
    files = [f for f in request.files.getlist("images") if f and f.filename is not None]
    if not text and not files:
        return _moment_json(False, "写点什么，或者配张图")
    if len(text) > _MOMENT_MAX_TEXT:
        return _moment_json(False, f"最多 {_MOMENT_MAX_TEXT} 字")
    if len(files) > _MOMENT_MAX_IMAGES:
        return _moment_json(False, f"一条最多 {_MOMENT_MAX_IMAGES} 张图")
    if _blocked_hit(sid, owner, "朋友圈", text):
        return _moment_json(False, BLOCKED_MSG)
    day_start = int(datetime.now(TZ_BEIJING).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    if db.execute("SELECT COUNT(*) FROM moments WHERE show_id=? AND role_name=? AND created_at>=?",
                  (sid, owner, day_start)).fetchone()[0] >= _MOMENT_DAILY_POSTS:
        return _moment_json(False, f"今天已经发了 {_MOMENT_DAILY_POSTS} 条，明天再来")
    processed = []
    for f in files:
        raw = f.read(_MOMENT_MAX_FILE + 1)
        if len(raw) > _MOMENT_MAX_FILE:
            return _moment_json(False, "有张图片太大了")
        try:
            processed.append(_moment_process(raw))
        except ValueError as e:
            return _moment_json(False, f"有张图片打不开：{e}")
    with _phone_send_lock:  # 额度检查和写入之间不能被插队
        if processed:
            quota = _moment_player_quota(db, sid)
            used = _moment_player_used(db, sid, owner)
            if used + len(processed) > quota:
                return _moment_json(False, f"图片额度不够：本季已用 {used}/{quota} 张。"
                                          f"可以在「我的朋友圈」删掉以前的图片腾出位置，文字会保留")
            new_bytes = sum(len(a) + len(b) for a, b, _, _ in processed)
            if _moment_tenant_used(db, tid) + new_bytes > _moment_tenant_quota_bytes(db, tid):
                return _moment_json(False, "存档空间满了，暂时不能发图，请联系管理员清理")
        now = int(time.time() * 1000)
        sync = _phone_sync_row(db, sid)
        game_day = (sync["snap"].get("game_day") or "") if sync else ""
        cur = db.execute("INSERT INTO moments (tenant_id, show_id, role_name, content, game_day, created_at) VALUES (?,?,?,?,?,?)",
                         (tid, sid, owner, text, game_day, now))
        mid = cur.lastrowid
        folder = os.path.join(str(tid), str(sid))
        os.makedirs(os.path.join(MOMENT_IMAGE_DIR, folder), exist_ok=True)
        for i, (full, thumb, w, h) in enumerate(processed):
            key = secrets.token_hex(12)
            fname, tname = os.path.join(folder, key + ".jpg"), os.path.join(folder, key + "_t.jpg")
            with open(os.path.join(MOMENT_IMAGE_DIR, fname), "wb") as fh:
                fh.write(full)
            with open(os.path.join(MOMENT_IMAGE_DIR, tname), "wb") as fh:
                fh.write(thumb)
            db.execute("""INSERT INTO moment_images (moment_id, tenant_id, show_id, role_name, file, thumb, size_bytes,
                          width, height, seq, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                       (mid, tid, sid, owner, fname, tname, len(full) + len(thumb), w, h, i, now))
        db.commit()
    return _moment_json(True, "已发布", id=mid)

@app.route("/p/me/moments/<int:mid>/like", methods=["POST"])
def player_moment_like(mid):
    ok_, err = _moment_guard()
    if err:
        return err
    sid, owner, _ = ok_
    _p = _comm_pause_json(get_db(), sid)
    if _p:
        return _p
    db = get_db()
    if not db.execute("SELECT 1 FROM moments WHERE id=? AND show_id=? AND deleted=0", (mid, sid)).fetchone():
        return _moment_json(False, "这条朋友圈不见了")
    why = _moment_can_write(db, sid)
    if why:
        return _moment_json(False, why)
    if db.execute("SELECT 1 FROM moment_likes WHERE moment_id=? AND role_name=?", (mid, owner)).fetchone():
        db.execute("DELETE FROM moment_likes WHERE moment_id=? AND role_name=?", (mid, owner))
        liked = False
    else:
        db.execute("INSERT INTO moment_likes (moment_id, role_name, created_at) VALUES (?,?,?)",
                   (mid, owner, int(time.time() * 1000)))
        liked = True
    db.commit()
    likes = [r["role_name"] for r in db.execute(
        "SELECT role_name FROM moment_likes WHERE moment_id=? ORDER BY created_at", (mid,))]
    return _moment_json(True, liked=liked, likes=likes)

@app.route("/p/me/moments/<int:mid>/comment", methods=["POST"])
def player_moment_comment(mid):
    ok_, err = _moment_guard()
    if err:
        return err
    sid, owner, _ = ok_
    _p = _comm_pause_json(get_db(), sid)
    if _p:
        return _p
    db = get_db()
    if not db.execute("SELECT 1 FROM moments WHERE id=? AND show_id=? AND deleted=0", (mid, sid)).fetchone():
        return _moment_json(False, "这条朋友圈不见了")
    why = _moment_can_write(db, sid)
    if why:
        return _moment_json(False, why)
    text = (request.form.get("content") or "").strip()
    if not text:
        return _moment_json(False, "评论不能为空")
    if len(text) > _MOMENT_MAX_COMMENT:
        return _moment_json(False, f"评论最多 {_MOMENT_MAX_COMMENT} 字")
    if _blocked_hit(sid, owner, "朋友圈评论", text):
        return _moment_json(False, BLOCKED_MSG)
    reply_to = (request.form.get("reply_to") or "").strip()
    # 只能回复这条朋友圈下真的评论过的人（或楼主），不能随手写个名字
    if reply_to:
        valid = {r["role_name"] for r in db.execute(
            "SELECT role_name FROM moment_comments WHERE moment_id=? AND deleted=0", (mid,))}
        valid.add(db.execute("SELECT role_name FROM moments WHERE id=?", (mid,)).fetchone()["role_name"])
        if reply_to not in valid or reply_to == owner:
            reply_to = ""
    now = int(time.time() * 1000)
    last = db.execute("SELECT MAX(m.created_at) FROM moment_comments m JOIN moments p ON p.id=m.moment_id "
                      "WHERE p.show_id=? AND m.role_name=?", (sid, owner)).fetchone()[0] or 0
    if now - last < _MOMENT_COMMENT_GAP_MS:
        return _moment_json(False, "慢一点，隔几秒再评论")
    db.execute("INSERT INTO moment_comments (moment_id, role_name, reply_to, content, created_at) VALUES (?,?,?,?,?)",
               (mid, owner, reply_to, text, now))
    db.commit()
    return _moment_json(True)

@app.route("/p/me/moments/<int:mid>/delete", methods=["POST"])
def player_moment_delete(mid):
    ok_, err = _moment_guard()
    if err:
        return err
    sid, owner, _ = ok_
    db = get_db()
    row = db.execute("SELECT 1 FROM moments WHERE id=? AND show_id=? AND role_name=? AND deleted=0",
                     (mid, sid, owner)).fetchone()
    if not row:
        return _moment_json(False, "只能删自己的朋友圈")
    _moment_delete_images(db, "moment_id=?", (mid,))
    db.execute("UPDATE moments SET deleted=1 WHERE id=?", (mid,))
    db.commit()
    return _moment_json(True)

@app.route("/p/me/moments/comment/<int:cid>/delete", methods=["POST"])
def player_moment_comment_delete(cid):
    ok_, err = _moment_guard()
    if err:
        return err
    sid, owner, _ = ok_
    db = get_db()
    # 自己的评论可以删；楼主也可以删自己朋友圈下的任何评论
    row = db.execute("""SELECT c.id FROM moment_comments c JOIN moments m ON m.id=c.moment_id
                        WHERE c.id=? AND m.show_id=? AND c.deleted=0 AND (c.role_name=? OR m.role_name=?)""",
                     (cid, sid, owner, owner)).fetchone()
    if not row:
        return _moment_json(False, "不能删这条评论")
    db.execute("UPDATE moment_comments SET deleted=1 WHERE id=?", (cid,))
    db.commit()
    return _moment_json(True)

@app.route("/p/me/moments/image/<int:image_id>/delete", methods=["POST"])
def player_moment_image_delete(image_id):
    ok_, err = _moment_guard()
    if err:
        return err
    sid, owner, _ = ok_
    db = get_db()
    n = _moment_delete_images(db, "id=? AND show_id=? AND role_name=?", (image_id, sid, owner))
    db.commit()
    if not n:
        return _moment_json(False, "只能删自己的图片")
    return _moment_json(True, "图片已删除，那条朋友圈的文字还在",
                        used=_moment_player_used(db, sid, owner), quota=_moment_player_quota(db, sid))

# ── 头像 ──────────────────────────────────────────────────────────────────────
# 一季一个角色一张：服务端居中裁成正方形、缩到 256×256 的 JPEG（约 10–30KB，同样去掉 EXIF）；
# 重新上传直接替换，旧文件立刻删掉。本季所有人都能看到——对话/联系人按显示的名字认人，头像跟着名字走，
# 所以被换了落款的信显示的是落款那个人的头像，「未知号码」没有头像，不会多透露什么。
# 头像很小，不算进团账号的朋友圈图片空间。
_AVATAR_EDGE    = 256
_AVATAR_GAP_MS  = 5000

def _avatar_process(raw):
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = 40_000_000
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        raise ValueError("不是能识别的图片")
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    img = ImageOps.fit(img, (_AVATAR_EDGE, _AVATAR_EDGE), method=Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85, optimize=True)
    return buf.getvalue()

def _avatar_remove(db, sid, role):
    row = db.execute("SELECT file FROM phone_avatars WHERE show_id=? AND role_name=?", (sid, role)).fetchone()
    if row:
        try:
            os.remove(os.path.join(MOMENT_IMAGE_DIR, row["file"]))
        except OSError:
            pass
        db.execute("DELETE FROM phone_avatars WHERE show_id=? AND role_name=?", (sid, role))

@app.context_processor
def inject_phone_urls():
    """模板里用 purl() 生成对话/首页链接：管理员以某人视角查看时换成管理员路由"""
    def purl(endpoint, **kw):
        as_role = kw.pop("_as", None)
        if as_role:
            if endpoint == "player_phone_thread":
                return url_for("admin_phone_thread", role=as_role, other=kw["other"])
            if endpoint == "player_phone_inbox":
                return url_for("admin_phone_inbox", role=as_role)
        return url_for(endpoint, **kw)
    return {"purl": purl}

@app.context_processor
def inject_phone_npcs():
    """网页手机页面用：本季的 NPC 名单（名字旁边标 NPC；匿名的地方不标）"""
    if not (request.path.startswith("/p/me") or request.path.startswith("/p/admin")):
        return {}
    try:
        who = _phone_current()
        sync = _phone_sync_row(get_db(), who[0]) if who else None
        return {"phone_npcs": [r["name"] for r in ((sync["snap"].get("roster") or []) if sync else []) if r.get("npc")],
                "comm_paused": bool(who and who[1] != PHONE_ADMIN and _phone_comm_paused(get_db(), who[0]))}
    except Exception:
        return {}

@app.context_processor
def inject_phone_avatars():
    """网页手机页面用：本季谁有头像 {名字: 版本号}，前端据此把名字头像换成图片"""
    if not (request.path.startswith("/p/me") or request.path.startswith("/p/admin")):
        return {}
    try:
        who = _phone_current()
        if not who:
            return {}
        db = get_db()
        rows = db.execute("SELECT role_name, updated_at FROM phone_avatars WHERE show_id=?", (who[0],)).fetchall()
        # 底部导航「心动信」的未读点：收到的最新一封心动信的存档 id（进过信箱就记成已读）
        last = db.execute("SELECT MAX(id) FROM extra_events WHERE show_id=? AND type='lovemail' AND to_role=?", who).fetchone()[0]
        nicks = _nick_map(db, who[0])
        remarks = _remark_map(db, who[0], who[1])
        def disp(name):
            """名字的显示写法：自己给 TA 写了备注就是「备注（真名）」，否则 TA 设了微信名就是「微信名（真名）」，都没有就是真名"""
            nick = remarks.get(name) or nicks.get(name)
            return f"{nick}（{name}）" if nick else name
        return {"phone_avatars": {r["role_name"]: r["updated_at"] for r in rows}, "lovemail_last": last or 0, "disp": disp,
                "my_remarks": remarks}
    except Exception:
        return {}

# ── 给对方的备注 ─────────────────────────────────────────────────────────────────
_REMARK_MAX = 12

def _remark_map(db, sid, owner):
    if owner == PHONE_ADMIN:
        return {}
    return {r["target"]: r["remark"] for r in db.execute(
        "SELECT target, remark FROM phone_remarks WHERE show_id=? AND owner=?", (sid, owner))}

@app.route("/p/me/remark", methods=["POST"])
def player_remark():
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    f = request.form
    target = (f.get("target") or "").strip()
    back = url_for("player_phone_thread", other=target) if target else url_for("player_phone_inbox")
    if owner == PHONE_ADMIN or not hmac.compare_digest(f.get("csrf", ""), session.get("phone_csrf", "") or "-"):
        session["phone_flash"] = "❌ 页面过期了，刷新后再试"
        return redirect(back)
    db = get_db()
    roster = _phone_roster(_phone_sync_row(db, sid))
    if target == owner or target not in roster:
        session["phone_flash"] = "❌ 只能给名单里的人写备注"
        return redirect(back)
    remark = (f.get("remark") or "").strip()
    if not remark or remark == target:
        db.execute("DELETE FROM phone_remarks WHERE show_id=? AND owner=? AND target=?", (sid, owner, target))
        db.commit()
        session["phone_flash"] = "已清除备注"
        return redirect(back)
    if len(remark) > _REMARK_MAX:
        session["phone_flash"] = f"❌ 备注最多 {_REMARK_MAX} 个字（现在 {len(remark)} 个）"
    elif re.search(r"[()（）\[\]【】＠@\n\r]", remark) or _CQ_CODE.search(remark):
        session["phone_flash"] = "❌ 备注里不能有括号、@ 或特殊符号"
    elif _blocked_hit(sid, owner, "备注", remark):
        session["phone_flash"] = BLOCKED_MSG
    else:
        db.execute("""INSERT INTO phone_remarks (show_id, owner, target, remark, updated_at) VALUES (?,?,?,?,?)
                      ON CONFLICT(show_id, owner, target) DO UPDATE SET remark=excluded.remark, updated_at=excluded.updated_at""",
                   (sid, owner, target, remark, int(time.time() * 1000)))
        db.commit()
        session["phone_flash"] = f"✅ 备注已保存，只有你自己看得到"
    return redirect(back)

# ── 微信名 ──────────────────────────────────────────────────────────────────────
# 在「我的」里自己设，别人在消息列表和对话标题里看到「微信名（真名）」；真名永远跟在括号里，所以冒充不了别人。
# 规则：1–12 字；不能带括号（不然能伪造「某某（别人的真名）」）、不能是 CQ 码、不过违禁词、
# 不能和别人的真名或微信名重复；填空就是清除。只影响显示，匿名对话的化名、心动信署名、落款都不受影响。
_NICK_MAX = 12

def _nick_map(db, sid):
    return {r["role"]: r["nick"] for r in db.execute("SELECT role, nick FROM phone_nicknames WHERE show_id=?", (sid,))}

def _nick_set(db, sid, owner, raw):
    """返回 (ok, 提示)；调用方持有 _phone_send_lock"""
    nick = (raw or "").strip()
    if not nick or nick == owner:
        db.execute("DELETE FROM phone_nicknames WHERE show_id=? AND role=?", (sid, owner))
        db.commit()
        return True, "已清除微信名，别人只会看到你的名字"
    if len(nick) > _NICK_MAX:
        return False, f"❌ 微信名最多 {_NICK_MAX} 个字（现在 {len(nick)} 个）"
    if re.search(r"[()（）\[\]【】\n\r]", nick) or _CQ_CODE.search(nick):
        return False, "❌ 微信名里不能有括号或特殊符号"
    if nick in _ALIAS_RESERVED:
        return False, "❌ 这个微信名不能用，换一个"
    roster = _phone_roster(_phone_sync_row(db, sid))
    taken = {n for n in roster if n != owner} | {k for r, k in _nick_map(db, sid).items() if r != owner}   # 别人的真名和别人的微信名
    if nick in taken:
        return False, "❌ 这个名字已经有人用了，换一个"
    if _blocked_hit(sid, owner, "微信名", nick):
        return False, BLOCKED_MSG
    db.execute("""INSERT INTO phone_nicknames (show_id, role, nick, updated_at) VALUES (?,?,?,?)
                  ON CONFLICT(show_id, role) DO UPDATE SET nick=excluded.nick, updated_at=excluded.updated_at""",
               (sid, owner, nick, int(time.time() * 1000)))
    db.commit()
    return True, f"✅ 微信名已设为「{nick}」，别人会看到「{nick}（{owner}）」"

@app.route("/p/me/nickname", methods=["POST"])
def player_nickname():
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    if not hmac.compare_digest(request.form.get("csrf", ""), session.get("phone_csrf", "") or "-"):
        session["phone_flash"] = "❌ 页面过期了，刷新后再试"
    elif owner == PHONE_ADMIN:
        session["phone_flash"] = "❌ 管理身份不能设置微信名"
    else:
        with _phone_send_lock:
            ok_, msg = _nick_set(get_db(), sid, owner, request.form.get("nick", ""))
        session["phone_flash"] = msg
    return redirect(url_for("player_phone_library", view="profile"))

@app.route("/p/me/avatar", methods=["POST"])
def player_avatar_upload():
    ok_, err = _moment_guard()
    if err:
        return err
    sid, owner, tid = ok_
    db = get_db()
    if request.content_length is None or request.content_length > _MOMENT_MAX_FILE + 65536:
        return _moment_json(False, "图片太大了")
    f = request.files.get("avatar")
    if not f:
        return _moment_json(False, "没收到图片")
    old = db.execute("SELECT updated_at FROM phone_avatars WHERE show_id=? AND role_name=?", (sid, owner)).fetchone()
    now = int(time.time() * 1000)
    if old and now - old["updated_at"] < _AVATAR_GAP_MS:
        return _moment_json(False, "换得太快了，隔几秒再试")
    try:
        data = _avatar_process(f.read(_MOMENT_MAX_FILE + 1))
    except ValueError as e:
        return _moment_json(False, f"图片打不开：{e}")
    folder = os.path.join("avatars", str(tid), str(sid))
    os.makedirs(os.path.join(MOMENT_IMAGE_DIR, folder), exist_ok=True)
    name = os.path.join(folder, secrets.token_hex(12) + ".jpg")
    with open(os.path.join(MOMENT_IMAGE_DIR, name), "wb") as fh:
        fh.write(data)
    with _phone_send_lock:
        _avatar_remove(db, sid, owner)  # 旧头像文件立刻删掉
        db.execute("INSERT INTO phone_avatars (show_id, role_name, tenant_id, file, size_bytes, updated_at) VALUES (?,?,?,?,?,?)",
                   (sid, owner, tid, name, len(data), now))
        db.commit()
    return _moment_json(True, "头像已更新", v=now)

@app.route("/p/me/avatar/delete", methods=["POST"])
def player_avatar_delete():
    ok_, err = _moment_guard()
    if err:
        return err
    sid, owner, _ = ok_
    db = get_db()
    _avatar_remove(db, sid, owner)
    db.commit()
    return _moment_json(True, "已换回名字头像")

@app.route("/p/me/avatar/<path:role>")
def player_avatar(role):
    who = _phone_current()
    if not who:
        abort(404)
    row = get_db().execute("SELECT file FROM phone_avatars WHERE show_id=? AND role_name=?", (who[0], role)).fetchone()
    if not row:
        abort(404)
    resp = send_file(os.path.join(MOMENT_IMAGE_DIR, row["file"]), mimetype="image/jpeg")
    resp.headers["X-Moment-Image"] = "1"  # 地址带版本号，换头像地址就变，可以放心缓存
    return resp

@app.route("/admin/avatars/<int:show_id>/<path:role>")
@require_admin
def admin_avatar_image(show_id, role):
    row = get_db().execute("SELECT file FROM phone_avatars WHERE show_id=? AND role_name=? AND tenant_id=?",
                           (show_id, role, current_tenant_id())).fetchone()
    if not row:
        abort(404)
    return send_file(os.path.join(MOMENT_IMAGE_DIR, row["file"]), mimetype="image/jpeg")

# ── 点歌 ──────────────────────────────────────────────────────────────────────
# 网页手机和群里（「点歌 歌名 给 某人 寄语」）都能点，一律匿名：公告群和网页「公开播报」只写「有人点给 X」，
# 被点的人手机里「点歌台」对话也会收到一条；管理员后台能看到是谁点的。
# 可以从网易云或 QQ 音乐里选。搜歌都走各自网页版的老接口（网易 search/get/web + song/detail；
# QQ smartbox 联想 + fcg_play_single_song 单曲详情），都不是官方开放接口，对方一改就可能失效——
# 失效时搜索会报「暂时搜不到」，已经点过的歌照常显示。QQ 的联想接口只给最相关的几首。
# 不转发任何音频：网易云在网页里用官方外链播放器，QQ 音乐没有可嵌入的播放器、只给「在 QQ 音乐打开」链接；
# 群里由机器人发 [CQ:music,type=163/qq] 卡片 + 文字链接。VIP/付费歌标出来（外链多半放不了）。
# 公告群那份由机器人在每 30 秒同步时取走（announced=0 的），发完回报；机器人挂了超过 2 小时的就不补发了。
_SONG_DEFAULT_DAILY  = 3
_SONG_MAX_MSG        = 100
_SONG_ANNOUNCE_TTL   = 2 * 3600 * 1000
_song_cache          = {}           # 关键词 → (时间, 结果)
_song_rate           = {}           # 角色 → 上次搜索时间
_NETEASE_HEADERS     = {"Referer": "https://music.163.com/", "User-Agent": "Mozilla/5.0 (changri-archive)"}

def _netease_get(path, params):
    url = "https://music.163.com" + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_NETEASE_HEADERS)
    with urllib.request.urlopen(req, timeout=6) as r:
        return json.loads(r.read().decode("utf-8"))

SONG_PLATFORMS = {"163": "网易云", "qq": "QQ音乐"}

def _qq_get(url, params):
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params),
                                 headers={"Referer": "https://y.qq.com/", "User-Agent": "Mozilla/5.0 (changri-archive)"})
    with urllib.request.urlopen(req, timeout=6) as r:
        return json.loads(r.read().decode("utf-8"))

def _qq_detail(mid):
    """QQ 音乐 songmid → 歌曲信息；查不到返回 None"""
    data = _qq_get("https://c.y.qq.com/v8/fcg-bin/fcg_play_single_song.fcg", {"songmid": mid, "format": "json"})
    items = data.get("data") or []
    if not items:
        return None
    sg = items[0]
    al = sg.get("album") or {}
    pay = sg.get("pay") or {}
    return {"platform": "qq", "id": int(sg.get("id") or 0), "mid": sg.get("mid") or mid,
            "name": sg.get("name") or sg.get("title") or "",
            "artists": " / ".join(a.get("name", "") for a in sg.get("singer") or [] if a.get("name")),
            "album": al.get("name") or "",
            "cover": f"https://y.gtimg.cn/music/photo_new/T002R300x300M000{al['mid']}.jpg" if al.get("mid") else "",
            "vip": bool(pay.get("pay_play"))}

def _qq_search(q):
    data = _qq_get("https://c.y.qq.com/splcloud/fcgi-bin/smartbox_new.fcg",
                   {"key": q, "format": "json", "inCharset": "utf-8", "outCharset": "utf-8"})
    mids = [it["mid"] for it in (((data.get("data") or {}).get("song") or {}).get("itemlist") or []) if it.get("mid")]
    return [d for d in (_qq_detail(m) for m in mids[:6]) if d and d["id"]]

def _song_lookup(platform, song_id):
    """提交时按平台重新查一遍（不信任前端传来的歌名）；网易云用数字 id，QQ 用 songmid"""
    if platform == "qq":
        return _qq_detail(str(song_id)) if song_id else None
    try:
        sid_int = int(song_id)
    except (TypeError, ValueError):
        return None
    return _song_details([sid_int]).get(sid_int)

def _song_details(ids):
    """网易云歌曲 id 列表 → {id: 歌曲信息}；拿不到返回空 dict"""
    if not ids:
        return {}
    data = _netease_get("/api/song/detail/", {"ids": json.dumps(ids)})
    out = {}
    for sg in data.get("songs") or []:
        al = sg.get("album") or {}
        out[sg["id"]] = {
            "platform": "163", "id": sg["id"], "mid": "", "name": sg.get("name") or "",
            "artists": " / ".join(a.get("name", "") for a in sg.get("artists") or [] if a.get("name")),
            "album": al.get("name") or "", "cover": (al.get("picUrl") or "").replace("http://", "https://"),
            "vip": int(sg.get("fee") or 0) in (1, 4),  # 1=VIP 4=付费专辑，外链播放器放不了
        }
    return out

def _song_search(q, platform="163"):
    """关键词 → 歌曲列表（网易云最多 10 首，QQ 只有最相关的几首）；接口出错抛 RuntimeError"""
    q = q.strip()[:40]
    platform = "qq" if platform == "qq" else "163"
    now = time.time()
    key = (platform, q)
    hit = _song_cache.get(key)
    if hit and now - hit[0] < 600:
        return hit[1]
    try:
        if platform == "qq":
            songs = _qq_search(q)
        else:
            data = _netease_get("/api/search/get/web", {"s": q, "type": 1, "limit": 10, "offset": 0})
            ids = [sg["id"] for sg in ((data.get("result") or {}).get("songs") or [])]
            details = _song_details(ids)
            songs = [details[i] for i in ids if i in details]
    except Exception:
        raise RuntimeError(f"暂时搜不到歌，{SONG_PLATFORMS[platform]}那边可能出问题了，稍后再试")
    if len(_song_cache) > 300:
        _song_cache.clear()
    _song_cache[key] = (now, songs)
    return songs

def _song_daily_cap(db, sid):
    row = db.execute("SELECT song_daily FROM phone_settings WHERE show_id=?", (sid,)).fetchone()
    return row["song_daily"] if row and row["song_daily"] else _SONG_DEFAULT_DAILY

def _song_used_today(db, sid, role):
    day_start = int(datetime.now(TZ_BEIJING).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    return db.execute("SELECT COUNT(*) FROM song_requests WHERE show_id=? AND from_role=? AND created_at>=? AND deleted=0",
                      (sid, role, day_start)).fetchone()[0]

def _song_roster(db, sid):
    """能被点歌的人：插件上报的角色名单；没同步过就用激活码名单兜底"""
    names = _phone_roster(_phone_sync_row(db, sid))
    if not names:
        names = [r["role_name"] for r in db.execute("SELECT role_name FROM phone_codes WHERE show_id=?", (sid,))]
    return names

def _song_create(db, sid, tid, from_role, to_role, song, message, source):
    """网页和群里共用的点歌入口：返回 (ok, 提示, 行 id)"""
    show = db.execute("SELECT * FROM shows WHERE id=?", (sid,)).fetchone()
    if not show or _schedule_zone(dict(show)) != "main":
        return False, "❌ 不在档期内，暂时不能点歌", None
    # 「送给」可以写名单外的称呼（比如情侣间的化名）：是角色本名就进那个人的点歌台，否则只在公开播报里显示
    to_role = (to_role or "").strip()
    if to_role in ("大家", "所有人"):
        to_role = ""
    if len(to_role) > 20:
        return False, "❌ 「送给」最多 20 字", None
    if to_role == from_role:
        return False, "❌ 不能点给自己", None
    message = (message or "").strip()
    if len(message) > _SONG_MAX_MSG:
        return False, f"❌ 寄语最多 {_SONG_MAX_MSG} 字", None
    if _blocked_hit(sid, from_role, "点歌寄语", to_role, message):
        return False, BLOCKED_MSG, None
    cap = _song_daily_cap(db, sid)
    used = _song_used_today(db, sid, from_role)
    if used >= cap:
        return False, f"🎵 今天已经点了 {cap} 首，明天再来", None
    sync = _phone_sync_row(db, sid)
    game_day = (sync["snap"].get("game_day") or "") if sync else ""
    cur = db.execute("""INSERT INTO song_requests (tenant_id, show_id, from_role, to_role, platform, song_id, song_mid, song_name,
                        artists, album, cover, fee, message, source, game_day, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (tid, sid, from_role, to_role, song["platform"], song["id"], song.get("mid") or "", song["name"],
                      song["artists"], song["album"], song["cover"], 1 if song.get("vip") else 0, message, source,
                      game_day, int(time.time() * 1000)))
    db.commit()
    target = f"给 {to_role}" if to_role else "给大家"
    return True, (f"🎵 已匿名点歌《{song['name']}》- {song['artists']} {target}，稍后在公告里播出。"
                  f"今日第 {used + 1}/{cap} 首"), cur.lastrowid

def _song_view(sg):
    """页面显示用：平台、封面、能不能嵌播放器、跳转链接"""
    qq = sg["platform"] == "qq"
    return {"platform": sg["platform"], "platform_name": SONG_PLATFORMS.get(sg["platform"], ""),
            "id": sg["song_id"], "name": sg["song_name"], "artists": sg["artists"], "cover": sg["cover"],
            "vip": bool(sg["fee"]), "embed": (not qq),
            "link": (f"https://y.qq.com/n/ryqq/songDetail/{sg['song_mid']}" if qq
                     else f"https://y.music.163.com/m/song?id={sg['song_id']}")}

def _song_rows(db, sid):
    return [dict(r) for r in db.execute(
        "SELECT * FROM song_requests WHERE show_id=? AND deleted=0 ORDER BY created_at, id", (sid,))]

@app.route("/p/me/song")
def player_song():
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    db = get_db()
    show = db.execute("SELECT * FROM shows WHERE id=?", (sid,)).fetchone()
    why = _PAUSE_MSG if _phone_comm_paused(db, sid) else (None if _schedule_zone(dict(show)) == "main" else "不在档期内，暂时不能点歌")
    return render_template("phone.html", mode="song", owner=owner, sid=sid, csrf=_phone_csrf(), why=why,
                           contacts=sorted(n for n in _song_roster(db, sid) if n != owner),
                           preset_to=request.args.get("to", ""), cap=_song_daily_cap(db, sid),
                           used=_song_used_today(db, sid, owner), max_msg=_SONG_MAX_MSG)

@app.route("/p/me/song/search")
def player_song_search():
    who = _phone_current()
    if not who:
        return jsonify(ok=False, msg="手机登录已失效"), 401
    q = (request.args.get("q") or "").strip()
    platform = "qq" if request.args.get("platform") == "qq" else "163"
    if not q:
        return jsonify(ok=True, songs=[])
    now = time.time()
    if now - _song_rate.get(who, 0) < 1:
        return jsonify(ok=False, msg="搜得太快了，稍等一下"), 429
    _song_rate[who] = now
    if len(_song_rate) > 5000:
        _song_rate.clear()
    try:
        return jsonify(ok=True, songs=_song_search(q, platform))
    except RuntimeError as e:
        return jsonify(ok=False, msg=str(e)), 502

@app.route("/p/me/song", methods=["POST"])
def player_song_post():
    ok_, err = _moment_guard()
    if err:
        return err
    sid, owner, tid = ok_
    _p = _comm_pause_json(get_db(), sid)
    if _p:
        return _p
    db = get_db()
    platform = "qq" if request.form.get("platform") == "qq" else "163"
    song_key = (request.form.get("song_id") or "").strip()[:40]
    if not song_key:
        return _moment_json(False, "先选一首歌")
    try:
        song = _song_lookup(platform, song_key)
    except Exception:
        song = None
    if not song:
        return _moment_json(False, "这首歌暂时查不到，换一首试试")
    with _phone_send_lock:
        ok, msg, _ = _song_create(db, sid, tid, owner, request.form.get("to", ""), song,
                                  request.form.get("message", ""), "web")
    return _moment_json(ok, msg)

@app.route("/api/song/request", methods=["POST"])
def api_song_request():
    """群里「点歌」：插件把关键词和寄语交过来，这里搜第一首、校验、入库；公告群那份等下一次同步由插件发"""
    tid  = get_tenant_from_token()
    show = get_current_show_for_tenant(tid)
    if not show:
        return jsonify(ok=False, msg="❌ 还没有进行中的季度"), 503
    data = request.json or {}
    from_role = str(data.get("from_role") or "").strip()
    keyword   = str(data.get("keyword") or "").strip()
    if not from_role or not keyword:
        return jsonify(ok=False, msg="❌ 点歌格式：点歌 歌名 [给 对方 寄语]")
    platform = data.get("platform") if data.get("platform") in ("qq", "163") else None
    songs, last_err = [], None
    for pf in ([platform] if platform else ["163", "qq"]):
        try:
            songs = _song_search(keyword, pf)
        except RuntimeError as e:
            last_err = e
            continue
        if songs:
            break
    if not songs and last_err:
        return jsonify(ok=False, msg="❌ " + str(last_err))
    if not songs:
        return jsonify(ok=False, msg=f"❌ 没搜到「{keyword}」，换个关键词试试（可以加上歌手名）")
    db = get_db()
    with _phone_send_lock:
        ok, msg, _ = _song_create(db, show["id"], tid, from_role, data.get("to_role", ""), songs[0],
                                  data.get("message", ""), "group")
    return jsonify(ok=ok, msg=msg)

def _song_pending_for_bot(db, sid, done_ids):
    """同步用：先把插件回报已发的标掉；再给出还没发到公告群的（超过 2 小时的不补发，直接标掉）"""
    now = int(time.time() * 1000)
    ids = [int(i) for i in (done_ids or []) if str(i).isdigit()][:200]
    if ids:
        db.execute(f"UPDATE song_requests SET announced=1 WHERE show_id=? AND id IN ({','.join('?' * len(ids))})",
                   [sid] + ids)
    db.execute("UPDATE song_requests SET announced=1 WHERE show_id=? AND announced=0 AND created_at<?",
               (sid, now - _SONG_ANNOUNCE_TTL))
    db.commit()
    return [{"id": r["id"], "platform": r["platform"], "song_id": r["song_id"], "mid": r["song_mid"],
             "name": r["song_name"], "artists": r["artists"], "to": r["to_role"], "message": r["message"]}
            for r in db.execute("SELECT * FROM song_requests WHERE show_id=? AND announced=0 AND deleted=0 ORDER BY id LIMIT 20",
                                (sid,))]

# ── 时间线与统计（只读）──────────────────────────────────────────────────────────
# 时间线 / 我的数量 / 我的弧长 / 待回 来自插件每 2 分钟上报的报告（phone_reports），跟群里同名指令同一套算法；
# 待回只有不用实时问 QQ 的部分（待进群/待退群/群名还是得在群里查）。互动统计存档站自己算，按玩家手机里看到的样子：
# 短信礼物照「对话」归人（误投/换落款照玩家看到的算），心动信只算寄出的去向、收到的只给总数（来信是匿名的）。
_STATS_VIEWS = ("timeline", "counts", "pending", "arc", "interact")

def _phone_pending_items(report, dismissed=()):
    """待回各项 + 认「这一次提醒」的 key（旧插件没报开始时间时退化成按群/人认）+ 是否已「暂不提醒」"""
    pending = (report or {}).get("pending") or {}
    rel_n = pending.get("rel_n") or {}
    items = []
    for row in pending.get("pending") or []:
        items.append({"kind": "session", "minutes": row["elapsed_min"], "data": row,
                      "key": f"s:{row.get('gid')}:{row.get('since') or ''}"})
    for row in pending.get("letters") or []:
        items.append({"kind": "letter", "minutes": row["wait_min"], "data": row,
                      "key": f"l:{row.get('from')}:{row.get('ts') or ''}"})
    for name in pending.get("rel") or []:
        items.append({"kind": "relation", "minutes": None, "data": name, "key": f"r:{name}:{rel_n.get(name, '')}"})
    for item in items:
        item["dismissed"] = item["key"] in dismissed
    return sorted(items, key=lambda item: -(item["minutes"] if item["minutes"] is not None else -1))


def _phone_timeline_upcoming(db, sid, owner):
    """首页「时间线」快捷入口的数字：还没结束的日程（进行中/待开启，不含微信群）"""
    row = db.execute("SELECT data FROM phone_reports WHERE show_id=? AND role=?", (sid, owner)).fetchone()
    events = (json.loads(row["data"]).get("timeline") or []) if row else []
    return sum(1 for e in events if not e.get("wechat") and not str(e.get("tag") or "").startswith("已完结"))


def _phone_dismissed(db, sid, owner):
    return {r["key"] for r in db.execute("SELECT key FROM phone_pending_dismiss WHERE show_id=? AND role=?", (sid, owner))}


def _phone_pending_summary(db, sid, owner):
    row = db.execute("SELECT data, updated_at FROM phone_reports WHERE show_id=? AND role=?", (sid, owner)).fetchone()
    items = [i for i in (_phone_pending_items(json.loads(row["data"]), _phone_dismissed(db, sid, owner)) if row else [])
             if not i["dismissed"]]
    longest = max((item["minutes"] for item in items if item["minutes"] is not None), default=None)
    duration = ""
    if longest is not None:
        duration = (f"{longest // 60} 小时 " if longest >= 60 else "") + f"{longest % 60} 分钟"
    return {"count": len(items), "longest": duration,
            "stale": bool(row and int(time.time()*1000) - row["updated_at"] > 10*60*1000)}


def _phone_arc_view(text):
    """兼容已上报的文字报告；未知格式保留原文，不推断回复状态。"""
    out = {"average": None, "sample": "", "sessions": [], "notes": []}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or (line.startswith("【") and line.endswith("的弧长】")):
            continue
        summary = re.fullmatch(r"本人总平均[：:]\s*(\d+(?:\.\d+)?)分钟(?:[（(](.*)[）)])?", line)
        if summary:
            out["average"], out["sample"] = summary.group(1), summary.group(2) or ""
            continue
        if line in ("当前未结双嘉宾小群：", "当前未结多人场次："):
            continue
        if line == "当前没有进行中的场次。":
            out["notes"].append(line)
            continue
        event = re.fullmatch(r"(.+?)[：:](.+?)[，,]本人平均(\d+(?:\.\d+)?)分钟[（(](.+?)[）)][，,](.+)", line)
        if not event:
            out["notes"].append(line)
            continue
        title, participants, average, sample, waiting = event.groups()
        progress = ""
        pair = re.fullmatch(r"(.+) (\d+v\d+)[（(]待(.+)[）)]", participants)
        if pair:
            participants, progress, turn = pair.groups()
        gid_m = re.search(r"(\d+)$", title)   # 标题如「私约5001」，末尾数字是群号，用来对上插件上报的本场字数
        out["sessions"].append({"title": title, "gid": gid_m.group(1) if gid_m else "", "participants": participants, "progress": progress,
                                "average": average, "sample": sample, "waiting": waiting})
    return out


def _phone_count_line(text, prefix):
    """只读取明确指定口径的报告行。"""
    for line in (text or "").splitlines():
        match = re.fullmatch(r"\s*(?:[👤🌐]\s*)?" + re.escape(prefix) + r"[：:]\s*(.*?)\s*", line)
        if not match:
            continue
        items = []
        for part in re.split(r"[｜|]", match.group(1)):
            item = re.fullmatch(r"\s*(.+?)\s+(\d+)\s*次\s*", part)
            if not item:
                return []
            items.append({"label": item.group(1), "count": int(item.group(2))})
        return items
    return []


def _phone_personal_counts(text):
    return _phone_count_line(text, "我今天")


def _phone_public_daily(db, sid):
    sync = _phone_sync_row(db, sid)
    day = (sync or {}).get("snap", {}).get("game_day", "")
    if day:
        for row in db.execute("SELECT data, updated_at FROM phone_reports WHERE show_id=? ORDER BY updated_at DESC", (sid,)):
            report = json.loads(row["data"])
            if report.get("day") != day:
                continue
            counts = _phone_count_line(report.get("counts"), "全员今天")
            if counts:
                text = " · ".join(f"{item['label']} {item['count']} 次" for item in counts)
                stale = int(time.time() * 1000) - row["updated_at"] > 10 * 60 * 1000
                return {"text": text, "day": day, "stale": stale}
    return {"text": "今日统计等待同步", "day": day, "stale": False}


@app.route("/p/me/public/daily")
def player_phone_public_daily():
    who = _phone_current()
    if not who:
        return jsonify(error="手机登录已失效"), 401
    return jsonify(_phone_public_daily(get_db(), who[0]))


def _phone_interactions(db, sid, owner):
    rows = {}
    for m in _phone_views(db, sid, owner):
        if m["kind"] not in ("sms", "gift"):
            continue
        who = m["other"].partition("＠")[0]
        r = rows.setdefault(who, {"name": who, "sms_sent": 0, "sms_recv": 0, "gift_sent": 0, "gift_recv": 0, "lm_sent": 0})
        r[f"{m['kind']}_{'sent' if m['mine'] else 'recv'}"] += 1
    lm_recv = 0
    for e in db.execute("SELECT from_role, to_role FROM extra_events WHERE show_id=? AND type='lovemail' AND (from_role=? OR to_role=?)",
                        (sid, owner, owner)):
        if e["to_role"] == owner:
            lm_recv += 1
        if e["from_role"] == owner and e["to_role"]:
            r = rows.setdefault(e["to_role"], {"name": e["to_role"], "sms_sent": 0, "sms_recv": 0, "gift_sent": 0, "gift_recv": 0, "lm_sent": 0})
            r["lm_sent"] += 1
    out = sorted(rows.values(), key=lambda r: -(r["sms_sent"] + r["sms_recv"] + r["gift_sent"] + r["gift_recv"] + r["lm_sent"]))
    return out, lm_recv

@app.route("/p/me/pending/dismiss", methods=["POST"])
def player_pending_dismiss():
    """待回「暂不提醒 / 恢复提醒」：只影响网页上的提醒，不算已回复，群里「我的待回」照旧列出"""
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    key = (request.form.get("key") or "").strip()[:200]
    if not hmac.compare_digest(request.form.get("csrf", ""), session.get("phone_csrf", "") or "-"):
        session["phone_flash"] = "❌ 页面过期了，刷新后再试"
    elif owner != PHONE_ADMIN and key:
        db = get_db()
        if request.form.get("action") == "restore":
            db.execute("DELETE FROM phone_pending_dismiss WHERE show_id=? AND role=? AND key=?", (sid, owner, key))
        else:
            db.execute("INSERT OR IGNORE INTO phone_pending_dismiss (show_id, role, key, created_at) VALUES (?,?,?,?)",
                       (sid, owner, key, int(time.time() * 1000)))
        db.commit()
    return redirect(url_for("player_stats", view="pending"))

@app.route("/p/me/stats")
def player_stats():
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    if owner == PHONE_ADMIN:
        return redirect(url_for("admin_phone_index"))
    db = get_db()
    view = request.args.get("view") if request.args.get("view") in _STATS_VIEWS else "timeline"
    row = db.execute("SELECT data, updated_at FROM phone_reports WHERE show_id=? AND role=?", (sid, owner)).fetchone()
    report = json.loads(row["data"]) if row else None
    days = []
    for ev in (report or {}).get("timeline") or []:
        if not days or days[-1]["day"] != ev.get("day"):
            days.append({"day": ev.get("day") or "", "events": []})
        days[-1]["events"].append(ev)
    inter, lm_recv = _phone_interactions(db, sid, owner) if view == "interact" else ([], 0)
    return render_template("phone.html", mode="stats", owner=owner, sid=sid, view=view, report=report, days=days,
                           updated=(_phone_time(row["updated_at"]) if row else ""),
                           stale=bool(row) and int(time.time() * 1000) - row["updated_at"] > 10 * 60 * 1000,
                           inter=inter, lm_recv=lm_recv,
                           pending_items=_phone_pending_items(report, _phone_dismissed(db, sid, owner)) if view == "pending" else [],
                           csrf=_phone_csrf(), flash=session.pop("phone_flash", None),
                           arc_view=_phone_arc_view((report or {}).get("arc")) if view == "arc" else None,
                           personal_counts=_phone_personal_counts((report or {}).get("counts")) if view == "counts" else [])

# ── 网页群聊 ─────────────────────────────────────────────────────────────────────
# 玩家自己拉人建群（至少再拉 2 个人），任何成员都能拉人、改群名，谁都可以退群；只在网页上，不进 QQ。
# 跟网页发送一起开关（关着时能看不能发、不能建群拉人，退群随时可以）。一条消息算 1 次短信，跟短信共用上限和冷却，
# 插件同步时照短信计次数。规则照短信：违禁词、个人功能权限、混乱效果（内容侵蚀 + 落款错乱；误投/撕信在群里没意义不做）、
# 公开播报（开关和概率同短信）。拉黑：你拉黑的人用真名发的群消息你看不到；化名发言不受实名拉黑影响（同匿名对话，防反查）。
# 发件人自己永远看到原文；化名不能跟角色名单里的人重名。群聊不能送礼。
# 总开关：用户 2026-09-30 要求做好先不放出来。关着时入口、页面、指南条目都不出现，已有的群也不显示；要开时改成 True 再部署
GROUP_CHAT_ON       = False
app.jinja_env.globals["group_chat_on"] = GROUP_CHAT_ON
_GROUP_MAX_MEMBERS  = 20
_GROUP_NAME_MAX     = 20
_GROUP_DAILY_CREATE = 5

def _group_key(gid):
    return f"__group__{gid}"

def _group_get(db, sid, owner, gid):
    """owner 还在群里才返回 (群, 我的成员行)，否则 None；群聊没开放时一律 None"""
    if not GROUP_CHAT_ON:
        return None
    g = db.execute("SELECT * FROM phone_groups WHERE id=? AND show_id=?", (gid, sid)).fetchone()
    if not g:
        return None
    me = db.execute("SELECT * FROM phone_group_members WHERE group_id=? AND role=? AND left_at=0", (gid, owner)).fetchone()
    return (g, me) if me else None

def _group_members(db, gid):
    return [r["role"] for r in db.execute(
        "SELECT role FROM phone_group_members WHERE group_id=? AND left_at=0 ORDER BY joined_at, role", (gid,))]

def _group_sys(db, g, text, now):
    sync = _phone_sync_row(db, g["show_id"])
    game_day = (sync["snap"].get("game_day") or "") if sync else ""
    db.execute("INSERT INTO phone_group_msgs (tenant_id, show_id, group_id, kind, content, delivered, game_day, created_at) VALUES (?,?,?,?,?,?,?,?)",
               (g["tenant_id"], g["show_id"], g["id"], "sys", text, text, game_day, now))

def _group_msgs(db, sid, owner, g, me, roster=None, blocked=None):
    """某个群在 owner 眼里的消息（入群之后的；被我拉黑的人用真名发的看不到），格式跟私聊的 view 一样"""
    if roster is None or blocked is None:
        sync = _phone_sync_row(db, sid)
        snap = sync["snap"] if sync else {}
        roster = set(_phone_roster(sync))
        blocked = {b.get("blocked") for b in _phone_effective_blocks(db, sid, snap) if b.get("blocker") == owner}
    key, out = _group_key(g["id"]), []
    for r in db.execute("SELECT * FROM phone_group_msgs WHERE group_id=? AND created_at>=? AND deleted=0 ORDER BY id",
                        (g["id"], me["joined_at"])):
        base = {"id": f"g{r['id']}", "other": key, "ts": r["created_at"], "game_day": r["game_day"] or "", "public": False}
        if r["kind"] == "sys":
            out.append(dict(base, kind="sys", mine=False, text=r["content"], signature=""))
            continue
        mine = r["from_role"] == owner
        if not mine and not r["alias"] and r["from_role"] in blocked:
            continue
        shown = r["signature"] or r["from_role"]
        out.append(dict(base, kind="gsms", mine=mine, text=r["content"] if mine else r["delivered"],
                        signature="" if mine else shown, alias=r["alias"] if mine else "", public=bool(r["is_public"]),
                        av=None if (r["alias"] or shown not in roster) else shown, av_initial=shown[:1],
                        admin_del=f"group:{r['id']}"))
    return out

def _group_list(db, sid, owner):
    if not GROUP_CHAT_ON:
        return []
    return db.execute("""SELECT g.*, m.joined_at FROM phone_groups g JOIN phone_group_members m ON m.group_id=g.id
                         WHERE g.show_id=? AND m.role=? AND m.left_at=0 ORDER BY g.id""", (sid, owner)).fetchall()

def _group_views(db, sid, owner):
    """所有群的消息（给「有新消息」指纹和轮询用）"""
    sync = _phone_sync_row(db, sid)
    snap = sync["snap"] if sync else {}
    roster = set(_phone_roster(sync))
    blocked = {b.get("blocked") for b in _phone_effective_blocks(db, sid, snap) if b.get("blocker") == owner}
    out = []
    for g in _group_list(db, sid, owner):
        out += _group_msgs(db, sid, owner, g, {"joined_at": g["joined_at"]}, roster, blocked)
    return out

def _group_threads(db, sid, owner):
    """收件箱里的群聊行，格式跟私聊行一样，多一个 group"""
    sync = _phone_sync_row(db, sid)
    snap = sync["snap"] if sync else {}
    roster = set(_phone_roster(sync))
    blocked = {b.get("blocked") for b in _phone_effective_blocks(db, sid, snap) if b.get("blocker") == owner}
    out = []
    for g in _group_list(db, sid, owner):
        msgs = _group_msgs(db, sid, owner, g, {"joined_at": g["joined_at"]}, roster, blocked)
        n = len(_group_members(db, g["id"]))
        last = msgs[-1] if msgs else {"ts": g["joined_at"], "game_day": "", "mine": False, "kind": "sys", "text": "群聊已创建"}
        if last["kind"] == "sys":
            preview = last["text"]
        else:
            preview = ("我：" if last["mine"] else f"{last['signature']}：") + last["text"].replace("\n", " ")
        out.append({"other": _group_key(g["id"]), "group": {"id": g["id"], "name": g["name"], "n": n}, "last": last,
                    "received_ts": max([m["ts"] for m in msgs if not m["mine"]] or [0]),
                    "preview": preview, "time": _phone_time(last["ts"])})
    return out

def _phone_all_views(db, sid, owner):
    return _phone_views(db, sid, owner) + _group_views(db, sid, owner)

def _group_can_act(db, sid, owner):
    """建群/发言/拉人/改名的共同前提：跟网页发送一样"""
    if not GROUP_CHAT_ON:
        return "群聊还没有开放"
    st = _phone_status(db, sid, owner)
    if not st["can"]:
        return st["why"] or "网页发送没有开放"
    if not st["sms"]:
        return "寄信功能已关闭"
    return ""

def _group_check_name(sid, owner, name):
    if len(name) > _GROUP_NAME_MAX:
        return f"❌ 群名最多 {_GROUP_NAME_MAX} 字"
    if _CQ_CODE.search(name) or _blocked_hit(sid, owner, "群名", name):
        return BLOCKED_MSG
    return ""

def _group_create(db, sid, tid, owner, name, members):
    why = _group_can_act(db, sid, owner)
    if why:
        return False, "❌ " + why, None
    roster = _phone_roster(_phone_sync_row(db, sid))
    members = [m for m in dict.fromkeys(members) if m and m != owner]
    if any(m not in roster for m in members):
        return False, "❌ 只能拉角色名单里的人", None
    if len(members) < 2:
        return False, "❌ 至少再选 2 个人才能建群（两个人直接发短信就好）", None
    if len(members) + 1 > _GROUP_MAX_MEMBERS:
        return False, f"❌ 一个群最多 {_GROUP_MAX_MEMBERS} 人", None
    name = (name or "").strip()
    if not name:  # 没起名就用成员名，太长截掉
        name = ("、".join([owner] + members[:2]) + ("等" if len(members) > 2 else ""))[:_GROUP_NAME_MAX]
    err = _group_check_name(sid, owner, name)
    if err:
        return False, err, None
    now = int(time.time() * 1000)
    day_start = int(datetime.now(TZ_BEIJING).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    if db.execute("SELECT COUNT(*) FROM phone_groups WHERE show_id=? AND created_by=? AND created_at>=?",
                  (sid, owner, day_start)).fetchone()[0] >= _GROUP_DAILY_CREATE:
        return False, f"❌ 今天已经建了 {_GROUP_DAILY_CREATE} 个群，明天再来", None
    gid = db.execute("INSERT INTO phone_groups (tenant_id, show_id, name, created_by, created_at) VALUES (?,?,?,?,?)",
                     (tid, sid, name, owner, now)).lastrowid
    for m in [owner] + members:
        db.execute("INSERT INTO phone_group_members (group_id, role, joined_at) VALUES (?,?,?)", (gid, m, now))
    g = db.execute("SELECT * FROM phone_groups WHERE id=?", (gid,)).fetchone()
    _group_sys(db, g, f"{owner} 发起了群聊，拉了 {'、'.join(members)}", now)
    db.commit()
    return True, "", gid

def _group_send(db, sid, owner, gid, text, alias):
    """群里发一条：返回 (ok, 提示)；调用方持有 _phone_send_lock"""
    got = _group_get(db, sid, owner, gid)
    if not got:
        return False, "❌ 你不在这个群里了"
    g, _ = got
    why = _group_can_act(db, sid, owner)
    if why:
        return False, "❌ " + why
    sync = _phone_sync_row(db, sid)
    snap, now = sync["snap"], int(time.time() * 1000)
    rules = snap.get("rules") or {}
    roster = _phone_roster(sync)
    if owner not in roster:
        return False, "❌ 找不到你的角色，等机器人下一次同步后再试"
    if "sms" in set((snap.get("feature_off") or {}).get(owner) or []):
        return False, "🕊️ 你被限制使用寄信功能。"
    text, alias = (text or "").strip(), (alias or "").strip()
    if not text:
        return False, "❌ 内容不能为空"
    if len(text) > _PHONE_MAX_LEN:
        return False, f"❌ 太长了，最多 {_PHONE_MAX_LEN} 字"
    if alias:
        if len(alias) > _ALIAS_MAX_LEN:
            return False, f"❌ 化名最多 {_ALIAS_MAX_LEN} 字"
        if alias in roster or alias in _ALIAS_RESERVED or "＠" in alias:
            return False, "❌ 这个化名不能用，换一个"
    if _CQ_CODE.search(text + alias) or _blocked_hit(sid, owner, "群聊", text, alias):
        return False, BLOCKED_MSG
    chaos = rules.get("chaos") or {}
    limit = int(chaos.get("dailyLimit", 5))
    cooldown_ms = max(int(rules.get("mail_cooldown_min", 60)) * 60000, _PHONE_MIN_GAP_MS)
    used, last = _phone_usage(db, sid, sync, owner, "sms", now)
    if now - last < cooldown_ms:
        return False, f"⏳ 鸽子正在休息，请 {math.ceil((cooldown_ms - (now - last)) / 60000)} 分钟后再试"
    if used >= limit:
        return False, f"🕊️ 今日寄信次数已达上限({limit})"
    rnd = secrets.SystemRandom()
    delivered = _chaos_erode(text, chaos)
    signature = alias or owner
    if not alias and rnd.random() < float(chaos.get("mistakenSignature", 0)) / 100:
        others = [n for n in roster if n != owner]
        if others:
            signature = rnd.choice(others)
    is_public = bool(rules.get("sms_public")) and rnd.randint(1, 100) <= int(chaos.get("publicChance", 50))
    day_key, game_day, _ = _phone_day(sync, now)
    db.execute("""INSERT INTO phone_group_msgs (tenant_id, show_id, group_id, kind, from_role, alias, signature, content, delivered,
                  is_public, hide_receiver, show_effect, game_day, day_key, created_at) VALUES (?,?,?,'msg',?,?,?,?,?,?,?,?,?,?,?)""",
               (g["tenant_id"], sid, gid, owner, alias, signature, text, delivered, 1 if is_public else 0,
                1 if is_public and rules.get("hide_receiver") else 0, 1 if chaos.get("publicShowEffect") else 0,
                game_day, day_key, now))
    db.commit()
    return True, f"💬 已发到群聊「{g['name']}」。今日已发 {used + 1}/{limit}。"

def _group_manage(db, sid, owner, gid, action, value):
    got = _group_get(db, sid, owner, gid)
    if not got:
        return False, "❌ 你不在这个群里了"
    g, _ = got
    now = int(time.time() * 1000)
    if action == "leave":
        db.execute("UPDATE phone_group_members SET left_at=? WHERE group_id=? AND role=?", (now, gid, owner))
        _group_sys(db, g, f"{owner} 退出了群聊", now)
        db.commit()
        return True, f"已退出群聊「{g['name']}」"
    why = _group_can_act(db, sid, owner)
    if why:
        return False, "❌ " + why
    value = (value or "").strip()
    if action == "rename":
        if not value:
            return False, "❌ 群名不能为空"
        err = _group_check_name(sid, owner, value)
        if err:
            return False, err
        db.execute("UPDATE phone_groups SET name=? WHERE id=?", (value, gid))
        _group_sys(db, g, f"{owner} 把群名改成了「{value}」", now)
        db.commit()
        return True, "✅ 群名已修改"
    if action == "add":
        members = _group_members(db, gid)
        if value not in _phone_roster(_phone_sync_row(db, sid)):
            return False, "❌ 只能拉角色名单里的人"
        if value in members:
            return False, f"「{value}」已经在群里了"
        if len(members) >= _GROUP_MAX_MEMBERS:
            return False, f"❌ 一个群最多 {_GROUP_MAX_MEMBERS} 人"
        db.execute("""INSERT INTO phone_group_members (group_id, role, joined_at) VALUES (?,?,?)
                      ON CONFLICT(group_id, role) DO UPDATE SET joined_at=excluded.joined_at, left_at=0""", (gid, value, now))
        _group_sys(db, g, f"{owner} 拉 {value} 进了群", now)
        db.commit()
        return True, f"✅ 已把「{value}」拉进群"
    return False, "❌ 不认识的操作"

@app.route("/p/me/g/new", methods=["GET", "POST"])
def player_group_new():
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    if owner == PHONE_ADMIN:
        return redirect(url_for("admin_phone_index"))
    if not GROUP_CHAT_ON:
        return redirect(url_for("player_phone_new"))
    db = get_db()
    if request.method == "POST":
        if not hmac.compare_digest(request.form.get("csrf", ""), session.get("phone_csrf", "") or "-"):
            session["phone_flash"] = "❌ 页面过期了，刷新后再试"
            return redirect(url_for("player_group_new"))
        tid = db.execute("SELECT tenant_id FROM shows WHERE id=?", (sid,)).fetchone()["tenant_id"]
        with _phone_send_lock:
            ok, msg, gid = _group_create(db, sid, tid, owner, request.form.get("name", ""), request.form.getlist("member"))
        if ok:
            return redirect(url_for("player_group_thread", gid=gid))
        session["phone_flash"] = msg
        return redirect(url_for("player_group_new"))
    return render_template("phone.html", mode="group_new", owner=owner, sid=sid, csrf=_phone_csrf(),
                           why=_group_can_act(db, sid, owner), flash=session.pop("phone_flash", None),
                           contacts=sorted(n for n in _phone_roster(_phone_sync_row(db, sid)) if n != owner),
                           name_max=_GROUP_NAME_MAX, max_members=_GROUP_MAX_MEMBERS)

@app.route("/p/me/g/<int:gid>")
def player_group_thread(gid):
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    if owner == PHONE_ADMIN:
        return redirect(url_for("admin_phone_index"))
    db = get_db()
    got = _group_get(db, sid, owner, gid)
    if not got:
        session["phone_flash"] = "你不在这个群里"
        return redirect(url_for("player_phone_inbox"))
    g, me = got
    st = _phone_status(db, sid, owner)
    members = _group_members(db, gid)
    return render_template("phone.html", mode="thread", owner=owner, sid=sid, other=_group_key(gid),
                           group={"id": gid, "name": g["name"], "members": members, "n": len(members)},
                           addable=sorted(n for n in _phone_roster(_phone_sync_row(db, sid)) if n not in members),
                           alias_thread=None, alias_state=None, block_state=None,
                           msgs=_phone_mark_breaks([dict(m, time=_phone_time(m["ts"])) for m in _group_msgs(db, sid, owner, g, me)]),
                           status=st, can_reply=st["can"], revision=_phone_revision(_phone_all_views(db, sid, owner)),
                           stickers=_phone_stickers(db, sid) if st["can"] else [], my_presets=[],
                           csrf=_phone_csrf(), sent=session.pop("phone_sent", False), flash=session.pop("phone_flash", None),
                           draft=session.pop("phone_draft", ""), draft_kind="sms", draft_gift="",
                           group_alias=session.pop("group_alias", ""), alias_len=_ALIAS_MAX_LEN)

@app.route("/p/me/g/<int:gid>/send", methods=["POST"])
def player_group_send(gid):
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    back = url_for("player_group_thread", gid=gid)
    if not hmac.compare_digest(request.form.get("csrf", ""), session.get("phone_csrf", "") or "-"):
        ok, msg = False, "❌ 页面过期了，刷新后再发"
    elif owner == PHONE_ADMIN:
        ok, msg = False, "❌ 管理身份不能发"
    else:
        with _phone_send_lock:
            ok, msg = _group_send(get_db(), sid, owner, gid, request.form.get("text", ""), request.form.get("alias", ""))
    session["phone_flash"], session["phone_sent"] = msg, ok
    session["group_alias"] = (request.form.get("alias", "") or "")[:_ALIAS_MAX_LEN]  # 化名留着，连发不用重填
    if not ok:
        session["phone_draft"] = request.form.get("text", "")[:_PHONE_MAX_LEN]
    return redirect(back)

@app.route("/p/me/g/<int:gid>/manage", methods=["POST"])
def player_group_manage(gid):
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    if not hmac.compare_digest(request.form.get("csrf", ""), session.get("phone_csrf", "") or "-"):
        session["phone_flash"] = "❌ 页面过期了，刷新后再试"
        return redirect(url_for("player_group_thread", gid=gid))
    action = request.form.get("action", "")
    with _phone_send_lock:
        ok, msg = _group_manage(get_db(), sid, owner, gid, action, request.form.get("value", ""))
    session["phone_flash"] = msg
    if ok and action == "leave":
        return redirect(url_for("player_phone_inbox"))
    return redirect(url_for("player_group_thread", gid=gid))

@app.route("/p/me/block", methods=["POST"])
def player_phone_block():
    """对话页「⋯」里的实名拉黑/解除：规则同群里「拉黑 角色名 [静默]」「取消拉黑 角色名」"""
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    target = request.form.get("target", "").strip()
    back = url_for("player_phone_thread", other=target) if target else url_for("player_phone_inbox")
    if not hmac.compare_digest(request.form.get("csrf", ""), session.get("phone_csrf", "") or "-"):
        session["phone_flash"] = "❌ 页面过期了，刷新后再试"
        return redirect(back)
    db = get_db()
    with _phone_send_lock:
        st = _phone_block_state(db, sid, owner, target)
        action = "unblock" if request.form.get("action") == "unblock" else "block"
        silent = request.form.get("silent") == "1"
        if st is None:
            msg = "❌ 这里不能拉黑 TA"
        elif action == "unblock" and not st["blocked"]:
            msg = f"❓ 你并没有拉黑「{target}」"
        elif action == "unblock" and st["wait_min"]:
            msg = f"⏳ 拉黑满 2 小时才能解除，还要等 {st['wait_min']} 分钟"
        elif action == "block" and st["blocked"] and st["silent"] == silent:
            msg = f"已经拉黑「{target}」了"
        else:
            db.execute("INSERT INTO phone_block_ops (show_id, blocker, target, action, silent, created_at) VALUES (?,?,?,?,?,?)",
                       (sid, owner, target, action, 1 if silent else 0, int(time.time() * 1000)))
            db.commit()
            msg = (f"✅ 已取消拉黑「{target}」" if action == "unblock" else
                   f"🚫 已拉黑「{target}」（{'静默' if silent else '不静默'}），TA 之后发起的短信/礼物/私约/电话/微信/漂流瓶回信都不会再送达你，"
                   f"群里半分钟内同步生效。满 2 小时后才能解除")
    session["phone_flash"] = msg
    return redirect(back)

def _block_ops_for_bot(db, sid, done_ids):
    ids = [int(i) for i in (done_ids or []) if str(i).isdigit()][:200]
    if ids:
        db.execute(f"UPDATE phone_block_ops SET done=1 WHERE show_id=? AND id IN ({','.join('?' * len(ids))})", [sid] + ids)
        db.commit()
    return [{"id": r["id"], "blocker": r["blocker"], "target": r["target"], "action": r["action"],
             "silent": bool(r["silent"]), "ts": r["created_at"]}
            for r in db.execute("SELECT * FROM phone_block_ops WHERE show_id=? AND done=0 ORDER BY id LIMIT 50", (sid,))]

# ── 心动信 ─────────────────────────────────────────────────────────────────────
# 规则、今日已投封数、还在机器人信池里等派送的信，全部来自插件同步快照（rules.lovemail / snapshot.lovemail），存档站不另存一套。
# 网页投的信先进 phone_lovemails，下一次同步交给机器人放进它的信池、计进每日次数，之后跟群里投的一样每晚统一派送；
# 派送时机器人照常 POST /api/event 存档，所以「收到的 / 寄出的」往期直接读存档。
# 机器人没连上（快照过期）时不收信：信只能靠它派送，次数也只有它算得准。收件人只看得到署名，看不到是谁寄的。
_LM_MAX_LEN = 500
_LM_SIG_MAX = 20
_CQ_CODE    = re.compile(r"\[CQ:[^\]]*\]")

def _lm_state(db, sid, owner):
    """页面和投递共用：能不能投、为什么不能、今日上限/已投、等派送的信（机器人信池里的 + 网页还没交出去的）"""
    now  = int(time.time() * 1000)
    show = db.execute("SELECT * FROM shows WHERE id=?", (sid,)).fetchone()
    sync = _phone_sync_row(db, sid)
    snap = sync["snap"] if sync else {}
    rules = (snap.get("rules") or {}).get("lovemail")
    st = {"ready": rules is not None, "can": False, "why": "", "limit": 0, "used": 0, "pending": [],
          "delivery_time": "", "game_day": snap.get("game_day") or ""}
    if rules is None:
        st["why"] = "心动信要等机器人升级到新版本、同步过一次才能在网页上用"
        return st
    lm = snap.get("lovemail") or {}
    st["limit"] = int(rules.get("limit") or 0)
    st["delivery_time"] = rules.get("delivery_time") or ""
    revoking = {r["mail_ts"] for r in db.execute(
        "SELECT mail_ts FROM phone_lovemail_revokes WHERE show_id=? AND from_role=? AND done=0", (sid, owner))}
    pool = [p for p in (lm.get("pending") or []) if p.get("from") == owner]
    handed = {p.get("web_id") for p in pool if p.get("web_id")}
    pending = [{"to": p.get("to") or "", "content": _CQ_CODE.sub("", p.get("content") or "").strip(),
                "signature": p.get("signature") or "匿名", "game_day": p.get("game_day") or "",
                "ts": int(p.get("ts") or 0), "web_id": 0, "revoking": int(p.get("ts") or 0) in revoking} for p in pool]
    web = [r for r in db.execute("SELECT * FROM phone_lovemails WHERE show_id=? AND from_role=? AND state='new' ORDER BY id",
                                 (sid, owner)) if r["id"] not in handed]
    pending += [{"to": r["to_role"], "content": r["content"], "signature": r["signature"], "game_day": r["game_day"],
                 "ts": r["created_at"], "web_id": r["id"], "revoking": False} for r in web]
    st["pending"] = sorted(pending, key=lambda p: p["ts"])
    day = st["game_day"]
    st["used"] = int((lm.get("counts") or {}).get(owner) or 0) + sum(1 for r in web if r["game_day"] == day)
    win = rules.get("window")
    hour = datetime.now(TZ_BEIJING).hour
    if _schedule_zone(dict(show)) != "main":
        why = "不在档期内，暂时不能投信"
    elif now - sync["synced_at"] >= _PHONE_SYNC_FRESH_MS and not snap.get("demo"):  # 演示季没有机器人，快照是脚本写死的
        why = "机器人暂时没连上，信要靠它派送，稍后再来投"
    elif not rules.get("enabled"):
        why = "心动信箱已关闭，暂不可投稿"
    elif not rules.get("has_day"):
        why = "还没设置游戏天数，暂时不能投信"
    elif "lovemail" in set((snap.get("feature_off") or {}).get(owner) or []):
        why = "你的心动信功能已被管理员关闭"
    elif win and not (int(win.get("start", 0)) <= hour < int(win.get("end", 24))):
        why = f"心动信开放时间为 {int(win['start']):02d}:00–{int(win['end']):02d}:00"
    elif st["limit"] <= 0:
        why = f"{day} 的心动信投稿已关闭"
    elif st["used"] >= st["limit"]:
        why = f"{day} 已经投了 {st['used']} 封（上限 {st['limit']} 封），等下一天再来"
    else:
        why = ""
    st["why"], st["can"] = why, not why
    return st

def _lm_send(db, sid, tid, owner, to_role, content, signature):
    """网页投信：返回 (ok, 提示)。调用方持有 _phone_send_lock，查次数和写入之间不会被插队"""
    st = _lm_state(db, sid, owner)
    if not st["can"]:
        return False, "📪 " + st["why"]
    to_role = (to_role or "").strip()
    if to_role not in _phone_roster(_phone_sync_row(db, sid)):
        return False, "❌ 找不到这个收件人，请从名单里选"
    content = (content or "").strip()
    signature = (signature or "").strip() or "匿名"
    if not content:
        return False, "❌ 写点什么再投"
    if len(content) > _LM_MAX_LEN:
        return False, f"❌ 信最多 {_LM_MAX_LEN} 字（现在 {len(content)} 字）"
    if len(signature) > _LM_SIG_MAX:
        return False, f"❌ 署名最多 {_LM_SIG_MAX} 字"
    if _CQ_CODE.search(content + signature):
        return False, "❌ 信里不能带 [CQ:…] 这样的代码"
    if _blocked_hit(sid, owner, "心动信", content, signature):
        return False, BLOCKED_MSG
    db.execute("""INSERT INTO phone_lovemails (tenant_id, show_id, from_role, to_role, content, signature, game_day, created_at)
                  VALUES (?,?,?,?,?,?,?,?)""",
               (tid, sid, owner, to_role, content, signature, st["game_day"], int(time.time() * 1000)))
    db.commit()
    left = st["limit"] - st["used"] - 1
    when = f"{st['delivery_time']} " if st["delivery_time"] else ""
    return True, f"💌 已投进「{to_role}」的信箱，{when}统一派送。{st['game_day']} 还能投 {left} 封"

def _lm_revoke(db, sid, owner, ts, web_id):
    """撤回还没派送的信：网页的还没交给机器人就直接作废；已经在机器人信池里的，记一条撤回请求等下次同步"""
    now = int(time.time() * 1000)
    if web_id:
        row = db.execute("SELECT * FROM phone_lovemails WHERE id=? AND show_id=? AND from_role=?",
                         (web_id, sid, owner)).fetchone()
        if not row or row["state"] != "new":
            return False, "这封信已经交给邮差了，刷新看看"
        db.execute("UPDATE phone_lovemails SET state='revoked' WHERE id=?", (web_id,))
        if row["handed_at"]:  # 同步回包里已经给过机器人，它可能已经放进信池
            db.execute("INSERT INTO phone_lovemail_revokes (show_id, from_role, mail_ts, created_at) VALUES (?,?,?,?)",
                       (sid, owner, row["created_at"], now))
        db.commit()
        return True, "✅ 已撤回，今日次数会还给你"
    st = _lm_state(db, sid, owner)
    if not any(p["ts"] == ts and not p["web_id"] for p in st["pending"]):
        return False, "找不到这封信，可能已经派送了"
    if not db.execute("SELECT 1 FROM phone_lovemail_revokes WHERE show_id=? AND from_role=? AND mail_ts=? AND done=0",
                      (sid, owner, ts)).fetchone():
        db.execute("INSERT INTO phone_lovemail_revokes (show_id, from_role, mail_ts, created_at) VALUES (?,?,?,?)",
                   (sid, owner, ts, now))
        db.commit()
    return True, "✅ 撤回已提交，半分钟内生效，次数会还给你（到点已经派送的就撤不回了）"

def _lm_history(db, sid, owner):
    """存档里已经派送的心动信：(收到的, 寄出的)，新的在前。收到的只给署名，不给发件人"""
    recv, sent = [], []
    for r in db.execute("""SELECT id, from_role, to_role, content, extra_info, timestamp, game_day FROM extra_events
                           WHERE show_id=? AND type='lovemail' AND (to_role=? OR from_role=?) ORDER BY id DESC""",
                        (sid, owner, owner)):
        info = json.loads(r["extra_info"] or "{}")
        item = {"id": r["id"], "content": _CQ_CODE.sub("", r["content"] or "").strip() or "（图片）",
                "signature": info.get("signature") or info.get("from_custom_name") or "匿名",
                "game_day": r["game_day"] or "", "public": bool(info.get("isPublic"))}
        if r["to_role"] == owner:
            recv.append(item)
        if r["from_role"] == owner:
            sent.append(dict(item, to=r["to_role"]))
    return recv, sent

def _lm_for_bot(db, sid, done_ids, revoke_done):
    """同步用：标掉机器人回报已放进信池的 / 已处理的撤回，再给出还没交出去的信和撤回请求"""
    now = int(time.time() * 1000)
    for ids, sql in ((done_ids, "UPDATE phone_lovemails SET state='taken' WHERE show_id=? AND state='new' AND id IN ({})"),
                     (revoke_done, "UPDATE phone_lovemail_revokes SET done=1 WHERE show_id=? AND id IN ({})")):
        ids = [int(i) for i in (ids or []) if str(i).isdigit()][:200]
        if ids:
            db.execute(sql.format(",".join("?" * len(ids))), [sid] + ids)
    mails = db.execute("SELECT * FROM phone_lovemails WHERE show_id=? AND state='new' ORDER BY id LIMIT 50", (sid,)).fetchall()
    if mails:
        db.execute(f"UPDATE phone_lovemails SET handed_at=? WHERE handed_at=0 AND id IN ({','.join('?' * len(mails))})",
                   [now] + [m["id"] for m in mails])
    revokes = db.execute("SELECT * FROM phone_lovemail_revokes WHERE show_id=? AND done=0 ORDER BY id LIMIT 50", (sid,)).fetchall()
    db.commit()
    return ([{"id": m["id"], "from_role": m["from_role"], "to_role": m["to_role"], "content": m["content"],
              "signature": m["signature"], "game_day": m["game_day"], "timestamp": m["created_at"]} for m in mails],
            [{"id": r["id"], "from_role": r["from_role"], "ts": r["mail_ts"]} for r in revokes])

_QUOTE_SOURCES = {
    # 一言：只要文学(d)/诗词(i)/哲学(k)，避开动漫游戏类
    "hitokoto": ("https://v1.hitokoto.cn/?c=d&c=i&c=k&max_length=40&encode=json",
                 lambda j: (j["hitokoto"], "——" + (j.get("from_who") or "") + "《" + j["from"] + "》" if j.get("from") else ("——" + j["from_who"] if j.get("from_who") else ""))),
    "shici":    ("https://v2.jinrishici.com/one.json",
                 lambda j: (j["data"]["content"], "——" + j["data"]["origin"]["author"] + "《" + j["data"]["origin"]["title"] + "》")),
}

def _quote_fetch(kind):
    import urllib.request
    url, parse = _QUOTE_SOURCES[kind]
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "rp-archive"}), timeout=3) as r:
            text, source = parse(json.loads(r.read().decode("utf-8")))
        text = (text or "").strip()
        return (text[:80], source[:40]) if text else None
    except Exception:
        return None

@app.route("/p/me/quote")
def player_quote():
    """消息页「每日一句」：一言 / 今日诗词各缓存一条，当天第一次请求时去拉，拉不到就用最近一次的。"""
    if not _phone_current():
        return jsonify(error="手机登录已失效"), 401
    db = get_db()
    day = datetime.now().strftime("%Y-%m-%d")
    out = []
    for kind in _QUOTE_SOURCES:
        row = db.execute("SELECT text, source FROM daily_quotes WHERE day=? AND kind=?", (day, kind)).fetchone()
        if not row:
            got = _quote_fetch(kind)
            if got:
                db.execute("INSERT OR IGNORE INTO daily_quotes (day, kind, text, source) VALUES (?,?,?,?)", (day, kind, got[0], got[1]))
                db.commit()
                row = {"text": got[0], "source": got[1]}
            else:
                row = db.execute("SELECT text, source FROM daily_quotes WHERE kind=? ORDER BY day DESC LIMIT 1", (kind,)).fetchone()
        if row:
            out.append({"kind": kind, "text": row["text"], "source": row["source"]})
    return jsonify(quotes=out)

@app.route("/p/me/character")
def player_character():
    """角色页：背包 / 属性（只读）。数据是插件随 phone_reports 每 2 分钟上报的 rpg 快照，操作仍在 QQ 里。"""
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    if owner == PHONE_ADMIN:
        return redirect(url_for("admin_phone_index"))
    row = get_db().execute("SELECT data, updated_at FROM phone_reports WHERE show_id=? AND role=?", (sid, owner)).fetchone()
    rpg = (json.loads(row["data"]).get("rpg") if row else None) or None
    return render_template("phone.html", mode="char", owner=owner, sid=sid, csrf=_phone_csrf(), rpg=rpg,
                           rpg_time=(ts_to_str(row["updated_at"]) if row and rpg else ""),
                           view="attrs" if request.args.get("view") == "attrs" else "bag")

@app.route("/p/me/lovemail/last")
def player_lovemail_last():
    """轻量接口：收到的最新一封心动信的存档 id，页面开着时每 30 秒查一次，准点派送后弹「已送达」"""
    who = _phone_current()
    if not who:
        return jsonify(error="手机登录已失效"), 401
    last = get_db().execute("SELECT MAX(id) FROM extra_events WHERE show_id=? AND type='lovemail' AND to_role=?", who).fetchone()[0]
    return jsonify(last=last or 0)

@app.route("/p/me/lovemail")
def player_lovemail():
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    if owner == PHONE_ADMIN:
        return redirect(url_for("admin_phone_index"))
    db = get_db()
    view = request.args.get("view") if request.args.get("view") in ("sent", "write") else "inbox"
    recv, sent = _lm_history(db, sid, owner)
    return render_template("phone.html", mode="lovemail", owner=owner, sid=sid, view=view, lm=_lm_state(db, sid, owner),
                           recv=recv, sent=sent, csrf=_phone_csrf(), max_len=_LM_MAX_LEN, sig_max=_LM_SIG_MAX,
                           contacts=sorted(n for n in _phone_roster(_phone_sync_row(db, sid)) if n != owner),
                           preset_to=request.args.get("to", ""), flash=session.pop("lm_flash", None) or (_PAUSE_MSG if _phone_comm_paused(db, sid) else None),
                           draft=session.pop("lm_draft", None))

@app.route("/p/me/lovemail", methods=["POST"])
def player_lovemail_post():
    who = _phone_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid, owner = who
    if owner == PHONE_ADMIN:
        return redirect(url_for("admin_phone_index"))
    f = request.form
    if not hmac.compare_digest(f.get("csrf", ""), session.get("phone_csrf", "") or "-"):
        ok, msg = False, "❌ 页面过期了，刷新后再投"
    else:
        db = get_db()
        tid = db.execute("SELECT tenant_id FROM shows WHERE id=?", (sid,)).fetchone()["tenant_id"]
        with _phone_send_lock:
            if f.get("action") == "revoke":
                ok, msg = _lm_revoke(db, sid, owner, int(f.get("ts") or 0) if str(f.get("ts") or "").isdigit() else 0,
                                     int(f.get("web_id") or 0) if str(f.get("web_id") or "").isdigit() else 0)
            else:
                ok, msg = _lm_send(db, sid, tid, owner, f.get("to", ""), f.get("content", ""), f.get("signature", ""))
    session["lm_flash"] = msg
    if f.get("action") == "revoke":
        return redirect(url_for("player_lovemail", view="sent"))
    if not ok:  # 没投出去，草稿留着
        session["lm_draft"] = {"to": f.get("to", "")[:20], "content": f.get("content", "")[:_LM_MAX_LEN],
                               "signature": f.get("signature", "")[:_LM_SIG_MAX]}
        return redirect(url_for("player_lovemail", view="write"))
    return redirect(url_for("player_lovemail", view="sent"))

# ── 管理身份（网页手机里维护）───────────────────────────────────────────────────
# 用后台生成的「管理员手机码」进门：能以任何角色的视角翻手机（每条带管理员才看得到的真实情况小字），
# 能删短信/礼物/朋友圈/评论/图片/点歌/头像；前端每次删除都有二次确认，后端每次删除都记 moderation.log。
# 不能发任何东西（所有玩家写接口对管理身份一律拒绝）。

def _phone_admin_current():
    who = _phone_current()
    return who if who and who[1] == PHONE_ADMIN else None

def _admin_role_list(db, sid):
    names = set(_phone_roster(_phone_sync_row(db, sid)))
    names |= {r["role_name"] for r in db.execute("SELECT role_name FROM phone_codes WHERE show_id=?", (sid,))}
    for r in db.execute("SELECT from_role, to_role FROM extra_events WHERE show_id=? AND type IN ('sms','gift')", (sid,)):
        names.update(n for n in (r["from_role"], r["to_role"]) if n)
    return sorted(names)

def _admin_note(e):
    """管理员看的真实情况：一行小字"""
    info = e.get("extra_info") or {}
    if e["type"] == "song":
        return f"点歌人：{e['from_role']}"
    parts = [f"实际：{e['from_role']} → {e['to_role'] or '（静默拉黑，未送达）'}"]
    if info.get("alias_id"):
        parts.append(f"匿名对话：{info.get('alias_owner')} 用化名「{info.get('alias_name')}」")
    if info.get("from_custom_name"):
        parts.append(f"署名「{info['from_custom_name']}」")
    intended = info.get("intended_to")
    if intended and intended != e["to_role"] and e["to_role"]:
        parts.append(f"误送，本来给{intended}")
    if e["type"] == "sms":
        if info.get("is_content_chaos"):
            parts.append(f"原文：{e['content']}")
        if info.get("is_signature_chaos"):
            parts.append(f"落款被换成{_sig_name(info.get('signature'))}")
        if info.get("is_torn"):
            parts.append(f"撕信，后半页在{info.get('torn_holder')}")
    if e["type"] == "gift" and info.get("isLost"):
        parts.append("礼物丢失")
    if info.get("source") == "web":
        parts.append("网页发送")
    return " · ".join(parts)

def _admin_log(sid, what):
    try:
        os.makedirs(os.path.dirname(MODERATION_LOG), exist_ok=True)
        with open(MODERATION_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(TZ_BEIJING).isoformat(timespec='seconds')}\tshow={sid}\tADMIN\t删除\t{what}\n")
    except OSError:
        pass

@app.route("/p/admin")
def admin_phone_index():
    who = _phone_admin_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid = who[0]
    db = get_db()
    rows = []
    for name in _admin_role_list(db, sid):
        n = db.execute("SELECT COUNT(*) FROM extra_events WHERE show_id=? AND type IN ('sms','gift') AND (from_role=? OR to_role=?)",
                       (sid, name, name)).fetchone()[0]
        rows.append({"name": name, "count": n})
    return render_template("phone.html", mode="admin_index", owner="管理员", sid=sid, roles=rows, csrf=_phone_csrf(),
                           phone_admin=True)

@app.route("/p/admin/as/<role>")
def admin_phone_inbox(role):
    who = _phone_admin_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid = who[0]
    db = get_db()
    return render_template("phone.html", mode="inbox", owner=role, sid=sid, admin_as=role, phone_admin=True,
                           threads=_phone_threads(db, sid, role), status={"can": False, "why": "", "sms": None, "gift": None},
                           public=None, moments_latest=None, revision="", csrf=_phone_csrf())

@app.route("/p/admin/as/<role>/<other>")
def admin_phone_thread(role, other):
    who = _phone_admin_current()
    if not who:
        return redirect(url_for("phone_code_entry"))
    sid = who[0]
    db = get_db()
    events = {e["id"]: e for e in _phone_events(db, sid)}
    msgs = _phone_msgs(db, sid, role, other)
    for m in msgs:
        e = events.get(m["id"])
        m["admin_note"] = _admin_note(e) if e else ""
        m["admin_del"] = _admin_del_key(m["id"])
    return render_template("phone.html", mode="thread", owner=role, sid=sid, other=other, admin_as=role, phone_admin=True,
                           msgs=msgs, status={"can": False, "why": "管理身份：只能查看和删除", "sms": None, "gift": None},
                           can_reply=False, revision="", csrf=_phone_csrf(), stickers=[], flash=None, draft="",
                           draft_kind="sms", draft_gift="", sent=False)

def _admin_del_key(view_id):
    """手机视图里的 id → 删除接口用的 (类型, 真实 id)：正数是 extra_events，≤-1000000 是点歌，其余负数是静默拉黑的网页短信"""
    if view_id > 0:
        return f"event:{view_id}"
    if view_id <= -1_000_000:
        return f"song:{-view_id - 1_000_000}"
    return f"silent:{-view_id}"

@app.route("/p/admin/delete", methods=["POST"])
def admin_phone_delete():
    who = _phone_admin_current()
    if not who:
        return jsonify(ok=False, msg="管理身份已失效"), 401
    token = request.headers.get("X-CSRF", "") or request.form.get("csrf", "")
    if not hmac.compare_digest(token, session.get("phone_csrf", "") or "-"):
        return _moment_json(False, "页面过期了，刷新后再试")
    sid = who[0]
    db = get_db()
    kind, _, raw_id = (request.form.get("target") or "").partition(":")
    if kind == "avatar":
        _avatar_remove(db, sid, raw_id)
        db.commit(); _admin_log(sid, f"头像 {raw_id}")
        return _moment_json(True, "已删除")
    try:
        tid_ = int(raw_id)
    except ValueError:
        return _moment_json(False, "不认识要删的东西")
    if kind == "event":
        row = db.execute("SELECT type, from_role, to_role, content FROM extra_events WHERE id=? AND show_id=? AND type IN ('sms','gift')",
                         (tid_, sid)).fetchone()
        if not row:
            return _moment_json(False, "已经不在了")
        db.execute("DELETE FROM extra_events WHERE id=?", (tid_,))
        what = f"{'短信' if row['type'] == 'sms' else '礼物'} {row['from_role']}→{row['to_role']}：{row['content']}"
    elif kind == "group":
        row = db.execute("SELECT from_role, content FROM phone_group_msgs WHERE id=? AND show_id=? AND deleted=0",
                         (tid_, sid)).fetchone()
        if not row:
            return _moment_json(False, "已经不在了")
        db.execute("UPDATE phone_group_msgs SET deleted=1 WHERE id=?", (tid_,))
        what = f"群消息 {row['from_role']}：{row['content']}"
    elif kind == "silent":
        if not db.execute("SELECT 1 FROM phone_silent WHERE id=? AND show_id=?", (tid_, sid)).fetchone():
            return _moment_json(False, "已经不在了")
        db.execute("DELETE FROM phone_silent WHERE id=?", (tid_,)); what = f"静默拉黑短信 #{tid_}"
    elif kind == "song":
        db.execute("UPDATE song_requests SET deleted=1 WHERE id=? AND show_id=?", (tid_, sid)); what = f"点歌 #{tid_}"
    elif kind == "moment":
        if not db.execute("SELECT 1 FROM moments WHERE id=? AND show_id=?", (tid_, sid)).fetchone():
            return _moment_json(False, "已经不在了")
        _moment_delete_images(db, "moment_id=?", (tid_,))
        db.execute("UPDATE moments SET deleted=1 WHERE id=?", (tid_,)); what = f"朋友圈 #{tid_}"
    elif kind == "comment":
        db.execute("UPDATE moment_comments SET deleted=1 WHERE id=? AND moment_id IN (SELECT id FROM moments WHERE show_id=?)",
                   (tid_, sid)); what = f"评论 #{tid_}"
    elif kind == "image":
        _moment_delete_images(db, "id=? AND show_id=?", (tid_, sid)); what = f"朋友圈图片 #{tid_}"
    else:
        return _moment_json(False, "不认识要删的东西")
    db.commit()
    _admin_log(sid, what)
    return _moment_json(True, "已删除")

# ── 后台：朋友圈管理（空间/额度/删帖删图） ──

def _moment_storage_warning():
    """后台页顶部的红字：团账号朋友圈图片空间用到 90% 以上时返回提示文字"""
    tid = current_tenant_id()
    if not tid:
        return None
    db = get_db()
    used, quota = _moment_tenant_used(db, tid), _moment_tenant_quota_bytes(db, tid)
    if quota and used >= quota * _MOMENT_WARN_RATIO:
        pct = min(100, int(used * 100 / quota))
        return (f"朋友圈图片空间已用 {pct}%（{used / 1048576:.0f}/{quota / 1048576:.0f} MB）"
                + ("，已经满了，玩家暂时不能发图" if used >= quota else "，快满了") + "。请到「朋友圈管理」删除旧季度的图片。")
    return None

@app.context_processor
def inject_moment_storage_warning():
    ep = request.endpoint or ""
    if ep.startswith("admin") and session.get("admin_logged_in"):
        try:
            return {"moment_storage_warning": _moment_storage_warning()}
        except Exception:
            return {}
    return {}

@app.route("/admin/moments", methods=["GET", "POST"])
@require_admin
def admin_moments():
    tid = current_tenant_id()
    sid = get_show_id()
    db  = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "quota" and sid:
            try:
                q = max(0, min(500, int(request.form.get("quota") or 0)))
            except ValueError:
                q = 0
            db.execute("INSERT INTO phone_settings (show_id, moment_quota) VALUES (?, ?) "
                       "ON CONFLICT(show_id) DO UPDATE SET moment_quota=excluded.moment_quota", (sid, q))
        elif action == "purge_show":
            target = request.form.get("show_id", type=int)
            if target and db.execute("SELECT 1 FROM shows WHERE id=? AND tenant_id=?", (target, tid)).fetchone():
                _moment_delete_images(db, "show_id=? AND tenant_id=?", (target, tid))
        elif action == "delete_post":
            mid = request.form.get("id", type=int)
            if db.execute("SELECT 1 FROM moments WHERE id=? AND tenant_id=?", (mid, tid)).fetchone():
                _moment_delete_images(db, "moment_id=?", (mid,))
                db.execute("UPDATE moments SET deleted=1 WHERE id=?", (mid,))
        elif action == "delete_image":
            _moment_delete_images(db, "id=? AND tenant_id=?", (request.form.get("id", type=int), tid))
        elif action == "delete_avatar":
            target = request.form.get("show_id", type=int)
            if db.execute("SELECT 1 FROM shows WHERE id=? AND tenant_id=?", (target, tid)).fetchone():
                _avatar_remove(db, target, request.form.get("role", ""))
        elif action == "delete_comment":
            cid = request.form.get("id", type=int)
            db.execute("""UPDATE moment_comments SET deleted=1 WHERE id=? AND moment_id IN
                          (SELECT id FROM moments WHERE tenant_id=?)""", (cid, tid))
        db.commit()
        return redirect(url_for("admin_moments"))
    used, quota = _moment_tenant_used(db, tid), _moment_tenant_quota_bytes(db, tid)
    per_show = [dict(r) for r in db.execute("""
        SELECT s.id, s.name, s.is_current, COUNT(i.id) AS n, COALESCE(SUM(i.size_bytes),0) AS bytes
        FROM shows s LEFT JOIN moment_images i ON i.show_id=s.id AND i.deleted_at=0
        WHERE s.tenant_id=? GROUP BY s.id ORDER BY s.id DESC""", (tid,))]
    posts, _ = _moment_feed(db, sid, None, limit=50) if sid else ([], False)
    avatars = [dict(r) for r in db.execute(
        "SELECT role_name, updated_at FROM phone_avatars WHERE show_id=? ORDER BY role_name", (sid,))] if sid else []
    return render_template("admin_moments.html", used=used, quota=quota, per_show=per_show, posts=posts,
                           avatars=avatars, sid=sid,
                           player_quota=_moment_player_quota(db, sid) if sid else _MOMENT_DEFAULT_QUOTA,
                           default_quota=_MOMENT_DEFAULT_QUOTA)

@app.route("/admin/moments/img/<int:image_id>")
@require_admin
def admin_moment_image(image_id):
    row = get_db().execute("SELECT * FROM moment_images WHERE id=? AND tenant_id=? AND deleted_at=0",
                           (image_id, current_tenant_id())).fetchone()
    if not row:
        abort(404)
    return send_file(os.path.join(MOMENT_IMAGE_DIR, row["thumb"] if request.args.get("s") == "thumb" else row["file"]),
                     mimetype="image/jpeg")

@app.route('/admin/phone_theme_preview')
@require_admin
def admin_phone_theme_preview():
    if not get_db().execute('SELECT id FROM shows WHERE id=? AND tenant_id=?',(get_show_id(),current_tenant_id())).fetchone(): abort(404)
    visual, copy = request.args.get('visual', 'modern'), request.args.get('copy', 'modern')
    if visual not in PHONE_THEMES or copy not in PHONE_COPY: abort(400)
    config = {'visual':visual, 'copy':copy, 'words':{key:request.args.get('word_'+key,'')[:100] for key in PHONE_COPY['modern']}}
    return render_template('phone.html', mode='inbox', sid=get_show_id(), owner='主题预览', threads=[],
                           status={'can':False}, public=None, phone_skin_override=config, revision='')


@app.route("/admin/phone_codes", methods=["GET", "POST"])
@require_admin
def admin_phone_codes():
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()
    if not sid:
        return render_template("admin_phone_codes.html", rows=[], show=None)
    # 名单 = 存档站见过的角色（参与过场次/收发过短信礼物）+ 管理员手动加过码的角色。
    # 插件不会主动推送角色名单，开季前 players 表是空的，所以要允许手动加。
    roles = {r["role_name"]: bool(r["is_npc"]) for r in db.execute(
        "SELECT role_name, MAX(is_npc) AS is_npc FROM players WHERE show_id=? AND role_name!='' GROUP BY role_name", (sid,)
    ).fetchall()}
    for r in db.execute("SELECT role_name FROM phone_codes WHERE show_id=?", (sid,)):
        roles.setdefault(r["role_name"], False)
    sync = _phone_sync_row(db, sid)
    for r in ((sync["snap"].get("roster") or []) if sync else []):  # 插件上报的角色名单（新版插件才有）
        if r.get("name"):
            roles[r["name"]] = roles.get(r["name"], False) or bool(r.get("npc"))
    if request.method == "POST":
        action = request.form.get("action")
        now = int(time.time() * 1000)
        if action == "phone_theme":
            if not db.execute('SELECT id FROM shows WHERE id=? AND tenant_id=?',(sid,tid)).fetchone(): abort(404)
            if not hmac.compare_digest(request.form.get('theme_csrf',''), session.get('theme_csrf') or '-'): abort(403)
            visual, copy = request.form.get('visual'), request.form.get('copy')
            if visual not in PHONE_THEMES or copy not in PHONE_COPY: abort(400)
            words = {key: request.form.get('word_'+key, '').strip()[:100] for key in PHONE_COPY['modern']}
            config = json.dumps({'visual':visual, 'copy':copy, 'words':words}, ensure_ascii=False)
            db.execute("INSERT INTO phone_settings (show_id, theme_config) VALUES (?,?) ON CONFLICT(show_id) DO UPDATE SET theme_config=excluded.theme_config", (sid, config))
        elif action == "web_send":
            if request.form.get("on") == "1" and not sync:
                return "机器人还没有同步本季规则，暂时不能打开网页发送", 409
            db.execute("INSERT INTO phone_settings (show_id, web_send) VALUES (?, ?) "
                       "ON CONFLICT(show_id) DO UPDATE SET web_send=excluded.web_send",
                       (sid, 1 if request.form.get("on") == "1" else 0))
        elif action == "comm_pause":
            db.execute("INSERT INTO phone_settings (show_id, web_send, comm_paused) VALUES (?, 0, ?) "
                       "ON CONFLICT(show_id) DO UPDATE SET comm_paused=excluded.comm_paused",
                       (sid, 1 if request.form.get("on") == "1" else 0))
        elif action == "admin_code":
            db.execute("DELETE FROM phone_admin_codes WHERE show_id=?", (sid,))  # 生成/重置：旧码立即作废
            db.execute("INSERT INTO phone_admin_codes (show_id, tenant_id, code, created_at) VALUES (?,?,?,?)",
                       (sid, tid, _new_phone_code(db), now))
        elif action == "song_daily":
            try:
                n = max(0, min(50, int(request.form.get("n") or 0)))
            except ValueError:
                n = 0
            db.execute("INSERT INTO phone_settings (show_id, song_daily) VALUES (?, ?) "
                       "ON CONFLICT(show_id) DO UPDATE SET song_daily=excluded.song_daily", (sid, n))
        elif action == "delete_song":
            db.execute("UPDATE song_requests SET deleted=1 WHERE id=? AND show_id=?", (request.form.get("id", type=int), sid))
        elif action == "stickers":
            text = "\n".join(_phone_parse_stickers(request.form.get("stickers", "")))
            db.execute("INSERT INTO phone_settings (show_id, stickers) VALUES (?, ?) "
                       "ON CONFLICT(show_id) DO UPDATE SET stickers=excluded.stickers", (sid, text))
        elif action == "add_roles":
            # 一行一个（也接受逗号/顿号/空格分隔），名字要跟群里「创建新角色」时的本名一字不差
            names = {n.strip() for n in re.split(r"[\n,，、\s]+", request.form.get("names", "")) if n.strip()}
            have = {r["role_name"] for r in db.execute("SELECT role_name FROM phone_codes WHERE show_id=?", (sid,))}
            for role in sorted(names - have):
                if len(role) <= 30:
                    db.execute("INSERT INTO phone_codes (tenant_id, show_id, role_name, code, created_at) VALUES (?,?,?,?,?)",
                               (tid, sid, role, _new_phone_code(db), now))
        elif action == "delete":
            # 手动加错名字时用；删掉码后，存档站没见过的角色会从列表里消失
            db.execute("DELETE FROM phone_codes WHERE show_id=? AND role_name=?", (sid, request.form.get("role", "")))
        elif action == "generate_all":
            have = {r["role_name"] for r in db.execute("SELECT role_name FROM phone_codes WHERE show_id=?", (sid,))}
            for role in roles:
                if role not in have:
                    db.execute("INSERT INTO phone_codes (tenant_id, show_id, role_name, code, created_at) VALUES (?,?,?,?,?)",
                               (tid, sid, role, _new_phone_code(db), now))
        elif action == "reset":
            role = request.form.get("role", "")
            if role in roles:
                # 重置 = 旧码立刻作废，发出去的旧链接也打不开了（码泄露时用）
                db.execute("DELETE FROM phone_codes WHERE show_id=? AND role_name=?", (sid, role))
                db.execute("INSERT INTO phone_codes (tenant_id, show_id, role_name, code, created_at) VALUES (?,?,?,?,?)",
                           (tid, sid, role, _new_phone_code(db), now))
        db.commit()
        return redirect(url_for("admin_phone_codes"))
    codes = {r["role_name"]: r["code"] for r in db.execute(
        "SELECT role_name, code FROM phone_codes WHERE show_id=?", (sid,))}
    rows = [{"role": r, "is_npc": roles[r], "code": codes.get(r)}
            for r in sorted(roles, key=lambda r: (roles[r], r))]
    show = db.execute("SELECT * FROM shows WHERE id=?", (sid,)).fetchone()
    sync_ago = None
    if sync and sync["synced_at"]:
        sync_ago = max(0, int(time.time() * 1000) - sync["synced_at"]) // 60000
    session.setdefault("theme_csrf", secrets.token_urlsafe(24))
    return render_template("admin_phone_codes.html", rows=rows, show=show,
                           theme_settings=phone_theme(sid), base_url=_phone_base_url(),
                           web_send=_phone_web_send_on(db, sid), comm_paused=_phone_comm_paused(db, sid), sync_ago=sync_ago, has_sync=bool(sync),
                           song_daily=_song_daily_cap(db, sid), song_default=_SONG_DEFAULT_DAILY,
                           admin_code=(db.execute("SELECT code FROM phone_admin_codes WHERE show_id=?", (sid,)).fetchone() or {"code": None})["code"],
                           songs=[dict(r, time=ts_to_str(r["created_at"])) for r in db.execute(
                               "SELECT * FROM song_requests WHERE show_id=? AND deleted=0 ORDER BY id DESC LIMIT 50", (sid,))],
                           stickers_custom="\n".join(_phone_parse_stickers((db.execute(
                               "SELECT stickers FROM phone_settings WHERE show_id=?", (sid,)).fetchone() or {"stickers": ""})["stickers"])),
                           stickers_default="\n".join(_PHONE_DEFAULT_STICKERS),
                           sync_fresh=bool(sync) and sync_ago is not None and sync_ago < 10,
                           zone=_schedule_zone(dict(show)))

@app.route("/search")
@require_login
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return redirect(url_for("home"))
    sid = get_show_id()
    db  = get_db()
    q_lower = q.lower()

    # 收集所有 distinct role_name（来自 sessions 的 participants 字段）
    rows = db.execute("SELECT DISTINCT participants FROM sessions WHERE show_id=?", (sid,)).fetchall()
    all_roles = set()
    for r in rows:
        try:
            parts = json.loads(r["participants"] or "[]")
            all_roles.update(parts)
        except Exception:
            pass

    # 同时收集 players 表中的角色
    player_rows = db.execute("SELECT role_name FROM players WHERE show_id=?", (sid,)).fetchall()
    for r in player_rows:
        if r["role_name"]:
            all_roles.add(r["role_name"])

    # 收集 extra_events 中的发送/接收角色（只有短信记录但无场次的角色也能被搜到）
    event_rows = db.execute(
        "SELECT DISTINCT from_role, to_role FROM extra_events WHERE show_id=?", (sid,)
    ).fetchall()
    for r in event_rows:
        if r["from_role"]: all_roles.add(r["from_role"])
        if r["to_role"]:   all_roles.add(r["to_role"])

    show_names = get_show_names(db, sid)
    # show_name → role_name 反查表（小写）
    show_to_role = {v.lower(): k for k, v in show_names.items()}

    matched = set()
    for role in all_roles:
        if q_lower in role.lower():
            matched.add(role)
        sn = show_names.get(role, "")
        if sn and q_lower in sn.lower():
            matched.add(role)
    # 也从 show_name 反查中匹配
    for sn_lower, role in show_to_role.items():
        if q_lower in sn_lower and role in all_roles:
            matched.add(role)

    matched = sorted(matched)

    if len(matched) == 1:
        return redirect(url_for("character_view", role_name=matched[0]))
    if len(matched) == 0:
        # 无结果也给个页面而不是空角色页
        return render_template("search_results.html", q=q, results=[], show_names=show_names)
    return render_template("search_results.html", q=q, results=matched, show_names=show_names)


# ── 公开视图路由 ─────────────────────────────────────────────────────────────

def _get_public_show(token):
    row = get_db().execute(
        "SELECT * FROM shows WHERE public_token=? AND public_view_enabled=1", (token,)
    ).fetchone()
    return dict(row) if row else None

@app.route("/view/<token>")
def public_home(token):
    show = _get_public_show(token)
    if not show: abort(404)
    db   = get_db()
    rows = db.execute("""
        SELECT game_day, COUNT(*) AS session_count,
               SUM(total_replies) AS total_replies, SUM(total_words) AS total_words,
               MIN(start_ts) AS first_ts
        FROM sessions WHERE show_id=?
        GROUP BY game_day ORDER BY first_ts DESC
    """, (show["id"],)).fetchall()
    # event counts per game_day
    ev_rows = db.execute("""
        SELECT game_day,
               SUM(CASE WHEN type='sms'      THEN 1 ELSE 0 END) AS sms_count,
               SUM(CASE WHEN type='gift'     THEN 1 ELSE 0 END) AS gift_count,
               SUM(CASE WHEN type='lovemail' THEN 1 ELSE 0 END) AS lovemail_count
        FROM extra_events WHERE show_id=? AND type IN ('sms','gift','lovemail')
        GROUP BY game_day
    """, (show["id"],)).fetchall()
    ev_by_day = {r["game_day"]: dict(r) for r in ev_rows}
    days = []
    for r in rows:
        d = dict(r)
        d["first_date"] = ts_to_str(d["first_ts"])
        if d["game_day"].strip():
            ev = ev_by_day.get(d["game_day"], {})
            d["sms_count"]      = ev.get("sms_count", 0) or 0
            d["gift_count"]     = ev.get("gift_count", 0) or 0
            d["lovemail_count"] = ev.get("lovemail_count", 0) or 0
            days.append(d)
    return render_template("public_home.html", show=show, days=days, token=token)

@app.route("/view/<token>/date/<game_day>")
def public_date(token, game_day):
    show = _get_public_show(token)
    if not show: abort(404)
    db   = get_db()
    flat = get_flat_config(db, show["id"])
    _true = ("true", "1", "True")
    show_sms      = flat.get("public_show_sms",      "true") in _true
    show_gift     = flat.get("public_show_gift",     "true") in _true
    show_lovemail = flat.get("public_show_lovemail", "true") in _true
    show_letter   = flat.get("public_show_letter",   "false") in _true
    allowed = [t for t, ok in [("sms", show_sms), ("gift", show_gift), ("lovemail", show_lovemail), ("direct_letter", show_letter)] if ok]
    rows = db.execute(
        "SELECT * FROM sessions WHERE show_id=? AND game_day=? ORDER BY start_ts DESC", (show["id"], game_day)
    ).fetchall()
    day_events = []
    if allowed:
        ph = ",".join("?" * len(allowed))
        ev_rows = db.execute(
            f"SELECT * FROM extra_events WHERE show_id=? AND game_day=? AND type IN ({ph}) ORDER BY timestamp ASC",
            [show["id"], game_day] + allowed
        ).fetchall()
        day_events = _parse_events(ev_rows)
    show_names = get_show_names(db, show["id"])
    return render_template("public_date.html", show=show, token=token,
                           day_events=day_events,
                           game_day=game_day, sessions=_enrich_sessions(rows, _get_rest_pair(db, show["id"])), show_names=show_names,
                           show_letter=show_letter, ts_to_str=ts_to_str)

@app.route("/view/<token>/session/<path:session_id>")
def public_session_view(token, session_id):
    show = _get_public_show(token)
    if not show: abort(404)
    db   = get_db()
    sess = db.execute("SELECT * FROM sessions WHERE id=? AND show_id=?", (session_id, show["id"])).fetchone()
    if not sess: abort(404)
    flat       = get_flat_config(db, show["id"])
    sess       = _enrich_session(dict(sess), _parse_rest_hours(flat.get("rest_hours", "")))
    rp         = db.execute("SELECT * FROM rp_entries WHERE session_id=? AND show_id=? ORDER BY seq,timestamp", (session_id, show["id"])).fetchall()
    _true      = ("true", "1", "True")
    show_sms      = flat.get("public_show_sms",      "true") in _true
    show_gift     = flat.get("public_show_gift",     "true") in _true
    show_lovemail = flat.get("public_show_lovemail", "true") in _true
    show_letter   = flat.get("public_show_letter",   "false") in _true
    allowed   = {t for t, ok in [("sms", show_sms), ("gift", show_gift), ("lovemail", show_lovemail), ("direct_letter", show_letter)] if ok}
    all_events = _parse_events(db.execute("SELECT * FROM extra_events WHERE session_id=? AND show_id=? ORDER BY timestamp", (session_id, show["id"])).fetchall())
    events     = [e for e in all_events if e["type"] in allowed]
    show_names = get_show_names(db, show["id"])
    return render_template("public_session.html", show=show, token=token,
                           sess=sess, rp=rp, events=events, show_names=show_names, ts_to_str=ts_to_str,
                           show_letter=show_letter)

@app.route("/view/<token>/events")
def public_events(token):
    show = _get_public_show(token)
    if not show: abort(404)
    db   = get_db()
    flat = get_flat_config(db, show["id"])
    _true = ("true", "1", "True")
    show_sms      = flat.get("public_show_sms",      "true") in _true
    show_gift     = flat.get("public_show_gift",     "true") in _true
    show_lovemail = flat.get("public_show_lovemail", "true") in _true
    show_letter   = flat.get("public_show_letter",   "false") in _true
    allowed = [t for t, ok in [("sms", show_sms), ("gift", show_gift), ("lovemail", show_lovemail), ("direct_letter", show_letter)] if ok]
    if not allowed:
        events = []
    else:
        ph = ",".join("?" * len(allowed))
        rows = db.execute(
            f"SELECT * FROM extra_events WHERE show_id=? AND type IN ({ph}) ORDER BY timestamp DESC",
            [show["id"]] + allowed
        ).fetchall()
        events = _parse_events(rows)
    counts = {
        "sms":           sum(1 for e in events if e["type"] == "sms"),
        "gift":          sum(1 for e in events if e["type"] == "gift"),
        "lovemail":      sum(1 for e in events if e["type"] == "lovemail"),
        "direct_letter": sum(1 for e in events if e["type"] == "direct_letter"),
    }
    return render_template("public_events.html", show=show, token=token,
                           events=events, counts=counts, ts_to_str=ts_to_str,
                           show_sms=show_sms, show_gift=show_gift, show_lovemail=show_lovemail,
                           show_letter=show_letter)


@app.route("/view/<token>/character/<role_name>")
def public_character(token, role_name):
    show = _get_public_show(token)
    if not show: abort(404)
    db   = get_db()
    rows = db.execute("SELECT * FROM sessions WHERE show_id=? ORDER BY start_ts DESC", (show["id"],)).fetchall()
    show_names = get_show_names(db, show["id"])
    sessions_list = [s for s in _enrich_sessions(rows, _get_rest_pair(db, show["id"])) if role_name in s["participants"]]
    return render_template("public_character.html", show=show, token=token,
                           role_name=role_name, sessions=sessions_list, show_names=show_names)


# ── API 路由 ─────────────────────────────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
def api_config():
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    flat = get_flat_config(get_db(), show_id)
    return jsonify(assemble_bot_config(flat))

@app.route("/api/sync_config", methods=["POST"])
def api_sync_config():
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    data = request.json or {}
    if not data:
        return jsonify({"ok": False, "error": "empty payload"}), 400
    _SYNC_SKIP_KEYS = {"global_days", "auto_day_reset_enabled"}
    db = get_db()
    for key, value in data.items():
        if key in _SYNC_SKIP_KEYS:
            continue
        db.execute(
            "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
            "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
            (show_id, tid, key, _strip_json_str(value))
        )
    db.execute(
        "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
        "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
        (show_id, tid, "_last_bot_sync", str(int(time.time() * 1000)))
    )
    db.commit()
    return jsonify({"ok": True, "synced": len(data)})

@app.route("/api/pending_items", methods=["GET", "DELETE"])
def api_pending_items():
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    db  = get_db()
    if request.method == "DELETE":
        db.execute(
            "UPDATE site_config SET value='[]' WHERE show_id=? AND key='item_registry_pending'",
            (show_id,)
        )
        db.commit()
        return jsonify({"ok": True})
    row = db.execute(
        "SELECT value FROM site_config WHERE show_id=? AND key='item_registry_pending'",
        (show_id,)
    ).fetchone()
    pending = []
    if row and row["value"]:
        try:
            pending = json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            pending = []
    return jsonify({"pending": pending})

@app.route("/api/pending_equips", methods=["GET", "DELETE"])
def api_pending_equips():
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    db  = get_db()
    if request.method == "DELETE":
        db.execute(
            "UPDATE site_config SET value='[]' WHERE show_id=? AND key='equipment_registry_pending'",
            (show_id,)
        )
        db.commit()
        return jsonify({"ok": True})
    row = db.execute(
        "SELECT value FROM site_config WHERE show_id=? AND key='equipment_registry_pending'",
        (show_id,)
    ).fetchone()
    pending = []
    if row and row["value"]:
        try:
            pending = json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            pending = []
    return jsonify({"pending": pending})

@app.route("/api/collect_image", methods=["POST"])
def api_collect_image():
    """插件「我提交」里带的 QQ 临时图片链接，由 rp_archive 下载后落地为永久 URL。
    按 (tenant, show, uid) 记额度，结束季度时随图片文件一起清空，服务器盘不会无限增长。"""
    tid  = get_tenant_from_token()
    show = get_current_show_for_tenant(tid)
    if not show:
        return jsonify({"ok": False, "error": "no active season"}), 404
    show_id = show["id"]

    data      = request.json or {}
    image_url = (data.get("image_url") or "").strip()
    uid       = str(data.get("uid") or "").strip()
    if not image_url or not uid:
        return jsonify({"ok": False, "error": "missing image_url or uid"}), 400

    parsed = urlparse(image_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return jsonify({"ok": False, "error": "invalid url"}), 400
    if not _is_url_host_public(parsed.hostname):
        return jsonify({"ok": False, "error": "url not allowed"}), 400

    db   = get_db()
    used = db.execute(
        "SELECT COALESCE(SUM(size_bytes),0) AS total FROM collected_images WHERE tenant_id=? AND show_id=? AND uid=?",
        (tid, show_id, uid)
    ).fetchone()["total"]
    if used >= COLLECT_IMAGE_USER_QUOTA_BYTES:
        return jsonify({"ok": False, "error": "quota exceeded"}), 413

    cap = min(COLLECT_IMAGE_MAX_BYTES, COLLECT_IMAGE_USER_QUOTA_BYTES - used)
    try:
        req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if not content_type.startswith("image/"):
                return jsonify({"ok": False, "error": "not an image"}), 400
            buf = resp.read(cap + 1)
    except Exception as e:
        _logger.error("collect_image 下载失败: %s", e)
        return jsonify({"ok": False, "error": "download failed"}), 502

    if len(buf) > cap:
        return jsonify({"ok": False, "error": "image too large or quota exceeded"}), 413

    ext_name = "png" if "png" in content_type else "gif" if "gif" in content_type else "jpg"
    filename = f"{secrets.token_hex(8)}.{ext_name}"
    save_dir = os.path.join(COLLECT_IMAGE_DIR, str(tid), str(show_id), uid)
    os.makedirs(save_dir, exist_ok=True)
    with open(os.path.join(save_dir, filename), "wb") as f:
        f.write(buf)

    db.execute(
        "INSERT INTO collected_images (tenant_id, show_id, uid, filename, size_bytes, created_at) VALUES (?,?,?,?,?,?)",
        (tid, show_id, uid, filename, len(buf), int(time.time() * 1000))
    )
    db.commit()

    base_url = request.host_url.rstrip("/")
    return jsonify({"ok": True, "url": f"{base_url}/static/collected_images/{tid}/{show_id}/{uid}/{filename}"})

@app.route("/api/collect_image/delete", methods=["POST"])
def api_delete_collect_image():
    """插件「删除上传」/「我清空」时调用，把 collect_image 转存出来的文件和配额记录一起删掉，
    否则本地记录删了、服务器上的图片和配额占用还留着（配额要等季度结束才会被批量清）。"""
    tid  = get_tenant_from_token()
    data = request.json or {}
    image_url = (data.get("url") or "").strip()
    if not image_url:
        return jsonify({"ok": False, "error": "missing url"}), 400

    m = re.search(r"/static/collected_images/(\d+)/(\d+)/([^/]+)/([^/]+)$", image_url)
    if not m:
        return jsonify({"ok": False, "error": "invalid url"}), 400
    url_tid, show_id, uid, filename = m.group(1), m.group(2), m.group(3), m.group(4)
    if str(url_tid) != str(tid):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    db  = get_db()
    row = db.execute(
        "SELECT id FROM collected_images WHERE tenant_id=? AND show_id=? AND uid=? AND filename=?",
        (tid, show_id, uid, filename)
    ).fetchone()
    if not row:
        return jsonify({"ok": True, "already_gone": True})

    try:
        os.remove(os.path.join(COLLECT_IMAGE_DIR, str(tid), str(show_id), uid, filename))
    except OSError:
        pass
    db.execute("DELETE FROM collected_images WHERE id=?", (row["id"],))
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/event", methods=["POST"])
def api_event():
    tid  = get_tenant_from_token()
    show = get_current_show_for_tenant(tid)
    if not show: abort(503)
    show_id = show["id"]
    data       = request.json or {}
    event_type = data.get("type", "")
    if event_type not in ("lovemail", "sms", "gift", "direct_letter"):
        return jsonify({"ok": False, "error": "invalid type"}), 400

    # 档期门控：仅主档期内的互动事件才写入
    zone = _schedule_zone(show, data.get("timestamp"))
    if zone != 'main':
        return jsonify({"ok": True, "skipped": zone})
    db        = get_db()
    from_role = data.get("from_role","").strip()
    from_qq   = str(data.get("from_qq","")).strip()
    to_role   = data.get("to_role","").strip()
    to_qq     = str(data.get("to_qq","")).strip()
    now       = int(time.time() * 1000)
    extra_info = data.get("extra_info",{})
    # 自定义名字：归属到真实角色，但在 extra_info 中保留显示用名
    from_custom = data.get("from_custom_name","").strip()
    to_custom   = data.get("to_custom_name","").strip()
    if from_custom and from_custom != from_role:
        extra_info["from_custom_name"] = from_custom
    if to_custom and to_custom != to_role:
        extra_info["to_custom_name"] = to_custom
    db.execute("""
        INSERT INTO extra_events
          (show_id,tenant_id,session_id,type,from_role,to_role,content,extra_info,timestamp,game_day)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (show_id, tid, data.get("session_id") or "", event_type,
          from_role, to_role, data.get("content",""),
          json.dumps(extra_info, ensure_ascii=False),
          data.get("timestamp",0), data.get("game_day","")))

    def _upsert_event_player(role, qq):
        if not role:
            return
        effective_qq = qq if qq and qq != role else role  # 有真实QQ用真实QQ，否则placeholder
        existing = db.execute(
            "SELECT qq FROM players WHERE show_id=? AND role_name=?", (show_id, role)
        ).fetchone()
        if existing:
            # 如果现有记录是placeholder且现在有真实QQ，升级
            if existing["qq"] == role and effective_qq != role:
                db.execute(
                    "UPDATE players SET qq=?, last_updated=? WHERE show_id=? AND role_name=?",
                    (effective_qq, now, show_id, role)
                )
            else:
                db.execute("UPDATE players SET last_updated=? WHERE show_id=? AND role_name=?",
                           (now, show_id, role))
        else:
            db.execute("""
                INSERT OR IGNORE INTO players
                  (show_id,tenant_id,qq,role_name,sessions_count,total_replies,total_words,last_updated)
                VALUES (?,?,?,?,0,0,0,?)
            """, (show_id, tid, effective_qq, role, now))

    # 短信/礼物/写信综：发送方和收件方都注册；心动信不计入活跃
    if event_type in ("sms", "gift", "direct_letter"):
        _upsert_event_player(from_role, from_qq)
        _upsert_event_player(to_role, to_qq)
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/event/delete_by_match", methods=["POST"])
def api_event_delete_by_match():
    """发错撤回：玩家引用自己发错人的短信/礼物发「撤回」时，机器人按投递时写入的
    (type, from_role, to_role, timestamp) 精确删掉那条 extra_events，避免季末公开存档里还能看到。
    timestamp 是机器人上报 /api/event 时自己带的毫秒时间戳，同一人同一毫秒不会有两条。"""
    tid  = get_tenant_from_token()
    show = get_current_show_for_tenant(tid)
    if not show: abort(503)
    data = request.json or {}
    event_type = data.get("type", "")
    if event_type not in ("sms", "gift"):
        return jsonify({"ok": False, "error": "invalid type"}), 400
    db = get_db()
    cur = db.execute(
        "DELETE FROM extra_events WHERE show_id=? AND tenant_id=? AND type=? AND from_role=? AND to_role=? AND timestamp=?",
        (show["id"], tid, event_type, (data.get("from_role") or "").strip(),
         (data.get("to_role") or "").strip(), data.get("timestamp") or 0)
    )
    db.commit()
    return jsonify({"ok": True, "deleted": cur.rowcount})

# ── 长日将尽许愿墙：独立公开功能，不走 tenant/api_token 鉴权 ─────────────────
WISH_RATE_LIMIT_WINDOW_MS = 10 * 60 * 1000   # 10 分钟
WISH_RATE_LIMIT_MAX       = 3                # 同一 IP 窗口内最多提交 3 条
WISH_CONTENT_MAX_LEN      = 300
WISH_AUTHOR_MAX_LEN       = 30
WISH_NOTE_MAX_LEN         = 200

def _hash_ip(ip):
    return hashlib.sha256((ip or "").encode("utf-8")).hexdigest()[:16]

def _check_wish_admin_password(data):
    db  = get_db()
    row = db.execute(
        "SELECT value FROM changri_wish_config WHERE key='admin_password_hash'"
    ).fetchone()
    if not row:
        return False
    return check_password_hash(row["value"], (data.get("password") or ""))

@app.route("/api/changri_wishes", methods=["GET"])
def changri_wishes_list():
    db = get_db()
    status = request.args.get("status")
    if status in ("pending", "implemented"):
        rows = db.execute(
            "SELECT * FROM changri_wishes WHERE status=? ORDER BY created_at DESC", (status,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM changri_wishes ORDER BY created_at DESC").fetchall()
    return jsonify({"ok": True, "wishes": [dict(r) for r in rows]})

@app.route("/api/changri_wishes", methods=["POST"])
def changri_wishes_create():
    data    = request.json or {}
    content = (data.get("content") or "").strip()
    author  = (data.get("author_name") or "").strip()[:WISH_AUTHOR_MAX_LEN]
    if not content:
        return jsonify({"ok": False, "error": "许愿内容不能为空"}), 400
    if len(content) > WISH_CONTENT_MAX_LEN:
        return jsonify({"ok": False, "error": f"内容太长（最多 {WISH_CONTENT_MAX_LEN} 字）"}), 400

    db      = get_db()
    now     = int(time.time() * 1000)
    ip_hash = _hash_ip(request.remote_addr)
    recent  = db.execute(
        "SELECT COUNT(*) c FROM changri_wishes WHERE ip_hash=? AND created_at>=?",
        (ip_hash, now - WISH_RATE_LIMIT_WINDOW_MS)
    ).fetchone()["c"]
    if recent >= WISH_RATE_LIMIT_MAX:
        return jsonify({"ok": False, "error": "提交太频繁，过一会再试试吧"}), 429

    db.execute(
        "INSERT INTO changri_wishes (content, author_name, status, ip_hash, created_at) VALUES (?,?,?,?,?)",
        (content, author, "pending", ip_hash, now)
    )
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/changri_wishes/<int:wish_id>/implement", methods=["POST"])
def changri_wishes_implement(wish_id):
    data = request.json or {}
    if not _check_wish_admin_password(data):
        return jsonify({"ok": False, "error": "密码错误"}), 403
    db   = get_db()
    now  = int(time.time() * 1000)
    note = (data.get("admin_note") or "").strip()[:WISH_NOTE_MAX_LEN]
    db.execute(
        "UPDATE changri_wishes SET status='implemented', implemented_at=?, admin_note=? WHERE id=?",
        (now, note, wish_id)
    )
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/changri_wishes/<int:wish_id>/unimplement", methods=["POST"])
def changri_wishes_unimplement(wish_id):
    data = request.json or {}
    if not _check_wish_admin_password(data):
        return jsonify({"ok": False, "error": "密码错误"}), 403
    db = get_db()
    db.execute("UPDATE changri_wishes SET status='pending', implemented_at=NULL WHERE id=?", (wish_id,))
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/changri_wishes/<int:wish_id>", methods=["DELETE"])
def changri_wishes_delete(wish_id):
    data = request.json or {}
    if not _check_wish_admin_password(data):
        return jsonify({"ok": False, "error": "密码错误"}), 403
    db = get_db()
    db.execute("DELETE FROM changri_wishes WHERE id=?", (wish_id,))
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/changri_wishes/change_password", methods=["POST"])
def changri_wishes_change_password():
    data = request.json or {}
    if not _check_wish_admin_password(data):
        return jsonify({"ok": False, "error": "密码错误"}), 403
    new_pw = (data.get("new_password") or "").strip()
    if len(new_pw) < 6:
        return jsonify({"ok": False, "error": "新密码至少 6 位"}), 400
    db = get_db()
    db.execute(
        "UPDATE changri_wish_config SET value=? WHERE key='admin_password_hash'",
        (generate_password_hash(new_pw),)
    )
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/rp", methods=["POST"])
def api_rp():
    tid  = get_tenant_from_token()
    show = get_current_show_for_tenant(tid)
    if not show: abort(503)
    show_id = show["id"]
    data = request.json or {}
    sid  = data.get("session_id","")
    if not sid:
        return jsonify({"ok": False, "error": "missing session_id"}), 400
    # 与 /api/session_stats、/api/session_end 保持一致：档期开始前不记录，
    # 否则 entry 单边累加 total_words/total_replies，而 stats 覆盖被 skip，数字永远是错的
    zone = _schedule_zone(show, data.get("timestamp"))
    if zone == 'pre':
        return jsonify({"ok": True, "skipped": "pre_schedule"})
    db = get_db()
    if not db.execute("SELECT id FROM sessions WHERE id=? AND show_id=?", (sid, show_id)).fetchone():
        db.execute("""
            INSERT OR IGNORE INTO sessions
              (id,show_id,tenant_id,group_id,platform,game_day,game_time,place,subtype,
               participants,start_ts,end_ts,forced,total_replies,total_words,stats)
            VALUES (?,?,?,?,?,?,?,?,?,'[]',?,0,0,0,0,'{}')
        """, (sid, show_id, tid,
              data.get("group_id",""),
              data.get("platform",""),
              data.get("game_day","") or "",
              data.get("game_time",""),
              data.get("place",""),
              data.get("subtype",""),
              data.get("timestamp",0)))
    max_seq = db.execute(
        "SELECT COALESCE(MAX(seq),0) FROM rp_entries WHERE session_id=? AND show_id=?", (sid, show_id)
    ).fetchone()[0]
    # 计算 reply_time_ms：距同 session 内上一条不同角色的 entry
    cur_ts    = data.get("timestamp", 0)
    role_name_rp = data.get("role_name", "")
    reply_time_ms = None
    if cur_ts and role_name_rp:
        prev_other = db.execute(
            "SELECT timestamp FROM rp_entries WHERE session_id=? AND show_id=? AND role_name!=? AND timestamp>0 ORDER BY seq DESC LIMIT 1",
            (sid, show_id, role_name_rp)
        ).fetchone()
        if prev_other:
            diff = cur_ts - prev_other["timestamp"]
            if 0 < diff < 7_200_000:
                reply_time_ms = diff
    db.execute("""
        INSERT INTO rp_entries (show_id,tenant_id,session_id,role_name,content,seq,timestamp,reply_time_ms)
        VALUES (?,?,?,?,?,?,?,?)
    """, (show_id, tid, sid, role_name_rp, data.get("content",""),
          max_seq+1, cur_ts, reply_time_ms))
    db.execute(
        "UPDATE sessions SET total_replies=total_replies+1, total_words=total_words+? WHERE id=? AND show_id=?",
        (len(data.get("content","")), sid, show_id)
    )

    # 计算本次回复时间（距上一条不同角色的 entry）并累计到 players
    role_name = data.get("role_name", "")
    cur_ts    = data.get("timestamp", 0)
    is_npc    = bool(data.get("is_npc", False))
    # 若 is_npc，标记 players 表
    if role_name and is_npc:
        db.execute(
            "UPDATE players SET is_npc=1 WHERE show_id=? AND role_name=?",
            (show_id, role_name)
        )
    # 补戏期/超期（过了档期结束日、季度还没手动结束）：只留 rp_entries/session 场次记录，不计入弧长
    if role_name and cur_ts and not is_npc and zone == 'main':
        prev = db.execute(
            "SELECT timestamp FROM rp_entries WHERE session_id=? AND show_id=? AND role_name!=? AND timestamp>0 ORDER BY seq DESC LIMIT 1",
            (sid, show_id, role_name)
        ).fetchone()
        if prev:
            diff_ms = cur_ts - prev["timestamp"]
            if 0 < diff_ms < 7_200_000:  # 0~2小时内视为有效
                db.execute("""
                    UPDATE players
                    SET reply_time_sum=reply_time_sum+?, reply_time_count=reply_time_count+1
                    WHERE show_id=? AND role_name=?
                """, (diff_ms, show_id, role_name))

    db.commit()
    return jsonify({"ok": True})

@app.route("/api/rp/delete_by_content", methods=["POST"])
def api_rp_delete_by_content():
    """引用+撤回联动：机器人侧没有存「QQ消息ID→复盘条目ID」的映射，只能反查被撤回消息的原文，
    按 (session_id, role_name, content) 匹配删除。同名同内容在该场次出现不止一条时（比如同一人发过
    两条一模一样的短回复），靠 orig_timestamp（被撤回消息的原始发送时间，机器人侧从 get_msg 拿）
    挑 rp_entries.timestamp 离它最近的那条，而不是无脑删最新一条，避免删错。
    不回退 sessions 的 total_replies/total_words，与后台手动删除 rp_delete 保持同一口径（那边也不回退）。"""
    tid  = get_tenant_from_token()
    show = get_current_show_for_tenant(tid)
    if not show: abort(503)
    show_id = show["id"]
    data = request.json or {}
    sid       = data.get("session_id", "")
    role_name = data.get("role_name", "")
    content   = data.get("content", "")
    orig_ts   = data.get("orig_timestamp")
    if not sid or not role_name or not content:
        return jsonify({"ok": False, "error": "missing session_id/role_name/content"}), 400
    db = get_db()
    rows = db.execute(
        "SELECT id, timestamp FROM rp_entries WHERE session_id=? AND show_id=? AND role_name=? AND content=? ORDER BY seq DESC",
        (sid, show_id, role_name, content)
    ).fetchall()
    if not rows:
        return jsonify({"ok": True, "deleted": False})
    if orig_ts and len(rows) > 1:
        target = min(rows, key=lambda r: abs((r["timestamp"] or 0) - orig_ts))
    else:
        target = rows[0]
    db.execute("DELETE FROM rp_entries WHERE id=?", (target["id"],))
    db.commit()
    return jsonify({"ok": True, "deleted": True})

def _compute_player_totals(db, show_id, role_name):
    """从 sessions.stats 重算指定角色的累计回复数、字数、场次数。"""
    all_sessions = db.execute(
        "SELECT stats, participants FROM sessions WHERE show_id=?", (show_id,)
    ).fetchall()
    total_replies = 0
    total_words   = 0
    sessions_count = 0
    for s in all_sessions:
        try:
            stats = json.loads(s["stats"] or "{}")
            parts = json.loads(s["participants"] or "[]")
        except Exception:
            continue
        if role_name in stats:
            total_replies  += stats[role_name].get("replies", 0)
            total_words    += stats[role_name].get("words",   0)
        if role_name in parts:
            sessions_count += 1
    return total_replies, total_words, sessions_count


def _upsert_players_from_list(db, show_id, tid, players_list):
    """从 [{qq, role_name, is_npc?}] 批量 upsert 玩家表，并从 sessions.stats 重算累计数据。
    若该角色名已有占位行（qq=role_name），将其升级为真实 QQ。
    NPC 玩家：只更新 is_npc 标记，不计弧长统计。"""
    now = int(time.time() * 1000)
    for p in players_list:
        qq        = str(p.get("qq","")).strip()
        role_name = str(p.get("role_name","")).strip()
        is_npc    = bool(p.get("is_npc", False))
        if not qq or not role_name: continue

        if is_npc:
            # NPC：只确保行存在并标记 is_npc=1，不更新弧长数据
            db.execute("""
                INSERT INTO players (show_id,tenant_id,qq,role_name,sessions_count,total_replies,total_words,last_updated,is_npc)
                VALUES (?,?,?,?,0,0,0,?,1)
                ON CONFLICT(show_id,qq) DO UPDATE SET
                    role_name=excluded.role_name,
                    is_npc=1
            """, (show_id, tid, qq, role_name, now))
            continue

        total_replies, total_words, sessions_count = _compute_player_totals(db, show_id, role_name)

        # 如果存在以 role_name 为占位 QQ 的行，直接把 QQ 更新为真实值
        placeholder = db.execute(
            "SELECT 1 FROM players WHERE show_id=? AND qq=? AND role_name=?",
            (show_id, role_name, role_name)
        ).fetchone()
        if placeholder and qq != role_name:
            db.execute("""
                UPDATE players SET qq=?, sessions_count=?, total_replies=?, total_words=?, last_updated=?
                WHERE show_id=? AND qq=? AND role_name=?
            """, (qq, sessions_count, total_replies, total_words, now, show_id, role_name, role_name))
        else:
            db.execute("""
                INSERT INTO players (show_id,tenant_id,qq,role_name,sessions_count,total_replies,total_words,last_updated)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(show_id,qq) DO UPDATE SET
                    role_name=excluded.role_name,
                    sessions_count=excluded.sessions_count,
                    total_replies=excluded.total_replies,
                    total_words=excluded.total_words,
                    last_updated=excluded.last_updated
            """, (show_id, tid, qq, role_name, sessions_count, total_replies, total_words, now))


@app.route("/api/session_stats", methods=["POST"])
def api_session_stats():
    """实时更新正在进行中的场次 stats（每次有效 RP 回复后 bot 主动推送）。"""
    tid  = get_tenant_from_token()
    show = get_current_show_for_tenant(tid)
    if not show: abort(503)
    show_id = show["id"]
    data  = request.json or {}
    sid   = data.get("session_id","")
    if not sid:
        return jsonify({"ok": False, "error": "missing session_id"}), 400

    zone = _schedule_zone(show)
    if zone == 'pre':
        return jsonify({"ok": True, "skipped": "pre_schedule"})

    stats = data.get("stats", {})
    db    = get_db()
    total_replies = sum(v.get("replies",0) for v in stats.values())
    total_words   = sum(v.get("words",0)   for v in stats.values())
    stats_json    = json.dumps(stats, ensure_ascii=False)
    existing = db.execute("SELECT id FROM sessions WHERE id=? AND show_id=?", (sid, show_id)).fetchone()
    if existing:
        db.execute("""
            UPDATE sessions SET total_replies=?, total_words=?, stats=?
            WHERE id=? AND show_id=?
        """, (total_replies, total_words, stats_json, sid, show_id))
    else:
        # 场次还未正式建立（session_end 尚未到来），先建占位行
        db.execute("""
            INSERT OR IGNORE INTO sessions
              (id,show_id,tenant_id,group_id,platform,game_day,game_time,place,subtype,
               participants,start_ts,end_ts,forced,total_replies,total_words,stats)
            VALUES (?,?,?,?,?,?,?,?,?,'[]',?,0,0,?,?,?)
        """, (sid, show_id, tid,
              data.get("group_id",""),
              data.get("platform",""),
              data.get("game_day","") or "",
              data.get("game_time",""),
              data.get("place",""),
              data.get("subtype",""),
              int(time.time()*1000),
              total_replies, total_words, stats_json))
    # 补戏期只保存场次 stats，不更新玩家弧长
    if zone != 'supplement':
        _upsert_players_from_list(db, show_id, tid, data.get("players", []))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/session_end", methods=["POST"])
def api_session_end():
    tid  = get_tenant_from_token()
    show = get_current_show_for_tenant(tid)
    if not show: abort(503)
    show_id = show["id"]
    data = request.json or {}
    sid  = data.get("session_id","")
    if not sid:
        return jsonify({"ok": False, "error": "missing session_id"}), 400

    # 档期门控
    zone = _schedule_zone(show)
    if zone == 'pre':
        return jsonify({"ok": True, "skipped": "pre_schedule"})

    stats = data.get("stats",{})
    parts = data.get("participants",[])
    db    = get_db()

    # supplement 期间标记场次为"补戏"，方便界面区分
    subtype_val = data.get("subtype","")
    if zone == 'supplement':
        subtype_val = (subtype_val + "|补戏").lstrip("|")

    db.execute("""
        INSERT OR REPLACE INTO sessions
          (id,show_id,tenant_id,group_id,platform,game_day,game_time,place,subtype,
           participants,start_ts,end_ts,forced,total_replies,total_words,stats)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (sid, show_id, tid,
          data.get("group_id",""), data.get("platform",""),
          data.get("game_day",""), data.get("game_time",""),
          data.get("place",""),    subtype_val,
          json.dumps(parts, ensure_ascii=False),
          data.get("start_ts",0), data.get("end_ts",0),
          1 if data.get("forced") else 0,
          sum(v.get("replies",0) for v in stats.values()),
          sum(v.get("words",0)   for v in stats.values()),
          json.dumps(stats, ensure_ascii=False)))
    # 自动同步玩家数据（无需手动执行「更新玩家数据库」）
    # 补戏期：只保存场次记录，不计弧长
    if zone != 'supplement':
        _upsert_players_from_list(db, show_id, tid, data.get("players", []))
    db.commit()
    return jsonify({"ok": True, "zone": zone})

def _show_is_no_review(db, show_id):
    """该季是否「不复盘」（只记统计，不存对话内容）。"""
    row = db.execute("SELECT description FROM shows WHERE id=?", (show_id,)).fetchone()
    return bool(row and row["description"] == "no_review")

@app.route("/api/recent_sessions", methods=["GET"])
def api_recent_sessions():
    """Bot 用：拉取最近 N 场已结束场次的基本信息和个人统计，供奖励情况核查。"""
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id:
        return jsonify({"ok": False, "error": "no current show"}), 404
    limit = min(int(request.args.get("limit", 10)), 50)
    db    = get_db()
    if _show_is_no_review(db, show_id):   # 不复盘季度的场次没有对话内容，不列入奖励核查/复盘
        return jsonify({"ok": True, "sessions": []})
    rows  = db.execute(
        """SELECT id, group_id, platform, game_day, game_time, place, subtype,
                  participants, start_ts, end_ts, forced, stats
           FROM sessions
           WHERE show_id=? AND forced=0
           ORDER BY end_ts DESC
           LIMIT ?""",
        (show_id, limit)
    ).fetchall()
    return jsonify({
        "ok": True,
        "sessions": [dict(r) for r in rows]
    })

@app.route("/api/my_sessions", methods=["GET"])
def api_my_sessions():
    """Bot 用：拉取当前季度里某玩家参与过的已结束场次列表，供「全部复盘」编号展示。"""
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id:
        return jsonify({"ok": False, "error": "no current show"}), 404
    role_name = request.args.get("role_name", "").strip()
    if not role_name:
        return jsonify({"ok": False, "error": "role_name required"}), 400
    limit = min(int(request.args.get("limit", 30)), 50)
    db   = get_db()
    if _show_is_no_review(db, show_id):   # 不复盘季度的场次没有对话内容，不列入「全部复盘」
        return jsonify({"ok": True, "sessions": []})
    rows = db.execute(
        """SELECT id, group_id, game_day, game_time, place, subtype,
                  participants, start_ts, end_ts
           FROM sessions
           WHERE show_id=? AND forced=0 AND end_ts>0
           ORDER BY end_ts DESC""",
        (show_id,)
    ).fetchall()
    sessions = []
    for r in rows:
        r = dict(r)
        try:
            participants = json.loads(r.get("participants") or "[]")
        except Exception:
            participants = []
        if role_name not in participants:
            continue
        r["participants"] = participants
        sessions.append(r)
        if len(sessions) >= limit:
            break
    return jsonify({"ok": True, "sessions": sessions})

@app.route("/api/session_full/<path:session_id>", methods=["GET"])
def api_session_full(session_id):
    """Bot 用：拉取指定场次的完整 RP 正文，供「查看复盘 编号」还原场次内容。"""
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id:
        return jsonify({"ok": False, "error": "no current show"}), 404
    db   = get_db()
    sess = db.execute(
        "SELECT id, game_day, game_time, place, subtype, participants FROM sessions WHERE id=? AND show_id=?",
        (session_id, show_id)
    ).fetchone()
    if not sess:
        return jsonify({"ok": False, "error": "session not found"}), 404
    sess = dict(sess)
    try:
        sess["participants"] = json.loads(sess.get("participants") or "[]")
    except Exception:
        sess["participants"] = []
    entries = db.execute(
        "SELECT role_name, content, timestamp FROM rp_entries WHERE session_id=? AND show_id=? ORDER BY seq, timestamp",
        (session_id, show_id)
    ).fetchall()
    return jsonify({
        "ok": True,
        "session": sess,
        "entries": [dict(e) for e in entries]
    })

@app.route("/api/update_players", methods=["POST"])
def api_update_players():
    tid       = get_tenant_from_token()
    show_id   = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    data      = request.json or {}
    show_name = data.get("show_name","")
    players   = data.get("players",[])
    if not isinstance(players, list):
        return jsonify({"ok": False, "error": "players must be a list"}), 400
    now = int(time.time() * 1000)
    db  = get_db()
    count = 0
    for p in players:
        qq        = str(p.get("qq","")).strip()
        role_name = str(p.get("role_name","")).strip()
        if not qq or not role_name: continue
        db.execute("""
            INSERT INTO players (show_id,tenant_id,qq,role_name,show_name,sessions_count,total_replies,total_words,last_updated)
            VALUES (?,?,?,?,?,0,0,0,?)
            ON CONFLICT(show_id,qq) DO UPDATE SET
                role_name=excluded.role_name, show_name=excluded.show_name, last_updated=excluded.last_updated
        """, (show_id, tid, qq, role_name, show_name, now))
        count += 1
    db.commit()
    return jsonify({"ok": True, "count": count})


# ── 已知群管理 ───────────────────────────────────────────────────────────────

@app.route("/admin/groups", methods=["GET", "POST"])
@require_admin
def admin_groups():
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()
    msg = None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            gid      = request.form.get("group_id","").strip()
            set_name = request.form.get("set_name","").strip()
            note     = request.form.get("name","").strip()
            if gid and set_name:
                existing = db.execute(
                    "SELECT id FROM known_groups WHERE tenant_id=? AND group_id=? AND set_name=?",
                    (tid, gid, set_name)
                ).fetchone()
                if not existing:
                    db.execute(
                        "INSERT INTO known_groups(show_id,tenant_id,group_id,set_name,name,created_at) VALUES(?,?,?,?,?,?)",
                        (0, tid, gid, set_name, note, int(time.time()*1000))
                    )
                    db.commit()
                msg = "added"
        elif action == "bulk_add":
            set_name = request.form.get("set_name","").strip()
            raw      = request.form.get("group_ids","")
            if set_name and raw:
                import re
                gids = [g.strip() for g in re.split(r"[\s,，、;；]+", raw) if g.strip().isdigit()]
                now  = int(time.time()*1000)
                added = 0
                for gid in gids:
                    existing = db.execute(
                        "SELECT id FROM known_groups WHERE tenant_id=? AND group_id=? AND set_name=?",
                        (tid, gid, set_name)
                    ).fetchone()
                    if not existing:
                        db.execute(
                            "INSERT INTO known_groups(show_id,tenant_id,group_id,set_name,name,created_at) VALUES(?,?,?,?,?,?)",
                            (0, tid, gid, set_name, "", now)
                        )
                        added += 1
                if added:
                    db.commit()
                msg = f"bulk_added_{added}"
        elif action == "add_set":
            set_name = request.form.get("set_name","").strip()
            if set_name:
                try:
                    db.execute(
                        "INSERT OR IGNORE INTO known_group_sets(show_id,tenant_id,set_name,created_at) VALUES(?,?,?,?)",
                        (0, tid, set_name, int(time.time()*1000))
                    )
                    db.commit()
                    msg = "set_created"
                except Exception:
                    msg = None
        elif action == "delete":
            row_id = request.form.get("row_id", type=int)
            if row_id:
                db.execute("DELETE FROM known_groups WHERE id=? AND tenant_id=?", (row_id, tid))
                db.commit()
            if request.headers.get("X-Fetch") == "1":
                return jsonify({"ok": True})
            msg = "deleted"
        elif action == "delete_set":
            set_name = request.form.get("set_name","").strip()
            if set_name:
                db.execute("DELETE FROM known_groups WHERE tenant_id=? AND set_name=?", (tid, set_name))
                db.execute("DELETE FROM known_group_sets WHERE tenant_id=? AND set_name=?", (tid, set_name))
                db.commit()
            if request.headers.get("X-Fetch") == "1":
                return jsonify({"ok": True})
            msg = "set_deleted"
        elif action == "edit":
            row_id = request.form.get("row_id", type=int)
            note   = request.form.get("name","").strip()
            if row_id:
                db.execute("UPDATE known_groups SET name=? WHERE id=? AND tenant_id=?", (note, row_id, tid))
                db.commit()
            msg = "edited"
    # 所有已创建的组名（含空组），跨季度按 tenant 查询
    set_name_rows = db.execute(
        "SELECT set_name FROM known_group_sets WHERE tenant_id=? ORDER BY created_at",
        (tid,)
    ).fetchall()
    member_rows = db.execute(
        "SELECT * FROM known_groups WHERE tenant_id=? ORDER BY set_name, created_at",
        (tid,)
    ).fetchall()
    from collections import OrderedDict
    sets = OrderedDict()
    for r in set_name_rows:
        sets.setdefault(r["set_name"], [])
    for r in member_rows:
        sn = r["set_name"] or "（未分组）"
        sets.setdefault(sn, []).append(dict(r))

    import json as _json
    occupied = []
    occupied_synced_str = None
    sync_row = db.execute("SELECT synced_at FROM group_occupancy_sync WHERE tenant_id=?", (tid,)).fetchone()
    if sync_row:
        # 机器人已上报过真实占用快照：以它为准（含微信群，强结释放后立即消失）
        occupied_synced_str = ts_to_str(sync_row["synced_at"])
        for r in db.execute(
            "SELECT * FROM group_occupancy WHERE tenant_id=? ORDER BY start_ts ASC, group_id", (tid,)
        ).fetchall():
            sd = dict(r)
            try:
                sd["participants_list"] = _json.loads(sd.get("participants") or "[]")
            except Exception:
                sd["participants_list"] = []
            sd["start_str"] = ts_to_str(sd["start_ts"]) if sd.get("start_ts") else "—"
            occupied.append(sd)
    else:
        # 旧版机器人（还不会上报快照）：退回按场次记录推算——end_ts=0 且 start_ts>0 的进行中场次
        active_sessions = db.execute(
            """SELECT group_id, game_day, game_time, place, subtype, participants, start_ts
               FROM sessions
               WHERE tenant_id=? AND end_ts=0 AND start_ts>0
               ORDER BY start_ts ASC""",
            (tid,)
        ).fetchall()
        for s in active_sessions:
            sd = dict(s)
            try:
                parts = _json.loads(sd.get("participants") or "[]")
            except Exception:
                parts = []
            sd["participants_list"] = parts
            sd["start_str"] = ts_to_str(sd.get("start_ts", 0))
            occupied.append(sd)

    return render_template("admin_groups.html", sets=sets, msg=msg, occupied=occupied,
                           occupied_synced_str=occupied_synced_str)


# ── 结戏奖励 Dashboard ────────────────────────────────────────────────────────

def _get_reward_config(db, show_id):
    rows = db.execute(
        "SELECT key,value FROM site_config WHERE show_id=? AND key IN (?,?,?,?)",
        (show_id, "reward_bonus_templates", "reward_draw_config",
         "reward_item_registry", "item_registry")
    ).fetchall()
    cfg = {r["key"]: r["value"] for r in rows}
    try:
        bonus_templates = json.loads(cfg.get("reward_bonus_templates") or "[]")
    except Exception:
        bonus_templates = []
    try:
        draw_config = json.loads(cfg.get("reward_draw_config") or "{}")
    except Exception:
        draw_config = {}
    # 优先读主注册表 item_registry，回退到 reward_item_registry（旧数据兼容）
    try:
        item_registry = json.loads(cfg.get("item_registry") or "{}")
    except Exception:
        item_registry = {}
    if not item_registry:
        try:
            item_registry = json.loads(cfg.get("reward_item_registry") or "{}")
        except Exception:
            item_registry = {}
    return bonus_templates, draw_config, item_registry


_PARAM_MAP = {
    '段数': '本场个人段数',
    '字数': '本场个人总字数',
    '总字数': '本场个人总字数',
    '平均字数': '本场个人平均每段字数',
    '耗费时间': '结戏最多耗费时间',
}

def _to_int(v, default):
    """网页表单里的数字：留空/乱填回退默认值，小数取整。以前直接 int()，一个框留空整份结戏奖励就保存失败（500）"""
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return default

def _convert_ui_block(blk):
    conds = []
    for c in blk.get('conditions', []):
        param = _PARAM_MAP.get(c.get('param', ''), c.get('param', ''))
        cond = {'param': param, 'op': c.get('op', '>=')}
        if c.get('op') == 'range':
            cond['value'] = [_to_int(c.get('min'), 0), _to_int(c.get('max'), 0)]
        else:
            cond['value'] = _to_int(c.get('value'), 0)
        conds.append(cond)
    rwds = []
    for r in blk.get('rewards', []):
        rtype = r.get('rtype', '货币')
        reward = {'type': 'fixed', 'amount': _to_int(r.get('amount'), 0)}
        prob = r.get('prob')
        if _to_int(prob, 100) < 100:
            reward['prob'] = _to_int(prob, 100)
        if rtype == '货币':
            reward['target'] = (r.get('target') or '').strip()
            reward['targetType'] = 'currency'
        elif rtype == '道具':
            reward['target'] = (r.get('code') or '').strip()
            reward['targetType'] = 'item'
        elif rtype == '抽取次数':
            pool_name = (r.get('pool_name') or '').strip()
            if not pool_name:
                continue
            rwds.append({'type': 'named_draw', 'pool_name': pool_name, 'amount': _to_int(r.get('amount'), 1)})
            continue
        else:
            reward['target'] = (r.get('name') or '').strip()
            reward['targetType'] = 'attr'
        if not reward['target']:
            continue  # 目标为空则跳过，不写入 bot 存储
        rwds.append(reward)
    return {'conditions': conds, 'rewards': rwds}

def _ui_tpls_to_bot_format(tpls):
    import time as _t
    result = []
    for tpl in tpls:
        blocks = tpl.get('blocks', [])
        groups = []
        i = 0
        while i < len(blocks):
            blk = blocks[i]
            group_blocks = [_convert_ui_block(blk)]
            while blk.get('next_op', 'AND').upper() == 'OR' and i + 1 < len(blocks):
                i += 1
                blk = blocks[i]
                group_blocks.append(_convert_ui_block(blk))
            groups.append({'op': 'or' if len(group_blocks) > 1 else 'and', 'blocks': group_blocks})
            i += 1
        result.append({
            'id': tpl.get('id', int(_t.time() * 1000)),
            'name': tpl.get('name', ''),
            'subtype': tpl.get('subtype', '通用'),
            'enabled': tpl.get('enabled', True),
            'groups': groups,
        })
    return result


_PARAM_MAP_REV = {
    '本场个人段数':          '段数',
    '本场个人总字数':        '字数',
    '本场个人平均每段字数':  '平均字数',
    '结戏最多耗费时间':      '耗费时间',
}
_RTYPE_MAP_REV = {'currency': '货币', 'item': '道具', 'attr': '属性'}

def _bot_tpls_to_ui_format(tpls):
    result = []
    for tpl in tpls:
        flat_blocks = []
        groups = tpl.get('groups', [])
        for gi, group in enumerate(groups):
            blks = group.get('blocks', [])
            op = group.get('op', 'and').lower()
            is_last_group = (gi == len(groups) - 1)
            for bi, blk in enumerate(blks):
                is_last_in_group = (bi == len(blks) - 1)
                conds = []
                for c in blk.get('conditions', []):
                    param = _PARAM_MAP_REV.get(c.get('param', ''), c.get('param', ''))
                    cond = {'param': param, 'op': c.get('op', '>=')}
                    val = c.get('value', 0)
                    if c.get('op') == 'range':
                        cond['min'] = val[0] if isinstance(val, list) else 0
                        cond['max'] = val[1] if isinstance(val, list) and len(val) > 1 else 0
                    else:
                        cond['value'] = val
                    conds.append(cond)
                rwds = []
                for r in blk.get('rewards', []):
                    if r.get('type') == 'named_draw':
                        reward = {'rtype': '抽取次数', 'pool_name': r.get('pool_name', ''), 'amount': r.get('amount', 1)}
                        if r.get('prob') and int(r['prob']) < 100:
                            reward['prob'] = int(r['prob'])
                        rwds.append(reward)
                        continue
                    rtype = _RTYPE_MAP_REV.get(r.get('targetType', ''), '货币')
                    reward = {'rtype': rtype, 'amount': r.get('amount', 0)}
                    if r.get('prob') and int(r['prob']) < 100:
                        reward['prob'] = int(r['prob'])
                    if rtype == '货币':
                        reward['target'] = r.get('target', '')
                    elif rtype == '道具':
                        reward['code'] = r.get('target', '')
                    else:
                        reward['name'] = r.get('target', '')
                    rwds.append(reward)
                next_op = 'OR' if (op == 'or' and not is_last_in_group) else 'AND'
                flat_blocks.append({'conditions': conds, 'rewards': rwds, 'next_op': next_op})
        result.append({
            'id':      tpl.get('id', 0),
            'name':    tpl.get('name', ''),
            'subtype': tpl.get('subtype', '通用'),
            'enabled': tpl.get('enabled', True),
            'blocks':  flat_blocks,
        })
    return result


def _save_reward_config_key(db, show_id, tid, key, value_str):
    db.execute(
        "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
        "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
        (show_id, tid, key, value_str)
    )


# ── 地点示意图（后台自己拼，小手机里看）─────────────────────────────────────────
# 存在 site_config.place_maps：{地点名: {w, h, visible, items:[rect/door/mark]}}。只在网页端，不在 assemble_bot_config 的透传名单里，
# 所以机器人拉不到、也不会触发「网页端有改动」。渲染见 templates/_place_map_render.html（后台编辑器和小手机共用）。
_PM_KINDS = {"water", "green", "road", "plaza", "room", "building"}
_PM_PATHS = {"road", "dirt", "river", "fence", "wall"}

def _clean_place_map(raw):
    if not isinstance(raw, dict):
        raise ValueError("bad map")
    def _i(v, lo, hi, default=0):
        try: return max(lo, min(hi, int(v)))
        except (TypeError, ValueError): return default
    w, h = _i(raw.get("w"), 6, 60, 20), _i(raw.get("h"), 6, 60, 14)
    items = []
    for it in (raw.get("items") or [])[:600]:
        if not isinstance(it, dict): continue
        t = it.get("t")
        if t == "rect" and it.get("kind") in _PM_KINDS:
            x, y = _i(it.get("x"), 0, w - 1), _i(it.get("y"), 0, h - 1)
            items.append({"t": "rect", "kind": it["kind"], "x": x, "y": y,
                          "w": _i(it.get("w"), 1, w - x, 1), "h": _i(it.get("h"), 1, h - y, 1),
                          "name": str(it.get("name") or "")[:20], "place": str(it.get("place") or "")[:40]})
        elif t == "door" and it.get("o") in ("h", "v"):
            items.append({"t": "door", "o": it["o"], "x": _i(it.get("x"), 0, w), "y": _i(it.get("y"), 0, h)})
        elif t == "mark":
            items.append({"t": "mark", "x": _i(it.get("x"), 0, w - 1), "y": _i(it.get("y"), 0, h - 1),
                          "s": _i(it.get("s"), 1, 3, 1),
                          "icon": str(it.get("icon") or "📍")[:8], "label": str(it.get("label") or "")[:12]})
        elif t == "path" and it.get("kind") in _PM_PATHS:
            pts = []
            for q in (it.get("pts") or [])[:400]:
                if isinstance(q, (list, tuple)) and len(q) == 2:
                    pts.append([_i(q[0], 0, w - 1), _i(q[1], 0, h - 1)])
            if len(pts) >= 2:
                items.append({"t": "path", "kind": it["kind"], "pts": pts})
    return {"w": w, "h": h, "visible": bool(raw.get("visible")), "items": items}

def _place_in_maps(maps):
    """{地点名: [放了它的地图名]}，地点列表里标出每个地点在哪张地图上"""
    out = {}
    for mname, m in maps.items():
        for it in m.get("items", []):
            if it.get("t") == "rect" and it.get("place"):
                out.setdefault(it["place"], [])
                if mname not in out[it["place"]]: out[it["place"]].append(mname)
    return out

def _get_maps(db, sid):
    row = db.execute("SELECT value FROM site_config WHERE show_id=? AND key='place_maps'", (sid,)).fetchone()
    try:
        m = json.loads(row["value"]) if row and row["value"] else {}
        return m if isinstance(m, dict) else {}
    except Exception:
        return {}

def _save_maps(db, sid, tid, maps):
    db.execute(
        "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
        "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
        (sid, tid, "place_maps", json.dumps(maps, ensure_ascii=False)))
    db.commit()


@app.route("/admin/places", methods=["GET", "POST"])
@require_admin
def admin_places():
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()

    def _get_places():
        row = db.execute("SELECT value FROM site_config WHERE show_id=? AND key='available_places'", (sid,)).fetchone()
        try: return json.loads(row["value"]) if row and row["value"] else {}
        except: return {}

    def _save_places(places):
        db.execute(
            "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
            "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
            (sid, tid, "available_places", json.dumps(places, ensure_ascii=False))
        )
        db.commit()

    def _get_keys():
        row = db.execute("SELECT value FROM site_config WHERE show_id=? AND key='place_keys'", (sid,)).fetchone()
        try: return json.loads(row["value"]) if row and row["value"] else {}
        except: return {}

    def _save_keys(keys):
        db.execute(
            "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
            "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
            (sid, tid, "place_keys", json.dumps(keys, ensure_ascii=False))
        )
        db.commit()

    if request.method == "POST":
        action = request.form.get("action","")
        is_fetch = request.headers.get("X-Fetch") == "1"

        if action == "add_place":
            name = request.form.get("name","").strip()
            desc = request.form.get("desc","").strip()
            if name:
                places = _get_places()
                if name not in places:
                    places[name] = {"desc": desc, "locked": False}
                    _save_places(places)
                    if is_fetch: return jsonify({"ok": True})
                else:
                    if is_fetch: return jsonify({"ok": False, "error": "exists"})

        elif action == "add_places_bulk":
            count = request.form.get("count", 0, type=int)
            places = _get_places()
            created, skipped = [], []
            for i in range(count):
                name = request.form.get(f"name_{i}", "").strip()
                desc = request.form.get(f"desc_{i}", "").strip()
                if not name:
                    continue
                if name in places:
                    skipped.append(name)
                else:
                    places[name] = {"desc": desc, "locked": False}
                    created.append(name)
            if created:
                _save_places(places)
            if is_fetch: return jsonify({"ok": True, "created": created, "skipped": skipped})

        elif action == "save_map":
            # 地图是独立的，名字随便取（一张地图里可以放多个地点），不要求跟地点同名
            name = request.form.get("name","").strip()[:30]
            if not name:
                if is_fetch: return jsonify({"ok": False, "error": "地图要有名字"})
            else:
                try:
                    cleaned = _clean_place_map(json.loads(request.form.get("map", "")))
                except Exception:
                    if is_fetch: return jsonify({"ok": False, "error": "地图数据不对"})
                    return redirect(url_for("admin_places"))
                maps = _get_maps(db, sid)
                maps[name] = cleaned
                _save_maps(db, sid, tid, maps)
                if is_fetch: return jsonify({"ok": True})

        elif action == "rename_map":
            old = request.form.get("name","").strip()
            new = request.form.get("new_name","").strip()[:30]
            maps = _get_maps(db, sid)
            if old in maps and new and (new == old or new not in maps):
                if new != old:
                    maps = {(new if k == old else k): v for k, v in maps.items()}   # 保持顺序
                    _save_maps(db, sid, tid, maps)
                if is_fetch: return jsonify({"ok": True})
            elif is_fetch:
                return jsonify({"ok": False, "error": "新名字已经有一张地图在用了" if new in maps else "找不到这张地图"})

        elif action == "delete_map":
            name = request.form.get("name","").strip()
            maps = _get_maps(db, sid)
            if maps.pop(name, None) is not None:
                _save_maps(db, sid, tid, maps)
            if is_fetch: return jsonify({"ok": True})

        elif action == "delete_place":
            name = request.form.get("name","").strip()
            if name:
                places = _get_places()
                places.pop(name, None)
                _save_places(places)
                # clean up keys for this place
                keys = _get_keys()
                changed = False
                for plat in keys:
                    for uid in list(keys[plat].keys()):
                        if name in keys[plat][uid]:
                            keys[plat][uid].remove(name)
                            changed = True
                if changed:
                    _save_keys(keys)
            if is_fetch: return jsonify({"ok": True})

        elif action == "toggle_place":
            name = request.form.get("name","").strip()
            locked = None
            if name:
                places = _get_places()
                if name in places:
                    places[name]["locked"] = not places[name].get("locked", False)
                    locked = places[name]["locked"]
                    _save_places(places)
            if is_fetch: return jsonify({"ok": True, "locked": locked})

        elif action == "update_desc":
            name = request.form.get("name","").strip()
            desc = request.form.get("desc","").strip()
            if name:
                places = _get_places()
                if name in places:
                    places[name]["desc"] = desc
                    _save_places(places)
            if is_fetch: return jsonify({"ok": True})

        elif action in ("add_key", "remove_key"):
            # 钥匙是玩家数据，以机器人为准（网页这份只是展示用快照，不会下发给机器人）
            if is_fetch: return jsonify({"ok": False, "error": "请在 QQ 用「地点管理 钥匙 角色名 地点」发放钥匙"})

        elif action == "clear_all":
            if request.form.get("confirm") == "Y":
                db.execute("DELETE FROM site_config WHERE show_id=? AND key IN ('available_places','place_keys','place_maps')", (sid,))
                db.commit()
            if is_fetch: return jsonify({"ok": True})

        elif action == "sync_spot_pools":
            places = _get_places()
            flat = get_flat_config(db, sid)
            try: pool_defs = json.loads(flat.get("pool_definitions", "{}") or "{}")
            except: pool_defs = {}
            created, skipped = [], []
            for name in places:
                pool_name = f"{name}池"
                if pool_name in pool_defs:
                    skipped.append(pool_name)
                else:
                    pool_defs[pool_name] = {"name": pool_name, "type": "fixed", "items": [], "enabled": True}
                    created.append(pool_name)
            db.execute(
                "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
                "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
                (sid, tid, "pool_definitions", json.dumps(pool_defs, ensure_ascii=False))
            )
            db.commit()
            if is_fetch: return jsonify({"ok": True, "created": created, "skipped": skipped})

        return redirect(url_for("admin_places"))

    # GET — build display data
    places  = _get_places()
    all_keys = _get_keys()

    # cross-ref players for role names (QQ platform)
    players = db.execute(
        "SELECT qq, role_name FROM players WHERE show_id=? AND is_npc=0 ORDER BY role_name",
        (sid,)
    ).fetchall()
    qq_to_name = {p["qq"]: (p["role_name"] or p["qq"]) for p in players}

    # keys_by_place: {place_name: [{"platform":..,"uid":..,"role":..}, ...]}
    keys_by_place = {name: [] for name in places}
    orphan_keys = []  # keys referencing non-existent places
    for plat, uid_map in all_keys.items():
        for uid, place_list in uid_map.items():
            role = qq_to_name.get(uid, uid)
            for pname in place_list:
                entry = {"platform": plat, "uid": uid, "role": role}
                if pname in keys_by_place:
                    keys_by_place[pname].append(entry)
                else:
                    orphan_keys.append({**entry, "place": pname})

    return render_template("admin_places.html",
                           places=places,
                           place_maps=_get_maps(db, sid),
                           place_in_maps=_place_in_maps(_get_maps(db, sid)),
                           keys_by_place=keys_by_place,
                           players=[dict(p) for p in players],
                           orphan_keys=orphan_keys)


@app.route("/admin/rewards", methods=["GET"])
@require_admin
def admin_rewards():
    try:
        return _admin_rewards_inner()
    except Exception:
        return "<pre style='color:red;padding:20px'>" + traceback.format_exc() + "</pre>", 500

def _admin_rewards_inner():
    sid = get_show_id()
    db  = get_db()
    _, draw_config, item_registry = _get_reward_config(db, sid)
    # 从 end_game_bonus_templates（bot 格式）读取并转为 UI 格式
    flat = get_flat_config(db, sid)
    try:
        bot_tpls = json.loads(flat.get("end_game_bonus_templates", "[]"))
    except Exception:
        bot_tpls = []
    bonus_templates = _bot_tpls_to_ui_format(bot_tpls)
    try:
        aliases = json.loads(flat.get("private_appointment_aliases", "[]"))
    except Exception:
        aliases = []
    try:
        private_resources = json.loads(flat.get("private_resources") or "{}") or {"私密": {"name": "私约", "isDefault": True}}
    except Exception:
        private_resources = {"私密": {"name": "私约", "isDefault": True}}
    page    = max(1, request.args.get("page", 1, type=int))
    per_page = 30
    total   = db.execute("SELECT COUNT(*) FROM reward_records WHERE show_id=?", (sid,)).fetchone()[0]
    records = db.execute(
        "SELECT * FROM reward_records WHERE show_id=? ORDER BY distributed_at DESC LIMIT ? OFFSET ?",
        (sid, per_page, (page-1)*per_page)
    ).fetchall()
    total_pages = max(1, (total + per_page - 1) // per_page)
    try:
        pool_names = sorted(json.loads(flat.get("pool_definitions", "{}") or "{}").keys())
    except Exception:
        pool_names = []
    equip_registry = json.loads(flat.get("equipment_registry", "{}") or "{}")
    return render_template("admin_rewards.html",
                           bonus_templates=bonus_templates,
                           draw_config=draw_config,
                           item_registry=item_registry,
                           equip_registry=equip_registry,
                           pool_names=pool_names,
                           aliases=aliases,
                           private_resources=private_resources,
                           records=[dict(r) for r in records],
                           total=total, page=page, total_pages=total_pages,
                           ts_to_str=ts_to_str)


@app.route("/admin/rewards/config", methods=["POST"])
@require_admin
def admin_rewards_save_config():
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()
    section = request.form.get("section","")
    if section == "draw":
        enabled   = request.form.get("draw_enabled") == "1"
        chance    = max(0, min(100, request.form.get("draw_chance", 0, type=int)))
        count     = max(1, request.form.get("draw_count", 1, type=int))
        val = json.dumps({"enabled": enabled, "chance": chance, "count": count})
        _save_reward_config_key(db, sid, tid, "reward_draw_config", val)
        db.commit()
    elif section == "items":
        # 只收「增/删」操作，在服务器当前的注册表上应用，不再接收页面内存里的整份注册表——
        # 否则页面打开期间别处（通用库导入、另一个页签、机器人推送）加进去的条目，会被这页旧内存整份覆盖掉。
        # 返回合并后的最新注册表，页面用它刷新，顺带把旧页面漏掉的条目补看见。
        if request.form.get("item_registry_json") and not request.form.get("ops"):
            return jsonify({"ok": False, "error": "页面版本过旧，请刷新后再操作（避免覆盖别处的改动）"})
        try:
            ops = json.loads(request.form.get("ops") or "[]")
            if not isinstance(ops, list):
                raise ValueError
        except (ValueError, json.JSONDecodeError):
            return jsonify({"ok": False, "error": "json_parse"})
        if not db.in_transaction:
            db.execute("BEGIN IMMEDIATE")   # 读-改-写期间锁住写入，避免两个保存交错
        reg = _load_show_registry(db, tid, sid) or {}
        err = None
        for op in ops:
            if not isinstance(op, dict):
                continue
            if op.get("op") == "add":
                e = _uni_clean_entry(op.get("entry"))
                if not e:
                    err = "名称和类型必填"
                    break
                if any(isinstance(r, dict) and r.get("name") == e["name"] for r in reg.values()):
                    err = f"「{e['name']}」已存在"
                    break
                prefix = _UNI_TYPES[e["type"]]
                code = next((prefix + str(d).zfill(3) for d in range(1, 10000)
                             if (prefix + str(d).zfill(3)) not in reg), None)
                if not code:
                    err = "编号空间已满"
                    break
                reg[code] = {"code": code, **e}
            elif op.get("op") == "del":
                reg.pop(str(op.get("code") or ""), None)
        if not err and ops:
            val = json.dumps(reg, ensure_ascii=False)
            # 同时写主注册表（机器人拉取）和兼容 key
            _save_reward_config_key(db, sid, tid, "item_registry", val)
            _save_reward_config_key(db, sid, tid, "reward_item_registry", val)
        db.commit()
        if request.headers.get("X-Fetch") == "1":
            return jsonify({"ok": not err, "error": err, "registry": reg})
    elif section == "bonus":
        raw = request.form.get("bonus_templates_json","").strip()
        try:
            parsed = json.loads(raw)
            val = json.dumps(parsed, ensure_ascii=False)
        except Exception:
            if request.headers.get("X-Fetch") == "1":
                return jsonify({"ok": False, "error": "json_parse"})
            return redirect(url_for("admin_rewards") + "?err=json")
        # UI 格式 → bot 格式，写到唯一数据源 key
        bot_val = json.dumps(_ui_tpls_to_bot_format(parsed), ensure_ascii=False)
        _save_reward_config_key(db, sid, tid, "end_game_bonus_templates", bot_val)
        db.commit()
        if request.headers.get("X-Fetch") == "1":
            return jsonify({"ok": True})
    return redirect(url_for("admin_rewards") + "?saved=1")


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_show_names(db, show_id):
    rows = db.execute(
        "SELECT role_name, show_name FROM players WHERE show_id=? AND show_name IS NOT NULL AND show_name!=''",
        (show_id,)
    ).fetchall()
    return {r["role_name"]: r["show_name"] for r in rows}

def _parse_events(rows):
    result = []
    for e in rows:
        e = dict(e)
        try: e["extra_info"] = json.loads(e["extra_info"] or "{}")
        except Exception: e["extra_info"] = {}
        result.append(e)
    return result

def _parse_rest_hours(s):
    """解析 'HHMM-HHMM' 字符串，返回 (start_min, end_min) 或 None。支持跨夜区间如 2200-0600。"""
    import re
    if not s:
        return None
    s = s.strip()
    if not re.match(r'^\d{4}-\d{4}$', s):
        return None
    start, end = s.split('-')
    s_min = int(start[:2]) * 60 + int(start[2:])
    e_min = int(end[:2])   * 60 + int(end[2:])
    if s_min == e_min or s_min >= 1440 or e_min > 1440:
        return None
    return (s_min, e_min)


def _effective_duration_mins(start_ms, end_ms, rest_start_min, rest_end_min):
    """计算 [start_ms, end_ms] 区间内扣除每日休息时段后的有效分钟数。end<=start 视为跨夜，延伸到次日。"""
    from datetime import datetime, timedelta
    if end_ms <= start_ms:
        return 0
    start_sec = start_ms / 1000
    end_sec   = end_ms   / 1000
    start_dt  = datetime.fromtimestamp(start_sec, TZ_BEIJING)
    # 从前一天起算，覆盖前一日跨夜休息段延伸到当日的部分
    cur_day   = datetime(start_dt.year, start_dt.month, start_dt.day, tzinfo=TZ_BEIJING) - timedelta(days=1)
    wrap      = rest_end_min <= rest_start_min
    rest_overlap_sec = 0.0
    while cur_day.timestamp() < end_sec:
        rest_s = cur_day.timestamp() + rest_start_min * 60
        rest_e = cur_day.timestamp() + (rest_end_min + (1440 if wrap else 0)) * 60
        ov_s = max(start_sec, rest_s)
        ov_e = min(end_sec,   rest_e)
        if ov_e > ov_s:
            rest_overlap_sec += ov_e - ov_s
        cur_day += timedelta(days=1)
    effective_sec = (end_sec - start_sec) - rest_overlap_sec
    return max(0, int(effective_sec / 60))


def _get_rest_pair(db, show_id):
    """从配置读取休息时段，返回 (start_min, end_min) 或 None。"""
    flat = get_flat_config(db, show_id)
    return _parse_rest_hours(flat.get("rest_hours", ""))


def _enrich_session(s, rest_pair=None):
    try: s["participants"] = json.loads(s.get("participants") or "[]")
    except Exception: s["participants"] = []
    try: s["stats"] = json.loads(s.get("stats") or "{}")
    except Exception: s["stats"] = {}
    s["start_str"] = ts_to_str(s.get("start_ts"))
    s["end_str"]   = ts_to_str(s.get("end_ts"))
    start, end = s.get("start_ts",0), s.get("end_ts",0)
    if start and end and end > start:
        if rest_pair:
            mins = _effective_duration_mins(start, end, rest_pair[0], rest_pair[1])
        else:
            mins = (end - start) // 60000
        s["duration_str"] = f"{mins//60}小时{mins%60}分" if mins >= 60 else (f"{mins}分钟" if mins > 0 else "")
    else:
        s["duration_str"] = ""
    return s

def _enrich_sessions(rows, rest_pair=None):
    return [_enrich_session(dict(r), rest_pair) for r in rows]


@app.route("/api/group_occupancy", methods=["POST"])
def api_group_occupancy():
    """机器人上报「此刻真实被占用的全部群」（整体快照，覆盖式），后台群号组页据此显示当前占用群。"""
    tid  = get_tenant_from_token()
    data = request.json or {}
    groups = data.get("groups")
    if not isinstance(groups, list):
        return jsonify({"ok": False, "error": "groups must be a list"}), 400
    db  = get_db()
    now = int(time.time() * 1000)
    db.execute("DELETE FROM group_occupancy WHERE tenant_id=?", (tid,))
    for g in groups:
        gid = str(g.get("group_id", "")).strip()
        if not gid:
            continue
        parts = g.get("participants") or []
        db.execute(
            "INSERT OR REPLACE INTO group_occupancy"
            "(tenant_id,group_id,subtype,game_day,game_time,place,participants,start_ts) VALUES(?,?,?,?,?,?,?,?)",
            (tid, gid, str(g.get("subtype", "") or ""), str(g.get("game_day", "") or ""),
             str(g.get("game_time", "") or ""), str(g.get("place", "") or ""),
             json.dumps(parts if isinstance(parts, list) else [], ensure_ascii=False),
             int(g.get("start_ts") or 0))
        )
    db.execute("INSERT OR REPLACE INTO group_occupancy_sync(tenant_id,synced_at) VALUES(?,?)", (tid, now))
    db.commit()
    return jsonify({"ok": True, "count": len(groups)})


@app.route("/api/groups", methods=["GET"])
def api_groups():
    tid = get_tenant_from_token()
    db  = get_db()
    rows = db.execute(
        "SELECT group_id, name, description FROM known_groups WHERE tenant_id=? ORDER BY created_at",
        (tid,)
    ).fetchall()
    return jsonify({"ok": True, "groups": [dict(r) for r in rows]})


@app.route("/api/group_set/<set_name>", methods=["GET"])
def api_group_set(set_name):
    tid  = get_tenant_from_token()
    db   = get_db()
    rows = db.execute(
        "SELECT group_id FROM known_groups WHERE tenant_id=? AND set_name=? ORDER BY created_at",
        (tid, set_name)
    ).fetchall()
    return jsonify({"ok": True, "set_name": set_name, "group_ids": [r["group_id"] for r in rows]})


@app.route("/api/reward_result", methods=["POST"])
def api_reward_result():
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    data    = request.json or {}
    results = data.get("results", [])
    if not isinstance(results, list):
        return jsonify({"ok": False, "error": "results must be a list"}), 400
    db  = get_db()
    now = int(time.time() * 1000)
    for r in results:
        db.execute(
            "INSERT INTO reward_records(show_id,tenant_id,session_id,game_day,player_qq,role_name,reward_data,distributed_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (show_id, tid,
             str(r.get("session_id","")), str(r.get("game_day","")),
             str(r.get("player_qq","")), str(r.get("role_name","")),
             json.dumps(r.get("reward_data",{}), ensure_ascii=False),
             r.get("distributed_at", now))
        )
    db.commit()
    return jsonify({"ok": True, "count": len(results)})


@app.route("/api/reward_config", methods=["GET"])
def api_reward_config():
    """机器人拉取结戏奖励配置（道具注册表 + 奖励模版 + 抽奖配置）。"""
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    db = get_db()
    bonus_templates, draw_config, item_registry = _get_reward_config(db, show_id)
    return jsonify({
        "ok": True,
        "item_registry":     item_registry,
        "bonus_templates":   bonus_templates,
        "draw_config":       draw_config,
    })


# ── 抽取池管理 ──────────────────────────────────────────────────────────────

def _get_pool_data(db, show_id):
    flat = get_flat_config(db, show_id)
    pool_defs = json.loads(flat.get("pool_definitions", "{}") or "{}")
    pool_cfg  = json.loads(flat.get("pool_draw_config", '{"total":null,"pools":{}}') or '{"total":null,"pools":{}}')
    item_registry = json.loads(flat.get("item_registry", "{}") or "{}")
    if not item_registry:
        item_registry = json.loads(flat.get("reward_item_registry", "{}") or "{}")
    return pool_defs, pool_cfg, item_registry


@app.route("/admin/help/bulk", methods=["GET"])
@require_admin
def admin_bulk_help():
    """批量录入教程：各种格式说明 + 可复制的 AI 提示词（提示词里带上当前已有的属性/槽位/物品名）。"""
    sid = get_show_id()
    db  = get_db()
    flat = get_flat_config(db, sid)
    def _j(key, default):
        raw = flat.get(key) or ""
        try:
            return json.loads(raw) if raw else default
        except (json.JSONDecodeError, TypeError):
            return default
    item_reg  = _j("item_registry", {}) or {}
    equip_reg = _j("equipment_registry", {}) or {}
    slots     = _j("equipment_slots", ["head", "chest", "hand", "leg", "foot"]) or []
    slot_names = _j("equipment_slot_names", {}) or {}
    default_slot_names = {"head": "头部", "chest": "胸部", "hand": "手部", "leg": "腿部", "foot": "脚部"}
    recipes   = _j("craft_recipes", {}) or {}
    gifts     = _j("preset_gifts", {}) or {}
    ctx = {
        "attrs":      list((_j("rpg_attr_defs", {}) or {}).keys()),
        "slots":      [{"code": c, "name": slot_names.get(c) or default_slot_names.get(c) or c} for c in slots],
        "currencies": [r.get("name") for r in item_reg.values() if isinstance(r, dict) and r.get("type") == "currency" and r.get("name")],
        "items":      [r.get("name") for r in item_reg.values() if isinstance(r, dict) and r.get("type") != "currency" and r.get("name")],
        "equips":     [r.get("name") for r in equip_reg.values() if isinstance(r, dict) and r.get("name")],
        "recipes":    [(item_reg.get(code) or {}).get("name") or code for code in recipes.keys()],
        "gifts":      [f"{code} {g.get('name', '')}".strip() for code, g in gifts.items() if isinstance(g, dict)],
    }
    return render_template("admin_bulk_help.html", ctx=ctx)


@app.route("/admin/rpg", methods=["GET"])
@require_admin
def admin_rpg():
    sid = get_show_id()
    db  = get_db()
    flat = get_flat_config(db, sid)
    def _j(key, default):
        raw = flat.get(key) or ""
        try:
            return json.loads(raw) if raw else default
        except (json.JSONDecodeError, TypeError):
            return default
    item_reg = _j("item_registry", {})
    if not item_reg:
        item_reg = _j("reward_item_registry", {})
    return render_template("admin_rpg.html",
        item_registry       = item_reg,
        attr_defs           = _j("rpg_attr_defs", {}),
        item_pending        = _j("item_registry_pending", []),
        equip_registry      = _j("equipment_registry", {}),
        equip_pending       = _j("equipment_registry_pending", []),
        equip_slots         = _j("equipment_slots", ["head","chest","hand","leg","foot"]),
        equip_slot_names    = _j("equipment_slot_names", {}),
        craft_recipes       = _j("craft_recipes", {}),
        skill_defs          = _j("skill_defs", {}),
        battle_attrs        = _j("battle_attrs", {}),
        attack_defense_cfg  = _j("attack_defense_config", {}),
        player_skills       = _j("player_skills", {}),
        battle_log          = _j("battle_log", []),
        trade_whitelist     = _j("trade_whitelist", []),
        point_groups        = _j("rpg_point_groups", {}),
    )


@app.route("/admin/rpg/save", methods=["POST"])
@require_admin
def admin_rpg_save():
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()
    data = request.get_json(silent=True) or {}
    allowed = {
        "item_registry", "rpg_attr_defs", "sys_attr_presets",
        "item_registry_pending", "equipment_registry",
        "equipment_registry_pending", "equipment_slots", "equipment_slot_names",
        "craft_recipes", "skill_defs",
        "attack_defense_config",
        "trade_whitelist",
        "rpg_point_groups",
    }
    # battle_attrs / player_skills 是玩家数据，只能在 QQ 里改（「属性 设置」「技能 配置」）
    for key, val in data.items():
        if key not in allowed:
            continue
        if key == "attack_defense_config" and isinstance(val, dict):
            # 合并写入：机器人侧还有网页没展示的字段（如 maxRefusals），整体覆盖会把它们丢掉
            old = db.execute("SELECT value FROM site_config WHERE show_id=? AND key='attack_defense_config'",
                             (sid,)).fetchone()
            try: merged = json.loads(old["value"]) if old and old["value"] else {}
            except (json.JSONDecodeError, TypeError): merged = {}
            merged.update(val)
            val = merged
        if isinstance(val, (dict, list)):
            val = json.dumps(val, ensure_ascii=False)
        db.execute(
            "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
            "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
            (sid, tid, key, val)
        )
    db.commit()
    return jsonify({"ok": True})


@app.route("/admin/pools", methods=["GET"])
@require_admin
def admin_pools():
    sid = get_show_id()
    db  = get_db()
    pool_defs, pool_cfg, item_registry = _get_pool_data(db, sid)
    flat = get_flat_config(db, sid)
    attr_defs = json.loads(flat.get("rpg_attr_defs", "{}") or "{}")
    pool_schemas = json.loads(flat.get("pool_schemas", "{}") or "{}")
    return render_template("admin_pools.html",
                           pool_defs=pool_defs,
                           pool_cfg=pool_cfg,
                           item_registry=item_registry,
                           attr_defs=attr_defs,
                           pool_schemas=pool_schemas)


@app.route("/admin/pools/save", methods=["POST"])
@require_admin
def admin_pools_save():
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "error": "no data"}), 400
    pool_defs = data.get("pool_definitions", {})
    pool_cfg  = data.get("pool_draw_config", {"total": None, "pools": {}})
    to_save = [("pool_definitions", pool_defs), ("pool_draw_config", pool_cfg)]
    if "pool_schemas" in data:
        to_save.append(("pool_schemas", data["pool_schemas"]))
    for key, val in to_save:
        db.execute(
            "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
            "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
            (sid, tid, key, json.dumps(val, ensure_ascii=False))
        )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/pool_config", methods=["GET"])
def api_pool_config():
    """机器人拉取抽取池配置。"""
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id:
        abort(503)
    db = get_db()
    pool_defs, pool_cfg, _ = _get_pool_data(db, show_id)
    flat = get_flat_config(db, show_id)
    pool_schemas = json.loads(flat.get("pool_schemas", "{}") or "{}")
    return jsonify({"ok": True, "pool_definitions": pool_defs, "pool_draw_config": pool_cfg,
                     "pool_schemas": pool_schemas})


@app.route("/api/pool_config", methods=["POST"])
def api_pool_config_push():
    """机器人推送本地池子配置到存档服务器（覆盖）。"""
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id:
        abort(503)
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "error": "no data"}), 400
    db = get_db()
    updates = []
    if "pool_definitions" in data:
        updates.append(("pool_definitions", data["pool_definitions"]))
    if "pool_draw_config" in data:
        updates.append(("pool_draw_config", data["pool_draw_config"]))
    if "pool_schemas" in data:
        updates.append(("pool_schemas", data["pool_schemas"]))
    if not updates:
        return jsonify({"ok": False, "error": "missing pool_definitions or pool_draw_config"}), 400
    for key, val in updates:
        db.execute(
            "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
            "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
            (show_id, tid, key, json.dumps(val, ensure_ascii=False))
        )
    db.commit()
    pool_count = len(data.get("pool_definitions", {}))
    return jsonify({"ok": True, "pools": pool_count})


@app.route("/admin/auctions", methods=["GET"])
@require_admin
def admin_auctions():
    sid = get_show_id()
    db  = get_db()
    flat = get_flat_config(db, sid)
    queue    = json.loads(flat.get("auction_queue",    "[]") or "[]")
    snapshot = json.loads(flat.get("auction_snapshot", "{}") or "{}")
    item_registry = json.loads(flat.get("item_registry", "{}") or "{}")
    if not item_registry:
        item_registry = json.loads(flat.get("reward_item_registry", "{}") or "{}")
    return render_template("admin_auctions.html",
                           queue=queue, snapshot=snapshot,
                           item_registry=item_registry)


@app.route("/admin/auctions/save", methods=["POST"])
@require_admin
def admin_auctions_save():
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "error": "no data"}), 400
    queue = data.get("queue", [])
    db.execute(
        "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
        "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
        (sid, tid, "auction_queue", json.dumps(queue, ensure_ascii=False))
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/admin/gifts", methods=["GET"])
@require_admin
def admin_gifts():
    sid = get_show_id()
    db  = get_db()
    flat = get_flat_config(db, sid)
    preset_gifts = json.loads(flat.get("preset_gifts", "{}") or "{}")
    return render_template("admin_gifts.html", preset_gifts=preset_gifts)


@app.route("/admin/gifts/save", methods=["POST"])
@require_admin
def admin_gifts_save():
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "error": "no data"}), 400
    gifts = data.get("preset_gifts", {})
    db.execute(
        "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
        "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
        (sid, tid, "preset_gifts", json.dumps(gifts, ensure_ascii=False))
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/admin/shop", methods=["GET"])
@require_admin
def admin_shop():
    sid = get_show_id()
    db  = get_db()
    flat = get_flat_config(db, sid)
    def _j(key, default):
        raw = flat.get(key) or ""
        try:
            return json.loads(raw) if raw else default
        except (json.JSONDecodeError, TypeError):
            return default
    item_reg      = _j("item_registry", {})
    if not item_reg:
        item_reg  = _j("reward_item_registry", {})
    return render_template("admin_shop.html",
        shop_listings    = _j("shop_listings", []),
        secondhand_market= _j("secondhand_market", {}),
        market_config    = _j("market_config", {"fee": 3, "enabled": True}),
        item_registry    = item_reg,
    )


@app.route("/admin/shop/save", methods=["POST"])
@require_admin
def admin_shop_save():
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "error": "no data"}), 400
    allowed = {"shop_listings", "market_config"}
    for key, val in data.items():
        if key not in allowed:
            continue
        if isinstance(val, (dict, list)):
            val = json.dumps(val, ensure_ascii=False)
        db.execute(
            "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
            "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
            (sid, tid, key, val)
        )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/auction_queue", methods=["GET"])
def api_auction_queue_get():
    """机器人拉取拍卖队列。"""
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id:
        abort(503)
    db = get_db()
    flat  = get_flat_config(db, show_id)
    queue = json.loads(flat.get("auction_queue", "[]") or "[]")
    return jsonify({"ok": True, "queue": queue})


@app.route("/api/auction_queue", methods=["DELETE"])
def api_auction_queue_clear():
    """机器人拉取完毕后清空队列。"""
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id:
        abort(503)
    db = get_db()
    tid_w = tid
    db.execute(
        "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
        "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
        (show_id, tid_w, "auction_queue", "[]")
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/auction_snapshot", methods=["GET"])
def api_auction_snapshot_get():
    """机器人拉取拍卖快照（用于 bot 重启后恢复进行中的拍卖）。"""
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id:
        abort(503)
    db = get_db()
    row = db.execute(
        "SELECT value FROM site_config WHERE show_id=? AND key='auction_snapshot'", (show_id,)
    ).fetchone()
    snapshot = {}
    if row and row["value"]:
        try:
            snapshot = json.loads(row["value"])
        except Exception:
            pass
    return jsonify({"ok": True, "snapshot": snapshot})


@app.route("/api/auction_snapshot", methods=["POST"])
def api_auction_snapshot():
    """机器人推送拍卖快照到存档服务器。"""
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id:
        abort(503)
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "error": "no data"}), 400
    snapshot = data.get("snapshot", {})
    db = get_db()
    db.execute(
        "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
        "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
        (show_id, tid, "auction_snapshot", json.dumps(snapshot, ensure_ascii=False))
    )
    db.commit()
    return jsonify({"ok": True, "count": len(snapshot)})


import secrets as _secrets

_GUIDE_MAX = 2

def _guide_slug():
    return _secrets.token_urlsafe(6)

def _parse_guide_blocks(raw):
    """兼容旧 array 格式和新 object 格式，统一返回 {key: text_or_None}。"""
    try:
        data = json.loads(raw or "{}")
    except Exception:
        return {}
    if isinstance(data, list):          # 旧格式：["key1","key2"]
        return {k: None for k in data}
    if isinstance(data, dict):          # 新格式：{"key1": null, "key2": "custom..."}
        return data
    return {}

def _build_guide_blocks(raw):
    """从 blocks 字段构建可渲染的区块列表，含自定义内容。"""
    mapping  = _parse_guide_blocks(raw)
    key_defs = {b["key"]: b for b in COMMAND_BLOCKS}
    result   = []
    for key, custom_text in mapping.items():
        b = key_defs.get(key)
        if not b:
            continue
        lines = custom_text.split("\n") if custom_text else b["lines"]
        result.append({**b, "lines": lines, "has_custom": custom_text is not None})
    return result

@app.route("/admin/command-guides", methods=["GET"])
@require_admin
def admin_command_guides():
    tid = current_tenant_id()
    db  = get_db()
    guides = db.execute(
        "SELECT id, name, slug, blocks, created_at FROM command_guides WHERE tenant_id=? ORDER BY created_at DESC",
        (tid,)
    ).fetchall()
    guides = [dict(g) for g in guides]
    for g in guides:
        g["count"] = len(_parse_guide_blocks(g["blocks"]))
    return render_template("admin_command_guides.html",
        guides=guides, blocks=COMMAND_BLOCKS,
        can_create=len(guides) < _GUIDE_MAX,
        guide_max=_GUIDE_MAX)

def _collect_blocks_from_form():
    """从 POST 表单收集 blocks dict：选中的 key → 自定义文本或 None。"""
    selected_keys = request.form.getlist("blocks")
    result = {}
    for key in selected_keys:
        custom = request.form.get(f"block_text_{key}", "").strip()
        # 找到默认内容，判断是否真的改动了
        default_lines = next((b["lines"] for b in COMMAND_BLOCKS if b["key"] == key), None)
        default_text  = "\n".join(default_lines) if default_lines else ""
        result[key] = custom if (custom and custom != default_text) else None
    return json.dumps(result, ensure_ascii=False)

@app.route("/admin/command-guides/new", methods=["GET","POST"])
@require_admin
def admin_command_guide_new():
    tid = current_tenant_id()
    db  = get_db()
    if db.execute("SELECT COUNT(*) FROM command_guides WHERE tenant_id=?", (tid,)).fetchone()[0] >= _GUIDE_MAX:
        return redirect(url_for("admin_command_guides") + "?err=limit")
    if request.method == "POST":
        name   = request.form.get("name", "").strip() or "指令指南"
        blocks = _collect_blocks_from_form()
        slug   = _guide_slug()
        while db.execute("SELECT 1 FROM command_guides WHERE slug=?", (slug,)).fetchone():
            slug = _guide_slug()
        db.execute(
            "INSERT INTO command_guides(tenant_id,name,slug,blocks,created_at) VALUES(?,?,?,?,?)",
            (tid, name, slug, blocks, int(time.time()*1000))
        )
        db.commit()
        return redirect(url_for("admin_command_guides") + "?saved=1")
    return render_template("admin_command_guide_edit.html",
        guide=None, blocks=COMMAND_BLOCKS, selected_map={})

@app.route("/admin/command-guides/<int:gid>/edit", methods=["GET","POST"])
@require_admin
def admin_command_guide_edit(gid):
    tid = current_tenant_id()
    db  = get_db()
    row = db.execute("SELECT * FROM command_guides WHERE id=? AND tenant_id=?", (gid, tid)).fetchone()
    if not row: abort(404)
    if request.method == "POST":
        name   = request.form.get("name", "").strip() or "指令指南"
        blocks = _collect_blocks_from_form()
        db.execute("UPDATE command_guides SET name=?, blocks=? WHERE id=?", (name, blocks, gid))
        db.commit()
        return redirect(url_for("admin_command_guides") + "?saved=1")
    selected_map = _parse_guide_blocks(row["blocks"])
    return render_template("admin_command_guide_edit.html",
        guide=dict(row), blocks=COMMAND_BLOCKS, selected_map=selected_map)

@app.route("/admin/command-guides/<int:gid>/delete", methods=["POST"])
@require_admin
def admin_command_guide_delete(gid):
    tid = current_tenant_id()
    db  = get_db()
    db.execute("DELETE FROM command_guides WHERE id=? AND tenant_id=?", (gid, tid))
    db.commit()
    return redirect(url_for("admin_command_guides"))

def _guide_to_text(name, blocks_raw):
    """将指南内容转为纯文字，供 bot 直接发送。"""
    blocks = _build_guide_blocks(blocks_raw)
    player_blocks = [b for b in blocks if b["category"] == "player"]
    admin_blocks  = [b for b in blocks if b["category"] == "admin"]
    parts = [f"📖 {name}"]
    def render_section(section_label, blist):
        parts.append(f"\n【{section_label}】")
        for b in blist:
            parts.append(f"\n▸ {b['label']}")
            for line in b["lines"]:
                parts.append(line)
    if player_blocks:
        render_section("玩家指令", player_blocks)
    if admin_blocks:
        render_section("管理指令", admin_blocks)
    return "\n".join(parts)


@app.route("/api/command_guides", methods=["GET"])
def api_command_guides():
    tid  = get_tenant_from_token()
    db   = get_db()
    rows = db.execute(
        "SELECT name, slug, blocks FROM command_guides WHERE tenant_id=? ORDER BY created_at DESC",
        (tid,)
    ).fetchall()
    guides = [{"name": r["name"], "text": _guide_to_text(r["name"], r["blocks"])} for r in rows]
    return jsonify({"ok": True, "guides": guides})




if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5001, debug=False)

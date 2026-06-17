import io, os, json, functools, secrets, time, hmac, logging, traceback, zipfile
from collections import defaultdict
from datetime import datetime, date as _date, timezone, timedelta

TZ_BEIJING = timezone(timedelta(hours=8))
from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, abort, send_file, g)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "rp_archive_secret_key_change_me")


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
        "。战斗状态",
        "  查看当前战斗状态与属性",
        "",
        "。战斗历史",
        "  查看历史战斗记录",
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
        "。设置 基础 / 互动 / 信件 / 公告 / 道具 / 群组 / 季末报告",
        "  进入对应模块的设置面板",
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
        "。初始化设置",
        "  将所有设置恢复为默认值（慎用）",
        "",
        "。同步设置",
        "  从 rparchive 拉取并覆盖所有系统配置",
        "",
        "。同步到服务端",
        "  将机器人当前配置推送到 rparchive",
        "",
        "。全量上传",
        "  将所有配置（含物品注册/结戏模版）一次性推送到 rparchive",
        "",
        "。创建新季度 恋综名 复盘/不复盘 [MMDD-MMDD] [补戏MMDD]",
        "  新建一个游戏季度，可指定档期",
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
        "。存入统计",
        "  将全场玩家历史数据导出为字段格式",
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
        "。上载物品 名称*描述[*属性效果]  （支持多行批量）",
        "  例：。上载物品 急救包*紧急治疗用品*体力+20",
        "。注册货币 名称*描述",
        "  例：。注册货币 金币*基础流通货币",
        "。上载互动物品 名称*描述*互动效果",
        "  注册可施加给他人的互动类道具",
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
        "。注册池子 池子名 fixed/free",
        "  fixed=固定池（加权随机），free=自由池（有限存量）",
        "。一键建池 池子名",
        "  快速创建标准池（自动设置默认参数）",
        "。上架池子 池子名 物品码*权重or数量  （支持多行）",
        "。从池移除 池子名 物品码",
        "。查看池子 池子名",
        "  查看该池所有物品及库存",
        "。清空池子 池子名",
        "  清空池内所有物品",
        "。池子设定 总量:N / 池子名:N / 总量:无限 / 查看",
        "。开启池子/关闭池子/删除池子 池子名",
        "。发放抽取 角色名 N              总额外次数",
        "。发放抽取 角色名 池子名 N       特定池额外次数",
        "。同步踩点池",
        "  从 rparchive 同步踩点奖励池配置",
        "。同步池子",
        "  从 rparchive 同步所有池子配置",
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
        "。物品使用记录 [N]   查看今日最近N条",
    ]},
    {"key": "adm_rpg", "label": "🧬 RPG 属性 & 合成", "category": "admin", "lines": [
        "【属性注册】",
        "。注册属性 属性名1 属性名2 ...",
        "  注册可用属性名（防止与货币重名）",
        "。注册属性 列表",
        "  查看已注册属性列表",
        "。删除属性 属性名",
        "  删除已注册的属性",
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
        "。注册合成 产物码*描述*材料码1:数量1,材料码2:数量2[*限制]",
        "  例：。注册合成 高级丹*升级丹药*初级丹:3,金币:100",
        "属性限制：*attr:属性名:最小值",
        "货币限制：*currency:货币名:最小值",
        "",
        "【装备与升级】",
        "。注册装备 装备名*描述*槽位[*属性效果]",
        "  注册可穿戴装备",
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
        "。上传预设礼物 #1&玫瑰花&一束红玫瑰",
        "  批量：#1&礼物1&内容$#2&礼物2&内容",
        "。上传预设礼物 导出  （导出所有礼物 JSON）",
        "",
        "。删除预设礼物 编号",
        "。删除预设礼物 全部 确认  ⚠️",
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
        "。拉取拍卖队列",
        "  从 rparchive 拉取待上架的拍卖队列",
        "",
        "。上传拍卖",
        "  将当前拍卖状态推送到 rparchive",
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
    {"section": "基础", "fields": [
        {"key": "love_show_name",         "label": "恋综名",      "type": "text",   "default": ""},
        {"key": "global_days",            "label": "当前游戏日",   "type": "text",   "default": "D1", "note": "如 D1 / D2 / D3"},
        {"key": "auto_day_reset_enabled", "label": "自动天数推进", "type": "bool",   "default": "false"},
        {"key": "item_pool_mode",         "label": "道具池模式",   "type": "select", "default": "自由池", "options": ["自由池", "抽取池"]},
    ]},
    {"section": "群组 ID", "fields": [
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
        {"key": "enable_general_letter",      "label": "通用信件",          "type": "bool", "default": "true"},
        {"key": "enable_general_gift",        "label": "普通礼物",          "type": "bool", "default": "true"},
        {"key": "enable_general_appointment", "label": "普通邀约",          "type": "bool", "default": "true"},
        {"key": "enable_chaos_letter",        "label": "短信",              "type": "bool", "default": "true"},
        {"key": "enable_secret_letter",       "label": "秘密信件",          "type": "bool", "default": "true"},
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
        {"key": "dlc_moments",               "label": "朋友圈DLC",         "type": "bool", "default": "false"},
    ]},
    {"section": "邀约", "fields": [
        {"key": "enable_join_existing_appointment", "label": "允许加入已有私约",        "type": "bool",   "default": "false"},
        {"key": "group_expire_hours",               "label": "小群过期（小时）",        "type": "number", "default": "48"},
        {"key": "rest_hours",                       "label": "休息时段（不计弧长）",    "type": "text",   "default": "", "note": "格式 HHMM-HHMM，如 0200-0800，留空不限制"},
        {"key": "appointment_coin_cost",            "label": "私约写信币费用",          "type": "number", "default": "0", "note": "发起私约/电话消耗的写信币数（0=免费）"},
        {"key": "idle_group_name",                  "label": "备用群名",                "type": "text",   "default": "备用", "note": "群结束后修改成的群名，默认为「备用」"},
    ]},
    {"section": "邀约时长（分钟）", "json_parent": "appointment_duration_config", "fields": [
        {"key": "phone",   "label": "电话门槛", "type": "number", "default": "29"},
        {"key": "private", "label": "私密门槛", "type": "number", "default": "59"},
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
        {"key": "forumMaxLength", "label": "帖子/回复字数上限", "type": "number", "default": "500"},
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
        {"key": "poeticSignature",   "label": "诗意署名",      "type": "number", "default": "0",  "min": 0, "max": 100},
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
        {"key": "私密", "label": "私约别名", "type": "text", "default": "", "note": "留空=默认「私密」，群名超6字自动省略"},
        {"key": "电话", "label": "电话别名", "type": "text", "default": "", "note": "留空=默认「电话」"},
        {"key": "官约", "label": "官约别名", "type": "text", "default": "", "note": "留空=默认「官约」"},
        {"key": "微信", "label": "微信别名", "type": "text", "default": "", "note": "留空=默认「微信」"},
        {"key": "心愿", "label": "心愿别名", "type": "text", "default": "", "note": "留空=默认「心愿」"},
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
                result[f["key"]] = flat.get(f["key"], str(f["default"]))
    # 透传 blob 键（机器人以 JSON 字符串形式存储，原样透传）
    for blob_key in ("item_registry", "rpg_attr_defs", "sys_attr_presets",
                     "end_game_bonus_templates", "end_game_draw_config",
                     "custom_message_templates", "preset_gifts",
                     "private_appointment_aliases",
                     "equipment_registry", "equipment_slots", "equipment_slot_names"):
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
            public_view_enabled INTEGER DEFAULT 0,
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
                "VALUES (?,?,1,0,?,?)",
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
        row = db.execute("SELECT id FROM shows WHERE tenant_id=? ORDER BY id", (tid,)).fetchone()
    if row:
        session["view_show_id"] = row["id"]
        return row["id"]
    return None

def get_current_show_id_for_tenant(tenant_id):
    """API 用：找该租户当前活跃季的 ID。"""
    db  = get_db()
    row = db.execute("SELECT id FROM shows WHERE tenant_id=? AND is_current=1", (tenant_id,)).fetchone()
    if not row:
        row = db.execute("SELECT id FROM shows WHERE tenant_id=? ORDER BY id DESC", (tenant_id,)).fetchone()
    return row["id"] if row else None

def get_current_show_for_tenant(tenant_id):
    """API 用：返回当前活跃季的完整行（dict），含档期字段。"""
    db  = get_db()
    row = db.execute("SELECT * FROM shows WHERE tenant_id=? AND is_current=1", (tenant_id,)).fetchone()
    if not row:
        row = db.execute("SELECT * FROM shows WHERE tenant_id=? ORDER BY id DESC", (tenant_id,)).fetchone()
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

    year  = today.year
    start = _parse_mmdd(start_str, year)
    end_str  = show.get("schedule_end") or start_str
    supp_str = show.get("supplement_end") or ""
    # 跨年档期：若 end 的 MMDD < start 的 MMDD，说明 end 在下一年
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

@app.route("/api/new_season", methods=["POST"])
def api_new_season():
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
    # 把已有 is_current=1 的 show 全部关掉（处理 JSCLEAR 未先结束季度的情况）
    db.execute("UPDATE shows SET is_current=0 WHERE tenant_id=? AND is_current=1", (tid,))
    # 建新 show
    token = secrets.token_urlsafe(24)
    db.execute(
        "INSERT INTO shows (tenant_id,name,description,is_current,public_view_enabled,public_token,"
        "created_at,schedule_start,schedule_end,supplement_end) "
        "VALUES (?,?,?,1,0,?,?,?,?,?)",
        (tid, name, mode, token, int(time.time() * 1000),
         sched_start, sched_end, supp_end)
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
        "SELECT id, name, description FROM shows WHERE tenant_id=? AND is_current=1", (tid,)
    ).fetchone()
    if not show:
        # 没有 is_current=1，取最新的
        show = db.execute(
            "SELECT id, name, description FROM shows WHERE tenant_id=? ORDER BY id DESC LIMIT 1", (tid,)
        ).fetchone()
    if not show:
        return jsonify({"ok": False, "error": "no show found"}), 404
    mode = show["description"] if show["description"] in ("review", "no_review") else "review"
    return jsonify({"ok": True, "show_id": show["id"], "name": show["name"], "mode": mode,
                    "schedule_start": show["schedule_start"] or "",
                    "schedule_end":   show["schedule_end"]   or "",
                    "supplement_end": show["supplement_end"] or ""})

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
        "UPDATE shows SET schedule_start=?, schedule_end=?, supplement_end=? WHERE id=?",
        (start, end, supp, show["id"])
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
    db.commit()
    base_url = request.host_url.rstrip("/")
    public_url = f"{base_url}/public/{show['public_token']}" if show["public_token"] else base_url
    return jsonify({"ok": True, "show_id": show["id"], "name": show["name"], "public_url": public_url})

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
    # 找出已结束（end_ts>0）且无任何 rp_entries 的 session
    rows = db.execute("""
        SELECT s.id FROM sessions s
        WHERE s.end_ts > 0
        AND (SELECT count(*) FROM rp_entries e WHERE e.session_id = s.id) = 0
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
                "VALUES (?,?,1,0,?,?)",
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
    tid  = current_tenant_id()
    name = request.form.get("name", "").strip()
    desc = request.form.get("description", "").strip()
    if not name:
        return redirect(url_for("admin_shows") + "?msg=empty_name")
    db  = get_db()
    count = db.execute("SELECT COUNT(*) FROM shows WHERE tenant_id=?", (tid,)).fetchone()[0]
    if count >= 5:
        return redirect(url_for("admin_shows") + "?msg=limit_reached")
    now = int(time.time() * 1000)
    db.execute(
        "INSERT INTO shows (tenant_id,name,description,is_current,public_view_enabled,public_token,created_at) "
        "VALUES (?,?,?,0,0,?,?)",
        (tid, name, desc, secrets.token_urlsafe(24), now)
    )
    db.commit()
    return redirect(url_for("admin_shows") + "?msg=created")

@app.route("/admin/shows/<int:sid>/activate", methods=["POST"])
@require_admin
def admin_show_activate(sid):
    """将指定季设为「当前季」（机器人数据写入此季）。"""
    tid = current_tenant_id()
    db  = get_db()
    if not db.execute("SELECT id FROM shows WHERE id=? AND tenant_id=?", (sid, tid)).fetchone():
        abort(404)
    db.execute("UPDATE shows SET is_current=0 WHERE tenant_id=?", (tid,))
    db.execute("UPDATE shows SET is_current=1 WHERE id=?", (sid,))
    db.commit()
    session.pop("view_show_id", None)
    if request.headers.get("X-Fetch") == "1":
        return jsonify({"ok": True})
    return redirect(url_for("admin_shows") + "?msg=activated")

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
    if not db.execute("SELECT id FROM shows WHERE id=? AND tenant_id=?", (sid, tid)).fetchone():
        abort(404)
    data = request.json or {}
    start = (data.get("schedule_start") or "").strip()
    end   = (data.get("schedule_end")   or "").strip()
    supp  = (data.get("supplement_end") or "").strip()
    # 简单格式校验：空串或 4 位数字
    for v in (start, end, supp):
        if v and (len(v) != 4 or not v.isdigit()):
            return jsonify({"ok": False, "error": f"格式错误：{v}，需为 MMDD 四位数字"}), 400
    db.execute(
        "UPDATE shows SET schedule_start=?, schedule_end=?, supplement_end=? WHERE id=?",
        (start, end, supp, sid)
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

    # 心动信/礼物：收集没有 session_id 的（有 session_id 的已附在各场次文件内）
    nonsession_by_day_type = {}
    for ev in _parse_events(db.execute(
        "SELECT * FROM extra_events WHERE show_id=? AND (session_id IS NULL OR session_id='') AND type != 'sms' ORDER BY timestamp",
        (sid,)
    ).fetchall()):
        day = _fsafe(ev.get("game_day") or "未归档")
        etype = ev.get("type") or "其他"
        nonsession_by_day_type.setdefault((day, etype), []).append(ev)

    _etype_names = {"lovemail": "心动信", "gift": "礼物"}

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

        for (day, etype), evs in sorted(nonsession_by_day_type.items()):
            label = _etype_names.get(etype, etype)
            lines = [f"【 {show_name} · {day} · {label} 】", ""]
            for ev in evs:
                t_str = ts_to_str(ev.get("timestamp", 0)) if ev.get("timestamp") else "—"
                lines.append(f"{t_str}  {ev.get('from_role','')} → {ev.get('to_role','')}")
                if ev.get("content"):
                    lines.append(ev["content"])
                lines.append("")
            zf.writestr(f"{day}/{label}.txt", "\n".join(lines))

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
            "SELECT id FROM shows WHERE tenant_id=? ORDER BY id DESC LIMIT 1", (tid,)
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
        for sec in CONFIG_SCHEMA:
            for f in sec["fields"]:
                db_key = _cfg_db_key(sec, f["key"])
                if f["type"] == "bool":
                    value = "true" if request.form.get(db_key) else "false"
                elif f["type"] == "routing":
                    value = _parse_routing_text(request.form.get(db_key, ""))
                else:
                    value = _strip_json_str(request.form.get(db_key, str(f["default"])))
                new_flat[db_key] = value
        # 保存物品注册表与属性定义（JSON blob，不经过 CONFIG_SCHEMA）
        for blob_key in ("item_registry", "rpg_attr_defs", "sys_attr_presets",
                         "end_game_draw_config",
                         "item_registry_pending", "custom_message_templates",
                         "private_appointment_aliases",
                         "equipment_registry", "equipment_registry_pending",
                         "equipment_slots", "equipment_slot_names"):
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
    equip_registry_json      = flat.get("equipment_registry", "{}")
    equip_pending_json       = flat.get("equipment_registry_pending", "[]")
    equip_slots_json         = flat.get("equipment_slots", '["head","chest","hand","leg","foot"]')
    equip_slot_names_json    = flat.get("equipment_slot_names", "{}")
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
                           equip_registry_json=equip_registry_json,
                           equip_pending_json=equip_pending_json,
                           equip_slots_json=equip_slots_json,
                           equip_slot_names_json=equip_slot_names_json,
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

    return render_template("admin.html",
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
    db = get_db()
    for key, value in data.items():
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

@app.route("/api/pending_items", methods=["GET"])
def api_pending_items():
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    db  = get_db()
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

@app.route("/api/pending_equips", methods=["GET"])
def api_pending_equips():
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    db  = get_db()
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
    if _schedule_zone(show, data.get("timestamp")) == 'pre':
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
    if role_name and cur_ts and not is_npc:
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
    return render_template("admin_groups.html", sets=sets, msg=msg)


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

def _convert_ui_block(blk):
    conds = []
    for c in blk.get('conditions', []):
        param = _PARAM_MAP.get(c.get('param', ''), c.get('param', ''))
        cond = {'param': param, 'op': c.get('op', '>=')}
        if c.get('op') == 'range':
            cond['value'] = [int(c.get('min', 0)), int(c.get('max', 0))]
        else:
            cond['value'] = int(c.get('value', 0))
        conds.append(cond)
    rwds = []
    for r in blk.get('rewards', []):
        rtype = r.get('rtype', '货币')
        reward = {'type': 'fixed', 'amount': int(r.get('amount', 0))}
        prob = r.get('prob')
        if prob is not None and int(prob) < 100:
            reward['prob'] = int(prob)
        if rtype == '货币':
            reward['target'] = r.get('target', '')
            reward['targetType'] = 'currency'
        elif rtype == '道具':
            reward['target'] = r.get('code', '')
            reward['targetType'] = 'item'
        else:
            reward['target'] = r.get('name', '')
            reward['targetType'] = 'attr'
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


@app.route("/admin/rewards", methods=["GET"])
@require_admin
def admin_rewards():
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
    page    = max(1, request.args.get("page", 1, type=int))
    per_page = 30
    total   = db.execute("SELECT COUNT(*) FROM reward_records WHERE show_id=?", (sid,)).fetchone()[0]
    records = db.execute(
        "SELECT * FROM reward_records WHERE show_id=? ORDER BY distributed_at DESC LIMIT ? OFFSET ?",
        (sid, per_page, (page-1)*per_page)
    ).fetchall()
    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template("admin_rewards.html",
                           bonus_templates=bonus_templates,
                           draw_config=draw_config,
                           item_registry=item_registry,
                           aliases=aliases,
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
        enabled = request.form.get("draw_enabled") == "1"
        chance  = max(0, min(100, request.form.get("draw_chance", 0, type=int)))
        count   = max(1, request.form.get("draw_count", 1, type=int))
        val = json.dumps({"enabled": enabled, "chance": chance, "count": count})
        _save_reward_config_key(db, sid, tid, "reward_draw_config", val)
        db.commit()
    elif section == "items":
        raw = request.form.get("item_registry_json","").strip()
        try:
            parsed = json.loads(raw)
            val = json.dumps(parsed, ensure_ascii=False)
        except Exception:
            if request.headers.get("X-Fetch") == "1":
                return jsonify({"ok": False, "error": "json_parse"})
            return redirect(url_for("admin_rewards") + "?err=json")
        # 同时写主注册表（机器人拉取）和兼容 key
        _save_reward_config_key(db, sid, tid, "item_registry", val)
        _save_reward_config_key(db, sid, tid, "reward_item_registry", val)
        db.commit()
        if request.headers.get("X-Fetch") == "1":
            return jsonify({"ok": True})
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
    player_rows = db.execute(
        "SELECT role_name FROM players WHERE show_id=? AND role_name!='' ORDER BY role_name",
        (sid,)
    ).fetchall()
    player_list = [r[0] for r in player_rows]
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
        player_list         = player_list,
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
        "battle_attrs", "attack_defense_config", "player_skills",
    }
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


@app.route("/admin/pools", methods=["GET"])
@require_admin
def admin_pools():
    sid = get_show_id()
    db  = get_db()
    pool_defs, pool_cfg, item_registry = _get_pool_data(db, sid)
    flat = get_flat_config(db, sid)
    attr_defs = json.loads(flat.get("rpg_attr_defs", "{}") or "{}")
    return render_template("admin_pools.html",
                           pool_defs=pool_defs,
                           pool_cfg=pool_cfg,
                           item_registry=item_registry,
                           attr_defs=attr_defs)


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
    for key, val in (("pool_definitions", pool_defs), ("pool_draw_config", pool_cfg)):
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
    return jsonify({"ok": True, "pool_definitions": pool_defs, "pool_draw_config": pool_cfg})


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

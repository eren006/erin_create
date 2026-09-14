"""霍格沃茨养成游戏 · 网页操作台。

所有操作都走这里，和机器人共用同一套引擎函数（plugins/hp_*），不重写业务逻辑。
操作结果实时显示在网页上，同时往通知队列里排一条，由机器人播报到指定的QQ群。

账号=QQ号，管理员批准后才能用，初始密码 88888888。
"""

from __future__ import annotations

import os
import secrets

import nonebot

nonebot.init()  # 只加载配置，让下面的插件模块能正常导入；不注册适配器、不启动机器人

from flask import (  # noqa: E402
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import admin_reset  # noqa: E402
import gossip  # noqa: E402
import newspaper_service  # noqa: E402
import submissions  # noqa: E402
import web_auth  # noqa: E402
from plugins.hp_core import ambient as core_ambient  # noqa: E402
from plugins.hp_core import notify as core_notify  # noqa: E402
from plugins.hp_core import spells as spell_catalog  # noqa: E402
from plugins.hp_core import storage as core_storage  # noqa: E402
from plugins.hp_events import christmas, creatures, duel, forest, gnomes, grading, prefect, quidditch  # noqa: E402
from plugins.hp_school import (  # noqa: E402
    careers,
    casting,
    choc_frog,
    daily_plan,
    homework,
    lesson_events,
    lessons,
    mainline,
    potions,
    shop,
    shop_catalog,
    sorting,
    story_mainline,
    subjects,
    tailor,
    themes,
    work,
)
from plugins.hp_social import friendship, romance
from plugins.hp_social import storage as social_storage  # noqa: E402

web_auth.init_db()
core_notify.init_db()
submissions.init_db()
gossip.init_db()
themes.init_db()

# 首次启动时生成一个管理密码，只在日志里明文出现这一次；之后可以在后台自行修改
if not web_auth.has_admin_password():
    _initial_admin = os.getenv("HOGWARTS_ADMIN_PASSWORD") or secrets.token_urlsafe(9)
    web_auth.set_admin_password(_initial_admin)
    print(f"[霍格沃茨] 已生成管理密码：{_initial_admin}（请保存，仅此一次明文显示）", flush=True)

app = Flask(__name__)
app.secret_key = os.getenv("HOGWARTS_SECRET_KEY") or "hogwarts-dev-secret-change-me"

NEWSPAPER_URL = os.getenv("NEWSPAPER_PUBLIC_URL", "http://120.26.120.128:5017")

ENGINE_ERRORS = (
    christmas.ChristmasError,
    prefect.PrefectError,
    potions.PotionError,
    submissions.SubmissionError,
    gossip.GossipError,
    sorting.SortingError,
    lessons.LessonError,
    lesson_events.LessonEventError,
    homework.HomeworkError,
    shop.ShopError,
    casting.CastError,
    work.WorkError,
    careers.CareerError,
    mainline.MainlineError,
    story_mainline.StoryError,
    daily_plan.DailyPlanError,
    quidditch.QuidditchError,
    duel.DuelError,
    forest.ForestError,
    romance.RomanceError,
    friendship.FriendshipError,
    gnomes.GnomeError,
    creatures.CreatureError,
    tailor.TailorError,
    choc_frog.ChocFrogError,
    themes.ThemeError,
)


# ======================== 登录与权限 ========================


@app.before_request
def _load_user():
    g.account = web_auth.session_user(session.get("token", ""))
    g.uid = g.account["player_uid"] if g.account else None
    g.player = core_storage.get_player(g.uid) if g.uid else None


def _require_login():
    if not g.account:
        return redirect(url_for("login", next=request.path))
    if g.account["must_change_password"] and request.endpoint not in ("password", "logout"):
        flash("初始密码还没改，先设置一个自己的密码。", "warn")
        return redirect(url_for("password"))
    return None


def _require_player():
    """已登录但还没入学的，赶去入学。"""
    guard = _require_login()
    if guard:
        return guard
    if not g.player or not g.player["house"]:
        if request.endpoint != "enroll":
            return redirect(url_for("enroll"))
    return None


def _notify(text: str, category: str = "", merge_key: str = "", amount: int = 1) -> None:
    """排一条待播报。text 里的 {n} 会在汇总时替换成合并后的次数。
    带 merge_key 的会合并同类项（比如连上5节课只占一行）。"""
    core_notify.push(
        text, uid=g.uid or "", category=category, merge_key=merge_key, amount=amount
    )


def _display_name(uid: str | None = None) -> str:
    return core_storage.get_full_name(uid or g.uid)


@app.context_processor
def _inject():
    current_day = core_storage.get_current_day()
    seasonal_theme = themes.seasonal_theme_for_day(current_day)
    personal_theme = themes.get_equipped(g.uid) if g.get("uid") and g.get("player") else ""
    theme_key = seasonal_theme or personal_theme
    return {
        "account": g.get("account"),
        "player": g.get("player"),
        "display_name": _display_name(g.uid) if g.get("uid") and g.get("player") else "",
        "current_day": current_day,
        "newspaper_url": NEWSPAPER_URL,
        "current_theme": theme_key,
        "seasonal_theme": seasonal_theme,
    }


# ======================== 账号 ========================


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        try:
            result = web_auth.request_account(
                request.form.get("uid", ""),
                request.form.get("binding_code", ""),
                request.form.get("note", ""),
            )
            flash(
                f"申请已提交（{result['name']}，{result['house']}）。"
                "等管理员批准后就能登录了，初始密码 88888888。",
                "ok",
            )
            return redirect(url_for("login"))
        except web_auth.AuthError as e:
            flash(str(e), "error")
    return render_template("web/register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            token = web_auth.login(request.form.get("uid", ""), request.form.get("password", ""))
            session["token"] = token
            return redirect(request.args.get("next") or url_for("index"))
        except web_auth.AuthError as e:
            flash(str(e), "error")
    return render_template("web/login.html")


@app.get("/logout")
def logout():
    web_auth.logout(session.pop("token", ""))
    return redirect(url_for("login"))


@app.route("/password", methods=["GET", "POST"])
def password():
    if not g.account:
        return redirect(url_for("login"))
    if request.method == "POST":
        try:
            web_auth.change_password(
                g.account["uid"], request.form.get("old", ""), request.form.get("new", "")
            )
            flash("密码改好了。", "ok")
            return redirect(url_for("index"))
        except web_auth.AuthError as e:
            flash(str(e), "error")
    return render_template("web/password.html")


ADMIN_SESSION_KEY = "admin_ok"


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if web_auth.check_admin_password(request.form.get("password", "")):
            session[ADMIN_SESSION_KEY] = True
            return redirect(url_for("admin"))
        flash("管理密码不对。", "error")
    return render_template("web/admin_login.html")


@app.get("/admin/logout")
def admin_logout():
    session.pop(ADMIN_SESSION_KEY, None)
    return redirect(url_for("admin_login"))


@app.route("/admin/password", methods=["GET", "POST"])
def admin_password():
    if not session.get(ADMIN_SESSION_KEY):
        return redirect(url_for("admin_login"))
    if request.method == "POST":
        try:
            web_auth.change_admin_password(
                request.form.get("old", ""), request.form.get("new", "")
            )
            flash("管理密码已更新。", "ok")
            return redirect(url_for("admin"))
        except web_auth.AuthError as e:
            flash(str(e), "error")
    return render_template("web/admin_password.html")


@app.route("/admin", methods=["GET", "POST"])
def admin():
    """管理后台走独立的密码登录，跟玩家账号完全解耦。"""
    if not session.get(ADMIN_SESSION_KEY):
        return redirect(url_for("admin_login"))
    if request.method == "POST":
        action = request.form.get("action")
        target = request.form.get("uid", "")
        try:
            if action == "approve":
                web_auth.approve(target)
                flash(f"已批准 {target}。", "ok")
            elif action == "reject":
                web_auth.reject(target)
                flash(f"已拒绝 {target}。", "ok")
            elif action == "revoke":
                web_auth.revoke(target)
                flash(f"已停用 {target}。", "ok")
            elif action == "reset":
                web_auth.reset_password(target)
                flash(f"{target} 的密码已重置为 88888888。", "ok")
            elif action == "announce":
                message = request.form.get("message", "").strip()
                if not message:
                    flash("通知内容不能为空。", "error")
                else:
                    from plugins.hp_school import storage as school_storage
                    announcement_id = school_storage.add_group_announcement(message)
                    flash(f"已添加群通知（ID: {announcement_id}），将在下一个时间窗口发送。", "ok")
            elif action == "reset_enrollment":
                identifier = target.strip()
                confirm = request.form.get("confirm_uid", "").strip()
                if confirm != identifier:
                    flash("确认栏没有填一样的内容，为防止误删已取消操作。", "error")
                else:
                    # 没绑定网页账号的人不在下面的账号列表里，管理员大概率只知道角色名字、
                    # 不知道QQ号，所以这里两种都认：纯数字当QQ号，否则按角色名查uid。
                    resolved_uid = (
                        identifier if identifier.isdigit()
                        else core_storage.get_uid_by_name(identifier)
                    )
                    if not resolved_uid:
                        flash(f"「{identifier}」查不到对应的角色，检查一下QQ号或角色名字有没有打对。", "error")
                    else:
                        result = admin_reset.reset_enrollment(resolved_uid)
                        if result["old_house"]:
                            flash(
                                f"已清空 {resolved_uid}（原 {result['old_name']}·{result['old_house']}）"
                                "的入学记录及全部关联数据，本人可在QQ群重新「/入学」。",
                                "ok",
                            )
                        else:
                            flash(f"{resolved_uid} 本来就还没入学，已清空其残留的中间数据。", "ok")
            elif action == "rename_player":
                identifier = target.strip()
                new_name = request.form.get("new_name", "")
                new_surname = request.form.get("new_surname", "")
                resolved_uid = (
                    identifier if identifier.isdigit()
                    else core_storage.get_uid_by_name(identifier)
                )
                if not resolved_uid:
                    flash(f"「{identifier}」查不到对应的角色，检查一下QQ号或角色名字有没有打对。", "error")
                else:
                    result = admin_reset.rename_player(resolved_uid, new_name, new_surname)
                    flash(f"已把 {result['old_name']} 改名为 {result['new_name']}。", "ok")
            elif action == "transfer_house":
                identifier = target.strip()
                new_house = request.form.get("new_house", "").strip()
                confirm = request.form.get("confirm_uid", "").strip()
                if confirm != identifier:
                    flash("确认栏没有填一样的内容，为防止误操作已取消。", "error")
                else:
                    resolved_uid = (
                        identifier if identifier.isdigit()
                        else core_storage.get_uid_by_name(identifier)
                    )
                    if not resolved_uid:
                        flash(f"「{identifier}」查不到对应的角色，检查一下QQ号或角色名字有没有打对。", "error")
                    else:
                        result = admin_reset.transfer_house(resolved_uid, new_house)
                        flash(
                            f"已把 {result['old_name']} 从 {result['old_house']} 转到 {result['new_house']}"
                            f"（清零了TA为{result['old_house']}攒下的{result['cleared_points']}点学院分，"
                            "其余游戏数据不受影响）。",
                            "ok",
                        )
            elif action == "adjust_stat":
                identifier = target.strip()
                stat = request.form.get("stat", "")
                stat_subject = request.form.get("subject", "")
                try:
                    amount = int(request.form.get("amount", "0"))
                except ValueError:
                    amount = 0
                resolved_uid = (
                    identifier if identifier.isdigit()
                    else core_storage.get_uid_by_name(identifier)
                )
                if not resolved_uid:
                    flash(f"「{identifier}」查不到对应的角色，检查一下QQ号或角色名字有没有打对。", "error")
                else:
                    result = admin_reset.adjust_stat(resolved_uid, stat, amount, stat_subject)
                    sign = "+" if result["delta"] > 0 else ""
                    flash(
                        f"已把 {result['name']} 的{result['label']}从 {result['old']} 调整为 {result['new']}"
                        f"（{sign}{result['delta']}）。",
                        "ok",
                    )

        except web_auth.AuthError as e:
            flash(str(e), "error")
        except admin_reset.ResetError as e:
            flash(str(e), "error")
        except Exception as e:
            flash(f"出错：{str(e)}", "error")
        return redirect(url_for("admin"))

    accounts = web_auth.list_accounts()
    for acc in accounts:
        player_uid = acc.get("player_uid") or acc["uid"]
        player = core_storage.get_player(player_uid)
        acc["player_name"] = core_storage.get_full_name(player_uid) if player and player["house"] else ""
        acc["house"] = player["house"] if player else ""
    return render_template(
        "web/admin.html",
        pending=[a for a in accounts if a["status"] == "pending"],
        others=[a for a in accounts if a["status"] != "pending"],
        houses=core_storage.HOUSES,
        subjects=subjects.SUBJECTS,
    )


# ======================== 主页 / 面板 ========================

CAMPUS_FEED_LIMIT = 20


def _relative_time(created_at: int, now_ts: int) -> str:
    elapsed = max(0, now_ts - created_at)
    if elapsed < 60:
        return "刚刚"
    if elapsed < 3600:
        return f"{elapsed // 60}分钟前"
    if elapsed < 86400:
        return f"{elapsed // 3600}小时前"
    return f"{elapsed // 86400}天前"


def _campus_feed(limit: int = CAMPUS_FEED_LIMIT) -> list[dict]:
    """把真实操作记录（notify队列）和闲逛花絮（ambient）按时间混排，做成首页的"校园动态"。"""
    now_ts = core_storage.now()
    entries = [
        {
            "name": core_storage.get_full_name(r["uid"]) if r["uid"] else "",
            "text": r["text"].replace("{n}", str(r["amount"])),
            "created_at": r["created_at"],
        }
        for r in core_notify.list_recent(limit)
    ]
    entries += [
        {
            "name": core_storage.get_full_name(a["uid"]),
            "text": f"出现在{a['location']}，{a['activity']}。",
            "created_at": a["created_at"],
        }
        for a in core_ambient.generate(now_ts)
    ]
    entries.sort(key=lambda e: e["created_at"], reverse=True)
    for e in entries:
        e["relative_time"] = _relative_time(e["created_at"], now_ts)
    return entries[:limit]


@app.get("/")
def index():
    guard = _require_login()
    if guard:
        return guard
    if not g.player or not g.player["house"]:
        return redirect(url_for("enroll"))
    try:
        plan = daily_plan.build(g.uid)
    except ENGINE_ERRORS as e:
        flash(str(e), "error")
        plan = None
    exp_map = core_storage.get_all_subject_exp(g.uid)
    learned = core_storage.list_learned_spells(g.uid)

    christmas_today = christmas.is_christmas(core_storage.get_current_day() or 1)
    feast = None
    if christmas_today:
        pudding_result = christmas.maybe_draw_pending_puddings()
        if pudding_result:
            winner_name = core_storage.get_full_name(pudding_result["winner"])
            _notify(f"🎅 圣诞布丁抽奖：{winner_name} 吃到了藏着的硬币，赢得 {pudding_result['galleons']} 加隆！", "social")
        feast = christmas.feast_state(g.uid)

    exams = core_storage.get_exam_results(g.uid)
    return render_template(
        "web/index.html",
        plan=plan,
        exp_map=exp_map,
        subjects=subjects.SUBJECTS,
        learned_count=len(learned),
        spell_total=len(spell_catalog.SPELLS),
        status_suffix=core_storage.get_status_suffix(g.uid),
        exams=exams,
        exam_grades=sorted({row["grade"] for row in exams}),
        subject_names={k: v[0] for k, v in subjects.SUBJECTS_BY_KEY.items()},
        career=careers.get(g.uid),
        relatives=core_storage.list_relatives(g.uid),
        campus_feed=_campus_feed(),
        christmas_today=christmas_today,
        feast=feast,
    )


# ======================== 入学引导（分院与魔杖只在QQ里做） ========================


@app.get("/enroll")
def enroll():
    """入学和选魔杖必须在QQ群里完成，网页只负责把人引过去。
    这样能保证每个角色都绑在真实QQ号上，选魔杖的按钮体验在QQ里也更好。"""
    guard = _require_login()
    if guard:
        return guard
    if g.player and g.player["house"]:
        return redirect(url_for("index"))

    progress = sorting.resume(g.uid)
    stage = "none"
    if progress:
        stage = "wand" if progress.get("wand_title") else "sorting"
    return render_template("web/enroll.html", stage=stage, progress=progress)


# ======================== 上课 ========================


@app.route("/lessons", methods=["GET", "POST"])
def lessons_page():
    guard = _require_player()
    if guard:
        return guard

    if request.method == "POST":
        try:
            if request.form.get("action") == "start":
                lesson_events.start(g.uid, request.form.get("subject", ""))
            else:
                result = lesson_events.resolve(
                    g.uid, request.form.get("token", ""), int(request.form.get("position", "0"))
                )
                _flash_lesson_result(result)
        except ENGINE_ERRORS as e:
            flash(str(e), "error")
        return redirect(url_for("lessons_page"))

    session_view = None
    try:
        from plugins.hp_school import storage as school_storage

        row = school_storage.get_lesson_session(g.uid)
        if row:
            session_view = lesson_events.start(g.uid, row["subject_key"])
    except ENGINE_ERRORS:
        session_view = None

    day = core_storage.get_current_day() or 1
    unlocked = []
    for key, name, unlock_grade, category in subjects.SUBJECTS:
        if g.player["grade"] < unlock_grade:
            continue
        unlocked.append(
            {
                "key": key,
                "name": name,
                "category": category,
                "is_spell": key in spell_catalog.SPELL_SUBJECTS,
                "today": core_storage.get_lesson_count(g.uid, key, day),
                "scored": core_storage.get_scored_lesson_count(g.uid, key, day),
                "exp": core_storage.get_subject_exp(g.uid, key),
                "next_spell": lessons.next_spell_for(g.uid, key, g.player["grade"]),
                "progress": core_storage.get_spell_progress(g.uid, key),
                "score_preview": grading.preview_score_range(g.uid, key, g.player["grade"]),
            }
        )
    return render_template(
        "web/lessons.html",
        subjects=unlocked,
        session_view=session_view,
        fatigue=core_storage.get_total_scored_lesson_count(g.uid, day),
        fatigue_max=lessons.DAILY_GLOBAL_LIMIT,
        per_subject=lessons.DAILY_LIMIT_PER_SUBJECT,
        lessons_per_spell=spell_catalog.LESSONS_PER_SPELL,
    )


def _flash_lesson_result(result: dict) -> None:
    parts = [result.get("outcome_text") or "这节课上完了。"]
    if result.get("exp_gained"):
        parts.append(f"{result['subject']} +{result['exp_gained']}经验")
    if result.get("friend_bonus"):
        parts.append(f"（含好友同修+{result['friend_bonus']}）")
    subject = result["subject"]
    _notify(f"上了{{n}}节{subject}", "study", merge_key=f"lesson:{subject}")
    if result.get("learned_spell"):
        s = result["learned_spell"]
        parts.append(f"学会了「{s['name']}」")
        _notify(f"学会了「{s['name']}」", "study")
    flash("　".join(parts), "ok")


# ======================== 作业 ========================


@app.route("/homework", methods=["GET", "POST"])
def homework_page():
    guard = _require_player()
    if guard:
        return guard
    if request.method == "POST":
        try:
            result = homework.submit(g.uid, request.form.get("subject", ""))
            if result["success"]:
                _notify("交了{n}份作业", "study", merge_key="homework")
                msg = f"{result['subject']}作业交了，+{result['exp_gained']}经验。"
                if result.get("pity"):
                    msg += f"（试到第{homework.HOMEWORK_PITY_ATTEMPTS}次，保底成功）"
                if result["completion_reward"]:
                    msg += f" 📜 今日作业全部交齐，额外拿到{result['completion_reward']}加隆。"
                flash(msg, "ok")
            else:
                flash(
                    f"「{result['subject']}」这次没做出来，羊皮纸被揉成一团扔进了废纸篓——"
                    f"可以再交一次重试（每次重试扣{homework.HOMEWORK_RETRY_STAMINA_COST}点体力，"
                    f"再试{result['attempts_left_to_pity']}次必过）。",
                    "error",
                )
            if result["overdue_settled"]:
                flash(
                    f"顺手结算了{result['overdue_settled']}门逾期作业，共扣{result['overdue_penalty']}经验"
                    f"（每个缺席日最多扣{homework.HOMEWORK_DAILY_PENALTY_CAP}）。",
                    "warn",
                )
        except ENGINE_ERRORS as e:
            flash(str(e), "error")
        return redirect(url_for("homework_page"))
    try:
        state = homework.list_today(g.uid)
    except ENGINE_ERRORS as e:
        flash(str(e), "error")
        state = {"pending": [], "done": [], "overdue_settled": 0}
    return render_template("web/homework.html", state=state)


# ======================== 商店 / 背包 ========================


@app.route("/themes", methods=["GET", "POST"])
def themes_page():
    guard = _require_player()
    if guard:
        return guard
    if request.method == "POST":
        action = request.form.get("action", "")
        theme_key = request.form.get("theme", "")
        try:
            if action == "buy":
                result = themes.buy(g.uid, theme_key)
                _notify(f"在主题商店买了「{result['name']}」", "economy")
                flash(f"买到了「{result['name']}」，并解锁小游戏《{result['game_name']}》。", "ok")
            elif action == "equip":
                result = themes.equip(g.uid, theme_key)
                flash(f"已经换上「{result['name']}」。", "ok")
            elif action == "classic":
                themes.equip(g.uid, "")
                flash("已经换回学院经典主题。", "ok")
        except ENGINE_ERRORS as e:
            flash(str(e), "error")
        return redirect(url_for("themes_page"))
    return render_template("web/themes.html", themes=themes.list_for(g.uid))


@app.get("/themes/<theme_key>/game")
def theme_game_page(theme_key: str):
    guard = _require_player()
    if guard:
        return guard
    try:
        theme = themes.get_owned_theme(g.uid, theme_key)
    except ENGINE_ERRORS as e:
        flash(str(e), "error")
        return redirect(url_for("themes_page"))
    board = themes.leaderboard(theme_key)
    for row in board:
        row["name"] = _display_name(row["uid"])
        row["is_me"] = row["uid"] == g.uid
    return render_template("web/theme_game.html", theme=theme, leaderboard=board)


@app.post("/themes/<theme_key>/score")
def theme_game_score(theme_key: str):
    guard = _require_player()
    if guard:
        return {"ok": False, "error": "请先登录。"}, 401
    try:
        result = themes.record_score(g.uid, theme_key, request.form.get("score", ""))
        board = themes.leaderboard(theme_key)
        for row in board:
            row["name"] = _display_name(row["uid"])
            row["is_me"] = row["uid"] == g.uid
        return {"ok": True, "result": result, "leaderboard": board}
    except ENGINE_ERRORS as e:
        return {"ok": False, "error": str(e)}, 400


@app.route("/shop", methods=["GET", "POST"])
def shop_page():
    guard = _require_player()
    if guard:
        return guard
    if request.method == "POST":
        try:
            result = shop.buy(g.uid, request.form.get("item", ""))
            _notify(f"在对角巷买了「{result['name']}」", "economy")
            flash(f"买到了「{result['name']}」，花了{result['price']}加隆。", "ok")
        except ENGINE_ERRORS as e:
            flash(str(e), "error")
        return redirect(url_for("shop_page", cat=request.form.get("cat", "")))

    cat = request.args.get("cat") or shop_catalog.CATEGORIES[0]
    if cat not in shop_catalog.CATEGORIES:
        cat = shop_catalog.CATEGORIES[0]
    items = []
    for key, name, category, price, desc, effect in shop.current_offerings(cat):
        item = {"key": key, "name": name, "price": price, "desc": desc}
        if category == "礼物":
            item["stock"] = shop.gift_remaining(key, effect["stock"])
            item["stock_max"] = effect["stock"]
        elif key == choc_frog.FROG_ITEM_KEY:
            item["stock"] = shop.frog_remaining()
            item["stock_max"] = shop.FROG_HOURLY_CAP
        items.append(item)
    return render_template(
        "web/shop.html",
        categories=shop_catalog.CATEGORIES,
        cat=cat,
        items=items,
        rotating=cat in shop_catalog.ROTATING_CATEGORIES,
        next_rotation=shop.seconds_to_next_rotation() // 60 + 1,
        next_restock=shop.seconds_to_next_restock() // 60 + 1,
        frog_cap=shop.FROG_HOURLY_CAP,
    )


@app.route("/bag", methods=["GET", "POST"])
def bag_page():
    guard = _require_player()
    if guard:
        return guard
    if request.method == "POST":
        action = request.form.get("action")
        item = request.form.get("item", "")
        try:
            if action == "eat":
                result = shop.eat_snack(g.uid, item)
                _notify(
                    f"吃了{{n}}份「{result['name']}」补体力", "economy",
                    merge_key=f"eat:{result['name']}",
                )
                text = f"吃了「{result['name']}」，体力+{result['restored']}。"
                card = result.get("card")
                if card:
                    if card["is_new"]:
                        text += f"\n🐸 开出新卡片「{card['name']}」（{card['rarity']}）！"
                    else:
                        text += f"\n🐸 开出「{card['name']}」，已经有了，换成{card['consolation']}加隆安慰奖。"
                    if card["unlocked_titles"]:
                        text += "\n🏅 解锁巧克力蛙称号：" + "、".join(card["unlocked_titles"])
                    text += "\n去「巧克力蛙图鉴」页看看收集进度。"
                if result["cavity_triggered"]:
                    text += f"\n🦷 今天已经吃了{result['eaten_today']}个零食，吃出蛀牙了，体力恢复速度减半，一天后自己好。"
                flash(text, "ok")
            elif action == "sell":
                result = shop.sell(g.uid, item, int(request.form.get("quantity", "1")))
                _notify(
                    f"卖掉了{result['quantity']}份「{result['name']}」，进账{result['total']}加隆",
                    "economy",
                )
                flash(f"卖了{result['quantity']}份「{result['name']}」，得{result['total']}加隆。", "ok")
            elif action == "equip":
                result = quidditch.equip_broom(g.uid, item)
                _notify(f"换上了「{result['name']}」", "quidditch")
                flash(f"装备了「{result['name']}」，耐久{result['durability']}。", "ok")
            elif action == "prank":
                target = _resolve_name(request.form.get("target", ""))
                result = shop.use_prank(g.uid, item, target)
                _notify(
                    f"对 {core_storage.get_full_name(target)} 用了「{result['name']}」——"
                    f"{result['label']}，持续{result['hours']}小时。",
                    "prank",
                )
                flash(f"「{result['name']}」用出去了。", "ok")
        except (ENGINE_ERRORS + (LookupError,)) as e:
            flash(str(e), "error")
        return redirect(url_for("bag_page"))
    return render_template("web/bag.html", items=shop.get_bag(g.uid))


def _resolve_name(name: str) -> str:
    uid = core_storage.get_uid_by_name(name.strip())
    if uid is None:
        raise LookupError(f"学校里没有叫「{name.strip()}」的人。")
    return uid


# ======================== 厨房 ========================

KITCHEN_CATEGORY_NAMES = {
    "breakfast": "🌅 早餐",
    "main": "🍽️ 主食",
    "soup": "🍲 汤类",
    "dessert": "🍰 甜点",
    "magic": "✨ 魔法美食",
    "beverage": "☕ 饮品",
    "snack": "🍪 点心小食",
    "other": "📝 其他",
}
KITCHEN_CATEGORY_ORDER = ["breakfast", "main", "soup", "dessert", "magic", "beverage", "snack", "other"]


@app.route("/kitchen", methods=["GET", "POST"])
def kitchen_page():
    guard = _require_player()
    if guard:
        return guard

    from plugins.hp_school import kitchen

    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "cook_start":
                result = kitchen.start(g.uid, request.form.get("recipe", ""))
                if result.get("resumed"):
                    flash("你还有一份没做完的菜，接着刚才的步骤来。", "ok")
            elif action == "cook_choose":
                position = int(request.form.get("position", "0"))
                result = kitchen.choose(g.uid, position)
                if result.get("finished"):
                    if result["success"]:
                        _notify(f"做出了一份「{result['recipe']}」", "kitchen", merge_key="cook")
                        flash(
                            f"🍳 {result['recipe']} 制作{'完美' if result['perfect'] else '成功'}！"
                            f"（{result['score']}/{result['max_score']}）得到 ×{result['quantity']}，"
                            f"烹饪经验+{result['cooking_exp_gain']}（目前{result['total_cooking_exp']}）。",
                            "ok",
                        )
                        unlocked = kitchen.check_achievements(g.uid)
                        if unlocked:
                            flash("🏅 " + "、".join(unlocked), "ok")
                    else:
                        flash(f"🔥 {result['recipe']} 做失败了：{result['accident']}，材料没能保住。", "warn")
                else:
                    flash(f"已选择第{position}项，进入下一步。", "ok")
            elif action == "consume":
                food_input = request.form.get("food", "")
                result = kitchen.consume(g.uid, food_input)
                found = kitchen.find_any_recipe(food_input)
                if found:
                    kitchen.apply_food_effects(g.uid, found[0])
                flash(f"😋 吃了「{result['recipe']}」，效果：{result['effect']}", "ok")
            elif action == "gift":
                food_input = request.form.get("food", "")
                recipient = request.form.get("recipient", "")
                result = kitchen.gift_food(g.uid, food_input, recipient)
                _notify(f"送了一份「{result['food_name']}」给 {result['recipient_name']}", "kitchen")
                flash(f"🎁 送了一份「{result['food_name']}」给 {result['recipient_name']}。", "ok")
            elif action == "claim_materials":
                granted = kitchen.grant_weekly_materials(g.uid)
                text = "、".join(f"{kitchen.get_material_name(k)}×{v}" for k, v in granted.items())
                flash(f"📦 领到了：{text}", "ok")
            elif action == "forage":
                result = kitchen.forage_material(g.uid)
                flash(f"🔎 探索了一番，找到了一份「{result['material_name']}」！", "ok")
        except (kitchen.KitchenError, ValueError) as e:
            flash(str(e), "error")
        return redirect(url_for("kitchen_page"))

    session_row = kitchen.get_session(g.uid)
    if session_row:
        cook_state = kitchen._render_session(session_row, resumed=True)
        return render_template("web/kitchen.html", cook_state=cook_state)

    player = core_storage.sync_stamina(g.uid)
    exp = core_storage.get_cooking_exp(g.uid)

    day = core_storage.get_current_day() or 1
    conn = core_storage.get_conn()
    try:
        daily_row = conn.execute(
            "SELECT count FROM kitchen_daily WHERE uid=? AND day=?", (g.uid, day)
        ).fetchone()
        cooked_today = daily_row["count"] if daily_row else 0

        pantry_rows = conn.execute(
            "SELECT food_key, quantity FROM kitchen_inventory WHERE uid=? AND quantity>0 ORDER BY food_key",
            (g.uid,),
        ).fetchall()
        material_rows = conn.execute(
            "SELECT item_key, quantity FROM inventory WHERE uid=? AND item_key LIKE 'mat_%' AND quantity>0 "
            "ORDER BY item_key",
            (g.uid,),
        ).fetchall()
    finally:
        conn.close()

    pantry = [
        {"key": row["food_key"], "name": kitchen.item_name(row["food_key"]), "quantity": row["quantity"]}
        for row in pantry_rows
        if kitchen.item_name(row["food_key"])
    ]
    materials = [
        {"key": row["item_key"], "name": kitchen.get_material_name(row["item_key"]), "quantity": row["quantity"]}
        for row in material_rows
    ]
    have_materials = {row["item_key"]: row["quantity"] for row in material_rows}

    recipes_by_category: dict[str, list] = {}
    for key, recipe in kitchen.RECIPES.items():
        cat = recipe.get("category", "other")
        unlocked = g.player["grade"] >= recipe["grade"] and exp >= recipe["exp"]
        ingredients = [
            {
                "name": kitchen.get_material_name(item_key),
                "need": amount,
                "have": have_materials.get(item_key, 0),
            }
            for item_key, amount in recipe["ingredients"].items()
        ]
        can_afford = all(i["have"] >= i["need"] for i in ingredients)
        recipes_by_category.setdefault(cat, []).append(
            {
                "key": key,
                "name": recipe["name"],
                "grade": recipe["grade"],
                "exp": recipe["exp"],
                "effect": recipe["effect"],
                "ingredients": ingredients,
                "unlocked": unlocked,
                "can_afford": can_afford,
            }
        )
    for cat in recipes_by_category:
        recipes_by_category[cat].sort(key=lambda r: (not r["unlocked"], r["grade"], r["exp"]))

    current_festival = kitchen.get_current_festival()
    festival_recipes = []
    if current_festival:
        for key, recipe in kitchen.get_available_festival_foods(current_festival).items():
            unlocked = g.player["grade"] >= recipe["grade"] and exp >= recipe["exp"]
            ingredients = [
                {
                    "name": kitchen.get_material_name(item_key),
                    "need": amount,
                    "have": have_materials.get(item_key, 0),
                }
                for item_key, amount in recipe["ingredients"].items()
            ]
            festival_recipes.append(
                {
                    "key": key,
                    "name": recipe["name"],
                    "grade": recipe["grade"],
                    "exp": recipe["exp"],
                    "effect": recipe["effect"],
                    "ingredients": ingredients,
                    "unlocked": unlocked,
                    "can_afford": all(i["have"] >= i["need"] for i in ingredients),
                }
            )

    return render_template(
        "web/kitchen.html",
        cook_state=None,
        cooking_exp=exp,
        stamina=player["stamina"],
        stamina_max=core_storage.STAMINA_MAX,
        cook_cost=kitchen.COOK_STAMINA_COST,
        forage_cost=kitchen.FORAGE_STAMINA_COST,
        cooked_today=cooked_today,
        daily_limit=kitchen.DAILY_LIMIT,
        pantry=pantry,
        materials=materials,
        current_festival=current_festival,
        festival_recipes=festival_recipes,
        category_order=KITCHEN_CATEGORY_ORDER,
        category_names=KITCHEN_CATEGORY_NAMES,
        recipes_by_category=recipes_by_category,
        chef_leaderboard=kitchen.chef_leaderboard(),
    )


# ======================== 裁缝铺（马金夫人长袍店） ========================


@app.route("/tailor", methods=["GET", "POST"])
def tailor_page():
    guard = _require_player()
    if guard:
        return guard

    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "take_lesson":
                result = tailor.take_lesson(g.uid)
                flash(
                    f"上完了这堂缝纫课，缝纫等级到{result['level']}级了。"
                    + ("已经满级！" if result["maxed"] else ""),
                    "ok",
                )
            elif action == "buy_pattern":
                result = tailor.buy_pattern(g.uid, request.form.get("pattern", ""))
                flash(f"花{result['price']}加隆学会了「{result['name']}」的裁剪方法。", "ok")
            elif action == "craft":
                result = tailor.craft(g.uid, request.form.get("pattern", ""))
                if result.get("is_new_design"):
                    _notify(result["notify_text"], "fashion")
                    flash(
                        f"🧵 做出了一件「{result['name']}」，第一次做出这个款式，"
                        f"时尚值+{result['fashion_gain']}！",
                        "ok",
                    )
                else:
                    _notify(f"做出了一件「{result['name']}」", "kitchen", merge_key="tailor_craft")
                    flash(f"🧵 做出了一件「{result['name']}」，放进了衣橱。", "ok")
            elif action == "list_for_sale":
                result = tailor.list_for_sale(g.uid, request.form.get("clothing", ""))
                flash(f"「{result['name']}」上架了，等客人来买。", "ok")
            elif action == "wear":
                result = tailor.wear(g.uid, request.form.get("clothing", ""))
                _notify(result["notify_text"], "fashion")
                flash(f"你穿上了「{result['name']}」，风头都被你抢了。", "ok")
        except ENGINE_ERRORS as e:
            flash(str(e), "error")
        return redirect(url_for("tailor_page"))

    listings_data = tailor.my_listings(g.uid)
    for event in listings_data["sold_events"]:
        flash(f"🎉 摊位上的「{event['name']}」被客人买走了，进账{event['amount']}加隆！", "ok")

    player = core_storage.sync_stamina(g.uid)
    return render_template(
        "web/tailor.html",
        status=tailor.status(g.uid),
        stamina=player["stamina"],
        stamina_max=core_storage.STAMINA_MAX,
        lesson_cost=tailor.LESSON_STAMINA_COST,
        pattern_groups=tailor.patterns_by_slot(g.uid),
        wardrobe=tailor.my_wardrobe(g.uid),
        listings=listings_data["listings"],
        sold_today=listings_data["sold_today"],
        sale_daily_limit=listings_data["sale_daily_limit"],
        leaderboard=tailor.leaderboard(),
        fashion_leaderboard=tailor.fashion_leaderboard(),
    )


# ======================== 魔咒 ========================


@app.route("/spells", methods=["GET", "POST"])
def spells_page():
    guard = _require_player()
    if guard:
        return guard
    if request.method == "POST":
        try:
            result = casting.cast(g.uid, request.form.get("spell", ""))
            _notify(f"施放了「{result['spell']}」", "study", merge_key=f"cast:{result['spell']}")
            if "cleared" in result:
                flash(f"「{result['spell']}」——{'、'.join(result['cleared'])}都清干净了。", "ok")
            else:
                flash(f"「{result['spell']}」——{result['name']}修好了，耐久回到{result['after']}。", "ok")
        except ENGINE_ERRORS as e:
            flash(str(e), "error")
        return redirect(url_for("spells_page"))

    learned = core_storage.list_learned_spells(g.uid)
    groups = []
    for subject_key in spell_catalog.SPELL_SUBJECTS:
        rows = []
        for skey, name, latin, _, min_grade, category, desc in spell_catalog.spells_of_subject(subject_key):
            rows.append(
                {
                    "key": skey,
                    "name": name,
                    "latin": latin,
                    "category": category,
                    "desc": desc,
                    "learned": skey in learned,
                    "locked": min_grade > g.player["grade"],
                    "min_grade": min_grade,
                }
            )
        target = lessons.next_spell_for(g.uid, subject_key, g.player["grade"])
        groups.append(
            {
                "subject": subjects.SUBJECTS_BY_KEY[subject_key][0],
                "rows": rows,
                "target": target[1] if target else "",
                "progress": core_storage.get_spell_progress(g.uid, subject_key),
            }
        )
    forest_rows = [
        {
            "key": s[0],
            "name": s[1],
            "latin": s[2],
            "category": s[5],
            "desc": s[6],
            "learned": s[0] in learned,
        }
        for s in spell_catalog.spells_of_subject(spell_catalog.FOREST_SUBJECT)
    ]
    return render_template(
        "web/spells.html",
        groups=groups,
        forest_rows=forest_rows,
        castable=casting.CASTABLE,
        lessons_per_spell=spell_catalog.LESSONS_PER_SPELL,
        learned_count=len(learned),
        total=len(spell_catalog.SPELLS),
    )


# ======================== 打工 ========================


@app.route("/work", methods=["GET", "POST"])
def work_page():
    guard = _require_player()
    if guard:
        return guard
    if request.method == "POST":
        try:
            result = work.work(g.uid, request.form.get("job", ""))
            _notify("打了{n}份工", "economy", merge_key="work")
            flash(
                f"🧹 {result['job']}：{result['story']}\n"
                f"工资+{result['earnings']}加隆（现有{result['galleons']}加隆），"
                f"今天已打工{result['count']}/{result['daily_limit']}次。",
                "ok",
            )
        except ENGINE_ERRORS as e:
            flash(str(e), "error")
        return redirect(url_for("work_page"))
    return render_template("web/work.html", jobs=work.available_jobs(g.player["grade"]))


# ======================== 魁地奇 ========================


@app.route("/quidditch", methods=["GET", "POST"])
def quidditch_page():
    guard = _require_player()
    if guard:
        return guard
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "join":
                result = quidditch.become_player(g.uid, request.form.get("position", ""))
                _notify(f"成为了{g.player['house']}魁地奇队的{result['position']}", "quidditch")
                flash(f"你成为了{result['position']}。", "ok")
            elif action == "challenge":
                result = quidditch.challenge_position(g.uid, request.form.get("position", ""))
                if result["win"]:
                    _notify(
                        f"在队内选拔中击败了 "
                        f"{core_storage.get_full_name(result['opponent'])}，拿下了{result['position']}的位置",
                        "quidditch",
                    )
                flash(("PK成功！" if result["win"] else "PK失败。") + f"判定{result['chance']:.2f}", "ok")
            elif action == "switch":
                result = quidditch.switch_position(g.uid, request.form.get("position", ""))
                if result["swapped_with"]:
                    partner = core_storage.get_full_name(result["swapped_with"])
                    _notify(
                        f"和{partner}对调了位置，从{result['old_position']}换到了"
                        f"{g.player['house']}魁地奇队的{result['position']}",
                        "quidditch",
                    )
                    flash(
                        f"已经和 {partner} 对调位置：你从「{result['old_position']}」"
                        f"换到「{result['position']}」。",
                        "ok",
                    )
                else:
                    _notify(
                        f"从{result['old_position']}换到了{g.player['house']}魁地奇队的{result['position']}",
                        "quidditch",
                    )
                    flash(f"已经从「{result['old_position']}」换到「{result['position']}」。", "ok")
            elif action == "train":
                result = quidditch.train(g.uid)
                _notify("训练了{n}次魁地奇", "quidditch", merge_key="qtrain")
                flash(f"训练完成，{result['stat']}+{result['gain']}。", "ok")
            elif action == "match":
                result = quidditch.simulate_match(g.uid, g.player["house"])
                winner = result["winner"] or "打平"
                _notify(
                    f"🧹 魁地奇：{result['house_a']} {result['score_a']} : {result['score_b']} "
                    f"{result['house_b']}，{winner}"
                    + (f"，学院分+{quidditch.MATCH_WIN_HOUSE_POINTS}" if result["winner"] else ""),
                    "quidditch",
                )
                flash(
                    "\n".join(result["log"])
                    + f"\n\n最终比分：{result['house_a']} {result['score_a']} : "
                    f"{result['score_b']} {result['house_b']}",
                    "ok",
                )
        except ENGINE_ERRORS as e:
            flash(str(e), "error")
        return redirect(url_for("quidditch_page"))

    from plugins.hp_events import storage as events_storage

    me = events_storage.get_quidditch_player(g.uid)
    day = core_storage.get_current_day() or 1
    daily = events_storage.get_daily(g.uid, day) if me else None
    rosters = {house: quidditch.get_roster(house) for house in core_storage.HOUSES}
    match_totals = events_storage.house_total_matches_all()
    return render_template(
        "web/quidditch.html",
        me=me,
        daily=daily,
        rosters=rosters,
        positions=quidditch.POSITIONS,
        stat_labels=quidditch.STAT_LABELS,
        stat_keys=quidditch.STAT_KEYS,
        houses=core_storage.HOUSES,
        flying_threshold=quidditch.FLYING_THRESHOLD,
        flying_exp=core_storage.get_subject_exp(g.uid, quidditch.FLYING_SUBJECT_KEY),
        mvps={h: quidditch.get_mvp(h) for h in core_storage.HOUSES},
        position_desc={pos: quidditch.position_desc(pos) for pos in quidditch.POSITIONS},
        name_of=core_storage.get_full_name,
        house_total_matches={h: match_totals.get(h, 0) for h in core_storage.HOUSES},
        house_today_matches={h: events_storage.get_house_daily_matches(h, day) for h in core_storage.HOUSES},
        house_daily_limit=quidditch.MATCH_HOUSE_DAILY_LIMIT,
    )


# ======================== 决斗 ========================


@app.route("/duel", methods=["GET", "POST"])
def duel_page():
    guard = _require_player()
    if guard:
        return guard
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "challenge":
                target = _resolve_name(request.form.get("target", ""))
                duel.challenge(g.uid, target)
                _notify(
                    f"向 {core_storage.get_full_name(target)} 发起了决斗！"
                    f"（对方可以在网页上应战或拒绝）",
                    "duel",
                )
                flash("战书已下。", "ok")
            elif action == "withdraw":
                duel.withdraw(g.uid)
                flash("已撤回。", "ok")
            elif action == "accept":
                challenger = request.form.get("challenger", "")
                duel.accept(g.uid, challenger)
                _notify(
                    f"接受了 {core_storage.get_full_name(challenger)} 的决斗",
                    "duel",
                )
                flash("决斗开始！", "ok")
            elif action == "decline":
                duel.decline(g.uid, request.form.get("challenger", ""))
                flash("已拒绝。", "ok")
            elif action == "cast":
                result = duel.cast(g.uid, request.form.get("spell", ""))
                _flash_duel(result)
            elif action == "skip":
                duel.skip(g.uid)
                flash("这一回合什么都没做。", "ok")
            elif action == "flee":
                result = duel.flee(g.uid)
                _notify(
                    f"在决斗中逃跑了，"
                    f"{core_storage.get_full_name(result['opponent'])} 获胜",
                    "duel",
                )
                flash("你逃跑了。", "warn")
        except (ENGINE_ERRORS + (LookupError,)) as e:
            flash(str(e), "error")
        return redirect(url_for("duel_page"))

    from plugins.hp_events import storage as events_storage

    state = None
    try:
        state = duel.get_state(g.uid)
    except ENGINE_ERRORS:
        state = None
    return render_template(
        "web/duel.html",
        state=state,
        my_challenge=events_storage.get_challenge_by_challenger(g.uid),
        incoming=events_storage.list_challenges_to(g.uid),
        full_name=core_storage.get_full_name,
        min_grade=spell_catalog.DUEL_MIN_GRADE,
    )


def _flash_duel(result: dict) -> None:
    parts = [f"{result['spell']}！"]
    if result["countered"]:
        parts.append("克制成功")
    if result["damage"]:
        parts.append(f"造成{result['damage']}伤害")
    if result["shield_gain"]:
        parts.append(f"获得{result['shield_gain']}护盾")
    flash("　".join(parts), "ok")
    if result.get("finished"):
        winner = result["winner"]
        if winner == g.uid:
            _notify(
                f"赢下了与 "
                f"{core_storage.get_full_name(result['loser'])} 的决斗（{result['reason']}），"
                f"{result['winner_house']}学院分+{result['house_points']}",
                "duel",
            )
        elif winner:
            _notify(
                f"输给了 {core_storage.get_full_name(winner)}"
                f"（{result['reason']}）",
                "duel",
            )
        else:
            _notify("的决斗以平局收场", "duel")


# ======================== 禁林 ========================


@app.route("/forest", methods=["GET", "POST"])
def forest_page():
    guard = _require_player()
    if guard:
        return guard
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "enter":
                result = forest.enter(g.uid)
                _notify("溜进了禁林", "forest")
                flash(f"第1层：{result['monster']}", "ok")
            elif action == "cast":
                result = forest.cast(g.uid, request.form.get("spell", ""))
                _flash_forest(result)
            elif action == "skip":
                forest.skip(g.uid)
                flash("你屏住呼吸，什么都没做。", "warn")
            elif action == "deeper":
                result = forest.go_deeper(g.uid)
                _notify(f"往禁林更深处走到了第{result['depth']}层", "forest")
                flash(f"第{result['depth']}层：{result['monster']}", "ok")
            elif action == "retreat":
                result = forest.retreat(g.uid)
                _notify(
                    f"从禁林第{result['depth']}层平安返回，"
                    f"带回{result['galleons']}加隆"
                    + (f"和{'、'.join(result['materials'])}" if result["materials"] else ""),
                    "forest",
                )
                flash(f"撤退成功，落袋{result['galleons']}加隆。", "ok")
        except ENGINE_ERRORS as e:
            flash(str(e), "error")
        return redirect(url_for("forest_page"))

    state = None
    try:
        state = forest.get_state(g.uid)
    except ENGINE_ERRORS:
        state = None
    from plugins.hp_events import storage as events_storage

    day = core_storage.get_current_day() or 1
    return render_template(
        "web/forest.html",
        state=state,
        bestiary=forest.bestiary(g.uid),
        runs_today=events_storage.get_forest_daily(g.uid, day),
        daily_limit=forest.DAILY_LIMIT,
        stamina_cost=forest.STAMINA_COST,
        has_lumos=core_storage.has_spell(g.uid, forest.LUMOS_KEY),
    )


def _flash_forest(result: dict) -> None:
    parts = [f"{result['spell']}！"]
    if result["countered"]:
        parts.append("克制成功")
    if result["resisted"]:
        parts.append("但它几乎不为所动")
    if result["damage"]:
        parts.append(f"造成{result['damage']}伤害")
    flash("　".join(parts), "ok")
    if result.get("monster_down"):
        msg = f"打倒了{result['monster']}！"
        if result.get("learned_spell"):
            s = result["learned_spell"]
            msg += f" 学会了「{s['name']}」"
            _notify(f"在禁林打倒了{result['monster']}，学会了「{s['name']}」", "forest")
        pattern_learned = result.get("loot", {}).get("pattern_learned")
        if pattern_learned:
            msg += f" 🧵 还捡到一张图纸，学会了「{pattern_learned}」的裁剪方法！"
            _notify(f"在禁林捡到裁缝图纸，学会了「{pattern_learned}」", "forest")
        flash(msg, "ok")
    if result.get("defeated"):
        _notify(f"在禁林第{result['depth']}层倒下了，这趟的收获全丢了", "forest")
        flash("你倒下了，这趟的收获全丢了。", "error")


# ======================== 抓地精（二年级限时活动） ========================


@app.route("/gnomes", methods=["GET", "POST"])
def gnomes_page():
    guard = _require_player()
    if guard:
        return guard

    if request.method == "POST":
        try:
            result = gnomes.catch(g.uid)
            if result["success"]:
                _notify(f"抓到了一只{result['tier']}，赚了{result['reward']}加隆", "economy")
                flash(f"{result['line']}　抓到了「{result['tier']}」，+{result['reward']}加隆。", "ok")
            else:
                flash(result["line"], "warn")
        except ENGINE_ERRORS as e:
            flash(str(e), "error")
        return redirect(url_for("gnomes_page"))

    from plugins.hp_events import storage as events_storage

    day = core_storage.get_current_day() or 1
    return render_template(
        "web/gnomes.html",
        is_open=gnomes.is_open(day),
        start_day=gnomes.GNOME_START_DAY,
        end_day=gnomes.GNOME_END_DAY,
        cooldown_remaining=gnomes.get_cooldown_remaining(g.uid),
        my_total=events_storage.get_gnome_total(g.uid),
        my_today=events_storage.get_gnome_daily(g.uid, day),
        leaderboard=gnomes.leaderboard(20),
        house_leaderboard=gnomes.house_leaderboard(),
        full_name=core_storage.get_full_name,
    )


# ======================== 照料神奇生物（三年级限时活动） ========================


@app.route("/creatures", methods=["GET", "POST"])
def creatures_page():
    guard = _require_player()
    if guard:
        return guard

    if request.method == "POST":
        try:
            result = creatures.tend(g.uid)
            if result["success"]:
                _notify(f"照料了一只{result['tier']}，赚了{result['reward']}加隆", "economy")
                msg = f"{result['line']}　照顾好了「{result['tier']}」，+{result['reward']}加隆。"
            else:
                msg = result["line"]
            rare_pet = result.get("rare_pet")
            if rare_pet:
                _notify(f"照料神奇生物时意外收服了一只{rare_pet['name']}", "economy")
                msg += (
                    f"\n\n{rare_pet['line']}\n"
                    f"「{rare_pet['name']}」已经放进你的背包，发「/领养宠物 {rare_pet['name']}」正式收养吧。"
                )
            flash(msg, "ok" if (result["success"] or rare_pet) else "warn")
        except ENGINE_ERRORS as e:
            flash(str(e), "error")
        return redirect(url_for("creatures_page"))

    from plugins.hp_events import storage as events_storage

    day = core_storage.get_current_day() or 1
    return render_template(
        "web/creatures.html",
        is_open=creatures.is_open(day),
        start_day=creatures.CREATURE_START_DAY,
        end_day=creatures.CREATURE_END_DAY,
        cooldown_remaining=creatures.get_cooldown_remaining(g.uid),
        my_total=events_storage.get_creature_total(g.uid),
        my_today=events_storage.get_creature_daily(g.uid, day),
        leaderboard=creatures.leaderboard(20),
        full_name=core_storage.get_full_name,
    )


# ======================== 寝室 ========================


@app.route("/dorm", methods=["GET", "POST"])
def dorm_page():
    guard = _require_player()
    if guard:
        return guard

    from plugins.hp_social import dorm, garden

    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "invite":
                target = _resolve_name(request.form.get("target", ""))
                dorm.invite(g.uid, target)
                flash(f"已向 {core_storage.get_full_name(target)} 发出同寝邀请。", "ok")
            elif action == "withdraw":
                dorm.withdraw(g.uid)
                flash("已撤回邀请。", "ok")
            elif action == "decline":
                dorm.decline(g.uid, request.form.get("from_uid", ""))
                flash("已拒绝。", "ok")
            elif action == "accept":
                result = dorm.accept(g.uid, request.form.get("from_uid", ""))
                _notify(f"和 {core_storage.get_full_name(result['roommate'])} 同住一间寝室了", "social")
                flash(f"搬进了「{result['name']}」，室友是 {core_storage.get_full_name(result['roommate'])}。", "ok")
            elif action == "leave":
                result = dorm.leave(g.uid)
                flash(f"退出了寝室，和 {core_storage.get_full_name(result['roommate'])} 各自安好。", "warn")
            elif action == "rename":
                result = dorm.rename(g.uid, request.form.get("name", ""))
                flash(f"寝室改名为「{result['name']}」。", "ok")
            elif action == "garden_forage":
                result = garden.forage(g.uid)
                flash(f"{result['line']} 现在手上有{result['seeds']}颗种子。", "ok")
            elif action == "garden_plant":
                result = garden.plant(g.uid)
                flash(f"种下了一颗种子，大约{result['grow_hours']}小时后可以收获。", "ok")
            elif action == "garden_harvest":
                result = garden.harvest(g.uid)
                if result["success"]:
                    flash(f"🪴 花盆里长出了一株「{result['plant_name']}」！已经摆进了花园。", "ok")
                else:
                    flash(result["line"], "warn")
        except (dorm.DormError, garden.GardenError, LookupError) as e:
            flash(str(e), "error")
        return redirect(url_for("dorm_page"))

    conn = core_storage.get_conn()
    try:
        incoming = conn.execute(
            "SELECT * FROM dorm_invites WHERE to_uid = ? ORDER BY created_at", (g.uid,)
        ).fetchall()
        my_outgoing_invite = conn.execute(
            "SELECT * FROM dorm_invites WHERE from_uid = ?", (g.uid,)
        ).fetchone()
    finally:
        conn.close()

    return render_template(
        "web/dorm.html",
        my_dorm=dorm.get_my_dorm(g.uid),
        incoming_invites=incoming,
        my_outgoing_invite=my_outgoing_invite,
        leaderboard=dorm.leaderboard(),
        pots=garden.list_pots(g.uid),
        garden_status=garden.status(g.uid),
        full_name=core_storage.get_full_name,
    )


# ======================== 邮件 ========================


@app.route("/mail", methods=["GET", "POST"])
def mail_page():
    guard = _require_player()
    if guard:
        return guard

    from plugins.hp_social import mail

    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "send":
                target = _resolve_name(request.form.get("target", ""))
                item_input = request.form.get("item", "")
                quantity = int(request.form.get("quantity", "1") or "1")
                result = mail.send(
                    g.uid, target, request.form.get("content", ""), item_input, quantity
                )
                if result["item_name"]:
                    flash(
                        f"信寄给了 {result['target_name']}，还捎带了{result['quantity']}份「{result['item_name']}」。",
                        "ok",
                    )
                else:
                    flash(f"信寄给了 {result['target_name']}。", "ok")
        except (mail.MailError, LookupError, ValueError) as e:
            flash(str(e), "error")
        return redirect(url_for("mail_page"))

    return render_template(
        "web/mail.html",
        letters=mail.inbox(g.uid),
        bag_items=[item for item in shop.get_bag(g.uid) if item["quantity"] > 0],
    )


# ======================== 社交 ========================


@app.route("/social", methods=["GET", "POST"])
def social_page():
    guard = _require_player()
    if guard:
        return guard
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "gift":
                target = _resolve_name(request.form.get("target", ""))
                result = romance.send_gift(g.uid, request.form.get("item", ""), target)
                _notify(
                    f"送了 {core_storage.get_full_name(target)} 一份「{result['name']}」", "social"
                )
                flash(f"送出「{result['name']}」，好感+{result['gain']}。", "ok")
            elif action == "flirt":
                target = _resolve_name(request.form.get("target", ""))
                result = romance.flirt(g.uid, target)
                flash(f"{result['line']}　好感+{result['gain']}", "ok")
            elif action == "confess":
                target = _resolve_name(request.form.get("target", ""))
                romance.confess(g.uid, target)
                _notify(
                    f"和 {core_storage.get_full_name(target)} 在一起了！", "social"
                )
                flash("在一起了！", "ok")
            elif action == "date":
                result = romance.go_on_date(g.uid, request.form.get("activity", ""))
                _notify(
                    f"和 {core_storage.get_full_name(result['partner'])} 去了{result['activity']}",
                    "social",
                )
                flash(f"约会愉快，双方好感+{result['affection_gain']}。", "ok")
            elif action == "breakup":
                result = romance.break_up(g.uid)
                _notify(
                    f"和 {core_storage.get_full_name(result['partner'])} 分手了", "social"
                )
                flash("分手了。", "warn")
            elif action == "interfere":
                target = _resolve_name(request.form.get("target", ""))
                result = romance.interfere(g.uid, target)
                if result["success"]:
                    _notify(
                        f"💔 {core_storage.get_full_name(target)} 和 "
                        f"{core_storage.get_full_name(result['rival'])} 分手了，据说和TA有关",
                        "social",
                    )
                flash("插足成功。" if result["success"] else "插足失败，对方很不高兴。", "ok")
            elif action == "hangout":
                target = _resolve_name(request.form.get("target", ""))
                result = friendship.hang_out(g.uid, target)
                flash(f"{result['line']}　友谊值都+{result['gain']}", "ok")
            elif action == "friend_gift":
                target = _resolve_name(request.form.get("target", ""))
                result = friendship.send_gift(g.uid, request.form.get("item", ""), target)
                _notify(
                    f"送了 {core_storage.get_full_name(target)} 一份「{result['name']}」（友情）", "social"
                )
                flash(f"送出「{result['name']}」，友谊值+{result['gain']}。", "ok")
        except (ENGINE_ERRORS + (LookupError,)) as e:
            flash(str(e), "error")
        return redirect(url_for("social_page"))

    state = romance.my_romance(g.uid)
    friend_state = friendship.my_friends(g.uid)
    gifts = [
        {"name": name, "price": price, "affection": effect["affection"]}
        for _, name, cat, price, _, effect in shop_catalog.list_by_category("礼物")
    ]
    owned = {i["name"] for i in shop.get_bag(g.uid)}
    owned_gifts = [gift for gift in gifts if gift["name"] in owned]
    return render_template(
        "web/social.html",
        state=state,
        friend_state=friend_state,
        gifts=owned_gifts,
        activities=romance.DATE_ACTIVITIES,
        affection_max=romance.AFFECTION_MAX,
        confess_threshold=romance.CONFESS_THRESHOLD,
        friend_max=friendship.FRIEND_MAX,
        full_name=core_storage.get_full_name,
        name_of=core_storage.get_name,
        couples=social_storage.list_all_couples(),
    )


# ======================== 成长册 / 职业 ========================


@app.route("/mainline", methods=["GET", "POST"])
def mainline_page():
    guard = _require_player()
    if guard:
        return guard
    if request.method == "POST" and request.form.get("action") == "story_choice":
        try:
            result = story_mainline.choose(g.uid, request.form.get("choice", ""))
            flash(
                f"你选择了「{result['text']}」，获得{result['reward']}加隆。"
                + (" 本阶段已经推进。" if result["advanced"] else ""),
                "ok",
            )
            _notify(f"参与了《{story_mainline.STORY_TITLE}》阶段任务", "story")
        except ENGINE_ERRORS as e:
            flash(str(e), "error")
        return redirect(url_for("mainline_page"))
    try:
        book = mainline.open_book(g.uid)
    except ENGINE_ERRORS as e:
        flash(str(e), "error")
        book = None
    try:
        story_task = story_mainline.task_for(g.uid)
        story_progress = story_mainline.progress(g.uid)
    except ENGINE_ERRORS as e:
        flash(str(e), "error")
        story_task = None
        story_progress = None
    return render_template(
        "web/mainline.html", book=book, story_task=story_task, story_progress=story_progress,
        story_title=story_mainline.STORY_TITLE, ending_names=story_mainline.ENDING_NAMES,
        tag_names=story_mainline.TAG_NAMES,
    )


@app.route("/careers", methods=["GET", "POST"])
def careers_page():
    guard = _require_player()
    if guard:
        return guard
    if request.method == "POST":
        try:
            result = careers.choose(g.uid, request.form.get("career", ""))
            _notify(f"毕业后成为了{result['name']}", "career")
            flash(f"你成为了{result['name']}。", "ok")
        except ENGINE_ERRORS as e:
            flash(str(e), "error")
        return redirect(url_for("careers_page"))
    return render_template(
        "web/careers.html", options=careers.list_options(g.uid), chosen=careers.get(g.uid)
    )


# ======================== 巧克力蛙图鉴 ========================


@app.route("/choc-frog", methods=["GET", "POST"])
def choc_frog_page():
    guard = _require_player()
    if guard:
        return guard
    if request.method == "POST":
        try:
            name = choc_frog.wear_title(g.uid, request.form.get("title", ""))
            flash(f"已经佩戴称号「{name}」。", "ok")
        except ENGINE_ERRORS as e:
            flash(str(e), "error")
        return redirect(url_for("choc_frog_page"))
    return render_template(
        "web/choc_frog.html",
        collection=choc_frog.my_collection(g.uid),
        rarity_order=choc_frog.RARITY_ORDER,
        titles=choc_frog.title_state(g.uid),
    )


# ======================== 魔药 ========================


@app.route("/potions", methods=["GET", "POST"])
def potions_page():
    guard = _require_player()
    if guard:
        return guard
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "start":
                potions.start(g.uid, request.form.get("recipe", ""))
            elif action == "choose":
                # potions.choose 收的是 1/2/3，不是从0开始的下标
                result = potions.choose(g.uid, int(request.form.get("position", "1")))
                if result.get("finished"):
                    _flash_potion_result(result)
            elif action == "abandon":
                if potions.abandon(g.uid):
                    flash("你把坩埚里的东西倒掉了，材料和体力不退。", "warn")
            elif action == "use":
                # 复方汤剂要指定变身对象，其他药剂不用
                target_name = request.form.get("target", "").strip()
                target_uid = _resolve_name(target_name) if target_name else None
                result = potions.use(g.uid, request.form.get("potion", ""), target_uid)
                _flash_potion_use(result)
            elif action == "gift":
                target_uid = _resolve_name(request.form.get("target", ""))
                result = potions.gift(
                    g.uid,
                    target_uid,
                    request.form.get("potion", ""),
                    int(request.form.get("quantity", "1")),
                )
                _notify(
                    f"送了 {result['target_name']} {result['quantity']}瓶{result['name']}",
                    "social",
                )
                flash(
                    f"送出{result['quantity']}瓶「{result['name']}」给 {result['target_name']}"
                    f"（今天送了{result['today_count']}/{result['daily_limit']}次）。",
                    "ok",
                )
            elif action == "wear_title":
                name = potions.wear_title(g.uid, request.form.get("title", ""))
                _notify(f"戴上了「{name}」的称号", "study")
                flash(f"称号已换成「{name}」。", "ok")
        except (ENGINE_ERRORS + (ValueError, LookupError)) as e:
            flash(str(e), "error")
        return redirect(url_for("potions_page"))

    session_row = potions.get_session(g.uid)
    brewing = None
    if session_row:
        brewing = potions.start(g.uid, "")  # 有进行中的坩埚时会原样返回当前这一步
    catalog = potions.list_recipes(g.uid)
    owned = {}
    for item in shop.get_bag(g.uid):
        owned[item["name"]] = item["quantity"]
    day = core_storage.get_current_day() or 1
    conn = core_storage.get_conn()
    try:
        row = conn.execute(
            "SELECT count FROM potion_daily WHERE uid = ? AND day = ?", (g.uid, day)
        ).fetchone()
        brewed_today = row["count"] if row else 0
    finally:
        conn.close()

    conn = core_storage.get_conn()
    try:
        row = conn.execute(
            "SELECT count FROM potion_trade_daily WHERE uid = ? AND day = ?", (g.uid, day)
        ).fetchone()
        gifted_today = row["count"] if row else 0
    except Exception:
        gifted_today = 0
    finally:
        conn.close()

    return render_template(
        "web/potions.html",
        brewing=brewing,
        catalog=catalog,
        owned=owned,
        potion_names=set(potions.POTION_ITEMS.values()),
        brewed_today=brewed_today,
        daily_limit=potions.DAILY_LIMIT,
        stamina_cost=potions.BREW_STAMINA_COST,
        titles=potions.title_state(g.uid),
        gifted_today=gifted_today,
        trade_limit=potions.TRADE_DAILY_LIMIT,
        polyjuice_name=potions.RECIPES["polyjuice"]["name"],
    )


def _flash_potion_result(result: dict) -> None:
    if result["quantity"]:
        flash(
            f"{result['recipe']}熬好了——{result['quality']}（{result['score']}/3步做对），"
            f"得到{result['quantity']}瓶。",
            "ok",
        )
        _notify(
            f"熬出了{result['quantity']}瓶{result['recipe']}（{result['quality']}）",
            "study",
            merge_key=f"potion:{result['recipe']}:{result['quality']}",
        )
    else:
        flash(f"{result['recipe']}熬砸了（{result['score']}/3步做对）。{result['accident']}。", "error")
        _notify(f"熬{result['recipe']}翻车了，{result['accident']}", "study")


def _flash_potion_use(result: dict) -> None:
    if "restored" in result:
        flash(f"喝下{result['name']}，体力+{result['restored']}（现在{result['stamina']}）。", "ok")
        _notify("喝了{n}瓶提神剂", "study", merge_key="drink:energizing")
        return
    if "target_name" in result:
        flash(
            f"喝下{result['name']}，接下来{result['hours']}小时你顶着 {result['target_name']} 的模样。",
            "ok",
        )
        _notify(f"喝下复方汤剂，变成了 {result['target_name']} 的模样", "prank")
        return
    flash(f"喝下{result['name']}。{result['effect']}", "ok")
    _notify(f"喝了{{n}}瓶{result['name']}", "study", merge_key=f"drink:{result['name']}")


# ======================== 圣诞节 ========================


@app.route("/christmas", methods=["GET", "POST"])
def christmas_page():
    guard = _require_player()
    if guard:
        return guard
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "robe":
                result = christmas.design_robe(
                    g.uid,
                    request.form.get("color", ""),
                    request.form.get("style", ""),
                    request.form.get("accessory", ""),
                )
                flash(f"礼服定好了：{result['描述']}", "ok")
            elif action == "invite":
                target = _resolve_name(request.form.get("target", ""))
                christmas.invite_partner(g.uid, target)
                _notify(f"邀请了 {core_storage.get_full_name(target)} 做圣诞舞会的舞伴", "social")
                flash("邀请发出去了，等对方回应。", "ok")
            elif action == "withdraw_invite":
                christmas.withdraw_invite(g.uid)
                flash("已撤回邀请。", "ok")
            elif action in ("accept_invite", "decline_invite"):
                inviter = request.form.get("inviter", "")
                result = christmas.respond_invite(g.uid, inviter, action == "accept_invite")
                if result["accepted"]:
                    _notify(
                        f"答应了 {core_storage.get_full_name(inviter)} 的舞会邀请", "social"
                    )
                    flash("答应了，舞会见。", "ok")
                else:
                    flash("已婉拒。", "ok")
            elif action == "attend":
                result = christmas.attend(g.uid)
                _flash_ball_attend(result)
            elif action == "hang":
                result = christmas.hang(g.uid, request.form.get("ornament", ""))
                _notify(f"往圣诞树上挂了{{n}}件装饰", "social", merge_key="tree_hang")
                msg = f"你挂上了{result['ornament']}（+{result['points']}），进度 {result['progress']}/{result['goal']}。"
                if result["just_completed"]:
                    msg += " ✨整棵树亮了起来！"
                    _notify("挂上了最后一件装饰，圣诞树亮了", "social")
                    for award in result["rank_awards"]:
                        award_name = core_storage.get_full_name(award["uid"])
                        core_notify.push(
                            f"{award_name} 拿下圣诞树贡献榜第{award['rank']}名，"
                            f"解锁「{award['title']}」称号，+{award['galleons']}加隆",
                            uid=award["uid"],
                            category="social",
                        )
                flash(msg, "ok")
            elif action == "claim_tree":
                result = christmas.claim_tree_reward(g.uid)
                flash(f"🎁 领到 {result['galleons']}加隆 和一份「{result['gift']}」。", "ok")
            elif action == "eat_feast":
                result = christmas.eat_feast(g.uid, request.form.get("dish", ""))
                msg = f"你吃了一道{result['dish']}。"
                if result["gift"]:
                    msg += f" 盘子底下压着一份小礼品：{result['gift']}！"
                if result["got_pudding_entry"]:
                    msg += " 布丁里的硬币被你吃到了——今晚10点看看运气。"
                msg += f"（目前吃过 {result['variety']} 种）"
                flash(msg, "ok")
        except (ENGINE_ERRORS + (LookupError,)) as e:
            flash(str(e), "error")
        return redirect(url_for("christmas_page"))

    day = core_storage.get_current_day() or 1
    year = christmas._year_of(day)
    from plugins.hp_events import storage as events_storage

    return render_template(
        "web/christmas.html",
        ball=christmas.ball_window_state(),
        robe=christmas.get_robe(g.uid),
        partner=christmas.get_partner(g.uid),
        my_invite=events_storage.get_ball_invite_from(g.uid, year),
        incoming=events_storage.list_ball_invites_to(g.uid, year),
        attended=events_storage.has_attended_ball(g.uid, year),
        colors=christmas.ROBE_COLORS,
        styles=christmas.ROBE_STYLES,
        accessories=christmas.ROBE_ACCESSORIES,
        tree=christmas.tree_state(),
        tree_reward=christmas.tree_reward_state(g.uid),
        tree_leaderboard=christmas.tree_contributor_leaderboard(limit=5),
        ornaments=christmas.TREE_ORNAMENTS,
        points_min=christmas.TREE_HANG_POINTS_MIN,
        points_max=christmas.TREE_HANG_POINTS_MAX,
        feast=christmas.feast_state(g.uid),
        feast_leaderboard=christmas.feast_leaderboard(limit=5),
        pudding_draw=events_storage.get_pudding_draw(year),
        full_name=core_storage.get_full_name,
        name_of=core_storage.get_name,
    )


def _flash_ball_attend(result: dict) -> None:
    parts = ["你走进了礼堂。"]
    if result["robe"]:
        parts.append(result["robe"]["描述"])
    if result["partner_attended"]:
        parts.append(f"和舞伴跳了一整晚，好感度各+{result['affection']}。")
    flash("　".join(parts), "ok")
    _notify("出席了圣诞舞会", "social")


# ======================== 级长选举 ========================


@app.route("/prefect", methods=["GET", "POST"])
def prefect_page():
    guard = _require_player()
    if guard:
        return guard
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "vote":
                target = _resolve_name(request.form.get("target", ""))
                result = prefect.vote(g.uid, target)
                if result["changed"]:
                    flash(f"改投给了 {core_storage.get_full_name(target)}。", "ok")
                else:
                    flash(f"你投给了 {core_storage.get_full_name(target)}。", "ok")
            elif action == "duty":
                result = prefect.run_duty(g.uid)
                _notify(
                    f"带队巡查了走廊，{result['house']}学院分+{result['house_points']}", "study"
                )
                flash(
                    f"巡查完毕，{result['house']}学院分+{result['house_points']}，"
                    f"你拿到{result['galleons']}加隆。",
                    "ok",
                )
        except (ENGINE_ERRORS + (LookupError,)) as e:
            flash(str(e), "error")
        return redirect(url_for("prefect_page"))

    day = core_storage.get_current_day() or 1
    state = prefect.phase(day)
    return render_template(
        "web/prefect.html",
        state=state,
        nominate_day=prefect.NOMINATE_DAY,
        close_day=prefect.CLOSE_DAY,
        winners_per_house=prefect.WINNERS_PER_HOUSE,
        candidates=prefect.candidates(g.player["house"]) if state == "voting" else [],
        my_vote=prefect.my_vote(g.uid),
        prefects=prefect.prefects() if state == "closed" else {},
        duty=prefect.duty_state(g.uid),
    )


# ======================== 校报投稿 ========================


def _school_year_of(day: int) -> int:
    for year, (_, end) in newspaper_service.YEAR_RANGES.items():
        if day <= end:
            return year
    return 7


@app.route("/submit", methods=["GET", "POST"])
def submit_page():
    guard = _require_player()
    if guard:
        return guard
    day = core_storage.get_current_day() or 1
    if request.method == "POST":
        try:
            result = submissions.submit(
                g.uid,
                request.form.get("title", ""),
                request.form.get("body", ""),
                day,
                _school_year_of(day),
            )
            flash(
                f"《{result['title']}》已投给编辑部，等审核。"
                f"今天投了{result['used']}/{result['limit']}篇。",
                "ok",
            )
        except ENGINE_ERRORS as e:
            flash(str(e), "error")
        return redirect(url_for("submit_page"))

    return render_template(
        "web/submit.html",
        mine=submissions.list_mine(g.uid),
        used=submissions.count_today(g.uid, day),
        limit=submissions.DAILY_LIMIT,
        title_max=submissions.TITLE_MAX,
        body_max=submissions.BODY_MAX,
        school_year=_school_year_of(day),
    )


@app.route("/admin/submissions", methods=["GET", "POST"])
def admin_submissions():
    if not session.get(ADMIN_SESSION_KEY):
        return redirect(url_for("admin_login"))
    if request.method == "POST":
        try:
            sub_id = int(request.form.get("id", "0"))
            approved = request.form.get("action") == "approve"
            row = submissions.review(sub_id, approved, request.form.get("note", ""))
            if approved:
                core_notify.push(
                    f"的来稿《{row['title']}》登上了{row['school_year']}年级校报",
                    uid=row["uid"],
                    category="press",
                )
                flash(f"《{row['title']}》已通过，会登上{row['school_year']}年级校报。", "ok")
            else:
                flash(f"《{row['title']}》已退稿。", "ok")
        except (submissions.SubmissionError, ValueError) as e:
            flash(str(e), "error")
        return redirect(url_for("admin_submissions"))

    pending = submissions.list_by_status("pending")
    recent = [s for s in submissions.list_by_status() if s["status"] != "pending"][:30]
    for row in pending + recent:
        row["author"] = core_storage.get_full_name(row["uid"])
    return render_template("web/admin_submissions.html", pending=pending, recent=recent)


# ======================== 女巫周刊（匿名八卦投稿） ========================


@app.route("/gossip", methods=["GET", "POST"])
def gossip_page():
    guard = _require_player()
    if guard:
        return guard
    day = core_storage.get_current_day() or 1
    if request.method == "POST":
        try:
            result = gossip.submit(
                g.uid,
                request.form.get("body", ""),
                request.form.get("mentioned", ""),
                day,
            )
            flash(
                f"投出去了，匿名等审核。今天投了{result['used']}/{result['limit']}条。",
                "ok",
            )
        except ENGINE_ERRORS as e:
            flash(str(e), "error")
        return redirect(url_for("gossip_page"))

    return render_template(
        "web/gossip.html",
        mine=gossip.list_mine(g.uid),
        used=gossip.count_today(g.uid, day),
        limit=gossip.daily_limit_for(g.uid),
        body_min=gossip.BODY_MIN,
        body_max=gossip.BODY_MAX,
    )


@app.route("/admin/gossip", methods=["GET", "POST"])
def admin_gossip():
    if not session.get(ADMIN_SESSION_KEY):
        return redirect(url_for("admin_login"))
    if request.method == "POST":
        try:
            gossip_id = int(request.form.get("id", "0"))
            approved = request.form.get("action") == "approve"
            row = gossip.review(gossip_id, approved, request.form.get("note", ""))
            if approved:
                flash(f"已通过，稿费{row['reward']}加隆已发放，等待下一轮播报进群。", "ok")
            else:
                flash("已退稿，没有稿费。", "ok")
        except (gossip.GossipError, ValueError) as e:
            flash(str(e), "error")
        return redirect(url_for("admin_gossip"))

    pending = gossip.list_by_status("pending")
    recent = [s for s in gossip.list_by_status() if s["status"] != "pending"][:30]
    for row in pending + recent:
        row["author"] = core_storage.get_full_name(row["uid"])
    return render_template("web/admin_gossip.html", pending=pending, recent=recent)


@app.route("/admin/quidditch-matchups")
def admin_quidditch_matchups():
    """各院当前阵容两两对战的胜率分析——纯计算模拟（不落库），拿真实比赛同一套
    引擎跑很多次统计胜率，给95%置信区间，帮管理员看战力是否失衡。"""
    if not session.get(ADMIN_SESSION_KEY):
        return redirect(url_for("admin_login"))
    try:
        trials = int(request.args.get("trials", 1000))
    except ValueError:
        trials = 1000
    trials = max(100, min(trials, 5000))

    matchups = quidditch.all_matchups(trials)
    return render_template(
        "web/admin_quidditch_matchups.html",
        matchups=matchups,
        trials=trials,
        positions=quidditch.POSITIONS,
        position_desc={pos: quidditch.position_desc(pos) for pos in quidditch.POSITIONS},
    )


# ======================== 竞选新人王 ========================


@app.route("/freshman-duel", methods=["GET", "POST"])
def freshman_duel_page():
    guard = _require_player()
    if guard:
        return guard
    if g.player["grade"] != 1:
        return render_template("web/freshman_duel.html", not_available=True)

    from plugins.hp_school import freshman_duel

    if request.method == "POST":
        result = freshman_duel.perform_duel(g.uid)
        flash(result["message"], "ok" if result["ok"] else "warn")
        return redirect(url_for("freshman_duel_page"))

    my_duel_row = freshman_duel.storage.get_freshman_duel(g.uid)
    my_duel = dict(my_duel_row) if my_duel_row else None
    rankings = freshman_duel.get_leaderboard()
    can_duel, cooldown_msg = freshman_duel.can_duel(my_duel or {})

    return render_template(
        "web/freshman_duel.html",
        my_duel=my_duel,
        rankings_text=rankings,
        can_duel=can_duel,
        cooldown_msg=cooldown_msg,
        positions=freshman_duel.BOARD_POSITIONS,
    )


# ======================== 排行榜 ========================


@app.get("/rankings")
def rankings():
    guard = _require_player()
    if guard:
        return guard
    subject_top = core_storage.subject_exam_leaderboard(3)
    subject_order = [(key, name) for key, name, _, _ in subjects.SUBJECTS if key in subject_top]
    return render_template(
        "web/rankings.html",
        students=core_storage.student_leaderboard(limit=10),
        houses=core_storage.house_leaderboard(),
        subject_top=subject_top,
        subject_order=subject_order,
        quidditch_top=quidditch.get_leaderboard(10),
        feast_top=christmas.feast_leaderboard(limit=10),
    )


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(
        host=os.getenv("GAME_WEB_HOST", "0.0.0.0"),
        port=int(os.getenv("GAME_WEB_PORT", "5018")),
        debug=False,
    )

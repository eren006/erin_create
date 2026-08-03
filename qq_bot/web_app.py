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

import newspaper_service  # noqa: E402
import submissions  # noqa: E402
import web_auth  # noqa: E402
from plugins.hp_core import notify as core_notify  # noqa: E402
from plugins.hp_core import spells as spell_catalog  # noqa: E402
from plugins.hp_core import storage as core_storage  # noqa: E402
from plugins.hp_events import duel, forest, quidditch  # noqa: E402
from plugins.hp_school import (  # noqa: E402
    careers,
    casting,
    daily_plan,
    homework,
    lesson_events,
    lessons,
    mainline,
    potions,
    shop,
    shop_catalog,
    sorting,
    subjects,
    work,
)
from plugins.hp_social import romance
from plugins.hp_social import storage as social_storage  # noqa: E402

web_auth.init_db()
core_notify.init_db()
submissions.init_db()

# 首次启动时生成一个管理密码，只在日志里明文出现这一次；之后可以在后台自行修改
if not web_auth.has_admin_password():
    _initial_admin = os.getenv("HOGWARTS_ADMIN_PASSWORD") or secrets.token_urlsafe(9)
    web_auth.set_admin_password(_initial_admin)
    print(f"[霍格沃茨] 已生成管理密码：{_initial_admin}（请保存，仅此一次明文显示）", flush=True)

app = Flask(__name__)
app.secret_key = os.getenv("HOGWARTS_SECRET_KEY") or "hogwarts-dev-secret-change-me"

ENGINE_ERRORS = (
    potions.PotionError,
    submissions.SubmissionError,
    sorting.SortingError,
    lessons.LessonError,
    lesson_events.LessonEventError,
    homework.HomeworkError,
    shop.ShopError,
    casting.CastError,
    work.WorkError,
    careers.CareerError,
    mainline.MainlineError,
    daily_plan.DailyPlanError,
    quidditch.QuidditchError,
    duel.DuelError,
    forest.ForestError,
    romance.RomanceError,
)


# ======================== 登录与权限 ========================


@app.before_request
def _load_user():
    g.account = web_auth.session_user(session.get("token", ""))
    g.uid = g.account["uid"] if g.account else None
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
    return {
        "account": g.get("account"),
        "player": g.get("player"),
        "display_name": _display_name(g.uid) if g.get("uid") and g.get("player") else "",
        "current_day": core_storage.get_current_day(),
    }


# ======================== 账号 ========================


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        try:
            result = web_auth.request_account(
                request.form.get("uid", ""), request.form.get("note", "")
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
                g.uid, request.form.get("old", ""), request.form.get("new", "")
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

        except web_auth.AuthError as e:
            flash(str(e), "error")
        return redirect(url_for("admin"))

    accounts = web_auth.list_accounts()
    for acc in accounts:
        player = core_storage.get_player(acc["uid"])
        acc["player_name"] = core_storage.get_full_name(acc["uid"]) if player and player["house"] else ""
        acc["house"] = player["house"] if player else ""
    return render_template(
        "web/admin.html",
        pending=[a for a in accounts if a["status"] == "pending"],
        others=[a for a in accounts if a["status"] != "pending"],
    )


# ======================== 主页 / 面板 ========================


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
    return render_template(
        "web/index.html",
        plan=plan,
        exp_map=exp_map,
        subjects=subjects.SUBJECTS,
        learned_count=len(learned),
        spell_total=len(spell_catalog.SPELLS),
        status_suffix=core_storage.get_status_suffix(g.uid),
        exams=core_storage.get_exam_results(g.uid),
        subject_names={k: v[0] for k, v in subjects.SUBJECTS_BY_KEY.items()},
        career=careers.get(g.uid),
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
            _notify("交了{n}份作业", "study", merge_key="homework")
            flash(f"{result['subject']}作业交了，+{result['exp_gained']}经验。", "ok")
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
        items.append(item)
    return render_template(
        "web/shop.html",
        categories=shop_catalog.CATEGORIES,
        cat=cat,
        items=items,
        rotating=cat in shop_catalog.ROTATING_CATEGORIES,
        next_rotation=shop.seconds_to_next_rotation() // 60 + 1,
        next_restock=shop.seconds_to_next_restock() // 60 + 1,
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
                _notify("吃了{n}份零食补体力", "economy", merge_key="eat")
                flash(f"吃了「{result['name']}」，体力+{result['restored']}。", "ok")
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
            flash(result.get("text") or f"打工结束，赚了{result.get('galleons', 0)}加隆。", "ok")
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
            elif action == "train":
                result = quidditch.train(g.uid)
                _notify("训练了{n}次魁地奇", "quidditch", merge_key="qtrain")
                flash(f"训练完成，{result['stat']}+{result['gain']}。", "ok")
            elif action == "match":
                opponent = request.form.get("house", "")
                result = quidditch.simulate_match(g.uid, g.player["house"], opponent)
                winner = result["winner"] or "打平"
                _notify(
                    f"🧹 魁地奇：{result['house_a']} {result['score_a']} : {result['score_b']} "
                    f"{result['house_b']}，{winner}"
                    + (f"，学院分+{quidditch.MATCH_WIN_HOUSE_POINTS}" if result["winner"] else ""),
                    "quidditch",
                )
                flash(
                    f"{result['house_a']} {result['score_a']} : {result['score_b']} {result['house_b']}",
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
        flash(msg, "ok")
    if result.get("defeated"):
        _notify(f"在禁林第{result['depth']}层倒下了，这趟的收获全丢了", "forest")
        flash("你倒下了，这趟的收获全丢了。", "error")


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
        except (ENGINE_ERRORS + (LookupError,)) as e:
            flash(str(e), "error")
        return redirect(url_for("social_page"))

    state = romance.my_romance(g.uid)
    gifts = [
        {"name": name, "price": price, "affection": effect["affection"]}
        for _, name, cat, price, _, effect in shop_catalog.list_by_category("礼物")
    ]
    owned = {i["name"] for i in shop.get_bag(g.uid)}
    return render_template(
        "web/social.html",
        state=state,
        gifts=[gift for gift in gifts if gift["name"] in owned],
        activities=romance.DATE_ACTIVITIES,
        affection_max=romance.AFFECTION_MAX,
        confess_threshold=romance.CONFESS_THRESHOLD,
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
    try:
        book = mainline.open_book(g.uid)
    except ENGINE_ERRORS as e:
        flash(str(e), "error")
        book = None
    return render_template("web/mainline.html", book=book)


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


# ======================== 排行榜 ========================


@app.get("/rankings")
def rankings():
    guard = _require_player()
    if guard:
        return guard
    return render_template(
        "web/rankings.html",
        students=core_storage.student_leaderboard(20),
        houses=core_storage.house_leaderboard(),
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

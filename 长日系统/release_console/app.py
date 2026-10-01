"""长日系统本地发布控制台。

只在本机运行（127.0.0.1），不对外网开放。用来把"记一笔改动 -> 攒够了发一个版本"
这件事从手动改一堆文件变成点几个按钮，同时管部署脚本和一份 TODO 清单。
"""
import json
import re
import urllib.error
import urllib.request
import uuid
import zipfile
from datetime import date
from pathlib import Path

from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent          # 长日系统/
ROOT_DIR = BASE_DIR.parent                                  # erin_creation/
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)

HUB_HTML = BASE_DIR / "changri_hub.html"
WISHES_HTML = BASE_DIR / "changri_wishes.html"
INFO_TOML = BASE_DIR / "dist" / "changri_sealpack_src" / "info.toml"

RP_ARCHIVE_DIR = ROOT_DIR / "rp_archive"

# 部署（scp/ssh 到服务器）不重复实现，而是代理转发给已有的 deploy_dashboard
# （长日hub家族、rp_archive 都已注册在那边），这样这里点一下按钮就能直接跑。
DEPLOY_DASHBOARD_URL = "http://127.0.0.1:5064"
DEPLOY_TARGET_PATHS = {str(BASE_DIR): "hub", str(RP_ARCHIVE_DIR): "rp_archive"}


def deploy_dashboard_get(path):
    req = urllib.request.Request(DEPLOY_DASHBOARD_URL + path)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def deploy_dashboard_post(path, timeout=620):
    req = urllib.request.Request(
        DEPLOY_DASHBOARD_URL + path, method="POST", data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

PENDING_FILE = DATA_DIR / "pending_changes.json"
TODOS_FILE = DATA_DIR / "todos.json"
RELEASE_LOG_FILE = DATA_DIR / "release_log.json"

# 核心模块（长日系统.js）的版本号 = 系统总版本号，驱动 hub/wishes/info.toml。
# 其它模块各自独立版本号，只在勾选"顺带升级"时才会跟着这次发布一起改。
MODULES = [
    {"key": "core", "label": "长日系统（核心）", "src": "长日系统.js", "dist": "dist/changri_sealpack_src/scripts/core.js", "is_core": True},
    {"key": "settings", "label": "长日设置", "src": "长日设置.js", "dist": "dist/changri_sealpack_src/scripts/settings.js", "is_core": False},
    {"key": "social", "label": "长日社交", "src": "长日社交.js", "dist": "dist/changri_sealpack_src/scripts/social.js", "is_core": False},
    {"key": "alarm", "label": "长日闹钟", "src": "长日闹钟.js", "dist": "dist/changri_sealpack_src/scripts/alarm.js", "is_core": False},
    {"key": "season", "label": "长日季度", "src": "长日季度.js", "dist": "dist/changri_sealpack_src/scripts/season.js", "is_core": False},
    {"key": "auction", "label": "长日拍卖", "src": "长日拍卖.js", "dist": "dist/changri_sealpack_src/scripts/auction.js", "is_core": False},
    {"key": "dinner", "label": "长日晚餐", "src": "长日晚餐.js", "dist": "dist/changri_sealpack_src/scripts/dinner.js", "is_core": False},
    {"key": "entrance", "label": "长日出场", "src": "长日出场.js", "dist": "dist/changri_sealpack_src/scripts/entrance.js", "is_core": False},
    {"key": "letters", "label": "长日写信综", "src": "长日写信综.js", "dist": "dist/changri_sealpack_src/scripts/letters.js", "is_core": False},
    {"key": "rpg", "label": "长日RPG", "src": "长日RPG.js", "dist": "dist/changri_sealpack_src/scripts/rpg.js", "is_core": False},
]
MODULES_BY_KEY = {m["key"]: m for m in MODULES}

TYPE_TITLES = {"feat": "新增", "improve": "优化", "fix": "修复", "chore": "其他"}
TYPE_ORDER = ["feat", "improve", "fix", "chore"]

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


# ---------------------------------------------------------------- 基础读写

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_pending():
    return load_json(PENDING_FILE, [])


def save_pending(items):
    save_json(PENDING_FILE, items)


def load_todos():
    return load_json(TODOS_FILE, [])


def save_todos(items):
    save_json(TODOS_FILE, items)


def load_release_log():
    return load_json(RELEASE_LOG_FILE, [])


def save_release_log(items):
    save_json(RELEASE_LOG_FILE, items)


# ---------------------------------------------------------------- 版本读取

def get_module_version(module: dict) -> str:
    src_path = BASE_DIR / module["src"]
    text = read_text(src_path)
    m = re.search(r"//\s*@version\s+([\d.]+)", text)
    if not m:
        raise RuntimeError(f"{module['src']} 里找不到 @version 行")
    return m.group(1)


def get_all_module_versions():
    out = []
    for m in MODULES:
        try:
            v = get_module_version(m)
        except Exception as e:
            v = f"读取失败: {e}"
        out.append({"key": m["key"], "label": m["label"], "version": v, "is_core": m["is_core"]})
    return out


def bump_version(old_version: str, bump: str, custom_version: str = "") -> str:
    if bump == "custom":
        if not VERSION_RE.match(custom_version or ""):
            raise ValueError("自定义版本号格式要是 x.y.z")
        return custom_version
    parts = old_version.split(".")
    if len(parts) != 3:
        raise ValueError(f"无法识别的版本号：{old_version}")
    major, minor, patch = (int(x) for x in parts)
    if bump == "patch":
        patch += 1
    elif bump == "minor":
        minor += 1
        patch = 0
    else:
        raise ValueError(f"未知的升级方式：{bump}")
    return f"{major}.{minor}.{patch}"


# 每个模块文件里版本号出现两处：文件头的 `// @version` 注释（人看的），和
# `seal.ext.new(内部名, 作者, 版本号)` 里的版本号字符串（SealDice 实际读取、在扩展列表里显示的那个）。
# 这两处历史上只手动改了前者——长日RPG.js 就因此在 2026-09 之前一直卡着 header=2.2.0 / ext.new=2.1.0
# 的错位——所以这里两处必须一起改，改不到就直接报错中止，不能悄悄漏掉一处。
EXT_NEW_RE = re.compile(r"(seal\.ext\.new\(\s*['\"][^'\"]*['\"]\s*,\s*['\"][^'\"]*['\"]\s*,\s*['\"])([^'\"]*)(['\"])")


def bump_ext_new_version(text: str, old_version: str, new_version: str) -> str:
    """把文本里唯一一处 `seal.ext.new(...)` 调用里的版本号从 old_version 改成 new_version。
    没找到 ext.new 调用，或者它当前的版本号不是 old_version（说明已经跟 header 不一致，需要人工确认
    该信哪个），都返回 None，交给调用方决定是报错还是走别的分支。"""
    m = EXT_NEW_RE.search(text)
    if not m or m.group(2) != old_version:
        return None
    return text[:m.start(2)] + new_version + text[m.end(2):]


# ---------------------------------------------------------------- CHANGELOG 解析（只读展示用）

ENTRY_RE = re.compile(
    r'\{\s*version:\s*"([^"]+)",\s*date:\s*"([^"]+)",\s*latest:\s*(true|false),\s*groups:\s*\[(?P<groups>.*?)\n {4}\]\s*\}',
    re.S,
)
GROUP_RE = re.compile(
    r'\{\s*type:\s*"([^"]+)",\s*title:\s*"([^"]+)",\s*items:\s*\[(?P<items>.*?)\n {6}\]\}',
    re.S,
)
ITEM_RE = re.compile(r'"((?:[^"\\]|\\.)*)"\s*,?')


def parse_changelog():
    html = read_text(HUB_HTML)
    m = re.search(r"const CHANGELOG = \[(?P<body>.*?)\n\];", html, re.S)
    if not m:
        return []
    body = m.group("body")
    entries = []
    for em in ENTRY_RE.finditer(body):
        version, entry_date, latest, groups_text = em.group(1), em.group(2), em.group(3), em.group("groups")
        groups = []
        for gm in GROUP_RE.finditer(groups_text):
            gtype, gtitle, items_text = gm.group(1), gm.group(2), gm.group("items")
            items = [x.replace('\\"', '"').replace("\\\\", "\\") for x in ITEM_RE.findall(items_text)]
            groups.append({"type": gtype, "title": gtitle, "items": items})
        entries.append({"version": version, "date": entry_date, "latest": latest == "true", "groups": groups})
    return entries


# ---------------------------------------------------------------- 发布（写文件）

def build_changelog_entry_block(version: str, entry_date: str, notes: list) -> str:
    by_type = {}
    for n in notes:
        by_type.setdefault(n["type"], []).append(n["text"])

    groups_lines = []
    for t in TYPE_ORDER:
        if t not in by_type:
            continue
        title = TYPE_TITLES.get(t, "其他")
        groups_lines.append(f'      {{ type: "{t}", title: "{title}", items: [')
        for text in by_type[t]:
            groups_lines.append(f"        {json.dumps(text, ensure_ascii=False)},")
        groups_lines.append("      ]},")
    groups_block = "\n".join(groups_lines)

    return (
        "  {\n"
        f'    version: "{version}",\n'
        f'    date: "{entry_date}",\n'
        "    latest: true,\n"
        "    groups: [\n"
        f"{groups_block}\n"
        "    ]\n"
        "  },\n"
    )


def sync_modules_dist(skip_keys=frozenset()) -> list:
    """把 skip_keys 之外的每个模块的 dist 同步成当前 src 内容（不一样才写，一样的跳过）。
    发布时用来兜底"这次没升级但代码已经改了"的模块；也单独暴露成 /api/sync_dist，
    平时改完某个卫星模块想立刻同步一下、还不想走整套发布流程时用。"""
    changed = []
    for module in MODULES:
        if module["key"] in skip_keys:
            continue
        src_path = BASE_DIR / module["src"]
        dist_path = BASE_DIR / module["dist"]
        src_text = read_text(src_path)
        if dist_path.exists() and read_text(dist_path) == src_text:
            continue
        write_text(dist_path, src_text)
        changed.append(str(dist_path))
    return changed


SEALPACK_SRC_DIR = BASE_DIR / "dist" / "changri_sealpack_src"
SEALPACK_OUT_DIR = BASE_DIR / "dist"


def build_sealpack(version: str = None) -> Path:
    """把 dist/changri_sealpack_src/ 打成 SealDice 能直接导入的 changri@版本号.sealpack
    （sealpack 本质就是一个 zip，info.toml + assets/ + scripts/ 放在压缩包根目录）。"""
    if version is None:
        version = get_module_version(MODULES_BY_KEY["core"])
    if not VERSION_RE.match(version):
        raise ValueError(f"版本号格式不对：{version}")
    if not SEALPACK_SRC_DIR.is_dir():
        raise ValueError(f"找不到打包源目录：{SEALPACK_SRC_DIR}")

    out_path = SEALPACK_OUT_DIR / f"changri@{version}.sealpack"
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(SEALPACK_SRC_DIR.rglob("*")):
            if path.is_dir() or path.name == ".DS_Store":
                continue
            zf.write(path, path.relative_to(SEALPACK_SRC_DIR))
    return out_path


def do_release(bump: str, custom_version: str, note_ids: list, module_bumps: dict):
    """校验通过再写，避免半途写坏文件。返回 (new_version, changed_files)。"""
    core_module = MODULES_BY_KEY["core"]
    old_version = get_module_version(core_module)

    pending = load_pending()
    by_id = {n["id"]: n for n in pending}

    if bump == "none":
        if note_ids:
            raise ValueError("不改系统版本号的话，就不要选要发布的变更（它们会继续留在待发布列表里）")
        new_version = old_version
    else:
        if not note_ids:
            raise ValueError("请至少选一条待发布的变更")
        missing = [i for i in note_ids if i not in by_id]
        if missing:
            raise ValueError(f"找不到这些变更记录：{missing}")
        new_version = bump_version(old_version, bump, custom_version)

    notes = [by_id[i] for i in note_ids]
    today = date.today().isoformat()

    # 先把所有要动的模块版本号规划好、并校验格式，全部通过才动手写文件
    module_plans = []  # (module, old_v, new_v)
    for key, new_v in (module_bumps or {}).items():
        if key not in MODULES_BY_KEY:
            raise ValueError(f"未知模块：{key}")
        if key == "core":
            continue  # 核心模块版本号由系统版本号统一驱动，不单独走这个通道
        new_v = (new_v or "").strip()
        if not new_v:
            continue
        if not VERSION_RE.match(new_v):
            raise ValueError(f"{MODULES_BY_KEY[key]['label']} 的新版本号格式要是 x.y.z")
        module_plans.append((MODULES_BY_KEY[key], get_module_version(MODULES_BY_KEY[key]), new_v))

    # 校验通过再写，避免半途写坏文件：先把这次要落盘的每一份内容都在内存里算好、校验完，
    # 全部通过才进入下面真正写文件的阶段——之前 core 和"顺带升级的模块"是分两段分别校验+
    # 立即写入的，一旦某个模块校验失败，前面 core 那段其实已经写完了，版本号会停在半升级状态。
    planned_writes = {}   # path(Path) -> content(str)
    synced_keys = set()

    if bump != "none":
        hub_html = read_text(HUB_HTML)
        wishes_html = read_text(WISHES_HTML)
        info_toml = read_text(INFO_TOML)
        core_src = read_text(BASE_DIR / core_module["src"])

        nav_old = f'<div class="nav-meta">SYSTEM · v{old_version}</div>'
        hero_old = f'<div class="hero-stat"><b>v{old_version}</b><span>当前版本</span></div>'
        info_old = f'version = "{old_version}"'
        version_hdr_old = f"// @version      {old_version}"

        if "latest: true," not in hub_html:
            raise ValueError("hub.html 里找不到 latest: true, 锚点，中止发布")
        if nav_old not in hub_html:
            raise ValueError(f"hub.html 里找不到版本号锚点：{nav_old}")
        if hero_old not in hub_html:
            raise ValueError(f"hub.html 里找不到版本号锚点：{hero_old}")
        if "const CHANGELOG = [\n" not in hub_html:
            raise ValueError("hub.html 里找不到 const CHANGELOG = [ 锚点，中止发布")
        if nav_old not in wishes_html:
            raise ValueError(f"wishes.html 里找不到版本号锚点：{nav_old}")
        if info_old not in info_toml:
            raise ValueError(f"info.toml 里找不到版本号锚点：{info_old}")
        if version_hdr_old not in core_src:
            raise ValueError(f"{core_module['src']} 里找不到版本号锚点：{version_hdr_old}")

        entry_block = build_changelog_entry_block(new_version, today, notes)

        hub_html = hub_html.replace("latest: true,", "latest: false,", 1)
        hub_html = hub_html.replace(nav_old, f'<div class="nav-meta">SYSTEM · v{new_version}</div>', 1)
        hub_html = hub_html.replace(hero_old, f'<div class="hero-stat"><b>v{new_version}</b><span>当前版本</span></div>', 1)
        hub_html = hub_html.replace("const CHANGELOG = [\n", "const CHANGELOG = [\n" + entry_block, 1)
        wishes_html = wishes_html.replace(nav_old, f'<div class="nav-meta">SYSTEM · v{new_version}</div>', 1)
        info_toml = info_toml.replace(info_old, f'version = "{new_version}"', 1)
        core_src = core_src.replace(version_hdr_old, f"// @version      {new_version}", 1)

        # header 之外，seal.ext.new(...) 里也存了一份版本号（SealDice 扩展列表实际显示的就是这个），
        # 必须跟着一起改，不然会出现"注释写着新版本、SealDice 里显示旧版本"的错位（长日RPG.js 曾经
        # 就卡在 header=2.2.0 / ext.new=2.1.0 没同步，一直到这次才发现并修掉）。
        core_src_bumped = bump_ext_new_version(core_src, old_version, new_version)
        if core_src_bumped is None:
            raise ValueError(
                f"{core_module['src']} 里的 seal.ext.new(...) 版本号跟 header 对不上（应为 {old_version}），"
                f"中止发布——先手动核实这两处版本号一致，再重新发布"
            )
        core_src = core_src_bumped

        planned_writes[HUB_HTML] = hub_html
        planned_writes[WISHES_HTML] = wishes_html
        planned_writes[INFO_TOML] = info_toml
        planned_writes[BASE_DIR / core_module["src"]] = core_src
        planned_writes[BASE_DIR / core_module["dist"]] = core_src  # dist 是 src 的镜像，整份覆盖，不再单独维护
        synced_keys.add("core")

    for module, old_v, new_v in module_plans:
        src_path = BASE_DIR / module["src"]
        dist_path = BASE_DIR / module["dist"]
        src_text = read_text(src_path)
        old_hdr = f"// @version      {old_v}"
        if old_hdr not in src_text:
            raise ValueError(f"{module['label']} 的版本号锚点没找到（请检查 {module['src']}）")
        src_text = src_text.replace(old_hdr, f"// @version      {new_v}", 1)
        src_text_bumped = bump_ext_new_version(src_text, old_v, new_v)
        if src_text_bumped is None:
            raise ValueError(
                f"{module['label']}（{module['src']}）里的 seal.ext.new(...) 版本号跟 header 对不上"
                f"（应为 {old_v}），中止发布——先手动核实这两处版本号一致，再重新发布"
            )
        src_text = src_text_bumped
        planned_writes[src_path] = src_text
        planned_writes[dist_path] = src_text  # 同上，dist 整份覆盖
        synced_keys.add(module["key"])

    # 收尾：这次没碰版本号、但源码跟 dist 已经不一致的模块（比如中途改了功能但这次发布没打算升它的版号），
    # 照样计划把 dist 同步成 src 当前内容，避免"忘了 cp"这种事再发生——升不升版本号跟内容要不要同步是两件事。
    for module in MODULES:
        if module["key"] in synced_keys:
            continue
        dist_path = BASE_DIR / module["dist"]
        src_text = read_text(BASE_DIR / module["src"])
        if dist_path.exists() and read_text(dist_path) == src_text:
            continue
        planned_writes[dist_path] = src_text

    # 前面全部校验通过、一个 ValueError 都没抛出，这里才真正落盘——保证不会出现"部分文件已经
    # 升级、另一部分因为后校验失败而卡在旧版本号"的半途状态。
    for path, content in planned_writes.items():
        write_text(path, content)
    changed_files = [str(p) for p in planned_writes]

    remaining = [n for n in pending if n["id"] not in note_ids]
    save_pending(remaining)

    log = load_release_log()
    log.insert(0, {
        "version": new_version,
        "date": today,
        "notes": notes,
        "module_bumps": [{"key": mo["key"], "label": mo["label"], "old": ov, "new": nv} for mo, ov, nv in module_plans],
    })
    save_release_log(log)

    return new_version, changed_files


# ---------------------------------------------------------------- 路由

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    return jsonify({
        "modules": get_all_module_versions(),
        "pending": load_pending(),
        "todos": load_todos(),
        "release_log": load_release_log()[:10],
        "deploy_dashboard_url": DEPLOY_DASHBOARD_URL,
    })


@app.route("/api/pending", methods=["POST"])
def api_add_pending():
    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "内容不能为空"}), 400
    note_type = data.get("type") or "feat"
    if note_type not in TYPE_TITLES:
        note_type = "feat"
    module = data.get("module") or ""
    note = {
        "id": uuid.uuid4().hex[:8],
        "type": note_type,
        "module": module,
        "text": text,
        "created": date.today().isoformat(),
    }
    pending = load_pending()
    pending.append(note)
    save_pending(pending)
    return jsonify(note)


@app.route("/api/pending/<note_id>", methods=["PUT"])
def api_edit_pending(note_id):
    data = request.get_json(force=True)
    pending = load_pending()
    for n in pending:
        if n["id"] == note_id:
            if "text" in data:
                n["text"] = data["text"].strip()
            if "type" in data and data["type"] in TYPE_TITLES:
                n["type"] = data["type"]
            if "module" in data:
                n["module"] = data["module"]
            save_pending(pending)
            return jsonify(n)
    return jsonify({"error": "not found"}), 404


@app.route("/api/pending/<note_id>", methods=["DELETE"])
def api_delete_pending(note_id):
    pending = load_pending()
    pending = [n for n in pending if n["id"] != note_id]
    save_pending(pending)
    return jsonify({"ok": True})


@app.route("/api/todos", methods=["POST"])
def api_add_todo():
    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "内容不能为空"}), 400
    todo = {"id": uuid.uuid4().hex[:8], "text": text, "done": False, "created": date.today().isoformat()}
    todos = load_todos()
    todos.append(todo)
    save_todos(todos)
    return jsonify(todo)


@app.route("/api/todos/<todo_id>", methods=["PUT"])
def api_edit_todo(todo_id):
    data = request.get_json(force=True)
    todos = load_todos()
    for t in todos:
        if t["id"] == todo_id:
            if "done" in data:
                t["done"] = bool(data["done"])
            if "text" in data:
                t["text"] = data["text"].strip()
            save_todos(todos)
            return jsonify(t)
    return jsonify({"error": "not found"}), 404


@app.route("/api/todos/<todo_id>", methods=["DELETE"])
def api_delete_todo(todo_id):
    todos = load_todos()
    todos = [t for t in todos if t["id"] != todo_id]
    save_todos(todos)
    return jsonify({"ok": True})


@app.route("/api/changelog")
def api_changelog():
    try:
        return jsonify(parse_changelog())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/release", methods=["POST"])
def api_release():
    data = request.get_json(force=True)
    try:
        new_version, changed_files = do_release(
            bump=data.get("bump", "patch"),
            custom_version=data.get("custom_version", ""),
            note_ids=data.get("note_ids", []),
            module_bumps=data.get("module_bumps", {}),
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "version": new_version, "changed_files": changed_files})


@app.route("/api/sync_dist", methods=["POST"])
def api_sync_dist():
    """不发布、不改版本号，只把所有模块的 dist 同步成当前 src 内容——中途改完某个卫星模块的代码，
    想立刻同步一下再去测试/打包时用，不用等到正式发布那一刻。"""
    try:
        changed_files = sync_modules_dist()
    except OSError as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True, "changed_files": changed_files, "count": len(changed_files)})


@app.route("/api/package", methods=["POST"])
def api_package():
    """把 dist/changri_sealpack_src/ 打成 changri@版本号.sealpack，供导入 SealDice。
    打包前不校验 dist 是否已跟 src 同步——想确保打的是最新代码，先点"同步 dist"或先发布一次。"""
    data = request.get_json(silent=True) or {}
    try:
        out_path = build_sealpack(version=data.get("version") or None)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "path": str(out_path), "size_kb": round(out_path.stat().st_size / 1024, 1)})


@app.route("/api/deploy/targets")
def api_deploy_targets():
    try:
        projects = deploy_dashboard_get("/api/projects")
    except (urllib.error.URLError, TimeoutError, ConnectionRefusedError) as e:
        return jsonify({"error": f"连不上部署控制台（{DEPLOY_DASHBOARD_URL}），先启动它：cd deploy_dashboard && python3 app.py（{e}）"}), 503
    targets = [p for p in projects if p.get("path") in DEPLOY_TARGET_PATHS]
    return jsonify(targets)


@app.route("/api/deploy/<int:project_id>/run", methods=["POST"])
def api_deploy_run(project_id):
    try:
        result = deploy_dashboard_post(f"/api/projects/{project_id}/deploy")
    except (urllib.error.URLError, TimeoutError, ConnectionRefusedError) as e:
        return jsonify({"error": f"部署请求失败：{e}"}), 503
    except urllib.error.HTTPError as e:
        return jsonify({"error": f"部署控制台返回错误：{e.read().decode('utf-8', 'ignore')}"}), e.code
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5098, debug=False)

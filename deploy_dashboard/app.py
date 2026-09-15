import os
import sqlite3
import subprocess
import threading
from datetime import datetime

from flask import Flask, render_template, request, jsonify

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "deploy_dashboard.db")
DEPLOY_TIMEOUT_SECONDS = 600
OUTPUT_MAX_CHARS = 20000

app = Flask(__name__)

# Guards against double-clicking Deploy on the same project while a run is in flight.
_running_lock = threading.Lock()
_running_project_ids = set()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            path TEXT NOT NULL,
            deploy_script TEXT NOT NULL,
            last_deployed_commit TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS deploy_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            from_commit TEXT,
            to_commit TEXT,
            commit_log TEXT,
            output TEXT,
            exit_code INTEGER,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_project ON deploy_runs(project_id)")
    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def resolve_deploy_script(project_path, deploy_script):
    if os.path.isabs(deploy_script):
        return deploy_script
    return os.path.join(project_path, deploy_script)


def git_head(path):
    try:
        result = subprocess.run(
            ["git", "-C", path, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def git_commit_log(path, from_commit, to_commit):
    if not to_commit:
        return None
    try:
        rev_range = f"{from_commit}..{to_commit}" if from_commit else to_commit
        # Scoped to `path` itself (`-- .`) so a project living inside a monorepo
        # doesn't pick up unrelated commits from sibling projects in the same repo.
        result = subprocess.run(
            ["git", "-C", path, "log", "--oneline", "-n", "50", rev_range, "--", "."],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def project_to_dict(row, conn):
    last_run = conn.execute(
        """SELECT started_at, finished_at, status, commit_log
           FROM deploy_runs WHERE project_id = ? ORDER BY id DESC LIMIT 1""",
        (row["id"],),
    ).fetchone()
    return {
        "id": row["id"],
        "name": row["name"],
        "path": row["path"],
        "deploy_script": row["deploy_script"],
        "last_deployed_commit": row["last_deployed_commit"],
        "created_at": row["created_at"],
        "last_run": dict(last_run) if last_run else None,
        "is_running": row["id"] in _running_project_ids,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/projects", methods=["GET"])
def list_projects():
    conn = get_db()
    rows = conn.execute("SELECT * FROM projects ORDER BY name COLLATE NOCASE").fetchall()
    projects = [project_to_dict(r, conn) for r in rows]
    conn.close()
    return jsonify(projects)


@app.route("/api/projects", methods=["POST"])
def add_project():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    path = (data.get("path") or "").strip()
    deploy_script = (data.get("deploy_script") or "deploy.sh").strip()

    if not name:
        return jsonify({"error": "项目名称不能为空"}), 400
    if not path:
        return jsonify({"error": "路径不能为空"}), 400

    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(path):
        return jsonify({"error": f"路径不存在或不是目录: {path}"}), 400

    script_path = resolve_deploy_script(path, deploy_script)
    if not os.path.isfile(script_path):
        return jsonify({"error": f"部署脚本不存在: {script_path}"}), 400

    conn = get_db()
    cur = conn.execute(
        "INSERT INTO projects (name, path, deploy_script, last_deployed_commit, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, path, deploy_script, git_head(path), datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (cur.lastrowid,)).fetchone()
    result = project_to_dict(row, conn)
    conn.close()
    return jsonify(result), 201


@app.route("/api/projects/<int:project_id>", methods=["DELETE"])
def delete_project(project_id):
    conn = get_db()
    conn.execute("DELETE FROM deploy_runs WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/projects/<int:project_id>/history", methods=["GET"])
def project_history(project_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM deploy_runs WHERE project_id = ? ORDER BY id DESC LIMIT 50",
        (project_id,),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/history", methods=["GET"])
def global_history():
    conn = get_db()
    rows = conn.execute(
        """SELECT deploy_runs.*, projects.name AS project_name
           FROM deploy_runs JOIN projects ON projects.id = deploy_runs.project_id
           ORDER BY deploy_runs.id DESC LIMIT 100"""
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/projects/<int:project_id>/deploy", methods=["POST"])
def deploy_project(project_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        conn.close()
        return jsonify({"error": "项目不存在"}), 404

    with _running_lock:
        if project_id in _running_project_ids:
            conn.close()
            return jsonify({"error": "这个项目已经在部署中了"}), 409
        _running_project_ids.add(project_id)

    project_path = row["path"]
    script_path = resolve_deploy_script(project_path, row["deploy_script"])
    from_commit = row["last_deployed_commit"]
    started_at = datetime.now().isoformat(timespec="seconds")

    try:
        to_commit_before = git_head(project_path)
        try:
            result = subprocess.run(
                ["bash", script_path],
                cwd=project_path,
                capture_output=True, text=True,
                timeout=DEPLOY_TIMEOUT_SECONDS,
            )
            exit_code = result.returncode
            output = (result.stdout or "") + (result.stderr or "")
            status = "success" if exit_code == 0 else "failed"
        except subprocess.TimeoutExpired as e:
            exit_code = -1
            output = (e.stdout or "") + (e.stderr or "") + "\n[超时: 部署脚本运行超过 {}s]".format(DEPLOY_TIMEOUT_SECONDS)
            status = "failed"

        to_commit = git_head(project_path) or to_commit_before
        commit_log = git_commit_log(project_path, from_commit, to_commit)
        finished_at = datetime.now().isoformat(timespec="seconds")

        if len(output) > OUTPUT_MAX_CHARS:
            output = output[-OUTPUT_MAX_CHARS:]
            output = "...(已截断)...\n" + output

        conn.execute(
            """INSERT INTO deploy_runs
               (project_id, started_at, finished_at, status, from_commit, to_commit, commit_log, output, exit_code)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (project_id, started_at, finished_at, status, from_commit, to_commit, commit_log, output, exit_code),
        )
        if status == "success":
            conn.execute(
                "UPDATE projects SET last_deployed_commit = ? WHERE id = ?",
                (to_commit, project_id),
            )
        conn.commit()

        result_row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        response = project_to_dict(result_row, conn)
        response["last_output"] = output
        response["last_status"] = status
        conn.close()
        return jsonify(response)
    finally:
        with _running_lock:
            _running_project_ids.discard(project_id)


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5064))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug, host="0.0.0.0", port=port)

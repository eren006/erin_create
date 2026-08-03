"""霍格沃茨校园报纸 Flask 站点。"""

import os
import sqlite3

from flask import Flask, abort, render_template

from newspaper_service import archive_days, build_issue, current_day

app = Flask(__name__)


@app.get("/")
def index():
    try:
        latest = archive_days(current_day())[0]
        return render_template("newspaper.html", issue=build_issue(latest))
    except sqlite3.OperationalError:
        return render_template("newspaper_unavailable.html"), 503


@app.get("/issue/<int:end_day>")
def issue(end_day: int):
    try:
        available = archive_days(current_day())
        if end_day not in available:
            abort(404)
        return render_template("newspaper.html", issue=build_issue(end_day))
    except sqlite3.OperationalError:
        return render_template("newspaper_unavailable.html"), 503


@app.get("/health")
def health():
    try:
        current_day()
        return {"status": "ok"}
    except sqlite3.OperationalError:
        return {"status": "waiting_for_database"}, 503


if __name__ == "__main__":
    app.run(
        host=os.getenv("NEWSPAPER_HOST", "0.0.0.0"),
        port=int(os.getenv("NEWSPAPER_PORT", "5001")),
        debug=False,
    )

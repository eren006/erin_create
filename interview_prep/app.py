import os

from flask import Flask, render_template

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html", active="home")


@app.route("/sql")
def sql_page():
    return render_template("sql.html", active="sql")


@app.route("/pandas")
def pandas_page():
    return render_template("pandas.html", active="pandas")


@app.route("/basics")
def basics_page():
    return render_template("basics.html", active="basics")


@app.route("/learn")
def learn_page():
    return render_template("learn.html", active="learn")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5012))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)

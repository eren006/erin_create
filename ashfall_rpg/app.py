import os
import json
import random
import sqlite3
import uuid
from datetime import datetime, timezone

from flask import Flask, render_template, request, session, redirect, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "ashfall.db")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24).hex()
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# ---------------------------------------------------------------------------
# Game data
# ---------------------------------------------------------------------------

REALMS = [
    {"name": "Mortal Body", "next_needed": 18, "hp": 36, "qi": 14, "atk": 6, "def": 3},
    {"name": "Qi Gathering", "next_needed": 32, "hp": 52, "qi": 24, "atk": 9, "def": 5},
    {"name": "Foundation Establishment", "next_needed": 50, "hp": 74, "qi": 36, "atk": 13, "def": 8},
    {"name": "Core Formation", "next_needed": 75, "hp": 100, "qi": 52, "atk": 18, "def": 12},
    {"name": "Ascendant", "next_needed": None, "hp": 130, "qi": 75, "atk": 26, "def": 17},
]

ROOTS = {
    "ember": {
        "label": "Ember Root",
        "tagline": "A restless heat that answers with fire.",
        "skill_name": "Cinder Strike",
        "skill_cost": 6,
        "skill_desc": "A searing blow that burns through armor.",
    },
    "tide": {
        "label": "Tide Root",
        "tagline": "A calm current that mends as it moves.",
        "skill_name": "Flowing Ward",
        "skill_cost": 6,
        "skill_desc": "Restores health and softens the next blow.",
    },
    "stone": {
        "label": "Stone Root",
        "tagline": "An unshaken weight, slow but unbreakable.",
        "skill_name": "Bulwark",
        "skill_cost": 7,
        "skill_desc": "Braces against the next attack, cutting its force sharply.",
    },
    "gale": {
        "label": "Gale Root",
        "tagline": "A quick wind that strikes twice before it's noticed.",
        "skill_name": "Wind Cutter",
        "skill_cost": 5,
        "skill_desc": "Two swift cuts, faster than the eye follows.",
    },
}

LOCATIONS = [
    {
        "key": "village",
        "title": "The Weathered Village",
        "intro": (
            "Smoke curls from a dozen chimneys at the foot of Ashfall Peak. The elders say the "
            "mountain has been silent for a generation — no cultivator has returned from its "
            "summit. You were born in the shadow of that silence, and today you leave it behind. "
            "A worn shrine at the village edge marks where wandering cultivators used to meditate "
            "before the climb."
        ),
        "enemy": None,
        "clear_text": "You sit before the shrine and draw your first real breath of Qi. The road out of the village opens ahead of you.",
        "reward": 10,
    },
    {
        "key": "forest",
        "title": "The Whispering Forest",
        "intro": (
            "The trees here grow close and the light turns grey-green before it reaches the ground. "
            "Something moves between the trunks — low, quick, hungry. A bramble wolf, fur matted "
            "with old frost, steps into the path and does not move aside."
        ),
        "enemy": {"name": "Bramble Wolf", "hp": 22, "atk": 4, "def": 1},
        "clear_text": "The wolf yields the path. Deeper in the forest you find a hollow where the Qi pools thick enough to taste.",
        "reward": 18,
    },
    {
        "key": "ruins",
        "title": "The Sunken Ruins",
        "intro": (
            "Stone columns lean into a lake that swallowed a shrine centuries ago. A warden of "
            "carved rock still stands guard at the threshold, algae grown thick in the grooves "
            "of its armor, eyes lit with a Qi that has not noticed you are trespassing — yet."
        ),
        "enemy": {"name": "Ruin Warden", "hp": 48, "atk": 8, "def": 4},
        "clear_text": "The warden's light fades and the ruins go quiet. Beyond the broken gate, the path begins to climb in earnest.",
        "reward": 28,
    },
    {
        "key": "peak",
        "title": "Ashfall Peak",
        "intro": (
            "The air thins and turns to ash on your tongue. At the summit a figure of cinder and "
            "old armor waits where the last cultivator to climb this far must have fallen. The "
            "Ashbound Sentinel does not speak. It simply raises its blade."
        ),
        "enemy": {"name": "The Ashbound Sentinel", "hp": 85, "atk": 12, "def": 6},
        "clear_text": None,
        "reward": 0,
        "min_realm": 2,
        "gate_text": (
            "The mountain wind pushes you back before you take three steps. Your Qi is not yet deep "
            "enough to stand against what waits at the summit — you must reach Foundation Establishment first."
        ),
    },
]

MAX_LOG = 6


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS players (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            state TEXT NOT NULL
        )"""
    )
    conn.commit()
    conn.close()


def new_state(name, root_key):
    realm = REALMS[0]
    root = ROOTS[root_key]
    return {
        "name": name,
        "root": root_key,
        "realm_index": 0,
        "insight": 0,
        "hp": realm["hp"],
        "max_hp": realm["hp"],
        "qi": realm["qi"],
        "max_qi": realm["qi"],
        "atk": realm["atk"],
        "def": realm["def"],
        "location_index": 0,
        "location_state": "intro",  # intro | combat | cleared
        "enemy_hp": None,
        "enemy_max_hp": None,
        "log": [f"You set out from {LOCATIONS[0]['title']} with nothing but a name and a root of {root['label']}."],
        "game_over": False,
        "victory": False,
    }


def load_state():
    pid = session.get("player_id")
    if not pid:
        return None
    conn = get_db()
    row = conn.execute("SELECT state FROM players WHERE id = ?", (pid,)).fetchone()
    conn.close()
    if not row:
        return None
    return json.loads(row["state"])


def save_state(state):
    pid = session.get("player_id")
    conn = get_db()
    conn.execute("UPDATE players SET state = ? WHERE id = ?", (json.dumps(state), pid))
    conn.commit()
    conn.close()


def create_player(name, root_key):
    pid = uuid.uuid4().hex
    session["player_id"] = pid
    state = new_state(name, root_key)
    conn = get_db()
    conn.execute(
        "INSERT INTO players (id, created_at, state) VALUES (?, ?, ?)",
        (pid, datetime.now(timezone.utc).isoformat(), json.dumps(state)),
    )
    conn.commit()
    conn.close()
    return state


def log(state, message):
    state["log"].insert(0, message)
    state["log"] = state["log"][:MAX_LOG]


# ---------------------------------------------------------------------------
# Combat helpers
# ---------------------------------------------------------------------------

def clamp(value, low, high):
    return max(low, min(high, value))


def player_attack_damage(state, defense):
    base = state["atk"] - defense
    return max(1, base + random.randint(-2, 2))


def enemy_attack_damage(state, enemy_atk, multiplier=1.0):
    base = (enemy_atk - state["def"]) * multiplier
    return max(1, round(base + random.randint(-1, 2)))


def enemy_turn(state, enemy, dmg_multiplier=1.0):
    if state["enemy_hp"] <= 0:
        return
    dmg = enemy_attack_damage(state, enemy["atk"], dmg_multiplier)
    state["hp"] = clamp(state["hp"] - dmg, 0, state["max_hp"])
    log(state, f"The {enemy['name']} strikes back for {dmg} damage.")
    if state["hp"] <= 0:
        defeat(state)


def defeat(state):
    state["game_over"] = False
    state["location_state"] = "intro"
    state["enemy_hp"] = None
    state["enemy_max_hp"] = None
    state["hp"] = state["max_hp"]
    state["qi"] = state["max_qi"]
    log(state, "You are forced back, but your footing holds. You catch your breath and steady your Qi before trying again.")


def start_combat(state, location):
    enemy = location["enemy"]
    state["location_state"] = "combat"
    state["enemy_hp"] = enemy["hp"]
    state["enemy_max_hp"] = enemy["hp"]
    log(state, f"The {enemy['name']} blocks your path.")


def win_combat(state, location):
    state["location_state"] = "cleared"
    state["enemy_hp"] = None
    reward = location["reward"]
    state["insight"] += reward
    log(state, f"The {location['enemy']['name']} falls. You feel {reward} points of Insight settle into your core.")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    state = load_state()
    if not state:
        return render_template("creation.html", roots=ROOTS)
    return render_game(state)


@app.route("/create", methods=["POST"])
def create():
    name = (request.form.get("name") or "").strip()[:24]
    root_key = request.form.get("root")
    if not name:
        name = "Nameless Wanderer"
    if root_key not in ROOTS:
        root_key = "ember"
    state = create_player(name, root_key)
    save_state(state)
    return redirect(url_for("index"))


@app.route("/action", methods=["POST"])
def action():
    state = load_state()
    if not state:
        return redirect(url_for("index"))

    act = request.form.get("act")
    location = LOCATIONS[state["location_index"]]
    root = ROOTS[state["root"]]

    if act == "meditate" and state["location_state"] in ("intro", "cleared"):
        gained = random.randint(6, 10)
        state["insight"] += gained
        heal = round(state["max_hp"] * 0.25)
        qi_heal = round(state["max_qi"] * 0.25)
        state["hp"] = clamp(state["hp"] + heal, 0, state["max_hp"])
        state["qi"] = clamp(state["qi"] + qi_heal, 0, state["max_qi"])
        log(state, f"You meditate quietly and gain {gained} Insight, recovering some strength.")

    elif act == "breakthrough" and state["location_state"] in ("intro", "cleared"):
        realm = REALMS[state["realm_index"]]
        needed = realm["next_needed"]
        if needed is not None and state["insight"] >= needed and state["realm_index"] < len(REALMS) - 1:
            state["realm_index"] += 1
            new_realm = REALMS[state["realm_index"]]
            state["insight"] = 0
            state["max_hp"] = new_realm["hp"]
            state["max_qi"] = new_realm["qi"]
            state["atk"] = new_realm["atk"]
            state["def"] = new_realm["def"]
            state["hp"] = state["max_hp"]
            state["qi"] = state["max_qi"]
            log(state, f"Your cultivation breaks through to {new_realm['name']}. Power floods your meridians.")

    elif act == "advance" and state["location_state"] == "cleared":
        if state["location_index"] >= len(LOCATIONS) - 1:
            pass
        else:
            next_location = LOCATIONS[state["location_index"] + 1]
            min_realm = next_location.get("min_realm")
            if min_realm is not None and state["realm_index"] < min_realm:
                log(state, next_location["gate_text"])
            else:
                state["location_index"] += 1
                state["location_state"] = "intro"
                state["enemy_hp"] = None
                log(state, f"You travel onward to {next_location['title']}.")

    elif act == "engage" and state["location_state"] == "intro" and location["enemy"]:
        start_combat(state, location)

    elif act == "engage" and state["location_state"] == "intro" and not location["enemy"]:
        state["location_state"] = "cleared"
        log(state, location["clear_text"])

    elif act in ("attack", "skill", "defend") and state["location_state"] == "combat":
        enemy = location["enemy"]
        dmg_multiplier = 1.0

        if act == "attack":
            dmg = player_attack_damage(state, enemy["def"])
            state["enemy_hp"] -= dmg
            log(state, f"You strike the {enemy['name']} for {dmg} damage.")

        elif act == "skill":
            cost = root["skill_cost"]
            if state["qi"] < cost:
                log(state, f"Not enough Qi to unleash {root['skill_name']}.")
                save_state(state)
                return redirect(url_for("index"))
            state["qi"] -= cost
            root_key = state["root"]
            if root_key == "ember":
                dmg = max(1, round((state["atk"] * 1.8) - enemy["def"]))
                state["enemy_hp"] -= dmg
                log(state, f"{root['skill_name']} sears the {enemy['name']} for {dmg} damage.")
            elif root_key == "tide":
                heal = round(state["max_hp"] * 0.3)
                state["hp"] = clamp(state["hp"] + heal, 0, state["max_hp"])
                dmg_multiplier = 0.5
                log(state, f"{root['skill_name']} mends {heal} health and softens the coming blow.")
            elif root_key == "stone":
                dmg_multiplier = 0.3
                log(state, f"{root['skill_name']} braces you against the {enemy['name']}'s next attack.")
            elif root_key == "gale":
                dmg1 = max(1, round((state["atk"] * 0.9) - enemy["def"]))
                dmg2 = max(1, round((state["atk"] * 0.9) - enemy["def"]))
                state["enemy_hp"] -= (dmg1 + dmg2)
                log(state, f"{root['skill_name']} lands two cuts for {dmg1} and {dmg2} damage.")

        elif act == "defend":
            dmg_multiplier = 0.5
            regen = 4
            state["qi"] = clamp(state["qi"] + regen, 0, state["max_qi"])
            log(state, "You brace yourself, ready to absorb the next blow.")

        if state["enemy_hp"] <= 0:
            win_combat(state, location)
        else:
            enemy_turn(state, enemy, dmg_multiplier)
            if not state["game_over"] and state["hp"] > 0 and state["location_index"] == len(LOCATIONS) - 1 and state["location_state"] == "cleared":
                pass

    # victory check: cleared the final location
    if (
        state["location_index"] == len(LOCATIONS) - 1
        and state["location_state"] == "cleared"
        and not state.get("victory")
    ):
        state["victory"] = True
        log(state, "The Ashbound Sentinel crumbles to cinder and wind. Ashfall Peak is silent again — but this time, you are the one standing.")

    save_state(state)
    return redirect(url_for("index"))


@app.route("/reset", methods=["POST"])
def reset():
    pid = session.get("player_id")
    if pid:
        conn = get_db()
        conn.execute("DELETE FROM players WHERE id = ?", (pid,))
        conn.commit()
        conn.close()
    session.pop("player_id", None)
    return redirect(url_for("index"))


def render_game(state):
    location = LOCATIONS[state["location_index"]]
    realm = REALMS[state["realm_index"]]
    root = ROOTS[state["root"]]
    next_needed = realm["next_needed"]
    can_breakthrough = (
        next_needed is not None
        and state["insight"] >= next_needed
        and state["location_state"] in ("intro", "cleared")
    )
    return render_template(
        "game.html",
        s=state,
        location=location,
        enemy=location.get("enemy"),
        realm=realm,
        realms=REALMS,
        root=root,
        can_breakthrough=can_breakthrough,
        is_last_location=state["location_index"] == len(LOCATIONS) - 1,
    )


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5060))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug, host="0.0.0.0", port=port)

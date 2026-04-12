import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from openai import OpenAI

# ---------------------------------------------------
# Setup
# ---------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
BASE_CONFIG_PATH = CONFIG_DIR / "base.yaml"
CASES_DIR = CONFIG_DIR / "cases"
INSTANCE_DIR = BASE_DIR / "instance"
SESSIONS_DIR = INSTANCE_DIR / "sessions"

INSTANCE_DIR.mkdir(exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(BASE_DIR / ".env")

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "replace-me")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_SUPERVISION_INTERVAL = 5
MAX_HISTORY_LINES = 40

# ---------------------------------------------------
# Load config
# ---------------------------------------------------

def load_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

base_config = load_yaml(BASE_CONFIG_PATH)
base_agents = base_config["agents"]

# ---------------------------------------------------
# Cases
# ---------------------------------------------------

def discover_cases():
    cases = {}
    for path in sorted(CASES_DIR.glob("case_*.yaml")):
        data = load_yaml(path)
        scenario = data.get("scenario", {})
        case_id = scenario.get("id") or path.stem
        cases[case_id] = {
            "scenario": scenario,
            "patient": data["patient"],
        }
    return cases

CASES = discover_cases()
DEFAULT_CASE_ID = list(CASES.keys())[0]

def get_case(case_id):
    return CASES.get(case_id, CASES[DEFAULT_CASE_ID])

# ---------------------------------------------------
# Gender handling
# ---------------------------------------------------

def get_patient_label(case_id):
    gender = get_case(case_id)["scenario"].get("gender", "female")

    if gender == "male":
        return "Patient"
    if gender == "diverse":
        return "Patient:in"
    return "Patientin"

# ---------------------------------------------------
# Session
# ---------------------------------------------------

def session_file():
    sid = session.get("id")
    if not sid:
        sid = str(uuid.uuid4())
        session["id"] = sid
    return SESSIONS_DIR / f"{sid}.json"

def load_state():
    path = session_file()
    if not path.exists():
        return create_state()

    with open(path, "r") as f:
        return json.load(f)

def save_state(state):
    with open(session_file(), "w") as f:
        json.dump(state, f, indent=2)

def create_state(case_id=None):
    return {
        "case_id": case_id or DEFAULT_CASE_ID,
        "dialog_history": [],
        "therapist_turns": [],
        "therapist_turn_count": 0,
        "supervision_history": [],
        "latest_supervision": None,
        "latest_evaluation": None,
        "supervision_interval": DEFAULT_SUPERVISION_INTERVAL,
    }

# ---------------------------------------------------
# Text normalization
# ---------------------------------------------------

def rewrite_action(text, case_id):
    label = get_patient_label(case_id)

    text = re.sub(r"^(Ich|ich)\s+", f"{label} ", text)

    verbs = {
        "seufze": "seufzt",
        "schaue": "schaut",
        "blicke": "blickt",
        "zögere": "zögert",
        "schweige": "schweigt"
    }

    for k, v in verbs.items():
        text = re.sub(rf"\b{k}\b", v, text)

    if not text.lower().startswith(label.lower()):
        text = f"{label} {text}"

    return text

def normalize(text, case_id):
    m = re.match(r"\*(.+?)\*\s*(.*)", text, re.DOTALL)
    if m:
        action = rewrite_action(m.group(1), case_id)
        spoken = m.group(2)
        return f"[*{action}*]\n\n{spoken}"
    return text

# ---------------------------------------------------
# LLM Calls
# ---------------------------------------------------

def llm(system, user):
    r = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.4,
    )
    return r.choices[0].message.content.strip()

def call_patient(case_id, text, history):
    case = get_case(case_id)
    system = case["patient"]["instructions"]
    prompt = "\n".join(history[-MAX_HISTORY_LINES:]) + "\n\n" + text
    return normalize(llm(system, prompt), case_id)

def call_supervisor(case_id, turns, reply):
    label = get_patient_label(case_id)
    system = base_agents["supervisor"]["instructions"]
    system = system.replace("Patientin", label)

    text = "\n".join(turns)
    if reply:
        text += "\n\n" + reply

    return llm(system, text)

def call_rater(case_id, turns, dialog):
    label = get_patient_label(case_id)
    system = base_agents["rater"]["instructions"]
    system = system.replace("Patientin", label)

    text = "\n".join(dialog[-80:])
    return llm(system, text)

# ---------------------------------------------------
# Routes
# ---------------------------------------------------

@app.route("/")
def index():
    state = load_state()
    return render_template("index.html", scenario=get_case(state["case_id"])["scenario"])

@app.route("/api/state")
def state():
    s = load_state()
    return jsonify(s)

@app.route("/api/turn", methods=["POST"])
def turn():
    s = load_state()
    text = request.json["text"]

    s["therapist_turn_count"] += 1
    s["therapist_turns"].append(text)
    s["dialog_history"].append(f"THERAPEUT: {text}")

    reply = call_patient(s["case_id"], text, s["dialog_history"])

    label = get_patient_label(s["case_id"]).upper()
    s["dialog_history"].append(f"{label}: {reply}")

    supervision = None
    if s["therapist_turn_count"] % s["supervision_interval"] == 0:
        supervision = call_supervisor(
            s["case_id"],
            s["therapist_turns"][-3:],
            reply
        )
        s["latest_supervision"] = supervision
        s["supervision_history"].append({
            "number": len(s["supervision_history"]) + 1,
            "text": supervision
        })

    save_state(s)

    return jsonify({
        "patient_reply": reply,
        "patient_label": label,
        "latest_supervision": s.get("latest_supervision"),
        "supervision_history": s.get("supervision_history"),
        "latest_evaluation": s.get("latest_evaluation"),
        "therapist_turn_count": s["therapist_turn_count"]
    })

@app.route("/api/evaluation", methods=["POST"])
def evaluation():
    s = load_state()

    eval_text = call_rater(
        s["case_id"],
        s["therapist_turns"],
        s["dialog_history"]
    )

    s["latest_evaluation"] = eval_text
    save_state(s)

    return jsonify({"evaluation_text": eval_text})

@app.route("/api/reset", methods=["POST"])
def reset():
    s = create_state()
    save_state(s)
    return jsonify({"ok": True})

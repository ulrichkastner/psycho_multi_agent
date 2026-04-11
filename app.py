import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "psy_training.yaml"
INSTANCE_DIR = BASE_DIR / "instance"
SESSIONS_DIR = INSTANCE_DIR / "sessions"

INSTANCE_DIR.mkdir(exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(BASE_DIR / ".env")

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "replace-me-with-a-long-random-secret")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,  # auf True setzen, falls gewünscht
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

scenario = config.get("scenario", {})
agents = config["agents"]
orchestration = config.get("orchestration", {})

eval_cfg = orchestration.get("evaluation_trigger", [])
EVAL_AFTER = eval_cfg[0].get("after_therapist_turns", 12) if eval_cfg else 12

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
BETA_PASSWORD = os.getenv("BETA_PASSWORD", "change-me")
MAX_TURNS = int(os.getenv("MAX_TURNS", "20"))
MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "3000"))
SUPERVISOR_EVERY_N_TURNS = 2
MAX_HISTORY_LINES = 40


def _session_file(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def create_empty_state() -> Dict[str, Any]:
    return {
        "dialog_history": [],
        "therapist_turns": [],
        "therapist_turn_count": 0,
        "last_patient_reply": None,
    }


def get_session_id() -> str:
    sid = session.get("chat_session_id")
    if not sid:
        sid = str(uuid.uuid4())
        session["chat_session_id"] = sid
    return sid


def load_state() -> Dict[str, Any]:
    sid = get_session_id()
    path = _session_file(sid)

    if not path.exists():
        state = create_empty_state()
        save_state(state)
        return state

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        state = create_empty_state()
        save_state(state)
        return state


def save_state(state: Dict[str, Any]) -> None:
    sid = get_session_id()
    path = _session_file(sid)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def reset_state() -> Dict[str, Any]:
    state = create_empty_state()
    save_state(state)
    return state


def is_logged_in() -> bool:
    return session.get("beta_logged_in", False) is True


def require_login():
    if not is_logged_in():
        return redirect(url_for("login"))
    return None


def llm_completion(system_text: str, user_text: str, temperature: float = 0.4) -> str:
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        temperature=temperature,
    )
    return (response.choices[0].message.content or "").strip()


def call_agent(agent_name: str, user_text: str, dialog_history: List[str]) -> str:
    agent = agents[agent_name]
    instructions = agent["instructions"]

    history_text = "\n".join(dialog_history[-MAX_HISTORY_LINES:])
    prompt = (
        "Bisheriger Dialog:\n"
        f"{history_text}\n\n"
        "Aktueller Beitrag, auf den du reagieren sollst:\n"
        f"{user_text}"
    )

    return llm_completion(instructions, prompt, temperature=0.4)


def call_supervisor(last_therapist_turns: List[str], last_patient_reply: Optional[str]) -> str:
    instructions = agents["supervisor"]["instructions"]

    text = "Letzte Interventionen des Therapeuten:\n"
    for t in last_therapist_turns:
        text += f"- {t}\n"

    if last_patient_reply:
        text += f"\nLetzte Antwort der Patientin:\n{last_patient_reply}\n"

    return llm_completion(instructions, text, temperature=0.4)


def call_rater(full_therapist_transcript: List[str], full_dialog: List[str]) -> str:
    instructions = agents["rater"]["instructions"]

    text = "Gesamter Dialog:\n" + "\n".join(full_dialog[-80:]) + "\n\n"
    text += "Therapeuten-Interventionen im Überblick:\n"
    for i, t in enumerate(full_therapist_transcript, start=1):
        text += f"{i}. {t}\n"

    return llm_completion(instructions, text, temperature=0.3)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        password = request.form.get("password", "").strip()
        if password == BETA_PASSWORD:
            session["beta_logged_in"] = True
            get_session_id()
            return redirect(url_for("index"))
        error = "Falsches Passwort."
    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def index():
    gate = require_login()
    if gate:
        return gate
    return render_template("index.html", scenario=scenario, eval_after=EVAL_AFTER)


@app.route("/api/state", methods=["GET"])
def api_state():
    if not is_logged_in():
        return jsonify({"error": "Nicht autorisiert"}), 401

    state = load_state()
    return jsonify(
        {
            "dialog_history": state["dialog_history"],
            "therapist_turn_count": state["therapist_turn_count"],
        }
    )


@app.route("/api/reset", methods=["POST"])
def api_reset():
    if not is_logged_in():
        return jsonify({"error": "Nicht autorisiert"}), 401

    reset_state()
    return jsonify(
        {
            "ok": True,
            "message": "Sitzung zurückgesetzt. Beginne mit einer neuen offenen Frage an Laura."
        }
    )


@app.route("/api/turn", methods=["POST"])
def api_turn():
    if not is_logged_in():
        return jsonify({"error": "Nicht autorisiert"}), 401

    state = load_state()
    data = request.get_json(force=True) or {}
    therapist_text = (data.get("text") or "").strip()

    if not therapist_text:
        return jsonify({"error": "Text fehlt"}), 400

    if len(therapist_text) > MAX_INPUT_LENGTH:
        return jsonify({"error": f"Eingabe zu lang. Maximal {MAX_INPUT_LENGTH} Zeichen."}), 400

    if state["therapist_turn_count"] >= MAX_TURNS:
        return jsonify({
            "error": f"Maximale Anzahl an Therapeuten-Zügen ({MAX_TURNS}) erreicht. Bitte Evaluation nutzen oder Sitzung zurücksetzen."
        }), 400

    state["therapist_turn_count"] += 1
    state["therapist_turns"].append(therapist_text)
    state["dialog_history"].append(f"THERAPEUT: {therapist_text}")

    try:
        patient_reply = call_agent("patient", therapist_text, state["dialog_history"])
    except Exception as e:
        return jsonify({"error": f"Fehler beim Aufruf der Patientin: {str(e)}"}), 500

    state["last_patient_reply"] = patient_reply
    state["dialog_history"].append(f"PATIENTIN: {patient_reply}")

    supervision_feedback = None
    evaluation_text = None

    if state["therapist_turn_count"] % SUPERVISOR_EVERY_N_TURNS == 0:
        try:
            supervision_feedback = call_supervisor(
                state["therapist_turns"][-2:],
                state["last_patient_reply"],
            )
            state["dialog_history"].append(f"SUPERVISION: {supervision_feedback}")
        except Exception as e:
            supervision_feedback = f"Fehler beim Supervisor-Aufruf: {str(e)}"

    if state["therapist_turn_count"] == EVAL_AFTER:
        try:
            evaluation_text = call_rater(state["therapist_turns"], state["dialog_history"])
        except Exception as e:
            evaluation_text = f"Fehler beim Evaluator-Aufruf: {str(e)}"

    save_state(state)

    return jsonify(
        {
            "patient_reply": patient_reply,
            "supervision_feedback": supervision_feedback,
            "evaluation": evaluation_text,
            "therapist_turn_count": state["therapist_turn_count"],
        }
    )


@app.route("/api/evaluation", methods=["POST"])
def api_evaluation():
    if not is_logged_in():
        return jsonify({"error": "Nicht autorisiert"}), 401

    state = load_state()

    try:
        evaluation_text = call_rater(state["therapist_turns"], state["dialog_history"])
    except Exception as e:
        return jsonify({"error": f"Fehler beim Evaluator-Aufruf: {str(e)}"}), 500

    return jsonify({"evaluation_text": evaluation_text})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
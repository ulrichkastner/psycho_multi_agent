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
app.secret_key = os.getenv("FLASK_SECRET_KEY", "replace-me-with-a-long-random-secret")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
BETA_PASSWORD = os.getenv("BETA_PASSWORD", "change-me")
MAX_TURNS = int(os.getenv("MAX_TURNS", "20"))
MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "3000"))
DEFAULT_SUPERVISION_INTERVAL = int(os.getenv("DEFAULT_SUPERVISION_INTERVAL", "5"))
MAX_HISTORY_LINES = 40


def load_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


base_config = load_yaml(BASE_CONFIG_PATH)
base_agents = base_config["agents"]
orchestration = base_config.get("orchestration", {})

eval_cfg = orchestration.get("evaluation_trigger", [])
EVAL_AFTER = eval_cfg[0].get("after_therapist_turns", 12) if eval_cfg else 12


def validate_case_config(case_data: Dict[str, Any], filename: str) -> List[str]:
    errors: List[str] = []

    if not isinstance(case_data, dict):
        return [f"{filename}: YAML-Inhalt ist kein Dictionary."]

    scenario = case_data.get("scenario")
    patient = case_data.get("patient")

    if not isinstance(scenario, dict):
        errors.append(f"{filename}: 'scenario' fehlt oder ist kein Objekt.")
    else:
        if not scenario.get("id"):
            errors.append(f"{filename}: 'scenario.id' fehlt.")
        if not scenario.get("title"):
            errors.append(f"{filename}: 'scenario.title' fehlt.")

        gender = scenario.get("gender")
        if gender is not None and gender not in {"male", "female", "diverse"}:
            errors.append(
                f"{filename}: 'scenario.gender' muss 'male', 'female' oder 'diverse' sein."
            )

        role_label = scenario.get("role_label")
        if role_label is not None and (not isinstance(role_label, str) or not role_label.strip()):
            errors.append(
                f"{filename}: 'scenario.role_label' muss ein nicht-leerer String sein."
            )

    if not isinstance(patient, dict):
        errors.append(f"{filename}: 'patient' fehlt oder ist kein Objekt.")
    else:
        if not patient.get("instructions"):
            errors.append(f"{filename}: 'patient.instructions' fehlt.")

    return errors


INVALID_CASES: List[Dict[str, Any]] = []


def discover_cases() -> Dict[str, Dict[str, Any]]:
    cases: Dict[str, Dict[str, Any]] = {}
    seen_ids = set()

    INVALID_CASES.clear()

    for path in sorted(CASES_DIR.glob("case_*.yaml")):
        try:
            data = load_yaml(path)
        except Exception as e:
            INVALID_CASES.append({
                "file": path.name,
                "errors": [f"{path.name}: YAML konnte nicht geladen werden: {str(e)}"]
            })
            continue

        errors = validate_case_config(data, path.name)
        if errors:
            INVALID_CASES.append({
                "file": path.name,
                "errors": errors
            })
            continue

        scenario = data["scenario"]
        case_id = scenario["id"]

        if case_id in seen_ids:
            INVALID_CASES.append({
                "file": path.name,
                "errors": [f"{path.name}: doppelte scenario.id '{case_id}'."]
            })
            continue

        seen_ids.add(case_id)

        cases[case_id] = {
            "file": path.name,
            "scenario": scenario,
            "patient": data["patient"],
        }

    return cases


CASES = discover_cases()
DEFAULT_CASE_ID = sorted(CASES.keys())[0] if CASES else None

if not CASES:
    raise RuntimeError("Keine gültigen Fälle gefunden. Bitte YAML-Dateien in config/cases/ prüfen.")


def get_case(case_id: Optional[str]) -> Dict[str, Any]:
    if case_id in CASES:
        return CASES[case_id]
    if DEFAULT_CASE_ID:
        return CASES[DEFAULT_CASE_ID]
    raise RuntimeError("Keine Fälle gefunden.")


def get_patient_label(case_id: str) -> str:
    case = get_case(case_id)
    scenario = case.get("scenario", {})

    role_label = scenario.get("role_label")
    if isinstance(role_label, str) and role_label.strip():
        return role_label.strip()

    gender = scenario.get("gender", "female")

    if gender == "male":
        return "Patient"
    if gender == "diverse":
        return "Patient:in"
    return "Patientin"


def _session_file(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def create_empty_state(case_id: Optional[str] = None) -> Dict[str, Any]:
    selected_case_id = case_id or DEFAULT_CASE_ID
    return {
        "case_id": selected_case_id,
        "mode": "training",
        "dialog_history": [],
        "therapist_turns": [],
        "therapist_turn_count": 0,
        "last_patient_reply": None,
        "latest_supervision": None,
        "latest_evaluation": None,
        "supervision_history": [],
        "supervision_interval": DEFAULT_SUPERVISION_INTERVAL,
    }


def get_session_id() -> str:
    sid = session.get("chat_session_id")
    if not sid:
        sid = str(uuid.uuid4())
        session["chat_session_id"] = sid
    return sid


def save_state(state: Dict[str, Any]) -> None:
    sid = get_session_id()
    path = _session_file(sid)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_state() -> Dict[str, Any]:
    sid = get_session_id()
    path = _session_file(sid)

    if not path.exists():
        state = create_empty_state()
        save_state(state)
        return state

    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = create_empty_state()
        save_state(state)
        return state

    if "case_id" not in state or state["case_id"] not in CASES:
        state["case_id"] = DEFAULT_CASE_ID
    if "latest_supervision" not in state:
        state["latest_supervision"] = None
    if "latest_evaluation" not in state:
        state["latest_evaluation"] = None
    if "supervision_history" not in state:
        state["supervision_history"] = []
    if "supervision_interval" not in state:
        state["supervision_interval"] = DEFAULT_SUPERVISION_INTERVAL

    cleaned_history = []
    latest_supervision = state.get("latest_supervision")
    latest_evaluation = state.get("latest_evaluation")

    for line in state.get("dialog_history", []):
        if isinstance(line, str) and line.startswith("SUPERVISION: "):
            if not latest_supervision:
                latest_supervision = line.replace("SUPERVISION: ", "", 1)
            continue
        if isinstance(line, str) and line.startswith("EVALUATION: "):
            if not latest_evaluation:
                latest_evaluation = line.replace("EVALUATION: ", "", 1)
            continue
        cleaned_history.append(line)

    state["dialog_history"] = cleaned_history
    state["latest_supervision"] = latest_supervision
    state["latest_evaluation"] = latest_evaluation

    return state


def reset_state(case_id: Optional[str] = None) -> Dict[str, Any]:
    state = create_empty_state(case_id=case_id)
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


def rewrite_action_to_neutral(action_text: str, case_id: str) -> str:
    label = get_patient_label(case_id)
    text = action_text.strip()

    text = re.sub(r"^(ich|Ich)\s+", f"{label} ", text)

    replacements = [
        (rf"\b{re.escape(label)} bin\b", f"{label} ist"),
        (rf"\b{re.escape(label)} schaue\b", f"{label} schaut"),
        (rf"\b{re.escape(label)} sehe\b", f"{label} schaut"),
        (rf"\b{re.escape(label)} seufze\b", f"{label} seufzt"),
        (rf"\b{re.escape(label)} schweige\b", f"{label} schweigt"),
        (rf"\b{re.escape(label)} zögere\b", f"{label} zögert"),
        (rf"\b{re.escape(label)} wirke\b", f"{label} wirkt"),
        (rf"\b{re.escape(label)} lache\b", f"{label} lacht"),
        (rf"\b{re.escape(label)} presse\b", f"{label} presst"),
        (rf"\b{re.escape(label)} atme\b", f"{label} atmet"),
        (rf"\b{re.escape(label)} fasse\b", f"{label} fasst"),
        (rf"\b{re.escape(label)} zucke\b", f"{label} zuckt"),
        (rf"\b{re.escape(label)} spiele\b", f"{label} spielt"),
        (rf"\b{re.escape(label)} blicke\b", f"{label} blickt"),
    ]

    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)

    if not text.lower().startswith(label.lower()):
        text = f"{label} {text[0].lower() + text[1:]}" if text else f"{label} reagiert"

    if text and text[-1] not in ".!?":
        text += "."

    return text


def normalize_patient_feedback(text: str, case_id: str) -> str:
    if not text:
        return ""

    normalized = text.strip()

    match = re.match(r"^\*(.+?)\*\s*(.*)$", normalized, flags=re.DOTALL)
    if match:
        action_text = match.group(1).strip()
        spoken_text = match.group(2).strip()
        action_text = rewrite_action_to_neutral(action_text, case_id)
        if spoken_text:
            return f"[*{action_text}*]\n\n{spoken_text}"
        return f"[*{action_text}*]"

    bracket_match = re.match(r"^\[\*?(.+?)\*?\]\s*(.*)$", normalized, flags=re.DOTALL)
    if bracket_match:
        action_text = bracket_match.group(1).strip()
        spoken_text = bracket_match.group(2).strip()
        action_text = rewrite_action_to_neutral(action_text, case_id)
        if spoken_text:
            return f"[*{action_text}*]\n\n{spoken_text}"
        return f"[*{action_text}*]"

    return normalized


def call_patient(case_id: str, user_text: str, dialog_history: List[str]) -> str:
    patient = get_case(case_id)["patient"]
    instructions = patient["instructions"]

    history_text = "\n".join(dialog_history[-MAX_HISTORY_LINES:])
    prompt = (
        "Bisheriger Dialog:\n"
        f"{history_text}\n\n"
        "Aktueller Beitrag, auf den du reagieren sollst:\n"
        f"{user_text}"
    )

    raw_reply = llm_completion(instructions, prompt, temperature=0.4)
    return normalize_patient_feedback(raw_reply, case_id)


def call_supervisor(case_id: str, last_therapist_turns: List[str], last_patient_reply: Optional[str]) -> str:
    label = get_patient_label(case_id)
    instructions = base_agents["supervisor"]["instructions"]

    instructions = instructions.replace("Patientinnen-Rolle", f"{label}-Rolle")
    instructions = instructions.replace("Patientin", label)
    instructions = instructions.replace("patientin", label.lower())

    text = "Letzte Interventionen des Therapeuten:\n"
    for t in last_therapist_turns:
        text += f"- {t}\n"

    if last_patient_reply:
        text += f"\nLetzte Antwort von {label.lower()}:\n{last_patient_reply}\n"

    return llm_completion(instructions, text, temperature=0.4)


def call_rater(case_id: str, full_therapist_transcript: List[str], full_dialog: List[str]) -> str:
    label = get_patient_label(case_id)
    instructions = base_agents["rater"]["instructions"]

    instructions = instructions.replace("Patientinnen", label)
    instructions = instructions.replace("Patientin", label)
    instructions = instructions.replace("patientin", label.lower())

    text = "Gesamter Dialog:\n" + "\n".join(full_dialog[-80:]) + "\n\n"
    text += f"Rollenbezeichnung im Fall: {label}\n\n"
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

    state = load_state()

    case_options = [
        {
            "id": case_id,
            "title": case_data["scenario"].get("title", case_id),
        }
        for case_id, case_data in sorted(CASES.items())
    ]

    current_case = get_case(state["case_id"])

    return render_template(
        "index.html",
        scenario=current_case["scenario"],
        eval_after=EVAL_AFTER,
        default_supervision_interval=DEFAULT_SUPERVISION_INTERVAL,
        case_options=case_options,
        current_case_id=state["case_id"],
    )


@app.route("/api/state", methods=["GET"])
def api_state():
    if not is_logged_in():
        return jsonify({"error": "Nicht autorisiert"}), 401

    state = load_state()
    current_case = get_case(state["case_id"])

    return jsonify(
        {
            "case_id": state["case_id"],
            "scenario": current_case["scenario"],
            "dialog_history": state["dialog_history"],
            "therapist_turn_count": state["therapist_turn_count"],
            "latest_supervision": state.get("latest_supervision"),
            "latest_evaluation": state.get("latest_evaluation"),
            "supervision_history": state.get("supervision_history", []),
            "supervision_interval": state.get("supervision_interval", DEFAULT_SUPERVISION_INTERVAL),
            "patient_label": get_patient_label(state["case_id"]).upper(),
            "invalid_cases": INVALID_CASES,
            "cases": [
                {
                    "id": case_id,
                    "title": case_data["scenario"].get("title", case_id),
                }
                for case_id, case_data in sorted(CASES.items())
            ],
        }
    )


@app.route("/api/settings", methods=["POST"])
def api_settings():
    if not is_logged_in():
        return jsonify({"error": "Nicht autorisiert"}), 401

    state = load_state()
    data = request.get_json(force=True) or {}

    interval = data.get("supervision_interval", DEFAULT_SUPERVISION_INTERVAL)
    case_id = data.get("case_id", state["case_id"])

    try:
        interval = int(interval)
    except (TypeError, ValueError):
        return jsonify({"error": "Supervisionsintervall muss eine ganze Zahl sein."}), 400

    if interval < 1 or interval > 50:
        return jsonify({"error": "Supervisionsintervall muss zwischen 1 und 50 liegen."}), 400

    if case_id not in CASES:
        return jsonify({"error": "Ungültiger Fall."}), 400

    case_changed = case_id != state["case_id"]

    if case_changed:
        state = create_empty_state(case_id=case_id)

    state["supervision_interval"] = interval
    save_state(state)

    current_case = get_case(state["case_id"])

    return jsonify(
        {
            "ok": True,
            "case_changed": case_changed,
            "case_id": state["case_id"],
            "scenario": current_case["scenario"],
            "patient_label": get_patient_label(state["case_id"]).upper(),
            "supervision_interval": interval,
            "message": (
                f"Fall gewechselt und Sitzung zurückgesetzt. Supervisionsintervall auf {interval} gesetzt."
                if case_changed
                else f"Supervisionsintervall auf {interval} gesetzt."
            ),
        }
    )


@app.route("/api/reset", methods=["POST"])
def api_reset():
    if not is_logged_in():
        return jsonify({"error": "Nicht autorisiert"}), 401

    state = load_state()
    state = reset_state(case_id=state["case_id"])

    return jsonify(
        {
            "ok": True,
            "message": "Sitzung zurückgesetzt.",
            "case_id": state["case_id"],
            "patient_label": get_patient_label(state["case_id"]).upper(),
            "supervision_interval": state["supervision_interval"],
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
        patient_reply = call_patient(state["case_id"], therapist_text, state["dialog_history"])
    except Exception as e:
        return jsonify({"error": f"Fehler beim Aufruf der Patient:in: {str(e)}"}), 500

    patient_label = get_patient_label(state["case_id"]).upper()
    state["last_patient_reply"] = patient_reply
    state["dialog_history"].append(f"{patient_label}: {patient_reply}")

    supervision_feedback = None
    evaluation_text = None

    supervision_interval = int(state.get("supervision_interval", DEFAULT_SUPERVISION_INTERVAL))

    if state["therapist_turn_count"] % supervision_interval == 0:
        try:
            last_n = min(supervision_interval, len(state["therapist_turns"]))
            supervision_feedback = call_supervisor(
                state["case_id"],
                state["therapist_turns"][-last_n:],
                state["last_patient_reply"],
            )
            state["latest_supervision"] = supervision_feedback
            state["supervision_history"].append({
                "number": len(state["supervision_history"]) + 1,
                "text": supervision_feedback
            })
        except Exception as e:
            supervision_feedback = f"Fehler beim Supervisor-Aufruf: {str(e)}"
            state["latest_supervision"] = supervision_feedback
            state["supervision_history"].append({
                "number": len(state["supervision_history"]) + 1,
                "text": supervision_feedback
            })

    if state["therapist_turn_count"] == EVAL_AFTER:
        try:
            evaluation_text = call_rater(
                state["case_id"],
                state["therapist_turns"],
                state["dialog_history"]
            )
            state["latest_evaluation"] = evaluation_text
        except Exception as e:
            evaluation_text = f"Fehler beim Evaluator-Aufruf: {str(e)}"
            state["latest_evaluation"] = evaluation_text

    save_state(state)

    return jsonify(
        {
            "patient_reply": patient_reply,
            "patient_label": patient_label,
            "supervision_feedback": supervision_feedback,
            "evaluation": evaluation_text,
            "therapist_turn_count": state["therapist_turn_count"],
            "latest_supervision": state.get("latest_supervision"),
            "latest_evaluation": state.get("latest_evaluation"),
            "supervision_history": state.get("supervision_history", []),
            "supervision_interval": supervision_interval,
            "case_id": state["case_id"],
        }
    )


@app.route("/api/evaluation", methods=["POST"])
def api_evaluation():
    if not is_logged_in():
        return jsonify({"error": "Nicht autorisiert"}), 401

    state = load_state()

    try:
        evaluation_text = call_rater(
            state["case_id"],
            state["therapist_turns"],
            state["dialog_history"]
        )
        state["latest_evaluation"] = evaluation_text
        save_state(state)
    except Exception as e:
        return jsonify({"error": f"Fehler beim Evaluator-Aufruf: {str(e)}"}), 500

    return jsonify({"evaluation_text": evaluation_text})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)

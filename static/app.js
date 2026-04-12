const chat = document.getElementById("chat");
const statusEl = document.getElementById("status");
const sendBtn = document.getElementById("sendBtn");
const evalBtn = document.getElementById("evalBtn");
const resetBtn = document.getElementById("resetBtn");
const therapistText = document.getElementById("therapistText");

const supervisionBox = document.getElementById("supervisionBox");
const evaluationBox = document.getElementById("evaluationBox");
const supervisionIntervalInput = document.getElementById("supervisionInterval");
const saveSettingsBtn = document.getElementById("saveSettingsBtn");

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text || "";
  return div.innerHTML;
}

function renderMarkdown(text) {
  if (!text) return "";
  if (typeof marked === "undefined") {
    return escapeHtml(text);
  }
  return marked.parse(text);
}

function appendMessage(kind, text) {
  const div = document.createElement("div");
  div.className = `msg ${kind}`;
  div.innerHTML = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function renderHistory(lines) {
  chat.innerHTML = "";

  for (const line of lines) {
    if (typeof line !== "string") continue;

    if (line.startsWith("THERAPEUT: ")) {
      appendMessage(
        "therapist",
        `<strong>Therapeut</strong><br>${escapeHtml(line.replace("THERAPEUT: ", ""))}`
      );
    } else if (line.startsWith("PATIENTIN: ")) {
      appendMessage(
        "patient",
        `<strong>Patientin</strong><br>${escapeHtml(line.replace("PATIENTIN: ", ""))}`
      );
    } else {
      continue;
    }
  }
}

function setSupervision(text) {
  supervisionBox.classList.remove("supervision-active");

  if (text && text.trim()) {
    supervisionBox.classList.remove("muted");
    supervisionBox.classList.add("supervision-active");
    supervisionBox.innerHTML = renderMarkdown(text);
  } else {
    supervisionBox.classList.add("muted");
    supervisionBox.innerHTML = "Noch keine Supervision vorhanden.";
  }
}

function setEvaluation(text) {
  evaluationBox.classList.remove("evaluation-active");

  if (text && text.trim()) {
    evaluationBox.classList.remove("muted");
    evaluationBox.classList.add("evaluation-active");
    evaluationBox.innerHTML = renderMarkdown(text);
  } else {
    evaluationBox.classList.add("muted");
    evaluationBox.innerHTML = "Noch keine Evaluation vorhanden.";
  }
}

async function loadState() {
  try {
    const res = await fetch("/api/state");
    const data = await res.json();

    if (!res.ok) {
      statusEl.textContent = data.error || "Fehler beim Laden des Zustands.";
      return;
    }

    if (Array.isArray(data.dialog_history)) {
      renderHistory(data.dialog_history);
    } else {
      chat.innerHTML = "";
    }

    if (typeof data.supervision_interval !== "undefined" && supervisionIntervalInput) {
      supervisionIntervalInput.value = data.supervision_interval;
    }

    setSupervision(data.latest_supervision || "");
    setEvaluation(data.latest_evaluation || "");
  } catch (err) {
    statusEl.textContent = "Netzwerk- oder Serverfehler beim Laden.";
  }
}

async function saveSettings() {
  const interval = supervisionIntervalInput.value.trim();

  saveSettingsBtn.disabled = true;
  statusEl.textContent = "Einstellungen werden gespeichert ...";

  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        supervision_interval: interval,
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      statusEl.textContent = data.error || "Fehler beim Speichern.";
      return;
    }

    if (typeof data.supervision_interval !== "undefined") {
      supervisionIntervalInput.value = data.supervision_interval;
    }

    statusEl.textContent = data.message || "Gespeichert.";
  } catch (err) {
    statusEl.textContent = "Netzwerk- oder Serverfehler.";
  } finally {
    saveSettingsBtn.disabled = false;
  }
}

async function sendTurn() {
  const text = therapistText.value.trim();
  if (!text) return;

  sendBtn.disabled = true;
  statusEl.textContent = "Antwort wird erzeugt ...";

  appendMessage(
    "therapist",
    `<strong>Therapeut</strong><br>${escapeHtml(text)}`
  );
  therapistText.value = "";

  try {
    const res = await fetch("/api/turn", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ text }),
    });

    const data = await res.json();

    if (!res.ok) {
      statusEl.textContent = data.error || "Fehler";
      return;
    }

    appendMessage(
      "patient",
      `<strong>Patientin</strong><br>${escapeHtml(data.patient_reply || "")}`
    );

    setSupervision(data.latest_supervision || "");
    setEvaluation(data.latest_evaluation || "");

    statusEl.textContent = `Turn ${data.therapist_turn_count} gespeichert.`;
  } catch (err) {
    statusEl.textContent = "Netzwerk- oder Serverfehler.";
  } finally {
    sendBtn.disabled = false;
  }
}

async function runEvaluation() {
  evalBtn.disabled = true;
  statusEl.textContent = "Evaluation läuft ...";

  try {
    const res = await fetch("/api/evaluation", {
      method: "POST",
    });

    const data = await res.json();

    if (!res.ok) {
      statusEl.textContent = data.error || "Fehler";
      return;
    }

    setEvaluation(data.evaluation_text || "");
    statusEl.textContent = "Evaluation abgeschlossen.";
  } catch (err) {
    statusEl.textContent = "Netzwerk- oder Serverfehler.";
  } finally {
    evalBtn.disabled = false;
  }
}

async function resetSession() {
  resetBtn.disabled = true;
  statusEl.textContent = "Sitzung wird zurückgesetzt ...";

  try {
    const res = await fetch("/api/reset", {
      method: "POST",
    });

    const data = await res.json();

    if (!res.ok) {
      statusEl.textContent = data.error || "Fehler";
      return;
    }

    chat.innerHTML = "";
    setSupervision("");
    setEvaluation("");

    if (typeof data.supervision_interval !== "undefined" && supervisionIntervalInput) {
      supervisionIntervalInput.value = data.supervision_interval;
    }

    statusEl.textContent = data.message || "Zurückgesetzt.";
  } catch (err) {
    statusEl.textContent = "Netzwerk- oder Serverfehler.";
  } finally {
    resetBtn.disabled = false;
  }
}

if (sendBtn) {
  sendBtn.addEventListener("click", sendTurn);
}

if (evalBtn) {
  evalBtn.addEventListener("click", runEvaluation);
}

if (resetBtn) {
  resetBtn.addEventListener("click", resetSession);
}

if (saveSettingsBtn) {
  saveSettingsBtn.addEventListener("click", saveSettings);
}

if (therapistText) {
  therapistText.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      sendTurn();
    }
  });
}

loadState();

const modeSelect = document.getElementById("modeSelect");
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
const caseSelect = document.getElementById("caseSelect");

const scenarioTitle = document.getElementById("scenarioTitle");
const scenarioDescription = document.getElementById("scenarioDescription");
const scenarioGoals = document.getElementById("scenarioGoals");

const supervisionLabel = document.getElementById("supervisionLabel");
const supervisionHistoryList = document.getElementById("supervisionHistoryList");
const supervisionHistoryDetails = document.getElementById("supervisionHistoryDetails");

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text || "";
  return div.innerHTML;
}

function renderMarkdownBlock(text) {
  if (!text) return "";
  if (typeof marked === "undefined") {
    return escapeHtml(text);
  }
  return marked.parse(text);
}

function renderChatMarkdown(text) {
  if (!text) return "";

  if (typeof marked === "undefined") {
    return escapeHtml(text).replace(/\n/g, "<br>");
  }

  let html = marked.parse(text);

  html = html
    .replace(/^<p>/, "")
    .replace(/<\/p>\s*$/, "")
    .replace(/<\/p>\s*<p>/g, "<br><br>");

  return html;
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
    } else if (line.startsWith("PATIENT")) {
      const splitIndex = line.indexOf(":");
      if (splitIndex === -1) continue;

      const label = line.substring(0, splitIndex).trim();
      const content = line.substring(splitIndex + 1).trim();

      appendMessage(
        "patient",
        `<strong>${escapeHtml(label)}</strong><br>${renderChatMarkdown(content)}`
      );
    }
  }
}

function buildSupervisionAccordion(markdownText) {
  const rawHtml = renderMarkdownBlock(markdownText || "");
  if (!rawHtml.trim()) {
    return "Noch keine Supervision vorhanden.";
  }

  const wrapper = document.createElement("div");
  wrapper.innerHTML = rawHtml;

  const nodes = Array.from(wrapper.childNodes);
  const sections = [];
  let currentSection = null;

  for (const node of nodes) {
    if (
      node.nodeType === Node.ELEMENT_NODE &&
      /^H[1-6]$/.test(node.tagName)
    ) {
      currentSection = {
        heading: node.textContent.trim(),
        headingTag: node.tagName.toLowerCase(),
        content: [],
      };
      sections.push(currentSection);
    } else {
      if (!currentSection) {
        currentSection = {
          heading: "",
          headingTag: "h3",
          content: [],
        };
        sections.push(currentSection);
      }
      currentSection.content.push(node.cloneNode(true));
    }
  }

  if (sections.length === 0) {
    return rawHtml;
  }

  const out = document.createElement("div");

  sections.forEach((section, index) => {
    const hasHeading = section.heading && section.heading.length > 0;

    if (index === 0) {
      const openBlock = document.createElement("div");
      openBlock.className = "supervision-section-open";

      if (hasHeading) {
        const h = document.createElement(section.headingTag || "h3");
        h.textContent = section.heading;
        openBlock.appendChild(h);
      }

      section.content.forEach((child) => openBlock.appendChild(child));
      out.appendChild(openBlock);
      return;
    }

    const accWrap = document.createElement("div");
    accWrap.className = "supervision-accordion";

    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = hasHeading ? section.heading : `Abschnitt ${index + 1}`;

    const body = document.createElement("div");
    body.className = "accordion-body";
    section.content.forEach((child) => body.appendChild(child));

    details.appendChild(summary);
    details.appendChild(body);
    accWrap.appendChild(details);
    out.appendChild(accWrap);
  });

  return out.innerHTML;
}

function setSupervision(text, number = null) {
  supervisionBox.classList.remove("supervision-active");

  if (text && text.trim()) {
    supervisionBox.classList.remove("muted");
    supervisionBox.classList.add("supervision-active");
    supervisionBox.innerHTML = buildSupervisionAccordion(text);
    supervisionLabel.textContent = number ? `Supervision ${number}` : "Aktuelle Supervision";
  } else {
    supervisionBox.classList.add("muted");
    supervisionBox.innerHTML = "Noch keine Supervision vorhanden.";
    supervisionLabel.textContent = "Noch keine Supervision";
  }
}

function setEvaluation(text) {
  evaluationBox.classList.remove("evaluation-active");

  if (text && text.trim()) {
    evaluationBox.classList.remove("muted");
    evaluationBox.classList.add("evaluation-active");
    evaluationBox.innerHTML = renderMarkdownBlock(text);
  } else {
    evaluationBox.classList.add("muted");
    evaluationBox.innerHTML = "Noch keine Evaluation vorhanden.";
  }
}

function renderScenario(scenario) {
  if (!scenario) return;

  scenarioTitle.textContent = scenario.title || "Training";
  scenarioDescription.textContent = scenario.description || "";

  scenarioGoals.innerHTML = "";
  const goals = Array.isArray(scenario.learning_goals) ? scenario.learning_goals : [];
  for (const goal of goals) {
    const li = document.createElement("li");
    li.textContent = goal;
    scenarioGoals.appendChild(li);
  }
}

function renderSupervisionHistory(history) {
  supervisionHistoryList.innerHTML = "";

  if (!Array.isArray(history) || history.length <= 1) {
    supervisionHistoryDetails.open = false;
    return;
  }

  const previousItems = history.slice(0, -1);

  for (const item of previousItems) {
    const wrapper = document.createElement("div");
    wrapper.className = "supervision-history-item";

    const label = document.createElement("div");
    label.className = "history-label";
    label.textContent = `Supervision ${item.number}`;

    const box = document.createElement("div");
    box.className = "meta-box";
    box.innerHTML = renderMarkdownBlock(item.text || "");

    wrapper.appendChild(label);
    wrapper.appendChild(box);
    supervisionHistoryList.appendChild(wrapper);
  }
}

function updateSupervisionUI(history) {
  if (!Array.isArray(history) || history.length === 0) {
    setSupervision("", null);
    renderSupervisionHistory([]);
    return;
  }

  const latest = history[history.length - 1];
  setSupervision(latest.text || "", latest.number || history.length);
  renderSupervisionHistory(history);
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

    if (typeof data.case_id !== "undefined" && caseSelect) {
      caseSelect.value = data.case_id;
    }

    renderScenario(data.scenario);
    updateSupervisionUI(data.supervision_history || []);
    setEvaluation(data.latest_evaluation || "");
  } catch (err) {
    statusEl.textContent = "Netzwerk- oder Serverfehler beim Laden.";
  }
}

async function saveSettings() {
  const interval = supervisionIntervalInput.value.trim();
  const caseId = caseSelect.value;

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
        case_id: caseId,
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

    if (typeof data.case_id !== "undefined") {
      caseSelect.value = data.case_id;
    }

    renderScenario(data.scenario);

    if (data.case_changed) {
      chat.innerHTML = "";
      updateSupervisionUI([]);
      setEvaluation("");
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
      `<strong>${escapeHtml(data.patient_label || "PATIENTIN")}</strong><br>${renderChatMarkdown(data.patient_reply || "")}`
    );

    updateSupervisionUI(data.supervision_history || []);
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
    updateSupervisionUI([]);
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

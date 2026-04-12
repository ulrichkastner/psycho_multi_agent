<h1>Psycho Multi Agent</h1>

<p>
  Ein webbasiertes Trainingssystem für psychotherapeutische Erstgespräche,
  Supervision und Evaluation mit mehreren simulierten Patient:innenfällen.
</p>

<h2>Über das Projekt</h2>

<p>
  <strong>Psycho Multi Agent</strong> ist eine Flask-basierte Anwendung für die
  psychotherapeutische Weiterbildung. Nutzer:innen können mit simulierten
  Patient:innen chatbasiert Gespräche führen, in festgelegten Intervallen
  supervisorisches Feedback erhalten und eine strukturierte Evaluation der
  Interventionen abrufen.
</p>

<p>
  Die Anwendung ist aktuell als Beta-System aufgebaut und wird über
  <strong>Render</strong> bereitgestellt. Die Falllogik ist modular organisiert:
  Neue Fälle können über zusätzliche <code>case_XXX.yaml</code>-Dateien ergänzt werden.
</p>

<h2>Funktionen</h2>

<ul>
  <li>Mehrere psychotherapeutische Trainingsfälle</li>
  <li>Fallauswahl über das Frontend</li>
  <li>Simulierte Patient:innenantworten mit verbalem und nonverbalem Feedback</li>
  <li>Automatische Supervision nach konfigurierbarem Intervall</li>
  <li>Supervisionshistorie mit nummerierten Rückmeldungen</li>
  <li>Manuelle und automatische Evaluation</li>
  <li>Markdown-basierte Darstellung von Supervision und Evaluation</li>
  <li>Passwortgeschützter Beta-Zugang</li>
  <li>Session-basierte Gesprächsverwaltung</li>
</ul>

<h2>Projektstruktur</h2>

<pre><code>psycho_multi_agent/
├── app.py
├── wsgi.py
├── requirements.txt
├── render.yaml
├── .gitignore
├── config/
│   ├── base.yaml
│   └── cases/
│       ├── case_001.yaml
│       ├── case_002.yaml
│       ├── case_003.yaml
        ├── case_004.yaml
│       └── case_XXX.yaml
├── templates/
│   ├── login.html
│   └── index.html
├── static/
│   └── app.js
└── instance/
    └── sessions/</code></pre>

<h2>Technischer Aufbau</h2>

<ul>
  <li><strong>Backend:</strong> Flask</li>
  <li><strong>LLM-Anbindung:</strong> OpenAI API</li>
  <li><strong>Frontend:</strong> HTML, CSS, JavaScript</li>
  <li><strong>Deployment:</strong> Render</li>
  <li><strong>Konfiguration:</strong> YAML-basierte Fall- und Agentensteuerung</li>
</ul>

<h2>Konzept</h2>

<p>
  Die Anwendung trennt drei Ebenen:
</p>

<ul>
  <li><strong>Patient:innenebene:</strong> simulierte Fallrolle mit eigener Dynamik</li>
  <li><strong>Supervisionsebene:</strong> strukturierte Rückmeldung zu therapeutischen Interventionen</li>
  <li><strong>Evaluationsebene:</strong> zusammenfassende Bewertung sprachlicher und inhaltlicher Aspekte</li>
</ul>

<p>
  Supervisor und Evaluator werden global definiert, während die Patient:innenrolle
  und das Szenario fallbezogen geladen werden.
</p>

<h2>Fallbibliothek</h2>

<p>Aktuell umfasst das Projekt mehrere Beispielkonfigurationen:</p>

<ul>
  <li><strong>case_001</strong> – Panikpatientin nach Kollaps im Job</li>
  <li><strong>case_002</strong> – Erschöpfte Patientin mit Hoffnungslosigkeit</li>
  <li><strong>case_003</strong> – Krisenpatientin nach Beziehungskonflikt</li>
  <li><strong>case_004</strong> – Patientin mit Herzangst und wiederholten Notfallbesuchen</li>
</ul>

<p>
  Weitere Fälle können durch zusätzliche Dateien im Verzeichnis
  <code>config/cases/</code> ergänzt werden.
</p>

<h2>Neuen Fall hinzufügen</h2>

<p>
  Neue Fälle werden über Dateien im Format <code>case_XXX.yaml</code> eingebunden.
</p>

<pre><code>config/cases/case_005.yaml</code></pre>

<p>Wichtige Voraussetzungen:</p>

<ul>
  <li>Dateiname beginnt mit <code>case_</code></li>
  <li>Die Datei liegt in <code>config/cases/</code></li>
  <li>Die YAML-Struktur ist gültig</li>
  <li>Nach dem Hinzufügen ist ein Redeploy der App erforderlich</li>
</ul>

<h2>Beispielstruktur eines Falls</h2>

<pre><code>scenario:
  id: "case_005"
  title: "Beispieltitel"
  description: >
    Kurze Beschreibung des Falls.
  learning_goals:
    - "Lernziel 1"
    - "Lernziel 2"

patient:
  role: "Simulierte Patientin"
  model: "gpt-4.1-mini"
  instructions: |
    Fallbezogene Instruktionen für die Patient:innenrolle.</code></pre>

<h2>Lokale Entwicklung</h2>

<pre><code>python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py</code></pre>

<p>
  Für produktionsnahe Ausführung wird Gunicorn über <code>wsgi.py</code> verwendet.
</p>

<h2>Deployment auf Render</h2>

<p>
  Das Projekt ist für Render vorbereitet. Die Konfiguration erfolgt über
  <code>render.yaml</code>.
</p>

<p>Wichtige Environment Variables:</p>

<ul>
  <li><code>OPENAI_API_KEY</code></li>
  <li><code>FLASK_SECRET_KEY</code></li>
  <li><code>BETA_PASSWORD</code></li>
  <li><code>OPENAI_MODEL</code></li>
  <li><code>MAX_TURNS</code></li>
  <li><code>MAX_INPUT_LENGTH</code></li>
  <li><code>DEFAULT_SUPERVISION_INTERVAL</code></li>
</ul>

<h2>Formatierung der Patient:innenantworten</h2>

<p>
  Nonverbale Rückmeldungen der simulierten Patient:innen werden in neutraler,
  markup-basierter Form dargestellt, zum Beispiel:
</p>

<pre><code>[*Patientin seufzt und schaut weg.*]

Ich weiß gerade nicht, was ich dazu sagen soll.</code></pre>

<p>
  Dadurch werden nonverbale Signale klar von der verbalen Antwort getrennt.
</p>

<h2>Bekannte Einschränkungen</h2>

<ul>
  <li>Aktuell Beta-Status</li>
  <li>Session-Speicherung erfolgt dateibasiert</li>
  <li>Keine persistente Nutzerverwaltung</li>
  <li>Keine Datenbankanbindung</li>
  <li>Falländerungen werden erst nach Redeploy sicher sichtbar</li>
</ul>

<h2>Sicherheit und Nutzungshinweis</h2>

<p>
  Dieses Projekt ist ein Trainings- und Demonstrationssystem. Es ist
  <strong>nicht</strong> für die Versorgung akuter Krisen gedacht und ersetzt
  keine klinische Einschätzung, Notfallhilfe oder Behandlung.
</p>

<p>
  Bitte keine echten Patient:innendaten eingeben.
</p>

<h2>Roadmap</h2>

<ul>
  <li>Weitere Fälle ergänzen</li>
  <li>Trainingsmodus und Prüfmodus unterscheiden</li>
  <li>Direkte Supervisor-Anfrage als eigene Funktion</li>
  <li>Validierung von Fallkonfigurationen beim Laden</li>
  <li>Verbesserte Sitzungs- und Nutzerverwaltung</li>
</ul>

<h2>Autor / Kontext</h2>

<p>
  Das Projekt wurde als psychotherapeutisches Trainingssystem für einen
  passwortgeschützten Beta-Bereich entwickelt und fortlaufend iterativ erweitert.
</p>

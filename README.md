# ORBIT — Operational Response, Briefing & Incident Triage

> Built for the **Kaggle × Google "5-Day AI Agents Intensive" capstone** (Day 5).

An agentic, **real-time disaster-coordination platform** modelled on the UN's
**UNDAC** (United Nations Disaster Assessment and Coordination) operating model
and the **OSOCC** (On-Site Operations Coordination Centre) concept from the
*UNDAC Handbook, 8th Edition (2024)*.

It turns a raw distress report into a full operational picture — assessed,
coordinated, resourced, reported and broadcast — through a team of cooperating
agents, and plots the live global disaster picture on an **interactive 3D
globe** in an EarthExplorer-style mission console.

> Runs **out of the box with no API keys** on free, public, live data
> (USGS, GDACS). Optionally upgrades to **Claude-powered** reasoning when an
> `ANTHROPIC_API_KEY` is present.

---

## What it does

### The agent team (OSOCC cells)
A report flows through six cooperating agents, streamed live to the UI:

| Agent | UNDAC mapping | Output |
|-------|---------------|--------|
| **Ingestion** | F.1 Information Management | Structured incident (type, location, geocoded coords, needs, casualties) |
| **Assessment (MIRA)** | F.2 Assessment & Analysis; Section K | Severity index (0–100), affected/displaced estimates, per-sector needs, priority actions, hazard-specific secondary hazards |
| **Coordination (OSOCC)** | D. OSOCC Concept; G.6 ICC | Lead clusters, **3W matrix** (Who does What Where), coordination gaps, OSOCC tasking |
| **Logistics** | G.11 Disaster logistics | Quantified resource request vs. live inventory, gap analysis, procurement recommendations |
| **Information Management** | F.3 Reporting / IM products | A full **Situation Report (SitRep)** in OCHA format |
| **Alerts & Notification** | A.2 / E.2 / F.4 | **Everbridge-style** severity-driven mass notifications with audience routing, channels and acknowledgement rules |

A **Human-In-The-Loop (HITL)** gate can pause the pipeline before committing
resources (toggle in the UI; `POST /api/incidents/{id}/approve` to release).

### The killer workflow: first report → shareable OSOCC briefing
Every incident is structured so an operator answers three questions in seconds —
**what happened, who owns what next, what is still uncertain** — and can export a
self-contained briefing package (`GET /api/incidents/{id}/briefing`, printable to PDF).

- **Confidence is separate from severity** ([backend/analysis.py](backend/analysis.py)):
  a loud single report is *Unverified*; a multi-source-confirmed event is *Confirmed*.
  Confidence is computed from cross-feed corroboration + news + social + reported impacts.
- **Evidence-first explainability**: an evidence ledger backs the picture, and every
  cluster recommendation carries a "because…" rationale.
- **Human acknowledgement loops**: 3W cluster taskings and alerts are machine
  *proposals* a human can **Accept / Reject / Amend**; open questions can be answered.
  The briefing package reflects those human decisions.
- **MIRA unanswered-questions**: the gaps that still need resolving, by category.
- **On-the-ground context** ([backend/data/context.py](backend/data/context.py)),
  fused per incident and shown in the brief + briefing:
  - **NASA GIBS/VIIRS satellite imagery** of the site *(keyless)*
  - **USGS ShakeMap** ground-shaking image for earthquakes *(keyless)*
  - **RainViewer** live precipitation-radar tile *(keyless)*
  - **OpenSky** live aircraft → airspace / airport-operability signal *(keyless)*
  - **Open-Meteo** operating conditions; **OSM/Overpass** hospitals + aerodromes *(keyless)*
  - **NASA FIRMS** active-fire detections *(free key)* — also corroborates wildfires
  - **OpenAQ v3** ground air quality (PM2.5) *(free key)*
  - **VesselAPI** live AIS vessels (maritime SAR assets) + nearest seaports (sea
    relief access) *(key)*
  - **ACLED** conflict/unrest events *(account + API access activation required)*

  Keys live in a gitignored `.env` (loaded at startup): `FIRMS_MAP_KEY`,
  `OPENAQ_API_KEY`, `VESSEL_API_KEY`, `ACLED_EMAIL`/`ACLED_PASSWORD`. Every source
  degrades gracefully if its key is absent.
- **Collaboration**: decision log, notes, agent timeline per incident.
- **Value metrics**: time-to-briefing, confidence score, open-questions count.

### Situational awareness & alerting
- **Live feeds** ([backend/data/live_feeds.py](backend/data/live_feeds.py)):
  USGS earthquakes, GDACS alerts, NASA EONET (wildfires/storms/volcanoes) and
  ReliefWeb — all keyless, normalised for the globe (~130+ live events).
- **Live news & social** ([backend/news.py](backend/news.py)): per-incident real
  news (Google News RSS, GDELT fallback) and social posts (Mastodon public
  timelines) shown in the brief's **News** tab. Keyless, source-attributed.
- **Monitoring engine** ([backend/monitor.py](backend/monitor.py)): a background
  poller detects *genuinely new* events (deduplicated against the backlog),
  matches them against user **watch rules** (min severity · hazard types ·
  region), and **dispatches real notifications**:
  - **Webhook** (keyless) — Slack / Discord / Teams / any incoming webhook.
  - **Email** (optional) — SMTP, enabled via `SMTP_*` env vars.
  Manage it all in the **Monitoring** view: set a channel, add rules, send a
  test alert, and watch the triggered-alert log.

### Grounding — nothing is fabricated
- **Real exposure** ([backend/data/exposure.py](backend/data/exposure.py)): when
  the pipeline runs on a live event, the assessment is grounded in **USGS PAGER**
  (population exposed to damaging shaking + official fatality alert bands) and
  **GDACS** (alert level, severity text, and `sendai` authority-reported
  dead/displaced/affected). Every figure carries a **source link**.
- **No invention**: if a figure isn't in a real source or stated in the report,
  it is shown as **"not estimated"** (never guessed). Severity is anchored to the
  real GDACS/PAGER alert level; with no data it is flagged *preliminary*.
- **Resource registry** ([backend/resources.py](backend/resources.py)): the
  inventory is a registry of **real, located, fully editable** records (location,
  owner, provenance) — add / edit / delete in the **Resources** view. The
  Logistics agent allocates from it and deducts on dispatch approval; it only
  quantifies demand when a real population figure exists.
- **Hazard Impact Knowledge Base** ([backend/data/hazard_kb.py](backend/data/hazard_kb.py))
  encodes the handbook's Section K summaries (K.1 Earthquakes → K.7 Droughts):
  secondary hazards, priority sectors, early actions and the "golden hours" window.

### The interface (EarthExplorer-style, 3D)
- Interactive **3D world** (globe.gl / three.js) with live disaster markers,
  sized by magnitude and coloured by severity, pulsing rings on critical events.
- Click any live event → it pre-fills the intake and you can **run the agent
  team on a real, live event** in one click.
- Left rail: incident intake, live-data-layer toggles, and a streaming
  **Agent Console**. Right rail: an **operational brief** (Overview · SitRep ·
  3W/Coordination · Logistics · Alerts).
- Views: Global Picture · Incidents · Resources (live inventory) · Hazard KB.

---

## Run it

```bash
python -m pip install -r requirements.txt
python run.py                       # → http://127.0.0.1:8000
```

## Deploy a live demo

ORBIT is a Python (FastAPI) app, so it needs a host that runs Python —
**GitHub Pages cannot run it** (static only). Use any Docker host:

```bash
# Google Cloud Run (on-brand for the course)
gcloud run deploy orbit --source . --allow-unauthenticated --region europe-west1

# or Render / Fly.io / Railway — point them at the included Dockerfile
# or Hugging Face Spaces — create a Docker Space, push this repo, set app_port: 8000
```

It boots with **zero secrets** (free keyless feeds). Add keys from `.env.example`
in the host's environment settings to unlock Claude reasoning + extra data sources.

Optional — enable Claude reasoning:

```bash
setx ANTHROPIC_API_KEY "sk-ant-..."   # Windows
export ANTHROPIC_API_KEY="sk-ant-..." # macOS/Linux
```

Optional — enable real alert delivery & feeds:

```bash
export ALERT_WEBHOOK_URL="https://hooks.slack.com/services/…"  # Slack/Discord/Teams/generic
export ALERT_EMAIL_TO="ops@example.org"                         # needs SMTP_* below
export SMTP_HOST="smtp.example.org"   # + SMTP_PORT SMTP_USER SMTP_PASS SMTP_FROM
export MONITOR_INTERVAL="120"          # feed poll interval, seconds
export RELIEFWEB_APPNAME="your-registered-appname"  # enables the ReliefWeb feed
```

(The webhook URL can also just be pasted into the **Monitoring** view at runtime.)

---

## API

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET`  | `/api/health` | status + which reasoning engine is active |
| `GET`  | `/api/events?min_magnitude=4.5` | aggregated live events for the globe |
| `GET`  | `/api/events/{earthquakes,gdacs,eonet,reliefweb}` | individual feeds |
| `GET/POST/DELETE` | `/api/monitor/rules` | manage watch rules |
| `GET/POST` | `/api/monitor/channels` | get/set webhook + email |
| `GET`  | `/api/monitor/alerts` · `/api/monitor/status` | triggered alerts & engine status |
| `POST` | `/api/monitor/test` · `/api/monitor/poll` | send a test alert · poll feeds now |
| `GET/POST/PUT/DELETE` | `/api/resources` · `/api/resources/{id}` | editable located resource registry |
| `POST` | `/api/run` | run the full pipeline (synchronous) |
| `WS`   | `/ws/run` | run the pipeline with **live streamed agent reasoning** |
| `GET`  | `/api/incidents` · `/api/incidents/{id}` | stored incidents |
| `POST` | `/api/incidents/{id}/approve` | HITL: approve dispatch & commit inventory |
| `GET`  | `/api/inventory` | live operational stock |
| `GET`  | `/api/hazards` | the hazard impact knowledge base |

---

## Architecture

```
crisis_coordinator/
├─ run.py                       # launcher (uvicorn)
├─ inventory.json               # live operational stock (mutated on dispatch)
├─ backend/
│  ├─ app.py                    # FastAPI: REST + WebSocket + static frontend
│  ├─ orchestrator.py           # OSOCC pipeline (chains the agents, HITL gate)
│  ├─ models.py                 # Pydantic domain models
│  ├─ llm.py                    # optional Claude layer (graceful heuristic fallback)
│  ├─ store.py                  # in-memory incident store
│  ├─ skills_geo.py             # geocoding (Nominatim + offline gazetteer)
│  ├─ agents/                   # ingestion, assessment, coordination,
│  │                            #   logistics, infomanagement, alerts
│  └─ data/
│     ├─ hazard_kb.py           # UNDAC Handbook Section K knowledge base
│     └─ live_feeds.py          # USGS / GDACS / ReliefWeb
└─ frontend/
   ├─ index.html · css/styles.css · js/{globe.js, app.js}
```

### Design choices (Everbridge / NVIDIA GTC influences)
- **Critical Event Management loop** (Everbridge): detect → assess → notify the
  right audiences over the right channels → require acknowledgement → escalate.
  Implemented in the Alerts agent with severity-based routing and a public
  cell-broadcast advisory for critical events.
- **Agentic, streaming pipeline** (per NVIDIA's agentic-AI direction): the
  orchestrator runs autonomous cells that hand structured state to one another
  and stream their reasoning live, with a human approval gate for consequential
  actions.

> ℹ️ This is a decision-support prototype. Outputs are estimates for coordination
> purposes and must be verified against ground truth before operational use.

### Legacy CLI
The original stdio-MCP CLI pipeline ([main.py](main.py), `agents/`, `skills/`,
`mcp_server/`) is preserved for reference and still runs via `python main.py`.
The platform above supersedes it.

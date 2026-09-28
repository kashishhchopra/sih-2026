# 🛡️ Smart Tourist Safety Monitoring & Incident Response System

A full-stack AI/ML system that issues **tamper-proof digital tourist IDs**, monitors
tourist movement in real time, detects anomalies with machine learning, computes a
dynamic **safety score**, enforces **geo-fences**, handles **SOS/panic** events, and
drives a complete **incident-response workflow** — with a live police/admin dashboard
and a responsive tourist mobile view.

> B.Tech AI/ML major project. Backend: **FastAPI + SQLAlchemy + scikit-learn**.
> Frontend: **React (Vite) + Tailwind + Leaflet + Recharts**. Real-time via **WebSockets**.

---

## Table of Contents
1. [Feature Overview](#feature-overview)
2. [Architecture](#architecture)
3. [Tech Stack](#tech-stack)
4. [Security](#security)
5. [Deployment (Docker, one command)](#deployment)
6. [Project Structure](#project-structure)
7. [Local Setup & Run](#setup--run)
8. [Live Demo Mode](#live-demo-mode)
9. [The ML Models (features, training, evaluation)](#the-ml-models)
10. [Digital ID Hash-Chain](#digital-id-hash-chain)
11. [API Reference](#api-reference)
12. [Demo Accounts](#demo-accounts)

---

## Feature Overview

| # | Feature | How it works |
|---|---------|--------------|
| 1 | **Digital Tourist ID** | KYC registration → unique `STS-XXXX` ID + QR code. Records stored as a **SHA-256 linked hash chain** (blockchain-style, tamper-evident). ID validity tied to trip dates. |
| 2 | **AI Anomaly Detection** | **Isolation Forest** flags sudden location drop-off, prolonged inactivity, and abnormal speed (abduction pattern). **Route-deviation** via distance-to-itinerary. **DBSCAN** clusters historical incidents into auto high-risk zones. |
| 3 | **Safety Score (0–100)** | **Random Forest regressor** on zone risk, time-of-day, anomaly score, crime index, weather (mock). Live, color-coded. |
| 4 | **Geo-fencing & Alerts** | Polygon zones + **point-in-polygon** (Shapely). Entering a high-risk/restricted zone auto-alerts tourist + dashboard over **WebSocket**. |
| 5 | **Panic / SOS** | One-tap SOS → nearest available police unit auto-dispatched, emergency contacts notified, **critical incident** created. |
| 6 | **Police/Admin Dashboard** | Live Leaflet map of all tourists + risk heat circles, real-time alert feed, tourist search by digital ID, **auto E-FIR** draft for missing persons, analytics charts. |
| 7 | **Tourist Mobile View** | Responsive page: safety score gauge, zone status, itinerary tracker, SOS, nearby police, opt-in live-tracking toggle. |
| 8 | **Incident Workflow** | Lifecycle `detected → acknowledged → dispatched → resolved`, ML/rule severity classification, response-time tracking. |
| 9 | **Self-Registration** | Public KYC form issues a digital ID and (optionally) a login, then auto-signs the tourist in. |
| 10 | **Security Audit Log** | Admin page + API trailing logins (with IP), SOS, and missing-person actions for accountability. |
| 11 | **Smart Trip Planner** | Turns the tourist's confirmed itinerary into a day-by-day plan, live against weather (services/weather.py), festivals/public holidays (services/festival.py), and permit flags (services/permit.py) for each day — a bad-weather day gets a real nearby indoor alternative (live OpenStreetMap lookup), not just a warning. |
| 12 | **Crowd & Queue Forecast** | Per-zone crowd forecast combining live tourist density, peak/off-peak season, real public holidays (Calendarific API), nearby festivals, and weather — plus a per-POI queue-wait estimate. Every forecast carries its `reasons[]`, never a bare number. |
| 13 | **Discovery** | Hidden spots, regional food, and homestays near the tourist — live from the OpenStreetMap Overpass API, merged with the database, with the DB as an automatic fallback if the live lookup is slow/unavailable. |
| 14 | **Multilingual Guide** | An everyday phrasebook (greetings, directions, food, shopping) in the tourist's chosen language — tap to translate and hear it spoken. |
| 15 | **Permit & E-Pass Automation** | Pre-fills a permit/e-pass application (Inner Line Permit, Restricted/Protected Area Permit, forest/wildlife entry) from the tourist's own KYC + itinerary. Two-step and honest: a draft the tourist reviews/edits, then an explicit confirm that **never submits anything to a government system** — it hands back the real official portal (Nagaland ILP, e-FRRO, Assam Sewa Setu) for the tourist to finish there themselves. |
| 16 | **Two-Way Live Voice Translator** | A conversation-mode translator for a tourist and a foreign traveler talking face-to-face — each side speaks in their own language, the other hears it translated aloud. |
| 17 | **Festival & Local Event Intelligence** | A calendar of this app's curated local festivals plus real national public holidays (Calendarific API), connected into the Smart Trip Planner and the Crowd & Queue Forecast rather than living as an isolated page. |

All seven live in the tourist app's new **Explore** tab (🌍). None of them touch any existing feature's data or routes — they're additive, reusing the existing itinerary, zone, weather, translation, and POI infrastructure wherever possible. Two external, free-tier data sources back them: OpenStreetMap's **Overpass API** (Discovery + indoor alternatives — no key needed) and **Calendarific** (public holidays — free key needed, see `backend/.env.example` / `CALENDARIFIC_API_KEY`). With no Calendarific key, holiday-driven signals are simply absent, never fabricated.

---

## Architecture

```mermaid
flowchart TB
    subgraph Client["Frontend — React + Vite + Tailwind"]
        T["🧳 Tourist Mobile View<br/>score · SOS · geofence · itinerary"]
        A["🖥️ Police/Admin Dashboard<br/>map · alerts · analytics · E-FIR"]
    end

    subgraph API["Backend — FastAPI"]
        AUTH["JWT Auth<br/>(admin / tourist roles)"]
        REST["REST API<br/>tourists · zones · incidents · analytics"]
        WS["WebSocket /ws/alerts<br/>live broadcast"]
        PIPE["Monitoring Pipeline<br/>ping → anomaly → geofence → alert → incident"]
    end

    subgraph ML["ML Layer (scikit-learn, joblib)"]
        IF["Isolation Forest<br/>anomaly detection"]
        RF["Random Forest<br/>safety score"]
        DB_["DBSCAN<br/>hot-zone discovery"]
    end

    subgraph SVC["Domain Services"]
        HC["SHA-256 Hash Chain<br/>tamper-proof ID"]
        GEO["Geo utils<br/>haversine · point-in-polygon"]
        EFIR["E-FIR generator"]
    end

    DBS[("SQLite / PostgreSQL<br/>SQLAlchemy ORM")]

    T <-->|REST + WS| API
    A <-->|REST + WS| API
    REST --> PIPE
    PIPE --> IF & RF & DB_
    PIPE --> GEO
    PIPE --> WS
    REST --> HC & EFIR
    API --> DBS
    ML -. joblib artifacts .-> PIPE
```

### Monitoring pipeline (per GPS ping)

```mermaid
sequenceDiagram
    participant Tourist
    participant API as FastAPI
    participant ML as Isolation Forest
    participant Geo as Geo-fence
    participant WS as WebSocket
    participant Dash as Dashboard

    Tourist->>API: POST /tourists/{id}/location {lat,lng,speed}
    API->>ML: features [speed, Δdist, Δtime, dist_from_route]
    ML-->>API: {is_anomaly, score}
    API->>Geo: point-in-polygon(zones)
    Geo-->>API: zones containing point
    API->>API: create alerts + incidents, refresh safety score
    API->>WS: broadcast(alert / location / incident)
    WS-->>Dash: live update
    API-->>Tourist: {safety_score, band, alerts_raised}
```

---

## Tech Stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2, Pydantic v2, JWT (python-jose), bcrypt
- **ML:** scikit-learn (IsolationForest, DBSCAN, RandomForestRegressor), pandas, numpy, joblib
- **Geo:** Shapely (point-in-polygon), haversine
- **DB:** SQLite (dev) — swap `DATABASE_URL` for PostgreSQL
- **Frontend:** React 18, Vite, Tailwind CSS, React-Leaflet, Recharts, Axios
- **Real-time:** native WebSockets
- **Deploy:** Docker + docker-compose (PostgreSQL + backend + nginx-served SPA)

---

## Security

The system is built to be deployed safely — **nothing security-sensitive is
hardcoded** and common web-attack classes are addressed:

| Area | Protection |
|------|------------|
| **Secrets** | `SECRET_KEY` is env-only; the app **refuses to start in production** without a strong key. Dev auto-generates an ephemeral key. |
| **Authentication** | JWT (HS256) with `iat`/`nbf`/`exp`/`jti` claims and a token `type` guard; bcrypt (cost 12) password hashing. |
| **Authorization** | Role-based (`admin` / `tourist`). Tourists can only read/act on **their own** record (`require_self_or_admin`); admin-only routes for dashboards, incidents, audit, E-FIR. |
| **Brute-force** | Per-IP **rate limiting** — strict on `/auth/login` (429 after N attempts), coarse global limit on every API route. |
| **WebSocket** | The live feed carries tourist PII, so the socket **requires a valid admin token** (rejected otherwise). |
| **Input validation** | Pydantic bounds on every input: lat∈[-90,90], lng∈[-180,180], speed caps, string length limits, polygon vertex validation, enum-checked fields, trip-date sanity. |
| **Injection** | SQLAlchemy ORM (parameterised) throughout — no string-built SQL. |
| **Transport headers** | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`, a restrictive **CSP**, and **HSTS** in production. |
| **Host / CORS** | `TrustedHostMiddleware` (explicit `ALLOWED_HOSTS`) + locked-down CORS origins/methods/headers. |
| **DoS surface** | Request **body-size limit** (413 on oversized payloads). |
| **Auditability** | A **security audit log** records logins (success/failure + IP), SOS, and missing-person actions, viewable in the admin **Audit Log** page. |
| **Least privilege** | Backend Docker image runs as a **non-root** user; interactive API docs are disabled in production. |
| **Privacy** | Documents stored masked/mock; live location tracking is **opt-in** by the tourist. |

> Single-instance note: the rate limiter and WebSocket manager are in-process. For
> a horizontally-scaled deployment, back them with **Redis** (pub/sub + shared
> counters) and run multiple workers; the code is structured to swap these in.

---

## Deployment

**One command** brings up PostgreSQL, the API, and the nginx-served SPA:

```bash
cp .env.example .env
# generate and paste a strong key:
python -c "import secrets; print(secrets.token_urlsafe(48))"   # -> SECRET_KEY in .env
docker compose up --build
```

Then open **http://localhost:8080**. The backend trains its ML models at image
build time and (by default) seeds demo data on first boot (`SEED_ON_START=true`).

What compose runs:
- **db** — PostgreSQL 16 with a persistent volume + healthcheck
- **backend** — FastAPI (non-root, single worker) reading all config from env
- **frontend** — React build served by nginx, proxying `/api` and `/ws` to the backend

For a real deployment set `ENVIRONMENT=production`, an explicit `ALLOWED_HOSTS`,
your real `CORS_ORIGINS`, `SEED_ON_START=false`, and put a TLS-terminating reverse
proxy in front. Every tunable lives in `.env` / `backend/.env.example` — no code edits.

---

## Project Structure

```
major project/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + router wiring
│   │   ├── core/               # config, security (JWT, bcrypt)
│   │   ├── db/                 # SQLAlchemy engine/session
│   │   ├── models/            # ORM: tourist, zone, incident, alert, police, user
│   │   ├── schemas/           # Pydantic request/response models
│   │   ├── api/               # routers: auth, tourists, zones, incidents, analytics, ws
│   │   ├── services/          # hashchain, geo, ml_service, safety, monitoring, efir
│   │   ├── websocket/         # connection manager
│   │   ├── ml/                # ⭐ data generation + model training scripts
│   │   └── scripts/           # seed.py, simulate.py (live demo)
│   ├── ml_models/             # saved *.joblib + metrics.json + hotzones.json
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── pages/admin/       # Dashboard, TouristSearch, Incidents, Analytics
│       ├── pages/tourist/     # TouristApp (mobile view)
│       └── components/        # ui, mapIcons, geo
└── README.md
```

---

## Setup & Run

> Prerequisites: **Python 3.11** and **Node 18+**. (Python 3.11 is recommended — the
> ML wheels install cleanly there.)

### 1. Backend

```bash
cd backend
py -3.11 -m venv venv            # Windows;  python3.11 -m venv venv on macOS/Linux
venv\Scripts\activate            # source venv/bin/activate on macOS/Linux
pip install -r requirements.txt

# Train ML models (writes ml_models/*.joblib + metrics.json)
python -m app.ml.train_all

# Seed demo data (tourists, zones, police units, incidents)
python -m app.scripts.seed

# Run the API (http://127.0.0.1:8000 , docs at /docs)
python -m uvicorn app.main:app --reload
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

Open **http://localhost:5173** and log in with a [demo account](#demo-accounts).
Vite proxies `/api` and `/ws` to the backend automatically.

---

## Live Demo Mode

With the backend running, drive fake tourists around the map and trigger scripted
anomalies so the dashboard lights up during a presentation:

```bash
cd backend
python -m app.scripts.simulate                 # 40 steps, 2s interval
python -m app.scripts.simulate --steps 120 --interval 1
```

Scripted events: high-speed **abduction pattern** (step 8), **geo-fence** entry into a
high-risk zone (step 14), **prolonged inactivity** anomaly (step 20), and a **SOS** with
auto-dispatch (step 26). Keep the admin **Live Dashboard** open to watch alerts stream in.

---

## The ML Models

All three models train on **reproducible synthetic data** (`app/ml/generate_data.py`,
fixed seed) and are saved with joblib. The API loads them lazily and degrades to
rule-based fallbacks if an artifact is missing, so a demo never crashes.
Re-run everything and regenerate metrics with `python -m app.ml.train_all`.

### 1) Isolation Forest — Anomaly Detection *(unsupervised)*

- **Goal:** flag abnormal movement — sudden location drop-off/jump, prolonged
  inactivity, and unusual speed (possible vehicle abduction).
- **Features (per ping):** `speed_kmh`, `dist_from_prev_m`, `inactivity_min`,
  `dist_from_route_m`. Standard-scaled; ordering shared by training & inference
  (`ml_service.anomaly_features`).
- **Why Isolation Forest:** anomalies are rare and unlabeled in the real world; the
  forest isolates outliers by random partitioning without needing labels. We inject
  a labeled test set purely to *evaluate*.
- **Evaluation (25% hold-out, synthetic):**

  | precision | recall | F1 | ROC-AUC |
  |-----------|--------|----|---------|
  | **0.96** | **0.96** | **0.96** | **0.9996** |

  A `decision_function` score is squashed to a 0–1 anomaly probability for the UI.

### 2) Random Forest Regressor — Safety Score

- **Goal:** a continuous **0–100** safety score (higher = safer), updated live.
- **Features:** `zone_risk`, `hour` (time of day), `anomaly_score`, `crime_index`
  (mock), `weather_risk` (mock).
- **Target:** a weighted risk formula (+ noise); the forest learns and generalises it,
  matching the brief's "weighted model" while remaining a trainable ML artifact.
- **Evaluation (25% hold-out):** **R² = 0.899**, **MAE = 3.68** points.
- **Feature importances:** zone_risk 0.37, anomaly_score 0.27, crime_index 0.25,
  hour 0.06, weather_risk 0.05 — i.e. *where* you are and *how anomalously you move*
  dominate the score, which matches domain intuition.

### 3) DBSCAN — High-Risk Zone Discovery *(clustering)*

- **Goal:** auto-identify high-risk zones from historical incident coordinates.
- **Input:** incident lat/lng points (dense hotspots + scattered noise).
- **Params:** `eps = 0.005°` (~0.55 km), `min_samples = 12`. DBSCAN finds dense
  clusters and labels sparse points as noise (no need to pre-set *k*).
- **Output:** each cluster → convex-hull polygon in `ml_models/hotzones.json`,
  imported by the seed script as `source="auto"` **Zone** rows shown on the map.
- **Evaluation:** **4 clusters** recovered, **silhouette = 0.878** (well-separated),
  64 noise points correctly excluded.

> **On the near-perfect anomaly metrics:** the synthetic anomaly scenarios are
> deliberately extreme (abduction-speed, long inactivity, large jumps) with a
> *borderline* band of normal outliers mixed in, so the classes overlap enough for
> honest ~0.96 metrics rather than a suspicious 1.00. On messy real GPS data expect
> lower recall; the pipeline is built to be retrained on real traces.

---

## Digital ID Hash-Chain

Each tourist owns an append-only chain of `IdBlock` rows. Every block stores
`hash = SHA256(index | timestamp | event | data | previous_hash)`, linking to the
previous block's hash — so editing any historical record breaks every subsequent
hash. `GET /tourists/{id}/chain/verify` recomputes the links and reports tamper
status. This simulates a blockchain locally (no external chain needed).

```mermaid
flowchart LR
    G["Genesis<br/>prev=000…0"] --> B1["ID_ISSUED<br/>hash₁ = H(…,prev)"]
    B1 --> B2["CHECKIN<br/>hash₂ = H(…,hash₁)"]
    B2 --> B3["… future events<br/>hash₃ = H(…,hash₂)"]
```

---

## API Reference

Interactive docs at **`/docs`** (Swagger). Key endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` · `/api/config` | Health check · public map config (no secrets) |
| POST | `/api/auth/login` | JWT login (OAuth2 password flow, rate-limited) |
| POST | `/api/tourists` | Self-register tourist + mint digital ID |
| GET | `/api/tourists/{id}/qr` | QR code (base64 PNG) |
| GET | `/api/tourists/{id}/chain/verify` | Verify hash chain integrity |
| POST | `/api/tourists/{id}/location` | Ingest GPS ping → full pipeline |
| GET | `/api/tourists/{id}/safety-score` | Live safety score + breakdown |
| POST | `/api/tourists/{id}/sos` | Panic/SOS → dispatch nearest unit |
| POST | `/api/tourists/{id}/mark-missing` | Mark missing + auto E-FIR |
| GET | `/api/zones` · POST | List / create geo-fence polygons |
| GET | `/api/alerts` | Alert feed |
| GET/PATCH | `/api/incidents` | Incident list / advance lifecycle |
| GET | `/api/analytics/*` | Summary, over-time, by-type, zone-risk, severity |
| GET | `/api/audit-log` | Security audit trail (admin only) |
| GET | `/api/tourists/{id}/trip-plan` | Smart Trip Planner: day-by-day plan with per-day weather check |
| GET | `/api/crowd/forecast` · `/api/crowd/forecast/poi/{id}` | Crowd & Queue Forecast: per-zone forecast · per-POI queue estimate |
| GET | `/api/discovery` · `/api/discovery/offline-bundle` | Discovery: hidden spots/regional food/homestays · offline-cacheable bundle |
| GET | `/api/translate/guide/categories` · `/api/translate/guide/{category}` · POST `/api/translate/guide/phrase` | Multilingual Guide phrasebook |
| GET | `/api/permits/types` · GET/POST `/api/tourists/{id}/permits` · PATCH/POST `…/permits/{id}` · `…/{id}/confirm` | Permit & E-Pass Automation: draft → edit → explicit confirm (never auto-submitted) |
| GET | `/api/festivals` · `/api/festivals/near` | Festival & Local Event Intelligence |
| WS | `/ws/alerts?token=…` | Live alert/location/incident stream (admin token required) |

---

## Demo Accounts

| Role | Email | Password |
|------|-------|----------|
| **Police / Admin** | `admin@tourism.gov.in` | `admin123` |
| **Tourist** | `aarav@example.com` | `tourist123` |
| Tourist | `emma@example.com` / `rohan@…` / `sofia@…` / `kenji@…` | `tourist123` |

---

### Academic notes / evaluation checklist
- **Models:** documented above with features, rationale, and metrics (precision/recall/F1/ROC-AUC, R²/MAE, silhouette).
- **Reproducibility:** fixed seeds; `python -m app.ml.train_all` regenerates `metrics.json`.
- **Explainability:** safety score returns a per-factor breakdown; anomaly reasons are human-readable.
- **Data privacy:** documents are stored masked/mock; live tracking is opt-in.
"# major-project" 

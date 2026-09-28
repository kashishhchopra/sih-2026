# Synthetic dataset

Everything this project consumes — operational records and ML training data —
generated in one reproducible pass by
[`app/scripts/generate_synthetic_dataset.py`](../app/scripts/generate_synthetic_dataset.py)
and loaded through the real ORM by
[`app/scripts/load_synthetic_dataset.py`](../app/scripts/load_synthetic_dataset.py).

```bash
cd backend
python -m app.scripts.generate_synthetic_dataset          # writes data/synthetic/
alembic upgrade head                                      # if the schema is not there yet
python -m app.scripts.load_synthetic_dataset              # loads it into DATABASE_URL
```

The generator is fully seeded: the same arguments produce byte-identical files,
so a metric quoted in the report can be tied to a specific dataset via the
SHA-256 checksums in `manifest.json`.

---

## Profiles

Measured on the reference machine (`--seed 42`); `stress` is extrapolated.

| Profile | Tourists | History | Pings | Total rows | Size | Generation |
|---|---|---|---|---|---|---|
| `demo` | 40 | 14 d | 8 266 | 29 517 | 2.1 MB | ~2 s |
| `medium` | 250 | 30 d | 58 022 | 183 949 | 13.4 MB | ~17 s |
| **`full`** (default, generated) | **750** | **45 d** | **201 609** | **581 231** | **43.8 MB** | **~5 min** |
| `stress` | 3 000 | 90 d | ~1.6 M | ~4.5 M | ~350 MB | ~40 min |

```bash
python -m app.scripts.generate_synthetic_dataset --profile stress
python -m app.scripts.generate_synthetic_dataset --tourists 2000 --days 90 --seed 7
```

`--limit-pings N` on the loader loads a slice of the ping stream when a full
load is more than a demo needs.

---

## What is in `data/synthetic/`

### Operational data (loads into the database)

| File | Rows | Contents |
|---|---:|---|
| `zones.csv` | 34 | 26 hand-defined geo-fences + 8 `source=auto` DBSCAN hot-zones; polygon, risk level, crime index |
| `police_units.csv` | 22 | Real Guwahati Police Commissionerate stations, ~15 % marked unavailable |
| `tourists.csv` | 750 | KYC, itinerary JSON, emergency contacts JSON, trip window, live state, behaviour profile |
| `users.csv` | 626 | 5 admin accounts + tourist logins (passwords hashed at load) |
| `id_chain_events.csv` | 2 860 | Hash-chain events per tourist; digests computed at load (they are keyed with `SECRET_KEY`) |
| `location_pings.csv` | 201 609 | The GPS stream, with every derived field the pipeline computes |
| `alerts.csv` | 37 887 | `geofence` · `anomaly` · `route_deviation` · `sos` · `health_anomaly` · `fall_detected` |
| `incidents.csv` | 3 549 | Full lifecycle with response timings across all four severities |
| `incident_events.csv` | 12 943 | Per-incident status timeline |
| `devices.csv` | 232 | IoT wearables with firmware, battery, heartbeat |
| `device_telemetry.csv` | 14 134 | Band telemetry incl. heart rate, falls, hardware SOS presses |
| `efirs.csv` | 14 | Filed missing-person reports, some closed |
| `audit_logs.csv` | 7 554 | Logins (incl. failures), SOS, dispatches, E-FIR actions, admin activity |
| `weather_observations.csv` | 4 028 | Per-day per-landmark conditions, monsoon-weighted, OWM condition ids |

### ML training data

| File | Rows | Model | Columns |
|---|---:|---|---|
| `ml_movement.csv` | 120 000 | IsolationForest | `speed_kmh, dist_from_prev_m, inactivity_min, dist_from_route_m, label` (+ `scenario`, `hour`) |
| `ml_safety.csv` | 150 000 | RandomForestRegressor | `zone_risk, hour, anomaly_score, crime_index, weather_risk, safety_score` |
| `ml_incident_points.csv` | 24 989 | DBSCAN | `lat, lng` (+ `type`, `severity`) |

Column names match `app/ml/generate_data.py` exactly, so they are drop-in:

```bash
export SYNTHETIC_DATA_DIR=$PWD/data/synthetic   # PowerShell: $env:SYNTHETIC_DATA_DIR=...
python -m app.ml.train_all
```

Unset the variable and the trainers fall back to the original parametric
generators, so a fresh clone and `docker build` still work with no data files
present.

Measured on the generated `full` corpus:

| Model | Result |
|---|---|
| IsolationForest | precision **0.810**, recall **0.814**, F1 **0.812**, ROC-AUC **0.993** |
| RandomForest safety score | R² **0.917**, MAE **3.30** |
| DBSCAN hot-zones | **12** clusters, 1 869 noise points, silhouette **0.528** |

The anomaly F1 is lower than what the original parametric generator reports
(~0.97), and that is the honest number rather than a regression. The old
training set was, in effect, all *moving* pings; real traffic is ~84 % a phone
sitting still in a hotel or a museum. Training on the realistic mix leaves the
moving-but-normal tail sparse, and an unsupervised IsolationForest at 9 %
contamination flags part of it. ROC-AUC stays at 0.993, so the ranking is
essentially unchanged — it is the fixed threshold that costs precision.

---

## How the data is grounded

Reference constants live in
[`app/scripts/synthetic_reference.py`](../app/scripts/synthetic_reference.py)
and come from published sources rather than invention:

- **76 landmarks** with their real coordinates — Kamakhya Temple (26.1664 N,
  91.7055 E) and Umananda Island (26.1964 N, 91.7453 E) per Wikipedia,
  Cherrapunji (25.2912 N, 91.6783 E), plus the Guwahati wards and the wider
  Seven Sisters circuit (Shillong, Kaziranga, Tawang, Majuli, Loktak, …).
- **22 police units** mapped to the actual Guwahati Police Commissionerate
  station roster (Dispur, Panbazar, Paltan Bazar, Chandmari, Bharalumukh,
  Fatasil Ambari, Basistha, …) with their published control-room numbers.
- **Nationality mix** follows the Ministry of Tourism's Foreign Tourist Arrival
  source-country ranking (Bangladesh > USA > UK > Australia > Canada), scaled so
  domestic Indian travellers are ~78 % — North-East footfall is domestic-heavy.
  The pool holds 26 nationalities (22 of them drawn in the 750-tourist corpus),
  each with matching name pools, passport formats and dialling codes.
- **Crime indices** are anchored on the NCRB *Crime in India* pattern: transit
  hubs and night markets score highest, patrolled civic districts lowest.
- **Weather** uses real OpenWeatherMap condition ids mapped through the same
  risk function `app/services/weather.py` applies, monsoon-weighted for Jun–Sep.

No real person's data is present. Aadhaar numbers are emitted masked
(`XXXX-XXXX-nnnn`) exactly as the existing seed data does, and all names are
drawn from common given/family-name pools.

---

## The behaviour mix

Each tourist is assigned one scripted profile. The tail is the point — it is
what actually exercises the detector, the fences, SOS dispatch and the E-FIR
workflow:

| Profile | Share | What it produces |
|---|---:|---|
| `normal` | 60 % | Ordinary sightseeing, no alerts |
| `night_wanderer` | 8 % | Active 22:00–04:00 → low safety scores |
| `route_deviation` | 7 % | Strays > 2 km off the planned itinerary |
| `geofence_intrusion` | 7 % | Enters a high-risk or restricted fence |
| `inactivity` | 5 % | 55–190 minutes of silence |
| `high_speed_transit` | 4 % | 92–118 km/h — fast but legitimate (near-miss case) |
| `abduction_pattern` | 3 % | 135–245 km/h off-route jump → critical |
| `sos_panic` | 3 % | Panic button, unit auto-dispatched |
| `missing_person` | 2 % | Drops off the network → E-FIR filed |
| `device_fall` | 1 % | Wearable reports a fall + heart-rate anomaly |

Realism choices worth knowing about, because each one changes what the data
means:

- **Every derived field duplicates `services/monitoring.process_ping`.** A
  loaded ping's stored anomaly verdict and safety score are what the running
  application would recompute from it, including the offline weather mock.
- **Itineraries carry "en route" waypoints.** `min_distance_to_route` measures
  distance to the nearest *waypoint*; an itinerary of endpoints alone would
  report a tourist halfway along a legitimate 6 km road as 3 km off-route and
  the deviation alarm would fire on every normal journey.
- **Dwell and overnight periods emit stationary pings**, not silent gaps — a gap
  is the signature of the inactivity scenario, and leaving one would mean every
  tourist raised an anomaly every night.
- **Hotels are placed outside high-risk and restricted fences.** The pipeline
  raises a geofence alert per ping with no dedupe, so one tourist sleeping
  inside a fence would emit an alert every 30 minutes until morning.
- **Inter-city transfers are modelled as a coverage gap**, so the next ping is
  distant and the detector flags it — which is correct behaviour, and the
  resulting false positive is deliberately in the fixture for the operator
  workflow to close.
- **`ml_incident_points.csv` density is not a free parameter.** `train_zones.py`
  clusters with a fixed `eps=0.005°` and `min_samples=12`; scatter laid down
  thickly enough that an eps-circle holds 12 points stops being noise and
  clusters on its own. The scatter is capped below that threshold.

Two things in the data are *not* produced by the live pipeline, and are labelled
as such:

- **Legacy incident register** — the live pipeline only opens `high` anomaly
  incidents and `critical` geofence/SOS/missing ones, so a purely pipeline-derived
  corpus leaves the analytics severity chart with two bars. These rows stand for
  records migrated from the control room's earlier paper register.
- **`geofence` incidents** are emitted once per tourist per restricted zone on
  entry, modelling an operator escalation. The pipeline itself only raises
  geofence *alerts*.

---

## A note on `/api/ml/drift`

After loading, the drift endpoint reports `psi=1.47 significant drift` — and it
is wrong to read that as a data problem. `services/drift.py` compares the **500
most recent** pings against the training reference. In a backfilled historical
corpus those 500 rows all come from one narrow time window belonging to whoever
was travelling last, which at most timestamps means overnight hotel heartbeats
at ~0 km/h. Widen the window and the drift disappears:

| Live sample | PSI | Verdict |
|---|---:|---|
| 500 most recent pings | 1.4703 | significant drift |
| 500 randomly sampled pings | 0.0311 | stable |
| 20 000 most recent pings | 0.0024 | stable |
| Whole corpus (201 609 pings) | 0.0020 | stable |

So the training distribution matches live traffic almost exactly; the reading is
an artifact of PSI being measured on the tail of a bulk history load rather than
on a running system. Drive the API with `python -m app.scripts.simulate` for a
few minutes and the endpoint reports stable against genuinely live pings.

---

## Notes on loading

- Table **contents** are replaced by default; the schema is untouched, so
  Alembic still owns it. `--keep-existing` appends instead.
- Passwords are hashed with bcrypt at load time. The dataset reuses two demo
  passwords deliberately (`admin123` / `tourist123`, as published in the README),
  and the loader hashes each distinct one once — otherwise 662 accounts at
  ~250 ms each would take three minutes.
- **Device API keys are not loadable credentials.** `devices.csv` carries a
  deterministic stub; a loaded band is registered but not drivable. Re-register
  it through `POST /api/devices/register` to receive a real one-time key.
- Loading the `full` corpus takes ~20 s on SQLite.

## Repository size

`data/synthetic/` is ~46 MB. It regenerates byte-identically from
`--seed 42 --profile full`, so if that is too much for the repository, add
`backend/data/synthetic/` to `.gitignore` and keep the generator instead — the
`manifest.json` checksums are what pin a reported metric to a dataset, not the
CSVs themselves.

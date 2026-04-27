# Drone Readiness MVP — Use Case 1: Monitor Drone Availability

A working end-to-end system for monitoring drone availability and readiness via Raspberry Pi agent diagnostics.

---

## What This Use Case Does

The backend maintains a registry of drones. When a diagnostic is requested for a drone, the backend contacts that drone's Raspberry Pi agent over REST. The Pi agent simulates a local hardware self-check (battery, rotors, sensors, communications) and returns the results. The backend applies state rules and updates the drone's status to one of:

| Status        | Reason                                         |
|---------------|------------------------------------------------|
| `READY`       | Battery ≥ 60%, all hardware checks passed      |
| `CHARGING`    | Battery < 60%                                  |
| `MAINTENANCE` | Rotor or sensor check failed                   |
| `OFFLINE`     | Pi agent unreachable or timed out              |
| `ERROR`       | Unexpected internal failure                    |
| `DIAGNOSTIC`  | Diagnostic in progress (transitional)          |
| `IDLE`        | Known drone, not yet checked                   |

---

## Architecture

```
┌─────────────────────────────────────────┐
│             Browser / curl              │
│  GET /drones   POST /drones/{id}/diag   │
└────────────────────┬────────────────────┘
                     │
         ┌───────────▼───────────┐
         │   Backend (FastAPI)   │
         │   SQLite via SQLAlch. │
         └───┬──────┬──────┬─────┘
             │      │      │
      port 8001   8002   8003  (8004 = no agent → OFFLINE)
             │      │      │
         ┌───▼──┐ ┌─▼───┐ ┌▼────┐
         │Pi-001│ │Pi-002│ │Pi-003│
         │Alpha │ │Beta  │ │Gamma │
         └──────┘ └─────┘ └──────┘
```

**Backend → Pi agent communication:**  
`POST http://<agent_host>:<port>/diagnostic`  
The backend stores an `agent_url` per drone and calls `POST /diagnostic` on it. If the agent is unreachable or times out (10 s), the drone is marked `OFFLINE`.

---

## Project Structure

```
backend/
  app/
    api/          health.py, drones.py
    models/       drone.py, diagnostic.py
    schemas/      drone.py, diagnostic.py
    services/     diagnostic_service.py
    db/           database.py, seed.py
    main.py       FastAPI app + lifespan
  main.py         Uvicorn entry point
  requirements.txt

pi_agent/
  main.py         Pi agent (configurable via env vars)
  requirements.txt
  .env.example

frontend_optional/
  index.html      Single-page dashboard

tests/
  conftest.py
  test_drones.py
  test_diagnostic.py

run_demo.sh       Start everything with one command
```

---

## How to Run the Backend

```bash
cd backend
pip install -r requirements.txt
python main.py
```

The backend starts on **http://localhost:8000**.  
Auto-seeds 4 demo drones on first run.

- Dashboard:  http://localhost:8000  
- API docs:   http://localhost:8000/docs  
- Health:     http://localhost:8000/health  

---

## How to Run a Pi Agent

Each drone requires its own agent instance, configured via environment variables.

```bash
cd pi_agent
pip install -r requirements.txt

# Drone-Alpha: healthy
PI_AGENT_ID=pi-001 PORT=8001 BATTERY_PERCENT=85.0 ROTOR_OK=true SENSORS_OK=true python main.py

# Drone-Beta: low battery
PI_AGENT_ID=pi-002 PORT=8002 BATTERY_PERCENT=35.0 ROTOR_OK=true SENSORS_OK=true python main.py

# Drone-Gamma: rotor failure
PI_AGENT_ID=pi-003 PORT=8003 BATTERY_PERCENT=72.0 ROTOR_OK=false SENSORS_OK=true python main.py
```

On a real Raspberry Pi, copy `pi_agent/` to the device and run it with the appropriate env vars pointing `BACKEND_URL` at the backend host.

---

## Run Everything at Once (Demo)

```bash
chmod +x run_demo.sh
./run_demo.sh
```

This starts 3 Pi agents (ports 8001–8003) and the backend (port 8000). Drone-Delta intentionally has no agent to demo the OFFLINE state.

---

## How to Seed / Reset Demo Data

```bash
# Seed happens automatically on backend startup.
# To reset manually:
curl -X POST http://localhost:8000/seed
```

Or click **Reset Demo Data** in the dashboard.

---

## API Reference

| Method | Path                        | Description                          |
|--------|-----------------------------|--------------------------------------|
| GET    | `/health`                   | Backend health check                 |
| GET    | `/drones`                   | List all drones with current status  |
| GET    | `/drones/{id}`              | Get a single drone                   |
| POST   | `/drones/{id}/diagnostic`   | Trigger a diagnostic check           |
| POST   | `/seed`                     | Wipe and re-seed demo data           |

### Example: trigger a diagnostic

```bash
curl -X POST http://localhost:8000/drones/1/diagnostic | python -m json.tool
```

Response:
```json
{
  "id": 1,
  "drone_id": 1,
  "battery_percent": 85.0,
  "rotor_ok": true,
  "sensors_ok": true,
  "communication_ok": true,
  "computed_status": "READY",
  "message": "All systems nominal. Drone is ready for deployment.",
  "checked_at": "2026-04-20T12:00:00+00:00"
}
```

---

## Testing the Four Drone States

### READY — Drone-Alpha (id: 1)
Requires pi-agent on port 8001 running with `BATTERY_PERCENT=85 ROTOR_OK=true SENSORS_OK=true`.

```bash
curl -X POST http://localhost:8000/drones/1/diagnostic
# computed_status: "READY"
```

### CHARGING — Drone-Beta (id: 2)
Requires pi-agent on port 8002 running with `BATTERY_PERCENT=35`.

```bash
curl -X POST http://localhost:8000/drones/2/diagnostic
# computed_status: "CHARGING"
```

### MAINTENANCE — Drone-Gamma (id: 3)
Requires pi-agent on port 8003 running with `ROTOR_OK=false`.

```bash
curl -X POST http://localhost:8000/drones/3/diagnostic
# computed_status: "MAINTENANCE"
```

### OFFLINE — Drone-Delta (id: 4)
No agent is running on port 8004. The backend times out and marks the drone offline.

```bash
curl -X POST http://localhost:8000/drones/4/diagnostic
# computed_status: "OFFLINE"
```

---

## Running Tests

```bash
cd backend
# use the project venv or install deps first
python -m pytest tests/ -v
```

Tests live in `backend/tests/` and use an in-memory SQLite database with all Pi agent HTTP calls mocked — no agents need to be running.

> **Note:** Run pytest from inside `backend/`, not from the project root. The project root contains `code.py` which shadows Python's stdlib `code` module and breaks pytest's debugger setup.

---

## State Transition Rules

```
communication_ok == False  →  OFFLINE
battery_percent  <  60     →  CHARGING
rotor_ok == False          →  MAINTENANCE
sensors_ok == False        →  MAINTENANCE
(all pass)                 →  READY
```

Priority order: OFFLINE > CHARGING > MAINTENANCE > READY.

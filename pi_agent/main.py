"""
Raspberry Pi drone agent.

Represents one physical drone. Exposes a small REST API that the backend calls
when it needs a diagnostic reading. All drone characteristics are controlled via
environment variables so a single script can simulate any scenario.

Environment variables
---------------------
PI_AGENT_ID       Identifier for this Pi (default: pi-001)
DRONE_ID          Drone logical ID sent back in responses (default: drone-1)
PORT              Port to listen on (default: 8001)
BACKEND_URL       Backend base URL — used only if the agent needs to push events
                  (not required for this use case, default: http://localhost:8000)

Simulated hardware state (set these to control the demo scenario)
-----------------------------------------------------------------
BATTERY_PERCENT   float, 0–100 (default: 85.0)
ROTOR_OK          true / false (default: true)
SENSORS_OK        true / false (default: true)
"""

import os
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
PI_AGENT_ID = os.getenv("PI_AGENT_ID", "pi-001")
DRONE_ID = os.getenv("DRONE_ID", "drone-1")
PORT = int(os.getenv("PORT", "8001"))
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

BATTERY_PERCENT = float(os.getenv("BATTERY_PERCENT", "85.0"))
ROTOR_OK = os.getenv("ROTOR_OK", "true").lower() in ("1", "true", "yes")
SENSORS_OK = os.getenv("SENSORS_OK", "true").lower() in ("1", "true", "yes")

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title=f"Pi Agent — {PI_AGENT_ID}",
    description="Drone self-check agent running on Raspberry Pi.",
    version="1.0.0",
)


class DiagnosticRequest(BaseModel):
    drone_id: Optional[str] = None


class DiagnosticPayload(BaseModel):
    pi_agent_id: str
    drone_id: str
    battery_percent: float
    rotor_ok: bool
    sensors_ok: bool
    communication_ok: bool
    message: str
    checked_at: str


@app.get("/health")
def health():
    return {
        "status": "ok",
        "pi_agent_id": PI_AGENT_ID,
        "drone_id": DRONE_ID,
    }


@app.post("/diagnostic", response_model=DiagnosticPayload)
def run_diagnostic(request: DiagnosticRequest) -> DiagnosticPayload:
    """
    Simulate a drone self-check.

    In production this would query real hardware sensors.
    Here the values come from environment variables configured per-drone.
    """
    battery = _read_battery()
    rotor_ok = _check_rotors()
    sensors_ok = _check_sensors()
    communication_ok = True  # by definition: if we respond, comms are up

    issues = []
    if battery < 60:
        issues.append(f"battery low ({battery:.1f}%)")
    if not rotor_ok:
        issues.append("rotor failure detected")
    if not sensors_ok:
        issues.append("sensor failure detected")

    if issues:
        message = "Self-check issues: " + "; ".join(issues) + "."
    else:
        message = "Self-check complete. All systems nominal."

    return DiagnosticPayload(
        pi_agent_id=PI_AGENT_ID,
        drone_id=DRONE_ID,
        battery_percent=battery,
        rotor_ok=rotor_ok,
        sensors_ok=sensors_ok,
        communication_ok=communication_ok,
        message=message,
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Simulated hardware reads
# ---------------------------------------------------------------------------

def _read_battery() -> float:
    """Return configured battery level (simulates ADC read on real hardware)."""
    return BATTERY_PERCENT


def _check_rotors() -> bool:
    """Return configured rotor status (simulates ESC/motor feedback check)."""
    return ROTOR_OK


def _check_sensors() -> bool:
    """Return configured sensor status (simulates IMU/GPS/barometer checks)."""
    return SENSORS_OK


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"[pi-agent] Starting {PI_AGENT_ID} on port {PORT}")
    print(f"[pi-agent] Config: battery={BATTERY_PERCENT}%, rotor_ok={ROTOR_OK}, sensors_ok={SENSORS_OK}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)

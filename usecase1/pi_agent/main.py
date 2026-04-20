"""
Drone Pi Agent — simulates the drone's onboard self-check.

The Facility System calls POST /diagnostic.
The drone performs battery, rotor and sensor checks and returns the result.

Configure via environment variables:
  PORT            port to listen on     (default: 8001)
  BATTERY         battery percentage    (default: 85.0)
  ROTORS_OK       true / false          (default: true)
  SENSORS_OK      true / false          (default: true)

Run: python main.py
"""

import os
import uvicorn
from fastapi import FastAPI

PORT       = int(os.getenv("PORT", "8001"))
BATTERY    = float(os.getenv("BATTERY", "85.0"))
ROTORS_OK  = os.getenv("ROTORS_OK",  "true").lower() == "true"
SENSORS_OK = os.getenv("SENSORS_OK", "true").lower() == "true"

app = FastAPI(title=f"Drone Agent (port {PORT})")


@app.get("/health")
def health():
    return {"status": "ok", "port": PORT}


@app.post("/diagnostic")
def run_diagnostic():
    """Drone performs self-check and returns the result."""
    return {
        "battery_percent": BATTERY,
        "rotors_ok":       ROTORS_OK,
        "sensors_ok":      SENSORS_OK,
    }


if __name__ == "__main__":
    print(f"[drone-agent] port={PORT}  battery={BATTERY}%  rotors={ROTORS_OK}  sensors={SENSORS_OK}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)

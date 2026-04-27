#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run_demo.sh — Start all demo Pi agents and the backend in one command.
#
# Usage:
#   chmod +x run_demo.sh
#   ./run_demo.sh
#
# Press Ctrl-C to stop everything.
# ---------------------------------------------------------------------------

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT/backend"
AGENT_DIR="$ROOT/pi_agent"

# Kill all background jobs when the script exits
cleanup() {
  echo ""
  echo "[demo] Shutting down…"
  kill 0
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Pi agent — Drone-Alpha: healthy (battery 85%, all OK)  → expects READY
# ---------------------------------------------------------------------------
echo "[demo] Starting Pi agent for Drone-Alpha on port 8001…"
(
  cd "$AGENT_DIR"
  PI_AGENT_ID=pi-001 DRONE_ID=drone-1 PORT=8001 \
  BATTERY_PERCENT=85.0 ROTOR_OK=true SENSORS_OK=true \
  python main.py
) &

# ---------------------------------------------------------------------------
# Pi agent — Drone-Beta: low battery (35%)  → expects CHARGING
# ---------------------------------------------------------------------------
echo "[demo] Starting Pi agent for Drone-Beta on port 8002…"
(
  cd "$AGENT_DIR"
  PI_AGENT_ID=pi-002 DRONE_ID=drone-2 PORT=8002 \
  BATTERY_PERCENT=35.0 ROTOR_OK=true SENSORS_OK=true \
  python main.py
) &

# ---------------------------------------------------------------------------
# Pi agent — Drone-Gamma: rotor failure  → expects MAINTENANCE
# ---------------------------------------------------------------------------
echo "[demo] Starting Pi agent for Drone-Gamma on port 8003…"
(
  cd "$AGENT_DIR"
  PI_AGENT_ID=pi-003 DRONE_ID=drone-3 PORT=8003 \
  BATTERY_PERCENT=72.0 ROTOR_OK=false SENSORS_OK=true \
  python main.py
) &

# Drone-Delta has no agent running → backend will report OFFLINE

# Give agents a moment to bind their ports
sleep 1

# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------
echo "[demo] Starting backend on port 8000…"
echo "[demo] Dashboard → http://localhost:8000"
echo "[demo] API docs  → http://localhost:8000/docs"
echo ""
(
  cd "$BACKEND_DIR"
  python main.py
)

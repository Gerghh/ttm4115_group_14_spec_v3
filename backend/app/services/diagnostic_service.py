import httpx
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from ..models.drone import Drone
from ..models.diagnostic import DiagnosticResult

BATTERY_READY_THRESHOLD = 60.0
AGENT_TIMEOUT = 10.0  # seconds before marking drone OFFLINE


def compute_status(
    battery: float, rotor_ok: bool, sensors_ok: bool, communication_ok: bool
) -> tuple[str, str]:
    """Apply state rules and return (status, human-readable message)."""
    if not communication_ok:
        return "OFFLINE", "Communication with Pi agent failed. Drone is unreachable."
    if battery < BATTERY_READY_THRESHOLD:
        return (
            "CHARGING",
            f"Battery at {battery:.1f}% — below the {BATTERY_READY_THRESHOLD:.0f}% threshold. Drone is charging.",
        )
    if not rotor_ok and not sensors_ok:
        return "MAINTENANCE", "Rotor check failed and sensor check failed. Drone requires maintenance."
    if not rotor_ok:
        return "MAINTENANCE", "Rotor check failed. Drone requires maintenance."
    if not sensors_ok:
        return "MAINTENANCE", "Sensor check failed. Drone requires maintenance."
    return "READY", "All systems nominal. Drone is ready for deployment."


async def run_diagnostic(drone_id: int, db: Session) -> DiagnosticResult:
    drone = db.query(Drone).filter(Drone.id == drone_id).first()
    if not drone:
        raise ValueError(f"Drone {drone_id} not found")

    drone.status = "DIAGNOSTIC"
    db.commit()

    battery = 0.0
    rotor_ok = False
    sensors_ok = False
    communication_ok = False
    agent_message = ""

    try:
        async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
            resp = await client.post(
                f"{drone.agent_url}/diagnostic",
                json={"drone_id": drone.raspberry_pi_id},
            )
            resp.raise_for_status()
            data = resp.json()
            battery = float(data["battery_percent"])
            rotor_ok = bool(data["rotor_ok"])
            sensors_ok = bool(data["sensors_ok"])
            communication_ok = bool(data.get("communication_ok", True))
            agent_message = data.get("message", "")
    except httpx.TimeoutException:
        communication_ok = False
        agent_message = "Pi agent request timed out."
    except httpx.ConnectError:
        communication_ok = False
        agent_message = "Could not connect to Pi agent."
    except Exception as exc:
        communication_ok = False
        agent_message = f"Unexpected error contacting Pi agent: {exc}"

    status, status_message = compute_status(battery, rotor_ok, sensors_ok, communication_ok)

    # Combine agent message with computed status message for full context
    final_message = f"{status_message}" + (f" | Agent: {agent_message}" if agent_message else "")

    now = datetime.now(timezone.utc)
    result = DiagnosticResult(
        drone_id=drone.id,
        battery_percent=battery,
        rotor_ok=rotor_ok,
        sensors_ok=sensors_ok,
        communication_ok=communication_ok,
        computed_status=status,
        message=final_message,
        checked_at=now,
    )
    db.add(result)

    drone.status = status
    drone.battery_percent = battery
    drone.rotor_ok = rotor_ok
    drone.sensors_ok = sensors_ok
    drone.communication_ok = communication_ok
    drone.last_check_at = now
    drone.last_error_message = final_message if status != "READY" else None

    db.commit()
    db.refresh(result)
    return result

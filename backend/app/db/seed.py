from sqlalchemy.orm import Session
from ..models.drone import Drone

# Four drones covering all demo scenarios:
# Alpha  → healthy, will become READY
# Beta   → low battery, will become CHARGING
# Gamma  → rotor failure, will become MAINTENANCE
# Delta  → no agent running (port 8004), will become OFFLINE
SEED_DRONES = [
    {
        "name": "Drone-Alpha",
        "raspberry_pi_id": "pi-001",
        "agent_url": "http://localhost:8001",
        "facility_name": "Warehouse A",
        "status": "IDLE",
        "battery_percent": 85.0,
        "rotor_ok": True,
        "sensors_ok": True,
        "communication_ok": True,
        "max_payload_kg": 5.0,
    },
    {
        "name": "Drone-Beta",
        "raspberry_pi_id": "pi-002",
        "agent_url": "http://localhost:8002",
        "facility_name": "Warehouse A",
        "status": "IDLE",
        "battery_percent": 35.0,
        "rotor_ok": True,
        "sensors_ok": True,
        "communication_ok": True,
        "max_payload_kg": 5.0,
    },
    {
        "name": "Drone-Gamma",
        "raspberry_pi_id": "pi-003",
        "agent_url": "http://localhost:8003",
        "facility_name": "Warehouse B",
        "status": "IDLE",
        "battery_percent": 72.0,
        "rotor_ok": False,
        "sensors_ok": True,
        "communication_ok": True,
        "max_payload_kg": 8.0,
    },
    {
        "name": "Drone-Delta",
        "raspberry_pi_id": "pi-004",
        "agent_url": "http://localhost:8004",  # intentionally no agent running here
        "facility_name": "Warehouse B",
        "status": "OFFLINE",
        "battery_percent": 0.0,
        "rotor_ok": False,
        "sensors_ok": False,
        "communication_ok": False,
        "max_payload_kg": 5.0,
    },
]


def seed_drones(db: Session) -> None:
    if db.query(Drone).count() > 0:
        print("[seed] Database already contains drones — skipping seed.")
        return
    for data in SEED_DRONES:
        db.add(Drone(**data))
    db.commit()
    print(f"[seed] Inserted {len(SEED_DRONES)} demo drones.")


def reseed_drones(db: Session) -> None:
    """Wipe and re-seed. Used by the POST /seed admin endpoint."""
    from ..models.diagnostic import DiagnosticResult

    db.query(DiagnosticResult).delete()
    db.query(Drone).delete()
    db.commit()
    for data in SEED_DRONES:
        db.add(Drone(**data))
    db.commit()
    print(f"[seed] Re-seeded {len(SEED_DRONES)} demo drones.")

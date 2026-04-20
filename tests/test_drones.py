"""Tests for GET /drones and GET /drones/{id} endpoints."""
import pytest


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_list_drones_returns_seeded_drones(client):
    resp = client.get("/drones")
    assert resp.status_code == 200
    drones = resp.json()
    assert len(drones) == 4
    names = {d["name"] for d in drones}
    assert {"Drone-Alpha", "Drone-Beta", "Drone-Gamma", "Drone-Delta"} == names


def test_list_drones_schema(client):
    resp = client.get("/drones")
    drone = resp.json()[0]
    required_fields = {
        "id", "name", "raspberry_pi_id", "facility_name",
        "status", "battery_percent", "rotor_ok", "sensors_ok",
        "communication_ok", "max_payload_kg", "last_check_at", "last_error_message",
    }
    assert required_fields.issubset(drone.keys())


def test_get_drone_by_id(client):
    # Get list first to find a real ID
    drones = client.get("/drones").json()
    alpha = next(d for d in drones if d["name"] == "Drone-Alpha")
    resp = client.get(f"/drones/{alpha['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Drone-Alpha"
    assert resp.json()["battery_percent"] == 85.0
    assert resp.json()["rotor_ok"] is True


def test_get_drone_not_found(client):
    resp = client.get("/drones/99999")
    assert resp.status_code == 404


def test_drone_alpha_initial_state(client):
    drones = client.get("/drones").json()
    alpha = next(d for d in drones if d["name"] == "Drone-Alpha")
    assert alpha["status"] == "IDLE"
    assert alpha["battery_percent"] >= 60
    assert alpha["rotor_ok"] is True
    assert alpha["sensors_ok"] is True


def test_drone_beta_low_battery_initial_state(client):
    drones = client.get("/drones").json()
    beta = next(d for d in drones if d["name"] == "Drone-Beta")
    assert beta["battery_percent"] < 60


def test_drone_gamma_rotor_failure_initial_state(client):
    drones = client.get("/drones").json()
    gamma = next(d for d in drones if d["name"] == "Drone-Gamma")
    assert gamma["rotor_ok"] is False


def test_reseed_endpoint(client):
    resp = client.post("/seed")
    assert resp.status_code == 200
    assert "re-seeded" in resp.json()["message"].lower()
    # Drones should still be present after reseed
    drones = client.get("/drones").json()
    assert len(drones) == 4

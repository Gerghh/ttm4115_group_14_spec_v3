"""Tests for POST /drones/{id}/diagnostic with mocked Pi agent responses."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_agent_response(battery: float, rotor_ok: bool, sensors_ok: bool, communication_ok: bool = True):
    """Build a mock httpx response that the diagnostic service will parse."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "battery_percent": battery,
        "rotor_ok": rotor_ok,
        "sensors_ok": sensors_ok,
        "communication_ok": communication_ok,
        "message": "Simulated self-check complete.",
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _get_drone_id(client, name: str) -> int:
    drones = client.get("/drones").json()
    return next(d["id"] for d in drones if d["name"] == name)


# ---------------------------------------------------------------------------
# Compute status unit tests (no HTTP needed)
# ---------------------------------------------------------------------------

def test_compute_status_ready():
    from app.services.diagnostic_service import compute_status
    status, msg = compute_status(85.0, True, True, True)
    assert status == "READY"
    assert "nominal" in msg.lower()


def test_compute_status_offline():
    from app.services.diagnostic_service import compute_status
    status, msg = compute_status(85.0, True, True, False)
    assert status == "OFFLINE"
    assert "communication" in msg.lower()


def test_compute_status_charging():
    from app.services.diagnostic_service import compute_status
    status, msg = compute_status(35.0, True, True, True)
    assert status == "CHARGING"
    assert "35.0%" in msg


def test_compute_status_maintenance_rotor():
    from app.services.diagnostic_service import compute_status
    status, msg = compute_status(75.0, False, True, True)
    assert status == "MAINTENANCE"
    assert "rotor" in msg.lower()


def test_compute_status_maintenance_sensors():
    from app.services.diagnostic_service import compute_status
    status, msg = compute_status(75.0, True, False, True)
    assert status == "MAINTENANCE"
    assert "sensor" in msg.lower()


def test_compute_status_maintenance_both():
    from app.services.diagnostic_service import compute_status
    status, msg = compute_status(75.0, False, False, True)
    assert status == "MAINTENANCE"


# Offline beats charging
def test_compute_status_offline_beats_low_battery():
    from app.services.diagnostic_service import compute_status
    status, _ = compute_status(10.0, True, True, False)
    assert status == "OFFLINE"


# ---------------------------------------------------------------------------
# Diagnostic endpoint integration tests (Pi agent mocked)
# ---------------------------------------------------------------------------

def test_diagnostic_not_found(client):
    resp = client.post("/drones/99999/diagnostic")
    assert resp.status_code == 404


def test_diagnostic_alpha_becomes_ready(client):
    drone_id = _get_drone_id(client, "Drone-Alpha")

    mock_resp = _mock_agent_response(battery=85.0, rotor_ok=True, sensors_ok=True)

    with patch("app.services.diagnostic_service.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(return_value=mock_resp))
        )
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = client.post(f"/drones/{drone_id}/diagnostic")

    assert resp.status_code == 200
    data = resp.json()
    assert data["computed_status"] == "READY"
    assert data["battery_percent"] == 85.0
    assert data["rotor_ok"] is True
    assert data["sensors_ok"] is True

    # Verify drone state updated in DB
    drone = client.get(f"/drones/{drone_id}").json()
    assert drone["status"] == "READY"
    assert drone["last_error_message"] is None


def test_diagnostic_beta_becomes_charging(client):
    drone_id = _get_drone_id(client, "Drone-Beta")

    mock_resp = _mock_agent_response(battery=35.0, rotor_ok=True, sensors_ok=True)

    with patch("app.services.diagnostic_service.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(return_value=mock_resp))
        )
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = client.post(f"/drones/{drone_id}/diagnostic")

    assert resp.status_code == 200
    data = resp.json()
    assert data["computed_status"] == "CHARGING"
    assert data["battery_percent"] == 35.0

    drone = client.get(f"/drones/{drone_id}").json()
    assert drone["status"] == "CHARGING"
    assert drone["last_error_message"] is not None


def test_diagnostic_gamma_becomes_maintenance(client):
    drone_id = _get_drone_id(client, "Drone-Gamma")

    mock_resp = _mock_agent_response(battery=72.0, rotor_ok=False, sensors_ok=True)

    with patch("app.services.diagnostic_service.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(return_value=mock_resp))
        )
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = client.post(f"/drones/{drone_id}/diagnostic")

    assert resp.status_code == 200
    data = resp.json()
    assert data["computed_status"] == "MAINTENANCE"
    assert data["rotor_ok"] is False

    drone = client.get(f"/drones/{drone_id}").json()
    assert drone["status"] == "MAINTENANCE"


def test_diagnostic_delta_becomes_offline_on_connect_error(client):
    """Pi agent unreachable → OFFLINE."""
    drone_id = _get_drone_id(client, "Drone-Delta")

    import httpx as _httpx

    with patch("app.services.diagnostic_service.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(
                post=AsyncMock(side_effect=_httpx.ConnectError("Connection refused"))
            )
        )
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = client.post(f"/drones/{drone_id}/diagnostic")

    assert resp.status_code == 200
    data = resp.json()
    assert data["computed_status"] == "OFFLINE"
    assert data["communication_ok"] is False

    drone = client.get(f"/drones/{drone_id}").json()
    assert drone["status"] == "OFFLINE"


def test_diagnostic_timeout_becomes_offline(client):
    """Pi agent timeout → OFFLINE."""
    drone_id = _get_drone_id(client, "Drone-Alpha")

    import httpx as _httpx

    with patch("app.services.diagnostic_service.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(
                post=AsyncMock(side_effect=_httpx.TimeoutException("Timeout"))
            )
        )
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = client.post(f"/drones/{drone_id}/diagnostic")

    assert resp.status_code == 200
    assert resp.json()["computed_status"] == "OFFLINE"


def test_diagnostic_result_schema(client):
    drone_id = _get_drone_id(client, "Drone-Alpha")

    mock_resp = _mock_agent_response(85.0, True, True)

    with patch("app.services.diagnostic_service.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(return_value=mock_resp))
        )
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        data = client.post(f"/drones/{drone_id}/diagnostic").json()

    required = {"id", "drone_id", "battery_percent", "rotor_ok", "sensors_ok",
                "communication_ok", "computed_status", "message", "checked_at"}
    assert required.issubset(data.keys())

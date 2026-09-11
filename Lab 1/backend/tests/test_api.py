"""Integration tests for FastAPI endpoints, WebSocket history delivery, and live streaming."""

from fastapi.testclient import TestClient
from app.main import app, thermometer_state, manager, settings


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "sensor_addresses" in data
    assert "history_samples" in data
    assert data["sensor_addresses"]["s1"] == "28-31-F5-A8-11-00-00-E4"
    assert data["sensor_addresses"]["s2"] == "28-E4-C4-EB-10-00-00-1A"


def test_get_history_endpoint():
    thermometer_state.clear_history()
    thermometer_state.update_sensor_temp(1, 21.5)
    thermometer_state.update_sensor_temp(2, 30.5)
    for i in range(10):
        thermometer_state.record_tick(ts=1756510000 + i)

    client = TestClient(app)
    response = client.get("/api/history")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 10
    assert len(data["history"]) == 10
    assert data["history"][0]["ts"] == 1756510000
    assert data["history"][-1]["ts"] == 1756510009


def test_button_control_endpoint():
    client = TestClient(app)
    original_dev_mode = settings.DEV_MODE
    settings.DEV_MODE = True
    try:
        # Valid button 1
        response = client.post("/api/buttons/1", json={"on": True})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["button_id"] == 1
        assert data["on"] is True
        assert thermometer_state.button1_on is True

        # Valid button 2
        response = client.post("/api/buttons/2", json={"on": False})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["button_id"] == 2
        assert data["on"] is False
        assert thermometer_state.button2_on is False

        # Invalid button id
        response = client.post("/api/buttons/3", json={"on": True})
        assert response.status_code == 400
    finally:
        settings.DEV_MODE = original_dev_mode


def test_websocket_receives_history_and_subsequent_live_samples():
    """Verify that a connecting WebSocket receives history array and then live sample broadcasts."""
    thermometer_state.clear_history()
    thermometer_state.update_sensor_temp(1, 24.5)
    thermometer_state.update_sensor_temp(2, 33.1)
    thermometer_state.mark_message_received()

    # Pre-populate 5 historical ticks
    base_ts = 1756512000
    for i in range(5):
        thermometer_state.record_tick(ts=base_ts + i)

    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        # First message on connect should be the history list
        history_msg = websocket.receive_json()
        assert isinstance(history_msg, list)
        assert len(history_msg) == 5
        assert history_msg[0]["ts"] == base_ts
        assert history_msg[-1]["ts"] == base_ts + 4
        assert history_msg[-1]["s1"]["c"] == 24.5

        # Broadcast next live sample using websocket's portal
        next_sample = {
            "ts": base_ts + 5,
            "s1": {"ok": True, "c": 24.7},
            "s2": {"ok": True, "c": 33.2},
            "btn1": False,
            "btn2": True,
        }
        websocket.portal.call(manager.broadcast, next_sample)

        live_msg = websocket.receive_json()
        assert isinstance(live_msg, dict)
        assert live_msg["ts"] == base_ts + 5
        assert live_msg["s1"]["c"] == 24.7
        assert live_msg["btn2"] is True

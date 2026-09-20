"""Unit and integration tests for email alert system, state transitions, and custom messages."""

import time
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.alerts import EmailAlertManager
from app.config import Settings
from app.main import alert_manager, app


def test_alert_settings_api():
    client = TestClient(app)

    # 1. Get initial settings
    response = client.get("/api/settings/alerts")
    assert response.status_code == 200
    data = response.json()
    assert "recipient_email" in data
    assert "min_temperature_c" in data
    assert "max_temperature_c" in data
    assert "low_message" in data
    assert "high_message" in data
    assert data["smtp_sender"] == "itworksonmymachine.sd@gmail.com"

    # 2. Update settings
    update_payload = {
        "enabled": True,
        "recipient_email": "alerts-test@example.com",
        "min_temperature_c": 18.0,
        "max_temperature_c": 32.5,
        "low_message": "Warning: Frost hazard detected!",
        "high_message": "Warning: Overheat hazard detected!",
        "cooldown_seconds": 120,
    }
    response = client.post("/api/settings/alerts", json=update_payload)
    assert response.status_code == 200
    updated = response.json()
    assert updated["enabled"] is True
    assert updated["recipient_email"] == "alerts-test@example.com"
    assert updated["min_temperature_c"] == 18.0
    assert updated["max_temperature_c"] == 32.5
    assert updated["low_message"] == "Warning: Frost hazard detected!"
    assert updated["high_message"] == "Warning: Overheat hazard detected!"
    assert updated["cooldown_seconds"] == 120


def test_alert_email_formatting_includes_custom_messages():
    settings = Settings()
    mgr = EmailAlertManager(settings)

    # Test Sensor 1 Max Threshold
    subject, text, html = mgr.format_alert_message(
        sensor_id=1,
        current_temp_c=36.4,
        threshold_type="maximum",
        threshold_val_c=35.0,
        custom_message="Critical lab temperature exceeded!",
    )
    assert "Sensor 1" in subject
    assert "MAXIMUM" in subject
    assert "36.4 °C" in subject
    assert "Critical lab temperature exceeded!" in text
    assert "Sensor 1" in text
    assert settings.SENSOR_1_ADDRESS in text
    assert "36.4 °C" in text
    assert "35.0 °C" in text
    assert "Critical lab temperature exceeded!" in html

    # Test Sensor 2 Min Threshold
    subject2, text2, html2 = mgr.format_alert_message(
        sensor_id=2,
        current_temp_c=12.1,
        threshold_type="minimum",
        threshold_val_c=15.0,
        custom_message="Sensor is dangerously cold!",
    )
    assert "Sensor 2" in subject2
    assert "MINIMUM" in subject2
    assert "12.1 °C" in subject2
    assert "Sensor is dangerously cold!" in text2
    assert settings.SENSOR_2_ADDRESS in text2


def test_state_transition_single_email_and_reset_behavior():
    """
    Verify:
    1. Entering HIGH sends exactly ONE email.
    2. Remaining in HIGH sends 0 additional emails regardless of elapsed time.
    3. Returning to NORMAL sends 0 emails and resets sensor alert state.
    4. Crossing HIGH again sends a NEW email.
    5. Same sequence for LOW threshold.
    """
    settings = Settings()
    mgr = EmailAlertManager(settings)
    mgr.update_settings(
        enabled=True,
        recipient_email="student@uiowa.edu",
        min_temperature_c=16.0,
        max_temperature_c=34.0,
        low_message="Low temp detected!",
        high_message="High temp detected!",
    )

    sent_emails = []

    def mock_send(recipient, subject, text, html=None):
        sent_emails.append({"to": recipient, "subject": subject, "text": text})

    mgr.send_email_async = mock_send

    def sample_with_s1(temp_c):
        return {
            "ts": int(time.time()),
            "s1": {"ok": True, "c": temp_c},
            "s2": {"ok": True, "c": 25.0},
            "btn1": False,
            "btn2": False,
        }

    # Step 1: Normal 22.0°C -> 0 emails
    mgr.check_sample_and_alert(sample_with_s1(22.0))
    assert len(sent_emails) == 0
    assert mgr.sensor_states[1] == "NORMAL"

    # Step 2: Crosses max threshold (36.0°C) -> Sends 1 HIGH email
    mgr.check_sample_and_alert(sample_with_s1(36.0))
    assert len(sent_emails) == 1
    assert "Sensor 1" in sent_emails[-1]["subject"]
    assert "MAXIMUM" in sent_emails[-1]["subject"]
    assert "High temp detected!" in sent_emails[-1]["text"]
    assert mgr.sensor_states[1] == "HIGH"

    # Step 3: Stays HIGH (38.0°C, 40.0°C) -> No additional emails
    mgr.check_sample_and_alert(sample_with_s1(38.0))
    mgr.check_sample_and_alert(sample_with_s1(40.0))
    assert len(sent_emails) == 1
    assert mgr.sensor_states[1] == "HIGH"

    # Step 4: Returns to NORMAL (25.0°C) -> No email sent, state resets to NORMAL
    mgr.check_sample_and_alert(sample_with_s1(25.0))
    assert len(sent_emails) == 1
    assert mgr.sensor_states[1] == "NORMAL"

    # Step 5: Crosses max threshold again (37.0°C) -> Sends NEW HIGH email
    mgr.check_sample_and_alert(sample_with_s1(37.0))
    assert len(sent_emails) == 2
    assert "Sensor 1" in sent_emails[-1]["subject"]
    assert "MAXIMUM" in sent_emails[-1]["subject"]
    assert mgr.sensor_states[1] == "HIGH"

    # Step 6: Returns to NORMAL (20.0°C)
    mgr.check_sample_and_alert(sample_with_s1(20.0))
    assert len(sent_emails) == 2
    assert mgr.sensor_states[1] == "NORMAL"

    # Step 7: Drops below MIN threshold (14.0°C) -> Sends 1 LOW email
    mgr.check_sample_and_alert(sample_with_s1(14.0))
    assert len(sent_emails) == 3
    assert "Sensor 1" in sent_emails[-1]["subject"]
    assert "MINIMUM" in sent_emails[-1]["subject"]
    assert "Low temp detected!" in sent_emails[-1]["text"]
    assert mgr.sensor_states[1] == "LOW"

    # Step 8: Stays LOW (12.0°C) -> No additional email
    mgr.check_sample_and_alert(sample_with_s1(12.0))
    assert len(sent_emails) == 3


def test_independent_sensor_states():
    """Verify that Sensor 1 and Sensor 2 alert states are completely independent."""
    settings = Settings()
    mgr = EmailAlertManager(settings)
    mgr.update_settings(
        enabled=True,
        recipient_email="student@uiowa.edu",
        min_temperature_c=16.0,
        max_temperature_c=34.0,
    )

    sent_emails = []

    def mock_send(recipient, subject, text, html=None):
        sent_emails.append({"to": recipient, "subject": subject, "text": text})

    mgr.send_email_async = mock_send

    # S1 is HIGH (36°C), S2 is NORMAL (24°C) -> 1 email for S1
    mgr.check_sample_and_alert({
        "ts": int(time.time()),
        "s1": {"ok": True, "c": 36.0},
        "s2": {"ok": True, "c": 24.0},
        "btn1": False,
        "btn2": False,
    })
    assert len(sent_emails) == 1
    assert "Sensor 1" in sent_emails[0]["subject"]
    assert mgr.sensor_states[1] == "HIGH"
    assert mgr.sensor_states[2] == "NORMAL"

    # Next tick: S1 stays HIGH (36°C), S2 becomes LOW (12°C) -> 1 email for S2
    mgr.check_sample_and_alert({
        "ts": int(time.time()),
        "s1": {"ok": True, "c": 36.0},
        "s2": {"ok": True, "c": 12.0},
        "btn1": False,
        "btn2": False,
    })
    assert len(sent_emails) == 2
    assert "Sensor 2" in sent_emails[1]["subject"]
    assert "MINIMUM" in sent_emails[1]["subject"]
    assert mgr.sensor_states[1] == "HIGH"
    assert mgr.sensor_states[2] == "LOW"


def test_unplugged_or_missing_sensors_never_trigger_alerts():
    """Missing or faulty sensor data must never cause temperature alerts."""
    settings = Settings()
    mgr = EmailAlertManager(settings)
    mgr.update_settings(
        enabled=True,
        recipient_email="student@uiowa.edu",
        min_temperature_c=16.0,
        max_temperature_c=34.0,
    )

    sent_emails = []
    mgr.send_email_async = lambda r, s, t, h=None: sent_emails.append(s)

    # Sensor 1 unplugged, Sensor 2 missing error
    mgr.check_sample_and_alert({
        "ts": int(time.time()),
        "s1": {"ok": False, "err": "unplugged"},
        "s2": {"ok": False, "err": "error"},
        "btn1": False,
        "btn2": False,
    })
    assert len(sent_emails) == 0

    # Sensor readings with None
    mgr.check_sample_and_alert({
        "ts": int(time.time()),
        "s1": {"ok": True, "c": None},
        "s2": {"ok": False, "err": "unplugged"},
        "btn1": False,
        "btn2": False,
    })
    assert len(sent_emails) == 0


@patch("smtplib.SMTP")
def test_test_email_endpoint(mock_smtp):
    mock_instance = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_instance

    client = TestClient(app)
    response = client.post(
        "/api/settings/alerts/test",
        json={"recipient_email": "verify@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "verify@example.com" in data["message"]

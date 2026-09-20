"""Unit tests for MQTT topic parsing and command generation."""

from app.config import Settings
from app.mqtt_client import ThermometerMQTTClient
from app.state import ThermometerState


def test_mqtt_temperature_parsing():
    state = ThermometerState()
    settings = Settings(DEV_MODE=True)
    client = ThermometerMQTTClient(state, settings)

    # String float
    client.handle_message("thermometer/sensor/1/temperature", "23.6")
    assert state.sensor1_ok is True
    assert round(state.sensor1_temperature_c, 1) == 23.6

    # JSON float
    client.handle_message("thermometer/sensor/2/temperature", '{"c": 31.2}')
    assert state.sensor2_ok is True
    assert round(state.sensor2_temperature_c, 1) == 31.2


def test_mqtt_status_parsing():
    state = ThermometerState()
    settings = Settings(DEV_MODE=True)
    client = ThermometerMQTTClient(state, settings)

    # Status unplugged
    client.handle_message("thermometer/sensor/1/status", "unplugged")
    assert state.sensor1_ok is False
    assert state.sensor1_error == "unplugged"

    # Status OK
    client.handle_message("thermometer/sensor/1/status", "ok")
    assert state.sensor1_ok is True

    # JSON status
    client.handle_message("thermometer/sensor/2/status", '{"ok": false, "err": "crc_error"}')
    assert state.sensor2_ok is False
    assert state.sensor2_error == "crc_error"


def test_mqtt_button_parsing():
    state = ThermometerState()
    settings = Settings(DEV_MODE=True)
    client = ThermometerMQTTClient(state, settings)

    client.handle_message("thermometer/button/1/state", "1")
    assert state.button1_on is True

    client.handle_message("thermometer/button/1/state", "0")
    assert state.button1_on is False

    client.handle_message("thermometer/button/2/state", '{"on": true}')
    assert state.button2_on is True


def test_publish_button_command_in_dev_mode():
    state = ThermometerState()
    settings = Settings(DEV_MODE=True)
    client = ThermometerMQTTClient(state, settings)

    success = client.publish_button_command(1, True)
    assert success is True
    assert state.button1_on is True


def test_lcd_button_toggles_do_not_affect_temperature_measurement():
    """Verify that turning physical LCD display states ON/OFF leaves temperature readings and errors untouched."""
    state = ThermometerState()
    settings = Settings(DEV_MODE=True)
    client = ThermometerMQTTClient(state, settings)

    # Set initial temperatures
    client.handle_message("thermometer/sensor/1/temperature", "22.5")
    client.handle_message("thermometer/sensor/2/temperature", "31.8")
    assert state.sensor1_temperature_c == 22.5
    assert state.sensor2_temperature_c == 31.8

    # Turn LCD 1 and LCD 2 OFF
    client.handle_message("thermometer/button/1/state", '{"on": false}')
    client.handle_message("thermometer/button/2/state", '{"on": false}')
    assert state.button1_on is False
    assert state.button2_on is False

    # Temperature readings are unchanged
    assert state.sensor1_temperature_c == 22.5
    assert state.sensor2_temperature_c == 31.8

    wire = state.to_wire_format(ts=1756512000)
    assert wire["s1"]["ok"] is True
    assert wire["s1"]["c"] == 22.5
    assert wire["s2"]["ok"] is True
    assert wire["s2"]["c"] == 31.8
    assert wire["btn1"] is False
    assert wire["btn2"] is False



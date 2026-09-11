"""Unit tests for state management and 300-second rolling history."""

import time
from app.state import ThermometerState


def test_initial_state():
    state = ThermometerState()
    assert not state.is_box_online()
    assert state.sensor1_temperature_c is None
    assert state.sensor2_temperature_c is None
    assert not state.sensor1_ok
    assert not state.sensor2_ok
    assert not state.button1_on
    assert not state.button2_on
    assert len(state.get_history()) == 0


def test_state_updates_and_wire_format():
    state = ThermometerState()
    state.update_sensor_temp(1, 22.44)
    state.update_sensor_status(2, False, "unplugged")
    state.update_button_state(1, True)
    state.update_button_state(2, False)

    wire = state.to_wire_format(ts=1756512000)
    assert wire == {
        "ts": 1756512000,
        "s1": {"ok": True, "c": 22.4},
        "s2": {"ok": False, "err": "unplugged"},
        "btn1": True,
        "btn2": False,
    }


def test_invalid_temperature_never_sent_as_0_or_999():
    state = ThermometerState()
    state.update_sensor_temp(1, -999.0)
    wire = state.to_wire_format()
    assert wire["s1"]["ok"] is False
    assert "c" not in wire["s1"] or wire["s1"].get("c") != -999.0


def test_box_offline_detection():
    state = ThermometerState()
    state.mark_message_received(timestamp=time.time() - 4.0)
    assert not state.is_box_online(threshold_seconds=3.0)

    state.mark_message_received(timestamp=time.time())
    assert state.is_box_online(threshold_seconds=3.0)


def test_history_never_exceeds_300_entries():
    state = ThermometerState(history_maxlen=300)
    base_ts = 1756510000

    # Add 450 ticks
    for i in range(450):
        state.update_sensor_temp(1, 20.0 + (i % 10))
        state.record_tick(ts=base_ts + i)

    hist = state.get_history()
    assert len(hist) == 300
    # Oldest in deque should be base_ts + 150
    assert hist[0]["ts"] == base_ts + 150
    # Newest in deque should be base_ts + 449
    assert hist[-1]["ts"] == base_ts + 449


def test_history_is_chronological():
    state = ThermometerState(history_maxlen=300)
    base_ts = 1756510000

    for i in range(50):
        state.update_sensor_temp(1, 22.0)
        state.record_tick(ts=base_ts + i)

    hist = state.get_history()
    assert len(hist) == 50
    for idx in range(len(hist) - 1):
        assert hist[idx]["ts"] < hist[idx + 1]["ts"]
        assert hist[idx + 1]["ts"] == hist[idx]["ts"] + 1


def test_missing_readings_remain_missing_in_history():
    state = ThermometerState(history_maxlen=300)
    ts = 1756510000

    # Box is online, but sensor 2 is unplugged
    state.update_sensor_temp(1, 23.5)
    state.update_sensor_status(2, False, "unplugged")
    sample1 = state.record_tick(ts=ts)
    assert sample1["s1"]["ok"] is True
    assert sample1["s1"]["c"] == 23.5
    assert sample1["s2"]["ok"] is False
    assert sample1["s2"]["err"] == "unplugged"
    assert "c" not in sample1["s2"]

    # Now simulate box going offline for next tick
    state.last_message_time = time.time() - 10.0  # stale
    sample2 = state.record_tick(ts=ts + 1, threshold_seconds=3.0)
    assert sample2["s1"]["ok"] is False
    assert sample2["s2"]["ok"] is False
    assert "c" not in sample2["s1"]
    assert "c" not in sample2["s2"]

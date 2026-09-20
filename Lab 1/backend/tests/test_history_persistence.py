"""Automated tests for 300-second rolling history disk persistence and recovery."""

import json
import os
import time
import pytest
from app.state import ThermometerState


def test_missing_cache_starts_normally_with_empty_history(tmp_path):
    cache_file = tmp_path / "nonexistent_cache.json"
    state = ThermometerState(history_maxlen=300, cache_file_path=str(cache_file))

    assert len(state.get_history()) == 0
    assert not os.path.exists(str(cache_file))


def test_history_is_written_to_disk_atomically(tmp_path):
    cache_file = tmp_path / "history_cache.json"
    state = ThermometerState(history_maxlen=300, cache_file_path=str(cache_file))

    now = int(time.time())
    state.update_sensor_temp(1, 24.5)
    state.update_sensor_temp(2, 33.2)
    sample = state.record_tick(ts=now)

    assert os.path.exists(str(cache_file))
    with open(str(cache_file), "r", encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["ts"] == now
    assert data[0]["s1"]["c"] == 24.5
    assert data[0]["s2"]["c"] == 33.2


def test_history_is_restored_after_creating_new_state(tmp_path):
    cache_file = tmp_path / "history_cache.json"
    state1 = ThermometerState(history_maxlen=300, cache_file_path=str(cache_file))

    now = int(time.time())
    # Record 10 samples within the last 10 seconds
    for i in range(10):
        state1.update_sensor_temp(1, 20.0 + i)
        state1.record_tick(ts=now - (10 - i))

    hist1 = state1.get_history()
    assert len(hist1) == 10

    # Simulate restarting FastAPI by instantiating a brand new ThermometerState
    state2 = ThermometerState(history_maxlen=300, cache_file_path=str(cache_file))
    hist2 = state2.get_history()

    assert len(hist2) == 10
    for s1, s2 in zip(hist1, hist2):
        assert s1["ts"] == s2["ts"]
        assert s1["s1"] == s2["s1"]
        assert s1["s2"] == s2["s2"]


def test_samples_older_than_300_seconds_are_discarded(tmp_path):
    cache_file = tmp_path / "history_cache.json"
    now = int(time.time())

    # Create dummy samples: 5 very old (>300s) and 5 recent (<300s)
    old_samples = [
        {"ts": now - 500 + i, "s1": {"ok": True, "c": 21.0}, "s2": {"ok": True, "c": 31.0}, "btn1": False, "btn2": False}
        for i in range(5)
    ]
    recent_samples = [
        {"ts": now - 50 + i, "s1": {"ok": True, "c": 22.0}, "s2": {"ok": True, "c": 32.0}, "btn1": False, "btn2": False}
        for i in range(5)
    ]

    with open(str(cache_file), "w", encoding="utf-8") as f:
        json.dump(old_samples + recent_samples, f)

    # Instantiate ThermometerState
    state = ThermometerState(history_maxlen=300, cache_file_path=str(cache_file))
    restored = state.get_history()

    # Only recent samples should be loaded
    assert len(restored) == 5
    for s in restored:
        assert now - s["ts"] <= 300
        assert s["s1"]["c"] == 22.0


def test_all_samples_discarded_if_stopped_longer_than_300_seconds(tmp_path):
    cache_file = tmp_path / "history_cache.json"
    now = int(time.time())

    # All samples are > 300s old
    stale_samples = [
        {"ts": now - 400 + i, "s1": {"ok": True, "c": 21.0}, "s2": {"ok": True, "c": 31.0}, "btn1": False, "btn2": False}
        for i in range(20)
    ]

    with open(str(cache_file), "w", encoding="utf-8") as f:
        json.dump(stale_samples, f)

    state = ThermometerState(history_maxlen=300, cache_file_path=str(cache_file))
    restored = state.get_history()

    assert len(restored) == 0


def test_malformed_or_corrupt_cache_does_not_crash_startup(tmp_path):
    cache_file = tmp_path / "corrupt_cache.json"

    # Write corrupt JSON bytes
    with open(str(cache_file), "w", encoding="utf-8") as f:
        f.write("{ invalid json corrupted content !@#$")

    # Should log a warning and start with empty history rather than crashing
    state = ThermometerState(history_maxlen=300, cache_file_path=str(cache_file))
    assert len(state.get_history()) == 0


def test_non_list_cache_does_not_crash_startup(tmp_path):
    cache_file = tmp_path / "dict_cache.json"

    with open(str(cache_file), "w", encoding="utf-8") as f:
        json.dump({"error": "not a list"}, f)

    state = ThermometerState(history_maxlen=300, cache_file_path=str(cache_file))
    assert len(state.get_history()) == 0


def test_no_fake_samples_generated_for_downtime_gap(tmp_path):
    cache_file = tmp_path / "downtime_cache.json"
    now = int(time.time())

    # Backend was running until 40 seconds ago, stopped for 40 seconds, then restarted
    cached = [
        {"ts": now - 70 + i, "s1": {"ok": True, "c": 23.0}, "s2": {"ok": True, "c": 33.0}, "btn1": False, "btn2": False}
        for i in range(30)
    ]
    with open(str(cache_file), "w", encoding="utf-8") as f:
        json.dump(cached, f)

    # Start up
    state = ThermometerState(history_maxlen=300, cache_file_path=str(cache_file))
    restored = state.get_history()

    # The 30 samples exist with their exact historical timestamps
    assert len(restored) == 30
    assert restored[-1]["ts"] == now - 41

    # Record 1 new live tick now
    new_sample = state.record_tick(ts=now)
    all_history = state.get_history()

    assert len(all_history) == 31
    # Check gap: difference between the previous sample and new sample is 41 seconds
    gap = all_history[-1]["ts"] - all_history[-2]["ts"]
    assert gap == 41  # Gap is preserved as a natural time jump, no fake samples invented!


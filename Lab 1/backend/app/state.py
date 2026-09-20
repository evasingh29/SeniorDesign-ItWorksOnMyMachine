"""State and rolling history management for thermometer sensors and buttons."""

import collections
import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("thermometer.state")


class ThermometerState:
    """Thread-safe state and 300-second rolling history manager for digital thermometer."""

    def __init__(
        self,
        history_maxlen: int = 300,
        cache_file_path: Optional[str] = None,
    ):
        self._lock = threading.Lock()
        self.history_maxlen = history_maxlen
        self.cache_file_path = cache_file_path
        self.history: collections.deque[Dict[str, Any]] = collections.deque(
            maxlen=history_maxlen
        )
        self.sensor1_temperature_c: Optional[float] = None
        self.sensor2_temperature_c: Optional[float] = None
        self.sensor1_ok: bool = False
        self.sensor2_ok: bool = False
        self.sensor1_error: Optional[str] = "unplugged"
        self.sensor2_error: Optional[str] = "unplugged"
        self.button1_on: bool = False
        self.button2_on: bool = False
        self.last_message_time: float = 0.0

        if self.cache_file_path:
            self._load_cache()

    def _load_cache(self) -> None:
        """Load and validate cached history from disk, discarding samples older than history_maxlen."""
        if not self.cache_file_path or not os.path.isfile(self.cache_file_path):
            return

        try:
            with open(self.cache_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                logger.warning(
                    f"History cache at {self.cache_file_path} is not a list. Starting with empty history."
                )
                return

            now = time.time()
            valid_samples = []
            for sample in data:
                if not isinstance(sample, dict):
                    continue
                ts = sample.get("ts")
                if not isinstance(ts, (int, float)):
                    continue
                # Keep only samples strictly within the rolling window (e.g. past 300 seconds)
                age = now - ts
                if 0 <= age <= self.history_maxlen or (-5.0 <= age < 0):
                    valid_samples.append(sample)

            valid_samples.sort(key=lambda s: s["ts"])

            with self._lock:
                self.history = collections.deque(
                    valid_samples[-self.history_maxlen:], maxlen=self.history_maxlen
                )
                logger.info(
                    f"Restored {len(self.history)} valid historical samples from cache: {self.cache_file_path}"
                )
        except Exception as e:
            logger.warning(
                f"Failed to load history cache from {self.cache_file_path}: {e}. Starting with empty history."
            )
            with self._lock:
                self.history.clear()

    def _save_cache_unlocked(self) -> None:
        """Persist current history deque to disk using atomic rename."""
        if not self.cache_file_path:
            return

        try:
            cache_dir = os.path.dirname(os.path.abspath(self.cache_file_path))
            os.makedirs(cache_dir, exist_ok=True)

            temp_file = self.cache_file_path + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(list(self.history), f)

            os.replace(temp_file, self.cache_file_path)
        except Exception as e:
            logger.warning(f"Failed to persist history cache to {self.cache_file_path}: {e}")

    def mark_message_received(self, timestamp: Optional[float] = None) -> None:
        """Record the time of the latest message from the hardware."""
        with self._lock:
            self.last_message_time = timestamp or time.time()

    def update_sensor_temp(self, sensor_id: int, temp_c: Optional[float]) -> None:
        """Update temperature reading for a sensor."""
        with self._lock:
            self.last_message_time = time.time()
            if sensor_id == 1:
                # Handle invalid values like 0 or -999 sent as errors
                if temp_c is None or temp_c <= -900:
                    self.sensor1_temperature_c = None
                    self.sensor1_ok = False
                    if not self.sensor1_error:
                        self.sensor1_error = "unplugged"
                else:
                    self.sensor1_temperature_c = temp_c
                    self.sensor1_ok = True
                    self.sensor1_error = None
            elif sensor_id == 2:
                if temp_c is None or temp_c <= -900:
                    self.sensor2_temperature_c = None
                    self.sensor2_ok = False
                    if not self.sensor2_error:
                        self.sensor2_error = "unplugged"
                else:
                    self.sensor2_temperature_c = temp_c
                    self.sensor2_ok = True
                    self.sensor2_error = None

    def update_sensor_status(self, sensor_id: int, ok: bool, err: Optional[str] = None) -> None:
        """Update operational status for a sensor."""
        with self._lock:
            self.last_message_time = time.time()
            if sensor_id == 1:
                self.sensor1_ok = ok
                self.sensor1_error = err if not ok else None
                if not ok:
                    self.sensor1_temperature_c = None
            elif sensor_id == 2:
                self.sensor2_ok = ok
                self.sensor2_error = err if not ok else None
                if not ok:
                    self.sensor2_temperature_c = None

    def update_button_state(self, button_id: int, on: bool) -> None:
        """Update physical button/indicator lamp state."""
        with self._lock:
            self.last_message_time = time.time()
            if button_id == 1:
                self.button1_on = on
            elif button_id == 2:
                self.button2_on = on

    def is_box_online(self, threshold_seconds: float = 3.0) -> bool:
        """Check if messages were received within the staleness window."""
        with self._lock:
            if self.last_message_time <= 0:
                return False
            return (time.time() - self.last_message_time) <= threshold_seconds

    def to_wire_format(self, ts: Optional[int] = None) -> Dict[str, Any]:
        """
        Serialize current live state to the exact JSON wire format:
        {
          "ts": 1756512000,
          "s1": { "ok": true, "c": 22.4 },
          "s2": { "ok": false, "err": "unplugged" },
          "btn1": true,
          "btn2": false
        }
        """
        with self._lock:
            return self._build_sample_unlocked(ts=ts)

    def _build_sample_unlocked(self, ts: Optional[int] = None, box_online: Optional[bool] = None) -> Dict[str, Any]:
        """Internal sample builder while lock is already held."""
        current_ts = ts if ts is not None else int(time.time())
        is_online = box_online if box_online is not None else (
            self.last_message_time > 0 and (time.time() - self.last_message_time) <= 3.0
        )

        if is_online:
            # Format Sensor 1
            if self.sensor1_ok and self.sensor1_temperature_c is not None:
                s1 = {"ok": True, "c": round(self.sensor1_temperature_c, 1)}
            else:
                s1 = {"ok": False, "err": self.sensor1_error or "unplugged"}

            # Format Sensor 2
            if self.sensor2_ok and self.sensor2_temperature_c is not None:
                s2 = {"ok": True, "c": round(self.sensor2_temperature_c, 1)}
            else:
                s2 = {"ok": False, "err": self.sensor2_error or "unplugged"}
        else:
            # Box is offline: record missing/unusable data for each sensor
            s1 = {"ok": False, "err": self.sensor1_error or "unplugged"}
            s2 = {"ok": False, "err": self.sensor2_error or "unplugged"}

        return {
            "ts": current_ts,
            "s1": s1,
            "s2": s2,
            "btn1": self.button1_on,
            "btn2": self.button2_on,
        }

    def record_tick(self, ts: Optional[int] = None, threshold_seconds: float = 3.0) -> Dict[str, Any]:
        """
        Record one second tick into the 300-second rolling history buffer.
        If the box is online, records current reading. If offline, records missing reading.
        Returns the created sample.
        """
        with self._lock:
            current_ts = ts if ts is not None else int(time.time())
            is_online = self.last_message_time > 0 and (time.time() - self.last_message_time) <= threshold_seconds
            sample = self._build_sample_unlocked(ts=current_ts, box_online=is_online)
            self.history.append(sample)
            self._save_cache_unlocked()
            return sample

    def get_history(self) -> List[Dict[str, Any]]:
        """Return a chronological copy of the rolling history buffer (oldest to newest)."""
        with self._lock:
            return list(self.history)

    def clear_history(self) -> None:
        """Clear all historical samples."""
        with self._lock:
            self.history.clear()
            self._save_cache_unlocked()

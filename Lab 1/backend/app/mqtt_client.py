"""MQTT Client for HiveMQ Cloud integration and hardware command publishing."""

import json
import logging
import random
import threading
import time
from typing import Optional

import paho.mqtt.client as mqtt

from .config import Settings
from .state import ThermometerState

logger = logging.getLogger("thermometer.mqtt")


class ThermometerMQTTClient:
    """Manages MQTT connection to HiveMQ Cloud, parses telemetry, and sends commands."""

    def __init__(self, state: ThermometerState, settings: Settings):
        self.state = state
        self.settings = settings
        self._connected = False
        self._client: Optional[mqtt.Client] = None
        self._sim_thread: Optional[threading.Thread] = None
        self._sim_stop_event = threading.Event()

    def is_connected(self) -> bool:
        return self._connected

    def start(self) -> None:
        """Start the MQTT client or development simulation."""
        if self.settings.DEV_MODE:
            logger.info("Starting in DEV_MODE: Launching mock sensor simulator.")
            self._start_simulator()
            return

        self._init_paho_client()

    def stop(self) -> None:
        """Stop MQTT client and background threads."""
        if self.settings.DEV_MODE:
            self._sim_stop_event.set()
            if self._sim_thread and self._sim_thread.is_alive():
                self._sim_thread.join(timeout=2.0)
            logger.info("Mock simulator stopped.")
            return

        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting MQTT client: {e}")
            self._connected = False

    def _init_paho_client(self) -> None:
        """Initialize paho-mqtt client with TLS and credentials."""
        try:
            # Handle paho-mqtt 2.x and 1.x API differences
            if hasattr(mqtt, "CallbackAPIVersion"):
                self._client = mqtt.Client(
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                    client_id=self.settings.MQTT_CLIENT_ID,
                )
            else:
                self._client = mqtt.Client(client_id=self.settings.MQTT_CLIENT_ID)

            if self.settings.HIVEMQ_USERNAME and self.settings.HIVEMQ_PASSWORD:
                self._client.username_pw_set(
                    self.settings.HIVEMQ_USERNAME, self.settings.HIVEMQ_PASSWORD
                )

            if self.settings.HIVEMQ_TLS:
                self._client.tls_set()

            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_message = self._on_message

            logger.info(
                f"Connecting to HiveMQ broker at {self.settings.HIVEMQ_BROKER}:{self.settings.HIVEMQ_PORT}..."
            )
            self._client.connect_async(
                self.settings.HIVEMQ_BROKER,
                self.settings.HIVEMQ_PORT,
                keepalive=60,
            )
            self._client.loop_start()
        except Exception as e:
            logger.error(f"Failed to initialize MQTT connection: {e}")
            self._connected = False

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self._connected = True
            logger.info("Successfully connected to HiveMQ MQTT Broker.")
            # Subscribe to topics
            subscriptions = [
                (self.settings.TOPIC_SENSOR_1_TEMP, 0),
                (self.settings.TOPIC_SENSOR_2_TEMP, 0),
                (self.settings.TOPIC_SENSOR_1_STATUS, 0),
                (self.settings.TOPIC_SENSOR_2_STATUS, 0),
                (self.settings.TOPIC_BUTTON_1_STATE, 0),
                (self.settings.TOPIC_BUTTON_2_STATE, 0),
                ("thermometer/sensor/+/+", 0),
                ("thermometer/button/+/+", 0),
            ]
            for topic, qos in subscriptions:
                client.subscribe(topic, qos=qos)
                logger.debug(f"Subscribed to MQTT topic: {topic}")
        else:
            self._connected = False
            logger.error(f"Failed to connect to MQTT broker with result code: {rc}")

    def _on_disconnect(self, client, userdata, rc, properties=None):
        self._connected = False
        logger.warning(f"Disconnected from HiveMQ MQTT Broker (code: {rc}).")

    def _on_message(self, client, userdata, msg):
        """Parse incoming MQTT telemetry messages and update application state."""
        try:
            topic = msg.topic
            payload_str = msg.payload.decode("utf-8").strip()
            self.handle_message(topic, payload_str)
        except Exception as e:
            logger.error(f"Error handling message on topic {msg.topic}: {e}")

    def handle_message(self, topic: str, payload_str: str) -> None:
        """Process decoded MQTT topic and payload."""
        logger.debug(f"MQTT Rx: {topic} -> {payload_str}")

        # Sensor 1 Temperature
        if topic == self.settings.TOPIC_SENSOR_1_TEMP or topic.endswith("sensor/1/temperature"):
            temp = self._parse_temperature(payload_str)
            self.state.update_sensor_temp(1, temp)

        # Sensor 2 Temperature
        elif topic == self.settings.TOPIC_SENSOR_2_TEMP or topic.endswith("sensor/2/temperature"):
            temp = self._parse_temperature(payload_str)
            self.state.update_sensor_temp(2, temp)

        # Sensor 1 Status
        elif topic == self.settings.TOPIC_SENSOR_1_STATUS or topic.endswith("sensor/1/status"):
            ok, err = self._parse_status(payload_str)
            self.state.update_sensor_status(1, ok, err)

        # Sensor 2 Status
        elif topic == self.settings.TOPIC_SENSOR_2_STATUS or topic.endswith("sensor/2/status"):
            ok, err = self._parse_status(payload_str)
            self.state.update_sensor_status(2, ok, err)

        # Button 1 State
        elif topic == self.settings.TOPIC_BUTTON_1_STATE or topic.endswith("button/1/state"):
            on = self._parse_button(payload_str)
            self.state.update_button_state(1, on)

        # Button 2 State
        elif topic == self.settings.TOPIC_BUTTON_2_STATE or topic.endswith("button/2/state"):
            on = self._parse_button(payload_str)
            self.state.update_button_state(2, on)

        else:
            # Generic message from box
            self.state.mark_message_received()

    def _parse_temperature(self, payload: str) -> Optional[float]:
        """Extract float temperature in Celsius from string or JSON."""
        try:
            # Try JSON first
            if payload.startswith("{"):
                data = json.loads(payload)
                if isinstance(data, dict):
                    # Check for ok flag
                    if data.get("ok") is False:
                        return None
                    for key in ("c", "temp", "temperature", "value"):
                        if key in data and data[key] is not None:
                            val = float(data[key])
                            return val if val > -900 else None
                return None
            
            # Plain numeric string
            val = float(payload)
            return val if val > -900 else None
        except (ValueError, TypeError, json.JSONDecodeError):
            return None

    def _parse_status(self, payload: str) -> tuple[bool, Optional[str]]:
        """Extract status (ok, err) from string or JSON."""
        try:
            if payload.startswith("{"):
                data = json.loads(payload)
                if isinstance(data, dict):
                    ok = bool(data.get("ok", True))
                    err = data.get("err") or ("unplugged" if not ok else None)
                    return ok, err

            lower = payload.lower()
            if lower in ("ok", "ready", "online", "connected", "1", "true"):
                return True, None
            elif lower in ("unplugged", "disconnected", "missing"):
                return False, "unplugged"
            else:
                return False, payload or "error"
        except Exception:
            return False, "error"

    def _parse_button(self, payload: str) -> bool:
        """Extract boolean button state from string or JSON."""
        try:
            if payload.startswith("{"):
                data = json.loads(payload)
                if isinstance(data, dict):
                    if "on" in data:
                        return bool(data["on"])
                    if "state" in data:
                        return bool(data["state"])
            lower = payload.lower()
            return lower in ("1", "true", "on", "pressed", "high")
        except Exception:
            return False

    def publish_button_command(self, button_id: int, on: bool) -> bool:
        """Publish a command to virtual press/toggle physical button on ESP32."""
        topic = (
            self.settings.TOPIC_COMMAND_BUTTON_1
            if button_id == 1
            else self.settings.TOPIC_COMMAND_BUTTON_2
        )
        payload = json.dumps({"on": on})

        if self.settings.DEV_MODE:
            logger.info(f"[DEV_MODE] Mock published command to {topic}: {payload}")
            # In dev mode, immediately reflect state
            self.state.update_button_state(button_id, on)
            return True

        if not self._client or not self._connected:
            logger.warning("Cannot publish command: MQTT client is not connected.")
            return False

        try:
            info = self._client.publish(topic, payload, qos=1)
            info.wait_for_publish(timeout=1.0)
            logger.info(f"Published command to {topic}: {payload}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish command to {topic}: {e}")
            return False

    # --------------------------------------------------------------------------
    # Simulator for Development Mode
    # --------------------------------------------------------------------------
    def _start_simulator(self) -> None:
        """Run a simulation loop generating temperature drift and dropouts."""
        self._connected = True

        def sim_loop():
            s1_center, s1_val = 24.0, 23.2
            s2_center, s2_val = 33.0, 34.1
            btn1, btn2 = False, False
            s1_dropout_left = 0
            s2_dropout_left = 0

            # Pre-initialize state
            self.state.update_sensor_temp(1, s1_val)
            self.state.update_sensor_temp(2, s2_val)

            while not self._sim_stop_event.is_set():
                # Random walk with mean reversion
                s1_val += (random.random() - 0.5) * 0.44 + (s1_center - s1_val) * 0.0015
                s2_val += (random.random() - 0.5) * 0.44 + (s2_center - s2_val) * 0.0015

                # Sensor 1 dropout simulation
                if s1_dropout_left > 0:
                    s1_dropout_left -= 1
                    self.state.update_sensor_status(1, False, "unplugged")
                elif random.random() < (1.0 / 300.0):
                    s1_dropout_left = random.randint(4, 8)
                    self.state.update_sensor_status(1, False, "unplugged")
                else:
                    jitter = (random.random() - 0.5) * 0.24
                    self.state.update_sensor_temp(1, round(s1_val + jitter, 1))

                # Sensor 2 dropout simulation
                if s2_dropout_left > 0:
                    s2_dropout_left -= 1
                    self.state.update_sensor_status(2, False, "unplugged")
                elif random.random() < (1.0 / 300.0):
                    s2_dropout_left = random.randint(4, 8)
                    self.state.update_sensor_status(2, False, "unplugged")
                else:
                    jitter = (random.random() - 0.5) * 0.24
                    self.state.update_sensor_temp(2, round(s2_val + jitter, 1))

                # Occasional button toggle simulation
                if random.random() < 0.02:
                    btn1 = not btn1
                    self.state.update_button_state(1, btn1)
                if random.random() < 0.02:
                    btn2 = not btn2
                    self.state.update_button_state(2, btn2)

                self.state.mark_message_received()
                time.sleep(1.0)

        self._sim_thread = threading.Thread(target=sim_loop, daemon=True)
        self._sim_thread.start()


"""Configuration settings for ECE:4880 Thermometer FastAPI Backend."""

from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # --------------------------------------------------------------------------
    # DS18B20 Hardware Sensor Addresses
    # --------------------------------------------------------------------------
    # Sensor 1 ROM address
    SENSOR_1_ADDRESS: str = Field(
        default="28-31-F5-A8-11-00-00-E4",
        description="DS18B20 64-bit ROM Hardware Address for Sensor 1"
    )
    # Sensor 2 ROM address
    SENSOR_2_ADDRESS: str = Field(
        default="28-E4-C4-EB-10-00-00-1A",
        description="DS18B20 64-bit ROM Hardware Address for Sensor 2"
    )

    # --------------------------------------------------------------------------
    # HiveMQ Cloud MQTT Broker Settings
    # --------------------------------------------------------------------------
    HIVEMQ_BROKER: str = Field(
        default="localhost",
        description="HiveMQ Cloud broker host"
    )
    HIVEMQ_PORT: int = Field(
        default=8883,
        description="HiveMQ Cloud broker port (8883 for TLS/SSL, 1883 for plaintext)"
    )
    HIVEMQ_USERNAME: Optional[str] = Field(
        default=None,
        description="HiveMQ username"
    )
    HIVEMQ_PASSWORD: Optional[str] = Field(
        default=None,
        description="HiveMQ password"
    )
    HIVEMQ_TLS: bool = Field(
        default=True,
        description="Enable TLS/SSL connection to MQTT broker"
    )
    MQTT_CLIENT_ID: str = Field(
        default="fastapi-thermometer-backend",
        description="MQTT client identifier"
    )

    # --------------------------------------------------------------------------
    # MQTT Topics
    # --------------------------------------------------------------------------
    TOPIC_SENSOR_1_TEMP: str = "thermometer/sensor/1/temperature"
    TOPIC_SENSOR_2_TEMP: str = "thermometer/sensor/2/temperature"
    TOPIC_SENSOR_1_STATUS: str = "thermometer/sensor/1/status"
    TOPIC_SENSOR_2_STATUS: str = "thermometer/sensor/2/status"
    TOPIC_BUTTON_1_STATE: str = "thermometer/button/1/state"
    TOPIC_BUTTON_2_STATE: str = "thermometer/button/2/state"
    TOPIC_COMMAND_BUTTON_1: str = "thermometer/command/button/1"
    TOPIC_COMMAND_BUTTON_2: str = "thermometer/command/button/2"

    # --------------------------------------------------------------------------
    # Server & Timing Parameters
    # --------------------------------------------------------------------------
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Timeout after which the hardware box is considered offline (seconds)
    STALE_THRESHOLD_SECONDS: float = 3.0

    # Rate at which WebSocket updates are broadcast (Hz/seconds)
    BROADCAST_INTERVAL_SECONDS: float = 1.0

    # Development simulation mode (generates mock MQTT data locally)
    DEV_MODE: bool = False

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()


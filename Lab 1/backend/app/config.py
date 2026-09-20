from pathlib import Path
from typing import List, Optional
import uuid
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(BASE_DIR / ".env"),
            str(REPO_ROOT / ".env"),
            ".env",
        ),
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
        default="28-F4-C4-EB-10-00-00-1A",
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
        default_factory=lambda: f"fastapi-thermometer-{uuid.uuid4().hex[:8]}",
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

    # Local file path for persisting 300-second rolling history across restarts
    HISTORY_CACHE_FILE: str = Field(
        default=str(BASE_DIR / "data" / "history_cache.json"),
        alias="history_cache_file",
        description="File path for persisting the 300-second rolling temperature history"
    )

    # Development simulation mode (generates mock MQTT data locally)
    DEV_MODE: bool = False

    # --------------------------------------------------------------------------
    # Gmail SMTP & Email Alerts Settings
    # --------------------------------------------------------------------------
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_SENDER: str = "itworksonmymachine.sd@gmail.com"
    APP_PASSWORD: Optional[str] = Field(
        default=None,
        alias="app_password",
        description="Gmail App Password from .env"
    )
    ALERT_RECIPIENT_EMAIL: str = Field(
        default="",
        alias="alert_recipient_email",
        description="Default recipient email address for temperature alerts"
    )
    ALERT_MIN_TEMP_C: Optional[float] = Field(
        default=15.0,
        alias="alert_min_temp_c",
        description="Default minimum temperature threshold in °C"
    )
    ALERT_MAX_TEMP_C: Optional[float] = Field(
        default=35.0,
        alias="alert_max_temp_c",
        description="Default maximum temperature threshold in °C"
    )
    ALERT_LOW_MESSAGE: str = Field(
        default="Temperature has fallen below the minimum!",
        alias="alert_low_message",
        description="Custom message for low temperature alert"
    )
    ALERT_HIGH_MESSAGE: str = Field(
        default="Temperature has exceeded the maximum!",
        alias="alert_high_message",
        description="Custom message for high temperature alert"
    )
    ALERT_ENABLED: bool = Field(
        default=True,
        alias="alert_enabled",
        description="Whether email alerts are enabled on startup"
    )
    ALERT_COOLDOWN_SECONDS: int = Field(
        default=60,
        alias="alert_cooldown_seconds",
        description="Cooldown duration in seconds between consecutive alert emails"
    )

    @property
    def cleaned_app_password(self) -> str:
        """Return app password stripped of whitespace and quotes."""
        if not self.APP_PASSWORD:
            return ""
        return self.APP_PASSWORD.strip().replace(" ", "").replace('"', "").replace("'", "")

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()



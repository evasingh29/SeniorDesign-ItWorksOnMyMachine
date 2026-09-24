"""FastAPI Application for Digital Thermometer Lab 1."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .alerts import EmailAlertManager
from .config import settings
from .mqtt_client import ThermometerMQTTClient
from .state import ThermometerState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("thermometer.app")

# Shared state, MQTT service, and Alert Manager instances
thermometer_state = ThermometerState(
    history_maxlen=300,
    cache_file_path=settings.HISTORY_CACHE_FILE,
)
mqtt_service = ThermometerMQTTClient(thermometer_state, settings)
alert_manager = EmailAlertManager(settings)


class ConnectionManager:
    """Manages active WebSocket connections from React frontend clients."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, data: dict) -> None:
        """Send data to all connected clients, pruning stale connections."""
        if not self.active_connections:
            return

        dead_connections = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(data)
            except Exception:
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead)


manager = ConnectionManager()


async def broadcast_loop():
    logger.info("Starting WebSocket broadcast worker & rolling history recorder (1 Hz).")
    while True:
        try:
            # Record a tick in the 300-second rolling history
            sample = thermometer_state.record_tick(
                threshold_seconds=settings.STALE_THRESHOLD_SECONDS
            )

            # Check temperature thresholds and trigger email alerts if configured
            alert_manager.check_sample_and_alert(sample)

            # Check if the thermometer box is online before broadcasting live frame
            if thermometer_state.is_box_online(
                threshold_seconds=settings.STALE_THRESHOLD_SECONDS
            ):
                await manager.broadcast(sample)
            else:
                # When box is offline, pause live broadcasts so frontend's staleness
                # timer triggers BOX OFFLINE.
                pass
        except Exception as e:
            logger.error(f"Error in broadcast loop: {e}")

        await asyncio.sleep(settings.BROADCAST_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing Thermometer Backend...")
    mqtt_service.start()
    broadcast_task = asyncio.create_task(broadcast_loop())
    yield
    # Shutdown
    logger.info("Shutting down Thermometer Backend...")
    broadcast_task.cancel()
    try:
        await broadcast_task
    except asyncio.CancelledError:
        pass
    mqtt_service.stop()


app = FastAPI(
    title="ECE:4880 Digital Thermometer Backend",
    description="FastAPI WebSocket and REST gateway with 300s rolling history and Gmail alerts between HiveMQ MQTT and React frontend.",
    version="1.2.0",
    lifespan=lifespan,
)

# Enable CORS for Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------------------
# Request / Response Schemas
# ------------------------------------------------------------------------------
class ButtonCommandRequest(BaseModel):
    on: bool = Field(..., description="Desired button state (True = ON/Pressed, False = OFF/Released)")


class ButtonCommandResponse(BaseModel):
    ok: bool
    button_id: int
    on: bool
    message: str


class AlertSettingsUpdateRequest(BaseModel):
    enabled: Optional[bool] = Field(default=None, description="Enable or disable automated email alerts")
    recipient_email: Optional[str] = Field(default=None, description="Recipient email address for alerts")
    min_temperature_c: Optional[float] = Field(default=None, description="Minimum temperature threshold in °C")
    max_temperature_c: Optional[float] = Field(default=None, description="Maximum temperature threshold in °C")
    low_message: Optional[str] = Field(default=None, description="Custom message for low temperature alert")
    high_message: Optional[str] = Field(default=None, description="Custom message for high temperature alert")
    cooldown_seconds: Optional[int] = Field(default=None, description="Cooldown seconds between consecutive alerts")


class AlertSettingsResponse(BaseModel):
    enabled: bool
    recipient_email: str
    min_temperature_c: Optional[float]
    max_temperature_c: Optional[float]
    low_message: str
    high_message: str
    cooldown_seconds: int
    smtp_sender: str
    smtp_configured: bool


class TestEmailRequest(BaseModel):
    recipient_email: Optional[str] = Field(default=None, description="Optional target recipient email for testing")


class TestEmailResponse(BaseModel):
    ok: bool
    message: str


class HealthResponse(BaseModel):
    status: str
    box_online: bool
    mqtt_connected: bool
    dev_mode: bool
    clients_connected: int
    history_samples: int
    alerts_enabled: bool
    alert_recipient: str
    sensor_addresses: dict


class HistoryResponse(BaseModel):
    history: List[Dict[str, Any]]
    count: int


# ------------------------------------------------------------------------------
# REST Endpoints
# ------------------------------------------------------------------------------
@app.get("/")
def root():
    """Root landing endpoint with quick links."""
    return {
        "service": "ECE:4880 Digital Thermometer Backend",
        "docs": "/docs",
        "health": "/health",
        "history": "/api/history",
        "alerts_settings": "/api/settings/alerts",
        "websocket": "ws://localhost:8000/ws",
    }


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Health status check endpoint."""
    alert_cfg = alert_manager.get_settings()
    return HealthResponse(
        status="ok",
        box_online=thermometer_state.is_box_online(
            threshold_seconds=settings.STALE_THRESHOLD_SECONDS
        ),
        mqtt_connected=mqtt_service.is_connected(),
        dev_mode=settings.DEV_MODE,
        clients_connected=len(manager.active_connections),
        history_samples=len(thermometer_state.get_history()),
        alerts_enabled=alert_cfg["enabled"],
        alert_recipient=alert_cfg["recipient_email"],
        sensor_addresses={
            "s1": settings.SENSOR_1_ADDRESS,
            "s2": settings.SENSOR_2_ADDRESS,
        },
    )


@app.get("/api/history", response_model=HistoryResponse)
def get_rolling_history():
    """Retrieve the rolling 300-second history buffer."""
    hist = thermometer_state.get_history()
    return HistoryResponse(history=hist, count=len(hist))


@app.get("/api/settings/alerts", response_model=AlertSettingsResponse)
@app.get("/api/alerts/settings", response_model=AlertSettingsResponse, include_in_schema=False)
def get_alert_settings():
    """Retrieve current email alert settings and threshold configurations."""
    return AlertSettingsResponse(**alert_manager.get_settings())


@app.post("/api/settings/alerts", response_model=AlertSettingsResponse)
@app.put("/api/settings/alerts", response_model=AlertSettingsResponse, include_in_schema=False)
@app.post("/api/alerts/settings", response_model=AlertSettingsResponse, include_in_schema=False)
def update_alert_settings(payload: AlertSettingsUpdateRequest):
    """Update email alert thresholds, recipient, and enabled state."""
    updated = alert_manager.update_settings(
        enabled=payload.enabled,
        recipient_email=payload.recipient_email,
        min_temperature_c=payload.min_temperature_c,
        max_temperature_c=payload.max_temperature_c,
        low_message=payload.low_message,
        high_message=payload.high_message,
        cooldown_seconds=payload.cooldown_seconds,
    )
    return AlertSettingsResponse(**updated)


@app.post("/api/settings/alerts/test", response_model=TestEmailResponse)
@app.post("/api/alerts/test", response_model=TestEmailResponse, include_in_schema=False)
def test_alert_email(payload: Optional[TestEmailRequest] = None):
    """
    Send an immediate test email to verify Gmail SMTP credentials and recipient delivery.
    """
    target = payload.recipient_email if payload else None
    success, msg = alert_manager.send_test_email(to_email=target)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=msg,
        )
    return TestEmailResponse(ok=True, message=msg)


@app.post("/api/buttons/{button_id}", response_model=ButtonCommandResponse)
def control_button(button_id: int, command: ButtonCommandRequest):
    """
    Virtually trigger physical button state on the ESP32 box by publishing
    an MQTT command message.
    """
    if button_id not in (1, 2):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid button_id {button_id}. Must be 1 or 2.",
        )

    success = mqtt_service.publish_button_command(button_id, command.on)
    if not success and not settings.DEV_MODE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MQTT broker is not connected. Command could not be delivered.",
        )

    return ButtonCommandResponse(
        ok=True,
        button_id=button_id,
        on=command.on,
        message=f"Button {button_id} command published successfully.",
    )


# ------------------------------------------------------------------------------
# WebSocket Endpoint
# ------------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time thermometer streaming to React frontends.
    Immediately sends up to 300 seconds of available rolling history as an array,
    then continues with 1 Hz individual sample broadcasts.
    """
    await manager.connect(websocket)
    try:
        # Deliver available rolling history immediately upon connection
        history = thermometer_state.get_history()
        if history:
            await websocket.send_json(history)

        # Keep connection open and listen for disconnection
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket client error: {e}")
        manager.disconnect(websocket)

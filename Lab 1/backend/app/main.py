"""FastAPI Application for Digital Thermometer Lab 1."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import settings
from .mqtt_client import ThermometerMQTTClient
from .state import ThermometerState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("thermometer.app")

# Shared state and MQTT service instances
thermometer_state = ThermometerState(history_maxlen=300)
mqtt_service = ThermometerMQTTClient(thermometer_state, settings)


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
    """
    Background worker running at 1 Hz that:
    1. Records a 1-second sample into the 300-sample rolling history buffer.
    2. Broadcasts the live sample to connected WebSocket clients if box is online.
    """
    logger.info("Starting WebSocket broadcast worker & rolling history recorder (1 Hz).")
    while True:
        try:
            # Record a tick in the 300-second rolling history
            sample = thermometer_state.record_tick(
                threshold_seconds=settings.STALE_THRESHOLD_SECONDS
            )

            # Check if the thermometer box is online before broadcasting live frame
            if thermometer_state.is_box_online(
                threshold_seconds=settings.STALE_THRESHOLD_SECONDS
            ):
                await manager.broadcast(sample)
            else:
                # When box is offline, we pause live broadcasts so frontend's 3-second
                # timeout flips to "BOX OFFLINE" cleanly.
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
    description="FastAPI WebSocket and REST gateway with 300s rolling history between HiveMQ MQTT and React frontend.",
    version="1.1.0",
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


class HealthResponse(BaseModel):
    status: str
    box_online: bool
    mqtt_connected: bool
    dev_mode: bool
    clients_connected: int
    history_samples: int
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
        "websocket": "ws://localhost:8000/ws",
    }


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Health status check endpoint."""
    return HealthResponse(
        status="ok",
        box_online=thermometer_state.is_box_online(
            threshold_seconds=settings.STALE_THRESHOLD_SECONDS
        ),
        mqtt_connected=mqtt_service.is_connected(),
        dev_mode=settings.DEV_MODE,
        clients_connected=len(manager.active_connections),
        history_samples=len(thermometer_state.get_history()),
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

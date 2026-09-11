# Lab 1 — Digital Thermometer Backend (FastAPI & MQTT)

ECE:4880 Senior Design. Gateway service connecting ESP32 temperature box telemetry (via HiveMQ Cloud MQTT broker) to the React web frontend over WebSockets.

---

## Architecture Overview

```
ESP32 Box (Dual DS18B20 + Pushbuttons)
      │
      ▼  MQTT over TLS (port 8883)
HiveMQ Cloud Broker
      │
      ▼  paho-mqtt
FastAPI Backend (Gateway & State Manager)
      │
      ▼  WebSocket (ws://localhost:8000/ws @ 1 Hz)
React Web Frontend (Vite)
```

1. The **ESP32** reads dual DS18B20 temperature probes and button states, publishing readings to HiveMQ Cloud.
2. The **FastAPI backend** maintains an in-memory thread-safe state, tracks box staleness/offline detection, and streams updates at 1 Hz via WebSocket to connected browser clients.
3. The **React frontend** subscribes to `ws://localhost:8000/ws` and renders real-time scrolling strip charts, stats, and button lamps.

---

## Hardware Sensor Addresses

Documented 64-bit ROM addresses for the two Dallas DS18B20 1-Wire temperature sensors:

| Sensor | ROM Hardware Address | Default Color |
|---|---|---|
| **Sensor 1** (`s1`) | `28-31-F5-A8-11-00-00-E4` | Red (`#d62828`) |
| **Sensor 2** (`s2`) | `28-E4-C4-EB-10-00-00-1A` | Blue (`#1d61c4`) |

---

## MQTT Topic Definitions

| Topic | Direction | Description | Example Payload |
|---|---|---|---|
| `thermometer/sensor/1/temperature` | ESP32 → Backend | Sensor 1 temperature in °C | `22.4` or `{"c": 22.4}` |
| `thermometer/sensor/2/temperature` | ESP32 → Backend | Sensor 2 temperature in °C | `31.8` or `{"c": 31.8}` |
| `thermometer/sensor/1/status` | ESP32 → Backend | Sensor 1 operational status | `"ok"`, `"unplugged"`, `{"ok": false, "err": "unplugged"}` |
| `thermometer/sensor/2/status` | ESP32 → Backend | Sensor 2 operational status | `"ok"`, `"unplugged"` |
| `thermometer/button/1/state` | ESP32 → Backend | Button 1 state | `true`, `false`, `1`, `0` |
| `thermometer/button/2/state` | ESP32 → Backend | Button 2 state | `true`, `false`, `1`, `0` |
| `thermometer/command/button/1` | Backend → ESP32 | Virtual button 1 toggle command | `{"on": true}` |
| `thermometer/command/button/2` | Backend → ESP32 | Virtual button 2 toggle command | `{"on": false}` |

---

## WebSocket Wire Format Contract

Broadcast to `ws://localhost:8000/ws` once per second:

```json
{
  "ts": 1756512000,
  "s1": { "ok": true, "c": 22.4 },
  "s2": { "ok": false, "err": "unplugged" },
  "btn1": true,
  "btn2": false
}
```

- **Temperature Units**: All readings are stored and transmitted in **Celsius**. The frontend converts to Fahrenheit for display when requested.
- **Sensor Faults**: Coerced to `{"ok": false, "err": "unplugged"}` or `{"ok": false, "err": "error"}`. `0` or `-999` are never sent for missing data.
- **Offline Detection**: If the ESP32 stops publishing for >3.0 seconds, the backend halts broadcast frames, prompting the frontend to indicate `BOX OFFLINE` within ~3 seconds.

---

## API Endpoints

### 1. `GET /health`
Returns backend health status, MQTT connection state, box online status, and rolling history sample count.

### 2. `GET /api/history`
Returns the current rolling history buffer (up to 300 seconds) in chronological order.

### 3. `POST /api/buttons/1` and `POST /api/buttons/2`
Virtually presses or releases a hardware button by publishing an MQTT command to the ESP32.

**Request Body:**
```json
{
  "on": true
}
```

### 4. `WS /ws`
WebSocket endpoint for real-time telemetry. Immediately transmits the rolling 300-second history array upon connection, then streams continuous 1 Hz live sample updates.

---

## Setup & Running

### Prerequisites
- Python 3.10+

### Installation

1. Navigate to the backend directory:
   ```bash
   cd "Lab 1/backend"
   ```

2. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

3. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your HiveMQ Cloud credentials or set DEV_MODE=true
   ```

5. Run the FastAPI development server:
   ```bash
   uvicorn app.main:app --reload
   ```

The backend will be available at [http://localhost:8000](http://localhost:8000) with interactive Swagger documentation at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## Development / Simulator Mode

If you don't have a live ESP32 or HiveMQ broker connected yet, enable local simulation in `.env`:

```ini
DEV_MODE=true
```

Or pass it as an environment variable when starting:

```bash
DEV_MODE=true uvicorn app.main:app --reload
```

In `DEV_MODE`, the backend generates realistic temperature drift (random walk), occasional dropout scenarios, and responds to virtual button commands automatically.

---

## Connecting the React Frontend

In `Lab 1/frontend/web/.env.local`:

```ini
VITE_WS_URL=ws://localhost:8000/ws
```

Run the frontend:

```bash
cd "Lab 1/frontend/web"
npm install
npm run dev
```


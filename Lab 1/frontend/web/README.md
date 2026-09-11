# Lab 1 — Digital Thermometer, browser front end

ECE:4880 Senior Design. Scrolling two-sensor temperature display for the
ESP32 thermometer box.

Today this runs entirely on a **simulated feed**. No WebSocket connection and
no settings panel yet — both are deliberately out of scope for this milestone.

## Run it

```bash
npm install
npm run dev
```

Then open the URL Vite prints (default <http://localhost:5173>).

## Requirements traceability

Each numbered requirement from the lab handout, and the file that implements it.

| # | Requirement | Implemented in |
|---|---|---|
| 1 | Y axis pinned to 10–50 °C, never auto-scaling | [`src/components/TemperatureChart.jsx`](src/components/TemperatureChart.jsx) — `scales.y.range` is a function returning the constants verbatim, ignoring the data. Bounds live in [`src/lib/constants.js`](src/lib/constants.js) (`Y_MIN_C`, `Y_MAX_C`). |
| 2 | X axis shows 300 s of history, labeled "seconds ago", reading 300 → 0 left to right | [`src/components/TemperatureChart.jsx`](src/components/TemperatureChart.jsx) — fixed `X_AGES` domain `[0, 299]` with `dir: -1`; axis label and `splits` set there. Window size is `HISTORY_SECONDS` in [`src/lib/constants.js`](src/lib/constants.js). |
| 3 | New data enters at the right once per second; graph scrolls right to left | [`src/data/dummySource.js`](src/data/dummySource.js) emits at 1 Hz; [`src/lib/ringBuffer.js`](src/lib/ringBuffer.js) appends and drops the oldest; the chart plots by *age*, so each append shifts every point one step left. |
| 4 | Two sensors, two visually distinguishable traces | [`src/lib/constants.js`](src/lib/constants.js) — `SENSOR_COLORS`, red `#d62828` / blue `#1d61c4` (dual-pen chart recorder). Applied in [`src/components/TemperatureChart.jsx`](src/components/TemperatureChart.jsx) and echoed on the readouts in [`src/components/SensorReadout.jsx`](src/components/SensorReadout.jsx). |
| 5 | Missing data distinguishable from off-scale data; stored as `null`, gaps shaded, never 0 or −999 | Storage: [`src/lib/ringBuffer.js`](src/lib/ringBuffer.js) and [`src/lib/useThermometer.js`](src/lib/useThermometer.js) coerce any unusable reading to `null`. Rendering: `spanGaps: false` breaks the trace and `gapShadingPlugin` in [`src/components/TemperatureChart.jsx`](src/components/TemperatureChart.jsx) hatches every null run in that sensor's pen color. Legend entry in [`src/App.jsx`](src/App.jsx). |

### Architecture decisions

| Decision | Where it is enforced |
|---|---|
| Celsius everywhere; convert to °F at display time only, in one place | [`src/lib/temperature.js`](src/lib/temperature.js) is the only file that knows about Fahrenheit. The chart's y scale stays Celsius; only tick *labels* convert. |
| Ring buffer fixed at 300 entries, oldest dropped, never grows | [`src/lib/ringBuffer.js`](src/lib/ringBuffer.js) — capacity is set once and enforced on every push. |
| Browser talks only to the Python backend over a WebSocket; never MQTT directly | [`src/data/wsSource.js`](src/data/wsSource.js) is the only network client, and it speaks plain WebSocket. |
| "Box offline" is the absence of messages, not a payload field | [`src/lib/useThermometer.js`](src/lib/useThermometer.js) — a staleness timer compares against `STALE_AFTER_MS`. Displayed by [`src/components/StatusBar.jsx`](src/components/StatusBar.jsx). |

## Swapping the dummy feed for the real one

This is a **one-file change**, by design.

A data source is any object with a single method:

```js
subscribe(onSample) -> unsubscribe()
```

`onSample` receives one message in the backend's wire format:

```json
{
  "ts": 1756512000,
  "s1": { "ok": true,  "c": 22.4 },
  "s2": { "ok": false, "err": "unplugged" },
  "btn1": true,
  "btn2": false
}
```

[`src/data/source.js`](src/data/source.js) picks the implementation from the
`VITE_WS_URL` env var. Set it and the app uses the live backend; leave it unset
and it uses the simulator:

```bash
# web/.env.local
VITE_WS_URL=ws://localhost:8000/ws
```

No component imports either source directly, so nothing else changes. The
WebSocket client in [`src/data/wsSource.js`](src/data/wsSource.js) is already
written against this interface (with reconnect), it is simply unused until the
backend exists.

Note the live source does **not** pre-fill history, while the simulator does.
That is intentional: a chart recorder has no trace for time it was not running,
and inventing one would mean drawing readings that were never taken.

## Simulated data

A slow random walk (the underlying temperature drifting) plus independent
per-sample noise (sensor jitter) — not a sine wave, which reads as obviously
synthetic. Tuning constants are at the top of
[`src/data/dummySource.js`](src/data/dummySource.js).

The 300-entry buffer is **pre-filled on load** with backdated samples, so the
graph is full immediately instead of drawing in over five minutes.

Each sensor also drops out occasionally so the gap-shading path is visible
during the demo. The rate is tuned to roughly **one gap per sensor per
300-second screen**, so some loads will show no gap at all. To force gaps for a
demo, raise `DROPOUT_CHANCE` in
[`src/data/dummySource.js`](src/data/dummySource.js) (e.g. `1 / 40`).

## Layout

```
src/
  data/
    source.js        the seam: chooses a source from VITE_WS_URL
    dummySource.js   simulated feed (today's default)
    wsSource.js      live backend feed (written, not yet used)
  lib/
    constants.js     300 s window, 10-50 °C bounds, pen colors, stale timeout
    ringBuffer.js    fixed 300-entry buffer, nulls for missing readings
    temperature.js   the only place °C becomes °F
    useThermometer.js  subscribes a source to the buffer, detects staleness
  components/
    TemperatureChart.jsx  uPlot instance + gap-shading plugin
    SensorReadout.jsx     current value per sensor, doubles as legend
    StatusBar.jsx         link state and button lamps
  App.jsx
  styles.css
```

## Two implementation notes

Both of these are load-bearing; they look like style choices and are not.

1. **The uPlot instance is built exactly once**, in a `useEffect` with an empty
   dependency array, and updated with `setData`. Putting the data in that
   dependency array would destroy and recreate the canvas every second.
2. **`time: false` on the x scale.** Our x values are ages in seconds, not Unix
   timestamps. Without this uPlot reads them as epoch seconds and prints 1970
   dates on the axis.

## Verified behavior

Checked against a real browser, not just a passing build:

- The canvas element is the same node after several seconds of 1 Hz updates (trap 1).
- The y scale stays `[10, 50]` when fed −40 °C, 900 °C, and all-`null` data.
- The x scale stays `[0, 299]` with `time: false`; no 1970 dates anywhere.
- Trace features move measurably leftward over time (chart-recorder scroll).
- Silencing the feed flips the strip to BOX OFFLINE within ~3 s and blanks the
  readouts to `--.-`, rather than holding a stale number.
- Switching to °F relabels the axis 50–122 and leaves the traces in place,
  confirming conversion happens at display time only.

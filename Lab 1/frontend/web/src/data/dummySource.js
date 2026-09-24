/**
 * Fake sensor feed. Emits exactly the payload the Python backend will send,
 * so nothing downstream can tell the difference.
 *
 */
import { HISTORY_SECONDS } from '../lib/constants.js'

// Random walk parameters, in °C.
const WALK_STEP = 0.22 // per-second drift of the underlying temperature
const NOISE = 0.12 // per-sample measurement jitter
const PULL = 0.0015 // gentle pull back toward the sensor's center

// Each sensor sits at a different baseline so the two traces separate.
const SENSORS = [
  { key: 's1', center: 24.0, start: 23.2 },
  { key: 's2', center: 33.0, start: 34.1 },
]

const DROPOUT_CHANCE = 1 / 320
const DROPOUT_MIN = 4
const DROPOUT_MAX = 9

function createWalker({ center, start }) {
  let value = start
  let dropoutLeft = 0
  return {
    step() {
      value += (Math.random() - 0.5) * 2 * WALK_STEP + (center - value) * PULL

      if (dropoutLeft > 0) {
        dropoutLeft -= 1
        return null
      }
      if (Math.random() < DROPOUT_CHANCE) {
        dropoutLeft = DROPOUT_MIN + Math.floor(Math.random() * (DROPOUT_MAX - DROPOUT_MIN))
        return null
      }

      const measured = value + (Math.random() - 0.5) * 2 * NOISE
      return Math.round(measured * 10) / 10
    },
  }
}

function buildMessage(ts, walkers, btn1, btn2) {
  const msg = { ts, btn1, btn2 }
  for (const sensor of SENSORS) {
    const c = walkers[sensor.key].step()
    msg[sensor.key] = c === null ? { ok: false, err: 'unplugged' } : { ok: true, c }
  }
  return msg
}

export function createDummySource() {
  return {
    subscribe(onSample) {
      const walkers = {}
      for (const sensor of SENSORS) walkers[sensor.key] = createWalker(sensor)

      let btn1 = false
      let btn2 = false

      const now = Math.floor(Date.now() / 1000)
      for (let i = HISTORY_SECONDS - 1; i >= 0; i -= 1) {
        onSample(buildMessage(now - i, walkers, btn1, btn2))
      }

      const timer = setInterval(() => {
        // buttons toggle occasionally so the indicators aren't dead on screen.
        if (Math.random() < 0.02) btn1 = !btn1
        if (Math.random() < 0.02) btn2 = !btn2
        onSample(buildMessage(Math.floor(Date.now() / 1000), walkers, btn1, btn2))
      }, 1000)

      return () => clearInterval(timer)
    },
  }
}

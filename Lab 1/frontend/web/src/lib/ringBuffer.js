import { HISTORY_SECONDS, SENSOR_KEYS } from './constants.js'

export class RingBuffer {
  constructor(capacity = HISTORY_SECONDS) {
    this.capacity = capacity
    this.samples = []
  }

  push(sample) {
    // Standardize sensor values: null if missing or not ok
    const standardized = {
      ts: sample.ts,
      btn1: Boolean(sample.btn1),
      btn2: Boolean(sample.btn2),
    }

    for (const key of SENSOR_KEYS) {
      const sensorData = sample[key]
      if (sensorData && sensorData.ok && typeof sensorData.c === 'number' && !isNaN(sensorData.c)) {
        standardized[key] = sensorData.c
      } else {
        standardized[key] = null
      }
    }

    this.samples.push(standardized)
    if (this.samples.length > this.capacity) {
      this.samples.shift()
    }
  }

  get size() {
    return this.samples.length
  }

  latest(key) {
    if (this.samples.length === 0) return null
    const last = this.samples[this.samples.length - 1]
    return last[key] ?? null
  }

  valuesFor(key) {
    return this.samples.map((s) => s[key] ?? null)
  }

  clear() {
    this.samples = []
  }
}


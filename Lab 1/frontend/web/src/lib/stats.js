export function windowStats(values) {
  const valid = values.filter((v) => v !== null && v !== undefined && !isNaN(v))
  if (valid.length === 0) {
    return { min: null, max: null, avg: null, count: 0 }
  }

  let min = valid[0]
  let max = valid[0]
  let sum = 0

  for (let i = 0; i < valid.length; i++) {
    const v = valid[i]
    if (v < min) min = v
    if (v > max) max = v
    sum += v
  }

  return {
    min,
    max,
    avg: sum / valid.length,
    count: valid.length,
  }
}

export function recentTrend(values, window = 10) {
  const valid = values.filter((v) => v !== null && v !== undefined && !isNaN(v))
  if (valid.length < 2) return 'flat'

  const recent = valid.slice(-window)
  if (recent.length < 2) return 'flat'

  const first = recent[0]
  const last = recent[recent.length - 1]
  const diff = last - first

  // Threshold in °C: 0.1 °C change determines rising/falling
  if (diff > 0.1) return 'rising'
  if (diff < -0.1) return 'falling'
  return 'flat'
}


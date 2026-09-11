export const UNIT_C = 'C'
export const UNIT_F = 'F'

export function cToF(c) {
  if (c === null || c === undefined) return null
  return (c * 9) / 5 + 32
}

export function fToC(f) {
  if (f === null || f === undefined) return null
  return ((f - 32) * 5) / 9
}

export function unitSymbol(unit) {
  return `°${unit}`
}

export function toDisplay(c, unit) {
  if (c === null || c === undefined) return null
  return unit === UNIT_F ? cToF(c) : c
}

export function formatTemp(c, unit) {
  const val = toDisplay(c, unit)
  if (val === null || val === undefined || isNaN(val)) return '--.-'
  return val.toFixed(1)
}


import { SENSOR_COLORS, SENSOR_LABELS } from '../lib/constants.js'
import { formatTemp, toDisplay, unitSymbol } from '../lib/temperature.js'

const TREND_GLYPH = { rising: '▲', falling: '▼', flat: '—' }

/**
 * Current value for one sensor, plus min/max/avg over the visible window and a
 * trend arrow. Doubles as the chart legend: the pen stripe is the trace color.
 *
 * A missing reading shows "--.-" and the fault text, never a number. Stats
 * still display, computed from whatever samples the window does have.
 */
export default function SensorReadout({
  sensorKey, value, ok, err, unit, stale, stats, trend,
}) {
  const missing = stale || !ok || value === null
  const detail = stale ? 'no signal' : ok ? 'ok' : err || 'fault'

  // Span is in degrees, so it converts as a difference, not a temperature:
  // an interval of 1 °C is 1.8 °F, with no +32 offset.
  const spanC = stats && stats.min !== null ? stats.max - stats.min : null
  const span = spanC === null ? null : (unit === 'F' ? spanC * 9 / 5 : spanC)

  return (
    <div className={`readout${missing ? ' readout--missing' : ''}`}>
      <div className="readout__pen" style={{ background: SENSOR_COLORS[sensorKey] }} />
      <div className="readout__body">
        <div className="readout__top">
          <span className="readout__label">{SENSOR_LABELS[sensorKey]}</span>
          <span className={`readout__trend readout__trend--${missing ? 'flat' : trend}`}>
            {TREND_GLYPH[missing ? 'flat' : trend]}
          </span>
        </div>

        <div className="readout__value">
          <span className={`readout__number${missing ? ' readout__number--blank' : ''}`}>
            {/* An en-dash pair reads unambiguously as "no reading" at this
                size; "--.-" renders as floating ticks in ui-monospace. */}
            {missing ? '\u2013\u2013' : formatTemp(value, unit)}
          </span>
          <span className="readout__unit">{unitSymbol(unit)}</span>
        </div>

        <div className="readout__detail">{detail}</div>

        {stats && stats.count > 0 && (
          <dl className="stats">
            <div className="stats__item">
              <dt>min</dt>
              <dd>{formatTemp(stats.min, unit)}</dd>
            </div>
            <div className="stats__item">
              <dt>avg</dt>
              <dd>{formatTemp(stats.avg, unit)}</dd>
            </div>
            <div className="stats__item">
              <dt>max</dt>
              <dd>{formatTemp(stats.max, unit)}</dd>
            </div>
            <div className="stats__item">
              <dt>span</dt>
              <dd>{span === null ? '--' : span.toFixed(1)}</dd>
            </div>
          </dl>
        )}
      </div>
    </div>
  )
}

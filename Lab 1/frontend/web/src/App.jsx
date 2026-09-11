import { useMemo, useState } from 'react'
import TemperatureChart from './components/TemperatureChart.jsx'
import SensorReadout from './components/SensorReadout.jsx'
import HoverReadout from './components/HoverReadout.jsx'
import StatusBar from './components/StatusBar.jsx'
import { useThermometer } from './lib/useThermometer.js'
import { SENSOR_KEYS } from './lib/constants.js'
import { windowStats, recentTrend } from './lib/stats.js'
import { UNIT_C, UNIT_F, unitSymbol } from './lib/temperature.js'
import './styles.css'

export default function App() {
  const { buffer, tick, status, stale } = useThermometer()
  const [unit, setUnit] = useState(UNIT_C)
  const [hover, setHover] = useState(null)

  // Recomputed once per sample, not per render: the window is 300 points and
  // this runs on every tick, so it stays keyed to `tick`.
  const perSensor = useMemo(() => {
    const out = {}
    for (const key of SENSOR_KEYS) {
      const values = buffer.valuesFor(key)
      out[key] = { stats: windowStats(values), trend: recentTrend(values) }
    }
    return out
  }, [tick, buffer])

  // Difference between the two sensors, in degrees. A temperature *interval*,
  // so it scales by 9/5 without the +32 offset.
  const deltaC = useMemo(() => {
    const a = buffer.latest('s1')
    const b = buffer.latest('s2')
    if (a === null || b === null) return null
    return b - a
  }, [tick, buffer])

  const delta = deltaC === null ? null : unit === UNIT_F ? deltaC * 9 / 5 : deltaC

  const sourceLabel = import.meta.env.VITE_WS_URL
    ? `feed: ${import.meta.env.VITE_WS_URL}`
    : 'feed: simulated'

  return (
    <div className="chassis">
      <header className="chassis__head">
        <div className="chassis__brand">
          <span className="chassis__mark" aria-hidden="true" />
          <span className="chassis__model">TWO-CHANNEL THERMOMETER</span>
        </div>

        <div className="unit-toggle" role="group" aria-label="Display units">
          {[UNIT_C, UNIT_F].map((u) => (
            <button
              key={u}
              type="button"
              className={`unit-toggle__btn${unit === u ? ' unit-toggle__btn--on' : ''}`}
              onClick={() => setUnit(u)}
            >
              °{u}
            </button>
          ))}
        </div>
      </header>

      <div className="instrument">
        <div className="instrument__chart">
          <TemperatureChart buffer={buffer} tick={tick} unit={unit} onHover={setHover} />
        </div>

        <aside className="instrument__side">
          {SENSOR_KEYS.map((key) => (
            <SensorReadout
              key={key}
              sensorKey={key}
              value={buffer.latest(key)}
              ok={status[key].ok}
              err={status[key].err}
              unit={unit}
              stale={stale}
              stats={perSensor[key].stats}
              trend={perSensor[key].trend}
            />
          ))}

          <div className="delta">
            <span className="delta__label">Δ S2 − S1</span>
            <span className="delta__value">
              {delta === null || stale
                ? '\u2013\u2013'
                : `${delta > 0 ? '+' : ''}${delta.toFixed(1)}`}
              <span className="delta__unit">{unitSymbol(unit)}</span>
            </span>
          </div>

          <HoverReadout hover={hover} unit={unit} />

          <div className="gapkey">
            <span className="gapkey__swatch" />
            <span>hatching = no data</span>
          </div>
        </aside>
      </div>

      <StatusBar stale={stale} btn1={status.btn1} btn2={status.btn2} sourceLabel={sourceLabel} />
    </div>
  )
}

import { SENSOR_COLORS, SENSOR_LABELS } from '../lib/constants.js'
import { formatTemp, unitSymbol } from '../lib/temperature.js'

/**
 * Values at the hovered second. Renders in place of the live-delta line so the
 * panel height does not jump as the pointer enters and leaves the chart.
 */
export default function HoverReadout({ hover, unit }) {
  return (
    <div className="hover">
      <div className="hover__age">
        {hover ? `t − ${hover.secondsAgo}s` : 'hover chart'}
      </div>
      <div className="hover__rows">
        {(hover ? hover.values : [{ key: 's1', c: null }, { key: 's2', c: null }]).map(
          ({ key, c }) => (
            <div className="hover__row" key={key}>
              <span className="hover__dot" style={{ background: SENSOR_COLORS[key] }} />
              <span className="hover__name">{SENSOR_LABELS[key]}</span>
              <span className="hover__val">
                {c === null || c === undefined ? 'no data' : `${formatTemp(c, unit)}${unitSymbol(unit)}`}
              </span>
            </div>
          ),
        )}
      </div>
    </div>
  )
}

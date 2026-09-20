/**
 * Chassis status strip: link state, physical LCD controls, and feed info.
 *
 * "Offline" comes from the staleness timeout when no packets arrive.
 * Sensor 1 Display and Sensor 2 Display controls toggle the LCD lines on the physical box.
 */
export default function StatusBar({ stale, btn1, btn2, onToggleLcd, sourceLabel }) {
  return (
    <div className="statusbar">
      <div className={`statusbar__link${stale ? ' statusbar__link--offline' : ''}`}>
        <span className="statusbar__dot" />
        {stale ? 'BOX OFFLINE' : 'LINK OK'}
      </div>

      <div className="statusbar__lcd-group" role="group" aria-label="Physical LCD Display Controls">
        <span className="statusbar__lcd-title">PHYSICAL LCD:</span>

        <button
          type="button"
          className={`lcd-toggle-btn${btn1 ? ' lcd-toggle-btn--on' : ''}`}
          onClick={() => onToggleLcd && onToggleLcd(1, !btn1)}
          title="Toggle Sensor 1 display on physical LCD"
          aria-pressed={btn1}
        >
          <span className="lcd-toggle-btn__dot" />
          <span className="lcd-toggle-btn__text">Sensor 1 Display:</span>
          <span className="lcd-toggle-btn__state">{btn1 ? 'ON' : 'OFF'}</span>
        </button>

        <button
          type="button"
          className={`lcd-toggle-btn${btn2 ? ' lcd-toggle-btn--on' : ''}`}
          onClick={() => onToggleLcd && onToggleLcd(2, !btn2)}
          title="Toggle Sensor 2 display on physical LCD"
          aria-pressed={btn2}
        >
          <span className="lcd-toggle-btn__dot" />
          <span className="lcd-toggle-btn__text">Sensor 2 Display:</span>
          <span className="lcd-toggle-btn__state">{btn2 ? 'ON' : 'OFF'}</span>
        </button>
      </div>

      <div className="statusbar__source">{sourceLabel}</div>
    </div>
  )
}

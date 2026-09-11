/**
 * Chassis status strip: link state and the two pushbutton indicators.
 *
 * "Offline" here comes from the staleness timeout, not from any field in the
 * payload — the box going quiet is the signal.
 */
export default function StatusBar({ stale, btn1, btn2, sourceLabel }) {
  return (
    <div className="statusbar">
      <div className={`statusbar__link${stale ? ' statusbar__link--offline' : ''}`}>
        <span className="statusbar__dot" />
        {stale ? 'BOX OFFLINE' : 'LINK OK'}
      </div>
      <div className="statusbar__buttons">
        <span className={`lamp${btn1 ? ' lamp--on' : ''}`}>BTN1</span>
        <span className={`lamp${btn2 ? ' lamp--on' : ''}`}>BTN2</span>
      </div>
      <div className="statusbar__source">{sourceLabel}</div>
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { UNIT_C, UNIT_F, cToF, fToC, unitSymbol } from '../lib/temperature.js'
import { getApiBaseUrl } from '../lib/api.js'

export default function AlertSettings({ unit }) {
  const [recipientEmail, setRecipientEmail] = useState('')
  const [minInput, setMinInput] = useState('')
  const [maxInput, setMaxInput] = useState('')
  const [lowMessage, setLowMessage] = useState('')
  const [highMessage, setHighMessage] = useState('')

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [feedback, setFeedback] = useState(null) // { type: 'success' | 'error' | 'info', message: string }

  const prevUnitRef = useRef(unit)
  const apiBase = getApiBaseUrl()

  // Fetch initial alert settings from backend
  useEffect(() => {
    let active = true
    async function fetchSettings() {
      try {
        setLoading(true)
        const res = await fetch(`${apiBase}/api/settings/alerts`)
        if (!res.ok) {
          throw new Error(`Failed to load alert settings (${res.status})`)
        }
        const data = await res.json()
        if (!active) return

        setRecipientEmail(data.recipient_email || '')
        setLowMessage(data.low_message || '')
        setHighMessage(data.high_message || '')

        if (data.min_temperature_c !== null && data.min_temperature_c !== undefined) {
          const val = unit === UNIT_F ? cToF(data.min_temperature_c) : data.min_temperature_c
          setMinInput(val !== null ? (unit === UNIT_F ? val.toFixed(1) : String(val)) : '')
        } else {
          setMinInput('')
        }

        if (data.max_temperature_c !== null && data.max_temperature_c !== undefined) {
          const val = unit === UNIT_F ? cToF(data.max_temperature_c) : data.max_temperature_c
          setMaxInput(val !== null ? (unit === UNIT_F ? val.toFixed(1) : String(val)) : '')
        } else {
          setMaxInput('')
        }
      } catch (err) {
        if (!active) return
        setFeedback({
          type: 'error',
          message: `Could not connect to backend at ${apiBase}: ${err.message}`,
        })
      } finally {
        if (active) setLoading(false)
      }
    }

    fetchSettings()
    return () => {
      active = false
    }
  }, [apiBase])

  // Convert displayed input values when °C / °F unit toggle changes
  useEffect(() => {
    const prevUnit = prevUnitRef.current
    if (prevUnit !== unit) {
      if (minInput !== '' && !isNaN(parseFloat(minInput))) {
        const minC = prevUnit === UNIT_F ? fToC(parseFloat(minInput)) : parseFloat(minInput)
        const newMin = unit === UNIT_F ? cToF(minC) : minC
        setMinInput(newMin !== null ? (unit === UNIT_F ? newMin.toFixed(1) : String(Math.round(newMin * 10) / 10)) : '')
      }
      if (maxInput !== '' && !isNaN(parseFloat(maxInput))) {
        const maxC = prevUnit === UNIT_F ? fToC(parseFloat(maxInput)) : parseFloat(maxInput)
        const newMax = unit === UNIT_F ? cToF(maxC) : maxC
        setMaxInput(newMax !== null ? (unit === UNIT_F ? newMax.toFixed(1) : String(Math.round(newMax * 10) / 10)) : '')
      }
      prevUnitRef.current = unit
    }
  }, [unit, minInput, maxInput])

  const validate = () => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!recipientEmail || !emailRegex.test(recipientEmail.trim())) {
      return 'Please enter a valid recipient email address.'
    }

    const minParsed = parseFloat(minInput)
    const maxParsed = parseFloat(maxInput)

    if (minInput === '' || isNaN(minParsed) || maxInput === '' || isNaN(maxParsed)) {
      return 'Please enter valid numbers for both minimum and maximum temperature thresholds.'
    }

    const minC = unit === UNIT_F ? fToC(minParsed) : minParsed
    const maxC = unit === UNIT_F ? fToC(maxParsed) : maxParsed

    if (minC >= maxC) {
      return `Minimum threshold (${minParsed} ${unitSymbol(unit)}) must be strictly less than maximum threshold (${maxParsed} ${unitSymbol(unit)}).`
    }

    if (!lowMessage.trim()) {
      return 'Please provide a custom low temperature alert message.'
    }

    if (!highMessage.trim()) {
      return 'Please provide a custom high temperature alert message.'
    }

    return null
  }

  const handleSave = async (e) => {
    if (e) e.preventDefault()
    setFeedback(null)

    const error = validate()
    if (error) {
      setFeedback({ type: 'error', message: error })
      return
    }

    const minParsed = parseFloat(minInput)
    const maxParsed = parseFloat(maxInput)
    const minC = unit === UNIT_F ? fToC(minParsed) : minParsed
    const maxC = unit === UNIT_F ? fToC(maxParsed) : maxParsed

    const payload = {
      // Alerts are always armed: there is no mute control by design.
      enabled: true,
      recipient_email: recipientEmail.trim(),
      min_temperature_c: Math.round(minC * 10) / 10,
      max_temperature_c: Math.round(maxC * 10) / 10,
      low_message: lowMessage.trim(),
      high_message: highMessage.trim(),
    }

    try {
      setSaving(true)
      const res = await fetch(`${apiBase}/api/settings/alerts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || `Server error (${res.status})`)
      }

      const resData = await res.json()
      setFeedback({
        type: 'success',
        message: 'Alert configuration saved successfully.',
      })
      if (resData.settings) {
        setRecipientEmail(resData.settings.recipient_email)
        setLowMessage(resData.settings.low_message)
        setHighMessage(resData.settings.high_message)
      }
    } catch (err) {
      setFeedback({
        type: 'error',
        message: `Failed to save alert settings: ${err.message}`,
      })
    } finally {
      setSaving(false)
    }
  }

  const handleSendTest = async () => {
    setFeedback(null)
    try {
      setTesting(true)
      const res = await fetch(`${apiBase}/api/settings/alerts/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })

      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(data.detail || `Failed to send test email (${res.status})`)
      }

      setFeedback({
        type: 'success',
        message: data.message || `Test alert email sent to ${recipientEmail}!`,
      })
    } catch (err) {
      setFeedback({
        type: 'error',
        message: `Test email failed: ${err.message}`,
      })
    } finally {
      setTesting(false)
    }
  }

  return (
    <section className="alerts-panel" aria-label="Email Alert Settings">
      <div className="alerts-panel__head">
        <div className="alerts-panel__title-group">
          <span className="alerts-panel__badge" aria-hidden="true" />
          <h2 className="alerts-panel__title">EMAIL ALERT SETTINGS</h2>
        </div>
        <div className="alerts-panel__status">
          <span className="alerts-panel__toggle-text alerts-panel__toggle-text--on">
            ALERTS ARMED
          </span>
        </div>
      </div>

      {feedback && (
        <div
          className={`alerts-panel__banner alerts-panel__banner--${feedback.type}`}
          role="status"
        >
          <span className="alerts-panel__banner-icon">
            {feedback.type === 'success' ? '✔' : feedback.type === 'error' ? '⚠' : 'ℹ'}
          </span>
          <span className="alerts-panel__banner-text">{feedback.message}</span>
          <button
            type="button"
            className="alerts-panel__banner-close"
            onClick={() => setFeedback(null)}
            aria-label="Dismiss message"
          >
            ×
          </button>
        </div>
      )}

      <form className="alerts-panel__form" onSubmit={handleSave}>
        <div className="alerts-panel__grid">
          {/* Recipient Email */}
          <div className="alerts-panel__field alerts-panel__field--full">
            <label htmlFor="recipient-email" className="alerts-panel__label">
              RECIPIENT EMAIL ADDRESS
            </label>
            <input
              id="recipient-email"
              type="email"
              className="alerts-panel__input"
              placeholder="e.g. user@uiowa.edu"
              value={recipientEmail}
              onChange={(e) => setRecipientEmail(e.target.value)}
              disabled={loading}
              required
            />
          </div>

          {/* Min Temperature Threshold */}
          <div className="alerts-panel__field">
            <label htmlFor="min-temp" className="alerts-panel__label">
              LOW THRESHOLD MIN ({unitSymbol(unit)})
            </label>
            <div className="alerts-panel__input-group">
              <input
                id="min-temp"
                type="number"
                step="0.1"
                className="alerts-panel__input"
                placeholder={unit === UNIT_F ? '59.0' : '15.0'}
                value={minInput}
                onChange={(e) => setMinInput(e.target.value)}
                disabled={loading}
                required
              />
              <span className="alerts-panel__unit-addon">{unitSymbol(unit)}</span>
            </div>
          </div>

          {/* Max Temperature Threshold */}
          <div className="alerts-panel__field">
            <label htmlFor="max-temp" className="alerts-panel__label">
              HIGH THRESHOLD MAX ({unitSymbol(unit)})
            </label>
            <div className="alerts-panel__input-group">
              <input
                id="max-temp"
                type="number"
                step="0.1"
                className="alerts-panel__input"
                placeholder={unit === UNIT_F ? '95.0' : '35.0'}
                value={maxInput}
                onChange={(e) => setMaxInput(e.target.value)}
                disabled={loading}
                required
              />
              <span className="alerts-panel__unit-addon">{unitSymbol(unit)}</span>
            </div>
          </div>

          {/* Low Temperature Message */}
          <div className="alerts-panel__field">
            <label htmlFor="low-msg" className="alerts-panel__label">
              LOW TEMPERATURE MESSAGE
            </label>
            <input
              id="low-msg"
              type="text"
              className="alerts-panel__input"
              placeholder="e.g. Temperature has fallen below the minimum threshold!"
              value={lowMessage}
              onChange={(e) => setLowMessage(e.target.value)}
              disabled={loading}
              required
            />
          </div>

          {/* High Temperature Message */}
          <div className="alerts-panel__field">
            <label htmlFor="high-msg" className="alerts-panel__label">
              HIGH TEMPERATURE MESSAGE
            </label>
            <input
              id="high-msg"
              type="text"
              className="alerts-panel__input"
              placeholder="e.g. Temperature has exceeded the maximum threshold!"
              value={highMessage}
              onChange={(e) => setHighMessage(e.target.value)}
              disabled={loading}
              required
            />
          </div>
        </div>

        {/* Action Buttons */}
        <div className="alerts-panel__actions">
          <button
            type="submit"
            className="alerts-panel__btn alerts-panel__btn--primary"
            disabled={loading || saving || testing}
          >
            {saving ? 'SAVING...' : 'SAVE SETTINGS'}
          </button>

          <button
            type="button"
            className="alerts-panel__btn alerts-panel__btn--secondary"
            onClick={handleSendTest}
            disabled={loading || saving || testing}
          >
            {testing ? 'SENDING TEST...' : 'SEND TEST EMAIL'}
          </button>
        </div>
      </form>
    </section>
  )
}


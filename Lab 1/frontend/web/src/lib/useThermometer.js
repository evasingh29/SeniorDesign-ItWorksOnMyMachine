import { useEffect, useRef, useState } from 'react'
import { createSource } from '../data/source.js'
import { RingBuffer } from './ringBuffer.js'
import { HISTORY_SECONDS, STALE_AFTER_MS } from './constants.js'

export function useThermometer() {
  const bufferRef = useRef(new RingBuffer())
  const [tick, setTick] = useState(0)
  const [stale, setStale] = useState(true)
  const [status, setStatus] = useState({
    s1: { ok: false, err: 'no signal' },
    s2: { ok: false, err: 'no signal' },
    btn1: false,
    btn2: false,
  })

  const staleTimerRef = useRef(null)
  const lastSampleTimeRef = useRef(Date.now())
  const statusRef = useRef(status)
  statusRef.current = status

  useEffect(() => {
    const resetStaleTimer = () => {
      if (staleTimerRef.current) clearTimeout(staleTimerRef.current)
      setStale(false)

      staleTimerRef.current = setTimeout(() => {
        setStale(true)
        setStatus((prev) => ({
          ...prev,
          s1: { ok: false, err: 'no signal' },
          s2: { ok: false, err: 'no signal' },
        }))
      }, STALE_AFTER_MS)
    }

    const source = createSource()
    const unsubscribe = source.subscribe((sample) => {
      if (!sample) return

      resetStaleTimer()
      lastSampleTimeRef.current = Date.now()
      bufferRef.current.push(sample)

      setStatus({
        s1: sample.s1 || { ok: false, err: 'missing' },
        s2: sample.s2 || { ok: false, err: 'missing' },
        btn1: Boolean(sample.btn1),
        btn2: Boolean(sample.btn2),
      })

      setTick((t) => t + 1)
    })

    // Heartbeat ticker:
    // If the box stops sending data or is powered off, continue advancing
    // the 300-second window once per second with missing/null samples.
    const ticker = setInterval(() => {
      const now = Date.now()
      const elapsed = now - lastSampleTimeRef.current

      // If at least 1.2 seconds have elapsed since the last pushed sample,
      // generate null/missing samples for the elapsed offline seconds.
      if (elapsed >= 1200) {
        const missedSeconds = Math.min(
          Math.floor(elapsed / 1000),
          HISTORY_SECONDS
        )

        const nowSec = Math.floor(now / 1000)
        for (let i = missedSeconds - 1; i >= 0; i--) {
          const offlineSample = {
            ts: nowSec - i,
            s1: { ok: false, err: 'no signal' },
            s2: { ok: false, err: 'no signal' },
            btn1: statusRef.current.btn1,
            btn2: statusRef.current.btn2,
          }
          bufferRef.current.push(offlineSample)
        }

        lastSampleTimeRef.current += missedSeconds * 1000
        setTick((t) => t + 1)
      }
    }, 500)

    return () => {
      if (staleTimerRef.current) clearTimeout(staleTimerRef.current)
      clearInterval(ticker)
      if (unsubscribe) unsubscribe()
    }
  }, [])

  return {
    buffer: bufferRef.current,
    tick,
    status,
    stale,
  }
}

import { useEffect, useRef, useState } from 'react'
import { createSource } from '../data/source.js'
import { RingBuffer } from './ringBuffer.js'
import { STALE_AFTER_MS } from './constants.js'

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

  useEffect(() => {
    const resetStaleTimer = () => {
      if (staleTimerRef.current) clearTimeout(staleTimerRef.current)
      setStale(false)

      staleTimerRef.current = setTimeout(() => {
        setStale(true)
      }, STALE_AFTER_MS)
    }

    const source = createSource()
    const unsubscribe = source.subscribe((sample) => {
      if (!sample) return

      resetStaleTimer()
      bufferRef.current.push(sample)

      setStatus({
        s1: sample.s1 || { ok: false, err: 'missing' },
        s2: sample.s2 || { ok: false, err: 'missing' },
        btn1: Boolean(sample.btn1),
        btn2: Boolean(sample.btn2),
      })

      setTick((t) => t + 1)
    })

    return () => {
      if (staleTimerRef.current) clearTimeout(staleTimerRef.current)
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


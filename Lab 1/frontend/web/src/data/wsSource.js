/**
 * Live feed from the Python backend.
 *
 * Not exercised yet — today's scope is dummy data only — but it implements the
 * same subscribe(onSample) contract as the dummy source, so setting VITE_WS_URL
 * is the entire switch. The browser never speaks MQTT; the backend subscribes
 * to HiveMQ and relays over this socket.
 *
 * Note there is no pre-fill here: the live feed starts empty and fills in over
 * five minutes, which is correct. A real chart recorder has no history for time
 * it wasn't running, and inventing one would be fabricating readings.
 */
const RECONNECT_MS = 2000

export function createWebSocketSource(url) {
  return {
    subscribe(onSample) {
      let socket = null
      let retryTimer = null
      let closed = false

      const connect = () => {
        if (closed) return
        socket = new WebSocket(url)

        socket.onmessage = (event) => {
          try {
            onSample(JSON.parse(event.data))
          } catch {
            // A malformed frame is dropped rather than crashing the feed. It
            // then ages into staleness on its own, which is the correct
            // signal: we are not receiving usable data.
          }
        }

        socket.onclose = () => {
          // No synthetic "offline" sample is pushed. Offline is the absence of
          // messages, detected by the staleness timeout in useThermometer.
          if (!closed) retryTimer = setTimeout(connect, RECONNECT_MS)
        }

        socket.onerror = () => socket && socket.close()
      }

      connect()

      return () => {
        closed = true
        if (retryTimer) clearTimeout(retryTimer)
        if (socket) socket.close()
      }
    },
  }
}

/**
 * Live feed from the Python backend.
 * the live feed starts empty and fills in over five minutes, which is correct. A real chart recorder has no history for time
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
            const data = JSON.parse(event.data)
            if (Array.isArray(data)) {
              data.forEach((sample) => onSample(sample))
            } else if (data && typeof data === 'object') {
              onSample(data)
            }
          } catch {
          }
        }

        socket.onclose = () => {
          // No synthetic "offline" sample is pushed.
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

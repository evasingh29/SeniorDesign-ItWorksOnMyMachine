/**
 * The single seam between the UI and wherever readings come from.
 *
 * A source is an object with one method:
 *
 *   subscribe(onSample) -> unsubscribe()
 *
 * `onSample` is handed one message in the backend's wire format:
 *
 *   {
 *     "ts": 1756512000,
 *     "s1": { "ok": true,  "c": 22.4 },
 *     "s2": { "ok": false, "err": "unplugged" },
 *     "btn1": true,
 *     "btn2": false
 *   }
 *
 * Temperatures are Celsius on the wire and stay Celsius in the buffer.
 * Fahrenheit exists only at display time, in formatTemp().
 *
 * Swapping the dummy generator for the real feed is a change to this file
 * alone: implement the WebSocket client against the same shape and let
 * createSource() pick it. No component imports either implementation.
 */
import { createDummySource } from './dummySource.js'
import { createWebSocketSource } from './wsSource.js'

export function createSource() {
  const url = import.meta.env.VITE_WS_URL
  if (url) return createWebSocketSource(url)
  return createDummySource()
}

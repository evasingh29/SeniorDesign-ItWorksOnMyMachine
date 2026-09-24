/**
 * This is the single seam between the UI and wherever readings come from.
 * Temperatures are Celsius on the wire and stay Celsius in the buffer.
 * Fahrenheit exists only at display time, in formatTemp().
 *
 * Swapping the dummy generator for the real feed is a change to this file
 * alone: implement the WebSocket client against the same shape and let
 * createSource() pick it.
 */
import { createDummySource } from './dummySource.js'
import { createWebSocketSource } from './wsSource.js'

export function createSource() {
  const url = import.meta.env.VITE_WS_URL
  if (url) return createWebSocketSource(url)
  return createDummySource()
}

/**
 * Helper utilities for REST API calls to the FastAPI backend.
 */

export function getApiBaseUrl() {
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL.replace(/\/+$/, '')
  }
  if (import.meta.env.VITE_WS_URL) {
    try {
      const parsed = new URL(import.meta.env.VITE_WS_URL)
      const protocol = parsed.protocol === 'wss:' ? 'https:' : 'http:'
      return `${protocol}//${parsed.host}`
    } catch {
      // ignore invalid URL and fallback
    }
  }
  return 'http://localhost:8000'
}

export async function sendButtonCommand(buttonId, on) {
  const apiBase = getApiBaseUrl()
  const res = await fetch(`${apiBase}/api/buttons/${buttonId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ on: Boolean(on) }),
  })

  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || `Button command failed (${res.status})`)
  }

  return res.json()
}


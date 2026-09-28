import { useEffect, useRef, useState } from 'react'
import { getAccessToken, refreshAccessToken } from './api'
import { WS_PATH } from './config'

const RECONNECT_DELAY_MS = 3000

// Subscribes to a backend live-push channel, token-authenticated.
// `path` defaults to the admin alert feed (/ws/alerts); pass an explicit
// path (e.g. `/ws/tourist/{id}`) to use the per-tourist channel instead.
export default function useWebSocket(onEvent, path = WS_PATH) {
  const [connected, setConnected] = useState(false)
  const wsRef = useRef(null)
  const cbRef = useRef(onEvent)
  cbRef.current = onEvent

  useEffect(() => {
    if (!path) return undefined
    let cancelled = false
    let reconnectTimer = null

    const connectWith = (token) => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      // Token passed as a query param so the server can authorize the socket.
      const url = `${proto}://${location.host}${path}?token=${encodeURIComponent(token)}`
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)
      ws.onmessage = (e) => {
        try {
          cbRef.current?.(JSON.parse(e.data))
        } catch { /* ignore */ }
      }
      ws.onclose = () => {
        setConnected(false)
        if (cancelled) return
        // Access tokens expire in ~30 minutes; a socket open longer than
        // that gets closed by the server and needs a fresh token to
        // reconnect. The access token lives in memory only (api.js), so
        // `open()` re-reads it (and refreshes if needed) on every attempt
        // rather than relying on a stale closure.
        reconnectTimer = setTimeout(open, RECONNECT_DELAY_MS)
      }
    }

    const open = async () => {
      if (cancelled) return
      let token = getAccessToken()
      if (!token) {
        // Covers the case where this hook mounts before AuthProvider's own
        // silent refresh resolves, or a reconnect attempt after the
        // in-memory token was cleared without a page reload.
        try {
          token = await refreshAccessToken()
        } catch {
          return
        }
      }
      if (cancelled || !token) return
      connectWith(token)
    }

    open()
    return () => {
      cancelled = true
      clearTimeout(reconnectTimer)
      wsRef.current?.close()
    }
  }, [path])

  return { connected }
}

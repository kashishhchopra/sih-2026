import { useEffect, useRef, useState } from 'react'

// Wraps navigator.geolocation.watchPosition with permission-state handling.
// `enabled` gates the whole thing (the app also has its own tracking toggle,
// which now controls this hook instead of a fake random walk).
export default function useGeolocation({ enabled = true } = {}) {
  const [position, setPosition] = useState(null)
  const [error, setError] = useState(null)
  const [permissionState, setPermissionState] = useState('unknown') // granted|denied|prompt|unsupported|unknown
  const watchIdRef = useRef(null)

  useEffect(() => {
    if (!('geolocation' in navigator)) {
      setPermissionState('unsupported')
      return
    }
    if (!enabled) {
      if (watchIdRef.current != null) {
        navigator.geolocation.clearWatch(watchIdRef.current)
        watchIdRef.current = null
      }
      return
    }

    // navigator.permissions is not universally supported (notably older
    // Safari); watchPosition below still works without it, this just gives
    // an earlier, more specific UI message when denied.
    if (navigator.permissions?.query) {
      navigator.permissions
        .query({ name: 'geolocation' })
        .then((status) => {
          setPermissionState(status.state)
          status.onchange = () => setPermissionState(status.state)
        })
        .catch(() => {})
    }

    watchIdRef.current = navigator.geolocation.watchPosition(
      (pos) => {
        setError(null)
        setPermissionState('granted')
        setPosition({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
          speedKmh: pos.coords.speed != null ? Math.max(0, pos.coords.speed) * 3.6 : 0,
          heading: pos.coords.heading ?? null,
          timestamp: pos.timestamp,
        })
      },
      (err) => {
        setError(err.message)
        if (err.code === err.PERMISSION_DENIED) setPermissionState('denied')
      },
      { enableHighAccuracy: true, maximumAge: 10_000, timeout: 15_000 },
    )

    return () => {
      if (watchIdRef.current != null) {
        navigator.geolocation.clearWatch(watchIdRef.current)
        watchIdRef.current = null
      }
    }
  }, [enabled])

  return { position, error, permissionState }
}

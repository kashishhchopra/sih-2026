import { useEffect, useState } from 'react'

// navigator.onLine reports network *interface* state, not real connectivity
// (a device can report "online" on a captive-portal Wi-Fi with no actual
// internet) -- good enough here as a lightweight UI signal, not something
// load-bearing: the offline SOS queue's own request failure handling is what
// actually protects the SOS flow, this hook only drives the visible badge.
export default function useOnlineStatus() {
  const [online, setOnline] = useState(
    typeof navigator !== 'undefined' ? navigator.onLine : true,
  )

  useEffect(() => {
    const goOnline = () => setOnline(true)
    const goOffline = () => setOnline(false)
    window.addEventListener('online', goOnline)
    window.addEventListener('offline', goOffline)
    return () => {
      window.removeEventListener('online', goOnline)
      window.removeEventListener('offline', goOffline)
    }
  }, [])

  return online
}

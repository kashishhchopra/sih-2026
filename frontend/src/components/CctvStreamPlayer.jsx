import { useEffect, useRef, useState } from 'react'
import { CONNECTION } from '../lib/cctvService'

// Renders one camera's feed, choosing how to play it from the stream
// metadata the backend supplied -- never from a guess about the URL.
//
//   hls    -> <video> via hls.js, or the browser's native HLS (Safari/iOS)
//   mp4    -> <video>
//   mjpeg  -> <img> (an MJPEG endpoint is a never-ending multipart image)
//   jpeg   -> <img> re-fetched on an interval. Many public road cameras
//             publish a still that is replaced every few seconds rather than
//             a video stream; rendering it once would show a frozen frame
//             under a LIVE badge, which would be a lie.
//   webrtc -> not negotiable without a signalling server this deployment
//             doesn't run, so it says so rather than showing a dead box
//   rtsp   -> no browser plays RTSP directly; the backend already reports
//             it as `unplayable` and we explain that
//   none   -> a coverage-only camera with no feed
//
// There is no placeholder/simulated video anywhere in here: if a real frame
// cannot be shown, the surface says why instead of faking one.

function Overlay({ tone = 'slate', title, detail, onRetry, retrying, compact = false }) {
  const toneCls = {
    slate: 'text-slate-400',
    amber: 'text-amber-400',
    red: 'text-red-400',
  }[tone] || 'text-slate-400'
  // The small grid tile (CameraCard, ~96px tall) has no room for a title +
  // detail line + Retry button without colliding with the LIVE/OFFLINE
  // badge pinned to its top-left corner -- that collision is exactly what
  // produced "UNAVAILABLE" running into "...ERA UNAVAILABLE" on screen.
  // Compact mode shows one short line only; the full explanation and the
  // Retry button live in the expanded view (tapping the tile opens it).
  if (compact) {
    return (
      <div className="absolute inset-0 flex items-end justify-center pb-1.5 px-2 text-center">
        <div className={`text-[10px] font-medium leading-tight ${toneCls}`}>{title}</div>
      </div>
    )
  }
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 px-3 text-center">
      <div className={`text-xs font-semibold ${toneCls}`}>{title}</div>
      {detail && <div className="text-[10px] text-slate-500">{detail}</div>}
      {onRetry && (
        <button type="button" onClick={onRetry} disabled={retrying}
          className="mt-1.5 text-[10px] font-semibold px-2.5 py-1 rounded bg-slate-700 hover:bg-slate-600 text-slate-100 disabled:opacity-60">
          {retrying ? 'Reconnecting…' : 'Retry Connection'}
        </button>
      )}
    </div>
  )
}

// How often a still-image camera is re-fetched. Public road cameras
// typically publish a new frame every few seconds; polling faster than this
// just burns the source's bandwidth for no extra information.
const STILL_REFRESH_MS = 5000

export default function CctvStreamPlayer({
  camera, className = '', onRetry, retrying = false,
  // True for the small grid tile (CameraCard, ~96px tall): a short label
  // only, no detail line or Retry button -- see Overlay's compact branch
  // above for why. The expanded single-camera view passes compact=false
  // (the default) to show the full explanation and a working Retry.
  compact = false,
}) {
  const videoRef = useRef(null)
  const [playbackError, setPlaybackError] = useState(null)
  const [stillTick, setStillTick] = useState(0)
  const { stream_url: url, stream_type: type, connection } = camera || {}

  // Keep a still-image feed moving. The cache-busting parameter is what
  // actually forces a new frame -- without it the browser serves the same
  // cached image forever.
  useEffect(() => {
    if (type !== 'jpeg' || connection !== CONNECTION.LIVE) return undefined
    const timer = setInterval(() => setStillTick((n) => n + 1), STILL_REFRESH_MS)
    return () => clearInterval(timer)
  }, [type, connection, url])

  // Attach/detach HLS for this source. hls.js is loaded lazily so a
  // dashboard with no HLS cameras never pays for the library.
  useEffect(() => {
    setPlaybackError(null)
    if (type !== 'hls' || !url || connection !== CONNECTION.LIVE) return undefined
    const video = videoRef.current
    if (!video) return undefined

    // Safari/iOS play HLS natively; there's no reason to load a library there.
    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = url
      return undefined
    }

    let hls = null
    let cancelled = false
    import('hls.js').then(({ default: Hls }) => {
      if (cancelled || !Hls.isSupported()) {
        if (!cancelled) setPlaybackError('This browser cannot play this stream.')
        return
      }
      hls = new Hls({ enableWorker: true, lowLatencyMode: true })
      hls.on(Hls.Events.ERROR, (_e, data) => {
        // Only a fatal error means the feed is genuinely gone; hls.js
        // recovers from most network/media hiccups on its own.
        if (data?.fatal) setPlaybackError('Lost connection to camera.')
      })
      hls.loadSource(url)
      hls.attachMedia(video)
    }).catch(() => {
      if (!cancelled) setPlaybackError('Stream player unavailable.')
    })

    return () => {
      cancelled = true
      if (hls) hls.destroy()
    }
  }, [url, type, connection])

  const frame = `relative bg-slate-950 overflow-hidden ${className}`

  if (!camera) return <div className={frame} />

  if (connection === CONNECTION.DISABLED) {
    return <div className={frame}><Overlay title={compact ? 'Disabled' : 'Camera Disabled'}
      detail="Turned off by the operator" compact={compact} /></div>
  }
  if (connection === CONNECTION.NO_STREAM) {
    return <div className={frame}><Overlay title={compact ? 'No feed' : 'No Feed Configured'}
      detail="Coverage record only — no video source" compact={compact} /></div>
  }
  if (connection === CONNECTION.UNPLAYABLE) {
    return <div className={frame}><Overlay tone="amber" title={compact ? 'Not viewable here' : 'Stream Not Viewable Here'}
      detail="RTSP needs a server-side relay this deployment doesn't run" compact={compact} /></div>
  }
  if (connection === CONNECTION.UNAVAILABLE) {
    return (
      <div className={frame}>
        <Overlay tone="amber" title={compact ? 'Unavailable' : 'CAMERA UNAVAILABLE'}
          detail="The source is publishing an 'unavailable' notice, not a view"
          onRetry={onRetry} retrying={retrying} compact={compact} />
      </div>
    )
  }
  if (connection === CONNECTION.UNKNOWN) {
    return <div className={frame}><Overlay title={compact ? 'Connecting…' : 'Connecting to camera…'} compact={compact} /></div>
  }
  if (connection === CONNECTION.OFFLINE) {
    return (
      <div className={frame}>
        <Overlay tone="red" title={compact ? 'Offline' : 'CAMERA OFFLINE'} detail="Unable to connect to camera"
          onRetry={onRetry} retrying={retrying} compact={compact} />
      </div>
    )
  }

  // connection === live
  if (playbackError) {
    return (
      <div className={frame}>
        <Overlay tone="red" title={compact ? 'Offline' : 'CAMERA OFFLINE'} detail={playbackError}
          onRetry={onRetry} retrying={retrying} compact={compact} />
      </div>
    )
  }

  if (type === 'jpeg') {
    const separator = url.includes('?') ? '&' : '?'
    return (
      <div className={frame}>
        <img src={`${url}${separator}_t=${stillTick}`}
          alt={`Latest frame from ${camera.label}`}
          className="w-full h-full object-cover"
          onError={() => setPlaybackError('Lost connection to camera.')} />
      </div>
    )
  }

  if (type === 'mjpeg') {
    return (
      <div className={frame}>
        {/* An MJPEG endpoint streams frames as a multipart image response. */}
        <img src={url} alt={`Live feed from ${camera.label}`}
          className="w-full h-full object-cover"
          onError={() => setPlaybackError('Lost connection to camera.')} />
      </div>
    )
  }

  if (type === 'hls' || type === 'mp4') {
    return (
      <div className={frame}>
        <video ref={videoRef} className="w-full h-full object-cover"
          autoPlay muted playsInline controls={false}
          src={type === 'mp4' ? url : undefined}
          aria-label={`Live feed from ${camera.label}`}
          onError={() => setPlaybackError('Lost connection to camera.')} />
      </div>
    )
  }

  if (type === 'webrtc') {
    return <div className={frame}><Overlay tone="amber" title={compact ? 'WebRTC' : 'WebRTC Feed'}
      detail="Needs a signalling server this deployment doesn't run" compact={compact} /></div>
  }

  return <div className={frame}><Overlay title={compact ? 'Unsupported' : 'Unsupported Stream Type'}
    detail={type} compact={compact} /></div>
}

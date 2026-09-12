import { useEffect, useState } from 'react'
import useLivenessCheck from '../hooks/useLivenessCheck.js'
import { verifyLiveness } from '../lib/livenessService.js'

// Real, camera-based 3-step active-liveness check for the registration
// "Photo" step -- see hooks/useLivenessCheck.js for the actual detection
// logic (MediaPipe Face Landmarker + geometry on real landmarks, no
// server round-trip per frame) and lib/liveness.js for why the movement
// checks don't need to know absolute left/right.
//
// Deliberately NOT a replacement for the existing live-camera capture --
// pages/Register.jsx keeps that component (`LivePhotoCapture`) as the
// fallback for a browser/device this can't run on (see `onUnavailable`),
// so registration is never blocked by this feature.
export default function LivenessCapture({ onCapture, onCancel, onUnavailable }) {
  const liveness = useLivenessCheck({ onUnavailable })
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')

  const useThisPhoto = async () => {
    setSubmitting(true)
    setSubmitError('')
    try {
      const result = await verifyLiveness({
        sessionId: liveness.sessionId,
        photo: liveness.finalPhoto,
        steps: liveness.completedStepIds,
        livenessScore: liveness.livenessScore ?? 0,
      })
      onCapture(liveness.finalPhoto, { livenessToken: result.verification_token || null })
    } catch {
      // The verification record is an internal integrity add-on, not a
      // gate on registration itself -- a network hiccup here must still
      // let the tourist continue with the photo they just captured.
      onCapture(liveness.finalPhoto, { livenessToken: null })
    } finally {
      setSubmitting(false)
    }
  }

  // Once the model/camera genuinely can't run here, hand off to the
  // fallback immediately rather than showing a dead screen.
  useEffect(() => {
    if (liveness.overallPhase === 'unavailable') onUnavailable?.()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveness.overallPhase])

  if (liveness.overallPhase === 'unavailable') return null

  if (liveness.overallPhase === 'complete') {
    return (
      <div className="space-y-3 text-center">
        <div className="text-emerald-400 font-semibold">✓ Identity Photo Verified</div>
        <p className="text-xs text-slate-400">Your live photo has been successfully captured.</p>
        <img src={liveness.finalPhoto} alt="Your profile" className="w-32 h-32 rounded-xl object-cover mx-auto border border-white/20" />
        {submitError && <div className="text-xs text-red-300">{submitError}</div>}
        <div className="flex gap-3 justify-center pt-1">
          <button type="button" onClick={liveness.retakeAll}
            className="text-xs font-semibold bg-white/10 hover:bg-white/20 border border-white/20 px-4 py-2 rounded-lg">
            Retake
          </button>
          <button type="button" onClick={useThisPhoto} disabled={submitting}
            className="text-xs font-semibold bg-gradient-to-r from-cyan-400 to-sky-500 text-slate-900 px-5 py-2 rounded-lg disabled:opacity-60">
            {submitting ? 'Saving…' : 'Use Photo'}
          </button>
        </div>
      </div>
    )
  }

  const stepMeta = liveness.steps[liveness.stepIndex]
  const inCapture = liveness.overallPhase === 'capturing'

  return (
    <div className="space-y-3">
      <div className="text-center">
        <h3 className="font-bold text-white">Verify Your Identity</h3>
        <p className="text-xs text-slate-400">Complete 3 quick actions so we can confirm you're a real person.</p>
      </div>

      {/* Mirrored container: video + face-box overlay flip together so the
          overlay always lines up with what's on screen, without any manual
          coordinate math -- see file header. */}
      <div className="relative w-full max-w-xs mx-auto rounded-xl overflow-hidden bg-black" style={{ aspectRatio: '3/4' }}>
        <div className="absolute inset-0" style={{ transform: 'scaleX(-1)' }}>
          <video ref={liveness.videoRef} muted playsInline className="w-full h-full object-cover" />
          {liveness.faceBox && !inCapture && (
            <div
              className={`absolute border-2 rounded-lg transition-colors ${
                liveness.stepPhase === 'completed' ? 'border-emerald-400'
                  : liveness.stepPhase === 'movement_detected' ? 'border-cyan-400'
                    : 'border-white/70'}`}
              style={{
                left: `${liveness.faceBox.x * 100}%`, top: `${liveness.faceBox.y * 100}%`,
                width: `${liveness.faceBox.width * 100}%`, height: `${liveness.faceBox.height * 100}%`,
              }}
            />
          )}
        </div>

        {liveness.modelState === 'loading' && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/60 text-xs text-slate-300 text-center px-4">
            Starting camera &amp; identity check…
          </div>
        )}

        {inCapture && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/70">
            <div className="text-center">
              <div className="text-emerald-400 font-semibold text-sm">Verification Complete</div>
              <div className="text-[11px] text-slate-300 mt-1">Capturing your photo…</div>
            </div>
          </div>
        )}

        {liveness.guidance && liveness.modelState === 'ready' && !inCapture && (
          <div className="absolute bottom-0 inset-x-0 bg-black/70 text-white text-xs text-center py-2 px-3">
            {liveness.guidance}
          </div>
        )}

        {liveness.stepPhase === 'completed' && !inCapture && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/50">
            <div className="text-emerald-400 font-semibold">✓ {stepMeta.verified}</div>
          </div>
        )}
      </div>

      {liveness.cameraError && <div className="text-xs text-red-300 text-center">{liveness.cameraError}</div>}

      {!inCapture && liveness.modelState === 'ready' && (
        <>
          <div className="text-center">
            <div className="font-semibold text-white">{stepMeta.instruction}</div>
            <p className="text-xs text-slate-400 mt-0.5">{stepMeta.detail}</p>
          </div>

          {/* progress bar for the current step's movement */}
          <div className="h-1.5 rounded-full bg-white/10 overflow-hidden max-w-xs mx-auto">
            <div className="h-full bg-cyan-400 transition-all" style={{ width: `${Math.round(liveness.stepProgress * 100)}%` }} />
          </div>

          {/* step dots -- ● current/done, ○ upcoming */}
          <div className="flex items-center justify-center gap-2">
            {liveness.steps.map((s, i) => (
              <span key={s.id} className={`text-lg leading-none ${i <= liveness.stepIndex ? 'text-cyan-400' : 'text-white/25'}`}>
                {i <= liveness.stepIndex ? '●' : '○'}
              </span>
            ))}
          </div>
          <p className="text-[11px] text-slate-500 text-center">Step {liveness.stepIndex + 1} of {liveness.steps.length}</p>

          {liveness.retryNotice && (
            <div className="text-center space-y-1.5">
              <div className="text-xs text-orange-300">{liveness.retryNotice}</div>
              <button type="button" onClick={liveness.retryStep}
                className="text-xs font-semibold bg-white/10 hover:bg-white/20 border border-white/20 px-4 py-1.5 rounded-lg">
                Try Again
              </button>
            </div>
          )}
        </>
      )}

      <div className="text-center">
        <button type="button" onClick={() => { liveness.cancel(); onCancel?.() }}
          className="text-xs text-slate-400 hover:text-slate-200">
          Cancel and use a plain photo instead
        </button>
      </div>
    </div>
  )
}

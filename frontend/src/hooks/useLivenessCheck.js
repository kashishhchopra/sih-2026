import { useCallback, useEffect, useRef, useState } from 'react'
import {
  STEPS, loadFaceLandmarkerWithTimeout, computeFaceSignals, computeFaceBox,
  positionGuidance, sampleBrightness, sharpnessScore,
} from '../lib/liveness.js'

// Tunables for the movement checks. See lib/liveness.js's header for why
// these thresholds are compared against a per-step baseline rather than an
// absolute "turned right = positive" direction.
const YAW_THRESHOLD = 0.05
const PITCH_THRESHOLD = 0.045
const NOD_THRESHOLD = 0.035
const DOMINANCE_RATIO = 1.25 // the intended axis must move clearly more than the other
const SUSTAIN_FRAMES = 4 // consecutive frames past threshold, to filter jitter/single-frame noise
const CALIBRATION_FRAMES = 8 // stable frames needed before trusting a baseline
const CALIBRATION_VARIANCE_MAX = 0.0004 // a settled face, not mid-motion, before locking a baseline
const STEP_TIMEOUT_MS = 14000
const DETECT_INTERVAL_MS = 90 // ~11 fps -- plenty for slow, deliberate head movement

// The per-frame detection loop is a requestAnimationFrame recursion that
// must survive for the component's whole lifetime without React ever
// re-creating it -- if it depended on step/phase state via closure, every
// state update would leave the ALREADY-SCHEDULED frame still holding the
// old values (a classic stale-closure bug: the loop would keep checking
// against step 1 forever after advancing to step 2). So every value the
// loop reads across frames lives in a ref, not in React state; state exists
// only to drive what's rendered, and the loop only ever *writes* to it.
export default function useLivenessCheck({ onUnavailable } = {}) {
  const videoRef = useRef(null)
  const brightnessCanvasRef = useRef(document.createElement('canvas'))
  const streamRef = useRef(null)
  const landmarkerRef = useRef(null)
  const rafRef = useRef(null)
  const lastDetectAtRef = useRef(0)

  // ---- loop state (refs = source of truth for the running detection loop) --
  const stepIndexRef = useRef(0)
  const nodPhaseRef = useRef(null) // null | 'down'
  const nodDirectionRef = useRef(0)
  const baselineRef = useRef(null)
  const calibrationWindowRef = useRef([])
  const sustainedRef = useRef(0)
  const peakDeltaRef = useRef(0)
  const stepStartedAtRef = useRef(0)
  const stepScoresRef = useRef([])
  const overallPhaseRef = useRef('checking')
  // Guards completeStep() against firing more than once per step. The
  // movement threshold, once crossed, typically STAYS crossed for many
  // more frames (the tourist naturally holds the pose for a moment) --
  // without this, every one of those frames re-fired completeStep(),
  // each scheduling its own 900ms advance, and several overlapping
  // advances landing together raced stepIndex through step 2 and 3
  // almost instantly, skipping straight to the capture screen.
  const completingRef = useRef(false)
  const sessionIdRef = useRef(`sess-${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`)

  // ---- render state ----------------------------------------------------
  const [modelState, setModelState] = useState('loading') // loading | ready | unavailable
  const [guidance, setGuidance] = useState('No face detected. Please position yourself inside the frame.')
  const [faceBox, setFaceBox] = useState(null)
  const [stepIndex, setStepIndexState] = useState(0)
  const [stepPhase, setStepPhase] = useState('waiting') // waiting | face_detected | movement_detected | completed
  const [stepProgress, setStepProgress] = useState(0)
  const [retryNotice, setRetryNotice] = useState('')
  const [overallPhase, setOverallPhaseState] = useState('checking') // checking|in_progress|capturing|complete|unavailable
  // Wraps the setter so overallPhaseRef (read by the RAF loop, which
  // never reads React state directly -- see file header) updates in the
  // same tick as the state, with no gap for a race between the two.
  const setOverallPhase = useCallback((phase) => {
    overallPhaseRef.current = phase
    setOverallPhaseState(phase)
  }, [])
  const [finalPhoto, setFinalPhoto] = useState(null)
  const [livenessScore, setLivenessScore] = useState(null)
  const [cameraError, setCameraError] = useState('')

  const stop = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
  }, [])

  const resetStepTracking = useCallback(() => {
    completingRef.current = false
    baselineRef.current = null
    calibrationWindowRef.current = []
    sustainedRef.current = 0
    peakDeltaRef.current = 0
    nodPhaseRef.current = null
    nodDirectionRef.current = 0
    stepStartedAtRef.current = Date.now()
    setStepPhase('waiting')
    setStepProgress(0)
    setRetryNotice('')
  }, [])

  const retryStep = useCallback(() => resetStepTracking(), [resetStepTracking])

  const goToNextStepOrFinish = useCallback(() => {
    if (stepIndexRef.current < STEPS.length - 1) {
      stepIndexRef.current += 1
      setStepIndexState(stepIndexRef.current)
      resetStepTracking()
    } else {
      setOverallPhase('capturing')
    }
  }, [resetStepTracking])

  const completeStep = useCallback(() => {
    if (completingRef.current) return
    completingRef.current = true
    const i = stepIndexRef.current
    const elapsed = Date.now() - stepStartedAtRef.current
    // A step cleared far too fast to be a deliberate human motion is scored
    // lower rather than rejected outright -- rewards natural movement
    // without hard-failing a fast-but-genuine one.
    const timingFactor = elapsed < 150 ? 0.6 : 1
    const threshold = STEPS[i].axis === 'yaw' ? YAW_THRESHOLD
      : STEPS[i].axis === 'pitch' ? PITCH_THRESHOLD : NOD_THRESHOLD
    const magnitudeFactor = Math.min(1, peakDeltaRef.current / (threshold * 1.6))
    stepScoresRef.current[i] = magnitudeFactor * timingFactor

    setStepPhase('completed')
    setStepProgress(1)
    setTimeout(goToNextStepOrFinish, 900) // let the "✓ verified" message be readable
  }, [goToNextStepOrFinish])

  // ---- capture the best of a few frames once verification is complete ----
  const captureBestFrame = useCallback(() => {
    const video = videoRef.current
    if (!video) return
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')

    let samples = 0
    let attempts = 0
    let best = null
    const finish = () => {
      stop()
      if (best) {
        setFinalPhoto(best.dataUrl)
        const avgStepScore = stepScoresRef.current.length
          ? stepScoresRef.current.reduce((a, b) => a + b, 0) / stepScoresRef.current.length
          : 0
        // Floor at 0.6: every step that reaches here already cleared its
        // real movement threshold, so the score communicates *quality*
        // above the pass bar -- it never drops below what a genuine pass
        // means.
        setLivenessScore(Math.min(0.97, 0.6 + 0.37 * avgStepScore))
        setOverallPhase('complete')
      } else {
        // The video feed disappeared before a single usable frame could be
        // captured (e.g. the stream ended mid-capture) -- treat this as a
        // retry on the last step rather than crashing or hanging silently.
        stepIndexRef.current = STEPS.length - 1
        setStepIndexState(stepIndexRef.current)
        resetStepTracking() // clears retryNotice too -- must run before setting the message below
        setRetryNotice("We couldn't capture your photo. Please try again.")
        setOverallPhase('in_progress')
        rafRef.current = requestAnimationFrame(tick)
      }
    }
    const grab = () => {
      // The video's reported dimensions can transiently read 0 (a stream
      // ending, a tab backgrounding, or simply a frame boundary) -- drawing
      // FROM a 0x0 source throws, so this is checked on every attempt
      // rather than sized once outside the loop. A few retries cover a
      // transient dip; a video that never recovers ends the capture
      // gracefully via `finish()` instead of throwing.
      if (!video.videoWidth || !video.videoHeight) {
        attempts += 1
        if (attempts < 15) { setTimeout(grab, 100); return }
        finish()
        return
      }
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
      ctx.drawImage(video, 0, 0)
      const brightness = sampleBrightness(
        video, { x: 0.2, y: 0.15, width: 0.6, height: 0.7 }, brightnessCanvasRef.current
      ) || 0
      const sharpness = sharpnessScore(canvas)
      // Brightness close to a comfortable mid-range plus sharpness -- both
      // real, both measured, combined into one pick-the-best-frame score.
      const brightnessScore = 1 - Math.min(1, Math.abs(brightness - 150) / 150)
      const score = sharpness * 0.7 + brightnessScore * 60
      if (!best || score > best.score) {
        best = { score, dataUrl: canvas.toDataURL('image/jpeg', 0.92) }
      }
      samples += 1
      if (samples < 5) {
        setTimeout(grab, 120)
        return
      }
      finish()
    }
    grab()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stop, resetStepTracking])

  useEffect(() => {
    if (overallPhase === 'capturing') captureBestFrame()
  }, [overallPhase, captureBestFrame])

  // ---- per-frame detection loop (created once; reads/writes refs only) ---
  const tick = useCallback((now) => {
    if (overallPhaseRef.current !== 'in_progress') return // capture/complete/cancelled -- let the loop end
    rafRef.current = requestAnimationFrame(tick)
    const video = videoRef.current
    const landmarker = landmarkerRef.current
    if (!video || !landmarker || video.readyState < 2) return
    if (now - lastDetectAtRef.current < DETECT_INTERVAL_MS) return
    lastDetectAtRef.current = now

    let result
    try {
      result = landmarker.detectForVideo(video, now)
    } catch {
      return // a transient decode hiccup -- just wait for the next frame
    }
    const faces = result?.faceLandmarks || []
    const faceCount = faces.length

    if (faceCount !== 1) {
      setFaceBox(null)
      setGuidance(positionGuidance({ faceCount, box: { x: 0.5, y: 0.5, width: 0, height: 0 } }))
      setStepPhase('waiting')
      return
    }

    const landmarks = faces[0]
    const box = computeFaceBox(landmarks)
    setFaceBox(box)
    const brightness = sampleBrightness(video, box, brightnessCanvasRef.current)
    const guide = positionGuidance({ faceCount, box, brightness })
    setGuidance(guide)
    if (guide) {
      setStepPhase('waiting')
      return
    }

    const { yawSignal, pitchSignal } = computeFaceSignals(landmarks)

    // Calibrate a neutral baseline from a short run of stable frames before
    // trusting any delta -- this is what stops a static held-up photo (or
    // the very first frame, mid-repositioning) from ever registering as
    // "movement": there IS no movement to measure against yet.
    if (!baselineRef.current) {
      setStepPhase('face_detected')
      if (!stepStartedAtRef.current) stepStartedAtRef.current = Date.now()
      const win = calibrationWindowRef.current
      win.push({ yaw: yawSignal, pitch: pitchSignal })
      if (win.length > CALIBRATION_FRAMES) win.shift()
      if (win.length === CALIBRATION_FRAMES) {
        const meanYaw = win.reduce((a, p) => a + p.yaw, 0) / win.length
        const meanPitch = win.reduce((a, p) => a + p.pitch, 0) / win.length
        const varYaw = win.reduce((a, p) => a + (p.yaw - meanYaw) ** 2, 0) / win.length
        const varPitch = win.reduce((a, p) => a + (p.pitch - meanPitch) ** 2, 0) / win.length
        if (varYaw < CALIBRATION_VARIANCE_MAX && varPitch < CALIBRATION_VARIANCE_MAX) {
          baselineRef.current = { yaw: meanYaw, pitch: meanPitch }
        }
      }
      if (Date.now() - stepStartedAtRef.current > STEP_TIMEOUT_MS) {
        setRetryNotice("We couldn't detect the movement. Please try again.")
        resetStepTracking()
      }
      return
    }

    const dYaw = yawSignal - baselineRef.current.yaw
    const dPitch = pitchSignal - baselineRef.current.pitch
    const axis = STEPS[stepIndexRef.current].axis

    if (axis === 'nod') {
      // Two real phases, in order: pitch moves away from neutral past the
      // threshold (phase A -- direction doesn't matter, whichever way the
      // tourist's chin actually goes first), then swings back past neutral
      // in the OPPOSITE direction by a comparable margin (phase B). A
      // single-direction drift, or a static held-up photo, can only ever
      // satisfy phase A, never both -- that's what makes this check an
      // actual nod and not just "did pitch change at all".
      const magnitude = Math.abs(dPitch)
      if (nodPhaseRef.current !== 'down') {
        if (magnitude > NOD_THRESHOLD) {
          sustainedRef.current += 1
          if (sustainedRef.current >= SUSTAIN_FRAMES) {
            nodDirectionRef.current = Math.sign(dPitch)
            peakDeltaRef.current = Math.max(peakDeltaRef.current, magnitude)
            nodPhaseRef.current = 'down'
            setStepPhase('movement_detected')
            setStepProgress(0.5)
            sustainedRef.current = 0
          }
        } else {
          sustainedRef.current = 0
        }
      } else {
        const swungBack = Math.sign(dPitch) === -nodDirectionRef.current && magnitude > NOD_THRESHOLD * 0.7
        if (swungBack) {
          sustainedRef.current += 1
          peakDeltaRef.current = Math.max(peakDeltaRef.current, magnitude)
          if (sustainedRef.current >= SUSTAIN_FRAMES) completeStep()
        } else {
          sustainedRef.current = 0
        }
      }
    } else {
      const primary = axis === 'yaw' ? dYaw : dPitch
      const other = axis === 'yaw' ? dPitch : dYaw
      const magnitude = Math.abs(primary)
      const threshold = axis === 'yaw' ? YAW_THRESHOLD : PITCH_THRESHOLD
      const isDominant = magnitude > Math.abs(other) * DOMINANCE_RATIO
      setStepPhase('movement_detected')
      setStepProgress(Math.min(1, magnitude / threshold))
      if (magnitude > threshold && isDominant) {
        sustainedRef.current += 1
        peakDeltaRef.current = Math.max(peakDeltaRef.current, magnitude)
        if (sustainedRef.current >= SUSTAIN_FRAMES) completeStep()
      } else {
        sustainedRef.current = 0
      }
    }

    if (Date.now() - stepStartedAtRef.current > STEP_TIMEOUT_MS) {
      setRetryNotice("We couldn't detect the movement. Please try again.")
      resetStepTracking()
    }
  }, [completeStep, resetStepTracking])

  const startCameraAndLoop = useCallback((landmarker) => {
    landmarkerRef.current = landmarker
    return navigator.mediaDevices?.getUserMedia({ video: { facingMode: 'user' } }).then((stream) => {
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        videoRef.current.play()
      }
      setOverallPhase('in_progress')
      stepStartedAtRef.current = Date.now()
      rafRef.current = requestAnimationFrame(tick)
    })
  }, [tick])

  // ---- lifecycle: load model + camera, start the loop ---------------------
  useEffect(() => {
    let cancelled = false
    setOverallPhase('checking')
    loadFaceLandmarkerWithTimeout()
      .then((landmarker) => {
        if (cancelled) return null
        return startCameraAndLoop(landmarker)
      })
      .then(() => {
        if (!cancelled) setModelState('ready')
      })
      .catch((err) => {
        if (cancelled) return
        // Surfaced in devtools so a real failure (network/GPU/permission)
        // is diagnosable instead of silently landing on "unavailable".
        console.error('Liveness check could not start; falling back to plain photo capture.', err)
        setModelState('unavailable')
        setOverallPhase('unavailable')
        if (err?.name === 'NotAllowedError') {
          setCameraError('Camera access is required to verify your identity. Please allow camera access and retry.')
        } else if (err?.name === 'NotFoundError') {
          setCameraError('No camera was found on this device.')
        }
        onUnavailable?.(err)
      })
    return () => {
      cancelled = true
      stop()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const retakeAll = useCallback(() => {
    stepScoresRef.current = []
    stepIndexRef.current = 0
    setStepIndexState(0)
    setFinalPhoto(null)
    setLivenessScore(null)
    resetStepTracking()
    setOverallPhase('checking')
    loadFaceLandmarkerWithTimeout()
      .then((landmarker) => startCameraAndLoop(landmarker))
      .then(() => setModelState('ready'))
      .catch((err) => {
        setModelState('unavailable')
        setOverallPhase('unavailable')
        onUnavailable?.(err)
      })
  }, [resetStepTracking, startCameraAndLoop, onUnavailable])

  return {
    videoRef,
    modelState,
    overallPhase,
    guidance,
    faceBox,
    steps: STEPS,
    stepIndex,
    stepPhase,
    stepProgress,
    retryNotice,
    finalPhoto,
    livenessScore,
    cameraError,
    sessionId: sessionIdRef.current,
    completedStepIds: STEPS.slice(0, overallPhase === 'complete' || overallPhase === 'capturing' ? STEPS.length : stepIndex)
      .map((s) => s.id),
    retryStep,
    cancel: stop,
    retakeAll,
  }
}

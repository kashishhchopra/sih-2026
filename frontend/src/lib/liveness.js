// Real, in-browser 3-step active-liveness check for tourist registration --
// no server round-trip per frame, no video ever leaves the device. Uses
// MediaPipe's Face Landmarker (WASM + a small pretrained model, fetched
// once and cached by the browser) to get 478 real 3D face landmarks per
// frame from the live camera feed, then simple, self-referential geometry
// on those points to detect real head movement.
//
// Why geometry on raw landmarks instead of MediaPipe's own
// facial-transformation-matrix (which would give a "proper" yaw/pitch/roll
// in degrees): decoding that matrix correctly depends on an axis/handedness
// convention we cannot verify without a live camera and a human moving
// their head in front of it, which this environment cannot do. Getting an
// axis sign backwards there would silently invert "turn right" and "look
// up". The approach here sidesteps that risk entirely: every check is
// self-referential to a baseline captured at the start of that step (a
// ratio moving away from *its own* neutral value), so it works correctly
// regardless of that convention -- see STEPS/thresholds below for exactly
// what each one verifies, and the docstring on `computeFaceSignals`.
//
// This module is pure logic (no React) so it's unit-testable and so the
// hook (./hooks/useLivenessCheck.js) stays about state, not geometry.

export const STEPS = [
  {
    id: 'turn_right',
    axis: 'yaw',
    instruction: 'Turn your head to the right',
    detail: 'Slowly turn your head to the right and look toward your shoulder.',
    verified: 'Head movement verified',
  },
  {
    id: 'look_up',
    axis: 'pitch',
    instruction: 'Look slightly upward',
    detail: 'Keep your face inside the frame and slowly look upward.',
    verified: 'Upward movement verified',
  },
  {
    id: 'nod',
    axis: 'nod',
    instruction: 'Please nod your head',
    detail: 'Slowly nod once.',
    verified: 'Liveness verified',
  },
]

// ---- MediaPipe FaceLandmarker: lazy singleton -----------------------------
// Loaded once per page (not once per component mount) since the WASM
// runtime + model download take a couple of seconds -- reusing it makes
// "retake" / a second registration attempt instant.
let _landmarkerPromise = null

const MODEL_URL =
  'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'
const WASM_URL = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm'

async function _createLandmarker(FaceLandmarker, filesetResolver, delegate) {
  return FaceLandmarker.createFromOptions(filesetResolver, {
    baseOptions: { modelAssetPath: MODEL_URL, delegate },
    runningMode: 'VIDEO',
    numFaces: 2, // exactly enough to tell "one face" from "more than one"
    minFaceDetectionConfidence: 0.5,
    minFacePresenceConfidence: 0.5,
    minTrackingConfidence: 0.5,
  })
}

export function loadFaceLandmarker() {
  if (!_landmarkerPromise) {
    _landmarkerPromise = (async () => {
      const { FaceLandmarker, FilesetResolver } = await import('@mediapipe/tasks-vision')
      const filesetResolver = await FilesetResolver.forVisionTasks(WASM_URL)
      // Not every browser/GPU combination supports MediaPipe's WebGL
      // delegate reliably (Safari and some integrated-GPU/sandboxed setups
      // are known to reject it) -- try GPU first for speed, and silently
      // retry once on the CPU delegate rather than failing the whole
      // registration flow over an accelerator that just isn't available.
      try {
        return await _createLandmarker(FaceLandmarker, filesetResolver, 'GPU')
      } catch (gpuErr) {
        console.warn('Liveness: GPU delegate failed, retrying on CPU.', gpuErr)
        return await _createLandmarker(FaceLandmarker, filesetResolver, 'CPU')
      }
    })().catch((err) => {
      _landmarkerPromise = null // let a later retry try loading again
      console.error('Liveness: face landmarker failed to load.', err)
      throw err
    })
  }
  return _landmarkerPromise
}

/** Race model loading against a timeout so a slow/blocked network never
 * leaves the registration flow stuck -- the caller falls back to the
 * existing plain live-capture step instead. */
export function loadFaceLandmarkerWithTimeout(timeoutMs = 16000) {
  return Promise.race([
    loadFaceLandmarker(),
    new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), timeoutMs)),
  ])
}

// ---- landmark indices (standard MediaPipe Face Mesh topology) ------------
const NOSE_TIP = 1
const CHIN = 152
const LEFT_EYE_OUTER = 33
const RIGHT_EYE_OUTER = 263
const CHEEK_A = 234 // one side of the face, near the ear
const CHEEK_B = 454 // the other side -- see file header for why we don't
// need to know, and don't assert, which of these is the tourist's
// anatomical left vs right.

function dist(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y)
}
function mid(a, b) {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
}

/**
 * Turns one frame's 468/478 raw landmarks (normalized 0..1 image
 * coordinates) into two scale-invariant signals:
 *
 *  - yawSignal:   (distance nose->cheekA - distance nose->cheekB) / their sum.
 *                 ~0 facing the camera; swings toward +1 or -1 as the head
 *                 turns, because the near-side cheek foreshortens toward
 *                 the nose while the far-side one doesn't.
 *  - pitchSignal: vertical position of the nose tip relative to the
 *                 eye-line, normalized by eye-line-to-chin distance so it
 *                 doesn't change just because the tourist moved closer to
 *                 or further from the camera.
 *
 * Both are ratios (scale cancels out of the arithmetic), so they read the
 * same regardless of how far the face is from the camera or how large the
 * face is on screen -- only genuine head rotation moves them.
 */
export function computeFaceSignals(landmarks) {
  const nose = landmarks[NOSE_TIP]
  const cheekA = landmarks[CHEEK_A]
  const cheekB = landmarks[CHEEK_B]
  const distA = dist(nose, cheekA)
  const distB = dist(nose, cheekB)
  const yawSignal = (distA - distB) / (distA + distB || 1)

  const eyeMid = mid(landmarks[LEFT_EYE_OUTER], landmarks[RIGHT_EYE_OUTER])
  const chin = landmarks[CHIN]
  const faceHeight = dist(eyeMid, chin) || 1
  const pitchSignal = (nose.y - eyeMid.y) / faceHeight

  return { yawSignal, pitchSignal }
}

/** Bounding box of the face in normalized (0..1) coordinates, for the
 * on-screen face frame and the too-close/far/off-center guidance. */
export function computeFaceBox(landmarks) {
  let minX = 1, minY = 1, maxX = 0, maxY = 0
  for (const p of landmarks) {
    if (p.x < minX) minX = p.x
    if (p.y < minY) minY = p.y
    if (p.x > maxX) maxX = p.x
    if (p.y > maxY) maxY = p.y
  }
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY }
}

// ---- position/lighting guidance thresholds --------------------------------
export const FACE_SIZE_MIN = 0.22 // face width < 22% of frame -> too far
export const FACE_SIZE_MAX = 0.75 // > 75% of frame -> too close
export const CENTER_OFFSET_MAX = 0.18 // face-box center vs frame center
export const MIN_BRIGHTNESS = 60 // 0-255 average luma of the face region

/** Plain-language guidance for the current frame, or null when position and
 * lighting are good enough to track movement against. Priority order
 * matches the spec: no-face, multiple-faces, lighting, distance, centering. */
export function positionGuidance({ faceCount, box, brightness }) {
  if (faceCount === 0) return 'No face detected. Please position yourself inside the frame.'
  if (faceCount > 1) return 'Please make sure only one person is visible.'
  if (brightness != null && brightness < MIN_BRIGHTNESS) return 'Please move to a better-lit area.'
  if (box.width < FACE_SIZE_MIN) return 'Move closer to the camera'
  if (box.width > FACE_SIZE_MAX) return 'Move slightly away'
  const cx = box.x + box.width / 2
  const cy = box.y + box.height / 2
  if (Math.abs(cx - 0.5) > CENTER_OFFSET_MAX || Math.abs(cy - 0.5) > CENTER_OFFSET_MAX) {
    return 'Center your face'
  }
  return null
}

/** Average luma (perceived brightness, 0-255) of a region of a video frame
 * -- a real signal read from real pixels, standing in for a light meter no
 * browser exposes. `box` is normalized (0..1) coordinates. */
export function sampleBrightness(video, box, canvas) {
  const vw = video.videoWidth, vh = video.videoHeight
  if (!vw || !vh) return null
  const sx = Math.max(0, box.x * vw), sy = Math.max(0, box.y * vh)
  const sw = Math.min(vw - sx, box.width * vw), sh = Math.min(vh - sy, box.height * vh)
  if (sw < 4 || sh < 4) return null
  canvas.width = 24
  canvas.height = 24
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  ctx.drawImage(video, sx, sy, sw, sh, 0, 0, 24, 24)
  const { data } = ctx.getImageData(0, 0, 24, 24)
  let sum = 0
  for (let i = 0; i < data.length; i += 4) {
    sum += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]
  }
  return sum / (data.length / 4)
}

/** Lightweight blur-detection proxy: average local gradient magnitude on a
 * downsampled grayscale copy. Real signal from real pixels (a simplified,
 * cheap cousin of the standard Laplacian-variance sharpness metric) --
 * higher means sharper; a near-zero value means an essentially flat/blurry
 * image. Only run once, on the final captured frame -- not per-frame. */
export function sharpnessScore(canvas) {
  const w = 96, h = Math.round((canvas.height / canvas.width) * 96) || 96
  const tmp = document.createElement('canvas')
  tmp.width = w
  tmp.height = h
  const ctx = tmp.getContext('2d', { willReadFrequently: true })
  ctx.drawImage(canvas, 0, 0, w, h)
  const { data } = ctx.getImageData(0, 0, w, h)
  const gray = new Float32Array(w * h)
  for (let i = 0, p = 0; i < data.length; i += 4, p++) {
    gray[p] = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]
  }
  let energy = 0
  for (let y = 0; y < h - 1; y++) {
    for (let x = 0; x < w - 1; x++) {
      const idx = y * w + x
      energy += Math.abs(gray[idx + 1] - gray[idx]) + Math.abs(gray[idx + w] - gray[idx])
    }
  }
  return energy / (w * h)
}

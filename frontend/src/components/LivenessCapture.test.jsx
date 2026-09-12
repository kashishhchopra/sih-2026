import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import api from '../api'
import LivenessCapture from './LivenessCapture.jsx'

// ---- a controllable fake FaceLandmarker + rAF queue ------------------------
// Lets tests drive the real detection loop (hooks/useLivenessCheck.js) frame
// by frame with synthetic-but-real landmark geometry, instead of needing an
// actual camera/GPU -- the geometry itself is exercised for real; only the
// camera/model plumbing around it is faked.
const { mockDetectForVideo, mockLandmarker } = vi.hoisted(() => {
  const mockDetectForVideo = vi.fn().mockReturnValue({ faceLandmarks: [] })
  return { mockDetectForVideo, mockLandmarker: { detectForVideo: mockDetectForVideo } }
})

vi.mock('@mediapipe/tasks-vision', () => ({
  FilesetResolver: { forVisionTasks: vi.fn().mockResolvedValue({}) },
  FaceLandmarker: { createFromOptions: vi.fn().mockResolvedValue(mockLandmarker) },
}))

const mock = new MockAdapter(api)

let rafQueue = []
function runFrame(now) {
  const cb = rafQueue.shift()
  cb?.(now)
}

// A full 478-point array with only the indices the geometry actually reads
// populated -- see lib/liveness.test.js for the same fixture shape.
function landmarksAt({ noseX = 0.5, noseY = 0.55 } = {}) {
  const pts = new Array(478).fill(0).map(() => ({ x: 0.5, y: 0.5, z: 0 }))
  pts[1] = { x: noseX, y: noseY, z: 0 }
  pts[152] = { x: 0.5, y: 0.85, z: 0 }
  pts[33] = { x: 0.35, y: 0.4, z: 0 }
  pts[263] = { x: 0.65, y: 0.4, z: 0 }
  pts[234] = { x: 0.3, y: 0.55, z: 0 }
  pts[454] = { x: 0.7, y: 0.55, z: 0 }
  return pts
}
const NEUTRAL = landmarksAt()
const TURNED = landmarksAt({ noseX: 0.4 }) // clears the yaw threshold, ~0 pitch delta
const LOOKED_UP = landmarksAt({ noseY: 0.45 }) // clears the pitch threshold, ~0 yaw delta
const NOD_DOWN = landmarksAt({ noseY: 0.45 })
const NOD_UP = landmarksAt({ noseY: 0.6 })

function setFaces(landmarks) {
  mockDetectForVideo.mockReturnValue({ faceLandmarks: landmarks ? [landmarks] : [] })
}

/** Feed one synthetic frame through the running loop. Timestamps step by
 * >90ms (DETECT_INTERVAL_MS) so every call actually reaches detection. */
let frameNow = 0
async function feedFrame(landmarks) {
  setFaces(landmarks)
  frameNow += 100
  await act(async () => runFrame(frameNow))
}
async function feedFrames(landmarks, count) {
  for (let i = 0; i < count; i++) await feedFrame(landmarks)
}

beforeEach(() => {
  mock.reset()
  vi.clearAllMocks()
  rafQueue = []
  frameNow = 0
  mockDetectForVideo.mockReturnValue({ faceLandmarks: [] })
  global.requestAnimationFrame = (cb) => { rafQueue.push(cb); return rafQueue.length }
  global.cancelAnimationFrame = () => {}

  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [] }) },
  })
  HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue()
  Object.defineProperty(HTMLMediaElement.prototype, 'readyState', { configurable: true, get: () => 4 })
  // videoWidth/videoHeight are spec'd (and jsdom implements them) on
  // HTMLVideoElement, not the parent HTMLMediaElement -- mocking the wrong
  // prototype leaves jsdom's own always-0 getter in place, silently, which
  // is exactly the "video reports 0x0" case exercised deliberately in the
  // fallback test below.
  Object.defineProperties(HTMLVideoElement.prototype, {
    videoWidth: { configurable: true, get: () => 640 },
    videoHeight: { configurable: true, get: () => 480 },
  })
  HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
    drawImage: vi.fn(),
    getImageData: vi.fn().mockReturnValue({ data: new Uint8ClampedArray(400).fill(150) }),
  })
  HTMLCanvasElement.prototype.toDataURL = vi.fn().mockReturnValue('data:image/jpeg;base64,captured')
})

async function waitForCameraReady() {
  await waitFor(() => expect(screen.getByText('Turn your head to the right')).toBeInTheDocument())
}

describe('LivenessCapture', () => {
  it('shows the identity-verification intro and starts the camera/model', async () => {
    render(<LivenessCapture onCapture={vi.fn()} onCancel={vi.fn()} onUnavailable={vi.fn()} />)
    expect(screen.getByText('Verify Your Identity')).toBeInTheDocument()
    await waitForCameraReady()
    expect(screen.getByText('Step 1 of 3')).toBeInTheDocument()
  })

  it('shows guidance when no face is visible, and clears it once one appears', async () => {
    render(<LivenessCapture onCapture={vi.fn()} onCancel={vi.fn()} onUnavailable={vi.fn()} />)
    await waitForCameraReady()
    await feedFrame(null)
    expect(screen.getByText(/No face detected/)).toBeInTheDocument()

    await feedFrames(NEUTRAL, 8) // calibration window
    await waitFor(() => expect(screen.queryByText(/No face detected/)).not.toBeInTheDocument())
  })

  it('flags more than one face', async () => {
    render(<LivenessCapture onCapture={vi.fn()} onCancel={vi.fn()} onUnavailable={vi.fn()} />)
    await waitForCameraReady()
    setFaces(null)
    mockDetectForVideo.mockReturnValue({ faceLandmarks: [NEUTRAL, NEUTRAL] })
    frameNow += 100
    await act(async () => runFrame(frameNow))
    expect(screen.getByText(/only one person/)).toBeInTheDocument()
  })

  it('does not complete a step for a static face -- no movement, no pass', async () => {
    render(<LivenessCapture onCapture={vi.fn()} onCancel={vi.fn()} onUnavailable={vi.fn()} />)
    await waitForCameraReady()
    // Calibrate, then keep feeding the exact same (neutral) frame -- a
    // static held-up photo has no baseline-relative movement to detect.
    await feedFrames(NEUTRAL, 8)
    await feedFrames(NEUTRAL, 10)
    expect(screen.getByText('Turn your head to the right')).toBeInTheDocument()
  })

  it('completes the real 3-step sequence and produces a captured photo', async () => {
    const onCapture = vi.fn()
    mock.onPost('/tourists/verify-liveness').reply(200, { verification_token: 'tok-123' })
    render(<LivenessCapture onCapture={onCapture} onCancel={vi.fn()} onUnavailable={vi.fn()} />)
    await waitForCameraReady()

    // Step 1: turn right (yaw).
    await feedFrames(NEUTRAL, 8)
    await feedFrames(TURNED, 4)
    await waitFor(() => expect(screen.getByText('✓ Head movement verified')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('Look slightly upward')).toBeInTheDocument(), { timeout: 2000 })

    // Step 2: look up (pitch).
    await feedFrames(NEUTRAL, 8)
    await feedFrames(LOOKED_UP, 4)
    await waitFor(() => expect(screen.getByText('✓ Upward movement verified')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('Please nod your head')).toBeInTheDocument(), { timeout: 2000 })

    // Step 3: nod -- down, then back up past neutral.
    await feedFrames(NEUTRAL, 8)
    await feedFrames(NOD_DOWN, 4)
    await feedFrames(NOD_UP, 4)
    await waitFor(() => expect(screen.getByText('✓ Liveness verified')).toBeInTheDocument())

    await waitFor(() => expect(screen.getByText('✓ Identity Photo Verified')).toBeInTheDocument(), { timeout: 3000 })
    expect(screen.getByAltText('Your profile')).toHaveAttribute('src', 'data:image/jpeg;base64,captured')

    fireEvent.click(screen.getByText('Use Photo'))
    await waitFor(() => expect(onCapture).toHaveBeenCalledWith(
      'data:image/jpeg;base64,captured', { livenessToken: 'tok-123' }
    ))
    const sent = JSON.parse(mock.history.post[0].data)
    expect(sent.steps).toEqual(['turn_right', 'look_up', 'nod'])
  }, 15000)

  it('lets the tourist retake after completion, without calling onCapture', async () => {
    mock.onPost('/tourists/verify-liveness').reply(200, { verification_token: 'tok-456' })
    render(<LivenessCapture onCapture={vi.fn()} onCancel={vi.fn()} onUnavailable={vi.fn()} />)
    await waitForCameraReady()
    await feedFrames(NEUTRAL, 8)
    await feedFrames(TURNED, 4)
    await waitFor(() => screen.getByText('Look slightly upward'), { timeout: 2000 })
    await feedFrames(NEUTRAL, 8)
    await feedFrames(LOOKED_UP, 4)
    await waitFor(() => screen.getByText('Please nod your head'), { timeout: 2000 })
    await feedFrames(NEUTRAL, 8)
    await feedFrames(NOD_DOWN, 4)
    await feedFrames(NOD_UP, 4)
    await waitFor(() => expect(screen.getByText('✓ Identity Photo Verified')).toBeInTheDocument(), { timeout: 3000 })

    fireEvent.click(screen.getByText('Retake'))
    await waitFor(() => expect(screen.getByText('Verify Your Identity')).toBeInTheDocument())
    await waitForCameraReady() // back to step 1
  }, 15000)

  it('still lets the tourist proceed with the photo if the backend call fails', async () => {
    const onCapture = vi.fn()
    mock.onPost('/tourists/verify-liveness').reply(500)
    render(<LivenessCapture onCapture={onCapture} onCancel={vi.fn()} onUnavailable={vi.fn()} />)
    await waitForCameraReady()
    await feedFrames(NEUTRAL, 8)
    await feedFrames(TURNED, 4)
    await waitFor(() => screen.getByText('Look slightly upward'), { timeout: 2000 })
    await feedFrames(NEUTRAL, 8)
    await feedFrames(LOOKED_UP, 4)
    await waitFor(() => screen.getByText('Please nod your head'), { timeout: 2000 })
    await feedFrames(NEUTRAL, 8)
    await feedFrames(NOD_DOWN, 4)
    await feedFrames(NOD_UP, 4)
    await waitFor(() => expect(screen.getByText('✓ Identity Photo Verified')).toBeInTheDocument(), { timeout: 3000 })

    fireEvent.click(screen.getByText('Use Photo'))
    await waitFor(() => expect(onCapture).toHaveBeenCalledWith(
      'data:image/jpeg;base64,captured', { livenessToken: null }
    ))
  }, 15000)

  it('calls onUnavailable and renders nothing when the camera is denied', async () => {
    const onUnavailable = vi.fn()
    navigator.mediaDevices.getUserMedia = vi.fn().mockRejectedValue(
      Object.assign(new Error('denied'), { name: 'NotAllowedError' })
    )
    const { container } = render(<LivenessCapture onCapture={vi.fn()} onCancel={vi.fn()} onUnavailable={onUnavailable} />)
    await waitFor(() => expect(onUnavailable).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('does not skip steps 2 and 3 when the tourist holds the turned pose (regression)', async () => {
    // Real usage: a tourist keeps their head turned for well more than the
    // few frames strictly needed to cross the movement threshold. Each of
    // those extra qualifying frames must NOT re-fire step completion --
    // that bug raced stepIndex through steps 2 and 3 almost instantly and
    // landed straight on the black "capturing" overlay after step 1.
    render(<LivenessCapture onCapture={vi.fn()} onCancel={vi.fn()} onUnavailable={vi.fn()} />)
    await waitForCameraReady()
    await feedFrames(NEUTRAL, 8)
    await feedFrames(TURNED, 20) // held far longer than SUSTAIN_FRAMES requires

    // Land on step 2 -- not step 3, and not the capture screen (each extra
    // qualifying frame above must not have re-fired step completion).
    await waitFor(() => expect(screen.getByText('Look slightly upward')).toBeInTheDocument(), { timeout: 3000 })
    expect(screen.getByText('Step 2 of 3')).toBeInTheDocument()
    expect(screen.queryByText('Please nod your head')).not.toBeInTheDocument()
    expect(screen.queryByText('Verification Complete')).not.toBeInTheDocument()
  })

  it('recovers gracefully if the video reports 0x0 during capture, instead of crashing', async () => {
    render(<LivenessCapture onCapture={vi.fn()} onCancel={vi.fn()} onUnavailable={vi.fn()} />)
    await waitForCameraReady()
    await feedFrames(NEUTRAL, 8)
    await feedFrames(TURNED, 4)
    await waitFor(() => screen.getByText('Look slightly upward'), { timeout: 2000 })
    await feedFrames(NEUTRAL, 8)
    await feedFrames(LOOKED_UP, 4)
    await waitFor(() => screen.getByText('Please nod your head'), { timeout: 2000 })

    // The video feed reports 0x0 for the rest of this test -- simulating a
    // stream that ended right as capture was about to start. This must
    // never throw (the original bug report) and must never leave the
    // tourist on a dead screen -- it should retry the last step instead.
    Object.defineProperties(HTMLVideoElement.prototype, {
      videoWidth: { configurable: true, get: () => 0 },
      videoHeight: { configurable: true, get: () => 0 },
    })
    await feedFrames(NEUTRAL, 8)
    await feedFrames(NOD_DOWN, 4)
    await feedFrames(NOD_UP, 4)

    await waitFor(() => expect(screen.getByText(/couldn't capture your photo/)).toBeInTheDocument(), { timeout: 6000 })
    // Back on step 3, not thrown back to step 1.
    expect(screen.getByText('Please nod your head')).toBeInTheDocument()
    expect(screen.getByText('Step 3 of 3')).toBeInTheDocument()
  }, 15000)

  it('cancelling hands control back to the caller', async () => {
    const onCancel = vi.fn()
    render(<LivenessCapture onCapture={vi.fn()} onCancel={onCancel} onUnavailable={vi.fn()} />)
    await waitForCameraReady()
    fireEvent.click(screen.getByText('Cancel and use a plain photo instead'))
    expect(onCancel).toHaveBeenCalled()
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  computeFaceSignals, computeFaceBox, positionGuidance, sampleBrightness, sharpnessScore,
  FACE_SIZE_MIN, FACE_SIZE_MAX, MIN_BRIGHTNESS,
} from './liveness.js'

// A neutral, forward-facing synthetic landmark set: nose equidistant from
// both cheek landmarks, eye-line and chin at plausible relative positions.
// Only the handful of indices computeFaceSignals/computeFaceBox actually
// read are populated with real geometry; the rest of the 478-point array
// isn't needed for these pure-function tests.
function makeLandmarks({ noseX = 0.5, noseY = 0.55, cheekAX = 0.3, cheekBX = 0.7 } = {}) {
  const pts = new Array(478).fill(0).map(() => ({ x: 0.5, y: 0.5, z: 0 }))
  pts[1] = { x: noseX, y: noseY, z: 0 } // nose tip
  pts[152] = { x: 0.5, y: 0.85, z: 0 } // chin
  pts[33] = { x: 0.35, y: 0.4, z: 0 } // left eye outer
  pts[263] = { x: 0.65, y: 0.4, z: 0 } // right eye outer
  pts[234] = { x: cheekAX, y: 0.55, z: 0 }
  pts[454] = { x: cheekBX, y: 0.55, z: 0 }
  return pts
}

describe('computeFaceSignals', () => {
  it('reads ~0 yaw for a symmetric, forward-facing face', () => {
    const { yawSignal } = computeFaceSignals(makeLandmarks({ noseX: 0.5, cheekAX: 0.3, cheekBX: 0.7 }))
    expect(Math.abs(yawSignal)).toBeLessThan(0.02)
  })

  it('swings when the nose moves closer to one cheek than the other', () => {
    // Nose shifted toward cheekA (0.3) -- distance to cheekA shrinks,
    // distance to cheekB grows, so the signal should move away from 0 and
    // its sign should be consistent every time the nose leans the same way.
    const base = computeFaceSignals(makeLandmarks({ noseX: 0.5, cheekAX: 0.3, cheekBX: 0.7 }))
    const turned = computeFaceSignals(makeLandmarks({ noseX: 0.38, cheekAX: 0.3, cheekBX: 0.7 }))
    expect(Math.abs(turned.yawSignal)).toBeGreaterThan(Math.abs(base.yawSignal) + 0.05)
  })

  it('is scale-invariant -- doubling all distances does not change the signal', () => {
    const near = computeFaceSignals(makeLandmarks({ noseX: 0.4, cheekAX: 0.3, cheekBX: 0.7 }))
    // Same proportions, twice the spread -- a face twice as close to camera.
    const far = computeFaceSignals(makeLandmarks({ noseX: 0.3, cheekAX: 0.1, cheekBX: 0.9 }))
    expect(Math.abs(near.yawSignal - far.yawSignal)).toBeLessThan(0.05)
  })

  it('pitch signal changes when the nose moves relative to the eye line', () => {
    const neutral = computeFaceSignals(makeLandmarks({ noseY: 0.55 }))
    const shifted = computeFaceSignals(makeLandmarks({ noseY: 0.45 }))
    expect(neutral.pitchSignal).not.toBeCloseTo(shifted.pitchSignal, 2)
  })
})

describe('computeFaceBox', () => {
  it('bounds all landmark points', () => {
    const pts = [{ x: 0.2, y: 0.3 }, { x: 0.8, y: 0.4 }, { x: 0.5, y: 0.9 }, { x: 0.5, y: 0.1 }]
    const box = computeFaceBox(pts)
    expect(box.x).toBeCloseTo(0.2)
    expect(box.y).toBeCloseTo(0.1)
    expect(box.width).toBeCloseTo(0.6)
    expect(box.height).toBeCloseTo(0.8)
  })
})

describe('positionGuidance', () => {
  const goodBox = { x: 0.5 - 0.35 / 2, y: 0.5 - 0.35 / 2, width: 0.35, height: 0.35 }

  it('reports no face when none is detected', () => {
    expect(positionGuidance({ faceCount: 0, box: goodBox })).toMatch(/No face detected/)
  })

  it('reports multiple faces before any other guidance', () => {
    expect(positionGuidance({ faceCount: 2, box: goodBox, brightness: 10 }))
      .toMatch(/only one person/)
  })

  it('reports poor lighting ahead of distance/centering issues', () => {
    const msg = positionGuidance({ faceCount: 1, box: goodBox, brightness: MIN_BRIGHTNESS - 5 })
    expect(msg).toMatch(/better-lit/)
  })

  it('asks the tourist to move closer when the face is too small', () => {
    const small = { x: 0.45, y: 0.45, width: FACE_SIZE_MIN - 0.05, height: FACE_SIZE_MIN - 0.05 }
    expect(positionGuidance({ faceCount: 1, box: small, brightness: 200 })).toMatch(/closer/)
  })

  it('asks the tourist to move away when the face is too large', () => {
    const big = { x: 0.1, y: 0.1, width: FACE_SIZE_MAX + 0.1, height: FACE_SIZE_MAX + 0.1 }
    expect(positionGuidance({ faceCount: 1, box: big, brightness: 200 })).toMatch(/away/)
  })

  it('asks the tourist to center their face when off-center', () => {
    const offCenter = { x: 0.05, y: 0.45, width: 0.3, height: 0.3 }
    expect(positionGuidance({ faceCount: 1, box: offCenter, brightness: 200 })).toMatch(/Center/)
  })

  it('returns null (no guidance) once position and lighting are both fine', () => {
    expect(positionGuidance({ faceCount: 1, box: goodBox, brightness: 200 })).toBeNull()
  })
})

describe('sampleBrightness', () => {
  beforeEach(() => {
    HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
      drawImage: vi.fn(),
      getImageData: vi.fn().mockReturnValue({ data: new Uint8ClampedArray([200, 200, 200, 255]) }),
    })
  })

  it('returns null when the video has no dimensions yet', () => {
    const video = { videoWidth: 0, videoHeight: 0 }
    expect(sampleBrightness(video, { x: 0, y: 0, width: 1, height: 1 }, document.createElement('canvas'))).toBeNull()
  })

  it('reads real pixel data into an average luma', () => {
    const video = { videoWidth: 640, videoHeight: 480 }
    const result = sampleBrightness(video, { x: 0.2, y: 0.2, width: 0.4, height: 0.4 }, document.createElement('canvas'))
    expect(result).toBeCloseTo(200, 0)
  })
})

describe('sharpnessScore', () => {
  beforeEach(() => {
    HTMLCanvasElement.prototype.getContext = vi.fn()
  })

  it('reports near-zero energy for a flat (blurry) image', () => {
    HTMLCanvasElement.prototype.getContext.mockReturnValue({
      drawImage: vi.fn(),
      getImageData: () => ({ data: new Uint8ClampedArray(96 * 96 * 4).fill(128) }),
    })
    const canvas = document.createElement('canvas')
    canvas.width = 200
    canvas.height = 200
    expect(sharpnessScore(canvas)).toBeCloseTo(0, 5)
  })

  it('reports high energy for a high-contrast checkerboard (sharp edges)', () => {
    HTMLCanvasElement.prototype.getContext.mockReturnValue({
      drawImage: vi.fn(),
      getImageData: (x, y, w, h) => {
        const data = new Uint8ClampedArray(w * h * 4)
        for (let py = 0; py < h; py++) {
          for (let px = 0; px < w; px++) {
            const v = (px + py) % 2 === 0 ? 255 : 0
            const i = (py * w + px) * 4
            data[i] = data[i + 1] = data[i + 2] = v
            data[i + 3] = 255
          }
        }
        return { data }
      },
    })
    const canvas = document.createElement('canvas')
    canvas.width = 200
    canvas.height = 200
    expect(sharpnessScore(canvas)).toBeGreaterThan(50)
  })
})

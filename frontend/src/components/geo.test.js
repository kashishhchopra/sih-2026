import { describe, it, expect } from 'vitest'
import { haversineKm, pointInPoly } from './geo'

describe('haversineKm', () => {
  it('is zero for identical points', () => {
    expect(haversineKm(26.1445, 91.7362, 26.1445, 91.7362)).toBeCloseTo(0, 6)
  })

  it('gives ~111 km for one degree of latitude', () => {
    expect(haversineKm(0, 0, 1, 0)).toBeCloseTo(111.19, 1)
  })

  it('is symmetric', () => {
    expect(haversineKm(26.1, 91.7, 26.2, 91.8)).toBeCloseTo(
      haversineKm(26.2, 91.8, 26.1, 91.7), 9,
    )
  })
})

describe('pointInPoly', () => {
  // A square around Guwahati's Old Market, matching the seeded zone shape.
  const square = [
    [26.157, 91.742],
    [26.157, 91.758],
    [26.173, 91.758],
    [26.173, 91.742],
  ]

  it('detects a point at the centre', () => {
    expect(pointInPoly(26.165, 91.75, square)).toBe(true)
  })

  it('rejects a point outside', () => {
    expect(pointInPoly(26.20, 91.90, square)).toBe(false)
  })

  it('rejects a point just beyond each edge', () => {
    expect(pointInPoly(26.156, 91.75, square)).toBe(false)
    expect(pointInPoly(26.174, 91.75, square)).toBe(false)
    expect(pointInPoly(26.165, 91.741, square)).toBe(false)
    expect(pointInPoly(26.165, 91.759, square)).toBe(false)
  })

  it('returns false for degenerate rings', () => {
    expect(pointInPoly(26.165, 91.75, [])).toBe(false)
    expect(pointInPoly(26.165, 91.75, [[26.1, 91.7], [26.2, 91.8]])).toBe(false)
    expect(pointInPoly(26.165, 91.75, null)).toBe(false)
    expect(pointInPoly(26.165, 91.75, undefined)).toBe(false)
  })

  it('handles a concave polygon', () => {
    // An L-shape: the notch must read as outside.
    const L = [[0, 0], [0, 4], [2, 4], [2, 2], [4, 2], [4, 0]]
    expect(pointInPoly(1, 1, L)).toBe(true)
    expect(pointInPoly(3, 3, L)).toBe(false)
  })
})

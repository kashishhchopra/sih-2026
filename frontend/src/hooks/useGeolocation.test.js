import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, waitFor, cleanup } from '@testing-library/react'
import useGeolocation from './useGeolocation'

function installFakeGeolocation() {
  const watchers = {}
  let nextId = 1
  const fake = {
    watchPosition: vi.fn((onSuccess, onError) => {
      const id = nextId++
      watchers[id] = { onSuccess, onError }
      return id
    }),
    clearWatch: vi.fn((id) => { delete watchers[id] }),
  }
  Object.defineProperty(navigator, 'geolocation', { value: fake, configurable: true })
  return { fake, watchers }
}

describe('useGeolocation', () => {
  afterEach(() => {
    // Unmount every hook FIRST (so cleanup effects still see a real
    // navigator.geolocation to call clearWatch on), then remove the fake.
    cleanup()
    delete navigator.geolocation
    delete navigator.permissions
  })

  it('reports unsupported when navigator.geolocation is absent', () => {
    delete navigator.geolocation
    const { result } = renderHook(() => useGeolocation())
    expect(result.current.permissionState).toBe('unsupported')
  })

  it('does not start watching when disabled', () => {
    const { fake } = installFakeGeolocation()
    renderHook(() => useGeolocation({ enabled: false }))
    expect(fake.watchPosition).not.toHaveBeenCalled()
  })

  it('converts a successful position into lat/lng/speedKmh', async () => {
    const { watchers } = installFakeGeolocation()
    const { result } = renderHook(() => useGeolocation({ enabled: true }))

    watchers[1].onSuccess({
      coords: { latitude: 26.15, longitude: 91.74, accuracy: 12, speed: 2 }, // 2 m/s
      timestamp: 1700000000000,
    })

    await waitFor(() => expect(result.current.position).not.toBeNull())
    expect(result.current.position.lat).toBe(26.15)
    expect(result.current.position.lng).toBe(91.74)
    expect(result.current.position.speedKmh).toBeCloseTo(7.2, 1) // 2 m/s * 3.6
    expect(result.current.permissionState).toBe('granted')
  })

  it('treats a null GPS speed as stationary rather than NaN', async () => {
    const { watchers } = installFakeGeolocation()
    const { result } = renderHook(() => useGeolocation({ enabled: true }))
    watchers[1].onSuccess({
      coords: { latitude: 26.15, longitude: 91.74, accuracy: 12, speed: null },
      timestamp: 1700000000000,
    })
    await waitFor(() => expect(result.current.position).not.toBeNull())
    expect(result.current.position.speedKmh).toBe(0)
  })

  it('surfaces a permission-denied error', async () => {
    const { watchers } = installFakeGeolocation()
    const { result } = renderHook(() => useGeolocation({ enabled: true }))
    watchers[1].onError({ code: 1, PERMISSION_DENIED: 1, message: 'User denied Geolocation' })
    await waitFor(() => expect(result.current.permissionState).toBe('denied'))
    expect(result.current.error).toBe('User denied Geolocation')
  })

  it('clears the watch on unmount', () => {
    const { fake } = installFakeGeolocation()
    const { unmount } = renderHook(() => useGeolocation({ enabled: true }))
    unmount()
    expect(fake.clearWatch).toHaveBeenCalledWith(1)
  })

  it('clears the watch when enabled flips to false', () => {
    const { fake } = installFakeGeolocation()
    const { rerender } = renderHook(({ enabled }) => useGeolocation({ enabled }), {
      initialProps: { enabled: true },
    })
    expect(fake.watchPosition).toHaveBeenCalledTimes(1)
    rerender({ enabled: false })
    expect(fake.clearWatch).toHaveBeenCalledWith(1)
  })
})

import { describe, it, expect, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import useOnlineStatus from './useOnlineStatus'

function setNavigatorOnLine(value) {
  Object.defineProperty(navigator, 'onLine', { value, configurable: true, writable: true })
}

describe('useOnlineStatus', () => {
  afterEach(() => setNavigatorOnLine(true))

  it('reflects navigator.onLine at mount', () => {
    setNavigatorOnLine(false)
    const { result } = renderHook(() => useOnlineStatus())
    expect(result.current).toBe(false)
  })

  it('flips to false on an offline event', () => {
    setNavigatorOnLine(true)
    const { result } = renderHook(() => useOnlineStatus())
    act(() => window.dispatchEvent(new Event('offline')))
    expect(result.current).toBe(false)
  })

  it('flips back to true on an online event', () => {
    setNavigatorOnLine(false)
    const { result } = renderHook(() => useOnlineStatus())
    act(() => window.dispatchEvent(new Event('online')))
    expect(result.current).toBe(true)
  })
})

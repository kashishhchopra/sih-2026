import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// jsdom has no ResizeObserver -- Recharts' <ResponsiveContainer> (used on
// the Analytics page and anywhere else a chart is rendered) needs one to
// mount at all. A minimal no-op stand-in is enough: tests assert on the
// data/labels rendered, not on actual pixel measurements.
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

// jsdom has no URL.createObjectURL/revokeObjectURL -- any page that builds a
// downloadable blob link (e.g. the Analytics page's PDF/Excel export
// buttons) throws without a stand-in. Real object-URL semantics don't matter
// for tests, which only assert that the download was triggered.
if (typeof globalThis.URL.createObjectURL === 'undefined') {
  globalThis.URL.createObjectURL = () => 'blob:mock-url'
}
if (typeof globalThis.URL.revokeObjectURL === 'undefined') {
  globalThis.URL.revokeObjectURL = () => {}
}

// Unmount anything a test rendered, so cases cannot leak DOM into each other.
afterEach(() => {
  cleanup()
  localStorage.clear()
})

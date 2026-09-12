import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import TrailReplay from './TrailReplay'

// jsdom does not implement the layout/SVG internals Leaflet's renderer needs
// (getBoundingClientRect etc return zeros), so MapContainer throws on mount
// in this environment regardless of correctness. The behaviour actually under
// test here is the scrubber (step state, button wiring) -- not tile
// rendering -- so the map primitives are stubbed to inert placeholders.
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }) => <div>{children}</div>,
  TileLayer: () => null,
  Polyline: () => null,
  CircleMarker: () => null,
  Marker: () => null,
}))
vi.mock('./mapIcons', () => ({ touristIcon: () => ({}) }))

const pings = [
  { lat: 26.10, lng: 91.70, speed_kmh: 4, timestamp: '2026-01-01T10:00:00', is_anomaly: false },
  { lat: 26.11, lng: 91.71, speed_kmh: 5, timestamp: '2026-01-01T10:05:00', is_anomaly: false },
  { lat: 26.30, lng: 91.90, speed_kmh: 160, timestamp: '2026-01-01T10:10:00', is_anomaly: true },
]

describe('TrailReplay', () => {
  it('shows an empty-state message with no pings', () => {
    render(<TrailReplay pings={[]} />)
    expect(screen.getByText(/no location history/i)).toBeInTheDocument()
  })

  it('defaults the scrubber to the latest ping', () => {
    render(<TrailReplay pings={pings} />)
    expect(screen.getByText(/Ping 3 \/ 3/)).toBeInTheDocument()
    expect(screen.getByText(/⚠ anomaly/)).toBeInTheDocument()
  })

  it('scrubbing back moves off the anomaly ping', () => {
    render(<TrailReplay pings={pings} />)
    fireEvent.change(screen.getByRole('slider'), { target: { value: '0' } })
    expect(screen.getByText(/Ping 1 \/ 3/)).toBeInTheDocument()
    expect(screen.queryByText(/⚠ anomaly/)).not.toBeInTheDocument()
  })

  it('the "Start" button jumps to the first ping', () => {
    render(<TrailReplay pings={pings} />)
    fireEvent.click(screen.getByText(/Start/))
    expect(screen.getByText(/Ping 1 \/ 3/)).toBeInTheDocument()
  })

  it('the "Latest" button returns to the newest ping', () => {
    render(<TrailReplay pings={pings} />)
    fireEvent.click(screen.getByText(/Start/))
    fireEvent.click(screen.getByText(/Latest/))
    expect(screen.getByText(/Ping 3 \/ 3/)).toBeInTheDocument()
  })

  it('shows the current ping speed', () => {
    render(<TrailReplay pings={pings} />)
    fireEvent.change(screen.getByRole('slider'), { target: { value: '1' } })
    expect(screen.getByText('5.0 km/h')).toBeInTheDocument()
  })
})

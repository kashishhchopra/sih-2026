import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import TrajectoryOverlay from './TrajectoryOverlay'

// jsdom doesn't implement the SVG/layout internals Leaflet's renderer needs,
// so real Polyline/CircleMarker throw on mount here -- stub to inert
// placeholders and assert on props instead (same approach as TrailReplay.test.jsx).
vi.mock('react-leaflet', () => ({
  Polyline: (props) => <div data-testid="polyline" data-positions={JSON.stringify(props.positions)} />,
  CircleMarker: (props) => <div data-testid="circle-marker" data-center={JSON.stringify(props.center)}>{props.children}</div>,
  Popup: ({ children }) => <div data-testid="popup">{children}</div>,
}))

const points = [
  { lat: 26.10, lng: 91.70, eta_min: 5 },
  { lat: 26.11, lng: 91.71, eta_min: 10 },
  { lat: 26.12, lng: 91.72, eta_min: 15 },
]

describe('TrajectoryOverlay', () => {
  it('renders nothing when there are no predicted points', () => {
    const { container } = render(<TrajectoryOverlay points={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when points is null/undefined', () => {
    const { container } = render(<TrajectoryOverlay points={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('draws a dashed line through every predicted point', () => {
    const { getByTestId } = render(<TrajectoryOverlay points={points} />)
    const positions = JSON.parse(getByTestId('polyline').dataset.positions)
    expect(positions).toEqual([[26.10, 91.70], [26.11, 91.71], [26.12, 91.72]])
  })

  it('marks the final predicted point with its ETA', () => {
    const { getByTestId, getByText } = render(<TrajectoryOverlay points={points} />)
    const center = JSON.parse(getByTestId('circle-marker').dataset.center)
    expect(center).toEqual([26.12, 91.72])
    expect(getByText(/15 min/)).toBeInTheDocument()
  })
})

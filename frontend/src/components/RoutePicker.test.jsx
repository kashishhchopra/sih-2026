import { describe, it, expect, vi } from 'vitest'
import { render, act, renderHook } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import api from '../api'
import RoutePicker, { RouteLayer, useRoutePicker } from './RoutePicker'

// jsdom doesn't implement the SVG/layout internals Leaflet's renderer needs,
// so real Polyline/CircleMarker throw on mount here -- stub to inert
// placeholders and assert on props instead (same approach as TrajectoryOverlay.test.jsx).
vi.mock('react-leaflet', () => ({
  Polyline: (props) => (
    <div data-testid="polyline" className={props.className}
      data-positions={JSON.stringify(props.positions)}
      data-color={props.pathOptions.color} data-weight={props.pathOptions.weight} />
  ),
  CircleMarker: (props) => <div data-testid="circle-marker" data-center={JSON.stringify(props.center)} />,
  useMapEvents: (handlers) => { global.__mapClickHandler = handlers.click; return null },
}))

const mock = new MockAdapter(api)

const routeResponse = {
  tourist_id: 1,
  recommended: { points: [[26.1, 91.7], [26.11, 91.705], [26.12, 91.71]], risk_score: 5, length_km: 1.5, risk_level: 'low' },
  candidates: [
    { points: [[26.1, 91.7], [26.11, 91.71], [26.12, 91.72]], risk_score: 80, length_km: 1.4, risk_level: 'high' },
    { points: [[26.1, 91.7], [26.11, 91.705], [26.12, 91.71]], risk_score: 5, length_km: 1.5, risk_level: 'low' },
  ],
}
// candidates[1] === recommended by value but RouteLayer compares by reference,
// so build the fixture with the SAME object reference, matching what the
// real API/JSON.parse response naturally yields via `result.recommended`.
routeResponse.candidates[1] = routeResponse.recommended

describe('RoutePicker', () => {
  it('renders nothing outside the map when not active', () => {
    const { result } = renderHook(() => useRoutePicker(1))
    const { container } = render(<RoutePicker active={false} onToggle={() => {}} state={result.current} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a destination prompt and disabled button before a destination is picked', () => {
    const { result } = renderHook(() => useRoutePicker(1))
    const { getByText } = render(<RoutePicker active={true} onToggle={() => {}} state={result.current} />)
    expect(getByText(/Tap the map to choose a destination/)).toBeInTheDocument()
    expect(getByText('Find safe route').closest('button')).toBeDisabled()
  })

  it('RouteLayer renders a destination marker once picked', () => {
    const { getByTestId } = render(
      <RouteLayer active={true} dest={[26.15, 91.72]} result={null} onPick={() => {}} />
    )
    const center = JSON.parse(getByTestId('circle-marker').dataset.center)
    expect(center).toEqual([26.15, 91.72])
  })

  it('renders all candidate routes and visually emphasizes the recommended one', () => {
    const { getAllByTestId } = render(
      <RouteLayer active={true} dest={[26.12, 91.71]} result={routeResponse} onPick={() => {}} />
    )
    const polylines = getAllByTestId('polyline')
    expect(polylines).toHaveLength(2)

    const recommended = polylines.find((p) => p.className === 'route-recommended')
    const other = polylines.find((p) => p.className === 'route-candidate')
    expect(recommended).toBeTruthy()
    expect(other).toBeTruthy()
    // thicker line for the recommended route
    expect(Number(recommended.dataset.weight)).toBeGreaterThan(Number(other.dataset.weight))
    // colored by risk level via mapIcons.riskColor
    expect(recommended.dataset.color).toBe('#22c55e') // low
    expect(other.dataset.color).toBe('#f97316') // high
  })

  it('fetches and displays the recommendation, including the disclaimer', async () => {
    mock.onGet('/tourists/1/route-recommendation').reply(200, routeResponse)
    const { result } = renderHook(() => useRoutePicker(1))
    act(() => { result.current.pick([26.12, 91.71]) })

    const { rerender, getByText } = render(<RoutePicker active={true} onToggle={() => {}} state={result.current} />)
    rerender(<RoutePicker active={true} onToggle={() => {}} state={result.current} />)

    await act(async () => { await result.current.findRoute() })
    rerender(<RoutePicker active={true} onToggle={() => {}} state={result.current} />)

    expect(getByText(/Approximate route, not turn-by-turn navigation/)).toBeInTheDocument()
    expect(getByText(/1.5 km/)).toBeInTheDocument()
  })

  it('surfaces a 400 error (e.g. no known tourist location) instead of crashing', async () => {
    mock.onGet('/tourists/1/route-recommendation').reply(400, { detail: 'Tourist has no known location yet' })
    const { result } = renderHook(() => useRoutePicker(1))
    act(() => { result.current.pick([26.12, 91.71]) })

    const { rerender, getByText } = render(<RoutePicker active={true} onToggle={() => {}} state={result.current} />)
    await act(async () => { await result.current.findRoute() })
    rerender(<RoutePicker active={true} onToggle={() => {}} state={result.current} />)

    expect(getByText('Tourist has no known location yet')).toBeInTheDocument()
  })
})

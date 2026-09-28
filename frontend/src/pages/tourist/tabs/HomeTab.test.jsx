import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import HomeTab from './HomeTab.jsx'

// jsdom has no real SVG/canvas renderer for Leaflet -- same class of gap
// every other map-using page in this repo works around the same way.
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children, center }) => <div data-testid="map" data-center={JSON.stringify(center)}>{children}</div>,
  TileLayer: () => null,
  Marker: ({ children }) => <div data-testid="marker">{children}</div>,
  Polygon: () => null,
  Popup: ({ children }) => <div>{children}</div>,
}))

// These children fetch their own data/have their own dedicated test suites
// -- irrelevant to the map-center regression under test here.
vi.mock('../../../components/DisasterBanner.jsx', () => ({ default: () => null }))
vi.mock('../../../components/RecommendedPlaces.jsx', () => ({ default: () => null }))
vi.mock('../../../components/SafetyAssistantCard.jsx', () => ({ default: () => null }))
vi.mock('../../../components/ScoreExplanation.jsx', () => ({ default: () => null }))
vi.mock('../../../components/RoutePicker.jsx', () => ({ RouteLayer: () => null }))

const baseData = {
  me: { id: 1, full_name: 'Test User', last_lat: null, last_lng: null },
  score: { score: 80, breakdown: { zone: 'Zone A', explanation: [] } },
  zones: [],
  trajectory: [],
  nearby: [],
  riskyZone: null,
  routePicker: { dest: null, result: null, pick: vi.fn() },
  routePickerOpen: false,
  setRoutePickerOpen: vi.fn(),
  tid: 1,
  sendSOS: vi.fn(),
}

describe('HomeTab', () => {
  // Regression: a brand-new tourist (registered but never sent a location
  // ping yet) has last_lat/last_lng === null. The map used to build its
  // `center` prop directly from those, which crashed the whole app
  // ("Cannot read properties of null (reading 'lat')") the moment such a
  // tourist opened the Home tab.
  it('does not crash and falls back to the default map center when the tourist has no location yet', () => {
    expect(() => render(<HomeTab data={baseData} onVoice={vi.fn()} onNavigateTab={vi.fn()} />))
      .not.toThrow()
    const map = screen.getByTestId('map')
    const center = JSON.parse(map.dataset.center)
    expect(center).toEqual([26.1445, 91.7362]) // DEFAULT_MAP.center
  })

  it('omits the tourist marker when there is no location yet', () => {
    render(<HomeTab data={baseData} onVoice={vi.fn()} onNavigateTab={vi.fn()} />)
    expect(screen.queryByTestId('marker')).not.toBeInTheDocument()
  })

  it('centers on and marks the tourist once a real location exists', () => {
    const data = { ...baseData, me: { ...baseData.me, last_lat: 26.15, last_lng: 91.74 } }
    render(<HomeTab data={data} onVoice={vi.fn()} onNavigateTab={vi.fn()} />)
    const map = screen.getByTestId('map')
    expect(JSON.parse(map.dataset.center)).toEqual([26.15, 91.74])
    expect(screen.getByTestId('marker')).toBeInTheDocument()
  })

  it('filters out nearby units with missing coordinates instead of crashing', () => {
    const data = {
      ...baseData,
      me: { ...baseData.me, last_lat: 26.15, last_lng: 91.74 },
      nearby: [{ id: 1, lat: 26.16, lng: 91.75 }, { id: 2, lat: null, lng: null }],
    }
    expect(() => render(<HomeTab data={data} onVoice={vi.fn()} onNavigateTab={vi.fn()} />))
      .not.toThrow()
  })
})

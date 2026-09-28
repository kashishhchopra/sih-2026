import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import MockAdapter from 'axios-mock-adapter'
import api from '../../api'
import PoliceNetwork from './PoliceNetwork'

const renderPage = () => render(<MemoryRouter><PoliceNetwork /></MemoryRouter>)

// react-leaflet's Polygon/Polyline layers need a real SVG renderer that jsdom
// doesn't provide (same class of gap as canvas) -- every other map-using
// page in this repo is untested for exactly that reason. This page's own
// logic (KPIs, cards, modals, the activity feed) doesn't depend on Leaflet
// actually painting, so it's swapped for inert stand-ins here only.
// Marker/Polygon forward `eventHandlers.click` onto a plain <div> so tests
// can still exercise the real click-to-focus wiring (focusOnStation,
// focusOnZone) without a real Leaflet SVG renderer.
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }) => <div>{children}</div>,
  TileLayer: () => null,
  Marker: ({ children, eventHandlers }) => (
    <div onClick={eventHandlers?.click}>{children}</div>
  ),
  Popup: ({ children }) => <div>{children}</div>,
  Polygon: ({ children, eventHandlers }) => (
    <div onClick={eventHandlers?.click}>{children}</div>
  ),
  Polyline: () => null,
  useMap: () => ({ flyTo: () => {}, getZoom: () => 13 }),
}))

vi.mock('../../useWebSocket', () => ({
  default: () => ({ connected: true }),
}))

const mock = new MockAdapter(api)

beforeEach(() => mock.reset())

const dashboardBody = {
  generated_at: '2026-01-01T00:00:00',
  stations: [
    {
      id: 1, name: 'Market PS', phone: '100', contact_officer: 'Inspector Nair',
      lat: 26.16, lng: 91.75, zone_id: 2, zone_name: 'Old Market High-Risk Zone',
      open_incidents: 1, critical_incidents: 1, incident_ids: [7],
      total_officers: 28, max_concurrent_cases: 1, has_capacity: false, load_pct: 100.0,
    },
    {
      id: 2, name: 'City Central PS', phone: '100', contact_officer: 'Inspector Baruah',
      lat: 26.145, lng: 91.737, zone_id: 4, zone_name: 'City Center Safe Zone',
      open_incidents: 0, critical_incidents: 0, incident_ids: [],
      total_officers: 32, max_concurrent_cases: 8, has_capacity: true, load_pct: 0.0,
    },
  ],
  unassigned_incidents: [],
  total_open_incidents: 1,
}

const stationsBody = [
  { id: 1, name: 'Market PS', zone_id: 2, phone: '100', contact_officer: 'Inspector Nair', lat: 26.16, lng: 91.75 },
  { id: 2, name: 'City Central PS', zone_id: 4, phone: '100', contact_officer: 'Inspector Baruah', lat: 26.145, lng: 91.737 },
]

const zonesBody = [
  { id: 2, name: 'Old Market High-Risk Zone', risk_level: 'high', polygon: [[26.157, 91.742], [26.157, 91.758], [26.163, 91.758], [26.163, 91.742]], crime_index: 70, description: '', source: 'manual' },
  { id: 4, name: 'City Center Safe Zone', risk_level: 'low', polygon: [[26.139, 91.730], [26.139, 91.744], [26.151, 91.744], [26.151, 91.730]], crime_index: 15, description: '', source: 'manual' },
]

function mockBaseEndpoints() {
  mock.onGet('/police-network/dashboard').reply(200, dashboardBody)
  mock.onGet('/police-network/stations').reply(200, stationsBody)
  mock.onGet('/zones').reply(200, zonesBody)
  mock.onGet('/zones/crowd-density').reply(200, [
    { zone_id: 2, zone: 'Old Market High-Risk Zone', tourist_count: 5, density: 'low', overcrowded: false },
  ])
  mock.onGet('/police-units').reply(200, [])
  mock.onGet('/tourists').reply(200, [])
  mock.onGet(/\/police-network\/cameras\/nearby.*/).reply(200, [
    { id: 9, label: 'Old Market Main Gate Cam 1', zone_id: 2, lat: 26.16, lng: 91.75, status: 'active', distance_m: 12 },
  ])
  mock.onGet(/\/police-network\/fallback-preview.*/).reply(200, [
    { station_id: 2, name: 'City Central PS', distance_km: 2.1, open_cases: 0,
      max_concurrent_cases: 8, total_officers: 32, has_capacity: true, load_pct: 0.0 },
    { station_id: 1, name: 'Market PS', distance_km: 0.3, open_cases: 1,
      max_concurrent_cases: 1, total_officers: 28, has_capacity: false, load_pct: 100.0 },
  ])
  // The real CCTV console -- deliberately empty here, matching the honest
  // "no feeds available" state most of this test file doesn't care about.
  mock.onGet('/cctv').reply(200, { cameras: [], summary: {
    total: 0, live: 0, offline: 0, no_stream: 0, provider: null,
    provider_configured: false, refresh_interval_seconds: 0,
  } })
  // Disaster & Weather Monitoring -- empty by default; tests that care
  // about it override this.
  mock.onGet('/police-network/disaster-summary').reply(200, [])
}

describe('PoliceNetwork page', () => {
  it('renders the network status header, KPIs, and station cards', async () => {
    mockBaseEndpoints()
    const { findByText, findAllByText, findByRole } = renderPage()
    await findByRole('heading', { name: 'Central Safety Dashboard' })
    await findByText('NETWORK OPERATIONAL')
    expect((await findAllByText('Market PS')).length).toBeGreaterThan(0)
    expect((await findAllByText('City Central PS')).length).toBeGreaterThan(0)
  })

  it('shows the zone coverage table with real risk/tourist/camera data', async () => {
    mockBaseEndpoints()
    const { findByText, findAllByText } = renderPage()
    await findByText('Zone Coverage & Assignment')
    // Also present in the zone polygon's map popup now that Polygon
    // renders its children in tests -- assert presence, not uniqueness.
    expect((await findAllByText('Old Market High-Risk Zone')).length).toBeGreaterThan(0)
  })

  it('shows the real CCTV surveillance console instead of the old demo grid', async () => {
    // The standalone "Nearby CCTV" card (CAM-NNN tiles with a LIVE/OFFLINE
    // badge sourced from Camera.status, not an actual feed) was removed in
    // favour of CctvNetworkPanel, which only ever labels a camera LIVE
    // after /api/cctv reports a real probed connection. See
    // CctvNetworkPanel.test.jsx for that component's own coverage.
    mockBaseEndpoints()
    const { findByText, queryByText } = renderPage()
    await findByText('CCTV Network')
    expect(queryByText(/^CAM-\d/)).not.toBeInTheDocument()
  })

  it('opens the station detail modal and sends a case directly', async () => {
    mockBaseEndpoints()
    mock.onPost('/police-network/incidents/7/transfer/send').reply(201, {})

    const { findAllByText, findByText } = renderPage()
    const viewButtons = await findAllByText('View Station')
    fireEvent.click(viewButtons[0])

    await findByText('Station Commander')
    const select = await findByText('Send to…')
    fireEvent.change(select.closest('select'), { target: { value: '2' } })
    fireEvent.click(await findByText('Send Case'))

    await waitFor(() => {
      expect(mock.history.post.some((r) => r.url === '/police-network/incidents/7/transfer/send')).toBe(true)
    })
  })

  it('opens the contact modal for a station', async () => {
    mockBaseEndpoints()
    const { findAllByText, findByText } = renderPage()
    const contactButtons = await findAllByText('Contact')
    fireEvent.click(contactButtons[0])
    await findByText('Connecting…')
    await findByText('🟢 Connected')
  })

  it('runs the simulate-incident demo flow', async () => {
    mockBaseEndpoints()
    const { findByText } = renderPage()
    fireEvent.click(await findByText('🚨 Simulate Incident'))
    await findByText('ACTIVE RESPONSE IN PROGRESS')
    await findByText(/Tourist SOS raised/)
    await findByText('Mark Resolved', {}, { timeout: 6000 })
  })

  it('shows each station case load, flagging one at capacity', async () => {
    mockBaseEndpoints()
    const { findAllByText, findByText } = renderPage()
    // Market PS is 1/1 -> at capacity; City Central PS is 0/8 -> free
    await findByText(/1\/1 · AT CAPACITY/)
    expect((await findAllByText('Case load')).length).toBe(2)
  })

  it('loads the resource fallback order when a zone/station is selected', async () => {
    mockBaseEndpoints()
    const { findByText, findAllByText } = renderPage()
    await findByText('Resource Fallback Order')
    // nothing selected yet
    await findByText(/Click a zone or station marker/)

    // click the zone-coverage table row (same focusOnStation handler the
    // station cards and map markers use)
    const cells = await findAllByText('Old Market High-Risk Zone')
    fireEvent.click(cells.find((el) => el.closest('tr')))

    // ranked list: the station with spare capacity leads, the full one is flagged
    await findByText(/2\.1 km/)
    await findByText(/0\/8 free/)
    await findByText(/1\/1 FULL/)
  })

  // Regression: clicking a zone's polygon directly on the map -- the other
  // "select a zone" affordance the empty-state text promises, distinct from
  // the Zone Coverage table row -- previously had no click handler wired at
  // all, so the fallback card stayed stuck on "Select a station or zone".
  it('loads the resource fallback order when a zone polygon on the map is clicked', async () => {
    mockBaseEndpoints()
    const { findByText } = renderPage()
    await findByText('Resource Fallback Order')
    await findByText(/Click a zone or station marker/)

    // The click lands inside the Polygon's popup content and bubbles up
    // through the DOM to the Polygon wrapper's own click handler, same as
    // a real Leaflet click anywhere inside the polygon's shape would.
    const popup = await findByText('Old Market High-Risk Zone', { selector: 'b' })
    fireEvent.click(popup)

    await findByText(/2\.1 km/)
    await findByText(/0\/8 free/)
    await findByText(/1\/1 FULL/)
  })

  it('shows an honest empty state when there are no active hazard advisories', async () => {
    mockBaseEndpoints()
    const { findByText } = renderPage()
    await findByText('Disaster & Weather Monitoring')
    await findByText(/No active weather or disaster alerts/)
  })

  it('shows the Disaster & Weather Monitoring section from real advisory data', async () => {
    mockBaseEndpoints()
    mock.onGet('/police-network/disaster-summary').reply(200, [
      { id: 1, zone_id: 2, hazard_type: 'flood', severity: 'high',
        title: 'Flood Advisory', message: 'Flash flood advisory.', source: 'simulated',
        active: true, issued_at: '2026-01-01T00:00:00', expires_at: null,
        zone_name: 'Old Market High-Risk Zone', affected_tourists: 3,
        station_id: 1, station_name: 'Market PS' },
    ])
    const { findByText, findAllByText } = renderPage()
    await findByText('Disaster & Weather Monitoring')
    // Also appears in the affected zone's map popup now that it's drawn
    // with the hazard highlight -- assert presence, not uniqueness.
    expect((await findAllByText('Flood Advisory')).length).toBeGreaterThan(0)
    await findByText(/3 affected tourists/)
    expect((await findAllByText(/Market PS/)).length).toBeGreaterThan(0)
  })

  it('shows a retry option when the disaster feed fails', async () => {
    mockBaseEndpoints()
    mock.onGet('/police-network/disaster-summary').networkError()
    const { findByText } = renderPage()
    await findByText(/Weather & Disaster Alert Service Unavailable/)
    await findByText('Retry')
  })
})

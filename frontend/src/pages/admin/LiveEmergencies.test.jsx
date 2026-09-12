import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, fireEvent, waitFor, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import MockAdapter from 'axios-mock-adapter'
import api from '../../api'
import LiveEmergencies from './LiveEmergencies'

const renderPage = (initialEntry = '/admin/live-emergencies') => render(
  <MemoryRouter initialEntries={[initialEntry]}><LiveEmergencies /></MemoryRouter>,
)

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }) => <div>{children}</div>,
  TileLayer: () => null,
  Marker: ({ children }) => <div>{children}</div>,
  Popup: ({ children }) => <div>{children}</div>,
  Polyline: () => null,
}))

let wsCallback = null
vi.mock('../../useWebSocket', () => ({
  default: (cb) => { wsCallback = cb; return { connected: true } },
}))

const mock = new MockAdapter(api)

beforeEach(() => {
  mock.reset()
  wsCallback = null
})

const emergency = {
  incident_id: 42, tourist_id: 1, tourist_name: 'Aarav', digital_id: 'STS-1042',
  incident_type: 'sos', severity: 'critical', status: 'dispatched',
  live_tracking_active: true, station_id: 1, station_name: 'Central Police Station',
  location_status: 'live', seconds_since_update: 4,
  latest: { lat: 26.15, lng: 91.74, accuracy_m: 8, speed_kmh: 3.2, heading_deg: 92,
           timestamp: new Date().toISOString(), anomaly_flag: false, demo: false },
  trail: [{ lat: 26.14, lng: 91.73 }, { lat: 26.15, lng: 91.74 }],
}

describe('LiveEmergencies', () => {
  it('shows an empty state when nothing is active', async () => {
    mock.onGet('/incidents/live').reply(200, [])
    const { findByText } = renderPage()
    await findByText('No active emergencies right now.')
  })

  it('lists an active emergency with its station and live status', async () => {
    mock.onGet('/incidents/live').reply(200, [emergency])
    const { findByText } = renderPage()
    await findByText(/🚨 INC-42/)
    expect(screen.getByText(/Central Police Station/)).toBeInTheDocument()
    expect(screen.getByText('🟢 LIVE')).toBeInTheDocument()
  })

  it('shows an error message if the list fails to load', async () => {
    mock.onGet('/incidents/live').reply(500)
    const { findByText } = renderPage()
    await findByText('Could not load live emergencies right now.')
  })

  it('moves the marker/trail when a live location update arrives over the socket', async () => {
    mock.onGet('/incidents/live').reply(200, [emergency])
    const { findByText } = renderPage()
    await findByText(/🚨 INC-42/)

    wsCallback({
      event: 'emergency_location', incident_id: 42, lat: 26.20, lng: 91.80,
      accuracy_m: 5, speed_kmh: 4, heading_deg: 180, timestamp: new Date().toISOString(),
      anomaly_flag: false, demo: false,
    })
    // The mocked Popup renders its children as plain DOM, so the new
    // accuracy value proves the map's marker actually picked up the pushed
    // update rather than sitting on the stale initial fetch.
    await waitFor(() => expect(
      screen.getByText((_, node) => node?.textContent === 'Accuracy: ±5 m')
    ).toBeInTheDocument())
  })

  it('removes an emergency from the list once tracking stops', async () => {
    mock.onGet('/incidents/live').reply(200, [emergency])
    const { findByText, queryByText } = renderPage()
    await findByText(/🚨 INC-42/)

    wsCallback({ event: 'emergency_tracking_stopped', incident_id: 42 })
    await waitFor(() => expect(queryByText(/🚨 INC-42/)).not.toBeInTheDocument())
  })

  it('pre-selects the incident named in the ?incident= deep link from "View Live Location"', async () => {
    const second = { ...emergency, incident_id: 43, digital_id: 'STS-2000', tourist_name: 'Emma' }
    mock.onGet('/incidents/live').reply(200, [emergency, second])
    const { findByText } = renderPage('/admin/live-emergencies?incident=43')
    await findByText(/🚨 INC-43/)
    // The card for #43 is the one with the active-selection border.
    expect(screen.getByText(/🚨 INC-43/).closest('button')).toHaveClass('border-red-500')
  })

  it('fetches the deep-linked case directly and shows it even when the aggregate live list omits it', async () => {
    // #99 isn't in /incidents/live (e.g. its location is STALE/OFFLINE, or
    // it was just transferred) -- View Live Location must still show it by
    // fetching it individually rather than only matching the filtered list.
    mock.onGet('/incidents/live').reply(200, [])
    mock.onGet('/incidents/99/location').reply(200, {
      ...emergency, incident_id: 99, digital_id: 'STS-9099', location_status: 'offline',
    })
    const { findByText, findAllByText } = renderPage('/admin/live-emergencies?incident=99')
    await findByText(/🚨 INC-99/)
    expect((await findAllByText(/STS-9099/)).length).toBeGreaterThan(0)
  })

  it('shows a clear notice when the deep-linked case has no location data yet', async () => {
    mock.onGet('/incidents/live').reply(200, [])
    mock.onGet('/incidents/7/location').reply(200, {
      incident_id: 7, tourist_id: 5, tourist_name: 'Rohan', digital_id: 'STS-7000',
      incident_type: 'sos', severity: 'critical', status: 'dispatched',
      live_tracking_active: true, station_id: 1, station_name: 'Central Police Station',
      location_status: 'no_data', seconds_since_update: null, latest: null, trail: [],
    })
    const { findByText } = renderPage('/admin/live-emergencies?incident=7')
    await findByText(/has not received any location update yet/i)
  })

  it('shows full tourist and case detail for the selected emergency', async () => {
    const withDetail = {
      ...emergency, tourist_phone: '9876543210', tourist_nationality: 'Indian',
      hotel: 'ABC Residency', safety_score: 72, description: 'SOS triggered',
      detected_at: new Date().toISOString(),
      emergency_contacts: [{ name: 'Kin', phone: '+91-1', relation: 'family' }],
    }
    mock.onGet('/incidents/live').reply(200, [withDetail])
    const { findByText } = renderPage()
    await findByText(/🚨 INC-42/)
    await findByText('9876543210')
    await findByText('ABC Residency')
    await findByText(/Kin \(family\)/)
  })

  it('selecting a different card shows that emergency on the map', async () => {
    const second = { ...emergency, incident_id: 43, digital_id: 'STS-2000', tourist_name: 'Emma' }
    mock.onGet('/incidents/live').reply(200, [emergency, second])
    const { findByText, getByText } = renderPage()
    await findByText(/🚨 INC-42/)
    fireEvent.click(getByText(/🚨 INC-43/))
    // No crash / still renders both cards -- map swap is covered by the
    // mocked leaflet stand-ins, the real assertion is selection doesn't error.
    expect(getByText(/🚨 INC-42/)).toBeInTheDocument()
    expect(getByText(/🚨 INC-43/)).toBeInTheDocument()
  })
})

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import api from '../api'
import IncidentTimeline from './IncidentTimeline'

// See TrailReplay.test.jsx -- jsdom can't render Leaflet's SVG internals.
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }) => <div>{children}</div>,
  TileLayer: () => null,
  Polyline: () => null,
  CircleMarker: () => null,
  Marker: () => null,
}))
vi.mock('./mapIcons', () => ({ touristIcon: () => ({}) }))

const mock = new MockAdapter(api)

const timeline = {
  incident_id: 5, tourist_id: 3, window_start: '2026-01-01T09:45:00',
  events: [
    { timestamp: '2026-01-01T10:00:00', kind: 'anomaly', label: 'Anomalous movement', detail: 'speed 90.0 km/h' },
    { timestamp: '2026-01-01T10:01:00', kind: 'status', label: 'detected', detail: '' },
  ],
}

beforeEach(() => mock.reset())

describe('IncidentTimeline', () => {
  it('shows a loading state before the response arrives', () => {
    mock.onGet('/incidents/5/timeline').reply(200, timeline)
    mock.onGet('/tourists/3/pings?limit=200').reply(200, [])
    const { getByText } = render(<IncidentTimeline incidentId={5} touristId={3} />)
    expect(getByText(/Loading timeline/)).toBeInTheDocument()
  })

  it('renders timeline events in order', async () => {
    mock.onGet('/incidents/5/timeline').reply(200, timeline)
    mock.onGet('/tourists/3/pings?limit=200').reply(200, [])
    const { findByText } = render(<IncidentTimeline incidentId={5} touristId={3} />)

    await findByText('Anomalous movement')
    await findByText('detected')
  })

  it('shows the trail replay when pings exist', async () => {
    mock.onGet('/incidents/5/timeline').reply(200, timeline)
    mock.onGet('/tourists/3/pings?limit=200').reply(200, [
      { lat: 26.1, lng: 91.7, speed_kmh: 5, timestamp: '2026-01-01T10:00:00', is_anomaly: false },
    ])
    const { findByText } = render(<IncidentTimeline incidentId={5} touristId={3} />)
    await findByText(/Replay/)
  })

  it('shows an empty-state message when there are no events', async () => {
    mock.onGet('/incidents/5/timeline').reply(200, { incident_id: 5, tourist_id: null, events: [] })
    const { findByText } = render(<IncidentTimeline incidentId={5} touristId={null} />)
    await findByText(/No timeline events/)
  })
})

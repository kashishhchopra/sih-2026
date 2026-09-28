import { describe, it, expect, beforeEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import api from '../../api'
import ResponderConsole from './ResponderConsole'

vi.mock('../../useWebSocket', () => ({ default: () => ({ connected: true }) }))

// jsdom can't render real Leaflet internals -- stub to inert placeholders,
// same approach as Dashboard/RoutePicker tests.
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }) => <div data-testid="map">{children}</div>,
  TileLayer: () => null,
  Marker: ({ children }) => <div data-testid="marker">{children}</div>,
  Popup: ({ children }) => <div data-testid="popup">{children}</div>,
}))

const mock = new MockAdapter(api)

const INCIDENTS = [
  { id: 1, tourist_id: 10, type: 'sos', severity: 'critical', status: 'dispatched',
    escalation_stage: 'control_room', description: 'SOS from field',
    lat: 26.15, lng: 91.74, detected_at: '2026-01-01T10:00:00' },
]

beforeEach(() => {
  mock.reset()
  mock.onGet('/incidents/mine').reply(200, INCIDENTS)
  mock.onGet('/tourists/10').reply(200, {
    id: 10, full_name: 'Victim Tourist', phone: '+91-90000-00000', digital_id: 'STS-DEMO001',
  })
})

describe('ResponderConsole', () => {
  it('lists incidents assigned to the responder with tourist info', async () => {
    const { findByText, findAllByText } = render(<ResponderConsole />)
    await findByText('#1')
    const matches = await findAllByText(/Victim Tourist/)
    expect(matches.length).toBeGreaterThan(0)
  })

  it('shows an empty state when nothing is assigned', async () => {
    mock.onGet('/incidents/mine').reply(200, [])
    const { findByText } = render(<ResponderConsole />)
    await findByText(/No incidents currently assigned/)
  })

  it('acknowledging an incident calls the acknowledge endpoint and refreshes', async () => {
    mock.onPost('/incidents/1/acknowledge').reply(200, {})
    const { findByText } = render(<ResponderConsole />)
    const btn = await findByText('Acknowledge')
    fireEvent.click(btn)

    await findByText('#1') // still renders after refresh
    expect(mock.history.post.some((r) => r.url === '/incidents/1/acknowledge')).toBe(true)
  })

  it('resolving an incident calls PATCH with status=resolved', async () => {
    mock.onPatch('/incidents/1').reply(200, {})
    const { findByText } = render(<ResponderConsole />)
    const btn = await findByText('Resolve')
    fireEvent.click(btn)

    await findByText('#1')
    const patchCall = mock.history.patch.find((r) => r.url === '/incidents/1')
    expect(JSON.parse(patchCall.data).status).toBe('resolved')
  })
})

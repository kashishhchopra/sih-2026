import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, fireEvent, waitFor, screen } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import '../i18n' // initializes i18next so t() resolves real strings, not raw keys
import api from '../api'
import EmergencyModeCard from './EmergencyModeCard'

let wsCallback = null
vi.mock('../useWebSocket', () => ({
  default: (cb) => { wsCallback = cb; return { connected: true } },
}))

const mock = new MockAdapter(api)

beforeEach(() => {
  mock.reset()
  wsCallback = null
})

const sosSent = {
  incident_id: 7, silent: false, status: 'dispatched', live_tracking_active: true,
  station_id: 1, station_name: 'Central Police Station',
  nearest_unit: { name: 'Unit Alpha', station: 'Central PS', distance_km: 1.2 },
}

describe('EmergencyModeCard', () => {
  it('renders nothing when there is no active SOS', () => {
    const { container } = render(<EmergencyModeCard sosSent={null} tid={1} posRef={{ current: [26.1, 91.7] }} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('never shows for a silent/duress SOS, even though tracking is still active underneath', () => {
    const { container } = render(
      <EmergencyModeCard sosSent={{ ...sosSent, silent: true }} tid={1} posRef={{ current: [26.1, 91.7] }} />
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('shows Emergency Mode with station, response and demo-mode disclosure for a visible SOS', async () => {
    mock.onPost('/incidents/7/location').reply(201, { status: 'ok' })
    const { findByText } = render(
      <EmergencyModeCard sosSent={sosSent} tid={1} posRef={{ current: [26.1445, 91.7362] }} />
    )
    await findByText('🚨 Emergency Mode')
    expect(screen.getByText('Central Police Station')).toBeInTheDocument()
    expect(screen.getByText('Officer assigned')).toBeInTheDocument()
    // SIMULATE_GPS defaults on in this test env -- must say so, never claim a real fix.
    await findByText(/Demo mode/)
  })

  it('goes LIVE once the first location post succeeds', async () => {
    mock.onPost('/incidents/7/location').reply(201, { status: 'ok' })
    render(
      <EmergencyModeCard sosSent={sosSent} tid={1} posRef={{ current: [26.1445, 91.7362] }} />
    )
    await waitFor(() => expect(screen.getAllByText('LIVE').length).toBeGreaterThan(0))
  })

  it('requires a second tap to actually cancel the emergency', async () => {
    mock.onPost('/incidents/7/location').reply(201, { status: 'ok' })
    mock.onPost('/incidents/7/stop-tracking').reply(200, { status: 'stopped' })
    const { findByText, getByText } = render(
      <EmergencyModeCard sosSent={sosSent} tid={1} posRef={{ current: [26.1445, 91.7362] }} />
    )
    await findByText('🚨 Emergency Mode')
    fireEvent.click(getByText('Cancel Emergency'))
    expect(getByText('Tap again to confirm')).toBeInTheDocument()
    expect(mock.history.post.filter((r) => r.url === '/incidents/7/stop-tracking')).toHaveLength(0)

    fireEvent.click(getByText('Tap again to confirm'))
    await waitFor(() => expect(mock.history.post.some((r) => r.url === '/incidents/7/stop-tracking')).toBe(true))
    await findByText('Emergency Resolved')
  })

  it('shows "Emergency Resolved" once police/operator stop tracking remotely', async () => {
    mock.onPost('/incidents/7/location').reply(201, { status: 'ok' })
    const { findByText } = render(
      <EmergencyModeCard sosSent={sosSent} tid={1} posRef={{ current: [26.1445, 91.7362] }} />
    )
    await findByText('🚨 Emergency Mode')
    wsCallback({ event: 'emergency_tracking_stopped', incident_id: 7, reason: 'incident resolved' })
    await findByText('Live emergency location sharing has stopped.')
  })
})

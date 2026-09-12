import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import api from '../../api'
import Analytics from './Analytics'

// jsdom has no real <canvas> (the `canvas` npm package isn't installed), and
// leaflet.heat's internal renderer calls HTMLCanvasElement.getContext() and
// throws when it gets null -- an uncaught error inside HeatmapLayer's effect
// that crashes the whole page in tests. None of these tests assert on the
// heatmap's pixels, only on the surrounding page text, so stub the layer out
// the same way this codebase already stubs non-essential child components
// (e.g. useSpeechRecognition in VoiceAssistantButton.test.jsx).
vi.mock('../../components/HeatmapLayer.jsx', () => ({ default: () => null }))

const mock = new MockAdapter(api)

const summaryBody = {
  total_tourists: 10, active_tourists: 8, sos_active: 1, missing: 0,
  total_incidents: 5, open_incidents: 2, active_alerts: 3,
  avg_safety_score: 78.4, avg_response_time_seconds: 145, total_zones: 4,
}

function mockBaseEndpoints() {
  mock.onGet('/analytics/summary').reply(200, summaryBody)
  mock.onGet('/analytics/incidents-over-time').reply((config) => {
    const g = config.params?.granularity || 'day'
    return [200, [{ date: g === 'month' ? '2026-09' : g === 'week' ? '2026-W36' : '2026-09-01', count: 3 }]]
  })
  mock.onGet('/analytics/alerts-by-type').reply(200, [{ type: 'geofence', count: 4 }])
  mock.onGet('/analytics/zone-risk').reply(200, [
    { zone: 'Old Market', risk_level: 'high', crime_index: 72, alert_count: 3 },
  ])
  mock.onGet('/analytics/severity-breakdown').reply(200, [{ severity: 'high', count: 2 }])
  mock.onGet('/analytics/incident-types').reply(200, {
    by_type: [{ type: 'sos', count: 2 }, { type: 'missing_person', count: 1 }],
    sos: { total: 2, active: 1, resolved: 1 },
  })
  mock.onGet('/analytics/incidents-heatmap').reply(200, [{ lat: 26.14, lng: 91.73 }])
  mock.onGet('/analytics/police-performance').reply(200, {
    stations: [{
      station_id: 1, station: 'Central Station', cases_handled: 5, pending: 2,
      resolved: 3, avg_response_time_seconds: 90, avg_resolution_time_seconds: 600,
      transfers_received: 1,
    }],
    total_transfers: 1,
  })
  mock.onGet('/analytics/tourist-activity').reply(200, {
    total_tourists: 10, active_tourists: 8, domestic_tourists: 7, international_tourists: 3,
    popular_destinations: [{ destination: 'Kaziranga National Park', count: 4 }],
  })
  mock.onGet('/zones/crowd-density').reply(200, [
    { zone_id: 1, zone: 'Old Market', tourist_count: 6, density: 'high', overcrowded: true },
  ])
  mock.onGet('/ml/status').reply(200, {
    artifacts: {}, inference_mode: 'rule-based fallback', hotzones_available: false,
    live_pings_collected: 120, anomalies_flagged: 4,
  })
  mock.onGet('/cctv').reply(200, {
    cameras: [], summary: {
      total: 3, live: 2, offline: 0, no_stream: 1, unavailable: 0,
      provider: null, provider_configured: false, refresh_interval_seconds: 30,
    },
  })
}


function statValue(container, label) {
  const labelEl = Array.from(container.querySelectorAll('div')).find((d) => d.textContent === label)
  return labelEl?.nextElementSibling?.textContent
}

beforeEach(() => { mock.reset() })

describe('Analytics page', () => {
  it('renders the top-level KPIs from real summary data', async () => {
    mockBaseEndpoints()
    const { findByText, container } = render(<Analytics />)
    await findByText('Total Incidents', undefined, { timeout: 4000 })
    expect(statValue(container, 'Total Incidents')).toBe('5')
    expect(statValue(container, 'Avg Response Time')).toBe('145s')
  })

  it('shows SOS & Emergency Analytics from the real incident-types endpoint', async () => {
    mockBaseEndpoints()
    const { findByText, container } = render(<Analytics />)
    await findByText('🚨 SOS & Emergency Analytics', undefined, { timeout: 4000 })
    expect(statValue(container, 'Total SOS Cases')).toBe('2')
    expect(statValue(container, 'Active SOS')).toBe('1')
    expect(statValue(container, 'Resolved SOS')).toBe('1')
  })

  it('re-fetches the trend chart with the selected granularity', async () => {
    mockBaseEndpoints()
    const { findByText, getByText } = render(<Analytics />)
    await findByText('Incidents Over Time', undefined, { timeout: 4000 })
    fireEvent.click(getByText('Weekly'))
    await waitFor(() => {
      const last = mock.history.get.filter((c) => c.url === '/analytics/incidents-over-time').at(-1)
      expect(last.params).toEqual({ granularity: 'week' })
    })
    fireEvent.click(getByText('Monthly'))
    await waitFor(() => {
      const last = mock.history.get.filter((c) => c.url === '/analytics/incidents-over-time').at(-1)
      expect(last.params).toEqual({ granularity: 'month' })
    })
  })

  it('renders Police Performance from real per-station data', async () => {
    mockBaseEndpoints()
    const { findByText } = render(<Analytics />)
    expect(await findByText('Central Station', undefined, { timeout: 4000 })).toBeInTheDocument()
    expect(await findByText('90s', undefined, { timeout: 4000 })).toBeInTheDocument() // avg response
    expect(await findByText('10m', undefined, { timeout: 4000 })).toBeInTheDocument() // avg resolution (600s)
    expect(await findByText(/1 inter-station case transfer/, undefined, { timeout: 4000 })).toBeInTheDocument()
  })

  it('shows an honest empty state when no stations exist', async () => {
    mockBaseEndpoints()
    mock.onGet('/analytics/police-performance').reply(200, { stations: [], total_transfers: 0 })
    const { findByText } = render(<Analytics />)
    expect(await findByText(/No stations registered yet/i, undefined, { timeout: 4000 })).toBeInTheDocument()
  })

  it('renders Tourist Activity: domestic/international split and popular destinations', async () => {
    mockBaseEndpoints()
    const { findByText, queryByText } = render(<Analytics />)
    expect(await findByText('Domestic vs. International', undefined, { timeout: 4000 })).toBeInTheDocument()
    // Recharts' <ResponsiveContainer> needs real element dimensions to draw
    // bars/axis labels, which jsdom doesn't provide -- so the destination
    // name itself never reaches the DOM here. Assert on the branch that
    // *is* observable instead: with a non-empty popular_destinations list,
    // the "no data" empty state must not be shown.
    await findByText('Popular Destinations (confirmed itineraries)', undefined, { timeout: 4000 })
    expect(queryByText(/No confirmed itinerary destinations yet/i)).not.toBeInTheDocument()
  })

  it('shows an honest empty state when no confirmed destinations exist', async () => {
    mockBaseEndpoints()
    mock.onGet('/analytics/tourist-activity').reply(200, {
      total_tourists: 0, active_tourists: 0, domestic_tourists: 0,
      international_tourists: 0, popular_destinations: [],
    })
    const { findByText } = render(<Analytics />)
    expect(await findByText(/No confirmed itinerary destinations yet/i, undefined, { timeout: 4000 })).toBeInTheDocument()
  })

  it('renders CCTV & AI Analytics from the real /cctv and /ml/status data', async () => {
    mockBaseEndpoints()
    const { findByText, container } = render(<Analytics />)
    await findByText('📹 CCTV & AI Analytics', undefined, { timeout: 4000 })
    expect(statValue(container, 'AI Anomalies Flagged')).toBe('4')
    expect(await findByText('rule-based fallback', { exact: false }, { timeout: 4000 })).toBeInTheDocument()
  })

  it('never claims a camera is live from CCTV summary alone -- reads counts from the API', async () => {
    mockBaseEndpoints()
    mock.onGet('/cctv').reply(200, {
      cameras: [], summary: {
        total: 5, live: 0, offline: 5, no_stream: 0, unavailable: 0,
        provider: 'json', provider_configured: true, refresh_interval_seconds: 30,
      },
    })
    const { findByText, container } = render(<Analytics />)
    await findByText('📹 CCTV & AI Analytics', undefined, { timeout: 4000 })
    await findByText('Cameras Live', undefined, { timeout: 4000 })
    expect(statValue(container, 'Cameras Live')).toBe('0')
  })

  it('downloads the Excel report via the real endpoint', async () => {
    mockBaseEndpoints()
    mock.onGet('/analytics/excel').reply(200, new Blob(['x']))
    const { findByText } = render(<Analytics />)
    const btn = await findByText(/Download Excel Report/i, undefined, { timeout: 4000 })
    fireEvent.click(btn)
    await waitFor(() => {
      expect(mock.history.get.some((c) => c.url === '/analytics/excel')).toBe(true)
    })
  })

  it('shows the incident density heatmap section with a no-data message when empty', async () => {
    mockBaseEndpoints()
    mock.onGet('/analytics/incidents-heatmap').reply(200, [])
    const { findByText } = render(<Analytics />)
    expect(await findByText('Incident Density Heatmap', undefined, { timeout: 4000 })).toBeInTheDocument()
    expect(await findByText(/No located incidents yet/i, undefined, { timeout: 4000 })).toBeInTheDocument()
  })
})

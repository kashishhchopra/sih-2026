import { describe, it, expect, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import i18n from '../i18n' // initializes i18next so t() resolves real strings, not raw keys
import api from '../api'
import DisasterBanner from './DisasterBanner'

const mock = new MockAdapter(api)

beforeEach(() => mock.reset())

describe('DisasterBanner', () => {
  it('renders nothing when there are no active advisories', async () => {
    mock.onGet('/tourists/1/disasters').reply(200, [])
    const { container } = render(<DisasterBanner touristId={1} />)
    // wait a tick for the fetch to resolve
    await new Promise((r) => setTimeout(r, 10))
    expect(container.firstChild).toBeNull()
  })

  it('shows an active advisory', async () => {
    mock.onGet('/tourists/1/disasters').reply(200, [
      { id: 1, zone_id: 2, hazard_type: 'flood', severity: 'high',
        message: 'Flash flood advisory.', source: 'simulated', active: true,
        issued_at: '2026-01-01T00:00:00', expires_at: null },
    ])
    const { findByText } = render(<DisasterBanner touristId={1} />)
    await findByText(/Flash flood advisory/)
    await findByText(/^flood advisory$/i)
  })

  it('shows source, zone, instructions and title from the real advisory data', async () => {
    mock.onGet('/tourists/1/disasters').reply(200, [
      { id: 2, zone_id: 3, hazard_type: 'extreme_heat', severity: 'critical',
        title: 'Extreme Heat Advisory', message: 'Current conditions: clear sky (46.0°C).',
        instructions: 'Stay hydrated, avoid direct sun 11am-4pm.', source: 'openweathermap',
        active: true, zone_name: 'Old Market High-Risk Zone',
        issued_at: '2026-01-01T00:00:00', expires_at: '2026-01-01T06:00:00' },
    ])
    const { findByText } = render(<DisasterBanner touristId={1} />)
    await findByText('Extreme Heat Advisory')
    await findByText(/Current conditions: clear sky/)
    await findByText(/Stay hydrated/)
    await findByText(/Old Market High-Risk Zone/)
    await findByText(/openweathermap/)
  })

  it('does not fetch a translation when the UI language is English', async () => {
    await i18n.changeLanguage('en') // this app's i18n singleton is process-wide -- pin it explicitly
    mock.onGet('/tourists/1/disasters').reply(200, [
      { id: 3, zone_id: 2, hazard_type: 'storm', severity: 'high',
        message: 'Severe storm warning.', source: 'simulated', active: true,
        issued_at: '2026-01-01T00:00:00', expires_at: null },
    ])
    const { findByText } = render(<DisasterBanner touristId={1} />)
    await findByText(/Severe storm warning/)
    expect(mock.history.post.filter((r) => r.url === '/translate/text')).toHaveLength(0)
  })

  it('translates the advisory message for a non-English UI language', async () => {
    await i18n.changeLanguage('hi')
    mock.onGet('/tourists/1/disasters').reply(200, [
      { id: 4, zone_id: 2, hazard_type: 'flood', severity: 'high',
        message: 'Flash flood advisory.', source: 'simulated', active: true,
        issued_at: '2026-01-01T00:00:00', expires_at: null },
    ])
    mock.onPost('/translate/text').reply(200, { text: 'बाढ़ की चेतावनी।', demo: false })
    const { findByText } = render(<DisasterBanner touristId={1} />)
    await findByText('बाढ़ की चेतावनी।')
    await i18n.changeLanguage('en') // restore for any test that runs after this one
  })
})

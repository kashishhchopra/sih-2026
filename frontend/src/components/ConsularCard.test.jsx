import { describe, it, expect, beforeEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import '../i18n' // initializes i18next so t() resolves real strings, not raw keys
import api from '../api'
import ConsularCard from './ConsularCard'

const mock = new MockAdapter(api)

const foreignCard = {
  digital_id: 'STS-JP1', emergency_numbers: { all_in_one: '112' },
  consular: {
    country_code: 'JP', country_name: 'Japan', mission_type: 'Embassy',
    city: 'New Delhi', phone: '+91-11-4610-4610', distance_km: 3.2,
  },
  country_guidance: {
    helpline_language: 'Japanese',
    visa_overstay_note: 'Contact your nearest FRRO before your visa expires.',
    common_scams: ['Unofficial travel agents near stations'],
    police_reporting_steps: ['Call 112', 'File an FIR'],
  },
}

const indianCard = {
  digital_id: 'STS-IN1', emergency_numbers: { all_in_one: '112' },
}

beforeEach(() => mock.reset())

describe('ConsularCard', () => {
  it('renders nothing while loading', () => {
    mock.onGet('/tourists/1/safety-card').reply(() => new Promise(() => {}))
    const { container } = render(<ConsularCard touristId={1} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing for an Indian national (no consular key)', async () => {
    mock.onGet('/tourists/1/safety-card').reply(200, indianCard)
    const { container } = render(<ConsularCard touristId={1} />)
    await new Promise((r) => setTimeout(r, 10))
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the mission name, phone, and distance for a foreign national', async () => {
    mock.onGet('/tourists/2/safety-card').reply(200, foreignCard)
    const { findByText } = render(<ConsularCard touristId={2} />)
    await findByText(/Japan Embassy/)
    await findByText(/3.2 km away/)
    await findByText('☎ +91-11-4610-4610')
  })

  it('the phone link is a tel: link', async () => {
    mock.onGet('/tourists/2/safety-card').reply(200, foreignCard)
    const { findByText } = render(<ConsularCard touristId={2} />)
    const link = await findByText('☎ +91-11-4610-4610')
    expect(link.closest('a')).toHaveAttribute('href', 'tel:+91-11-4610-4610')
  })

  it('expands guidance on click and shows scams/reporting steps', async () => {
    mock.onGet('/tourists/2/safety-card').reply(200, foreignCard)
    const { findByText } = render(<ConsularCard touristId={2} />)
    const summary = await findByText(/Guidance for Japanese speakers/)
    fireEvent.click(summary)
    await findByText(/Unofficial travel agents/)
    await findByText('Call 112')
  })
})

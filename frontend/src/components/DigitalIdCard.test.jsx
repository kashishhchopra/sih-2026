import { describe, it, expect, beforeEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import '../i18n' // initializes i18next so t() resolves real strings, not raw keys
import api from '../api'
import DigitalIdCard from './DigitalIdCard'

const mock = new MockAdapter(api)

const card = {
  digital_id: 'STS-ABC123', full_name: 'Kashish Chopra', photo: 'data:image/png;base64,abc',
  hotel: 'ABC Residency', trip_start: '2026-01-01T00:00:00', trip_end: '2026-01-10T00:00:00',
  id_status: 'active', issued_at: '2026-01-01T00:00:00', qr_png_base64: 'data:image/png;base64,qr',
}

beforeEach(() => mock.reset())

describe('DigitalIdCard', () => {
  it('is collapsed by default and does not fetch', () => {
    const { queryByAltText } = render(<DigitalIdCard touristId={1} />)
    expect(queryByAltText(/QR code/)).not.toBeInTheDocument()
  })

  it('fetches and shows the card when opened', async () => {
    mock.onGet('/tourists/1/digital-id').reply(200, card)
    const { getByText, findByText } = render(<DigitalIdCard touristId={1} />)
    fireEvent.click(getByText(/Digital Tourist Safety ID/))
    await findByText('Kashish Chopra')
    await findByText('STS-ABC123')
    await findByText('ABC Residency')
    await findByText(/ID VERIFIED/)
  })

  it('regenerating replaces the QR after confirmation', async () => {
    mock.onGet('/tourists/1/digital-id').reply(200, card)
    mock.onPost('/tourists/1/digital-id/regenerate').reply(200, {
      ...card, qr_png_base64: 'data:image/png;base64,newqr',
    })
    const { getByText, findByText, findByAltText } = render(<DigitalIdCard touristId={1} />)
    fireEvent.click(getByText(/Digital Tourist Safety ID/))
    await findByText('Kashish Chopra')

    fireEvent.click(getByText('Regenerate QR'))
    await findByText(/Continue\?/)
    fireEvent.click(getByText('Confirm'))

    const img = await findByAltText('Digital ID QR code')
    await new Promise((r) => setTimeout(r, 0))
    expect(mock.history.post.some((r) => r.url === '/tourists/1/digital-id/regenerate')).toBe(true)
    expect(img).toBeInTheDocument()
  })

  it('shows the expired status badge', async () => {
    mock.onGet('/tourists/1/digital-id').reply(200, { ...card, id_status: 'expired' })
    const { getByText, findByText } = render(<DigitalIdCard touristId={1} />)
    fireEvent.click(getByText(/Digital Tourist Safety ID/))
    await findByText(/EXPIRED/)
  })
})

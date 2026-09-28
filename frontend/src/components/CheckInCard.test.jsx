import { describe, it, beforeEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import '../i18n' // initializes i18next so t() resolves real strings, not raw keys
import api from '../api'
import CheckInCard from './CheckInCard'

const mock = new MockAdapter(api)

beforeEach(() => mock.reset())

describe('CheckInCard', () => {
  it('shows an empty state with no planned outings', async () => {
    mock.onGet('/tourists/1/checkins').reply(200, [])
    const { findByText } = render(<CheckInCard touristId={1} />)
    await findByText(/No planned outings/)
  })

  it('lists a planned check-in with its status', async () => {
    mock.onGet('/tourists/1/checkins').reply(200, [
      { id: 1, destination_name: 'Riverside trek', dest_lat: null, dest_lng: null,
        expected_return_at: '2026-01-01T18:00:00', checked_in_at: null, status: 'planned',
        created_at: '2026-01-01T10:00:00' },
    ])
    const { findByText } = render(<CheckInCard touristId={1} />)
    await findByText('Riverside trek')
    await findByText('planned')
  })

  it('shows missed check-ins distinctly', async () => {
    mock.onGet('/tourists/1/checkins').reply(200, [
      { id: 1, destination_name: 'Hillside', dest_lat: null, dest_lng: null,
        expected_return_at: '2026-01-01T18:00:00', checked_in_at: null, status: 'missed',
        created_at: '2026-01-01T10:00:00' },
    ])
    const { findByText } = render(<CheckInCard touristId={1} />)
    await findByText('missed')
  })

  it('checking in updates the list', async () => {
    mock.onGet('/tourists/1/checkins').replyOnce(200, [
      { id: 1, destination_name: 'Market', dest_lat: null, dest_lng: null,
        expected_return_at: '2026-01-01T18:00:00', checked_in_at: null, status: 'planned',
        created_at: '2026-01-01T10:00:00' },
    ])
    mock.onPost('/tourists/1/checkins/1/checkin').reply(200, {})
    mock.onGet('/tourists/1/checkins').reply(200, [
      { id: 1, destination_name: 'Market', dest_lat: null, dest_lng: null,
        expected_return_at: '2026-01-01T18:00:00', checked_in_at: '2026-01-01T17:00:00',
        status: 'checked_in', created_at: '2026-01-01T10:00:00' },
    ])
    const { findByText } = render(<CheckInCard touristId={1} />)
    fireEvent.click(await findByText(/I'm back safe/))
    await findByText(/No planned outings/)
  })
})

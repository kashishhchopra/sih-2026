import { describe, it, expect, beforeEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import api from '../api'
import { DuressPinSettings, DuressLockButton } from './DuressLock'

const mock = new MockAdapter(api)

beforeEach(() => mock.reset())

describe('DuressPinSettings', () => {
  it('disables Set PIN until a valid 4-8 digit PIN is entered', () => {
    const { getByText, getByPlaceholderText } = render(<DuressPinSettings touristId={1} />)
    const button = getByText('Set PIN')
    expect(button).toBeDisabled()
    fireEvent.change(getByPlaceholderText(/4-8 digit PIN/), { target: { value: '12' } })
    expect(button).toBeDisabled()
    fireEvent.change(getByPlaceholderText(/4-8 digit PIN/), { target: { value: '1234' } })
    expect(button).not.toBeDisabled()
  })

  it('strips non-digit characters from input', () => {
    const { getByPlaceholderText } = render(<DuressPinSettings touristId={1} />)
    fireEvent.change(getByPlaceholderText(/4-8 digit PIN/), { target: { value: '12a3b4' } })
    expect(getByPlaceholderText(/4-8 digit PIN/).value).toBe('1234')
  })

  it('saves the PIN and shows confirmation', async () => {
    mock.onPost('/tourists/1/duress-pin').reply(200, { tourist_id: 1, duress_pin_set: true })
    const { getByText, getByPlaceholderText, findByText } = render(<DuressPinSettings touristId={1} />)
    fireEvent.change(getByPlaceholderText(/4-8 digit PIN/), { target: { value: '4321' } })
    fireEvent.click(getByText('Set PIN'))
    await findByText(/Duress PIN saved/)
  })
})

describe('DuressLockButton', () => {
  it('opens a passcode pad and shows the same message on any entry', async () => {
    mock.onPost('/tourists/1/sos/duress').reply(400, { detail: 'Incorrect PIN' })
    const { getByTitle, getByText, findByText } = render(
      <DuressLockButton touristId={1} getPosition={() => [26.1, 91.7]} />
    )
    fireEvent.click(getByTitle('App lock'))
    fireEvent.click(getByText('1'))
    fireEvent.click(getByText('2'))
    fireEvent.click(getByText('3'))
    fireEvent.click(getByText('4'))
    fireEvent.click(getByText('✓'))
    await findByText(/Incorrect passcode/)
  })

  it('does not call the API when no position is known', () => {
    const { getByTitle, getByText } = render(
      <DuressLockButton touristId={1} getPosition={() => null} />
    )
    fireEvent.click(getByTitle('App lock'))
    fireEvent.click(getByText('✓'))
    expect(mock.history.post.length).toBe(0)
  })
})

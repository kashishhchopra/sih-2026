import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ForgotPassword from './ForgotPassword'
import { ThemeProvider } from '../theme.jsx'

vi.mock('../api', () => ({ default: { post: vi.fn() } }))
import api from '../api'

const renderPage = () => render(
  <MemoryRouter><ThemeProvider><ForgotPassword /></ThemeProvider></MemoryRouter>,
)

// resetAllMocks (not clearAllMocks) so a queued mockResolvedValueOnce from
// one test can never leak into the next.
beforeEach(() => vi.resetAllMocks())

describe('ForgotPassword', () => {
  it('starts on the request-code step', () => {
    renderPage()
    expect(screen.getByText(/send reset code/i)).toBeInTheDocument()
  })

  it('requesting a code advances to the reset step and shows the server message', async () => {
    api.post.mockResolvedValue({ data: { message: 'If that email is registered...' } })
    renderPage()

    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'a@b.com' } })
    fireEvent.click(screen.getByText(/send reset code/i))

    await waitFor(() => expect(screen.getByText(/if that email is registered/i)).toBeInTheDocument())
    expect(api.post).toHaveBeenCalledWith('/auth/forgot-password', { email: 'a@b.com' })
    expect(screen.getByLabelText(/reset code/i)).toBeInTheDocument()
  })

  it('never surfaces per-email information from the request step', async () => {
    // The endpoint returns the same generic message regardless of the email;
    // the UI must display exactly what came back, not infer anything.
    api.post.mockResolvedValue({ data: { message: 'Generic ack.' } })
    renderPage()
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'nobody@nowhere.com' } })
    fireEvent.click(screen.getByText(/send reset code/i))
    await waitFor(() => expect(screen.getByText('Generic ack.')).toBeInTheDocument())
  })

  it('submitting a valid code and new password completes the flow', async () => {
    api.post.mockResolvedValueOnce({ data: { message: 'sent' } })
    renderPage()
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'a@b.com' } })
    fireEvent.click(screen.getByText(/send reset code/i))
    await waitFor(() => expect(screen.getByLabelText(/reset code/i)).toBeInTheDocument())

    api.post.mockResolvedValueOnce({})
    fireEvent.change(screen.getByLabelText(/reset code/i), { target: { value: 'abc123' } })
    fireEvent.change(screen.getByLabelText(/new password/i), { target: { value: 'Newpass123!' } })
    fireEvent.click(screen.getByText('Reset password'))

    await waitFor(() => expect(screen.getByText(/password has been reset/i)).toBeInTheDocument())
    expect(api.post).toHaveBeenLastCalledWith('/auth/reset-password',
      { token: 'abc123', new_password: 'Newpass123!' })
  })

  it('shows a server-provided error for an invalid or expired code', async () => {
    api.post.mockResolvedValueOnce({ data: { message: 'sent' } })
    renderPage()
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'a@b.com' } })
    fireEvent.click(screen.getByText(/send reset code/i))
    await waitFor(() => expect(screen.getByLabelText(/reset code/i)).toBeInTheDocument())

    api.post.mockRejectedValueOnce({ response: { data: { detail: 'Invalid or expired reset token' } } })
    fireEvent.change(screen.getByLabelText(/reset code/i), { target: { value: 'wrong' } })
    fireEvent.change(screen.getByLabelText(/new password/i), { target: { value: 'Newpass123!' } })
    fireEvent.click(screen.getByText('Reset password'))

    await waitFor(() => expect(screen.getByText('Invalid or expired reset token')).toBeInTheDocument())
    // Must stay on the reset step, not silently advance.
    expect(screen.queryByText(/password has been reset/i)).not.toBeInTheDocument()
  })

  it('links back to the login page', () => {
    renderPage()
    expect(screen.getByText('Back to sign in')).toBeInTheDocument()
  })
})

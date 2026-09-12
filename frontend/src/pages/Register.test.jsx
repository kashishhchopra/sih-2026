import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { useEffect } from 'react'
import Register from './Register.jsx'

vi.mock('../api', () => ({ default: { post: vi.fn() } }))
vi.mock('../auth.jsx', () => ({ useAuth: () => ({ login: vi.fn() }) }))
// The 3-step liveness check (components/LivenessCapture.jsx) has its own
// dedicated test suite (LivenessCapture.test.jsx) covering the real
// detection flow with MediaPipe mocked. Here it just needs to behave like
// "unavailable in this browser" so every existing registration test below
// exercises the pre-existing plain live-capture fallback exactly as it did
// before this feature was added -- these tests are about the registration
// flow, not about liveness detection.
function MockLivenessCapture({ onUnavailable }) {
  useEffect(() => { onUnavailable() }, [onUnavailable])
  return null
}
vi.mock('../components/LivenessCapture.jsx', () => ({ default: MockLivenessCapture }))
import api from '../api'

const renderPage = () => render(<MemoryRouter><Register /></MemoryRouter>)

beforeEach(() => {
  vi.resetAllMocks()

  // jsdom has no real camera or <canvas> 2D context -- stub just enough of
  // the LivePhotoCapture path (components/live capture lives in this same
  // file) for a "Capture Photo" click to produce a photo and advance the
  // step, without needing an actual video/canvas pipeline.
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [] }) },
  })
  HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue()
  HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({ drawImage: vi.fn() })
  HTMLCanvasElement.prototype.toDataURL = vi.fn().mockReturnValue('data:image/jpeg;base64,test')
  // jsdom never actually decodes an <img>, so `_resizePhoto`'s onload would
  // never fire -- fire it synchronously on src assignment instead.
  global.Image = class {
    set src(_v) { this.onload?.() }
  }
})

function fillIdentityAndAdvance(documentType = 'aadhaar') {
  fireEvent.change(screen.getByPlaceholderText('Enter Full Name'), { target: { value: 'Aarav Sharma' } })
  fireEvent.change(screen.getByLabelText(/Select Verification Method/i), { target: { value: documentType } })
  fireEvent.click(screen.getByText('Next'))
}

// Captures a photo (live camera step, mandatory) and advances past it.
async function capturePhotoAndAdvance() {
  expect(screen.getByText(/— Photo/)).toBeInTheDocument()
  const captureBtn = await screen.findByText('📸 Capture Photo')
  await waitFor(() => expect(captureBtn).not.toBeDisabled())
  fireEvent.click(captureBtn)
  await screen.findByText('Retake photo')
  fireEvent.click(screen.getByText('Next'))
}

describe('Register', () => {
  it('starts on the Identity step', () => {
    renderPage()
    expect(screen.getByText(/Step 1 of/)).toBeInTheDocument()
    expect(screen.getByText(/— Identity/)).toBeInTheDocument()
  })

  it('an aadhaar registration never shows a Visa & Travel step', () => {
    renderPage()
    fillIdentityAndAdvance('aadhaar')
    // Document step
    expect(screen.getByText(/— Document/)).toBeInTheDocument()
    expect(screen.queryByText('Visa & Travel')).not.toBeInTheDocument()
  })

  it('a passport registration inserts the Visa & Travel step after Document', () => {
    renderPage()
    fillIdentityAndAdvance('passport')
    expect(screen.getByText(/— Document/)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/Passport Number/i), { target: { value: 'A1234567' } })
    fireEvent.change(screen.getByLabelText(/Phone/i), { target: { value: '9876543210' } })
    fireEvent.change(screen.getByLabelText(/Country of Citizenship/i), { target: { value: 'JP' } })
    fireEvent.click(screen.getByText('Next'))

    expect(screen.getByText(/— Visa & Travel/)).toBeInTheDocument()
  })

  it('cannot advance past the Visa step without visa type and expiry', () => {
    renderPage()
    fillIdentityAndAdvance('passport')
    fireEvent.change(screen.getByLabelText(/Passport Number/i), { target: { value: 'A1234567' } })
    fireEvent.change(screen.getByLabelText(/Phone/i), { target: { value: '9876543210' } })
    fireEvent.change(screen.getByLabelText(/Country of Citizenship/i), { target: { value: 'JP' } })
    fireEvent.click(screen.getByText('Next'))
    expect(screen.getByText(/— Visa & Travel/)).toBeInTheDocument()

    // Visa Type/Expiry carry the `required` HTML attribute, so a browser
    // blocks the click via native constraint validation before this app's
    // own JS validator ever runs -- same pattern as every other required
    // field in this form. Assert we're still on the same step either way.
    fireEvent.click(screen.getByText('Next'))
    expect(screen.getByText(/— Visa & Travel/)).toBeInTheDocument()
  })

  it('cannot advance past the Photo step without capturing a photo', () => {
    renderPage()
    fillIdentityAndAdvance('aadhaar')
    fireEvent.change(screen.getByLabelText(/Aadhaar Number/i), { target: { value: '123456789012' } })
    fireEvent.change(screen.getByLabelText(/Phone/i), { target: { value: '9876543210' } })
    fireEvent.click(screen.getByText('Next'))  // -> Photo
    expect(screen.getByText(/— Photo/)).toBeInTheDocument()

    fireEvent.click(screen.getByText('Next'))
    expect(screen.getByText(/— Photo/)).toBeInTheDocument()
    expect(screen.getByText(/Please fill in the required fields/)).toBeInTheDocument()
  })

  it('sends visa fields in the submission payload for a passport registration', async () => {
    api.post.mockResolvedValue({ data: { digital_id: 'STS-TEST', trip_end: '2026-12-01T00:00:00' } })
    renderPage()
    fillIdentityAndAdvance('passport')

    fireEvent.change(screen.getByLabelText(/Passport Number/i), { target: { value: 'A1234567' } })
    fireEvent.change(screen.getByLabelText(/Phone/i), { target: { value: '9876543210' } })
    fireEvent.change(screen.getByLabelText(/Country of Citizenship/i), { target: { value: 'JP' } })
    fireEvent.click(screen.getByText('Next'))

    fireEvent.change(screen.getByLabelText(/Visa Type/i), { target: { value: 'Tourist' } })
    fireEvent.change(screen.getByLabelText(/Visa Expiry/i), { target: { value: '2026-12-31' } })
    fireEvent.click(screen.getByText('Next'))  // -> Photo

    await capturePhotoAndAdvance()  // -> Trip

    fireEvent.change(screen.getByLabelText(/Trip Start/i), { target: { value: '2026-11-01T09:00' } })
    fireEvent.change(screen.getByLabelText(/Trip End/i), { target: { value: '2026-11-10T09:00' } })
    fireEvent.click(screen.getByText('Next'))  // -> Emergency Contact
    fireEvent.click(screen.getByText('Next'))  // -> Account
    fireEvent.click(screen.getByText(/Get Your Unique Blockchain ID/))

    expect(api.post).toHaveBeenCalled()
    const [path, payload] = api.post.mock.calls[0]
    expect(path).toBe('/tourists')
    expect(payload.nationality).toBe('Japan')
    expect(payload.visa_type).toBe('Tourist')
    expect(payload.visa_expiry).toContain('2026-12-31')
    expect(payload.photo).toBe('data:image/jpeg;base64,test')
  })

  it('an aadhaar submission never includes visa fields', async () => {
    api.post.mockResolvedValue({ data: { digital_id: 'STS-TEST', trip_end: '2026-12-01T00:00:00' } })
    renderPage()
    fillIdentityAndAdvance('aadhaar')

    fireEvent.change(screen.getByLabelText(/Aadhaar Number/i), { target: { value: '123456789012' } })
    fireEvent.change(screen.getByLabelText(/Phone/i), { target: { value: '9876543210' } })
    fireEvent.click(screen.getByText('Next'))  // -> Photo

    await capturePhotoAndAdvance()  // -> Trip

    fireEvent.change(screen.getByLabelText(/Trip Start/i), { target: { value: '2026-11-01T09:00' } })
    fireEvent.change(screen.getByLabelText(/Trip End/i), { target: { value: '2026-11-10T09:00' } })
    fireEvent.click(screen.getByText('Next'))  // -> Emergency
    fireEvent.click(screen.getByText('Next'))  // -> Account
    fireEvent.click(screen.getByText(/Get Your Unique Blockchain ID/))

    const [, payload] = api.post.mock.calls[0]
    expect(payload.visa_type).toBeUndefined()
    expect(payload.visa_expiry).toBeUndefined()
  })

  // ---------------------------------------------------- identity validation
  it('filters digits and symbols out of the name field as they are typed', () => {
    renderPage()
    fireEvent.change(screen.getByPlaceholderText('Enter Full Name'), { target: { value: 'Rahul123@Sharma' } })
    expect(screen.getByPlaceholderText('Enter Full Name').value).toBe('RahulSharma')
  })

  it('cannot advance past Identity with an empty name', () => {
    renderPage()
    fireEvent.change(screen.getByLabelText(/Select Verification Method/i), { target: { value: 'aadhaar' } })
    fireEvent.click(screen.getByText('Next'))
    expect(screen.getByText(/— Identity/)).toBeInTheDocument()
  })

  it('filters non-digit characters and enforces the 6-9 start on the phone field', () => {
    renderPage()
    fillIdentityAndAdvance('aadhaar')
    const phoneInput = screen.getByLabelText(/Phone/i)
    fireEvent.change(phoneInput, { target: { value: '98765abc10' } })
    expect(phoneInput.value).toBe('9876510')
  })

  it('cannot advance past Document with an incomplete Aadhaar number', () => {
    renderPage()
    fillIdentityAndAdvance('aadhaar')
    fireEvent.change(screen.getByLabelText(/Aadhaar Number/i), { target: { value: '1234' } })
    fireEvent.change(screen.getByLabelText(/Phone/i), { target: { value: '9876543210' } })
    fireEvent.click(screen.getByText('Next'))
    expect(screen.getByText(/— Document/)).toBeInTheDocument()
    expect(screen.getByText(/Please fill in the required fields/)).toBeInTheDocument()
  })

  it('auto-uppercases a lowercase PAN and accepts it once complete', () => {
    renderPage()
    fillIdentityAndAdvance('pan')
    const panInput = screen.getByLabelText(/Pan Number/i)
    fireEvent.change(panInput, { target: { value: 'abcde1234f' } })
    expect(panInput.value).toBe('ABCDE1234F')
    fireEvent.change(screen.getByLabelText(/Phone/i), { target: { value: '9876543210' } })
    fireEvent.click(screen.getByText('Next'))
    expect(screen.getByText(/— Photo/)).toBeInTheDocument()
  })

  it('normalizes collapsed whitespace in the name before submitting', async () => {
    api.post.mockResolvedValue({ data: { digital_id: 'STS-TEST', trip_end: '2026-12-01T00:00:00' } })
    renderPage()
    fireEvent.change(screen.getByPlaceholderText('Enter Full Name'), { target: { value: '  Rahul   Sharma  ' } })
    fireEvent.change(screen.getByLabelText(/Select Verification Method/i), { target: { value: 'aadhaar' } })
    fireEvent.click(screen.getByText('Next'))

    fireEvent.change(screen.getByLabelText(/Aadhaar Number/i), { target: { value: '123456789012' } })
    fireEvent.change(screen.getByLabelText(/Phone/i), { target: { value: '9876543210' } })
    fireEvent.click(screen.getByText('Next'))  // -> Photo

    await capturePhotoAndAdvance()  // -> Trip
    fireEvent.change(screen.getByLabelText(/Trip Start/i), { target: { value: '2026-11-01T09:00' } })
    fireEvent.change(screen.getByLabelText(/Trip End/i), { target: { value: '2026-11-10T09:00' } })
    fireEvent.click(screen.getByText('Next'))  // -> Emergency
    fireEvent.click(screen.getByText('Next'))  // -> Account
    fireEvent.click(screen.getByText(/Get Your Unique Blockchain ID/))

    const [, payload] = api.post.mock.calls[0]
    expect(payload.full_name).toBe('Rahul Sharma')
    expect(payload.document_number).toBe('123456789012')
  })
})

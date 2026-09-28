import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import TouristApp from './TouristApp.jsx'
import { ThemeProvider } from '../../theme.jsx'

const renderApp = () => render(<ThemeProvider><TouristApp /></ThemeProvider>)

vi.mock('../../auth.jsx', () => ({
  useAuth: () => ({ user: { tourist_id: 1, role: 'tourist', full_name: 'Aarav' }, logout: vi.fn() }),
}))

const mockData = {
  ready: true,
  online: true,
  me: { id: 1, digital_id: 'STS-001', full_name: 'Aarav' },
  toast: null,
  sendSOS: vi.fn(),
  posRef: { current: [26.14, 91.73] },
  emergencyMessage: '', setEmergencyMessage: vi.fn(),
  sosSent: null, sosQueued: false, pendingCount: 0,
}

vi.mock('./useTouristData.js', () => ({ default: () => mockData }))
vi.mock('./tabs/HomeTab.jsx', () => ({ default: () => <div data-testid="tab-home">home tab</div> }))
vi.mock('./tabs/PlanTab.jsx', () => ({ default: () => <div data-testid="tab-plan">plan tab</div> }))
vi.mock('./tabs/HelpTab.jsx', () => ({ default: () => <div data-testid="tab-help">help tab</div> }))
vi.mock('./tabs/MeTab.jsx', () => ({ default: () => <div data-testid="tab-me">me tab</div> }))
vi.mock('../../components/DuressLock.jsx', () => ({ DuressLockButton: () => <div /> }))

describe('TouristApp', () => {
  beforeEach(() => {
    mockData.sendSOS.mockClear()
    mockData.ready = true
  })

  it('shows a loading state until useTouristData is ready', () => {
    mockData.ready = false
    const { getByText } = renderApp()
    expect(getByText(/loading/i)).toBeInTheDocument()
    mockData.ready = true
  })

  it('defaults to the Home tab', () => {
    const { getByTestId, queryByTestId } = renderApp()
    expect(getByTestId('tab-home')).toBeInTheDocument()
    expect(queryByTestId('tab-plan')).not.toBeInTheDocument()
  })

  it('switches tabs via the tab bar', () => {
    const { getByText, getByTestId, queryByTestId } = renderApp()
    fireEvent.click(getByText('Help'))
    expect(getByTestId('tab-help')).toBeInTheDocument()
    expect(queryByTestId('tab-home')).not.toBeInTheDocument()
  })

  it('renders exactly one SOS button that calls sendSOS', () => {
    renderApp()
    const sosButtons = document.querySelectorAll('button')
    const sos = [...sosButtons].find((b) => b.textContent.includes('SOS'))
    fireEvent.click(sos)
    expect(mockData.sendSOS).toHaveBeenCalled()
  })

  it('opens the report sheet without triggering an SOS', () => {
    const { getByText, getByRole } = renderApp()
    fireEvent.click(getByText(/Add details before sending/))
    expect(getByRole('dialog')).toBeInTheDocument()
    expect(mockData.sendSOS).not.toHaveBeenCalled()
  })
})

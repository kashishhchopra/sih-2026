import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ThemeProvider, useTheme } from './theme.jsx'

function Probe() {
  const { theme, toggle } = useTheme()
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <button onClick={toggle}>toggle</button>
    </div>
  )
}

const renderProbe = () => render(<ThemeProvider><Probe /></ThemeProvider>)

beforeEach(() => {
  localStorage.clear()
  document.documentElement.classList.remove('dark')
})

describe('ThemeProvider', () => {
  it('defaults to light when nothing is stored and the system has no preference', () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: false })
    renderProbe()
    expect(screen.getByTestId('theme')).toHaveTextContent('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    vi.restoreAllMocks()
  })

  it('respects a system dark-mode preference when nothing is stored', () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: true })
    renderProbe()
    expect(screen.getByTestId('theme')).toHaveTextContent('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    vi.restoreAllMocks()
  })

  it('a stored preference overrides the system preference', () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: true }) // system says dark
    localStorage.setItem('stsTheme', 'light')
    renderProbe()
    expect(screen.getByTestId('theme')).toHaveTextContent('light')
    vi.restoreAllMocks()
  })

  it('toggle flips the theme and updates the <html> class', () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: false })
    renderProbe()
    fireEvent.click(screen.getByText('toggle'))
    expect(screen.getByTestId('theme')).toHaveTextContent('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)

    fireEvent.click(screen.getByText('toggle'))
    expect(screen.getByTestId('theme')).toHaveTextContent('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    vi.restoreAllMocks()
  })

  it('persists the choice to localStorage', () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: false })
    renderProbe()
    fireEvent.click(screen.getByText('toggle'))
    expect(localStorage.getItem('stsTheme')).toBe('dark')
    vi.restoreAllMocks()
  })
})

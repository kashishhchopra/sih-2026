import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import RiskForecastStrip from './RiskForecastStrip'

const forecast = [
  { minutes: 15, score: 82, band: 'safe', zone: 'open area' },
  { minutes: 30, score: 55, band: 'moderate', zone: 'open area' },
  { minutes: 60, score: 18, band: 'danger', zone: 'Old Market High-Risk Zone' },
]

describe('RiskForecastStrip', () => {
  it('renders nothing with an empty forecast', () => {
    const { container } = render(<RiskForecastStrip forecast={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders one tile per horizon with rounded score and band label', () => {
    render(<RiskForecastStrip forecast={forecast} />)
    expect(screen.getByText('+15 min')).toBeInTheDocument()
    expect(screen.getByText('+30 min')).toBeInTheDocument()
    expect(screen.getByText('+60 min')).toBeInTheDocument()
    expect(screen.getByText('82')).toBeInTheDocument()
    expect(screen.getByText('Danger')).toBeInTheDocument()
    expect(screen.getByText('Old Market High-Risk Zone')).toBeInTheDocument()
  })
})

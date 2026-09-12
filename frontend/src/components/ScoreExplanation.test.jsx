import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ScoreExplanation from './ScoreExplanation'

const explanation = {
  base_value: 50.06,
  contributions: {
    zone_risk: 9.82,
    hour: 1.77,
    anomaly_score: -10.33,
    crime_index: -8.67,
    weather_risk: 2.0,
  },
}

describe('ScoreExplanation', () => {
  it('renders nothing when there is no explanation', () => {
    const { container } = render(<ScoreExplanation explanation={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('is collapsed by default behind a summary', () => {
    render(<ScoreExplanation explanation={explanation} />)
    expect(screen.getByText('Why this score?')).toBeInTheDocument()
    expect(screen.queryByText(/Zone risk level/)).not.toBeVisible()
  })

  it('reveals the per-feature breakdown when opened', () => {
    render(<ScoreExplanation explanation={explanation} />)
    fireEvent.click(screen.getByText('Why this score?'))
    expect(screen.getByText('Zone risk level')).toBeVisible()
    expect(screen.getByText('+9.82')).toBeInTheDocument()
    expect(screen.getByText('-10.33')).toBeInTheDocument()
  })

  it('sorts features by the magnitude of their contribution', () => {
    render(<ScoreExplanation explanation={explanation} />)
    const labels = screen.getAllByText(/risk level|Time of day|anomaly|crime index|Weather/i)
      .map((el) => el.textContent)
    // Largest absolute contribution (anomaly_score, -10.33) leads.
    expect(labels[0]).toBe('Movement anomaly')
  })

  it('falls back to the raw key for an unrecognised feature name', () => {
    render(<ScoreExplanation explanation={{ base_value: 50, contributions: { mystery_feature: 3 } }} />)
    expect(screen.getByText('mystery_feature')).toBeInTheDocument()
  })
})

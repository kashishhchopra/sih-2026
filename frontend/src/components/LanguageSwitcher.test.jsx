import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'
import i18n, { SUPPORTED_LANGUAGES } from '../i18n'
import LanguageSwitcher from './LanguageSwitcher.jsx'

function renderSwitcher() {
  return render(
    <I18nextProvider i18n={i18n}>
      <LanguageSwitcher />
    </I18nextProvider>,
  )
}

describe('LanguageSwitcher', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('lists every supported language as an option', () => {
    renderSwitcher()
    const options = screen.getAllByRole('option')
    expect(options).toHaveLength(SUPPORTED_LANGUAGES.length)
  })

  it('reflects the active language', () => {
    renderSwitcher()
    expect(screen.getByRole('combobox').value).toBe('en')
  })

  it('changing the selection switches the active i18n language', async () => {
    renderSwitcher()
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'hi' } })
    expect(i18n.language).toBe('hi')
  })

  it('persists the choice to localStorage so it survives a reload', async () => {
    renderSwitcher()
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'ta' } })
    expect(localStorage.getItem('stsLang')).toBe('ta')
  })
})

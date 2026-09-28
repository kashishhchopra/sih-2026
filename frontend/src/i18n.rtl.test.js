import { describe, it, expect } from 'vitest'
import { RTL_LANGUAGES, SUPPORTED_LANGUAGES } from './i18n.js'

describe('RTL_LANGUAGES', () => {
  it('is a subset of SUPPORTED_LANGUAGES', () => {
    const codes = new Set(SUPPORTED_LANGUAGES.map((l) => l.code))
    for (const rtl of RTL_LANGUAGES) {
      expect(codes.has(rtl)).toBe(true)
    }
  })

  it('includes Arabic', () => {
    expect(RTL_LANGUAGES).toContain('ar')
  })

  it('does not mark any Indian or other LTR language as RTL', () => {
    const ltrCodes = SUPPORTED_LANGUAGES.map((l) => l.code).filter((c) => c !== 'ar')
    for (const code of ltrCodes) {
      expect(RTL_LANGUAGES).not.toContain(code)
    }
  })
})

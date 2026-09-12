import { describe, it, expect } from 'vitest'
import en from './locales/en.json'

// Every locale must define exactly the same key paths as the English source.
// A missing key doesn't error at runtime -- i18next just falls back silently
// to English (or the raw key), so the gap would only surface as a user in
// that language quietly seeing the wrong copy. This test catches it at build
// time instead.
//
// Locales are discovered via import.meta.glob rather than a hardcoded map --
// a locale file dropped into src/locales/ without being added to a list here
// used to be silently exempt from this whole check.
function keyPaths(obj, prefix = '') {
  return Object.entries(obj).flatMap(([k, v]) => {
    const path = prefix ? `${prefix}.${k}` : k
    return typeof v === 'object' && v !== null ? keyPaths(v, path) : [path]
  })
}

const localeModules = import.meta.glob('./locales/*.json', { eager: true })
const LOCALES = Object.fromEntries(
  Object.entries(localeModules)
    .map(([path, mod]) => [path.match(/\.\/locales\/(.+)\.json$/)[1], mod.default])
    .filter(([code]) => code !== 'en')
)

const englishKeys = new Set(keyPaths(en))

describe('locale key parity', () => {
  it('the English source has the expected key count (sanity check)', () => {
    expect(englishKeys.size).toBeGreaterThan(20)
  })

  it('discovered more than just the original 10 Indian-language locales', () => {
    // Regression guard for the glob-discovery switch itself: if it silently
    // found zero files, every test below would vacuously pass.
    expect(Object.keys(LOCALES).length).toBeGreaterThanOrEqual(20)
  })

  it.each(Object.entries(LOCALES))('%s defines exactly the English key set', (_code, locale) => {
    const keys = new Set(keyPaths(locale))
    const missing = [...englishKeys].filter((k) => !keys.has(k))
    const extra = [...keys].filter((k) => !englishKeys.has(k))
    expect({ missing, extra }).toEqual({ missing: [], extra: [] })
  })

  it.each(Object.entries(LOCALES))('%s has no empty translation values', (_code, locale) => {
    const empty = keyPaths(locale).filter((path) => {
      const value = path.split('.').reduce((o, k) => o?.[k], locale)
      return typeof value !== 'string' || value.trim() === ''
    })
    expect(empty).toEqual([])
  })

  it.each(Object.entries(LOCALES))('%s preserves every {{placeholder}} the English string uses', (_code, locale) => {
    const placeholderRe = /\{\{(\w+)\}\}/g
    const mismatches = []
    for (const path of englishKeys) {
      const enValue = path.split('.').reduce((o, k) => o?.[k], en)
      const locValue = path.split('.').reduce((o, k) => o?.[k], locale)
      if (typeof enValue !== 'string' || typeof locValue !== 'string') continue
      const enPlaceholders = [...enValue.matchAll(placeholderRe)].map((m) => m[1]).sort()
      const locPlaceholders = [...locValue.matchAll(placeholderRe)].map((m) => m[1]).sort()
      if (JSON.stringify(enPlaceholders) !== JSON.stringify(locPlaceholders)) {
        mismatches.push({ path, enPlaceholders, locPlaceholders })
      }
    }
    expect(mismatches).toEqual([])
  })

  it.each(Object.entries(LOCALES))('%s never puts a raw emergency number in translated text', (_code, locale) => {
    // Emergency numbers (112/100/1363/etc) must always render from
    // card.emergency_numbers (server data), never from a locale string --
    // a bad translation could otherwise ship a wrong number for something
    // this safety-critical. This is a coarse heuristic (3+ consecutive
    // digits), not a formal proof, but catches the failure mode that matters.
    const suspicious = keyPaths(locale).filter((path) => {
      const value = path.split('.').reduce((o, k) => o?.[k], locale)
      return typeof value === 'string' && /\d{3,}/.test(value.replace(/\{\{\w+\}\}/g, ''))
    })
    expect(suspicious).toEqual([])
  })
})

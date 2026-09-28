import { describe, it, expect } from 'vitest'
import { detectIntent, INTENTS } from './voiceIntent'

describe('detectIntent', () => {
  it('returns null for empty/unmatched text', () => {
    expect(detectIntent('')).toBeNull()
    expect(detectIntent('   ')).toBeNull()
    expect(detectIntent('please book me a hot air balloon ride')).toBeNull()
  })

  it.each([
    'log in', 'sign in', 'I want to log in', 'sign me in', 'take me to login',
    'continue as a tourist',
  ])('recognizes "%s" as LOGIN', (phrase) => {
    expect(detectIntent(phrase)).toBe(INTENTS.LOGIN)
  })

  it.each([
    'register', 'sign up', 'create an account', 'I am new', "I'm new", 'new tourist',
  ])('recognizes "%s" as REGISTER', (phrase) => {
    expect(detectIntent(phrase)).toBe(INTENTS.REGISTER)
  })

  it.each([
    'I forgot my password', 'forgot password', 'reset my password',
    "I can't remember my password",
  ])('recognizes "%s" as FORGOT_PASSWORD', (phrase) => {
    expect(detectIntent(phrase)).toBe(INTENTS.FORGOT_PASSWORD)
  })

  it.each([
    'send an sos', 'this is an emergency', 'I need emergency assistance',
    'emergency', 'help me now',
  ])('recognizes "%s" as SEND_SOS', (phrase) => {
    expect(detectIntent(phrase)).toBe(INTENTS.SEND_SOS)
  })

  it.each([
    'how does this app work', "what's musafir", 'help me', 'what can you do',
  ])('recognizes "%s" as HELP_GENERAL', (phrase) => {
    expect(detectIntent(phrase)).toBe(INTENTS.HELP_GENERAL)
  })

  it.each([
    'show my tourist id', 'open my digital id', 'my tourist id',
  ])('recognizes "%s" as SHOW_TOURIST_ID', (phrase) => {
    expect(detectIntent(phrase)).toBe(INTENTS.SHOW_TOURIST_ID)
  })

  it.each([
    'open my itinerary', 'my trip plan', 'show my itinerary',
  ])('recognizes "%s" as SHOW_ITINERARY', (phrase) => {
    expect(detectIntent(phrase)).toBe(INTENTS.SHOW_ITINERARY)
  })

  it.each(['go home', 'take me home', 'home screen'])('recognizes "%s" as GO_HOME', (phrase) => {
    expect(detectIntent(phrase)).toBe(INTENTS.GO_HOME)
  })

  it.each(['next', 'next step', 'continue', 'proceed'])('recognizes "%s" as NEXT_STEP', (phrase) => {
    expect(detectIntent(phrase)).toBe(INTENTS.NEXT_STEP)
  })

  it('is case-insensitive', () => {
    expect(detectIntent('LOG IN')).toBe(INTENTS.LOGIN)
    expect(detectIntent('ReGiStEr')).toBe(INTENTS.REGISTER)
  })

  it('falls back to English patterns for an unlisted language code', () => {
    expect(detectIntent('log in', 'xx')).toBe(INTENTS.LOGIN)
  })
})

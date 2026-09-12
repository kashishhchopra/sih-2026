// Real intent detection for voice commands, shared by the pre-login voice
// assistant (Login/Register) and the in-app voice action router
// (useVoiceAssistant's optional onAction hook). Each intent is a *set* of
// phrasings -- "sign me in", "I want to log in" and "take me to login" all
// resolve to the same LOGIN intent -- never a single hardcoded string
// match, so the assistant isn't limited to one exact sentence per action.
//
// This is intentionally the same shape as the backend's own intent router
// (services/copilot.py): try each pattern group in order, return the first
// match. Everything an intent here maps to is a REAL action the caller
// performs (navigate, submit a real form, call a real API) -- this module
// only classifies text, it never fabricates a result.
//
// Patterns are English-first today (this app's spoken-language coverage is
// broadest for en-IN); the seam to extend per-language is `PATTERNS_BY_LANG`
// below -- add a language code with its own pattern groups and callers keep
// working unchanged, falling back to English patterns for anything unlisted.

const EN_PATTERNS = {
  // ---- pre-login intents ----
  LOGIN: [
    // "log in" / "sign in" / "sign me in" / "log me in" -- the optional
    // filler word is what makes "sign me in" resolve here rather than
    // dead-ending, per the natural phrasings this has to accept.
    /\b(log|sign)\s*(me\s+)?(in|on)\b/i,
    /\bi want to log ?in\b/i,
    /\bcontinue as (a )?tourist\b/i,
    /\btake me to (the )?login\b/i,
    /\blogin\b/i,
  ],
  REGISTER: [
    /\bregister\b/i,
    /\bsign\s*up\b/i,
    /\bcreate (an? )?account\b/i,
    /\bnew (tourist|user)\b/i,
    /\bi('m| am) new\b/i,
  ],
  FORGOT_PASSWORD: [
    /\bforgot\b.*\bpassword\b/i,
    /\breset\b.*\bpassword\b/i,
    /\bi (can'?t|cannot) (remember|recall) my password\b/i,
  ],
  // Checked before HELP_GENERAL/PATTERN below: "help me NOW" and other
  // emergency phrasings must never be swallowed by HELP_GENERAL's broader
  // "help me" pattern -- safety-critical intents win overlapping matches,
  // same rule the backend's own intent router documents for itself.
  SEND_SOS: [
    /\bsend (an? )?sos\b/i,
    /\bi need emergency assistance\b/i,
    /\bthis is an emergency\b/i,
    /\bemergency\s*!?$/i,
    /\bhelp me now\b/i,
  ],
  HELP_GENERAL: [
    /\bhow does this (app |thing )?work\b/i,
    /\b(what is|what's|what does) (this|musafir)\b/i,
    /\bi need help\b/i,
    /\bhelp me\b/i,
    /\bwhat can you do\b/i,
  ],

  // ---- in-app navigation / action intents ----
  SHOW_TOURIST_ID: [
    /\b(show|open|see) my (tourist|digital)?\s*id\b/i,
    /\bmy tourist id\b/i,
    /\bdigital id\b/i,
  ],
  SHOW_ITINERARY: [
    /\b(open|show) my itinerary\b/i,
    /\bmy trip plan\b/i,
    /\btrip plan\b/i,
    /\bmy plan\b/i,
  ],
  GO_BACK: [/\bgo back\b/i, /\bback\b/i],
  GO_HOME: [/\bgo home\b/i, /\btake me home\b/i, /\bhome (tab|screen|page)\b/i],

  // ---- register-page step navigation (voice-guided wizard) ----
  NEXT_STEP: [/\bnext( step)?\b/i, /\bcontinue\b/i, /\bproceed\b/i],
  PREVIOUS_STEP: [/\b(previous|go back)( step)?\b/i],
  READ_STEP: [/\bread (this|the) step\b/i, /\bwhat step\b/i, /\bwhere am i\b/i, /\bwhat'?s next\b/i],
}

const PATTERNS_BY_LANG = { en: EN_PATTERNS }

/** Classify `text` into one of the intents above, or null if nothing
 * matches (callers should then fall through to their own open-ended
 * handling -- a Q&A endpoint, an LLM, or "I didn't understand"). */
export function detectIntent(text, lang = 'en') {
  const heard = (text || '').trim()
  if (!heard) return null
  const patterns = PATTERNS_BY_LANG[lang] || EN_PATTERNS
  for (const [intent, regexes] of Object.entries(patterns)) {
    if (regexes.some((re) => re.test(heard))) {
      return intent
    }
  }
  return null
}

export const INTENTS = Object.freeze({
  LOGIN: 'LOGIN',
  REGISTER: 'REGISTER',
  FORGOT_PASSWORD: 'FORGOT_PASSWORD',
  HELP_GENERAL: 'HELP_GENERAL',
  SHOW_TOURIST_ID: 'SHOW_TOURIST_ID',
  SHOW_ITINERARY: 'SHOW_ITINERARY',
  SEND_SOS: 'SEND_SOS',
  GO_BACK: 'GO_BACK',
  GO_HOME: 'GO_HOME',
  NEXT_STEP: 'NEXT_STEP',
  PREVIOUS_STEP: 'PREVIOUS_STEP',
  READ_STEP: 'READ_STEP',
})

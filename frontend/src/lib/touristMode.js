import { useCallback, useState } from 'react'

// "Tourist Mode": the app already cascades the tourist's own chosen UI
// language everywhere via i18next (see i18n.js) -- explore, navigation,
// monument info, voice assistant and emergency instructions all follow it
// automatically since every component reads the same i18next instance.
// What that alone doesn't cover is a SEPARATE, persisted "language to
// speak to the local person in front of me" choice (e.g. a French tourist
// in India: UI in French, but talking to a local defaults to Hindi) -- that
// is what this module adds, shared by every translator component instead
// of each one defaulting/resetting independently.
const KEY = 'stsLocalsLanguage'
const DEFAULT_LOCALS_LANGUAGE = 'hi'

export function getLocalsLanguage() {
  try {
    return localStorage.getItem(KEY) || DEFAULT_LOCALS_LANGUAGE
  } catch {
    return DEFAULT_LOCALS_LANGUAGE
  }
}

export function setLocalsLanguage(lang) {
  try {
    localStorage.setItem(KEY, lang)
  } catch {
    // localStorage unavailable (private mode, storage full) -- the choice
    // just won't persist across reloads, which is a fine degradation.
  }
}

export function useLocalsLanguage() {
  const [lang, setLang] = useState(getLocalsLanguage)
  const update = useCallback((next) => {
    setLocalsLanguage(next)
    setLang(next)
  }, [])
  return [lang, update]
}

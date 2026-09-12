import api from '../api'

// Thin wrapper over /translate/* (see backend/app/api/translate.py +
// services/translation.py). Every text-translation response may carry
// `demo: true` when no live translation API key is configured -- callers
// must surface that, never hide it.
export function listLanguages() {
  return api.get('/translate/languages').then((r) => r.data)
}

export function listPhraseIds() {
  return api.get('/translate/phrases').then((r) => r.data)
}

export function translatePhrase(phraseId, targetLang) {
  return api.post('/translate/phrase', { phrase_id: phraseId, target_lang: targetLang }).then((r) => r.data)
}

export function translateText(text, targetLang, sourceLang) {
  return api.post('/translate/text', {
    text, target_lang: targetLang, ...(sourceLang ? { source_lang: sourceLang } : {}),
  }).then((r) => r.data)
}

// ---- Multilingual Guide: everyday phrasebook, grouped by category ----

export function listGuideCategories() {
  return api.get('/translate/guide/categories').then((r) => r.data)
}

export function listGuidePhraseIds(category) {
  return api.get(`/translate/guide/${category}`).then((r) => r.data)
}

export function translateGuidePhrase(category, phraseId, targetLang) {
  return api
    .post('/translate/guide/phrase', { category, phrase_id: phraseId, target_lang: targetLang })
    .then((r) => r.data)
}

import api from '../api'

// Cultural Etiquette Guide: see backend/app/api/etiquette.py + services/etiquette.py.
export function listEtiquetteTopics() {
  return api.get('/etiquette/topics').then((r) => r.data)
}

export function getEtiquetteTopic(topic, lang) {
  return api.get(`/etiquette/${topic}`, { params: { lang } }).then((r) => r.data)
}

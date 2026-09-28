import api from '../api'

// Thin wrapper over POST /tourists/verify-liveness (see
// backend/app/services/liveness.py). Public, unauthenticated -- there is no
// tourist account yet at this point in registration, same as POST
// /tourists itself.
export function verifyLiveness({ sessionId, photo, steps, livenessScore }) {
  return api.post('/tourists/verify-liveness', {
    session_id: sessionId, photo, steps, liveness_score: livenessScore,
  }).then((r) => r.data)
}

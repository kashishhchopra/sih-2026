import api from '../api'

// Thin wrapper over /permits/* (see backend/app/api/permits.py). Two-step by
// design: start (draft) -> edit -> confirm. Confirming never submits
// anything to a government system -- it returns the real official portal
// URL for the tourist to finish the actual application on themselves.
export function listPermitTypes() {
  return api.get('/permits/types').then((r) => r.data)
}

export function listPermits(touristId) {
  return api.get(`/tourists/${touristId}/permits`).then((r) => r.data)
}

export function startPermitApplication(touristId, permitType, zoneId, destinationName) {
  return api
    .post(`/tourists/${touristId}/permits`, {
      permit_type: permitType, zone_id: zoneId ?? null, destination_name: destinationName || '',
    })
    .then((r) => r.data)
}

export function updatePermitForm(touristId, permitId, form) {
  return api.patch(`/tourists/${touristId}/permits/${permitId}`, { form }).then((r) => r.data)
}

export function confirmPermit(touristId, permitId) {
  return api.post(`/tourists/${touristId}/permits/${permitId}/confirm`).then((r) => r.data)
}

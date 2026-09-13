import api from '../api'

// Currency conversion: see backend/app/api/currency.py + services/currency.py.
export function listCurrencies() {
  return api.get('/currency/list').then((r) => r.data)
}

export function convertFromInr(amount, to) {
  return api.get('/currency/convert', { params: { amount, to } }).then((r) => r.data)
}

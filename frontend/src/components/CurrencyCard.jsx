import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card } from './ui.jsx'
import { convertFromInr } from '../lib/currencyService.js'

const QUICK_CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'CNY', 'AUD', 'CAD', 'AED', 'SGD', 'RUB']

// Currency & Price Explanation: convert an INR amount (e.g. a menu price or
// a quoted fare) into the tourist's home currency using real, live
// exchange rates -- see backend/app/services/currency.py. Never a
// hardcoded/stale rate: `demo: true` means the live rate genuinely
// couldn't be fetched right now, shown honestly rather than guessed.
export default function CurrencyCard() {
  const { t } = useTranslation()
  const [amount, setAmount] = useState('')
  const [currency, setCurrency] = useState('USD')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const convert = () => {
    const value = parseFloat(amount)
    if (!value || value <= 0) return
    setError('')
    setLoading(true)
    convertFromInr(value, currency)
      .then(setResult)
      .catch(() => setError(t('currency.failed')))
      .finally(() => setLoading(false))
  }

  return (
    <Card title={t('currency.card_title')} icon="💱" iconColor="bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-300">
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">{t('currency.intro')}</p>
      {error && <div className="text-sm text-red-600 dark:text-red-400 mb-2">{error}</div>}

      <div className="flex gap-2 mb-2">
        <input value={amount} onChange={(e) => setAmount(e.target.value)} type="number" min="0" inputMode="decimal"
          placeholder={t('currency.amount_placeholder')}
          className="flex-1 text-sm border border-slate-200 dark:border-slate-600 dark:bg-slate-700 rounded-lg px-2 py-1.5" />
        <select value={currency} onChange={(e) => setCurrency(e.target.value)}
          className="text-sm border border-slate-200 dark:border-slate-600 dark:bg-slate-700 rounded-lg px-2 py-1.5">
          {QUICK_CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <button onClick={convert} disabled={loading}
        className="w-full text-sm font-semibold bg-emerald-600 hover:bg-emerald-700 text-white py-2 rounded-lg disabled:opacity-60">
        {loading ? t('currency.converting') : t('currency.convert_button')}
      </button>

      {result && (
        <div className="mt-3 bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 text-sm">
          {result.demo ? (
            <div className="text-orange-600 dark:text-orange-400">{result.note}</div>
          ) : (
            <>
              <div className="font-semibold text-slate-800 dark:text-slate-100">
                ₹{result.amount_inr} ≈ {result.converted} {result.currency}
              </div>
              <div className="text-xs text-slate-400 mt-1">{t('currency.rate_note', { rate: result.rate })}</div>
            </>
          )}
        </div>
      )}
    </Card>
  )
}

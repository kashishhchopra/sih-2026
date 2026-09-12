import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import api from '../api'
import { Card } from './ui.jsx'

const STATUS_CLS = {
  planned: 'bg-slate-100 text-slate-700',
  checked_in: 'bg-green-100 text-green-700',
  missed: 'bg-orange-100 text-orange-700',
  escalated: 'bg-red-100 text-red-700',
}

// Tourist Check-in / Check-out: register an expected destination + return
// time. A miss becomes a soft distress signal on its own -- see
// services/checkin.py:tick_checkins().
export default function CheckInCard({ touristId }) {
  const { t } = useTranslation()
  const [checkins, setCheckins] = useState([])
  const [destination, setDestination] = useState('')
  const [returnAt, setReturnAt] = useState('')
  const [creating, setCreating] = useState(false)

  const load = () => api.get(`/tourists/${touristId}/checkins`).then((r) => setCheckins(r.data))
  useEffect(() => {
    load()
    const iv = setInterval(load, 30000)
    return () => clearInterval(iv)
  }, [touristId])

  const create = async (e) => {
    e.preventDefault()
    if (!destination.trim() || !returnAt) return
    setCreating(true)
    try {
      await api.post(`/tourists/${touristId}/checkins`, {
        destination_name: destination,
        expected_return_at: new Date(returnAt).toISOString(),
      })
      setDestination('')
      setReturnAt('')
      load()
    } finally {
      setCreating(false)
    }
  }

  const checkIn = async (id) => {
    await api.post(`/tourists/${touristId}/checkins/${id}/checkin`)
    load()
  }

  const open = checkins.filter((c) => c.status !== 'checked_in')

  return (
    <Card title={t('checkin.card_title')}>
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">
        {t('checkin.intro')}
      </p>

      <form onSubmit={create} className="flex flex-col gap-2 mb-3">
        <input value={destination} onChange={(e) => setDestination(e.target.value)}
          placeholder={t('checkin.destination_placeholder')}
          className="border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 rounded-lg px-3 py-2 text-sm" />
        <input type="datetime-local" value={returnAt} onChange={(e) => setReturnAt(e.target.value)}
          className="border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 rounded-lg px-3 py-2 text-sm" />
        <button disabled={creating || !destination.trim() || !returnAt}
          className="bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white text-sm font-semibold py-2 rounded-lg">
          {creating ? t('checkin.saving') : t('checkin.plan_button')}
        </button>
      </form>

      <div className="space-y-2">
        {open.length === 0 && <div className="text-xs text-slate-400">{t('checkin.no_outings')}</div>}
        {open.map((c) => (
          <div key={c.id} className="border border-slate-100 dark:border-slate-700 rounded-lg p-2.5 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-medium">{c.destination_name}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${STATUS_CLS[c.status]}`}>
                {c.status.replace('_', ' ')}
              </span>
            </div>
            <div className="text-xs text-slate-400 mt-0.5">
              {t('checkin.expected_back', { when: new Date(c.expected_return_at).toLocaleString() })}
            </div>
            <button onClick={() => checkIn(c.id)}
              className="mt-2 w-full text-xs font-semibold bg-green-600 hover:bg-green-700 text-white py-1.5 rounded-lg">
              {t('checkin.im_back_safe')}
            </button>
          </div>
        ))}
      </div>
    </Card>
  )
}

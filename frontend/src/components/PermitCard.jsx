import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card } from './ui.jsx'
import {
  listPermitTypes, listPermits, startPermitApplication, updatePermitForm, confirmPermit,
} from '../lib/permitService.js'

const STATUS_CLS = {
  draft: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200',
  reviewed: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
}

// Permit & E-Pass Automation: pre-fills a permit application from the
// tourist's own profile + itinerary. This app has NO real government permit
// integration -- "Confirm" never submits anything anywhere. It only locks in
// what the tourist reviewed and hands them the real official portal to
// finish the actual application themselves. See backend/app/services/permit.py.
export default function PermitCard({ touristId }) {
  const { t } = useTranslation()
  const [types, setTypes] = useState([])
  const [permits, setPermits] = useState([])
  const [permitType, setPermitType] = useState('')
  const [destination, setDestination] = useState('')
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({})
  const [confirmingId, setConfirmingId] = useState(null)

  const load = () => {
    Promise.all([listPermitTypes(), listPermits(touristId)])
      .then(([t_, p]) => { setTypes(t_); setPermits(p); if (t_.length) setPermitType(t_[0].code) })
      .catch(() => setError(t('permits.failed')))
  }
  useEffect(load, [touristId]) // eslint-disable-line react-hooks/exhaustive-deps

  const start = async (e) => {
    e.preventDefault()
    if (!permitType) return
    setStarting(true)
    setError('')
    try {
      await startPermitApplication(touristId, permitType, null, destination)
      setDestination('')
      load()
    } catch {
      setError(t('permits.apply_failed'))
    } finally {
      setStarting(false)
    }
  }

  const openEdit = (p) => { setEditingId(p.id); setEditForm({ ...p.form }) }

  const saveEdit = async (permitId) => {
    try {
      await updatePermitForm(touristId, permitId, editForm)
      setEditingId(null)
      load()
    } catch {
      setError(t('permits.apply_failed'))
    }
  }

  const confirm = async (p) => {
    setConfirmingId(p.id)
    setError('')
    try {
      const updated = await confirmPermit(touristId, p.id)
      load()
      // Open the REAL official portal in a new tab -- this app never submits
      // the application itself.
      if (updated.portal?.portal_url) window.open(updated.portal.portal_url, '_blank', 'noopener')
    } catch {
      setError(t('permits.apply_failed'))
    } finally {
      setConfirmingId(null)
    }
  }

  return (
    <Card title={t('permits.card_title')} icon="📝" iconColor="bg-indigo-50 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-300">
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">{t('permits.intro')}</p>
      <p className="text-[11px] text-orange-600 dark:text-orange-400 mb-3">{t('permits.honesty_notice')}</p>
      {error && <div className="text-sm text-red-600 dark:text-red-400 mb-2">{error}</div>}

      <form onSubmit={start} className="flex flex-col gap-2 mb-3">
        <select value={permitType} onChange={(e) => setPermitType(e.target.value)}
          className="text-sm border border-slate-200 dark:border-slate-600 dark:bg-slate-700 rounded-lg px-2 py-1.5">
          {types.map((pt) => <option key={pt.code} value={pt.code}>{pt.name}</option>)}
        </select>
        {types.find((pt) => pt.code === permitType) && (
          <div className="text-[11px] text-slate-400">
            {types.find((pt) => pt.code === permitType).description}
          </div>
        )}
        <input value={destination} onChange={(e) => setDestination(e.target.value)}
          placeholder={t('permits.destination_placeholder')}
          className="text-sm border border-slate-200 dark:border-slate-600 dark:bg-slate-700 rounded-lg px-2 py-1.5" />
        <button disabled={starting || !permitType}
          className="text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white py-2 rounded-lg">
          {starting ? t('permits.applying') : t('permits.start_draft_button')}
        </button>
      </form>

      <div className="space-y-2">
        {permits.length === 0 && <div className="text-xs text-slate-400">{t('permits.none_yet')}</div>}
        {permits.map((p) => (
          <div key={p.id} className="border border-slate-100 dark:border-slate-700 rounded-lg p-2.5 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-medium">{p.form.permit_type?.replace(/_/g, ' ')}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${STATUS_CLS[p.status] || STATUS_CLS.draft}`}>
                {t(`permits.status_${p.status}`, p.status)}
              </span>
            </div>

            {editingId === p.id ? (
              <div className="mt-2 space-y-1.5">
                {Object.entries(editForm).map(([k, v]) => (
                  <div key={k} className="flex items-center gap-2">
                    <label className="text-[11px] text-slate-400 w-28 shrink-0">{k.replace(/_/g, ' ')}</label>
                    <input value={v ?? ''} onChange={(e) => setEditForm((f) => ({ ...f, [k]: e.target.value }))}
                      className="flex-1 text-xs border border-slate-200 dark:border-slate-600 dark:bg-slate-700 rounded px-1.5 py-1" />
                  </div>
                ))}
                <div className="flex gap-2 pt-1">
                  <button onClick={() => saveEdit(p.id)}
                    className="text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-1 rounded-lg">
                    {t('permits.save_review')}
                  </button>
                  <button onClick={() => setEditingId(null)}
                    className="text-xs font-medium text-slate-500 dark:text-slate-400 px-3 py-1">
                    {t('permits.cancel')}
                  </button>
                </div>
              </div>
            ) : (
              <div className="mt-2 text-xs text-slate-500 dark:text-slate-400 space-y-0.5">
                <div>{t('permits.destination_label')}: {p.form.destination}</div>
                <div>{t('permits.applicant_label')}: {p.form.applicant_name}</div>
              </div>
            )}

            {p.status === 'draft' && editingId !== p.id && (
              <div className="flex gap-2 mt-2">
                <button onClick={() => openEdit(p)}
                  className="text-xs font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 px-3 py-1.5 rounded-lg">
                  {t('permits.review_edit')}
                </button>
                <button onClick={() => confirm(p)} disabled={confirmingId === p.id}
                  className="text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white px-3 py-1.5 rounded-lg">
                  {confirmingId === p.id ? t('permits.confirming') : t('permits.confirm_open_portal')}
                </button>
              </div>
            )}

            {p.status === 'reviewed' && (
              <div className="mt-2 text-xs">
                <div className="text-slate-400">{t('permits.local_reference', { ref: p.reference_no })}</div>
                {p.portal?.portal_url && (
                  <a href={p.portal.portal_url} target="_blank" rel="noopener noreferrer"
                    className="text-indigo-600 dark:text-indigo-400 font-semibold underline">
                    {t('permits.open_portal_again', { name: p.portal.portal_name })}
                  </a>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  )
}

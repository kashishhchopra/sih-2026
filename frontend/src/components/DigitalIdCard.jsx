import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import api from '../api'

const STATUS_META = {
  active: { icon: '🟢', labelKey: 'digital_id.status_active', cls: 'text-green-600 dark:text-green-400' },
  expiring_soon: { icon: '🟡', labelKey: 'digital_id.status_expiring', cls: 'text-yellow-600 dark:text-yellow-400' },
  expired: { icon: '⚫', labelKey: 'digital_id.status_expired', cls: 'text-slate-500 dark:text-slate-400' },
  invalidated: { icon: '🔴', labelKey: 'digital_id.status_invalidated', cls: 'text-red-600 dark:text-red-400' },
}

// The Digital Tourist Safety ID card -- a government-credential-style card
// with photo + secure QR, not just a profile page. The QR encodes only an
// opaque token (never the tourist's actual information); a scanner only
// learns anything after the backend verifies that token and checks the
// scanner's own role -- see backend/services/tourist_id.py.
export default function DigitalIdCard({ touristId }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [card, setCard] = useState(null)
  const [loading, setLoading] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [confirmRegen, setConfirmRegen] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await api.get(`/tourists/${touristId}/digital-id`)
      setCard(data)
    } finally {
      setLoading(false)
    }
  }

  const toggle = () => {
    const next = !open
    setOpen(next)
    if (next && !card) load()
  }

  const regenerate = async () => {
    setRegenerating(true)
    try {
      const { data } = await api.post(`/tourists/${touristId}/digital-id/regenerate`)
      setCard(data)
      setConfirmRegen(false)
    } finally {
      setRegenerating(false)
    }
  }

  useEffect(() => { setCard(null) }, [touristId])

  const meta = card ? (STATUS_META[card.id_status] || STATUS_META.active) : null

  return (
    <div>
      <button onClick={toggle}
        className="w-full text-sm font-semibold text-sky-700 dark:text-sky-400 bg-sky-50 dark:bg-sky-900/30 rounded-xl py-2">
        {open ? t('digital_id.toggle_hide') : t('digital_id.toggle_show')}
      </button>

      {open && (
        <div className="mt-3">
          {loading && !card && <div className="text-sm text-slate-400 text-center py-4">{t('digital_id.loading')}</div>}
          {card && (
            <div className="rounded-[var(--theme-radius)] shadow-[var(--theme-shadow)] overflow-hidden bg-white dark:bg-slate-800">
              {/* Digital passport / travel-card banner -- the same brand
                  identity as the rest of the tourist app, styled to feel
                  like a real travel credential rather than a plain profile
                  card. */}
              <div className="bg-gradient-to-r from-sky-600 to-sky-500 px-4 py-3 flex items-center justify-between text-white">
                <div className="flex items-center gap-1.5 font-bold tracking-wide text-sm">
                  {t('digital_id.brand')}
                </div>
                <span className="text-emerald-300 text-lg leading-none">✓</span>
              </div>
              <div className="p-4">
              <div className="flex gap-4 items-start justify-center">
                {card.photo ? (
                  <img src={card.photo} alt={t('digital_id.photo_alt')}
                    className="w-24 h-24 rounded-xl object-cover border border-slate-200 dark:border-slate-600 shrink-0" />
                ) : (
                  <div className="w-24 h-24 rounded-xl bg-slate-100 dark:bg-slate-700 shrink-0 flex items-center justify-center text-3xl">🪪</div>
                )}
                {card.qr_png_base64 ? (
                  <img src={card.qr_png_base64} alt={t('digital_id.qr_alt')}
                    className="w-24 h-24 border border-slate-200 dark:border-slate-600 rounded-lg shrink-0 bg-white p-1" />
                ) : (
                  <div className="w-24 h-24 rounded-lg bg-slate-100 dark:bg-slate-700 shrink-0 flex items-center justify-center text-xs text-slate-400 text-center p-1">
                    {t('digital_id.qr_unavailable')}
                  </div>
                )}
              </div>

              <div className="text-center mt-3">
                <div className="font-bold text-lg text-slate-800 dark:text-slate-100">{card.full_name}</div>
                <div className="text-sm mt-1"><span className="text-slate-400">{t('digital_id.tourist_id_label')}</span> <span className="font-mono">{card.digital_id}</span></div>
                {card.hotel && <div className="text-sm"><span className="text-slate-400">{t('digital_id.hotel_label')}</span> {card.hotel}</div>}
                <div className="text-sm text-slate-400">
                  {new Date(card.trip_start).toLocaleDateString()} → {new Date(card.trip_end).toLocaleDateString()}
                </div>
                <div className={`text-sm font-bold mt-2 flex items-center justify-center gap-1.5 ${meta.cls}`}>
                  <span>{meta.icon}</span>{t(meta.labelKey)}
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-700 flex items-center justify-center gap-2">
                {!confirmRegen ? (
                  <button onClick={() => setConfirmRegen(true)}
                    className="text-xs bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 font-semibold px-3 py-1.5 rounded-lg">
                    {t('digital_id.regenerate_qr')}
                  </button>
                ) : (
                  <>
                    <span className="text-xs text-slate-500">{t('digital_id.regenerate_confirm')}</span>
                    <button onClick={regenerate} disabled={regenerating}
                      className="text-xs bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white font-semibold px-3 py-1.5 rounded-lg">
                      {regenerating ? t('digital_id.regenerating') : t('digital_id.confirm')}
                    </button>
                    <button onClick={() => setConfirmRegen(false)}
                      className="text-xs text-slate-500 hover:underline">{t('digital_id.cancel')}</button>
                  </>
                )}
              </div>
              <div className="mt-2 text-[11px] text-slate-400 text-center">
                {t('digital_id.qr_note')}
              </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

import { useEffect, useRef } from 'react'

// A single reusable bottom sheet -- backdrop + slide-up panel, closes on
// Escape or backdrop click, and moves focus into the panel while open so
// keyboard/screen-reader users don't get stranded on the page behind it.
export default function BottomSheet({ open, onClose, title, children }) {
  const panelRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') onClose?.() }
    document.addEventListener('keydown', onKey)
    panelRef.current?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[1200] flex items-end justify-center">
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
        aria-hidden="true"
        data-testid="sheet-backdrop"
      />
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="relative w-full max-w-md max-h-[85vh] overflow-y-auto bg-slate-100 dark:bg-slate-900 rounded-t-2xl shadow-2xl p-4 pb-8 outline-none"
      >
        <div className="flex items-center justify-between mb-3 sticky top-0 bg-slate-100 dark:bg-slate-900 pb-2">
          <h2 className="font-bold text-slate-900 dark:text-slate-100">{title}</h2>
          <button onClick={onClose} aria-label="Close"
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-xl leading-none px-2">
            ×
          </button>
        </div>
        <div className="space-y-4">{children}</div>
      </div>
    </div>
  )
}

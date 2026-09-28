import { useTranslation } from 'react-i18next'

// Popular Indian destinations, shown purely for inspiration -- a real
// travel-app touch on the home screen, matching the "travel app first,
// safety system second" direction. Deliberately NOT wired to any booking
// or "add to itinerary" action: this app has no real booking integration
// (see services/maps.py/transport's own "never fake availability" rule),
// so these are informational only, never a fabricated CTA.
const PLACES = [
  {
    name: 'Taj Mahal', place: 'Agra',
    photo: 'https://images.unsplash.com/photo-1524492412937-b28074a5d7da?w=400&q=60',
  },
  {
    name: 'Hawa Mahal', place: 'Jaipur',
    photo: 'https://images.unsplash.com/photo-1477587458883-47145ed94245?w=400&q=60',
  },
  {
    name: 'India Gate', place: 'Delhi',
    photo: 'https://images.unsplash.com/photo-1571401835393-8c5f35328320?w=400&q=60',
  },
  {
    name: 'Backwaters', place: 'Kerala',
    photo: 'https://images.unsplash.com/photo-1602216056096-3b40cc0c9944?w=400&q=60',
  },
]

export default function RecommendedPlaces() {
  const { t } = useTranslation()
  return (
    <div>
      <div className="text-sm font-bold text-slate-800 dark:text-slate-100 mb-2">{t('home_extra.popular_destinations')}</div>
      <div className="flex gap-3 overflow-x-auto pb-1 -mx-1 px-1">
        {PLACES.map((p) => (
          <div key={p.name}
            className="shrink-0 w-36 rounded-2xl overflow-hidden shadow-[var(--theme-shadow)] bg-white dark:bg-slate-800">
            <img src={p.photo} alt={`${p.name}, ${p.place}`} loading="lazy"
              className="w-full h-24 object-cover" />
            <div className="p-2">
              <div className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">{p.name}</div>
              <div className="text-[11px] text-slate-500 dark:text-slate-400">{p.place}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

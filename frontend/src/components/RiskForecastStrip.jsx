import { bandColor, bandLabel } from './ui.jsx'

// Three small chips showing the predicted safety score at +15/+30/+60 min,
// from GET /tourists/{id}/risk-forecast. `forecast` is
// [{minutes, score, band, zone}, ...].
export default function RiskForecastStrip({ forecast }) {
  if (!forecast || forecast.length === 0) return null

  return (
    <div className="grid grid-cols-3 gap-2">
      {forecast.map((f) => {
        const color = bandColor(f.score)
        return (
          <div key={f.minutes}
            className="bg-white dark:bg-slate-800 rounded-xl shadow-sm p-3 text-center border-t-2"
            style={{ borderTopColor: color }}>
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
              +{f.minutes} min
            </div>
            <div className="text-xl font-bold mt-1" style={{ color }}>{Math.round(f.score)}</div>
            <div className="text-xs font-medium mt-0.5" style={{ color }}>{bandLabel(f.score)}</div>
            <div className="text-[10px] text-slate-400 mt-1 truncate" title={f.zone}>{f.zone}</div>
          </div>
        )
      })}
    </div>
  )
}

// Small colourful banner shown at the top of Plan/Help/Me so each tab reads
// at a glance instead of opening straight into a stack of grey cards -- same
// "travel app first" visual language as HomeTab's hero, just themed per tab
// (indigo for planning, teal for safety/help, violet for profile) so the
// three tabs stay visually distinct from one another.
export default function TabHero({ icon, title, subtitle, gradient }) {
  return (
    <div className={`rounded-[var(--theme-radius)] p-4 text-white shadow-[var(--theme-shadow)] bg-gradient-to-br ${gradient}`}>
      <div className="flex items-center gap-3">
        <span className="w-11 h-11 rounded-2xl bg-white/20 flex items-center justify-center text-2xl shrink-0">
          {icon}
        </span>
        <div className="min-w-0">
          <div className="font-bold text-lg leading-tight">{title}</div>
          {subtitle && <div className="text-xs text-white/85 mt-0.5">{subtitle}</div>}
        </div>
      </div>
    </div>
  )
}

// Small shared helper for the Disaster & Weather Alert Feed UI (used by
// DisasterBanner and the Police Network Dashboard's disaster monitoring
// section). Mirrors the existing local copy in CctvNetworkPanel.jsx --
// duplicated rather than that file being changed to import a shared util,
// per this session's "don't touch pre-existing files, just add" rule.
export function relativeTime(iso) {
  if (!iso) return null
  const utc = /[Z+]|-\d{2}:\d{2}$/.test(iso) ? iso : `${iso}Z`
  const seconds = Math.max(0, Math.round((Date.now() - new Date(utc).getTime()) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`
  return `${Math.round(seconds / 86400)}d ago`
}

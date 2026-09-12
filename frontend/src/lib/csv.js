// Minimal CSV export -- no dependency, since the data here is always a flat
// array of plain objects (exactly what recharts already consumes for these
// charts, so the same `data` prop doubles as the export source).
function escapeCell(value) {
  const s = value == null ? '' : String(value)
  // Quote whenever the value contains a character that would otherwise
  // change how a spreadsheet parses the row.
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export function toCSV(rows) {
  if (!rows || rows.length === 0) return ''
  const columns = Object.keys(rows[0])
  const lines = [columns.join(',')]
  for (const row of rows) {
    lines.push(columns.map((c) => escapeCell(row[c])).join(','))
  }
  return lines.join('\r\n')
}

export function downloadCSV(filename, rows) {
  const csv = toCSV(rows)
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename.endsWith('.csv') ? filename : `${filename}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

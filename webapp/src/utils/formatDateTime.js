/**
 * ISO-8601 (например 2026-04-22T11:08:53Z) → читаемая дата/время для ru-RU в часовом поясе устройства.
 */
export function formatDateTimeRu(iso) {
  if (iso == null || iso === '') return '—'
  if (typeof iso !== 'string') return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(d)
}

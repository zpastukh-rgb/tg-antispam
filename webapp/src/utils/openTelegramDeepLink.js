/**
 * Надёжно открывает Telegram-ссылки/диплинки:
 * - https://t.me/...
 * - tg://...
 * - @username
 */
export function openTelegramDeepLink(url) {
  if (!url || typeof window === 'undefined') return false
  const raw = String(url || '').trim()
  if (!raw) return false
  const tg = window.Telegram?.WebApp

  let normalized = raw
  if (normalized.startsWith('@')) {
    normalized = `https://t.me/${encodeURIComponent(normalized.replace(/^@+/, ''))}`
  } else if (normalized.startsWith('tg://user?id=')) {
    normalized = `https://t.me/user?id=${encodeURIComponent(normalized.replace('tg://user?id=', ''))}`
  }

  try {
    if (normalized.startsWith('https://t.me/') && typeof tg?.openTelegramLink === 'function') {
      tg.openTelegramLink(normalized)
      return true
    }
  } catch {
    //
  }
  try {
    if (typeof tg?.openLink === 'function') {
      tg.openLink(normalized, { try_instant_view: false })
      return true
    }
  } catch {
    //
  }
  try {
    window.location.href = normalized
    return true
  } catch {
    //
  }
  try {
    window.open(normalized, '_blank', 'noopener,noreferrer')
    return true
  } catch {
    return false
  }
}

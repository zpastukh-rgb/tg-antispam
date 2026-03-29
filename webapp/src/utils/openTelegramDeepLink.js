/**
 * Deep link вида https://t.me/...?startgroup=... — внутри Mini App.
 * Telegram Mini Apps: openTelegramLink — основной способ; openLink — запасной.
 */
export function openTelegramDeepLink(url) {
  if (!url || typeof window === 'undefined') return false
  const tg = window.Telegram?.WebApp
  if (typeof tg?.openTelegramLink === 'function') {
    try {
      tg.openTelegramLink(url)
      return true
    } catch {
      //
    }
  }
  if (typeof tg?.openLink === 'function') {
    try {
      tg.openLink(url, { try_instant_view: false })
      return true
    } catch {
      //
    }
  }
  window.open(url, '_blank', 'noopener,noreferrer')
  return false
}

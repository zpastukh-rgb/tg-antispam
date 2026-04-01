/**
 * Открывает startgroup deep link внутри Telegram WebApp.
 * Внешний браузер НЕ используем, чтобы не ломать flow подключения.
 */
export function openTelegramDeepLink(url) {
  if (!url || typeof window === 'undefined') return false
  const tg = window.Telegram?.WebApp
  if (typeof tg?.openTelegramLink === 'function') {
    try {
      tg.openTelegramLink(url)
      return true
    } catch {
      return false
    }
  }
  return false
}

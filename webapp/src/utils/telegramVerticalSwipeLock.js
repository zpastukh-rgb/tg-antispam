/**
 * Telegram Mini App (Bot API ≥7.7): жест свайпа вниз сворачивает WebView.
 * Пока юзер ведёт указатель по горизонтальным каруселям — отключаем вертикальный свайп клиента,
 * затем включаем обратно, чтобы не блокировать навсегда.
 */
const activePointerIds = new Set()
let dashboardCarouselLock = false
let delayedEnableTimer = null

function tryDisableVerticalSwipes() {
  const tg = typeof window !== 'undefined' ? window.Telegram?.WebApp : null
  if (!tg || typeof tg.disableVerticalSwipes !== 'function') return
  try {
    tg.disableVerticalSwipes()
  } catch {
    //
  }
}

function tryEnableVerticalSwipes() {
  const tg = typeof window !== 'undefined' ? window.Telegram?.WebApp : null
  if (!tg || typeof tg.enableVerticalSwipes !== 'function') return
  try {
    tg.enableVerticalSwipes()
  } catch {
    //
  }
}

function canEnableVerticalSwipes() {
  return !dashboardCarouselLock && activePointerIds.size === 0
}

function scheduleEnableVerticalSwipes(delayMs = 0) {
  if (delayedEnableTimer) {
    clearTimeout(delayedEnableTimer)
    delayedEnableTimer = null
  }
  const ms = Math.max(0, Number(delayMs) || 0)
  if (!canEnableVerticalSwipes()) return
  if (ms <= 0) {
    tryEnableVerticalSwipes()
    return
  }
  delayedEnableTimer = setTimeout(() => {
    delayedEnableTimer = null
    if (canEnableVerticalSwipes()) tryEnableVerticalSwipes()
  }, ms)
}

/** Главная «Аккаунт»: держим disableVerticalSwipes, пока видна карусель статистика↔рассылки. */
export function setTelegramDashboardCarouselLock(locked) {
  dashboardCarouselLock = !!locked
  if (dashboardCarouselLock) {
    if (delayedEnableTimer) {
      clearTimeout(delayedEnableTimer)
      delayedEnableTimer = null
    }
    tryDisableVerticalSwipes()
    return
  }
  if (canEnableVerticalSwipes()) scheduleEnableVerticalSwipes(0)
}

/** Начало горизонтального свайпа (pointerdown после setPointerCapture). */
export function telegramVerticalSwipeGestureBegin(pointerId) {
  const id = Number(pointerId)
  if (!Number.isFinite(id)) return
  if (activePointerIds.has(id)) return
  const wasEmpty = activePointerIds.size === 0
  activePointerIds.add(id)
  if (wasEmpty) tryDisableVerticalSwipes()
}

/**
 * Конец жеста: pointerup / pointercancel / lostpointercapture.
 * @param {number} pointerId
 * @param {{ delayMs?: number }} [options] — задержка перед enableVerticalSwipes (плавный snap карусели).
 */
export function telegramVerticalSwipeGestureEnd(pointerId, options = {}) {
  const id = Number(pointerId)
  if (!Number.isFinite(id)) return
  if (!activePointerIds.delete(id)) return
  if (activePointerIds.size === 0) {
    scheduleEnableVerticalSwipes(Number(options.delayMs || 0))
  }
}

function clearSwipeLocks() {
  if (delayedEnableTimer) {
    clearTimeout(delayedEnableTimer)
    delayedEnableTimer = null
  }
  if (activePointerIds.size === 0) return
  activePointerIds.clear()
  if (canEnableVerticalSwipes()) tryEnableVerticalSwipes()
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') clearSwipeLocks()
  })
}

/** Если ушли с экрана в середине жеста — вернуть клиенту обычный свайп сворачивания. */
export function telegramVerticalSwipeGestureResetAll() {
  dashboardCarouselLock = false
  clearSwipeLocks()
  tryEnableVerticalSwipes()
}

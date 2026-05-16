/**
 * Telegram Mini App (Bot API ≥7.7): жест свайпа вниз сворачивает WebView.
 * Пока юзер ведёт указатель по горизонтальным каруселям — отключаем вертикальный свайп клиента,
 * затем включаем обратно, чтобы не блокировать навсегда.
 */
const activePointerIds = new Set()

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

/** Начало горизонтального свайпа (pointerdown после setPointerCapture). */
export function telegramVerticalSwipeGestureBegin(pointerId) {
  const id = Number(pointerId)
  if (!Number.isFinite(id)) return
  if (activePointerIds.has(id)) return
  const wasEmpty = activePointerIds.size === 0
  activePointerIds.add(id)
  if (wasEmpty) tryDisableVerticalSwipes()
}

/** Конец жеста: pointerup / pointercancel / lostpointercapture. */
export function telegramVerticalSwipeGestureEnd(pointerId) {
  const id = Number(pointerId)
  if (!Number.isFinite(id)) return
  if (!activePointerIds.delete(id)) return
  if (activePointerIds.size === 0) tryEnableVerticalSwipes()
}

function clearSwipeLocks() {
  if (activePointerIds.size === 0) return
  activePointerIds.clear()
  tryEnableVerticalSwipes()
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') clearSwipeLocks()
  })
}

/** Если ушли с экрана в середине жеста — вернуть клиенту обычный свайп сворачивания. */
export function telegramVerticalSwipeGestureResetAll() {
  clearSwipeLocks()
}

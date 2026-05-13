/**
 * Логи экранов «Защита» и «Подключённые чаты».
 *
 * Включение:
 * - `npm run dev` — логи включены
 * - прод: `VITE_GUARD_DEBUG=true` при сборке фронта
 * - или в консоли браузера (если доступен localStorage с origin мини-аппа):
 *   `localStorage.setItem('GUARD_DEBUG','1')` и перезагрузка страницы
 *
 * Терминал: при `npm run dev` или `vite preview` те же строки дублируются в процесс Vite
 * (POST /__guard_debug_log), чтобы смотреть живой лог, пока мини-апп открыт с dev-URL.
 */

function forwardToDevTerminal(kind, payload) {
  if (!import.meta.env.DEV) return
  try {
    fetch('/__guard_debug_log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind, ...payload }),
      keepalive: true,
    }).catch(() => {})
  } catch {
    //
  }
}

export function guardDebugEnabled() {
  if (import.meta.env.DEV) return true
  if (import.meta.env.VITE_GUARD_DEBUG === 'true') return true
  try {
    return typeof localStorage !== 'undefined' && localStorage.getItem('GUARD_DEBUG') === '1'
  } catch {
    return false
  }
}

/** @param {string} scope @param {string} msg @param {unknown} [extra] */
export function guardLog(scope, msg, extra) {
  if (!guardDebugEnabled()) return
  if (extra !== undefined) console.log(`[Guard:${scope}]`, msg, extra)
  else console.log(`[Guard:${scope}]`, msg)
  forwardToDevTerminal('log', { scope, msg, extra })
}

/** @param {string} scope @param {string} msg @param {unknown} [err] */
export function guardWarn(scope, msg, err) {
  if (!guardDebugEnabled()) return
  const detail =
    err && typeof err === 'object' && 'body' in err
      ? err.body?.detail ?? err.body
      : err && typeof err === 'object' && 'message' in err
        ? err.message
        : err
  console.warn(`[Guard:${scope}]`, msg, detail !== undefined ? detail : '')
  if (err && typeof err === 'object' && err.status != null) {
    console.warn(`[Guard:${scope}] HTTP`, err.status)
  }
  forwardToDevTerminal('warn', { scope, msg, detail })
}

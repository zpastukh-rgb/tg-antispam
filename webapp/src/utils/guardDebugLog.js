/**
 * Логи экранов «Защита» и «Подключённые чаты».
 *
 * Включение:
 * - `npm run dev` — логи включены
 * - прод: `VITE_GUARD_DEBUG=true` при сборке фронта
 * - или в консоли браузера (если доступен localStorage с origin мини-аппа):
 *   `localStorage.setItem('GUARD_DEBUG','1')` и перезагрузка страницы
 *
 * Цепочка «тап по плитке фильтра → полифилл → openProtectionFilterModal» (узкий лог):
 *   `localStorage.setItem('GUARD_FILTER_CHAIN','1')` — без полного GUARD_DEBUG
 *   (в dev включено по умолчанию вместе с dev-сборкой)
 *
 * Терминал (локальный Vite): при `npm run dev` / `vite preview` — POST /__guard_debug_log.
 *
 * Лог в Railway (сервис API, Deploy Logs): при тапе по плитке фильтра клиент шлёт POST
 * `/api/debug/webapp-client-log` с заголовками Mini App. Достаточно валидного `X-Telegram-Init-Data`
 * (как у `/api/me`). Дополнительно можно задать `GUARD_WEBAPP_DEBUG_LOG_TOKEN` на API и WebApp —
 * тогда в заголовке `X-Guard-Webapp-Debug-Token` (опционально для клиента).
 *
 * Как читать цепочку в логах (msg / scope):
 * 1) polyfill: touchend→resolve → synthetic click() → after_native_click_rAF0
 * 2) Protection: openProtectionFilterModal:chain_start (plan.steps — порядок шагов Vue)
 * 3) openProtectionFilterModal:defer_scheduled — только links/mentions (отложенное открытие)
 * 4) openProtectionFilterModal — флаги refs; затем filterModalDom:afterNextTick / rAF1 / rAF2
 *    — dom.ok=false «not-in-dom» значит v-if не смонтировал разметку; ok=true но rect.w/h≈0 — слой есть, но не виден
 */

import { getApiBaseUrl, getInitData, getMiniAppAuthHeaders } from '../api/client.js'

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

function getWebappDebugLogToken() {
  try {
    if (typeof window !== 'undefined') {
      const w = window.__GUARD_WEBAPP_DEBUG_LOG_TOKEN__
      const s = String(w || '').trim()
      if (s.length >= 8) return s
    }
  } catch {
    //
  }
  try {
    const v = import.meta.env.VITE_WEBAPP_DEBUG_LOG_TOKEN
    const s = String(v || '').trim()
    if (s.length >= 8) return s
  } catch {
    //
  }
  return ''
}

/** Production + токен в guard-api-config: можно слать лог без init (редко нужно). */
export function guardRemoteLogSinkReady() {
  if (import.meta.env.DEV) return false
  if (!getApiBaseUrl()) return false
  return getWebappDebugLogToken().length >= 8
}

/** Production: есть база API и (токен или initData) — шлём filter-chain на Railway. */
function filterChainRailwayReady() {
  if (import.meta.env.DEV) return false
  if (!getApiBaseUrl()) return false
  if (getWebappDebugLogToken().length >= 8) return true
  try {
    return !!getInitData()
  } catch {
    return false
  }
}

function forwardFilterChainToApiStdout(payload) {
  if (import.meta.env.DEV) return
  const base = getApiBaseUrl()
  if (!base) return
  const token = getWebappDebugLogToken()
  const hasToken = token.length >= 8
  if (!hasToken && !getInitData()) return

  const headers = { ...getMiniAppAuthHeaders() }
  if (hasToken) headers['X-Guard-Webapp-Debug-Token'] = token
  try {
    fetch(`${base.replace(/\/$/, '')}/api/debug/webapp-client-log`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ kind: 'filter-chain', ...payload }),
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

/** Узкая трассировка: только плитки фильтров + полифилл (см. комментарий вверху файла). */
export function guardFilterChainEnabled() {
  if (import.meta.env.DEV) return true
  try {
    return typeof localStorage !== 'undefined' && localStorage.getItem('GUARD_FILTER_CHAIN') === '1'
  } catch {
    return false
  }
}

/** @param {string} scope @param {string} msg @param {unknown} [extra] */
export function guardFilterChain(scope, msg, extra) {
  const local = guardFilterChainEnabled()
  const railway = filterChainRailwayReady()
  if (!local && !railway) return
  if (extra !== undefined) console.log(`[Guard:filter-chain:${scope}]`, msg, extra)
  else console.log(`[Guard:filter-chain:${scope}]`, msg)
  if (local) forwardToDevTerminal('filter-chain', { scope, msg, extra })
  if (railway) forwardFilterChainToApiStdout({ scope, msg, extra })
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

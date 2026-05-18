import { ref } from 'vue'
import { api, getApiBaseUrl, getInitData } from '../api/client'
import { getLocale } from '../i18n/index.js'
import { guardLog, guardWarn } from '../utils/guardDebugLog.js'

/**
 * initData в Telegram WebApp не реактивен: нельзя оборачивать getInitData() в computed —
 * первое вычисление (часто до готовности WebView) залипает false, и запросы/модалки не стартуют.
 * Держим один ref на весь фронт и коротко поллим, пока не появится подпись или не выйдем по таймауту.
 */
const hasInitData = ref(!!getInitData())

let initDataPollExhaustedLogged = false

function syncHasInitDataFromWindow() {
  const prev = hasInitData.value
  const next = !!getInitData()
  if (hasInitData.value !== next) {
    hasInitData.value = next
    if (!prev && next) {
      guardLog('useApi:initData', 'initData became available (requests can authenticate)')
    }
    if (prev && !next) {
      guardWarn('useApi:initData', 'initData cleared — session may have reset', {})
    }
  }
  try {
    if (typeof window !== 'undefined') {
      const raw = getInitData()
      window.__GUARD_INIT_DATA_DIAG__ = {
        hasFlag: hasInitData.value,
        /** Есть ли непустая строка подписи прямо сейчас (источник тот же, что у fetch). */
        liveLen: typeof raw === 'string' ? raw.length : 0,
        apiBaseLen: String(getApiBaseUrl() || '').length,
      }
    }
  } catch {
    //
  }
  return next
}

/** Принудительно перечитать initData (например перед запросом в тот же тик, когда WebApp только дописал поле). */
export function syncInitDataState() {
  return syncHasInitDataFromWindow()
}

if (typeof window !== 'undefined') {
  syncHasInitDataFromWindow()
  requestAnimationFrame(() => {
    syncHasInitDataFromWindow()
    queueMicrotask(syncHasInitDataFromWindow)
  })
  let ticks = 0
  const pollMs = 50
  const maxTicks = 80
  const id = window.setInterval(() => {
    syncHasInitDataFromWindow()
    ticks += 1
    if (hasInitData.value || ticks >= maxTicks) {
      window.clearInterval(id)
      if (!hasInitData.value && ticks >= maxTicks && !initDataPollExhaustedLogged) {
        initDataPollExhaustedLogged = true
        guardWarn(
          'useApi:initData',
          `still no initData after ~${Math.round((maxTicks * pollMs) / 1000)}s poll (requests may 401 — open panel from Telegram, not external browser)`,
          { telegramWebApp: typeof window.Telegram?.WebApp?.initData === 'string' ? 'present' : 'missing' },
        )
      }
    }
  }, pollMs)
}

/** Сообщения об ошибках с бэка — локализованные (RU/EN). */
export function messageFromApiError(e) {
  const raw = e?.body?.detail ?? e?.message ?? ''
  const detail = typeof raw === 'string' ? raw : String(raw || '')
  const status = e?.status
  const dtrim = detail.trim()
  const dlow = dtrim.toLowerCase()
  const isEn = String(getLocale() || 'ru').toLowerCase().startsWith('en')

  if (status === 503 || dlow.includes('service is starting')) {
    return isEn
      ? 'API is still booting (database warm-up). Wait 15–30 seconds and open the panel again from Telegram.'
      : 'API ещё запускается (прогрев базы). Подождите 15–30 секунд и снова откройте панель из Telegram.'
  }

  const looksLikeNetwork =
    !dtrim ||
    /^load failed$/i.test(dtrim) ||
    /failed to fetch|networkerror|fetch failed|load failed|network request failed|connection refused|aborted/i.test(
      dlow,
    )
  if (looksLikeNetwork) {
    return isEn
      ? (
          'Request to the API failed (network, CORS, or wrong API URL). Check: ' +
          '1) Frontend service env: VITE_API_BASE_URL (or GUARD_API_BASE_URL) = full https://… to the API; ' +
          '2) In Telegram WebView console: window.__GUARD_API_BASE_EFFECTIVE__ matches that URL; ' +
          '3) API allows CORS (e.g. CORS_ORIGINS=* or your Mini App origin).'
        )
      : (
          'Запрос к API не прошёл (сеть, CORS или адрес API). Проверьте: ' +
          '1) у сервиса фронта в Railway задан VITE_API_BASE_URL (или GUARD_API_BASE_URL) = полный https://… API; ' +
          '2) в консоли: window.__GUARD_API_BASE_EFFECTIVE__ и window.__GUARD_INIT_DATA_DIAG__ — база должна совпасть с API, liveLen > 0 если сессия Mini App есть; ' +
          '3) у API CORS_ORIGINS=* или домен Mini App.'
        )
  }
  if (detail === 'Chat not found' || (status === 404 && String(detail).toLowerCase().includes('chat'))) {
    return isEn
      ? 'Chat not found or you have no access. Pick a chat in “Connected chats” or connect a new group.'
      : 'Чат не найден или у вас нет к нему доступа. Выберите чат в разделе «Подключённые чаты» или подключите новую группу.'
  }
  if (detail === 'Chat not found or access denied' || (status === 403 && String(detail).toLowerCase().includes('chat'))) {
    return isEn
      ? 'No access to this chat. Pick another chat in “Connected chats”.'
      : 'Нет доступа к этому чату. Выберите другой чат в разделе «Подключённые чаты».'
  }
  if (status === 401 && (String(detail).toLowerCase().includes('init') || String(detail).toLowerCase().includes('telegram'))) {
    return isEn
      ? (
          'Mini App session is not verified. Close the panel and reopen it via the Menu button inside the bot chat (not from an external browser). ' +
          'If window.__GUARD_INIT_DATA_DIAG__.liveLen is 0, Telegram did not inject initData.'
        )
      : (
          'Сессия Mini App не подтверждена. Закройте панель и откройте снова через кнопку «Меню» в чате с ботом (не из внешнего браузера). ' +
          'Если в консоли window.__GUARD_INIT_DATA_DIAG__.liveLen === 0, Telegram не передал подпись. ' +
          'Если открываете через другого бота — аккаунт должен совпадать с ботом этого API.'
        )
  }
  if (status === 401 && String(detail).toLowerCase().includes('session terminated')) {
    return isEn
      ? 'This session has ended. Reopen the Mini App from Telegram.'
      : 'Эта сессия завершена. Откройте мини-приложение заново из Telegram.'
  }
  return detail || (isEn ? 'Request error' : 'Ошибка запроса')
}

export function useApi() {
  const loading = ref(false)
  const error = ref(null)

  async function fetch(fn) {
    loading.value = true
    error.value = null
    try {
      const data = await fn()
      return data
    } catch (e) {
      error.value = messageFromApiError(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  /** То же, что fetch, но без глобального loading — экран не «мигает» при фоновых запросах */
  async function fetchSilent(fn) {
    error.value = null
    try {
      return await fn()
    } catch (e) {
      error.value = messageFromApiError(e)
      throw e
    }
  }

  return {
    api,
    loading,
    error,
    fetch,
    fetchSilent,
    hasInitData,
  }
}

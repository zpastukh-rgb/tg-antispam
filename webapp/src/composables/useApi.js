import { ref, computed } from 'vue'
import { api, getInitData } from '../api/client'

/** Сообщения об ошибках с бэка — по-русски для пользователя (экспорт для админки / Guard Pulse). */
export function messageFromApiError(e) {
  const raw = e?.body?.detail ?? e?.message ?? ''
  const detail = typeof raw === 'string' ? raw : String(raw || '')
  const status = e?.status
  const dtrim = detail.trim()
  const dlow = dtrim.toLowerCase()

  if (status === 503 || dlow.includes('service is starting')) {
    return 'API ещё запускается (прогрев базы). Подождите 15–30 секунд и снова откройте панель из Telegram.'
  }

  const looksLikeNetwork =
    !dtrim ||
    /^load failed$/i.test(dtrim) ||
    /failed to fetch|networkerror|fetch failed|load failed|network request failed|connection refused|aborted/i.test(
      dlow,
    )
  if (looksLikeNetwork) {
    return (
      'Запрос к API не прошёл (сеть, CORS или адрес API). ' +
      'Проверьте: 1) у сервиса фронта в Railway задан VITE_API_BASE_URL (или GUARD_API_BASE_URL) = полный https://… API; ' +
      '2) в консоли: window.__GUARD_API_BASE_EFFECTIVE__ — должен быть тот же URL; ' +
      '3) у API CORS_ORIGINS=* или домен Mini App.'
    )
  }
  if (detail === 'Chat not found' || (status === 404 && String(detail).toLowerCase().includes('chat'))) {
    return 'Чат не найден или у вас нет к нему доступа. Выберите чат в разделе «Подключённые чаты» или подключите новую группу.'
  }
  if (detail === 'Chat not found or access denied' || (status === 403 && String(detail).toLowerCase().includes('chat'))) {
    return 'Нет доступа к этому чату. Выберите другой чат в разделе «Подключённые чаты».'
  }
  if (status === 401 && (String(detail).toLowerCase().includes('init') || String(detail).toLowerCase().includes('telegram'))) {
    return 'Сессия Mini App не подтверждена. Закройте панель и откройте снова через кнопку «Меню» в чате с ботом (не из внешнего браузера). Если открываете другого бота — у этого аккаунта должен быть тот же бот, что и API на сервере.'
  }
  return detail || 'Ошибка запроса'
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

  const hasInitData = computed(() => !!getInitData())

  return {
    api,
    loading,
    error,
    fetch,
    fetchSilent,
    hasInitData,
  }
}

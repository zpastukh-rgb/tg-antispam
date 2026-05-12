import { ref, computed } from 'vue'
import { api, getInitData } from '../api/client'
import { getLocale } from '../i18n/index.js'

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
      ? 'Request to the API failed (network, CORS or API URL). Check the frontend env vars and CORS.'
      : 'Запрос к API не прошёл (сеть, CORS или адрес API). Проверьте конфигурацию фронтенда и CORS.'
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
      ? 'Mini App session is not verified. Close the panel and open it again via the “Menu” button in the bot chat.'
      : 'Сессия Mini App не подтверждена. Закройте панель и откройте снова через кнопку «Меню» в чате с ботом.'
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

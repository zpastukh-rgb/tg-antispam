import { ref, computed } from 'vue'
import { api, getInitData } from '../api/client'

/** Сообщения об ошибках с бэка — по-русски для пользователя */
function messageFromApiError(e) {
  const detail = e.body?.detail || e.message || ''
  const status = e.status
  if (detail === 'Chat not found' || (status === 404 && String(detail).toLowerCase().includes('chat'))) {
    return 'Чат не найден или у вас нет к нему доступа. Выберите чат в разделе «Подключённые чаты» или подключите новую группу.'
  }
  if (detail === 'Chat not found or access denied' || (status === 403 && String(detail).toLowerCase().includes('chat'))) {
    return 'Нет доступа к этому чату. Выберите другой чат в разделе «Подключённые чаты».'
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

  const hasInitData = computed(() => !!getInitData())

  return {
    api,
    loading,
    error,
    fetch,
    hasInitData,
  }
}

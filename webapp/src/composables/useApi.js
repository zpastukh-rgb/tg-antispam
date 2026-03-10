import { ref, computed } from 'vue'
import { api, getInitData } from '../api/client'

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
      error.value = e.body?.detail || e.message || 'Ошибка запроса'
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

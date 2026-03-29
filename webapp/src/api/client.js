/**
 * API-клиент для бэкенда. Все запросы отправляют initData для авторизации.
 */

const getBaseUrl = () => {
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL.replace(/\/$/, '')
  }
  return ''
}

/**
 * Получить initData для Telegram Web App (или из query для локальной разработки).
 */
export function getInitData() {
  if (typeof window === 'undefined') return ''
  const tg = window.Telegram?.WebApp
  if (tg?.initData) return tg.initData
  const params = new URLSearchParams(window.location.search)
  return params.get('initData') || params.get('tgWebAppData') || ''
}

async function request(method, path, body = null) {
  const base = getBaseUrl()
  const url = path.startsWith('http') ? path : `${base}${path}`
  const initData = getInitData()

  const headers = {
    'Content-Type': 'application/json',
    ...(initData ? { 'X-Telegram-Init-Data': initData } : {}),
  }

  const options = { method, headers }
  if (body != null && method !== 'GET') {
    options.body = JSON.stringify(body)
  }

  const res = await fetch(url, options)
  if (!res.ok) {
    const err = new Error(res.statusText || `HTTP ${res.status}`)
    err.status = res.status
    try {
      err.body = await res.json()
    } catch {
      err.body = { detail: await res.text() }
    }
    throw err
  }

  const contentType = res.headers.get('Content-Type') || ''
  if (contentType.includes('application/json')) {
    return res.json()
  }
  return res.text()
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body),
  patch: (path, body) => request('PATCH', path, body),
  delete: (path) => request('DELETE', path),

  me: () => api.get('/api/me'),
  chats: () => api.get('/api/chats'),
  selectChat: (chatId) => api.post('/api/chats/select', { chat_id: chatId }),
  chat: (chatId) => api.get(`/api/chat/${chatId}`),
  updateRule: (chatId, rule) => api.patch(`/api/chat/${chatId}/rule`, rule),
  addStopword: (chatId, word) => api.post(`/api/chat/${chatId}/stopwords`, { word }),
  deleteStopword: (chatId, word) => api.delete(`/api/chat/${chatId}/stopwords?word=${encodeURIComponent(word)}`),
  connectPending: () => api.get('/api/connect/pending'),
  billing: () => api.get('/api/billing'),
  botInfo: () => api.get('/api/bot-info'),
  globalAntispamList: () => api.get('/api/global-antispam'),
  globalAntispamAdd: (userId, reason) => api.post('/api/global-antispam', { user_id: userId, reason: reason || '' }),
  globalAntispamRemove: (userId) => api.delete(`/api/global-antispam/${userId}`),
  setReportsChat: (chatId, logChatId) => api.post(`/api/chat/${chatId}/reports-chat`, { log_chat_id: logChatId }),
  copySettings: (chatId, targetChatId) => api.post(`/api/chat/${chatId}/copy-settings`, { target_chat_id: targetChatId }),
  promoApply: (code) => api.post('/api/promo/apply', { code }),
  yookassaCreatePayment: (months) => api.post('/api/payments/yookassa/create', { months }),
}

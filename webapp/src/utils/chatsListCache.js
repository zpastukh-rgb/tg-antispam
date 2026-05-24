import { readSessionJson, writeSessionJson, readLocalJson, writeLocalJson } from './sessionCache.js'

export const CHATS_LIST_CACHE_PREFIX = 'guard.chats.list.v1'

export function chatsCacheKey(mode) {
  return `${CHATS_LIST_CACHE_PREFIX}:${mode === 'shared' ? 'shared' : 'all'}`
}

function viewerIdFromInit() {
  try {
    const id = window.Telegram?.WebApp?.initDataUnsafe?.user?.id
    const n = Number(id || 0)
    return Number.isFinite(n) && n > 0 ? n : 0
  } catch {
    return 0
  }
}

function isDelegatedCabinetChatRow(chat, viewerId) {
  if (!chat) return false
  const oid = Number(chat.owner_user_id || 0)
  const vid = Number(viewerId || 0)
  if (oid > 0 && vid > 0 && oid === vid) return false
  if (oid > 0 && oid !== vid) return true
  return !!chat.is_shared
}

export function sortChatsRows(rows, delegatedOnly, viewerId = 0) {
  const list = Array.isArray(rows) ? rows : []
  if (delegatedOnly) return list
  const vid = Number(viewerId || 0) > 0 ? Number(viewerId) : viewerIdFromInit()
  return [...list].sort(
    (a, b) => Number(isDelegatedCabinetChatRow(b, vid)) - Number(isDelegatedCabinetChatRow(a, vid)),
  )
}

export function readChatsListCache(mode) {
  const key = chatsCacheKey(mode)
  return readSessionJson(key, 10 * 60 * 1000) || readLocalJson(key, 24 * 60 * 60 * 1000)
}

export function writeChatsListCache(mode, data) {
  const key = chatsCacheKey(mode)
  writeSessionJson(key, data)
  writeLocalJson(key, data)
}

const fetchInFlight = {}

/** Один in-flight запрос на mode — prefetch и экран «Чаты» делят один ответ. */
export function fetchChatsList(apiClient, mode = 'all') {
  const key = mode === 'shared' ? 'shared' : 'all'
  if (fetchInFlight[key]) return fetchInFlight[key]
  fetchInFlight[key] = apiClient.chats(key).finally(() => {
    fetchInFlight[key] = null
  })
  return fetchInFlight[key]
}

function cacheChatsApiResponse(mode, data, viewerId = 0) {
  const key = mode === 'shared' ? 'shared' : 'all'
  const prev = readChatsListCache(key)
  const rows = sortChatsRows(data?.chats || [], key === 'shared', viewerId)
  const payload = {
    rows,
    selected_chat_id: data?.selected_chat_id ?? null,
    pending_count: Number(prev?.pending_count || 0),
    spike_alerts: prev?.spike_alerts && typeof prev.spike_alerts === 'object' ? prev.spike_alerts : {},
  }
  writeChatsListCache(key, payload)
  return payload
}

export async function prefetchChatsList(apiClient, mode, viewerId = 0) {
  const key = mode === 'shared' ? 'shared' : 'all'
  try {
    const data = await fetchChatsList(apiClient, key)
    return cacheChatsApiResponse(key, data, viewerId)
  } catch {
    return null
  }
}

export async function fetchAndCacheChatsList(apiClient, mode, viewerId = 0) {
  const key = mode === 'shared' ? 'shared' : 'all'
  const data = await fetchChatsList(apiClient, key)
  const payload = cacheChatsApiResponse(key, data, viewerId)
  return { data, ...payload }
}

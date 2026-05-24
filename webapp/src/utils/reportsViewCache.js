import { readSessionJson, writeSessionJson, readLocalJson, writeLocalJson } from './sessionCache.js'
import { prefetchChatsList, readChatsListCache } from './chatsListCache.js'

export const REPORTS_VIEW_CACHE_KEY = 'guard.reports.view.v1'
export const REPORTS_BOT_INFO_CACHE_KEY = 'guard.reports.bot_info.v1'

export function buildReportsUrl(botData, protectedChatId) {
  const tpl = botData?.reports_chat_url_template
  if (tpl && protectedChatId != null) {
    return tpl.replace(/\{chat_id\}/g, String(protectedChatId))
  }
  const u = String(botData?.username || '').replace(/^@+/, '').trim()
  if (!u || protectedChatId == null) return null
  return `https://t.me/${u}?startgroup=reportschat_${protectedChatId}`
}

export function isReportsSelectableChat(c) {
  return String(c?.chat_kind || 'group').toLowerCase() !== 'channel'
}

export function filterReportsSelectableChats(list) {
  return (list || []).filter(isReportsSelectableChat)
}

export function readReportsViewCache() {
  return (
    readSessionJson(REPORTS_VIEW_CACHE_KEY, 10 * 60 * 1000) ||
    readLocalJson(REPORTS_VIEW_CACHE_KEY, 24 * 60 * 60 * 1000)
  )
}

export function writeReportsViewCache(data) {
  writeSessionJson(REPORTS_VIEW_CACHE_KEY, data)
  writeLocalJson(REPORTS_VIEW_CACHE_KEY, data)
}

export function readBotInfoCache() {
  return (
    readSessionJson(REPORTS_BOT_INFO_CACHE_KEY, 30 * 60 * 1000) ||
    readLocalJson(REPORTS_BOT_INFO_CACHE_KEY, 24 * 60 * 60 * 1000)
  )
}

export function writeBotInfoCache(data) {
  if (!data || typeof data !== 'object') return
  writeSessionJson(REPORTS_BOT_INFO_CACHE_KEY, data)
  writeLocalJson(REPORTS_BOT_INFO_CACHE_KEY, data)
}

const chatFetchInFlight = {}

export function fetchChatDeduped(apiClient, chatId) {
  const key = String(chatId || '')
  if (!key || key === '0') return Promise.reject(new Error('invalid chat id'))
  if (chatFetchInFlight[key]) return chatFetchInFlight[key]
  chatFetchInFlight[key] = apiClient.chat(Number(chatId)).finally(() => {
    chatFetchInFlight[key] = null
  })
  return chatFetchInFlight[key]
}

export function pickReportsSelection(rows, preferredId = null, fallbackSelectedId = null) {
  const selectable = filterReportsSelectableChats(rows)
  const preferred = Number(preferredId || 0)
  if (preferred > 0 && selectable.some((c) => Number(c.id) === preferred)) return preferred
  const fromServer = Number(fallbackSelectedId || 0)
  if (fromServer > 0 && selectable.some((c) => Number(c.id) === fromServer)) return fromServer
  return Number(selectable[0]?.id || 0) || null
}

export function buildReportsShellChat(row, chatId, fromPartial = null) {
  const id = Number(chatId || row?.id || 0)
  const partial = fromPartial && typeof fromPartial === 'object' ? fromPartial : null
  return {
    id,
    title: String(partial?.title || row?.title || id || '').trim() || String(id),
    log_chat_id: partial?.log_chat_id ?? null,
    log_chat_title: partial?.log_chat_title ?? null,
    rule: partial?.rule || {
      log_enabled: true,
      auto_reports_enabled: false,
    },
  }
}

export function buildReportsSnapshotPayload(rows, selectedId, chat, botInfo, reportsChatUrl, extras = {}) {
  return {
    chatsList: rows || [],
    selectedChatId: selectedId ?? null,
    chat: chat || null,
    botInfo: botInfo || null,
    reportsChatUrl: reportsChatUrl ?? null,
    ...extras,
  }
}

export async function prefetchReportsView(apiClient) {
  try {
    const chatsPayload = await prefetchChatsList(apiClient, 'all')
    const rows = chatsPayload?.rows || readChatsListCache('all')?.rows || []
    if (!rows.length) return null

    const selectedId = pickReportsSelection(rows, null, chatsPayload?.selected_chat_id)
    const cachedBot = readBotInfoCache()
    const row = rows.find((c) => Number(c.id) === Number(selectedId))

    if (!selectedId) {
      writeReportsViewCache(
        buildReportsSnapshotPayload(rows, null, { noSelection: true }, cachedBot, null),
      )
      return null
    }

    const botPromise = cachedBot ? Promise.resolve(cachedBot) : apiClient.botInfo().catch(() => null)
    const chatPromise = fetchChatDeduped(apiClient, selectedId).catch(() => null)
    const [botData, chatData] = await Promise.all([botPromise, chatPromise])

    if (botData) writeBotInfoCache(botData)
    const bot = botData || cachedBot || null
    const chat = chatData?.rule ? chatData : buildReportsShellChat(row, selectedId, chatData)
    writeReportsViewCache(
      buildReportsSnapshotPayload(
        rows,
        selectedId,
        chat,
        bot,
        buildReportsUrl(bot, selectedId),
      ),
    )
    return chatData || chat
  } catch {
    return null
  }
}

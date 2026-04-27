/**
 * API-клиент для бэкенда. Все запросы отправляют initData для авторизации.
 */

function trimApiBase(raw) {
  if (raw == null) return ''
  let s = String(raw).trim()
  if ((s.startsWith('"') && s.endsWith('"')) || (s.startsWith("'") && s.endsWith("'"))) {
    s = s.slice(1, -1).trim()
  }
  s = s.replace(/\/$/, '')
  if (!s || s.toLowerCase() === 'undefined') return ''
  return s
}

/**
 * Порядок: 1) window из /guard-api-config.js (Railway рантайм) 2) Vite build 3) meta.
 */
const getBaseUrl = () => {
  if (typeof window !== 'undefined') {
    try {
      const w = trimApiBase(window.__GUARD_API_BASE__)
      if (w && /^https?:\/\//i.test(w)) return w
    } catch {
      //
    }
  }
  const fromEnv = trimApiBase(import.meta.env.VITE_API_BASE_URL)
  if (fromEnv) return fromEnv
  if (typeof window !== 'undefined') {
    try {
      const meta = document.querySelector('meta[name="guard-api-base"]')?.getAttribute('content')
      const m = trimApiBase(meta)
      if (m && /^https?:\/\//i.test(m)) return m
    } catch {
      //
    }
  }
  return ''
}

if (typeof window !== 'undefined' && import.meta.env.PROD) {
  window.__GUARD_API_BASE_BUILT__ = trimApiBase(import.meta.env.VITE_API_BASE_URL) || ''
}

/**
 * Получить initData для Telegram Web App (или из query для локальной разработки).
 */
function readInitDataFromUrl() {
  if (typeof window === 'undefined') return ''
  const fromSearch = new URLSearchParams(window.location.search)
  const s = fromSearch.get('initData') || fromSearch.get('tgWebAppData') || ''
  if (s) return s
  const hashRaw = String(window.location.hash || '')
  if (hashRaw.startsWith('#')) {
    const hash = hashRaw.slice(1)
    const idx = hash.indexOf('?')
    const hashQuery = idx >= 0 ? hash.slice(idx + 1) : hash
    if (hashQuery) {
      const fromHash = new URLSearchParams(hashQuery)
      return fromHash.get('initData') || fromHash.get('tgWebAppData') || ''
    }
  }
  return ''
}

export function getInitData() {
  if (typeof window === 'undefined') return ''
  const tg = window.Telegram?.WebApp
  if (tg?.initData) return tg.initData
  const fromUrl = readInitDataFromUrl()
  if (fromUrl) {
    try {
      sessionStorage.setItem('guard.initData', fromUrl)
    } catch {
      //
    }
    return fromUrl
  }
  try {
    return sessionStorage.getItem('guard.initData') || ''
  } catch {
    return ''
  }
}

async function request(method, path, body = null) {
  const base = getBaseUrl()
  /**
   * В проде без VITE_API_BASE_URL запросы вида /api/me уходят на тот же хост, что и статика
   * (serve/nginx), и не достигают бэкенда — пользователь видит «не удалось связаться с сервером».
   */
  if (import.meta.env.PROD && !path.startsWith('http') && !base) {
    const err = new Error('API base URL missing')
    err.status = 0
    err.body = {
      detail:
        'Веб-приложение собрано без адреса API (переменная VITE_API_BASE_URL на этапе сборки). Укажите полный URL бэкенда в настройках деплоя фронта (например Railway → Variables) и пересоберите сервис.',
    }
    throw err
  }
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

  let res
  try {
    res = await fetch(url, options)
  } catch (netErr) {
    const err = new Error(netErr?.message || 'fetch failed')
    err.status = 0
    err.body = { detail: netErr?.message || 'fetch failed' }
    err.cause = netErr
    throw err
  }
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

if (typeof window !== 'undefined') {
  queueMicrotask(() => {
    try {
      window.__GUARD_API_BASE_EFFECTIVE__ = getBaseUrl()
    } catch {
      //
    }
  })
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body),
  put: (path, body) => request('PUT', path, body),
  patch: (path, body) => request('PATCH', path, body),
  delete: (path) => request('DELETE', path),

  me: () => api.get('/api/me'),
  presencePing: () => api.post('/api/presence/ping', {}),
  chats: (mode = 'all', opts = {}) => {
    const q = new URLSearchParams()
    q.set('mode', String(mode || 'all'))
    if (opts?.refreshTelegram) q.set('refresh_telegram', '1')
    return api.get(`/api/chats?${q.toString()}`)
  },
  selectChat: (chatId) => api.post('/api/chats/select', { chat_id: chatId }),
  chat: (chatId, opts = {}) => {
    const q = new URLSearchParams()
    if (opts?.refreshTelegram) q.set('refresh_telegram', '1')
    const qs = q.toString()
    return api.get(`/api/chat/${chatId}${qs ? `?${qs}` : ''}`)
  },
  chatSetActive: (chatId, active) => api.post(`/api/chat/${chatId}/active`, { active: !!active }),
  cleanDeleted: (chatId) => api.post(`/api/chat/${chatId}/clean-deleted`, {}),
  removeChat: (chatId) => api.delete(`/api/chat/${chatId}`),
  updateRule: (chatId, rule) => api.patch(`/api/chat/${chatId}/rule`, rule),
  sendChatRulesNow: (chatId, payload) => api.post(`/api/chat/${chatId}/rules/send`, payload || {}),
  channelRuleDraftsGet: (chatId) => api.get(`/api/chat/${chatId}/channel-rule-drafts`),
  channelRuleDraftsSet: (chatId, drafts = []) => api.post(`/api/chat/${chatId}/channel-rule-drafts`, { drafts }),
  addStopword: (chatId, word) => api.post(`/api/chat/${chatId}/stopwords`, { word }),
  deleteStopword: (chatId, word) => api.delete(`/api/chat/${chatId}/stopwords?word=${encodeURIComponent(word)}`),
  chatReputation: (chatId) => api.get(`/api/chat/${chatId}/reputation`),
  addReputationWord: (chatId, word) => api.post(`/api/chat/${chatId}/reputation/words`, { word }),
  deleteReputationWord: (chatId, word) => api.delete(`/api/chat/${chatId}/reputation/words?word=${encodeURIComponent(word)}`),
  addWhitelistDomain: (chatId, domain) => api.post(`/api/chat/${chatId}/whitelist/domains`, { domain }),
  deleteWhitelistDomain: (chatId, domain) =>
    api.delete(`/api/chat/${chatId}/whitelist/domains?domain=${encodeURIComponent(domain)}`),
  addWhitelistUser: (chatId, userRef) => api.post(`/api/chat/${chatId}/whitelist/users`, { user_ref: userRef }),
  deleteWhitelistUser: (chatId, userId) =>
    api.delete(`/api/chat/${chatId}/whitelist/users?target_user_id=${encodeURIComponent(userId)}`),
  addWhitelistSenderChat: (chatId, channel) =>
    api.post(`/api/chat/${chatId}/whitelist/sender-chats`, { channel }),
  deleteWhitelistSenderChat: (chatId, channelUsername) =>
    api.delete(`/api/chat/${chatId}/whitelist/sender-chats?channel_username=${encodeURIComponent(channelUsername)}`),
  deleteWelcomePhoto: (chatId) => api.delete(`/api/chat/${chatId}/welcome/photo`),
  addLinkBlacklistPattern: (chatId, pattern) => api.post(`/api/chat/${chatId}/link-blacklist`, { pattern }),
  deleteLinkBlacklistPattern: (chatId, pattern) =>
    api.delete(`/api/chat/${chatId}/link-blacklist?pattern=${encodeURIComponent(pattern)}`),
  connectPending: () => api.get('/api/connect/pending'),
  connectActivatePending: () => api.post('/api/connect/pending/activate', {}),
  connectCleanupPending: (hours = 24) => api.post('/api/connect/pending/cleanup', { hours }),
  connectClearAllPending: () => api.post('/api/connect/pending/clear-all', {}),
  billing: () => api.get('/api/billing'),
  activitySummary: () => api.get('/api/activity/summary'),
  ownerJoinReportSettings: () => api.get('/api/owner/join-report-settings'),
  ownerSetJoinReportSettings: (periods = []) => api.post('/api/owner/join-report-settings', { periods }),
  activityHours: (chatId = null, hours = 24, fromTs = '', toTs = '') => {
    const params = new URLSearchParams()
    if (chatId != null && chatId !== '') params.set('chat_id', String(chatId))
    if (fromTs && toTs) {
      params.set('from_ts', String(fromTs))
      params.set('to_ts', String(toTs))
    } else {
      params.set('hours', String(hours || 24))
    }
    return api.get(`/api/activity/hours?${params.toString()}`)
  },
  activitySlotDetail: (fromTs, toTs, chatId = null) => {
    const q = new URLSearchParams()
    q.set('from_ts', String(fromTs))
    q.set('to_ts', String(toTs))
    if (chatId != null && chatId !== '') q.set('chat_id', String(chatId))
    return api.get(`/api/activity/slot-detail?${q.toString()}`)
  },
  activityAudienceGender: (chatId = null) => {
    const q = new URLSearchParams()
    if (chatId != null && chatId !== '') q.set('chat_id', String(chatId))
    return api.get(`/api/activity/audience-gender?${q.toString()}`)
  },
  activityJournal: (chatId = null, limit = 100, fromTs = '', toTs = '') => {
    const qs = [`limit=${encodeURIComponent(limit)}`]
    if (chatId != null && chatId !== '') qs.push(`chat_id=${encodeURIComponent(chatId)}`)
    if (fromTs) qs.push(`from_ts=${encodeURIComponent(fromTs)}`)
    if (toTs) qs.push(`to_ts=${encodeURIComponent(toTs)}`)
    return api.get(`/api/activity/journal?${qs.join('&')}`)
  },
  activityGroupBreakdown: (chatId, opts = {}) => {
    const q = new URLSearchParams()
    q.set('chat_id', String(chatId))
    if (opts.fromTs && opts.toTs) {
      q.set('from_ts', String(opts.fromTs))
      q.set('to_ts', String(opts.toTs))
    } else if (opts.hours != null) {
      q.set('hours', String(opts.hours))
    } else {
      q.set('hours', '24')
    }
    return api.get(`/api/activity/group-breakdown?${q.toString()}`)
  },
  referral: () => api.get('/api/referral'),
  referralPeople: () => api.get('/api/referral/people'),
  referralShareHit: () => api.post('/api/referral/share-hit', {}),
  referralBonusToSub: () => api.post('/api/referral/bonus-to-sub', {}),
  referralBonusToAurum: () => api.post('/api/referral/bonus-to-aurum', {}),
  referralPayouts: () => api.get('/api/referral/payouts'),
  referralPayoutRequest: (payload) => api.post('/api/referral/payouts/request', payload),
  adminOverview: () => api.get('/api/admin/overview'),
  adminInsightsSummary: (hours = 24) => api.get(`/api/admin/insights/summary?hours=${encodeURIComponent(hours)}`),
  adminMessageTemplates: () => api.get('/api/admin/message-templates'),
  adminMessageTemplateOptions: () => api.get('/api/admin/message-templates/options'),
  adminMessageTemplateCreate: (body) => api.post('/api/admin/message-templates', body),
  adminMessageTemplatePatch: (id, body) => api.patch(`/api/admin/message-templates/${id}`, body),
  adminMessageTemplateDelete: (id) => api.delete(`/api/admin/message-templates/${id}`),
  adminPayouts: () => api.get('/api/admin/payouts'),
  adminSetPayoutStatus: (id, status, admin_note = '') => api.post(`/api/admin/payouts/${id}/status`, { status, admin_note }),
  adminReferralsTop: () => api.get('/api/admin/referrals/top'),
  adminCommissions: () => api.get('/api/admin/commissions'),
  adminCommissionsSummary: () => api.get('/api/admin/commissions/summary'),
  adminUsers: () => api.get('/api/admin/users'),
  adminUserSubscriptionProfile: (telegramId) =>
    api.get(`/api/admin/users/${encodeURIComponent(telegramId)}/subscription-profile`),
  adminDeleteBlockUser: (telegramId) => api.post(`/api/admin/users/${telegramId}/delete-block`, {}),
  adminUnblockUser: (telegramId) => api.post(`/api/admin/users/${telegramId}/unblock`, {}),
  adminChats: () => api.get('/api/admin/chats'),
  adminRevenueStats: (period = '30d') => api.get(`/api/admin/revenue-stats?period=${encodeURIComponent(period)}`),
  adminReferralFunnel: () => api.get('/api/admin/referrals/funnel'),
  adminMyPartnerStats: () => api.get('/api/admin/my-partner-stats'),
  adminOpsHealth: () => api.get('/api/admin/ops/health'),
  adminDiagnosticsSummary: (windowHours = 24) =>
    api.get(`/api/admin/diagnostics/summary?window_hours=${encodeURIComponent(String(windowHours))}`),
  adminDiagnosticsFeed: (limit = 80, q = '') => {
    const qs = new URLSearchParams()
    qs.set('limit', String(limit))
    const t = String(q || '').trim()
    if (t) qs.set('q', t)
    return api.get(`/api/admin/diagnostics/feed?${qs.toString()}`)
  },
  adminOpsAction: (action) => api.post('/api/admin/ops/action', { action }),
  adminResetUserFinance: (telegramId) => api.post(`/api/admin/users/${telegramId}/reset-finance`, {}),
  adminUserResetDelegation: (telegramId) => api.post(`/api/admin/users/${telegramId}/reset-delegation`, {}),
  adminUserResetConnectedChats: (telegramId) => api.post(`/api/admin/users/${telegramId}/reset-connected-chats`, {}),
  adminUserSetJoinReportSettings: (telegramId, periods = []) =>
    api.post(`/api/admin/users/${telegramId}/join-report-settings`, { periods }),
  adminTestCreateSubscriptionPayment: (months, targetTelegramId = null) =>
    api.post('/api/admin/test-payments/create-subscription', {
      months,
      ...(targetTelegramId ? { target_telegram_id: targetTelegramId } : {}),
    }),
  adminTestCreateTokensPayment: (tokens, targetTelegramId = null) =>
    api.post('/api/admin/test-payments/create-tokens', {
      tokens,
      ...(targetTelegramId ? { target_telegram_id: targetTelegramId } : {}),
    }),
  adminTestCreateBindingProbePayment: (targetTelegramId = null, mode = 'live') =>
    api.post('/api/admin/test-payments/create-binding-probe', {
      mode,
      ...(targetTelegramId ? { target_telegram_id: targetTelegramId } : {}),
    }),
  historyPayments: () => api.get('/api/history/payments'),
  historyTokens: () => api.get('/api/history/tokens'),
  historySubscription: () => api.get('/api/history/subscription'),
  spikeAlerts: () => api.get('/api/alerts/spike'),
  sendReceiptEmail: (payment_id, email, full_name) => api.post('/api/history/payments/receipt', { payment_id, email, full_name }),
  botInfo: () => api.get('/api/bot-info'),
  adminGlobalBadUrlsList: () => api.get('/api/admin/global-bad-urls'),
  meGlobalBadUrlsList: () => api.get('/api/me/global-bad-urls'),
  meGlobalBadUrlsAdd: (body) => api.post('/api/me/global-bad-urls', body),
  meGlobalBadUrlsDelete: (pattern) =>
    api.delete(`/api/me/global-bad-urls?pattern=${encodeURIComponent(pattern)}`),
  /** Черновики «правила в группе» — синхронизация между телефоном и ПК (один Telegram-аккаунт). */
  mePostRulesDraftsGet: () => api.get('/api/me/post-rules-drafts'),
  mePostRulesDraftsPut: (drafts) => api.put('/api/me/post-rules-drafts', { drafts: drafts || [] }),
  adminGlobalBadUrlsAdd: (body) => api.post('/api/admin/global-bad-urls', body),
  adminGlobalBadUrlsDelete: (pattern) =>
    api.delete(`/api/admin/global-bad-urls?pattern=${encodeURIComponent(pattern)}`),
  globalAntispamList: () => api.get('/api/global-antispam'),
  globalAntispamAdd: (userId, reason) => api.post('/api/global-antispam', { user_id: userId, reason: reason || '' }),
  globalAntispamRemove: (userId) => api.delete(`/api/global-antispam/${userId}`),
  setReportsChat: (chatId, logChatId) => api.post(`/api/chat/${chatId}/reports-chat`, { log_chat_id: logChatId }),
  chatManagers: (chatId) => api.get(`/api/chat/${chatId}/managers`),
  chatManagerAdd: (chatId, payload) => api.post(`/api/chat/${chatId}/managers`, payload),
  chatManagerRemove: (chatId, managerUserId) => api.delete(`/api/chat/${chatId}/managers/${managerUserId}`),
  chatManagerInviteCancel: (chatId, inviteId) => api.delete(`/api/chat/${chatId}/manager-invites/${inviteId}`),
  copySettings: (chatId, targetChatId) => api.post(`/api/chat/${chatId}/copy-settings`, { target_chat_id: targetChatId }),
  chatMemberUnban: (chatId, targetUserId) =>
    api.post(`/api/chat/${chatId}/member-unban`, { user_id: Number(targetUserId) }),
  chatMemberUnmute: (chatId, targetUserId) =>
    api.post(`/api/chat/${chatId}/member-unmute`, { user_id: Number(targetUserId) }),
  promoApply: (code) => api.post('/api/promo/apply', { code }),
  yookassaCreatePayment: (months) => api.post('/api/payments/yookassa/create', { months }),
  yookassaReconcilePending: () => api.post('/api/payments/yookassa/reconcile-pending', {}),
  disableAutorenew: () => api.post('/api/payments/autorenew/disable', {}),
  /** Только для TG id из TEST_TARIFF_PAYMENT_TELEGRAM_IDS (отдельный путь от продовой оплаты). */
  yookassaCreateTestSubscriptionPayment: (months) =>
    api.post('/api/payments/yookassa/create-test-subscription', { months }),
  yookassaCreateTokensPayment: (tokens) => api.post('/api/payments/yookassa/create-tokens', { tokens }),
  adminBroadcasts: (scope = 'mine') =>
    api.get(`/api/admin/broadcasts?scope=${encodeURIComponent(scope === 'all' ? 'all' : 'mine')}`),
  /** scope: mine | all — группы этого бота для рассылки (не «вся админка чатов»). */
  adminBroadcastGroups: (scope = 'mine') =>
    api.get(`/api/admin/broadcast/groups?scope=${encodeURIComponent(scope)}`),
  adminBroadcastChannels: (scope = 'mine') =>
    api.get(`/api/admin/broadcast/channels?scope=${encodeURIComponent(scope === 'all' ? 'all' : 'mine')}`),
  adminBroadcast: (id) => api.get(`/api/admin/broadcasts/${id}`),
  adminBroadcastStats: (id, batchId = '', fromTs = '', toTs = '', targetKind = '') => {
    const params = new URLSearchParams()
    if (batchId) params.set('batch_id', String(batchId))
    if (fromTs) params.set('from_ts', String(fromTs))
    if (toTs) params.set('to_ts', String(toTs))
    if (targetKind) params.set('target_kind', String(targetKind))
    const qs = params.toString()
    return api.get(`/api/admin/broadcasts/${id}/stats${qs ? `?${qs}` : ''}`)
  },
  adminBroadcastAutopostStats: (id, days = 7) =>
    api.get(
      `/api/admin/broadcasts/${encodeURIComponent(String(id))}/autopost-stats?days=${encodeURIComponent(String(Math.min(30, Math.max(1, Number(days) || 7))))}`,
    ),
  adminBroadcastCreate: (body) => api.post('/api/admin/broadcasts', body),
  adminBroadcastPatch: (id, body) => api.patch(`/api/admin/broadcasts/${id}`, body),
  adminBroadcastDelete: (id) => api.delete(`/api/admin/broadcasts/${id}`),
  adminBroadcastSend: (id, target = 'users', chatIds = []) => api.post(`/api/admin/broadcasts/${id}/send`, { target, chat_ids: chatIds }),
  adminBroadcastQuote: (id, target = 'users', chatIds = []) => api.post(`/api/admin/broadcasts/${id}/quote`, { target, chat_ids: chatIds }),
  adminAutopostCampaigns: () => api.get('/api/admin/autopost-campaigns'),
  adminAutopostCampaignCreate: (body) => api.post('/api/admin/autopost-campaigns', body),
  adminAutopostCampaignPatch: (id, body) => api.patch(`/api/admin/autopost-campaigns/${id}`, body),
  adminAutopostCampaignDelete: (id) => api.delete(`/api/admin/autopost-campaigns/${id}`),
  adminAutopostCampaignAutopostStats: (id, days = 7) =>
    api.get(
      `/api/admin/autopost-campaigns/${encodeURIComponent(String(id))}/autopost-stats?days=${encodeURIComponent(String(Math.min(30, Math.max(1, Number(days) || 7))))}`,
    ),
  billingTokenPacks: () => api.get('/api/billing/token-packs'),
  /** Владелец: кто платит AURUM за рассылки делегата — owner | delegate | delegate_first */
  meDelegateBroadcastPayerPatch: (value) => api.patch('/api/me/delegate-broadcast-payer', { value }),
  /** Перевод AURUM владельца менеджеру (менеджер должен быть в chat_managers хотя бы одного чата владельца). */
  billingAurumTransferToDelegate: (targetTelegramId, amount) =>
    api.post('/api/billing/aurum-transfer-to-delegate', {
      target_telegram_id: Number(targetTelegramId),
      amount: Number(amount),
    }),
}

/**
 * Загрузка фото/видео/GIF/документа к черновику рассылки (multipart).
 */
export async function adminBroadcastUploadMedia(broadcastId, file, mediaKind = '') {
  const base = getBaseUrl()
  const url = `${base}/api/admin/broadcasts/${broadcastId}/media`
  const initData = getInitData()
  const fd = new FormData()
  fd.append('file', file)
  fd.append('media_kind', mediaKind || '')
  const res = await fetch(url, {
    method: 'POST',
    headers: initData ? { 'X-Telegram-Init-Data': initData } : {},
    body: fd,
  })
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
  return res.json()
}

export async function uploadChatWelcomePhoto(chatId, file) {
  const base = getBaseUrl()
  const url = `${base}/api/chat/${chatId}/welcome/photo`
  const initData = getInitData()
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(url, {
    method: 'POST',
    headers: initData ? { 'X-Telegram-Init-Data': initData } : {},
    body: fd,
  })
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
  return res.json()
}

export async function fetchChatWelcomePhotoPreviewUrl(chatId) {
  const base = getBaseUrl()
  const url = `${base}/api/chat/${chatId}/welcome/photo`
  const initData = getInitData()
  const res = await fetch(url, {
    method: 'GET',
    headers: initData ? { 'X-Telegram-Init-Data': initData } : {},
  })
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
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}

export async function uploadChatRulesPhoto(chatId, target, file) {
  const base = getBaseUrl()
  const initData = getInitData()
  const fd = new FormData()
  fd.append('target', String(target || 'group'))
  fd.append('file', file)
  const url = `${base}/api/chat/${chatId}/rules/photo`
  const r = await fetch(url, {
    method: 'POST',
    headers: initData ? { 'X-Telegram-Init-Data': initData } : {},
    body: fd,
  })
  if (!r.ok) {
    const err = new Error(r.statusText || `HTTP ${r.status}`)
    err.status = r.status
    try {
      err.body = await r.json()
    } catch {
      err.body = { detail: await r.text() }
    }
    throw err
  }
  return r.json()
}

export async function fetchChatRulesPhotoPreviewUrl(chatId, target) {
  const base = getBaseUrl()
  const initData = getInitData()
  const url = `${base}/api/chat/${chatId}/rules/photo?target=${encodeURIComponent(String(target || 'group'))}`
  const r = await fetch(url, { headers: initData ? { 'X-Telegram-Init-Data': initData } : {} })
  if (!r.ok) {
    const err = new Error(r.statusText || `HTTP ${r.status}`)
    err.status = r.status
    try {
      err.body = await r.json()
    } catch {
      err.body = { detail: await r.text() }
    }
    throw err
  }
  const blob = await r.blob()
  return URL.createObjectURL(blob)
}

export async function deleteChatRulesPhoto(chatId, target) {
  return api.delete(`/api/chat/${chatId}/rules/photo?target=${encodeURIComponent(String(target || 'group'))}`)
}

/**
 * Загрузка файла медиа для превью (object URL — вызовите URL.revokeObjectURL когда не нужен).
 */
export async function fetchAdminBroadcastMediaPreviewUrl(broadcastId, mediaId) {
  const base = getBaseUrl()
  const url = `${base}/api/admin/broadcasts/${broadcastId}/media/${mediaId}/file`
  const initData = getInitData()
  const res = await fetch(url, {
    method: 'GET',
    headers: initData ? { 'X-Telegram-Init-Data': initData } : {},
  })
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
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}

export function revokeBroadcastMediaPreviewUrl(u) {
  if (!u || typeof u !== 'string') return
  try {
    URL.revokeObjectURL(u)
  } catch {
    // ignore
  }
}

export async function adminBroadcastDeleteMediaItem(broadcastId, mediaId) {
  const base = getBaseUrl()
  const url = `${base}/api/admin/broadcasts/${broadcastId}/media/${mediaId}`
  const initData = getInitData()
  const res = await fetch(url, {
    method: 'DELETE',
    headers: initData ? { 'X-Telegram-Init-Data': initData } : {},
  })
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
  return res.json()
}

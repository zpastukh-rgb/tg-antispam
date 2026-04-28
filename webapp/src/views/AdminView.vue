<script setup>
import { ref, shallowRef, onMounted, onBeforeUnmount, computed, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useApi, messageFromApiError } from '../composables/useApi'
import {
  adminBroadcastUploadMedia,
  adminBroadcastDeleteMediaItem,
  fetchAdminBroadcastMediaPreviewUrl,
  revokeBroadcastMediaPreviewUrl,
  getInitData,
} from '../api/client'
import { hasFullAdminRights } from '../utils/adminAccess'
import { useCabinetMode } from '../composables/useCabinetMode'
import SubscriptionManagementPanel from '../components/SubscriptionManagementPanel.vue'

const { api, fetch, fetchSilent, hasInitData } = useApi()
const route = useRoute()
const { cabinetMode, setCabinetMode } = useCabinetMode()
/** С первого кадра при открытии из Telegram — не мелькает полная админка до загрузки /me */
const loading = ref(!!getInitData())
const error = ref('')
const data = ref(null)
const tab = ref('overview')
const payouts = ref([])
const referralsTop = ref([])
const referralInfo = ref(null)
const commissions = ref([])
const commissionsSummary = ref({ pending_rub: 0, available_rub: 0, paid_rub: 0, reserve_for_next_payout_rub: 0 })
const myPartnerPayouts = ref({ available_rub: 0, pending_rub: 0, commission_total_rub: 0, paid_total_rub: 0 })
const myPartnerStats = ref({ total_rub: 0, available_rub: 0, pending_rub: 0, paid_rub: 0, periods_rub: {}, by_month: [] })
const users = ref([])
const usersPreset = ref('all')
const showUserInfoModal = ref(false)
const selectedAdminUser = ref(null)
/** /api/admin/users/:id/subscription-profile — для карточки как в «Моя подписка» */
const selectedUserSubscriptionProfile = ref(null)
const selectedUserSubscriptionLoading = ref(false)
const chats = ref([])
const chatsOwnerFilter = ref(0)
const navBackStack = ref([])
const navForwardStack = ref([])
const navRestoring = ref(false)
const revenueStats = ref({ today_rub: 0, month_rub: 0, by_day: [], by_month: [] })
const revenuePeriod = ref('30d')
const referralsFunnel = ref([])
const actionLoadingId = ref(0)
const showPayoutHelp = ref(false)
const partnerHelpOpen = ref(false)
const partnerHelpTitle = ref('😈 Коротко')
const partnerHelpLines = ref([])
const payoutSearch = ref('')
const payoutsOnlyPaid = ref(false)
const showDateFilter = ref(false)
const dateFrom = ref('')
const dateTo = ref('')
const testPayLoading = ref(false)
const testTargetTelegramId = ref('')
const testSubscriptionPlans = [1, 3, 12, 24, 72]
const testTokenPacks = [40, 100, 250, 600, 1500]
const opsHealth = ref({ status: 'ok', diagnostics: [], activity_by_hour: [] })
const opsLoading = ref(false)
const opsActionLoading = ref('')
/** Подвкладки Guard Pulse: мониторинг / журнал серверных 5xx для владельца */
/** Метка сборки: если в Guard Pulse её нет — открыт старый фронт (нужен redeploy WebApp). */
const GUARD_PULSE_UI_MARKER = 'Панель v2 · апр.2026'
const opsInnerTab = ref('pulse')
/** Подробности Guard Pulse / журнал (ⓘ), чтобы не засорять экран. */
const guardPulseInfoOpen = ref(false)
const incidentFeed = ref([])
const incidentFeedLoading = ref(false)
const incidentSummary = ref(null)
const incidentSummaryLoading = ref(false)
const incidentSearchQuery = ref('')
/** Личная база URL (Premium / «моя» у полного админа); для админа ещё globalBadUrlSystemItems + globalBadUrlUserBases. */
const globalBadUrlItems = ref([])
const globalBadUrlSystemItems = ref([])
const globalBadUrlUserBases = ref([])
const globalBadUrlLoading = ref(false)
const newGlobalBadUrl = ref('')
const newGlobalBadUrlNote = ref('')
const newMyGlobalBadUrl = ref('')
const newMyGlobalBadUrlNote = ref('')
const showMyGlobalBadUrlInfo = ref(false)
const showGlobalBadUrlInfo = ref(false)
/** Переход из АнтиURL: открыть вкладку «Пользователи» и прокрутить к карточке. */
const usersScrollTargetTelegramId = ref(0)
const usersHighlightTelegramId = ref(0)
const insights = ref({ window_hours: 24, group_joins_count: 0, starts_count: 0, payments_count: 0, payments_sum_rub: 0, referral_shares_count: 0, referral_levels: [] })
const joinReportPresetOptions = [
  { id: 'day', label: 'Раз в день' },
  { id: '3d', label: 'Раз в 3 дня' },
  { id: 'week', label: 'Раз в неделю' },
  { id: 'month', label: 'Раз в месяц' },
]
const insightsLoading = ref(false)
const msgTemplates = ref([])
const msgTemplateOptions = ref({ events: [], targets: [] })
const msgTemplatesLoading = ref(false)
const msgTemplateSavingId = ref(0)
const broadcasts = ref([])
const bcLoading = ref(false)
const bcSaving = ref(false)
const bcUploading = ref(false)
const bcSending = ref(false)
const bcShowAllRecentModal = ref(false)
const bcQuickDraftModalOpen = ref(false)
/** Сохранённое на сервере название при открытии быстрого черновика — для кнопки ✓ */
const bcQuickTitleBaseline = ref('')
const bcQuickDraftBaseline = ref(null)
const bcOpeningQuickDraft = ref(false)
const bcQuickDraftInitializing = ref(false)
const bcSendTargetModalOpen = ref(false)
const bcSendTargetChannels = ref(false)
const bcSendTargetGroups = ref(false)
const bcSendTargetBots = ref(false)
const bcShowBotsPicker = ref(false)
const bcBotsSearch = ref('')
const bcBotRecipients = ref([
  { id: 1, title: 'Все активные пользователи бота' },
])
const bcSelectedBotRecipientIds = ref([])
const bcGroupsSearch = ref('')
const bcChannelsSearch = ref('')
const bcConfirmModalOpen = ref(false)
const bcConfirmLoading = ref(false)
const bcConfirmSending = ref(false)
const bcConfirmQuoteTokens = ref(0)
const bcConfirmRecipientLabel = ref('—')
const bcConfirmMessageLen = ref(0)
const bcConfirmButtonsCount = ref(0)
const bcConfirmHasMedia = ref(false)
const bcConfirmMode = ref('groups') // groups | users | mixed
const bcConfirmChatIds = ref([])
const bcSelectedId = ref(null)
const bcTitle = ref('')
const bcQuickTitleDirty = computed(
  () => String(bcTitle.value ?? '').trim() !== String(bcQuickTitleBaseline.value ?? '').trim(),
)
const bcBodyHtml = ref('')
const bcButtonRows = ref([[{ text: '', url: '', web_app_url: '', callback_data: '' }]])
/** Тип для следующей загрузки файла */
/** Тип медиа, сохранённый на сервере для выбранного черновика */
const bcMediaKindStored = ref('none')
const bcMediaOriginalName = ref('')
const bcBodyRef = ref(null)
const bcEmojiHostRef = ref(null)
const bcEmojiOpen = ref(false)
const bcShowMainHelp = ref(false)
/** '' | 'keyboard' | 'media' — модалки редактирования кнопок и файла из блока «Оформление» */
const bcAuxModal = ref('')
const bcShowFormatHelp = ref(false)
const bcShowAutopostHelp = ref(false)
const BC_DELEGATED_PREF_KEY = 'guard.delegated.broadcast.chat_id'
/** Открыть ADM → рассылка с предвыбранным каналом (из списка чатов / Protection). */
const BC_OPEN_CHANNEL_KEY = 'guard.broadcast.open_channel_id'
const bcShowGroupsPicker = ref(false)
const bcSelectedGroupIds = ref([])
/** Группы этого бота для выбора в рассылке/автопосте (из /api/admin/broadcast/groups). */
const bcBroadcastGroups = ref([])
const bcBroadcastChannels = ref([])
const bcSelectedChannelIds = ref([])
const bcShowChannelsPicker = ref(false)
const bcBroadcastCanScopeAll = ref(false)
const bcBroadcastGroupScope = ref('mine')
/** Список черновиков: mine — только свои (по умолчанию); all — явно для полного админа. */
const bcBroadcastDraftListScope = ref('mine')

const bcRecentBroadcasts = computed(() =>
  (broadcasts.value || [])
    .filter((b) => {
      const status = String(b?.status || '').toLowerCase()
      const hasRuns = Number(b?.recipient_total || 0) > 0 || Number(b?.recipient_ok || 0) > 0 || Number(b?.recipient_fail || 0) > 0
      return hasRuns || status === 'sent' || status === 'sending' || status === 'failed'
    })
    .sort((a, b) => {
      const ta = Date.parse(String(a?.sent_at || a?.created_at || 0)) || 0
      const tb = Date.parse(String(b?.sent_at || b?.created_at || 0)) || 0
      return tb - ta
    }),
)
const bcRecentBroadcastsPreview = computed(() => bcRecentBroadcasts.value.slice(0, 3))
const bcQuickButtonPreview = computed(() =>
  (bcButtonRows.value || [])
    .flatMap((row) => (Array.isArray(row) ? row : []))
    .map((btn) => ({
      text: String(btn?.text || '').trim(),
      url: String(btn?.url || btn?.web_app_url || '').trim(),
    }))
    .filter((btn) => btn.text),
)

const bcSendTargetSummary = computed(() => {
  const rows = []
  if (bcSendTargetChannels.value) rows.push(`Каналы: ${Number(bcSelectedChannelIds.value?.length || 0)}`)
  if (bcSendTargetGroups.value) rows.push(`Группы: ${Number(bcSelectedGroupIds.value?.length || 0)}`)
  if (bcSendTargetBots.value) rows.push(`Боты (личка): ${Number(bcSelectedBotRecipientIds.value?.length || 0)}`)
  return rows
})

function ruPlural(n, one, few, many) {
  const v = Math.abs(Number(n || 0))
  const d100 = v % 100
  if (d100 >= 11 && d100 <= 14) return many
  const d10 = v % 10
  if (d10 === 1) return one
  if (d10 >= 2 && d10 <= 4) return few
  return many
}

function bcConfirmSymbolsLabel(n) {
  const v = Math.max(0, Number(n || 0))
  return `~${v} ${ruPlural(v, 'символ', 'символа', 'символов')}`
}

function bcConfirmButtonsLabel(n) {
  const v = Math.max(0, Number(n || 0))
  if (!v) return 'Нет'
  return `${v} ${ruPlural(v, 'кнопка', 'кнопки', 'кнопок')}`
}

function clampPct(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return 0
  return Math.min(100, Math.max(0, Math.round(n)))
}

function fmtPctPartFromRatio(num, den) {
  const n = Number(num || 0)
  const d = Number(den || 0)
  if (!d || d <= 0) return null
  return clampPct((n / d) * 100)
}

function fmtBroadcastShortTime(iso) {
  if (!iso) return ''
  const d = new Date(String(iso))
  if (Number.isNaN(d.getTime())) return ''
  const now = new Date()
  const pad = (x) => String(x).padStart(2, '0')
  const sameDay =
    d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate()
  const timeStr = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  if (sameDay) return `Сегодня, ${timeStr}`
  return timeStr
}

function fmtIntSpace(n) {
  const v = Number(n || 0)
  if (!Number.isFinite(v)) return '0'
  try {
    return new Intl.NumberFormat('ru-RU').format(Math.trunc(v))
  } catch {
    return String(Math.trunc(v))
  }
}

function fmtPctTrim(p) {
  if (p == null) return '—'
  const n = Number(p)
  if (!Number.isFinite(n)) return '—'
  const s = n.toFixed(1).replace('.', ',')
  return `${s}%`
}

const bcSendProgressTotal = computed(() => {
  const row = bcSendLiveRow.value
  const rt = Number(row?.recipient_total || 0)
  if (Number.isFinite(rt) && rt > 0) return rt
  const kind = String(bcSendTargetKind.value || 'groups')
  let n = 0
  if (kind === 'users') n = Number(bcSelectedBotRecipientIds.value?.length || 0)
  else if (kind === 'groups') {
    n =
      Number(bcSelectedGroupIds.value?.length || 0) +
      Number(bcSelectedChannelIds.value?.length || 0)
  } else {
    n =
      Number(bcSelectedGroupIds.value?.length || 0) +
      Number(bcSelectedChannelIds.value?.length || 0) +
      Number(bcSelectedBotRecipientIds.value?.length || 0)
  }
  return Math.max(0, Math.trunc(n))
})

const bcSendProgressDone = computed(() => {
  const row = bcSendLiveRow.value
  const ok = Number(row?.recipient_ok || 0)
  const fail = Number(row?.recipient_fail || 0)
  const sum = ok + fail
  if (Number.isFinite(sum) && sum >= 0) return Math.max(0, Math.trunc(sum))
  return 0
})

const bcSendProgressPercent = computed(() => {
  const total = bcSendProgressTotal.value
  if (!total) return 0
  return clampPct((bcSendProgressDone.value / total) * 100)
})

/** Длина видимой дуги пропорциональна проценту (не перевёрнуто). */
const bcSendCircleDash = computed(() => {
  const p = bcSendProgressPercent.value
  const R = 52
  const C = 2 * Math.PI * R
  const filled = C * (p / 100)
  return `${filled.toFixed(2)} ${C.toFixed(2)}`
})

const bcSendStatsOverall = computed(() => bcSendResultSnapshot.value?.overall || null)
const bcSendStatsBots = computed(() => bcSendResultSnapshot.value?.bots || null)
const bcSendStatsGroups = computed(() => bcSendResultSnapshot.value?.groups || null)

const bcSendDeliveredOk = computed(() => {
  const o = bcSendStatsOverall.value
  const v = Number(o?.ok ?? o?.delivered ?? 0)
  return Number.isFinite(v) ? Math.max(0, Math.trunc(v)) : 0
})

const bcSendDeliveredTotal = computed(() => {
  const o = bcSendStatsOverall.value
  const v = Number(o?.total ?? o?.attempts ?? 0)
  return Number.isFinite(v) && v > 0 ? Math.trunc(v) : bcSendProgressTotal.value
})

const bcSendDeliveredPct = computed(() =>
  fmtPctPartFromRatio(bcSendDeliveredOk.value, bcSendDeliveredTotal.value),
)

/** «Клики»: успешные доставки в личку боту (users). Подпись уточняется в карточке UI. */
const bcSendClicks = computed(() => {
  const b = bcSendStatsBots.value
  const v = Number(b?.ok ?? 0)
  return Number.isFinite(v) ? Math.max(0, Math.trunc(v)) : 0
})

/** «Переходы»: успешные доставки в группы/каналы (чаты). */
const bcSendTransitions = computed(() => {
  const g = bcSendStatsGroups.value
  const v = Number(g?.ok ?? 0)
  return Number.isFinite(v) ? Math.max(0, Math.trunc(v)) : 0
})

const bcSendClicksPct = computed(() => fmtPctPartFromRatio(bcSendClicks.value, bcSendDeliveredOk.value))

const bcSendTransitionsPct = computed(() => fmtPctPartFromRatio(bcSendTransitions.value, bcSendDeliveredOk.value))

/**
 * CTR в карточке — «охват базы»: доставлено успешно относительно всех подключённых групп/каналов
 * и активных пользователей бота (как в /stats: connected_*).
 */
const bcSendCtrDen = computed(() => {
  const s = bcSendResultSnapshot.value
  const g = Number(s?.connected_groups_total || 0)
  const b = Number(s?.connected_bots_total || 0)
  const sum = (Number.isFinite(g) ? g : 0) + (Number.isFinite(b) ? b : 0)
  return Math.max(1, Math.trunc(sum))
})

const bcSendCtrPct = computed(() => fmtPctPartFromRatio(bcSendDeliveredOk.value, bcSendCtrDen.value))

const bcSendCompletedAtLabel = computed(() => {
  const row = bcSendLiveRow.value
  const iso = row?.finished_at || row?.sent_at || row?.updated_at || row?.created_at
  return fmtBroadcastShortTime(iso)
})

const bcFilteredGroups = computed(() => {
  const q = String(bcGroupsSearch.value || '').trim().toLowerCase()
  if (!q) return bcBroadcastGroups.value || []
  return (bcBroadcastGroups.value || []).filter((c) => String(c?.title || c?.username || '').toLowerCase().includes(q))
})

const bcFilteredChannels = computed(() => {
  const q = String(bcChannelsSearch.value || '').trim().toLowerCase()
  if (!q) return bcBroadcastChannels.value || []
  return (bcBroadcastChannels.value || []).filter((c) => String(c?.title || c?.username || '').toLowerCase().includes(q))
})

const bcFilteredBots = computed(() => {
  const q = String(bcBotsSearch.value || '').trim().toLowerCase()
  if (!q) return bcBotRecipients.value || []
  return (bcBotRecipients.value || []).filter((b) => String(b?.title || '').toLowerCase().includes(q))
})
const bcSelectedTargetsCount = computed(() =>
  Number((bcSelectedChannelIds.value || []).length || 0) + Number((bcSelectedGroupIds.value || []).length || 0),
)

function bcRecentWhenLabel(item) {
  const raw = String(item?.sent_at || item?.created_at || '').trim()
  if (!raw) return 'дата не указана'
  const d = new Date(raw)
  if (!Number.isFinite(d.getTime())) return 'дата не указана'
  return d.toLocaleString('ru-RU', {
    day: 'numeric',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function bcRecentStatusLabel(item) {
  const st = String(item?.status || '').toLowerCase()
  if (st === 'sent') return 'Отправлено'
  if (st === 'sending') return 'Отправляется'
  if (st === 'failed') return 'С ошибкой'
  if (st === 'draft') return 'Черновик'
  return 'Запуск'
}

async function openQuickBroadcastDraft() {
  if (bcOpeningQuickDraft.value) return
  bcOpeningQuickDraft.value = true
  try {
    const needsCreate = !bcSelectedId.value
    if (needsCreate) {
      bcQuickDraftInitializing.value = true
      bcEditorOpen.value = false
      bcQuickDraftModalOpen.value = true
      bcTitle.value = String(bcTitle.value || 'Новый черновик')
      bcBodyHtml.value = String(bcBodyHtml.value || '')
      await nextTick()
      if (bcBodyRef.value) bcBodyRef.value.innerHTML = bcBodyHtml.value || ''
    }
    if (!bcSelectedId.value) {
      await createBcDraft()
    }
    if (!bcSelectedId.value) return
    bcEditorOpen.value = false
    bcQuickDraftModalOpen.value = true
    bcQuickTitleBaseline.value = String(bcTitle.value || '')
    bcQuickDraftBaseline.value = null
    await nextTick()
    if (bcBodyRef.value) bcBodyRef.value.innerHTML = bcBodyHtml.value || ''
    bcSyncEditorHtml()
    bcQuickDraftBaseline.value = {
      title: String(bcTitle.value || '').trim(),
      body: String(bcNormalizeHtmlForTelegram(bcBodyHtml.value || '') || ''),
      keyboard: JSON.stringify(bcBuildKeyboardPayload() || []),
      mediaKind: String(bcMediaKindStored.value || 'none'),
      mediaName: String(bcMediaOriginalName.value || ''),
    }
    bcUpdateFormatState()
  } finally {
    bcQuickDraftInitializing.value = false
    bcOpeningQuickDraft.value = false
  }
}

async function openSendTargetModal() {
  bcSendTargetChannels.value = false
  bcSendTargetGroups.value = false
  bcSendTargetBots.value = false
  bcBroadcastGroupScope.value = 'mine'
  await Promise.all([loadBroadcastEligibleGroups(), loadBroadcastEligibleChannels()])
  bcSendTargetModalOpen.value = true
}

async function proceedSendTargetModal() {
  if (Number(bcSelectedTargetsCount.value || 0) <= 0) return
  await openBcConfirmModal()
}

function bcConfirmBuildPayload() {
  const channelIds = (bcSelectedChannelIds.value || []).map((x) => Number(x || 0)).filter((x) => x !== 0)
  const groupIds = (bcSelectedGroupIds.value || []).map((x) => Number(x || 0)).filter((x) => x !== 0)
  const mergedIds = [...new Set([...channelIds, ...groupIds].map((x) => Number(x || 0)).filter((x) => x !== 0))]
  const nChannels = mergedIds.filter((id) => bcBroadcastChannels.value.some((c) => bcNormalizeChatId(c) === id)).length
  const nGroups = mergedIds.filter((id) => bcBroadcastGroups.value.some((c) => bcNormalizeChatId(c) === id)).length
  if (mergedIds.length > 0) {
    if (!mergedIds.length) return null
    let label = ''
    if (nChannels > 0 && nGroups === 0) label = `${nChannels} ${ruPlural(nChannels, 'канал', 'канала', 'каналов')}`
    else if (nGroups > 0 && nChannels === 0) label = `${nGroups} ${ruPlural(nGroups, 'группа', 'группы', 'групп')}`
    else label = `${nChannels} ${ruPlural(nChannels, 'канал', 'канала', 'каналов')} · ${nGroups} ${ruPlural(nGroups, 'группа', 'группы', 'групп')}`
    return { mode: 'groups', ids: mergedIds, recipientLabel: label }
  }
  return null
}

async function openBcConfirmModal() {
  const payload = bcConfirmBuildPayload()
  if (!payload) {
    return
  }
  const bid = Number(bcSelectedId.value || 0)
  if (!bid) return
  bcConfirmLoading.value = true
  bcConfirmMode.value = payload.mode
  bcConfirmChatIds.value = [...payload.ids]
  bcConfirmRecipientLabel.value = payload.recipientLabel
  bcConfirmMessageLen.value = Number(bcCurrentLen() || 0)
  bcConfirmButtonsCount.value = (bcButtonRows.value || []).flatMap((r) => Array.isArray(r) ? r : []).filter((b) => String(b?.text || '').trim()).length
  bcConfirmHasMedia.value = (bcMediaHistory.value || []).length > 0
  bcConfirmQuoteTokens.value = 0
  try {
    const q = await fetch(() => api.adminBroadcastQuote(bid, payload.mode, payload.ids))
    const need = Number(q?.cost_tokens ?? 0)
    if (need > 0 && q?.can_afford === false) {
      alert(`Недостаточно AURUM: нужно ${need} ✨, доступно ${Number(q?.spendable_credits || 0)} ✨.`)
      return
    }
    bcConfirmQuoteTokens.value = need
    // Экран подтверждения — отдельный шаг поверх админки, без подложки "Куда отправить".
    bcSendTargetModalOpen.value = false
    bcConfirmModalOpen.value = true
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось рассчитать стоимость'))
  } finally {
    bcConfirmLoading.value = false
  }
}

async function submitBcConfirmedSend() {
  const bid = Number(bcSelectedId.value || 0)
  if (!bid) return
  bcConfirmSending.value = true
  try {
    await persistCurrentBroadcast()
    await fetch(() =>
      api.adminBroadcastSend(bid, bcConfirmMode.value, bcConfirmMode.value === 'groups' ? bcConfirmChatIds.value : [], {
        keepDraftAfter: true,
      }),
    )
    bcConfirmModalOpen.value = false
    bcSendTargetModalOpen.value = false
    bcShowGroupsPicker.value = false
    bcShowChannelsPicker.value = false
    bcShowBotsPicker.value = false
    upsertBroadcastInList({ id: bid, status: 'sending' })
    startBroadcastProgressPolling(bid, 'groups')
    bcSaveLocalSnapshot()
    try {
      meAdminProfile.value = await api.me()
    } catch {
      //
    }
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось отправить'))
  } finally {
    bcConfirmSending.value = false
  }
}

async function openQuickAutopost() {
  if (!bcSelectedId.value) {
    await createBcDraft()
  }
  bcAutopostingModalOpen.value = true
}

/** Полная серверная админка (все вкладки). */
const meAdminProfile = ref(null)
function applyAdminMeSubscription(next) {
  meAdminProfile.value = next
}
const showFullAdminShell = computed(() => {
  const m = meAdminProfile.value
  return !!(m && hasFullAdminRights(m))
})
/** Фактический базовый URL API в WebView (для подсказки при «мониторинг не загрузился»). */
const guardApiBaseEffective = computed(() => {
  if (typeof window === 'undefined') return ''
  const a = String(window.__GUARD_API_BASE_EFFECTIVE__ || window.__GUARD_API_BASE__ || '').trim()
  return a || ''
})
/** Premium без полных прав: обзор + рефералы + рассылка (как «синий» упрощённый ADM). */
const isPremiumCabinet = computed(() => {
  const m = meAdminProfile.value
  if (!m || hasFullAdminRights(m)) return false
  return !!m.is_premium
})
/** Free, делегированный менеджер: только рассылка/автопост по чужим чатам, без обзора Premium. */
const isDelegatedFreeBroadcastCabinet = computed(() => {
  const m = meAdminProfile.value
  if (!m || hasFullAdminRights(m)) return false
  if (!!m.is_premium) return false
  return !!m.has_managed_shared_chat
})
const delegatePayerSaving = ref(false)
const aurumTransferToDelegateTg = ref('')
const aurumTransferToDelegateAmt = ref('')
const aurumTransferLoading = ref(false)

async function saveDelegateBroadcastPayer(mode) {
  if (!meAdminProfile.value || isDelegatedFreeBroadcastCabinet.value) return
  delegatePayerSaving.value = true
  try {
    await fetch(() => api.meDelegateBroadcastPayerPatch(mode))
    meAdminProfile.value = { ...meAdminProfile.value, delegate_broadcast_payer: mode }
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось сохранить'))
  } finally {
    delegatePayerSaving.value = false
  }
}

async function submitAurumTransferToDelegate() {
  const tg = Number(String(aurumTransferToDelegateTg.value || '').trim())
  const amt = Number(String(aurumTransferToDelegateAmt.value || '').replace(',', '.'))
  if (!tg || tg <= 0 || !Number.isFinite(amt) || amt < 0.01) {
    alert('Укажите Telegram id менеджера и сумму AURUM (от 0.01)')
    return
  }
  aurumTransferLoading.value = true
  try {
    const r = await fetch(() => api.billingAurumTransferToDelegate(tg, amt))
    alert(`Переведено: ${Number(r?.transferred ?? amt)} ✨`)
    aurumTransferToDelegateAmt.value = ''
    meAdminProfile.value = await api.me()
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось перевести'))
  } finally {
    aurumTransferLoading.value = false
  }
}

/** Общие ограничения рассылки (только группы, без «в боты» как у полного админа). */
const isBroadcastShellLite = computed(
  () => isPremiumCabinet.value || isDelegatedFreeBroadcastCabinet.value,
)
/** Кампании автопоста и плашка-памятка: полный админ + Premium + делегированный кабинет рассылки. */
const showAutopostCampaignsUi = computed(
  () => showFullAdminShell.value || isBroadcastShellLite.value,
)
const plActivitySummary = ref(null)
const plActivityJournal = ref([])
const showPartnerEventsModal = ref(false)
const showPartnerSpendModal = ref(false)
const showPartnerGroupsModal = ref(false)
const partnerGroupsTab = ref('all')
const showPartnerJoinsModal = ref(false)
const ownerJoinReportPeriods = ref([])
const ownerJoinReportSaving = ref(false)
const showPartnerHourlyModal = ref(false)
const showPartnerHourlyChatPicker = ref(false)
const partnerHourlyPreset = ref('24h')
const partnerHourlyChatId = ref('all')
const partnerHourlyData = ref({
  slots: [],
  hours: [],
  totals: { events: 0, moderation: 0, joins: 0, spam_moderation: 0, spam_deleted: 0, messages_with_guard: 0 },
  chats: [],
  bar_scale_max: 1,
  bar_scale_note: '',
  segment_joins: { channel: 0, group: 0, linked_group: 0 },
  segment_spam: { channel: 0, group: 0, linked_group: 0 },
})
const partnerHourlyLoading = ref(false)
const partnerAudienceGenderData = ref({
  male: 0,
  female: 0,
  unknown: 0,
  male_pct: 35.4,
  female_pct: 64.6,
  known_total: 0,
  audience_total: 0,
  is_estimate: true,
})
const partnerAudienceGenderLastValid = ref({
  male: 0,
  female: 0,
  unknown: 0,
  male_pct: 35.4,
  female_pct: 64.6,
  known_total: 0,
  audience_total: 0,
  is_estimate: true,
})
const partnerHourlyUseCustomRange = ref(false)
const partnerHourlyRangeOpen = ref(false)
const partnerHourlyDateFrom = ref('')
const partnerHourlyDateTo = ref('')
const showPartnerSlotDetailModal = ref(false)
const partnerSlotDetailLoading = ref(false)
const partnerSlotDetailTitle = ref('')
const partnerSlotDetailData = ref({ joins: [], moderation: [] })
const showPartnerSegmentModal = ref(false)
const partnerOverlayOpen = computed(
  () =>
    showPartnerEventsModal.value ||
    showPartnerSpendModal.value ||
    showPartnerGroupsModal.value ||
    showPartnerJoinsModal.value ||
    showPartnerHourlyModal.value ||
    showPartnerHourlyChatPicker.value ||
    showPartnerSlotDetailModal.value ||
    showPartnerSegmentModal.value,
)
const partnerSegmentModalTab = ref('joins')
const partnerJournalDoneKeys = ref(new Set())
const OWNER_JOIN_REPORT_PRESETS = [
  { id: 'day', label: 'Раз в день' },
  { id: '3d', label: 'Раз в 3 дня' },
  { id: 'week', label: 'Раз в неделю' },
  { id: 'month', label: 'Раз в месяц' },
]
const PARTNER_HOURLY_PRESETS = [
  { id: '24h', label: '24ч', hours: 24 },
  { id: '7d', label: '7д', hours: 24 * 7 },
  { id: '30d', label: '30д', hours: 24 * 30 },
]

function partnerNormalizeAction(action) {
  const a = String(action || '').toLowerCase()
  if (a.includes('observe') || a.includes('замеч')) return 'observe'
  if (a.includes('ban')) return 'ban'
  if (a.includes('mute') || a.includes('restrict')) return 'mute'
  return 'delete'
}

function partnerActionLabelRu(action) {
  const key = partnerNormalizeAction(action)
  if (key === 'ban') return 'Блокировка'
  if (key === 'mute') return 'Ограничение'
  if (key === 'observe') return 'Замечено'
  return 'Удаление'
}

const PARTNER_SPAM_REASON_BASES = new Set([
  'stopword',
  'profanity',
  'jobs',
  'casino',
  'link',
  'mention',
  'media',
  'buttons',
])

function partnerIsSpamReason(reason) {
  const raw = String(reason || '').trim().toLowerCase()
  if (!raw) return false
  const base = raw.replace(/_newbie$/i, '')
  return PARTNER_SPAM_REASON_BASES.has(base)
}

const partnerSlotDetailModerationDisplay = computed(() => {
  const rows = partnerSlotDetailData.value?.moderation || []
  const t = String(partnerSlotDetailTitle.value || '')
  if (t.includes('Спам')) {
    return rows.filter((m) => partnerIsSpamReason(m.reason))
  }
  return rows
})

function partnerReasonRu(reason) {
  const raw = String(reason || '').trim().toLowerCase()
  if (!raw) return '—'
  const base = raw.replace(/_newbie$/i, '')
  const map = {
    link: 'Ссылки',
    media: 'Медиа',
    buttons: 'Кнопки',
    mention: 'Упоминания',
    stopword: 'Стоп-слова',
    profanity: 'Мат',
    jobs: 'Подработки',
    casino: 'Казино',
    silence: 'Тишина',
  }
  if (map[raw]) return map[raw]
  if (map[base]) return map[base]
  return raw.replace(/_/g, ' ')
}

async function loadPartnerLiteActivity() {
  const [s, j, jr] = await Promise.all([
    api.activitySummary(),
    api.activityJournal(null, 80),
    api.ownerJoinReportSettings().catch(() => ({ periods: [] })),
  ])
  plActivitySummary.value = s
  plActivityJournal.value = j?.items || []
  ownerJoinReportPeriods.value = Array.isArray(jr?.periods) ? jr.periods : []
}

function toggleOwnerJoinReportPreset(id) {
  const v = String(id || '').trim().toLowerCase()
  if (!['day', '3d', 'week', 'month'].includes(v)) return
  const cur = [...(ownerJoinReportPeriods.value || [])]
  const i = cur.indexOf(v)
  if (i >= 0) cur.splice(i, 1)
  else cur.push(v)
  ownerJoinReportPeriods.value = cur
}

async function saveOwnerJoinReportSettings() {
  ownerJoinReportSaving.value = true
  try {
    const r = await fetch(() => api.ownerSetJoinReportSettings(ownerJoinReportPeriods.value || []))
    ownerJoinReportPeriods.value = Array.isArray(r?.periods) ? r.periods : ownerJoinReportPeriods.value
    alert('Периодичность коротких отчётов сохранена')
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось сохранить периодичность отчётов'))
  } finally {
    ownerJoinReportSaving.value = false
  }
}

async function partnerQuickUnmute(ev) {
  const chatId = Number(ev?.chat_id || 0)
  const uid = Number(ev?.user_id || 0)
  if (!chatId || !uid) return
  if (!window.confirm(`Снять мут для ${partnerUserLabel(ev)}?`)) return
  try {
    await fetch(() => api.chatMemberUnmute(chatId, uid))
    partnerJournalDoneKeys.value.add(`mute:${chatId}:${uid}`)
    partnerJournalDoneKeys.value = new Set(partnerJournalDoneKeys.value)
    alert('Команда на размут отправлена')
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось размутить'))
  }
}

async function partnerQuickUnban(ev) {
  const chatId = Number(ev?.chat_id || 0)
  const uid = Number(ev?.user_id || 0)
  if (!chatId || !uid) return
  if (!window.confirm(`Разбанить ${partnerUserLabel(ev)}?`)) return
  try {
    await fetch(() => api.chatMemberUnban(chatId, uid))
    partnerJournalDoneKeys.value.add(`ban:${chatId}:${uid}`)
    partnerJournalDoneKeys.value = new Set(partnerJournalDoneKeys.value)
    alert('Команда на разбан отправлена')
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось разбанить'))
  }
}

function partnerQuickObserve(ev) {
  const uid = Number(ev?.user_id || 0)
  if (!uid) return
  alert(`Пользователь ${partnerUserLabel(ev)} отмечен как «замечено»`)
}

function _partnerDayBoundsIso(dateStr, endOfDay) {
  const s = String(dateStr || '').trim()
  if (!s) return null
  const d = new Date(`${s}T${endOfDay ? '23:59:59' : '00:00:00'}`)
  if (Number.isNaN(d.getTime())) return null
  return d.toISOString()
}

async function loadPartnerHourlyActivity() {
  partnerHourlyLoading.value = true
  try {
    const chatArg = partnerHourlyChatId.value === 'all' ? null : Number(partnerHourlyChatId.value || 0)
    let r
    if (
      partnerHourlyUseCustomRange.value
      && String(partnerHourlyDateFrom.value || '').trim()
      && String(partnerHourlyDateTo.value || '').trim()
    ) {
      const dFrom = new Date(`${String(partnerHourlyDateFrom.value).trim()}T00:00:00`)
      const dTo = new Date(`${String(partnerHourlyDateTo.value).trim()}T00:00:00`)
      if (!Number.isNaN(dFrom.getTime()) && !Number.isNaN(dTo.getTime()) && dFrom > dTo) {
        alert('Дата «с» не может быть позже «по»')
        partnerHourlyLoading.value = false
        return
      }
      const fromIso = _partnerDayBoundsIso(partnerHourlyDateFrom.value, false)
      const toIso = _partnerDayBoundsIso(partnerHourlyDateTo.value, true)
      if (fromIso && toIso) {
        r = await fetch(() => api.activityHours(chatArg, 24, fromIso, toIso))
      }
    }
    if (!r) {
      const pid = String(partnerHourlyPreset.value || '24h')
      const preset = PARTNER_HOURLY_PRESETS.find((x) => x.id === pid) || PARTNER_HOURLY_PRESETS[0]
      r = await fetch(() => api.activityHours(chatArg, preset.hours))
    }
    const g = await fetch(() => api.activityAudienceGender(chatArg)).catch(() => null)
    partnerHourlyData.value = r || partnerHourlyData.value
    if (g) {
      partnerAudienceGenderData.value = g
      const known = Number(g?.known_total || (Number(g?.male || 0) + Number(g?.female || 0)))
      if (known > 0) partnerAudienceGenderLastValid.value = { ...g }
    }
  } catch {
    partnerHourlyData.value = {
      slots: [],
      hours: [],
      totals: { events: 0, moderation: 0, joins: 0, spam_moderation: 0, spam_deleted: 0, messages_with_guard: 0 },
      chats: [],
      bar_scale_max: 1,
      bar_scale_note: '',
      segment_joins: { channel: 0, group: 0, linked_group: 0 },
      segment_spam: { channel: 0, group: 0, linked_group: 0 },
    }
    partnerAudienceGenderData.value = {
      male: 0,
      female: 0,
      unknown: 0,
      male_pct: 35.4,
      female_pct: 64.6,
      known_total: 0,
      audience_total: 0,
      is_estimate: true,
    }
  } finally {
    partnerHourlyLoading.value = false
  }
}

function partnerPresetDateHint(presetId) {
  const id = String(presetId || '')
  const now = new Date()
  const fmt = (d) =>
    d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })
  if (id === '24h') return fmt(now)
  if (id === '7d') {
    const a = new Date(now.getTime() - 7 * 86400000)
    return `${fmt(a)} — ${fmt(now)}`
  }
  if (id === '30d') {
    const a = new Date(now.getTime() - 30 * 86400000)
    return `${fmt(a)} — ${fmt(now)}`
  }
  return ''
}

const PARTNER_HELP = {
  chatList: {
    shortTitle: 'Список чатов в партнёрке',
    lines: [
      'Группы, каналы и «обсуждение канала» я помечаю разными значками — сразу видно, где люди пишут вживую, а где только лента постов.',
      'Если у канала есть привязанная группа обсуждения, «живую» статистику беру оттуда.',
    ],
  },
  dayCounter: {
    shortTitle: 'Счётчик за сутки',
    lines: [
      'На главной — короткая сводка за последние 24 часа; в окне можно развернуть период и разрез по чатам.',
      'Считаю те же события, что в журнале: удаления, муты, баны и остальное по правилам чата.',
    ],
  },
  journal: {
    shortTitle: 'Журнал за сутки',
    lines: [
      'Здесь последние действия защиты: что снял с эфира, кого приглушил или выгнал.',
      'Кнопки у строки появляются только там, где они реально нужны — не предлагаю разбан без бана.',
    ],
  },
  spend: {
    shortTitle: 'Списания ⚡',
    lines: [
      'Рассылка и автопост едят токены: сначала AURUM ✨, потом подписочные ⚡ — так честнее для кошелька.',
      'Сколько снял за конкретный прогон, смотри в деталях; всё по тарифу, без сюрпризов.',
    ],
  },
  discussion: {
    shortTitle: 'Группа и канал',
    lines: [
      '«Группа в канале» в Telegram — это обсуждение: туда люди пишут комментарии.',
      'Графики по каналу, если есть обсуждение, собираю из привязанного чата; в одном только постах админов мало данных для картинки.',
    ],
  },
  events: {
    shortTitle: 'График событий',
    lines: [
      'События — это срабатывания Guard в чате плюс новые участники, которых я зафиксировал.',
      'Насколько «шумно» в слоте, зависит от выбранного отрезка времени.',
    ],
  },
  customRange: {
    shortTitle: 'Свой диапазон дат',
    lines: [
      'Ты выбираешь календарные сутки в часовом поясе браузера; я перевожу границы в UTC и дергаю API.',
      'Если цифры «пляшут» на стыке дней — глянь время и часовой пояс на устройстве.',
    ],
  },
  barScale: {
    shortTitle: 'Полоски на графике',
    lines: [
      'Высота столбика — доля от максимума в одном слоте на выбранном интервале. Это масштаб графика, не лимит чата и не «потолок».',
      'Два пика рядом значат: в эти минуты было жарко относительно остального окна.',
    ],
  },
  tgstatPack: {
    shortTitle: 'Что это за статистика',
    lines: [
      'Карточки сверху показывают срез по выбранному чату/каналу из подключённых у пользователя.',
      'Для части метрик беру прямые цифры из Guard (участники, события, модерация, спам), а остальное отображается как справочный формат блока.',
      'Пол внизу — оценка по first_name вступивших пользователей в подключенных чатах (может быть неполной).',
    ],
  },
}

function partnerHelpBind(key, variant = 'corner') {
  const h = PARTNER_HELP[key]
  const tt = h?.shortTitle || 'Справка'
  const base =
    'z-30 inline-flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-full border-2 border-slate-400/80 bg-slate-950 text-[11px] font-bold text-slate-100 shadow-md hover:bg-slate-800 active:scale-95'
  const pos =
    variant === 'corner'
      ? 'absolute right-2 top-2'
      : variant === 'trailing'
        ? 'absolute right-1 top-1'
        : ''
  return {
    type: 'button',
    title: tt,
    'aria-label': `Справка: ${tt}`,
    class: [base, pos].filter(Boolean).join(' '),
  }
}

function partnerShowHelp(key) {
  const h = PARTNER_HELP[key]
  if (!h) return
  partnerHelpTitle.value = `😈 ${h.shortTitle}`
  partnerHelpLines.value = h.lines
  partnerHelpOpen.value = true
}

const partnerHourlySlots = computed(() => partnerHourlyData.value?.slots || [])
const partnerChatsGrouped = computed(() => {
  const arr = partnerHourlyData.value?.chats || []
  return {
    groups: arr.filter((c) => (c.ui_segment || 'group') === 'group'),
    channels: arr.filter((c) => c.ui_segment === 'channel'),
    linked: arr.filter((c) => c.ui_segment === 'linked_group'),
  }
})
const partnerGroupsModalRows = computed(() => {
  const tabId = String(partnerGroupsTab.value || 'all')
  const channels = partnerChatsGrouped.value?.channels || []
  const groups = partnerChatsGrouped.value?.groups || []
  const linked = partnerChatsGrouped.value?.linked || []
  return {
    showChannels: tabId === 'all' || tabId === 'channels',
    showGroups: tabId === 'all' || tabId === 'groups',
    channels,
    groups,
    linked,
  }
})
const partnerOwnChatsOrdered = computed(() => {
  const channels = [...(partnerChatsGrouped.value?.channels || [])]
    .sort((a, b) => String(a?.title || '').localeCompare(String(b?.title || ''), 'ru'))
  const groups = [...(partnerChatsGrouped.value?.groups || [])]
    .sort((a, b) => String(a?.title || '').localeCompare(String(b?.title || ''), 'ru'))
  return { channels, groups }
})

const partnerHourlyBarMax = computed(() => Math.max(1, Number(partnerHourlyData.value?.bar_scale_max || 1)))
const PARTNER_CHART_W = 140
const PARTNER_CHART_H = 42
function sparklinePath(values, width = 140, height = 42) {
  const arr = (values || []).map((x) => Number(x || 0))
  if (!arr.length) return ''
  const maxV = Math.max(1, ...arr)
  const step = arr.length > 1 ? width / (arr.length - 1) : width
  return arr
    .map((v, i) => {
      const x = i * step
      const y = height - (Math.max(0, v) / maxV) * height
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(2)} ${y.toFixed(2)}`
    })
    .join(' ')
}
const partnerChartLabels = computed(() => {
  const slots = partnerHourlySlots.value || []
  return slots.map((s) => {
    const d = new Date(String(s?.slot_start || ''))
    if (!Number.isFinite(d.getTime())) return '—'
    return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })
  })
})
const partnerChartSeries = computed(() => {
  const slots = partnerHourlySlots.value || []
  return {
    joins: slots.map((s) => Number(s?.joins || 0)),
    moderation: slots.map((s) => Number(s?.moderation || 0)),
    spam: slots.map((s) => Number(s?.spam_moderation || 0)),
    events: slots.map((s) => Number(s?.events || 0)),
  }
})
const partnerChartHover = ref(null)
function partnerChartPoint(values, idx) {
  const arr = (values || []).map((x) => Number(x || 0))
  if (!arr.length) return { x: 0, y: PARTNER_CHART_H, value: 0 }
  const maxV = Math.max(1, ...arr)
  const i = Math.max(0, Math.min(arr.length - 1, Number(idx || 0)))
  const x = arr.length > 1 ? (i / (arr.length - 1)) * PARTNER_CHART_W : PARTNER_CHART_W / 2
  const y = PARTNER_CHART_H - (Math.max(0, arr[i]) / maxV) * PARTNER_CHART_H
  return { x, y, value: arr[i] }
}
function partnerChartHoverMove(evt, key, values, labels = []) {
  const arr = (values || []).map((x) => Number(x || 0))
  if (!arr.length) {
    partnerChartHover.value = null
    return
  }
  const el = evt?.currentTarget
  const rect = el?.getBoundingClientRect?.()
  if (!rect || rect.width <= 0 || rect.height <= 0) return
  const relX = Math.max(0, Math.min(rect.width, Number(evt.clientX || 0) - rect.left))
  const idx = arr.length > 1 ? Math.round((relX / rect.width) * (arr.length - 1)) : 0
  const p = partnerChartPoint(arr, idx)
  const xPx = (p.x / PARTNER_CHART_W) * rect.width
  const yPx = (p.y / PARTNER_CHART_H) * rect.height
  partnerChartHover.value = {
    key,
    idx,
    x: p.x,
    y: p.y,
    value: p.value,
    label: String(labels?.[idx] || `#${idx + 1}`),
    xPx,
    yPx,
  }
}
function partnerChartHoverLeave(key) {
  if (!partnerChartHover.value) return
  if (partnerChartHover.value.key === key) partnerChartHover.value = null
}
const partnerMiniCharts = computed(() => {
  const joins = partnerChartSeries.value.joins
  const moderation = partnerChartSeries.value.moderation
  const spam = partnerChartSeries.value.spam
  const events = partnerChartSeries.value.events
  return {
    joinsPath: sparklinePath(joins, PARTNER_CHART_W, PARTNER_CHART_H),
    moderationPath: sparklinePath(moderation, PARTNER_CHART_W, PARTNER_CHART_H),
    spamPath: sparklinePath(spam, PARTNER_CHART_W, PARTNER_CHART_H),
    eventsPath: sparklinePath(events, PARTNER_CHART_W, PARTNER_CHART_H),
  }
})
const partnerTgstatLikeMetrics = computed(() => ({
  subscribers: { total: '247 840', today: '+2', week: '-736', month: '+190' },
  citation: { total: '655', channels: '783', mentions: '4 406', reposts: '58' },
  avgReach: { total: '20 668', err: '8.3%', err24: '4.1%' },
  adReach: { total: '10 166', h12: '7.4k', h24: '10.2k', h48: '12.3k' },
  age: { period: '6 лет 2 месяца', createdAt: '12.02.2020', addedAt: '12.02.2020' },
  posts: { total: '8 438', yesterday: '7', week: '38', month: '161' },
  err: { readAll: '9%', read24h: '5%' },
  er: { value: '1.18%', forwards: '50', comments: '—', reactions: '114' },
}))
const partnerSelectedChatMeta = computed(() => {
  const cid = String(partnerHourlyChatId.value || 'all')
  if (cid === 'all') return null
  return (partnerHourlyData.value?.chats || []).find((x) => String(x?.id || '') === cid) || null
})
function partnerFmtInt(n) {
  const v = Number(n || 0)
  if (!Number.isFinite(v)) return '0'
  return Math.round(v).toLocaleString('ru-RU')
}
const partnerAudienceGender = computed(() => {
  const cur = partnerAudienceGenderData.value || {}
  const curKnown = Number(cur?.known_total || (Number(cur?.male || 0) + Number(cur?.female || 0)))
  const src = curKnown > 0 ? cur : (partnerAudienceGenderLastValid.value || cur)
  const malePctRaw = Number(src?.male_pct || 0)
  const femalePctRaw = Number(src?.female_pct || 0)
  const malePct = Math.max(0, Math.min(100, malePctRaw || 0))
  const femalePct = Math.max(0, Math.min(100, femalePctRaw || 0))
  const chats = partnerHourlyData.value?.chats || []
  let audience = Number(src?.audience_total || 0)
  if (partnerSelectedChatMeta.value) {
    audience = Math.max(audience, Number(partnerSelectedChatMeta.value?.members_count || 0))
  } else {
    audience = Math.max(audience, chats.reduce((acc, c) => acc + Number(c?.members_count || 0), 0))
  }
  const maleCount = Number(src?.male || 0)
  const femaleCount = Number(src?.female || 0)
  const unknownCount = Number(src?.unknown || 0)
  const knownTotal = Number(src?.known_total || maleCount + femaleCount)
  return {
    malePct,
    femalePct,
    audience,
    maleCount,
    femaleCount,
    unknownCount,
    knownTotal,
    isEstimate: !!src?.is_estimate || curKnown <= 0,
  }
})
const partnerReachWindows = computed(() => {
  const slots = partnerHourlyData.value?.slots || []
  if (!slots.length) return { h12: 0, h24: 0, h48: 0 }
  const nowTs = Date.now()
  let h12 = 0
  let h24 = 0
  let h48 = 0
  for (const s of slots) {
    const ts = new Date(String(s?.slot_start || '')).getTime()
    if (!Number.isFinite(ts)) continue
    const val = Number(s?.events || 0)
    const dt = nowTs - ts
    if (dt <= 12 * 3600 * 1000) h12 += val
    if (dt <= 24 * 3600 * 1000) h24 += val
    if (dt <= 48 * 3600 * 1000) h48 += val
  }
  return { h12, h24, h48 }
})
const partnerTgstatDisplay = computed(() => {
  const base = partnerTgstatLikeMetrics.value
  const sel = partnerSelectedChatMeta.value
  const totals = partnerHourlyData.value?.totals || {}
  const chats = partnerHourlyData.value?.chats || []
  const membersAll = chats.reduce((acc, c) => acc + Number(c?.members_count || 0), 0)
  const membersCur = Number(sel?.members_count || 0)
  const subscribersTotal = partnerFmtInt(sel ? membersCur : membersAll)
  const joinsTotal = Number(sel?.joins ?? totals?.joins ?? 0)
  const moderationTotal = Number(sel?.moderation ?? totals?.moderation ?? 0)
  const spamTotal = Number(sel?.spam_moderation ?? totals?.spam_moderation ?? 0)
  const connectedAt = String(sel?.connected_at || '').trim()
  const lastActivityAt = String(sel?.last_activity_at || '').trim()
  const msgChecked = Number(sel?.messages_checked || 0)
  const msgDeleted = Number(sel?.messages_deleted || 0)
  const usersBanned = Number(sel?.users_banned || 0)
  const ageFrom = connectedAt ? new Date(connectedAt.replace('Z', '+00:00')) : null
  let agePeriod = '—'
  if (ageFrom && Number.isFinite(ageFrom.getTime())) {
    const days = Math.max(0, Math.floor((Date.now() - ageFrom.getTime()) / 86400000))
    const years = Math.floor(days / 365)
    const months = Math.floor((days % 365) / 30)
    agePeriod = years > 0 ? `${years} лет ${months} месяца` : `${months} месяца`
  }
  const activityPct = membersAll > 0 ? Math.min(100, ((totals?.events || 0) / Math.max(1, membersAll) * 100)) : 0
  return {
    ...base,
    subscribers: {
      ...base.subscribers,
      total: subscribersTotal || base.subscribers.total,
      today: `${joinsTotal >= 0 ? '+' : ''}${partnerFmtInt(joinsTotal)}`,
      week: `${moderationTotal > 0 ? '-' : ''}${partnerFmtInt(moderationTotal)}`,
      month: `+${partnerFmtInt(Math.max(joinsTotal, moderationTotal, spamTotal))}`,
    },
    citation: {
      ...base.citation,
      total: partnerFmtInt(spamTotal || moderationTotal || joinsTotal),
      channels: partnerFmtInt((chats || []).filter((c) => c?.ui_segment === 'channel').length),
      mentions: partnerFmtInt(totals?.events || 0),
      reposts: partnerFmtInt(totals?.spam_deleted || 0),
    },
    avgReach: {
      ...base.avgReach,
      total: partnerFmtInt(Math.max(1, Math.round((totals?.events || 0) / Math.max(1, chats.length)))),
      err: `${Number(base.avgReach.err || '8.3').toString()}%`,
      err24: `${Number(base.avgReach.err24 || '4.1').toString()}%`,
    },
    adReach: {
      ...base.adReach,
      total: partnerFmtInt(Math.max(1, totals?.messages_with_guard || 0)),
      h12: partnerFmtInt(partnerReachWindows.value.h12),
      h24: partnerFmtInt(partnerReachWindows.value.h24),
      h48: partnerFmtInt(partnerReachWindows.value.h48),
    },
    age: {
      ...base.age,
      period: agePeriod,
      createdAt: connectedAt ? String(connectedAt).slice(0, 10).split('-').reverse().join('.') : '—',
      addedAt: lastActivityAt ? String(lastActivityAt).slice(0, 10).split('-').reverse().join('.') : '—',
    },
    posts: {
      ...base.posts,
      total: partnerFmtInt(msgChecked || totals?.messages_with_guard || 0),
      yesterday: partnerFmtInt(partnerReachWindows.value.h24),
      week: partnerFmtInt(partnerReachWindows.value.h48),
      month: partnerFmtInt(totals?.events || 0),
    },
    err: {
      readAll: `${activityPct.toFixed(1)}%`,
      read24h: `${Math.min(100, activityPct * 0.65).toFixed(1)}%`,
    },
    er: {
      value: `${activityPct.toFixed(2)}%`,
      forwards: partnerFmtInt(msgDeleted),
      comments: '—',
      reactions: partnerFmtInt(usersBanned),
    },
  }
})

async function openPartnerSlotDetail(fromTs, toTs, title) {
  if (!fromTs || !toTs) return
  partnerSlotDetailTitle.value = title || 'Подробности'
  showPartnerSlotDetailModal.value = true
  partnerSlotDetailLoading.value = true
  partnerSlotDetailData.value = { joins: [], moderation: [] }
  try {
    const chatArg = partnerHourlyChatId.value === 'all' ? null : Number(partnerHourlyChatId.value || 0)
    const r = await fetch(() => api.activitySlotDetail(fromTs, toTs, chatArg))
    partnerSlotDetailData.value = r || partnerSlotDetailData.value
  } catch {
    partnerSlotDetailData.value = { joins: [], moderation: [] }
  } finally {
    partnerSlotDetailLoading.value = false
  }
}

function applyPartnerCustomRange() {
  partnerHourlyUseCustomRange.value = true
  partnerHourlyRangeOpen.value = false
  loadPartnerHourlyActivity()
}

function selectPartnerPreset(pid) {
  partnerHourlyPreset.value = pid
  partnerHourlyUseCustomRange.value = false
  partnerHourlyRangeOpen.value = false
  loadPartnerHourlyActivity()
}

function togglePartnerHourlyRange() {
  partnerHourlyRangeOpen.value = !partnerHourlyRangeOpen.value
}

const partnerActivityPeriodLine = computed(() => {
  const a = partnerHourlyData.value?.period_from
  const b = partnerHourlyData.value?.period_to
  if (!a || !b) return ''
  try {
    const da = new Date(String(a).replace('Z', '+00:00'))
    const db = new Date(String(b).replace('Z', '+00:00'))
    const f = (x) =>
      x.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
    return `${f(da)} — ${f(db)}`
  } catch {
    return ''
  }
})

function partnerUserHref(row) {
  const id = Number(row?.user_id ?? row?.telegram_id ?? 0)
  const un = String(
    row?.username || row?.user_username || row?.target_username || row?.owner_username || '',
  ).trim().replace(/^@+/, '')
  if (un) return `https://t.me/${un}`
  if (id) return `https://t.me/user?id=${id}`
  return ''
}

function partnerUserLabel(row) {
  const id = Number(row?.user_id ?? row?.telegram_id ?? 0)
  const un = String(
    row?.username || row?.user_username || row?.target_username || row?.owner_username || '',
  ).trim().replace(/^@+/, '')
  if (un) return `@${un}`
  if (id) return `id ${id}`
  return '—'
}

function openPartnerHourlyModal() {
  showPartnerHourlyModal.value = true
  loadPartnerHourlyActivity()
}

function openPartnerGroupsModal() {
  partnerGroupsTab.value = 'all'
  showPartnerGroupsModal.value = true
  loadPartnerHourlyActivity()
}

function openPartnerJoinsModal() {
  openPartnerHourlyModal()
}

function selectPartnerChatFromList(chatId) {
  partnerHourlyChatId.value = String(chatId || 'all')
  showPartnerHourlyChatPicker.value = false
  loadPartnerHourlyActivity()
}

const partnerJoinsOverviewHint = computed(() => partnerPresetDateHint(partnerHourlyPreset.value || '24h'))

function openPartnerEventsModal() {
  showPartnerEventsModal.value = true
}

function partnerJournalActionHidden(ev, kind) {
  const chatId = Number(ev?.chat_id || 0)
  const uid = Number(ev?.user_id || 0)
  return partnerJournalDoneKeys.value.has(`${kind}:${chatId}:${uid}`)
}

const partnerEvents24h = computed(() => (plActivityJournal.value || []).slice(0, 120))

async function loadReferralLite() {
  const [info, people] = await Promise.all([api.referral(), api.referralPeople()])
  referralInfo.value = info || null
  referralsTop.value = (people?.full_list || []).filter((x) => !!x?.is_paid)
}

async function loadMyPartnerStatsLite() {
  try {
    const r = await api.adminMyPartnerStats()
    myPartnerStats.value = r || myPartnerStats.value
  } catch {
    //
  }
}
const bcShowPreview = ref(false)
const bcPreviewItem = ref(null)
/** Превью медиа в модалке «Посмотреть»: blob/object URLs */
const bcPreviewMediaThumbs = ref([])
/** Переименование черновика в списке слева */
const bcDraftRenameId = ref(null)
const bcDraftRenameValue = ref('')
const bcSavingTitleId = ref(null)
const bcEditModalOpen = ref(false)
const bcEditTitle = ref('')
const bcEditBodyHtml = ref('')
const bcEditBodyRef = ref(null)
const bcLinkModalOpen = ref(false)
const bcLinkUrl = ref('https://')
const bcLinkRange = ref(null)
const bcEmojiPickerReady = ref(false)
const bcEditorOpen = ref(false)
const bcSavedTick = ref(false)
const bcFormatState = ref({ bold: false, italic: false, underline: false, strike: false, spoiler: false, link: false })
const bcSavedRange = ref(null)
const bcActiveSpoilerText = ref('')
const bcActiveLinkUrl = ref('')
const bcShowSpoilerInfo = ref(false)
const bcShowLinkInfo = ref(false)
const bcMediaHistory = ref([])
/** Превью первого визуального медиа в карточке черновика (id → { previewUrl, kind }) */
const bcDraftThumbById = shallowRef({})
/** Полноэкранный просмотр медиа из редактора / модалки файлов */
const bcMediaViewerOpen = ref(false)
const bcMediaViewerItem = ref(null)
const bcHistory = ref([])
const bcHistoryIndex = ref(-1)
const bcStatsModalOpen = ref(false)
const bcStatsSelectedId = ref(0)
const bcStatsLoading = ref(false)
const bcStatsTab = ref('bots')
const bcStatsBatchId = ref('')
const bcStatsFrom = ref('')
const bcStatsTo = ref('')
const bcStatsPreset = ref('')
const bcLastSendTargetByPost = ref({})
const bcStatsPollTimer = ref(null)
const bcStatsHistoryModalOpen = ref(false)
const bcStatsReloadTimer = ref(null)
const bcSendModalOpen = ref(false)
const bcSendModalState = ref('sending') // sending | done | failed
const bcSendModalText = ref('')
const bcSendModalBroadcastId = ref(0)
const bcSendPollTimer = ref(null)
const bcSendAutoCloseTimer = ref(null)
/** Последняя строка /admin/broadcasts/:id во время отправки */
const bcSendLiveRow = ref(null)
/** groups | users | all — как запускали sendBc / submitBcConfirmedSend */
const bcSendTargetKind = ref('groups')
const bcSendResultLoading = ref(false)
/** Снимок метрик после завершения (из /stats) */
const bcSendResultSnapshot = ref(null)
/** Минимум времени на экране «Отправка…» перед переходом к результату (мс). */
const BC_SEND_MIN_VISIBLE_MS = 3000
/** Время открытия экрана отправки — для BC_SEND_MIN_VISIBLE_MS */
const bcSendSendingStartedAt = ref(0)
/** Белый знак Telegram внутри круга (локальный svg в public/) */
const bcTelegramPlaneIconUrl = `${import.meta.env.BASE_URL}broadcast/telegram-plane-white.svg`

const adminBcBg = `${import.meta.env.BASE_URL}admin-bg-dark-final.png`
/** Верхняя отсечка AURUM за один запуск/слот на бэкенде (broadcast_send_plan.BROADCAST_MAX_TOKENS). */
const BC_BROADCAST_MAX_TOKENS = 2500
const bcAutopostingModalOpen = ref(false)
/** stopped | running | paused — с сервера (поле autopost у черновика) */
const bcAutopostRunState = ref('stopped')
/** Настройки расписания автопостинга */
const bcAutopostingForm = ref({
  scheduleMode: 'every_day',
  /** Пн=0 … Вс=6 — используется при scheduleMode === 'weekdays' */
  weekdays: [0, 1, 2, 3, 4],
  postsPerDay: 1,
  /** IANA, например Europe/Moscow — как в браузере/телефоне при сохранении */
  timezone: typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Moscow' : 'Europe/Moscow',
  windowStart: '10:00',
  windowEnd: '21:00',
  spreadInWindow: true,
  /** Пустой = во все активные группы бота; иначе только перечисленные chat_id (<0). */
  group_chat_ids: [],
  /** Каналы (chat_kind=channel), те же отрицательные id */
  channel_chat_ids: [],
  /** Все черновики в ротации автопоста */
  use_all_broadcasts: false,
  /** Явный список id постов (когда use_all_broadcasts = false) */
  broadcast_ids: [],
  /** groups | users — куда ведёт автопостинг */
  autopost_target: 'groups',
  /** true = в автопост не уходят каналы (выбор каналов в пресете сохраняется) */
  autopost_channels_disabled: false,
})

const bcAutopostDetailOpen = ref(false)
const bcAutopostDetailLoading = ref(false)
const bcAutopostDetailDays = ref(7)
const bcAutopostDetailData = ref(null)
/** Оценка POST /quote для подсказки стоимости автопоста (тот же target=groups, что в фоне). */
const bcAutopostQuoteInfo = ref(null)

/** Независимые кампании автопоста (отдельная сущность от черновика). */
const bcAutopostCampaigns = ref([])
/** Редактор модалки: черновик слева или кампания */
const bcAutopostEditMode = ref('campaign')
const bcAutopostCampaignId = ref(null)
/** Для оценки ⚡ при редактировании кампании */
const bcAutopostCampaignAnchorBid = ref(null)
const bcAutopostCampaignUserSeq = ref(null)
/** Источник данных для модалки «недавние» */
const bcAutopostDetailSource = ref('broadcast')

const BC_WEEKDAY_OPTS = [
  { v: 0, label: 'Пн' },
  { v: 1, label: 'Вт' },
  { v: 2, label: 'Ср' },
  { v: 3, label: 'Чт' },
  { v: 4, label: 'Пт' },
  { v: 5, label: 'Сб' },
  { v: 6, label: 'Вс' },
]

function applyAutopostFromServerItem(item) {
  const ap = item?.autopost
  if (!ap || typeof ap !== 'object') {
    bcAutopostRunState.value = 'stopped'
    bcAutopostingForm.value = {
      scheduleMode: 'every_day',
      weekdays: [0, 1, 2, 3, 4],
      postsPerDay: 1,
      timezone:
        typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Moscow' : 'Europe/Moscow',
      windowStart: '10:00',
      windowEnd: '21:00',
      spreadInWindow: true,
      group_chat_ids: [],
      channel_chat_ids: [],
      use_all_broadcasts: false,
      broadcast_ids: [],
      autopost_target: 'groups',
      autopost_channels_disabled: false,
    }
    return
  }
  const st = ap.runState === 'running' || ap.runState === 'paused' ? ap.runState : 'stopped'
  bcAutopostRunState.value = st
  const gRaw = ap.group_chat_ids
  const gIds = Array.isArray(gRaw) ? [...new Set(gRaw.map((x) => Number(x)).filter((x) => x < 0))].sort((a, b) => a - b) : []
  const chRaw = ap.channel_chat_ids
  const chIds = Array.isArray(chRaw) ? [...new Set(chRaw.map((x) => Number(x)).filter((x) => x < 0))].sort((a, b) => a - b) : []
  const useAllPosts = !!ap.use_all_broadcasts
  const bRaw = ap.broadcast_ids
  const bIds = Array.isArray(bRaw) ? [...new Set(bRaw.map((x) => Number(x)).filter((x) => x > 0))].sort((a, b) => a - b) : []
  bcAutopostingForm.value = {
    scheduleMode: ap.scheduleMode === 'weekdays' ? 'weekdays' : 'every_day',
    weekdays: Array.isArray(ap.weekdays) && ap.weekdays.length ? [...ap.weekdays.map(Number)] : [0, 1, 2, 3, 4],
    postsPerDay: Math.min(288, Math.max(1, Number(ap.postsPerDay) || 1)),
    timezone:
      String(ap.timezone || '').trim() ||
      (typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone : '') ||
      'Europe/Moscow',
    windowStart: ap.windowStart || '10:00',
    windowEnd: ap.windowEnd || '21:00',
    spreadInWindow: ap.spreadInWindow !== false,
    group_chat_ids: gIds,
    channel_chat_ids: chIds,
    use_all_broadcasts: useAllPosts,
    broadcast_ids: useAllPosts ? [] : bIds,
    autopost_target:
      isBroadcastShellLite.value ? 'groups' : ap.autopost_target === 'users' ? 'users' : 'groups',
    autopost_channels_disabled: !!ap.autopost_channels_disabled,
  }
}

function bcAutopostBuildPayload() {
  const f = bcAutopostingForm.value
  const posts = Math.min(288, Math.max(1, Number(f.postsPerDay) || 1))
  let wd = [...new Set((f.weekdays || []).map(Number))].filter((d) => d >= 0 && d <= 6).sort((a, b) => a - b)
  if (f.scheduleMode === 'weekdays' && !wd.length) wd = [0, 1, 2, 3, 4]
  const rs = bcAutopostRunState.value === 'running' || bcAutopostRunState.value === 'paused' ? bcAutopostRunState.value : 'stopped'
  const g = [...new Set((f.group_chat_ids || []).map((x) => Number(x)).filter((x) => x < 0))].sort((a, b) => a - b)
  const ch = [...new Set((f.channel_chat_ids || []).map((x) => Number(x)).filter((x) => x < 0))].sort((a, b) => a - b)
  const useAllB = f.use_all_broadcasts === true
  const br = useAllB
    ? []
    : [...new Set((f.broadcast_ids || []).map((x) => Number(x)).filter((x) => x > 0))].sort((a, b) => a - b)
  const tz =
    String(f.timezone || '').trim() ||
    (typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone : '') ||
    'Europe/Moscow'
  return {
    runState: rs,
    scheduleMode: f.scheduleMode === 'weekdays' ? 'weekdays' : 'every_day',
    weekdays: f.scheduleMode === 'every_day' ? [0, 1, 2, 3, 4, 5, 6] : wd,
    postsPerDay: posts,
    timezone: tz.slice(0, 80),
    windowStart: f.windowStart || '10:00',
    windowEnd: f.windowEnd || '21:00',
    spreadInWindow: f.spreadInWindow !== false,
    autopost_target: isBroadcastShellLite.value ? 'groups' : f.autopost_target === 'users' ? 'users' : 'groups',
    group_chat_ids: g,
    channel_chat_ids: ch,
    autopost_channels_disabled: !!f.autopost_channels_disabled,
    use_all_broadcasts: useAllB,
    broadcast_ids: br,
  }
}

async function loadBroadcastEligibleGroups() {
  try {
    const sc = bcBroadcastGroupScope.value === 'all' ? 'all' : 'mine'
    const r = await fetch(() => api.adminBroadcastGroups(sc))
    const items = r?.items || []
    const myTg = Number(meAdminProfile.value?.telegram_id || 0)
    const onlyForeign =
      cabinetMode.value === 'delegated' || isDelegatedFreeBroadcastCabinet.value
    bcBroadcastGroups.value = onlyForeign
      ? items.filter((x) => Number(x?.owner_telegram_id || 0) !== myTg)
      : items
    tryApplyDelegatedPreferredGroup()
    if (isDelegatedFreeBroadcastCabinet.value) {
      applyDelegatedFreeBroadcastGroupLock()
    }
    bcBroadcastCanScopeAll.value = !!r?.can_scope_all
  } catch {
    bcBroadcastGroups.value = []
  }
}

/** Free + делегирование: только чужие группы из списка; выбор фиксируется (после localStorage-предвыбора). */
function applyDelegatedFreeBroadcastGroupLock() {
  const ids = (bcBroadcastGroups.value || [])
    .map((c) => bcNormalizeChatId(c))
    .filter((x) => Number.isFinite(x) && x !== 0)
  if (!ids.length) return
  const allowed = new Set(ids)
  let chosen = (bcSelectedGroupIds.value || []).map(Number).filter((x) => allowed.has(x))
  if (!chosen.length) {
    chosen = [...ids]
  }
  bcSelectedGroupIds.value = [...chosen]
  bcAutopostingForm.value = {
    ...bcAutopostingForm.value,
    group_chat_ids: [...chosen],
    autopost_target: 'groups',
  }
}

function tryApplyDelegatedPreferredGroup() {
  let pref = 0
  try {
    pref = Number(localStorage.getItem(BC_DELEGATED_PREF_KEY) || 0)
  } catch {
    pref = 0
  }
  if (!pref || !Array.isArray(bcBroadcastGroups.value) || !bcBroadcastGroups.value.length) return
  const allowed = new Set(bcBroadcastGroups.value.map((x) => Number(x?.chat_id || x?.id || 0)))
  if (!allowed.has(pref)) return
  if (!bcSelectedGroupIds.value.includes(pref)) {
    bcSelectedGroupIds.value = [pref]
  }
  bcAutopostingForm.value = {
    ...bcAutopostingForm.value,
    group_chat_ids: [pref],
  }
  try {
    localStorage.removeItem(BC_DELEGATED_PREF_KEY)
  } catch {
    //
  }
}

function tryApplyOpenChannelPref() {
  let pref = 0
  try {
    pref = Number(localStorage.getItem(BC_OPEN_CHANNEL_KEY) || 0)
  } catch {
    pref = 0
  }
  if (!pref || !Array.isArray(bcBroadcastChannels.value) || !bcBroadcastChannels.value.length) return
  const allowed = new Set(bcBroadcastChannels.value.map((x) => bcNormalizeChatId(x)))
  if (!allowed.has(pref)) return
  if (!bcSelectedChannelIds.value.includes(pref)) {
    bcSelectedChannelIds.value = [pref]
  }
  try {
    localStorage.removeItem(BC_OPEN_CHANNEL_KEY)
  } catch {
    //
  }
}

async function loadBroadcastEligibleChannels() {
  try {
    const sc = bcBroadcastGroupScope.value === 'all' ? 'all' : 'mine'
    const r = await fetch(() => api.adminBroadcastChannels(sc))
    const items = r?.items || []
    const myTg = Number(meAdminProfile.value?.telegram_id || 0)
    const onlyForeignCh =
      cabinetMode.value === 'delegated' || isDelegatedFreeBroadcastCabinet.value
    bcBroadcastChannels.value = onlyForeignCh
      ? items.filter((x) => Number(x?.owner_telegram_id || 0) !== myTg)
      : items
  } catch {
    bcBroadcastChannels.value = []
  }
}

async function loadBcAutopostDetailStats() {
  const id =
    bcAutopostDetailSource.value === 'campaign'
      ? Number(bcAutopostCampaignId.value || 0)
      : Number(bcSelectedId.value || 0)
  if (!id) {
    bcAutopostDetailData.value = null
    return
  }
  bcAutopostDetailLoading.value = true
  try {
    if (bcAutopostDetailSource.value === 'campaign') {
      bcAutopostDetailData.value = await fetch(() =>
        api.adminAutopostCampaignAutopostStats(id, Number(bcAutopostDetailDays.value || 7) || 7),
      )
    } else {
      bcAutopostDetailData.value = await fetch(() =>
        api.adminBroadcastAutopostStats(id, Number(bcAutopostDetailDays.value || 7) || 7),
      )
    }
  } catch {
    bcAutopostDetailData.value = null
  } finally {
    bcAutopostDetailLoading.value = false
  }
}

async function openBcAutopostDetailStatsModal() {
  bcAutopostDetailSource.value = bcAutopostEditMode.value === 'campaign' ? 'campaign' : 'broadcast'
  bcAutopostDetailOpen.value = true
  await loadBcAutopostDetailStats()
}

async function onBcBroadcastGroupScopeChange() {
  await loadBroadcastEligibleGroups()
  await loadBroadcastEligibleChannels()
  const allowed = new Set(bcBroadcastGroups.value.map((c) => bcNormalizeChatId(c)))
  const allowedCh = new Set(bcBroadcastChannels.value.map((c) => bcNormalizeChatId(c)))
  bcSelectedGroupIds.value = bcSelectedGroupIds.value.filter((id) => allowed.has(Number(id)))
  bcSelectedChannelIds.value = bcSelectedChannelIds.value.filter((id) => allowedCh.has(Number(id)))
  const gf = bcAutopostingForm.value.group_chat_ids || []
  if (gf.length) {
    bcAutopostingForm.value = {
      ...bcAutopostingForm.value,
      group_chat_ids: gf.filter((id) => allowed.has(Number(id))),
    }
  }
  const cf = bcAutopostingForm.value.channel_chat_ids || []
  if (cf.length) {
    bcAutopostingForm.value = {
      ...bcAutopostingForm.value,
      channel_chat_ids: cf.filter((id) => allowedCh.has(Number(id))),
    }
  }
}

async function saveBcAutopostingModal() {
  const payload = bcAutopostBuildPayload()
  if (bcAutopostEditMode.value === 'campaign') {
    const cid = Number(bcAutopostCampaignId.value || 0)
    if (!cid) return
    try {
      await fetch(() => api.adminAutopostCampaignPatch(cid, { autopost: payload }))
      await loadAutopostCampaigns()
      bcAutopostingModalOpen.value = false
    } catch (e) {
      window.alert(String(e?.body?.detail || e?.message || 'Не удалось сохранить расписание'))
    }
    return
  }
  if (!bcSelectedId.value) return
  const id = bcSelectedId.value
  try {
    const r = await fetch(() => api.adminBroadcastPatch(id, { autopost: payload }))
    upsertBroadcastInList(r)
    applyAutopostFromServerItem(r)
    bcAutopostingModalOpen.value = false
  } catch (e) {
    window.alert(String(e?.body?.detail || e?.message || 'Не удалось сохранить расписание'))
  }
}

async function bcAutopostMergeSave(patch) {
  const next = { ...bcAutopostBuildPayload(), ...patch }
  if (bcAutopostEditMode.value === 'campaign') {
    const cid = Number(bcAutopostCampaignId.value || 0)
    if (!cid) return
    try {
      await fetch(() => api.adminAutopostCampaignPatch(cid, { autopost: next }))
      await loadAutopostCampaigns()
    } catch (e) {
      window.alert(String(e?.body?.detail || e?.message || 'Не удалось сохранить'))
    }
    return
  }
  const id = bcSelectedId.value
  if (!id) return
  try {
    const r = await fetch(() => api.adminBroadcastPatch(id, { autopost: next }))
    upsertBroadcastInList(r)
    applyAutopostFromServerItem(r)
  } catch (e) {
    window.alert(String(e?.body?.detail || e?.message || 'Не удалось сохранить'))
  }
}

async function refreshBcAutopostCostHint() {
  bcAutopostQuoteInfo.value = null
  const ids = (bcAutopostingForm.value.broadcast_ids || []).map(Number).filter((x) => x > 0)
  let bid = ids[0] || Number(bcSelectedId.value || 0)
  if (bcAutopostEditMode.value === 'campaign') {
    bid = Number(bcAutopostCampaignAnchorBid.value || 0) || ids[0] || 0
  }
  if (!bid) return
  const gPart = [...(bcAutopostingForm.value.group_chat_ids || [])]
  const chPart = bcAutopostingForm.value.autopost_channels_disabled ? [] : [...(bcAutopostingForm.value.channel_chat_ids || [])]
  const gids = [...gPart, ...chPart]
  try {
    bcAutopostQuoteInfo.value = await fetch(() => api.adminBroadcastQuote(bid, 'groups', gids))
  } catch {
    bcAutopostQuoteInfo.value = null
  }
}

async function bcAutopostStartOrResume() {
  await refreshBcAutopostCostHint()
  const q = bcAutopostQuoteInfo.value
  let msg =
    'Автопостинг: за каждый слот списывается столько же AURUM ✨, сколько за одну ручную отправку «В группы» / «В каналы» с тем же списком чатов (1 ✨ на каждый выбранный чат за слот). При нехватке AURUM слот пропускается. Продолжить?'
  if (q?.broadcast_charge_applies && Number(q.cost_tokens || 0) > 0) {
    msg = `Ориентир: ${Number(q.cost_tokens)} ✨ за один слот (${Number(q.n_groups || 0)} чатов в списке). ` + msg
    if (q.can_afford === false) {
      msg += ' Сейчас AURUM не хватает — слоты будут пропускаться, пока не пополните баланс в главном приложении → «Токены» (нужна подписка).'
    }
  }
  if (!window.confirm(msg)) return
  await bcAutopostMergeSave({ runState: 'running' })
}

async function bcAutopostStart() {
  await bcAutopostStartOrResume()
}

function bcAutopostPause() {
  bcAutopostMergeSave({ runState: 'paused' })
}

async function bcAutopostResume() {
  await bcAutopostStartOrResume()
}

function bcAutopostStop() {
  bcAutopostMergeSave({ runState: 'stopped' })
}

function bcCampaignRunState(camp) {
  const ap = camp?.autopost
  if (!ap || typeof ap !== 'object') return 'stopped'
  return ap.runState === 'running' || ap.runState === 'paused' ? ap.runState : 'stopped'
}

async function openBcAutopostCampaignModal(camp) {
  const id = Number(camp?.id || 0)
  if (!id) return
  bcAutopostEditMode.value = 'campaign'
  bcAutopostCampaignId.value = id
  bcAutopostCampaignUserSeq.value = camp?.user_seq != null && camp?.user_seq !== '' ? Number(camp.user_seq) : null
  bcAutopostCampaignAnchorBid.value = Number(camp?.anchor_broadcast_id || 0) || null
  applyAutopostFromServerItem({ autopost: camp?.autopost })
  bcBroadcastGroupScope.value = 'mine'
  await loadBroadcastEligibleGroups()
  await loadBroadcastEligibleChannels()
  const saved = [...(bcAutopostingForm.value.group_chat_ids || [])]
  const have = new Set(bcBroadcastGroups.value.map((c) => bcNormalizeChatId(c)))
  if (saved.some((gid) => !have.has(Number(gid))) && bcBroadcastCanScopeAll.value) {
    bcBroadcastGroupScope.value = 'all'
    await loadBroadcastEligibleGroups()
    await loadBroadcastEligibleChannels()
  }
  if (!bcAutopostingForm.value.use_all_broadcasts && !(bcAutopostingForm.value.broadcast_ids || []).length) {
    const cid = Number(bcAutopostCampaignAnchorBid.value || 0)
    if (cid > 0) {
      bcAutopostingForm.value = { ...bcAutopostingForm.value, broadcast_ids: [cid] }
    }
  }
  if (!String(bcAutopostingForm.value.timezone || '').trim() && typeof Intl !== 'undefined') {
    bcAutopostingForm.value = {
      ...bcAutopostingForm.value,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Moscow',
    }
  }
  await refreshBcAutopostCostHint()
  bcAutopostingModalOpen.value = true
}

async function createBcAutopostCampaign() {
  if (!bcSelectedId.value) {
    window.alert('Выберите шаблон слева — он станет якорем ротации для новой кампании.')
    return
  }
  try {
    await fetch(() => api.adminAutopostCampaignCreate({ anchor_broadcast_id: Number(bcSelectedId.value) }))
    await loadAutopostCampaigns()
  } catch (e) {
    window.alert(String(e?.body?.detail || e?.message || 'Не удалось создать кампанию'))
  }
}

async function onBcCampaignTitleBlur(camp, ev) {
  const id = Number(camp?.id || 0)
  if (!id) return
  const raw = String(ev?.target?.value ?? '').trim().slice(0, 255)
  const prev = String(camp?.title || '').trim()
  if (!raw || raw === prev) {
    if (ev?.target) ev.target.value = prev
    return
  }
  try {
    await fetch(() => api.adminAutopostCampaignPatch(id, { title: raw }))
    await loadAutopostCampaigns()
  } catch (e) {
    if (ev?.target) ev.target.value = prev
    window.alert(String(e?.body?.detail || e?.message || 'Не удалось сохранить название'))
  }
}

async function deleteBcAutopostCampaign(camp) {
  const id = Number(camp?.id || 0)
  if (!id) return
  if (!window.confirm('Удалить кампанию автопоста? Расписание будет удалено без восстановления.')) return
  try {
    await fetch(() => api.adminAutopostCampaignDelete(id))
    await loadAutopostCampaigns()
  } catch (e) {
    window.alert(String(e?.body?.detail || e?.message || 'Не удалось удалить'))
  }
}

async function bcCampaignPatchRunState(camp, runState) {
  const id = Number(camp?.id || 0)
  if (!id) return
  try {
    await fetch(() => api.adminAutopostCampaignPatch(id, { autopost: { runState } }))
    await loadAutopostCampaigns()
  } catch (e) {
    window.alert(String(e?.body?.detail || e?.message || 'Не удалось сохранить'))
  }
}

async function bcCampaignStartOrResume(camp) {
  const anchorBid = Number(camp?.anchor_broadcast_id || 0)
  const ap = camp?.autopost && typeof camp.autopost === 'object' ? { ...camp.autopost } : {}
  const gPart = [...(ap.group_chat_ids || [])]
  const chPart = ap.autopost_channels_disabled ? [] : [...(ap.channel_chat_ids || [])]
  const gids = [...gPart, ...chPart]
  let q = null
  if (anchorBid > 0) {
    try {
      q = await fetch(() => api.adminBroadcastQuote(anchorBid, 'groups', gids))
    } catch {
      q = null
    }
  }
  let msg =
    'Автопостинг (кампания): за каждый слот — столько же AURUM ✨, сколько за одну ручную отправку с тем же списком чатов. Продолжить?'
  if (q?.broadcast_charge_applies && Number(q.cost_tokens || 0) > 0) {
    msg = `Ориентир: ${Number(q.cost_tokens)} ✨ за один слот (${Number(q.n_groups || 0)} чатов). ` + msg
    if (q.can_afford === false) {
      msg += ' Сейчас AURUM не хватает — слоты будут пропускаться, пока не пополните баланс в главном приложении → «Токены» (нужна подписка).'
    }
  }
  if (!window.confirm(msg)) return
  await bcCampaignPatchRunState(camp, 'running')
}

function bcCampaignPause(camp) {
  bcCampaignPatchRunState(camp, 'paused')
}

async function bcCampaignResume(camp) {
  await bcCampaignStartOrResume(camp)
}

function bcCampaignStop(camp) {
  bcCampaignPatchRunState(camp, 'stopped')
}

function bcToggleWeekday(d) {
  const set = new Set(bcAutopostingForm.value.weekdays || [])
  if (set.has(d)) set.delete(d)
  else set.add(d)
  bcAutopostingForm.value.weekdays = [...set].sort((a, b) => a - b)
}
const bcStatsData = ref({
  bots: { ok: 0, fail: 0, total: 0 },
  groups: { ok: 0, fail: 0, total: 0 },
  overall: { ok: 0, fail: 0, total: 0 },
  per_groups: [],
  batches: [],
  errors: [],
  connected_groups_total: 0,
  connected_bots_total: 0,
})

const bcStatsBatchesFiltered = computed(() => Array.isArray(bcStatsData.value?.batches) ? bcStatsData.value.batches : [])
const bcStatsHistoryFiltered = computed(() => {
  const items = Array.isArray(bcStatsData.value?.batches) ? bcStatsData.value.batches : []
  const fromMs = bcStatsFrom.value ? new Date(bcStatsFrom.value).getTime() : 0
  const toMs = bcStatsTo.value ? new Date(bcStatsTo.value).getTime() : 0
  return items.filter((b) => {
    const st = new Date(String(b?.started_at || '')).getTime()
    if (!Number.isFinite(st)) return false
    if (fromMs && st < fromMs) return false
    if (toMs && st > toMs) return false
    return true
  })
})
const bcStatsHistoryPreview = computed(() => bcStatsHistoryFiltered.value.slice(0, 3))

const BC_PARSE_MODE = 'HTML'

function bcMediaKindLabel(kind) {
  const k = String(kind || 'none').toLowerCase()
  const map = {
    none: 'нет',
    photo: 'фото',
    video: 'видео',
    animation: 'GIF / анимация',
    document: 'файл / документ',
  }
  return map[k] || k
}

function bcMediaIcon(kind) {
  const k = String(kind || 'none').toLowerCase()
  if (k === 'photo') return '🖼'
  if (k === 'video') return '🎬'
  if (k === 'animation') return '🎞'
  if (k === 'document') return '📄'
  return '—'
}

function bcNormalizeChatId(c) {
  return Number(c?.chat_id || c?.id || 0)
}

function fmtDateTime(v) {
  const s = String(v || '').trim()
  if (!s) return '—'
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return s
  return d.toLocaleString('ru-RU', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function fmtUserSeenAt(v) {
  return fmtDateTime(v)
}

function userOnlineState(lastSeenAt) {
  const raw = String(lastSeenAt || '').trim()
  if (!raw) return { online: false, label: 'оффлайн' }
  const ts = Date.parse(raw)
  if (!Number.isFinite(ts)) return { online: false, label: 'оффлайн' }
  const freshMs = 2 * 60 * 1000
  const online = Date.now() - ts <= freshMs
  return { online, label: online ? 'онлайн' : 'оффлайн' }
}

function fmtBcTokens(v) {
  const n = Number(v || 0)
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}

function fmtBatchLabel(b) {
  const started = fmtDateTime(b?.started_at)
  const ended = fmtDateTime(b?.ended_at)
  const total = Number(b?.total || 0)
  const ok = Number(b?.ok || 0)
  const fail = Number(b?.fail || 0)
  if (started === ended || ended === '—') return `${started} · всего ${total} · ок ${ok} · ошибки ${fail}`
  return `${started} → ${ended} · всего ${total} · ок ${ok} · ошибки ${fail}`
}

function nowLocalInputValue() {
  const d = new Date()
  const yyyy = String(d.getFullYear())
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}`
}

function toLocalInputValue(d) {
  const yyyy = String(d.getFullYear())
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}`
}

function minusMinutesLocalInputValue(minutes = 1) {
  const d = new Date(Date.now() - Math.max(0, Number(minutes || 0)) * 60 * 1000)
  const yyyy = String(d.getFullYear())
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}`
}

function bcStatusLabel(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'draft') return 'Черновик'
  if (s === 'sending') return 'Отправляется'
  if (s === 'sent') return 'Отправлено'
  if (s === 'failed') return 'Ошибка'
  return String(status || '—')
}

function bcTargetLabel(target) {
  const t = String(target || '').toLowerCase()
  if (t === 'groups') return 'группы'
  if (t === 'all') return 'боты и группы'
  return 'боты'
}

function applyStatsPreset(kind) {
  const now = new Date()
  const toIso = toLocalInputValue(now)
  let from = new Date(now)
  if (kind === 'today') {
    from.setHours(0, 0, 0, 0)
  } else if (kind === '24h') {
    from = new Date(now.getTime() - 24 * 60 * 60 * 1000)
  } else if (kind === '7d') {
    from = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
  } else if (kind === '30d') {
    from = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
  }
  bcStatsPreset.value = String(kind || '')
  bcStatsFrom.value = toLocalInputValue(from)
  bcStatsTo.value = toIso
  scheduleLoadBroadcastStats(120)
}

function scheduleLoadBroadcastStats(delayMs = 250) {
  if (bcStatsReloadTimer.value) {
    clearTimeout(bcStatsReloadTimer.value)
    bcStatsReloadTimer.value = null
  }
  bcStatsReloadTimer.value = setTimeout(() => {
    bcStatsReloadTimer.value = null
    if (!bcStatsModalOpen.value) return
    loadBroadcastStats()
  }, Math.max(0, Number(delayMs || 0)))
}

function bcStorageTg() {
  const t = Number(meAdminProfile.value?.telegram_id || 0)
  return t > 0 ? String(t) : '0'
}

function bcDraftCacheKey(id) {
  return `admin.broadcast.draft.${bcStorageTg()}.${Number(id || 0)}`
}

function bcLastDraftIdKey() {
  return `admin.broadcast.last_draft_id.${bcStorageTg()}`
}

function bcLastTargetsKey() {
  return `admin.broadcast.last_targets_by_post.${bcStorageTg()}`
}

function bcSaveLocalSnapshot() {
  const id = Number(bcSelectedId.value || 0)
  if (!id) return
  try {
    const payload = {
      title: String(bcTitle.value || ''),
      body_html: String(bcBodyHtml.value || ''),
      keyboard_rows: bcButtonRows.value || [[bcEmptyButton()]],
      media_kind: String(bcMediaKindStored.value || 'none'),
      media_name: String(bcMediaOriginalName.value || ''),
      ts: Date.now(),
    }
    localStorage.setItem(bcDraftCacheKey(id), JSON.stringify(payload))
    localStorage.setItem(bcLastDraftIdKey(), String(id))
  } catch {
    // ignore storage issues
  }
}

function bcLoadLastTargetsMap() {
  try {
    const raw = localStorage.getItem(bcLastTargetsKey())
    if (!raw) return {}
    const obj = JSON.parse(raw)
    return obj && typeof obj === 'object' ? obj : {}
  } catch {
    return {}
  }
}

function bcSaveLastTargetsMap() {
  try {
    localStorage.setItem(bcLastTargetsKey(), JSON.stringify(bcLastSendTargetByPost.value || {}))
  } catch {
    // ignore storage issues
  }
}

function bcLoadLocalSnapshot(id) {
  try {
    const raw = localStorage.getItem(bcDraftCacheKey(id))
    if (!raw) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

const bcStatsCurrentItem = computed(() => {
  const id = Number(bcStatsSelectedId.value || 0)
  if (!id) return null
  return (broadcasts.value || []).find((b) => Number(b?.id || 0) === id) || null
})

function openBroadcastStats() {
  if (!broadcasts.value.length) {
    alert('Нет постов для статистики')
    return
  }
  if (!Number(bcStatsSelectedId.value || 0)) {
    bcStatsSelectedId.value = Number(bcSelectedId.value || broadcasts.value[0]?.id || 0)
  }
  const sid = Number(bcStatsSelectedId.value || 0)
  const remembered = String(bcLastSendTargetByPost.value?.[sid] || '').toLowerCase()
  bcStatsTab.value = isBroadcastShellLite.value ? 'groups' : remembered === 'groups' ? 'groups' : 'bots'
  bcStatsFrom.value = ''
  bcStatsTo.value = nowLocalInputValue()
  bcStatsModalOpen.value = true
  loadBroadcastStats()
}

function openStatsHistoryModal() {
  if (!bcStatsTo.value) bcStatsTo.value = nowLocalInputValue()
  bcStatsHistoryModalOpen.value = true
}

function statsHistoryTitle() {
  if (isBroadcastShellLite.value) return 'История отправок в группы'
  return bcStatsTab.value === 'groups' ? 'История отправок в группы' : 'История отправок в боты'
}

function applyHistoryItem(item) {
  const st = String(item?.started_at || '').trim()
  const en = String(item?.ended_at || item?.started_at || '').trim()
  if (st) bcStatsFrom.value = st.slice(0, 16)
  if (en) bcStatsTo.value = en.slice(0, 16)
  bcStatsHistoryModalOpen.value = false
  loadBroadcastStats()
}

async function loadBroadcastStats() {
  const id = Number(bcStatsSelectedId.value || 0)
  if (!id) return
  bcStatsLoading.value = true
  try {
    const r = await fetch(() =>
      api.adminBroadcastStats(
        id,
        '',
        bcStatsFrom.value || '',
        bcStatsTo.value || '',
        isBroadcastShellLite.value ? 'groups' : bcStatsTab.value || 'bots',
      ),
    )
    bcStatsData.value = {
      bots: r?.bots || { ok: 0, fail: 0, total: 0 },
      groups: r?.groups || { ok: 0, fail: 0, total: 0 },
      overall: r?.overall || { ok: 0, fail: 0, total: 0 },
      per_groups: Array.isArray(r?.per_groups) ? r.per_groups : [],
      batches: Array.isArray(r?.batches) ? r.batches : [],
      errors: Array.isArray(r?.errors) ? r.errors : [],
      connected_groups_total: Number(r?.connected_groups_total || 0),
      connected_bots_total: Number(r?.connected_bots_total || 0),
    }
    bcStatsBatchId.value = String(r?.active_batch_id || '')
  } catch {
    bcStatsData.value = {
      bots: { ok: 0, fail: 0, total: 0 },
      groups: { ok: 0, fail: 0, total: 0 },
      overall: { ok: 0, fail: 0, total: 0 },
      per_groups: [],
      batches: [],
      errors: [],
      connected_groups_total: 0,
      connected_bots_total: 0,
    }
  } finally {
    bcStatsLoading.value = false
  }
}

function stopBroadcastProgressPolling() {
  if (bcSendPollTimer.value) {
    clearInterval(bcSendPollTimer.value)
    bcSendPollTimer.value = null
  }
  if (bcSendAutoCloseTimer.value) {
    clearTimeout(bcSendAutoCloseTimer.value)
    bcSendAutoCloseTimer.value = null
  }
}

function resetBcSendUiExtras() {
  bcSendLiveRow.value = null
  bcSendResultSnapshot.value = null
  bcSendResultLoading.value = false
}

async function loadBcSendResultStats(broadcastId) {
  const bid = Number(broadcastId || 0)
  if (!bid) return
  bcSendResultLoading.value = true
  try {
    const r = await fetchSilent(() =>
      api.adminBroadcastStats(
        bid,
        '',
        minusMinutesLocalInputValue(30),
        nowLocalInputValue(),
        isBroadcastShellLite.value ? 'groups' : String(bcSendTargetKind.value || '') === 'groups' ? 'groups' : 'bots',
      ),
    )
    bcSendResultSnapshot.value = {
      bots: r?.bots || { ok: 0, fail: 0, total: 0 },
      groups: r?.groups || { ok: 0, fail: 0, total: 0 },
      overall: r?.overall || { ok: 0, fail: 0, total: 0 },
      per_groups: Array.isArray(r?.per_groups) ? r.per_groups : [],
      batches: Array.isArray(r?.batches) ? r.batches : [],
      errors: Array.isArray(r?.errors) ? r.errors : [],
      connected_groups_total: Number(r?.connected_groups_total || 0),
      connected_bots_total: Number(r?.connected_bots_total || 0),
    }
  } catch {
    bcSendResultSnapshot.value = {
      bots: { ok: 0, fail: 0, total: 0 },
      groups: { ok: 0, fail: 0, total: 0 },
      overall: { ok: 0, fail: 0, total: 0 },
      per_groups: [],
      batches: [],
      errors: [],
      connected_groups_total: 0,
      connected_bots_total: 0,
    }
  } finally {
    bcSendResultLoading.value = false
  }
}

function closeBcSendModal() {
  stopBroadcastProgressPolling()
  bcSendModalOpen.value = false
  bcSendModalState.value = 'sending'
  bcSendModalText.value = ''
  bcSendModalBroadcastId.value = 0
  resetBcSendUiExtras()
}

function bcSendGoToBroadcasts() {
  tab.value = 'broadcasts'
  closeBcSendModal()
}

function bcSendOpenStatsFromModal() {
  const bid = Number(bcSendModalBroadcastId.value || 0)
  if (!bid) return
  bcStatsSelectedId.value = bid
  const remembered = String(bcLastSendTargetByPost.value?.[bid] || '').toLowerCase()
  bcStatsTab.value = isBroadcastShellLite.value ? 'groups' : remembered === 'groups' ? 'groups' : 'bots'
  bcStatsFrom.value = minusMinutesLocalInputValue(30)
  bcStatsTo.value = nowLocalInputValue()
  bcStatsModalOpen.value = true
  loadBroadcastStats()
  closeBcSendModal()
}

/** Отмена в UI не останавливает серверную отправку — только закрывает экран прогресса. */
function bcSendCancelWatching() {
  stopBroadcastProgressPolling()
  bcSendModalOpen.value = false
  bcSendModalState.value = 'sending'
  bcSendModalText.value = ''
  bcSendModalBroadcastId.value = 0
  resetBcSendUiExtras()
}

/** Закрыть шаги «куда / подтверждение / пикеры» перед полноэкранной отправкой — иначе они перекрывают оверлей (у них z-index выше). */
function bcDismissBroadcastSendPrefaceOverlays() {
  bcConfirmModalOpen.value = false
  bcConfirmSending.value = false
  bcConfirmLoading.value = false
  bcSendTargetModalOpen.value = false
  bcShowGroupsPicker.value = false
  bcShowChannelsPicker.value = false
  bcShowBotsPicker.value = false
}

async function startBroadcastProgressPolling(id, target) {
  stopBroadcastProgressPolling()
  resetBcSendUiExtras()
  bcDismissBroadcastSendPrefaceOverlays()
  await nextTick()
  bcSendModalOpen.value = true
  bcSendSendingStartedAt.value = Date.now()
  bcSendModalState.value = 'sending'
  bcSendModalBroadcastId.value = Number(id || 0)
  bcSendModalText.value = ''
  bcSendTargetKind.value = String(target || 'users')
  bcStatsBatchId.value = ''
  bcLastSendTargetByPost.value = {
    ...(bcLastSendTargetByPost.value || {}),
    [Number(id || 0)]: String(target || ''),
  }
  bcSaveLastTargetsMap()
  bcStatsFrom.value = minusMinutesLocalInputValue(1)
  bcStatsTo.value = nowLocalInputValue()
  if (bcStatsModalOpen.value && Number(bcStatsSelectedId.value || 0) === Number(id || 0)) {
    bcStatsTab.value = String(target || '').toLowerCase() === 'groups' ? 'groups' : 'bots'
  }
  const tick = async () => {
    const bid = Number(bcSendModalBroadcastId.value || 0)
    if (!bid) return
    try {
      const row = await fetchSilent(() => api.adminBroadcast(bid))
      bcSendLiveRow.value = row || { id: bid }
      upsertBroadcastInList(row || { id: bid })
      if (
        bcStatsModalOpen.value &&
        Number(bcStatsSelectedId.value || 0) === bid &&
        !bcSendModalOpen.value
      ) {
        await loadBroadcastStats()
      }
      const st = String(row?.status || '').toLowerCase()
      const sentAt = row?.sent_at
      const okc = Number(row?.recipient_ok || 0)
      const flc = Number(row?.recipient_fail || 0)
      const totc = Number(row?.recipient_total || 0)
      const countsLookComplete = totc > 0 && okc + flc >= totc
      const finishedAsDraftWithStats = st === 'draft' && !!sentAt && countsLookComplete
      if (st === 'sent' || finishedAsDraftWithStats) {
        stopBroadcastProgressPolling()
        const bidSnap = bid
        const t0 = bcSendSendingStartedAt.value || Date.now()
        const wait = Math.max(0, BC_SEND_MIN_VISIBLE_MS - (Date.now() - t0))
        if (wait > 0) {
          await new Promise((resolve) => {
            setTimeout(resolve, wait)
          })
        }
        if (!bcSendModalOpen.value || Number(bcSendModalBroadcastId.value || 0) !== bidSnap) return
        bcSendModalState.value = 'done'
        await loadBcSendResultStats(bidSnap)
        return
      }
      if (st === 'failed') {
        bcSendModalState.value = 'failed'
        bcSendModalText.value = String(row?.error_message || 'Ошибка отправки')
        stopBroadcastProgressPolling()
      }
    } catch {
      // Сетевые сбои не должны рвать процесс отображения.
    }
  }
  tick()
  bcSendPollTimer.value = setInterval(tick, 1200)
}

function bcFileExt(name) {
  const n = String(name || '')
  const i = n.lastIndexOf('.')
  if (i < 0) return ''
  return n.slice(i + 1).toUpperCase()
}

function bcCurrentMaxLen() {
  return bcMediaKindStored.value === 'none' ? 4096 : 1024
}

function bcCurrentLen() {
  return String(bcNormalizeHtmlForTelegram(bcBodyHtml.value || '')).length
}

function bcHasMessageText() {
  const plain = String(bcNormalizeHtmlForTelegram(bcBodyHtml.value || '') || '')
    .replace(/\s+/g, '')
    .trim()
  return plain.length > 0
}

function bcHasSelectedTargets() {
  return Number(bcSelectedTargetsCount.value || 0) > 0
}

async function ensureEmojiPicker() {
  if (bcEmojiPickerReady.value) return
  try {
    await import('emoji-picker-element')
    bcEmojiPickerReady.value = true
  } catch {
    /* без смайл-пикера интерфейс остаётся рабочим */
  }
}

function bcSyncEditorHtml() {
  const el = bcBodyRef.value
  if (!el) return
  bcBodyHtml.value = String(el.innerHTML || '')
}

function bcRecordHistory(force = false) {
  const el = bcBodyRef.value
  if (!el) return
  const html = String(el.innerHTML || '')
  if (!force) {
    const cur = bcHistory.value[bcHistoryIndex.value]
    if (cur === html) return
  }
  if (bcHistoryIndex.value < bcHistory.value.length - 1) {
    bcHistory.value = bcHistory.value.slice(0, bcHistoryIndex.value + 1)
  }
  bcHistory.value.push(html)
  if (bcHistory.value.length > 120) {
    bcHistory.value.shift()
  }
  bcHistoryIndex.value = bcHistory.value.length - 1
}

function bcCanUndo() {
  return bcHistoryIndex.value > 0
}

function bcCanRedo() {
  return bcHistoryIndex.value >= 0 && bcHistoryIndex.value < bcHistory.value.length - 1
}

function bcUndo() {
  if (!bcCanUndo()) return
  bcHistoryIndex.value -= 1
  const el = bcBodyRef.value
  if (!el) return
  el.innerHTML = String(bcHistory.value[bcHistoryIndex.value] || '')
  bcSyncEditorHtml()
  bcSavedTick.value = false
  bcUpdateFormatState()
}

function bcRedo() {
  if (!bcCanRedo()) return
  bcHistoryIndex.value += 1
  const el = bcBodyRef.value
  if (!el) return
  el.innerHTML = String(bcHistory.value[bcHistoryIndex.value] || '')
  bcSyncEditorHtml()
  bcSavedTick.value = false
  bcUpdateFormatState()
}

function bcNormalizeHtmlForTelegram(raw) {
  const esc = (s) => String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  const host = document.createElement('div')
  host.innerHTML = String(raw || '')
  const walk = (node) => {
    if (!node) return ''
    if (node.nodeType === Node.TEXT_NODE) return esc(node.textContent || '')
    if (node.nodeType !== Node.ELEMENT_NODE) return ''
    const el = node
    const tag = String(el.tagName || '').toLowerCase()
    const inner = Array.from(el.childNodes || []).map((n) => walk(n)).join('')
    if (tag === 'br') return '\n'
    if (tag === 'div' || tag === 'p') return `${inner}\n`
    if (tag === 'b' || tag === 'strong') return `<b>${inner}</b>`
    if (tag === 'i' || tag === 'em') return `<i>${inner}</i>`
    if (tag === 'u') return `<u>${inner}</u>`
    if (tag === 's' || tag === 'strike' || tag === 'del') return `<s>${inner}</s>`
    if (tag === 'code') return `<code>${inner}</code>`
    if (tag === 'pre') return `<pre>${inner}</pre>`
    if (tag === 'blockquote') return `<blockquote>${inner}</blockquote>`
    if (tag === 'a') {
      const href = String(el.getAttribute('href') || '').trim().replace(/"/g, '&quot;')
      return href ? `<a href="${href}">${inner}</a>` : inner
    }
    if (tag === 'span' && String(el.getAttribute('data-spoiler') || '') === '1') {
      return `<tg-spoiler>${inner}</tg-spoiler>`
    }
    if (tag === 'tg-spoiler') return `<tg-spoiler>${inner}</tg-spoiler>`
    if (tag === 'tg-emoji') {
      const id = String(el.getAttribute('emoji-id') || '').trim()
      return id ? `<tg-emoji emoji-id="${id}">${inner || '🙂'}</tg-emoji>` : (inner || '🙂')
    }
    return inner
  }
  return walk(host).replace(/\n{3,}/g, '\n\n').trim()
}

function bcInsertHtmlAtCursor(html) {
  const sel = window.getSelection?.()
  const range = sel && sel.rangeCount ? sel.getRangeAt(0) : bcSavedRange.value
  if (!range) return
  range.deleteContents()
  const temp = document.createElement('div')
  temp.innerHTML = html
  const frag = document.createDocumentFragment()
  let node = null
  while ((node = temp.firstChild)) frag.appendChild(node)
  range.insertNode(frag)
  range.collapse(false)
  if (sel) {
    sel.removeAllRanges()
    sel.addRange(range)
  }
  bcSavedRange.value = range.cloneRange()
  bcSyncEditorHtml()
  bcRecordHistory()
}

function bcCurrentRange() {
  const sel = window.getSelection?.()
  if (sel && sel.rangeCount) return sel.getRangeAt(0)
  return bcSavedRange.value
}

function bcSelectedTextFromRange(range) {
  if (!range) return ''
  try {
    return String(range.cloneContents().textContent || '')
  } catch {
    return ''
  }
}

function bcWrapRange(range, htmlOpen, htmlClose) {
  if (!range) return false
  const text = bcSelectedTextFromRange(range)
  if (!text.trim()) return false
  const sel = window.getSelection?.()
  if (sel) {
    sel.removeAllRanges()
    sel.addRange(range)
  }
  bcInsertHtmlAtCursor(`${htmlOpen}${text}${htmlClose}`)
  return true
}

function bcExec(cmd) {
  const el = bcBodyRef.value
  if (!el) return
  el.focus()
  document.execCommand(cmd, false)
  bcUpdateFormatState()
  bcSyncEditorHtml()
  bcRecordHistory()
}

function bcExecEdit(cmd) {
  const el = bcEditBodyRef.value
  if (!el) return
  el.focus()
  document.execCommand(cmd, false)
  bcEditBodyHtml.value = bcNormalizeHtmlForTelegram(String(el.innerHTML || ''))
}

function bcFormatBold() { bcExec('bold') }
function bcFormatItalic() { bcExec('italic') }
function bcFormatUnderline() { bcExec('underline') }
function bcFormatStrike() { bcExec('strikeThrough') }
function bcEditBold() { bcExecEdit('bold') }
function bcEditItalic() { bcExecEdit('italic') }
function bcEditUnderline() { bcExecEdit('underline') }
function bcEditStrike() { bcExecEdit('strikeThrough') }
function bcFormatSpoiler() {
  const el = bcBodyRef.value
  if (!el) return
  el.focus()
  const range = bcCurrentRange()
  if (!bcWrapRange(range, '<span data-spoiler="1">', '</span>')) {
    alert('Выдели текст, затем нажми «Скрытый»')
    return
  }
  bcSavedTick.value = false
  bcUpdateFormatState()
}
function bcFormatPre() {
  const el = bcBodyRef.value
  if (!el) return
  el.focus()
  const sel = window.getSelection?.()
  const text = sel?.toString() || ''
  if (!text.trim()) {
    alert('Выдели текст, затем нажми «PRE»')
    return
  }
  bcInsertHtmlAtCursor(`<pre>${text}</pre>`)
  bcSavedTick.value = false
}
function bcFormatBlockquote() {
  const el = bcBodyRef.value
  if (!el) return
  el.focus()
  const range = bcCurrentRange()
  if (!bcWrapRange(range, '<blockquote>', '</blockquote>')) {
    alert('Выдели текст, затем нажми «Цитата»')
    return
  }
  bcSavedTick.value = false
  bcUpdateFormatState()
}
function bcClearFormatting() {
  const el = bcBodyRef.value
  if (!el) return
  // Полный сброс оформления: оставляем только чистый текст и эмодзи.
  // Скрытия/ссылки/цитаты/теги убираются, переносы строк сохраняются.
  const plain = String(el.innerText || '').replace(/\n{3,}/g, '\n\n').trim()
  el.innerHTML = ''
  el.innerText = plain
  bcBodyHtml.value = bcNormalizeHtmlForTelegram(plain)
  bcActiveSpoilerText.value = ''
  bcActiveLinkUrl.value = ''
  bcUpdateFormatState()
  bcRecordHistory()
  bcSavedTick.value = false
}
function bcFormatCode() {
  const el = bcBodyRef.value
  if (!el) return
  el.focus()
  const sel = window.getSelection?.()
  const text = sel?.toString() || ''
  if (!text.trim()) {
    alert('Выдели текст, затем нажми «Код»')
    return
  }
  bcInsertHtmlAtCursor(`<code>${text}</code>`)
  bcSavedTick.value = false
}

function bcFormatLink() {
  const el = bcBodyRef.value
  if (!el) return
  const sel = window.getSelection?.()
  const range = sel && sel.rangeCount ? sel.getRangeAt(0).cloneRange() : bcSavedRange.value
  const selectedText = bcSelectedTextFromRange(range)
  if (!selectedText.trim()) {
    alert('Выдели текст, затем нажми «Ссылка»')
    return
  }
  bcLinkRange.value = range || null
  bcLinkUrl.value = 'https://'
  bcLinkModalOpen.value = true
}

function bcApplyLinkModal() {
  const href = String(bcLinkUrl.value || '').trim()
  if (!href) return
  const el = bcBodyRef.value
  if (!el) return
  const sel = window.getSelection?.()
  el.focus()
  if (bcLinkRange.value && sel) {
    sel.removeAllRanges()
    sel.addRange(bcLinkRange.value)
  }
  document.execCommand('createLink', false, href)
  bcSyncEditorHtml()
  bcRecordHistory()
  bcSavedTick.value = false
  bcLinkModalOpen.value = false
  bcLinkRange.value = null
}

function bcEditLink() {
  const el = bcEditBodyRef.value
  if (!el) return
  const href = window.prompt('Ссылка', 'https://')
  if (!href || !String(href).trim()) return
  el.focus()
  document.execCommand('createLink', false, String(href).trim())
  bcEditBodyHtml.value = bcNormalizeHtmlForTelegram(String(el.innerHTML || ''))
}

function onBcEditInput(ev) {
  bcEditBodyHtml.value = bcNormalizeHtmlForTelegram(String(ev?.target?.innerHTML || ''))
}

function onBcEmojiClick(ev) {
  const unicode = ev?.detail?.unicode
  if (!unicode) return
  const el = bcBodyRef.value
  if (!el) return
  el.focus()
  bcInsertHtmlAtCursor(unicode)
  bcSavedTick.value = false
}

function onBcEditorInput(ev) {
  bcBodyHtml.value = bcNormalizeHtmlForTelegram(String(ev?.target?.innerHTML || ''))
  bcSavedTick.value = false
  bcRecordHistory()
  bcSaveLocalSnapshot()
}

function onBcEditorClick(ev) {
  const el = ev?.target
  if (!(el instanceof HTMLElement)) return
  const spoiler = el.closest('[data-spoiler="1"], tg-spoiler')
  if (!spoiler) return
  spoiler.classList.add('reveal')
  window.setTimeout(() => spoiler.classList.remove('reveal'), 5000)
}

function onBcEditorSelectionChange() {
  const sel = window.getSelection?.()
  if (!sel || !sel.rangeCount) return
  const range = sel.getRangeAt(0)
  const editor = bcBodyRef.value
  if (!editor) return
  if (!editor.contains(range.startContainer)) return
  bcSavedRange.value = range.cloneRange()
  const from = range.startContainer instanceof Element ? range.startContainer : range.startContainer?.parentElement
  const spoilerEl = from?.closest?.('[data-spoiler="1"], tg-spoiler')
  const linkEl = from?.closest?.('a')
  bcActiveSpoilerText.value = spoilerEl ? String(spoilerEl.textContent || '').trim() : ''
  bcActiveLinkUrl.value = linkEl ? String(linkEl.getAttribute('href') || '').trim() : ''
  bcUpdateFormatState()
}

function onGlobalClickForEmoji(ev) {
  if (!bcEmojiOpen.value) return
  const host = bcEmojiHostRef.value
  if (!host) return
  if (host.contains(ev.target)) return
  bcEmojiOpen.value = false
}

function bcUpdateFormatState() {
  try {
    bcFormatState.value = {
      bold: !!document.queryCommandState('bold'),
      italic: !!document.queryCommandState('italic'),
      underline: !!document.queryCommandState('underline'),
      strike: !!document.queryCommandState('strikeThrough'),
      spoiler: !!bcActiveSpoilerText.value,
      link: !!bcActiveLinkUrl.value,
    }
  } catch {
    bcFormatState.value = { bold: false, italic: false, underline: false, strike: false, spoiler: false, link: false }
  }
}

async function bcToggleEmojiOpen() {
  if (!bcEmojiOpen.value) {
    await ensureEmojiPicker()
  }
  bcEmojiOpen.value = !bcEmojiOpen.value
}

function todayIsoDate() {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function resetPayoutDatesToToday() {
  const t = todayIsoDate()
  dateFrom.value = t
  dateTo.value = t
}

function nextMondayLabel() {
  const d = new Date()
  const day = d.getDay() // 0..6, where 1 is Monday
  let addDays = (8 - day) % 7
  if (addDays === 0) addDays = 7
  d.setDate(d.getDate() + addDays)
  const dd = String(d.getDate()).padStart(2, '0')
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const yyyy = d.getFullYear()
  return `${dd}.${mm}.${yyyy}`
}

function payoutStatusLabel(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'new') return 'на рассмотрении'
  if (s === 'paid') return 'выплачено'
  if (s === 'rejected') return 'отклонено'
  return s || '—'
}

function payoutCardClass(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'paid') return 'border-sky-400/40 bg-sky-500/10'
  if (s === 'rejected') return 'border-rose-400/40 bg-rose-500/10'
  return 'border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800'
}

function openExternalLink(url) {
  const link = String(url || '').trim()
  if (!link) {
    alert('Ссылка недоступна для этого пользователя/чата')
    return
  }
  const tg = window.Telegram?.WebApp
  const normalized = link.startsWith('tg://user?id=')
    ? `https://t.me/user?id=${encodeURIComponent(link.replace('tg://user?id=', ''))}`
    : link
  try {
    if (normalized.startsWith('https://t.me/') && typeof tg?.openTelegramLink === 'function') {
      tg.openTelegramLink(normalized)
      return true
    }
  } catch {
    //
  }
  try {
    if (typeof tg?.openLink === 'function') {
      tg.openLink(normalized)
      return true
    }
  } catch {
    //
  }
  try {
    if (typeof window !== 'undefined' && window.location) {
      window.location.href = normalized
      return true
    }
  } catch {
    //
  }
  try {
    window.open(normalized, '_blank', 'noopener,noreferrer')
    return true
  } catch {
    alert('Не удалось открыть ссылку в Telegram')
    return false
  }
}

function openExternalFromAnchor(e, url) {
  const tg = window.Telegram?.WebApp
  const link = String(url || '').trim()
  if (!link) return
  if (typeof tg?.openTelegramLink === 'function' || typeof tg?.openLink === 'function') {
    e?.preventDefault?.()
    openExternalLink(link)
  }
}

function profileLinkForUser(u) {
  const username = String(u?.username || '').trim().replace(/^@+/, '')
  if (username) return `https://t.me/${username}`
  const tgId = Number(u?.telegram_id || 0)
  if (tgId > 0) return `https://t.me/user?id=${tgId}`
  return ''
}

const filteredPayouts = computed(() => {
  const q = String(payoutSearch.value || '').trim().toLowerCase()
  const source = payoutsOnlyPaid.value
    ? payouts.value.filter((x) => String(x?.status || '').toLowerCase() === 'paid')
    : payouts.value
  const filteredBySearch = !q
    ? source
    : source.filter((x) => {
    const uname = String(x?.username || '').toLowerCase()
    const fname = String(x?.first_name || '').toLowerCase()
    const tgId = String(x?.telegram_id || '')
    const reqId = String(x?.id || '')
    return uname.includes(q) || fname.includes(q) || tgId.includes(q) || reqId.includes(q)
  })
  const fromTs = dateFrom.value ? Date.parse(`${dateFrom.value}T00:00:00`) : null
  const toTs = dateTo.value ? Date.parse(`${dateTo.value}T23:59:59`) : null
  if (!fromTs && !toTs) return filteredBySearch
  return filteredBySearch.filter((x) => {
    const raw = String(x?.paid_at || x?.updated_at || x?.created_at || '')
    const ts = Date.parse(raw)
    if (!Number.isFinite(ts)) return false
    if (fromTs && ts < fromTs) return false
    if (toTs && ts > toTs) return false
    return true
  })
})

const payoutRequestsSummary = computed(() => {
  const activeStatuses = new Set(['new', 'approved', 'frozen'])
  const active = (payouts.value || []).filter((x) => activeStatuses.has(String(x?.status || '').toLowerCase()))
  const users = new Set(active.map((x) => Number(x?.telegram_id || 0)).filter((x) => x > 0))
  const total = active.reduce((acc, x) => acc + Number(x?.amount_rub || 0), 0)
  return {
    usersCount: users.size,
    requestsCount: active.length,
    totalAmountRub: Math.round(total * 100) / 100,
  }
})

async function loadOverview() {
  data.value = await fetch(() => api.adminOverview())
}

async function loadPayouts() {
  const r = await fetch(() => api.adminPayouts())
  payouts.value = r?.items || []
}

async function refreshPayoutsNow() {
  resetPayoutDatesToToday()
  await loadPayouts()
}

async function loadReferralsTop() {
  const [info, people] = await Promise.all([
    fetch(() => api.referral()),
    fetch(() => api.referralPeople()),
  ])
  referralInfo.value = info || null
  referralsTop.value = (people?.full_list || []).filter((x) => !!x?.is_paid)
}

async function loadCommissions() {
  const [list, summary] = await Promise.all([
    fetch(() => api.adminCommissions()),
    fetch(() => api.adminCommissionsSummary()),
  ])
  commissions.value = list?.items || []
  commissionsSummary.value = summary || commissionsSummary.value
}

async function loadMyPartnerPayouts() {
  try {
    const r = await fetch(() => api.referralPayouts())
    myPartnerPayouts.value = r || myPartnerPayouts.value
  } catch {
    //
  }
}

async function loadMyPartnerStats() {
  try {
    const r = await fetch(() => api.adminMyPartnerStats())
    myPartnerStats.value = r || myPartnerStats.value
  } catch {
    //
  }
}

async function loadUsers() {
  const r = await fetch(() => api.adminUsers())
  users.value = r?.items || []
  const target = Number(usersScrollTargetTelegramId.value || 0)
  if (target > 0) {
    usersScrollTargetTelegramId.value = 0
    await nextTick()
    const el = document.getElementById(`admin-user-card-${target}`)
    if (el) {
      usersHighlightTelegramId.value = target
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      window.setTimeout(() => {
        usersHighlightTelegramId.value = 0
      }, 2800)
    } else {
      window.alert('Пользователь не попал в выборку списка (первые 1000). Откройте Telegram-профиль по @username.')
    }
  }
}

async function goToAdminUserInList(telegramId) {
  const id = Number(telegramId || 0)
  if (!id) return
  usersScrollTargetTelegramId.value = id
  if (tab.value === 'users') {
    await loadUsers()
  } else {
    tab.value = 'users'
  }
}

async function loadChats() {
  try {
    const r = await fetch(() => api.adminChats())
    chats.value = r?.items || []
  } catch {
    chats.value = []
  }
}

const filteredChats = computed(() => {
  const owner = Number(chatsOwnerFilter.value || 0)
  if (!owner) return chats.value
  return chats.value.filter((c) => Number(c?.owner_telegram_id || 0) === owner)
})

function isTodayIso(isoLike) {
  if (!isoLike) return false
  const dt = new Date(isoLike)
  if (Number.isNaN(dt.getTime())) return false
  const now = new Date()
  return (
    dt.getFullYear() === now.getFullYear()
    && dt.getMonth() === now.getMonth()
    && dt.getDate() === now.getDate()
  )
}

const filteredAdminUsers = computed(() => {
  const preset = String(usersPreset.value || 'all')
  const rows = users.value || []
  if (preset === 'today') {
    return rows.filter((u) => isTodayIso(u?.first_start_at || u?.created_at))
  }
  if (preset === 'joins24') return rows.filter((u) => Number(u?.joins_24h || 0) > 0)
  if (preset === 'promo') return rows.filter((u) => !!String(u?.promo_applied_code || '').trim())
  if (preset === 'antiurl') return rows.filter((u) => !!u?.anti_url_enabled)
  if (preset === 'blocked') return rows.filter((u) => String(u?.status || '') === 'blocked')
  if (preset === 'online') return rows.filter((u) => !!userOnlineState(u?.last_webapp_seen_at).online)
  return rows
})

async function openAdminUserInfo(userRow) {
  selectedAdminUser.value = userRow || null
  showUserInfoModal.value = !!userRow
  selectedUserSubscriptionProfile.value = null
  const tg = Number(userRow?.telegram_id || 0)
  if (!tg) return
  selectedUserSubscriptionLoading.value = true
  try {
    const data = await fetchSilent(() => api.adminUserSubscriptionProfile(tg))
    selectedUserSubscriptionProfile.value = data
  } catch {
    selectedUserSubscriptionProfile.value = null
  } finally {
    selectedUserSubscriptionLoading.value = false
  }
}

function adminNavSnapshot() {
  return {
    tab: String(tab.value || 'overview'),
    chatsOwnerFilter: Number(chatsOwnerFilter.value || 0),
    usersPreset: String(usersPreset.value || 'all'),
  }
}

function applyAdminNavState(state) {
  if (!state) return
  navRestoring.value = true
  tab.value = String(state.tab || 'overview')
  chatsOwnerFilter.value = Number(state.chatsOwnerFilter || 0)
  usersPreset.value = String(state.usersPreset || 'all')
  setTimeout(() => {
    navRestoring.value = false
  }, 0)
}

function navBack() {
  const prev = navBackStack.value.pop()
  if (!prev) return
  navForwardStack.value.push(adminNavSnapshot())
  applyAdminNavState(prev)
}

function navForward() {
  const next = navForwardStack.value.pop()
  if (!next) return
  navBackStack.value.push(adminNavSnapshot())
  applyAdminNavState(next)
}

async function loadRevenueStats() {
  try {
    const r = await fetch(() => api.adminRevenueStats(revenuePeriod.value))
    revenueStats.value = r || revenueStats.value
  } catch {
    revenueStats.value = { today_rub: 0, month_rub: 0, by_day: [], by_month: [] }
  }
}

function revenuePeriodLabel(v) {
  const p = String(v || '')
  if (p === '7d') return '7д'
  if (p === '30d') return '30д'
  if (p === '90d') return '90д'
  if (p === '12m') return '12м'
  return p
}

async function loadReferralsFunnel() {
  try {
    const r = await fetch(() => api.adminReferralFunnel())
    referralsFunnel.value = r?.items || []
  } catch {
    referralsFunnel.value = []
  }
}

async function loadGlobalBadUrls() {
  const canRead = showFullAdminShell.value || isPremiumCabinet.value
  if (!canRead) {
    globalBadUrlItems.value = []
    globalBadUrlSystemItems.value = []
    globalBadUrlUserBases.value = []
    return
  }
  globalBadUrlLoading.value = true
  try {
    if (showFullAdminShell.value) {
      const r = await fetch(() => api.adminGlobalBadUrlsList())
      globalBadUrlSystemItems.value = r?.system || []
      const myTg = Number(meAdminProfile.value?.telegram_id || 0)
      const bases = Array.isArray(r?.user_bases) ? r.user_bases : []
      const mine = bases.find((x) => Number(x?.owner_telegram_id || 0) === myTg)
      globalBadUrlItems.value = mine?.items || []
      globalBadUrlUserBases.value = bases.filter((x) => Number(x?.owner_telegram_id || 0) !== myTg)
    } else if (isPremiumCabinet.value) {
      const r = await fetch(() => api.meGlobalBadUrlsList())
      globalBadUrlItems.value = r?.items || []
      globalBadUrlSystemItems.value = []
      globalBadUrlUserBases.value = []
    }
  } catch {
    globalBadUrlItems.value = []
    globalBadUrlSystemItems.value = []
    globalBadUrlUserBases.value = []
  } finally {
    globalBadUrlLoading.value = false
  }
}

async function addGlobalBadUrl() {
  const pattern = (newGlobalBadUrl.value || '').trim()
  if (!pattern) return
  globalBadUrlLoading.value = true
  try {
    await fetch(() =>
      api.adminGlobalBadUrlsAdd({
        pattern,
        note: (newGlobalBadUrlNote.value || '').trim(),
      }),
    )
    newGlobalBadUrl.value = ''
    newGlobalBadUrlNote.value = ''
    await loadGlobalBadUrls()
  } finally {
    globalBadUrlLoading.value = false
  }
}

async function removeGlobalBadUrl(pat) {
  globalBadUrlLoading.value = true
  try {
    await fetch(() => api.adminGlobalBadUrlsDelete(pat))
    await loadGlobalBadUrls()
  } finally {
    globalBadUrlLoading.value = false
  }
}

async function addMyGlobalBadUrl() {
  const pattern = (newMyGlobalBadUrl.value || '').trim()
  if (!pattern) return
  globalBadUrlLoading.value = true
  try {
    await fetch(() =>
      api.meGlobalBadUrlsAdd({
        pattern,
        note: (newMyGlobalBadUrlNote.value || '').trim(),
      }),
    )
    newMyGlobalBadUrl.value = ''
    newMyGlobalBadUrlNote.value = ''
    await loadGlobalBadUrls()
  } finally {
    globalBadUrlLoading.value = false
  }
}

async function removeMyGlobalBadUrl(pat) {
  globalBadUrlLoading.value = true
  try {
    await fetch(() => api.meGlobalBadUrlsDelete(pat))
    await loadGlobalBadUrls()
  } finally {
    globalBadUrlLoading.value = false
  }
}

async function loadDiagnosticsSummary() {
  const m = meAdminProfile.value
  if (!m || !hasFullAdminRights(m)) return
  incidentSummaryLoading.value = true
  try {
    const r = await fetchSilent(() => api.adminDiagnosticsSummary(24))
    incidentSummary.value = r
  } catch {
    incidentSummary.value = null
  } finally {
    incidentSummaryLoading.value = false
  }
}

async function loadOpsHealth() {
  opsLoading.value = true
  const delays = [0, 450, 1200]
  let lastErr = null
  for (let i = 0; i < delays.length; i += 1) {
    if (delays[i] > 0) {
      await new Promise((r) => setTimeout(r, delays[i]))
    }
    try {
      const r = await fetchSilent(() => api.adminOpsHealth())
      opsHealth.value = { ...(r || {}), load_failed: false }
      lastErr = null
      break
    } catch (e) {
      lastErr = e
    }
  }
  if (lastErr) {
    const human = messageFromApiError(lastErr)
    const urlHint = guardApiBaseEffective.value
      ? `Сейчас фронт обращается к API по адресу: ${guardApiBaseEffective.value}`
      : 'Адрес API пустой: задайте VITE_API_BASE_URL при сборке WebApp и/или runtime guard-api-config.js (см. DEPLOY-RAILWAY.md).'
    opsHealth.value = {
      status: 'unknown',
      load_failed: true,
      load_error_human: human,
      diagnostics: [
        'Мониторинг Guard Pulse сейчас не загрузился: это не «диагноз сервера», а то, что браузер/Telegram не смог получить ответ от API (часто сеть, CORS или неверный адрес API).',
        urlHint,
        human,
      ],
      activity_by_hour: [],
    }
  }
  opsLoading.value = false
  void loadDiagnosticsSummary()
}

function incidentCategoryLabel(cat) {
  const key = String(cat || '').toLowerCase()
  const map = {
    api: 'API',
    payment: 'Оплата',
    telegram_api: 'Telegram',
    broadcast: 'Рассылка',
    moderation: 'Модерация',
    bot: 'Бот',
    other: 'Прочее',
  }
  return map[key] || cat || '—'
}

/** Скорость ответа БД для подписи в Guard Pulse (мс, запятая как в RU). */
function formatDbPingMs(ms) {
  const n = Number(ms)
  if (!Number.isFinite(n) || n < 0) return '—'
  const t = n < 10 ? n.toFixed(2) : n < 100 ? n.toFixed(1) : String(Math.round(n))
  return `${t.replace('.', ',')} мс`
}

/** Сколько уже работает процесс API без перезапуска (тот хост/контейнер, куда ходит Mini App — не локальный терминал). */
function formatServerUptimeRu(sec) {
  const s = Math.max(0, Math.floor(Number(sec) || 0))
  if (s < 60) return `${s} с`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} мин`
  const h = Math.floor(m / 60)
  const rm = m % 60
  return rm ? `${h} ч ${rm} мин` : `${h} ч`
}

async function loadIncidentFeed() {
  incidentFeedLoading.value = true
  try {
    const q = (incidentSearchQuery.value || '').trim()
    const r = await fetch(() => api.adminDiagnosticsFeed(100, q))
    incidentFeed.value = Array.isArray(r?.items) ? r.items : []
  } catch {
    incidentFeed.value = []
  } finally {
    incidentFeedLoading.value = false
  }
}

watch(
  () => [tab.value, opsInnerTab.value],
  ([t, inner]) => {
    if (t !== 'ops') return
    void loadDiagnosticsSummary()
    if (inner === 'journal') loadIncidentFeed()
  },
)

async function loadInsights() {
  insightsLoading.value = true
  try {
    const r = await fetch(() => api.adminInsightsSummary(24))
    insights.value = r || insights.value
  } finally {
    insightsLoading.value = false
  }
}

async function loadMessageTemplates() {
  msgTemplatesLoading.value = true
  try {
    const [r, o] = await Promise.all([
      fetch(() => api.adminMessageTemplates()),
      fetch(() => api.adminMessageTemplateOptions()),
    ])
    msgTemplateOptions.value = o || msgTemplateOptions.value
    msgTemplates.value = (r?.items || []).map((x) => ({ ...x }))
  } finally {
    msgTemplatesLoading.value = false
  }
}

async function saveMessageTemplate(item) {
  const id = Number(item?.id || 0)
  if (!id) return
  msgTemplateSavingId.value = id
  try {
    await fetch(() =>
      api.adminMessageTemplatePatch(id, {
        title: item.title || '',
        body_text: item.body_text || '',
        enabled: !!item.enabled,
        delay_minutes: item.delay_minutes === '' || item.delay_minutes == null ? null : Number(item.delay_minutes),
        parse_mode: item.parse_mode || '',
        event_key: item.event_key || 'manual',
        target_kind: item.target_kind || 'owner_admin',
        trigger_hours: Number(item.trigger_hours || 24),
        min_count: Number(item.min_count || 1),
        cooldown_minutes: Number(item.cooldown_minutes || 1440),
        schedule_time_hm: item.schedule_time_hm || '',
      }),
    )
  } finally {
    msgTemplateSavingId.value = 0
  }
}

async function createMessageTemplate() {
  const title = prompt('Название нового сообщения')
  if (!title) return
  const body = prompt('Текст сообщения')
  if (!body) return
  await fetch(() =>
    api.adminMessageTemplateCreate({
      title,
      body_text: body,
      event_key: 'manual',
      target_kind: 'owner_admin',
      trigger_hours: 24,
      min_count: 1,
      cooldown_minutes: 1440,
    }),
  )
  await loadMessageTemplates()
}

async function deleteMessageTemplate(item) {
  if (!item?.is_custom) return
  if (!confirm(`Удалить сообщение «${item.title || item.template_key}»?`)) return
  await fetch(() => api.adminMessageTemplateDelete(item.id))
  msgTemplates.value = msgTemplates.value.filter((x) => Number(x.id || 0) !== Number(item.id || 0))
}

async function runOpsAction(action) {
  const actionLabel =
    action === 'restart_api' ? 'API' : action === 'restart_webapp' ? 'WebApp' : action === 'restart_bot' ? 'бота' : 'сервис'
  if (!window.confirm(`Перезапустить ${actionLabel}?`)) return
  opsActionLoading.value = action
  try {
    await fetch(() => api.adminOpsAction(action))
    await loadOpsHealth()
    if (action === 'restart_webapp') {
      if (window.confirm('WebApp отправлен на перезапуск. Обновить страницу сейчас?')) {
        window.location.reload()
      }
    } else if (action === 'restart_api') {
      window.alert('API отправлен на перезапуск.')
    } else {
      window.alert('Бот отправлен на перезапуск.')
    }
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось выполнить действие'))
  } finally {
    opsActionLoading.value = ''
  }
}

async function setPayoutStatus(item, status) {
  if (status === 'paid') {
    const ok = window.confirm('Подтвердить выплату? После подтверждения пользователю придет уведомление.')
    if (!ok) return
  }
  actionLoadingId.value = Number(item?.id || 0)
  try {
    await fetch(() => api.adminSetPayoutStatus(item.id, status))
    await Promise.all([loadPayouts(), loadCommissions()])
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось изменить статус'))
  } finally {
    actionLoadingId.value = 0
  }
}

async function resetUserFinance(item) {
  const tgId = Number(item?.telegram_id || 0)
  if (!tgId) return
  const ok = window.confirm(`Сбросить подписку и токены у ${item.first_name || item.username || tgId}?`)
  if (!ok) return
  try {
    await fetch(() => api.adminResetUserFinance(tgId))
    await loadUsers()
    await Promise.all([loadOverview(), loadPayouts(), loadReferralsTop(), loadCommissions(), loadMyPartnerPayouts(), loadMyPartnerStats()])
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось выполнить сброс'))
  }
}

async function deleteBlockUser(item) {
  const tgId = Number(item?.telegram_id || 0)
  if (!tgId) return
  const ok = window.confirm(`Удалить данные и заблокировать пользователя ${item.first_name || item.username || tgId}?`)
  if (!ok) return
  try {
    await fetch(() => api.adminDeleteBlockUser(tgId))
    await Promise.all([loadUsers(), loadChats(), loadOverview()])
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось удалить и заблокировать пользователя'))
  }
}

async function unblockUser(item) {
  const tgId = Number(item?.telegram_id || 0)
  if (!tgId) return
  const ok = window.confirm(
    `Разбанить ${item.first_name || item.username || tgId}? Статус станет активным, запись в глобальной антиспам-базе будет снята (если была).`,
  )
  if (!ok) return
  try {
    await fetch(() => api.adminUnblockUser(tgId))
    await loadUsers()
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось разбанить пользователя'))
  }
}

async function resetUserDelegation(item) {
  const tgId = Number(item?.telegram_id || 0)
  if (!tgId) return
  const ok = window.confirm(
    `Снять делегирование у ${item.first_name || item.username || tgId}? Пользователь перестанет быть менеджером во всех чужих чатах, приглашения менеджера будут удалены.`,
  )
  if (!ok) return
  try {
    await fetch(() => api.adminUserResetDelegation(tgId))
    await loadUsers()
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось сбросить делегирование'))
  }
}

async function resetUserConnectedChats(item) {
  const tgId = Number(item?.telegram_id || 0)
  if (!tgId) return
  const ok = window.confirm(
    `Отключить все группы пользователя ${item.first_name || item.username || tgId} как владельца? Чаты станут неактивными в панели (бот останется в группах до удаления вручную). Блокировки аккаунта не будет.`,
  )
  if (!ok) return
  try {
    await fetch(() => api.adminUserResetConnectedChats(tgId))
    await Promise.all([loadUsers(), loadChats(), loadOverview()])
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось отключить чаты'))
  }
}

function toggleJoinReportPeriod(item, periodId) {
  if (!item || !periodId) return
  const cur = Array.isArray(item.join_report_periods) ? [...item.join_report_periods] : []
  const i = cur.indexOf(periodId)
  if (i >= 0) cur.splice(i, 1)
  else cur.push(periodId)
  item.join_report_periods = cur
}

async function saveJoinReportSettings(item) {
  const tgId = Number(item?.telegram_id || 0)
  if (!tgId) return
  const periods = Array.isArray(item?.join_report_periods)
    ? item.join_report_periods.filter((x) => ['day', '3d', 'week', 'month'].includes(String(x)))
    : []
  try {
    const r = await fetch(() => api.adminUserSetJoinReportSettings(tgId, periods))
    item.join_report_periods = Array.isArray(r?.periods) ? r.periods : periods
    alert('Настройки отчётов сохранены')
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось сохранить периодичность отчётов'))
  }
}

function resolveTestTargetTelegramId() {
  const raw = String(testTargetTelegramId.value || '').trim()
  if (!raw) return null
  const id = Number(raw)
  return Number.isFinite(id) && id > 0 ? id : null
}

async function createAdminTestSubscription(months) {
  testPayLoading.value = true
  try {
    const targetId = resolveTestTargetTelegramId()
    const r = await fetch(() => api.adminTestCreateSubscriptionPayment(months, targetId))
    const url = String(r?.confirmation_url || '')
    if (!url) throw new Error('Не получена ссылка оплаты')
    const tg = window.Telegram?.WebApp
    if (typeof tg?.openLink === 'function') tg.openLink(url, { try_instant_view: false })
    else window.open(url, '_blank', 'noopener,noreferrer')
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось создать тестовую оплату'))
  } finally {
    testPayLoading.value = false
  }
}

async function createAdminTestTokens(tokens) {
  testPayLoading.value = true
  try {
    const targetId = resolveTestTargetTelegramId()
    const r = await fetch(() => api.adminTestCreateTokensPayment(tokens, targetId))
    const url = String(r?.confirmation_url || '')
    if (!url) throw new Error('Не получена ссылка оплаты')
    const tg = window.Telegram?.WebApp
    if (typeof tg?.openLink === 'function') tg.openLink(url, { try_instant_view: false })
    else window.open(url, '_blank', 'noopener,noreferrer')
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось создать тестовую оплату токенов'))
  } finally {
    testPayLoading.value = false
  }
}

async function createAdminBindingProbe(mode = 'live') {
  testPayLoading.value = true
  try {
    const targetId = resolveTestTargetTelegramId()
    const r = await fetch(() => api.adminTestCreateBindingProbePayment(targetId, mode))
    const url = String(r?.confirmation_url || '')
    if (!url) throw new Error('Не получена ссылка оплаты')
    const tg = window.Telegram?.WebApp
    if (typeof tg?.openLink === 'function') tg.openLink(url, { try_instant_view: false })
    else window.open(url, '_blank', 'noopener,noreferrer')
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось создать тариф 2д/1₽'))
  } finally {
    testPayLoading.value = false
  }
}

function bcEmptyButton() {
  return { text: '', url: '', web_app_url: '', callback_data: '' }
}

function bcKeyboardRowsFromApi(kbd) {
  const rows = kbd?.rows
  if (!rows?.length) return [[bcEmptyButton()]]
  return rows.map((row) =>
    row.map((b) => ({
      text: b.text || '',
      url: b.url || '',
      web_app_url: b.web_app?.url || '',
      callback_data: b.callback_data || '',
    })),
  )
}

function bcBuildKeyboardPayload() {
  const out = []
  for (const row of bcButtonRows.value) {
    const line = []
    for (const b of row) {
      const text = String(b.text || '').trim()
      if (!text) continue
      const url = String(b.url || '').trim()
      const wu = String(b.web_app_url || '').trim()
      const cb = String(b.callback_data || '').trim()
      if (url) line.push({ text, url })
      else if (wu) line.push({ text, web_app_url: wu })
      else if (cb) line.push({ text, callback_data: cb })
    }
    if (line.length) out.push(line)
  }
  return out
}

function upsertBroadcastInList(item) {
  if (!item?.id) return
  const id = Number(item.id)
  const idx = broadcasts.value.findIndex((x) => Number(x?.id || 0) === id)
  if (idx >= 0) {
    broadcasts.value[idx] = { ...broadcasts.value[idx], ...item }
    return
  }
  broadcasts.value.unshift(item)
}

async function persistCurrentBroadcast() {
  const id = bcSelectedId.value
  if (!id) return null
  bcSyncEditorHtml()
  const normalizedBody = bcNormalizeHtmlForTelegram(bcBodyHtml.value)
  const maxLen = bcMediaKindStored.value === 'none' ? 4096 : 1024
  if (normalizedBody.length > maxLen) {
    throw new Error(`Текст слишком длинный: максимум ${maxLen} символов для текущего типа поста`)
  }
  const r = await fetch(() =>
    api.adminBroadcastPatch(id, {
      title: bcTitle.value,
      body_text: normalizedBody,
      parse_mode: BC_PARSE_MODE,
      keyboard_rows: bcBuildKeyboardPayload(),
    }),
  )
  bcBodyHtml.value = normalizedBody
  bcMediaKindStored.value = r?.media_kind || bcMediaKindStored.value
  bcSavedTick.value = true
  bcSaveLocalSnapshot()
  upsertBroadcastInList(r)
  return r
}

function revokeBcDraftListThumbs() {
  const cur = bcDraftThumbById.value || {}
  for (const v of Object.values(cur)) {
    if (v?.previewUrl) revokeBroadcastMediaPreviewUrl(v.previewUrl)
  }
  bcDraftThumbById.value = {}
}

async function prefetchBcDraftListThumbs() {
  revokeBcDraftListThumbs()
  const list = (broadcasts.value || []).slice(0, 36)
  const next = {}
  for (const b of list) {
    const bid = Number(b?.id || 0)
    if (!bid) continue
    let items = Array.isArray(b?.media_items) ? b.media_items : []
    if (!items.length) {
      try {
        const full = await fetch(() => api.adminBroadcast(bid))
        items = Array.isArray(full?.media_items) ? full.media_items : []
      } catch {
        continue
      }
    }
    const first = (items || []).find((m) => {
      const k = String(m?.media_kind || '').toLowerCase()
      return Number(m?.id) > 0 && (k.includes('photo') || k.includes('video') || k === 'animation')
    })
    if (!first) continue
    const mid = Number(first.id)
    const mk = String(first.media_kind || '').toLowerCase()
    const kind = mk.includes('photo') ? 'photo' : 'video'
    try {
      const previewUrl = await fetchAdminBroadcastMediaPreviewUrl(bid, mid)
      next[bid] = { previewUrl, kind }
    } catch {
      //
    }
  }
  bcDraftThumbById.value = next
}

async function setBcBroadcastDraftListScope(scope) {
  const sc = scope === 'all' && bcBroadcastCanScopeAll.value ? 'all' : 'mine'
  bcBroadcastDraftListScope.value = sc
  await loadBroadcasts()
}

async function loadBroadcasts() {
  bcLoading.value = true
  try {
    const listScope =
      bcBroadcastDraftListScope.value === 'all' && bcBroadcastCanScopeAll.value ? 'all' : 'mine'
    const r = await fetch(() => api.adminBroadcasts(listScope))
    broadcasts.value = r?.items || []
    if (r?.scope === 'mine' && bcBroadcastDraftListScope.value === 'all') {
      bcBroadcastDraftListScope.value = 'mine'
    }
  } catch {
    broadcasts.value = []
  } finally {
    bcLoading.value = false
    await loadAutopostCampaigns()
  }
  await prefetchBcDraftListThumbs()
  const currentId = Number(bcSelectedId.value || 0)
  if (currentId && broadcasts.value.some((x) => Number(x?.id || 0) === currentId)) return
  let preferredId = 0
  try {
    preferredId = Number(localStorage.getItem(bcLastDraftIdKey()) || 0)
  } catch {
    preferredId = 0
  }
  const preferred = broadcasts.value.find((x) => Number(x?.id || 0) === preferredId)
  const fallback = broadcasts.value[0] || null
  if (preferred) applyBroadcastToForm(preferred)
  else if (fallback) applyBroadcastToForm(fallback)
}

async function loadAutopostCampaigns() {
  try {
    const r = await fetch(() => api.adminAutopostCampaigns())
    bcAutopostCampaigns.value = r?.items || []
  } catch {
    bcAutopostCampaigns.value = []
  }
}

function applyBroadcastToForm(item) {
  bcSelectedId.value = item?.id ?? null
  const local = bcLoadLocalSnapshot(item?.id)
  bcTitle.value = (local?.title ?? item?.title) || ''
  bcBodyHtml.value = bcNormalizeHtmlForTelegram((local?.body_html ?? item?.body_text) || '')
  bcButtonRows.value = local?.keyboard_rows?.length ? local.keyboard_rows : bcKeyboardRowsFromApi(item?.keyboard)
  const serverItems = Array.isArray(item?.media_items) ? item.media_items : []
  const serverHasMedia =
    serverItems.length > 0 ||
    String(item?.media_kind || 'none').toLowerCase() !== 'none' ||
    !!(item?.has_media_file || item?.telegram_file_id || (item?.media_original_name && String(item.media_original_name).trim()))
  if (serverHasMedia) {
    bcMediaKindStored.value = item?.media_kind || 'photo'
    bcMediaOriginalName.value = String(item?.media_original_name || '')
    bcMediaHistory.value = serverItems.length
      ? serverItems.map((m) => ({
          id: Number(m?.id || 0),
          name: String(m?.media_original_name || ''),
          kind: String(m?.media_kind || 'photo'),
          previewUrl: null,
        }))
      : item?.media_original_name
        ? [{ id: 0, name: String(item.media_original_name), kind: item?.media_kind || 'photo', previewUrl: null }]
        : []
  } else {
    bcMediaKindStored.value = local?.media_kind || item?.media_kind || 'none'
    bcMediaOriginalName.value = local?.media_name || item?.media_original_name || ''
    bcMediaHistory.value = serverItems.length
      ? serverItems.map((m) => ({
          id: Number(m?.id || 0),
          name: String(m?.media_original_name || ''),
          kind: String(m?.media_kind || 'photo'),
          previewUrl: null,
        }))
      : item?.media_original_name
        ? [{ id: 0, name: item.media_original_name, kind: item?.media_kind || 'photo', previewUrl: null }]
        : []
  }
  try {
    localStorage.setItem(bcLastDraftIdKey(), String(Number(item?.id || 0)))
  } catch {
    // ignore storage issues
  }
  bcSavedTick.value = true
  bcEditorOpen.value = true
  if (!bcAutopostingModalOpen.value) {
    applyAutopostFromServerItem(item)
  }
  nextTick(() => {
    if (bcBodyRef.value) bcBodyRef.value.innerHTML = bcBodyHtml.value || ''
    bcHistory.value = [String(bcBodyRef.value?.innerHTML || '')]
    bcHistoryIndex.value = 0
    bcUpdateFormatState()
    bcSaveLocalSnapshot()
    loadBcMediaThumbnails()
  })
}

async function createBcDraft() {
  try {
    const r = await fetch(() =>
      api.adminBroadcastCreate({
        title: 'Новый черновик',
        body_text: '',
        parse_mode: BC_PARSE_MODE,
        keyboard_rows: [],
      }),
    )
    upsertBroadcastInList(r)
    applyBroadcastToForm(r)
    await prefetchBcDraftListThumbs()
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось создать черновик'))
  }
}

async function saveBcDraft() {
  const id = bcSelectedId.value
  if (!id) return false
  bcSaving.value = true
  let ok = false
  try {
    await persistCurrentBroadcast()
    ok = true
    if (bcQuickDraftModalOpen.value) {
      bcQuickTitleBaseline.value = String(bcTitle.value || '')
      bcQuickDraftBaseline.value = {
        title: String(bcTitle.value || '').trim(),
        body: String(bcNormalizeHtmlForTelegram(bcBodyHtml.value || '') || ''),
        keyboard: JSON.stringify(bcBuildKeyboardPayload() || []),
        mediaKind: String(bcMediaKindStored.value || 'none'),
        mediaName: String(bcMediaOriginalName.value || ''),
      }
    }
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось сохранить'))
  } finally {
    bcSaving.value = false
  }
  return ok
}

function bcQuickDraftHasPendingChanges() {
  if (!bcQuickDraftModalOpen.value) return false
  bcSyncEditorHtml()
  const cur = {
    title: String(bcTitle.value || '').trim(),
    body: String(bcNormalizeHtmlForTelegram(bcBodyHtml.value || '') || ''),
    keyboard: JSON.stringify(bcBuildKeyboardPayload() || []),
    mediaKind: String(bcMediaKindStored.value || 'none'),
    mediaName: String(bcMediaOriginalName.value || ''),
  }
  const base = bcQuickDraftBaseline.value
  if (!base) {
    return !!(cur.title || cur.body || cur.keyboard !== '[]' || cur.mediaKind !== 'none' || cur.mediaName)
  }
  return (
    cur.title !== String(base.title || '') ||
    cur.body !== String(base.body || '') ||
    cur.keyboard !== String(base.keyboard || '[]') ||
    cur.mediaKind !== String(base.mediaKind || 'none') ||
    cur.mediaName !== String(base.mediaName || '')
  )
}

async function closeQuickBroadcastDraft() {
  if (bcSaving.value) return
  const hasChanges = bcQuickDraftHasPendingChanges()
  if (hasChanges) {
    const shouldSave = window.confirm('Сохранить изменения перед выходом?')
    if (shouldSave) {
      const saved = await saveBcDraft()
      if (!saved) return
    }
  }
  bcQuickDraftModalOpen.value = false
  bcAuxModal.value = ''
  bcEditorOpen.value = false
}

async function applyBcQuickDraftTitle() {
  const id = Number(bcSelectedId.value || 0)
  if (!id || !bcQuickTitleDirty.value) return
  const title = String(bcTitle.value ?? '').trim().slice(0, 255) || 'Черновик'
  bcSavingTitleId.value = id
  try {
    const r = await fetch(() => api.adminBroadcastPatch(id, { title }))
    upsertBroadcastInList(r)
    bcTitle.value = String(r?.title ?? title)
    bcQuickTitleBaseline.value = String(bcTitle.value)
    bcSaveLocalSnapshot()
    bcSavedTick.value = true
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось сохранить название'))
  } finally {
    bcSavingTitleId.value = null
  }
}

function revokeAllBcMediaPreviewUrls() {
  for (const m of bcMediaHistory.value) {
    if (m?.previewUrl) revokeBroadcastMediaPreviewUrl(m.previewUrl)
  }
}

async function loadBcMediaThumbnails() {
  const bid = Number(bcSelectedId.value || 0)
  if (!bid) return
  revokeAllBcMediaPreviewUrls()
  let sourceRows = [...bcMediaHistory.value]
  if (sourceRows.some((m) => !Number(m?.id) && (m?.name || String(m?.kind || '').toLowerCase() !== 'none'))) {
    try {
      const full = await fetch(() => api.adminBroadcast(bid))
      const items = Array.isArray(full?.media_items) ? full.media_items : []
      if (items.length) {
        sourceRows = items.map((m) => ({
          id: Number(m?.id || 0),
          name: String(m?.media_original_name || ''),
          kind: String(m?.media_kind || 'photo'),
          previewUrl: null,
        }))
        bcMediaHistory.value = sourceRows
      }
    } catch {
      //
    }
  }
  const next = []
  for (const m of bcMediaHistory.value) {
    const row = { ...m, previewUrl: null }
    const kid = String(m.kind || '').toLowerCase()
    const canThumb = !!m.id && (kid.includes('photo') || kid.includes('video') || kid === 'animation')
    if (canThumb) {
      try {
        row.previewUrl = await fetchAdminBroadcastMediaPreviewUrl(bid, m.id)
      } catch {
        row.previewUrl = null
      }
    }
    next.push(row)
  }
  bcMediaHistory.value = next
}

async function clearBcMedia() {
  const id = bcSelectedId.value
  if (!id) return
  if (!window.confirm('Убрать медиа из черновика?')) return
  try {
    const r = await fetch(() => api.adminBroadcastPatch(id, { clear_media: true }))
    bcMediaKindStored.value = r?.media_kind || 'none'
    bcMediaOriginalName.value = r?.media_original_name || ''
    revokeAllBcMediaPreviewUrls()
    bcMediaHistory.value = []
    bcSavedTick.value = false
    upsertBroadcastInList(r)
    await prefetchBcDraftListThumbs()
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Ошибка'))
  }
}

async function uploadBcMedia(ev) {
  const id = bcSelectedId.value
  const f = ev.target?.files?.[0]
  if (ev.target) ev.target.value = ''
  if (!id || !f) return
  bcUploading.value = true
  try {
    const r = await adminBroadcastUploadMedia(id, f, '')
    bcMediaKindStored.value = r?.media_kind || bcMediaKindStored.value
    bcMediaOriginalName.value = r?.media_original_name || bcMediaOriginalName.value
    const items = Array.isArray(r?.media_items) ? r.media_items : []
    bcMediaHistory.value = items.map((m) => ({
      id: Number(m?.id || 0),
      name: String(m?.media_original_name || ''),
      kind: String(m?.media_kind || 'photo'),
      previewUrl: null,
    }))
    bcSavedTick.value = false
    upsertBroadcastInList(r)
    await loadBcMediaThumbnails()
    await prefetchBcDraftListThumbs()
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Загрузка не удалась'))
  } finally {
    bcUploading.value = false
  }
}

async function removeBcMediaItem(mediaId) {
  const id = Number(bcSelectedId.value || 0)
  if (!id || !mediaId) return
  try {
    const r = await fetch(() => adminBroadcastDeleteMediaItem(id, mediaId))
    bcMediaKindStored.value = r?.media_kind || 'none'
    bcMediaOriginalName.value = r?.media_original_name || ''
    const items = Array.isArray(r?.media_items) ? r.media_items : []
    bcMediaHistory.value = items.map((m) => ({
      id: Number(m?.id || 0),
      name: String(m?.media_original_name || ''),
      kind: String(m?.media_kind || 'photo'),
      previewUrl: null,
    }))
    await loadBcMediaThumbnails()
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось удалить файл'))
  }
}

async function deleteBcDraft() {
  const id = bcSelectedId.value
  if (!id) return
  if (!window.confirm('Удалить черновик?')) return
  try {
    await fetch(() => api.adminBroadcastDelete(id))
    bcSelectedId.value = null
    bcTitle.value = ''
    bcBodyHtml.value = ''
    bcButtonRows.value = [[bcEmptyButton()]]
    bcMediaKindStored.value = 'none'
    bcMediaOriginalName.value = ''
    bcEditorOpen.value = false
    await loadBroadcasts()
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось удалить'))
  }
}

async function deleteBcDraftItem(item) {
  const id = Number(item?.id || 0)
  if (!id) return
  if (!window.confirm('Удалить этот черновик?')) return
  try {
    await fetch(() => api.adminBroadcastDelete(id))
    broadcasts.value = (broadcasts.value || []).filter((b) => Number(b?.id || 0) !== id)
    if (Number(bcSelectedId.value || 0) === id) {
      bcSelectedId.value = null
      bcEditorOpen.value = false
    }
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось удалить'))
  }
}

async function deleteBcDraftById(id) {
  const bid = Number(id || 0)
  if (!bid) return
  if (!window.confirm('Удалить этот черновик?')) return
  try {
    await fetch(() => api.adminBroadcastDelete(bid))
    try {
      localStorage.removeItem(bcDraftCacheKey(bid))
    } catch {
      // ignore
    }
    if (Number(bcSelectedId.value || 0) === bid) {
      bcSelectedId.value = null
      bcTitle.value = ''
      bcBodyHtml.value = ''
      bcButtonRows.value = [[bcEmptyButton()]]
      bcMediaKindStored.value = 'none'
      bcMediaOriginalName.value = ''
      bcEditorOpen.value = false
    }
    await loadBroadcasts()
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось удалить'))
  }
}

async function sendBc(target = 'users') {
  if (isBroadcastShellLite.value && target !== 'groups') {
    alert(
      isDelegatedFreeBroadcastCabinet.value
        ? 'По делегированному доступу можно отправлять только в группы владельца.'
        : 'В Premium-кабинете доступна только рассылка в ваши группы.',
    )
    return
  }
  const id = bcSelectedId.value
  if (!id) return
  let quote = null
  try {
    quote = await fetch(() => api.adminBroadcastQuote(id, target, []))
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось оценить стоимость рассылки'))
    return
  }
  if (quote?.broadcast_charge_applies && Number(quote.cost_tokens || 0) > 0 && quote.can_afford === false) {
    alert(
      `Недостаточно AURUM: нужно ${Number(quote.cost_tokens || 0)} ✨, доступно ${Number(quote.spendable_credits || 0)} ✨. Докупите пакет в главном приложении → «Токены» (нужна активная подписка).`,
    )
    return
  }
  const titleByTarget = target === 'groups'
    ? 'Разослать во все группы, где подключен бот?'
    : target === 'all'
      ? 'Разослать в личные сообщения и во все группы?'
      : 'Разослать всем активным пользователям бота?'
  const costHint =
    quote?.broadcast_charge_applies && Number(quote.cost_tokens || 0) > 0
      ? ` Будет списано ${Number(quote.cost_tokens)} ✨ (чатов в выборе: ${Number(quote.n_groups || 0)}; размер аудитории не умножает цену).`
      : ''
  if (!window.confirm(`${titleByTarget}${costHint} Запущенная отправка на сервере не останавливается, но прогресс можно скрыть кнопкой «Отменить просмотр».`)) return
  bcSending.value = true
  try {
    await persistCurrentBroadcast()
    await fetch(() => api.adminBroadcastSend(id, target, [], { keepDraftAfter: true }))
    upsertBroadcastInList({ id, status: 'sending' })
    startBroadcastProgressPolling(id, target)
    bcSaveLocalSnapshot()
    try {
      meAdminProfile.value = await api.me()
    } catch {
      //
    }
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось отправить'))
  } finally {
    bcSending.value = false
  }
}

async function openGroupsSendModal() {
  bcBroadcastGroupScope.value = 'mine'
  await loadBroadcastEligibleGroups()
  bcGroupsSearch.value = ''
  bcSelectedGroupIds.value = []
  bcShowGroupsPicker.value = true
}

async function openChannelsSendModal() {
  bcBroadcastGroupScope.value = 'mine'
  await loadBroadcastEligibleChannels()
  bcChannelsSearch.value = ''
  bcSelectedChannelIds.value = []
  bcShowChannelsPicker.value = true
}

function selectedGroupTitles() {
  const selected = new Set(bcSelectedGroupIds.value.map((x) => Number(x || 0)))
  const names = bcBroadcastGroups.value
    .filter((c) => selected.has(bcNormalizeChatId(c)))
    .map((c) => c.title || c.username || String(bcNormalizeChatId(c)))
  return names
}

function toggleAutopostGroupChat(id) {
  if (isDelegatedFreeBroadcastCabinet.value) return
  const v = Number(id || 0)
  if (!v) return
  const cur = [...(bcAutopostingForm.value.group_chat_ids || [])]
  const i = cur.indexOf(v)
  if (i >= 0) cur.splice(i, 1)
  else cur.push(v)
  cur.sort((a, b) => a - b)
  bcAutopostingForm.value = { ...bcAutopostingForm.value, group_chat_ids: cur }
}

function bcAutopostSelectAllListedGroups() {
  if (isDelegatedFreeBroadcastCabinet.value) return
  const ids = bcBroadcastGroups.value.map((x) => bcNormalizeChatId(x)).filter((x) => x < 0)
  bcAutopostingForm.value = { ...bcAutopostingForm.value, group_chat_ids: [...new Set(ids)].sort((a, b) => a - b) }
}

function bcAutopostClearGroupSelection() {
  if (isDelegatedFreeBroadcastCabinet.value) return
  bcAutopostingForm.value = { ...bcAutopostingForm.value, group_chat_ids: [] }
}

function toggleAutopostChannelChat(id) {
  if (isDelegatedFreeBroadcastCabinet.value) return
  const v = Number(id || 0)
  if (!v) return
  const cur = [...(bcAutopostingForm.value.channel_chat_ids || [])]
  const i = cur.indexOf(v)
  if (i >= 0) cur.splice(i, 1)
  else cur.push(v)
  cur.sort((a, b) => a - b)
  bcAutopostingForm.value = { ...bcAutopostingForm.value, channel_chat_ids: cur }
}

function bcAutopostSelectAllListedChannels() {
  if (isDelegatedFreeBroadcastCabinet.value) return
  const ids = bcBroadcastChannels.value.map((x) => bcNormalizeChatId(x)).filter((x) => x < 0)
  bcAutopostingForm.value = { ...bcAutopostingForm.value, channel_chat_ids: [...new Set(ids)].sort((a, b) => a - b) }
}

function bcAutopostClearChannelSelection() {
  if (isDelegatedFreeBroadcastCabinet.value) return
  bcAutopostingForm.value = { ...bcAutopostingForm.value, channel_chat_ids: [] }
}

const bcDraftBroadcastsForAutopost = computed(() =>
  (broadcasts.value || []).filter((b) => String(b?.status || 'draft').toLowerCase() === 'draft'),
)

function bcAutopostSetUseAllPosts(checked) {
  const v = !!checked
  const cid = Number(bcSelectedId.value || 0)
  bcAutopostingForm.value = {
    ...bcAutopostingForm.value,
    use_all_broadcasts: v,
    broadcast_ids: v ? [] : cid > 0 ? [cid] : [],
  }
}

function toggleAutopostBroadcastId(id) {
  const v = Number(id || 0)
  if (!v || bcAutopostingForm.value.use_all_broadcasts) return
  const cur = [...(bcAutopostingForm.value.broadcast_ids || [])]
  const i = cur.indexOf(v)
  if (i >= 0) cur.splice(i, 1)
  else cur.push(v)
  cur.sort((a, b) => a - b)
  bcAutopostingForm.value = { ...bcAutopostingForm.value, broadcast_ids: cur }
}

function bcAutopostSelectAllDraftPosts() {
  if (bcAutopostingForm.value.use_all_broadcasts) return
  const ids = bcDraftBroadcastsForAutopost.value.map((b) => Number(b.id)).filter((x) => x > 0)
  bcAutopostingForm.value = { ...bcAutopostingForm.value, broadcast_ids: [...new Set(ids)].sort((a, b) => a - b) }
}

function bcAutopostClearPostSelection() {
  const cid = Number(bcSelectedId.value || 0)
  bcAutopostingForm.value = {
    ...bcAutopostingForm.value,
    use_all_broadcasts: false,
    broadcast_ids: cid > 0 ? [cid] : [],
  }
}

async function openBcPreviewFromAutopost(b) {
  await openBcPreview(b)
}

function bcRevokePreviewMediaThumbs() {
  for (const t of bcPreviewMediaThumbs.value) {
    if (t?.previewUrl) revokeBroadcastMediaPreviewUrl(t.previewUrl)
  }
  bcPreviewMediaThumbs.value = []
}

async function loadPreviewMediaThumbs(item) {
  bcRevokePreviewMediaThumbs()
  const bid = Number(item?.id || 0)
  if (!bid) return
  let rows = Array.isArray(item?.media_items) ? item.media_items : []
  if (
    !rows.length &&
    (item?.media_original_name ||
      item?.has_media_file ||
      item?.telegram_file_id ||
      String(item?.media_kind || 'none').toLowerCase() !== 'none')
  ) {
    try {
      const full = await fetch(() => api.adminBroadcast(bid))
      rows = Array.isArray(full?.media_items) ? full.media_items : []
    } catch {
      rows = []
    }
  }
  const thumbs = []
  for (const m of rows) {
    const mk = String(m.media_kind || '').toLowerCase()
    const mid = Number(m.id || 0)
    if (!mid) continue
    if (mk.includes('photo') || mk.includes('video') || mk === 'animation') {
      try {
        const previewUrl = await fetchAdminBroadcastMediaPreviewUrl(bid, mid)
        thumbs.push({
          previewUrl,
          kind: mk.includes('photo') ? 'photo' : mk.includes('video') ? 'video' : 'animation',
          name: String(m.media_original_name || ''),
        })
      } catch {
        //
      }
    }
    if (thumbs.length >= 8) break
  }
  bcPreviewMediaThumbs.value = thumbs
}

function bcStartDraftRename(b) {
  bcDraftRenameId.value = Number(b?.id || 0) || null
  bcDraftRenameValue.value = String(b?.title || '')
}

function bcCancelDraftRename() {
  bcDraftRenameId.value = null
  bcDraftRenameValue.value = ''
}

async function bcCommitDraftRename(b) {
  const id = Number(b?.id || 0)
  if (!id) return
  const title = String(bcDraftRenameValue.value || '').trim().slice(0, 255)
  bcSavingTitleId.value = id
  try {
    const r = await fetch(() => api.adminBroadcastPatch(id, { title }))
    upsertBroadcastInList(r)
    if (Number(bcSelectedId.value || 0) === id) {
      bcTitle.value = String(r?.title ?? title)
      bcSaveLocalSnapshot()
    }
    bcDraftRenameId.value = null
    bcDraftRenameValue.value = ''
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось сохранить название'))
  } finally {
    bcSavingTitleId.value = null
  }
}

function onBcDraftCardShellClick(b) {
  if (bcDraftRenameId.value && Number(bcDraftRenameId.value) !== Number(b?.id || 0)) {
    bcCancelDraftRename()
  }
  applyBroadcastToForm(b)
}

function toggleGroupSelection(id) {
  if (isDelegatedFreeBroadcastCabinet.value) return
  const v = Number(id || 0)
  if (!v) return
  if (bcSelectedGroupIds.value.includes(v)) {
    bcSelectedGroupIds.value = bcSelectedGroupIds.value.filter((x) => x !== v)
  } else {
    bcSelectedGroupIds.value.push(v)
  }
}

function toggleChannelSelection(id) {
  if (isDelegatedFreeBroadcastCabinet.value) return
  const v = Number(id || 0)
  if (!v) return
  if (bcSelectedChannelIds.value.includes(v)) {
    bcSelectedChannelIds.value = bcSelectedChannelIds.value.filter((x) => x !== v)
  } else {
    bcSelectedChannelIds.value.push(v)
  }
}

function toggleBotRecipientSelection(id) {
  const v = Number(id || 0)
  if (!v) return
  if (bcSelectedBotRecipientIds.value.includes(v)) {
    bcSelectedBotRecipientIds.value = bcSelectedBotRecipientIds.value.filter((x) => x !== v)
  } else {
    bcSelectedBotRecipientIds.value.push(v)
  }
}

async function sendBcToSelectedGroups() {
  bcSendTargetGroups.value = true
  bcShowGroupsPicker.value = false
  bcSendTargetModalOpen.value = true
}

function selectedChannelTitles() {
  const selected = new Set(bcSelectedChannelIds.value.map((x) => Number(x || 0)))
  return bcBroadcastChannels.value
    .filter((c) => selected.has(bcNormalizeChatId(c)))
    .map((c) => c.title || c.username || String(bcNormalizeChatId(c)))
}

async function sendBcToSelectedChannels() {
  bcSendTargetChannels.value = true
  bcShowChannelsPicker.value = false
  bcSendTargetModalOpen.value = true
}

function chooseBotRecipients() {
  bcShowBotsPicker.value = false
  bcSendTargetModalOpen.value = true
}

function addBcRow() {
  bcButtonRows.value.push([bcEmptyButton()])
}

function addBcButton(rowIdx) {
  bcButtonRows.value[rowIdx].push(bcEmptyButton())
}

function removeBcButton(rowIdx, btnIdx) {
  const row = bcButtonRows.value[rowIdx]
  row.splice(btnIdx, 1)
  if (!row.length) {
    bcButtonRows.value.splice(rowIdx, 1)
  }
  if (!bcButtonRows.value.length) bcButtonRows.value = [[bcEmptyButton()]]
  bcSavedTick.value = false
}

function removeBcRow(rowIdx) {
  bcButtonRows.value.splice(rowIdx, 1)
  if (!bcButtonRows.value.length) bcButtonRows.value = [[bcEmptyButton()]]
  bcSavedTick.value = false
}

function closeBcPreview() {
  bcShowPreview.value = false
  bcRevokePreviewMediaThumbs()
}

function openBcMediaViewer(m) {
  if (!m?.previewUrl) return
  bcMediaViewerItem.value = m
  bcMediaViewerOpen.value = true
}

function closeBcMediaViewer() {
  bcMediaViewerOpen.value = false
  bcMediaViewerItem.value = null
}

async function openBcPreview(item) {
  bcRevokePreviewMediaThumbs()
  bcPreviewItem.value = item || null
  bcShowPreview.value = true
  await loadPreviewMediaThumbs(item)
}

function previewKeyboardRows(item) {
  try {
    return item?.keyboard?.rows || []
  } catch {
    return []
  }
}

async function saveBcEditModal() {
  const id = Number(bcSelectedId.value || 0)
  if (!id) return
  bcSaving.value = true
  try {
    const body = bcNormalizeHtmlForTelegram(bcEditBodyHtml.value)
    const r = await fetch(() =>
      api.adminBroadcastPatch(id, {
        title: bcEditTitle.value,
        body_text: body,
        parse_mode: BC_PARSE_MODE,
      }),
    )
    bcEditModalOpen.value = false
    upsertBroadcastInList(r)
    applyBroadcastToForm(r)
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось сохранить'))
  } finally {
    bcSaving.value = false
  }
}

onMounted(async () => {
  if (String(route.query.cabinet || '').toLowerCase() === 'delegated') {
    setCabinetMode('delegated')
  }
  window.addEventListener('click', onGlobalClickForEmoji)
  document.addEventListener('selectionchange', onBcEditorSelectionChange)
  if (!hasInitData.value) {
    loading.value = false
    return
  }
  resetPayoutDatesToToday()
  loading.value = true
  error.value = ''
  try {
    meAdminProfile.value = await api.me()
    bcLastSendTargetByPost.value = bcLoadLastTargetsMap()
    const bcDeepTab = String(route.query.tab || '').toLowerCase() === 'broadcasts'
    let bcDeepChannel = 0
    try {
      bcDeepChannel = Number(localStorage.getItem(BC_OPEN_CHANNEL_KEY) || 0)
    } catch {
      bcDeepChannel = 0
    }
    if (isDelegatedFreeBroadcastCabinet.value) {
      tab.value = 'broadcasts'
      bcStatsTab.value = 'groups'
      bcBroadcastGroupScope.value = 'mine'
      await Promise.allSettled([
        loadBroadcasts(),
        loadBroadcastEligibleGroups(),
        loadBroadcastEligibleChannels(),
      ])
    } else if (isPremiumCabinet.value) {
      tab.value = 'overview'
      bcStatsTab.value = 'groups'
      bcBroadcastGroupScope.value = 'mine'
      await Promise.allSettled([
        loadPartnerLiteActivity(),
        loadReferralLite(),
        loadBroadcasts(),
        loadMyPartnerStatsLite(),
      ])
    } else {
      // Быстрый первый экран админки: сначала обзор/пользователи.
      await Promise.all([loadOverview(), loadUsers()])
      // Остальные данные догружаем в фоне, чтобы вкладка открывалась заметно быстрее.
      Promise.allSettled([
        loadPayouts(),
        loadReferralsTop(),
        loadCommissions(),
        loadMyPartnerPayouts(),
        loadMyPartnerStats(),
        loadOpsHealth(),
        loadInsights(),
        loadMessageTemplates(),
        loadChats(),
        loadRevenueStats(),
        loadReferralsFunnel(),
      ]).catch(() => {
        //
      })
    }
    if (bcDeepTab || bcDeepChannel) {
      tab.value = 'broadcasts'
      try {
        await ensureEmojiPicker()
      } catch {
        //
      }
      await Promise.all([loadBroadcasts(), loadBroadcastEligibleGroups(), loadBroadcastEligibleChannels()])
      tryApplyDelegatedPreferredGroup()
      tryApplyOpenChannelPref()
    } else if (showFullAdminShell.value && String(route.query.tab || '').toLowerCase() === 'ops') {
      tab.value = 'ops'
      opsInnerTab.value = String(route.query.ops || '').toLowerCase() === 'journal' ? 'journal' : 'pulse'
    }
  } catch (e) {
    error.value = String(e?.body?.detail || e?.message || 'Нет доступа')
  } finally {
    loading.value = false
  }
})

watch(
  () => bcShowPreview.value,
  (open) => {
    if (!open) bcRevokePreviewMediaThumbs()
  },
)

watch(
  () => bcAuxModal.value,
  (v) => {
    if (v === 'media') loadBcMediaThumbnails()
  },
)

onBeforeUnmount(() => {
  closeBcMediaViewer()
  bcRevokePreviewMediaThumbs()
  revokeBcDraftListThumbs()
  revokeAllBcMediaPreviewUrls()
  window.removeEventListener('click', onGlobalClickForEmoji)
  document.removeEventListener('selectionchange', onBcEditorSelectionChange)
  if (bcStatsReloadTimer.value) {
    clearTimeout(bcStatsReloadTimer.value)
    bcStatsReloadTimer.value = null
  }
  document.body.style.overflow = ''
  stopBroadcastProgressPolling()
  if (bcStatsPollTimer.value) {
    clearInterval(bcStatsPollTimer.value)
    bcStatsPollTimer.value = null
  }
})

watch(
  () => [tab.value, isDelegatedFreeBroadcastCabinet.value],
  ([t, delegatedFree]) => {
    if (delegatedFree && t !== 'broadcasts') {
      tab.value = 'broadcasts'
    }
  },
)

watch(
  () => tab.value,
  async (v) => {
    if (v === 'payouts') {
      resetPayoutDatesToToday()
      await loadPayouts()
      return
    }
    if (v === 'commissions') {
      await loadCommissions()
      return
    }
    if (v === 'users') {
      await loadUsers()
      return
    }
    if (v === 'chats') {
      await loadChats()
      return
    }
    if (v === 'revenue') {
      await loadRevenueStats()
      return
    }
    if (v === 'funnel') {
      await loadReferralsFunnel()
      return
    }
    if (v === 'ops') {
      await loadOpsHealth()
      return
    }
    if (v === 'bad_urls') {
      if (!showFullAdminShell.value && !isPremiumCabinet.value) {
        tab.value = 'overview'
        return
      }
      await loadGlobalBadUrls()
      return
    }
    if (v === 'insights') {
      await loadInsights()
      return
    }
    if (v === 'messages') {
      await loadMessageTemplates()
      return
    }
    if (v === 'broadcasts') {
      try {
        await ensureEmojiPicker()
      } catch {
        //
      }
      await loadBroadcasts()
      await loadBroadcastEligibleGroups()
      await loadBroadcastEligibleChannels()
      tryApplyDelegatedPreferredGroup()
      tryApplyOpenChannelPref()
    }
  }
)

watch(() => bcTitle.value, () => {
  bcSavedTick.value = false
  bcSaveLocalSnapshot()
})

watch(
  () => bcButtonRows.value,
  () => {
    bcSavedTick.value = false
    bcSaveLocalSnapshot()
  },
  { deep: true },
)

watch(() => bcBodyHtml.value, () => {
  bcSaveLocalSnapshot()
})

watch(
  () => [bcStatsModalOpen.value, bcStatsSelectedId.value],
  ([open, id]) => {
    if (!open) return
    if (!Number(id || 0)) return
    loadBroadcastStats()
  },
)

watch(() => bcStatsSelectedId.value, () => {
  bcStatsBatchId.value = ''
})

watch(() => bcStatsBatchId.value, (v, p) => {
  // batch selector hidden; keep state for compatibility only.
})

watch(() => bcStatsTab.value, (v, p) => {
  if (!bcStatsModalOpen.value) return
  if (isBroadcastShellLite.value && v === 'bots') {
    bcStatsTab.value = 'groups'
    return
  }
  if (v === p) return
  loadBroadcastStats()
})

watch(
  () => [bcStatsFrom.value, bcStatsTo.value],
  () => {
    if (!bcStatsModalOpen.value) return
    if (!bcStatsFrom.value && !bcStatsTo.value) bcStatsPreset.value = ''
    scheduleLoadBroadcastStats(250)
  },
)

watch(
  () => [bcStatsFrom.value, bcStatsTo.value, bcStatsData.value?.batches?.length || 0],
  () => {
    const list = bcStatsBatchesFiltered.value
    if (!list.length) {
      bcStatsBatchId.value = ''
      return
    }
    if (!list.some((x) => String(x?.batch_id || '') === String(bcStatsBatchId.value || ''))) {
      bcStatsBatchId.value = String(list[0]?.batch_id || '')
    }
  },
)

watch(
  () =>
    bcStatsModalOpen.value ||
    partnerOverlayOpen.value ||
    bcQuickDraftModalOpen.value ||
    bcShowAllRecentModal.value ||
    bcSendTargetModalOpen.value ||
    bcSendModalOpen.value ||
    bcConfirmModalOpen.value ||
    bcShowBotsPicker.value,
  (lock) => {
    if (typeof document === 'undefined') return
    const body = document.body
    const html = document.documentElement
    if (lock) {
      body.dataset.modalLockY = String(window.scrollY || 0)
      body.style.position = 'fixed'
      body.style.top = `-${body.dataset.modalLockY}px`
      body.style.left = '0'
      body.style.right = '0'
      body.style.width = '100%'
      body.style.overflow = 'hidden'
      html.style.overflow = 'hidden'
    } else {
      const y = Number(body.dataset.modalLockY || 0)
      body.style.position = ''
      body.style.top = ''
      body.style.left = ''
      body.style.right = ''
      body.style.width = ''
      body.style.overflow = ''
      html.style.overflow = ''
      delete body.dataset.modalLockY
      if (Number.isFinite(y) && y > 0) window.scrollTo(0, y)
    }
  },
  { immediate: true },
)

watch(() => bcStatsModalOpen.value, () => {
  if (bcStatsPollTimer.value) {
    clearInterval(bcStatsPollTimer.value)
    bcStatsPollTimer.value = null
  }
})

watch(
  [() => tab.value, () => chatsOwnerFilter.value, () => usersPreset.value],
  (next, prev) => {
    if (!prev || navRestoring.value) return
    const [prevTab, prevOwner, prevPreset] = prev
    const [nextTab, nextOwner, nextPreset] = next
    if (prevTab === nextTab && prevOwner === nextOwner && prevPreset === nextPreset) return
    navBackStack.value.push({
      tab: String(prevTab || 'overview'),
      chatsOwnerFilter: Number(prevOwner || 0),
      usersPreset: String(prevPreset || 'all'),
    })
    if (navBackStack.value.length > 80) navBackStack.value.shift()
    navForwardStack.value = []
  },
)
</script>

<template>
  <div
    class="relative min-h-[calc(100dvh-7rem)]"
  >
    <div
      class="pointer-events-none fixed inset-0 z-0 bg-cover bg-center"
      :style="{ backgroundImage: `url(${adminBcBg})`, backgroundAttachment: 'fixed' }"
      aria-hidden="true"
    />
    <div
      class="pointer-events-none fixed inset-0 z-0 bg-black/55"
      aria-hidden="true"
    />
    <div class="relative z-10 space-y-3 pb-[calc(5.25rem+env(safe-area-inset-bottom,0px))]">
    <div v-if="!hasInitData" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
      Откройте панель из Telegram.
    </div>
    <div v-else-if="loading" class="rounded-xl border border-slate-200 bg-white p-4 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
      Загрузка...
    </div>
    <div v-else-if="error" class="rounded-xl border border-rose-300 bg-rose-50 p-4 text-rose-700 dark:border-rose-700 dark:bg-rose-900/20 dark:text-rose-300">
      {{ error }}
    </div>
    <template v-else>
    <h1 class="text-xl font-semibold text-gray-100 md:text-2xl">
      {{
        isPremiumCabinet
          ? '👑 Кабинет Premium'
          : isDelegatedFreeBroadcastCabinet
            ? 'Рассылка (делегированный чат)'
            : 'Админка'
      }}
    </h1>
    <div class="flex items-center gap-2">
      <button
        type="button"
        class="rounded-lg border border-white/15 bg-white/10 px-2.5 py-1 text-xs font-semibold text-slate-100 hover:bg-white/15 disabled:opacity-50"
        :disabled="!navBackStack.length"
        @click="navBack"
      >
        ← Назад
      </button>
      <button
        type="button"
        class="rounded-lg border border-white/15 bg-white/10 px-2.5 py-1 text-xs font-semibold text-slate-100 hover:bg-white/15 disabled:opacity-50"
        :disabled="!navForwardStack.length"
        @click="navForward"
      >
        Вперёд →
      </button>
    </div>
    <p
      v-if="isDelegatedFreeBroadcastCabinet"
      class="text-[12px] leading-snug text-violet-200/90"
    >
      Доступна только рассылка и автопост в группы, куда вас добавили как менеджера. Другие разделы админки недоступны.
    </p>
    <div v-if="showFullAdminShell" class="grid grid-cols-3 gap-2">
      <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'overview' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'overview'">Статистика</button>
      <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'payouts' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'payouts'">Выплаты</button>
      <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'referrals' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'referrals'">Рефералы</button>
      <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'commissions' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'commissions'">Комиссии</button>
      <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'test_payments' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'test_payments'">Тест оплаты</button>
      <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'ops' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'ops'">Guard Pulse</button>
      <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'bad_urls' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'bad_urls'">АнтиURL</button>
      <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'insights' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'insights'">Сводка</button>
      <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'messages' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'messages'">Сообщения</button>
      <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'broadcasts' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'broadcasts'">Рассылка</button>
      <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'subscription' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'subscription'">Подписка</button>
    </div>
    <div v-else-if="isPremiumCabinet" class="grid grid-cols-3 gap-2">
      <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'overview' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'overview'">Статистика</button>
      <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'broadcasts' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'broadcasts'">Рассылка</button>
      <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'referrals' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'referrals'">Рефералы</button>
      <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'bad_urls' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'bad_urls'">АнтиURL</button>
      <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'subscription' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'subscription'">Подписка</button>
    </div>

    <div
      v-if="tab === 'overview' && (isPremiumCabinet || data)"
      class="grid grid-cols-2 gap-2"
    >
      <template v-if="isPremiumCabinet">
        <div class="col-span-2 rounded-xl border border-slate-600 bg-slate-900/80 p-3 text-slate-100">
          <p class="text-xs font-semibold text-lime-300/90">Статистика защиты (ваши группы)</p>
          <p class="mt-1 text-[11px] text-slate-400">Управление по вашим подключённым группам/каналам: активность, подключения, удаления, расходы и отчёты в личку.</p>
        </div>
        <div
          role="button"
          tabindex="0"
          class="relative cursor-pointer select-none rounded-xl border border-cyan-500/45 bg-cyan-950/30 p-3 pt-9 text-left shadow-[0_0_18px_-8px_rgba(34,211,238,0.55)] outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
          @click="openPartnerGroupsModal"
          @keydown.enter.prevent="openPartnerGroupsModal"
          @keydown.space.prevent="openPartnerGroupsModal"
        >
          <button
            type="button"
            v-bind="partnerHelpBind('chatList')"
            @click.stop.prevent="partnerShowHelp('chatList')"
            @mousedown.stop
          >
            i
          </button>
          <p class="text-[10px] font-semibold uppercase tracking-wide text-cyan-200/90">Группы</p>
          <p class="mt-1 text-lg font-extrabold text-cyan-100">
            {{ Number((plActivitySummary?.groups_count ?? plActivitySummary?.chats_count) || 0) }} / {{ Number((plActivitySummary?.groups_limit ?? plActivitySummary?.chat_limit) || 0) }}
          </p>
          <p class="text-[10px] text-cyan-100/75">лимиты считаются отдельно</p>
        </div>
        <div
          role="button"
          tabindex="0"
          class="relative cursor-pointer select-none rounded-xl border border-amber-500/45 bg-amber-950/30 p-3 pt-9 text-left shadow-[0_0_18px_-8px_rgba(251,191,36,0.45)] outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60"
          @click="openPartnerGroupsModal"
          @keydown.enter.prevent="openPartnerGroupsModal"
          @keydown.space.prevent="openPartnerGroupsModal"
        >
          <button
            type="button"
            v-bind="partnerHelpBind('chatList')"
            @click.stop.prevent="partnerShowHelp('chatList')"
            @mousedown.stop
          >
            i
          </button>
          <p class="text-[10px] font-semibold uppercase tracking-wide text-amber-200/90">Каналы</p>
          <p class="mt-1 text-lg font-extrabold text-amber-100">
            {{ Number(plActivitySummary?.channels_count || 0) }} / {{ Number((plActivitySummary?.channels_limit ?? plActivitySummary?.channel_limit) || 0) }}
          </p>
          <p class="text-[10px] text-amber-100/75">лимиты считаются отдельно</p>
        </div>
        <div
          role="button"
          tabindex="0"
          class="relative cursor-pointer select-none rounded-xl border border-violet-500/45 bg-violet-950/30 p-3 pt-9 text-left shadow-[0_0_18px_-8px_rgba(139,92,246,0.55)] outline-none focus-visible:ring-2 focus-visible:ring-violet-400/60"
          @click="openPartnerJoinsModal"
          @keydown.enter.prevent="openPartnerJoinsModal"
          @keydown.space.prevent="openPartnerJoinsModal"
        >
          <button
            type="button"
            v-bind="partnerHelpBind('dayCounter')"
            @click.stop.prevent="partnerShowHelp('dayCounter')"
            @mousedown.stop
          >
            i
          </button>
          <p class="text-[10px] font-semibold uppercase tracking-wide text-violet-200/90">Подключились</p>
          <p class="mt-1 text-lg font-extrabold text-violet-100">{{ Number(plActivitySummary?.today?.joins || 0) }}</p>
          <p class="text-[10px] text-violet-100/75">за 24ч (все группы/каналы)</p>
          <p class="mt-0.5 text-[9px] text-violet-200/60">Период пресета: {{ partnerJoinsOverviewHint }}</p>
        </div>
        <div
          role="button"
          tabindex="0"
          class="relative cursor-pointer select-none rounded-xl border border-emerald-500/45 bg-emerald-950/30 p-3 pt-9 text-left shadow-[0_0_18px_-8px_rgba(16,185,129,0.55)] outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60"
          @click="openPartnerEventsModal"
          @keydown.enter.prevent="openPartnerEventsModal"
          @keydown.space.prevent="openPartnerEventsModal"
        >
          <button
            type="button"
            v-bind="partnerHelpBind('journal')"
            @click.stop.prevent="partnerShowHelp('journal')"
            @mousedown.stop
          >
            i
          </button>
          <p class="text-[10px] font-semibold uppercase tracking-wide text-emerald-200/90">За 24ч удалений</p>
          <p class="mt-1 text-lg font-extrabold text-emerald-100">{{ Number(plActivitySummary?.today?.deleted || 0) }}</p>
          <p class="text-[10px] text-emerald-100/75">последние события и действия</p>
        </div>
        <div
          role="button"
          tabindex="0"
          class="relative cursor-pointer select-none rounded-xl border border-fuchsia-400/45 bg-fuchsia-900/25 p-3 pt-9 text-left shadow-[0_0_18px_-8px_rgba(217,70,239,0.55)] outline-none focus-visible:ring-2 focus-visible:ring-fuchsia-400/60"
          @click="showPartnerSpendModal = true"
          @keydown.enter.prevent="showPartnerSpendModal = true"
          @keydown.space.prevent="showPartnerSpendModal = true"
        >
          <button
            type="button"
            v-bind="partnerHelpBind('spend')"
            @click.stop.prevent="partnerShowHelp('spend')"
            @mousedown.stop
          >
            i
          </button>
          <p class="text-[10px] font-semibold uppercase tracking-wide text-fuchsia-200/90">Расходы</p>
          <p class="mt-1 text-lg font-extrabold text-fuchsia-100">
            {{ Number(meAdminProfile?.broadcast_spend_tokens || 0) }} ⚡
          </p>
          <p class="text-[10px] text-fuchsia-100/75">на рассылки и автопост</p>
        </div>
        <div class="col-span-2 rounded-xl border border-cyan-500/40 bg-slate-950/88 p-2.5 shadow-inner ring-1 ring-cyan-900/50 backdrop-blur-sm">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-cyan-200">Сводка владельца групп</p>
          <p class="mt-0.5 text-[11px] text-slate-300">
            Короткие отчёты в личку по всем вашим подключённым группам/каналам: сколько подключились и сколько сейчас участников.
          </p>
          <div class="mt-2 flex flex-wrap gap-1.5">
            <button
              v-for="p in OWNER_JOIN_REPORT_PRESETS"
              :key="`owner-jr-${p.id}`"
              type="button"
              class="rounded-md px-2 py-1 text-[10px] font-semibold"
              :class="(ownerJoinReportPeriods || []).includes(p.id) ? 'bg-cyan-600 text-white' : 'bg-slate-700 text-slate-200'"
              @click="toggleOwnerJoinReportPreset(p.id)"
            >
              {{ p.label }}
            </button>
            <button
              type="button"
              class="rounded-md bg-emerald-700 px-2 py-1 text-[10px] font-semibold text-white disabled:opacity-60"
              :disabled="ownerJoinReportSaving"
              @click="saveOwnerJoinReportSettings"
            >
              Сохранить отчёты
            </button>
            <button
              type="button"
              class="rounded-md bg-indigo-700 px-2 py-1 text-[10px] font-semibold text-white"
              @click="openPartnerHourlyModal"
            >
              Активность по часам
            </button>
          </div>
      </div>
      </template>
      <template v-else>
      <p class="col-span-2 text-center text-[11px] text-slate-500 dark:text-slate-400">
        Всего пользователей в базе: <span class="font-semibold text-slate-700 dark:text-slate-200">{{ data.users_total }}</span>
      </p>
      <button type="button" class="rounded-xl border border-slate-200 bg-white p-3 text-left dark:border-slate-700 dark:bg-slate-800" @click="tab = 'users'">
        <p class="text-xs text-slate-500 dark:text-slate-400">Пользователей</p>
        <p class="mt-1 text-xl font-bold text-slate-900 dark:text-white">{{ data.users_total }}</p>
      </button>
      <button type="button" class="rounded-xl border border-slate-200 bg-white p-3 text-left dark:border-slate-700 dark:bg-slate-800" @click="tab = 'chats'">
        <p class="text-xs text-slate-500 dark:text-slate-400">Чатов</p>
        <p class="mt-1 text-xl font-bold text-slate-900 dark:text-white">{{ data.chats_total }}</p>
      </button>
      <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <p class="text-xs text-slate-500 dark:text-slate-400">Успешных оплат</p>
        <p class="mt-1 text-xl font-bold text-slate-900 dark:text-white">{{ data.payments_succeeded }}</p>
      </div>
      <button type="button" class="rounded-xl border border-slate-200 bg-white p-3 text-left dark:border-slate-700 dark:bg-slate-800" @click="tab = 'revenue'">
        <p class="text-xs text-slate-500 dark:text-slate-400">Выручка (RUB)</p>
        <p class="mt-1 text-xl font-bold text-slate-900 dark:text-white">{{ data.revenue_total_rub }}</p>
      </button>
      <button type="button" class="col-span-2 rounded-xl border border-slate-200 bg-white p-3 text-left dark:border-slate-700 dark:bg-slate-800" @click="tab = 'funnel'">
        <p class="text-xs text-slate-500 dark:text-slate-400">Платящих рефералов</p>
        <p class="mt-1 text-xl font-bold text-slate-900 dark:text-white">{{ data.referral_paid_users }}</p>
      </button>
      <div class="col-span-2 rounded-xl border border-fuchsia-400/40 bg-fuchsia-500/10 p-3">
        <p class="text-xs font-semibold text-fuchsia-700 dark:text-fuchsia-300">Мой заработок по партнерке</p>
        <p class="mt-1 text-xl font-extrabold text-fuchsia-800 dark:text-fuchsia-200">{{ myPartnerStats.total_rub || 0 }} ₽</p>
        <p class="mt-1 text-xs text-slate-600 dark:text-slate-300">
          Доступно: {{ myPartnerStats.available_rub || 0 }} ₽ · Уже выплачено: {{ myPartnerStats.paid_rub || 0 }} ₽
        </p>
        <p class="mt-1 text-[11px] text-slate-600 dark:text-slate-300">
          1д: {{ myPartnerStats.periods_rub?.['1d'] || 0 }} ₽ · 7д: {{ myPartnerStats.periods_rub?.['7d'] || 0 }} ₽ · 14д: {{ myPartnerStats.periods_rub?.['14d'] || 0 }} ₽
        </p>
        <p class="mt-0.5 text-[11px] text-slate-600 dark:text-slate-300">
          30д: {{ myPartnerStats.periods_rub?.['30d'] || 0 }} ₽ · 6м: {{ myPartnerStats.periods_rub?.['180d'] || 0 }} ₽ · 1г: {{ myPartnerStats.periods_rub?.['365d'] || 0 }} ₽
        </p>
        <div v-if="(myPartnerStats.by_month || []).length" class="mt-2 rounded-lg border border-fuchsia-300/30 bg-fuchsia-500/5 p-2">
          <p class="text-[11px] font-semibold text-fuchsia-700 dark:text-fuchsia-300">Помесячно (12 мес):</p>
          <div class="mt-1 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-slate-700 dark:text-slate-300">
            <div v-for="m in myPartnerStats.by_month" :key="`mypm-${m.month}`" class="flex items-center justify-between gap-2">
              <span>{{ m.month }}</span>
              <span class="font-semibold">{{ m.amount_rub }} ₽</span>
            </div>
          </div>
        </div>
      </div>
      </template>
    </div>
    <div v-else-if="showFullAdminShell && tab === 'payouts'" class="space-y-2">
      <div class="sticky top-0 z-10 space-y-2 rounded-xl bg-slate-950/90 p-1.5 backdrop-blur">
        <div class="rounded-xl border border-lime-400/40 bg-lime-500/10 p-3">
          <p class="text-xs font-semibold text-lime-700 dark:text-lime-300">К следующему понедельнику ({{ nextMondayLabel() }}) отложить:</p>
          <p class="mt-1 text-xl font-extrabold text-lime-800 dark:text-lime-200">{{ commissionsSummary.reserve_for_next_payout_rub }} ₽</p>
          <p class="mt-1 text-xs text-slate-600 dark:text-slate-300">
            Ожидает разблокировки: {{ commissionsSummary.pending_rub }} ₽ · Доступно сейчас: {{ commissionsSummary.available_rub }} ₽
          </p>
        </div>
        <div class="rounded-xl border border-sky-400/40 bg-sky-500/10 p-3">
          <p class="text-xs font-semibold text-sky-700 dark:text-sky-300">Заявки принимаются до понедельника, выплата — в следующий понедельник:</p>
          <p class="mt-1 text-xl font-extrabold text-sky-800 dark:text-sky-200">{{ payoutRequestsSummary.usersCount }} чел. · {{ payoutRequestsSummary.totalAmountRub }} ₽</p>
          <p class="mt-1 text-xs text-slate-600 dark:text-slate-300">Заявок: {{ payoutRequestsSummary.requestsCount }}</p>
        </div>
      </div>
      <div class="flex items-center justify-end">
        <button
          type="button"
          class="mr-2 inline-flex h-7 items-center justify-center rounded-md border border-emerald-300 bg-emerald-100 px-2 text-[11px] font-bold text-emerald-800 dark:border-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200"
          aria-label="Обновить выплаты"
          @click="refreshPayoutsNow"
        >
          Обновить
        </button>
        <button
          type="button"
          class="mr-2 inline-flex h-7 items-center justify-center rounded-md border border-slate-300 px-2 text-xs font-bold text-slate-700 dark:border-slate-600 dark:text-slate-200"
          aria-label="Фильтр по дате"
          @click="showDateFilter = !showDateFilter"
        >
          📅
        </button>
        <button
          type="button"
          class="inline-flex h-7 min-w-7 items-center justify-center rounded-full border border-sky-300 bg-sky-100 px-2 text-xs font-extrabold text-sky-800 dark:border-sky-700 dark:bg-sky-900/30 dark:text-sky-200"
          aria-label="Инструкция по выплатам"
          @click="showPayoutHelp = true"
        >
          i
        </button>
      </div>
      <div v-if="showDateFilter" class="grid grid-cols-2 gap-2 rounded-2xl border border-cyan-400/35 bg-gradient-to-br from-slate-900/95 to-slate-800/95 p-2.5 shadow-[0_0_0_1px_rgba(34,211,238,0.08)]">
        <label class="text-xs text-slate-600 dark:text-slate-300">
          <span class="font-semibold uppercase tracking-wide text-cyan-200">с</span>
          <input v-model="dateFrom" type="date" class="mt-1 w-full rounded-xl border border-cyan-400/30 bg-slate-950/70 px-2.5 py-2 text-xs font-semibold text-cyan-100 outline-none transition focus:border-cyan-300">
        </label>
        <label class="text-xs text-slate-600 dark:text-slate-300">
          <span class="font-semibold uppercase tracking-wide text-cyan-200">по</span>
          <input v-model="dateTo" type="date" class="mt-1 w-full rounded-xl border border-cyan-400/30 bg-slate-950/70 px-2.5 py-2 text-xs font-semibold text-cyan-100 outline-none transition focus:border-cyan-300">
        </label>
      </div>
      <div class="grid grid-cols-[1fr_auto] gap-2">
        <input v-model="payoutSearch" type="text" placeholder="Поиск: имя / @username / telegram id / #заявки" class="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100">
        <button type="button" class="rounded-xl px-3 py-2 text-xs font-semibold" :class="payoutsOnlyPaid ? 'bg-emerald-500 text-white' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="payoutsOnlyPaid = !payoutsOnlyPaid">
          {{ payoutsOnlyPaid ? 'Только оплаченные: ON' : 'Только оплаченные' }}
        </button>
      </div>
      <div v-if="filteredPayouts.length === 0" class="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
        Заявок на вывод пока нет.
      </div>
      <div v-for="item in filteredPayouts" :key="item.id" class="rounded-xl border p-3 transition-colors" :class="payoutCardClass(item.status)">
        <p class="text-xs text-slate-500 dark:text-slate-400">{{ item.created_at }} · #{{ item.id }} · @{{ item.username || item.telegram_id }}</p>
        <p class="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{{ item.amount_rub }} ₽ · {{ item.method }} · {{ payoutStatusLabel(item.status) }}</p>
        <p class="text-xs text-slate-600 dark:text-slate-300">Реквизиты: {{ item.requisites }}</p>
        <p v-if="item.paid_at" class="mt-1 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
          Оплачено админом: {{ item.paid_at }}
        </p>
        <p class="mt-1 text-xs text-slate-600 dark:text-slate-300">
          Доступно сейчас: {{ item.available_rub_now }} ₽ · Всего комиссия: {{ item.commission_total_rub }} ₽
        </p>
        <p v-if="item.requisites_users_count > 1" class="mt-1 text-xs font-semibold text-amber-600 dark:text-amber-300">
          ⚠️ Эти реквизиты встречаются у {{ item.requisites_users_count }} пользователей
        </p>
        <p v-if="item.risk_flag" class="mt-1 text-xs font-semibold text-rose-600 dark:text-rose-300">Риск: {{ item.risk_note || 'требует проверки' }}</p>
        <div class="mt-2 flex flex-wrap gap-1.5">
          <button
            type="button"
            class="guard-green-soft rounded-lg px-2 py-1 text-xs font-semibold text-white disabled:opacity-60"
            :disabled="actionLoadingId === item.id || String(item.status || '').toLowerCase() === 'paid'"
            @click="setPayoutStatus(item, 'paid')"
          >
            {{ String(item.status || '').toLowerCase() === 'paid' ? 'Выплачено ✓' : 'Выплатить' }}
          </button>
          <button type="button" class="rounded-lg bg-rose-500 px-2 py-1 text-xs font-semibold text-white disabled:opacity-60" :disabled="actionLoadingId === item.id" @click="setPayoutStatus(item, 'rejected')">Отклонить</button>
        </div>
      </div>
    </div>
    <div v-else-if="tab === 'referrals' && isPremiumCabinet" class="space-y-2">
      <div v-if="isPremiumCabinet" class="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <div class="rounded-xl border border-fuchsia-500/45 bg-gradient-to-br from-fuchsia-950/80 to-purple-900/50 p-3 text-center shadow-[0_0_20px_-8px_rgba(217,70,239,0.45)]">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-fuchsia-200/90">Всего с партнёрки</p>
          <p class="mt-1 text-lg font-extrabold text-fuchsia-100">{{ myPartnerStats.total_rub || 0 }} ₽</p>
        </div>
        <div class="rounded-xl border border-emerald-500/45 bg-gradient-to-br from-emerald-950/80 to-teal-900/50 p-3 text-center">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-emerald-200/90">Доступно</p>
          <p class="mt-1 text-lg font-extrabold text-emerald-100">{{ myPartnerStats.available_rub || 0 }} ₽</p>
        </div>
        <div class="rounded-xl border border-amber-500/45 bg-gradient-to-br from-amber-950/70 to-orange-900/45 p-3 text-center sm:col-span-1 col-span-2">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-amber-200/90">Ожидает разблокировки</p>
          <p class="mt-0.5 px-1 text-[9px] leading-tight text-amber-200/70">комиссии до ~7 дней после оплаты реферала</p>
          <p class="mt-1 text-lg font-extrabold text-amber-100">{{ myPartnerStats.pending_rub || 0 }} ₽</p>
        </div>
        <div class="rounded-xl border border-sky-500/45 bg-gradient-to-br from-sky-950/80 to-blue-900/50 p-3 text-center">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-sky-200/90">Выплачено</p>
          <p class="mt-1 text-lg font-extrabold text-sky-100">{{ myPartnerStats.paid_rub || 0 }} ₽</p>
        </div>
        <div class="col-span-2 rounded-xl border border-lime-500/40 bg-lime-950/25 p-2 sm:col-span-2">
          <p class="text-center text-[10px] font-semibold text-lime-200/90">За периоды (начислено)</p>
          <div class="mt-1 flex flex-wrap justify-center gap-x-3 gap-y-1 text-[11px] font-semibold text-lime-50/95">
            <span>1д: {{ myPartnerStats.periods_rub?.['1d'] || 0 }} ₽</span>
            <span>7д: {{ myPartnerStats.periods_rub?.['7d'] || 0 }} ₽</span>
            <span>30д: {{ myPartnerStats.periods_rub?.['30d'] || 0 }} ₽</span>
          </div>
        </div>
      </div>
      <div class="grid grid-cols-3 gap-2">
        <div class="rounded-xl border border-cyan-400/40 bg-cyan-500/10 px-2 py-1.5 text-center text-[11px] font-semibold text-cyan-700 dark:text-cyan-200">
          Переслали: {{ referralInfo?.share_count || 0 }}
        </div>
        <div class="rounded-xl border border-indigo-400/35 bg-indigo-500/10 px-2 py-1.5 text-center text-[11px] font-semibold text-indigo-700 dark:text-indigo-200">
          Старт: {{ referralInfo?.start_count || 0 }}
        </div>
        <div class="rounded-xl border border-lime-400/45 bg-lime-500/15 px-2 py-1.5 text-center text-[11px] font-bold text-lime-700 dark:text-lime-200">
          Оплатили: {{ referralInfo?.paid_count || 0 }}
        </div>
      </div>
      <div v-if="referralsTop.length === 0" class="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
        Оплативших рефералов пока нет.
      </div>
      <div v-for="(item, idx) in referralsTop" :key="`rt-${idx}-${item.telegram_id}`" class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <p class="text-sm font-semibold text-slate-900 dark:text-white">
          {{ item.first_name || 'Пользователь' }}
          <span v-if="item.username" class="ml-1 text-xs font-medium text-cyan-600 dark:text-cyan-300">@{{ item.username }}</span>
        </p>
        <p class="text-xs text-slate-600 dark:text-slate-300">
          Оплат: {{ item.payments_count || 0 }} · Продаж: {{ item.sales_rub || 0 }} ₽ · Начисление: {{ item.partner_reward_rub || 0 }} ₽
        </p>
      </div>
    </div>
    <div v-else-if="showFullAdminShell && tab === 'commissions'" class="space-y-2">
      <div class="rounded-xl border border-lime-400/40 bg-lime-500/10 p-3">
        <p class="text-xs font-semibold text-lime-700 dark:text-lime-300">К следующему понедельнику ({{ nextMondayLabel() }}) отложить:</p>
        <p class="mt-1 text-2xl font-extrabold text-lime-800 dark:text-lime-200">{{ commissionsSummary.reserve_for_next_payout_rub }} ₽</p>
        <p class="mt-1 text-xs text-slate-600 dark:text-slate-300">
          Ожидает разблокировки: {{ commissionsSummary.pending_rub }} ₽ · Доступно: {{ commissionsSummary.available_rub }} ₽ · Уже выплачено: {{ commissionsSummary.paid_rub }} ₽
        </p>
      </div>
      <div v-if="commissions.length === 0" class="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
        Начислений пока нет.
      </div>
      <div v-for="item in commissions" :key="`cm-${item.id}`" class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <p class="text-xs text-slate-500 dark:text-slate-400">{{ item.created_at }} · L{{ item.level }} · {{ item.status }}</p>
        <p class="mt-1 text-sm font-semibold text-slate-900 dark:text-white">
          +{{ item.reward_amount_rub }} ₽ ({{ Math.round((item.rate || 0) * 100) }}%) · продажа {{ item.sales_amount_rub }} ₽
        </p>
        <p class="text-xs text-cyan-700 dark:text-cyan-300">
          <a
            v-if="item.owner_username"
            :href="`https://t.me/${String(item.owner_username).replace(/^@+/, '')}`"
            target="_blank"
            rel="noopener noreferrer"
            class="underline decoration-cyan-500/40 hover:text-cyan-500"
            @click="openExternalFromAnchor($event, `https://t.me/${String(item.owner_username).replace(/^@+/, '')}`)"
          >@{{ String(item.owner_username).replace(/^@+/, '') }}</a>
          <span v-else>{{ item.owner_name || '—' }}</span>
        </p>
      </div>
    </div>
    <div v-else-if="showFullAdminShell && tab === 'users'" class="space-y-2">
      <p v-if="data" class="text-center text-xs text-slate-600 dark:text-slate-400">
        В базе: <b>{{ data.users_total }}</b> · в списке ниже: <b>{{ filteredAdminUsers.length }}</b> (до 1000 записей)
      </p>
      <div class="flex flex-wrap gap-1.5">
        <button type="button" class="rounded-md px-2 py-1 text-[11px] font-semibold" :class="usersPreset === 'all' ? 'bg-cyan-600 text-white' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="usersPreset = 'all'">Все</button>
        <button type="button" class="rounded-md px-2 py-1 text-[11px] font-semibold" :class="usersPreset === 'today' ? 'bg-cyan-600 text-white' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="usersPreset = 'today'">Сегодня подключились</button>
        <button type="button" class="rounded-md px-2 py-1 text-[11px] font-semibold" :class="usersPreset === 'joins24' ? 'bg-cyan-600 text-white' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="usersPreset = 'joins24'">Есть входы 24ч</button>
        <button type="button" class="rounded-md px-2 py-1 text-[11px] font-semibold" :class="usersPreset === 'promo' ? 'bg-cyan-600 text-white' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="usersPreset = 'promo'">С промокодом</button>
        <button type="button" class="rounded-md px-2 py-1 text-[11px] font-semibold" :class="usersPreset === 'antiurl' ? 'bg-cyan-600 text-white' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="usersPreset = 'antiurl'">АнтиURL включен</button>
        <button type="button" class="rounded-md px-2 py-1 text-[11px] font-semibold" :class="usersPreset === 'online' ? 'bg-cyan-600 text-white' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="usersPreset = 'online'">Онлайн в панели</button>
        <button type="button" class="rounded-md px-2 py-1 text-[11px] font-semibold" :class="usersPreset === 'blocked' ? 'bg-cyan-600 text-white' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="usersPreset = 'blocked'">Заблокированные</button>
      </div>
      <div v-if="filteredAdminUsers.length === 0" class="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
        Пользователей пока нет.
      </div>
      <div
        v-for="u in filteredAdminUsers"
        :id="'admin-user-card-' + u.telegram_id"
        :key="`u-${u.telegram_id}`"
        class="rounded-2xl border border-cyan-400/22 bg-gradient-to-b from-slate-900/90 via-slate-950/92 to-black/90 p-3 text-slate-100 shadow-[0_18px_60px_-28px_rgba(0,0,0,0.95),inset_0_1px_0_rgba(255,255,255,0.1)] ring-1 ring-cyan-300/20 backdrop-blur-xl transition-shadow"
        :class="Number(usersHighlightTelegramId) === Number(u.telegram_id) ? 'ring-2 ring-cyan-500/70 shadow-md dark:ring-cyan-400/50' : ''"
      >
        <p class="text-sm font-semibold text-white">
          {{ u.first_name || 'Пользователь' }}
          <a
            v-if="u.username"
            :href="profileLinkForUser(u)"
            target="_blank"
            rel="noopener noreferrer"
            class="ml-1 text-xs font-semibold text-cyan-300 underline decoration-cyan-400/50 underline-offset-2 hover:text-cyan-200"
            @click="openExternalFromAnchor($event, profileLinkForUser(u))"
          >@{{ String(u.username).replace(/^@+/, '') }}</a>
          <span class="ml-1 text-xs text-slate-400">ID {{ u.telegram_id }}</span>
          <span
            v-if="u.status === 'blocked'"
            class="ml-1 rounded bg-red-500/20 px-1.5 py-0.5 text-[10px] font-bold uppercase text-red-300"
          >заблокирован</span>
          <span
            v-else-if="u.in_global_antispam"
            class="ml-1 rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-bold uppercase text-amber-200"
          >глоб. антиспам</span>
        </p>
        <div class="mt-1 flex flex-wrap items-center gap-1.5 text-[10px]">
          <span class="rounded-full border border-cyan-300/30 bg-cyan-500/12 px-2 py-0.5 text-cyan-100">Тариф: {{ u.tariff }}</span>
          <span class="rounded-full border border-emerald-300/30 bg-emerald-500/12 px-2 py-0.5 text-emerald-100">Свои: {{ u.chat_count ?? 0 }}</span>
          <span class="rounded-full border border-violet-300/30 bg-violet-500/12 px-2 py-0.5 text-violet-100">Делег.: {{ u.delegated_chat_count ?? 0 }}</span>
          <span class="rounded-full border border-white/20 bg-white/10 px-2 py-0.5 text-slate-200">{{ userOnlineState(u.last_webapp_seen_at).label }}</span>
        </div>
        <div class="mt-2">
          <div class="flex flex-wrap gap-2">
            <button type="button" class="rounded-lg border border-cyan-300/35 bg-cyan-500/15 px-3 py-1.5 text-xs font-semibold text-cyan-100 hover:bg-cyan-500/25" @click="openAdminUserInfo(u)">Инфо</button>
            <a :href="profileLinkForUser(u) || '#'" target="_blank" rel="noopener noreferrer" class="rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-semibold text-white" :class="!profileLinkForUser(u) ? 'pointer-events-none opacity-60' : ''" @click="openExternalFromAnchor($event, profileLinkForUser(u))">Профиль</a>
            <button type="button" class="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white" @click="chatsOwnerFilter = Number(u.telegram_id || 0); tab = 'chats'">Чаты</button>
            <button type="button" class="rounded-lg bg-amber-700 px-3 py-1.5 text-xs font-semibold text-white" @click="resetUserDelegation(u)">Сброс делегирования</button>
            <button type="button" class="rounded-lg bg-orange-700 px-3 py-1.5 text-xs font-semibold text-white" @click="resetUserConnectedChats(u)">Сброс своих групп</button>
            <button type="button" class="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white" @click="resetUserFinance(u)">Сброс тарифа/токенов</button>
            <button
              v-if="u.status === 'blocked' || u.in_global_antispam"
              type="button"
              class="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white"
              @click="unblockUser(u)"
            >
              Разбанить
            </button>
            <button
              v-else
              type="button"
              class="rounded-lg bg-red-700 px-3 py-1.5 text-xs font-semibold text-white"
              @click="deleteBlockUser(u)"
            >
              Удалить+Блок
            </button>
          </div>
        </div>
      </div>
    </div>
    <div
      v-if="showFullAdminShell && tab === 'users' && showUserInfoModal && selectedAdminUser"
      class="fixed inset-0 z-[270] flex items-center justify-center bg-black/70 p-3"
      @click.self="showUserInfoModal = false"
    >
      <div class="w-full max-w-2xl rounded-2xl border border-cyan-400/22 bg-gradient-to-b from-slate-900/95 via-slate-950/95 to-black/95 p-4 text-slate-100 shadow-[0_28px_96px_-30px_rgba(0,0,0,0.95),inset_0_1px_0_rgba(255,255,255,0.1)] ring-1 ring-cyan-300/20 backdrop-blur-2xl">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-cyan-100">Пользователь — подробная информация</h3>
          <button type="button" class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10" @click="showUserInfoModal = false">✕</button>
        </div>
        <p class="text-sm font-semibold text-white">
          {{ selectedAdminUser.first_name || 'Пользователь' }}
          <span v-if="selectedAdminUser.username" class="ml-1 text-cyan-300">@{{ selectedAdminUser.username }}</span>
          <span class="ml-1 text-xs text-slate-400">ID {{ selectedAdminUser.telegram_id }}</span>
        </p>
        <p v-if="selectedUserSubscriptionLoading" class="mt-2 text-xs text-slate-400">Загрузка подписки…</p>
        <div v-else-if="selectedUserSubscriptionProfile" class="mt-3 -mx-1 max-h-[min(70vh,480px)] overflow-y-auto">
          <SubscriptionManagementPanel
            :profile="selectedUserSubscriptionProfile"
            variant="embedded"
            :read-only="true"
            :hide-embedded-hint="true"
          />
        </div>
        <div class="mt-2 space-y-1 text-[11px] text-slate-300">
          <p>AURUM: <b>{{ selectedAdminUser.aurum_tokens || 0 }} ✨</b> · Партнёрские: <b>{{ selectedAdminUser.partner_tokens }} ⚡</b></p>
          <p>Первый /start: <b>{{ fmtUserSeenAt(selectedAdminUser.first_start_at) }}</b> · Регистрация: <b>{{ fmtUserSeenAt(selectedAdminUser.created_at) }}</b></p>
          <p>В панели: <b>{{ fmtUserSeenAt(selectedAdminUser.last_webapp_seen_at) }}</b> · Статус: <b>{{ userOnlineState(selectedAdminUser.last_webapp_seen_at).label }}</b></p>
          <p>Свои группы: <b>{{ selectedAdminUser.chat_count ?? 0 }}</b> · Делегированные: <b>{{ selectedAdminUser.delegated_chat_count ?? 0 }}</b></p>
          <p>Подключились в группы: <b>{{ selectedAdminUser.joins_24h ?? 0 }}</b> за 24ч · <b>{{ selectedAdminUser.joins_30d ?? 0 }}</b> за 30д</p>
          <p>
            АнтиURL: <b>{{ selectedAdminUser.anti_url_enabled ? 'включён' : 'выключен' }}</b>
            <span v-if="Number(selectedAdminUser.anti_url_enabled_chats || 0) > 0"> · чатов с АнтиURL: {{ Number(selectedAdminUser.anti_url_enabled_chats) }}</span>
          </p>
          <p v-if="selectedAdminUser.promo_applied_code">
            Промокод: <b>{{ selectedAdminUser.promo_applied_code }}</b>
            · статус: <b>{{ selectedAdminUser.promo_is_active ? 'активен' : 'не активен' }}</b>
            <span v-if="selectedAdminUser.promo_applied_at"> · активирован: {{ fmtUserSeenAt(selectedAdminUser.promo_applied_at) }}</span>
            <span v-if="selectedAdminUser.promo_expires_at"> · действует до: {{ fmtUserSeenAt(selectedAdminUser.promo_expires_at) }}</span>
            <span v-if="Number(selectedAdminUser.promo_days_left || 0) > 0"> · осталось: {{ Number(selectedAdminUser.promo_days_left) }} дн</span>
          </p>
          <p v-else>Промокод не активирован.</p>
        </div>
      </div>
    </div>
    <div v-else-if="showFullAdminShell && tab === 'chats'" class="space-y-2">
      <div class="flex items-center justify-between gap-2">
        <p class="text-xs text-slate-500 dark:text-slate-400">
          {{ chatsOwnerFilter ? `Показаны чаты пользователя ID ${chatsOwnerFilter}` : 'Показаны все чаты' }}
        </p>
        <button v-if="chatsOwnerFilter" type="button" class="rounded-lg bg-slate-700 px-2 py-1 text-xs font-semibold text-white" @click="chatsOwnerFilter = 0">
          Сброс фильтра
        </button>
      </div>
      <div v-if="filteredChats.length === 0" class="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
        Подключенных чатов пока нет.
      </div>
      <div v-for="c in filteredChats" :key="`chat-${c.chat_id}`" class="rounded-2xl border border-cyan-400/22 bg-gradient-to-b from-slate-900/90 via-slate-950/92 to-black/90 p-3 text-slate-100 shadow-[0_18px_60px_-28px_rgba(0,0,0,0.95),inset_0_1px_0_rgba(255,255,255,0.1)] ring-1 ring-cyan-300/20 backdrop-blur-xl">
        <p class="text-sm font-semibold text-white">
          {{ c.title || ('Чат ' + c.chat_id) }}
          <span
            v-if="c.is_log_chat"
            class="ml-1 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-bold uppercase text-amber-800 dark:text-amber-200"
          >чат отчётов</span>
        </p>
        <p class="mt-1 text-xs text-slate-300">
          ID {{ c.chat_id }} · owner:
          <a
            v-if="c.owner_username"
            :href="`https://t.me/${String(c.owner_username).replace(/^@+/, '')}`"
            target="_blank"
            rel="noopener noreferrer"
            class="font-medium text-cyan-300 underline decoration-cyan-500/40 hover:text-cyan-200"
            @click="openExternalFromAnchor($event, `https://t.me/${String(c.owner_username).replace(/^@+/, '')}`)"
          >@{{ String(c.owner_username).replace(/^@+/, '') }}</a>
          <span v-else class="font-mono">{{ c.owner_telegram_id }}</span>
        </p>
        <div class="mt-2 flex gap-2">
          <a
            :href="c.open_link || '#'"
            target="_blank"
            rel="noopener noreferrer"
            class="rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
            :class="!c.open_link ? 'pointer-events-none opacity-60' : ''"
            @click="openExternalFromAnchor($event, c.open_link)"
          >
            Открыть чат
          </a>
        </div>
      </div>
    </div>
    <div v-else-if="showFullAdminShell && tab === 'revenue'" class="space-y-2">
      <div class="flex flex-wrap items-center gap-2">
        <button v-for="p in ['7d', '30d', '90d', '12m']" :key="`rp-${p}`" type="button" class="rounded-lg px-2.5 py-1.5 text-xs font-semibold" :class="revenuePeriod === p ? 'bg-emerald-500 text-white' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="revenuePeriod = p; loadRevenueStats()">
          {{ revenuePeriodLabel(p) }}
        </button>
      </div>
      <div class="grid grid-cols-2 gap-2">
        <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
          <p class="text-xs text-slate-500 dark:text-slate-400">За сегодня</p>
          <p class="mt-1 text-xl font-bold text-slate-900 dark:text-white">{{ revenueStats.today_rub }} ₽</p>
        </div>
        <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
          <p class="text-xs text-slate-500 dark:text-slate-400">За месяц</p>
          <p class="mt-1 text-xl font-bold text-slate-900 dark:text-white">{{ revenueStats.month_rub }} ₽</p>
        </div>
      </div>
      <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <p class="text-xs text-slate-500 dark:text-slate-400">Всего выручка (реально оплачено)</p>
        <p class="mt-1 text-xl font-bold text-slate-900 dark:text-white">{{ data?.revenue_total_rub || 0 }} ₽</p>
      </div>
      <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <p class="text-xs font-semibold text-slate-600 dark:text-slate-300">Диаграмма по дням (30 дней)</p>
        <div class="mt-2 h-40 overflow-hidden rounded-lg bg-slate-50 p-2 dark:bg-slate-900/50">
          <div class="flex h-full items-end gap-1">
            <div
              v-for="d in revenueStats.by_day"
              :key="`day-${d.date}`"
              class="group relative min-w-0 flex-1 rounded-t bg-emerald-500/70"
              :style="{ height: `${Math.max(4, (Number(d.amount_rub || 0) / Math.max(1, ...revenueStats.by_day.map(x => Number(x.amount_rub || 0)))) * 100)}%` }"
            >
              <span class="pointer-events-none absolute -top-6 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-slate-900 px-1.5 py-0.5 text-[10px] text-white opacity-0 transition group-hover:opacity-100">
                {{ d.amount_rub }} ₽
              </span>
            </div>
          </div>
        </div>
      </div>
      <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <p class="text-xs font-semibold text-slate-600 dark:text-slate-300">По месяцам</p>
        <div class="mt-2 space-y-1">
          <div v-for="m in revenueStats.by_month" :key="`month-${m.month}`" class="flex items-center justify-between text-xs">
            <span class="text-slate-500 dark:text-slate-400">{{ m.month }}</span>
            <span class="font-semibold text-slate-900 dark:text-slate-100">{{ m.amount_rub }} ₽ · {{ m.payments_count }} оплат</span>
          </div>
        </div>
      </div>
    </div>
    <div v-else-if="showFullAdminShell && tab === 'funnel'" class="space-y-2">
      <div v-if="referralsFunnel.length === 0" class="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
        Платящих рефералов пока нет.
      </div>
      <div v-for="item in referralsFunnel" :key="`rf-${item.telegram_id}`" class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <div class="flex items-center justify-between gap-2">
          <p class="text-sm font-semibold text-slate-900 dark:text-white">
            {{ item.first_name || 'Пользователь' }}
            <span v-if="item.username" class="ml-1 text-xs text-cyan-600 dark:text-cyan-300">@{{ item.username }}</span>
          </p>
          <button type="button" class="rounded-lg bg-cyan-600 px-2 py-1 text-xs font-semibold text-white disabled:opacity-60" :disabled="!item.dm_link" @click="openExternalLink(item.dm_link)">
            В личку
          </button>
        </div>
        <p class="mt-1 text-xs text-slate-600 dark:text-slate-300">
          Шаринг: {{ item.share_count }} · Старт: {{ item.start_count }} · Оплатили: {{ item.paid_count }} · Продажи: {{ item.sales_total_rub }} ₽
        </p>
        <p class="mt-1 text-xs text-slate-600 dark:text-slate-300">
          Воронка по уровням: L1 {{ item.downline_level_1 }} · L2 {{ item.downline_level_2 }} · L3 {{ item.downline_level_3 }}
        </p>
      </div>
    </div>
    <div v-else-if="showFullAdminShell && tab === 'test_payments'" class="space-y-3">
      <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">Тестовый магазин (админ)</p>
        <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
          Эти кнопки создают тестовые ссылки YooKassa прямо из админки.
        </p>
        <p class="mt-2 rounded-lg border border-slate-600/45 bg-slate-900/35 px-2.5 py-2 text-[11px] text-slate-300">
          По умолчанию реальные оплаты пытаются привязать карту для автосписаний.
          Если у LIVE-магазина ЮKassa recurring пока не активирован, платёж пройдет как обычный и не заблокируется.
        </p>
        <input
          v-model="testTargetTelegramId"
          type="number"
          min="1"
          step="1"
          placeholder="Telegram ID получателя (пусто = вы)"
          class="mt-2 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
        >
      </div>
      <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">Тест подписки (основные тарифы)</p>
        <div class="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
          <button
            v-for="m in testSubscriptionPlans"
            :key="`sub-${m}`"
            type="button"
            class="rounded-lg bg-cyan-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-60"
            :disabled="testPayLoading"
            @click="createAdminTestSubscription(m)"
          >
            {{ m }} мес.
          </button>
        </div>
      </div>
      <div class="rounded-xl border border-amber-200 bg-amber-50 p-3 dark:border-amber-700/40 dark:bg-amber-950/20">
        <p class="text-xs font-semibold text-amber-900 dark:text-amber-200">Тест привязки карты: 2 дня / 1 ₽</p>
        <p class="mt-1 text-[11px] text-amber-800/90 dark:text-amber-200/80">
          Создаёт платёж с сохранением payment method. Используйте для проверки флага привязки карты и напоминаний о списании.
        </p>
        <div class="mt-2 flex flex-wrap gap-2">
          <button
            type="button"
            class="rounded-lg bg-amber-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-60"
            :disabled="testPayLoading"
            @click="createAdminBindingProbe('live')"
          >
            Запустить 2д / 1₽ (LIVE)
          </button>
          <button
            type="button"
            class="rounded-lg bg-slate-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-60"
            :disabled="testPayLoading"
            @click="createAdminBindingProbe('test')"
          >
            Запустить 2д / 1₽ (TEST)
          </button>
        </div>
      </div>
      <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">Тест токенов</p>
        <div class="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
          <button
            v-for="pack in testTokenPacks"
            :key="`tok-${pack}`"
            type="button"
            class="rounded-lg bg-emerald-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-60"
            :disabled="testPayLoading"
            @click="createAdminTestTokens(pack)"
          >
            {{ pack }} ⚡
          </button>
        </div>
      </div>
    </div>
    <div v-else-if="showFullAdminShell && tab === 'ops'" class="space-y-3">
      <p class="text-center text-[10px] font-medium uppercase tracking-wide text-cyan-600/90 dark:text-cyan-300/90">
        {{ GUARD_PULSE_UI_MARKER }}
      </p>
      <div class="flex gap-2 rounded-xl border border-slate-200 bg-slate-50 p-1.5 dark:border-slate-600 dark:bg-slate-800/60">
        <div class="flex min-w-0 flex-1 flex-wrap gap-2">
          <button
            type="button"
            class="rounded-lg px-3 py-1.5 text-xs font-semibold transition"
            :class="opsInnerTab === 'pulse' ? 'bg-cyan-600 text-white shadow' : 'text-slate-600 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700'"
            @click="opsInnerTab = 'pulse'"
          >
            Мониторинг
          </button>
          <button
            type="button"
            class="rounded-lg px-3 py-1.5 text-xs font-semibold transition"
            :class="opsInnerTab === 'journal' ? 'bg-cyan-600 text-white shadow' : 'text-slate-600 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700'"
            @click="opsInnerTab = 'journal'"
          >
            Журнал сбоев
          </button>
        </div>
        <button
          type="button"
          class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-300 bg-white text-sm font-bold text-slate-600 shadow-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
          title="Подробности и подсказки"
          aria-label="Подробности Guard Pulse"
          @click="guardPulseInfoOpen = true"
        >
          ⓘ
        </button>
      </div>

      <div
        v-if="incidentSummary || incidentSummaryLoading"
        class="rounded-xl border p-3 text-xs leading-relaxed"
        :class="{
          'border-emerald-500/55 bg-emerald-500/10 text-emerald-950 dark:border-emerald-700/50 dark:bg-emerald-950/25 dark:text-emerald-100':
            !opsHealth.load_failed && incidentSummary && incidentSummary.level === 'ok',
          'border-amber-500/55 bg-amber-500/10 text-amber-950 dark:border-amber-700/45 dark:bg-amber-950/30 dark:text-amber-50':
            opsHealth.load_failed || (incidentSummary && incidentSummary.level === 'warn'),
          'border-rose-500/60 bg-rose-500/15 text-rose-950 dark:border-rose-700/50 dark:bg-rose-950/35 dark:text-rose-50':
            !opsHealth.load_failed && incidentSummary && incidentSummary.level === 'critical',
        }"
      >
        <p class="font-semibold text-slate-800 dark:text-slate-100">Пульс по пользователям (журнал за {{ (incidentSummary && incidentSummary.window_hours) || 24 }} ч)</p>
        <p v-if="opsHealth.load_failed" class="mt-1 text-slate-800 dark:text-slate-100">
          Связь со сводкой мониторинга нестабильна — уровень ниже по <b>журналу в базе</b>. Подробности — в ⓘ.
        </p>
        <template v-else-if="incidentSummary">
          <p class="mt-1 text-slate-800 dark:text-slate-100">
            Уровень:
            <b>{{
              incidentSummary.level === 'ok'
                ? 'норма (зелёный)'
                : incidentSummary.level === 'warn'
                  ? 'требует внимания (оранжевый)'
                  : 'критично (красный)'
            }}</b>
            · уникальных пользователей в журнале: <b>{{ incidentSummary.distinct_users_affected }}</b>
            · записей: <b>{{ incidentSummary.total_incidents }}</b>
          </p>
          <p v-if="incidentSummary.by_category && Object.keys(incidentSummary.by_category).length" class="mt-1 text-[11px] text-slate-600 dark:text-slate-300">
            По категориям:
            <span v-for="(count, catKey) in incidentSummary.by_category" :key="`cat-${catKey}`" class="mr-2 inline-block">
              {{ incidentCategoryLabel(catKey) }}: {{ count }}
            </span>
          </p>
          <ul v-if="(incidentSummary.lines_ru || []).length" class="mt-2 list-disc space-y-0.5 pl-4 text-slate-700 dark:text-slate-200">
            <li v-for="(ln, li) in incidentSummary.lines_ru" :key="`isl-${li}`">{{ ln }}</li>
          </ul>
        </template>
        <p v-if="incidentSummaryLoading" class="mt-1 text-slate-500">Обновление сводки…</p>
      </div>

      <div v-show="opsInnerTab === 'pulse'" class="space-y-3">
      <div class="rounded-xl border border-cyan-400/40 bg-cyan-500/10 p-3">
        <p class="text-xs font-semibold text-cyan-700 dark:text-cyan-300">Состояние серверов</p>
        <template v-if="opsHealth.load_failed">
          <p class="mt-1 text-sm text-slate-700 dark:text-slate-300">
            <b class="text-amber-800 dark:text-amber-200">Сводка не загрузилась</b> — см. ⓘ. Обновить: кнопка внизу.
          </p>
        </template>
        <template v-else>
          <p class="mt-1 text-sm text-slate-700 dark:text-slate-300">
            <b>{{ opsHealth.status === 'ok' ? 'Нормально' : 'Нужна проверка' }}</b>
            · база <b>{{ formatDbPingMs(opsHealth.db_latency_ms) }}</b>
            · API без перезапуска <b>{{ formatServerUptimeRu(opsHealth.api_uptime_sec || 0) }}</b>
          </p>
        </template>
      </div>
      <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <p class="text-xs font-semibold text-slate-600 dark:text-slate-300">Перезапуск на Railway (порядок после выкладки кода)</p>
        <p class="mt-1 text-[11px] leading-snug text-slate-500 dark:text-slate-400">
          1 → API (бэкенд), 2 → WebApp (мини-ап), 3 → бот. Сверху вниз — как обычно накатывают слои.
        </p>
        <div class="mt-2 flex flex-col gap-2">
          <button type="button" class="rounded-lg bg-amber-600 px-3 py-2.5 text-left text-xs font-semibold text-white disabled:opacity-60" :disabled="opsActionLoading === 'restart_api'" @click="runOpsAction('restart_api')">
            <span class="font-extrabold tabular-nums text-amber-100">1.</span> Перезапуск API
          </button>
          <button type="button" class="rounded-lg bg-indigo-600 px-3 py-2.5 text-left text-xs font-semibold text-white disabled:opacity-60" :disabled="opsActionLoading === 'restart_webapp'" @click="runOpsAction('restart_webapp')">
            <span class="font-extrabold tabular-nums text-indigo-100">2.</span> Перезапуск WebApp
          </button>
          <button type="button" class="rounded-lg bg-rose-600 px-3 py-2.5 text-left text-xs font-semibold text-white disabled:opacity-60" :disabled="opsActionLoading === 'restart_bot'" @click="runOpsAction('restart_bot')">
            <span class="font-extrabold tabular-nums text-rose-100">3.</span> Перезапуск бота
          </button>
        </div>
      </div>
      <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <p class="text-xs font-semibold text-slate-600 dark:text-slate-300">Оплаты по часам (сутки)</p>
        <div class="mt-2 h-32 overflow-hidden rounded-lg bg-slate-50 p-2 dark:bg-slate-900/50">
          <div class="flex h-full items-end gap-1">
            <div
              v-for="h in (opsHealth.activity_by_hour || [])"
              :key="`ops-hour-${h.hour}`"
              class="group relative min-w-0 flex-1 rounded-t bg-cyan-500/70"
              :style="{ height: `${Math.max(4, (Number(h.payments_sum_rub || 0) / Math.max(1, ...(opsHealth.activity_by_hour || []).map(x => Number(x.payments_sum_rub || 0)))) * 100)}%` }"
            >
              <span class="pointer-events-none absolute -top-6 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-slate-900 px-1.5 py-0.5 text-[10px] text-white opacity-0 transition group-hover:opacity-100">
                {{ h.payments_sum_rub }} ₽
              </span>
            </div>
          </div>
        </div>
      </div>
      <button type="button" class="w-full rounded-lg bg-cyan-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-60" :disabled="opsLoading" @click="loadOpsHealth()">
        Обновить мониторинг
      </button>
      </div>

      <div v-show="opsInnerTab === 'journal'" class="space-y-3">
        <p class="text-center text-[11px] text-slate-500 dark:text-slate-400">Что попадает в журнал — в ⓘ справа от вкладок.</p>
        <div class="flex flex-col gap-2 sm:flex-row">
          <input
            v-model="incidentSearchQuery"
            type="search"
            placeholder="Поиск: id или @username / имя из базы"
            class="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 placeholder:text-slate-400 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
            @keydown.enter.prevent="loadIncidentFeed()"
          />
          <button
            type="button"
            class="rounded-lg bg-slate-700 px-3 py-2 text-xs font-semibold text-white dark:bg-slate-600"
            :disabled="incidentFeedLoading"
            @click="loadIncidentFeed()"
          >
            Найти
          </button>
        </div>
        <button
          type="button"
          class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-800 disabled:opacity-60 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          :disabled="incidentFeedLoading"
          @click="loadIncidentFeed()"
        >
          Обновить журнал
        </button>
        <div
          v-if="!incidentFeed.length && !incidentFeedLoading"
          class="rounded-xl border border-slate-200 bg-white p-4 text-center text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-800"
        >
          Пока записей нет.
        </div>
        <div
          v-else-if="incidentFeedLoading"
          class="rounded-xl border border-slate-200 bg-white p-4 text-center text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-800"
        >
          Загрузка…
        </div>
        <ul v-else-if="incidentFeed.length" class="space-y-2">
          <li
            v-for="row in incidentFeed"
            :key="`inc-${row.id}`"
            class="rounded-xl border bg-white p-3 text-xs text-slate-700 dark:bg-slate-800 dark:text-slate-200"
            :class="{
              'border-rose-400/70 dark:border-rose-600/60': row.severity === 'critical',
              'border-amber-300/80 dark:border-amber-600/50': row.severity === 'warn',
              'border-slate-200 dark:border-slate-700': row.severity !== 'critical' && row.severity !== 'warn',
            }"
          >
            <div class="flex flex-wrap items-center gap-1.5">
              <span
                class="rounded px-1.5 py-0.5 text-[10px] font-bold uppercase"
                :class="{
                  'bg-rose-600 text-white': row.severity === 'critical',
                  'bg-amber-500 text-white': row.severity === 'warn',
                  'bg-slate-500 text-white': row.severity !== 'critical' && row.severity !== 'warn',
                }"
              >
                {{ row.severity === 'critical' ? 'красный' : row.severity === 'warn' ? 'оранж' : 'фон' }}
              </span>
              <span class="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-700 dark:bg-slate-900 dark:text-slate-200">{{
                incidentCategoryLabel(row.category)
              }}</span>
              <span v-if="row.affected_count > 0" class="text-[10px] font-semibold text-slate-600 dark:text-slate-300">
                затронуто аккаунтов: {{ row.affected_count }}
              </span>
            </div>
            <p class="mt-1 font-mono text-[10px] text-slate-500">{{ row.created_at }} · {{ row.method }} · HTTP {{ row.status_code }} · {{ row.path }}</p>
            <p class="mt-1 whitespace-pre-wrap text-slate-800 dark:text-slate-100">{{ row.summary_ru }}</p>
            <p v-if="row.detail_snippet" class="mt-1 font-mono text-[10px] text-slate-500">{{ row.detail_snippet }}</p>
            <p v-if="row.affected_telegram_ids_json && row.affected_telegram_ids_json !== '[]'" class="mt-1 font-mono text-[10px] text-slate-500">
              id: {{ row.affected_telegram_ids_json }}
            </p>
          </li>
        </ul>
      </div>

      <Teleport to="body">
        <div
          v-if="guardPulseInfoOpen"
          class="fixed inset-0 z-[200] flex items-end justify-center bg-black/50 p-3 sm:items-center"
          @click.self="guardPulseInfoOpen = false"
        >
          <div
            class="max-h-[min(85vh,560px)] w-full max-w-md overflow-y-auto rounded-2xl border border-slate-200 bg-white p-4 text-xs leading-relaxed text-slate-700 shadow-xl dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
            @click.stop
          >
            <div class="mb-3 flex items-center justify-between gap-2">
              <p class="text-sm font-bold text-slate-900 dark:text-slate-100">Подробности</p>
              <button
                type="button"
                class="rounded-lg bg-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-800 dark:bg-slate-700 dark:text-slate-100"
                @click="guardPulseInfoOpen = false"
              >
                Закрыть
              </button>
            </div>

            <section class="space-y-2 border-b border-slate-200 pb-3 dark:border-slate-600">
              <p class="font-semibold text-slate-800 dark:text-slate-100">Мониторинг</p>
              <p>
                Если сводка не открывается — чаще всего сеть, CORS или неверный адрес API у Mini App. После смены URL задайте
                <code class="rounded bg-slate-100 px-1 dark:bg-slate-800">VITE_API_BASE_URL</code> / <code class="rounded bg-slate-100 px-1 dark:bg-slate-800">GUARD_API_BASE_URL</code> на сервисе WebApp и пересоберите фронт.
              </p>
              <p>
                «База X мс» — за сколько отвечает PostgreSQL; меньше обычно лучше. «API без перезапуска» — сколько работает
                <b>именно процесс API</b>, который обрабатывает запросы Mini App (тот URL из
                <code class="rounded bg-slate-100 px-1 dark:bg-slate-800">VITE_API_BASE_URL</code> / Railway). Данные
                <b>не</b> приходят из вашего терминала: перезапуск бота или WebApp на сервере этот счётчик не обнуляет —
                только перезапуск сервиса API. В ответе есть поле <code class="rounded bg-slate-100 px-1 dark:bg-slate-800">api_boot_at</code> (момент старта этого воркера).
              </p>
              <ul v-if="(opsHealth.diagnostics || []).length" class="list-disc space-y-1 pl-4 text-slate-600 dark:text-slate-300">
                <li v-for="(d, i) in opsHealth.diagnostics" :key="`gp-info-d-${i}`">{{ d }}</li>
              </ul>
            </section>

            <section v-if="opsHealth.railway_redeploy" class="space-y-2 border-b border-slate-200 py-3 dark:border-slate-600">
              <p class="font-semibold text-slate-800 dark:text-slate-100">Railway и кнопки перезапуска</p>
              <p>
                Токен из Railway → Account → Tokens хранится в сервисе API как
                <code class="rounded bg-slate-100 px-1 dark:bg-slate-800">RAILWAY_API_TOKEN</code> или
                <code class="rounded bg-slate-100 px-1 dark:bg-slate-800">RAILWAY_TOKEN</code>. Шаги: см. файл
                <span class="font-medium">DEPLOY-RAILWAY.md</span> (раздел Guard Pulse).
              </p>
              <p>На экране кнопки идут в порядке: <b>1 — API</b>, <b>2 — WebApp</b>, <b>3 — бот</b> (сначала бэкенд, потом фронт, потом polling).</p>
              <ul class="space-y-0.5 font-mono text-[11px] text-slate-600 dark:text-slate-300">
                <li>Токен: {{ opsHealth.railway_redeploy.token_configured ? '✓ задан' : '✗ нет' }}</li>
                <li>Среда (RAILWAY_ENVIRONMENT_ID): {{ opsHealth.railway_redeploy.environment_configured ? '✓' : '✗' }}</li>
                <li>ID сервисов — бот: {{ opsHealth.railway_redeploy.service_ids?.bot ? '✓' : '✗' }}, API: {{ opsHealth.railway_redeploy.service_ids?.api ? '✓' : '✗' }}, WebApp: {{ opsHealth.railway_redeploy.service_ids?.webapp ? '✓' : '✗' }}</li>
              </ul>
            </section>

            <section class="space-y-2 pt-3">
              <p class="font-semibold text-slate-800 dark:text-slate-100">Журнал сбоев</p>
              <p>
                Сюда попадают <b>5xx</b> по API, необработанные исключения в API (если удалось связать с Telegram id из init-data), ошибки <b>бота</b> в polling и сбои <b>оплаты</b> (например, не ушло ЛС после успешной оплаты).
              </p>
              <p>Это не заметки «Замечено» в чатах и не логи авторассылки.</p>
              <p>
                При оранжевом/красном уровне владельцу может прийти ЛС с кнопкой — если заданы админские Telegram id и
                <code class="rounded bg-slate-100 px-1 dark:bg-slate-800">BOT_TOKEN</code> на сервисе API.
              </p>
              <p class="text-slate-500 dark:text-slate-400">Пустой список: либо всё стабильно, либо журнал недавно включён.</p>
            </section>
          </div>
        </div>
      </Teleport>
    </div>

    <div v-else-if="(showFullAdminShell || isPremiumCabinet) && tab === 'bad_urls'" class="space-y-3">
      <!-- Premium: только личная база URL -->
      <template v-if="isPremiumCabinet && !showFullAdminShell">
        <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
          <div class="flex items-center justify-between gap-2">
            <p class="text-sm font-semibold text-slate-900 dark:text-slate-100">Моя база URL</p>
            <button
              type="button"
              class="inline-flex h-8 min-w-8 items-center justify-center rounded-full border border-sky-300 bg-sky-100 px-2 text-sm font-extrabold text-sky-800 shadow-sm hover:bg-sky-200 dark:border-sky-700 dark:bg-sky-900/30 dark:text-sky-200 dark:hover:bg-sky-900/45"
              aria-label="Что это за функция"
              @click="showMyGlobalBadUrlInfo = !showMyGlobalBadUrlInfo"
            >
              i
            </button>
          </div>
          <div
            v-if="showMyGlobalBadUrlInfo"
            class="mt-2 rounded-xl border border-cyan-300/40 bg-cyan-50 p-3 text-xs leading-relaxed text-slate-700 dark:border-cyan-700/50 dark:bg-cyan-950/25 dark:text-slate-200"
          >
            <p><b>Твоя личная база:</b> сюда кладёшь куски ссылок, которые Guard будет ловить <b>во всех твоих чатах</b>, если в «Защите» включена проверка по глобальной базе.</p>
            <p class="mt-1">Наказание — как в настройках чата: удалить / мут / бан.</p>
          </div>
          <div class="mt-2 flex flex-col gap-2 sm:flex-row">
            <input
              v-model="newMyGlobalBadUrl"
              type="text"
              placeholder="evil.com или t.me/spam"
              class="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
              :disabled="globalBadUrlLoading"
              @keydown.enter.prevent="addMyGlobalBadUrl()"
            >
            <input
              v-model="newMyGlobalBadUrlNote"
              type="text"
              placeholder="Заметка (опционально)"
              class="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
              :disabled="globalBadUrlLoading"
            >
            <button
              type="button"
              class="shrink-0 rounded-lg bg-rose-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
              :disabled="globalBadUrlLoading || !(newMyGlobalBadUrl || '').trim()"
              @click="addMyGlobalBadUrl()"
            >
              Добавить
            </button>
          </div>
        </div>
        <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
          <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">Список ({{ globalBadUrlItems.length }})</p>
          <ul v-if="globalBadUrlItems.length" class="mt-2 max-h-72 space-y-1 overflow-y-auto">
            <li
              v-for="it in globalBadUrlItems"
              :key="`gbu-my-${it.pattern}`"
              class="flex flex-col gap-1 rounded-lg border border-slate-200 px-2 py-1.5 text-xs dark:border-slate-600 sm:flex-row sm:items-center sm:justify-between sm:gap-2"
            >
              <div class="min-w-0">
                <p class="font-mono text-slate-900 break-all dark:text-slate-100">{{ it.pattern }}</p>
                <p v-if="it.note" class="mt-0.5 break-words text-slate-500 dark:text-slate-400">{{ it.note }}</p>
              </div>
              <button
                type="button"
                class="self-end rounded-md px-2 py-0.5 text-rose-600 hover:bg-rose-500/10 hover:underline dark:text-rose-400 sm:self-auto"
                :disabled="globalBadUrlLoading"
                @click="removeMyGlobalBadUrl(it.pattern)"
              >
                удалить
              </button>
            </li>
          </ul>
          <p v-else class="mt-2 text-xs text-slate-500">Пока пусто — добавь шаблон выше.</p>
          <button
            type="button"
            class="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-700 dark:border-slate-600 dark:text-slate-200"
            :disabled="globalBadUrlLoading"
            @click="loadGlobalBadUrls()"
          >
            Обновить список
          </button>
        </div>
      </template>

      <!-- Полный админ: общая база + моя личная + чужие личные -->
      <template v-else-if="showFullAdminShell">
        <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
          <div class="flex items-center justify-between gap-2">
            <p class="text-sm font-semibold text-slate-900 dark:text-slate-100">Общая база Guard</p>
            <button
              type="button"
              class="inline-flex h-8 min-w-8 items-center justify-center rounded-full border border-sky-300 bg-sky-100 px-2 text-sm font-extrabold text-sky-800 shadow-sm hover:bg-sky-200 dark:border-sky-700 dark:bg-sky-900/30 dark:text-sky-200 dark:hover:bg-sky-900/45"
              aria-label="Что это за функция"
              @click="showGlobalBadUrlInfo = !showGlobalBadUrlInfo"
            >
              i
            </button>
          </div>
          <div
            v-if="showGlobalBadUrlInfo"
            class="mt-2 rounded-xl border border-cyan-300/40 bg-cyan-50 p-3 text-xs leading-relaxed text-slate-700 dark:border-cyan-700/50 dark:bg-cyan-950/25 dark:text-slate-200"
          >
            <p><b>Только для твоих чатов как админа:</b> эти шаблоны подмешиваются к проверке «глобальная база» <b>только там, где ты владелец Guard</b>. У других пользователей сюда не лезет.</p>
            <p class="mt-1">Наказание задаётся в «Защите» каждого чата.</p>
          </div>
          <div class="mt-2 flex flex-col gap-2 sm:flex-row">
            <input
              v-model="newGlobalBadUrl"
              type="text"
              placeholder="evil.com или t.me/spam"
              class="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
              :disabled="globalBadUrlLoading"
              @keydown.enter.prevent="addGlobalBadUrl()"
            >
            <input
              v-model="newGlobalBadUrlNote"
              type="text"
              placeholder="Заметка (опционально)"
              class="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
              :disabled="globalBadUrlLoading"
            >
            <button
              type="button"
              class="shrink-0 rounded-lg bg-rose-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
              :disabled="globalBadUrlLoading || !(newGlobalBadUrl || '').trim()"
              @click="addGlobalBadUrl()"
            >
              Добавить
            </button>
          </div>
        </div>
        <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
          <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">Общая база — список ({{ globalBadUrlSystemItems.length }})</p>
          <ul v-if="globalBadUrlSystemItems.length" class="mt-2 max-h-56 space-y-1 overflow-y-auto">
            <li
              v-for="it in globalBadUrlSystemItems"
              :key="`gbu-sys-${it.pattern}`"
              class="flex flex-col gap-1 rounded-lg border border-slate-200 px-2 py-1.5 text-xs dark:border-slate-600 sm:flex-row sm:items-center sm:justify-between sm:gap-2"
            >
              <div class="min-w-0">
                <p class="font-mono text-slate-900 break-all dark:text-slate-100">{{ it.pattern }}</p>
                <p v-if="it.note" class="mt-0.5 break-words text-slate-500 dark:text-slate-400">{{ it.note }}</p>
              </div>
              <button
                type="button"
                class="self-end rounded-md px-2 py-0.5 text-rose-600 hover:bg-rose-500/10 hover:underline dark:text-rose-400 sm:self-auto"
                :disabled="globalBadUrlLoading"
                @click="removeGlobalBadUrl(it.pattern)"
              >
                удалить
              </button>
            </li>
          </ul>
          <p v-else class="mt-2 text-xs text-slate-500">Пока пусто.</p>
        </div>

        <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
          <p class="text-sm font-semibold text-slate-900 dark:text-slate-100">Моя личная база URL</p>
          <p class="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">Как у Premium: только твои чаты, когда в «Защите» включена глобальная проверка.</p>
          <div class="mt-2 flex flex-col gap-2 sm:flex-row">
            <input
              v-model="newMyGlobalBadUrl"
              type="text"
              placeholder="evil.com или t.me/spam"
              class="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
              :disabled="globalBadUrlLoading"
              @keydown.enter.prevent="addMyGlobalBadUrl()"
            >
            <input
              v-model="newMyGlobalBadUrlNote"
              type="text"
              placeholder="Заметка (опционально)"
              class="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
              :disabled="globalBadUrlLoading"
            >
            <button
              type="button"
              class="shrink-0 rounded-lg bg-rose-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
              :disabled="globalBadUrlLoading || !(newMyGlobalBadUrl || '').trim()"
              @click="addMyGlobalBadUrl()"
            >
              Добавить
            </button>
          </div>
          <ul v-if="globalBadUrlItems.length" class="mt-2 max-h-48 space-y-1 overflow-y-auto">
            <li
              v-for="it in globalBadUrlItems"
              :key="`gbu-admin-my-${it.pattern}`"
              class="flex flex-col gap-1 rounded-lg border border-slate-200 px-2 py-1.5 text-xs dark:border-slate-600 sm:flex-row sm:items-center sm:justify-between sm:gap-2"
            >
              <div class="min-w-0">
                <p class="font-mono text-slate-900 break-all dark:text-slate-100">{{ it.pattern }}</p>
                <p v-if="it.note" class="mt-0.5 break-words text-slate-500 dark:text-slate-400">{{ it.note }}</p>
              </div>
              <button
                type="button"
                class="self-end rounded-md px-2 py-0.5 text-rose-600 hover:bg-rose-500/10 hover:underline dark:text-rose-400 sm:self-auto"
                :disabled="globalBadUrlLoading"
                @click="removeMyGlobalBadUrl(it.pattern)"
              >
                удалить
              </button>
            </li>
          </ul>
          <p v-else class="mt-2 text-xs text-slate-500">Пока пусто.</p>
        </div>

        <div v-if="globalBadUrlUserBases.length" class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
          <p class="text-sm font-semibold text-slate-900 dark:text-slate-100">Личные базы других пользователей</p>
          <div class="mt-2 max-h-64 space-y-3 overflow-y-auto pr-1">
            <div
              v-for="ub in globalBadUrlUserBases"
              :key="`ubase-${ub.owner_telegram_id}`"
              class="rounded-lg border border-slate-200 p-2 dark:border-slate-600"
            >
              <button
                type="button"
                class="w-full rounded-lg px-1 py-1.5 text-left transition hover:bg-slate-100 dark:hover:bg-slate-700/60"
                title="Открыть карточку в разделе «Пользователи»"
                @click="goToAdminUserInList(ub.owner_telegram_id)"
              >
                <span class="text-xs font-semibold text-slate-900 dark:text-slate-100">
                  {{ ub.owner_first_name || 'Пользователь' }}
                  <span v-if="ub.owner_username" class="ml-1 text-cyan-600 dark:text-cyan-300">@{{ ub.owner_username }}</span>
                  <span class="ml-1 text-[11px] font-normal text-slate-500">ID {{ ub.owner_telegram_id }}</span>
                </span>
              </button>
              <ul class="mt-1.5 space-y-1">
                <li
                  v-for="it in (ub.items || [])"
                  :key="`ubase-it-${ub.owner_telegram_id}-${it.pattern}`"
                  class="rounded-md border border-slate-200 px-2 py-1 text-[11px] dark:border-slate-700"
                >
                  <span class="font-mono text-slate-800 dark:text-slate-200">{{ it.pattern }}</span>
                  <span v-if="it.note" class="mt-0.5 block text-slate-500 dark:text-slate-400">{{ it.note }}</span>
                </li>
              </ul>
            </div>
          </div>
        </div>

        <button
          type="button"
          class="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-700 dark:border-slate-600 dark:text-slate-200"
          :disabled="globalBadUrlLoading"
          @click="loadGlobalBadUrls()"
        >
          Обновить всё
        </button>
      </template>
    </div>

    <div v-else-if="(showFullAdminShell || isPremiumCabinet) && tab === 'subscription'" class="space-y-3">
      <SubscriptionManagementPanel
        v-if="meAdminProfile"
        :profile="meAdminProfile"
        variant="embedded"
        @update:profile="applyAdminMeSubscription"
      />
      <div v-else class="rounded-xl border border-slate-600 bg-slate-900/60 p-4 text-sm text-slate-300">Загрузка профиля…</div>
    </div>

    <div v-else-if="showFullAdminShell && tab === 'insights'" class="space-y-3">
      <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <p class="text-sm font-semibold text-slate-900 dark:text-slate-100">Сводка за последние {{ insights.window_hours || 24 }} часов</p>
        <div class="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
          <div class="rounded-lg bg-slate-100 p-2 dark:bg-slate-900/70">Вступлений в группы: <b>{{ insights.group_joins_count || 0 }}</b></div>
          <div class="rounded-lg bg-slate-100 p-2 dark:bg-slate-900/70">Нажали /start: <b>{{ insights.starts_count || 0 }}</b></div>
          <div class="rounded-lg bg-slate-100 p-2 dark:bg-slate-900/70">Оплат: <b>{{ insights.payments_count || 0 }}</b></div>
          <div class="rounded-lg bg-slate-100 p-2 dark:bg-slate-900/70">Сумма оплат: <b>{{ insights.payments_sum_rub || 0 }} ₽</b></div>
          <div class="rounded-lg bg-slate-100 p-2 dark:bg-slate-900/70">Шеров рефералки: <b>{{ insights.referral_shares_count || 0 }}</b></div>
        </div>
        <p class="mt-3 text-xs font-semibold text-slate-700 dark:text-slate-300">Реферальные уровни</p>
        <div class="mt-1 space-y-1 text-xs text-slate-700 dark:text-slate-300">
          <div v-for="lvl in (insights.referral_levels || [])" :key="`lvl-${lvl.level}`" class="rounded-lg bg-slate-50 px-2 py-1 dark:bg-slate-900/60">
            L{{ lvl.level }}: оплат {{ lvl.payments_count }} · продажи {{ lvl.sales_sum_rub }} ₽ · награда {{ lvl.reward_sum_rub }} ₽
          </div>
          <div v-if="!(insights.referral_levels || []).length" class="text-slate-500">Пока нет данных по уровням.</div>
        </div>
      </div>
      <button type="button" class="w-full rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-60" :disabled="insightsLoading" @click="loadInsights()">
        Обновить сводку
      </button>
    </div>

    <div v-else-if="showFullAdminShell && tab === 'messages'" class="space-y-3">
      <div class="rounded-2xl border border-violet-400/35 bg-gradient-to-br from-slate-900 to-slate-800 p-3 text-slate-100 shadow-[0_0_24px_-10px_rgba(139,92,246,0.55)]">
        <div class="flex items-center justify-between gap-2">
          <div>
            <p class="text-sm font-semibold">Конструктор системных сообщений</p>
            <p class="mt-0.5 text-[11px] text-slate-300">Гибко: событие, окно, порог, cooldown, расписание и текст с переменными.</p>
          </div>
          <button type="button" class="rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-violet-500" @click="createMessageTemplate">+ Добавить</button>
        </div>
      </div>
      <div v-pre class="rounded-xl border border-slate-200 bg-white p-2 text-[11px] text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
        Переменные: <code>{{count}}</code> <code>{{hours}}</code> <code>{{payments_sum}}</code> <code>{{event_label}}</code> <code>{{date}}</code>
      </div>
      <div v-for="item in msgTemplates" :key="`tpl-${item.id}`" class="rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <div class="flex items-start justify-between gap-2">
          <div class="w-full space-y-1">
            <input v-model="item.title" class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-900" placeholder="Название" />
            <p class="text-[11px] text-slate-500">Ключ: {{ item.template_key }}</p>
          </div>
          <label class="flex items-center gap-1 rounded-lg border border-slate-300 px-2 py-1 text-xs text-slate-600 dark:border-slate-600 dark:text-slate-300">
            <input v-model="item.enabled" type="checkbox" />
            активно
          </label>
        </div>
        <div class="mt-2 grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-3">
          <label class="space-y-1">
            <span class="text-slate-500">Событие</span>
            <select v-model="item.event_key" class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-900">
              <option v-for="o in (msgTemplateOptions.events || [])" :key="`evt-${o.id}`" :value="o.id">{{ o.label }}</option>
            </select>
          </label>
          <label class="space-y-1">
            <span class="text-slate-500">Кому</span>
            <select v-model="item.target_kind" class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-900">
              <option v-for="o in (msgTemplateOptions.targets || [])" :key="`tgt-${o.id}`" :value="o.id">{{ o.label }}</option>
            </select>
          </label>
          <label class="space-y-1">
            <span class="text-slate-500">Окно (часы)</span>
            <input v-model="item.trigger_hours" type="number" min="1" max="168" class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-900" />
          </label>
          <label class="space-y-1">
            <span class="text-slate-500">Порог (мин. count)</span>
            <input v-model="item.min_count" type="number" min="1" class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-900" />
          </label>
          <label class="space-y-1">
            <span class="text-slate-500">Cooldown (мин)</span>
            <input v-model="item.cooldown_minutes" type="number" min="1" class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-900" />
          </label>
          <label class="space-y-1">
            <span class="text-slate-500">Время (UTC HH:MM)</span>
            <input v-model="item.schedule_time_hm" class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-900" placeholder="например 09:00" />
          </label>
          <label class="space-y-1">
            <span class="text-slate-500">Задержка (мин)</span>
            <input v-model="item.delay_minutes" type="number" min="1" class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-900" placeholder="для reminder-сюжетов" />
          </label>
          <label class="space-y-1">
            <span class="text-slate-500">parse_mode</span>
            <input v-model="item.parse_mode" class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-900" placeholder="Markdown / HTML" />
          </label>
        </div>
        <textarea v-model="item.body_text" rows="5" class="mt-2 w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs dark:border-slate-600 dark:bg-slate-900" />
        <div class="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <button type="button" class="rounded-lg bg-emerald-600 px-3 py-1.5 font-semibold text-white disabled:opacity-60" :disabled="msgTemplateSavingId === item.id" @click="saveMessageTemplate(item)">Сохранить</button>
          <button v-if="item.is_custom" type="button" class="rounded-lg bg-rose-600 px-3 py-1.5 font-semibold text-white" @click="deleteMessageTemplate(item)">Удалить</button>
        </div>
      </div>
      <button type="button" class="w-full rounded-lg bg-slate-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-60" :disabled="msgTemplatesLoading" @click="loadMessageTemplates()">
        Обновить список
      </button>
    </div>

    <div v-else-if="tab === 'broadcasts'" class="bc-broadcast-shell relative -mx-4 min-w-0 overflow-x-clip overflow-y-visible md:-mx-6">
      <div
        class="min-w-0 space-y-2.5 px-4 py-3 md:px-6 pb-[max(5.25rem,calc(5.75rem+env(safe-area-inset-bottom,0px)))] md:pb-[max(6rem,calc(6.5rem+env(safe-area-inset-bottom,0px)))]"
      >
      <div class="flex items-center justify-between gap-2 px-0.5 py-1">
        <p class="text-sm font-semibold tracking-tight text-zinc-100">Рассылка</p>
        <button
          type="button"
          class="bc-tool-btn bc-broadcast-i"
          title="Справка по рассылке"
          @click="bcShowMainHelp = true"
        >
          i
        </button>
      </div>

      <div class="rounded-2xl border border-white/[0.08] bg-gradient-to-b from-[#0f141d]/94 via-[#0c1017]/96 to-black/95 px-3 py-3 shadow-[0_18px_48px_-24px_rgba(0,0,0,0.95)] ring-1 ring-white/[0.05]">
        <p class="text-[24px] font-black leading-none tracking-tight text-white">Рассылки</p>
        <p class="mt-1 text-[12px] leading-snug text-zinc-300">Отправляйте сообщения один раз в каналы, группы или боты.</p>

        <div class="mt-3 space-y-2">
          <button
            type="button"
            class="w-full rounded-xl border border-[#3d6dff]/65 bg-gradient-to-r from-[#142a62]/92 via-[#172f6e]/92 to-[#152b5f]/92 px-3 py-2.5 text-left shadow-[0_12px_24px_-16px_rgba(49,99,255,0.75),inset_0_1px_0_rgba(255,255,255,0.12)] ring-1 ring-[#5b8dff]/25 transition active:scale-[0.995] disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="bcOpeningQuickDraft"
            @click="openQuickBroadcastDraft"
          >
            <span class="flex items-center gap-2.5">
              <span class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-blue-200/15 bg-blue-500/20 text-blue-100 shadow-[0_0_18px_-8px_rgba(56,189,248,0.8)]">
                <svg viewBox="0 0 24 24" class="h-5 w-5" fill="currentColor" aria-hidden="true">
                  <path d="M21.5 4.8 18.4 19c-.2.9-.8 1.1-1.6.7l-4.4-3.2-2.1 2c-.2.2-.4.4-.9.4l.3-4.5 8.3-7.5c.4-.3-.1-.5-.5-.2l-10.2 6.4-4.4-1.4c-.9-.3-.9-.9.2-1.3L19.9 4c.8-.3 1.5.2 1.3.8z" />
                </svg>
              </span>
              <span class="min-w-0">
                <span class="block truncate text-[18px] font-extrabold leading-tight text-white">Одноразовая рассылка</span>
                <span class="mt-0.5 block text-[12px] text-slate-200/90">Отправить один раз</span>
              </span>
            </span>
          </button>

          <button
            type="button"
            class="w-full rounded-xl border border-emerald-400/30 bg-gradient-to-r from-[#1e3f19]/92 via-[#1f4a1e]/90 to-[#183614]/92 px-3 py-2.5 text-left shadow-[0_12px_24px_-16px_rgba(34,197,94,0.7),inset_0_1px_0_rgba(255,255,255,0.11)] ring-1 ring-emerald-300/20 transition active:scale-[0.995]"
            @click="openQuickAutopost"
          >
            <span class="flex items-center gap-2.5">
              <span class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-emerald-200/15 bg-emerald-500/20 text-emerald-100 shadow-[0_0_18px_-8px_rgba(74,222,128,0.75)]">
                <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <rect x="4.4" y="5" width="15.2" height="14.8" rx="2.2" />
                  <path d="M8 8.7h5.8M8 12h8M8 15.3h4.8" />
                  <path d="M16.2 4v3.3M14.6 5.65h3.3" />
                </svg>
              </span>
              <span class="min-w-0">
                <span class="block truncate text-[18px] font-extrabold leading-tight text-white">Автокампании</span>
                <span class="mt-0.5 block text-[12px] text-slate-200/90">Создать и запустить по расписанию</span>
              </span>
            </span>
          </button>
        </div>

        <div class="mt-3 border-t border-white/[0.08] pt-3">
          <div class="flex items-center justify-between gap-2">
            <p class="text-[19px] font-black tracking-tight text-white">Последние рассылки</p>
            <button
              type="button"
              class="text-[14px] font-bold text-[#59a6ff] transition hover:text-[#7cbcff]"
              :disabled="!bcRecentBroadcasts.length"
              @click="bcShowAllRecentModal = true"
            >
              Смотреть все
            </button>
          </div>

          <div class="mt-2 space-y-2">
            <div
              v-for="item in bcRecentBroadcastsPreview"
              :key="`recent-bc-${item.id}`"
              class="rounded-xl border border-white/[0.07] bg-[#111827]/88 px-3 py-2.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] ring-1 ring-white/[0.03]"
            >
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <p class="truncate text-[15px] font-extrabold text-zinc-100">{{ item.title || ('Рассылка #' + item.id) }}</p>
                  <p class="mt-0.5 text-[11px] text-zinc-400">{{ bcRecentStatusLabel(item) }} • {{ bcRecentWhenLabel(item) }}</p>
                </div>
                <span class="text-lg leading-none text-zinc-500">›</span>
              </div>
              <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-zinc-300">
                <span>Охват <b class="text-zinc-100">{{ Number(item.recipient_total || 0) }}</b></span>
                <span>Успешно <b class="text-zinc-100">{{ Number(item.recipient_ok || 0) }}</b></span>
                <span>Ошибки <b class="text-zinc-100">{{ Number(item.recipient_fail || 0) }}</b></span>
              </div>
            </div>
            <p v-if="!bcRecentBroadcastsPreview.length" class="rounded-xl border border-white/[0.07] bg-[#111827]/80 px-3 py-2 text-[12px] text-zinc-400">
              Пока нет запусков рассылок.
            </p>
          </div>
        </div>
      </div>

      <Teleport to="body">
        <div
          v-if="bcQuickDraftModalOpen"
          class="fixed inset-0 z-[10000] flex min-h-[100dvh] min-w-0 flex-col bg-[#09090b] pt-[env(safe-area-inset-top,0px)] pb-[env(safe-area-inset-bottom,0px)]"
          @click.self="closeQuickBroadcastDraft"
        >
          <div class="flex min-h-0 w-full flex-1 flex-col overflow-y-auto overscroll-contain px-3 py-2">
            <div class="flex min-h-0 flex-1 flex-col bg-[#0b111b]/95 p-3 text-zinc-100">
          <div class="mb-2 flex items-start justify-between gap-2 pb-2">
            <div class="min-w-0 flex-1">
              <p class="truncate text-[19px] font-black text-white">Новая рассылка</p>
              <div class="mt-1.5 flex min-w-0 items-center gap-1.5">
                <input
                  v-model="bcTitle"
                  type="text"
                  class="min-w-0 flex-1 rounded-lg border border-white/10 bg-zinc-950/80 px-2.5 py-1.5 text-[13px] text-zinc-200 placeholder:text-zinc-500 focus:border-cyan-500/45 focus:outline-none focus:ring-1 focus:ring-cyan-500/25"
                  placeholder="Название черновика"
                  maxlength="255"
                  :disabled="Number(bcSavingTitleId || 0) === Number(bcSelectedId || 0) && Number(bcSelectedId || 0) > 0"
                  @keydown.enter.prevent="applyBcQuickDraftTitle"
                />
                <button
                  v-show="bcQuickTitleDirty"
                  type="button"
                  class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-emerald-500/40 bg-emerald-500/20 text-[16px] font-bold text-emerald-200 shadow-[0_0_20px_-4px_rgba(16,185,129,0.5)] transition active:scale-95 hover:border-emerald-400/55 hover:bg-emerald-500/30 disabled:opacity-50"
                  :disabled="Number(bcSavingTitleId || 0) === Number(bcSelectedId || 0) && Number(bcSelectedId || 0) > 0"
                  title="Применить название"
                  @click="applyBcQuickDraftTitle"
                >
                  ✓
                </button>
              </div>
            </div>
            <div class="flex items-center gap-1">
              <button type="button" class="rounded-lg px-2 py-1 text-[13px] font-bold text-[#70a8ff] hover:bg-white/10" :disabled="bcSaving" @click="saveBcDraft">
                Сохранить
              </button>
              <button
                type="button"
                class="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-transparent text-sm text-zinc-200 hover:bg-white/[0.08]"
                aria-label="Закрыть"
                :disabled="bcSaving"
                @click="closeQuickBroadcastDraft"
              >
                ✕
              </button>
            </div>
          </div>

          <p class="text-[12px] font-semibold text-zinc-300">Текст сообщения</p>
          <div
            ref="bcBodyRef"
            class="bc-editor mt-2 h-40 overflow-y-auto rounded-xl border border-white/[0.08] bg-zinc-950 px-3 py-2.5 text-sm leading-relaxed focus-within:border-white/20 focus-within:ring-0"
            contenteditable="true"
            @input="onBcEditorInput"
            @click="onBcEditorClick"
            @mouseup="bcUpdateFormatState"
            @keyup="bcUpdateFormatState"
          />

          <div class="mt-2 flex flex-wrap gap-1.5">
            <button type="button" class="bc-tool-btn min-w-[2.1rem] !px-2" :class="bcFormatState.bold ? 'bc-tool-active' : ''" @mousedown.prevent @click="bcFormatBold"><b>B</b></button>
            <button type="button" class="bc-tool-btn min-w-[2.1rem] !px-2" :class="bcFormatState.italic ? 'bc-tool-active' : ''" @mousedown.prevent @click="bcFormatItalic"><i>I</i></button>
            <button type="button" class="bc-tool-btn min-w-[2.1rem] !px-2" :class="bcFormatState.underline ? 'bc-tool-active' : ''" @mousedown.prevent @click="bcFormatUnderline"><u>U</u></button>
            <button type="button" class="bc-tool-btn min-w-[2.1rem] !px-2" :class="bcFormatState.strike ? 'bc-tool-active' : ''" @mousedown.prevent @click="bcFormatStrike"><s>S</s></button>
            <button type="button" class="bc-tool-btn !px-2 !text-[11px]" :class="!bcCanUndo() ? 'opacity-40' : ''" :disabled="!bcCanUndo()" @mousedown.prevent @click="bcUndo">↶</button>
            <button type="button" class="bc-tool-btn !px-2 !text-[11px]" :class="!bcCanRedo() ? 'opacity-40' : ''" :disabled="!bcCanRedo()" @mousedown.prevent @click="bcRedo">↷</button>
          </div>

          <p class="mt-1 text-[11px]" :class="bcCurrentLen() > bcCurrentMaxLen() ? 'text-rose-400' : 'text-slate-500'">
            {{ bcCurrentLen() }} / {{ bcCurrentMaxLen() }} символов
          </p>

          <div class="mt-3">
            <p class="text-[12px] font-semibold text-zinc-300">Кнопки</p>
            <div v-if="bcQuickButtonPreview.length" class="mt-1.5 space-y-1.5">
              <div
                v-for="(btn, bi) in bcQuickButtonPreview.slice(0, 3)"
                :key="`quick-bbtn-${bi}-${btn.text}`"
                class="rounded-lg border border-white/10 bg-white/[0.04] px-2.5 py-1.5"
              >
                <p class="truncate text-[12px] font-semibold text-zinc-100">{{ btn.text }}</p>
                <p v-if="btn.url" class="truncate text-[11px] text-zinc-400">{{ btn.url }}</p>
              </div>
            </div>
            <button type="button" class="bc-tool-btn mt-1.5 !text-[12px]" @click="bcAuxModal = 'keyboard'">＋ Кнопки под постом</button>
          </div>

          <div class="mt-3">
            <p class="text-[12px] font-semibold text-zinc-300">Вложения</p>
            <div v-if="bcMediaHistory.length" class="mt-1.5 flex flex-wrap gap-2">
              <div v-for="(m, mi) in bcMediaHistory.slice(0, 4)" :key="`quick-pv-${mi}-${m.id || mi}`" class="relative shrink-0">
                <button
                  v-if="m.previewUrl && (String(m.kind || '').toLowerCase().includes('photo') || String(m.kind || '').toLowerCase().includes('video') || String(m.kind || '').toLowerCase() === 'animation')"
                  type="button"
                  class="group relative block h-14 w-14 overflow-hidden rounded-lg border border-white/15 bg-slate-950/80 shadow-md ring-1 ring-white/[0.06] transition hover:border-cyan-400/35 hover:ring-cyan-400/25"
                  title="Открыть крупно"
                  @click="openBcMediaViewer(m)"
                >
                  <img
                    v-if="String(m.kind || '').toLowerCase().includes('photo')"
                    :src="m.previewUrl"
                    class="h-full w-full object-cover"
                    alt=""
                  />
                  <video
                    v-else
                    :src="m.previewUrl"
                    class="h-full w-full object-cover"
                    muted
                    playsinline
                  />
                </button>
                <div
                  v-else
                  class="flex h-14 w-14 flex-col items-center justify-center gap-0.5 rounded-lg border border-white/10 bg-slate-950/75 p-1 text-center shadow-inner ring-1 ring-white/[0.04]"
                >
                  <span class="text-base leading-none">{{ bcMediaIcon(m.kind) }}</span>
                </div>
              </div>
            </div>
            <button type="button" class="bc-tool-btn mt-1.5 !text-[12px]" @click="bcAuxModal = 'media'">📎 Файл и медиа</button>
          </div>

          <button
            type="button"
            class="mt-auto w-full rounded-xl border border-indigo-400/40 bg-gradient-to-r from-indigo-600/95 to-blue-700/95 px-4 py-2 text-[13px] font-extrabold text-white shadow-[0_14px_30px_-16px_rgba(59,130,246,0.8)] disabled:cursor-not-allowed disabled:opacity-45"
            :disabled="!bcHasMessageText()"
            @click="openSendTargetModal"
          >
            Далее
          </button>
            </div>
          </div>
        </div>
      </Teleport>

      <Teleport to="body">
        <div
          v-if="bcSendTargetModalOpen"
          class="fixed inset-0 z-[10020] flex min-h-[100dvh] min-w-0 flex-col bg-[#09090b] pt-[env(safe-area-inset-top,0px)] pb-[env(safe-area-inset-bottom,0px)]"
          @click.self="bcSendTargetModalOpen = false"
        >
          <div class="flex min-h-0 w-full flex-1 flex-col overflow-y-auto overscroll-contain px-3 py-2">
            <div class="flex min-h-0 w-full flex-1 flex-col rounded-2xl border border-white/[0.04] bg-[#0b111b]/95 p-3 text-zinc-100 shadow-[0_24px_72px_-28px_rgba(0,0,0,0.9)] ring-1 ring-white/[0.02]">
          <div class="flex items-center justify-between gap-2">
            <div class="flex min-w-0 items-center gap-1">
              <button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-transparent text-[14px] text-white/90 hover:bg-white/[0.08]" @click="bcSendTargetModalOpen = false">←</button>
              <p class="truncate text-[19px] font-black text-white">Куда отправить</p>
            </div>
            <button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-transparent text-[14px] text-white/90 hover:bg-white/[0.08]" @click="bcSendTargetModalOpen = false">✕</button>
          </div>
          <p class="mt-2 text-[13px] text-zinc-400">Выберите получателей</p>

          <div class="mt-4 space-y-2.5">
            <button
              type="button"
              class="flex w-full items-center justify-between gap-3 rounded-xl bg-white/[0.035] px-3 py-2.5 text-left"
              @click="bcSendTargetChannels = !bcSendTargetChannels"
            >
              <span class="min-w-0">
                <span class="block text-[18px] font-extrabold text-white">Каналы</span>
                <span class="block text-[12px] text-slate-200/90">Отправить в каналы</span>
              </span>
              <span class="inline-flex h-6 w-6 items-center justify-center rounded-md border text-[14px] font-black" :class="bcSendTargetChannels ? 'border-violet-300/55 bg-violet-600/85 text-white' : 'border-white/35 bg-transparent text-transparent'">✓</span>
            </button>

            <button
              type="button"
              class="flex w-full items-center justify-between gap-3 rounded-xl bg-white/[0.035] px-3 py-2.5 text-left"
              @click="bcSendTargetGroups = !bcSendTargetGroups"
            >
              <span class="min-w-0">
                <span class="block text-[18px] font-extrabold text-white">Группы</span>
                <span class="block text-[12px] text-slate-200/90">Отправить в группы</span>
              </span>
              <span class="inline-flex h-6 w-6 items-center justify-center rounded-md border text-[14px] font-black" :class="bcSendTargetGroups ? 'border-violet-300/55 bg-violet-600/85 text-white' : 'border-white/35 bg-transparent text-transparent'">✓</span>
            </button>

            <button
              type="button"
              class="flex w-full items-center justify-between gap-3 rounded-xl bg-white/[0.035] px-3 py-2.5 text-left"
              @click="bcSendTargetBots = !bcSendTargetBots"
            >
              <span class="min-w-0">
                <span class="block text-[18px] font-extrabold text-white">Боты (лички)</span>
                <span class="block text-[12px] text-slate-200/90">Отправить в боты</span>
              </span>
              <span class="inline-flex h-6 w-6 items-center justify-center rounded-md border text-[14px] font-black" :class="bcSendTargetBots ? 'border-violet-300/55 bg-violet-600/85 text-white' : 'border-white/35 bg-transparent text-transparent'">✓</span>
            </button>
          </div>

          <div class="mt-5">
            <p class="text-[13px] font-semibold text-zinc-300">Выбрано</p>
            <div class="mt-1.5 space-y-1.5">
              <button
                v-if="bcSendTargetChannels"
                type="button"
                class="flex w-full items-center justify-between rounded-xl bg-white/[0.04] px-3 py-2 text-left text-[14px] font-semibold text-zinc-100"
                @click="bcShowChannelsPicker = true"
              >
                <span>{{ `Каналы: ${Number(bcSelectedChannelIds.length || 0)}` }}</span>
                <span>›</span>
              </button>
              <button
                v-if="bcSendTargetGroups"
                type="button"
                class="flex w-full items-center justify-between rounded-xl bg-white/[0.04] px-3 py-2 text-left text-[14px] font-semibold text-zinc-100"
                @click="bcShowGroupsPicker = true"
              >
                <span>{{ `Группы: ${Number(bcSelectedGroupIds.length || 0)}` }}</span>
                <span>›</span>
              </button>
              <div v-if="bcSendTargetBots" class="rounded-xl bg-white/[0.04] px-3 py-2 text-[14px] font-semibold text-zinc-100">
                {{ `Боты (личка): ${Number(bcSelectedBotRecipientIds.length || 0)}` }}
              </div>
              <p v-if="!bcSendTargetSummary.length" class="rounded-xl bg-white/[0.03] px-3 py-2 text-[12px] text-zinc-400">Ничего не выбрано</p>
            </div>
          </div>

          <button
            type="button"
            class="mt-auto w-full rounded-xl border border-indigo-400/40 bg-gradient-to-r from-indigo-600/95 to-blue-700/95 px-4 py-2 text-[13px] font-extrabold text-white shadow-[0_14px_30px_-16px_rgba(59,130,246,0.8)] disabled:cursor-not-allowed disabled:opacity-45"
            :disabled="bcSelectedTargetsCount <= 0"
            @click="proceedSendTargetModal"
          >
            Далее
          </button>
            </div>
          </div>
        </div>
      </Teleport>

      <Teleport to="body">
      <div
        v-if="bcConfirmModalOpen"
        class="fixed inset-0 z-[10030] flex flex-col overflow-y-auto bg-[#070b12] px-1.5 pb-[max(5.75rem,calc(5.25rem+env(safe-area-inset-bottom,0px)))] pt-[max(0.25rem,calc(env(safe-area-inset-top,0px)+46px))]"
        @click.self="bcConfirmModalOpen = false"
      >
        <div
          class="mx-auto flex w-full max-w-[min(28rem,calc(100vw-0.75rem))] min-h-[calc(100dvh-7.9rem)] flex-col rounded-2xl border border-white/[0.08] bg-[#0a101a]/92 px-2.5 py-2.5 text-zinc-100 shadow-[0_22px_70px_-30px_rgba(0,0,0,0.88)]"
        >
          <div class="flex items-center gap-2">
            <button type="button" class="inline-flex h-7 w-7 items-center justify-center rounded-full bg-transparent text-[13px] text-white/90 hover:bg-white/[0.08]" @click="bcConfirmModalOpen = false">←</button>
            <p class="text-[19px] font-bold text-white leading-none">Подтверждение</p>
          </div>

          <div class="mt-3 text-center">
            <div
              class="mx-auto mb-2 flex h-[5.15rem] w-[5.15rem] items-center justify-center rounded-full border border-violet-300/22 bg-[#1a1330]/45 shadow-[0_0_22px_-8px_rgba(139,92,246,0.55)]"
            >
              <svg viewBox="0 0 24 24" class="h-9 w-9 text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.3)]" fill="currentColor" aria-hidden="true">
                <path d="M21.5 4.8 18.4 19c-.2.9-.8 1.1-1.6.7l-4.4-3.2-2.1 2c-.2.2-.4.4-.9.4l.3-4.5 8.3-7.5c.4-.3-.1-.5-.5-.2l-10.2 6.4-4.4-1.4c-.9-.3-.9-.9.2-1.3L19.9 4c.8-.3 1.5.2 1.3.8z" />
              </svg>
            </div>
            <p class="text-[18px] font-extrabold text-white leading-tight">Готово к отправке</p>
            <p class="mx-auto mt-1 max-w-[17rem] text-[13px] leading-[1.35] text-zinc-300/95">Проверьте настройки и подтвердите отправку рассылки</p>
          </div>

          <div class="mt-4 rounded-xl border border-white/[0.07] bg-white/[0.02] px-3 py-2">
            <div class="flex items-center justify-between gap-3 py-1.5 text-[13px] leading-snug">
              <span class="text-zinc-300">Получатели</span>
              <span class="text-right font-semibold text-zinc-100">{{ bcConfirmRecipientLabel }}</span>
            </div>
            <div class="flex items-center justify-between gap-3 py-1.5 text-[13px] leading-snug">
              <span class="text-zinc-300">Текст сообщения</span>
              <span class="text-right font-semibold text-zinc-100">{{ bcConfirmSymbolsLabel(bcConfirmMessageLen) }}</span>
            </div>
            <div class="flex items-center justify-between gap-3 py-1.5 text-[13px] leading-snug">
              <span class="text-zinc-300">Кнопки</span>
              <span class="text-right font-semibold text-zinc-100">{{ bcConfirmButtonsLabel(bcConfirmButtonsCount) }}</span>
            </div>
            <div class="flex items-center justify-between gap-3 py-1.5 text-[13px] leading-snug">
              <span class="text-zinc-300">Вложения</span>
              <span class="text-right font-semibold text-zinc-100">{{ bcConfirmHasMedia ? 'Есть' : 'Нет' }}</span>
            </div>
          </div>

          <div class="mt-2.5 flex items-center justify-between gap-3 rounded-xl border border-white/[0.07] bg-white/[0.02] px-3 py-2">
            <span class="text-[14px] font-semibold text-zinc-100">Стоимость</span>
            <span class="text-[15px] font-black text-amber-300">{{ bcConfirmLoading ? '...' : `${bcConfirmQuoteTokens} AURUM` }}</span>
          </div>

          <div class="mt-auto pt-4">
            <div class="flex gap-2">
              <button type="button" class="flex-1 rounded-xl border border-white/12 bg-[#171e2e]/95 px-3 py-2 text-[15px] font-semibold text-[#7590d8]" :disabled="bcConfirmSending" @click="bcConfirmModalOpen = false">Отмена</button>
              <button type="button" class="flex-1 rounded-xl border border-indigo-400/45 bg-gradient-to-r from-[#6d3ef7] to-[#4b67ff] px-3 py-2 text-[15px] font-extrabold text-white" :disabled="bcConfirmSending || bcConfirmLoading" @click="submitBcConfirmedSend">{{ bcConfirmSending ? 'Отправка...' : 'Отправить' }}</button>
            </div>
          </div>
        </div>
      </div>
      </Teleport>

      <div
        v-if="bcShowAllRecentModal"
        class="fixed inset-0 z-[320] flex items-end justify-center bg-black/75 px-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] pt-[max(12px,calc(env(safe-area-inset-top,0px)+48px))] md:items-center md:pb-6"
        @click.self="bcShowAllRecentModal = false"
      >
        <div class="w-full max-w-lg rounded-2xl border border-white/12 bg-[#0b111b]/96 p-3 text-zinc-100 shadow-[0_24px_64px_-24px_rgba(0,0,0,0.92)]">
          <div class="mb-2 flex items-center justify-between border-b border-white/10 pb-2">
            <p class="text-[16px] font-extrabold text-white">Все последние рассылки</p>
            <button type="button" class="rounded-lg px-2 py-1 text-sm text-zinc-300 hover:bg-white/10" @click="bcShowAllRecentModal = false">✕</button>
          </div>
          <div class="max-h-[min(70vh,30rem)] space-y-2 overflow-y-auto pr-1">
            <div
              v-for="item in bcRecentBroadcasts"
              :key="`recent-all-bc-${item.id}`"
              class="rounded-xl border border-white/[0.08] bg-[#121a27]/88 px-3 py-2.5"
            >
              <p class="truncate text-[14px] font-bold text-zinc-100">{{ item.title || ('Рассылка #' + item.id) }}</p>
              <p class="mt-0.5 text-[11px] text-zinc-400">{{ bcRecentStatusLabel(item) }} • {{ bcRecentWhenLabel(item) }}</p>
              <div class="mt-1.5 flex flex-wrap items-center gap-3 text-[11px] text-zinc-300">
                <span>Охват <b class="text-zinc-100">{{ Number(item.recipient_total || 0) }}</b></span>
                <span>Успешно <b class="text-zinc-100">{{ Number(item.recipient_ok || 0) }}</b></span>
                <span>Ошибки <b class="text-zinc-100">{{ Number(item.recipient_fail || 0) }}</b></span>
              </div>
            </div>
            <p v-if="!bcRecentBroadcasts.length" class="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-[12px] text-zinc-400">
              Пока нет запусков рассылок.
            </p>
          </div>
        </div>
      </div>

      <div
        v-if="cabinetMode === 'delegated'"
        class="rounded-lg bg-zinc-950/45 px-2.5 py-1.5 text-[11px] text-zinc-300 ring-1 ring-white/[0.05] backdrop-blur-md"
      >
        Фиолетовый ADM: рассылка и автопост только по делегированным группам/каналам.
      </div>

      <div
        v-if="bcBroadcastCanScopeAll && showFullAdminShell"
        class="flex flex-wrap items-center gap-2 rounded-lg bg-zinc-950/40 px-2.5 py-1.5 text-[11px] text-zinc-300 ring-1 ring-white/[0.05] backdrop-blur-md"
      >
        <span class="text-zinc-500">Черновики в списке:</span>
        <button
          type="button"
          class="rounded-md px-2 py-0.5 font-semibold transition"
          :class="bcBroadcastDraftListScope !== 'all' ? 'bg-violet-600/50 text-white ring-1 ring-violet-400/50' : 'text-slate-400 hover:bg-white/10'"
          @click="setBcBroadcastDraftListScope('mine')"
        >
          только мои
        </button>
        <button
          type="button"
          class="rounded-md px-2 py-0.5 font-semibold transition"
          :class="bcBroadcastDraftListScope === 'all' ? 'bg-amber-900/50 text-amber-100 ring-1 ring-amber-500/40' : 'text-slate-400 hover:bg-white/10'"
          @click="setBcBroadcastDraftListScope('all')"
        >
          все пользователи
        </button>
      </div>

      <div class="flex flex-wrap gap-1.5">
        <button
          type="button"
          class="rounded-xl border border-white/[0.1] bg-zinc-800/90 px-3 py-1.5 text-xs font-semibold text-zinc-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] ring-1 ring-white/[0.05] backdrop-blur-md transition hover:bg-zinc-700/90"
          @click="createBcDraft"
        >
          + Черновик
        </button>
        <button
          type="button"
          class="rounded-xl border border-white/[0.1] bg-zinc-900/80 px-3 py-1.5 text-xs font-semibold text-zinc-200 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] ring-1 ring-white/[0.04] backdrop-blur-md hover:bg-zinc-800/85 disabled:opacity-45"
          :disabled="!broadcasts.length"
          @click="openBroadcastStats"
        >
          Статистика
        </button>
      </div>

      <div v-if="bcLoading" class="text-sm text-slate-400">Загрузка…</div>

      <div v-else class="grid min-w-0 gap-2.5 lg:grid-cols-[minmax(0,200px)_minmax(0,1fr)]">
        <div
          class="max-h-[min(40vh,300px)] space-y-1 overflow-y-auto rounded-xl bg-zinc-950/40 p-1.5 ring-1 ring-white/[0.06] backdrop-blur-xl"
        >
          <div
            v-for="b in broadcasts"
            :key="`bc-${b.id}`"
            role="button"
            tabindex="0"
            class="bc-draft-list-card w-full cursor-pointer rounded-xl border border-white/[0.06] px-2 py-2 text-left text-xs text-zinc-200 transition"
            :class="
              bcSelectedId === b.id
                ? 'bg-zinc-800/95 shadow-[0_12px_40px_-16px_rgba(0,0,0,0.65)] ring-1 ring-white/[0.12]'
                : 'bg-zinc-900/55 hover:bg-zinc-800/75'
            "
            @click="onBcDraftCardShellClick(b)"
            @keydown.enter.prevent="onBcDraftCardShellClick(b)"
          >
            <div class="flex items-start justify-between gap-1.5">
              <div class="min-w-0 flex-1">
                <input
                  v-if="bcDraftRenameId === b.id"
                  v-model="bcDraftRenameValue"
                  type="text"
                  maxlength="255"
                  class="bc-draft-title-input w-full rounded-lg border border-white/15 bg-zinc-950/90 px-2 py-1 text-xs font-medium text-zinc-100 outline-none ring-1 ring-white/[0.06] focus:border-cyan-400/40 focus:ring-cyan-400/25"
                  placeholder="Название"
                  @click.stop
                  @keydown.enter.prevent="bcCommitDraftRename(b)"
                />
                <span v-else class="block truncate font-medium text-zinc-100">{{ b.title || 'Без названия' }}</span>
              </div>
              <div class="flex shrink-0 items-center gap-0.5">
                <button
                  v-if="bcDraftRenameId !== b.id"
                  type="button"
                  class="bc-draft-emoji-btn"
                  title="Переименовать"
                  aria-label="Переименовать"
                  @click.stop="bcStartDraftRename(b)"
                >
                  ✍️
                </button>
                <button
                  v-else
                  type="button"
                  class="bc-draft-emoji-btn"
                  title="Сохранить название"
                  aria-label="Сохранить название"
                  :disabled="bcSavingTitleId === b.id"
                  @click.stop="bcCommitDraftRename(b)"
                >
                  {{ bcSavingTitleId === b.id ? '…' : '✅' }}
                </button>
                <span
                  class="shrink-0 rounded-md border border-white/[0.08] bg-zinc-950/50 px-1.5 py-0.5 text-[10px] tracking-wide text-zinc-300"
                >
                  {{ bcStatusLabel(b.status) }}
                </span>
                <button
                  type="button"
                  class="rounded-md border border-rose-500/35 bg-rose-950/40 px-1.5 py-0.5 text-[10px] text-rose-100 hover:bg-rose-900/50"
                  title="Удалить черновик"
                  @click.stop="deleteBcDraftById(b.id)"
                >
                  🗑
                </button>
              </div>
            </div>
            <div v-if="bcBroadcastDraftListScope === 'all'" class="mt-0.5 text-[9px] text-zinc-500">
              владелец tg: {{ b.admin_telegram_id }}
            </div>
            <div class="mt-2 flex flex-wrap items-center gap-2">
              <button
                v-if="bcDraftThumbById[b.id]?.previewUrl"
                type="button"
                class="h-10 w-10 shrink-0 overflow-hidden rounded-lg border border-white/[0.1] bg-zinc-950/70 shadow-sm ring-1 ring-white/[0.04] transition hover:border-white/20"
                title="Открыть фото"
                @click.stop="openBcMediaViewer(bcDraftThumbById[b.id])"
              >
                <img
                  v-if="bcDraftThumbById[b.id].kind === 'photo'"
                  :src="bcDraftThumbById[b.id].previewUrl"
                  class="h-full w-full object-cover"
                  alt=""
                />
                <video
                  v-else
                  :src="bcDraftThumbById[b.id].previewUrl"
                  class="h-full w-full object-cover"
                  muted
                  playsinline
                />
              </button>
              <button type="button" class="bc-tool-btn !px-2 !py-1 text-[11px]" @click.stop="openBcPreview(b)">Посмотреть</button>
              <button type="button" class="bc-tool-btn !px-2 !py-1 text-[11px]" @click.stop="applyBroadcastToForm(b)">Исправить</button>
            </div>
          </div>
          <p v-if="!broadcasts.length" class="p-3 text-center text-xs text-slate-500">Черновиков пока нет</p>
        </div>

        <div v-if="bcEditorOpen && bcSelectedId" class="min-w-0 max-w-full space-y-2.5">
          <div class="flex items-center gap-2">
            <button type="button" class="bc-tool-btn" @click="bcEditorOpen = false">← Назад</button>
            <span class="text-[11px] text-slate-400">Редактирование</span>
          </div>
          <div class="rounded-xl bg-zinc-950/55 p-3 shadow-[0_20px_50px_-24px_rgba(0,0,0,0.55)] ring-1 ring-white/[0.06] backdrop-blur-xl">
            <div class="mb-1.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
              <p class="text-sm font-semibold text-zinc-100">Шаблон рассылки</p>
              <span
                class="max-w-full whitespace-nowrap text-[11px] font-medium leading-none"
                :class="bcSavedTick ? 'text-emerald-300' : 'text-amber-300'"
              >
                {{ bcSavedTick ? '✓ сохранено' : '● есть несохранённые изменения' }}
              </span>
            </div>
            <p class="truncate text-sm font-medium text-zinc-200">{{ bcTitle || 'Без названия' }}</p>

            <div ref="bcEmojiHostRef" class="mt-4 flex flex-wrap items-center gap-2 border-t border-white/[0.06] pt-4">
              <span class="text-xs font-semibold text-zinc-400">Оформление текста</span>
              <button type="button" class="bc-tool-btn bc-broadcast-i" title="Справка по оформлению" @click="bcShowFormatHelp = true">
                i
              </button>
              <div class="flex flex-wrap gap-1">
                <button type="button" class="bc-tool-btn" :class="bcFormatState.bold ? 'bc-tool-active' : ''" title="Жирный" @mousedown.prevent @click="bcFormatBold"><b>Ж</b></button>
                <button type="button" class="bc-tool-btn" :class="bcFormatState.italic ? 'bc-tool-active' : ''" title="Курсив" @mousedown.prevent @click="bcFormatItalic"><i>К</i></button>
                <button type="button" class="bc-tool-btn" :class="bcFormatState.underline ? 'bc-tool-active' : ''" title="Подчёркивание" @mousedown.prevent @click="bcFormatUnderline"><u>Ч</u></button>
                <button type="button" class="bc-tool-btn" :class="bcFormatState.strike ? 'bc-tool-active' : ''" title="Зачёркнутый" @mousedown.prevent @click="bcFormatStrike"><s>З</s></button>
                <button type="button" class="bc-tool-btn text-[11px]" :class="bcFormatState.spoiler ? 'bc-tool-active' : ''" title="Скрытый" @mousedown.prevent @click="bcFormatSpoiler">🙈 Скрытый</button>
                <button type="button" class="bc-tool-btn text-[11px]" title="Моноширинный блок" @mousedown.prevent @click="bcFormatPre">⌨ PRE</button>
                <button type="button" class="bc-tool-btn font-mono text-[11px]" title="Код" @mousedown.prevent @click="bcFormatCode">{ }</button>
                <button type="button" class="bc-tool-btn text-[11px]" :class="bcFormatState.link ? 'bc-tool-active' : ''" title="Ссылка" @mousedown.prevent @click="bcFormatLink">🔗 Ссылка</button>
                <button type="button" class="bc-tool-btn text-[11px]" title="Цитата" @mousedown.prevent @click="bcFormatBlockquote">❝ Цитата</button>
                <button type="button" class="bc-tool-btn text-[11px]" title="Убрать форматирование" @mousedown.prevent @click="bcClearFormatting">✕ Сбросить все</button>
                <button
                  type="button"
                  class="bc-tool-btn text-[11px]"
                  :class="bcEmojiOpen ? 'bg-violet-600/40 ring-1 ring-violet-400' : ''"
                  @click="bcToggleEmojiOpen"
                >
                  😀 Смайлы
                </button>
              </div>
              <div v-show="bcEmojiOpen" class="bc-emoji-popover mt-3 w-full">
              <emoji-picker
                v-if="bcEmojiPickerReady"
                class="bc-emoji-picker"
                @emoji-click="onBcEmojiClick"
              />
              <p v-else class="p-4 text-center text-xs text-slate-500">Загрузка смайликов…</p>
            </div>
            </div>
            <div class="mt-2 flex flex-wrap gap-1.5">
              <button type="button" class="bc-tool-btn text-[11px]" @click="bcAuxModal = 'keyboard'">＋ Кнопки под постом</button>
              <button type="button" class="bc-tool-btn text-[11px]" @click="bcAuxModal = 'media'">📎 Файл и медиа</button>
            </div>
            <div v-if="bcMediaHistory.length" class="mt-2 flex flex-wrap gap-2">
              <div v-for="(m, mi) in bcMediaHistory" :key="`pv-${mi}-${m.id || mi}`" class="relative shrink-0">
                <button
                  v-if="m.previewUrl && (String(m.kind || '').toLowerCase().includes('photo') || String(m.kind || '').toLowerCase().includes('video') || String(m.kind || '').toLowerCase() === 'animation')"
                  type="button"
                  class="group relative block h-16 w-16 overflow-hidden rounded-xl border border-white/15 bg-slate-950/80 shadow-md ring-1 ring-white/[0.06] transition hover:border-cyan-400/35 hover:ring-cyan-400/25"
                  title="Открыть крупно"
                  @click="openBcMediaViewer(m)"
                >
                  <img
                    v-if="String(m.kind || '').toLowerCase().includes('photo')"
                    :src="m.previewUrl"
                    class="h-full w-full object-cover"
                    alt=""
                  />
                  <video
                    v-else
                    :src="m.previewUrl"
                    class="h-full w-full object-cover"
                    muted
                    playsinline
                  />
                  <span
                    class="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/55 via-transparent to-white/[0.04] opacity-80 group-hover:opacity-100"
                  />
                </button>
                <div
                  v-else
                  class="flex h-16 w-16 flex-col items-center justify-center gap-0.5 rounded-xl border border-white/10 bg-slate-950/75 p-1 text-center shadow-inner ring-1 ring-white/[0.04]"
                >
                  <span class="text-lg leading-none">{{ bcMediaIcon(m.kind) }}</span>
                  <span class="line-clamp-2 max-w-[4.5rem] text-[9px] leading-tight text-slate-400">{{ m.name }}</span>
                </div>
                <button
                  v-if="m.id"
                  type="button"
                  class="absolute -right-1 -top-1 z-[1] flex h-5 w-5 items-center justify-center rounded-full bg-rose-600 text-[10px] text-white shadow ring-1 ring-white/20"
                  @click.stop="removeBcMediaItem(m.id)"
                >
                  ✕
                </button>
              </div>
            </div>

            <label class="mt-4 block text-xs font-semibold text-slate-400">Текст поста</label>
            <div class="mt-1 flex flex-wrap gap-1.5">
              <button type="button" class="bc-tool-btn text-[11px]" :class="!bcCanUndo() ? 'opacity-40' : ''" :disabled="!bcCanUndo()" @mousedown.prevent @click="bcUndo">↶ Назад</button>
              <button type="button" class="bc-tool-btn text-[11px]" :class="!bcCanRedo() ? 'opacity-40' : ''" :disabled="!bcCanRedo()" @mousedown.prevent @click="bcRedo">↷ Вперёд</button>
            </div>
            <p class="mt-1 text-[11px]" :class="bcCurrentLen() > bcCurrentMaxLen() ? 'text-rose-400' : 'text-slate-500'">
              {{ bcCurrentLen() }} / {{ bcCurrentMaxLen() }} символов
            </p>
            <div
              ref="bcBodyRef"
              class="bc-editor mt-1.5 h-48 overflow-y-auto rounded-xl border border-white/[0.1] bg-zinc-950 px-3 py-2.5 text-sm leading-relaxed focus-within:border-cyan-500/45 focus-within:ring-1 focus-within:ring-cyan-500/25"
              contenteditable="true"
              @input="onBcEditorInput"
              @click="onBcEditorClick"
              @mouseup="bcUpdateFormatState"
              @keyup="bcUpdateFormatState"
            />
            <div class="mt-4 flex flex-wrap gap-2 border-t border-white/[0.08] pt-4">
              <button
                type="button"
                class="rounded-xl border border-white/[0.12] bg-slate-800/[0.92] px-3.5 py-2 text-xs font-semibold text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] ring-1 ring-white/[0.05] backdrop-blur-md transition hover:border-slate-400/35 disabled:opacity-60"
                :disabled="bcSaving"
                @click="saveBcDraft"
              >
                Сохранить
              </button>
              <button
                v-if="!isBroadcastShellLite"
                type="button"
                class="rounded-xl border border-emerald-400/40 bg-gradient-to-br from-emerald-600/95 to-emerald-900/90 px-3.5 py-2 text-xs font-semibold text-white shadow-[0_10px_28px_-8px_rgba(52,211,153,0.45)] ring-1 ring-white/10 transition hover:brightness-110 disabled:opacity-60"
                :disabled="bcSending"
                @click="sendBc('users')"
              >
                В боты
              </button>
              <button
                type="button"
                class="rounded-xl border border-cyan-400/40 bg-gradient-to-br from-cyan-600/95 to-slate-900/90 px-3.5 py-2 text-xs font-semibold text-white shadow-[0_10px_28px_-8px_rgba(34,211,238,0.4)] ring-1 ring-white/10 transition hover:brightness-110 disabled:opacity-60"
                :disabled="bcSending"
                @click="openGroupsSendModal"
              >
                В группы
              </button>
              <button
                type="button"
                class="rounded-xl border border-indigo-400/40 bg-gradient-to-br from-indigo-600/95 to-slate-900/90 px-3.5 py-2 text-xs font-semibold text-white shadow-[0_10px_28px_-8px_rgba(129,140,248,0.45)] ring-1 ring-white/10 transition hover:brightness-110 disabled:opacity-60"
                :disabled="bcSending"
                @click="openChannelsSendModal"
              >
                В каналы
              </button>
            </div>
          </div>

          <div
            v-if="showAutopostCampaignsUi"
            class="rounded-xl bg-zinc-950/50 p-2 ring-1 ring-white/[0.06] backdrop-blur-xl"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="flex min-w-0 items-center gap-1.5">
                <span class="text-[10px] font-semibold uppercase tracking-wide text-zinc-300">Кампании автопоста</span>
                <button
                  type="button"
                  class="bc-tool-btn bc-broadcast-i shrink-0"
                  title="Справка по автопосту"
                  aria-label="Справка по автопосту"
                  @click="bcShowAutopostHelp = true"
                >
                  i
                </button>
              </div>
              <button
                type="button"
                class="rounded-md border border-cyan-500/40 bg-cyan-950/40 px-2 py-1 text-[10px] font-semibold text-cyan-100"
                @click="createBcAutopostCampaign"
              >
                + Кампания
              </button>
            </div>
            <p class="mt-1 text-[10px] leading-snug text-slate-400">
              Несколько независимых расписаний (разные ротации постов и чаты). Создать: выберите шаблон слева и нажмите «+&nbsp;Кампания». Управление расписанием — только кнопка «Настройка» у нужной кампании.
            </p>
            <div v-if="bcAutopostCampaigns.length" class="mt-2 space-y-2">
              <div
                v-for="camp in bcAutopostCampaigns"
                :key="`apc-${camp.id}`"
                class="flex flex-col gap-1.5 rounded-lg border border-white/10 bg-black/25 px-2 py-1.5"
              >
                <div class="flex flex-wrap items-center justify-between gap-1">
                  <div class="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span class="text-[9px] font-medium uppercase tracking-wide text-slate-500">№ {{ camp.user_seq != null ? camp.user_seq : '—' }}</span>
                    <input
                      type="text"
                      class="bc-post-input w-full max-w-[220px] rounded-md border border-slate-600 bg-slate-900/90 px-2 py-1 text-[11px] text-white"
                      :value="camp.title"
                      maxlength="255"
                      @blur="onBcCampaignTitleBlur(camp, $event)"
                    />
                  </div>
                  <button type="button" class="text-[10px] text-rose-400/90 hover:text-rose-300" @click="deleteBcAutopostCampaign(camp)">
                    Удалить
                  </button>
                </div>
                <div class="flex flex-wrap items-center gap-1.5">
                  <span
                    v-if="bcCampaignRunState(camp) === 'running'"
                    class="inline-flex items-center gap-1 rounded bg-emerald-950/45 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300"
                  >
                    <span class="h-1 w-1 animate-pulse rounded-full bg-emerald-400" />
                    Запущен
                  </span>
                  <span v-else-if="bcCampaignRunState(camp) === 'paused'" class="text-[10px] font-medium text-amber-300">На паузе</span>
                  <span v-else class="text-[10px] text-slate-500">Стоп</span>
                  <button
                    type="button"
                    class="rounded-md border border-fuchsia-400/35 bg-fuchsia-950/30 px-2 py-0.5 text-[10px] font-semibold text-fuchsia-100"
                    @click="openBcAutopostCampaignModal(camp)"
                  >
                    Настройка
                  </button>
                  <button
                    v-if="bcCampaignRunState(camp) === 'stopped'"
                    type="button"
                    class="rounded-md border border-emerald-500/45 bg-emerald-800/80 px-2 py-0.5 text-[10px] font-bold text-white"
                    @click="bcCampaignStartOrResume(camp)"
                  >
                    Запустить
                  </button>
                  <template v-else-if="bcCampaignRunState(camp) === 'running'">
                    <button
                      type="button"
                      class="rounded-md border border-amber-400/50 bg-amber-900/55 px-2 py-0.5 text-[10px] font-semibold text-amber-100"
                      @click="bcCampaignPause(camp)"
                    >
                      Пауза
                    </button>
                    <button type="button" class="bc-tool-btn !py-0.5 !px-2 text-[10px]" @click="bcCampaignStop(camp)">Стоп</button>
                  </template>
                  <template v-else>
                    <button
                      type="button"
                      class="rounded-md border border-emerald-500/45 bg-emerald-800/85 px-2 py-0.5 text-[10px] font-semibold text-emerald-50"
                      @click="bcCampaignResume(camp)"
                    >
                      ▶
                    </button>
                    <button type="button" class="bc-tool-btn !py-0.5 !px-2 text-[10px]" @click="bcCampaignStop(camp)">Стоп</button>
                  </template>
                </div>
              </div>
            </div>
            <p v-else class="mt-1.5 text-[10px] text-slate-500">Пока нет кампаний — нажмите «+ Кампания» (слева выберите шаблон поста).</p>
          </div>

          <div
            v-if="isBroadcastShellLite && meAdminProfile"
            class="mb-2 rounded-xl bg-zinc-950/50 px-3 py-2 text-[11px] leading-snug text-zinc-200 ring-1 ring-white/[0.06] backdrop-blur-md"
          >
            <p class="text-[10px] font-semibold uppercase tracking-wide text-zinc-400">Токены и рассылка</p>
            <p class="mt-1 text-slate-100/95">
              AURUM:
              <b class="tabular-nums text-fuchsia-200">{{ fmtBcTokens(meAdminProfile.aurum_tokens || 0) }}</b>
              ✨ · партнёрские:
              <b class="tabular-nums text-lime-200">{{ fmtBcTokens(meAdminProfile.partner_tokens) }}</b>
              ⚡
            </p>
            <p v-if="Number(meAdminProfile.broadcast_spend_tokens || 0) > 0" class="mt-0.5 text-slate-300/90">
              Уже потрачено на рассылки:
              <b class="tabular-nums text-amber-100">{{ fmtBcTokens(meAdminProfile.broadcast_spend_tokens) }}</b>
              ✨
            </p>
            <p class="mt-1 text-[10px] text-slate-400">
              Списание только с AURUM ✨. Партнёрские ⚡ не списываются сами — переведите в AURUM в рефералке.
              За один запуск: <b>1 ✨ на каждый выбранный групповой или канальный чат</b> (число подписчиков не умножает цену). Потолок за раз на сервере — {{ BC_BROADCAST_MAX_TOKENS }} ✨.
            </p>
            <div
              v-if="!isDelegatedFreeBroadcastCabinet"
              class="mt-2 space-y-2 rounded-lg border border-white/10 bg-black/25 p-2 text-[10px] text-slate-300"
            >
              <p class="font-semibold text-slate-200">Делегаты: кто платит AURUM за их рассылки в ваши чаты</p>
              <div class="flex flex-wrap gap-1.5">
                <button
                  type="button"
                  class="rounded-md border px-2 py-1 text-[10px] font-semibold transition"
                  :class="(meAdminProfile.delegate_broadcast_payer || 'delegate_first') === 'delegate_first' ? 'border-cyan-400/50 bg-cyan-500/15 text-cyan-100' : 'border-white/12 bg-white/5 text-slate-300'"
                  :disabled="delegatePayerSaving"
                  @click="saveDelegateBroadcastPayer('delegate_first')"
                >Сначала делегат</button>
                <button
                  type="button"
                  class="rounded-md border px-2 py-1 text-[10px] font-semibold transition"
                  :class="meAdminProfile.delegate_broadcast_payer === 'owner' ? 'border-cyan-400/50 bg-cyan-500/15 text-cyan-100' : 'border-white/12 bg-white/5 text-slate-300'"
                  :disabled="delegatePayerSaving"
                  @click="saveDelegateBroadcastPayer('owner')"
                >Всегда с меня</button>
                <button
                  type="button"
                  class="rounded-md border px-2 py-1 text-[10px] font-semibold transition"
                  :class="meAdminProfile.delegate_broadcast_payer === 'delegate' ? 'border-cyan-400/50 bg-cyan-500/15 text-cyan-100' : 'border-white/12 bg-white/5 text-slate-300'"
                  :disabled="delegatePayerSaving"
                  @click="saveDelegateBroadcastPayer('delegate')"
                >Всегда с делегата</button>
              </div>
              <p class="text-slate-500">При «сначала делегат» — если у менеджера не хватает ✨, спишется с вашего счёта (если хватает).</p>
              <div class="flex flex-wrap items-end gap-2 border-t border-white/10 pt-2">
                <label class="flex min-w-[7rem] flex-col gap-0.5">
                  <span class="text-[9px] uppercase text-slate-500">Tg id менеджера</span>
                  <input v-model="aurumTransferToDelegateTg" type="text" inputmode="numeric" class="rounded border border-white/15 bg-black/40 px-1.5 py-1 text-[11px] text-white" placeholder="напр. 123456789" />
                </label>
                <label class="flex min-w-[5rem] flex-col gap-0.5">
                  <span class="text-[9px] uppercase text-slate-500">Сумма ✨</span>
                  <input v-model="aurumTransferToDelegateAmt" type="text" inputmode="decimal" class="rounded border border-white/15 bg-black/40 px-1.5 py-1 text-[11px] text-white" placeholder="100" />
                </label>
                <button
                  type="button"
                  class="rounded-md border border-amber-400/40 bg-amber-500/15 px-2 py-1 text-[10px] font-bold text-amber-100 disabled:opacity-50"
                  :disabled="aurumTransferLoading"
                  @click="submitAurumTransferToDelegate"
                >Перевести AURUM</button>
              </div>
              <p class="text-[9px] text-slate-500">Перевод только менеджерам, уже добавленным в ваши чаты.</p>
            </div>
          </div>
        </div>

        <p
          v-else
          class="flex min-h-[180px] items-center justify-center rounded-xl border border-dashed border-white/[0.12] bg-zinc-900/50 p-6 text-center text-xs text-zinc-500 ring-1 ring-white/[0.05] backdrop-blur-md"
        >
          Выбери шаблон слева и нажми «Исправить».
        </p>
      </div>
      </div>
    </div>
    </template>

    <div
      v-if="bcAutopostingModalOpen"
      class="bc-autopost-modal-overlay fixed inset-0 z-[300] flex min-h-0 flex-col items-center justify-center overflow-y-auto overscroll-contain bg-black/75 px-3 py-4 pt-[max(0.75rem,calc(env(safe-area-inset-top,0px)+52px))] pb-[max(1rem,calc(5rem+env(safe-area-inset-bottom,0px)))] backdrop-blur-sm"
      @click.self="bcAutopostingModalOpen = false"
    >
      <div
        class="bc-autopost-modal-card mx-auto flex w-full max-w-md min-h-0 max-h-[min(88dvh,40rem)] flex-col overflow-hidden rounded-2xl bg-zinc-950/[0.92] text-zinc-100 shadow-[0_28px_80px_-24px_rgba(0,0,0,0.88)] ring-1 ring-white/[0.08] backdrop-blur-2xl sm:max-h-[min(86vh,42rem)]"
        @click.stop
      >
        <div class="shrink-0 bg-zinc-900/50 p-4 pb-2 backdrop-blur-md">
          <div class="flex items-center justify-between gap-2">
            <h3 class="text-sm font-semibold text-zinc-100">
              {{
                bcAutopostEditMode === 'campaign'
                  ? `Автопостинг — кампания №${bcAutopostCampaignUserSeq != null ? bcAutopostCampaignUserSeq : bcAutopostCampaignId || ''} (id ${bcAutopostCampaignId || ''})`
                  : 'Автопостинг'
              }}
            </h3>
            <div class="flex items-center gap-1">
              <button type="button" class="bc-tool-btn bc-broadcast-i" title="Справка по автопосту" @click="bcShowAutopostHelp = true">
                i
              </button>
              <button type="button" class="bc-tool-btn !px-2 !py-1" @click="bcAutopostingModalOpen = false">✕</button>
            </div>
          </div>
        </div>
        <div class="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain px-4 py-3">
        <div class="rounded-xl bg-white/[0.04] p-2.5 text-[11px] leading-snug text-zinc-200 backdrop-blur-md">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-zinc-400">Токены за автопост</p>
          <p class="mt-1 text-zinc-200/95">
            За <b>каждый</b> слот списание AURUM ✨ такое же, как за одну ручную отправку «В группы» / «В каналы» с тем же списком чатов (один слот = один запуск по всем выбранным группам и каналам сразу).
            Повторный тик не спишет дважды за тот же слот.
          </p>
          <p class="mt-1.5 text-[10px] leading-snug text-zinc-500">
            Правило: <b>1 ✨ на каждый выбранный чат</b> за слот; отдельной «предоплаты за день» пока нет. Потолок за слот — {{ BC_BROADCAST_MAX_TOKENS }} ✨.
          </p>
          <p
            v-if="bcAutopostQuoteInfo && bcAutopostQuoteInfo.broadcast_charge_applies"
            class="mt-1.5 rounded-lg bg-white/[0.05] px-2 py-1.5 text-[11px] text-zinc-200"
          >
            Оценка по текущим настройкам: <b>{{ Number(bcAutopostQuoteInfo.cost_tokens || 0) }}</b> ✨ за слот
            · чатов в списке <b>{{ Number(bcAutopostQuoteInfo.n_groups || 0) }}</b>
            <span v-if="bcAutopostQuoteInfo.can_afford === false" class="ml-1 font-semibold text-rose-300">· AURUM не хватает</span>
          </p>
          <button type="button" class="bc-tool-btn mt-2 !py-1 text-[10px]" @click="refreshBcAutopostCostHint">Пересчитать оценку</button>
        </div>
        <div class="rounded-xl bg-white/[0.04] p-2.5 backdrop-blur-md">
          <div class="flex flex-wrap items-start justify-between gap-2">
            <p class="text-[10px] font-semibold uppercase tracking-wide text-zinc-400">Управление</p>
            <button
              type="button"
              class="bc-tool-btn shrink-0 !px-2 !py-1 text-[10px] font-semibold"
              @click="openBcAutopostDetailStatsModal"
            >
              Статистика
            </button>
          </div>
          <div class="mt-2 flex flex-wrap items-center gap-2">
            <span
              v-if="bcAutopostRunState === 'running'"
              class="inline-flex items-center gap-1 rounded-md bg-emerald-950/50 px-2 py-1 text-[10px] font-semibold text-emerald-300 ring-1 ring-emerald-500/40"
            >
              <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" aria-hidden="true" />
              Автопостинг запущен
            </span>
            <span
              v-else-if="bcAutopostRunState === 'paused'"
              class="inline-flex items-center gap-1 rounded-md bg-amber-950/40 px-2 py-1 text-[10px] font-semibold text-amber-200 ring-1 ring-amber-400/50"
            >
              На паузе
            </span>
            <span v-else class="text-[10px] text-slate-500">Остановлен</span>
          </div>
          <div class="mt-2 flex flex-wrap gap-1.5">
            <button
              v-if="bcAutopostRunState === 'stopped'"
              type="button"
              class="rounded-lg border border-emerald-500/50 bg-emerald-700/85 px-3 py-1.5 text-[11px] font-bold text-white shadow-[0_0_16px_-4px_rgba(52,211,153,0.55)]"
              @click="bcAutopostStart"
            >
              Запустить
            </button>
            <template v-else-if="bcAutopostRunState === 'running'">
              <button
                type="button"
                class="rounded-lg border border-amber-400/50 bg-amber-900/50 px-3 py-1.5 text-[11px] font-semibold text-amber-100 hover:bg-amber-900/65"
                @click="bcAutopostPause"
              >
                Пауза
              </button>
              <button
                type="button"
                class="rounded-lg border border-slate-500/60 bg-slate-800/90 px-3 py-1.5 text-[11px] font-semibold text-slate-200"
                @click="bcAutopostStop"
              >
                Стоп
              </button>
            </template>
            <template v-else>
              <span
                class="inline-flex h-9 min-w-[2.25rem] items-center justify-center rounded-lg border-2 border-amber-400/80 bg-amber-500/20 text-base text-amber-100 shadow-[0_0_22px_rgba(251,191,36,0.45)] animate-pulse"
                title="На паузе"
                aria-hidden="true"
              >
                ⏸
              </span>
              <button
                type="button"
                class="rounded-lg border border-emerald-500/50 bg-emerald-800/80 px-3 py-1.5 text-[11px] font-semibold text-emerald-50"
                @click="bcAutopostResume"
              >
                Возобновить
              </button>
              <button
                type="button"
                class="rounded-lg border border-slate-500/60 bg-slate-800/90 px-3 py-1.5 text-[11px] font-semibold text-slate-200"
                @click="bcAutopostStop"
              >
                Стоп
              </button>
            </template>
          </div>
        </div>
        <div class="rounded-xl bg-white/[0.04] p-2.5 backdrop-blur-md">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-zinc-400">Куда отправляет автопостинг</p>
          <p class="mt-1 text-[11px] leading-snug text-zinc-500">
            Отдельно от кнопок отправки в редакторе поста. Подробная статистика по слотам автопоста — кнопка «Статистика» выше.
          </p>
          <div class="mt-2 space-y-2">
            <label
              class="flex cursor-pointer items-start gap-2.5 rounded-lg bg-white/[0.03] px-3 py-2 transition hover:bg-white/[0.06]"
              :class="bcAutopostingForm.autopost_target === 'groups' ? 'ring-1 ring-emerald-500/30' : ''"
            >
              <input v-model="bcAutopostingForm.autopost_target" type="radio" value="groups" class="mt-0.5 shrink-0 text-emerald-500" />
              <span>
                <span class="block text-[12px] font-semibold text-slate-100">В группы</span>
                <span class="mt-0.5 block text-[11px] text-slate-500">Список ниже или все активные группы (пустой список = во все, как раньше).</span>
              </span>
            </label>
            <label
              v-if="showFullAdminShell"
              class="flex cursor-pointer items-start gap-2.5 rounded-lg bg-white/[0.03] px-3 py-2 transition hover:bg-white/[0.06]"
              :class="bcAutopostingForm.autopost_target === 'users' ? 'ring-1 ring-cyan-500/30' : ''"
            >
              <input v-model="bcAutopostingForm.autopost_target" type="radio" value="users" class="mt-0.5 shrink-0 text-cyan-500" />
              <span>
                <span class="block text-[12px] font-semibold text-slate-100">В боты (личка)</span>
                <span class="mt-0.5 block text-[11px] text-slate-500">Всем активным пользователям, у которых уже есть диалог с ботом.</span>
              </span>
            </label>
          </div>
        </div>
        <div class="pb-1">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-zinc-400">Посты в ротации</p>
          <p class="mt-1 text-[11px] leading-snug text-slate-400">
            Выберите посты в ротацию или «все шаблоны». Просмотр — как в редакторе (текст, фото, кнопки).
          </p>
          <label class="mt-2 flex cursor-pointer items-center gap-2 text-[11px] text-slate-300">
            <input
              type="checkbox"
              class="h-3.5 w-3.5 rounded border-fuchsia-500 bg-slate-900 text-fuchsia-500"
              :checked="bcAutopostingForm.use_all_broadcasts === true"
              @change="bcAutopostSetUseAllPosts($event.target.checked)"
            />
            Все шаблоны по очереди
          </label>
          <div v-if="!bcAutopostingForm.use_all_broadcasts" class="mt-2 max-h-36 space-y-1 overflow-y-auto rounded-lg bg-white/[0.03] p-2">
            <div
              v-for="b in bcDraftBroadcastsForAutopost"
              :key="`aprot-${b.id}`"
              class="flex items-center gap-2 rounded-md px-1 py-0.5 hover:bg-slate-800/50"
            >
              <input
                type="checkbox"
                class="h-3.5 w-3.5 shrink-0 rounded border-violet-500 bg-slate-900 text-cyan-500"
                :checked="(bcAutopostingForm.broadcast_ids || []).includes(Number(b.id))"
                @change="toggleAutopostBroadcastId(Number(b.id))"
              />
              <span class="min-w-0 flex-1 truncate text-[11px] text-slate-200">{{ b.title || ('Пост #' + b.id) }}</span>
              <button type="button" class="bc-tool-btn !px-1.5 !py-0.5 text-[10px]" title="Просмотр" @click.prevent="openBcPreviewFromAutopost(b)">👁</button>
            </div>
            <p v-if="!bcDraftBroadcastsForAutopost.length" class="py-2 text-center text-[11px] text-slate-500">Нет шаблонов в статусе «черновик»</p>
          </div>
          <div v-if="!bcAutopostingForm.use_all_broadcasts" class="mt-2 flex flex-wrap gap-2">
            <button type="button" class="bc-tool-btn !py-1 text-[11px]" @click="bcAutopostSelectAllDraftPosts">Выбрать все</button>
            <button type="button" class="bc-tool-btn !py-1 text-[11px]" @click="bcAutopostClearPostSelection">Только текущий</button>
          </div>
        </div>
        <p class="text-[10px] font-semibold uppercase tracking-wide text-zinc-400">Расписание</p>
        <div class="mt-1.5 space-y-1.5 text-xs">
          <label class="flex items-center gap-2 text-zinc-300">
            <input v-model="bcAutopostingForm.scheduleMode" type="radio" value="every_day" class="text-zinc-400" />
            Каждый день
          </label>
          <label class="flex items-center gap-2 text-zinc-300">
            <input v-model="bcAutopostingForm.scheduleMode" type="radio" value="weekdays" class="text-zinc-400" />
            Только выбранные дни недели
          </label>
        </div>
        <div v-if="bcAutopostingForm.scheduleMode === 'weekdays'" class="mt-2 flex flex-wrap gap-1">
          <button
            v-for="d in BC_WEEKDAY_OPTS"
            :key="`wd-${d.v}`"
            type="button"
            class="rounded-md px-2 py-1 text-[11px] font-semibold transition"
            :class="
              (bcAutopostingForm.weekdays || []).includes(d.v)
                ? 'bg-white/[0.12] text-zinc-50 ring-1 ring-white/15'
                : 'bg-white/[0.04] text-zinc-500 hover:bg-white/[0.07]'
            "
            @click="bcToggleWeekday(d.v)"
          >
            {{ d.label }}
          </button>
        </div>
        <div class="mt-3 grid grid-cols-2 gap-2">
          <label class="col-span-2 text-[11px] font-medium text-zinc-500">Публикаций за сутки (слоты внутри окна ниже, до 288)</label>
          <input
            v-model.number="bcAutopostingForm.postsPerDay"
            type="number"
            min="1"
            max="288"
            class="col-span-2 rounded-lg bg-white/[0.06] px-2 py-1.5 text-sm text-white ring-1 ring-white/[0.08]"
          />
        </div>
        <div class="mt-2">
          <label class="text-[11px] text-zinc-500">Часовой пояс расписания</label>
          <p class="mt-0.5 text-[10px] leading-snug text-zinc-600">
            Берётся с этого устройства при сохранении (как время в телефоне/ПК). Можно править вручную (IANA, напр. Europe/Moscow).
          </p>
          <input
            v-model="bcAutopostingForm.timezone"
            type="text"
            class="mt-1 w-full rounded-lg bg-white/[0.06] px-2 py-1.5 font-mono text-xs text-white ring-1 ring-white/[0.08]"
            spellcheck="false"
            autocomplete="off"
          />
        </div>
        <div class="mt-3 grid grid-cols-2 gap-2">
          <div>
            <label class="text-[11px] text-zinc-500">Окно с (локальное время)</label>
            <input v-model="bcAutopostingForm.windowStart" type="time" class="mt-0.5 w-full rounded-lg bg-white/[0.06] px-2 py-1.5 text-sm text-white ring-1 ring-white/[0.08]" />
          </div>
          <div>
            <label class="text-[11px] text-zinc-500">до</label>
            <input v-model="bcAutopostingForm.windowEnd" type="time" class="mt-0.5 w-full rounded-lg bg-white/[0.06] px-2 py-1.5 text-sm text-white ring-1 ring-white/[0.08]" />
          </div>
        </div>
        <label class="mt-3 flex cursor-pointer items-center gap-2 text-[11px] text-slate-300">
          <input v-model="bcAutopostingForm.spreadInWindow" type="checkbox" class="h-3.5 w-3.5 rounded border-violet-500 bg-slate-900 text-cyan-500" />
          <span>
            Равномерно в окне: интервал между постами =
            <span class="font-mono text-cyan-200/90">окно ÷ публикаций за день</span>
            (первый не в самый старт окна). Сними галку — тогда первая в начале окна, последняя в конце, шаг чуть другой.
          </span>
        </label>
        <div v-if="bcAutopostingForm.autopost_target === 'groups'" class="mt-4 pt-2">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-zinc-400">Группы для автопоста</p>
          <p class="mt-1 text-[11px] leading-snug text-slate-400">
            Только группы этого бота. Пустой список = пост уйдёт во все активные группы (как кнопка «В группы» без отбора). Иначе — только отмеченные.
          </p>
          <div v-if="bcBroadcastCanScopeAll" class="mt-2 flex flex-wrap gap-3 text-[11px] text-slate-300">
            <label class="inline-flex cursor-pointer items-center gap-1.5">
              <input v-model="bcBroadcastGroupScope" type="radio" value="mine" class="text-fuchsia-500" @change="onBcBroadcastGroupScopeChange" />
              Мои группы
            </label>
            <label class="inline-flex cursor-pointer items-center gap-1.5">
              <input v-model="bcBroadcastGroupScope" type="radio" value="all" class="text-fuchsia-500" @change="onBcBroadcastGroupScopeChange" />
              Все группы на боте
            </label>
          </div>
          <div class="mt-2 max-h-48 min-h-0 space-y-1 overflow-y-auto overscroll-contain rounded-lg bg-white/[0.03] p-2 touch-pan-y">
            <label
              v-for="c in bcBroadcastGroups"
              :key="`apg-${bcNormalizeChatId(c)}`"
              class="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 hover:bg-slate-800/60"
            >
              <input
                type="checkbox"
                :checked="(bcAutopostingForm.group_chat_ids || []).includes(bcNormalizeChatId(c))"
                @change="toggleAutopostGroupChat(bcNormalizeChatId(c))"
              />
              <span class="text-[11px] text-slate-200">{{ c.title || c.username || bcNormalizeChatId(c) }}</span>
            </label>
            <p v-if="!bcBroadcastGroups.length" class="py-2 text-center text-[11px] text-slate-500">Нет групп в этом режиме</p>
          </div>
          <div class="mt-2 flex flex-wrap gap-2">
            <button type="button" class="bc-tool-btn !py-1 text-[11px]" @click="bcAutopostSelectAllListedGroups">Выбрать все</button>
            <button type="button" class="bc-tool-btn !py-1 text-[11px]" @click="bcAutopostClearGroupSelection">Очистить (во все)</button>
          </div>
        </div>
        <div v-if="bcAutopostingForm.autopost_target === 'groups'" class="mt-4 pt-2">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-zinc-400">Каналы для автопоста</p>
          <label
            class="mt-2 flex cursor-pointer items-center gap-2 rounded-lg bg-white/[0.05] px-2.5 py-2 text-[11px] text-zinc-200 hover:bg-white/[0.08]"
          >
            <input
              v-model="bcAutopostingForm.autopost_channels_disabled"
              type="checkbox"
              class="h-3.5 w-3.5 shrink-0 rounded border-indigo-400 bg-slate-900 text-indigo-400"
              @change="refreshBcAutopostCostHint"
            />
            <span>
              <span class="font-semibold">Не отправлять в каналы</span>
              <span class="mt-0.5 block text-[10px] font-normal text-slate-400">Только группы из блока выше. Отмеченные каналы остаются в пресете — снимите галочку, чтобы снова слать в каналы.</span>
            </span>
          </label>
          <p class="mt-2 text-[11px] leading-snug text-slate-400">
            Каналы, где бот — администратор (появляются после добавления бота в канал). Пустой список каналов = только группы из блока выше.
          </p>
          <div v-if="bcBroadcastCanScopeAll" class="mt-2 flex flex-wrap gap-3 text-[11px] text-slate-300">
            <label class="inline-flex cursor-pointer items-center gap-1.5">
              <input v-model="bcBroadcastGroupScope" type="radio" value="mine" class="text-indigo-400" @change="onBcBroadcastGroupScopeChange" />
              Мои каналы
            </label>
            <label class="inline-flex cursor-pointer items-center gap-1.5">
              <input v-model="bcBroadcastGroupScope" type="radio" value="all" class="text-indigo-400" @change="onBcBroadcastGroupScopeChange" />
              Все каналы на боте
            </label>
          </div>
          <div class="mt-2 max-h-40 min-h-0 space-y-1 overflow-y-auto overscroll-contain rounded-lg bg-white/[0.03] p-2 touch-pan-y">
            <label
              v-for="c in bcBroadcastChannels"
              :key="`apch-${bcNormalizeChatId(c)}`"
              class="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 hover:bg-slate-800/60"
            >
              <input
                type="checkbox"
                :checked="(bcAutopostingForm.channel_chat_ids || []).includes(bcNormalizeChatId(c))"
                @change="toggleAutopostChannelChat(bcNormalizeChatId(c))"
              />
              <span class="text-[11px] text-slate-200">{{ c.title || c.username || bcNormalizeChatId(c) }}</span>
            </label>
            <p v-if="!bcBroadcastChannels.length" class="py-2 text-center text-[11px] text-slate-500">Нет каналов — добавьте бота админом в канал</p>
          </div>
          <div class="mt-2 flex flex-wrap gap-2">
            <button type="button" class="bc-tool-btn !py-1 text-[11px]" @click="bcAutopostSelectAllListedChannels">Выбрать все каналы</button>
            <button type="button" class="bc-tool-btn !py-1 text-[11px]" @click="bcAutopostClearChannelSelection">Сбросить каналы</button>
          </div>
        </div>
        <div
          v-if="bcAutopostingForm.autopost_target === 'users' && showFullAdminShell"
          class="mt-4 rounded-lg bg-white/[0.04] px-3 py-2 text-[11px] text-zinc-300"
        >
          Для рассылки в личку выбор групп не используется — получат все активные пользователи бота.
        </div>
        </div>
        <div class="shrink-0 bg-zinc-900/55 p-4 pt-3 backdrop-blur-md">
          <div class="flex flex-wrap justify-end gap-2">
            <button type="button" class="bc-tool-btn" @click="bcAutopostingModalOpen = false">Отмена</button>
            <button
              type="button"
              class="rounded-xl border border-fuchsia-400/45 bg-gradient-to-br from-fuchsia-600/95 to-violet-800/90 px-3.5 py-2 text-xs font-semibold text-white shadow-[0_12px_36px_-8px_rgba(192,38,211,0.55)] ring-1 ring-white/10 transition hover:brightness-110"
              @click="saveBcAutopostingModal"
            >
              Сохранить
            </button>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="bcAutopostDetailOpen"
      class="bc-modal-tg-host fixed inset-0 z-[360] flex items-center justify-center bg-black/75 backdrop-blur-sm"
      @click.self="bcAutopostDetailOpen = false"
    >
      <div
        class="flex max-h-[min(86vh,28rem)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/[0.1] bg-slate-950/[0.94] text-slate-100 shadow-[0_28px_80px_-24px_rgba(0,0,0,0.85)] ring-1 ring-cyan-400/20 backdrop-blur-2xl"
        @click.stop
      >
        <div class="shrink-0 border-b border-white/10 p-4 pb-2">
          <div class="flex items-center justify-between gap-2">
            <p class="text-sm font-semibold text-white">Статистика автопоста</p>
            <button type="button" class="bc-tool-btn !px-2 !py-1" @click="bcAutopostDetailOpen = false">✕</button>
          </div>
          <p class="mt-1 text-[11px] text-slate-400">
            Учитываются только запуски с пометкой «autopost» (после обновления сервера). Ротация: id {{ (bcAutopostDetailData?.rotation_broadcast_ids || []).join(', ') || '—' }}.
          </p>
          <div class="mt-2 flex flex-wrap items-center gap-2">
            <label class="text-[11px] text-slate-400">Дней:</label>
            <select
              v-model.number="bcAutopostDetailDays"
              class="rounded-lg border border-slate-600 bg-black/40 px-2 py-1 text-xs text-white"
              @change="loadBcAutopostDetailStats"
            >
              <option :value="1">1</option>
              <option :value="3">3</option>
              <option :value="7">7</option>
              <option :value="14">14</option>
              <option :value="30">30</option>
            </select>
            <button type="button" class="bc-tool-btn !py-1 text-[10px]" @click="loadBcAutopostDetailStats">Обновить</button>
          </div>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-3">
          <p v-if="bcAutopostDetailLoading" class="text-[11px] text-slate-500">Загрузка…</p>
          <template v-else-if="bcAutopostDetailData">
            <p class="text-[11px] text-slate-300">
              Слотов автопоста за период: <b>{{ Number(bcAutopostDetailData.autopost_slots_recorded || 0) }}</b>
              <span v-if="Number(bcAutopostDetailData.posts_per_day_config || 0)" class="text-slate-500">
                · в настройках «публикаций за сутки»: {{ Number(bcAutopostDetailData.posts_per_day_config) }}</span>
            </p>
            <div v-if="showFullAdminShell" class="mt-3 rounded-lg border border-cyan-500/30 bg-cyan-950/25 p-2.5 text-[11px]">
              <p class="font-semibold text-cyan-200/90">В боты (личка)</p>
              <p class="mt-1 text-slate-300">
                Доставлено успешно: <b>{{ Number(bcAutopostDetailData.bots?.recipient_ok || 0) }}</b>
                · ошибок: <b>{{ Number(bcAutopostDetailData.bots?.recipient_fail || 0) }}</b>
                · всего получателей в логах: <b>{{ Number(bcAutopostDetailData.bots?.recipient_total || 0) }}</b>
              </p>
            </div>
            <div class="mt-3 rounded-lg border border-fuchsia-500/30 bg-black/30 p-2.5 text-[11px]">
              <p class="font-semibold text-fuchsia-200/90">Группы и каналы</p>
              <p class="mt-1 text-slate-300">
                Доставлено успешно: <b>{{ Number(bcAutopostDetailData.groups?.recipient_ok || 0) }}</b>
                · ошибок: <b>{{ Number(bcAutopostDetailData.groups?.recipient_fail || 0) }}</b>
                · всего получателей в логах: <b>{{ Number(bcAutopostDetailData.groups?.recipient_total || 0) }}</b>
              </p>
            </div>
            <p class="mt-3 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Последние запуски</p>
            <ul class="mt-1 space-y-1 text-[10px] text-slate-400">
              <li v-for="(r, ri) in bcAutopostDetailData.runs || []" :key="`aprun-${ri}-${r.id}`" class="break-words rounded border border-white/5 bg-black/20 px-2 py-1">
                #{{ r.id }} · {{ r.target_kind }} · ok {{ r.recipient_ok }}/{{ r.recipient_total }} · {{ r.created_at || '' }}
              </li>
              <li v-if="!(bcAutopostDetailData.runs || []).length" class="text-slate-600">Пока нет записей за выбранный период</li>
            </ul>
          </template>
          <p v-else class="text-[11px] text-slate-500">Нет данных</p>
        </div>
      </div>
    </div>

    <div
      v-if="bcStatsModalOpen"
      class="bc-modal-tg-host fixed inset-0 z-50 flex items-center justify-center overflow-y-auto overscroll-contain bg-black/75 backdrop-blur-sm"
      @click.self="bcStatsModalOpen = false"
    >
      <div
        class="w-full max-w-xl max-h-[88vh] overflow-y-auto rounded-2xl border border-white/[0.1] bg-slate-950/[0.94] p-4 shadow-[0_28px_80px_-24px_rgba(0,0,0,0.85)] ring-1 ring-cyan-400/20 backdrop-blur-2xl"
      >
        <div class="mb-3 flex items-center justify-between">
          <p class="text-base font-semibold text-white">Статистика рассылки</p>
          <button type="button" class="bc-tool-btn" @click="bcStatsModalOpen = false">✕</button>
        </div>
        <label class="text-xs text-slate-400">Пост</label>
        <select
          v-model="bcStatsSelectedId"
          class="mt-1 w-full rounded-xl border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-slate-100"
        >
          <option v-for="b in broadcasts" :key="`bstat-${b.id}`" :value="Number(b.id)">
            {{ b.title || 'Без названия' }}
          </option>
        </select>
        <div class="mt-2 rounded-xl border border-slate-700 bg-slate-950/40 p-2">
          <div class="flex items-center justify-between gap-2">
            <p class="text-xs text-slate-300">{{ statsHistoryTitle() }}</p>
            <button type="button" class="bc-tool-btn" @click="openStatsHistoryModal">Вся история</button>
          </div>
          <div class="mt-2 space-y-1">
            <button
              v-for="h in bcStatsHistoryPreview"
              :key="`hist-preview-${h.batch_id}`"
              type="button"
              class="w-full rounded-lg border border-slate-700 bg-slate-900/60 px-2 py-1.5 text-left text-xs text-slate-200 hover:border-cyan-500/50"
              @click="applyHistoryItem(h)"
            >
              {{ fmtBatchLabel(h) }}
            </button>
            <p v-if="!bcStatsHistoryPreview.length" class="text-[11px] text-slate-500">Пока нет запусков</p>
          </div>
        </div>
        <div v-if="bcStatsCurrentItem" class="mt-4 grid grid-cols-2 gap-2 text-xs">
          <div class="rounded-xl border border-slate-700 bg-slate-800/70 p-3">
            <p class="text-slate-400">Статус</p>
            <p class="mt-1 text-sm font-semibold text-white">{{ bcStatusLabel(bcStatsCurrentItem.status) }}</p>
          </div>
          <div class="rounded-xl border border-slate-700 bg-slate-800/70 p-3">
            <p class="text-slate-400">{{ bcStatsTab === 'groups' ? 'Всего подключено групп' : 'Всего подключено ботов' }}</p>
            <p class="mt-1 text-sm font-semibold text-white">{{ bcStatsTab === 'groups' ? (bcStatsData.connected_groups_total || 0) : (bcStatsData.connected_bots_total || 0) }}</p>
          </div>
          <div class="rounded-xl border border-slate-700 bg-slate-800/70 p-3">
            <p class="text-slate-400">Создан</p>
            <p class="mt-1 text-sm font-semibold text-white">{{ fmtDateTime(bcStatsCurrentItem.created_at) }}</p>
          </div>
          <div class="rounded-xl border border-slate-700 bg-slate-800/70 p-3">
            <p class="text-slate-400">Разослан</p>
            <p class="mt-1 text-sm font-semibold text-white">{{ fmtDateTime(bcStatsCurrentItem.sent_at) }}</p>
          </div>
        </div>
        <div v-if="showFullAdminShell" class="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            class="bc-tool-btn"
            :class="bcStatsTab === 'bots' ? 'bc-tool-active' : ''"
            @click="bcStatsTab = 'bots'"
          >
            В боты
          </button>
          <button
            type="button"
            class="bc-tool-btn"
            :class="bcStatsTab === 'groups' ? 'bc-tool-active' : ''"
            @click="bcStatsTab = 'groups'"
          >
            В группы
          </button>
        </div>
        <div v-if="showFullAdminShell && bcStatsTab === 'bots'" class="mt-3 grid grid-cols-2 gap-2 text-xs">
          <div class="rounded-xl border border-emerald-500/40 bg-emerald-500/10 p-3">
            <p class="text-emerald-200">Доставлено</p>
            <p class="mt-1 text-sm font-semibold text-emerald-100">{{ bcStatsData.bots.ok || 0 }}</p>
          </div>
          <div class="rounded-xl border border-rose-500/40 bg-rose-500/10 p-3">
            <p class="text-rose-200">Ошибки</p>
            <p class="mt-1 text-sm font-semibold text-rose-100">{{ bcStatsData.bots.fail || 0 }}</p>
          </div>
        </div>
        <div v-else class="mt-3 space-y-2">
          <div v-if="isBroadcastShellLite" class="mb-1 text-[11px] text-slate-400">
            {{
              isDelegatedFreeBroadcastCabinet
                ? 'Статистика только по отправкам в делегированные группы.'
                : 'Статистика только по отправкам в ваши группы.'
            }}
          </div>
          <div class="grid grid-cols-2 gap-2 text-xs">
            <div class="rounded-xl border border-emerald-500/40 bg-emerald-500/10 p-3">
              <p class="text-emerald-200">Доставлено</p>
              <p class="mt-1 text-sm font-semibold text-emerald-100">{{ bcStatsData.groups.ok || 0 }}</p>
            </div>
            <div class="rounded-xl border border-rose-500/40 bg-rose-500/10 p-3">
              <p class="text-rose-200">Ошибки</p>
              <p class="mt-1 text-sm font-semibold text-rose-100">{{ bcStatsData.groups.fail || 0 }}</p>
            </div>
          </div>
          <div class="max-h-48 overflow-y-auto rounded-xl border border-slate-700 bg-slate-950/40 p-2">
            <div
              v-for="g in bcStatsData.per_groups"
              :key="`bsg-${g.chat_id}`"
              class="mb-1 flex items-center justify-between rounded-lg bg-slate-800/60 px-2 py-1.5 text-xs text-slate-200"
            >
              <span class="min-w-0 truncate pr-2">{{ g.title }}</span>
              <span class="shrink-0 text-emerald-300">✓ {{ g.ok }}</span>
              <span class="shrink-0 text-rose-300">✕ {{ g.fail }}</span>
            </div>
            <p v-if="!bcStatsData.per_groups.length" class="p-2 text-center text-xs text-slate-500">Детализация по группам пока пуста</p>
          </div>
        </div>
        <div class="mt-3 rounded-xl border border-slate-700 bg-slate-950/40 p-2">
          <p class="text-xs font-semibold text-slate-300">Ошибки по выбранному периоду</p>
          <div class="mt-2 max-h-40 space-y-1 overflow-y-auto">
            <div
              v-for="(er, ei) in bcStatsData.errors"
              :key="`berr-${ei}`"
              class="rounded-lg border border-rose-500/30 bg-rose-950/20 px-2 py-1.5 text-[11px] text-rose-100"
            >
              <p>{{ fmtDateTime(er.created_at) }} · {{ er.target_kind === 'group' ? 'Группа' : 'Бот' }} {{ er.target_id }}</p>
              <p class="mt-0.5 text-rose-200/90">{{ er.error_message || 'Неизвестная ошибка' }}</p>
            </div>
            <p v-if="!bcStatsData.errors.length" class="text-[11px] text-slate-500">Ошибок нет</p>
          </div>
        </div>
        <p class="mt-3 text-[11px] text-slate-400">
          Telegram Bot API не отдает просмотры/комментарии/пересылки по постам в группах для ботов.
          Здесь показывается точная техническая статистика доставки.
        </p>
      </div>
    </div>

    <div
      v-if="bcStatsHistoryModalOpen"
      class="bc-modal-tg-host fixed inset-0 z-[60] flex items-center justify-center overflow-y-auto overscroll-contain bg-black/75 backdrop-blur-sm"
      @click.self="bcStatsHistoryModalOpen = false"
    >
      <div
        class="w-full max-w-xl max-h-[88vh] overflow-y-auto rounded-2xl border border-white/[0.1] bg-slate-950/[0.94] p-4 shadow-[0_28px_80px_-24px_rgba(0,0,0,0.85)] ring-1 ring-cyan-400/20 backdrop-blur-2xl"
      >
        <div class="mb-3 flex items-center justify-between">
          <p class="text-base font-semibold text-white">{{ statsHistoryTitle() }}</p>
          <button type="button" class="bc-tool-btn" @click="bcStatsHistoryModalOpen = false">✕</button>
        </div>
        <div class="mt-1 flex flex-wrap gap-1.5">
          <button type="button" class="bc-tool-btn" :class="bcStatsPreset === 'today' ? 'bc-tool-active' : ''" @click="applyStatsPreset('today')">Сегодня</button>
          <button type="button" class="bc-tool-btn" :class="bcStatsPreset === '24h' ? 'bc-tool-active' : ''" @click="applyStatsPreset('24h')">24ч</button>
          <button type="button" class="bc-tool-btn" :class="bcStatsPreset === '7d' ? 'bc-tool-active' : ''" @click="applyStatsPreset('7d')">7 дней</button>
          <button type="button" class="bc-tool-btn" :class="bcStatsPreset === '30d' ? 'bc-tool-active' : ''" @click="applyStatsPreset('30d')">30 дней</button>
          <button type="button" class="bc-tool-btn" @click="bcStatsPreset=''; bcStatsFrom=''; bcStatsTo=nowLocalInputValue()">Сброс</button>
        </div>
        <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <div>
            <label class="text-xs text-slate-400">С даты и времени</label>
            <input
              v-model="bcStatsFrom"
              type="datetime-local"
              class="mt-1 w-full rounded-xl border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-slate-100"
            />
          </div>
          <div>
            <label class="text-xs text-slate-400">По дату и время</label>
            <input
              v-model="bcStatsTo"
              type="datetime-local"
              class="mt-1 w-full rounded-xl border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-slate-100"
            />
          </div>
        </div>
        <div class="mt-3 space-y-1">
          <button
            v-for="h in bcStatsHistoryFiltered"
            :key="`hist-full-${h.batch_id}`"
            type="button"
            class="w-full rounded-lg border border-slate-700 bg-slate-900/60 px-2 py-2 text-left text-xs text-slate-200 hover:border-cyan-500/50"
            @click="applyHistoryItem(h)"
          >
            {{ fmtBatchLabel(h) }}
          </button>
          <p v-if="!bcStatsHistoryFiltered.length" class="text-[11px] text-slate-500">История не найдена по выбранному периоду</p>
        </div>
      </div>
    </div>

    <div
      v-if="bcAuxModal === 'keyboard'"
      class="fixed inset-0 z-[345] flex items-center justify-center bg-black/75 p-3 py-6 pt-[max(0.75rem,calc(env(safe-area-inset-top,0px)+52px))] pb-[max(1rem,calc(5rem+env(safe-area-inset-bottom,0px)))] backdrop-blur-sm"
      @click.self="bcAuxModal = ''"
    >
      <div
        class="flex max-h-[min(86vh,34rem)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/[0.1] bg-slate-950/[0.94] shadow-[0_28px_80px_-24px_rgba(0,0,0,0.85)] ring-1 ring-violet-400/20 backdrop-blur-2xl"
        @click.stop
      >
        <div class="flex shrink-0 items-center justify-between border-b border-slate-700/60 p-3">
          <p class="text-sm font-semibold text-white">Кнопки под постом</p>
          <div class="flex items-center gap-2">
            <button type="button" class="bc-tool-btn !px-2.5 !py-1 text-[11px]" :disabled="bcSaving" @click="saveBcDraft">Сохранить</button>
            <button type="button" class="bc-tool-btn" @click="bcAuxModal = ''">✕</button>
          </div>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-2 touch-pan-y">
          <div v-for="(row, ri) in bcButtonRows" :key="`mkb-${ri}`" class="mt-2 space-y-1.5 rounded-lg border border-white/10 bg-black/30 p-2 ring-1 ring-violet-500/15">
            <div class="flex items-center justify-between gap-2">
              <span class="text-xs font-semibold text-slate-400">Ряд {{ ri + 1 }}</span>
              <button type="button" class="text-xs text-rose-400 hover:text-rose-300" @click="removeBcRow(ri)">Убрать ряд</button>
            </div>
            <div
              v-for="(btn, bi) in row"
              :key="`mkbtn-${ri}-${bi}`"
              class="grid grid-cols-1 gap-2 border-t border-slate-700/40 pt-3 text-xs sm:grid-cols-2"
            >
              <input
                v-model="btn.text"
                type="text"
                placeholder="Текст на кнопке"
                class="bc-post-input rounded-lg border border-slate-600 bg-slate-900 px-2 py-1.5 sm:col-span-2"
              />
              <input
                v-model="btn.url"
                type="text"
                placeholder="Ссылка https://… (из браузера)"
                class="bc-post-input rounded-lg border border-slate-600 bg-slate-900 px-2 py-1.5"
              />
              <input
                v-model="btn.web_app_url"
                type="text"
                placeholder="URL мини-приложения (Web App)"
                class="bc-post-input rounded-lg border border-slate-600 bg-slate-900 px-2 py-1.5"
              />
              <input
                v-model="btn.callback_data"
                type="text"
                placeholder="Данные для бота (callback)"
                class="bc-post-input rounded-lg border border-slate-600 bg-slate-900 px-2 py-1.5 sm:col-span-2"
              />
              <button type="button" class="text-rose-400 sm:col-span-2" @click="removeBcButton(ri, bi)">Удалить кнопку</button>
            </div>
            <button type="button" class="text-xs font-semibold text-violet-400" @click="addBcButton(ri)">+ Кнопка в этот ряд</button>
          </div>
          <button type="button" class="mt-3 w-full rounded-lg border border-violet-500/40 py-2 text-sm font-semibold text-violet-200" @click="addBcRow">
            + Новый ряд кнопок
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="bcAuxModal === 'media'"
      class="fixed inset-0 z-[345] flex items-center justify-center bg-black/75 p-3 py-6 pt-[max(0.75rem,calc(env(safe-area-inset-top,0px)+52px))] pb-[max(1rem,calc(5rem+env(safe-area-inset-bottom,0px)))] backdrop-blur-sm"
      @click.self="bcAuxModal = ''"
    >
      <div
        class="flex max-h-[min(86vh,34rem)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/[0.1] bg-slate-950/[0.94] shadow-[0_28px_80px_-24px_rgba(0,0,0,0.85)] ring-1 ring-violet-400/20 backdrop-blur-2xl"
        @click.stop
      >
        <div class="flex shrink-0 items-center justify-between border-b border-slate-700/60 p-3">
          <p class="text-sm font-semibold text-white">Файл и медиа</p>
          <button type="button" class="bc-tool-btn" @click="bcAuxModal = ''">✕</button>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-2 touch-pan-y">
          <div class="flex flex-wrap gap-2">
            <div v-for="(m, mi) in bcMediaHistory" :key="`mm-${mi}-${m.id || mi}`" class="relative shrink-0">
              <button
                v-if="m.previewUrl && (String(m.kind || '').toLowerCase().includes('photo') || String(m.kind || '').toLowerCase().includes('video') || String(m.kind || '').toLowerCase() === 'animation')"
                type="button"
                class="group relative block h-24 w-24 overflow-hidden rounded-xl border border-white/15 bg-slate-950/80 shadow-md ring-1 ring-white/[0.06] transition hover:border-cyan-400/35"
                title="Открыть крупно"
                @click="openBcMediaViewer(m)"
              >
                <img
                  v-if="String(m.kind || '').toLowerCase().includes('photo')"
                  :src="m.previewUrl"
                  class="h-full w-full object-cover"
                  alt=""
                />
                <video
                  v-else
                  :src="m.previewUrl"
                  class="h-full w-full object-cover"
                  muted
                  playsinline
                />
                <span class="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/50 to-transparent opacity-90 group-hover:opacity-100" />
              </button>
              <div
                v-else
                class="flex h-24 w-24 flex-col items-center justify-center gap-1 rounded-xl border border-white/10 bg-slate-950/75 p-1 text-center ring-1 ring-white/[0.04]"
              >
                <span class="text-2xl">{{ bcMediaIcon(m.kind) }}</span>
                <span class="line-clamp-3 text-[10px] text-slate-400">{{ m.name }}</span>
              </div>
              <button
                v-if="m.id"
                type="button"
                class="absolute -right-1 -top-1 z-[1] flex h-6 w-6 items-center justify-center rounded-full bg-rose-600 text-xs text-white shadow ring-1 ring-white/20"
                @click.stop="removeBcMediaItem(m.id)"
              >
                ✕
              </button>
            </div>
          </div>
          <div v-if="!bcMediaHistory.length" class="py-6 text-center text-sm text-slate-500">Файл ещё не добавлен</div>
          <div class="mt-4 flex flex-wrap items-center gap-2">
            <label
              class="cursor-pointer rounded-xl border border-violet-400/40 bg-gradient-to-br from-violet-600/95 to-indigo-800/90 px-3 py-2 text-xs font-semibold text-white shadow-[0_10px_32px_-8px_rgba(124,58,237,0.55)] ring-1 ring-white/10 transition hover:brightness-110 disabled:opacity-50"
              :class="bcUploading ? 'pointer-events-none opacity-60' : ''"
            >
              <span class="inline-flex items-center gap-2">
                <span v-if="bcUploading" class="bc-spinner" />
                {{ bcUploading ? 'Загрузка…' : 'Выбрать файл' }}
              </span>
              <input
                type="file"
                class="hidden"
                accept="image/png,image/jpeg,image/webp,image/heic,image/heif,image/avif,image/bmp,video/mp4,video/quicktime,video/webm,video/x-matroska,audio/mpeg,audio/wav,audio/x-wav,audio/mp4,audio/aac,audio/ogg,audio/flac,.png,.jpg,.jpeg,.webp,.heic,.heif,.avif,.bmp,.mp4,.mov,.webm,.mkv,.mp3,.wav,.m4a,.aac,.ogg,.flac,.pdf"
                @change="uploadBcMedia"
              />
            </label>
            <button type="button" class="text-xs font-medium text-rose-400 hover:text-rose-300" :disabled="bcUploading" @click="clearBcMedia">Убрать медиа</button>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="bcShowMainHelp"
      class="bc-modal-tg-host fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm"
      @click.self="bcShowMainHelp = false"
    >
      <div
        class="w-full max-w-lg rounded-2xl bg-zinc-950/[0.93] p-4 shadow-[0_28px_80px_-24px_rgba(0,0,0,0.88)] ring-1 ring-white/[0.08] backdrop-blur-2xl"
      >
        <div class="mb-2 flex items-center justify-between gap-2">
          <p class="text-base font-semibold text-zinc-100">😈 Рассылка — коротко</p>
          <button type="button" class="bc-tool-btn shrink-0" @click="bcShowMainHelp = false">✕</button>
        </div>
        <div class="space-y-2.5 text-sm leading-snug text-zinc-400">
          <div
            v-if="cabinetMode === 'delegated'"
            class="rounded-xl bg-white/[0.05] p-3 text-[13px] leading-snug text-zinc-200 backdrop-blur-md"
          >
            <p class="font-semibold text-zinc-100">Фиолетовый ADM</p>
            <p class="mt-1">
              Я вижу только те чаты и каналы, куда тебя пустили как делегата. Чужие группы владельца и его личный кабинет я не трогаю — это не твоя территория.
            </p>
            <p class="mt-2 text-[12px] text-zinc-400">Кому выдали права и как открыть «свой» кабинет — решает владелец бота.</p>
          </div>
          <p class="text-zinc-200">
            <span class="font-semibold text-emerald-200/95">В личку</span> — одно нажатие, письмо уходит всем подписчикам, у кого в базе статус «активен». Не хочешь слать всем — сначала подумай, что пишешь: откат не волшебный.
          </p>
          <p>
            <span class="font-semibold text-cyan-200/90">Шаблон слева</span> — это твой черновик поста: текст, кнопки, картинка или файл лежат на сервере, пока ты сам не отправишь или не включишь автопост-кампанию.
          </p>
          <p>Имя шаблона видишь только ты — переименуй хоть каждый день, на подписчиков это не влияет.</p>
          <p class="text-zinc-500">
            Оформление как в Telegram: жирный, курсив, ссылки — кнопками над полем. Руками HTML городить не нужно — я не люблю сюрпризы в разметке.
          </p>
        </div>
      </div>
    </div>

    <div
      v-if="bcShowFormatHelp"
      class="bc-modal-tg-host fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm"
      @click.self="bcShowFormatHelp = false"
    >
      <div
        class="max-h-[min(88vh,28rem)] w-full max-w-lg overflow-y-auto overscroll-contain rounded-2xl bg-zinc-950/[0.93] p-4 shadow-[0_28px_80px_-24px_rgba(0,0,0,0.88)] ring-1 ring-white/[0.08] backdrop-blur-2xl"
      >
        <div class="mb-2 flex items-center justify-between">
          <p class="text-base font-semibold text-zinc-100">😈 Пост: текст, кнопки, файлы</p>
          <button type="button" class="bc-tool-btn" @click="bcShowFormatHelp = false">✕</button>
        </div>
        <p class="mb-3 rounded-lg bg-white/[0.05] px-2.5 py-2 text-[13px] leading-snug text-zinc-200 backdrop-blur-md">
          Коротко: «＋ Кнопки под постом» и «📎 Файл и медиа» — отдельные окна. Собрал пост — сохрани шаблон, потом жми «В боты», «В группы» или настрой автопост. Я не угадываю, что ты имел в виду, если не сохранил.
        </p>
        <p class="mb-2 text-xs font-semibold text-zinc-400">Текст и стили</p>
        <ul class="mb-4 list-disc space-y-1 pl-4 text-sm text-zinc-400">
          <li>Кнопка стиля подсвечена — формат включён для места, где курсор.</li>
          <li>Выдели кусок текста и нажми: жирный, курсив, подчёркнутый, зачёркнутый.</li>
          <li>Скрытый текст, цитата, код — сначала выдели фрагмент, потом жми нужное.</li>
          <li>Ссылка: выдели слова → «Ссылка» → вставь адрес в окно.</li>
          <li>В редакторе видно почти как в чате; в Telegram уходит нормальная разметка.</li>
          <li>Можно и через правый клик по тексту — как привык в системе.</li>
        </ul>
        <p class="mb-2 text-xs font-semibold text-zinc-400">Кнопки под постом</p>
        <ul class="mb-4 list-disc space-y-1 pl-4 text-sm text-zinc-400">
          <li><span class="font-semibold text-zinc-200">Обычная ссылка</span> — откроется сайт или чужой канал.</li>
          <li><span class="font-semibold text-zinc-200">Мини-приложение</span> — откроется твой Web App по ссылке.</li>
          <li><span class="font-semibold text-zinc-200">Callback</span> — короткий код для бота (до 64 символов), не для людей в браузер.</li>
          <li class="text-zinc-500">В одной кнопке не смешивай типы — одно поле на кнопку.</li>
        </ul>
        <p class="mb-2 text-xs font-semibold text-zinc-400">Файлы и картинки</p>
        <ul class="mb-4 list-disc space-y-1 pl-4 text-sm text-zinc-400">
          <li>Картинку можно отправить «как фото» — тогда галерея не сожмёт превью; при необходимости включи «Точно фото» при загрузке.</li>
          <li>Картинки и видео — обычные форматы (jpg, png, webp, gif, mp4 и т.д.).</li>
          <li>Несколько файлов: кнопки цепляются к первому сообщению, остальное уйдёт следом или альбомом — так устроен Telegram.</li>
          <li>Бот ругается на медиа — сохрани шаблон и залей файл ещё раз, иногда так лечится.</li>
        </ul>
        <p class="mb-2 text-xs font-semibold text-zinc-400">В группы и в каналы</p>
        <p class="text-sm leading-snug text-zinc-400">
          Сработает, если ты админ того чата, бот там тоже с правами, а канал ты добавил боту как админа — тогда он появится в списке «В каналы». Без прав я даже не постучусь в дверь.
        </p>
      </div>
    </div>

    <div
      v-if="bcShowAutopostHelp"
      class="bc-modal-tg-host fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm"
      @click.self="bcShowAutopostHelp = false"
    >
      <div
        class="w-full max-w-lg rounded-2xl bg-zinc-950/[0.93] p-4 shadow-[0_28px_80px_-24px_rgba(0,0,0,0.88)] ring-1 ring-white/[0.08] backdrop-blur-2xl"
      >
        <div class="mb-2 flex items-center justify-between">
          <p class="text-base font-semibold text-zinc-100">😈 Автопост — без магии</p>
          <button type="button" class="bc-tool-btn" @click="bcShowAutopostHelp = false">✕</button>
        </div>
        <div class="max-h-[min(60vh,28rem)] space-y-3 overflow-y-auto pr-0.5 text-left text-sm leading-snug text-zinc-400">
          <p class="rounded-lg bg-white/[0.05] px-2.5 py-2 text-zinc-200 backdrop-blur-md">
            <span class="font-semibold text-zinc-100">Кампания</span> — это отдельное «расписание + кому слать + какие посты крутить». Слева выбери шаблон, жми «+ Кампания», потом «Настройка» у нужной строки. Кампаний может быть несколько — например, разные группы или разные наборы постов.
          </p>
          <p>
            <span class="font-semibold text-amber-200/95">Окно и галка «Равномерно»</span> — посты только между «с» и «до» по твоему часовому поясу. Если галка включена (по умолчанию), шаг между соседними постами ровно
            <span class="font-mono text-cyan-200/90">длина окна / число публикаций за день</span>
            — например, час и 10 постов ≈ каждые 6 минут, без выплёвывания пачки в начало окна. Без галки — старая схема «первая у старта, последняя у финиша».
          </p>
          <p class="text-zinc-500">
            Если я был офлайн и слот «протух» примерно больше <span class="font-medium text-zinc-300">50 минут</span> — этот слот <span class="font-medium text-zinc-300">пропускаю</span>, AURUM за него не снимаю. Так не наказываю за то, что бот не дышал сетью.
          </p>
          <p>
            <span class="font-semibold text-emerald-200/95">За AURUM ✨</span> — с каждого <b>удачного</b> выхода в свет столько же, сколько за одну ручную отправку с тем же списком чатов: <b>1 ✨ на каждый выбранный групповой или канальный чат</b> (подписчики не умножают цену), до {{ BC_BROADCAST_MAX_TOKENS }} ✨ за слот. Один и тот же слот не спишу дважды; отдельной пачковой оплаты «за день» пока нет.
          </p>
          <p class="text-[13px] text-zinc-500">
            Фиолетовый ADM — шлю туда, куда тебя пустили делегатом. Голубой — твои чаты и привычные сценарии владельца.
          </p>
        </div>
      </div>
    </div>

    <div
      v-if="bcShowSpoilerInfo"
      class="bc-modal-tg-host fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm"
      @click.self="bcShowSpoilerInfo = false"
    >
      <div
        class="w-full max-w-md rounded-2xl border border-white/[0.1] bg-slate-950/[0.94] p-4 shadow-[0_28px_80px_-24px_rgba(0,0,0,0.85)] ring-1 ring-violet-400/25 backdrop-blur-2xl"
      >
        <div class="mb-2 flex items-center justify-between">
          <p class="text-base font-semibold text-white">Скрытый текст</p>
          <button type="button" class="bc-tool-btn" @click="bcShowSpoilerInfo = false">✕</button>
        </div>
        <p class="text-sm text-slate-200">{{ bcActiveSpoilerText || 'Курсор не внутри скрытого текста' }}</p>
      </div>
    </div>

    <div
      v-if="bcShowLinkInfo"
      class="bc-modal-tg-host fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm"
      @click.self="bcShowLinkInfo = false"
    >
      <div
        class="w-full max-w-md rounded-2xl border border-white/[0.1] bg-slate-950/[0.94] p-4 shadow-[0_28px_80px_-24px_rgba(0,0,0,0.85)] ring-1 ring-violet-400/25 backdrop-blur-2xl"
      >
        <div class="mb-2 flex items-center justify-between">
          <p class="text-base font-semibold text-white">Ссылка в тексте</p>
          <button type="button" class="bc-tool-btn" @click="bcShowLinkInfo = false">✕</button>
        </div>
        <p class="break-all text-sm text-slate-200">{{ bcActiveLinkUrl || 'Курсор не внутри ссылки' }}</p>
      </div>
    </div>

    <div
      v-if="showPartnerEventsModal"
      class="fixed inset-0 z-[65] flex items-end justify-center bg-black/70 p-3 md:items-center"
      @click.self="showPartnerEventsModal = false"
    >
      <div
        class="flex h-[min(85vh,calc(100dvh-24px))] max-h-[85vh] w-full max-w-2xl min-h-0 flex-col overflow-hidden rounded-2xl border border-cyan-400/50 bg-slate-950 p-4 shadow-2xl"
        @click.stop
      >
        <div class="mb-2 flex shrink-0 items-center justify-between">
          <p class="text-base font-semibold text-white">Последние события защиты (24ч)</p>
          <button type="button" class="bc-tool-btn" @click="showPartnerEventsModal = false">✕</button>
        </div>
        <p class="mb-2 shrink-0 text-[11px] text-slate-300">Удалений за 24ч: <b>{{ Number(plActivitySummary?.today?.deleted || 0) }}</b>. Ниже последние события с релевантными действиями.</p>
        <div class="min-h-0 flex-1 touch-pan-y space-y-1 overflow-y-auto overscroll-y-contain pr-1">
          <div
            v-for="(ev, ei) in partnerEvents24h"
            :key="`plj-modal-${ei}-${ev.created_at}-${ev.user_id}`"
            class="rounded-lg border px-2 py-2 text-[11px]"
            :class="partnerNormalizeAction(ev.action) === 'observe'
              ? 'border-red-500/60 bg-red-950/40 text-red-100'
              : 'border-slate-700 bg-slate-800/80 text-slate-200'"
          >
            <div class="flex flex-wrap items-center gap-1 text-[10px] text-slate-400">
              <span>{{ ev.created_at }}</span>
              <span>·</span>
              <span class="font-mono">{{ ev.chat_title }}</span>
            </div>
            <p class="mt-0.5 font-semibold">
              <a
                v-if="partnerUserHref(ev)"
                href="#"
                class="text-sky-300 underline decoration-sky-500/50 underline-offset-2 hover:text-sky-200"
                @click.prevent.stop="openExternalLink(partnerUserHref(ev))"
              >{{ partnerUserLabel(ev) }}</a>
              <span v-else>{{ partnerUserLabel(ev) }}</span>
              · {{ partnerActionLabelRu(ev.action) }}
              <span v-if="partnerNormalizeAction(ev.action) === 'delete' || partnerNormalizeAction(ev.action) === 'observe'"> · {{ partnerReasonRu(ev.reason) }}</span>
            </p>
            <div class="mt-1.5 flex flex-wrap gap-1.5">
              <button
                v-if="partnerNormalizeAction(ev.action) === 'mute' && !partnerJournalActionHidden(ev, 'mute')"
                type="button"
                class="rounded-md bg-emerald-700 px-2 py-1 text-[10px] font-semibold text-white"
                @click="partnerQuickUnmute(ev)"
              >
                Размут
              </button>
              <button
                v-if="partnerNormalizeAction(ev.action) === 'ban' && !partnerJournalActionHidden(ev, 'ban')"
                type="button"
                class="rounded-md bg-indigo-700 px-2 py-1 text-[10px] font-semibold text-white"
                @click="partnerQuickUnban(ev)"
              >
                Разбан
              </button>
              <button
                v-if="partnerNormalizeAction(ev.action) === 'observe'"
                type="button"
                class="rounded-md bg-amber-700 px-2 py-1 text-[10px] font-semibold text-white"
                @click="partnerQuickObserve(ev)"
              >
                Замечено
              </button>
            </div>
          </div>
          <p v-if="!(partnerEvents24h || []).length" class="py-6 text-center text-[11px] text-slate-500">Пока нет событий.</p>
        </div>
      </div>
    </div>

    <div
      v-if="showPartnerSpendModal"
      class="fixed inset-0 z-[66] flex items-center justify-center bg-black/70 p-3 pb-[calc(4.5rem+env(safe-area-inset-bottom,0px))] md:pb-6"
      @click.self="showPartnerSpendModal = false"
    >
      <div class="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-2xl border border-fuchsia-400/50 bg-slate-950 p-4 shadow-2xl">
        <div class="mb-2 flex items-center justify-between">
          <p class="text-base font-semibold text-white">Расходы на рассылки</p>
          <button type="button" class="bc-tool-btn" @click="showPartnerSpendModal = false">✕</button>
        </div>
        <div class="space-y-1 text-sm text-slate-200">
          <p>Всего списано: <b>{{ Number(meAdminProfile?.broadcast_spend_tokens || 0) }} ⚡</b></p>
          <p>Из подписки: <b>{{ Number(meAdminProfile?.broadcast_spend_sub_tokens || 0) }} ⚡</b></p>
          <p>Из AURUM: <b>{{ Number(meAdminProfile?.broadcast_spend_aurum_tokens || 0) }} ✨</b></p>
        </div>
      </div>
    </div>

    <div
      v-if="showPartnerGroupsModal"
      class="fixed inset-0 z-[67] flex items-end justify-center bg-black/70 p-3 md:items-center"
      @click.self="showPartnerGroupsModal = false"
    >
      <div
        class="flex h-[min(88vh,calc(100dvh-24px))] max-h-[88vh] w-full max-w-2xl min-h-0 flex-col overflow-hidden rounded-2xl border border-cyan-400/50 bg-slate-950 p-4 shadow-2xl"
        @click.stop
      >
        <div class="mb-2 flex shrink-0 items-center justify-between gap-2">
          <p class="text-base font-semibold text-white">Подключённые группы и каналы</p>
          <button type="button" class="bc-tool-btn" @click="showPartnerGroupsModal = false">✕</button>
        </div>
        <div class="relative mb-2 shrink-0 pr-10">
          <p class="text-[11px] text-slate-300">
            Всего подключено: <b>{{ Number(plActivitySummary?.chats_count || 0) }}</b>
            (группы: <b>{{ Number(plActivitySummary?.groups_count || 0) }}</b>, каналы: <b>{{ Number(plActivitySummary?.channels_count || 0) }}</b>).
            Каналы считают вступления и модерацию в <b>чате обсуждения</b>, если он привязан.
          </p>
          <button
            type="button"
            v-bind="partnerHelpBind('discussion', 'trailing')"
            @click.stop.prevent="partnerShowHelp('discussion')"
            @mousedown.stop
          >
            i
          </button>
        </div>
        <div class="mb-2 shrink-0 flex items-center gap-2">
          <button type="button" class="rounded-md px-2 py-1 text-[10px] font-semibold" :class="partnerGroupsTab === 'all' ? 'bg-cyan-600 text-white' : 'bg-slate-700 text-slate-200'" @click="partnerGroupsTab = 'all'">Все</button>
          <button type="button" class="rounded-md px-2 py-1 text-[10px] font-semibold" :class="partnerGroupsTab === 'groups' ? 'bg-cyan-600 text-white' : 'bg-slate-700 text-slate-200'" @click="partnerGroupsTab = 'groups'">Группы</button>
          <button type="button" class="rounded-md px-2 py-1 text-[10px] font-semibold" :class="partnerGroupsTab === 'channels' ? 'bg-cyan-600 text-white' : 'bg-slate-700 text-slate-200'" @click="partnerGroupsTab = 'channels'">Каналы</button>
        </div>
        <div class="min-h-0 flex-1 touch-pan-y space-y-3 overflow-y-auto overscroll-y-contain pr-1">
          <template v-if="partnerGroupsModalRows.showChannels && (partnerGroupsModalRows.channels || []).length">
            <p class="text-[10px] font-semibold uppercase tracking-wide text-amber-200/90">Каналы</p>
            <div
              v-for="c in partnerGroupsModalRows.channels"
              :key="`pgm-ch-${c.id}`"
              class="rounded-lg border border-amber-700/40 bg-amber-950/20 px-2 py-2 text-[11px] text-slate-200"
            >
              <p class="font-semibold">{{ c.title }}</p>
              <p class="mt-0.5 text-slate-400">
                Участников (канал): <b>{{ c.members_count ?? '—' }}</b> · Вступило в обсуждении: <b>{{ Number(c.joins || 0) }}</b>
                · Спам-срабатывания: <b>{{ Number(c.spam_moderation || 0) }}</b>
              </p>
            </div>
          </template>
          <template v-if="partnerGroupsModalRows.showChannels && (partnerGroupsModalRows.linked || []).length">
            <p class="text-[10px] font-semibold uppercase tracking-wide text-sky-200/90">Группы обсуждения каналов</p>
            <div
              v-for="c in partnerGroupsModalRows.linked"
              :key="`pgm-lg-${c.id}`"
              class="rounded-lg border border-sky-700/40 bg-sky-950/20 px-2 py-2 text-[11px] text-slate-200"
            >
              <p class="font-semibold">{{ c.title }}</p>
              <p class="mt-0.5 text-slate-400">
                ID канала-родителя: <b>{{ c.parent_channel_id || '—' }}</b> · Подключились: <b>{{ Number(c.joins || 0) }}</b>
                · Модерация: <b>{{ Number(c.moderation || 0) }}</b>
              </p>
            </div>
          </template>
          <template v-if="partnerGroupsModalRows.showGroups && (partnerGroupsModalRows.groups || []).length">
            <p class="text-[10px] font-semibold uppercase tracking-wide text-cyan-200/90">Группы / супергруппы</p>
            <div
              v-for="c in partnerGroupsModalRows.groups"
              :key="`pgm-gr-${c.id}`"
              class="rounded-lg border border-slate-700 bg-slate-900/70 px-2 py-2 text-[11px] text-slate-200"
            >
              <p class="font-semibold">{{ c.title }}</p>
              <p class="mt-0.5 text-slate-400">
                Участников сейчас: <b>{{ c.members_count ?? '—' }}</b> · Подключились: <b>{{ Number(c.joins || 0) }}</b> · Модерация: <b>{{ Number(c.moderation || 0) }}</b>
              </p>
            </div>
          </template>
          <p v-if="!(partnerHourlyData?.chats || []).length" class="py-6 text-center text-[11px] text-slate-500">Список пуст.</p>
        </div>
      </div>
    </div>

    <div
      v-if="showPartnerJoinsModal"
      class="fixed inset-0 z-[67] flex items-end justify-center bg-black/70 p-3 md:items-center"
      @click.self="showPartnerJoinsModal = false"
    >
      <div
        class="flex h-[min(88vh,calc(100dvh-24px))] max-h-[88vh] w-full max-w-2xl min-h-0 flex-col overflow-hidden rounded-2xl border border-violet-400/50 bg-slate-950 p-4 shadow-2xl"
        @click.stop
      >
        <div class="mb-2 flex shrink-0 items-center justify-between gap-2">
          <div>
            <p class="text-base font-semibold text-white">Подключились: подробная статистика</p>
            <p v-if="partnerActivityPeriodLine" class="text-[10px] text-violet-200/80">{{ partnerActivityPeriodLine }}</p>
          </div>
          <button type="button" class="bc-tool-btn" @click="showPartnerJoinsModal = false">✕</button>
        </div>
        <div class="mb-2 flex shrink-0 flex-wrap items-center gap-2">
          <select
            v-model="partnerHourlyChatId"
            class="rounded-lg border border-slate-600 bg-black/40 px-2 py-1 text-xs text-white"
            @change="loadPartnerHourlyActivity"
          >
            <option value="all">Все объекты</option>
            <optgroup v-if="(partnerChatsGrouped.groups || []).length" label="Группы">
              <option v-for="c in partnerChatsGrouped.groups" :key="`pj-gr-${c.id}`" :value="String(c.id)">{{ c.title }}</option>
            </optgroup>
            <optgroup v-if="(partnerChatsGrouped.channels || []).length" label="Каналы">
              <option v-for="c in partnerChatsGrouped.channels" :key="`pj-ch-${c.id}`" :value="String(c.id)">{{ c.title }}</option>
            </optgroup>
            <optgroup v-if="(partnerChatsGrouped.linked || []).length" label="Обсуждения каналов">
              <option v-for="c in partnerChatsGrouped.linked" :key="`pj-lg-${c.id}`" :value="String(c.id)">{{ c.title }}</option>
            </optgroup>
          </select>
          <button
            v-for="p in PARTNER_HOURLY_PRESETS"
            :key="`pjoin-${p.id}`"
            type="button"
            class="rounded-md px-2 py-1 text-[10px] font-semibold leading-tight"
            :class="!partnerHourlyUseCustomRange && partnerHourlyPreset === p.id ? 'bg-violet-600 text-white' : 'bg-slate-700 text-slate-200'"
            @click="selectPartnerPreset(p.id)"
          >
            <span class="block">{{ p.label }}</span>
            <span class="block text-[8px] font-normal opacity-90">{{ partnerPresetDateHint(p.id) }}</span>
          </button>
        </div>
        <div class="relative mb-2 shrink-0 pr-10">
          <p class="text-[11px] text-slate-300">
            Подключились за период: <b>{{ Number(partnerHourlyData?.totals?.joins || 0) }}</b> ·
            Событий всего: <b>{{ Number(partnerHourlyData?.totals?.events || 0) }}</b>
          </p>
          <button
            type="button"
            v-bind="partnerHelpBind('events', 'trailing')"
            @click.stop.prevent="partnerShowHelp('events')"
            @mousedown.stop
          >
            i
          </button>
        </div>
        <div class="mb-2 flex shrink-0 flex-wrap gap-1.5">
          <button
            type="button"
            class="rounded-md border border-violet-500/50 bg-violet-950/30 px-2 py-1 text-[10px] font-semibold text-violet-100"
            @click="partnerSegmentModalTab = 'joins'; showPartnerSegmentModal = true"
          >
            Подробнее: вступления
          </button>
          <button
            type="button"
            class="rounded-md border border-rose-500/50 bg-rose-950/30 px-2 py-1 text-[10px] font-semibold text-rose-100"
            @click="partnerSegmentModalTab = 'spam'; showPartnerSegmentModal = true"
          >
            Подробнее: спам-фильтры
          </button>
        </div>
        <div class="min-h-0 flex-1 touch-pan-y space-y-1 overflow-y-auto overscroll-y-contain pr-1">
          <button
            v-for="row in partnerHourlySlots"
            :key="`pjoin-slot-${row.index}`"
            type="button"
            class="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-2 py-1.5 text-left text-[11px] text-slate-200 hover:border-violet-500/50"
            @click="openPartnerSlotDetail(row.slot_start, row.slot_end, row.label)"
          >
            <p class="font-semibold text-violet-100/90">{{ row.label }}</p>
            <p>подключились: <b>{{ Number(row.joins || 0) }}</b> · событий: {{ Number(row.events || 0) }}</p>
          </button>
          <p v-if="!partnerHourlySlots.length" class="py-6 text-center text-[11px] text-slate-500">Нет данных.</p>
        </div>
      </div>
    </div>

    <div
      v-if="showPartnerSegmentModal"
      class="fixed inset-0 z-[69] flex items-end justify-center bg-black/70 p-3 md:items-center"
      @click.self="showPartnerSegmentModal = false"
    >
      <div class="w-full max-w-sm rounded-2xl border border-violet-400/50 bg-slate-950 p-4 shadow-2xl">
        <div class="mb-2 flex items-center justify-between">
          <p class="text-sm font-semibold text-white">{{ partnerSegmentModalTab === 'joins' ? 'Вступления по типам' : 'Спам по типам чатов' }}</p>
          <button type="button" class="bc-tool-btn" @click="showPartnerSegmentModal = false">✕</button>
        </div>
        <div v-if="partnerSegmentModalTab === 'joins'" class="space-y-1 text-[11px] text-slate-200">
          <p>Каналы (в обсуждении): <b>{{ Number(partnerHourlyData?.segment_joins?.channel || 0) }}</b></p>
          <p>Группы: <b>{{ Number(partnerHourlyData?.segment_joins?.group || 0) }}</b></p>
          <p>Обсуждения (как отдельный чат): <b>{{ Number(partnerHourlyData?.segment_joins?.linked_group || 0) }}</b></p>
        </div>
        <div v-else class="space-y-1 text-[11px] text-slate-200">
          <p>Каналы: <b>{{ Number(partnerHourlyData?.segment_spam?.channel || 0) }}</b></p>
          <p>Группы: <b>{{ Number(partnerHourlyData?.segment_spam?.group || 0) }}</b></p>
          <p>Обсуждения: <b>{{ Number(partnerHourlyData?.segment_spam?.linked_group || 0) }}</b></p>
        </div>
      </div>
    </div>

    <div
      v-if="showPartnerSlotDetailModal"
      class="fixed inset-0 z-[69] flex items-end justify-center bg-black/70 p-3 md:items-center"
      @click.self="showPartnerSlotDetailModal = false"
    >
      <div
        class="flex h-[min(85vh,calc(100dvh-24px))] max-h-[85vh] w-full max-w-lg min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-500/50 bg-slate-950 p-4 shadow-2xl"
        @click.stop
      >
        <div class="mb-2 flex shrink-0 items-center justify-between gap-2">
          <p class="text-sm font-semibold text-white">{{ partnerSlotDetailTitle }}</p>
          <button type="button" class="bc-tool-btn" @click="showPartnerSlotDetailModal = false">✕</button>
        </div>
        <div v-if="partnerSlotDetailLoading" class="shrink-0 py-6 text-center text-xs text-slate-400">Загрузка…</div>
        <div v-else class="min-h-0 flex-1 touch-pan-y space-y-2 overflow-y-auto overscroll-y-contain pr-1 text-[11px] text-slate-200">
          <p class="font-semibold text-cyan-200/90">Вступили</p>
          <div v-for="(j, ji) in (partnerSlotDetailData?.joins || [])" :key="`jd-${ji}-${j.user_id}`" class="rounded border border-slate-700/80 bg-slate-900/60 px-2 py-1">
            {{ j.joined_at }} · чат {{ j.chat_title }} ·
            <a
              v-if="partnerUserHref(j)"
              href="#"
              class="text-sky-300 underline decoration-sky-500/50 underline-offset-2 hover:text-sky-200"
              @click.prevent.stop="openExternalLink(partnerUserHref(j))"
            >{{ partnerUserLabel(j) }}</a>
            <span v-else>{{ partnerUserLabel(j) }}</span>
          </div>
          <p v-if="!(partnerSlotDetailData?.joins || []).length" class="text-slate-500">Нет вступлений в этом слоте.</p>
          <p class="font-semibold text-amber-200/90">Модерация</p>
          <div v-for="(m, mi) in partnerSlotDetailModerationDisplay" :key="`md-${mi}-${m.user_id}`" class="rounded border border-slate-700/80 bg-slate-900/60 px-2 py-1">
            {{ m.created_at }} · {{ partnerActionLabelRu(m.action) }} · {{ partnerReasonRu(m.reason) }} ·
            <a
              v-if="partnerUserHref(m)"
              href="#"
              class="text-sky-300 underline decoration-sky-500/50 underline-offset-2 hover:text-sky-200"
              @click.prevent.stop="openExternalLink(partnerUserHref(m))"
            >{{ partnerUserLabel(m) }}</a>
            <span v-else>{{ partnerUserLabel(m) }}</span>
          </div>
          <p v-if="!partnerSlotDetailModerationDisplay.length" class="text-slate-500">Нет записей модерации в этом слоте.</p>
        </div>
      </div>
    </div>

    <div
      v-if="showPartnerHourlyModal"
      class="fixed inset-0 z-[68] flex items-end justify-center overflow-y-auto overscroll-contain bg-black/70 p-3 pt-[max(1rem,calc(env(safe-area-inset-top,0px)+88px))] pb-[max(1rem,calc(5.5rem+env(safe-area-inset-bottom,0px)))] md:items-center"
      @click.self="showPartnerHourlyModal = false"
    >
      <div
        class="flex h-[min(86vh,calc(100dvh-168px))] max-h-[86vh] w-full max-w-3xl min-h-0 flex-col overflow-hidden rounded-2xl border border-indigo-400/50 bg-slate-950 p-4 shadow-2xl md:h-[min(88vh,calc(100dvh-120px))]"
        @click.stop
      >
        <div class="mb-2 flex shrink-0 items-center justify-between gap-2">
          <div>
            <p class="text-base font-semibold text-white">Активность по времени</p>
            <p v-if="partnerActivityPeriodLine" class="text-[10px] text-indigo-200/80">{{ partnerActivityPeriodLine }}</p>
          </div>
          <button type="button" class="bc-tool-btn" @click="showPartnerHourlyModal = false">✕</button>
        </div>
        <div class="relative mb-2 shrink-0 rounded-xl border border-slate-700/80 bg-slate-900/60 p-2 pr-11">
          <p class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-300">Выбор чата/канала</p>
          <button
            type="button"
            class="w-full rounded-lg border border-indigo-400/45 bg-indigo-500/15 px-3 py-2 text-left text-xs font-semibold text-indigo-100 hover:bg-indigo-500/25"
            @click="showPartnerHourlyChatPicker = true"
          >
            {{ partnerSelectedChatMeta?.title || 'Все подключенные объекты' }}
            <span class="ml-2 text-[10px] text-indigo-200/80">Нажмите, чтобы выбрать</span>
          </button>
          <button
            type="button"
            v-bind="partnerHelpBind('tgstatPack', 'trailing')"
            @click.stop.prevent="partnerShowHelp('tgstatPack')"
            @mousedown.stop
          >
            i
          </button>
        </div>
        <div class="min-h-0 flex-1 touch-pan-y overflow-y-auto overscroll-y-contain pr-1">
          <div v-if="partnerHourlyLoading" class="py-8 text-center text-sm text-slate-400">Загрузка…</div>
          <div v-else class="space-y-2">
            <div class="rounded-xl border border-slate-600/70 bg-slate-900/75 p-3 text-slate-100">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-4xl font-extrabold leading-none">{{ partnerTgstatDisplay.subscribers.total }}</p>
                  <div class="mt-2 space-y-0.5 text-[12px]">
                    <p><span class="inline-block min-w-14 font-semibold text-emerald-300">{{ partnerTgstatDisplay.subscribers.today }}</span> сегодня</p>
                    <p><span class="inline-block min-w-14 font-semibold text-rose-300">{{ partnerTgstatDisplay.subscribers.week }}</span> за неделю</p>
                    <p><span class="inline-block min-w-14 font-semibold text-emerald-300">{{ partnerTgstatDisplay.subscribers.month }}</span> за месяц</p>
                  </div>
                </div>
                <div class="w-[42%] text-right">
                  <p class="text-[11px] uppercase tracking-wide text-slate-300">подписчики</p>
                  <div class="relative mt-3 h-14 w-full">
                    <svg viewBox="0 0 140 42" class="h-14 w-full text-cyan-300/85">
                      <path :d="partnerMiniCharts.joinsPath" fill="none" stroke="currentColor" stroke-width="2" />
                      <line
                        v-if="partnerChartHover?.key === 'subs'"
                        :x1="partnerChartHover.x"
                        :x2="partnerChartHover.x"
                        y1="0"
                        y2="42"
                        stroke="currentColor"
                        stroke-opacity="0.4"
                        stroke-dasharray="2 2"
                      />
                      <circle v-if="partnerChartHover?.key === 'subs'" :cx="partnerChartHover.x" :cy="partnerChartHover.y" r="2.6" fill="currentColor" stroke="white" stroke-width="1" />
                      <rect
                        x="0"
                        y="0"
                        width="140"
                        height="42"
                        fill="transparent"
                        @mousemove="partnerChartHoverMove($event, 'subs', partnerChartSeries.joins, partnerChartLabels)"
                        @mouseleave="partnerChartHoverLeave('subs')"
                      />
                    </svg>
                    <div
                      v-if="partnerChartHover?.key === 'subs'"
                      class="pointer-events-none absolute z-10 min-w-[78px] -translate-x-1/2 -translate-y-full rounded-md border border-white/15 bg-slate-900/95 px-2 py-1 text-[10px] text-white shadow-lg"
                      :style="{ left: `${partnerChartHover.xPx}px`, top: `${Math.max(12, partnerChartHover.yPx - 8)}px` }"
                    >
                      <p class="text-slate-300">{{ partnerChartHover.label }}</p>
                      <p class="font-semibold">{{ partnerFmtInt(partnerChartHover.value) }}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="rounded-xl border border-slate-600/70 bg-slate-900/75 p-3 text-slate-100">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-4xl font-extrabold leading-none">{{ partnerTgstatDisplay.citation.total }}</p>
                  <div class="mt-2 space-y-0.5 text-[12px]">
                    <p><span class="inline-block min-w-16 font-semibold">{{ partnerTgstatDisplay.citation.channels }}</span> уп. каналов</p>
                    <p><span class="inline-block min-w-16 font-semibold">{{ partnerTgstatDisplay.citation.mentions }}</span> упоминаний</p>
                    <p><span class="inline-block min-w-16 font-semibold">{{ partnerTgstatDisplay.citation.reposts }}</span> репостов</p>
                  </div>
                </div>
                <div class="w-[42%] text-right">
                  <p class="text-[11px] uppercase tracking-wide text-slate-300">индекс цитирования</p>
                  <div class="relative mt-3 h-14 w-full">
                    <svg viewBox="0 0 140 42" class="h-14 w-full text-emerald-300/90">
                      <path :d="partnerMiniCharts.moderationPath" fill="none" stroke="currentColor" stroke-width="2" />
                      <line v-if="partnerChartHover?.key === 'citation'" :x1="partnerChartHover.x" :x2="partnerChartHover.x" y1="0" y2="42" stroke="currentColor" stroke-opacity="0.4" stroke-dasharray="2 2" />
                      <circle v-if="partnerChartHover?.key === 'citation'" :cx="partnerChartHover.x" :cy="partnerChartHover.y" r="2.6" fill="currentColor" stroke="white" stroke-width="1" />
                      <rect x="0" y="0" width="140" height="42" fill="transparent" @mousemove="partnerChartHoverMove($event, 'citation', partnerChartSeries.moderation, partnerChartLabels)" @mouseleave="partnerChartHoverLeave('citation')" />
                    </svg>
                    <div v-if="partnerChartHover?.key === 'citation'" class="pointer-events-none absolute z-10 min-w-[78px] -translate-x-1/2 -translate-y-full rounded-md border border-white/15 bg-slate-900/95 px-2 py-1 text-[10px] text-white shadow-lg" :style="{ left: `${partnerChartHover.xPx}px`, top: `${Math.max(12, partnerChartHover.yPx - 8)}px` }">
                      <p class="text-slate-300">{{ partnerChartHover.label }}</p>
                      <p class="font-semibold">{{ partnerFmtInt(partnerChartHover.value) }}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="rounded-xl border border-slate-600/70 bg-slate-900/75 p-3 text-slate-100">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-4xl font-extrabold leading-none">{{ partnerTgstatDisplay.avgReach.total }}</p>
                  <div class="mt-2 space-y-0.5 text-[12px]">
                    <p><span class="inline-block min-w-16 font-semibold">{{ partnerTgstatDisplay.avgReach.err }}</span> ERR</p>
                    <p><span class="inline-block min-w-16 font-semibold">{{ partnerTgstatDisplay.avgReach.err24 }}</span> ERR24</p>
                  </div>
                </div>
                <div class="w-[42%] text-right">
                  <p class="text-[11px] uppercase tracking-wide text-slate-300">средний охват<br>1 публикации</p>
                  <div class="relative mt-3 h-14 w-full">
                    <svg viewBox="0 0 140 42" class="h-14 w-full text-amber-300/90">
                      <path :d="partnerMiniCharts.spamPath" fill="none" stroke="currentColor" stroke-width="2" />
                      <line v-if="partnerChartHover?.key === 'avgReach'" :x1="partnerChartHover.x" :x2="partnerChartHover.x" y1="0" y2="42" stroke="currentColor" stroke-opacity="0.4" stroke-dasharray="2 2" />
                      <circle v-if="partnerChartHover?.key === 'avgReach'" :cx="partnerChartHover.x" :cy="partnerChartHover.y" r="2.6" fill="currentColor" stroke="white" stroke-width="1" />
                      <rect x="0" y="0" width="140" height="42" fill="transparent" @mousemove="partnerChartHoverMove($event, 'avgReach', partnerChartSeries.spam, partnerChartLabels)" @mouseleave="partnerChartHoverLeave('avgReach')" />
                    </svg>
                    <div v-if="partnerChartHover?.key === 'avgReach'" class="pointer-events-none absolute z-10 min-w-[78px] -translate-x-1/2 -translate-y-full rounded-md border border-white/15 bg-slate-900/95 px-2 py-1 text-[10px] text-white shadow-lg" :style="{ left: `${partnerChartHover.xPx}px`, top: `${Math.max(12, partnerChartHover.yPx - 8)}px` }">
                      <p class="text-slate-300">{{ partnerChartHover.label }}</p>
                      <p class="font-semibold">{{ partnerFmtInt(partnerChartHover.value) }}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="rounded-xl border border-slate-600/70 bg-slate-900/75 p-3 text-slate-100">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-4xl font-extrabold leading-none">{{ partnerTgstatDisplay.adReach.total }}</p>
                  <div class="mt-2 space-y-0.5 text-[12px]">
                    <p><span class="inline-block min-w-16 font-semibold">{{ partnerTgstatDisplay.adReach.h12 }}</span> за 12 часов</p>
                    <p><span class="inline-block min-w-16 font-semibold">{{ partnerTgstatDisplay.adReach.h24 }}</span> за 24 часа</p>
                    <p><span class="inline-block min-w-16 font-semibold">{{ partnerTgstatDisplay.adReach.h48 }}</span> за 48 часов</p>
                  </div>
                </div>
                <div class="w-[42%] text-right">
                  <p class="text-[11px] uppercase tracking-wide text-slate-300">средний рекламный<br>охват 1 публикации</p>
                  <div class="relative mt-3 h-14 w-full">
                    <svg viewBox="0 0 140 42" class="h-14 w-full text-orange-300/90">
                      <path :d="partnerMiniCharts.eventsPath" fill="none" stroke="currentColor" stroke-width="2" />
                      <line v-if="partnerChartHover?.key === 'adReach'" :x1="partnerChartHover.x" :x2="partnerChartHover.x" y1="0" y2="42" stroke="currentColor" stroke-opacity="0.4" stroke-dasharray="2 2" />
                      <circle v-if="partnerChartHover?.key === 'adReach'" :cx="partnerChartHover.x" :cy="partnerChartHover.y" r="2.6" fill="currentColor" stroke="white" stroke-width="1" />
                      <rect x="0" y="0" width="140" height="42" fill="transparent" @mousemove="partnerChartHoverMove($event, 'adReach', partnerChartSeries.events, partnerChartLabels)" @mouseleave="partnerChartHoverLeave('adReach')" />
                    </svg>
                    <div v-if="partnerChartHover?.key === 'adReach'" class="pointer-events-none absolute z-10 min-w-[78px] -translate-x-1/2 -translate-y-full rounded-md border border-white/15 bg-slate-900/95 px-2 py-1 text-[10px] text-white shadow-lg" :style="{ left: `${partnerChartHover.xPx}px`, top: `${Math.max(12, partnerChartHover.yPx - 8)}px` }">
                      <p class="text-slate-300">{{ partnerChartHover.label }}</p>
                      <p class="font-semibold">{{ partnerFmtInt(partnerChartHover.value) }}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="rounded-xl border border-slate-600/70 bg-slate-900/75 p-3 text-slate-100">
              <p class="text-4xl font-extrabold leading-none">{{ partnerTgstatDisplay.age.period }}</p>
              <div class="mt-3 grid grid-cols-2 gap-3 text-[12px]">
                <div>
                  <p class="font-semibold">{{ partnerTgstatDisplay.age.createdAt }}</p>
                  <p class="text-slate-400">подключен в Guard</p>
                </div>
                <div>
                  <p class="font-semibold">{{ partnerTgstatDisplay.age.addedAt }}</p>
                  <p class="text-slate-400">последняя активность</p>
                </div>
              </div>
              <p class="mt-2 text-right text-[11px] uppercase tracking-wide text-slate-300">возраст в системе</p>
            </div>

            <div class="rounded-xl border border-slate-600/70 bg-slate-900/75 p-3 text-slate-100">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-4xl font-extrabold leading-none">{{ partnerTgstatDisplay.posts.total }} всего</p>
                  <div class="mt-2 space-y-0.5 text-[12px]">
                    <p><span class="inline-block min-w-14 font-semibold">{{ partnerTgstatDisplay.posts.yesterday }}</span> вчера</p>
                    <p><span class="inline-block min-w-14 font-semibold">{{ partnerTgstatDisplay.posts.week }}</span> за неделю</p>
                    <p><span class="inline-block min-w-14 font-semibold">{{ partnerTgstatDisplay.posts.month }}</span> за месяц</p>
                  </div>
                </div>
                <div class="w-[42%] text-right">
                  <p class="text-[11px] uppercase tracking-wide text-slate-300">публикации</p>
                  <div class="relative mt-3 h-14 w-full">
                    <svg viewBox="0 0 140 42" class="h-14 w-full text-slate-300/90">
                      <path :d="partnerMiniCharts.eventsPath" fill="none" stroke="currentColor" stroke-width="2" />
                      <line v-if="partnerChartHover?.key === 'posts'" :x1="partnerChartHover.x" :x2="partnerChartHover.x" y1="0" y2="42" stroke="currentColor" stroke-opacity="0.4" stroke-dasharray="2 2" />
                      <circle v-if="partnerChartHover?.key === 'posts'" :cx="partnerChartHover.x" :cy="partnerChartHover.y" r="2.6" fill="currentColor" stroke="white" stroke-width="1" />
                      <rect x="0" y="0" width="140" height="42" fill="transparent" @mousemove="partnerChartHoverMove($event, 'posts', partnerChartSeries.events, partnerChartLabels)" @mouseleave="partnerChartHoverLeave('posts')" />
                    </svg>
                    <div v-if="partnerChartHover?.key === 'posts'" class="pointer-events-none absolute z-10 min-w-[78px] -translate-x-1/2 -translate-y-full rounded-md border border-white/15 bg-slate-900/95 px-2 py-1 text-[10px] text-white shadow-lg" :style="{ left: `${partnerChartHover.xPx}px`, top: `${Math.max(12, partnerChartHover.yPx - 8)}px` }">
                      <p class="text-slate-300">{{ partnerChartHover.label }}</p>
                      <p class="font-semibold">{{ partnerFmtInt(partnerChartHover.value) }}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="rounded-xl border border-slate-600/70 bg-slate-900/75 p-3 text-slate-100">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-4xl font-extrabold leading-none">{{ partnerTgstatDisplay.err.readAll }}</p>
                  <p class="mt-2 text-[12px] text-slate-300">подписчиков читают посты канала</p>
                </div>
                <div class="text-right">
                  <p class="text-4xl font-extrabold leading-none">{{ partnerTgstatDisplay.err.read24h }}</p>
                  <p class="mt-2 text-[12px] text-slate-300">читают посты в первые 24 часа<br>после публикации</p>
                </div>
              </div>
              <p class="mt-2 text-right text-[11px] uppercase tracking-wide text-slate-300">вовлеченность подписчиков (ERR)</p>
            </div>

            <div class="rounded-xl border border-slate-600/70 bg-slate-900/75 p-3 text-slate-100">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-4xl font-extrabold leading-none">{{ partnerTgstatDisplay.er.value }}</p>
                  <div class="mt-2 space-y-0.5 text-[12px]">
                    <p><span class="inline-block min-w-14 font-semibold">{{ partnerTgstatDisplay.er.forwards }}</span> пересылки</p>
                    <p><span class="inline-block min-w-14 font-semibold">{{ partnerTgstatDisplay.er.comments }}</span> комментарии</p>
                    <p><span class="inline-block min-w-14 font-semibold">{{ partnerTgstatDisplay.er.reactions }}</span> реакции</p>
                  </div>
                </div>
                <div class="w-[42%] text-right">
                  <p class="text-[11px] uppercase tracking-wide text-slate-300">вовлеченность<br>подписчиков (ER)</p>
                  <div class="relative mt-3 h-14 w-full">
                    <svg viewBox="0 0 140 42" class="h-14 w-full text-fuchsia-300/90">
                      <path :d="partnerMiniCharts.joinsPath" fill="none" stroke="currentColor" stroke-width="2" />
                      <line v-if="partnerChartHover?.key === 'er'" :x1="partnerChartHover.x" :x2="partnerChartHover.x" y1="0" y2="42" stroke="currentColor" stroke-opacity="0.4" stroke-dasharray="2 2" />
                      <circle v-if="partnerChartHover?.key === 'er'" :cx="partnerChartHover.x" :cy="partnerChartHover.y" r="2.6" fill="currentColor" stroke="white" stroke-width="1" />
                      <rect x="0" y="0" width="140" height="42" fill="transparent" @mousemove="partnerChartHoverMove($event, 'er', partnerChartSeries.joins, partnerChartLabels)" @mouseleave="partnerChartHoverLeave('er')" />
                    </svg>
                    <div v-if="partnerChartHover?.key === 'er'" class="pointer-events-none absolute z-10 min-w-[78px] -translate-x-1/2 -translate-y-full rounded-md border border-white/15 bg-slate-900/95 px-2 py-1 text-[10px] text-white shadow-lg" :style="{ left: `${partnerChartHover.xPx}px`, top: `${Math.max(12, partnerChartHover.yPx - 8)}px` }">
                      <p class="text-slate-300">{{ partnerChartHover.label }}</p>
                      <p class="font-semibold">{{ partnerFmtInt(partnerChartHover.value) }}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div class="rounded-xl border border-slate-600/70 bg-slate-900/75 p-3 text-slate-100">
              <div class="mb-2 flex items-center justify-between gap-2">
                <p class="text-[11px] uppercase tracking-wide text-slate-300">пол подписчиков</p>
                <p class="text-[11px] text-slate-400">аудитория: {{ partnerFmtInt(partnerAudienceGender.audience) }}</p>
              </div>
              <div class="flex items-end justify-between gap-3">
                <div>
                  <p class="text-4xl font-extrabold leading-none">{{ partnerAudienceGender.malePct }}%</p>
                  <p class="text-lg font-semibold text-cyan-200">{{ partnerFmtInt(partnerAudienceGender.maleCount) }}</p>
                  <p class="text-[12px] text-slate-300">мужчины</p>
                </div>
                <div class="text-right">
                  <p class="text-4xl font-extrabold leading-none">{{ partnerAudienceGender.femalePct }}%</p>
                  <p class="text-lg font-semibold text-rose-200">{{ partnerFmtInt(partnerAudienceGender.femaleCount) }}</p>
                  <p class="text-[12px] text-slate-300">женщины</p>
                </div>
              </div>
              <div class="mt-3 h-8 overflow-hidden rounded-lg border border-slate-600 bg-slate-950/60">
                <div class="flex h-full w-full">
                  <div
                    class="flex h-full items-center justify-center bg-cyan-500/75 text-sm font-bold text-white"
                    :style="{ width: `${partnerAudienceGender.malePct}%` }"
                  >
                    {{ partnerAudienceGender.malePct }}%
                  </div>
                  <div
                    class="flex h-full items-center justify-center bg-rose-500/80 text-sm font-bold text-white"
                    :style="{ width: `${partnerAudienceGender.femalePct}%` }"
                  >
                    {{ partnerAudienceGender.femalePct }}%
                  </div>
                </div>
              </div>
              <p class="mt-2 text-[11px] text-slate-400">
                Учтено по именам: {{ partnerFmtInt(partnerAudienceGender.knownTotal) }}, не определено: {{ partnerFmtInt(partnerAudienceGender.unknownCount) }}
                <span v-if="partnerAudienceGender.isEstimate">· оценка</span>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="showPartnerHourlyChatPicker"
      class="fixed inset-0 z-[69] flex items-center justify-center overflow-y-auto overscroll-contain bg-black/75 p-3 pt-[max(1rem,calc(env(safe-area-inset-top,0px)+88px))] pb-[max(1rem,calc(5.5rem+env(safe-area-inset-bottom,0px)))] backdrop-blur-sm"
      @click.self="showPartnerHourlyChatPicker = false"
    >
      <div
        class="flex max-h-[min(84vh,calc(100dvh-170px))] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/[0.1] bg-slate-950/[0.95] shadow-[0_28px_80px_-24px_rgba(0,0,0,0.85)] ring-1 ring-cyan-400/25 backdrop-blur-2xl md:max-h-[min(88vh,34rem)]"
        @click.stop
      >
        <div class="shrink-0 border-b border-slate-700/60 p-4 pb-2">
          <div class="flex items-center justify-between">
            <p class="text-base font-semibold text-white">Выбрать чат / канал</p>
            <button type="button" class="bc-tool-btn" @click="showPartnerHourlyChatPicker = false">✕</button>
          </div>
          <p class="mt-2 text-[11px] leading-snug text-slate-400">
            Показываются все подключенные объекты, включая делегированные.
          </p>
        </div>
        <div class="min-h-0 flex-1 touch-pan-y space-y-3 overflow-y-auto overscroll-contain p-3 text-[11px]">
          <button
            type="button"
            class="w-full rounded-lg border px-3 py-2 text-left"
            :class="partnerHourlyChatId === 'all' ? 'border-violet-300/60 bg-violet-500/20 text-violet-50' : 'border-slate-700 bg-slate-900/70 text-slate-200'"
            @click="selectPartnerChatFromList('all')"
          >
            Все объекты
          </button>
          <template v-if="(partnerChatsGrouped.channels || []).length">
            <p class="text-[10px] font-semibold uppercase tracking-wide text-amber-200/90">Каналы</p>
            <button
              v-for="c in partnerChatsGrouped.channels"
              :key="`ph-pick-ch-${c.id}`"
              type="button"
              class="w-full rounded-lg border px-3 py-2 text-left"
              :class="String(partnerHourlyChatId || 'all') === String(c.id) ? 'border-amber-300/60 bg-amber-500/20 text-amber-50' : 'border-amber-700/40 bg-amber-950/20 text-amber-100'"
              @click="selectPartnerChatFromList(c.id)"
            >
              <div class="flex items-center justify-between gap-2">
                <p class="truncate font-semibold">{{ c.title }}</p>
                <span v-if="c.is_shared" class="rounded border border-violet-500/40 bg-violet-500/20 px-1.5 py-0.5 text-[9px] text-violet-100">делегировано</span>
              </div>
            </button>
          </template>
          <template v-if="(partnerChatsGrouped.groups || []).length">
            <p class="text-[10px] font-semibold uppercase tracking-wide text-cyan-200/90">Группы</p>
            <button
              v-for="c in partnerChatsGrouped.groups"
              :key="`ph-pick-gr-${c.id}`"
              type="button"
              class="w-full rounded-lg border px-3 py-2 text-left"
              :class="String(partnerHourlyChatId || 'all') === String(c.id) ? 'border-cyan-300/60 bg-cyan-500/20 text-cyan-50' : 'border-slate-700 bg-slate-900/70 text-slate-200'"
              @click="selectPartnerChatFromList(c.id)"
            >
              <div class="flex items-center justify-between gap-2">
                <p class="truncate font-semibold">{{ c.title }}</p>
                <span v-if="c.is_shared" class="rounded border border-violet-500/40 bg-violet-500/20 px-1.5 py-0.5 text-[9px] text-violet-100">делегировано</span>
              </div>
            </button>
          </template>
          <p v-if="!(partnerHourlyData?.chats || []).length" class="py-6 text-center text-slate-500">Нет подключенных объектов</p>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="bcSendModalOpen"
        class="fixed inset-0 z-[10100] flex min-h-[100dvh] min-w-0 flex-col bg-[#09090b] pt-[env(safe-area-inset-top,0px)] pb-[env(safe-area-inset-bottom,0px)]"
        @click.self="bcSendModalState === 'sending' ? null : closeBcSendModal()"
      >
        <div
          v-if="bcSendModalState === 'sending'"
          class="flex min-h-[100dvh] w-full max-w-full flex-col px-5"
        >
          <p class="shrink-0 pt-4 text-[16px] font-semibold text-white">Отправка...</p>
          <div class="flex min-h-0 flex-1 flex-col items-center justify-center">
            <div class="relative mx-auto w-full max-w-[19rem]">
              <div class="relative mx-auto h-[180px] w-[180px]">
                <svg
                  class="pointer-events-none absolute left-0 top-0 h-[180px] w-[180px] -rotate-90"
                  viewBox="0 0 120 120"
                  aria-hidden="true"
                >
                  <defs>
                    <linearGradient id="bcSendNeonRing" x1="0%" y1="30%" x2="100%" y2="100%">
                      <stop offset="0%" stop-color="#60a5fa" />
                      <stop offset="50%" stop-color="#6366f1" />
                      <stop offset="100%" stop-color="#8b5cf6" />
                    </linearGradient>
                  </defs>
                  <circle cx="60" cy="60" r="52" fill="none" stroke="rgba(148,163,184,0.14)" stroke-width="8" />
                  <circle
                    cx="60"
                    cy="60"
                    r="52"
                    fill="none"
                    stroke="url(#bcSendNeonRing)"
                    stroke-width="8"
                    stroke-linecap="round"
                    :stroke-dasharray="bcSendCircleDash"
                    class="transition-[stroke-dasharray] duration-300 ease-out"
                  />
                </svg>
                <div
                  class="absolute left-1/2 top-1/2 flex h-[112px] w-[112px] -translate-x-1/2 -translate-y-1/2 items-center justify-center"
                >
                  <span
                    class="pointer-events-none absolute inset-0 rounded-full bg-[radial-gradient(circle,rgba(99,102,241,0.45)_0%,rgba(59,130,246,0.2)_35%,rgba(59,130,246,0.06)_60%,transparent_78%)] blur-[6px] bc-send-icon-pulse"
                    aria-hidden="true"
                  />
                  <img
                    :src="bcTelegramPlaneIconUrl"
                    class="relative h-12 w-12 select-none object-contain drop-shadow-[0_0_24px_rgba(99,102,241,0.95)]"
                    width="36"
                    height="36"
                    alt=""
                  />
                </div>
                <span
                  class="absolute -bottom-0.5 right-[-1.9rem] text-[28px] font-semibold tabular-nums tracking-tight text-white drop-shadow-[0_2px_8px_rgba(0,0,0,0.65)]"
                >
                  {{ bcSendProgressPercent }}%
                </span>
              </div>
            </div>
            <div class="mt-7 w-full max-w-[17.5rem] text-center">
              <p class="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">Отправлено</p>
              <p class="mt-0.5 text-[18px] font-semibold tabular-nums leading-none text-white">
                {{ fmtIntSpace(bcSendProgressDone) }}
                <span class="text-[16px] text-slate-500">из</span>
                {{ fmtIntSpace(bcSendProgressTotal) }}
              </p>
            </div>
          </div>
          <div class="shrink-0 px-0 pb-4 pt-2">
            <button
              type="button"
              class="mx-auto block w-full rounded-2xl border border-white/[0.08] bg-white/[0.06] py-3.5 text-[14px] font-semibold text-white active:scale-[0.99] hover:bg-white/[0.1]"
              @click="bcSendCancelWatching"
            >
              Отменить отправку
            </button>
          </div>
        </div>

        <div
          v-else-if="bcSendModalState === 'done'"
          class="relative mx-auto flex w-full max-w-[22rem] flex-1 flex-col overflow-y-auto overscroll-contain px-4 pb-6 pt-4"
        >
          <p class="text-[17px] font-semibold leading-snug text-white">Рассылка отправлена!</p>
          <div class="mt-5 flex flex-col items-center">
            <div
              class="flex h-[108px] w-[108px] items-center justify-center rounded-full bg-emerald-500/18 shadow-[0_0_48px_-10px_rgba(52,211,153,0.7)] ring-2 ring-emerald-400/40"
            >
              <span class="text-4xl text-emerald-300">✓</span>
            </div>
            <p class="mt-3 text-[14px] text-slate-400">{{ bcSendCompletedAtLabel }}</p>
          </div>

          <div class="mt-5 grid grid-cols-3 gap-2">
            <div class="rounded-xl border border-white/[0.05] bg-white/[0.02] px-2 py-2.5 text-center">
              <p class="text-[10px] text-slate-500">Доставлено</p>
              <p class="mt-1 text-[15px] font-semibold tabular-nums text-white">{{ fmtIntSpace(bcSendDeliveredOk) }}</p>
              <p class="mt-0.5 text-[12px] font-semibold tabular-nums text-emerald-400">
                {{ fmtPctTrim(bcSendDeliveredPct) }}
              </p>
            </div>
            <div class="rounded-xl border border-white/[0.05] bg-white/[0.02] px-2 py-2.5 text-center">
              <p class="text-[10px] text-slate-500">Клики · в ЛС</p>
              <p class="mt-1 text-[15px] font-semibold tabular-nums text-white">{{ fmtIntSpace(bcSendClicks) }}</p>
              <p class="mt-0.5 text-[12px] font-semibold tabular-nums text-emerald-400">
                {{ fmtPctTrim(bcSendClicksPct) }}
              </p>
            </div>
            <div class="rounded-xl border border-white/[0.05] bg-white/[0.02] px-2 py-2.5 text-center">
              <p class="text-[10px] text-slate-500">Переходы · в чаты</p>
              <p class="mt-1 text-[15px] font-semibold tabular-nums text-white">{{ fmtIntSpace(bcSendTransitions) }}</p>
              <p class="mt-0.5 text-[12px] font-semibold tabular-nums text-emerald-400">
                {{ fmtPctTrim(bcSendTransitionsPct) }}
              </p>
            </div>
          </div>
          <div class="mt-2 rounded-xl border border-white/[0.05] bg-white/[0.02] px-3 py-3 text-center">
            <p class="text-[10px] text-slate-500">CTR · охват базы</p>
            <p class="mt-1 text-2xl font-semibold tabular-nums text-emerald-400">{{ fmtPctTrim(bcSendCtrPct) }}</p>
          </div>
          <p class="mt-2 text-center text-[10px] leading-snug text-slate-500">
            «Клики» и «Переходы» здесь — это успешные доставки в личку и в группы/каналы по логам отправки. CTR — доля доставленных сообщений относительно всех подключённых групп/каналов и активных пользователей бота (не клики по ссылкам в тексте).
          </p>

          <div class="mt-4 grid grid-cols-2 gap-2">
            <button
              type="button"
              class="rounded-xl border border-white/[0.08] bg-white/[0.05] py-3 text-[13px] font-semibold text-white hover:bg-white/[0.08]"
              @click="bcSendGoToBroadcasts"
            >
              К рассылкам
            </button>
            <button
              type="button"
              class="rounded-xl bg-gradient-to-r from-violet-600 to-sky-500 py-3 text-[13px] font-semibold text-white shadow-lg shadow-indigo-900/30 hover:brightness-105"
              @click="bcSendOpenStatsFromModal"
            >
              Статистика
            </button>
          </div>
        </div>

        <div
          v-else
          class="mx-auto flex w-full max-w-[22rem] flex-1 flex-col px-4 pb-8 pt-10"
        >
          <div class="flex items-start justify-between gap-2">
            <p class="text-base font-semibold text-white">Ошибка отправки</p>
            <button type="button" class="bc-tool-btn" @click="closeBcSendModal">✕</button>
          </div>
          <p class="mt-3 text-sm leading-relaxed text-slate-200">{{ bcSendModalText || 'Не удалось выполнить рассылку.' }}</p>
          <button
            type="button"
            class="mt-5 w-full rounded-xl border border-white/[0.08] bg-white/[0.06] py-3 text-sm font-semibold text-white hover:bg-white/[0.09]"
            @click="closeBcSendModal"
          >
            Закрыть
          </button>
        </div>
      </div>
    </Teleport>

    <div
      v-if="bcMediaViewerOpen && bcMediaViewerItem"
      class="fixed inset-0 z-[365] flex items-center justify-center bg-black/88 p-3 pt-[max(0.5rem,calc(env(safe-area-inset-top,0px)+48px))] pb-[max(0.75rem,calc(4.5rem+env(safe-area-inset-bottom,0px)))] backdrop-blur-md"
      @click.self="closeBcMediaViewer"
    >
      <div
        class="relative w-full max-w-[min(100vw-1.5rem,48rem)] rounded-2xl border border-white/[0.12] bg-slate-950/[0.92] p-2 shadow-[0_32px_90px_-24px_rgba(0,0,0,0.9)] ring-1 ring-white/[0.06] backdrop-blur-xl"
        @click.stop
      >
        <button
          type="button"
          class="bc-tool-btn absolute right-2 top-2 z-[2] !px-2.5 !py-1 text-[11px]"
          @click="closeBcMediaViewer"
        >
          ✕ Закрыть
        </button>
        <img
          v-if="String(bcMediaViewerItem.kind || '').toLowerCase().includes('photo')"
          :src="bcMediaViewerItem.previewUrl"
          class="mx-auto max-h-[min(82dvh,36rem)] w-auto max-w-full rounded-xl object-contain"
          alt=""
        />
        <video
          v-else
          :src="bcMediaViewerItem.previewUrl"
          class="mx-auto max-h-[min(82dvh,36rem)] w-full max-w-full rounded-xl object-contain"
          controls
          playsinline
        />
        <p v-if="bcMediaViewerItem.name" class="mt-2 truncate px-2 text-center text-[11px] text-slate-400">
          {{ bcMediaViewerItem.name }}
        </p>
      </div>
    </div>

    <Teleport to="body">
    <div
      v-if="bcShowGroupsPicker"
      class="fixed inset-0 z-[10040] flex items-center justify-center bg-black/75 p-3 py-6 pt-[max(0.75rem,calc(env(safe-area-inset-top,0px)+52px))] pb-[max(1rem,calc(5rem+env(safe-area-inset-bottom,0px)))] backdrop-blur-sm"
      @click.self="bcShowGroupsPicker = false"
    >
      <div
        class="flex max-h-[min(88vh,32rem)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/[0.1] bg-slate-950/[0.94] shadow-[0_28px_80px_-24px_rgba(0,0,0,0.85)] ring-1 ring-cyan-400/25 backdrop-blur-2xl"
        @click.stop
      >
        <div class="shrink-0 border-b border-slate-700/60 p-4 pb-2">
          <div class="flex items-center justify-between">
            <p class="text-[26px] font-black text-white leading-none">Выбор групп</p>
            <button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-transparent text-sm text-white/90 hover:bg-white/[0.08]" @click="bcShowGroupsPicker = false">✕</button>
          </div>
          <p class="mt-2 text-[14px] text-slate-300">Выберите группы для рассылки</p>
          <div class="mt-2 flex items-center justify-between gap-2 text-[14px]">
            <span class="text-slate-300">Выбрано: {{ selectedGroupTitles().length }}</span>
            <div class="flex items-center gap-3">
              <button type="button" class="font-semibold text-indigo-300" @click="bcSelectedGroupIds = bcBroadcastGroups.map((x) => bcNormalizeChatId(x))">Выбрать все</button>
              <button type="button" class="font-semibold text-indigo-300" @click="bcSelectedGroupIds = []">Очистить</button>
            </div>
          </div>
          <input
            v-model="bcGroupsSearch"
            type="text"
            placeholder="Поиск групп"
            class="mt-2 w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-500"
          />
        </div>
        <div class="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain px-4 py-2 touch-pan-y">
          <label
            v-for="c in bcFilteredGroups"
            :key="`bcgroup-${bcNormalizeChatId(c)}`"
            class="flex cursor-pointer items-center gap-2 rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2 hover:bg-slate-800/70"
          >
            <input
              type="checkbox"
              :checked="bcSelectedGroupIds.includes(bcNormalizeChatId(c))"
              @change="toggleGroupSelection(bcNormalizeChatId(c))"
            />
            <span class="text-sm text-slate-200">{{ c.title || c.username || bcNormalizeChatId(c) }}</span>
          </label>
          <p v-if="!bcFilteredGroups.length" class="px-2 py-3 text-center text-xs text-slate-500">Нет подходящих групп</p>
        </div>
        <div class="shrink-0 border-t border-slate-700/60 p-4 pt-3">
          <button type="button" class="w-full rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white" @click="sendBcToSelectedGroups">Выбрать</button>
        </div>
      </div>
    </div>
    </Teleport>

    <Teleport to="body">
    <div
      v-if="bcShowChannelsPicker"
      class="fixed inset-0 z-[10040] flex items-center justify-center bg-black/75 p-3 py-6 pt-[max(0.75rem,calc(env(safe-area-inset-top,0px)+52px))] pb-[max(1rem,calc(5rem+env(safe-area-inset-bottom,0px)))] backdrop-blur-sm"
      @click.self="bcShowChannelsPicker = false"
    >
      <div
        class="flex max-h-[min(88vh,32rem)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/[0.1] bg-slate-950/[0.94] shadow-[0_28px_80px_-24px_rgba(0,0,0,0.85)] ring-1 ring-indigo-400/25 backdrop-blur-2xl"
        @click.stop
      >
        <div class="shrink-0 border-b border-slate-700/60 p-4 pb-2">
          <div class="flex items-center justify-between">
            <p class="text-[26px] font-black text-white leading-none">Выбор каналов</p>
            <button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-transparent text-sm text-white/90 hover:bg-white/[0.08]" @click="bcShowChannelsPicker = false">✕</button>
          </div>
          <p class="mt-2 text-[14px] text-slate-300">Выберите каналы для рассылки</p>
          <div class="mt-2 flex items-center justify-between gap-2 text-[14px]">
            <span class="text-slate-300">Выбрано: {{ selectedChannelTitles().length }}</span>
            <div class="flex items-center gap-3">
              <button type="button" class="font-semibold text-indigo-300" @click="bcSelectedChannelIds = bcBroadcastChannels.map((x) => bcNormalizeChatId(x))">Выбрать все</button>
              <button type="button" class="font-semibold text-indigo-300" @click="bcSelectedChannelIds = []">Очистить</button>
            </div>
          </div>
          <input
            v-model="bcChannelsSearch"
            type="text"
            placeholder="Поиск каналов"
            class="mt-2 w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-500"
          />
        </div>
        <div class="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain px-4 py-2 touch-pan-y">
          <label
            v-for="c in bcFilteredChannels"
            :key="`bcchan-${bcNormalizeChatId(c)}`"
            class="flex cursor-pointer items-center gap-2 rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2 hover:bg-slate-800/70"
          >
            <input
              type="checkbox"
              :checked="bcSelectedChannelIds.includes(bcNormalizeChatId(c))"
              @change="toggleChannelSelection(bcNormalizeChatId(c))"
            />
            <span class="text-sm text-slate-200">{{ c.title || c.username || bcNormalizeChatId(c) }}</span>
          </label>
          <p v-if="!bcFilteredChannels.length" class="px-2 py-3 text-center text-xs text-slate-500">Нет каналов в этом режиме</p>
        </div>
        <div class="shrink-0 border-t border-slate-700/60 p-4 pt-3">
          <button type="button" class="w-full rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white" @click="sendBcToSelectedChannels">Выбрать</button>
        </div>
      </div>
    </div>
    </Teleport>

    <Teleport to="body">
    <div
      v-if="bcShowBotsPicker"
      class="fixed inset-0 z-[10040] flex items-center justify-center bg-black/75 p-3 py-6 pt-[max(0.75rem,calc(env(safe-area-inset-top,0px)+52px))] pb-[max(1rem,calc(5rem+env(safe-area-inset-bottom,0px)))] backdrop-blur-sm"
      @click.self="bcShowBotsPicker = false"
    >
      <div
        class="flex max-h-[min(88vh,32rem)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/[0.1] bg-slate-950/[0.94] shadow-[0_28px_80px_-24px_rgba(0,0,0,0.85)] ring-1 ring-indigo-400/25 backdrop-blur-2xl"
        @click.stop
      >
        <div class="shrink-0 border-b border-slate-700/60 p-4 pb-2">
          <div class="flex items-center justify-between">
            <p class="text-[26px] font-black text-white leading-none">Выбор ботов</p>
            <button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-transparent text-sm text-white/90 hover:bg-white/[0.08]" @click="bcShowBotsPicker = false">✕</button>
          </div>
          <p class="mt-2 text-[14px] text-slate-300">Выберите получателей в личку</p>
          <div class="mt-2 flex items-center justify-between gap-2 text-[14px]">
            <span class="text-slate-300">Выбрано: {{ bcSelectedBotRecipientIds.length }}</span>
            <div class="flex items-center gap-3">
              <button type="button" class="font-semibold text-indigo-300" @click="bcSelectedBotRecipientIds = bcBotRecipients.map((x) => Number(x.id))">Выбрать все</button>
              <button type="button" class="font-semibold text-indigo-300" @click="bcSelectedBotRecipientIds = []">Очистить</button>
            </div>
          </div>
          <input
            v-model="bcBotsSearch"
            type="text"
            placeholder="Поиск ботов"
            class="mt-2 w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-500"
          />
        </div>
        <div class="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain px-4 py-2 touch-pan-y">
          <label
            v-for="b in bcFilteredBots"
            :key="`bcbot-${b.id}`"
            class="flex cursor-pointer items-center gap-2 rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2 hover:bg-slate-800/70"
          >
            <input
              type="checkbox"
              :checked="bcSelectedBotRecipientIds.includes(Number(b.id))"
              @change="toggleBotRecipientSelection(Number(b.id))"
            />
            <span class="text-sm text-slate-200">{{ b.title }}</span>
          </label>
          <p v-if="!bcFilteredBots.length" class="px-2 py-3 text-center text-xs text-slate-500">Нет доступных получателей</p>
        </div>
        <div class="shrink-0 border-t border-slate-700/60 p-4 pt-3">
          <button type="button" class="w-full rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white" @click="chooseBotRecipients">Выбрать</button>
        </div>
      </div>
    </div>
    </Teleport>

    <div
      v-if="bcShowPreview && bcPreviewItem"
      class="bc-modal-tg-host fixed inset-0 z-[340] flex items-center justify-center bg-black/80 backdrop-blur-md"
      @click.self="closeBcPreview"
    >
      <div
        class="flex max-h-[min(88vh,40rem)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/[0.1] bg-zinc-950/[0.94] shadow-[0_28px_80px_-24px_rgba(0,0,0,0.88)] ring-1 ring-white/[0.06] backdrop-blur-2xl"
        @click.stop
      >
        <div class="shrink-0 border-b border-white/[0.08] bg-zinc-900/60 p-4 pb-2 backdrop-blur-md">
          <div class="flex items-center justify-between gap-2">
            <p class="text-base font-semibold text-zinc-100">Просмотр черновика</p>
            <button type="button" class="bc-tool-btn !px-2.5 !py-1" @click="closeBcPreview">✕</button>
          </div>
          <p class="mt-2 text-xs text-zinc-400">Название: {{ bcPreviewItem.title || 'Без названия' }}</p>
          <p v-if="bcPreviewItem.error_message" class="mt-1 text-xs text-rose-300">Ошибка последней отправки: {{ bcPreviewItem.error_message }}</p>
        </div>
        <div
          class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-3 touch-pan-y"
          @click.self="closeBcPreview"
        >
          <div v-if="bcPreviewMediaThumbs.length" class="flex flex-wrap gap-2">
            <button
              v-for="(t, ti) in bcPreviewMediaThumbs"
              :key="`pvthumb-${ti}`"
              type="button"
              class="relative h-16 w-16 shrink-0 overflow-hidden rounded-xl border border-white/15 bg-zinc-950/80 shadow-md ring-1 ring-white/[0.06] transition hover:border-cyan-400/35"
              :title="t.name || 'Открыть'"
              @click="openBcMediaViewer(t)"
            >
              <img
                v-if="t.kind === 'photo'"
                :src="t.previewUrl"
                class="h-full w-full object-cover"
                alt=""
              />
              <video
                v-else
                :src="t.previewUrl"
                class="h-full w-full object-cover"
                muted
                playsinline
              />
            </button>
          </div>
          <div class="mt-3 rounded-xl border border-white/[0.08] bg-zinc-950/55 p-3 ring-1 ring-white/[0.04]">
            <div
              class="max-h-[50vh] overflow-y-auto text-sm leading-relaxed text-zinc-100 whitespace-pre-wrap"
              v-html="bcPreviewItem.body_text || 'Без текста'"
            />
          </div>
          <div v-if="previewKeyboardRows(bcPreviewItem).length" class="mt-3 space-y-1">
            <p class="text-xs text-zinc-500">Кнопки из поста:</p>
            <div v-for="(row, ri) in previewKeyboardRows(bcPreviewItem)" :key="`pv-row-${ri}`" class="flex flex-wrap gap-1">
              <span
                v-for="(btn, bi) in row"
                :key="`pv-btn-${ri}-${bi}`"
                class="rounded-md border border-white/[0.1] bg-zinc-900/80 px-2 py-1 text-xs text-zinc-200"
              >
                {{ btn.text }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="bcEditModalOpen"
      class="bc-modal-tg-host fixed inset-0 z-50 flex items-start justify-center bg-black/60 md:items-center"
      @click.self="bcEditModalOpen = false"
    >
      <div class="w-full max-w-2xl rounded-2xl border border-violet-400/50 bg-slate-900 p-4 shadow-2xl">
        <div class="mb-2 flex items-center justify-between">
          <p class="text-base font-semibold text-white">Исправить пост</p>
          <button type="button" class="bc-tool-btn" @click="bcEditModalOpen = false">✕</button>
        </div>
        <input
          v-model="bcEditTitle"
          type="text"
          class="bc-post-input w-full rounded-xl border border-slate-600 bg-slate-950 px-3 py-2 text-sm"
          placeholder="Название поста"
        />
        <div class="mt-2 flex flex-wrap gap-1">
          <button type="button" class="bc-tool-btn" @mousedown.prevent @click="bcEditBold"><b>Ж</b></button>
          <button type="button" class="bc-tool-btn" @mousedown.prevent @click="bcEditItalic"><i>К</i></button>
          <button type="button" class="bc-tool-btn" @mousedown.prevent @click="bcEditUnderline"><u>Ч</u></button>
          <button type="button" class="bc-tool-btn" @mousedown.prevent @click="bcEditStrike"><s>З</s></button>
          <button type="button" class="bc-tool-btn" @mousedown.prevent @click="bcEditLink">🔗 Ссылка</button>
          <button type="button" class="bc-tool-btn" @mousedown.prevent @click="bcToggleEmojiOpen">😀 Смайлы</button>
        </div>
        <div v-show="bcEmojiOpen" class="bc-emoji-popover mt-2">
          <emoji-picker
            v-if="bcEmojiPickerReady"
            class="bc-emoji-picker"
            @emoji-click="onBcEditEmojiClick"
          />
        </div>
        <div
          ref="bcEditBodyRef"
          class="bc-editor mt-2 h-56 overflow-y-auto rounded-xl border border-slate-600 bg-slate-950 px-3 py-2.5 text-sm leading-relaxed"
          contenteditable="true"
          @input="onBcEditInput"
        />
        <div class="mt-3 flex gap-2">
          <button type="button" class="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white" :disabled="bcSaving" @click="saveBcEditModal">Сохранить</button>
          <button type="button" class="bc-tool-btn" @click="bcEditModalOpen = false">Отмена</button>
        </div>
      </div>
    </div>

    <div
      v-if="bcLinkModalOpen"
      class="bc-modal-tg-host fixed inset-0 z-50 flex items-start justify-center bg-black/60 md:items-center"
      @click.self="bcLinkModalOpen = false"
    >
      <div class="w-full max-w-md rounded-2xl border border-violet-400/50 bg-slate-900 p-4 shadow-2xl">
        <div class="mb-2 flex items-center justify-between">
          <p class="text-base font-semibold text-white">Добавить ссылку</p>
          <button type="button" class="bc-tool-btn" @click="bcLinkModalOpen = false">✕</button>
        </div>
        <input
          v-model="bcLinkUrl"
          type="text"
          placeholder="https://..."
          class="bc-post-input w-full rounded-xl border border-slate-600 bg-slate-950 px-3 py-2 text-sm"
        />
        <div class="mt-3 flex gap-2">
          <button type="button" class="rounded-xl bg-violet-600 px-4 py-2 text-sm font-semibold text-white" @click="bcApplyLinkModal">Применить</button>
          <button type="button" class="bc-tool-btn" @click="bcLinkModalOpen = false">Отмена</button>
        </div>
      </div>
    </div>

    <div
      v-if="partnerHelpOpen"
      class="bc-modal-tg-host fixed inset-0 z-[310] flex items-start justify-center bg-black/60 md:items-center"
      @click.self="partnerHelpOpen = false"
    >
      <div class="w-full max-w-lg rounded-2xl border border-cyan-500/40 bg-slate-900 p-4 shadow-2xl">
        <div class="mb-2 flex items-center justify-between">
          <p class="text-base font-semibold text-white">{{ partnerHelpTitle }}</p>
          <button type="button" class="bc-tool-btn" @click="partnerHelpOpen = false">✕</button>
        </div>
        <div class="max-h-[min(60vh,28rem)] space-y-2.5 overflow-y-auto text-left text-sm leading-snug text-slate-300">
          <p v-for="(ln, pi) in partnerHelpLines" :key="`ph-${pi}`">{{ ln }}</p>
        </div>
      </div>
    </div>

    <div
      v-if="showPayoutHelp"
      class="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-3 md:items-center"
      @click.self="showPayoutHelp = false"
    >
      <div class="w-full max-w-md rounded-2xl border border-sky-300/50 bg-white p-4 shadow-2xl dark:border-sky-700/60 dark:bg-gray-800">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-base font-semibold text-gray-900 dark:text-white">😈 Выплаты — без суеты</h3>
          <button
            type="button"
            class="rounded-lg px-2 py-1 text-sm text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700"
            @click="showPayoutHelp = false"
          >
            ✕
          </button>
        </div>
        <ol class="list-decimal space-y-1.5 pl-4 text-sm text-gray-700 dark:text-gray-300">
          <li>Глянь сумму заявки и что реально есть на балансе — я не умею печатать деньги из воздуха.</li>
          <li>Заявки принимаешь до понедельника; переводы обычно в следующий понедельник (ориентир: {{ nextMondayLabel() }}).</li>
          <li>Если реквизиты один в один у разных людей — лучше «Заморозить» и разобраться, чем потом объясняться.</li>
          <li>Если всё чисто — переведи вручную через банк, как тебе удобно.</li>
          <li>После перевода жми «Выплатить» и подтверждай — человеку улетит уведомление, что я зафиксировал выплату.</li>
          <li>Пахнет фродом — «Отклонить»; нужно время на проверку — «Заморозить», без драмы в чате.</li>
        </ol>
      </div>
    </div>
    </div>
  </div>
</template>

<style scoped>
.bc-tool-btn {
  @apply rounded-xl border border-white/[0.14] bg-slate-800/[0.88] px-2.5 py-1 text-xs font-medium text-slate-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.07),0_10px_28px_-14px_rgba(0,0,0,0.55)] backdrop-blur-md transition hover:border-cyan-400/35 hover:bg-slate-700/90 hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.1),0_12px_32px_-10px_rgba(34,211,238,0.18)];
}
.bc-tool-active {
  @apply border-emerald-400/60 bg-emerald-900/45 text-emerald-50 shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_0_20px_-6px_rgba(52,211,153,0.35)];
}
.bc-emoji-popover {
  @apply overflow-hidden rounded-xl border border-violet-500/35 bg-slate-950/95 shadow-[0_0_28px_-8px_rgba(139,92,246,0.35)] ring-1 ring-cyan-500/15;
}
.bc-spinner {
  width: 0.8rem;
  height: 0.8rem;
  border: 2px solid rgba(255,255,255,0.35);
  border-top-color: #ffffff;
  border-radius: 9999px;
  animation: bc-spin 0.8s linear infinite;
}
.bc-hourglass {
  display: inline-flex;
  font-size: 1.35rem;
  line-height: 1;
  animation: bc-hourglass-pulse 0.95s ease-in-out infinite;
}
@keyframes bc-spin {
  to { transform: rotate(360deg); }
}
@keyframes bc-hourglass-pulse {
  0% { transform: rotate(0deg) scale(1); opacity: 0.92; }
  50% { transform: rotate(180deg) scale(1.08); opacity: 1; }
  100% { transform: rotate(360deg) scale(1); opacity: 0.92; }
}
.bc-send-icon-pulse {
  animation: bc-send-icon-pulse 3s ease-in-out infinite;
}
@keyframes bc-send-icon-pulse {
  0% { transform: scale(0.95); opacity: 0.55; }
  50% { transform: scale(1.12); opacity: 0.9; }
  100% { transform: scale(0.95); opacity: 0.55; }
}
/* Поля поста: явный светлый текст (Telegram WebView / без класса .dark на <html>) */
.bc-post-input {
  color: #f8fafc !important;
  caret-color: #f8fafc;
  -webkit-text-fill-color: #f8fafc;
}
.bc-post-input::placeholder {
  color: #f8fafc !important;
  opacity: 0.55;
  -webkit-text-fill-color: #f8fafc;
}
.bc-editor {
  color: #f8fafc !important;
  caret-color: #f8fafc !important;
  -webkit-text-fill-color: #f8fafc;
  background-color: rgb(9 9 11) !important;
}
.bc-broadcast-i {
  @apply !inline-flex !h-7 !w-7 !shrink-0 !items-center !justify-center !rounded-full !p-0 !text-[10px] !font-bold !leading-none;
}
.bc-draft-emoji-btn {
  @apply inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/[0.14] bg-zinc-900/85 text-[15px] leading-none shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-sm transition hover:border-cyan-400/35 hover:bg-zinc-800/90 active:scale-[0.97];
}
.bc-draft-list-card:focus-visible {
  box-shadow: 0 0 0 2px rgba(34, 211, 238, 0.35);
}
.bc-editor :deep(p),
.bc-editor :deep(div),
.bc-editor :deep(span),
.bc-editor :deep(b),
.bc-editor :deep(i),
.bc-editor :deep(u),
.bc-editor :deep(s),
.bc-editor :deep(br) {
  color: #f8fafc !important;
  -webkit-text-fill-color: #f8fafc;
}
.bc-editor:empty:before {
  content: "Напиши сообщение…";
  color: #94a3b8 !important;
  -webkit-text-fill-color: #94a3b8;
}
.bc-editor :deep([data-spoiler="1"]),
.bc-editor :deep(tg-spoiler) {
  color: transparent !important;
  -webkit-text-fill-color: transparent;
  border-radius: 0.35rem;
  padding: 0 0.2rem;
  background-color: rgba(148, 163, 184, 0.22);
  background-image: radial-gradient(rgba(226, 232, 240, 0.9) 0.85px, transparent 0.9px);
  background-size: 5px 5px;
  transition: color .15s ease, background-color .15s ease;
}
.bc-editor :deep([data-spoiler="1"]:hover),
.bc-editor :deep(tg-spoiler:hover) {
  color: #e2e8f0 !important;
  -webkit-text-fill-color: #e2e8f0;
}
.bc-editor :deep([data-spoiler="1"].reveal),
.bc-editor :deep(tg-spoiler.reveal) {
  color: #e2e8f0 !important;
  -webkit-text-fill-color: #e2e8f0;
}
.bc-editor :deep(a) {
  color: #60a5fa !important;
  -webkit-text-fill-color: #60a5fa;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.bc-editor :deep(blockquote) {
  margin: 0.35rem 0;
  padding: 0.35rem 0.65rem;
  border-left: 3px solid rgba(59, 130, 246, 0.85);
  background: rgba(59, 130, 246, 0.10);
  border-radius: 0.4rem;
  color: #e2e8f0 !important;
  -webkit-text-fill-color: #e2e8f0;
}
.bc-editor code {
  background: rgba(148, 163, 184, 0.2);
  border-radius: 0.35rem;
  padding: 0.05rem 0.3rem;
  color: #f8fafc !important;
  -webkit-text-fill-color: #f8fafc;
}
.bc-autopost-modal-overlay {
  -webkit-overflow-scrolling: touch;
}
.bc-autopost-modal-card .min-h-0.flex-1.overflow-y-auto {
  -webkit-overflow-scrolling: touch;
}
.bc-modal-tg-host {
  padding-left: max(0.75rem, env(safe-area-inset-left, 0px));
  padding-right: max(0.75rem, env(safe-area-inset-right, 0px));
  /* нижнее меню Telegram / мини-приложение — не прятать кнопки модалки */
  padding-bottom: max(1rem, calc(4.5rem + env(safe-area-inset-bottom, 0px)));
  padding-top: max(0.75rem, calc(env(safe-area-inset-top, 0px) + 52px));
}
@media (min-width: 768px) {
  .bc-modal-tg-host {
    padding-top: max(1rem, calc(env(safe-area-inset-top, 0px) + 0.75rem));
    padding-bottom: max(1rem, calc(1.25rem + env(safe-area-inset-bottom, 0px)));
  }
}
</style>

<style>
/* emoji-picker-element: тема под тёмную админку */
.bc-emoji-picker {
  --background: #0f172a;
  --border-color: #334155;
  --button-hover-background: #1e293b;
  --category-font-color: #94a3b8;
  --indicator-color: #8b5cf6;
  --input-border-color: #475569;
  --input-font-color: #f1f5f9;
  --input-placeholder-color: #64748b;
  --outline-color: #8b5cf6;
  width: 100%;
  max-width: 100%;
  height: 22rem;
}
</style>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import { useModalScrollLock } from '../composables/useModalScrollLock.js'
import { formatDateTimeShortRu } from '../utils/formatDateTime'
import { openTelegramDeepLink } from '../utils/openTelegramDeepLink'
import { resolveModerationTrigger } from '../utils/moderationTrigger.js'
import ChatAvatar from './ChatAvatar.vue'

const { t: tt, te } = useI18n()

const props = defineProps({
  summary: { type: Object, default: () => ({}) },
  hourlyData: { type: Object, default: () => ({}) },
  audienceGender: { type: Object, default: () => ({}) },
  loading: { type: Boolean, default: false },
  periodKey: { type: String, default: 'today' },
  mode: { type: String, default: 'protection' },
})

const emit = defineEmits(['period-change', 'open-groups', 'report-context-change'])

/** Telegram chat id как строка (без потери точности и без NaN при длинных id). */
function sidChat(v) {
  if (v == null || v === '') return ''
  const s = String(v).trim()
  return /^-?\d+$/.test(s) ? s : ''
}

/** Если сумма by_hour = 0 при ненулевом total_deleted — собрать часы из by_hour_by_reason. */
function rebuildByHourIfSparse(merged) {
  if (!merged || typeof merged !== 'object') return merged
  const raw = Array.isArray(merged.by_hour) && merged.by_hour.length === 24
    ? merged.by_hour.map((x) => Math.max(0, Number(x || 0)))
    : Array.from({ length: 24 }, () => 0)
  const sum = raw.reduce((a, b) => a + b, 0)
  const td = Math.max(0, Number(merged.total_deleted || 0))
  if (sum > 0 || td <= 0) return merged
  const br = merged.by_hour_by_reason
  if (!br || typeof br !== 'object') return merged
  const next = raw.slice()
  for (let h = 0; h < 24; h += 1) {
    let acc = 0
    for (const key of Object.keys(br)) {
      const bucket = br[key]
      if (Array.isArray(bucket)) acc += Math.max(0, Number(bucket[h] || 0))
    }
    next[h] = acc
  }
  if (!next.some((x) => x > 0)) return merged
  return { ...merged, by_hour: next }
}

const statsPeriod = ref(props.periodKey || 'today')
const statsType = ref('all')
const statsSubView = ref('timeline')
const statsScope = ref('all')
const selectedChatId = ref('all')
/** all | groups | channels — фильтр списка чатов в пресетах */
const chatKindFilter = ref('all')
const hoverIndex = ref(-1)
const threatOpen = ref(false)
const threatLoadingId = ref('')
const threatDetails = ref({})
const growthModalOpen = ref(false)
const growthModalKind = ref('joined')
const growthModalLoading = ref(false)
const growthModalItems = ref([])
const growthModalPeriod = ref({ from: '', to: '' })
const reasonHitsModalOpen = ref(false)
const reasonHitsModalLoading = ref(false)
const reasonHitsModalItems = ref([])
const reasonHitsModalLabel = ref('')
const reasonHitsModalReason = ref('')
const reasonHitsModalTotal = ref(0)
const reasonHitsModalHasMore = ref(false)
const reasonHitsModalOffset = ref(0)
let silentRefreshTimer = null

/** Какая pill сейчас грузится по клику пользователя (не тихое автообновление). */
const filterBusyKey = ref('')

function isPillBusy(kind, isActive) {
  if (!isActive) return false
  if (kind === 'period') return Boolean(props.loading) || filterBusyKey.value === 'period'
  return filterBusyKey.value === kind
}

function growthApiChatKind() {
  if (selectedChatId.value !== 'all') return null
  if (chatKindFilter.value === 'channels') return 'channel'
  if (chatKindFilter.value === 'groups') return 'group'
  return null
}

function growthRowAllowed(row) {
  const allowedIds = new Set(activeStatsChatRows.value.map((c) => String(c?.id)))
  if (!allowedIds.size) return true
  return allowedIds.has(String(row?.chat_id))
}

function growthApiPeriod() {
  const k = String(statsPeriod.value || 'today')
  if (k === '6m') return '180d'
  if (k === '1y') return '365d'
  return k
}

function growthUserLabel(row) {
  const un = String(row?.username || '').trim().replace(/^@/, '')
  if (un) return `@${un}`
  const uid = Number(row?.user_id || 0)
  return uid > 0 ? `id ${uid}` : '—'
}

function moderationUsername(row) {
  return String(row?.username || '').trim().replace(/^@+/, '')
}

function moderationFirstName(row) {
  return String(row?.first_name || '').trim()
}

function moderationHitTime(iso) {
  return formatDateTimeShortRu(iso)
}

function openModerationUserProfile(row) {
  const u = moderationUsername(row)
  const uid = Number(row?.user_id || 0)
  if (u) {
    openTelegramDeepLink(`https://t.me/${encodeURIComponent(u)}`)
    return
  }
  if (uid > 0) {
    openTelegramDeepLink(`https://t.me/user?id=${uid}`)
  }
}

function normalizeModerationAction(action) {
  const a = String(action || '').toLowerCase()
  if (a.includes('observe') || a.includes('замеч')) return 'observe'
  if (a.includes('ban')) return 'ban'
  if (a.includes('mute') || a.includes('restrict')) return 'mute'
  return 'delete'
}

function moderationStatusLabel(row) {
  const key = normalizeModerationAction(row?.action)
  const path = `cabinet_stats.protection.hit_status_${key}`
  if (te(path)) return tt(path)
  return tt('cabinet_stats.protection.hit_status_delete')
}

function moderationStatusClass(row) {
  const key = normalizeModerationAction(row?.action)
  if (key === 'ban') return 'bg-rose-500/15 text-rose-200 ring-1 ring-rose-400/30'
  if (key === 'mute') return 'bg-amber-500/15 text-amber-200 ring-1 ring-amber-400/30'
  if (key === 'observe') return 'bg-red-500/15 text-red-200 ring-1 ring-red-400/30'
  return 'bg-slate-500/15 text-slate-200 ring-1 ring-white/10'
}

function moderationTriggerText(row) {
  const raw = resolveModerationTrigger(row)
  if (raw && raw !== '—') return raw
  const k = normalizeReason(row?.reason || '')
  if (k.startsWith('media_')) {
    const sub = k.slice('media_'.length)
    const path = `filters.media_kinds.${sub}`
    if (te(path)) return tt(path)
  }
  if (k.startsWith('button_')) {
    const sub = k.slice('button_'.length)
    const path = `filters.button_kinds.${sub}`
    if (te(path)) return tt(path)
  }
  if (k.startsWith('mention_')) {
    const sub = k.slice('mention_'.length)
    const path = `filters.mention_kinds_short.${sub}`
    if (te(path)) return tt(path)
  }
  return '—'
}

function moderationApiPeriod() {
  const k = String(statsPeriod.value || 'today')
  if (k === '6m') return '180d'
  if (k === '1y') return '365d'
  return k
}

async function loadReasonHitsModal(reset = true) {
  if (!reasonHitsModalReason.value) return
  if (reset) {
    reasonHitsModalLoading.value = true
    reasonHitsModalItems.value = []
    reasonHitsModalOffset.value = 0
    reasonHitsModalTotal.value = 0
    reasonHitsModalHasMore.value = false
  }
  try {
    const chatId = selectedChatId.value === 'all' ? null : Number(selectedChatId.value || 0)
    const r = await api.activityModerationEvents(
      moderationApiPeriod(),
      statsScope.value,
      chatId,
      reasonHitsModalReason.value,
      200,
      reasonHitsModalOffset.value,
    )
    const batch = Array.isArray(r?.items) ? r.items : []
    reasonHitsModalTotal.value = Math.max(0, Number(r?.total || 0))
    reasonHitsModalHasMore.value = Boolean(r?.has_more)
    reasonHitsModalItems.value = reset ? batch : [...reasonHitsModalItems.value, ...batch]
    reasonHitsModalOffset.value = reasonHitsModalItems.value.length
  } catch {
    if (reset) {
      reasonHitsModalItems.value = []
      reasonHitsModalTotal.value = 0
      reasonHitsModalHasMore.value = false
    }
  } finally {
    reasonHitsModalLoading.value = false
  }
}

async function openReasonHitsModal(card) {
  reasonHitsModalLabel.value = String(card?.label || '')
  reasonHitsModalReason.value = String(card?.reason || '')
  reasonHitsModalOpen.value = true
  await loadReasonHitsModal(true)
}

function closeReasonHitsModal() {
  reasonHitsModalOpen.value = false
}

async function loadMoreReasonHits() {
  if (reasonHitsModalLoading.value || !reasonHitsModalHasMore.value) return
  reasonHitsModalLoading.value = true
  await loadReasonHitsModal(false)
}

function growthChatKindLabel(kind) {
  const k = String(kind || 'group').toLowerCase()
  if (k === 'channel') return tt('cabinet_stats.growth.modal_chat_channel')
  return tt('cabinet_stats.growth.modal_chat_group')
}

const growthModalTitle = computed(() => {
  const k = String(growthModalKind.value || 'joined')
  if (k === 'left') return tt('cabinet_stats.growth.modal_title_left')
  if (k === 'net') return tt('cabinet_stats.growth.modal_title_net')
  return tt('cabinet_stats.growth.modal_title_joined')
})

async function openGrowthEventsModal(kind) {
  const k = String(kind || 'joined')
  growthModalKind.value = k
  growthModalOpen.value = true
  growthModalLoading.value = true
  growthModalItems.value = []
  growthModalPeriod.value = { from: '', to: '' }
  try {
    const chatId = selectedChatId.value === 'all' ? null : Number(selectedChatId.value || 0)
    const r = await api.activityGrowthEvents(
      growthApiPeriod(),
      statsScope.value,
      chatId,
      k,
      k === 'net' ? 300 : 250,
      growthApiChatKind(),
    )
    const batch = Array.isArray(r?.items) ? r.items : []
    growthModalItems.value = batch.filter((row) => growthRowAllowed(row))
    growthModalPeriod.value = { from: String(r?.period_from || ''), to: String(r?.period_to || '') }
  } catch {
    growthModalItems.value = []
  } finally {
    growthModalLoading.value = false
  }
}

function closeGrowthEventsModal() {
  growthModalOpen.value = false
  growthModalItems.value = []
}

watch(() => props.periodKey, (k) => {
  if (k && k !== statsPeriod.value) statsPeriod.value = k
})

const PERIOD_ROWS = computed(() => [
  { key: 'today', label: tt('cabinet_stats.period.today') },
  { key: '7d', label: tt('cabinet_stats.period.d7') },
  { key: '30d', label: tt('cabinet_stats.period.d30') },
  { key: '6m', label: tt('cabinet_stats.period.m6') },
  { key: '1y', label: tt('cabinet_stats.period.y1') },
])
const TYPE_TABS = computed(() => [
  { key: 'all', label: tt('cabinet_stats.type_tabs.all') },
  { key: 'deletions', label: tt('cabinet_stats.type_tabs.deletions') },
  { key: 'connections', label: tt('cabinet_stats.type_tabs.connections') },
])
const SCOPE_TABS = computed(() => [
  { key: 'all', label: tt('cabinet_stats.scope.all') },
  { key: 'own', label: tt('cabinet_stats.scope.own') },
  { key: 'delegated', label: tt('cabinet_stats.scope.delegated') },
])
const SUB_TABS = computed(() => [
  { key: 'timeline', label: tt('cabinet_stats.sub_tabs.timeline') },
  { key: 'types', label: tt('cabinet_stats.sub_tabs.types') },
  { key: 'hours', label: tt('cabinet_stats.sub_tabs.hours') },
  { key: 'weekdays', label: tt('cabinet_stats.sub_tabs.weekdays') },
])
const typeTabs = computed(() =>
  TYPE_TABS.value.map((t) =>
    isGrowthMode.value && t.key === 'deletions' ? { ...t, label: tt('cabinet_stats.type_tabs.growth') } : t,
  ),
)

const COLOR_POOL = ['#ef4444', '#3b82f6', '#f59e0b', '#f97316', '#60a5fa', '#dc2626', '#fb923c']

const totals = computed(() => props.hourlyData?.totals || {})
const chats = computed(() => (Array.isArray(props.hourlyData?.chats) ? props.hourlyData.chats : []))
const chatsCount = computed(() => Math.max(0, Math.round(Number((props.summary?.groups_count ?? props.summary?.chats_count) || 0))))
const joinsTotal = computed(() => Math.max(0, Math.round(Number(totals.value?.joins || 0))))
const isGrowthMode = computed(() => String(props.mode || 'protection') === 'growth')

const breakdownData = ref(null)
function isChannelChat(c) {
  const kind = String(c?.chat_kind || c?.kind || 'group').toLowerCase()
  return kind === 'channel'
}
function isDelegatedChat(c) {
  return !!(c?.is_delegated || c?.is_shared)
}
/** Делегированные — только во вкладке «Делегированные»; в «Все» и «Свои» их нет. */
function chatMatchesStatsScope(c) {
  const scope = String(statsScope.value || 'all')
  const delegated = isDelegatedChat(c)
  if (scope === 'delegated') return delegated
  return !delegated
}
const availableScopeChats = computed(() => {
  const rows = Array.isArray(breakdownData.value?.chats) ? breakdownData.value.chats : []
  return rows.filter((c) => chatMatchesStatsScope(c))
})
const scopeChatGroups = computed(() => availableScopeChats.value.filter((c) => !isChannelChat(c)))
const scopeChatChannels = computed(() => availableScopeChats.value.filter((c) => isChannelChat(c)))
const showChatKindFilter = computed(() => scopeChatGroups.value.length > 0 && scopeChatChannels.value.length > 0)
const filteredScopeChats = computed(() => {
  const rows = availableScopeChats.value
  if (chatKindFilter.value === 'groups') return rows.filter((c) => !isChannelChat(c))
  if (chatKindFilter.value === 'channels') return rows.filter((c) => isChannelChat(c))
  return rows
})
/** Чаты, по которым считаются карточки и модалки (scope + тип + выбранный чат). */
const activeStatsChatRows = computed(() => {
  if (selectedChatId.value !== 'all') {
    const row = selectedScopeChatRow.value
    return row ? [row] : []
  }
  return filteredScopeChats.value
})
function sumActiveChatField(field) {
  return activeStatsChatRows.value.reduce((acc, c) => acc + Math.max(0, toNum(c?.[field] || 0)), 0)
}
const anyStatsModalOpen = computed(() => growthModalOpen.value || reasonHitsModalOpen.value)
useModalScrollLock(anyStatsModalOpen)
const selectedScopeChatRow = computed(() => {
  if (selectedChatId.value === 'all') return null
  const id = String(selectedChatId.value)
  return availableScopeChats.value.find((c) => String(c?.id) === id) || null
})

/** id из ModerationLog (канал + обсуждение и т.д.) для выбранной в пресетах группы. */
function moderationIdsForSelectedChat() {
  if (selectedChatId.value === 'all') return null
  const row = selectedScopeChatRow.value
  const raw = row?.moderation_chat_ids
  if (Array.isArray(raw) && raw.length) {
    return raw.map((x) => sidChat(x)).filter(Boolean)
  }
  const one = sidChat(selectedChatId.value)
  return one ? [one] : null
}

const reportContextPayload = computed(() => ({
  scope: String(statsScope.value || 'all'),
  chatId: selectedChatId.value === 'all' ? null : sidChat(selectedChatId.value) || null,
  chatTitle: String(selectedScopeChatRow.value?.title || ''),
  periodKey: String(statsPeriod.value || 'today'),
  journalChatIds: moderationIdsForSelectedChat(),
  eligibleChatIds:
    selectedChatId.value === 'all'
      ? availableScopeChats.value.map((c) => sidChat(c?.id)).filter(Boolean)
      : [sidChat(selectedChatId.value)].filter(Boolean),
}))

function normalizeReason(reason) {
  const raw = String(reason || '').trim().toLowerCase()
  if (!raw) return ''
  return raw.replace(/_newbie$/i, '')
}
function toNum(v) {
  const n = Number(v || 0)
  return Number.isFinite(n) ? n : 0
}
function hasAnyBreakdownDetails(payload) {
  const byReasonLen = Array.isArray(payload?.by_reason)
    ? payload.by_reason.length
    : (payload?.by_reason && typeof payload.by_reason === 'object')
      ? Object.keys(payload.by_reason || {}).length
      : 0
  const byHourSum = Array.isArray(payload?.by_hour)
    ? payload.by_hour.reduce((a, b) => a + toNum(b), 0)
    : 0
  const byWeekdaySum = Array.isArray(payload?.by_weekday)
    ? payload.by_weekday.reduce((a, b) => a + toNum(b), 0)
    : 0
  const totalDeleted = toNum(payload?.total_deleted || 0)
  const totalJoined = toNum(payload?.total_joined || 0)
  const totalLeft = toNum(payload?.total_left || 0)
  const totalMessages = toNum(payload?.total_messages || 0)
  const byHourJoinsSum = Array.isArray(payload?.by_hour_joins)
    ? payload.by_hour_joins.reduce((a, b) => a + toNum(b), 0)
    : 0
  const byHourLeavesSum = Array.isArray(payload?.by_hour_leaves)
    ? payload.by_hour_leaves.reduce((a, b) => a + toNum(b), 0)
    : 0
  const byHourMessagesSum = Array.isArray(payload?.by_hour_messages)
    ? payload.by_hour_messages.reduce((a, b) => a + toNum(b), 0)
    : 0
  return (
    byReasonLen > 0
    || byHourSum > 0
    || byWeekdaySum > 0
    || totalDeleted > 0
    || totalJoined > 0
    || totalLeft > 0
    || totalMessages > 0
    || byHourJoinsSum > 0
    || byHourLeavesSum > 0
    || byHourMessagesSum > 0
  )
}
function prettifyReason(reason) {
  const k = normalizeReason(reason)
  if (!k) return tt('cabinet_stats.reasons.unknown')
  if (k.startsWith('mention_')) {
    const sub = k.slice('mention_'.length)
    const path = `cabinet_stats.reasons.mention_${sub}`
    if (te(path)) return tt(path)
  }
  if (k.startsWith('media_')) {
    const sub = k.slice('media_'.length)
    const path = `cabinet_stats.reasons.media_${sub}`
    if (te(path)) return tt(path)
  }
  if (k.startsWith('button_')) {
    const sub = k.slice('button_'.length)
    const path = `cabinet_stats.reasons.button_${sub}`
    if (te(path)) return tt(path)
  }
  const path = `cabinet_stats.reasons.${k}`
  if (te(path)) return tt(path)
  return k.replace(/_/g, ' ')
}

const statsPeriodLabel = computed(() => {
  const row = PERIOD_ROWS.value.find((p) => p.key === statsPeriod.value)
  return row?.label || statsPeriod.value
})

function growthEventTime(iso) {
  return formatDateTimeShortRu(iso)
}

const growthModalPeriodLabel = computed(() => {
  const from = growthModalPeriod.value?.from
  const to = growthModalPeriod.value?.to
  if (!from && !to) return ''
  if (from && to) return `${formatDateTimeShortRu(from)} — ${formatDateTimeShortRu(to)}`
  return formatDateTimeShortRu(from || to)
})
function reasonColor(reason) {
  const key = normalizeReason(reason)
  if (key === 'media') return '#ef4444'
  if (key === 'link' || key === 'global_url' || key === 'url') return '#3b82f6'
  if (key === 'profanity' || key === 'vulgar' || key === 'insult') return '#f97316'
  if (key === 'nazi' || key === 'racism' || key === 'nationalism') return '#f59e0b'
  let hash = 0
  for (let i = 0; i < key.length; i += 1) hash = ((hash << 5) - hash + key.charCodeAt(i)) | 0
  return COLOR_POOL[Math.abs(hash) % COLOR_POOL.length]
}

async function loadBreakdown(opts = {}) {
  const silent = Boolean(opts?.silent)
  try {
    const period = statsPeriod.value === '6m' ? '180d' : statsPeriod.value === '1y' ? '365d' : statsPeriod.value
    const chatIdRaw = selectedChatId.value === 'all' ? null : Number(selectedChatId.value || 0)
    const hasChatId = chatIdRaw != null && Number.isFinite(Number(chatIdRaw)) && Number(chatIdRaw) !== 0
    const chatId = hasChatId ? Number(chatIdRaw) : null
    const base = await api.activityBreakdown(period, statsScope.value, null)
    if (chatId != null) {
      // Для выбранного чата используем activityBreakdown с chat_id:
      // этот эндпоинт возвращает полную детализацию (by_reason/by_hour/heatmap),
      // в отличие от group-breakdown (там buckets только для карточек).
      let scoped = await api.activityBreakdown(period, statsScope.value, chatId).catch(() => null)
      const scopedHasDetails = hasAnyBreakdownDetails(scoped)
      // Для некоторых делегированных чатов owner_scope может вернуть totals без деталей.
      // Fallback: запрашиваем тот же chat_id через scope=all.
      if (!scopedHasDetails && statsScope.value !== 'all') {
        const retryAll = await api.activityBreakdown(period, 'all', chatId).catch(() => null)
        if (retryAll) scoped = retryAll
      }
      breakdownData.value = rebuildByHourIfSparse(
        scoped
          ? {
              ...base,
              ...scoped,
              chats: Array.isArray(base?.chats) ? base.chats : [],
            }
          : base,
      )
    } else {
      breakdownData.value = rebuildByHourIfSparse(base)
    }
  } catch {
    breakdownData.value = null
  } finally {
    if (!silent) filterBusyKey.value = ''
  }
}
watch(statsScope, () => {
  selectedChatId.value = 'all'
  chatKindFilter.value = 'all'
  // Не показываем список из прошлого scope до загрузки нового.
  breakdownData.value = null
})
watch(availableScopeChats, (rows) => {
  if (!Array.isArray(rows) || rows.length === 0) return
  if (selectedChatId.value === 'all') return
  const ok = rows.some((c) => String(c?.id) === String(selectedChatId.value))
  if (!ok) selectedChatId.value = 'all'
})
watch(showChatKindFilter, (on) => {
  if (!on && chatKindFilter.value !== 'all') chatKindFilter.value = 'all'
})
watch(chatKindFilter, () => {
  if (selectedChatId.value === 'all') return
  const ok = filteredScopeChats.value.some((c) => String(c?.id) === String(selectedChatId.value))
  if (!ok) selectedChatId.value = 'all'
})
watch(
  [statsPeriod, statsScope, selectedChatId],
  () => void loadBreakdown({ silent: filterBusyKey.value === '' }),
  { immediate: true },
)
watch([statsPeriod, statsScope, selectedChatId], () => {
  threatOpen.value = false
  threatDetails.value = {}
  threatLoadingId.value = ''
})
watch(
  reportContextPayload,
  (ctx) => {
    emit('report-context-change', ctx)
  },
  { immediate: true, deep: true },
)

const reasonRows = computed(() => {
  const arrRows = Array.isArray(breakdownData.value?.by_reason)
    ? breakdownData.value.by_reason
    : (breakdownData.value?.by_reason && typeof breakdownData.value.by_reason === 'object')
      ? Object.entries(breakdownData.value.by_reason).map(([reason, count]) => ({ reason, count }))
      : []
  let rows = arrRows
    .map((r) => ({
      reason: normalizeReason(r?.reason || ''),
      label: prettifyReason(r?.reason || ''),
      n: Math.max(0, toNum(r?.count)),
      color: reasonColor(r?.reason || ''),
      examples: Array.isArray(breakdownData.value?.examples_by_reason?.[normalizeReason(r?.reason || '')])
        ? breakdownData.value.examples_by_reason[normalizeReason(r?.reason || '')]
        : [],
    }))
    .filter((x) => x.reason && x.n > 0)
  if (!rows.length) {
    const byHr = breakdownData.value?.by_hour_by_reason || {}
    rows = Object.entries(byHr)
      .map(([reason, bucket]) => ({
        reason: normalizeReason(reason),
        label: prettifyReason(reason),
        n: Array.isArray(bucket) ? bucket.reduce((a, b) => a + Math.max(0, toNum(b)), 0) : 0,
        color: reasonColor(reason),
        examples: [],
      }))
      .filter((x) => x.reason && x.n > 0)
  }
  return rows.sort((a, b) => b.n - a.n)
})
const deletedTotal = computed(() => {
  const apiTotal = Math.max(0, Number(breakdownData.value?.total_deleted || 0))
  if (apiTotal > 0) return apiTotal
  const byReasonSum = reasonRows.value.reduce((a, b) => a + b.n, 0)
  if (byReasonSum > 0) return byReasonSum
  const t = Number(totals.value?.moderation || 0)
  if (t > 0) return Math.round(t)
  return Math.max(0, Math.round(Number(props.summary?.today?.deleted || 0)))
})
const filtersTriggered = computed(() => reasonRows.value.length)
const donutSlices = computed(() => {
  if (!reasonRows.value.length && deletedTotal.value > 0) {
    return [{ reason: 'fallback', label: tt('cabinet_stats.reasons.fallback'), n: deletedTotal.value, color: '#334155', pct: 100, start: 0, end: 100 }]
  }
  const total = Math.max(1, deletedTotal.value)
  let acc = 0
  return reasonRows.value.map((r) => {
    const pct = (r.n / total) * 100
    const out = { ...r, pct, start: acc, end: acc + pct }
    acc += pct
    return out
  })
})
const donutGradient = computed(() => {
  if (!donutSlices.value.length) return 'conic-gradient(#334155 0 100%)'
  return `conic-gradient(${donutSlices.value.map((p) => `${p.color} ${p.start}% ${p.end}%`).join(', ')})`
})

const growthJoined = computed(() => {
  if (isGrowthMode.value && activeStatsChatRows.value.length) return sumActiveChatField('joined')
  return Math.max(0, toNum(breakdownData.value?.total_joined || 0))
})
const growthLeft = computed(() => {
  if (isGrowthMode.value && activeStatsChatRows.value.length) return sumActiveChatField('left')
  return Math.max(0, toNum(breakdownData.value?.total_left || 0))
})
const growthNet = computed(() => growthJoined.value - growthLeft.value)
const growthMessages = computed(() => {
  if (isGrowthMode.value && activeStatsChatRows.value.length) return sumActiveChatField('messages')
  return Math.max(0, toNum(breakdownData.value?.total_messages || 0))
})
const growthTopChat = computed(() => {
  if (selectedScopeChatRow.value) {
    return {
      title: String(selectedScopeChatRow.value?.title || selectedScopeChatRow.value?.id || tt('cabinet_stats.reasons.chat_fallback')),
      messages: Math.max(0, toNum(selectedScopeChatRow.value?.messages || 0)),
      joins: Math.max(0, toNum(selectedScopeChatRow.value?.joined || 0)),
      left: Math.max(0, toNum(selectedScopeChatRow.value?.left || 0)),
    }
  }
  const rows = Array.isArray(activeStatsChatRows.value) ? activeStatsChatRows.value : []
  if (!rows.length) return { title: tt('cabinet_stats.reasons.no_data'), messages: 0, joins: 0, left: 0 }
  const best = [...rows].sort((a, b) => Number(b?.messages || 0) - Number(a?.messages || 0))[0]
  return {
    title: String(best?.title || best?.id || tt('cabinet_stats.reasons.chat_fallback')),
    messages: Math.max(0, toNum(best?.messages || 0)),
    joins: Math.max(0, toNum(best?.joined || 0)),
    left: Math.max(0, toNum(best?.left || 0)),
  }
})

const audienceGenderCard = computed(() => {
  const g = props.audienceGender || {}
  const maleCount = Math.max(0, Number(g?.maleCount || 0))
  const femaleCount = Math.max(0, Number(g?.femaleCount || 0))
  const sumNamed = maleCount + femaleCount
  const knownTotal = Math.max(0, Number(g?.knownTotal || sumNamed))
  let malePct = Math.max(0, Math.min(100, Number(g?.malePct ?? 0)))
  let femalePct =
    g?.femalePct != null && g?.femalePct !== ''
      ? Math.max(0, Math.min(100, Number(g.femalePct)))
      : sumNamed > 0
        ? Math.max(0, Math.min(100, 100 - malePct))
        : 0
  if (props.loading || (sumNamed <= 0 && knownTotal <= 0)) {
    malePct = 0
    femalePct = 0
  }
  return {
    audience: Math.max(0, Number(g?.audience || 0)),
    malePct: Number.isFinite(malePct) ? Math.round(malePct * 10) / 10 : 0,
    femalePct: Number.isFinite(femalePct) ? Math.round(femalePct * 10) / 10 : 0,
    maleCount,
    femaleCount,
    knownTotal,
    unknownCount: Math.max(0, Number(g?.unknownCount || 0)),
    hasAny: knownTotal > 0,
  }
})

const byHour = computed(() => {
  const arr = isGrowthMode.value
    ? (Array.isArray(breakdownData.value?.by_hour_messages) ? breakdownData.value.by_hour_messages : [])
    : (Array.isArray(breakdownData.value?.by_hour) ? breakdownData.value.by_hour : [])
  if (arr.length === 24) {
    const out = arr.map((x) => Math.max(0, Number(x || 0)))
    const sum = out.reduce((a, b) => a + b, 0)
    const td = Math.max(0, Number(breakdownData.value?.total_deleted || 0))
    if (!isGrowthMode.value && sum === 0 && td > 0) {
      const fixed = rebuildByHourIfSparse(breakdownData.value)?.by_hour
      if (Array.isArray(fixed) && fixed.length === 24) return fixed.map((x) => Math.max(0, Number(x || 0)))
    }
    return out
  }
  return Array.from({ length: 24 }, () => 0)
})
const xTickLabels = ['00:00', '06:00', '12:00', '18:00', '24:00']
const CHART = { w: 360, h: 188, pad: { l: 34, r: 4, t: 6, b: 20 } }

function niceChartMax(raw) {
  const v = Math.max(0, Number(raw || 0))
  if (v <= 4) return 4
  const exp = 10 ** Math.floor(Math.log10(v))
  const f = v / exp
  let niceF = 10
  if (f <= 1) niceF = 1
  else if (f <= 2) niceF = 2
  else if (f <= 5) niceF = 5
  return niceF * exp
}

function linePathFromCoords(coords) {
  if (!coords.length) return ''
  return coords.map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
}

function smoothLinePathFromCoords(coords) {
  if (coords.length < 2) return linePathFromCoords(coords)
  let d = `M${coords[0].x.toFixed(1)},${coords[0].y.toFixed(1)}`
  for (let i = 0; i < coords.length - 1; i += 1) {
    const p0 = coords[i - 1] || coords[i]
    const p1 = coords[i]
    const p2 = coords[i + 1]
    const p3 = coords[i + 2] || p2
    const cp1x = p1.x + (p2.x - p0.x) / 6
    const cp1y = p1.y + (p2.y - p0.y) / 6
    const cp2x = p2.x - (p3.x - p1.x) / 6
    const cp2y = p2.y - (p3.y - p1.y) / 6
    d += ` C${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`
  }
  return d
}

function areaPathFromCoords(coords, smooth = true) {
  if (!coords.length) return ''
  const baseY = CHART.h - CHART.pad.b
  const first = coords[0]
  const last = coords[coords.length - 1]
  const top = smooth ? smoothLinePathFromCoords(coords) : linePathFromCoords(coords)
  return `${top} L${last.x.toFixed(1)},${baseY} L${first.x.toFixed(1)},${baseY} Z`
}

function chartCoords(vals, maxY) {
  const { w, h, pad } = CHART
  const plotW = w - pad.l - pad.r
  const plotH = h - pad.t - pad.b
  const denom = Math.max(1, maxY)
  const n = Math.max(1, vals.length - 1)
  return vals.map((v, i) => ({
    x: pad.l + (i / n) * plotW,
    y: pad.t + plotH - (Math.max(0, v) / denom) * plotH,
  }))
}
const yMax = computed(() => niceChartMax(Math.max(...byHour.value, 0)))
const yTicks = computed(() => {
  const m = yMax.value
  return [m, Math.round(m * 0.75), Math.round(m * 0.5), Math.round(m * 0.25), 0]
})

const singleSeriesCoords = computed(() => chartCoords(byHour.value, yMax.value))
const linePath = computed(() => smoothLinePathFromCoords(singleSeriesCoords.value))
const singleAreaPath = computed(() => areaPathFromCoords(singleSeriesCoords.value, true))

const singleGridLines = computed(() => {
  const { h, pad } = CHART
  const plotH = h - pad.t - pad.b
  return yTicks.value.map((tick) => ({
    y: pad.t + plotH - (tick / Math.max(1, yMax.value)) * plotH,
    label: tick,
  }))
})

const chartHoverLineX = computed(() => {
  if (hoverIndex.value < 0) return null
  const { w, pad } = CHART
  const plotW = w - pad.l - pad.r
  return pad.l + (hoverIndex.value / 23) * plotW
})

const timelineXAxisTicks = computed(() => {
  const { w, pad } = CHART
  const plotW = w - pad.l - pad.r
  const n = xTickLabels.length - 1
  return xTickLabels.map((label, i) => ({
    label,
    x: pad.l + (i / n) * plotW,
  }))
})

const top3Reasons = computed(() => reasonRows.value.slice(0, 6))
const growthTypeRows = computed(() => {
  const rows = [
    { reason: 'joined', label: tt('cabinet_stats.growth.row_joined'), n: growthJoined.value, color: '#10b981' },
    { reason: 'left', label: tt('cabinet_stats.growth.row_left'), n: growthLeft.value, color: '#f97316' },
    { reason: 'net', label: tt('cabinet_stats.growth.row_net'), n: Math.abs(growthNet.value), color: growthNet.value >= 0 ? '#34d399' : '#fb7185' },
    { reason: 'messages', label: tt('cabinet_stats.growth.row_messages'), n: growthMessages.value, color: '#8b5cf6' },
  ]
  return rows.filter((r) => r.n > 0 || r.reason === 'net')
})
const byHourByReason = computed(() => {
  const src = breakdownData.value?.by_hour_by_reason || {}
  const out = {}
  for (const k of Object.keys(src || {})) {
    out[normalizeReason(k)] = Array.isArray(src[k]) ? src[k].map((x) => Math.max(0, Number(x || 0))) : Array.from({ length: 24 }, () => 0)
  }
  return out
})
const timelineMultiSeriesBase = computed(() =>
  isGrowthMode.value
    ? [
      { reason: 'joined', label: tt('cabinet_stats.reasons.subscriptions'), color: '#10b981', vals: Array.isArray(breakdownData.value?.by_hour_joins) ? breakdownData.value.by_hour_joins.map((x) => Math.max(0, toNum(x))) : Array.from({ length: 24 }, () => 0) },
      { reason: 'left', label: tt('cabinet_stats.reasons.unsubscriptions'), color: '#f97316', vals: Array.isArray(breakdownData.value?.by_hour_leaves) ? breakdownData.value.by_hour_leaves.map((x) => Math.max(0, toNum(x))) : Array.from({ length: 24 }, () => 0) },
      { reason: 'messages', label: tt('cabinet_stats.growth.row_messages'), color: '#8b5cf6', vals: Array.isArray(breakdownData.value?.by_hour_messages) ? breakdownData.value.by_hour_messages.map((x) => Math.max(0, toNum(x))) : Array.from({ length: 24 }, () => 0) },
    ]
    : top3Reasons.value.map((r) => ({
      ...r,
      vals: byHourByReason.value[r.reason] || Array.from({ length: 24 }, () => 0),
    })),
)

const timelineYMax = computed(() => {
  let max = 0
  for (const r of timelineMultiSeriesBase.value) {
    for (const v of r.vals || []) max = Math.max(max, Number(v || 0))
  }
  return niceChartMax(max)
})

const timelineYTicks = computed(() => {
  const m = timelineYMax.value
  return [m, Math.round(m * 0.75), Math.round(m * 0.5), Math.round(m * 0.25), 0]
})

const timelineGridLines = computed(() => {
  const { h, pad } = CHART
  const plotH = h - pad.t - pad.b
  return timelineYTicks.value.map((tick) => ({
    y: pad.t + plotH - (tick / Math.max(1, timelineYMax.value)) * plotH,
    label: tick,
  }))
})

const timelineMultiSeries = computed(() =>
  timelineMultiSeriesBase.value.map((r) => {
    const coords = chartCoords(r.vals, timelineYMax.value)
    return {
      ...r,
      coords,
      path: smoothLinePathFromCoords(coords),
      areaPath: areaPathFromCoords(coords, true),
    }
  }),
)

const timelineBottomRows = computed(() => {
  if (hoverIndex.value >= 0 && hoverData.value?.rows?.length) {
    return hoverData.value.rows
  }
  return timelineMultiSeries.value.map((r) => ({
    label: r.label,
    color: r.color,
    n: (r.vals || []).reduce((a, b) => a + Number(b || 0), 0),
  }))
})

const timelineBottomCaption = computed(() => {
  if (hoverIndex.value >= 0 && hoverData.value?.hour) return hoverData.value.hour
  return tt('cabinet_stats.protection.legend_period_total')
})

const weekdayRows = computed(() => {
  const src = Array.from({ length: 7 }, () => 0)
  const raw = isGrowthMode.value ? null : breakdownData.value?.by_weekday
  if (Array.isArray(raw)) {
    for (let i = 0; i < 7; i += 1) src[i] = Math.max(0, toNum(raw[i]))
  } else if (raw && typeof raw === 'object') {
    const map = { mon: 0, tue: 1, wed: 2, thu: 3, fri: 4, sat: 5, sun: 6, monday: 0, tuesday: 1, wednesday: 2, thursday: 3, friday: 4, saturday: 5, sunday: 6 }
    for (const [k, v] of Object.entries(raw)) {
      const idx = map[String(k).toLowerCase()]
      if (idx != null) src[idx] = Math.max(0, toNum(v))
    }
  }
  const growthHeat = Array.isArray(breakdownData.value?.activity_heatmap_24x7) ? breakdownData.value.activity_heatmap_24x7 : []
  if (isGrowthMode.value && growthHeat.length === 7) {
    for (let d = 0; d < 7; d += 1) src[d] = (growthHeat[d] || []).reduce((a, b) => a + Math.max(0, toNum(b)), 0)
  } else if (isGrowthMode.value && growthHeat.length >= 24 && Array.isArray(growthHeat[0]) && growthHeat[0].length === 7) {
    for (let h = 0; h < 24; h += 1) {
      for (let d = 0; d < 7; d += 1) src[d] += Math.max(0, toNum(growthHeat[h]?.[d]))
    }
  }
  if (!src.some((x) => x > 0) && Array.isArray(breakdownData.value?.heatmap_24x7) && breakdownData.value.heatmap_24x7.length === 7) {
    for (let d = 0; d < 7; d += 1) {
      src[d] = (breakdownData.value.heatmap_24x7[d] || []).reduce((a, b) => a + Math.max(0, toNum(b)), 0)
    }
  }
  const labels = [
    { full: tt('cabinet_stats.weekdays.mon_full'), short: tt('cabinet_stats.weekdays.mon_short') },
    { full: tt('cabinet_stats.weekdays.tue_full'), short: tt('cabinet_stats.weekdays.tue_short') },
    { full: tt('cabinet_stats.weekdays.wed_full'), short: tt('cabinet_stats.weekdays.wed_short') },
    { full: tt('cabinet_stats.weekdays.thu_full'), short: tt('cabinet_stats.weekdays.thu_short') },
    { full: tt('cabinet_stats.weekdays.fri_full'), short: tt('cabinet_stats.weekdays.fri_short') },
    { full: tt('cabinet_stats.weekdays.sat_full'), short: tt('cabinet_stats.weekdays.sat_short') },
    { full: tt('cabinet_stats.weekdays.sun_full'), short: tt('cabinet_stats.weekdays.sun_short') },
  ]
  const max = Math.max(1, ...src.map((x) => Number(x || 0)))
  return labels.map((label, i) => ({
    label: label.full,
    short: label.short,
    n: Math.max(0, Number(src[i] || 0)),
    pct: (Math.max(0, Number(src[i] || 0)) / max) * 100,
  }))
})

const heatGrid = computed(() => {
  const src = isGrowthMode.value
    ? (Array.isArray(breakdownData.value?.activity_heatmap_24x7) ? breakdownData.value.activity_heatmap_24x7 : [])
    : (Array.isArray(breakdownData.value?.heatmap_24x7) ? breakdownData.value.heatmap_24x7 : [])
  if (src.length === 7 && Array.isArray(src[0]) && src[0].length >= 24) {
    const rows = Array.from({ length: 8 }, () => Array.from({ length: 7 }, () => 0))
    for (let d = 0; d < 7; d += 1) {
      for (let h = 0; h < 24; h += 1) {
        const row = Math.floor(h / 3)
        rows[row][d] += toNum(src[d]?.[h])
      }
    }
    return rows
  }
  if (src.length >= 24 && Array.isArray(src[0]) && src[0].length === 7) {
    const rows = Array.from({ length: 8 }, () => Array.from({ length: 7 }, () => 0))
    for (let h = 0; h < 24; h += 1) {
      const row = Math.floor(h / 3)
      for (let d = 0; d < 7; d += 1) rows[row][d] += toNum(src[h]?.[d])
    }
    return rows
  }
  return Array.from({ length: 8 }, () => Array.from({ length: 7 }, () => 0))
})
const heatMax = computed(() => Math.max(1, ...heatGrid.value.flat()))
const heatDayLabels = computed(() => [
  tt('cabinet_stats.weekdays.mon_short'),
  tt('cabinet_stats.weekdays.tue_short'),
  tt('cabinet_stats.weekdays.wed_short'),
  tt('cabinet_stats.weekdays.thu_short'),
  tt('cabinet_stats.weekdays.fri_short'),
  tt('cabinet_stats.weekdays.sat_short'),
  tt('cabinet_stats.weekdays.sun_short'),
])
const heatRowLabels = ['0', '3', '6', '9', '12', '15', '18', '21']
function heatCellStyle(v) {
  const a = 0.1 + (Math.max(0, Number(v || 0)) / heatMax.value) * 0.85
  return { background: `rgba(124,58,237,${a.toFixed(3)})` }
}

const hoverData = computed(() => {
  const i = Math.max(0, Math.min(23, Number(hoverIndex.value >= 0 ? hoverIndex.value : 23)))
  const hour = `${String(i).padStart(2, '0')}:00`
  const total = byHour.value[i] || 0
  return {
    hour,
    total,
    rows: timelineMultiSeries.value.map((r) => ({ label: r.label, color: r.color, n: Number(r.vals[i] || 0) })),
  }
})

const connectionsRows = computed(() => {
  const scoped = availableScopeChats.value
  if (scoped.length) return scoped
  const fallback = chats.value.filter((c) => chatMatchesStatsScope(c))
  return fallback
})

const threatTopChats = computed(() =>
  [...connectionsRows.value]
    .map((c) => ({ ...c, _risk: Math.max(0, Number(c?.deleted ?? c?.moderation ?? 0)) }))
    .filter((c) => c._risk > 0)
    .sort((a, b) => b._risk - a._risk)
    .slice(0, 3),
)

async function loadThreatChatDetails(chatId) {
  const cid = Number(chatId || 0)
  if (!cid) return
  threatLoadingId.value = String(cid)
  try {
    const period = statsPeriod.value === '6m' ? '180d' : statsPeriod.value === '1y' ? '365d' : statsPeriod.value
    let res = await api.activityBreakdown(period, statsScope.value, cid).catch(() => null)
    const hasByReason = Array.isArray(res?.by_reason)
      ? res.by_reason.length > 0
      : !!(res?.by_reason && Object.keys(res.by_reason || {}).length > 0)
    if (!hasByReason && statsScope.value !== 'all') {
      const retryAll = await api.activityBreakdown(period, 'all', cid).catch(() => null)
      if (retryAll) res = retryAll
    }
    const byReason = Array.isArray(res?.by_reason)
      ? res.by_reason
      : (res?.by_reason && typeof res.by_reason === 'object')
        ? Object.entries(res.by_reason).map(([reason, count]) => ({ reason, count }))
        : []
    threatDetails.value = {
      ...threatDetails.value,
      [cid]: byReason
        .map((r) => ({
          reason: normalizeReason(r?.reason || ''),
          label: prettifyReason(r?.reason || ''),
          n: Math.max(0, Number(r?.count || 0)),
          color: reasonColor(r?.reason || ''),
        }))
        .filter((x) => x.n > 0)
        .sort((a, b) => b.n - a.n),
    }
  } catch {
    threatDetails.value = { ...threatDetails.value, [cid]: [] }
  } finally {
    threatLoadingId.value = ''
  }
}

async function toggleThreatSection() {
  threatOpen.value = !threatOpen.value
  if (!threatOpen.value) return
  const jobs = threatTopChats.value.map((c) => loadThreatChatDetails(c.id))
  await Promise.all(jobs)
}

function threatTopThree(chatId) {
  const rows = threatDetails.value?.[Number(chatId || 0)] || []
  return rows.slice(0, 3)
}

function onChartMove(ev) {
  const el = ev.currentTarget
  if (!el || typeof el.getBoundingClientRect !== 'function') return
  const r = el.getBoundingClientRect()
  const x = (ev.touches?.[0]?.clientX ?? ev.clientX) - r.left
  const rel = Math.max(0, Math.min(1, x / Math.max(1, r.width)))
  hoverIndex.value = Math.round(rel * 23)
}
function onChartLeave() {
  hoverIndex.value = -1
}

function pillActiveClass(on) {
  return on
    ? 'border border-[#7dff3a]/80 bg-[rgba(125,255,58,0.14)] text-[#deffbf] shadow-[0_0_18px_-6px_rgba(125,255,58,0.5)]'
    : 'border border-white/10 bg-white/[0.06] text-slate-300'
}
function onPeriodPick(key) {
  filterBusyKey.value = 'period'
  statsPeriod.value = key
  emit('period-change', { key })
}
function onTypePick(key) {
  filterBusyKey.value = 'type'
  statsType.value = key
  void nextTick(() => {
    if (filterBusyKey.value === 'type') filterBusyKey.value = ''
  })
}
function onSubViewPick(key) {
  filterBusyKey.value = 'subview'
  statsSubView.value = key
  void nextTick(() => {
    if (filterBusyKey.value === 'subview') filterBusyKey.value = ''
  })
}
function emitReportContextNow() {
  emit('report-context-change', {
    scope: String(statsScope.value || 'all'),
    chatId: selectedChatId.value === 'all' ? null : sidChat(selectedChatId.value) || null,
    chatTitle: String(selectedScopeChatRow.value?.title || ''),
    periodKey: String(statsPeriod.value || 'today'),
    journalChatIds: moderationIdsForSelectedChat(),
    eligibleChatIds:
      selectedChatId.value === 'all'
        ? availableScopeChats.value.map((c) => sidChat(c?.id)).filter(Boolean)
        : [sidChat(selectedChatId.value)].filter(Boolean),
  })
}
function pickStatsScope(scopeKey) {
  filterBusyKey.value = 'scope'
  statsScope.value = String(scopeKey || 'all')
  emitReportContextNow()
}
function pickScopeAllChats() {
  filterBusyKey.value = 'chat'
  selectedChatId.value = 'all'
  emitReportContextNow()
}
function pickScopeChat(chatId) {
  filterBusyKey.value = 'chat'
  selectedChatId.value = String(chatId || 'all')
  emitReportContextNow()
}

const touchStartX = ref(null)
function onTouchStart(e) { touchStartX.value = e.changedTouches?.[0]?.clientX ?? null }
function onTouchEnd(e) {
  if (touchStartX.value == null) return
  const x = e.changedTouches?.[0]?.clientX
  if (x == null) return
  const dx = x - touchStartX.value
  touchStartX.value = null
  if (Math.abs(dx) < 48) return
  const order = TYPE_TABS.value.map((t) => t.key)
  const i = order.indexOf(statsType.value)
  if (dx < 0 && i < order.length - 1) onTypePick(order[i + 1])
  else if (dx > 0 && i > 0) onTypePick(order[i - 1])
}

onMounted(() => {
  silentRefreshTimer = setInterval(() => {
    void loadBreakdown({ silent: true })
  }, 3000)
})

onUnmounted(() => {
  if (silentRefreshTimer) {
    clearInterval(silentRefreshTimer)
    silentRefreshTimer = null
  }
})
</script>

<template>
  <div class="owner-protection-stats -mx-1 flex min-h-0 flex-col font-display sm:-mx-0">
    <div class="sticky top-0 z-10 space-y-2 border-b border-white/10 bg-zinc-950/80 px-1 py-2.5 backdrop-blur-xl supports-[backdrop-filter]:bg-zinc-950/65">
      <div class="flex gap-2 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <button v-for="p in PERIOD_ROWS" :key="p.key" type="button" class="shrink-0 rounded-full px-3.5 py-2 text-[12px] font-semibold transition active:scale-[0.98]" :class="pillActiveClass(statsPeriod === p.key)" :disabled="isPillBusy('period', statsPeriod === p.key)" @click="onPeriodPick(p.key)">
          <span v-if="isPillBusy('period', statsPeriod === p.key)" class="hourglass-flip inline-block" aria-hidden="true">⏳</span>
          <span v-else>{{ p.label }}</span>
        </button>
      </div>
      <div class="flex gap-2 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <button v-for="t in typeTabs" :key="t.key" type="button" class="shrink-0 rounded-full px-3.5 py-2 text-[12px] font-semibold transition active:scale-[0.98]" :class="pillActiveClass(statsType === t.key)" :disabled="isPillBusy('type', statsType === t.key)" @click="onTypePick(t.key)">
          <span v-if="isPillBusy('type', statsType === t.key)" class="hourglass-flip inline-block" aria-hidden="true">⏳</span>
          <span v-else>{{ t.label }}</span>
        </button>
      </div>
      <div v-if="statsType === 'deletions'" class="flex gap-2 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <button v-for="s in SUB_TABS" :key="s.key" type="button" class="shrink-0 rounded-full px-3.5 py-1.5 text-[11px] font-semibold transition active:scale-[0.98]" :class="pillActiveClass(statsSubView === s.key)" :disabled="isPillBusy('subview', statsSubView === s.key)" @click="onSubViewPick(s.key)">
          <span v-if="isPillBusy('subview', statsSubView === s.key)" class="hourglass-flip inline-block" aria-hidden="true">⏳</span>
          <span v-else>{{ s.label }}</span>
        </button>
      </div>
      <div class="grid grid-cols-3 gap-2">
        <button v-for="s in SCOPE_TABS" :key="s.key" type="button" class="rounded-xl border px-2.5 py-2 text-[11px] font-semibold transition" :class="statsScope === s.key ? 'border-[#7dff3a]/80 bg-[rgba(125,255,58,0.14)] text-[#deffbf]' : 'border-white/10 bg-white/[0.04] text-slate-300'" :disabled="isPillBusy('scope', statsScope === s.key)" @click="pickStatsScope(s.key)">
          <span v-if="isPillBusy('scope', statsScope === s.key)" class="hourglass-flip inline-block" aria-hidden="true">⏳</span>
          <span v-else>{{ s.label }}</span>
        </button>
      </div>
      <div v-if="showChatKindFilter" class="grid grid-cols-3 gap-2">
        <button type="button" class="rounded-xl border px-2.5 py-2 text-[11px] font-semibold transition" :class="chatKindFilter === 'all' ? 'border-cyan-400/50 bg-cyan-500/10 text-cyan-100' : 'border-white/10 bg-white/[0.04] text-slate-300'" @click="chatKindFilter = 'all'">
          {{ tt('cabinet_stats.all_chats') }}
        </button>
        <button type="button" class="rounded-xl border px-2.5 py-2 text-[11px] font-semibold transition" :class="chatKindFilter === 'groups' ? 'border-emerald-400/50 bg-emerald-500/10 text-emerald-100' : 'border-white/10 bg-white/[0.04] text-slate-300'" @click="chatKindFilter = 'groups'">
          {{ tt('cabinet_stats.growth.groups') }}
        </button>
        <button type="button" class="rounded-xl border px-2.5 py-2 text-[11px] font-semibold transition" :class="chatKindFilter === 'channels' ? 'border-violet-400/50 bg-violet-500/10 text-violet-100' : 'border-white/10 bg-white/[0.04] text-slate-300'" @click="chatKindFilter = 'channels'">
          {{ tt('cabinet_stats.growth.channels') }}
        </button>
      </div>
      <div v-if="availableScopeChats.length" class="flex gap-2 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <button type="button" class="shrink-0 rounded-full px-3 py-1.5 text-[11px] font-semibold transition" :class="pillActiveClass(selectedChatId === 'all')" :disabled="isPillBusy('chat', selectedChatId === 'all')" @click="pickScopeAllChats()">
          <span v-if="isPillBusy('chat', selectedChatId === 'all')" class="hourglass-flip inline-block" aria-hidden="true">⏳</span>
          <span v-else>{{ tt('cabinet_stats.all_chats') }}</span>
        </button>
        <button
          v-for="c in filteredScopeChats"
          :key="`sc-${c.id}`"
          type="button"
          class="shrink-0 rounded-full px-3 py-1.5 text-[11px] font-semibold transition"
          :class="pillActiveClass(String(selectedChatId) === String(c.id))"
          :disabled="isPillBusy('chat', String(selectedChatId) === String(c.id))"
          @click="pickScopeChat(c.id)"
        >
          <span v-if="isPillBusy('chat', String(selectedChatId) === String(c.id))" class="hourglass-flip inline-block" aria-hidden="true">⏳</span>
          <span v-else class="inline-flex max-w-[11rem] items-center gap-1 truncate">
            <span v-if="isChannelChat(c)" class="shrink-0 text-[10px]" aria-hidden="true">📢</span>
            <span class="truncate">{{ c.title || c.id }}</span>
          </span>
        </button>
      </div>
      <p v-if="false && loading" class="px-0.5 text-[11px] text-emerald-300/80">{{ tt('cabinet_stats.updating') }}</p>
    </div>

    <div
      class="min-h-0 flex-1 overscroll-contain px-1 pb-4 pt-3"
      :class="anyStatsModalOpen ? 'overflow-hidden touch-none' : 'touch-pan-y overflow-y-auto'"
      @touchstart.passive="onTouchStart"
      @touchend="onTouchEnd"
    >
      <div v-if="statsType === 'all'" class="space-y-3">
        <template v-if="isGrowthMode">
          <div class="overflow-hidden rounded-2xl border border-emerald-400/20 bg-gradient-to-br from-[#0c1410] via-[#10141a] to-[#0a1018] p-4 shadow-[0_16px_48px_-28px_rgba(16,185,129,0.55)] backdrop-blur-md">
            <div>
              <p class="text-[13px] font-semibold text-white">{{ tt('cabinet_stats.growth.audience_title') }}</p>
              <p class="mt-0.5 text-[10px] text-slate-400">{{ tt('cabinet_stats.growth.period_label', { label: statsPeriodLabel }) }}</p>
            </div>
            <div class="mt-3 grid grid-cols-2 gap-2">
              <button
                type="button"
                class="group rounded-xl border border-emerald-400/25 bg-gradient-to-br from-emerald-950/40 to-black/30 p-3 text-left transition hover:border-emerald-300/45 hover:from-emerald-900/35 active:scale-[0.99]"
                @click="openGrowthEventsModal('joined')"
              >
                <p class="text-[10px] font-semibold uppercase tracking-wide text-emerald-200/85">{{ tt('cabinet_stats.growth.joined') }}</p>
                <p class="mt-1 text-xl font-black tabular-nums text-white">{{ growthJoined }}</p>
                <p class="mt-1 text-[9px] text-emerald-200/60 group-hover:text-emerald-100/80">{{ tt('cabinet_stats.growth.open_list') }}</p>
              </button>
              <button
                type="button"
                class="group rounded-xl border border-orange-400/25 bg-gradient-to-br from-orange-950/35 to-black/30 p-3 text-left transition hover:border-orange-300/45 hover:from-orange-900/30 active:scale-[0.99]"
                @click="openGrowthEventsModal('left')"
              >
                <p class="text-[10px] font-semibold uppercase tracking-wide text-orange-200/85">{{ tt('cabinet_stats.growth.left') }}</p>
                <p class="mt-1 text-xl font-black tabular-nums text-white">{{ growthLeft }}</p>
                <p class="mt-1 text-[9px] text-orange-200/60 group-hover:text-orange-100/80">{{ tt('cabinet_stats.growth.open_list') }}</p>
              </button>
            </div>
            <button
              type="button"
              class="group mt-2 w-full rounded-xl border border-violet-400/30 bg-gradient-to-r from-violet-950/35 via-indigo-950/25 to-black/20 p-3 text-left transition hover:border-violet-300/45 active:scale-[0.99]"
              @click="openGrowthEventsModal('net')"
            >
              <p class="text-[10px] font-semibold uppercase tracking-wide text-violet-200/85">{{ tt('cabinet_stats.growth.net') }}</p>
              <p class="mt-1 text-xl font-black tabular-nums" :class="growthNet >= 0 ? 'text-emerald-200' : 'text-rose-200'">
                {{ growthNet >= 0 ? '+' : '' }}{{ growthNet }}
              </p>
              <p class="mt-1 text-[10px] text-violet-100/75">{{ tt('cabinet_stats.growth.messages_n', { n: growthMessages }) }}</p>
              <p class="mt-0.5 text-[9px] text-violet-200/55 group-hover:text-violet-100/75">{{ tt('cabinet_stats.growth.open_list') }}</p>
            </button>
          </div>
          <div class="rounded-2xl border border-white/10 bg-[#10141a]/95 p-4 backdrop-blur-md">
            <p class="text-[12px] font-semibold text-white">{{ tt('cabinet_stats.growth.top_chat_title') }}</p>
            <p class="mt-2 truncate text-[14px] font-bold text-white">{{ growthTopChat.title }}</p>
            <p class="mt-1 text-[11px] text-slate-300">
              {{ tt('cabinet_stats.growth.top_chat_line', { messages: growthTopChat.messages, joins: growthTopChat.joins, left: growthTopChat.left }) }}
            </p>
          </div>
          <div class="rounded-2xl border border-white/10 bg-[#10141a]/95 p-4 backdrop-blur-md">
            <div class="mb-2 flex items-center justify-between gap-2">
              <p class="text-[12px] font-semibold text-white">{{ tt('cabinet_stats.growth.gender_title') }}</p>
              <p class="text-[11px] text-slate-400">{{ tt('cabinet_stats.growth.audience_n', { n: Math.round(audienceGenderCard.audience) }) }}</p>
            </div>
            <div class="flex items-end justify-between gap-3">
              <div>
                <p class="text-3xl font-extrabold leading-none text-emerald-300">{{ audienceGenderCard.malePct }}%</p>
                <p class="text-[12px] text-slate-300">{{ tt('cabinet_stats.growth.men') }}</p>
              </div>
              <div class="text-right">
                <p class="text-3xl font-extrabold leading-none text-sky-300">{{ audienceGenderCard.femalePct }}%</p>
                <p class="text-[12px] text-slate-300">{{ tt('cabinet_stats.growth.women') }}</p>
              </div>
            </div>
            <div class="mt-3 h-8 overflow-hidden rounded-lg border border-white/10 bg-black/35">
              <div class="flex h-full w-full">
                <div class="h-full bg-emerald-500/80" :style="{ width: `${audienceGenderCard.malePct}%` }" />
                <div class="h-full bg-sky-500/80" :style="{ width: `${audienceGenderCard.femalePct}%` }" />
              </div>
            </div>
            <p class="mt-2 text-[11px] text-slate-400">
              {{ tt('cabinet_stats.growth.gender_breakdown', { known: Math.round(audienceGenderCard.knownTotal), unknown: Math.round(audienceGenderCard.unknownCount) }) }}
            </p>
          </div>
        </template>
        <template v-else>
        <div class="rounded-2xl border border-white/10 bg-[#10141a]/95 p-4 backdrop-blur-md">
          <p class="text-[12px] font-semibold text-white">{{ tt('cabinet_stats.protection.filter_hits') }}</p>
          <div class="mt-4 flex gap-3">
            <div class="relative h-28 w-28 shrink-0">
              <div class="absolute inset-0 rounded-full" :style="{ background: donutGradient }" />
              <div class="absolute inset-[20%] flex flex-col items-center justify-center rounded-full bg-[#0b0e11] text-center">
                <p class="text-xl font-black tabular-nums text-white">{{ deletedTotal }}</p>
                <p class="mt-0.5 text-[9px] font-semibold text-slate-500">{{ tt('cabinet_stats.protection.total') }}</p>
              </div>
            </div>
            <div class="min-w-0 flex-1 space-y-1.5">
              <div v-for="row in donutSlices" :key="row.reason" class="flex items-center justify-between gap-2 text-[11px]">
                <span class="flex min-w-0 items-center gap-2">
                  <span class="h-2.5 w-2.5 shrink-0 rounded-sm" :style="{ backgroundColor: row.color }" />
                  <span class="truncate text-slate-200">{{ row.label }}</span>
                </span>
                <span class="shrink-0 tabular-nums text-slate-300">{{ row.n }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="rounded-2xl border border-white/10 bg-[#10141a]/95 p-4 backdrop-blur-md">
          <p class="text-[12px] font-semibold text-white">{{ tt('cabinet_stats.protection.deletion_trend') }}</p>
          <div class="mt-3 overflow-hidden rounded-2xl border border-white/[0.08] bg-gradient-to-b from-[#0c1018] to-[#080a0f] shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
            <div
              class="relative cursor-crosshair px-1 pt-1.5"
              @mousemove="onChartMove"
              @mouseleave="onChartLeave"
              @touchmove.prevent="onChartMove"
              @touchend="onChartLeave"
            >
              <div class="aspect-[360/188] w-full">
                <svg class="h-full w-full" :viewBox="`0 0 ${CHART.w} ${CHART.h}`" preserveAspectRatio="xMidYMid meet">
                <defs>
                  <linearGradient id="del-trend-area" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="#7dff3a" stop-opacity="0.28" />
                    <stop offset="100%" stop-color="#7dff3a" stop-opacity="0" />
                  </linearGradient>
                </defs>
                <line
                  v-for="(g, gi) in singleGridLines"
                  :key="`sg-${gi}`"
                  :x1="CHART.pad.l"
                  :y1="g.y"
                  :x2="CHART.w - CHART.pad.r"
                  :y2="g.y"
                  stroke="rgba(148,163,184,0.1)"
                  stroke-width="1"
                  stroke-dasharray="4 4"
                />
                <path :d="singleAreaPath" fill="url(#del-trend-area)" />
                <path
                  :d="linePath"
                  fill="none"
                  stroke="#7dff3a"
                  stroke-width="2.6"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  style="filter: drop-shadow(0 0 5px rgba(125,255,58,0.45))"
                />
                <circle
                  v-if="hoverIndex >= 0 && singleSeriesCoords[hoverIndex]"
                  :cx="singleSeriesCoords[hoverIndex].x"
                  :cy="singleSeriesCoords[hoverIndex].y"
                  r="4"
                  fill="#7dff3a"
                  stroke="#0b0e11"
                  stroke-width="1.5"
                />
                <line
                  v-if="chartHoverLineX != null"
                  :x1="chartHoverLineX"
                  :y1="CHART.pad.t"
                  :x2="chartHoverLineX"
                  :y2="CHART.h - CHART.pad.b"
                  stroke="rgba(125,255,58,0.35)"
                  stroke-width="1"
                  stroke-dasharray="3 3"
                />
                <text
                  v-for="(g, gi) in singleGridLines"
                  :key="`syl-${gi}`"
                  x="2"
                  :y="g.y + 3"
                  fill="rgba(148,163,184,0.52)"
                  font-size="9"
                >{{ g.label }}</text>
                <line
                  :x1="CHART.pad.l"
                  :y1="CHART.h - CHART.pad.b"
                  :x2="CHART.w - CHART.pad.r"
                  :y2="CHART.h - CHART.pad.b"
                  stroke="rgba(148,163,184,0.2)"
                  stroke-width="1"
                />
                <text
                  v-for="(t, ti) in timelineXAxisTicks"
                  :key="`sxl-${ti}`"
                  :x="t.x"
                  :y="CHART.h - 6"
                  text-anchor="middle"
                  fill="rgba(148,163,184,0.45)"
                  font-size="9"
                >{{ t.label }}</text>
                </svg>
              </div>
            </div>
            <div class="border-t border-white/[0.06] px-2 py-2">
              <div class="flex items-center justify-between gap-2 text-[10px]">
                <span class="font-semibold tabular-nums text-slate-300">{{ hoverIndex >= 0 ? hoverData.hour : tt('cabinet_stats.protection.legend_period_total') }}</span>
                <span v-if="hoverIndex < 0" class="text-slate-600">{{ tt('cabinet_stats.protection.legend_hover_hint') }}</span>
              </div>
              <p class="mt-1 text-xl font-black tabular-nums text-[#7dff3a]">
                {{ hoverIndex >= 0 ? hoverData.total : deletedTotal }}
              </p>
              <p class="mt-0.5 text-[10px] text-slate-500">{{ tt('cabinet_stats.protection.total') }}</p>
            </div>
          </div>
        </div>

        <div class="rounded-2xl border border-white/10 bg-[#10141a]/95 p-4 backdrop-blur-md">
          <div class="flex items-center justify-between gap-2">
            <p class="text-[12px] font-semibold text-white">{{ tt('cabinet_stats.protection.at_risk') }}</p>
            <button type="button" class="rounded-lg border border-rose-500/40 bg-rose-500/10 px-2.5 py-1 text-[11px] font-semibold text-rose-200" @click="toggleThreatSection">
              {{ threatOpen ? tt('cabinet_stats.protection.hide') : tt('cabinet_stats.protection.show') }}
            </button>
          </div>
          <div v-if="threatOpen" class="mt-3 space-y-2">
            <div v-for="c in threatTopChats" :key="`th-${c.id}`" class="rounded-xl border border-white/10 bg-black/20 p-2.5">
              <div class="flex items-center justify-between gap-2">
                <p class="truncate text-[12px] font-semibold text-white">{{ c.title || c.id }}</p>
                <span class="text-[11px] font-bold tabular-nums text-rose-200">{{ tt('cabinet_stats.protection.deletions_n', { n: c._risk }) }}</span>
              </div>
              <div class="mt-1.5 flex flex-wrap gap-1.5">
                <span v-for="r in threatTopThree(c.id)" :key="`th-${c.id}-${r.reason}`" class="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] text-slate-200">
                  <span class="h-2 w-2 rounded-full" :style="{ backgroundColor: r.color }" />
                  {{ r.label }}: {{ r.n }}
                </span>
              </div>
              <div v-if="threatLoadingId === String(c.id)" class="mt-1 text-[10px] text-slate-400">{{ tt('cabinet_stats.protection.refreshing_filters') }}</div>
              <details class="mt-2">
                <summary class="cursor-pointer text-[11px] font-semibold text-cyan-200">{{ tt('cabinet_stats.protection.expand_filters') }}</summary>
                <div class="mt-1.5 space-y-1">
                  <div
                    v-for="r in (threatDetails[c.id] || [])"
                    :key="`thall-${c.id}-${r.reason}`"
                    class="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.03] px-2 py-1 text-[10px]"
                  >
                    <span class="inline-flex items-center gap-1.5 text-slate-200">
                      <span class="h-2 w-2 rounded-full" :style="{ backgroundColor: r.color }" />
                      {{ r.label }}
                    </span>
                    <span class="font-semibold tabular-nums text-slate-100">{{ r.n }}</span>
                  </div>
                </div>
              </details>
            </div>
            <p v-if="!threatTopChats.length" class="text-[11px] text-slate-400">{{ tt('cabinet_stats.protection.no_elevated') }}</p>
          </div>
        </div>
        </template>
      </div>

      <div v-else-if="statsType === 'deletions'" class="space-y-3">
        <template v-if="statsSubView === 'timeline'">
          <div class="rounded-2xl border border-white/10 bg-[#10141a]/95 p-4 backdrop-blur-md">
            <p class="text-[12px] font-semibold text-white">{{ isGrowthMode ? tt('cabinet_stats.protection.title_growth_time') : tt('cabinet_stats.protection.title_del_time') }}</p>
            <div class="mt-3 overflow-hidden rounded-2xl border border-white/[0.08] bg-gradient-to-b from-[#0c1018] to-[#080a0f] shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
              <div
                class="relative cursor-crosshair px-1 pt-1.5"
                @mousemove="onChartMove"
                @mouseleave="onChartLeave"
                @touchmove.prevent="onChartMove"
                @touchend="onChartLeave"
              >
                <div class="aspect-[360/188] w-full">
                  <svg class="h-full w-full" :viewBox="`0 0 ${CHART.w} ${CHART.h}`" preserveAspectRatio="xMidYMid meet">
                  <defs>
                    <linearGradient v-for="r in timelineMultiSeries" :id="`tl-area-${r.reason}`" :key="`g-${r.reason}`" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" :stop-color="r.color" stop-opacity="0.22" />
                      <stop offset="100%" :stop-color="r.color" stop-opacity="0" />
                    </linearGradient>
                  </defs>
                  <line
                    v-for="(g, gi) in timelineGridLines"
                    :key="`hg-${gi}`"
                    :x1="CHART.pad.l"
                    :y1="g.y"
                    :x2="CHART.w - CHART.pad.r"
                    :y2="g.y"
                    stroke="rgba(148,163,184,0.1)"
                    stroke-width="1"
                    stroke-dasharray="4 4"
                  />
                  <path
                    v-for="r in [...timelineMultiSeries].reverse()"
                    :key="`a-${r.reason}`"
                    :d="r.areaPath"
                    :fill="`url(#tl-area-${r.reason})`"
                  />
                  <path
                    v-for="r in timelineMultiSeries"
                    :key="r.reason"
                    :d="r.path"
                    fill="none"
                    :stroke="r.color"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    :style="{ filter: `drop-shadow(0 0 3px ${r.color}66)` }"
                  />
                  <template v-if="hoverIndex >= 0">
                    <circle
                      v-for="r in timelineMultiSeries"
                      :key="`dot-${r.reason}`"
                      :cx="r.coords[hoverIndex]?.x"
                      :cy="r.coords[hoverIndex]?.y"
                      r="3.5"
                      :fill="r.color"
                      stroke="#0b0e11"
                      stroke-width="1.5"
                    />
                  </template>
                  <line
                    v-if="chartHoverLineX != null"
                    :x1="chartHoverLineX"
                    :y1="CHART.pad.t"
                    :x2="chartHoverLineX"
                    :y2="CHART.h - CHART.pad.b"
                    stroke="rgba(125,255,58,0.35)"
                    stroke-width="1"
                    stroke-dasharray="3 3"
                  />
                  <text
                    v-for="(g, gi) in timelineGridLines"
                    :key="`yl-${gi}`"
                    x="2"
                    :y="g.y + 3"
                    fill="rgba(148,163,184,0.52)"
                    font-size="9"
                  >{{ g.label }}</text>
                  <line
                    :x1="CHART.pad.l"
                    :y1="CHART.h - CHART.pad.b"
                    :x2="CHART.w - CHART.pad.r"
                    :y2="CHART.h - CHART.pad.b"
                    stroke="rgba(148,163,184,0.2)"
                    stroke-width="1"
                  />
                  <text
                    v-for="(t, ti) in timelineXAxisTicks"
                    :key="`xl-${ti}`"
                    :x="t.x"
                    :y="CHART.h - 6"
                    text-anchor="middle"
                    fill="rgba(148,163,184,0.45)"
                    font-size="9"
                  >{{ t.label }}</text>
                  </svg>
                </div>
              </div>
              <div class="border-t border-white/[0.06] px-2 py-2">
                <div class="mb-1.5 flex items-center justify-between gap-2 text-[10px]">
                  <span class="font-semibold tabular-nums text-slate-300">{{ timelineBottomCaption }}</span>
                  <span v-if="hoverIndex < 0" class="text-slate-600">{{ tt('cabinet_stats.protection.legend_hover_hint') }}</span>
                </div>
                <div class="grid grid-cols-3 gap-1.5">
                  <div
                    v-for="row in timelineBottomRows"
                    :key="row.label"
                    class="flex items-center justify-between gap-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1 transition-colors"
                    :class="hoverIndex >= 0 ? 'border-white/12 bg-white/[0.05]' : ''"
                  >
                    <span class="flex min-w-0 items-center gap-1 truncate text-[10px] text-slate-300">
                      <span class="h-1.5 w-1.5 shrink-0 rounded-full" :style="{ backgroundColor: row.color, boxShadow: `0 0 5px ${row.color}88` }" />
                      <span class="truncate">{{ row.label }}</span>
                    </span>
                    <span class="shrink-0 text-[11px] font-bold tabular-nums text-white">{{ row.n }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="rounded-2xl border border-white/10 bg-[#10141a]/95 p-4 backdrop-blur-md">
            <p class="mb-3 text-[12px] font-semibold text-white">{{ isGrowthMode ? tt('cabinet_stats.protection.title_growth_day') : tt('cabinet_stats.protection.title_del_day') }}</p>
            <div class="grid grid-cols-[34px_1fr] gap-2">
              <div class="flex h-44 flex-col justify-between pb-5 text-[10px] text-slate-500">
                <span>{{ Math.max(...weekdayRows.map((w) => w.n)) }}</span>
                <span>{{ Math.round(Math.max(...weekdayRows.map((w) => w.n)) / 2) }}</span>
                <span>0</span>
              </div>
              <div class="space-y-1">
                <div class="flex h-36 items-end gap-2">
                  <div
                    v-for="w in weekdayRows"
                    :key="w.label"
                    class="flex h-full min-w-0 flex-1 items-end justify-center"
                  >
                    <div
                      class="w-full max-w-[38px] rounded-md bg-gradient-to-t from-emerald-500 to-cyan-400 shadow-[0_12px_26px_-12px_rgba(16,185,129,0.9)]"
                      :style="{ height: `${Math.max(14, w.pct)}%` }"
                    />
                  </div>
                </div>
                <div class="flex gap-2">
                  <span
                    v-for="w in weekdayRows"
                    :key="`lbl-${w.label}`"
                    class="min-w-0 flex-1 text-center text-[10px] text-slate-400"
                  >
                    {{ w.short }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </template>

        <template v-else-if="statsSubView === 'types'">
          <div class="space-y-2">
            <div v-for="card in (isGrowthMode ? growthTypeRows : reasonRows)" :key="card.reason" class="rounded-2xl border border-white/10 bg-[#141820]/95 p-3.5 backdrop-blur-md">
              <div class="flex items-start justify-between gap-2">
                <p class="text-[14px] font-bold text-white">{{ card.label }}</p>
                <p class="shrink-0 text-[13px] tabular-nums text-slate-300">{{ card.n }} <span class="text-slate-500">({{ ((card.n / Math.max(1, isGrowthMode ? Math.max(1, growthJoined + growthLeft + growthMessages) : deletedTotal)) * 100).toFixed(1) }}%)</span></p>
              </div>
              <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
                <div class="h-full rounded-full transition-all" :style="{ width: `${Math.min(100, (card.n / Math.max(1, isGrowthMode ? Math.max(1, growthJoined + growthLeft + growthMessages) : deletedTotal)) * 100)}%`, backgroundColor: card.color }" />
              </div>
              <div v-if="!isGrowthMode && card.examples?.length" class="mt-2 flex flex-wrap gap-1.5">
                <span v-for="ex in card.examples.slice(0, 8)" :key="`${card.reason}-${ex}`" class="rounded-full border border-white/10 bg-black/35 px-2 py-0.5 text-[10px] text-slate-300">{{ ex }}</span>
              </div>
              <button
                v-if="!isGrowthMode && card.n > 0"
                type="button"
                class="mt-2.5 w-full rounded-xl border border-cyan-400/30 bg-cyan-500/10 px-3 py-2 text-[11px] font-semibold text-cyan-100 transition hover:bg-cyan-500/15"
                @click="openReasonHitsModal(card)"
              >
                {{ tt('cabinet_stats.protection.show_full_list') }}
              </button>
            </div>
          </div>
        </template>

        <template v-else-if="statsSubView === 'hours'">
          <div class="rounded-2xl border border-white/10 bg-[#10141a]/95 p-3 backdrop-blur-md">
            <p class="mb-2 text-[12px] font-semibold text-white">{{ isGrowthMode ? tt('cabinet_stats.protection.title_growth_hour') : tt('cabinet_stats.protection.title_del_hour') }}</p>
            <div class="grid grid-cols-[18px_repeat(7,minmax(0,1fr))] gap-1 text-[10px]">
              <span />
              <span v-for="d in heatDayLabels" :key="`hd-${d}`" class="text-center text-slate-400">{{ d }}</span>
              <template v-for="(row, ri) in heatGrid" :key="`r-${ri}`">
                <span class="self-center text-slate-500">{{ heatRowLabels[ri] }}</span>
                <span v-for="(cell, ci) in row" :key="`c-${ri}-${ci}`" class="block h-6 rounded-[6px] border border-white/10" :style="heatCellStyle(cell)" />
              </template>
            </div>
            <div class="mt-3 flex items-center justify-between text-[10px] text-slate-400">
              <span>{{ tt('cabinet_stats.protection.less') }}</span>
              <div class="mx-2 h-2 flex-1 rounded-full bg-gradient-to-r from-violet-950 to-violet-500" />
              <span>{{ tt('cabinet_stats.protection.more') }}</span>
            </div>
          </div>
        </template>

        <template v-else-if="statsSubView === 'weekdays'">
          <div class="rounded-2xl border border-white/10 bg-[#10141a]/95 p-4 backdrop-blur-md">
            <p class="mb-3 text-[12px] font-semibold text-white">{{ isGrowthMode ? tt('cabinet_stats.protection.title_growth_week') : tt('cabinet_stats.protection.title_del_week') }}</p>
            <div class="space-y-2.5">
              <div v-for="w in weekdayRows" :key="w.label" class="grid grid-cols-[1fr_2.5fr_auto] items-center gap-2">
                <span class="text-[12px] text-slate-300">{{ w.label }}</span>
                <div class="h-3 rounded-full bg-white/10">
                  <div class="h-full rounded-full bg-gradient-to-r from-violet-700 to-purple-500" :style="{ width: `${Math.max(4, w.pct)}%` }" />
                </div>
                <span class="text-[12px] font-semibold tabular-nums text-slate-200">{{ w.n }}</span>
              </div>
            </div>
          </div>
        </template>
      </div>

      <div v-else-if="statsType === 'connections'" class="space-y-2">
        <div v-for="c in connectionsRows.slice(0, 12)" :key="c.id" class="flex items-center gap-3 rounded-2xl border border-white/10 bg-[#12161c]/90 p-3 backdrop-blur-md">
          <ChatAvatar
            :chat-id="c.id"
            :title="c.title || String(c.id)"
            :username="c.username || ''"
          />
          <div class="min-w-0 flex-1">
            <p class="truncate text-[14px] font-semibold text-white">{{ c.title || c.id }}</p>
            <p class="text-[11px] text-slate-500">
              <template v-if="isGrowthMode">
                {{ tt('cabinet_stats.protection.conn_growth', { joined: Number(c.joined || 0), left: Number(c.left || 0), messages: Number(c.messages || 0) }) }}
              </template>
              <template v-else>
                {{ tt('cabinet_stats.protection.conn_mod', { deleted: Number(c.deleted || c.moderation || 0), messages: Number(c.messages || 0) }) }}
              </template>
            </p>
          </div>
          <span class="shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-bold" :class="Number((isGrowthMode ? c.messages : (c.deleted || c.moderation)) || 0) > 0 ? 'border-emerald-400/40 text-emerald-200' : 'border-white/15 text-slate-400'">{{ Number((isGrowthMode ? c.messages : (c.deleted || c.moderation)) || 0) > 0 ? tt('cabinet_stats.protection.active') : tt('cabinet_stats.protection.quiet') }}</span>
        </div>
        <p v-if="!connectionsRows.length" class="py-8 text-center text-[13px] text-slate-500">{{ tt('cabinet_stats.protection.no_data_period') }}</p>
        <button type="button" class="w-full rounded-2xl border border-cyan-400/35 bg-cyan-500/10 py-3 text-[13px] font-semibold text-cyan-100" @click="emit('open-groups')">{{ tt('cabinet_stats.protection.show_all_chats') }}</button>
      </div>
    </div>
  </div>
  <Teleport to="body">
    <div
      v-if="growthModalOpen"
      class="fixed inset-0 z-[96000] flex items-end justify-center overscroll-contain bg-black/75 p-3 pb-[max(1rem,env(safe-area-inset-bottom))] backdrop-blur-sm sm:items-center"
      @click.self="closeGrowthEventsModal"
      @touchmove.prevent
    >
      <div
        class="flex max-h-[min(88vh,640px)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-emerald-400/30 bg-[#0b0e11] shadow-[0_28px_80px_-24px_rgba(16,185,129,0.45)] ring-1 ring-emerald-400/20"
        @click.stop
      >
        <div class="flex shrink-0 items-start justify-between gap-2 border-b border-white/10 px-4 py-3">
          <div class="min-w-0">
            <p class="text-sm font-semibold text-white">{{ growthModalTitle }}</p>
            <p v-if="growthModalPeriodLabel" class="mt-0.5 text-[10px] text-slate-400">{{ growthModalPeriodLabel }}</p>
          </div>
          <button type="button" class="guard-green-soft shrink-0 rounded-lg px-3 py-1.5 text-[11px] font-semibold" @click="closeGrowthEventsModal">{{ tt('common.close') }}</button>
        </div>
        <div v-if="growthModalLoading" class="px-4 py-10 text-center text-sm text-slate-400">
          <span class="hourglass-flip mr-1 inline-block" aria-hidden="true">⏳</span>{{ tt('cabinet_stats.growth.modal_loading') }}
        </div>
        <div v-else class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-2">
          <p v-if="!growthModalItems.length" class="py-6 text-center text-[12px] text-slate-500">{{ tt('cabinet_stats.growth.modal_empty') }}</p>
          <div
            v-for="(row, idx) in growthModalItems"
            :key="`gr-${idx}-${row.user_id}-${row.at}`"
            class="mb-2 rounded-xl border border-white/10 bg-[#11151C] px-3 py-2.5"
          >
            <div class="flex items-start justify-between gap-2">
              <p class="text-[13px] font-semibold text-emerald-200">{{ growthUserLabel(row) }}</p>
              <span
                class="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold"
                :class="row.event === 'left' ? 'bg-orange-500/20 text-orange-200' : 'bg-emerald-500/20 text-emerald-200'"
              >
                {{ row.event === 'left' ? tt('cabinet_stats.growth.event_left') : tt('cabinet_stats.growth.event_joined') }}
              </span>
            </div>
            <p class="mt-1 text-[11px] tabular-nums text-slate-400">{{ growthEventTime(row.at) }}</p>
            <p class="mt-0.5 text-[11px] text-slate-300">
              {{ growthChatKindLabel(row.chat_kind) }}: <span class="text-zinc-100">{{ row.chat_title }}</span>
            </p>
          </div>
        </div>
      </div>
    </div>
  </Teleport>

  <Teleport to="body">
    <div
      v-if="reasonHitsModalOpen"
      class="fixed inset-0 z-[96000] flex items-end justify-center overscroll-contain bg-black/75 p-3 pb-[max(1rem,env(safe-area-inset-bottom))] backdrop-blur-sm sm:items-center"
      @click.self="closeReasonHitsModal"
      @touchmove.prevent
    >
      <div
        class="flex max-h-[min(88vh,640px)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-cyan-400/30 bg-[#0b0e11] shadow-[0_28px_80px_-24px_rgba(34,211,238,0.35)] ring-1 ring-cyan-400/20"
        @click.stop
      >
        <div class="flex shrink-0 items-start justify-between gap-2 border-b border-white/10 px-4 py-3">
          <div class="min-w-0">
            <p class="truncate text-sm font-semibold text-white">{{ reasonHitsModalLabel }}</p>
            <p v-if="reasonHitsModalTotal > 0" class="mt-0.5 text-[10px] text-slate-400">
              {{ tt('cabinet_stats.protection.hits_modal_count', { shown: reasonHitsModalItems.length, total: reasonHitsModalTotal }) }}
            </p>
          </div>
          <button type="button" class="guard-green-soft shrink-0 rounded-lg px-3 py-1.5 text-[11px] font-semibold" @click="closeReasonHitsModal">{{ tt('common.close') }}</button>
        </div>
        <div v-if="reasonHitsModalLoading && !reasonHitsModalItems.length" class="px-4 py-10 text-center text-sm text-slate-400">
          <span class="hourglass-flip mr-1 inline-block" aria-hidden="true">⏳</span>{{ tt('cabinet_stats.protection.hits_loading') }}
        </div>
        <div v-else class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-2">
          <p v-if="!reasonHitsModalItems.length" class="py-6 text-center text-[12px] text-slate-500">{{ tt('cabinet_stats.protection.hits_empty') }}</p>
          <div
            v-for="row in reasonHitsModalItems"
            :key="`rh-${row.id}-${row.created_at}`"
            class="mb-2 rounded-xl border border-white/10 bg-[#11151C] px-3 py-2.5"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
                <button
                  v-if="moderationUsername(row)"
                  type="button"
                  class="text-[13px] font-semibold text-cyan-300 underline decoration-cyan-500/35 underline-offset-2 hover:text-cyan-200"
                  @click="openModerationUserProfile(row)"
                >
                  @{{ moderationUsername(row) }}
                </button>
                <span
                  v-if="moderationUsername(row) && moderationFirstName(row)"
                  class="text-[12px] text-slate-600"
                  aria-hidden="true"
                >·</span>
                <button
                  v-else-if="Number(row.user_id) > 0"
                  type="button"
                  class="text-[13px] font-semibold text-cyan-300 underline decoration-cyan-500/35 underline-offset-2 hover:text-cyan-200"
                  @click="openModerationUserProfile(row)"
                >
                  id {{ row.user_id }}
                </button>
                <span
                  v-if="moderationFirstName(row)"
                  class="text-[13px] font-semibold text-white"
                >
                  {{ moderationFirstName(row) }}
                </span>
                <span
                  v-if="!moderationUsername(row) && !moderationFirstName(row) && !(Number(row.user_id) > 0)"
                  class="text-[13px] text-slate-400"
                >
                  —
                </span>
              </div>
              <span class="shrink-0 text-[10px] tabular-nums text-slate-500">{{ moderationHitTime(row.created_at) }}</span>
            </div>
            <p v-if="row.chat_title" class="mt-1 text-[10px] text-slate-500">{{ row.chat_title }}</p>
            <p v-if="row.message_text" class="mt-2 whitespace-pre-wrap break-words text-[12px] leading-relaxed text-zinc-100">{{ row.message_text }}</p>
            <p v-else class="mt-2 text-[12px] italic text-slate-500">—</p>
            <div class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px]">
              <span
                class="inline-flex shrink-0 rounded-full px-2 py-0.5 font-semibold"
                :class="moderationStatusClass(row)"
              >
                {{ moderationStatusLabel(row) }}
              </span>
              <span class="min-w-0 text-amber-200/90">
                {{ tt('cabinet_stats.protection.hit_trigger', { detail: moderationTriggerText(row) }) }}
              </span>
            </div>
          </div>
          <button
            v-if="reasonHitsModalHasMore"
            type="button"
            class="mb-2 w-full rounded-xl border border-white/15 bg-white/[0.04] py-2.5 text-[12px] font-semibold text-slate-200 disabled:opacity-50"
            :disabled="reasonHitsModalLoading"
            @click="loadMoreReasonHits"
          >
            {{ reasonHitsModalLoading ? tt('cabinet_stats.protection.hits_loading') : tt('cabinet_stats.protection.hits_load_more') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>

</template>

<style scoped>
@keyframes hourglassFlip {
  0% {
    transform: rotate(0deg);
  }
  50% {
    transform: rotate(180deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

.hourglass-flip {
  animation: hourglassFlip 0.9s ease-in-out infinite;
  transform-origin: 50% 50%;
}
</style>

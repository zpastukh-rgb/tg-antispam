<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '../api/client'

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
const hoverIndex = ref(-1)
const threatOpen = ref(false)
const threatLoadingId = ref('')
const threatDetails = ref({})
let silentRefreshTimer = null

watch(() => props.periodKey, (k) => {
  if (k && k !== statsPeriod.value) statsPeriod.value = k
})

const PERIOD_ROWS = [
  { key: 'today', label: 'Сегодня' },
  { key: '7d', label: '7 дней' },
  { key: '30d', label: '30 дней' },
  { key: '6m', label: '6 месяцев' },
  { key: '1y', label: 'Год' },
]
const TYPE_TABS = [
  { key: 'all', label: 'Все действия' },
  { key: 'deletions', label: 'Удаления' },
  { key: 'connections', label: 'Подключения' },
]
const SCOPE_TABS = [
  { key: 'all', label: 'Все' },
  { key: 'own', label: 'Свои' },
  { key: 'delegated', label: 'Делегированные' },
]
const SUB_TABS = [
  { key: 'timeline', label: 'Динамика' },
  { key: 'types', label: 'Типы' },
  { key: 'hours', label: 'Часы' },
  { key: 'weekdays', label: 'Дни недели' },
]
const typeTabs = computed(() =>
  TYPE_TABS.map((t) => (isGrowthMode.value && t.key === 'deletions' ? { ...t, label: 'Рост' } : t)),
)

const COLOR_POOL = ['#ef4444', '#3b82f6', '#f59e0b', '#f97316', '#60a5fa', '#dc2626', '#fb923c']
const REASON_LABEL_MAP = {
  ads: 'Реклама',
  vulgar: 'Вульгарность',
  nazi: 'Нацизм',
  insult: 'Оскорбления',
  racism: 'Расизм',
  profanity: 'Мат',
  stopword: 'Запретные слова',
  media: 'Медиа',
  link: 'Ссылки',
  mention: 'Упоминания',
  casino: 'Казино / ставки',
  jobs: 'Подработки',
  politics: 'Анти-политика',
  religion: 'Религия',
  esoteric: 'Эзотерика / магия',
  buttons: 'Кнопки',
  antinakrutka: 'Анти-накрутка',
  flood: 'Флуд',
  raid: 'Рейд',
  captcha: 'Капча',
  global_antispam: 'Глобальный антиспам',
  forward: 'Репосты',
  nationalism: 'Национализм',
  extremism: 'Экстремизм',
  terror: 'Терроризм',
  global_url: 'Глобальные URL',
  url: 'URL',
  hate: 'Ненависть',
  abuse: 'Абьюз',
  spam: 'Спам',
}

const totals = computed(() => props.hourlyData?.totals || {})
const chats = computed(() => (Array.isArray(props.hourlyData?.chats) ? props.hourlyData.chats : []))
const chatsCount = computed(() => Math.max(0, Math.round(Number((props.summary?.groups_count ?? props.summary?.chats_count) || 0))))
const joinsTotal = computed(() => Math.max(0, Math.round(Number(totals.value?.joins || 0))))
const isGrowthMode = computed(() => String(props.mode || 'protection') === 'growth')

const breakdownLoading = ref(false)
const breakdownData = ref(null)
function isChannelChat(c) {
  const kind = String(c?.chat_kind || c?.kind || 'group').toLowerCase()
  return kind === 'channel'
}
const availableScopeChats = computed(() => {
  const rows = Array.isArray(breakdownData.value?.chats) ? breakdownData.value.chats : []
  if (statsScope.value === 'delegated') {
    return rows.filter((c) => (c?.is_delegated || c?.is_shared) && !isChannelChat(c))
  }
  if (statsScope.value === 'own') {
    return rows.filter((c) => !(c?.is_delegated || c?.is_shared))
  }
  return rows
})
const selectedScopeChatRow = computed(() => {
  if (selectedChatId.value === 'all') return null
  const id = String(selectedChatId.value)
  const inScoped = availableScopeChats.value.find((c) => String(c?.id) === id)
  if (inScoped) return inScoped
  return chats.value.find((c) => String(c?.id) === id) || null
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
  if (!k) return 'Неизвестно'
  if (REASON_LABEL_MAP[k]) return REASON_LABEL_MAP[k]
  return k.replace(/_/g, ' ')
}
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

async function loadBreakdown() {
  breakdownLoading.value = true
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
    breakdownLoading.value = false
  }
}
watch(statsScope, () => {
  selectedChatId.value = 'all'
  // Не показываем список из прошлого scope до загрузки нового.
  breakdownData.value = null
})
watch(availableScopeChats, (rows) => {
  if (!Array.isArray(rows) || rows.length === 0) return
  if (selectedChatId.value === 'all') return
  const ok = rows.some((c) => String(c?.id) === String(selectedChatId.value))
  if (!ok) selectedChatId.value = 'all'
})
watch([statsPeriod, statsScope, selectedChatId], () => void loadBreakdown(), { immediate: true })
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
    return [{ reason: 'fallback', label: 'Без детализации', n: deletedTotal.value, color: '#334155', pct: 100, start: 0, end: 100 }]
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

const growthJoined = computed(() => Math.max(0, toNum(breakdownData.value?.total_joined || 0)))
const growthLeft = computed(() => Math.max(0, toNum(breakdownData.value?.total_left || 0)))
const growthNet = computed(() => growthJoined.value - growthLeft.value)
const growthMessages = computed(() => Math.max(0, toNum(breakdownData.value?.total_messages || 0)))
const growthTopChat = computed(() => {
  if (selectedScopeChatRow.value) {
    return {
      title: String(selectedScopeChatRow.value?.title || selectedScopeChatRow.value?.id || 'Чат'),
      messages: Math.max(0, toNum(selectedScopeChatRow.value?.messages || 0)),
      joins: Math.max(0, toNum(selectedScopeChatRow.value?.joined || 0)),
      left: Math.max(0, toNum(selectedScopeChatRow.value?.left || 0)),
    }
  }
  const rows = Array.isArray(connectionsRows.value) ? connectionsRows.value : []
  if (!rows.length) return { title: 'Нет данных', messages: 0, joins: 0, left: 0 }
  const best = [...rows].sort((a, b) => Number(b?.messages || 0) - Number(a?.messages || 0))[0]
  return {
    title: String(best?.title || best?.id || 'Чат'),
    messages: Math.max(0, toNum(best?.messages || 0)),
    joins: Math.max(0, toNum(best?.joined || 0)),
    left: Math.max(0, toNum(best?.left || 0)),
  }
})

const chatRowsForStats = computed(() => {
  const rows = Array.isArray(breakdownData.value?.chats) && breakdownData.value.chats.length
    ? breakdownData.value.chats
    : chats.value
  return Array.isArray(rows) ? rows : []
})
const channelRowsForStats = computed(() => chatRowsForStats.value.filter((c) => isChannelChat(c)))
const groupRowsForStats = computed(() => chatRowsForStats.value.filter((c) => !isChannelChat(c)))
const channelMessagesTotal = computed(() =>
  channelRowsForStats.value.reduce((acc, c) => acc + Math.max(0, toNum(c?.messages || 0)), 0),
)
const channelGrowthNet = computed(() =>
  channelRowsForStats.value.reduce((acc, c) => acc + Math.max(0, toNum(c?.joined || 0)) - Math.max(0, toNum(c?.left || 0)), 0),
)
const topChannelByMessages = computed(() => {
  if (!channelRowsForStats.value.length) return null
  return [...channelRowsForStats.value].sort((a, b) => toNum(b?.messages || 0) - toNum(a?.messages || 0))[0] || null
})
const audienceGenderCard = computed(() => {
  const g = props.audienceGender || {}
  const malePct = Math.max(0, Math.min(100, Number(g?.malePct || 0)))
  const femalePct = Math.max(0, Math.min(100, Number(g?.femalePct || (100 - malePct))))
  const knownTotal = Math.max(0, Number(g?.knownTotal || 0))
  return {
    audience: Math.max(0, Number(g?.audience || 0)),
    malePct: Number.isFinite(malePct) ? Math.round(malePct * 10) / 10 : 0,
    femalePct: Number.isFinite(femalePct) ? Math.round(femalePct * 10) / 10 : 0,
    maleCount: Math.max(0, Number(g?.maleCount || 0)),
    femaleCount: Math.max(0, Number(g?.femaleCount || 0)),
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
const yMax = computed(() => Math.max(4, ...byHour.value))
const yTicks = computed(() => [yMax.value, Math.round(yMax.value * 0.66), Math.round(yMax.value * 0.33), 0])

function linePathFor(values) {
  const vals = (values || []).map((v) => Number(v || 0))
  const w = 320
  const h = 132
  const padL = 28
  const padR = 8
  const padT = 8
  const padB = 18
  const maxV = Math.max(1, ...vals)
  const step = vals.length > 1 ? (w - padL - padR) / (vals.length - 1) : 0
  return vals.map((v, i) => {
    const x = padL + i * step
    const y = padT + (h - padT - padB) * (1 - Math.min(1, v / maxV))
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`
  }).join(' ')
}
const linePath = computed(() => linePathFor(byHour.value))

const top3Reasons = computed(() => reasonRows.value.slice(0, 6))
const growthTypeRows = computed(() => {
  const rows = [
    { reason: 'joined', label: 'Подписались', n: growthJoined.value, color: '#10b981' },
    { reason: 'left', label: 'Отписались', n: growthLeft.value, color: '#f97316' },
    { reason: 'net', label: 'Чистый рост', n: Math.abs(growthNet.value), color: growthNet.value >= 0 ? '#34d399' : '#fb7185' },
    { reason: 'messages', label: 'Сообщения', n: growthMessages.value, color: '#8b5cf6' },
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
const timelineMultiSeries = computed(() =>
  isGrowthMode.value
    ? [
      { reason: 'joined', label: 'Подписки', color: '#10b981', vals: Array.isArray(breakdownData.value?.by_hour_joins) ? breakdownData.value.by_hour_joins.map((x) => Math.max(0, toNum(x))) : Array.from({ length: 24 }, () => 0) },
      { reason: 'left', label: 'Отписки', color: '#f97316', vals: Array.isArray(breakdownData.value?.by_hour_leaves) ? breakdownData.value.by_hour_leaves.map((x) => Math.max(0, toNum(x))) : Array.from({ length: 24 }, () => 0) },
      { reason: 'messages', label: 'Сообщения', color: '#8b5cf6', vals: Array.isArray(breakdownData.value?.by_hour_messages) ? breakdownData.value.by_hour_messages.map((x) => Math.max(0, toNum(x))) : Array.from({ length: 24 }, () => 0) },
    ].map((r) => ({ ...r, path: linePathFor(r.vals) }))
    : top3Reasons.value.map((r) => ({
      ...r,
      vals: byHourByReason.value[r.reason] || Array.from({ length: 24 }, () => 0),
      path: linePathFor(byHourByReason.value[r.reason] || Array.from({ length: 24 }, () => 0)),
    })),
)

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
    { full: 'Понедельник', short: 'Пн' },
    { full: 'Вторник', short: 'Вт' },
    { full: 'Среда', short: 'Ср' },
    { full: 'Четверг', short: 'Чт' },
    { full: 'Пятница', short: 'Пт' },
    { full: 'Суббота', short: 'Сб' },
    { full: 'Воскресенье', short: 'Вс' },
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
const heatDayLabels = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
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
  const fallback = chats.value
  if (statsScope.value === 'delegated') {
    return fallback.filter((c) => (c?.is_delegated || c?.is_shared) && !isChannelChat(c))
  }
  if (statsScope.value === 'own') {
    return fallback.filter((c) => !(c?.is_delegated || c?.is_shared))
  }
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
  statsPeriod.value = key
  emit('period-change', { key })
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
  statsScope.value = String(scopeKey || 'all')
  emitReportContextNow()
}
function pickScopeAllChats() {
  selectedChatId.value = 'all'
  emitReportContextNow()
}
function pickScopeChat(chatId) {
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
  const order = TYPE_TABS.map((t) => t.key)
  const i = order.indexOf(statsType.value)
  if (dx < 0 && i < order.length - 1) statsType.value = order[i + 1]
  else if (dx > 0 && i > 0) statsType.value = order[i - 1]
}

onMounted(() => {
  silentRefreshTimer = setInterval(() => {
    void loadBreakdown()
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
        <button v-for="p in PERIOD_ROWS" :key="p.key" type="button" class="shrink-0 rounded-full px-3.5 py-2 text-[12px] font-semibold transition active:scale-[0.98]" :class="pillActiveClass(statsPeriod === p.key)" @click="onPeriodPick(p.key)">
          {{ p.label }}
        </button>
      </div>
      <div class="flex gap-2 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <button v-for="t in typeTabs" :key="t.key" type="button" class="shrink-0 rounded-full px-3.5 py-2 text-[12px] font-semibold transition active:scale-[0.98]" :class="pillActiveClass(statsType === t.key)" @click="statsType = t.key">
          {{ t.label }}
        </button>
      </div>
      <div v-if="statsType === 'deletions'" class="flex gap-2 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <button v-for="s in SUB_TABS" :key="s.key" type="button" class="shrink-0 rounded-full px-3.5 py-1.5 text-[11px] font-semibold transition active:scale-[0.98]" :class="pillActiveClass(statsSubView === s.key)" @click="statsSubView = s.key">
          {{ s.label }}
        </button>
      </div>
      <div class="grid grid-cols-3 gap-2">
        <button v-for="s in SCOPE_TABS" :key="s.key" type="button" class="rounded-xl border px-2.5 py-2 text-[11px] font-semibold transition" :class="statsScope === s.key ? 'border-[#7dff3a]/80 bg-[rgba(125,255,58,0.14)] text-[#deffbf]' : 'border-white/10 bg-white/[0.04] text-slate-300'" @click="pickStatsScope(s.key)">
          {{ s.label }}
        </button>
      </div>
      <div v-if="statsScope !== 'all' && availableScopeChats.length" class="flex gap-2 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <button type="button" class="shrink-0 rounded-full px-3 py-1.5 text-[11px] font-semibold transition" :class="pillActiveClass(selectedChatId === 'all')" @click="pickScopeAllChats()">
          Все группы
        </button>
        <button
          v-for="c in availableScopeChats"
          :key="`sc-${c.id}`"
          type="button"
          class="shrink-0 rounded-full px-3 py-1.5 text-[11px] font-semibold transition"
          :class="pillActiveClass(String(selectedChatId) === String(c.id))"
          @click="pickScopeChat(c.id)"
        >
          {{ c.title || c.id }}
        </button>
      </div>
      <p v-if="false && (loading || breakdownLoading)" class="px-0.5 text-[11px] text-emerald-300/80">Обновление…</p>
    </div>

    <div class="min-h-0 flex-1 touch-pan-y overflow-y-auto overscroll-contain px-1 pb-4 pt-3" @touchstart.passive="onTouchStart" @touchend="onTouchEnd">
      <div v-if="statsType === 'all'" class="space-y-3">
        <template v-if="isGrowthMode">
          <div class="rounded-2xl border border-white/10 bg-[#10141a]/95 p-4 backdrop-blur-md">
            <p class="text-[12px] font-semibold text-white">Рост аудитории</p>
            <div class="mt-3 grid grid-cols-2 gap-2">
              <div class="rounded-xl border border-white/10 bg-black/20 p-2.5">
                <p class="text-[10px] text-emerald-200/85">Подписалось</p>
                <p class="mt-0.5 text-lg font-black tabular-nums text-white">{{ growthJoined }}</p>
              </div>
              <div class="rounded-xl border border-white/10 bg-black/20 p-2.5">
                <p class="text-[10px] text-orange-200/85">Отписалось</p>
                <p class="mt-0.5 text-lg font-black tabular-nums text-white">{{ growthLeft }}</p>
              </div>
            </div>
            <div class="mt-2 rounded-xl border border-violet-400/25 bg-violet-950/20 p-2.5">
              <p class="text-[10px] text-violet-200/85">Чистый рост</p>
              <p class="mt-0.5 text-lg font-black tabular-nums" :class="growthNet >= 0 ? 'text-emerald-200' : 'text-rose-200'">
                {{ growthNet >= 0 ? '+' : '' }}{{ growthNet }}
              </p>
              <p class="mt-1 text-[10px] text-violet-100/80">Сообщений: {{ growthMessages }}</p>
            </div>
          </div>
          <div class="rounded-2xl border border-white/10 bg-[#10141a]/95 p-4 backdrop-blur-md">
            <p class="text-[12px] font-semibold text-white">Самый активный чат</p>
            <p class="mt-2 truncate text-[14px] font-bold text-white">{{ growthTopChat.title }}</p>
            <p class="mt-1 text-[11px] text-slate-300">
              Сообщений: <span class="font-semibold tabular-nums text-white">{{ growthTopChat.messages }}</span>
              · Подписалось: <span class="font-semibold tabular-nums text-white">{{ growthTopChat.joins }}</span>
              · Отписалось: <span class="font-semibold tabular-nums text-white">{{ growthTopChat.left }}</span>
            </p>
          </div>
          <div class="rounded-2xl border border-white/10 bg-[#10141a]/95 p-4 backdrop-blur-md">
            <div class="flex items-center justify-between gap-2">
              <p class="text-[12px] font-semibold text-white">Статистика чатов и каналов</p>
              <span class="text-[10px] text-slate-400">всего: {{ chatRowsForStats.length }}</span>
            </div>
            <div class="mt-3 grid grid-cols-2 gap-2">
              <div class="rounded-xl border border-white/10 bg-black/20 p-2.5">
                <p class="text-[10px] text-slate-300/90">Группы</p>
                <p class="mt-0.5 text-lg font-black tabular-nums text-white">{{ groupRowsForStats.length }}</p>
              </div>
              <div class="rounded-xl border border-cyan-400/20 bg-cyan-950/20 p-2.5">
                <p class="text-[10px] text-cyan-100/90">Каналы</p>
                <p class="mt-0.5 text-lg font-black tabular-nums text-cyan-100">{{ channelRowsForStats.length }}</p>
              </div>
            </div>
            <div class="mt-2 grid grid-cols-2 gap-2">
              <div class="rounded-xl border border-white/10 bg-black/20 p-2.5">
                <p class="text-[10px] text-slate-300/90">Сообщений в каналах</p>
                <p class="mt-0.5 text-lg font-black tabular-nums text-white">{{ channelMessagesTotal }}</p>
              </div>
              <div class="rounded-xl border border-emerald-400/20 bg-emerald-950/15 p-2.5">
                <p class="text-[10px] text-emerald-100/90">Прирост каналов</p>
                <p class="mt-0.5 text-lg font-black tabular-nums" :class="channelGrowthNet >= 0 ? 'text-emerald-200' : 'text-rose-200'">{{ channelGrowthNet >= 0 ? '+' : '' }}{{ channelGrowthNet }}</p>
              </div>
            </div>
            <p class="mt-2 truncate text-[11px] text-slate-400">
              Топ канал: <span class="font-semibold text-white">{{ topChannelByMessages?.title || '—' }}</span>
              <span v-if="topChannelByMessages"> · {{ Math.max(0, toNum(topChannelByMessages?.messages || 0)) }} сообщений</span>
            </p>
          </div>
          <div class="rounded-2xl border border-white/10 bg-[#10141a]/95 p-4 backdrop-blur-md">
            <div class="mb-2 flex items-center justify-between gap-2">
              <p class="text-[12px] font-semibold text-white">Пол участников</p>
              <p class="text-[11px] text-slate-400">аудитория: {{ Math.round(audienceGenderCard.audience) }}</p>
            </div>
            <div class="flex items-end justify-between gap-3">
              <div>
                <p class="text-3xl font-extrabold leading-none text-white">{{ audienceGenderCard.malePct }}%</p>
                <p class="text-sm font-semibold text-cyan-200">{{ Math.round(audienceGenderCard.maleCount) }}</p>
                <p class="text-[12px] text-slate-300">мужчины</p>
              </div>
              <div class="text-right">
                <p class="text-3xl font-extrabold leading-none text-white">{{ audienceGenderCard.femalePct }}%</p>
                <p class="text-sm font-semibold text-rose-200">{{ Math.round(audienceGenderCard.femaleCount) }}</p>
                <p class="text-[12px] text-slate-300">женщины</p>
              </div>
            </div>
            <div class="mt-3 h-8 overflow-hidden rounded-lg border border-white/10 bg-black/35">
              <div class="flex h-full w-full">
                <div
                  class="flex h-full items-center justify-center bg-cyan-500/75 text-sm font-bold text-white"
                  :style="{ width: `${audienceGenderCard.malePct}%` }"
                >
                  {{ audienceGenderCard.malePct }}%
                </div>
                <div
                  class="flex h-full items-center justify-center bg-rose-500/80 text-sm font-bold text-white"
                  :style="{ width: `${audienceGenderCard.femalePct}%` }"
                >
                  {{ audienceGenderCard.femalePct }}%
                </div>
              </div>
            </div>
            <p class="mt-2 text-[11px] text-slate-400">
              Учтено по именам: {{ Math.round(audienceGenderCard.knownTotal) }}, не определено: {{ Math.round(audienceGenderCard.unknownCount) }}
            </p>
          </div>
        </template>
        <template v-else>
        <div class="rounded-2xl border border-white/10 bg-[#10141a]/95 p-4 backdrop-blur-md">
          <p class="text-[12px] font-semibold text-white">Срабатывания фильтров</p>
          <div class="mt-4 flex gap-3">
            <div class="relative h-28 w-28 shrink-0">
              <div class="absolute inset-0 rounded-full" :style="{ background: donutGradient }" />
              <div class="absolute inset-[20%] flex flex-col items-center justify-center rounded-full bg-[#0b0e11] text-center">
                <p class="text-xl font-black tabular-nums text-white">{{ deletedTotal }}</p>
                <p class="mt-0.5 text-[9px] font-semibold text-slate-500">Всего</p>
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
          <p class="text-[12px] font-semibold text-white">Динамика удалений</p>
          <div class="relative mt-3 overflow-hidden rounded-xl border border-white/[0.06] bg-[#0b0e11] px-2 py-3" @mousemove="onChartMove" @mouseleave="onChartLeave" @touchmove.prevent="onChartMove" @touchend="onChartLeave">
            <svg class="h-[148px] w-full" viewBox="0 0 320 132" preserveAspectRatio="none">
              <line x1="28" y1="114" x2="312" y2="114" stroke="rgba(148,163,184,0.15)" stroke-width="1" />
              <text v-for="(yv, yi) in yTicks" :key="`y-${yi}`" x="2" :y="10 + yi * 34" fill="rgba(148,163,184,0.52)" font-size="9">{{ yv }}</text>
              <text x="28" y="126" fill="rgba(148,163,184,0.45)" font-size="9">{{ xTickLabels[0] }}</text>
              <text x="96" y="126" fill="rgba(148,163,184,0.45)" font-size="9">{{ xTickLabels[1] }}</text>
              <text x="164" y="126" fill="rgba(148,163,184,0.45)" font-size="9">{{ xTickLabels[2] }}</text>
              <text x="232" y="126" fill="rgba(148,163,184,0.45)" font-size="9">{{ xTickLabels[3] }}</text>
              <text x="286" y="126" fill="rgba(148,163,184,0.45)" font-size="9">{{ xTickLabels[4] }}</text>
              <path :d="linePath" fill="none" stroke="#7dff3a" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            <div class="pointer-events-none absolute right-2 top-2 rounded-lg border border-slate-600/80 bg-slate-900/95 px-2.5 py-1.5 text-[10px] text-slate-200">
              {{ hoverData.hour }} · {{ hoverData.total }} удалений
            </div>
          </div>
        </div>

        <div class="rounded-2xl border border-white/10 bg-[#10141a]/95 p-4 backdrop-blur-md">
          <div class="flex items-center justify-between gap-2">
            <p class="text-[12px] font-semibold text-white">Под угрозой</p>
            <button type="button" class="rounded-lg border border-rose-500/40 bg-rose-500/10 px-2.5 py-1 text-[11px] font-semibold text-rose-200" @click="toggleThreatSection">
              {{ threatOpen ? 'Скрыть' : 'Показать' }}
            </button>
          </div>
          <div v-if="threatOpen" class="mt-3 space-y-2">
            <div v-for="c in threatTopChats" :key="`th-${c.id}`" class="rounded-xl border border-white/10 bg-black/20 p-2.5">
              <div class="flex items-center justify-between gap-2">
                <p class="truncate text-[12px] font-semibold text-white">{{ c.title || c.id }}</p>
                <span class="text-[11px] font-bold tabular-nums text-rose-200">{{ c._risk }} удалений</span>
              </div>
              <div class="mt-1.5 flex flex-wrap gap-1.5">
                <span v-for="r in threatTopThree(c.id)" :key="`th-${c.id}-${r.reason}`" class="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] text-slate-200">
                  <span class="h-2 w-2 rounded-full" :style="{ backgroundColor: r.color }" />
                  {{ r.label }}: {{ r.n }}
                </span>
              </div>
              <div v-if="threatLoadingId === String(c.id)" class="mt-1 text-[10px] text-slate-400">Обновляем фильтры…</div>
              <details class="mt-2">
                <summary class="cursor-pointer text-[11px] font-semibold text-cyan-200">Раскрыть все фильтры</summary>
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
            <p v-if="!threatTopChats.length" class="text-[11px] text-slate-400">Сейчас нет групп с повышенным количеством удалений.</p>
          </div>
        </div>
        </template>
      </div>

      <div v-else-if="statsType === 'deletions'" class="space-y-3">
        <template v-if="statsSubView === 'timeline'">
          <div class="rounded-2xl border border-white/10 bg-[#10141a]/95 p-4 backdrop-blur-md">
            <p class="text-[12px] font-semibold text-white">{{ isGrowthMode ? 'Динамика роста и сообщений' : 'Удаления по времени' }}</p>
            <div class="mt-3 overflow-hidden rounded-xl border border-white/[0.06] bg-[#0b0e11] px-2 py-3" @mousemove="onChartMove" @mouseleave="onChartLeave" @touchmove.prevent="onChartMove" @touchend="onChartLeave">
              <svg class="h-[150px] w-full" viewBox="0 0 320 132" preserveAspectRatio="none">
                <line x1="28" y1="114" x2="312" y2="114" stroke="rgba(148,163,184,0.15)" stroke-width="1" />
                <text v-for="(yv, yi) in yTicks" :key="`dy-${yi}`" x="2" :y="10 + yi * 34" fill="rgba(148,163,184,0.52)" font-size="9">{{ yv }}</text>
                <path v-for="r in timelineMultiSeries" :key="r.reason" :d="r.path" fill="none" :stroke="r.color" stroke-width="2.1" stroke-linecap="round" />
              </svg>
              <div class="pointer-events-none absolute right-2 top-2 rounded-lg border border-slate-600/80 bg-slate-900/95 px-2.5 py-1.5 text-[10px] text-slate-200">
                {{ hoverData.hour }}
                <div v-for="row in hoverData.rows" :key="row.label" class="flex items-center gap-1">
                  <span class="inline-block h-2 w-2 rounded-full" :style="{ backgroundColor: row.color }" />
                  <span>{{ row.label }}: {{ row.n }}</span>
                </div>
              </div>
              <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-slate-300">
                <span v-for="r in timelineMultiSeries" :key="`l-${r.reason}`" class="inline-flex items-center gap-1.5">
                  <span class="h-2 w-2 rounded-full" :style="{ backgroundColor: r.color }" />
                  {{ r.label }}
                </span>
              </div>
            </div>
          </div>
          <div class="rounded-2xl border border-white/10 bg-[#10141a]/95 p-4 backdrop-blur-md">
            <p class="mb-3 text-[12px] font-semibold text-white">{{ isGrowthMode ? 'Активность по дням' : 'Удаления по дням' }}</p>
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
            </div>
          </div>
        </template>

        <template v-else-if="statsSubView === 'hours'">
          <div class="rounded-2xl border border-white/10 bg-[#10141a]/95 p-3 backdrop-blur-md">
            <p class="mb-2 text-[12px] font-semibold text-white">{{ isGrowthMode ? 'Сообщения по часам' : 'Удаления по часам' }}</p>
            <div class="grid grid-cols-[18px_repeat(7,minmax(0,1fr))] gap-1 text-[10px]">
              <span />
              <span v-for="d in heatDayLabels" :key="`hd-${d}`" class="text-center text-slate-400">{{ d }}</span>
              <template v-for="(row, ri) in heatGrid" :key="`r-${ri}`">
                <span class="self-center text-slate-500">{{ heatRowLabels[ri] }}</span>
                <span v-for="(cell, ci) in row" :key="`c-${ri}-${ci}`" class="block h-6 rounded-[6px] border border-white/10" :style="heatCellStyle(cell)" />
              </template>
            </div>
            <div class="mt-3 flex items-center justify-between text-[10px] text-slate-400">
              <span>Меньше</span>
              <div class="mx-2 h-2 flex-1 rounded-full bg-gradient-to-r from-violet-950 to-violet-500" />
              <span>Больше</span>
            </div>
          </div>
        </template>

        <template v-else-if="statsSubView === 'weekdays'">
          <div class="rounded-2xl border border-white/10 bg-[#10141a]/95 p-4 backdrop-blur-md">
            <p class="mb-3 text-[12px] font-semibold text-white">{{ isGrowthMode ? 'Активность по дням недели' : 'Удаления по дням недели' }}</p>
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
          <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-lg">💬</div>
          <div class="min-w-0 flex-1">
            <p class="truncate text-[14px] font-semibold text-white">{{ c.title || c.id }}</p>
            <p class="text-[11px] text-slate-500">
              {{ isGrowthMode ? `Подписались: ${Number(c.joined || 0)} · Отписались: ${Number(c.left || 0)} · Сообщений: ${Number(c.messages || 0)}` : `Удалений: ${Number(c.deleted || c.moderation || 0)} · Сообщений: ${Number(c.messages || 0)}` }}
            </p>
          </div>
          <span class="shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-bold" :class="Number((isGrowthMode ? c.messages : (c.deleted || c.moderation)) || 0) > 0 ? 'border-emerald-400/40 text-emerald-200' : 'border-white/15 text-slate-400'">{{ Number((isGrowthMode ? c.messages : (c.deleted || c.moderation)) || 0) > 0 ? 'Активен' : 'Тихо' }}</span>
        </div>
        <p v-if="!connectionsRows.length" class="py-8 text-center text-[13px] text-slate-500">Нет данных за период.</p>
        <button type="button" class="w-full rounded-2xl border border-cyan-400/35 bg-cyan-500/10 py-3 text-[13px] font-semibold text-cyan-100" @click="emit('open-groups')">Показать все чаты</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useApi, messageFromApiError } from '../composables/useApi'
import { api as rawApi } from '../api/client'
import NavIcon from '../components/NavIcon.vue'
import SecurityPinGateModal from '../components/SecurityPinGateModal.vue'
import SubscriptionManagementPanel from '../components/SubscriptionManagementPanel.vue'
import { useDashboardSection } from '../composables/useDashboardSection'
import { useSecurityPinGate } from '../composables/useSecurityPinGate'
import { useToast } from '../composables/useToast'
import { shouldAskPinForAction } from '../utils/settingsSecurity'
import { formatDateTimeRu, formatDateTimeShortRu } from '../utils/formatDateTime'
import { openTelegramDeepLink } from '../utils/openTelegramDeepLink'

const router = useRouter()
const route = useRoute()
const { api, loading, error, fetchSilent, hasInitData } = useApi()
const { showToast } = useToast()
const bootError = ref('')
const { dashboardSection, setDashboardSection, billingFromGroupStats } = useDashboardSection()
const me = ref(null)
const {
  pinGateOpen,
  pinGateInput,
  pinGateError,
  pinGateBusy,
  requestPinIfNeeded,
  submitPinGate,
  cancelPinGate,
} = useSecurityPinGate(() => Number(me.value?.telegram_id || 0))
const showQuickStartModal = ref(false)
const showAccountHistoryModal = ref(false)
const historyTab = ref('payments')
const historyLoading = ref(false)
const historyLoadCompleted = ref(false)
const historyPayments = ref([])
const historyTokens = ref([])
const showReceiptModal = ref(false)
const receiptTarget = ref(null)
const receiptFullName = ref('')
const receiptEmail = ref('')
const receiptSending = ref(false)
function receiptNameKey() {
  const uid = me.value?.telegram_id || 'anon'
  return `guard_receipt_full_name_${uid}`
}
function receiptEmailKey() {
  const uid = me.value?.telegram_id || 'anon'
  return `guard_receipt_email_${uid}`
}
const promoCode = ref('')
const promoLoading = ref(false)
const showPromoCodeModal = ref(false)
const payLoadingMonths = ref(null)
/** Тестовые тарифы (отдельный API) — только при me.test_tariff_payment_visible */
const payLoadingTestMonths = ref(null)
const tokenPacks = ref([])
const tokenPacksLoading = ref(false)
const tokenPacksError = ref('')
const payLoadingTokenPack = ref(null)
const selectedTokenPack = ref(null)
const testTokenPayLoading = ref(false)
const showSubscriptionInfo = ref(false)
const showAurumHelpModal = ref(false)
const aurumHelpParagraphs = ref([])
const showTokensInfoModal = ref(false)
/** Free: экран «токены недоступны» по тапу на AURUM в быстром меню / молнии */
const showFreeAurumGateModal = ref(false)
/** Premium: витрина AURUM по тапу на кнопку «Токены» */
const showPremiumAurumShowcaseModal = ref(false)
const tokensInfoTitle = ref('')
const tokensInfoParagraphs = ref([])
const subscriptionInfoWrapRef = ref(null)
/** Якорь: выбор периода подписки (лендинг Taplink → скролл сюда) */
const billingPremiumPlansRef = ref(null)
const billingPremiumPitchRef = ref(null)
const billingPremiumCompareRef = ref(null)
const billingLandingPlansRef = ref(null)
/** Выбор на лендинге (1 / 3 / 6 / 12 мес.) — «Продолжить» */
const landingSelectedPlanMonths = ref(null)
const showAllLandingPlans = ref(false)
const showAllTokenPacks = ref(false)
/** Модалка «Способ оплаты» после выбора периода (карта ЮKassa / Stars) */
const showPremiumPayMethodModal = ref(false)
const premiumPayMethodMonths = ref(null)
const tokenPayMethodPackTokens = ref(null)
const premiumPayMethodSelected = ref('card')
const premiumPayMethodFlow = ref('main')
const premiumPayMethodProceedLoading = ref(false)
const showPaymentRedirectScreen = ref(false)
const paymentRedirectUrl = ref('')
const paymentRedirectCountdown = ref(3)
let paymentRedirectTimer = null
const waitPremiumActivationAfterPayment = ref(false)
const showPremiumActivatedModal = ref(false)
const paymentWaitBaselinePremium = ref(false)
const paymentWaitBaselineUntilTs = ref(0)
let paymentActivationPollTimer = null
let premiumActivationCheckRunning = false
let premiumActivationCheckQueued = false
const tokenBreakdownWrapRef = ref(null)
const showTokenBreakdown = ref(false)
let tokenHideTimer = null
const showFundsMovementModal = ref(false)
const fundsModalWrapRef = ref(null)
const spikeActiveShared = ref(false)
let spikeAlertTimer = null
/** Premium: мини-лендинг токенов перед выбором пакета */
const showPremiumTokenLanding = ref(false)
const premiumTokenLandingRef = ref(null)
const premiumTokenLandingTitleRef = ref(null)
const premiumTokenPacksRef = ref(null)
const tokenLandingHowItWorksRef = ref(null)
/** Низ лендинга токенов: выбор пакета (скролл с кнопки «Выбрать пакет токенов») */
const tokenLandingPackChoiceRef = ref(null)
/** Заголовок блока пакетов — якорь скролла, чтобы «Выбор пакета» был у верха экрана */
const tokenLandingPackChoiceTitleRef = ref(null)
const tokenLandingOrbitSrc = `${import.meta.env.BASE_URL}token-landing-orbit.png`
let tokenLandingOrbitPreloadImg = null

const partnerData = ref(null)
const partnerLoading = ref(false)
const partnerError = ref('')
const partnerTab = ref('balance')
const refsMode = ref('full')
const referralPeople = ref({ full_list: [], top_active: [] })
const referralPeopleLoading = ref(false)
const partnerPayouts = ref({ items: [], commissions: [], available_rub: 0, min_payout_rub: 1500, commission_total_rub: 0, pending_rub: 0, reserved_rub: 0, paid_total_rub: 0, token_rub_rate: 2 })
const partnerPayoutsLoading = ref(false)
const payoutAmountRub = ref('')
const payoutMethod = ref('sbp')
const payoutRequisites = ref('')
const payoutFullName = ref('')
const payoutSubmitting = ref(false)
const bonusTransferLoading = ref(false)
const docsExampleSale = ref(10000)
const activitySummary = ref({
  protection_active: false,
  protected_groups_count: 0,
  tariff: 'free',
  chats_count: 0,
  chats_count_total: 0,
  chat_limit: 0,
  group_limit: 0,
  channel_limit: 0,
  groups_count: 0,
  channels_count: 0,
  groups_limit: 0,
  channels_limit: 0,
  usage_progress: 0,
  groups_usage_progress: 0,
  channels_usage_progress: 0,
  today: { deleted: 0, muted: 0, banned: 0, enabled_metrics: { delete: true, mute: false, ban: false } },
  yesterday: { deleted: 0, muted: 0, banned: 0, observed: 0, joins: 0 },
})
const activityJournal = ref([])
const activityChats = ref([])
const showActivityModal = ref(false)
const activityLoading = ref(false)
const showGroupActivityModal = ref(false)
const groupActivityChatId = ref('')
const groupActivityTitle = ref('')
const groupBreakdown = ref(null)
const groupJournalItems = ref([])
const groupStatsPreset = ref('24h')
const groupStatsUseCustom = ref(false)
const groupStatsRangeExpanded = ref(false)
const groupStatsFromInput = ref('')
const groupStatsToInput = ref('')
const updatesIndex = ref(0)
/** Короткая подпись при переключении вкладок главной (без синих экранов) */
const dashSwitchBusy = ref(false)
let dashSwitchTimer = null
const showUpdatesRoadmapModal = ref(false)
/** Раскрытый текст обновления в модалке ленты (ключ slide.key) */
const updatesRoadmapExpanded = ref({})
let activityTimer = null
let updatesTimer = null
/** Счётчик запросов activitySummary: не применять устаревший ответ при гонке параллельных вызовов */
let activitySummaryFetchGen = 0
/** Время успешного ответа activity summary (для пропуска лишнего refetch при возврате на вкладку). */
let lastActivitySummaryOkAt = 0

/** Период для блока «Статистика» на главной (не путать с верхним рядом — там всегда «сегодня» из summary). */
const dashboardStatsPeriod = ref('today')
const dashboardPeriodBreakdown = ref(null)
const dashboardPeriodLoading = ref(false)
const DASHBOARD_STATS_PERIOD_OPTIONS = [
  { key: 'today', label: 'Сегодня' },
  { key: '7d', label: '7 дней' },
  { key: '14d', label: '14 дней' },
  { key: '30d', label: '30 дней' },
]

/** Компактная карточка рассылки под статистикой (те же правила, что «Рассылка» в таббаре). */
const broadcastMiniEligibleCount = ref(null)
const broadcastMiniScheduledCount = ref(null)
/** Успешные доставки (autopost) за сутки по первому посту — для «Сколько отправлено сегодня». */
const broadcastMiniSentToday = ref(null)
const broadcastMiniLoading = ref(false)
let broadcastMiniDebounceTimer = null

let statBroadcastNudgeTimer = null
const statBroadcastDragDx = ref(0)
const statBroadcastNudgePx = ref(0)
const statBroadcastDragging = ref(false)
let statBroadcastPointerId = null
let statBroadcastPointerStartX = 0
const statBroadcastJustDragged = ref(false)
let statBroadcastJustDraggedClear = null

/** Ручное переключение: «Обновления ↔ Premium», «Статистика ↔ Рассылки» */
const homeUpdatesPremiumSlide = ref(0)
const homeStatBroadcastSlide = ref(0)
const homeUpdatesPremiumInstant = ref(false)
const homeStatBroadcastInstant = ref(false)

function setUpdatesPremiumSlide(i) {
  const next = i === 1 ? 1 : 0
  const cur = homeUpdatesPremiumSlide.value
  if (next === cur) return
  if (next < cur) {
    homeUpdatesPremiumInstant.value = true
    homeUpdatesPremiumSlide.value = next
    void nextTick(() => {
      requestAnimationFrame(() => {
        homeUpdatesPremiumInstant.value = false
      })
    })
  } else {
    homeUpdatesPremiumInstant.value = false
    homeUpdatesPremiumSlide.value = next
  }
}

function stepUpdatesPremium(delta) {
  const cur = homeUpdatesPremiumSlide.value
  const n = cur + delta
  const next = n <= 0 ? 0 : n >= 1 ? 1 : n
  if (next === cur) return
  if (delta < 0) {
    homeUpdatesPremiumInstant.value = true
    homeUpdatesPremiumSlide.value = next
    void nextTick(() => {
      requestAnimationFrame(() => {
        homeUpdatesPremiumInstant.value = false
      })
    })
  } else {
    homeUpdatesPremiumInstant.value = false
    homeUpdatesPremiumSlide.value = next
  }
}

function stepStatBroadcast(delta) {
  if (!accountShowBroadcastMiniCard.value) return
  const cur = homeStatBroadcastSlide.value
  const n = cur + delta
  const next = n <= 0 ? 0 : n >= 1 ? 1 : n
  if (next === cur) return
  if (delta < 0) {
    homeStatBroadcastInstant.value = true
    homeStatBroadcastSlide.value = next
    void nextTick(() => {
      requestAnimationFrame(() => {
        homeStatBroadcastInstant.value = false
      })
    })
  } else {
    homeStatBroadcastInstant.value = false
    homeStatBroadcastSlide.value = next
  }
}

function statBroadcastTrackStyle() {
  if (!accountShowBroadcastMiniCard.value) return {}
  const slide = homeStatBroadcastSlide.value
  const drag = statBroadcastDragDx.value
  const nudge = statBroadcastNudgePx.value
  const instant = homeStatBroadcastInstant.value
  const dragging = statBroadcastDragging.value
  const extra = drag + nudge
  return {
    transform: `translateX(calc(-${slide * 50}% + ${extra}px))`,
    transition:
      dragging || instant
        ? 'none'
        : 'transform 0.45s cubic-bezier(0.22, 1, 0.36, 1)',
  }
}

function statBroadcastPointerTargetIgnoresSwipe(el) {
  if (!el || typeof el.closest !== 'function') return true
  return !!el.closest('select, [data-no-swipe], a, input, textarea, label')
}

function onStatDeletedStatClick() {
  if (statBroadcastJustDragged.value) return
  void openActivityDetails()
}

function onStatBroadcastRailPointerDown(e) {
  if (!accountShowBroadcastMiniCard.value) return
  if (statBroadcastPointerTargetIgnoresSwipe(e.target)) return
  if (e.button != null && e.button !== 0) return
  statBroadcastPointerId = e.pointerId
  statBroadcastPointerStartX = e.clientX
  statBroadcastDragDx.value = 0
  statBroadcastDragging.value = true
  try {
    e.currentTarget?.setPointerCapture?.(e.pointerId)
  } catch {
    //
  }
}

function onStatBroadcastRailPointerMove(e) {
  if (!statBroadcastDragging.value || e.pointerId !== statBroadcastPointerId) return
  const dx = e.clientX - statBroadcastPointerStartX
  statBroadcastDragDx.value = dx
  if (Math.abs(dx) > 14) {
    statBroadcastJustDragged.value = true
    if (statBroadcastJustDraggedClear) clearTimeout(statBroadcastJustDraggedClear)
    statBroadcastJustDraggedClear = setTimeout(() => {
      statBroadcastJustDraggedClear = null
      statBroadcastJustDragged.value = false
    }, 320)
  }
}

function onStatBroadcastRailPointerUp(e) {
  if (statBroadcastPointerId === null || e.pointerId !== statBroadcastPointerId) return
  try {
    e.currentTarget?.releasePointerCapture?.(e.pointerId)
  } catch {
    //
  }
  const dx = statBroadcastDragDx.value
  statBroadcastDragging.value = false
  statBroadcastPointerId = null
  statBroadcastDragDx.value = 0
  const th = 52
  const cur = homeStatBroadcastSlide.value
  if (dx < -th && cur === 0) {
    stepStatBroadcast(1)
  } else if (dx > th && cur === 1) {
    stepStatBroadcast(-1)
  }
}

function onStatBroadcastRailPointerCancel(e) {
  onStatBroadcastRailPointerUp(e)
}

function restartStatBroadcastNudge() {
  if (statBroadcastNudgeTimer) {
    clearInterval(statBroadcastNudgeTimer)
    statBroadcastNudgeTimer = null
  }
  if (dashboardSection.value !== 'account' || !accountShowBroadcastMiniCard.value) return
  statBroadcastNudgeTimer = setInterval(() => {
    if (homeStatBroadcastSlide.value !== 0) return
    if (statBroadcastDragging.value) return
    statBroadcastNudgePx.value = -11
    setTimeout(() => {
      statBroadcastNudgePx.value = 0
    }, 380)
  }, 3000)
}

const currentUpdateSlide = computed(() => UPDATES_SLIDES[updatesIndex.value] || UPDATES_SLIDES[0])

function restartUpdatesRotation() {
  if (updatesTimer) {
    clearInterval(updatesTimer)
    updatesTimer = null
  }
  if (dashboardSection.value !== 'account') return
  updatesTimer = setInterval(() => {
    updatesIndex.value = (updatesIndex.value + 1) % UPDATES_SLIDES.length
  }, 4000)
}

function selectUpdatesSlide(i) {
  const n = UPDATES_SLIDES.length
  if (i < 0 || i >= n) return
  updatesIndex.value = i
  restartUpdatesRotation()
}

function applyUpdatePrimaryAction() {
  const slide = currentUpdateSlide.value
  const a = slide?.primaryAction
  if (!a) return
  if (a === 'partner') setDashboardSection('partner')
  if (a === 'protection') router.push('/protection')
}

function normalizeAction(action) {
  const a = String(action || '').toLowerCase()
  if (a.includes('observe') || a.includes('замеч')) return 'observe'
  if (a.includes('ban')) return 'ban'
  if (a.includes('mute') || a.includes('restrict')) return 'mute'
  return 'delete'
}

function actionLabelRu(action) {
  const key = normalizeAction(action)
  if (key === 'ban') return 'Блокировка'
  if (key === 'mute') return 'Ограничение'
  if (key === 'observe') return 'Замечено (без удаления)'
  return 'Удаление'
}

/** Человекочитаемая причина срабатывания фильтра (ключи из moderation_logs.reason). */
function moderationReasonRu(reason) {
  const raw = String(reason || '').trim().toLowerCase()
  if (!raw) return '—'
  const base = raw.replace(/_newbie$/i, '')
  const map = {
    link: 'Ссылки',
    media: 'Медиа / стикеры',
    buttons: 'Сообщения с кнопками',
    mention: 'Упоминания',
    stopword: 'Стоп-слова',
    profanity: 'Мат',
    jobs: 'Подработки',
    casino: 'Казино / ставки',
    politics: 'Анти-политика',
    silence: 'Режим тишины',
    antinakrutka: 'Анти-накрутка',
    captcha: 'Капча',
    flood: 'Флуд',
    global_antispam: 'Глобальная база',
    raid: 'Рейд',
    spam: 'Спам',
    forward: 'Репосты',
  }
  if (map[raw]) return map[raw]
  if (map[base]) return raw.endsWith('_newbie') ? `${map[base]} (новички)` : map[base]
  if (base.includes('profanity')) return 'Мат'
  if (base.includes('stopword')) return 'Стоп-слова'
  if (base.includes('newbie')) return 'Новички'
  return raw.replace(/_/g, ' ')
}

function journalDisplayTime(iso) {
  return formatDateTimeShortRu(iso)
}

/** @param {{ username?: string | null, user_id?: number }} item */
function violatorLabel(item) {
  const u = String(item?.username || '').trim().replace(/^@+/, '')
  if (u) return `@${u}`
  const id = Number(item?.user_id || 0)
  return id ? `ID ${id}` : '—'
}

function openViolatorProfile(item) {
  const u = String(item?.username || '').trim().replace(/^@+/, '')
  const uid = Number(item?.user_id || 0)
  if (u) {
    const url = `https://t.me/${encodeURIComponent(u)}`
    openTelegramDeepLink(url)
    return
  }
  if (uid) {
    const url = `https://t.me/user?id=${uid}`
    openTelegramDeepLink(url)
  }
}

/** Одна строка: тип нарушения + конкретный триггер (слово, ссылка…). */
function journalTriggerDescription(item) {
  const cat = moderationReasonRu(item.reason)
  const d = String(item?.detail || '').trim()
  if (d) return `${cat}: «${d}»`
  const mp = String(item?.message_preview || '').trim().replace(/\s+/g, ' ')
  if (mp) {
    const snip = mp.length > 140 ? `${mp.slice(0, 140)}…` : mp
    return `${cat} · фрагмент: «${snip}»`
  }
  return cat
}

const modPrivilegeBusyKey = ref('')
/** Строка журнала: после успешного размута/разбана показываем галочку вместо кнопки */
const modUnmuteDone = ref(/** @type {Record<string, boolean>} */ ({}))
const modUnbanDone = ref(/** @type {Record<string, boolean>} */ ({}))

watch(showGroupActivityModal, (open) => {
  if (!open) {
    modUnmuteDone.value = {}
    modUnbanDone.value = {}
  }
})

function journalEventKey(item) {
  return `${String(item?.created_at || '')}|${Number(item?.user_id || 0)}|${String(item?.action || '')}`
}

async function postChatMemberPrivilege(kind, chatId, userId, rowKey) {
  const cid = Number(chatId || 0)
  const uid = Number(userId || 0)
  if (!cid || !uid) return
  const key = `${kind}-${cid}-${uid}`
  modPrivilegeBusyKey.value = key
  try {
    if (kind === 'unban') await rawApi.chatMemberUnban(cid, uid)
    else await rawApi.chatMemberUnmute(cid, uid)
    if (rowKey) {
      if (kind === 'unban') modUnbanDone.value = { ...modUnbanDone.value, [rowKey]: true }
      else modUnmuteDone.value = { ...modUnmuteDone.value, [rowKey]: true }
    }
    showToast(kind === 'unban' ? 'Разбан выполнен в Telegram' : 'Размут выполнен в Telegram')
    await loadGroupActivityFull()
  } catch (e) {
    const d = e?.body?.detail || e?.message || 'Не удалось выполнить действие'
    showToast(String(d))
  } finally {
    modPrivilegeBusyKey.value = ''
  }
}

const activityOverview = computed(() => {
  const out = { total: 0, deleted: 0, muted: 0, banned: 0, observed: 0 }
  for (const item of activityJournal.value || []) {
    out.total += 1
    const key = normalizeAction(item?.action)
    if (key === 'ban') out.banned += 1
    else if (key === 'mute') out.muted += 1
    else if (key === 'observe') out.observed += 1
    else out.deleted += 1
  }
  return out
})

const activityByGroup = computed(() => {
  const map = new Map((activityChats.value || []).map((c) => [Number(c.id || 0), {
    chat_id: Number(c.id || 0),
    chat_title: String(c.title || c.id || 'Группа'),
    total: 0,
    deleted: 0,
    muted: 0,
    banned: 0,
    observed: 0,
  }]))
  for (const item of activityJournal.value || []) {
    const chatId = Number(item?.chat_id || 0)
    const title = String(item?.chat_title || chatId || 'Группа')
    if (!map.has(chatId)) {
      map.set(chatId, { chat_id: chatId, chat_title: title, total: 0, deleted: 0, muted: 0, banned: 0, observed: 0 })
    }
    const row = map.get(chatId)
    row.total += 1
    const key = normalizeAction(item?.action)
    if (key === 'ban') row.banned += 1
    else if (key === 'mute') row.muted += 1
    else if (key === 'observe') row.observed += 1
    else row.deleted += 1
  }
  return Array.from(map.values()).sort((a, b) => b.total - a.total)
})

function activityChatIsShared(chatId) {
  const cid = Number(chatId || 0)
  const row = (activityChats.value || []).find((c) => Number(c.id) === cid)
  return !!row?.is_shared
}

const activityByGroupDelegated = computed(() =>
  (activityByGroup.value || []).filter((g) => activityChatIsShared(g.chat_id)),
)
const activityByGroupMine = computed(() =>
  (activityByGroup.value || []).filter((g) => !activityChatIsShared(g.chat_id)),
)

const groupBreakdownBuckets = computed(() => groupBreakdown.value?.buckets || [])
const breakdownUserPremium = computed(() => !!groupBreakdown.value?.is_premium)
const groupPeriodLabel = computed(() => {
  const b = groupBreakdown.value
  if (b?.period_from && b?.period_to) {
    return `${formatDateTimeShortRu(b.period_from)} — ${formatDateTimeShortRu(b.period_to)}`
  }
  return 'Период'
})

/** Все события журнала по выбранной группе и периоду (удаление / мут / бан). */
const groupJournalForModal = computed(() => {
  const cid = Number(groupActivityChatId.value || 0)
  if (!cid) return []
  return (groupJournalItems.value || []).filter((item) => Number(item?.chat_id || 0) === cid)
})

function filterStatCardTone(tone) {
  const t = String(tone || 'emerald')
  if (t === 'rose') {
    return 'border-rose-500/70 bg-rose-950/35'
  }
  if (t === 'amber') {
    return 'border-amber-500/70 bg-amber-950/30'
  }
  if (t === 'violet') {
    return 'border-violet-500/70 bg-violet-950/30'
  }
  if (t === 'slate') {
    return 'border-slate-500/70 bg-slate-900/50'
  }
  return 'border-emerald-400/80 bg-emerald-950/35'
}

const totalTokens = computed(() => {
  const total = Number(me.value?.aurum_tokens || 0) + Number(me.value?.partner_tokens || 0)
  return String(Math.max(0, Math.round(total)))
})
const tariffIsPremium = computed(() => ['premium', 'pro', 'business'].includes((me.value?.tariff || 'free').toLowerCase()))
/** Карточка «Рассылки» на главной: показываем всем авторизованным (маркетинг); доступ по-прежнему через Premium/делегирование. */
const accountShowBroadcastMiniCard = computed(() => !!me.value)
const dashboardAvatarSrc = computed(() => {
  const base = import.meta.env.BASE_URL
  return tariffIsPremium.value ? `${base}premium-guard-emblem.png` : `${base}avatar-free.png`
})
/** Уникальные id для SVG-градиентов статуса защиты */
const protCheckGradId = `prot-ok-${Math.random().toString(36).slice(2, 11)}`
const protOffGradId = `prot-off-${Math.random().toString(36).slice(2, 11)}`
const activityChatsCount = computed(() => Number(activitySummary.value?.chats_count || 0))
/** Группы с включённым Guard (не каналы, не на паузе) — строка «Защищено сегодня». */
const activityProtectedGroupsCount = computed(() =>
  Math.max(0, Math.round(Number(activitySummary.value?.protected_groups_count ?? 0))),
)
const activityGroupsCount = computed(() => Number((activitySummary.value?.groups_count ?? activitySummary.value?.chats_count) || 0))
const activityChannelsCount = computed(() => Number(activitySummary.value?.channels_count || 0))
const activityGroupsLimit = computed(() => Number((activitySummary.value?.groups_limit ?? activitySummary.value?.group_limit ?? activitySummary.value?.chat_limit) || 0))
const activityChannelsLimit = computed(() => Number((activitySummary.value?.channels_limit ?? activitySummary.value?.channel_limit) || 0))
const activityGroupsProgress = computed(() => Number((activitySummary.value?.groups_usage_progress ?? activitySummary.value?.usage_progress) || 0))
const activityChannelsProgress = computed(() => Number(activitySummary.value?.channels_usage_progress || 0))
/** Есть подключённые группы и защита включена */
const protectionStatusOk = computed(() => !!activitySummary.value?.protection_active)
/** Нет подключённых чатов в сводке — отдельное состояние UI */
const protectionStatusNoChats = computed(() => activityChatsCount.value === 0)

/** Оценка «сэкономлено админам» (₽): ~25 ₽ на обработанное удаление за сегодня (ориентир времени модератора). */
const dashboardEstimatedSavedRub = computed(() => {
  const d = Math.max(0, Math.round(Number(activitySummary.value?.today?.deleted || 0)))
  return d * 25
})

/**
 * Уровень защиты: 1–4 сегмента и цвет (красный → оранжевый → жёлтый → зелёный).
 * Считаем балл 0–100 из факторов: тариф, protection_active, число защищённых групп
 * (без каналов, без паузы), удаления за сутки, загрузка лимита групп.
 */
const dashboardProtectionLevelMeta = computed(() => {
  const empty = {
    segments: 0,
    score: 0,
    label: '—',
    labelClass: 'text-white/45',
    fillSegmentClass: '',
  }
  const n = activityProtectedGroupsCount.value
  if (n <= 0) return empty

  const del = Math.max(0, Math.round(Number(activitySummary.value?.today?.deleted || 0)))
  const t = String(activitySummary.value?.tariff || 'free').toLowerCase()
  const premium = ['premium', 'pro', 'business'].includes(t)
  const protOn = !!activitySummary.value?.protection_active
  const usage = Math.max(0, Math.min(100, activityGroupsProgress.value))

  let score = 0
  score += premium ? 22 : 10
  score += protOn ? 38 : 8
  score += Math.min(18, Math.round(n * 3))
  score += Math.min(14, Math.round(del * 0.35))
  score += Math.min(8, Math.round(usage / 12))

  const s = Math.max(0, Math.min(100, Math.round(score)))

  let segments = 1
  if (s >= 72) segments = 4
  else if (s >= 48) segments = 3
  else if (s >= 24) segments = 2

  const tiers = {
    1: {
      label: 'Слабый',
      fillSegmentClass: 'bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.35)]',
      labelClass: 'text-rose-400',
    },
    2: {
      label: 'Базовый',
      fillSegmentClass: 'bg-orange-500 shadow-[0_0_6px_rgba(249,115,22,0.32)]',
      labelClass: 'text-orange-400',
    },
    3: {
      label: 'Средний',
      fillSegmentClass: 'bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.38)]',
      labelClass: 'text-amber-300',
    },
    4: {
      label: 'Сильный',
      fillSegmentClass: 'bg-lime-400 shadow-[0_0_6px_rgba(163,230,53,0.38)]',
      labelClass: 'text-lime-400',
    },
  }

  const meta = tiers[segments]
  return {
    segments,
    score: s,
    label: meta.label,
    labelClass: meta.labelClass,
    fillSegmentClass: meta.fillSegmentClass,
  }
})

/** Оценка часов, сэкономленных админам (25 ₽/удаление, ориентир 1500 ₽/ч модератора). */
const dashboardSavedHoursLabel = computed(() => {
  const d = Math.max(0, Math.round(Number(activitySummary.value?.today?.deleted || 0)))
  if (d === 0) return '0 ч'
  const hours = (d * 25) / 1500
  if (hours < 0.05) return '< 0,1 ч'
  return `${hours.toFixed(1).replace('.', ',')} ч`
})

/** Тренд «к вчера» для счётчиков (процент или текст). */
function statTrendPctLine(todayVal, yesterdayVal) {
  const t = Math.max(0, Math.round(Number(todayVal) || 0))
  const y = Math.max(0, Math.round(Number(yesterdayVal) || 0))
  if (t === 0 && y === 0) return 'нет данных'
  if (y === 0) return t > 0 ? 'вчера было 0' : 'как вчера'
  const pct = Math.round(((t - y) / y) * 100)
  const sign = pct > 0 ? '+' : ''
  return `${sign}${pct}% к вчера`
}

const statTrendDeleted = computed(() =>
  statTrendPctLine(activitySummary.value?.today?.deleted, activitySummary.value?.yesterday?.deleted),
)
const statTrendSaved = computed(() =>
  statTrendPctLine(activitySummary.value?.today?.deleted, activitySummary.value?.yesterday?.deleted),
)
const statTrendJoins = computed(() => {
  const t = Math.max(0, Math.round(Number(activitySummary.value?.today?.joins ?? 0)))
  const y = Math.max(0, Math.round(Number(activitySummary.value?.yesterday?.joins ?? 0)))
  if (t === 0 && y === 0) return 'нет вступлений'
  const diff = t - y
  if (diff === 0) return 'как вчера'
  if (diff > 0) return `+${diff} к вчера`
  return `${diff} к вчера`
})

const statsCardUsesPeriod = computed(() => dashboardStatsPeriod.value !== 'today')
const statsCardDeleted = computed(() => {
  if (!statsCardUsesPeriod.value) {
    return Math.max(0, Math.round(Number(activitySummary.value?.today?.deleted ?? 0)))
  }
  return Math.max(0, Math.round(Number(dashboardPeriodBreakdown.value?.total_deleted ?? 0)))
})
const statsCardJoins = computed(() => {
  if (!statsCardUsesPeriod.value) {
    return Math.max(0, Math.round(Number(activitySummary.value?.today?.joins ?? 0)))
  }
  return Math.max(0, Math.round(Number(dashboardPeriodBreakdown.value?.total_joined ?? 0)))
})
const statsCardSavedHoursLabel = computed(() => {
  const d = statsCardDeleted.value
  if (d === 0) return '0 ч'
  const hours = (d * 25) / 1500
  if (hours < 0.05) return '< 0,1 ч'
  return `${hours.toFixed(1).replace('.', ',')} ч`
})
const statsCardTrendDeleted = computed(() => {
  if (statsCardUsesPeriod.value) {
    const p = DASHBOARD_STATS_PERIOD_OPTIONS.find((x) => x.key === dashboardStatsPeriod.value)
    return p ? `за ${p.label.toLowerCase()}` : 'за период'
  }
  return statTrendDeleted.value
})
const statsCardTrendSaved = computed(() => {
  if (statsCardUsesPeriod.value) {
    const p = DASHBOARD_STATS_PERIOD_OPTIONS.find((x) => x.key === dashboardStatsPeriod.value)
    return p ? `за ${p.label.toLowerCase()}` : 'за период'
  }
  return statTrendSaved.value
})
const statsCardTrendJoins = computed(() => {
  if (statsCardUsesPeriod.value) {
    return statsCardJoins.value > 0 ? `всего: ${statsCardJoins.value}` : 'нет вступлений'
  }
  return statTrendJoins.value
})

/** Доля занятых слотов групп по тарифу (вместо «точность AI»). */
const statGroupsLimitPercent = computed(() => {
  const p = Number(activityGroupsProgress.value || 0)
  if (!Number.isFinite(p)) return '—'
  return `${Math.max(0, Math.min(100, Math.round(p)))}%`
})

const statGroupsLimitFoot = computed(() => {
  const left = Math.max(0, Math.round(Number(activityGroupsLimit.value || 0) - Number(activityGroupsCount.value || 0)))
  if (Number(activityGroupsLimit.value || 0) <= 0) return 'тариф'
  if (left === 0) return 'лимит'
  if (left <= 3) return 'мало слотов'
  return 'в норме'
})

function fmtRubInt(n) {
  const v = Math.max(0, Math.round(Number(n) || 0))
  try {
    return v.toLocaleString('ru-RU')
  } catch {
    return String(v)
  }
}

function ruChatsCountLabel(count) {
  const n = Math.abs(Math.trunc(Number(count) || 0))
  const k = n % 100
  const l = n % 10
  if (k > 10 && k < 20) return `${n} чатов`
  if (l === 1) return `${n} чат`
  if (l >= 2 && l <= 4) return `${n} чата`
  return `${n} чатов`
}

function ruGroupsProtectedLabel(count) {
  const n = Math.abs(Math.trunc(Number(count) || 0))
  const k = n % 100
  const l = n % 10
  if (k > 10 && k < 20) return `${n} групп`
  if (l === 1) return `${n} группа`
  if (l >= 2 && l <= 4) return `${n} группы`
  return `${n} групп`
}

function goManageChats() {
  router.push({ path: '/chats' })
}

function goAccountHistory() {
  showAccountHistoryModal.value = true
  void loadHistoryIfNeeded()
}

function formatUpdateMetaShort(s) {
  const v = String(s?.version || '1').trim()
  try {
    const iso = s?.publishedAt
    if (!iso) return `v${v}`
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return `v${v}`
    const dayMonth = d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
    const time = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    return `v${v} · ${dayMonth} · ${time}`
  } catch {
    return `v${v}`
  }
}

function formatUpdateMetaLong(s) {
  const v = String(s?.version || '1').trim()
  try {
    const iso = s?.publishedAt
    if (!iso) return `v${v}`
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return `v${v}`
    const dateStr = d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
    const timeStr = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    return `v${v} · ${dateStr} · ${timeStr}`
  } catch {
    return `v${v}`
  }
}

function toggleUpdatesRoadmapExpand(key) {
  const k = String(key || '')
  updatesRoadmapExpanded.value = {
    ...updatesRoadmapExpanded.value,
    [k]: !updatesRoadmapExpanded.value[k],
  }
}

watch(showUpdatesRoadmapModal, (open) => {
  if (!open) updatesRoadmapExpanded.value = {}
})

const ACCOUNT_HOME_PREMIUM_BULLETS = [
  'AI-фильтр нового поколения',
  'Автобан и анти-рейды',
  'Приоритетная поддержка',
  'Расширенная статистика',
]

/** Лента обновлений: от новых к более ранним; на главной — только первые UPDATES_HOME_PREVIEW_N */
const UPDATES_HOME_PREVIEW_N = 3

const UPDATES_SLIDES = [
  {
    key: 'stats_growth',
    version: '2.4',
    publishedAt: '2026-05-06T15:30:00+03:00',
    headline: 'Статистика защиты и роста',
    teaser:
      'Один экран: удаления по фильтрам, динамика, подписки и сообщения — без прыжков по разделам.',
    body: 'Мы переработали блок статистики в Premium-кабинете: видно, что сработало в защите, как растёт аудитория и какие чаты самые активные. Это экономит время модераторам: не нужно собирать картину по кускам — всё рядом и обновляется автоматически.',
    primaryLabel: null,
    primaryAction: null,
    imageUrl: null,
  },
  {
    key: 'filters_wave',
    version: '2.3',
    publishedAt: '2026-05-05T18:00:00+03:00',
    headline: 'Новые фильтры и точнее триггеры',
    teaser: 'Казино, ссылки, медиа и «глобальные» правила — меньше шума, больше контроля.',
    body: 'Добавлены и уточнены фильтры под реальные сценарии: ставки и казино, подозрительные URL, медиа и жёсткие словари. Настройки стали понятнее: проще включить нужное и не ловить ложные срабатывания.',
    primaryLabel: null,
    primaryAction: null,
    imageUrl: null,
  },
  {
    key: 'launch_public',
    version: '2.2',
    publishedAt: '2026-05-04T12:00:00+03:00',
    headline: 'Запуск AntiSpam Guard',
    teaser: 'Мы вышли в прод: защита групп и каналов, статистика и регулярные улучшения по дорожной карте.',
    body: 'Официальный запуск сервиса для администраторов Telegram. Вы можете подключать чаты, настраивать защиту, смотреть статистику и получать обновления без простоя. Мы на связи и продолжаем усиливать продукт после старта.',
    primaryLabel: null,
    primaryAction: null,
    imageUrl: null,
  },
  {
    key: 'earn',
    version: '2.1',
    publishedAt: '2026-05-03T11:00:00+03:00',
    headline: 'Заработок с Guard',
    teaser: 'Приглашайте пользователей — получайте токены за их оплаты.',
    body: 'Реферальная программа помогает монетизировать аудиторию: вы делитесь ссылкой, подписчики оформляют Premium или пополняют баланс — вам начисляются токены. Меньше ручной работы, прозрачнее мотивация развивать сообщество.',
    primaryLabel: 'Заработать',
    primaryAction: 'partner',
    imageUrl: null,
  },
  {
    key: 'casino',
    version: '2.0',
    publishedAt: '2026-05-02T09:30:00+03:00',
    headline: 'Фильтр казино и ставок',
    teaser: 'Убираем ставки, казино-спам и навязчивые рассылки до того, как они испортят чат.',
    body: 'Добавлен отдельный контур правил для ставок и казино: меньше флуда, чище лента. Проверьте профиль фильтров в защите чата — можно включить под ваш стиль общения.',
    primaryLabel: 'Посмотреть',
    primaryAction: 'protection',
    imageUrl: null,
  },
  {
    key: 'premium_cabinet',
    version: '1.9',
    publishedAt: '2026-05-01T14:15:00+03:00',
    headline: 'Premium-кабинет в одном стиле',
    teaser: 'Синий ADM: защита, статистика роста, рассылки — без устаревших экранов.',
    body: 'Обновили навигацию и визуал кабинета: меньше отвлекающих рамок, больше воздуха и понятных действий. Удобнее вести несколько чатов и следить за состоянием защиты.',
    primaryLabel: null,
    primaryAction: null,
    imageUrl: null,
  },
  {
    key: 'ai',
    version: '1.8',
    publishedAt: '2026-04-28T10:00:00+03:00',
    headline: 'Скоро: ИИ-помощник модерации',
    teaser: 'Умные подсказки и авторазбор спорных сообщений — в разработке.',
    body: 'Готовим модель, которая поможет администраторам быстрее принимать решения: контекст, риск и рекомендации по настройке антиспама. Следите за лентой — выпустим отдельным релизом.',
    primaryLabel: null,
    primaryAction: null,
    imageUrl: null,
  },
]

const updatesHomePreview = computed(() => UPDATES_SLIDES.slice(0, UPDATES_HOME_PREVIEW_N))

const GROUP_STATS_PRESETS = [
  { key: '24h', label: '24 ч' },
  { key: '7d', label: '7 дн.' },
  { key: '30d', label: '30 дн.' },
  { key: '6m', label: 'Полгода' },
  { key: '1y', label: 'Год' },
]
/** Подарок AURUM с Premium: сумма ₽ / 4 ✨ (в 2 раза меньше старого «₽/2»). */
const SUBSCRIPTION_GIFT_RUB_PER_AURUM = 4

const PREMIUM_PLANS = [
  { months: 1, icon: '🛡', label: '1 месяц', price: '490 ₽', priceRub: 490, savings: '' },
  { months: 3, icon: '⚡', label: '3 месяца', price: '990 ₽', priceRub: 990, savings: 'Экономия 480 ₽' },
  { months: 6, icon: '📅', label: '6 месяцев', price: '1590 ₽', priceRub: 1590, savings: 'Экономия 1350 ₽' },
  { months: 12, icon: '👑', label: '12 месяцев', price: '2790 ₽', priceRub: 2790, savings: 'Экономия 3090 ₽' },
  { months: 24, icon: '💎', label: '24 месяца', price: '4790 ₽', priceRub: 4790, savings: 'Экономия 6970 ₽' },
  { months: 72, icon: '🚀', label: '72 месяца', price: '10 990 ₽', priceRub: 10990, savings: 'Экономия 24 290 ₽' },
]

const premiumPayMethodSummary = computed(() => {
  if (premiumPayMethodFlow.value === 'tokens') {
    const tokens = Number(tokenPayMethodPackTokens.value || 0)
    if (!tokens) return ''
    const pack = (tokenPacks.value || []).find((p) => Number(p.tokens) === tokens)
    const price = Math.round(Number(pack?.price_rub || 0))
    return price > 0 ? `${tokens} ⚡ · ${price} ₽` : `${tokens} ⚡`
  }
  const m = premiumPayMethodMonths.value
  if (!m) return ''
  const p = PREMIUM_PLANS.find((x) => x.months === m)
  return p ? `${p.label} · ${p.price}` : ''
})

/**
 * Лендинг «Free vs Premium»: сверху рефералка и фильтр ссылок/упоминаний (во Free тоже ✓),
 * затем остальное; внизу лимит чатов. Premium в рефералке: «3 уровня» зелёным.
 */
const billingCompareRows = [
  { id: 'referral', kind: 'referral', label: 'Реферальная программа' },
  { id: 'links_mentions', kind: 'ok', label: 'Фильтр ссылок и упоминаний', free: 'ok', premium: 'ok' },
  { id: 'panel', kind: 'ok', label: 'Панель в Telegram, базовая работа', free: 'ok', premium: 'ok' },
  { id: 'spam', kind: 'ok', label: 'Расширенная защита от спама', free: 'no', premium: 'ok' },
  { id: 'autodel', kind: 'ok', label: 'Автоудаление', free: 'no', premium: 'ok' },
  { id: 'bcast', kind: 'ok', label: 'Рассылки', free: 'no', premium: 'ok' },
  { id: 'autopost', kind: 'ok', label: 'Автопостинг', free: 'no', premium: 'ok' },
  { id: 'stats', kind: 'ok', label: 'Расширенная статистика', free: 'no', premium: 'ok' },
  { id: 'reports_track', kind: 'ok', label: 'Отслеживание отчетов', free: 'no', premium: 'ok' },
  { id: 'support', kind: 'ok', label: 'Приоритетная поддержка', free: 'no', premium: 'ok' },
  { id: 'chat_limit', kind: 'limits', label: 'Макс. каналов / групп' },
]

const LANDING_PLAN_UI = [
  { months: 1 },
  { months: 3 },
  { months: 6 },
  { months: 12, tag: 'Популярно' },
]

const landingPlanShowcase = computed(() =>
  LANDING_PLAN_UI.map((ui) => {
    const plan = PREMIUM_PLANS.find((p) => p.months === ui.months)
    if (!plan) return null
    const discountLabel =
      Number(plan.months) === 1 ? '' : premiumSavingsCornerBadge(plan)
    return { ...plan, discountLabel, tag: ui.tag || '' }
  }).filter(Boolean),
)

const landingPlanCards = computed(() => {
  const base = landingPlanShowcase.value
  if (!showAllLandingPlans.value) return base
  const featuredMonths = new Set(base.map((x) => Number(x.months)))
  const extra = PREMIUM_PLANS.filter((p) => !featuredMonths.has(Number(p.months))).map((p) => ({
    ...p,
    discountLabel: premiumSavingsCornerBadge(p),
    tag: Number(p.months) === 24 ? 'Выгодно' : '',
  }))
  return [...base, ...extra]
})

const hasHiddenTokenPacks = computed(() => (tokenPacks.value || []).some((p) => p.extra))
const displayedTokenPacks = computed(() => {
  const all = tokenPacks.value || []
  if (!all.length) return all
  if (!all.some((p) => p.extra)) return all
  if (showAllTokenPacks.value) return all
  return all.filter((p) => !p.extra)
})

function subscriptionTokensForPlan(plan) {
  const rub = Number(plan?.priceRub ?? 0)
  if (!rub) return 0
  return Math.round(rub / SUBSCRIPTION_GIFT_RUB_PER_AURUM)
}

/** Короткая подпись для угла карточки: из «Экономия 480 ₽» → «−480 ₽» */
function premiumSavingsCornerBadge(plan) {
  const s = String(plan?.savings || '').trim()
  if (!s) return ''
  const m = s.match(/Экономия\s+([\d\s\u00a0]+)\s*₽/i)
  if (!m) return ''
  const num = m[1].replace(/[\s\u00a0]+/g, ' ').trim()
  if (!num) return ''
  return `−${num} ₽`
}
function applyMeState(nextMe) {
  const wasPremium = !!me.value?.is_premium
  const prevUntilTs = Date.parse(String(me.value?.subscription_until || '')) || 0
  me.value = nextMe || null
  const nowPremium = !!me.value?.is_premium
  const nowUntilTs = Date.parse(String(me.value?.subscription_until || '')) || 0
  if (waitPremiumActivationAfterPayment.value && nowPremium) {
    const becamePremium = !paymentWaitBaselinePremium.value && nowPremium
    const prolongedFromBaseline = paymentWaitBaselinePremium.value && nowUntilTs > paymentWaitBaselineUntilTs.value
    const prolongedFromPrev = wasPremium && nowUntilTs > prevUntilTs
    if (becamePremium || prolongedFromBaseline || prolongedFromPrev) {
      waitPremiumActivationAfterPayment.value = false
      stopPaymentActivationFastPolling()
      showPremiumActivatedModal.value = true
    }
  }
}

function schedulePremiumActivationCheck() {
  if (!waitPremiumActivationAfterPayment.value) return
  premiumActivationCheckQueued = true
  void runPremiumActivationCheckLoop()
}

async function runPremiumActivationCheckLoop() {
  if (premiumActivationCheckRunning) return
  premiumActivationCheckRunning = true
  try {
    while (premiumActivationCheckQueued && waitPremiumActivationAfterPayment.value) {
      premiumActivationCheckQueued = false
      try {
        await fetchSilent(() => api.yookassaReconcilePending())
        const fresh = await fetchSilent(() => rawApi.me())
        applyMeState(fresh)
      } catch {
        //
      }
    }
  } finally {
    premiumActivationCheckRunning = false
  }
}

function startPaymentActivationFastPolling() {
  if (paymentActivationPollTimer || typeof window === 'undefined') return
  schedulePremiumActivationCheck()
  paymentActivationPollTimer = setInterval(() => {
    if (!waitPremiumActivationAfterPayment.value) return
    if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
    schedulePremiumActivationCheck()
  }, 250)
}

function stopPaymentActivationFastPolling() {
  if (!paymentActivationPollTimer) return
  clearInterval(paymentActivationPollTimer)
  paymentActivationPollTimer = null
  premiumActivationCheckQueued = false
}

function updateBodyScrollLock() {
  if (typeof document === 'undefined') return
  const lock = !!(
    showPromoCodeModal.value ||
    showPremiumPayMethodModal.value ||
    showPaymentRedirectScreen.value ||
    showPremiumActivatedModal.value ||
    showFreeAurumGateModal.value ||
    showPremiumAurumShowcaseModal.value ||
    showUpdatesRoadmapModal.value
  )
  const body = document.body
  const html = document.documentElement
  if (!body || !html) return
  body.style.overflow = lock ? 'hidden' : ''
  html.style.overflow = lock ? 'hidden' : ''
}

async function loadMeInitial() {
  if (!hasInitData.value) return
  bootError.value = ''
  error.value = null
  loading.value = true
  const actGen = ++activitySummaryFetchGen
  try {
    const [meRes, actRes] = await Promise.allSettled([rawApi.me(), rawApi.activitySummary()])
    if (meRes.status === 'fulfilled') {
      applyMeState(meRes.value)
    } else {
      me.value = null
      const e = meRes.reason
      const d = String(e?.body?.detail || e?.message || '').trim()
      bootError.value =
        d && !/^load failed$/i.test(d)
          ? d
          : 'Не удалось загрузить профиль. Проверьте интернет или задеплойте API (сервис zealous-bravery).'
    }
    if (actRes.status === 'fulfilled' && actGen === activitySummaryFetchGen) {
      activitySummary.value = actRes.value
      lastActivitySummaryOkAt = Date.now()
    }
  } finally {
    loading.value = false
  }
}

async function loadSpikeAlertsState() {
  try {
    const data = await rawApi.spikeAlerts()
    spikeActiveShared.value = !!data?.active_shared
  } catch {
    spikeActiveShared.value = false
  }
}

function openSharedThreatChats() {
  router.push({ path: '/chats', query: { cabinet: 'delegated', threat: '1' } })
}

onMounted(async () => {
  await Promise.all([loadMeInitial(), loadSpikeAlertsState()])
  if (typeof window !== 'undefined' && 'requestIdleCallback' in window) {
    window.requestIdleCallback(() => preloadTokenLandingOrbit(), { timeout: 2500 })
  } else {
    setTimeout(() => preloadTokenLandingOrbit(), 1800)
  }
  if (!dashboardSection.value) setDashboardSection('account')
  if (dashboardSection.value === 'partner') {
    await ensurePartnerData()
    await ensureReferralPeople()
    await ensurePartnerPayouts()
  }
  // Открыть модалку «Подробный отчёт по защите» из ?report=1
  // (фиолетовый ADM → кнопка «Отчёты»).
  if (String(route.query?.report || '') === '1') {
    try { await openActivityDetails() } catch { /* */ }
    try {
      const q = { ...route.query }
      delete q.report
      router.replace({ path: route.path, query: q }).catch(() => {})
    } catch { /* */ }
  }
  // Открыть модалку «Токены AURUM» из ?topup=1
  // (синий ADM → «+ Пополнить» в настройках/состоянии подписки).
  if (String(route.query?.topup || '') === '1') {
    try {
      if (tariffIsPremium.value) showPremiumAurumShowcaseModal.value = true
      else showFreeAurumGateModal.value = true
    } catch { /* */ }
    try {
      const q = { ...route.query }
      delete q.topup
      router.replace({ path: route.path, query: q }).catch(() => {})
    } catch { /* */ }
  }
  if (String(route.query?.updates || '') === '1') {
    showUpdatesRoadmapModal.value = true
    try {
      const q = { ...route.query }
      delete q.updates
      router.replace({ path: route.path, query: q }).catch(() => {})
    } catch {
      //
    }
  }
  try {
    const savedName = localStorage.getItem(receiptNameKey()) || ''
    const savedEmail = localStorage.getItem(receiptEmailKey()) || ''
    receiptFullName.value = savedName
    receiptEmail.value = savedEmail
  } catch {
    //
  }
  document.addEventListener('pointerdown', onGlobalPointerDown, true)
  startActivityAutoRefresh()
  restartUpdatesRotation()
  restartStatBroadcastNudge()
  if (spikeAlertTimer) clearInterval(spikeAlertTimer)
  spikeAlertTimer = setInterval(loadSpikeAlertsState, 30000)
  await tryOpenProtectionReportFromRoute()
  document.addEventListener('visibilitychange', onVisibilityPaymentCheck)
  if (typeof window !== 'undefined') {
    window.addEventListener('focus', onWindowFocusPremiumCheck)
  }
  updateBodyScrollLock()
})

watch(
  () => [route.path, String(route.query.protection_report || '')],
  () => {
    void tryOpenProtectionReportFromRoute()
  },
)

function scheduleBroadcastMiniSnapshot() {
  if (broadcastMiniDebounceTimer) clearTimeout(broadcastMiniDebounceTimer)
  broadcastMiniDebounceTimer = setTimeout(() => {
    broadcastMiniDebounceTimer = null
    const sec = dashboardSection.value || 'account'
    if (sec !== 'account' && sec !== 'subscription') return
    if (!accountShowBroadcastMiniCard.value) return
    void loadBroadcastMiniSnapshot()
  }, 280)
}

watch(
  () => [dashboardSection.value, accountShowBroadcastMiniCard.value, me.value?.telegram_id, route.path],
  () => {
    scheduleBroadcastMiniSnapshot()
    restartStatBroadcastNudge()
  },
  { immediate: true },
)

watch(accountShowBroadcastMiniCard, () => {
  homeStatBroadcastSlide.value = 0
})

watch(
  () => [
    showPromoCodeModal.value,
    showPremiumPayMethodModal.value,
    showPaymentRedirectScreen.value,
    showPremiumActivatedModal.value,
    showFreeAurumGateModal.value,
    showPremiumAurumShowcaseModal.value,
    showUpdatesRoadmapModal.value,
  ],
  () => updateBodyScrollLock(),
)

function onVisibilityPaymentCheck() {
  if (document.visibilityState === 'visible') {
    schedulePremiumActivationCheck()
  }
}

function onWindowFocusPremiumCheck() {
  if (!waitPremiumActivationAfterPayment.value) return
  schedulePremiumActivationCheck()
}

/** Telegram / WebView: гарантируем вкладку из ?section= (даже если guard отработал не так). */
watch(
  () => [String(route.path || ''), String(route.query?.section || '').trim().toLowerCase()],
  ([path, sec]) => {
    if (path !== '/') return
    if (sec === 'billing' || sec === 'partner' || sec === 'account' || sec === 'subscription') {
      setDashboardSection(sec)
    }
  },
  { immediate: true },
)

watch(
  () => String(route.query?.updates || ''),
  (flag) => {
    if (flag !== '1') return
    showUpdatesRoadmapModal.value = true
    try {
      const q = { ...route.query }
      delete q.updates
      router.replace({ path: route.path, query: q }).catch(() => {})
    } catch {
      //
    }
  },
)

watch(dashboardSection, (section) => {
  restartUpdatesRotation()
  dashSwitchBusy.value = true
  if (dashSwitchTimer) clearTimeout(dashSwitchTimer)
  dashSwitchTimer = setTimeout(() => {
    dashSwitchBusy.value = false
    dashSwitchTimer = null
  }, 50)
  if ((section === 'billing' || section === 'subscription') && hasInitData.value) {
    fetchSilent(() => rawApi.me())
      .then((v) => {
        applyMeState(v)
      })
      .catch(() => {})
    nextTick(() => {
      const mainEl = typeof document !== 'undefined' ? document.querySelector('main') : null
      mainEl?.scrollTo?.({ top: 0, behavior: 'auto' })
      window.scrollTo?.(0, 0)
    })
  }
  if (section !== 'billing') {
    landingSelectedPlanMonths.value = null
  }
  if (section !== 'tokens') {
    showPremiumTokenLanding.value = false
  }
})

function scrollBillingElIntoView(el) {
  nextTick(() => {
    nextTick(() => {
      el?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
    })
  })
}

function scrollToBillingPremiumPlans() {
  scrollBillingElIntoView(billingPremiumPlansRef.value)
}

function scrollToBillingPremiumPitch() {
  scrollBillingElIntoView(billingPremiumPitchRef.value)
}

function scrollToBillingPremiumCompare() {
  scrollBillingElIntoView(billingPremiumCompareRef.value)
}

function scrollToBillingLandingPlans() {
  scrollBillingElIntoView(billingLandingPlansRef.value)
}

function selectLandingPlan(months) {
  const n = Number(months)
  landingSelectedPlanMonths.value = landingSelectedPlanMonths.value === n ? null : n
}

function onLandingContinue() {
  const m = landingSelectedPlanMonths.value
  if (m) {
    openPremiumPayMethodModal(m)
    return
  }
  scrollToBillingPremiumPlans()
  showToast('Выберите срок на карточке или в списке ниже')
}

function closePremiumPayMethodModal() {
  if (premiumPayMethodProceedLoading.value) return
  showPremiumPayMethodModal.value = false
  premiumPayMethodMonths.value = null
  tokenPayMethodPackTokens.value = null
  premiumPayMethodSelected.value = 'card'
  premiumPayMethodFlow.value = 'main'
}

function openPremiumPayMethodModal(months, flow = 'main') {
  if (payLoadingMonths.value != null || payLoadingTestMonths.value != null) return
  const n = Number(months)
  if (!Number.isFinite(n) || n <= 0) return
  if (flow === 'tokens') {
    tokenPayMethodPackTokens.value = n
    premiumPayMethodMonths.value = null
  } else {
    premiumPayMethodMonths.value = n
    tokenPayMethodPackTokens.value = null
  }
  premiumPayMethodSelected.value = 'card'
  premiumPayMethodFlow.value = flow === 'test' || flow === 'tokens' ? flow : 'main'
  showPremiumPayMethodModal.value = true
}

async function onPremiumPayMethodProceed() {
  const m = premiumPayMethodMonths.value
  const tokenPack = Number(tokenPayMethodPackTokens.value || 0)
  const method = premiumPayMethodSelected.value
  const flow = premiumPayMethodFlow.value
  if (!m && !tokenPack) return
  if (method === 'card') {
    const okPin = await requestPinIfNeeded('payments')
    if (!okPin) {
      if (shouldAskPinForAction('payments')) showToast('Нужен код из «Настройки → Безопасность»')
      return
    }
    premiumPayMethodProceedLoading.value = true
    try {
      if (flow === 'tokens') await startTokenPackPayment(tokenPack)
      else if (flow === 'test') await startTestTariffPayment(m)
      else await startPayment(m)
    } finally {
      premiumPayMethodProceedLoading.value = false
    }
    return
  }
  showToast('Telegram Stars скоро будет доступно. Выберите оплату картой / СБП через ЮKassa.')
}

const billingScrollTargets = {
  plans: () => billingPremiumPlansRef.value,
  pitch: () => billingPremiumPitchRef.value,
  compare: () => billingPremiumCompareRef.value,
  landing: () => billingLandingPlansRef.value,
}

watch(
  () =>
    `${dashboardSection.value}|${String(route.query.scroll || '').trim().toLowerCase()}|${me.value ? '1' : '0'}`,
  (key) => {
    const [section, scroll, ready] = key.split('|')
    if (ready !== '1' || section !== 'billing') return
    const sc = String(scroll || '').trim().toLowerCase()
    const pick = billingScrollTargets[sc]
    if (!pick) return
    nextTick(() => {
      nextTick(() => {
        pick()?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
        const q = { ...route.query }
        delete q.scroll
        const keys = Object.keys(q)
        router.replace({ path: route.path, query: keys.length ? q : undefined }).catch(() => {})
      })
    })
  },
)

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onGlobalPointerDown, true)
  if (activityTimer) clearInterval(activityTimer)
  if (updatesTimer) clearInterval(updatesTimer)
  if (dashSwitchTimer) clearTimeout(dashSwitchTimer)
  if (tokenHideTimer) clearTimeout(tokenHideTimer)
  if (spikeAlertTimer) clearInterval(spikeAlertTimer)
  if (broadcastMiniDebounceTimer) clearTimeout(broadcastMiniDebounceTimer)
  if (statBroadcastNudgeTimer) {
    clearInterval(statBroadcastNudgeTimer)
    statBroadcastNudgeTimer = null
  }
  if (statBroadcastJustDraggedClear) clearTimeout(statBroadcastJustDraggedClear)
  if (paymentRedirectTimer) clearInterval(paymentRedirectTimer)
  stopPaymentActivationFastPolling()
  document.removeEventListener('visibilitychange', onVisibilityPaymentCheck)
  if (typeof window !== 'undefined') {
    window.removeEventListener('focus', onWindowFocusPremiumCheck)
  }
  if (typeof document !== 'undefined') {
    document.body.style.overflow = ''
    document.documentElement.style.overflow = ''
  }
  tokenLandingOrbitPreloadImg = null
})

function onTokenWrapEnter() {
  if (!tariffIsPremium.value) return
  if (tokenHideTimer) {
    clearTimeout(tokenHideTimer)
    tokenHideTimer = null
  }
  showTokenBreakdown.value = true
}

function onTokenWrapLeave() {
  if (!tariffIsPremium.value) return
  if (tokenHideTimer) clearTimeout(tokenHideTimer)
  tokenHideTimer = setTimeout(() => {
    showTokenBreakdown.value = false
    tokenHideTimer = null
  }, 160)
}

function toggleTokenBreakdown(ev) {
  ev?.stopPropagation?.()
  if (tokenHideTimer) {
    clearTimeout(tokenHideTimer)
    tokenHideTimer = null
  }
  showTokenBreakdown.value = !showTokenBreakdown.value
}

function closeFundsMovementModal() {
  showFundsMovementModal.value = false
}

function onGlobalPointerDown(event) {
  const target = event?.target
  if (!(target instanceof Node)) return

  if (showTokenBreakdown.value) {
    const tel = tokenBreakdownWrapRef.value
    if (tel && !tel.contains(target)) {
      showTokenBreakdown.value = false
      if (tokenHideTimer) {
        clearTimeout(tokenHideTimer)
        tokenHideTimer = null
      }
    }
  }

  if (showFundsMovementModal.value) {
    const fel = fundsModalWrapRef.value
    if (fel && !fel.contains(target)) {
      showFundsMovementModal.value = false
    }
  }

  if (showSubscriptionInfo.value) {
    const wrapEl = subscriptionInfoWrapRef.value
    if (wrapEl && !wrapEl.contains(target)) {
      showSubscriptionInfo.value = false
    }
  }
}

function fmtAmount(v) {
  const n = Number(v || 0)
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}

function providerLabel(v) {
  const raw = String(v || '').toLowerCase()
  if (!raw) return '—'
  if (raw.includes('yookassa')) return 'YooKassa'
  return raw
}

function tokenReasonLabel(v) {
  const raw = String(v || '').trim().toLowerCase()
  if (!raw) return '—'
  if (raw === 'tokens_purchase') return 'Покупка токенов'
  if (raw === 'broadcast_bonus') return 'Рассылка (списано с бонусных ⚡)'
  if (raw === 'broadcast_sub') return 'Рассылка (исторический остаток)'
  if (raw === 'daily_burn') return 'Ежедневное списание подписки'
  if (raw === 'bonus_to_sub') return 'Перевод: партнерские -> подписочные (списание)'
  if (raw === 'bonus_to_sub_target') return 'Перевод: партнерские -> подписочные (зачисление)'
  return raw
}

async function ensurePartnerData() {
  if (partnerData.value || partnerLoading.value) return
  partnerLoading.value = true
  partnerError.value = ''
  try {
    partnerData.value = await rawApi.referral()
  } catch (e) {
    partnerError.value = String(e?.body?.detail || e?.message || 'Не удалось загрузить партнерские данные')
  } finally {
    partnerLoading.value = false
  }
}

async function ensureReferralPeople() {
  if (referralPeopleLoading.value) return
  referralPeopleLoading.value = true
  try {
    referralPeople.value = await rawApi.referralPeople()
  } catch {
    referralPeople.value = { full_list: [], top_active: [] }
  } finally {
    referralPeopleLoading.value = false
  }
}

async function ensurePartnerPayouts() {
  if (partnerPayoutsLoading.value) return
  partnerPayoutsLoading.value = true
  try {
    partnerPayouts.value = await rawApi.referralPayouts()
  } catch {
    //
  } finally {
    partnerPayoutsLoading.value = false
  }
}

function normalizeTokenPacksPayload(r) {
  if (Array.isArray(r)) return r
  const nested = r?.data
  const items = r?.items ?? r?.packs ?? (nested && (nested.items ?? nested.packs))
  return Array.isArray(items) ? items : []
}

function mapTokenPackRow(raw) {
  const tokens = Number(raw?.tokens ?? raw?.token ?? 0)
  const priceRub = Number(raw?.price_rub ?? raw?.price ?? raw?.priceRub ?? 0)
  const discountLabel = raw?.discount_label ?? raw?.discountLabel ?? null
  if (!tokens || !Number.isFinite(tokens)) return null
  const tag = raw?.tag
  return {
    tokens,
    price_rub: priceRub,
    discount_label: discountLabel || null,
    extra: raw?.extra === true,
    tag: tag != null && String(tag).trim() ? String(tag).trim() : null,
  }
}

async function loadTokenPacksFromApi() {
  tokenPacksLoading.value = true
  tokenPacksError.value = ''
  try {
    const r = await rawApi.billingTokenPacks()
    const rows = normalizeTokenPacksPayload(r).map(mapTokenPackRow).filter(Boolean)
    tokenPacks.value = [...rows].sort((a, b) => Number(a.tokens) - Number(b.tokens))
  } catch (e) {
    tokenPacks.value = []
    tokenPacksError.value = messageFromApiError(e)
  } finally {
    tokenPacksLoading.value = false
  }
}

async function openYookassaUrlFromResponse(r) {
  const url = r?.confirmation_url
  if (!url) return
  const tg = window.Telegram?.WebApp
  if (typeof tg?.openLink === 'function') tg.openLink(url, { try_instant_view: false })
  else window.open(url, '_blank', 'noopener,noreferrer')
}

async function startTokenPackPayment(tokens) {
  const t = Number(tokens || 0)
  if (!t) return
  payLoadingTokenPack.value = t
  try {
    const r = await fetchSilent(() => api.yookassaCreateTokensPayment(t))
    const url = r?.confirmation_url
    if (!url) {
      showToast('Нет ссылки на оплату')
      return
    }
    beginPaymentRedirect(url)
  } finally {
    payLoadingTokenPack.value = null
  }
}

function buyTokenPackYookassa(tokens) {
  openPremiumPayMethodModal(Number(tokens || 0), 'tokens')
}

function selectTokenPack(tokens) {
  const t = Number(tokens || 0)
  if (!t) return
  selectedTokenPack.value = selectedTokenPack.value === t ? null : t
}

function continueTokenPackCheckout() {
  const t = Number(selectedTokenPack.value || 0)
  if (!t) {
    showToast('Выберите пакет токенов')
    return
  }
  buyTokenPackYookassa(t)
}

async function buyTokenPackAdminTest(tokens) {
  const t = Number(tokens || 0)
  if (!t) return
  const okPin = await requestPinIfNeeded('payments')
  if (!okPin) {
    if (shouldAskPinForAction('payments')) showToast('Нужен код из «Настройки → Безопасность»')
    return
  }
  testTokenPayLoading.value = true
  try {
    const r = await fetchSilent(() => rawApi.adminTestCreateTokensPayment(t))
    await openYookassaUrlFromResponse(r)
  } finally {
    testTokenPayLoading.value = false
  }
}

const AURUM_LIST_RUB_PER_TOKEN = 2.0

function showAurumTokensHelp() {
  const packs = tokenPacks.value || []
  const sample = packs[0]
  let packLine = ''
  if (sample && Number(sample.tokens) > 0 && sample.price_rub != null) {
    const per = Number(sample.price_rub) / Number(sample.tokens)
    packLine = `Сейчас в каталоге, например, пакет ${Number(sample.tokens)} AURUM за ${Math.round(Number(sample.price_rub))} ₽ — это примерно ${per.toFixed(2)} ₽ за один AURUM.`
  }
  const paras = [
    'AURUM ✨ — «топливо» для рассылок и ИИ в кабинете.',
    `Ориентир по цене в лоб: около ${AURUM_LIST_RUB_PER_TOKEN} ₽ за 1 AURUM; в пакетах обычно выгоднее за счёт скидок.${packLine ? ` ${packLine}` : ''}`,
    'С Premium в подарок начисляется AURUM ✨ (меньше суммы в рублях, чтобы подписка и докупка не дублировали выгоду). Партнёрские ⚡ лежат отдельно — их можно перевести в AURUM. Рассылка списывает сначала AURUM ✨.',
  ]
  aurumHelpParagraphs.value = paras
  showAurumHelpModal.value = true
}

const tokensInfoBtnClass =
  'inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-white/20 bg-white/[0.06] text-[9px] font-extrabold text-white/80 shadow-[inset_0_1px_0_rgba(255,255,255,0.1)] backdrop-blur-md transition hover:bg-white/[0.11] active:scale-95'

const tokensInfoToolbarClass =
  'inline-flex shrink-0 items-center gap-0.5 rounded-full border border-white/[0.1] bg-black/30 px-0.5 py-0.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-md'

const tokensInfoBtnAmberClass =
  'inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-amber-400/40 bg-amber-950/45 text-[9px] font-extrabold text-amber-100 shadow-[inset_0_1px_0_rgba(251,191,36,0.12)] backdrop-blur-md transition hover:bg-amber-900/35 active:scale-95'

function openTokensSubscriptionInfo() {
  tokensInfoTitle.value = 'Пакеты и подписка'
  tokensInfoParagraphs.value = [
    'Пакеты AURUM можно оплатить только при активной подписке Guard Premium.',
    'Так расход токенов остаётся связанным с тарифом, а риск злоупотреблений ниже.',
  ]
  showTokensInfoModal.value = true
}

function openTokensCheckoutInfo() {
  tokensInfoTitle.value = 'Оплата'
  tokensInfoParagraphs.value = [
    'Нажмите на карточку пакета — откроется страница оплаты YooKassa с уже выбранной суммой.',
    'Возврат средств выполняется по правилам банка и платёжной системы.',
  ]
  showTokensInfoModal.value = true
}

function openTokensAdminTestInfo() {
  tokensInfoTitle.value = 'Тестовая оплата'
  tokensInfoParagraphs.value = [
    'Видно только администраторам. Создаёт тот же платёж YooKassa, что и в админке, без дополнительной проверки Premium.',
  ]
  showTokensInfoModal.value = true
}

function openPremiumHeaderInfo() {
  tokensInfoTitle.value = 'Guard Premium'
  const bullets = PREMIUM_PLANS.filter((p) => p.savings).map((p) => `${p.label} · ${p.price} — ${p.savings}.`)
  tokensInfoParagraphs.value = [
    'Промокод: введите в поле и нажмите «Готово». Скидка или бонус — по правилам акции.',
    'Оплата: нажмите срок в сетке — откроется YooKassa. К подписке в подарок начисляется AURUM ✨ (ориентир: сумма в рублях / 4 ≈ число ✨).',
    'Длинные периоды выгоднее, чем платить каждый месяц по отдельности:',
    ...bullets,
  ]
  showTokensInfoModal.value = true
}

function openPremiumPayMethodInfo() {
  tokensInfoTitle.value = 'Как проходит оплата'
  tokensInfoParagraphs.value = [
    'Мы не вводим карту внутри Telegram: после выбора периода открывается защищённая страница ЮKassa — там карта, СБП и другие способы, которые включены в вашем магазине.',
    '1. Нажмите срок подписки ниже и выберите «Банковская карта».',
    '2. Оплатите на стороне ЮKassa.',
    '3. Вернитесь в Guard; при необходимости обновите экран — Premium подтянется.',
    'Автопродление привязано к сохранённой карте в ЮKassa — блок «Авто» ниже после первой оплаты.',
  ]
  showTokensInfoModal.value = true
}

function openPremiumAutorenewInfo() {
  tokensInfoTitle.value = 'Автосписание'
  tokensInfoParagraphs.value = [
    'При включённом автосписании продление идёт по сохранённой карте, чтобы защита не прерывалась.',
    'Отключить автосписание можно в любой момент — доступ сохранится до конца уже оплаченного периода.',
  ]
  showTokensInfoModal.value = true
}

function openPremiumTestTariffInfo() {
  tokensInfoTitle.value = 'Тест тарифов'
  tokensInfoParagraphs.value = [
    'Блок виден только вашему аккаунту. Создаёт тот же платёж YooKassa, что и у обычных кнопок выше.',
  ]
  showTokensInfoModal.value = true
}

watch(showAllTokenPacks, (open) => {
  if (open) return
  const sel = Number(selectedTokenPack.value || 0)
  if (!sel) return
  const p = (tokenPacks.value || []).find((x) => Number(x.tokens) === sel)
  if (p?.extra) selectedTokenPack.value = null
})

watch(
  () => dashboardSection.value,
  (section) => {
    if (section === 'partner') {
      ensurePartnerData()
      ensureReferralPeople()
      ensurePartnerPayouts()
      return
    }
    if (section === 'tokens') {
      loadTokenPacksFromApi()
      fetchSilent(() => api.me())
        .then((v) => {
          applyMeState(v)
        })
        .catch(() => {})
      return
    }
    if (section === 'account') {
      if (Date.now() - lastActivitySummaryOkAt > 4500) refreshActivitySummarySilent()
    }
  }
)

const partnerAurumTokens = computed(() => {
  const v = Number(partnerData.value?.aurum_credits || 0)
  return Number.isInteger(v) ? String(v) : v.toFixed(2)
})
const partnerBonusTokens = computed(() => {
  const v = Number(partnerData.value?.bonus_credits || 0)
  return Number.isInteger(v) ? String(v) : v.toFixed(2)
})
const paidFullRefs = computed(() => (referralPeople.value?.full_list || []).filter((x) => !!x?.is_paid))
const paidActiveRefs = computed(() => (referralPeople.value?.top_active || []).filter((x) => !!x?.is_paid))
const partnerActiveUntilLabel = computed(() => formatDateTimeRu(partnerData.value?.active_until))

async function copyPartnerLink() {
  const link = String(partnerData.value?.ref_link || '')
  if (!link) return
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(link)
      alert('Ссылка скопирована')
      return
    }
  } catch {
    //
  }
  alert('Скопируйте ссылку вручную')
}

function sharePartnerLink() {
  const link = String(partnerData.value?.ref_link || '')
  if (!link) return
  fetchSilent(() => api.referralShareHit()).catch(() => {})
  const text = 'Guard защищает чаты от спама. Подключайся по моей ссылке.'
  const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`
  const tg = window.Telegram?.WebApp
  if (typeof tg?.openTelegramLink === 'function') {
    tg.openTelegramLink(shareUrl)
    return
  }
  if (typeof tg?.openLink === 'function') {
    tg.openLink(shareUrl)
    return
  }
  window.open(shareUrl, '_blank', 'noopener,noreferrer')
}

function displayReferralName(item) {
  const firstName = String(item?.first_name || '').trim()
  const username = String(item?.username || '').trim()
  if (firstName) return firstName
  if (username) return `@${username}`
  const tgId = Number(item?.telegram_id || 0)
  if (tgId > 0) return `ID ${tgId}`
  return 'Пользователь'
}

async function setDashboardStatsPeriod(key) {
  const k = String(key || 'today')
  dashboardStatsPeriod.value = k
  if (k === 'today') {
    dashboardPeriodBreakdown.value = null
    await refreshActivitySummarySilent()
    return
  }
  dashboardPeriodLoading.value = true
  try {
    dashboardPeriodBreakdown.value = await rawApi.activityBreakdown(k, 'all')
  } catch {
    dashboardPeriodBreakdown.value = null
  } finally {
    dashboardPeriodLoading.value = false
  }
}

function onDashboardStatsPeriodChange(ev) {
  const v = String(ev?.target?.value || 'today')
  void setDashboardStatsPeriod(v)
}

async function refreshActivitySummarySilent() {
  if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
  const gen = ++activitySummaryFetchGen
  try {
    const data = await rawApi.activitySummary()
    if (gen !== activitySummaryFetchGen) return
    activitySummary.value = data
    lastActivitySummaryOkAt = Date.now()
    if (dashboardStatsPeriod.value !== 'today') {
      try {
        dashboardPeriodBreakdown.value = await rawApi.activityBreakdown(dashboardStatsPeriod.value, 'all')
      } catch {
        dashboardPeriodBreakdown.value = null
      }
    }
  } catch (e) {
    try {
      console.warn('[Guard] /api/activity/summary failed', e?.status, e?.body?.detail || e?.message || e)
    } catch {
      //
    }
  }
}

async function refreshActivityJournalSilent() {
  if (!showActivityModal.value) return
  try {
    const r = await rawApi.activityJournal(null, 300)
    activityJournal.value = r?.items || []
    const fromJournal = Array.isArray(r?.chats) ? r.chats : []
    if (fromJournal.length) {
      activityChats.value = fromJournal
    } else {
      const chatsRes = await rawApi.chats('all').catch(() => null)
      const fallbackChats = Array.isArray(chatsRes?.chats) ? chatsRes.chats : []
      activityChats.value = fallbackChats
    }
  } catch {
    //
  }
}

function presetHours(key) {
  if (key === '7d') return 168
  if (key === '30d') return 720
  if (key === '6m') return 24 * 183
  if (key === '1y') return 24 * 365
  return 24
}

function localInputToIsoUtc(s) {
  if (!s) return ''
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return ''
  return d.toISOString()
}

function getGroupTimeRange() {
  if (groupStatsUseCustom.value && groupStatsFromInput.value && groupStatsToInput.value) {
    const fromTs = localInputToIsoUtc(groupStatsFromInput.value)
    const toTs = localInputToIsoUtc(groupStatsToInput.value)
    if (fromTs && toTs) return { fromTs, toTs }
  }
  const hours = presetHours(groupStatsPreset.value)
  const to = new Date()
  const from = new Date(to.getTime() - hours * 3600 * 1000)
  return { fromTs: from.toISOString(), toTs: to.toISOString() }
}

async function loadGroupActivityFull() {
  const cid = Number(groupActivityChatId.value || 0)
  if (!cid) return
  const { fromTs, toTs } = getGroupTimeRange()
  if (!fromTs || !toTs) return
  try {
    const [bd, jr] = await Promise.all([
      rawApi.activityGroupBreakdown(cid, { fromTs, toTs }),
      rawApi.activityJournal(cid, 500, fromTs, toTs),
    ])
    groupBreakdown.value = bd
    groupJournalItems.value = jr?.items || []
    if (bd?.chat_title) groupActivityTitle.value = bd.chat_title
  } catch {
    //
  }
}

async function refreshGroupActivitySilent() {
  if (!showGroupActivityModal.value) return
  await loadGroupActivityFull()
}

function selectGroupStatsPreset(key) {
  groupStatsPreset.value = key
  groupStatsUseCustom.value = false
  if (showGroupActivityModal.value) loadGroupActivityFull()
}

function applyGroupCustomRange() {
  if (!groupStatsFromInput.value || !groupStatsToInput.value) return
  const fromTs = localInputToIsoUtc(groupStatsFromInput.value)
  const toTs = localInputToIsoUtc(groupStatsToInput.value)
  if (!fromTs || !toTs) return
  if (new Date(fromTs) >= new Date(toTs)) return
  groupStatsUseCustom.value = true
  groupStatsRangeExpanded.value = false
  loadGroupActivityFull()
}

function toggleGroupStatsRangePanel() {
  groupStatsRangeExpanded.value = !groupStatsRangeExpanded.value
}

function goBroadcastMiniCreate() {
  router.push({ path: '/admin', query: { admin_tab: 'broadcasts' } })
}

function _apSchedActive(ap) {
  const rs = String(ap?.runState || '').toLowerCase()
  return !!ap && (rs === 'running' || rs === 'paused')
}

async function loadBroadcastMiniSnapshot() {
  if (!me.value || !hasInitData.value) return
  broadcastMiniLoading.value = true
  try {
    const [gRes, chRes, brRes, campRes] = await Promise.all([
      rawApi.adminBroadcastGroups('mine').catch(() => ({ items: [] })),
      rawApi.adminBroadcastChannels('mine').catch(() => ({ items: [] })),
      rawApi.adminBroadcasts('mine').catch(() => ({ items: [] })),
      rawApi.adminAutopostCampaigns().catch(() => ({ items: [] })),
    ])
    const gItems = gRes?.items || []
    const chItems = chRes?.items || []
    broadcastMiniEligibleCount.value = gItems.length + chItems.length
    const brList = brRes?.items || []
    const camps = campRes?.items || []
    let sched = 0
    for (const c of camps) {
      if (_apSchedActive(c?.autopost)) sched += 1
    }
    for (const b of brList) {
      if (_apSchedActive(b?.autopost)) sched += 1
    }
    broadcastMiniScheduledCount.value = sched
    broadcastMiniSentToday.value = null
    if (brList.length > 0) {
      const bid = Number(brList[0]?.id || 0)
      if (bid > 0) {
        try {
          const st = await rawApi.adminBroadcastAutopostStats(bid, 1)
          broadcastMiniSentToday.value =
            Number(st?.bots?.recipient_ok || 0) + Number(st?.groups?.recipient_ok || 0)
        } catch {
          broadcastMiniSentToday.value = null
        }
      }
    }
  } catch {
    broadcastMiniEligibleCount.value = null
    broadcastMiniScheduledCount.value = null
    broadcastMiniSentToday.value = null
  } finally {
    broadcastMiniLoading.value = false
  }
}

async function openActivityDetails() {
  showActivityModal.value = true
  activityLoading.value = true
  try {
    const r = await rawApi.activityJournal(null, 300)
    activityJournal.value = r?.items || []
    const fromJournal = Array.isArray(r?.chats) ? r.chats : []
    if (fromJournal.length) {
      activityChats.value = fromJournal
    } else {
      const chatsRes = await rawApi.chats('all').catch(() => null)
      const fallbackChats = Array.isArray(chatsRes?.chats) ? chatsRes.chats : []
      activityChats.value = fallbackChats
    }
  } catch {
    activityJournal.value = []
    activityChats.value = []
  } finally {
    activityLoading.value = false
  }
}

/** Из «Подключённые чаты» (делегированные): тот же отчёт, что по «Подробнее» на главной. */
async function tryOpenProtectionReportFromRoute() {
  if (route.path !== '/') return
  let mustOpen = String(route.query.protection_report || '').trim() === '1'
  if (!mustOpen) {
    try {
      mustOpen = sessionStorage.getItem('guard_open_protection_report') === '1'
    } catch {
      //
    }
  }
  if (!mustOpen) return
  setDashboardSection('account')
  await nextTick()
  await openActivityDetails()
  try {
    sessionStorage.removeItem('guard_open_protection_report')
  } catch {
    //
  }
  const q = { ...route.query }
  delete q.protection_report
  await router.replace({ path: '/', query: Object.keys(q).length ? q : undefined })
}

async function openGroupActivityDetails(row) {
  const cid = Number(row?.chat_id || 0)
  if (!cid) return
  groupActivityChatId.value = String(cid)
  groupActivityTitle.value = String(row?.chat_title || `Чат ${cid}`)
  groupStatsPreset.value = '24h'
  groupStatsUseCustom.value = false
  groupStatsRangeExpanded.value = false
  groupStatsFromInput.value = ''
  groupStatsToInput.value = ''
  showGroupActivityModal.value = true
  await loadGroupActivityFull()
}

function closeGroupActivityModal() {
  billingFromGroupStats.value = false
  showGroupActivityModal.value = false
  groupActivityChatId.value = ''
  groupBreakdown.value = null
  groupJournalItems.value = []
}

function goBillingCloseGroupModal() {
  billingFromGroupStats.value = true
  setDashboardSection('billing')
  showGroupActivityModal.value = false
  showActivityModal.value = false
}

async function backFromBillingToGroupStats() {
  billingFromGroupStats.value = false
  setDashboardSection('account')
  if (groupActivityChatId.value) {
    showGroupActivityModal.value = true
    await loadGroupActivityFull()
  }
}

function openBillingSection(opts = {}) {
  billingFromGroupStats.value = false
  if (opts.scrollPlans) {
    void router.push({ path: '/', query: { ...route.query, section: 'billing', scroll: 'plans' } })
  } else if (opts.scrollLanding) {
    void router.push({ path: '/', query: { ...route.query, section: 'billing', scroll: 'landing' } })
  } else {
    setDashboardSection('billing')
    const q = { ...route.query, section: 'billing' }
    delete q.scroll
    void router.push({ path: '/', query: q })
  }
}

function openPremiumLandingFromAurumGate() {
  showFreeAurumGateModal.value = false
  openBillingSection({ scrollLanding: true })
}

function openTokenPacksFromShowcase() {
  showPremiumAurumShowcaseModal.value = false
  showPremiumTokenLanding.value = true
  setDashboardSection('tokens')
  // Делаем несколько попыток после переключения секции/отрисовки, чтобы скролл
  // стабильно срабатывал и заголовок AURUM был в зоне видимости.
  const scrollToTitle = () => {
    const titleEl = premiumTokenLandingTitleRef.value
    if (!titleEl || typeof titleEl.getBoundingClientRect !== 'function') {
      premiumTokenLandingRef.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
      return
    }
    const rect = titleEl.getBoundingClientRect()
    // ~0.5 см выше, чтобы рамка/хедер не перекрывали заголовок
    const topOffset = 96
    const targetTop = Math.max(0, rect.top + (window.scrollY || 0) - topOffset)
    window.scrollTo({ top: targetTop, behavior: 'smooth' })
    const mainEl = typeof document !== 'undefined' ? document.querySelector('main') : null
    if (mainEl && typeof mainEl.scrollTo === 'function') {
      const mainRect = mainEl.getBoundingClientRect()
      const mainTarget = Math.max(0, mainEl.scrollTop + rect.top - mainRect.top - topOffset)
      mainEl.scrollTo({ top: mainTarget, behavior: 'smooth' })
    }
  }
  nextTick(() => {
    nextTick(scrollToTitle)
    setTimeout(scrollToTitle, 80)
    setTimeout(scrollToTitle, 180)
  })
}

function scrollToPremiumTokenPacks(opts = {}) {
  const { reloadPacks = true } = opts
  selectedTokenPack.value = null
  const scrollPacks = () => {
    const titleEl = tokenLandingPackChoiceTitleRef.value
    const sectionEl = tokenLandingPackChoiceRef.value
    const el =
      titleEl && !tokenPacksLoading.value ? titleEl : sectionEl
    el?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  }
  const afterLayout = () => {
    nextTick(() => {
      nextTick(() => {
        scrollPacks()
        requestAnimationFrame(scrollPacks)
        setTimeout(scrollPacks, 80)
        setTimeout(scrollPacks, 220)
      })
    })
  }
  if (reloadPacks) {
    void loadTokenPacksFromApi().then(() => afterLayout())
  } else {
    afterLayout()
  }
}

function scrollToTokenHowItWorks() {
  nextTick(() => {
    nextTick(() => {
      tokenLandingHowItWorksRef.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
    })
  })
}

function preloadTokenLandingOrbit() {
  if (typeof window === 'undefined') return
  const img = new Image()
  img.decoding = 'async'
  img.loading = 'eager'
  img.src = tokenLandingOrbitSrc
  tokenLandingOrbitPreloadImg = img
}

function onQuickNavTokensClick() {
  if (tariffIsPremium.value) showPremiumAurumShowcaseModal.value = true
  else showFreeAurumGateModal.value = true
}

function onTokensBoltClick(ev) {
  ev?.stopPropagation?.()
  if (!tariffIsPremium.value) {
    if (tokenHideTimer) {
      clearTimeout(tokenHideTimer)
      tokenHideTimer = null
    }
    showTokenBreakdown.value = false
    showFreeAurumGateModal.value = true
    return
  }
  toggleTokenBreakdown(ev)
}

function startActivityAutoRefresh() {
  if (activityTimer) clearInterval(activityTimer)
  const tick = () => {
    if (typeof document === 'undefined' || document.visibilityState !== 'hidden') {
      refreshActivitySummarySilent()
      if (showActivityModal.value) refreshActivityJournalSilent()
      if (showGroupActivityModal.value) refreshGroupActivitySilent()
    }
    if (waitPremiumActivationAfterPayment.value) schedulePremiumActivationCheck()
  }
  activityTimer = setInterval(tick, 3000)
}


async function submitPayoutRequest() {
  const amount = Number(payoutAmountRub.value || 0)
  if (!amount) return
  const minPayout = Number(partnerPayouts.value?.min_payout_rub || 1500)
  if (amount < minPayout) {
    alert('Сумма недостаточна для вывода')
    return
  }
  payoutSubmitting.value = true
  try {
    await fetchSilent(() => api.referralPayoutRequest({
      amount_rub: amount,
      method: payoutMethod.value,
      requisites: payoutRequisites.value,
      full_name: payoutFullName.value,
    }))
    payoutAmountRub.value = ''
    payoutRequisites.value = ''
    await ensurePartnerPayouts()
    alert('Заявка на вывод отправлена')
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось отправить заявку'))
  } finally {
    payoutSubmitting.value = false
  }
}

async function transferPartnerBonusToAurum() {
  if (bonusTransferLoading.value) return
  bonusTransferLoading.value = true
  try {
    const r = await fetchSilent(() => api.referralBonusToAurum())
    const moved = Number(r?.moved || 0)
    await Promise.all([
      ensurePartnerData(),
      fetchSilent(() => api.me()).then((v) => { applyMeState(v) }).catch(() => {}),
      ensurePartnerPayouts(),
    ])
    if (moved > 0) {
      alert(`Переведено в AURUM: ${fmtAmount(moved)} ✨`)
    } else {
      alert('Партнерских токенов для перевода нет')
    }
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || 'Не удалось перевести токены'))
  } finally {
    bonusTransferLoading.value = false
  }
}

const docsCalc = computed(() => {
  const amount = Math.max(0, Number(docsExampleSale.value || 0))
  const l1 = Math.round(amount * 0.15 * 100) / 100
  const l2 = Math.round(amount * 0.10 * 100) / 100
  const l3 = Math.round(amount * 0.05 * 100) / 100
  return { amount, l1, l2, l3, total: Math.round((l1 + l2 + l3) * 100) / 100 }
})

async function loadHistoryIfNeeded() {
  if (historyLoadCompleted.value || historyLoading.value) return
  historyLoading.value = true
  try {
    const [p, t] = await Promise.all([
      fetchSilent(() => api.historyPayments()),
      fetchSilent(() => api.historyTokens()),
    ])
    historyPayments.value = p?.items || []
    historyTokens.value = t?.items || []
  } finally {
    historyLoading.value = false
    historyLoadCompleted.value = true
  }
}

async function startPayment(months) {
  payLoadingMonths.value = months
  try {
    const r = await fetchSilent(() => api.yookassaCreatePayment(months))
    const url = r?.confirmation_url
    if (!url) {
      showToast('Нет ссылки на оплату')
      return
    }
    beginPaymentRedirect(url)
  } catch (e) {
    showToast(String(e?.body?.detail || e?.message || 'Не удалось создать платёж'))
  } finally {
    payLoadingMonths.value = null
  }
}

function openPaymentUrl(url) {
  showPaymentRedirectScreen.value = false
  const tg = window.Telegram?.WebApp
  try {
    if (typeof tg?.openLink === 'function') {
      tg.openLink(url, { try_instant_view: false })
      schedulePremiumActivationCheck()
      // Keep flow inside Telegram mini app context; retry openLink if first call no-ops.
      setTimeout(() => {
        if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
          try {
            tg.openLink(url, { try_instant_view: false })
          } catch {
            //
          }
        }
      }, 900)
      setTimeout(() => schedulePremiumActivationCheck(), 1200)
      return
    }
  } catch {
    //
  }
  // Desktop webviews sometimes block window.open; same-tab redirect is more reliable.
  try {
    window.location.assign(url)
  } catch {
    window.open(url, '_blank', 'noopener,noreferrer')
  }
}

function beginPaymentRedirect(url) {
  paymentRedirectUrl.value = String(url || '').trim()
  if (!paymentRedirectUrl.value) return
  paymentWaitBaselinePremium.value = !!me.value?.is_premium
  paymentWaitBaselineUntilTs.value = Date.parse(String(me.value?.subscription_until || '')) || 0
  waitPremiumActivationAfterPayment.value = true
  startPaymentActivationFastPolling()
  showPremiumPayMethodModal.value = false
  showPaymentRedirectScreen.value = true
  paymentRedirectCountdown.value = 3
  if (paymentRedirectTimer) clearInterval(paymentRedirectTimer)
  paymentRedirectTimer = setInterval(() => {
    paymentRedirectCountdown.value = Math.max(0, paymentRedirectCountdown.value - 1)
    if (paymentRedirectCountdown.value <= 0) {
      if (paymentRedirectTimer) {
        clearInterval(paymentRedirectTimer)
        paymentRedirectTimer = null
      }
      openPaymentUrl(paymentRedirectUrl.value)
    }
  }, 1000)
}

function closePremiumActivatedModalToHome() {
  showPremiumActivatedModal.value = false
  setDashboardSection('account')
  const q = { ...route.query, section: 'account' }
  delete q.scroll
  void router.push({ path: '/', query: q }).catch(() => {})
}

function onPremiumActivatedGoSubscription() {
  showPremiumActivatedModal.value = false
  openSubscriptionScreen()
}

function openSubscriptionScreen() {
  setDashboardSection('subscription')
  const q = { ...route.query, section: 'subscription' }
  delete q.scroll
  void router.push({ path: '/', query: q }).catch(() => {})
}

function openPromoCodeModal() {
  showPromoCodeModal.value = true
}

function closePromoCodeModal() {
  if (promoLoading.value) return
  showPromoCodeModal.value = false
}

function openTariffFromSubscription() {
  setDashboardSection('billing')
  const q = { ...route.query, section: 'billing' }
  delete q.scroll
  void router.push({ path: '/', query: q }).catch(() => {})
}

function proceedToPaymentNow() {
  const url = paymentRedirectUrl.value
  if (!url) return
  if (paymentRedirectTimer) {
    clearInterval(paymentRedirectTimer)
    paymentRedirectTimer = null
  }
  openPaymentUrl(url)
}

async function startTestTariffPayment(months) {
  if (!me.value?.test_tariff_payment_visible) return
  payLoadingTestMonths.value = months
  try {
    const r = await fetchSilent(() => api.yookassaCreateTestSubscriptionPayment(months))
    const url = r?.confirmation_url
    if (!url) return
    beginPaymentRedirect(url)
  } finally {
    payLoadingTestMonths.value = null
  }
}

async function applyPromo() {
  const code = (promoCode.value || '').trim()
  if (!code) return
  promoLoading.value = true
  try {
    await fetchSilent(() => api.promoApply(code))
    promoCode.value = ''
    applyMeState(await fetchSilent(() => api.me()))
    window.dispatchEvent(new CustomEvent('guard:me-refresh'))
    showPromoCodeModal.value = false
    showPremiumActivatedModal.value = true
  } finally {
    promoLoading.value = false
  }
}

function openReceiptModal(item) {
  showFundsMovementModal.value = false
  receiptTarget.value = item || null
  try {
    receiptFullName.value = localStorage.getItem(receiptNameKey()) || receiptFullName.value || ''
    receiptEmail.value = localStorage.getItem(receiptEmailKey()) || receiptEmail.value || ''
  } catch {
    //
  }
  showReceiptModal.value = true
}

function openReceiptLink(item) {
  const url = String(item?.receipt_url || '').trim()
  if (!url) return
  const tg = window.Telegram?.WebApp
  if (typeof tg?.openLink === 'function') tg.openLink(url, { try_instant_view: false })
  else window.open(url, '_blank', 'noopener,noreferrer')
}

async function submitReceipt() {
  if (!receiptTarget.value) return
  receiptSending.value = true
  try {
    try {
      localStorage.setItem(receiptNameKey(), receiptFullName.value || '')
      localStorage.setItem(receiptEmailKey(), receiptEmail.value || '')
    } catch {
      //
    }
    await api.sendReceiptEmail(receiptTarget.value.id, receiptEmail.value, receiptFullName.value)
    showReceiptModal.value = false
  } catch (e) {
    const detail = String(e?.body?.detail || e?.message || '')
    if (detail.includes('EMAIL_NOT_CONFIGURED')) {
      alert('Отправка чека по email временно недоступна: почтовый сервер не настроен.')
    } else if (detail) {
      alert(detail)
    } else {
      alert('Не удалось отправить чек. Попробуйте позже.')
    }
  } finally {
    receiptSending.value = false
  }
}

</script>

<template>
  <div class="space-y-3">

    <div v-if="!hasInitData" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
      Откройте панель из Telegram (бот → команда или кнопка меню), чтобы данные подгрузились.
    </div>

    <div v-else-if="bootError" class="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
      <p>{{ bootError }}</p>
      <button
        type="button"
        class="mt-3 w-full rounded-lg bg-slate-800 px-3 py-2 text-sm font-semibold text-white dark:bg-slate-200 dark:text-slate-900"
        @click="loadMeInitial"
      >
        Повторить
      </button>
    </div>

    <div v-else-if="error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
      {{ error }}
    </div>

    <div
      v-else-if="me"
      class="relative isolate -mx-4 min-h-0 px-4 pb-1.5 pt-0 font-display md:-mx-6 md:px-6 md:pt-0"
    >
      <SubscriptionManagementPanel
        v-if="dashboardSection === 'subscription'"
        :profile="me"
        variant="page"
        @update:profile="applyMeState"
        @open-tariff="openTariffFromSubscription"
      />
      <div v-else class="relative z-[2]">
      <div
        v-if="dashSwitchBusy"
        class="pointer-events-none absolute inset-x-0 top-1 z-30 flex justify-center"
        aria-hidden="true"
      >
        <span class="text-xs font-medium text-white/90 drop-shadow-[0_1px_4px_rgba(0,0,0,0.85)]">Секундочку…</span>
      </div>
      <div class="mt-0 space-y-0">
        <div
          class="relative w-full min-w-0 max-w-full pb-1 pt-0 text-slate-100"
          :class="showTokenBreakdown ? 'z-[45]' : ''"
        >
          <!-- Главный блок: без отдельной тёмной подложки — контент на фоне экрана -->
          <div class="pb-1 pl-0 pr-2 pt-0 md:pb-1.5 md:pr-2.5">
            <div class="flex items-start gap-0">
              <div class="relative mt-1 -ml-3 flex h-28 w-28 shrink-0 items-center justify-center self-start md:-ml-3.5">
                <img
                  :src="dashboardAvatarSrc"
                  alt=""
                  draggable="false"
                  class="block h-28 w-28 max-h-[7rem] max-w-[7rem] object-contain object-top"
                  @dragstart.prevent
                />
              </div>
              <div class="flex min-h-0 min-w-0 flex-1 flex-col items-stretch pl-0.5 pt-0.5 sm:pl-1">
                <div class="flex flex-wrap items-center gap-0.5">
                  <svg
                    v-if="protectionStatusOk"
                    class="h-3 w-3 shrink-0 [filter:drop-shadow(0_0_4px_rgba(163,230,53,0.45))]"
                    viewBox="0 0 24 24"
                    fill="none"
                    aria-hidden="true"
                  >
                    <defs>
                      <linearGradient :id="protCheckGradId" x1="3" y1="4" x2="21" y2="20" gradientUnits="userSpaceOnUse">
                        <stop stop-color="#d9f99d" />
                        <stop offset="0.5" stop-color="#a3e635" />
                        <stop offset="1" stop-color="#4d7c0f" />
                      </linearGradient>
                    </defs>
                    <circle cx="12" cy="12" r="12" :fill="`url(#${protCheckGradId})`" />
                    <path d="M7 12l3 3 7-7" stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                  <svg
                    v-else-if="protectionStatusNoChats"
                    class="h-3 w-3 shrink-0"
                    viewBox="0 0 24 24"
                    fill="none"
                    aria-hidden="true"
                  >
                    <defs>
                      <linearGradient :id="protOffGradId" x1="3" y1="4" x2="21" y2="20" gradientUnits="userSpaceOnUse">
                        <stop stop-color="#fecdd3" />
                        <stop offset="0.5" stop-color="#fb7185" />
                        <stop offset="1" stop-color="#9f1239" />
                      </linearGradient>
                    </defs>
                    <circle cx="12" cy="12" r="12" :fill="`url(#${protOffGradId})`" />
                    <path d="M8 8l8 8M16 8L8 16" stroke="white" stroke-width="2.2" stroke-linecap="round" />
                  </svg>
                  <svg v-else class="h-3 w-3 shrink-0 text-amber-500/90" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <circle cx="12" cy="12" r="12" fill="currentColor" />
                    <path d="M8 12h8" stroke="#0a0a0c" stroke-width="2.2" stroke-linecap="round" />
                  </svg>
                  <p
                    class="text-[11px] font-extrabold leading-tight tracking-tight md:text-[12px]"
                    :class="protectionStatusOk ? 'text-lime-400' : protectionStatusNoChats ? 'text-rose-400' : 'text-amber-400'"
                  >
                    <template v-if="protectionStatusOk">Защита активна</template>
                    <template v-else-if="protectionStatusNoChats">Защита отключена</template>
                    <template v-else>Защита не активна</template>
                  </p>
                </div>

                <div class="mt-2 w-full min-w-0 sm:mt-2.5">
                  <div
                    class="flex w-full min-w-0 items-stretch justify-between divide-x divide-white/[0.07]"
                  >
                    <div class="flex min-w-0 flex-1 flex-col items-center px-1.5 text-center sm:px-2">
                      <p class="w-full text-[8px] font-semibold uppercase tracking-wide text-white/45">Удалено</p>
                      <p class="mt-0.5 w-full text-[15px] font-extrabold tabular-nums leading-none text-white sm:text-[16px]">
                        {{ activitySummary?.today?.deleted ?? 0 }}
                      </p>
                      <p class="mt-0.5 w-full text-[9px] font-medium leading-tight text-lime-400/95">сообщения</p>
                    </div>
                    <div class="flex min-w-0 flex-1 flex-col items-center px-1.5 text-center sm:px-2">
                      <p class="w-full text-[8px] font-semibold uppercase tracking-wide text-white/45">Сэкономлено</p>
                      <p class="mt-0.5 w-full whitespace-nowrap text-center text-[12px] font-extrabold tabular-nums leading-none text-white sm:text-[13px]">
                        ~ {{ fmtRubInt(dashboardEstimatedSavedRub) }} ₽
                      </p>
                      <p class="mt-0.5 w-full text-[9px] font-medium leading-tight text-lime-400/95">админам</p>
                    </div>
                    <div class="flex min-w-0 flex-1 flex-col items-center px-1.5 text-center sm:px-2">
                      <p class="w-full whitespace-nowrap text-[8px] font-semibold uppercase leading-tight tracking-wide text-white/45">
                        Уровень защиты
                      </p>
                      <div class="mt-0.5 flex w-full min-w-0 flex-col items-stretch gap-1">
                        <p
                          class="text-center text-[13px] font-extrabold leading-tight sm:text-[14px]"
                          :class="dashboardProtectionLevelMeta.labelClass"
                        >
                          {{ dashboardProtectionLevelMeta.label }}
                        </p>
                        <!-- Полоска на всю ширину колонки; незаполнено — серым как в группах TG -->
                        <div
                          class="flex h-1 w-full min-w-0 gap-1"
                          :title="`Оценка: ${dashboardProtectionLevelMeta.score ?? '—'}/100 (тариф, Guard не на паузе, защищённые группы, удаления за сутки, лимит групп)`"
                        >
                          <span
                            v-for="seg in 4"
                            :key="`prot-seg-${seg}`"
                            class="min-h-[4px] min-w-0 flex-1 rounded-[2px]"
                            :class="
                              seg <= dashboardProtectionLevelMeta.segments && dashboardProtectionLevelMeta.fillSegmentClass
                                ? dashboardProtectionLevelMeta.fillSegmentClass
                                : 'bg-zinc-600/85'
                            "
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <button
                  type="button"
                  class="mt-2 flex w-full items-center gap-1.5 rounded-lg bg-zinc-900/80 px-2 py-1 text-left transition hover:bg-zinc-800/80 active:bg-zinc-800/90 sm:mt-2.5 sm:py-1.5"
                  @click="goManageChats"
                >
                  <span class="grid h-5 w-5 shrink-0 place-items-center rounded-md bg-lime-500/15 text-lime-300">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                      <circle cx="9" cy="7" r="4" />
                      <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
                    </svg>
                  </span>
                  <span class="min-w-0 flex-1 text-[11px] font-semibold leading-tight text-white sm:text-[12px]">
                    Защищено сегодня: <span class="text-lime-400">{{ ruGroupsProtectedLabel(activityProtectedGroupsCount) }}</span>
                  </span>
                  <span class="shrink-0 text-sm font-light text-white/40" aria-hidden="true">›</span>
                </button>
              </div>
            </div>
          </div>

          <template v-if="dashboardSection === 'account'">
          <!-- Нижний ряд: AURUM (уже) | чаты (шире) -->
          <div class="mt-1 grid min-w-0 grid-cols-[minmax(0,40%)_minmax(0,60%)] gap-1.5 md:grid-cols-[minmax(0,38%)_minmax(0,62%)] md:gap-2">
            <div class="relative min-w-0 rounded-xl border border-amber-400/15 bg-gradient-to-b from-black/45 to-zinc-950/90 px-1 pb-0.5 pt-1 shadow-[0_10px_36px_-18px_rgba(0,0,0,0.65)] backdrop-blur-md md:px-1.5">
              <div class="flex items-start justify-between gap-1.5">
                <div class="min-w-0">
                  <p class="flex items-center gap-0.5 text-[8px] font-bold uppercase tracking-wide text-amber-200/90">
                    <span aria-hidden="true">⚡</span> Токены AURUM
                  </p>
                  <p class="mt-0.5 flex items-baseline gap-0.5 text-[18px] font-extrabold tabular-nums leading-none text-white">
                    {{ fmtAmount(me?.aurum_tokens || 0) }}
                    <span class="text-sm">✨</span>
                  </p>
                  <p class="mt-0.5 text-[9px] text-white/45">Ваш баланс</p>
                </div>
                <div class="relative grid h-9 w-9 shrink-0 place-items-center">
                  <span class="absolute inset-0 rounded-full border border-lime-400/25" />
                  <span class="absolute inset-[3px] rounded-full border border-lime-400/15" />
                  <NavIcon name="bolt" class="relative h-4 w-4 text-lime-400 drop-shadow-[0_0_8px_rgba(163,230,53,0.4)]" />
                </div>
              </div>
              <div class="mt-1 grid grid-cols-2 gap-0.5">
                <button
                  type="button"
                  class="flex min-w-0 items-center justify-center gap-0.5 rounded-md bg-gradient-to-b from-lime-400 to-lime-600 px-1 py-1.5 text-[9px] font-bold leading-tight text-lime-950 shadow-[0_3px_10px_rgba(132,204,22,0.3)] transition hover:brightness-105 sm:text-[10px]"
                  @click="onQuickNavTokensClick"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                    <circle cx="9" cy="21" r="1" /><circle cx="20" cy="21" r="1" />
                    <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
                  </svg>
                  Купить
                </button>
                <button
                  type="button"
                  class="flex min-w-0 items-center justify-center gap-0.5 rounded-md border border-white/15 bg-white/[0.06] px-1 py-1.5 text-[9px] font-semibold leading-tight text-white/90 transition hover:bg-white/10 sm:text-[10px]"
                  @click="goAccountHistory"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                    <circle cx="12" cy="12" r="10" />
                    <path d="M12 6v6l4 2" />
                  </svg>
                  История
                </button>
              </div>
            </div>

            <div class="relative min-w-0 rounded-xl bg-gradient-to-b from-black/40 to-zinc-950/90 px-1.5 pb-0.5 pt-1 shadow-[0_10px_36px_-18px_rgba(0,0,0,0.65)] backdrop-blur-md md:pl-2 md:pr-2">
              <button
                v-if="spikeActiveShared"
                type="button"
                class="absolute right-1 top-1 z-[1] inline-flex items-center justify-center"
                title="Есть чат под угрозой"
                aria-label="Открыть делегированные чаты под угрозой"
                @click.stop="openSharedThreatChats"
              >
                <span class="absolute inline-flex h-3 w-3 animate-ping rounded-full bg-yellow-400/55" />
                <span class="relative text-[10px] leading-none text-yellow-300">⚠</span>
              </button>
              <p class="mb-0.5 flex items-center gap-1 text-[8px] font-bold uppercase tracking-wide text-white/85">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-sky-300/90" aria-hidden="true">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
                Ваши чаты
              </p>
              <div class="space-y-1.5">
                <div class="flex min-w-0 items-center gap-1.5">
                  <span class="flex h-5 w-5 shrink-0 items-center justify-center" aria-hidden="true">
                    <svg
                      class="h-[18px] w-[18px] text-lime-300 [filter:drop-shadow(0_0_8px_rgba(132,204,22,0.85))]"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2.2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    >
                      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                      <circle cx="9" cy="7" r="4" />
                    </svg>
                  </span>
                  <span class="shrink-0 whitespace-nowrap text-[10px] font-semibold leading-tight text-lime-200">
                    Группы
                    <span class="ml-0.5 tabular-nums font-medium text-white/90">
                      {{ activityGroupsCount }} / {{ activityGroupsLimit }}
                    </span>
                  </span>
                  <div class="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-white/10">
                    <div
                      class="h-full rounded-full bg-gradient-to-r from-lime-400 to-emerald-600 transition-all"
                      :style="{ width: `${Math.max(0, Math.min(100, Number(activityGroupsProgress || 0)))}%` }"
                    />
                  </div>
                  <button
                    type="button"
                    class="grid h-4 w-4 shrink-0 place-items-center rounded-md border border-lime-300/35 bg-gradient-to-b from-lime-400 to-lime-600 text-[10px] font-bold leading-none text-lime-950 shadow-[0_0_10px_rgba(132,204,22,0.45)]"
                    aria-label="Подключить группу"
                    @click="$router.push({ path: '/connect', query: { kind: 'group' } })"
                  >
                    +
                  </button>
                </div>

                <div class="flex min-w-0 items-center gap-1.5">
                  <span class="flex h-5 w-5 shrink-0 items-center justify-center" aria-hidden="true">
                    <svg
                      class="h-5 w-5 text-cyan-300 [filter:drop-shadow(0_0_10px_rgba(34,211,238,0.95))]"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    >
                      <path d="M11 5L6 9H2v6h4l5 4V5z" />
                      <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
                      <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
                    </svg>
                  </span>
                  <span class="shrink-0 whitespace-nowrap text-[10px] font-semibold leading-tight text-white/95">
                    Каналы
                    <span class="ml-0.5 tabular-nums font-medium text-white/90">
                      {{ activityChannelsCount }} / {{ activityChannelsLimit }}
                    </span>
                  </span>
                  <div class="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-white/10">
                    <div
                      class="h-full rounded-full bg-gradient-to-r from-amber-400 to-orange-600 transition-all"
                      :style="{ width: `${Math.max(0, Math.min(100, Number(activityChannelsProgress || 0)))}%` }"
                    />
                  </div>
                  <button
                    type="button"
                    class="grid h-4 w-4 shrink-0 place-items-center rounded-md border border-amber-300/40 bg-gradient-to-b from-amber-400 to-amber-600 text-[10px] font-bold leading-none text-amber-950 shadow-[0_0_10px_rgba(251,191,36,0.4)]"
                    aria-label="Подключить канал"
                    @click="$router.push({ path: '/connect', query: { kind: 'channel' } })"
                  >
                    +
                  </button>
                </div>
              </div>
              <button
                type="button"
                class="mt-1 flex w-full items-center justify-center gap-0.5 rounded-lg bg-black/30 py-1 text-[10px] font-semibold text-white/90 transition hover:bg-black/45"
                @click="goManageChats"
              >
                Управление
                <span class="text-white/40">›</span>
              </button>
            </div>
          </div>

          <!-- Статистика ↔ Рассылки: на всю ширину, свайп / подсказка раз в 3 с -->
          <div
            class="mt-0.5 w-full min-w-0"
            :class="accountShowBroadcastMiniCard ? 'cursor-grab touch-pan-x active:cursor-grabbing' : ''"
            @pointerdown="onStatBroadcastRailPointerDown"
            @pointermove="onStatBroadcastRailPointerMove"
            @pointerup="onStatBroadcastRailPointerUp"
            @pointercancel="onStatBroadcastRailPointerCancel"
          >
            <div class="min-w-0 w-full overflow-hidden rounded-2xl">
            <div
              class="flex will-change-transform"
              :class="accountShowBroadcastMiniCard ? 'w-[200%]' : 'w-full'"
              :style="accountShowBroadcastMiniCard ? statBroadcastTrackStyle() : {}"
            >
              <div :class="accountShowBroadcastMiniCard ? 'w-1/2 shrink-0 pr-[3px]' : 'w-full shrink-0'">
                <div
                  class="rounded-2xl border border-white/[0.08] bg-gradient-to-b from-[#101010] to-[#0b0b0b] px-2 pb-1 pt-1 shadow-[0_16px_44px_-24px_rgba(0,0,0,0.9)] ring-1 ring-inset ring-white/[0.04] sm:px-2.5 sm:pb-1.5 sm:pt-1.5"
                >
                  <div class="flex items-start justify-between gap-2 pb-0.5 pt-0.5">
                    <div class="-mt-px flex min-w-0 items-center gap-1.5">
                      <span class="grid h-5 w-5 shrink-0 place-items-center text-lime-400/90" aria-hidden="true">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                          <path d="M18 20V10M12 20V4M6 20v-6" stroke-linecap="round" />
                        </svg>
                      </span>
                      <span class="truncate text-[13px] font-semibold leading-none text-white sm:text-[14px]">Статистика</span>
                    </div>
                    <label class="relative shrink-0 pt-px">
                      <span class="sr-only">Период статистики</span>
                      <select
                        class="pointer-events-auto max-w-[8.5rem] cursor-pointer appearance-none rounded-lg border border-lime-500/40 bg-black/50 py-0.5 pl-2 pr-7 text-[11px] font-semibold leading-none text-lime-400 outline-none ring-0 sm:max-w-none sm:py-1 sm:pl-2 sm:text-[12px]"
                        :value="dashboardStatsPeriod"
                        title="Период для показателей ниже"
                        @change="onDashboardStatsPeriodChange"
                      >
                        <option
                          v-for="opt in DASHBOARD_STATS_PERIOD_OPTIONS"
                          :key="opt.key"
                          :value="opt.key"
                        >
                          {{ opt.label }}
                        </option>
                      </select>
                      <span class="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 text-lime-400/90" aria-hidden="true">
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                          <path d="m6 9 6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
                        </svg>
                      </span>
                    </label>
                  </div>

                  <div
                    class="relative mt-0.5 flex min-w-0 gap-0 overflow-x-auto pb-0 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden sm:gap-0.5"
                    :class="dashboardPeriodLoading ? 'opacity-60' : ''"
                  >
                    <div
                      role="button"
                      tabindex="0"
                      class="flex min-w-0 flex-[1_1_0] cursor-pointer flex-col border-r border-white/10 py-1 pr-1 transition hover:bg-white/[0.04] active:bg-white/[0.06]"
                      @click="onStatDeletedStatClick"
                      @keydown.enter.prevent="onStatDeletedStatClick"
                    >
                      <div class="flex items-center gap-1.5">
                        <span class="grid h-[18px] w-[18px] shrink-0 place-items-center" aria-hidden="true">
                          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-lime-400">
                            <circle cx="12" cy="12" r="10" />
                            <path d="m4.93 4.93 14.14 14.14" stroke-linecap="round" />
                          </svg>
                        </span>
                        <span class="text-[14px] font-extrabold tabular-nums leading-none text-white sm:text-[15px]">{{ statsCardDeleted }}</span>
                      </div>
                      <p class="mt-1 w-full text-[10px] font-medium leading-snug text-white/60 sm:text-[11px]">Удалено</p>
                      <p class="mt-0.5 line-clamp-2 w-full text-[9px] font-medium leading-snug text-lime-400/90 sm:text-[10px]">{{ statsCardTrendDeleted }}</p>
                    </div>

                    <div class="flex min-w-0 flex-[1_1_0] flex-col border-r border-white/10 px-1 py-1 sm:px-1.5">
                      <div class="flex items-center gap-1.5">
                        <span class="grid h-[18px] w-[18px] shrink-0 place-items-center" aria-hidden="true">
                          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-sky-400">
                            <circle cx="12" cy="12" r="10" />
                            <path d="M12 6v6l4 2" stroke-linecap="round" stroke-linejoin="round" />
                          </svg>
                        </span>
                        <span class="text-[14px] font-extrabold tabular-nums leading-none text-white sm:text-[15px]">{{ statsCardSavedHoursLabel }}</span>
                      </div>
                      <p class="mt-1 w-full text-[10px] font-medium leading-snug text-white/60 sm:text-[11px]">Сэкономлено</p>
                      <p class="mt-0.5 line-clamp-2 w-full text-[9px] font-medium leading-snug text-lime-400/90 sm:text-[10px]">{{ statsCardTrendSaved }}</p>
                    </div>

                    <div class="flex min-w-0 flex-[1_1_0] flex-col border-r border-white/10 px-1 py-1 sm:px-1.5">
                      <div class="flex items-center gap-1.5">
                        <span class="grid h-[18px] w-[18px] shrink-0 place-items-center" aria-hidden="true">
                          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-violet-400">
                            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                            <circle cx="9" cy="7" r="4" />
                            <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
                          </svg>
                        </span>
                        <span class="text-[14px] font-extrabold tabular-nums leading-none text-white sm:text-[15px]">{{ statsCardJoins }}</span>
                      </div>
                      <p class="mt-1 w-full text-[10px] font-medium leading-snug text-white/60 sm:text-[11px]">Вступили</p>
                      <p class="mt-0.5 line-clamp-2 w-full text-[9px] font-medium leading-snug text-lime-400/90 sm:text-[10px]">{{ statsCardTrendJoins }}</p>
                    </div>

                    <div class="flex min-w-0 flex-[1_1_0] flex-col py-1 pl-1 sm:pl-1.5">
                      <div class="flex items-center gap-1.5">
                        <span class="grid h-[18px] w-[18px] shrink-0 place-items-center" aria-hidden="true">
                          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-amber-300">
                            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" stroke-linecap="round" stroke-linejoin="round" />
                          </svg>
                        </span>
                        <span class="text-[14px] font-extrabold tabular-nums leading-none text-white sm:text-[15px]">{{ statGroupsLimitPercent }}</span>
                      </div>
                      <p class="mt-1 w-full text-[10px] font-medium leading-snug text-white/60 sm:text-[11px]">Лимит групп</p>
                      <p class="mt-0.5 line-clamp-2 w-full text-[9px] font-medium leading-snug text-lime-400/90 sm:text-[10px]">{{ statGroupsLimitFoot }}</p>
                    </div>
                  </div>
                </div>
              </div>

              <div
                v-if="accountShowBroadcastMiniCard"
                class="w-1/2 shrink-0 pl-[3px]"
              >
                <div
                  class="overflow-hidden rounded-2xl border border-violet-500/35 bg-gradient-to-br from-[#151220] via-[#0c0a12] to-black shadow-[0_14px_40px_-20px_rgba(91,33,182,0.45)] ring-1 ring-inset ring-violet-400/10"
                >
                  <div class="flex items-start gap-1.5 px-1.5 pb-1 pt-1 sm:gap-2 sm:px-2 sm:pb-1 sm:pt-1.5">
                    <div
                      class="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-violet-500 via-violet-700 to-indigo-950 shadow-[0_0_16px_rgba(167,139,250,0.38)] sm:h-8 sm:w-8"
                      aria-hidden="true"
                    >
                      <NavIcon name="telegram" class="h-[17px] w-[17px] text-white drop-shadow-[0_1px_8px_rgba(255,255,255,0.35)]" />
                    </div>
                    <div class="min-w-0 flex-1">
                      <span class="text-[12px] font-extrabold leading-tight text-white sm:text-[13px]">Рассылки</span>
                      <p class="mt-0.5 line-clamp-2 text-[8px] leading-snug text-white/50 sm:text-[9px]">
                        Отправляйте сообщения во все ваши чаты за секунды
                      </p>
                    </div>
                    <span
                      class="inline-flex max-w-[46%] shrink-0 rounded-full bg-gradient-to-r from-fuchsia-500 via-violet-500 to-indigo-500 p-[1.5px] shadow-[0_0_16px_rgba(168,85,247,0.4)]"
                    >
                      <button
                        type="button"
                        data-no-swipe
                        class="flex min-w-0 items-center gap-0.5 rounded-full bg-gradient-to-b from-zinc-800 to-black px-2 py-1 text-[9px] font-bold leading-tight text-white ring-1 ring-inset ring-white/10 transition hover:brightness-110 active:scale-[0.98] sm:px-2.5 sm:text-[10px]"
                        @click.stop="goBroadcastMiniCreate"
                      >
                        <span class="truncate">Создать</span>
                        <span class="shrink-0 text-xs font-light text-violet-200/90" aria-hidden="true">›</span>
                      </button>
                    </span>
                  </div>
                  <div
                    class="mx-1 mb-0.5 mt-0 grid grid-cols-3 gap-0 divide-x divide-white/[0.08] rounded-lg bg-black/50 px-1 py-0.5 sm:mx-1.5 sm:px-1.5"
                  >
                    <div class="flex min-w-0 flex-col gap-0.5 px-1 py-0.5">
                      <div class="flex items-center gap-1">
                        <span class="grid h-5 w-5 shrink-0 place-items-center rounded-md bg-black/35" aria-hidden="true">
                          <NavIcon name="chats" class="h-3.5 w-3.5 text-white/85" />
                        </span>
                        <span class="text-[12px] font-extrabold tabular-nums leading-none text-white sm:text-[13px]">
                          {{ broadcastMiniLoading ? '…' : (broadcastMiniEligibleCount ?? '—') }}
                        </span>
                      </div>
                      <p class="w-full text-[8px] font-medium leading-tight text-white/48 sm:text-[9px]">Доступно чатов</p>
                    </div>
                    <div class="flex min-w-0 flex-col gap-0.5 px-1 py-0.5">
                      <div class="flex items-center gap-1">
                        <span class="grid h-5 w-5 shrink-0 place-items-center rounded-md bg-black/35" aria-hidden="true">
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-sky-300">
                            <path d="m22 2-7 20-4-9-9-4Z" stroke-linejoin="round" />
                          </svg>
                        </span>
                        <span class="text-[12px] font-extrabold tabular-nums leading-none text-white sm:text-[13px]">
                          {{ broadcastMiniLoading ? '…' : (broadcastMiniSentToday ?? '—') }}
                        </span>
                      </div>
                      <p class="w-full text-[8px] font-medium leading-tight text-white/48 sm:text-[9px]">Сколько отправлено сегодня</p>
                    </div>
                    <div class="flex min-w-0 flex-col gap-0.5 px-1 py-0.5">
                      <div class="flex items-center gap-1">
                        <span class="grid h-5 w-5 shrink-0 place-items-center rounded-md bg-black/35" aria-hidden="true">
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-violet-300">
                            <circle cx="12" cy="12" r="10" />
                            <path d="M12 6v6l4 2" stroke-linecap="round" stroke-linejoin="round" />
                          </svg>
                        </span>
                        <span class="text-[12px] font-extrabold tabular-nums leading-none text-white sm:text-[13px]">
                          {{ broadcastMiniLoading ? '…' : (broadcastMiniScheduledCount ?? 0) }}
                        </span>
                      </div>
                      <p class="w-full text-[8px] font-medium leading-tight text-white/48 sm:text-[9px]">Запланировано</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            </div>
          </div>

          <!-- Обновления ↔ Premium: справа, компактная карточка -->
          <div
            class="ml-auto mr-0 mt-1 w-[min(100%,15rem)] max-w-[15rem] overflow-hidden rounded-2xl bg-gradient-to-b from-[#100c08] to-[#050505] shadow-[0_14px_38px_-18px_rgba(245,158,11,0.35)] ring-1 ring-amber-400/35 sm:w-[min(100%,16rem)] sm:max-w-[16rem]"
          >
            <div
              class="flex items-center justify-center gap-2 border-b border-amber-500/15 bg-black/25 px-2 py-1.5 sm:gap-3 sm:px-2 sm:py-2"
            >
              <div class="flex min-w-0 flex-1 items-center justify-center gap-2 sm:gap-4">
                <button
                  type="button"
                  class="text-[11px] font-extrabold tracking-tight transition sm:text-[12px]"
                  :class="
                    homeUpdatesPremiumSlide === 0
                      ? 'text-amber-300 drop-shadow-[0_0_16px_rgba(252,211,77,0.35)]'
                      : 'text-white/38 hover:text-white/70'
                  "
                  @click="setUpdatesPremiumSlide(0)"
                >
                  Premium защита
                </button>
                <button
                  type="button"
                  class="text-[11px] font-extrabold tracking-tight transition sm:text-[12px]"
                  :class="
                    homeUpdatesPremiumSlide === 1
                      ? 'text-lime-400 drop-shadow-[0_0_16px_rgba(163,230,53,0.4)]'
                      : 'text-white/38 hover:text-white/70'
                  "
                  @click="setUpdatesPremiumSlide(1)"
                >
                  Обновления
                </button>
              </div>
            </div>
            <div class="min-h-[9rem] overflow-hidden px-0.5 pb-0.5 sm:min-h-[9.5rem]">
              <div
                class="flex w-[200%] transition-transform ease-out"
                :class="homeUpdatesPremiumInstant ? 'duration-0' : 'duration-500'"
                :style="{ transform: `translateX(-${homeUpdatesPremiumSlide * 50}%)` }"
              >
                <div class="w-1/2 shrink-0 p-2 sm:p-2.5">
                  <div
                    class="flex min-h-[7.5rem] flex-col rounded-xl bg-gradient-to-b from-[#161210] to-[#080705] p-2.5 shadow-[inset_0_1px_0_rgba(251,191,36,0.07),0_10px_28px_-14px_rgba(180,83,9,0.28)] sm:min-h-[8rem] sm:p-3"
                  >
                    <ul class="flex-1 space-y-1.5 text-[11px] leading-snug text-white/[0.92] sm:text-[12px]">
                      <li v-for="(line, i) in ACCOUNT_HOME_PREMIUM_BULLETS" :key="`prem-${i}`" class="flex gap-2">
                        <span class="shrink-0 font-semibold text-amber-400/95" aria-hidden="true">✓</span>
                        <span>{{ line }}</span>
                      </li>
                    </ul>
                    <div class="mt-2 w-full">
                      <button
                        v-if="!tariffIsPremium"
                        type="button"
                        class="flex w-full items-center justify-center gap-1.5 rounded-2xl bg-gradient-to-r from-amber-950 via-amber-600 to-yellow-300 px-3 py-2.5 text-[11px] font-extrabold leading-tight text-white shadow-[0_10px_34px_-10px_rgba(251,191,36,0.65),inset_0_1px_0_rgba(255,255,255,0.22)] ring-1 ring-amber-300/45 sm:text-[12px]"
                        @click="openBillingSection({ scrollPlans: true })"
                      >
                        <span aria-hidden="true">🛡</span>
                        Усилить защиту
                      </button>
                      <button
                        v-else
                        type="button"
                        class="flex w-full items-center justify-center gap-1.5 rounded-2xl bg-gradient-to-r from-amber-950 via-amber-500 to-yellow-200 px-3 py-2.5 text-[11px] font-extrabold leading-tight text-amber-950 shadow-[0_12px_40px_-12px_rgba(251,191,36,0.75),inset_0_1px_0_rgba(255,255,255,0.35)] ring-1 ring-amber-200/50 sm:text-[12px]"
                        @click="openBillingSection()"
                      >
                        <span aria-hidden="true">👑</span>
                        Продлить Premium
                      </button>
                    </div>
                  </div>
                </div>
                <div class="w-1/2 shrink-0 p-2 sm:p-2.5">
                  <ul class="space-y-1.5 text-[10px] leading-snug text-white/[0.88] sm:text-[11px]">
                    <li
                      v-for="s in updatesHomePreview"
                      :key="`upd-${s.key}`"
                      class="rounded-lg bg-white/[0.04] px-2 py-1 ring-1 ring-lime-400/12"
                    >
                      <p class="text-[9px] font-semibold text-lime-300/90">{{ formatUpdateMetaShort(s) }}</p>
                      <p class="mt-0.5 font-semibold leading-tight text-white">{{ s.headline }}</p>
                    </li>
                  </ul>
                  <div class="mt-2 border-t border-lime-400/12 pt-2">
                    <button
                      type="button"
                      class="flex w-full items-center justify-between gap-1 text-left text-[10px] font-semibold text-white/55 transition hover:text-white/90 sm:text-[11px]"
                      @click="showUpdatesRoadmapModal = true"
                    >
                      <span>Смотреть все обновления</span>
                      <span class="text-base font-light text-white/35" aria-hidden="true">›</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
          </template>
        </div>

      </div>

      <div v-if="dashboardSection === 'partner'" class="mt-1 space-y-3">
        <p class="text-center text-xl font-extrabold uppercase tracking-[0.03em] text-white">PARTNER</p>
        <div class="grid grid-cols-3 gap-2">
          <button
            type="button"
            class="rounded-xl border border-slate-700 bg-slate-800/90 px-1 py-1.5 text-center text-[12px] font-semibold text-slate-100"
            :class="partnerTab === 'balance' ? 'ring-1 ring-lime-400/70' : ''"
            @click="partnerTab = 'balance'"
          >
            <div class="mx-auto mb-1 inline-flex h-6 w-6 items-center justify-center rounded-full bg-white/10 text-white">
              <NavIcon name="billing" class="h-3.5 w-3.5" />
            </div>
            Баланс
          </button>
          <button
            type="button"
            class="rounded-xl border border-slate-700 bg-slate-800/90 px-1 py-1.5 text-center text-[12px] font-semibold text-slate-100"
            :class="partnerTab === 'refs' ? 'ring-1 ring-lime-400/70' : ''"
            @click="partnerTab = 'refs'; ensureReferralPeople()"
          >
            <div class="mx-auto mb-1 inline-flex h-6 w-6 items-center justify-center rounded-full bg-white/10 text-white">
              <NavIcon name="partner" class="h-3.5 w-3.5" />
            </div>
            <span class="whitespace-nowrap">Мои рефералы</span>
          </button>
          <button
            type="button"
            class="rounded-xl border border-slate-700 bg-slate-800/90 px-1 py-1.5 text-center text-[12px] font-semibold text-slate-100"
            :class="partnerTab === 'docs' ? 'ring-1 ring-lime-400/70' : ''"
            @click="partnerTab = 'docs'"
          >
            <div class="mx-auto mb-1 inline-flex h-6 w-6 items-center justify-center rounded-full bg-white/10 text-white">
              <NavIcon name="reports" class="h-3.5 w-3.5" />
            </div>
            Документация
          </button>
        </div>

        <div v-if="partnerLoading" class="py-3 text-center text-sm text-white/75">
          Секундочку…
        </div>
        <div v-else-if="partnerError" class="rounded-xl border border-rose-400/40 bg-rose-900/20 p-4 text-sm text-rose-200">
          {{ partnerError }}
        </div>
        <div v-else-if="partnerData && partnerTab === 'balance'" class="rounded-xl border border-slate-700 bg-slate-900/80 p-4 text-sm text-slate-200">
          <div class="space-y-1.5">
            <p>
              Доступ: ✅ {{ partnerData.access_label || '—' }}<br>
              ├ Осталось дней: <b>{{ partnerData.days_left ?? 0 }}</b><br>
              └ Активен до: <b>{{ partnerActiveUntilLabel }}</b>
            </p>
            <p>
              Баланс:<br>
              ├ AURUM: <b>{{ partnerAurumTokens }} ✨</b> (рассылки и ИИ)<br>
              └ Партнёрские: <b>{{ partnerBonusTokens }} ⚡</b> (1 ⚡ = 2 ₽)
            </p>
            <p class="text-xs leading-relaxed text-slate-400">
              AURUM пополняется подарком с Premium и покупкой пакетов. Партнёрские ⚡ можно перевести в AURUM кнопкой ниже.
              При рассылке списание идёт с AURUM.
            </p>
            <p v-if="partnerData.ref_link">
              Ваша партнерская ссылка:<br>
              └ <button type="button" class="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-xs text-left text-cyan-300" @click="copyPartnerLink">{{ partnerData.ref_link }}</button>
            </p>
            <p>
              Приглашенных людей:<br>
              └ Всего: <b>{{ partnerData.invited_count || 0 }}</b>, Оплачивают: <b>{{ partnerData.paid_count || 0 }}</b>
            </p>
          </div>
          <div class="mt-3 flex flex-wrap gap-2">
            <button type="button" class="guard-green-soft rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-60" :disabled="bonusTransferLoading" @click="transferPartnerBonusToAurum">
              Партнёрские → AURUM ✨
            </button>
            <button type="button" class="rounded-lg border border-sky-400/40 bg-sky-500/10 px-3 py-1.5 text-xs font-semibold text-sky-300" @click="sharePartnerLink">
              Поделиться
            </button>
          </div>
          <div class="mt-4 rounded-xl border border-slate-700 bg-slate-800/70 p-3">
            <p>Доступно к выводу: <b>{{ fmtAmount(partnerPayouts.available_rub || 0) }} ₽</b></p>
            <p class="mt-0.5">Ожидает разблокировки <span class="text-slate-400">(комиссии до ~7 дней после оплаты реферала)</span>: <b>{{ fmtAmount(partnerPayouts.pending_rub || 0) }} ₽</b></p>
            <p class="mt-0.5">В заявках: <b>{{ fmtAmount(partnerPayouts.reserved_rub || 0) }} ₽</b></p>
            <p class="mt-0.5">Уже выплачено: <b>{{ fmtAmount(partnerPayouts.paid_total_rub || 0) }} ₽</b></p>
            <p class="mt-0.5 text-xs text-slate-400">Курс партнерских токенов: 1 ⚡ = {{ fmtAmount(partnerPayouts.token_rub_rate || 2) }} ₽</p>
            <p class="mt-0.5 text-sm font-semibold text-amber-300">Минимум на вывод: {{ fmtAmount(partnerPayouts.min_payout_rub || 1500) }} ₽</p>
            <div class="mt-2 grid gap-2 sm:grid-cols-2">
              <input v-model="payoutAmountRub" type="number" min="0" step="1" placeholder="Сумма RUB" class="rounded-lg border border-slate-600 bg-slate-900 px-2.5 py-2 text-xs text-white">
              <select v-model="payoutMethod" class="rounded-lg border border-slate-600 bg-slate-900 px-2.5 py-2 text-xs text-white">
                <option value="sbp">СБП</option>
                <option value="card">Карта</option>
              </select>
              <input v-model="payoutRequisites" type="text" placeholder="Реквизиты (телефон/карта)" class="sm:col-span-2 rounded-lg border border-slate-600 bg-slate-900 px-2.5 py-2 text-xs text-white">
              <input v-model="payoutFullName" type="text" placeholder="ФИО получателя" class="sm:col-span-2 rounded-lg border border-slate-600 bg-slate-900 px-2.5 py-2 text-xs text-white">
            </div>
            <button type="button" class="mt-2 guard-green-soft rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-60" :disabled="payoutSubmitting || partnerPayoutsLoading" @click="submitPayoutRequest">
              Запросить вывод
            </button>
            <div v-if="(partnerPayouts.commissions || []).length" class="mt-3 rounded-lg border border-slate-700 bg-slate-900/70 p-2">
              <p class="text-[11px] font-semibold text-slate-300">Последние начисления:</p>
              <div v-for="c in (partnerPayouts.commissions || []).slice(0, 5)" :key="`pc-${c.id}`" class="mt-1 text-[11px] text-slate-300">
                L{{ c.level }} · +{{ fmtAmount(c.reward_amount_rub) }} ₽ · {{ c.status }}
              </div>
            </div>
          </div>
        </div>
        <div v-else-if="partnerData && partnerTab === 'refs'" class="space-y-2">
          <div class="rounded-3xl bg-white p-4 text-slate-900">
            <div class="grid grid-cols-2 gap-2 border-b border-slate-200 pb-2 text-center">
              <button
                type="button"
                class="pb-1 text-[15px] font-semibold"
                :class="refsMode === 'full' ? 'border-b-4 border-sky-500 text-sky-600' : 'text-slate-400'"
                @click="refsMode = 'full'"
              >
                Полный список
              </button>
              <button
                type="button"
                class="pb-1 text-[15px] font-semibold"
                :class="refsMode === 'active' ? 'border-b-4 border-sky-500 text-sky-600' : 'text-slate-400'"
                @click="refsMode = 'active'"
              >
                Самые активные
              </button>
            </div>

            <div v-if="referralPeopleLoading" class="py-4 text-center text-sm text-slate-500">
              Секундочку…
            </div>
            <div
              v-else-if="(refsMode === 'full' ? paidFullRefs : paidActiveRefs).length === 0"
              class="py-8 text-center text-[18px] font-medium text-slate-700"
            >
              Рефералы отсутствуют.
            </div>
            <div v-else class="mt-3 space-y-2">
              <div
                v-for="item in (refsMode === 'full' ? paidFullRefs : paidActiveRefs)"
                :key="`${refsMode}-${item.user_id}`"
                class="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"
              >
                <div class="flex items-center justify-between gap-2">
                  <p class="truncate text-sm font-semibold text-slate-900">{{ displayReferralName(item) }}</p>
                  <span class="text-xs font-semibold" :class="item.is_paid ? 'text-emerald-600' : 'text-slate-500'">
                    {{ item.is_paid ? 'Платит' : 'Без оплаты' }}
                  </span>
                </div>
                <p class="mt-0.5 text-xs text-slate-600">
                  Оплат: {{ item.payments_count || 0 }} · Токены ИИ: {{ item.tokens_purchased || 0 }} ⚡
                </p>
              </div>
            </div>
          </div>
        </div>
        <div v-else-if="partnerData && partnerTab === 'docs'" class="space-y-2">
          <div class="rounded-2xl border border-fuchsia-300/35 bg-white p-4 text-slate-900">
            <p class="text-lg font-extrabold text-[#4bbf67]">❓ Как работает партнерская программа?</p>
            <p class="mt-2 text-sm">
              Вы приглашаете пользователей по своей ссылке и получаете вознаграждение с их оплат.
              Программа трехуровневая:
            </p>
            <div class="mt-2 space-y-1 text-sm">
              <p><span class="inline-flex h-5 w-5 items-center justify-center rounded bg-slate-900 text-xs font-bold text-white">1</span> <b class="ml-1">Уровень:</b> 15%</p>
              <p><span class="inline-flex h-5 w-5 items-center justify-center rounded bg-slate-900 text-xs font-bold text-white">2</span> <b class="ml-1">Уровень:</b> 10%</p>
              <p><span class="inline-flex h-5 w-5 items-center justify-center rounded bg-slate-900 text-xs font-bold text-white">3</span> <b class="ml-1">Уровень:</b> 5%</p>
            </div>
            <p class="mt-2 text-sm text-slate-600">
              Выплаты выполняются вручную в RUB. Заявки принимаются раз в неделю (по понедельникам),
              чтобы снизить риск мошенничества.
            </p>
            <p class="mt-2 text-sm text-slate-700">
              💸 Вознаграждение начисляется за <b>оплату подписки</b> и за <b>покупку токенов ИИ</b>.
            </p>
            <p class="mt-1 text-sm text-slate-700">
              💱 Фиксированный курс: <b>1 партнерский токен = 2 ₽</b>.
            </p>
          </div>
          <div class="rounded-2xl border border-fuchsia-300/35 bg-white p-4 text-slate-900">
            <p class="text-lg font-extrabold text-[#4bbf67]">❓ Как начисляется вознаграждение?</p>
            <p class="mt-2 text-sm">
              Пример: ваш реферал 1-го уровня оплатил 10 000 ₽ — начисление 1 500 ₽.
              Если его реферал оплатил 10 000 ₽ — вам 1 000 ₽ (2-й уровень).
              На 3-м уровне — 500 ₽.
            </p>
            <p class="mt-2 text-sm italic text-slate-600">
              💡 Начисления за покупки токенов и подписок учитываются автоматически.
            </p>
            <div class="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
              <p class="text-sm font-semibold">Калькулятор примера</p>
              <input v-model="docsExampleSale" type="number" min="0" step="100" class="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm">
              <p class="mt-2 text-xs">Сумма оплаты: <b>{{ fmtAmount(docsCalc.amount) }} ₽</b></p>
              <p class="text-xs"><span class="inline-flex h-4 w-4 items-center justify-center rounded bg-slate-900 text-[10px] font-bold text-white">+</span> 1 уровень (15%): <b>{{ fmtAmount(docsCalc.l1) }} ₽</b></p>
              <p class="text-xs"><span class="inline-flex h-4 w-4 items-center justify-center rounded bg-slate-900 text-[10px] font-bold text-white">+</span> 2 уровень (10%): <b>{{ fmtAmount(docsCalc.l2) }} ₽</b></p>
              <p class="text-xs"><span class="inline-flex h-4 w-4 items-center justify-center rounded bg-slate-900 text-[10px] font-bold text-white">+</span> 3 уровень (5%): <b>{{ fmtAmount(docsCalc.l3) }} ₽</b></p>
              <p class="text-xs">Итого: <b>{{ fmtAmount(docsCalc.total) }} ₽</b></p>
            </div>
          </div>
          <div class="rounded-2xl border border-fuchsia-300/35 bg-white p-4 text-slate-900">
            <p class="text-lg font-extrabold text-[#4bbf67]">❓ Как вывести средства?</p>
            <ol class="mt-2 list-decimal space-y-1 pl-4 text-sm">
              <li>Укажите сумму и реквизиты (СБП или карта) в разделе Баланс.</li>
              <li>Отправьте заявку на вывод.</li>
              <li>После проверки администратор вручную переводит средства.</li>
              <li>После статуса «Выплачено» вы получите уведомление в личку.</li>
            </ol>
          </div>
          <div class="rounded-2xl border border-emerald-300/35 bg-white p-4 text-slate-900">
            <p class="text-lg font-extrabold text-[#4bbf67]">❓ За что начисляется вознаграждение?</p>
            <p class="mt-2 text-sm"><b>✅ Начисляется:</b> оплата подписки, покупка токенов ИИ.</p>
            <p class="mt-1 text-sm text-slate-700">
              ℹ️ В спорных или подозрительных случаях начисления могут быть пересмотрены администратором.
            </p>
          </div>
        </div>
      </div>

      <div
        v-if="dashboardSection === 'tokens'"
        :class="
          showPremiumTokenLanding
            ? 'relative mx-auto mt-1 w-full max-w-md text-white md:max-w-lg'
            : 'relative mt-1 overflow-hidden rounded-[1.1rem] border border-white/[0.14] bg-gradient-to-b from-zinc-900/55 via-zinc-950/85 to-black px-2.5 py-2.5 text-white shadow-[0_32px_90px_-36px_rgba(34,211,238,0.22)] ring-1 ring-inset ring-white/[0.06] backdrop-blur-2xl sm:rounded-[1.2rem] sm:px-3 sm:py-3'
        "
      >
        <template v-if="!showPremiumTokenLanding">
          <div
            class="pointer-events-none absolute -left-[20%] -top-[45%] h-[95%] w-[65%] rounded-full bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.16),transparent_58%)] opacity-50 blur-3xl"
            aria-hidden="true"
          />
          <div
            class="pointer-events-none absolute inset-0 bg-[linear-gradient(125deg,rgba(255,255,255,0.07)_0%,transparent_38%,rgba(255,255,255,0.04)_62%,transparent_100%)]"
            aria-hidden="true"
          />
        </template>
        <div
          :class="showPremiumTokenLanding ? 'relative z-10 space-y-3' : 'relative z-10 space-y-2'"
        >
          <div class="flex items-center justify-between gap-2">
            <h3 class="min-w-0 truncate text-[13px] font-semibold leading-tight tracking-tight text-white/95 sm:text-[14px]" />
            <div
              v-if="!showPremiumTokenLanding"
              class="flex shrink-0 items-center gap-1.5"
            >
              <div
                class="rounded-md border border-white/[0.1] bg-white/[0.05] px-1.5 py-0.5 text-right shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-md"
                title="Всего доступных токенов"
              >
                <p class="text-[8px] font-medium uppercase leading-none tracking-[0.12em] text-white/38">Всего</p>
                <p class="text-xs font-bold leading-tight tabular-nums text-lime-200">{{ totalTokens }}<span class="ml-px text-[9px]">⚡</span></p>
              </div>
              <div
                v-if="tariffIsPremium"
                :class="tokensInfoToolbarClass"
                role="group"
                aria-label="Справка по токенам и оплате"
              >
                <button
                  type="button"
                  :class="tokensInfoBtnClass"
                  title="Счета, AURUM и расход"
                  aria-label="Счета, AURUM и расход"
                  @click="showAurumTokensHelp"
                >i</button>
                <button
                  type="button"
                  :class="tokensInfoBtnClass"
                  title="Оплата пакетов и возвраты"
                  aria-label="Оплата пакетов и возвраты"
                  @click="openTokensCheckoutInfo"
                >i</button>
              </div>
              <button
                v-else
                type="button"
                :class="tokensInfoBtnClass"
                title="Что такое AURUM и как считаются токены"
                aria-label="Что такое AURUM и как считаются токены"
                @click="showAurumTokensHelp"
              >i</button>
            </div>
          </div>
          <p
            v-if="tariffIsPremium && Number(me?.broadcast_spend_tokens || 0) > 0"
            class="text-[9px] leading-tight text-amber-200/80"
          >
            Рассылки: −{{ fmtAmount(me.broadcast_spend_tokens) }} ⚡
          </p>

          <template v-if="!tariffIsPremium">
            <div
              class="rounded-xl border border-white/[0.1] bg-zinc-900/80 px-3 py-4 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-md"
            >
              <div class="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-black/35 ring-1 ring-white/10">
                <svg class="h-8 w-8 text-white/45" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path
                    d="M7 11V8a5 5 0 0 1 10 0v3"
                    stroke="currentColor"
                    stroke-width="1.6"
                    stroke-linecap="round"
                  />
                  <rect x="6" y="11" width="12" height="10" rx="2" stroke="currentColor" stroke-width="1.6" />
                  <circle cx="12" cy="16" r="1.2" fill="currentColor" />
                </svg>
              </div>
              <p class="text-[13px] font-semibold leading-tight text-white">Токены недоступны на Free-тарифе</p>
              <p class="mt-2 text-[11px] leading-snug text-white/55">
                Токены нужны для рассылок, автопостинга и других функций.
              </p>
            </div>
            <button
              type="button"
              class="relative w-full overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-white text-center shadow-[0_10px_32px_-6px_rgba(243,156,18,0.65),0_4px_16px_-4px_rgba(108,52,131,0.5),inset_0_1px_0_rgba(255,255,255,0.28)] transition active:scale-[0.99]"
              style="
                background: linear-gradient(
                  90deg,
                  #f39c12 0%,
                  #df5a3b 34%,
                  #b043cc 56%,
                  #5c2dc1 74%,
                  #2a1a83 100%
                );
              "
              @click="openBillingSection({ scrollLanding: true })"
            >
              Получить Premium
            </button>
            <ul class="space-y-2.5 pt-1 text-left text-[11px] leading-snug text-white/75">
              <li class="flex items-start gap-2.5">
                <span class="mt-0.5 inline-flex h-[1.375rem] w-[1.375rem] shrink-0 items-center justify-center" aria-hidden="true">
                  <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path
                      d="M7.5 11V8a4.5 4.5 0 0 1 9 0v3"
                      stroke="#ff9f1c"
                      stroke-width="1.85"
                      stroke-linecap="round"
                    />
                    <rect x="5.5" y="11" width="13" height="10.5" rx="2.2" stroke="#ff9f1c" stroke-width="1.85" />
                  </svg>
                </span>
                <span>Разблокируйте все возможности</span>
              </li>
              <li class="flex items-start gap-2.5">
                <span class="mt-0.5 inline-flex h-[1.375rem] w-[1.375rem] shrink-0 items-center justify-center" aria-hidden="true">
                  <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path
                      d="M13 2.25 5.25 13.25h5.35l-1.35 8.5 8.75-11.5H12.9L13 2.25z"
                      stroke="#5cff5c"
                      stroke-width="1.75"
                      stroke-linejoin="round"
                      stroke-linecap="round"
                    />
                  </svg>
                </span>
                <span>Делайте рассылки и автопостинг</span>
              </li>
              <li class="flex items-start gap-2.5">
                <span class="mt-0.5 inline-flex h-[1.375rem] w-[1.375rem] shrink-0 items-center justify-center" aria-hidden="true">
                  <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path
                      d="M5.5 12.5 10 17l8.5-10"
                      stroke="#4ade80"
                      stroke-width="2.35"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                  </svg>
                </span>
                <span>Привлекайте клиентов и зарабатывайте</span>
              </li>
            </ul>
          </template>
          <template v-else>
            <div
              v-if="showPremiumTokenLanding"
              ref="premiumTokenLandingRef"
              class="space-y-4"
            >
              <section
                class="relative overflow-hidden rounded-[1.125rem] border border-white/[0.14] bg-black px-4 py-6 text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] ring-1 ring-inset ring-white/[0.08]"
              >
                <div
                  class="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_50%_0%,rgba(251,191,36,0.1),transparent_52%)]"
                  aria-hidden="true"
                />
                <div class="relative z-[1] space-y-4">
                  <div>
                    <h4 ref="premiumTokenLandingTitleRef" class="text-center text-[17px] font-extrabold leading-tight text-white">AURUM — топливо для роста вашего сообщества</h4>
                    <p class="mx-auto mt-2 max-w-[20rem] text-center text-[12px] leading-snug text-white/65">
                      Токены дают возможность автоматизировать канал, делать рассылки и привлекать новых клиентов.
                    </p>
                    <img
                      :src="tokenLandingOrbitSrc"
                      alt="Схема возможностей токенов"
                      class="mx-auto mt-2.5 w-full max-w-[23rem] bg-transparent object-contain"
                      draggable="false"
                      @dragstart.prevent
                    >
                  </div>
                  <div class="rounded-xl border border-white/[0.1] bg-zinc-950/50 px-3 py-2.5">
                    <p class="text-[12px] font-bold text-white">Почему это выгодно?</p>
                    <ul class="mt-1.5 space-y-1.5 text-[12px] leading-snug text-white/82">
                      <li class="flex items-center gap-2"><span class="inline-flex h-4 w-4 items-center justify-center text-[15px] font-black leading-none text-lime-300 drop-shadow-[0_0_6px_rgba(163,230,53,0.85)]">✓</span><span>Экономите время — автоматизация рутины</span></li>
                      <li class="flex items-center gap-2"><span class="inline-flex h-4 w-4 items-center justify-center text-[15px] font-black leading-none text-lime-300 drop-shadow-[0_0_6px_rgba(163,230,53,0.85)]">✓</span><span>Увеличиваете охваты и вовлеченность</span></li>
                      <li class="flex items-center gap-2"><span class="inline-flex h-4 w-4 items-center justify-center text-[15px] font-black leading-none text-lime-300 drop-shadow-[0_0_6px_rgba(163,230,53,0.85)]">✓</span><span>Привлекаете новых клиентов и зарабатываете</span></li>
                      <li class="flex items-center gap-2"><span class="inline-flex h-4 w-4 items-center justify-center text-[15px] font-black leading-none text-lime-300 drop-shadow-[0_0_6px_rgba(163,230,53,0.85)]">✓</span><span>Платите только за результат</span></li>
                    </ul>
                  </div>
                  <div class="space-y-2">
                    <button
                      type="button"
                      class="relative w-full overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-white text-center shadow-[0_14px_42px_-14px_rgba(243,156,18,0.62),inset_0_1px_0_rgba(255,255,255,0.28)] transition active:scale-[0.99]"
                      style="background: linear-gradient(90deg, #f39c12 0%, #df5a3b 34%, #b043cc 56%, #5c2dc1 74%, #2a1a83 100%);"
                      @click="scrollToPremiumTokenPacks"
                    >
                      Выбрать пакет токенов
                    </button>
                    <button
                      type="button"
                      class="w-full text-center text-[13px] font-medium text-slate-300 underline decoration-slate-500 underline-offset-4 transition hover:text-white"
                      @click="scrollToTokenHowItWorks"
                    >
                      Как это работает
                    </button>
                  </div>
                </div>
              </section>

              <section
                ref="tokenLandingHowItWorksRef"
                class="scroll-mt-[4.5rem] relative overflow-hidden rounded-[1.125rem] border border-white/[0.14] bg-black px-4 py-6 text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] ring-1 ring-inset ring-white/[0.08]"
              >
                <div
                  class="pointer-events-none absolute -left-1/4 bottom-0 h-40 w-40 rounded-full bg-[radial-gradient(circle_at_center,rgba(167,139,250,0.1),transparent_60%)] blur-2xl"
                  aria-hidden="true"
                />
                <div
                  class="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_50%_100%,rgba(251,191,36,0.06),transparent_55%)]"
                  aria-hidden="true"
                />
                <div class="relative z-[1] space-y-4">
                  <div>
                    <h4 class="text-center text-[17px] font-extrabold leading-tight text-white">Токены = новые клиенты и больше продаж</h4>
                    <div
                      class="mt-2.5 divide-y divide-white/[0.07] rounded-xl border border-white/[0.1] bg-zinc-950/78 shadow-[0_0_36px_-10px_rgba(99,102,241,0.22),inset_0_1px_0_rgba(255,255,255,0.04)]"
                    >
                    <div class="flex items-start gap-2.5 px-2.5 py-2.5">
                      <div
                        class="mt-0.5 flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-[#3ec5ff] to-[#0d7bc4] shadow-[0_0_22px_-2px_rgba(34,158,217,0.95),inset_0_1px_0_rgba(255,255,255,0.35)] ring-2 ring-[#7dd8fc]/90"
                        aria-hidden="true"
                      >
                        <svg viewBox="0 0 24 24" class="h-8 w-8 text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.35)]" fill="none" aria-hidden="true">
                          <path
                            d="M21.5 4.8 18.4 19c-.2.9-.8 1.1-1.6.7l-4.4-3.2-2.1 2c-.2.2-.4.4-.9.4l.3-4.5 8.3-7.5c.4-.3-.1-.5-.5-.2l-10.2 6.4-4.4-1.4c-.9-.3-.9-.9.2-1.3L19.9 4c.8-.3 1.5.2 1.3.8z"
                            fill="currentColor"
                          />
                        </svg>
                      </div>
                      <div
                        class="min-w-0 flex-1 rounded-lg border border-sky-400/15 bg-black/58 px-2.5 py-2 shadow-[inset_0_0_28px_rgba(56,189,248,0.07),0_0_22px_-8px_rgba(56,189,248,0.2)]"
                      >
                        <p class="text-[12px] font-bold text-white">Рассылки по чатам</p>
                        <p class="mt-0.5 text-[11px] leading-snug text-white/70">Отправляйте рекламные предложения, акции и новости в активные чаты.</p>
                      </div>
                    </div>
                    <div class="flex items-start gap-2.5 px-2.5 py-2.5">
                      <div
                        class="mt-0.5 flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-[#e879f9] via-[#c026d3] to-[#7c3aed] shadow-[0_0_24px_-2px_rgba(192,38,211,0.9),inset_0_1px_0_rgba(255,255,255,0.32)] ring-2 ring-[#f0abfc]/85"
                        aria-hidden="true"
                      >
                        <svg viewBox="0 0 24 24" class="h-8 w-8 text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.35)]" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                          <rect x="5.4" y="3.9" width="13.2" height="16.2" rx="2.2" />
                          <path d="M8.3 7.7h7.4M8.3 10.4h6.2M8.3 13.1h6.9" stroke-width="1.4" />
                          <path d="M12 15.8v3.8M10.1 17.7h3.8" stroke-width="2.15" />
                        </svg>
                      </div>
                      <div
                        class="min-w-0 flex-1 rounded-lg border border-sky-400/15 bg-black/58 px-2.5 py-2 shadow-[inset_0_0_28px_rgba(56,189,248,0.07),0_0_22px_-8px_rgba(56,189,248,0.2)]"
                      >
                        <p class="text-[12px] font-bold text-white">Автопостинг в каналы</p>
                        <p class="mt-0.5 text-[11px] leading-snug text-white/70">Регулярные публикации привлекают новую аудиторию и удерживают старую.</p>
                      </div>
                    </div>
                    <div class="flex items-start gap-2.5 px-2.5 py-2.5">
                      <div
                        class="mt-0.5 flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-[#4ade80] via-[#22c55e] to-[#15803d] shadow-[0_0_24px_-2px_rgba(34,197,94,0.92),inset_0_1px_0_rgba(255,255,255,0.3)] ring-2 ring-[#86efac]/90"
                        aria-hidden="true"
                      >
                        <svg viewBox="0 0 24 24" class="h-8 w-8 text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.35)]" fill="none" aria-hidden="true">
                          <circle cx="8.8" cy="8.6" r="2.35" stroke="currentColor" stroke-width="1.85" />
                          <path d="M4.6 17.4a4.35 4.35 0 0 1 8.4 0" stroke="currentColor" stroke-width="1.85" stroke-linecap="round" />
                          <circle cx="16.2" cy="9.1" r="1.95" stroke="currentColor" stroke-width="1.85" />
                          <path d="M13.6 16.6a3.55 3.55 0 0 1 5.35 0.72" stroke="currentColor" stroke-width="1.85" stroke-linecap="round" />
                        </svg>
                      </div>
                      <div
                        class="min-w-0 flex-1 rounded-lg border border-sky-400/15 bg-black/58 px-2.5 py-2 shadow-[inset_0_0_28px_rgba(56,189,248,0.07),0_0_22px_-8px_rgba(56,189,248,0.2)]"
                      >
                        <p class="text-[12px] font-bold text-white">Привлечение клиентов</p>
                        <p class="mt-0.5 text-[11px] leading-snug text-white/70">Используйте рассылки и контент, чтобы превращать подписчиков в клиентов.</p>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="rounded-2xl border border-white/[0.08] bg-gradient-to-b from-zinc-900/82 to-black/95 px-3.5 py-3 shadow-[0_12px_32px_-16px_rgba(0,0,0,0.86)]">
                  <p class="text-center text-[16px] font-extrabold text-white">Как это работает</p>
                  <div class="mt-2.5 flex items-center justify-between gap-0.5">
                    <div class="flex min-w-0 flex-1 flex-col items-center gap-1.5 text-center">
                      <div class="flex h-[3.75rem] w-[3.75rem] items-center justify-center rounded-[1rem] border border-[#7dd8fc]/45 bg-gradient-to-br from-[#2fa8f0] via-[#1b8fe0] to-[#1464b8] shadow-[0_0_22px_-2px_rgba(56,189,248,0.95),inset_0_1px_0_rgba(255,255,255,0.26)]">
                        <svg viewBox="0 0 24 24" class="h-8 w-8 text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.25)]" fill="currentColor" aria-hidden="true">
                          <path d="M21.5 4.8 18.4 19c-.2.9-.8 1.1-1.6.7l-4.4-3.2-2.1 2c-.2.2-.4.4-.9.4l.3-4.5 8.3-7.5c.4-.3-.1-.5-.5-.2l-10.2 6.4-4.4-1.4c-.9-.3-.9-.9.2-1.3L19.9 4c.8-.3 1.5.2 1.3.8z" />
                        </svg>
                      </div>
                      <p class="text-[10px] font-semibold leading-tight text-white">Рассылка</p>
                    </div>
                    <span class="pb-6 text-[26px] font-black leading-none text-white/90">→</span>
                    <div class="flex min-w-0 flex-1 flex-col items-center gap-1.5 text-center">
                      <div class="flex h-[3.75rem] w-[3.75rem] items-center justify-center rounded-[1rem] border border-[#d8b4fe]/45 bg-gradient-to-br from-[#7e3af2] via-[#6d28d9] to-[#4c1d95] shadow-[0_0_22px_-2px_rgba(168,85,247,0.92),inset_0_1px_0_rgba(255,255,255,0.2)]">
                        <svg viewBox="0 0 24 24" class="h-8 w-8 text-[#f5ecff] drop-shadow-[0_1px_2px_rgba(0,0,0,0.25)]" fill="none" aria-hidden="true">
                          <path
                            d="M6.4 7.8h11.2a2.05 2.05 0 0 1 2.05 2.05v5.9a2.05 2.05 0 0 1-2.05 2.05h-4.1l-3.1 2.55v-2.55H6.4a2.05 2.05 0 0 1-2.05-2.05V9.85A2.05 2.05 0 0 1 6.4 7.8z"
                            stroke="currentColor"
                            stroke-width="1.75"
                            stroke-linejoin="round"
                          />
                          <path d="M8.6 11.4h7M8.6 13.8h4.6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
                        </svg>
                      </div>
                      <p class="text-[10px] font-semibold leading-tight text-white">Отклики</p>
                    </div>
                    <span class="pb-6 text-[26px] font-black leading-none text-white/90">→</span>
                    <div class="flex min-w-0 flex-1 flex-col items-center gap-1.5 text-center">
                      <div class="flex h-[3.75rem] w-[3.75rem] items-center justify-center rounded-[1rem] border border-[#fcd34d]/45 bg-gradient-to-br from-[#f59e0b] via-[#d97706] to-[#92400e] shadow-[0_0_22px_-2px_rgba(245,158,11,0.88),inset_0_1px_0_rgba(255,255,255,0.2)]">
                        <svg viewBox="0 0 24 24" class="h-8 w-8 text-[#fff4cf] drop-shadow-[0_1px_2px_rgba(0,0,0,0.25)]" fill="none" aria-hidden="true">
                          <circle cx="9" cy="9" r="2.35" stroke="currentColor" stroke-width="1.75" />
                          <path d="M4.8 17.7a4.2 4.2 0 0 1 8.2 0" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" />
                          <circle cx="16.5" cy="9.2" r="1.95" stroke="currentColor" stroke-width="1.75" />
                          <path d="M13.7 17a3.6 3.6 0 0 1 5.4.7" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" />
                        </svg>
                      </div>
                      <p class="text-[10px] font-semibold leading-tight text-white">Клиенты</p>
                    </div>
                    <span class="pb-6 text-[26px] font-black leading-none text-amber-300">→</span>
                    <div class="flex min-w-0 flex-1 flex-col items-center gap-1.5 text-center">
                      <div class="flex h-[3.75rem] w-[3.75rem] items-center justify-center rounded-[1rem] border border-[#a3e635]/45 bg-gradient-to-br from-[#65a30d] via-[#4d7c0f] to-[#365314] shadow-[0_0_22px_-2px_rgba(132,204,22,0.9),inset_0_1px_0_rgba(255,255,255,0.2)]">
                        <svg viewBox="0 0 24 24" class="h-8 w-8 text-[#d9f99d] drop-shadow-[0_1px_2px_rgba(0,0,0,0.25)]" fill="none" aria-hidden="true">
                          <path d="M4.2 18.6h15.6" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" />
                          <rect x="5.4" y="12.4" width="3.1" height="6.2" rx="0.55" fill="currentColor" />
                          <rect x="10.45" y="9.2" width="3.1" height="9.4" rx="0.55" fill="currentColor" />
                          <rect x="15.5" y="5.6" width="3.1" height="13" rx="0.55" fill="currentColor" />
                        </svg>
                      </div>
                      <p class="text-[10px] font-semibold leading-tight text-white">Прибыль</p>
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  class="mt-2 w-full rounded-[1.05rem] border border-[#f6cc55]/75 bg-gradient-to-b from-[#ffd94a] via-[#f2b705] to-[#a96a00] px-4 py-2 text-center text-[17px] font-black tracking-tight text-black shadow-[0_18px_30px_-14px_rgba(235,160,0,0.96),0_0_28px_-10px_rgba(255,190,0,0.72),inset_0_1px_0_rgba(255,237,176,0.5),inset_0_-9px_14px_rgba(107,63,0,0.45)] transition active:scale-[0.99]"
                  @click="scrollToPremiumTokenPacks({ reloadPacks: false })"
                >
                  ⚡ Запустить рассылку
                </button>
                <p class="mt-2 text-center text-[13px] font-extrabold text-amber-300">Следите за обновлениями!</p>
                </div>
              </section>

              <section
                ref="tokenLandingPackChoiceRef"
                class="scroll-mt-[5.75rem] relative overflow-hidden rounded-[1.125rem] border border-white/[0.14] bg-black px-4 py-6 text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] ring-1 ring-inset ring-white/[0.08]"
              >
                <div v-if="tokenPacksLoading" class="py-4 text-center text-[11px] text-white/45">Загрузка…</div>
                <div v-else class="space-y-2">
                  <h4
                    ref="tokenLandingPackChoiceTitleRef"
                    class="scroll-mt-[5.75rem] text-center text-[16px] font-extrabold tracking-tight text-white"
                  >Выбор пакета</h4>
                  <div
                    v-if="tokenPacksError"
                    class="rounded-xl border border-red-400/40 bg-red-950/40 px-2.5 py-2.5 text-[11px] leading-snug text-red-100/95"
                  >
                    <p>{{ tokenPacksError }}</p>
                    <button
                      type="button"
                      class="mt-2 w-full rounded-lg border border-white/15 bg-white/10 py-2 text-[12px] font-semibold text-white transition hover:bg-white/14"
                      @click="loadTokenPacksFromApi"
                    >
                      Обновить
                    </button>
                  </div>
                  <div
                    v-else-if="!tokenPacks.length"
                    class="rounded-xl border border-white/[0.1] bg-zinc-900/70 px-2.5 py-3 text-center text-[11px] leading-snug text-white/60"
                  >
                    Каталог пакетов пуст. Проверьте соединение или обновите список.
                    <button
                      type="button"
                      class="mt-2 w-full rounded-lg border border-white/15 bg-white/10 py-2 text-[12px] font-semibold text-white transition hover:bg-white/14"
                      @click="loadTokenPacksFromApi"
                    >
                      Обновить
                    </button>
                  </div>
                  <div v-else class="space-y-0">
                    <div class="grid grid-cols-2 gap-2.5">
                      <button
                        v-for="pack in displayedTokenPacks"
                        :key="`tpl-${pack.tokens}`"
                        type="button"
                        class="relative flex min-h-[9.25rem] flex-col items-stretch rounded-xl border px-2 pb-2 pt-2 text-center transition active:scale-[0.99] disabled:opacity-55"
                        :class="
                          selectedTokenPack !== null && Number(selectedTokenPack) === Number(pack.tokens)
                            ? 'border-amber-400/80 bg-amber-500/10 ring-2 ring-amber-400/45'
                            : 'border-white/10 bg-zinc-950/90 hover:border-white/20'
                        "
                        :disabled="payLoadingTokenPack !== null"
                        @click="selectTokenPack(pack.tokens)"
                      >
                        <span
                          v-if="pack.discount_label"
                          class="absolute right-1 top-1 z-[1] max-w-[calc(100%-0.5rem)] truncate rounded bg-violet-600 px-1 py-px text-[8px] font-extrabold leading-tight text-white"
                        >{{ pack.discount_label }}</span>
                        <div
                          class="flex min-h-0 w-full flex-1 flex-col items-center justify-center gap-1.5 px-0.5 py-1 text-center"
                        >
                          <span class="block w-full text-xl font-extrabold tabular-nums tracking-tight text-white sm:text-2xl">
                            {{ Math.round(Number(pack.price_rub || 0)) }} ₽
                          </span>
                          <span class="block w-full text-sm font-semibold tabular-nums text-amber-200/95 sm:text-base">
                            +{{ pack.tokens }}
                            <span class="inline-block translate-y-px text-amber-300" aria-hidden="true">⚡</span>
                          </span>
                        </div>
                        <span
                          v-if="pack.tag"
                          class="mt-auto shrink-0 rounded-full bg-emerald-500/20 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-emerald-300"
                        >{{ pack.tag }}</span>
                        <p
                          v-if="payLoadingTokenPack === pack.tokens"
                          class="absolute inset-x-0 bottom-1 text-center text-[8px] font-medium text-cyan-300/95"
                        >…</p>
                      </button>
                    </div>
                    <button
                      v-if="hasHiddenTokenPacks"
                      type="button"
                      class="mt-3 w-full py-2 text-center text-[13px] font-medium text-slate-400 underline decoration-slate-600 underline-offset-4 transition hover:text-slate-300"
                      @click="showAllTokenPacks = !showAllTokenPacks"
                    >
                      {{ showAllTokenPacks ? 'Скрыть дополнительные пакеты' : 'Показать ещё пакеты' }}
                    </button>
                  </div>
                </div>
                <button
                  v-if="tokenPacks.length"
                  type="button"
                  class="relative mt-2 w-full overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-white text-center shadow-[0_14px_42px_-14px_rgba(243,156,18,0.62),inset_0_1px_0_rgba(255,255,255,0.28)] transition active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-45"
                  style="background: linear-gradient(90deg, #f39c12 0%, #df5a3b 34%, #b043cc 56%, #5c2dc1 74%, #2a1a83 100%);"
                  :disabled="selectedTokenPack === null || payLoadingTokenPack !== null"
                  @click="continueTokenPackCheckout"
                >
                  {{ payLoadingTokenPack !== null ? 'Готовим оплату...' : 'Продолжить' }}
                </button>
                <button
                  v-if="tokenPacks.length"
                  type="button"
                  class="mt-2 w-full py-2 text-center text-[13px] font-medium text-slate-400 underline decoration-slate-500 underline-offset-4 transition hover:text-slate-300"
                  @click="openPromoCodeModal"
                >
                  Есть промокод?
                </button>
                <div
                  v-if="me?.is_admin"
                  class="flex flex-wrap items-center gap-x-1.5 gap-y-1 rounded-lg border border-amber-400/22 bg-amber-500/[0.05] px-1.5 py-1 backdrop-blur-xl"
                >
                  <span class="text-[9px] font-semibold uppercase tracking-wide text-amber-200/90">Тест</span>
                  <button
                    type="button"
                    :class="tokensInfoBtnAmberClass"
                    title="Тестовая оплата для администраторов"
                    aria-label="Тестовая оплата для администраторов"
                    @click="openTokensAdminTestInfo"
                  >i</button>
                  <div class="flex min-w-0 flex-1 flex-wrap gap-0.5">
                    <button
                      v-for="pack in tokenPacks"
                      :key="`ttpl-${pack.tokens}`"
                      type="button"
                      class="rounded-md border border-amber-500/30 bg-black/22 px-1.5 py-0.5 text-[9px] font-bold tabular-nums text-amber-100 backdrop-blur-md disabled:opacity-50"
                      :disabled="testTokenPayLoading"
                      @click="buyTokenPackAdminTest(pack.tokens)"
                    >
                      {{ pack.tokens }}
                    </button>
                  </div>
                </div>
              </section>
              <section
                class="relative overflow-hidden rounded-[1.125rem] border border-white/[0.14] bg-black px-4 py-3 text-center text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] ring-1 ring-inset ring-white/[0.08]"
              >
                <p class="text-[10px] font-medium text-white/45">© {{ new Date().getFullYear() }} AI Guard. Все права защищены.</p>
                <p class="mt-1 text-[10px] text-white/38">Соцсети: Telegram · VK · YouTube</p>
              </section>
            </div>

            <div v-if="!showPremiumTokenLanding && tokenPacksLoading" class="py-4 text-center text-[11px] text-white/45">Загрузка…</div>
            <div
              v-else-if="!showPremiumTokenLanding"
              ref="premiumTokenPacksRef"
              class="mt-1 space-y-2"
            >
              <h4 class="text-center text-[16px] font-extrabold tracking-tight text-white">Выбор пакета</h4>
              <div
                v-if="tokenPacksError"
                class="rounded-xl border border-red-400/40 bg-red-950/40 px-2.5 py-2.5 text-[11px] leading-snug text-red-100/95"
              >
                <p>{{ tokenPacksError }}</p>
                <button
                  type="button"
                  class="mt-2 w-full rounded-lg border border-white/15 bg-white/10 py-2 text-[12px] font-semibold text-white transition hover:bg-white/14"
                  @click="loadTokenPacksFromApi"
                >
                  Обновить
                </button>
              </div>
              <div
                v-else-if="!tokenPacks.length"
                class="rounded-xl border border-white/[0.1] bg-zinc-900/70 px-2.5 py-3 text-center text-[11px] leading-snug text-white/60"
              >
                Каталог пакетов пуст. Проверьте соединение или обновите список.
                <button
                  type="button"
                  class="mt-2 w-full rounded-lg border border-white/15 bg-white/10 py-2 text-[12px] font-semibold text-white transition hover:bg-white/14"
                  @click="loadTokenPacksFromApi"
                >
                  Обновить
                </button>
              </div>
              <div v-else class="space-y-0">
                <div class="grid grid-cols-2 gap-2.5">
                  <button
                    v-for="pack in displayedTokenPacks"
                    :key="`tp-${pack.tokens}`"
                    type="button"
                    class="relative flex min-h-[9.25rem] flex-col items-stretch rounded-xl border px-2 pb-2 pt-2 text-center transition active:scale-[0.99] disabled:opacity-55"
                    :class="
                      selectedTokenPack !== null && Number(selectedTokenPack) === Number(pack.tokens)
                        ? 'border-amber-400/80 bg-amber-500/10 ring-2 ring-amber-400/45'
                        : 'border-white/10 bg-zinc-950/90 hover:border-white/20'
                    "
                    :disabled="payLoadingTokenPack !== null"
                    @click="selectTokenPack(pack.tokens)"
                  >
                    <span
                      v-if="pack.discount_label"
                      class="absolute right-1 top-1 z-[1] max-w-[calc(100%-0.5rem)] truncate rounded bg-violet-600 px-1 py-px text-[8px] font-extrabold leading-tight text-white"
                    >{{ pack.discount_label }}</span>
                    <div
                      class="flex min-h-0 w-full flex-1 flex-col items-center justify-center gap-1.5 px-0.5 py-1 text-center"
                    >
                      <span class="block w-full text-xl font-extrabold tabular-nums tracking-tight text-white sm:text-2xl">
                        {{ Math.round(Number(pack.price_rub || 0)) }} ₽
                      </span>
                      <span class="block w-full text-sm font-semibold tabular-nums text-amber-200/95 sm:text-base">
                        +{{ pack.tokens }}
                        <span class="inline-block translate-y-px text-amber-300" aria-hidden="true">⚡</span>
                      </span>
                    </div>
                    <span
                      v-if="pack.tag"
                      class="mt-auto shrink-0 rounded-full bg-emerald-500/20 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-emerald-300"
                    >{{ pack.tag }}</span>
                    <p
                      v-if="payLoadingTokenPack === pack.tokens"
                      class="absolute inset-x-0 bottom-1 text-center text-[8px] font-medium text-cyan-300/95"
                    >…</p>
                  </button>
                </div>
                <button
                  v-if="hasHiddenTokenPacks"
                  type="button"
                  class="mt-3 w-full py-2 text-center text-[13px] font-medium text-slate-400 underline decoration-slate-600 underline-offset-4 transition hover:text-slate-300"
                  @click="showAllTokenPacks = !showAllTokenPacks"
                >
                  {{ showAllTokenPacks ? 'Скрыть дополнительные пакеты' : 'Показать ещё пакеты' }}
                </button>
              </div>
            </div>
            <button
              v-if="!showPremiumTokenLanding && tokenPacks.length"
              type="button"
              class="relative mt-2 w-full overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-white text-center shadow-[0_14px_42px_-14px_rgba(243,156,18,0.62),inset_0_1px_0_rgba(255,255,255,0.28)] transition active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-45"
              style="background: linear-gradient(90deg, #f39c12 0%, #df5a3b 34%, #b043cc 56%, #5c2dc1 74%, #2a1a83 100%);"
              :disabled="selectedTokenPack === null || payLoadingTokenPack !== null"
              @click="continueTokenPackCheckout"
            >
              {{ payLoadingTokenPack !== null ? 'Готовим оплату...' : 'Продолжить' }}
            </button>
            <button
              v-if="!showPremiumTokenLanding && tokenPacks.length"
              type="button"
              class="mt-2 w-full py-2 text-center text-[13px] font-medium text-slate-400 underline decoration-slate-500 underline-offset-4 transition hover:text-slate-300"
              @click="openPromoCodeModal"
            >
              Есть промокод?
            </button>
            <div
              v-if="!showPremiumTokenLanding && me?.is_admin"
              class="flex flex-wrap items-center gap-x-1.5 gap-y-1 rounded-lg border border-amber-400/22 bg-amber-500/[0.05] px-1.5 py-1 backdrop-blur-xl"
            >
              <span class="text-[9px] font-semibold uppercase tracking-wide text-amber-200/90">Тест</span>
              <button
                type="button"
                :class="tokensInfoBtnAmberClass"
                title="Тестовая оплата для администраторов"
                aria-label="Тестовая оплата для администраторов"
                @click="openTokensAdminTestInfo"
              >i</button>
              <div class="flex min-w-0 flex-1 flex-wrap gap-0.5">
                <button
                  v-for="pack in tokenPacks"
                  :key="`ttp-${pack.tokens}`"
                  type="button"
                  class="rounded-md border border-amber-500/30 bg-black/22 px-1.5 py-0.5 text-[9px] font-bold tabular-nums text-amber-100 backdrop-blur-md disabled:opacity-50"
                  :disabled="testTokenPayLoading"
                  @click="buyTokenPackAdminTest(pack.tokens)"
                >
                  {{ pack.tokens }}
                </button>
              </div>
            </div>
          </template>
        </div>
      </div>

      <div
        v-if="dashboardSection === 'billing'"
        class="mx-auto mt-1 w-full max-w-md space-y-4 md:max-w-lg"
      >
        <!-- Лендинг тарифов: узкая колонка как в телефоне, на десктопе то же визуально; Free — только после /me и без подписки -->
        <section
            v-if="me && !me.is_premium"
            id="billing-free-limits"
            class="relative overflow-hidden rounded-[1.125rem] border border-violet-500/30 bg-black px-4 py-6 text-white shadow-[0_0_48px_-18px_rgba(124,58,237,0.45)] ring-1 ring-inset ring-violet-500/15"
          >
            <div
              class="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_50%_0%,rgba(139,92,246,0.22),transparent_55%)]"
              aria-hidden="true"
            />
            <div class="relative z-[1] flex flex-col items-center">
              <div
                class="flex h-[4.25rem] w-[4.25rem] items-center justify-center rounded-full border-2 border-violet-400/55 bg-gradient-to-b from-violet-950/90 to-black text-[2rem] shadow-[0_0_36px_rgba(167,139,250,0.65)]"
                aria-hidden="true"
              >
                🔒
              </div>
              <p class="mt-5 text-center text-[11px] font-extrabold uppercase tracking-[0.22em] text-violet-300">
                Ограничения Free
              </p>
              <p class="mt-2 max-w-[19rem] text-center text-[13px] leading-relaxed text-slate-400">
                Вы используете бесплатный тариф. Некоторые функции недоступны в Free версии
              </p>
              <ul class="mt-5 w-full max-w-md space-y-3 rounded-2xl border border-white/[0.08] bg-zinc-950/90 px-4 py-4">
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="mt-0.5 shrink-0 text-violet-400" aria-hidden="true">🔒</span>
                  Автоудаление спама
                </li>
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="mt-0.5 shrink-0 text-violet-400" aria-hidden="true">🔒</span>
                  Фильтр ссылок и упоминаний
                </li>
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="mt-0.5 shrink-0 text-violet-400" aria-hidden="true">🔒</span>
                  Рассылки по чатам и каналам
                </li>
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="mt-0.5 shrink-0 text-violet-400" aria-hidden="true">🔒</span>
                  Расширенная статистика
                </li>
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="mt-0.5 shrink-0 text-amber-400/95 drop-shadow-[0_0_8px_rgba(251,191,36,0.45)]" aria-hidden="true">🔒</span>
                  Приоритетная поддержка
                </li>
              </ul>
              <button
                type="button"
                class="mt-6 w-full max-w-md rounded-2xl bg-violet-600 py-3.5 text-[15px] font-bold text-white shadow-[0_12px_32px_-8px_rgba(124,58,237,0.55)] transition hover:bg-violet-500 active:scale-[0.99]"
                @click="scrollToBillingPremiumPitch"
              >
                Подробнее о Premium
              </button>
            </div>
          </section>

          <!-- 2. Экран Premium -->
          <section
            id="billing-premium-pitch"
            ref="billingPremiumPitchRef"
            class="relative overflow-hidden rounded-[1.125rem] border border-amber-500/25 bg-black px-4 py-6 text-white ring-1 ring-inset ring-amber-500/10"
          >
            <div
              class="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_50%_0%,rgba(251,191,36,0.12),transparent_50%)]"
              aria-hidden="true"
            />
            <div class="relative z-[1]">
              <div class="flex items-center justify-center gap-2">
                <span class="text-xl leading-none" aria-hidden="true">👑</span>
                <span class="text-[15px] font-bold tracking-tight text-white">Premium</span>
              </div>
              <p class="mt-4 text-center text-[1.05rem] font-bold leading-snug text-amber-300 sm:text-lg">
                Раскройте полный потенциал Guard
              </p>
              <p class="mx-auto mt-2 max-w-[20rem] text-center text-[13px] leading-relaxed text-slate-400">
                Больше защиты, больше функций, больше возможностей для роста
              </p>
              <ul class="mx-auto mt-5 max-w-md space-y-3">
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-500/15 text-sm text-amber-300" aria-hidden="true">✦</span>
                  Чистый чат без спама 24/7
                </li>
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-500/15 text-sm text-amber-300" aria-hidden="true">✦</span>
                  Автоматическое удаление
                </li>
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-500/15 text-sm text-amber-300" aria-hidden="true">✦</span>
                  Рассылки и автопостинг
                </li>
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-500/15 text-sm text-amber-300" aria-hidden="true">✦</span>
                  Расширенная аналитика
                </li>
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-500/15 text-sm text-amber-300" aria-hidden="true">✦</span>
                  Приоритетная поддержка
                </li>
              </ul>
              <button
                type="button"
                class="relative mx-auto mt-6 flex w-full max-w-md items-center justify-center overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-white text-center shadow-[0_14px_42px_-14px_rgba(243,156,18,0.62),inset_0_1px_0_rgba(255,255,255,0.28)] transition active:scale-[0.99]"
                style="background: linear-gradient(90deg, #f39c12 0%, #df5a3b 34%, #b043cc 56%, #5c2dc1 74%, #2a1a83 100%);"
                @click="scrollToBillingLandingPlans"
              >
                Выбрать тариф
              </button>
              <button
                type="button"
                class="mt-3 w-full py-2 text-center text-[13px] font-medium text-slate-500 underline decoration-slate-600 underline-offset-4 transition hover:text-slate-400"
                @click="scrollToBillingPremiumCompare"
              >
                Сравнить тарифы
              </button>
            </div>
          </section>

          <!-- 3. Сравнение тарифов -->
          <section
            id="billing-premium-compare"
            ref="billingPremiumCompareRef"
            class="scroll-mt-3 relative overflow-hidden rounded-[1.125rem] border border-violet-500/25 bg-black px-4 py-6 text-white shadow-[0_0_48px_-12px_rgba(139,92,246,0.35)] ring-1 ring-inset ring-white/[0.06]"
          >
            <div
              class="pointer-events-none absolute -right-1/4 top-0 h-48 w-48 rounded-full bg-[radial-gradient(circle_at_center,rgba(250,204,21,0.1),transparent_65%)] blur-2xl"
              aria-hidden="true"
            />
            <div
              class="pointer-events-none absolute -left-1/4 bottom-0 h-40 w-40 rounded-full bg-[radial-gradient(circle_at_center,rgba(167,139,250,0.18),transparent_60%)] blur-2xl"
              aria-hidden="true"
            />
            <div class="relative z-[1]">
              <h2 class="text-center text-lg font-extrabold tracking-tight text-white sm:text-xl">
                Сравнение тарифов
              </h2>

              <div
                class="mt-5 flex items-stretch gap-1 rounded-2xl border border-white/[0.1] bg-zinc-950/90 p-1 shadow-inner"
                role="presentation"
              >
                <div class="flex flex-1 items-center justify-center rounded-xl border border-transparent py-3">
                  <span class="text-xs font-bold uppercase tracking-[0.2em] text-violet-300/90">Free</span>
                </div>
                <div
                  class="flex w-12 shrink-0 flex-col items-center justify-center rounded-xl border border-white/[0.08] bg-black/50 py-2"
                  aria-hidden="true"
                >
                  <span class="text-xl leading-none text-violet-300/90">🛡</span>
                </div>
                <div
                  class="flex flex-[1.12] flex-col items-center justify-center rounded-xl border-2 border-amber-400/75 bg-gradient-to-b from-amber-500/12 to-violet-950/40 py-2.5 shadow-[0_0_24px_-6px_rgba(251,191,36,0.35)]"
                >
                  <span class="text-xs font-extrabold uppercase tracking-[0.18em] text-amber-200">Premium</span>
                </div>
              </div>

              <div
                class="mt-4 overflow-x-auto overflow-y-hidden rounded-xl border border-white/[0.08] bg-black/60"
              >
                <!-- Free и Premium: равные доли остатка ширины (1fr + 1fr), чтобы внутри было больше места для подписи внизу -->
                <div
                  class="grid w-full min-w-0 grid-cols-[minmax(0,auto)_minmax(0,1fr)_minmax(0,1fr)] justify-items-stretch gap-x-1.5 sm:gap-x-2"
                >
                <span
                  class="min-w-0 border-b border-white/[0.08] bg-white/[0.03] py-2.5 pl-2 pr-1.5 text-[10px] font-bold uppercase tracking-wide text-slate-500 sm:pl-2.5"
                >Функция</span>
                <span
                  class="flex min-w-0 items-center justify-center border-b border-l border-white/[0.08] bg-white/[0.03] px-1.5 py-2.5 text-center text-[10px] font-bold uppercase text-violet-300/85"
                >Free</span>
                <span
                  class="flex min-w-0 flex-col items-center justify-center border-b border-l border-amber-400/40 bg-amber-500/[0.1] px-1.5 py-2 text-[10px] font-bold uppercase text-amber-100/95"
                >
                  <span class="leading-none">👑</span>
                  <span class="mt-0.5">Premium</span>
                </span>
                <template
                  v-for="(row, idx) in billingCompareRows"
                  :key="row.id"
                >
                  <template v-if="row.kind === 'referral'">
                    <span
                      class="min-w-0 border-b border-white/[0.06] py-2.5 pl-2 pr-1.5 text-[12px] leading-snug text-slate-200 sm:pl-2.5"
                      :class="idx % 2 === 1 ? 'bg-white/[0.02]' : 'bg-white/[0.01]'"
                    >{{ row.label }}</span>
                    <div
                      class="flex min-w-0 flex-col items-center justify-center border-b border-l border-white/[0.06] px-1.5 py-2.5 text-center"
                      :class="idx % 2 === 1 ? 'bg-white/[0.02]' : 'bg-white/[0.01]'"
                    >
                      <span class="text-[15px] font-bold leading-none text-emerald-400">✓</span>
                      <span class="mt-1 w-full text-center text-[9px] font-medium leading-none text-slate-400">1 уровень</span>
                    </div>
                    <div
                      class="flex min-w-0 flex-col items-center justify-center border-b border-l border-amber-400/15 bg-amber-500/[0.05] px-1.5 py-2.5 text-center"
                    >
                      <span class="text-[15px] font-bold leading-none text-emerald-400">✓</span>
                      <span class="mt-1 w-full text-center text-[9px] font-semibold leading-tight text-emerald-300">3 уровня</span>
                    </div>
                  </template>
                  <template v-else-if="row.kind === 'limits'">
                    <span
                      class="min-w-0 border-b border-white/[0.06] py-2.5 pl-2 pr-1.5 text-[12px] leading-snug text-slate-200 sm:pl-2.5"
                      :class="idx % 2 === 1 ? 'bg-white/[0.02]' : 'bg-white/[0.01]'"
                    >{{ row.label }}</span>
                    <div
                      class="flex min-w-0 flex-col items-center justify-center border-b border-l border-white/[0.06] px-1.5 py-2.5 text-center"
                      :class="idx % 2 === 1 ? 'bg-white/[0.02]' : 'bg-white/[0.01]'"
                    >
                      <span class="text-[11px] font-bold tabular-nums tracking-tight text-violet-300/95">3 / 3</span>
                    </div>
                    <div
                      class="flex min-w-0 flex-col items-center justify-center border-b border-l border-amber-400/15 bg-amber-500/[0.05] px-1.5 py-2.5 text-center"
                    >
                      <span class="text-[11px] font-semibold leading-tight text-amber-200/95">Без лимитов</span>
                    </div>
                  </template>
                  <template v-else>
                    <span
                      class="min-w-0 border-b border-white/[0.06] py-2.5 pl-2 pr-1.5 text-[12px] leading-snug text-slate-200 sm:pl-2.5"
                      :class="idx % 2 === 1 ? 'bg-white/[0.02]' : 'bg-white/[0.01]'"
                    >{{ row.label }}</span>
                    <span
                      class="flex min-w-0 items-center justify-center border-b border-l border-white/[0.05] px-1.5 text-[16px] font-bold"
                      :class="[row.free === 'ok' ? 'text-emerald-400' : 'text-rose-400/90', idx % 2 === 1 ? 'bg-white/[0.02]' : 'bg-white/[0.01]']"
                    >{{ row.free === 'ok' ? '✓' : '✕' }}</span>
                    <span
                      class="flex min-w-0 items-center justify-center border-b border-l border-amber-400/15 bg-amber-500/[0.05] px-1.5 text-[16px] font-bold text-emerald-400"
                    >{{ row.premium === 'ok' ? '✓' : '✕' }}</span>
                  </template>
                </template>
                </div>
              </div>

              <button
                type="button"
                class="relative w-full overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-white text-center shadow-[0_14px_42px_-14px_rgba(243,156,18,0.62),inset_0_1px_0_rgba(255,255,255,0.28)] transition active:scale-[0.99]"
              style="background: linear-gradient(90deg, #f39c12 0%, #df5a3b 34%, #b043cc 56%, #5c2dc1 74%, #2a1a83 100%);"
                @click="scrollToBillingLandingPlans"
              >
                Выбрать Premium
              </button>
            </div>
          </section>

          <!-- 4. Выбор тарифа (карточки как в макете) -->
          <section
            id="billing-landing-plans"
            ref="billingLandingPlansRef"
            class="relative overflow-hidden rounded-[1.125rem] border border-white/[0.12] bg-black px-4 py-6 text-white ring-1 ring-inset ring-white/[0.06]"
          >
            <h2 class="text-center text-lg font-extrabold tracking-tight text-white sm:text-xl">
              Выбор тарифа
            </h2>
            <div class="mt-5 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
              <button
                v-for="card in landingPlanCards"
                :key="card.months"
                type="button"
                class="relative flex min-h-[8.5rem] flex-col items-stretch rounded-xl border px-2 pb-2 pt-2 text-center transition active:scale-[0.99]"
                :class="
                  landingSelectedPlanMonths === card.months
                    ? 'border-amber-400/80 bg-amber-500/10 ring-2 ring-amber-400/45'
                    : 'border-white/10 bg-zinc-950/90 hover:border-white/20'
                "
                @click="selectLandingPlan(card.months)"
              >
                <span
                  v-if="card.discountLabel"
                  class="absolute right-1 top-1 z-[1] max-w-[calc(100%-0.5rem)] truncate rounded bg-violet-600 px-1 py-px text-[8px] font-extrabold leading-tight text-white"
                >{{ card.discountLabel }}</span>
                <div class="flex min-h-0 flex-1 flex-col items-center justify-center gap-1 px-0.5 pb-1 pt-3">
                  <span class="text-[11px] font-semibold text-slate-400">{{ card.label }}</span>
                  <span class="text-base font-extrabold tabular-nums text-white sm:text-lg">{{ card.price }}</span>
                  <span class="text-[11px] font-semibold tabular-nums text-amber-200/90">
                    +{{ subscriptionTokensForPlan(card) }}
                    <span class="inline-block translate-y-px text-amber-300" aria-hidden="true">⚡</span>
                  </span>
                </div>
                <span
                  v-if="card.tag"
                  class="mt-auto shrink-0 rounded-full bg-emerald-500/20 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-emerald-300"
                >{{ card.tag }}</span>
              </button>
            </div>
            <button
              type="button"
              class="mt-3 w-full py-2 text-center text-[13px] font-medium text-slate-400 underline decoration-slate-600 underline-offset-4 transition hover:text-slate-300"
              @click="showAllLandingPlans = !showAllLandingPlans"
            >
              {{ showAllLandingPlans ? 'Скрыть дополнительные тарифы' : 'Показать все тарифы' }}
            </button>
            <button
              type="button"
              class="relative w-full overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-white text-center shadow-[0_14px_42px_-14px_rgba(243,156,18,0.62),inset_0_1px_0_rgba(255,255,255,0.28)] transition active:scale-[0.99]"
              style="background: linear-gradient(90deg, #f39c12 0%, #df5a3b 34%, #b043cc 56%, #5c2dc1 74%, #2a1a83 100%);"
              @click="onLandingContinue"
            >
              Продолжить
            </button>
            <button
              type="button"
              class="mt-2 w-full py-2 text-center text-[13px] font-medium text-slate-500 underline decoration-slate-600 underline-offset-4 transition hover:text-slate-400"
              @click="openPromoCodeModal"
            >
              Есть промокод?
            </button>
            <!-- Оплата и все периоды — внутри того же лендинга, без отдельной «страницы Guard Premium» -->
            <div class="mt-8 space-y-3 border-t border-white/[0.1] pt-7">
              <button
                v-if="billingFromGroupStats"
                type="button"
                class="flex w-full items-center justify-center gap-1 rounded-lg border border-white/[0.12] bg-white/[0.06] py-1.5 text-[12px] font-semibold text-lime-200/95 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-md transition hover:bg-white/[0.1] active:scale-[0.99]"
                @click="backFromBillingToGroupStats"
              >
                ← К статистике группы
              </button>

          <div id="billing-premium-plans" ref="billingPremiumPlansRef" class="scroll-mt-4 space-y-2"></div>

          <div
            v-if="me?.test_tariff_payment_visible"
            class="flex flex-col gap-1 rounded-lg border border-amber-400/22 bg-amber-500/[0.05] px-1.5 py-1.5 backdrop-blur-xl"
          >
            <div class="flex flex-wrap items-center gap-x-1.5 gap-y-1">
              <span class="text-[9px] font-semibold uppercase tracking-wide text-amber-200/90">Тест тарифов</span>
              <button
                type="button"
                :class="tokensInfoBtnAmberClass"
                title="Что это за блок"
                aria-label="Тестовая оплата тарифов"
                @click="openPremiumTestTariffInfo"
              >i</button>
            </div>
            <div class="grid grid-cols-2 gap-1 sm:grid-cols-3">
              <button
                v-for="plan in PREMIUM_PLANS"
                :key="`test-tariff-${plan.months}`"
                type="button"
                class="relative min-h-[3.1rem] overflow-hidden rounded-lg border border-amber-500/30 bg-black/25 px-1.5 py-1 text-left backdrop-blur-md transition hover:border-amber-400/45 hover:bg-amber-950/20 disabled:opacity-55"
                :disabled="payLoadingTestMonths !== null || payLoadingMonths !== null"
                @click="openPremiumPayMethodModal(plan.months, 'test')"
              >
                <span
                  v-if="premiumSavingsCornerBadge(plan)"
                  class="absolute right-0.5 top-0.5 z-[1] max-w-[min(100%,5.5rem)] truncate rounded bg-amber-600/92 px-0.5 py-px text-[7px] font-bold leading-none tabular-nums tracking-wide text-white shadow-sm"
                >{{ premiumSavingsCornerBadge(plan) }}</span>
                <div
                  class="flex flex-col justify-center gap-0.5"
                  :class="premiumSavingsCornerBadge(plan) ? 'pr-5 pt-0.5' : ''"
                >
                  <span class="text-[9px] text-amber-200/70">{{ plan.icon }}</span>
                  <span class="text-[10px] font-bold leading-tight text-amber-100">{{ plan.label }}</span>
                  <span class="text-[9px] font-semibold tabular-nums text-amber-200/85">{{ plan.price }}</span>
                  <span class="text-[8px] font-semibold tabular-nums text-amber-300/90">+{{ subscriptionTokensForPlan(plan) }} ⚡</span>
                  <span class="text-[7px] font-bold uppercase tracking-wide text-amber-400/80">тест</span>
                </div>
                <span
                  v-if="payLoadingTestMonths === plan.months"
                  class="absolute inset-x-0 bottom-0.5 text-center text-[8px] font-medium text-amber-200"
                >…</span>
              </button>
            </div>
            <button
              v-if="me?.is_admin"
              type="button"
              class="mt-1 w-full rounded-md border border-white/15 bg-white/[0.06] py-1.5 text-[11px] font-semibold text-slate-100 transition hover:bg-white/10"
              @click="openSubscriptionScreen"
            >
              Открыть экран подписки
            </button>
          </div>
          <div class="mt-4 border-t border-white/[0.08] pt-3 text-center">
            <p class="text-[10px] font-medium text-white/45">© {{ new Date().getFullYear() }} AI Guard. Все права защищены.</p>
            <p class="mt-1 text-[10px] text-white/38">Соцсети: Telegram · VK · YouTube</p>
          </div>
        </div>
        </section>
      </div>

      <div v-if="dashboardSection === 'faq'" class="mt-1 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
        <h3 class="text-base font-semibold text-slate-900 dark:text-white">FAQ</h3>
        <ul class="mt-2 list-disc space-y-1 pl-4 text-sm text-slate-700 dark:text-slate-300">
          <li>Токены подписки отвечают за доступ по периоду.</li>
          <li>Счёт «сверх подписки» объединяет партнёрские начисления и докупку «⚡ для рассылки».</li>
          <li>Их можно перевести в подписочные токены (кнопка в партнёрке).</li>
        </ul>
      </div>

      <div v-if="dashboardSection === 'history'" class="mt-1">
        <div class="rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
          <div class="grid grid-cols-2 gap-2">
            <button
              type="button"
              class="rounded-xl px-3 py-2 text-sm font-semibold"
              :class="historyTab === 'payments' ? 'bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-200' : 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200'"
              @click="historyTab = 'payments'"
            >
              История платежей
            </button>
            <button
              type="button"
              class="rounded-xl px-3 py-2 text-sm font-semibold"
              :class="historyTab === 'tokens' ? 'bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-200' : 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200'"
              @click="historyTab = 'tokens'"
            >
              История токенов
            </button>
          </div>
          <div v-if="historyLoading" class="py-6 text-center text-sm text-slate-500 dark:text-slate-400">Секундочку…</div>
          <div v-else-if="historyTab === 'payments'" class="mt-3 space-y-2">
            <div v-if="historyPayments.length === 0" class="rounded-xl bg-slate-50 p-4 text-center text-sm text-slate-500 dark:bg-slate-700/40 dark:text-slate-400">
              Платежей пока нет.
            </div>
            <div v-for="(item, idx) in historyPayments" :key="`dp-${idx}`" class="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
              <p class="text-xs text-slate-500 dark:text-slate-400">{{ item.created_at || '—' }}</p>
              <div class="mt-1 flex items-center justify-between gap-2">
                <div>
                  <p class="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    <template v-if="String(item.tariff || '').toLowerCase() === 'tokens'">
                      {{ fmtAmount(item.amount_rub) }} ₽ · {{ item.months }} ⚡
                    </template>
                    <template v-else>
                      {{ fmtAmount(item.amount_rub) }} ₽ · {{ item.months }} мес.
                    </template>
                  </p>
                  <p class="text-xs text-slate-500 dark:text-slate-400">
                    {{ providerLabel(item.provider) }} · {{ item.status }}
                  </p>
                </div>
                <div class="flex items-center gap-2">
                  <button
                    v-if="item.receipt_url"
                    type="button"
                    class="rounded-xl bg-emerald-300 px-3 py-2 text-sm font-extrabold text-slate-900"
                    @click="openReceiptLink(item)"
                  >
                    🧾 Чек
                  </button>
                  <button
                    type="button"
                    class="rounded-xl bg-cyan-300 px-3 py-2 text-sm font-extrabold text-slate-900"
                    @click="openReceiptModal(item)"
                  >
                    Получить чек
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="mt-3 space-y-2">
            <div v-if="historyTokens.length === 0" class="rounded-xl bg-slate-50 p-4 text-center text-sm text-slate-500 dark:bg-slate-700/40 dark:text-slate-400">
              Движения токенов пока нет.
            </div>
            <div v-for="(item, idx) in historyTokens" :key="`dt-${idx}`" class="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
              <p class="text-xs text-slate-500 dark:text-slate-400">{{ item.created_at || '—' }}</p>
              <p class="mt-1 text-sm font-semibold" :class="item.delta >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'">
                {{ item.delta >= 0 ? '+' : '' }}{{ fmtAmount(item.delta) }} ⚡
              </p>
              <p class="text-xs text-slate-500 dark:text-slate-400">{{ tokenReasonLabel(item.reason) }}</p>
            </div>
          </div>
        </div>
      </div>
      </div>
    </div>

    <div v-else-if="loading || (hasInitData && me === null && !error && !bootError)" class="py-10 text-center text-sm text-white/80">
      Секундочку…
    </div>

    <div
      v-if="showQuickStartModal"
      class="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-3 md:items-center"
      @click.self="showQuickStartModal = false"
    >
      <div class="w-full max-w-md rounded-2xl border border-sky-300/50 bg-white p-4 shadow-2xl dark:border-sky-700/60 dark:bg-gray-800">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-base font-semibold text-gray-900 dark:text-white">⚡ FAQ</h3>
          <button
            type="button"
            class="rounded-lg px-2 py-1 text-sm text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700"
            @click="showQuickStartModal = false"
          >
            ✕
          </button>
        </div>
        <ol class="list-decimal space-y-2 pl-4 text-sm text-gray-700 dark:text-gray-300">
          <li>Подключите группу и откройте раздел Защита.</li>
          <li>Токены подписки отвечают за доступ по периоду.</li>
          <li>Партнерские токены начисляются за оплаты рефералов.</li>
          <li>Партнерские токены можно переводить в подписку.</li>
        </ol>
        <p class="mt-3 text-xs text-gray-500 dark:text-gray-400">
          Совет: сначала группа и отчёты, потом тонкая настройка фильтров.
        </p>
      </div>
    </div>

    <div
      v-if="showAccountHistoryModal"
      class="fixed inset-0 z-[56] flex items-end justify-center bg-black/40 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur-md md:items-center md:pb-3"
      role="dialog"
      aria-modal="true"
      aria-label="История платежей и токенов"
      @click.self="showAccountHistoryModal = false"
    >
      <div
        class="flex max-h-[min(85vh,calc(100dvh-2.5rem))] w-full max-w-md flex-col overflow-hidden rounded-[22px] border border-black/[0.08] bg-[#f2f2f7] shadow-[0_25px_80px_-24px_rgba(0,0,0,0.45)] dark:border-white/[0.12] dark:bg-[#1c1c1e]"
        @click.stop
      >
        <div class="flex shrink-0 items-center justify-between px-4 pb-2 pt-3">
          <h2 class="text-[17px] font-semibold tracking-tight text-black dark:text-white">История</h2>
          <button
            type="button"
            class="flex h-8 w-8 items-center justify-center rounded-full bg-black/[0.06] text-[17px] font-light leading-none text-black/45 transition active:scale-95 dark:bg-white/[0.12] dark:text-white/55 dark:hover:bg-white/[0.18]"
            aria-label="Закрыть"
            @click="showAccountHistoryModal = false"
          >
            ✕
          </button>
        </div>
        <div class="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-y-contain px-3 pb-4 [-webkit-overflow-scrolling:touch]">
          <div class="flex rounded-[10px] bg-black/[0.06] p-0.5 dark:bg-white/[0.08]">
            <button
              type="button"
              class="flex-1 rounded-[9px] py-2 text-[13px] font-medium transition"
              :class="
                historyTab === 'payments'
                  ? 'bg-white text-black shadow-sm dark:bg-zinc-600 dark:text-white dark:shadow-none'
                  : 'text-black/45 dark:text-white/40'
              "
              @click="historyTab = 'payments'"
            >
              Платежи
            </button>
            <button
              type="button"
              class="flex-1 rounded-[9px] py-2 text-[13px] font-medium transition"
              :class="
                historyTab === 'tokens'
                  ? 'bg-white text-black shadow-sm dark:bg-zinc-600 dark:text-white dark:shadow-none'
                  : 'text-black/45 dark:text-white/40'
              "
              @click="historyTab = 'tokens'"
            >
              Токены
            </button>
          </div>

          <div v-if="historyLoading" class="py-8 text-center text-[15px] text-black/35 dark:text-white/35">Секундочку…</div>
          <div v-else-if="historyTab === 'payments'" class="space-y-2">
            <div
              v-if="historyPayments.length === 0"
              class="rounded-[14px] bg-white px-4 py-6 text-center text-[15px] text-black/45 dark:bg-white/[0.06] dark:text-white/45"
            >
              Платежей пока нет.
            </div>
            <div
              v-for="(item, idx) in historyPayments"
              :key="`mh-dp-${idx}`"
              class="rounded-[14px] border border-black/[0.06] bg-white p-3 dark:border-white/[0.08] dark:bg-white/[0.05]"
            >
              <p class="text-[13px] text-black/45 dark:text-white/45">{{ item.created_at || '—' }}</p>
              <div class="mt-1.5 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div class="min-w-0">
                  <p class="text-[15px] font-semibold text-black dark:text-white">
                    <template v-if="String(item.tariff || '').toLowerCase() === 'tokens'">
                      {{ fmtAmount(item.amount_rub) }} ₽ · {{ item.months }} ⚡
                    </template>
                    <template v-else>
                      {{ fmtAmount(item.amount_rub) }} ₽ · {{ item.months }} мес.
                    </template>
                  </p>
                  <p class="mt-0.5 text-[13px] text-black/45 dark:text-white/45">
                    {{ providerLabel(item.provider) }} · {{ item.status }}
                  </p>
                </div>
                <div class="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
                  <button
                    v-if="item.receipt_url"
                    type="button"
                    class="rounded-full bg-emerald-500/90 px-3 py-1.5 text-[13px] font-semibold text-white"
                    @click="openReceiptLink(item)"
                  >
                    Чек
                  </button>
                  <button
                    type="button"
                    class="rounded-full bg-sky-500/90 px-3 py-1.5 text-[13px] font-semibold text-white"
                    @click="openReceiptModal(item)"
                  >
                    Получить чек
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="space-y-2">
            <div
              v-if="historyTokens.length === 0"
              class="rounded-[14px] bg-white px-4 py-6 text-center text-[15px] text-black/45 dark:bg-white/[0.06] dark:text-white/45"
            >
              Движения токенов пока нет.
            </div>
            <div
              v-for="(item, idx) in historyTokens"
              :key="`mh-dt-${idx}`"
              class="rounded-[14px] border border-black/[0.06] bg-white p-3 dark:border-white/[0.08] dark:bg-white/[0.05]"
            >
              <p class="text-[13px] text-black/45 dark:text-white/45">{{ item.created_at || '—' }}</p>
              <p class="mt-1 text-[15px] font-semibold" :class="item.delta >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'">
                {{ item.delta >= 0 ? '+' : '' }}{{ fmtAmount(item.delta) }} ⚡
              </p>
              <p class="mt-0.5 text-[13px] text-black/45 dark:text-white/45">{{ tokenReasonLabel(item.reason) }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="showActivityModal"
      class="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-3 pb-[calc(4.5rem+env(safe-area-inset-bottom,0px))] backdrop-blur-[2px] md:items-center md:pb-3"
      @click.self="showActivityModal = false"
    >
      <div
        class="flex min-h-0 max-h-[min(86vh,calc(100dvh-5rem))] w-full max-w-xl flex-col overflow-hidden rounded-[1.35rem] border border-white/12 bg-zinc-950/82 p-3 text-slate-100 shadow-[0_28px_90px_-28px_rgba(0,0,0,0.92)] ring-1 ring-white/10 backdrop-blur-2xl"
      >
        <div class="mb-3 flex shrink-0 items-center justify-between gap-2">
          <h3 class="text-sm font-semibold text-white">Подробный отчет по защите</h3>
          <button type="button" class="rounded-lg px-2 py-1 text-sm text-zinc-400 hover:bg-white/10 hover:text-white" @click="showActivityModal = false">✕</button>
        </div>
        <div v-if="activityLoading" class="shrink-0 py-5 text-center text-sm text-zinc-400">Секундочку…</div>
        <div v-else-if="activityChats.length === 0" class="shrink-0 py-6 text-center text-sm text-zinc-500">Групп пока нет.</div>
        <div v-else class="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-y-contain pr-1 [-webkit-overflow-scrolling:touch]">
          <section class="overflow-hidden rounded-[1.1rem] border border-white/10 bg-black/35 p-2.5 ring-1 ring-white/10 backdrop-blur-xl">
            <p class="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">Общий отчёт</p>
            <div class="mt-1 grid grid-cols-2 gap-1.5 text-xs sm:grid-cols-3 md:grid-cols-5">
              <div class="rounded-lg border border-white/10 bg-zinc-950/50 p-2 ring-1 ring-white/5 backdrop-blur-md">
                <p class="text-[10px] text-zinc-500">Всего</p>
                <p class="text-base font-bold text-white">{{ activityOverview.total }}</p>
              </div>
              <div class="rounded-lg border border-rose-500/35 bg-rose-950/25 p-2 ring-1 ring-rose-500/15 backdrop-blur-md">
                <p class="text-[10px] text-rose-200/85">Удалено</p>
                <p class="text-base font-bold text-rose-200">{{ activityOverview.deleted }}</p>
              </div>
              <div class="rounded-lg border border-red-500/40 bg-red-950/30 p-2 ring-1 ring-red-400/20 backdrop-blur-md">
                <p class="text-[10px] text-red-200/90">Замечено</p>
                <p class="text-base font-bold text-red-200">{{ activityOverview.observed }}</p>
              </div>
              <div class="rounded-lg border border-amber-500/35 bg-amber-950/25 p-2 ring-1 ring-amber-400/15 backdrop-blur-md">
                <p class="text-[10px] text-amber-200/85">Ограничено (мут)</p>
                <p class="text-base font-bold text-amber-200">{{ activityOverview.muted }}</p>
              </div>
              <div class="rounded-lg border border-fuchsia-500/35 bg-fuchsia-950/25 p-2 ring-1 ring-fuchsia-400/15 backdrop-blur-md">
                <p class="text-[10px] text-fuchsia-200/85">Заблокировано</p>
                <p class="text-base font-bold text-fuchsia-200">{{ activityOverview.banned }}</p>
              </div>
            </div>
          </section>

          <section class="overflow-hidden rounded-[1.1rem] border border-white/10 bg-black/35 p-2.5 ring-1 ring-white/10 backdrop-blur-xl">
            <p class="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">Группы</p>
            <div class="mt-1.5 space-y-3">
              <div v-if="activityByGroupDelegated.length">
                <p class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-violet-200/90">Делегированные</p>
                <div class="space-y-1.5">
                  <div
                    v-for="group in activityByGroupDelegated"
                    :key="`grp-del-${group.chat_id}`"
                    class="rounded-xl border border-violet-400/20 bg-zinc-950/45 p-2 ring-1 ring-violet-500/15 backdrop-blur-md"
                  >
                    <div class="flex items-start justify-between gap-2">
                      <div>
                        <p class="text-xs font-semibold text-white">{{ group.chat_title }}</p>
                        <p class="mt-0.5 text-[11px] text-zinc-300">
                          Всего: <b>{{ group.total }}</b> · Удалено: <b>{{ group.deleted }}</b> · <span class="font-semibold text-red-300/95">Замечено: <b>{{ group.observed }}</b></span> · Ограничено (мут): <b>{{ group.muted }}</b> · Заблокировано: <b>{{ group.banned }}</b>
                        </p>
                      </div>
                      <button
                        type="button"
                        class="shrink-0 rounded-lg border border-white/15 bg-white/8 px-2 py-0.5 text-[11px] font-semibold text-zinc-100 hover:bg-white/14"
                        @click="openGroupActivityDetails(group)"
                      >
                        Подробнее
                      </button>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="activityByGroupMine.length">
                <p class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">Мои чаты</p>
                <div class="space-y-1.5">
                  <div
                    v-for="group in activityByGroupMine"
                    :key="`grp-own-${group.chat_id}`"
                    class="rounded-xl border border-white/10 bg-zinc-950/40 p-2 ring-1 ring-white/5 backdrop-blur-md"
                  >
                    <div class="flex items-start justify-between gap-2">
                      <div>
                        <p class="text-xs font-semibold text-white">{{ group.chat_title }}</p>
                        <p class="mt-0.5 text-[11px] text-zinc-300">
                          Всего: <b>{{ group.total }}</b> · Удалено: <b>{{ group.deleted }}</b> · <span class="font-semibold text-red-300/95">Замечено: <b>{{ group.observed }}</b></span> · Ограничено (мут): <b>{{ group.muted }}</b> · Заблокировано: <b>{{ group.banned }}</b>
                        </p>
                      </div>
                      <button
                        type="button"
                        class="shrink-0 rounded-lg border border-white/15 bg-white/8 px-2 py-0.5 text-[11px] font-semibold text-zinc-100 hover:bg-white/14"
                        @click="openGroupActivityDetails(group)"
                      >
                        Подробнее
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>

    <div
      v-if="showGroupActivityModal"
      class="fixed inset-0 z-[60] flex items-end justify-center bg-black/70 p-3 backdrop-blur-[2px] md:items-center"
      @click.self="closeGroupActivityModal"
    >
      <div
        class="flex max-h-[88vh] w-full max-w-md flex-col overflow-hidden rounded-[1.35rem] border border-white/12 bg-zinc-950/85 p-3 text-slate-100 shadow-[0_28px_90px_-28px_rgba(0,0,0,0.92)] ring-1 ring-white/10 backdrop-blur-2xl"
      >
        <div class="mb-2 flex shrink-0 items-center justify-between gap-2">
          <div class="min-w-0">
            <h3 class="truncate text-sm font-semibold text-white">{{ groupActivityTitle }}</h3>
            <p class="text-[10px] text-zinc-500">{{ groupPeriodLabel }}</p>
          </div>
          <button type="button" class="rounded-lg px-2 py-1 text-sm text-zinc-400 hover:bg-white/10 hover:text-white" @click="closeGroupActivityModal">✕</button>
        </div>
        <div class="flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-y-contain [-webkit-overflow-scrolling:touch]">
          <div class="shrink-0 space-y-1.5">
            <div class="flex flex-wrap gap-1">
              <button
                v-for="p in GROUP_STATS_PRESETS"
                :key="p.key"
                type="button"
                class="rounded-lg border px-2 py-1 text-[10px] font-semibold"
                :class="!groupStatsUseCustom && groupStatsPreset === p.key ? 'border-lime-400/80 bg-lime-500/15 text-lime-200' : 'border-white/12 bg-black/35 text-zinc-200'"
                @click="selectGroupStatsPreset(p.key)"
              >
                {{ p.label }}
              </button>
            </div>
            <button
              type="button"
              class="w-full rounded-lg border border-white/12 bg-black/30 py-1.5 text-[10px] font-semibold text-zinc-300 backdrop-blur-md"
              :class="groupStatsUseCustom ? 'ring-1 ring-amber-400/60' : ''"
              @click="toggleGroupStatsRangePanel"
            >
              {{ groupStatsRangeExpanded ? '▾ Скрыть свой период' : '▸ Свой период (с даты по дату)' }}
            </button>
            <div v-if="groupStatsRangeExpanded" class="space-y-1.5 rounded-xl border border-white/12 bg-black/35 p-2 backdrop-blur-md">
              <label class="block text-[10px] text-zinc-500">С даты и времени</label>
              <input v-model="groupStatsFromInput" type="datetime-local" class="w-full rounded-lg border border-white/12 bg-zinc-950/80 px-2 py-1 text-[11px] text-white">
              <label class="block text-[10px] text-zinc-500">По дату и время</label>
              <input v-model="groupStatsToInput" type="datetime-local" class="w-full rounded-lg border border-white/12 bg-zinc-950/80 px-2 py-1 text-[11px] text-white">
              <button
                type="button"
                class="mt-1 w-full rounded-lg bg-lime-500/90 py-1.5 text-[11px] font-bold text-slate-900"
                @click="applyGroupCustomRange"
              >
                Применить период
              </button>
            </div>
          </div>
          <div class="mt-2 grid grid-cols-2 gap-2">
            <div
              v-for="bucket in groupBreakdownBuckets"
              :key="bucket.key"
              class="flex min-h-[4.5rem] flex-col justify-between rounded-xl border-2 p-2"
              :class="filterStatCardTone(bucket.tone)"
            >
              <p class="text-left text-[10px] font-medium leading-tight text-white/90">{{ bucket.label }}</p>
              <div class="mt-1">
                <template v-if="bucket.premium && !breakdownUserPremium">
                  <button
                    type="button"
                    class="w-full rounded-lg border border-amber-400/70 bg-amber-500/15 py-1.5 text-center text-[11px] font-bold text-amber-200"
                    @click="goBillingCloseGroupModal"
                  >
                    Premium
                  </button>
                </template>
                <template v-else>
                  <p class="text-xl font-extrabold leading-none text-white">{{ bucket.count }}</p>
                  <p v-if="bucket.note" class="mt-0.5 text-[9px] leading-tight text-slate-400">{{ bucket.note }}</p>
                </template>
              </div>
            </div>
          </div>
          <div class="mt-2 shrink-0 overflow-hidden rounded-xl border border-white/10 bg-black/35 ring-1 ring-white/5 backdrop-blur-md">
            <p class="border-b border-white/10 px-2 py-1.5 text-[10px] uppercase tracking-wide text-zinc-500">События за период</p>
            <div class="space-y-1 px-2 py-2 pb-3">
              <div v-if="groupJournalForModal.length === 0" class="py-4 text-center text-[11px] text-zinc-500">Событий за период нет.</div>
              <div
                v-for="(item, idx) in groupJournalForModal"
                :key="`gj-${idx}-${item.created_at}-${item.user_id}-${item.action}`"
                class="rounded-lg border p-2"
                :class="normalizeAction(item.action) === 'observe'
                  ? 'border-red-500/70 bg-red-950/35 ring-1 ring-red-500/20'
                  : 'border-white/10 bg-zinc-950/50'"
              >
                <div class="flex flex-wrap items-start justify-between gap-2">
                  <div class="min-w-0 flex-1">
                    <p class="text-[10px] text-zinc-500">{{ journalDisplayTime(item.created_at) }}</p>
                    <button
                      type="button"
                      class="mt-0.5 block max-w-full truncate text-left text-[11px] font-semibold text-cyan-200 underline decoration-cyan-500/35 underline-offset-2 hover:text-cyan-100"
                      :aria-label="`Профиль ${violatorLabel(item)}`"
                      @click="openViolatorProfile(item)"
                    >
                      {{ violatorLabel(item) }}
                    </button>
                    <p
                      class="mt-1 text-[11px] leading-snug"
                      :class="normalizeAction(item.action) === 'observe' ? 'text-red-200/95' : 'text-zinc-200'"
                    >
                      <span class="font-semibold">{{ actionLabelRu(item.action) }}</span>
                      <span class="text-zinc-500"> · </span>
                      <span>{{ journalTriggerDescription(item) }}</span>
                    </p>
                  </div>
                  <div v-if="normalizeAction(item.action) === 'mute'" class="flex shrink-0 items-center gap-1">
                    <span
                      v-if="modUnmuteDone[journalEventKey(item)]"
                      class="inline-flex h-8 min-w-[2rem] items-center justify-center rounded-full bg-emerald-600/30 text-sm font-bold text-emerald-200 ring-1 ring-emerald-400/40"
                      title="Размут выполнен"
                      aria-label="Размут выполнен"
                    >✓</span>
                    <button
                      v-else
                      type="button"
                      class="rounded-md border border-amber-500/50 bg-amber-500/15 px-2 py-1 text-[10px] font-bold text-amber-100 hover:bg-amber-500/25 disabled:opacity-50"
                      :disabled="!!modPrivilegeBusyKey"
                      @click="postChatMemberPrivilege('unmute', groupActivityChatId, item.user_id, journalEventKey(item))"
                    >
                      Размутить
                    </button>
                  </div>
                  <div v-if="normalizeAction(item.action) === 'ban'" class="flex shrink-0 items-center gap-1">
                    <span
                      v-if="modUnbanDone[journalEventKey(item)]"
                      class="inline-flex h-8 min-w-[2rem] items-center justify-center rounded-full bg-emerald-600/30 text-sm font-bold text-emerald-200 ring-1 ring-emerald-400/40"
                      title="Разбан выполнен"
                      aria-label="Разбан выполнен"
                    >✓</span>
                    <button
                      v-else
                      type="button"
                      class="rounded-md border border-fuchsia-500/50 bg-fuchsia-500/15 px-2 py-1 text-[10px] font-bold text-fuchsia-100 hover:bg-fuchsia-500/25 disabled:opacity-50"
                      :disabled="!!modPrivilegeBusyKey"
                      @click="postChatMemberPrivilege('unban', groupActivityChatId, item.user_id, journalEventKey(item))"
                    >
                      Разбанить
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

    </div>

    <div
      v-if="showUpdatesRoadmapModal"
      class="fixed inset-0 z-[70] flex items-end justify-center bg-[#03050c]/82 p-3 backdrop-blur-md md:items-center"
      role="presentation"
      @click.self="showUpdatesRoadmapModal = false"
    >
      <div
        class="flex max-h-[min(86vh,calc(100dvh-2rem))] w-full max-w-md flex-col overflow-hidden rounded-[22px] bg-gradient-to-br from-[#0a1022]/98 via-[#0d1530]/96 to-[#04070f]/98 text-slate-100 shadow-[0_28px_70px_-30px_rgba(56,189,248,0.42)] ring-1 ring-cyan-400/20"
        role="dialog"
        aria-modal="true"
        aria-labelledby="updates-roadmap-title"
      >
        <div class="shrink-0 p-4 pb-2">
          <div class="flex items-center justify-between gap-2">
            <h3 id="updates-roadmap-title" class="text-[17px] font-semibold tracking-tight text-white">Лента обновлений</h3>
            <button
              type="button"
              class="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-slate-900/55 text-sm text-slate-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] transition hover:bg-slate-800/75 hover:text-white"
              @click="showUpdatesRoadmapModal = false"
            >
              ✕
            </button>
          </div>
          <p class="mt-1 text-[12px] leading-snug text-slate-400/95">
            На главной показаны последние {{ UPDATES_HOME_PREVIEW_N }} релиза — здесь полный список.
          </p>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto overscroll-y-contain px-4 pb-4 [-webkit-overflow-scrolling:touch]">
          <ul class="space-y-3">
            <li
              v-for="s in UPDATES_SLIDES"
              :key="s.key"
              class="rounded-2xl bg-gradient-to-br from-slate-900/72 via-slate-950/55 to-black/50 p-3.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_16px_34px_-22px_rgba(34,211,238,0.35)] ring-1 ring-cyan-400/15"
            >
              <p class="text-[11px] font-semibold tracking-wide text-cyan-200/95">{{ formatUpdateMetaLong(s) }}</p>
              <p class="mt-1.5 text-[15px] font-bold leading-snug text-white">{{ s.headline }}</p>
              <p class="mt-2 text-[13px] leading-snug text-slate-300/95">{{ s.teaser }}</p>
              <div
                v-if="updatesRoadmapExpanded[s.key]"
                class="mt-2 border-t border-white/[0.06] pt-2 text-[13px] leading-relaxed text-slate-200/95"
              >
                {{ s.body }}
              </div>
              <button
                type="button"
                class="mt-3 text-[13px] font-semibold text-cyan-300 transition hover:text-cyan-200"
                @click="toggleUpdatesRoadmapExpand(s.key)"
              >
                {{ updatesRoadmapExpanded[s.key] ? 'Скрыть' : 'Показать полностью' }}
              </button>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <div
      v-if="showFundsMovementModal"
      class="fixed inset-0 z-[58] flex items-end justify-center bg-black/65 p-3 backdrop-blur-sm md:items-center"
      @click.self="closeFundsMovementModal"
    >
      <div
        ref="fundsModalWrapRef"
        class="flex max-h-[88vh] w-full max-w-md flex-col overflow-hidden rounded-2xl border border-slate-600 bg-white shadow-2xl dark:border-slate-600 dark:bg-slate-900"
        role="dialog"
        aria-modal="true"
        aria-labelledby="funds-modal-title"
      >
        <div class="flex shrink-0 items-center justify-between gap-2 border-b border-slate-200 px-3 py-2.5 dark:border-slate-700">
          <h3 id="funds-modal-title" class="text-sm font-semibold text-slate-900 dark:text-white">Движение средств</h3>
          <button
            type="button"
            class="rounded-lg px-2 py-1 text-sm text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
            @click="closeFundsMovementModal"
          >
            ✕
          </button>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto overscroll-y-contain p-3 [-webkit-overflow-scrolling:touch]">
          <div class="grid grid-cols-2 gap-2">
            <button
              type="button"
              class="rounded-xl px-3 py-2 text-sm font-semibold"
              :class="historyTab === 'payments' ? 'bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-200' : 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200'"
              @click="historyTab = 'payments'"
            >
              История платежей
            </button>
            <button
              type="button"
              class="rounded-xl px-3 py-2 text-sm font-semibold"
              :class="historyTab === 'tokens' ? 'bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-200' : 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200'"
              @click="historyTab = 'tokens'"
            >
              История токенов
            </button>
          </div>
          <div v-if="historyLoading" class="py-6 text-center text-sm text-slate-500 dark:text-slate-400">Секундочку…</div>
          <div v-else-if="historyTab === 'payments'" class="mt-3 space-y-2">
            <div v-if="historyPayments.length === 0" class="rounded-xl bg-slate-50 p-4 text-center text-sm text-slate-500 dark:bg-slate-700/40 dark:text-slate-400">
              Платежей пока нет.
            </div>
            <div v-for="(item, idx) in historyPayments" :key="`mf-dp-${idx}`" class="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
              <p class="text-xs text-slate-500 dark:text-slate-400">{{ item.created_at || '—' }}</p>
              <div class="mt-1 flex items-center justify-between gap-2">
                <div>
                  <p class="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    <template v-if="String(item.tariff || '').toLowerCase() === 'tokens'">
                      {{ fmtAmount(item.amount_rub) }} ₽ · {{ item.months }} ⚡
                    </template>
                    <template v-else>
                      {{ fmtAmount(item.amount_rub) }} ₽ · {{ item.months }} мес.
                    </template>
                  </p>
                  <p class="text-xs text-slate-500 dark:text-slate-400">
                    {{ providerLabel(item.provider) }} · {{ item.status }}
                  </p>
                </div>
                <div class="flex items-center gap-2">
                  <button
                    v-if="item.receipt_url"
                    type="button"
                    class="rounded-xl bg-emerald-300 px-3 py-2 text-sm font-extrabold text-slate-900"
                    @click="openReceiptLink(item)"
                  >
                    🧾 Чек
                  </button>
                  <button
                    type="button"
                    class="rounded-xl bg-cyan-300 px-3 py-2 text-sm font-extrabold text-slate-900"
                    @click="openReceiptModal(item)"
                  >
                    Получить чек
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="mt-3 space-y-2">
            <div v-if="historyTokens.length === 0" class="rounded-xl bg-slate-50 p-4 text-center text-sm text-slate-500 dark:bg-slate-700/40 dark:text-slate-400">
              Движения токенов пока нет.
            </div>
            <div v-for="(item, idx) in historyTokens" :key="`mf-dt-${idx}`" class="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
              <p class="text-xs text-slate-500 dark:text-slate-400">{{ item.created_at || '—' }}</p>
              <p class="mt-1 text-sm font-semibold" :class="item.delta >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'">
                {{ item.delta >= 0 ? '+' : '' }}{{ fmtAmount(item.delta) }} ⚡
              </p>
              <p class="text-xs text-slate-500 dark:text-slate-400">{{ tokenReasonLabel(item.reason) }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="showReceiptModal"
      class="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-3 md:items-center"
      @click.self="showReceiptModal = false"
    >
      <div class="w-full max-w-md rounded-2xl bg-white p-4 shadow-2xl dark:bg-gray-800">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-base font-semibold text-gray-900 dark:text-white">Получить чек</h3>
          <button
            type="button"
            class="rounded-lg px-2 py-1 text-sm text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700"
            @click="showReceiptModal = false"
          >
            ✕
          </button>
        </div>
        <p class="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-100">
          Если поля не заполнены, укажите данные вручную и нажмите «Получить чек».
        </p>
        <div class="space-y-2">
          <label class="block text-sm text-slate-700 dark:text-slate-300">Имя фамилия:</label>
          <input
            v-model="receiptFullName"
            type="text"
            placeholder="Alex Smirnov"
            autocomplete="name"
            class="w-full rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 text-sm text-slate-900"
          >
          <label class="block text-sm text-slate-700 dark:text-slate-300">E-mail:</label>
          <input
            v-model="receiptEmail"
            type="email"
            placeholder="you@email.com"
            autocomplete="email"
            class="w-full rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 text-sm text-slate-900"
          >
          <p class="rounded-xl border border-cyan-300 px-3 py-2 text-sm text-slate-700 dark:text-slate-300">
            Поле email обязательное для отправки чека.
          </p>
          <button
            type="button"
            class="mt-2 w-full rounded-xl bg-cyan-300 px-4 py-3 text-lg font-extrabold text-slate-900 disabled:opacity-50"
            :disabled="receiptSending || !receiptEmail"
            @click="submitReceipt"
          >
            Получить чек
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="showAurumHelpModal"
      class="fixed inset-0 z-[280] flex items-end justify-center bg-black/70 p-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] backdrop-blur-[3px] md:items-center md:pb-6"
      @click.self="showAurumHelpModal = false"
    >
      <div
        class="w-full max-w-lg overflow-hidden rounded-[1.25rem] border border-white/[0.14] bg-gradient-to-b from-zinc-900/75 to-zinc-950/92 p-4 text-slate-100 shadow-[0_28px_90px_-28px_rgba(0,0,0,0.9)] ring-1 ring-inset ring-white/[0.06] backdrop-blur-2xl"
        @click.stop
      >
        <div class="mb-3 flex items-center justify-between gap-2 border-b border-white/10 pb-2">
          <h3 class="text-sm font-semibold tracking-tight text-white">AURUM и счета</h3>
          <button
            type="button"
            class="rounded-lg px-2 py-1 text-sm text-white/50 hover:bg-white/10 hover:text-white"
            @click="showAurumHelpModal = false"
          >
            ✕
          </button>
        </div>
        <div class="max-h-[min(65vh,26rem)] space-y-2.5 overflow-y-auto text-left text-[13px] leading-snug text-white/72">
          <p v-for="(ap, ai) in aurumHelpParagraphs" :key="`aur-${ai}`">{{ ap }}</p>
        </div>
      </div>
    </div>

    <div
      v-if="showPremiumAurumShowcaseModal"
      class="fixed inset-0 z-[283] flex items-end justify-center bg-black/75 p-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] backdrop-blur-[4px] md:items-center md:pb-6"
      @click.self="showPremiumAurumShowcaseModal = false"
    >
      <div
        class="w-full max-w-lg overflow-hidden rounded-[1.25rem] border border-white/[0.14] bg-gradient-to-b from-zinc-900/80 via-zinc-950/92 to-black px-3 py-3.5 text-white shadow-[0_28px_90px_-28px_rgba(34,211,238,0.15)] ring-1 ring-inset ring-white/[0.06] backdrop-blur-2xl sm:px-4 sm:py-4"
        @click.stop
      >
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="min-w-0 truncate text-[14px] font-semibold tracking-tight text-white/95">Токены AURUM</h3>
          <div class="flex shrink-0 items-center gap-2">
            <div
              class="rounded-md border border-white/[0.1] bg-white/[0.05] px-2 py-0.5 text-right shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
              title="Всего доступных токенов"
            >
              <p class="text-[8px] font-medium uppercase leading-none tracking-[0.12em] text-white/38">Всего</p>
              <p class="text-xs font-bold leading-tight tabular-nums text-amber-200">{{ totalTokens }}<span class="ml-px text-[9px]">⚡</span></p>
            </div>
            <button
              type="button"
              class="rounded-lg px-2 py-1 text-sm text-white/50 hover:bg-white/10 hover:text-white"
              aria-label="Закрыть"
              @click="showPremiumAurumShowcaseModal = false"
            >
              ✕
            </button>
          </div>
        </div>
        <div class="rounded-xl border border-white/[0.1] bg-zinc-900/85 px-3 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
          <p class="text-center text-[13px] font-semibold text-white">С токенами вы сможете:</p>
          <div class="mt-3 grid grid-cols-4 gap-1.5 sm:gap-2">
            <div
              class="flex min-h-0 flex-col items-center rounded-lg border border-white/[0.12] bg-black/35 px-1 py-2.5 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.09)]"
            >
              <div class="flex h-12 w-12 shrink-0 items-center justify-center">
                <svg viewBox="0 0 24 24" class="h-10 w-10 text-[#38bdf8] drop-shadow-[0_0_12px_rgba(56,189,248,0.75)]" fill="none" aria-hidden="true">
                  <path d="M21.5 4.8 18.4 19c-.2.9-.8 1.1-1.6.7l-4.4-3.2-2.1 2c-.2.2-.4.4-.9.4l.3-4.5 8.3-7.5c.4-.3-.1-.5-.5-.2l-10.2 6.4-4.4-1.4c-.9-.3-.9-.9.2-1.3L19.9 4c.8-.3 1.5.2 1.3.8z" fill="currentColor" />
                </svg>
              </div>
              <p class="mt-1.5 w-full text-balance text-center text-[9px] font-semibold leading-[1.2] text-white/88 sm:text-[10px]">Рассылки по чатам</p>
            </div>
            <div
              class="flex min-h-0 flex-col items-center rounded-lg border border-white/[0.12] bg-black/35 px-1 py-2.5 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.09)]"
            >
              <div class="flex h-12 w-12 shrink-0 items-center justify-center">
                <svg viewBox="0 0 24 24" class="h-10 w-10 text-[#2dd4bf] drop-shadow-[0_0_12px_rgba(45,212,191,0.75)]" fill="none" aria-hidden="true">
                  <path d="M6 18v-3.2a2.8 2.8 0 0 1 2.8-2.8h6.4A2.8 2.8 0 0 1 18 14.8V18" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" />
                  <path d="M12 5v6.5" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" />
                  <path d="m8.8 8.2 3.2-3.2 3.2 3.2" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" />
                  <rect x="4.8" y="18" width="14.4" height="1.8" rx="0.9" fill="currentColor" />
                </svg>
              </div>
              <p class="mt-1.5 w-full text-balance text-center text-[9px] font-semibold leading-[1.2] text-white/88 sm:text-[10px]">Автопостинг в каналы</p>
            </div>
            <div
              class="flex min-h-0 flex-col items-center rounded-lg border border-white/[0.12] bg-black/35 px-1 py-2.5 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.09)]"
            >
              <div class="flex h-12 w-12 shrink-0 items-center justify-center">
                <svg viewBox="0 0 24 24" class="h-10 w-10 text-[#a855f7] drop-shadow-[0_0_12px_rgba(168,85,247,0.75)]" fill="none" aria-hidden="true">
                  <path d="M4 6.8A2.8 2.8 0 0 1 6.8 4h10.4A2.8 2.8 0 0 1 20 6.8v6.4a2.8 2.8 0 0 1-2.8 2.8h-6l-3.8 3v-3H6.8A2.8 2.8 0 0 1 4 13.2V6.8z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" />
                  <circle cx="9" cy="10" r="1" fill="currentColor" />
                  <circle cx="12" cy="10" r="1" fill="currentColor" />
                  <circle cx="15" cy="10" r="1" fill="currentColor" />
                </svg>
              </div>
              <p class="mt-1.5 w-full text-balance text-center text-[9px] font-semibold leading-[1.2] text-white/88 sm:text-[10px]">AI-ответы (скоро)</p>
            </div>
            <div
              class="flex min-h-0 flex-col items-center rounded-lg border border-white/[0.12] bg-black/35 px-1 py-2.5 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.09)]"
            >
              <div class="flex h-12 w-12 shrink-0 items-center justify-center">
                <svg viewBox="0 0 24 24" class="h-10 w-10 text-[#22c55e] drop-shadow-[0_0_12px_rgba(34,197,94,0.8)]" fill="none" aria-hidden="true">
                  <circle cx="9" cy="9" r="2.5" stroke="currentColor" stroke-width="1.7" />
                  <path d="M4.7 18a4.5 4.5 0 0 1 8.6 0" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
                  <circle cx="16.5" cy="9.5" r="2" stroke="currentColor" stroke-width="1.7" />
                  <path d="M13.9 17.3a3.8 3.8 0 0 1 5.7.7" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
                </svg>
              </div>
              <p class="mt-1.5 w-full text-balance text-center text-[9px] font-semibold leading-[1.2] text-white/88 sm:text-[10px]">Привлечение клиентов</p>
            </div>
          </div>
        </div>
        <button
          type="button"
          class="relative mt-3 w-full overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-white text-center shadow-[0_14px_42px_-14px_rgba(243,156,18,0.62),inset_0_1px_0_rgba(255,255,255,0.28)] transition active:scale-[0.99]"
          style="background: linear-gradient(90deg, #f39c12 0%, #df5a3b 34%, #b043cc 56%, #5c2dc1 74%, #2a1a83 100%);"
          @click="openTokenPacksFromShowcase"
        >
          Купить токены
        </button>
      </div>
    </div>

    <div
      v-if="showFreeAurumGateModal"
      class="fixed inset-0 z-[284] flex items-end justify-center bg-black/75 p-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] backdrop-blur-[4px] md:items-center md:pb-6"
      @click.self="showFreeAurumGateModal = false"
    >
      <div
        class="w-full max-w-lg overflow-hidden rounded-[1.25rem] border border-white/[0.14] bg-gradient-to-b from-zinc-900/80 via-zinc-950/92 to-black px-3 py-3.5 text-white shadow-[0_28px_90px_-28px_rgba(34,211,238,0.15)] ring-1 ring-inset ring-white/[0.06] backdrop-blur-2xl sm:px-4 sm:py-4"
        @click.stop
      >
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="min-w-0 truncate text-[14px] font-semibold tracking-tight text-white/95">Токены AURUM</h3>
          <div class="flex shrink-0 items-center gap-2">
            <div
              class="rounded-md border border-white/[0.1] bg-white/[0.05] px-2 py-0.5 text-right shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
              title="Всего доступных токенов"
            >
              <p class="text-[8px] font-medium uppercase leading-none tracking-[0.12em] text-white/38">Всего</p>
              <p class="text-xs font-bold leading-tight tabular-nums text-amber-200">0<span class="ml-px text-[9px]">⚡</span></p>
            </div>
            <button
              type="button"
              class="rounded-lg px-2 py-1 text-sm text-white/50 hover:bg-white/10 hover:text-white"
              aria-label="Закрыть"
              @click="showFreeAurumGateModal = false"
            >
              ✕
            </button>
          </div>
        </div>
        <div
          class="rounded-xl border border-white/[0.1] bg-zinc-900/85 px-3 py-4 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
        >
          <div class="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-black/40 ring-1 ring-white/10">
            <svg class="h-8 w-8 text-white/45" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M7 11V8a5 5 0 0 1 10 0v3"
                stroke="currentColor"
                stroke-width="1.6"
                stroke-linecap="round"
              />
              <rect x="6" y="11" width="12" height="10" rx="2" stroke="currentColor" stroke-width="1.6" />
              <circle cx="12" cy="16" r="1.2" fill="currentColor" />
            </svg>
          </div>
          <p class="text-[13px] font-semibold leading-tight text-white">Токены недоступны на Free-тарифе</p>
          <p class="mt-2 text-[11px] leading-snug text-white/55">
            Токены нужны для рассылок, автопостинга и других функций.
          </p>
        </div>
        <button
          type="button"
          class="relative mt-3 w-full overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-white text-center shadow-[0_10px_32px_-6px_rgba(243,156,18,0.65),0_4px_16px_-4px_rgba(108,52,131,0.5),inset_0_1px_0_rgba(255,255,255,0.28)] transition active:scale-[0.99]"
          style="
            background: linear-gradient(
              90deg,
              #f39c12 0%,
              #df5a3b 34%,
              #b043cc 56%,
              #5c2dc1 74%,
              #2a1a83 100%
            );
          "
          @click="openPremiumLandingFromAurumGate"
        >
          Получить Premium
        </button>
        <ul class="mt-3 space-y-2.5 text-left text-[11px] leading-snug text-white/75">
          <li class="flex items-start gap-2.5">
            <span class="mt-0.5 inline-flex h-[1.375rem] w-[1.375rem] shrink-0 items-center justify-center" aria-hidden="true">
              <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path
                  d="M7.5 11V8a4.5 4.5 0 0 1 9 0v3"
                  stroke="#ff9f1c"
                  stroke-width="1.85"
                  stroke-linecap="round"
                />
                <rect x="5.5" y="11" width="13" height="10.5" rx="2.2" stroke="#ff9f1c" stroke-width="1.85" />
              </svg>
            </span>
            <span>Разблокируйте все возможности</span>
          </li>
          <li class="flex items-start gap-2.5">
            <span class="mt-0.5 inline-flex h-[1.375rem] w-[1.375rem] shrink-0 items-center justify-center" aria-hidden="true">
              <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path
                  d="M13 2.25 5.25 13.25h5.35l-1.35 8.5 8.75-11.5H12.9L13 2.25z"
                  stroke="#5cff5c"
                  stroke-width="1.75"
                  stroke-linejoin="round"
                  stroke-linecap="round"
                />
              </svg>
            </span>
            <span>Делайте рассылки и автопостинг</span>
          </li>
          <li class="flex items-start gap-2.5">
            <span class="mt-0.5 inline-flex h-[1.375rem] w-[1.375rem] shrink-0 items-center justify-center" aria-hidden="true">
              <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path
                  d="M5.5 12.5 10 17l8.5-10"
                  stroke="#4ade80"
                  stroke-width="2.35"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </span>
            <span>Привлекайте клиентов и зарабатывайте</span>
          </li>
        </ul>
      </div>
    </div>

    <div
      v-if="showTokensInfoModal"
      class="fixed inset-0 z-[281] flex items-end justify-center bg-black/70 p-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] backdrop-blur-[3px] md:items-center md:pb-6"
      @click.self="showTokensInfoModal = false"
    >
      <div
        class="w-full max-w-lg overflow-hidden rounded-[1.25rem] border border-white/[0.14] bg-gradient-to-b from-zinc-900/75 to-zinc-950/92 p-4 text-slate-100 shadow-[0_28px_90px_-28px_rgba(0,0,0,0.9)] ring-1 ring-inset ring-white/[0.06] backdrop-blur-2xl"
        @click.stop
      >
        <div class="mb-3 flex items-center justify-between gap-2 border-b border-white/10 pb-2">
          <h3 class="text-sm font-semibold tracking-tight text-white">{{ tokensInfoTitle }}</h3>
          <button
            type="button"
            class="rounded-lg px-2 py-1 text-sm text-white/50 hover:bg-white/10 hover:text-white"
            @click="showTokensInfoModal = false"
          >
            ✕
          </button>
        </div>
        <div class="max-h-[min(65vh,26rem)] space-y-2.5 overflow-y-auto text-left text-[13px] leading-snug text-white/72">
          <p v-for="(tp, ti) in tokensInfoParagraphs" :key="`toki-${ti}`">{{ tp }}</p>
        </div>
      </div>
    </div>

    <div
      v-if="showPremiumPayMethodModal"
      class="fixed inset-0 z-[282] flex items-end justify-center bg-black/70 p-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] backdrop-blur-[3px] md:items-center md:pb-6"
      @click.self="closePremiumPayMethodModal"
    >
      <div
        class="w-full max-w-md overflow-hidden rounded-[1.25rem] border border-white/[0.14] bg-gradient-to-b from-zinc-900/90 to-zinc-950/95 p-4 text-slate-100 shadow-[0_28px_90px_-28px_rgba(0,0,0,0.9)] ring-1 ring-inset ring-white/[0.06] backdrop-blur-2xl"
        @click.stop
      >
        <div class="mb-1 flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <h3 class="text-base font-bold tracking-tight text-white">
                {{ premiumPayMethodFlow === 'tokens' ? 'Купить токены' : 'Способ оплаты' }}
              </h3>
              <button
                type="button"
                :class="tokensInfoBtnClass"
                title="Как проходит оплата"
                aria-label="Как проходит оплата"
                @click="openPremiumPayMethodInfo"
              >i</button>
            </div>
            <p class="mt-0.5 text-[13px] text-white/50">
              {{
                premiumPayMethodFlow === 'tokens'
                  ? 'Вы будете перенаправлены на защищенную страницу ЮKassa для покупки токенов'
                  : 'Вы будете перенаправлены на защищенную страницу ЮKassa'
              }}
            </p>
            <p
              v-if="premiumPayMethodSummary"
              class="mt-1.5 truncate text-[12px] font-semibold text-amber-200/90"
            >
              {{ premiumPayMethodSummary }}
            </p>
          </div>
          <button
            type="button"
            class="shrink-0 rounded-lg px-2 py-1 text-sm text-white/50 hover:bg-white/10 hover:text-white"
            aria-label="Закрыть"
            :disabled="premiumPayMethodProceedLoading"
            @click="closePremiumPayMethodModal"
          >
            ✕
          </button>
        </div>

        <div class="mt-4 space-y-2">
          <button
            type="button"
            class="flex w-full items-center gap-3 rounded-xl border px-3 py-3 text-left transition active:scale-[0.99]"
            :class="
              premiumPayMethodSelected === 'card'
                ? 'border-cyan-300/50 bg-cyan-500/[0.08] ring-1 ring-cyan-300/35'
                : 'border-white/[0.1] bg-white/[0.06] hover:border-white/20 hover:bg-white/[0.09]'
            "
            @click="premiumPayMethodSelected = 'card'"
          >
            <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-white/10 text-xl" aria-hidden="true">💳</span>
            <span class="min-w-0 flex-1">
              <span class="block text-[14px] font-bold text-white">Банковская карта / СБП</span>
              <span class="mt-0.5 block text-[12px] text-white/55">Visa, Mastercard, МИР · ЮKassa (СБП и др. — если включены в кассе)</span>
            </span>
            <span class="text-white/35" aria-hidden="true">{{ premiumPayMethodSelected === 'card' ? '✓' : '○' }}</span>
          </button>

          <button
            type="button"
            class="flex w-full items-center gap-3 rounded-xl border px-3 py-3 text-left transition active:scale-[0.99]"
            :class="
              premiumPayMethodSelected === 'stars'
                ? 'border-cyan-300/50 bg-cyan-500/[0.08] ring-1 ring-cyan-300/35'
                : 'border-white/[0.1] bg-white/[0.06] hover:border-white/20 hover:bg-white/[0.09]'
            "
            @click="premiumPayMethodSelected = 'stars'"
          >
            <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-amber-400/20 text-xl" aria-hidden="true">⭐</span>
            <span class="min-w-0 flex-1">
              <span class="block text-[14px] font-bold text-white">Telegram Stars</span>
              <span class="mt-0.5 block text-[12px] text-white/55">Скоро в приложении</span>
            </span>
            <span class="text-white/35" aria-hidden="true">{{ premiumPayMethodSelected === 'stars' ? '✓' : '○' }}</span>
          </button>
        </div>

        <div class="mt-4 space-y-1 border-t border-white/10 pt-3 text-[11px] text-white/55">
          <p class="flex items-center gap-2"><span class="text-emerald-400">✓</span><span>Безопасная оплата через ЮKassa</span></p>
          <p class="flex items-center gap-2"><span class="text-emerald-400">✓</span><span>Карты, СБП и другие способы</span></p>
          <p class="flex items-center gap-2"><span class="text-emerald-400">✓</span><span>Данные карты не хранятся в Guard</span></p>
        </div>

        <button
          type="button"
          class="relative w-full overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-white text-center shadow-[0_14px_42px_-14px_rgba(243,156,18,0.62),inset_0_1px_0_rgba(255,255,255,0.28)] transition active:scale-[0.99]"
          style="background: linear-gradient(90deg, #f39c12 0%, #df5a3b 34%, #b043cc 56%, #5c2dc1 74%, #2a1a83 100%);"
          :disabled="premiumPayMethodProceedLoading"
          @click="onPremiumPayMethodProceed"
        >
          {{ premiumPayMethodProceedLoading ? 'Готовим оплату...' : 'Перейти к оплате' }}
        </button>

        <p class="mt-2 text-center text-[10px] text-white/40">
          {{
            premiumPayMethodFlow === 'tokens'
              ? 'Нажимая кнопку, вы соглашаетесь с офертой и условиями покупки.'
              : 'Нажимая кнопку, вы соглашаетесь с офертой и условиями подписки.'
          }}
        </p>
      </div>
    </div>

    <div
      v-if="showPromoCodeModal"
      class="fixed inset-0 z-[289] flex items-end justify-center bg-black/78 p-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] backdrop-blur-[3px] md:items-center md:pb-6"
      @click.self="closePromoCodeModal"
    >
      <div
        class="w-full max-w-md rounded-[1.25rem] border border-white/[0.14] bg-gradient-to-b from-zinc-900/90 to-zinc-950/95 p-4 text-slate-100 shadow-[0_28px_90px_-28px_rgba(0,0,0,0.9)] ring-1 ring-inset ring-white/[0.06] backdrop-blur-2xl"
        @click.stop
      >
        <div class="mb-2 flex items-start justify-between gap-2">
          <div class="min-w-0">
            <h3 class="text-base font-bold tracking-tight text-white">Есть промокод?</h3>
            <p class="mt-0.5 text-[13px] text-white/55">Введите код и активируйте Premium.</p>
          </div>
          <button
            type="button"
            class="shrink-0 rounded-lg px-2 py-1 text-sm text-white/50 hover:bg-white/10 hover:text-white"
            aria-label="Закрыть"
            :disabled="promoLoading"
            @click="closePromoCodeModal"
          >
            ✕
          </button>
        </div>
        <div class="mt-3 flex gap-2">
          <input
            v-model="promoCode"
            type="text"
            placeholder="Промокод"
            class="min-w-0 flex-1 rounded-xl border border-white/[0.12] bg-white/[0.06] px-3 py-2.5 text-[14px] text-white placeholder:text-white/35 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-md"
          >
          <button
            type="button"
            class="shrink-0 rounded-xl border border-emerald-400/35 bg-emerald-500/20 px-3 py-2.5 text-[12px] font-bold text-emerald-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-md transition hover:bg-emerald-500/28 disabled:opacity-45"
            :disabled="promoLoading || !(promoCode || '').trim()"
            @click="applyPromo()"
          >
            {{ promoLoading ? '...' : 'Готово' }}
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="showPaymentRedirectScreen"
      class="fixed inset-0 z-[290] flex items-center justify-center bg-black/90 px-4"
    >
      <div class="w-full max-w-md rounded-[1.4rem] border border-white/10 bg-gradient-to-b from-zinc-900/95 to-black p-6 text-white shadow-[0_28px_90px_-28px_rgba(0,0,0,0.9)]">
        <div class="mx-auto flex h-28 w-28 items-center justify-center rounded-full border border-violet-500/35 bg-violet-500/10 shadow-[0_0_36px_-8px_rgba(139,92,246,0.55)]">
          <span class="text-5xl leading-none text-violet-300" aria-hidden="true">◌</span>
        </div>
        <h3 class="mt-6 text-center text-2xl font-bold tracking-tight">Переход на страницу оплаты</h3>
        <p class="mx-auto mt-3 max-w-xs text-center text-sm leading-relaxed text-white/65">
          Сейчас вы будете перенаправлены на защищённую страницу ЮKassa для завершения оплаты.
        </p>

        <div class="mx-auto mt-6 max-w-xs space-y-2 text-sm text-white/72">
          <p class="flex items-center gap-2"><span class="text-emerald-400">✓</span><span>Безопасное соединение</span></p>
          <p class="flex items-center gap-2"><span class="text-emerald-400">✓</span><span>Передача данных по защищённому каналу</span></p>
          <p class="flex items-center gap-2"><span class="text-emerald-400">✓</span><span>Мы не храним данные карты</span></p>
        </div>

        <p class="mt-6 text-center text-sm font-semibold text-violet-300">
          Открываем оплату через {{ paymentRedirectCountdown }}...
        </p>

        <button
          type="button"
          class="relative w-full overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-white text-center shadow-[0_14px_42px_-14px_rgba(243,156,18,0.62),inset_0_1px_0_rgba(255,255,255,0.28)] transition active:scale-[0.99]"
          style="background: linear-gradient(90deg, #f39c12 0%, #df5a3b 34%, #b043cc 56%, #5c2dc1 74%, #2a1a83 100%);"
          @click="proceedToPaymentNow"
        >
          Перейти к оплате сейчас
        </button>
      </div>
    </div>

    <div
      v-if="showPremiumActivatedModal"
      class="fixed inset-0 z-[291] flex items-center justify-center bg-black/88 px-4"
    >
      <div class="w-full max-w-md rounded-[1.4rem] border border-white/10 bg-gradient-to-b from-zinc-900/95 to-black p-5 text-white shadow-[0_28px_90px_-28px_rgba(0,0,0,0.9)]">
        <div class="mx-auto flex h-28 w-28 items-center justify-center rounded-full border border-emerald-400/45 bg-emerald-500/10 shadow-[0_0_36px_-8px_rgba(16,185,129,0.6)]">
          <span class="text-5xl leading-none" aria-hidden="true">🛡️</span>
        </div>

        <h3 class="mt-5 text-center text-[2rem] font-bold leading-tight">Premium активирован!</h3>
        <p class="mx-auto mt-2 max-w-xs text-center text-[15px] leading-relaxed text-white/70">
          Спасибо, что выбрали Guard. Теперь вам доступны все возможности защиты.
        </p>

        <div class="mt-5 space-y-2 rounded-xl border border-white/10 bg-white/[0.03] p-3 text-[14px] text-white/80">
          <p class="flex items-center gap-2"><span class="text-emerald-400">✓</span><span>Чат под защитой 24/7</span></p>
          <p class="flex items-center gap-2"><span class="text-emerald-400">✓</span><span>Все функции разблокированы</span></p>
          <p class="flex items-center gap-2"><span class="text-emerald-400">✓</span><span>Мы всегда рядом, если что-то нужно</span></p>
        </div>

        <button
          type="button"
          class="mt-5 w-full rounded-2xl bg-gradient-to-r from-violet-600 via-violet-500 to-indigo-600 py-3.5 text-[15px] font-extrabold text-white shadow-[0_14px_44px_-16px_rgba(124,58,237,0.72)] transition hover:brightness-105 active:scale-[0.99]"
          @click="closePremiumActivatedModalToHome"
        >
          Отлично!
        </button>

        <button
          type="button"
          class="mt-2 w-full text-center text-[13px] font-medium text-violet-300 underline decoration-violet-400/55 underline-offset-4 transition hover:text-violet-200"
          @click="onPremiumActivatedGoSubscription"
        >
          Моя подписка
        </button>
      </div>
    </div>

    <SecurityPinGateModal
      :open="pinGateOpen"
      :busy="pinGateBusy"
      :error="pinGateError"
      :model-value="pinGateInput"
      @update:model-value="pinGateInput = $event"
      @submit="submitPinGate"
      @cancel="cancelPinGate"
    />

  </div>
</template>

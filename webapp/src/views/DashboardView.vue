<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useApi, messageFromApiError } from '../composables/useApi'
import { api as rawApi } from '../api/client'
import NavIcon from '../components/NavIcon.vue'
import GuardBlueLoadingState from '../components/GuardBlueLoadingState.vue'
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
const { t, tm } = useI18n()
const { api, loading, error, fetchSilent, hasInitData } = useApi()
const { showToast } = useToast()
const bootError = ref('')
const dashCtx = useDashboardSection()
/** Единое сравниваемое значение для шаблона (вкладки главной). */
const dashSection = computed(() => dashCtx.dashboardSection.value || 'account')
const billingFromGroupStats = dashCtx.billingFromGroupStats
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
const DASHBOARD_STATS_PERIOD_OPTIONS = computed(() => [
  { key: 'today', label: t('dashboard.period.today') },
  { key: '7d', label: t('dashboard.period.7d') },
  { key: '14d', label: t('dashboard.period.14d') },
  { key: '30d', label: t('dashboard.period.30d') },
])

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
  if (dashCtx.dashboardSection.value !== 'account' || !accountShowBroadcastMiniCard.value) return
  statBroadcastNudgeTimer = setInterval(() => {
    if (homeStatBroadcastSlide.value !== 0) return
    if (statBroadcastDragging.value) return
    statBroadcastNudgePx.value = -11
    setTimeout(() => {
      statBroadcastNudgePx.value = 0
    }, 380)
  }, 3000)
}

const currentUpdateSlide = computed(() => UPDATES_SLIDES.value[updatesIndex.value] || UPDATES_SLIDES.value[0])

function restartUpdatesRotation() {
  if (updatesTimer) {
    clearInterval(updatesTimer)
    updatesTimer = null
  }
  if (dashCtx.dashboardSection.value !== 'account') return
  updatesTimer = setInterval(() => {
    updatesIndex.value = (updatesIndex.value + 1) % UPDATES_SLIDES.value.length
  }, 4000)
}

function selectUpdatesSlide(i) {
  const n = UPDATES_SLIDES.value.length
  if (i < 0 || i >= n) return
  updatesIndex.value = i
  restartUpdatesRotation()
}

function applyUpdatePrimaryAction() {
  const slide = currentUpdateSlide.value
  const a = slide?.primaryAction
  if (!a) return
  if (a === 'partner') dashCtx.setDashboardSection('partner')
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
  if (key === 'ban') return t('dashboard.actions.ban')
  if (key === 'mute') return t('dashboard.actions.mute')
  if (key === 'observe') return t('dashboard.actions.observe')
  return t('dashboard.actions.delete')
}

/** Человекочитаемая причина срабатывания фильтра (ключи из moderation_logs.reason). */
function moderationReasonRu(reason) {
  const raw = String(reason || '').trim().toLowerCase()
  if (!raw) return '—'
  const base = raw.replace(/_newbie$/i, '')
  const keyFor = (k) => {
    const direct = t(`dashboard.reasons.${k}`)
    return direct && direct !== `dashboard.reasons.${k}` ? direct : null
  }
  const knownKeys = new Set([
    'link', 'media', 'buttons', 'mention', 'stopword', 'profanity', 'jobs', 'casino',
    'politics', 'religion', 'esoteric', 'silence', 'antinakrutka', 'captcha', 'flood',
    'global_antispam', 'raid', 'spam', 'forward',
  ])
  if (knownKeys.has(raw)) return keyFor(raw) || raw
  if (knownKeys.has(base)) {
    const labelBase = keyFor(base) || base
    return raw.endsWith('_newbie')
      ? t('dashboard.reasons.newbie_suffix', { base: labelBase })
      : labelBase
  }
  if (base.includes('profanity')) return t('dashboard.reasons.profanity')
  if (base.includes('stopword')) return t('dashboard.reasons.stopword')
  if (base.includes('newbie')) return t('dashboard.reasons.newbies')
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
    const fragLabel = t('dashboard.journal_ui.snippet')
    return `${cat} · ${fragLabel}: «${snip}»`
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
    showToast(kind === 'unban' ? t('dashboard.toasts.unban_ok') : t('dashboard.toasts.unmute_ok'))
    await loadGroupActivityFull()
  } catch (e) {
    const d = e?.body?.detail || e?.message || t('errors.action_failed')
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
  const groupFallback = t('dashboard.home_shell.group_fallback')
  const map = new Map((activityChats.value || []).map((c) => [Number(c.id || 0), {
    chat_id: Number(c.id || 0),
    chat_title: String(c.title || c.id || groupFallback),
    total: 0,
    deleted: 0,
    muted: 0,
    banned: 0,
    observed: 0,
  }]))
  for (const item of activityJournal.value || []) {
    const chatId = Number(item?.chat_id || 0)
    const title = String(item?.chat_title || chatId || groupFallback)
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
  return t('dashboard.period.fallback')
})

/** Все события журнала по выбранной группе и периоду (удаление / мут / бан). */
const groupJournalForModal = computed(() => {
  const cid = Number(groupActivityChatId.value || 0)
  if (!cid) return []
  return (groupJournalItems.value || []).filter((item) => Number(item?.chat_id || 0) === cid)
})

function filterStatCardTone(tone) {
  const k = String(tone || 'emerald')
  if (k === 'rose') {
    return 'border-rose-500/70 bg-rose-950/35'
  }
  if (k === 'amber') {
    return 'border-amber-500/70 bg-amber-950/30'
  }
  if (k === 'violet') {
    return 'border-violet-500/70 bg-violet-950/30'
  }
  if (k === 'slate') {
    return 'border-slate-500/70 bg-slate-900/50'
  }
  return 'border-emerald-400/80 bg-emerald-950/35'
}

const totalTokens = computed(() => {
  const total = Number(me.value?.aurum_tokens || 0) + Number(me.value?.partner_tokens || 0)
  return String(Math.max(0, Math.round(total)))
})
const tariffIsPremium = computed(() => ['premium', 'pro', 'business'].includes((me.value?.tariff || 'free').toLowerCase()))
/** 10-дневный Premium-триал: можно ли активировать (FREE + ни разу не активировал + окно открыто). */
const trialEligible = computed(() => !!me.value && !!me.value.trial_eligible)
/** Триал сейчас идёт (юзер активировал, осталось N дней Premium бесплатно). */
const trialActive = computed(() => !!me.value && !!me.value.trial_active)
/** Кнопка-замена «Усилить защиту»: показывать ли «🚀 Попробовать 10 дней бесплатно». */
const showTrialCta = computed(() => !tariffIsPremium.value && trialEligible.value)
/** Сколько дней осталось в активном Premium-триале. */
const trialRemainingDays = computed(() => Number(me.value?.trial_remaining_days || 0))
/** Free-аккаунт: на главной не показываем «живую» сводку статистики — нули и пояснение (как в кабинете Guard). */
const dashboardStatsPremiumLocked = computed(() => !!me.value && !me.value.is_premium)
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
  const tariffCode = String(activitySummary.value?.tariff || 'free').toLowerCase()
  const premium = ['premium', 'pro', 'business'].includes(tariffCode)
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
      label: t('dashboard.hero.protection_weak'),
      fillSegmentClass: 'bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.35)]',
      labelClass: 'text-rose-400',
    },
    2: {
      label: t('dashboard.hero.protection_basic'),
      fillSegmentClass: 'bg-orange-500 shadow-[0_0_6px_rgba(249,115,22,0.32)]',
      labelClass: 'text-orange-400',
    },
    3: {
      label: t('dashboard.hero.protection_medium'),
      fillSegmentClass: 'bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.38)]',
      labelClass: 'text-amber-300',
    },
    4: {
      label: t('dashboard.hero.protection_strong'),
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
  const isEn = t('common.locale_code') === 'en'
  const d = Math.max(0, Math.round(Number(activitySummary.value?.today?.deleted || 0)))
  if (d === 0) return isEn ? '0 h' : '0 ч'
  const hours = (d * 25) / 1500
  if (hours < 0.05) return isEn ? '< 0.1 h' : '< 0,1 ч'
  return isEn
    ? `${hours.toFixed(1)} h`
    : `${hours.toFixed(1).replace('.', ',')} ч`
})

/** Сравнение с предыдущим днём (понятные формулировки, не «к вчера»). */
function statTrendPctLine(todayVal, yesterdayVal) {
  const td = Math.max(0, Math.round(Number(todayVal) || 0))
  const y = Math.max(0, Math.round(Number(yesterdayVal) || 0))
  if (td === 0 && y === 0) return t('dashboard.hero.no_data')
  if (y === 0)
    return td > 0
      ? t('dashboard.hero.vs_yesterday_zero_today')
      : t('dashboard.hero.vs_yesterday_zero_diff')
  const pct = Math.round(((td - y) / y) * 100)
  const sign = pct > 0 ? '+' : ''
  return t('dashboard.hero.vs_yesterday_pct', { sign, pct })
}

const statTrendDeleted = computed(() =>
  statTrendPctLine(activitySummary.value?.today?.deleted, activitySummary.value?.yesterday?.deleted),
)
const statTrendSaved = computed(() =>
  statTrendPctLine(activitySummary.value?.today?.deleted, activitySummary.value?.yesterday?.deleted),
)
const statTrendJoins = computed(() => {
  const td = Math.max(0, Math.round(Number(activitySummary.value?.today?.joins ?? 0)))
  const y = Math.max(0, Math.round(Number(activitySummary.value?.yesterday?.joins ?? 0)))
  if (td === 0 && y === 0) return t('dashboard.hero.no_joins')
  const diff = td - y
  if (diff === 0) return t('dashboard.hero.vs_yesterday_same')
  if (diff > 0) return t('dashboard.hero.vs_yesterday_more', { n: diff })
  return t('dashboard.hero.vs_yesterday_less', { n: Math.abs(diff) })
})

const statsCardUsesPeriod = computed(() => dashboardStatsPeriod.value !== 'today')
const statsCardDeleted = computed(() => {
  if (dashboardStatsPremiumLocked.value) return 0
  if (!statsCardUsesPeriod.value) {
    return Math.max(0, Math.round(Number(activitySummary.value?.today?.deleted ?? 0)))
  }
  return Math.max(0, Math.round(Number(dashboardPeriodBreakdown.value?.total_deleted ?? 0)))
})
const statsCardJoins = computed(() => {
  if (dashboardStatsPremiumLocked.value) return 0
  if (!statsCardUsesPeriod.value) {
    return Math.max(0, Math.round(Number(activitySummary.value?.today?.joins ?? 0)))
  }
  return Math.max(0, Math.round(Number(dashboardPeriodBreakdown.value?.total_joined ?? 0)))
})
const statsCardSavedHoursLabel = computed(() => {
  const isEn = t('common.locale_code') === 'en'
  if (dashboardStatsPremiumLocked.value) return isEn ? '0 h' : '0 ч'
  const d = statsCardDeleted.value
  if (d === 0) return isEn ? '0 h' : '0 ч'
  const hours = (d * 25) / 1500
  if (hours < 0.05) return isEn ? '< 0.1 h' : '< 0,1 ч'
  return isEn ? `${hours.toFixed(1)} h` : `${hours.toFixed(1).replace('.', ',')} ч`
})
const statsCardTrendDeleted = computed(() => {
  if (dashboardStatsPremiumLocked.value) return t('dashboard.hero.need_premium')
  if (statsCardUsesPeriod.value) {
    const p = DASHBOARD_STATS_PERIOD_OPTIONS.value.find((x) => x.key === dashboardStatsPeriod.value)
    return p
      ? t('dashboard.hero.for_period', { period: p.label.toLowerCase() })
      : t('dashboard.hero.for_period_fallback')
  }
  return statTrendDeleted.value
})
const statsCardTrendSaved = computed(() => {
  if (dashboardStatsPremiumLocked.value) return t('dashboard.hero.need_premium')
  if (statsCardUsesPeriod.value) {
    const p = DASHBOARD_STATS_PERIOD_OPTIONS.value.find((x) => x.key === dashboardStatsPeriod.value)
    return p
      ? t('dashboard.hero.for_period', { period: p.label.toLowerCase() })
      : t('dashboard.hero.for_period_fallback')
  }
  return statTrendSaved.value
})
const statsCardTrendJoins = computed(() => {
  if (dashboardStatsPremiumLocked.value) return t('dashboard.hero.need_premium')
  if (statsCardUsesPeriod.value) {
    if (statsCardJoins.value > 0) {
      return t('dashboard.home_shell.joins_total_suffix', { n: statsCardJoins.value })
    }
    return t('dashboard.hero.no_joins')
  }
  return statTrendJoins.value
})

/** Доля занятых слотов групп по тарифу (вместо «точность AI»). */
const statGroupsLimitPercent = computed(() => {
  if (dashboardStatsPremiumLocked.value) return '0%'
  const p = Number(activityGroupsProgress.value || 0)
  if (!Number.isFinite(p)) return '—'
  return `${Math.max(0, Math.min(100, Math.round(p)))}%`
})

const statGroupsLimitFoot = computed(() => {
  if (dashboardStatsPremiumLocked.value) return t('dashboard.statsCard.slots_status_premium_needed')
  const left = Math.max(0, Math.round(Number(activityGroupsLimit.value || 0) - Number(activityGroupsCount.value || 0)))
  if (Number(activityGroupsLimit.value || 0) <= 0) return t('dashboard.statsCard.slots_status_no_tariff')
  if (left === 0) return t('dashboard.statsCard.slots_status_limit')
  if (left <= 3) return t('dashboard.statsCard.slots_status_low')
  return t('dashboard.statsCard.slots_status_ok')
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
  if (t('common.locale_code') === 'en') {
    return t(n === 1 ? 'dashboard.counters.n_chats_one' : 'dashboard.counters.n_chats', { n })
  }
  const k = n % 100
  const l = n % 10
  if (k > 10 && k < 20) return t('dashboard.counters.n_chats', { n })
  if (l === 1) return t('dashboard.counters.n_chats_one', { n })
  if (l >= 2 && l <= 4) return t('dashboard.counters.n_chats_few', { n })
  return t('dashboard.counters.n_chats', { n })
}

function ruGroupsProtectedLabel(count) {
  const n = Math.abs(Math.trunc(Number(count) || 0))
  if (t('common.locale_code') === 'en') {
    return t(n === 1 ? 'dashboard.counters.n_groups_one' : 'dashboard.counters.n_groups', { n })
  }
  const k = n % 100
  const l = n % 10
  if (k > 10 && k < 20) return t('dashboard.counters.n_groups', { n })
  if (l === 1) return t('dashboard.counters.n_groups_one', { n })
  if (l >= 2 && l <= 4) return t('dashboard.counters.n_groups_few', { n })
  return t('dashboard.counters.n_groups', { n })
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

const ACCOUNT_HOME_PREMIUM_BULLETS = computed(() => [
  t('dashboard.hero.premium_feature_ai'),
  t('dashboard.hero.premium_feature_autoban'),
  t('dashboard.hero.premium_feature_support'),
  t('dashboard.hero.premium_feature_stats'),
])

/** Лента обновлений: от новых к более ранним; на главной — только первые UPDATES_HOME_PREVIEW_N */
const UPDATES_HOME_PREVIEW_N = 3

const UPDATES_SLIDES = computed(() => [
  {
    key: 'stats_growth',
    version: '2.4',
    publishedAt: '2026-05-06T15:30:00+03:00',
    headline: t('dashboard.feed_items.stats.headline'),
    teaser: t('dashboard.feed_items.stats.teaser'),
    body: t('dashboard.feed_items.stats.body'),
    primaryLabel: null,
    primaryAction: null,
    imageUrl: null,
  },
  {
    key: 'filters_wave',
    version: '2.3',
    publishedAt: '2026-05-05T18:00:00+03:00',
    headline: t('dashboard.feed_items.filters.headline'),
    teaser: t('dashboard.feed_items.filters.teaser'),
    body: t('dashboard.feed_items.filters.body'),
    primaryLabel: null,
    primaryAction: null,
    imageUrl: null,
  },
  {
    key: 'launch_public',
    version: '2.2',
    publishedAt: '2026-05-04T12:00:00+03:00',
    headline: t('dashboard.feed_items.launch.headline'),
    teaser: t('dashboard.feed_items.launch.teaser'),
    body: t('dashboard.feed_items.launch.body'),
    primaryLabel: null,
    primaryAction: null,
    imageUrl: null,
  },
  {
    key: 'earn',
    version: '2.1',
    publishedAt: '2026-05-03T11:00:00+03:00',
    headline: t('dashboard.feed_items.referrals.headline'),
    teaser: t('dashboard.feed_items.referrals.teaser'),
    body: t('dashboard.feed_items.referrals.body'),
    primaryLabel: t('dashboard.feed_items.referrals.primary'),
    primaryAction: 'partner',
    imageUrl: null,
  },
  {
    key: 'casino',
    version: '2.0',
    publishedAt: '2026-05-02T09:30:00+03:00',
    headline: t('dashboard.feed_items.casino.headline'),
    teaser: t('dashboard.feed_items.casino.teaser'),
    body: t('dashboard.feed_items.casino.body'),
    primaryLabel: t('dashboard.feed_items.casino.primary'),
    primaryAction: 'protection',
    imageUrl: null,
  },
  {
    key: 'premium_cabinet',
    version: '1.9',
    publishedAt: '2026-05-01T14:15:00+03:00',
    headline: t('dashboard.feed_items.cabinet.headline'),
    teaser: t('dashboard.feed_items.cabinet.teaser'),
    body: t('dashboard.feed_items.cabinet.body'),
    primaryLabel: null,
    primaryAction: null,
    imageUrl: null,
  },
  {
    key: 'ai',
    version: '1.8',
    publishedAt: '2026-04-28T10:00:00+03:00',
    headline: t('dashboard.feed_items.ai.headline'),
    teaser: t('dashboard.feed_items.ai.teaser'),
    body: t('dashboard.feed_items.ai.body'),
    primaryLabel: null,
    primaryAction: null,
    imageUrl: null,
  },
])

const updatesHomePreview = computed(() => UPDATES_SLIDES.value.slice(0, UPDATES_HOME_PREVIEW_N))

const GROUP_STATS_PRESETS = computed(() => [
  { key: '24h', label: t('dashboard.period.24h') },
  { key: '7d', label: t('dashboard.period.7d_short') },
  { key: '30d', label: t('dashboard.period.30d_short') },
  { key: '6m', label: t('dashboard.period.6m') },
  { key: '1y', label: t('dashboard.period.1y') },
])
function formatPlanRub(amount) {
  const n = Math.round(Number(amount) || 0)
  const loc = t('common.locale_code') === 'en' ? 'en-US' : 'ru-RU'
  return n.toLocaleString(loc)
}

/** @returns {string[]} */
function infoParagraphList(key) {
  const raw = tm(key)
  return Array.isArray(raw) ? raw.map((x) => String(x)) : []
}

/** Подарок AURUM с Premium: сумма ₽ / 4 ✨ (в 2 раза меньше старого «₽/2»). */
const SUBSCRIPTION_GIFT_RUB_PER_AURUM = 4

const PREMIUM_PLANS_SPEC = [
  { months: 1, icon: '🛡', priceRub: 490, savingsRub: 0 },
  { months: 3, icon: '⚡', priceRub: 990, savingsRub: 480 },
  { months: 6, icon: '📅', priceRub: 1590, savingsRub: 1350 },
  { months: 12, icon: '👑', priceRub: 2790, savingsRub: 3090 },
  { months: 24, icon: '💎', priceRub: 4790, savingsRub: 6970 },
  { months: 72, icon: '🚀', priceRub: 10990, savingsRub: 24290 },
]

const premiumPlansCatalog = computed(() =>
  PREMIUM_PLANS_SPEC.map((p) => {
    const savings =
      p.savingsRub > 0
        ? t('dashboard.plans.savings_full', { rub: formatPlanRub(p.savingsRub) })
        : ''
    return {
      months: p.months,
      icon: p.icon,
      label: t(`dashboard.plans.months_${p.months}`),
      price: `${formatPlanRub(p.priceRub)} ₽`,
      priceRub: p.priceRub,
      savings,
      savingsRub: p.savingsRub,
    }
  }),
)

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
  const p = premiumPlansCatalog.value.find((x) => x.months === m)
  return p ? `${p.label} · ${p.price}` : ''
})

/**
 * Лендинг «Free vs Premium»: сверху рефералка и фильтр ссылок/упоминаний (во Free тоже ✓),
 * затем остальное; внизу лимит чатов. Premium в рефералке: «3 уровня» зелёным.
 */
const billingCompareRows = computed(() => [
  { id: 'referral', kind: 'referral', label: t('dashboard.referralRow.label') },
  {
    id: 'links_mentions',
    kind: 'ok',
    label: t('dashboard.sections.links_mentions'),
    free: 'ok',
    premium: 'ok',
  },
  { id: 'panel', kind: 'ok', label: t('dashboard.sections.panel'), free: 'ok', premium: 'ok' },
  { id: 'spam', kind: 'ok', label: t('dashboard.sections.spam'), free: 'no', premium: 'ok' },
  { id: 'autodel', kind: 'ok', label: t('dashboard.sections.autodel'), free: 'no', premium: 'ok' },
  { id: 'bcast', kind: 'ok', label: t('dashboard.sections.bcast'), free: 'no', premium: 'ok' },
  { id: 'autopost', kind: 'ok', label: t('dashboard.sections.autopost'), free: 'no', premium: 'ok' },
  { id: 'stats', kind: 'ok', label: t('dashboard.sections.stats'), free: 'no', premium: 'ok' },
  { id: 'reports_track', kind: 'ok', label: t('dashboard.sections.reports_track'), free: 'no', premium: 'ok' },
  { id: 'support', kind: 'ok', label: t('dashboard.sections.support'), free: 'no', premium: 'ok' },
  { id: 'chat_limit', kind: 'limits', label: t('dashboard.sections.chat_limit') },
])

const LANDING_PLAN_UI = [
  { months: 1 },
  { months: 3 },
  { months: 6 },
  { months: 12, tagKey: 'popular' },
]

const landingPlanShowcase = computed(() =>
  LANDING_PLAN_UI.map((ui) => {
    const plan = premiumPlansCatalog.value.find((p) => p.months === ui.months)
    if (!plan) return null
    const discountLabel = Number(plan.months) === 1 ? '' : premiumSavingsCornerBadge(plan)
    const tag =
      ui.tagKey === 'popular'
        ? t('dashboard.plans.popular_tag')
        : ui.tagKey === 'best'
          ? t('dashboard.plans.best_tag')
          : ''
    return { ...plan, discountLabel, tag }
  }).filter(Boolean),
)

const landingPlanCards = computed(() => {
  const base = landingPlanShowcase.value
  if (!showAllLandingPlans.value) return base
  const featuredMonths = new Set(base.map((x) => Number(x.months)))
  const extra = premiumPlansCatalog.value
    .filter((p) => !featuredMonths.has(Number(p.months)))
    .map((p) => ({
      ...p,
      discountLabel: premiumSavingsCornerBadge(p),
      tag: Number(p.months) === 24 ? t('dashboard.plans.best_tag') : '',
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

/** Короткая подпись для угла карточки: «−480 ₽» */
function premiumSavingsCornerBadge(plan) {
  const rub = Number(plan?.savingsRub ?? 0)
  if (!rub) return ''
  return t('dashboard.plans.savings_short', { rub: formatPlanRub(rub) })
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
          : t('errors.cannot_load_profile')
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
  if (!dashCtx.dashboardSection.value) dashCtx.setDashboardSection('account')
  if (dashCtx.dashboardSection.value === 'partner') {
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
  // Открыть лендинг биллинга и автоматически активировать триал из ?trial=1
  // (DM-кнопка «🚀 Попробовать 10 дней бесплатно» из reminders).
  if (String(route.query?.trial || '') === '1') {
    try {
      const q = { ...route.query }
      delete q.trial
      router.replace({ path: route.path, query: q }).catch(() => {})
    } catch { /* */ }
    if (trialEligible.value && !tariffIsPremium.value) {
      try { await activateTrialClick() } catch { /* */ }
    } else if (trialActive.value) {
      showToast(t('dashboard.trial.already_active_toast'))
    }
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
    const sec = dashCtx.dashboardSection.value || 'account'
    if (sec !== 'account' && sec !== 'subscription') return
    if (!accountShowBroadcastMiniCard.value) return
    void loadBroadcastMiniSnapshot()
  }, 280)
}

watch(
  () => [dashCtx.dashboardSection.value, accountShowBroadcastMiniCard.value, me.value?.telegram_id, route.path],
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
    if (
      sec === 'billing' ||
      sec === 'partner' ||
      sec === 'account' ||
      sec === 'subscription' ||
      sec === 'tokens'
    ) {
      dashCtx.setDashboardSection(sec)
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

watch(dashCtx.dashboardSection, (section) => {
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
  showToast(t('dashboard.toasts.choose_period'))
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
      if (shouldAskPinForAction('payments')) showToast(t('errors.pin_required'))
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
  showToast(t('dashboard.toasts.stars_soon'))
}

const billingScrollTargets = {
  plans: () => billingPremiumPlansRef.value,
  pitch: () => billingPremiumPitchRef.value,
  compare: () => billingPremiumCompareRef.value,
  landing: () => billingLandingPlansRef.value,
}

watch(
  () =>
    `${dashCtx.dashboardSection.value}|${String(route.query.scroll || '').trim().toLowerCase()}|${me.value ? '1' : '0'}`,
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
  if (raw === 'tokens_purchase') return t('history.kinds.tokens_purchase')
  if (raw === 'broadcast_bonus') return t('history.kinds.broadcast_bonus')
  if (raw === 'broadcast_sub') return t('history.kinds.broadcast_sub')
  if (raw === 'daily_burn') return t('history.kinds.daily_burn')
  if (raw === 'bonus_to_sub') return t('history.kinds.bonus_to_sub')
  if (raw === 'bonus_to_sub_target') return t('history.kinds.bonus_to_sub_target')
  return raw
}

async function ensurePartnerData() {
  if (partnerData.value || partnerLoading.value) return
  partnerLoading.value = true
  partnerError.value = ''
  try {
    partnerData.value = await rawApi.referral()
  } catch (e) {
    partnerError.value = String(e?.body?.detail || e?.message || t('dashboard.toasts.partner_load_failed'))
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
  const tok = Number(tokens || 0)
  if (!tok) return
  payLoadingTokenPack.value = tok
  try {
    const r = await fetchSilent(() => api.yookassaCreateTokensPayment(tok))
    const url = r?.confirmation_url
    if (!url) {
      showToast(t('errors.payment_link_missing'))
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
  const n = Number(tokens || 0)
  if (!n) return
  selectedTokenPack.value = selectedTokenPack.value === n ? null : n
}

function continueTokenPackCheckout() {
  const tok = Number(selectedTokenPack.value || 0)
  if (!tok) {
    showToast(t('dashboard.toasts.select_pack'))
    return
  }
  buyTokenPackYookassa(tok)
}

async function buyTokenPackAdminTest(tokens) {
  const tk = Number(tokens || 0)
  if (!tk) return
  const okPin = await requestPinIfNeeded('payments')
  if (!okPin) {
    if (shouldAskPinForAction('payments')) showToast(t('errors.pin_required'))
    return
  }
  testTokenPayLoading.value = true
  try {
    const r = await fetchSilent(() => rawApi.adminTestCreateTokensPayment(tk))
    await openYookassaUrlFromResponse(r)
  } finally {
    testTokenPayLoading.value = false
  }
}

const AURUM_LIST_RUB_PER_TOKEN = 2.0

function showAurumTokensHelp() {
  const packs = tokenPacks.value || []
  const sample = packs[0]
  let exampleSuffix = ''
  if (sample && Number(sample.tokens) > 0 && sample.price_rub != null) {
    const per = Number(sample.price_rub) / Number(sample.tokens)
    exampleSuffix = t('dashboard.info.aurum_example_suffix', {
      tokens: Number(sample.tokens),
      rub: Math.round(Number(sample.price_rub)),
      per: per.toFixed(2),
    })
  }
  aurumHelpParagraphs.value = [
    t('dashboard.info.aurum_p0'),
    t('dashboard.info.aurum_p1', { rate: AURUM_LIST_RUB_PER_TOKEN, example_suffix: exampleSuffix }),
    t('dashboard.info.aurum_p2'),
  ]
  showAurumHelpModal.value = true
}

const tokensInfoBtnClass =
  'inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-white/20 bg-white/[0.06] text-[9px] font-extrabold text-white/80 shadow-[inset_0_1px_0_rgba(255,255,255,0.1)] backdrop-blur-md transition hover:bg-white/[0.11] active:scale-95'

const tokensInfoToolbarClass =
  'inline-flex shrink-0 items-center gap-0.5 rounded-full border border-white/[0.1] bg-black/30 px-0.5 py-0.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-md'

const tokensInfoBtnAmberClass =
  'inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-amber-400/40 bg-amber-950/45 text-[9px] font-extrabold text-amber-100 shadow-[inset_0_1px_0_rgba(251,191,36,0.12)] backdrop-blur-md transition hover:bg-amber-900/35 active:scale-95'

function openTokensSubscriptionInfo() {
  tokensInfoTitle.value = t('dashboard.info.tokens_subscription_title')
  tokensInfoParagraphs.value = infoParagraphList('dashboard.info.tokens_subscription_body')
  showTokensInfoModal.value = true
}

function openTokensCheckoutInfo() {
  tokensInfoTitle.value = t('dashboard.info.tokens_checkout_title')
  tokensInfoParagraphs.value = infoParagraphList('dashboard.info.tokens_checkout_body')
  showTokensInfoModal.value = true
}

function openTokensAdminTestInfo() {
  tokensInfoTitle.value = t('dashboard.info.tokens_test_title')
  tokensInfoParagraphs.value = infoParagraphList('dashboard.info.tokens_test_body')
  showTokensInfoModal.value = true
}

function openPremiumHeaderInfo() {
  tokensInfoTitle.value = t('dashboard.info.premium_header_title')
  const introArr = infoParagraphList('dashboard.info.premium_header_intro')
  const bullets = premiumPlansCatalog.value
    .filter((p) => p.savings)
    .map((p) =>
      t('dashboard.info.premium_plan_bullet', { label: p.label, price: p.price, savings: p.savings }),
    )
  tokensInfoParagraphs.value = [...introArr, ...bullets]
  showTokensInfoModal.value = true
}

function openPremiumPayMethodInfo() {
  tokensInfoTitle.value = t('dashboard.info.pay_flow_title')
  const key =
    premiumPayMethodFlow.value === 'tokens'
      ? 'dashboard.info.pay_flow_tokens'
      : 'dashboard.info.pay_flow_subscribe'
  tokensInfoParagraphs.value = infoParagraphList(key)
  showTokensInfoModal.value = true
}

function openPremiumAutorenewInfo() {
  tokensInfoTitle.value = t('dashboard.info.autorenew_title')
  tokensInfoParagraphs.value = infoParagraphList('dashboard.info.autorenew_body')
  showTokensInfoModal.value = true
}

function openPremiumTestTariffInfo() {
  tokensInfoTitle.value = t('dashboard.info.test_tariff_title')
  tokensInfoParagraphs.value = infoParagraphList('dashboard.info.test_tariff_body')
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
  () => dashCtx.dashboardSection.value,
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
      if (!hasInitData.value || !me.value) return
      if (Date.now() - lastActivitySummaryOkAt > 4500) refreshActivitySummarySilent()
    }
  },
  { immediate: true },
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
      alert(t('dashboard.partner_ui.link_copied'))
      return
    }
  } catch {
    //
  }
  alert(t('dashboard.partner_ui.link_copy_manual'))
}

function sharePartnerLink() {
  const link = String(partnerData.value?.ref_link || '')
  if (!link) return
  fetchSilent(() => api.referralShareHit()).catch(() => {})
  const text = t('dashboard.partner_ui.share_text')
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
  return t('dashboard.partner_ui.user_fallback')
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
  dashCtx.setDashboardSection('account')
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
  groupActivityTitle.value = String(row?.chat_title || t('dashboard.home_shell.chat_fallback', { id: cid }))
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
  dashCtx.setDashboardSection('billing')
  showGroupActivityModal.value = false
  showActivityModal.value = false
}

async function backFromBillingToGroupStats() {
  billingFromGroupStats.value = false
  dashCtx.setDashboardSection('account')
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
    dashCtx.setDashboardSection('billing')
    const q = { ...route.query, section: 'billing' }
    delete q.scroll
    void router.push({ path: '/', query: q })
  }
}

const trialActivating = ref(false)

async function activateTrialClick() {
  if (trialActivating.value) return
  trialActivating.value = true
  try {
    const res = await rawApi.activateTrial()
    if (res?.already_active) {
      showToast(t('dashboard.trial.already_active_toast'))
    } else {
      showToast(t('dashboard.trial.activated_toast', { n: Number(res?.trial_remaining_days || 10) }))
    }
    try {
      const fresh = await rawApi.me()
      applyMeState(fresh)
    } catch (_) {
      // Свежие данные подтянутся в следующем тике — не критично.
    }
  } catch (e) {
    const detail = String(e?.body?.detail || e?.message || '').toLowerCase()
    let key = 'dashboard.trial.error_generic'
    if (detail.includes('trial_trial_already_used') || detail.includes('trial_already_used')) {
      key = 'dashboard.trial.error_already_used'
    } else if (detail.includes('trial_window_closed') || detail.includes('window_closed')) {
      key = 'dashboard.trial.error_window_closed'
    } else if (detail.includes('trial_active_subscription') || detail.includes('active_subscription')) {
      key = 'dashboard.trial.error_active_subscription'
    } else if (detail.includes('trial_no_first_start') || detail.includes('no_first_start')) {
      key = 'dashboard.trial.error_no_first_start'
    }
    showToast(t(key))
  } finally {
    trialActivating.value = false
  }
}

function openPremiumLandingFromAurumGate() {
  showFreeAurumGateModal.value = false
  openBillingSection({ scrollLanding: true })
}

function openTokenPacksFromShowcase() {
  showPremiumAurumShowcaseModal.value = false
  showPremiumTokenLanding.value = true
  dashCtx.setDashboardSection('tokens')
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
    alert(t('dashboard.partner_ui.payout_too_low'))
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
    alert(t('dashboard.partner_ui.payout_sent'))
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || t('dashboard.partner_ui.payout_failed')))
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
      alert(t('dashboard.partner_ui.bonus_transferred', { amount: fmtAmount(moved) }))
    } else {
      alert(t('dashboard.partner_ui.bonus_none'))
    }
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || t('dashboard.partner_ui.bonus_failed')))
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
      showToast(t('errors.payment_link_missing'))
      return
    }
    beginPaymentRedirect(url)
  } catch (e) {
    showToast(String(e?.body?.detail || e?.message || t('errors.payment_failed')))
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
  dashCtx.setDashboardSection('account')
  const q = { ...route.query, section: 'account' }
  delete q.scroll
  void router.push({ path: '/', query: q }).catch(() => {})
}

function onPremiumActivatedGoSubscription() {
  showPremiumActivatedModal.value = false
  openSubscriptionScreen()
}

function openSubscriptionScreen() {
  dashCtx.setDashboardSection('subscription')
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
  dashCtx.setDashboardSection('billing')
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
      alert(t('dashboard.billing.receipt_alert_email_down'))
    } else if (detail) {
      alert(detail)
    } else {
      alert(t('dashboard.billing.receipt_alert_send_failed'))
    }
  } finally {
    receiptSending.value = false
  }
}

</script>

<template>
  <div class="space-y-3">

    <div v-if="!hasInitData" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
      {{ t('dashboard.home_shell.boot_hint') }}
    </div>

    <div v-else-if="bootError" class="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
      <p>{{ bootError }}</p>
      <button
        type="button"
        class="mt-3 w-full rounded-lg bg-slate-800 px-3 py-2 text-sm font-semibold text-white dark:bg-slate-200 dark:text-slate-900"
        @click="loadMeInitial"
      >
        {{ t('dashboard.home_shell.retry') }}
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
        v-if="dashSection === 'subscription'"
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
        <span class="text-xs font-medium text-white/90 drop-shadow-[0_1px_4px_rgba(0,0,0,0.85)]">{{ t('dashboard.home_shell.moment') }}</span>
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
                    <template v-if="protectionStatusOk">{{ t('dashboard.hero.protection_active') }}</template>
                    <template v-else-if="protectionStatusNoChats">{{ t('dashboard.hero.protection_status_no_chats') }}</template>
                    <template v-else>{{ t('dashboard.hero.protection_status_limbo') }}</template>
                  </p>
                </div>

                <div class="mt-2 w-full min-w-0 sm:mt-2.5">
                  <div
                    class="flex w-full min-w-0 items-stretch justify-between divide-x divide-white/[0.07]"
                  >
                    <div class="flex min-w-0 flex-1 flex-col items-center px-1.5 text-center sm:px-2">
                      <p class="w-full text-[8px] font-semibold uppercase tracking-wide text-white/45">{{ t('dashboard.hero.col_deleted') }}</p>
                      <p class="mt-0.5 w-full text-[15px] font-extrabold tabular-nums leading-none text-white sm:text-[16px]">
                        {{ activitySummary?.today?.deleted ?? 0 }}
                      </p>
                      <p class="mt-0.5 w-full text-[9px] font-medium leading-tight text-lime-400/95">{{ t('dashboard.hero.col_deleted_sub') }}</p>
                    </div>
                    <div class="flex min-w-0 flex-1 flex-col items-center px-1.5 text-center sm:px-2">
                      <p class="w-full text-[8px] font-semibold uppercase tracking-wide text-white/45">{{ t('dashboard.hero.col_saved') }}</p>
                      <p class="mt-0.5 w-full whitespace-nowrap text-center text-[12px] font-extrabold tabular-nums leading-none text-white sm:text-[13px]">
                        ~ {{ fmtRubInt(dashboardEstimatedSavedRub) }} ₽
                      </p>
                      <p class="mt-0.5 w-full text-[9px] font-medium leading-tight text-lime-400/95">{{ t('dashboard.hero.col_saved_sub') }}</p>
                    </div>
                    <div class="flex min-w-0 flex-1 flex-col items-center px-1.5 text-center sm:px-2">
                      <p class="w-full whitespace-nowrap text-[8px] font-semibold uppercase leading-tight tracking-wide text-white/45">
                        {{ t('dashboard.hero.col_level') }}
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
                          :title="t('dashboard.hero.score_tooltip', { score: dashboardProtectionLevelMeta.score ?? '—' })"
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
                  <span class="min-w-0 flex-1 text-[11px] font-semibold leading-tight text-white sm:text-[12px]"
                    >{{ t('dashboard.hero.protected_today_prefix') }}
                    <span class="text-lime-400">{{ ruGroupsProtectedLabel(activityProtectedGroupsCount) }}</span></span
                  >
                  <span class="shrink-0 text-sm font-light text-white/40" aria-hidden="true">›</span>
                </button>
              </div>
            </div>
          </div>

          <template v-if="dashSection === 'account'">
          <!-- Нижний ряд: AURUM (уже) | чаты (шире) -->
          <div class="mt-1 grid min-w-0 grid-cols-[minmax(0,40%)_minmax(0,60%)] gap-1.5 md:grid-cols-[minmax(0,38%)_minmax(0,62%)] md:gap-2">
            <div class="relative min-w-0 rounded-xl border border-amber-400/15 bg-gradient-to-b from-black/45 to-zinc-950/90 px-1 pb-0.5 pt-1 shadow-[0_10px_36px_-18px_rgba(0,0,0,0.65)] backdrop-blur-md md:px-1.5">
              <div class="flex items-start justify-between gap-1.5">
                <div class="min-w-0">
                  <p class="flex items-center gap-0.5 text-[8px] font-bold uppercase tracking-wide text-amber-200/90">
                    <span aria-hidden="true">⚡</span> {{ t('dashboard.hero.aurum_heading') }}
                  </p>
                  <p class="mt-0.5 flex items-baseline gap-0.5 text-[18px] font-extrabold tabular-nums leading-none text-white">
                    {{ fmtAmount(me?.aurum_tokens || 0) }}
                    <span class="text-sm">✨</span>
                  </p>
                  <p class="mt-0.5 text-[9px] text-white/45">{{ t('dashboard.hero.your_balance') }}</p>
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
                  {{ t('dashboard.hero.buy_short') }}
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
                  {{ t('dashboard.hero.history_short') }}
                </button>
              </div>
            </div>

            <div class="relative min-w-0 rounded-xl bg-gradient-to-b from-black/40 to-zinc-950/90 px-1.5 pb-0.5 pt-1 shadow-[0_10px_36px_-18px_rgba(0,0,0,0.65)] backdrop-blur-md md:pl-2 md:pr-2">
              <button
                v-if="spikeActiveShared"
                type="button"
                class="absolute right-1 top-1 z-[1] inline-flex items-center justify-center"
                :title="t('dashboard.chats_mini.threat_tooltip')"
                :aria-label="t('dashboard.chats_mini.threat_aria')"
                @click.stop="openSharedThreatChats"
              >
                <span class="absolute inline-flex h-3 w-3 animate-ping rounded-full bg-yellow-400/55" />
                <span class="relative text-[10px] leading-none text-yellow-300">⚠</span>
              </button>
              <p class="mb-0.5 flex items-center gap-1 text-[8px] font-bold uppercase tracking-wide text-white/85">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-sky-300/90" aria-hidden="true">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
                {{ t('dashboard.chats_mini.title') }}
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
                    {{ t('dashboard.hero.groups_short') }}
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
                    :aria-label="t('dashboard.chats_mini.connect_group_aria')"
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
                    {{ t('dashboard.hero.channels_short') }}
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
                    :aria-label="t('dashboard.chats_mini.connect_channel_aria')"
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
                {{ t('dashboard.chats_mini.manage') }}
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
                      <span class="truncate text-[13px] font-semibold leading-none text-white sm:text-[14px]">{{ t('dashboard.stats_strip.title') }}</span>
                    </div>
                    <label class="relative shrink-0 pt-px">
                      <span class="sr-only">{{ t('dashboard.stats_strip.period_sr_only') }}</span>
                      <select
                        class="pointer-events-auto max-w-[8.5rem] cursor-pointer appearance-none rounded-lg border border-lime-500/40 bg-black/50 py-0.5 pl-2 pr-7 text-[11px] font-semibold leading-none text-lime-400 outline-none ring-0 sm:max-w-none sm:py-1 sm:pl-2 sm:text-[12px] disabled:cursor-not-allowed disabled:opacity-45"
                        :disabled="dashboardStatsPremiumLocked"
                        :value="dashboardStatsPeriod"
                        :title="t('dashboard.stats_strip.period_hint')"
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
                    v-if="dashboardStatsPremiumLocked"
                    class="mt-1.5 rounded-lg border border-violet-500/30 bg-violet-950/35 px-2 py-1.5 text-[10px] leading-snug text-violet-100/95 ring-1 ring-violet-400/15"
                  >
                    {{ t('dashboard.stats_strip.free_locked_banner') }}
                  </div>

                  <div
                    class="relative mt-0.5 flex min-w-0 gap-0 overflow-x-auto pb-0 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden sm:gap-0.5"
                    :class="dashboardPeriodLoading ? 'opacity-60' : ''"
                  >
                    <div
                      class="flex min-w-0 flex-[1_1_0] flex-col border-r border-white/10 py-1 pr-1"
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
                      <p class="mt-1 w-full text-[10px] font-medium leading-snug text-white/60 sm:text-[11px]">{{ t('dashboard.stats_strip.col_deleted') }}</p>
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
                      <p class="mt-1 w-full text-[10px] font-medium leading-snug text-white/60 sm:text-[11px]">{{ t('dashboard.stats_strip.col_saved') }}</p>
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
                      <p class="mt-1 w-full text-[10px] font-medium leading-snug text-white/60 sm:text-[11px]">{{ t('dashboard.stats_strip.col_joined') }}</p>
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
                      <p class="mt-1 w-full text-[10px] font-medium leading-snug text-white/60 sm:text-[11px]">{{ t('dashboard.stats_strip.col_group_slots') }}</p>
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
                      <span class="text-[12px] font-extrabold leading-tight text-white sm:text-[13px]">{{ t('dashboard.broadcast_mini.title') }}</span>
                      <p class="mt-0.5 line-clamp-2 text-[8px] leading-snug text-white/50 sm:text-[9px]">
                        {{ t('dashboard.broadcast_mini.sub') }}
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
                        <span class="truncate">{{ t('dashboard.broadcast_mini.create') }}</span>
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
                      <p class="w-full text-[8px] font-medium leading-tight text-white/48 sm:text-[9px]">{{ t('dashboard.broadcast_mini.eligible') }}</p>
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
                      <p class="w-full text-[8px] font-medium leading-tight text-white/48 sm:text-[9px]">{{ t('dashboard.broadcast_mini.sent_today') }}</p>
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
                      <p class="w-full text-[8px] font-medium leading-tight text-white/48 sm:text-[9px]">{{ t('dashboard.broadcast_mini.scheduled') }}</p>
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
                  {{ t('dashboard.hero.home_tab_premium') }}
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
                  {{ t('dashboard.hero.home_tab_updates') }}
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
                        v-if="showTrialCta"
                        type="button"
                        :disabled="trialActivating"
                        class="flex w-full items-center justify-center gap-1.5 rounded-2xl bg-gradient-to-r from-emerald-700 via-emerald-500 to-lime-300 px-3 py-2.5 text-[11px] font-extrabold leading-tight text-emerald-950 shadow-[0_10px_34px_-10px_rgba(16,185,129,0.65),inset_0_1px_0_rgba(255,255,255,0.3)] ring-1 ring-emerald-300/45 disabled:opacity-60 sm:text-[12px]"
                        @click="activateTrialClick"
                      >
                        <span aria-hidden="true">🚀</span>
                        {{ trialActivating ? t('dashboard.trial.activating') : t('dashboard.trial.try_free_btn') }}
                      </button>
                      <button
                        v-else-if="!tariffIsPremium"
                        type="button"
                        class="flex w-full items-center justify-center gap-1.5 rounded-2xl bg-gradient-to-r from-amber-950 via-amber-600 to-yellow-300 px-3 py-2.5 text-[11px] font-extrabold leading-tight text-white shadow-[0_10px_34px_-10px_rgba(251,191,36,0.65),inset_0_1px_0_rgba(255,255,255,0.22)] ring-1 ring-amber-300/45 sm:text-[12px]"
                        @click="openBillingSection({ scrollPlans: true })"
                      >
                        <span aria-hidden="true">🛡</span>
                        {{ t('dashboard.hero.strengthen_protection') }}
                      </button>
                      <button
                        v-else
                        type="button"
                        class="flex w-full items-center justify-center gap-1.5 rounded-2xl bg-gradient-to-r from-amber-950 via-amber-500 to-yellow-200 px-3 py-2.5 text-[11px] font-extrabold leading-tight text-amber-950 shadow-[0_12px_40px_-12px_rgba(251,191,36,0.75),inset_0_1px_0_rgba(255,255,255,0.35)] ring-1 ring-amber-200/50 sm:text-[12px]"
                        @click="openBillingSection()"
                      >
                        <span aria-hidden="true">👑</span>
                        {{ t('dashboard.plans.cta_renew') }}
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
                      <span>{{ t('dashboard.hero.view_all_updates') }}</span>
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

      <div v-if="dashSection === 'partner'" class="mt-1 space-y-3">
        <p class="text-center text-xl font-extrabold uppercase tracking-[0.03em] text-white">{{ t('partner.title') }}</p>
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
            {{ t('partner.tab_balance') }}
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
            <span class="whitespace-nowrap">{{ t('partner.tab_refs') }}</span>
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
            {{ t('partner.tab_docs') }}
          </button>
        </div>

        <div v-if="partnerLoading" class="py-3 text-center text-sm text-white/75">
          {{ t('partner.loading') }}
        </div>
        <div v-else-if="partnerError" class="rounded-xl border border-rose-400/40 bg-rose-900/20 p-4 text-sm text-rose-200">
          {{ partnerError }}
        </div>
        <div v-else-if="partnerData && partnerTab === 'balance'" class="rounded-xl border border-slate-700 bg-slate-900/80 p-4 text-sm text-slate-200">
          <div class="space-y-1.5">
            <p>
              {{ t('partner.access', { label: partnerData.access_label || '—' }) }}<br>
              ├ {{ t('partner.days_left') }} <b>{{ partnerData.days_left ?? 0 }}</b><br>
              └ {{ t('partner.active_until') }} <b>{{ partnerActiveUntilLabel }}</b>
            </p>
            <p>
              {{ t('partner.balance_header') }}<br>
              ├ {{ t('partner.aurum_line', { amt: partnerAurumTokens }) }}<br>
              └ {{ t('partner.bonus_line', { amt: partnerBonusTokens }) }}
            </p>
            <p class="text-xs leading-relaxed text-slate-400">
              {{ t('partner.balance_hint') }}
            </p>
            <p v-if="partnerData.ref_link">
              {{ t('partner.your_link') }}<br>
              └ <button type="button" class="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-xs text-left text-cyan-300" @click="copyPartnerLink">{{ partnerData.ref_link }}</button>
            </p>
            <p>
              {{ t('partner.invited') }}<br>
              └ {{ t('partner.invited_total') }} <b>{{ partnerData.invited_count || 0 }}</b>, {{ t('partner.paying') }} <b>{{ partnerData.paid_count || 0 }}</b>
            </p>
          </div>
          <div class="mt-3 flex flex-wrap gap-2">
            <button type="button" class="guard-green-soft rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-60" :disabled="bonusTransferLoading" @click="transferPartnerBonusToAurum">
              {{ t('partner.transfer_cta') }}
            </button>
            <button type="button" class="rounded-lg border border-sky-400/40 bg-sky-500/10 px-3 py-1.5 text-xs font-semibold text-sky-300" @click="sharePartnerLink">
              {{ t('partner.share') }}
            </button>
          </div>
          <div class="mt-4 rounded-xl border border-slate-700 bg-slate-800/70 p-3">
            <p>{{ t('partner.available_payout') }} <b>{{ fmtAmount(partnerPayouts.available_rub || 0) }} ₽</b></p>
            <p class="mt-0.5">{{ t('partner.pending_unlock') }} <b>{{ fmtAmount(partnerPayouts.pending_rub || 0) }} ₽</b></p>
            <p class="mt-0.5">{{ t('partner.in_requests') }} <b>{{ fmtAmount(partnerPayouts.reserved_rub || 0) }} ₽</b></p>
            <p class="mt-0.5">{{ t('partner.paid_out') }} <b>{{ fmtAmount(partnerPayouts.paid_total_rub || 0) }} ₽</b></p>
            <p class="mt-0.5 text-xs text-slate-400">{{ t('partner.token_rate', { rate: fmtAmount(partnerPayouts.token_rub_rate || 2) }) }}</p>
            <p class="mt-0.5 text-sm font-semibold text-amber-300">{{ t('partner.min_payout', { rub: fmtAmount(partnerPayouts.min_payout_rub || 1500) }) }}</p>
            <div class="mt-2 grid gap-2 sm:grid-cols-2">
              <input v-model="payoutAmountRub" type="number" min="0" step="1" :placeholder="t('partner.amount_placeholder')" class="rounded-lg border border-slate-600 bg-slate-900 px-2.5 py-2 text-xs text-white">
              <select v-model="payoutMethod" class="rounded-lg border border-slate-600 bg-slate-900 px-2.5 py-2 text-xs text-white">
                <option value="sbp">{{ t('partner.method_sbp') }}</option>
                <option value="card">{{ t('partner.method_card') }}</option>
              </select>
              <input v-model="payoutRequisites" type="text" :placeholder="t('partner.requisites_placeholder')" class="sm:col-span-2 rounded-lg border border-slate-600 bg-slate-900 px-2.5 py-2 text-xs text-white">
              <input v-model="payoutFullName" type="text" :placeholder="t('partner.fullname_placeholder')" class="sm:col-span-2 rounded-lg border border-slate-600 bg-slate-900 px-2.5 py-2 text-xs text-white">
            </div>
            <button type="button" class="mt-2 guard-green-soft rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-60" :disabled="payoutSubmitting || partnerPayoutsLoading" @click="submitPayoutRequest">
              {{ t('partner.request_payout') }}
            </button>
            <div v-if="(partnerPayouts.commissions || []).length" class="mt-3 rounded-lg border border-slate-700 bg-slate-900/70 p-2">
              <p class="text-[11px] font-semibold text-slate-300">{{ t('partner.recent_commissions') }}</p>
              <div v-for="c in (partnerPayouts.commissions || []).slice(0, 5)" :key="`pc-${c.id}`" class="mt-1 text-[11px] text-slate-300">
                {{ t('partner.level_line', { level: c.level, amount: fmtAmount(c.reward_amount_rub), status: c.status }) }}
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
                {{ t('partner.refs_mode_full') }}
              </button>
              <button
                type="button"
                class="pb-1 text-[15px] font-semibold"
                :class="refsMode === 'active' ? 'border-b-4 border-sky-500 text-sky-600' : 'text-slate-400'"
                @click="refsMode = 'active'"
              >
                {{ t('partner.refs_mode_active') }}
              </button>
            </div>

            <div v-if="referralPeopleLoading" class="py-4 text-center text-sm text-slate-500">
              {{ t('partner.refs_loading') }}
            </div>
            <div
              v-else-if="(refsMode === 'full' ? paidFullRefs : paidActiveRefs).length === 0"
              class="py-8 text-center text-[18px] font-medium text-slate-700"
            >
              {{ t('partner.refs_empty') }}
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
                    {{ item.is_paid ? t('partner.refs_status_paying') : t('partner.refs_status_free') }}
                  </span>
                </div>
                <p class="mt-0.5 text-xs text-slate-600">
                  {{ t('partner.refs_stats_line', { p: item.payments_count || 0, t: item.tokens_purchased || 0 }) }}
                </p>
              </div>
            </div>
          </div>
        </div>
        <div v-else-if="partnerData && partnerTab === 'docs'" class="space-y-2">
          <div class="rounded-2xl border border-fuchsia-300/35 bg-white p-4 text-slate-900">
            <p class="text-lg font-extrabold text-[#4bbf67]">{{ t('partner.docs_q_program') }}</p>
            <p class="mt-2 text-sm">
              {{ t('partner.docs_program_intro') }}
            </p>
            <div class="mt-2 space-y-1 text-sm">
              <p><span class="inline-flex h-5 w-5 items-center justify-center rounded bg-slate-900 text-xs font-bold text-white">1</span> {{ t('partner.docs_lvl_1') }}</p>
              <p><span class="inline-flex h-5 w-5 items-center justify-center rounded bg-slate-900 text-xs font-bold text-white">2</span> {{ t('partner.docs_lvl_2') }}</p>
              <p><span class="inline-flex h-5 w-5 items-center justify-center rounded bg-slate-900 text-xs font-bold text-white">3</span> {{ t('partner.docs_lvl_3') }}</p>
            </div>
            <p class="mt-2 text-sm text-slate-600">
              {{ t('partner.docs_payouts_note') }}
            </p>
            <p class="mt-2 text-sm text-slate-700">
              {{ t('partner.docs_reward_for') }}
            </p>
            <p class="mt-1 text-sm text-slate-700">
              {{ t('partner.docs_token_rate_line') }}
            </p>
          </div>
          <div class="rounded-2xl border border-fuchsia-300/35 bg-white p-4 text-slate-900">
            <p class="text-lg font-extrabold text-[#4bbf67]">{{ t('partner.docs_q_accrual') }}</p>
            <p class="mt-2 text-sm">
              {{ t('partner.docs_accrual_example') }}
            </p>
            <p class="mt-2 text-sm italic text-slate-600">
              {{ t('partner.docs_accrual_auto') }}
            </p>
            <div class="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
              <p class="text-sm font-semibold">{{ t('partner.docs_calc_title') }}</p>
              <input v-model="docsExampleSale" type="number" min="0" step="100" class="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm">
              <p class="mt-2 text-xs">{{ t('partner.docs_sale_label') }} <b>{{ fmtAmount(docsCalc.amount) }} ₽</b></p>
              <p class="text-xs"><span class="inline-flex h-4 w-4 items-center justify-center rounded bg-slate-900 text-[10px] font-bold text-white">+</span> {{ t('partner.docs_lvl1_calc') }} <b>{{ fmtAmount(docsCalc.l1) }} ₽</b></p>
              <p class="text-xs"><span class="inline-flex h-4 w-4 items-center justify-center rounded bg-slate-900 text-[10px] font-bold text-white">+</span> {{ t('partner.docs_lvl2_calc') }} <b>{{ fmtAmount(docsCalc.l2) }} ₽</b></p>
              <p class="text-xs"><span class="inline-flex h-4 w-4 items-center justify-center rounded bg-slate-900 text-[10px] font-bold text-white">+</span> {{ t('partner.docs_lvl3_calc') }} <b>{{ fmtAmount(docsCalc.l3) }} ₽</b></p>
              <p class="text-xs">{{ t('partner.docs_total') }} <b>{{ fmtAmount(docsCalc.total) }} ₽</b></p>
            </div>
          </div>
          <div class="rounded-2xl border border-fuchsia-300/35 bg-white p-4 text-slate-900">
            <p class="text-lg font-extrabold text-[#4bbf67]">{{ t('partner.docs_q_withdraw') }}</p>
            <ol class="mt-2 list-decimal space-y-1 pl-4 text-sm">
              <li>{{ t('partner.docs_withdraw_1') }}</li>
              <li>{{ t('partner.docs_withdraw_2') }}</li>
              <li>{{ t('partner.docs_withdraw_3') }}</li>
              <li>{{ t('partner.docs_withdraw_4') }}</li>
            </ol>
          </div>
          <div class="rounded-2xl border border-emerald-300/35 bg-white p-4 text-slate-900">
            <p class="text-lg font-extrabold text-[#4bbf67]">{{ t('partner.docs_q_what_counts') }}</p>
            <p class="mt-2 text-sm">{{ t('partner.docs_counts_yes') }}</p>
            <p class="mt-1 text-sm text-slate-700">
              {{ t('partner.docs_counts_note') }}
            </p>
          </div>
        </div>
      </div>

      <div
        v-if="dashSection === 'tokens'"
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
                :title="t('dashboard.billing.aurum_gate_total_hint')"
              >
                <p class="text-[8px] font-medium uppercase leading-none tracking-[0.12em] text-white/38">{{ t('dashboard.billing.aurum_gate_total_label') }}</p>
                <p class="text-xs font-bold leading-tight tabular-nums text-lime-200">{{ totalTokens }}<span class="ml-px text-[9px]">⚡</span></p>
              </div>
              <div
                v-if="tariffIsPremium"
                :class="tokensInfoToolbarClass"
                role="group"
                :aria-label="t('dashboard.tokens.toolbar_help_aria')"
              >
                <button
                  type="button"
                  :class="tokensInfoBtnClass"
                  :title="t('dashboard.tokens.help_balances_tooltip')"
                  :aria-label="t('dashboard.tokens.help_balances_aria')"
                  @click="showAurumTokensHelp"
                >i</button>
                <button
                  type="button"
                  :class="tokensInfoBtnClass"
                  :title="t('dashboard.tokens.help_checkout_tooltip')"
                  :aria-label="t('dashboard.tokens.help_checkout_aria')"
                  @click="openTokensCheckoutInfo"
                >i</button>
              </div>
              <button
                v-else
                type="button"
                :class="tokensInfoBtnClass"
                :title="t('dashboard.tokens.help_what_aurum_tooltip')"
                :aria-label="t('dashboard.tokens.help_what_aurum_aria')"
                @click="showAurumTokensHelp"
              >i</button>
            </div>
          </div>
          <p
            v-if="tariffIsPremium && Number(me?.broadcast_spend_tokens || 0) > 0"
            class="text-[9px] leading-tight text-amber-200/80"
          >
            {{ t('dashboard.tokens.broadcast_spend', { amt: fmtAmount(me.broadcast_spend_tokens) }) }}
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
              <p class="text-[13px] font-semibold leading-tight text-white">{{ t('dashboard.billing.aurum_gate_unavailable') }}</p>
              <p class="mt-2 text-[11px] leading-snug text-white/55">
                {{ t('dashboard.billing.aurum_gate_sub') }}
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
              {{ t('dashboard.billing.gate_get_premium') }}
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
                <span>{{ t('dashboard.billing.gate_li_unlock') }}</span>
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
                <span>{{ t('dashboard.billing.gate_li_broadcast') }}</span>
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
                <span>{{ t('dashboard.billing.gate_li_clients') }}</span>
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
                    <h4 ref="premiumTokenLandingTitleRef" class="text-center text-[17px] font-extrabold leading-tight text-white">{{ t('dashboard.tokens.fuel_title') }}</h4>
                    <p class="mx-auto mt-2 max-w-[20rem] text-center text-[12px] leading-snug text-white/65">
                      {{ t('dashboard.tokens.fuel_sub') }}
                    </p>
                    <img
                      :src="tokenLandingOrbitSrc"
                      :alt="t('dashboard.tokens.orbit_alt')"
                      class="mx-auto mt-2.5 w-full max-w-[23rem] bg-transparent object-contain"
                      draggable="false"
                      @dragstart.prevent
                    >
                  </div>
                  <div class="rounded-xl border border-white/[0.1] bg-zinc-950/50 px-3 py-2.5">
                    <p class="text-[12px] font-bold text-white">{{ t('dashboard.tokens.why_title') }}</p>
                    <ul class="mt-1.5 space-y-1.5 text-[12px] leading-snug text-white/82">
                      <li class="flex items-center gap-2"><span class="inline-flex h-4 w-4 items-center justify-center text-[15px] font-black leading-none text-lime-300 drop-shadow-[0_0_6px_rgba(163,230,53,0.85)]">✓</span><span>{{ t('dashboard.tokens.why_1') }}</span></li>
                      <li class="flex items-center gap-2"><span class="inline-flex h-4 w-4 items-center justify-center text-[15px] font-black leading-none text-lime-300 drop-shadow-[0_0_6px_rgba(163,230,53,0.85)]">✓</span><span>{{ t('dashboard.tokens.why_2') }}</span></li>
                      <li class="flex items-center gap-2"><span class="inline-flex h-4 w-4 items-center justify-center text-[15px] font-black leading-none text-lime-300 drop-shadow-[0_0_6px_rgba(163,230,53,0.85)]">✓</span><span>{{ t('dashboard.tokens.why_3') }}</span></li>
                      <li class="flex items-center gap-2"><span class="inline-flex h-4 w-4 items-center justify-center text-[15px] font-black leading-none text-lime-300 drop-shadow-[0_0_6px_rgba(163,230,53,0.85)]">✓</span><span>{{ t('dashboard.tokens.why_4') }}</span></li>
                    </ul>
                  </div>
                  <div class="space-y-2">
                    <button
                      type="button"
                      class="relative w-full overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-white text-center shadow-[0_14px_42px_-14px_rgba(243,156,18,0.62),inset_0_1px_0_rgba(255,255,255,0.28)] transition active:scale-[0.99]"
                      style="background: linear-gradient(90deg, #f39c12 0%, #df5a3b 34%, #b043cc 56%, #5c2dc1 74%, #2a1a83 100%);"
                      @click="scrollToPremiumTokenPacks"
                    >
                      {{ t('dashboard.tokens.cta_choose_pack') }}
                    </button>
                    <button
                      type="button"
                      class="w-full text-center text-[13px] font-medium text-slate-300 underline decoration-slate-500 underline-offset-4 transition hover:text-white"
                      @click="scrollToTokenHowItWorks"
                    >
                      {{ t('dashboard.tokens.link_how_it_works') }}
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
                    <h4 class="text-center text-[17px] font-extrabold leading-tight text-white">{{ t('dashboard.tokens.how_headline') }}</h4>
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
                        <p class="text-[12px] font-bold text-white">{{ t('dashboard.tokens.feat_broadcast_title') }}</p>
                        <p class="mt-0.5 text-[11px] leading-snug text-white/70">{{ t('dashboard.tokens.feat_broadcast_body') }}</p>
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
                        <p class="text-[12px] font-bold text-white">{{ t('dashboard.tokens.feat_autopost_title') }}</p>
                        <p class="mt-0.5 text-[11px] leading-snug text-white/70">{{ t('dashboard.tokens.feat_autopost_body') }}</p>
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
                        <p class="text-[12px] font-bold text-white">{{ t('dashboard.tokens.feat_clients_title') }}</p>
                        <p class="mt-0.5 text-[11px] leading-snug text-white/70">{{ t('dashboard.tokens.feat_clients_body') }}</p>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="rounded-2xl border border-white/[0.08] bg-gradient-to-b from-zinc-900/82 to-black/95 px-3.5 py-3 shadow-[0_12px_32px_-16px_rgba(0,0,0,0.86)]">
                  <p class="text-center text-[16px] font-extrabold text-white">{{ t('dashboard.tokens.how_steps_title') }}</p>
                  <div class="mt-2.5 flex items-center justify-between gap-0.5">
                    <div class="flex min-w-0 flex-1 flex-col items-center gap-1.5 text-center">
                      <div class="flex h-[3.75rem] w-[3.75rem] items-center justify-center rounded-[1rem] border border-[#7dd8fc]/45 bg-gradient-to-br from-[#2fa8f0] via-[#1b8fe0] to-[#1464b8] shadow-[0_0_22px_-2px_rgba(56,189,248,0.95),inset_0_1px_0_rgba(255,255,255,0.26)]">
                        <svg viewBox="0 0 24 24" class="h-8 w-8 text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.25)]" fill="currentColor" aria-hidden="true">
                          <path d="M21.5 4.8 18.4 19c-.2.9-.8 1.1-1.6.7l-4.4-3.2-2.1 2c-.2.2-.4.4-.9.4l.3-4.5 8.3-7.5c.4-.3-.1-.5-.5-.2l-10.2 6.4-4.4-1.4c-.9-.3-.9-.9.2-1.3L19.9 4c.8-.3 1.5.2 1.3.8z" />
                        </svg>
                      </div>
                      <p class="text-[10px] font-semibold leading-tight text-white">{{ t('dashboard.tokens.how_step_broadcast') }}</p>
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
                      <p class="text-[10px] font-semibold leading-tight text-white">{{ t('dashboard.tokens.how_step_replies') }}</p>
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
                      <p class="text-[10px] font-semibold leading-tight text-white">{{ t('dashboard.tokens.how_step_clients') }}</p>
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
                      <p class="text-[10px] font-semibold leading-tight text-white">{{ t('dashboard.tokens.how_step_profit') }}</p>
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  class="mt-2 w-full rounded-[1.05rem] border border-[#f6cc55]/75 bg-gradient-to-b from-[#ffd94a] via-[#f2b705] to-[#a96a00] px-4 py-2 text-center text-[17px] font-black tracking-tight text-black shadow-[0_18px_30px_-14px_rgba(235,160,0,0.96),0_0_28px_-10px_rgba(255,190,0,0.72),inset_0_1px_0_rgba(255,237,176,0.5),inset_0_-9px_14px_rgba(107,63,0,0.45)] transition active:scale-[0.99]"
                  @click="scrollToPremiumTokenPacks({ reloadPacks: false })"
                >
                  {{ t('dashboard.tokens.cta_run_broadcast') }}
                </button>
                <p class="mt-2 text-center text-[13px] font-extrabold text-amber-300">{{ t('dashboard.tokens.follow_updates') }}</p>
                </div>
              </section>

              <section
                ref="tokenLandingPackChoiceRef"
                class="scroll-mt-[5.75rem] relative overflow-hidden rounded-[1.125rem] border border-white/[0.14] bg-black px-4 py-6 text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] ring-1 ring-inset ring-white/[0.08]"
              >
                <div v-if="tokenPacksLoading" class="py-4 text-center text-[11px] text-white/45">{{ t('dashboard.tokens.loading') }}</div>
                <div v-else class="space-y-2">
                  <h4
                    ref="tokenLandingPackChoiceTitleRef"
                    class="scroll-mt-[5.75rem] text-center text-[16px] font-extrabold tracking-tight text-white"
                  >{{ t('dashboard.tokens.pack_choice_title') }}</h4>
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
                      {{ t('dashboard.tokens.refresh') }}
                    </button>
                  </div>
                  <div
                    v-else-if="!tokenPacks.length"
                    class="rounded-xl border border-white/[0.1] bg-zinc-900/70 px-2.5 py-3 text-center text-[11px] leading-snug text-white/60"
                  >
                    {{ t('dashboard.tokens.packs_empty') }}
                    <button
                      type="button"
                      class="mt-2 w-full rounded-lg border border-white/15 bg-white/10 py-2 text-[12px] font-semibold text-white transition hover:bg-white/14"
                      @click="loadTokenPacksFromApi"
                    >
                      {{ t('dashboard.tokens.refresh') }}
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
                      {{ showAllTokenPacks ? t('dashboard.tokens.hide_extra_packs') : t('dashboard.tokens.show_more_packs') }}
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
                  {{ payLoadingTokenPack !== null ? t('dashboard.billing.pay_preparing') : t('dashboard.billing.continue') }}
                </button>
                <button
                  v-if="tokenPacks.length"
                  type="button"
                  class="mt-2 w-full py-2 text-center text-[13px] font-medium text-slate-400 underline decoration-slate-500 underline-offset-4 transition hover:text-slate-300"
                  @click="openPromoCodeModal"
                >
                  {{ t('dashboard.billing.have_promo') }}
                </button>
                <div
                  v-if="me?.is_admin"
                  class="flex flex-wrap items-center gap-x-1.5 gap-y-1 rounded-lg border border-amber-400/22 bg-amber-500/[0.05] px-1.5 py-1 backdrop-blur-xl"
                >
                  <span class="text-[9px] font-semibold uppercase tracking-wide text-amber-200/90">{{ t('dashboard.tokens.test_label') }}</span>
                  <button
                    type="button"
                    :class="tokensInfoBtnAmberClass"
                    :title="t('dashboard.tokens.test_pay_tooltip')"
                    :aria-label="t('dashboard.tokens.test_pay_info_aria')"
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
                <p class="text-[10px] font-medium text-white/45">{{ t('dashboard.billing.footer_rights', { year: new Date().getFullYear() }) }}</p>
                <p class="mt-1 text-[10px] text-white/38">{{ t('dashboard.billing.footer_social') }}</p>
              </section>
            </div>

            <div v-if="!showPremiumTokenLanding && tokenPacksLoading" class="py-4 text-center text-[11px] text-white/45">{{ t('dashboard.tokens.loading') }}</div>
            <div
              v-else-if="!showPremiumTokenLanding"
              ref="premiumTokenPacksRef"
              class="mt-1 space-y-2"
            >
              <h4 class="text-center text-[16px] font-extrabold tracking-tight text-white">{{ t('dashboard.tokens.pack_choice_title') }}</h4>
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
                  {{ t('dashboard.tokens.refresh') }}
                </button>
              </div>
              <div
                v-else-if="!tokenPacks.length"
                class="rounded-xl border border-white/[0.1] bg-zinc-900/70 px-2.5 py-3 text-center text-[11px] leading-snug text-white/60"
              >
                {{ t('dashboard.tokens.packs_empty') }}
                <button
                  type="button"
                  class="mt-2 w-full rounded-lg border border-white/15 bg-white/10 py-2 text-[12px] font-semibold text-white transition hover:bg-white/14"
                  @click="loadTokenPacksFromApi"
                >
                  {{ t('dashboard.tokens.refresh') }}
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
                  {{ showAllTokenPacks ? t('dashboard.tokens.hide_extra_packs') : t('dashboard.tokens.show_more_packs') }}
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
              {{ payLoadingTokenPack !== null ? t('dashboard.billing.pay_preparing') : t('dashboard.billing.continue') }}
            </button>
            <button
              v-if="!showPremiumTokenLanding && tokenPacks.length"
              type="button"
              class="mt-2 w-full py-2 text-center text-[13px] font-medium text-slate-400 underline decoration-slate-500 underline-offset-4 transition hover:text-slate-300"
              @click="openPromoCodeModal"
            >
              {{ t('dashboard.billing.have_promo') }}
            </button>
            <div
              v-if="!showPremiumTokenLanding && me?.is_admin"
              class="flex flex-wrap items-center gap-x-1.5 gap-y-1 rounded-lg border border-amber-400/22 bg-amber-500/[0.05] px-1.5 py-1 backdrop-blur-xl"
            >
              <span class="text-[9px] font-semibold uppercase tracking-wide text-amber-200/90">{{ t('dashboard.tokens.test_label') }}</span>
              <button
                type="button"
                :class="tokensInfoBtnAmberClass"
                :title="t('dashboard.tokens.test_pay_tooltip')"
                :aria-label="t('dashboard.tokens.test_pay_info_aria')"
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
        v-if="dashSection === 'billing'"
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
                {{ t('dashboard.billing.free_limits_title') }}
              </p>
              <p class="mt-2 max-w-[19rem] text-center text-[13px] leading-relaxed text-slate-400">
                {{ t('dashboard.billing.free_limits_sub') }}
              </p>
              <ul class="mt-5 w-full max-w-md space-y-3 rounded-2xl border border-white/[0.08] bg-zinc-950/90 px-4 py-4">
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="mt-0.5 shrink-0 text-violet-400" aria-hidden="true">🔒</span>
                  {{ t('dashboard.billing.free_li_autodel') }}
                </li>
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="mt-0.5 shrink-0 text-violet-400" aria-hidden="true">🔒</span>
                  {{ t('dashboard.billing.free_li_links') }}
                </li>
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="mt-0.5 shrink-0 text-violet-400" aria-hidden="true">🔒</span>
                  {{ t('dashboard.billing.free_li_broadcast') }}
                </li>
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="mt-0.5 shrink-0 text-violet-400" aria-hidden="true">🔒</span>
                  {{ t('dashboard.billing.free_li_stats') }}
                </li>
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="mt-0.5 shrink-0 text-amber-400/95 drop-shadow-[0_0_8px_rgba(251,191,36,0.45)]" aria-hidden="true">🔒</span>
                  {{ t('dashboard.billing.free_li_support') }}
                </li>
              </ul>
              <button
                type="button"
                class="mt-6 w-full max-w-md rounded-2xl bg-violet-600 py-3.5 text-[15px] font-bold text-white shadow-[0_12px_32px_-8px_rgba(124,58,237,0.55)] transition hover:bg-violet-500 active:scale-[0.99]"
                @click="scrollToBillingPremiumPitch"
              >
                {{ t('dashboard.billing.cta_learn_premium') }}
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
                {{ t('dashboard.billing.premium_pitch_title') }}
              </p>
              <p class="mx-auto mt-2 max-w-[20rem] text-center text-[13px] leading-relaxed text-slate-400">
                {{ t('dashboard.billing.premium_pitch_sub') }}
              </p>
              <ul class="mx-auto mt-5 max-w-md space-y-3">
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-500/15 text-sm text-amber-300" aria-hidden="true">✦</span>
                  {{ t('dashboard.billing.pf_clean_chat') }}
                </li>
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-500/15 text-sm text-amber-300" aria-hidden="true">✦</span>
                  {{ t('dashboard.billing.pf_autodel') }}
                </li>
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-500/15 text-sm text-amber-300" aria-hidden="true">✦</span>
                  {{ t('dashboard.billing.pf_broadcast') }}
                </li>
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-500/15 text-sm text-amber-300" aria-hidden="true">✦</span>
                  {{ t('dashboard.billing.pf_analytics') }}
                </li>
                <li class="flex items-start gap-3 text-[13px] leading-snug text-slate-200">
                  <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-500/15 text-sm text-amber-300" aria-hidden="true">✦</span>
                  {{ t('dashboard.billing.pf_support') }}
                </li>
              </ul>
              <button
                v-if="showTrialCta"
                type="button"
                :disabled="trialActivating"
                class="relative mx-auto mt-6 flex w-full max-w-md items-center justify-center overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-emerald-950 text-center shadow-[0_14px_42px_-14px_rgba(16,185,129,0.62),inset_0_1px_0_rgba(255,255,255,0.32)] ring-1 ring-emerald-300/45 transition active:scale-[0.99] disabled:opacity-60"
                style="background: linear-gradient(90deg, #34d399 0%, #10b981 50%, #84cc16 100%);"
                @click="activateTrialClick"
              >
                <span aria-hidden="true" class="mr-1.5">🚀</span>
                {{ trialActivating ? t('dashboard.trial.activating') : t('dashboard.trial.activate_btn') }}
              </button>
              <button
                v-else
                type="button"
                class="relative mx-auto mt-6 flex w-full max-w-md items-center justify-center overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-white text-center shadow-[0_14px_42px_-14px_rgba(243,156,18,0.62),inset_0_1px_0_rgba(255,255,255,0.28)] transition active:scale-[0.99]"
                style="background: linear-gradient(90deg, #f39c12 0%, #df5a3b 34%, #b043cc 56%, #5c2dc1 74%, #2a1a83 100%);"
                @click="scrollToBillingLandingPlans"
              >
                {{ t('dashboard.billing.cta_pick_plan') }}
              </button>
              <p
                v-if="showTrialCta"
                class="mt-3 text-center text-[12px] leading-snug text-emerald-300/85"
              >{{ t('dashboard.trial.hint_landing') }}</p>
              <button
                v-if="!showTrialCta"
                type="button"
                class="mt-3 w-full py-2 text-center text-[13px] font-medium text-slate-500 underline decoration-slate-600 underline-offset-4 transition hover:text-slate-400"
                @click="scrollToBillingPremiumCompare"
              >
                {{ t('dashboard.billing.link_compare_plans') }}
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
                {{ t('dashboard.billing.compare_title') }}
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
                >{{ t('dashboard.billing.compare_feature_col') }}</span>
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
                      <span class="mt-1 w-full text-center text-[9px] font-medium leading-none text-slate-400">{{ t('dashboard.billing.referral_tier_free') }}</span>
                    </div>
                    <div
                      class="flex min-w-0 flex-col items-center justify-center border-b border-l border-amber-400/15 bg-amber-500/[0.05] px-1.5 py-2.5 text-center"
                    >
                      <span class="text-[15px] font-bold leading-none text-emerald-400">✓</span>
                      <span class="mt-1 w-full text-center text-[9px] font-semibold leading-tight text-emerald-300">{{ t('dashboard.billing.referral_tier_premium') }}</span>
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
                      <span class="text-[11px] font-semibold leading-tight text-amber-200/95">{{ t('dashboard.billing.limits_unlimited') }}</span>
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
                v-if="showTrialCta"
                type="button"
                :disabled="trialActivating"
                class="relative w-full overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-emerald-950 text-center shadow-[0_14px_42px_-14px_rgba(16,185,129,0.62),inset_0_1px_0_rgba(255,255,255,0.32)] ring-1 ring-emerald-300/45 transition active:scale-[0.99] disabled:opacity-60"
                style="background: linear-gradient(90deg, #34d399 0%, #10b981 50%, #84cc16 100%);"
                @click="activateTrialClick"
              >
                <span aria-hidden="true" class="mr-1.5">🚀</span>
                {{ trialActivating ? t('dashboard.trial.activating') : t('dashboard.trial.activate_btn') }}
              </button>
              <button
                v-else
                type="button"
                class="relative w-full overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-white text-center shadow-[0_14px_42px_-14px_rgba(243,156,18,0.62),inset_0_1px_0_rgba(255,255,255,0.28)] transition active:scale-[0.99]"
              style="background: linear-gradient(90deg, #f39c12 0%, #df5a3b 34%, #b043cc 56%, #5c2dc1 74%, #2a1a83 100%);"
                @click="scrollToBillingLandingPlans"
              >
                {{ t('dashboard.billing.cta_choose_premium_btn') }}
              </button>
              <p
                v-if="showTrialCta"
                class="mt-3 text-center text-[12px] leading-snug text-emerald-300/85"
              >{{ t('dashboard.trial.hint_landing') }}</p>
            </div>
          </section>

          <!-- 4. Выбор тарифа (карточки как в макете) — скрываем, пока юзер не активировал триал -->
          <section
            v-if="!showTrialCta"
            id="billing-landing-plans"
            ref="billingLandingPlansRef"
            class="relative overflow-hidden rounded-[1.125rem] border border-white/[0.12] bg-black px-4 py-6 text-white ring-1 ring-inset ring-white/[0.06]"
          >
            <h2 class="text-center text-lg font-extrabold tracking-tight text-white sm:text-xl">
              {{ t('dashboard.billing.plan_choice_title') }}
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
              {{ showAllLandingPlans ? t('dashboard.billing.hide_extra_plans') : t('dashboard.billing.show_all_plans') }}
            </button>
            <button
              type="button"
              class="relative w-full overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-white text-center shadow-[0_14px_42px_-14px_rgba(243,156,18,0.62),inset_0_1px_0_rgba(255,255,255,0.28)] transition active:scale-[0.99]"
              style="background: linear-gradient(90deg, #f39c12 0%, #df5a3b 34%, #b043cc 56%, #5c2dc1 74%, #2a1a83 100%);"
              @click="onLandingContinue"
            >
              {{ t('dashboard.billing.continue') }}
            </button>
            <button
              type="button"
              class="mt-2 w-full py-2 text-center text-[13px] font-medium text-slate-500 underline decoration-slate-600 underline-offset-4 transition hover:text-slate-400"
              @click="openPromoCodeModal"
            >
              {{ t('dashboard.billing.have_promo') }}
            </button>
            <!-- Оплата и все периоды — внутри того же лендинга, без отдельной «страницы Guard Premium» -->
            <div class="mt-8 space-y-3 border-t border-white/[0.1] pt-7">
              <button
                v-if="billingFromGroupStats"
                type="button"
                class="flex w-full items-center justify-center gap-1 rounded-lg border border-white/[0.12] bg-white/[0.06] py-1.5 text-[12px] font-semibold text-lime-200/95 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-md transition hover:bg-white/[0.1] active:scale-[0.99]"
                @click="backFromBillingToGroupStats"
              >
                {{ t('dashboard.billing.back_to_group_stats') }}
              </button>

          <div id="billing-premium-plans" ref="billingPremiumPlansRef" class="scroll-mt-4 space-y-2"></div>

          <div
            v-if="me?.test_tariff_payment_visible"
            class="flex flex-col gap-1 rounded-lg border border-amber-400/22 bg-amber-500/[0.05] px-1.5 py-1.5 backdrop-blur-xl"
          >
            <div class="flex flex-wrap items-center gap-x-1.5 gap-y-1">
              <span class="text-[9px] font-semibold uppercase tracking-wide text-amber-200/90">{{ t('dashboard.billing.test_tariffs_label') }}</span>
              <button
                type="button"
                :class="tokensInfoBtnAmberClass"
                :title="t('dashboard.billing.test_block_tooltip')"
                :aria-label="t('dashboard.billing.test_block_aria')"
                @click="openPremiumTestTariffInfo"
              >i</button>
            </div>
            <div class="grid grid-cols-2 gap-1 sm:grid-cols-3">
              <button
                v-for="plan in premiumPlansCatalog"
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
                  <span class="text-[7px] font-bold uppercase tracking-wide text-amber-400/80">{{ t('dashboard.billing.test_tariff_corner') }}</span>
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
              {{ t('dashboard.billing.open_sub_screen') }}
            </button>
          </div>
          <div class="mt-4 border-t border-white/[0.08] pt-3 text-center">
            <p class="text-[10px] font-medium text-white/45">{{ t('dashboard.billing.footer_rights', { year: new Date().getFullYear() }) }}</p>
            <p class="mt-1 text-[10px] text-white/38">{{ t('dashboard.billing.footer_social') }}</p>
          </div>
        </div>
        </section>
      </div>

      <div v-if="dashSection === 'faq'" class="mt-1 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
        <h3 class="text-base font-semibold text-slate-900 dark:text-white">FAQ</h3>
        <ul class="mt-2 list-disc space-y-1 pl-4 text-sm text-slate-700 dark:text-slate-300">
          <li>{{ t('dashboard.billing.faq_li_sub') }}</li>
          <li>{{ t('dashboard.billing.faq_li_bonus') }}</li>
          <li>{{ t('dashboard.billing.faq_li_convert') }}</li>
        </ul>
      </div>

      <div v-if="dashSection === 'history'" class="mt-1">
        <div class="rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
          <div class="grid grid-cols-2 gap-2">
            <button
              type="button"
              class="rounded-xl px-3 py-2 text-sm font-semibold"
              :class="historyTab === 'payments' ? 'bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-200' : 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200'"
              @click="historyTab = 'payments'"
            >
              {{ t('dashboard.billing.history_payments_tab') }}
            </button>
            <button
              type="button"
              class="rounded-xl px-3 py-2 text-sm font-semibold"
              :class="historyTab === 'tokens' ? 'bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-200' : 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200'"
              @click="historyTab = 'tokens'"
            >
              {{ t('dashboard.billing.history_tokens_tab') }}
            </button>
          </div>
          <div v-if="historyLoading" class="py-6 text-center text-sm text-slate-500 dark:text-slate-400">{{ t('dashboard.billing.history_wait') }}</div>
          <div v-else-if="historyTab === 'payments'" class="mt-3 space-y-2">
            <div v-if="historyPayments.length === 0" class="rounded-xl bg-slate-50 p-4 text-center text-sm text-slate-500 dark:bg-slate-700/40 dark:text-slate-400">
              {{ t('dashboard.billing.history_no_payments') }}
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
                      {{ fmtAmount(item.amount_rub) }} ₽ · {{ t('dashboard.billing.months_short', { n: item.months }) }}
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
                    {{ t('dashboard.billing.receipt_btn') }}
                  </button>
                  <button
                    type="button"
                    class="rounded-xl bg-cyan-300 px-3 py-2 text-sm font-extrabold text-slate-900"
                    @click="openReceiptModal(item)"
                  >
                    {{ t('dashboard.billing.get_receipt') }}
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="mt-3 space-y-2">
            <div v-if="historyTokens.length === 0" class="rounded-xl bg-slate-50 p-4 text-center text-sm text-slate-500 dark:bg-slate-700/40 dark:text-slate-400">
              {{ t('dashboard.billing.history_no_tokens') }}
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

    <div
      v-else-if="loading || (hasInitData && me === null && !error && !bootError)"
      class="py-6"
    >
      <GuardBlueLoadingState />
    </div>

    <div
      v-else
      class="rounded-xl border border-white/10 bg-white/[0.06] p-4 text-sm text-white/85 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
    >
      <p>{{ t('app.profile_error') }}</p>
      <button
        type="button"
        class="mt-3 w-full rounded-lg bg-lime-500/20 px-3 py-2 text-sm font-semibold text-lime-100 ring-1 ring-lime-500/30"
        @click="loadMeInitial"
      >
        {{ t('common.refresh') }}
      </button>
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
          <li>{{ t('dashboard.home_shell.quick_faq.li1') }}</li>
          <li>{{ t('dashboard.home_shell.quick_faq.li2') }}</li>
          <li>{{ t('dashboard.home_shell.quick_faq.li3') }}</li>
          <li>{{ t('dashboard.home_shell.quick_faq.li4') }}</li>
        </ol>
        <p class="mt-3 text-xs text-gray-500 dark:text-gray-400">
          {{ t('dashboard.home_shell.quick_faq.tip') }}
        </p>
      </div>
    </div>

    <div
      v-if="showAccountHistoryModal"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center bg-black/40 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur-md md:items-center md:pb-3"
      role="dialog"
      aria-modal="true"
      :aria-label="t('dashboard.home_shell.history_modal.aria')"
      @click.self="showAccountHistoryModal = false"
    >
      <div
        class="flex max-h-[min(85vh,calc(100dvh-2.5rem))] w-full max-w-md flex-col overflow-hidden rounded-[22px] border border-black/[0.08] bg-[#f2f2f7] shadow-[0_25px_80px_-24px_rgba(0,0,0,0.45)] dark:border-white/[0.12] dark:bg-[#1c1c1e]"
        @click.stop
      >
        <div class="flex shrink-0 items-center justify-between px-4 pb-2 pt-3">
          <h2 class="text-[17px] font-semibold tracking-tight text-black dark:text-white">{{ t('dashboard.home_shell.history_modal.title') }}</h2>
          <button
            type="button"
            class="flex h-8 w-8 items-center justify-center rounded-full bg-black/[0.06] text-[17px] font-light leading-none text-black/45 transition active:scale-95 dark:bg-white/[0.12] dark:text-white/55 dark:hover:bg-white/[0.18]"
            :aria-label="t('common.close')"
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
              {{ t('dashboard.home_shell.history_modal.payments') }}
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
              {{ t('dashboard.home_shell.history_modal.tokens') }}
            </button>
          </div>

          <div v-if="historyLoading" class="py-8 text-center text-[15px] text-black/35 dark:text-white/35">{{ t('dashboard.home_shell.moment') }}</div>
          <div v-else-if="historyTab === 'payments'" class="space-y-2">
            <div
              v-if="historyPayments.length === 0"
              class="rounded-[14px] bg-white px-4 py-6 text-center text-[15px] text-black/45 dark:bg-white/[0.06] dark:text-white/45"
            >
              {{ t('dashboard.home_shell.history_modal.no_payments') }}
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
                      {{ fmtAmount(item.amount_rub) }} ₽ · {{ t('dashboard.billing.months_short', { n: item.months }) }}
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
                    {{ t('dashboard.billing.get_receipt') }}
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
              {{ t('dashboard.billing.history_no_tokens') }}
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
          <h3 class="text-sm font-semibold text-white">{{ t('dashboard.home_shell.activity_modal.title') }}</h3>
          <button type="button" class="rounded-lg px-2 py-1 text-sm text-zinc-400 hover:bg-white/10 hover:text-white" @click="showActivityModal = false">✕</button>
        </div>
        <div v-if="activityLoading" class="shrink-0 py-5 text-center text-sm text-zinc-400">{{ t('dashboard.home_shell.moment') }}</div>
        <div v-else-if="activityChats.length === 0" class="shrink-0 py-6 text-center text-sm text-zinc-500">{{ t('dashboard.home_shell.activity_modal.no_groups') }}</div>
        <div v-else class="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-y-contain pr-1 [-webkit-overflow-scrolling:touch]">
          <section class="overflow-hidden rounded-[1.1rem] border border-white/10 bg-black/35 p-2.5 ring-1 ring-white/10 backdrop-blur-xl">
            <p class="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">{{ t('dashboard.home_shell.activity_modal.overall') }}</p>
            <div class="mt-1 grid grid-cols-2 gap-1.5 text-xs sm:grid-cols-3 md:grid-cols-5">
              <div class="rounded-lg border border-white/10 bg-zinc-950/50 p-2 ring-1 ring-white/5 backdrop-blur-md">
                <p class="text-[10px] text-zinc-500">{{ t('dashboard.home_shell.activity_modal.col_total') }}</p>
                <p class="text-base font-bold text-white">{{ activityOverview.total }}</p>
              </div>
              <div class="rounded-lg border border-rose-500/35 bg-rose-950/25 p-2 ring-1 ring-rose-500/15 backdrop-blur-md">
                <p class="text-[10px] text-rose-200/85">{{ t('dashboard.home_shell.activity_modal.col_deleted') }}</p>
                <p class="text-base font-bold text-rose-200">{{ activityOverview.deleted }}</p>
              </div>
              <div class="rounded-lg border border-red-500/40 bg-red-950/30 p-2 ring-1 ring-red-400/20 backdrop-blur-md">
                <p class="text-[10px] text-red-200/90">{{ t('dashboard.home_shell.activity_modal.col_observed') }}</p>
                <p class="text-base font-bold text-red-200">{{ activityOverview.observed }}</p>
              </div>
              <div class="rounded-lg border border-amber-500/35 bg-amber-950/25 p-2 ring-1 ring-amber-400/15 backdrop-blur-md">
                <p class="text-[10px] text-amber-200/85">{{ t('dashboard.home_shell.activity_modal.col_muted') }}</p>
                <p class="text-base font-bold text-amber-200">{{ activityOverview.muted }}</p>
              </div>
              <div class="rounded-lg border border-fuchsia-500/35 bg-fuchsia-950/25 p-2 ring-1 ring-fuchsia-400/15 backdrop-blur-md">
                <p class="text-[10px] text-fuchsia-200/85">{{ t('dashboard.home_shell.activity_modal.col_banned') }}</p>
                <p class="text-base font-bold text-fuchsia-200">{{ activityOverview.banned }}</p>
              </div>
            </div>
          </section>

          <section class="overflow-hidden rounded-[1.1rem] border border-white/10 bg-black/35 p-2.5 ring-1 ring-white/10 backdrop-blur-xl">
            <p class="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">{{ t('dashboard.home_shell.activity_modal.groups') }}</p>
            <div class="mt-1.5 space-y-3">
              <div v-if="activityByGroupDelegated.length">
                <p class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-violet-200/90">{{ t('dashboard.home_shell.activity_modal.delegated') }}</p>
                <div class="space-y-1.5">
                  <div
                    v-for="group in activityByGroupDelegated"
                    :key="`grp-del-${group.chat_id}`"
                    class="rounded-xl border border-violet-400/20 bg-zinc-950/45 p-2 ring-1 ring-violet-500/15 backdrop-blur-md"
                  >
                    <div class="flex items-start justify-between gap-2">
                      <div>
                        <p class="text-xs font-semibold text-white">{{ group.chat_title }}</p>
                        <p class="mt-0.5 text-[11px] text-zinc-300" v-text="t('dashboard.home_shell.activity_modal.group_line', { total: group.total, deleted: group.deleted, observed: group.observed, muted: group.muted, banned: group.banned })"></p>
                      </div>
                      <button
                        type="button"
                        class="shrink-0 rounded-lg border border-white/15 bg-white/8 px-2 py-0.5 text-[11px] font-semibold text-zinc-100 hover:bg-white/14"
                        @click="openGroupActivityDetails(group)"
                      >
                        {{ t('dashboard.home_shell.activity_modal.details') }}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="activityByGroupMine.length">
                <p class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">{{ t('dashboard.home_shell.activity_modal.mine') }}</p>
                <div class="space-y-1.5">
                  <div
                    v-for="group in activityByGroupMine"
                    :key="`grp-own-${group.chat_id}`"
                    class="rounded-xl border border-white/10 bg-zinc-950/40 p-2 ring-1 ring-white/5 backdrop-blur-md"
                  >
                    <div class="flex items-start justify-between gap-2">
                      <div>
                        <p class="text-xs font-semibold text-white">{{ group.chat_title }}</p>
                        <p class="mt-0.5 text-[11px] text-zinc-300" v-text="t('dashboard.home_shell.activity_modal.group_line', { total: group.total, deleted: group.deleted, observed: group.observed, muted: group.muted, banned: group.banned })"></p>
                      </div>
                      <button
                        type="button"
                        class="shrink-0 rounded-lg border border-white/15 bg-white/8 px-2 py-0.5 text-[11px] font-semibold text-zinc-100 hover:bg-white/14"
                        @click="openGroupActivityDetails(group)"
                      >
                        {{ t('dashboard.home_shell.activity_modal.details') }}
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
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center bg-black/70 p-3 backdrop-blur-[2px] md:items-center"
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
              {{ groupStatsRangeExpanded ? t('dashboard.home_shell.group_stats.range_hide') : t('dashboard.home_shell.group_stats.range_show') }}
            </button>
            <div v-if="groupStatsRangeExpanded" class="space-y-1.5 rounded-xl border border-white/12 bg-black/35 p-2 backdrop-blur-md">
              <label class="block text-[10px] text-zinc-500">{{ t('dashboard.home_shell.group_stats.from_dt') }}</label>
              <input v-model="groupStatsFromInput" type="datetime-local" class="w-full rounded-lg border border-white/12 bg-zinc-950/80 px-2 py-1 text-[11px] text-white">
              <label class="block text-[10px] text-zinc-500">{{ t('dashboard.home_shell.group_stats.to_dt') }}</label>
              <input v-model="groupStatsToInput" type="datetime-local" class="w-full rounded-lg border border-white/12 bg-zinc-950/80 px-2 py-1 text-[11px] text-white">
              <button
                type="button"
                class="mt-1 w-full rounded-lg bg-lime-500/90 py-1.5 text-[11px] font-bold text-slate-900"
                @click="applyGroupCustomRange"
              >
                {{ t('dashboard.home_shell.group_stats.apply_range') }}
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
            <p class="border-b border-white/10 px-2 py-1.5 text-[10px] uppercase tracking-wide text-zinc-500">{{ t('dashboard.home_shell.group_stats.events_title') }}</p>
            <div class="space-y-1 px-2 py-2 pb-3">
              <div v-if="groupJournalForModal.length === 0" class="py-4 text-center text-[11px] text-zinc-500">{{ t('dashboard.home_shell.group_stats.events_empty') }}</div>
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
                      :aria-label="t('dashboard.home_shell.group_stats.profile_aria', { name: violatorLabel(item) })"
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
                      :title="t('dashboard.home_shell.group_stats.unmute_done')"
                      :aria-label="t('dashboard.home_shell.group_stats.unmute_done')"
                    >✓</span>
                    <button
                      v-else
                      type="button"
                      class="rounded-md border border-amber-500/50 bg-amber-500/15 px-2 py-1 text-[10px] font-bold text-amber-100 hover:bg-amber-500/25 disabled:opacity-50"
                      :disabled="!!modPrivilegeBusyKey"
                      @click="postChatMemberPrivilege('unmute', groupActivityChatId, item.user_id, journalEventKey(item))"
                    >
                      {{ t('dashboard.home_shell.group_stats.unmute') }}
                    </button>
                  </div>
                  <div v-if="normalizeAction(item.action) === 'ban'" class="flex shrink-0 items-center gap-1">
                    <span
                      v-if="modUnbanDone[journalEventKey(item)]"
                      class="inline-flex h-8 min-w-[2rem] items-center justify-center rounded-full bg-emerald-600/30 text-sm font-bold text-emerald-200 ring-1 ring-emerald-400/40"
                      :title="t('dashboard.home_shell.group_stats.unban_done')"
                      :aria-label="t('dashboard.home_shell.group_stats.unban_done')"
                    >✓</span>
                    <button
                      v-else
                      type="button"
                      class="rounded-md border border-fuchsia-500/50 bg-fuchsia-500/15 px-2 py-1 text-[10px] font-bold text-fuchsia-100 hover:bg-fuchsia-500/25 disabled:opacity-50"
                      :disabled="!!modPrivilegeBusyKey"
                      @click="postChatMemberPrivilege('unban', groupActivityChatId, item.user_id, journalEventKey(item))"
                    >
                      {{ t('dashboard.home_shell.group_stats.unban') }}
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
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center bg-[#03050c]/82 p-3 backdrop-blur-md md:items-center"
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
            <h3 id="updates-roadmap-title" class="text-[17px] font-semibold tracking-tight text-white">{{ t('dashboard.home_shell.updates_roadmap.title') }}</h3>
            <button
              type="button"
              class="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-slate-900/55 text-sm text-slate-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] transition hover:bg-slate-800/75 hover:text-white"
              @click="showUpdatesRoadmapModal = false"
            >
              ✕
            </button>
          </div>
          <p class="mt-1 text-[12px] leading-snug text-slate-400/95">
            {{ t('dashboard.home_shell.updates_roadmap.subtitle', { n: UPDATES_HOME_PREVIEW_N }) }}
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
                {{ updatesRoadmapExpanded[s.key] ? t('dashboard.home_shell.updates_roadmap.hide') : t('dashboard.home_shell.updates_roadmap.show_full') }}
              </button>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <div
      v-if="showFundsMovementModal"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center bg-black/65 p-3 backdrop-blur-sm md:items-center"
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
          <h3 id="funds-modal-title" class="text-sm font-semibold text-slate-900 dark:text-white">{{ t('dashboard.home_shell.funds_modal.title') }}</h3>
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
              {{ t('dashboard.home_shell.funds_modal.tab_payments') }}
            </button>
            <button
              type="button"
              class="rounded-xl px-3 py-2 text-sm font-semibold"
              :class="historyTab === 'tokens' ? 'bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-200' : 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200'"
              @click="historyTab = 'tokens'"
            >
              {{ t('dashboard.home_shell.funds_modal.tab_tokens') }}
            </button>
          </div>
          <div v-if="historyLoading" class="py-6 text-center text-sm text-slate-500 dark:text-slate-400">{{ t('dashboard.home_shell.moment') }}</div>
          <div v-else-if="historyTab === 'payments'" class="mt-3 space-y-2">
            <div v-if="historyPayments.length === 0" class="rounded-xl bg-slate-50 p-4 text-center text-sm text-slate-500 dark:bg-slate-700/40 dark:text-slate-400">
              {{ t('dashboard.home_shell.funds_modal.no_payments') }}
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
                      {{ fmtAmount(item.amount_rub) }} ₽ · {{ t('dashboard.billing.months_short', { n: item.months }) }}
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
                    {{ t('dashboard.billing.receipt_btn') }}
                  </button>
                  <button
                    type="button"
                    class="rounded-xl bg-cyan-300 px-3 py-2 text-sm font-extrabold text-slate-900"
                    @click="openReceiptModal(item)"
                  >
                    {{ t('dashboard.billing.get_receipt') }}
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="mt-3 space-y-2">
            <div v-if="historyTokens.length === 0" class="rounded-xl bg-slate-50 p-4 text-center text-sm text-slate-500 dark:bg-slate-700/40 dark:text-slate-400">
              {{ t('dashboard.billing.history_no_tokens') }}
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
          <h3 class="text-base font-semibold text-gray-900 dark:text-white">{{ t('dashboard.billing.receipt_modal_title') }}</h3>
          <button
            type="button"
            class="rounded-lg px-2 py-1 text-sm text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700"
            @click="showReceiptModal = false"
          >
            ✕
          </button>
        </div>
        <p class="mb-3 text-sm text-gray-600 dark:text-gray-300">
          {{ t('dashboard.billing.receipt_modal_hint') }}
        </p>
        <div class="space-y-2">
          <label class="block text-sm text-slate-700 dark:text-slate-300">{{ t('dashboard.billing.receipt_full_name_label') }}</label>
          <input
            v-model="receiptFullName"
            type="text"
            placeholder="Alex Smirnov"
            autocomplete="name"
            class="w-full rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 text-sm text-slate-900"
          >
          <label class="block text-sm text-slate-700 dark:text-slate-300">{{ t('dashboard.billing.receipt_email_label') }}</label>
          <input
            v-model="receiptEmail"
            type="email"
            placeholder="you@email.com"
            autocomplete="email"
            class="w-full rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 text-sm text-slate-900"
          >
          <p class="rounded-xl border border-cyan-300 px-3 py-2 text-sm text-slate-700 dark:text-slate-300">
            {{ t('dashboard.billing.receipt_email_required') }}
          </p>
          <button
            type="button"
            class="mt-2 w-full rounded-xl bg-cyan-300 px-4 py-3 text-lg font-extrabold text-slate-900 disabled:opacity-50"
            :disabled="receiptSending || !receiptEmail"
            @click="submitReceipt"
          >
            {{ t('dashboard.billing.get_receipt') }}
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="showAurumHelpModal"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center bg-black/70 p-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] backdrop-blur-[3px] md:items-center md:pb-6"
      @click.self="showAurumHelpModal = false"
    >
      <div
        class="w-full max-w-lg overflow-hidden rounded-[1.25rem] border border-white/[0.14] bg-gradient-to-b from-zinc-900/75 to-zinc-950/92 p-4 text-slate-100 shadow-[0_28px_90px_-28px_rgba(0,0,0,0.9)] ring-1 ring-inset ring-white/[0.06] backdrop-blur-2xl"
        @click.stop
      >
        <div class="mb-3 flex items-center justify-between gap-2 border-b border-white/10 pb-2">
          <h3 class="text-sm font-semibold tracking-tight text-white">{{ t('dashboard.billing.aurum_modal_title') }}</h3>
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
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center bg-black/75 p-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] backdrop-blur-[4px] md:items-center md:pb-6"
      @click.self="showPremiumAurumShowcaseModal = false"
    >
      <div
        class="w-full max-w-lg overflow-hidden rounded-[1.25rem] border border-white/[0.14] bg-gradient-to-b from-zinc-900/80 via-zinc-950/92 to-black px-3 py-3.5 text-white shadow-[0_28px_90px_-28px_rgba(34,211,238,0.15)] ring-1 ring-inset ring-white/[0.06] backdrop-blur-2xl sm:px-4 sm:py-4"
        @click.stop
      >
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="min-w-0 truncate text-[14px] font-semibold tracking-tight text-white/95">{{ t('dashboard.tokens.title') }}</h3>
          <div class="flex shrink-0 items-center gap-2">
            <div
              class="rounded-md border border-white/[0.1] bg-white/[0.05] px-2 py-0.5 text-right shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
              :title="t('dashboard.billing.aurum_gate_total_hint')"
            >
              <p class="text-[8px] font-medium uppercase leading-none tracking-[0.12em] text-white/38">{{ t('dashboard.billing.aurum_gate_total_label') }}</p>
              <p class="text-xs font-bold leading-tight tabular-nums text-amber-200">{{ totalTokens }}<span class="ml-px text-[9px]">⚡</span></p>
            </div>
            <button
              type="button"
              class="rounded-lg px-2 py-1 text-sm text-white/50 hover:bg-white/10 hover:text-white"
              :aria-label="t('dashboard.billing.close_aria')"
              @click="showPremiumAurumShowcaseModal = false"
            >
              ✕
            </button>
          </div>
        </div>
        <div class="rounded-xl border border-white/[0.1] bg-zinc-900/85 px-3 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
          <p class="text-center text-[13px] font-semibold text-white">{{ t('dashboard.billing.showcase_intro') }}</p>
          <div class="mt-3 grid grid-cols-4 gap-1.5 sm:gap-2">
            <div
              class="flex min-h-0 flex-col items-center rounded-lg border border-white/[0.12] bg-black/35 px-1 py-2.5 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.09)]"
            >
              <div class="flex h-12 w-12 shrink-0 items-center justify-center">
                <svg viewBox="0 0 24 24" class="h-10 w-10 text-[#38bdf8] drop-shadow-[0_0_12px_rgba(56,189,248,0.75)]" fill="none" aria-hidden="true">
                  <path d="M21.5 4.8 18.4 19c-.2.9-.8 1.1-1.6.7l-4.4-3.2-2.1 2c-.2.2-.4.4-.9.4l.3-4.5 8.3-7.5c.4-.3-.1-.5-.5-.2l-10.2 6.4-4.4-1.4c-.9-.3-.9-.9.2-1.3L19.9 4c.8-.3 1.5.2 1.3.8z" fill="currentColor" />
                </svg>
              </div>
              <p class="mt-1.5 w-full text-balance text-center text-[9px] font-semibold leading-[1.2] text-white/88 sm:text-[10px]">{{ t('dashboard.billing.showcase_f1') }}</p>
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
              <p class="mt-1.5 w-full text-balance text-center text-[9px] font-semibold leading-[1.2] text-white/88 sm:text-[10px]">{{ t('dashboard.billing.showcase_f2') }}</p>
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
              <p class="mt-1.5 w-full text-balance text-center text-[9px] font-semibold leading-[1.2] text-white/88 sm:text-[10px]">{{ t('dashboard.billing.showcase_f3') }}</p>
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
              <p class="mt-1.5 w-full text-balance text-center text-[9px] font-semibold leading-[1.2] text-white/88 sm:text-[10px]">{{ t('dashboard.billing.showcase_f4') }}</p>
            </div>
          </div>
        </div>
        <button
          type="button"
          class="relative mt-3 w-full overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-white text-center shadow-[0_14px_42px_-14px_rgba(243,156,18,0.62),inset_0_1px_0_rgba(255,255,255,0.28)] transition active:scale-[0.99]"
          style="background: linear-gradient(90deg, #f39c12 0%, #df5a3b 34%, #b043cc 56%, #5c2dc1 74%, #2a1a83 100%);"
          @click="openTokenPacksFromShowcase"
        >
          {{ t('dashboard.billing.buy_tokens') }}
        </button>
      </div>
    </div>

    <div
      v-if="showFreeAurumGateModal"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center bg-black/75 p-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] backdrop-blur-[4px] md:items-center md:pb-6"
      @click.self="showFreeAurumGateModal = false"
    >
      <div
        class="w-full max-w-lg overflow-hidden rounded-[1.25rem] border border-white/[0.14] bg-gradient-to-b from-zinc-900/80 via-zinc-950/92 to-black px-3 py-3.5 text-white shadow-[0_28px_90px_-28px_rgba(34,211,238,0.15)] ring-1 ring-inset ring-white/[0.06] backdrop-blur-2xl sm:px-4 sm:py-4"
        @click.stop
      >
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="min-w-0 truncate text-[14px] font-semibold tracking-tight text-white/95">{{ t('dashboard.tokens.title') }}</h3>
          <div class="flex shrink-0 items-center gap-2">
            <div
              class="rounded-md border border-white/[0.1] bg-white/[0.05] px-2 py-0.5 text-right shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
              :title="t('dashboard.billing.aurum_gate_total_hint')"
            >
              <p class="text-[8px] font-medium uppercase leading-none tracking-[0.12em] text-white/38">{{ t('dashboard.billing.aurum_gate_total_label') }}</p>
              <p class="text-xs font-bold leading-tight tabular-nums text-amber-200">0<span class="ml-px text-[9px]">⚡</span></p>
            </div>
            <button
              type="button"
              class="rounded-lg px-2 py-1 text-sm text-white/50 hover:bg-white/10 hover:text-white"
              :aria-label="t('dashboard.billing.close_aria')"
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
          <p class="text-[13px] font-semibold leading-tight text-white">{{ t('dashboard.billing.aurum_gate_unavailable') }}</p>
          <p class="mt-2 text-[11px] leading-snug text-white/55">
            {{ t('dashboard.billing.aurum_gate_sub') }}
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
          {{ t('dashboard.billing.gate_get_premium') }}
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
            <span>{{ t('dashboard.billing.gate_li_unlock') }}</span>
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
            <span>{{ t('dashboard.billing.gate_li_broadcast') }}</span>
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
            <span>{{ t('dashboard.billing.gate_li_clients') }}</span>
          </li>
        </ul>
      </div>
    </div>

    <div
      v-if="showTokensInfoModal"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center bg-black/70 p-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] backdrop-blur-[3px] md:items-center md:pb-6"
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
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center bg-black/70 p-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] backdrop-blur-[3px] md:items-center md:pb-6"
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
                {{
                  premiumPayMethodFlow === 'tokens'
                    ? t('dashboard.billing.pay_method_title_tokens')
                    : t('dashboard.billing.pay_method_title_subscribe')
                }}
              </h3>
              <button
                type="button"
                :class="tokensInfoBtnClass"
                :title="t('dashboard.info.pay_method_hint_title')"
                :aria-label="t('dashboard.info.pay_method_hint_aria')"
                @click="openPremiumPayMethodInfo"
              >i</button>
            </div>
            <p class="mt-0.5 text-[13px] text-white/50">
              {{
                premiumPayMethodFlow === 'tokens'
                  ? t('dashboard.billing.pay_subtitle_tokens')
                  : t('dashboard.billing.pay_subtitle_subscribe')
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
            :aria-label="t('dashboard.billing.close_aria')"
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
              <span class="block text-[14px] font-bold text-white">{{ t('dashboard.billing.pay_card_title') }}</span>
              <span class="mt-0.5 block text-[12px] text-white/55">{{ t('dashboard.billing.pay_card_hint') }}</span>
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
              <span class="mt-0.5 block text-[12px] text-white/55">{{ t('dashboard.billing.pay_stars_hint') }}</span>
            </span>
            <span class="text-white/35" aria-hidden="true">{{ premiumPayMethodSelected === 'stars' ? '✓' : '○' }}</span>
          </button>
        </div>

        <div class="mt-4 space-y-1 border-t border-white/10 pt-3 text-[11px] text-white/55">
          <p class="flex items-center gap-2"><span class="text-emerald-400">✓</span><span>{{ t('dashboard.billing.pay_trust_1') }}</span></p>
          <p class="flex items-center gap-2"><span class="text-emerald-400">✓</span><span>{{ t('dashboard.billing.pay_trust_2') }}</span></p>
          <p class="flex items-center gap-2"><span class="text-emerald-400">✓</span><span>{{ t('dashboard.billing.pay_trust_3') }}</span></p>
        </div>

        <button
          type="button"
          class="relative w-full overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-white text-center shadow-[0_14px_42px_-14px_rgba(243,156,18,0.62),inset_0_1px_0_rgba(255,255,255,0.28)] transition active:scale-[0.99]"
          style="background: linear-gradient(90deg, #f39c12 0%, #df5a3b 34%, #b043cc 56%, #5c2dc1 74%, #2a1a83 100%);"
          :disabled="premiumPayMethodProceedLoading"
          @click="onPremiumPayMethodProceed"
        >
          {{ premiumPayMethodProceedLoading ? t('dashboard.billing.pay_preparing') : t('dashboard.billing.pay_proceed') }}
        </button>

        <p class="mt-2 text-center text-[10px] text-white/40">
          {{
            premiumPayMethodFlow === 'tokens'
              ? t('dashboard.billing.pay_legal_tokens')
              : t('dashboard.billing.pay_legal_subscribe')
          }}
        </p>
      </div>
    </div>

    <div
      v-if="showPromoCodeModal"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center bg-black/78 p-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] backdrop-blur-[3px] md:items-center md:pb-6"
      @click.self="closePromoCodeModal"
    >
      <div
        class="w-full max-w-md rounded-[1.25rem] border border-white/[0.14] bg-gradient-to-b from-zinc-900/90 to-zinc-950/95 p-4 text-slate-100 shadow-[0_28px_90px_-28px_rgba(0,0,0,0.9)] ring-1 ring-inset ring-white/[0.06] backdrop-blur-2xl"
        @click.stop
      >
        <div class="mb-2 flex items-start justify-between gap-2">
          <div class="min-w-0">
            <h3 class="text-base font-bold tracking-tight text-white">{{ t('dashboard.billing.promo_title') }}</h3>
            <p class="mt-0.5 text-[13px] text-white/55">{{ t('dashboard.billing.promo_sub') }}</p>
          </div>
          <button
            type="button"
            class="shrink-0 rounded-lg px-2 py-1 text-sm text-white/50 hover:bg-white/10 hover:text-white"
            :aria-label="t('dashboard.billing.close_aria')"
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
            :placeholder="t('dashboard.billing.promo_placeholder')"
            class="min-w-0 flex-1 rounded-xl border border-white/[0.12] bg-white/[0.06] px-3 py-2.5 text-[14px] text-white placeholder:text-white/35 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-md"
          >
          <button
            type="button"
            class="shrink-0 rounded-xl border border-emerald-400/35 bg-emerald-500/20 px-3 py-2.5 text-[12px] font-bold text-emerald-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-md transition hover:bg-emerald-500/28 disabled:opacity-45"
            :disabled="promoLoading || !(promoCode || '').trim()"
            @click="applyPromo()"
          >
            {{ promoLoading ? '...' : t('dashboard.billing.promo_done') }}
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="showPaymentRedirectScreen"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-center justify-center bg-black/90 px-4"
    >
      <div class="w-full max-w-md rounded-[1.4rem] border border-white/10 bg-gradient-to-b from-zinc-900/95 to-black p-6 text-white shadow-[0_28px_90px_-28px_rgba(0,0,0,0.9)]">
        <div class="mx-auto flex h-28 w-28 items-center justify-center rounded-full border border-violet-500/35 bg-violet-500/10 shadow-[0_0_36px_-8px_rgba(139,92,246,0.55)]">
          <span class="text-5xl leading-none text-violet-300" aria-hidden="true">◌</span>
        </div>
        <h3 class="mt-6 text-center text-2xl font-bold tracking-tight">{{ t('dashboard.billing.redirect_title') }}</h3>
        <p class="mx-auto mt-3 max-w-xs text-center text-sm leading-relaxed text-white/65">
          {{ t('dashboard.billing.redirect_sub') }}
        </p>

        <div class="mx-auto mt-6 max-w-xs space-y-2 text-sm text-white/72">
          <p class="flex items-center gap-2"><span class="text-emerald-400">✓</span><span>{{ t('dashboard.billing.redirect_trust_1') }}</span></p>
          <p class="flex items-center gap-2"><span class="text-emerald-400">✓</span><span>{{ t('dashboard.billing.redirect_trust_2') }}</span></p>
          <p class="flex items-center gap-2"><span class="text-emerald-400">✓</span><span>{{ t('dashboard.billing.redirect_trust_3') }}</span></p>
        </div>

        <p class="mt-6 text-center text-sm font-semibold text-violet-300">
          {{ t('dashboard.billing.redirect_opening', { n: paymentRedirectCountdown }) }}
        </p>

        <button
          type="button"
          class="relative w-full overflow-hidden rounded-2xl px-4 py-3 text-[15px] font-extrabold tracking-tight text-white text-center shadow-[0_14px_42px_-14px_rgba(243,156,18,0.62),inset_0_1px_0_rgba(255,255,255,0.28)] transition active:scale-[0.99]"
          style="background: linear-gradient(90deg, #f39c12 0%, #df5a3b 34%, #b043cc 56%, #5c2dc1 74%, #2a1a83 100%);"
          @click="proceedToPaymentNow"
        >
          {{ t('dashboard.billing.redirect_cta') }}
        </button>
      </div>
    </div>

    <div
      v-if="showPremiumActivatedModal"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-center justify-center bg-black/88 px-4"
    >
      <div class="w-full max-w-md rounded-[1.4rem] border border-white/10 bg-gradient-to-b from-zinc-900/95 to-black p-5 text-white shadow-[0_28px_90px_-28px_rgba(0,0,0,0.9)]">
        <div class="mx-auto flex h-28 w-28 items-center justify-center rounded-full border border-emerald-400/45 bg-emerald-500/10 shadow-[0_0_36px_-8px_rgba(16,185,129,0.6)]">
          <span class="text-5xl leading-none" aria-hidden="true">🛡️</span>
        </div>

        <h3 class="mt-5 text-center text-[2rem] font-bold leading-tight">{{ t('dashboard.billing.activated_title') }}</h3>
        <p class="mx-auto mt-2 max-w-xs text-center text-[15px] leading-relaxed text-white/70">
          {{ t('dashboard.billing.activated_sub') }}
        </p>

        <div class="mt-5 space-y-2 rounded-xl border border-white/10 bg-white/[0.03] p-3 text-[14px] text-white/80">
          <p class="flex items-center gap-2"><span class="text-emerald-400">✓</span><span>{{ t('dashboard.billing.activated_1') }}</span></p>
          <p class="flex items-center gap-2"><span class="text-emerald-400">✓</span><span>{{ t('dashboard.billing.activated_2') }}</span></p>
          <p class="flex items-center gap-2"><span class="text-emerald-400">✓</span><span>{{ t('dashboard.billing.activated_3') }}</span></p>
        </div>

        <button
          type="button"
          class="mt-5 w-full rounded-2xl bg-gradient-to-r from-violet-600 via-violet-500 to-indigo-600 py-3.5 text-[15px] font-extrabold text-white shadow-[0_14px_44px_-16px_rgba(124,58,237,0.72)] transition hover:brightness-105 active:scale-[0.99]"
          @click="closePremiumActivatedModalToHome"
        >
          {{ t('dashboard.billing.activated_ok') }}
        </button>

        <button
          type="button"
          class="mt-2 w-full text-center text-[13px] font-medium text-violet-300 underline decoration-violet-400/55 underline-offset-4 transition hover:text-violet-200"
          @click="onPremiumActivatedGoSubscription"
        >
          {{ t('dashboard.billing.activated_my_sub') }}
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

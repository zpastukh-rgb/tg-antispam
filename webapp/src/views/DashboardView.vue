<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useApi, messageFromApiError } from '../composables/useApi'
import { api as rawApi } from '../api/client'
import NavIcon from '../components/NavIcon.vue'
import SubscriptionManagementPanel from '../components/SubscriptionManagementPanel.vue'
import { useDashboardSection } from '../composables/useDashboardSection'
import { useToast } from '../composables/useToast'
import { formatDateTimeRu, formatDateTimeShortRu } from '../utils/formatDateTime'
import { openTelegramDeepLink } from '../utils/openTelegramDeepLink'

const router = useRouter()
const route = useRoute()
const { api, loading, error, fetchSilent, hasInitData } = useApi()
const { showToast } = useToast()
const bootError = ref('')
const { dashboardSection, setDashboardSection, billingFromGroupStats } = useDashboardSection()
const me = ref(null)
const showQuickStartModal = ref(false)
const quickHintKey = ref('')
const showMoreMenu = ref(false)
const historyTab = ref('payments')
const historyLoading = ref(false)
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
const moreMenuWrapRef = ref(null)
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

/** Круглые кнопки справа сверху: тот же размер/стиль, что и «Токены» */
const quickNavTileClass =
  'relative inline-flex h-7 w-7 items-center justify-center rounded-full border border-cyan-400/50 bg-gradient-to-br from-cyan-500/35 via-lime-400/25 to-fuchsia-600/25 text-lime-100 shadow-[0_0_18px_-6px_rgba(34,211,238,0.42)] backdrop-blur-md transition hover:brightness-110'
const quickNavTileIconClass = 'h-4 w-4 text-lime-200 drop-shadow-[0_0_8px_rgba(190,242,100,0.75)]'
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
let activityTimer = null
let updatesTimer = null
let quickHintTimer = null
/** Счётчик запросов activitySummary: не применять устаревший ответ при гонке параллельных вызовов */
let activitySummaryFetchGen = 0

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
const dashboardAvatarSrc = computed(() => {
  const base = import.meta.env.BASE_URL
  return tariffIsPremium.value ? `${base}premium-guard-emblem.png` : `${base}avatar-free.png`
})
/** Уникальные id для SVG-градиентов статуса защиты */
const protCheckGradId = `prot-ok-${Math.random().toString(36).slice(2, 11)}`
const protOffGradId = `prot-off-${Math.random().toString(36).slice(2, 11)}`
const activityChatsCount = computed(() => Number(activitySummary.value?.chats_count || 0))
const activityGroupsCount = computed(() => Number((activitySummary.value?.groups_count ?? activitySummary.value?.chats_count) || 0))
const activityChannelsCount = computed(() => Number(activitySummary.value?.channels_count || 0))
const activityGroupsLimit = computed(() => Number((activitySummary.value?.groups_limit ?? activitySummary.value?.group_limit ?? activitySummary.value?.chat_limit) || 0))
const activityChannelsLimit = computed(() => Number((activitySummary.value?.channels_limit ?? activitySummary.value?.channel_limit) || 0))
const activityGroupsProgress = computed(() => Number((activitySummary.value?.groups_usage_progress ?? activitySummary.value?.usage_progress) || 0))
const activityChannelsProgress = computed(() => Number(activitySummary.value?.channels_usage_progress || 0))
/** Есть подключённые группы и защита включена */
const protectionStatusOk = computed(() => activityChatsCount.value > 0 && !!activitySummary.value?.protection_active)
/** Нет ни одной группы — отдельное состояние UI */
const protectionStatusNoChats = computed(() => activityChatsCount.value === 0)

/** Слайды виджета «Обновления»: imageUrl — опционально, картинка под текстом внутри карточки */
const UPDATES_SLIDES = [
  {
    key: 'earn',
    headline: 'Заработок с Guard',
    body: 'Приглашай друзей и зарабатывай токены за их оплаты!',
    primaryLabel: 'Заработать',
    primaryAction: 'partner',
    imageUrl: null,
  },
  {
    key: 'casino',
    headline: 'Добавили фильтр казино',
    body: 'Блокируем ставки, казино и спам-рассылки. Проверьте настройки защиты в чате.',
    primaryLabel: 'Посмотреть',
    primaryAction: 'protection',
    imageUrl: null,
  },
  {
    key: 'ai',
    headline: 'Скоро: искусственный интеллект',
    body: 'Готовим умную модерацию и подсказки по настройке антиспама. Следите за новостями!',
    primaryLabel: null,
    primaryAction: null,
    imageUrl: null,
  },
]

/** Справа сверху вниз: токены → FAQ → ещё (без «Тарифа») */
const quickTiles = [
  { key: 'tokens', label: 'AURUM', icon: 'bolt' },
  { key: 'faq', label: 'FAQ', icon: 'help' },
  { key: 'more', label: 'Еще', icon: 'chevrons-down' },
]
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
    showPremiumAurumShowcaseModal.value
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
  try {
    applyMeState(await rawApi.me())
  } catch (e) {
    me.value = null
    const d = String(e?.body?.detail || e?.message || '').trim()
    bootError.value =
      d && !/^load failed$/i.test(d)
        ? d
        : 'Не удалось загрузить профиль. Проверьте интернет или задеплойте API (сервис zealous-bravery).'
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
  preloadTokenLandingOrbit()
  await loadMeInitial()
  if (!dashboardSection.value) setDashboardSection('account')
  if (dashboardSection.value === 'partner') {
    await ensurePartnerData()
    await ensureReferralPeople()
    await ensurePartnerPayouts()
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
  await loadSpikeAlertsState()
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

watch(
  () => [
    showPromoCodeModal.value,
    showPremiumPayMethodModal.value,
    showPaymentRedirectScreen.value,
    showPremiumActivatedModal.value,
    showFreeAurumGateModal.value,
    showPremiumAurumShowcaseModal.value,
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
  if (quickHintTimer) clearTimeout(quickHintTimer)
  if (dashSwitchTimer) clearTimeout(dashSwitchTimer)
  if (tokenHideTimer) clearTimeout(tokenHideTimer)
  if (spikeAlertTimer) clearInterval(spikeAlertTimer)
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

function openSettingsFromMoreMenu() {
  showMoreMenu.value = false
  window.dispatchEvent(new CustomEvent('guard-open-menu'))
}

function openFundsMovementModal() {
  showMoreMenu.value = false
  showFundsMovementModal.value = true
  loadHistoryIfNeeded()
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

  if (showMoreMenu.value) {
    const menuEl = moreMenuWrapRef.value
    if (menuEl && !menuEl.contains(target)) {
      showMoreMenu.value = false
    }
  }
}

function onQuickHintStart(key) {
  if (quickHintTimer) clearTimeout(quickHintTimer)
  quickHintTimer = setTimeout(() => {
    quickHintKey.value = key
  }, 450)
}

function onQuickHintEnd() {
  if (quickHintTimer) clearTimeout(quickHintTimer)
  quickHintTimer = null
  quickHintKey.value = ''
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
    if (section === 'account') refreshActivitySummarySilent()
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

async function refreshActivitySummarySilent() {
  const gen = ++activitySummaryFetchGen
  try {
    const data = await rawApi.activitySummary()
    if (gen !== activitySummaryFetchGen) return
    activitySummary.value = data
  } catch {
    //
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
  showMoreMenu.value = false
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
  refreshActivitySummarySilent()
  if (activityTimer) clearInterval(activityTimer)
  activityTimer = setInterval(() => {
    refreshActivitySummarySilent()
    if (showActivityModal.value) refreshActivityJournalSilent()
    if (showGroupActivityModal.value) refreshGroupActivitySilent()
    if (waitPremiumActivationAfterPayment.value) schedulePremiumActivationCheck()
  }, 3000)
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
  if (historyPayments.value.length || historyTokens.value.length || historyLoading.value) return
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
      class="relative isolate -mx-4 min-h-[calc(100dvh-7.5rem)] px-4 pb-2 pt-0 font-display md:-mx-6 md:px-6 md:pt-1"
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
      <div class="pointer-events-none absolute right-1 top-2 z-20 text-white md:top-3">
        <div class="pointer-events-auto mr-0.5 mt-2 flex flex-col items-center gap-2">
          <template v-for="tile in quickTiles" :key="tile.key">
            <div v-if="tile.key === 'more'" ref="moreMenuWrapRef" class="relative flex items-center justify-center">
              <button
                type="button"
                :class="[quickNavTileClass, showMoreMenu ? 'ring-2 ring-amber-200/75 ring-offset-2 ring-offset-slate-950' : '']"
                :title="tile.label"
                :aria-label="tile.label"
                @touchstart.passive="onQuickHintStart(tile.key)"
                @touchend="onQuickHintEnd"
                @touchcancel="onQuickHintEnd"
                @mousedown="onQuickHintStart(tile.key)"
                @mouseup="onQuickHintEnd"
                @mouseleave="onQuickHintEnd"
                @click="showMoreMenu = !showMoreMenu"
              >
                <NavIcon :name="tile.icon" :class="quickNavTileIconClass" />
                <div
                  v-if="quickHintKey === tile.key"
                  class="pointer-events-none absolute right-[calc(100%+6px)] top-1/2 z-20 -translate-y-1/2 whitespace-nowrap rounded-md border border-slate-500 bg-slate-900 px-2 py-1 text-[10px] text-slate-100"
                >
                  {{ tile.label }}
                </div>
              </button>
              <div
                v-if="showMoreMenu"
                class="absolute right-[calc(100%+8px)] top-0 z-30 w-52 rounded-xl border border-slate-300 bg-white p-1.5 shadow-xl dark:border-slate-600 dark:bg-slate-800"
              >
                <button
                  type="button"
                  class="w-full rounded-lg px-3 py-2 text-left text-sm font-medium text-slate-800 hover:bg-slate-100 dark:text-slate-100 dark:hover:bg-slate-700"
                  @click="openSettingsFromMoreMenu()"
                >
                  <span class="inline-flex items-center gap-2">
                    <NavIcon name="settings" class="h-4 w-4 text-slate-500 dark:text-slate-300" />
                    Настройки
                  </span>
                </button>
                <button
                  type="button"
                  class="mt-1 w-full rounded-lg px-3 py-2 text-left text-sm font-medium text-slate-800 hover:bg-slate-100 dark:text-slate-100 dark:hover:bg-slate-700"
                  @click="openFundsMovementModal()"
                >
                  <span class="inline-flex items-center gap-2">
                    <NavIcon name="calculator" class="h-4 w-4 text-slate-500 dark:text-slate-300" />
                    Движение средств
                  </span>
                </button>
              </div>
            </div>
            <button
              v-else-if="tile.key === 'tokens'"
              type="button"
              :class="[quickNavTileClass, dashboardSection === 'tokens' ? 'ring-2 ring-amber-200/80 ring-offset-2 ring-offset-slate-950' : '']"
              :title="tile.label"
              :aria-label="tile.label"
              @touchstart.passive="onQuickHintStart(tile.key)"
              @touchend="onQuickHintEnd"
              @touchcancel="onQuickHintEnd"
              @mousedown="onQuickHintStart(tile.key)"
              @mouseup="onQuickHintEnd"
              @mouseleave="onQuickHintEnd"
              @click="onQuickNavTokensClick"
            >
              <NavIcon :name="tile.icon" :class="quickNavTileIconClass" />
              <div
                v-if="quickHintKey === tile.key"
                class="pointer-events-none absolute right-[calc(100%+6px)] top-1/2 z-20 -translate-y-1/2 whitespace-nowrap rounded-md border border-slate-500 bg-slate-900 px-2 py-1 text-[10px] text-slate-100"
              >
                {{ tile.label }}
              </div>
            </button>
            <button
              v-else
              type="button"
              :class="[quickNavTileClass, dashboardSection === tile.key ? 'ring-2 ring-amber-200/80 ring-offset-2 ring-offset-slate-950' : '']"
              :title="tile.label"
              :aria-label="tile.label"
              @touchstart.passive="onQuickHintStart(tile.key)"
              @touchend="onQuickHintEnd"
              @touchcancel="onQuickHintEnd"
              @mousedown="onQuickHintStart(tile.key)"
              @mouseup="onQuickHintEnd"
              @mouseleave="onQuickHintEnd"
              @click="showMoreMenu = false; setDashboardSection(tile.key)"
            >
              <NavIcon :name="tile.icon" :class="quickNavTileIconClass" />
              <div
                v-if="quickHintKey === tile.key"
                class="pointer-events-none absolute right-[calc(100%+6px)] top-1/2 z-20 -translate-y-1/2 whitespace-nowrap rounded-md border border-slate-500 bg-slate-900 px-2 py-1 text-[10px] text-slate-100"
              >
                {{ tile.label }}
              </div>
            </button>
          </template>
        </div>
      </div>

      <div class="mt-0 space-y-0">
        <div
          class="relative -ml-5 -mt-0.5 pb-0.5 pl-2.5 pr-11 pt-1 text-slate-100 md:-ml-8 md:pl-3 md:pt-1.5"
          :class="showTokenBreakdown ? 'z-[45]' : ''"
        >
          <div class="flex items-start justify-start gap-0 -translate-y-0.5 md:-translate-y-1">
            <div
              class="relative self-start drop-shadow-[0_4px_16px_rgba(0,0,0,0.35)]"
              :class="
                tariffIsPremium
                  ? 'shrink-0 -translate-x-2.5 translate-y-0.5 md:-translate-x-3 md:translate-y-1'
                  : 'flex h-[calc(10rem/1.5)] w-[calc(10rem/1.5)] flex-none shrink-0 translate-y-1 md:translate-y-1.5'
              "
            >
              <img
                :src="dashboardAvatarSrc"
                alt=""
                draggable="false"
                :class="
                  tariffIsPremium
                    ? 'block h-[8rem] w-[8rem] max-w-[min(8rem,calc(100vw-8.75rem))] max-h-[min(8rem,calc(100vw-8.75rem))] rounded-xl object-contain object-top bg-transparent'
                    : 'block h-full w-full rounded-xl object-contain object-top bg-transparent'
                "
                @dragstart.prevent
              />
              
            </div>
            <div
              class="min-w-0 flex-1 pl-1 pt-4 md:pl-1.5 md:pt-5"
              :class="
                tariffIsPremium
                  ? '-ml-3 -translate-x-1 md:-ml-4 md:-translate-x-2'
                  : '-ml-1 translate-x-2 pl-2 md:-ml-2 md:translate-x-2.5 md:pl-2.5'
              "
            >
              <div class="flex items-center gap-1.5">
                <svg
                  v-if="protectionStatusOk"
                  class="h-3 w-3 shrink-0 self-center [filter:drop-shadow(0_0_2px_rgba(163,230,53,0.5))]"
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
                  <path
                    d="M7 12l3 3 7-7"
                    stroke="white"
                    stroke-width="2.2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
                <svg
                  v-else-if="protectionStatusNoChats"
                  class="h-3 w-3 shrink-0 self-center [filter:drop-shadow(0_0_2px_rgba(251,113,133,0.5))]"
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
                  <path
                    d="M8 8l8 8M16 8L8 16"
                    stroke="white"
                    stroke-width="2.2"
                    stroke-linecap="round"
                  />
                </svg>
                <svg
                  v-else
                  class="h-3 w-3 shrink-0 self-center text-amber-500/90"
                  viewBox="0 0 24 24"
                  fill="none"
                  aria-hidden="true"
                >
                  <circle cx="12" cy="12" r="12" fill="currentColor" />
                  <path d="M8 12h8" stroke="#0a0a0c" stroke-width="2.2" stroke-linecap="round" />
                </svg>
                <p
                  class="text-[13px] font-semibold leading-tight tracking-tight"
                  :class="protectionStatusOk ? 'text-lime-400' : protectionStatusNoChats ? 'text-rose-400' : 'text-amber-400'"
                >
                  <template v-if="protectionStatusOk">Защита активна</template>
                  <template v-else-if="protectionStatusNoChats">Защита отключена</template>
                  <template v-else>Защита не активна</template>
                </p>
                <span class="ml-auto inline-flex min-w-0 shrink-0 items-center text-[13px] font-semibold tabular-nums text-slate-100">
                  <span
                    ref="tokenBreakdownWrapRef"
                    class="relative inline-flex min-h-[1.25rem] items-center gap-0.5 align-middle"
                    @mouseenter="onTokenWrapEnter"
                    @mouseleave="onTokenWrapLeave"
                  >
                    <span class="inline-block tabular-nums">{{ totalTokens }}</span>
                    <button
                      type="button"
                      class="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-lime-400 transition-colors hover:bg-white/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-lime-300/60"
                      aria-label="Состав токенов"
                      @click.stop="onTokensBoltClick"
                    >
                      <NavIcon name="bolt" class="pointer-events-none h-4 w-4" />
                    </button>
                    <div
                      v-show="showTokenBreakdown"
                      class="pointer-events-auto absolute right-0 top-[calc(100%+8px)] z-[60] w-[12.25rem] max-w-[min(12.25rem,calc(100vw-3.25rem))] overflow-hidden rounded-2xl border border-lime-400/25 bg-gradient-to-b from-slate-900/98 via-zinc-950/98 to-black/95 px-3 py-3 text-left shadow-[0_16px_48px_-12px_rgba(0,0,0,0.9),0_0_28px_-8px_rgba(163,230,53,0.18),inset_0_1px_0_rgba(255,255,255,0.08)] ring-1 ring-inset ring-white/[0.07] backdrop-blur-xl"
                      @mouseenter="onTokenWrapEnter"
                      @mouseleave="onTokenWrapLeave"
                    >
                      <div class="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-lime-300/45 to-transparent" aria-hidden="true" />
                      <p class="text-[15px] font-extrabold leading-tight tracking-tight text-white">
                        Всего
                        <span class="ml-1.5 inline-block tabular-nums text-lime-100 drop-shadow-[0_0_14px_rgba(190,242,100,0.35)]">{{ totalTokens }}</span>
                      </p>
                      <div class="mt-2.5 space-y-2 border-t border-white/10 pt-2.5">
                        <p class="flex items-baseline justify-between gap-2 text-[13px] leading-tight">
                          <span class="shrink-0 text-[11px] font-bold uppercase tracking-wide text-slate-400">AURUM</span>
                          <span class="min-w-0 text-right font-bold tabular-nums text-cyan-100 drop-shadow-[0_0_12px_rgba(34,211,238,0.28)]">{{ fmtAmount(me?.aurum_tokens || 0) }} ✨</span>
                        </p>
                        <p class="flex items-baseline justify-between gap-2 text-[13px] leading-tight">
                          <span class="shrink-0 text-[11px] font-bold uppercase tracking-wide text-slate-400">Партнёрские</span>
                          <span class="min-w-0 text-right font-bold tabular-nums text-lime-200 drop-shadow-[0_0_12px_rgba(190,242,100,0.22)]">{{ fmtAmount(me?.partner_tokens || 0) }} ⚡</span>
                        </p>
                      </div>
                    </div>
                  </span>
                </span>
              </div>
              <div class="mt-1 flex flex-col gap-1">
                <p v-if="Number(me?.broadcast_spend_tokens || 0) > 0" class="text-[11px] leading-tight text-slate-400">
                  На рассылки в кабинете потрачено:
                  <span class="font-semibold text-amber-200/95">{{ fmtAmount(me.broadcast_spend_tokens) }}</span>
                  <NavIcon name="bolt" class="ml-0.5 inline-block h-3 w-3 align-middle text-amber-300/90" />
                </p>
                <div class="text-[11px] leading-tight text-slate-300">
                  <div class="flex w-full min-w-0 flex-col gap-1">
                    <div class="flex min-w-0 flex-col gap-0">
                      <div class="flex min-w-0 flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
                        <span class="shrink-0 text-[12px] font-semibold text-slate-200">Группы / чаты:</span>
                        <span class="shrink-0 text-[12px] font-semibold tabular-nums text-slate-100">
                          {{ activityGroupsCount }} / {{ activityGroupsLimit }}
                        </span>
                      </div>
                      <div class="-mt-px flex min-w-0 items-center gap-0.5">
                        <div
                          class="h-1.5 min-w-0 max-w-[min(10rem,calc(100%-1.125rem))] flex-1 overflow-hidden rounded-full bg-slate-700/60"
                        >
                          <div
                            class="h-full rounded-full transition-all duration-300"
                            :style="{
                              width: `${Math.max(0, Math.min(100, Number(activityGroupsProgress || 0)))}%`,
                              background: `linear-gradient(90deg, rgba(190,242,100,0.75) 0%, rgba(132,204,22,0.9) 50%, rgba(52,211,153,0.7) 100%)`,
                            }"
                          />
                        </div>
                        <button
                          type="button"
                          class="inline-flex h-5 w-5 min-w-[1.25rem] shrink-0 items-center justify-center rounded-md bg-gradient-to-b from-lime-300 to-lime-600 text-[13px] font-bold leading-none text-lime-950 shadow-[0_3px_10px_rgba(101,163,13,0.5),inset_0_1px_0_rgba(255,255,255,0.35)] ring-1 ring-lime-200/60 transition duration-200 hover:scale-[1.06] hover:from-lime-200 hover:to-lime-500 hover:shadow-[0_5px_18px_rgba(163,230,53,0.7)] hover:ring-lime-100/80 active:scale-[0.98]"
                          aria-label="Подключить группу"
                          title="Подключить группу"
                          @click="$router.push({ path: '/connect', query: { kind: 'group' } })"
                        >
                          +
                        </button>
                      </div>
                    </div>
                    <div class="flex min-w-0 flex-col gap-0">
                      <div class="flex min-w-0 flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
                        <span class="shrink-0 text-[12px] font-semibold text-amber-200">Каналы:</span>
                        <span class="shrink-0 text-[12px] font-semibold tabular-nums text-amber-100">
                          {{ activityChannelsCount }} / {{ activityChannelsLimit }}
                        </span>
                      </div>
                      <div class="-mt-px flex min-w-0 items-center gap-0.5">
                        <div
                          class="h-1.5 min-w-0 max-w-[min(10rem,calc(100%-1.125rem))] flex-1 overflow-hidden rounded-full bg-slate-700/50"
                        >
                          <div
                            class="h-full rounded-full transition-all duration-300"
                            :style="{
                              width: `${Math.max(0, Math.min(100, Number(activityChannelsProgress || 0)))}%`,
                              background: `linear-gradient(90deg, rgba(251,191,36,0.75) 0%, rgba(245,158,11,0.9) 55%, rgba(217,119,6,0.8) 100%)`,
                            }"
                          />
                        </div>
                        <button
                          type="button"
                          class="inline-flex h-5 w-5 min-w-[1.25rem] shrink-0 items-center justify-center rounded-md bg-gradient-to-b from-amber-300 to-amber-600 text-[13px] font-bold leading-none text-amber-950 shadow-[0_3px_10px_rgba(217,119,6,0.5),inset_0_1px_0_rgba(255,255,255,0.35)] ring-1 ring-amber-200/70 transition duration-200 hover:scale-[1.06] hover:from-amber-200 hover:to-amber-500 hover:shadow-[0_5px_18px_rgba(252,211,77,0.75)] hover:ring-amber-100/85 active:scale-[0.98]"
                          aria-label="Подключить канал"
                          title="Подключить канал"
                          @click="$router.push({ path: '/connect', query: { kind: 'channel' } })"
                        >
                          +
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <template v-if="dashboardSection === 'account'">

        <div class="mt-2 grid grid-cols-2 items-start gap-2">
          <div class="min-w-0 p-1">
            <div class="rounded-2xl border border-white/10 bg-white/[0.07] p-2.5 shadow-[0_8px_32px_-8px_rgba(0,0,0,0.55)] backdrop-blur-xl">
              <div class="grid grid-cols-[auto,minmax(0,1fr)] gap-x-1 gap-y-1 items-start text-slate-100">
                <svg class="row-start-1 col-start-1 mt-[3px] h-2.5 w-2.5 shrink-0 text-lime-400" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true">
                  <rect x="1" y="7" width="2.2" height="4" rx="0.4" />
                  <rect x="4.4" y="4" width="2.2" height="7" rx="0.4" />
                  <rect x="7.8" y="1" width="2.2" height="10" rx="0.4" />
                </svg>
                <p class="row-start-1 col-start-2 text-[12px] font-semibold leading-none tracking-tight">Сегодня</p>
                <div class="col-span-2 row-start-2 min-w-0 space-y-0.5 text-[11px] leading-tight text-slate-200">
                  <p v-if="activitySummary?.today?.enabled_metrics?.delete" class="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                    <span class="shrink-0 font-semibold tabular-nums text-white">+{{ activitySummary?.today?.deleted || 0 }}</span>
                    <span class="min-w-0 whitespace-nowrap font-medium text-slate-300">Удалено <span class="font-semibold text-lime-300">сообщений</span></span>
                  </p>
                  <p v-if="activitySummary?.today?.enabled_metrics?.mute" class="flex flex-wrap items-center gap-x-3 gap-y-0.5">
                    <span class="inline-flex shrink-0 items-center gap-2">
                      <svg class="h-3.5 w-3.5 text-amber-200/90" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
                        <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
                        <line x1="3.5" y1="3.5" x2="20.5" y2="20.5" />
                      </svg>
                      <span class="font-semibold tabular-nums text-white">{{ activitySummary?.today?.muted || 0 }}</span>
                    </span>
                    <span class="whitespace-nowrap font-medium text-slate-300">Муты</span>
                  </p>
                  <p v-if="activitySummary?.today?.enabled_metrics?.ban" class="flex flex-wrap items-center gap-x-3 gap-y-0.5">
                    <span class="inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded bg-slate-700 text-[8px]">⛔</span>
                    <span class="shrink-0 font-semibold tabular-nums text-white">{{ activitySummary?.today?.banned || 0 }}</span>
                    <span class="whitespace-nowrap font-medium text-slate-300">Баны</span>
                  </p>
                  <p v-if="activitySummary?.today?.enabled_metrics?.observe" class="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                    <span class="shrink-0 font-semibold tabular-nums text-red-300">+{{ activitySummary?.today?.observed || 0 }}</span>
                    <span class="min-w-0 whitespace-nowrap font-medium text-slate-300">Замечено <span class="font-semibold text-red-300/95">без удаления</span></span>
                  </p>
                </div>
              </div>
              <button
                type="button"
                class="mt-1.5 rounded-xl border border-white/10 bg-black/14 px-2.5 py-0.5 text-[11px] font-semibold text-slate-100 shadow-[0_0_28px_-12px_rgba(52,211,153,0.12)] backdrop-blur-md hover:bg-black/22"
                @click="openActivityDetails"
              >
                Подробнее ›
              </button>
            </div>
          </div>
          <div class="min-w-0 p-1">
            <div
              class="relative rounded-2xl border border-white/10 bg-white/[0.07] p-2.5 shadow-[0_8px_32px_-8px_rgba(0,0,0,0.55)] backdrop-blur-xl"
            >
              <button
                v-if="spikeActiveShared"
                type="button"
                class="absolute right-2 top-2 inline-flex items-center justify-center"
                title="Фиолетовый ADM: есть чат под угрозой"
                aria-label="Открыть делегированные чаты под угрозой"
                @click="openSharedThreatChats"
              >
                <span class="absolute inline-flex h-4 w-4 animate-ping rounded-full bg-yellow-400/55" />
                <span class="relative text-[12px] leading-none text-yellow-300">⚠</span>
              </button>
              <div class="mb-2 flex min-w-0 items-center gap-1.5">
                <div class="flex min-w-0 flex-1 items-center gap-1 pl-0.5">
                  <span class="shrink-0 text-[1.05rem] leading-none drop-shadow-[0_0_6px_rgba(251,146,60,0.35)]" aria-hidden="true">🔥</span>
                  <span class="min-w-0 truncate text-[11px] font-bold tracking-tight text-white">Обновления</span>
                </div>
                <button
                  type="button"
                  class="flex shrink-0 items-center gap-0.5 rounded-md px-1 py-0.5 text-slate-400 hover:bg-white/10 hover:text-slate-200"
                  aria-label="Все обновления"
                  @click="showUpdatesRoadmapModal = true"
                >
                  <span class="flex gap-0.5 text-[9px] leading-none" aria-hidden="true">
                    <span class="h-1 w-1 rounded-full bg-current opacity-80" />
                    <span class="h-1 w-1 rounded-full bg-current opacity-80" />
                    <span class="h-1 w-1 rounded-full bg-current opacity-80" />
                  </span>
                  <span class="text-xs font-medium text-slate-300">›</span>
                </button>
              </div>

              <div
                class="relative min-h-[9.5rem] overflow-hidden rounded-xl border-0 bg-black/22 shadow-[inset_0_0_24px_rgba(0,0,0,0.25)]"
              >
                <img
                  v-if="currentUpdateSlide.imageUrl"
                  :src="currentUpdateSlide.imageUrl"
                  alt=""
                  class="pointer-events-none absolute inset-0 h-full w-full object-cover object-right-bottom opacity-95"
                  draggable="false"
                >
                <div
                  class="pointer-events-none absolute inset-0 bg-gradient-to-br from-black/80 via-black/55 to-black/25"
                  :class="currentUpdateSlide.imageUrl ? '' : 'from-black/70 via-[#1a1520]/85 to-black/40'"
                />
                <div class="relative z-[1] flex min-h-[9.5rem] flex-col p-3 pb-3.5">
                  <p class="text-[13px] font-semibold leading-snug text-white drop-shadow-sm">
                    {{ currentUpdateSlide.headline }}
                  </p>
                  <p class="mt-1.5 text-[11px] font-normal leading-relaxed text-slate-300 drop-shadow-sm">
                    {{ currentUpdateSlide.body }}
                  </p>
                  <div class="mt-auto flex flex-wrap items-center gap-2 pt-3">
                    <button
                      v-if="currentUpdateSlide.primaryLabel"
                      type="button"
                      class="rounded-full bg-gradient-to-r from-lime-400 via-lime-500 to-emerald-700 px-4 py-2 text-[11px] font-bold text-slate-900 shadow-[0_4px_16px_rgba(132,204,22,0.35)]"
                      @click="applyUpdatePrimaryAction()"
                    >
                      {{ currentUpdateSlide.primaryLabel }}
                    </button>
                  </div>
                </div>
              </div>

              <div class="mt-2.5 flex justify-center gap-2">
                <button
                  v-for="(_, idx) in UPDATES_SLIDES"
                  :key="idx"
                  type="button"
                  class="h-2 w-2 rounded-full transition-all"
                  :class="updatesIndex === idx ? 'scale-110 bg-lime-400 shadow-[0_0_8px_rgba(163,230,53,0.7)]' : 'bg-white/25 hover:bg-white/40'"
                  :aria-label="`Слайд ${idx + 1}`"
                  :aria-current="updatesIndex === idx ? 'true' : undefined"
                  @click="selectUpdatesSlide(idx)"
                />
              </div>
            </div>
          </div>
        </div>

        </template>
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
      class="fixed inset-0 z-[70] flex items-end justify-center bg-black/70 p-3 backdrop-blur-sm md:items-center"
      @click.self="showUpdatesRoadmapModal = false"
    >
      <div class="w-full max-w-md rounded-2xl border border-white/10 bg-slate-950/95 p-4 text-slate-100 shadow-2xl">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-base font-semibold text-white">Лента обновлений</h3>
          <button
            type="button"
            class="rounded-lg px-2 py-1 text-sm text-slate-400 hover:bg-white/10 hover:text-white"
            @click="showUpdatesRoadmapModal = false"
          >
            ✕
          </button>
        </div>
        <p class="mb-3 text-xs leading-relaxed text-slate-400">
          Позже сюда добавим загрузку картинок для каждого блока. На главном экране фото можно будет задать в поле <span class="font-mono text-slate-300">imageUrl</span> у слайда — оно ляжет под текст в карточке.
        </p>
        <ul class="space-y-3 text-sm">
          <li
            v-for="(s, idx) in UPDATES_SLIDES"
            :key="s.key"
            class="rounded-xl border border-white/10 bg-black/30 p-3"
          >
            <p class="text-xs font-medium text-lime-400/90">№{{ idx + 1 }} · {{ s.key }}</p>
            <p class="mt-1 font-semibold text-white">{{ s.headline }}</p>
            <p class="mt-1 text-xs leading-relaxed text-slate-400">{{ s.body }}</p>
          </li>
        </ul>
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

  </div>
</template>

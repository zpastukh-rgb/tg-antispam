<script setup>
/**
 * Настройки Mini App — премиальный «Apple» стиль, подтверждения по типам действий, PIN 4 цифры.
 */
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { useApi, messageFromApiError } from '../composables/useApi'
import { useToast } from '../composables/useToast'
import { usePremiumLock } from '../composables/usePremiumLock'
import { useModalScrollLock, resetModalScrollLock } from '../composables/useModalScrollLock'
import NavIcon from '../components/NavIcon.vue'
import SubscriptionManagementPanel from '../components/SubscriptionManagementPanel.vue'
import { formatDateRu, formatDateTimeShortRu } from '../utils/formatDateTime'
import { setLocale as setAppLocale, getLocale, normalizeLocale } from '../i18n'
import { useI18n } from 'vue-i18n'
import {
  GUARD_SECURITY_ACTIONS,
  loadConfirmMaster,
  saveConfirmMaster,
  loadConfirmMap,
  saveConfirmMap,
  loadPinEnabled,
  savePinEnabled,
  loadPinMap,
  savePinMap,
  loadPinHash,
  savePinHash,
  clearPin,
  verifyPin,
  hashPin,
  shouldConfirmForAction,
  shouldAskPinForAction,
} from '../utils/settingsSecurity'
import {
  applySettingsBootCache,
  hydrateSettingsBoot,
  prefetchSettingsBoot,
} from '../utils/settingsViewCache'
import { readBotInfoCache } from '../utils/reportsViewCache'

const router = useRouter()
const { hasInitData, fetchSilent } = useApi()
const { showToast } = useToast()
const { t, locale: i18nLocale } = useI18n()
const { openLock: openPremiumLockModal } = usePremiumLock()

const LANG_KEY = 'guard.settings.lang'
const LANG_AUTO_KEY = 'guard.settings.lang_auto'
const DELEGATION_ON_KEY = 'guard.settings.delegation_enabled'
const RETENTION_KEY = 'guard.settings.retention_months'
const LOGIN_HIST_KEY = 'guard.login_history_v1'

/** Экран навигации (не путать с window.screen) */
const panel = ref('hub')
const me = ref(null)
const botInfo = ref(null)
const loading = ref(false)
const bootErr = ref('')
let meLoadInFlight = null

const delegationLoading = ref(false)
const delegationRows = ref([])
const purgeLoading = ref(false)
const showPurgeConfirm = ref(false)
const pdfBusy = ref(false)
const pdfBusyAction = ref('')
const showPdfModal = ref(false)
const pdfReportType = ref('protection')
const pdfScope = ref('all')
const pdfPeriod = ref('30d')
const pdfChatId = ref('')
const pdfPreviewLoading = ref(false)
const pdfPreview = ref(null)
const pdfObjectUrl = ref('')

const JOIN_REPORT_ORDER = ['day', '3d', 'week', 'month']
const joinReportPeriods = ref([])
const joinReportLoading = ref(false)
const joinReportSaving = ref(false)

const joinReportPresetOptions = computed(() =>
  JOIN_REPORT_ORDER.map((id) => ({
    id,
    label:
      id === 'day'
        ? t('admin.partner_presets.join_day')
        : id === '3d'
          ? t('admin.partner_presets.join_3d')
          : id === 'week'
            ? t('admin.partner_presets.join_week')
            : t('admin.partner_presets.join_month'),
  })),
)

function joinReportEnabled(id) {
  return Array.isArray(joinReportPeriods.value) && joinReportPeriods.value.includes(id)
}

async function loadJoinReportSettings() {
  joinReportLoading.value = true
  try {
    const r = await fetchSilent(() => api.ownerJoinReportSettings())
    joinReportPeriods.value = Array.isArray(r?.periods) ? [...r.periods] : []
  } catch {
    joinReportPeriods.value = []
  } finally {
    joinReportLoading.value = false
  }
}

async function toggleJoinReportPreset(id) {
  if (joinReportSaving.value || joinReportLoading.value) return
  const cur = new Set(joinReportPeriods.value || [])
  if (cur.has(id)) cur.delete(id)
  else cur.add(id)
  const next = JOIN_REPORT_ORDER.filter((p) => cur.has(p))
  joinReportPeriods.value = next
  joinReportSaving.value = true
  try {
    const r = await fetchSilent(() => api.ownerSetJoinReportSettings(next))
    joinReportPeriods.value = Array.isArray(r?.periods) ? [...r.periods] : next
    showToast(t('settings.notifications.saved'))
  } catch (e) {
    showToast(messageFromApiError(e))
    await loadJoinReportSettings()
  } finally {
    joinReportSaving.value = false
  }
}

watch(panel, (p) => {
  if (p === 'joinReportSettings') void loadJoinReportSettings()
})


const PDF_PERIOD_OPTIONS = computed(() => [
  { key: 'today', label: t('dashboard.period.today') },
  { key: '7d', label: t('dashboard.period.7d') },
  { key: '30d', label: t('dashboard.period.30d') },
  { key: '6m', label: t('dashboard.period.6m') },
  { key: '1y', label: t('dashboard.period.1y') },
])

const langs = [
  { code: 'ru', label: 'Русский' },
  { code: 'en', label: 'English' },
]

const retentionOptions = computed(() => {
  const isEn = t('common.locale_code') === 'en'
  if (isEn) {
    return [
      { months: 3, label: '3 months' },
      { months: 6, label: '6 months' },
      { months: 12, label: '12 months' },
      { months: 24, label: '24 months' },
    ]
  }
  return [
    { months: 3, label: '3 месяца' },
    { months: 6, label: '6 месяцев' },
    { months: 12, label: '12 месяцев' },
    { months: 24, label: '24 месяца' },
  ]
})

function readLs(key, fallback = '') {
  try {
    return localStorage.getItem(key) ?? fallback
  } catch {
    return fallback
  }
}
function writeLs(key, val) {
  try {
    localStorage.setItem(key, val)
  } catch {
    //
  }
}

/** Должен совпадать с vue-i18n: при пустом LS берём текущую локаль (Telegram / дефолт), а не жёсткий 'ru'. */
function readInitialUiLang() {
  try {
    const raw = localStorage.getItem(LANG_KEY)
    if (raw != null && String(raw).trim() !== '') return normalizeLocale(raw)
  } catch {
    //
  }
  return getLocale()
}

const uiLang = ref(readInitialUiLang())
const langAuto = ref(readLs(LANG_AUTO_KEY, '1') === '1')
const delegationEnabled = ref(readLs(DELEGATION_ON_KEY, '1') === '1')
const retentionMonths = ref(Number(readLs(RETENTION_KEY, '12')) || 12)

const confirmMaster = ref(loadConfirmMaster())
const confirmMap = ref({ ...loadConfirmMap() })
const pinEnabled = ref(loadPinEnabled())
const pinMap = ref({ ...loadPinMap() })

const sessions = ref([])
const loginHistory = ref([])

/** PIN: модалка и мастер-настройка */
const showPinModal = ref(false)
const pinEntry = ref('')
const pinGateAfterOk = ref(null)
const pinNew = ref('')
const pinNew2 = ref('')
const pinBusy = ref(false)

watch(uiLang, (v) => writeLs(LANG_KEY, normalizeLocale(v)))
watch(langAuto, (v) => writeLs(LANG_AUTO_KEY, v ? '1' : '0'))
watch(delegationEnabled, (v) => writeLs(DELEGATION_ON_KEY, v ? '1' : '0'))
watch(retentionMonths, (v) => writeLs(RETENTION_KEY, String(v)))
watch(confirmMaster, (v) => saveConfirmMaster(v))
watch(
  confirmMap,
  (v) => saveConfirmMap(v),
  { deep: true },
)
watch(
  pinMap,
  (v) => savePinMap(v),
  { deep: true },
)

const langLabel = computed(() => langs.find((l) => l.code === uiLang.value)?.label || 'Русский')
const retentionLabel = computed(() => {
  const o = retentionOptions.value.find((x) => x.months === Number(retentionMonths.value))
  if (o?.label) return o.label
  const isEn = t('common.locale_code') === 'en'
  return isEn ? `${retentionMonths.value} mo` : `${retentionMonths.value} мес.`
})

const botDisplayName = computed(() => 'Guard Bot')
const botHandle = computed(() => {
  const u = String(botInfo.value?.username || '').replace(/^@/, '')
  return u ? `@${u}` : '@guard_bot'
})

const isPremium = computed(() => !!me.value?.is_premium)
const settingsModalOpen = computed(() => showPdfModal.value || showPurgeConfirm.value)
useModalScrollLock(settingsModalOpen)
const subscriptionUntilShort = computed(() => formatDateRu(me.value?.subscription_until))

/** Инвалидация computed после записи PIN в localStorage */
const pinStateRev = ref(0)
const pinIsSet = computed(() => {
  void pinStateRev.value
  return !!loadPinHash()
})

const paymentMethodLabel = computed(() => {
  const source = String(me.value?.subscription_source || '').toLowerCase()
  if (source === 'trial') return t('subscription.payment_method.gift')
  if (source === 'promo') return t('billing.method.promo')
  const p = String(me.value?.payment_method_type || '').toLowerCase()
  if (p.includes('card')) return t('billing.method.yookassa_card')
  if (p.includes('sbp')) return t('billing.method.yookassa_sbp')
  if (p.includes('yoo_money')) return t('billing.method.yookassa')
  if (p) return `${t('billing.method.yookassa')} (${p})`
  return '—'
})

function deviceLabelFromUA() {
  const ua = navigator.userAgent || ''
  const isEn = t('common.locale_code') === 'en'
  if (/Telegram/i.test(ua)) {
    if (/iPhone|iPad/i.test(ua)) return 'Telegram · iOS'
    if (/Android/i.test(ua)) return 'Telegram · Android'
    return 'Telegram Mini App'
  }
  if (/iPhone/i.test(ua)) return 'iPhone'
  if (/iPad/i.test(ua)) return 'iPad'
  if (/Android/i.test(ua)) return 'Android'
  if (/Mac OS X/i.test(ua)) return 'Safari · macOS'
  if (/Windows NT/i.test(ua)) return 'Chrome · Windows'
  if (/Linux/i.test(ua)) return isEn ? 'Browser · Linux' : 'Браузер · Linux'
  return isEn ? 'This device' : 'Это устройство'
}

async function loadSessions() {
  if (!hasInitData.value) {
    sessions.value = []
    return
  }
  try {
    const data = await fetchSilent(() => api.sessionsList())
    sessions.value = Array.isArray(data?.items) ? data.items : []
  } catch {
    sessions.value = []
  }
}

function touchLoginHistory() {
  const entry = {
    at: new Date().toISOString(),
    label: deviceLabelFromUA(),
  }
  let list = []
  try {
    list = JSON.parse(readLs(LOGIN_HIST_KEY, '[]') || '[]')
    if (!Array.isArray(list)) list = []
  } catch {
    list = []
  }
  list.unshift(entry)
  list = list.slice(0, 60)
  try {
    localStorage.setItem(LOGIN_HIST_KEY, JSON.stringify(list))
  } catch {
    //
  }
  loginHistory.value = list
}

async function terminateOtherSessions() {
  const isEn = t('common.locale_code') === 'en'
  try {
    const r = await fetchSilent(() => api.sessionsTerminateOthers())
    await loadSessions()
    showToast(
      isEn
        ? `Sessions terminated: ${Number(r?.removed || 0)}`
        : `Завершено сессий: ${Number(r?.removed || 0)}`,
    )
  } catch (e) {
    showToast(messageFromApiError(e, isEn ? 'Could not terminate other sessions' : 'Не удалось завершить другие сессии'))
  }
}

async function terminateSession(sessionId) {
  const sid = String(sessionId || '')
  if (!sid) return
  const isEn = t('common.locale_code') === 'en'
  try {
    const r = await fetchSilent(() => api.sessionsTerminate({ id: sid }))
    if (r?.terminated_current) {
      showToast(isEn ? 'Current session ended. Restart the Mini App.' : 'Текущая сессия завершена. Перезапустите мини-приложение.')
      return
    }
    await loadSessions()
    showToast(isEn ? 'Session terminated' : 'Сессия завершена')
  } catch (e) {
    showToast(messageFromApiError(e, isEn ? 'Could not terminate session' : 'Не удалось завершить сессию'))
  }
}

function onSettingsSubscriptionProfileUpdate(next) {
  if (next && typeof next === 'object') me.value = next
}

function applyMeLanguageFromProfile(profile) {
  const remoteLang = normalizeLocale(profile?.language)
  if (!remoteLang) return
  uiLang.value = remoteLang
  setAppLocale(remoteLang)
}

function hydrateSettingsFromCache() {
  const cached = hydrateSettingsBoot()
  if (cached.me) {
    me.value = cached.me
    applyMeLanguageFromProfile(cached.me)
  }
  if (cached.botInfo) botInfo.value = cached.botInfo
  return !!(cached.me || cached.botInfo)
}

function onGuardMeRefresh() {
  const cached = hydrateSettingsBoot()
  if (cached.me) me.value = cached.me
  if (cached.botInfo) botInfo.value = cached.botInfo
}

async function loadMe(opts = {}) {
  const background = !!opts.background
  if (!hasInitData.value) {
    loading.value = false
    return
  }
  if (meLoadInFlight) return meLoadInFlight

  const hadCache = hydrateSettingsFromCache()
  if (!background && !hadCache && !me.value) loading.value = true
  bootErr.value = ''

  meLoadInFlight = (async () => {
    try {
      const botCached = readBotInfoCache()
      const [u, bi] = await Promise.all([
        fetchSilent(() => api.me()),
        botCached
          ? Promise.resolve(botCached)
          : fetchSilent(() => api.botInfo()).catch(() => null),
      ])
      if (u) {
        me.value = u
        applyMeLanguageFromProfile(u)
      }
      if (bi && typeof bi === 'object') botInfo.value = bi
      applySettingsBootCache(u, bi)
      if (!u && !me.value) {
        bootErr.value = t('app.profile_error')
      }
    } catch (e) {
      if (!me.value) bootErr.value = messageFromApiError(e, t('app.profile_error'))
    } finally {
      loading.value = false
      meLoadInFlight = null
    }
  })()

  return meLoadInFlight
}

async function chooseLanguage(code) {
  const norm = code === 'en' ? 'en' : 'ru'
  uiLang.value = norm
  setAppLocale(norm)
  panel.value = 'profile'
  if (me.value) me.value.language = norm
  try {
    await api.meSetLanguage(norm)
    showToast(t(norm === 'en' ? 'settings.language.saved_en' : 'settings.language.saved_ru'))
  } catch (e) {
    showToast(messageFromApiError(e, t('settings.language.save_failed')))
  }
}

function managerRoleLabel(perms) {
  const p = perms || {}
  const prot = !!p.protection
  const rep = !!p.reports
  const br = !!p.broadcast
  const fp = !!p.first_post_settings
  if ((prot && rep && br) || (prot && rep)) return t('settings.delegation.role_admin')
  if (prot || rep) return t('settings.delegation.role_moderator')
  if (br || fp) return t('settings.delegation.role_moderator')
  return t('settings.delegation.role_moderator')
}

async function loadDelegations() {
  if (!hasInitData.value || !delegationEnabled.value) {
    delegationRows.value = []
    return
  }
  delegationLoading.value = true
  const rows = []
  try {
    const data = await api.chats('all')
    const chats = (data?.chats || []).filter((c) => !c.is_shared && Number(c.managers_count || 0) > 0)
    await Promise.all(
      chats.map(async (c) => {
        try {
          const m = await api.chatManagers(c.id)
          for (const man of m.managers || []) {
            rows.push({
              chatId: c.id,
              chatTitle: c.title || String(c.id),
              chatUsername: c.username ? `@${String(c.username).replace(/^@/, '')}` : '',
              managerUsername: man.username ? `@${String(man.username).replace(/^@/, '')}` : '',
              managerName: String(man.first_name || '').trim() || `id ${man.user_id}`,
              managerId: man.user_id,
              role: managerRoleLabel(man.permissions),
            })
          }
        } catch {
          //
        }
      }),
    )
    delegationRows.value = rows
  } catch {
    delegationRows.value = []
  } finally {
    delegationLoading.value = false
  }
}

watch(panel, (s) => {
  if (s === 'delegation') loadDelegations()
  if (s === 'security') void loadSessions()
  if (s === 'data' && !pdfChats.value.length) void loadPdfChats()
})

watch(delegationEnabled, () => {
  if (panel.value === 'delegation') loadDelegations()
})

watch(pinEnabled, (on) => {
  savePinEnabled(on)
  if (!on) {
    pinMap.value = { ...loadPinMap() }
    return
  }
  if (!loadPinHash()) {
    pinNew.value = ''
    pinNew2.value = ''
    panel.value = 'pinSetup'
  }
})

function toggleConfirmFor(id) {
  confirmMap.value = { ...confirmMap.value, [id]: !confirmMap.value[id] }
}

function togglePinFor(id) {
  pinMap.value = { ...pinMap.value, [id]: !pinMap.value[id] }
}

function iosSwitchClass(on) {
  return on
    ? 'border-emerald-400/40 bg-emerald-500/[0.32] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.12)]'
    : 'border-white/[0.14] bg-white/[0.09]'
}

async function exportPdf() {
  if (!me.value) return
  if (!isPremium.value) {
    openPremiumLockModal({
      feature: 'pdf_export',
      me: me.value,
      titleKey: 'premium_lock.lock_pdf_export_title',
      descriptionKey: 'premium_lock.lock_pdf_export_body',
    })
    return
  }
  showPdfModal.value = true
  void loadPdfChats()
  await refreshPdfPreview()
}

let pdfRefreshTimer = null
function schedulePdfRefresh() {
  if (!showPdfModal.value) return
  if (pdfRefreshTimer) clearTimeout(pdfRefreshTimer)
  pdfRefreshTimer = setTimeout(() => {
    pdfRefreshTimer = null
    void refreshPdfPreview()
  }, 250)
}

const pdfChats = ref([])
const pdfChatsLoading = ref(false)
const pdfChatRows = computed(() => {
  const rows = Array.isArray(pdfChats.value) ? pdfChats.value : []
  if (pdfScope.value === 'own') return rows.filter((x) => !x.is_shared)
  if (pdfScope.value === 'delegated') return rows.filter((x) => !!x.is_shared)
  return rows
})

function _pdfPeriodApiKey() {
  return pdfPeriod.value === '6m' ? '180d' : pdfPeriod.value === '1y' ? '365d' : pdfPeriod.value
}

function _pdfSelectedChatId() {
  const s = String(pdfChatId.value || '').trim()
  return s && /^-?\d+$/.test(s) ? s : null
}

function _pdfChatTitleById(chatId) {
  const sid = String(chatId || '')
  const row = (pdfChats.value || []).find((c) => String(c.id) === sid)
  return row?.title || sid || t('settings.pdf.filter_all_chats')
}

function revokePdfObjectUrl() {
  if (!pdfObjectUrl.value) return
  try {
    URL.revokeObjectURL(pdfObjectUrl.value)
  } catch {
    //
  }
  pdfObjectUrl.value = ''
}

async function loadPdfChats() {
  if (pdfChatsLoading.value || !hasInitData.value) return
  pdfChatsLoading.value = true
  try {
    const data = await fetchSilent(() => api.chats('all'))
    pdfChats.value = Array.isArray(data?.chats) ? data.chats : []
  } catch {
    pdfChats.value = []
  } finally {
    pdfChatsLoading.value = false
  }
}

const REASON_LABEL_MAP_RU = {
  ads: 'Реклама', vulgar: 'Вульгарность', nazi: 'Нацизм', insult: 'Оскорбления',
  racism: 'Расизм', profanity: 'Мат', stopword: 'Запретные слова', media: 'Медиа',
  link: 'Ссылки', mention: 'Упоминания', casino: 'Казино / ставки', crypto: 'Антикрипт', jobs: 'Подработки',
  politics: 'Анти-политика', religion: 'Религия', esoteric: 'Эзотерика / магия',
  drugs: 'Наркотики',
  buttons: 'Кнопки', antinakrutka: 'Анти-накрутка', flood: 'Флуд', raid: 'Рейд',
  captcha: 'Капча', global_antispam: 'Глобальный антиспам', forward: 'Репосты',
  global_url: 'Глобальные URL', url: 'URL', hate: 'Ненависть', spam: 'Спам',
  other: 'Прочее',
}
const REASON_LABEL_MAP_EN = {
  ads: 'Ads', vulgar: 'Vulgar', nazi: 'Nazi', insult: 'Insults',
  racism: 'Racism', profanity: 'Profanity', stopword: 'Stopwords', media: 'Media',
  link: 'Links', mention: 'Mentions', casino: 'Casino / betting', crypto: 'Anti-crypto', jobs: 'Side jobs',
  politics: 'Anti‑politics', religion: 'Religion', esoteric: 'Esoteric / magic',
  drugs: 'Drugs',
  buttons: 'Buttons', antinakrutka: 'Anti‑boosting', flood: 'Flood', raid: 'Raid',
  captcha: 'Captcha', global_antispam: 'Global antispam', forward: 'Forwards',
  global_url: 'Global URLs', url: 'URL', hate: 'Hate', spam: 'Spam',
  other: 'Other',
}
function _prettyReason(key) {
  const isEn = t('common.locale_code') === 'en'
  const map = isEn ? REASON_LABEL_MAP_EN : REASON_LABEL_MAP_RU
  const k = String(key || '').toLowerCase().replace(/_newbie$/i, '')
  return map[k] || k.replace(/_/g, ' ') || '—'
}

async function refreshPdfPreview() {
  if (!hasInitData.value || pdfPreviewLoading.value) return
  pdfPreviewLoading.value = true
  try {
    const chatId = _pdfSelectedChatId()
    const [breakdown, audienceGender] = await Promise.all([
      fetchSilent(() => api.activityBreakdown(_pdfPeriodApiKey(), pdfScope.value, chatId)),
      pdfReportType.value === 'growth'
        ? fetchSilent(() => api.activityAudienceGender(chatId)).catch(() => null)
        : Promise.resolve(null),
    ])
    // by_reason: бэк отдаёт массив [{reason, count}]. Подстраховка на случай dict.
    let rawReason = breakdown?.by_reason
    let byReasonArr = []
    if (Array.isArray(rawReason)) {
      byReasonArr = rawReason.map((r) => ({
        reason: String(r?.reason || ''),
        count: Math.max(0, Number(r?.count || 0)),
      }))
    } else if (rawReason && typeof rawReason === 'object') {
      byReasonArr = Object.entries(rawReason).map(([reason, count]) => ({
        reason: String(reason || ''),
        count: Math.max(0, Number(count || 0)),
      }))
    }
    byReasonArr = byReasonArr
      .filter((x) => x.reason && x.count > 0)
      .sort((a, b) => b.count - a.count)
      .slice(0, 8)
      .map((x) => ({ ...x, label: _prettyReason(x.reason) }))

    const isGrowth = pdfReportType.value === 'growth'
    const hourSrc = isGrowth
      ? (Array.isArray(breakdown?.by_hour_joins) ? breakdown.by_hour_joins : [])
      : (Array.isArray(breakdown?.by_hour) ? breakdown.by_hour : [])
    const byHour = Array.from({ length: 24 }, (_, i) => ({ hour: i, value: Math.max(0, Number(hourSrc[i] || 0)) }))

    const joined = Math.max(0, Number(breakdown?.total_joined || 0))
    const left = Math.max(0, Number(breakdown?.total_left || 0))
    const chatsTotal = Math.max(0, Number(breakdown?.chats_total || (Array.isArray(breakdown?.chats) ? breakdown.chats.length : 0)))
    const gender = audienceGender?.items || audienceGender || null
    pdfPreview.value = {
      generated_at: new Date().toISOString(),
      report_type: pdfReportType.value,
      period: pdfPeriod.value,
      scope: pdfScope.value,
      chat_id: chatId,
      chat_title: chatId ? _pdfChatTitleById(chatId) : t('settings.pdf.filter_all_chats'),
      deleted: Math.max(0, Number(breakdown?.total_deleted || 0)),
      joined,
      left,
      messages: Math.max(0, Number(breakdown?.total_messages || 0)),
      active_users: Math.max(0, Number(breakdown?.active_users || 0)),
      chats_total: chatsTotal,
      growth_net: joined - left,
      by_reason: byReasonArr,
      by_hour: byHour,
      audience_gender: gender,
    }
    revokePdfObjectUrl()
  } catch (e) {
    const isEn = t('common.locale_code') === 'en'
    showToast(messageFromApiError(e, isEn ? 'Could not load PDF preview' : 'Не удалось загрузить превью PDF'))
  } finally {
    pdfPreviewLoading.value = false
  }
}

const previewPeriodLabel = computed(() => {
  if (!pdfPreview.value) return ''
  return PDF_PERIOD_OPTIONS.value.find((x) => x.key === pdfPreview.value.period)?.label || pdfPreview.value.period
})
const previewScopeLabel = computed(() => {
  if (!pdfPreview.value) return ''
  const s = pdfPreview.value.scope
  return s === 'own' ? t('settings.pdf.filter_own') : s === 'delegated' ? t('settings.pdf.filter_delegated') : t('settings.pdf.filter_all')
})
const previewGeneratedAt = computed(() => {
  if (!pdfPreview.value) return ''
  return formatDateTimeShortRu(pdfPreview.value.generated_at)
})

function previewSparklinePath(byHour, w = 480, h = 110, pad = 16) {
  const arr = Array.isArray(byHour) && byHour.length ? byHour : Array.from({ length: 24 }, () => ({ value: 0 }))
  const vals = arr.map((x) => Math.max(0, Number(x?.value || 0)))
  const maxV = Math.max(1, ...vals)
  const stepX = (w - pad * 2) / Math.max(1, arr.length - 1)
  return arr
    .map((_, i) => {
      const x = pad + i * stepX
      const y = h - pad - (vals[i] / maxV) * (h - pad * 2)
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`
    })
    .join(' ')
}
function previewReasonBarWidth(count) {
  if (!pdfPreview.value || !Array.isArray(pdfPreview.value.by_reason)) return '0%'
  const max = Math.max(1, ...pdfPreview.value.by_reason.map((x) => Number(x.count || 0)))
  return `${Math.max(8, Math.round((Number(count || 0) / max) * 100))}%`
}

let _pdfMakeCache = null
let _pdfMakeLoadPromise = null
async function loadPdfMake() {
  if (_pdfMakeCache) return _pdfMakeCache
  if (_pdfMakeLoadPromise) return _pdfMakeLoadPromise
  _pdfMakeLoadPromise = (async () => {
    const pm = await import('pdfmake/build/pdfmake')
    const pdfMake = pm.default || pm
    const vmod = await import('pdfmake/build/vfs_fonts')
    const vfs =
      vmod?.default?.pdfMake?.vfs ||
      vmod?.pdfMake?.vfs ||
      vmod?.default?.vfs ||
      vmod?.vfs ||
      vmod?.default ||
      vmod
    // Совместимость с 0.2/0.3.
    if (typeof pdfMake.addVirtualFileSystem === 'function') {
      pdfMake.addVirtualFileSystem(vfs)
    } else {
      pdfMake.vfs = vfs
    }
    if (!pdfMake.fonts || !pdfMake.fonts.Roboto) {
      pdfMake.fonts = {
        Roboto: {
          normal: 'Roboto-Regular.ttf',
          bold: 'Roboto-Medium.ttf',
          italics: 'Roboto-Italic.ttf',
          bolditalics: 'Roboto-MediumItalic.ttf',
        },
      }
    }
    _pdfMakeCache = pdfMake
    return pdfMake
  })()
  try {
    return await _pdfMakeLoadPromise
  } finally {
    _pdfMakeLoadPromise = null
  }
}

async function rebuildPdfBlob() {
  if (!pdfPreview.value) throw new Error(t('common.locale_code') === 'en' ? 'No PDF data' : 'Нет данных для PDF')
  const pdfMake = await loadPdfMake()
  const doc = buildPdfDoc(pdfPreview.value)
  const blob = await new Promise((resolve, reject) => {
    let done = false
    const tid = setTimeout(() => {
      if (done) return
      done = true
      reject(new Error('PDF generation timed out'))
    }, 15000)
    try {
      pdfMake.createPdf(doc).getBlob((b) => {
        if (done) return
        done = true
        clearTimeout(tid)
        if (b) resolve(b)
        else reject(new Error('PDF blob is empty'))
      })
    } catch (e) {
      if (done) return
      done = true
      clearTimeout(tid)
      reject(e)
    }
  })
  revokePdfObjectUrl()
  pdfObjectUrl.value = URL.createObjectURL(blob)
  fetchSilent(() =>
    api.pdfExportCreate({
      report_type: pdfPreview.value.report_type,
      period_key: pdfPreview.value.period,
      scope: pdfPreview.value.scope,
      chat_id: pdfPreview.value.chat_id,
      payload: pdfPreview.value,
      from_ts: null,
      to_ts: null,
    }),
  ).catch(() => null)
  return { url: pdfObjectUrl.value, blob }
}

function buildPdfCopyText(preview) {
  const isGrowth = String(preview?.report_type || 'protection') === 'growth'
  const isEn = t('common.locale_code') === 'en'
  const loc = isEn ? 'en-US' : 'ru-RU'
  const lines = isEn
    ? [
        `GUARD — ${isGrowth ? 'Growth statistics' : 'Protection statistics'}`,
        `Period: ${previewPeriodLabel.value || '-'}`,
        `Scope: ${previewScopeLabel.value || '-'}`,
        `Chat: ${preview?.chat_title || t('settings.pdf.filter_all_chats')}`,
        '',
        `Messages: ${Number(preview?.messages || 0).toLocaleString(loc)}`,
        `Active users: ${Number(preview?.active_users || 0).toLocaleString(loc)}`,
        `Chats: ${Number(preview?.chats_total || 0).toLocaleString(loc)}`,
        `Joined: ${Number(preview?.joined || 0).toLocaleString(loc)}`,
        `Left: ${Number(preview?.left || 0).toLocaleString(loc)}`,
      ]
    : [
        `GUARD — ${isGrowth ? 'Статистика роста' : 'Статистика защиты'}`,
        `Период: ${previewPeriodLabel.value || '-'}`,
        `Область: ${previewScopeLabel.value || '-'}`,
        `Чат: ${preview?.chat_title || t('settings.pdf.filter_all_chats')}`,
        '',
        `Сообщений: ${Number(preview?.messages || 0).toLocaleString(loc)}`,
        `Активных пользователей: ${Number(preview?.active_users || 0).toLocaleString(loc)}`,
        `Чатов: ${Number(preview?.chats_total || 0).toLocaleString(loc)}`,
        `Вступили: ${Number(preview?.joined || 0).toLocaleString(loc)}`,
        `Покинули: ${Number(preview?.left || 0).toLocaleString(loc)}`,
      ]
  if (isGrowth) {
    lines.push(isEn ? `Net growth: ${Number(preview?.growth_net || 0).toLocaleString(loc)}` : `Чистый прирост: ${Number(preview?.growth_net || 0).toLocaleString(loc)}`)
  } else {
    lines.push(isEn ? `Deleted: ${Number(preview?.deleted || 0).toLocaleString(loc)}` : `Удалено: ${Number(preview?.deleted || 0).toLocaleString(loc)}`)
  }
  return lines.join('\n')
}

function _hourChartCanvas(byHour, color = '#7dff3a') {
  const chartW = 480
  const chartH = 130
  const pad = 14
  const arr = Array.isArray(byHour) && byHour.length ? byHour : Array.from({ length: 24 }, (_, i) => ({ hour: i, value: 0 }))
  const values = arr.map((x) => Math.max(0, Number(x.value || 0)))
  const maxHour = Math.max(1, ...values)
  const stepX = (chartW - pad * 2) / Math.max(1, arr.length - 1)
  const points = arr.map((x, i) => {
    const v = values[i] || 0
    const px = pad + i * stepX
    const py = chartH - pad - (v / maxHour) * (chartH - pad * 2)
    return { x: Number(px.toFixed(2)), y: Number(py.toFixed(2)) }
  })
  const lineCoords = points.flatMap((p) => [p.x, p.y])
  return {
    stack: [
      {
        canvas: [
          { type: 'rect', x: 0, y: 0, w: chartW, h: chartH, color: '#f8fafc' },
          { type: 'line', x1: pad, y1: chartH - pad, x2: chartW - pad, y2: chartH - pad, lineColor: '#e5e7eb', lineWidth: 0.6 },
          { type: 'polyline', points: lineCoords, lineColor: color, lineWidth: 2.2 },
          ...points.map((p) => ({ type: 'ellipse', x: p.x, y: p.y, r1: 1.6, r2: 1.6, color })),
        ],
      },
      {
        columns: [
          { width: '*', text: '00:00', style: 'axis' },
          { width: '*', text: '06:00', style: 'axis', alignment: 'center' },
          { width: '*', text: '12:00', style: 'axis', alignment: 'center' },
          { width: '*', text: '18:00', style: 'axis', alignment: 'center' },
          { width: '*', text: '23:00', style: 'axis', alignment: 'right' },
        ],
        margin: [0, 4, 0, 0],
      },
    ],
  }
}

function _reasonBars(byReason) {
  const arr = Array.isArray(byReason) ? byReason : []
  const max = Math.max(1, ...arr.map((x) => Number(x.count || 0)))
  return arr.slice(0, 8).map((r) => {
    const w = Math.max(14, Math.round((Number(r.count || 0) / max) * 220))
    return {
      columns: [
        { width: 140, text: String(r.label || r.reason || '—'), color: '#1f2937', noWrap: false },
        {
          width: 230,
          stack: [
            { canvas: [{ type: 'rect', x: 0, y: 6, w: 220, h: 8, color: '#e5e7eb' }] },
            { canvas: [{ type: 'rect', x: 0, y: -2, w, h: 8, color: '#7dff3a' }] },
          ],
        },
        { width: '*', text: String(r.count || 0), alignment: 'right', bold: true, color: '#111827' },
      ],
      margin: [0, 4, 0, 4],
    }
  })
}

function _metricCard(title, value, fill) {
  return {
    width: '*',
    table: {
      widths: ['*'],
      body: [[{
        stack: [
          { text: String(title), style: 'metricLabel' },
          { text: String(value), style: 'metricValue' },
        ],
        fillColor: fill,
        border: [false, false, false, false],
        margin: [10, 8, 10, 10],
      }]],
    },
    layout: 'noBorders',
  }
}

function buildPdfDoc(preview) {
  const isGrowth = String(preview.report_type || 'protection') === 'growth'
  const isEn = t('common.locale_code') === 'en'
  const periodLabel = PDF_PERIOD_OPTIONS.value.find((x) => x.key === preview.period)?.label || preview.period
  const scopeLabel = preview.scope === 'own'
    ? t('settings.pdf.filter_own')
    : preview.scope === 'delegated'
      ? t('settings.pdf.filter_delegated')
      : t('settings.pdf.filter_all')

  const headerMeta = {
    columns: [
      { width: '*', text: `${isEn ? 'Period:' : 'Период:'} ${periodLabel}`, style: 'meta' },
      { width: '*', text: `${isEn ? 'Scope:' : 'Область:'} ${scopeLabel}`, style: 'meta' },
      { width: '*', text: `${isEn ? 'Chat:' : 'Чат:'} ${preview.chat_title}`, style: 'meta', alignment: 'right' },
    ],
    margin: [0, 6, 0, 0],
  }

  const header = {
    stack: [
      { text: 'GUARD', style: 'brand' },
      { text: isGrowth ? (isEn ? 'Growth statistics' : 'Статистика роста') : (isEn ? 'Protection statistics and reports' : 'Статистика защиты и отчётов'), style: 'h1' },
      { text: `${isEn ? 'Generated:' : 'Сформировано:'} ${formatDateTimeShortRu(preview.generated_at)}`, style: 'muted', margin: [0, 2, 0, 0] },
      headerMeta,
    ],
    margin: [0, 0, 0, 12],
  }

  const L = isEn
    ? {
        joined: 'Joined', left: 'Left', netGrowth: 'Net growth',
        messages: 'Messages', activeUsers: 'Active users', activeChats: 'Active chats',
        deleted: 'Deleted', reasons: 'Triggers by reason',
        emptyReasons: 'No triggers for the selected period',
        dynDel: 'Deletions over time (per hour)',
        dynJoin: 'Joins over time (per hour)',
        gender: 'Audience gender', male: 'Male', female: 'Female', unknown: 'Not specified',
        keyMetrics: 'Key metrics',
        footer: 'Report is generated from the same APIs and filters as in-app stats.',
        titleProt: 'GUARD — Protection statistics',
        titleGrow: 'GUARD — Growth statistics',
      }
    : {
        joined: 'Вступлений', left: 'Выходов', netGrowth: 'Рост (нетто)',
        messages: 'Сообщений', activeUsers: 'Активных людей', activeChats: 'Активных чатов',
        deleted: 'Удалено', reasons: 'Срабатывания по причинам',
        emptyReasons: 'Нет срабатываний за выбранный период',
        dynDel: 'Динамика удалений (по часам)',
        dynJoin: 'Динамика вступлений (по часам)',
        gender: 'Пол участников', male: 'Мужчины', female: 'Женщины', unknown: 'Неопределено',
        keyMetrics: 'Ключевые метрики',
        footer: 'Отчёт формируется из тех же API и фильтров, что и статистика в приложении.',
        titleProt: 'GUARD — Статистика защиты',
        titleGrow: 'GUARD — Статистика роста',
      }

  const metricsRows = isGrowth
    ? [
        {
          columns: [
            _metricCard(L.joined, preview.joined, '#dcfce7'),
            _metricCard(L.left, preview.left, '#ede9fe'),
            _metricCard(L.netGrowth, preview.growth_net, '#fef3c7'),
          ],
          columnGap: 8,
        },
        {
          columns: [
            _metricCard(L.messages, preview.messages, '#cffafe'),
            _metricCard(L.activeUsers, preview.active_users, '#e0f2fe'),
            _metricCard(L.activeChats, preview.chats_total, '#f1f5f9'),
          ],
          columnGap: 8,
          margin: [0, 8, 0, 0],
        },
      ]
    : [
        {
          columns: [
            _metricCard(L.deleted, preview.deleted, '#ecfccb'),
            _metricCard(L.messages, preview.messages, '#cffafe'),
            _metricCard(L.activeUsers, preview.active_users, '#e0f2fe'),
          ],
          columnGap: 8,
        },
        {
          columns: [
            _metricCard(L.joined, preview.joined, '#dcfce7'),
            _metricCard(L.left, preview.left, '#ede9fe'),
            _metricCard(L.activeChats, preview.chats_total, '#f1f5f9'),
          ],
          columnGap: 8,
          margin: [0, 8, 0, 0],
        },
      ]

  const protectionSections = [
    { text: L.reasons, style: 'h2', margin: [0, 14, 0, 6] },
    ...(preview.by_reason.length ? _reasonBars(preview.by_reason) : [{ text: L.emptyReasons, style: 'muted' }]),
    { text: L.dynDel, style: 'h2', margin: [0, 14, 0, 6] },
    _hourChartCanvas(preview.by_hour, '#7dff3a'),
  ]

  const growthGender = preview.audience_gender ? {
    margin: [0, 12, 0, 0],
    stack: [
      { text: L.gender, style: 'h2', margin: [0, 0, 0, 6] },
      {
        columns: [
          _metricCard(L.male, Number(preview.audience_gender?.male || 0), '#e0f2fe'),
          _metricCard(L.female, Number(preview.audience_gender?.female || 0), '#fae8ff'),
          _metricCard(L.unknown, Number(preview.audience_gender?.unknown || 0), '#f3f4f6'),
        ],
        columnGap: 8,
      },
    ],
  } : null

  const growthSections = [
    { text: L.dynJoin, style: 'h2', margin: [0, 14, 0, 6] },
    _hourChartCanvas(preview.by_hour, '#22c55e'),
    ...(growthGender ? [growthGender] : []),
  ]

  return {
    content: [
      header,
      { text: L.keyMetrics, style: 'h2', margin: [0, 4, 0, 6] },
      ...metricsRows,
      ...(isGrowth ? growthSections : protectionSections),
      {
        text: L.footer,
        style: 'muted',
        margin: [0, 16, 0, 0],
      },
    ],
    styles: {
      brand: { fontSize: 10, color: '#16a34a', bold: true, characterSpacing: 0.4 },
      h1: { fontSize: 18, bold: true, color: '#111827' },
      h2: { fontSize: 12, bold: true, color: '#111827' },
      muted: { fontSize: 9, color: '#6b7280' },
      meta: { fontSize: 9, color: '#475569' },
      metricLabel: { fontSize: 9, color: '#334155' },
      metricValue: { fontSize: 16, bold: true, color: '#111827', margin: [0, 4, 0, 0] },
      axis: { fontSize: 8, color: '#6b7280' },
    },
    defaultStyle: { fontSize: 10, color: '#111827' },
    pageMargins: [28, 28, 28, 28],
    info: {
      title: isGrowth ? L.titleGrow : L.titleProt,
      author: 'GUARD',
      creator: 'GUARD Mini App',
    },
  }
}

async function ensurePdfReady() {
  if (!pdfObjectUrl.value) {
    if (!pdfPreview.value) await refreshPdfPreview()
    await rebuildPdfBlob()
  }
  const isEn = t('common.locale_code') === 'en'
  if (!pdfObjectUrl.value) throw new Error(isEn ? 'Could not prepare PDF' : 'Не удалось подготовить PDF')
  return pdfObjectUrl.value
}

function _pdfFileName() {
  const type = pdfPreview.value?.report_type === 'growth' ? 'rost' : 'zashchita'
  const period = pdfPreview.value?.period || 'all'
  return `guard-${type}-${period}.pdf`
}

async function openPdfPreviewFile() {
  if (pdfBusy.value) return
  pdfBusy.value = true
  pdfBusyAction.value = 'open'
  try {
    const u = await ensurePdfReady()
    const filename = _pdfFileName()
    // Кросс-платформенно: desktop -> открыть вкладку/скачать, mobile -> share sheet если доступен.
    if (navigator?.canShare && navigator?.share && window.File) {
      try {
        const rebuilt = await rebuildPdfBlob()
        const file = new File([rebuilt.blob], filename, { type: 'application/pdf' })
        if (navigator.canShare({ files: [file] })) {
          await navigator.share({ files: [file], title: filename })
          return
        }
      } catch {
        // fallback ниже
      }
    }
    let opened = false
    try {
      const w = window.open(u, '_blank', 'noopener,noreferrer')
      if (w) opened = true
    } catch {
      //
    }
    if (!opened) {
      const a = document.createElement('a')
      a.href = u
      a.target = '_blank'
      a.rel = 'noopener noreferrer'
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
    }
  } catch (e) {
    const isEn = t('common.locale_code') === 'en'
    showToast(messageFromApiError(e, isEn ? 'Could not open PDF on this device' : 'Не удалось открыть PDF на устройстве'))
  } finally {
    pdfBusyAction.value = ''
    pdfBusy.value = false
  }
}

async function copyPdfLink() {
  if (pdfBusy.value) return
  pdfBusy.value = true
  pdfBusyAction.value = 'copy'
  try {
    if (!pdfPreview.value) await refreshPdfPreview()
    if (!pdfPreview.value) throw new Error(t('settings.pdf.no_data_for_copy'))
    const text = buildPdfCopyText(pdfPreview.value)
    let copied = false
    if (navigator?.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(text)
        copied = true
      } catch {
        //
      }
    }
    if (copied) {
      showToast(t('settings.pdf.copied_text'))
      return
    }
    showToast(t('settings.pdf.copy_clipboard_unavailable'))
  } catch (e) {
    showToast(messageFromApiError(e, t('settings.pdf.copy_failed')))
  } finally {
    pdfBusyAction.value = ''
    pdfBusy.value = false
  }
}

async function runPurge() {
  if (purgeLoading.value) return
  purgeLoading.value = true
  try {
    await api.mePurgeOwnedChatsAnalytics()
    showToast(t('settings.data.purge_done'))
    showPurgeConfirm.value = false
    await loadMe()
  } catch (e) {
    showToast(messageFromApiError(e, t('settings.data.purge_failed')))
  } finally {
    purgeLoading.value = false
  }
}

function continuePurgeAfterPin() {
  showPinModal.value = false
  pinEntry.value = ''
  pinGateAfterOk.value = null
  if (shouldConfirmForAction('purge_data')) {
    showPurgeConfirm.value = true
  } else {
    runPurge()
  }
}

async function startPurge() {
  if (shouldAskPinForAction('purge_data')) {
    pinGateAfterOk.value = () => continuePurgeAfterPin()
    pinEntry.value = ''
    showPinModal.value = true
    return
  }
  if (shouldConfirmForAction('purge_data')) {
    showPurgeConfirm.value = true
    return
  }
  runPurge()
}

async function submitPinModal() {
  const tid = me.value?.telegram_id
  const isEn = t('common.locale_code') === 'en'
  if (tid == null) {
    showToast(isEn ? 'No account data' : 'Нет данных аккаунта')
    return
  }
  const p = String(pinEntry.value || '').replace(/\D/g, '').slice(0, 4)
  if (p.length !== 4) {
    showToast(t('settings.security.pin.gate_hint'))
    return
  }
  pinBusy.value = true
  try {
    const ok = await verifyPin(tid, p, loadPinHash())
    if (!ok) {
      showToast(t('settings.security.pin.wrong'))
      return
    }
    const fn = pinGateAfterOk.value
    pinGateAfterOk.value = null
    showPinModal.value = false
    pinEntry.value = ''
    fn?.()
  } finally {
    pinBusy.value = false
  }
}

async function saveNewPin() {
  const tid = me.value?.telegram_id
  const isEn = t('common.locale_code') === 'en'
  if (tid == null) {
    showToast(isEn ? 'No account data' : 'Нет данных аккаунта')
    return
  }
  const a = String(pinNew.value || '').replace(/\D/g, '').slice(0, 4)
  const b = String(pinNew2.value || '').replace(/\D/g, '').slice(0, 4)
  if (a.length !== 4 || b.length !== 4) {
    showToast(t('settings.security.pin.save_failed'))
    return
  }
  if (a !== b) {
    showToast(t('settings.security.pin.mismatch'))
    return
  }
  pinBusy.value = true
  try {
    const h = await hashPin(tid, a)
    savePinHash(h)
    savePinEnabled(true)
    pinEnabled.value = true
    pinStateRev.value += 1
    showToast(t('settings.security.pin.saved'))
    pinNew.value = ''
    pinNew2.value = ''
    panel.value = 'security'
  } finally {
    pinBusy.value = false
  }
}

function removePin() {
  clearPin()
  pinEnabled.value = false
  pinMap.value = { ...loadPinMap() }
  pinStateRev.value += 1
  savePinEnabled(false)
  showToast(t('settings.security.pin.removed'))
  panel.value = 'security'
}

function onPinMasterClick() {
  if (pinEnabled.value && pinIsSet.value) {
    removePin()
    return
  }
  if (pinEnabled.value && !pinIsSet.value) {
    pinNew.value = ''
    pinNew2.value = ''
    panel.value = 'pinSetup'
    return
  }
  pinEnabled.value = true
}

function goBilling() {
  router.push({ path: '/', query: { section: 'billing' } }).catch(() => {})
}

function goChats() {
  router.push('/chats').catch(() => {})
}

function back() {
  if (panel.value === 'hub') {
    router.back()
    return
  }
  if (panel.value === 'pinSetup' && !loadPinHash()) {
    pinEnabled.value = false
    savePinEnabled(false)
    panel.value = 'security'
    return
  }
  if (panel.value === 'languagePick') {
    panel.value = 'profile'
    return
  }
  if (panel.value === 'retentionPick') {
    panel.value = 'data'
    return
  }
  if (panel.value === 'loginHistory') {
    panel.value = 'security'
    return
  }
  if (panel.value === 'joinReportSettings') {
    panel.value = 'botNotifications'
    return
  }
  if (panel.value === 'botNotifications') {
    panel.value = 'hub'
    return
  }
  if (['confirmActionsDetail', 'pinSetup', 'pinActions'].includes(panel.value)) {
    panel.value = 'security'
    return
  }
  panel.value = 'hub'
}

function panelTitle() {
  const titles = {
    profile: t('settings.profile.title'),
    payment: t('settings.hub.payment.title'),
    data: t('settings.hub.data.title'),
    delegation: t('settings.delegation.title'),
    security: t('settings.security.title'),
    languagePick: t('settings.language.title'),
    retentionPick: t('settings.data.retention_title'),
    loginHistory: t('settings.security.login_history'),
    confirmActionsDetail: t('settings.security.confirm.detail_title'),
    pinSetup: t('settings.security.pin.gate_title'),
    pinActions: t('settings.security.pin.title'),
    botNotifications: t('settings.notifications.menu_title'),
    joinReportSettings: t('settings.notifications.short_reports_title'),
  }
  return titles[panel.value] || t('settings.title')
}

onMounted(() => {
  try {
    window?.Telegram?.WebApp?.expand?.()
  } catch {
    //
  }
  const n = normalizeLocale(uiLang.value)
  if (n !== uiLang.value) uiLang.value = n
  setAppLocale(n)
  document.documentElement.lang = n === 'en' ? 'en' : 'ru'
  confirmMap.value = { ...loadConfirmMap() }
  pinMap.value = { ...loadPinMap() }
  pinEnabled.value = loadPinEnabled()
  touchLoginHistory()
  const hadCache = hydrateSettingsFromCache()
  void loadMe({ background: hadCache })
  window.addEventListener('guard:me-refresh', onGuardMeRefresh)
})

watch(uiLang, (v) => {
  document.documentElement.lang = normalizeLocale(v) === 'en' ? 'en' : 'ru'
})

watch([pdfReportType, pdfScope, pdfPeriod, pdfChatId], () => {
  if (!showPdfModal.value) return
  schedulePdfRefresh()
})

watch(pdfScope, () => {
  if (pdfChatId.value && !pdfChatRows.value.find((x) => String(x.id) === String(pdfChatId.value))) {
    pdfChatId.value = ''
  }
})

watch(showPdfModal, (on) => {
  if (on) {
    void loadPdfChats()
    void refreshPdfPreview()
  } else {
    revokePdfObjectUrl()
    pdfPreview.value = null
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('guard:me-refresh', onGuardMeRefresh)
  revokePdfObjectUrl()
  if (pdfRefreshTimer) {
    clearTimeout(pdfRefreshTimer)
    pdfRefreshTimer = null
  }
  resetModalScrollLock()
})
</script>

<template>
  <div
    class="settings-root mx-auto max-w-lg space-y-4 pb-10 text-[15px] leading-snug tracking-[-0.01em] text-white antialiased"
  >
    <!-- Hub -->
    <template v-if="panel === 'hub'">
      <div class="px-0.5 pt-1">
        <h1 class="text-[28px] font-semibold tracking-[-0.03em] text-white">{{ t('settings.title') }}</h1>
      </div>

      <div
        v-if="!hasInitData"
        class="rounded-[22px] border border-amber-400/20 bg-amber-500/[0.08] px-4 py-3.5 text-[14px] text-amber-100/95 backdrop-blur-xl"
      >
        {{ t('app.init_required') }}
      </div>
      <template v-else>
        <div
          v-if="bootErr && !me"
          class="rounded-[22px] border border-rose-400/25 bg-rose-500/[0.1] px-4 py-3.5 text-[14px] text-rose-100 backdrop-blur-xl"
        >
          {{ bootErr }}
        </div>

        <div class="space-y-2">
        <button
          v-for="row in [
            { key: 'profile', title: t('settings.hub.profile.title'), sub: t('settings.hub.profile.sub'), icon: 'account' },
            { key: 'payment', title: t('settings.hub.payment.title'), sub: t('settings.hub.payment.sub'), icon: 'billing' },
            { key: 'data', title: t('settings.hub.data.title'), sub: t('settings.hub.data.sub'), icon: 'reports' },
            { key: 'botNotifications', title: t('settings.hub.notifications.title'), sub: t('settings.hub.notifications.sub'), icon: 'bell' },
            { key: 'delegation', title: t('settings.hub.delegation.title'), sub: t('settings.hub.delegation.sub'), icon: 'chats' },
            { key: 'security', title: t('settings.hub.security.title'), sub: t('settings.hub.security.sub'), icon: 'shield' },
          ]"
          :key="row.key"
          type="button"
          class="group flex w-full items-center gap-3.5 rounded-[22px] border border-white/[0.11] bg-white/[0.07] px-4 py-3.5 text-left shadow-[inset_0_1px_0_0_rgba(255,255,255,0.08),0_20px_50px_-28px_rgba(0,0,0,0.85)] backdrop-blur-2xl transition active:scale-[0.99] active:opacity-95"
          @click="panel = row.key"
        >
          <span
            class="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-white/[0.1] bg-white/[0.08] text-white/85 shadow-inner"
          >
            <NavIcon :name="row.icon" class="h-6 w-6" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block text-[16px] font-semibold text-white">{{ row.title }}</span>
            <span class="mt-0.5 block text-[13px] text-white/45">{{ row.sub }}</span>
          </span>
          <NavIcon name="chevron-right" class="h-5 w-5 shrink-0 text-white/25 group-hover:text-white/40" />
        </button>
        </div>
      </template>
    </template>

    <!-- Sub-screen shell -->
    <template v-else>
      <div class="flex items-start justify-between gap-3 px-0.5 pt-1">
        <h2 class="min-w-0 flex-1 text-[22px] font-semibold tracking-[-0.03em] text-white">
          {{ panelTitle() }}
        </h2>
        <button
          type="button"
          class="shrink-0 pt-1 text-[15px] font-medium text-white/45 transition hover:text-white/90"
          @click="back"
        >
          {{ t('common.back') }}
        </button>
      </div>

      <!-- Profile -->
      <div v-if="panel === 'profile'" class="space-y-3 pt-3">
        <div
          v-if="!me && loading"
          class="rounded-[22px] bg-white/[0.06] px-4 py-8 text-center text-[14px] text-white/55 backdrop-blur-2xl"
        >
          {{ t('common.loading') }}
        </div>
        <template v-else>
        <button
          type="button"
          class="flex w-full items-center gap-3.5 rounded-[22px] border border-white/[0.11] bg-white/[0.07] px-4 py-4 text-left shadow-[inset_0_1px_0_0_rgba(255,255,255,0.07)] backdrop-blur-2xl transition hover:bg-white/[0.09]"
          @click="
            botInfo?.username &&
              window.open(`https://t.me/${String(botInfo.username).replace(/^@/, '')}`, '_blank', 'noopener,noreferrer')
          "
        >
          <span
            class="flex h-[52px] w-[52px] shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#34d399] to-[#22d3ee] text-2xl shadow-[0_12px_32px_-12px_rgba(52,211,153,0.55)]"
          >
            🤖
          </span>
          <span class="min-w-0 flex-1">
            <span class="block text-[16px] font-semibold text-white">{{ botDisplayName }}</span>
            <span class="block text-[13px] text-white/45">{{ botHandle }}</span>
            <span class="mt-1 block text-[11px] text-white/35">{{ t('settings.profile.bot_caption') }}</span>
          </span>
          <NavIcon name="chevron-right" class="h-5 w-5 shrink-0 text-white/25" />
        </button>

        <div
          v-if="me"
          class="flex w-full items-center gap-3.5 rounded-[22px] border border-white/[0.11] bg-white/[0.07] px-4 py-4 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.07)] backdrop-blur-2xl"
        >
          <span
            class="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-white/[0.12] bg-white/[0.09] text-[18px] font-semibold text-cyan-200/95"
          >
            {{ String(me.first_name || me.username || '?').slice(0, 1).toUpperCase() }}
          </span>
          <span class="min-w-0 flex-1">
            <span class="block text-[16px] font-semibold text-white">{{ me.first_name || (t('common.locale_code') === 'en' ? 'Account' : 'Аккаунт') }}</span>
            <span class="block text-[13px] text-white/45">{{ me.username ? `@${me.username}` : t('settings.profile.username_hidden') }}</span>
            <span class="mt-0.5 block text-[11px] font-mono text-white/35">{{ t('settings.profile.id_label', { id: me.telegram_id }) }}</span>
          </span>
        </div>

        <div
          class="rounded-[22px] border border-violet-400/20 bg-gradient-to-br from-violet-500/[0.14] via-indigo-500/[0.08] to-transparent p-4 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.08)] backdrop-blur-2xl"
        >
          <div class="flex items-start gap-3">
            <span class="text-2xl opacity-95">👑</span>
            <div class="min-w-0 flex-1">
              <p class="text-[11px] font-medium uppercase tracking-[0.12em] text-violet-200/65">{{ t('settings.profile.tariff_label') }}</p>
              <p class="mt-1 text-[18px] font-semibold text-white">{{ isPremium ? t('billing.premium') : t('billing.free') }}</p>
              <div class="mt-2 flex flex-wrap items-center gap-2">
                <span
                  class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold"
                  :class="isPremium ? 'border-emerald-400/35 bg-emerald-400/15 text-emerald-100' : 'border-white/15 bg-white/[0.06] text-white/55'"
                >
                  <span class="h-1.5 w-1.5 rounded-full" :class="isPremium ? 'bg-emerald-300' : 'bg-white/35'" />
                  {{ isPremium ? t('settings.profile.tariff_active') : t('settings.profile.tariff_inactive') }}
                </span>
                <span v-if="isPremium" class="text-[13px] text-white/70">{{ t('settings.profile.tariff_until', { date: subscriptionUntilShort }) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="overflow-hidden rounded-[22px] border border-white/[0.11] bg-white/[0.06] shadow-[inset_0_1px_0_0_rgba(255,255,255,0.07)] backdrop-blur-2xl">
          <button
            type="button"
            class="flex w-full items-center justify-between gap-3 px-4 py-3.5 text-left transition hover:bg-white/[0.04]"
            @click="panel = 'languagePick'"
          >
            <span class="text-[15px] font-medium text-white">{{ t('settings.language.title') }}</span>
            <span class="flex items-center gap-1 text-[14px] text-white/45">
              {{ langLabel }}
              <NavIcon name="chevron-right" class="h-4 w-4 text-white/25" />
            </span>
          </button>
          <div class="mx-4 h-px bg-white/[0.08]" />
          <div class="flex items-center justify-between gap-3 px-4 py-3.5">
            <div>
              <p class="text-[15px] font-medium text-white">{{ t('settings.language.auto') }}</p>
              <p class="mt-0.5 text-[12px] text-white/35">{{ t('settings.language.auto_hint') }}</p>
            </div>
            <button
              type="button"
              role="switch"
              :aria-checked="langAuto"
              class="relative h-[31px] w-[51px] shrink-0 rounded-full border transition duration-200"
              :class="iosSwitchClass(langAuto)"
              @click="langAuto = !langAuto"
            >
              <span
                class="absolute left-[3px] top-1/2 h-[25px] w-[25px] rounded-full bg-white shadow-md transition duration-200"
                :style="{ transform: langAuto ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }"
              />
            </button>
          </div>
        </div>
        </template>
      </div>

      <!-- Payment -->
      <div v-if="panel === 'payment'" class="space-y-3 pt-3">
        <SubscriptionManagementPanel
          v-if="me"
          :profile="me"
          variant="embedded"
          @update:profile="onSettingsSubscriptionProfileUpdate"
          @open-tariff="goBilling"
        />
        <div
          v-else
          class="rounded-[22px] border border-white/[0.11] bg-white/[0.06] px-4 py-8 text-center text-[14px] text-white/55 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.07)] backdrop-blur-2xl"
        >
          {{ t('common.locale_code') === 'en' ? 'Loading subscription…' : 'Загружаем подписку…' }}
        </div>
      </div>

      <!-- Data -->
      <div v-if="panel === 'data'" class="space-y-3 pt-3">
        <p class="px-1 text-[12px] font-medium uppercase tracking-[0.14em] text-white/35">{{ t('settings.data.export_header') }}</p>
        <button
          type="button"
          class="flex w-full items-center gap-3.5 rounded-[22px] border border-transparent bg-white/[0.07] px-4 py-4 text-left shadow-[inset_0_1px_0_0_rgba(255,255,255,0.06)] backdrop-blur-2xl disabled:opacity-45"
          :disabled="pdfBusy || !me"
          @click="exportPdf"
        >
          <span class="text-2xl">📕</span>
          <span class="min-w-0 flex-1">
            <span class="block text-[16px] font-semibold text-white">{{ t('settings.data.export_pdf_title') }}</span>
            <span class="mt-0.5 block text-[13px] text-white/45">{{ t('settings.data.export_pdf_sub') }}</span>
          </span>
          <NavIcon name="chevron-right" class="h-5 w-5 shrink-0 text-white/25" />
        </button>

        <p class="px-1 pt-1 text-[12px] font-medium uppercase tracking-[0.14em] text-white/35">{{ t('settings.data.retention_header') }}</p>
        <div class="overflow-hidden rounded-[22px] border border-white/[0.11] bg-white/[0.06] backdrop-blur-2xl">
          <button
            type="button"
            class="flex w-full items-center justify-between gap-3 px-4 py-3.5 text-left transition hover:bg-white/[0.04]"
            @click="panel = 'retentionPick'"
          >
            <span class="text-[15px] font-medium text-white">{{ t('settings.data.retention_title') }}</span>
            <span class="flex items-center gap-1 text-[14px] text-white/45">
              {{ retentionLabel }}
              <NavIcon name="chevron-right" class="h-4 w-4 text-white/25" />
            </span>
          </button>
          <div class="border-t border-white/[0.08] px-4 py-3.5">
            <p class="text-[13px] font-medium text-white/65">{{ t('settings.data.retention_what_stored') }}</p>
            <ul class="mt-2 space-y-2 text-[14px] leading-relaxed text-white/45">
              <li class="flex gap-2.5"><span class="text-emerald-400/90">·</span> {{ t('settings.data.retention_item_messages') }}</li>
              <li class="flex gap-2.5"><span class="text-emerald-400/90">·</span> {{ t('settings.data.retention_item_moderation') }}</li>
              <li class="flex gap-2.5"><span class="text-emerald-400/90">·</span> {{ t('settings.data.retention_item_growth') }}</li>
            </ul>
          </div>
        </div>

        <p class="px-1 pt-1 text-[12px] font-medium uppercase tracking-[0.14em] text-white/35">{{ t('settings.data.purge_header') }}</p>
        <button
          type="button"
          class="w-full rounded-[22px] border border-rose-400/30 bg-rose-500/[0.1] px-4 py-4 text-left shadow-[inset_0_1px_0_0_rgba(255,255,255,0.06)] backdrop-blur-xl transition hover:bg-rose-500/[0.14] disabled:opacity-45"
          :disabled="purgeLoading"
          @click="startPurge"
        >
          <p class="text-[16px] font-semibold text-rose-100">{{ t('settings.data.purge_title') }}</p>
          <p class="mt-1 text-[13px] text-rose-200/65">{{ t('settings.data.purge_sub') }}</p>
        </button>
        <div
          class="rounded-2xl bg-rose-500/[0.08] px-3.5 py-2.5 text-[12px] leading-relaxed text-rose-100/85 backdrop-blur-lg"
        >
          {{ t('settings.data.purge_disclaimer') }}
        </div>

        <div
          v-if="showPurgeConfirm"
          style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center bg-black/55 p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] backdrop-blur-md sm:items-center"
          role="dialog"
          aria-modal="true"
          @click.self="showPurgeConfirm = false"
          @touchmove.prevent
        >
          <div
            class="w-full max-w-md overflow-hidden rounded-[24px] border border-white/[0.14] bg-[#1c1c1e]/95 p-5 shadow-2xl backdrop-blur-2xl"
          >
            <p class="text-[17px] font-semibold text-white">{{ t('settings.data.purge_confirm_title') }}</p>
            <p class="mt-2 text-[14px] leading-relaxed text-white/45">
              {{ t('settings.data.purge_confirm_body') }}
            </p>
            <div class="mt-5 flex gap-2.5">
              <button
                type="button"
                class="flex-1 rounded-2xl border border-white/[0.14] bg-white/[0.06] py-3 text-[15px] font-medium text-white transition hover:bg-white/[0.1]"
                @click="showPurgeConfirm = false"
              >
                {{ t('common.cancel') }}
              </button>
              <button
                type="button"
                class="flex-1 rounded-2xl border border-rose-400/35 bg-rose-500 py-3 text-[15px] font-semibold text-white shadow-lg disabled:opacity-50"
                :disabled="purgeLoading"
                @click="runPurge"
              >
                {{ purgeLoading ? (t('common.locale_code') === 'en' ? 'Deleting…' : 'Удаление…') : t('settings.data.purge_button') }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Bot notifications (hub) -->
      <div v-if="panel === 'botNotifications'" class="space-y-3 pt-3">
        <p class="px-1 text-[14px] leading-relaxed text-white/50">{{ t('settings.notifications.intro') }}</p>
        <button
          type="button"
          class="group flex w-full items-center gap-3.5 rounded-[22px] border border-white/[0.11] bg-white/[0.07] px-4 py-3.5 text-left shadow-[inset_0_1px_0_0_rgba(255,255,255,0.08),0_20px_50px_-28px_rgba(0,0,0,0.85)] backdrop-blur-2xl transition active:scale-[0.99] hover:bg-white/[0.09]"
          @click="panel = 'joinReportSettings'"
        >
          <span
            class="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-white/[0.1] bg-white/[0.08] text-white/85 shadow-inner"
          >
            <NavIcon name="reports" class="h-6 w-6" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block text-[16px] font-semibold text-white">{{ t('settings.notifications.short_reports_title') }}</span>
            <span class="mt-0.5 block text-[13px] text-white/45">{{ t('settings.notifications.short_reports_sub') }}</span>
          </span>
          <NavIcon name="chevron-right" class="h-5 w-5 shrink-0 text-white/25 group-hover:text-white/40" />
        </button>
      </div>

      <!-- Short reports schedule -->
      <div v-if="panel === 'joinReportSettings'" class="space-y-4 pt-3">
        <p class="px-1 text-[14px] leading-relaxed text-white/55">
          {{ t('dashboard.stats_strip.join_report_hint') }}
        </p>
        <div v-if="joinReportLoading" class="rounded-[22px] bg-white/[0.06] px-4 py-10 text-center text-[14px] text-white/40 backdrop-blur-xl">
          {{ t('common.loading') }}
        </div>
        <div v-else class="overflow-hidden rounded-[22px] border border-white/[0.11] bg-white/[0.06] shadow-[inset_0_1px_0_0_rgba(255,255,255,0.07)] backdrop-blur-2xl">
          <div
            v-for="(opt, oi) in joinReportPresetOptions"
            :key="opt.id"
            class="flex items-center justify-between gap-3 px-4 py-3.5"
            :class="oi > 0 ? 'border-t border-white/[0.08]' : ''"
          >
            <span class="text-[15px] font-medium text-white">{{ opt.label }}</span>
            <button
              type="button"
              role="switch"
              :aria-checked="joinReportEnabled(opt.id)"
              :disabled="joinReportSaving"
              class="relative h-[31px] w-[51px] shrink-0 rounded-full border transition duration-200 disabled:opacity-45"
              :class="iosSwitchClass(joinReportEnabled(opt.id))"
              @click="toggleJoinReportPreset(opt.id)"
            >
              <span
                class="absolute left-[3px] top-1/2 h-[25px] w-[25px] rounded-full bg-white shadow-md transition duration-200"
                :style="{
                  transform: joinReportEnabled(opt.id) ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)',
                }"
              />
            </button>
          </div>
        </div>
      </div>

      <!-- Delegation -->
      <div v-if="panel === 'delegation'" class="space-y-3 pt-3">
        <div class="rounded-[22px] border border-cyan-400/18 bg-white/[0.06] p-4 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.07)] backdrop-blur-2xl">
          <div class="flex items-start justify-between gap-3">
            <div>
              <p class="text-[16px] font-semibold text-white">{{ t('settings.delegation.title') }}</p>
              <p class="mt-1 text-[13px] leading-relaxed text-white/45">
                {{ t('settings.delegation.desc') }}
              </p>
            </div>
            <button
              type="button"
              role="switch"
              :aria-checked="delegationEnabled"
              class="relative mt-0.5 h-[31px] w-[51px] shrink-0 rounded-full border transition duration-200"
              :class="iosSwitchClass(delegationEnabled)"
              @click="delegationEnabled = !delegationEnabled"
            >
              <span
                class="absolute left-[3px] top-1/2 h-[25px] w-[25px] rounded-full bg-white shadow-md transition duration-200"
                :style="{ transform: delegationEnabled ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }"
              />
            </button>
          </div>
        </div>

        <button
          type="button"
          class="flex w-full items-center justify-between gap-3 rounded-[22px] border border-white/[0.11] bg-white/[0.07] px-4 py-3.5 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.07)] backdrop-blur-2xl transition hover:bg-white/[0.09]"
          @click="goChats"
        >
          <span class="text-[15px] font-medium text-white">{{ t('settings.delegation.connected_chats') }}</span>
          <NavIcon name="chevron-right" class="h-5 w-5 text-white/25" />
        </button>

        <div v-if="delegationLoading" class="py-12 text-center text-[14px] text-white/35">{{ t('common.loading') }}</div>
        <div
          v-else-if="!delegationEnabled"
          class="rounded-[22px] border border-white/[0.08] bg-white/[0.04] px-4 py-10 text-center text-[14px] text-white/40 backdrop-blur-xl"
        >
          {{ t('settings.delegation.disabled') }}
        </div>
        <div v-else class="space-y-2">
          <p class="px-1 text-[12px] font-medium uppercase tracking-[0.14em] text-white/35">{{ t('settings.delegation.list_header') }}</p>
          <button
            v-for="(row, idx) in delegationRows"
            :key="`d-${row.chatId}-${row.managerId}-${idx}`"
            type="button"
            class="flex w-full items-center gap-3 rounded-[22px] border border-white/[0.1] bg-white/[0.06] px-3.5 py-3 text-left shadow-[inset_0_1px_0_0_rgba(255,255,255,0.06)] backdrop-blur-xl transition hover:bg-white/[0.08]"
            @click="goChats"
          >
            <span
              class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-white/[0.1] bg-white/[0.06] text-lg"
            >
              💬
            </span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-[15px] font-semibold text-white">{{ row.chatTitle }}</span>
              <span class="block truncate text-[13px] text-white/45">{{ row.chatUsername || row.managerUsername }}</span>
              <span
                class="mt-1 inline-block rounded-lg border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide"
                :class="(row.role === t('settings.delegation.role_admin')) ? 'border-emerald-400/35 text-emerald-200' : 'border-sky-400/35 text-sky-200'"
              >
                {{ row.role }}
              </span>
            </span>
            <NavIcon name="chevron-right" class="h-5 w-5 shrink-0 text-white/25" />
          </button>
          <div
            v-if="!delegationRows.length"
            class="rounded-[22px] border border-dashed border-white/15 bg-white/[0.03] px-4 py-10 text-center text-[14px] text-white/40"
          >
            {{ t('settings.delegation.empty') }}
          </div>
        </div>

        <button
          type="button"
          class="w-full rounded-[22px] border border-emerald-400/35 bg-emerald-500/[0.16] py-3.5 text-[15px] font-semibold text-emerald-50 shadow-[0_18px_44px_-24px_rgba(52,211,153,0.7)] backdrop-blur-xl transition hover:bg-emerald-500/[0.24] disabled:opacity-40"
          :disabled="!delegationEnabled"
          @click="goChats"
        >
          {{ t('settings.delegation.add') }}
        </button>
      </div>

      <!-- Security -->
      <div v-if="panel === 'security'" class="space-y-3 pt-3">
        <div class="rounded-[22px] border border-white/[0.11] bg-white/[0.06] p-4 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.07)] backdrop-blur-2xl">
          <p class="text-[14px] font-medium text-white/65">{{ t('settings.security.sessions_label') }}</p>
          <p class="mt-1 text-[13px] text-white/40">{{ t('settings.security.sessions_count', { count: sessions.length }) }}</p>
          <div class="mt-3 space-y-2">
            <div
              v-for="s in sessions"
              :key="s.id"
              class="flex items-center gap-2 rounded-2xl border border-white/[0.08] bg-black/20 px-3 py-2.5 backdrop-blur-md"
            >
              <div class="min-w-0 flex-1">
                <p class="truncate text-[14px] font-medium text-white">
                  {{ s.label }}
                  <span v-if="s.current" class="ml-1 text-[12px] font-normal text-emerald-300/95">{{ t('settings.security.session_current') }}</span>
                </p>
                <p class="text-[11px] text-white/35">{{ t('settings.security.session_last_seen', { when: formatDateTimeShortRu(s.lastSeen) }) }}</p>
              </div>
              <button
                type="button"
                class="shrink-0 text-[22px] leading-none text-white/55 transition hover:text-white"
                :aria-label="t('settings.security.terminate_session')"
                :title="t('settings.security.terminate_session')"
                @click="terminateSession(s.id)"
              >
                ×
              </button>
            </div>
          </div>
          <button
            type="button"
            class="mt-4 w-full rounded-2xl border border-rose-400/35 bg-rose-500/[0.12] py-3 text-[14px] font-semibold text-rose-100 transition hover:bg-rose-500/[0.18]"
            @click="terminateOtherSessions"
          >
            {{ t('settings.security.terminate_all') }}
          </button>
        </div>

        <div class="overflow-hidden rounded-[22px] border border-white/[0.11] bg-white/[0.06] shadow-[inset_0_1px_0_0_rgba(255,255,255,0.07)] backdrop-blur-2xl">
          <div class="flex items-center justify-between gap-3 px-4 py-3.5">
            <div>
              <p class="text-[15px] font-medium text-white">{{ t('settings.security.confirm.title') }}</p>
              <p class="mt-0.5 text-[12px] text-white/35">{{ t('settings.security.confirm.sub') }}</p>
            </div>
            <button
              type="button"
              role="switch"
              :aria-checked="confirmMaster"
              class="relative h-[31px] w-[51px] shrink-0 rounded-full border transition duration-200"
              :class="iosSwitchClass(confirmMaster)"
              @click="confirmMaster = !confirmMaster"
            >
              <span
                class="absolute left-[3px] top-1/2 h-[25px] w-[25px] rounded-full bg-white shadow-md transition duration-200"
                :style="{ transform: confirmMaster ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }"
              />
            </button>
          </div>
          <button
            type="button"
            class="flex w-full items-center justify-between border-t border-white/[0.08] px-4 py-3.5 text-left transition hover:bg-white/[0.04] disabled:opacity-40"
            :disabled="!confirmMaster"
            @click="panel = 'confirmActionsDetail'"
          >
            <span class="text-[14px] text-white/80">{{ t('settings.security.confirm.detail_title') }}</span>
            <NavIcon name="chevron-right" class="h-5 w-5 text-white/25" />
          </button>
        </div>

        <div class="overflow-hidden rounded-[22px] border border-white/[0.11] bg-white/[0.06] shadow-[inset_0_1px_0_0_rgba(255,255,255,0.07)] backdrop-blur-2xl">
          <div class="flex items-center justify-between gap-3 px-4 py-3.5">
            <div>
              <p class="text-[15px] font-medium text-white">{{ t('settings.security.pin.title') }}</p>
              <p class="mt-0.5 text-[12px] text-white/35">{{ t('settings.security.pin.sub') }}</p>
            </div>
            <button
              type="button"
              role="switch"
              :aria-checked="pinEnabled && pinIsSet"
              class="relative h-[31px] w-[51px] shrink-0 rounded-full border transition duration-200"
              :class="iosSwitchClass(pinEnabled && pinIsSet)"
              @click="onPinMasterClick"
            >
              <span
                class="absolute left-[3px] top-1/2 h-[25px] w-[25px] rounded-full bg-white shadow-md transition duration-200"
                :style="{ transform: pinEnabled && pinIsSet ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }"
              />
            </button>
          </div>
          <button
            type="button"
            class="flex w-full items-center justify-between border-t border-white/[0.08] px-4 py-3.5 text-left transition hover:bg-white/[0.04] disabled:opacity-40"
            :disabled="!pinEnabled || !pinIsSet"
            @click="panel = 'pinActions'"
          >
            <span class="text-[14px] text-white/80">{{ t('settings.security.pin.ask') }}</span>
            <NavIcon name="chevron-right" class="h-5 w-5 text-white/25" />
          </button>
          <button
            type="button"
            class="flex w-full items-center justify-between border-t border-white/[0.08] px-4 py-3.5 text-left transition hover:bg-white/[0.04]"
            @click="
              pinNew = '';
              pinNew2 = '';
              panel = 'pinSetup'
            "
          >
            <span class="text-[14px] text-white/80">{{ pinIsSet ? t('settings.security.pin.change') : t('settings.security.pin.set') }}</span>
            <NavIcon name="chevron-right" class="h-5 w-5 text-white/25" />
          </button>
        </div>

        <button
          type="button"
          class="flex w-full items-center justify-between gap-3 rounded-[22px] border border-white/[0.11] bg-white/[0.06] px-4 py-3.5 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.07)] backdrop-blur-2xl transition hover:bg-white/[0.08]"
          @click="panel = 'loginHistory'"
        >
          <span class="text-[15px] font-medium text-white">{{ t('settings.security.login_history') }}</span>
          <NavIcon name="chevron-right" class="h-5 w-5 text-white/25" />
        </button>
      </div>

      <!-- Confirm detail -->
      <div v-if="panel === 'confirmActionsDetail'" class="space-y-0 pt-3">
        <p class="mb-2 px-1 text-[12px] text-white/35">{{ t('settings.security.confirm.detail_hint') }}</p>
        <div class="overflow-hidden rounded-[22px] border border-white/[0.11] bg-white/[0.06] backdrop-blur-2xl">
          <div
            v-for="(act, i) in GUARD_SECURITY_ACTIONS"
            :key="act.id"
            class="flex items-center justify-between gap-3 px-4 py-3.5"
            :class="i > 0 ? 'border-t border-white/[0.08]' : ''"
          >
            <span class="text-[14px] text-white/85">{{ act.label }}</span>
            <button
              type="button"
              class="relative h-[31px] w-[51px] shrink-0 rounded-full border transition duration-200"
              :class="iosSwitchClass(!!confirmMap[act.id])"
              @click="toggleConfirmFor(act.id)"
            >
              <span
                class="absolute left-[3px] top-1/2 h-[25px] w-[25px] rounded-full bg-white shadow-md transition duration-200"
                :style="{ transform: confirmMap[act.id] ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }"
              />
            </button>
          </div>
        </div>
      </div>

      <!-- PIN actions -->
      <div v-if="panel === 'pinActions'" class="space-y-0 pt-3">
        <p class="mb-2 px-1 text-[12px] text-white/35">{{ t('settings.security.pin.ask_hint') }}</p>
        <div class="overflow-hidden rounded-[22px] border border-white/[0.11] bg-white/[0.06] backdrop-blur-2xl">
          <div
            v-for="(act, i) in GUARD_SECURITY_ACTIONS"
            :key="act.id"
            class="flex items-center justify-between gap-3 px-4 py-3.5"
            :class="i > 0 ? 'border-t border-white/[0.08]' : ''"
          >
            <span class="text-[14px] text-white/85">{{ act.label }}</span>
            <button
              type="button"
              class="relative h-[31px] w-[51px] shrink-0 rounded-full border transition duration-200"
              :class="iosSwitchClass(!!pinMap[act.id])"
              @click="togglePinFor(act.id)"
            >
              <span
                class="absolute left-[3px] top-1/2 h-[25px] w-[25px] rounded-full bg-white shadow-md transition duration-200"
                :style="{ transform: pinMap[act.id] ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }"
              />
            </button>
          </div>
        </div>
      </div>

      <!-- PIN setup -->
      <div v-if="panel === 'pinSetup'" class="space-y-4 pt-3">
        <p class="text-[14px] leading-relaxed text-white/45">
          {{ t('settings.security.pin.new_hint') }}
        </p>
        <div class="space-y-3 rounded-[22px] border border-white/[0.11] bg-white/[0.06] p-4 backdrop-blur-2xl">
          <label class="block text-[12px] font-medium text-white/45">{{ t('settings.security.pin.new_label') }}</label>
          <input
            v-model="pinNew"
            type="password"
            inputmode="numeric"
            maxlength="4"
            autocomplete="off"
            class="w-full rounded-2xl border border-white/[0.12] bg-black/30 px-4 py-3.5 text-center text-[22px] font-semibold tracking-[0.4em] text-white outline-none ring-0 focus:border-emerald-400/40"
            placeholder="••••"
          />
          <label class="block text-[12px] font-medium text-white/45">{{ t('settings.security.pin.new_repeat') }}</label>
          <input
            v-model="pinNew2"
            type="password"
            inputmode="numeric"
            maxlength="4"
            autocomplete="off"
            class="w-full rounded-2xl border border-white/[0.12] bg-black/30 px-4 py-3.5 text-center text-[22px] font-semibold tracking-[0.4em] text-white outline-none focus:border-emerald-400/40"
            placeholder="••••"
          />
        </div>
        <button
          type="button"
          class="w-full rounded-[22px] border border-emerald-400/35 bg-emerald-500/[0.2] py-3.5 text-[15px] font-semibold text-emerald-50 shadow-lg disabled:opacity-50"
          :disabled="pinBusy"
          @click="saveNewPin"
        >
          {{ t('common.locale_code') === 'en' ? 'Save code' : 'Сохранить код' }}
        </button>
      </div>

      <!-- Language picker -->
      <div v-if="panel === 'languagePick'" class="space-y-2 pt-3">
        <p class="px-1 text-[12px] leading-relaxed text-white/35">
          {{ t('settings.language.hint') }}
        </p>
        <button
          v-for="l in langs"
          :key="l.code"
          type="button"
          class="flex w-full items-center justify-between rounded-[22px] border px-4 py-3.5 text-left transition"
          :class="uiLang === l.code ? 'border-emerald-400/35 bg-emerald-500/[0.12]' : 'border-white/[0.11] bg-white/[0.06]'"
          @click="chooseLanguage(l.code)"
        >
          <span class="text-[16px] font-medium text-white">{{ l.label }}</span>
          <span v-if="uiLang === l.code" class="text-emerald-300">✓</span>
        </button>
      </div>

      <!-- Retention picker -->
      <div v-if="panel === 'retentionPick'" class="space-y-2 pt-3">
        <button
          v-for="o in retentionOptions"
          :key="o.months"
          type="button"
          class="flex w-full items-center justify-between rounded-[22px] border px-4 py-3.5 text-left transition"
          :class="retentionMonths === o.months ? 'border-cyan-400/35 bg-cyan-500/[0.12]' : 'border-white/[0.11] bg-white/[0.06]'"
          @click="
            retentionMonths = o.months;
            panel = 'data'
          "
        >
          <span class="text-[16px] font-medium text-white">{{ o.label }}</span>
          <span v-if="retentionMonths === o.months" class="text-cyan-300">✓</span>
        </button>
        <p class="px-1 text-[12px] leading-relaxed text-white/35">
          {{ t('common.locale_code') === 'en' ? 'Shown in app and PDF; server-side policy may differ.' : 'Отображается в приложении и в PDF; серверная политика может отличаться.' }}
        </p>
      </div>

      <!-- Login history -->
      <div v-if="panel === 'loginHistory'" class="space-y-2 pt-3">
        <div
          v-if="!loginHistory.length"
          class="rounded-[22px] border border-white/[0.1] px-4 py-12 text-center text-[14px] text-white/35"
        >
          {{ t('settings.security.login_history_empty') }}
        </div>
        <div
          v-for="(h, i) in loginHistory"
          :key="i"
          class="rounded-[22px] border border-white/[0.1] bg-white/[0.05] px-4 py-3 backdrop-blur-xl"
        >
          <p class="text-[14px] font-medium text-white">{{ h.label }}</p>
          <p class="text-[12px] text-white/35">{{ formatDateTimeShortRu(h.at) }}</p>
        </div>
      </div>
    </template>

    <!-- PDF modal -->
    <div
      v-if="showPdfModal"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-center justify-center bg-black/70 p-4 backdrop-blur-2xl"
      role="dialog"
      aria-modal="true"
      @click.self="showPdfModal = false"
      @touchmove.prevent
    >
      <div
        class="flex max-h-[92vh] w-full max-w-md flex-col overflow-hidden rounded-[26px] bg-[#15171a]/96 shadow-[0_30px_60px_-20px_rgba(0,0,0,0.7)]"
      >
        <div class="flex items-start justify-between gap-3 px-4 pb-2 pt-4">
          <div class="min-w-0">
            <p class="text-[17px] font-semibold text-white">{{ t('settings.pdf.modal_title') }}</p>
            <p class="mt-0.5 truncate text-[12px] text-white/50">
              {{ pdfReportType === 'growth' ? t('settings.pdf.report_growth_full') : t('settings.pdf.report_protection_full') }}
            </p>
          </div>
          <button
            type="button"
            class="-mr-1 -mt-1 grid h-9 w-9 place-items-center rounded-full bg-white/[0.07] text-[20px] leading-none text-white/65 transition active:scale-95"
            :aria-label="t('common.close')"
            @click="showPdfModal = false"
          >
            ×
          </button>
        </div>

        <div class="px-4">
          <div class="grid grid-cols-2 gap-1.5 rounded-2xl bg-white/[0.05] p-1">
            <button
              type="button"
              class="rounded-xl px-3 py-2 text-[12.5px] font-semibold transition"
              :class="pdfReportType === 'protection' ? 'bg-[rgba(125,255,58,0.18)] text-[#e2ffc4] shadow-[0_0_18px_-6px_rgba(125,255,58,0.55)]' : 'text-white/65'"
              @click="pdfReportType = 'protection'"
            >
              {{ t('settings.pdf.report_protection') }}
            </button>
            <button
              type="button"
              class="rounded-xl px-3 py-2 text-[12.5px] font-semibold transition"
              :class="pdfReportType === 'growth' ? 'bg-[rgba(125,255,58,0.18)] text-[#e2ffc4] shadow-[0_0_18px_-6px_rgba(125,255,58,0.55)]' : 'text-white/65'"
              @click="pdfReportType = 'growth'"
            >
              {{ t('settings.pdf.report_growth') }}
            </button>
          </div>

          <div class="mt-2 grid grid-cols-3 gap-2">
            <div class="relative">
              <select
                v-model="pdfPeriod"
                class="w-full appearance-none rounded-xl bg-white/[0.06] px-3 py-2 pr-7 text-[12.5px] text-white outline-none"
              >
                <option v-for="o in PDF_PERIOD_OPTIONS" :key="o.key" :value="o.key">{{ o.label }}</option>
              </select>
              <span class="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-white/45">▾</span>
            </div>
            <div class="relative">
              <select
                v-model="pdfScope"
                class="w-full appearance-none rounded-xl bg-white/[0.06] px-3 py-2 pr-7 text-[12.5px] text-white outline-none"
              >
                <option value="all">{{ t('settings.pdf.filter_all') }}</option>
                <option value="own">{{ t('settings.pdf.filter_own') }}</option>
                <option value="delegated">{{ t('settings.pdf.filter_delegated') }}</option>
              </select>
              <span class="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-white/45">▾</span>
            </div>
            <div class="relative">
              <select
                v-model="pdfChatId"
                class="w-full appearance-none rounded-xl bg-white/[0.06] px-3 py-2 pr-7 text-[12.5px] text-white outline-none"
              >
                <option value="">{{ t('settings.pdf.filter_all_chats') }}</option>
                <option v-for="c in pdfChatRows" :key="c.id" :value="String(c.id)">
                  {{ c.title || c.id }}
                </option>
              </select>
              <span class="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-white/45">▾</span>
            </div>
          </div>
        </div>

        <div class="mx-4 mt-3 flex-1 overflow-hidden rounded-2xl bg-[#0f1216]">
          <div
            v-if="pdfPreviewLoading"
            class="flex h-full min-h-[280px] items-center justify-center text-[13px] text-white/45"
          >
            <span class="inline-flex items-center gap-2">
              <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-white/40" />
              {{ t('settings.pdf.preparing') }}
            </span>
          </div>
          <div
            v-else-if="pdfPreview"
            class="max-h-[58vh] overflow-y-auto p-3"
          >
            <!-- HTML‑превью «страницы PDF» -->
            <article class="mx-auto w-full max-w-[640px] rounded-[10px] bg-white text-slate-900 shadow-[0_30px_70px_-30px_rgba(0,0,0,0.55)]">
              <header class="border-b border-slate-200 px-6 pb-4 pt-5">
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#3a9a16]">
                      GUARD
                    </p>
                    <h1 class="mt-1 text-[18px] font-semibold leading-tight">
                      {{ pdfReportType === 'growth' ? t('settings.pdf.report_growth') : (t('common.locale_code') === 'en' ? 'Protection stats' : 'Статистика защиты') }}
                    </h1>
                  </div>
                  <p class="shrink-0 text-right text-[10px] text-slate-500">
                    {{ t('settings.pdf.generated_at') }}<br />{{ previewGeneratedAt }}
                  </p>
                </div>
                <p class="mt-2 text-[11px] text-slate-500">
                  {{ t('settings.pdf.period_label') }} <b class="text-slate-800">{{ previewPeriodLabel }}</b> · {{ t('settings.pdf.scope_label') }}
                  <b class="text-slate-800">{{ previewScopeLabel }}</b> · {{ t('settings.pdf.source_label') }}
                  <b class="text-slate-800">{{ pdfPreview.chat_title }}</b>
                </p>
              </header>

              <section class="grid grid-cols-3 gap-2 px-6 pt-4">
                <template v-if="pdfReportType === 'protection'">
                  <div class="rounded-lg bg-[#f4faef] px-3 py-2">
                    <p class="text-[9.5px] uppercase tracking-wider text-slate-500">{{ t('settings.pdf.metrics.deleted') }}</p>
                    <p class="mt-0.5 text-[17px] font-semibold text-slate-900">{{ pdfPreview.deleted.toLocaleString('ru-RU') }}</p>
                  </div>
                  <div class="rounded-lg bg-[#f4faef] px-3 py-2">
                    <p class="text-[9.5px] uppercase tracking-wider text-slate-500">{{ t('settings.pdf.metrics.messages') }}</p>
                    <p class="mt-0.5 text-[17px] font-semibold text-slate-900">{{ pdfPreview.messages.toLocaleString('ru-RU') }}</p>
                  </div>
                  <div class="rounded-lg bg-[#f4faef] px-3 py-2">
                    <p class="text-[9.5px] uppercase tracking-wider text-slate-500">{{ t('settings.pdf.metrics.active') }}</p>
                    <p class="mt-0.5 text-[17px] font-semibold text-slate-900">{{ pdfPreview.active_users.toLocaleString('ru-RU') }}</p>
                  </div>
                  <div class="rounded-lg bg-[#f4faef] px-3 py-2">
                    <p class="text-[9.5px] uppercase tracking-wider text-slate-500">{{ t('settings.pdf.metrics.joined') }}</p>
                    <p class="mt-0.5 text-[17px] font-semibold text-slate-900">{{ pdfPreview.joined.toLocaleString('ru-RU') }}</p>
                  </div>
                  <div class="rounded-lg bg-[#f4faef] px-3 py-2">
                    <p class="text-[9.5px] uppercase tracking-wider text-slate-500">{{ t('settings.pdf.metrics.left') }}</p>
                    <p class="mt-0.5 text-[17px] font-semibold text-slate-900">{{ pdfPreview.left.toLocaleString('ru-RU') }}</p>
                  </div>
                  <div class="rounded-lg bg-[#f4faef] px-3 py-2">
                    <p class="text-[9.5px] uppercase tracking-wider text-slate-500">{{ t('settings.pdf.metrics.chats') }}</p>
                    <p class="mt-0.5 text-[17px] font-semibold text-slate-900">{{ pdfPreview.chats_total.toLocaleString('ru-RU') }}</p>
                  </div>
                </template>
                <template v-else>
                  <div class="rounded-lg bg-[#f4faef] px-3 py-2">
                    <p class="text-[9.5px] uppercase tracking-wider text-slate-500">{{ t('settings.pdf.metrics.joined') }}</p>
                    <p class="mt-0.5 text-[17px] font-semibold text-slate-900">{{ pdfPreview.joined.toLocaleString('ru-RU') }}</p>
                  </div>
                  <div class="rounded-lg bg-[#f4faef] px-3 py-2">
                    <p class="text-[9.5px] uppercase tracking-wider text-slate-500">{{ t('settings.pdf.metrics.left') }}</p>
                    <p class="mt-0.5 text-[17px] font-semibold text-slate-900">{{ pdfPreview.left.toLocaleString('ru-RU') }}</p>
                  </div>
                  <div class="rounded-lg bg-[#f4faef] px-3 py-2">
                    <p class="text-[9.5px] uppercase tracking-wider text-slate-500">{{ t('settings.pdf.metrics.growth_net') }}</p>
                    <p
                      class="mt-0.5 text-[17px] font-semibold"
                      :class="pdfPreview.growth_net >= 0 ? 'text-[#2e7a16]' : 'text-rose-600'"
                    >
                      {{ pdfPreview.growth_net >= 0 ? '+' : '' }}{{ pdfPreview.growth_net.toLocaleString('ru-RU') }}
                    </p>
                  </div>
                  <div class="rounded-lg bg-[#f4faef] px-3 py-2">
                    <p class="text-[9.5px] uppercase tracking-wider text-slate-500">{{ t('settings.pdf.metrics.messages') }}</p>
                    <p class="mt-0.5 text-[17px] font-semibold text-slate-900">{{ pdfPreview.messages.toLocaleString('ru-RU') }}</p>
                  </div>
                  <div class="rounded-lg bg-[#f4faef] px-3 py-2">
                    <p class="text-[9.5px] uppercase tracking-wider text-slate-500">{{ t('settings.pdf.metrics.active') }}</p>
                    <p class="mt-0.5 text-[17px] font-semibold text-slate-900">{{ pdfPreview.active_users.toLocaleString('ru-RU') }}</p>
                  </div>
                  <div class="rounded-lg bg-[#f4faef] px-3 py-2">
                    <p class="text-[9.5px] uppercase tracking-wider text-slate-500">{{ t('settings.pdf.metrics.chats') }}</p>
                    <p class="mt-0.5 text-[17px] font-semibold text-slate-900">{{ pdfPreview.chats_total.toLocaleString('ru-RU') }}</p>
                  </div>
                </template>
              </section>

              <section v-if="pdfReportType === 'protection' && pdfPreview.by_reason?.length" class="px-6 pt-5">
                <p class="text-[12px] font-semibold text-slate-900">{{ t('settings.pdf.reasons_title') }}</p>
                <ul class="mt-2 space-y-1.5">
                  <li v-for="r in pdfPreview.by_reason" :key="r.reason" class="text-[11px]">
                    <div class="flex items-center justify-between gap-2">
                      <span class="truncate text-slate-700">{{ r.label || r.reason }}</span>
                      <span class="shrink-0 font-semibold text-slate-900">{{ r.count.toLocaleString('ru-RU') }}</span>
                    </div>
                    <div class="mt-1 h-1.5 w-full rounded-full bg-slate-100">
                      <div
                        class="h-full rounded-full bg-[#7DFF3A]"
                        :style="{ width: previewReasonBarWidth(r.count) }"
                      />
                    </div>
                  </li>
                </ul>
              </section>

              <section class="px-6 pt-5">
                <p class="text-[12px] font-semibold text-slate-900">
                  {{ pdfReportType === 'growth' ? t('settings.pdf.dynamic_growth') : t('settings.pdf.dynamic_deletions') }}
                </p>
                <div class="mt-2 overflow-hidden rounded-lg bg-[#f7faf2] p-2">
                  <svg viewBox="0 0 480 110" class="block h-[110px] w-full">
                    <defs>
                      <linearGradient id="pdfSparkFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="#7DFF3A" stop-opacity="0.35" />
                        <stop offset="100%" stop-color="#7DFF3A" stop-opacity="0" />
                      </linearGradient>
                    </defs>
                    <path :d="`${previewSparklinePath(pdfPreview.by_hour)} L 464 94 L 16 94 Z`" fill="url(#pdfSparkFill)" />
                    <path :d="previewSparklinePath(pdfPreview.by_hour)" fill="none" stroke="#3a9a16" stroke-width="1.8" />
                  </svg>
                  <div class="mt-1 flex justify-between px-1 text-[9px] text-slate-500">
                    <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>23:00</span>
                  </div>
                </div>
              </section>

              <section
                v-if="pdfReportType === 'growth' && pdfPreview.audience_gender"
                class="px-6 pt-5"
              >
                <p class="text-[12px] font-semibold text-slate-900">{{ t('settings.pdf.audience_gender') }}</p>
                <div class="mt-2 grid grid-cols-3 gap-2 text-[11px]">
                  <div class="rounded-md bg-sky-50 px-2 py-1.5">
                    <p class="text-[9.5px] uppercase tracking-wider text-slate-500">{{ t('settings.pdf.gender_male') }}</p>
                    <p class="text-[14px] font-semibold text-slate-900">{{ Number(pdfPreview.audience_gender.male || 0).toLocaleString('ru-RU') }}</p>
                  </div>
                  <div class="rounded-md bg-pink-50 px-2 py-1.5">
                    <p class="text-[9.5px] uppercase tracking-wider text-slate-500">{{ t('settings.pdf.gender_female') }}</p>
                    <p class="text-[14px] font-semibold text-slate-900">{{ Number(pdfPreview.audience_gender.female || 0).toLocaleString('ru-RU') }}</p>
                  </div>
                  <div class="rounded-md bg-slate-100 px-2 py-1.5">
                    <p class="text-[9.5px] uppercase tracking-wider text-slate-500">{{ t('settings.pdf.gender_unknown') }}</p>
                    <p class="text-[14px] font-semibold text-slate-900">{{ Number(pdfPreview.audience_gender.unknown || 0).toLocaleString('ru-RU') }}</p>
                  </div>
                </div>
              </section>

              <footer class="mt-5 border-t border-slate-200 px-6 py-3 text-[10px] text-slate-400">
                {{ t('settings.pdf.footer') }}
              </footer>
            </article>
          </div>
          <div
            v-else
            class="flex h-full min-h-[280px] items-center justify-center px-6 text-center text-[13px] text-white/45"
          >
            {{ t('settings.pdf.empty') }}
          </div>
        </div>

        <div class="px-4 pb-4 pt-3">
          <button
            type="button"
            class="mx-auto inline-flex w-full max-w-[260px] items-center justify-center gap-2 rounded-2xl bg-white/[0.07] py-3 text-[13px] font-medium text-white transition active:scale-[0.98] disabled:opacity-40"
            :disabled="pdfBusy || pdfPreviewLoading || !pdfPreview"
            @click="copyPdfLink"
          >
            <span v-if="pdfBusy && pdfBusyAction === 'copy'" class="h-1.5 w-1.5 animate-pulse rounded-full bg-white/70" />
            {{ pdfBusy && pdfBusyAction === 'copy' ? t('settings.pdf.copy_busy') : t('settings.pdf.copy') }}
          </button>
        </div>
      </div>
    </div>

    <!-- PIN gate modal -->
    <div
      v-if="showPinModal"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center bg-black/55 p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] backdrop-blur-md sm:items-center"
      role="dialog"
      aria-modal="true"
      @click.self="showPinModal = false"
    >
      <div class="w-full max-w-md overflow-hidden rounded-[24px] border border-white/[0.14] bg-[#1c1c1e]/95 p-5 backdrop-blur-2xl">
        <p class="text-[17px] font-semibold text-white">{{ t('settings.security.pin.gate_title') }}</p>
        <p class="mt-1 text-[13px] text-white/45">{{ t('settings.security.pin.gate_hint') }}</p>
        <input
          v-model="pinEntry"
          type="password"
          inputmode="numeric"
          maxlength="4"
          class="mt-4 w-full rounded-2xl border border-white/[0.14] bg-black/35 px-4 py-3.5 text-center text-[22px] font-semibold tracking-[0.45em] text-white outline-none focus:border-emerald-400/45"
          autocomplete="off"
          @keyup.enter="submitPinModal"
        />
        <div class="mt-5 flex gap-2.5">
          <button
            type="button"
            class="flex-1 rounded-2xl border border-white/[0.14] bg-white/[0.06] py-3 text-[15px] font-medium text-white"
            @click="showPinModal = false"
          >
            {{ t('common.cancel') }}
          </button>
          <button
            type="button"
            class="flex-1 rounded-2xl border border-emerald-400/35 bg-emerald-500 py-3 text-[15px] font-semibold text-white disabled:opacity-50"
            :disabled="pinBusy"
            @click="submitPinModal"
          >
            {{ t('settings.security.pin.next') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-root {
  font-family:
    system-ui,
    -apple-system,
    BlinkMacSystemFont,
    'SF Pro Text',
    'SF Pro Display',
    'Segoe UI',
    sans-serif;
}
</style>

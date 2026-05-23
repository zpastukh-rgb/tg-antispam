<script setup>
import { ref, shallowRef, onMounted, onBeforeUnmount, computed, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useApi, messageFromApiError } from '../composables/useApi'

const { t: tt, te, locale } = useI18n()
function adminLocaleTag() {
  return String(locale.value || 'ru').toLowerCase().startsWith('en') ? 'en-US' : 'ru-RU'
}
function localeIsEn() {
  return adminLocaleTag() === 'en-US'
}
const guardPulseUiMarker = computed(() => tt('admin.pulse.ui_marker'))
import {
  adminBroadcastUploadMedia,
  adminBroadcastDeleteMediaItem,
  fetchAdminBroadcastMediaPreviewUrl,
  revokeBroadcastMediaPreviewUrl,
  getInitData,
} from '../api/client'
import { hasFullAdminRights } from '../utils/adminAccess'
import { userCanUseBroadcasts, ownerHasPremiumAnalytics } from '../utils/broadcastAccess'
import { usePremiumLock } from '../composables/usePremiumLock'
import { useCabinetMode } from '../composables/useCabinetMode'
import SubscriptionManagementPanel from '../components/SubscriptionManagementPanel.vue'
import OwnerCabinetHome from '../components/OwnerCabinetHome.vue'
import OwnerCabinetProtectionStats from '../components/OwnerCabinetProtectionStats.vue'
import CabinetPremiumTitleBar from '../components/CabinetPremiumTitleBar.vue'
import SecurityPinGateModal from '../components/SecurityPinGateModal.vue'
import GuardTeleport from '../components/GuardTeleport.vue'
import { normalizeHtmlForTelegram, sanitizeEditorLinksNoUnderline, telegramHtmlToEditorInnerHtml } from '../utils/telegramHtmlForTg'
import {
  editorSplitBlockquoteAtCaret,
  editorSoftBreakInsideBlockquote,
  editorPlaceCaretAtEditableStart,
  editorResetTypingExecCommands,
  editorUnwrapRangeInsideContainer,
  editorUnwrapElementFully,
  editorApplyMonospaceFormat,
} from '../utils/richEditorDom'
import { useSecurityPinGate } from '../composables/useSecurityPinGate'
import { shouldAskPinForAction } from '../utils/settingsSecurity'

const { api, fetch, fetchSilent, hasInitData } = useApi()
const { openLock: openPremiumFeatureLock } = usePremiumLock()
const route = useRoute()
const router = useRouter()
const { cabinetMode, setCabinetMode } = useCabinetMode()
/** С первого кадра при открытии из Telegram — не мелькает полная админка до загрузки /me */
const loading = ref(!!getInitData())
const error = ref('')
const data = ref(null)
const tab = ref('overview')
/** Вкладки, перенесённые под карточки Обзора (полная админка). */
const adminOverviewEmbed = ref('')
function goAdminEmbed(name) {
  adminOverviewEmbed.value = String(name || '')
  tab.value = 'overview'
}

/** Синий ADM (Premium): hero как на главной + сетка разделов и вложенные экраны. */
const premiumAdmSection = ref('')
const ownerProtectionStatsMode = ref('protection')
const ownerProtectionReportOpen = ref(false)
const ownerProtectionReportContext = ref({
  scope: 'all',
  chatId: null,
  chatTitle: '',
  eligibleChatIds: [],
})
function openPremiumAdmCard(key) {
  const k = String(key || '')
  ownerProtectionReportOpen.value = false
  if (k === 'partner') {
    premiumAdmSection.value = ''
    ownerProtectionStatsMode.value = 'protection'
    router.push({ path: '/', query: { section: 'partner' } }).catch(() => {})
    return
  }
  if (k === 'broadcasts') {
    if (isOwnerCabinet.value && !userCanUseBroadcasts(meAdminProfile.value)) {
      openPremiumFeatureLock({
        feature: 'broadcast_owner_hub',
        me: meAdminProfile.value,
        titleKey: 'premium_lock.lock_broadcast_owner_title',
        descriptionKey: 'premium_lock.lock_broadcast_owner_body',
      })
      return
    }
    premiumAdmSection.value = ''
    ownerProtectionStatsMode.value = 'protection'
    tab.value = 'broadcasts'
    return
  }
  if (k === 'settings') {
    premiumAdmSection.value = ''
    ownerProtectionStatsMode.value = 'protection'
    router.push('/settings').catch(() => {})
    return
  }
  if (k === 'updates') {
    premiumAdmSection.value = ''
    ownerProtectionStatsMode.value = 'protection'
    router.push({ path: '/', query: { section: 'account', updates: '1' } }).catch(() => {})
    return
  }
  if (k === 'stats') {
    if (isOwnerCabinet.value && !ownerHasPremiumAnalytics(meAdminProfile.value)) {
      openPremiumFeatureLock({
        feature: 'owner_stats_hub',
        me: meAdminProfile.value,
        titleKey: 'premium_lock.lock_owner_stats_title',
        descriptionKey: 'premium_lock.lock_owner_stats_body',
      })
      return
    }
    premiumAdmSection.value = 'protection'
    ownerProtectionStatsMode.value = 'growth'
    return
  }
  if (k === 'protection') {
    if (isOwnerCabinet.value && !ownerHasPremiumAnalytics(meAdminProfile.value)) {
      openPremiumFeatureLock({
        feature: 'owner_protection_reports_hub',
        me: meAdminProfile.value,
        titleKey: 'premium_lock.lock_owner_protection_reports_title',
        descriptionKey: 'premium_lock.lock_owner_protection_reports_body',
      })
      return
    }
  }
  ownerProtectionStatsMode.value = 'protection'
  premiumAdmSection.value = k
}
function premiumExitToHome() {
  ownerProtectionReportOpen.value = false
  premiumAdmSection.value = ''
  tab.value = 'overview'
}

function goOwnerSubscriptionPage() {
  router.push({ path: '/', query: { section: 'subscription' } }).catch(() => {})
}

function onGuardHeaderBack(ev) {
  if (String(route.path || '') !== '/admin') return
  if (showFullAdminShell.value && adminOverviewEmbed.value) {
    ev.preventDefault()
    adminOverviewEmbed.value = ''
    return
  }
  if (isOwnerCabinet.value) {
    if (premiumAdmSection.value) {
      ev.preventDefault()
      premiumAdmSection.value = ''
      return
    }
    if (tab.value !== 'overview') {
      ev.preventDefault()
      tab.value = 'overview'
      adminOverviewEmbed.value = ''
      return
    }
  }
}

watch(tab, (v) => {
  if (v !== 'overview') premiumAdmSection.value = ''
  if (String(route.path || '') === '/admin') {
    const nt = String(v || 'overview')
    if (String(route.query.admin_tab || '') !== nt) {
      router.replace({ path: '/admin', query: { ...route.query, admin_tab: nt } }).catch(() => {})
    }
  }
})

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
const partnerHelpTitle = ref('')
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
const joinReportPresetOptions = computed(() => [
  { id: 'day', label: tt('admin.partner_presets.join_day') },
  { id: '3d', label: tt('admin.partner_presets.join_3d') },
  { id: 'week', label: tt('admin.partner_presets.join_week') },
  { id: 'month', label: tt('admin.partner_presets.join_month') },
])
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
/** Модалка статистики по записи из «Последние рассылки» + повтор отправки */
const bcRecentStatsModalOpen = ref(false)
const bcRecentStatsBroadcastId = ref(0)
const bcRecentStatsBroadcastMeta = ref(null)
const bcRecentStatsLoading = ref(false)
const bcRecentStatsSnapshot = ref(null)
const bcQuickDraftModalOpen = ref(false)
/** Сохранённое на сервере название при открытии быстрого черновика — для кнопки ✓ */
const bcQuickTitleBaseline = ref('')
const bcQuickDraftBaseline = ref(null)
const bcOpeningQuickDraft = ref(false)
const bcQuickDraftInitializing = ref(false)
const bcSendTargetModalOpen = ref(false)
const bcSendTimingModalOpen = ref(false)
const bcSendTimingMode = ref('now')
const bcSendScheduleAtLocal = ref('')
/** Ошибка quote / валидации на шаге «Куда отправить» без нативного alert под стеком модалок */
const bcSendQuoteError = ref('')
const bcRecentPulseById = ref({})
const bcSendTargetChannels = ref(false)
const bcSendTargetGroups = ref(false)
const bcSendTargetBots = ref(false)
const bcAdminIncludeBotRecipients = ref(false)
const bcShowBotsPicker = ref(false)
const bcBotsSearch = ref('')
const bcBotRecipients = ref([{ id: 1, special: 'all' }])
const bcSelectedBotRecipientIds = ref([])
function bcBotRowTitle(b) {
  if (b?.special === 'all') return tt('admin.broadcast_send.all_bot_users')
  return String(b?.title || '')
}
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
const bcQuickSaveBtnLabel = computed(() => {
  if (bcSaving.value) return tt('common.save')
  if (bcSavedTick.value) return tt('admin.broadcast_ui.btn_saved')
  return tt('common.save')
})
const bcQuickSaveBtnClass = computed(() => {
  if (bcSaving.value) return 'text-zinc-400'
  if (bcSavedTick.value) return 'text-emerald-300 shadow-[0_0_14px_-4px_rgba(52,211,153,0.65)]'
  return 'text-[#70a8ff]'
})
const bcBodyHtml = ref('')
const bcButtonRows = ref([[{ text: '', url: '', web_app_url: '', callback_data: '' }]])
/** Тип для следующей загрузки файла */
/** Тип медиа, сохранённый на сервере для выбранного черновика */
const bcMediaKindStored = ref('none')
const bcMediaOriginalName = ref('')
const bcBodyRef = ref(null)
/** Подсветка «тряски» при «Далее» с незаполненными полями */
const bcQuickDraftTitleInputRef = ref(null)
const bcCampaignUxWizardTitleInputRef = ref(null)
const bcCampaignUxWizardPostsListRef = ref(null)
const bcEditModalOpen = ref(false)
const bcEditBodyRef = ref(null)
function bcBodyEditors() {
  const out = []
  const v = bcBodyRef.value
  if (v) {
    if (Array.isArray(v)) out.push(...v.filter(Boolean))
    else out.push(v)
  }
  if (bcEditModalOpen.value && bcEditBodyRef.value) {
    out.push(bcEditBodyRef.value)
  }
  return out.filter(Boolean)
}
function bcResolveBodyEditor() {
  const list = bcBodyEditors()
  if (!list.length) return null
  const ae = document.activeElement
  const focused = list.find((el) => el === ae || (ae && typeof el.contains === 'function' && el.contains(ae)))
  if (focused) return focused
  const visible = list.find((el) => el.isConnected && el.getClientRects().length > 0)
  return visible || list[0] || null
}
function bcSetBodyEditorHtml(html) {
  const raw = String(html || '')
  const next = telegramHtmlToEditorInnerHtml(raw)
  for (const el of bcBodyEditors()) {
    el.innerHTML = next || ''
    sanitizeEditorLinksNoUnderline(el)
  }
}
const bcEmojiHostRef = ref(null)
const bcEmojiOpen = ref(false)
const bcShowMainHelp = ref(false)
/** '' | 'keyboard' | 'media' — модалки редактирования кнопок и файла из блока «Оформление» */
const bcAuxModal = ref('')
const bcKeyboardInfoOpen = ref(false)
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

const bcCurrentBroadcastIsOneshot = computed(() => {
  const id = Number(bcSelectedId.value || 0)
  const row = (broadcasts.value || []).find((x) => Number(x?.id || 0) === id)
  return String(row?.cabinet_draft_scope || '') === 'oneshot'
})

const bcRecentSendEvents = ref([])
const bcRecentListPreset = ref('all')

const bcRecentBroadcasts = computed(() => {
  const events = bcRecentSendEvents.value || []
  if (events.length) {
    return events.map((ev) => ({
      id: Number(ev.broadcast_id || 0),
      run_id: Number(ev.run_id || 0),
      schedule_id: ev.schedule_id ? Number(ev.schedule_id) : null,
      autopost_campaign_id: ev.autopost_campaign_id ? Number(ev.autopost_campaign_id) : null,
      campaign_title: String(ev.campaign_title || '').trim(),
      title: String(ev.broadcast_title || '').trim(),
      sent_at: ev.sent_at || ev.created_at,
      scheduled_at: ev.scheduled_at || null,
      timezone_name: ev.timezone_name || null,
      schedule_status: String(ev.schedule_status || ''),
      created_at: ev.created_at,
      recipient_ok: Number(ev.recipient_ok || 0),
      recipient_total: Number(ev.recipient_total || 0),
      recipient_fail: Number(ev.recipient_fail || 0),
      audience_ok: Number(ev.audience_ok || 0),
      last_target: String(ev.last_target || ''),
      status: String(ev.status || 'sent'),
      list_kind: String(ev.list_kind || ''),
      run_source: String(ev.run_source || ''),
      target_kind: String(ev.target_kind || ''),
    }))
  }
  return (broadcasts.value || [])
    .filter((b) => {
      const status = String(b?.status || '').toLowerCase()
      const hasRuns = Number(b?.recipient_total || 0) > 0 || Number(b?.recipient_ok || 0) > 0 || Number(b?.recipient_fail || 0) > 0
      return hasRuns || status === 'sent' || status === 'sending' || status === 'failed'
    })
    .sort((a, b) => {
      const ta = Date.parse(String(a?.sent_at || a?.created_at || 0)) || 0
      const tb = Date.parse(String(b?.sent_at || b?.created_at || 0)) || 0
      return tb - ta
    })
})
const bcRecentBroadcastsFiltered = computed(() => {
  const src = bcRecentBroadcasts.value || []
  const preset = String(bcRecentListPreset.value || 'all')
  if (preset === 'oneshot') {
    return src.filter((item) => {
      const lk = String(item?.list_kind || '').toLowerCase()
      return lk === 'oneshot' || lk === 'oneshot_scheduled'
    })
  }
  if (preset === 'scheduled') {
    return src.filter((item) => String(item?.list_kind || '').toLowerCase() === 'oneshot_scheduled')
  }
  return src
})
const bcRecentBroadcastsPreview = computed(() => bcRecentBroadcastsFiltered.value.slice(0, 3))
const bcQuickButtonPreviewRows = computed(() =>
  (bcButtonRows.value || [])
    .map((row) =>
      (Array.isArray(row) ? row : [])
        .map((btn) => ({
          text: String(btn?.text || '').trim(),
          url: String(btn?.url || btn?.web_app_url || '').trim(),
          style: String(btn?.style || '').trim().toLowerCase(),
          kind: String(btn?.kind || 'default').trim().toLowerCase(),
        }))
        .filter((btn) => btn.text),
    )
    .filter((row) => row.length),
)
const bcQuickButtonPreview = computed(() => bcQuickButtonPreviewRows.value.flat())
const bcKeyboardLayoutActive = computed(() => {
  const rows = bcQuickButtonPreviewRows.value
  if (!rows.length) return 'inline'
  if (rows.length === 1) return 'inline'
  if (rows.length > 1 && rows.every((r) => r.length === 1)) return 'stacked'
  return 'custom'
})

const bcSendTargetSummary = computed(() => {
  const rows = []
  if (bcSendTargetChannels.value) {
    rows.push(tt('admin.broadcast_send.target_channels', { n: Number(bcSelectedChannelIds.value?.length || 0) }))
  }
  if (bcSendTargetGroups.value) {
    rows.push(tt('admin.broadcast_send.target_groups', { n: Number(bcSelectedGroupIds.value?.length || 0) }))
  }
  if (showFullAdminShell.value && bcAdminIncludeBotRecipients.value) {
    rows.push(tt('admin.broadcast_ui.include_bot_users_short'))
  }
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
  if (localeIsEn()) {
    return v === 1
      ? tt('admin.broadcast_send.symbols_one', { n: v })
      : tt('admin.broadcast_send.symbols_other', { n: v })
  }
  return `~${v} ${ruPlural(v, 'символ', 'символа', 'символов')}`
}

function bcConfirmButtonsLabel(n) {
  const v = Math.max(0, Number(n || 0))
  if (!v) return tt('admin.broadcast_send.buttons_none')
  if (localeIsEn()) {
    return v === 1
      ? tt('admin.broadcast_send.buttons_one', { n: v })
      : tt('admin.broadcast_send.buttons_other', { n: v })
  }
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
  if (sameDay) return tt('admin.broadcast_send.today_time', { time: timeStr })
  return timeStr
}

function fmtIntSpace(n) {
  const v = Number(n || 0)
  if (!Number.isFinite(v)) return '0'
  try {
    return new Intl.NumberFormat(adminLocaleTag()).format(Math.trunc(v))
  } catch {
    return String(Math.trunc(v))
  }
}

function fmtPctTrim(p) {
  if (p == null) return '—'
  const n = Number(p)
  if (!Number.isFinite(n)) return '—'
  const s = localeIsEn() ? n.toFixed(1) : n.toFixed(1).replace('.', ',')
  return `${s}%`
}
function stripHtml(raw) {
  return String(raw || '')
    .replace(/<[^>]*>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

const bcSendProgressTotal = computed(() => {
  const row = bcSendLiveRow.value
  const rt = Number(row?.recipient_total || 0)
  if (Number.isFinite(rt) && rt > 0) return rt
  const kind = String(bcSendTargetKind.value || 'groups')
  let n = 0
  if (kind === 'users') n = Number(bcSelectedBotRecipientIds.value?.length || 0)
  else if (kind === 'groups' || kind === 'all') {
    n = bcActiveSendGroupIds.value.length + bcActiveSendChannelIds.value.length
  } else {
    n =
      bcActiveSendGroupIds.value.length +
      bcActiveSendChannelIds.value.length +
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

const bcSendDeliveredOk = computed(() => {
  const s = bcSendResultSnapshot.value
  if (!s) return 0
  const o = Number(s.overall?.ok ?? NaN)
  if (Number.isFinite(o) && o > 0) return Math.max(0, Math.trunc(o))
  const g = Number(s.groups?.ok ?? 0)
  const b = Number(s.bots?.ok ?? 0)
  const sum = (Number.isFinite(g) ? g : 0) + (Number.isFinite(b) ? b : 0)
  if (sum > 0) return Math.max(0, Math.trunc(sum))
  const aud = Number(s.audience_ok || 0)
  return Number.isFinite(aud) && aud > 0 ? Math.max(0, Math.trunc(aud)) : 0
})

const bcSendDeliveredTotal = computed(() => {
  const s = bcSendResultSnapshot.value
  if (!s) return bcSendProgressTotal.value
  const t = Number(s.overall?.total ?? NaN)
  if (Number.isFinite(t) && t > 0) return Math.max(0, Math.trunc(t))
  const aud = Number(s.audience_total || 0)
  if (Number.isFinite(aud) && aud > 0) return Math.max(0, Math.trunc(aud))
  return bcSendProgressTotal.value
})

const bcSendDeliveredPct = computed(() =>
  fmtPctPartFromRatio(bcSendDeliveredOk.value, bcSendDeliveredTotal.value),
)

const bcSendCtrDen = computed(() => {
  const s = bcSendResultSnapshot.value
  const g = Number(s?.connected_groups_total || 0)
  const b = Number(s?.connected_bots_total || 0)
  const sum = (Number.isFinite(g) ? g : 0) + (Number.isFinite(b) ? b : 0)
  return Math.max(1, Math.trunc(sum))
})

const bcSendStatCtrUsesClickRatio = computed(() => {
  const s = bcSendResultSnapshot.value
  if (!s) return true
  const m = String(s.stats_ctr_mode || '').toLowerCase()
  if (m === 'reach') return false
  if (m === 'interactions') return true
  const t = Number(s.real_clicks_total ?? NaN)
  return Number.isFinite(t) && t >= 0
})

const bcSendStatCtrSub = computed(() => {
  const s = bcSendResultSnapshot.value
  if (!s) return ''
  const delivered = bcSendDeliveredOk.value
  const clicksTotal = Math.max(0, Math.trunc(Number(s.real_clicks_total || 0)))
  if (bcSendStatCtrUsesClickRatio.value) {
    return tt('admin.broadcast_shell.ctr_sub_clicks', {
      clicks: fmtIntSpace(clicksTotal),
      delivered: fmtIntSpace(delivered),
    })
  }
  return tt('admin.broadcast_shell.ctr_sub_reach', {
    delivered: fmtIntSpace(delivered),
    base: fmtIntSpace(bcSendCtrDen.value),
  })
})

const bcSendCtrPct = computed(() => {
  const s = bcSendResultSnapshot.value
  if (!s) return null
  const apiPct = s.stats_ctr_percent
  if (apiPct != null && Number.isFinite(Number(apiPct))) {
    return clampPct(Number(apiPct))
  }
  const clicksTotal = Number(s.real_clicks_total || 0)
  const delivered = bcSendDeliveredOk.value
  if (Number.isFinite(clicksTotal) && clicksTotal >= 0) {
    return fmtPctPartFromRatio(Math.max(0, Math.trunc(clicksTotal)), delivered)
  }
  return fmtPctPartFromRatio(delivered, bcSendCtrDen.value)
})

/** Реакции по ссылкам reaction:… в учёте */
const bcSendDoneReactions = computed(() => Number(bcSendResultSnapshot.value?.real_reactions_total || 0))

const bcRecentStatDeliveredOk = computed(() => {
  const s = bcRecentStatsSnapshot.value
  if (!s) return 0
  const o = Number(s.overall?.ok ?? NaN)
  if (Number.isFinite(o) && o > 0) return Math.max(0, Math.trunc(o))
  const g = Number(s.groups?.ok ?? 0)
  const b = Number(s.bots?.ok ?? 0)
  const sum = (Number.isFinite(g) ? g : 0) + (Number.isFinite(b) ? b : 0)
  if (sum > 0) return Math.max(0, Math.trunc(sum))
  const aud = Number(s.audience_ok || 0)
  return Number.isFinite(aud) ? Math.max(0, Math.trunc(aud)) : 0
})
const bcRecentStatCtrDen = computed(() => {
  const s = bcRecentStatsSnapshot.value
  if (!s) return 1
  const g = Number(s.connected_groups_total || 0)
  const b = Number(s.connected_bots_total || 0)
  const sum = (Number.isFinite(g) ? g : 0) + (Number.isFinite(b) ? b : 0)
  return Math.max(1, Math.trunc(sum))
})
const bcRecentStatCtrUsesClickRatio = computed(() => {
  const s = bcRecentStatsSnapshot.value
  if (!s) return true
  const m = String(s.stats_ctr_mode || '').toLowerCase()
  if (m === 'reach') return false
  if (m === 'interactions') return true
  const t = Number(s.real_clicks_total ?? NaN)
  return Number.isFinite(t) && t >= 0
})
const bcRecentStatCtrSub = computed(() => {
  const s = bcRecentStatsSnapshot.value
  if (!s) return ''
  const delivered = bcRecentStatDeliveredOk.value
  const clicksTotal = Math.max(0, Math.trunc(Number(s.real_clicks_total || 0)))
  if (bcRecentStatCtrUsesClickRatio.value) {
    return tt('admin.broadcast_shell.ctr_sub_clicks', {
      clicks: fmtIntSpace(clicksTotal),
      delivered: fmtIntSpace(delivered),
    })
  }
  return tt('admin.broadcast_shell.ctr_sub_reach', {
    delivered: fmtIntSpace(delivered),
    base: fmtIntSpace(bcRecentStatCtrDen.value),
  })
})
const bcRecentStatCtrPct = computed(() => {
  const s = bcRecentStatsSnapshot.value
  if (!s) return null
  const apiPct = s.stats_ctr_percent
  if (apiPct != null && Number.isFinite(Number(apiPct))) {
    return clampPct(Number(apiPct))
  }
  const clicksTotal = Number(s.real_clicks_total || 0)
  const delivered = bcRecentStatDeliveredOk.value
  if (Number.isFinite(clicksTotal) && clicksTotal >= 0) {
    return fmtPctPartFromRatio(Math.max(0, Math.trunc(clicksTotal)), delivered)
  }
  return fmtPctPartFromRatio(delivered, bcRecentStatCtrDen.value)
})
const bcRecentStatReactions = computed(() => Number(bcRecentStatsSnapshot.value?.real_reactions_total || 0))

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
  const list = bcBotRecipients.value || []
  if (!q) return list
  return list.filter((b) => bcBotRowTitle(b).toLowerCase().includes(q))
})
/** ID каналов/групп только для включённых галочек «Куда отправить» (старый выбор не тащим). */
const bcActiveSendChannelIds = computed(() => {
  if (!bcSendTargetChannels.value) return []
  return (bcSelectedChannelIds.value || []).map((x) => Number(x || 0)).filter((x) => x !== 0)
})
const bcActiveSendGroupIds = computed(() => {
  if (!bcSendTargetGroups.value) return []
  return (bcSelectedGroupIds.value || []).map((x) => Number(x || 0)).filter((x) => x !== 0)
})
const bcSelectedTargetsCount = computed(
  () => bcActiveSendChannelIds.value.length + bcActiveSendGroupIds.value.length,
)

function bcDefaultScheduleLocalInput() {
  const d = new Date(Date.now() + 60 * 60 * 1000)
  return toLocalInputValue(d)
}

function bcFormatScheduledAtLabel(raw, tzName) {
  const s = String(raw || '').trim()
  if (!s) return tt('admin.broadcast_send.date_unknown')
  const d = new Date(s)
  if (!Number.isFinite(d.getTime())) return tt('admin.broadcast_send.date_unknown')
  const opts = {
    day: 'numeric',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }
  const tz = String(tzName || '').trim()
  try {
    if (tz) {
      return new Intl.DateTimeFormat(adminLocaleTag(), { ...opts, timeZone: tz }).format(d)
    }
  } catch {
    //
  }
  return d.toLocaleString(adminLocaleTag(), opts)
}

function bcRecentWhenLabel(item) {
  const lk = String(item?.list_kind || '').toLowerCase()
  if (lk === 'oneshot_scheduled' && item?.scheduled_at) {
    return tt('admin.broadcast_shell.scheduled_for', {
      when: bcFormatScheduledAtLabel(item.scheduled_at, item.timezone_name),
    })
  }
  const raw = String(item?.sent_at || item?.created_at || '').trim()
  if (!raw) return tt('admin.broadcast_send.date_unknown')
  const d = new Date(raw)
  if (!Number.isFinite(d.getTime())) return tt('admin.broadcast_send.date_unknown')
  return d.toLocaleString(adminLocaleTag(), {
    day: 'numeric',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function bcRecentStatusLabel(item) {
  const lk = String(item?.list_kind || '').toLowerCase()
  if (lk === 'oneshot_scheduled') return tt('admin.broadcast_shell.status_scheduled')
  const st = String(item?.status || '').toLowerCase()
  const sentAt = String(item?.sent_at || '').trim()
  const okN = Number(item?.recipient_ok || 0)
  const failN = Number(item?.recipient_fail || 0)
  const hadRun = !!sentAt && (okN > 0 || failN > 0)
  if (st === 'draft' && hadRun) {
    if (failN > 0 && okN <= 0) return bcStatusLabel('failed')
    if (failN > 0 && okN > 0) return tt('admin.broadcast_stats.status_partial')
    return bcStatusLabel('sent')
  }
  if (st === 'sent' || st === 'sending' || st === 'failed' || st === 'draft') return bcStatusLabel(st)
  return tt('admin.broadcast_send.status_launch')
}

function bcRecentOneShotStatusClass(item) {
  const lk = String(item?.list_kind || '').toLowerCase()
  if (lk === 'oneshot_scheduled') return 'text-violet-300 font-medium'
  const st = String(item?.status || '').toLowerCase()
  if (st === 'draft') return 'text-rose-400 font-medium'
  if (st === 'failed') return 'text-rose-300'
  if (st === 'sending') return 'text-amber-300'
  if (st === 'sent') return 'text-emerald-400'
  return 'text-sky-300'
}

function bcRecentBroadcastDisplayTitle(item) {
  if (!item) return ''
  const lk = String(item?.list_kind || '').toLowerCase()
  const draftTitle = String(item.title || item.broadcast_title || item.run_title || '').trim()
  const cid = Number(item?.autopost_campaign_id || 0)
  if (cid > 0 || lk === 'campaign') {
    const ct = String(item.campaign_title || '').trim()
    if (ct) return ct
    const camp =
      (cid > 0 ? (bcAutopostCampaigns.value || []).find((c) => Number(c?.id || 0) === cid) : null) ||
      bcCampaignForRecentBroadcast(item)
    if (camp && String(camp.title || '').trim()) return String(camp.title || '').trim()
  }
  if (lk === 'oneshot' || !bcRecentBroadcastKindIsCampaign(item)) {
    if (draftTitle) return draftTitle
    return tt('admin.broadcast_shell.untitled', { id: item.id })
  }
  const camp = bcCampaignForRecentBroadcast(item)
  if (camp && String(camp.title || '').trim()) return String(camp.title || '').trim()
  if (draftTitle) return draftTitle
  return tt('admin.broadcast_shell.untitled', { id: item.id })
}

const bcRecentStatsHeaderTitle = computed(() => {
  const id = Number(bcRecentStatsBroadcastId.value || 0)
  const fromList = (broadcasts.value || []).find((b) => Number(b?.id || 0) === id)
  const meta = bcRecentStatsBroadcastMeta.value
  const row = fromList || meta
  if (row) return bcRecentBroadcastDisplayTitle(row)
  return tt('admin.broadcast_shell.untitled', { id })
})
function bcBroadcastStatsTargetKindForSendFlow() {
  if (isBroadcastShellLite.value) return 'groups'
  const sk = String(bcSendTargetKind.value || '').toLowerCase()
  if (sk === 'groups') return 'groups'
  if (sk === 'users') return 'bots'
  if (sk === 'all') return 'groups'
  return 'bots'
}

/** Из списка: для Premium/рассылок — вкладка «группы», иначе общая сводка. */
function bcBroadcastStatsTargetKindForRecentModal() {
  if (isBroadcastShellLite.value || isPremiumCabinet.value || isDelegatedFreeBroadcastCabinet.value) {
    return 'groups'
  }
  return ''
}

function bcApplyRecentStatsSnapshot(r) {
  return {
    overall: r?.overall || { ok: 0, fail: 0, total: 0 },
    groups: r?.groups || { ok: 0, fail: 0, total: 0 },
    bots: r?.bots || { ok: 0, fail: 0, total: 0 },
    audience_ok: Number(r?.audience_ok || 0),
    audience_total: Number(r?.audience_total || 0),
    real_clicks: Number(r?.real_clicks || 0),
    real_transitions: Number(r?.real_transitions || 0),
    real_clicks_total: Number(r?.real_clicks_total || 0),
    real_link_clicks_total: Number(r?.real_link_clicks_total || 0),
    real_callback_clicks_total: Number(r?.real_callback_clicks_total || 0),
    real_reactions_total: Number(r?.real_reactions_total || 0),
    connected_groups_total: Number(r?.connected_groups_total || 0),
    connected_bots_total: Number(r?.connected_bots_total || 0),
    broadcast_url_tracking_configured: Boolean(r?.broadcast_url_tracking_configured),
    real_link_items: Array.isArray(r?.real_link_items) ? r.real_link_items : [],
    real_callback_items: Array.isArray(r?.real_callback_items) ? r.real_callback_items : [],
    stats_ctr_percent: r?.stats_ctr_percent != null && Number.isFinite(Number(r.stats_ctr_percent)) ? Number(r.stats_ctr_percent) : null,
    stats_ctr_mode: String(r?.stats_ctr_mode || ''),
    per_groups: Array.isArray(r?.per_groups) ? r.per_groups : [],
    send_history: Array.isArray(r?.send_history) ? r.send_history : [],
  }
}

function bcClearStatsPulseTimers() {
  for (const t of bcStatsPulseTimers.value || []) {
    clearTimeout(t)
  }
  bcStatsPulseTimers.value = []
}

function bcPulseBroadcastStats(loadFn, broadcastId, guardFn) {
  const bid = Number(broadcastId || 0)
  if (!bid || typeof loadFn !== 'function') return
  bcClearStatsPulseTimers()
  bcStatsPulseTimers.value = BC_STATS_PULSE_DELAYS_MS.map((ms) =>
    window.setTimeout(() => {
      if (typeof guardFn === 'function' && !guardFn()) return
      void loadFn(bid, { silent: true })
    }, ms),
  )
}

async function bcLoadRecentBroadcastStats(broadcastId, opts = {}) {
  const bid = Number(broadcastId || 0)
  if (!bid) return
  const silent = Boolean(opts?.silent)
  const tk = bcBroadcastStatsTargetKindForRecentModal()
  if (!silent) {
    bcRecentStatsLoading.value = true
    bcRecentStatsSnapshot.value = null
  }
  try {
    const runFetch = silent ? fetchSilent : fetch
    const r = await runFetch(() => api.adminBroadcastStats(bid, '', '', '', tk))
    if (r && typeof r === 'object') {
      bcRecentStatsSnapshot.value = bcApplyRecentStatsSnapshot(r)
    }
    try {
      const row = await fetchSilent(() => api.adminBroadcast(bid))
      if (row && Number(row?.id || 0) === bid) {
        upsertBroadcastInList(row)
        if (bcRecentStatsBroadcastId.value === bid) {
          bcRecentStatsBroadcastMeta.value =
            bcRecentStatsBroadcastMeta.value && Number(bcRecentStatsBroadcastMeta.value?.id || 0) === bid
              ? { ...bcRecentStatsBroadcastMeta.value, ...row }
              : { ...row }
        }
      }
    } catch {
      //
    }
  } catch {
    if (!silent) bcRecentStatsSnapshot.value = null
  } finally {
    if (!silent) bcRecentStatsLoading.value = false
  }
}

async function bcOpenRecentBroadcastStats(item) {
  const id = Number(item?.id || 0)
  if (!id) return
  try {
    await loadAutopostCampaigns()
  } catch {
    //
  }
  const cid = Number(item?.autopost_campaign_id || 0)
  if (cid > 0) {
    const camp =
      (bcAutopostCampaigns.value || []).find((c) => Number(c?.id || 0) === cid) ||
      (item.campaign_title ? { id: cid, title: item.campaign_title, autopost: {} } : null)
    if (camp) {
      bcShowAllRecentModal.value = false
      bcCloseRecentBroadcastStats()
      tab.value = 'broadcasts'
      await openBcCampaignUxManage(camp)
      return
    }
  }
  const camp = bcCampaignForRecentBroadcast(item)
  if (camp) {
    bcShowAllRecentModal.value = false
    bcCloseRecentBroadcastStats()
    tab.value = 'broadcasts'
    const freshId = Number(camp?.id || 0)
    const fresh = freshId ? (bcAutopostCampaigns.value || []).find((c) => Number(c?.id || 0) === freshId) : null
    await openBcCampaignUxManage(fresh || camp)
    return
  }

  bcRecentStatsBroadcastId.value = id
  bcRecentStatsBroadcastMeta.value = item ? { ...item } : null
  bcRecentStatsModalOpen.value = true
  bcRecentStatsSnapshot.value = null
  await bcLoadRecentBroadcastStats(id)
  bcPulseBroadcastStats(
    bcLoadRecentBroadcastStats,
    id,
    () => bcRecentStatsModalOpen.value && Number(bcRecentStatsBroadcastId.value || 0) === id,
  )
}

function bcCloseRecentBroadcastStats() {
  bcRecentStatsModalOpen.value = false
  bcRecentStatsBroadcastId.value = 0
  bcRecentStatsSnapshot.value = null
  bcRecentStatsBroadcastMeta.value = null
  bcClearStatsPulseTimers()
}

function bcRecentStatsGoToBroadcastsTab() {
  bcCloseRecentBroadcastStats()
  tab.value = 'broadcasts'
}

function bcRecentStatsRepeatBroadcast() {
  if (isOwnerCabinet.value && !meAdminProfile.value?.is_premium) {
    void router.push({ path: '/', query: { section: 'billing', scroll: 'plans' } })
    return
  }
  const id = Number(bcRecentStatsBroadcastId.value || 0)
  if (!id) return
  const item =
    (broadcasts.value || []).find((x) => Number(x?.id || 0) === id) || bcRecentStatsBroadcastMeta.value
  if (!item || Number(item?.id || 0) !== id) {
    window.alert(tt('admin.broadcast_shell.repeat_need_refresh'))
    return
  }
  bcRecentStatsModalOpen.value = false
  bcRecentStatsBroadcastId.value = 0
  bcRecentStatsSnapshot.value = null
  bcRecentStatsBroadcastMeta.value = null

  applyBroadcastToForm(item)
  bcEditorOpen.value = false
  bcQuickDraftModalOpen.value = true
  bcQuickTitleBaseline.value = String(bcTitle.value || '')
  bcQuickDraftBaseline.value = null
  nextTick(() => {
    bcSetBodyEditorHtml(bcBodyHtml.value || '')
    bcSyncEditorHtml()
    bcQuickDraftBaseline.value = {
      title: String(bcTitle.value || '').trim(),
      body: String(bcNormalizeHtmlForTelegram(bcBodyHtml.value || '') || ''),
      keyboard: JSON.stringify(bcBuildKeyboardPayload() || []),
      mediaKind: String(bcMediaKindStored.value || 'none'),
      mediaName: String(bcMediaOriginalName.value || ''),
    }
    bcUpdateFormatState()
  })
}

async function openQuickBroadcastDraft() {
  if (isOwnerCabinet.value && !meAdminProfile.value?.is_premium) {
    void router.push({ path: '/', query: { section: 'billing', scroll: 'plans' } })
    return
  }
  if (bcOpeningQuickDraft.value) return
  bcOpeningQuickDraft.value = true
  try {
    bcQuickDraftInitializing.value = true
    bcEditorOpen.value = false
    revokeAllBcMediaPreviewUrls()
    bcSelectedId.value = null
    bcTitle.value = ''
    bcBodyHtml.value = ''
    bcButtonRows.value = [[bcEmptyButton()]]
    bcMediaKindStored.value = 'none'
    bcMediaOriginalName.value = ''
    bcMediaHistory.value = []
    bcQuickDraftModalOpen.value = true
    await nextTick()
    bcSetBodyEditorHtml('')
    bcSyncEditorHtml()
    await createBcDraft('oneshot')
    if (!bcSelectedId.value) return
    bcEditorOpen.value = false
    bcQuickTitleBaseline.value = String(bcTitle.value || '')
    bcQuickDraftBaseline.value = null
    await nextTick()
    bcSetBodyEditorHtml(bcBodyHtml.value || '')
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
  bcSendQuoteError.value = ''
  bcSendTargetChannels.value = false
  bcSendTargetGroups.value = false
  bcSendTargetBots.value = false
  bcAdminIncludeBotRecipients.value = false
  bcBroadcastGroupScope.value = 'mine'
  await Promise.all([loadBroadcastEligibleGroups(), loadBroadcastEligibleChannels()])
  bcSendTargetModalOpen.value = true
}

async function proceedSendTargetModal() {
  if (!bcCanProceedSendTargets.value) return
  bcSendQuoteError.value = ''
  bcSendTimingMode.value = 'now'
  if (!String(bcSendScheduleAtLocal.value || '').trim()) {
    bcSendScheduleAtLocal.value = bcDefaultScheduleLocalInput()
  }
  bcSendTargetModalOpen.value = false
  bcSendTimingModalOpen.value = true
}

async function proceedSendTimingModal() {
  bcSendQuoteError.value = ''
  if (bcSendTimingMode.value === 'scheduled') {
    const raw = String(bcSendScheduleAtLocal.value || '').trim()
    if (!raw) {
      bcSendQuoteError.value = tt('admin.broadcast_send.schedule_time_required')
      return
    }
    const t = new Date(raw).getTime()
    if (!Number.isFinite(t) || t < Date.now() + 2 * 60 * 1000) {
      bcSendQuoteError.value = tt('admin.broadcast_send.schedule_time_too_soon')
      return
    }
  }
  bcSendTimingModalOpen.value = false
  await openBcConfirmModal()
}

const bcConfirmSubmitLabel = computed(() => {
  if (bcConfirmSending.value) return tt('admin.broadcast_ui.sending')
  if (bcSendTimingMode.value === 'scheduled') return tt('admin.broadcast_ui.schedule')
  return tt('admin.broadcast_ui.send')
})

const bcConfirmReadySub = computed(() =>
  bcSendTimingMode.value === 'scheduled'
    ? tt('admin.broadcast_ui.ready_sub_scheduled')
    : tt('admin.broadcast_ui.ready_sub'),
)

function bcConfirmBuildPayload() {
  const channelIds = [...bcActiveSendChannelIds.value]
  const groupIds = [...bcActiveSendGroupIds.value]
  const mergedIds = [...new Set([...channelIds, ...groupIds].map((x) => Number(x || 0)).filter((x) => x !== 0))]
  const wantBotsDmOnly = !!(showFullAdminShell.value && bcAdminIncludeBotRecipients.value && !mergedIds.length)
  const wantBotsAlso = !!(showFullAdminShell.value && bcAdminIncludeBotRecipients.value && mergedIds.length > 0)

  if (!mergedIds.length) {
    if (wantBotsDmOnly && !bcSendTargetChannels.value && !bcSendTargetGroups.value) {
      return {
        mode: 'users',
        ids: [],
        recipientLabel: tt('admin.broadcast_send.all_bot_users'),
      }
    }
    return null
  }
  if (!bcSendTargetChannels.value && !bcSendTargetGroups.value) {
    return null
  }
  const chSet = new Set((bcBroadcastChannels.value || []).map((c) => bcNormalizeChatId(c)))
  const grSet = new Set((bcBroadcastGroups.value || []).map((c) => bcNormalizeChatId(c)))
  let nChannels = 0
  let nGroups = 0
  for (const rawId of mergedIds) {
    const id = Number(rawId || 0)
    if (!id) continue
    const inCh = chSet.has(id)
    const inGr = grSet.has(id)
    if (inCh && inGr) {
      nChannels += 1
    } else if (inCh) {
      nChannels += 1
    } else if (inGr) {
      nGroups += 1
    } else {
      nGroups += 1
    }
  }

  let label = ''
  if (localeIsEn()) {
    if (nChannels > 0 && nGroups === 0) {
      label =
        nChannels === 1
          ? tt('admin.broadcast_send.en_channel_one', { n: nChannels })
          : tt('admin.broadcast_send.en_channel_other', { n: nChannels })
    } else if (nGroups > 0 && nChannels === 0) {
      label =
        nGroups === 1
          ? tt('admin.broadcast_send.en_group_one', { n: nGroups })
          : tt('admin.broadcast_send.en_group_other', { n: nGroups })
    } else {
      const ch =
        nChannels === 1
          ? tt('admin.broadcast_send.en_channel_one', { n: nChannels })
          : tt('admin.broadcast_send.en_channel_other', { n: nChannels })
      const gr =
        nGroups === 1 ? tt('admin.broadcast_send.en_group_one', { n: nGroups }) : tt('admin.broadcast_send.en_group_other', { n: nGroups })
      label = `${ch} · ${gr}`
    }
  } else if (nChannels > 0 && nGroups === 0) {
    label = `${nChannels} ${ruPlural(nChannels, 'канал', 'канала', 'каналов')}`
  } else if (nGroups > 0 && nChannels === 0) {
    label = `${nGroups} ${ruPlural(nGroups, 'группа', 'группы', 'групп')}`
  } else {
    label = `${nChannels} ${ruPlural(nChannels, 'канал', 'канала', 'каналов')} · ${nGroups} ${ruPlural(nGroups, 'группа', 'группы', 'групп')}`
  }

  let mode = 'groups'
  if (wantBotsAlso) {
    mode = 'all'
    label = `${label} — ${tt('admin.broadcast_ui.include_bot_users_short')}`
  }
  return {
    mode,
    ids: mergedIds,
    recipientLabel: label,
  }
}

async function openBcConfirmModal() {
  bcSendQuoteError.value = ''
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
    const reqN = Number(q?.requested_chat_ids ?? payload.ids.length)
    const resN = Number(q?.n_groups ?? 0)
    if (need > 0 && q?.can_afford === false) {
      bcSendQuoteError.value = tt('admin.broadcast_send.aurum_short', { need, have: Number(q?.spendable_credits || 0) })
      bcSendTimingModalOpen.value = true
      return
    }
    if (payload.ids.length && resN < reqN) {
      bcSendQuoteError.value = tt('admin.broadcast_send.some_chats_filtered', {
        requested: reqN,
        resolved: resN,
      })
      if (resN <= 0) {
        bcSendTimingModalOpen.value = true
        return
      }
    } else {
      bcSendQuoteError.value = ''
    }
    if (resN > 0 && (payload.mode === 'groups' || payload.mode === 'all')) {
      const nCh = payload.ids.filter((id) =>
        (bcBroadcastChannels.value || []).some((c) => bcNormalizeChatId(c) === Number(id)),
      ).length
      const nGr = Math.max(0, resN - nCh)
      if (localeIsEn()) {
        const parts = []
        if (nCh > 0) {
          parts.push(
            nCh === 1
              ? tt('admin.broadcast_send.en_channel_one', { n: nCh })
              : tt('admin.broadcast_send.en_channel_other', { n: nCh }),
          )
        }
        if (nGr > 0) {
          parts.push(
            nGr === 1
              ? tt('admin.broadcast_send.en_group_one', { n: nGr })
              : tt('admin.broadcast_send.en_group_other', { n: nGr }),
          )
        }
        bcConfirmRecipientLabel.value = parts.join(' · ') || payload.recipientLabel
      } else {
        const parts = []
        if (nCh > 0) parts.push(`${nCh} ${ruPlural(nCh, 'канал', 'канала', 'каналов')}`)
        if (nGr > 0) parts.push(`${nGr} ${ruPlural(nGr, 'группа', 'группы', 'групп')}`)
        bcConfirmRecipientLabel.value = parts.join(' · ') || payload.recipientLabel
      }
    }
    bcConfirmQuoteTokens.value = need
    bcConfirmModalOpen.value = true
  } catch (e) {
    bcSendQuoteError.value = String(e?.body?.detail || e?.message || tt('admin.broadcast_send.quote_failed'))
    bcSendTimingModalOpen.value = true
  } finally {
    bcConfirmLoading.value = false
  }
}

async function submitBcConfirmedSend() {
  const bid = Number(bcSelectedId.value || 0)
  if (!bid) return
  const okPin = await requestPinIfNeeded('broadcast')
  if (!okPin) {
    if (shouldAskPinForAction('broadcast')) alert(tt('admin.broadcast_send.pin_required'))
    return
  }
  bcConfirmSending.value = true
  try {
    await persistCurrentBroadcast()
    const sendPayload = bcConfirmBuildPayload()
    if (!sendPayload) {
      throw new Error(tt('admin.broadcast_ui.nothing_selected'))
    }
    const chatIdsPayload =
      sendPayload.mode === 'groups' || sendPayload.mode === 'all' ? sendPayload.ids : []
    if (bcSendTimingMode.value === 'scheduled') {
      const tz =
        typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Moscow' : 'Europe/Moscow'
      await fetch(() =>
        api.adminBroadcastSchedule(bid, sendPayload.mode, chatIdsPayload, {
          scheduledAt: new Date(String(bcSendScheduleAtLocal.value || '')).toISOString(),
          timezone: tz,
          keepDraftAfter: true,
        }),
      )
      bcDismissBroadcastSendPrefaceOverlays()
      bcSendTimingModalOpen.value = false
      await loadRecentSendEvents({ silent: true })
      await closeQuickBroadcastDraft()
      alert(tt('admin.broadcast_send.schedule_ok'))
      return
    }
    bcDismissBroadcastSendPrefaceOverlays()
    const sendTargetKind =
      sendPayload.mode === 'users'
        ? 'users'
        : sendPayload.mode === 'groups'
          ? 'groups'
          : sendPayload.mode === 'all'
            ? 'all'
            : 'mixed'
    upsertBroadcastInList({ id: bid, status: 'sending' })
    await startBroadcastProgressPolling(bid, sendTargetKind)
    await fetch(() =>
      api.adminBroadcastSend(bid, sendPayload.mode, chatIdsPayload, {
        keepDraftAfter: true,
      }),
    )
    bcSaveLocalSnapshot()
    try {
      meAdminProfile.value = await api.me()
    } catch {
      //
    }
  } catch (e) {
    if (bcSendTimingMode.value === 'scheduled') {
      alert(String(e?.body?.detail || e?.message || tt('admin.broadcast_send.schedule_failed')))
    } else {
      bcSendModalState.value = 'failed'
      bcSendModalText.value = String(e?.body?.detail || e?.message || tt('admin.broadcast_send.send_failed'))
      stopBroadcastProgressPolling()
    }
  } finally {
    bcConfirmSending.value = false
  }
}

async function openQuickAutopost() {
  await openBcCampaignUxList()
}

/** Полная серверная админка (все вкладки). */
const meAdminProfile = ref(null)
const {
  pinGateOpen,
  pinGateInput,
  pinGateError,
  pinGateBusy,
  requestPinIfNeeded,
  submitPinGate,
  cancelPinGate,
} = useSecurityPinGate(() => Number(meAdminProfile.value?.telegram_id || 0))
function applyAdminMeSubscription(next) {
  meAdminProfile.value = next
}
const showFullAdminShell = computed(() => {
  const m = meAdminProfile.value
  return !!(m && hasFullAdminRights(m))
})

/** Полный админ: только галка «в личку всем активным пользователям бота», без групп/каналов (target users). */
const bcSendBotsDmOnlyEligible = computed(() => {
  if (!showFullAdminShell.value || !bcAdminIncludeBotRecipients.value) return false
  if (Number(bcSelectedTargetsCount.value || 0) > 0) return false
  if (bcSendTargetChannels.value || bcSendTargetGroups.value) return false
  return true
})

const bcCanProceedSendTargets = computed(() => {
  if (bcSendBotsDmOnlyEligible.value) return true
  if (bcSendTargetChannels.value && bcActiveSendChannelIds.value.length > 0) return true
  if (bcSendTargetGroups.value && bcActiveSendGroupIds.value.length > 0) return true
  return false
})

function bcToggleSendTargetChannels() {
  bcSendTargetChannels.value = !bcSendTargetChannels.value
  if (!bcSendTargetChannels.value) bcSelectedChannelIds.value = []
}

function bcToggleSendTargetGroups() {
  bcSendTargetGroups.value = !bcSendTargetGroups.value
  if (!bcSendTargetGroups.value) bcSelectedGroupIds.value = []
}
/** Фактический базовый URL API в WebView (для подсказки при «мониторинг не загрузился»). */
const guardApiBaseEffective = computed(() => {
  if (typeof window === 'undefined') return ''
  const a = String(window.__GUARD_API_BASE_EFFECTIVE__ || window.__GUARD_API_BASE__ || '').trim()
  return a || ''
})
/** Premium без полных прав (тариф). */
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
/** Владелец Free/Premium без серверной админки; не путать с делегированным только рассылкой. */
const isOwnerCabinet = computed(() => {
  if (isDelegatedFreeBroadcastCabinet.value) return false
  const m = meAdminProfile.value
  if (!m || hasFullAdminRights(m)) return false
  return true
})
/** Личная «статистика защиты / партнёрка»: кабинет владельца или полный админ с Premium. */
const showPersonalPartnerOverview = computed(() => {
  if (isOwnerCabinet.value) return true
  const m = meAdminProfile.value
  return !!(showFullAdminShell.value && m && m.is_premium)
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
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.save_failed')))
  } finally {
    delegatePayerSaving.value = false
  }
}

async function submitAurumTransferToDelegate() {
  const tg = Number(String(aurumTransferToDelegateTg.value || '').trim())
  const amt = Number(String(aurumTransferToDelegateAmt.value || '').replace(',', '.'))
  if (!tg || tg <= 0 || !Number.isFinite(amt) || amt < 0.01) {
    alert(tt('admin.dlg.transfer_fill'))
    return
  }
  aurumTransferLoading.value = true
  try {
    const r = await fetch(() => api.billingAurumTransferToDelegate(tg, amt))
    alert(tt('admin.dlg.transferred', { n: Number(r?.transferred ?? amt) }))
    aurumTransferToDelegateAmt.value = ''
    meAdminProfile.value = await api.me()
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.transfer_failed')))
  } finally {
    aurumTransferLoading.value = false
  }
}

/** Общие ограничения рассылки (только группы, без «в боты» как у полного админа). */
const isBroadcastShellLite = computed(
  () => isOwnerCabinet.value || isDelegatedFreeBroadcastCabinet.value,
)
/** Кампании автопоста и плашка-памятка: полный админ + Premium + делегированный кабинет рассылки. */
const showAutopostCampaignsUi = computed(
  () => showFullAdminShell.value || isBroadcastShellLite.value,
)
const plActivitySummary = ref(null)
const plActivityBreakdown = ref(null)
const plActivityJournal = ref([])
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
  male_pct: 0,
  female_pct: 0,
  known_total: 0,
  audience_total: 0,
  is_estimate: true,
})
const partnerAudienceGenderLastValid = ref({
  male: 0,
  female: 0,
  unknown: 0,
  male_pct: 0,
  female_pct: 0,
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
    showPartnerGroupsModal.value ||
    showPartnerJoinsModal.value ||
    showPartnerHourlyModal.value ||
    showPartnerHourlyChatPicker.value ||
    showPartnerSlotDetailModal.value ||
    showPartnerSegmentModal.value,
)
const partnerSegmentModalTab = ref('joins')
const partnerSegmentModalTitle = computed(() =>
  partnerSegmentModalTab.value === 'joins'
    ? tt('admin.partner_ui.segment_title_joins')
    : tt('admin.partner_ui.segment_title_spam'),
)
const partnerJoinsPeriodSummary = computed(() =>
  tt('admin.partner_ui.joins_period_line', {
    joins: Number(partnerHourlyData.value?.totals?.joins || 0),
    events: Number(partnerHourlyData.value?.totals?.events || 0),
  }),
)
const partnerJournalDoneKeys = ref(new Set())
const PARTNER_HOURLY_PRESET_DEFS = [
  { id: '24h', hours: 24 },
  { id: '7d', hours: 24 * 7 },
  { id: '30d', hours: 24 * 30 },
  { id: '6m', hours: 24 * 183 },
  { id: '1y', hours: 24 * 365 },
]
const PARTNER_HOURLY_PRESETS = computed(() =>
  PARTNER_HOURLY_PRESET_DEFS.map((d) => ({
    id: d.id,
    label: tt(`admin.partner_presets.hourly_${d.id}`),
    hours: d.hours,
  })),
)

function partnerSlotRowMeta(row) {
  return tt('admin.partner_ui.slot_joined_events', {
    joins: Number(row?.joins || 0),
    events: Number(row?.events || 0),
  })
}

function partnerNormalizeAction(action) {
  const a = String(action || '').toLowerCase()
  if (a.includes('observe') || a.includes('замеч')) return 'observe'
  if (a.includes('ban')) return 'ban'
  if (a.includes('mute') || a.includes('restrict')) return 'mute'
  return 'delete'
}

function partnerActionLabel(action) {
  const key = partnerNormalizeAction(action)
  if (key === 'ban') return tt('admin.journal.action_ban')
  if (key === 'mute') return tt('admin.journal.action_mute')
  if (key === 'observe') return tt('admin.journal.action_observe')
  return tt('admin.journal.action_delete')
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
  const t = String(partnerSlotDetailTitle.value || '').toLowerCase()
  if (t.includes('спам') || t.includes('spam')) {
    return rows.filter((m) => partnerIsSpamReason(m.reason))
  }
  return rows
})

function partnerReasonLabel(reason) {
  const raw = String(reason || '').trim().toLowerCase()
  if (!raw) return '—'
  const base = raw.replace(/_newbie$/i, '')
  const path = `cabinet_stats.reasons.${base}`
  if (te(path)) return tt(path)
  const pathRaw = `cabinet_stats.reasons.${raw}`
  if (te(pathRaw)) return tt(pathRaw)
  return raw.replace(/_/g, ' ')
}

async function loadPartnerLiteActivity() {
  const to0 = new Date()
  const from0 = new Date()
  from0.setHours(0, 0, 0, 0)
  const [s, b, j, jr] = await Promise.all([
    api.activitySummary(),
    api.activityBreakdown('today', 'all').catch(() => null),
    fetchSilent(() => api.activityJournal(null, 150, from0.toISOString(), to0.toISOString())).catch(() => ({ items: [] })),
    api.ownerJoinReportSettings().catch(() => ({ periods: [] })),
  ])
  plActivitySummary.value = s
  plActivityBreakdown.value = b
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
    alert(tt('admin.dlg.join_report_saved'))
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.join_report_save_failed')))
  } finally {
    ownerJoinReportSaving.value = false
  }
}

async function partnerQuickUnmute(ev) {
  const chatId = Number(ev?.chat_id || 0)
  const uid = Number(ev?.user_id || 0)
  if (!chatId || !uid) return
  if (!window.confirm(tt('admin.dlg.partner_unmute_confirm', { name: partnerUserLabel(ev) }))) return
  try {
    await fetch(() => api.chatMemberUnmute(chatId, uid))
    partnerJournalDoneKeys.value.add(`mute:${chatId}:${uid}`)
    partnerJournalDoneKeys.value = new Set(partnerJournalDoneKeys.value)
    alert(tt('admin.dlg.partner_unmute_ok'))
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.partner_unmute_fail')))
  }
}

async function partnerQuickUnban(ev) {
  const chatId = Number(ev?.chat_id || 0)
  const uid = Number(ev?.user_id || 0)
  if (!chatId || !uid) return
  if (!window.confirm(tt('admin.dlg.partner_unban_confirm', { name: partnerUserLabel(ev) }))) return
  try {
    await fetch(() => api.chatMemberUnban(chatId, uid))
    partnerJournalDoneKeys.value.add(`ban:${chatId}:${uid}`)
    partnerJournalDoneKeys.value = new Set(partnerJournalDoneKeys.value)
    alert(tt('admin.dlg.partner_unban_ok'))
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.partner_unban_fail')))
  }
}

function partnerQuickObserve(ev) {
  const uid = Number(ev?.user_id || 0)
  if (!uid) return
  alert(tt('admin.dlg.partner_observed', { name: partnerUserLabel(ev) }))
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
        alert(tt('admin.dlg.date_from_after_to'))
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
      const preset = PARTNER_HOURLY_PRESET_DEFS.find((x) => x.id === pid) || PARTNER_HOURLY_PRESET_DEFS[0]
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
      male_pct: 0,
      female_pct: 0,
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
  const fmt = (d) => d.toLocaleDateString(adminLocaleTag(), { day: 'numeric', month: 'short', year: 'numeric' })
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

const PARTNER_HELP_LINE_COUNTS = { chatList: 2, dayCounter: 2, discussion: 2, events: 2, customRange: 2, barScale: 2, tgstatPack: 3 }
const PARTNER_HELP_SLUG = {
  chatList: 'chat_list',
  dayCounter: 'day_counter',
  discussion: 'discussion',
  events: 'events',
  customRange: 'custom_range',
  barScale: 'bar_scale',
  tgstatPack: 'tgstat_pack',
}

function partnerHelpBase(key) {
  const slug = PARTNER_HELP_SLUG[key]
  return slug ? `admin.partner_help.${slug}` : ''
}

function partnerHelpTitleText(key) {
  const base = partnerHelpBase(key)
  return base ? tt(`${base}.title`) : tt('admin.partner_help.help_generic')
}

function partnerHelpLinesFor(key) {
  const base = partnerHelpBase(key)
  const n = PARTNER_HELP_LINE_COUNTS[key] || 0
  if (!base || !n) return []
  return Array.from({ length: n }, (_, i) => tt(`${base}.l${i}`))
}

function partnerHelpBind(key, variant = 'corner') {
  const shortTitle = partnerHelpTitleText(key)
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
    title: shortTitle,
    'aria-label': tt('admin.partner_help.aria', { title: shortTitle }),
    class: [base, pos].filter(Boolean).join(' '),
  }
}

function partnerShowHelp(key) {
  if (!PARTNER_HELP_SLUG[key]) return
  partnerHelpTitle.value = `${tt('admin.partner_help.modal_prefix')}${partnerHelpTitleText(key)}`
  partnerHelpLines.value = partnerHelpLinesFor(key)
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
    .sort((a, b) => String(a?.title || '').localeCompare(String(b?.title || ''), adminLocaleTag()))
  const groups = [...(partnerChatsGrouped.value?.groups || [])]
    .sort((a, b) => String(a?.title || '').localeCompare(String(b?.title || ''), adminLocaleTag()))
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
    return d.toLocaleDateString(adminLocaleTag(), { day: '2-digit', month: 'short' })
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
const ownerHourlyTotalsForStats = computed(() => partnerHourlyData.value?.totals || {})
const ownerModerationSeriesForStats = computed(() => partnerChartSeries.value?.moderation || [])
const ownerStatsPeriodKey = computed(() => {
  if (partnerHourlyUseCustomRange.value) return 'custom'
  const p = String(partnerHourlyPreset.value || '24h')
  if (p === '7d') return '7d'
  if (p === '30d') return '30d'
  if (p === '6m') return '6m'
  if (p === '1y') return '1y'
  return 'today'
})

function onOwnerStatsPeriodChange(payload) {
  const key = String(payload?.key || 'today')
  partnerHourlyUseCustomRange.value = false
  if (key === '7d') partnerHourlyPreset.value = '7d'
  else if (key === '30d') partnerHourlyPreset.value = '30d'
  else if (key === '6m') partnerHourlyPreset.value = '6m'
  else if (key === '1y') partnerHourlyPreset.value = '1y'
  else partnerHourlyPreset.value = '24h'
  void loadPartnerHourlyActivity()
  if (ownerProtectionReportOpen.value && String(premiumAdmSection.value || '') === 'protection') {
    void refreshOwnerProtectionJournal()
  }
}

function _ownerApiPeriodFromStatsKey(key) {
  const k = String(key || 'today')
  if (k === 'custom') return '30d'
  if (k === '6m') return '180d'
  if (k === '1y') return '365d'
  if (k === '7d' || k === '30d' || k === 'today') return k
  return 'today'
}

function _ownerJournalIsoRange(periodKey) {
  const to = new Date()
  const k = String(periodKey || 'today')
  if (k === 'custom') {
    if (partnerHourlyUseCustomRange.value) {
      const fromIso = _partnerDayBoundsIso(partnerHourlyDateFrom.value, false)
      const toIso = _partnerDayBoundsIso(partnerHourlyDateTo.value, true)
      if (fromIso && toIso) return { fromTs: fromIso, toTs: toIso }
    }
    const from = new Date(to.getTime() - 30 * 86400000)
    return { fromTs: from.toISOString(), toTs: to.toISOString() }
  }
  if (k === '7d') return { fromTs: new Date(to.getTime() - 7 * 86400000).toISOString(), toTs: to.toISOString() }
  if (k === '30d') return { fromTs: new Date(to.getTime() - 30 * 86400000).toISOString(), toTs: to.toISOString() }
  if (k === '6m') return { fromTs: new Date(to.getTime() - 180 * 86400000).toISOString(), toTs: to.toISOString() }
  if (k === '1y') return { fromTs: new Date(to.getTime() - 365 * 86400000).toISOString(), toTs: to.toISOString() }
  const from = new Date()
  from.setHours(0, 0, 0, 0)
  return { fromTs: from.toISOString(), toTs: to.toISOString() }
}

async function refreshOwnerProtectionJournal() {
  if (!hasInitData.value) return
  const ctx = ownerProtectionReportContext.value || {}
  const scope = ['all', 'own', 'delegated'].includes(String(ctx.scope || 'all')) ? String(ctx.scope) : 'all'
  const chatId = sidOwnerCtx(ctx.chatId)
  const periodKey = String(ownerStatsPeriodKey.value || 'today')
  const apiPeriod = _ownerApiPeriodFromStatsKey(periodKey)
  const { fromTs, toTs } = _ownerJournalIsoRange(periodKey)
  try {
    const [b, j] = await Promise.all([
      fetchSilent(() => api.activityBreakdown(apiPeriod, scope, chatId)),
      fetchSilent(() => api.activityJournal(chatId, 400, fromTs, toTs)),
    ])
    if (b) plActivityBreakdown.value = b
    plActivityJournal.value = Array.isArray(j?.items) ? j.items : []
  } catch {
    //
  }
}

watch(
  () => ({
    open: ownerProtectionReportOpen.value,
    period: ownerStatsPeriodKey.value,
    scope: ownerProtectionReportContext.value?.scope,
    chatId: ownerProtectionReportContext.value?.chatId,
    eligibleLen: (ownerProtectionReportContext.value?.eligibleChatIds || []).length,
    journalSig: (() => {
      const j = ownerProtectionReportContext.value?.journalChatIds
      if (!Array.isArray(j) || !j.length) return ''
      return j.join(',')
    })(),
  }),
  () => {
    if (!ownerProtectionReportOpen.value) return
    if (String(premiumAdmSection.value || '') !== 'protection') return
    void refreshOwnerProtectionJournal()
  },
)

const showCabinetCrownNav = computed(() => {
  if (!isOwnerCabinet.value || showFullAdminShell.value) return false
  const ps = String(premiumAdmSection.value || '')
  if (ps === 'protection') return true
  const t = String(tab.value || '')
  if (t === 'broadcasts' || t === 'subscription') return true
  return false
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
  return Math.round(v).toLocaleString(adminLocaleTag())
}
const partnerAudienceGender = computed(() => {
  const cur = partnerAudienceGenderData.value || {}
  const maleC = Math.max(0, Number(cur?.male || 0))
  const femaleC = Math.max(0, Number(cur?.female || 0))
  const curKnown = Number(cur?.known_total || maleC + femaleC)

  if (partnerHourlyLoading.value) {
    const chats = partnerHourlyData.value?.chats || []
    let audience = Number(cur?.audience_total || 0)
    if (partnerSelectedChatMeta.value) {
      audience = Math.max(audience, Number(partnerSelectedChatMeta.value?.members_count || 0))
    } else {
      audience = Math.max(audience, chats.reduce((acc, c) => acc + Number(c?.members_count || 0), 0))
    }
    return {
      malePct: 0,
      femalePct: 0,
      audience,
      maleCount: 0,
      femaleCount: 0,
      unknownCount: 0,
      knownTotal: 0,
      isEstimate: true,
    }
  }

  if (curKnown <= 0 || maleC + femaleC <= 0) {
    const chats = partnerHourlyData.value?.chats || []
    let audience = Number(cur?.audience_total || 0)
    if (partnerSelectedChatMeta.value) {
      audience = Math.max(audience, Number(partnerSelectedChatMeta.value?.members_count || 0))
    } else {
      audience = Math.max(audience, chats.reduce((acc, c) => acc + Number(c?.members_count || 0), 0))
    }
    const unknownCount = Math.max(0, Number(cur?.unknown || 0))
    return {
      malePct: 0,
      femalePct: 0,
      audience,
      maleCount: 0,
      femaleCount: 0,
      unknownCount,
      knownTotal: 0,
      isEstimate: !!cur?.is_estimate,
    }
  }

  const src = curKnown > 0 ? cur : partnerAudienceGenderLastValid.value || cur
  const maleCount = Number(src?.male || 0)
  const femaleCount = Number(src?.female || 0)
  const namedSum = maleCount + femaleCount
  let malePct = 0
  let femalePct = 0
  if (namedSum > 0) {
    malePct = Math.max(0, Math.min(100, (maleCount / namedSum) * 100))
    femalePct = Math.max(0, Math.min(100, 100 - malePct))
  } else {
    const malePctRaw = Number(src?.male_pct || 0)
    const femalePctRaw = Number(src?.female_pct || 0)
    malePct = Math.max(0, Math.min(100, malePctRaw || 0))
    femalePct = Math.max(0, Math.min(100, femalePctRaw || 0))
  }
  const chats = partnerHourlyData.value?.chats || []
  let audience = Number(src?.audience_total || 0)
  if (partnerSelectedChatMeta.value) {
    audience = Math.max(audience, Number(partnerSelectedChatMeta.value?.members_count || 0))
  } else {
    audience = Math.max(audience, chats.reduce((acc, c) => acc + Number(c?.members_count || 0), 0))
  }
  const unknownCount = Number(src?.unknown || 0)
  const knownTotal = Number(src?.known_total || maleCount + femaleCount)
  return {
    malePct: Math.round(malePct * 10) / 10,
    femalePct: Math.round(femalePct * 10) / 10,
    audience,
    maleCount,
    femaleCount,
    unknownCount,
    knownTotal,
    isEstimate: !!src?.is_estimate,
  }
})
watch(ownerProtectionStatsMode, (m) => {
  if (String(m || '') === 'growth') ownerProtectionReportOpen.value = false
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
  partnerSlotDetailTitle.value = title || tt('admin.partner_ui.slot_fallback_title')
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
      x.toLocaleString(adminLocaleTag(), { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
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

function closeOwnerProtectionReport() {
  ownerProtectionReportOpen.value = false
}

/** Telegram chat id в контексте отчёта (строка, без NaN при длинных id). */
function sidOwnerCtx(v) {
  if (v == null || v === '') return null
  const s = String(v).trim()
  if (!/^-?\d+$/.test(s)) return null
  return s
}

function onOwnerProtectionReportContextChange(next) {
  const scope = String(next?.scope || 'all')
  ownerProtectionReportContext.value = {
    scope: ['all', 'own', 'delegated'].includes(scope) ? scope : 'all',
    chatId: sidOwnerCtx(next?.chatId),
    chatTitle: String(next?.chatTitle || ''),
    journalChatIds: Array.isArray(next?.journalChatIds)
      ? next.journalChatIds.map((x) => sidOwnerCtx(x)).filter(Boolean)
      : null,
    eligibleChatIds: Array.isArray(next?.eligibleChatIds)
      ? next.eligibleChatIds.map((x) => sidOwnerCtx(x)).filter(Boolean)
      : [],
  }
}

function partnerJournalActionHidden(ev, kind) {
  const chatId = Number(ev?.chat_id || 0)
  const uid = Number(ev?.user_id || 0)
  return partnerJournalDoneKeys.value.has(`${kind}:${chatId}:${uid}`)
}

const ownerProtectionChatSharingMap = computed(() => {
  const map = new Map()
  const rows = Array.isArray(plActivityBreakdown.value?.chats)
    ? plActivityBreakdown.value.chats
    : Array.isArray(partnerHourlyData.value?.chats)
      ? partnerHourlyData.value.chats
      : []
  for (const row of rows) {
    const del = !!(row?.is_delegated || row?.is_shared)
    const ids = Array.isArray(row?.moderation_chat_ids) && row.moderation_chat_ids.length
      ? row.moderation_chat_ids.map((x) => sidOwnerCtx(x)).filter(Boolean)
      : [sidOwnerCtx(row?.id)].filter(Boolean)
    for (const id of ids) map.set(id, del)
  }
  return map
})
const ownerProtectionChatIdByTitle = computed(() => {
  const m = new Map()
  const rows = Array.isArray(plActivityBreakdown.value?.chats)
    ? plActivityBreakdown.value.chats
    : Array.isArray(partnerHourlyData.value?.chats)
      ? partnerHourlyData.value.chats
      : []
  for (const row of rows) {
    const cid = sidOwnerCtx(row?.id)
    const title = String(row?.title || '').trim().toLowerCase()
    if (cid && title) m.set(title, cid)
  }
  return m
})
function _moderationPhysicalSetsFromBreakdown(bd) {
  const own = new Set()
  const delegated = new Set()
  const rows = Array.isArray(bd?.chats) ? bd.chats : []
  for (const row of rows) {
    const del = !!(row?.is_delegated || row?.is_shared)
    const ids = Array.isArray(row?.moderation_chat_ids) && row.moderation_chat_ids.length
      ? row.moderation_chat_ids.map((x) => sidOwnerCtx(x)).filter(Boolean)
      : [sidOwnerCtx(row?.id)].filter(Boolean)
    for (const id of ids) {
      if (del) delegated.add(id)
      else own.add(id)
    }
  }
  return { own, delegated, hasIds: own.size + delegated.size > 0 }
}

const ownerProtectionReportEvents = computed(() => {
  const list = (plActivityJournal.value || []).slice(0, 400)
  const ctx = ownerProtectionReportContext.value || {}
  const scope = String(ctx.scope || 'all')
  const eligible = new Set((ctx.eligibleChatIds || []).map((x) => sidOwnerCtx(x)).filter(Boolean))
  const targetKey = sidOwnerCtx(ctx.chatId) || (eligible.size === 1 ? Array.from(eligible)[0] : '')
  const sharing = ownerProtectionChatSharingMap.value
  const titleToId = ownerProtectionChatIdByTitle.value
  const phys = _moderationPhysicalSetsFromBreakdown(plActivityBreakdown.value)
  const jids = ctx.journalChatIds
  const bdRows = Array.isArray(plActivityBreakdown.value?.chats) ? plActivityBreakdown.value.chats : []
  const breakdownRowForTarget = bdRows.find((r) => sidOwnerCtx(r?.id) === targetKey) || null
  const breakdownModerationIds = breakdownRowForTarget && Array.isArray(breakdownRowForTarget.moderation_chat_ids)
    && breakdownRowForTarget.moderation_chat_ids.length
    ? breakdownRowForTarget.moderation_chat_ids.map((x) => sidOwnerCtx(x)).filter(Boolean)
    : []
  return list.filter((ev) => {
    const titleKey = String(ev?.chat_title || '').trim().toLowerCase()
    const cidStr = sidOwnerCtx(ev?.chat_id) || (titleKey ? titleToId.get(titleKey) : null)
    if (!cidStr) return false
    if (targetKey) {
      const allow = new Set()
      if (Array.isArray(jids) && jids.length) for (const x of jids) {
        const k = sidOwnerCtx(x)
        if (k) allow.add(k)
      }
      allow.add(targetKey)
      for (const x of breakdownModerationIds) allow.add(x)
      return allow.has(cidStr)
    }
    // Не фильтруем по eligibleChatIds при «все чаты»: /api/activity/journal уже ограничен доступными чатами.
    if (scope === 'own') {
      if (phys.hasIds) return phys.own.has(cidStr)
      return !sharing.get(cidStr)
    }
    if (scope === 'delegated') {
      if (phys.hasIds) return phys.delegated.has(cidStr)
      return !!sharing.get(cidStr)
    }
    return true
  })
})
const ownerProtectionReportHint = computed(() => {
  const ctx = ownerProtectionReportContext.value || {}
  const eligible = (ctx.eligibleChatIds || []).map((x) => sidOwnerCtx(x)).filter(Boolean)
  const targetKey = sidOwnerCtx(ctx.chatId) || (eligible.length === 1 ? eligible[0] : '')
  if (targetKey) {
    return tt('admin.owner_report.hint_single_chat', { title: ctx.chatTitle || `#${targetKey}` })
  }
  if (ctx.scope === 'own') return tt('admin.owner_report.hint_scope_own')
  if (ctx.scope === 'delegated') return tt('admin.owner_report.hint_scope_delegated')
  return tt('admin.owner_report.hint_scope_all')
})
const ownerProtectionReportPeriodLabel = computed(() => {
  const k = String(ownerStatsPeriodKey.value || 'today')
  const keyI18n =
    k === 'today'
      ? 'period_today'
      : k === '7d'
        ? 'period_7d'
        : k === '30d'
          ? 'period_30d'
          : k === '6m'
            ? 'period_6m'
            : k === '1y'
              ? 'period_1y'
              : k === 'custom'
                ? 'period_custom'
                : 'period_fallback'
  return tt(`admin.owner_report.${keyI18n}`)
})
const ownerProtectionReportDeletedCount = computed(() => {
  const n = Number(plActivityBreakdown.value?.total_deleted ?? NaN)
  if (Number.isFinite(n)) return n
  return Number(plActivitySummary.value?.today?.deleted || 0)
})
function ownerProtectionReportTimeLabel(iso) {
  if (!iso) return '—'
  const dt = new Date(iso)
  const loc = locale.value === 'en' ? 'en-US' : 'ru-RU'
  if (Number.isNaN(dt.getTime())) {
    const s = String(iso)
    const m = s.match(/(\d{2}):(\d{2})/)
    return m ? `${m[1]}:${m[2]}` : s
  }
  if (String(ownerStatsPeriodKey.value || 'today') !== 'today') {
    return dt.toLocaleString(loc, {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
  }
  return dt.toLocaleTimeString(loc, {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

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
const bcEditTitle = ref('')
const bcEditBodyHtml = ref('')
const bcLinkModalOpen = ref(false)
const bcEditorHintOpen = ref(false)
const bcEditorHintText = ref('')
const bcLinkUrl = ref('')
const bcLinkRange = ref(null)

function bcEditorShowHint(message) {
  const msg = String(message || '').trim()
  if (!msg) return
  bcEditorHintText.value = msg
  bcEditorHintOpen.value = true
}
const bcEmojiPickerReady = ref(false)
const bcEditorOpen = ref(false)
const bcSavedTick = ref(false)
const bcFormatState = ref({
  bold: false,
  italic: false,
  underline: false,
  strike: false,
  spoiler: false,
  link: false,
  quote: false,
})
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
/** Тихое автообновление статистики одноразовой рассылки (bcRecentStatsModalOpen) и экрана «отправлено». */
const bcStatsPollTimer = ref(null)
const bcSendResultPollTimer = ref(null)
/** Быстрые догрузки метрик после отправки / открытия статистики */
const bcStatsPulseTimers = ref([])
const BC_STATS_POLL_MS = 1500
const BC_STATS_PULSE_DELAYS_MS = [0, 600, 1200, 2500, 4500, 7000]
/** Тихое автообновление списка «последние рассылки» пока открыта вкладка broadcasts. */
const bcBroadcastsListPollTimer = ref(null)
/** Тихий опрос статистики в модалке «Статистика рассылки». */
const bcStatsModalPollTimer = ref(null)
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
/** Лимит текста без медиа (Telegram). С медиа — подпись до 1024 символов HTML, остаток отдельными сообщениями. */
const BC_BROADCAST_BODY_MAX_CHARS = 4096
const BC_BROADCAST_CAPTION_MAX_CHARS = 1024
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
/** Новый полноэкранный UX автокампаний */
const bcCampaignUxOpen = ref(false)
const bcCampaignUxScreen = ref('list') // list | wizard | review | success | manage | stats | progress | postEditor
const bcCampaignUxStep = ref(1) // 1..4
const bcCampaignUxBusy = ref(false)
const bcCampaignUxManageId = ref(0)
const bcCampaignUxStatsPeriod = ref(7)
const bcCampaignUxStatsData = ref(null)
const bcCampaignUxStatsDeliverModalOpen = ref(false)
const bcCampaignUxRecipientPickerOpen = ref(false)
const bcCampaignUxRecipientPickerKind = ref('groups')
const bcCampaignUxRecipientQuery = ref('')
const bcCampaignUxRecipientsModalOpen = ref(false)
const bcCampaignUxCampaignPostsModalOpen = ref(false)
const bcCampaignUxCampaignPostsModalItems = ref([])
const bcCampaignUxCampaignPostsModalHeading = computed(() => {
  const n = (bcCampaignUxCampaignPostsModalItems.value || []).length
  if (n <= 1) return tt('admin.bc_campaign.modal_single_post_title')
  return tt('admin.bc_campaign.modal_posts_title')
})
const bcCampaignUxRemovingPostBid = ref(0)
/** id черновика → превью первого медиа для модалки «Посты кампании» */
/** Снимок последнего слота отправки автокампании (экран «Процесс отправки»). */
const bcCampaignUxProgressSnapshot = ref(null)
let bcCampaignUxProgressPollTimer = null
/** Тихое обновление экранов автокампании: статистика, список кампаний. */
let bcCampaignUxStatsPollTimer = null
let bcCampaignUxCampaignSyncPollTimer = null

const bcCampaignUxEditingCampaignId = ref(0)
const bcCampaignUxPostEditorId = ref(0)
const bcCampaignUxPostEditorMode = ref('create') // create | edit
const bcCampaignUxPostEditorReturn = ref('wizard')
const bcCampaignUxPostEditorLoading = ref(false)
const bcCampaignUxWizard = ref({
  title: '',
  postIds: [],
  campaignType: 'progress', // progress | rotation | simple
  scheduleMode: 'every_day', // every_day | weekdays | interval
  intervalDays: 1,
  weekdays: [0, 1, 2, 3, 4],
  startDate: '',
  endDate: '',
  sendTime: '09:00',
  timezone: typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Yekaterinburg' : 'Asia/Yekaterinburg',
  postsPerDay: 1,
  spreadInWindow: true,
  windowStart: '09:00',
  windowEnd: '21:00',
  sendWindows: [{ windowStart: '09:00', windowEnd: '21:00', posts: 1 }],
  targetChannels: true,
  targetGroups: true,
  targetBots: false,
  selectedGroups: [],
  selectedChannels: [],
  customDays: '',
})
const bcCampaignUxSuccessInfo = ref({ id: 0, nextAt: '' })

const bcCampaignUxScheduleModalOpen = ref(false)
const bcCampaignUxScheduleCampId = ref(0)
const bcCampaignUxScheduleSavedSig = ref('')
const bcCampaignUxScheduleBusy = ref(false)
const bcCampaignUxScheduleForm = ref({
  scheduleMode: 'every_day',
  intervalDays: 1,
  weekdays: [0, 1, 2, 3, 4],
  startDate: '',
  endDate: '',
  sendTime: '09:00',
  timezone: 'Asia/Yekaterinburg',
  spreadInWindow: true,
  customDays: '',
  sendWindows: [{ windowStart: '09:00', windowEnd: '21:00', posts: 1 }],
})

const bcCampaignUxManageItem = computed(() => {
  const id = Number(bcCampaignUxManageId.value || 0)
  return (bcAutopostCampaigns.value || []).find((c) => Number(c?.id || 0) === id) || null
})
const bcCampaignUxManageDestinations = computed(() => {
  const it = bcCampaignUxManageItem.value
  if (!it) return { usersOnly: false, channels: [], groups: [] }
  return bcCampaignUxDestinationsForCamp(it)
})

/** Ожидаемое число чатов в одном слоте (группы + каналы); для ЛС/ботов — 0, смотри run в API. */
function bcCampaignUxProgressExpectedRecipients() {
  const it = bcCampaignUxManageItem.value
  const d = bcCampaignUxDestinationsForCamp(it)
  if (d.usersOnly) return 0
  return d.channels.length + d.groups.length
}

async function bcCampaignUxRefreshProgressSnapshot() {
  const id = Number(bcCampaignUxManageId.value || 0)
  if (!id) {
    bcCampaignUxProgressSnapshot.value = null
    return
  }
  try {
    const d = await fetchSilent(() => api.adminAutopostCampaignAutopostStats(id, 1))
    const done = Math.max(0, Math.trunc(Number(d?.post_slots_sent_today ?? 0)))
    const total = Math.max(0, Math.trunc(Number(d?.post_slots_planned_today ?? 0)))
    const fail = Math.max(0, Math.trunc(Number(d?.post_slots_with_fail_today ?? 0)))
    bcCampaignUxProgressSnapshot.value = { total, done, fail }
  } catch {
    bcCampaignUxProgressSnapshot.value = { total: 0, done: 0, fail: 0 }
  }
}

function bcCampaignUxStopAuxCampaignPollers() {
  if (bcCampaignUxStatsPollTimer) {
    clearInterval(bcCampaignUxStatsPollTimer)
    bcCampaignUxStatsPollTimer = null
  }
  if (bcCampaignUxCampaignSyncPollTimer) {
    clearInterval(bcCampaignUxCampaignSyncPollTimer)
    bcCampaignUxCampaignSyncPollTimer = null
  }
}

async function bcCampaignUxRefreshStatsQuiet() {
  const id = Number(bcCampaignUxManageId.value || 0)
  if (!id || bcCampaignUxScreen.value !== 'stats' || !bcCampaignUxOpen.value) return
  try {
    const data = await fetchSilent(() =>
      api.adminAutopostCampaignAutopostStats(id, Number(bcCampaignUxStatsPeriod.value || 7) || 7),
    )
    if (data && typeof data === 'object') bcCampaignUxStatsData.value = data
  } catch {
    //
  }
}

function bcCampaignUxStopProgressPolling() {
  if (bcCampaignUxProgressPollTimer) {
    clearInterval(bcCampaignUxProgressPollTimer)
    bcCampaignUxProgressPollTimer = null
  }
}

/** Текст на карточке «Посты» экрана кампании — названия черновиков, без числа постов */
const bcCampaignUxManagePostsCardLabel = computed(() => bcCampaignUxPostsCardLabelForCamp(bcCampaignUxManageItem.value))
const bcCampaignUxManageAurumUi = computed(() => bcCampaignUxManagePeriodAurumBreakdown(bcCampaignUxManageItem.value))
const bcCampaignUxStatsDeliveredOk = computed(() => {
  const d = bcCampaignUxStatsData.value
  if (!d) return 0
  const b = Number(d.bots?.recipient_ok || 0)
  const g = Number(d.groups?.recipient_ok || 0)
  return Math.max(0, Math.trunc(b + g))
})
const bcCampaignUxStatsSortedRuns = computed(() => {
  const rows = [...(bcCampaignUxStatsData.value?.runs || [])]
  rows.sort((a, b) => {
    const ta = Date.parse(String(a?.sent_at || a?.created_at || ''))
    const tb = Date.parse(String(b?.sent_at || b?.created_at || ''))
    return (Number.isFinite(tb) ? tb : 0) - (Number.isFinite(ta) ? ta : 0)
  })
  return rows
})
const bcCampaignUxStatsCtrSub = computed(() => {
  const d = bcCampaignUxStatsData.value
  if (!d) return ''
  const m = String(d.stats_ctr_mode || '').toLowerCase()
  const clicks = fmtIntSpace(Math.max(0, Math.trunc(Number(d.real_clicks_total || 0))))
  const del = fmtIntSpace(bcCampaignUxStatsDeliveredOk.value)
  if (m === 'reach') {
    return tt('admin.broadcast_shell.ctr_sub_reach', {
      delivered: del,
      base: fmtIntSpace(
        Math.max(
          1,
          Math.trunc(Number(d.connected_groups_total || 0)) + Math.trunc(Number(d.connected_bots_total || 0)),
        ),
      ),
    })
  }
  return tt('admin.broadcast_shell.ctr_sub_clicks', { clicks, delivered: del })
})
const bcCampaignUxStatsCtrPct = computed(() => {
  const d = bcCampaignUxStatsData.value
  if (!d) return null
  const p = d.stats_ctr_percent
  if (p != null && Number.isFinite(Number(p))) return clampPct(Number(p))
  const g = Number(d.groups?.ctr || 0)
  return Number.isFinite(g) ? clampPct(g) : null
})

/** Экран «Процесс отправки»: посты за календарный день кампании из /autopost-stats (post_slots_*). */
const bcCampaignAutopostProgressDone = computed(() => {
  const s = bcCampaignUxProgressSnapshot.value
  if (s && typeof s.done === 'number') return Math.max(0, Math.trunc(s.done))
  return 0
})
const bcCampaignAutopostProgressTotal = computed(() => {
  const s = bcCampaignUxProgressSnapshot.value
  if (s && typeof s.total === 'number' && s.total >= 0) return Math.max(0, Math.trunc(s.total))
  return 0
})
const bcCampaignAutopostProgressPct = computed(() => {
  const s = bcCampaignUxProgressSnapshot.value
  if (!s) return 0
  const t = Number(s.total || 0)
  const d = Number(s.done || 0)
  if (t > 0) return clampPct(Math.min(1, d / t) * 100)
  return d > 0 ? 100 : 0
})
const bcCampaignAutopostProgressRingDash = computed(() => {
  const p = bcCampaignAutopostProgressPct.value
  const R = 52
  const C = 2 * Math.PI * R
  const filled = C * (p / 100)
  return `${filled.toFixed(2)} ${C.toFixed(2)}`
})
const bcCampaignAutopostProgressFail = computed(() => {
  const s = bcCampaignUxProgressSnapshot.value
  if (s && typeof s.fail === 'number') return Math.max(0, Math.trunc(s.fail))
  return 0
})
const bcCampaignUxWizardCanNext = computed(() => {
  const w = bcCampaignUxWizard.value
  const botsOk = showFullAdminShell.value && w.targetBots
  if (bcCampaignUxStep.value === 1) return !!String(w.title || '').trim() && Number(w.postIds?.length || 0) > 0
  if (bcCampaignUxStep.value === 2) return ['progress', 'rotation', 'simple'].includes(String(w.campaignType || ''))
  if (bcCampaignUxStep.value === 3) {
    const postsTotal = bcCampaignUxWizardPostsPerDayTotal.value
    if (postsTotal <= 0) return false
    const sd = String(w.startDate || '').trim()
    const ed = String(w.endDate || '').trim()
    if (sd && ed && sd > ed) return false
    return true
  }
  if (bcCampaignUxStep.value === 4) {
    if (botsOk && !w.targetChannels && !w.targetGroups) return true
    if (!w.targetChannels && !w.targetGroups) return false
    if (w.targetChannels && !(w.selectedChannels || []).length) return false
    if (w.targetGroups && !(w.selectedGroups || []).length) return false
    return true
  }
  return true
})
function bcCampaignUxWizardActiveChannelIds() {
  const w = bcCampaignUxWizard.value
  if (!w.targetChannels) return []
  return (w.selectedChannels || []).map((x) => Number(x || 0)).filter((x) => x !== 0)
}
function bcCampaignUxWizardActiveGroupIds() {
  const w = bcCampaignUxWizard.value
  if (!w.targetGroups) return []
  return (w.selectedGroups || []).map((x) => Number(x || 0)).filter((x) => x !== 0)
}
const bcCampaignUxSelectedSummary = computed(() => {
  return {
    channels: bcCampaignUxWizardActiveChannelIds().length,
    groups: bcCampaignUxWizardActiveGroupIds().length,
    bots: bcCampaignUxWizard.value.targetBots ? Number(bcSelectedBotRecipientIds.value?.length || 0) : 0,
  }
})
/** Лимит AURUM за один слот как в broadcast_charge_tokens на бэке. */
const BC_AUTOPOST_SLOT_AURUM_CAP = 2500
/** Согласовано с _AUTOPOST_FIRE_GRACE в autopost_loop.py — слот ещё можно отправить после планового времени. */
const BC_AUTOPOST_SLOT_FIRE_GRACE_MIN = 15
const bcCampaignUxEstimatedCost = computed(() => {
  const s = bcCampaignUxSelectedSummary.value
  return Math.max(0, Math.trunc((s.channels || 0) + (s.groups || 0)))
})
const bcCampaignUxSlotAurumCharge = computed(() =>
  Math.min(BC_AUTOPOST_SLOT_AURUM_CAP, Math.max(0, Math.trunc(Number(bcCampaignUxEstimatedCost.value || 0)))),
)
const bcCampaignUxPeriodQualifiedDays = computed(() => {
  const w = bcCampaignUxWizard.value
  const pad = (n) => String(n).padStart(2, '0')
  const today = new Date()
  let startStr = String(w.startDate || '').trim()
  if (!startStr) {
    startStr = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`
  }
  let sd = bcCampaignUxParseYmdLocal(startStr)
  if (!sd) {
    sd = bcCampaignUxParseYmdLocal(`${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`)
  }
  if (!sd) return 0
  const endRaw = String(w.endDate || '').trim()
  let ed = endRaw ? bcCampaignUxParseYmdLocal(endRaw) : null
  if (!ed) {
    ed = new Date(sd.getFullYear(), sd.getMonth(), sd.getDate())
    ed.setDate(ed.getDate() + 365)
  }
  const sdDay = new Date(sd.getFullYear(), sd.getMonth(), sd.getDate())
  const edDay = new Date(ed.getFullYear(), ed.getMonth(), ed.getDate())
  if (edDay < sdDay) return 0
  const wdSet = bcCampaignUxWizardWeekdaySet()
  if (!wdSet.size) return 0
  let n = 0
  const cur = new Date(sdDay)
  while (cur <= edDay) {
    const pyWd = (cur.getDay() + 6) % 7
    if (wdSet.has(pyWd)) n++
    cur.setDate(cur.getDate() + 1)
  }
  return n
})
const bcCampaignUxPeriodSendingOpenEnded = computed(() => !String(bcCampaignUxWizard.value.endDate || '').trim())
const bcCampaignUxWizardPostsPerDayTotal = computed(() => {
  const w = bcCampaignUxWizard.value
  const rows = Array.isArray(w.sendWindows) ? w.sendWindows.filter((x) => x && typeof x === 'object') : []
  if (rows.length >= 2) {
    let s = 0
    for (const r of rows) {
      s += Math.max(1, Math.min(288, Math.trunc(Number(r.posts || 1))))
    }
    return Math.max(1, Math.min(288, s))
  }
  if (rows.length === 1) {
    return Math.max(1, Math.min(288, Math.trunc(Number(rows[0].posts || w.postsPerDay || 1))))
  }
  return Math.max(1, Math.min(288, Math.trunc(Number(w.postsPerDay || 1))))
})
const bcCampaignUxWizardSlotTimePreview = computed(() => bcCampaignUxSlotPreviewLines(bcCampaignUxWizard.value))
const bcCampaignUxWizardSlotEntries = computed(() => {
  const previews = bcCampaignUxWizardSlotTimePreview.value || []
  const w = bcCampaignUxWizard.value
  const tz = String(w.timezone || 'Europe/Moscow')
  const schedDay = String(w.startDate || '').trim() || bcCampaignUxTodayIsoInTimezone(tz)
  const markPast = bcCampaignUxShouldMarkPastSlotsSkipped(schedDay, tz)
  return previews.map((labels) =>
    (labels || []).map((label) => ({
      label,
      status: bcCampaignUxResolveSlotDisplayStatus(label, {
        scheduleDay: schedDay,
        tz,
        sent: null,
        markPastAsSkipped: markPast,
      }),
    })),
  )
})
const bcCampaignUxScheduleModalSlotTimePreview = computed(() => bcCampaignUxSlotPreviewLines(bcCampaignUxScheduleForm.value))
const bcCampaignUxScheduleModalCamp = computed(() =>
  bcCampaignUxScheduleCampId.value
    ? (bcAutopostCampaigns.value || []).find((c) => Number(c?.id || 0) === Number(bcCampaignUxScheduleCampId.value))
    : null,
)
const bcCampaignUxScheduleModalSlotStatusApplicable = computed(() =>
  bcCampaignUxScheduleFormMatchesSaved(bcCampaignUxScheduleModalCamp.value, bcCampaignUxScheduleForm.value),
)
const bcCampaignUxScheduleModalSlotDay = computed(() => {
  const st = bcCampaignUxScheduleModalCamp.value?.slot_status_today
  return st?.day ? String(st.day) : ''
})
const bcCampaignUxScheduleModalNightDayHint = computed(() => {
  const form = bcCampaignUxScheduleForm.value
  const day = bcCampaignUxScheduleModalSlotDay.value
  if (!day || !form) return ''
  const rows = form.sendWindows || []
  const nightSeg = rows.find((r) => bcCampaignUxWindowCrossesMidnight(r.windowStart, r.windowEnd))
  if (!nightSeg) return ''
  const tz = String(form.timezone || bcCampaignUxScheduleModalCamp.value?.timezone || 'Europe/Moscow')
  const today = bcCampaignUxTodayIsoInTimezone(tz)
  if (!today || today === day) return ''
  const end = String(nightSeg.windowEnd || form.windowEnd || '05:00').slice(0, 5)
  return tt('admin.bc_campaign.schedule_night_day_hint', { day, today, end, tz })
})
const bcCampaignUxScheduleModalBlockHint = computed(() => {
  const st = bcCampaignUxScheduleModalCamp.value?.slot_status_today
  if (!st?.last_block_reason || !bcCampaignUxScheduleModalSlotStatusApplicable.value) return ''
  const reason = String(st.last_block_reason || '').trim()
  if (!reason) return ''
  const extra = st.last_block && typeof st.last_block === 'object' ? st.last_block : {}
  const next = String(st.next_slot_time || '').trim()
  const key = `admin.bc_campaign.schedule_block_${reason}`
  if (te(key)) return tt(key, { next, ...extra })
  return tt('admin.bc_campaign.schedule_block_unknown', { next, reason })
})
const bcCampaignUxScheduleModalStoppedHint = computed(() => {
  const camp = bcCampaignUxScheduleModalCamp.value
  if (!camp || !bcCampaignUxScheduleModalSlotStatusApplicable.value) return ''
  if (bcCampaignRunState(camp) === 'running') return ''
  return tt('admin.bc_campaign.schedule_not_running_hint')
})
const bcCampaignUxScheduleModalSchedulerHint = computed(() => {
  const camp = bcCampaignUxScheduleModalCamp.value
  if (!camp || bcCampaignRunState(camp) !== 'running') return ''
  const sched = camp?.slot_status_today?.scheduler || camp?.autopost_scheduler
  if (!sched || typeof sched !== 'object') return ''
  if (sched.bot_token_configured === false) {
    return tt('admin.bc_campaign.schedule_block_bot_token_missing')
  }
  const runningCampaigns = Number(sched.running_campaigns ?? -1)
  if (runningCampaigns === 0) {
    return tt('admin.bc_campaign.schedule_not_running_hint')
  }
  const ticks = Number(sched.ticks_total || 0)
  if (ticks <= 0 || sched.loop_alive === false) {
    return tt('admin.bc_campaign.schedule_scheduler_not_running')
  }
  return ''
})
const bcCampaignUxScheduleModalSlotEntries = computed(() => {
  const previews = bcCampaignUxScheduleModalSlotTimePreview.value || []
  const camp = bcCampaignUxScheduleModalCamp.value
  const form = bcCampaignUxScheduleForm.value
  const st = camp?.slot_status_today || null
  const statusApplicable = bcCampaignUxScheduleModalSlotStatusApplicable.value
  const campRunning = bcCampaignRunState(camp) === 'running'
  const { sent, skipped } =
    statusApplicable && campRunning && st ? bcCampaignUxScheduleStatusTimeSets(st) : { sent: new Set(), skipped: new Set() }
  const tz = String(form?.timezone || camp?.autopost?.timezone || 'Europe/Moscow')
  const schedDay = String(st?.day || bcCampaignUxScheduleModalSlotDay.value || form?.startDate || bcCampaignUxTodayIsoInTimezone(tz))
  const markPast = campRunning && bcCampaignUxShouldMarkPastSlotsSkipped(schedDay, tz)
  const flatPreview = previews.flat()
  const backendTimes =
    statusApplicable && campRunning && Array.isArray(st?.times) && st.times.length === flatPreview.length
      ? st.times
      : null
  let flatIdx = 0
  return previews.map((labels) =>
    (labels || []).map((previewLabel) => {
      const label = backendTimes ? backendTimes[flatIdx++] : previewLabel
      let status = 'preview'
      if (statusApplicable && campRunning) {
        status = bcCampaignUxResolveSlotDisplayStatus(label, {
          scheduleDay: schedDay,
          tz,
          sent,
          skipped,
          markPastAsSkipped: markPast,
        })
      } else if (statusApplicable) {
        status = 'pending'
      }
      return { label, status }
    }),
  )
})
const bcCampaignUxWizardReviewTimingPreview = computed(() => {
  const w = bcCampaignUxWizard.value
  return bcCampaignUxScheduleSubtitleFromAutopost({
    windowStart: w.windowStart,
    windowEnd: w.windowEnd,
    postsPerDay: bcCampaignUxWizardPostsPerDayTotal.value,
    sendWindows: w.sendWindows,
  })
})
const bcCampaignUxPeriodScheduledSends = computed(() =>
  Math.max(0, Math.trunc(bcCampaignUxPeriodQualifiedDays.value * Math.max(1, Number(bcCampaignUxWizardPostsPerDayTotal.value || 1)))),
)
const bcCampaignUxPeriodAurumEstimate = computed(() =>
  Math.max(0, Math.trunc(bcCampaignUxSlotAurumCharge.value * bcCampaignUxPeriodScheduledSends.value)),
)

const bcCampaignUxPostMap = computed(() => {
  const map = new Map()
  for (const b of broadcasts.value || []) {
    const bid = Number(b?.id || 0)
    if (bid) map.set(bid, b)
  }
  return map
})
const bcCampaignUxWizardPosts = computed(() =>
  (bcCampaignUxWizard.value.postIds || [])
    .map((id) => bcCampaignUxPostMap.value.get(Number(id)))
    .filter(Boolean),
)
const bcCampaignUxRecipientsFiltered = computed(() => {
  const q = String(bcCampaignUxRecipientQuery.value || '').trim().toLowerCase()
  const src = bcCampaignUxRecipientPickerKind.value === 'channels' ? bcBroadcastChannels.value : bcBroadcastGroups.value
  if (!q) return src || []
  return (src || []).filter((c) => String(c?.title || c?.username || bcNormalizeChatId(c)).toLowerCase().includes(q))
})

/** Черновики для ротации «все посты»: не одноразовые; autopost или ещё без scope. */
function bcBroadcastIsAutopostRotationDraft(b) {
  if (String(b?.status || 'draft').toLowerCase() !== 'draft') return false
  const sc = String(b?.cabinet_draft_scope || '').trim().toLowerCase()
  if (sc === 'oneshot') return false
  if (sc === 'autopost') return true
  return b?.cabinet_draft_scope == null || sc === ''
}

function bcCampaignForRecentBroadcast(item) {
  const cid = Number(item?.autopost_campaign_id || 0)
  if (cid > 0) {
    return (bcAutopostCampaigns.value || []).find((c) => Number(c?.id || 0) === cid) || null
  }
  const bid = Number(item?.id || 0)
  if (!bid) return null
  const camps = bcAutopostCampaigns.value || []
  const matches = []
  const seen = new Set()
  const push = (camp) => {
    const id = Number(camp?.id || 0)
    if (!id || seen.has(id)) return
    seen.add(id)
    matches.push(camp)
  }
  for (const camp of camps) {
    const ap = camp?.autopost || {}
    const anchor = Number(camp?.anchor_broadcast_id || ap?.anchor_broadcast_id || 0)
    if (anchor === bid) {
      push(camp)
      continue
    }
    const br = Array.isArray(ap.broadcast_ids) ? ap.broadcast_ids.map((x) => Number(x)) : []
    if (br.some((x) => x === bid)) {
      push(camp)
      continue
    }
    if (ap.use_all_broadcasts && String(item?.cabinet_draft_scope || '').toLowerCase() === 'autopost') {
      push(camp)
    }
  }
  return matches.length === 1 ? matches[0] : null
}

function bcRecentBroadcastKindIsCampaign(item) {
  if (!item) return false
  const lk = String(item.list_kind || '').toLowerCase()
  if (lk === 'oneshot' || lk === 'oneshot_scheduled') return false
  if (Number(item?.autopost_campaign_id || 0) > 0) return true
  if (lk === 'campaign') return true
  if (String(item.cabinet_draft_scope || '').toLowerCase() === 'oneshot') return false
  if (bcCampaignForRecentBroadcast(item)) return true
  if (String(item.cabinet_draft_scope || '').toLowerCase() === 'autopost') return true
  return false
}

function bcRecentBroadcastKindLabel(item) {
  if (!item) return tt('admin.broadcast_shell.recent_kind_oneshot')
  if (String(item?.list_kind || '').toLowerCase() === 'oneshot_scheduled') {
    return tt('admin.broadcast_shell.recent_kind_oneshot_scheduled')
  }
  if (String(item.cabinet_draft_scope || '').toLowerCase() === 'oneshot')
    return tt('admin.broadcast_shell.recent_kind_oneshot')
  if (bcRecentBroadcastKindIsCampaign(item)) return tt('admin.broadcast_shell.recent_kind_campaign')
  return tt('admin.broadcast_shell.recent_kind_oneshot')
}

function bcRecentSendHistoryHasSuccess(h) {
  if (Number(h?.recipient_ok || 0) > 0) return true
  if (Number(h?.bots?.ok || 0) > 0) return true
  if ((h?.groups || []).some((g) => Number(g.ok || 0) > 0)) return true
  return false
}

function bcFormatPerSendEngagementLine(eng) {
  if (!eng || typeof eng !== 'object') return ''
  return tt('admin.bc_campaign.per_send_engagement_line', {
    links: fmtIntSpace(Math.max(0, Number(eng.link_total || 0))),
    buttons: fmtIntSpace(Math.max(0, Number(eng.callback_total || 0))),
    reactions: fmtIntSpace(Math.max(0, Number(eng.reaction_total || 0))),
  })
}

function bcBroadcastRowHasKeyboardButtons(item) {
  const rows = item?.keyboard?.rows
  if (!Array.isArray(rows) || !rows.length) return false
  return rows.some(
    (row) =>
      Array.isArray(row) &&
      row.some((b) => {
        const txt = String(b?.text || '').trim()
        if (!txt) return false
        return !!String(b?.url || b?.web_app_url || '').trim()
      }),
  )
}

function bcBroadcastRowHasHttpLink(item) {
  return /https?:\/\//i.test(String(item?.body_text || ''))
}

function bcBroadcastRowHasTrackables(item) {
  return bcBroadcastRowHasKeyboardButtons(item) || bcBroadcastRowHasHttpLink(item)
}

function bcRecentPulseEntry(bid) {
  const id = Number(bid || 0)
  if (!id) return null
  return bcRecentPulseById.value[id] || null
}

function bcRecentCardPrimaryLabel(item) {
  const lt = String(item?.last_target || '').toLowerCase()
  if (lt === 'channels') return tt('admin.broadcast_shell.recent_metric_channel_reach')
  if (bcBroadcastRowHasTrackables(item)) return tt('admin.broadcast_shell.recent_metric_interactions')
  return tt('admin.broadcast_shell.recent_metric_delivered_runs')
}

function bcRecentCardPrimaryValue(item, pulse) {
  const lt = String(item?.last_target || '').toLowerCase()
  const p = pulse && typeof pulse === 'object' ? pulse : null
  const linkT = Number(p?.real_link_clicks_total || 0)
  const cbT = Number(p?.real_callback_clicks_total || 0)
  if (lt === 'channels') {
    const aud = Number(p?.audience_ok || 0)
    return Math.max(aud, Number(item?.recipient_total || 0))
  }
  if (bcBroadcastRowHasTrackables(item)) return linkT + cbT
  return Number(item?.recipient_ok || 0)
}

async function bcRecentPulseHydrateQuiet() {
  const src = bcRecentBroadcasts.value || []
  const cap = bcShowAllRecentModal.value ? Math.min(120, src.length) : 12
  const ids = src
    .slice(0, cap)
    .filter((b) => !Number(b?.autopost_campaign_id || 0))
    .filter((b) => String(b?.list_kind || '').toLowerCase() !== 'oneshot_scheduled')
    .map((b) => Number(b?.id || 0))
    .filter((x) => x > 0)
  if (!ids.length) return
  const tk = bcBroadcastStatsTargetKindForRecentModal()
  await Promise.all(
    ids.map(async (bid) => {
      try {
        const r = await fetchSilent(() => api.adminBroadcastStats(bid, '', '', '', tk))
        if (!r || typeof r !== 'object') return
        bcRecentPulseById.value = {
          ...bcRecentPulseById.value,
          [bid]: {
            audience_ok: Number(r.audience_ok || 0),
            real_link_clicks_total: Number(r.real_link_clicks_total || 0),
            real_callback_clicks_total: Number(r.real_callback_clicks_total || 0),
          },
        }
      } catch {
        //
      }
    }),
  )
}

function bcCampaignUxPostsPerDayFromAutopost(ap) {
  if (!ap || typeof ap !== 'object') return 1
  const sw = Array.isArray(ap.sendWindows) ? ap.sendWindows.filter((x) => x && typeof x === 'object') : []
  if (sw.length >= 2) {
    let s = 0
    for (const seg of sw) {
      s += Math.max(1, Math.min(288, Math.trunc(Number(seg.posts || 1))))
    }
    return Math.max(1, Math.min(288, s))
  }
  if (sw.length === 1) return Math.max(1, Math.min(288, Math.trunc(Number(sw[0].posts || ap.postsPerDay || 1))))
  return Math.max(1, Math.min(288, Math.trunc(Number(ap.postsPerDay || 1))))
}

function bcCampaignUxScheduleSubtitleFromAutopost(ap) {
  if (!ap || typeof ap !== 'object') return '—'
  const sw = Array.isArray(ap.sendWindows) ? ap.sendWindows.filter((x) => x && typeof x === 'object') : []
  if (sw.length >= 2) {
    return sw
      .map((s) => {
        const a = String(s.windowStart || '').slice(0, 5)
        const b = String(s.windowEnd || '').slice(0, 5)
        const n = Math.max(1, Math.min(288, Math.trunc(Number(s.posts || 1))))
        return `${a}–${b} (${n})`
      })
      .join(' · ')
  }
  if (sw.length === 1) {
    const s = sw[0]
    const a = String(s.windowStart || ap.windowStart || '').slice(0, 5)
    const b = String(s.windowEnd || ap.windowEnd || '').slice(0, 5)
    const n = Math.max(1, Math.min(288, Math.trunc(Number(s.posts || ap.postsPerDay || 1))))
    return `${a}–${b} · ${n} ${tt('admin.bc_campaign.slot_posts_suffix')}`
  }
  const a = String(ap.windowStart || '09:00').slice(0, 5)
  const b = String(ap.windowEnd || '21:00').slice(0, 5)
  return `${a}–${b}`
}

function bcCampaignUxPeriodLabelFromCamp(camp) {
  const ap = camp?.autopost || {}
  const s = String(ap.startDate || '').trim().slice(0, 10)
  const e = String(ap.endDate || '').trim().slice(0, 10)
  if (!s && !e) return tt('admin.bc_campaign.period_open_both_inline')
  if (s && e) return `${s} — ${e}`
  if (s && !e) return tt('admin.bc_campaign.period_from_open', { d: s })
  return tt('admin.bc_campaign.period_until', { d: e })
}

function bcCampaignUxScheduleSegmentsFromAp(ap) {
  const baseWs = String(ap?.windowStart || '09:00').slice(0, 5)
  const baseWe = String(ap?.windowEnd || '21:00').slice(0, 5)
  const basePosts = Math.max(1, Math.min(288, Math.trunc(Number(ap?.postsPerDay || 1))))
  const swRaw = Array.isArray(ap?.sendWindows) ? ap.sendWindows.filter((x) => x && typeof x === 'object') : []
  const out = []
  for (const s of swRaw.slice(0, 24)) {
    out.push({
      windowStart: String(s.windowStart || baseWs).slice(0, 5),
      windowEnd: String(s.windowEnd || baseWe).slice(0, 5),
      posts: Math.max(1, Math.min(288, Math.trunc(Number(s.posts || basePosts)))),
    })
  }
  if (!out.length) {
    out.push({ windowStart: baseWs, windowEnd: baseWe, posts: basePosts })
  }
  return out
}

function bcCampaignUxNormalizeSendWindowRowsFromInput(w) {
  const baseWs = String(w.windowStart || '').trim().slice(0, 5) || '09:00'
  const baseWe = String(w.windowEnd || '').trim().slice(0, 5) || '21:00'
  const fbPosts = Math.max(1, Math.min(288, Math.trunc(Number(w.postsPerDay || 1))))
  const raw = Array.isArray(w.sendWindows) ? w.sendWindows.filter((x) => x && typeof x === 'object') : []
  const rows = []
  for (const r of raw) {
    rows.push({
      windowStart: String(r.windowStart || baseWs).slice(0, 5),
      windowEnd: String(r.windowEnd || baseWe).slice(0, 5),
      posts: Math.max(1, Math.min(288, Math.trunc(Number(r.posts || fbPosts)))),
    })
  }
  if (!rows.length) {
    rows.push({ windowStart: baseWs, windowEnd: baseWe, posts: fbPosts })
  }
  let sum = rows.reduce((a, r) => a + r.posts, 0)
  for (let guard = 0; guard < 50000 && sum > 288; guard++) {
    let cut = false
    for (let i = rows.length - 1; i >= 0; i--) {
      if (rows[i].posts > 1) {
        rows[i].posts -= 1
        cut = true
        break
      }
    }
    if (!cut) break
    sum = rows.reduce((a, r) => a + r.posts, 0)
  }
  return { rows, sum }
}

function bcCampaignUxAutopostTimingPayloadFromRows(w, rows) {
  const sum = rows.reduce((a, r) => a + r.posts, 0)
  const first = rows[0]
  const firstPost = String(first.windowStart || '09:00').slice(0, 5)
  const spread = w.spreadInWindow !== false
  const base = {
    postsPerDay: Math.max(1, Math.min(288, sum)),
    firstPostTime: firstPost,
    windowStart: String(first.windowStart || '09:00').slice(0, 5),
    windowEnd: String(first.windowEnd || '21:00').slice(0, 5),
    spreadInWindow: spread,
  }
  if (rows.length >= 2) {
    return {
      ...base,
      postsPerDay: Math.max(1, Math.min(288, sum)),
      sendWindows: rows.map((r) => ({
        windowStart: r.windowStart,
        windowEnd: r.windowEnd,
        posts: r.posts,
      })),
    }
  }
  return {
    ...base,
    postsPerDay: Math.max(1, Math.min(288, first.posts)),
    sendWindows: [],
  }
}

/** Предпросмотр времени слотов (совпадает с autopost_loop при обычном дневном окне; без учёта перехода TZ). */
function bcParseHmCampaign(s) {
  const parts = String(s || '00:00').trim().split(':')
  const h = Math.max(0, Math.min(23, parseInt(parts[0], 10) || 0))
  const m = Math.max(0, Math.min(59, parseInt(parts[1], 10) || 0))
  return { h, m }
}

function bcHmMinutesCampaign(hm) {
  return hm.h * 60 + hm.m
}

function bcCampaignUxDayWindowMinuteSpan(ws, we) {
  const lo = bcHmMinutesCampaign(bcParseHmCampaign(ws))
  let hi = bcHmMinutesCampaign(bcParseHmCampaign(we))
  if (hi <= lo) hi += 24 * 60
  return { lo, hi }
}

function bcCampaignUxWindowCrossesMidnight(ws, we) {
  const lo = bcHmMinutesCampaign(bcParseHmCampaign(String(ws || '09:00').slice(0, 5)))
  const hi = bcHmMinutesCampaign(bcParseHmCampaign(String(we || '21:00').slice(0, 5)))
  return hi <= lo
}

function bcCampaignUxTodayIsoInTimezone(tzName) {
  const tz = String(tzName || 'Europe/Moscow').trim() || 'Europe/Moscow'
  try {
    return new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
  } catch {
    return ''
  }
}

function bcCampaignUxAddDaysIso(isoDay, addDays) {
  const [y, m, d] = String(isoDay || '').split('-').map((x) => parseInt(x, 10))
  if (!y || !m || !d) return ''
  const dt = new Date(Date.UTC(y, m - 1, d + Math.trunc(Number(addDays) || 0)))
  return dt.toISOString().slice(0, 10)
}

function bcCampaignUxNowHmMinutesInTimezone(tzName) {
  const tz = String(tzName || 'Europe/Moscow').trim() || 'Europe/Moscow'
  try {
    const parts = Object.fromEntries(
      new Intl.DateTimeFormat('en-GB', { timeZone: tz, hour: '2-digit', minute: '2-digit', hour12: false })
        .formatToParts(new Date())
        .filter((p) => p.type !== 'literal')
        .map((p) => [p.type, p.value]),
    )
    return parseInt(parts.hour, 10) * 60 + parseInt(parts.minute, 10)
  } catch {
    return 0
  }
}

/** День уже начался (сегодня или раньше) — прошлые слоты не планируем. */
function bcCampaignUxShouldMarkPastSlotsSkipped(scheduleDayIso, tzName) {
  const day = String(scheduleDayIso || '').trim()
  const today = bcCampaignUxTodayIsoInTimezone(tzName)
  if (!day || !today) return false
  return day <= today
}

function bcCampaignUxResolveSlotDisplayStatus(label, { scheduleDay, tz, sent, skipped, markPastAsSkipped }) {
  const keys = bcCampaignUxSlotLabelMatchKeys(label)
  if (sent && keys.some((k) => sent.has(k))) return 'sent'
  if (skipped && keys.some((k) => skipped.has(k))) return 'skipped'
  const schedDay = String(scheduleDay || '').trim()
  const tzName = String(tz || 'Europe/Moscow')
  if (markPastAsSkipped && schedDay && bcCampaignUxShouldMarkPastSlotsSkipped(schedDay, tzName)) {
    if (bcCampaignUxSlotLabelIsPastGrace(label, schedDay, tzName)) return 'skipped'
  }
  return 'pending'
}

/** Слот прошёл и окно отправки (grace) истекло — показываем «пропущено». */
function bcCampaignUxSlotLabelIsPastGrace(label, scheduleDayIso, tzName, graceMin = BC_AUTOPOST_SLOT_FIRE_GRACE_MIN) {
  const m = String(label || '').trim().match(/^(\d{1,2}):(\d{2})(?:\s\(\+(\d+)\))?$/)
  if (!m || !scheduleDayIso) return false
  const slotDay = bcCampaignUxAddDaysIso(scheduleDayIso, m[3] ? parseInt(m[3], 10) : 0)
  const today = bcCampaignUxTodayIsoInTimezone(tzName)
  if (!slotDay || !today) return false
  if (slotDay < today) return true
  if (slotDay > today) return false
  const slotMin = parseInt(m[1], 10) * 60 + parseInt(m[2], 10)
  return slotMin + graceMin <= bcCampaignUxNowHmMinutesInTimezone(tzName)
}

function bcClampMinCampaign(m, lo, hi) {
  return Math.min(hi, Math.max(lo, m))
}

function bcFireMinutesCampaign(lo, hi, n, spread) {
  const span = hi - lo
  if (n <= 0) return []
  if (n === 1) {
    if (span <= 0) return [lo]
    return [spread ? lo + span / 2 : lo]
  }
  if (span <= 0) return Array(n).fill(lo)
  if (spread) return Array.from({ length: n }, (_, k) => lo + (span * (k + 1)) / n)
  return Array.from({ length: n }, (_, k) => lo + (span * k) / (n - 1))
}

function bcComposeAnchoredMinutesCampaign(lo, hi, n, fpMin) {
  const tFirst = bcClampMinCampaign(fpMin, lo, hi)
  if (n <= 1) return [tFirst]
  const tLo = Math.max(lo, tFirst + 1)
  if (tLo >= hi) return [tFirst]
  const rem = bcFireMinutesCampaign(tLo, hi, n - 1, true)
  return [tFirst, ...rem].sort((a, b) => a - b)
}

function bcMinToHmLabelCampaign(totalMin) {
  const wrap = Math.floor(totalMin / (24 * 60))
  let x = totalMin % (24 * 60)
  if (x < 0) x += 24 * 60
  const hh = Math.floor(x / 60)
  const mm = Math.floor(x % 60)
  const pad = (u) => String(u).padStart(2, '0')
  if (wrap > 0) return `${pad(hh)}:${pad(mm)} (+${wrap})`
  return `${pad(hh)}:${pad(mm)}`
}

function bcPickAnchorSegmentMinuteCampaign(ordered, fpMin) {
  if (!ordered.length) return { idx: 0, anchorInside: fpMin }
  const t0First = ordered[0].lo
  const t1Last = ordered[ordered.length - 1].hi
  if (fpMin <= t0First) return { idx: 0, anchorInside: t0First }
  if (fpMin >= t1Last) {
    const last = ordered[ordered.length - 1]
    return { idx: ordered.length - 1, anchorInside: bcClampMinCampaign(fpMin, last.lo, last.hi) }
  }
  for (let idx = 0; idx < ordered.length; idx++) {
    const { lo, hi } = ordered[idx]
    if (lo <= fpMin && fpMin <= hi) return { idx, anchorInside: bcClampMinCampaign(fpMin, lo, hi) }
  }
  for (let j = 0; j < ordered.length - 1; j++) {
    const t1cur = ordered[j].hi
    const t0next = ordered[j + 1].lo
    if (t1cur < fpMin && fpMin < t0next) return { idx: j + 1, anchorInside: t0next }
  }
  return { idx: 0, anchorInside: t0First }
}

function bcCampaignUxOrderedMinuteSegments(rows) {
  return rows
    .map((seg, iOrig) => {
      const { lo, hi } = bcCampaignUxDayWindowMinuteSpan(seg.windowStart, seg.windowEnd)
      return { iOrig, seg, lo, hi }
    })
    .sort((a, b) => a.lo - b.lo)
}

function bcCampaignUxSlotPreviewByOriginalIndex(form) {
  const spread = form?.spreadInWindow !== false
  const { rows } = bcCampaignUxNormalizeSendWindowRowsFromInput(form || {})
  const out = rows.map(() => [])
  if (!rows.length) return out
  let fpSrc = String(rows[0].windowStart || '09:00').slice(0, 5)
  const fpMin = bcHmMinutesCampaign(bcParseHmCampaign(fpSrc))

  function setLabels(iOrig, mins) {
    const uniq = [...new Set(mins.map((x) => Math.round(x * 1000) / 1000))]
    uniq.sort((a, b) => a - b)
    out[iOrig] = uniq.map((x) => bcMinToHmLabelCampaign(x))
  }

  if (rows.length < 2) {
    const seg = rows[0]
    const { lo, hi } = bcCampaignUxDayWindowMinuteSpan(seg.windowStart, seg.windowEnd)
    const n = Math.max(1, Math.min(288, Math.trunc(Number(seg.posts) || 1)))
    const mins = spread ? bcComposeAnchoredMinutesCampaign(lo, hi, n, fpMin) : bcFireMinutesCampaign(lo, hi, n, false)
    setLabels(0, mins)
    return out
  }

  const ordered = bcCampaignUxOrderedMinuteSegments(rows)
  let anchorIdx = null
  let anchorInside = null
  if (spread) {
    const pick = bcPickAnchorSegmentMinuteCampaign(ordered, fpMin)
    anchorIdx = pick.idx
    anchorInside = pick.anchorInside
  }
  for (let ord_i = 0; ord_i < ordered.length; ord_i++) {
    const ord = ordered[ord_i]
    const n = Math.max(1, Math.min(288, Math.trunc(Number(ord.seg.posts) || 1)))
    let mins
    if (spread && anchorIdx !== null && anchorInside != null && ord_i === anchorIdx) {
      mins = bcComposeAnchoredMinutesCampaign(ord.lo, ord.hi, n, anchorInside)
    } else {
      mins = bcFireMinutesCampaign(ord.lo, ord.hi, n, spread)
    }
    setLabels(ord.iOrig, mins)
  }
  return out
}

function bcCampaignUxScheduleSegmentsSignature(rows, spread = true) {
  const norm = (rows || []).map((r) => ({
    windowStart: String(r.windowStart || '09:00').slice(0, 5),
    windowEnd: String(r.windowEnd || '21:00').slice(0, 5),
    posts: Math.max(1, Math.min(288, Math.trunc(Number(r.posts || 1)))),
  }))
  return JSON.stringify({ rows: norm, spread: spread !== false })
}

function bcCampaignUxSlotLabelMatchKeys(label) {
  const raw = String(label || '').trim()
  const m = raw.match(/^(\d{1,2}):(\d{2})(?:\s\(\+(\d+)\))?$/)
  if (!m) return [raw]
  const hh = String(m[1]).padStart(2, '0')
  const mm = m[2]
  const keys = [`${hh}:${mm}`]
  if (m[3]) keys.push(`${hh}:${mm}+${m[3]}`)
  return keys
}

function bcCampaignUxScheduleStatusTimeSets(st) {
  const sent = new Set()
  const skipped = new Set()
  if (!st || typeof st !== 'object') return { sent, skipped, day: '' }
  const times = Array.isArray(st.times) ? st.times : []
  const addKeys = (set, idx) => {
    const t = times[idx]
    if (!t) return
    for (const k of bcCampaignUxSlotLabelMatchKeys(t)) set.add(k)
  }
  for (const i of st.sent_times || []) {
    for (const k of bcCampaignUxSlotLabelMatchKeys(i)) sent.add(k)
  }
  for (const i of st.skipped_times || []) {
    for (const k of bcCampaignUxSlotLabelMatchKeys(i)) skipped.add(k)
  }
  for (const i of st.sent_indices || []) addKeys(sent, Number(i))
  for (const i of st.skipped_indices || []) addKeys(skipped, Number(i))
  return { sent, skipped, day: String(st.day || '') }
}

function bcCampaignUxScheduleFormMatchesSaved(camp, form) {
  if (!camp || !form) return false
  const ap = camp.autopost || {}
  const savedRows = bcCampaignUxScheduleSegmentsFromAp(ap)
  const { rows: formRows } = bcCampaignUxNormalizeSendWindowRowsFromInput(form)
  const savedSig = bcCampaignUxScheduleSegmentsSignature(savedRows, ap?.spreadInWindow !== false)
  const formSig = bcCampaignUxScheduleSegmentsSignature(formRows, form?.spreadInWindow !== false)
  return savedSig === formSig
}

function bcCampaignUxSlotPreviewLines(form) {
  const byIx = bcCampaignUxSlotPreviewByOriginalIndex(form)
  return byIx.map((labels) => labels || [])
}

function bcCampaignUxScheduleSlotStatusClass(status) {
  if (status === 'sent') return 'text-emerald-400'
  if (status === 'skipped') return 'text-rose-400'
  if (status === 'preview') return 'text-violet-300/90'
  return 'text-slate-200'
}

function bcCampaignUxScheduleSlotStatusTitle(status) {
  if (status === 'sent') return tt('admin.bc_campaign.schedule_slot_sent')
  if (status === 'skipped') return tt('admin.bc_campaign.schedule_slot_skipped')
  if (status === 'preview') return tt('admin.bc_campaign.schedule_slot_preview')
  return tt('admin.bc_campaign.schedule_slot_pending')
}

async function bcCampaignUxBroadcastsResolvedForCamp(camp) {
  if (!camp) return []
  const ap = camp.autopost || {}
  if (ap.use_all_broadcasts) return (broadcasts.value || []).filter((b) => bcBroadcastIsAutopostRotationDraft(b))
  const ids = []
  const brIds = Array.isArray(ap.broadcast_ids) ? ap.broadcast_ids : []
  for (const x of brIds) {
    const v = Math.trunc(Number(x))
    if (v > 0) ids.push(v)
  }
  if (!ids.length) {
    const anchor = Number(camp.anchor_broadcast_id || ap.anchor_broadcast_id || 0)
    if (anchor > 0) ids.push(anchor)
  }
  const uniq = [...new Set(ids)]
  const out = []
  for (const bid of uniq) {
    let row =
      bid > 0 ? (broadcasts.value || []).find((b) => Number(b?.id || 0) === bid) : null
    if (!row && bid > 0) {
      try {
        row = await fetch(() => api.adminBroadcast(bid))
        if (row) upsertBroadcastInList(row)
      } catch {
        row = null
      }
    }
    if (row) out.push(row)
  }
  return out
}

function bcCampaignUxStatusLabel(camp) {
  const s = bcCampaignRunState(camp)
  if (s === 'running') return tt('admin.autopost.status_running')
  if (s === 'paused') return tt('admin.autopost.status_paused')
  return tt('admin.autopost.status_stopped')
}

function bcCampaignUxStatusBadgeClass(camp) {
  const s = bcCampaignRunState(camp)
  if (s === 'running') return 'border border-emerald-400/25 bg-emerald-500/10 text-emerald-300'
  if (s === 'paused') return 'border border-amber-400/30 bg-amber-500/10 text-amber-200'
  return 'border border-rose-400/35 bg-rose-500/12 text-rose-200'
}

function bcCampaignUxListCtrPct(camp) {
  const p = camp?.stats_ctr_percent
  if (p != null && Number.isFinite(Number(p))) return clampPct(Number(p))
  const c = Number(camp?.ctr ?? 0)
  return Number.isFinite(c) ? clampPct(c) : null
}
function bcCampaignUxTodaySent(camp) {
  const rows = Array.isArray(camp?.autopost?.recent_runs) ? camp.autopost.recent_runs : []
  const now = new Date()
  const y = now.getFullYear()
  const m = now.getMonth()
  const d = now.getDate()
  return rows.filter((r) => {
    const dt = new Date(String(r?.created_at || ''))
    return !Number.isNaN(dt.getTime()) && dt.getFullYear() === y && dt.getMonth() === m && dt.getDate() === d
  }).length
}
function bcCampaignUxNearestAt() {
  const now = new Date()
  const w = bcCampaignUxWizard.value
  const sw0 = Array.isArray(w.sendWindows) && w.sendWindows.length ? w.sendWindows[0] : null
  const t0 = sw0?.windowStart || w.windowStart || '09:00'
  const [h, mm] = String(t0 || '09:00').split(':').map((x) => Number(x || 0))
  const dt = new Date(now)
  dt.setHours(Number.isFinite(h) ? h : 9, Number.isFinite(mm) ? mm : 0, 0, 0)
  if (dt.getTime() <= now.getTime()) dt.setDate(dt.getDate() + 1)
  return fmtDateTime(dt.toISOString())
}

function bcCampaignUxParseYmdLocal(ymd) {
  const p = String(ymd || '')
    .trim()
    .split('-')
    .map((x) => Number(String(x || '').trim()))
  if (p.length !== 3) return null
  const [y, mo, da] = p
  if (!Number.isFinite(y) || !Number.isFinite(mo) || !Number.isFinite(da)) return null
  const dt = new Date(y, mo - 1, da)
  if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== da) return null
  return dt
}

function bcCampaignUxWeekdaySetFromAutopost(ap) {
  const mode = String(ap?.scheduleMode || 'every_day')
  if (mode === 'weekdays') {
    const wd = Array.isArray(ap?.weekdays) && ap.weekdays.length ? ap.weekdays.map(Number).filter((x) => x >= 0 && x <= 6) : [0, 1, 2, 3, 4]
    return new Set(wd)
  }
  return new Set([0, 1, 2, 3, 4, 5, 6])
}

function bcCampaignUxQualifiedSendingDaysFromAutopost(ap) {
  const pad = (n) => String(n).padStart(2, '0')
  const today = new Date()
  let startStr = String(ap?.startDate || '').trim()
  if (!startStr) {
    startStr = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`
  }
  let sd = bcCampaignUxParseYmdLocal(startStr)
  if (!sd) {
    sd = bcCampaignUxParseYmdLocal(`${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`)
  }
  if (!sd) return 0
  const endRaw = String(ap?.endDate || '').trim()
  let ed = endRaw ? bcCampaignUxParseYmdLocal(endRaw) : null
  if (!ed) {
    ed = new Date(sd.getFullYear(), sd.getMonth(), sd.getDate())
    ed.setDate(ed.getDate() + 365)
  }
  const sdDay = new Date(sd.getFullYear(), sd.getMonth(), sd.getDate())
  const edDay = new Date(ed.getFullYear(), ed.getMonth(), ed.getDate())
  if (edDay < sdDay) return 0
  const wdSet = bcCampaignUxWeekdaySetFromAutopost(ap)
  if (!wdSet.size) return 0
  let n = 0
  const cur = new Date(sdDay)
  while (cur <= edDay) {
    const pyWd = (cur.getDay() + 6) % 7
    if (wdSet.has(pyWd)) n++
    cur.setDate(cur.getDate() + 1)
  }
  return n
}

function bcCampaignUxScheduledSendsFromAutopost(ap) {
  const ppd = bcCampaignUxPostsPerDayFromAutopost(ap)
  return Math.max(0, Math.trunc(bcCampaignUxQualifiedSendingDaysFromAutopost(ap) * Math.max(1, ppd)))
}

function bcCampaignUxSlotAurumFromAutopost(ap) {
  const ng = Number((ap?.group_chat_ids || []).length || 0)
  const nc = ap?.autopost_channels_disabled ? 0 : Number((ap?.channel_chat_ids || []).length || 0)
  return Math.min(BC_AUTOPOST_SLOT_AURUM_CAP, Math.max(0, Math.trunc(ng + nc)))
}

/** Оценка AURUM за период для сохранённой кампании (как на экране обзора мастера). */
function bcCampaignUxManagePeriodAurumBreakdown(camp) {
  const ap = camp?.autopost
  if (!ap || typeof ap !== 'object') return null
  if (String(ap.autopost_target || 'groups') === 'users') return { usersOnly: true }
  const slot = bcCampaignUxSlotAurumFromAutopost(ap)
  const sends = bcCampaignUxScheduledSendsFromAutopost(ap)
  const openEnded = !String(ap.endDate || '').trim()
  const total = Math.max(0, Math.trunc(slot * sends))
  return { slot, sends, total, openEnded, usersOnly: false }
}

function bcCampaignUxWizardWeekdaySet() {
  const w = bcCampaignUxWizard.value
  const mode = String(w.scheduleMode || 'every_day')
  const wdFromCustom = String(w.customDays || '')
    .split(',')
    .map((x) => Number(String(x || '').trim()))
    .filter((n) => Number.isFinite(n) && n >= 0 && n <= 6)
  if (mode === 'weekdays') return new Set((w.weekdays || []).map(Number).filter((x) => x >= 0 && x <= 6))
  if (mode === 'custom')
    return new Set(wdFromCustom.length ? [...new Set(wdFromCustom)] : [1, 3, 5])
  return new Set([0, 1, 2, 3, 4, 5, 6])
}

function bcCampaignUxSetStartDateTodayFromTz() {
  const w = bcCampaignUxWizard.value
  const tz = String(w.timezone || '').trim()
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  let ymd = ''
  let hm = '09:00'
  try {
    const tzUse = tz || (typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone : 'UTC')
    const parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: tzUse,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).formatToParts(d)
    const gp = (t) => parts.find((x) => x.type === t)?.value || ''
    ymd = `${gp('year')}-${gp('month')}-${gp('day')}`
    hm = `${gp('hour')}:${gp('minute')}`
  } catch {
    ymd = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
    hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  }
  hm = hm.slice(0, 5)
  bcCampaignUxWizard.value = { ...bcCampaignUxWizard.value, startDate: ymd, sendTime: hm }
}

function bcCampaignUxChatTitleFromEligible(chatId) {
  const id = Number(chatId)
  if (!id) return ''
  let row = (bcBroadcastChannels.value || []).find((c) => bcNormalizeChatId(c) === id)
  if (row) {
    const t = String(row?.title || row?.username || '').trim()
    if (t) return t
  }
  row = (bcBroadcastGroups.value || []).find((c) => bcNormalizeChatId(c) === id)
  if (row) {
    const t = String(row?.title || row?.username || '').trim()
    if (t) return t
  }
  return tt('admin.bc_campaign.chat_label_unknown', { id: String(id) })
}

function bcCampaignUxDestinationsIsEmpty(camp) {
  const d = bcCampaignUxDestinationsForCamp(camp)
  if (d.usersOnly) return false
  return !d.channels.length && !d.groups.length
}

function bcCampaignUxDestinationsForCamp(camp) {
  const ap = camp?.autopost || {}
  const usersOnly = String(ap.autopost_target || 'groups') === 'users'
  const chDisabled = !!ap.autopost_channels_disabled
  const channels = chDisabled ? [] : [...new Set((ap.channel_chat_ids || []).map(Number).filter((x) => Number.isFinite(x) && x !== 0))]
  const groups = [...new Set((ap.group_chat_ids || []).map(Number).filter((x) => Number.isFinite(x) && x !== 0))]
  const chLbl = channels.map((cid) => ({ id: cid, label: bcCampaignUxChatTitleFromEligible(cid), kind: 'ch' }))
  const grLbl = groups.map((gid) => ({ id: gid, label: bcCampaignUxChatTitleFromEligible(gid), kind: 'gr' }))
  return { usersOnly, channels: chLbl, groups: grLbl }
}

function bcCampaignUxDestinationsPreviewLines(camp) {
  const d = bcCampaignUxDestinationsForCamp(camp)
  if (d.usersOnly) return tt('admin.bc_campaign.targets_dm_autopost')
  const parts = []
  if (d.channels.length) {
    const tail = d.channels.length > 3 ? '…' : ''
    parts.push(`${tt('admin.bc_campaign.tgt_channels_short')}: ${d.channels.slice(0, 3).map((x) => x.label).join(', ')}${tail}`)
  }
  if (d.groups.length) {
    const tail = d.groups.length > 3 ? '…' : ''
    parts.push(`${tt('admin.bc_campaign.tgt_groups_short')}: ${d.groups.slice(0, 3).map((x) => x.label).join(', ')}${tail}`)
  }
  return parts.join(' · ') || tt('admin.bc_campaign.destinations_fallback')
}

/** Посты, закреплённые за автокампанией (для модалки и проверок). */
function bcCampaignUxBroadcastsForCamp(camp) {
  if (!camp) return []
  const ap = camp.autopost || {}
  if (ap.use_all_broadcasts) {
    return (broadcasts.value || []).filter((b) => bcBroadcastIsAutopostRotationDraft(b))
  }
  const ids = Array.isArray(ap.broadcast_ids) ? ap.broadcast_ids.map((x) => Number(x)).filter((x) => x > 0) : []
  if (ids.length) {
    const seen = new Set()
    const out = []
    for (const id of ids) {
      const b = (broadcasts.value || []).find((bb) => Number(bb?.id || 0) === id)
      if (b && !seen.has(id)) {
        seen.add(id)
        out.push(b)
      }
    }
    return out
  }
  const anchor = Number(camp.anchor_broadcast_id || ap.anchor_broadcast_id || 0)
  if (anchor > 0) {
    const b = (broadcasts.value || []).find((x) => Number(x?.id || 0) === anchor)
    return b ? [b] : []
  }
  return []
}

function bcCampaignUxPostButtonRowsForDisplay(item) {
  if (!item) return []
  const rows = Array.isArray(item.keyboard_rows) && item.keyboard_rows.length
    ? item.keyboard_rows
    : bcKeyboardRowsFromApi(item?.keyboard)
  return (rows || []).filter((row) => Array.isArray(row) && row.some((b) => String(b?.text || '').trim()))
}

function bcCampaignUxOpenRecipientsModal() {
  bcCampaignUxRecipientsModalOpen.value = true
}

function bcCampaignUxCloseRecipientsModal() {
  bcCampaignUxRecipientsModalOpen.value = false
}

function bcCampaignUxCloseCampaignPostsModal() {
  bcCampaignUxCampaignPostsModalOpen.value = false
  bcCampaignUxCampaignPostsModalItems.value = []
  const m = bcCampaignUxPostsModalMedia.value || {}
  for (const k of Object.keys(m)) {
    const entry = m[k]
    if (entry?.previewUrl) revokeBroadcastMediaPreviewUrl(entry.previewUrl)
  }
  bcCampaignUxPostsModalMedia.value = {}
}

async function bcCampaignUxFillCampaignPostsModalMedia() {
  const list = await bcCampaignUxBroadcastsResolvedForCamp(bcCampaignUxManageItem.value)
  bcCampaignUxCampaignPostsModalItems.value = list
  const map = {}
  await Promise.all(
    (list || []).map(async (b) => {
      const bid = Number(b?.id || 0)
      if (!bid) return
      try {
        let rows = Array.isArray(b.media_items) ? b.media_items : []
        if (
          !rows.length &&
          (b.has_media_file ||
            b.telegram_file_id ||
            String(b.media_kind || 'none').toLowerCase() !== 'none')
        ) {
          const full = await fetch(() => api.adminBroadcast(bid))
          rows = Array.isArray(full?.media_items) ? full.media_items : []
        }
        for (const mi of rows) {
          const mk = String(mi.media_kind || '').toLowerCase()
          const mid = Number(mi.id || 0)
          if (!mid) continue
          if (mk.includes('photo') || mk.includes('video') || mk === 'animation') {
            const previewUrl = await fetchAdminBroadcastMediaPreviewUrl(bid, mid)
            map[bid] = {
              previewUrl,
              kind: mk.includes('photo') ? 'photo' : mk.includes('video') ? 'video' : 'animation',
            }
            break
          }
        }
      } catch {
        //
      }
    }),
  )
  bcCampaignUxPostsModalMedia.value = map
}

async function bcCampaignUxOpenCampaignPostsModal() {
  for (const k of Object.keys(bcCampaignUxPostsModalMedia.value || {})) {
    const entry = bcCampaignUxPostsModalMedia.value[k]
    if (entry?.previewUrl) revokeBroadcastMediaPreviewUrl(entry.previewUrl)
  }
  bcCampaignUxPostsModalMedia.value = {}
  bcCampaignUxCampaignPostsModalItems.value = []
  bcCampaignUxCampaignPostsModalOpen.value = true
  try {
    await loadBroadcasts()
  } catch {
    //
  }
  await bcCampaignUxFillCampaignPostsModalMedia()
}

async function bcCampaignUxRemoveBroadcastFromCampaignModal(broadcastId) {
  const bid = Number(broadcastId || 0)
  const camp = bcCampaignUxManageItem.value
  const cid = Number(camp?.id || 0)
  if (!bid || !cid) return
  const ap = camp?.autopost && typeof camp.autopost === 'object' ? { ...camp.autopost } : {}
  if (ap.use_all_broadcasts) {
    window.alert(tt('admin.bc_campaign.modal_posts_rotation_no_remove'))
    return
  }
  const curIds = bcCampaignUxBroadcastsForCamp(camp)
    .map((b) => Number(b?.id || 0))
    .filter((x) => x > 0)
  const nextIds = curIds.filter((x) => x !== bid)
  if (!nextIds.length) {
    window.alert(tt('admin.bc_campaign.modal_posts_need_one'))
    return
  }
  if (!window.confirm(tt('admin.bc_campaign.modal_posts_remove_confirm'))) return
  bcCampaignUxRemovingPostBid.value = bid
  try {
    ap.use_all_broadcasts = false
    ap.broadcast_ids = [...nextIds]
    await fetch(() =>
      api.adminAutopostCampaignPatch(cid, {
        anchor_broadcast_id: nextIds[0],
        autopost: ap,
      }),
    )
    await loadAutopostCampaigns()
    await loadBroadcasts()
    await bcCampaignUxFillCampaignPostsModalMedia()
  } catch (e) {
    window.alert(String(e?.body?.detail || e?.message || tt('admin.autopost.err_save')))
  } finally {
    bcCampaignUxRemovingPostBid.value = 0
  }
}

function bcCampaignUxPostsCountLabelForCamp(camp) {
  if (!camp) return '0'
  const ap = camp.autopost || {}
  if (ap.use_all_broadcasts) return tt('admin.bc_campaign.word_all')
  const resolved = bcCampaignUxBroadcastsForCamp(camp)
  if (resolved.length) return String(resolved.length)
  const ids = [...new Set((Array.isArray(ap.broadcast_ids) ? ap.broadcast_ids : []).map((x) => Number(x)).filter((x) => x > 0))]
  if (ids.length) return String(ids.length)
  const anchor = Number(camp.anchor_broadcast_id || ap.anchor_broadcast_id || 0)
  return anchor > 0 ? '1' : '0'
}

function bcCampaignUxDraftDisplayTitle(row) {
  const s = String(row?.run_title ?? row?.title ?? '').trim()
  if (s) return s
  return tt('admin.broadcast_stats.untitled')
}

function bcCampaignUxPrimaryBroadcastIdForCamp(camp) {
  if (!camp) return 0
  const ap = camp.autopost || {}
  const anchor = Number(camp.anchor_broadcast_id || ap.anchor_broadcast_id || 0)
  if (anchor > 0) return anchor
  const br = Array.isArray(ap.broadcast_ids) ? ap.broadcast_ids : []
  for (const x of br) {
    const id = Number(x)
    if (id > 0) return id
  }
  if (ap.use_all_broadcasts) {
    const drafts = (broadcasts.value || []).filter((b) => bcBroadcastIsAutopostRotationDraft(b))
    if (drafts.length) return Number(drafts[0].id || 0)
  }
  return 0
}

/** Подпись карточки «Посты» — название(я) черновика, без счётчика */
function bcCampaignUxPostsCardLabelForCamp(camp) {
  if (!camp) return '—'
  const ap = camp.autopost || {}
  if (ap.use_all_broadcasts) return tt('admin.bc_campaign.word_all')
  const resolved = bcCampaignUxBroadcastsForCamp(camp)
  if (resolved.length) {
    const parts = resolved.map((b) => bcCampaignUxDraftDisplayTitle(b))
    return parts.join(' · ')
  }
  const ids = [...new Set((Array.isArray(ap.broadcast_ids) ? ap.broadcast_ids : []).map((x) => Number(x)).filter((x) => x > 0))]
  const anchor = Number(camp.anchor_broadcast_id || ap.anchor_broadcast_id || 0)
  const need = [...ids]
  if (anchor > 0 && !need.includes(anchor)) need.unshift(anchor)
  if (!need.length) return '—'
  const parts = need.map((id) => {
    const b = (broadcasts.value || []).find((bb) => Number(bb?.id || 0) === id)
    if (b) return bcCampaignUxDraftDisplayTitle(b)
    return tt('admin.broadcast_stats.untitled')
  })
  return parts.join(' · ')
}

async function bcCampaignUxManageOpenPostEditor(opts = {}) {
  const camp = bcCampaignUxManageItem.value
  const bid = bcCampaignUxPrimaryBroadcastIdForCamp(camp || {})
  if (!bid) {
    window.alert(tt('admin.bc_campaign.modal_posts_empty'))
    return
  }
  const returnScreen =
    opts?.returnScreen === 'stats' || bcCampaignUxScreen.value === 'stats' ? 'stats' : 'manage'
  void bcCampaignUxOpenPostEditor(bid, { returnScreen })
}

async function bcCampaignUxStatsOpenPostEditor() {
  await bcCampaignUxManageOpenPostEditor({ returnScreen: 'stats' })
}

async function openBcCampaignUxManage(camp) {
  const id = Number(camp?.id || 0)
  if (!id) return
  const ap = camp?.autopost || {}
  const savedG = Array.isArray(ap?.group_chat_ids) ? ap.group_chat_ids : []
  const savedCh = Array.isArray(ap?.channel_chat_ids) ? ap.channel_chat_ids : []
  bcBroadcastGroupScope.value = 'mine'
  try {
    await Promise.all([loadBroadcastEligibleGroups(), loadBroadcastEligibleChannels()])
    await bcExpandBroadcastScopeIfSavedTargetsMissing(savedG, savedCh)
  } catch {
    /* ignore */
  }
  bcCampaignUxManageId.value = id
  bcCampaignUxScreen.value = 'manage'
  bcCampaignUxOpen.value = true
}
async function openBcCampaignUxList() {
  if (isOwnerCabinet.value && !meAdminProfile.value?.is_premium) {
    void router.push({ path: '/', query: { section: 'billing', scroll: 'plans' } })
    return
  }
  bcCampaignUxOpen.value = true
  bcCampaignUxScreen.value = 'list'
  await loadAutopostCampaigns()
  void Promise.all([loadBroadcastEligibleGroups(), loadBroadcastEligibleChannels()])
}
async function openBcCampaignUxWizard() {
  if (!(broadcasts.value || []).length) {
    const created = await createBcDraft('autopost')
    if (!created) return
  }
  bcBroadcastGroupScope.value = 'mine'
  await loadBroadcastEligibleGroups()
  await loadBroadcastEligibleChannels()
  const selectedBid = Number(bcSelectedId.value || (broadcasts.value?.[0]?.id || 0) || 0)
  bcCampaignUxWizard.value = {
    title: '',
    postIds: selectedBid ? [selectedBid] : [],
    campaignType: 'simple',
    scheduleMode: 'every_day',
    intervalDays: 1,
    weekdays: [0, 1, 2, 3, 4],
    startDate: '',
    endDate: '',
    sendTime: '09:00',
    windowStart: '09:00',
    windowEnd: '21:00',
    timezone: typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Yekaterinburg' : 'Asia/Yekaterinburg',
    postsPerDay: 1,
    spreadInWindow: true,
    sendWindows: [{ windowStart: '09:00', windowEnd: '21:00', posts: 1 }],
    targetChannels: false,
    targetGroups: true,
    targetBots: false,
    selectedGroups: [],
    selectedChannels: [],
    customDays: '',
  }
  bcCampaignUxSetStartDateTodayFromTz()
  bcCampaignUxEditingCampaignId.value = 0
  bcCampaignUxStep.value = 1
  bcCampaignUxScreen.value = 'wizard'
  bcCampaignUxOpen.value = true
}
function bcOneShotFlowBack() {
  if (bcConfirmModalOpen.value) {
    bcConfirmModalOpen.value = false
    bcSendTimingModalOpen.value = true
    return
  }
  if (bcSendTimingModalOpen.value) {
    bcSendTimingModalOpen.value = false
    bcSendTargetModalOpen.value = true
    return
  }
  if (bcSendTargetModalOpen.value) {
    bcSendTargetModalOpen.value = false
    return
  }
  if (bcAuxModal.value) {
    bcAuxModal.value = ''
    return
  }
  void closeQuickBroadcastDraft()
}

function bcCampaignUxBack() {
  if (bcAuxModal.value && bcCampaignUxOpen.value) {
    bcAuxModal.value = ''
    return
  }
  if (bcCampaignUxScheduleModalOpen.value) {
    bcCampaignUxCloseScheduleModal()
    return
  }
  if (bcCampaignUxRecipientsModalOpen.value) {
    bcCampaignUxCloseRecipientsModal()
    return
  }
  if (bcCampaignUxCampaignPostsModalOpen.value) {
    bcCampaignUxCloseCampaignPostsModal()
    return
  }
  if (bcCampaignUxScreen.value === 'postEditor') {
    bcCampaignUxPostEditorLoading.value = false
    bcCampaignUxScreen.value = String(bcCampaignUxPostEditorReturn.value || 'wizard')
    return
  }
  if (bcCampaignUxScreen.value === 'wizard' && bcCampaignUxStep.value > 1) {
    bcCampaignUxStep.value -= 1
    return
  }
  if (bcCampaignUxScreen.value === 'review') {
    bcCampaignUxScreen.value = 'wizard'
    bcCampaignUxStep.value = 4
    return
  }
  if (bcCampaignUxScreen.value === 'manage' || bcCampaignUxScreen.value === 'stats' || bcCampaignUxScreen.value === 'success') {
    bcCampaignUxScreen.value = 'list'
    return
  }
  bcCampaignUxOpen.value = false
}
function bcCampaignUxNextStep() {
  if (!bcCampaignUxWizardCanNext.value) return
  if (bcCampaignUxStep.value >= 4) {
    bcCampaignUxScreen.value = 'review'
    return
  }
  bcCampaignUxStep.value += 1
}

function bcRunShakeClass(el) {
  if (!el || typeof el.classList === 'undefined') return
  try {
    el.classList.remove('bc-shake-x')
    void el.offsetWidth
    el.classList.add('bc-shake-x')
    window.setTimeout(() => {
      try {
        el.classList.remove('bc-shake-x')
      } catch {
        //
      }
    }, 480)
  } catch {
    //
  }
}

function bcCampaignUxNextStepAttempt() {
  if (bcCampaignUxWizardCanNext.value) {
    bcCampaignUxNextStep()
    return
  }
  if (bcCampaignUxStep.value === 1) {
    const w = bcCampaignUxWizard.value
    const titleOk = !!String(w.title || '').trim()
    const postsOk = Number(w.postIds?.length || 0) > 0
    if (!titleOk) {
      bcRunShakeClass(bcCampaignUxWizardTitleInputRef.value)
      return
    }
    if (!postsOk) {
      bcRunShakeClass(bcCampaignUxWizardPostsListRef.value)
    }
  }
}

function bcQuickDraftTryNext() {
  bcSyncEditorHtml()
  const titleOk = String(bcTitle.value || '').trim().length > 0
  const bodyOk = bcHasMessageText()
  if (!titleOk) {
    bcRunShakeClass(bcQuickDraftTitleInputRef.value)
    return
  }
  if (!bodyOk) {
    bcRunShakeClass(bcBodyRef.value)
    return
  }
  void openSendTargetModal()
}

async function bcCampaignUxDeleteAllDraftPosts() {
  const ids = bcDraftBroadcastsForAutopost.value.map((b) => Number(b?.id || 0)).filter((x) => x > 0)
  if (!ids.length) return
  if (!window.confirm(tt('admin.dlg.bc_delete_all_draft_posts_confirm'))) return
  try {
    for (const id of ids) {
      await fetch(() => api.adminBroadcastDelete(id))
      try {
        localStorage.removeItem(bcDraftCacheKey(id))
      } catch {
        //
      }
    }
    const sel = Number(bcSelectedId.value || 0)
    if (sel && ids.includes(sel)) {
      bcSelectedId.value = null
      bcTitle.value = ''
      bcBodyHtml.value = ''
      bcButtonRows.value = [[bcEmptyButton()]]
      bcMediaKindStored.value = 'none'
      bcMediaOriginalName.value = ''
      bcMediaHistory.value = []
      bcEditorOpen.value = false
    }
    await loadBroadcasts()
    bcCampaignUxPruneStalePostIds()
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.bc_delete_failed')))
  }
}
function bcCampaignUxTogglePost(id) {
  const bid = Number(id || 0)
  if (!bid) return
  const cur = (bcCampaignUxWizard.value.postIds || []).map((x) => Number(x))
  if (cur.length === 1 && cur[0] === bid) {
    bcCampaignUxWizard.value.postIds = []
    return
  }
  bcCampaignUxWizard.value.postIds = [bid]
}
function bcCampaignUxSelectAllDraftPosts() {
  const ids = bcDraftBroadcastsForAutopost.value.map((b) => Number(b.id || 0)).filter((x) => x > 0)
  if (!ids.length) return
  bcCampaignUxWizard.value.postIds = [ids[0]]
}
function bcCampaignUxClearDraftPostSelection() {
  const draftSet = new Set(bcDraftBroadcastsForAutopost.value.map((b) => Number(b.id || 0)).filter((x) => x > 0))
  bcCampaignUxWizard.value.postIds = (bcCampaignUxWizard.value.postIds || [])
    .map((x) => Number(x))
    .filter((x) => x > 0 && !draftSet.has(x))
}
function bcCampaignUxRemovePost(id) {
  const bid = Number(id || 0)
  bcCampaignUxWizard.value.postIds = (bcCampaignUxWizard.value.postIds || []).map((x) => Number(x)).filter((x) => x !== bid)
}
function bcCampaignUxPostMeta(item) {
  const hasMedia = !!(item?.media_items?.length || item?.media_original_name || item?.has_media_file)
  const hasButtons = !!(item?.keyboard?.rows?.length || item?.keyboard_rows?.length)
  if (hasMedia && hasButtons) return '🖼️🔗'
  if (hasMedia) return '🖼️'
  if (hasButtons) return '🔗'
  return '✍️'
}
async function bcCampaignUxHydratePostEditor(bid) {
  const id = Number(bid || 0)
  if (!id) return false
  let item = bcCampaignUxPostMap.value.get(id)
  if (!item) {
    try {
      item = await fetch(() => api.adminBroadcast(id))
      if (item?.id) upsertBroadcastInList(item)
    } catch {
      item = null
    }
  }
  if (!item) return false
  let full = item
  const listItems = Array.isArray(item?.media_items) ? item.media_items : []
  const needsFull =
    !listItems.length ||
    listItems.some((m) => !Number(m?.id)) ||
    String(item?.media_kind || 'none').toLowerCase() !== 'none' ||
    !!(item?.has_media_file || item?.telegram_file_id)
  if (needsFull) {
    try {
      const row = await fetch(() => api.adminBroadcast(id))
      if (row?.id) {
        full = row
        upsertBroadcastInList(row)
      }
    } catch {
      //
    }
  }
  applyBroadcastToForm(full)
  bcQuickTitleBaseline.value = String(bcTitle.value || '')
  return true
}

async function bcCampaignUxOpenPostEditor(id = 0, opts = {}) {
  const bid = Number(id || 0)
  const returnScreen = opts?.returnScreen === 'stats' ? 'stats' : opts?.returnScreen === 'manage' ? 'manage' : 'wizard'
  bcCampaignUxPostEditorReturn.value = returnScreen
  if (bid > 0) {
    bcCampaignUxPostEditorId.value = bid
    bcCampaignUxPostEditorMode.value = 'edit'
    bcCampaignUxScreen.value = 'postEditor'
    const cached = bcCampaignUxPostMap.value.get(bid)
    if (cached) {
      applyBroadcastToForm(cached)
      bcQuickTitleBaseline.value = String(bcTitle.value || '')
    } else {
      bcTitle.value = ''
      bcBodyHtml.value = ''
      bcButtonRows.value = []
      bcMediaHistory.value = []
      bcSelectedId.value = bid
    }
    bcCampaignUxPostEditorLoading.value = true
    try {
      const ok = await bcCampaignUxHydratePostEditor(bid)
      if (!ok) {
        window.alert(tt('admin.dlg.generic_error'))
        bcCampaignUxScreen.value = returnScreen
      }
    } finally {
      bcCampaignUxPostEditorLoading.value = false
    }
    return
  }
  const created = await createBcDraft('autopost')
  if (!created) return
  const nid = Number(bcSelectedId.value || 0)
  if (!nid) {
    window.alert(tt('admin.bc_campaign.err_draft_create'))
    return
  }
  bcCampaignUxPostEditorId.value = nid
  bcCampaignUxPostEditorMode.value = 'create'
  bcCampaignUxScreen.value = 'postEditor'
  bcQuickTitleBaseline.value = String(bcTitle.value || '')
}
async function bcCampaignUxSavePostEditor() {
  const ok = await saveBcDraft()
  if (!ok) return
  const bid = Number(bcSelectedId.value || bcCampaignUxPostEditorId.value || 0)
  if (bid > 0 && String(bcCampaignUxPostEditorReturn.value || 'wizard') === 'wizard') {
    bcCampaignUxWizard.value.postIds = [bid]
  }
  const nextScreen = String(bcCampaignUxPostEditorReturn.value || 'wizard')
  bcCampaignUxScreen.value = nextScreen
  if (nextScreen === 'stats' && bcCampaignUxManageItem.value) {
    try {
      await bcCampaignUxOpenStats(bcCampaignUxManageItem.value)
    } catch {
      //
    }
    return
  }
  if (nextScreen === 'manage') {
    try {
      await Promise.all([loadBroadcasts(), loadAutopostCampaigns()])
    } catch {
      //
    }
  }
}
function bcCampaignUxToggleWeekday(day) {
  const v = Number(day)
  if (!(v >= 0 && v <= 6)) return
  const set = new Set((bcCampaignUxWizard.value.weekdays || []).map((x) => Number(x)))
  if (set.has(v)) set.delete(v)
  else set.add(v)
  bcCampaignUxWizard.value.weekdays = [...set].sort((a, b) => a - b)
}
function bcCampaignUxToggleWizardTargetChannels() {
  const w = bcCampaignUxWizard.value
  w.targetChannels = !w.targetChannels
  if (!w.targetChannels) w.selectedChannels = []
}
function bcCampaignUxToggleWizardTargetGroups() {
  const w = bcCampaignUxWizard.value
  w.targetGroups = !w.targetGroups
  if (!w.targetGroups) w.selectedGroups = []
}
function bcCampaignUxOpenRecipientPicker(kind) {
  bcCampaignUxRecipientPickerKind.value = kind === 'channels' ? 'channels' : 'groups'
  bcCampaignUxRecipientQuery.value = ''
  bcCampaignUxRecipientPickerOpen.value = true
}
function bcCampaignUxToggleRecipient(id) {
  const chatId = Number(id || 0)
  if (!chatId) return
  const field = bcCampaignUxRecipientPickerKind.value === 'channels' ? 'selectedChannels' : 'selectedGroups'
  const set = new Set((bcCampaignUxWizard.value[field] || []).map((x) => Number(x)))
  if (set.has(chatId)) set.delete(chatId)
  else set.add(chatId)
  bcCampaignUxWizard.value[field] = [...set]
}
function bcCampaignUxSelectAllRecipients() {
  if (bcCampaignUxRecipientPickerKind.value === 'channels') {
    bcCampaignUxWizard.value.selectedChannels = (bcBroadcastChannels.value || []).map((c) => bcNormalizeChatId(c)).filter((x) => x < 0)
    return
  }
  bcCampaignUxWizard.value.selectedGroups = (bcBroadcastGroups.value || []).map((c) => bcNormalizeChatId(c)).filter((x) => x < 0)
}
function bcCampaignUxClearRecipients() {
  if (bcCampaignUxRecipientPickerKind.value === 'channels') {
    bcCampaignUxWizard.value.selectedChannels = []
    return
  }
  bcCampaignUxWizard.value.selectedGroups = []
}
async function bcCampaignUxCreateCampaign() {
  if (bcCampaignUxBusy.value) return
  const w = bcCampaignUxWizard.value
  if (!String(w.title || '').trim()) return
  bcCampaignUxBusy.value = true
  try {
    await loadBroadcasts()
    const existing = new Set((broadcasts.value || []).map((b) => Number(b?.id || 0)).filter((x) => x > 0))
    const rawPosts = [...new Set((w.postIds || []).map((x) => Number(x)).filter((x) => x > 0))]
    if (!rawPosts.length) return
    const postIds = rawPosts.filter((x) => existing.has(x)).slice(0, 1)
    if (!postIds.length) {
      window.alert(tt('admin.bc_campaign.err_posts_resolve'))
      return
    }
    const modeRaw = String(w.scheduleMode || 'every_day')
    const mode = modeRaw === 'weekdays' ? 'weekdays' : 'every_day'
    const wd = mode === 'weekdays' ? [...(w.weekdays || [0, 1, 2, 3, 4])] : [0, 1, 2, 3, 4, 5, 6]
    const { rows } = bcCampaignUxNormalizeSendWindowRowsFromInput(w)
    const timing = bcCampaignUxAutopostTimingPayloadFromRows(w, rows)
    const activeG = bcCampaignUxWizardActiveGroupIds()
    const activeCh = bcCampaignUxWizardActiveChannelIds()
    const usersOnly =
      showFullAdminShell.value &&
      !isBroadcastShellLite.value &&
      w.targetBots &&
      !w.targetGroups &&
      !w.targetChannels
    if (!usersOnly && !activeG.length && !activeCh.length) {
      window.alert(tt('admin.bc_campaign.err_pick_recipients'))
      return
    }
    const ap = {
      runState: 'stopped',
      scheduleMode: mode === 'weekdays' ? 'weekdays' : 'every_day',
      weekdays: wd,
      startDate: String(w.startDate || '').trim().slice(0, 10),
      endDate: String(w.endDate || '').trim().slice(0, 10),
      timezone: String(w.timezone || 'Asia/Yekaterinburg').trim() || 'Asia/Yekaterinburg',
      ...timing,
      autopost_target:
        showFullAdminShell.value &&
        !isBroadcastShellLite.value &&
        w.targetBots &&
        !w.targetGroups &&
        !w.targetChannels
          ? 'users'
          : 'groups',
      group_chat_ids: [...bcCampaignUxWizardActiveGroupIds()],
      channel_chat_ids: [...bcCampaignUxWizardActiveChannelIds()],
      autopost_channels_disabled: !w.targetChannels,
      use_all_broadcasts: false,
      broadcast_ids: [...postIds],
    }
    let cid = Number(bcCampaignUxEditingCampaignId.value || 0)
    if (cid > 0) {
      await fetch(() =>
        api.adminAutopostCampaignPatch(cid, {
          title: String(w.title || '').trim(),
          anchor_broadcast_id: postIds[0],
          autopost: ap,
        }),
      )
    } else {
      const created = await fetch(() => api.adminAutopostCampaignCreate({ anchor_broadcast_id: postIds[0] }))
      cid = Number(created?.id || 0)
      if (!cid) throw new Error(tt('admin.autopost.err_campaign_not_created'))
      await fetch(() =>
        api.adminAutopostCampaignPatch(cid, {
          title: String(w.title || '').trim(),
          anchor_broadcast_id: postIds[0],
          autopost: ap,
        }),
      )
    }
    await loadAutopostCampaigns()
    const camp = (bcAutopostCampaigns.value || []).find((c) => Number(c?.id || 0) === cid)
    const apSaved = camp?.autopost && typeof camp.autopost === 'object' ? camp.autopost : {}
    const savedN =
      (apSaved.group_chat_ids || []).length +
      (apSaved.autopost_channels_disabled ? 0 : (apSaved.channel_chat_ids || []).length)
    const wantedN = activeG.length + activeCh.length
    if (wantedN > 0 && savedN === 0) {
      window.alert(tt('admin.bc_campaign.err_recipients_filtered'))
    } else if (wantedN > savedN && savedN > 0) {
      window.alert(tt('admin.broadcast_send.some_chats_filtered', { requested: wantedN, resolved: savedN }))
    }
    bcCampaignUxSuccessInfo.value = { id: cid, nextAt: bcCampaignUxNearestAt(), needsStart: true }
    bcCampaignUxManageId.value = cid
    bcCampaignUxScreen.value = 'success'
  } catch (e) {
    window.alert(String(e?.body?.detail || e?.message || tt('admin.autopost.err_create_campaign')))
  } finally {
    bcCampaignUxBusy.value = false
  }
}

async function bcCampaignUxSuccessStartNow() {
  const id = Number(bcCampaignUxSuccessInfo.value?.id || bcCampaignUxManageId.value || 0)
  if (!id) return
  try {
    await loadAutopostCampaigns()
    const camp = (bcAutopostCampaigns.value || []).find((c) => Number(c?.id || 0) === id)
    if (!camp) return
    await bcCampaignStartOrResume(camp)
    bcCampaignUxSuccessInfo.value = { ...bcCampaignUxSuccessInfo.value, needsStart: false }
    bcCampaignUxManageId.value = id
    bcCampaignUxScreen.value = 'manage'
  } catch (e) {
    window.alert(String(e?.body?.detail || e?.message || tt('admin.autopost.err_save')))
  }
}

async function bcCampaignUxOpenScheduleModal(camp) {
  const id = Number(camp?.id || 0)
  if (!id) return
  try {
    await loadAutopostCampaigns({ silent: true })
  } catch {
    /* keep cached camp */
  }
  const fresh = (bcAutopostCampaigns.value || []).find((c) => Number(c?.id || 0) === id) || camp
  const ap = fresh?.autopost || camp?.autopost || {}
  bcCampaignUxScheduleCampId.value = id
  const apModeRaw = String(ap?.scheduleMode || fresh?.autopost?.scheduleMode || 'every_day')
  const apMode = apModeRaw === 'weekdays' ? 'weekdays' : 'every_day'
  bcCampaignUxScheduleForm.value = {
    scheduleMode: apMode,
    intervalDays: 1,
    weekdays: Array.isArray(ap?.weekdays) && ap.weekdays.length ? ap.weekdays.map((x) => Number(x)) : [0, 1, 2, 3, 4],
    startDate: String(ap?.startDate || '').slice(0, 10),
    endDate: String(ap?.endDate || '').slice(0, 10),
    sendTime: String(ap?.firstPostTime || ap?.windowStart || '09:00').slice(0, 5),
    timezone: String(ap?.timezone || 'Asia/Yekaterinburg'),
    spreadInWindow: ap?.spreadInWindow !== false,
    customDays: '',
    sendWindows: bcCampaignUxScheduleSegmentsFromAp(ap),
  }
  bcCampaignUxScheduleSavedSig.value = bcCampaignUxScheduleSegmentsSignature(
    bcCampaignUxScheduleForm.value.sendWindows,
    bcCampaignUxScheduleForm.value.spreadInWindow !== false,
  )
  bcCampaignUxScheduleModalOpen.value = true
}

function bcCampaignUxCloseScheduleModal() {
  bcCampaignUxScheduleModalOpen.value = false
  bcCampaignUxScheduleCampId.value = 0
  bcCampaignUxScheduleSavedSig.value = ''
}

function bcCampaignUxScheduleSetStartTodayFromTz() {
  const w = bcCampaignUxScheduleForm.value
  const tz = String(w.timezone || '').trim()
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  let ymd = ''
  let hm = '09:00'
  try {
    const tzUse = tz || (typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone : 'UTC')
    const parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: tzUse,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).formatToParts(d)
    const gp = (t) => parts.find((x) => x.type === t)?.value || ''
    ymd = `${gp('year')}-${gp('month')}-${gp('day')}`
    hm = `${gp('hour')}:${gp('minute')}`
  } catch {
    ymd = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
    hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  }
  hm = hm.slice(0, 5)
  bcCampaignUxScheduleForm.value = { ...bcCampaignUxScheduleForm.value, startDate: ymd, sendTime: hm }
}

function bcCampaignUxScheduleToggleWeekday(day) {
  const v = Number(day)
  if (!(v >= 0 && v <= 6)) return
  const w = bcCampaignUxScheduleForm.value
  const set = new Set((w.weekdays || []).map((x) => Number(x)))
  if (set.has(v)) set.delete(v)
  else set.add(v)
  bcCampaignUxScheduleForm.value = { ...w, weekdays: [...set].sort((a, b) => a - b) }
}

function bcCampaignUxScheduleFormAddSegment() {
  const w = bcCampaignUxScheduleForm.value
  const arr = [...(w.sendWindows || [])]
  const last = arr.length ? arr[arr.length - 1] : { windowStart: '09:00', windowEnd: '21:00', posts: 1 }
  arr.push({
    windowStart: String(last.windowStart || '09:00').slice(0, 5),
    windowEnd: String(last.windowEnd || '21:00').slice(0, 5),
    posts: Math.max(1, Math.min(288, Math.trunc(Number(last.posts || 1)))),
  })
  bcCampaignUxScheduleForm.value = { ...w, sendWindows: arr }
}

function bcCampaignUxScheduleFormRemoveSegment(idx) {
  const w = bcCampaignUxScheduleForm.value
  const arr = [...(w.sendWindows || [])]
  if (arr.length <= 1) return
  arr.splice(Number(idx), 1)
  bcCampaignUxScheduleForm.value = { ...w, sendWindows: arr }
}

function bcCampaignUxWizardAddScheduleSegment() {
  const w = bcCampaignUxWizard.value
  const arr = [...(w.sendWindows || [])]
  const last = arr.length ? arr[arr.length - 1] : null
  const row = last
    ? {
        windowStart: String(last.windowStart || '09:00').slice(0, 5),
        windowEnd: String(last.windowEnd || '21:00').slice(0, 5),
        posts: Math.max(1, Math.min(288, Math.trunc(Number(last.posts || w.postsPerDay || 1)))),
      }
    : {
        windowStart: String(w.windowStart || '09:00').slice(0, 5),
        windowEnd: String(w.windowEnd || '21:00').slice(0, 5),
        posts: Math.max(1, Math.min(288, Math.trunc(Number(w.postsPerDay || 1)))),
      }
  bcCampaignUxWizard.value = { ...w, sendWindows: [...arr, row] }
}

function bcCampaignUxWizardRemoveScheduleSegment(idx) {
  const w = bcCampaignUxWizard.value
  const arr = [...(w.sendWindows || [])]
  if (arr.length <= 1) return
  arr.splice(Number(idx), 1)
  bcCampaignUxWizard.value = { ...w, sendWindows: arr }
}

function bcCampaignUxWizardPostsPerDayEdited() {
  const w = bcCampaignUxWizard.value
  const arr = [...(w.sendWindows || [])]
  if (arr.length !== 1) return
  const ppd = Math.max(1, Math.min(288, Math.trunc(Number(w.postsPerDay || 1))))
  arr[0].posts = ppd
  bcCampaignUxWizard.value = { ...w, windowStart: arr[0].windowStart, windowEnd: arr[0].windowEnd, sendWindows: arr }
}

function bcCampaignUxWizardSegmentPostsEdited() {
  const w = bcCampaignUxWizard.value
  const arr = [...(w.sendWindows || [])]
  if (arr.length !== 1) return
  const p = Math.max(1, Math.min(288, Math.trunc(Number(arr[0].posts || 1))))
  arr[0].posts = p
  bcCampaignUxWizard.value = { ...w, postsPerDay: p, windowStart: arr[0].windowStart, windowEnd: arr[0].windowEnd, sendWindows: arr }
}

async function bcCampaignUxSaveScheduleModal() {
  if (bcCampaignUxScheduleBusy.value) return
  const cid = Number(bcCampaignUxScheduleCampId.value || 0)
  if (!cid) return
  const w = bcCampaignUxScheduleForm.value
  const modeRaw = String(w.scheduleMode || 'every_day')
  const mode = modeRaw === 'weekdays' ? 'weekdays' : 'every_day'
  const wd = mode === 'weekdays' ? [...(w.weekdays || [0, 1, 2, 3, 4])] : [0, 1, 2, 3, 4, 5, 6]
  const { rows } = bcCampaignUxNormalizeSendWindowRowsFromInput(w)
  const timing = bcCampaignUxAutopostTimingPayloadFromRows(w, rows)
  const ap = {
    scheduleMode: mode === 'weekdays' ? 'weekdays' : 'every_day',
    weekdays: wd,
    startDate: String(w.startDate || '').trim().slice(0, 10),
    endDate: String(w.endDate || '').trim().slice(0, 10),
    timezone: String(w.timezone || 'Asia/Yekaterinburg').trim() || 'Asia/Yekaterinburg',
    ...timing,
  }
  bcCampaignUxScheduleBusy.value = true
  try {
    await fetch(() => api.adminAutopostCampaignPatch(cid, { autopost: ap }))
    await loadAutopostCampaigns()
    bcCampaignUxCloseScheduleModal()
  } catch (e) {
    window.alert(String(e?.body?.detail || e?.message || tt('admin.autopost.err_save')))
  } finally {
    bcCampaignUxScheduleBusy.value = false
  }
}

function bcCampaignUxFormatCampStatInstant(iso) {
  if (!iso) return '—'
  try {
    const d = new Date(String(iso))
    if (Number.isNaN(d.getTime())) return String(iso)
    const tz = String(bcCampaignUxManageItem.value?.autopost?.timezone || '').trim()
    const opts = { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }
    if (tz) {
      try {
        return new Intl.DateTimeFormat(undefined, { ...opts, timeZone: tz }).format(d)
      } catch {
        //
      }
    }
    return new Intl.DateTimeFormat(undefined, opts).format(d)
  } catch {
    return String(iso)
  }
}

function bcCampaignUxLeaveStatsToManage() {
  bcCampaignUxStatsDeliverModalOpen.value = false
  bcCampaignUxScreen.value = 'manage'
}

async function bcCampaignUxOpenStats(camp) {
  const id = Number(camp?.id || bcCampaignUxManageId.value || 0)
  if (!id) return
  bcCampaignUxStatsDeliverModalOpen.value = false
  bcCampaignUxManageId.value = id
  bcCampaignUxScreen.value = 'stats'
  bcCampaignUxStatsData.value = null
  bcBroadcastGroupScope.value = 'mine'
  try {
    await Promise.all([loadBroadcastEligibleGroups(), loadBroadcastEligibleChannels()])
  } catch {
    /* ignore */
  }
  try {
    bcCampaignUxStatsData.value = await fetch(() =>
      api.adminAutopostCampaignAutopostStats(id, Number(bcCampaignUxStatsPeriod.value || 7) || 7),
    )
  } catch {
    bcCampaignUxStatsData.value = null
  }
}

const CABINET_WEEKDAY_SHORT_KEYS = [
  'mon_short',
  'tue_short',
  'wed_short',
  'thu_short',
  'fri_short',
  'sat_short',
  'sun_short',
]
const BC_WEEKDAY_OPTS = computed(() =>
  CABINET_WEEKDAY_SHORT_KEYS.map((key, idx) => ({
    v: idx,
    label: tt(`cabinet_stats.weekdays.${key}`),
  })),
)

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

/** После загрузки списков групп/каналов: убираем id, которых нет в допустимом списке (смена кабинета owner↔delegated и т.д.). */
function bcSanitizeSelectionsToEligibleLists() {
  const allowedG = new Set((bcBroadcastGroups.value || []).map((c) => bcNormalizeChatId(c)))
  bcSelectedGroupIds.value = [...new Set((bcSelectedGroupIds.value || []).map(Number).filter((id) => allowedG.has(Number(id))))]
  const allowedCh = new Set((bcBroadcastChannels.value || []).map((c) => bcNormalizeChatId(c)))
  bcSelectedChannelIds.value = [...new Set((bcSelectedChannelIds.value || []).map(Number).filter((id) => allowedCh.has(Number(id))))]
  const prevG = bcAutopostingForm.value.group_chat_ids || []
  const prevCh = bcAutopostingForm.value.channel_chat_ids || []
  const nextG = prevG.map(Number).filter((id) => allowedG.has(id))
  const nextCh = prevCh.map(Number).filter((id) => allowedCh.has(id))
  if (nextG.length !== prevG.length || nextCh.length !== prevCh.length) {
    bcAutopostingForm.value = {
      ...bcAutopostingForm.value,
      group_chat_ids: [...nextG],
      channel_chat_ids: [...nextCh],
    }
  }
}

async function loadBroadcastEligibleGroups() {
  try {
    const sc = bcBroadcastGroupScope.value === 'all' ? 'all' : 'mine'
    const r = await fetch(() => api.adminBroadcastGroups(sc, { includeInactive: true }))
    const items = r?.items || []
    const myTg = Number(meAdminProfile.value?.telegram_id || 0)
    const onlyForeign =
      cabinetMode.value === 'delegated' || isDelegatedFreeBroadcastCabinet.value
    bcBroadcastGroups.value = onlyForeign
      ? items.filter((x) => Number(x?.owner_telegram_id || 0) !== myTg)
      : items
    bcSanitizeSelectionsToEligibleLists()
    tryApplyDelegatedPreferredGroup()
    if (isDelegatedFreeBroadcastCabinet.value) {
      applyDelegatedFreeBroadcastGroupLock()
    } else if (onlyForeign && bcBroadcastGroups.value.length === 1 && !(bcSelectedGroupIds.value || []).length) {
      const gid = bcNormalizeChatId(bcBroadcastGroups.value[0])
      bcSelectedGroupIds.value = [gid]
      bcAutopostingForm.value = {
        ...bcAutopostingForm.value,
        group_chat_ids: [gid],
        autopost_target: 'groups',
      }
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

/** Free + делегирование рассылки: допустимы только каналы из ответа API; без выбора — все переданные id. */
function applyDelegatedFreeBroadcastChannelLock() {
  const ids = (bcBroadcastChannels.value || [])
    .map((c) => bcNormalizeChatId(c))
    .filter((x) => Number.isFinite(x) && x !== 0)
  if (!ids.length) return
  const allowed = new Set(ids)
  let chosen = (bcSelectedChannelIds.value || []).map(Number).filter((x) => allowed.has(x))
  if (!chosen.length) {
    chosen = [...ids]
  }
  bcSelectedChannelIds.value = [...chosen]
  bcAutopostingForm.value = {
    ...bcAutopostingForm.value,
    channel_chat_ids: [...chosen],
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
    bcSanitizeSelectionsToEligibleLists()
    if (isDelegatedFreeBroadcastCabinet.value) {
      applyDelegatedFreeBroadcastChannelLock()
    } else if (
      onlyForeignCh &&
      bcBroadcastChannels.value.length === 1 &&
      !(bcSelectedChannelIds.value || []).length
    ) {
      const cid = bcNormalizeChatId(bcBroadcastChannels.value[0])
      bcSelectedChannelIds.value = [cid]
      bcAutopostingForm.value = {
        ...bcAutopostingForm.value,
        channel_chat_ids: [cid],
      }
    }
  } catch {
    bcBroadcastChannels.value = []
  }
}

/**
 * Расширяем scope=all только если в сохранённых id есть чаты вне списка «мой кабинет»
 * (полный админ сервиса). Иначе счётчик на главной и выбор получателей совпадают по умолчанию.
 */
async function bcExpandBroadcastScopeIfSavedTargetsMissing(savedGroupIds, savedChannelIds) {
  if (!bcBroadcastCanScopeAll.value) return
  const gids = [...new Set((savedGroupIds || []).map(Number).filter((x) => Number.isFinite(x) && x < 0))]
  const cids = [...new Set((savedChannelIds || []).map(Number).filter((x) => Number.isFinite(x) && x < 0))]
  const haveG = new Set((bcBroadcastGroups.value || []).map((c) => bcNormalizeChatId(c)))
  const haveCh = new Set((bcBroadcastChannels.value || []).map((c) => bcNormalizeChatId(c)))
  const missG = gids.some((id) => !haveG.has(id))
  const missCh = cids.some((id) => !haveCh.has(id))
  if (!missG && !missCh) return
  bcBroadcastGroupScope.value = 'all'
  await loadBroadcastEligibleGroups()
  await loadBroadcastEligibleChannels()
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
      window.alert(String(e?.body?.detail || e?.message || tt('admin.autopost.err_save_schedule')))
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
    window.alert(String(e?.body?.detail || e?.message || tt('admin.autopost.err_save_schedule')))
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
      window.alert(String(e?.body?.detail || e?.message || tt('admin.autopost.err_save')))
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
    window.alert(String(e?.body?.detail || e?.message || tt('admin.autopost.err_save')))
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
  let msg = tt('admin.autopost.confirm_autopost_draft_intro')
  if (q?.broadcast_charge_applies && Number(q.cost_tokens || 0) > 0) {
    msg =
      tt('admin.autopost.confirm_slot_hint_list', {
        tokens: Number(q.cost_tokens),
        n: Number(q.n_groups || 0),
      }) + msg
    if (q.can_afford === false) {
      msg += tt('admin.autopost.confirm_aurum_short_suffix')
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
  await bcExpandBroadcastScopeIfSavedTargetsMissing(
    bcAutopostingForm.value.group_chat_ids || [],
    bcAutopostingForm.value.channel_chat_ids || [],
  )
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
    window.alert(tt('admin.autopost.pick_template_anchor'))
    return
  }
  try {
    await fetch(() => api.adminAutopostCampaignCreate({ anchor_broadcast_id: Number(bcSelectedId.value) }))
    await loadAutopostCampaigns()
  } catch (e) {
    window.alert(String(e?.body?.detail || e?.message || tt('admin.autopost.err_create_campaign')))
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
    window.alert(String(e?.body?.detail || e?.message || tt('admin.autopost.err_save_title')))
  }
}

async function deleteBcAutopostCampaign(camp) {
  const id = Number(camp?.id || 0)
  if (!id) return
  if (!window.confirm(tt('admin.autopost.confirm_delete_campaign'))) return
  try {
    await fetch(() => api.adminAutopostCampaignDelete(id))
    await loadAutopostCampaigns()
    bcCampaignUxManageId.value = 0
    bcCampaignUxScreen.value = 'list'
    bcCampaignUxStatsDeliverModalOpen.value = false
    bcCampaignUxRecipientsModalOpen.value = false
    bcCampaignUxCloseScheduleModal()
    if (bcCampaignUxCampaignPostsModalOpen.value) bcCampaignUxCloseCampaignPostsModal()
  } catch (e) {
    window.alert(String(e?.body?.detail || e?.message || tt('admin.autopost.err_delete')))
  }
}

async function bcCampaignPatchRunState(camp, runState) {
  const id = Number(camp?.id || 0)
  if (!id) return
  try {
    await fetch(() => api.adminAutopostCampaignPatch(id, { autopost: { runState } }))
    await loadAutopostCampaigns()
  } catch (e) {
    window.alert(String(e?.body?.detail || e?.message || tt('admin.autopost.err_save')))
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
  let msg = tt('admin.autopost.confirm_autopost_campaign_intro')
  if (q?.broadcast_charge_applies && Number(q.cost_tokens || 0) > 0) {
    msg =
      tt('admin.autopost.confirm_slot_hint_short', {
        tokens: Number(q.cost_tokens),
        n: Number(q.n_groups || 0),
      }) + msg
    if (q.can_afford === false) {
      msg += tt('admin.autopost.confirm_aurum_short_suffix')
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
  send_history: [],
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
  const path = `admin.media_kind.${k}`
  if (['none', 'photo', 'video', 'animation', 'document'].includes(k) && te(path)) return tt(path)
  return k
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
  if (!c || typeof c !== 'object') return 0
  if (c.chat_id !== undefined && c.chat_id !== null && c.chat_id !== '') {
    const n = Number(c.chat_id)
    if (Number.isFinite(n) && n !== 0) return n
  }
  const alt = Number(c.telegram_chat_id ?? c.channel_id ?? 0)
  if (Number.isFinite(alt) && alt !== 0) return alt
  return Number(c.id || 0)
}

function fmtDateTime(v) {
  const s = String(v || '').trim()
  if (!s) return '—'
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return s
  return d.toLocaleString(adminLocaleTag(), {
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
  if (!raw) return { online: false, label: tt('admin.presence.offline') }
  const ts = Date.parse(raw)
  if (!Number.isFinite(ts)) return { online: false, label: tt('admin.presence.offline') }
  const freshMs = 2 * 60 * 1000
  const online = Date.now() - ts <= freshMs
  return { online, label: online ? tt('admin.presence.online') : tt('admin.presence.offline') }
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
  if (started === ended || ended === '—') return tt('admin.broadcast_stats.batch_same', { started, total, ok, fail })
  return tt('admin.broadcast_stats.batch_range', { started, ended, total, ok, fail })
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
  if (s === 'draft') return tt('admin.broadcast_stats.status_draft')
  if (s === 'sending') return tt('admin.broadcast_stats.status_sending')
  if (s === 'sent') return tt('admin.broadcast_stats.status_sent')
  if (s === 'failed') return tt('admin.broadcast_stats.status_failed')
  return String(status || '—')
}

function bcTargetLabel(target) {
  const t = String(target || '').toLowerCase()
  if (t === 'groups') return tt('admin.broadcast_send.target_kind_groups')
  if (t === 'all') return tt('admin.broadcast_send.target_kind_all')
  return tt('admin.broadcast_send.target_kind_users')
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
    alert(tt('admin.broadcast_stats.no_posts'))
    return
  }
  if (!Number(bcStatsSelectedId.value || 0)) {
    bcStatsSelectedId.value = Number(bcSelectedId.value || broadcasts.value[0]?.id || 0)
  }
  const sid = Number(bcStatsSelectedId.value || 0)
  const remembered = String(bcLastSendTargetByPost.value?.[sid] || '').toLowerCase()
  bcStatsTab.value =
    isBroadcastShellLite.value
      ? 'groups'
      : remembered === 'groups' || remembered === 'all'
        ? 'groups'
        : 'bots'
  bcStatsFrom.value = ''
  bcStatsTo.value = nowLocalInputValue()
  bcStatsModalOpen.value = true
  loadBroadcastStats()
}

function openStatsHistoryModal() {
  if (!bcStatsTo.value) bcStatsTo.value = nowLocalInputValue()
  bcStatsHistoryModalOpen.value = true
}

const statsHistoryTitleComputed = computed(() => {
  if (isBroadcastShellLite.value) return tt('admin.broadcast_stats.history_groups')
  return bcStatsTab.value === 'groups'
    ? tt('admin.broadcast_stats.history_groups')
    : tt('admin.broadcast_stats.history_bots')
})

function statsHistoryTitle() {
  return statsHistoryTitleComputed.value
}

function applyHistoryItem(item) {
  const st = String(item?.started_at || '').trim()
  const en = String(item?.ended_at || item?.started_at || '').trim()
  if (st) bcStatsFrom.value = st.slice(0, 16)
  if (en) bcStatsTo.value = en.slice(0, 16)
  bcStatsHistoryModalOpen.value = false
  loadBroadcastStats()
}

async function loadBroadcastStats(opts = {}) {
  const silent = Boolean(opts?.silent)
  const id = Number(bcStatsSelectedId.value || 0)
  if (!id) return
  if (!silent) bcStatsLoading.value = true
  const doFetch = silent ? fetchSilent : fetch
  try {
    const r = await doFetch(() =>
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
      send_history: Array.isArray(r?.send_history) ? r.send_history : [],
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
      send_history: [],
    }
  } finally {
    if (!silent) bcStatsLoading.value = false
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

async function loadBcSendResultStats(broadcastId, opts = {}) {
  const bid = Number(broadcastId || 0)
  if (!bid) return
  const silent = Boolean(opts?.silent)
  if (!silent) bcSendResultLoading.value = true
  try {
    const tk = bcBroadcastStatsTargetKindForSendFlow()
    const r = await fetchSilent(() => api.adminBroadcastStats(bid, '', '', '', tk))
    bcSendResultSnapshot.value = {
      bots: r?.bots || { ok: 0, fail: 0, total: 0 },
      groups: r?.groups || { ok: 0, fail: 0, total: 0 },
      overall: r?.overall || { ok: 0, fail: 0, total: 0 },
      audience_ok: Number(r?.audience_ok || 0),
      audience_total: Number(r?.audience_total || 0),
      per_groups: Array.isArray(r?.per_groups) ? r.per_groups : [],
      batches: Array.isArray(r?.batches) ? r.batches : [],
      errors: Array.isArray(r?.errors) ? r.errors : [],
      connected_groups_total: Number(r?.connected_groups_total || 0),
      connected_bots_total: Number(r?.connected_bots_total || 0),
      real_clicks: Number(r?.real_clicks || 0),
      real_transitions: Number(r?.real_transitions || 0),
      real_clicks_total: Number(r?.real_clicks_total || 0),
      real_link_clicks_total: Number(r?.real_link_clicks_total || 0),
      real_callback_clicks_total: Number(r?.real_callback_clicks_total || 0),
      real_reactions_total: Number(r?.real_reactions_total || 0),
      broadcast_url_tracking_configured: Boolean(r?.broadcast_url_tracking_configured),
      real_link_items: Array.isArray(r?.real_link_items) ? r.real_link_items : [],
      real_callback_items: Array.isArray(r?.real_callback_items) ? r.real_callback_items : [],
      stats_ctr_percent: r?.stats_ctr_percent != null && Number.isFinite(Number(r.stats_ctr_percent)) ? Number(r.stats_ctr_percent) : null,
      stats_ctr_mode: String(r?.stats_ctr_mode || ''),
    }
  } catch {
    if (!silent) {
      bcSendResultSnapshot.value = {
      bots: { ok: 0, fail: 0, total: 0 },
      groups: { ok: 0, fail: 0, total: 0 },
      overall: { ok: 0, fail: 0, total: 0 },
      audience_ok: 0,
      audience_total: 0,
      per_groups: [],
      batches: [],
      errors: [],
      connected_groups_total: 0,
      connected_bots_total: 0,
      real_clicks: 0,
      real_transitions: 0,
      real_clicks_total: 0,
      real_link_clicks_total: 0,
      real_callback_clicks_total: 0,
      real_reactions_total: 0,
      broadcast_url_tracking_configured: true,
      real_link_items: [],
      real_callback_items: [],
      stats_ctr_percent: null,
      stats_ctr_mode: '',
    }
    }
  } finally {
    if (!silent) bcSendResultLoading.value = false
  }
}

function closeBcSendModal() {
  stopBroadcastProgressPolling()
  bcClearStatsPulseTimers()
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
  const live =
    bcSendLiveRow.value && Number(bcSendLiveRow.value?.id || 0) === bid ? { ...bcSendLiveRow.value } : null
  const row = live || (broadcasts.value || []).find((x) => Number(x?.id || 0) === bid)
  const item =
    row || {
      id: bid,
      title: '',
      status: 'sent',
      recipient_ok: Number(bcSendLiveRow.value?.recipient_ok || 0),
      recipient_total: Number(bcSendLiveRow.value?.recipient_total || 0),
      sent_at: bcSendLiveRow.value?.sent_at || bcSendLiveRow.value?.finished_at || '',
    }
  closeBcSendModal()
  bcOpenRecentBroadcastStats(item)
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
  bcSendTimingModalOpen.value = false
  bcSendTargetModalOpen.value = false
  bcShowGroupsPicker.value = false
  bcShowChannelsPicker.value = false
  bcShowBotsPicker.value = false
  bcCampaignUxRecipientPickerOpen.value = false
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
    const t = String(target || '').toLowerCase()
    bcStatsTab.value =
      t === 'groups'
        ? 'groups'
        : t === 'users'
          ? 'bots'
          : t === 'all'
            ? 'groups'
            : 'bots'
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
        await loadBroadcastStats({ silent: true })
      }
      const st = String(row?.status || '').toLowerCase()
      const sentAt = row?.sent_at
      const okc = Number(row?.recipient_ok || 0)
      const flc = Number(row?.recipient_fail || 0)
      const totc = Number(row?.recipient_total || 0)
      const countsLookComplete = totc > 0 && okc + flc >= totc
      const finishedAsDraftWithStats = st === 'draft' && !!sentAt && countsLookComplete
      const sendingVisibleFor = Date.now() - Number(bcSendSendingStartedAt.value || 0)
      const finishedBySentAtFallback = !!sentAt && st !== 'failed' && sendingVisibleFor >= 9000
      const errMsg = String(row?.error_message || '').trim()
      const failedAsDraftWithError =
        st === 'draft' && !sentAt && !!errMsg && okc <= 0 && sendingVisibleFor >= 3500
      const succeededDespiteDraft =
        st === 'draft' && !!sentAt && okc > 0 && (countsLookComplete || finishedBySentAtFallback)
      if (st === 'sent' || finishedAsDraftWithStats || finishedBySentAtFallback || succeededDespiteDraft) {
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
        await loadBcSendResultStats(bidSnap, { silent: true })
        bcPulseBroadcastStats(
          loadBcSendResultStats,
          bidSnap,
          () =>
            bcSendModalOpen.value &&
            bcSendModalState.value === 'done' &&
            Number(bcSendModalBroadcastId.value || 0) === bidSnap,
        )
        return
      }
      if (failedAsDraftWithError) {
        bcSendModalState.value = 'failed'
        bcSendModalText.value = errMsg || tt('admin.broadcast_send.send_error')
        stopBroadcastProgressPolling()
        return
      }
      if (st === 'failed') {
        bcSendModalState.value = 'failed'
        bcSendModalText.value = String(row?.error_message || tt('admin.broadcast_send.send_error'))
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

function bcEditorHasMediaAttachment() {
  if ((bcMediaHistory.value || []).length > 0) return true
  const mk = String(bcMediaKindStored.value || 'none').toLowerCase()
  if (mk !== 'none') return true
  const bid = Number(bcSelectedId.value || 0)
  if (!bid) return false
  const row = (broadcasts.value || []).find((b) => Number(b?.id || 0) === bid)
  return !!(
    row?.has_media_file ||
    row?.telegram_file_id ||
    (Array.isArray(row?.media_items) && row.media_items.length) ||
    String(row?.media_original_name || '').trim()
  )
}

function bcCurrentMaxLen() {
  return bcEditorHasMediaAttachment() ? BC_BROADCAST_CAPTION_MAX_CHARS : BC_BROADCAST_BODY_MAX_CHARS
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
  const el = bcResolveBodyEditor()
  if (!el) return
  sanitizeEditorLinksNoUnderline(el)
  const htmlFromEditor = String(el.innerHTML || '')
  const normalized = bcNormalizeHtmlForTelegram(htmlFromEditor)
  if (bcEditModalOpen.value && bcEditBodyRef.value && el === bcEditBodyRef.value) {
    bcEditBodyHtml.value = normalized
    return
  }
  bcBodyHtml.value = normalized
}

function bcRecordHistory(force = false) {
  const el = bcResolveBodyEditor()
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
  const el = bcResolveBodyEditor()
  if (!el) return
  el.innerHTML = String(bcHistory.value[bcHistoryIndex.value] || '')
  sanitizeEditorLinksNoUnderline(el)
  bcSyncEditorHtml()
  bcSavedTick.value = false
  bcUpdateFormatState()
}

function bcRedo() {
  if (!bcCanRedo()) return
  bcHistoryIndex.value += 1
  const el = bcResolveBodyEditor()
  if (!el) return
  el.innerHTML = String(bcHistory.value[bcHistoryIndex.value] || '')
  sanitizeEditorLinksNoUnderline(el)
  bcSyncEditorHtml()
  bcSavedTick.value = false
  bcUpdateFormatState()
}

/** Подчёркивание только из атрибута style (fragment не в дереве документа — getComputedStyle неверен). */
function bcUnderlineFromStyleAttr(el) {
  const st = String(el?.getAttribute?.('style') || '')
  return (
    /\btext-decoration-line\s*:\s*[^;'"]*\bunderline\b/i.test(st) ||
    /\btext-decoration\s*:\s*[^;'"]*\bunderline\b/i.test(st)
  )
}

function bcElementUnderlineInRenderedEditor(spanEl) {
  if (!(spanEl instanceof HTMLElement)) return false
  if (bcUnderlineFromStyleAttr(spanEl)) return true
  if (!spanEl.isConnected) return false
  try {
    const cs = window.getComputedStyle(spanEl)
    const line = `${cs.textDecorationLine || ''} ${cs.textDecoration || ''}`
    return line.includes('underline')
  } catch {
    return false
  }
}

/** span с underline после execCommand → <u>, иначе нормализация удаляет оформление. */
function bcCoerceUnderlineSpansToU(root) {
  if (!(root instanceof HTMLElement)) return
  const spans = root.querySelectorAll('span')
  for (let i = spans.length - 1; i >= 0; i -= 1) {
    const sp = spans.item(i)
    if (!(sp instanceof HTMLElement)) continue
    if (String(sp.getAttribute('data-spoiler') || '') === '1') continue
    if (!bcElementUnderlineInRenderedEditor(sp)) continue
    const u = document.createElement('u')
    while (sp.firstChild) u.appendChild(sp.firstChild)
    sp.parentNode?.replaceChild(u, sp)
  }
}

function bcNormalizeHtmlForTelegram(raw) {
  return normalizeHtmlForTelegram(String(raw ?? ''))
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
  const el = bcResolveBodyEditor()
  if (!el) return
  el.focus()
  if (cmd === 'underline') {
    try {
      document.execCommand('styleWithCSS', false, false)
    } catch {
      //
    }
  }
  document.execCommand(cmd, false)
  if (cmd === 'underline') bcCoerceUnderlineSpansToU(el)
  bcUpdateFormatState()
  bcSyncEditorHtml()
  bcRecordHistory()
}


function bcFormatBold() { bcExec('bold') }
function bcFormatItalic() { bcExec('italic') }
function bcFormatUnderline() { bcExec('underline') }
function bcFormatStrike() { bcExec('strikeThrough') }
function bcFormatSpoiler() {
  const el = bcResolveBodyEditor()
  if (!el) return
  el.focus()
  const range = bcCurrentRange()
  if (!range) {
    bcEditorShowHint(tt('admin.broadcast_editor.select_text_spoiler'))
    return
  }
  let n = range.commonAncestorContainer
  if (n.nodeType === Node.TEXT_NODE) n = n.parentElement
  const spoiler = n?.closest?.('[data-spoiler="1"], tg-spoiler')
  if (spoiler && el.contains(spoiler)) {
    if (range.collapsed) {
      editorUnwrapElementFully(spoiler)
    } else if (!bcSelectedTextFromRange(range).trim()) {
      bcEditorShowHint(tt('admin.broadcast_editor.select_text_spoiler'))
      return
    } else if (!editorUnwrapRangeInsideContainer(spoiler, range)) {
      bcEditorShowHint(tt('admin.broadcast_editor.select_text_spoiler'))
      return
    }
    bcSyncEditorHtml()
    bcRecordHistory()
    bcSavedTick.value = false
    bcUpdateFormatState()
    return
  }
  if (!bcWrapRange(range, '<span data-spoiler="1">', '</span>')) {
    bcEditorShowHint(tt('admin.broadcast_editor.select_text_spoiler'))
    return
  }
  bcSavedTick.value = false
  bcUpdateFormatState()
}
function bcFormatPre() {
  const el = bcResolveBodyEditor()
  if (!el) return
  el.focus()
  const range = bcCurrentRange()
  if (!range) {
    bcEditorShowHint(tt('admin.broadcast_editor.select_text_pre'))
    return
  }
  if (
    !editorApplyMonospaceFormat(el, range, {
      onEmpty: () => bcEditorShowHint(tt('admin.broadcast_editor.select_text_pre')),
    })
  ) {
    return
  }
  bcSyncEditorHtml()
  bcRecordHistory()
  bcSavedTick.value = false
  bcUpdateFormatState()
}
function bcFormatBlockquote() {
  const el = bcResolveBodyEditor()
  if (!el) return
  el.focus()
  const range = bcCurrentRange()
  if (!range) {
    bcEditorShowHint(tt('admin.broadcast_editor.select_text_quote'))
    return
  }
  let n = range.commonAncestorContainer
  if (n.nodeType === Node.TEXT_NODE) n = n.parentElement
  const bq = n?.closest?.('blockquote')
  if (bq && el.contains(bq)) {
    if (range.collapsed) {
      editorUnwrapElementFully(bq)
    } else if (!bcSelectedTextFromRange(range).trim()) {
      bcEditorShowHint(tt('admin.broadcast_editor.select_text_quote'))
      return
    } else if (!editorUnwrapRangeInsideContainer(bq, range)) {
      bcEditorShowHint(tt('admin.broadcast_editor.select_text_quote'))
      return
    }
    bcSyncEditorHtml()
    bcRecordHistory()
    bcSavedTick.value = false
    bcUpdateFormatState()
    return
  }
  if (!bcWrapRange(range, '<blockquote>', '</blockquote>')) {
    bcEditorShowHint(tt('admin.broadcast_editor.select_text_quote'))
    return
  }
  bcSavedTick.value = false
  bcUpdateFormatState()
}
function bcClearFormatting() {
  const el = bcResolveBodyEditor()
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
function bcFormatLink() {
  const el = bcResolveBodyEditor()
  if (!el) return
  el.focus()
  const sel = window.getSelection?.()
  const range = sel && sel.rangeCount ? sel.getRangeAt(0).cloneRange() : bcSavedRange.value
  let n = range?.commonAncestorContainer
  if (n && n.nodeType === Node.TEXT_NODE) n = n.parentElement
  const linkEl = n?.closest?.('a')
  if (linkEl && el.contains(linkEl)) {
    try {
      const rg = document.createRange()
      rg.selectNodeContents(linkEl)
      sel?.removeAllRanges()
      sel?.addRange(rg)
      document.execCommand('unlink', false, null)
    } catch {
      //
    }
    bcSyncEditorHtml()
    bcRecordHistory()
    bcSavedTick.value = false
    bcUpdateFormatState()
    return
  }
  const selectedText = bcSelectedTextFromRange(range)
  if (!selectedText.trim()) {
    bcEditorShowHint(tt('admin.broadcast_editor.select_text_link'))
    return
  }
  bcLinkRange.value = range || null
  bcLinkUrl.value = ''
  bcLinkModalOpen.value = true
}

function bcApplyLinkModal() {
  const href = String(bcLinkUrl.value || '').trim()
  const hrefOk = /^https?:\/\//i.test(href) || /^tg:\/\//i.test(href) || /^mailto:/i.test(href)
  if (!hrefOk) {
    bcEditorShowHint(tt('admin.broadcast_editor.link_url_invalid'))
    return
  }
  const el = bcResolveBodyEditor()
  if (!el) return
  const range = bcLinkRange.value || bcCurrentRange()
  const selectedText = bcSelectedTextFromRange(range)
  if (!selectedText.trim()) {
    bcEditorShowHint(tt('admin.broadcast_editor.select_text_link'))
    return
  }
  const sel = window.getSelection?.()
  el.focus()
  if (range && sel) {
    sel.removeAllRanges()
    sel.addRange(range)
    range.deleteContents()
    const a = document.createElement('a')
    a.href = href
    a.textContent = selectedText
    a.style.textDecoration = 'none'
    a.style.textDecorationLine = 'none'
    a.setAttribute('data-bc-link', '1')
    while (a.parentElement && String(a.parentElement.tagName || '').toLowerCase() === 'u') {
      const u = a.parentElement
      u.parentNode?.insertBefore(a, u)
      if (!String(u.textContent || '').trim()) u.remove()
    }
    range.insertNode(a)
    range.setStartAfter(a)
    range.collapse(true)
    sel.removeAllRanges()
    sel.addRange(range)
    bcSavedRange.value = range.cloneRange()
  }
  sanitizeEditorLinksNoUnderline(el)
  bcSyncEditorHtml()
  bcRecordHistory()
  bcSavedTick.value = false
  bcLinkModalOpen.value = false
  bcLinkRange.value = null
  bcLinkUrl.value = ''
}

function onBcEditInput(ev) {
  const el = ev?.target
  if (el instanceof HTMLElement) sanitizeEditorLinksNoUnderline(el)
  bcEditBodyHtml.value = bcNormalizeHtmlForTelegram(String(el?.innerHTML || ''))
}

function onBcEmojiClick(ev) {
  const unicode = ev?.detail?.unicode
  if (!unicode) return
  const el = bcResolveBodyEditor()
  if (!el) return
  el.focus()
  bcInsertHtmlAtCursor(unicode)
  bcSavedTick.value = false
}

function onBcEditorInput(ev) {
  const el = ev?.target
  if (el instanceof HTMLElement) sanitizeEditorLinksNoUnderline(el)
  bcBodyHtml.value = bcNormalizeHtmlForTelegram(String(el?.innerHTML || ''))
  bcSavedTick.value = false
  bcRecordHistory()
  bcSaveLocalSnapshot()
  nextTick(() => {
    if (el instanceof HTMLElement) sanitizeEditorLinksNoUnderline(el)
  })
}

/** Вставка из буфера: берём plain text и кладём в редактор как текст + &lt;br&gt;, без «слоя» Chrome div/br, которые дают лишние пустые строки. */
function bcInsertPlainTextAtCursor(ed, plain) {
  const lines = String(plain ?? '').replace(/\r\n/g, '\n').split('\n')
  const sel = window.getSelection?.()
  if (!ed || !sel?.rangeCount) return false
  const range = sel.getRangeAt(0)
  if (!ed.contains(range.commonAncestorContainer)) return false
  range.deleteContents()
  const frag = document.createDocumentFragment()
  lines.forEach((ln, i) => {
    frag.appendChild(document.createTextNode(ln))
    if (i < lines.length - 1) frag.appendChild(document.createElement('br'))
  })
  const last = frag.lastChild
  if (!last) return false
  range.insertNode(frag)
  try {
    range.setStartAfter(last)
    range.collapse(true)
    sel.removeAllRanges()
    sel.addRange(range)
  } catch {
    //
  }
  bcSavedRange.value = range.cloneRange()
  return true
}

function bcOnEditorPaste(ev) {
  const el = bcResolveBodyEditor()
  if (!el || ev?.defaultPrevented) return
  const t = ev.target
  if (t !== el && !el.contains(t)) return
  const dt = ev.clipboardData
  if (!dt || dt.files?.length) return
  let plain = ''
  try {
    plain = dt.getData('text/plain')
  } catch {
    plain = ''
  }
  // Пустая вставка с HTML только — оставляем поведение браузера (редко нужна «богатая» вставка).
  if (plain === '' && dt.types?.includes('text/html')) return
  if (plain === null) return
  ev.preventDefault()
  if (!bcInsertPlainTextAtCursor(el, plain)) return
  bcSyncEditorHtml()
  bcSavedTick.value = false
  bcRecordHistory(true)
  if (!bcEditModalOpen.value || el !== bcEditBodyRef.value) {
    bcSaveLocalSnapshot()
  }
  nextTick(() => bcUpdateFormatState())
}

function onBcEditorClick(ev) {
  const el = ev?.target
  if (!(el instanceof HTMLElement)) return
  const spoiler = el.closest('[data-spoiler="1"], tg-spoiler')
  if (!spoiler) return
  spoiler.classList.add('reveal')
  window.setTimeout(() => spoiler.classList.remove('reveal'), 5000)
}

function bcResetTypingFormatsAtCaret(root) {
  editorResetTypingExecCommands(root, { coerceUnderlineSpans: bcCoerceUnderlineSpansToU })
}

function bcOnEditorKeydown(e) {
  const root = e.currentTarget
  if (!(root instanceof HTMLElement)) return
  if (e.key === 'Enter' && e.shiftKey && !e.isComposing) {
    if (editorSoftBreakInsideBlockquote(root)) {
      e.preventDefault()
      e.stopPropagation()
      bcSyncEditorHtml()
      bcRecordHistory(true)
      bcSaveLocalSnapshot()
      bcSavedTick.value = false
      requestAnimationFrame(() => {
        bcResetTypingFormatsAtCaret(root)
        bcUpdateFormatState()
      })
    }
    return
  }
  if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return
  if (editorSplitBlockquoteAtCaret(root, editorPlaceCaretAtEditableStart)) {
    e.preventDefault()
    e.stopPropagation()
    bcSyncEditorHtml()
    bcRecordHistory(true)
    bcSaveLocalSnapshot()
    bcSavedTick.value = false
    requestAnimationFrame(() => {
      bcResetTypingFormatsAtCaret(root)
      bcUpdateFormatState()
    })
    return
  }
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      bcResetTypingFormatsAtCaret(root)
      bcSyncEditorHtml()
      bcSaveLocalSnapshot()
      bcSavedTick.value = false
      bcUpdateFormatState()
    })
  })
}

function onBcEditorSelectionChange() {
  const sel = window.getSelection?.()
  if (!sel || !sel.rangeCount) return
  const range = sel.getRangeAt(0)
  const editors = bcBodyEditors()
  const editor = editors.find((el) => el && typeof el.contains === 'function' && el.contains(range.startContainer))
  if (!editor) return
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
  let quote = false
  try {
    const sel = window.getSelection?.()
    if (sel?.rangeCount) {
      const r = sel.getRangeAt(0)
      let n = r.commonAncestorContainer
      if (n.nodeType === Node.TEXT_NODE) n = n.parentElement
      const qn = n?.closest?.('blockquote')
      const ed = bcResolveBodyEditor()
      quote = !!(qn && ed && ed.contains(qn))
    }
  } catch {
    quote = false
  }
  try {
    bcFormatState.value = {
      bold: !!document.queryCommandState('bold'),
      italic: !!document.queryCommandState('italic'),
      underline: !!document.queryCommandState('underline'),
      strike: !!document.queryCommandState('strikeThrough'),
      spoiler: !!bcActiveSpoilerText.value,
      link: !!bcActiveLinkUrl.value,
      quote,
    }
  } catch {
    bcFormatState.value = {
      bold: false,
      italic: false,
      underline: false,
      strike: false,
      spoiler: false,
      link: false,
      quote: false,
    }
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
  if (s === 'new') return tt('admin.user_billing.payout_status_new')
  if (s === 'paid') return tt('admin.user_billing.payout_status_paid')
  if (s === 'rejected') return tt('admin.user_billing.payout_status_rejected')
  return s || tt('admin.user_billing.payout_status_unknown')
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
    alert(tt('admin.dlg.link_unavailable'))
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
    alert(tt('admin.dlg.open_link_failed'))
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
      window.alert(tt('admin.dlg.user_not_in_list_preview'))
    }
  }
}

async function goToAdminUserInList(telegramId) {
  const id = Number(telegramId || 0)
  if (!id) return
  usersScrollTargetTelegramId.value = id
  goAdminEmbed('users')
  await loadUsers()
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

function adminUserPromoDurationLabel(u) {
  const daysLeft = Number(u?.promo_days_left || 0)
  if (daysLeft > 0) return tt('admin.user_billing.promo_days', { n: daysLeft })
  const purpose = String(u?.promo_purpose || '').trim()
  if (localeIsEn()) {
    const m = purpose.match(/for\s+(\d+)\s*(?:day|days)?/i) || purpose.match(/(\d+)\s*d\b/i)
    if (m) return tt('admin.user_billing.promo_days', { n: Number(m[1] || 0) })
    return ''
  }
  const m = purpose.match(/на\s+(\d+)\s*дн/i)
  if (m) return tt('admin.user_billing.promo_days', { n: Number(m[1] || 0) })
  return ''
}

function adminUserPaymentLabel(u) {
  const promoCode = String(u?.promo_applied_code || '').trim()
  if (promoCode) {
    const dur = adminUserPromoDurationLabel(u)
    return dur ? tt('admin.user_billing.promo_code_dur', { code: promoCode, dur }) : tt('admin.user_billing.promo_code', { code: promoCode })
  }
  const p = String(u?.payment_method_type || '').toLowerCase()
  if (p.includes('card')) return tt('admin.user_billing.yookassa_card')
  if (p.includes('sbp')) return tt('admin.user_billing.yookassa_sbp')
  if (p.includes('yoo_money')) return tt('admin.user_billing.yookassa')
  if (p) return tt('admin.user_billing.yookassa_raw', { method: p })
  if (u?.payment_method_bound) return tt('admin.user_billing.yookassa')
  return tt('admin.user_billing.never_paid')
}

async function openAdminUserInfo(userRow) {
  selectedAdminUser.value = userRow || null
  showUserInfoModal.value = !!userRow
}

function adminNavSnapshot() {
  return {
    tab: String(tab.value || 'overview'),
    chatsOwnerFilter: Number(chatsOwnerFilter.value || 0),
    usersPreset: String(usersPreset.value || 'all'),
    adminOverviewEmbed: String(adminOverviewEmbed.value || ''),
  }
}

function applyAdminNavState(state) {
  if (!state) return
  navRestoring.value = true
  tab.value = String(state.tab || 'overview')
  chatsOwnerFilter.value = Number(state.chatsOwnerFilter || 0)
  usersPreset.value = String(state.usersPreset || 'all')
  adminOverviewEmbed.value = String(state.adminOverviewEmbed || '')
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
  if (p === '7d') return tt('admin.revenue_period.d7')
  if (p === '30d') return tt('admin.revenue_period.d30')
  if (p === '90d') return tt('admin.revenue_period.d90')
  if (p === '12m') return tt('admin.revenue_period.m12')
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
  const canRead = showFullAdminShell.value || isOwnerCabinet.value
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
    } else if (isOwnerCabinet.value) {
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
      ? tt('admin.pulse.api_url_current', { url: guardApiBaseEffective.value })
      : tt('admin.pulse.api_url_missing')
    opsHealth.value = {
      status: 'unknown',
      load_failed: true,
      load_error_human: human,
      diagnostics: [tt('admin.pulse.load_failed_intro'), urlHint, human],
      activity_by_hour: [],
    }
  }
  opsLoading.value = false
  void loadDiagnosticsSummary()
}

function incidentCategoryLabel(cat) {
  const key = String(cat || '').toLowerCase()
  const path = `admin.pulse.category_${key}`
  if (te(path)) return tt(path)
  return cat || '—'
}

function formatDbPingMs(ms) {
  const n = Number(ms)
  if (!Number.isFinite(n) || n < 0) return '—'
  const t = n < 10 ? n.toFixed(2) : n < 100 ? n.toFixed(1) : String(Math.round(n))
  const localized = localeIsEn() ? t : t.replace('.', ',')
  return tt('admin.pulse.time_ms', { n: localized })
}

function formatServerUptime(sec) {
  const s = Math.max(0, Math.floor(Number(sec) || 0))
  if (s < 60) return tt('admin.pulse.uptime_seconds', { s })
  const m = Math.floor(s / 60)
  if (m < 60) return tt('admin.pulse.uptime_minutes', { m })
  const h = Math.floor(m / 60)
  const rm = m % 60
  return rm ? tt('admin.pulse.uptime_hours_min', { h, rm }) : tt('admin.pulse.uptime_hours', { h })
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
  const title = prompt(tt('admin.dlg.msg_prompt_title'))
  if (!title) return
  const body = prompt(tt('admin.dlg.msg_prompt_body'))
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
  if (!confirm(tt('admin.dlg.msg_delete_confirm', { title: item.title || item.template_key }))) return
  await fetch(() => api.adminMessageTemplateDelete(item.id))
  msgTemplates.value = msgTemplates.value.filter((x) => Number(x.id || 0) !== Number(item.id || 0))
}

async function runOpsAction(action) {
  const key =
    action === 'restart_api'
      ? 'ops_restart_api_confirm'
      : action === 'restart_webapp'
        ? 'ops_restart_webapp_confirm'
        : action === 'restart_bot'
          ? 'ops_restart_bot_confirm'
          : 'ops_restart_other_confirm'
  if (!window.confirm(tt(`admin.dlg.${key}`))) return
  opsActionLoading.value = action
  try {
    await fetch(() => api.adminOpsAction(action))
    await loadOpsHealth()
    if (action === 'restart_webapp') {
      if (window.confirm(tt('admin.dlg.ops_webapp_reload_confirm'))) {
        window.location.reload()
      }
    } else if (action === 'restart_api') {
      window.alert(tt('admin.dlg.ops_api_restarting'))
    } else {
      window.alert(tt('admin.dlg.ops_bot_restarting'))
    }
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.ops_action_failed')))
  } finally {
    opsActionLoading.value = ''
  }
}

async function setPayoutStatus(item, status) {
  if (status === 'paid') {
    const ok = window.confirm(tt('admin.dlg.payout_confirm_paid'))
    if (!ok) return
  }
  actionLoadingId.value = Number(item?.id || 0)
  try {
    await fetch(() => api.adminSetPayoutStatus(item.id, status))
    await Promise.all([loadPayouts(), loadCommissions()])
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.payout_status_failed')))
  } finally {
    actionLoadingId.value = 0
  }
}

async function resetUserFinance(item) {
  const tgId = Number(item?.telegram_id || 0)
  if (!tgId) return
  const nm = String(item?.first_name || item?.username || tgId || '').trim() || String(tgId)
  const ok = window.confirm(tt('admin.dlg.user_reset_finance_confirm', { name: nm }))
  if (!ok) return
  try {
    await fetch(() => api.adminResetUserFinance(tgId))
    await loadUsers()
    await Promise.all([loadOverview(), loadPayouts(), loadReferralsTop(), loadCommissions(), loadMyPartnerPayouts(), loadMyPartnerStats()])
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.user_reset_finance_fail')))
  }
}

async function deleteBlockUser(item) {
  const tgId = Number(item?.telegram_id || 0)
  if (!tgId) return
  const nm = String(item?.first_name || item?.username || tgId || '').trim() || String(tgId)
  const ok = window.confirm(tt('admin.dlg.user_delete_block_confirm', { name: nm }))
  if (!ok) return
  try {
    await fetch(() => api.adminDeleteBlockUser(tgId))
    await Promise.all([loadUsers(), loadChats(), loadOverview()])
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.user_delete_block_fail')))
  }
}

async function unblockUser(item) {
  const tgId = Number(item?.telegram_id || 0)
  if (!tgId) return
  const nm = String(item?.first_name || item?.username || tgId || '').trim() || String(tgId)
  const ok = window.confirm(tt('admin.dlg.user_unblock_confirm', { name: nm }))
  if (!ok) return
  try {
    await fetch(() => api.adminUnblockUser(tgId))
    await loadUsers()
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.user_unblock_fail')))
  }
}

async function resetUserDelegation(item) {
  const tgId = Number(item?.telegram_id || 0)
  if (!tgId) return
  const nm = String(item?.first_name || item?.username || tgId || '').trim() || String(tgId)
  const ok = window.confirm(tt('admin.dlg.user_remove_delegation_confirm', { name: nm }))
  if (!ok) return
  try {
    await fetch(() => api.adminUserResetDelegation(tgId))
    await loadUsers()
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.user_remove_delegation_fail')))
  }
}

async function resetUserConnectedChats(item) {
  const tgId = Number(item?.telegram_id || 0)
  if (!tgId) return
  const nm = String(item?.first_name || item?.username || tgId || '').trim() || String(tgId)
  const ok = window.confirm(tt('admin.dlg.user_reset_chats_confirm', { name: nm }))
  if (!ok) return
  try {
    await fetch(() => api.adminUserResetConnectedChats(tgId))
    await Promise.all([loadUsers(), loadChats(), loadOverview()])
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.user_reset_chats_fail')))
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
    alert(tt('admin.dlg.user_join_report_saved'))
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.user_join_report_save_failed')))
  }
}

function resolveTestTargetTelegramId() {
  const raw = String(testTargetTelegramId.value || '').trim()
  if (!raw) return null
  const id = Number(raw)
  return Number.isFinite(id) && id > 0 ? id : null
}

async function createAdminTestSubscription(months) {
  const okPin = await requestPinIfNeeded('payments')
  if (!okPin) {
    if (shouldAskPinForAction('payments')) alert(tt('admin.broadcast_send.pin_required'))
    return
  }
  testPayLoading.value = true
  try {
    const targetId = resolveTestTargetTelegramId()
    const r = await fetch(() => api.adminTestCreateSubscriptionPayment(months, targetId))
    const url = String(r?.confirmation_url || '')
    if (!url) throw new Error(tt('admin.dlg.pay_no_url'))
    const tg = window.Telegram?.WebApp
    if (typeof tg?.openLink === 'function') tg.openLink(url, { try_instant_view: false })
    else window.open(url, '_blank', 'noopener,noreferrer')
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.test_sub_failed')))
  } finally {
    testPayLoading.value = false
  }
}

async function createAdminTestTokens(tokens) {
  const okPin = await requestPinIfNeeded('payments')
  if (!okPin) {
    if (shouldAskPinForAction('payments')) alert(tt('admin.broadcast_send.pin_required'))
    return
  }
  testPayLoading.value = true
  try {
    const targetId = resolveTestTargetTelegramId()
    const r = await fetch(() => api.adminTestCreateTokensPayment(tokens, targetId))
    const url = String(r?.confirmation_url || '')
    if (!url) throw new Error(tt('admin.dlg.pay_no_url'))
    const tg = window.Telegram?.WebApp
    if (typeof tg?.openLink === 'function') tg.openLink(url, { try_instant_view: false })
    else window.open(url, '_blank', 'noopener,noreferrer')
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.test_tokens_failed')))
  } finally {
    testPayLoading.value = false
  }
}

async function createAdminBindingProbe(mode = 'live') {
  const okPin = await requestPinIfNeeded('payments')
  if (!okPin) {
    if (shouldAskPinForAction('payments')) alert(tt('admin.broadcast_send.pin_required'))
    return
  }
  testPayLoading.value = true
  try {
    const targetId = resolveTestTargetTelegramId()
    const r = await fetch(() => api.adminTestCreateBindingProbePayment(targetId, mode))
    const url = String(r?.confirmation_url || '')
    if (!url) throw new Error(tt('admin.dlg.pay_no_url'))
    const tg = window.Telegram?.WebApp
    if (typeof tg?.openLink === 'function') tg.openLink(url, { try_instant_view: false })
    else window.open(url, '_blank', 'noopener,noreferrer')
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.test_probe_failed')))
  } finally {
    testPayLoading.value = false
  }
}

const BC_TME_HOSTS = new Set(['t.me', 'telegram.me', 'telegram.dog'])

function bcNormalizeTelegramUsername(raw) {
  let s = String(raw || '').trim()
  if (!s) return ''
  s = s.replace(/^https?:\/\//i, '')
  s = s.replace(/^(t\.me|telegram\.me|telegram\.dog)\//i, '')
  s = s.replace(/^@+/, '')
  s = s.split(/[/?#]/)[0]
  return s.trim()
}

function bcParsePrefilledDmUrl(url) {
  const raw = String(url || '').trim()
  if (!raw) return null
  try {
    const withProto = /^https?:\/\//i.test(raw) ? raw : `https://${raw.replace(/^\/\//, '')}`
    const u = new URL(withProto)
    const host = u.hostname.toLowerCase().replace(/^www\./, '')
    if (!BC_TME_HOSTS.has(host)) return null
    const username = bcNormalizeTelegramUsername(u.pathname)
    if (!username || username === 'share') return null
    const prefill = u.searchParams.get('text')
    if (prefill == null || prefill === '') return null
    return { dm_username: username, dm_prefill_text: prefill }
  } catch {
    return null
  }
}

function bcBuildPrefilledDmUrl(username, prefillText) {
  const user = bcNormalizeTelegramUsername(username)
  const body = String(prefillText || '').trim()
  if (!user || !body) return ''
  return `https://t.me/${user}?text=${encodeURIComponent(body)}`
}

function bcEmptyButton() {
  return {
    kind: 'default',
    text: '',
    url: '',
    web_app_url: '',
    callback_data: '',
    style: '',
    non_member_text: '',
    member_text: '',
    dm_username: '',
    dm_prefill_text: '',
  }
}

function bcEmptyHiddenContinuationButton() {
  return {
    kind: 'hidden_continuation',
    text: '',
    url: '',
    web_app_url: '',
    callback_data: '',
    style: '',
    non_member_text: '',
    member_text: '',
    dm_username: '',
    dm_prefill_text: '',
  }
}

function bcEmptyPrefilledDmButton() {
  return {
    kind: 'prefilled_dm',
    text: '',
    url: '',
    web_app_url: '',
    callback_data: '',
    style: '',
    non_member_text: '',
    member_text: '',
    dm_username: '',
    dm_prefill_text: '',
  }
}

const BC_BUTTON_STYLE_OPTIONS = [
  { id: '', labelKey: 'admin.broadcast_ui.btn_style_default' },
  { id: 'primary', labelKey: 'admin.broadcast_ui.btn_style_primary' },
  { id: 'success', labelKey: 'admin.broadcast_ui.btn_style_success' },
  { id: 'danger', labelKey: 'admin.broadcast_ui.btn_style_danger' },
]

function bcButtonStylePreviewClass(style) {
  const s = String(style || '').trim().toLowerCase()
  if (s === 'primary') return 'bg-sky-500 ring-1 ring-sky-300/45'
  if (s === 'success') return 'bg-emerald-500 ring-1 ring-emerald-300/45'
  if (s === 'danger') return 'bg-rose-500 ring-1 ring-rose-300/45'
  return 'bg-slate-500 ring-1 ring-white/25'
}

function bcButtonStyleChipClass(style, kind = 'default') {
  const s = String(style || '').trim().toLowerCase()
  const k = String(kind || 'default').trim().toLowerCase()
  const layout = 'rounded-lg border px-2.5 py-1.5 text-center font-semibold shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]'
  if (s === 'primary') return `${layout} border-sky-400/55 bg-sky-600 text-white`
  if (s === 'success') return `${layout} border-emerald-400/55 bg-emerald-600 text-white`
  if (s === 'danger') return `${layout} border-rose-400/55 bg-rose-600 text-white`
  if (k === 'hidden_continuation') return `${layout} border-cyan-400/40 bg-cyan-950/75 text-cyan-100`
  if (k === 'prefilled_dm') return `${layout} border-sky-400/40 bg-sky-950/75 text-sky-100`
  return `${layout} border-white/12 bg-slate-700/90 text-slate-100`
}

function bcKeyboardRowsFromApi(kbd) {
  const rows = kbd?.rows
  if (!rows?.length) return [[bcEmptyButton()]]
  return rows.map((row) =>
    row.map((b) => {
      const hc = b?.hidden_continuation
      if (hc && (hc.non_member_text || hc.member_text)) {
        return {
          kind: 'hidden_continuation',
          text: b.text || '',
          url: '',
          web_app_url: '',
          callback_data: '',
          style: b.style || '',
          non_member_text: hc.non_member_text || '',
          member_text: hc.member_text || '',
          dm_username: '',
          dm_prefill_text: '',
        }
      }
      const parsedDm = b.url ? bcParsePrefilledDmUrl(b.url) : null
      if (parsedDm) {
        return {
          kind: 'prefilled_dm',
          text: b.text || '',
          url: '',
          web_app_url: '',
          callback_data: '',
          style: b.style || '',
          non_member_text: '',
          member_text: '',
          dm_username: parsedDm.dm_username,
          dm_prefill_text: parsedDm.dm_prefill_text,
        }
      }
      return {
        kind: 'default',
        text: b.text || '',
        url: b.url || '',
        web_app_url: b.web_app?.url || '',
        callback_data: b.callback_data || '',
        style: b.style || '',
        non_member_text: '',
        member_text: '',
        dm_username: '',
        dm_prefill_text: '',
      }
    }),
  )
}

function bcBuildKeyboardPayload() {
  const out = []
  for (const row of bcButtonRows.value) {
    const line = []
    for (const b of row) {
      const text = String(b.text || '').trim()
      if (!text) continue
      const style = String(b.style || '').trim().toLowerCase()
      const kind = String(b.kind || 'default').trim()
      let item = null
      if (kind === 'hidden_continuation') {
        const nonMember = String(b.non_member_text || '').trim()
        const member = String(b.member_text || '').trim()
        if (!nonMember && !member) continue
        item = {
          text,
          hidden_continuation: {
            non_member_text: nonMember,
            member_text: member,
          },
        }
      } else if (kind === 'prefilled_dm') {
        const url = bcBuildPrefilledDmUrl(b.dm_username, b.dm_prefill_text)
        if (!url) continue
        item = { text, url }
      } else {
        const url = String(b.url || '').trim()
        const wu = String(b.web_app_url || '').trim()
        const cb = String(b.callback_data || '').trim()
        if (url) item = { text, url }
        else if (wu) item = { text, web_app_url: wu }
        else if (cb) item = { text, callback_data: cb }
      }
      if (!item) continue
      if (['primary', 'success', 'danger'].includes(style)) item.style = style
      line.push(item)
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
  const bodyMax = bcCurrentMaxLen()
  if (normalizedBody.length > bodyMax) {
    throw new Error(tt('admin.dlg.bc_text_too_long', { max: bodyMax }))
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

async function loadRecentSendEvents(opts = {}) {
  const silent = Boolean(opts?.silent)
  try {
    const r = silent
      ? await fetchSilent(() => api.adminBroadcastRecentSendEvents(80))
      : await fetch(() => api.adminBroadcastRecentSendEvents(80))
    bcRecentSendEvents.value = Array.isArray(r?.items) ? r.items : []
  } catch {
    if (!silent) bcRecentSendEvents.value = []
  }
}

async function loadBroadcasts(opts = {}) {
  const silent = Boolean(opts?.silent)
  if (!silent) bcLoading.value = true
  try {
    const listScope =
      bcBroadcastDraftListScope.value === 'all' && bcBroadcastCanScopeAll.value ? 'all' : 'mine'
    const r = await fetch(() => api.adminBroadcasts(listScope))
    broadcasts.value = r?.items || []
    await loadRecentSendEvents({ silent: true })
    if (r?.scope === 'mine' && bcBroadcastDraftListScope.value === 'all') {
      bcBroadcastDraftListScope.value = 'mine'
    }
  } catch {
    if (!silent) broadcasts.value = []
  } finally {
    if (!silent) bcLoading.value = false
    if (!silent) await loadAutopostCampaigns()
  }
  bcCampaignUxPruneStalePostIds()
  if (!silent) await prefetchBcDraftListThumbs()
  if (silent) return

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

async function loadAutopostCampaigns(opts = {}) {
  const silent = !!opts.silent
  try {
    const r = silent
      ? await fetchSilent(() => api.adminAutopostCampaigns())
      : await fetch(() => api.adminAutopostCampaigns())
    if (Array.isArray(r?.items)) bcAutopostCampaigns.value = r.items
    else if (!silent) bcAutopostCampaigns.value = []
  } catch {
    if (!silent) bcAutopostCampaigns.value = []
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
    bcSetBodyEditorHtml(bcBodyHtml.value || '')
    bcHistory.value = [String(bcResolveBodyEditor()?.innerHTML || '')]
    bcHistoryIndex.value = 0
    bcUpdateFormatState()
    bcSaveLocalSnapshot()
    loadBcMediaThumbnails()
  })
}

async function createBcDraft(cabinetScope = null) {
  try {
    const body = {
      title: '',
      body_text: '',
      parse_mode: BC_PARSE_MODE,
      keyboard_rows: [],
    }
    if (cabinetScope === 'autopost' || cabinetScope === 'oneshot') {
      body.cabinet_draft_scope = cabinetScope
    }
    const r = await fetch(() => api.adminBroadcastCreate(body))
    upsertBroadcastInList(r)
    applyBroadcastToForm(r)
    void prefetchBcDraftListThumbs()
    return true
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.bc_create_failed')))
    return false
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
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.save_failed')))
  } finally {
    bcSaving.value = false
  }
  return ok
}

async function saveBcAuxKeyboardModal() {
  if (bcSelectedId.value) {
    const ok = await saveBcDraft()
    if (!ok) return
  }
  bcAuxModal.value = ''
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
    const shouldSave = window.confirm(tt('admin.dlg.bc_save_before_exit_confirm'))
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
  const title = String(bcTitle.value ?? '').trim().slice(0, 255) || tt('admin.dlg.bc_draft_fallback_title')
  bcSavingTitleId.value = id
  try {
    const r = await fetch(() => api.adminBroadcastPatch(id, { title }))
    upsertBroadcastInList(r)
    bcTitle.value = String(r?.title ?? title)
    bcQuickTitleBaseline.value = String(bcTitle.value)
    bcSaveLocalSnapshot()
    bcSavedTick.value = true
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.bc_title_save_failed')))
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
  const rowFromList = (broadcasts.value || []).find((b) => Number(b?.id || 0) === bid)
  const needsFull =
    !sourceRows.length ||
    sourceRows.some((m) => !Number(m?.id)) ||
    !!(rowFromList?.has_media_file || rowFromList?.telegram_file_id) ||
    String(rowFromList?.media_kind || bcMediaKindStored.value || 'none').toLowerCase() !== 'none'
  if (needsFull) {
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
  if (!window.confirm(tt('admin.dlg.bc_remove_media_confirm'))) return
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
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.generic_error')))
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
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.upload_failed')))
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
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.bc_delete_media_failed')))
  }
}

async function deleteBcDraft() {
  const id = bcSelectedId.value
  if (!id) return
  if (!window.confirm(tt('admin.dlg.bc_delete_draft_confirm'))) return
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
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.bc_delete_failed')))
  }
}

async function deleteBcDraftItem(item) {
  const id = Number(item?.id || 0)
  if (!id) return
  if (!window.confirm(tt('admin.dlg.bc_delete_draft_confirm_this'))) return
  try {
    await fetch(() => api.adminBroadcastDelete(id))
    broadcasts.value = (broadcasts.value || []).filter((b) => Number(b?.id || 0) !== id)
    bcCampaignUxPruneStalePostIds()
    if (Number(bcSelectedId.value || 0) === id) {
      bcSelectedId.value = null
      bcEditorOpen.value = false
    }
    await loadBroadcasts()
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.bc_delete_failed')))
  }
}

async function deleteBcDraftById(id) {
  const bid = Number(id || 0)
  if (!bid) return
  if (!window.confirm(tt('admin.dlg.bc_delete_draft_confirm_this'))) return
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
    bcCampaignUxPruneStalePostIds()
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.bc_delete_failed')))
  }
}

async function sendBc(target = 'users') {
  if (isBroadcastShellLite.value && target !== 'groups') {
    alert(
      isDelegatedFreeBroadcastCabinet.value ? tt('admin.dlg.bc_send_lite_delegated') : tt('admin.dlg.bc_send_lite_owner'),
    )
    return
  }
  const id = bcSelectedId.value
  if (!id) return
  let quote = null
  try {
    quote = await fetch(() => api.adminBroadcastQuote(id, target, []))
  } catch (e) {
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.bc_quote_failed')))
    return
  }
  if (quote?.broadcast_charge_applies && Number(quote.cost_tokens || 0) > 0 && quote.can_afford === false) {
    alert(
      tt('admin.broadcast_send.aurum_topup_long', {
        need: Number(quote.cost_tokens || 0),
        have: Number(quote.spendable_credits || 0),
      }),
    )
    return
  }
  const titleByTarget =
    target === 'groups'
      ? tt('admin.broadcast_send.send_confirm_all_groups')
      : target === 'all'
        ? tt('admin.broadcast_send.send_confirm_all_mixed')
        : tt('admin.broadcast_send.send_confirm_all_users')
  const costHint =
    quote?.broadcast_charge_applies && Number(quote.cost_tokens || 0) > 0
      ? tt('admin.broadcast_send.send_cost_line', {
          tokens: Number(quote.cost_tokens),
          n: Number(quote.n_groups || 0),
        })
      : ''
  const okPin = await requestPinIfNeeded('broadcast')
  if (!okPin) {
    if (shouldAskPinForAction('broadcast')) alert(tt('admin.broadcast_send.pin_required'))
    return
  }
  if (!window.confirm(`${titleByTarget}${costHint} ${tt('admin.broadcast_send.send_progress_note')}`)) return
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
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.bc_send_failed')))
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

/** Пикер над шагом «Куда отправить»: перед открытием подтягиваем список с API (иначе висят старые/урезанные данные). */
async function openBcBroadcastGroupsPickerInFlow() {
  await loadBroadcastEligibleGroups()
  bcGroupsSearch.value = ''
  bcShowGroupsPicker.value = true
}

async function openBcBroadcastChannelsPickerInFlow() {
  await loadBroadcastEligibleChannels()
  bcChannelsSearch.value = ''
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
  (broadcasts.value || []).filter((b) => bcBroadcastIsAutopostRotationDraft(b)),
)
const bcCampaignUxHasDraftPostsSelected = computed(() => {
  const draftSet = new Set(bcDraftBroadcastsForAutopost.value.map((b) => Number(b.id || 0)).filter((x) => x > 0))
  return (bcCampaignUxWizard.value.postIds || []).some((pid) => draftSet.has(Number(pid)))
})

/** Убираем из мастера автокампаний id постов, которых уже нет среди черновиков (после удаления и т.п.). */
function bcCampaignUxPruneStalePostIds() {
  const draftIds = new Set(
    (broadcasts.value || [])
      .filter((b) => String(b?.status || 'draft').toLowerCase() === 'draft')
      .map((b) => Number(b.id || 0))
      .filter((x) => x > 0),
  )
  const cur = [...(bcCampaignUxWizard.value.postIds || [])].map(Number).filter((x) => x > 0)
  const next = cur.filter((id) => draftIds.has(id)).slice(0, 1)
  if (next.length !== cur.length || cur.length > 1) {
    bcCampaignUxWizard.value = { ...bcCampaignUxWizard.value, postIds: next }
  }
}

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
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.bc_title_save_failed')))
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

function addBcHiddenContinuationButton(rowIdx) {
  bcButtonRows.value[rowIdx].push(bcEmptyHiddenContinuationButton())
}

function addBcPrefilledDmButton(rowIdx) {
  bcButtonRows.value[rowIdx].push(bcEmptyPrefilledDmButton())
}

function bcFlattenFilledButtons() {
  const out = []
  for (const row of bcButtonRows.value || []) {
    for (const b of row || []) {
      if (!String(b?.text || '').trim()) continue
      out.push({ ...b })
    }
  }
  return out
}

/** Все кнопки в одну строку под постом (как три «Жми» в ряд). */
function bcApplyKeyboardLayoutInline() {
  const flat = bcFlattenFilledButtons()
  bcButtonRows.value = flat.length ? [flat] : [[bcEmptyButton()]]
  bcSavedTick.value = false
}

/** Каждая кнопка — отдельный ряд (друг под другом на всю ширину). */
function bcApplyKeyboardLayoutStacked() {
  const flat = bcFlattenFilledButtons()
  bcButtonRows.value = flat.length ? flat.map((b) => [b]) : [[bcEmptyButton()]]
  bcSavedTick.value = false
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
    alert(String(e?.body?.detail || e?.message || tt('admin.dlg.save_failed')))
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
  window.addEventListener('guard:header-back', onGuardHeaderBack)
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
    } else if (isOwnerCabinet.value) {
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
        loadPartnerLiteActivity(),
        loadReferralLite(),
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
    if (isOwnerCabinet.value && String(route.query.open || '').toLowerCase() === 'stats_reports') {
      tab.value = 'overview'
      premiumAdmSection.value = 'protection'
      ownerProtectionStatsMode.value = 'protection'
    }
  } catch (e) {
    error.value = String(e?.body?.detail || e?.message || tt('admin.dlg.no_access'))
  } finally {
    loading.value = false
  }
})

watch(
  () => premiumAdmSection.value,
  (s) => {
    if (s === 'protection') void loadPartnerHourlyActivity()
  },
)

watch(
  () => bcShowPreview.value,
  (open) => {
    if (!open) bcRevokePreviewMediaThumbs()
  },
)

watch(
  () => bcAuxModal.value,
  (v) => {
    if (v !== 'keyboard') bcKeyboardInfoOpen.value = false
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
  window.removeEventListener('guard:header-back', onGuardHeaderBack)
  if (bcStatsReloadTimer.value) {
    clearTimeout(bcStatsReloadTimer.value)
    bcStatsReloadTimer.value = null
  }
  document.body.style.overflow = ''
  stopBroadcastProgressPolling()
  bcCampaignUxStopProgressPolling()
  if (bcStatsPollTimer.value) {
    clearInterval(bcStatsPollTimer.value)
    bcStatsPollTimer.value = null
  }
  if (bcSendResultPollTimer.value) {
    clearInterval(bcSendResultPollTimer.value)
    bcSendResultPollTimer.value = null
  }
  if (bcBroadcastsListPollTimer.value) {
    clearInterval(bcBroadcastsListPollTimer.value)
    bcBroadcastsListPollTimer.value = null
  }
  if (bcStatsModalPollTimer.value) {
    clearInterval(bcStatsModalPollTimer.value)
    bcStatsModalPollTimer.value = null
  }
})

watch(
  () => [bcCampaignUxOpen.value, bcCampaignUxScreen.value],
  ([open, s]) => {
    bcCampaignUxStopProgressPolling()
    bcCampaignUxStopAuxCampaignPollers()
    if (!open) {
      bcCampaignUxProgressSnapshot.value = null
      return
    }
    if (s === 'progress') {
      void bcCampaignUxRefreshProgressSnapshot()
      bcCampaignUxProgressPollTimer = setInterval(() => {
        void bcCampaignUxRefreshProgressSnapshot()
      }, 2500)
    } else {
      bcCampaignUxProgressSnapshot.value = null
    }
    if (s === 'stats') {
      void bcCampaignUxRefreshStatsQuiet()
      bcCampaignUxStatsPollTimer = window.setInterval(() => void bcCampaignUxRefreshStatsQuiet(), 4000)
    }
    if (s === 'list' || s === 'manage') {
      bcCampaignUxCampaignSyncPollTimer = window.setInterval(() => {
        void loadAutopostCampaigns({ silent: true })
      }, 7000)
    }
  },
)

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
    if (v === 'referrals' && (isOwnerCabinet.value || showFullAdminShell.value)) {
      await Promise.all([loadReferralLite(), loadMyPartnerStatsLite()])
      return
    }
    if (v === 'ops') {
      await loadOpsHealth()
      return
    }
    if (v === 'bad_urls') {
      if (!showFullAdminShell.value && !isOwnerCabinet.value) {
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
      void bcRecentPulseHydrateQuiet()
    }
  }
)

watch(
  () => [showFullAdminShell.value, tab.value, adminOverviewEmbed.value],
  async ([full, t, emb]) => {
    if (!full || t !== 'overview') return
    const e = String(emb || '')
    if (!e) return
    try {
      if (e === 'users') await loadUsers()
      else if (e === 'chats') await loadChats()
      else if (e === 'revenue') await loadRevenueStats()
      else if (e === 'funnel') await loadReferralsFunnel()
      else if (e === 'commissions') await loadCommissions()
      else if (e === 'referrals') await loadReferralsTop()
    } catch {
      //
    }
  },
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
    if (bcStatsModalPollTimer.value) {
      clearInterval(bcStatsModalPollTimer.value)
      bcStatsModalPollTimer.value = null
    }
    if (!open || !Number(id || 0)) return
    loadBroadcastStats()
    bcStatsModalPollTimer.value = window.setInterval(() => {
      void loadBroadcastStats({ silent: true })
    }, 3000)
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
    bcRecentStatsModalOpen.value ||
    bcSendTargetModalOpen.value ||
    bcSendTimingModalOpen.value ||
    bcSendModalOpen.value ||
    bcConfirmModalOpen.value ||
    showUserInfoModal.value ||
    bcShowBotsPicker.value ||
    bcCampaignUxOpen.value ||
    bcCampaignUxRecipientPickerOpen.value,
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

watch(
  () => bcShowAllRecentModal.value,
  (open) => {
    if (open) void bcRecentPulseHydrateQuiet()
  },
)

watch(
  () => [bcRecentStatsModalOpen.value, bcRecentStatsBroadcastId.value],
  ([open, bid]) => {
    if (bcStatsPollTimer.value) {
      clearInterval(bcStatsPollTimer.value)
      bcStatsPollTimer.value = null
    }
    if (!open || !Number(bid || 0)) return
    bcStatsPollTimer.value = window.setInterval(() => {
      void bcLoadRecentBroadcastStats(Number(bid), { silent: true })
    }, BC_STATS_POLL_MS)
  },
)

watch(
  () => [bcSendModalOpen.value, bcSendModalState.value, bcSendModalBroadcastId.value],
  ([open, st, bid]) => {
    if (bcSendResultPollTimer.value) {
      clearInterval(bcSendResultPollTimer.value)
      bcSendResultPollTimer.value = null
    }
    if (!open || st !== 'done' || !Number(bid || 0)) return
    bcSendResultPollTimer.value = window.setInterval(() => {
      void loadBcSendResultStats(Number(bid), { silent: true })
    }, BC_STATS_POLL_MS)
  },
)

watch(
  () => tab.value,
  (v) => {
    if (bcBroadcastsListPollTimer.value) {
      clearInterval(bcBroadcastsListPollTimer.value)
      bcBroadcastsListPollTimer.value = null
    }
    if (v !== 'broadcasts') return
    bcBroadcastsListPollTimer.value = window.setInterval(() => {
      void loadBroadcasts({ silent: true })
      void bcRecentPulseHydrateQuiet()
    }, 3500)
  },
  { immediate: true },
)

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
      {{ tt('app.init_required') }}
    </div>
    <div
      v-else-if="loading"
      class="relative overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-br from-slate-900/88 via-slate-950/90 to-black/95 p-6 text-center text-slate-100 shadow-[0_16px_50px_-16px_rgba(0,0,0,0.85)] backdrop-blur-xl ring-1 ring-white/10"
      aria-busy="true"
    >
      <div class="mx-auto mb-3 inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/8 px-3 py-1.5 text-xs font-semibold text-slate-100 shadow-[0_0_20px_-10px_rgba(255,255,255,0.35)]">
        <span class="inline-block bc-hourglass">⏳</span>
        {{ tt('admin.shell.loading_cabinet') }}
      </div>
      <div class="space-y-2.5">
        <div class="mx-auto h-3 w-2/3 max-w-[14rem] animate-pulse rounded bg-white/15" />
        <div class="h-20 animate-pulse rounded-xl bg-white/10" />
        <div class="h-20 animate-pulse rounded-xl bg-white/10" />
      </div>
    </div>
    <div v-else-if="error" class="rounded-xl border border-rose-300 bg-rose-50 p-4 text-rose-700 dark:border-rose-700 dark:bg-rose-900/20 dark:text-rose-300">
      {{ error }}
    </div>
    <template v-else>
    <CabinetPremiumTitleBar
      v-if="showCabinetCrownNav"
      :profile="meAdminProfile"
      @go-subscription="goOwnerSubscriptionPage"
    />
    <h1
      v-if="!(isOwnerCabinet && !premiumAdmSection && tab === 'overview') && !(isOwnerCabinet && showCabinetCrownNav)"
      class="text-xl font-semibold text-gray-100 md:text-2xl"
    >
      {{
        isDelegatedFreeBroadcastCabinet
          ? tt('admin.shell.title_broadcast_delegated')
          : isOwnerCabinet && !meAdminProfile?.is_premium
            ? tt('admin.shell.title_free_cabinet')
            : isPremiumCabinet || (showFullAdminShell && meAdminProfile?.is_premium)
              ? tt('admin.shell.title_premium_cabinet')
              : showFullAdminShell
                ? tt('admin.shell.title_service_admin')
                : tt('admin.title')
      }}
    </h1>
    <p
      v-if="isDelegatedFreeBroadcastCabinet"
      class="text-[12px] leading-snug text-violet-200/90"
    >
      {{ tt('admin.shell.delegated_subtitle') }}
    </p>
    <div v-if="showFullAdminShell" class="space-y-2">
      <div class="grid grid-cols-3 gap-2">
        <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'overview' && !adminOverviewEmbed ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'overview'; adminOverviewEmbed = ''">{{ tt('admin.tabs.stats') }}</button>
        <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'broadcasts' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'broadcasts'">{{ tt('admin.tabs.broadcasts') }}</button>
        <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'referrals' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'referrals'">{{ tt('admin.shell.tab_referrals') }}</button>
        <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'bad_urls' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'bad_urls'">{{ tt('admin.shell.tab_antiurl') }}</button>
        <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'subscription' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'subscription'">{{ tt('admin.tabs.subscription') }}</button>
      </div>
      <div class="grid grid-cols-3 gap-2 border-t border-white/10 pt-2">
        <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'payouts' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'payouts'">{{ tt('common.locale_code') === 'en' ? 'Payouts' : 'Выплаты' }}</button>
        <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'ops' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'ops'">Guard Pulse</button>
        <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'insights' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'insights'">{{ tt('common.locale_code') === 'en' ? 'Insights' : 'Сводка' }}</button>
        <button type="button" class="rounded-lg px-2 py-1.5 text-xs font-semibold" :class="tab === 'messages' ? 'bg-primary-100 text-primary-800 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'" @click="tab = 'messages'">{{ tt('common.locale_code') === 'en' ? 'Messages' : 'Сообщения' }}</button>
      </div>
    </div>

    <div
      v-if="tab === 'overview' && (showPersonalPartnerOverview || (showFullAdminShell && data))"
      class="grid grid-cols-2 gap-2"
    >
      <template v-if="isOwnerCabinet && !showFullAdminShell">
        <template v-if="!premiumAdmSection">
          <div class="col-span-2">
            <OwnerCabinetHome
              :summary="plActivitySummary"
              :profile="meAdminProfile"
              :referral-paid-count="referralInfo?.paid_count != null ? referralInfo.paid_count : null"
              :broadcast-spend-tokens="meAdminProfile?.broadcast_spend_tokens != null ? meAdminProfile.broadcast_spend_tokens : null"
              @open-section="openPremiumAdmCard"
              @open-main="goOwnerSubscriptionPage"
            />
          </div>
        </template>
        <template v-else-if="premiumAdmSection === 'protection'">
          <div class="col-span-2 min-h-0 space-y-2">
            <div
              v-if="ownerProtectionStatsMode === 'protection'"
              class="flex items-center justify-between gap-2 rounded-2xl bg-gradient-to-r from-cyan-950/70 via-sky-950/60 to-indigo-950/70 px-3 py-2.5 ring-1 ring-cyan-300/20"
            >
              <button
                type="button"
                class="rounded-xl border border-cyan-400/35 bg-cyan-500/10 px-3 py-1.5 text-[11px] font-semibold text-cyan-100 shadow-[0_10px_24px_-16px_rgba(34,211,238,0.75)] transition hover:bg-cyan-500/20"
                @click="ownerProtectionReportOpen = !ownerProtectionReportOpen"
              >
                {{ ownerProtectionReportOpen ? tt('admin.owner_report.detailed_hide') : tt('admin.owner_report.detailed_show') }}
              </button>
              <p class="text-[11px] text-cyan-100/75">{{ tt('admin.owner_report.unban_unmute_hint') }}</p>
            </div>
            <OwnerCabinetProtectionStats
              :summary="plActivitySummary || {}"
              :hourly-data="partnerHourlyData"
              :audience-gender="partnerAudienceGender"
              :loading="partnerHourlyLoading"
              :period-key="ownerStatsPeriodKey"
              :mode="ownerProtectionStatsMode"
              @period-change="onOwnerStatsPeriodChange"
              @open-groups="openPartnerGroupsModal"
              @report-context-change="onOwnerProtectionReportContextChange"
            />
            <div
              v-if="ownerProtectionReportOpen && ownerProtectionStatsMode === 'protection'"
              class="rounded-[24px] bg-gradient-to-br from-[#050b1f]/96 via-[#09132d]/95 to-[#02050e]/98 p-3 shadow-[0_35px_90px_-36px_rgba(6,182,212,0.7)] ring-1 ring-cyan-300/20 backdrop-blur-2xl"
            >
              <div class="mb-2 flex items-center justify-between">
                <p class="text-base font-semibold text-white drop-shadow-[0_0_16px_rgba(34,211,238,0.35)]">{{ tt('admin.owner_report.modal_title') }}</p>
                <button
                  type="button"
                  class="inline-flex h-8 w-8 items-center justify-center rounded-full bg-white/10 text-cyan-100 transition hover:bg-white/15"
                  @click="closeOwnerProtectionReport"
                >
                  ✕
                </button>
              </div>
              <p class="mb-2 text-[11px] text-cyan-100/85">
                {{ tt('admin.owner_report.deleted_prefix', { period: ownerProtectionReportPeriodLabel, count: ownerProtectionReportDeletedCount }) }}
                {{ ownerProtectionReportHint }}
              </p>
              <div class="max-h-[52vh] space-y-1 overflow-y-auto pr-1">
                <div
                  v-for="(ev, ei) in ownerProtectionReportEvents"
                  :key="`owner-protection-report-${ei}-${ev.created_at}-${ev.user_id}`"
                  class="rounded-xl px-2.5 py-2 text-[11px] ring-1 backdrop-blur-md"
                  :class="partnerNormalizeAction(ev.action) === 'observe'
                    ? 'bg-gradient-to-br from-red-950/60 via-rose-950/55 to-red-900/50 text-red-100 ring-red-300/35'
                    : 'bg-gradient-to-br from-slate-900/75 via-slate-900/65 to-slate-800/60 text-slate-100 ring-cyan-300/20'"
                >
                  <div class="flex flex-wrap items-center gap-1 text-[10px] text-slate-300/80">
                    <span>{{ ownerProtectionReportTimeLabel(ev.created_at) }}</span>
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
                    · {{ partnerActionLabel(ev.action) }}
                    <span v-if="partnerNormalizeAction(ev.action) === 'delete' || partnerNormalizeAction(ev.action) === 'observe'"> · {{ partnerReasonLabel(ev.reason) }}</span>
                  </p>
                  <div class="mt-1.5 flex flex-wrap gap-1.5">
                    <button
                      v-if="partnerNormalizeAction(ev.action) === 'mute' && !partnerJournalActionHidden(ev, 'mute')"
                      type="button"
                      class="rounded-md bg-emerald-500/80 px-2 py-1 text-[10px] font-semibold text-white shadow-[0_10px_20px_-10px_rgba(16,185,129,0.85)]"
                      @click="partnerQuickUnmute(ev)"
                    >
                      {{ tt('admin.owner_report.unmute') }}
                    </button>
                    <button
                      v-if="partnerNormalizeAction(ev.action) === 'ban' && !partnerJournalActionHidden(ev, 'ban')"
                      type="button"
                      class="rounded-md bg-indigo-500/85 px-2 py-1 text-[10px] font-semibold text-white shadow-[0_10px_20px_-10px_rgba(99,102,241,0.85)]"
                      @click="partnerQuickUnban(ev)"
                    >
                      {{ tt('admin.owner_report.unban') }}
                    </button>
                    <button
                      v-if="partnerNormalizeAction(ev.action) === 'observe'"
                      type="button"
                      class="rounded-md bg-amber-500/85 px-2 py-1 text-[10px] font-semibold text-slate-950 shadow-[0_10px_20px_-10px_rgba(251,191,36,0.85)]"
                      @click="partnerQuickObserve(ev)"
                    >
                      {{ tt('admin.owner_report.observed') }}
                    </button>
                  </div>
                </div>
                <p v-if="!(ownerProtectionReportEvents || []).length" class="py-6 text-center text-[11px] text-slate-400">{{ tt('admin.owner_report.no_events_yet') }}</p>
              </div>
            </div>
          </div>
        </template>
        <template v-else-if="premiumAdmSection === 'updates'">
          <div class="col-span-2 overflow-hidden rounded-2xl bg-gradient-to-br from-[#0c1326]/96 via-[#111a35]/94 to-[#050812]/98 p-4 shadow-[0_20px_52px_-22px_rgba(56,189,248,0.38)] ring-1 ring-cyan-300/15">
            <p class="text-[13px] font-semibold uppercase tracking-[0.08em] text-cyan-200/85">Лента обновлений</p>
            <p class="mt-2 text-[14px] leading-snug text-slate-100/85">
              Все релизы, улучшения и дорожная карта доступны на главной странице в блоке
              «Смотреть все обновления».
            </p>
            <button
              type="button"
              class="mt-4 w-full rounded-xl bg-gradient-to-r from-cyan-600 via-sky-500 to-indigo-500 py-2.5 text-sm font-semibold text-white shadow-[0_12px_28px_-12px_rgba(56,189,248,0.8)] transition hover:brightness-110 active:scale-[0.99]"
              @click="router.push({ path: '/', query: { section: 'account', updates: '1' } })"
            >
              Открыть ленту обновлений
            </button>
          </div>
        </template>
      </template>
      <template v-if="showFullAdminShell && data">
        <div class="col-span-2 rounded-xl border border-cyan-500/35 bg-slate-950/90 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-cyan-200/90">База и финансы (сервис)</p>
          <p class="mt-0.5 text-[11px] text-slate-400">В базе <b class="text-slate-200">{{ data.users_total }}</b> пользователей · откройте раздел под карточками.</p>
          <div class="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
            <button type="button" class="rounded-lg border border-cyan-500/40 bg-cyan-950/50 px-2 py-2 text-left text-[11px] font-semibold text-cyan-100 shadow-[0_0_16px_-8px_rgba(34,211,238,0.5)] transition hover:bg-cyan-950/80" @click="goAdminEmbed('users')">
              Пользователи <span class="block text-lg font-bold text-white">{{ data.users_total }}</span>
            </button>
            <button type="button" class="rounded-lg border border-cyan-500/40 bg-cyan-950/50 px-2 py-2 text-left text-[11px] font-semibold text-cyan-100 shadow-[0_0_16px_-8px_rgba(34,211,238,0.5)] transition hover:bg-cyan-950/80" @click="goAdminEmbed('chats')">
              Чаты <span class="block text-lg font-bold text-white">{{ data.chats_total }}</span>
            </button>
            <button type="button" class="rounded-lg border border-emerald-500/35 bg-emerald-950/40 px-2 py-2 text-left text-[11px] font-semibold text-emerald-100" @click="goAdminEmbed('revenue')">
              Выручка ₽ <span class="block text-lg font-bold text-white">{{ data.revenue_total_rub }}</span>
            </button>
            <button type="button" class="rounded-lg border border-violet-500/35 bg-violet-950/40 px-2 py-2 text-left text-[11px] font-semibold text-violet-100" @click="goAdminEmbed('funnel')">
              Платящих реф. <span class="block text-lg font-bold text-white">{{ data.referral_paid_users }}</span>
            </button>
            <button type="button" class="rounded-lg border border-lime-500/35 bg-lime-950/35 px-2 py-2 text-left text-[11px] font-semibold text-lime-100" @click="goAdminEmbed('commissions')">
              Резерв комиссий <span class="block text-lg font-bold text-white">{{ commissionsSummary.reserve_for_next_payout_rub ?? 0 }} ₽</span>
            </button>
            <div class="rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-[11px] text-slate-300">
              Оплат успешно: <b class="text-white">{{ data.payments_succeeded }}</b>
            </div>
          </div>
        </div>
      </template>
    </div>
    <div v-if="tab === 'overview' && showFullAdminShell && adminOverviewEmbed === 'users'" class="space-y-2">
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
        <p class="mt-1 text-[9px] text-slate-500">
          Согласия: пакет документов — <b>{{ u.legal_bundle_accepted_at ? 'да' : 'нет' }}</b> · ПД —
          <b>{{ u.legal_pd_accepted_at ? 'да' : 'нет' }}</b> · маркетинг — <b>{{ u.legal_marketing_opt_in ? 'да' : 'нет' }}</b>
        </p>
        <div class="mt-2">
          <div class="flex flex-wrap gap-2">
            <button type="button" class="rounded-lg border border-cyan-300/35 bg-cyan-500/15 px-3 py-1.5 text-xs font-semibold text-cyan-100 hover:bg-cyan-500/25" @click="openAdminUserInfo(u)">Инфо</button>
            <a :href="profileLinkForUser(u) || '#'" target="_blank" rel="noopener noreferrer" class="rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-semibold text-white" :class="!profileLinkForUser(u) ? 'pointer-events-none opacity-60' : ''" @click="openExternalFromAnchor($event, profileLinkForUser(u))">Профиль</a>
            <button type="button" class="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white" @click="chatsOwnerFilter = Number(u.telegram_id || 0); goAdminEmbed('chats')">Чаты</button>
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
      v-if="showFullAdminShell && tab === 'overview' && showUserInfoModal && selectedAdminUser"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-center justify-center bg-black/70 p-3"
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
        <div class="mt-2 space-y-1 text-[11px] text-slate-300">
          <p>Способ оплаты/активации: <b>{{ adminUserPaymentLabel(selectedAdminUser) }}</b></p>
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
          <p class="mt-2 border-t border-white/10 pt-2">
            <span class="font-semibold text-slate-200">Согласия (юр.):</span>
            пакет документов —
            <b class="text-emerald-300">{{ selectedAdminUser.legal_bundle_accepted_at ? 'да' : 'нет' }}</b>
            <span v-if="selectedAdminUser.legal_bundle_accepted_at" class="text-slate-500">
              ({{ fmtUserSeenAt(selectedAdminUser.legal_bundle_accepted_at) }})</span>
            · обработка ПД —
            <b class="text-emerald-300">{{ selectedAdminUser.legal_pd_accepted_at ? 'да' : 'нет' }}</b>
            <span v-if="selectedAdminUser.legal_pd_accepted_at" class="text-slate-500">
              ({{ fmtUserSeenAt(selectedAdminUser.legal_pd_accepted_at) }})</span>
            · маркетинг —
            <b class="text-sky-300">{{ selectedAdminUser.legal_marketing_opt_in ? 'да' : 'нет' }}</b>
          </p>
        </div>
      </div>
    </div>
    <div v-if="tab === 'overview' && showFullAdminShell && adminOverviewEmbed === 'referrals'" class="space-y-2">
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
      <div v-for="(item, idx) in referralsTop" :key="`rt-adm-${idx}-${item.telegram_id}`" class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <p class="text-sm font-semibold text-slate-900 dark:text-white">
          {{ item.first_name || 'Пользователь' }}
          <span v-if="item.username" class="ml-1 text-xs font-medium text-cyan-600 dark:text-cyan-300">@{{ item.username }}</span>
        </p>
        <p class="text-xs text-slate-600 dark:text-slate-300">
          Оплат: {{ item.payments_count || 0 }} · Продаж: {{ item.sales_rub || 0 }} ₽ · Начисление: {{ item.partner_reward_rub || 0 }} ₽
        </p>
      </div>
    </div>
    <div v-if="tab === 'overview' && showFullAdminShell && adminOverviewEmbed === 'funnel'" class="space-y-2">
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
    <div v-if="tab === 'overview' && showFullAdminShell && adminOverviewEmbed === 'revenue'" class="space-y-2">
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
    <div v-if="tab === 'overview' && showFullAdminShell && adminOverviewEmbed === 'commissions'" class="space-y-2">
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
    <div v-if="tab === 'overview' && showFullAdminShell && adminOverviewEmbed === 'chats'" class="space-y-2">
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
    <div v-else-if="tab === 'referrals' && (isOwnerCabinet || showFullAdminShell)" class="space-y-2">
      <div v-if="isOwnerCabinet || showFullAdminShell" class="grid grid-cols-2 gap-2 sm:grid-cols-3">
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
    <div v-else-if="showFullAdminShell && tab === 'ops'" class="space-y-3">
      <p class="text-center text-[10px] font-medium uppercase tracking-wide text-cyan-600/90 dark:text-cyan-300/90">
        {{ guardPulseUiMarker }}
      </p>
      <div class="flex gap-2 rounded-xl border border-slate-200 bg-slate-50 p-1.5 dark:border-slate-600 dark:bg-slate-800/60">
        <div class="flex min-w-0 flex-1 flex-wrap gap-2">
          <button
            type="button"
            class="rounded-lg px-3 py-1.5 text-xs font-semibold transition"
            :class="opsInnerTab === 'pulse' ? 'bg-cyan-600 text-white shadow' : 'text-slate-600 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700'"
            @click="opsInnerTab = 'pulse'"
          >
            {{ tt('admin.pulse.tab_monitoring') }}
          </button>
          <button
            type="button"
            class="rounded-lg px-3 py-1.5 text-xs font-semibold transition"
            :class="opsInnerTab === 'journal' ? 'bg-cyan-600 text-white shadow' : 'text-slate-600 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700'"
            @click="opsInnerTab = 'journal'"
          >
            {{ tt('admin.pulse.tab_failure_log') }}
          </button>
        </div>
        <button
          type="button"
          class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-300 bg-white text-sm font-bold text-slate-600 shadow-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
          :title="tt('admin.pulse.info_btn_title')"
          :aria-label="tt('admin.pulse.info_btn_aria')"
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
        <p class="font-semibold text-slate-800 dark:text-slate-100">
          {{ tt('admin.pulse.user_pulse_title', { hours: (incidentSummary && incidentSummary.window_hours) || 24 }) }}
        </p>
        <p v-if="opsHealth.load_failed" class="mt-1 text-slate-800 dark:text-slate-100">
          {{ tt('admin.pulse.summary_link_unstable') }}
        </p>
        <template v-else-if="incidentSummary">
          <p class="mt-1 text-slate-800 dark:text-slate-100">
            {{ tt('admin.pulse.level_prefix') }}
            <b>{{
              incidentSummary.level === 'ok'
                ? tt('admin.pulse.level_ok')
                : incidentSummary.level === 'warn'
                  ? tt('admin.pulse.level_warn')
                  : tt('admin.pulse.level_critical')
            }}</b>
            · {{ tt('admin.pulse.distinct_users') }} <b>{{ incidentSummary.distinct_users_affected }}</b>
            · {{ tt('admin.pulse.incident_records') }} <b>{{ incidentSummary.total_incidents }}</b>
          </p>
          <p v-if="incidentSummary.by_category && Object.keys(incidentSummary.by_category).length" class="mt-1 text-[11px] text-slate-600 dark:text-slate-300">
            {{ tt('admin.pulse.by_category') }}
            <span v-for="(count, catKey) in incidentSummary.by_category" :key="`cat-${catKey}`" class="mr-2 inline-block">
              {{ incidentCategoryLabel(catKey) }}: {{ count }}
            </span>
          </p>
          <ul v-if="(incidentSummary.lines_ru || []).length" class="mt-2 list-disc space-y-0.5 pl-4 text-slate-700 dark:text-slate-200">
            <li v-for="(ln, li) in incidentSummary.lines_ru" :key="`isl-${li}`">{{ ln }}</li>
          </ul>
        </template>
        <p v-if="incidentSummaryLoading" class="mt-1 text-slate-500">{{ tt('admin.pulse.updating_summary') }}</p>
      </div>

      <div v-show="opsInnerTab === 'pulse'" class="space-y-3">
      <div class="rounded-xl border border-cyan-400/40 bg-cyan-500/10 p-3">
        <p class="text-xs font-semibold text-cyan-700 dark:text-cyan-300">{{ tt('admin.pulse.server_state') }}</p>
        <template v-if="opsHealth.load_failed">
          <p class="mt-1 text-sm text-slate-700 dark:text-slate-300">
            <b class="text-amber-800 dark:text-amber-200">{{ tt('admin.pulse.summary_not_loaded') }}</b>{{ tt('admin.pulse.summary_not_loaded_hint') }}
          </p>
        </template>
        <template v-else>
          <p class="mt-1 text-sm text-slate-700 dark:text-slate-300">
            <b>{{ opsHealth.status === 'ok' ? tt('admin.pulse.status_ok_short') : tt('admin.pulse.status_check') }}</b
            >{{
              tt('admin.pulse.server_metrics', {
                db: formatDbPingMs(opsHealth.db_latency_ms),
                uptime: formatServerUptime(opsHealth.api_uptime_sec || 0),
              })
            }}
          </p>
        </template>
      </div>
      <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <p class="text-xs font-semibold text-slate-600 dark:text-slate-300">{{ tt('admin.pulse.railway_title') }}</p>
        <p class="mt-1 text-[11px] leading-snug text-slate-500 dark:text-slate-400">
          {{ tt('admin.pulse.railway_hint') }}
        </p>
        <div class="mt-2 flex flex-col gap-2">
          <button type="button" class="rounded-lg bg-amber-600 px-3 py-2.5 text-left text-xs font-semibold text-white disabled:opacity-60" :disabled="opsActionLoading === 'restart_api'" @click="runOpsAction('restart_api')">
            <span class="font-extrabold tabular-nums text-amber-100">1.</span> {{ tt('admin.pulse.restart_api') }}
          </button>
          <button type="button" class="rounded-lg bg-indigo-600 px-3 py-2.5 text-left text-xs font-semibold text-white disabled:opacity-60" :disabled="opsActionLoading === 'restart_webapp'" @click="runOpsAction('restart_webapp')">
            <span class="font-extrabold tabular-nums text-indigo-100">2.</span> {{ tt('admin.pulse.restart_webapp') }}
          </button>
          <button type="button" class="rounded-lg bg-rose-600 px-3 py-2.5 text-left text-xs font-semibold text-white disabled:opacity-60" :disabled="opsActionLoading === 'restart_bot'" @click="runOpsAction('restart_bot')">
            <span class="font-extrabold tabular-nums text-rose-100">3.</span> {{ tt('admin.pulse.restart_bot') }}
          </button>
        </div>
      </div>
      <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <p class="text-xs font-semibold text-slate-600 dark:text-slate-300">{{ tt('admin.pulse.payments_by_hour') }}</p>
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
        {{ tt('admin.pulse.refresh_monitoring') }}
      </button>
      </div>

      <div v-show="opsInnerTab === 'journal'" class="space-y-3">
        <p class="text-center text-[11px] text-slate-500 dark:text-slate-400">{{ tt('admin.pulse.journal_intro') }}</p>
        <div class="flex flex-col gap-2 sm:flex-row">
          <input
            v-model="incidentSearchQuery"
            type="search"
            :placeholder="tt('admin.pulse.journal_search_ph')"
            class="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 placeholder:text-slate-400 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
            @keydown.enter.prevent="loadIncidentFeed()"
          />
          <button
            type="button"
            class="rounded-lg bg-slate-700 px-3 py-2 text-xs font-semibold text-white dark:bg-slate-600"
            :disabled="incidentFeedLoading"
            @click="loadIncidentFeed()"
          >
            {{ tt('admin.pulse.find') }}
          </button>
        </div>
        <button
          type="button"
          class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-800 disabled:opacity-60 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          :disabled="incidentFeedLoading"
          @click="loadIncidentFeed()"
        >
          {{ tt('admin.pulse.refresh_journal') }}
        </button>
        <div
          v-if="!incidentFeed.length && !incidentFeedLoading"
          class="rounded-xl border border-slate-200 bg-white p-4 text-center text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-800"
        >
          {{ tt('admin.pulse.journal_empty') }}
        </div>
        <div
          v-else-if="incidentFeedLoading"
          class="rounded-xl border border-slate-200 bg-white p-4 text-center text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-800"
        >
          {{ tt('admin.pulse.journal_loading') }}
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
                {{
                  row.severity === 'critical'
                    ? tt('admin.pulse.severity_critical')
                    : row.severity === 'warn'
                      ? tt('admin.pulse.severity_warn')
                      : tt('admin.pulse.severity_ok')
                }}
              </span>
              <span class="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-700 dark:bg-slate-900 dark:text-slate-200">{{
                incidentCategoryLabel(row.category)
              }}</span>
              <span v-if="row.affected_count > 0" class="text-[10px] font-semibold text-slate-600 dark:text-slate-300">
                {{ tt('admin.pulse.accounts_affected') }} {{ row.affected_count }}
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

      <GuardTeleport>
        <div
          v-if="guardPulseInfoOpen"
          style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center bg-black/50 p-3 sm:items-center"
          @click.self="guardPulseInfoOpen = false"
        >
          <div
            class="max-h-[min(85vh,560px)] w-full max-w-md overflow-y-auto rounded-2xl border border-slate-200 bg-white p-4 text-xs leading-relaxed text-slate-700 shadow-xl dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
            @click.stop
          >
            <div class="mb-3 flex items-center justify-between gap-2">
              <p class="text-sm font-bold text-slate-900 dark:text-slate-100">{{ tt('admin.pulse.info_modal_title') }}</p>
              <button
                type="button"
                class="rounded-lg bg-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-800 dark:bg-slate-700 dark:text-slate-100"
                @click="guardPulseInfoOpen = false"
              >
                {{ tt('admin.pulse.info_close') }}
              </button>
            </div>

            <section class="space-y-2 border-b border-slate-200 pb-3 dark:border-slate-600">
              <p class="font-semibold text-slate-800 dark:text-slate-100">{{ tt('admin.pulse.info_monitor_heading') }}</p>
              <p>
                {{ tt('admin.pulse.info_monitor_p1') }}
              </p>
              <p>
                {{ tt('admin.pulse.info_monitor_p2') }}
              </p>
              <ul v-if="(opsHealth.diagnostics || []).length" class="list-disc space-y-1 pl-4 text-slate-600 dark:text-slate-300">
                <li v-for="(d, i) in opsHealth.diagnostics" :key="`gp-info-d-${i}`">{{ d }}</li>
              </ul>
            </section>

            <section v-if="opsHealth.railway_redeploy" class="space-y-2 border-b border-slate-200 py-3 dark:border-slate-600">
              <p class="font-semibold text-slate-800 dark:text-slate-100">{{ tt('admin.pulse.info_railway_heading') }}</p>
              <p>
                {{ tt('admin.pulse.info_railway_p1') }}
              </p>
              <p>{{ tt('admin.pulse.info_railway_p2') }}</p>
              <ul class="space-y-0.5 font-mono text-[11px] text-slate-600 dark:text-slate-300">
                <li>
                  {{ tt('admin.pulse.railway_token_label') }}
                  {{ opsHealth.railway_redeploy.token_configured ? tt('admin.pulse.token_ok') : tt('admin.pulse.token_missing') }}
                </li>
                <li>{{ tt('admin.pulse.env_label') }} {{ opsHealth.railway_redeploy.environment_configured ? tt('admin.pulse.yes') : tt('admin.pulse.no') }}</li>
                <li>
                  {{ tt('admin.pulse.service_ids_label') }} {{ opsHealth.railway_redeploy.service_ids?.bot ? tt('admin.pulse.yes') : tt('admin.pulse.no') }}, API:
                  {{ opsHealth.railway_redeploy.service_ids?.api ? tt('admin.pulse.yes') : tt('admin.pulse.no') }}, WebApp:
                  {{ opsHealth.railway_redeploy.service_ids?.webapp ? tt('admin.pulse.yes') : tt('admin.pulse.no') }}
                </li>
              </ul>
            </section>

            <section class="space-y-2 pt-3">
              <p class="font-semibold text-slate-800 dark:text-slate-100">{{ tt('admin.pulse.info_journal_heading') }}</p>
              <p>
                {{ tt('admin.pulse.info_journal_p1') }}
              </p>
              <p>{{ tt('admin.pulse.info_journal_p2') }}</p>
              <p>
                {{ tt('admin.pulse.info_journal_p3') }}
              </p>
              <p class="text-slate-500 dark:text-slate-400">{{ tt('admin.pulse.info_journal_footer') }}</p>
            </section>
          </div>
        </div>
      </GuardTeleport>
    </div>

    <div v-else-if="(showFullAdminShell || isOwnerCabinet) && tab === 'bad_urls'" class="space-y-3">
      <!-- Premium: только личная база URL -->
      <template v-if="isOwnerCabinet && !showFullAdminShell">
        <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
          <div class="flex items-center justify-between gap-2">
            <p class="text-sm font-semibold text-slate-900 dark:text-slate-100">{{ tt('admin.bad_urls.title_my') }}</p>
            <button
              type="button"
              class="inline-flex h-8 min-w-8 items-center justify-center rounded-full border border-sky-300 bg-sky-100 px-2 text-sm font-extrabold text-sky-800 shadow-sm hover:bg-sky-200 dark:border-sky-700 dark:bg-sky-900/30 dark:text-sky-200 dark:hover:bg-sky-900/45"
              :aria-label="tt('admin.bad_urls.aria_help')"
              @click="showMyGlobalBadUrlInfo = !showMyGlobalBadUrlInfo"
            >
              i
            </button>
          </div>
          <div
            v-if="showMyGlobalBadUrlInfo"
            class="mt-2 rounded-xl border border-cyan-300/40 bg-cyan-50 p-3 text-xs leading-relaxed text-slate-700 dark:border-cyan-700/50 dark:bg-cyan-950/25 dark:text-slate-200"
          >
            <p>{{ tt('admin.bad_urls.info_my_p1') }}</p>
            <p class="mt-1">{{ tt('admin.bad_urls.info_my_p2') }}</p>
          </div>
          <div class="mt-2 flex flex-col gap-2 sm:flex-row">
            <input
              v-model="newMyGlobalBadUrl"
              type="text"
              :placeholder="tt('admin.bad_urls.placeholder_pattern')"
              class="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
              :disabled="globalBadUrlLoading"
              @keydown.enter.prevent="addMyGlobalBadUrl()"
            >
            <input
              v-model="newMyGlobalBadUrlNote"
              type="text"
              :placeholder="tt('admin.bad_urls.placeholder_note')"
              class="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
              :disabled="globalBadUrlLoading"
            >
            <button
              type="button"
              class="shrink-0 rounded-lg bg-rose-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
              :disabled="globalBadUrlLoading || !(newMyGlobalBadUrl || '').trim()"
              @click="addMyGlobalBadUrl()"
            >
              {{ tt('admin.bad_urls.add') }}
            </button>
          </div>
        </div>
        <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
          <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">{{ tt('admin.bad_urls.list_heading', { count: globalBadUrlItems.length }) }}</p>
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
                {{ tt('admin.bad_urls.remove') }}
              </button>
            </li>
          </ul>
          <p v-else class="mt-2 text-xs text-slate-500">{{ tt('admin.bad_urls.empty_owner_hint') }}</p>
          <button
            type="button"
            class="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-700 dark:border-slate-600 dark:text-slate-200"
            :disabled="globalBadUrlLoading"
            @click="loadGlobalBadUrls()"
          >
            {{ tt('admin.bad_urls.refresh_list') }}
          </button>
        </div>
      </template>

      <!-- Полный админ: общая база + моя личная + чужие личные -->
      <template v-else-if="showFullAdminShell">
        <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
          <div class="flex items-center justify-between gap-2">
            <p class="text-sm font-semibold text-slate-900 dark:text-slate-100">{{ tt('admin.bad_urls.title_guard_shared') }}</p>
            <button
              type="button"
              class="inline-flex h-8 min-w-8 items-center justify-center rounded-full border border-sky-300 bg-sky-100 px-2 text-sm font-extrabold text-sky-800 shadow-sm hover:bg-sky-200 dark:border-sky-700 dark:bg-sky-900/30 dark:text-sky-200 dark:hover:bg-sky-900/45"
              :aria-label="tt('admin.bad_urls.aria_help')"
              @click="showGlobalBadUrlInfo = !showGlobalBadUrlInfo"
            >
              i
            </button>
          </div>
          <div
            v-if="showGlobalBadUrlInfo"
            class="mt-2 rounded-xl border border-cyan-300/40 bg-cyan-50 p-3 text-xs leading-relaxed text-slate-700 dark:border-cyan-700/50 dark:bg-cyan-950/25 dark:text-slate-200"
          >
            <p>{{ tt('admin.bad_urls.info_guard_p1') }}</p>
            <p class="mt-1">{{ tt('admin.bad_urls.info_guard_p2') }}</p>
          </div>
          <div class="mt-2 flex flex-col gap-2 sm:flex-row">
            <input
              v-model="newGlobalBadUrl"
              type="text"
              :placeholder="tt('admin.bad_urls.placeholder_pattern')"
              class="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
              :disabled="globalBadUrlLoading"
              @keydown.enter.prevent="addGlobalBadUrl()"
            >
            <input
              v-model="newGlobalBadUrlNote"
              type="text"
              :placeholder="tt('admin.bad_urls.placeholder_note')"
              class="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
              :disabled="globalBadUrlLoading"
            >
            <button
              type="button"
              class="shrink-0 rounded-lg bg-rose-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
              :disabled="globalBadUrlLoading || !(newGlobalBadUrl || '').trim()"
              @click="addGlobalBadUrl()"
            >
              {{ tt('admin.bad_urls.add') }}
            </button>
          </div>
        </div>
        <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
          <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">{{ tt('admin.bad_urls.system_list_heading', { count: globalBadUrlSystemItems.length }) }}</p>
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
                {{ tt('admin.bad_urls.remove') }}
              </button>
            </li>
          </ul>
          <p v-else class="mt-2 text-xs text-slate-500">{{ tt('admin.bad_urls.empty_short') }}</p>
        </div>

        <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
          <p class="text-sm font-semibold text-slate-900 dark:text-slate-100">{{ tt('admin.bad_urls.title_my_personal') }}</p>
          <p class="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">{{ tt('admin.bad_urls.my_personal_hint') }}</p>
          <div class="mt-2 flex flex-col gap-2 sm:flex-row">
            <input
              v-model="newMyGlobalBadUrl"
              type="text"
              :placeholder="tt('admin.bad_urls.placeholder_pattern')"
              class="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
              :disabled="globalBadUrlLoading"
              @keydown.enter.prevent="addMyGlobalBadUrl()"
            >
            <input
              v-model="newMyGlobalBadUrlNote"
              type="text"
              :placeholder="tt('admin.bad_urls.placeholder_note')"
              class="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
              :disabled="globalBadUrlLoading"
            >
            <button
              type="button"
              class="shrink-0 rounded-lg bg-rose-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
              :disabled="globalBadUrlLoading || !(newMyGlobalBadUrl || '').trim()"
              @click="addMyGlobalBadUrl()"
            >
              {{ tt('admin.bad_urls.add') }}
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
                {{ tt('admin.bad_urls.remove') }}
              </button>
            </li>
          </ul>
          <p v-else class="mt-2 text-xs text-slate-500">{{ tt('admin.bad_urls.empty_short') }}</p>
        </div>

        <div v-if="globalBadUrlUserBases.length" class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
          <p class="text-sm font-semibold text-slate-900 dark:text-slate-100">{{ tt('admin.bad_urls.title_other_users') }}</p>
          <div class="mt-2 max-h-64 space-y-3 overflow-y-auto pr-1">
            <div
              v-for="ub in globalBadUrlUserBases"
              :key="`ubase-${ub.owner_telegram_id}`"
              class="rounded-lg border border-slate-200 p-2 dark:border-slate-600"
            >
              <button
                type="button"
                class="w-full rounded-lg px-1 py-1.5 text-left transition hover:bg-slate-100 dark:hover:bg-slate-700/60"
                :title="tt('admin.bad_urls.open_user_card_title')"
                @click="goToAdminUserInList(ub.owner_telegram_id)"
              >
                <span class="text-xs font-semibold text-slate-900 dark:text-slate-100">
                  {{ ub.owner_first_name || tt('admin.bad_urls.user_fallback') }}
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
          {{ tt('admin.bad_urls.refresh_all') }}
        </button>
      </template>
    </div>

    <div v-else-if="(showFullAdminShell || isOwnerCabinet) && tab === 'subscription'" class="space-y-3">
      <SubscriptionManagementPanel
        v-if="meAdminProfile"
        :profile="meAdminProfile"
        variant="embedded"
        @update:profile="applyAdminMeSubscription"
      />
      <div v-else class="rounded-xl border border-slate-600 bg-slate-900/60 p-4 text-sm text-slate-300">{{ tt('app.loading_profile') }}</div>
    </div>

    <div v-else-if="showFullAdminShell && tab === 'insights'" class="space-y-3">
      <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <p class="text-sm font-semibold text-slate-900 dark:text-slate-100">{{ tt('admin.insights.summary_title', { hours: insights.window_hours || 24 }) }}</p>
        <div class="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
          <div class="rounded-lg bg-slate-100 p-2 dark:bg-slate-900/70">{{ tt('admin.insights.metric_group_joins') }} <b>{{ insights.group_joins_count || 0 }}</b></div>
          <div class="rounded-lg bg-slate-100 p-2 dark:bg-slate-900/70">{{ tt('admin.insights.metric_starts') }} <b>{{ insights.starts_count || 0 }}</b></div>
          <div class="rounded-lg bg-slate-100 p-2 dark:bg-slate-900/70">{{ tt('admin.insights.metric_payments') }} <b>{{ insights.payments_count || 0 }}</b></div>
          <div class="rounded-lg bg-slate-100 p-2 dark:bg-slate-900/70">{{ tt('admin.insights.metric_payments_sum') }} <b>{{ insights.payments_sum_rub || 0 }} ₽</b></div>
          <div class="rounded-lg bg-slate-100 p-2 dark:bg-slate-900/70">{{ tt('admin.insights.metric_referral_shares') }} <b>{{ insights.referral_shares_count || 0 }}</b></div>
        </div>
        <p class="mt-3 text-xs font-semibold text-slate-700 dark:text-slate-300">{{ tt('admin.insights.referral_levels') }}</p>
        <div class="mt-1 space-y-1 text-xs text-slate-700 dark:text-slate-300">
          <div v-for="lvl in (insights.referral_levels || [])" :key="`lvl-${lvl.level}`" class="rounded-lg bg-slate-50 px-2 py-1 dark:bg-slate-900/60">
            {{ tt('admin.insights.level_line', { level: lvl.level, payments: lvl.payments_count, sales: lvl.sales_sum_rub, reward: lvl.reward_sum_rub }) }}
          </div>
          <div v-if="!(insights.referral_levels || []).length" class="text-slate-500">{{ tt('admin.insights.levels_empty') }}</div>
        </div>
      </div>
      <button type="button" class="w-full rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-60" :disabled="insightsLoading" @click="loadInsights()">
        {{ tt('admin.insights.refresh') }}
      </button>
    </div>

    <div v-else-if="showFullAdminShell && tab === 'messages'" class="space-y-3">
      <div class="rounded-2xl border border-violet-400/35 bg-gradient-to-br from-slate-900 to-slate-800 p-3 text-slate-100 shadow-[0_0_24px_-10px_rgba(139,92,246,0.55)]">
        <div class="flex items-center justify-between gap-2">
          <div>
            <p class="text-sm font-semibold">{{ tt('admin.msg_templates.hero_title') }}</p>
            <p class="mt-0.5 text-[11px] text-slate-300">{{ tt('admin.msg_templates.hero_sub') }}</p>
          </div>
          <button type="button" class="rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-violet-500" @click="createMessageTemplate">{{ tt('admin.msg_templates.add') }}</button>
        </div>
      </div>
      <div class="rounded-xl border border-slate-200 bg-white p-2 text-[11px] text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
        <span>{{ tt('admin.msg_templates.variables_intro') }}</span>
        <span v-pre class="ml-1">
          <code>{{count}}</code> <code>{{hours}}</code> <code>{{payments_sum}}</code> <code>{{event_label}}</code> <code>{{date}}</code>
        </span>
      </div>
      <div v-for="item in msgTemplates" :key="`tpl-${item.id}`" class="rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <div class="flex items-start justify-between gap-2">
          <div class="w-full space-y-1">
            <input v-model="item.title" class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-900" :placeholder="tt('admin.msg_templates.title_placeholder')" />
            <p class="text-[11px] text-slate-500">{{ tt('admin.msg_templates.key_prefix') }} {{ item.template_key }}</p>
          </div>
          <label class="flex items-center gap-1 rounded-lg border border-slate-300 px-2 py-1 text-xs text-slate-600 dark:border-slate-600 dark:text-slate-300">
            <input v-model="item.enabled" type="checkbox" />
            {{ tt('admin.msg_templates.enabled_checkbox') }}
          </label>
        </div>
        <div class="mt-2 grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-3">
          <label class="space-y-1">
            <span class="text-slate-500">{{ tt('admin.msg_templates.field_event') }}</span>
            <select v-model="item.event_key" class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-900">
              <option v-for="o in (msgTemplateOptions.events || [])" :key="`evt-${o.id}`" :value="o.id">{{ o.label }}</option>
            </select>
          </label>
          <label class="space-y-1">
            <span class="text-slate-500">{{ tt('admin.msg_templates.field_target') }}</span>
            <select v-model="item.target_kind" class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-900">
              <option v-for="o in (msgTemplateOptions.targets || [])" :key="`tgt-${o.id}`" :value="o.id">{{ o.label }}</option>
            </select>
          </label>
          <label class="space-y-1">
            <span class="text-slate-500">{{ tt('admin.msg_templates.field_window_hours') }}</span>
            <input v-model="item.trigger_hours" type="number" min="1" max="168" class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-900" />
          </label>
          <label class="space-y-1">
            <span class="text-slate-500">{{ tt('admin.msg_templates.field_min_count') }}</span>
            <input v-model="item.min_count" type="number" min="1" class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-900" />
          </label>
          <label class="space-y-1">
            <span class="text-slate-500">{{ tt('admin.msg_templates.field_cooldown') }}</span>
            <input v-model="item.cooldown_minutes" type="number" min="1" class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-900" />
          </label>
          <label class="space-y-1">
            <span class="text-slate-500">{{ tt('admin.msg_templates.field_schedule_utc') }}</span>
            <input v-model="item.schedule_time_hm" class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-900" :placeholder="tt('admin.msg_templates.ph_schedule')" />
          </label>
          <label class="space-y-1">
            <span class="text-slate-500">{{ tt('admin.msg_templates.field_delay') }}</span>
            <input v-model="item.delay_minutes" type="number" min="1" class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-900" :placeholder="tt('admin.msg_templates.ph_delay')" />
          </label>
          <label class="space-y-1">
            <span class="text-slate-500">{{ tt('admin.msg_templates.field_parse_mode') }}</span>
            <input v-model="item.parse_mode" class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-900" :placeholder="tt('admin.msg_templates.ph_parse_mode')" />
          </label>
        </div>
        <textarea v-model="item.body_text" rows="5" class="mt-2 w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs dark:border-slate-600 dark:bg-slate-900" />
        <div class="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <button type="button" class="rounded-lg bg-emerald-600 px-3 py-1.5 font-semibold text-white disabled:opacity-60" :disabled="msgTemplateSavingId === item.id" @click="saveMessageTemplate(item)">{{ tt('common.save') }}</button>
          <button v-if="item.is_custom" type="button" class="rounded-lg bg-rose-600 px-3 py-1.5 font-semibold text-white" @click="deleteMessageTemplate(item)">{{ tt('admin.msg_templates.delete') }}</button>
        </div>
      </div>
      <button type="button" class="w-full rounded-lg bg-slate-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-60" :disabled="msgTemplatesLoading" @click="loadMessageTemplates()">
        {{ tt('admin.msg_templates.refresh_list') }}
      </button>
    </div>

    <div v-else-if="tab === 'broadcasts'" class="bc-broadcast-shell relative -mx-4 min-w-0 overflow-x-clip overflow-y-visible md:-mx-6">
      <div
        class="min-w-0 space-y-2.5 px-4 py-3 md:px-6 pb-[max(5.25rem,calc(5.75rem+env(safe-area-inset-bottom,0px)))] md:pb-[max(6rem,calc(6.5rem+env(safe-area-inset-bottom,0px)))]"
      >
      <div class="rounded-2xl border border-white/[0.08] bg-gradient-to-b from-[#0f141d]/94 via-[#0c1017]/96 to-black/95 px-3 py-3 shadow-[0_18px_48px_-24px_rgba(0,0,0,0.95)] ring-1 ring-white/[0.05]">
        <p class="text-[24px] font-black leading-none tracking-tight text-white">{{ tt('admin.broadcast_shell.title') }}</p>
        <p class="mt-1 text-[12px] leading-snug text-zinc-300">{{ tt('admin.broadcast_shell.subtitle') }}</p>

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
                <span class="block truncate text-[18px] font-extrabold leading-tight text-white">{{ tt('admin.broadcast_shell.quick_title') }}</span>
                <span class="mt-0.5 block text-[12px] text-slate-200/90">{{ tt('admin.broadcast_shell.quick_sub') }}</span>
              </span>
            </span>
          </button>

          <button
            type="button"
            class="w-full rounded-xl border border-emerald-400/30 bg-gradient-to-r from-[#1e3f19]/92 via-[#1f4a1e]/90 to-[#183614]/92 px-3 py-2.5 text-left shadow-[0_12px_24px_-16px_rgba(34,197,94,0.7),inset_0_1px_0_rgba(255,255,255,0.11)] ring-1 ring-emerald-300/20 transition active:scale-[0.995]"
            @click="openBcCampaignUxList"
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
                <span class="block truncate text-[18px] font-extrabold leading-tight text-white">{{ tt('admin.broadcast_shell.campaigns_title') }}</span>
                <span class="mt-0.5 block text-[12px] text-slate-200/90">{{ tt('admin.broadcast_shell.campaigns_sub') }}</span>
              </span>
            </span>
          </button>
        </div>

        <div class="mt-3 border-t border-white/[0.08] pt-3">
          <div class="flex items-center justify-between gap-2">
            <p class="text-[19px] font-black tracking-tight text-white">{{ tt('admin.broadcast_shell.recent_title') }}</p>
            <button
              type="button"
              class="text-[14px] font-bold text-[#59a6ff] transition hover:text-[#7cbcff]"
              :disabled="!bcRecentBroadcastsFiltered.length"
              @click="bcShowAllRecentModal = true"
            >
              {{ tt('admin.broadcast_shell.view_all') }}
            </button>
          </div>

          <div class="mt-2 flex flex-wrap gap-1.5">
            <button
              type="button"
              class="rounded-lg border px-2.5 py-1 text-[11px] font-semibold transition"
              :class="bcRecentListPreset === 'all' ? 'border-sky-400/45 bg-sky-500/15 text-sky-100' : 'border-white/10 bg-white/[0.03] text-zinc-400'"
              @click="bcRecentListPreset = 'all'"
            >
              {{ tt('admin.broadcast_shell.recent_preset_all') }}
            </button>
            <button
              type="button"
              class="rounded-lg border px-2.5 py-1 text-[11px] font-semibold transition"
              :class="bcRecentListPreset === 'oneshot' ? 'border-sky-400/45 bg-sky-500/15 text-sky-100' : 'border-white/10 bg-white/[0.03] text-zinc-400'"
              @click="bcRecentListPreset = 'oneshot'"
            >
              {{ tt('admin.broadcast_shell.recent_preset_oneshot') }}
            </button>
            <button
              type="button"
              class="rounded-lg border px-2.5 py-1 text-[11px] font-semibold transition"
              :class="bcRecentListPreset === 'scheduled' ? 'border-violet-400/45 bg-violet-500/15 text-violet-100' : 'border-white/10 bg-white/[0.03] text-zinc-400'"
              @click="bcRecentListPreset = 'scheduled'"
            >
              {{ tt('admin.broadcast_shell.recent_preset_scheduled') }}
            </button>
          </div>

          <div class="mt-2 space-y-2">
            <div
              v-for="item in bcRecentBroadcastsPreview"
              :key="`recent-bc-${item.schedule_id || item.run_id || item.autopost_campaign_id || item.id}-${item.scheduled_at || item.sent_at || ''}`"
              role="button"
              tabindex="0"
              class="cursor-pointer rounded-xl border border-white/[0.07] bg-[#111827]/88 px-3 py-2.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] ring-1 ring-white/[0.03] transition hover:border-white/[0.12] hover:bg-[#151d2e]/90"
              @click="bcOpenRecentBroadcastStats(item)"
              @keydown.enter.prevent="bcOpenRecentBroadcastStats(item)"
              @keydown.space.prevent="bcOpenRecentBroadcastStats(item)"
            >
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <p class="truncate text-[15px] font-extrabold text-zinc-100">{{ bcRecentBroadcastDisplayTitle(item) }}</p>
                  <p class="mt-0.5 text-[11px] text-zinc-400">
                    <span :class="bcRecentOneShotStatusClass(item)">{{ bcRecentStatusLabel(item) }}</span>
                    <span> · </span
                    ><span :class="bcRecentBroadcastKindIsCampaign(item) ? 'font-semibold text-emerald-400' : 'font-semibold text-sky-400'">{{ bcRecentBroadcastKindLabel(item) }}</span
                    ><span> · {{ bcRecentWhenLabel(item) }}</span>
                  </p>
                </div>
                <span class="text-lg leading-none text-zinc-500">›</span>
              </div>
              <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-zinc-300">
                <span>{{ bcRecentCardPrimaryLabel(item) }} <b class="text-zinc-100">{{ fmtIntSpace(bcRecentCardPrimaryValue(item, bcRecentPulseEntry(item.id))) }}</b></span>
                <span>{{ tt('admin.broadcast_shell.delivered_ok') }} <b class="text-zinc-100">{{ Number(item.recipient_ok || 0) }}</b></span>
                <span>{{ tt('admin.broadcast_shell.errors') }} <b class="text-zinc-100">{{ Number(item.recipient_fail || 0) }}</b></span>
              </div>
            </div>
            <p v-if="!bcRecentBroadcastsPreview.length" class="rounded-xl border border-white/[0.07] bg-[#111827]/80 px-3 py-2 text-[12px] text-zinc-400">
              {{ tt('admin.broadcast_shell.recent_empty') }}
            </p>
          </div>
        </div>
      </div>

      <GuardTeleport guard-to="body">
        <div
          v-if="bcQuickDraftModalOpen"
          class="fixed inset-0 z-[95000] flex min-h-[100dvh] min-w-0 flex-col bg-[#0b0d14] pb-[env(safe-area-inset-bottom,0px)] pt-[max(0.25rem,calc(env(safe-area-inset-top,0px)+48px))]"
          @click.self="closeQuickBroadcastDraft"
        >
          <div class="flex min-h-0 w-full flex-1 flex-col overflow-y-auto overscroll-contain px-3 py-2">
            <div class="flex flex-col bg-[#12161f] p-3 text-zinc-100">
          <div class="mb-2 flex items-start justify-between gap-2 pb-2">
            <div class="min-w-0 flex-1">
              <p class="truncate text-[19px] font-black text-white">{{ tt('admin.broadcast_ui.quick_new_broadcast') }}</p>
              <div class="mt-1.5 flex min-w-0 items-center gap-1.5">
                <input
                  ref="bcQuickDraftTitleInputRef"
                  v-model="bcTitle"
                  type="text"
                  class="min-w-0 flex-1 rounded-lg border border-white/10 bg-zinc-950/80 px-2.5 py-1.5 text-[13px] text-zinc-200 placeholder:text-zinc-500 focus:border-cyan-500/45 focus:outline-none focus:ring-1 focus:ring-cyan-500/25"
                  :placeholder="tt('admin.broadcast_ui.draft_title_ph')"
                  maxlength="255"
                  :disabled="Number(bcSavingTitleId || 0) === Number(bcSelectedId || 0) && Number(bcSelectedId || 0) > 0"
                  @keydown.enter.prevent="applyBcQuickDraftTitle"
                />
                <button
                  v-show="bcQuickTitleDirty"
                  type="button"
                  class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-emerald-500/40 bg-emerald-500/20 text-[13px] font-bold text-emerald-200 shadow-[0_0_20px_-4px_rgba(16,185,129,0.5)] transition active:scale-95 hover:border-emerald-400/55 hover:bg-emerald-500/30 disabled:opacity-50"
                  :disabled="Number(bcSavingTitleId || 0) === Number(bcSelectedId || 0) && Number(bcSelectedId || 0) > 0"
                  :title="tt('admin.broadcast_ui.apply_title')"
                  @click="applyBcQuickDraftTitle"
                >
                  ✓
                </button>
              </div>
            </div>
            <div class="flex items-center gap-1">
              <button
                type="button"
                class="rounded-lg px-2 py-1 text-[13px] font-bold transition hover:bg-white/10 disabled:cursor-wait disabled:opacity-70"
                :class="bcQuickSaveBtnClass"
                :disabled="bcSaving"
                :aria-busy="bcSaving"
                @click="saveBcDraft"
              >
                <span class="relative inline-flex min-w-[5.25rem] items-center justify-center">
                  <span
                    v-if="bcSaving"
                    class="absolute inset-0 flex items-center justify-center"
                    aria-hidden="true"
                  >
                    <span
                      class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current/20 border-t-current"
                    />
                  </span>
                  <span :class="bcSaving ? 'opacity-0' : ''">{{ bcQuickSaveBtnLabel }}</span>
                </span>
              </button>
              <button
                type="button"
                class="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-transparent text-sm text-zinc-200 hover:bg-white/[0.08]"
                :aria-label="tt('admin.broadcast_ui.close')"
                :disabled="bcSaving"
                @click="closeQuickBroadcastDraft"
              >
                ✕
              </button>
            </div>
          </div>

          <p class="text-[12px] font-semibold text-zinc-300">{{ tt('admin.broadcast_ui.message_text') }}</p>
          <div
            ref="bcBodyRef"
            class="bc-editor mt-2 h-40 min-h-[10rem] shrink-0 overflow-y-auto rounded-xl border border-white/[0.08] bg-zinc-950 px-3 py-2.5 text-sm leading-relaxed focus-within:border-white/20 focus-within:ring-0"
            contenteditable="true"
            :data-placeholder="tt('admin.broadcast_ui.message_body_ph')"
            @input="onBcEditorInput"
            @paste="bcOnEditorPaste"
            @keydown="bcOnEditorKeydown"
            @click="onBcEditorClick"
            @mouseup="bcUpdateFormatState"
            @keyup="bcUpdateFormatState"
          />

          <div class="mt-2 flex flex-wrap gap-1.5">
            <button type="button" class="bc-tool-btn min-w-[2.1rem] !px-2" :class="bcFormatState.bold ? 'bc-tool-active' : ''" @mousedown.prevent @click="bcFormatBold"><b>B</b></button>
            <button type="button" class="bc-tool-btn min-w-[2.1rem] !px-2" :class="bcFormatState.italic ? 'bc-tool-active' : ''" @mousedown.prevent @click="bcFormatItalic"><i>I</i></button>
            <button type="button" class="bc-tool-btn min-w-[2.1rem] !px-2" :class="bcFormatState.underline ? 'bc-tool-active' : ''" @mousedown.prevent @click="bcFormatUnderline"><u>U</u></button>
            <button type="button" class="bc-tool-btn min-w-[2.1rem] !px-2" :class="bcFormatState.strike ? 'bc-tool-active' : ''" @mousedown.prevent @click="bcFormatStrike"><s>S</s></button>
            <button type="button" class="bc-tool-btn min-w-[2.1rem] !px-2 !text-[11px]" :class="bcFormatState.quote ? 'bc-tool-active' : ''" title="Цитата" @mousedown.prevent @click="bcFormatBlockquote">❝</button>
            <button type="button" class="bc-tool-btn min-w-[2.1rem] !px-2 !text-[11px]" :class="bcFormatState.spoiler ? 'bc-tool-active' : ''" title="Скрытый" @mousedown.prevent @click="bcFormatSpoiler">🙈</button>
            <button type="button" class="bc-tool-btn min-w-[2.1rem] !px-2 !text-[11px]" :class="bcFormatState.link ? 'bc-tool-active' : ''" title="Ссылка" @mousedown.prevent @click="bcFormatLink">🔗</button>
            <button type="button" class="bc-tool-btn font-mono min-w-[2.1rem] !px-2 !text-[11px]" title="Моноширинный блок" @mousedown.prevent @click="bcFormatPre">⌨</button>
            <button type="button" class="bc-tool-btn !px-2 !text-[11px]" :class="!bcCanUndo() ? 'opacity-40' : ''" :disabled="!bcCanUndo()" @mousedown.prevent @click="bcUndo">↶</button>
            <button type="button" class="bc-tool-btn !px-2 !text-[11px]" :class="!bcCanRedo() ? 'opacity-40' : ''" :disabled="!bcCanRedo()" @mousedown.prevent @click="bcRedo">↷</button>
          </div>

          <p class="mt-1 text-[11px]" :class="bcCurrentLen() > bcCurrentMaxLen() ? 'text-rose-400' : 'text-slate-500'">
            {{ tt('admin.broadcast_ui.chars_count', { current: bcCurrentLen(), max: bcCurrentMaxLen() }) }}
          </p>

          <div class="mt-3">
            <p class="text-[12px] font-semibold text-zinc-300">{{ tt('admin.broadcast_ui.buttons_block') }}</p>
            <div v-if="bcQuickButtonPreviewRows.length" class="mt-1.5 space-y-1">
              <div
                v-for="(row, ri) in bcQuickButtonPreviewRows.slice(0, 4)"
                :key="`quick-brow-${ri}`"
                class="flex flex-wrap gap-1"
              >
                <div
                  v-for="(btn, bi) in row"
                  :key="`quick-bbtn-${ri}-${bi}-${btn.text}`"
                  class="min-w-0 flex-1"
                  :class="[bcButtonStyleChipClass(btn.style, btn.kind), row.length === 1 ? 'basis-full' : 'basis-[calc(50%-0.125rem)]']"
                >
                  <p class="truncate text-[12px]">{{ btn.text }}</p>
                </div>
              </div>
            </div>
            <button type="button" class="bc-tool-btn mt-1.5 !text-[12px]" @click="bcAuxModal = 'keyboard'">{{ tt('admin.broadcast_ui.add_post_buttons') }}</button>
          </div>

          <div class="mt-3">
            <p class="text-[12px] font-semibold text-zinc-300">{{ tt('admin.broadcast_ui.attachments') }}</p>
            <div v-if="bcMediaHistory.length" class="mt-1.5 flex flex-wrap gap-2">
              <div v-for="(m, mi) in bcMediaHistory.slice(0, 4)" :key="`quick-pv-${mi}-${m.id || mi}`" class="relative shrink-0">
                <button
                  v-if="m.previewUrl && (String(m.kind || '').toLowerCase().includes('photo') || String(m.kind || '').toLowerCase().includes('video') || String(m.kind || '').toLowerCase() === 'animation')"
                  type="button"
                  class="group relative block h-14 w-14 overflow-hidden rounded-lg border border-white/15 bg-slate-950/80 shadow-md ring-1 ring-white/[0.06] transition hover:border-cyan-400/35 hover:ring-cyan-400/25"
                  :title="tt('admin.broadcast_ui.open_large')"
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
            <button type="button" class="bc-tool-btn mt-1.5 !text-[12px]" @click="bcAuxModal = 'media'">{{ tt('admin.broadcast_ui.file_and_media') }}</button>
          </div>

          <button
            type="button"
            class="mt-4 w-full shrink-0 rounded-xl border border-indigo-400/40 bg-gradient-to-r from-indigo-600/95 to-blue-700/95 px-4 py-2 text-[13px] font-extrabold text-white shadow-[0_14px_30px_-16px_rgba(59,130,246,0.8)]"
            :class="!String(bcTitle || '').trim() || !bcHasMessageText() ? 'cursor-not-allowed opacity-45' : ''"
            @click="bcQuickDraftTryNext"
          >
            {{ tt('common.next') }}
          </button>
            </div>
          </div>
        </div>
      </GuardTeleport>

      <GuardTeleport guard-to="body">
        <div
          v-if="bcSendTargetModalOpen"
          class="fixed inset-0 z-[95200] flex min-h-[100dvh] min-w-0 flex-col bg-[#0b0d14] pb-[env(safe-area-inset-bottom,0px)] pt-[max(0.25rem,calc(env(safe-area-inset-top,0px)+48px))]"
          @click.self="bcSendTargetModalOpen = false"
        >
          <div class="flex min-h-0 w-full flex-1 flex-col overflow-y-auto overscroll-contain px-3 py-2">
            <div class="flex flex-col rounded-2xl border border-white/[0.04] bg-[#12161f] p-3 text-zinc-100 shadow-[0_24px_72px_-28px_rgba(0,0,0,0.9)] ring-1 ring-white/[0.02]">
          <div class="flex items-center justify-between gap-2">
            <div class="flex min-w-0 items-center gap-1">
              <button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-transparent text-[14px] text-white/90 hover:bg-white/[0.08]" @click="bcOneShotFlowBack">←</button>
              <p class="truncate text-[19px] font-black text-white">{{ tt('admin.broadcast_ui.send_where') }}</p>
            </div>
            <button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-transparent text-[14px] text-white/90 hover:bg-white/[0.08]" @click="bcSendTargetModalOpen = false">✕</button>
          </div>
          <p class="mt-2 text-[13px] text-zinc-400">{{ tt('admin.broadcast_ui.choose_recipients') }}</p>

          <div class="mt-4 space-y-2.5">
            <button
              type="button"
              class="flex w-full items-center justify-between gap-3 rounded-xl bg-white/[0.035] px-3 py-2.5 text-left"
              @click="bcToggleSendTargetChannels"
            >
              <span class="min-w-0">
                <span class="block text-[18px] font-extrabold text-white">{{ tt('admin.broadcast_ui.channels_title') }}</span>
                <span class="block text-[12px] text-slate-200/90">{{ tt('admin.broadcast_ui.channels_sub') }}</span>
              </span>
              <span class="inline-flex h-6 w-6 items-center justify-center rounded-md border text-[14px] font-black" :class="bcSendTargetChannels ? 'border-violet-300/55 bg-violet-600/85 text-white' : 'border-white/35 bg-transparent text-transparent'">✓</span>
            </button>

            <button
              type="button"
              class="flex w-full items-center justify-between gap-3 rounded-xl bg-white/[0.035] px-3 py-2.5 text-left"
              @click="bcToggleSendTargetGroups"
            >
              <span class="min-w-0">
                <span class="block text-[18px] font-extrabold text-white">{{ tt('admin.broadcast_ui.groups_title') }}</span>
                <span class="block text-[12px] text-slate-200/90">{{ tt('admin.broadcast_ui.groups_sub') }}</span>
              </span>
              <span class="inline-flex h-6 w-6 items-center justify-center rounded-md border text-[14px] font-black" :class="bcSendTargetGroups ? 'border-violet-300/55 bg-violet-600/85 text-white' : 'border-white/35 bg-transparent text-transparent'">✓</span>
            </button>

            <label
              v-if="showFullAdminShell"
              class="flex cursor-pointer items-start gap-3 rounded-xl border border-cyan-500/28 bg-white/[0.04] px-3 py-2.5 text-left"
            >
              <input v-model="bcAdminIncludeBotRecipients" type="checkbox" class="mt-1 size-5 shrink-0 rounded border-white/25 bg-transparent text-indigo-500 focus:ring-indigo-500/40" />
              <span class="min-w-0">
                <span class="block text-[16px] font-extrabold text-white">{{ tt('admin.broadcast_ui.include_bot_users') }}</span>
                <span class="mt-0.5 block text-[12px] text-slate-300/95">{{ tt('admin.broadcast_ui.include_bot_users_sub') }}</span>
              </span>
            </label>
          </div>

          <div class="mt-5">
            <p class="text-[13px] font-semibold text-zinc-300">{{ tt('admin.broadcast_ui.selected') }}</p>
            <div class="mt-1.5 space-y-1.5">
              <button
                v-if="bcSendTargetChannels"
                type="button"
                class="flex w-full items-center justify-between rounded-xl bg-white/[0.04] px-3 py-2 text-left text-[14px] font-semibold text-zinc-100"
                @click="openBcBroadcastChannelsPickerInFlow()"
              >
                <span>{{ tt('admin.broadcast_send.target_channels', { n: Number(bcSelectedChannelIds.length || 0) }) }}</span>
                <span>›</span>
              </button>
              <button
                v-if="bcSendTargetGroups"
                type="button"
                class="flex w-full items-center justify-between rounded-xl bg-white/[0.04] px-3 py-2 text-left text-[14px] font-semibold text-zinc-100"
                @click="openBcBroadcastGroupsPickerInFlow()"
              >
                <span>{{ tt('admin.broadcast_send.target_groups', { n: Number(bcSelectedGroupIds.length || 0) }) }}</span>
                <span>›</span>
              </button>
              <p v-if="!bcSendTargetSummary.length" class="rounded-xl bg-white/[0.03] px-3 py-2 text-[12px] text-zinc-400">{{ tt('admin.broadcast_ui.nothing_selected') }}</p>
            </div>
          </div>

          <div v-if="bcSendQuoteError" class="mt-3 rounded-xl border border-rose-500/35 bg-rose-950/40 px-3 py-2 text-[12px] leading-snug text-rose-50">
            {{ bcSendQuoteError }}
          </div>

          <button
            type="button"
            class="mt-4 w-full rounded-xl border border-indigo-400/40 bg-gradient-to-r from-indigo-600/95 to-blue-700/95 px-4 py-2 text-[13px] font-extrabold text-white shadow-[0_14px_30px_-16px_rgba(59,130,246,0.8)]"
            :class="!bcCanProceedSendTargets || bcConfirmLoading ? 'cursor-not-allowed opacity-45' : ''"
            :disabled="!bcCanProceedSendTargets || bcConfirmLoading"
            @click="proceedSendTargetModal()"
          >
            {{ tt('common.next') }}
          </button>
            </div>
          </div>
        </div>
      </GuardTeleport>

      <GuardTeleport guard-to="body">
        <div
          v-if="bcSendTimingModalOpen"
          class="fixed inset-0 z-[95250] flex min-h-[100dvh] min-w-0 flex-col bg-[#0b0d14] pb-[env(safe-area-inset-bottom,0px)] pt-[max(0.25rem,calc(env(safe-area-inset-top,0px)+48px))]"
          @click.self="bcSendTimingModalOpen = false"
        >
          <div class="flex min-h-0 w-full flex-1 flex-col overflow-y-auto overscroll-contain px-3 py-2">
            <div class="flex flex-col rounded-2xl border border-white/[0.04] bg-[#12161f] p-3 text-zinc-100 shadow-[0_24px_72px_-28px_rgba(0,0,0,0.9)] ring-1 ring-white/[0.02]">
              <div class="flex items-center justify-between gap-2">
                <div class="flex min-w-0 items-center gap-1">
                  <button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-transparent text-[14px] text-white/90 hover:bg-white/[0.08]" @click="bcOneShotFlowBack">←</button>
                  <p class="truncate text-[19px] font-black text-white">{{ tt('admin.broadcast_ui.timing_title') }}</p>
                </div>
                <button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-transparent text-[14px] text-white/90 hover:bg-white/[0.08]" @click="bcSendTimingModalOpen = false">✕</button>
              </div>
              <p class="mt-2 text-[13px] text-zinc-400">{{ tt('admin.broadcast_ui.timing_sub') }}</p>

              <div class="mt-4 space-y-2.5">
                <button
                  type="button"
                  class="flex w-full items-center justify-between gap-3 rounded-xl bg-white/[0.035] px-3 py-2.5 text-left"
                  @click="bcSendTimingMode = 'now'"
                >
                  <span class="min-w-0">
                    <span class="block text-[18px] font-extrabold text-white">{{ tt('admin.broadcast_ui.timing_now') }}</span>
                    <span class="block text-[12px] text-slate-200/90">{{ tt('admin.broadcast_ui.timing_now_sub') }}</span>
                  </span>
                  <span class="inline-flex h-6 w-6 items-center justify-center rounded-md border text-[14px] font-black" :class="bcSendTimingMode === 'now' ? 'border-violet-300/55 bg-violet-600/85 text-white' : 'border-white/35 bg-transparent text-transparent'">✓</span>
                </button>

                <button
                  type="button"
                  class="flex w-full items-center justify-between gap-3 rounded-xl bg-white/[0.035] px-3 py-2.5 text-left"
                  @click="bcSendTimingMode = 'scheduled'"
                >
                  <span class="min-w-0">
                    <span class="block text-[18px] font-extrabold text-white">{{ tt('admin.broadcast_ui.timing_scheduled') }}</span>
                    <span class="block text-[12px] text-slate-200/90">{{ tt('admin.broadcast_ui.timing_scheduled_sub') }}</span>
                  </span>
                  <span class="inline-flex h-6 w-6 items-center justify-center rounded-md border text-[14px] font-black" :class="bcSendTimingMode === 'scheduled' ? 'border-violet-300/55 bg-violet-600/85 text-white' : 'border-white/35 bg-transparent text-transparent'">✓</span>
                </button>
              </div>

              <div v-if="bcSendTimingMode === 'scheduled'" class="mt-4">
                <label class="text-[13px] font-semibold text-zinc-300">{{ tt('admin.broadcast_ui.timing_datetime_label') }}</label>
                <input
                  v-model="bcSendScheduleAtLocal"
                  type="datetime-local"
                  class="mt-1.5 w-full rounded-xl border border-white/10 bg-zinc-950/80 px-3 py-2 text-[14px] text-zinc-100"
                />
              </div>

              <div v-if="bcSendQuoteError" class="mt-3 rounded-xl border border-rose-500/35 bg-rose-950/40 px-3 py-2 text-[12px] leading-snug text-rose-50">
                {{ bcSendQuoteError }}
              </div>

              <button
                type="button"
                class="mt-4 w-full rounded-xl border border-indigo-400/40 bg-gradient-to-r from-indigo-600/95 to-blue-700/95 px-4 py-2 text-[13px] font-extrabold text-white shadow-[0_14px_30px_-16px_rgba(59,130,246,0.8)]"
                :class="bcConfirmLoading ? 'cursor-not-allowed opacity-45' : ''"
                :disabled="bcConfirmLoading"
                @click="proceedSendTimingModal()"
              >
                {{ tt('common.next') }}
              </button>
            </div>
          </div>
        </div>
      </GuardTeleport>

      <GuardTeleport>
      <div
        v-if="bcConfirmModalOpen"
        class="fixed inset-0 z-[95350] flex flex-col overflow-y-auto bg-[#0b0d14] px-1.5 pb-[max(5.75rem,calc(5.25rem+env(safe-area-inset-bottom,0px)))] pt-[max(0.25rem,calc(env(safe-area-inset-top,0px)+46px))]"
        @click.self="bcConfirmModalOpen = false"
      >
        <div
          class="mx-auto flex w-full max-w-[min(28rem,calc(100vw-0.75rem))] min-h-[calc(100dvh-7.9rem)] flex-col rounded-2xl border border-white/[0.08] bg-[#101622] px-2.5 py-2.5 text-zinc-100 shadow-[0_22px_70px_-30px_rgba(0,0,0,0.88)]"
        >
          <div class="flex items-center gap-2">
            <button type="button" class="inline-flex h-7 w-7 items-center justify-center rounded-full bg-transparent text-[13px] text-white/90 hover:bg-white/[0.08]" @click="bcOneShotFlowBack">←</button>
            <p class="text-[19px] font-bold text-white leading-none">{{ tt('admin.broadcast_ui.confirmation') }}</p>
          </div>

          <div class="mt-3 text-center">
            <div
              class="mx-auto mb-2 flex h-[5.15rem] w-[5.15rem] items-center justify-center rounded-full border border-violet-300/22 bg-[#1a1330]/45 shadow-[0_0_22px_-8px_rgba(139,92,246,0.55)]"
            >
              <svg viewBox="0 0 24 24" class="h-9 w-9 text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.3)]" fill="currentColor" aria-hidden="true">
                <path d="M21.5 4.8 18.4 19c-.2.9-.8 1.1-1.6.7l-4.4-3.2-2.1 2c-.2.2-.4.4-.9.4l.3-4.5 8.3-7.5c.4-.3-.1-.5-.5-.2l-10.2 6.4-4.4-1.4c-.9-.3-.9-.9.2-1.3L19.9 4c.8-.3 1.5.2 1.3.8z" />
              </svg>
            </div>
            <p class="text-[18px] font-extrabold text-white leading-tight">{{ tt('admin.broadcast_ui.ready_title') }}</p>
            <p class="mx-auto mt-1 max-w-[17rem] text-[13px] leading-[1.35] text-zinc-300/95">{{ bcConfirmReadySub }}</p>
          </div>

          <div class="mt-4 rounded-xl border border-white/[0.07] bg-white/[0.02] px-3 py-2">
            <div v-if="bcSendTimingMode === 'scheduled'" class="flex items-center justify-between gap-3 py-1.5 text-[13px] leading-snug">
              <span class="text-zinc-300">{{ tt('admin.broadcast_ui.row_scheduled_at') }}</span>
              <span class="text-right font-semibold text-violet-200">{{ bcFormatScheduledAtLabel(new Date(String(bcSendScheduleAtLocal || '')).toISOString(), typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone : '') }}</span>
            </div>
            <div class="flex items-center justify-between gap-3 py-1.5 text-[13px] leading-snug">
              <span class="text-zinc-300">{{ tt('admin.broadcast_ui.row_recipients') }}</span>
              <span class="text-right font-semibold text-zinc-100">{{ bcConfirmRecipientLabel }}</span>
            </div>
            <div class="flex items-center justify-between gap-3 py-1.5 text-[13px] leading-snug">
              <span class="text-zinc-300">{{ tt('admin.broadcast_ui.row_message') }}</span>
              <span class="text-right font-semibold text-zinc-100">{{ bcConfirmSymbolsLabel(bcConfirmMessageLen) }}</span>
            </div>
            <div class="flex items-center justify-between gap-3 py-1.5 text-[13px] leading-snug">
              <span class="text-zinc-300">{{ tt('admin.broadcast_ui.row_buttons') }}</span>
              <span class="text-right font-semibold text-zinc-100">{{ bcConfirmButtonsLabel(bcConfirmButtonsCount) }}</span>
            </div>
            <div class="flex items-center justify-between gap-3 py-1.5 text-[13px] leading-snug">
              <span class="text-zinc-300">{{ tt('admin.broadcast_ui.row_attachments') }}</span>
              <span class="text-right font-semibold text-zinc-100">{{ bcConfirmHasMedia ? tt('admin.broadcast_ui.has_yes') : tt('admin.broadcast_ui.has_no') }}</span>
            </div>
          </div>

          <div class="mt-2.5 flex items-center justify-between gap-3 rounded-xl border border-white/[0.07] bg-white/[0.02] px-3 py-2">
            <span class="text-[14px] font-semibold text-zinc-100">{{ tt('admin.broadcast_ui.cost') }}</span>
            <span class="text-[15px] font-black text-amber-300">{{ bcConfirmLoading ? '...' : `${bcConfirmQuoteTokens} AURUM` }}</span>
          </div>

          <div class="mt-auto pt-4">
            <div class="flex gap-2">
              <button type="button" class="flex-1 rounded-xl border border-white/12 bg-[#171e2e]/95 px-3 py-2 text-[15px] font-semibold text-[#7590d8]" :disabled="bcConfirmSending" @click="bcConfirmModalOpen = false">{{ tt('common.cancel') }}</button>
              <button type="button" class="flex-1 rounded-xl border border-indigo-400/45 bg-gradient-to-r from-[#6d3ef7] to-[#4b67ff] px-3 py-2 text-[15px] font-extrabold text-white" :disabled="bcConfirmSending || bcConfirmLoading" @click="submitBcConfirmedSend">{{ bcConfirmSubmitLabel }}</button>
            </div>
          </div>
        </div>
      </div>
      </GuardTeleport>

      <div
        v-if="bcShowAllRecentModal"
        class="fixed inset-0 z-[95000] flex items-end justify-center bg-[#0b0d14] px-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] pt-[max(12px,calc(env(safe-area-inset-top,0px)+48px))] md:items-center md:pb-6"
        @click.self="bcShowAllRecentModal = false"
      >
        <div class="w-full max-w-lg rounded-2xl border border-white/12 bg-[#12161f] p-3 text-zinc-100 shadow-[0_24px_64px_-24px_rgba(0,0,0,0.92)]">
          <div class="mb-2 flex items-center justify-between border-b border-white/10 pb-2">
            <p class="text-[16px] font-extrabold text-white">{{ tt('admin.broadcast_ui.all_recent_title') }}</p>
            <button type="button" class="rounded-lg px-2 py-1 text-sm text-zinc-300 hover:bg-white/10" @click="bcShowAllRecentModal = false">✕</button>
          </div>
          <div class="max-h-[min(70vh,30rem)] space-y-2 overflow-y-auto pr-1">
            <div
              v-for="item in bcRecentBroadcastsFiltered"
              :key="`recent-all-bc-${item.schedule_id || item.run_id || item.autopost_campaign_id || item.id}-${item.scheduled_at || item.sent_at || ''}`"
              role="button"
              tabindex="0"
              class="cursor-pointer rounded-xl border border-white/[0.08] bg-[#121a27]/88 px-3 py-2.5 transition hover:border-white/[0.14] hover:bg-[#172032]/95"
              @click="bcOpenRecentBroadcastStats(item)"
              @keydown.enter.prevent="bcOpenRecentBroadcastStats(item)"
              @keydown.space.prevent="bcOpenRecentBroadcastStats(item)"
            >
              <p class="truncate text-[14px] font-bold text-zinc-100">{{ bcRecentBroadcastDisplayTitle(item) }}</p>
              <p class="mt-0.5 text-[11px] text-zinc-400">
                <span :class="bcRecentOneShotStatusClass(item)">{{ bcRecentStatusLabel(item) }}</span>
                <span> · </span
                ><span :class="bcRecentBroadcastKindIsCampaign(item) ? 'font-semibold text-emerald-400' : 'font-semibold text-sky-400'">{{ bcRecentBroadcastKindLabel(item) }}</span
                ><span> · {{ bcRecentWhenLabel(item) }}</span>
              </p>
              <div class="mt-1.5 flex flex-wrap items-center gap-3 text-[11px] text-zinc-300">
                <span>{{ bcRecentCardPrimaryLabel(item) }} <b class="text-zinc-100">{{ fmtIntSpace(bcRecentCardPrimaryValue(item, bcRecentPulseEntry(item.id))) }}</b></span>
                <span>{{ tt('admin.broadcast_shell.delivered_ok') }} <b class="text-zinc-100">{{ Number(item.recipient_ok || 0) }}</b></span>
                <span>{{ tt('admin.broadcast_shell.errors') }} <b class="text-zinc-100">{{ Number(item.recipient_fail || 0) }}</b></span>
              </div>
            </div>
            <p v-if="!bcRecentBroadcastsFiltered.length" class="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-[12px] text-zinc-400">
              {{ tt('admin.broadcast_shell.recent_empty') }}
            </p>
          </div>
        </div>
      </div>

      <GuardTeleport guard-to="body">
      <div
        v-if="bcRecentStatsModalOpen"
        class="fixed inset-0 z-[95500] flex items-end justify-center bg-black/72 px-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] pt-[max(12px,calc(env(safe-area-inset-top,0px)+48px))] backdrop-blur-[2px] md:items-center md:pb-6"
        @click.self="bcCloseRecentBroadcastStats"
      >
        <div class="flex max-h-[min(85vh,36rem)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/12 bg-[#12161f] text-zinc-100 shadow-[0_24px_64px_-24px_rgba(0,0,0,0.92)]">
          <div class="flex shrink-0 items-start justify-between gap-2 border-b border-white/10 px-4 py-3">
            <div class="min-w-0">
              <p class="truncate text-[16px] font-extrabold leading-snug text-white">{{ bcRecentStatsHeaderTitle }}</p>
              <p class="mt-0.5 text-[12px] text-zinc-500">{{ tt('admin.broadcast_shell.recent_stats_title') }}</p>
              <p v-if="bcRecentStatsBroadcastMeta" class="mt-0.5 text-[11px] text-zinc-500">
                <span :class="bcRecentOneShotStatusClass(bcRecentStatsBroadcastMeta)">{{ bcRecentStatusLabel(bcRecentStatsBroadcastMeta) }}</span>
                <span> · </span
                ><span :class="bcRecentBroadcastKindIsCampaign(bcRecentStatsBroadcastMeta) ? 'font-semibold text-emerald-400' : 'font-semibold text-sky-400'">{{ bcRecentBroadcastKindLabel(bcRecentStatsBroadcastMeta) }}</span
                ><span> · {{ bcRecentWhenLabel(bcRecentStatsBroadcastMeta) }}</span>
              </p>
            </div>
            <button type="button" class="shrink-0 rounded-lg px-2 py-1 text-sm text-zinc-300 hover:bg-white/10" @click="bcCloseRecentBroadcastStats">✕</button>
          </div>
          <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-3">
            <p v-if="bcRecentStatsLoading" class="py-8 text-center text-sm text-zinc-400">{{ tt('admin.broadcast_shell.stats_loading') }}</p>
            <template v-else-if="bcRecentStatsSnapshot">
              <p
                v-if="bcRecentStatsSnapshot.broadcast_url_tracking_configured === false"
                class="mb-2 rounded-lg border border-amber-500/25 bg-amber-500/8 px-2.5 py-1.5 text-[10px] leading-snug text-amber-100/90"
              >
                {{ tt('admin.broadcast_shell.tracking_off_hint') }}
              </p>
              <p
                v-else
                class="mb-2 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-[10px] leading-snug text-slate-400"
              >
                {{ tt('admin.broadcast_shell.tracking_on_hint') }}
              </p>
              <div class="grid grid-cols-2 gap-2">
                <div class="rounded-xl border border-white/10 bg-[#11151C] p-2.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
                  <p class="text-[10px] text-slate-500">{{ tt('admin.bc_campaign.metric_delivered_posts') }}</p>
                  <p class="text-lg font-bold tabular-nums text-white">{{ fmtIntSpace(bcRecentStatDeliveredOk) }}</p>
                  <div class="mt-2 space-y-1.5 border-t border-white/[0.08] pt-2">
                    <div class="flex items-center justify-between gap-2 text-[11px]">
                      <span class="text-slate-500">{{ tt('admin.bc_campaign.metric_reactions') }}</span>
                      <span class="font-semibold tabular-nums text-white">{{ fmtIntSpace(bcRecentStatReactions) }}</span>
                    </div>
                    <div class="flex items-center justify-between gap-2 text-[11px]">
                      <span class="text-slate-500">{{ tt('admin.bc_campaign.metric_link_clicks') }}</span>
                      <span class="font-semibold tabular-nums text-white">{{ fmtIntSpace(Number(bcRecentStatsSnapshot.real_link_clicks_total || 0)) }}</span>
                    </div>
                    <div class="flex items-center justify-between gap-2 text-[11px]">
                      <span class="text-slate-500">{{ tt('admin.bc_campaign.metric_button_clicks') }}</span>
                      <span class="font-semibold tabular-nums text-white">{{ fmtIntSpace(Number(bcRecentStatsSnapshot.real_callback_clicks_total || 0)) }}</span>
                    </div>
                  </div>
                </div>
                <div class="rounded-xl border border-white/10 bg-[#11151C] p-2.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
                  <p class="text-[10px] text-slate-500">
                    <abbr :title="tt('admin.broadcast_shell.ctr_hint_title')" class="cursor-help underline decoration-dotted decoration-slate-500 underline-offset-2">{{
                      tt('admin.broadcast_shell.ctr_abbr')
                    }}</abbr>
                  </p>
                  <p class="text-lg font-bold tabular-nums text-emerald-300">{{ fmtPctTrim(bcRecentStatCtrPct) }}</p>
                  <p class="mt-0.5 text-[10px] leading-tight text-slate-500">{{ bcRecentStatCtrSub }}</p>
                </div>
              </div>
              <div v-if="(bcRecentStatsSnapshot.per_groups || []).length" class="mt-2">
                <p class="mb-1.5 text-[11px] font-semibold text-slate-400">{{ tt('admin.broadcast_shell.delivered_by_chat_title') }}</p>
                <div class="rounded-xl border border-white/10 bg-[#11151C] px-2.5 py-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
                  <div
                    v-for="(row, idx) in bcRecentStatsSnapshot.per_groups"
                    :key="`bc-recent-pg-${idx}-${row.chat_id}`"
                    class="flex items-center justify-between gap-2 border-b border-white/[0.06] py-2 last:border-b-0"
                  >
                    <p class="min-w-0 flex-1 truncate text-[12px] text-zinc-200">{{ row.title || row.chat_id }}</p>
                    <span class="shrink-0 text-[12px] font-semibold tabular-nums text-emerald-200">{{ fmtIntSpace(row.ok) }}</span>
                  </div>
                </div>
              </div>
              <div v-if="(bcRecentStatsSnapshot.send_history || []).length" class="mt-3">
                <p class="mb-1.5 text-[11px] font-semibold text-slate-400">{{ tt('admin.broadcast_shell.send_history_title') }}</p>
                <div class="max-h-52 space-y-2 overflow-y-auto overscroll-contain rounded-xl border border-white/10 bg-[#11151C] px-2.5 py-2">
                  <div
                    v-for="(h, hi) in bcRecentStatsSnapshot.send_history"
                    :key="`bc-recent-hist-${hi}-${h.batch_id ?? hi}`"
                    class="border-b border-white/[0.06] pb-2 last:border-b-0 last:pb-0"
                  >
                    <p class="text-[11px] font-semibold text-zinc-200">
                      {{ fmtBroadcastShortTime(h.started_at || h.ended_at) || '—' }}
                    </p>
                    <ul v-if="(h.groups || []).length" class="mt-1 space-y-0.5 pl-3 text-[11px] leading-snug text-slate-400">
                      <li v-for="(g, gi) in h.groups" :key="`bc-rhg-${hi}-${g.chat_id}-${gi}`">
                        <span class="text-zinc-300">{{ g.title || g.chat_id }}</span>
                        <span v-if="Number(g.ok) > 0" class="text-emerald-400/90"> · ✓ {{ g.ok }}</span>
                        <span v-if="Number(g.fail) > 0" class="text-rose-300/90"> · ✕ {{ g.fail }}</span>
                      </li>
                    </ul>
                    <p v-else-if="Number(h.bots?.total) > 0" class="mt-1 text-[10px] text-slate-400">
                      {{ tt('admin.broadcast_shell.send_history_bots', { ok: Number(h.bots?.ok || 0), n: Number(h.bots?.total || 0) }) }}
                    </p>
                    <p v-else class="mt-1 text-[10px] text-slate-400">
                      {{
                        tt('admin.broadcast_shell.send_history_summary', {
                          ok: Number(h.recipient_ok || 0),
                          fail: Number(h.recipient_fail || 0),
                        })
                      }}
                    </p>
                    <p v-if="bcRecentSendHistoryHasSuccess(h) && bcFormatPerSendEngagementLine(h.per_send_engagement)" class="mt-1.5 text-[10px] leading-snug text-slate-400">
                      {{ bcFormatPerSendEngagementLine(h.per_send_engagement) }}
                    </p>
                  </div>
                </div>
              </div>
            </template>
            <p v-else class="py-8 text-center text-sm text-rose-300/90">{{ tt('admin.broadcast_shell.stats_load_failed') }}</p>
          </div>
          <div class="shrink-0 border-t border-white/10 px-4 py-3 pb-[max(0.75rem,calc(0.35rem+env(safe-area-inset-bottom,0px)))]">
            <div class="flex gap-2">
              <button
                type="button"
                class="flex-1 rounded-xl border border-white/12 bg-white/[0.06] py-3 text-[14px] font-semibold text-zinc-100 shadow-sm hover:bg-white/[0.1] disabled:cursor-not-allowed disabled:opacity-50"
                :disabled="bcRecentStatsLoading"
                @click="bcRecentStatsGoToBroadcastsTab"
              >
                {{ tt('admin.broadcast_shell.btn_to_broadcasts_tab') }}
              </button>
              <button
                type="button"
                class="flex-1 rounded-xl bg-gradient-to-r from-violet-600 to-sky-500 py-3 text-[14px] font-bold text-white shadow-lg shadow-indigo-900/30 hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
                :disabled="bcRecentStatsLoading || !bcRecentStatsBroadcastId"
                @click="bcRecentStatsRepeatBroadcast"
              >
                {{ tt('admin.broadcast_shell.btn_repeat_broadcast') }}
              </button>
            </div>
          </div>
        </div>
      </div>
      </GuardTeleport>

      <div
        v-if="false && cabinetMode === 'delegated'"
        class="rounded-lg bg-zinc-950/45 px-2.5 py-1.5 text-[11px] text-zinc-300 ring-1 ring-white/[0.05] backdrop-blur-md"
      >
        {{ tt('admin.broadcast_ui.delegated_strip') }}
      </div>

      <div
        v-if="false && bcBroadcastCanScopeAll && showFullAdminShell"
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

      <div v-if="false" class="flex flex-wrap gap-1.5">
        <button
          type="button"
          class="rounded-xl border border-white/[0.1] bg-zinc-800/90 px-3 py-1.5 text-xs font-semibold text-zinc-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] ring-1 ring-white/[0.05] backdrop-blur-md transition hover:bg-zinc-700/90"
          @click="() => createBcDraft('oneshot')"
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

      <div v-if="false && bcLoading" class="text-sm text-slate-400">Загрузка…</div>

      <div v-if="false" class="grid min-w-0 gap-2.5 lg:grid-cols-[minmax(0,200px)_minmax(0,1fr)]">
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
              <button type="button" class="bc-tool-btn bc-broadcast-i" :title="tt('admin.broadcast_ui.format_help_tooltip')" :aria-label="tt('admin.broadcast_ui.format_help_aria')" @click="bcShowFormatHelp = true">
                i
              </button>
              <div class="flex flex-wrap gap-1">
                <button type="button" class="bc-tool-btn" :class="bcFormatState.bold ? 'bc-tool-active' : ''" title="Жирный" @mousedown.prevent @click="bcFormatBold"><b>Ж</b></button>
                <button type="button" class="bc-tool-btn" :class="bcFormatState.italic ? 'bc-tool-active' : ''" title="Курсив" @mousedown.prevent @click="bcFormatItalic"><i>К</i></button>
                <button type="button" class="bc-tool-btn" :class="bcFormatState.underline ? 'bc-tool-active' : ''" title="Подчёркивание" @mousedown.prevent @click="bcFormatUnderline"><u>Ч</u></button>
                <button type="button" class="bc-tool-btn" :class="bcFormatState.strike ? 'bc-tool-active' : ''" title="Зачёркнутый" @mousedown.prevent @click="bcFormatStrike"><s>З</s></button>
                <button type="button" class="bc-tool-btn text-[11px]" :class="bcFormatState.spoiler ? 'bc-tool-active' : ''" title="Скрытый" @mousedown.prevent @click="bcFormatSpoiler">🙈 Скрытый</button>
                <button type="button" class="bc-tool-btn text-[11px]" title="Моноширинный блок" @mousedown.prevent @click="bcFormatPre">⌨ PRE</button>
                <button type="button" class="bc-tool-btn text-[11px]" :class="bcFormatState.link ? 'bc-tool-active' : ''" title="Ссылка" @mousedown.prevent @click="bcFormatLink">🔗 Ссылка</button>
                <button type="button" class="bc-tool-btn text-[11px]" :class="bcFormatState.quote ? 'bc-tool-active' : ''" title="Цитата" @mousedown.prevent @click="bcFormatBlockquote">❝ Цитата</button>
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
                  :title="tt('admin.broadcast_ui.open_large')"
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
              {{ tt('admin.broadcast_ui.chars_count', { current: bcCurrentLen(), max: bcCurrentMaxLen() }) }}
            </p>
            <div
              ref="bcBodyRef"
              class="bc-editor mt-1.5 h-48 min-h-[12rem] shrink-0 overflow-y-auto rounded-xl border border-white/[0.1] bg-zinc-950 px-3 py-2.5 text-sm leading-relaxed focus-within:border-cyan-500/45 focus-within:ring-1 focus-within:ring-cyan-500/25"
              contenteditable="true"
              :data-placeholder="tt('admin.broadcast_ui.message_body_ph')"
              @input="onBcEditorInput"
              @paste="bcOnEditorPaste"
              @keydown="bcOnEditorKeydown"
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
                <span class="text-[10px] font-semibold uppercase tracking-wide text-zinc-300">{{ tt('admin.autopost.campaigns_sidebar_title') }}</span>
                <button
                  type="button"
                  class="bc-tool-btn bc-broadcast-i shrink-0"
                  :title="tt('admin.autopost.help_tooltip')"
                  :aria-label="tt('admin.autopost.help_aria')"
                  @click="bcShowAutopostHelp = true"
                >
                  i
                </button>
              </div>
              <button
                type="button"
                class="rounded-md border border-cyan-500/40 bg-cyan-950/40 px-2 py-1 text-[10px] font-semibold text-cyan-100"
                @click="openBcCampaignUxWizard"
              >
                {{ tt('admin.autopost.btn_new_campaign_short') }}
              </button>
            </div>
            <p class="mt-1 text-[10px] leading-snug text-slate-400">
              {{ tt('admin.autopost.campaigns_sidebar_hint') }}
            </p>
            <div v-if="bcAutopostCampaigns.length" class="mt-2 space-y-2">
              <div
                v-for="camp in bcAutopostCampaigns"
                :key="`apc-${camp.id}`"
                class="flex flex-col gap-1.5 rounded-lg border border-white/10 bg-black/25 px-2 py-1.5"
                role="button"
                tabindex="0"
                @click="openBcCampaignUxManage(camp)"
                @keydown.enter.prevent="openBcCampaignUxManage(camp)"
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

    <GuardTeleport guard-to="body">
      <div
        v-if="bcCampaignUxOpen"
        class="fixed inset-0 z-[100200] flex h-[100dvh] min-w-0 flex-col overflow-hidden bg-[#0b0d14] pt-[env(safe-area-inset-top,0px)] pb-[env(safe-area-inset-bottom,0px)] text-white"
      >
        <div class="flex items-center justify-between border-b border-white/10 bg-[#12141c] px-4 py-3">
          <button type="button" class="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-white/[0.03] text-white/90 transition hover:bg-white/[0.08] active:scale-[0.98]" @click="bcCampaignUxBack">←</button>
          <div class="min-w-0 text-center">
            <p class="truncate text-[19px] font-extrabold tracking-tight">{{ bcCampaignUxScreen === 'list' ? tt('admin.bc_campaign.title_list') : bcCampaignUxScreen === 'manage' ? (bcCampaignUxManageItem?.title || tt('admin.bc_campaign.title_manage')) : bcCampaignUxScreen === 'stats' ? tt('admin.bc_campaign.title_stats') : tt('admin.bc_campaign.title_new') }}</p>
            <p v-if="bcCampaignUxScreen === 'wizard'" class="text-[11px] font-medium text-slate-400">{{ tt('admin.bc_campaign.wizard_step', { n: bcCampaignUxStep, max: 5 }) }}</p>
          </div>
          <button type="button" class="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-white/[0.03] text-white/90 transition hover:bg-white/[0.08] active:scale-[0.98]" @click="bcCampaignUxCloseScheduleModal(); bcCampaignUxRecipientsModalOpen = false; if (bcCampaignUxCampaignPostsModalOpen) bcCampaignUxCloseCampaignPostsModal(); bcCampaignUxOpen = false">✕</button>
        </div>

        <div v-if="bcCampaignUxScreen === 'list'" class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 pb-[max(5.5rem,calc(5.75rem+env(safe-area-inset-bottom,0px)))]">
          <p class="text-[13px] text-slate-300">{{ tt('admin.bc_campaign.list_intro') }}</p>
          <button type="button" class="mt-3 w-full rounded-2xl border border-emerald-400/40 bg-gradient-to-r from-[#27b35f] to-[#36D67A] px-4 py-3 text-[15px] font-extrabold text-[#04130a] shadow-[0_18px_34px_-18px_rgba(54,214,122,0.75)] transition hover:brightness-110 active:scale-[0.995]" @click="openBcCampaignUxWizard">{{ tt('admin.bc_campaign.btn_new') }}</button>
          <div class="mt-4 space-y-2.5">
            <div
              v-for="camp in bcAutopostCampaigns"
              :key="`ux-camp-${camp.id}`"
              role="button"
              tabindex="0"
              class="w-full cursor-pointer rounded-2xl border border-white/10 bg-[#11151C] px-3 py-3 text-left shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_16px_30px_-24px_rgba(15,23,42,0.9)] transition hover:border-indigo-300/35 hover:bg-[#151A22]"
              @click="openBcCampaignUxManage(camp)"
              @keydown.enter.prevent="openBcCampaignUxManage(camp)"
              @keydown.space.prevent="openBcCampaignUxManage(camp)"
            >
              <div class="flex items-center justify-between gap-2">
                <p class="truncate text-[16px] font-bold">{{ camp.title || tt('admin.bc_campaign.campaign_named', { id: camp.id }) }}</p>
                <span class="rounded-md px-2 py-0.5 text-[11px]" :class="bcCampaignUxStatusBadgeClass(camp)">{{ bcCampaignUxStatusLabel(camp) }}</span>
              </div>
              <div class="mt-2 grid grid-cols-2 gap-1 text-[11px] text-slate-300">
                <span>{{ tt('admin.bc_campaign.row_recipients_label') }}: {{ Number((camp?.autopost?.group_chat_ids || []).length || 0) + Number((camp?.autopost?.channel_chat_ids || []).length || 0) }}</span>
                <span>{{ tt('admin.bc_campaign.row_posts_label') }}: {{ bcCampaignUxPostsCountLabelForCamp(camp) }}</span>
                <span>{{ tt('admin.bc_campaign.row_today_label') }}: {{ bcCampaignUxTodaySent(camp) }}</span>
                <span>CTR: {{ fmtPctTrim(bcCampaignUxListCtrPct(camp)) }}</span>
              </div>
              <div v-if="bcCampaignUxDestinationsIsEmpty(camp)" class="mt-1.5 rounded-lg border border-indigo-500/20 bg-indigo-500/8 px-2 py-2">
                <p class="text-[10px] leading-snug text-slate-400">{{ tt('admin.bc_campaign.destinations_empty_hint') }}</p>
              </div>
              <p v-else class="mt-1.5 line-clamp-2 text-[10px] leading-snug text-slate-500">{{ bcCampaignUxDestinationsPreviewLines(camp) }}</p>
            </div>
            <div v-if="!bcAutopostCampaigns.length" class="rounded-2xl border border-dashed border-white/15 bg-[#11151C]/85 px-3 py-5 text-center">
              <p class="text-[14px] font-semibold text-slate-200">{{ tt('admin.bc_campaign.empty_title') }}</p>
              <p class="mt-1 text-[12px] text-slate-400">{{ tt('admin.bc_campaign.empty_sub') }}</p>
            </div>
          </div>
        </div>

        <div v-else-if="bcCampaignUxScreen === 'wizard'" class="flex min-h-0 flex-1 flex-col">
          <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4">
          <template v-if="bcCampaignUxStep === 1">
            <p class="text-[12px] text-slate-400">{{ tt('admin.bc_campaign.step_n_of_5', { n: 1 }) }}</p>
            <label class="mt-2 block text-[12px] font-semibold text-slate-300">{{ tt('admin.bc_campaign.name_label') }}</label>
            <input
              ref="bcCampaignUxWizardTitleInputRef"
              v-model="bcCampaignUxWizard.title"
              type="text"
              maxlength="255"
              class="mt-1 w-full rounded-2xl border border-white/10 bg-[#11151C] px-3 py-2.5 text-sm text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] focus:border-indigo-400/45 focus:outline-none focus:ring-1 focus:ring-indigo-400/30"
              :placeholder="tt('admin.bc_campaign.name_ph')"
            />
            <p class="mt-3 text-[12px] font-semibold text-slate-300">{{ tt('admin.bc_campaign.posts_heading') }}</p>
            <button
              type="button"
              class="mt-2 w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-semibold transition hover:bg-white/[0.08]"
              @click="bcCampaignUxOpenPostEditor(0)"
            >
              {{ tt('admin.bc_campaign.btn_create_post') }}
            </button>
            <div class="mt-2">
              <button
                type="button"
                class="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-semibold transition hover:bg-white/[0.08] disabled:cursor-not-allowed disabled:opacity-45"
                :disabled="!bcCampaignUxHasDraftPostsSelected"
                @click="bcCampaignUxClearDraftPostSelection"
              >
                {{ tt('admin.bc_campaign.btn_clear_post_selection') }}
              </button>
            </div>
            <button
              type="button"
              class="mt-2 w-full rounded-xl border border-rose-500/35 bg-rose-950/40 px-3 py-2 text-xs font-semibold text-rose-100 transition hover:bg-rose-950/55 disabled:cursor-not-allowed disabled:opacity-45"
              :disabled="!bcDraftBroadcastsForAutopost.length"
              @click="bcCampaignUxDeleteAllDraftPosts"
            >
              {{ tt('admin.bc_campaign.btn_delete_all_post_drafts') }}
            </button>
            <div ref="bcCampaignUxWizardPostsListRef" class="mt-2 max-h-56 space-y-1 overflow-y-auto rounded-2xl border border-white/10 bg-[#11151C] p-2">
              <div
                v-for="b in bcDraftBroadcastsForAutopost"
                :key="`wiz-post-${b.id}`"
                class="flex items-center gap-2 rounded-lg px-2 py-1.5 text-[12px] transition hover:bg-white/[0.06]"
              >
                <input
                  class="shrink-0 rounded border-white/30"
                  type="checkbox"
                  :checked="bcCampaignUxWizard.postIds.includes(Number(b.id))"
                  @change="bcCampaignUxTogglePost(b.id)"
                />
                <div class="flex min-w-0 flex-1 items-center gap-2 overflow-hidden">
                  <span class="shrink-0 whitespace-nowrap text-[13px] leading-none" :title="tt('admin.bc_campaign.post_type_hint')">{{ bcCampaignUxPostMeta(b) }}</span>
                  <span class="min-w-0 truncate">{{ b.title || tt('admin.bc_campaign.post_named', { id: b.id }) }}</span>
                </div>
                <button
                  type="button"
                  class="shrink-0 rounded-md border border-white/10 bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-slate-200"
                  :title="tt('admin.bc_campaign.edit_post_draft')"
                  @click.stop="bcCampaignUxOpenPostEditor(b.id)"
                >
                  ✎
                </button>
                <button
                  type="button"
                  class="shrink-0 rounded-md border border-rose-500/35 bg-rose-900/35 px-2 py-0.5 text-[11px] font-semibold text-rose-100"
                  :title="tt('admin.bc_campaign.delete_one_post_draft')"
                  @click.stop="deleteBcDraftItem(b)"
                >
                  ✕
                </button>
              </div>
            </div>
            <p class="mt-2 text-[11px] text-slate-500">{{ tt('admin.bc_campaign.posts_tip') }}</p>
          </template>

          <template v-else-if="bcCampaignUxStep === 2">
            <p class="text-[12px] text-slate-400">{{ tt('admin.bc_campaign.step_n_of_5', { n: 2 }) }}</p>
            <p class="mt-2 text-[16px] font-bold">{{ tt('admin.bc_campaign.type_heading') }}</p>
            <div class="mt-3 rounded-2xl border border-violet-400/35 bg-violet-500/10 px-3 py-3 text-[13px] leading-relaxed text-slate-200">
              <p class="font-semibold text-violet-100">{{ tt('admin.bc_campaign.type_simple') }}</p>
              <p class="mt-1 text-[12px] text-slate-400">{{ tt('admin.bc_campaign.type_simple_sub') }}</p>
            </div>
          </template>

          <template v-else-if="bcCampaignUxStep === 3">
            <p class="text-[12px] text-slate-400">{{ tt('admin.bc_campaign.step_n_of_5', { n: 3 }) }}</p>
            <p class="mt-2 text-[16px] font-bold">{{ tt('admin.bc_campaign.schedule_heading') }}</p>
            <div class="mt-3 space-y-2 rounded-2xl border border-white/10 bg-[#11151C] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
              <label class="text-[12px] text-slate-300">{{ tt('admin.bc_campaign.period_start_label') }}</label>
              <div class="flex flex-wrap items-center gap-2">
                <input v-model="bcCampaignUxWizard.startDate" type="date" class="min-w-[10rem] flex-1 rounded-xl border border-white/10 bg-black/30 px-2 py-2 text-sm focus:border-indigo-400/45 focus:outline-none" />
                <button type="button" class="shrink-0 rounded-xl border border-violet-400/40 bg-violet-600/25 px-3 py-2 text-[11px] font-semibold text-violet-100 transition hover:bg-violet-600/35" @click="bcCampaignUxSetStartDateTodayFromTz">{{ tt('admin.bc_campaign.btn_today_tz') }}</button>
              </div>
              <label class="pt-1 text-[12px] text-slate-300">{{ tt('admin.bc_campaign.period_end_label') }}</label>
              <input v-model="bcCampaignUxWizard.endDate" type="date" class="w-full rounded-xl border border-white/10 bg-black/30 px-2 py-2 text-sm focus:border-indigo-400/45 focus:outline-none" />
              <p class="text-[10px] text-slate-500">{{ tt('admin.bc_campaign.period_end_hint') }}</p>
              <label class="text-[12px] text-slate-300">{{ tt('admin.bc_campaign.freq_label') }}</label>
              <select v-model="bcCampaignUxWizard.scheduleMode" class="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-2 py-2 text-sm focus:border-indigo-400/45 focus:outline-none">
                <option value="every_day">{{ tt('admin.bc_campaign.freq_every_day') }}</option>
                <option value="weekdays">{{ tt('admin.bc_campaign.freq_weekdays') }}</option>
              </select>
              <div v-if="bcCampaignUxWizard.scheduleMode === 'weekdays'" class="flex flex-wrap gap-1.5 pt-1">
                <button v-for="d in BC_WEEKDAY_OPTS" :key="`wiz-wd-${d.v}`" type="button" class="rounded-lg border px-2 py-1 text-[11px] transition" :class="bcCampaignUxWizard.weekdays.includes(d.v) ? 'border-violet-400 bg-violet-500/20 text-violet-100' : 'border-white/15 bg-black/20 hover:bg-white/[0.06]'" @click="bcCampaignUxToggleWeekday(d.v)">{{ d.label }}</button>
              </div>
              <label class="mt-2 text-[12px] text-slate-300">{{ tt('admin.bc_campaign.multi_send_windows_heading') }}</label>
              <p class="text-[10px] leading-snug text-slate-500">{{ tt('admin.bc_campaign.multi_send_windows_help') }}</p>
              <div v-for="(seg, si) in bcCampaignUxWizard.sendWindows" :key="`wiz-sw-${si}`" class="mt-2 space-y-2 rounded-xl border border-white/[0.08] bg-black/25 p-2.5">
                <div class="flex items-center justify-between gap-2">
                  <span class="text-[11px] font-semibold text-slate-400">{{ tt('admin.bc_campaign.slot_n', { n: si + 1 }) }}</span>
                  <div class="flex shrink-0 gap-1">
                    <button
                      type="button"
                      class="rounded-lg border border-emerald-500/35 px-2 py-0.5 text-[12px] font-bold text-emerald-200 disabled:cursor-not-allowed disabled:opacity-40"
                      :disabled="(bcCampaignUxWizard.sendWindows || []).length >= 24"
                      @click="bcCampaignUxWizardAddScheduleSegment"
                    >
                      +
                    </button>
                    <button
                      type="button"
                      class="rounded-lg border border-rose-500/35 px-2 py-0.5 text-[12px] font-bold text-rose-100 disabled:cursor-not-allowed disabled:opacity-40"
                      :disabled="(bcCampaignUxWizard.sendWindows || []).length <= 1"
                      @click="bcCampaignUxWizardRemoveScheduleSegment(si)"
                    >
                      −
                    </button>
                  </div>
                </div>
                <div class="grid grid-cols-2 gap-2">
                  <div>
                    <p class="text-[10px] text-slate-500">{{ tt('admin.bc_campaign.slot_from') }}</p>
                    <input v-model="seg.windowStart" type="time" class="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-2 py-2 text-sm focus:border-indigo-400/45 focus:outline-none" />
                  </div>
                  <div>
                    <p class="text-[10px] text-slate-500">{{ tt('admin.bc_campaign.slot_to') }}</p>
                    <input v-model="seg.windowEnd" type="time" class="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-2 py-2 text-sm focus:border-indigo-400/45 focus:outline-none" />
                  </div>
                </div>
                <div>
                  <p class="text-[10px] text-slate-500">{{ tt('admin.bc_campaign.posts_in_slot') }}</p>
                  <input
                    v-model.number="seg.posts"
                    type="number"
                    min="1"
                    max="288"
                    class="hide-num-spin mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-2 py-2 text-sm focus:border-indigo-400/45 focus:outline-none"
                    @blur="bcCampaignUxWizardSegmentPostsEdited()"
                  />
                </div>
                <div
                  v-if="(bcCampaignUxWizardSlotTimePreview[si] || []).length"
                  class="rounded-lg border border-white/[0.06] bg-black/20 px-2 py-2"
                >
                  <p class="text-[10px] font-semibold text-slate-500">{{ tt('admin.bc_campaign.schedule_slot_times_preview') }}</p>
                  <p class="mt-1 break-words font-mono text-[11px] leading-relaxed">
                    <template v-for="(ent, ti) in (bcCampaignUxWizardSlotEntries[si] || [])" :key="`wiz-st-${si}-${ti}`">
                      <span v-if="ti > 0" class="text-slate-500"> · </span>
                      <span
                        :class="bcCampaignUxScheduleSlotStatusClass(ent.status)"
                        :title="bcCampaignUxScheduleSlotStatusTitle(ent.status)"
                      >{{ ent.label }}</span>
                    </template>
                  </p>
                  <p
                    v-if="bcCampaignUxShouldMarkPastSlotsSkipped(bcCampaignUxWizard.startDate || bcCampaignUxTodayIsoInTimezone(bcCampaignUxWizard.timezone), bcCampaignUxWizard.timezone)"
                    class="mt-1.5 text-[10px] leading-snug text-slate-500"
                  >
                    {{ tt('admin.bc_campaign.schedule_past_slots_hint') }}
                  </p>
                  <p class="mt-2 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-slate-500">
                    <span><span class="text-slate-200" aria-hidden="true">●</span> {{ tt('admin.bc_campaign.schedule_slot_pending') }}</span>
                    <span><span class="text-rose-400" aria-hidden="true">●</span> {{ tt('admin.bc_campaign.schedule_slot_skipped') }}</span>
                  </p>
                  <p class="mt-2 text-[10px] leading-snug text-slate-500">{{ tt('admin.bc_campaign.schedule_timing_precision') }}</p>
                </div>
              </div>
              <p v-if="(bcCampaignUxWizard.sendWindows || []).length >= 2" class="mt-2 text-[11px] font-medium text-slate-400">
                {{ tt('admin.bc_campaign.slots_daily_total') }}: {{ bcCampaignUxWizardPostsPerDayTotal }}
              </p>
              <label class="text-[12px] text-slate-300">{{ tt('admin.bc_campaign.timezone') }}</label>
              <input v-model="bcCampaignUxWizard.timezone" type="text" class="w-full rounded-xl border border-white/10 bg-black/30 px-2 py-2 text-sm focus:border-indigo-400/45 focus:outline-none" />
              <label class="flex items-center gap-2 text-[12px] text-slate-300"><input v-model="bcCampaignUxWizard.spreadInWindow" type="checkbox" /> {{ tt('admin.bc_campaign.spread_even') }}</label>
            </div>
          </template>

          <template v-else-if="bcCampaignUxStep === 4">
            <p class="text-[12px] text-slate-400">{{ tt('admin.bc_campaign.step_n_of_5', { n: 4 }) }}</p>
            <p class="mt-2 text-[16px] font-bold">{{ tt('admin.bc_campaign.where_heading') }}</p>
            <div class="mt-3 space-y-2">
              <label class="flex cursor-pointer items-center justify-between rounded-2xl border border-white/10 bg-[#11151C] px-3 py-3 text-sm transition hover:bg-[#151A22]"><span>{{ tt('admin.bc_campaign.target_channels') }}</span><input :checked="bcCampaignUxWizard.targetChannels" type="checkbox" @change="bcCampaignUxToggleWizardTargetChannels" /></label>
              <label class="flex cursor-pointer items-center justify-between rounded-2xl border border-white/10 bg-[#11151C] px-3 py-3 text-sm transition hover:bg-[#151A22]"><span>{{ tt('admin.bc_campaign.target_groups') }}</span><input :checked="bcCampaignUxWizard.targetGroups" type="checkbox" @change="bcCampaignUxToggleWizardTargetGroups" /></label>
              <label
                v-if="showFullAdminShell && !isBroadcastShellLite"
                class="flex items-center justify-between rounded-2xl border border-white/10 bg-[#11151C] px-3 py-3 text-sm transition hover:bg-[#151A22]"
                ><span>{{ tt('admin.bc_campaign.target_bots') }}</span><input v-model="bcCampaignUxWizard.targetBots" type="checkbox"
              /></label>
            </div>
            <div class="mt-3 rounded-2xl border border-white/10 bg-[#11151C] px-3 py-2 text-[12px] text-slate-300">
              <p>{{ tt('admin.bc_campaign.selected_heading') }}</p>
              <p class="mt-1">{{ tt('admin.bc_campaign.selected_counts', { ch: bcCampaignUxSelectedSummary.channels, gr: bcCampaignUxSelectedSummary.groups }) }}</p>
            </div>
            <div class="mt-2 flex gap-2">
              <button type="button" class="flex-1 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-semibold transition hover:bg-white/[0.08]" @click="bcCampaignUxOpenRecipientPicker('channels')">{{ tt('admin.bc_campaign.pick_channels') }}</button>
              <button type="button" class="flex-1 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-semibold transition hover:bg-white/[0.08]" @click="bcCampaignUxOpenRecipientPicker('groups')">{{ tt('admin.bc_campaign.pick_groups') }}</button>
            </div>
          </template>

          </div>
          <div class="shrink-0 border-t border-white/10 bg-[#05070B] px-4 pt-3 pb-[max(0.75rem,calc(0.5rem+env(safe-area-inset-bottom,0px)))]">
            <button
              type="button"
              class="w-full rounded-2xl border border-indigo-400/45 bg-gradient-to-r from-[#6d3ef7] via-[#4f46e5] to-[#355dff] px-4 py-3 text-[14px] font-bold shadow-[0_18px_36px_-18px_rgba(79,70,229,0.95)] transition hover:brightness-110"
              :class="!bcCampaignUxWizardCanNext ? 'cursor-not-allowed opacity-45' : ''"
              @click="bcCampaignUxNextStepAttempt"
            >
              {{ tt('admin.bc_campaign.btn_next') }}
            </button>
          </div>
        </div>

        <div v-else-if="bcCampaignUxScreen === 'review'" class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 pb-[max(5.5rem,calc(5.75rem+env(safe-area-inset-bottom,0px)))]">
          <p class="text-[12px] text-slate-400">{{ tt('admin.bc_campaign.step_n_of_5', { n: 5 }) }}</p>
          <p class="mt-2 text-[18px] font-extrabold">{{ tt('admin.bc_campaign.review_heading') }}</p>
          <div class="mt-3 space-y-2 rounded-2xl border border-white/10 bg-[#11151C] p-3 text-[13px] text-slate-200 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
            <p>{{ tt('admin.bc_campaign.rv_name') }}: <b>{{ bcCampaignUxWizard.title }}</b></p>
            <p>{{ tt('admin.bc_campaign.rv_type') }}: <b>{{ bcCampaignUxWizard.campaignType === 'progress' ? tt('admin.bc_campaign.type_progress') : bcCampaignUxWizard.campaignType === 'rotation' ? tt('admin.bc_campaign.type_rotation') : tt('admin.bc_campaign.type_simple') }}</b></p>
            <p>{{ tt('admin.bc_campaign.rv_daily_window') }}: <b>{{ bcCampaignUxWizardReviewTimingPreview }} · {{ bcCampaignUxWizard.timezone }}</b></p>
            <p>
              {{ tt('admin.bc_campaign.rv_dates') }}:
              <b
                ><template v-if="bcCampaignUxWizard.startDate">{{ bcCampaignUxWizard.startDate }}</template
                ><template v-else>{{ tt('admin.bc_campaign.from_immediately') }}</template>
                —
                <template v-if="bcCampaignUxWizard.endDate">{{ bcCampaignUxWizard.endDate }}</template>
                <template v-else>{{ tt('admin.bc_campaign.open_end_inline') }}</template></b
              >
            </p>
            <p>{{ tt('admin.bc_campaign.rv_recipients') }}: <b>{{ tt('admin.bc_campaign.selected_counts', { ch: bcCampaignUxSelectedSummary.channels, gr: bcCampaignUxSelectedSummary.groups }) }}</b></p>
            <p>{{ tt('admin.bc_campaign.rv_posts_count') }}: <b>{{ bcCampaignUxWizard.postIds.length }}</b></p>
            <p>{{ tt('admin.bc_campaign.rv_slot_cost') }}: <b class="text-amber-300">{{ bcCampaignUxSlotAurumCharge }} AURUM</b></p>
            <p>
              {{ tt('admin.bc_campaign.rv_period_sends') }}: <b>{{ fmtIntSpace(bcCampaignUxPeriodScheduledSends) }}</b>
              <span v-if="bcCampaignUxPeriodSendingOpenEnded" class="text-slate-500"> {{ tt('admin.bc_campaign.open_end_notice_short') }}</span>
            </p>
            <p>{{ tt('admin.bc_campaign.rv_period_aurum') }}: <b class="text-amber-300">{{ fmtIntSpace(bcCampaignUxPeriodAurumEstimate) }} AURUM</b></p>
            <p class="text-[11px] text-slate-500">{{ tt('admin.bc_campaign.debit_per_send_note') }}</p>
            <p>{{ tt('admin.bc_campaign.rv_balance') }}: <b class="text-amber-200">{{ fmtBcTokens(meAdminProfile?.aurum_tokens || 0) }}</b></p>
          </div>
          <p class="mt-3 text-[12px] text-slate-400">{{ tt('admin.bc_campaign.after_launch_note') }}</p>
          <div class="mt-4 flex gap-2">
            <button type="button" class="flex-1 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm font-semibold transition hover:bg-white/[0.08]" @click="bcCampaignUxBack">{{ tt('admin.bc_campaign.back') }}</button>
            <button type="button" class="flex-1 rounded-xl border border-emerald-400/45 bg-gradient-to-r from-[#27b35f] to-[#36D67A] px-3 py-2 text-sm font-bold text-[#04130a] shadow-[0_18px_34px_-18px_rgba(54,214,122,0.95)] disabled:cursor-not-allowed disabled:opacity-50" :disabled="bcCampaignUxBusy" @click="bcCampaignUxCreateCampaign">{{ bcCampaignUxBusy ? (bcCampaignUxEditingCampaignId ? tt('admin.bc_campaign.saving') : tt('admin.bc_campaign.creating')) : (bcCampaignUxEditingCampaignId ? tt('admin.bc_campaign.save_changes') : tt('admin.bc_campaign.create_action')) }}</button>
          </div>
        </div>

        <div v-else-if="bcCampaignUxScreen === 'success'" class="flex min-h-0 flex-1 flex-col items-center justify-center px-4 py-6 text-center">
          <div class="flex h-28 w-28 items-center justify-center rounded-full border border-emerald-300/45 bg-emerald-500/20 text-5xl text-emerald-300 shadow-[0_0_64px_-12px_rgba(54,214,122,0.7),inset_0_0_20px_rgba(255,255,255,0.12)]">✓</div>
          <p class="mt-4 text-[26px] font-extrabold">{{ tt('admin.bc_campaign.success_title') }}</p>
          <p v-if="bcCampaignUxSuccessInfo.needsStart" class="mt-1 text-[13px] text-amber-100/95">{{ tt('admin.bc_campaign.success_sub_stopped') }}</p>
          <p v-else class="mt-1 text-[13px] text-slate-300">{{ tt('admin.bc_campaign.success_sub', { when: bcCampaignUxSuccessInfo.nextAt || tt('admin.bc_campaign.success_when_fallback') }) }}</p>
          <div class="mt-5 w-full max-w-sm space-y-2">
            <button
              v-if="bcCampaignUxSuccessInfo.needsStart"
              type="button"
              class="w-full rounded-2xl border border-emerald-400/45 bg-gradient-to-r from-[#27b35f] to-[#36D67A] px-4 py-3 font-bold text-[#04130a] shadow-[0_18px_34px_-18px_rgba(54,214,122,0.95)] transition hover:brightness-110"
              @click="bcCampaignUxSuccessStartNow"
            >
              {{ tt('admin.bc_campaign.success_start_now') }}
            </button>
            <button type="button" class="w-full rounded-2xl border border-emerald-400/45 bg-gradient-to-r from-[#27b35f] to-[#36D67A] px-4 py-3 font-bold text-[#04130a] shadow-[0_18px_34px_-18px_rgba(54,214,122,0.95)] transition hover:brightness-110" @click="bcCampaignUxScreen = 'manage'">{{ tt('admin.bc_campaign.btn_to_campaign') }}</button>
            <button type="button" class="w-full rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 font-semibold transition hover:bg-white/[0.08]" @click="bcCampaignUxScreen = 'list'">{{ tt('admin.bc_campaign.btn_to_list') }}</button>
          </div>
        </div>

        <div v-else-if="bcCampaignUxScreen === 'manage' && bcCampaignUxManageItem" class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 pb-[max(5.5rem,calc(5.75rem+env(safe-area-inset-bottom,0px)))]">
          <p class="text-[12px] text-slate-400">{{ tt('admin.bc_campaign.manage_status') }} <span class="text-slate-200">{{ bcCampaignUxStatusLabel(bcCampaignUxManageItem) }}</span></p>
          <div class="mt-3 grid grid-cols-2 gap-2">
            <button type="button" class="rounded-2xl border border-white/10 bg-[#11151C] px-3 py-3 text-left transition hover:bg-[#151A22]" @click="bcCampaignUxManageOpenPostEditor">
              <p class="text-[12px] text-slate-400">{{ tt('admin.bc_campaign.card_posts') }}</p>
              <p class="mt-1 line-clamp-3 text-sm font-semibold leading-snug text-white">{{ bcCampaignUxManagePostsCardLabel }}</p>
            </button>
            <button
              type="button"
              class="rounded-2xl border border-white/10 bg-[#11151C] px-3 py-3 text-left transition hover:bg-[#151A22]"
              @click="bcCampaignUxOpenScheduleModal(bcCampaignUxManageItem)"
            >
              <p class="text-[12px] text-slate-400">{{ tt('admin.bc_campaign.card_schedule') }}</p>
              <p class="mt-1 text-sm font-semibold text-white">{{ bcCampaignUxScheduleSubtitleFromAutopost(bcCampaignUxManageItem.autopost) }}</p>
            </button>
            <button
              type="button"
              class="rounded-2xl border border-white/10 bg-[#11151C] px-3 py-3 text-left transition hover:bg-[#151A22]"
              @click="bcCampaignUxOpenScheduleModal(bcCampaignUxManageItem)"
            >
              <p class="text-[12px] text-slate-400">{{ tt('admin.bc_campaign.card_period') }}</p>
              <p class="mt-1 line-clamp-3 text-[13px] font-semibold leading-snug text-white">{{ bcCampaignUxPeriodLabelFromCamp(bcCampaignUxManageItem) }}</p>
            </button>
            <button type="button" class="rounded-2xl border border-white/10 bg-[#11151C] px-3 py-3 text-left transition hover:bg-[#151A22]" @click="bcCampaignUxOpenStats(bcCampaignUxManageItem)">
              <p class="text-[12px] text-slate-400">{{ tt('admin.bc_campaign.card_statistics') }}</p>
              <p class="mt-1 text-sm font-semibold text-emerald-300">{{ tt('admin.bc_campaign.stat_open') }}</p>
            </button>
          </div>
          <p
            v-if="bcCampaignUxManageAurumUi && bcCampaignUxManageAurumUi.usersOnly"
            class="mt-2 rounded-xl border border-white/10 bg-[#11151C] px-3 py-2 text-[11px] text-slate-400"
          >
            {{ tt('admin.bc_campaign.manage_aurum_dm_skip') }}
          </p>
          <p
            v-else-if="bcCampaignUxManageAurumUi && !bcCampaignUxManageAurumUi.usersOnly"
            class="mt-2 rounded-xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-[12px] text-amber-100/95"
          >
            {{ tt('admin.bc_campaign.manage_aurum_period', { total: fmtIntSpace(bcCampaignUxManageAurumUi.total), slot: fmtIntSpace(bcCampaignUxManageAurumUi.slot), sends: fmtIntSpace(bcCampaignUxManageAurumUi.sends) }) }}
            <span v-if="bcCampaignUxManageAurumUi.openEnded" class="text-amber-200/70"> {{ tt('admin.bc_campaign.open_end_notice_short') }}</span>
          </p>
          <div class="mt-3 rounded-2xl border border-white/10 bg-[#11151C] p-3 text-[11px] text-slate-300">
            <button type="button" class="flex w-full items-center justify-between text-left text-[11px] font-semibold text-slate-400 transition hover:text-slate-200" @click="bcCampaignUxOpenRecipientsModal">
              <span>{{ tt('admin.bc_campaign.manage_dest_heading') }}</span>
              <span class="text-slate-500">›</span>
            </button>
            <template v-if="bcCampaignUxManageDestinations.usersOnly">
              <p class="mt-1">{{ tt('admin.bc_campaign.targets_dm_autopost') }}</p>
            </template>
            <template v-else>
              <ul v-if="bcCampaignUxManageDestinations.channels.length" class="mt-1 list-inside list-disc space-y-0.5">
                <li v-for="row in bcCampaignUxManageDestinations.channels" :key="`m-ch-${row.id}`">{{ row.label }}</li>
              </ul>
              <ul v-if="bcCampaignUxManageDestinations.groups.length" class="mt-1 list-inside list-disc space-y-0.5">
                <li v-for="row in bcCampaignUxManageDestinations.groups" :key="`m-gr-${row.id}`">{{ row.label }}</li>
              </ul>
              <p v-if="!bcCampaignUxManageDestinations.channels.length && !bcCampaignUxManageDestinations.groups.length" class="mt-1 text-slate-500">
                {{ tt('admin.bc_campaign.destinations_fallback') }}
              </p>
            </template>
          </div>
          <div class="mt-3 flex flex-wrap gap-2">
            <button v-if="bcCampaignRunState(bcCampaignUxManageItem) === 'running'" type="button" class="rounded-xl border border-amber-400/40 bg-amber-900/50 px-3 py-2 text-xs font-semibold text-amber-100 transition hover:bg-amber-900/70" @click="bcCampaignPause(bcCampaignUxManageItem)">{{ tt('admin.bc_campaign.pause') }}</button>
            <button v-else type="button" class="rounded-xl border border-emerald-400/45 bg-emerald-700/85 px-3 py-2 text-xs font-semibold text-emerald-50 transition hover:brightness-110" @click="bcCampaignStartOrResume(bcCampaignUxManageItem)">{{ tt('admin.bc_campaign.start') }}</button>
            <button type="button" class="rounded-xl border border-white/15 bg-white/[0.04] px-3 py-2 text-xs font-semibold transition hover:bg-white/[0.08]" @click="bcCampaignStop(bcCampaignUxManageItem)">{{ tt('admin.bc_campaign.stop') }}</button>
            <button type="button" class="rounded-xl border border-emerald-400/35 bg-emerald-950/40 px-3 py-2 text-xs font-semibold text-emerald-100 transition hover:bg-emerald-950/55" @click="bcCampaignUxScreen = 'progress'">{{ tt('admin.bc_campaign.sending_progress') }}</button>
          </div>
          <div class="mt-4 space-y-2">
            <button type="button" class="flex w-full items-center justify-between rounded-2xl border border-rose-500/45 bg-rose-950/40 px-3 py-3 text-left text-rose-100 transition hover:bg-rose-950/60" @click="deleteBcAutopostCampaign(bcCampaignUxManageItem)"><span>{{ tt('admin.bc_campaign.delete_campaign') }}</span><span>›</span></button>
          </div>
        </div>

        <div v-if="bcCampaignUxScreen === 'postEditor'" class="relative min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 pb-[max(5.5rem,calc(5.75rem+env(safe-area-inset-bottom,0px)))]">
          <div
            v-if="bcCampaignUxPostEditorLoading"
            class="absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 rounded-xl bg-[#0b0d14]/90 px-4 backdrop-blur-[2px]"
            role="status"
            aria-live="polite"
          >
            <p class="text-sm font-semibold text-slate-200">{{ tt('admin.bc_campaign.post_editor_loading') }}</p>
          </div>
          <div :class="bcCampaignUxPostEditorLoading ? 'pointer-events-none select-none opacity-35' : ''">
          <p class="text-[12px] text-slate-400">{{ bcCampaignUxPostEditorMode === 'edit' ? tt('admin.bc_campaign.post_editor_edit') : tt('admin.bc_campaign.post_editor_new') }}</p>
          <label class="mt-2 block text-[12px] font-semibold text-slate-300">{{ tt('admin.bc_campaign.post_draft_title_label') }}</label>
          <div class="mt-1 flex min-w-0 items-center gap-1.5">
            <input
              v-model="bcTitle"
              type="text"
              maxlength="255"
              class="min-w-0 flex-1 rounded-xl border border-white/10 bg-[#11151C] px-3 py-2 text-sm text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] placeholder:text-slate-500 focus:border-indigo-400/45 focus:outline-none focus:ring-1 focus:ring-indigo-400/30"
              :placeholder="tt('admin.broadcast_ui.draft_title_ph')"
              :disabled="Number(bcSavingTitleId || 0) === Number(bcSelectedId || 0) && Number(bcSelectedId || 0) > 0"
              @keydown.enter.prevent="applyBcQuickDraftTitle"
            />
            <button
              v-show="bcQuickTitleDirty"
              type="button"
              class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-emerald-500/40 bg-emerald-500/20 text-[13px] font-bold text-emerald-200 shadow-[0_0_20px_-4px_rgba(16,185,129,0.35)] transition active:scale-95 hover:border-emerald-400/55 hover:bg-emerald-500/30 disabled:opacity-50"
              :disabled="Number(bcSavingTitleId || 0) === Number(bcSelectedId || 0) && Number(bcSelectedId || 0) > 0"
              :title="tt('admin.broadcast_ui.apply_title')"
              @click="applyBcQuickDraftTitle"
            >
              ✓
            </button>
          </div>
          <p class="mt-2 text-[12px] font-semibold text-zinc-300">{{ tt('admin.broadcast_ui.message_text') }}</p>
          <div
            ref="bcBodyRef"
            class="bc-editor mt-2 h-40 min-h-[10rem] shrink-0 overflow-y-auto rounded-xl border border-white/[0.08] bg-zinc-950 px-3 py-2.5 text-sm leading-relaxed focus-within:border-white/20 focus-within:ring-0"
            contenteditable="true"
            :data-placeholder="tt('admin.broadcast_ui.message_body_ph')"
            @input="onBcEditorInput"
            @paste="bcOnEditorPaste"
            @keydown="bcOnEditorKeydown"
            @click="onBcEditorClick"
            @mouseup="bcUpdateFormatState"
            @keyup="bcUpdateFormatState"
          />
          <div class="mt-2 flex flex-wrap gap-1.5">
            <button type="button" class="bc-tool-btn min-w-[2.1rem] !px-2" :class="bcFormatState.bold ? 'bc-tool-active' : ''" @mousedown.prevent @click="bcFormatBold"><b>B</b></button>
            <button type="button" class="bc-tool-btn min-w-[2.1rem] !px-2" :class="bcFormatState.italic ? 'bc-tool-active' : ''" @mousedown.prevent @click="bcFormatItalic"><i>I</i></button>
            <button type="button" class="bc-tool-btn min-w-[2.1rem] !px-2" :class="bcFormatState.underline ? 'bc-tool-active' : ''" @mousedown.prevent @click="bcFormatUnderline"><u>U</u></button>
            <button type="button" class="bc-tool-btn min-w-[2.1rem] !px-2" :class="bcFormatState.strike ? 'bc-tool-active' : ''" @mousedown.prevent @click="bcFormatStrike"><s>S</s></button>
            <button type="button" class="bc-tool-btn min-w-[2.1rem] !px-2 !text-[11px]" :class="bcFormatState.quote ? 'bc-tool-active' : ''" title="Цитата" @mousedown.prevent @click="bcFormatBlockquote">❝</button>
            <button type="button" class="bc-tool-btn min-w-[2.1rem] !px-2 !text-[11px]" :class="bcFormatState.spoiler ? 'bc-tool-active' : ''" title="Скрытый" @mousedown.prevent @click="bcFormatSpoiler">🙈</button>
            <button type="button" class="bc-tool-btn min-w-[2.1rem] !px-2 !text-[11px]" :class="bcFormatState.link ? 'bc-tool-active' : ''" title="Ссылка" @mousedown.prevent @click="bcFormatLink">🔗</button>
            <button type="button" class="bc-tool-btn font-mono min-w-[2.1rem] !px-2 !text-[11px]" title="Моноширинный блок" @mousedown.prevent @click="bcFormatPre">⌨</button>
            <button type="button" class="bc-tool-btn !px-2 !text-[11px]" :class="!bcCanUndo() ? 'opacity-40' : ''" :disabled="!bcCanUndo()" @mousedown.prevent @click="bcUndo">↶</button>
            <button type="button" class="bc-tool-btn !px-2 !text-[11px]" :class="!bcCanRedo() ? 'opacity-40' : ''" :disabled="!bcCanRedo()" @mousedown.prevent @click="bcRedo">↷</button>
          </div>
          <p class="mt-1 text-[11px]" :class="bcCurrentLen() > bcCurrentMaxLen() ? 'text-rose-400' : 'text-slate-500'">
            {{ tt('admin.broadcast_ui.chars_count', { current: bcCurrentLen(), max: bcCurrentMaxLen() }) }}
          </p>
          <div v-if="bcQuickButtonPreviewRows.length" class="mt-2 space-y-1">
            <p class="text-[11px] font-semibold text-slate-400">{{ tt('admin.broadcast_ui.buttons_block') }}</p>
            <div
              v-for="(row, ri) in bcQuickButtonPreviewRows.slice(0, 6)"
              :key="`camp-pe-row-${ri}`"
              class="flex flex-wrap gap-1"
            >
              <div
                v-for="(btn, bi) in row"
                :key="`camp-pe-btn-${ri}-${bi}-${btn.text}`"
                class="min-w-0 flex-1"
                :class="[bcButtonStyleChipClass(btn.style, btn.kind), row.length === 1 ? 'basis-full' : 'basis-[calc(50%-0.125rem)]']"
              >
                <p class="truncate text-center text-[12px]">{{ btn.text }}</p>
              </div>
            </div>
          </div>
          <div class="mt-3 grid grid-cols-2 gap-2">
            <button type="button" class="bc-tool-btn !w-full !justify-center text-[12px]" @click="bcAuxModal = 'keyboard'">{{ tt('admin.broadcast_ui.add_post_buttons') }}</button>
            <button type="button" class="bc-tool-btn !w-full !justify-center text-[12px]" @click="bcAuxModal = 'media'">{{ tt('admin.broadcast_ui.file_and_media') }}</button>
          </div>
          <div v-if="bcMediaHistory.length" class="mt-2 flex flex-wrap gap-2">
            <div v-for="(m, mi) in bcMediaHistory.slice(0, 8)" :key="`camp-pe-m-${mi}-${m.id || mi}`" class="relative shrink-0">
              <button
                v-if="m.previewUrl && (String(m.kind || '').toLowerCase().includes('photo') || String(m.kind || '').toLowerCase().includes('video') || String(m.kind || '').toLowerCase() === 'animation')"
                type="button"
                class="group relative block h-14 w-14 overflow-hidden rounded-lg border border-white/15 bg-slate-950/80 shadow-md ring-1 ring-white/[0.06] transition hover:border-cyan-400/35 hover:ring-cyan-400/25"
                :title="tt('admin.broadcast_ui.open_large')"
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
          <div class="mt-6 flex gap-2">
            <button type="button" class="bc-tool-btn flex-1 !justify-center py-2.5 text-sm font-semibold" @click="bcCampaignUxBack">{{ tt('admin.bc_campaign.back') }}</button>
            <button
              type="button"
              class="flex-1 rounded-xl border border-indigo-400/40 bg-gradient-to-r from-indigo-600/95 to-blue-700/95 px-3 py-2 text-sm font-extrabold text-white shadow-[0_14px_30px_-16px_rgba(59,130,246,0.8)] transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-45"
              :disabled="bcSaving"
              @click="bcCampaignUxSavePostEditor"
            >
              {{ tt('admin.bc_campaign.btn_save_post') }}
            </button>
          </div>
          </div>
        </div>

        <div v-if="bcCampaignUxScreen === 'progress'" class="relative flex min-h-0 flex-1 flex-col px-4 pb-6 pt-1">
          <p class="absolute left-4 top-2 z-10 max-w-[78%] text-left text-[13px] font-semibold leading-tight text-slate-200">
            {{ tt('admin.bc_campaign.progress_title') }}
          </p>
          <div class="flex flex-1 flex-col items-center justify-center pt-9 text-center">
          <div class="relative mt-2 h-44 w-44">
            <svg class="absolute inset-0 h-full w-full -rotate-90" viewBox="0 0 120 120" aria-hidden="true">
              <defs>
                <linearGradient id="bcApProgressRing" x1="0%" y1="30%" x2="100%" y2="100%">
                  <stop offset="0%" stop-color="#27b35f" />
                  <stop offset="52%" stop-color="#36D67A" />
                  <stop offset="100%" stop-color="#8fd41a" />
                </linearGradient>
              </defs>
              <circle cx="60" cy="60" r="52" fill="none" stroke="rgba(148,163,184,0.16)" stroke-width="8" />
              <circle cx="60" cy="60" r="52" fill="none" stroke="url(#bcApProgressRing)" stroke-width="8" stroke-linecap="round" :stroke-dasharray="bcCampaignAutopostProgressRingDash" />
            </svg>
            <div class="absolute inset-0 flex items-center justify-center">
              <img :src="bcTelegramPlaneIconUrl" class="h-11 w-11 object-contain drop-shadow-[0_0_22px_rgba(54,214,122,0.75)]" alt="" />
            </div>
            <span class="pointer-events-none absolute -bottom-0.5 -right-[0.55rem] text-[18px] font-bold tabular-nums leading-none sm:-right-[0.4rem] sm:text-[19px]">{{ bcCampaignAutopostProgressPct }}%</span>
          </div>
          <p class="mt-4 text-[12px] uppercase tracking-[0.14em] text-slate-500">{{ tt('admin.bc_campaign.progress_sent') }}</p>
          <p class="text-3xl font-bold tabular-nums">
            {{ fmtIntSpace(bcCampaignAutopostProgressDone) }}
            <span class="text-xl text-slate-400">{{ tt('admin.bc_campaign.progress_of') }}</span>
            {{ fmtIntSpace(bcCampaignAutopostProgressTotal) }}
          </p>
          <p v-if="bcCampaignAutopostProgressFail > 0" class="mt-2 text-sm text-rose-300">{{ tt('admin.bc_campaign.errors_label') }} {{ bcCampaignAutopostProgressFail }}</p>
          <button type="button" class="mt-8 w-full max-w-sm rounded-2xl border border-rose-500/45 bg-rose-950/45 px-4 py-3 text-[15px] font-semibold text-rose-100 transition hover:bg-rose-900/55" @click="bcCampaignUxScreen = 'manage'">{{ tt('admin.bc_campaign.btn_stop_sending') }}</button>
          </div>
        </div>

        <div v-if="bcCampaignUxScreen === 'stats'" class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 pb-[max(5.5rem,calc(5.75rem+env(safe-area-inset-bottom,0px)))]">
          <div class="flex items-center gap-2">
            <label class="text-[12px] text-slate-400">{{ tt('admin.bc_campaign.stats_period') }}</label>
            <select v-model.number="bcCampaignUxStatsPeriod" class="rounded-lg border border-white/10 bg-white/[0.05] px-2 py-1 text-xs focus:border-indigo-400/45 focus:outline-none" @change="bcCampaignUxOpenStats(bcCampaignUxManageItem)">
              <option :value="1">{{ tt('admin.bc_campaign.period_today') }}</option>
              <option :value="7">{{ tt('admin.bc_campaign.period_7d') }}</option>
              <option :value="30">{{ tt('admin.bc_campaign.period_30d') }}</option>
              <option :value="90">{{ tt('admin.bc_campaign.period_all') }}</option>
            </select>
          </div>
          <p
            v-if="bcCampaignUxStatsData && bcCampaignUxStatsData.broadcast_url_tracking_configured === false"
            class="mb-2 rounded-lg border border-amber-500/25 bg-amber-500/8 px-2.5 py-1.5 text-[10px] leading-snug text-amber-100/90"
          >
            {{ tt('admin.broadcast_shell.tracking_off_hint') }}
          </p>
          <p
            v-else-if="bcCampaignUxStatsData"
            class="mb-2 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-[10px] leading-snug text-slate-400"
          >
            {{ tt('admin.broadcast_shell.tracking_on_hint') }}
          </p>
          <div class="mt-1 grid grid-cols-2 gap-2">
            <button
              type="button"
              class="rounded-xl border border-white/10 bg-[#11151C] p-2.5 text-left shadow-[inset_0_1px_0_rgba(255,255,255,0.03)] ring-2 ring-transparent transition hover:border-emerald-400/30 hover:bg-[#141a24] hover:ring-emerald-500/15 focus-visible:outline-none focus-visible:ring-emerald-400/35"
              @click="bcCampaignUxStatsDeliverModalOpen = true"
            >
              <p class="text-[10px] text-slate-500">{{ tt('admin.bc_campaign.metric_delivered_posts') }}</p>
              <p class="text-lg font-bold tabular-nums">{{ fmtIntSpace(bcCampaignUxStatsDeliveredOk) }}</p>
              <p class="mt-1 text-[9px] text-slate-500">{{ tt('admin.bc_campaign.stats_delivery_tap_hint') }}</p>
              <div class="mt-2 space-y-1.5 border-t border-white/[0.08] pt-2">
                <div class="flex items-center justify-between gap-2 text-[11px]">
                  <span class="text-slate-500">{{ tt('admin.bc_campaign.metric_reactions') }}</span>
                  <span class="font-semibold tabular-nums text-white">{{ fmtIntSpace(Number(bcCampaignUxStatsData?.real_reactions_total || 0)) }}</span>
                </div>
                <div class="flex items-center justify-between gap-2 text-[11px]">
                  <span class="text-slate-500">{{ tt('admin.bc_campaign.metric_link_clicks') }}</span>
                  <span class="font-semibold tabular-nums text-white">{{ fmtIntSpace(Number(bcCampaignUxStatsData?.real_link_clicks_total || 0)) }}</span>
                </div>
                <div class="flex items-center justify-between gap-2 text-[11px]">
                  <span class="text-slate-500">{{ tt('admin.bc_campaign.metric_button_clicks') }}</span>
                  <span class="font-semibold tabular-nums text-white">{{ fmtIntSpace(Number(bcCampaignUxStatsData?.real_callback_clicks_total || 0)) }}</span>
                </div>
              </div>
            </button>
            <div class="rounded-xl border border-white/10 bg-[#11151C] p-2.5">
              <p class="text-[10px] text-slate-500">
                <abbr :title="tt('admin.broadcast_shell.ctr_hint_title')" class="cursor-help underline decoration-dotted decoration-slate-500 underline-offset-2">{{
                  tt('admin.broadcast_shell.ctr_abbr')
                }}</abbr>
              </p>
              <p class="text-lg font-bold tabular-nums text-emerald-300">{{ fmtPctTrim(bcCampaignUxStatsCtrPct) }}</p>
              <p class="mt-0.5 text-[10px] leading-tight text-slate-500">{{ bcCampaignUxStatsCtrSub }}</p>
            </div>
          </div>
          <p class="mt-3 text-[12px] text-slate-400">
            {{ Number(bcCampaignUxStatsData?.stats_ctr_percent ?? bcCampaignUxStatsData?.groups?.ctr ?? 0) >= 8 ? tt('admin.bc_campaign.ctr_above') : tt('admin.bc_campaign.ctr_try') }}
          </p>
          <div class="mt-4 rounded-xl border border-white/10 bg-[#11151C] p-3 text-[11px] text-slate-300">
            <p class="font-semibold text-slate-400">{{ tt('admin.bc_campaign.manage_dest_heading') }}</p>
            <template v-if="bcCampaignUxManageDestinations.usersOnly">
              <p class="mt-1">{{ tt('admin.bc_campaign.targets_dm_autopost') }}</p>
            </template>
            <template v-else-if="bcCampaignUxManageItem">
              <ul v-if="bcCampaignUxManageDestinations.channels.length" class="mt-1 list-inside list-disc space-y-0.5">
                <li v-for="row in bcCampaignUxManageDestinations.channels" :key="`st-ch-${row.id}`">{{ row.label }}</li>
              </ul>
              <ul v-if="bcCampaignUxManageDestinations.groups.length" class="mt-1 list-inside list-disc space-y-0.5">
                <li v-for="row in bcCampaignUxManageDestinations.groups" :key="`st-gr-${row.id}`">{{ row.label }}</li>
              </ul>
              <p v-if="!bcCampaignUxManageDestinations.channels.length && !bcCampaignUxManageDestinations.groups.length" class="mt-1 text-slate-500">
                {{ tt('admin.bc_campaign.destinations_fallback') }}
              </p>
            </template>
          </div>
          <button
            type="button"
            class="mt-4 w-full rounded-xl border border-indigo-400/35 bg-indigo-500/12 px-4 py-2.5 text-sm font-semibold text-indigo-100 transition hover:bg-indigo-500/20"
            @click="bcCampaignUxStatsOpenPostEditor"
          >{{ tt('admin.bc_campaign.edit_post_draft') }}</button>
          <button type="button" class="mt-2 w-full rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2.5 text-sm font-semibold transition hover:bg-white/[0.08]" @click="bcCampaignUxLeaveStatsToManage">{{ tt('admin.bc_campaign.btn_to_campaign') }}</button>
        </div>
      </div>
    </GuardTeleport>

    <GuardTeleport guard-to="body">
      <!-- Вынесены из оболочки кампании: фиксированный z-index в body, иначе вложенные absolute оказывались ниже параллельных teleport-слоёв. -->
      <div
        v-if="bcCampaignUxScheduleModalOpen && bcCampaignUxOpen"
        class="fixed inset-0 z-[100230] flex items-end justify-center bg-black/72 px-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] pt-[max(12px,calc(env(safe-area-inset-top,0px)+48px))] backdrop-blur-[2px] md:items-center md:pb-6"
        @click.self="bcCampaignUxCloseScheduleModal"
      >
        <div
          class="flex max-h-[min(85vh,36rem)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/12 bg-[#12161f] text-zinc-100 shadow-[0_24px_64px_-24px_rgba(0,0,0,0.92)]"
          @click.stop
        >
          <div class="flex shrink-0 items-start justify-between gap-2 border-b border-white/10 px-4 py-3">
            <div class="min-w-0">
              <p class="truncate text-[16px] font-extrabold leading-snug text-white">{{ tt('admin.bc_campaign.schedule_modal_title') }}</p>
            </div>
            <button type="button" class="shrink-0 rounded-lg px-2 py-1 text-sm text-zinc-300 hover:bg-white/10" @click="bcCampaignUxCloseScheduleModal">✕</button>
          </div>
          <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-3">
            <div class="space-y-2 rounded-2xl border border-white/10 bg-[#11151C] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
              <label class="text-[12px] text-slate-300">{{ tt('admin.bc_campaign.period_start_label') }}</label>
              <div class="flex flex-wrap items-center gap-2">
                <input v-model="bcCampaignUxScheduleForm.startDate" type="date" class="min-w-[10rem] flex-1 rounded-xl border border-white/10 bg-black/30 px-2 py-2 text-sm focus:border-indigo-400/45 focus:outline-none" />
                <button
                  type="button"
                  class="shrink-0 rounded-xl border border-violet-400/40 bg-violet-600/25 px-3 py-2 text-[11px] font-semibold text-violet-100 transition hover:bg-violet-600/35"
                  @click="bcCampaignUxScheduleSetStartTodayFromTz"
                >
                  {{ tt('admin.bc_campaign.btn_today_tz') }}
                </button>
              </div>
              <label class="pt-1 text-[12px] text-slate-300">{{ tt('admin.bc_campaign.period_end_label') }}</label>
              <input v-model="bcCampaignUxScheduleForm.endDate" type="date" class="w-full rounded-xl border border-white/10 bg-black/30 px-2 py-2 text-sm focus:border-indigo-400/45 focus:outline-none" />
              <p class="text-[10px] text-slate-500">{{ tt('admin.bc_campaign.period_end_hint') }}</p>
              <label class="text-[12px] text-slate-300">{{ tt('admin.bc_campaign.freq_label') }}</label>
              <select v-model="bcCampaignUxScheduleForm.scheduleMode" class="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-2 py-2 text-sm focus:border-indigo-400/45 focus:outline-none">
                <option value="every_day">{{ tt('admin.bc_campaign.freq_every_day') }}</option>
                <option value="weekdays">{{ tt('admin.bc_campaign.freq_weekdays') }}</option>
              </select>
              <div v-if="bcCampaignUxScheduleForm.scheduleMode === 'weekdays'" class="flex flex-wrap gap-1.5 pt-1">
                <button
                  v-for="d in BC_WEEKDAY_OPTS"
                  :key="`sch-wd-${d.v}`"
                  type="button"
                  class="rounded-lg border px-2 py-1 text-[11px] transition"
                  :class="bcCampaignUxScheduleForm.weekdays.includes(d.v) ? 'border-violet-400 bg-violet-500/20 text-violet-100' : 'border-white/15 bg-black/20 hover:bg-white/[0.06]'"
                  @click="bcCampaignUxScheduleToggleWeekday(d.v)"
                >
                  {{ d.label }}
                </button>
              </div>
              <label class="mt-2 text-[12px] text-slate-300">{{ tt('admin.bc_campaign.multi_send_windows_heading') }}</label>
              <p class="text-[10px] leading-snug text-slate-500">{{ tt('admin.bc_campaign.multi_send_windows_help') }}</p>
              <div v-for="(seg, si) in bcCampaignUxScheduleForm.sendWindows" :key="`sch-sw-${si}`" class="mt-2 space-y-2 rounded-xl border border-white/[0.08] bg-black/25 p-2.5">
                <div class="flex items-center justify-between gap-2">
                  <span class="text-[11px] font-semibold text-slate-400">{{ tt('admin.bc_campaign.slot_n', { n: si + 1 }) }}</span>
                  <div class="flex shrink-0 gap-1">
                    <button
                      type="button"
                      class="rounded-lg border border-emerald-500/35 px-2 py-0.5 text-[12px] font-bold text-emerald-200 disabled:cursor-not-allowed disabled:opacity-40"
                      :disabled="(bcCampaignUxScheduleForm.sendWindows || []).length >= 24"
                      @click="bcCampaignUxScheduleFormAddSegment"
                    >
                      +
                    </button>
                    <button
                      type="button"
                      class="rounded-lg border border-rose-500/35 px-2 py-0.5 text-[12px] font-bold text-rose-100 disabled:cursor-not-allowed disabled:opacity-40"
                      :disabled="(bcCampaignUxScheduleForm.sendWindows || []).length <= 1"
                      @click="bcCampaignUxScheduleFormRemoveSegment(si)"
                    >
                      −
                    </button>
                  </div>
                </div>
                <div class="grid grid-cols-2 gap-2">
                  <div>
                    <p class="text-[10px] text-slate-500">{{ tt('admin.bc_campaign.slot_from') }}</p>
                    <input v-model="seg.windowStart" type="time" class="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-2 py-2 text-sm focus:border-indigo-400/45 focus:outline-none" />
                  </div>
                  <div>
                    <p class="text-[10px] text-slate-500">{{ tt('admin.bc_campaign.slot_to') }}</p>
                    <input v-model="seg.windowEnd" type="time" class="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-2 py-2 text-sm focus:border-indigo-400/45 focus:outline-none" />
                  </div>
                </div>
                <div>
                  <p class="text-[10px] text-slate-500">{{ tt('admin.bc_campaign.posts_in_slot') }}</p>
                  <input v-model.number="seg.posts" type="number" min="1" max="288" class="hide-num-spin mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-2 py-2 text-sm focus:border-indigo-400/45 focus:outline-none" />
                </div>
                <div
                  v-if="(bcCampaignUxScheduleModalSlotTimePreview[si] || []).length"
                  class="rounded-lg border border-white/[0.06] bg-black/20 px-2 py-2"
                >
                  <p class="text-[10px] font-semibold text-slate-500">
                    <template v-if="bcCampaignUxScheduleModalSlotDay">
                      {{ tt('admin.bc_campaign.schedule_slot_times_preview_day', { day: bcCampaignUxScheduleModalSlotDay }) }}
                    </template>
                    <template v-else>
                      {{ tt('admin.bc_campaign.schedule_slot_times_preview') }}
                    </template>
                  </p>
                  <p
                    v-if="bcCampaignUxScheduleModalNightDayHint"
                    class="mt-1 text-[10px] leading-snug text-sky-200/90"
                  >
                    {{ bcCampaignUxScheduleModalNightDayHint }}
                  </p>
                  <p
                    v-if="!bcCampaignUxScheduleModalSlotStatusApplicable"
                    class="mt-1 text-[10px] leading-snug text-amber-200/85"
                  >
                    {{ tt('admin.bc_campaign.schedule_slot_preview_draft_hint') }}
                  </p>
                  <p class="mt-1 break-words font-mono text-[11px] leading-relaxed">
                    <template v-for="(ent, ti) in (bcCampaignUxScheduleModalSlotEntries[si] || [])" :key="`sch-st-${si}-${ti}`">
                      <span v-if="ti > 0" class="text-slate-500"> · </span>
                      <span
                        :class="bcCampaignUxScheduleSlotStatusClass(ent.status)"
                        :title="bcCampaignUxScheduleSlotStatusTitle(ent.status)"
                      >{{ ent.label }}</span>
                    </template>
                  </p>
                  <p class="mt-2 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-slate-500">
                    <span v-if="bcCampaignUxScheduleModalSlotStatusApplicable && bcCampaignRunState(bcCampaignUxScheduleModalCamp) === 'running'"><span class="text-emerald-400" aria-hidden="true">●</span> {{ tt('admin.bc_campaign.schedule_slot_sent') }}</span>
                    <span v-if="bcCampaignUxScheduleModalSlotStatusApplicable && bcCampaignRunState(bcCampaignUxScheduleModalCamp) === 'running'"><span class="text-slate-200" aria-hidden="true">●</span> {{ tt('admin.bc_campaign.schedule_slot_pending') }}</span>
                    <span v-if="bcCampaignUxScheduleModalSlotStatusApplicable && bcCampaignRunState(bcCampaignUxScheduleModalCamp) === 'running'"><span class="text-rose-400" aria-hidden="true">●</span> {{ tt('admin.bc_campaign.schedule_slot_skipped') }}</span>
                    <span v-if="bcCampaignUxScheduleModalSlotStatusApplicable && bcCampaignRunState(bcCampaignUxScheduleModalCamp) !== 'running'"><span class="text-slate-200" aria-hidden="true">●</span> {{ tt('admin.bc_campaign.schedule_slot_planned_stopped') }}</span>
                    <span v-if="!bcCampaignUxScheduleModalSlotStatusApplicable"><span class="text-violet-300" aria-hidden="true">●</span> {{ tt('admin.bc_campaign.schedule_slot_preview') }}</span>
                  </p>
                  <p
                    v-if="bcCampaignUxScheduleModalSchedulerHint"
                    class="mt-2 rounded-lg border border-rose-500/40 bg-rose-500/10 px-2 py-1.5 text-[11px] leading-snug text-rose-100/95"
                  >
                    {{ bcCampaignUxScheduleModalSchedulerHint }}
                  </p>
                  <p
                    v-if="bcCampaignUxScheduleModalStoppedHint"
                    class="mt-2 rounded-lg border border-amber-500/35 bg-amber-500/10 px-2 py-1.5 text-[11px] leading-snug text-amber-100/95"
                  >
                    {{ bcCampaignUxScheduleModalStoppedHint }}
                  </p>
                  <p
                    v-if="bcCampaignUxScheduleModalBlockHint"
                    class="mt-2 rounded-lg border border-amber-500/35 bg-amber-500/10 px-2 py-1.5 text-[11px] leading-snug text-amber-100/95"
                  >
                    {{ bcCampaignUxScheduleModalBlockHint }}
                  </p>
                  <p class="mt-2 text-[10px] leading-snug text-slate-500">{{ tt('admin.bc_campaign.schedule_timing_precision') }}</p>
                </div>
              </div>
              <p v-if="(bcCampaignUxScheduleForm.sendWindows || []).length >= 2" class="mt-2 text-[11px] font-medium text-slate-400">
                {{ tt('admin.bc_campaign.slots_daily_total') }}:
                {{ (bcCampaignUxScheduleForm.sendWindows || []).reduce((a, s) => a + Math.max(1, Math.min(288, Number(s.posts || 1))), 0) }}
              </p>
              <label class="mt-3 text-[12px] text-slate-300">{{ tt('admin.bc_campaign.timezone') }}</label>
              <input v-model="bcCampaignUxScheduleForm.timezone" type="text" class="w-full rounded-xl border border-white/10 bg-black/30 px-2 py-2 text-sm focus:border-indigo-400/45 focus:outline-none" />
              <label class="flex items-center gap-2 text-[12px] text-slate-300"><input v-model="bcCampaignUxScheduleForm.spreadInWindow" type="checkbox" /> {{ tt('admin.bc_campaign.spread_even') }}</label>
            </div>
          </div>
          <div class="shrink-0 border-t border-white/10 px-4 py-3 pb-[max(0.75rem,calc(0.35rem+env(safe-area-inset-bottom,0px)))]">
            <div class="flex gap-2">
              <button
                type="button"
                class="flex-1 rounded-xl border border-white/12 bg-white/[0.04] py-3 text-[14px] font-semibold text-zinc-100 transition hover:bg-white/[0.08] disabled:opacity-50"
                :disabled="bcCampaignUxScheduleBusy"
                @click="bcCampaignUxCloseScheduleModal"
              >
                {{ tt('common.cancel') }}
              </button>
              <button
                type="button"
                class="flex-1 rounded-xl bg-gradient-to-r from-[#27b35f] to-[#36D67A] py-3 text-[14px] font-bold text-[#04130a] shadow-[0_14px_30px_-14px_rgba(54,214,122,0.85)] hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
                :disabled="bcCampaignUxScheduleBusy"
                @click="bcCampaignUxSaveScheduleModal"
              >
                {{ tt('common.save') }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div
        v-if="bcCampaignUxRecipientsModalOpen && bcCampaignUxOpen"
        class="fixed inset-0 z-[100230] flex items-end justify-center bg-black/72 px-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] pt-[max(12px,calc(env(safe-area-inset-top,0px)+48px))] backdrop-blur-[2px] md:items-center md:pb-6"
        @click.self="bcCampaignUxCloseRecipientsModal"
      >
        <div
          class="flex max-h-[min(80vh,28rem)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/12 bg-[#12161f] text-zinc-100 shadow-[0_24px_64px_-24px_rgba(0,0,0,0.92)]"
          role="dialog"
          aria-modal="true"
          @click.stop
        >
          <div class="flex shrink-0 items-center justify-between gap-2 border-b border-white/10 px-4 py-3">
            <p class="text-[16px] font-extrabold text-white">{{ tt('admin.bc_campaign.modal_recipients_title') }}</p>
            <button type="button" class="rounded-lg px-2 py-1 text-sm text-zinc-300 hover:bg-white/10" @click="bcCampaignUxCloseRecipientsModal">✕</button>
          </div>
          <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-3">
            <div class="mb-3 rounded-lg border border-white/10 bg-[#11151C] px-3 py-2">
              <p class="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{{ tt('admin.bc_campaign.modal_period_heading') }}</p>
              <p class="mt-1 text-[13px] text-slate-200">{{ bcCampaignUxPeriodLabelFromCamp(bcCampaignUxManageItem) }}</p>
            </div>
            <template v-if="bcCampaignUxManageDestinations.usersOnly">
              <p class="text-[13px] text-slate-300">{{ tt('admin.bc_campaign.targets_dm_autopost') }}</p>
            </template>
            <template v-else>
              <template v-if="bcCampaignUxManageDestinations.channels.length">
                <p class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-violet-300">{{ tt('admin.bc_campaign.target_channels') }}</p>
                <ul class="mb-3 list-inside list-disc space-y-1 text-[13px] text-slate-200">
                  <li v-for="row in bcCampaignUxManageDestinations.channels" :key="`mr-ch-${row.id}`">{{ row.label }}</li>
                </ul>
              </template>
              <template v-if="bcCampaignUxManageDestinations.groups.length">
                <p class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-cyan-300">{{ tt('admin.bc_campaign.target_groups') }}</p>
                <ul class="list-inside list-disc space-y-1 text-[13px] text-slate-200">
                  <li v-for="row in bcCampaignUxManageDestinations.groups" :key="`mr-gr-${row.id}`">{{ row.label }}</li>
                </ul>
              </template>
              <p v-if="!bcCampaignUxManageDestinations.channels.length && !bcCampaignUxManageDestinations.groups.length" class="text-[13px] text-slate-500">
                {{ tt('admin.bc_campaign.destinations_fallback') }}
              </p>
            </template>
          </div>
        </div>
      </div>

      <div
        v-if="bcCampaignUxCampaignPostsModalOpen && bcCampaignUxOpen"
        class="fixed inset-0 z-[100230] flex items-end justify-center bg-black/72 px-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] pt-[max(12px,calc(env(safe-area-inset-top,0px)+48px))] backdrop-blur-[2px] md:items-center md:pb-6"
        @click.self="bcCampaignUxCloseCampaignPostsModal"
      >
        <div
          class="flex max-h-[min(85vh,36rem)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/12 bg-[#12161f] text-zinc-100 shadow-[0_24px_64px_-24px_rgba(0,0,0,0.92)]"
          role="dialog"
          aria-modal="true"
          @click.stop
        >
          <div class="flex shrink-0 items-center justify-between gap-2 border-b border-white/10 px-4 py-3">
            <p class="text-[16px] font-extrabold text-white">{{ bcCampaignUxCampaignPostsModalHeading }}</p>
            <button type="button" class="rounded-lg px-2 py-1 text-sm text-zinc-300 hover:bg-white/10" @click="bcCampaignUxCloseCampaignPostsModal">✕</button>
          </div>
          <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-3">
            <template v-if="bcCampaignUxCampaignPostsModalItems.length">
              <div v-for="post in bcCampaignUxCampaignPostsModalItems" :key="`camp-post-modal-${post.id}`" class="mb-3 rounded-xl border border-white/10 bg-[#11151C] p-3">
                <p class="text-[12px] font-semibold text-white">
                  {{ post.title || tt('admin.bc_campaign.post_named', { id: post.id }) }}
                </p>
                <div v-if="bcCampaignUxPostsModalMedia[post.id]?.previewUrl" class="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    class="relative h-24 w-24 shrink-0 overflow-hidden rounded-xl border border-white/15 bg-zinc-950/80 ring-1 ring-white/[0.06] transition hover:border-cyan-400/35"
                    @click="openBcMediaViewer(bcCampaignUxPostsModalMedia[post.id])"
                  >
                    <img
                      v-if="bcCampaignUxPostsModalMedia[post.id].kind === 'photo'"
                      :src="bcCampaignUxPostsModalMedia[post.id].previewUrl"
                      class="h-full w-full object-cover"
                      alt=""
                    />
                    <video v-else :src="bcCampaignUxPostsModalMedia[post.id].previewUrl" class="h-full w-full object-cover" muted playsinline />
                  </button>
                </div>
                <div
                  class="mt-2 max-h-48 overflow-y-auto rounded-lg border border-white/[0.08] bg-zinc-950/55 p-2.5 text-[13px] leading-relaxed text-zinc-100"
                  v-html="bcNormalizeHtmlForTelegram(String(post.body_html || post.body_text || '')) || '—'"
                />
              </div>
            </template>
            <p v-else class="py-4 text-center text-[13px] text-slate-500">{{ tt('admin.bc_campaign.modal_posts_empty') }}</p>
          </div>
          <div class="flex shrink-0 gap-2 border-t border-white/10 px-4 py-3 pb-[max(0.65rem,calc(0.25rem+env(safe-area-inset-bottom,0px)))]">
            <button type="button" class="bc-tool-btn flex-1 !justify-center py-2.5 text-sm" @click="bcCampaignUxCloseCampaignPostsModal">{{ tt('common.close') }}</button>
          </div>
        </div>
      </div>

        <div
          v-if="bcCampaignUxStatsDeliverModalOpen && bcCampaignUxOpen"
          class="fixed inset-0 z-[100235] flex items-end justify-center bg-black/75 px-3 pb-[max(1rem,calc(4.25rem+env(safe-area-inset-bottom,0px)))] pt-[env(safe-area-inset-top,0px)] backdrop-blur-[2px] md:items-center md:pb-12"
          @click.self="bcCampaignUxStatsDeliverModalOpen = false"
        >
          <div
            class="flex max-h-[min(82dvh,32rem)] w-full max-w-md flex-col overflow-hidden rounded-2xl border border-white/12 bg-[#12161f] text-zinc-100 shadow-[0_24px_80px_-24px_rgba(0,0,0,0.95)]"
            role="dialog"
            aria-modal="true"
            @click.stop
          >
            <div class="flex shrink-0 items-center justify-between gap-2 border-b border-white/10 px-4 py-3">
              <p class="text-[15px] font-extrabold text-white">{{ tt('admin.bc_campaign.delivery_history_title') }}</p>
              <button type="button" class="rounded-lg px-2 py-1 text-sm text-zinc-300 hover:bg-white/10" @click="bcCampaignUxStatsDeliverModalOpen = false">✕</button>
            </div>
            <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-3">
              <template v-if="bcCampaignUxStatsSortedRuns.length">
                <div
                  v-for="run in bcCampaignUxStatsSortedRuns"
                  :key="`camp-dlv-${run.id}-${run.broadcast_id}`"
                  class="mb-2 rounded-xl border border-white/[0.08] bg-[#11151C] px-3 py-2.5 text-[12px] leading-snug text-zinc-200"
                >
                  <p class="font-semibold text-white">{{ run.broadcast_title || tt('admin.bc_campaign.post_named', { id: run.broadcast_id }) }}</p>
                  <p class="mt-1 text-[11px] text-slate-400">
                    {{ bcCampaignUxFormatCampStatInstant(run.sent_at || run.created_at) }}
                    <span class="mx-1 text-slate-600">·</span>
                    {{ tt('admin.bc_campaign.delivery_hist_ok', { n: fmtIntSpace(Math.max(0, Math.trunc(Number(run.recipient_ok || 0)))) }) }}
                    <template v-if="Number(run.recipient_fail || 0) > 0">
                      · {{ tt('admin.bc_campaign.delivery_hist_fail', { n: fmtIntSpace(Math.max(0, Math.trunc(Number(run.recipient_fail || 0)))) }) }}
                    </template>
                  </p>
                  <p
                    v-if="Math.max(0, Math.trunc(Number(run.recipient_ok || 0))) > 0 && bcFormatPerSendEngagementLine(run.per_send_engagement)"
                    class="mt-2 text-[10px] leading-snug text-slate-500"
                  >
                    {{ bcFormatPerSendEngagementLine(run.per_send_engagement) }}
                  </p>
                </div>
              </template>
              <p v-else class="py-6 text-center text-[13px] text-slate-500">{{ tt('admin.bc_campaign.delivery_history_empty') }}</p>
            </div>
            <div class="shrink-0 border-t border-white/10 px-4 py-3">
              <button type="button" class="w-full rounded-xl border border-white/12 bg-white/[0.06] py-2.5 text-sm font-semibold transition hover:bg-white/[0.09]" @click="bcCampaignUxStatsDeliverModalOpen = false">{{ tt('common.close') }}</button>
            </div>
          </div>
        </div>
    </GuardTeleport>

    <GuardTeleport guard-to="body">
      <div
        v-if="bcCampaignUxRecipientPickerOpen && bcCampaignUxOpen"
        class="fixed inset-0 z-[100240] flex h-[100dvh] min-w-0 flex-col overflow-hidden bg-[#0b0d14] pt-[env(safe-area-inset-top,0px)] pb-[env(safe-area-inset-bottom,0px)] text-white"
      >
        <div class="flex items-center justify-between border-b border-white/10 bg-[#12141c] px-4 py-3">
          <p class="text-[16px] font-bold">{{ bcCampaignUxRecipientPickerKind === 'channels' ? tt('admin.bc_campaign.picker_channels') : tt('admin.bc_campaign.picker_groups') }}</p>
          <button type="button" class="rounded-lg px-2 py-1 text-sm text-zinc-300 transition hover:bg-white/10" @click="bcCampaignUxRecipientPickerOpen = false">✕</button>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-3 pb-[max(5.5rem,calc(5.75rem+env(safe-area-inset-bottom,0px)))]">
          <input v-model="bcCampaignUxRecipientQuery" type="text" :placeholder="tt('admin.bc_campaign.search_ph')" class="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm placeholder:text-slate-500 focus:border-indigo-400/45 focus:outline-none" />
          <div class="mt-3 space-y-1.5">
            <label
              v-for="c in bcCampaignUxRecipientsFiltered"
              :key="`ux-r-${bcCampaignUxRecipientPickerKind}-${bcNormalizeChatId(c)}`"
              class="flex items-center gap-2 rounded-xl border border-white/10 bg-[#11151C] px-3 py-2 text-sm transition hover:bg-[#151A22]"
            >
              <input
                type="checkbox"
                :checked="(bcCampaignUxRecipientPickerKind === 'channels' ? bcCampaignUxWizard.selectedChannels : bcCampaignUxWizard.selectedGroups).includes(bcNormalizeChatId(c))"
                @change="bcCampaignUxToggleRecipient(bcNormalizeChatId(c))"
              />
              <span class="truncate">{{ c.title || c.username || bcNormalizeChatId(c) }}</span>
            </label>
            <p v-if="!bcCampaignUxRecipientsFiltered.length" class="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-[12px] text-slate-400">{{ tt('admin.bc_campaign.nothing_found') }}</p>
          </div>
        </div>
        <div class="grid grid-cols-3 gap-2 border-t border-white/10 bg-black/20 px-4 py-3">
          <button type="button" class="rounded-xl border border-white/10 bg-white/[0.04] px-2 py-2 text-xs font-semibold transition hover:bg-white/[0.08]" @click="bcCampaignUxSelectAllRecipients">{{ tt('admin.bc_campaign.select_all') }}</button>
          <button type="button" class="rounded-xl border border-white/10 bg-white/[0.04] px-2 py-2 text-xs font-semibold transition hover:bg-white/[0.08]" @click="bcCampaignUxClearRecipients">{{ tt('admin.bc_campaign.clear') }}</button>
          <button type="button" class="rounded-xl border border-emerald-400/40 bg-gradient-to-r from-[#27b35f] to-[#36D67A] px-2 py-2 text-xs font-bold text-[#04130a] shadow-[0_16px_28px_-18px_rgba(54,214,122,0.95)] transition hover:brightness-110" @click="bcCampaignUxRecipientPickerOpen = false">{{ tt('admin.bc_campaign.done') }}</button>
        </div>
      </div>
    </GuardTeleport>

    <div
      v-if="bcAutopostingModalOpen"
      class="bc-autopost-modal-overlay fixed inset-0 z-[96000] flex min-h-0 flex-col items-center justify-center overflow-y-auto overscroll-contain bg-[#0b0d14] px-3 py-4 pt-[max(0.75rem,calc(env(safe-area-inset-top,0px)+52px))] pb-[max(1rem,calc(5rem+env(safe-area-inset-bottom,0px)))]"
      @click.self="bcAutopostingModalOpen = false"
    >
      <div
        class="bc-autopost-modal-card mx-auto flex w-full max-w-md min-h-0 max-h-[min(88dvh,40rem)] flex-col overflow-hidden rounded-2xl bg-[#16171e] text-zinc-100 shadow-[0_28px_80px_-24px_rgba(0,0,0,0.88)] ring-1 ring-white/[0.08] sm:max-h-[min(86vh,42rem)]"
        @click.stop
      >
        <div class="shrink-0 bg-[#1a1c24] p-4 pb-2">
          <div class="flex items-center justify-between gap-2">
            <h3 class="text-sm font-semibold text-zinc-100">
              {{
                bcAutopostEditMode === 'campaign'
                  ? `Автопостинг — кампания №${bcAutopostCampaignUserSeq != null ? bcAutopostCampaignUserSeq : bcAutopostCampaignId || ''} (id ${bcAutopostCampaignId || ''})`
                  : 'Автопостинг'
              }}
            </h3>
            <div class="flex items-center gap-1">
              <button
                type="button"
                class="bc-tool-btn bc-broadcast-i"
                :title="tt('admin.autopost.help_tooltip')"
                :aria-label="tt('admin.autopost.help_aria')"
                @click="bcShowAutopostHelp = true"
              >
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
            <button type="button" class="bc-tool-btn" @click="bcAutopostingModalOpen = false">{{ tt('common.locale_code') === 'en' ? 'Cancel' : 'Отмена' }}</button>
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
          <p class="text-base font-semibold text-white">{{ tt('admin.broadcast_stats.title') }}</p>
          <button type="button" class="bc-tool-btn" @click="bcStatsModalOpen = false">✕</button>
        </div>
        <label class="text-xs text-slate-400">{{ tt('admin.broadcast_stats.post') }}</label>
        <select
          v-model="bcStatsSelectedId"
          class="mt-1 w-full rounded-xl border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-slate-100"
        >
          <option v-for="b in broadcasts" :key="`bstat-${b.id}`" :value="Number(b.id)">
            {{ b.title || tt('admin.broadcast_stats.untitled') }}
          </option>
        </select>
        <div class="mt-2 rounded-xl border border-slate-700 bg-slate-950/40 p-2">
          <div class="flex items-center justify-between gap-2">
            <p class="text-xs text-slate-300">{{ statsHistoryTitle() }}</p>
            <button type="button" class="bc-tool-btn" @click="openStatsHistoryModal">{{ tt('admin.broadcast_stats.full_history') }}</button>
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
            <p v-if="!bcStatsHistoryPreview.length" class="text-[11px] text-slate-500">{{ tt('admin.broadcast_stats.no_runs_yet') }}</p>
          </div>
        </div>
        <div v-if="bcStatsCurrentItem" class="mt-4 grid grid-cols-2 gap-2 text-xs">
          <div class="rounded-xl border border-slate-700 bg-slate-800/70 p-3">
            <p class="text-slate-400">{{ tt('admin.broadcast_stats.status') }}</p>
            <p class="mt-1 text-sm font-semibold text-white">{{ bcStatusLabel(bcStatsCurrentItem.status) }}</p>
          </div>
          <div class="rounded-xl border border-slate-700 bg-slate-800/70 p-3">
            <p class="text-slate-400">{{ bcStatsTab === 'groups' ? tt('admin.broadcast_stats.connected_groups') : tt('admin.broadcast_stats.connected_bots') }}</p>
            <p class="mt-1 text-sm font-semibold text-white">{{ bcStatsTab === 'groups' ? (bcStatsData.connected_groups_total || 0) : (bcStatsData.connected_bots_total || 0) }}</p>
          </div>
          <div class="rounded-xl border border-slate-700 bg-slate-800/70 p-3">
            <p class="text-slate-400">{{ tt('admin.broadcast_stats.created') }}</p>
            <p class="mt-1 text-sm font-semibold text-white">{{ fmtDateTime(bcStatsCurrentItem.created_at) }}</p>
          </div>
          <div class="rounded-xl border border-slate-700 bg-slate-800/70 p-3">
            <p class="text-slate-400">{{ tt('admin.broadcast_stats.sent') }}</p>
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
            {{ tt('admin.broadcast_stats.to_bots') }}
          </button>
          <button
            type="button"
            class="bc-tool-btn"
            :class="bcStatsTab === 'groups' ? 'bc-tool-active' : ''"
            @click="bcStatsTab = 'groups'"
          >
            {{ tt('admin.broadcast_stats.to_groups') }}
          </button>
        </div>
        <div v-if="showFullAdminShell && bcStatsTab === 'bots'" class="mt-3 grid grid-cols-2 gap-2 text-xs">
          <div class="rounded-xl border border-emerald-500/40 bg-emerald-500/10 p-3">
            <p class="text-emerald-200">{{ tt('admin.broadcast_stats.delivered') }}</p>
            <p class="mt-1 text-sm font-semibold text-emerald-100">{{ bcStatsData.bots.ok || 0 }}</p>
          </div>
          <div class="rounded-xl border border-rose-500/40 bg-rose-500/10 p-3">
            <p class="text-rose-200">{{ tt('admin.broadcast_stats.errors') }}</p>
            <p class="mt-1 text-sm font-semibold text-rose-100">{{ bcStatsData.bots.fail || 0 }}</p>
          </div>
        </div>
        <div v-else class="mt-3 space-y-2">
          <div v-if="isBroadcastShellLite" class="mb-1 text-[11px] text-slate-400">
            {{
              isDelegatedFreeBroadcastCabinet
                ? tt('admin.broadcast_stats.stats_delegated_only')
                : tt('admin.broadcast_stats.stats_own_only')
            }}
          </div>
          <div class="grid grid-cols-2 gap-2 text-xs">
            <div class="rounded-xl border border-emerald-500/40 bg-emerald-500/10 p-3">
              <p class="text-emerald-200">{{ tt('admin.broadcast_stats.delivered') }}</p>
              <p class="mt-1 text-sm font-semibold text-emerald-100">{{ bcStatsData.groups.ok || 0 }}</p>
            </div>
            <div class="rounded-xl border border-rose-500/40 bg-rose-500/10 p-3">
              <p class="text-rose-200">{{ tt('admin.broadcast_stats.errors') }}</p>
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
            <p v-if="!bcStatsData.per_groups.length" class="p-2 text-center text-xs text-slate-500">{{ tt('admin.broadcast_stats.per_group_empty') }}</p>
          </div>
        </div>
        <div v-if="(bcStatsData.send_history || []).length" class="mt-3">
          <p class="text-xs font-semibold text-slate-300">{{ tt('admin.broadcast_shell.send_history_title') }}</p>
          <div class="mt-2 max-h-52 space-y-2 overflow-y-auto rounded-xl border border-slate-700 bg-slate-950/40 px-2 py-2">
            <div
              v-for="(h, hi) in bcStatsData.send_history"
              :key="`bstat-hist-${hi}-${h.batch_id ?? hi}`"
              class="border-b border-slate-700/60 pb-2 last:border-b-0 last:pb-0"
            >
              <p class="text-[11px] font-semibold text-slate-200">{{ fmtBroadcastShortTime(h.started_at || h.ended_at) || '—' }}</p>
              <ul v-if="(h.groups || []).length" class="mt-1 space-y-0.5 pl-3 text-[11px] text-slate-400">
                <li v-for="(g, gi) in h.groups" :key="`bsh-${hi}-${g.chat_id}-${gi}`">
                  <span class="text-slate-200">{{ g.title || g.chat_id }}</span>
                  <span v-if="Number(g.ok) > 0" class="text-emerald-400/90"> · ✓ {{ g.ok }}</span>
                  <span v-if="Number(g.fail) > 0" class="text-rose-300/90"> · ✕ {{ g.fail }}</span>
                </li>
              </ul>
              <p v-else-if="Number(h.bots?.total) > 0" class="mt-1 text-[10px] text-slate-400">
                {{ tt('admin.broadcast_shell.send_history_bots', { ok: Number(h.bots?.ok || 0), n: Number(h.bots?.total || 0) }) }}
              </p>
              <p v-else class="mt-1 text-[10px] text-slate-400">
                {{ tt('admin.broadcast_shell.send_history_summary', { ok: Number(h.recipient_ok || 0), fail: Number(h.recipient_fail || 0) }) }}
              </p>
            </div>
          </div>
        </div>
        <div class="mt-3 rounded-xl border border-slate-700 bg-slate-950/40 p-2">
          <p class="text-xs font-semibold text-slate-300">{{ tt('admin.broadcast_stats.errors_period') }}</p>
          <div class="mt-2 max-h-40 space-y-1 overflow-y-auto">
            <div
              v-for="(er, ei) in bcStatsData.errors"
              :key="`berr-${ei}`"
              class="rounded-lg border border-rose-500/30 bg-rose-950/20 px-2 py-1.5 text-[11px] text-rose-100"
            >
              <p>{{ fmtDateTime(er.created_at) }} · {{ er.target_kind === 'group' ? tt('admin.broadcast_stats.target_group') : tt('admin.broadcast_stats.target_bot') }} {{ er.target_id }}</p>
              <p class="mt-0.5 text-rose-200/90">{{ er.error_message || tt('admin.broadcast_stats.unknown_error') }}</p>
            </div>
            <p v-if="!bcStatsData.errors.length" class="text-[11px] text-slate-500">{{ tt('admin.broadcast_stats.no_errors') }}</p>
          </div>
        </div>
        <p class="mt-3 text-[11px] text-slate-400">
          {{ tt('admin.broadcast_stats.api_note') }}
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
          <button type="button" class="bc-tool-btn" :class="bcStatsPreset === 'today' ? 'bc-tool-active' : ''" @click="applyStatsPreset('today')">{{ tt('admin.broadcast_stats.preset_today') }}</button>
          <button type="button" class="bc-tool-btn" :class="bcStatsPreset === '24h' ? 'bc-tool-active' : ''" @click="applyStatsPreset('24h')">{{ tt('admin.broadcast_stats.preset_24h') }}</button>
          <button type="button" class="bc-tool-btn" :class="bcStatsPreset === '7d' ? 'bc-tool-active' : ''" @click="applyStatsPreset('7d')">{{ tt('admin.broadcast_stats.preset_7d') }}</button>
          <button type="button" class="bc-tool-btn" :class="bcStatsPreset === '30d' ? 'bc-tool-active' : ''" @click="applyStatsPreset('30d')">{{ tt('admin.broadcast_stats.preset_30d') }}</button>
          <button type="button" class="bc-tool-btn" @click="bcStatsPreset=''; bcStatsFrom=''; bcStatsTo=nowLocalInputValue()">{{ tt('admin.broadcast_stats.preset_reset') }}</button>
        </div>
        <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <div>
            <label class="text-xs text-slate-400">{{ tt('admin.broadcast_stats.date_from') }}</label>
            <input
              v-model="bcStatsFrom"
              type="datetime-local"
              class="mt-1 w-full rounded-xl border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-slate-100"
            />
          </div>
          <div>
            <label class="text-xs text-slate-400">{{ tt('admin.broadcast_stats.date_to') }}</label>
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

    <GuardTeleport>
    <div
      v-if="bcAuxModal === 'keyboard'"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:100250;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-center justify-center bg-black/75 p-3 py-6 pt-[max(0.75rem,calc(env(safe-area-inset-top,0px)+52px))] pb-[max(1rem,calc(5rem+env(safe-area-inset-bottom,0px)))] backdrop-blur-sm"
      @click.self="bcAuxModal = ''"
    >
      <div
        class="flex max-h-[min(86vh,34rem)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/[0.1] bg-slate-950/[0.94] shadow-[0_28px_80px_-24px_rgba(0,0,0,0.85)] ring-1 ring-violet-400/20 backdrop-blur-2xl"
        @click.stop
      >
        <div class="flex shrink-0 items-center justify-between border-b border-slate-700/60 p-3">
          <div class="flex min-w-0 items-center gap-2">
            <p class="text-sm font-semibold text-white">{{ tt('admin.broadcast_ui.keyboard_modal_title') }}</p>
            <button
              type="button"
              class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-violet-400/25 bg-violet-950/40 text-[11px] font-bold text-violet-200/90 transition hover:bg-violet-900/50 hover:text-white"
              :title="tt('admin.broadcast_ui.keyboard_info_btn_title')"
              :aria-label="tt('admin.broadcast_ui.keyboard_info_btn_aria')"
              @click="bcKeyboardInfoOpen = true"
            >
              ⓘ
            </button>
          </div>
          <div class="flex items-center gap-2">
            <button type="button" class="bc-tool-btn !px-2.5 !py-1 text-[11px]" :disabled="bcSaving" @click="saveBcAuxKeyboardModal">{{ tt('common.locale_code') === 'en' ? 'Save' : 'Сохранить' }}</button>
            <button type="button" class="bc-tool-btn" @click="bcAuxModal = ''">✕</button>
          </div>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-2 touch-pan-y">
          <div class="mt-0.5 flex flex-wrap items-center gap-2">
            <span class="text-[11px] font-medium text-slate-400">{{ tt('admin.broadcast_ui.keyboard_layout_label') }}</span>
            <button
              type="button"
              class="bc-tool-btn !px-2 !py-1 text-[11px]"
              :class="bcKeyboardLayoutActive === 'inline' ? 'bc-tool-active' : ''"
              @click="bcApplyKeyboardLayoutInline"
            >
              {{ tt('admin.broadcast_ui.keyboard_layout_inline') }}
            </button>
            <button
              type="button"
              class="bc-tool-btn !px-2 !py-1 text-[11px]"
              :class="bcKeyboardLayoutActive === 'stacked' ? 'bc-tool-active' : ''"
              @click="bcApplyKeyboardLayoutStacked"
            >
              {{ tt('admin.broadcast_ui.keyboard_layout_stacked') }}
            </button>
          </div>
          <div
            v-if="bcQuickButtonPreviewRows.length"
            class="mt-2 rounded-lg border border-violet-500/20 bg-violet-950/15 px-2.5 py-2"
          >
            <p class="text-[10px] font-semibold uppercase tracking-wide text-violet-300/80">{{ tt('admin.broadcast_ui.keyboard_layout_preview') }}</p>
            <div class="mt-1.5 space-y-1">
              <div
                v-for="(row, ri) in bcQuickButtonPreviewRows"
                :key="`kb-tg-prev-${ri}`"
                class="flex gap-1"
                :class="bcKeyboardLayoutActive === 'stacked' ? 'flex-col' : 'flex-row flex-wrap'"
              >
                <span
                  v-for="(btn, bi) in row"
                  :key="`kb-tg-prev-${ri}-${bi}`"
                  class="truncate text-[11px]"
                  :class="[
                    bcButtonStyleChipClass(btn.style, btn.kind),
                    bcKeyboardLayoutActive === 'stacked' || row.length === 1 ? 'block w-full' : 'min-w-0 flex-1',
                  ]"
                >
                  {{ btn.text }}
                </span>
              </div>
            </div>
            <p v-if="bcQuickButtonPreview.length < 2" class="mt-1.5 text-[10px] leading-snug text-slate-500">
              {{ tt('admin.broadcast_ui.keyboard_layout_preview_hint') }}
            </p>
          </div>
          <div v-for="(row, ri) in bcButtonRows" :key="`mkb-${ri}`" class="mt-2 space-y-1.5 rounded-lg border border-white/10 bg-black/30 p-2 ring-1 ring-violet-500/15">
            <div class="flex items-center justify-between gap-2">
              <span class="text-xs font-semibold text-slate-400">{{ tt('admin.broadcast_ui.btn_row_label', { n: ri + 1 }) }}</span>
              <button type="button" class="text-xs text-rose-400 hover:text-rose-300" @click="removeBcRow(ri)">{{ tt('admin.broadcast_ui.btn_remove_row') }}</button>
            </div>
            <div
              v-for="(btn, bi) in row"
              :key="`mkbtn-${ri}-${bi}`"
              class="grid grid-cols-1 gap-2 border-t border-slate-700/40 pt-3 text-xs sm:grid-cols-2"
              :class="btn.kind === 'hidden_continuation' ? 'rounded-lg border border-cyan-500/25 bg-cyan-950/20 px-2 pb-2' : btn.kind === 'prefilled_dm' ? 'rounded-lg border border-sky-500/25 bg-sky-950/20 px-2 pb-2' : ''"
            >
              <div v-if="btn.kind === 'hidden_continuation'" class="sm:col-span-2 flex items-center justify-between gap-2">
                <span class="text-[11px] font-semibold uppercase tracking-wide text-cyan-300/90">{{ tt('admin.broadcast_ui.hidden_continuation_badge') }}</span>
              </div>
              <div v-if="btn.kind === 'prefilled_dm'" class="sm:col-span-2 flex items-center justify-between gap-2">
                <span class="text-[11px] font-semibold uppercase tracking-wide text-sky-300/90">{{ tt('admin.broadcast_ui.prefilled_dm_badge') }}</span>
              </div>
              <input
                v-model="btn.text"
                type="text"
                :placeholder="tt('admin.broadcast_ui.btn_text_ph')"
                class="bc-post-input rounded-lg border border-slate-600 bg-slate-900 px-2 py-1.5 sm:col-span-2"
              />
              <label class="flex items-center gap-2 sm:col-span-2">
                <span class="shrink-0 text-slate-400">{{ tt('admin.broadcast_ui.btn_style_label') }}</span>
                <span
                  class="inline-block h-4 w-4 shrink-0 rounded-full"
                  :class="bcButtonStylePreviewClass(btn.style)"
                  aria-hidden="true"
                />
                <select
                  v-model="btn.style"
                  class="min-w-0 flex-1 rounded-lg border border-slate-600 bg-slate-900 px-2 py-1.5 text-slate-100"
                >
                  <option v-for="opt in BC_BUTTON_STYLE_OPTIONS" :key="`bcbst-${opt.id || 'default'}`" :value="opt.id">
                    {{ tt(opt.labelKey) }}
                  </option>
                </select>
              </label>
              <template v-if="btn.kind === 'hidden_continuation'">
                <textarea
                  v-model="btn.non_member_text"
                  rows="3"
                  :placeholder="tt('admin.broadcast_ui.hidden_continuation_non_member_ph')"
                  class="bc-post-input min-h-[4.5rem] resize-y rounded-lg border border-slate-600 bg-slate-900 px-2 py-1.5 sm:col-span-2"
                />
                <p class="text-[10px] text-slate-500 sm:col-span-2">{{ tt('admin.broadcast_ui.hidden_continuation_non_member_hint') }}</p>
                <textarea
                  v-model="btn.member_text"
                  rows="3"
                  :placeholder="tt('admin.broadcast_ui.hidden_continuation_member_ph')"
                  class="bc-post-input min-h-[4.5rem] resize-y rounded-lg border border-slate-600 bg-slate-900 px-2 py-1.5 sm:col-span-2"
                />
                <p class="text-[10px] text-slate-500 sm:col-span-2">{{ tt('admin.broadcast_ui.hidden_continuation_member_hint') }}</p>
              </template>
              <template v-else-if="btn.kind === 'prefilled_dm'">
                <input
                  v-model="btn.dm_username"
                  type="text"
                  :placeholder="tt('admin.broadcast_ui.prefilled_dm_username_ph')"
                  class="bc-post-input rounded-lg border border-slate-600 bg-slate-900 px-2 py-1.5 sm:col-span-2"
                />
                <p class="text-[10px] text-slate-500 sm:col-span-2">{{ tt('admin.broadcast_ui.prefilled_dm_username_hint') }}</p>
                <textarea
                  v-model="btn.dm_prefill_text"
                  rows="3"
                  :placeholder="tt('admin.broadcast_ui.prefilled_dm_text_ph')"
                  class="bc-post-input min-h-[4.5rem] resize-y rounded-lg border border-slate-600 bg-slate-900 px-2 py-1.5 sm:col-span-2"
                />
                <p class="text-[10px] text-slate-500 sm:col-span-2">{{ tt('admin.broadcast_ui.prefilled_dm_text_hint') }}</p>
                <p
                  v-if="bcBuildPrefilledDmUrl(btn.dm_username, btn.dm_prefill_text)"
                  class="break-all text-[10px] text-sky-400/80 sm:col-span-2"
                >
                  {{ bcBuildPrefilledDmUrl(btn.dm_username, btn.dm_prefill_text) }}
                </p>
              </template>
              <template v-else>
                <input
                  v-model="btn.url"
                  type="text"
                  :placeholder="tt('admin.broadcast_ui.btn_url_ph')"
                  class="bc-post-input rounded-lg border border-slate-600 bg-slate-900 px-2 py-1.5"
                />
                <input
                  v-model="btn.web_app_url"
                  type="text"
                  :placeholder="tt('admin.broadcast_ui.btn_webapp_ph')"
                  class="bc-post-input rounded-lg border border-slate-600 bg-slate-900 px-2 py-1.5"
                />
                <input
                  v-model="btn.callback_data"
                  type="text"
                  :placeholder="tt('admin.broadcast_ui.btn_callback_ph')"
                  class="bc-post-input rounded-lg border border-slate-600 bg-slate-900 px-2 py-1.5 sm:col-span-2"
                />
              </template>
              <button type="button" class="text-rose-400 sm:col-span-2" @click="removeBcButton(ri, bi)">{{ tt('admin.broadcast_ui.btn_remove') }}</button>
            </div>
            <div class="flex flex-wrap gap-3 pt-1">
              <button type="button" class="text-xs font-semibold text-violet-400" @click="addBcButton(ri)">{{ tt('admin.broadcast_ui.btn_add_in_row') }}</button>
              <button type="button" class="text-xs font-semibold text-cyan-400" @click="addBcHiddenContinuationButton(ri)">{{ tt('admin.broadcast_ui.hidden_continuation_add') }}</button>
              <button type="button" class="text-xs font-semibold text-sky-400" @click="addBcPrefilledDmButton(ri)">{{ tt('admin.broadcast_ui.prefilled_dm_add') }}</button>
            </div>
          </div>
          <button type="button" class="mt-3 w-full rounded-lg border border-violet-500/40 py-2 text-sm font-semibold text-violet-200" @click="addBcRow">
            {{ tt('admin.broadcast_ui.btn_add_row') }}
          </button>
        </div>
      </div>
      <GuardTeleport>
        <div
          v-if="bcKeyboardInfoOpen"
          style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:101000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.82);padding:16px"
          class="flex items-center justify-center overscroll-none p-3 pt-[max(0.75rem,calc(env(safe-area-inset-top,0px)+52px))] pb-[max(1rem,calc(5rem+env(safe-area-inset-bottom,0px)))] backdrop-blur-sm"
          @click.self="bcKeyboardInfoOpen = false"
        >
          <div
            class="max-h-[min(85vh,28rem)] w-full max-w-md overflow-y-auto overscroll-contain rounded-2xl border border-white/[0.1] bg-slate-950/[0.98] p-4 text-slate-200 shadow-[0_28px_80px_-24px_rgba(0,0,0,0.9)] ring-1 ring-violet-400/25"
            @click.stop
          >
            <div class="mb-3 flex items-center justify-between gap-2">
              <p class="text-sm font-semibold text-white">{{ tt('admin.broadcast_ui.keyboard_info_modal_title') }}</p>
              <button
                type="button"
                class="rounded-lg bg-white/[0.06] px-2 py-1 text-xs text-slate-300 transition hover:bg-white/[0.1]"
                :aria-label="tt('common.close')"
                @click="bcKeyboardInfoOpen = false"
              >
                ✕
              </button>
            </div>
            <div class="space-y-2.5 text-[11px] leading-relaxed text-slate-400">
              <p>{{ tt('admin.broadcast_ui.btn_style_hint') }}</p>
              <p>{{ tt('admin.broadcast_ui.hidden_continuation_hint') }}</p>
              <p>{{ tt('admin.broadcast_ui.prefilled_dm_hint') }}</p>
              <p>{{ tt('admin.broadcast_ui.keyboard_layout_hint') }}</p>
            </div>
          </div>
        </div>
      </GuardTeleport>
    </div>
    </GuardTeleport>

    <GuardTeleport>
    <div
      v-if="bcAuxModal === 'media'"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:100250;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-center justify-center bg-black/75 p-3 py-6 pt-[max(0.75rem,calc(env(safe-area-inset-top,0px)+52px))] pb-[max(1rem,calc(5rem+env(safe-area-inset-bottom,0px)))] backdrop-blur-sm"
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
    </GuardTeleport>

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
          <p class="text-base font-semibold text-zinc-100">{{ tt('admin.autopost.help_modal_title') }}</p>
          <button type="button" class="bc-tool-btn" @click="bcShowAutopostHelp = false">✕</button>
        </div>
        <div class="max-h-[min(60vh,28rem)] space-y-3 overflow-y-auto pr-0.5 text-left text-sm leading-snug text-zinc-400">
          <p class="rounded-lg bg-white/[0.05] px-2.5 py-2 text-zinc-200 backdrop-blur-md">
            {{ tt('admin.autopost.help_p1') }}
          </p>
          <p>{{ tt('admin.autopost.help_p2') }}</p>
          <p class="text-zinc-500">{{ tt('admin.autopost.help_p3') }}</p>
          <p>{{ tt('admin.autopost.help_p4', { max: BC_BROADCAST_MAX_TOKENS }) }}</p>
          <p class="text-[13px] text-zinc-500">{{ tt('admin.autopost.help_p5') }}</p>
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
      v-if="showPartnerGroupsModal"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center bg-black/70 p-3 md:items-center"
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
          <p v-if="!(partnerHourlyData?.chats || []).length" class="py-6 text-center text-[11px] text-slate-500">{{ tt('admin.partner_ui.joins_list_empty') }}</p>
        </div>
      </div>
    </div>

    <div
      v-if="showPartnerJoinsModal"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center bg-black/70 p-3 md:items-center"
      @click.self="showPartnerJoinsModal = false"
    >
      <div
        class="flex h-[min(88vh,calc(100dvh-24px))] max-h-[88vh] w-full max-w-2xl min-h-0 flex-col overflow-hidden rounded-2xl border border-violet-400/50 bg-slate-950 p-4 shadow-2xl"
        @click.stop
      >
        <div class="mb-2 flex shrink-0 items-center justify-between gap-2">
          <div>
            <p class="text-base font-semibold text-white">{{ tt('admin.partner_ui.joins_modal_title') }}</p>
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
            <option value="all">{{ tt('admin.partner_ui.opt_all') }}</option>
            <optgroup v-if="(partnerChatsGrouped.groups || []).length" :label="tt('admin.partner_ui.opt_groups')">
              <option v-for="c in partnerChatsGrouped.groups" :key="`pj-gr-${c.id}`" :value="String(c.id)">{{ c.title }}</option>
            </optgroup>
            <optgroup v-if="(partnerChatsGrouped.channels || []).length" :label="tt('admin.partner_ui.opt_channels')">
              <option v-for="c in partnerChatsGrouped.channels" :key="`pj-ch-${c.id}`" :value="String(c.id)">{{ c.title }}</option>
            </optgroup>
            <optgroup v-if="(partnerChatsGrouped.linked || []).length" :label="tt('admin.partner_ui.opt_linked')">
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
          <p class="text-[11px] text-slate-300">{{ partnerJoinsPeriodSummary }}</p>
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
            {{ tt('admin.partner_ui.more_joins') }}
          </button>
          <button
            type="button"
            class="rounded-md border border-rose-500/50 bg-rose-950/30 px-2 py-1 text-[10px] font-semibold text-rose-100"
            @click="partnerSegmentModalTab = 'spam'; showPartnerSegmentModal = true"
          >
            {{ tt('admin.partner_ui.more_spam') }}
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
            <p>{{ partnerSlotRowMeta(row) }}</p>
          </button>
          <p v-if="!partnerHourlySlots.length" class="py-6 text-center text-[11px] text-slate-500">{{ tt('admin.partner_ui.hourly_empty') }}</p>
        </div>
      </div>
    </div>

    <div
      v-if="showPartnerSegmentModal"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center bg-black/70 p-3 md:items-center"
      @click.self="showPartnerSegmentModal = false"
    >
      <div class="w-full max-w-sm rounded-2xl border border-violet-400/50 bg-slate-950 p-4 shadow-2xl">
        <div class="mb-2 flex items-center justify-between">
          <p class="text-sm font-semibold text-white">{{ partnerSegmentModalTitle }}</p>
          <button type="button" class="bc-tool-btn" @click="showPartnerSegmentModal = false">✕</button>
        </div>
        <div v-if="partnerSegmentModalTab === 'joins'" class="space-y-1 text-[11px] text-slate-200">
          <p>{{ tt('admin.partner_ui.seg_join_channel_disc', { n: Number(partnerHourlyData?.segment_joins?.channel || 0) }) }}</p>
          <p>{{ tt('admin.partner_ui.seg_join_group', { n: Number(partnerHourlyData?.segment_joins?.group || 0) }) }}</p>
          <p>{{ tt('admin.partner_ui.seg_join_linked', { n: Number(partnerHourlyData?.segment_joins?.linked_group || 0) }) }}</p>
        </div>
        <div v-else class="space-y-1 text-[11px] text-slate-200">
          <p>{{ tt('admin.partner_ui.seg_spam_channel', { n: Number(partnerHourlyData?.segment_spam?.channel || 0) }) }}</p>
          <p>{{ tt('admin.partner_ui.seg_spam_group', { n: Number(partnerHourlyData?.segment_spam?.group || 0) }) }}</p>
          <p>{{ tt('admin.partner_ui.seg_spam_linked', { n: Number(partnerHourlyData?.segment_spam?.linked_group || 0) }) }}</p>
        </div>
      </div>
    </div>

    <div
      v-if="showPartnerSlotDetailModal"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center bg-black/70 p-3 md:items-center"
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
        <div v-if="partnerSlotDetailLoading" class="shrink-0 py-6 text-center text-xs text-slate-400">{{ tt('admin.partner_ui.slot_detail_loading') }}</div>
        <div v-else class="min-h-0 flex-1 touch-pan-y space-y-2 overflow-y-auto overscroll-y-contain pr-1 text-[11px] text-slate-200">
          <p class="font-semibold text-cyan-200/90">{{ tt('admin.partner_ui.slot_detail_joined') }}</p>
          <div v-for="(j, ji) in (partnerSlotDetailData?.joins || [])" :key="`jd-${ji}-${j.user_id}`" class="rounded border border-slate-700/80 bg-slate-900/60 px-2 py-1">
            {{ j.joined_at }} · {{ tt('admin.partner_ui.slot_detail_chat', { title: j.chat_title }) }} ·
            <a
              v-if="partnerUserHref(j)"
              href="#"
              class="text-sky-300 underline decoration-sky-500/50 underline-offset-2 hover:text-sky-200"
              @click.prevent.stop="openExternalLink(partnerUserHref(j))"
            >{{ partnerUserLabel(j) }}</a>
            <span v-else>{{ partnerUserLabel(j) }}</span>
          </div>
          <p v-if="!(partnerSlotDetailData?.joins || []).length" class="text-slate-500">{{ tt('admin.partner_ui.slot_detail_no_joins') }}</p>
          <p class="font-semibold text-amber-200/90">{{ tt('admin.partner_ui.slot_detail_moderation') }}</p>
          <div v-for="(m, mi) in partnerSlotDetailModerationDisplay" :key="`md-${mi}-${m.user_id}`" class="rounded border border-slate-700/80 bg-slate-900/60 px-2 py-1">
            {{ m.created_at }} · {{ partnerActionLabel(m.action) }} · {{ partnerReasonLabel(m.reason) }} ·
            <a
              v-if="partnerUserHref(m)"
              href="#"
              class="text-sky-300 underline decoration-sky-500/50 underline-offset-2 hover:text-sky-200"
              @click.prevent.stop="openExternalLink(partnerUserHref(m))"
            >{{ partnerUserLabel(m) }}</a>
            <span v-else>{{ partnerUserLabel(m) }}</span>
          </div>
          <p v-if="!partnerSlotDetailModerationDisplay.length" class="text-slate-500">{{ tt('admin.partner_ui.slot_detail_no_moderation') }}</p>
        </div>
      </div>
    </div>

    <div
      v-if="showPartnerHourlyModal"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center overflow-y-auto overscroll-contain bg-black/70 p-3 pt-[max(1rem,calc(env(safe-area-inset-top,0px)+88px))] pb-[max(1rem,calc(5.5rem+env(safe-area-inset-bottom,0px)))] md:items-center"
      @click.self="showPartnerHourlyModal = false"
    >
      <div
        class="flex h-[min(86vh,calc(100dvh-168px))] max-h-[86vh] w-full max-w-3xl min-h-0 flex-col overflow-hidden rounded-2xl border border-indigo-400/50 bg-slate-950 p-4 shadow-2xl md:h-[min(88vh,calc(100dvh-120px))]"
        @click.stop
      >
        <div class="mb-2 flex shrink-0 items-center justify-between gap-2">
          <div>
            <p class="text-base font-semibold text-white">{{ tt('admin.partner_ui.activity_modal_title') }}</p>
            <p v-if="partnerActivityPeriodLine" class="text-[10px] text-indigo-200/80">{{ partnerActivityPeriodLine }}</p>
          </div>
          <button type="button" class="bc-tool-btn" @click="showPartnerHourlyModal = false">✕</button>
        </div>
        <div class="relative mb-2 shrink-0 rounded-xl border border-slate-700/80 bg-slate-900/60 p-2 pr-11">
          <p class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-300">{{ tt('admin.partner_ui.chat_pick_label') }}</p>
          <button
            type="button"
            class="w-full rounded-lg border border-indigo-400/45 bg-indigo-500/15 px-3 py-2 text-left text-xs font-semibold text-indigo-100 hover:bg-indigo-500/25"
            @click="showPartnerHourlyChatPicker = true"
          >
            {{ partnerSelectedChatMeta?.title || tt('admin.partner_ui.all_connected') }}
            <span class="ml-2 text-[10px] text-indigo-200/80">{{ tt('admin.partner_ui.tap_to_select') }}</span>
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
          <div v-if="partnerHourlyLoading" class="py-8 text-center text-sm text-slate-400">{{ tt('common.loading') }}</div>
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
                  <p class="text-4xl font-extrabold leading-none text-emerald-300">{{ partnerAudienceGender.malePct }}%</p>
                  <p class="text-[12px] text-slate-300">мужчины</p>
                </div>
                <div class="text-right">
                  <p class="text-4xl font-extrabold leading-none text-sky-300">{{ partnerAudienceGender.femalePct }}%</p>
                  <p class="text-[12px] text-slate-300">женщины</p>
                </div>
              </div>
              <div class="mt-3 h-8 overflow-hidden rounded-lg border border-slate-600 bg-slate-950/60">
                <div class="flex h-full w-full">
                  <div class="h-full bg-emerald-500/80" :style="{ width: `${partnerAudienceGender.malePct}%` }" />
                  <div class="h-full bg-sky-500/80" :style="{ width: `${partnerAudienceGender.femalePct}%` }" />
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
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-center justify-center overflow-y-auto overscroll-contain bg-black/75 p-3 pt-[max(1rem,calc(env(safe-area-inset-top,0px)+88px))] pb-[max(1rem,calc(5.5rem+env(safe-area-inset-bottom,0px)))] backdrop-blur-sm"
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

    <GuardTeleport guard-to="body">
      <div
        v-if="bcSendModalOpen"
        class="fixed inset-0 z-[100010] flex min-h-[100dvh] min-w-0 flex-col bg-[#0b0d14] pb-[env(safe-area-inset-bottom,0px)] pt-[max(0.25rem,calc(env(safe-area-inset-top,0px)+48px))]"
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
                <span
                  class="pointer-events-none absolute left-1/2 top-1/2 h-[168px] w-[168px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/[0.06] shadow-[inset_0_0_0_6px_rgba(15,23,42,0.5),inset_0_10px_20px_rgba(15,23,42,0.55),inset_0_-8px_18px_rgba(2,6,23,0.8)]"
                  aria-hidden="true"
                />
                <svg
                  class="pointer-events-none absolute left-0 top-0 h-[180px] w-[180px] -rotate-90 drop-shadow-[0_0_12px_rgba(99,102,241,0.4)]"
                  viewBox="0 0 120 120"
                  aria-hidden="true"
                >
                  <defs>
                    <linearGradient id="bcSendNeonRing" x1="0%" y1="30%" x2="100%" y2="100%">
                      <stop offset="0%" stop-color="#7c83ff" />
                      <stop offset="52%" stop-color="#6366f1" />
                      <stop offset="100%" stop-color="#7c3aed" />
                    </linearGradient>
                  </defs>
                  <circle cx="60" cy="60" r="52" fill="none" stroke="rgba(148,163,184,0.12)" stroke-width="8" />
                  <circle cx="60" cy="60" r="52" fill="none" stroke="rgba(2,6,23,0.5)" stroke-width="10" />
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
                  class="absolute -bottom-1 right-[-2.3rem] text-[22px] font-semibold tabular-nums tracking-tight text-white drop-shadow-[0_2px_8px_rgba(0,0,0,0.65)]"
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
          class="relative mx-auto flex w-full max-w-[22rem] flex-col overflow-hidden px-4 pb-5 pt-2"
        >
          <p class="text-[16px] font-semibold leading-snug text-white">Рассылка отправлена!</p>
          <div class="mt-3 flex flex-col items-center">
            <div
              class="flex h-[76px] w-[76px] items-center justify-center rounded-full bg-emerald-500/18 shadow-[0_0_36px_-10px_rgba(52,211,153,0.65)] ring-2 ring-emerald-400/35"
            >
              <span class="text-3xl leading-none text-emerald-300">✓</span>
            </div>
            <p class="mt-2 text-[12px] text-slate-400">{{ bcSendCompletedAtLabel }}</p>
          </div>

          <p v-if="bcSendResultLoading" class="mt-4 text-center text-xs text-slate-400">{{ tt('admin.broadcast_shell.stats_loading') }}</p>
          <template v-else-if="bcSendResultSnapshot">
            <p
              v-if="bcSendResultSnapshot.broadcast_url_tracking_configured === false"
              class="mt-3 rounded-lg border border-amber-500/25 bg-amber-500/8 px-2 py-1 text-[10px] leading-snug text-amber-100/90"
            >
              {{ tt('admin.broadcast_shell.tracking_off_hint') }}
            </p>
            <div class="mt-3 rounded-xl border border-white/10 bg-[#11151C] p-2.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
              <div class="grid grid-cols-2 gap-x-2 gap-y-0.5">
                <div>
                  <p class="text-[9px] font-semibold uppercase tracking-wide text-slate-500">{{ tt('admin.bc_campaign.metric_delivered') }}</p>
                  <p class="text-[17px] font-bold tabular-nums leading-tight text-white">{{ fmtIntSpace(bcSendDeliveredOk) }}</p>
                </div>
                <div>
                  <p class="text-[9px] font-semibold uppercase tracking-wide text-slate-500">
                    <abbr :title="tt('admin.broadcast_shell.ctr_hint_title')" class="cursor-help underline decoration-dotted decoration-slate-500 underline-offset-2">{{
                      tt('admin.broadcast_shell.ctr_abbr')
                    }}</abbr>
                  </p>
                  <p class="text-[17px] font-bold tabular-nums leading-tight text-emerald-300">{{ fmtPctTrim(bcSendCtrPct) }}</p>
                  <p class="mt-0.5 text-[9px] leading-tight text-slate-500">{{ bcSendStatCtrSub }}</p>
                </div>
              </div>
              <div class="mt-2 border-t border-white/[0.06] pt-2">
                <div class="flex flex-wrap gap-x-3 gap-y-1 text-[11px] tabular-nums text-slate-200">
                  <span
                    ><span class="text-slate-500">{{ tt('admin.bc_campaign.metric_reactions') }}</span>
                    {{ fmtIntSpace(bcSendDoneReactions) }}</span
                  >
                  <span
                    ><span class="text-slate-500">{{ tt('admin.bc_campaign.metric_link_clicks') }}</span>
                    {{ fmtIntSpace(Number(bcSendResultSnapshot.real_link_clicks_total || 0)) }}</span
                  >
                  <span
                    ><span class="text-slate-500">{{ tt('admin.bc_campaign.metric_button_clicks') }}</span>
                    {{ fmtIntSpace(Number(bcSendResultSnapshot.real_callback_clicks_total || 0)) }}</span
                  >
                </div>
              </div>
            </div>
          </template>

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
          <p class="mt-3 text-sm leading-relaxed text-slate-200">{{ bcSendModalText || tt('admin.dlg.bc_run_failed') }}</p>
          <button
            type="button"
            class="mt-5 w-full rounded-xl border border-white/[0.08] bg-white/[0.06] py-3 text-sm font-semibold text-white hover:bg-white/[0.09]"
            @click="closeBcSendModal"
          >
            Закрыть
          </button>
        </div>
      </div>
    </GuardTeleport>

    <GuardTeleport guard-to="body">
    <div
      v-if="bcMediaViewerOpen && bcMediaViewerItem"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:100260;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-center justify-center bg-black/88 p-3 pt-[max(0.5rem,calc(env(safe-area-inset-top,0px)+48px))] pb-[max(0.75rem,calc(4.5rem+env(safe-area-inset-bottom,0px)))] backdrop-blur-md"
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
    </GuardTeleport>

    <GuardTeleport>
    <div
      v-if="bcShowGroupsPicker"
          class="fixed inset-0 z-[95450] flex items-center justify-center bg-black/75 p-3 py-6 pt-[max(0.75rem,calc(env(safe-area-inset-top,0px)+52px))] pb-[max(1rem,calc(5rem+env(safe-area-inset-bottom,0px)))] backdrop-blur-sm"
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
            <span class="text-slate-300">Выбрано: {{ bcSelectedGroupIds.length }}</span>
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
            <span class="min-w-0 flex-1 text-sm text-slate-200">{{ c.title || c.username || bcNormalizeChatId(c) }}</span>
            <span
              v-if="c.is_paused && !bcCurrentBroadcastIsOneshot"
              class="shrink-0 rounded-md border border-amber-400/35 bg-amber-500/15 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-amber-200"
            >
              {{ tt('admin.broadcast_shell.group_paused_badge') }}
            </span>
          </label>
          <p v-if="!bcFilteredGroups.length" class="px-2 py-3 text-center text-xs text-slate-500">Нет подходящих групп</p>
        </div>
        <div class="shrink-0 border-t border-slate-700/60 p-4 pt-3">
          <button type="button" class="w-full rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white" @click="sendBcToSelectedGroups">Выбрать</button>
        </div>
      </div>
    </div>
    </GuardTeleport>

    <GuardTeleport>
    <div
      v-if="bcShowChannelsPicker"
      class="fixed inset-0 z-[95450] flex items-center justify-center bg-black/75 p-3 py-6 pt-[max(0.75rem,calc(env(safe-area-inset-top,0px)+52px))] pb-[max(1rem,calc(5rem+env(safe-area-inset-bottom,0px)))] backdrop-blur-sm"
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
            <span class="text-slate-300">Выбрано: {{ bcSelectedChannelIds.length }}</span>
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
    </GuardTeleport>

    <GuardTeleport>
    <div
      v-if="bcShowBotsPicker"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-center justify-center bg-black/75 p-3 py-6 pt-[max(0.75rem,calc(env(safe-area-inset-top,0px)+52px))] pb-[max(1rem,calc(5rem+env(safe-area-inset-bottom,0px)))] backdrop-blur-sm"
      @click.self="bcShowBotsPicker = false"
    >
      <div
        class="flex max-h-[min(88vh,32rem)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/[0.1] bg-slate-950/[0.94] shadow-[0_28px_80px_-24px_rgba(0,0,0,0.85)] ring-1 ring-indigo-400/25 backdrop-blur-2xl"
        @click.stop
      >
        <div class="shrink-0 border-b border-slate-700/60 p-4 pb-2">
          <div class="flex items-center justify-between">
            <p class="text-[26px] font-black text-white leading-none">{{ tt('admin.partner_ui.bots_modal_title') }}</p>
            <button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-transparent text-sm text-white/90 hover:bg-white/[0.08]" @click="bcShowBotsPicker = false">✕</button>
          </div>
          <p class="mt-2 text-[14px] text-slate-300">{{ tt('admin.partner_ui.bots_modal_sub') }}</p>
          <div class="mt-2 flex items-center justify-between gap-2 text-[14px]">
            <span class="text-slate-300">{{ tt('admin.partner_ui.bots_selected', { n: bcSelectedBotRecipientIds.length }) }}</span>
            <div class="flex items-center gap-3">
              <button type="button" class="font-semibold text-indigo-300" @click="bcSelectedBotRecipientIds = bcBotRecipients.map((x) => Number(x.id))">{{ tt('admin.partner_ui.bots_select_all') }}</button>
              <button type="button" class="font-semibold text-indigo-300" @click="bcSelectedBotRecipientIds = []">{{ tt('admin.partner_ui.bots_clear') }}</button>
            </div>
          </div>
          <input
            v-model="bcBotsSearch"
            type="text"
            :placeholder="tt('admin.partner_ui.bots_search_ph')"
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
            <span class="text-sm text-slate-200">{{ bcBotRowTitle(b) }}</span>
          </label>
          <p v-if="!bcFilteredBots.length" class="px-2 py-3 text-center text-xs text-slate-500">{{ tt('admin.partner_ui.bots_empty') }}</p>
        </div>
        <div class="shrink-0 border-t border-slate-700/60 p-4 pt-3">
          <button type="button" class="w-full rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white" @click="chooseBotRecipients">{{ tt('admin.partner_ui.bots_choose') }}</button>
        </div>
      </div>
    </div>
    </GuardTeleport>

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
              class="bc-html-preview max-h-[50vh] overflow-y-auto text-sm leading-relaxed text-zinc-100 whitespace-pre-wrap"
              v-html="bcPreviewItem.body_text || 'Без текста'"
            />
          </div>
          <div v-if="previewKeyboardRows(bcPreviewItem).length" class="mt-3 space-y-1">
            <p class="text-xs text-zinc-500">Кнопки из поста:</p>
            <div v-for="(row, ri) in previewKeyboardRows(bcPreviewItem)" :key="`pv-row-${ri}`" class="flex flex-wrap gap-1">
              <span
                v-for="(btn, bi) in row"
                :key="`pv-btn-${ri}-${bi}`"
                :class="bcButtonStyleChipClass(btn.style, btn.hidden_continuation ? 'hidden_continuation' : '')"
              >
                {{ btn.text }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <GuardTeleport guard-to="body">
      <div
        v-if="bcEditModalOpen"
        class="fixed inset-0 z-[100260] flex items-start justify-center bg-black/60 p-3 pt-[max(0.75rem,calc(env(safe-area-inset-top,0px)+12px))] pb-[env(safe-area-inset-bottom,0px)] md:items-center"
        @click.self="bcEditModalOpen = false"
      >
      <div class="w-full max-w-2xl rounded-2xl border border-emerald-400/35 bg-slate-900 p-4 shadow-2xl" @click.stop>
        <div class="mb-2 flex items-center justify-between">
          <p class="text-base font-semibold text-white">{{ tt('admin.broadcast_ui.edit_post_title') }}</p>
          <button type="button" class="bc-tool-btn" @click="bcEditModalOpen = false">✕</button>
        </div>
        <input
          v-model="bcEditTitle"
          type="text"
          class="bc-post-input w-full rounded-xl border border-slate-600 bg-slate-950 px-3 py-2 text-sm"
          :placeholder="tt('admin.broadcast_ui.draft_title_ph')"
        />
        <div class="mt-2 flex flex-wrap gap-1">
          <button type="button" class="bc-tool-btn" @mousedown.prevent @click="bcFormatBold"><b>Ж</b></button>
          <button type="button" class="bc-tool-btn" @mousedown.prevent @click="bcFormatItalic"><i>К</i></button>
          <button type="button" class="bc-tool-btn" @mousedown.prevent @click="bcFormatUnderline"><u>Ч</u></button>
          <button type="button" class="bc-tool-btn" @mousedown.prevent @click="bcFormatStrike"><s>З</s></button>
          <button type="button" class="bc-tool-btn" :class="bcFormatState.quote ? 'bc-tool-active' : ''" @mousedown.prevent @click="bcFormatBlockquote">❝ {{ tt('admin.bc_campaign.fmt_quote') }}</button>
          <button type="button" class="bc-tool-btn" @mousedown.prevent @click="bcFormatSpoiler">🙈 {{ tt('admin.bc_campaign.fmt_spoiler') }}</button>
          <button type="button" class="bc-tool-btn" @mousedown.prevent @click="bcFormatLink">🔗 {{ tt('admin.bc_campaign.fmt_link') }}</button>
          <button type="button" class="bc-tool-btn font-mono text-[11px]" title="Моноширинный блок" @mousedown.prevent @click="bcFormatPre">⌨ {{ tt('admin.bc_campaign.fmt_mono_short') }}</button>
          <button type="button" class="bc-tool-btn text-[11px]" :class="!bcCanUndo() ? 'opacity-40' : ''" :disabled="!bcCanUndo()" @mousedown.prevent @click="bcUndo">↶ {{ tt('admin.bc_campaign.history_back') }}</button>
          <button type="button" class="bc-tool-btn text-[11px]" :class="!bcCanRedo() ? 'opacity-40' : ''" :disabled="!bcCanRedo()" @mousedown.prevent @click="bcRedo">↷ {{ tt('admin.bc_campaign.history_forward') }}</button>
          <button type="button" class="bc-tool-btn" @mousedown.prevent @click="bcToggleEmojiOpen">😀</button>
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
          :data-placeholder="tt('admin.broadcast_ui.message_body_ph')"
          @input="onBcEditInput"
          @paste="bcOnEditorPaste"
          @keydown="bcOnEditorKeydown"
          @click="onBcEditorClick"
          @mouseup="bcUpdateFormatState"
          @keyup="bcUpdateFormatState"
        />
        <div class="mt-3 flex gap-2">
          <button type="button" class="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white" :disabled="bcSaving" @click="saveBcEditModal">{{ tt('common.save') }}</button>
          <button type="button" class="bc-tool-btn" @click="bcEditModalOpen = false">{{ tt('common.close') }}</button>
        </div>
      </div>
      </div>
    </GuardTeleport>

    <GuardTeleport guard-to="body">
      <div
        v-if="bcLinkModalOpen"
        class="fixed inset-0 z-[100270] flex items-center justify-center bg-black/65 p-4 backdrop-blur-sm pt-[max(0.75rem,calc(env(safe-area-inset-top,0px)+12px))] pb-[env(safe-area-inset-bottom,0px)]"
        @click.self="bcLinkModalOpen = false"
      >
      <div class="w-full max-w-md rounded-2xl border border-violet-400/50 bg-slate-900 p-4 shadow-2xl" @click.stop>
        <div class="mb-2 flex items-center justify-between">
          <p class="text-base font-semibold text-white">{{ tt('admin.broadcast_ui.link_modal_title') }}</p>
          <button type="button" class="bc-tool-btn" @click="bcLinkModalOpen = false">✕</button>
        </div>
        <input
          v-model="bcLinkUrl"
          type="text"
          placeholder="https://..."
          class="bc-post-input w-full rounded-xl border border-slate-600 bg-slate-950 px-3 py-2 text-sm"
        />
        <div class="mt-3 flex gap-2">
          <button type="button" class="rounded-xl bg-violet-600 px-4 py-2 text-sm font-semibold text-white" @click="bcApplyLinkModal">{{ tt('common.apply') }}</button>
          <button type="button" class="bc-tool-btn" @click="bcLinkModalOpen = false">{{ tt('common.close') }}</button>
        </div>
      </div>
      </div>
    </GuardTeleport>

    <GuardTeleport guard-to="body">
      <div
        v-if="bcEditorHintOpen"
        class="fixed inset-0 z-[100275] flex items-center justify-center bg-black/60 p-4 pt-[max(0.75rem,calc(env(safe-area-inset-top,0px)+12px))] pb-[env(safe-area-inset-bottom,0px)]"
        @click.self="bcEditorHintOpen = false"
      >
        <div class="w-full max-w-sm rounded-2xl border border-amber-400/45 bg-[#161b26] p-4 shadow-2xl ring-1 ring-white/10" @click.stop>
          <p class="text-sm leading-snug text-zinc-100">{{ bcEditorHintText }}</p>
          <button type="button" class="bc-tool-btn mt-4 w-full !py-2.5 font-semibold" @click="bcEditorHintOpen = false">{{ tt('common.close') }}</button>
        </div>
      </div>
    </GuardTeleport>

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

  <GuardTeleport guard-to="body">
  <SecurityPinGateModal
    :open="pinGateOpen"
    :busy="pinGateBusy"
    :error="pinGateError"
    :model-value="pinGateInput"
    @update:model-value="pinGateInput = $event"
    @submit="submitPinGate"
    @cancel="cancelPinGate"
  />
  </GuardTeleport>
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
@keyframes bc-shake-x {
  0%,
  100% {
    transform: translateX(0);
  }
  18% {
    transform: translateX(-6px);
  }
  36% {
    transform: translateX(6px);
  }
  54% {
    transform: translateX(-4px);
  }
  72% {
    transform: translateX(4px);
  }
}
.bc-shake-x {
  animation: bc-shake-x 0.42s ease-out;
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
.bc-editor :deep(u) {
  text-decoration: underline !important;
  text-decoration-color: rgba(226, 232, 240, 0.9);
  text-underline-offset: 2px;
}
.bc-editor:empty:before {
  content: attr(data-placeholder);
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
.bc-editor :deep(a),
.bc-editor :deep(a:any-link),
.bc-editor :deep(a:-webkit-any-link),
.bc-html-preview :deep(a),
.bc-html-preview :deep(a:any-link),
.bc-html-preview :deep(a:-webkit-any-link) {
  color: #60a5fa !important;
  -webkit-text-fill-color: #60a5fa;
  text-decoration: none !important;
  text-decoration-line: none !important;
  -webkit-text-decoration: none !important;
}
.bc-editor :deep(a:hover),
.bc-html-preview :deep(a:hover) {
  color: #93c5fd !important;
  -webkit-text-fill-color: #93c5fd;
}
.bc-editor :deep(a u),
.bc-editor :deep(a ins),
.bc-html-preview :deep(a u),
.bc-html-preview :deep(a ins) {
  text-decoration: none !important;
  text-decoration-line: none !important;
}
.bc-editor :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 0.92em;
  padding: 0.05rem 0.25rem;
  border-radius: 0.25rem;
  background: rgba(148, 163, 184, 0.14);
  color: #e2e8f0 !important;
  -webkit-text-fill-color: #e2e8f0;
  white-space: pre-wrap;
  word-break: break-word;
}
.bc-editor :deep(pre) {
  display: block;
  max-width: 100%;
  box-sizing: border-box;
  margin: 0.35rem 0;
  padding: 0.35rem 0.5rem;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 0.92em;
  border-radius: 0.35rem;
  background: rgba(148, 163, 184, 0.12);
  color: #e2e8f0 !important;
  -webkit-text-fill-color: #e2e8f0;
}
.bc-editor :deep(blockquote) {
  display: block;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  margin: 0.35rem 0;
  padding: 0.35rem 1.35rem 0.35rem 0.65rem;
  border-left: 3px solid rgba(56, 189, 248, 0.88);
  background: rgba(59, 130, 246, 0.12);
  border-radius: 0.4rem;
  position: relative;
  color: #e2e8f0 !important;
  -webkit-text-fill-color: #e2e8f0;
}
.bc-editor :deep(blockquote)::after {
  content: '\201d';
  position: absolute;
  top: 0.12rem;
  right: 0.38rem;
  font-size: 0.95rem;
  line-height: 1;
  font-weight: 600;
  color: rgba(56, 189, 248, 0.72);
  pointer-events: none;
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
.hide-num-spin {
  appearance: textfield;
  -moz-appearance: textfield;
}
.hide-num-spin::-webkit-outer-spin-button,
.hide-num-spin::-webkit-inner-spin-button {
  margin: 0;
  appearance: none;
  -webkit-appearance: none;
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

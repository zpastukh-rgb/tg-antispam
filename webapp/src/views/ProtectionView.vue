<script setup>
import { ref, onMounted, onBeforeUnmount, computed, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useApi } from '../composables/useApi'
import { useToast } from '../composables/useToast'
import { guardLog, guardWarn } from '../utils/guardDebugLog'
import { useCabinetMode } from '../composables/useCabinetMode'
import {
  uploadChatWelcomePhoto,
  fetchChatWelcomePhotoPreviewUrl,
  revokeBroadcastMediaPreviewUrl,
  uploadChatRulesPhoto,
  fetchChatRulesPhotoPreviewUrl,
  deleteChatRulesPhoto,
} from '../api/client'
import { normalizeHtmlForTelegram } from '../utils/telegramHtmlForTg'
import {
  isTwoFaPinRequiredForAction,
  verifyPinDigits,
  SECURITY_ACTION_MASTER_PROTECTION_OFF,
} from '../composables/useSecurityTwoFa'
import {
  shouldAskPinForAction,
  shouldConfirmForAction,
  verifyPin,
  loadPinHash,
} from '../utils/settingsSecurity'

const router = useRouter()
const route = useRoute()
const { api, error, fetchSilent, hasInitData } = useApi()
const { cabinetMode, setCabinetMode } = useCabinetMode()
/** Смена чата без глобального loading (иначе весь экран «мигает») */
const switchChatBusy = ref(false)
const { showToast } = useToast()
const chat = ref(null)
const selectedChatId = ref(null)
const showChatPicker = ref(false)
const saving = ref(false)
const newStopword = ref('')
const stopwordLoading = ref(false)
const showStopwordsModal = ref(false)
const showLinksFilterModal = ref(false)
const showMentionsFilterModal = ref(false)
const showMediaFilterModal = ref(false)
const showButtonsFilterModal = ref(false)
const showChannelPostsFilterModal = ref(false)
const newWhitelistDomain = ref('')
const newWhitelistUserId = ref('')
const newWhitelistSenderChat = ref('')
const whitelistLoading = ref(false)
const newLinkBlacklistPattern = ref('')
const linkBlacklistLoading = ref(false)
const openLinkModeHint = ref(null)
const showMainInfoModal = ref(false)
const showChatSwitchInfoModal = ref(false)
const showFiltersInfoModal = ref(false)
const showSilenceInfoModal = ref(false)
const showSilencePickerModal = ref(false)
const showStopwordsInfoModal = ref(false)
const showReputationInfoModal = ref(false)
const showReputationSettingsModal = ref(false)
const showReputationWordsModal = ref(false)
const showReputationTopModal = ref(false)
const showHardDictInfoModal = ref(false)
const showCleanupInfoModal = ref(false)
const showAntinakrutkaInfoModal = ref(false)
const showAntinakrutkaSettingsModal = ref(false)
const showNewbieInfoModal = ref(false)
const showAntispamInfoModal = ref(false)
const showAntispamListModal = ref(false)
const showPublicAlertsHelpModal = ref(false)
/** Модалка «Ограничения Free» при попытке открыть Premium-функции без подписки */
const showFreeLimitsPremiumModal = ref(false)
const showPublicAlertsStyleHelpModal = ref(false)
const showPublicAlertsSettingsModal = ref(false)
const showGuardianPeriodicHelpModal = ref(false)
const showJoinCaptchaInfoModal = ref(false)
const showJoinCaptchaSettingsModal = ref(false)
const showSpamSpikeSettingsModal = ref(false)
const showSpamSpikeInfoModal = ref(false)
const showWelcomeSettingsModal = ref(false)
const showPostRulesSettingsModal = ref(false)
const postRulesGroupInfoOpen = ref(false)
const postRulesSendBusy = ref(false)
const postRulesBusy = ref(false)
const postRulesGroupPreviewUrl = ref('')
const postRulesDraftLoadingId = ref('')
const postRulesImagePreviewUrl = ref('')
const postRulesSaveBusy = ref(false)
const postRulesActiveDraftId = ref('')
const postRulesDraftNameDraft = ref('')
const postRulesDraftNameEditId = ref('')
const postRulesDraftNameDirty = ref(false)
const postRulesServerDirty = ref(false)
const postRulesShowSaved = ref(false)
let postRulesSavedFlashTimer = null
const postRulesGroupRunActiveId = ref('')
const postRulesGroupRunDraftBusyId = ref('')
const showPostRulesGroupSendModal = ref(false)
const postRulesGroupSendPickId = ref('')
const postRulesGroupFullPreviewRow = ref(null)
const showPostRulesGroupFullPreview = ref(false)
const showPostRulesButtonsModal = ref(false)
const postRulesLinkModalOpen = ref(false)
const postRulesLinkUrl = ref('https://')
const postRulesLinkRange = ref(null)
const showWelcomeButtonsModal = ref(false)
const welcomeBodyRef = ref(null)
const welcomeBodyHtml = ref('')
const welcomeFormatState = ref({ bold: false, italic: false, underline: false, strike: false, spoiler: false, link: false })
const welcomeLinkModalOpen = ref(false)
const welcomeLinkUrl = ref('https://')
const welcomeLinkRange = ref(null)
const welcomeSavedRange = ref(null)
const welcomeButtonRows = ref([[{ text: '', url: '', web_app_url: '', callback_data: '' }]])
const postRulesGroupButtonRows = ref([[{ text: '', url: '', web_app_url: '', callback_data: '' }]])
const postRulesBodyRef = ref(null)
const postRulesHistory = ref([])
const postRulesHistoryIndex = ref(-1)
const postRulesSavedRange = ref(null)
const postRulesFormatState = ref({ bold: false, italic: false, underline: false, strike: false })
const welcomeHistory = ref([])
const welcomeHistoryIndex = ref(-1)
const chatsList = ref([])
const chatsListLoading = ref(true)
const spikeAlertsByChat = ref({})
const antispamItems = ref([])
const reputationWords = ref([])
const reputationDefaultWords = ref([])
const reputationTop = ref([])
const reputationMyScore = ref(0)
const reputationLoading = ref(false)
const reputationWordsLoading = ref(false)
const newReputationWord = ref('')
const antispamLoading = ref(false)
const newAntispamUserId = ref('')
const copyTargetId = ref(null)
const copyLoading = ref(false)
const cleanLaunchLoading = ref(false)
const isPremium = ref(false)
const pickerToggleBusyByChat = ref({})
const showProtectionPinModal = ref(false)
const protectionPinInput = ref('')
const protectionPinError = ref('')
/** Telegram ID для проверки PIN из «Настройки → Безопасность» (хэш в localStorage) */
const viewerTelegramId = ref(0)
let protectionPinResolver = null

function requestProtectionPin() {
  return new Promise((resolve) => {
    protectionPinResolver = resolve
    protectionPinInput.value = ''
    protectionPinError.value = ''
    showProtectionPinModal.value = true
  })
}
async function submitProtectionPin() {
  const pin = String(protectionPinInput.value || '').replace(/\D/g, '').slice(0, 4)
  if (pin.length !== 4) {
    protectionPinError.value = 'Введите 4 цифры'
    return
  }
  const tid = Number(viewerTelegramId.value || 0)
  const storedHash = loadPinHash()
  let ok = false
  if (storedHash && tid) {
    try {
      ok = await verifyPin(tid, pin, storedHash)
    } catch {
      ok = false
    }
  }
  if (!ok) ok = verifyPinDigits(protectionPinInput.value)
  if (!ok) {
    protectionPinError.value = 'Неверный код'
    return
  }
  showProtectionPinModal.value = false
  const r = protectionPinResolver
  protectionPinResolver = null
  r?.(true)
}
function cancelProtectionPin() {
  showProtectionPinModal.value = false
  const r = protectionPinResolver
  protectionPinResolver = null
  r?.(false)
}

function masterOffConfirmMessage(chatTitle) {
  return `Выключить защиту только в чате «${chatTitle}»?\n\nНастройки сохранятся, но Guard перестанет модерировать этот чат, пока вы снова не включите защиту.`
}

async function ensureCanTurnMasterOff(chatTitle) {
  const needPin =
    shouldAskPinForAction('protection_settings') || isTwoFaPinRequiredForAction(SECURITY_ACTION_MASTER_PROTECTION_OFF)
  if (needPin) {
    const okPin = await requestProtectionPin()
    if (!okPin) return false
  }
  if (shouldConfirmForAction('protection_settings')) {
    return window.confirm(masterOffConfirmMessage(chatTitle))
  }
  return true
}
const welcomeForm = ref({
  enabled: false,
  text: '',
  maxPerMin: 0,
  silentOnRaid: false,
  raidThreshold: 8,
  raidWindowMinutes: 2,
  everyNJoins: 1,
})
const postRulesGroupForm = ref({
  enabled: false,
  text: '',
  pinOnSend: true,
  deletePinNotice: false,
  eventOnTrigger: false,
  eventOnPunish: false,
  eventTriggerEveryN: 1,
  eventPunishEveryN: 1,
})
const postRulesDrafts = ref([])
const welcomePreviewUrl = ref('')
const welcomePhotoBusy = ref(false)
const welcomeImagePreviewUrl = ref('')
const welcomeSessionBaseline = ref('')
const welcomeBusy = ref(false)
/** '' | 'main' | 'text' | 'rate' | 'raid' — оверлей Guard-подсказок в настройках приветствия */
const welcomeInfoModal = ref('')
let spikeAlertsTimer = null
const PROTECTION_CACHE_KEY = 'guard.protection.chat.cache.v1'
const PROTECTION_PREMIUM_CACHE_KEY = 'guard.protection.is_premium.v1'
const POST_RULES_DRAFTS_KEY = 'guard.protection.post_rules_drafts.v1'
/** Последний активный черновик правил группы по chatId — восстановление при повторном открытии модалки. */
const POST_RULES_LAST_DRAFT_KEY = 'guard.post_rules.last_draft.v1'
let postRulesDraftsRemoteSyncTimer = null

function postRulesLastDraftMap() {
  try {
    const raw = sessionStorage.getItem(POST_RULES_LAST_DRAFT_KEY)
    const o = raw ? JSON.parse(raw) : {}
    return o && typeof o === 'object' ? o : {}
  } catch {
    return {}
  }
}

function postRulesRememberLastDraftForChat() {
  try {
    const cid = String(Number(chat.value?.id || 0) || 0)
    if (!cid || cid === '0') return
    const o = postRulesLastDraftMap()
    o[cid] = String(postRulesActiveDraftId.value || '')
    sessionStorage.setItem(POST_RULES_LAST_DRAFT_KEY, JSON.stringify(o))
  } catch {
    //
  }
}

function postRulesGetLastActiveDraftIdForChat(cid) {
  try {
    return String(postRulesLastDraftMap()[String(cid)] || '')
  } catch {
    return ''
  }
}

function postRulesClearLastDraftForChat(cid) {
  try {
    const id = String(cid || '')
    if (!id || id === '0') return
    const o = postRulesLastDraftMap()
    if (!Object.prototype.hasOwnProperty.call(o, id)) return
    delete o[id]
    sessionStorage.setItem(POST_RULES_LAST_DRAFT_KEY, JSON.stringify(o))
  } catch {
    //
  }
}

function readProtectionCache() {
  try {
    const raw = localStorage.getItem(PROTECTION_CACHE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    return parsed
  } catch {
    return null
  }
}

function writeProtectionCache(payload) {
  try {
    localStorage.setItem(PROTECTION_CACHE_KEY, JSON.stringify(payload))
  } catch {
    // ignore storage quota/private mode restrictions
  }
}

/** Подмешивает в rule поля новых версий API — иначе из кэша приходят undefined и ломают форму/сохранение. */
function ensureChatRuleShape(c) {
  if (!c || typeof c !== 'object' || !c.rule || typeof c.rule !== 'object') return
  const r = c.rule
  const nInt = (v, lo, hi, d) => {
    const x = Number(v)
    if (!Number.isFinite(x)) return d
    return Math.max(lo, Math.min(hi, Math.floor(x)))
  }
  if (typeof r.rules_group_event_on_trigger !== 'boolean') r.rules_group_event_on_trigger = !!r.rules_group_event_on_trigger
  if (typeof r.rules_group_event_on_punish !== 'boolean') r.rules_group_event_on_punish = !!r.rules_group_event_on_punish
  r.rules_group_event_trigger_every_n = nInt(r.rules_group_event_trigger_every_n, 1, 500, 1)
  r.rules_group_event_punish_every_n = nInt(r.rules_group_event_punish_every_n, 1, 500, 1)
  r.rules_group_active_draft_id =
    r.rules_group_active_draft_id == null || r.rules_group_active_draft_id === undefined
      ? ''
      : String(r.rules_group_active_draft_id)
  if (typeof r.rules_group_delete_pin_notice !== 'boolean') r.rules_group_delete_pin_notice = !!r.rules_group_delete_pin_notice
}

function saveCurrentChatCache(nextChat = chat.value) {
  if (!nextChat?.rule || !nextChat?.id) return
  writeProtectionCache({
    selectedChatId: Number(selectedChatId.value || nextChat.id || 0) || null,
    chat: nextChat,
    savedAt: Date.now(),
  })
}

function readPremiumCache() {
  try {
    const raw = localStorage.getItem(PROTECTION_PREMIUM_CACHE_KEY)
    if (raw === '1') return true
    if (raw === '0') return false
  } catch {
    // ignore
  }
  return null
}

function writePremiumCache(v) {
  try {
    localStorage.setItem(PROTECTION_PREMIUM_CACHE_KEY, v ? '1' : '0')
  } catch {
    // ignore
  }
}

onMounted(async () => {
  if (!hasInitData.value) {
    guardLog('Protection', 'mount: skip (no initData)')
    return
  }
  const cached = readProtectionCache()
  const cachedPremium = readPremiumCache()
  if (cachedPremium !== null) isPremium.value = !!cachedPremium
  const cachedSelectedId = Number(cached?.selectedChatId || cached?.chat?.id || 0)
  if (cached?.chat?.rule) {
    chat.value = cached.chat
    ensureChatRuleShape(chat.value)
    if (cachedSelectedId) selectedChatId.value = cachedSelectedId
    guardLog('Protection', 'mount: hydrated from cache', { cachedSelectedId })
  }
  guardLog('Protection', 'mount: load chats + me + selected chat')
  try {
    let eagerChatPromise = null
    if (cachedSelectedId) {
      eagerChatPromise = fetchSilent(() => api.chat(cachedSelectedId))
        .then((data) => {
          if (!data?.rule) return null
          if (!selectedChatId.value || Number(selectedChatId.value) === cachedSelectedId) {
            selectedChatId.value = Number(data.id || cachedSelectedId)
            chat.value = data
            ensureChatRuleShape(chat.value)
            redirectChannelToBroadcastFromChatPayload(data)
            if (String(data.chat_kind || 'group').toLowerCase() === 'channel') return null
            void loadReputationPanel()
            saveCurrentChatCache(data)
          }
          return data
        })
        .catch(() => null)
    }

    // Всегда «all»: настройки защиты нужны по всем управляемым чатам (свои + делегированные).
    // Режим кабинета в шапке влияет на Рассылку/админку, но не должен «прятать» свои группы.
    const [chatsRes, meData] = await Promise.all([
      fetchSilent(() => api.chats('all')),
      fetchSilent(() => api.me()).catch(() => ({ is_premium: false })),
    ])
    const { chats, selected_chat_id } = chatsRes || {}
    guardLog('Protection', 'chats loaded', {
      chatsCount: (chats || []).length,
      selected_chat_id,
      premium: !!meData?.is_premium,
    })
    isPremium.value = !!meData?.is_premium
    viewerTelegramId.value = Number(meData?.telegram_id || 0)
    writePremiumCache(isPremium.value)
    chatsList.value = chats || []
    const fallbackSelectedChatId = pickDefaultProtectionChatId(chatsList.value)
    const resolvedSelectedChatId = Number(selected_chat_id || 0) || fallbackSelectedChatId || null
    selectedChatId.value = resolvedSelectedChatId
    void postRulesHydrateDraftsFromServer()
    if (!resolvedSelectedChatId) {
      chat.value = { noSelection: true }
      guardLog('Protection', 'no selected chat for protection → empty state')
      return
    }
    let data = null
    if (eagerChatPromise && Number(resolvedSelectedChatId) === cachedSelectedId) {
      data = await eagerChatPromise
    }
    if (!data?.rule) data = await fetchSilent(() => api.chat(resolvedSelectedChatId))
    chat.value = data
    ensureChatRuleShape(chat.value)
    redirectChannelToBroadcastFromChatPayload(data)
    if (String(data.chat_kind || 'group').toLowerCase() === 'channel') {
      chatsListLoading.value = false
      return
    }
    void loadReputationPanel()
    saveCurrentChatCache(data)
    void loadSpikeAlerts()
    void fetchSilent(() => api.globalAntispamList())
      .then((antispam) => {
        antispamItems.value = antispam?.items || []
      })
      .catch(() => {
        antispamItems.value = []
      })
    guardLog('Protection', 'chat rule snapshot', {
      chatId: data?.id,
      public_alerts_enabled: data?.rule?.public_alerts_enabled,
      public_alerts_style: data?.rule?.public_alerts_style,
    })
    guardLog('Protection', 'mount OK')
    if (spikeAlertsTimer) clearInterval(spikeAlertsTimer)
    spikeAlertsTimer = setInterval(loadSpikeAlerts, 30000)
  } catch (e) {
    guardWarn('Protection', 'mount failed', e)
    chat.value = { noSelection: false, loadError: true }
  } finally {
    chatsListLoading.value = false
  }
})

onBeforeUnmount(() => {
  if (postRulesDraftsRemoteSyncTimer) {
    clearTimeout(postRulesDraftsRemoteSyncTimer)
    postRulesDraftsRemoteSyncTimer = null
    if (hasInitData.value) {
      const snap = JSON.parse(JSON.stringify((postRulesDrafts.value || []).slice(0, 80)))
      void fetchSilent(() => api.mePostRulesDraftsPut(snap)).catch(() => {})
    }
  }
  if (spikeAlertsTimer) {
    clearInterval(spikeAlertsTimer)
    spikeAlertsTimer = null
  }
  if (welcomePreviewUrl.value) {
    revokeBroadcastMediaPreviewUrl(welcomePreviewUrl.value)
    welcomePreviewUrl.value = ''
  }
  if (postRulesGroupPreviewUrl.value) {
    revokeBroadcastMediaPreviewUrl(postRulesGroupPreviewUrl.value)
    postRulesGroupPreviewUrl.value = ''
  }
  document.removeEventListener('selectionchange', onWelcomeEditorSelectionChange)
  if (document?.body?.style) document.body.style.overflow = ''
})

function onWelcomeEditorSelectionChange() {
  const sel = window.getSelection?.()
  if (!sel || !sel.rangeCount) return
  const range = sel.getRangeAt(0)
  const editor = welcomeBodyRef.value
  if (!editor) return
  if (!editor.contains(range.startContainer)) return
  welcomeSavedRange.value = range.cloneRange()
  const from = range.startContainer instanceof Element ? range.startContainer : range.startContainer?.parentElement
  const spoilerEl = from?.closest?.('[data-spoiler="1"], tg-spoiler')
  const linkEl = from?.closest?.('a')
  welcomeFormatState.value = {
    bold: !!document.queryCommandState('bold'),
    italic: !!document.queryCommandState('italic'),
    underline: !!document.queryCommandState('underline'),
    strike: !!document.queryCommandState('strikeThrough'),
    spoiler: !!spoilerEl,
    link: !!linkEl,
  }
}

watch(
  () => showWelcomeSettingsModal.value,
  (open) => {
    if (document?.body?.style) {
      document.body.style.overflow = open ? 'hidden' : ''
    }
    if (open) {
      document.addEventListener('selectionchange', onWelcomeEditorSelectionChange)
    } else {
      document.removeEventListener('selectionchange', onWelcomeEditorSelectionChange)
      showWelcomeButtonsModal.value = false
      welcomeLinkModalOpen.value = false
      welcomeInfoModal.value = ''
      welcomeImagePreviewUrl.value = ''
    }
  },
)

const selectedChatTitle = computed(() => {
  const current = (chatsList.value || []).find((c) => Number(c.id) === Number(selectedChatId.value))
  return current?.title || chat.value?.title || 'Чат не выбран'
})
const selectedChatMeta = computed(() => (chatsList.value || []).find((c) => Number(c.id) === Number(selectedChatId.value)) || null)
const canUsePremiumForCurrentChat = computed(
  () => !!isPremium.value || (!!selectedChatMeta.value?.is_shared && !!chat.value?.chat_owner_is_premium),
)
/** Free / без подписки владельца: показываем «Premium» и прокладку, без реальной смены правил */
const premiumFeatureLocked = computed(() => !canUsePremiumForCurrentChat.value)
const premiumSectionFrameClass = computed(() =>
  premiumFeatureLocked.value
    ? 'ring-1 ring-amber-400/35 ring-inset shadow-[0_0_24px_-10px_rgba(251,191,36,0.12)]'
    : '',
)
const premiumControlRowClass = computed(() => (premiumFeatureLocked.value ? 'opacity-[0.72]' : ''))
/** «Перенести» в несколько чатов — только Premium; при 1 чате рамка не нужна */
const copySectionPremiumClass = computed(() => {
  if (!premiumFeatureLocked.value) return ''
  if ((chatsList.value || []).length <= 1) return ''
  return 'ring-1 ring-amber-400/35 ring-inset shadow-[0_0_24px_-10px_rgba(251,191,36,0.12)]'
})
function sortChatsByAvailability(list) {
  return [...(list || [])].sort((a, b) => {
    const lockDiff = Number(!!a?.locked_by_limit) - Number(!!b?.locked_by_limit)
    if (lockDiff !== 0) return lockDiff
    return String(a?.title || '').localeCompare(String(b?.title || ''), 'ru')
  })
}
function isChannelListRow(c) {
  return String(c?.chat_kind || 'group').toLowerCase() === 'channel'
}

function redirectChannelToBroadcastFromRow(row) {
  if (!row?.id) return
  const shared = !!row.is_shared
  try {
    localStorage.setItem('guard.broadcast.open_channel_id', String(Number(row.id)))
  } catch {
    //
  }
  setCabinetMode(shared ? 'delegated' : 'owner')
  const q = { tab: 'broadcasts' }
  if (shared) q.cabinet = 'delegated'
  router.replace({ path: '/admin', query: q })
}

function redirectChannelToBroadcastFromChatPayload(data) {
  if (!data?.id || data.noSelection || data.loadError) return
  if (String(data.chat_kind || 'group').toLowerCase() !== 'channel') return
  redirectChannelToBroadcastFromRow({ id: data.id, is_shared: !!data.is_shared })
}

const pickerDelegatedChats = computed(() =>
  sortChatsByAvailability((chatsList.value || []).filter((c) => !!c.is_shared && !isChannelListRow(c))),
)
const pickerOwnChats = computed(() =>
  sortChatsByAvailability((chatsList.value || []).filter((c) => !c.is_shared && !isChannelListRow(c))),
)
function delegatedCanProtection(chatRow) {
  if (!chatRow?.is_shared) return true
  const perms = chatRow?.delegated_permissions
  if (perms == null) return true
  return !!perms.protection
}
function pickDefaultProtectionChatId(rows = []) {
  const list = Array.isArray(rows) ? rows : []
  const firstAllowed = list.find((c) => !c?.locked_by_limit && delegatedCanProtection(c) && !isChannelListRow(c))
  if (firstAllowed?.id) return Number(firstAllowed.id)
  const firstGroup = list.find((c) => !isChannelListRow(c))
  if (firstGroup?.id) return Number(firstGroup.id)
  return null
}
const pickerTotalChats = computed(() => Number((chatsList.value || []).length || 0))
const pickerActiveChats = computed(() =>
  Number((chatsList.value || []).filter((c) => !c?.locked_by_limit && !!c?.master_anti_spam).length || 0),
)

const silenceStatusLabel = computed(() => {
  const mins = Number(chat.value?.rule?.silence_minutes || 0)
  if (!mins) return 'Выключено'
  const found = silencePresets.find((p) => p.value === mins)
  return found?.label || `${mins} минут`
})

const antiraidActivePresetKey = computed(() => {
  const r = chat.value?.rule
  if (!r) return null
  const threshold = Number(r.antinakrutka_joins_threshold || 10)
  const windowMin = Number(r.antinakrutka_window_minutes || 5)
  const action = String(r.antinakrutka_action || 'alert')
  const restrict = Number(r.antinakrutka_restrict_minutes || 30)
  const hit = antinakrutkaModePresets.find(
    (p) => p.threshold === threshold && p.window === windowMin && p.action === action && p.restrict === restrict,
  )
  return hit?.key || null
})

async function switchChat(chatId) {
  if (!chatId || Number(chatId) === Number(selectedChatId.value)) return
  const target = (chatsList.value || []).find((c) => Number(c.id) === Number(chatId))
  if (target?.locked_by_limit) {
    goToPremiumBilling()
    return
  }
  if (target && !delegatedCanProtection(target)) {
    showToast('У вас нет права «Защита» для этого чата.')
    return
  }
  if (target && isChannelListRow(target)) {
    redirectChannelToBroadcastFromRow(target)
    return
  }
  const prevId = Number(selectedChatId.value || 0) || null
  selectedChatId.value = Number(chatId)
  showChatPicker.value = false
  switchChatBusy.value = true
  try {
    const nextId = Number(chatId)
    const [, data] = await Promise.all([
      api.selectChat(nextId),
      api.chat(nextId),
    ])
    chat.value = data
    ensureChatRuleShape(chat.value)
    void loadReputationPanel()
    saveCurrentChatCache(data)
    void loadSpikeAlerts()
  } catch (e) {
    selectedChatId.value = prevId
    guardWarn('Protection', `switchChat(${chatId}) failed`, e)
    showToast('Не удалось переключить чат')
  } finally {
    switchChatBusy.value = false
  }
}

async function openChatPicker() {
  showChatPicker.value = true
  if ((chatsList.value || []).length > 0) return
  chatsListLoading.value = true
  try {
    const [chatsRes, meData] = await Promise.all([
      fetchSilent(() => api.chats('all')),
      fetchSilent(() => api.me()).catch(() => ({ is_premium: false })),
    ])
    isPremium.value = !!meData?.is_premium
    viewerTelegramId.value = Number(meData?.telegram_id || 0)
    writePremiumCache(isPremium.value)
    const rows = chatsRes?.chats || []
    chatsList.value = rows
    if (!selectedChatId.value && chatsRes?.selected_chat_id) {
      selectedChatId.value = Number(chatsRes.selected_chat_id)
    }
  } catch (e) {
    guardWarn('Protection', 'openChatPicker load failed', e)
  } finally {
    chatsListLoading.value = false
  }
}

function goToPremiumBilling() {
  showChatPicker.value = false
  const q = { ...route.query, section: 'billing' }
  delete q.scroll
  void router.push({ path: '/', query: q })
}

function openFreeLimitsPremiumModal() {
  showFreeLimitsPremiumModal.value = true
}

function closeFreeLimitsPremiumModal() {
  showFreeLimitsPremiumModal.value = false
}

/** Переход на лендинг тарифа, блок «Premium» */
function onFreeLimitsModalLearnMore() {
  showFreeLimitsPremiumModal.value = false
  void router.push({ path: '/', query: { ...route.query, section: 'billing', scroll: 'pitch' } })
}

function withPremiumForCurrentChatOrModal(fn) {
  if (canUsePremiumForCurrentChat.value) {
    fn?.()
    return true
  }
  openFreeLimitsPremiumModal()
  return false
}

function onSilenceConfigureClick() {
  withPremiumForCurrentChatOrModal(() => {
    showSilencePickerModal.value = true
  })
}

function onAntinakrutkaOpenSettingsClick() {
  withPremiumForCurrentChatOrModal(() => {
    showAntinakrutkaSettingsModal.value = true
  })
}

function onJoinCaptchaToggleClick() {
  withPremiumForCurrentChatOrModal(() =>
    updateRule({ join_captcha_enabled: !chat.value.rule.join_captcha_enabled }),
  )
}

function onJoinCaptchaOpenSettingsClick() {
  withPremiumForCurrentChatOrModal(() => {
    showJoinCaptchaSettingsModal.value = true
  })
}

function onNewbieToggleClick() {
  withPremiumForCurrentChatOrModal(() =>
    updateRule({ newbie_enabled: !chat.value.rule.newbie_enabled }),
  )
}

function onAntispamDbToggleClick() {
  withPremiumForCurrentChatOrModal(() =>
    updateRule({ use_global_antispam_db: !chat.value.rule.use_global_antispam_db }),
  )
}

function onCopySettingsBarClick() {
  if (!canUsePremiumForCurrentChat.value && (chatsList.value || []).length > 1) {
    openFreeLimitsPremiumModal()
    return
  }
  doCopySettings()
}

function onAntinakrutkaMainToggleClick() {
  withPremiumForCurrentChatOrModal(() =>
    updateRule({ antinakrutka_enabled: !chat.value.rule.antinakrutka_enabled }),
  )
}

function onSilencePresetPick(value) {
  withPremiumForCurrentChatOrModal(() => updateRule({ silence_minutes: value }))
}

function onGuardianIntervalPick(h) {
  withPremiumForCurrentChatOrModal(() => updateRule({ guardian_periodic_interval_hours: h }))
}

function onAntispamListButtonClick() {
  withPremiumForCurrentChatOrModal(() => {
    showAntispamListModal.value = true
  })
}

function pickerProtectionOn(c) {
  if (c?.locked_by_limit) return false
  if (!delegatedCanProtection(c)) return false
  return !!c?.master_anti_spam
}

async function toggleChatProtectionFromPicker(chatRow) {
  const cid = Number(chatRow?.id || 0)
  if (!cid || chatRow?.locked_by_limit) return
  if (!delegatedCanProtection(chatRow)) return
  if (pickerToggleBusyByChat.value[cid]) return
  const next = !pickerProtectionOn(chatRow)
  const titleHint = String(chatRow?.title || '').trim() || `#${cid}`
  if (!next) {
    const allow = await ensureCanTurnMasterOff(titleHint)
    if (!allow) return
  }
  pickerToggleBusyByChat.value = { ...pickerToggleBusyByChat.value, [cid]: true }
  const prev = pickerProtectionOn(chatRow)
  chatRow.master_anti_spam = next
  if (Number(selectedChatId.value) === cid && chat.value?.rule) {
    chat.value.rule.master_anti_spam = next
  }
  try {
    const data = await fetchSilent(() => api.updateRule(cid, { master_anti_spam: next }))
    if (data?.rule && Number(selectedChatId.value) === cid && chat.value?.id === cid) {
      chat.value.rule = data.rule
    }
    if (Number(selectedChatId.value) === cid && chat.value?.id === cid) {
      saveCurrentChatCache()
    }
  } catch (e) {
    chatRow.master_anti_spam = prev
    if (Number(selectedChatId.value) === cid && chat.value?.rule) {
      chat.value.rule.master_anti_spam = prev
    }
    guardWarn('Protection', `toggleChatProtectionFromPicker(${cid}) failed`, e)
    showToast('Не удалось переключить защиту')
  } finally {
    pickerToggleBusyByChat.value = { ...pickerToggleBusyByChat.value, [cid]: false }
  }
}

async function loadSpikeAlerts() {
  try {
    const r = await fetchSilent(() => api.spikeAlerts())
    const map = {}
    for (const row of r?.items || []) {
      const cid = Number(row?.chat_id || 0)
      if (!cid) continue
      map[cid] = row
    }
    spikeAlertsByChat.value = map
  } catch {
    spikeAlertsByChat.value = {}
  }
}

const currentSpikeAlert = computed(() => {
  const cid = Number(selectedChatId.value || chat.value?.id || 0)
  if (!cid) return null
  return spikeAlertsByChat.value[cid] || null
})

async function applySpikeRecommendedSettings() {
  if (!chat.value?.rule || !currentSpikeAlert.value) return
  const patch = {}
  if (!chat.value.rule.newbie_enabled) patch.newbie_enabled = true
  if (!chat.value.rule.first_message_captcha_enabled) patch.first_message_captcha_enabled = true
  if (!chat.value.rule.join_captcha_enabled) patch.join_captcha_enabled = true
  if (Number(chat.value.rule.silence_minutes || 0) <= 0) patch.silence_minutes = 10
  if (!Object.keys(patch).length) {
    showToast('Рекомендуемые безопасные настройки уже включены')
    return
  }
  await updateRule(patch)
}

const spamSpikeDeletePresets = [
  { n: 5, label: '5 удалений' },
  { n: 10, label: '10 удалений' },
  { n: 15, label: '15 удалений' },
  { n: 25, label: '25 удалений' },
  { n: 50, label: '50 удалений' },
  { n: 100, label: '100 удалений' },
  { n: 150, label: '150 удалений' },
]
const spamSpikeWindowPresets = [
  { m: 10, label: '10 мин' },
  { m: 20, label: '20 мин' },
  { m: 35, label: '35 мин' },
  { m: 60, label: '60 мин' },
  { m: 90, label: '90 мин' },
  { m: 120, label: '120 мин' },
  { m: 180, label: '180 мин' },
  { m: 360, label: '360 мин' },
]

const premiumGuardVisualClass =
  'text-[12px] font-semibold tracking-wide text-slate-100'
const premiumGuardHintClass =
  'rounded-xl border border-emerald-400/20 bg-emerald-500/8 px-2 py-1 text-[12px] text-emerald-100/95'

const spamSpikeDefaultDeleteCount = 15
const guardianPeriodicFreeHours = 24

async function updateRule(patch, opts = {}) {
  if (!chat.value?.id || chat.value.noSelection) return
  const quietToast = !!opts.quietToast
  saving.value = true
  guardLog('Protection', `PATCH rule chat=${chat.value.id}`, patch)
  try {
    const data = await fetchSilent(() => api.updateRule(chat.value.id, patch))
    chat.value.rule = data.rule
    saveCurrentChatCache()
    guardLog('Protection', 'PATCH rule OK', {
      public_alerts_enabled: data.rule?.public_alerts_enabled,
      public_alerts_style: data.rule?.public_alerts_style,
    })
    if (!quietToast) showToast('Настройки успешно сохранены')
  } catch (e) {
    guardWarn('Protection', 'PATCH rule failed', e)
    if (error.value) showToast(error.value)
    else showToast('Не удалось сохранить настройки')
  } finally {
    saving.value = false
  }
}

async function toggleMasterProtection() {
  if (!chat.value?.rule) return
  const next = !chat.value.rule.master_anti_spam
  if (!next) {
    const ok = await ensureCanTurnMasterOff(String(selectedChatTitle.value || 'Чат'))
    if (!ok) return
  }
  await updateRule({ master_anti_spam: next })
}

function policyButtonClass(currentMode, optValue) {
  const selected = currentMode === optValue
  if (!selected) {
    return protToggleOff
  }
  if (optValue === 'forbid') {
    return 'bg-gradient-to-r from-rose-500 to-red-600 text-white shadow-[0_8px_20px_-10px_rgba(239,68,68,0.75)]'
  }
  return 'guard-green-soft'
}

function linkScopeButtonClass(currentScope, optValue) {
  const cur = String(currentScope || 'all').toLowerCase()
  const selected = cur === optValue
  const base = 'rounded-2xl border px-2.5 py-2.5 text-xs font-medium leading-snug backdrop-blur-md transition-colors'
  if (!selected) {
    return `${base} border-white/12 bg-white/[0.05] text-zinc-300 hover:border-white/18 hover:bg-white/[0.08]`
  }
  return `${base} border-teal-400/40 bg-teal-500/15 text-teal-50 shadow-[0_0_20px_-8px_rgba(45,212,191,0.35)] ring-1 ring-teal-400/20`
}

function boolToggleClass(on) {
  return on ? 'guard-green-soft' : protToggleOff
}

function hardDictSwitchClass(on) {
  return on
    ? 'border-emerald-400/45 bg-emerald-500/[0.34] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.14)]'
    : 'border-rose-400/45 bg-rose-500/[0.28] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.09)]'
}

function actionButtonClass(current, value) {
  if (current !== value) return protToggleOff
  if (value === 'ban') return 'bg-gradient-to-r from-rose-500 to-red-600 text-white shadow-[0_8px_20px_-10px_rgba(239,68,68,0.75)]'
  if (value === 'mute') return 'bg-gradient-to-r from-amber-400 to-orange-500 text-slate-900 shadow-[0_8px_20px_-10px_rgba(249,115,22,0.75)]'
  if (value === 'observe') {
    return 'border-2 border-red-400/80 bg-gradient-to-br from-red-950/90 to-rose-900/80 text-red-100 shadow-[0_0_20px_-6px_rgba(248,113,113,0.55)] ring-1 ring-red-400/30'
  }
  return 'guard-green-soft'
}

function antiraidPresetClass(key) {
  if (antiraidActivePresetKey.value !== key) {
    return 'border border-white/10 bg-white/[0.05] text-zinc-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-sm hover:border-white/16 hover:bg-white/[0.08]'
  }
  if (key === 'hard') return 'border-red-300 bg-gradient-to-r from-rose-500 to-red-600 text-white hover:opacity-90 dark:border-red-700'
  if (key === 'standard') return 'border-amber-300 bg-gradient-to-r from-amber-400 to-orange-500 text-slate-900 hover:opacity-90 dark:border-amber-700'
  return 'border-emerald-300 guard-green-soft dark:border-emerald-700'
}

async function addStopword() {
  const word = (newStopword.value || '').trim()
  if (!word || !chat.value?.id || chat.value.noSelection) return
  stopwordLoading.value = true
  try {
    const data = await fetchSilent(() => api.addStopword(chat.value.id, word))
    chat.value.stopwords = data.stopwords || []
    if (chat.value.rule) chat.value.rule.stopwords_count = chat.value.stopwords.length
    newStopword.value = ''
    showToast('Стоп-слово добавлено')
  } finally {
    stopwordLoading.value = false
  }
}

async function removeStopword(word) {
  if (!chat.value?.id || chat.value.noSelection) return
  stopwordLoading.value = true
  try {
    const data = await fetchSilent(() => api.deleteStopword(chat.value.id, word))
    chat.value.stopwords = data.stopwords || []
    if (chat.value.rule) chat.value.rule.stopwords_count = chat.value.stopwords.length
    showToast('Стоп-слово удалено')
  } finally {
    stopwordLoading.value = false
  }
}

async function loadReputationPanel() {
  if (!chat.value?.id || chat.value?.noSelection) {
    reputationDefaultWords.value = []
    reputationWords.value = []
    reputationTop.value = []
    reputationMyScore.value = 0
    return
  }
  reputationLoading.value = true
  try {
    const data = await fetchSilent(() => api.chatReputation(chat.value.id))
    reputationDefaultWords.value = data?.default_words || []
    reputationWords.value = data?.custom_words || []
    reputationTop.value = data?.top || []
    reputationMyScore.value = Number(data?.my_score || 0)
  } finally {
    reputationLoading.value = false
  }
}

function openReputationUserProfile(row) {
  const uid = Number(row?.user_id || 0)
  const uname = String(row?.username || '').trim().replace(/^@+/, '')
  const tg = window.Telegram?.WebApp
  const link = uname ? `https://t.me/${uname}` : uid > 0 ? `https://t.me/user?id=${uid}` : ''
  if (!link) return
  try {
    if (typeof tg?.openTelegramLink === 'function') {
      tg.openTelegramLink(link)
      return
    }
  } catch {
    //
  }
  try {
    if (typeof tg?.openLink === 'function') {
      tg.openLink(link)
      return
    }
  } catch {
    //
  }
  try {
    window.open(link, '_blank', 'noopener,noreferrer')
  } catch {
    //
  }
}

async function addReputationWord() {
  const word = (newReputationWord.value || '').trim()
  if (!word || !chat.value?.id || chat.value.noSelection) return
  reputationWordsLoading.value = true
  try {
    await fetchSilent(() => api.addReputationWord(chat.value.id, word))
    newReputationWord.value = ''
    await loadReputationPanel()
    showToast('Слово благодарности добавлено')
  } finally {
    reputationWordsLoading.value = false
  }
}

async function removeReputationWord(word) {
  if (!word || !chat.value?.id || chat.value.noSelection) return
  reputationWordsLoading.value = true
  try {
    await fetchSilent(() => api.deleteReputationWord(chat.value.id, word))
    await loadReputationPanel()
    showToast('Слово удалено')
  } finally {
    reputationWordsLoading.value = false
  }
}

async function loadAntispamList() {
  antispamLoading.value = true
  try {
    const data = await fetchSilent(() => api.globalAntispamList())
    antispamItems.value = data?.items || []
  } finally {
    antispamLoading.value = false
  }
}

async function addAntispamUser() {
  const uid = (newAntispamUserId.value || '').trim()
  if (!uid || !/^\d+$/.test(uid)) {
    showToast('Введите числовой user_id')
    return
  }
  antispamLoading.value = true
  try {
    await fetchSilent(() => api.globalAntispamAdd(Number(uid)))
    newAntispamUserId.value = ''
    await loadAntispamList()
    showToast('Добавлено в антиспам базу')
  } finally {
    antispamLoading.value = false
  }
}

async function removeAntispamUser(userId) {
  antispamLoading.value = true
  try {
    await fetchSilent(() => api.globalAntispamRemove(userId))
    antispamItems.value = antispamItems.value.filter((i) => i.user_id !== userId)
    showToast('Удалено из базы')
  } finally {
    antispamLoading.value = false
  }
}

/** Запуск очистки прямо из API без выхода из Mini App. */
async function openCleanDeleted() {
  if (!chat.value?.id) return
  cleanLaunchLoading.value = true
  try {
    const res = await fetchSilent(() => api.cleanDeleted(chat.value.id))
    showToast(`Очистка завершена: проверено ${res.checked}, удалено ${res.kicked}`)
  } catch {
    showToast(error.value || 'Не удалось запустить очистку')
  } finally {
    cleanLaunchLoading.value = false
  }
}

async function doCopySettings() {
  if (!chat.value?.id || !copyTargetId.value || chat.value.noSelection) return
  if (copyTargetId.value !== '__all__' && Number(copyTargetId.value) === chat.value.id) {
    showToast('Выберите другой чат')
    return
  }
  copyLoading.value = true
  try {
    if (copyTargetId.value === '__all__') {
      const targets = (chatsList.value || []).filter((c) => Number(c.id) !== Number(chat.value.id))
      if (!targets.length) {
        showToast('Нет других чатов для переноса')
        return
      }
      const ok = window.confirm(`Перенести текущие настройки во все чаты (${targets.length})?`)
      if (!ok) return
      for (const target of targets) {
        await fetchSilent(() => api.copySettings(chat.value.id, Number(target.id)))
      }
      showToast(`Настройки перенесены во все чаты (${targets.length})`)
    } else {
    await fetchSilent(() => api.copySettings(chat.value.id, Number(copyTargetId.value)))
    showToast('Настройки перенесены')
    }
    copyTargetId.value = null
  } finally {
    copyLoading.value = false
  }
}

const policyOptions = [
  { value: 'allow', label: 'Разрешено' },
  { value: 'forbid', label: 'Запрещено' },
]

const linkModeOptions = [
  {
    value: 'allow',
    label: 'Ссылки разрешены',
    guardHtml:
      'Представь: <strong>Guard</strong> сидит и почти <strong>не трогает</strong> ссылки в чате — можно кидать что угодно, как наклейки.<br><br>Но если ты нарисовал <strong>чёрный список</strong> (Premium) или включил <strong>глобальную базу</strong> ниже — это как <strong>красные наклейки «нельзя»</strong>: их я всё равно сниму. Так честнее: «разрешено» ≠ «без правил».',
  },
  {
    value: 'allow_except_global',
    label: 'Всё, кроме глобальной базы URL',
    guardHtml:
      'Обычные ссылки — <strong>проходят</strong>. Но если в адресе есть кусок из <strong>твоей глобальной базы URL</strong> (Premium: «Кабинет → АнтиURL»), <strong>Guard</strong> говорит: «Это из ящика „фу“ — мимо».<br><br>Плюс твой <strong>чёрный список</strong> по чату. Если в ящике пусто — я не придираюсь.',
  },
  {
    value: 'open_blacklist',
    label: 'Всё, кроме чёрного списка',
    guardHtml:
      'Почти всё летит в чат, как мячик. Исключение — <strong>твой чёрный список</strong> (Premium): попал под строку — <strong>Guard</strong> без сантиментов.<br><br>Отдельного «интернет-полицейского» у меня нет: есть твои строки и опционально <strong>глобальная база</strong> ниже, если включишь.',
  },
  {
    value: 'smart',
    label: 'Умный режим',
    guardHtml:
      '<strong>Guard</strong> злится в основном на <strong>чужие t.me / telegram.me</strong>, но <strong>не трогает</strong> ссылку на <strong>наш чат</strong> и ссылку на <strong>человека, который уже сидит здесь</strong>.<br><br>Обычные сайты — не моя война в этом режиме: дальше работают стоп-слова и остальное.',
  },
  {
    value: 'telegram_only',
    label: 'Только Telegram-ссылки',
    guardHtml:
      'Режу только <strong>телеграмные</strong> штуки: <strong>t.me</strong>, <strong>telegram.me</strong>, <strong>tg://</strong>. Сайт с рецептом борща — <strong>не трогаю</strong> здесь; если там мусор — поймают другие фильтры.',
  },
  {
    value: 'forbid',
    label: 'Кроме доверенных',
    guardHtml:
      'Тут правило простое: можно кидать ссылки только из твоего списка <strong>«Доверенные ссылки»</strong> ниже. Это и есть «белый список» — список <strong>разрешённых</strong> ссылок.<br><br>Если в одном сообщении намешали разрешённую и левую ссылку — <strong>Guard</strong> удаляет <strong>всё сообщение целиком</strong>.',
  },
  {
    value: 'delete_all',
    label: 'Резать все ссылки',
    guardHtml:
      'Любая ссылка в сообщении — <strong>под нож</strong>. Как наказывать (удалить / мут / бан) — смотри общие настройки <strong>Guard</strong>, я не выдумываю отдельный суд.',
  },
]

const linkModalLegendHtml =
  'Здесь не одна кнопка «вкл/выкл», а <strong>как именно Guard смотрит на ссылки</strong>.<br><br><strong>Чёрный список</strong> — твои личные «нельзя» по этому чату (Premium). <strong>Глобальная база URL</strong> — твои шаблоны из <strong>Premium → АнтиURL</strong>, если включишь проверку ниже (одна база на все твои чаты). <strong>Белый список</strong> — «разрешено именно так». Всё может работать <strong>вместе</strong> — как несколько правил в одной игре 😈'

const linkModalGlobalBadUrlsHtml =
  'Откуда берётся: ты сам кладёшь шаблоны в <strong>«Кабинет Premium → АнтиURL»</strong> — это твоя личная коробка «фу-ссылки» на все чаты, где ты владелец Guard.<br><br>Как для пятилетки: включил тумблер ниже — Guard заглядывает в коробку. Выключил — не заглядывает. Если совпало, дальше срабатывает <strong>то наказание, которое у тебя выбрано в этом чате</strong> (удалить / мут / бан). Чужие люди твою коробку не видят и к себе её не подмешивают.'

const linkModalScopeHtml =
  'В <strong>форуме-обсуждении канала</strong> иногда хочется: в «Общем» чатике — помягче, а <strong>под постами</strong> — построже. Guard умеет: можно проверять <strong>только комментарии к постам</strong>.<br><br>В обычной группе без топиков я не гадаю — фильтр на <strong>весь чат</strong>, иначе спам уйдёт в «болталку» и смеётся в усы.'

const linkModalBlacklistHtml =
  'Сюда пишешь кусок адреса (например <code class="rounded-md bg-black/35 px-1 text-zinc-200">spam.ru</code>). Попало в ссылку в сообщении — <strong>Guard</strong> бьёт <strong>отдельным правилом</strong> (жёстче обычного delete/mute/ban за ссылку, если ты так настроил).<br><br>До <strong>20</strong> строк с Premium; без Premium ящик пустой — так устроен тариф, не обижайся.'

const linkModalWhitelistHtml =
  'Это список <strong>разрешённых ссылок</strong> для режима <strong>«Кроме доверенных»</strong>. Добавляй домен (<code class="rounded-md bg-black/35 px-1 text-zinc-200">vk.com</code>) или конкретный путь (<code class="rounded-md bg-black/35 px-1 text-zinc-200">t.me/канал</code>).<br><br>Если ссылка не из этого списка — Guard считает её чужой и удаляет сообщение по правилам чата. Лимит: <strong>5</strong> бесплатно, <strong>100</strong> с Premium.'

const linkModalWhitelistUsersHtml =
  'Это люди, которым Guard <strong>доверяет ссылки</strong> в этом чате. Их сообщения со ссылками не режутся ссылочным фильтром.<br><br>Зачем: например, твой модератор, рекламный менеджер или бот-партнёр. Добавлять можно по <strong>@username</strong> или по <strong>Telegram ID</strong>.'

function linkModeButtonClass(currentMode, optValue) {
  const selected = String(currentMode || '').toLowerCase() === String(optValue || '').toLowerCase()
  const base =
    'rounded-2xl border px-2.5 py-2.5 text-left text-xs font-medium leading-snug backdrop-blur-md transition-[border-color,background-color,box-shadow] duration-200'
  if (!selected) {
    return `${base} border-white/12 bg-white/[0.05] text-zinc-300 hover:border-white/20 hover:bg-white/[0.09]`
  }
  if (optValue === 'allow' || optValue === 'open_blacklist' || optValue === 'allow_except_global') {
    return `${base} border-emerald-400/45 bg-emerald-500/15 text-emerald-50 shadow-[0_0_24px_-8px_rgba(52,211,153,0.45)] ring-1 ring-emerald-400/25`
  }
  if (optValue === 'delete_all' || optValue === 'telegram_only') {
    return `${base} border-rose-400/50 bg-gradient-to-br from-rose-600/35 to-red-900/40 text-white shadow-[0_0_28px_-10px_rgba(251,113,133,0.5)] ring-1 ring-rose-400/30`
  }
  return `${base} border-violet-400/40 bg-violet-500/15 text-violet-50 shadow-[0_0_24px_-8px_rgba(167,139,250,0.4)] ring-1 ring-violet-400/25`
}

const linkModeSummary = computed(() => {
  const m = String(chat.value?.rule?.filter_links_mode || '').toLowerCase()
  const labels = {
    allow: 'Ссылки разрешены',
    allow_except_global: 'Всё разрешено, кроме глобальной базы URL',
    open_blacklist: 'Всё разрешено, кроме чёрного списка',
    forbid: 'Только доверенные шаблоны',
    smart: 'Умный режим (Telegram)',
    telegram_only: 'Режутся только Telegram-ссылки',
    delete_all: 'Режутся все ссылки',
    captcha: 'Ссылки через капчу (на паузе)',
  }
  return labels[m] || 'Ссылки фильтруются'
})

const mentionsSummary = computed(() =>
  chat.value?.rule?.filter_mentions ? 'Упоминания запрещены' : 'Упоминания разрешены',
)
const mediaSummary = computed(() => {
  const m = String(chat.value?.rule?.filter_media_mode || 'allow').toLowerCase()
  return m === 'forbid' ? 'Медиа запрещено' : 'Медиа разрешено'
})
const buttonsSummary = computed(() => {
  const m = String(chat.value?.rule?.filter_buttons_mode || 'allow').toLowerCase()
  return m === 'forbid' ? 'Кнопки запрещены' : 'Кнопки разрешены'
})
const channelPostsSummary = computed(() => {
  const enabled = !!chat.value?.rule?.filter_channel_posts_enabled
  if (!enabled) return 'Сообщения от каналов разрешены'
  return String(chat.value?.rule?.filter_channel_posts_action || 'delete') === 'ban'
    ? 'Режутся + канал-источник банится'
    : 'Режутся (без бана канала)'
})
const postRulesDraftsForChat = computed(() =>
  (postRulesDrafts.value || []).filter(
    (d) => String(d?.chatId || '') === postRulesDraftChatKey() && String(d?.mode || 'channel') === 'group',
  ),
)

const postRulesEditingDraftName = computed(() => {
  const id = String(postRulesActiveDraftId.value || '')
  if (!id) return ''
  const row = (postRulesDraftsForChat.value || []).find((d) => String(d?.id || '') === id)
  return String(row?.name || '').trim()
})

const postRulesUnsavedBanner = computed(() => postRulesDraftNameDirty.value || postRulesServerDirty.value)

const postRulesGroupInlineButtonCount = computed(() => {
  let n = 0
  for (const row of postRulesGroupButtonRows.value || []) {
    for (const b of row || []) {
      if (String(b?.text || '').trim()) n += 1
    }
  }
  return n
})

function postRulesFlashSaved() {
  postRulesShowSaved.value = true
  if (postRulesSavedFlashTimer) clearTimeout(postRulesSavedFlashTimer)
  postRulesSavedFlashTimer = setTimeout(() => {
    postRulesShowSaved.value = false
    postRulesSavedFlashTimer = null
  }, 1600)
}

function postRulesServerSignature() {
  return JSON.stringify({
    mode: 'group',
    g: postRulesGroupForm.value,
    gb: postRulesBuildKeyboardPayload(postRulesGroupButtonRows),
    gp: String(postRulesGroupPreviewUrl.value || ''),
  })
}

const postRulesGroupDraftStatusLabel = computed(() =>
  postRulesServerDirty.value ? 'Черновик не сохранён' : 'Черновик сохранён',
)
const postRulesGroupEditingLabel = computed(() => {
  const name = String(postRulesEditingDraftName.value || '').trim()
  const tail = postRulesServerDirty.value ? 'не сохранён' : 'сохранён'
  if (name) return `${name} · ${tail}`
  return tail
})

const postRulesServerBaseline = ref('')
/** Снимок только текста / кнопок / превью фото — для кнопки «Сохранить черновик». */
const postRulesDraftContentBaseline = ref('')

function postRulesMarkDraftContentBaseline() {
  postRulesDraftContentBaseline.value = JSON.stringify({
    text: String(postRulesGroupForm.value.text || ''),
    gb: postRulesBuildKeyboardPayload(postRulesGroupButtonRows),
    gp: String(postRulesGroupPreviewUrl.value || ''),
  })
}

function postRulesMarkServerBaseline() {
  postRulesServerBaseline.value = postRulesServerSignature()
  postRulesServerDirty.value = false
}

function postRulesTouchServerDirty() {
  postRulesServerDirty.value = postRulesServerSignature() !== String(postRulesServerBaseline.value || '')
}

const postRulesGroupBodyPanelLocked = computed(
  () => !String(postRulesActiveDraftId.value || '').trim(),
)

const postRulesShowSaveDraftButton = computed(() => {
  if (!String(postRulesActiveDraftId.value || '').trim()) return false
  const cur = JSON.stringify({
    text: String(postRulesGroupForm.value.text || ''),
    gb: postRulesBuildKeyboardPayload(postRulesGroupButtonRows),
    gp: String(postRulesGroupPreviewUrl.value || ''),
  })
  return cur !== String(postRulesDraftContentBaseline.value || '')
})

function postRulesDraftDisplayName(d) {
  const id = String(d?.id || '')
  if (!id) return String(d?.name || '').trim()
  if (String(postRulesDraftNameEditId.value || '') === id) return String(postRulesDraftNameDraft.value || '').trim()
  return String(d?.name || '').trim()
}

function postRulesBeginDraftNameEdit(d) {
  const id = String(d?.id || '')
  if (!id) return
  postRulesDraftNameEditId.value = id
  postRulesDraftNameDraft.value = String(d?.name || '')
  postRulesDraftNameDirty.value = false
}

function postRulesOnDraftNameInput(d, ev) {
  const id = String(d?.id || '')
  if (!id) return
  postRulesDraftNameEditId.value = id
  postRulesDraftNameDraft.value = String(ev?.target?.value || '')
  const base = String(d?.name || '')
  postRulesDraftNameDirty.value = String(postRulesDraftNameDraft.value || '').trim() !== String(base || '').trim()
}

async function postRulesCommitDraftName(d) {
  const id = String(d?.id || '')
  const mode = String(d?.mode || 'channel')
  if (!id) return
  const next = String(postRulesDraftNameDraft.value || '').trim()
  if (!next) {
    showToast('Имя не может быть пустым')
    return
  }
  postRulesDrafts.value = (postRulesDrafts.value || []).map((x) => {
    if (String(x?.id || '') !== id || String(x?.mode || 'channel') !== mode) return x
    return { ...x, name: next.slice(0, 80) }
  })
  postRulesPersistDrafts()
  postRulesDraftNameDirty.value = false
  postRulesDraftNameEditId.value = ''
  showToast('Название шаблона сохранено')
}

function mergeWhitelistFromResponse(data) {
  if (!data || !chat.value) return
  if (Array.isArray(data.whitelist_domains)) chat.value.whitelist_domains = data.whitelist_domains
  if (Array.isArray(data.whitelist_users)) chat.value.whitelist_users = data.whitelist_users
  if (Array.isArray(data.whitelist_sender_chats)) chat.value.whitelist_sender_chats = data.whitelist_sender_chats
}

function mergeLinkBlacklistFromResponse(data) {
  if (!data || !chat.value) return
  if (Array.isArray(data.link_blacklist)) chat.value.link_blacklist = data.link_blacklist
}

function welcomeEmptyBtn() {
  return { text: '', url: '', web_app_url: '', callback_data: '' }
}

function postRulesEmptyBtn() {
  return { text: '', url: '', web_app_url: '', callback_data: '' }
}

function welcomeKeyboardRowsFromRule(rows) {
  const fromApi = []
  for (const row of rows || []) {
    if (!Array.isArray(row) || !row.length) continue
    const line = row.map((b) => ({
      text: String(b?.text || ''),
      url: String(b?.url || ''),
      web_app_url: String(b?.web_app_url || ''),
      callback_data: String(b?.callback_data || ''),
    }))
    fromApi.push(line)
  }
  if (!fromApi.length) return [[welcomeEmptyBtn()]]
  return fromApi
}

function welcomeBuildKeyboardPayload() {
  const out = []
  for (const row of welcomeButtonRows.value || []) {
    const line = []
    for (const b of row || []) {
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
  return out.slice(0, 6)
}

function postRulesKeyboardRowsFromRule(rows) {
  const fromApi = []
  for (const row of rows || []) {
    if (!Array.isArray(row) || !row.length) continue
    const line = row.map((b) => ({
      text: String(b?.text || ''),
      url: String(b?.url || ''),
      web_app_url: String(b?.web_app_url || ''),
      callback_data: String(b?.callback_data || ''),
    }))
    fromApi.push(line)
  }
  if (!fromApi.length) return [[postRulesEmptyBtn()]]
  return fromApi
}

function postRulesBuildKeyboardPayload(rowsRef) {
  const out = []
  for (const row of rowsRef.value || []) {
    const line = []
    for (const b of row || []) {
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
  return out.slice(0, 8)
}

function postRulesAddRow(rowsRef) {
  if (!Array.isArray(rowsRef.value)) rowsRef.value = []
  rowsRef.value.push([postRulesEmptyBtn()])
  rowsRef.value = rowsRef.value.slice()
  postRulesTouchServerDirty()
}

function postRulesAddButton(rowsRef, rowIdx) {
  if (!Array.isArray(rowsRef.value) || !rowsRef.value[rowIdx]) return
  if ((rowsRef.value[rowIdx] || []).length >= 6) return
  rowsRef.value[rowIdx].push(postRulesEmptyBtn())
  rowsRef.value = rowsRef.value.slice()
  postRulesTouchServerDirty()
}

function postRulesRemoveButton(rowsRef, ri, bi) {
  if (!Array.isArray(rowsRef.value) || !rowsRef.value[ri]) return
  rowsRef.value[ri].splice(bi, 1)
  if (!rowsRef.value[ri].length) rowsRef.value.splice(ri, 1)
  if (!rowsRef.value.length) rowsRef.value = [[postRulesEmptyBtn()]]
  rowsRef.value = rowsRef.value.slice()
  postRulesTouchServerDirty()
}

function postRulesDraftChatKey() {
  return String(Number(chat.value?.id || 0) || 0)
}

function postRulesLoadDrafts() {
  try {
    const raw = localStorage.getItem(POST_RULES_DRAFTS_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    postRulesDrafts.value = Array.isArray(parsed) ? parsed : []
  } catch {
    postRulesDrafts.value = []
  }
}

function postRulesPersistDraftsToLocalStorage() {
  try {
    localStorage.setItem(POST_RULES_DRAFTS_KEY, JSON.stringify(postRulesDrafts.value.slice(0, 80)))
  } catch {
    // ignore localStorage errors
  }
}

function postRulesScheduleRemoteDraftsSync() {
  if (postRulesDraftsRemoteSyncTimer) clearTimeout(postRulesDraftsRemoteSyncTimer)
  const snapshot = JSON.parse(JSON.stringify((postRulesDrafts.value || []).slice(0, 80)))
  postRulesDraftsRemoteSyncTimer = setTimeout(async () => {
    postRulesDraftsRemoteSyncTimer = null
    if (!hasInitData.value) return
    try {
      await fetchSilent(() => api.mePostRulesDraftsPut(snapshot))
    } catch {
      //
    }
  }, 850)
}

function postRulesPersistDrafts() {
  postRulesPersistDraftsToLocalStorage()
  postRulesScheduleRemoteDraftsSync()
}

function postRulesPersistDraftsSkipRemote() {
  postRulesPersistDraftsToLocalStorage()
}

async function postRulesHydrateDraftsFromServer() {
  postRulesLoadDrafts()
  if (!hasInitData.value) return
  const localFallback = (postRulesDrafts.value || []).slice(0, 80)
  try {
    const res = await fetchSilent(() => api.mePostRulesDraftsGet())
    const remote = Array.isArray(res?.drafts) ? res.drafts : []
    if (!remote.length && localFallback.length) {
      postRulesDrafts.value = localFallback
      await fetchSilent(() => api.mePostRulesDraftsPut(postRulesDrafts.value))
      postRulesPersistDraftsToLocalStorage()
      return
    }
    postRulesDrafts.value = remote.slice(0, 80)
    postRulesPersistDraftsToLocalStorage()
  } catch {
    // оставляем локальную копию из postRulesLoadDrafts
  }
}

async function postRulesPreviewToDataUrl(mode) {
  const src = postRulesGroupPreviewUrl.value
  void mode
  if (!src) return ''
  try {
    const blob = await fetch(src).then((r) => r.blob())
    const dataUrl = await new Promise((resolve, reject) => {
      const fr = new FileReader()
      fr.onload = () => resolve(String(fr.result || ''))
      fr.onerror = reject
      fr.readAsDataURL(blob)
    })
    return String(dataUrl || '')
  } catch {
    return ''
  }
}

async function postRulesApplyDataUrlAsPhoto(mode, dataUrl) {
  if (!chat.value?.id || !dataUrl) return
  void mode
  try {
    const blob = await fetch(dataUrl).then((r) => r.blob())
    const ext = blob.type.includes('png') ? 'png' : blob.type.includes('webp') ? 'webp' : 'jpg'
    const file = new File([blob], `rules-draft.${ext}`, { type: blob.type || 'image/jpeg' })
    await uploadChatRulesPhoto(chat.value.id, 'group', file)
    await loadPostRulesPhotoPreview()
  } catch {
    // ignore draft media apply failure
  }
}

async function postRulesSaveDraft(opts = {}) {
  const silent = !!opts.silent
  postRulesSyncFormTextFromEditor()
  const cid = postRulesDraftChatKey()
  if (!cid || cid === '0') return
  const mode = 'group'
  const modePhotoDataUrl = await postRulesPreviewToDataUrl('group')
  const activeId = String(postRulesActiveDraftId.value || '')
  const baseNameFromEditor = String(postRulesEditorTextGet() || '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 40)
  const fallbackName = baseNameFromEditor || `Шаблон ${new Date().toLocaleString()}`
  if (activeId) {
    const nextPayload = {
      enabled: !!postRulesGroupForm.value.enabled,
      text: String(postRulesGroupForm.value.text || ''),
      pinOnSend: !!postRulesGroupForm.value.pinOnSend,
      deletePinNotice: !!postRulesGroupForm.value.deletePinNotice,
      eventOnTrigger: !!postRulesGroupForm.value.eventOnTrigger,
      eventOnPunish: !!postRulesGroupForm.value.eventOnPunish,
      eventTriggerEveryN: Math.max(1, Math.min(500, Number(postRulesGroupForm.value.eventTriggerEveryN || 1))),
      eventPunishEveryN: Math.max(1, Math.min(500, Number(postRulesGroupForm.value.eventPunishEveryN || 1))),
      buttons: postRulesBuildKeyboardPayload(postRulesGroupButtonRows),
      photoDataUrl: modePhotoDataUrl,
    }
    postRulesDrafts.value = (postRulesDrafts.value || []).map((x) => {
      if (String(x?.id || '') !== activeId) return x
      if (String(x?.chatId || '') !== cid || String(x?.mode || 'channel') !== mode) return x
      const nm = String(x?.name || '').trim() || fallbackName
      return { ...x, name: nm.slice(0, 80), savedAt: Date.now(), payload: nextPayload }
    })
    postRulesPersistDrafts()
    postRulesMarkDraftContentBaseline()
    if (!silent) showToast('Шаблон обновлён')
    return
  }
  const payload = {
    id: `d-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    chatId: cid,
    mode,
    name: fallbackName.slice(0, 80),
    savedAt: Date.now(),
    payload: {
      ...postRulesGroupForm.value,
      buttons: postRulesBuildKeyboardPayload(postRulesGroupButtonRows),
      photoDataUrl: modePhotoDataUrl,
    },
  }
  postRulesDrafts.value = [payload, ...(postRulesDrafts.value || []).filter((x) => String(x?.id || '') !== payload.id)].slice(0, 80)
  postRulesPersistDrafts()
  postRulesActiveDraftId.value = String(payload.id || '')
  postRulesDraftNameDraft.value = ''
  postRulesDraftNameEditId.value = ''
  postRulesDraftNameDirty.value = false
  postRulesMarkDraftContentBaseline()
  if (!silent) showToast('Шаблон сохранён')
}

function postRulesCreateGroupDraft() {
  const cid = postRulesDraftChatKey()
  if (!cid || cid === '0') return
  const mode = 'group'
  const n = (postRulesDraftsForChat.value || []).length + 1
  const payload = {
    id: `d-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    chatId: cid,
    mode,
    name: `Шаблон ${n}`,
    savedAt: Date.now(),
    payload: {
      enabled: !!postRulesGroupForm.value.enabled,
      text: '',
      pinOnSend: true,
      deletePinNotice: false,
      eventOnTrigger: false,
      eventOnPunish: false,
      eventTriggerEveryN: 1,
      eventPunishEveryN: 1,
      buttons: [],
      photoDataUrl: '',
    },
  }
  postRulesDrafts.value = [payload, ...(postRulesDrafts.value || [])].slice(0, 80)
  postRulesPersistDrafts()
  postRulesActiveDraftId.value = String(payload.id || '')
  postRulesGroupForm.value = {
    ...postRulesGroupForm.value,
    text: '',
    pinOnSend: true,
    deletePinNotice: false,
    eventOnTrigger: false,
    eventOnPunish: false,
    eventTriggerEveryN: 1,
    eventPunishEveryN: 1,
  }
  postRulesGroupButtonRows.value = [[postRulesEmptyBtn()]]
  void removePostRulesPhoto({ silent: true })
  postRulesEditorLoadFromForm({ silent: true })
  postRulesBeginDraftNameEdit(payload)
  postRulesMarkDraftContentBaseline()
  postRulesTouchServerDirty()
  showToast('Новый шаблон — отредактируйте и сохраните')
}

async function postRulesToggleRunGroupDraft(d) {
  const id = String(d?.id || '')
  if (!id || !chat.value?.id) return
  if (String(postRulesGroupRunDraftBusyId.value || '')) return
  postRulesGroupRunDraftBusyId.value = id
  try {
    if (String(postRulesGroupRunActiveId.value || '') === id) {
      postRulesGroupForm.value.enabled = false
      postRulesGroupRunActiveId.value = ''
      await updateRule(
        { rules_group_enabled: false, rules_group_active_draft_id: null },
        { quietToast: true },
      )
      if (chat.value?.rule) {
        chat.value.rule.rules_group_enabled = false
        chat.value.rule.rules_group_active_draft_id = ''
        ensureChatRuleShape(chat.value)
      }
      showToast('Запуск шаблона выключен')
      return
    }
    await postRulesApplyDraft(d, { quiet: true })
    postRulesGroupForm.value.enabled = true
    postRulesGroupRunActiveId.value = id
    await savePostRulesSettings({ skipResultToast: true })
    showToast(`Запущен: ${String(d?.name || '').trim() || 'шаблон'}`)
  } catch {
    showToast(error.value || 'Не удалось переключить шаблон')
  } finally {
    postRulesGroupRunDraftBusyId.value = ''
  }
}

function postRulesGroupDefaultSendPickId() {
  const list = (postRulesDraftsForChat.value || []).slice()
  if (!list.length) return ''
  const rid = String(postRulesGroupRunActiveId.value || '').trim()
  if (rid && list.some((x) => String(x?.id || '') === rid)) return rid
  list.sort((a, b) => (Number(b?.savedAt) || 0) - (Number(a?.savedAt) || 0))
  return String(list[0]?.id || '')
}

function postRulesGroupButtonLinesFromDraft(d) {
  const p = d?.payload || {}
  const raw = p.buttons ?? p.rules_group_buttons ?? []
  const lines = []
  for (const row of Array.isArray(raw) ? raw : []) {
    const inRow = []
    for (const b of row || []) {
      const t = String(b?.text || '').trim()
      if (t) inRow.push(t)
    }
    if (inRow.length) lines.push(inRow)
  }
  return lines
}

function postRulesGroupOpenFullPreview(d) {
  postRulesGroupFullPreviewRow.value = d
  showPostRulesGroupFullPreview.value = true
}
function postRulesGroupCloseFullPreview() {
  showPostRulesGroupFullPreview.value = false
  postRulesGroupFullPreviewRow.value = null
}

async function postRulesApplyDraft(d, opts = {}) {
  if (!d || typeof d !== 'object') return
  const quiet = !!opts.quiet
  postRulesDraftLoadingId.value = String(d?.id || '')
  try {
    postRulesActiveDraftId.value = String(d?.id || '')
    await nextTick()
    const p = d.payload || {}
    const prevGroupEn = !!postRulesGroupForm.value.enabled
    const buttonsRaw = p.buttons ?? p.rules_group_buttons ?? []
    postRulesGroupForm.value = {
      enabled: typeof p.enabled === 'boolean' ? !!p.enabled : prevGroupEn,
      text: String(p.text ?? ''),
      pinOnSend: p.pinOnSend !== undefined && p.pinOnSend !== null ? !!p.pinOnSend : true,
      deletePinNotice: !!p.deletePinNotice,
      eventOnTrigger: !!p.eventOnTrigger,
      eventOnPunish: !!p.eventOnPunish,
      eventTriggerEveryN: Math.max(1, Math.min(500, Number(p.eventTriggerEveryN || 1))),
      eventPunishEveryN: Math.max(1, Math.min(500, Number(p.eventPunishEveryN || 1))),
    }
    postRulesGroupButtonRows.value = postRulesKeyboardRowsFromRule(buttonsRaw || [])
    const ph = String(p.photoDataUrl || '').trim()
    if (ph) await postRulesApplyDataUrlAsPhoto('group', ph)
    else await loadPostRulesPhotoPreview()
    postRulesEditorLoadFromForm({ silent: true, flush: true })
    postRulesBeginDraftNameEdit(d)
    await nextTick()
    postRulesMarkServerBaseline()
    postRulesMarkDraftContentBaseline()
    if (!quiet) showToast('Черновик загружен')
  } finally {
    postRulesDraftLoadingId.value = ''
  }
}

async function postRulesDeleteDraft(id) {
  const mode = 'group'
  if (String(postRulesActiveDraftId.value || '') === String(id || '')) {
    postRulesActiveDraftId.value = ''
  }
  if (String(postRulesDraftNameEditId.value || '') === String(id || '')) {
    postRulesDraftNameEditId.value = ''
    postRulesDraftNameDraft.value = ''
    postRulesDraftNameDirty.value = false
  }
  const wasRun = String(postRulesGroupRunActiveId.value || '') === String(id || '')
  postRulesDrafts.value = (postRulesDrafts.value || []).filter(
    (x) => !(String(x?.id || '') === String(id || '') && String(x?.mode || 'channel') === mode),
  )
  postRulesPersistDrafts()
  if (wasRun) {
    postRulesGroupRunActiveId.value = ''
    if (chat.value?.rule) {
      chat.value.rule.rules_group_active_draft_id = ''
    }
    try {
      await updateRule({ rules_group_active_draft_id: null }, { quietToast: true })
    } catch {
      //
    }
  }
  const cid = String(Number(chat.value?.id || 0) || 0)
  if (cid && String(postRulesGetLastActiveDraftIdForChat(cid) || '') === String(id || '')) {
    postRulesClearLastDraftForChat(cid)
  }
}

function postRulesRowsRef() {
  return postRulesGroupButtonRows
}

function postRulesAddRowCurrent() {
  postRulesAddRow(postRulesRowsRef())
}

function postRulesAddButtonCurrent(ri) {
  postRulesAddButton(postRulesRowsRef(), ri)
}

function postRulesRemoveButtonCurrent(ri, bi) {
  postRulesRemoveButton(postRulesRowsRef(), ri, bi)
}

async function postRulesSaveButtonsFromModal() {
  await savePostRulesSettings()
}

function postRulesDraftSavedAtLabel(ts) {
  const n = Number(ts || 0)
  if (!Number.isFinite(n) || n <= 0) return ''
  try {
    return new Date(n).toLocaleString()
  } catch {
    return ''
  }
}

function openPostRulesImagePreview() {
  postRulesImagePreviewUrl.value = String(postRulesGroupPreviewUrl.value || '')
}

function postRulesEditorTextGet() {
  return String(postRulesGroupForm.value.text || '')
}

function postRulesEditorTextSet(v) {
  const clean = normalizeHtmlForTelegram(String(v || ''))
  postRulesGroupForm.value.text = clean
}

/** Снять HTML из contenteditable в form.text (иначе черновик/сервер без последней строки). */
function postRulesSyncFormTextFromEditor() {
  const el = postRulesBodyRef.value
  if (!el) return
  postRulesEditorTextSet(String(el.innerHTML || ''))
}

function postRulesEditorLoadFromForm(opts = {}) {
  const silent = !!opts?.silent
  const flush = !!opts?.flush
  const run = () => {
    const el = postRulesBodyRef.value
    if (!el) return
    el.innerHTML = String(postRulesEditorTextGet() || '')
    postRulesHistory.value = [String(el.innerHTML || '')]
    postRulesHistoryIndex.value = 0
    if (!silent) postRulesTouchServerDirty()
  }
  if (flush) {
    nextTick(() => {
      run()
      nextTick(run)
    })
    return
  }
  nextTick(run)
}

function postRulesRecordHistory(force = false) {
  const el = postRulesBodyRef.value
  if (!el) return
  const html = String(el.innerHTML || '')
  if (!force) {
    const cur = postRulesHistory.value[postRulesHistoryIndex.value]
    if (cur === html) return
  }
  if (postRulesHistoryIndex.value < postRulesHistory.value.length - 1) {
    postRulesHistory.value = postRulesHistory.value.slice(0, postRulesHistoryIndex.value + 1)
  }
  postRulesHistory.value.push(html)
  if (postRulesHistory.value.length > 120) postRulesHistory.value.shift()
  postRulesHistoryIndex.value = postRulesHistory.value.length - 1
}

function onPostRulesBodyInput() {
  const el = postRulesBodyRef.value
  if (!el) return
  postRulesEditorTextSet(String(el.innerHTML || ''))
  postRulesRecordHistory()
  postRulesTouchServerDirty()
}

function postRulesCanUndo() { return postRulesHistoryIndex.value > 0 }
function postRulesCanRedo() { return postRulesHistoryIndex.value >= 0 && postRulesHistoryIndex.value < postRulesHistory.value.length - 1 }
function postRulesUndo() {
  if (!postRulesCanUndo()) return
  postRulesHistoryIndex.value -= 1
  const el = postRulesBodyRef.value
  if (!el) return
  el.innerHTML = String(postRulesHistory.value[postRulesHistoryIndex.value] || '')
  postRulesEditorTextSet(el.innerHTML)
  postRulesTouchServerDirty()
}
function postRulesRedo() {
  if (!postRulesCanRedo()) return
  postRulesHistoryIndex.value += 1
  const el = postRulesBodyRef.value
  if (!el) return
  el.innerHTML = String(postRulesHistory.value[postRulesHistoryIndex.value] || '')
  postRulesEditorTextSet(el.innerHTML)
  postRulesTouchServerDirty()
}
function postRulesExec(cmd) {
  const el = postRulesBodyRef.value
  if (!el) return
  el.focus()
  document.execCommand(cmd, false)
  onPostRulesBodyInput()
  postRulesUpdateFormatState()
}
function postRulesUpdateFormatState() {
  const sel = window.getSelection?.()
  if (sel && sel.rangeCount) {
    const r = sel.getRangeAt(0)
    const el = postRulesBodyRef.value
    if (el && (el.contains(r.startContainer) || el.contains(r.endContainer))) {
      postRulesSavedRange.value = r.cloneRange()
    }
  }
  postRulesFormatState.value = {
    bold: !!document.queryCommandState('bold'),
    italic: !!document.queryCommandState('italic'),
    underline: !!document.queryCommandState('underline'),
    strike: !!document.queryCommandState('strikeThrough'),
  }
}
function postRulesFormatLink() {
  const sel = window.getSelection?.()
  const range = sel && sel.rangeCount ? sel.getRangeAt(0).cloneRange() : postRulesSavedRange.value
  const selectedText = String(range?.toString() || '').trim()
  if (!selectedText) {
    showToast('Сначала выдели текст для ссылки')
    return
  }
  postRulesLinkRange.value = range || null
  postRulesLinkUrl.value = 'https://'
  postRulesLinkModalOpen.value = true
}

function postRulesApplyLinkModal() {
  const url = String(postRulesLinkUrl.value || '').trim()
  if (!url) return
  const el = postRulesBodyRef.value
  if (!el) return
  el.focus()
  const sel = window.getSelection?.()
  const range = postRulesLinkRange.value || postRulesSavedRange.value || (sel && sel.rangeCount ? sel.getRangeAt(0) : null)
  if (!range) {
    showToast('Сначала выдели текст для ссылки')
    return
  }
  const text = String(range.toString() || '').trim()
  if (!text) {
    showToast('Сначала выдели текст для ссылки')
    return
  }
  const safeText = text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
  const safeUrl = url.replaceAll('"', '&quot;')
  range.deleteContents()
  const tmp = document.createElement('div')
  tmp.innerHTML = `<a href="${safeUrl}">${safeText}</a>`
  const node = tmp.firstChild
  if (node) {
    range.insertNode(node)
    range.setStartAfter(node)
    range.collapse(true)
    sel?.removeAllRanges()
    sel?.addRange(range)
    postRulesSavedRange.value = range.cloneRange()
  }
  onPostRulesBodyInput()
  postRulesLinkModalOpen.value = false
  postRulesLinkRange.value = null
}
function postRulesClearFormatting() {
  const el = postRulesBodyRef.value
  if (!el) return
  el.focus()
  document.execCommand('removeFormat', false)
  onPostRulesBodyInput()
}

function welcomeSyncEditorHtml() {
  const el = welcomeBodyRef.value
  if (!el) return
  welcomeBodyHtml.value = String(el.innerHTML || '')
}

function welcomeAfterDomMutation() {
  welcomeSyncEditorHtml()
  welcomeForm.value.text = normalizeHtmlForTelegram(String(welcomeBodyRef.value?.innerHTML || ''))
  welcomeRecordHistory()
}

function welcomeRecordHistory(force = false) {
  const el = welcomeBodyRef.value
  if (!el) return
  const html = String(el.innerHTML || '')
  if (!force) {
    const cur = welcomeHistory.value[welcomeHistoryIndex.value]
    if (cur === html) return
  }
  if (welcomeHistoryIndex.value < welcomeHistory.value.length - 1) {
    welcomeHistory.value = welcomeHistory.value.slice(0, welcomeHistoryIndex.value + 1)
  }
  welcomeHistory.value.push(html)
  if (welcomeHistory.value.length > 120) {
    welcomeHistory.value.shift()
  }
  welcomeHistoryIndex.value = welcomeHistory.value.length - 1
}

function welcomeCanUndo() {
  return welcomeHistoryIndex.value > 0
}

function welcomeCanRedo() {
  return welcomeHistoryIndex.value >= 0 && welcomeHistoryIndex.value < welcomeHistory.value.length - 1
}

function welcomeUndo() {
  if (!welcomeCanUndo()) return
  welcomeHistoryIndex.value -= 1
  const el = welcomeBodyRef.value
  if (!el) return
  el.innerHTML = String(welcomeHistory.value[welcomeHistoryIndex.value] || '')
  welcomeForm.value.text = normalizeHtmlForTelegram(String(el.innerHTML || ''))
  welcomeBodyHtml.value = String(el.innerHTML || '')
  nextTick(() => {
    el.focus()
    try {
      const r = document.createRange()
      r.selectNodeContents(el)
      r.collapse(false)
      const s = window.getSelection()
      s?.removeAllRanges()
      s?.addRange(r)
    } catch {
      // ignore
    }
    onWelcomeEditorSelectionChange()
  })
}

function welcomeRedo() {
  if (!welcomeCanRedo()) return
  welcomeHistoryIndex.value += 1
  const el = welcomeBodyRef.value
  if (!el) return
  el.innerHTML = String(welcomeHistory.value[welcomeHistoryIndex.value] || '')
  welcomeForm.value.text = normalizeHtmlForTelegram(String(el.innerHTML || ''))
  welcomeBodyHtml.value = String(el.innerHTML || '')
  nextTick(() => {
    el.focus()
    try {
      const r = document.createRange()
      r.selectNodeContents(el)
      r.collapse(false)
      const s = window.getSelection()
      s?.removeAllRanges()
      s?.addRange(r)
    } catch {
      // ignore
    }
    onWelcomeEditorSelectionChange()
  })
}

function welcomeInsertHtmlAtCursor(html) {
  const sel = window.getSelection?.()
  const range = sel && sel.rangeCount ? sel.getRangeAt(0) : welcomeSavedRange.value
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
  welcomeSavedRange.value = range.cloneRange()
  welcomeAfterDomMutation()
}

function welcomeCurrentRange() {
  const sel = window.getSelection?.()
  if (sel && sel.rangeCount) return sel.getRangeAt(0)
  return welcomeSavedRange.value
}

function welcomeSelectedTextFromRange(range) {
  if (!range) return ''
  try {
    return String(range.cloneContents().textContent || '')
  } catch {
    return ''
  }
}

function welcomeWrapRange(range, htmlOpen, htmlClose) {
  if (!range) return false
  const text = welcomeSelectedTextFromRange(range)
  if (!text.trim()) return false
  const sel = window.getSelection?.()
  if (sel) {
    sel.removeAllRanges()
    sel.addRange(range)
  }
  welcomeInsertHtmlAtCursor(`${htmlOpen}${text}${htmlClose}`)
  return true
}

function welcomeExec(cmd) {
  const el = welcomeBodyRef.value
  if (!el) return
  el.focus()
  document.execCommand(cmd, false)
  welcomeAfterDomMutation()
}

function welcomeFormatBold() {
  welcomeExec('bold')
}
function welcomeFormatItalic() {
  welcomeExec('italic')
}
function welcomeFormatUnderline() {
  welcomeExec('underline')
}
function welcomeFormatStrike() {
  welcomeExec('strikeThrough')
}

function welcomeFormatSpoiler() {
  const el = welcomeBodyRef.value
  if (!el) return
  el.focus()
  const range = welcomeCurrentRange()
  if (!welcomeWrapRange(range, '<span data-spoiler="1">', '</span>')) {
    window.alert('Выдели текст, затем нажми «Скрытый»')
    return
  }
}

function welcomeFormatPre() {
  const el = welcomeBodyRef.value
  if (!el) return
  el.focus()
  const sel = window.getSelection?.()
  const text = sel?.toString() || ''
  if (!text.trim()) {
    window.alert('Выдели текст, затем нажми «PRE»')
    return
  }
  welcomeInsertHtmlAtCursor(`<pre>${text}</pre>`)
}

function welcomeFormatBlockquote() {
  const el = welcomeBodyRef.value
  if (!el) return
  el.focus()
  const sel = window.getSelection()
  if (!sel || !sel.rangeCount) {
    window.alert('Выдели текст, затем нажми «Цитата»')
    return
  }
  const r0 = sel.getRangeAt(0)
  if (r0.collapsed) {
    window.alert('Выдели текст, затем нажми «Цитата»')
    return
  }
  const inEditor =
    el.contains(r0.commonAncestorContainer) || el.contains(r0.startContainer) || el.contains(r0.endContainer)
  if (!inEditor) {
    window.alert('Выдели текст в поле, затем нажми «Цитата»')
    return
  }
  // Не используем formatBlock: в однострочном contentEditable он тянет в цитату весь «блок» = всё поле.
  // Только оборачиваем ровно выделенный фрагмент.
  const rWork = r0.cloneRange()
  el.focus()
  sel.removeAllRanges()
  sel.addRange(rWork)
  const r1 = rWork.cloneRange()
  if (!r1) return
  try {
    if (!r1.toString().trim() && !welcomeSelectedTextFromRange(r1).trim()) {
      window.alert('Выдели текст, затем нажми «Цитата»')
      return
    }
    const frag = r1.extractContents()
    if (!frag) return
    const t = (frag.textContent || '').trim()
    if (!t) {
      window.alert('Выдели текст, затем нажми «Цитата»')
      return
    }
    const bq = document.createElement('blockquote')
    bq.appendChild(frag)
    r1.insertNode(bq)
    r1.setStartAfter(bq)
    r1.collapse(true)
    sel.removeAllRanges()
    sel.addRange(r1)
  } catch (e) {
    const r2 = welcomeCurrentRange()
    if (!welcomeWrapRange(r2, '<blockquote>', '</blockquote>')) {
      window.alert('Не удалось оформить цитату. Выдели кусок текста в поле и нажми «Цитата» снова.')
      return
    }
    return
  }
  welcomeAfterDomMutation()
}

function welcomeFormatCode() {
  const el = welcomeBodyRef.value
  if (!el) return
  el.focus()
  const sel = window.getSelection?.()
  const text = sel?.toString() || ''
  if (!text.trim()) {
    window.alert('Выдели текст, затем нажми «Код»')
    return
  }
  welcomeInsertHtmlAtCursor(`<code>${text}</code>`)
}

function welcomeFormatLink() {
  const el = welcomeBodyRef.value
  if (!el) return
  const sel = window.getSelection?.()
  const range = sel && sel.rangeCount ? sel.getRangeAt(0).cloneRange() : welcomeSavedRange.value
  const selectedText = welcomeSelectedTextFromRange(range)
  if (!selectedText.trim()) {
    window.alert('Выдели текст, затем нажми «Ссылка»')
    return
  }
  welcomeLinkRange.value = range || null
  welcomeLinkUrl.value = 'https://'
  welcomeLinkModalOpen.value = true
}

function welcomeApplyLinkModal() {
  const href = String(welcomeLinkUrl.value || '').trim()
  if (!href) return
  const el = welcomeBodyRef.value
  if (!el) return
  const sel = window.getSelection?.()
  el.focus()
  if (welcomeLinkRange.value && sel) {
    sel.removeAllRanges()
    sel.addRange(welcomeLinkRange.value)
  }
  document.execCommand('createLink', false, href)
  welcomeAfterDomMutation()
  welcomeLinkModalOpen.value = false
  welcomeLinkRange.value = null
}

function welcomeInsertPlain(chunk) {
  const el = welcomeBodyRef.value
  if (!el) return
  el.focus()
  document.execCommand('insertText', false, String(chunk || ''))
  welcomeAfterDomMutation()
}

function onWelcomeBodyInput() {
  welcomeAfterDomMutation()
}

function onWelcomeBodyClick(ev) {
  const el = ev?.target
  if (!(el instanceof HTMLElement)) return
  const spoiler = el.closest('[data-spoiler="1"], tg-spoiler')
  if (!spoiler) return
  spoiler.classList.add('reveal')
  window.setTimeout(() => spoiler.classList.remove('reveal'), 5000)
}

function initWelcomeEditorDom() {
  const el = welcomeBodyRef.value
  if (!el) return
  const raw = String(welcomeForm.value.text || '')
  if (/<\s*[a-z]/i.test(raw)) {
    el.innerHTML = raw
  } else {
    el.innerHTML = ''
    el.textContent = raw
  }
  welcomeSyncEditorHtml()
  welcomeForm.value.text = normalizeHtmlForTelegram(String(el.innerHTML || ''))
  welcomeHistory.value = [String(el.innerHTML || '')]
  welcomeHistoryIndex.value = 0
}

function welcomeAddRow() {
  if ((welcomeButtonRows.value || []).length >= 6) return
  welcomeButtonRows.value.push([welcomeEmptyBtn()])
}

function welcomeRemoveRow(ri) {
  const rows = [...(welcomeButtonRows.value || [])]
  rows.splice(ri, 1)
  welcomeButtonRows.value = rows.length ? rows : [[welcomeEmptyBtn()]]
}

function welcomeAddButton(rowIdx) {
  const rows = [...(welcomeButtonRows.value || [])]
  if (!rows[rowIdx]) return
  if (rows[rowIdx].length >= 4) return
  rows[rowIdx] = [...rows[rowIdx], welcomeEmptyBtn()]
  welcomeButtonRows.value = rows
}

function welcomeRemoveButton(ri, bi) {
  const rows = [...(welcomeButtonRows.value || [])]
  if (!rows[ri]) return
  rows[ri] = rows[ri].filter((_, i) => i !== bi)
  if (!rows[ri].length) rows.splice(ri, 1)
  welcomeButtonRows.value = rows.length ? rows : [[welcomeEmptyBtn()]]
}

function welcomeSnapshotForPersist() {
  welcomeSyncEditorHtml()
  const rawHtml = String(welcomeBodyRef.value?.innerHTML || welcomeBodyHtml.value || '')
  const text = normalizeHtmlForTelegram(rawHtml).slice(0, 4000)
  return JSON.stringify({
    en: !!welcomeForm.value.enabled,
    tx: text,
    bt: welcomeBuildKeyboardPayload(),
    mpm: Math.max(0, Math.min(60, Number(welcomeForm.value.maxPerMin || 0))),
    sor: !!welcomeForm.value.silentOnRaid,
    rth: Math.max(2, Math.min(200, Number(welcomeForm.value.raidThreshold || 8))),
    rwm: Math.max(1, Math.min(60, Number(welcomeForm.value.raidWindowMinutes || 2))),
    enj: Math.max(1, Math.min(500, Number(welcomeForm.value.everyNJoins || 1))),
    hp: !!chat.value?.rule?.welcome_has_photo,
  })
}

function welcomeMarkSessionBaseline() {
  welcomeSessionBaseline.value = welcomeSnapshotForPersist()
}

function welcomeSessionIsDirty() {
  return welcomeSnapshotForPersist() !== String(welcomeSessionBaseline.value || '')
}

function openWelcomeImagePreview() {
  const u = String(welcomePreviewUrl.value || '').trim()
  welcomeImagePreviewUrl.value = u
}

function openWelcomeSettings() {
  if (!chat.value?.rule) return
  welcomeForm.value = {
    enabled: !!chat.value.rule.welcome_enabled,
    text: String(chat.value.rule.welcome_text || ''),
    maxPerMin: Number(chat.value.rule.welcome_max_per_min || 0),
    silentOnRaid: !!chat.value.rule.welcome_silent_on_raid,
    raidThreshold: Number(chat.value.rule.welcome_raid_threshold || 8),
    raidWindowMinutes: Number(chat.value.rule.welcome_raid_window_minutes || 2),
    everyNJoins: Number(chat.value.rule.welcome_every_n_joins || 1),
  }
  welcomeButtonRows.value = welcomeKeyboardRowsFromRule(chat.value.rule.welcome_buttons || [])
  welcomeInfoModal.value = ''
  showWelcomeSettingsModal.value = true
  welcomeImagePreviewUrl.value = ''
  if (welcomePreviewUrl.value) {
    revokeBroadcastMediaPreviewUrl(welcomePreviewUrl.value)
    welcomePreviewUrl.value = ''
  }
  if (chat.value?.rule?.welcome_has_photo && chat.value?.id) {
    fetchChatWelcomePhotoPreviewUrl(chat.value.id)
      .then((u) => {
        welcomePreviewUrl.value = u
        nextTick(() => welcomeMarkSessionBaseline())
      })
      .catch(() => {
        welcomePreviewUrl.value = ''
      })
  }
  nextTick(() => {
    initWelcomeEditorDom()
    welcomeMarkSessionBaseline()
  })
}

async function onWelcomePhotoPicked(event) {
  const file = event?.target?.files?.[0]
  event.target.value = ''
  if (!file || !chat.value?.id) return
  welcomePhotoBusy.value = true
  try {
    await uploadChatWelcomePhoto(chat.value.id, file)
    chat.value.rule.welcome_has_photo = true
    if (welcomePreviewUrl.value) revokeBroadcastMediaPreviewUrl(welcomePreviewUrl.value)
    welcomePreviewUrl.value = await fetchChatWelcomePhotoPreviewUrl(chat.value.id)
    welcomeMarkSessionBaseline()
    showToast('Фото приветствия загружено')
  } catch {
    showToast(error.value || 'Не удалось загрузить фото')
  } finally {
    welcomePhotoBusy.value = false
  }
}

async function removeWelcomePhoto() {
  if (!chat.value?.id) return
  welcomePhotoBusy.value = true
  try {
    await fetchSilent(() => api.deleteWelcomePhoto(chat.value.id))
    chat.value.rule.welcome_has_photo = false
    if (welcomePreviewUrl.value) revokeBroadcastMediaPreviewUrl(welcomePreviewUrl.value)
    welcomePreviewUrl.value = ''
    welcomeMarkSessionBaseline()
    showToast('Фото удалено')
  } catch {
    showToast(error.value || 'Не удалось удалить фото')
  } finally {
    welcomePhotoBusy.value = false
  }
}

async function persistWelcomeSettings(opts = {}) {
  const closeAfter = !!opts.closeAfter
  const quietToast = !!opts.quietToast
  if (!chat.value?.id || !chat.value?.rule) return false
  welcomeBusy.value = true
  try {
    welcomeSyncEditorHtml()
    const rawHtml = String(welcomeBodyRef.value?.innerHTML || welcomeBodyHtml.value || '')
    const text = normalizeHtmlForTelegram(rawHtml).slice(0, 4000)
    const buttons = welcomeBuildKeyboardPayload()
    const everyN = Math.max(1, Math.min(500, Number(welcomeForm.value.everyNJoins || 1)))
    const maxPerMin = Math.max(0, Math.min(60, Number(welcomeForm.value.maxPerMin || 0)))
    const raidThreshold = Math.max(2, Math.min(200, Number(welcomeForm.value.raidThreshold || 8)))
    const raidWindow = Math.max(1, Math.min(60, Number(welcomeForm.value.raidWindowMinutes || 2)))
    const data = await fetchSilent(() =>
      api.updateRule(chat.value.id, {
        welcome_enabled: !!welcomeForm.value.enabled,
        welcome_text: text,
        welcome_buttons: buttons,
        welcome_max_per_min: maxPerMin,
        welcome_silent_on_raid: !!welcomeForm.value.silentOnRaid,
        welcome_raid_threshold: raidThreshold,
        welcome_raid_window_minutes: raidWindow,
        welcome_every_n_joins: everyN,
      }),
    )
    chat.value.rule = data.rule
    welcomeMarkSessionBaseline()
    saveCurrentChatCache()
    if (!quietToast) showToast('Приветствие сохранено')
    if (closeAfter) showWelcomeSettingsModal.value = false
    return true
  } catch {
    showToast(error.value || 'Не удалось сохранить приветствие')
    return false
  } finally {
    welcomeBusy.value = false
  }
}

async function saveWelcomeSettings() {
  await persistWelcomeSettings({ closeAfter: true, quietToast: false })
}

async function closeWelcomeSettingsModal() {
  if (!showWelcomeSettingsModal.value) return
  if (welcomeSessionIsDirty()) {
    await persistWelcomeSettings({ closeAfter: true, quietToast: false })
  } else {
    showWelcomeSettingsModal.value = false
  }
}

async function welcomeSaveButtonsFromModal() {
  const ok = await persistWelcomeSettings({ closeAfter: false, quietToast: true })
  if (ok) showToast('Кнопки сохранены')
}

async function openPostRulesSettings() {
  if (!chat.value?.rule) return
  ensureChatRuleShape(chat.value)
  postRulesGroupInfoOpen.value = false
  postRulesDraftNameDraft.value = ''
  postRulesDraftNameEditId.value = ''
  postRulesDraftNameDirty.value = false
  postRulesServerDirty.value = false
  postRulesShowSaved.value = false
  await postRulesHydrateDraftsFromServer()
  const cid = String(Number(chat.value?.id || 0) || 0)
  const lastDraftId = postRulesGetLastActiveDraftIdForChat(cid)
  const lastDraftRow =
    lastDraftId && cid
      ? (postRulesDrafts.value || []).find(
          (x) =>
            String(x?.id || '') === String(lastDraftId) &&
            String(x?.chatId || '') === cid &&
            String(x?.mode || 'group') === 'group',
        )
      : null
  postRulesGroupForm.value = {
    enabled: !!chat.value.rule.rules_group_enabled,
    text: String(chat.value.rule.rules_group_text || ''),
    pinOnSend: !!chat.value.rule.rules_group_pin_on_send,
    deletePinNotice: !!chat.value.rule.rules_group_delete_pin_notice,
    eventOnTrigger: !!chat.value.rule.rules_group_event_on_trigger,
    eventOnPunish: !!chat.value.rule.rules_group_event_on_punish,
    eventTriggerEveryN: Math.max(1, Math.min(500, Number(chat.value.rule.rules_group_event_trigger_every_n || 1))),
    eventPunishEveryN: Math.max(1, Math.min(500, Number(chat.value.rule.rules_group_event_punish_every_n || 1))),
  }
  postRulesGroupRunActiveId.value = String(chat.value.rule?.rules_group_active_draft_id || '')
  postRulesGroupButtonRows.value = postRulesKeyboardRowsFromRule(chat.value.rule.rules_group_buttons || [])
  postRulesActiveDraftId.value = ''
  showPostRulesGroupSendModal.value = false
  showPostRulesGroupFullPreview.value = false
  postRulesGroupFullPreviewRow.value = null
  showPostRulesSettingsModal.value = true
  await nextTick()
  postRulesEditorLoadFromForm({ silent: true, flush: true })
  await loadPostRulesPhotoPreview()
  await nextTick()
  if (lastDraftRow) {
    await postRulesApplyDraft(lastDraftRow, { quiet: true })
  } else {
    postRulesMarkServerBaseline()
    postRulesMarkDraftContentBaseline()
  }
}

function postRulesCurrentGroupTitle() {
  return String(chat.value?.title || '').trim() || `ID ${Number(chat.value?.id || 0)}`
}

async function loadPostRulesPhotoPreview() {
  if (!chat.value?.id) return
  try {
    const url = await fetchChatRulesPhotoPreviewUrl(chat.value.id, 'group')
    if (postRulesGroupPreviewUrl.value) revokeBroadcastMediaPreviewUrl(postRulesGroupPreviewUrl.value)
    postRulesGroupPreviewUrl.value = url
  } catch {
    if (postRulesGroupPreviewUrl.value) revokeBroadcastMediaPreviewUrl(postRulesGroupPreviewUrl.value)
    postRulesGroupPreviewUrl.value = ''
  }
}

async function onPostRulesPhotoPicked(event) {
  const f = event?.target?.files?.[0]
  event.target.value = ''
  if (!f || !chat.value?.id) return
  postRulesBusy.value = true
  try {
    await uploadChatRulesPhoto(chat.value.id, 'group', f)
    await loadPostRulesPhotoPreview()
    showToast('Фото для правил сохранено')
  } catch {
    showToast(error.value || 'Не удалось загрузить фото')
  } finally {
    postRulesBusy.value = false
    postRulesTouchServerDirty()
  }
}

async function removePostRulesPhoto(opts = {}) {
  const silent = !!opts?.silent
  if (!chat.value?.id) return
  postRulesBusy.value = true
  try {
    await fetchSilent(() => deleteChatRulesPhoto(chat.value.id, 'group'))
    if (postRulesGroupPreviewUrl.value) revokeBroadcastMediaPreviewUrl(postRulesGroupPreviewUrl.value)
    postRulesGroupPreviewUrl.value = ''
    if (!silent) showToast('Фото удалено')
  } catch {
    if (!silent) showToast(error.value || 'Не удалось удалить фото')
  } finally {
    postRulesBusy.value = false
    postRulesTouchServerDirty()
  }
}

async function savePostRulesSettings(opts = {}) {
  if (!chat.value?.rule || !chat.value?.id) return
  const skipResultToast = !!opts.skipResultToast
  postRulesSyncFormTextFromEditor()
  postRulesSaveBusy.value = true
  postRulesShowSaved.value = false
  const groupButtons = postRulesBuildKeyboardPayload(postRulesGroupButtonRows)
  const activeDraftIdForRun = String(postRulesGroupRunActiveId.value || '').trim()
  try {
    await updateRule(
      {
        rules_group_enabled: !!postRulesGroupForm.value.enabled,
        rules_group_text: String(postRulesGroupForm.value.text || '').slice(0, 4000),
        rules_group_buttons: groupButtons,
        rules_group_pin_on_send: !!postRulesGroupForm.value.pinOnSend,
        rules_group_delete_pin_notice: !!postRulesGroupForm.value.deletePinNotice,
        rules_group_event_on_trigger: !!postRulesGroupForm.value.eventOnTrigger,
        rules_group_event_on_punish: !!postRulesGroupForm.value.eventOnPunish,
        rules_group_event_trigger_every_n: Math.max(
          1,
          Math.min(500, Number(postRulesGroupForm.value.eventTriggerEveryN || 1)),
        ),
        rules_group_event_punish_every_n: Math.max(
          1,
          Math.min(500, Number(postRulesGroupForm.value.eventPunishEveryN || 1)),
        ),
        rules_group_active_draft_id: activeDraftIdForRun || null,
      },
      { quietToast: true },
    )
    chat.value.rule.rules_group_enabled = !!postRulesGroupForm.value.enabled
    chat.value.rule.rules_group_text = String(postRulesGroupForm.value.text || '').slice(0, 4000)
    chat.value.rule.rules_group_buttons = groupButtons
    chat.value.rule.rules_group_pin_on_send = !!postRulesGroupForm.value.pinOnSend
    chat.value.rule.rules_group_delete_pin_notice = !!postRulesGroupForm.value.deletePinNotice
    chat.value.rule.rules_group_event_on_trigger = !!postRulesGroupForm.value.eventOnTrigger
    chat.value.rule.rules_group_event_on_punish = !!postRulesGroupForm.value.eventOnPunish
    chat.value.rule.rules_group_event_trigger_every_n = Math.max(
      1,
      Math.min(500, Number(postRulesGroupForm.value.eventTriggerEveryN || 1)),
    )
    chat.value.rule.rules_group_event_punish_every_n = Math.max(
      1,
      Math.min(500, Number(postRulesGroupForm.value.eventPunishEveryN || 1)),
    )
    chat.value.rule.rules_group_active_draft_id = activeDraftIdForRun
    postRulesGroupRunActiveId.value = String(chat.value.rule?.rules_group_active_draft_id || activeDraftIdForRun || '')
    const activeId = String(postRulesActiveDraftId.value || '')
    if (activeId) {
      const cid = postRulesDraftChatKey()
      const modePhotoDataUrl = await postRulesPreviewToDataUrl('group')
      const nextPayload = {
        ...postRulesGroupForm.value,
        buttons: groupButtons,
        photoDataUrl: modePhotoDataUrl,
      }
      postRulesDrafts.value = (postRulesDrafts.value || []).map((x) => {
        if (String(x?.id || '') !== activeId) return x
        if (String(x?.chatId || '') !== cid) return x
        return { ...x, savedAt: Date.now(), payload: nextPayload }
      })
      postRulesPersistDrafts()
    }
    postRulesMarkServerBaseline()
    postRulesMarkDraftContentBaseline()
    if (!skipResultToast) {
      postRulesFlashSaved()
      showToast('Правила сохранены')
    }
    ensureChatRuleShape(chat.value)
    postRulesClearLastDraftForChat(chat.value.id)
  } finally {
    postRulesSaveBusy.value = false
  }
}

async function postRulesAutoSaveLocalDraftOnCloseBody() {
  if (!chat.value?.id) return
  const dirty = postRulesServerDirty.value || postRulesDraftNameDirty.value
  if (!dirty) return
  try {
    await postRulesSaveDraft({ silent: true })
  } catch {
    try {
      postRulesLoadDrafts()
    } catch {
      postRulesDrafts.value = []
    }
  }
}

async function closePostRulesSettingsModal() {
  postRulesSyncFormTextFromEditor()
  if (postRulesServerDirty.value) {
    try {
      await savePostRulesSettings()
    } catch {
      showToast(error.value || 'Не удалось сохранить настройки в Telegram')
      return
    }
  } else {
    await postRulesAutoSaveLocalDraftOnCloseBody()
  }
  postRulesRememberLastDraftForChat()
  showPostRulesSettingsModal.value = false
}

watch(showPostRulesSettingsModal, (open) => {
  if (!document?.body?.style) return
  document.body.style.overflow = open ? 'hidden' : ''
  if (!open) {
    postRulesGroupInfoOpen.value = false
    postRulesDraftNameEditId.value = ''
    postRulesDraftNameDraft.value = ''
    postRulesDraftNameDirty.value = false
    postRulesShowSaved.value = false
    showPostRulesGroupSendModal.value = false
    showPostRulesGroupFullPreview.value = false
    postRulesGroupFullPreviewRow.value = null
  }
})

async function postRulesDoGroupSendNow() {
  if (!chat.value?.id) return
  postRulesSendBusy.value = true
  try {
    if (postRulesServerDirty.value) {
      await savePostRulesSettings()
    }
    await fetchSilent(() => api.sendChatRulesNow(chat.value.id, {
      target: 'group',
      pin: !!postRulesGroupForm.value.pinOnSend,
      delete_pin_notice: !!postRulesGroupForm.value.deletePinNotice,
    }))
    showToast(postRulesGroupForm.value.pinOnSend ? 'Правила отправлены и закреплены' : 'Правила отправлены')
  } catch {
    showToast(error.value || 'Не удалось отправить правила')
  } finally {
    postRulesSendBusy.value = false
  }
}

async function sendPostRulesNowGroup() {
  if (!chat.value?.id) return
  if (postRulesDraftsForChat.value.length) {
    postRulesGroupSendPickId.value = postRulesGroupDefaultSendPickId()
    showPostRulesGroupSendModal.value = true
    return
  }
  return postRulesDoGroupSendNow()
}

async function postRulesConfirmGroupSendFromModal() {
  if (!chat.value?.id) return
  const list = postRulesDraftsForChat.value
  const id = String(postRulesGroupSendPickId.value || '')
  const d = list.find((x) => String(x?.id || '') === id) || null
  if (!d) {
    showPostRulesGroupSendModal.value = false
    return
  }
  postRulesSendBusy.value = true
  try {
    await postRulesApplyDraft(d, { quiet: true })
    await savePostRulesSettings({ skipResultToast: true })
    await fetchSilent(() => api.sendChatRulesNow(chat.value.id, {
      target: 'group',
      pin: !!postRulesGroupForm.value.pinOnSend,
      delete_pin_notice: !!postRulesGroupForm.value.deletePinNotice,
    }))
    showToast(postRulesGroupForm.value.pinOnSend ? 'Правила отправлены и закреплены' : 'Правила отправлены')
    showPostRulesGroupSendModal.value = false
  } catch {
    showToast(error.value || 'Не удалось отправить правила')
  } finally {
    postRulesSendBusy.value = false
  }
}

async function addLinkBlacklistPattern() {
  const p = (newLinkBlacklistPattern.value || '').trim()
  if (!p || !chat.value?.id || chat.value.noSelection) return
  if (!canUsePremiumForCurrentChat.value) {
    openFreeLimitsPremiumModal()
    return
  }
  linkBlacklistLoading.value = true
  try {
    const res = await fetchSilent(() => api.addLinkBlacklistPattern(chat.value.id, p))
    mergeLinkBlacklistFromResponse(res)
    newLinkBlacklistPattern.value = ''
    showToast('Добавлено в чёрный список')
  } catch {
    showToast(error.value || 'Не удалось добавить')
  } finally {
    linkBlacklistLoading.value = false
  }
}

async function removeLinkBlacklistPattern(pat) {
  if (!chat.value?.id) return
  linkBlacklistLoading.value = true
  try {
    const res = await fetchSilent(() => api.deleteLinkBlacklistPattern(chat.value.id, pat))
    mergeLinkBlacklistFromResponse(res)
    showToast('Удалено из чёрного списка')
  } catch {
    showToast(error.value || 'Не удалось удалить')
  } finally {
    linkBlacklistLoading.value = false
  }
}

async function addWhitelistDomain() {
  const d = (newWhitelistDomain.value || '').trim()
  if (!d || !chat.value?.id || chat.value.noSelection) return
  whitelistLoading.value = true
  try {
    const res = await fetchSilent(() => api.addWhitelistDomain(chat.value.id, d))
    mergeWhitelistFromResponse(res)
    newWhitelistDomain.value = ''
    showToast('Домен добавлен в доверенные')
  } catch {
    showToast(error.value || 'Не удалось добавить домен')
  } finally {
    whitelistLoading.value = false
  }
}

async function removeWhitelistDomain(domain) {
  if (!chat.value?.id) return
  whitelistLoading.value = true
  try {
    const res = await fetchSilent(() => api.deleteWhitelistDomain(chat.value.id, domain))
    mergeWhitelistFromResponse(res)
    showToast('Домен удалён')
  } catch {
    showToast(error.value || 'Не удалось удалить')
  } finally {
    whitelistLoading.value = false
  }
}

async function addWhitelistUser() {
  const raw = (newWhitelistUserId.value || '').trim()
  if (!raw || !chat.value?.id || chat.value.noSelection) {
    showToast('Укажи Telegram ID или @username')
    return
  }
  whitelistLoading.value = true
  try {
    const res = await fetchSilent(() => api.addWhitelistUser(chat.value.id, raw))
    mergeWhitelistFromResponse(res)
    newWhitelistUserId.value = ''
    showToast('Пользователь может слать ссылки без фильтра')
  } catch {
    showToast(error.value || 'Не удалось добавить пользователя')
  } finally {
    whitelistLoading.value = false
  }
}

async function removeWhitelistUser(uid) {
  if (!chat.value?.id) return
  whitelistLoading.value = true
  try {
    const res = await fetchSilent(() => api.deleteWhitelistUser(chat.value.id, uid))
    mergeWhitelistFromResponse(res)
    showToast('Удалено из доверенных')
  } catch {
    showToast(error.value || 'Не удалось удалить')
  } finally {
    whitelistLoading.value = false
  }
}

async function addWhitelistSenderChat() {
  const raw = (newWhitelistSenderChat.value || '').trim()
  if (!raw || !chat.value?.id || chat.value.noSelection) {
    showToast('Укажи @username канала')
    return
  }
  whitelistLoading.value = true
  try {
    const res = await fetchSilent(() => api.addWhitelistSenderChat(chat.value.id, raw))
    mergeWhitelistFromResponse(res)
    newWhitelistSenderChat.value = ''
    showToast('Канал добавлен в доверенные')
  } catch {
    showToast(error.value || 'Не удалось добавить канал')
  } finally {
    whitelistLoading.value = false
  }
}

async function removeWhitelistSenderChat(uname) {
  if (!chat.value?.id) return
  whitelistLoading.value = true
  try {
    const res = await fetchSilent(() => api.deleteWhitelistSenderChat(chat.value.id, uname))
    mergeWhitelistFromResponse(res)
    showToast('Канал удалён из доверенных')
  } catch {
    showToast(error.value || 'Не удалось удалить канал')
  } finally {
    whitelistLoading.value = false
  }
}

const actionOptions = [
  { value: 'delete', label: 'Удалить', hint: 'мягко' },
  { value: 'mute', label: 'Мут + удалить', hint: 'средне' },
  { value: 'ban', label: 'Бан', hint: 'жёстко' },
  { value: 'observe', label: 'Заметить', hint: 'без удаления' },
]

const mutePresets = [
  { value: 5, label: '5' },
  { value: 10, label: '10' },
  { value: 30, label: '30' },
  { value: 60, label: '60' },
  { value: 1440, label: '1 день' },
]
const newbiePresets = [5, 10, 15, 30, 60]
const joinCaptchaTtlPresets = [1, 2, 3, 4, 5]
const joinCaptchaKinds = [
  { value: 'button', label: 'Кнопки' },
  { value: 'math', label: 'Счёт' },
  { value: 'emoji', label: 'Эмодзи' },
  { value: 'word_emoji', label: 'Слово → эмодзи' },
  { value: 'digits', label: 'Цифры' },
  { value: 'word_send', label: 'Повтори слово' },
  { value: 'word_guess', label: 'Отгадай слово' },
]
// Синхронно с app/handlers/panel_dm.py — _kb_filter_silence (SILENCE_OPTIONS), сетка 2×N + «Отключить»
const silencePresets = [
  { value: 10, label: '10 минут' },
  { value: 60, label: '1 час' },
  { value: 120, label: '2 часа' },
  { value: 180, label: '3 часа' },
  { value: 240, label: '4 часа' },
  { value: 360, label: '6 часов' },
  { value: 480, label: '8 часов' },
  { value: 600, label: '10 часов' },
  { value: 720, label: '12 часов' },
  { value: 1440, label: '1 день' },
]
const antinakrutkaThresholdPresets = [5, 10, 15, 20]
const antinakrutkaWindowPresets = [3, 5, 10]
const antinakrutkaActionOptions = [
  { value: 'alert', label: 'Только оповещение' },
  { value: 'alert_restrict', label: 'Оповещение + мут' },
]
const antinakrutkaRestrictPresets = [15, 30, 60]
const antinakrutkaModePresets = [
  { key: 'soft', label: 'Мягко', threshold: 20, window: 3, action: 'alert', restrict: 30 },
  { key: 'standard', label: 'Стандарт', threshold: 10, window: 5, action: 'alert_restrict', restrict: 30 },
  { key: 'hard', label: 'Жёстко', threshold: 5, window: 10, action: 'alert_restrict', restrict: 60 },
]

const publicAlertsEveryPresets = [
  { n: 3, label: '3' },
  { n: 5, label: '5' },
  { n: 10, label: '10' },
  { n: 15, label: '15' },
  { n: 20, label: '20' },
]
const publicAlertsIntervalPresets = [
  { sec: 120, label: '2 мин' },
  { sec: 300, label: '5 мин' },
  { sec: 600, label: '10 мин' },
  { sec: 1800, label: '30 мин' },
  { sec: 3600, label: '1 ч' },
  { sec: 7200, label: '2 ч' },
]
const guardianPeriodicIntervalPresets = [
  { h: 24, label: '24ч' },
  { h: 48, label: '48ч' },
  { h: 72, label: '72ч' },
  { h: 168, label: '7д' },
]
const publicAlertsStyleOptions = [
  { value: 'soft', label: 'Мягко', hint: 'нейтральные формулировки' },
  { value: 'medium', label: 'Средне', hint: 'делово, без сленга' },
  { value: 'guard', label: 'Guard', hint: 'фирменный тон Guard' },
]
const publicAlertsStyleLabelMap = {
  soft: 'Мягко',
  medium: 'Средне',
  guard: 'Guard',
}
const publicAlertsCategoryExamplesByStyle = {
  soft: {
    spam: ['Мы убрали сообщение, которое не подошло по правилам. Если вопросы — напишите админам.', 'Одно сообщение удалено, чтобы чат оставался комфортным.'],
    link: ['Сообщение со ссылкой снято — так настроена защита чата.'],
    bad_words: ['Сообщение снято: в чате действует фильтр по выражениям.'],
    mute: ['Участнику временно ограничили отправку сообщений.'],
    ban: ['Участник покинул чат по решению защиты.'],
    generic: ['Защита чата обработала нарушение.', 'Сообщение не прошло проверку и было убрано.'],
  },
  medium: {
    spam: ['Спам удалён. Спасибо за порядок в чате.', 'Лишнее сообщение убрано модерацией.'],
    link: ['Сообщение со ссылкой удалено по правилам чата.', 'Ссылка не разрешена — сообщение снято.'],
    bad_words: ['Сообщение с ненормативной лексикой удалено.', 'Нарушение правил по языку — пост убран.'],
    mute: ['Участник ограничен по правилам чата.', 'Применено временное ограничение.'],
    ban: ['Участник исключён из чата по правилам.', 'Доступ участника к чату прекращён.'],
    generic: ['Сообщение обработано модерацией.', 'Правила чата применены.'],
  },
  guard: {
    spam: ['😈 Guard зачистил спам. Чат дышит свободнее.', '🧹 Спам снесён. Помойка закрыта.', '🚫 Ещё пачка мусора уничтожена.'],
    link: ['🔗 Левые ссылки срезаны. Проход закрыт.', '⚔ Guard распилил очередную партию ссылок.'],
    bad_words: ['🤬 Матершинник был снесён. Следи за языком.', '🪓 Грязный язык зачищен.'],
    mute: ['🔇 Нарушитель притих. В чате снова порядок.', '⛓ Один шумный пассажир отправлен остывать.'],
    ban: ['☠ Спамер выброшен за борт.', '🚪 Ещё один мусорный гость вылетел из чата.'],
    generic: ['😈 Guard продолжает зачистку.', '🛡 Порядок восстановлен.'],
  },
}
const currentPublicAlertsStyle = computed(() => {
  const st = String(chat.value?.rule?.public_alerts_style || 'guard').toLowerCase()
  return ['soft', 'medium', 'guard'].includes(st) ? st : 'guard'
})
const currentPublicAlertsStyleLabel = computed(() => publicAlertsStyleLabelMap[currentPublicAlertsStyle.value] || 'Guard')
const currentPublicAlertsExamples = computed(() => publicAlertsCategoryExamplesByStyle[currentPublicAlertsStyle.value] || publicAlertsCategoryExamplesByStyle.guard)
const guardianPeriodicExamples = [
  '😈 AntiSpam Guard на месте. Пока всё спокойно. Спамеров не обнаружено. Но если появятся — разберусь.',
  '🛡 AntiSpam Guard проверил чат. Спам не обнаружен. Можно продолжать общаться спокойно.',
  '😈 Я здесь. Слежу за ссылками, ботами и подозрительными сообщениями. Если кто-то решит спамить — долго не проживёт.',
  '🛡 Guard проверяет чат. Если заметите странные ссылки — можете не переживать. Я их тоже вижу.',
  '😈 AntiSpam Guard на дежурстве. Порядок в чате поддерживается автоматически.',
]

async function togglePublicAlerts(on) {
  if (!chat.value?.rule) return
  guardLog('Protection', 'togglePublicAlerts', { on, chatId: chat.value.id })
  await updateRule({ public_alerts_enabled: !!on })
}

async function toggleGuardianPeriodic(on) {
  if (!chat.value?.rule) return
  if (!canUsePremiumForCurrentChat.value) {
    openFreeLimitsPremiumModal()
    return
  }
  await updateRule({ guardian_periodic_enabled: !!on })
}

async function applyAntinakrutkaPreset(preset) {
  if (!chat.value?.rule) return
  if (!canUsePremiumForCurrentChat.value) {
    openFreeLimitsPremiumModal()
    return
  }
  await updateRule({
    antinakrutka_enabled: true,
    antinakrutka_joins_threshold: preset.threshold,
    antinakrutka_window_minutes: preset.window,
    antinakrutka_action: preset.action,
    antinakrutka_restrict_minutes: preset.restrict,
  })
}

/** Панели: тёмное «жидкое стекло» — градиент, внутренний блик, кольцо */
const protCard =
  'rounded-2xl border border-white/[0.11] bg-gradient-to-br from-white/[0.1] via-white/[0.04] to-black/25 p-3 text-slate-100 shadow-[0_10px_40px_-12px_rgba(0,0,0,0.65),inset_0_1px_0_rgba(255,255,255,0.11),inset_0_-1px_0_rgba(0,0,0,0.18)] backdrop-blur-xl ring-1 ring-amber-500/[0.04]'
/** Полоса выбора чата: «жидкое стекло», без холодного синего обода */
const protCardChatBar =
  'rounded-xl border border-white/[0.11] bg-gradient-to-br from-white/[0.09] via-zinc-950/55 to-black/55 p-2.5 text-slate-100 shadow-[0_14px_40px_-14px_rgba(0,0,0,0.75),inset_0_1px_0_rgba(255,255,255,0.12),inset_0_-1px_0_rgba(0,0,0,0.2)] backdrop-blur-xl backdrop-saturate-150 ring-1 ring-inset ring-white/[0.05]'
const protCardSub =
  'rounded-2xl border border-white/[0.09] bg-gradient-to-br from-white/[0.07] via-white/[0.03] to-black/20 p-3 text-slate-200 shadow-[0_8px_28px_-12px_rgba(0,0,0,0.55),inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-lg ring-1 ring-white/[0.05]'
/** Выключенный хвост переключателей / пресетов — стекло, не «серый пластик» */
const protToggleOff =
  'border border-white/12 bg-white/[0.06] text-zinc-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.07)] backdrop-blur-sm hover:border-white/18 hover:bg-white/[0.09]'
const protCardDanger =
  'rounded-2xl border border-rose-400/18 bg-gradient-to-br from-rose-950/50 via-rose-950/30 to-black/30 p-3 text-slate-100 shadow-[0_8px_32px_-12px_rgba(0,0,0,0.55),inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-xl ring-1 ring-rose-400/[0.07]'
const protCardSky =
  'rounded-2xl border border-sky-400/16 bg-gradient-to-br from-sky-950/45 via-sky-950/25 to-black/25 p-3 text-slate-100 shadow-[0_8px_32px_-12px_rgba(0,0,0,0.55),inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-xl ring-1 ring-sky-400/[0.06]'
const protCardIndigo =
  'rounded-2xl border border-violet-400/14 bg-gradient-to-br from-violet-950/40 via-violet-950/22 to-black/25 p-3 text-slate-100 shadow-[0_8px_32px_-12px_rgba(0,0,0,0.55),inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-xl ring-1 ring-violet-400/[0.06]'
</script>

<template>
  <div>
    <div
      class="relative isolate -mx-4 min-h-0 px-4 pb-8 font-display md:-mx-6 md:px-6 md:pb-10"
    >
      <div class="relative z-[2] space-y-4 pt-1 text-[13px] leading-snug md:pt-2">
    <div class="flex items-center justify-between gap-2">
      <h1 class="text-lg font-semibold text-white drop-shadow-sm md:text-xl">Защита</h1>
      <span
        v-if="switchChatBusy"
        class="pointer-events-none inline-flex shrink-0 items-center gap-1.5 rounded-full border border-cyan-300/35 bg-cyan-500/15 px-2.5 py-1 text-xs font-semibold text-cyan-100 shadow-[0_0_18px_-10px_rgba(34,211,238,0.9)]"
        aria-live="polite"
      ><span class="inline-block hourglass-flip">⏳</span>Переключаю чат…</span>
    </div>

    <div v-if="!hasInitData" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
      Откройте панель из Telegram.
    </div>

    <div v-else-if="chat?.noSelection" :class="protCard">
      <p class="text-xs text-slate-300">Сначала выберите чат в разделе «Подключённые чаты».</p>
      <button
        type="button"
        class="guard-green-soft mt-3 rounded-lg px-3 py-1.5 text-xs font-semibold"
        @click="router.push(cabinetMode === 'delegated' ? { path: '/chats', query: { cabinet: 'delegated' } } : '/chats')"
      >
        К списку чатов
      </button>
    </div>

    <div v-else-if="chat?.loadError || error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
      {{ error || 'Не удалось загрузить настройки' }}
    </div>

    <div v-else-if="chat?.rule" class="space-y-3.5">
      <!-- Только полоса чата липнет под шапкой App (h-14). Плашка «под угрозой» ниже — обычный скролл. -->
      <div
        class="sticky top-14 z-[28] -mx-4 px-4 py-2 md:-mx-6 md:px-6"
      >
        <div :class="protCardChatBar">
          <div class="flex items-center gap-1.5">
            <div
              class="guard-green-chip min-w-0 flex-1 rounded-xl border border-emerald-300/40 px-2.5 py-2 text-xs font-semibold shadow-[0_0_28px_-10px_rgba(163,230,53,0.45)] ring-1 ring-lime-200/25"
            >
              <span class="block truncate">{{ selectedChatTitle }}</span>
            </div>
            <button
              type="button"
              class="shrink-0 rounded-xl border border-white/[0.14] bg-white/[0.07] px-2.5 py-2 text-xs font-semibold text-slate-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.1)] backdrop-blur-md transition hover:border-white/22 hover:bg-white/[0.12]"
              @click="openChatPicker"
            >
              Выбор чата
            </button>
            <button
              type="button"
              class="prot-info-btn chatbar-info-btn shrink-0"
              aria-label="Как работает выбор чата"
              @click="showChatSwitchInfoModal = true"
            >
              i
            </button>
          </div>
        </div>
      </div>
      <div
        v-if="currentSpikeAlert"
        class="rounded-xl border border-yellow-400/45 bg-yellow-950/25 p-2.5 text-[11px] text-yellow-100 shadow-[0_0_16px_-10px_rgba(250,204,21,0.9)]"
      >
        <p class="font-semibold uppercase tracking-wide"><span class="mr-1 text-base text-orange-300">⚠</span>Статус: чат под угрозой</p>
        <p class="mt-1 text-yellow-100/90">
          За {{ currentSpikeAlert.window_min }} мин: всплеск срабатываний фильтров ({{ currentSpikeAlert.spam_count }}), подключений: {{ currentSpikeAlert.joins_count }}.
        </p>
        <p class="mt-1 text-yellow-100/80">Рекомендуем усилить:</p>
        <ul class="mt-0.5 list-disc space-y-0.5 pl-4 text-yellow-100/90">
          <li v-for="(rec, ri) in (currentSpikeAlert.recommendations || [])" :key="`spike-rec-${ri}`">{{ rec }}</li>
        </ul>
        <button
          type="button"
          class="mt-2 rounded-lg border border-yellow-300/60 bg-yellow-400/20 px-2.5 py-1 text-[11px] font-semibold text-yellow-100 hover:bg-yellow-400/30"
          @click="applySpikeRecommendedSettings"
        >
          Применить рекомендуемые настройки
        </button>
      </div>

      <!-- Модалка выбора чата снизу -->
      <div
        v-if="showChatPicker"
        class="fixed inset-0 z-[300] flex items-end justify-center bg-black/70 p-0 pb-[calc(5rem+env(safe-area-inset-bottom,0px))] md:items-end md:pb-6"
        @click="showChatPicker = false"
      >
        <div
          class="flex h-[min(78vh,36rem)] w-full max-w-lg min-h-0 flex-col rounded-t-3xl border border-white/15 border-b-0 bg-gradient-to-b from-slate-900/95 via-slate-950/95 to-black/95 px-3 pb-4 pt-2 text-slate-100 shadow-[0_-20px_60px_-16px_rgba(0,0,0,0.9),inset_0_1px_0_rgba(255,255,255,0.12)] backdrop-blur-2xl ring-1 ring-white/10 md:mx-2 md:rounded-3xl md:border-b md:pb-3"
          @click.stop
        >
          <div class="mx-auto mb-2 h-1 w-12 shrink-0 rounded-full bg-white/30 md:hidden" aria-hidden="true" />
          <div class="mb-2 flex shrink-0 items-center justify-between gap-2 border-b border-white/10 pb-2.5">
            <p class="text-sm font-semibold tracking-wide text-white/95">Выбор чата</p>
            <button
              type="button"
              class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 transition hover:bg-white/10 hover:text-white"
              @click="showChatPicker = false"
            >
              Закрыть
            </button>
          </div>
          <template v-if="chatsListLoading">
            <div class="flex min-h-0 flex-1 items-center justify-center px-2 py-2">
              <div class="w-full rounded-2xl border border-white/10 bg-white/[0.04] p-4 text-center">
                <div class="mx-auto mb-2 inline-flex items-center gap-2 rounded-full border border-emerald-300/35 bg-emerald-500/12 px-3 py-1.5 text-xs font-semibold text-emerald-100 shadow-[0_0_20px_-10px_rgba(16,185,129,0.9)]">
                  <span class="inline-block hourglass-flip">⏳</span>
                  Загружаю выбор чата…
                </div>
                <div class="space-y-2.5">
                  <div class="mx-auto h-3 w-2/3 max-w-[14rem] animate-pulse rounded bg-white/15" />
                  <div class="h-14 animate-pulse rounded-xl bg-white/10" />
                  <div class="h-14 animate-pulse rounded-xl bg-white/10" />
                </div>
              </div>
            </div>
          </template>
          <template v-else-if="(chatsList || []).length > 0">
            <div class="mb-2.5 shrink-0 rounded-2xl border border-white/10 bg-white/[0.04] px-3 py-2">
              <p class="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                Всего групп: {{ pickerTotalChats }} · Активных: {{ pickerActiveChats }}
              </p>
            </div>
            <div
              class="min-h-0 flex-1 space-y-1.5 overflow-y-auto overscroll-contain py-1 pr-0.5 touch-pan-y"
              style="-webkit-overflow-scrolling: touch;"
            >
              <div v-if="pickerDelegatedChats.length" class="space-y-1.5">
                <p class="px-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-violet-300">Делегированные</p>
                <button
                  v-for="c in pickerDelegatedChats"
                  :key="`pick-shared-${c.id}`"
                  type="button"
                  :class="[
                    Number(c.id) === Number(selectedChatId) && !c.locked_by_limit
                      ? 'border-violet-200/90 bg-violet-500/45 text-white shadow-[0_0_32px_-8px_rgba(167,139,250,1)] ring-1 ring-violet-200/70'
                      : '',
                    c.locked_by_limit
                      ? 'border border-amber-300/35 bg-amber-900/20 text-amber-100'
                      : 'border border-violet-300/25 bg-violet-900/20 text-slate-100 hover:bg-violet-900/30',
                  ]"
                  class="flex w-full items-center justify-between gap-2 rounded-2xl px-3 py-3 text-left text-sm backdrop-blur-xl transition"
                  @click="switchChat(c.id)"
                >
                  <span class="min-w-0 flex-1">
                    <span class="block truncate font-medium">{{ c.title }}</span>
                    <span v-if="c.locked_by_limit" class="block text-[10px] font-semibold uppercase tracking-wide text-amber-300">
                      Лимит Free: нужен Premium
                    </span>
                  </span>
                  <div class="shrink-0 flex items-center gap-1.5">
                    <button
                      type="button"
                      class="rounded-md border px-2 py-0.5 text-[10px] font-semibold"
                      :class="
                        c.locked_by_limit
                          ? 'border-amber-300/45 bg-amber-900/35 text-amber-100 opacity-80'
                          : !delegatedCanProtection(c)
                            ? 'border-slate-500/35 bg-slate-800/45 text-slate-300 opacity-85'
                            : pickerProtectionOn(c)
                              ? 'border-lime-300/55 bg-lime-500/20 text-lime-100'
                              : 'border-slate-400/35 bg-slate-700/35 text-slate-200'
                      "
                      :disabled="c.locked_by_limit || !delegatedCanProtection(c) || !!pickerToggleBusyByChat[Number(c.id)]"
                      @click.stop="toggleChatProtectionFromPicker(c)"
                    >
                      <span v-if="pickerToggleBusyByChat[Number(c.id)]" class="inline-block hourglass-flip">⏳</span>
                      <span v-else>{{ !delegatedCanProtection(c) ? 'Нет доступа' : (pickerProtectionOn(c) ? 'Активна' : 'На паузе') }}</span>
                    </button>
                    <span
                      v-if="c.locked_by_limit"
                      class="rounded-md border border-amber-300/50 bg-amber-800/35 px-2 py-0.5 text-[10px] font-semibold text-amber-50"
                    >
                      Premium
                    </span>
                    <span
                      v-if="spikeAlertsByChat[Number(c.id)]"
                      class="text-[18px] leading-none text-orange-300 drop-shadow-[0_0_12px_rgba(251,146,60,0.85)]"
                      title="В чате сейчас всплеск"
                    >⚠</span>
                  </div>
                </button>
              </div>
              <div v-if="pickerOwnChats.length" class="space-y-1.5 pt-1.5">
                <p class="px-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-cyan-300">Мои чаты</p>
                <button
                  v-for="c in pickerOwnChats"
                  :key="`pick-own-${c.id}`"
                  type="button"
                  :class="[
                    Number(c.id) === Number(selectedChatId) && !c.locked_by_limit
                      ? 'border-emerald-200/90 bg-emerald-500/45 text-white shadow-[0_0_32px_-8px_rgba(16,185,129,1)] ring-1 ring-emerald-200/70'
                      : '',
                    c.locked_by_limit
                      ? 'border border-amber-300/35 bg-amber-900/20 text-amber-100'
                      : 'border border-white/10 bg-white/[0.04] text-slate-100 hover:bg-white/[0.08]',
                  ]"
                  class="flex w-full items-center justify-between gap-2 rounded-2xl px-3 py-3 text-left text-sm backdrop-blur-xl transition"
                  @click="switchChat(c.id)"
                >
                  <span class="min-w-0 flex-1">
                    <span class="block truncate font-medium">{{ c.title }}</span>
                    <span v-if="c.locked_by_limit" class="block text-[10px] font-semibold uppercase tracking-wide text-amber-300">
                      Лимит Free: нужен Premium
                    </span>
                  </span>
                  <div class="shrink-0 flex items-center gap-1.5">
                    <button
                      type="button"
                      class="rounded-md border px-2 py-0.5 text-[10px] font-semibold"
                      :class="
                        c.locked_by_limit
                          ? 'border-amber-300/45 bg-amber-900/35 text-amber-100 opacity-80'
                          : !delegatedCanProtection(c)
                            ? 'border-slate-500/35 bg-slate-800/45 text-slate-300 opacity-85'
                            : pickerProtectionOn(c)
                              ? 'border-lime-300/55 bg-lime-500/20 text-lime-100'
                              : 'border-slate-400/35 bg-slate-700/35 text-slate-200'
                      "
                      :disabled="c.locked_by_limit || !delegatedCanProtection(c) || !!pickerToggleBusyByChat[Number(c.id)]"
                      @click.stop="toggleChatProtectionFromPicker(c)"
                    >
                      <span v-if="pickerToggleBusyByChat[Number(c.id)]" class="inline-block hourglass-flip">⏳</span>
                      <span v-else>{{ !delegatedCanProtection(c) ? 'Нет доступа' : (pickerProtectionOn(c) ? 'Активна' : 'На паузе') }}</span>
                    </button>
                    <span
                      v-if="c.locked_by_limit"
                      class="rounded-md border border-amber-300/50 bg-amber-800/35 px-2 py-0.5 text-[10px] font-semibold text-amber-50"
                    >
                      Premium
                    </span>
                    <span
                      v-if="spikeAlertsByChat[Number(c.id)]"
                      class="text-[18px] leading-none text-orange-300 drop-shadow-[0_0_12px_rgba(251,146,60,0.85)]"
                      title="В чате сейчас всплеск"
                    >⚠</span>
                  </div>
                </button>
              </div>
            </div>
          </template>
          <div v-else class="flex min-h-0 flex-1 items-center justify-center px-2 py-2">
            <div class="w-full rounded-2xl border border-white/10 bg-white/[0.04] p-4 text-center">
              <div class="mx-auto mb-2 inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/8 px-3 py-1.5 text-xs font-semibold text-slate-100 shadow-[0_0_20px_-10px_rgba(255,255,255,0.4)]">
                <span class="inline-block hourglass-flip">⏳</span>
                Подгружаю список чатов…
              </div>
              <div class="space-y-2.5">
                <div class="mx-auto h-3 w-2/3 max-w-[14rem] animate-pulse rounded bg-white/15" />
                <div class="h-14 animate-pulse rounded-xl bg-white/10" />
                <div class="h-14 animate-pulse rounded-xl bg-white/10" />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Основное -->
      <section :class="[protCard, 'relative z-0']">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h2 class="text-xs font-medium uppercase tracking-wide text-slate-200">Основное</h2>
          <button
            type="button"
            class="prot-info-btn"
            aria-label="Что делает переключатель защиты"
            @click="showMainInfoModal = true"
          >
            i
          </button>
        </div>
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            :class="boolToggleClass(chat.rule.master_anti_spam)"
            class="rounded-xl px-3 py-1.5 text-xs font-semibold"
            @click="toggleMasterProtection()"
          >
            {{ chat.rule.master_anti_spam ? '✅ Guard активен' : '⏸ Guard на паузе' }}
          </button>
        </div>
      </section>

      <!-- Фильтры -->
      <section :class="protCard">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h2 class="text-xs font-medium text-slate-200">Фильтры</h2>
          <button
            type="button"
            class="prot-info-btn"
            aria-label="Информация по фильтрам"
            @click="showFiltersInfoModal = true"
          >
            i
          </button>
        </div>
        <div class="space-y-3">
          <p class="text-[11px] leading-relaxed text-slate-500">
            Настройки открываются в отдельных окнах — так спокойнее крутить режимы и белые списки без простыни кнопок.
          </p>
          <div class="grid grid-cols-2 gap-2">
            <button
              type="button"
              class="group flex flex-col items-start rounded-xl border border-white/12 bg-gradient-to-br from-sky-500/15 to-indigo-600/10 p-3 text-left shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_6px_24px_-12px_rgba(0,0,0,0.45)] ring-1 ring-inset ring-white/[0.06] transition hover:border-sky-400/40 hover:shadow-md active:scale-[0.99]"
              @click="showLinksFilterModal = true"
            >
              <span class="text-lg leading-none">🔗</span>
              <span class="mt-1.5 text-xs font-semibold text-slate-100">Ссылки</span>
              <span class="mt-0.5 line-clamp-2 text-[10px] text-slate-400">{{ linkModeSummary }}</span>
            </button>
            <button
              type="button"
              class="group flex flex-col items-start rounded-xl border border-white/12 bg-gradient-to-br from-violet-500/15 to-fuchsia-600/10 p-3 text-left shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_6px_24px_-12px_rgba(0,0,0,0.45)] ring-1 ring-inset ring-white/[0.06] transition hover:border-violet-400/40 hover:shadow-md active:scale-[0.99]"
              @click="showMentionsFilterModal = true"
            >
              <span class="text-lg leading-none">@</span>
              <span class="mt-1.5 text-xs font-semibold text-slate-100">Упоминания</span>
              <span class="mt-0.5 line-clamp-2 text-[10px] text-slate-400">{{ mentionsSummary }}</span>
            </button>
            <button
              type="button"
              class="group flex flex-col items-start rounded-xl border border-white/12 bg-gradient-to-br from-amber-500/15 to-orange-600/10 p-3 text-left shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_6px_24px_-12px_rgba(0,0,0,0.45)] ring-1 ring-inset ring-white/[0.06] transition hover:border-amber-400/40 hover:shadow-md active:scale-[0.99]"
              @click="showMediaFilterModal = true"
            >
              <span class="text-lg leading-none">🖼</span>
              <span class="mt-1.5 text-xs font-semibold text-slate-100">Медиа</span>
              <span class="mt-0.5 line-clamp-2 text-[10px] text-slate-400">{{ mediaSummary }}</span>
            </button>
            <button
              type="button"
              class="group flex flex-col items-start rounded-xl border border-white/12 bg-gradient-to-br from-emerald-500/15 to-teal-600/10 p-3 text-left shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_6px_24px_-12px_rgba(0,0,0,0.45)] ring-1 ring-inset ring-white/[0.06] transition hover:border-emerald-400/40 hover:shadow-md active:scale-[0.99]"
              @click="showButtonsFilterModal = true"
            >
              <span class="text-lg leading-none">🔘</span>
              <span class="mt-1.5 text-xs font-semibold text-slate-100">Кнопки</span>
              <span class="mt-0.5 line-clamp-2 text-[10px] text-slate-400">{{ buttonsSummary }}</span>
            </button>
            <button
              type="button"
              class="group col-span-2 flex flex-col items-start rounded-xl border border-white/12 bg-gradient-to-br from-fuchsia-500/15 to-indigo-600/10 p-3 text-left shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_6px_24px_-12px_rgba(0,0,0,0.45)] ring-1 ring-inset ring-white/[0.06] transition hover:border-fuchsia-400/40 hover:shadow-md active:scale-[0.99]"
              @click="showChannelPostsFilterModal = true"
            >
              <span class="text-lg leading-none">📣</span>
              <span class="mt-1.5 text-xs font-semibold text-slate-100">Сообщения от каналов</span>
              <span class="mt-0.5 line-clamp-2 text-[10px] text-slate-400">{{ channelPostsSummary }}</span>
            </button>
          </div>
          <div class="flex items-center justify-between gap-2 pt-1">
            <span class="text-xs text-slate-300">Удалять сообщения «вступил в группу»</span>
            <button
              type="button"
            :class="boolToggleClass(chat.rule.delete_join_messages)"
              class="min-w-[5rem] rounded-lg px-2.5 py-1 text-xs font-medium"
              @click="updateRule({ delete_join_messages: !chat.rule.delete_join_messages })"
            >
              {{ chat.rule.delete_join_messages ? 'Да' : 'Нет' }}
            </button>
          </div>
          <div class="flex items-center justify-between gap-2 pt-1">
            <span class="text-xs text-slate-300">Удалять сообщения «покинул группу»</span>
              <button
                type="button"
            :class="boolToggleClass(chat.rule.delete_left_messages)"
              class="min-w-[5rem] rounded-lg px-2.5 py-1 text-xs font-medium"
              @click="updateRule({ delete_left_messages: !chat.rule.delete_left_messages })"
            >
              {{ chat.rule.delete_left_messages ? 'Да' : 'Нет' }}
              </button>
            </div>
          <div :class="protCardSub">
            <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h3 class="text-xs font-medium text-slate-200">🧠 Стоп-слова</h3>
              <div class="flex items-center gap-1.5">
                <button
                  v-if="(chat.stopwords || []).length"
                  type="button"
                  class="inline-flex items-center gap-1.5 rounded-full border border-cyan-400/50 bg-gradient-to-r from-cyan-500/25 to-sky-600/20 px-3 py-1 text-[11px] font-semibold text-cyan-100 shadow-[0_0_20px_-8px_rgba(34,211,238,0.6)] transition hover:border-cyan-300/80 hover:from-cyan-500/35"
                  @click="showStopwordsModal = true"
                >
                  Все слова
                  <span
                    class="rounded-full bg-black/35 px-1.5 py-0.5 text-[10px] font-bold tabular-nums text-white"
                  >{{ (chat.stopwords || []).length }}</span>
                </button>
                <button
                  type="button"
                  class="prot-info-btn"
                  aria-label="Информация по стоп-словам"
                  @click="showStopwordsInfoModal = true"
                >
                  i
                </button>
              </div>
            </div>
          <p class="mb-3 text-xs text-slate-300">
            Сообщения, содержащие эти слова (в тексте, не внутри ссылок), будут удаляться или наказываться по правилам выше.
          </p>
          <div class="mb-3 flex flex-wrap gap-2">
            <input
              v-model="newStopword"
              type="text"
              placeholder="Добавить слово"
              class="min-w-0 flex-1 rounded-lg border border-white/15 bg-white/10 px-2.5 py-1.5 text-xs text-slate-100 placeholder:text-slate-500"
              :disabled="stopwordLoading"
              @keydown.enter.prevent="addStopword()"
            />
            <button
              type="button"
              class="guard-green-soft rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
              :disabled="stopwordLoading || !(newStopword || '').trim()"
              @click="addStopword()"
            >
              Добавить
            </button>
          </div>
          <ul v-if="(chat.stopwords || []).length" class="space-y-1">
            <li
              v-for="w in (chat.stopwords || []).slice(0, 3)"
              :key="w"
              class="flex items-center justify-between rounded-lg bg-white/10 px-2.5 py-1.5 text-xs"
            >
              <span class="text-slate-200">{{ w }}</span>
              <button
                type="button"
                class="rounded p-1 text-red-600 hover:bg-red-100 dark:text-red-400 dark:hover:bg-red-900/30"
                :disabled="stopwordLoading"
                aria-label="Удалить"
                @click="removeStopword(w)"
              >
                ✕
              </button>
            </li>
          </ul>
          <p v-if="!(chat.stopwords || []).length" class="text-xs text-slate-400">
            Нет стоп-слов. Добавьте слово выше.
          </p>
          </div>

          <div :class="protCardDanger">
            <div class="mb-1 flex items-center justify-between gap-2">
              <h3 class="text-xs font-semibold text-rose-200">🚫 Guard: Жёсткий словарь</h3>
              <button
                type="button"
                class="prot-info-btn prot-info-btn--danger"
                aria-label="Информация по жёсткому словарю"
                @click="showHardDictInfoModal = true"
              >
                i
              </button>
            </div>
            <p class="mb-3 text-xs text-rose-100/90">
              Режет мат и искажённые формы по корням, а также подозрительные темы: подработки-скам, казино/ставки и политические обсуждения.
            </p>
            <div class="space-y-2">
          <div class="flex items-center justify-between gap-2">
                <span class="text-xs text-rose-100/90">Мат</span>
            <button
              type="button"
                  :class="hardDictSwitchClass(chat.rule.filter_profanity_enabled)"
                  class="relative h-[30px] w-[50px] shrink-0 rounded-full border transition duration-200"
              @click="updateRule({ filter_profanity_enabled: !chat.rule.filter_profanity_enabled })"
            >
              <span
                class="absolute left-[2px] top-1/2 h-[24px] w-[24px] rounded-full bg-white shadow-md transition duration-200"
                :style="{ transform: chat.rule.filter_profanity_enabled ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }"
              />
            </button>
              </div>
              <div class="flex items-center justify-between gap-2">
                <span class="text-xs text-rose-100/90">Мутные подработки</span>
                <button
                  type="button"
                  :class="hardDictSwitchClass(chat.rule.filter_jobs_enabled)"
                  class="relative h-[30px] w-[50px] shrink-0 rounded-full border transition duration-200"
                  @click="updateRule({ filter_jobs_enabled: !chat.rule.filter_jobs_enabled })"
                >
                  <span
                    class="absolute left-[2px] top-1/2 h-[24px] w-[24px] rounded-full bg-white shadow-md transition duration-200"
                    :style="{ transform: chat.rule.filter_jobs_enabled ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }"
                  />
                </button>
              </div>
              <div class="flex items-center justify-between gap-2">
                <span class="text-xs text-rose-100/90">Казино / ставки</span>
                <button
                  type="button"
                  :class="hardDictSwitchClass(chat.rule.filter_casino_enabled)"
                  class="relative h-[30px] w-[50px] shrink-0 rounded-full border transition duration-200"
                  @click="updateRule({ filter_casino_enabled: !chat.rule.filter_casino_enabled })"
                >
                  <span
                    class="absolute left-[2px] top-1/2 h-[24px] w-[24px] rounded-full bg-white shadow-md transition duration-200"
                    :style="{ transform: chat.rule.filter_casino_enabled ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }"
                  />
                </button>
              </div>
              <div class="flex items-center justify-between gap-2">
                <span class="text-xs text-rose-100/90">Реклама / акции / распродажи</span>
                <button
                  type="button"
                  :class="hardDictSwitchClass(chat.rule.filter_ads_enabled)"
                  class="relative h-[30px] w-[50px] shrink-0 rounded-full border transition duration-200"
                  @click="updateRule({ filter_ads_enabled: !chat.rule.filter_ads_enabled })"
                >
                  <span
                    class="absolute left-[2px] top-1/2 h-[24px] w-[24px] rounded-full bg-white shadow-md transition duration-200"
                    :style="{ transform: chat.rule.filter_ads_enabled ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }"
                  />
                </button>
              </div>
              <div class="flex items-center justify-between gap-2">
                <span class="text-xs text-rose-100/90">Обзывательства / оскорбления</span>
                <button
                  type="button"
                  :class="hardDictSwitchClass(chat.rule.filter_insults_enabled)"
                  class="relative h-[30px] w-[50px] shrink-0 rounded-full border transition duration-200"
                  @click="updateRule({ filter_insults_enabled: !chat.rule.filter_insults_enabled })"
                >
                  <span
                    class="absolute left-[2px] top-1/2 h-[24px] w-[24px] rounded-full bg-white shadow-md transition duration-200"
                    :style="{ transform: chat.rule.filter_insults_enabled ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }"
                  />
                </button>
              </div>
              <div class="flex items-center justify-between gap-2">
                <span class="text-xs text-rose-100/90">Антирасист (этнические оскорбления)</span>
                <button
                  type="button"
                  :class="hardDictSwitchClass(chat.rule.filter_racism_enabled)"
                  class="relative h-[30px] w-[50px] shrink-0 rounded-full border transition duration-200"
                  @click="updateRule({ filter_racism_enabled: !chat.rule.filter_racism_enabled })"
                >
                  <span
                    class="absolute left-[2px] top-1/2 h-[24px] w-[24px] rounded-full bg-white shadow-md transition duration-200"
                    :style="{ transform: chat.rule.filter_racism_enabled ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }"
                  />
                </button>
              </div>
              <div class="flex items-center justify-between gap-2">
                <span class="text-xs text-rose-100/90">Антифашист (нацизм / лозунги)</span>
                <button
                  type="button"
                  :class="hardDictSwitchClass(chat.rule.filter_nazi_enabled)"
                  class="relative h-[30px] w-[50px] shrink-0 rounded-full border transition duration-200"
                  @click="updateRule({ filter_nazi_enabled: !chat.rule.filter_nazi_enabled })"
                >
                  <span
                    class="absolute left-[2px] top-1/2 h-[24px] w-[24px] rounded-full bg-white shadow-md transition duration-200"
                    :style="{ transform: chat.rule.filter_nazi_enabled ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }"
                  />
                </button>
              </div>
              <div class="flex items-center justify-between gap-2">
                <span class="text-xs text-rose-100/90">Антипошлость (анатомия / половые)</span>
                <button
                  type="button"
                  :class="hardDictSwitchClass(chat.rule.filter_vulgar_enabled)"
                  class="relative h-[30px] w-[50px] shrink-0 rounded-full border transition duration-200"
                  @click="updateRule({ filter_vulgar_enabled: !chat.rule.filter_vulgar_enabled })"
                >
                  <span
                    class="absolute left-[2px] top-1/2 h-[24px] w-[24px] rounded-full bg-white shadow-md transition duration-200"
                    :style="{ transform: chat.rule.filter_vulgar_enabled ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }"
                  />
                </button>
              </div>
              <div class="flex items-center justify-between gap-2">
                <span class="text-xs text-rose-100/90">Анти-политика (политтемы / война / деятели)</span>
                <button
                  type="button"
                  :class="hardDictSwitchClass(chat.rule.filter_politics_enabled)"
                  class="relative h-[30px] w-[50px] shrink-0 rounded-full border transition duration-200"
                  @click="updateRule({ filter_politics_enabled: !chat.rule.filter_politics_enabled })"
                >
                  <span
                    class="absolute left-[2px] top-1/2 h-[24px] w-[24px] rounded-full bg-white shadow-md transition duration-200"
                    :style="{ transform: chat.rule.filter_politics_enabled ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }"
                  />
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section :class="protCard">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h2 class="text-xs font-medium text-slate-200">Приветствие новичков</h2>
          <button
            type="button"
            class="rounded-lg border border-white/15 bg-white/10 px-2.5 py-1 text-xs font-semibold text-slate-100 hover:bg-white/15"
            @click="openWelcomeSettings()"
          >
            Настроить
          </button>
        </div>
        <p class="text-[11px] text-slate-300/90">
          Отдельный текст для новых участников этого чата. Можно добавить кнопки и фото.
        </p>
        <p class="mt-1 text-[11px] text-slate-500">
          Статус:
          <span :class="chat.rule.welcome_enabled ? 'text-emerald-300' : 'text-slate-400'">
            {{ chat.rule.welcome_enabled ? 'включено' : 'выключено' }}
          </span>
          <span v-if="chat.rule.welcome_has_photo" class="text-sky-300"> · фото добавлено</span>
          <span class="text-zinc-500"> · каждый {{ Number(chat.rule.welcome_every_n_joins || 1) }}-й</span>
        </p>
      </section>

      <section :class="protCard">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h2 class="text-xs font-medium text-slate-200">📜 Правила в группе</h2>
          <button
            type="button"
            class="rounded-lg border border-white/15 bg-white/10 px-2.5 py-1 text-xs font-semibold text-slate-100 hover:bg-white/15"
            @click="openPostRulesSettings()"
          >
            Настроить
          </button>
        </div>
        <p class="text-[11px] text-slate-300/90">
          Статус:
          <span :class="chat.rule.rules_group_enabled ? 'text-emerald-300' : 'text-slate-400'">{{ chat.rule.rules_group_enabled ? 'включено' : 'выключено' }}</span>
        </p>
        <p class="mt-1 text-[11px] text-slate-500">
          Текст и кнопки для этого чата. Правила в комментариях к каналу — в «Подключённые чаты» → канал → «Настройки».
        </p>
      </section>

      <!-- Наказания -->
      <section :class="protCard">
        <h2 class="mb-3 text-xs font-medium text-slate-200">Наказания</h2>
        <div :class="protCardSub">
          <p class="text-xs font-semibold text-amber-200">⚔️ Режим Guard</p>
          <p class="mt-1 text-xs leading-relaxed text-amber-100/85">
            Все фильтры сверху (мат, подработки, казино, ссылки, кнопки и т.д.) получают <strong>одно общее наказание</strong> из этого блока.
            Выбираешь режим, Guard применяет его ко всем нарушениям.
          </p>
        </div>
        <div class="space-y-3">
          <div>
            <p class="mb-1 text-xs text-slate-400">Действие</p>
            <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <button
                v-for="opt in actionOptions"
                :key="opt.value"
                type="button"
                :class="actionButtonClass(chat.rule.action_mode, opt.value)"
                class="rounded-lg px-2 py-1.5 text-xs"
                @click="updateRule({ action_mode: opt.value })"
              >
                <span class="block font-semibold leading-none">{{ opt.label }}</span>
                <span class="mt-1 block text-[11px] leading-none opacity-80">{{ opt.hint }}</span>
              </button>
            </div>
          </div>
          <div v-if="chat.rule.action_mode === 'mute'">
            <p class="mb-1 text-xs text-slate-400">Длительность мута</p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="p in mutePresets"
                :key="p.value"
                type="button"
                :class="chat.rule.mute_minutes === p.value ? 'guard-green-soft' : protToggleOff"
                class="rounded-lg px-2.5 py-1 text-xs"
                @click="updateRule({ mute_minutes: p.value })"
              >
                {{ p.label }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <div class="h-2" aria-hidden="true" />

      <!-- Публичные сообщения от Guard -->
      <section :class="protCard">
        <div class="mb-2 flex items-center justify-between gap-2">
          <h2 class="text-sm font-semibold tracking-wide text-slate-50">Публичные сообщения от Guard</h2>
          <button
            type="button"
            class="prot-info-btn prot-info-btn--frost"
            aria-label="Справка: публичные сообщения"
            @click="showPublicAlertsHelpModal = true"
          >
            i
          </button>
        </div>
        <p
          v-if="premiumFeatureLocked"
          class="mb-1.5 text-[10px] font-medium text-amber-200/90"
        >
          Блок <span class="font-bold">Дежурные</span> и смена интервала в модалке — <span class="font-bold">Premium</span> · публичные алерты можно крутить и на Free
        </p>
        <p class="text-xs text-slate-300/90">
          Дежурные: <span class="font-semibold text-slate-100">{{ chat.rule.guardian_periodic_enabled ? 'включены' : 'выключены' }}</span>
          <span class="text-slate-400"> · {{ Number(chat.rule.guardian_periodic_interval_hours || guardianPeriodicFreeHours) }}ч</span>
        </p>
        <p class="mt-1 text-xs text-slate-300/90">
          Алерты: <span class="font-semibold text-slate-100">{{ chat.rule.public_alerts_enabled ? 'включены' : 'выключены' }}</span>
          <span v-if="chat.rule.public_alerts_enabled" class="text-slate-400"> · каждые {{ Number(chat.rule.public_alerts_every_n || 5) }} срабатываний</span>
        </p>
        <button
          type="button"
          class="mt-2 rounded-lg border border-white/15 bg-white/10 px-3 py-1.5 text-xs font-semibold text-slate-100 hover:bg-white/15"
          @click="showPublicAlertsSettingsModal = true"
        >
          Настроить
        </button>
        <p v-if="!chat.rule.guardian_messages_enabled" class="mt-2 text-[10px] text-amber-300/90">
          Служебные сообщения выключены — публичные алерты не отправляются.
        </p>
      </section>

      <section class="rounded-2xl border border-white/12 bg-gradient-to-br from-fuchsia-500/10 via-cyan-500/8 to-indigo-500/10 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_6px_24px_-12px_rgba(0,0,0,0.45)] ring-1 ring-inset ring-white/[0.06] backdrop-blur-xl">
        <div class="mb-2 flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold text-white/95">⭐ Репутация (карма)</h3>
          <div class="flex items-center gap-2">
            <button
              type="button"
              :class="boolToggleClass(chat.rule.reputation_enabled)"
              class="min-w-[5.25rem] rounded-lg px-2.5 py-1 text-xs font-medium"
              @click="updateRule({ reputation_enabled: !chat.rule.reputation_enabled })"
            >
              {{ chat.rule.reputation_enabled ? 'ВКЛ' : 'ВЫКЛ' }}
            </button>
            <button
              type="button"
              class="prot-info-btn"
              aria-label="Как работает карма"
              @click="showReputationInfoModal = true"
            >i</button>
          </div>
        </div>
        <p class="text-[11px] text-slate-200/85">
          Моя карма: <span class="font-semibold text-lime-300">{{ reputationMyScore }}</span>.
        </p>
        <button
          type="button"
          class="mt-2 w-full rounded-lg border border-cyan-400/35 bg-cyan-500/15 px-3 py-1.5 text-xs font-semibold text-cyan-100 transition hover:bg-cyan-500/25"
          @click="showReputationSettingsModal = true"
        >
          Настроить
        </button>
      </section>

      <div :class="protCardSub">
        <div class="flex items-start justify-between gap-2">
          <div>
            <p class="text-xs font-semibold uppercase tracking-wide text-slate-200">⚠ Всплеск удалений</p>
            <p class="mt-1 text-[11px] text-slate-300/90">
              Сейчас сработает, если Guard/админы удалят
              <strong>{{ Number(chat.rule.spam_spike_min_deletes || spamSpikeDefaultDeleteCount) }}</strong>
              сообщений за
              <strong>{{ Number(chat.rule.spam_spike_window_minutes || 35) }} мин</strong>.
            </p>
          </div>
          <button
            type="button"
            class="prot-info-btn"
            aria-label="Как работает всплеск удалений"
            @click="showSpamSpikeInfoModal = true"
          >
            i
          </button>
        </div>
        <div class="mt-2 flex flex-wrap items-center gap-2">
          <button
            type="button"
            :class="boolToggleClass(!!chat.rule.spam_spike_enabled)"
            class="rounded-xl px-3 py-1.5 text-xs font-semibold"
            @click="updateRule({ spam_spike_enabled: !chat.rule.spam_spike_enabled })"
          >
            {{ chat.rule.spam_spike_enabled ? 'ВКЛ' : 'ВЫКЛ' }}
          </button>
          <button
            type="button"
            class="rounded-xl border border-white/15 bg-white/10 px-3 py-1.5 text-xs font-semibold text-slate-100 hover:bg-white/15"
            @click="showSpamSpikeSettingsModal = true"
          >
            Настроить
          </button>
        </div>
      </div>

      <!-- Режим тишины (Premium) -->
      <section :class="[protCardSky, premiumSectionFrameClass]">
        <div class="mb-2 flex items-center justify-between gap-2">
          <p class="text-xs font-semibold text-sky-100">🤫 Режим тишины <span v-if="premiumFeatureLocked" class="text-amber-300">🔒 Premium</span></p>
          <button
            type="button"
            class="prot-info-btn"
            aria-label="Информация по режиму тишины"
            @click="showSilenceInfoModal = true"
          >
            i
          </button>
        </div>
        <p class="mb-2 text-xs leading-relaxed text-sky-100/85">
          После входа в чат выбранное время: любое сообщение участника может привести к муту на оставшиеся минуты окна.
        </p>
        <div :class="['flex flex-wrap items-center gap-2', premiumControlRowClass]">
          <span
            :class="(chat.rule.silence_minutes || 0) > 0 ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/25 dark:text-emerald-300' : 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'"
            class="inline-flex rounded-lg px-2.5 py-1.5 text-xs font-semibold"
          >
            {{ (chat.rule.silence_minutes || 0) > 0 ? `Включено: ${silenceStatusLabel}` : 'Выключено' }}
          </span>
          <button
            type="button"
            :class="[
              'rounded-lg border border-sky-300 bg-white px-3 py-1.5 text-xs font-semibold text-sky-700 hover:bg-sky-50 dark:border-sky-700 dark:bg-sky-900/20 dark:text-sky-300 dark:hover:bg-sky-900/35',
              premiumFeatureLocked && 'border-amber-400/40',
            ]"
            @click="onSilenceConfigureClick"
          >
            Настроить время
          </button>
        </div>
      </section>

      <!-- Антинакрутка (Premium) -->
      <section :class="[protCard, premiumSectionFrameClass]">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h2 class="text-xs font-medium text-slate-200">📈 Антинакрутка <span v-if="premiumFeatureLocked" class="text-amber-300">🔒 Premium</span></h2>
          <button
            type="button"
            class="prot-info-btn"
            aria-label="Информация по антинакрутке"
            @click="showAntinakrutkaInfoModal = true"
          >
            i
          </button>
        </div>
        <div :class="premiumControlRowClass">
          <p class="text-xs text-slate-300/90">
            Состояние: <span class="font-semibold text-slate-100">{{ chat.rule.antinakrutka_enabled ? 'включено' : 'выключено' }}</span>
            <span v-if="chat.rule.antinakrutka_enabled" class="text-slate-400"> · порог {{ Number(chat.rule.antinakrutka_joins_threshold || 10) }}, окно {{ Number(chat.rule.antinakrutka_window_minutes || 5) }} мин</span>
          </p>
        </div>
        <button
          type="button"
          :class="[
            'mt-2 rounded-lg border border-white/15 bg-white/10 px-3 py-1.5 text-xs font-semibold text-slate-100 hover:bg-white/15',
            premiumFeatureLocked && 'border-amber-400/30',
          ]"
          @click="onAntinakrutkaOpenSettingsClick"
        >
          Настроить
        </button>
      </section>

      <!-- Капча при входе (Premium) -->
      <section :class="[protCardIndigo, premiumSectionFrameClass]">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h2 class="text-xs font-medium text-slate-100">🧩 Капча при входе <span v-if="premiumFeatureLocked" class="text-amber-300">🔒 Premium</span></h2>
          <button
            type="button"
            class="prot-info-btn"
            aria-label="Справка: капча при входе"
            @click="showJoinCaptchaInfoModal = true"
          >
            i
          </button>
        </div>
        <div :class="['space-y-3', premiumControlRowClass]">
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs text-slate-300">Включить проверку новых участников</span>
            <button
              type="button"
              :class="boolToggleClass(!!chat.rule.join_captcha_enabled)"
              class="rounded-lg px-2.5 py-1 text-xs"
              @click="onJoinCaptchaToggleClick"
            >
              {{ chat.rule.join_captcha_enabled ? 'ВКЛ' : 'ВЫКЛ' }}
            </button>
          </div>
          <button
            type="button"
            :class="[
              'rounded-lg border border-white/15 bg-white/10 px-3 py-1.5 text-xs font-semibold text-slate-100 hover:bg-white/15',
              premiumFeatureLocked && 'border-amber-400/30',
            ]"
            @click="onJoinCaptchaOpenSettingsClick"
          >
            Настроить
          </button>
        </div>
      </section>

      <!-- Новички (Premium) -->
      <section :class="[protCardIndigo, premiumSectionFrameClass]">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h2 class="text-xs font-medium text-slate-100">🆕 Новички <span v-if="premiumFeatureLocked" class="text-amber-300">🔒 Premium</span></h2>
          <button
            type="button"
            class="prot-info-btn"
            aria-label="Информация по режиму новичков"
            @click="showNewbieInfoModal = true"
          >
            i
          </button>
        </div>
        <div :class="['space-y-3', premiumControlRowClass]">
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs text-slate-300">Режим новичков</span>
            <button
              type="button"
              :class="boolToggleClass(chat.rule.newbie_enabled)"
              class="rounded-lg px-2.5 py-1 text-xs"
              @click="onNewbieToggleClick"
            >
              {{ chat.rule.newbie_enabled ? 'ВКЛ' : 'ВЫКЛ' }}
            </button>
          </div>
          <div v-if="chat.rule.newbie_enabled && canUsePremiumForCurrentChat">
            <p class="mb-1 text-xs text-slate-400">Окно (мин)</p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="m in newbiePresets"
                :key="m"
                type="button"
                :class="chat.rule.newbie_minutes === m ? 'guard-green-soft' : protToggleOff"
                class="rounded-lg px-2.5 py-1 text-xs"
                @click="updateRule({ newbie_minutes: m })"
              >
                {{ m }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- Антиспам база (Premium) -->
      <section :class="[protCard, premiumSectionFrameClass]">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h2 class="text-xs font-medium text-slate-200">📋 Антиспам база <span v-if="premiumFeatureLocked" class="text-amber-300">🔒 Premium</span></h2>
        </div>
        <div :class="['space-y-3', premiumControlRowClass]">
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs text-slate-300">Проверять при входе в этот чат</span>
            <button
              type="button"
              :class="boolToggleClass(chat.rule.use_global_antispam_db)"
              class="rounded-lg px-2.5 py-1 text-xs"
              @click="onAntispamDbToggleClick"
            >
              {{ chat.rule.use_global_antispam_db ? 'ВКЛ' : 'ВЫКЛ' }}
            </button>
          </div>
          <div class="flex items-center justify-between gap-2">
            <p class="text-xs text-slate-400">Записей в базе: {{ (antispamItems || []).length }}</p>
            <button
              type="button"
              :class="[
                'rounded-lg border border-white/15 bg-white/10 px-3 py-1.5 text-xs font-semibold text-slate-100 hover:bg-white/15',
                premiumFeatureLocked && 'border-amber-400/30',
              ]"
              :disabled="antispamLoading"
              @click="onAntispamListButtonClick"
            >
              Настроить
            </button>
          </div>
        </div>
      </section>

      <!-- Очистка от удалённых аккаунтов -->
      <section :class="protCard">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h2 class="text-xs font-medium text-slate-200">🧹 Очистка от удалённых аккаунтов</h2>
          <button
            type="button"
            class="prot-info-btn"
            aria-label="Информация по очистке удалённых"
            @click="showCleanupInfoModal = true"
          >
            i
          </button>
        </div>
        <button
          v-if="chat?.id"
          type="button"
          class="guard-green-soft inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold transition"
          @click="openCleanDeleted"
        >
          <span v-if="cleanLaunchLoading" class="inline-flex items-center gap-2">
            <span class="inline-block hourglass-flip">⏳</span>
            Запуск…
          </span>
          <span v-else>Запустить очистку</span>
        </button>
        <p v-else class="text-xs text-slate-400">
          Выберите чат выше, чтобы запустить очистку.
        </p>
      </section>

      <!-- Перенести настройки (доступно при нескольких чатах / Premium) -->
      <section :class="[protCard, copySectionPremiumClass]">
        <h2 class="mb-3 text-xs font-medium text-slate-200">📤 Перенести настройки <span v-if="premiumFeatureLocked && (chatsList || []).length > 1" class="text-amber-300">🔒 Premium</span></h2>
        <p class="mb-3 text-xs text-slate-400">
          Скопировать все настройки защиты из текущего чата в выбранный или сразу во все чаты.
        </p>
        <div class="flex flex-wrap items-center gap-2">
          <select
            v-model="copyTargetId"
            class="rounded-lg border border-white/15 bg-white/10 px-2.5 py-1.5 text-xs text-slate-100"
          >
            <option :value="null">Выберите чат</option>
            <option value="__all__">Во все чаты</option>
            <option
              v-for="c in (chatsList || []).filter((x) => x.id !== chat?.id)"
              :key="c.id"
              :value="String(c.id)"
            >
              {{ c.title || c.id }}
            </option>
          </select>
          <button
            type="button"
            class="guard-green-soft rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
            :disabled="copyLoading || !copyTargetId || (copyTargetId !== '__all__' && String(copyTargetId) === String(chat?.id))"
            @click="onCopySettingsBarClick"
          >
            Перенести
          </button>
        </div>
      </section>

      <p v-if="saving" class="text-xs text-slate-400">Сохранение…</p>
    </div>

    <div v-else-if="hasInitData" class="space-y-3 py-2" aria-busy="true">
      <div class="mx-auto inline-flex items-center gap-2 rounded-full border border-cyan-300/30 bg-cyan-500/12 px-3 py-1.5 text-xs font-semibold text-cyan-100 shadow-[0_0_20px_-10px_rgba(34,211,238,0.9)]">
        <span class="inline-block hourglass-flip">⏳</span>
        Загружаю настройки чата…
      </div>
      <div class="space-y-2.5 rounded-2xl border border-white/10 bg-black/30 p-3 backdrop-blur-md">
        <div class="h-3 w-2/3 max-w-[14rem] animate-pulse rounded bg-white/15" />
        <div class="h-24 animate-pulse rounded-xl bg-white/10" />
        <div class="h-20 animate-pulse rounded-xl bg-white/10" />
        <div class="h-28 animate-pulse rounded-xl bg-white/10" />
      </div>
    </div>

      </div>
    </div>

    <div
      v-if="showPublicAlertsSettingsModal && chat?.rule"
      class="fixed inset-0 z-[262] flex items-end justify-center bg-black/65 p-3 md:items-center"
      @click.self="showPublicAlertsSettingsModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-cyan-400/20 bg-gradient-to-b from-slate-900/95 via-slate-950/95 to-black/95 p-4 text-slate-100 shadow-[0_24px_80px_-22px_rgba(0,0,0,0.9),inset_0_1px_0_rgba(255,255,255,0.1)] backdrop-blur-2xl ring-1 ring-cyan-300/20">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-cyan-100">Публичные сообщения — настройки</h3>
          <div class="flex items-center gap-1.5">
            <button
              type="button"
              class="prot-info-btn"
              aria-label="Пояснения по настройкам публичных сообщений"
              @click="showPublicAlertsHelpModal = true"
            >
              i
            </button>
            <button
              type="button"
              class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10"
              @click="showPublicAlertsSettingsModal = false"
            >
              ✕
            </button>
          </div>
        </div>
        <div class="space-y-3">
          <div class="rounded-xl border border-cyan-300/20 bg-cyan-500/[0.08] p-2.5 backdrop-blur-md">
            <div class="mb-2 flex items-center justify-between gap-2">
              <p class="text-[11px] font-semibold uppercase tracking-wide text-cyan-100">Дежурные сообщения</p>
              <button
                type="button"
                :class="boolToggleClass(!!chat.rule.guardian_periodic_enabled)"
                class="rounded-xl px-3 py-1.5 text-xs font-semibold"
                @click="toggleGuardianPeriodic(!chat.rule.guardian_periodic_enabled)"
              >
                {{ chat.rule.guardian_periodic_enabled ? 'ВКЛ' : 'ВЫКЛ' }}
              </button>
            </div>
            <p class="mb-1 text-[11px] text-slate-400">Частота дежурных сообщений Guard</p>
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="opt in guardianPeriodicIntervalPresets"
                :key="`gp-int-modal-${opt.h}`"
                type="button"
                class="rounded-lg px-2 py-1 text-[11px] font-semibold"
                :class="Number(chat.rule.guardian_periodic_interval_hours || guardianPeriodicFreeHours) === opt.h ? 'guard-green-soft text-slate-900' : protToggleOff"
                @click="onGuardianIntervalPick(opt.h)"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>

          <div class="rounded-xl border border-cyan-300/20 bg-cyan-500/[0.08] p-2.5 backdrop-blur-md">
            <div class="mb-2 flex items-center justify-between gap-2">
              <p class="text-[11px] font-semibold uppercase tracking-wide text-cyan-100">Публичные алерты</p>
              <button
                type="button"
                :class="boolToggleClass(!!chat.rule.public_alerts_enabled)"
                class="rounded-xl px-3 py-1.5 text-xs font-semibold"
                @click="togglePublicAlerts(!chat.rule.public_alerts_enabled)"
              >
                {{ chat.rule.public_alerts_enabled ? 'ВКЛ' : 'ВЫКЛ' }}
              </button>
            </div>
            <div class="space-y-2" :class="chat.rule.public_alerts_enabled ? '' : 'opacity-55'">
              <div>
                <p class="mb-1 text-[11px] text-slate-400">После скольких срабатываний подряд отправить строку</p>
                <div class="flex flex-wrap gap-1.5">
                  <button
                    v-for="p in publicAlertsEveryPresets"
                    :key="`pa-n-${p.n}`"
                    type="button"
                    class="rounded-lg px-2 py-1 text-[11px] font-semibold"
                    :class="Number(chat.rule.public_alerts_every_n) === p.n ? 'guard-green-soft text-slate-900' : 'bg-white/10 text-slate-200 hover:bg-white/15'"
                    :disabled="!chat.rule.public_alerts_enabled"
                    @click="updateRule({ public_alerts_every_n: p.n })"
                  >
                    {{ p.label }}
                  </button>
                </div>
              </div>
              <div>
                <p class="mb-1 text-[11px] text-slate-400">Не чаще одного сообщения, чем раз в…</p>
                <div class="flex flex-wrap gap-1.5">
                  <button
                    v-for="p in publicAlertsIntervalPresets"
                    :key="`pa-i-${p.sec}`"
                    type="button"
                    class="rounded-lg px-2 py-1 text-[11px] font-semibold"
                    :class="Number(chat.rule.public_alerts_min_interval_sec) === p.sec ? 'guard-green-soft text-slate-900' : 'bg-white/10 text-slate-200 hover:bg-white/15'"
                    :disabled="!chat.rule.public_alerts_enabled"
                    @click="updateRule({ public_alerts_min_interval_sec: p.sec })"
                  >
                    {{ p.label }}
                  </button>
                </div>
              </div>
              <div>
                <div class="mb-1 flex items-center justify-between gap-2">
                  <p class="text-[11px] text-slate-400">Стиль текста</p>
                  <button
                    type="button"
                    class="link-glass-info-btn"
                    aria-label="Примеры стилей публичных сообщений"
                    @click="showPublicAlertsStyleHelpModal = true"
                  >
                    ⓘ
                  </button>
                </div>
                <div class="grid grid-cols-1 gap-1.5 sm:grid-cols-3">
                  <button
                    v-for="st in publicAlertsStyleOptions"
                    :key="`pa-st-${st.value}`"
                    type="button"
                    class="rounded-xl border px-2 py-2 text-left text-[11px] transition"
                    :class="
                      (chat.rule.public_alerts_style || 'guard') === st.value
                        ? 'border-lime-400/50 bg-lime-500/15 text-lime-50'
                        : 'border-white/10 bg-white/5 text-slate-200 hover:bg-white/10'
                    "
                    :disabled="!chat.rule.public_alerts_enabled"
                    @click="updateRule({ public_alerts_style: st.value })"
                  >
                    <span class="block font-semibold">{{ st.label }}</span>
                    <span class="mt-0.5 block text-[10px] text-slate-400">{{ st.hint }}</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div
      v-if="showSpamSpikeInfoModal"
      class="fixed inset-0 z-[265] flex items-end justify-center bg-black/60 p-3 md:items-center"
      @click.self="showSpamSpikeInfoModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-orange-300/35 bg-white p-4 shadow-2xl dark:border-orange-500/35 dark:bg-slate-900">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white">😈 Всплеск удалений — как это работает</h3>
          <button
            type="button"
            class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10"
            @click="showSpamSpikeInfoModal = false"
          >
            ✕
          </button>
        </div>
        <div class="space-y-2 text-xs leading-relaxed text-gray-700 dark:text-slate-300">
          <p>Когда в чате резко летит мусор, я считаю удаления за выбранное окно времени. Добрался до порога — поднимаю флаг «под угрозой» и пингую ответственных.</p>
          <p>В счёт идут только модерационные удаления Guard/админов. Самоудаление пользователем в счётчик не попадает.</p>
          <p>Что крутят настройки в модалке:</p>
          <p>• <strong>Порог удалений</strong> — сколько удалений нужно для срабатывания.</p>
          <p>• <strong>Окно времени</strong> — за какой промежуток считаем эти удаления.</p>
          <p>• <strong>Уведомлять делегата</strong> — слать ли DM менеджерам чата при всплеске.</p>
          <p>• <strong>Главный триггер «всплеск удалений»</strong> — не пустышка: это мастер‑переключатель самого детектора. Если выключен, всплеск вообще не проверяется.</p>
        </div>
      </div>
    </div>
    <div
      v-if="showSpamSpikeSettingsModal && chat?.rule"
      class="fixed inset-0 z-[260] flex items-end justify-center bg-black/65 p-3 md:items-center"
      @click.self="showSpamSpikeSettingsModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-white/12 bg-zinc-950/78 p-4 text-slate-100 shadow-[0_26px_90px_-24px_rgba(0,0,0,0.95),inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-2xl">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-100">⚠ Настройка всплеска удалений</h3>
          <div class="flex items-center gap-1.5">
            <button
              type="button"
              class="prot-info-btn"
              aria-label="Пояснения по всплеску удалений"
              @click="showSpamSpikeInfoModal = true"
            >
              i
            </button>
            <button
              type="button"
              class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10"
              @click="showSpamSpikeSettingsModal = false"
            >
              ✕
            </button>
          </div>
        </div>

        <div class="space-y-3">
          <p class="rounded-xl border border-white/10 bg-white/[0.04] p-2.5 text-[11px] leading-relaxed text-slate-200">
            Guard считает только модерационные удаления по фильтрам (действия Guard/админов через инструменты модерации).
            Самоудаление сообщения пользователем в этот счётчик не попадает.
          </p>

          <div class="rounded-xl border border-white/10 bg-white/[0.04] p-2.5 backdrop-blur-md">
            <p class="text-[11px] font-semibold uppercase tracking-wide text-slate-200">Порог удалений</p>
            <div class="mt-2 flex flex-wrap gap-2">
              <button
                v-for="p in spamSpikeDeletePresets"
                :key="`spike-del-${p.n}`"
                type="button"
                :class="Number(chat.rule.spam_spike_min_deletes) === p.n ? 'guard-green-soft text-slate-900' : 'bg-white/[0.08] text-slate-200 hover:bg-white/[0.12]'"
                class="rounded-xl px-3 py-1.5 text-xs font-semibold"
                @click="updateRule({ spam_spike_min_deletes: p.n })"
              >
                {{ p.label }}
              </button>
            </div>
          </div>

          <div class="rounded-xl border border-white/10 bg-white/[0.04] p-2.5 backdrop-blur-md">
            <p class="text-[11px] font-semibold uppercase tracking-wide text-slate-200">Окно времени</p>
            <div class="mt-2 flex flex-wrap gap-2">
              <button
                v-for="p in spamSpikeWindowPresets"
                :key="`spike-win-${p.m}`"
                type="button"
                :class="Number(chat.rule.spam_spike_window_minutes) === p.m ? 'guard-green-soft text-slate-900' : 'bg-white/[0.08] text-slate-200 hover:bg-white/[0.12]'"
                class="rounded-xl px-3 py-1.5 text-xs font-semibold"
                @click="updateRule({ spam_spike_window_minutes: p.m })"
              >
                {{ p.label }}
              </button>
            </div>
          </div>

          <div class="flex items-center justify-between gap-2 rounded-xl border border-white/10 bg-white/[0.04] p-2.5 backdrop-blur-md">
            <div>
              <p class="text-xs font-semibold text-slate-100">Уведомлять делегата</p>
              <p class="text-[11px] text-slate-400">Если включено — DM о всплеске получат и менеджеры чата.</p>
            </div>
            <button
              type="button"
              :class="boolToggleClass(!!chat.rule.spam_spike_notify_managers)"
              class="rounded-xl px-3 py-1.5 text-xs font-semibold"
              @click="updateRule({ spam_spike_notify_managers: !chat.rule.spam_spike_notify_managers })"
            >
              {{ chat.rule.spam_spike_notify_managers ? 'ВКЛ' : 'ВЫКЛ' }}
            </button>
          </div>

          <div class="flex items-center justify-between gap-2 rounded-xl border border-white/10 bg-white/[0.04] p-2.5 backdrop-blur-md">
            <p class="text-xs text-slate-300">Главный триггер «всплеск удалений»</p>
            <button
              type="button"
              :class="boolToggleClass(!!chat.rule.spam_spike_enabled)"
              class="rounded-xl px-3 py-1.5 text-xs font-semibold"
              @click="updateRule({ spam_spike_enabled: !chat.rule.spam_spike_enabled })"
            >
              {{ chat.rule.spam_spike_enabled ? 'ВКЛ' : 'ВЫКЛ' }}
            </button>
          </div>
        </div>
      </div>
    </div>
    <div
      v-if="showCleanupInfoModal"
      class="fixed inset-0 z-[266] flex items-center justify-center bg-black/65 p-3"
      @click.self="showCleanupInfoModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-sky-300/50 bg-white p-4 shadow-2xl dark:border-sky-700/60 dark:bg-gray-800">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold text-gray-900 dark:text-white">😈 Очистка «призраков»</h3>
          <button type="button" class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10" @click="showCleanupInfoModal = false">✕</button>
        </div>
        <div class="space-y-2 text-xs text-gray-700 dark:text-gray-300">
          <p>Пробегаюсь по выбранному чату и выкидываю аккаунты, которые Telegram уже пометил как удалённые — они только засоряют списки.</p>
          <p>После рейда, массового входа или перед важным анонсом — самое время нажать и не тащить мёртвые души в статистику.</p>
          <p>Откроется личка со мной и стартанёт очистка именно для текущего чата — никуда руками копировать не надо.</p>
        </div>
      </div>
    </div>
    <div
      v-if="showFiltersInfoModal"
      class="fixed inset-0 z-[266] flex items-center justify-center bg-black/65 p-3"
      @click.self="showFiltersInfoModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-sky-300/50 bg-white p-4 shadow-2xl dark:border-sky-700/60 dark:bg-gray-800">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold text-gray-900 dark:text-white">😈 Фильтры — простыми словами</h3>
          <button type="button" class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10" @click="showFiltersInfoModal = false">✕</button>
        </div>
        <div class="space-y-2 text-xs text-gray-700 dark:text-gray-300">
          <p><strong>Разрешено</strong> — пропускаю мимо ушей, как будто ничего не было.</p>
          <p><strong>Запрещено</strong> — срабатываю по сценарию из блока «Наказания»: удалить, замьютить, забанить — что выберешь.</p>
          <p>На админов чата эти правила не вешаю — вы сами за порядок отвечаете.</p>
          <p><strong>Сообщения с кнопками</strong> — посты с inline-кнопками («жми сюда», «забери», «вступи»); чаще всего это реклама или скам, поэтому отдельный тумблер.</p>
        </div>
      </div>
    </div>
    <div
      v-if="showSilenceInfoModal"
      class="fixed inset-0 z-[266] flex items-center justify-center bg-black/65 p-3"
      @click.self="showSilenceInfoModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-sky-300/50 bg-white p-4 shadow-2xl dark:border-sky-700/60 dark:bg-gray-800">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold text-gray-900 dark:text-white">😈 Режим тишины</h3>
          <button type="button" class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10" @click="showSilenceInfoModal = false">✕</button>
        </div>
        <div class="space-y-2 text-xs text-gray-700 dark:text-gray-300">
          <p>Человек только зашёл — даю ему короткое «молчи в тряпочку». Если всё же пишет в окне, могу приглушить на остаток тишины.</p>
          <p>После рекламы, при волне новичков или когда чувствуешь, что вот-вот начнётся цирк — включай без стеснения.</p>
          <p class="text-xs text-slate-400">Админов не трогаю: вы и так знаете, что делаете.</p>
        </div>
      </div>
    </div>
    <div
      v-if="showPublicAlertsHelpModal"
      class="fixed inset-0 z-[266] flex items-center justify-center bg-black/65 p-3"
      @click.self="showPublicAlertsHelpModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-lime-400/35 bg-white p-4 shadow-2xl dark:border-lime-500/30 dark:bg-slate-900">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white">😈 Публичные реплики от меня</h3>
          <button type="button" class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10" @click="showPublicAlertsHelpModal = false">✕</button>
        </div>
        <div class="space-y-2 text-xs leading-relaxed text-gray-700 dark:text-slate-300">
          <p>
            Когда я <strong>реально</strong> снял спам, замьютил или забанил кого-то, коплю счётчик по чату. Добрался до порога и прошёл минимальный интервал с прошлой реплики — кидаю в чат одну короткую фразу без кнопок: мол, я на посту.
          </p>
          <p>
            Это не рекламная простыня, а редкий пинг «модерация жива». Частоту режу и по числу срабатываний, и по паузе между сообщениями — чтобы не бесить людей.
          </p>
          <p class="text-[11px] text-gray-500 dark:text-slate-400">
            Ниже показаны реплики именно для выбранного стиля (сейчас: {{ currentPublicAlertsStyleLabel }}).
          </p>
          <div class="rounded-xl border border-lime-400/25 bg-lime-500/10 p-2.5 text-[11px] text-slate-700 dark:text-slate-200">
            <p class="mb-1 font-semibold text-slate-800 dark:text-slate-100">
              Сейчас выбран стиль: {{ currentPublicAlertsStyleLabel }} — примеры для него:
            </p>
            <p>• Спам: «{{ currentPublicAlertsExamples.spam?.[0] }}»</p>
            <p>• Ссылки: «{{ currentPublicAlertsExamples.link?.[0] }}»</p>
            <p>• Мат/грубость: «{{ currentPublicAlertsExamples.bad_words?.[0] }}»</p>
            <p>• Мут: «{{ currentPublicAlertsExamples.mute?.[0] }}»</p>
            <p>• Бан: «{{ currentPublicAlertsExamples.ban?.[0] }}»</p>
          </div>
          <p class="text-[11px] text-gray-500 dark:text-slate-400">
            Фраза выбирается хаотично из набора под конкретный фильтр (спам/ссылка/мат и т.д.) и текущий стиль.
          </p>
        </div>
      </div>
    </div>
    <div
      v-if="showPublicAlertsStyleHelpModal"
      class="fixed inset-0 z-[266] flex items-center justify-center bg-black/65 p-3"
      @click.self="showPublicAlertsStyleHelpModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-sky-400/30 bg-white p-4 shadow-2xl dark:border-sky-500/30 dark:bg-slate-900">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white">📝 Примеры стилей публичных реплик</h3>
          <button
            type="button"
            class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10"
            @click="showPublicAlertsStyleHelpModal = false"
          >✕</button>
        </div>
        <div class="space-y-3 text-xs leading-relaxed text-gray-700 dark:text-slate-300">
          <div class="rounded-xl border border-lime-400/25 bg-lime-500/10 p-2.5">
            <p class="mb-1 font-semibold text-lime-900 dark:text-lime-200">
              Активный стиль сейчас: {{ currentPublicAlertsStyleLabel }}
            </p>
            <p>• Спам: «{{ currentPublicAlertsExamples.spam?.[1] || currentPublicAlertsExamples.spam?.[0] }}»</p>
            <p>• Ссылка: «{{ currentPublicAlertsExamples.link?.[1] || currentPublicAlertsExamples.link?.[0] }}»</p>
            <p>• Мат: «{{ currentPublicAlertsExamples.bad_words?.[1] || currentPublicAlertsExamples.bad_words?.[0] }}»</p>
            <p>• Мут/бан: «{{ currentPublicAlertsExamples.mute?.[0] }}» / «{{ currentPublicAlertsExamples.ban?.[0] }}»</p>
          </div>
          <p class="text-[11px] text-gray-500 dark:text-slate-400">
            После смены стиля этот список меняется автоматически.
          </p>
        </div>
      </div>
    </div>
    <div
      v-if="showGuardianPeriodicHelpModal"
      class="fixed inset-0 z-[266] flex items-center justify-center bg-black/65 p-3"
      @click.self="showGuardianPeriodicHelpModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-emerald-400/30 bg-white p-4 shadow-2xl dark:border-emerald-500/30 dark:bg-slate-900">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white">🛡 Дежурные сообщения в группе</h3>
          <button
            type="button"
            class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10"
            @click="showGuardianPeriodicHelpModal = false"
          >✕</button>
        </div>
        <div class="space-y-2 text-xs leading-relaxed text-gray-700 dark:text-slate-300">
          <p>
            Это отдельные «дежурные» сообщения о присутствии Guard в чате. Они отправляются не по факту конкретного нарушения, а периодически.
          </p>
          <p class="text-[11px] text-gray-500 dark:text-slate-400">
            На Free: всегда включены, интервал фиксирован 24 часа. На Premium можно отключить и выбрать частоту.
          </p>
          <div class="rounded-xl border border-emerald-400/25 bg-emerald-500/10 p-2.5 text-[11px]">
            <p class="mb-1 font-semibold text-emerald-900 dark:text-emerald-200">Примеры текущих дежурных сообщений:</p>
            <p v-for="(txt, idx) in guardianPeriodicExamples" :key="`gp-ex-${idx}`">• «{{ txt }}»</p>
          </div>
        </div>
      </div>
    </div>
    <div
      v-if="showSilencePickerModal"
      class="fixed inset-0 z-[266] flex items-center justify-center bg-black/65 p-3"
      @click.self="showSilencePickerModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-sky-300/50 bg-white p-4 shadow-2xl dark:border-sky-700/60 dark:bg-gray-800">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold text-gray-900 dark:text-white">🤫 Время режима тишины</h3>
          <button type="button" class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10" @click="showSilencePickerModal = false">✕</button>
        </div>
        <div class="grid grid-cols-2 gap-2">
            <button
            v-for="p in silencePresets"
            :key="`modal-silence-${p.value}`"
              type="button"
            :class="(chat.rule.silence_minutes || 0) === p.value ? 'guard-green-soft' : protToggleOff"
            class="rounded-lg px-2.5 py-2 text-center text-xs font-medium"
            @click="onSilencePresetPick(p.value)"
          >
            {{ p.label }}
          </button>
          <button
            type="button"
            :class="(chat.rule.silence_minutes || 0) === 0 ? 'guard-green-soft' : protToggleOff"
            class="col-span-2 rounded-lg px-2.5 py-2 text-center text-xs font-medium"
            @click="onSilencePresetPick(0)"
          >
            ❌ Отключить
            </button>
          </div>
      </div>
    </div>
    <div
      v-if="showStopwordsInfoModal"
      class="fixed inset-0 z-[266] flex items-center justify-center bg-black/65 p-3"
      @click.self="showStopwordsInfoModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-sky-300/50 bg-white p-4 shadow-2xl dark:border-sky-700/60 dark:bg-gray-800">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold text-gray-900 dark:text-white">😈 Стоп-слова</h3>
          <button type="button" class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10" @click="showStopwordsInfoModal = false">✕</button>
        </div>
        <div class="space-y-2 text-xs text-gray-700 dark:text-gray-300">
          <p>Твой личный список слов и фраз: увидел — среагировал так, как настроишь в наказаниях.</p>
          <p>Удобно для местных мемов-спама, рекламных маркеров и заезженных триггеров именно в этом чате.</p>
          <p class="text-xs text-slate-400">Смотрю на текст сообщения; что спрятано за ссылкой, сам не читаю — у Telegram свои правила.</p>
        </div>
      </div>
    </div>
    <div
      v-if="showHardDictInfoModal"
      class="fixed inset-0 z-[266] flex items-center justify-center bg-black/65 p-3"
      @click.self="showHardDictInfoModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-red-300/60 bg-white p-4 shadow-2xl dark:border-red-700/60 dark:bg-gray-800">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold text-gray-900 dark:text-white">😈 Жёсткий словарь</h3>
          <button type="button" class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10" @click="showHardDictInfoModal = false">✕</button>
        </div>
        <div class="space-y-2 text-xs text-gray-700 dark:text-gray-300">
          <p>Готовый набор самых частых токсичных и мошеннических заготовок — включил и не собираешь простыню вручную.</p>
          <p>Хорош для быстрого старта, пока ты допиливаешь свои правила.</p>
          <p class="text-xs text-slate-400">Нужны точечные исключения — пиши их в «Стоп-слова» выше, там гибче.</p>
        </div>
      </div>
    </div>
    <div
      v-if="showReputationInfoModal"
      class="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-3 backdrop-blur-[3px] md:items-center"
      @click.self="showReputationInfoModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-white/12 bg-gradient-to-b from-zinc-900/80 to-zinc-950/95 p-4 text-slate-100 shadow-[0_28px_90px_-28px_rgba(0,0,0,0.9)] ring-1 ring-inset ring-white/[0.06] backdrop-blur-2xl">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-sm font-semibold text-white">⭐ Карма в группе</h3>
          <button type="button" class="rounded-lg px-2 py-1 text-sm text-slate-400 hover:bg-white/10 hover:text-white" @click="showReputationInfoModal = false">✕</button>
        </div>
        <div class="space-y-2 text-xs leading-relaxed text-slate-200/90">
          <p>Проверка через команды: <b>/karma</b> — личная карма, <b>/topkarma</b> — топ группы.</p>
          <p>Начисление идёт, когда участник пишет слова благодарности в ответ на сообщение другого участника (самому себе начислить нельзя; есть кулдаун, чтобы не накручивать).</p>
          <p>После начисления Guard отправляет подтверждение в фирменном стиле: начисление, текущий баланс и быстрые команды.</p>
          <p>Карма хранится отдельно для каждой группы, между чатами не смешивается.</p>
          <p><b>Слова в базе:</b> {{ (reputationDefaultWords || []).join(', ') || '—' }}</p>
        </div>
      </div>
    </div>
    <div
      v-if="showReputationSettingsModal"
      class="fixed inset-0 z-[279] flex items-center justify-center bg-black/70 p-3 backdrop-blur-[3px]"
      @click.self="showReputationSettingsModal = false"
    >
      <div class="flex max-h-[84vh] w-full max-w-xl flex-col overflow-hidden rounded-2xl border border-white/12 bg-gradient-to-b from-zinc-900/85 to-zinc-950/95 p-3 text-slate-100 shadow-[0_28px_90px_-28px_rgba(0,0,0,0.9)] ring-1 ring-inset ring-white/[0.06] backdrop-blur-2xl">
        <div class="mb-2 flex items-center justify-between gap-2 border-b border-white/10 pb-2">
          <h3 class="text-sm font-semibold text-white">Настройки благодарности</h3>
          <button type="button" class="rounded-lg px-2 py-1 text-sm text-slate-400 hover:bg-white/10 hover:text-white" @click="showReputationSettingsModal = false">✕</button>
        </div>
        <div class="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          <div class="rounded-lg border border-white/12 bg-black/25 p-2">
            <p class="text-[10px] font-semibold uppercase tracking-wide text-slate-300">Слова в базе</p>
            <p class="mt-1 text-[11px] text-slate-300/90">{{ (reputationDefaultWords || []).join(', ') || '—' }}</p>
          </div>
          <div class="flex flex-wrap gap-2">
            <input
              v-model="newReputationWord"
              type="text"
              placeholder="Свое слово (напр. мерси)"
              class="min-w-0 flex-1 rounded-lg border border-white/15 bg-black/25 px-2.5 py-1.5 text-xs text-slate-100 placeholder:text-slate-500"
              :disabled="reputationWordsLoading"
              @keydown.enter.prevent="addReputationWord()"
            >
            <button
              type="button"
              class="guard-green-soft rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
              :disabled="reputationWordsLoading || !(newReputationWord || '').trim()"
              @click="addReputationWord()"
            >
              Добавить
            </button>
          </div>
          <div class="grid gap-2 sm:grid-cols-2">
            <div class="rounded-lg border border-white/12 bg-black/25 p-2">
              <div class="flex items-center justify-between gap-2">
                <p class="text-[10px] font-semibold uppercase tracking-wide text-slate-300">Свои слова</p>
                <button
                  v-if="reputationWords.length > 3"
                  type="button"
                  class="rounded-md border border-cyan-400/40 bg-cyan-500/15 px-2 py-0.5 text-[10px] font-semibold text-cyan-100"
                  @click="showReputationWordsModal = true"
                >
                  Все
                </button>
              </div>
              <ul v-if="reputationWords.length" class="mt-1 space-y-1">
                <li
                  v-for="w in reputationWords.slice(0, 3)"
                  :key="`rep-word-${w}`"
                  class="flex items-center justify-between rounded-md bg-white/8 px-2 py-1 text-[11px]"
                >
                  <span class="text-slate-200">{{ w }}</span>
                  <button
                    type="button"
                    class="rounded p-0.5 text-rose-300 hover:bg-rose-500/15"
                    :disabled="reputationWordsLoading"
                    @click="removeReputationWord(w)"
                  >✕</button>
                </li>
              </ul>
              <p v-else class="mt-1 text-[11px] text-slate-400">Индивидуальные слова не заданы.</p>
            </div>
            <div class="rounded-lg border border-white/12 bg-black/25 p-2">
              <div class="flex items-center justify-between gap-2">
                <p class="text-[10px] font-semibold uppercase tracking-wide text-slate-300">Топ группы</p>
                <button
                  v-if="reputationTop.length > 3"
                  type="button"
                  class="rounded-md border border-violet-400/40 bg-violet-500/15 px-2 py-0.5 text-[10px] font-semibold text-violet-100"
                  @click="showReputationTopModal = true"
                >
                  Все
                </button>
              </div>
              <p v-if="reputationLoading" class="mt-1 text-[11px] text-slate-400">Считаем...</p>
              <ul v-else-if="reputationTop.length" class="mt-1 space-y-1">
                <li
                  v-for="(row, idx) in reputationTop.slice(0, 3)"
                  :key="`rep-top-${row.user_id}`"
                  class="flex items-center justify-between rounded-md bg-white/8 px-2 py-1 text-[11px]"
                >
                  <button
                    type="button"
                    class="text-left text-cyan-200 underline decoration-cyan-500/40 underline-offset-2 hover:text-cyan-100"
                    @click="openReputationUserProfile(row)"
                  >
                    #{{ idx + 1 }} · {{ row.username ? `@${String(row.username).replace(/^@+/, '')}` : `id${row.user_id}` }}
                  </button>
                  <span class="font-semibold text-lime-300">{{ row.score }}</span>
                </li>
              </ul>
              <p v-else class="mt-1 text-[11px] text-slate-400">Пока без начислений.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div
      v-if="showMainInfoModal"
      class="fixed inset-0 z-[266] flex items-center justify-center bg-black/65 p-3"
      @click.self="showMainInfoModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-sky-300/50 bg-white p-4 shadow-2xl dark:border-sky-700/60 dark:bg-gray-800">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold text-gray-900 dark:text-white">😈 Защита этого чата</h3>
              <button
                type="button"
            class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10"
            @click="showMainInfoModal = false"
              >
            ✕
              </button>
            </div>
        <div class="space-y-2 text-xs text-gray-700 dark:text-gray-300">
          <p>Тумблер касается только того чата, который сейчас открыт — остальные не трогаю.</p>
          <p><strong>ВКЛ</strong> — работаю по твоим фильтрам и наказаниям, как договорились.</p>
          <p><strong>ВЫКЛ</strong> — отдыхаю в этом чате, но настройки не стираю, чтобы не собирать заново.</p>
          <p class="text-xs text-slate-400">
            Удобно на паузу поставить один зал, пока в другом творится праздник.
          </p>
          </div>
        </div>
    </div>
    <div
      v-if="showReputationWordsModal"
      class="fixed inset-0 z-[280] flex items-center justify-center bg-black/70 p-3 backdrop-blur-[3px]"
      @click.self="showReputationWordsModal = false"
    >
      <div class="flex max-h-[84vh] w-full max-w-md flex-col overflow-hidden rounded-2xl border border-white/12 bg-gradient-to-b from-zinc-900/85 to-zinc-950/95 p-3 text-slate-100 shadow-[0_28px_90px_-28px_rgba(0,0,0,0.9)] ring-1 ring-inset ring-white/[0.06] backdrop-blur-2xl">
        <div class="mb-2 flex items-center justify-between gap-2 border-b border-white/10 pb-2">
          <h3 class="text-sm font-semibold text-white">Свои слова</h3>
          <button type="button" class="rounded-lg px-2 py-1 text-sm text-slate-400 hover:bg-white/10 hover:text-white" @click="showReputationWordsModal = false">✕</button>
        </div>
        <div class="min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
          <div
            v-for="w in reputationWords"
            :key="`rep-word-modal-${w}`"
            class="flex items-center justify-between rounded-md border border-white/10 bg-white/[0.06] px-2 py-1 text-xs"
          >
            <span class="text-slate-100">{{ w }}</span>
            <button type="button" class="rounded p-0.5 text-rose-300 hover:bg-rose-500/15" :disabled="reputationWordsLoading" @click="removeReputationWord(w)">✕</button>
          </div>
        </div>
      </div>
    </div>
    <div
      v-if="showReputationTopModal"
      class="fixed inset-0 z-[281] flex items-center justify-center bg-black/70 p-3 backdrop-blur-[3px]"
      @click.self="showReputationTopModal = false"
    >
      <div class="flex max-h-[84vh] w-full max-w-md flex-col overflow-hidden rounded-2xl border border-white/12 bg-gradient-to-b from-zinc-900/85 to-zinc-950/95 p-3 text-slate-100 shadow-[0_28px_90px_-28px_rgba(0,0,0,0.9)] ring-1 ring-inset ring-white/[0.06] backdrop-blur-2xl">
        <div class="mb-2 flex items-center justify-between gap-2 border-b border-white/10 pb-2">
          <h3 class="text-sm font-semibold text-white">Топ группы</h3>
          <button type="button" class="rounded-lg px-2 py-1 text-sm text-slate-400 hover:bg-white/10 hover:text-white" @click="showReputationTopModal = false">✕</button>
        </div>
        <div class="min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
          <div
            v-for="(row, idx) in reputationTop"
            :key="`rep-top-modal-${row.user_id}`"
            class="flex items-center justify-between rounded-md border border-white/10 bg-white/[0.06] px-2 py-1 text-xs"
          >
            <button
              type="button"
              class="text-left text-cyan-200 underline decoration-cyan-500/40 underline-offset-2 hover:text-cyan-100"
              @click="openReputationUserProfile(row)"
            >
              #{{ idx + 1 }} · {{ row.username ? `@${String(row.username).replace(/^@+/, '')}` : `id${row.user_id}` }}
            </button>
            <span class="font-semibold text-lime-300">{{ row.score }}</span>
          </div>
        </div>
      </div>
    </div>
    <div
      v-if="showChatSwitchInfoModal"
      class="fixed inset-0 z-[266] flex items-center justify-center bg-black/65 p-3"
      @click.self="showChatSwitchInfoModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-sky-300/50 bg-white p-4 shadow-2xl dark:border-sky-700/60 dark:bg-gray-800">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold text-gray-900 dark:text-white">😈 Выбор чата</h3>
          <button
            type="button"
            class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10"
            @click="showChatSwitchInfoModal = false"
          >
            ✕
          </button>
        </div>
        <div class="space-y-2 text-xs text-gray-700 dark:text-gray-300">
          <p>Сверху видно, какой чат сейчас «на игле» — именно его кручу.</p>
          <p>«Выбор чата» открывает список подключённых залов и мгновенно перекидывает настройки туда, куда ткнул.</p>
          <p class="text-xs text-slate-400">
            Всё, что ниже на экране, относится только к активному чату — без сюрпризов для соседей.
          </p>
        </div>
      </div>
    </div>
    <Teleport to="body">
      <div
        v-if="showStopwordsModal"
        class="fixed inset-0 z-[260] flex items-center justify-center bg-black/60 p-4 backdrop-blur-[2px]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="stopwords-modal-title"
        @click.self="showStopwordsModal = false"
      >
        <div
          class="flex max-h-[min(78vh,36rem)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/15 bg-gradient-to-b from-slate-900 to-slate-950 text-slate-100 shadow-[0_24px_80px_-20px_rgba(0,0,0,0.85)] ring-1 ring-cyan-500/20"
          @click.stop
        >
          <div class="flex shrink-0 items-start justify-between gap-3 border-b border-white/10 px-4 py-3">
            <div>
              <h3 id="stopwords-modal-title" class="text-sm font-semibold text-white">Стоп-слова</h3>
              <p class="mt-0.5 text-[11px] text-slate-400">Прокрутка внутри списка · закрыть — вне окна или ✕</p>
            </div>
            <button
              type="button"
              class="rounded-lg px-2.5 py-1 text-xs text-slate-400 hover:bg-white/10 hover:text-white"
              @click="showStopwordsModal = false"
            >
              ✕
            </button>
          </div>
          <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-3 [-webkit-overflow-scrolling:touch]">
            <ul v-if="(chat?.stopwords || []).length" class="space-y-1.5">
              <li
                v-for="w in (chat?.stopwords || [])"
                :key="`modal-${w}`"
                class="flex items-center justify-between rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm"
              >
                <span class="font-mono text-slate-100">{{ w }}</span>
                <button
                  type="button"
                  class="rounded-lg px-2 py-1 text-xs text-rose-300 hover:bg-rose-500/15"
                  :disabled="stopwordLoading"
                  aria-label="Удалить"
                  @click="removeStopword(w)"
                >
                  Удалить
                </button>
              </li>
            </ul>
            <p v-else class="py-8 text-center text-sm text-slate-500">Список пуст</p>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="showProtectionPinModal"
        class="fixed inset-0 z-[305] flex items-end justify-center bg-black/75 px-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] pt-[max(12px,calc(env(safe-area-inset-top,0px)+48px))] backdrop-blur-md md:items-center md:pb-6"
        role="dialog"
        aria-modal="true"
        @click.self="cancelProtectionPin"
      >
        <div
          class="relative w-full max-w-sm overflow-hidden rounded-3xl bg-[radial-gradient(140%_100%_at_0%_0%,rgba(34,197,94,0.18)_0%,rgba(15,23,42,0.94)_55%,rgba(7,11,21,0.96)_100%)] p-4 text-slate-100 shadow-[0_30px_60px_-30px_rgba(34,197,94,0.45)]"
          @click.stop
        >
          <span aria-hidden="true" class="pointer-events-none absolute -right-16 -top-16 h-44 w-44 rounded-full bg-emerald-400/20 blur-3xl" />
          <div class="relative mb-2 flex items-center justify-between gap-2">
            <h3 class="truncate text-base font-extrabold text-white">PIN-код</h3>
            <button type="button" class="rounded-full bg-white/10 px-2 py-1 text-sm text-white/85 transition hover:bg-white/15" @click="cancelProtectionPin">✕</button>
          </div>
          <p class="relative mb-3 text-[12px] text-white/65">Введите PIN из настроек безопасности, чтобы поставить Guard на паузу.</p>
          <input
            v-model="protectionPinInput"
            type="password"
            inputmode="numeric"
            pattern="[0-9]*"
            maxlength="12"
            autocomplete="one-time-code"
            class="relative mb-2 w-full rounded-xl bg-white/10 px-3 py-2.5 text-center text-lg font-bold tracking-[0.5em] text-white outline-none ring-1 ring-white/10 focus:ring-emerald-400/50"
            placeholder="••••"
            @keyup.enter="submitProtectionPin"
          />
          <p v-if="protectionPinError" class="relative mb-2 text-[11px] font-semibold text-rose-200">{{ protectionPinError }}</p>
          <div class="relative flex justify-end gap-2">
            <button type="button" class="rounded-lg bg-white/10 px-3 py-1.5 text-xs font-semibold text-white/85 transition hover:bg-white/15" @click="cancelProtectionPin">Отмена</button>
            <button type="button" class="rounded-lg bg-emerald-500/30 px-3 py-1.5 text-xs font-bold text-emerald-100 transition hover:bg-emerald-500/40" @click="submitProtectionPin">Продолжить</button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="postRulesImagePreviewUrl"
        class="fixed inset-0 z-[270] flex items-center justify-center bg-black/75 p-4 backdrop-blur-[2px]"
        role="dialog"
        aria-modal="true"
        @click.self="postRulesImagePreviewUrl = ''"
      >
        <div class="w-full max-w-2xl rounded-2xl border border-white/15 bg-zinc-950/90 p-3 shadow-2xl" @click.stop>
          <div class="mb-2 flex justify-end">
            <button type="button" class="rounded-lg px-2 py-1 text-xs text-slate-300 hover:bg-white/10" @click="postRulesImagePreviewUrl = ''">✕</button>
          </div>
          <img :src="postRulesImagePreviewUrl" alt="preview" class="max-h-[75vh] w-full rounded-lg object-contain" />
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="welcomeImagePreviewUrl && showWelcomeSettingsModal"
        class="fixed inset-0 z-[270] flex items-center justify-center bg-black/75 p-4 backdrop-blur-[2px]"
        role="dialog"
        aria-modal="true"
        @click.self="welcomeImagePreviewUrl = ''"
      >
        <div class="w-full max-w-2xl rounded-2xl border border-white/12 bg-zinc-950/88 p-3 shadow-2xl backdrop-blur-xl" @click.stop>
          <div class="mb-2 flex justify-end">
            <button type="button" class="rounded-lg px-2 py-1 text-xs text-slate-300 hover:bg-white/10" @click="welcomeImagePreviewUrl = ''">✕</button>
          </div>
          <img :src="welcomeImagePreviewUrl" alt="Превью фото приветствия" class="max-h-[78vh] w-full rounded-lg object-contain" />
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="showWelcomeSettingsModal && chat?.rule"
        class="fixed inset-0 z-[258] flex items-center justify-center bg-black/55 p-3 sm:p-4 backdrop-blur-[2px]"
        role="dialog"
        aria-modal="true"
        @click.self="closeWelcomeSettingsModal()"
      >
        <div
          class="flex max-h-[min(90vh,48rem)] w-full max-w-2xl flex-col overflow-hidden rounded-[1.35rem] border border-white/12 bg-zinc-950/76 p-0 text-zinc-100 shadow-[0_34px_90px_-28px_rgba(0,0,0,0.78),inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-2xl backdrop-saturate-150"
          @click.stop
        >
          <div class="flex items-center justify-between border-b border-white/6 bg-gradient-to-r from-white/[0.04] to-transparent px-4 py-3">
            <div class="flex items-center gap-2">
              <h3 class="text-sm font-semibold text-white">👋 Приветствие новых участников</h3>
              <button
                type="button"
                class="link-glass-info-btn"
                :class="welcomeInfoModal === 'main' ? 'link-glass-info-btn--active' : ''"
                aria-label="Подсказка: автоприветствие в этом чате"
                @click="welcomeInfoModal = welcomeInfoModal === 'main' ? '' : 'main'"
              >ⓘ</button>
            </div>
            <button type="button" class="rounded-lg px-2 py-1 text-xs text-slate-400 hover:bg-white/10" @click="closeWelcomeSettingsModal()">✕</button>
          </div>
          <div class="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3 sm:px-4">
            <div class="glass-panel flex items-center justify-between gap-2 p-3">
              <span class="text-xs text-slate-200">Включить приветствие в этом чате</span>
              <button
                type="button"
                :class="boolToggleClass(!!welcomeForm.enabled)"
                class="min-w-[5rem] rounded-lg px-2.5 py-1 text-xs font-medium"
                @click="welcomeForm.enabled = !welcomeForm.enabled"
              >
                {{ welcomeForm.enabled ? 'ВКЛ' : 'ВЫКЛ' }}
              </button>
            </div>
            <p
              v-if="chat?.rule?.delete_join_messages"
              class="rounded-xl border border-amber-400/25 bg-amber-950/20 px-3 py-2 text-[11px] leading-relaxed text-amber-100"
            >
              Сейчас включено удаление сервисного «вступил». Поэтому в чате не видно системную плашку входа, но приветствие всё равно отправится новому участнику.
            </p>
            <div class="glass-panel p-3">
              <div class="mb-2 flex items-center justify-between gap-2">
                <p class="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Оформление текста</p>
                <button
                  type="button"
                  class="link-glass-info-btn"
                  :class="welcomeInfoModal === 'text' ? 'link-glass-info-btn--active' : ''"
                  aria-label="Подсказка: редактор и плейсхолдеры"
                  @click="welcomeInfoModal = welcomeInfoModal === 'text' ? '' : 'text'"
                >ⓘ</button>
              </div>
              <div class="mb-2 flex flex-wrap items-center gap-2">
                <label class="post-rules-tool-btn cursor-pointer px-3 py-1.5 text-[11px] font-semibold">
                  <span v-if="welcomePhotoBusy">Загрузка…</span>
                  <span v-else>Добавить фото</span>
                  <input type="file" accept="image/*" class="hidden" :disabled="welcomePhotoBusy || welcomeBusy" @change="onWelcomePhotoPicked" />
                </label>
                <button
                  v-if="welcomePreviewUrl"
                  type="button"
                  class="h-9 w-9 shrink-0 overflow-hidden rounded-lg border border-white/12 bg-black/40 ring-1 ring-white/10"
                  title="Открыть превью"
                  @click="openWelcomeImagePreview()"
                >
                  <img :src="welcomePreviewUrl" alt="" class="h-full w-full object-cover" />
                </button>
                <button
                  v-if="welcomePreviewUrl"
                  type="button"
                  class="post-rules-tool-btn border-rose-400/30 bg-rose-500/15 px-2 py-1 text-[10px] text-rose-100"
                  :disabled="welcomePhotoBusy"
                  @click="removeWelcomePhoto()"
                >Удалить фото</button>
                <button
                  type="button"
                  class="post-rules-tool-btn px-3 py-1.5 text-[11px] font-semibold"
                  @click="welcomeInfoModal = ''; showWelcomeButtonsModal = true"
                >
                  ＋ Кнопки под постом
                </button>
              </div>
              <div class="mb-2 flex flex-wrap gap-1.5">
                <button
                  type="button"
                  class="post-rules-tool-btn font-semibold"
                  :class="welcomeFormatState.bold ? 'border-white/35 bg-white/10' : ''"
                  title="Жирный"
                  @mousedown.prevent
                  @click="welcomeFormatBold"
                >Ж</button>
                <button
                  type="button"
                  class="post-rules-tool-btn italic font-semibold"
                  :class="welcomeFormatState.italic ? 'border-white/35 bg-white/10' : ''"
                  title="Курсив"
                  @mousedown.prevent
                  @click="welcomeFormatItalic"
                >К</button>
                <button
                  type="button"
                  class="post-rules-tool-btn font-semibold underline"
                  :class="welcomeFormatState.underline ? 'border-white/35 bg-white/10' : ''"
                  title="Подчёркнутый"
                  @mousedown.prevent
                  @click="welcomeFormatUnderline"
                >Ч</button>
                <button
                  type="button"
                  class="post-rules-tool-btn font-semibold line-through"
                  :class="welcomeFormatState.strike ? 'border-white/35 bg-white/10' : ''"
                  title="Зачёркнутый"
                  @mousedown.prevent
                  @click="welcomeFormatStrike"
                >З</button>
                <button type="button" class="post-rules-tool-btn" title="Скрытый" @mousedown.prevent @click="welcomeFormatSpoiler">👁</button>
                <button type="button" class="post-rules-tool-btn" title="Код" @mousedown.prevent @click="welcomeFormatCode">Код</button>
                <button type="button" class="post-rules-tool-btn" title="PRE" @mousedown.prevent @click="welcomeFormatPre">PRE</button>
                <button type="button" class="post-rules-tool-btn" title="Цитата" @mousedown.prevent @click="welcomeFormatBlockquote">❝ Цитата</button>
                <button type="button" class="post-rules-tool-btn" title="Ссылка" @mousedown.prevent @click="welcomeFormatLink">🔗 Ссылка</button>
                <button type="button" class="post-rules-tool-btn" title="Имя вступившего (как в Telegram)" @mousedown.prevent @click="welcomeInsertPlain('{first_name}')">{first_name}</button>
                <button type="button" class="post-rules-tool-btn" title="Полное имя" @mousedown.prevent @click="welcomeInsertPlain('{full_name}')">{full_name}</button>
                <button type="button" class="post-rules-tool-btn" title="Ник @username или пусто" @mousedown.prevent @click="welcomeInsertPlain('{username}')">{username}</button>
                <button type="button" class="post-rules-tool-btn" title="Название этой группы" @mousedown.prevent @click="welcomeInsertPlain('{chat_title}')">{chat_title}</button>
              </div>
              <p class="mb-1 text-[10px] font-medium uppercase tracking-wide text-zinc-500">Текст приветствия</p>
              <div class="mb-1.5 flex flex-wrap gap-1.5">
                <button
                  type="button"
                  class="post-rules-tool-btn px-2.5 text-zinc-200"
                  :class="!welcomeCanUndo() ? 'opacity-40' : ''"
                  :disabled="!welcomeCanUndo()"
                  title="Откат"
                  @mousedown.prevent
                  @click="welcomeUndo"
                >↶ Назад</button>
                <button
                  type="button"
                  class="post-rules-tool-btn px-2.5 text-zinc-200"
                  :class="!welcomeCanRedo() ? 'opacity-40' : ''"
                  :disabled="!welcomeCanRedo()"
                  title="Повтор"
                  @mousedown.prevent
                  @click="welcomeRedo"
                >↷ Вперёд</button>
              </div>
              <div
                ref="welcomeBodyRef"
                contenteditable="true"
                class="welcome-rich-editor max-h-56 min-h-[8rem] w-full overflow-y-auto rounded-xl border border-white/10 bg-slate-950/90 px-3 py-2 text-sm leading-relaxed text-slate-100 focus-within:border-white/20 focus-within:ring-1 focus-within:ring-white/10"
                data-placeholder="Привет, {first_name}! Добро пожаловать в {chat_title}"
                @input="onWelcomeBodyInput"
                @click="onWelcomeBodyClick"
                @mouseup="onWelcomeEditorSelectionChange"
                @keyup="onWelcomeEditorSelectionChange"
              />
              <p class="mt-1 text-[10px] leading-relaxed text-zinc-500">
                Плейсхолдеры: <strong>{first_name}</strong> — имя, <strong>{full_name}</strong> — полное имя, <strong>{username}</strong> — @ник или пусто, <strong>{chat_title}</strong> — название чата. Настройки привязаны к этому чату и синхронизируются с сервером для вашего аккаунта.
              </p>
            </div>
            <div class="glass-panel p-3">
              <div class="mb-2 flex items-center justify-between gap-2">
                <p class="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Частота отправки</p>
                <button
                  type="button"
                  class="link-glass-info-btn"
                  :class="welcomeInfoModal === 'rate' ? 'link-glass-info-btn--active' : ''"
                  aria-label="Подсказка: кому писать и лимит в минуту"
                  @click="welcomeInfoModal = welcomeInfoModal === 'rate' ? '' : 'rate'"
                >ⓘ</button>
              </div>
              <div class="mb-2 grid grid-cols-2 gap-2">
                <div>
                  <p class="mb-1 text-[10px] text-zinc-500">Отправлять каждому N-му вступившему</p>
                  <input v-model.number="welcomeForm.everyNJoins" type="number" min="1" max="500" class="w-full rounded-lg border border-white/14 bg-white/[0.06] px-2 py-1.5 text-xs" />
                </div>
                <div>
                  <p class="mb-1 text-[10px] text-zinc-500">Доп. лимит сообщений в минуту</p>
                  <div class="flex flex-wrap gap-1.5">
                    <button
                      v-for="n in [0,1,2,3,5,10]"
                      :key="`wel-rate-${n}`"
                      type="button"
                      class="rounded-lg px-2 py-1 text-[11px] font-semibold"
                      :class="Number(welcomeForm.maxPerMin || 0) === n ? 'guard-green-soft text-slate-900' : protToggleOff"
                      @click="welcomeForm.maxPerMin = n"
                    >
                      {{ n === 0 ? 'без лимита' : `${n}/мин` }}
                    </button>
                  </div>
                </div>
              </div>
            </div>
            <div class="glass-panel p-3">
              <div class="flex items-center justify-between gap-2">
                <div class="flex min-w-0 items-center gap-1.5">
                  <span class="text-xs text-slate-200">Молчать при рейде</span>
                  <button
                    type="button"
                    class="link-glass-info-btn shrink-0"
                    :class="welcomeInfoModal === 'raid' ? 'link-glass-info-btn--active' : ''"
                    aria-label="Подсказка: тишина при всплеске входов"
                    @click="welcomeInfoModal = welcomeInfoModal === 'raid' ? '' : 'raid'"
                  >ⓘ</button>
                </div>
                <button
                  type="button"
                  :class="boolToggleClass(!!welcomeForm.silentOnRaid)"
                  class="min-w-[5rem] shrink-0 rounded-lg px-2.5 py-1 text-xs font-medium"
                  @click="welcomeForm.silentOnRaid = !welcomeForm.silentOnRaid"
                >
                  {{ welcomeForm.silentOnRaid ? 'ВКЛ' : 'ВЫКЛ' }}
                </button>
              </div>
              <div v-if="welcomeForm.silentOnRaid" class="mt-2 grid grid-cols-2 gap-2">
                <div>
                  <p class="mb-1 text-[10px] text-zinc-500">Порог входов</p>
                  <input v-model.number="welcomeForm.raidThreshold" type="number" min="2" max="200" class="w-full rounded-lg border border-white/14 bg-white/[0.06] px-2 py-1.5 text-xs" />
                </div>
                <div>
                  <p class="mb-1 text-[10px] text-zinc-500">Окно (мин)</p>
                  <input v-model.number="welcomeForm.raidWindowMinutes" type="number" min="1" max="60" class="w-full rounded-lg border border-white/14 bg-white/[0.06] px-2 py-1.5 text-xs" />
                </div>
              </div>
            </div>
          </div>
          <div class="flex items-center justify-end gap-2 border-t border-white/10 px-3 py-2.5 sm:px-4">
            <button type="button" class="post-rules-action-btn post-rules-action-btn--cancel" @click="showWelcomeSettingsModal = false">Отмена</button>
            <button type="button" class="post-rules-action-btn post-rules-action-btn--save" :disabled="welcomeBusy" @click="saveWelcomeSettings()">{{ welcomeBusy ? 'Сохранение…' : 'Сохранить' }}</button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="showPostRulesSettingsModal && chat?.rule"
        class="fixed inset-0 z-[259] flex items-center justify-center bg-black/55 p-3 sm:p-4 backdrop-blur-[2px]"
        role="dialog"
        aria-modal="true"
        @click.self="closePostRulesSettingsModal()"
      >
        <div
          class="flex max-h-[min(90vh,48rem)] w-full max-w-3xl flex-col overflow-hidden rounded-[1.35rem] border border-white/12 bg-zinc-950/76 p-0 text-zinc-100 shadow-[0_34px_90px_-28px_rgba(0,0,0,0.78),inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-2xl backdrop-saturate-150"
          @click.stop
        >
          <div class="flex items-center justify-between border-b border-white/6 bg-gradient-to-r from-white/[0.04] to-transparent px-4 py-3">
            <div>
              <div class="flex items-center gap-2">
                <h3 class="text-sm font-semibold text-white">⚙️ Защита · правила в группе</h3>
                <span
                  class="inline-flex h-2.5 w-2.5 rounded-full"
                  :class="postRulesServerDirty ? 'bg-rose-400' : 'bg-emerald-400'"
                  :title="postRulesGroupDraftStatusLabel"
                />
              </div>
              <p class="text-[10px]" :class="postRulesServerDirty ? 'text-rose-300' : 'text-emerald-300'">{{ postRulesGroupEditingLabel }}</p>
              <p class="truncate text-[11px] text-slate-400">Группа: {{ postRulesCurrentGroupTitle() }}</p>
            </div>
            <button type="button" class="rounded-lg px-2 py-1 text-xs text-slate-400 hover:bg-white/10" @click="closePostRulesSettingsModal()">✕</button>
          </div>

          <div class="space-y-2 px-4 pt-2">
            <div class="flex items-center justify-between gap-2">
              <span class="text-[11px] text-slate-500">Правила в Telegram</span>
              <div class="flex items-center gap-1.5">
                <button
                  type="button"
                  class="inline-flex h-5 min-w-5 items-center justify-center rounded-full border border-cyan-400/35 bg-cyan-950/30 px-1 text-[10px] font-extrabold text-cyan-200"
                  @click="postRulesGroupInfoOpen = !postRulesGroupInfoOpen"
                >i</button>
                <button
                  type="button"
                  :class="boolToggleClass(!!postRulesGroupForm.enabled)"
                  class="min-w-[5rem] rounded-lg px-2.5 py-1 text-xs font-medium"
                  @click="postRulesGroupForm.enabled = !postRulesGroupForm.enabled; postRulesTouchServerDirty()"
                >{{ postRulesGroupForm.enabled ? 'ВКЛ' : 'ВЫКЛ' }}</button>
              </div>
            </div>
            <div
              v-if="postRulesGroupInfoOpen"
              class="max-h-[min(42vh,18rem)] overflow-y-auto overscroll-y-contain rounded-lg border border-cyan-400/20 bg-cyan-950/20 px-2.5 py-2 text-[11px] leading-snug text-cyan-100 [-webkit-overflow-scrolling:touch]"
            >
              <p class="mb-1 font-semibold text-cyan-50">Как это работает (Guard)</p>
              <p>• <b>ВКЛ</b> — шаблон правил активен: ручная отправка и автоотправка (если включены сценарии ниже). Без ВКЛ бот не шлёт правила в чат.</p>
              <p>• <b>«Любое срабатывание фильтра»</b> — Guard уже принял решение по сообщению (удалил, замутил, забанил или включил режим observe). Счётчик растёт на <b>каждое</b> такое событие; каждые N — пост с правилами.</p>
              <p>• <b>«На наказание»</b> — только если реально применилось жёсткое действие: сообщение удалено, или мут/бан удалось применить. Режим observe без удаления сюда не входит.</p>
              <p>• Если в одном сообщении выполнены оба порога — уходит <b>одно</b> сообщение с правилами.</p>
              <p>• <b>«Запуск»</b> — выбранный шаблон записывается в настройки Telegram-бота: его текст/фото/кнопки пойдут в авто и в ручную рассылку, пока не выключите (ВЫКЛ) не переключите на другой шаблон. Без запуска правила в БД остаются от «Сохранить», не от черновиков. Ручной «Отправить в группу» с несколькими шаблонами — сначала выбор черновика; по умолчанию предлагается последний изменённый или тот, что в «Запуске».</p>
              <p>• <b>Шаблоны</b> — синхронизируются с сервером для вашего Telegram-аккаунта (телефон и ПК один список, без перемешивания). Очень большие встроенные картинки в шаблоне могут не уместиться в облако — тогда превью подтянется с сервера правил чата. При закрытии окна несохранённые правки в Telegram (включая автоотправку) сохраняются на сервер, если были изменения.</p>
              <p>• <b>Логи автоотправки</b> — на сервере бота: <code class="rounded bg-black/30 px-1">grep group_rules_autosend</code>. События <code class="rounded bg-black/30 px-1">attempt</code> / <code class="rounded bg-black/30 px-1">ok</code> / <code class="rounded bg-black/30 px-1">send_failed</code> — INFO; счётчики «ещё не N» (<code class="rounded bg-black/30 px-1">wait</code>), пропуски (<code class="rounded bg-black/30 px-1">skip</code>), снимок после действия (<code class="rounded bg-black/30 px-1">after_act</code>) — DEBUG (включите DEBUG на логгере приложения).</p>
            </div>
            <div v-if="postRulesUnsavedBanner" class="rounded-lg border border-amber-400/25 bg-amber-950/25 px-2.5 py-2 text-[11px] text-amber-100">
              Есть несохранённые изменения: сначала «Сохранить черновик» (шаблон), затем «Сохранить» (в Telegram).
            </div>
            <div v-if="postRulesShowSaved" class="rounded-lg border border-emerald-400/25 bg-emerald-950/25 px-2.5 py-2 text-[11px] text-emerald-100">
              Изменения в Telegram сохранены
            </div>
          </div>

          <div class="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3 sm:px-4">
              <div class="glass-panel p-3">
                <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <p class="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Черновики</p>
                  <div class="flex flex-wrap items-center justify-end gap-1.5">
                    <button
                      type="button"
                      class="rounded-lg border border-emerald-400/40 bg-emerald-500/15 px-2 py-1 text-[11px] font-semibold text-emerald-100 hover:bg-emerald-500/25"
                      @click="postRulesCreateGroupDraft()"
                    >Создать черновик</button>
                    <button
                      v-if="postRulesShowSaveDraftButton"
                      type="button"
                      class="rounded-lg border border-violet-400/45 bg-violet-500/20 px-2 py-1 text-[11px] font-semibold text-violet-100 hover:bg-violet-500/30"
                      @click="postRulesSaveDraft()"
                    >Сохранить черновик</button>
                  </div>
                </div>
                <p v-if="postRulesEditingDraftName" class="mb-2 text-[11px] text-cyan-200">Сейчас правим: {{ postRulesEditingDraftName }}</p>
                <p class="mb-2 text-[11px] text-slate-400">Чат: {{ postRulesCurrentGroupTitle() }}</p>
                <div class="space-y-1.5">
                  <div
                    v-for="d in postRulesDraftsForChat.slice(0, 8)"
                    :key="`prd-${d.id}`"
                    class="flex flex-wrap items-center gap-1.5 rounded-lg border px-2 py-1.5"
                    :class="String(postRulesActiveDraftId || '') === String(d.id || '') ? 'border-cyan-400/45 bg-cyan-500/12' : 'border-white/10 bg-white/[0.04]'"
                  >
                    <span
                      class="inline-flex h-2 w-2 shrink-0 rounded-full"
                      :class="String(postRulesGroupRunActiveId || '') === String(d.id || '') ? 'bg-emerald-400' : 'bg-zinc-600'"
                      :title="String(postRulesGroupRunActiveId || '') === String(d.id || '') ? 'Запущен в Telegram' : 'Не запущен'"
                    />
                    <div class="min-w-0 flex-1">
                      <div class="flex min-w-0 items-center gap-2">
                        <input
                          :value="postRulesDraftDisplayName(d)"
                          type="text"
                          class="min-w-0 flex-1 rounded-md border border-white/10 bg-white/[0.05] px-2 py-1 text-[11px] text-slate-200"
                          @focus="postRulesBeginDraftNameEdit(d)"
                          @input="postRulesOnDraftNameInput(d, $event)"
                        />
                        <button
                          v-if="postRulesDraftNameDirty && String(postRulesDraftNameEditId || '') === String(d.id || '')"
                          type="button"
                          class="shrink-0 rounded-md border border-emerald-300/35 bg-emerald-500/20 px-2 py-0.5 text-[10px] font-extrabold text-emerald-100"
                          @click="postRulesCommitDraftName(d)"
                        >✓</button>
                      </div>
                      <p class="text-[10px] text-slate-500">{{ postRulesDraftSavedAtLabel(d.savedAt) }}</p>
                    </div>
                    <button type="button" class="rounded border border-white/20 bg-white/[0.08] px-1.5 py-0.5 text-[10px] text-slate-200" :disabled="postRulesDraftLoadingId === d.id" @click="postRulesApplyDraft(d)">{{ postRulesDraftLoadingId === d.id ? '…' : 'Править' }}</button>
                    <button
                      type="button"
                      class="rounded px-1.5 py-0.5 text-[10px] font-semibold"
                      :disabled="!!postRulesGroupRunDraftBusyId"
                      :class="String(postRulesGroupRunActiveId || '') === String(d.id || '') ? 'border border-rose-400/35 bg-rose-500/20 text-rose-100' : 'border border-emerald-400/35 bg-emerald-500/20 text-emerald-100'"
                      @click="postRulesToggleRunGroupDraft(d)"
                    >{{ String(postRulesGroupRunDraftBusyId || '') === String(d.id) ? '…' : (String(postRulesGroupRunActiveId || '') === String(d.id) ? 'ВЫКЛ' : 'Запуск') }}</button>
                    <button type="button" class="rounded border border-rose-400/25 bg-rose-500/15 px-1 py-0.5 text-[10px] text-rose-100 hover:bg-rose-500/25" @click="postRulesDeleteDraft(d.id)">🗑</button>
                  </div>
                  <p v-if="!postRulesDraftsForChat.length" class="text-[11px] text-slate-500">Черновиков пока нет.</p>
                </div>
              </div>

              <div class="glass-panel p-3">
                <p class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Автоотправка в чат</p>
                <p class="mb-2 text-[10px] text-slate-500">Только при включённом <b>ВКЛ</b> выше. Два независимых счётчика — «любой исход фильтра» и «только наказание».</p>
                <div class="space-y-2">
                  <div class="flex items-center justify-between gap-2">
                    <span class="max-w-[14rem] text-xs leading-snug text-slate-200">Любое срабатывание фильтра</span>
                    <button type="button" :class="boolToggleClass(!!postRulesGroupForm.eventOnTrigger)" class="min-w-[5rem] shrink-0 rounded-lg px-2.5 py-1 text-xs font-medium" @click="postRulesGroupForm.eventOnTrigger = !postRulesGroupForm.eventOnTrigger; postRulesTouchServerDirty()">{{ postRulesGroupForm.eventOnTrigger ? 'ВКЛ' : 'ВЫКЛ' }}</button>
                  </div>
                  <div v-if="postRulesGroupForm.eventOnTrigger" class="flex items-center justify-between gap-2">
                    <span class="text-[11px] text-slate-400">Каждые N таких событий</span>
                    <input v-model.number="postRulesGroupForm.eventTriggerEveryN" type="number" min="1" max="500" class="w-24 rounded-lg border border-white/14 bg-white/[0.06] px-2 py-1 text-xs" @input="postRulesTouchServerDirty()" />
                  </div>
                  <div class="flex items-center justify-between gap-2">
                    <span class="text-xs text-slate-200">На наказание (delete / мут / бан)</span>
                    <button type="button" :class="boolToggleClass(!!postRulesGroupForm.eventOnPunish)" class="min-w-[5rem] rounded-lg px-2.5 py-1 text-xs font-medium" @click="postRulesGroupForm.eventOnPunish = !postRulesGroupForm.eventOnPunish; postRulesTouchServerDirty()">{{ postRulesGroupForm.eventOnPunish ? 'ВКЛ' : 'ВЫКЛ' }}</button>
                  </div>
                  <div v-if="postRulesGroupForm.eventOnPunish" class="flex items-center justify-between gap-2">
                    <span class="text-[11px] text-slate-400">Каждые N наказаний</span>
                    <input v-model.number="postRulesGroupForm.eventPunishEveryN" type="number" min="1" max="500" class="w-24 rounded-lg border border-white/14 bg-white/[0.06] px-2 py-1 text-xs" @input="postRulesTouchServerDirty()" />
                  </div>
                </div>
              </div>

              <div class="glass-panel p-3" :class="postRulesGroupBodyPanelLocked ? 'border-amber-400/15' : ''">
                <p class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Текст правил для группы</p>
                <p
                  v-if="postRulesGroupBodyPanelLocked"
                  class="mb-2 rounded-lg border border-amber-400/25 bg-amber-950/25 px-2.5 py-2 text-[11px] text-amber-100"
                >
                  Редактирование текста, фото и кнопок доступно после «Создать черновик» или «Править» у шаблона выше.
                </p>
                <div class="mb-1.5 flex flex-wrap gap-1.5" :class="postRulesGroupBodyPanelLocked ? 'pointer-events-none opacity-45' : ''">
                  <button type="button" class="post-rules-tool-btn font-semibold" :class="postRulesFormatState.bold ? 'border-cyan-400/50 bg-cyan-500/15' : ''" @mousedown.prevent @click="postRulesExec('bold')">Ж</button>
                  <button type="button" class="post-rules-tool-btn italic" :class="postRulesFormatState.italic ? 'border-cyan-400/50 bg-cyan-500/15' : ''" @mousedown.prevent @click="postRulesExec('italic')">К</button>
                  <button type="button" class="post-rules-tool-btn underline" :class="postRulesFormatState.underline ? 'border-cyan-400/50 bg-cyan-500/15' : ''" @mousedown.prevent @click="postRulesExec('underline')">Ч</button>
                  <button type="button" class="post-rules-tool-btn line-through" :class="postRulesFormatState.strike ? 'border-cyan-400/50 bg-cyan-500/15' : ''" @mousedown.prevent @click="postRulesExec('strikeThrough')">З</button>
                  <button type="button" class="post-rules-tool-btn" @mousedown.prevent @click="postRulesFormatLink">🔗 Ссылка</button>
                  <button type="button" class="post-rules-tool-btn" @mousedown.prevent @click="postRulesClearFormatting">× Сбросить</button>
                </div>
                <div class="mb-1.5 flex flex-wrap gap-1.5" :class="postRulesGroupBodyPanelLocked ? 'pointer-events-none opacity-45' : ''">
                  <button type="button" class="post-rules-tool-btn px-2.5 text-zinc-200" :class="!postRulesCanUndo() ? 'opacity-40' : ''" :disabled="!postRulesCanUndo()" @mousedown.prevent @click="postRulesUndo">↶ Назад</button>
                  <button type="button" class="post-rules-tool-btn px-2.5 text-zinc-200" :class="!postRulesCanRedo() ? 'opacity-40' : ''" :disabled="!postRulesCanRedo()" @mousedown.prevent @click="postRulesRedo">↷ Вперёд</button>
                  <label class="post-rules-tool-btn cursor-pointer">
                    {{ postRulesBusy ? 'Загрузка фото…' : 'Файл' }}
                    <input type="file" accept="image/*" class="hidden" :disabled="postRulesBusy || postRulesGroupBodyPanelLocked" @change="onPostRulesPhotoPicked($event)" />
                  </label>
                  <button type="button" class="post-rules-tool-btn" :disabled="postRulesBusy || !postRulesGroupPreviewUrl || postRulesGroupBodyPanelLocked" @click="removePostRulesPhoto()">🗑</button>
                  <button v-if="postRulesGroupPreviewUrl" type="button" class="h-8 w-8 overflow-hidden rounded-lg border border-white/12 bg-black/40" :disabled="postRulesGroupBodyPanelLocked" @click="openPostRulesImagePreview()">
                    <img :src="postRulesGroupPreviewUrl" alt="" class="h-full w-full object-cover" />
                  </button>
                  <div class="flex items-center gap-1">
                    <button type="button" class="post-rules-tool-btn" :disabled="postRulesGroupBodyPanelLocked" @click="showPostRulesButtonsModal = true">＋ Кнопки</button>
                    <span v-if="postRulesGroupInlineButtonCount > 0" class="rounded-md border border-cyan-400/25 bg-cyan-500/15 px-1.5 py-0.5 text-[10px] font-bold text-cyan-100">{{ postRulesGroupInlineButtonCount }}</span>
                  </div>
                </div>
                <div
                  ref="postRulesBodyRef"
                  :contenteditable="!postRulesGroupBodyPanelLocked"
                  class="post-rules-rich-editor max-h-56 min-h-[8rem] w-full overflow-y-auto rounded-xl border border-white/10 bg-slate-950/90 px-3 py-2 text-sm leading-relaxed text-slate-100 focus-within:border-white/20 focus-within:ring-1 focus-within:ring-white/10"
                  :class="postRulesGroupBodyPanelLocked ? 'pointer-events-none select-none opacity-55' : ''"
                  data-placeholder="Текст правил для группы..."
                  @input="onPostRulesBodyInput"
                  @mouseup="postRulesUpdateFormatState"
                  @keyup="postRulesUpdateFormatState"
                />
              </div>

              <div class="glass-panel p-3">
                <p class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Закрепление и сервис</p>
                <div class="flex items-center justify-between gap-2">
                  <span class="text-xs text-slate-200">Закреплять при отправке</span>
                  <button type="button" :class="boolToggleClass(!!postRulesGroupForm.pinOnSend)" class="min-w-[5rem] rounded-lg px-2.5 py-1 text-xs font-medium" @click="postRulesGroupForm.pinOnSend = !postRulesGroupForm.pinOnSend; postRulesTouchServerDirty()">{{ postRulesGroupForm.pinOnSend ? 'ВКЛ' : 'ВЫКЛ' }}</button>
                </div>
                <div class="mt-2 flex items-center justify-between gap-2">
                  <span class="text-xs text-slate-200">Удалять «закрепил(а) сообщение»</span>
                  <button type="button" :class="boolToggleClass(!!postRulesGroupForm.deletePinNotice)" class="min-w-[5rem] rounded-lg px-2.5 py-1 text-xs font-medium" @click="postRulesGroupForm.deletePinNotice = !postRulesGroupForm.deletePinNotice; postRulesTouchServerDirty()">{{ postRulesGroupForm.deletePinNotice ? 'ВКЛ' : 'ВЫКЛ' }}</button>
                </div>
              </div>
          </div>

          <div class="post-rules-footer flex flex-col gap-1 border-t border-white/10 px-3 py-2 sm:px-4">
            <div class="flex flex-wrap items-center justify-end gap-2">
              <button type="button" class="post-rules-action-btn post-rules-action-btn--cancel" @click="closePostRulesSettingsModal()">Закрыть</button>
              <button
                type="button"
                class="post-rules-action-btn border border-cyan-400/40 bg-cyan-500/25 text-cyan-50 hover:bg-cyan-500/35"
                :disabled="postRulesSendBusy || postRulesSaveBusy"
                @click="sendPostRulesNowGroup()"
              >{{ postRulesSendBusy ? 'Отправка…' : 'Отправить в группу' }}</button>
              <button
                type="button"
                class="post-rules-action-btn post-rules-action-btn--save"
                :disabled="postRulesSaveBusy"
                @click="savePostRulesSettings()"
              >{{ postRulesSaveBusy ? 'Сохранение…' : 'Сохранить' }}</button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="showPostRulesGroupSendModal && showPostRulesSettingsModal"
        class="fixed inset-0 z-[263] flex items-center justify-center bg-black/60 p-4 backdrop-blur-[2px]"
        role="dialog"
        aria-modal="true"
        @click.self="showPostRulesGroupSendModal = false"
      >
        <div class="w-full max-w-lg overflow-hidden rounded-[1.25rem] border border-white/12 bg-zinc-950/92 text-zinc-100 shadow-2xl backdrop-blur-2xl ring-1 ring-white/10" @click.stop>
          <div class="border-b border-white/10 bg-gradient-to-r from-white/[0.06] to-transparent px-4 py-3">
            <h4 class="text-sm font-semibold text-white">Какой шаблон отправить в группу?</h4>
            <p class="mt-1 text-[11px] text-slate-400">Сначала будет сохранено в настройки Telegram, затем сразу отправка в чат. Глаз — полный предпросмотр.</p>
          </div>
          <div class="max-h-[50vh] space-y-1.5 overflow-y-auto px-3 py-3 sm:px-4">
            <div
              v-for="d in postRulesDraftsForChat"
              :key="`pgsnd-${d.id}`"
              class="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1.5"
            >
              <input
                v-model="postRulesGroupSendPickId"
                :value="String(d.id || '')"
                class="h-3.5 w-3.5 border-white/30"
                name="pr-send-pick"
                type="radio"
                :id="`prsp-${d.id}`"
              />
              <label class="min-w-0 flex-1 cursor-pointer text-[12px] text-slate-100" :for="`prsp-${d.id}`">
                <span class="block truncate">{{ postRulesDraftDisplayName(d) }}</span>
                <span class="text-[10px] text-slate-500">{{ postRulesDraftSavedAtLabel(d.savedAt) }}</span>
              </label>
              <button
                type="button"
                class="shrink-0 rounded-lg border border-white/15 bg-white/10 px-2 py-0.5 text-xs text-slate-200 hover:bg-white/16"
                title="Полный просмотр"
                @click="postRulesGroupOpenFullPreview(d)"
              >👁</button>
            </div>
            <p v-if="!postRulesDraftsForChat.length" class="text-center text-sm text-slate-500">Нет черновиков</p>
          </div>
          <div class="flex items-center justify-end gap-2 border-t border-white/10 px-4 py-3">
            <button type="button" class="rounded-lg border border-white/15 bg-white/10 px-3 py-2 text-xs font-semibold text-slate-200" @click="showPostRulesGroupSendModal = false">Отмена</button>
            <button
              type="button"
              class="guard-green-soft rounded-lg px-3 py-2 text-xs font-semibold disabled:opacity-50"
              :disabled="postRulesSendBusy || !postRulesGroupSendPickId"
              @click="postRulesConfirmGroupSendFromModal()"
            >{{ postRulesSendBusy ? 'Отправка…' : 'Отправить' }}</button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="showPostRulesGroupFullPreview && showPostRulesSettingsModal && postRulesGroupFullPreviewRow"
        class="fixed inset-0 z-[265] flex items-center justify-center bg-black/65 p-4 backdrop-blur-[2px]"
        role="dialog"
        aria-modal="true"
        @click.self="postRulesGroupCloseFullPreview()"
      >
        <div class="flex max-h-[min(90vh,36rem)] w-full max-w-lg flex-col overflow-hidden rounded-[1.1rem] border border-white/12 bg-zinc-950/95 text-zinc-100 shadow-2xl" @click.stop>
          <div class="flex items-center justify-between border-b border-white/10 px-3 py-2.5 sm:px-4">
            <h4 class="min-w-0 flex-1 truncate pr-2 text-sm font-semibold">Превью: {{ postRulesDraftDisplayName(postRulesGroupFullPreviewRow) }}</h4>
            <button type="button" class="shrink-0 rounded-lg px-2 py-1 text-xs text-slate-300 hover:bg-white/10" @click="postRulesGroupCloseFullPreview()">✕</button>
          </div>
          <div class="min-h-0 flex-1 overflow-y-auto px-3 py-3 sm:px-4">
            <img
              v-if="String((postRulesGroupFullPreviewRow.payload || {}).photoDataUrl || '').trim().length > 0"
              :src="(postRulesGroupFullPreviewRow.payload || {}).photoDataUrl"
              alt=""
              class="mb-2 max-h-40 w-full rounded-lg border border-white/10 object-contain"
            />
            <div
              v-else-if="(chat?.rule && chat.rule.rules_group_has_photo) && String(postRulesGroupRunActiveId || '') === String(postRulesGroupFullPreviewRow?.id || '')"
              class="mb-2 text-[10px] text-slate-500"
            >Фото подставится с сервера (в превью черновика нет data URL — в чате будет как на сервере, если картинка уже в правилах).</div>
            <div
              class="post-rules-preview-html rounded-lg border border-white/10 bg-black/35 px-3 py-2 text-sm leading-relaxed text-slate-100"
              v-html="String((postRulesGroupFullPreviewRow.payload || {}).text || '').length ? (postRulesGroupFullPreviewRow.payload || {}).text : '—'"
            />
            <div v-if="postRulesGroupButtonLinesFromDraft(postRulesGroupFullPreviewRow).length" class="mt-3">
              <p class="mb-1 text-[10px] font-semibold uppercase text-zinc-500">Кнопки</p>
              <div
                v-for="(row, i) in postRulesGroupButtonLinesFromDraft(postRulesGroupFullPreviewRow)"
                :key="`prbprev-${i}`"
                class="mb-1.5 flex flex-wrap gap-1.5"
              >
                <span
                  v-for="(b, j) in row"
                  :key="`prbpr-${i}-${j}`"
                  class="inline-flex rounded border border-cyan-400/25 bg-cyan-500/10 px-2 py-0.5 text-[11px] text-cyan-100"
                >{{ b }}</span>
              </div>
            </div>
          </div>
          <div class="border-t border-white/10 px-3 py-2.5 sm:px-4">
            <button type="button" class="w-full rounded-lg border border-white/15 bg-white/10 py-1.5 text-xs font-semibold" @click="postRulesGroupCloseFullPreview()">Закрыть</button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="showPostRulesButtonsModal && showPostRulesSettingsModal"
        class="fixed inset-0 z-[262] flex items-center justify-center bg-black/60 p-4 backdrop-blur-[2px]"
        role="dialog"
        aria-modal="true"
        @click.self="showPostRulesButtonsModal = false"
      >
        <div class="w-full max-w-2xl overflow-hidden rounded-[1.25rem] border border-white/15 bg-zinc-950/90 text-zinc-100 shadow-2xl backdrop-blur-xl ring-1 ring-white/10" @click.stop>
          <div class="flex items-center justify-between border-b border-white/10 bg-gradient-to-r from-white/[0.06] to-transparent px-4 py-2.5">
            <h4 class="text-sm font-semibold text-white">Кнопки под постом</h4>
            <button type="button" class="rounded-lg px-2 py-1 text-xs text-slate-300 hover:bg-white/10" @click="showPostRulesButtonsModal = false">✕</button>
          </div>
          <div class="max-h-[70vh] overflow-y-auto px-4 py-3">
            <div v-for="(row, ri) in postRulesRowsRef().value" :key="`prm-row-${ri}`" class="mb-3 rounded-xl border border-white/10 bg-white/[0.04] p-3">
              <div class="mb-2 flex items-center justify-between">
                <p class="text-xs font-semibold text-slate-200">Ряд {{ ri + 1 }}</p>
              </div>
              <div
                v-for="(btn, bi) in row"
                :key="`prm-btn-${ri}-${bi}`"
                class="mb-2 grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto_auto]"
              >
                <input v-model="btn.text" type="text" class="rounded-lg border border-white/14 bg-white/[0.06] px-2.5 py-1.5 text-xs" placeholder="Текст кнопки" />
                <input v-model="btn.url" type="text" class="rounded-lg border border-white/14 bg-white/[0.06] px-2.5 py-1.5 text-xs" placeholder="https://..." />
                <button type="button" class="rounded-lg border border-rose-400/35 bg-rose-500/20 px-2.5 py-1.5 text-xs text-rose-100" @click="postRulesRemoveButtonCurrent(ri, bi)">Удалить</button>
                <button type="button" class="rounded-lg border border-emerald-400/35 bg-emerald-500/20 px-2.5 py-1.5 text-xs font-semibold text-emerald-100" :disabled="postRulesSaveBusy" @click="postRulesSaveButtonsFromModal()">Сохранить</button>
              </div>
              <button type="button" class="text-xs font-semibold text-violet-300" @click="postRulesAddButtonCurrent(ri)">+ Кнопка в этот ряд</button>
            </div>
            <button type="button" class="w-full rounded-lg border border-violet-500/40 py-2 text-sm font-semibold text-violet-200" @click="postRulesAddRowCurrent">+ Ряд</button>
          </div>
          <div class="flex items-center justify-end gap-2 border-t border-white/10 px-4 py-3">
            <button type="button" class="rounded-lg border border-white/15 bg-white/10 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-white/15" @click="showPostRulesButtonsModal = false">Закрыть</button>
            <button type="button" class="guard-green-soft rounded-lg px-3 py-2 text-xs font-semibold text-slate-900 disabled:opacity-50" :disabled="postRulesSaveBusy" @click="postRulesSaveButtonsFromModal()">{{ postRulesSaveBusy ? 'Сохранение…' : 'Сохранить кнопки' }}</button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="postRulesLinkModalOpen && showPostRulesSettingsModal"
        class="fixed inset-0 z-[262] flex items-center justify-center bg-black/60 p-4 backdrop-blur-[2px]"
        role="dialog"
        aria-modal="true"
        @click.self="postRulesLinkModalOpen = false"
      >
        <div class="w-full max-w-md overflow-hidden rounded-[1.1rem] border border-white/15 bg-zinc-950/90 text-zinc-100 shadow-2xl backdrop-blur-xl ring-1 ring-white/10" @click.stop>
          <div class="flex items-center justify-between border-b border-white/10 px-4 py-2.5">
            <h4 class="text-sm font-semibold text-white">Ссылка</h4>
            <button type="button" class="rounded-lg px-2 py-1 text-xs text-slate-300 hover:bg-white/10" @click="postRulesLinkModalOpen = false">✕</button>
          </div>
          <div class="space-y-2 px-4 py-3">
            <input v-model.trim="postRulesLinkUrl" type="text" class="w-full rounded-lg border border-white/15 bg-white/[0.06] px-3 py-2 text-sm" placeholder="https://..." />
          </div>
          <div class="flex items-center justify-end gap-2 border-t border-white/10 px-4 py-3">
            <button type="button" class="rounded-lg border border-white/15 px-3 py-2 text-sm text-slate-200 hover:bg-white/10" @click="postRulesLinkModalOpen = false">Отмена</button>
            <button type="button" class="guard-green-soft rounded-lg px-3 py-2 text-sm font-semibold" @click="postRulesApplyLinkModal()">Применить</button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="welcomeInfoModal && showWelcomeSettingsModal"
        class="fixed inset-0 z-[261] flex items-center justify-center bg-black/60 p-4 backdrop-blur-[2px]"
        role="dialog"
        aria-modal="true"
        @click.self="welcomeInfoModal = ''"
      >
        <div
          class="w-full max-w-md overflow-hidden rounded-[1.25rem] border border-white/15 bg-zinc-950/90 text-zinc-100 shadow-2xl backdrop-blur-xl ring-1 ring-white/10"
          @click.stop
        >
          <div class="flex items-center justify-between border-b border-white/10 bg-gradient-to-r from-white/[0.06] to-transparent px-4 py-2.5">
            <h4 class="pr-2 text-sm font-semibold text-white">
              <template v-if="welcomeInfoModal === 'main'">Автоприветствие в чате</template>
              <template v-else-if="welcomeInfoModal === 'text'">Редактор и плейсхолдеры</template>
              <template v-else-if="welcomeInfoModal === 'rate'">Кому пишем и с какой скоростью</template>
              <template v-else-if="welcomeInfoModal === 'raid'">Молчать, когда врывается волна</template>
            </h4>
            <button type="button" class="shrink-0 rounded-lg px-2 py-1 text-xs text-slate-400 hover:bg-white/10" @click="welcomeInfoModal = ''" aria-label="Закрыть">✕</button>
          </div>
          <div class="max-h-[min(60vh,22rem)] overflow-y-auto px-4 py-3">
            <div
              v-if="welcomeInfoModal === 'main'"
              class="rounded-2xl border border-cyan-400/20 bg-cyan-500/[0.08] p-3 text-[11px] leading-relaxed text-zinc-200 backdrop-blur-md"
            >
              <p>Новичок <strong>впервые</strong> садится в <strong>эту</strong> группу — и <strong>Guard</strong> может тут же написать ему <strong>твоё</strong> личное приветствие. Ты задаёшь <strong>текст, картинку, кнопки</strong> и правила, <strong>как часто</strong> писать и <strong>когда лучше замолчать</strong>, если входов <strong>слишком много</strong> разом.</p>
              <p class="mt-1.5">Всё, что дальше в этом окне, — <strong>только про эту</strong> группу. <strong>Guard</strong> не путает это с настройками <strong>других</strong> твоих чатов.</p>
            </div>
            <div
              v-else-if="welcomeInfoModal === 'text'"
              class="rounded-xl border border-violet-400/20 bg-violet-500/[0.08] p-2.5 text-[11px] leading-relaxed text-zinc-200"
            >
              <p>
                <strong>Как в рассылке</strong> из кабинета: <strong>выдели</strong> кусок в поле, потом жми жирный, курсив, цитату, ссылку. Без выделения <strong>Guard</strong> не к чему «навесить» оформление. Исключение — <strong>плейсхолдеры</strong> внизу: вставляются в позицию курсора, как в рассылке, выделение не нужно.
              </p>
              <p class="mt-1.5">
                Наложил лишнего? Над полем <strong>↶ Назад / ↷ Вперёд</strong> — тот же откат, что в рассылке. <strong>Цитата</strong> в чате уйдёт как в Telegram, в чёрновике видна с боковой полоской.
              </p>
              <p class="mt-1.5">
                Сообщение уходит с той разметкой, которую собрал. <strong>Guard</strong> к моменту отправки подставит
                <strong>{first_name}</strong>, <strong>{full_name}</strong>, <strong>{username}</strong>, <strong>{chat_title}</strong> — для того, кто только вошёл, в <strong>этом</strong> чате.
              </p>
            </div>
            <div
              v-else-if="welcomeInfoModal === 'rate'"
              class="rounded-xl border border-cyan-400/20 bg-cyan-500/[0.08] p-2.5 text-[11px] leading-relaxed text-zinc-200"
            >
              <p>
                <strong>Каждому N-му</strong> — кого из новичков здороваем. <strong>N = 1</strong> — каждому, кто только что зашёл. <strong>N = 2</strong> — 2-му, 4-му, 6-му… <strong>N = 3</strong> — 3-му, 6-му, 9-му… Удобно, если не хочешь слать привет <strong>каждому</strong> вступившему, а, например, <strong>каждого третьего</strong>.
              </p>
              <p class="mt-1.5">
                <strong>Лимит в минуту</strong> — мягкий «потолок» на скорость: даже если волна входов жирная, <strong>Guard</strong> не сыплет приветствиями больше выбранного числа <strong>в эту</strong> минуту. <strong>0</strong> = без такой страховки, остальные правила ниже всё равно работают.
              </p>
            </div>
            <div
              v-else-if="welcomeInfoModal === 'raid'"
              class="rounded-xl border border-amber-400/20 bg-amber-500/[0.08] p-2.5 text-[11px] leading-relaxed text-zinc-200"
            >
              <p>
                Если за короткое время в чат <strong>вломилось</strong> слишком много людей — волна ботов, рейд, слишком плотный поток, — <strong>Guard</strong> может <strong>на время замолкнуть</strong> с приветствиями, чтобы <strong>не засыпать</strong> чат лишними пушами, пока волна <strong>не остынет</strong>.
              </p>
              <p class="mt-1.5">
                <strong>Порог входов</strong> + <strong>окно (мин)</strong> — в двух словах: «если столько-то <strong>новых</strong> вступивших <strong>за</strong> столько-то минут, считаем, что волна». Ниже порога в пределах окна — <strong>снова</strong> обычные приветы, как настроил.
              </p>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="showWelcomeButtonsModal && showWelcomeSettingsModal"
        class="fixed inset-0 z-[262] flex items-center justify-center bg-black/60 p-4 backdrop-blur-[2px]"
        role="dialog"
        aria-modal="true"
        @click.self="showWelcomeButtonsModal = false"
      >
        <div class="w-full max-w-2xl overflow-hidden rounded-[1.25rem] border border-white/15 bg-zinc-950/90 text-zinc-100 shadow-2xl backdrop-blur-xl ring-1 ring-white/10" @click.stop>
          <div class="flex items-center justify-between border-b border-white/10 bg-gradient-to-r from-white/[0.06] to-transparent px-4 py-2.5">
            <h4 class="text-sm font-semibold text-white">Кнопки под постом</h4>
            <button type="button" class="rounded-lg px-2 py-1 text-xs text-slate-300 hover:bg-white/10" @click="showWelcomeButtonsModal = false">✕</button>
          </div>
          <div class="max-h-[70vh] overflow-y-auto px-4 py-3">
            <div v-for="(row, ri) in welcomeButtonRows" :key="`wkb-${ri}`" class="mb-3 rounded-xl border border-white/10 bg-white/[0.04] p-3">
              <div class="mb-2 flex items-center justify-between gap-2">
                <p class="text-xs font-semibold text-slate-200">Ряд {{ ri + 1 }}</p>
                <button type="button" class="rounded-lg border border-rose-400/25 bg-rose-500/15 px-2 py-0.5 text-[10px] text-rose-100 hover:bg-rose-500/25" @click="welcomeRemoveRow(ri)">Убрать ряд</button>
              </div>
              <div
                v-for="(btn, bi) in row"
                :key="`wkbtn-${ri}-${bi}`"
                class="mb-2 grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto_auto]"
              >
                <input v-model="btn.text" type="text" class="rounded-lg border border-white/14 bg-white/[0.06] px-2.5 py-1.5 text-xs sm:col-span-2" placeholder="Текст кнопки" />
                <input v-model="btn.url" type="text" class="rounded-lg border border-white/14 bg-white/[0.06] px-2.5 py-1.5 text-xs" placeholder="https://..." />
                <input v-model="btn.web_app_url" type="text" class="rounded-lg border border-white/14 bg-white/[0.06] px-2.5 py-1.5 text-xs" placeholder="Web App URL" />
                <input v-model="btn.callback_data" type="text" class="rounded-lg border border-white/14 bg-white/[0.06] px-2.5 py-1.5 text-xs sm:col-span-2" placeholder="callback_data" />
                <button type="button" class="rounded-lg border border-rose-400/35 bg-rose-500/20 px-2.5 py-1.5 text-xs text-rose-100" @click="welcomeRemoveButton(ri, bi)">Удалить</button>
                <button type="button" class="rounded-lg border border-emerald-400/35 bg-emerald-500/20 px-2.5 py-1.5 text-xs font-semibold text-emerald-100" :disabled="welcomeBusy" @click="welcomeSaveButtonsFromModal()">Сохранить</button>
              </div>
              <button type="button" class="text-xs font-semibold text-violet-300" @click="welcomeAddButton(ri)">+ Кнопка в этот ряд</button>
            </div>
            <button type="button" class="w-full rounded-lg border border-violet-500/40 py-2 text-sm font-semibold text-violet-200" @click="welcomeAddRow">+ Ряд</button>
          </div>
          <div class="flex items-center justify-end gap-2 border-t border-white/10 px-4 py-3">
            <button type="button" class="rounded-lg border border-white/15 bg-white/10 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-white/15" @click="showWelcomeButtonsModal = false">Закрыть</button>
            <button type="button" class="guard-green-soft rounded-lg px-3 py-2 text-xs font-semibold text-slate-900 disabled:opacity-50" :disabled="welcomeBusy" @click="welcomeSaveButtonsFromModal()">{{ welcomeBusy ? 'Сохранение…' : 'Сохранить кнопки' }}</button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="welcomeLinkModalOpen"
        class="fixed inset-0 z-[263] flex items-start justify-center bg-black/60 p-4 md:items-center"
        role="dialog"
        aria-modal="true"
        @click.self="welcomeLinkModalOpen = false"
      >
        <div class="w-full max-w-md rounded-2xl border border-violet-400/50 bg-slate-900 p-4 shadow-2xl" @click.stop>
          <div class="mb-2 flex items-center justify-between">
            <p class="text-base font-semibold text-white">Добавить ссылку</p>
            <button type="button" class="rounded-lg px-2 py-1 text-xs text-slate-300 hover:bg-white/10" @click="welcomeLinkModalOpen = false">✕</button>
          </div>
          <input
            v-model="welcomeLinkUrl"
            type="text"
            placeholder="https://..."
            class="w-full rounded-xl border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white"
          />
          <div class="mt-3 flex gap-2">
            <button type="button" class="rounded-xl bg-violet-600 px-4 py-2 text-sm font-semibold text-white" @click="welcomeApplyLinkModal">Применить</button>
            <button type="button" class="rounded-lg border border-white/15 px-3 py-2 text-sm text-slate-200 hover:bg-white/10" @click="welcomeLinkModalOpen = false">Отмена</button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="showLinksFilterModal && chat?.rule"
        class="fixed inset-0 z-[255] flex items-center justify-center bg-black/45 p-4 backdrop-blur-md"
        role="dialog"
        aria-modal="true"
        @click.self="showLinksFilterModal = false"
      >
        <div
          class="links-glass-panel flex max-h-[min(88vh,44rem)] w-full max-w-xl flex-col overflow-hidden rounded-[1.35rem] border border-white/18 bg-zinc-950/75 text-zinc-100 shadow-[0_32px_96px_-24px_rgba(0,0,0,0.78),inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-2xl backdrop-saturate-150 ring-1 ring-white/10"
          @click.stop
        >
          <div
            class="flex shrink-0 items-center justify-between gap-2 border-b border-white/10 bg-gradient-to-r from-white/[0.06] to-transparent px-4 py-3.5"
          >
            <div class="flex min-w-0 items-center gap-2">
              <span
                class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-400/25 to-teal-500/15 text-lg ring-1 ring-emerald-400/20"
                aria-hidden="true"
              >🔗</span>
              <h3 class="truncate text-sm font-semibold tracking-tight text-white">Ссылки — политика Guard</h3>
            </div>
            <button
              type="button"
              class="rounded-xl border border-white/10 bg-white/[0.06] px-2.5 py-1.5 text-xs text-zinc-400 backdrop-blur-sm hover:border-white/20 hover:bg-white/10 hover:text-white"
              @click="showLinksFilterModal = false"
            >
              ✕
            </button>
          </div>
          <div
            class="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-4 py-4 [-webkit-overflow-scrolling:touch]"
          >
            <div>
              <div class="mb-2 flex items-center justify-between gap-2">
                <p class="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Режим фильтра</p>
                <button
                  type="button"
                  class="link-glass-info-btn"
                  :class="openLinkModeHint === '_legend' ? 'link-glass-info-btn--active' : ''"
                  aria-label="Подсказка"
                  @click="openLinkModeHint = openLinkModeHint === '_legend' ? null : '_legend'"
                >
                  ⓘ
                </button>
              </div>
              <div
                v-show="openLinkModeHint === '_legend'"
                class="link-modal-hint link-liquid-hint mb-2 rounded-2xl border border-white/12 bg-white/[0.06] p-3 text-[11px] leading-relaxed text-zinc-300 backdrop-blur-md"
                v-html="linkModalLegendHtml"
              />
              <div class="space-y-2.5">
                <template v-for="opt in linkModeOptions" :key="`lm-${opt.value}`">
                  <div class="flex gap-2">
                    <button
                      type="button"
                      :class="linkModeButtonClass(chat.rule.filter_links_mode, opt.value)"
                      class="min-w-0 flex-1"
                      @click="updateRule({ filter_links_mode: opt.value })"
                    >
                      {{ opt.label }}
                    </button>
                    <button
                      type="button"
                      class="link-glass-info-btn shrink-0 !h-9 !min-w-9 !rounded-2xl !px-2.5 !text-xs"
                      :class="openLinkModeHint === opt.value ? 'link-glass-info-btn--active' : ''"
                      :aria-expanded="openLinkModeHint === opt.value"
                      :aria-label="`Подсказка: ${opt.label}`"
                      @click="openLinkModeHint = openLinkModeHint === opt.value ? null : opt.value"
                    >
                      ⓘ
                    </button>
                  </div>
                  <div
                    v-show="openLinkModeHint === opt.value"
                    class="link-modal-hint link-liquid-hint rounded-2xl border border-white/10 bg-white/[0.05] p-3 text-[11px] leading-relaxed text-zinc-300 backdrop-blur-md"
                    v-html="opt.guardHtml"
                  />
                </template>
              </div>
            </div>
            <div
              class="rounded-2xl border border-teal-400/22 bg-gradient-to-br from-teal-500/[0.1] via-teal-950/20 to-emerald-950/25 p-3.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.07)] backdrop-blur-md ring-1 ring-inset ring-teal-300/10"
            >
              <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div class="min-w-0 flex-1">
                  <div class="mb-1.5 flex items-center justify-between gap-2">
                    <p class="text-xs font-semibold text-teal-100">Глобальная база URL Guard</p>
                    <button
                      type="button"
                      class="link-glass-info-btn"
                      :class="openLinkModeHint === '_global' ? 'link-glass-info-btn--active' : ''"
                      aria-label="Что такое глобальная база URL"
                      @click="openLinkModeHint = openLinkModeHint === '_global' ? null : '_global'"
                    >
                      ⓘ
                    </button>
                  </div>
                  <p class="text-[11px] leading-relaxed text-zinc-400">
                    Общий список «плохих» кусочков адресов от <strong class="text-zinc-200">админа Guard</strong> —
                    нажми <strong class="text-zinc-200">ⓘ</strong>, объясню по-человечески.
                  </p>
                  <div
                    v-show="openLinkModeHint === '_global'"
                    class="link-modal-hint link-liquid-hint mt-2 rounded-xl border border-teal-400/15 bg-black/30 p-3 text-[11px] leading-relaxed text-zinc-300 backdrop-blur-md"
                    v-html="linkModalGlobalBadUrlsHtml"
                  />
                </div>
                <button
                  type="button"
                  class="shrink-0 self-start rounded-xl border px-3 py-2 text-[11px] font-semibold backdrop-blur-sm transition-colors sm:py-1.5"
                  :class="
                    chat.rule.use_global_bad_urls
                      ? 'border-teal-400/40 bg-teal-500/90 text-white shadow-[0_0_20px_-6px_rgba(45,212,191,0.5)]'
                      : 'border-white/15 bg-white/[0.06] text-zinc-400 hover:border-white/25 hover:text-zinc-200'
                  "
                  @click="updateRule({ use_global_bad_urls: !chat.rule.use_global_bad_urls })"
                >
                  {{ chat.rule.use_global_bad_urls ? 'ВКЛ' : 'ВЫКЛ' }}
                </button>
              </div>
            </div>
            <div>
              <div class="mb-2 flex items-center justify-between gap-2">
                <p class="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Где проверять</p>
                <button
                  type="button"
                  class="link-glass-info-btn"
                  :class="openLinkModeHint === '_scope' ? 'link-glass-info-btn--active' : ''"
                  aria-label="Подсказка область"
                  @click="openLinkModeHint = openLinkModeHint === '_scope' ? null : '_scope'"
                >
                  ⓘ
                </button>
              </div>
              <div
                v-show="openLinkModeHint === '_scope'"
                class="link-modal-hint link-liquid-hint mb-2 rounded-2xl border border-violet-400/20 bg-violet-500/[0.09] p-3 text-[11px] leading-relaxed text-zinc-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-md"
                v-html="linkModalScopeHtml"
              />
              <div class="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  :class="linkScopeButtonClass(chat.rule.filter_links_scope, 'all')"
                  class="min-w-0"
                  @click="updateRule({ filter_links_scope: 'all' })"
                >
                  Комментарии + чат
                </button>
                <button
                  type="button"
                  :class="linkScopeButtonClass(chat.rule.filter_links_scope, 'channel_comments_only')"
                  class="min-w-0"
                  @click="updateRule({ filter_links_scope: 'channel_comments_only' })"
                >
                  Только комментарии к постам
                </button>
              </div>
            </div>
            <div
              class="rounded-2xl border border-rose-400/22 bg-gradient-to-br from-rose-600/[0.1] via-rose-950/25 to-red-950/35 p-3.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-md ring-1 ring-inset ring-rose-300/10"
            >
              <div class="mb-2 flex items-center justify-between gap-2">
                <p class="text-[11px] font-semibold uppercase tracking-wide text-rose-100/95">
                  Чёрный список ссылок
                  <span v-if="premiumFeatureLocked" class="font-normal text-amber-300">· Premium</span>
                </p>
                <button
                  type="button"
                  class="link-glass-info-btn"
                  :class="openLinkModeHint === '_bl' ? 'link-glass-info-btn--active' : ''"
                  aria-label="Подсказка чёрный список"
                  @click="openLinkModeHint = openLinkModeHint === '_bl' ? null : '_bl'"
                >
                  ⓘ
                </button>
              </div>
              <div
                v-show="openLinkModeHint === '_bl'"
                class="link-modal-hint link-liquid-hint mb-2 rounded-xl border border-rose-400/18 bg-rose-950/30 p-3 text-[11px] leading-relaxed text-zinc-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] backdrop-blur-md"
                v-html="linkModalBlacklistHtml"
              />
              <div class="mb-2 flex gap-2">
                <input
                  v-model="newLinkBlacklistPattern"
                  type="text"
                  placeholder="spam.com или t.me/spam_channel"
                  class="min-w-0 flex-1 rounded-xl border border-white/14 bg-white/[0.06] px-2.5 py-2 text-xs text-white placeholder:text-zinc-500 backdrop-blur-sm focus:border-rose-400/40 focus:outline-none"
                  :disabled="linkBlacklistLoading"
                  @keydown.enter.prevent="addLinkBlacklistPattern()"
                />
                <button
                  type="button"
                  class="shrink-0 rounded-xl bg-gradient-to-br from-rose-500 to-red-600 px-3 py-2 text-xs font-semibold text-white shadow-[0_8px_24px_-10px_rgba(244,63,94,0.55)] hover:from-rose-400 hover:to-red-500 disabled:opacity-50"
                  :disabled="linkBlacklistLoading || !(newLinkBlacklistPattern || '').trim()"
                  @click="addLinkBlacklistPattern()"
                >
                  +
                </button>
              </div>
              <ul class="max-h-32 space-y-1 overflow-y-auto pr-1">
                <li
                  v-for="b in chat.link_blacklist || []"
                  :key="`bl-${b}`"
                  class="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.04] px-2 py-1.5 font-mono text-[11px] backdrop-blur-sm"
                >
                  <span>{{ b }}</span>
                  <button
                    type="button"
                    class="text-rose-300 hover:text-rose-200"
                    :disabled="linkBlacklistLoading"
                    @click="removeLinkBlacklistPattern(b)"
                  >
                    убрать
                  </button>
                </li>
              </ul>
              <p class="mt-1.5 text-[10px] text-zinc-500">
                {{ (chat.link_blacklist || []).length }}/{{ chat.link_blacklist_max ?? 0 }}
              </p>
            </div>
            <div
              class="rounded-2xl border border-white/12 bg-gradient-to-br from-white/[0.07] to-black/20 p-3 text-[11px] leading-relaxed text-zinc-400 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-md ring-1 ring-inset ring-white/[0.04]"
            >
              <strong class="text-zinc-200">Не путать с делегированием:</strong> делегат в «Админы и доступы» — доступ к
              <em>панели</em> и рассылкам. Списки здесь — только про <em>ссылки в этом чате</em> для Guard.
            </div>
            <div>
              <div class="mb-2 flex items-center justify-between gap-2">
                <p class="mb-0 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                  Доверенные ссылки
                  <span class="font-normal normal-case text-zinc-500">
                    ({{ (chat.whitelist_domains || []).length }}/{{ chat.whitelist_max_domains ?? 5 }})
                  </span>
                </p>
                <button
                  type="button"
                  class="link-glass-info-btn"
                  :class="openLinkModeHint === '_wl' ? 'link-glass-info-btn--active' : ''"
                  aria-label="Подсказка доверенные"
                  @click="openLinkModeHint = openLinkModeHint === '_wl' ? null : '_wl'"
                >
                  ⓘ
                </button>
              </div>
              <div
                v-show="openLinkModeHint === '_wl'"
                class="link-modal-hint link-liquid-hint mb-2 rounded-2xl border border-sky-400/22 bg-sky-500/[0.1] p-3 text-[11px] leading-relaxed text-zinc-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.07)] backdrop-blur-md"
                v-html="linkModalWhitelistHtml"
              />
              <div class="mb-2 flex gap-2">
                <input
                  v-model="newWhitelistDomain"
                  type="text"
                  placeholder="Например google.com, youtube.com/channel или t.me/your_channel"
                  class="min-w-0 flex-1 rounded-xl border border-white/14 bg-white/[0.06] px-2.5 py-2 text-xs text-white placeholder:text-zinc-500 backdrop-blur-sm focus:border-sky-400/40 focus:outline-none"
                  :disabled="whitelistLoading"
                  @keydown.enter.prevent="addWhitelistDomain()"
                />
                <button
                  type="button"
                  class="shrink-0 rounded-xl bg-gradient-to-br from-sky-500 to-indigo-600 px-3 py-2 text-xs font-semibold text-white shadow-[0_8px_24px_-10px_rgba(56,189,248,0.45)] hover:from-sky-400 hover:to-indigo-500 disabled:opacity-50"
                  :disabled="whitelistLoading || !(newWhitelistDomain || '').trim()"
                  @click="addWhitelistDomain()"
                >
                  +
                </button>
              </div>
              <ul class="max-h-40 space-y-1 overflow-y-auto pr-1">
                <li
                  v-for="d in (chat.whitelist_domains || [])"
                  :key="`wl-d-${d}`"
                  class="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.04] px-2 py-1.5 font-mono text-[11px] backdrop-blur-sm"
                >
                  <span>{{ d }}</span>
                  <button
                    type="button"
                    class="text-rose-300 hover:text-rose-200"
                    :disabled="whitelistLoading"
                    @click="removeWhitelistDomain(d)"
                  >
                    убрать
                  </button>
                </li>
              </ul>
            </div>
            <div>
              <div class="mb-2 flex items-center justify-between gap-2">
                <p class="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                  Доверенные пользователи
                  <span class="font-normal normal-case text-zinc-500">
                    ({{ (chat.whitelist_users || []).length }}/{{ chat.whitelist_max_users ?? 50 }})
                  </span>
                </p>
                <button
                  type="button"
                  class="link-glass-info-btn"
                  :class="openLinkModeHint === '_wl_users' ? 'link-glass-info-btn--active' : ''"
                  aria-label="Подсказка: доверенные пользователи"
                  @click="openLinkModeHint = openLinkModeHint === '_wl_users' ? null : '_wl_users'"
                >
                  ⓘ
                </button>
              </div>
              <div
                v-show="openLinkModeHint === '_wl_users'"
                class="link-modal-hint link-liquid-hint mb-2 rounded-2xl border border-violet-400/20 bg-violet-500/[0.08] p-3 text-[11px] leading-relaxed text-zinc-300 backdrop-blur-md"
                v-html="linkModalWhitelistUsersHtml"
              />
              <div class="mb-2 flex gap-2">
                <input
                  v-model="newWhitelistUserId"
                  type="text"
                  placeholder="Например @manager или 123456789"
                  class="min-w-0 flex-1 rounded-xl border border-white/14 bg-white/[0.06] px-2.5 py-2 text-xs text-white placeholder:text-zinc-500 backdrop-blur-sm focus:border-violet-400/40 focus:outline-none"
                  :disabled="whitelistLoading"
                  @keydown.enter.prevent="addWhitelistUser()"
                />
                <button
                  type="button"
                  class="shrink-0 rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-600 px-3 py-2 text-xs font-semibold text-white shadow-[0_8px_24px_-10px_rgba(167,139,250,0.45)] hover:from-violet-400 hover:to-fuchsia-500 disabled:opacity-50"
                  :disabled="whitelistLoading || !(newWhitelistUserId || '').trim()"
                  @click="addWhitelistUser()"
                >
                  +
                </button>
              </div>
              <ul class="max-h-36 space-y-1 overflow-y-auto pr-1">
                <li
                  v-for="u in (chat.whitelist_users || [])"
                  :key="`wl-u-${u.user_id}`"
                  class="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.04] px-2 py-1.5 text-[11px] backdrop-blur-sm"
                >
                  <span>
                    <span class="font-mono text-zinc-200">{{ u.user_id }}</span>
                    <span v-if="u.username || u.first_name" class="text-zinc-500">
                      · @{{ u.username || '—' }} {{ u.first_name || '' }}
                    </span>
                  </span>
                  <button
                    type="button"
                    class="text-rose-300 hover:text-rose-200"
                    :disabled="whitelistLoading"
                    @click="removeWhitelistUser(u.user_id)"
                  >
                    убрать
                  </button>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="showChannelPostsFilterModal && chat?.rule"
        class="fixed inset-0 z-[255] flex items-center justify-center bg-black/45 p-4 backdrop-blur-md"
        role="dialog"
        aria-modal="true"
        @click.self="showChannelPostsFilterModal = false"
      >
        <div
          class="links-glass-panel flex max-h-[min(86vh,42rem)] w-full max-w-xl flex-col overflow-hidden rounded-[1.35rem] border border-white/18 bg-zinc-950/75 text-zinc-100 shadow-[0_32px_96px_-24px_rgba(0,0,0,0.78),inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-2xl backdrop-saturate-150 ring-1 ring-white/10"
          @click.stop
        >
          <div class="flex shrink-0 items-center justify-between gap-2 border-b border-white/10 bg-gradient-to-r from-white/[0.06] to-transparent px-4 py-3.5">
            <div class="flex min-w-0 items-center gap-2">
              <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-fuchsia-400/25 to-indigo-500/15 text-lg ring-1 ring-fuchsia-400/20">📣</span>
              <h3 class="truncate text-sm font-semibold tracking-tight text-white">Сообщения от каналов</h3>
            </div>
            <button
              type="button"
              class="rounded-xl border border-white/10 bg-white/[0.06] px-2.5 py-1.5 text-xs text-zinc-400 backdrop-blur-sm hover:border-white/20 hover:bg-white/10 hover:text-white"
              @click="showChannelPostsFilterModal = false"
            >
              ✕
            </button>
          </div>
          <div class="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain px-4 py-4 [-webkit-overflow-scrolling:touch]">
            <p class="text-[11px] leading-relaxed text-zinc-300">
              Ловит сообщения, отправленные <strong>от имени канала/чата</strong> в группе. Для своих каналов добавь @username в доверенные ниже.
            </p>
            <div class="flex items-center justify-between gap-2 rounded-xl border border-white/12 bg-white/[0.05] px-3 py-2">
              <span class="text-xs text-slate-200">Фильтр сообщений от каналов</span>
              <button
                type="button"
                :class="boolToggleClass(!!chat.rule.filter_channel_posts_enabled)"
                class="min-w-[5rem] rounded-lg px-2.5 py-1 text-xs font-medium"
                @click="updateRule({ filter_channel_posts_enabled: !chat.rule.filter_channel_posts_enabled })"
              >
                {{ chat.rule.filter_channel_posts_enabled ? 'ВКЛ' : 'ВЫКЛ' }}
              </button>
            </div>
            <div v-if="chat.rule.filter_channel_posts_enabled" class="rounded-xl border border-white/12 bg-white/[0.05] p-3">
              <p class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Реакция Guard</p>
              <div class="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  class="rounded-lg px-2.5 py-2 text-xs font-semibold"
                  :class="String(chat.rule.filter_channel_posts_action || 'delete') === 'delete' ? 'guard-green-soft text-slate-900' : protToggleOff"
                  @click="updateRule({ filter_channel_posts_action: 'delete' })"
                >
                  Удалять
                </button>
                <button
                  type="button"
                  class="rounded-lg px-2.5 py-2 text-xs font-semibold"
                  :class="String(chat.rule.filter_channel_posts_action || 'delete') === 'ban' ? 'bg-gradient-to-r from-rose-500 to-red-600 text-white shadow-[0_8px_20px_-10px_rgba(239,68,68,0.75)]' : protToggleOff"
                  @click="updateRule({ filter_channel_posts_action: 'ban' })"
                >
                  Удалять + банить канал
                </button>
              </div>
            </div>
            <div class="rounded-xl border border-white/12 bg-white/[0.05] p-3">
              <p class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                Доверенные каналы (@username)
                <span class="font-normal normal-case text-zinc-500">
                  ({{ (chat.whitelist_sender_chats || []).length }})
                </span>
              </p>
              <div class="mb-2 flex gap-2">
                <input
                  v-model="newWhitelistSenderChat"
                  type="text"
                  placeholder="Например @my_news_channel"
                  class="min-w-0 flex-1 rounded-xl border border-white/14 bg-white/[0.06] px-2.5 py-2 text-xs text-white placeholder:text-zinc-500 backdrop-blur-sm focus:border-fuchsia-400/40 focus:outline-none"
                  :disabled="whitelistLoading"
                  @keydown.enter.prevent="addWhitelistSenderChat()"
                />
                <button
                  type="button"
                  class="shrink-0 rounded-xl bg-gradient-to-br from-fuchsia-500 to-indigo-600 px-3 py-2 text-xs font-semibold text-white shadow-[0_8px_24px_-10px_rgba(217,70,239,0.45)] hover:from-fuchsia-400 hover:to-indigo-500 disabled:opacity-50"
                  :disabled="whitelistLoading || !(newWhitelistSenderChat || '').trim()"
                  @click="addWhitelistSenderChat()"
                >
                  +
                </button>
              </div>
              <ul class="max-h-36 space-y-1 overflow-y-auto pr-1">
                <li
                  v-for="u in (chat.whitelist_sender_chats || [])"
                  :key="`wl-sc-${u}`"
                  class="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.04] px-2 py-1.5 text-[11px] backdrop-blur-sm"
                >
                  <span class="font-mono text-zinc-200">@{{ String(u || '').replace(/^@+/, '') }}</span>
                  <button
                    type="button"
                    class="text-rose-300 hover:text-rose-200"
                    :disabled="whitelistLoading"
                    @click="removeWhitelistSenderChat(u)"
                  >
                    убрать
                  </button>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="showMentionsFilterModal && chat?.rule"
        class="fixed inset-0 z-[255] flex items-center justify-center bg-black/60 p-4 backdrop-blur-[2px]"
        @click.self="showMentionsFilterModal = false"
      >
        <div
          class="w-full max-w-md rounded-2xl border border-white/15 bg-gradient-to-b from-slate-900 to-slate-950 p-4 text-slate-100 shadow-2xl ring-1 ring-violet-500/20"
          @click.stop
        >
          <div class="mb-3 flex items-center justify-between">
            <h3 class="text-sm font-semibold text-white">@ Упоминания</h3>
            <button type="button" class="rounded-lg px-2 py-1 text-xs text-slate-400 hover:bg-white/10" @click="showMentionsFilterModal = false">✕</button>
          </div>
          <p class="mb-3 text-[11px] leading-relaxed text-slate-400">
            @username и текстовые упоминания. «Запрещено» — удаляются по общему действию (удалить / мут / бан).
          </p>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="opt in policyOptions"
              :key="`men-${opt.value}`"
              type="button"
              :class="policyButtonClass(chat.rule.filter_mentions ? 'forbid' : 'allow', opt.value)"
              class="rounded-xl px-2.5 py-2.5 text-xs font-medium"
              @click="updateRule({ filter_mentions: opt.value === 'forbid' })"
            >
              {{ opt.label }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="showMediaFilterModal && chat?.rule"
        class="fixed inset-0 z-[255] flex items-center justify-center bg-black/60 p-4 backdrop-blur-[2px]"
        @click.self="showMediaFilterModal = false"
      >
        <div
          class="w-full max-w-md rounded-2xl border border-white/15 bg-gradient-to-b from-slate-900 to-slate-950 p-4 text-slate-100 shadow-2xl ring-1 ring-amber-500/20"
          @click.stop
        >
          <div class="mb-3 flex items-center justify-between">
            <h3 class="text-sm font-semibold text-white">🖼 Медиа и стикеры</h3>
            <button type="button" class="rounded-lg px-2 py-1 text-xs text-slate-400 hover:bg-white/10" @click="showMediaFilterModal = false">✕</button>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="opt in policyOptions"
              :key="`med-${opt.value}`"
              type="button"
              :class="policyButtonClass(chat.rule.filter_media_mode, opt.value)"
              class="rounded-xl px-2.5 py-2.5 text-xs font-medium"
              @click="updateRule({ filter_media_mode: opt.value })"
            >
              {{ opt.label }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="showButtonsFilterModal && chat?.rule"
        class="fixed inset-0 z-[255] flex items-center justify-center bg-black/60 p-4 backdrop-blur-[2px]"
        @click.self="showButtonsFilterModal = false"
      >
        <div
          class="w-full max-w-md rounded-2xl border border-white/15 bg-gradient-to-b from-slate-900 to-slate-950 p-4 text-slate-100 shadow-2xl ring-1 ring-emerald-500/20"
          @click.stop
        >
          <div class="mb-3 flex items-center justify-between">
            <h3 class="text-sm font-semibold text-white">🔘 Сообщения с кнопками</h3>
            <button type="button" class="rounded-lg px-2 py-1 text-xs text-slate-400 hover:bg-white/10" @click="showButtonsFilterModal = false">✕</button>
          </div>
          <p class="mb-3 text-[11px] text-slate-400">
            Inline-кнопки вроде «перейти», «бонус», «вступить».
          </p>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="opt in policyOptions"
              :key="`btn-${opt.value}`"
              type="button"
              :class="policyButtonClass(chat.rule.filter_buttons_mode, opt.value)"
              class="rounded-xl px-2.5 py-2.5 text-xs font-medium"
              @click="updateRule({ filter_buttons_mode: opt.value })"
            >
              {{ opt.label }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <div
      v-if="showAntinakrutkaSettingsModal && chat?.rule"
      class="fixed inset-0 z-[266] flex items-center justify-center bg-black/65 p-3"
      @click.self="showAntinakrutkaSettingsModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-cyan-400/22 bg-gradient-to-b from-slate-900/95 via-slate-950/95 to-black/95 p-4 text-slate-100 shadow-[0_26px_90px_-24px_rgba(0,0,0,0.95),inset_0_1px_0_rgba(255,255,255,0.1)] backdrop-blur-2xl ring-1 ring-cyan-300/20">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-cyan-100">Антинакрутка — настройки</h3>
          <button
            type="button"
            class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10"
            @click="showAntinakrutkaSettingsModal = false"
          >
            ✕
          </button>
        </div>
        <div class="space-y-3">
          <div class="rounded-xl border border-cyan-300/20 bg-cyan-500/[0.08] p-2.5 backdrop-blur-md">
            <p class="mb-1 text-xs text-slate-300">Быстрая настройка</p>
            <div class="grid grid-cols-3 gap-2">
              <button
                v-for="preset in antinakrutkaModePresets"
                :key="`anti-set-${preset.key}`"
                type="button"
                class="rounded-lg border px-2 py-2 text-xs font-semibold transition"
                :class="antiraidPresetClass(preset.key)"
                @click="applyAntinakrutkaPreset(preset)"
              >
                {{ preset.label }}
              </button>
            </div>
          </div>
          <div class="flex items-center justify-between gap-2 rounded-xl border border-cyan-300/20 bg-cyan-500/[0.08] p-2.5 backdrop-blur-md">
            <span class="text-xs text-slate-300">Включить антинакрутку</span>
            <button
              type="button"
              :class="boolToggleClass(chat.rule.antinakrutka_enabled)"
              class="rounded-lg px-2.5 py-1 text-xs"
              @click="onAntinakrutkaMainToggleClick"
            >
              {{ chat.rule.antinakrutka_enabled ? 'ВКЛ' : 'ВЫКЛ' }}
            </button>
          </div>
          <div v-if="chat.rule.antinakrutka_enabled" class="space-y-2">
            <div>
              <p class="mb-1 text-xs text-slate-400">Порог (участников за окно)</p>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="n in antinakrutkaThresholdPresets"
                  :key="`anti-th-${n}`"
                  type="button"
                  :class="(chat.rule.antinakrutka_joins_threshold || 10) === n ? 'guard-green-soft' : protToggleOff"
                  class="rounded-lg px-2.5 py-1 text-xs"
                  @click="updateRule({ antinakrutka_joins_threshold: n })"
                >
                  {{ n }}
                </button>
              </div>
            </div>
            <div>
              <p class="mb-1 text-xs text-slate-400">Окно (мин)</p>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="w in antinakrutkaWindowPresets"
                  :key="`anti-win-${w}`"
                  type="button"
                  :class="(chat.rule.antinakrutka_window_minutes || 5) === w ? 'guard-green-soft' : protToggleOff"
                  class="rounded-lg px-2.5 py-1 text-xs"
                  @click="updateRule({ antinakrutka_window_minutes: w })"
                >
                  {{ w }} мин
                </button>
              </div>
            </div>
            <div>
              <p class="mb-1 text-xs text-slate-400">Действие</p>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="opt in antinakrutkaActionOptions"
                  :key="`anti-act-${opt.value}`"
                  type="button"
                  :class="(chat.rule.antinakrutka_action || 'alert') === opt.value ? 'guard-green-soft' : protToggleOff"
                  class="rounded-lg px-2.5 py-1 text-xs"
                  @click="updateRule({ antinakrutka_action: opt.value })"
                >
                  {{ opt.label }}
                </button>
              </div>
            </div>
            <div v-if="(chat.rule.antinakrutka_action || 'alert') === 'alert_restrict'">
              <p class="mb-1 text-xs text-slate-400">Мут (мин)</p>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="r in antinakrutkaRestrictPresets"
                  :key="`anti-res-${r}`"
                  type="button"
                  :class="(chat.rule.antinakrutka_restrict_minutes || 30) === r ? 'guard-green-soft' : protToggleOff"
                  class="rounded-lg px-2.5 py-1 text-xs"
                  @click="updateRule({ antinakrutka_restrict_minutes: r })"
                >
                  {{ r }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div
      v-if="showAntinakrutkaInfoModal"
      class="fixed inset-0 z-[266] flex items-center justify-center bg-black/65 p-3"
      @click.self="showAntinakrutkaInfoModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-sky-300/50 bg-white p-4 shadow-2xl dark:border-sky-700/60 dark:bg-gray-800">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold text-gray-900 dark:text-white">😈 Антинакрутка</h3>
          <button
            type="button"
            class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10"
            @click="showAntinakrutkaInfoModal = false"
          >
            ✕
          </button>
        </div>
        <div class="space-y-3 text-xs text-gray-700 dark:text-gray-300">
          <p>
            Слежу за <strong>волнами входов</strong> за короткое окно. Порог перевален — шлю сигнал, а если включено пожёстче, могу автоматом приглушить свежих, пока шторм не уляжется.
          </p>
          <div class="rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-900/40">
            <p class="font-semibold text-gray-900 dark:text-white">Три настроения</p>
            <p class="mt-1"><strong>Мягко</strong> — для обычного роста, чтобы не душить живых.</p>
            <p><strong>Стандарт</strong> — мой будничный режим по умолчанию.</p>
            <p><strong>Жёстко</strong> — когда явно лезут боты или рейд, и пора включать громче.</p>
          </div>
          <div class="rounded-lg border border-emerald-300/70 bg-emerald-50 p-3 dark:border-emerald-700/70 dark:bg-emerald-950/20">
            <p class="font-semibold text-emerald-900 dark:text-emerald-200">Вышла реклама у блогера</p>
            <p class="mt-1 text-emerald-800 dark:text-emerald-300">
              Держи <strong>Мягко</strong> или <strong>Стандарт</strong>, чтобы не резать нормальный приток. Увидел пустые профили, клонов и спам-волну — на 30–60 минут можно <strong>Жёстко</strong>, потом вернуться.
            </p>
          </div>
          <p class="text-xs text-slate-400">
            В отчётах видно, где был пик входов и сколько раз я вмешался — не гадай вслепую.
          </p>
        </div>
      </div>
    </div>
    <div
      v-if="showJoinCaptchaSettingsModal && chat?.rule"
      class="fixed inset-0 z-[266] flex items-end justify-center bg-black/65 p-3 md:items-center"
      @click.self="showJoinCaptchaSettingsModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-indigo-400/22 bg-gradient-to-b from-slate-900/95 via-slate-950/95 to-black/95 p-4 text-slate-100 shadow-[0_26px_90px_-24px_rgba(0,0,0,0.95),inset_0_1px_0_rgba(255,255,255,0.1)] backdrop-blur-2xl ring-1 ring-indigo-300/20">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-indigo-100">Капча при входе — настройки</h3>
          <button
            type="button"
            class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10"
            @click="showJoinCaptchaSettingsModal = false"
          >
            ✕
          </button>
        </div>
        <div class="space-y-3">
          <div>
            <p class="mb-1 text-xs text-slate-400">Время на ответ (мин)</p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="m in joinCaptchaTtlPresets"
                :key="`jc-ttl-modal-${m}`"
                type="button"
                :class="(chat.rule.join_captcha_ttl_minutes ?? 3) === m ? 'guard-green-soft' : protToggleOff"
                class="rounded-lg px-2.5 py-1 text-xs"
                @click="updateRule({ join_captcha_ttl_minutes: m })"
              >
                {{ m }}
              </button>
            </div>
          </div>
          <div>
            <p class="mb-1 text-xs text-slate-400">Тип проверки</p>
            <div class="flex max-h-[10rem] flex-wrap gap-1.5 overflow-y-auto pr-0.5">
              <button
                v-for="k in joinCaptchaKinds"
                :key="`jc-kind-modal-${k.value}`"
                type="button"
                :class="(chat.rule.join_captcha_kind || 'button') === k.value ? 'guard-green-soft' : protToggleOff"
                class="rounded-lg px-2 py-1 text-[11px] leading-tight"
                @click="updateRule({ join_captcha_kind: k.value })"
              >
                {{ k.label }}
              </button>
            </div>
          </div>
          <div class="mt-2 flex items-center justify-between gap-2">
            <span class="text-xs text-slate-300">Сначала в личку боту</span>
            <button
              type="button"
              :class="boolToggleClass(!!chat.rule.join_captcha_prefer_dm)"
              class="rounded-lg px-2.5 py-1 text-xs"
              @click="updateRule({ join_captcha_prefer_dm: !chat.rule.join_captcha_prefer_dm })"
            >
              {{ chat.rule.join_captcha_prefer_dm ? 'ДА' : 'НЕТ' }}
            </button>
          </div>
          <p class="text-[11px] leading-snug text-slate-500">
            Нужны права бота «блокировать» участников. Если не смогу ограничить — всё равно пришлю капчу, но писать смогут до прохождения.
          </p>
        </div>
      </div>
    </div>
    <div
      v-if="showJoinCaptchaInfoModal"
      class="fixed inset-0 z-[266] flex items-center justify-center bg-black/65 p-3"
      @click.self="showJoinCaptchaInfoModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-sky-300/50 bg-white p-4 shadow-2xl dark:border-sky-700/60 dark:bg-gray-800">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold text-gray-900 dark:text-white">😈 Капча при входе</h3>
          <button
            type="button"
            class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10"
            @click="showJoinCaptchaInfoModal = false"
          >
            ✕
          </button>
        </div>
        <div class="space-y-2 text-xs leading-relaxed text-gray-700 dark:text-gray-300">
          <p>
            После входа на время <strong>приглушаю</strong> человека (если у бота есть «блокировать») и включаю одну из проверок:
            <strong>кнопки</strong>, <strong>счёт</strong>, <strong>эмодзи</strong>, <strong>слово → эмодзи</strong>, <strong>цифры</strong> (картинка или текст, если картинка не взлетела),
            <strong>повтори слово</strong> или <strong>отгадай слово</strong> по маске — ответ нужно прислать сообщением в чат (или в ЛС, если капча ушла туда).
          </p>
          <p class="rounded-lg border border-amber-200/80 bg-amber-50/90 p-2.5 text-[11px] text-amber-950 dark:border-amber-700/50 dark:bg-amber-950/25 dark:text-amber-100">
            <strong>Про «только этот юзер».</strong> В группе текст капчи видят все — так устроен Telegram.
            Для <strong>кнопок</strong> я сверяю <strong>ID нажавшего</strong> с ID вступившего; для <strong>текста</strong> — только сообщения от его аккаунта.
            Чтобы не светить проверку в группе, включи <strong>«Сначала в личку»</strong> (нужен открытый диалог со мной).
          </p>
          <p class="text-[11px] text-gray-500 dark:text-gray-400">
            В форумах с темами капчу и приветствия лучше вести в одну закреплённую «служебную» ветку — иначе поток размазывается по топикам (см. документацию Telegram про главную ветку / forum).
          </p>
          <p class="text-[11px] text-gray-500 dark:text-gray-400">
            Не успел за минуты из настроек — кик с возможностью зайти снова. Успел — снимаю мут и дальше не лезу.
          </p>
        </div>
      </div>
    </div>
    <div
      v-if="showAntispamInfoModal"
      class="fixed inset-0 z-[266] flex items-center justify-center bg-black/65 p-3"
      @click.self="showAntispamInfoModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-sky-300/50 bg-white p-4 shadow-2xl dark:border-sky-700/60 dark:bg-gray-800">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold text-gray-900 dark:text-white">😈 Антиспам-база</h3>
          <button
            type="button"
            class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10"
            @click="showAntispamInfoModal = false"
          >
            ✕
          </button>
        </div>
        <div class="space-y-2 text-xs text-gray-700 dark:text-gray-300">
          <p>Общий чёрный список: кого занесли — того на входе режу во всех чатах, где проверка включена.</p>
          <p><strong>Зачем:</strong> одни и те же рейдеры снова и снова прыгают между твоими залами.</p>
          <p><strong>Как:</strong> включи проверку в чате и добавь ID или ответь <code>/addantispam</code> на сообщение гостя — я сам пойму, кого занести.</p>
          <p><strong>Если промахнулся:</strong> убери через «Открыть базу», не оставляй обидчиков навечно.</p>
        </div>
      </div>
    </div>
    <div
      v-if="showNewbieInfoModal"
      class="fixed inset-0 z-[266] flex items-center justify-center bg-black/65 p-3"
      @click.self="showNewbieInfoModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-sky-300/50 bg-white p-4 shadow-2xl dark:border-sky-700/60 dark:bg-gray-800">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold text-gray-900 dark:text-white">😈 Режим «Новички»</h3>
          <button
            type="button"
            class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10"
            @click="showNewbieInfoModal = false"
          >
            ✕
          </button>
        </div>
        <div class="space-y-2 text-xs text-gray-700 dark:text-gray-300">
          <p>Только вошёл — считаю его «свежаком» на выбранные минуты.</p>
          <p>Правила те же, но в отчётах подсвечу причину как «новичок», чтобы сразу видеть волну риска после рекламы или рейда.</p>
          <p><strong>Когда включать:</strong> после промо, когда сыпятся пустые профили или когда просто много новых лиц за короткий срок.</p>
          <p><strong>По времени:</strong> стартуй с 10–15 минут; если жарко — 30–60, потом отпусти назад.</p>
        </div>
      </div>
    </div>
    <div
      v-if="showAntispamListModal"
      class="fixed inset-0 z-[266] flex items-center justify-center bg-black/65 p-3"
      @click.self="showAntispamListModal = false"
    >
      <div class="w-full max-w-xl rounded-2xl border border-cyan-400/22 bg-gradient-to-b from-slate-900/95 via-slate-950/95 to-black/95 p-4 text-slate-100 shadow-[0_26px_90px_-24px_rgba(0,0,0,0.95),inset_0_1px_0_rgba(255,255,255,0.1)] backdrop-blur-2xl ring-1 ring-cyan-300/20">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-cyan-100">Антиспам база — настройки</h3>
          <button
            type="button"
            class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10"
            @click="showAntispamListModal = false"
          >
            ✕
          </button>
        </div>
        <p class="mb-3 rounded-xl border border-cyan-300/20 bg-cyan-500/[0.08] p-2.5 text-[11px] leading-relaxed text-slate-200/90 backdrop-blur-md">
          Общая база пользователей по всем чатам бота. При включении этой функции пользователи из базы будут автоматически удаляться при входе в текущий чат.
          Быстрый способ без ID: в группе ответьте на сообщение пользователя и отправьте <code>/addantispam</code>.
        </p>
        <div class="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
          <input
            v-model="newAntispamUserId"
            type="text"
            placeholder="User ID (число)"
            class="min-w-0 rounded-lg border border-white/15 bg-white/10 px-2.5 py-2 text-xs text-slate-100 placeholder:text-slate-400"
            :disabled="antispamLoading"
            @keydown.enter.prevent="addAntispamUser()"
          />
          <button
            type="button"
            class="guard-green-soft w-full rounded-lg px-3 py-2 text-xs font-semibold disabled:opacity-50 sm:w-auto"
            :disabled="antispamLoading || !(newAntispamUserId || '').trim()"
            @click="addAntispamUser()"
          >
            Добавить
          </button>
        </div>
        <p v-if="!(antispamItems || []).length" class="text-xs text-slate-400">База пока пустая.</p>
        <ul v-else class="max-h-[52vh] space-y-2 overflow-y-auto pr-1">
          <li
            v-for="item in antispamItems"
            :key="`base-${item.user_id}`"
            class="flex items-center justify-between gap-2 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs"
          >
            <span class="min-w-0 flex-1 text-slate-100">{{ item.display_label || item.user_id }}{{ item.reason ? ` — ${item.reason}` : '' }}</span>
            <button
              type="button"
              class="shrink-0 rounded-lg border border-rose-300/35 bg-rose-500/15 px-2.5 py-1 text-xs font-medium text-rose-100 hover:bg-rose-500/25"
              :disabled="antispamLoading"
              @click="removeAntispamUser(item.user_id)"
            >
              Удалить
            </button>
          </li>
        </ul>
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="showFreeLimitsPremiumModal"
        class="fixed inset-0 z-[268] flex items-center justify-center bg-black/70 p-4 backdrop-blur-[2px]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="free-limits-premium-title"
        @click.self="closeFreeLimitsPremiumModal"
      >
        <div
          class="relative w-full max-w-[min(100%,22rem)] overflow-hidden rounded-[1.125rem] border border-violet-500/35 bg-black px-5 py-7 text-white shadow-[0_0_48px_-18px_rgba(124,58,237,0.55)] ring-1 ring-inset ring-violet-500/15"
          @click.stop
        >
          <div
            class="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_50%_0%,rgba(139,92,246,0.22),transparent_55%)]"
            aria-hidden="true"
          />
          <button
            type="button"
            class="absolute right-3 top-3 z-[2] rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-400 transition hover:bg-white/10 hover:text-white"
            aria-label="Закрыть"
            @click="closeFreeLimitsPremiumModal"
          >
            ✕
          </button>
          <div class="relative z-[1] flex flex-col items-center">
            <div
              class="flex h-[4.25rem] w-[4.25rem] items-center justify-center rounded-full border-2 border-violet-400/55 bg-gradient-to-b from-violet-950/90 to-black text-[2rem] shadow-[0_0_36px_rgba(167,139,250,0.65)]"
              aria-hidden="true"
            >
              🔒
            </div>
            <p
              id="free-limits-premium-title"
              class="mt-5 text-center text-[11px] font-extrabold uppercase tracking-[0.22em] text-violet-300"
            >
              Ограничения Free
            </p>
            <p class="mt-2 max-w-[19rem] text-center text-[13px] leading-relaxed text-slate-400">
              Вы используете бесплатный тариф.<br>
              Некоторые функции недоступны в Free версии
            </p>
            <ul class="mt-5 w-full space-y-3 rounded-2xl border border-white/[0.08] bg-zinc-950/90 px-4 py-4">
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
              class="mt-6 w-full rounded-2xl bg-violet-600 py-3.5 text-[15px] font-bold text-white shadow-[0_12px_32px_-8px_rgba(124,58,237,0.55)] transition hover:bg-violet-500 active:scale-[0.99]"
              @click="onFreeLimitsModalLearnMore"
            >
              Подробнее о Premium
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
/* Круглые «i» — нейтральное тёмное стекло (без синего неона) */
.prot-info-btn {
  display: inline-flex;
  height: 1.75rem;
  min-width: 1.75rem;
  align-items: center;
  justify-content: center;
  padding: 0 0.35rem;
  border-radius: 9999px;
  font-size: 0.625rem;
  font-weight: 800;
  line-height: 1;
  letter-spacing: -0.02em;
  color: #e2e8f0;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: linear-gradient(155deg, rgba(51, 65, 85, 0.8) 0%, rgba(15, 23, 42, 0.96) 100%);
  box-shadow:
    0 4px 14px -6px rgba(0, 0, 0, 0.45),
    inset 0 1px 0 rgba(255, 255, 255, 0.14);
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease,
    transform 0.12s ease;
}
.prot-info-btn:hover {
  border-color: rgba(255, 255, 255, 0.35);
  box-shadow:
    0 6px 16px -8px rgba(0, 0, 0, 0.55),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
  transform: scale(1.04);
}
.prot-info-btn:active {
  transform: scale(0.97);
}
.prot-info-btn--danger {
  border-color: rgba(248, 113, 113, 0.45);
  background: linear-gradient(155deg, rgba(127, 29, 29, 0.88) 0%, rgba(15, 23, 42, 0.96) 100%);
  box-shadow:
    0 4px 14px -4px rgba(239, 68, 68, 0.32),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
  color: #fecaca;
}
.prot-info-btn--danger:hover {
  border-color: rgba(252, 165, 165, 0.55);
}
.prot-info-btn--frost {
  border-color: rgba(255, 255, 255, 0.26);
  background: linear-gradient(155deg, rgba(255, 255, 255, 0.1) 0%, rgba(15, 23, 42, 0.62) 100%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.18),
    0 4px 14px -6px rgba(0, 0, 0, 0.4);
  color: #fff;
}
.chatbar-info-btn {
  height: 1.65rem;
  min-width: 1.65rem;
  padding: 0 0.3rem;
}

/* Модалка «Ссылки»: стекло + читаемые подсказки с v-html */
.links-glass-panel {
  -webkit-backdrop-filter: blur(24px);
  backdrop-filter: blur(24px);
}

.link-glass-info-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 1.5rem;
  min-width: 1.5rem;
  padding: 0 0.4rem;
  border-radius: 9999px;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  color: #e2e8f0;
  border: 1px solid rgba(71, 85, 105, 0.55);
  background: linear-gradient(160deg, rgba(30, 41, 59, 0.95) 0%, rgba(15, 23, 42, 0.98) 100%);
  box-shadow:
    0 3px 12px -4px rgba(0, 0, 0, 0.5),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease,
    transform 0.12s ease;
}
.link-glass-info-btn:hover {
  border-color: rgba(148, 163, 184, 0.45);
  transform: scale(1.03);
}
.link-glass-info-btn--active {
  border-color: rgba(52, 211, 153, 0.45);
  color: #ecfdf5;
  background: linear-gradient(160deg, rgba(5, 150, 105, 0.45) 0%, rgba(15, 23, 42, 0.95) 100%);
  box-shadow:
    0 0 16px -5px rgba(52, 211, 153, 0.35),
    inset 0 1px 0 rgba(255, 255, 255, 0.12);
}

.link-liquid-hint {
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.08),
    0 4px 20px -12px rgba(0, 0, 0, 0.4);
}

.link-modal-hint :deep(strong) {
  font-weight: 600;
  color: rgb(250 250 250);
}

.link-modal-hint :deep(br) {
  display: block;
  margin-top: 0.35em;
}

@keyframes hourglassFlip {
  0% { transform: rotate(0deg); }
  50% { transform: rotate(180deg); }
  100% { transform: rotate(360deg); }
}

.hourglass-flip {
  animation: hourglassFlip 0.9s ease-in-out infinite;
  transform-origin: 50% 50%;
}

.welcome-rich-editor {
  color: #f8fafc !important;
  caret-color: #f8fafc !important;
  -webkit-text-fill-color: #f8fafc;
}
.welcome-rich-editor :deep(p),
.welcome-rich-editor :deep(div),
.welcome-rich-editor :deep(span),
.welcome-rich-editor :deep(b),
.welcome-rich-editor :deep(strong),
.welcome-rich-editor :deep(i),
.welcome-rich-editor :deep(em),
.welcome-rich-editor :deep(u),
.welcome-rich-editor :deep(s),
.welcome-rich-editor :deep(br) {
  color: #f8fafc !important;
  -webkit-text-fill-color: #f8fafc;
}
.welcome-rich-editor[data-placeholder]:empty:before {
  content: attr(data-placeholder);
  color: #94a3b8 !important;
  -webkit-text-fill-color: #94a3b8;
  pointer-events: none;
}
.welcome-rich-editor :deep(a) {
  color: #60a5fa !important;
  -webkit-text-fill-color: #60a5fa;
  text-decoration: underline;
  text-underline-offset: 2px;
}
/* Как в редакторе рассылки: цитата визуально в поле */
.welcome-rich-editor :deep(blockquote) {
  display: block;
  margin: 0.35rem 0;
  padding: 0.35rem 0.65rem;
  border-left: 3px solid rgba(59, 130, 246, 0.9);
  background: rgba(59, 130, 246, 0.12);
  border-radius: 0.4rem;
  color: #e2e8f0 !important;
  -webkit-text-fill-color: #e2e8f0;
}
.welcome-rich-editor :deep(blockquote) p,
.welcome-rich-editor :deep(blockquote) div {
  color: #e2e8f0 !important;
  -webkit-text-fill-color: #e2e8f0;
  margin: 0;
}
.welcome-rich-editor :deep(code) {
  background: rgba(148, 163, 184, 0.2);
  border-radius: 0.35rem;
  padding: 0.05rem 0.3rem;
  color: #f8fafc !important;
  -webkit-text-fill-color: #f8fafc;
  font-size: 0.85em;
}
.welcome-rich-editor :deep(pre) {
  margin: 0.25rem 0;
  padding: 0.35rem 0.5rem;
  border-radius: 0.4rem;
  background: rgba(15, 23, 42, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.25);
  white-space: pre-wrap;
  color: #e2e8f0 !important;
  -webkit-text-fill-color: #e2e8f0;
  font-size: 0.8em;
}
.welcome-rich-editor :deep([data-spoiler='1']) {
  color: transparent !important;
  -webkit-text-fill-color: transparent;
  border-radius: 0.35rem;
  padding: 0 0.2rem;
  background-color: rgba(148, 163, 184, 0.22);
  background-image: radial-gradient(rgba(226, 232, 240, 0.9) 0.85px, transparent 0.9px);
  background-size: 5px 5px;
}
.welcome-rich-editor :deep([data-spoiler='1'].reveal),
.welcome-rich-editor :deep([data-spoiler='1']:hover) {
  color: #e2e8f0 !important;
  -webkit-text-fill-color: #e2e8f0;
  background: rgba(255, 255, 255, 0.12);
  background-image: none;
}

.post-rules-tool-btn {
  border-radius: 0.65rem;
  border: 1px solid rgba(148, 163, 184, 0.28);
  background: linear-gradient(160deg, rgba(15, 23, 42, 0.85) 0%, rgba(2, 6, 23, 0.95) 100%);
  padding: 0.28rem 0.55rem;
  font-size: 11px;
  color: #dbeafe;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}
.post-rules-tool-btn:hover {
  border-color: rgba(103, 232, 249, 0.4);
  background: linear-gradient(160deg, rgba(8, 47, 73, 0.75) 0%, rgba(15, 23, 42, 0.95) 100%);
}
.post-rules-rich-editor {
  color: #f8fafc !important;
  caret-color: #f8fafc !important;
  -webkit-text-fill-color: #f8fafc;
}
.post-rules-rich-editor[data-placeholder]:empty:before {
  content: attr(data-placeholder);
  color: #94a3b8 !important;
  -webkit-text-fill-color: #94a3b8;
  pointer-events: none;
}
.post-rules-rich-editor :deep(a) {
  color: #60a5fa !important;
  -webkit-text-fill-color: #60a5fa;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.post-rules-modal-head {
  position: relative;
  overflow: hidden;
}
.post-rules-modal-head::after {
  content: '';
  position: absolute;
  inset: 0 auto 0 -20%;
  width: 45%;
  background: linear-gradient(110deg, rgba(255, 255, 255, 0.14), rgba(255, 255, 255, 0));
  transform: skewX(-18deg);
  pointer-events: none;
}
.post-rules-mode-btn-active {
  color: #ecfeff;
  border: 1px solid rgba(125, 211, 252, 0.5);
  box-shadow:
    0 10px 24px -14px rgba(34, 211, 238, 0.7),
    inset 0 1px 0 rgba(255, 255, 255, 0.16);
}
.post-rules-mode-btn-cyan {
  background: linear-gradient(140deg, rgba(34, 211, 238, 0.32), rgba(15, 23, 42, 0.92));
}
.post-rules-mode-btn-violet {
  background: linear-gradient(140deg, rgba(167, 139, 250, 0.34), rgba(15, 23, 42, 0.92));
  border-color: rgba(196, 181, 253, 0.5);
  box-shadow:
    0 10px 24px -14px rgba(167, 139, 250, 0.75),
    inset 0 1px 0 rgba(255, 255, 255, 0.16);
}
.post-rules-footer {
  background: linear-gradient(180deg, rgba(2, 6, 23, 0.35), rgba(2, 6, 23, 0.62));
}
.post-rules-action-btn {
  border-radius: 0.72rem;
  border: 1px solid rgba(148, 163, 184, 0.28);
  padding: 0.42rem 0.82rem;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
  transition: all 0.2s ease;
  backdrop-filter: blur(10px);
}
.post-rules-action-btn:disabled {
  opacity: 0.58;
  cursor: not-allowed;
}
.post-rules-action-btn--send {
  color: #e2e8f0;
}
.post-rules-action-btn--group {
  border-color: rgba(52, 211, 153, 0.45);
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.28), rgba(15, 23, 42, 0.92));
  box-shadow: 0 10px 26px -16px rgba(16, 185, 129, 0.82);
}
.post-rules-action-btn--group:hover {
  border-color: rgba(110, 231, 183, 0.58);
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.38), rgba(15, 23, 42, 0.92));
}
.post-rules-action-btn--channel {
  border-color: rgba(196, 181, 253, 0.44);
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.3), rgba(15, 23, 42, 0.92));
  box-shadow: 0 10px 26px -16px rgba(139, 92, 246, 0.85);
}
.post-rules-action-btn--channel:hover {
  border-color: rgba(216, 180, 254, 0.56);
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.4), rgba(15, 23, 42, 0.92));
}
.post-rules-action-btn--cancel {
  color: #cbd5e1;
  background: linear-gradient(145deg, rgba(51, 65, 85, 0.34), rgba(15, 23, 42, 0.9));
}
.post-rules-action-btn--cancel:hover {
  border-color: rgba(148, 163, 184, 0.42);
}
.post-rules-action-btn--save {
  color: #042f2e;
  border-color: rgba(45, 212, 191, 0.5);
  background: linear-gradient(140deg, rgba(45, 212, 191, 0.95), rgba(52, 211, 153, 0.86));
  box-shadow: 0 12px 30px -18px rgba(45, 212, 191, 0.9);
}
.post-rules-action-btn--save:hover {
  filter: brightness(1.06);
}

/* Модалка правил группы — те же «стеклянные» карточки, что в ChannelPostRulesModal */
.glass-panel {
  border-radius: 0.95rem;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: linear-gradient(160deg, rgba(15, 23, 42, 0.56) 0%, rgba(2, 6, 23, 0.48) 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(14px) saturate(140%);
}
</style>

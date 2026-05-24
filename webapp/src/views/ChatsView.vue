<script setup>
import { ref, onMounted, onUnmounted, watch, computed, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useApi, messageFromApiError } from '../composables/useApi'
import { guardFilterChain, guardLog, guardWarn } from '../utils/guardDebugLog'
import { useCabinetMode } from '../composables/useCabinetMode'
import { useToast } from '../composables/useToast'
import ChannelPostRulesModal from '../components/ChannelPostRulesModal.vue'
import SecurityPinGateModal from '../components/SecurityPinGateModal.vue'
import GuardTeleport from '../components/GuardTeleport.vue'
import GuardAutoApproveJoinSetting from '../components/GuardAutoApproveJoinSetting.vue'
import PremiumLockBadge from '../components/PremiumLockBadge.vue'
import ChatAvatar from '../components/ChatAvatar.vue'
import { useSecurityPinGate } from '../composables/useSecurityPinGate'
import { usePremiumLock } from '../composables/usePremiumLock'
import { shouldAskPinForAction } from '../utils/settingsSecurity'
import {
  readChatsListCache,
  writeChatsListCache,
  sortChatsRows,
  prefetchChatsList,
  fetchAndCacheChatsList,
} from '../utils/chatsListCache.js'

const ME_PREMIUM_CACHE_KEY = 'guard.me.is_premium.v1'

function readMePremiumCache() {
  try {
    const raw = localStorage.getItem(ME_PREMIUM_CACHE_KEY)
    if (raw === '1') return true
    if (raw === '0') return false
  } catch {
    //
  }
  return null
}

function writeMePremiumCache(isPremium) {
  try {
    localStorage.setItem(ME_PREMIUM_CACHE_KEY, isPremium ? '1' : '0')
  } catch {
    //
  }
}

const { t } = useI18n()
const isEn = computed(() => t('common.locale_code') === 'en')

const router = useRouter()
const route = useRoute()
const { api, error, fetchSilent, hasInitData } = useApi()
const { showToast } = useToast()
const { setCabinetMode } = useCabinetMode()
const { openLock } = usePremiumLock()
const lastMeForPremiumLock = ref(null)
/** Только фиолетовый ADM: ?cabinet=delegated. Обычный список чатов не зависит от localStorage — всегда свои + делегированные. */
const delegatedChatsOnly = computed(() => String(route.query.cabinet || '').toLowerCase() === 'delegated')
const focusThreatOnly = computed(() => String(route.query.threat || '') === '1')
/** Первый запрос списка: без глобального loading, но не показываем «нет чатов» до ответа API */
const chatsFirstLoad = ref(true)
const chats = ref([])
const selectedChatId = ref(null)
const pendingCount = ref(0)
const pendingLoading = ref(false)
const cabinetTab = ref('all') // all | mine | shared
/** Пресет внутри вкладки кабинета: все сущности | только группы | только каналы */
const kindPreset = ref('all') // all | groups | channels
const managersModalChat = ref(null)
const managersData = ref({ managers: [], can_manage_access: false, limit: 3, chat_kind: 'group' })
const managersLoading = ref(false)
const managersStats = ref(null)
const addManagerValue = ref('')
const addManagerPerms = ref({ protection: false, broadcast: false, reports: false, stats: false, first_post_settings: false })
const addManagerPermsOpen = ref(false)
// Если выбрано — отправляем флаг as_invite_link=true. Бэк создаст pending-инвайт
// с токеном даже если юзер ещё не общался с ботом, и вернёт invite_link.
const addManagerAsLink = ref(false)

// Журнал действий (Фаза 3). Открывается из шапки модалки админов.
// При клике на бейдж «N за 7д» у конкретного делегата — открывается с фильтром
// по этому user_id (см. openAuditModal(uid)).
const auditModalOpen = ref(false)
const auditLoading = ref(false)
const auditFilterUserId = ref(null)  // null = весь чат, число = только этот делегат
const _AUDIT_PAGE_SIZE = 25
const auditItems = ref([])
const auditTotal = ref(0)
const auditOffset = ref(0)
const auditUserActivity = ref(null) // { last_action_at, actions_7d, actions_30d } для single-user view

const isManagersChannel = computed(
  () => String(managersData.value?.chat_kind || managersModalChat.value?.chat_kind || 'group').toLowerCase() === 'channel'
)
const canSubmitNewManager = computed(() => {
  const raw = String(addManagerValue.value || '').trim()
  if (!raw) return false
  const p = addManagerPerms.value || {}
  if (isManagersChannel.value) return !!(p.broadcast || p.first_post_settings)
  return !!(p.protection || p.broadcast || p.reports || p.stats)
})

function _resetAddManagerForm() {
  addManagerValue.value = ''
  addManagerPerms.value = { protection: false, broadcast: false, reports: false, stats: false, first_post_settings: false }
  addManagerPermsOpen.value = false
  addManagerAsLink.value = false
}

// Мета каждого права: иконка + цветовая палитра бейджа.
// Цвет важен визуально, чтобы быстро понимать на какие зоны открыт доступ.
const MANAGER_PERM_META = Object.freeze({
  protection: {
    icon: '🛡',
    badge: 'bg-emerald-500/15 text-emerald-200',
    removeBtn: 'bg-emerald-900/40 text-emerald-100',
  },
  broadcast: {
    icon: '📢',
    badge: 'bg-violet-500/15 text-violet-200',
    removeBtn: 'bg-violet-900/40 text-violet-100',
  },
  reports: {
    icon: '📋',
    badge: 'bg-cyan-500/15 text-cyan-200',
    removeBtn: 'bg-cyan-900/40 text-cyan-100',
  },
  first_post_settings: {
    icon: '⭐',
    badge: 'bg-amber-500/15 text-amber-200',
    removeBtn: 'bg-amber-900/40 text-amber-100',
  },
})

function managerPermEntries(perms) {
  const p = perms || {}
  const out = []
  if (p.protection) out.push({ key: 'protection', label: t('chats.perms.protection') })
  if (p.broadcast) out.push({ key: 'broadcast', label: t('chats.perms.broadcast') })
  if (p.reports || p.stats) out.push({ key: 'reports', label: t('chats.perms.reports') })
  if (p.first_post_settings) out.push({ key: 'first_post_settings', label: t('chats.perms.first_post_settings') })
  return out
}

// Какие права ещё НЕ выданы делегату. Зависит от типа чата:
// для group релевантны protection/broadcast/reports;
// для channel — broadcast/first_post_settings (см. API normalize в routes.py).
function managerPermMissing(perms) {
  const p = perms || {}
  const isChannel = isManagersChannel.value
  const all = isChannel
    ? ['broadcast', 'first_post_settings']
    : ['protection', 'broadcast', 'reports']
  const out = []
  for (const key of all) {
    const has = key === 'reports' ? !!(p.reports || p.stats) : !!p[key]
    if (!has) out.push({ key, label: t(`chats.perms.${key}`) })
  }
  return out
}

function managerPermMeta(key) {
  return MANAGER_PERM_META[key] || {
    icon: '•',
    badge: 'bg-slate-500/15 text-slate-200',
    removeBtn: 'bg-slate-900/40 text-slate-200',
  }
}

// Цветной аватар-инициал. Цвет детерминирован user_id (хеш в палитру).
const _AVATAR_PALETTE = Object.freeze([
  'from-rose-500/45 to-pink-600/45',
  'from-orange-500/45 to-amber-600/45',
  'from-yellow-500/45 to-lime-600/45',
  'from-emerald-500/45 to-teal-600/45',
  'from-cyan-500/45 to-sky-600/45',
  'from-blue-500/45 to-indigo-600/45',
  'from-violet-500/45 to-purple-600/45',
  'from-fuchsia-500/45 to-pink-500/45',
])

function managerAvatarMeta(m) {
  if (!m) return { initials: '?', gradient: _AVATAR_PALETTE[0] }
  const name = String(m.first_name || m.username || '').trim()
  let initials = ''
  if (name) {
    const parts = name.split(/\s+/).filter(Boolean)
    initials = parts.slice(0, 2).map((p) => p[0]?.toUpperCase() || '').join('')
  }
  if (!initials) {
    const u = String(m.username || '').replace(/^@+/, '')
    initials = u ? u[0].toUpperCase() : '#'
  }
  const idx = Math.abs(Number(m.user_id || 0)) % _AVATAR_PALETTE.length
  return { initials: initials.slice(0, 2), gradient: _AVATAR_PALETTE[idx] }
}

// Пресеты прав — один клик, и все галки расставлены.
// Не показываются для канальной модалки (там всего 2 права).
const MANAGER_PERM_PRESETS = Object.freeze([
  {
    key: 'moderator',
    icon: '🛡',
    perms: { protection: true, broadcast: false, reports: false, stats: false },
  },
  {
    key: 'marketer',
    icon: '📢',
    perms: { protection: false, broadcast: true, reports: true, stats: true },
  },
  {
    key: 'auditor',
    icon: '👁',
    perms: { protection: false, broadcast: false, reports: true, stats: true },
  },
  {
    key: 'co_owner',
    icon: '👑',
    perms: { protection: true, broadcast: true, reports: true, stats: true },
  },
])

function applyManagerPreset(preset) {
  if (!preset) return
  // Сохраняем first_post_settings без изменений (это канальное право, не входит в группы).
  const cur = addManagerPerms.value || {}
  addManagerPerms.value = {
    protection: !!preset.perms.protection,
    broadcast: !!preset.perms.broadcast,
    reports: !!preset.perms.reports,
    stats: !!preset.perms.stats,
    first_post_settings: !!cur.first_post_settings,
  }
}

function isPermPresetActive(preset) {
  const p = addManagerPerms.value || {}
  return (
    !!p.protection === !!preset.perms.protection
    && !!p.broadcast === !!preset.perms.broadcast
    && !!p.reports === !!preset.perms.reports
    && !!p.stats === !!preset.perms.stats
  )
}

// Двухэтапное удаление: храним ID кандидата + список его прав.
const removeManagerConfirm = ref(null) // { user_id, name, perms: ['protection', ...] } | null
function askRemoveManager(manager) {
  if (!manager) return
  const lostPerms = managerPermEntries(manager.permissions || {}).map((p) => p.label)
  removeManagerConfirm.value = {
    user_id: manager.user_id,
    name: manager.first_name || (manager.username ? '@' + manager.username : String(manager.user_id || '—')),
    perms: lostPerms,
  }
}
function cancelRemoveManager() {
  removeManagerConfirm.value = null
}
async function confirmRemoveManager() {
  const target = removeManagerConfirm.value
  removeManagerConfirm.value = null
  if (target?.user_id) {
    await removeManager(target.user_id)
  }
}

function extractTelegramIdFromInitUnsafe() {
  try {
    const id = window.Telegram?.WebApp?.initDataUnsafe?.user?.id
    const n = Number(id || 0)
    return Number.isFinite(n) && n > 0 ? n : 0
  } catch {
    return 0
  }
}

/** Чужой кабинет (делегирование) для UI: сначала сравниваем owner_user_id с tg текущего пользователя,
 * при owner=0 оставляем флаг is_shared с бэка (делегат без владельца в строке). */
function isDelegatedCabinetChat(chat) {
  if (!chat) return false
  const oid = Number(chat.owner_user_id || 0)
  const vid = Number(viewerTelegramId.value || 0)
  if (oid > 0 && vid > 0 && oid === vid) return false
  if (oid > 0 && oid !== vid) return true
  return !!chat.is_shared
}

/** Для делегированного чата: разрешено ли право `key` (если delegated_permissions
 *  не пришли — старая запись, считаем что разрешено всё). Для своих чатов: всегда true. */
function delegatedCan(chat, key) {
  if (!chat || !isDelegatedCabinetChat(chat)) return true
  const perms = chat.delegated_permissions
  if (perms == null) return true
  return !!perms[key]
}

/** Короткая строка прав делегата под карточкой (ключи совпадают с delegated_permissions на API). */
const DELEGATED_PERM_KEYS = ['protection', 'broadcast', 'first_post_settings', 'reports']

function delegatedPermissionsLine(chat) {
  if (!chat || !isDelegatedCabinetChat(chat)) return ''
  const perms = chat.delegated_permissions
  if (perms == null) return t('chats.delegate_access_legacy')
  const labels = []
  for (const k of DELEGATED_PERM_KEYS) {
    if (perms[k]) labels.push(t(`chats.perms.${k}`))
  }
  if (!labels.length) return t('chats.delegate_access_none')
  return labels.join(' · ')
}
const isPremium = ref(readMePremiumCache() ?? false)
/** Для проверки PIN при отключении чата */
const viewerTelegramId = ref(extractTelegramIdFromInitUnsafe())
const {
  pinGateOpen,
  pinGateInput,
  pinGateError,
  pinGateBusy,
  requestPinIfNeeded,
  submitPinGate,
  cancelPinGate,
} = useSecurityPinGate(() => viewerTelegramId.value)
const showCabinetInfoModal = ref(false)
const showDelegatedInfoModal = ref(false)
const showManagersInfoModal = ref(false)
const spikeAlertsByChat = ref({})

const channelPostRulesOpen = ref(false)
const channelPostRulesDiscussionId = ref(0)
const channelPostRulesChannelId = ref(0)
const channelPostRulesChannelTitle = ref('')
const autoApproveSavingId = ref(0)
const autoApproveModalChat = ref(null)

function canManageAutoApprove(chat) {
  if (!chat || chat.locked_by_limit) return false
  // Группы: заявки настраиваются в «Защита» (опрос, ручной приём, отчёты).
  // Каналы: в «Защите» нет — здесь только простой автоприём заявок на подписку.
  if (!isChannelRow(chat)) return false
  return delegatedCan(chat, 'first_post_settings')
}

async function toggleAutoApproveJoin(chat, next) {
  const id = Number(chat?.id || 0)
  if (!id || !hasInitData.value) return
  const prev = !!chat.auto_approve_join_requests
  chat.auto_approve_join_requests = !!next
  autoApproveSavingId.value = id
  try {
    await fetchSilent(() =>
      api.updateRule(id, {
        join_requests_mode: next ? 'auto' : 'off',
        auto_approve_join_requests: !!next,
      }),
    )
  } catch (e) {
    chat.auto_approve_join_requests = prev
    showToast(messageFromApiError(e) || t('chats.toasts.auto_approve_failed'))
  } finally {
    autoApproveSavingId.value = 0
  }
}

function openAutoApproveModal(chat) {
  if (!canManageAutoApprove(chat)) return
  autoApproveModalChat.value = chat
}

function closeAutoApproveModal() {
  autoApproveModalChat.value = null
}

function autoApproveButtonClass(chat) {
  return chat?.auto_approve_join_requests
    ? 'rounded-lg border border-emerald-400/35 bg-emerald-500/15 px-2 py-1 text-[11px] font-semibold leading-tight text-emerald-100'
    : 'rounded-lg border border-violet-400/30 bg-violet-900/25 px-2 py-1 text-[11px] font-semibold leading-tight text-violet-200 hover:bg-violet-900/40'
}

async function openChannelPostRules(chat) {
  if (!chat || chat.locked_by_limit) return
  let did = Number(chat.linked_discussion_chat_id || 0)
  if (!did && Number(chat.id || 0)) {
    try {
      const row = await fetchSilent(() => api.chat(Number(chat.id), { refreshTelegram: true }))
      did = Number(row?.linked_discussion_chat_id || 0)
      if (did > 0) {
        const idx = (chats.value || []).findIndex((c) => Number(c?.id || 0) === Number(chat.id))
        if (idx >= 0) {
          const next = [...chats.value]
          next[idx] = {
            ...next[idx],
            linked_discussion_chat_id: did,
            linked_discussion_title: row?.linked_discussion_title || next[idx]?.linked_discussion_title || '',
          }
          chats.value = next
        }
      }
    } catch {
      // fallback ниже: покажем штатный тост
    }
  }
  if (!did) {
    try {
      const freshList = await fetchSilent(() => api.chats(delegatedChatsOnly.value ? 'shared' : 'all', { refreshTelegram: true }))
      const rows = Array.isArray(freshList?.chats) ? freshList.chats : []
      chats.value = delegatedChatsOnly.value ? rows : [...rows].sort((a, b) => Number(isDelegatedCabinetChat(b)) - Number(isDelegatedCabinetChat(a)))
      const fresh = (chats.value || []).find((c) => Number(c?.id || 0) === Number(chat.id))
      did = Number(fresh?.linked_discussion_chat_id || 0)
    } catch {
      // fallback ниже: покажем штатный тост
    }
  }
  if (!did) {
    showToast(t('chats.toasts.no_discussion'))
    return
  }
  channelPostRulesDiscussionId.value = did
  channelPostRulesChannelId.value = Number(chat.id || 0)
  channelPostRulesChannelTitle.value = String(chat.title || '').trim() || t('chats.labels.channel')
  guardFilterChain('ChannelRules', 'openChannelPostRules:modal_open', {
    channelId: Number(chat.id || 0),
    discussionChatId: did,
    delegatedCabinetChat: !!isDelegatedCabinetChat(chat),
    cabinetDelegatedQuery: delegatedChatsOnly.value,
    channelTitleLen: channelPostRulesChannelTitle.value.length,
  })
  channelPostRulesOpen.value = true
}

// Любая модалка «Чаты» (info-окна + «Админы чата» с её под-модалками) — должна
// блокировать прокрутку фоновой страницы, иначе пользователь промахивается мимо
// модалки и листает список чатов. См. также onUnmounted-сброс html/body.style.
const chatsInfoModalOpen = computed(
  () =>
    showCabinetInfoModal.value ||
    showDelegatedInfoModal.value ||
    showManagersInfoModal.value ||
    !!managersModalChat.value ||
    auditModalOpen.value ||
    addManagerPermsOpen.value ||
    !!removeManagerConfirm.value ||
    channelPostRulesOpen.value ||
    !!autoApproveModalChat.value,
)

watch(
  chatsInfoModalOpen,
  (open) => {
    if (typeof document === 'undefined') return
    const html = document.documentElement
    const body = document.body
    if (open) {
      html.style.overflow = 'hidden'
      body.style.overflow = 'hidden'
    } else {
      html.style.overflow = ''
      body.style.overflow = ''
    }
  },
  { flush: 'post' },
)

let stopVis = null
let managersPollTimer = null
let chatsLoadInFlight = null

function currentChatsMode() {
  return delegatedChatsOnly.value ? 'shared' : 'all'
}

function hydrateChatsFromCache(mode = currentChatsMode()) {
  const cached = readChatsListCache(mode)
  if (!cached || !Array.isArray(cached.rows)) return false
  chats.value = cached.rows
  selectedChatId.value = cached.selected_chat_id ?? null
  pendingCount.value = Number(cached.pending_count || 0)
  if (cached.spike_alerts && typeof cached.spike_alerts === 'object') {
    spikeAlertsByChat.value = cached.spike_alerts
  }
  chatsFirstLoad.value = false
  return true
}

function saveChatsCacheSnapshot(mode = currentChatsMode()) {
  writeChatsListCache(mode, {
    rows: chats.value,
    selected_chat_id: selectedChatId.value,
    pending_count: pendingCount.value,
    spike_alerts: spikeAlertsByChat.value,
  })
}

if (hasInitData.value) {
  hydrateChatsFromCache()
}

async function scrollToFirstThreatChat() {
  if (!focusThreatOnly.value) return
  const firstThreat = visibleChatsForThreatScroll().find((c) => !!chatSpikeAlert(c))
  const chatId = Number(firstThreat?.id || 0)
  if (!chatId || typeof document === 'undefined') return
  await nextTick()
  requestAnimationFrame(() => {
    const el = document.querySelector(`[data-chat-id="${chatId}"]`)
    if (!el || typeof el.scrollIntoView !== 'function') return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  })
}

async function loadSpikeAlertsQuiet(mode = currentChatsMode()) {
  try {
    const a = await fetchSilent(() => api.spikeAlerts())
    const map = {}
    for (const row of a?.items || []) {
      const cid = Number(row?.chat_id || 0)
      if (!cid) continue
      map[cid] = row
    }
    spikeAlertsByChat.value = map
    saveChatsCacheSnapshot(mode)
  } catch {
    spikeAlertsByChat.value = {}
  }
}

async function loadChatsExtras(mode = currentChatsMode()) {
  try {
    const [p, me] = await Promise.all([
      fetchSilent(() => api.connectPending()).catch(() => ({ chats: [] })),
      fetchSilent(() => api.me()).catch(() => null),
    ])
    pendingCount.value = Array.isArray(p?.chats) ? p.chats.length : 0
    if (me) {
      isPremium.value = !!me.is_premium
      writeMePremiumCache(!!me.is_premium)
      lastMeForPremiumLock.value = me
      const fromMe = Number(me.telegram_id || 0)
      viewerTelegramId.value = fromMe > 0 ? fromMe : extractTelegramIdFromInitUnsafe()
      chats.value = sortChatsRows(chats.value, mode === 'shared', viewerTelegramId.value)
    }
    saveChatsCacheSnapshot(mode)
  } catch (e) {
    guardWarn('Chats', 'loadChatsExtras failed', e)
  }
  void loadSpikeAlertsQuiet(mode)
}

function loadChats() {
  if (!hasInitData.value) {
    guardLog('Chats', 'loadChats: skip (no initData)')
    return Promise.resolve()
  }
  if (chatsLoadInFlight) return chatsLoadInFlight

  const mode = currentChatsMode()
  guardLog('Chats', 'loadChats: start', { mode })

  chatsLoadInFlight = (async () => {
    try {
      const { data, rows } = await fetchSilent(() =>
        fetchAndCacheChatsList(api, mode, viewerTelegramId.value),
      )
      chats.value = rows
      selectedChatId.value = data?.selected_chat_id ?? null
      if (mode !== 'shared' && focusThreatOnly.value) {
        cabinetTab.value = 'shared'
      }
      saveChatsCacheSnapshot(mode)
      chatsFirstLoad.value = false
      void scrollToFirstThreatChat()
      void loadChatsExtras(mode)
      guardLog('Chats', 'loadChats OK', {
        count: chats.value.length,
        selected: selectedChatId.value,
        pending: pendingCount.value,
      })
    } catch (e) {
      guardWarn('Chats', 'loadChats failed', e)
    } finally {
      chatsFirstLoad.value = false
      chatsLoadInFlight = null
    }
  })()
  return chatsLoadInFlight
}

function onPrefetchChats(ev) {
  const mode = String(ev?.detail?.mode || 'all') === 'shared' ? 'shared' : 'all'
  void prefetchChatsList(api, mode)
}

function chatSpikeAlert(chat) {
  const cid = Number(chat?.id || 0)
  if (!cid) return null
  return spikeAlertsByChat.value[cid] || null
}

watch(
  hasInitData,
  (ready) => {
    if (!ready) return
    if (!chats.value.length) hydrateChatsFromCache()
    void loadChats()
  },
  { immediate: true },
)

onMounted(() => {
  error.value = null
  window.addEventListener('guard:prefetch-chats', onPrefetchChats)
  const onVis = () => {
    if (document.visibilityState === 'visible') loadChats()
  }
  document.addEventListener('visibilitychange', onVis)
  stopVis = () => {
    document.removeEventListener('visibilitychange', onVis)
    window.removeEventListener('guard:prefetch-chats', onPrefetchChats)
  }
})

onUnmounted(() => {
  if (stopVis) stopVis()
  if (managersPollTimer) clearInterval(managersPollTimer)
  if (typeof document !== 'undefined') {
    document.documentElement.style.overflow = ''
    document.body.style.overflow = ''
  }
})

watch(
  () => route.query.cabinet,
  () => {
    if (!hydrateChatsFromCache(currentChatsMode())) {
      chatsFirstLoad.value = true
      chats.value = []
    }
    loadChats()
  },
)

watch(cabinetTab, () => {
  kindPreset.value = 'all'
})

watch(
  () => delegatedChatsOnly.value,
  (only) => {
    kindPreset.value = 'all'
    if (!only) cabinetTab.value = 'all'
  },
)

async function selectChat(id) {
  if (!hasInitData.value) return
  guardLog('Chats', 'selectChat', { id })
  try {
    await fetchSilent(() => api.selectChat(id))
    selectedChatId.value = id
  } catch (e) {
    guardWarn('Chats', 'selectChat failed', e)
  }
}

async function removeChat(chat) {
  if (!chat?.id || !hasInitData.value) return
  const okPin = await requestPinIfNeeded('chat_remove')
  if (!okPin) {
    if (shouldAskPinForAction('chat_remove')) {
      showToast(t('chats.toasts.pin_required'))
    }
    return
  }
  const kindLabel = isChannelRow(chat)
    ? t('chats.confirm.remove_kind_channel')
    : t('chats.confirm.remove_kind_group')
  const ok = window.confirm(
    t('chats.confirm.remove_title', { kind: kindLabel, title: chat.title || chat.id }),
  )
  if (!ok) return
  try {
    const data = await fetchSilent(() => api.removeChat(chat.id))
    chats.value = chats.value.filter((c) => c.id !== chat.id)
    if (selectedChatId.value === chat.id) {
      selectedChatId.value = data?.selected_chat_id ?? null
    }
    saveChatsCacheSnapshot()
    guardLog('Chats', 'removeChat OK', { removedId: chat.id })
  } catch (e) {
    guardWarn('Chats', 'removeChat failed', e)
  }
}

function goToProtection(chatId) {
  selectChat(chatId).then(() => router.push('/protection'))
}

function goToReports(chatId) {
  const isPerChat = !(chatId === undefined || chatId === null || chatId === '' || (typeof chatId === 'object' && !('id' in chatId)))
  if (isPerChat) {
    const row = (chats.value || []).find((c) => Number(c.id) === Number(chatId))
    setCabinetMode(isDelegatedCabinetChat(row) ? 'delegated' : 'owner')
    selectChat(chatId).catch(() => {})
    router.push({ path: '/reports', query: { chat_id: String(chatId) } })
    return
  }
  setCabinetMode('owner')
  router.push({ path: '/reports' })
}

function onChatActivationPremiumClick() {
  openLock({ feature: 'chat_activation_limit', me: lastMeForPremiumLock.value })
}

function onManagersPremiumClick() {
  openLock({ feature: 'chat_managers', me: lastMeForPremiumLock.value })
}

async function activatePendingFromEmpty() {
  if (!hasInitData.value) return
  pendingLoading.value = true
  try {
    const data = await fetchSilent(() => api.connectActivatePending())
    await loadChats()
    if (!data?.connected) {
      window.alert(
        Number(data?.skipped_rights || 0) > 0
          ? t('chats.toasts.bot_need_full_rights')
          : t('chats.toasts.bot_must_be_admin'),
      )
    }
  } finally {
    pendingLoading.value = false
  }
}

function protectionActive(chat) {
  return chat.master_anti_spam !== false
}

function ownerLabelPlain(chat) {
  if (!isDelegatedCabinetChat(chat)) return t('chats.role.mine')
  const u = (chat.owner_username || '').trim().replace(/^@+/, '')
  if (u) return u
  const n = (chat.owner_first_name || '').trim()
  if (n) return n
  return String(chat.owner_user_id || '').trim()
}

function openTelegramProfileFromUsername(raw) {
  const u = String(raw || '').trim().replace(/^@+/, '')
  if (!u) return
  const url = `https://t.me/${u}`
  const tg = window.Telegram?.WebApp
  try {
    if (typeof tg?.openTelegramLink === 'function') {
      tg.openTelegramLink(url)
      return
    }
  } catch {
    //
  }
  try {
    if (typeof tg?.openLink === 'function') {
      tg.openLink(url)
      return
    }
  } catch {
    //
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}

function sortChatsByAvailability(arr) {
  return [...(arr || [])].sort((a, b) => {
    const lockDiff = Number(!!a?.locked_by_limit) - Number(!!b?.locked_by_limit)
    if (lockDiff !== 0) return lockDiff
    return String(a?.title || '').localeCompare(String(b?.title || ''), 'ru')
  })
}

function isChannelRow(c) {
  return String(c?.chat_kind || 'group').toLowerCase() === 'channel'
}

function discussionTitleForChat(chat) {
  const id = Number(chat?.linked_discussion_chat_id || 0)
  const title = String(chat?.linked_discussion_title || '').trim()
  if (!title) return ''
  if (id && (title === String(id) || /^-?\d+$/.test(title))) return ''
  return title
}

function discussionLineForChat(chat) {
  const title = discussionTitleForChat(chat)
  if (title) return title
  const id = chat?.linked_discussion_chat_id
  return id ? `#${id}` : ''
}

const DISMISS_DISCUSSION_IDS_KEY = 'guard.dismissDiscussBanner.ids'

function loadDismissedDiscussionChannelIds() {
  try {
    const raw = localStorage.getItem(DISMISS_DISCUSSION_IDS_KEY)
    const arr = raw ? JSON.parse(raw) : []
    return new Set((Array.isArray(arr) ? arr : []).map(Number).filter((x) => x !== 0))
  } catch {
    return new Set()
  }
}

const dismissedDiscussionChannelIds = ref(loadDismissedDiscussionChannelIds())

function dismissDiscussionBanner(channelId) {
  const cid = Number(channelId || 0)
  if (!cid) return
  const next = new Set(dismissedDiscussionChannelIds.value)
  next.add(cid)
  dismissedDiscussionChannelIds.value = next
  try {
    localStorage.setItem(DISMISS_DISCUSSION_IDS_KEY, JSON.stringify([...next]))
  } catch {
    //
  }
}

const discussionConnectAlerts = computed(() => {
  const list = chats.value || []
  const dismissed = dismissedDiscussionChannelIds.value
  const byId = new Map(list.map((c) => [Number(c.id), c]))
  const out = []
  for (const c of list) {
    if (!isChannelRow(c)) continue
    const cid = Number(c.id || 0)
    if (!cid || dismissed.has(cid)) continue
    if (isDelegatedCabinetChat(c) && !delegatedCan(c, 'first_post_settings')) continue
    const did = Number(c.linked_discussion_chat_id || 0)
    if (!did) continue
    if (c.discussion_chat_connected || byId.has(did)) continue
    out.push({
      channelId: cid,
      channelTitle: String(c.title || '').trim() || String(cid),
      discussionTitle: discussionTitleForChat(c) || String(did),
    })
  }
  return out
})

/** Порядок: «Все» — делегаты → свои каналы → свои группы; «Мой» — каналы → группы; «Доступы» — группы → каналы делегата. */
const orderedDisplayRows = computed(() => {
  const list = chats.value || []
  if (delegatedChatsOnly.value) {
    return sortChatsByAvailability([...list])
  }
  if (cabinetTab.value === 'mine') {
    const own = list.filter((c) => !isDelegatedCabinetChat(c))
    return [
      ...sortChatsByAvailability(own.filter((c) => isChannelRow(c))),
      ...sortChatsByAvailability(own.filter((c) => !isChannelRow(c))),
    ]
  }
  if (cabinetTab.value === 'shared') {
    const sh = list.filter((c) => isDelegatedCabinetChat(c))
    return [
      ...sortChatsByAvailability(sh.filter((c) => !isChannelRow(c))),
      ...sortChatsByAvailability(sh.filter((c) => isChannelRow(c))),
    ]
  }
  const shared = list.filter((c) => isDelegatedCabinetChat(c))
  const own = list.filter((c) => !isDelegatedCabinetChat(c))
  return [
    ...sortChatsByAvailability(shared),
    ...sortChatsByAvailability(own.filter((c) => isChannelRow(c))),
    ...sortChatsByAvailability(own.filter((c) => !isChannelRow(c))),
  ]
})

const filteredByKindPreset = computed(() => {
  const r = orderedDisplayRows.value
  if (kindPreset.value === 'groups') return r.filter((c) => !isChannelRow(c))
  if (kindPreset.value === 'channels') return r.filter((c) => isChannelRow(c))
  return r
})

const frameDelegated = computed(() => {
  const list = filteredByKindPreset.value
  if (delegatedChatsOnly.value) return list
  return list.filter((c) => isDelegatedCabinetChat(c))
})
const frameOwnChannels = computed(() => {
  if (delegatedChatsOnly.value) return []
  return filteredByKindPreset.value.filter((c) => !isDelegatedCabinetChat(c) && isChannelRow(c))
})
const frameOwnGroups = computed(() => {
  if (delegatedChatsOnly.value) return []
  return filteredByKindPreset.value.filter((c) => !isDelegatedCabinetChat(c) && !isChannelRow(c))
})

const frameDelegatedHasThreat = computed(() => (frameDelegated.value || []).some((c) => !!chatSpikeAlert(c)))

/** Для навигации по «под угрозой» — тот же порядок, что на экране. */
function visibleChatsForThreatScroll() {
  return [...frameDelegated.value, ...frameOwnChannels.value, ...frameOwnGroups.value]
}

function sharedCabinetsCount() {
  return (chats.value || []).filter((c) => isDelegatedCabinetChat(c)).length
}

function chatCardClass(chat) {
  const spike = !!focusThreatOnly.value && !!chatSpikeAlert(chat)
  const spikeCls = spike ? 'ring-2 ring-yellow-400/45 shadow-[0_0_18px_-8px_rgba(250,204,21,0.5)]' : ''
  /** Карточка: прозрачное «стекло» на глобальном фоне, без засветления */
  const glass = 'rounded-xl bg-black/35 p-2.5 backdrop-blur-md'
  if (isChannelRow(chat)) {
    const tint = isDelegatedCabinetChat(chat) ? 'bg-violet-950/10' : 'bg-emerald-950/10'
    return [glass, tint, spikeCls]
  }
  const tint = isDelegatedCabinetChat(chat) ? 'bg-violet-950/10' : ''
  return [glass, tint, spikeCls]
}

async function openManagers(chat) {
  if (!chat?.id) return
  managersModalChat.value = chat
  managersLoading.value = true
  managersStats.value = null
  try {
    const [md, gs] = await Promise.all([
      api.chatManagers(chat.id),
      api.activityGroupBreakdown(chat.id, { hours: 24 * 7 }).catch(() => null),
    ])
    managersData.value = {
      managers: [],
      can_manage_access: false,
      limit: 3,
      chat_kind: 'group',
      ...(md && typeof md === 'object' ? md : {}),
    }
    managersStats.value = gs
    if (managersPollTimer) clearInterval(managersPollTimer)
    managersPollTimer = setInterval(async () => {
      if (!managersModalChat.value?.id) return
      try {
        const row = await api.chatManagers(managersModalChat.value.id)
        managersData.value = {
          ...managersData.value,
          ...(row && typeof row === 'object' ? row : {}),
        }
      } catch {
        //
      }
    }, 7000)
  } catch (e) {
    guardWarn('Chats', 'openManagers failed', e)
    showToast(messageFromApiError(e))
    closeManagers()
  } finally {
    managersLoading.value = false
  }
}

function closeManagers() {
  if (managersPollTimer) {
    clearInterval(managersPollTimer)
    managersPollTimer = null
  }
  managersModalChat.value = null
  managersStats.value = null
  _resetAddManagerForm()
}

async function _tryWriteClipboard(text) {
  if (!text) return false
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // продолжаем к fallback
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

async function copyInviteLink(inv) {
  const link = inv?.invite_link || ''
  if (!link) return
  const ok = await _tryWriteClipboard(link)
  showToast(ok ? t('chats.managers.invite_link_copied') : t('chats.managers.invite_link_copy_failed'))
}

function managerActivityBadgeClass(m) {
  // Тонировка бейджа по «свежести» активности:
  // - emerald  — делал что-то за 7 дней;
  // - zinc     — ничего не делал за 7 дней, но запись существует;
  // - rose     — добавлен >7 дней назад и ноль действий за 30 дней (потенциальный «мертвый» делегат).
  const n7 = Number(m?.actions_7d || 0)
  const n30 = Number(m?.actions_30d || 0)
  if (n7 > 0) return 'bg-emerald-500/15 text-emerald-200 hover:bg-emerald-500/25'
  if (n30 === 0) {
    const created = m?.created_at ? Date.parse(m.created_at) : NaN
    if (!Number.isNaN(created) && Date.now() - created > 7 * 24 * 60 * 60 * 1000) {
      return 'bg-rose-500/15 text-rose-200 hover:bg-rose-500/25'
    }
  }
  return 'bg-white/[0.04] text-zinc-300 hover:bg-white/[0.08]'
}

function managerActivityTitle(m) {
  const last = m?.last_action_at
  const n30 = Number(m?.actions_30d || 0)
  const parts = []
  parts.push(t('chats.managers.actions_30d', { n: n30 }))
  if (last) parts.push(t('chats.managers.last_action_at', { ts: formatLocalDate(last) }))
  else parts.push(t('chats.managers.never_acted'))
  return parts.join(' · ')
}

function formatLocalDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  try {
    return d.toLocaleString(isEn?.value ? 'en-GB' : 'ru-RU', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function auditActionLabel(kind) {
  // Ключи должны совпадать с _MANAGER_ACTION_KINDS в routes.py.
  const map = {
    manager_added: t('chats.managers.audit_kinds.manager_added'),
    manager_removed: t('chats.managers.audit_kinds.manager_removed'),
    manager_perms_updated: t('chats.managers.audit_kinds.manager_perms_updated'),
    manager_invite_created: t('chats.managers.audit_kinds.manager_invite_created'),
    manager_invite_cancelled: t('chats.managers.audit_kinds.manager_invite_cancelled'),
    manager_invite_accepted: t('chats.managers.audit_kinds.manager_invite_accepted'),
    rule_patched: t('chats.managers.audit_kinds.rule_patched'),
  }
  return map[kind] || kind
}

function auditActionIcon(kind) {
  const map = {
    manager_added: '➕',
    manager_removed: '🚫',
    manager_perms_updated: '🔧',
    manager_invite_created: '🔗',
    manager_invite_cancelled: '❌',
    manager_invite_accepted: '✅',
    rule_patched: '🛡',
  }
  return map[kind] || '·'
}

async function openAuditModal(filterUserId = null) {
  auditFilterUserId.value = filterUserId ? Number(filterUserId) : null
  auditItems.value = []
  auditTotal.value = 0
  auditOffset.value = 0
  auditUserActivity.value = null
  auditModalOpen.value = true
  await loadAudit({ reset: true })
}

function closeAuditModal() {
  auditModalOpen.value = false
  auditFilterUserId.value = null
  auditItems.value = []
  auditUserActivity.value = null
}

async function loadAudit({ reset = false } = {}) {
  if (!managersModalChat.value?.id) return
  const chatId = managersModalChat.value.id
  auditLoading.value = true
  try {
    if (auditFilterUserId.value) {
      // По одному делегату: отдельный эндпоинт со статистикой за 7д/30д + recent[10].
      const res = await fetchSilent(() => api.chatManagerActivity(chatId, auditFilterUserId.value))
      auditUserActivity.value = {
        last_action_at: res?.last_action_at || null,
        actions_7d: Number(res?.actions_7d || 0),
        actions_30d: Number(res?.actions_30d || 0),
      }
      auditItems.value = Array.isArray(res?.recent) ? res.recent : []
      auditTotal.value = auditItems.value.length
      auditOffset.value = auditItems.value.length
    } else {
      const offset = reset ? 0 : auditOffset.value
      const res = await fetchSilent(() => api.chatAudit(chatId, { limit: _AUDIT_PAGE_SIZE, offset }))
      const items = Array.isArray(res?.items) ? res.items : []
      auditItems.value = reset ? items : [...auditItems.value, ...items]
      auditTotal.value = Number(res?.total || auditItems.value.length)
      auditOffset.value = auditItems.value.length
    }
  } catch (e) {
    if (!reset) {
      // Тихо игнорируем при подгрузке — пользователь увидит «больше нет данных».
    } else {
      showToast(messageFromApiError(e))
    }
  } finally {
    auditLoading.value = false
  }
}

function auditCanLoadMore() {
  if (auditFilterUserId.value) return false
  return auditItems.value.length < auditTotal.value
}

function managerExpiresMeta(iso) {
  if (!iso) return null
  const ts = Date.parse(iso)
  if (Number.isNaN(ts)) return null
  const diffMs = ts - Date.now()
  if (diffMs <= 0) {
    return { label: t('chats.managers.expires_passed'), tone: 'rose' }
  }
  const minutes = Math.round(diffMs / 60000)
  const hours = Math.round(minutes / 60)
  const days = Math.round(hours / 24)
  let label
  if (minutes < 60) label = t('chats.managers.expires_minutes', { n: minutes })
  else if (hours < 24) label = t('chats.managers.expires_hours', { n: hours })
  else label = t('chats.managers.expires_days', { n: days })
  let tone = 'zinc'
  if (diffMs < 24 * 60 * 60 * 1000) tone = 'amber'
  if (diffMs < 2 * 60 * 60 * 1000) tone = 'rose'
  return { label, tone }
}

async function addManager() {
  if (!managersModalChat.value?.id) return
  const raw = String(addManagerValue.value || '').trim()
  if (!raw) return
  if (!canSubmitNewManager.value) {
    window.alert(t('chats.toasts.pick_perms'))
    return
  }
  const base = raw.startsWith('@') || Number.isNaN(Number(raw))
    ? { username: raw }
    : { telegram_id: Number(raw) }
  const p = addManagerPerms.value || {}
  const permissions = isManagersChannel.value
    ? { broadcast: !!p.broadcast, first_post_settings: !!p.first_post_settings }
    : { protection: !!p.protection, broadcast: !!p.broadcast, reports: !!(p.reports || p.stats) }
  const payload = { ...base, permissions }
  if (addManagerAsLink.value) payload.as_invite_link = true
  managersLoading.value = true
  try {
    const res = await fetchSilent(() => api.chatManagerAdd(managersModalChat.value.id, payload))
    managersData.value = { ...managersData.value, ...res }
    if (res?.created_status === 'pending_link' && res?.new_invite_link) {
      const ok = await _tryWriteClipboard(res.new_invite_link)
      showToast(ok ? t('chats.managers.invite_link_copied') : t('chats.managers.invite_link_created'))
    }
    _resetAddManagerForm()
    await loadChats()
  } catch (e) {
    const d = e?.body?.detail || e?.message || t('chats.toasts.add_admin_failed')
    window.alert(String(d))
  } finally {
    managersLoading.value = false
  }
}

function onAddManagerPrimaryClick() {
  addManagerPermsOpen.value = true
}
function onAddManagerInputEnter() {
  if (!String(addManagerValue.value || '').trim()) return
  if (!addManagerPermsOpen.value) {
    addManagerPermsOpen.value = true
    return
  }
  if (canSubmitNewManager.value) void addManager()
}

async function removeManager(uid) {
  if (!managersModalChat.value?.id || !uid) return
  managersLoading.value = true
  try {
    const res = await fetchSilent(() => api.chatManagerRemove(managersModalChat.value.id, uid))
    managersData.value = { ...managersData.value, ...res }
    await loadChats()
  } finally {
    managersLoading.value = false
  }
}

async function _patchManagerPerm(manager, key, value) {
  if (!managersModalChat.value?.id || !manager?.user_id || !key) return
  const base = manager?.permissions || {}
  const nextPerms = {
    protection: !!base.protection,
    broadcast: !!base.broadcast,
    reports: !!base.reports,
    first_post_settings: !!base.first_post_settings,
  }
  nextPerms[key] = !!value
  managersLoading.value = true
  try {
    const res = await fetchSilent(() => api.chatManagerUpdate(managersModalChat.value.id, manager.user_id, { permissions: nextPerms }))
    managersData.value = { ...managersData.value, ...res }
    await loadChats()
  } finally {
    managersLoading.value = false
  }
}

async function removeManagerPermission(manager, key) {
  await _patchManagerPerm(manager, key, false)
}

async function addManagerPermission(manager, key) {
  await _patchManagerPerm(manager, key, true)
}

async function cancelInvite(inviteId) {
  if (!managersModalChat.value?.id || !inviteId) return
  managersLoading.value = true
  try {
    const res = await fetchSilent(() => api.chatManagerInviteCancel(managersModalChat.value.id, inviteId))
    managersData.value = { ...managersData.value, ...res }
  } finally {
    managersLoading.value = false
  }
}

function inviteStatusLabel(s) {
  const v = String(s || '').toLowerCase()
  if (v === 'connected') return t('chats.invite_status.connected')
  if (v === 'connecting') return t('chats.invite_status.connecting')
  return t('chats.invite_status.sent')
}

function canOpenManagers(chat) {
  return !isDelegatedCabinetChat(chat) && !!isPremium.value
}

function openDelegatedBroadcast(chatId) {
  setCabinetMode('delegated')
  try {
    localStorage.setItem('guard.delegated.broadcast.chat_id', String(chatId))
  } catch {
    //
  }
  const nav = router.push({ path: '/admin', query: { cabinet: 'delegated', tab: 'broadcasts' } })
  if (nav && typeof nav.catch === 'function') {
    nav.catch((err) => {
      const n = String(err?.name || err || '')
      if (n.includes('duplicat') || n.includes('NavigationDuplicated')) return
      guardWarn('Chats', 'openDelegatedBroadcast: navigate', err)
    })
  }
}

function openChannelBroadcast(chat) {
  if (!chat?.id) return
  setCabinetMode(isDelegatedCabinetChat(chat) ? 'delegated' : 'owner')
  try {
    localStorage.setItem('guard.broadcast.open_channel_id', String(Number(chat.id)))
  } catch {
    //
  }
  const q = { tab: 'broadcasts' }
  if (isDelegatedCabinetChat(chat)) q.cabinet = 'delegated'
  const nav = router.push({ path: '/admin', query: q })
  if (nav && typeof nav.catch === 'function') {
    nav.catch((err) => {
      const n = String(err?.name || err || '')
      if (n.includes('duplicat') || n.includes('NavigationDuplicated')) return
      guardWarn('Chats', 'openChannelBroadcast: navigate', err)
    })
  }
}
</script>

<template>
  <div class="space-y-5">
    <h1 class="text-xl font-semibold text-gray-900 dark:text-white md:text-2xl">{{ t('chats.title') }}</h1>

    <div v-if="!hasInitData" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
      {{ t('chats.init_required') }}
    </div>

    <div v-else-if="error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
      {{ error }}
    </div>

    <div
      v-else-if="chatsFirstLoad && !chats.length"
      class="relative overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-br from-slate-900/88 via-slate-950/90 to-black/95 p-6 text-center text-slate-100 shadow-[0_16px_50px_-16px_rgba(0,0,0,0.85)] backdrop-blur-xl ring-1 ring-white/10"
      aria-busy="true"
    >
      <div class="mx-auto mb-3 inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/8 px-3 py-1.5 text-xs font-semibold text-slate-100 shadow-[0_0_20px_-10px_rgba(255,255,255,0.35)]">
        <span class="inline-block hourglass-flip">⏳</span>
        {{ delegatedChatsOnly ? t('chats.loading_delegated') : t('chats.loading') }}
      </div>
      <div class="space-y-2.5">
        <div class="mx-auto h-3 w-2/3 max-w-[14rem] animate-pulse rounded bg-white/15" />
        <div class="h-20 animate-pulse rounded-xl bg-white/10" />
        <div class="h-20 animate-pulse rounded-xl bg-white/10" />
      </div>
    </div>

    <div v-else-if="!chats.length" class="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
      <p class="text-gray-600 dark:text-gray-400">{{ t('chats.empty') }}</p>
      <p class="mt-2 text-sm text-gray-500 dark:text-gray-500">{{ t('chats.empty_hint') }}</p>
      <div class="mt-4 flex flex-wrap gap-2">
        <button
          v-if="pendingCount > 0"
          type="button"
          class="guard-green-soft rounded-lg px-3 py-1.5 text-sm font-semibold disabled:opacity-50"
          :disabled="pendingLoading"
          @click="activatePendingFromEmpty"
        >
          {{ t('chats.pending_connect', { count: pendingCount }) }}
        </button>
        <button
          type="button"
          class="rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700"
          @click="router.push('/connect')"
        >
          {{ t('chats.open_panel') }}
        </button>
      </div>
    </div>

    <div v-else class="-mx-4 space-y-3 px-4 pb-10 md:-mx-6 md:px-6">
      <div
        v-for="row in discussionConnectAlerts"
        :key="`disc-prompt-${row.channelId}`"
        class="rounded-xl border border-emerald-400/35 bg-emerald-950/40 px-3 py-3 text-[12px] text-emerald-50 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] ring-1 ring-emerald-500/15"
      >
        <p class="font-semibold text-emerald-100">{{ t('chats.discussion_banner_title') }}</p>
        <p class="mt-1 leading-snug text-emerald-50/95">
          {{
            t('chats.discussion_banner_body', {
              channel: row.channelTitle,
              discussion: row.discussionTitle,
            })
          }}
        </p>
        <div class="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            class="guard-green-soft rounded-lg px-3 py-2 text-xs font-bold text-slate-900"
            @click="router.push({ path: '/connect', query: { kind: 'group' } })"
          >
            {{ t('chats.discussion_banner_cta') }}
          </button>
          <button
            type="button"
            class="rounded-lg border border-white/15 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:bg-white/10"
            @click="dismissDiscussionBanner(row.channelId)"
          >
            {{ t('chats.discussion_banner_dismiss') }}
          </button>
        </div>
      </div>
      <div class="rounded-xl border border-white/[0.08] bg-black/30 px-2.5 py-2 backdrop-blur-md">
        <div v-if="!delegatedChatsOnly" class="mb-1.5 flex flex-wrap gap-1">
          <button type="button" class="rounded-lg px-2 py-1 text-[11px] font-semibold"
            :class="cabinetTab==='all' ? 'guard-green-soft' : 'border border-white/20 bg-white/10 text-slate-100'"
            @click="cabinetTab='all'">
            {{ t('chats.tabs.all') }}
          </button>
          <button type="button" class="rounded-lg px-2 py-1 text-[11px] font-semibold"
            :class="cabinetTab==='mine' ? 'guard-green-soft' : 'border border-white/20 bg-white/10 text-slate-100'"
            @click="cabinetTab='mine'">
            {{ t('chats.tabs.mine') }}
          </button>
          <button type="button" class="rounded-lg px-2 py-1 text-[11px] font-semibold"
            :class="cabinetTab==='shared' ? 'guard-green-soft' : 'border border-white/20 bg-white/10 text-slate-100'"
            @click="cabinetTab='shared'">
            {{ t('chats.tabs.shared') }}
          </button>
          <button
            type="button"
            class="inline-flex h-6 min-w-6 items-center justify-center rounded-full border border-sky-400/35 bg-sky-950/25 px-1.5 text-[10px] font-extrabold text-sky-200"
            @click="showCabinetInfoModal = true"
          >
            i
          </button>
        </div>
        <div class="flex flex-wrap items-center gap-1">
          <button
            type="button"
            class="rounded-lg px-2 py-1 text-[10px] font-semibold"
            :class="[
              kindPreset === 'all' ? 'guard-green-soft' : '',
              delegatedChatsOnly
                ? kindPreset !== 'all'
                  ? 'border border-violet-400/25 bg-violet-950/30 text-violet-100'
                  : ''
                : kindPreset !== 'all'
                  ? 'border border-white/15 bg-white/8 text-slate-200'
                  : '',
            ]"
            @click="kindPreset = 'all'"
          >
            {{ t('chats.presets.all') }}
          </button>
          <button
            type="button"
            class="rounded-lg px-2 py-1 text-[10px] font-semibold"
            :class="[
              kindPreset === 'groups' ? 'guard-green-soft' : '',
              delegatedChatsOnly
                ? kindPreset !== 'groups'
                  ? 'border border-violet-400/25 bg-violet-950/30 text-violet-100'
                  : ''
                : kindPreset !== 'groups'
                  ? 'border border-white/15 bg-white/8 text-slate-200'
                  : '',
            ]"
            @click="kindPreset = 'groups'"
          >
            {{ t('chats.presets.groups') }}
          </button>
          <button
            type="button"
            class="rounded-lg px-2 py-1 text-[10px] font-semibold"
            :class="[
              kindPreset === 'channels' ? 'guard-green-soft' : '',
              delegatedChatsOnly
                ? kindPreset !== 'channels'
                  ? 'border border-violet-400/25 bg-violet-950/30 text-violet-100'
                  : ''
                : kindPreset !== 'channels'
                  ? 'border border-white/15 bg-white/8 text-slate-200'
                  : '',
            ]"
            @click="kindPreset = 'channels'"
          >
            {{ t('chats.presets.channels') }}
          </button>
          <button
            v-if="delegatedChatsOnly"
            type="button"
            class="ml-auto inline-flex h-6 min-w-6 items-center justify-center rounded-full border border-violet-300/40 bg-violet-900/35 px-1.5 text-[10px] font-extrabold text-violet-100"
            aria-label="Что такое фиолетовый ADM"
            @click="showDelegatedInfoModal = true"
          >
            i
          </button>
        </div>
        <div v-if="delegatedChatsOnly && (kindPreset === 'all' || kindPreset === 'groups')" class="mb-2">
          <button
            type="button"
            class="inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-violet-400/35 bg-violet-500/10 px-3 py-1.5 text-[11px] font-semibold text-violet-100 transition hover:bg-violet-500/15"
            @click="goToReports"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M4 4h12l4 4v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z" /><path d="M16 4v4h4" /><path d="M7 14h10M7 18h6M7 10h4" />
            </svg>
            {{ t('chats.actions.group_reports') }}
          </button>
        </div>
      </div>
        <div v-if="cabinetTab === 'shared' && !delegatedChatsOnly" class="rounded-xl border border-white/[0.08] bg-black/30 p-2.5 backdrop-blur-md">
          <div class="flex items-center justify-between gap-2">
            <div>
              <p class="text-sm font-semibold text-white">{{ isEn ? 'Admins and access' : 'Админы и доступы' }}</p>
              <p class="text-[11px] text-slate-300">{{ isEn ? 'Available on Premium and only to the cabinet owner.' : 'Настройка доступна в Premium и только владельцу кабинета.' }}</p>
            </div>
            <span class="rounded-full border border-violet-400/25 bg-violet-500/12 px-2 py-0.5 text-[10px] font-semibold text-violet-200/95">
              {{ (isEn ? 'Access:' : 'Доступы:') }} {{ sharedCabinetsCount() }}
            </span>
          </div>
        </div>
        <p
          v-if="chats.length && !frameDelegated.length && !frameOwnChannels.length && !frameOwnGroups.length"
          class="rounded-lg border border-white/[0.08] bg-black/35 px-2 py-2 text-center text-[11px] text-slate-300 backdrop-blur-sm"
        >
          {{ t('chats.presets.empty') }}
        </p>

        <div v-if="frameDelegated.length" class="mb-5 space-y-2">
          <div
            class="relative flex items-center justify-between gap-2 overflow-hidden rounded-xl border border-violet-500/30 bg-gradient-to-r from-violet-950/55 via-black/40 to-transparent px-3 py-2 shadow-[0_0_28px_-10px_rgba(139,92,246,0.4)] backdrop-blur-md"
          >
            <span
              class="pointer-events-none absolute left-0 top-0 h-full w-[3px] bg-gradient-to-b from-violet-200/90 via-fuchsia-400/70 to-violet-600/40"
              aria-hidden="true"
            />
            <span
              class="pl-2 text-[11px] font-extrabold uppercase leading-tight tracking-[0.16em] text-violet-50 drop-shadow-[0_0_14px_rgba(167,139,250,0.55)]"
            >
              {{ cabinetTab === 'shared' || delegatedChatsOnly ? t('chats.sections.delegated_long') : t('chats.sections.delegated') }}
            </span>
            <span
              v-if="frameDelegatedHasThreat"
              class="relative inline-flex items-center justify-center"
              :title="isEn ? 'A delegated cabinet has a chat at risk' : 'В делегированном кабинете есть чат под угрозой'"
            >
              <span class="absolute inline-flex h-3.5 w-3.5 animate-ping rounded-full bg-yellow-400/40" />
              <span class="relative text-[11px] leading-none text-yellow-300">⚠</span>
            </span>
          </div>
          <div v-for="chat in frameDelegated" :key="'fd-' + chat.id" :data-chat-id="chat.id" :class="chatCardClass(chat)">
            <div class="flex items-start gap-3">
              <ChatAvatar
                :chat-id="chat.id"
                :title="chat.title || String(chat.id)"
                :username="chat.username || ''"
                size-class="h-11 w-11"
                text-class="text-[14px] font-bold"
              />
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-bold leading-tight text-white">{{ chat.title }}</p>
                <div class="mt-0.5 flex flex-wrap items-center gap-1">
                  <template v-if="(chat.owner_username || '').trim()">
                    <span class="text-[10px] text-slate-300">{{ t('chats.labels.cabinet') }}</span>
                    <button
                      type="button"
                      class="text-[10px] font-semibold text-cyan-300 underline decoration-cyan-500/40"
                      @click="openTelegramProfileFromUsername(chat.owner_username)"
                    >
                      @{{ String(chat.owner_username).replace(/^@+/, '') }}
                    </button>
                  </template>
                  <p v-else class="text-[10px] text-slate-300">{{ t('chats.labels.cabinet') }} {{ ownerLabelPlain(chat) }}</p>
                  <span
                    v-if="isChannelRow(chat)"
                    class="rounded-full border border-emerald-400/40 bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-emerald-100"
                  >{{ t('chats.labels.channel') }}</span>
                  <span
                    v-else
                    class="rounded-full border border-violet-400/35 bg-violet-500/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-violet-100"
                  >{{ t('chats.labels.group') }}</span>
                  <span
                    v-if="chatSpikeAlert(chat)"
                    class="rounded-full border border-yellow-400/45 bg-yellow-500/20 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-yellow-100"
                  >{{ t('chats.labels.threat') }}</span>
                </div>
                <p
                  v-if="isChannelRow(chat) && (chat.linked_discussion_title || chat.linked_discussion_chat_id)"
                  class="mt-0.5 text-[10px] text-slate-400"
                >
                  {{ t('chats.labels.discussion') }}
                  <span class="font-medium text-slate-200">{{ discussionLineForChat(chat) }}</span>
                </p>
                <p v-if="chat.locked_by_limit" class="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-300">{{ t('chats.labels.free_limit') }}</p>
                <p v-else-if="protectionActive(chat)" class="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-lime-300">
                  {{ isChannelRow(chat) ? t('chats.labels.connected') : t('chats.labels.active') }}
                </p>
                <p v-else class="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-400">{{ t('chats.labels.inactive') }}</p>
                <p v-if="delegatedPermissionsLine(chat)" class="mt-1 text-[10px] leading-snug text-violet-200/95">
                  <span class="font-semibold text-violet-100">{{ t('chats.delegate_access_label') }}</span>
                  {{ delegatedPermissionsLine(chat) }}
                </p>
              </div>
              <button
                v-if="!chat.locked_by_limit"
                type="button"
                class="shrink-0 rounded-lg border border-red-500/35 bg-red-950/25 px-2 py-1 text-xs text-red-200 hover:bg-red-950/40"
                :aria-label="isChannelRow(chat) ? t('chats.labels.remove_channel') : t('chats.labels.remove_group')"
                @click="removeChat(chat)"
              >✕</button>
            </div>
            <div class="mt-2 flex flex-wrap gap-1 border-t border-white/10 pt-2">
              <template v-if="isChannelRow(chat)">
                <button
                  v-if="!chat.locked_by_limit && delegatedCan(chat, 'broadcast')"
                  type="button"
                  class="guard-green-soft rounded-lg px-2 py-1 text-[11px] font-semibold leading-tight"
                  @click="openChannelBroadcast(chat)"
                >{{ t('chats.actions.broadcast') }}</button>
                <button
                  v-if="!chat.locked_by_limit && delegatedCan(chat, 'first_post_settings')"
                  type="button"
                  class="rounded-lg border border-slate-700/70 bg-zinc-900/75 px-2 py-1 text-[11px] font-semibold leading-tight text-slate-100 hover:bg-zinc-800/80"
                  @click="openChannelPostRules(chat)"
                >{{ t('chats.actions.settings') }}</button>
                <button
                  v-if="canManageAutoApprove(chat)"
                  type="button"
                  :class="autoApproveButtonClass(chat)"
                  @click="openAutoApproveModal(chat)"
                >{{ t('chats.actions.auto_approve') }}</button>
                <button
                  v-if="chat.locked_by_limit"
                  type="button"
                  class="inline-flex items-center gap-1 rounded-lg border border-amber-400/40 bg-amber-900/30 px-2 py-1 text-[11px] font-semibold leading-tight text-amber-100"
                  @click="onChatActivationPremiumClick"
                >
                  <PremiumLockBadge variant="crown" size="xs" />
                  <span>💳 Premium</span>
                </button>
              </template>
              <template v-else>
                <button
                  v-if="!chat.locked_by_limit && delegatedCan(chat, 'protection')"
                  type="button"
                  class="guard-green-soft rounded-lg px-2 py-1 text-[11px] font-semibold leading-tight"
                  @click="goToProtection(chat.id)"
                >{{ t('chats.actions.protection') }} <span v-if="chatSpikeAlert(chat)">⚠</span></button>
                <button
                  v-else-if="chat.locked_by_limit"
                  type="button"
                  class="inline-flex items-center gap-1 rounded-lg border border-amber-400/40 bg-amber-900/30 px-2 py-1 text-[11px] font-semibold leading-tight text-amber-100"
                  @click="onChatActivationPremiumClick"
                >
                  <PremiumLockBadge variant="crown" size="xs" />
                  <span>{{ t('chats.actions.protection_premium') }}</span>
                </button>
                <button
                  v-if="delegatedCan(chat, 'broadcast')"
                  type="button"
                  class="rounded-lg border border-violet-400/35 bg-violet-900/30 px-2 py-1 text-[11px] font-semibold leading-tight text-violet-200"
                  @click="openDelegatedBroadcast(chat.id)"
                >{{ t('chats.actions.groups_broadcast') }}</button>
                <button
                  v-if="canManageAutoApprove(chat)"
                  type="button"
                  :class="autoApproveButtonClass(chat)"
                  @click="openAutoApproveModal(chat)"
                >{{ t('chats.actions.auto_approve') }}</button>
              </template>
              <button
                v-if="canOpenManagers(chat)"
                type="button"
                class="inline-flex min-w-0 max-w-full items-center justify-center gap-1 rounded-lg border border-slate-700/70 bg-zinc-900/75 px-2.5 py-1 text-[11px] font-semibold leading-tight text-slate-100 hover:bg-zinc-800/80"
                @click="openManagers(chat)"
              >
                <span>{{ t('chats.actions.managers') }}</span>
                <span v-if="(Number(chat.managers_count) || 0) > 0" class="min-w-[1.1rem] shrink-0 tabular-nums text-cyan-200/95">{{ Number(chat.managers_count) || 0 }}</span>
              </button>
              <button
                v-if="!chat.locked_by_limit && !isChannelRow(chat) && delegatedCan(chat, 'reports')"
                type="button"
                class="rounded-lg border border-slate-700/70 bg-zinc-900/75 px-2 py-1 text-[11px] font-semibold leading-tight text-slate-100 hover:bg-zinc-800/80"
                @click="goToReports(chat.id)"
              >{{ chat.log_chat_id ? t('chats.actions.reports_done') : t('chats.actions.reports') }}</button>
            </div>
          </div>
        </div>

        <div v-if="frameOwnChannels.length" class="mb-5 space-y-2">
          <div
            class="relative overflow-hidden rounded-xl border border-lime-400/35 bg-gradient-to-r from-emerald-950/50 via-black/40 to-transparent px-3 py-2 shadow-[0_0_28px_-10px_rgba(163,255,0,0.25)] backdrop-blur-md"
          >
            <span
              class="pointer-events-none absolute left-0 top-0 h-full w-[3px] bg-gradient-to-b from-lime-300/95 via-emerald-400/70 to-lime-600/35"
              aria-hidden="true"
            />
            <span
              class="block pl-2 text-[11px] font-extrabold uppercase leading-tight tracking-[0.16em] text-lime-50 drop-shadow-[0_0_14px_rgba(163,255,0,0.4)]"
            >{{ t('chats.sections.channels_mine') }}</span>
          </div>
          <div v-for="chat in frameOwnChannels" :key="'oc-' + chat.id" :data-chat-id="chat.id" :class="chatCardClass(chat)">
            <div class="flex items-start gap-3">
              <ChatAvatar
                :chat-id="chat.id"
                :title="chat.title || String(chat.id)"
                :username="chat.username || ''"
                size-class="h-11 w-11"
                text-class="text-[14px] font-bold"
              />
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-bold leading-tight text-white">{{ chat.title }}</p>
                <div class="mt-0.5 flex flex-wrap items-center gap-1">
                  <p class="text-[10px] text-slate-300">{{ t('chats.labels.my_cabinet') }}</p>
                  <span class="rounded-full border border-emerald-400/40 bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-emerald-100">{{ t('chats.labels.channel') }}</span>
                </div>
                <p v-if="chat.linked_discussion_title || chat.linked_discussion_chat_id" class="mt-0.5 text-[10px] text-slate-400">
                  {{ t('chats.labels.discussion') }}
                  <span class="font-medium text-slate-200">{{ discussionLineForChat(chat) }}</span>
                </p>
                <p v-if="chat.locked_by_limit" class="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-300">{{ t('chats.labels.free_limit') }}</p>
                <p v-else-if="protectionActive(chat)" class="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-lime-300">{{ t('chats.labels.connected') }}</p>
                <p v-else class="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-400">{{ t('chats.labels.inactive') }}</p>
              </div>
              <button
                v-if="!chat.locked_by_limit"
                type="button"
                class="shrink-0 rounded-lg border border-red-500/35 bg-red-950/25 px-2 py-1 text-xs text-red-200"
                :aria-label="t('chats.labels.remove_channel')"
                @click="removeChat(chat)"
              >✕</button>
            </div>
            <div class="mt-2 flex flex-wrap gap-1 border-t border-white/10 pt-2">
              <button
                v-if="!chat.locked_by_limit"
                type="button"
                class="guard-green-soft rounded-lg px-2 py-1 text-[11px] font-semibold leading-tight"
                @click="openChannelBroadcast(chat)"
              >{{ t('chats.actions.broadcast') }}</button>
              <button
                v-if="!chat.locked_by_limit"
                type="button"
                class="rounded-lg border border-slate-700/70 bg-zinc-900/75 px-2 py-1 text-[11px] font-semibold leading-tight text-slate-100 hover:bg-zinc-800/80"
                @click="openChannelPostRules(chat)"
              >{{ t('chats.actions.settings') }}</button>
              <button
                v-if="canManageAutoApprove(chat)"
                type="button"
                :class="autoApproveButtonClass(chat)"
                @click="openAutoApproveModal(chat)"
              >{{ t('chats.actions.auto_approve') }}</button>
              <button
                v-if="chat.locked_by_limit"
                type="button"
                class="inline-flex items-center gap-1 rounded-lg border border-amber-400/40 bg-amber-900/30 px-2 py-1 text-[11px] font-semibold leading-tight text-amber-100"
                @click="onChatActivationPremiumClick"
              >
                <PremiumLockBadge variant="crown" size="xs" />
                <span>💳 Premium</span>
              </button>
              <button
                v-if="canOpenManagers(chat)"
                type="button"
                class="inline-flex min-w-0 max-w-full items-center justify-center gap-1 rounded-lg border border-slate-700/70 bg-zinc-900/75 px-2.5 py-1 text-[11px] font-semibold leading-tight text-slate-100"
                @click="openManagers(chat)"
              >
                <span>{{ t('chats.actions.managers') }}</span>
                <span v-if="(Number(chat.managers_count) || 0) > 0" class="min-w-[1.1rem] shrink-0 tabular-nums text-cyan-200/95">{{ Number(chat.managers_count) || 0 }}</span>
              </button>
              <button
                v-else
                type="button"
                class="inline-flex items-center gap-1 rounded-lg border border-amber-400/35 bg-amber-900/25 px-2 py-1 text-[11px] font-semibold leading-tight text-amber-200"
                @click="onManagersPremiumClick"
              >
                <PremiumLockBadge variant="crown" size="xs" />
                <span>{{ t('chats.actions.managers_premium') }}</span>
              </button>
            </div>
          </div>
        </div>

        <div v-if="frameOwnGroups.length" class="space-y-2">
          <div
            class="relative overflow-hidden rounded-xl border border-cyan-400/35 bg-gradient-to-r from-cyan-950/45 via-black/40 to-transparent px-3 py-2 shadow-[0_0_28px_-10px_rgba(34,211,238,0.28)] backdrop-blur-md"
          >
            <span
              class="pointer-events-none absolute left-0 top-0 h-full w-[3px] bg-gradient-to-b from-cyan-200/90 via-sky-400/65 to-cyan-600/35"
              aria-hidden="true"
            />
            <span
              class="block pl-2 text-[11px] font-extrabold uppercase leading-tight tracking-[0.16em] text-cyan-50 drop-shadow-[0_0_14px_rgba(34,211,238,0.45)]"
            >{{ t('chats.sections.groups_mine') }}</span>
          </div>
          <div v-for="chat in frameOwnGroups" :key="'og-' + chat.id" :data-chat-id="chat.id" :class="chatCardClass(chat)">
            <div class="flex items-start gap-3">
              <ChatAvatar
                :chat-id="chat.id"
                :title="chat.title || String(chat.id)"
                :username="chat.username || ''"
                size-class="h-11 w-11"
                text-class="text-[14px] font-bold"
              />
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-bold leading-tight text-white">{{ chat.title }}</p>
                <div class="mt-0.5 flex flex-wrap items-center gap-1">
                  <p class="text-[10px] text-slate-300">{{ t('chats.labels.my_cabinet') }}</p>
                  <span
                    v-if="chatSpikeAlert(chat)"
                    class="rounded-full border border-yellow-400/45 bg-yellow-500/20 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-yellow-100"
                  >{{ t('chats.labels.threat') }}</span>
                </div>
                <p v-if="chat.locked_by_limit" class="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-300">{{ t('chats.labels.free_limit') }}</p>
                <p v-else-if="protectionActive(chat)" class="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-lime-300">{{ t('chats.labels.active') }}</p>
                <p v-else class="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-400">{{ t('chats.labels.inactive') }}</p>
              </div>
              <button
                v-if="!chat.locked_by_limit"
                type="button"
                class="shrink-0 rounded-lg border border-red-500/35 bg-red-950/25 px-2 py-1 text-xs text-red-200"
                :aria-label="t('chats.labels.remove_group')"
                @click="removeChat(chat)"
              >✕</button>
            </div>
            <div class="mt-2 flex flex-wrap gap-1 border-t border-white/10 pt-2">
              <button
                v-if="!chat.locked_by_limit"
                type="button"
                class="guard-green-soft rounded-lg px-2 py-1 text-[11px] font-semibold leading-tight"
                @click="goToProtection(chat.id)"
              >{{ t('chats.actions.protection') }} <span v-if="chatSpikeAlert(chat)">⚠</span></button>
              <button
                v-else-if="chat.locked_by_limit"
                type="button"
                class="inline-flex items-center gap-1 rounded-lg border border-amber-400/40 bg-amber-900/30 px-2 py-1 text-[11px] font-semibold leading-tight text-amber-100"
                @click="onChatActivationPremiumClick"
              >
                <PremiumLockBadge variant="crown" size="xs" />
                <span>{{ t('chats.actions.protection_premium') }}</span>
              </button>
              <button
                v-if="canOpenManagers(chat)"
                type="button"
                class="inline-flex min-w-0 max-w-full items-center justify-center gap-1 rounded-lg border border-slate-700/70 bg-zinc-900/75 px-2.5 py-1 text-[11px] font-semibold leading-tight text-slate-100"
                @click="openManagers(chat)"
              >
                <span>{{ t('chats.actions.managers') }}</span>
                <span v-if="(Number(chat.managers_count) || 0) > 0" class="min-w-[1.1rem] shrink-0 tabular-nums text-cyan-200/95">{{ Number(chat.managers_count) || 0 }}</span>
              </button>
              <button
                v-else
                type="button"
                class="inline-flex items-center gap-1 rounded-lg border border-amber-400/35 bg-amber-900/25 px-2 py-1 text-[11px] font-semibold leading-tight text-amber-200"
                @click="onManagersPremiumClick"
              >
                <PremiumLockBadge variant="crown" size="xs" />
                <span>{{ t('chats.actions.managers_premium') }}</span>
              </button>
              <button
                v-if="!chat.locked_by_limit"
                type="button"
                class="rounded-lg border border-slate-700/70 bg-zinc-900/75 px-2 py-1 text-[11px] font-semibold leading-tight text-slate-100"
                @click="goToReports(chat.id)"
              >{{ chat.log_chat_id ? t('chats.actions.reports_done') : t('chats.actions.reports') }}</button>
            </div>
          </div>
        </div>
    </div>

    <GuardTeleport>
    <div
      v-if="managersModalChat"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.78);padding:16px"
      class="flex items-end justify-center px-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] pt-[max(12px,calc(env(safe-area-inset-top,0px)+48px))] md:items-center md:pb-6"
      @click.self="closeManagers"
    >
      <div class="w-full max-w-md max-h-[90vh] overflow-y-auto rounded-2xl border border-white/10 bg-[#101013] p-4 text-zinc-100 shadow-[0_24px_60px_-20px_rgba(0,0,0,0.9)]">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="truncate text-sm font-semibold text-white">{{ t('chats.managers.heading', { title: managersModalChat.title }) }}</h3>
          <div class="flex items-center gap-1">
            <button
              type="button"
              class="inline-flex h-6 min-w-[1.5rem] items-center justify-center rounded-full bg-white/[0.04] px-1 text-[10px] font-bold text-zinc-300 hover:bg-white/[0.08]"
              :title="isEn ? 'Help' : 'Справка'"
              @click="showManagersInfoModal = true"
            >
              i
            </button>
            <button type="button" class="rounded-lg px-2 py-1 text-xs text-zinc-400 hover:bg-white/10" @click="closeManagers">✕</button>
          </div>
        </div>
        <div v-if="managersLoading" class="text-xs text-zinc-400">{{ t('chats.managers.loading') }}</div>
        <div v-else class="space-y-3">
          <!-- Прогресс лимита делегатов + кнопка журнала действий -->
          <div class="flex items-center justify-between gap-2 text-[11px]">
            <span class="text-zinc-400">{{ t('chats.managers.count', { count: managersData.managers?.length || 0 }) }}</span>
            <div class="flex items-center gap-1.5">
              <button
                type="button"
                class="inline-flex items-center gap-1 rounded-full bg-white/[0.04] px-2 py-0.5 text-[10px] font-medium text-zinc-300 hover:bg-white/[0.08]"
                @click="openAuditModal()"
              >
                📋 {{ t('chats.managers.audit_button') }}
              </button>
              <span v-if="Number(managersData.limit) > 0" class="rounded-full bg-white/[0.04] px-2 py-0.5 font-medium text-zinc-300">
                {{ t('chats.managers.limit_progress', { used: managersData.managers?.length || 0, total: managersData.limit }) }}
              </span>
              <span v-else class="rounded-full bg-emerald-500/15 px-2 py-0.5 font-medium text-emerald-200">
                {{ t('chats.managers.limit_unlimited') }}
              </span>
            </div>
          </div>
          <!-- Сводка статистики чата (deleted/joined/messages) — без белой обводки -->
          <div v-if="managersStats" class="rounded-xl bg-white/[0.025] px-3 py-2 text-[11px] text-zinc-300">
            <p>
              {{
                t('chats.managers.stats', {
                  deleted: Number(managersStats?.total_deleted || 0),
                  joined: Number(managersStats?.total_joined || 0),
                  messages: Number(managersStats?.total_messages || 0),
                })
              }}
            </p>
          </div>
          <!-- Список делегатов -->
          <div class="space-y-2">
            <div
              v-for="m in (managersData.managers || [])"
              :key="`m-${m.user_id}`"
              class="flex items-start gap-2.5 rounded-xl border border-white/[0.06] bg-white/[0.025] px-3 py-2.5 text-xs"
            >
              <!-- Аватар-инициал -->
              <span
                class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br text-[12px] font-bold text-white shadow-inner"
                :class="managerAvatarMeta(m).gradient"
              >
                {{ managerAvatarMeta(m).initials }}
              </span>
              <!-- Имя + бейджи -->
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2">
                  <span class="truncate text-[13px] font-medium text-white">
                    {{ m.first_name || (m.username ? '@'+m.username : m.user_id) }}
                  </span>
                  <span
                    class="inline-flex h-1.5 w-1.5 shrink-0 rounded-full"
                    :class="m.is_online ? 'bg-emerald-400' : 'bg-zinc-500'"
                    :title="m.is_online ? t('chats.managers.online') : t('chats.managers.offline')"
                  />
                </div>
                <div class="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-zinc-500">
                  <span>ID {{ m.user_id }}</span>
                  <span
                    v-if="managerExpiresMeta(m.expires_at)"
                    class="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium"
                    :class="{
                      'bg-zinc-500/15 text-zinc-300': managerExpiresMeta(m.expires_at).tone === 'zinc',
                      'bg-amber-500/15 text-amber-200': managerExpiresMeta(m.expires_at).tone === 'amber',
                      'bg-rose-500/20 text-rose-200': managerExpiresMeta(m.expires_at).tone === 'rose',
                    }"
                    :title="t('chats.managers.expires_title')"
                  >
                    ⏳ {{ managerExpiresMeta(m.expires_at).label }}
                  </span>
                  <button
                    type="button"
                    class="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium"
                    :class="managerActivityBadgeClass(m)"
                    :title="managerActivityTitle(m)"
                    @click.stop="openAuditModal(m.user_id)"
                  >
                    📊 {{ t('chats.managers.actions_7d', { n: Number(m.actions_7d || 0) }) }}
                  </button>
                </div>
                <div class="mt-1.5 flex flex-wrap items-center gap-1">
                  <!-- Активные права. Кнопка ✕ снимает только одно конкретное право. -->
                  <span
                    v-for="perm in managerPermEntries(m.permissions)"
                    :key="`mp-${m.user_id}-${perm.key}`"
                    class="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium"
                    :class="managerPermMeta(perm.key).badge"
                  >
                    <span aria-hidden="true">{{ managerPermMeta(perm.key).icon }}</span>
                    {{ perm.label }}
                    <button
                      v-if="managersData.can_manage_access"
                      type="button"
                      class="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full text-[10px] leading-none text-white"
                      :class="managerPermMeta(perm.key).removeBtn"
                      :title="t('chats.managers.remove_perm_title')"
                      @click.stop="removeManagerPermission(m, perm.key)"
                    >
                      ✕
                    </button>
                  </span>
                  <!--
                    Бейджи недостающих прав. Полупрозрачные, с «+».
                    Клик добавляет это право без открытия модалки пресетов.
                    Видны только владельцу с can_manage_access.
                  -->
                  <button
                    v-for="perm in (managersData.can_manage_access ? managerPermMissing(m.permissions) : [])"
                    :key="`mpa-${m.user_id}-${perm.key}`"
                    type="button"
                    class="inline-flex items-center gap-1 rounded-full border border-dashed border-white/15 bg-white/[0.025] px-1.5 py-0.5 text-[10px] font-medium text-zinc-400 hover:border-white/30 hover:bg-white/[0.05] hover:text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                    :disabled="managersLoading"
                    :title="t('chats.managers.add_perm_title', { label: perm.label })"
                    @click.stop="addManagerPermission(m, perm.key)"
                  >
                    <span aria-hidden="true" class="opacity-60">{{ managerPermMeta(perm.key).icon }}</span>
                    {{ perm.label }}
                    <span class="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full bg-white/[0.08] text-[10px] leading-none">＋</span>
                  </button>
                  <span
                    v-if="!managerPermEntries(m.permissions).length && !managersData.can_manage_access"
                    class="rounded-full bg-white/[0.04] px-1.5 py-0.5 text-[10px] text-zinc-500"
                  >
                    {{ t('chats.managers.no_perms') }}
                  </span>
                </div>
              </div>
              <!-- Удалить админа -->
              <button
                v-if="managersData.can_manage_access"
                type="button"
                class="shrink-0 rounded-lg bg-rose-500/15 px-2 py-1 text-[11px] font-medium text-rose-200 hover:bg-rose-500/25"
                @click="askRemoveManager(m)"
              >
                {{ t('chats.managers.remove') }}
              </button>
            </div>
            <p v-if="!(managersData.managers || []).length" class="rounded-xl bg-white/[0.025] px-3 py-3 text-center text-xs text-zinc-500">{{ t('chats.managers.empty') }}</p>
          </div>
          <!-- Приглашения -->
          <div v-if="managersData.can_manage_access" class="space-y-1.5">
            <p class="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{{ t('chats.managers.invites_label') }}</p>
            <div
              v-for="inv in (managersData.invites || [])"
              :key="`inv-${inv.id}`"
              class="flex flex-col gap-2 rounded-lg bg-white/[0.025] px-2.5 py-2 text-[11px]"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="truncate text-zinc-200">
                  {{ inv.target_username ? '@' + inv.target_username : (inv.target_telegram_id || t('chats.managers.invite_anonymous')) }}
                </span>
                <div class="flex shrink-0 items-center gap-2">
                  <span
                    class="rounded-full px-1.5 py-0.5 text-[10px] font-medium"
                    :class="inv.status === 'connected' ? 'bg-emerald-500/15 text-emerald-200' : 'bg-amber-500/15 text-amber-200'"
                  >
                    {{ inviteStatusLabel(inv.status) }}
                  </span>
                  <span
                    v-if="inv.status !== 'connected' && managerExpiresMeta(inv.expires_at)"
                    class="rounded-full px-1.5 py-0.5 text-[10px] font-medium"
                    :class="{
                      'bg-zinc-500/15 text-zinc-300': managerExpiresMeta(inv.expires_at).tone === 'zinc',
                      'bg-amber-500/15 text-amber-200': managerExpiresMeta(inv.expires_at).tone === 'amber',
                      'bg-rose-500/20 text-rose-200': managerExpiresMeta(inv.expires_at).tone === 'rose',
                    }"
                    :title="t('chats.managers.expires_title')"
                  >
                    ⏳ {{ managerExpiresMeta(inv.expires_at).label }}
                  </span>
                </div>
              </div>
              <div v-if="inv.status !== 'connected'" class="flex flex-wrap items-center gap-1.5">
                <button
                  v-if="inv.invite_link"
                  type="button"
                  class="inline-flex items-center gap-1 rounded-lg bg-emerald-500/15 px-2 py-1 text-[10px] font-medium text-emerald-200 hover:bg-emerald-500/25"
                  @click="copyInviteLink(inv)"
                >
                  🔗 {{ t('chats.managers.copy_invite_link') }}
                </button>
                <button
                  v-if="managersData.can_manage_access"
                  type="button"
                  class="rounded-lg bg-white/[0.04] px-2 py-1 text-[10px] text-zinc-300 hover:bg-white/[0.08]"
                  @click="cancelInvite(inv.id)"
                >
                  {{ t('chats.managers.cancel_invite') }}
                </button>
              </div>
            </div>
            <p v-if="!(managersData.invites || []).length" class="text-[11px] text-zinc-500">{{ t('chats.managers.no_invites') }}</p>
          </div>
          <!-- Добавить нового админа -->
          <div v-if="managersData.can_manage_access" class="rounded-xl border border-white/[0.06] bg-white/[0.025] p-3">
            <input
              v-model="addManagerValue"
              type="text"
              class="mb-2 w-full rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-white placeholder:text-zinc-500 focus:border-white/20 focus:outline-none"
              @keydown.enter.prevent="onAddManagerInputEnter"
              :placeholder="t('chats.managers.invite_placeholder')"
            />
            <label class="mb-2 flex cursor-pointer items-start gap-2 rounded-lg bg-white/[0.03] px-2.5 py-2 text-[11px] text-zinc-300 hover:bg-white/[0.05]">
              <input
                v-model="addManagerAsLink"
                type="checkbox"
                class="mt-0.5 h-3.5 w-3.5 shrink-0 cursor-pointer accent-emerald-400"
              />
              <span class="flex-1">
                <span class="block font-medium text-white">{{ t('chats.managers.as_link_title') }}</span>
                <span class="block text-[10px] leading-snug text-zinc-500">{{ t('chats.managers.as_link_hint') }}</span>
              </span>
            </label>
            <button
              type="button"
              class="guard-green-soft w-full rounded-lg px-4 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="managersLoading || !String(addManagerValue || '').trim()"
              @click="onAddManagerPrimaryClick"
            >
              {{ addManagerPermsOpen ? t('chats.managers.confirm_perms') : t('chats.managers.pick_perms') }}
            </button>
          </div>
          <p v-if="managersData.premium_enabled === false" class="text-xs text-amber-300/90">
            {{ t('chats.managers.access_premium_only') }}
          </p>
          <p v-if="!managersData.can_manage_access && managersData.premium_enabled !== false" class="text-xs text-zinc-400">
            {{ t('chats.managers.owner_only') }}
          </p>
        </div>
      </div>
    </div>
    </GuardTeleport>

    <!-- Подтверждение удаления админа -->
    <GuardTeleport>
    <div
      v-if="removeManagerConfirm"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95500;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.78);padding:16px"
      class="flex items-center justify-center p-4"
      @click.self="cancelRemoveManager"
    >
      <div class="w-full max-w-sm rounded-2xl border border-white/10 bg-[#101013] p-4 text-zinc-100 shadow-[0_24px_60px_-20px_rgba(0,0,0,0.9)]">
        <h3 class="mb-2 text-sm font-semibold text-white">{{ t('chats.managers.confirm_remove_title', { name: removeManagerConfirm.name }) }}</h3>
        <p class="text-[12px] leading-snug text-zinc-400">{{ t('chats.managers.confirm_remove_hint') }}</p>
        <div v-if="removeManagerConfirm.perms.length" class="mt-2 flex flex-wrap gap-1">
          <span
            v-for="(lbl, i) in removeManagerConfirm.perms"
            :key="`crp-${i}`"
            class="rounded-full bg-white/[0.04] px-2 py-0.5 text-[10px] text-zinc-300"
          >
            {{ lbl }}
          </span>
        </div>
        <div class="mt-4 flex gap-2">
          <button
            type="button"
            class="flex-1 rounded-lg bg-white/[0.04] px-3 py-2 text-xs font-medium text-zinc-200 hover:bg-white/[0.08]"
            @click="cancelRemoveManager"
          >
            {{ t('chats.managers.confirm_remove_cancel') }}
          </button>
          <button
            type="button"
            class="flex-1 rounded-lg bg-rose-500/85 px-3 py-2 text-xs font-semibold text-white hover:bg-rose-500"
            @click="confirmRemoveManager"
          >
            {{ t('chats.managers.confirm_remove_ok') }}
          </button>
        </div>
      </div>
    </div>
    </GuardTeleport>

    <!-- Audit log: журнал действий делегатов/владельца в чате (Фаза 3) -->
    <GuardTeleport>
    <div
      v-if="managersModalChat && auditModalOpen"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.78);padding:16px"
      class="flex items-center justify-center px-4"
      @click.self="closeAuditModal"
    >
      <div
        class="relative max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl border border-white/10 bg-[#101013] p-4 shadow-[0_24px_60px_-20px_rgba(0,0,0,0.9)]"
        @click.stop
      >
        <div class="mb-3 flex items-start justify-between gap-3">
          <div class="min-w-0">
            <h3 class="text-sm font-semibold text-white">
              {{ auditFilterUserId
                ? t('chats.managers.audit_modal_title_user')
                : t('chats.managers.audit_modal_title') }}
            </h3>
            <p class="mt-0.5 text-[11px] text-zinc-500">
              {{ auditFilterUserId
                ? t('chats.managers.audit_modal_hint_user')
                : t('chats.managers.audit_modal_hint') }}
            </p>
          </div>
          <button type="button" class="shrink-0 rounded-lg px-2 py-1 text-xs text-zinc-400 hover:bg-white/10" @click="closeAuditModal">✕</button>
        </div>

        <!-- Сводка для single-user режима -->
        <div
          v-if="auditFilterUserId && auditUserActivity"
          class="mb-3 grid grid-cols-3 gap-1.5 rounded-xl bg-white/[0.025] p-2 text-[10px]"
        >
          <div class="text-center">
            <p class="text-zinc-500">{{ t('chats.managers.actions_label_7d') }}</p>
            <p class="text-base font-bold text-emerald-200">{{ auditUserActivity.actions_7d }}</p>
          </div>
          <div class="text-center">
            <p class="text-zinc-500">{{ t('chats.managers.actions_label_30d') }}</p>
            <p class="text-base font-bold text-zinc-200">{{ auditUserActivity.actions_30d }}</p>
          </div>
          <div class="text-center">
            <p class="text-zinc-500">{{ t('chats.managers.last_action_label') }}</p>
            <p class="text-[11px] font-medium leading-tight text-zinc-300">
              {{ auditUserActivity.last_action_at ? formatLocalDate(auditUserActivity.last_action_at) : t('chats.managers.never_acted') }}
            </p>
          </div>
        </div>

        <div v-if="auditLoading && !auditItems.length" class="py-6 text-center text-xs text-zinc-400">
          {{ t('chats.managers.loading') }}
        </div>
        <p v-else-if="!auditItems.length" class="py-6 text-center text-xs text-zinc-500">
          {{ t('chats.managers.audit_empty') }}
        </p>
        <ul v-else class="space-y-1.5">
          <li
            v-for="row in auditItems"
            :key="`audit-${row.id}`"
            class="flex items-start gap-2 rounded-xl border border-white/[0.06] bg-white/[0.025] px-3 py-2 text-[11px]"
          >
            <span aria-hidden="true" class="mt-0.5 text-[14px] leading-none">{{ auditActionIcon(row.action_kind) }}</span>
            <div class="min-w-0 flex-1">
              <p class="truncate text-[12px] font-medium text-white">{{ auditActionLabel(row.action_kind) }}</p>
              <p class="mt-0.5 truncate text-[10px] text-zinc-500">
                <span v-if="row.user_first_name || row.user_username">
                  {{ row.user_first_name || ('@' + row.user_username) }}
                </span>
                <span v-else>ID {{ row.user_id }}</span>
                <span class="mx-1 text-zinc-700">·</span>
                <span>{{ formatLocalDate(row.created_at) }}</span>
              </p>
              <p v-if="row.action_target" class="mt-0.5 truncate text-[10px] text-zinc-500">
                <span class="text-zinc-600">→</span> {{ row.action_target }}
              </p>
              <details
                v-if="row.meta && typeof row.meta === 'object'"
                class="mt-1"
              >
                <summary class="cursor-pointer text-[10px] text-zinc-500 hover:text-zinc-300">{{ t('chats.managers.audit_meta_toggle') }}</summary>
                <pre class="mt-1 overflow-x-auto rounded-md bg-black/30 p-1.5 text-[10px] leading-snug text-zinc-300">{{ JSON.stringify(row.meta, null, 2) }}</pre>
              </details>
            </div>
            <span
              v-if="!row.success"
              class="shrink-0 rounded-full bg-rose-500/15 px-1.5 py-0.5 text-[10px] text-rose-200"
            >{{ t('chats.managers.audit_failed') }}</span>
          </li>
        </ul>
        <div v-if="auditCanLoadMore()" class="mt-3 flex justify-center">
          <button
            type="button"
            class="rounded-lg bg-white/[0.05] px-3 py-1.5 text-[11px] font-medium text-zinc-200 hover:bg-white/[0.08] disabled:opacity-50"
            :disabled="auditLoading"
            @click="loadAudit()"
          >
            {{ auditLoading ? t('chats.managers.loading') : t('chats.managers.audit_load_more') }}
          </button>
        </div>
        <p v-if="auditTotal > 0 && !auditFilterUserId" class="mt-2 text-center text-[10px] text-zinc-600">
          {{ t('chats.managers.audit_total', { shown: auditItems.length, total: auditTotal }) }}
        </p>
      </div>
    </div>
    </GuardTeleport>

    <GuardTeleport>
    <div
      v-if="managersModalChat && addManagerPermsOpen"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.78);padding:16px"
      class="flex items-center justify-center px-4"
      @click.self="addManagerPermsOpen = false"
    >
      <form
        class="w-full max-w-md max-h-[90vh] overflow-y-auto rounded-2xl border border-white/10 bg-[#101013] p-4 shadow-[0_24px_60px_-20px_rgba(0,0,0,0.9)] text-zinc-100"
        @submit.prevent="addManager"
      >
        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-sm font-semibold text-white">{{ t('chats.managers.pick_perms_title') }}</h3>
          <button type="button" class="rounded-lg px-2 py-1 text-xs text-zinc-400 hover:bg-white/10" @click="addManagerPermsOpen = false">✕</button>
        </div>

        <!-- Пресеты прав: один клик расставляет все галки. Только для групп; для каналов не показываем. -->
        <div v-if="!isManagersChannel" class="mb-3">
          <p class="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{{ t('chats.managers.presets_label') }}</p>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="preset in MANAGER_PERM_PRESETS"
              :key="`pp-${preset.key}`"
              type="button"
              class="flex items-center gap-2 rounded-xl border px-3 py-2 text-left text-[12px] transition"
              :class="isPermPresetActive(preset)
                ? 'border-emerald-400/40 bg-emerald-500/10 text-emerald-100'
                : 'border-white/[0.06] bg-white/[0.025] text-zinc-200 hover:bg-white/[0.05]'"
              @click="applyManagerPreset(preset)"
            >
              <span class="text-base leading-none">{{ preset.icon }}</span>
              <div class="flex min-w-0 flex-col">
                <span class="truncate text-[12px] font-semibold">{{ t(`chats.managers.preset_names.${preset.key}`) }}</span>
                <span class="truncate text-[10px] text-zinc-500">{{ t(`chats.managers.preset_hints.${preset.key}`) }}</span>
              </div>
            </button>
          </div>
        </div>

        <p class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{{ t('chats.managers.perms_label') }}</p>

        <!-- iOS-тогглы для каждого права. -->
        <ul v-if="!isManagersChannel" class="space-y-2">
          <li class="flex items-center justify-between gap-3 rounded-xl border border-white/[0.06] bg-white/[0.025] px-3 py-2.5">
            <div class="flex min-w-0 flex-1 items-center gap-2.5">
              <span class="text-lg leading-none">🛡</span>
              <span class="truncate text-[13px] font-medium text-white">{{ t('chats.perm_help.protection') }}</span>
            </div>
            <button
              type="button" role="switch" :aria-checked="!!addManagerPerms.protection"
              class="relative h-[31px] w-[51px] shrink-0 rounded-full border transition duration-200"
              :class="addManagerPerms.protection ? 'border-emerald-400/40 bg-emerald-500/[0.32]' : 'border-white/[0.14] bg-white/[0.09]'"
              @click="addManagerPerms.protection = !addManagerPerms.protection"
            >
              <span class="absolute left-[3px] top-1/2 h-[25px] w-[25px] rounded-full bg-white shadow-md transition duration-200"
                :style="{ transform: addManagerPerms.protection ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }" />
            </button>
          </li>
          <li class="flex items-center justify-between gap-3 rounded-xl border border-white/[0.06] bg-white/[0.025] px-3 py-2.5">
            <div class="flex min-w-0 flex-1 items-center gap-2.5">
              <span class="text-lg leading-none">📢</span>
              <span class="truncate text-[13px] font-medium text-white">{{ t('chats.perm_help.broadcast') }}</span>
            </div>
            <button
              type="button" role="switch" :aria-checked="!!addManagerPerms.broadcast"
              class="relative h-[31px] w-[51px] shrink-0 rounded-full border transition duration-200"
              :class="addManagerPerms.broadcast ? 'border-emerald-400/40 bg-emerald-500/[0.32]' : 'border-white/[0.14] bg-white/[0.09]'"
              @click="addManagerPerms.broadcast = !addManagerPerms.broadcast"
            >
              <span class="absolute left-[3px] top-1/2 h-[25px] w-[25px] rounded-full bg-white shadow-md transition duration-200"
                :style="{ transform: addManagerPerms.broadcast ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }" />
            </button>
          </li>
          <li class="flex items-center justify-between gap-3 rounded-xl border border-white/[0.06] bg-white/[0.025] px-3 py-2.5">
            <div class="flex min-w-0 flex-1 items-center gap-2.5">
              <span class="text-lg leading-none">📊</span>
              <span class="truncate text-[13px] font-medium text-white">{{ t('chats.perm_help.stats') }}</span>
            </div>
            <button
              type="button" role="switch" :aria-checked="!!addManagerPerms.stats"
              class="relative h-[31px] w-[51px] shrink-0 rounded-full border transition duration-200"
              :class="addManagerPerms.stats ? 'border-emerald-400/40 bg-emerald-500/[0.32]' : 'border-white/[0.14] bg-white/[0.09]'"
              @click="addManagerPerms.stats = !addManagerPerms.stats"
            >
              <span class="absolute left-[3px] top-1/2 h-[25px] w-[25px] rounded-full bg-white shadow-md transition duration-200"
                :style="{ transform: addManagerPerms.stats ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }" />
            </button>
          </li>
          <li class="flex items-center justify-between gap-3 rounded-xl border border-white/[0.06] bg-white/[0.025] px-3 py-2.5">
            <div class="flex min-w-0 flex-1 items-center gap-2.5">
              <span class="text-lg leading-none">📋</span>
              <span class="truncate text-[13px] font-medium text-white">{{ t('chats.perm_help.reports') }}</span>
            </div>
            <button
              type="button" role="switch" :aria-checked="!!addManagerPerms.reports"
              class="relative h-[31px] w-[51px] shrink-0 rounded-full border transition duration-200"
              :class="addManagerPerms.reports ? 'border-emerald-400/40 bg-emerald-500/[0.32]' : 'border-white/[0.14] bg-white/[0.09]'"
              @click="addManagerPerms.reports = !addManagerPerms.reports"
            >
              <span class="absolute left-[3px] top-1/2 h-[25px] w-[25px] rounded-full bg-white shadow-md transition duration-200"
                :style="{ transform: addManagerPerms.reports ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }" />
            </button>
          </li>
        </ul>

        <!-- Канальная модалка прав. -->
        <ul v-else class="space-y-2">
          <li class="flex items-center justify-between gap-3 rounded-xl border border-white/[0.06] bg-white/[0.025] px-3 py-2.5">
            <div class="flex min-w-0 flex-1 items-center gap-2.5">
              <span class="text-lg leading-none">📢</span>
              <span class="truncate text-[13px] font-medium text-white">{{ t('chats.perm_help.broadcast_label') }}</span>
            </div>
            <button
              type="button" role="switch" :aria-checked="!!addManagerPerms.broadcast"
              class="relative h-[31px] w-[51px] shrink-0 rounded-full border transition duration-200"
              :class="addManagerPerms.broadcast ? 'border-emerald-400/40 bg-emerald-500/[0.32]' : 'border-white/[0.14] bg-white/[0.09]'"
              @click="addManagerPerms.broadcast = !addManagerPerms.broadcast"
            >
              <span class="absolute left-[3px] top-1/2 h-[25px] w-[25px] rounded-full bg-white shadow-md transition duration-200"
                :style="{ transform: addManagerPerms.broadcast ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }" />
            </button>
          </li>
          <li class="flex items-center justify-between gap-3 rounded-xl border border-white/[0.06] bg-white/[0.025] px-3 py-2.5">
            <div class="flex min-w-0 flex-1 items-center gap-2.5">
              <span class="text-lg leading-none">⭐</span>
              <span class="truncate text-[13px] font-medium text-white">{{ t('chats.perm_help.first_post') }}</span>
            </div>
            <button
              type="button" role="switch" :aria-checked="!!addManagerPerms.first_post_settings"
              class="relative h-[31px] w-[51px] shrink-0 rounded-full border transition duration-200"
              :class="addManagerPerms.first_post_settings ? 'border-emerald-400/40 bg-emerald-500/[0.32]' : 'border-white/[0.14] bg-white/[0.09]'"
              @click="addManagerPerms.first_post_settings = !addManagerPerms.first_post_settings"
            >
              <span class="absolute left-[3px] top-1/2 h-[25px] w-[25px] rounded-full bg-white shadow-md transition duration-200"
                :style="{ transform: addManagerPerms.first_post_settings ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }" />
            </button>
          </li>
        </ul>

        <div class="mt-4 flex gap-2">
          <button type="button" class="flex-1 rounded-lg bg-white/[0.04] px-3 py-2 text-xs font-medium text-zinc-200 hover:bg-white/[0.08]" @click="addManagerPermsOpen = false">{{ t('chats.managers.cancel') }}</button>
          <button type="submit" class="guard-green-soft flex-1 rounded-lg px-3 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50" :disabled="managersLoading || !canSubmitNewManager">
            {{ t('chats.managers.add') }}
          </button>
        </div>
      </form>
    </div>
    </GuardTeleport>

    <GuardTeleport>
    <div
      v-if="showCabinetInfoModal"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center overscroll-none bg-black/70 px-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] pt-[max(12px,calc(env(safe-area-inset-top,0px)+48px))] md:items-center md:pb-6"
      @click.self="showCabinetInfoModal = false"
      @wheel.self.prevent
      @touchmove.self.prevent
    >
      <div class="w-full max-w-xl rounded-2xl border border-sky-500/40 bg-slate-950 p-4 text-slate-100 shadow-2xl">
        <div class="mb-2 flex items-center justify-between border-b border-white/10 pb-2">
          <h3 class="text-sm font-semibold">{{ t('chats.help_connected.title') }}</h3>
          <button class="rounded-lg px-2 py-1 text-sm text-slate-400 hover:bg-white/10" @click="showCabinetInfoModal = false">✕</button>
        </div>
        <div class="max-h-[min(70vh,28rem)] space-y-3 overflow-y-auto overscroll-y-contain pr-1 text-xs leading-relaxed text-slate-300">
          <p class="text-[11px] text-slate-400">
            {{ t('chats.help_connected.intro') }}
          </p>
          <div class="rounded-lg border border-white/10 bg-white/[0.04] p-2.5">
            <p class="text-[11px] font-semibold text-teal-200">{{ t('chats.help_connected.tabs_title') }}</p>
            <ul class="mt-1 list-inside list-disc space-y-1 text-[11px] text-slate-300">
              <li><span class="font-medium text-slate-200">{{ t('chats.tabs.all') }}</span> — {{ t('chats.help_connected.tabs_all') }}</li>
              <li><span class="font-medium text-slate-200">{{ t('chats.tabs.mine') }}</span> — {{ t('chats.help_connected.tabs_mine') }}</li>
              <li><span class="font-medium text-slate-200">{{ t('chats.tabs.shared') }}</span> — {{ t('chats.help_connected.tabs_shared') }}</li>
            </ul>
          </div>
          <div class="rounded-lg border border-white/10 bg-white/[0.04] p-2.5">
            <p class="text-[11px] font-semibold text-teal-200">{{ t('chats.help_connected.presets_title') }}</p>
            <p class="mt-1 text-[11px] text-slate-300">
              {{ t('chats.help_connected.presets_body') }}
            </p>
          </div>
          <div class="rounded-lg border border-white/10 bg-white/[0.04] p-2.5">
            <p class="text-[11px] font-semibold text-teal-200">{{ t('chats.help_connected.groups_title') }}</p>
            <p class="mt-1 text-[11px] text-slate-300">
              {{ t('chats.help_connected.groups_body') }}
            </p>
            <p class="mt-1.5 text-[11px] text-slate-400">
              {{ t('chats.help_connected.groups_delegate') }}
            </p>
          </div>
          <div class="rounded-lg border border-emerald-500/25 bg-emerald-950/15 p-2.5">
            <p class="text-[11px] font-semibold text-emerald-200">{{ t('chats.help_connected.channels_title') }}</p>
            <p class="mt-1 text-[11px] text-slate-300">
              {{ t('chats.help_connected.channels_body') }}
            </p>
            <p class="mt-1.5 text-[11px] text-slate-400">
              {{ t('chats.help_connected.channels_delegate') }}
            </p>
          </div>
          <div class="rounded-lg border border-violet-500/25 bg-violet-950/20 p-2.5">
            <p class="text-[11px] font-semibold text-violet-200">{{ t('chats.help_connected.delegates_title') }}</p>
            <p class="mt-1 text-[11px] text-slate-300">
              {{ t('chats.help_connected.delegates_body') }}
            </p>
            <p class="mt-1.5 text-[11px] text-slate-400">
              {{ t('chats.help_connected.delegates_channels') }}
            </p>
          </div>
        </div>
      </div>
    </div>
    </GuardTeleport>

    <GuardTeleport>
    <div
      v-if="showDelegatedInfoModal"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center overscroll-none bg-black/70 px-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] pt-[max(12px,calc(env(safe-area-inset-top,0px)+48px))] md:items-center md:pb-6"
      @click.self="showDelegatedInfoModal = false"
      @wheel.self.prevent
      @touchmove.self.prevent
    >
      <div class="w-full max-w-xl rounded-2xl border border-violet-500/40 bg-slate-950 p-4 text-slate-100 shadow-2xl">
        <div class="mb-2 flex items-center justify-between border-b border-white/10 pb-2">
          <h3 class="text-sm font-semibold">{{ t('chats.help_violet_adm.title') }}</h3>
          <button class="rounded-lg px-2 py-1 text-sm text-slate-400 hover:bg-white/10" @click="showDelegatedInfoModal = false">✕</button>
        </div>
        <p class="text-xs text-slate-300">{{ t('chats.help_violet_adm.body') }}</p>
        <p class="mt-3 text-[11px] font-semibold text-violet-200">{{ t('chats.help_violet_adm.perms_title') }}</p>
        <p class="mt-1 text-[11px] leading-relaxed text-slate-400">{{ t('chats.help_violet_adm.perms_body') }}</p>
      </div>
    </div>
    </GuardTeleport>

    <GuardTeleport>
    <div
      v-if="showManagersInfoModal"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-end justify-center overscroll-none bg-black/70 px-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] pt-[max(12px,calc(env(safe-area-inset-top,0px)+48px))] md:items-center md:pb-6"
      @click.self="showManagersInfoModal = false"
      @wheel.self.prevent
      @touchmove.self.prevent
    >
      <div class="w-full max-w-xl rounded-2xl border border-sky-500/40 bg-slate-950 p-4 text-slate-100 shadow-2xl">
        <div class="mb-2 flex items-center justify-between border-b border-white/10 pb-2">
          <h3 class="text-sm font-semibold">{{ t('chats.help_managers.title') }}</h3>
          <button class="rounded-lg px-2 py-1 text-sm text-slate-400 hover:bg-white/10" @click="showManagersInfoModal = false">✕</button>
        </div>
        <p class="text-[13px] leading-relaxed text-slate-200/95">
          <span class="font-semibold text-white">{{ t('chats.help_managers.p1_title') }}</span>
          {{ t('chats.help_managers.p1_body') }}
        </p>
        <p class="mt-3 text-[12px] leading-relaxed text-slate-400">
          <span class="font-semibold text-slate-300">{{ t('chats.help_managers.p2_title') }}</span>
          {{ t('chats.help_managers.p2_body') }}
        </p>
        <p class="mt-3 text-[12px] leading-relaxed text-slate-400">
          <span class="font-semibold text-slate-300">{{ t('chats.help_managers.p3_title') }}</span>
          {{ t('chats.help_managers.p3_body') }}
        </p>
      </div>
    </div>
    </GuardTeleport>

    <GuardTeleport>
    <div
      v-if="autoApproveModalChat"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:95000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px"
      class="flex items-end justify-center overscroll-none bg-black/70 px-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] pt-[max(12px,calc(env(safe-area-inset-top,0px)+48px))] md:items-center md:pb-6"
      @click.self="closeAutoApproveModal"
      @wheel.self.prevent
      @touchmove.self.prevent
    >
      <div
        class="w-full max-w-md overflow-hidden rounded-2xl border border-violet-400/30 bg-slate-950 shadow-2xl ring-1 ring-white/[0.06]"
        @click.stop
      >
        <div class="flex items-center justify-between border-b border-white/10 px-4 py-3">
          <div class="min-w-0 pr-3">
            <p class="truncate text-sm font-semibold text-white">{{ autoApproveModalChat.title }}</p>
            <p class="text-[10px] uppercase tracking-wide text-violet-300/90">{{ t('chats.auto_approve.modal_subtitle') }}</p>
          </div>
          <button
            type="button"
            class="shrink-0 rounded-lg px-2 py-1 text-sm text-slate-400 hover:bg-white/10"
            @click="closeAutoApproveModal"
          >✕</button>
        </div>
        <div class="px-3 py-3">
          <GuardAutoApproveJoinSetting
            embedded
            :enabled="!!autoApproveModalChat.auto_approve_join_requests"
            :loading="autoApproveSavingId === autoApproveModalChat.id"
            :variant="isChannelRow(autoApproveModalChat) ? 'channel' : 'group'"
            @toggle="toggleAutoApproveJoin(autoApproveModalChat, $event)"
          />
        </div>
      </div>
    </div>
    </GuardTeleport>

    <ChannelPostRulesModal
      v-model="channelPostRulesOpen"
      :discussion-chat-id="channelPostRulesDiscussionId"
      :channel-id="channelPostRulesChannelId"
      :channel-title="channelPostRulesChannelTitle"
    />

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

<style scoped>
@keyframes hourglassFlip {
  0% { transform: rotate(0deg); }
  50% { transform: rotate(180deg); }
  100% { transform: rotate(360deg); }
}

.hourglass-flip {
  animation: hourglassFlip 0.9s ease-in-out infinite;
  transform-origin: 50% 50%;
}
</style>

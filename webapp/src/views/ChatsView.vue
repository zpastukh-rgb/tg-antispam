<script setup>
import { ref, onMounted, onUnmounted, watch, computed, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useApi, messageFromApiError } from '../composables/useApi'
import { guardLog, guardWarn } from '../utils/guardDebugLog'
import { useCabinetMode } from '../composables/useCabinetMode'
import { useToast } from '../composables/useToast'
import ChannelPostRulesModal from '../components/ChannelPostRulesModal.vue'
import SecurityPinGateModal from '../components/SecurityPinGateModal.vue'
import { useSecurityPinGate } from '../composables/useSecurityPinGate'
import { shouldAskPinForAction } from '../utils/settingsSecurity'

const { t } = useI18n()
const isEn = computed(() => t('common.locale_code') === 'en')

const router = useRouter()
const route = useRoute()
const { api, error, fetchSilent, hasInitData } = useApi()
const { showToast } = useToast()
const { setCabinetMode } = useCabinetMode()
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
}

function managerPermEntries(perms) {
  const p = perms || {}
  const out = []
  if (p.protection) out.push({ key: 'protection', label: t('chats.perms.protection') })
  if (p.broadcast) out.push({ key: 'broadcast', label: t('chats.perms.broadcast') })
  if (p.reports || p.stats) out.push({ key: 'reports', label: t('chats.perms.reports') })
  if (p.first_post_settings) out.push({ key: 'first_post_settings', label: t('chats.perms.first_post_settings') })
  return out
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
const isPremium = ref(false)
/** Для проверки PIN при отключении чата */
const viewerTelegramId = ref(0)
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
  channelPostRulesOpen.value = true
}

const chatsInfoModalOpen = computed(
  () =>
    showCabinetInfoModal.value ||
    showDelegatedInfoModal.value ||
    showManagersInfoModal.value,
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

async function loadChats() {
  if (!hasInitData.value) {
    guardLog('Chats', 'loadChats: skip (no initData)')
    return
  }
  guardLog('Chats', 'loadChats: start')
  const mode = delegatedChatsOnly.value ? 'shared' : 'all'
  try {
    const [data, p, me] = await Promise.all([
      fetchSilent(() => api.chats(mode)),
      fetchSilent(() => api.connectPending()).catch(() => ({ chats: [] })),
      fetchSilent(() => api.me()).catch(() => ({ is_premium: false })),
    ])
    const rows = data.chats || []
    isPremium.value = !!me?.is_premium
    const fromMe = Number(me?.telegram_id || 0)
    viewerTelegramId.value = fromMe > 0 ? fromMe : extractTelegramIdFromInitUnsafe()
    chats.value = delegatedChatsOnly.value
      ? rows
      : [...rows].sort((a, b) => Number(isDelegatedCabinetChat(b)) - Number(isDelegatedCabinetChat(a)))
    if (!delegatedChatsOnly.value && focusThreatOnly.value) {
      cabinetTab.value = 'shared'
    }
    selectedChatId.value = data.selected_chat_id ?? null
    pendingCount.value = Array.isArray(p?.chats) ? p.chats.length : 0
    try {
      const a = await fetchSilent(() => api.spikeAlerts())
      const map = {}
      for (const row of a?.items || []) {
        const cid = Number(row?.chat_id || 0)
        if (!cid) continue
        map[cid] = row
      }
      spikeAlertsByChat.value = map
    } catch {
      spikeAlertsByChat.value = {}
    }
    await scrollToFirstThreatChat()
    guardLog('Chats', 'loadChats OK', {
      count: chats.value.length,
      selected: selectedChatId.value,
      pending: pendingCount.value,
    })
  } catch (e) {
    guardWarn('Chats', 'loadChats failed', e)
  } finally {
    chatsFirstLoad.value = false
  }
}

function chatSpikeAlert(chat) {
  const cid = Number(chat?.id || 0)
  if (!cid) return null
  return spikeAlertsByChat.value[cid] || null
}

onMounted(async () => {
  error.value = null
  await loadChats()
  const onVis = () => {
    if (document.visibilityState === 'visible') loadChats()
  }
  document.addEventListener('visibilitychange', onVis)
  stopVis = () => document.removeEventListener('visibilitychange', onVis)
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
    loadChats()
  },
)

watch(cabinetTab, () => {
  kindPreset.value = 'all'
})

watch(
  () => delegatedChatsOnly.value,
  () => {
    kindPreset.value = 'all'
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
    router.push({ path: '/admin', query: { tab: 'overview', open: 'stats_reports', chat_id: String(chatId) } })
    return
  }
  setCabinetMode('owner')
  router.push({ path: '/admin', query: { tab: 'overview', open: 'stats_reports' } })
}

function goToPremiumBilling() {
  const q = { ...route.query, section: 'billing' }
  delete q.scroll
  void router.push({ path: '/', query: q })
}

async function activatePendingFromEmpty() {
  if (!hasInitData.value) return
  pendingLoading.value = true
  try {
    const data = await fetchSilent(() => api.connectActivatePending())
    await loadChats()
    if (!data?.connected) {
      window.alert(t('chats.toasts.bot_must_be_admin'))
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
  managersLoading.value = true
  try {
    const res = await fetchSilent(() => api.chatManagerAdd(managersModalChat.value.id, payload))
    managersData.value = { ...managersData.value, ...res }
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

async function removeManagerPermission(manager, key) {
  if (!managersModalChat.value?.id || !manager?.user_id || !key) return
  const base = manager?.permissions || {}
  const nextPerms = {
    protection: !!base.protection,
    broadcast: !!base.broadcast,
    reports: !!base.reports,
    first_post_settings: !!base.first_post_settings,
  }
  nextPerms[key] = false
  managersLoading.value = true
  try {
    const res = await fetchSilent(() => api.chatManagerUpdate(managersModalChat.value.id, manager.user_id, { permissions: nextPerms }))
    managersData.value = { ...managersData.value, ...res }
    await loadChats()
  } finally {
    managersLoading.value = false
  }
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
            <div class="flex items-start gap-2">
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
                  <span class="font-medium text-slate-200">{{ chat.linked_discussion_title || ('#' + chat.linked_discussion_chat_id) }}</span>
                </p>
                <p v-if="chat.locked_by_limit" class="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-300">{{ t('chats.labels.free_limit') }}</p>
                <p v-else-if="protectionActive(chat)" class="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-lime-300">
                  {{ isChannelRow(chat) ? t('chats.labels.connected') : t('chats.labels.active') }}
                </p>
                <p v-else class="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-400">{{ t('chats.labels.inactive') }}</p>
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
                  v-if="chat.locked_by_limit"
                  type="button"
                  class="rounded-lg border border-amber-400/40 bg-amber-900/30 px-2 py-1 text-[11px] font-semibold leading-tight text-amber-100"
                  @click="goToPremiumBilling"
                >💳 Premium</button>
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
                  class="rounded-lg border border-amber-400/40 bg-amber-900/30 px-2 py-1 text-[11px] font-semibold leading-tight text-amber-100"
                  @click="goToPremiumBilling"
                >{{ t('chats.actions.protection_premium') }}</button>
                <button
                  v-if="delegatedCan(chat, 'broadcast')"
                  type="button"
                  class="rounded-lg border border-violet-400/35 bg-violet-900/30 px-2 py-1 text-[11px] font-semibold leading-tight text-violet-200"
                  @click="openDelegatedBroadcast(chat.id)"
                >{{ t('chats.actions.groups_broadcast') }}</button>
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
            <div class="flex items-start gap-2">
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-bold leading-tight text-white">{{ chat.title }}</p>
                <div class="mt-0.5 flex flex-wrap items-center gap-1">
                  <p class="text-[10px] text-slate-300">{{ t('chats.labels.my_cabinet') }}</p>
                  <span class="rounded-full border border-emerald-400/40 bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-emerald-100">{{ t('chats.labels.channel') }}</span>
                </div>
                <p v-if="chat.linked_discussion_title || chat.linked_discussion_chat_id" class="mt-0.5 text-[10px] text-slate-400">
                  {{ t('chats.labels.discussion') }}
                  <span class="font-medium text-slate-200">{{ chat.linked_discussion_title || ('#' + chat.linked_discussion_chat_id) }}</span>
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
                v-else
                type="button"
                class="rounded-lg border border-amber-400/40 bg-amber-900/30 px-2 py-1 text-[11px] font-semibold leading-tight text-amber-100"
                @click="goToPremiumBilling"
              >💳 Premium</button>
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
                class="rounded-lg border border-amber-400/35 bg-amber-900/25 px-2 py-1 text-[11px] font-semibold leading-tight text-amber-200"
                @click="router.push({ path: '/', query: { ...route.query, section: 'account' } })"
              >{{ t('chats.actions.managers_premium') }}</button>
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
            <div class="flex items-start gap-2">
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
                v-else
                type="button"
                class="rounded-lg border border-amber-400/40 bg-amber-900/30 px-2 py-1 text-[11px] font-semibold leading-tight text-amber-100"
                @click="goToPremiumBilling"
              >{{ t('chats.actions.protection_premium') }}</button>
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
                class="rounded-lg border border-amber-400/35 bg-amber-900/25 px-2 py-1 text-[11px] font-semibold leading-tight text-amber-200"
                @click="router.push({ path: '/', query: { ...route.query, section: 'account' } })"
              >{{ t('chats.actions.managers_premium') }}</button>
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

    <Teleport to="body">
    <div
      v-if="managersModalChat"
      class="fixed inset-0 z-[300] flex items-end justify-center bg-black/70 px-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] pt-[max(12px,calc(env(safe-area-inset-top,0px)+48px))] md:items-center md:pb-6"
      @click.self="closeManagers"
    >
      <div class="w-full max-w-4xl rounded-3xl bg-gradient-to-b from-[#0c1523]/96 via-[#0a111d]/97 to-[#070d17]/99 p-4 text-slate-100 shadow-[0_32px_90px_-30px_rgba(0,0,0,0.95)] backdrop-blur-2xl ring-1 ring-sky-500/15">
        <div class="mb-3 flex items-center justify-between gap-2 pb-2">
          <h3 class="text-sm font-semibold text-white">{{ t('chats.managers.heading', { title: managersModalChat.title }) }}</h3>
          <div class="flex items-center gap-1">
            <button
              type="button"
              class="inline-flex h-6 min-w-[1.5rem] items-center justify-center rounded-full bg-cyan-500/12 px-1 text-[10px] font-bold text-cyan-200/95 shadow-[0_0_18px_-10px_rgba(34,211,238,0.75)] ring-1 ring-cyan-400/28"
              :title="isEn ? 'Help' : 'Справка'"
              @click="showManagersInfoModal = true"
            >
              i
            </button>
            <button type="button" class="rounded-lg px-2 py-1 text-sm text-slate-400 hover:bg-slate-800/80 hover:text-white" @click="closeManagers">✕</button>
          </div>
        </div>
        <div v-if="managersLoading" class="text-xs text-slate-400">{{ t('chats.managers.loading') }}</div>
        <div v-else class="space-y-2">
          <div class="text-[11px] text-slate-300">{{ t('chats.managers.count', { count: managersData.managers?.length || 0 }) }}</div>
          <div v-if="managersStats" class="rounded-xl bg-slate-900/55 p-2.5 text-[11px] text-slate-200 ring-1 ring-slate-700/45">
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
          <div class="space-y-1.5">
            <div v-for="m in (managersData.managers || [])" :key="`m-${m.user_id}`" class="flex items-center justify-between gap-2 rounded-xl bg-slate-900/60 px-2.5 py-2.5 text-xs shadow-[0_12px_30px_-22px_rgba(0,0,0,0.95)] ring-1 ring-slate-700/40 backdrop-blur-xl">
              <div class="min-w-0 flex-1">
                <span class="truncate">
                  {{ m.first_name || (m.username ? '@'+m.username : m.user_id) }}
                  <span class="text-slate-400">({{ m.user_id }})</span>
                </span>
                <div class="mt-0.5 flex flex-wrap items-center gap-1">
                  <span
                    class="inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold"
                    :class="m.is_online ? 'bg-emerald-500/20 text-emerald-200 ring-1 ring-emerald-400/30' : 'bg-slate-500/20 text-slate-300 ring-1 ring-slate-400/25'"
                  >
                    {{ m.is_online ? t('chats.managers.online') : t('chats.managers.offline') }}
                  </span>
                  <span
                    v-for="perm in managerPermEntries(m.permissions)"
                    :key="`mp-${m.user_id}-${perm.key}`"
                    class="inline-flex items-center gap-1 rounded-full bg-violet-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-violet-100 ring-1 ring-violet-400/30"
                  >
                    {{ perm.label }}
                    <button
                      v-if="managersData.can_manage_access"
                      type="button"
                      class="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full bg-violet-900/35 text-[10px] leading-none text-white ring-1 ring-violet-300/35"
                      @click.stop="removeManagerPermission(m, perm.key)"
                    >
                      ✕
                    </button>
                  </span>
                </div>
              </div>
              <div class="flex items-center gap-1">
                <button
                  v-if="managersData.can_manage_access"
                  type="button"
                  class="rounded-lg bg-red-950/35 px-1.5 py-0.5 text-[11px] text-red-200 ring-1 ring-red-400/35"
                  @click="removeManager(m.user_id)"
                >
                  {{ t('chats.managers.remove') }}
                </button>
              </div>
            </div>
            <p v-if="!(managersData.managers || []).length" class="text-xs text-slate-400">{{ t('chats.managers.empty') }}</p>
          </div>
          <div v-if="managersData.can_manage_access" class="space-y-1">
            <p class="text-[11px] text-slate-300">{{ t('chats.managers.invites_label') }}</p>
            <div v-for="inv in (managersData.invites || [])" :key="`inv-${inv.id}`" class="flex items-center justify-between rounded-lg bg-slate-900/55 px-2 py-1.5 text-[11px] ring-1 ring-slate-700/40">
              <span class="truncate text-slate-200">
                {{ inv.target_username ? '@' + inv.target_username : (inv.target_telegram_id || '—') }}
              </span>
              <div class="flex items-center gap-1.5">
                <span class="text-slate-300">{{ inviteStatusLabel(inv.status) }}</span>
                <button
                  v-if="managersData.can_manage_access && inv.status !== 'connected'"
                  type="button"
                  class="rounded-lg bg-amber-950/35 px-1.5 py-0.5 text-[10px] text-amber-200 ring-1 ring-amber-400/35"
                  @click="cancelInvite(inv.id)"
                >
                  {{ t('chats.managers.cancel_invite') }}
                </button>
              </div>
            </div>
            <p v-if="!(managersData.invites || []).length" class="text-[11px] text-slate-500">{{ t('chats.managers.no_invites') }}</p>
          </div>
          <div v-if="managersData.can_manage_access" class="mt-2 space-y-2 rounded-2xl bg-gradient-to-b from-slate-900/70 to-slate-950/65 p-3 backdrop-blur-xl ring-1 ring-slate-700/45">
            <input v-model="addManagerValue" type="text" class="w-full rounded-xl bg-slate-950/80 px-3 py-2 text-xs text-white outline-none ring-1 ring-slate-700/45 transition focus:ring-cyan-400/40"
              @keydown.enter.prevent="onAddManagerInputEnter"
              :placeholder="t('chats.managers.invite_placeholder')" />
            <button
              type="button"
              class="guard-green-soft rounded-xl px-4 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="managersLoading || !String(addManagerValue || '').trim()"
              @click="onAddManagerPrimaryClick"
            >
              {{ addManagerPermsOpen ? t('chats.managers.confirm_perms') : t('chats.managers.pick_perms') }}
            </button>
          </div>
          <p v-if="managersData.premium_enabled === false" class="text-xs text-amber-300">
            {{ t('chats.managers.access_premium_only') }}
          </p>
          <p v-if="!managersData.can_manage_access && managersData.premium_enabled !== false" class="text-xs text-slate-400">
            {{ t('chats.managers.owner_only') }}
          </p>
        </div>
      </div>
    </div>
    </Teleport>

    <Teleport to="body">
    <div
      v-if="managersModalChat && addManagerPermsOpen"
      class="fixed inset-0 z-[315] flex items-center justify-center bg-black/75 px-4"
      @click.self="addManagerPermsOpen = false"
    >
      <form
        class="w-full max-w-md rounded-2xl bg-gradient-to-b from-slate-900/96 to-slate-950/98 p-4 shadow-[0_28px_80px_-30px_rgba(0,0,0,0.95)] ring-1 ring-slate-700/50"
        @submit.prevent="addManager"
      >
        <div class="mb-3 flex items-center justify-end">
          <button type="button" class="rounded-lg px-2 py-1 text-sm text-slate-400 hover:bg-slate-800/80 hover:text-white" @click="addManagerPermsOpen = false">✕</button>
        </div>
        <div v-if="!isManagersChannel" class="flex flex-wrap gap-1.5">
          <label class="inline-flex items-center gap-1.5 rounded-xl bg-slate-900/65 px-2.5 py-1.5 text-[11px] text-slate-100 ring-1 ring-slate-700/45">
            <input v-model="addManagerPerms.protection" type="checkbox" class="h-3.5 w-3.5 accent-emerald-400" />
            <span>{{ t('chats.perm_help.protection') }}</span>
          </label>
          <label class="inline-flex items-center gap-1.5 rounded-xl bg-slate-900/65 px-2.5 py-1.5 text-[11px] text-slate-100 ring-1 ring-slate-700/45">
            <input v-model="addManagerPerms.broadcast" type="checkbox" class="h-3.5 w-3.5 accent-violet-400" />
            <span>{{ t('chats.perm_help.broadcast') }}</span>
          </label>
          <label class="inline-flex items-center gap-1.5 rounded-xl bg-slate-900/65 px-2.5 py-1.5 text-[11px] text-slate-100 ring-1 ring-slate-700/45">
            <input v-model="addManagerPerms.stats" type="checkbox" class="h-3.5 w-3.5 accent-sky-400" />
            <span>{{ t('chats.perm_help.stats') }}</span>
          </label>
          <label class="inline-flex items-center gap-1.5 rounded-xl bg-slate-900/65 px-2.5 py-1.5 text-[11px] text-slate-100 ring-1 ring-slate-700/45">
            <input v-model="addManagerPerms.reports" type="checkbox" class="h-3.5 w-3.5 accent-cyan-400" />
            <span>{{ t('chats.perm_help.reports') }}</span>
          </label>
        </div>
        <div v-else class="flex flex-wrap gap-1.5">
          <label class="inline-flex items-center gap-1.5 rounded-xl bg-slate-900/65 px-2.5 py-1.5 text-[11px] text-slate-100 ring-1 ring-slate-700/45">
            <input v-model="addManagerPerms.broadcast" type="checkbox" class="h-3.5 w-3.5 accent-violet-400" />
            <span>{{ t('chats.perm_help.broadcast_label') }}</span>
          </label>
          <label class="inline-flex items-center gap-1.5 rounded-xl bg-slate-900/65 px-2.5 py-1.5 text-[11px] text-slate-100 ring-1 ring-slate-700/45">
            <input v-model="addManagerPerms.first_post_settings" type="checkbox" class="h-3.5 w-3.5 accent-amber-400" />
            <span>{{ t('chats.perm_help.first_post') }}</span>
          </label>
        </div>
        <div class="mt-4 flex gap-2">
          <button type="button" class="flex-1 rounded-xl bg-slate-800/85 px-3 py-2 text-xs font-semibold text-slate-200 ring-1 ring-slate-700/45" @click="addManagerPermsOpen = false">{{ t('chats.managers.cancel') }}</button>
          <button type="submit" class="guard-green-soft flex-1 rounded-xl px-3 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50" :disabled="managersLoading || !canSubmitNewManager">
            {{ t('chats.managers.add') }}
          </button>
        </div>
      </form>
    </div>
    </Teleport>

    <Teleport to="body">
    <div
      v-if="showCabinetInfoModal"
      class="fixed inset-0 z-[320] flex items-end justify-center overscroll-none bg-black/70 px-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] pt-[max(12px,calc(env(safe-area-inset-top,0px)+48px))] md:items-center md:pb-6"
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
    </Teleport>

    <Teleport to="body">
    <div
      v-if="showDelegatedInfoModal"
      class="fixed inset-0 z-[320] flex items-end justify-center overscroll-none bg-black/70 px-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] pt-[max(12px,calc(env(safe-area-inset-top,0px)+48px))] md:items-center md:pb-6"
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
      </div>
    </div>
    </Teleport>

    <Teleport to="body">
    <div
      v-if="showManagersInfoModal"
      class="fixed inset-0 z-[330] flex items-end justify-center overscroll-none bg-black/70 px-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] pt-[max(12px,calc(env(safe-area-inset-top,0px)+48px))] md:items-center md:pb-6"
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
    </Teleport>

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

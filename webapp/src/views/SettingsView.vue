<script setup>
/**
 * Настройки Mini App — премиальный «Apple» стиль, подтверждения по типам действий, PIN 4 цифры.
 */
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { useApi, messageFromApiError } from '../composables/useApi'
import { useToast } from '../composables/useToast'
import NavIcon from '../components/NavIcon.vue'
import { formatDateRu, formatDateTimeShortRu } from '../utils/formatDateTime'
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

const router = useRouter()
const { hasInitData, fetchSilent } = useApi()
const { showToast } = useToast()

const LANG_KEY = 'guard.settings.lang'
const LANG_AUTO_KEY = 'guard.settings.lang_auto'
const DELEGATION_ON_KEY = 'guard.settings.delegation_enabled'
const RETENTION_KEY = 'guard.settings.retention_months'
const SESSIONS_KEY = 'guard.webapp_sessions_v1'
const LOGIN_HIST_KEY = 'guard.login_history_v1'

/** Экран навигации (не путать с window.screen) */
const panel = ref('hub')
const me = ref(null)
const botInfo = ref(null)
const loading = ref(true)
const bootErr = ref('')

const delegationLoading = ref(false)
const delegationRows = ref([])
const purgeLoading = ref(false)
const showPurgeConfirm = ref(false)
const pdfBusy = ref(false)

const langs = [
  { code: 'ru', label: 'Русский' },
  { code: 'en', label: 'English' },
]

const retentionOptions = [
  { months: 3, label: '3 месяца' },
  { months: 6, label: '6 месяцев' },
  { months: 12, label: '12 месяцев' },
  { months: 24, label: '24 месяца' },
]

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

const uiLang = ref(readLs(LANG_KEY, 'ru'))
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

watch(uiLang, (v) => writeLs(LANG_KEY, String(v || 'ru')))
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
  const o = retentionOptions.find((x) => x.months === Number(retentionMonths.value))
  return o?.label || `${retentionMonths.value} мес.`
})

const botDisplayName = computed(() => 'Guard Bot')
const botHandle = computed(() => {
  const u = String(botInfo.value?.username || '').replace(/^@/, '')
  return u ? `@${u}` : '@guard_bot'
})

const isPremium = computed(() => !!me.value?.is_premium)
const subscriptionUntilShort = computed(() => formatDateRu(me.value?.subscription_until))
/** Строка статуса подписки в том же духе, что блок тарифа на главной */
const mainScreenSubscriptionSummary = computed(() => {
  const m = me.value
  if (!m) return 'Загрузка…'
  const prem =
    !!m.is_premium || ['premium', 'pro', 'business'].includes(String(m.tariff || 'free').toLowerCase())
  if (!prem) return 'Тариф Free · Premium не активен'
  const until = subscriptionUntilShort.value
  if (until && until !== '—') return `Premium активна · до ${until}`
  return 'Premium активна'
})

/** Инвалидация computed после записи PIN в localStorage */
const pinStateRev = ref(0)
const pinIsSet = computed(() => {
  void pinStateRev.value
  return !!loadPinHash()
})

const paymentMethodLabel = computed(() => {
  const source = String(me.value?.subscription_source || '').toLowerCase()
  if (source === 'promo') return 'Промокод'
  const p = String(me.value?.payment_method_type || '').toLowerCase()
  if (p.includes('card')) return 'ЮKassa (карта)'
  if (p.includes('sbp')) return 'ЮKassa (СБП)'
  if (p.includes('yoo_money')) return 'ЮKassa'
  if (p) return `ЮKassa (${p})`
  return '—'
})

function sessionFingerprint() {
  try {
    const sw = typeof globalThis !== 'undefined' && globalThis.screen ? globalThis.screen.width : 0
    const sh = typeof globalThis !== 'undefined' && globalThis.screen ? globalThis.screen.height : 0
    const raw = `${navigator.userAgent}|${navigator.language}|${sw}x${sh}`
    let h = 0
    for (let i = 0; i < raw.length; i++) h = (Math.imul(31, h) + raw.charCodeAt(i)) | 0
    return `fp_${(h >>> 0).toString(16)}`
  } catch {
    return `fp_${Date.now()}`
  }
}

function deviceLabelFromUA() {
  const ua = navigator.userAgent || ''
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
  if (/Linux/i.test(ua)) return 'Браузер · Linux'
  return 'Это устройство'
}

function touchSessions() {
  const fp = sessionFingerprint()
  let list = []
  try {
    list = JSON.parse(readLs(SESSIONS_KEY, '[]') || '[]')
    if (!Array.isArray(list)) list = []
  } catch {
    list = []
  }
  const now = new Date().toISOString()
  const label = deviceLabelFromUA()
  let idx = list.findIndex((s) => s && s.fp === fp)
  if (idx < 0) {
    const id =
      typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : `s_${Date.now()}_${Math.random().toString(16).slice(2)}`
    list.unshift({ id, fp, label, lastSeen: now })
    idx = 0
  } else {
    list[idx].lastSeen = now
    list[idx].label = label
  }
  const curFp = fp
  list = list.slice(0, 14).map((s) => ({
    ...s,
    current: s.fp === curFp,
  }))
  try {
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(list))
  } catch {
    //
  }
  sessions.value = list
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

function terminateOtherSessions() {
  const fp = sessionFingerprint()
  const next = sessions.value.filter((s) => s.fp === fp).map((s) => ({ ...s, current: true }))
  try {
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(next))
  } catch {
    //
  }
  sessions.value = next
  showToast('Другие сессии завершены на этом устройстве.')
}

async function loadMe() {
  if (!hasInitData.value) {
    loading.value = false
    return
  }
  loading.value = true
  bootErr.value = ''
  try {
    const [u, bi] = await Promise.all([
      fetchSilent(() => api.me()),
      fetchSilent(() => api.botInfo()),
    ])
    me.value = u
    botInfo.value = bi
  } catch (e) {
    bootErr.value = messageFromApiError(e, 'Не удалось загрузить профиль')
  } finally {
    loading.value = false
  }
}

function managerRoleLabel(perms) {
  const p = perms || {}
  const prot = !!p.protection
  const rep = !!p.reports
  const br = !!p.broadcast
  const fp = !!p.first_post_settings
  if ((prot && rep && br) || (prot && rep)) return 'Администратор'
  if (prot || rep) return 'Модератор'
  if (br || fp) return 'Модератор'
  return 'Модератор'
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
  if (!me.value || pdfBusy.value) return
  pdfBusy.value = true
  try {
    const pdfMake = (await import('pdfmake/build/pdfmake')).default
    const vfs = (await import('pdfmake/build/vfs_fonts')).default
    pdfMake.vfs = vfs

    const lines = [
      { text: 'AntiSpam Guard — экспорт данных', style: 'h1', margin: [0, 0, 0, 8] },
      { text: `Сформировано: ${formatDateTimeShortRu(new Date().toISOString())}`, style: 'muted', margin: [0, 0, 0, 14] },
      { text: 'Аккаунт', style: 'h2', margin: [0, 6, 0, 4] },
      `Telegram ID: ${me.value.telegram_id ?? '—'}`,
      `Имя: ${me.value.first_name || '—'}`,
      `@username: ${me.value.username ? `@${me.value.username}` : '—'}`,
      `Тариф: ${me.value.is_premium ? 'Premium' : 'Free'}`,
      `Подписка до: ${formatDateRu(me.value.subscription_until)}`,
      `Способ оплаты (последний): ${paymentMethodLabel.value}`,
      `Период хранения (настройка в приложении): ${retentionLabel.value}`,
      { text: 'Чаты', style: 'h2', margin: [0, 14, 0, 4] },
      `Подключено чатов: ${me.value.chats_count ?? '—'}`,
      `Группы / каналы: ${me.value.groups_count ?? '—'} / ${me.value.channels_count ?? '—'}`,
      {
        text: 'Файл создан из раздела «Настройки» Mini App. Не содержит переписку пользователей.',
        style: 'muted',
        margin: [0, 18, 0, 0],
      },
    ]

    const doc = {
      content: lines.map((x) => (typeof x === 'string' ? { text: x, margin: [0, 1, 0, 0] } : x)),
      styles: {
        h1: { fontSize: 16, bold: true },
        h2: { fontSize: 12, bold: true, color: '#444444' },
        muted: { fontSize: 9, color: '#666666' },
      },
      defaultStyle: { fontSize: 10 },
    }
    pdfMake.createPdf(doc).download(`guard-export-${me.value.telegram_id || 'profile'}.pdf`)
    showToast('PDF сохранён')
  } catch (e) {
    showToast(messageFromApiError(e, 'Не удалось собрать PDF'))
  } finally {
    pdfBusy.value = false
  }
}

async function runPurge() {
  if (purgeLoading.value) return
  purgeLoading.value = true
  try {
    await api.mePurgeOwnedChatsAnalytics()
    showToast('История и статистика по вашим чатам очищены')
    showPurgeConfirm.value = false
    await loadMe()
  } catch (e) {
    showToast(messageFromApiError(e, 'Не удалось очистить данные'))
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
  if (tid == null) {
    showToast('Нет данных аккаунта')
    return
  }
  const p = String(pinEntry.value || '').replace(/\D/g, '').slice(0, 4)
  if (p.length !== 4) {
    showToast('Введите 4 цифры')
    return
  }
  pinBusy.value = true
  try {
    const ok = await verifyPin(tid, p, loadPinHash())
    if (!ok) {
      showToast('Неверный код')
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
  if (tid == null) {
    showToast('Нет данных аккаунта')
    return
  }
  const a = String(pinNew.value || '').replace(/\D/g, '').slice(0, 4)
  const b = String(pinNew2.value || '').replace(/\D/g, '').slice(0, 4)
  if (a.length !== 4 || b.length !== 4) {
    showToast('Код — ровно 4 цифры')
    return
  }
  if (a !== b) {
    showToast('Коды не совпадают')
    return
  }
  pinBusy.value = true
  try {
    const h = await hashPin(tid, a)
    savePinHash(h)
    savePinEnabled(true)
    pinEnabled.value = true
    pinStateRev.value += 1
    showToast('Код сохранён')
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
  showToast('Код отключён')
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

function goHistory() {
  router.push('/history').catch(() => {})
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
  if (['confirmActionsDetail', 'pinSetup', 'pinActions'].includes(panel.value)) {
    panel.value = 'security'
    return
  }
  panel.value = 'hub'
}

function panelTitle() {
  const titles = {
    profile: 'Профиль и аккаунт',
    payment: 'Оплата и подписка',
    data: 'Данные и статистика',
    delegation: 'Делегирование',
    security: 'Безопасность',
    languagePick: 'Язык',
    retentionPick: 'Период хранения',
    loginHistory: 'История входов',
    confirmActionsDetail: 'Подтверждения',
    pinSetup: 'Код безопасности',
    pinActions: 'Действия с кодом',
  }
  return titles[panel.value] || 'Настройки'
}

onMounted(() => {
  try {
    window?.Telegram?.WebApp?.expand?.()
  } catch {
    //
  }
  if (uiLang.value === 'uk') {
    uiLang.value = 'ru'
    writeLs(LANG_KEY, 'ru')
  }
  document.documentElement.lang = uiLang.value === 'en' ? 'en' : 'ru'
  confirmMap.value = { ...loadConfirmMap() }
  pinMap.value = { ...loadPinMap() }
  pinEnabled.value = loadPinEnabled()
  touchSessions()
  touchLoginHistory()
  loadMe()
})

watch(uiLang, (v) => {
  document.documentElement.lang = v === 'en' ? 'en' : 'ru'
})
</script>

<template>
  <div
    class="settings-root mx-auto max-w-lg space-y-4 pb-10 text-[15px] leading-snug tracking-[-0.01em] text-white antialiased"
  >
    <!-- Hub -->
    <template v-if="panel === 'hub'">
      <div class="px-0.5 pt-1">
        <h1 class="text-[28px] font-semibold tracking-[-0.03em] text-white">Настройки</h1>
      </div>

      <div
        v-if="!hasInitData"
        class="rounded-[22px] border border-amber-400/20 bg-amber-500/[0.08] px-4 py-3.5 text-[14px] text-amber-100/95 backdrop-blur-xl"
      >
        Откройте панель из Telegram.
      </div>
      <div
        v-else-if="loading"
        class="rounded-[22px] border border-white/[0.1] bg-white/[0.06] px-4 py-14 text-center text-[14px] text-white/40 backdrop-blur-xl"
      >
        Загрузка…
      </div>
      <div
        v-else-if="bootErr"
        class="rounded-[22px] border border-rose-400/25 bg-rose-500/[0.1] px-4 py-3.5 text-[14px] text-rose-100 backdrop-blur-xl"
      >
        {{ bootErr }}
      </div>

      <div v-else class="space-y-2">
        <button
          v-for="row in [
            { key: 'profile', title: 'Профиль и аккаунт', sub: 'Язык, тариф и сервисный профиль', icon: 'account' },
            { key: 'payment', title: 'Оплата и подписка', sub: 'История операций и продление', icon: 'billing' },
            { key: 'data', title: 'Данные и статистика', sub: 'Экспорт PDF, хранение, очистка', icon: 'reports' },
            { key: 'delegation', title: 'Делегирование', sub: 'Доступы к вашим чатам без передачи владения', icon: 'chats' },
            { key: 'security', title: 'Безопасность', sub: 'Сессии, подтверждения и код', icon: 'shield' },
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
          Назад
        </button>
      </div>

      <!-- Profile -->
      <div v-if="panel === 'profile'" class="space-y-3 pt-3">
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
            <span class="mt-1 block text-[11px] text-white/35">Сервис AntiSpam Guard в Telegram</span>
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
            <span class="block text-[16px] font-semibold text-white">{{ me.first_name || 'Аккаунт' }}</span>
            <span class="block text-[13px] text-white/45">{{ me.username ? `@${me.username}` : 'username скрыт' }}</span>
            <span class="mt-0.5 block text-[11px] font-mono text-white/35">ID {{ me.telegram_id }}</span>
          </span>
        </div>

        <div
          class="rounded-[22px] border border-violet-400/20 bg-gradient-to-br from-violet-500/[0.14] via-indigo-500/[0.08] to-transparent p-4 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.08)] backdrop-blur-2xl"
        >
          <div class="flex items-start gap-3">
            <span class="text-2xl opacity-95">👑</span>
            <div class="min-w-0 flex-1">
              <p class="text-[11px] font-medium uppercase tracking-[0.12em] text-violet-200/65">Тариф</p>
              <p class="mt-1 text-[18px] font-semibold text-white">{{ isPremium ? 'Premium' : 'Free' }}</p>
              <div class="mt-2 flex flex-wrap items-center gap-2">
                <span
                  class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold"
                  :class="isPremium ? 'border-emerald-400/35 bg-emerald-400/15 text-emerald-100' : 'border-white/15 bg-white/[0.06] text-white/55'"
                >
                  <span class="h-1.5 w-1.5 rounded-full" :class="isPremium ? 'bg-emerald-300' : 'bg-white/35'" />
                  {{ isPremium ? 'Активен' : 'Не активен' }}
                </span>
                <span v-if="isPremium" class="text-[13px] text-white/70">До {{ subscriptionUntilShort }}</span>
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
            <span class="text-[15px] font-medium text-white">Язык приложения</span>
            <span class="flex items-center gap-1 text-[14px] text-white/45">
              {{ langLabel }}
              <NavIcon name="chevron-right" class="h-4 w-4 text-white/25" />
            </span>
          </button>
          <div class="mx-4 h-px bg-white/[0.08]" />
          <div class="flex items-center justify-between gap-3 px-4 py-3.5">
            <div>
              <p class="text-[15px] font-medium text-white">Автоопределение языка</p>
              <p class="mt-0.5 text-[12px] text-white/35">По языку Telegram / системы</p>
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
      </div>

      <!-- Payment -->
      <div v-if="panel === 'payment'" class="space-y-3 pt-3">
        <button
          type="button"
          class="flex w-full items-center gap-3.5 rounded-[22px] border border-white/[0.11] bg-white/[0.07] px-4 py-4 text-left shadow-[inset_0_1px_0_0_rgba(255,255,255,0.07)] backdrop-blur-2xl transition hover:bg-white/[0.09]"
          @click="goHistory"
        >
          <span class="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-violet-400/25 bg-violet-500/10 text-lg">
            📜
          </span>
          <span class="min-w-0 flex-1">
            <span class="block text-[16px] font-semibold text-white">История операций</span>
            <span class="mt-0.5 block text-[13px] text-white/45">Все операции и платежи</span>
          </span>
          <NavIcon name="chevron-right" class="h-5 w-5 shrink-0 text-white/25" />
        </button>

        <div
          class="rounded-[22px] border border-violet-400/22 bg-gradient-to-br from-violet-500/[0.14] via-indigo-500/[0.07] to-transparent p-4 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.08)] backdrop-blur-2xl"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="flex items-start gap-2">
              <span class="text-2xl">👑</span>
              <div>
                <p class="text-[18px] font-semibold text-white">{{ isPremium ? 'Premium' : 'Free' }}</p>
                <p class="mt-0.5 text-[13px] text-white/45">
                  {{ isPremium ? 'Подписка активна' : 'Оформите Premium для расширенных функций' }}
                </p>
                <p v-if="isPremium" class="mt-1 text-[14px] text-white/75">до {{ subscriptionUntilShort }}</p>
              </div>
            </div>
            <span
              class="shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide"
              :class="isPremium ? 'border-emerald-400/35 bg-emerald-400/12 text-emerald-100' : 'border-white/15 bg-white/[0.06] text-white/45'"
            >
              {{ isPremium ? 'Активна' : 'Нет' }}
            </span>
          </div>
          <button
            type="button"
            class="mt-4 w-full rounded-2xl border border-violet-300/35 bg-violet-500/[0.18] py-3.5 text-[15px] font-semibold text-white shadow-[0_16px_40px_-20px_rgba(139,92,246,0.65)] transition hover:bg-violet-500/[0.26]"
            @click="goBilling"
          >
            Продлить подписку
          </button>
          <p class="mt-3 rounded-xl bg-black/25 px-3 py-2.5 text-center text-[13px] leading-snug text-white/80 ring-1 ring-white/[0.06]">
            {{ mainScreenSubscriptionSummary }}
          </p>
        </div>
      </div>

      <!-- Data -->
      <div v-if="panel === 'data'" class="space-y-3 pt-3">
        <p class="px-1 text-[12px] font-medium uppercase tracking-[0.14em] text-white/35">Экспорт данных</p>
        <button
          type="button"
          class="flex w-full items-center gap-3.5 rounded-[22px] border border-rose-400/22 bg-white/[0.07] px-4 py-4 text-left shadow-[inset_0_1px_0_0_rgba(255,255,255,0.06)] backdrop-blur-2xl disabled:opacity-45"
          :disabled="pdfBusy || !me"
          @click="exportPdf"
        >
          <span class="text-2xl">📕</span>
          <span class="min-w-0 flex-1">
            <span class="block text-[16px] font-semibold text-white">Экспорт в PDF</span>
            <span class="mt-0.5 block text-[13px] text-white/45">Сводка аккаунта и лимитов</span>
          </span>
          <NavIcon name="chevron-right" class="h-5 w-5 shrink-0 text-white/25" />
        </button>

        <p class="px-1 pt-1 text-[12px] font-medium uppercase tracking-[0.14em] text-white/35">Хранение данных</p>
        <div class="overflow-hidden rounded-[22px] border border-white/[0.11] bg-white/[0.06] backdrop-blur-2xl">
          <button
            type="button"
            class="flex w-full items-center justify-between gap-3 px-4 py-3.5 text-left transition hover:bg-white/[0.04]"
            @click="panel = 'retentionPick'"
          >
            <span class="text-[15px] font-medium text-white">Период хранения</span>
            <span class="flex items-center gap-1 text-[14px] text-white/45">
              {{ retentionLabel }}
              <NavIcon name="chevron-right" class="h-4 w-4 text-white/25" />
            </span>
          </button>
          <div class="border-t border-white/[0.08] px-4 py-3.5">
            <p class="text-[13px] font-medium text-white/65">Что хранится:</p>
            <ul class="mt-2 space-y-2 text-[14px] leading-relaxed text-white/45">
              <li class="flex gap-2.5"><span class="text-emerald-400/90">·</span> Сообщения и активность в ваших чатах</li>
              <li class="flex gap-2.5"><span class="text-emerald-400/90">·</span> Действия модерации</li>
              <li class="flex gap-2.5"><span class="text-emerald-400/90">·</span> Статистика роста аудитории</li>
            </ul>
          </div>
        </div>

        <p class="px-1 pt-1 text-[12px] font-medium uppercase tracking-[0.14em] text-white/35">Очистка данных</p>
        <button
          type="button"
          class="w-full rounded-[22px] border border-rose-400/30 bg-rose-500/[0.1] px-4 py-4 text-left shadow-[inset_0_1px_0_0_rgba(255,255,255,0.06)] backdrop-blur-xl transition hover:bg-rose-500/[0.14] disabled:opacity-45"
          :disabled="purgeLoading"
          @click="startPurge"
        >
          <p class="text-[16px] font-semibold text-rose-100">Очистить историю</p>
          <p class="mt-1 text-[13px] text-rose-200/65">Удалить старые данные и статистику по вашим чатам</p>
        </button>
        <div
          class="rounded-2xl border border-rose-400/28 bg-rose-500/[0.08] px-3.5 py-2.5 text-[12px] leading-relaxed text-rose-100/90 backdrop-blur-lg"
        >
          Необратимое действие. При необходимости сначала введите код безопасности.
        </div>

        <div
          v-if="showPurgeConfirm"
          class="fixed inset-0 z-[80] flex items-end justify-center bg-black/55 p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] backdrop-blur-md sm:items-center"
          role="dialog"
          aria-modal="true"
          @click.self="showPurgeConfirm = false"
        >
          <div
            class="w-full max-w-md overflow-hidden rounded-[24px] border border-white/[0.14] bg-[#1c1c1e]/95 p-5 shadow-2xl backdrop-blur-2xl"
          >
            <p class="text-[17px] font-semibold text-white">Подтвердить очистку?</p>
            <p class="mt-2 text-[14px] leading-relaxed text-white/45">
              Будут удалены журнал модерации и события активности по чатам, где вы владелец. Платежи и подписка не затрагиваются.
            </p>
            <div class="mt-5 flex gap-2.5">
              <button
                type="button"
                class="flex-1 rounded-2xl border border-white/[0.14] bg-white/[0.06] py-3 text-[15px] font-medium text-white transition hover:bg-white/[0.1]"
                @click="showPurgeConfirm = false"
              >
                Отмена
              </button>
              <button
                type="button"
                class="flex-1 rounded-2xl border border-rose-400/35 bg-rose-500 py-3 text-[15px] font-semibold text-white shadow-lg disabled:opacity-50"
                :disabled="purgeLoading"
                @click="runPurge"
              >
                {{ purgeLoading ? 'Удаление…' : 'Очистить' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Delegation -->
      <div v-if="panel === 'delegation'" class="space-y-3 pt-3">
        <div class="rounded-[22px] border border-cyan-400/18 bg-white/[0.06] p-4 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.07)] backdrop-blur-2xl">
          <div class="flex items-start justify-between gap-3">
            <div>
              <p class="text-[16px] font-semibold text-white">Делегирование</p>
              <p class="mt-1 text-[13px] leading-relaxed text-white/45">
                Доверенные люди управляют чатами в Guard без передачи владения в Telegram.
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
          <span class="text-[15px] font-medium text-white">Подключённые чаты</span>
          <NavIcon name="chevron-right" class="h-5 w-5 text-white/25" />
        </button>

        <div v-if="delegationLoading" class="py-12 text-center text-[14px] text-white/35">Загрузка списка…</div>
        <div
          v-else-if="!delegationEnabled"
          class="rounded-[22px] border border-white/[0.08] bg-white/[0.04] px-4 py-10 text-center text-[14px] text-white/40 backdrop-blur-xl"
        >
          Включите делегирование, чтобы добавлять администраторов Mini App к вашим чатам.
        </div>
        <div v-else class="space-y-2">
          <p class="px-1 text-[12px] font-medium uppercase tracking-[0.14em] text-white/35">Список делегированных</p>
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
                :class="row.role === 'Администратор' ? 'border-emerald-400/35 text-emerald-200' : 'border-sky-400/35 text-sky-200'"
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
            Пока нет делегированных администраторов. Откройте чат в списке подключённых и добавьте менеджера (Premium).
          </div>
        </div>

        <button
          type="button"
          class="w-full rounded-[22px] border border-emerald-400/35 bg-emerald-500/[0.16] py-3.5 text-[15px] font-semibold text-emerald-50 shadow-[0_18px_44px_-24px_rgba(52,211,153,0.7)] backdrop-blur-xl transition hover:bg-emerald-500/[0.24] disabled:opacity-40"
          :disabled="!delegationEnabled"
          @click="goChats"
        >
          Добавить делегирование
        </button>
      </div>

      <!-- Security -->
      <div v-if="panel === 'security'" class="space-y-3 pt-3">
        <div class="rounded-[22px] border border-white/[0.11] bg-white/[0.06] p-4 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.07)] backdrop-blur-2xl">
          <p class="text-[14px] font-medium text-white/65">Активные сессии</p>
          <p class="mt-1 text-[13px] text-white/40">Зафиксировано записей: {{ sessions.length }}</p>
          <div class="mt-3 space-y-2">
            <div
              v-for="s in sessions"
              :key="s.id"
              class="flex items-center gap-2 rounded-2xl border border-white/[0.08] bg-black/20 px-3 py-2.5 backdrop-blur-md"
            >
              <div class="min-w-0 flex-1">
                <p class="truncate text-[14px] font-medium text-white">
                  {{ s.label }}
                  <span v-if="s.current" class="ml-1 text-[12px] font-normal text-emerald-300/95">(это устройство)</span>
                </p>
                <p class="text-[11px] text-white/35">Последняя активность · {{ formatDateTimeShortRu(s.lastSeen) }}</p>
              </div>
              <span class="shrink-0 text-white/25">⋯</span>
            </div>
          </div>
          <button
            type="button"
            class="mt-4 w-full rounded-2xl border border-rose-400/35 bg-rose-500/[0.12] py-3 text-[14px] font-semibold text-rose-100 transition hover:bg-rose-500/[0.18]"
            @click="terminateOtherSessions"
          >
            Завершить все сессии
          </button>
        </div>

        <div class="overflow-hidden rounded-[22px] border border-white/[0.11] bg-white/[0.06] shadow-[inset_0_1px_0_0_rgba(255,255,255,0.07)] backdrop-blur-2xl">
          <div class="flex items-center justify-between gap-3 px-4 py-3.5">
            <div>
              <p class="text-[15px] font-medium text-white">Подтверждение действий</p>
              <p class="mt-0.5 text-[12px] text-white/35">Диалог перед важными операциями</p>
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
            <span class="text-[14px] text-white/80">Какие действия подтверждать</span>
            <NavIcon name="chevron-right" class="h-5 w-5 text-white/25" />
          </button>
        </div>

        <div class="overflow-hidden rounded-[22px] border border-white/[0.11] bg-white/[0.06] shadow-[inset_0_1px_0_0_rgba(255,255,255,0.07)] backdrop-blur-2xl">
          <div class="flex items-center justify-between gap-3 px-4 py-3.5">
            <div>
              <p class="text-[15px] font-medium text-white">Двухфакторный код</p>
              <p class="mt-0.5 text-[12px] text-white/35">4 цифры перед выбранными действиями</p>
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
            <span class="text-[14px] text-white/80">Запрашивать код для действий</span>
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
            <span class="text-[14px] text-white/80">{{ pinIsSet ? 'Сменить код' : 'Задать код (4 цифры)' }}</span>
            <NavIcon name="chevron-right" class="h-5 w-5 text-white/25" />
          </button>
        </div>

        <button
          type="button"
          class="flex w-full items-center justify-between gap-3 rounded-[22px] border border-white/[0.11] bg-white/[0.06] px-4 py-3.5 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.07)] backdrop-blur-2xl transition hover:bg-white/[0.08]"
          @click="panel = 'loginHistory'"
        >
          <span class="text-[15px] font-medium text-white">История входов</span>
          <NavIcon name="chevron-right" class="h-5 w-5 text-white/25" />
        </button>
      </div>

      <!-- Confirm detail -->
      <div v-if="panel === 'confirmActionsDetail'" class="space-y-0 pt-3">
        <p class="mb-2 px-1 text-[12px] text-white/35">Отметьте, для чего показывать подтверждение</p>
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
        <p class="mb-2 px-1 text-[12px] text-white/35">Где запрашивать 4-значный код</p>
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
          Придумайте код из 4 цифр. Он хранится только на этом устройстве (хэш), не передаётся на сервер.
        </p>
        <div class="space-y-3 rounded-[22px] border border-white/[0.11] bg-white/[0.06] p-4 backdrop-blur-2xl">
          <label class="block text-[12px] font-medium text-white/45">Код</label>
          <input
            v-model="pinNew"
            type="password"
            inputmode="numeric"
            maxlength="4"
            autocomplete="off"
            class="w-full rounded-2xl border border-white/[0.12] bg-black/30 px-4 py-3.5 text-center text-[22px] font-semibold tracking-[0.4em] text-white outline-none ring-0 focus:border-emerald-400/40"
            placeholder="••••"
          />
          <label class="block text-[12px] font-medium text-white/45">Повторите код</label>
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
          Сохранить код
        </button>
      </div>

      <!-- Language picker -->
      <div v-if="panel === 'languagePick'" class="space-y-2 pt-3">
        <button
          v-for="l in langs"
          :key="l.code"
          type="button"
          class="flex w-full items-center justify-between rounded-[22px] border px-4 py-3.5 text-left transition"
          :class="uiLang === l.code ? 'border-emerald-400/35 bg-emerald-500/[0.12]' : 'border-white/[0.11] bg-white/[0.06]'"
          @click="
            uiLang = l.code;
            panel = 'profile'
          "
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
          Отображается в приложении и в PDF; серверная политика может отличаться.
        </p>
      </div>

      <!-- Login history -->
      <div v-if="panel === 'loginHistory'" class="space-y-2 pt-3">
        <div
          v-if="!loginHistory.length"
          class="rounded-[22px] border border-white/[0.1] px-4 py-12 text-center text-[14px] text-white/35"
        >
          Записей пока нет.
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

    <!-- PIN gate modal -->
    <div
      v-if="showPinModal"
      class="fixed inset-0 z-[90] flex items-end justify-center bg-black/55 p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] backdrop-blur-md sm:items-center"
      role="dialog"
      aria-modal="true"
      @click.self="showPinModal = false"
    >
      <div class="w-full max-w-md overflow-hidden rounded-[24px] border border-white/[0.14] bg-[#1c1c1e]/95 p-5 backdrop-blur-2xl">
        <p class="text-[17px] font-semibold text-white">Код безопасности</p>
        <p class="mt-1 text-[13px] text-white/45">Введите 4 цифры</p>
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
            Отмена
          </button>
          <button
            type="button"
            class="flex-1 rounded-2xl border border-emerald-400/35 bg-emerald-500 py-3 text-[15px] font-semibold text-white disabled:opacity-50"
            :disabled="pinBusy"
            @click="submitPinModal"
          >
            Далее
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

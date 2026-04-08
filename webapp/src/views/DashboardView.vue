<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi'
import NavIcon from '../components/NavIcon.vue'
import { useDashboardSection } from '../composables/useDashboardSection'
import { formatDateTimeRu } from '../utils/formatDateTime'

const router = useRouter()
const { api, loading, error, fetch, hasInitData } = useApi()
const { dashboardSection, setDashboardSection } = useDashboardSection()
const me = ref(null)
const showQuickStartModal = ref(false)
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
const payLoadingMonths = ref(null)
const showSubscriptionInfo = ref(false)
const subscriptionInfoWrapRef = ref(null)
const partnerData = ref(null)
const partnerLoading = ref(false)
const partnerError = ref('')
const partnerTab = ref('balance')
const refsMode = ref('full')
const referralPeople = ref({ full_list: [], top_active: [] })
const referralPeopleLoading = ref(false)

const tariffLabel = computed(() => {
  const t = (me.value?.tariff || 'free').toLowerCase()
  return ['premium', 'pro', 'business'].includes(t) ? 'PREMIUM' : 'FREE'
})
const totalTokens = computed(() => {
  const total = Number(me.value?.subscription_tokens || 0) + Number(me.value?.partner_tokens || 0)
  return String(Math.max(0, Math.round(total)))
})
const tariffIsPremium = computed(() => ['premium', 'pro', 'business'].includes((me.value?.tariff || 'free').toLowerCase()))
const tariffEmoji = computed(() => (tariffIsPremium.value ? '💎' : '💼'))
const guardFaceSrc = `${import.meta.env.BASE_URL}logo.png`
const quickTiles = [
  { key: 'billing', label: 'Подписка', icon: 'billing' },
  { key: 'tokens', label: 'Токены', icon: 'bolt' },
  { key: 'faq', label: 'FAQ', icon: 'help' },
  { key: 'more', label: 'Еще', icon: 'chevrons-down' },
]
const PREMIUM_PLANS = [
  { months: 1, icon: '🛡', label: '1 месяц', price: '490 ₽', savings: '' },
  { months: 3, icon: '⚡', label: '3 месяца', price: '990 ₽', savings: 'Экономия 480 ₽' },
  { months: 12, icon: '👑', label: '12 месяцев', price: '2790 ₽', savings: 'Экономия 3090 ₽' },
  { months: 24, icon: '💎', label: '24 месяца', price: '4790 ₽', savings: 'Экономия 6970 ₽' },
  { months: 72, icon: '🚀', label: '72 месяца', price: '10 990 ₽', savings: 'Экономия 24 290 ₽' },
]
const subscriptionUntilLabel = computed(() => formatDateTimeRu(me.value?.subscription_until))

onMounted(async () => {
  if (!hasInitData.value) return
  try {
    me.value = await fetch(() => api.me())
  } catch {
    //
  }
  if (!dashboardSection.value) setDashboardSection('account')
  if (dashboardSection.value === 'partner') {
    await ensurePartnerData()
    await ensureReferralPeople()
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
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onGlobalPointerDown, true)
})

function onGlobalPointerDown(event) {
  if (!showSubscriptionInfo.value) return
  const wrapEl = subscriptionInfoWrapRef.value
  const target = event?.target
  if (!wrapEl || !(target instanceof Node)) return
  if (!wrapEl.contains(target)) {
    showSubscriptionInfo.value = false
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

async function ensurePartnerData() {
  if (partnerData.value || partnerLoading.value) return
  partnerLoading.value = true
  partnerError.value = ''
  try {
    partnerData.value = await fetch(() => api.referral())
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
    referralPeople.value = await fetch(() => api.referralPeople())
  } catch {
    referralPeople.value = { full_list: [], top_active: [] }
  } finally {
    referralPeopleLoading.value = false
  }
}

watch(
  () => dashboardSection.value,
  (section) => {
    if (section === 'partner') {
      ensurePartnerData()
      ensureReferralPeople()
    }
  }
)

const partnerSubTokens = computed(() => {
  const v = Number(partnerData.value?.subscription_credits || 0)
  return Number.isInteger(v) ? String(v) : v.toFixed(2)
})
const partnerBonusTokens = computed(() => {
  const v = Number(partnerData.value?.bonus_credits || 0)
  return Number.isInteger(v) ? String(v) : v.toFixed(2)
})
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

async function loadHistoryIfNeeded() {
  if (historyPayments.value.length || historyTokens.value.length || historyLoading.value) return
  historyLoading.value = true
  try {
    const [p, t] = await Promise.all([fetch(() => api.historyPayments()), fetch(() => api.historyTokens())])
    historyPayments.value = p?.items || []
    historyTokens.value = t?.items || []
  } finally {
    historyLoading.value = false
  }
}

async function startPayment(months) {
  payLoadingMonths.value = months
  try {
    const r = await fetch(() => api.yookassaCreatePayment(months))
    const url = r?.confirmation_url
    if (!url) return
    const tg = window.Telegram?.WebApp
    if (typeof tg?.openLink === 'function') tg.openLink(url, { try_instant_view: false })
    else window.open(url, '_blank', 'noopener,noreferrer')
  } finally {
    payLoadingMonths.value = null
  }
}

async function applyPromo() {
  const code = (promoCode.value || '').trim()
  if (!code) return
  promoLoading.value = true
  try {
    await fetch(() => api.promoApply(code))
    promoCode.value = ''
    me.value = await fetch(() => api.me())
  } finally {
    promoLoading.value = false
  }
}

function openReceiptModal(item) {
  receiptTarget.value = item || null
  try {
    receiptFullName.value = localStorage.getItem(receiptNameKey()) || receiptFullName.value || ''
    receiptEmail.value = localStorage.getItem(receiptEmailKey()) || receiptEmail.value || ''
  } catch {
    //
  }
  showReceiptModal.value = true
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

    <div v-else-if="error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
      {{ error }}
    </div>

    <div v-else-if="me">
      <div class="grid grid-cols-[1fr_auto] items-start gap-2 p-1 text-white">
        <div class="min-w-0 p-2">
          <img
            :src="guardFaceSrc"
            alt="Guard"
            draggable="false"
            class="h-14 w-14 rounded-xl border border-white/20 object-cover"
            @dragstart.prevent
          />
          <p class="mt-3 text-2xl font-extrabold leading-none">
            {{ totalTokens }}
            <NavIcon name="bolt" class="ml-0.5 inline-block h-4 w-4 align-middle text-lime-400" />
          </p>
          <p class="mt-1 text-[13px] text-slate-200">{{ tariffEmoji }} {{ tariffLabel }}</p>
        </div>

        <div class="grid grid-cols-2 gap-1.5">
          <button
            v-for="tile in quickTiles"
            :key="tile.key"
            type="button"
            class="h-[74px] w-[92px] rounded-xl bg-slate-800 p-2 text-center text-[11px] font-semibold text-lime-300 transition duration-150 hover:bg-slate-700 hover:shadow-[0_0_0_1px_rgba(132,204,22,0.45)]"
            :class="dashboardSection === tile.key ? 'bg-slate-700 shadow-[0_0_0_1px_rgba(132,204,22,0.55)]' : ''"
            @click="
              tile.key === 'more'
                ? (showMoreMenu = !showMoreMenu)
                : tile.key === 'billing'
                  ? (showMoreMenu = false, setDashboardSection('billing'))
                  : (showMoreMenu = false, setDashboardSection(tile.key))
            "
          >
            <NavIcon :name="tile.icon" class="mx-auto h-6 w-6 text-lime-400" />
            <div class="mt-0.5">{{ tile.label }}</div>
          </button>
          <div class="relative">
            <div
              v-if="showMoreMenu"
              class="absolute right-0 top-[calc(100%+6px)] z-30 w-52 rounded-xl border border-slate-300 bg-white p-1.5 shadow-xl dark:border-slate-600 dark:bg-slate-800"
            >
              <button
                type="button"
                class="w-full rounded-lg px-3 py-2 text-left text-sm font-medium text-slate-800 hover:bg-slate-100 dark:text-slate-100 dark:hover:bg-slate-700"
                @click="showMoreMenu = false"
              >
                <span class="inline-flex items-center gap-2">
                  <NavIcon name="settings" class="h-4 w-4 text-slate-500 dark:text-slate-300" />
                  Настройки
                </span>
              </button>
              <button
                type="button"
                class="mt-1 w-full rounded-lg px-3 py-2 text-left text-sm font-medium text-slate-800 hover:bg-slate-100 dark:text-slate-100 dark:hover:bg-slate-700"
                @click="showMoreMenu = false; setDashboardSection('history'); loadHistoryIfNeeded()"
              >
                <span class="inline-flex items-center gap-2">
                  <NavIcon name="calculator" class="h-4 w-4 text-slate-500 dark:text-slate-300" />
                  Движение средств
                </span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="dashboardSection === 'account'" class="mt-2 grid gap-2 sm:grid-cols-2">
        <div ref="subscriptionInfoWrapRef" class="sm:col-span-2 relative flex items-center gap-2 px-1 py-1 text-slate-200">
          <NavIcon name="chats" class="h-4 w-4 text-slate-300" />
          <span class="text-sm font-semibold">{{ me?.chats_count || 0 }} / {{ me?.chat_limit || 0 }}</span>
          <button
            type="button"
            class="inline-flex h-5 w-5 items-center justify-center rounded-full border border-cyan-400/50 text-[11px] font-bold text-cyan-300 hover:bg-cyan-500/10"
            aria-label="Информация о чатах и подписке"
            @click="showSubscriptionInfo = !showSubscriptionInfo"
          >
            i
          </button>
          <div
            v-if="showSubscriptionInfo"
            class="absolute left-0 top-[calc(100%+6px)] z-20 w-72 rounded-xl border border-slate-600 bg-slate-900 p-2.5 text-xs text-slate-200 shadow-xl"
          >
            <p>Подключено чатов: <b>{{ me?.chats_count || 0 }} / {{ me?.chat_limit || 0 }}</b></p>
            <p class="mt-1">Подписка до: <b>{{ subscriptionUntilLabel }}</b></p>
          </div>
        </div>
        <button type="button" class="guard-green-soft rounded-xl px-4 py-2.5 text-sm font-semibold" @click="$router.push('/connect')">
          ➕ Подключить группу
        </button>
        <button type="button" class="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-800 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100" @click="setDashboardSection('partner')">
          🎁 Партнерство
        </button>
      </div>

      <div v-else-if="dashboardSection === 'partner'" class="mt-2 space-y-3">
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

        <div v-if="partnerLoading" class="rounded-xl border border-slate-700 bg-slate-900/80 p-4 text-sm text-slate-300">
          Загрузка партнерских данных...
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
              ├ Токены подписки: <b>{{ partnerSubTokens }} ⚡</b><br>
              └ Партнерские токены: <b>{{ partnerBonusTokens }} ⚡</b>
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
            <button type="button" class="guard-green-soft rounded-lg px-3 py-1.5 text-xs font-semibold" @click="fetch(() => api.referralBonusToSub()).then(() => ensurePartnerData())">
              Перевести в подписку
            </button>
            <button type="button" class="rounded-lg border border-sky-400/40 bg-sky-500/10 px-3 py-1.5 text-xs font-semibold text-sky-300" @click="sharePartnerLink">
              Поделиться
            </button>
          </div>
        </div>
        <div v-else-if="partnerData && partnerTab === 'refs'" class="space-y-2">
          <div class="h-16 rounded-[28px] bg-slate-700/45" />
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

            <div v-if="referralPeopleLoading" class="py-8 text-center text-base text-slate-500">
              Загрузка...
            </div>
            <div
              v-else-if="(refsMode === 'full' ? (referralPeople.full_list || []) : (referralPeople.top_active || [])).length === 0"
              class="py-10 text-center text-[44px] font-medium text-slate-700"
            >
              Рефералы отсутствуют.
            </div>
            <div v-else class="mt-3 space-y-2">
              <div
                v-for="item in (refsMode === 'full' ? referralPeople.full_list : referralPeople.top_active)"
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
        <div v-else-if="partnerData && partnerTab === 'docs'" class="rounded-xl border border-slate-700 bg-slate-900/80 p-4 text-sm text-slate-200">
          <p>• За оплату приглашенного начисляется 33% в партнерские токены.</p>
          <p class="mt-1">• Партнерские токены можно перевести в токены подписки.</p>
          <p class="mt-1">• Самые активные считаются по покупкам токенов и количеству успешных оплат.</p>
        </div>
      </div>

      <div v-else-if="dashboardSection === 'tokens'" class="mt-2 rounded-2xl bg-slate-900 p-5 text-white">
        <p class="rounded-xl border border-cyan-300/60 px-4 py-3 text-center text-base text-cyan-100">
          ℹ️ Купить токены можно только с активной подпиской
        </p>
        <template v-if="!tariffIsPremium">
          <button
            type="button"
            class="mt-4 guard-green-soft w-full rounded-xl px-4 py-2.5 text-base font-semibold"
            @click="setDashboardSection('billing')"
          >
            Приобрести подписку
          </button>
        </template>
        <template v-else>
          <div class="mt-4 grid grid-cols-3 gap-2">
            <button
              type="button"
              class="rounded-xl border border-lime-300/50 bg-slate-800 px-2 py-2 text-center text-xs font-semibold text-lime-300 hover:bg-slate-700"
              @click="fetch(() => api.yookassaCreateTokensPayment(50)).then(r => (window.Telegram?.WebApp?.openLink ? window.Telegram.WebApp.openLink(r.confirmation_url) : window.open(r.confirmation_url, '_blank')))"
            >
              50 ⚡<br>100 ₽
            </button>
            <button
              type="button"
              class="rounded-xl border border-lime-300/50 bg-slate-800 px-2 py-2 text-center text-xs font-semibold text-lime-300 hover:bg-slate-700"
              @click="fetch(() => api.yookassaCreateTokensPayment(150)).then(r => (window.Telegram?.WebApp?.openLink ? window.Telegram.WebApp.openLink(r.confirmation_url) : window.open(r.confirmation_url, '_blank')))"
            >
              150 ⚡<br>300 ₽
            </button>
            <button
              type="button"
              class="rounded-xl border border-lime-300/50 bg-slate-800 px-2 py-2 text-center text-xs font-semibold text-lime-300 hover:bg-slate-700"
              @click="fetch(() => api.yookassaCreateTokensPayment(300)).then(r => (window.Telegram?.WebApp?.openLink ? window.Telegram.WebApp.openLink(r.confirmation_url) : window.open(r.confirmation_url, '_blank')))"
            >
              300 ⚡<br>600 ₽
            </button>
          </div>
        </template>
      </div>

      <div v-else-if="dashboardSection === 'billing'" class="mt-2 rounded-2xl border border-primary-700/50 bg-slate-900 p-4 text-white">
        <h3 class="text-lg font-semibold">🛡 Guardian Premium</h3>
        <div class="mt-3 rounded-xl border border-slate-700 bg-slate-800 p-3">
          <p class="text-sm text-slate-200">🎁 Промокод</p>
          <div class="mt-2 flex gap-2">
            <input
              v-model="promoCode"
              type="text"
              placeholder="Промокод"
              class="min-w-0 flex-1 rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-white"
            >
            <button
              type="button"
              class="guard-green-soft rounded-lg px-3 py-2 text-sm font-semibold disabled:opacity-50"
              :disabled="promoLoading || !(promoCode || '').trim()"
              @click="applyPromo()"
            >
              Активировать
            </button>
          </div>
        </div>
        <p class="mt-3 text-sm text-slate-300">Выберите период подписки:</p>
        <div class="mt-2 flex flex-col gap-2">
          <button
            v-for="plan in PREMIUM_PLANS"
            :key="plan.months"
            type="button"
            class="rounded-xl border border-slate-600 bg-slate-800 px-3 py-2.5 text-left text-sm font-semibold text-lime-300 hover:bg-slate-700 disabled:opacity-60"
            :disabled="payLoadingMonths !== null"
            @click="startPayment(plan.months)"
          >
            <span class="flex items-center justify-between gap-2">
              <span class="whitespace-nowrap">{{ plan.icon }} {{ plan.label }} — {{ plan.price }}</span>
              <span v-if="plan.savings" class="shrink-0 text-right text-xs font-bold text-cyan-300">{{ plan.savings }}</span>
            </span>
          </button>
        </div>
      </div>

      <div v-else-if="dashboardSection === 'faq'" class="mt-2 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
        <h3 class="text-base font-semibold text-slate-900 dark:text-white">FAQ</h3>
        <ul class="mt-2 list-disc space-y-1 pl-4 text-sm text-slate-700 dark:text-slate-300">
          <li>Токены подписки отвечают за доступ по периоду.</li>
          <li>Партнерские токены начисляются за оплаты рефералов.</li>
          <li>Партнерские токены можно переводить в подписку.</li>
        </ul>
      </div>

      <div v-else-if="dashboardSection === 'history'" class="mt-2">
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
          <div v-if="historyLoading" class="py-8 text-center text-sm text-slate-500 dark:text-slate-400">Загрузка…</div>
          <div v-else-if="historyTab === 'payments'" class="mt-3 space-y-2">
            <div v-if="historyPayments.length === 0" class="rounded-xl bg-slate-50 p-4 text-center text-sm text-slate-500 dark:bg-slate-700/40 dark:text-slate-400">
              Платежей пока нет.
            </div>
            <div v-for="(item, idx) in historyPayments" :key="`dp-${idx}`" class="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
              <p class="text-xs text-slate-500 dark:text-slate-400">{{ item.created_at || '—' }}</p>
              <div class="mt-1 flex items-center justify-between gap-2">
                <div>
                  <p class="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    {{ fmtAmount(item.amount_rub) }} ₽ · {{ item.months }} мес.
                  </p>
                  <p class="text-xs text-slate-500 dark:text-slate-400">
                    {{ providerLabel(item.provider) }} · {{ item.status }}
                  </p>
                </div>
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
          <div v-else class="mt-3 space-y-2">
            <div v-if="historyTokens.length === 0" class="rounded-xl bg-slate-50 p-4 text-center text-sm text-slate-500 dark:bg-slate-700/40 dark:text-slate-400">
              Движения токенов пока нет.
            </div>
            <div v-for="(item, idx) in historyTokens" :key="`dt-${idx}`" class="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
              <p class="text-xs text-slate-500 dark:text-slate-400">{{ item.created_at || '—' }}</p>
              <p class="mt-1 text-sm font-semibold" :class="item.delta >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'">
                {{ item.delta >= 0 ? '+' : '' }}{{ fmtAmount(item.delta) }} ⚡
              </p>
              <p class="text-xs text-slate-500 dark:text-slate-400">{{ item.reason }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div
      v-else-if="loading || (hasInitData && me === null && !error)"
      class="rounded-xl border border-gray-200 bg-white p-6 text-center dark:border-guardian-elevated-hi dark:bg-guardian-elevated"
    >
      <span class="text-gray-500 dark:text-gray-400">Загрузка…</span>
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
  </div>
</template>

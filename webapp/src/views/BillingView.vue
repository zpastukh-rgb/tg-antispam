<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import SecurityPinGateModal from '../components/SecurityPinGateModal.vue'
import { useApi } from '../composables/useApi'
import { useSecurityPinGate } from '../composables/useSecurityPinGate'
import { useToast } from '../composables/useToast'
import { shouldAskPinForAction } from '../utils/settingsSecurity'
import { formatDateTimeRu } from '../utils/formatDateTime'

const { t } = useI18n()
const { api, error, fetchSilent, hasInitData } = useApi()
const { showToast } = useToast()
const meTelegramId = ref(null)
const {
  pinGateOpen,
  pinGateInput,
  pinGateError,
  pinGateBusy,
  requestPinIfNeeded,
  submitPinGate,
  cancelPinGate,
} = useSecurityPinGate(() => Number(meTelegramId.value || 0))
const billing = ref(null)
const promoCode = ref('')
const promoLoading = ref(false)
const payLoadingMonths = ref(null)
const payLoadingTestMonths = ref(null)
const showPremiumInfoModal = ref(false)

/** Подарок AURUM с Premium: сумма ₽ / 4 ✨ (синхрон с бэкендом). */
const SUBSCRIPTION_GIFT_RUB_PER_AURUM = 4

const isEn = computed(() => t('common.locale_code') === 'en')

const PREMIUM_PLANS = computed(() => [
  { months: 1, icon: '🛡', label: t('dashboard.plans.months_1'), price: '490 ₽', priceRub: 490, savings: null },
  { months: 3, icon: '⚡', label: t('dashboard.plans.months_3'), price: '990 ₽', priceRub: 990, savings: '480 ₽' },
  { months: 6, icon: '📅', label: t('dashboard.plans.months_6'), price: '1590 ₽', priceRub: 1590, savings: '1350 ₽' },
  { months: 12, icon: '👑', label: t('dashboard.plans.months_12'), price: '2790 ₽', priceRub: 2790, savings: '3090 ₽' },
  { months: 24, icon: '💎', label: t('dashboard.plans.months_24'), price: '4790 ₽', priceRub: 4790, savings: '6970 ₽' },
  { months: 72, icon: '🚀', label: t('dashboard.plans.months_72'), price: '10 990 ₽', priceRub: 10990, savings: '24 290 ₽' },
])

function subscriptionTokensForPlan(plan) {
  const rub = Number(plan?.priceRub ?? 0)
  if (!rub) return 0
  return Math.round(rub / SUBSCRIPTION_GIFT_RUB_PER_AURUM)
}

const tariffLabel = computed(() => {
  const tk = (billing.value?.tariff || 'free').toLowerCase()
  return ['premium', 'pro', 'business'].includes(tk) ? 'PREMIUM' : 'FREE'
})

const subscriptionUntilLabel = computed(() => formatDateTimeRu(billing.value?.subscription_until))

async function startPayment(months) {
  const okPin = await requestPinIfNeeded('payments')
  if (!okPin) {
    if (shouldAskPinForAction('payments')) showToast(t('errors.pin_required'))
    return
  }
  payLoadingMonths.value = months
  try {
    const r = await fetchSilent(() => api.yookassaCreatePayment(months))
    const url = r?.confirmation_url
    if (!url) {
      showToast(t('errors.payment_link_missing'))
      return
    }
    const tg = window.Telegram?.WebApp
    if (typeof tg?.openLink === 'function') {
      tg.openLink(url, { try_instant_view: false })
    } else {
      window.open(url, '_blank', 'noopener,noreferrer')
    }
    showToast(isEn.value ? 'Opening payment page' : 'Откроется страница оплаты')
  } catch (e) {
    const msg = e?.body?.detail || e?.message || t('errors.payment_failed')
    showToast(typeof msg === 'string' ? msg : t('errors.payment_failed'))
  } finally {
    payLoadingMonths.value = null
  }
}

async function startTestTariffPayment(months) {
  if (!billing.value?.test_tariff_payment_visible) return
  const okPin = await requestPinIfNeeded('payments')
  if (!okPin) {
    if (shouldAskPinForAction('payments')) showToast(t('errors.pin_required'))
    return
  }
  payLoadingTestMonths.value = months
  try {
    const r = await fetchSilent(() => api.yookassaCreateTestSubscriptionPayment(months))
    const url = r?.confirmation_url
    if (!url) {
      showToast(t('errors.payment_link_missing'))
      return
    }
    const tg = window.Telegram?.WebApp
    if (typeof tg?.openLink === 'function') {
      tg.openLink(url, { try_instant_view: false })
    } else {
      window.open(url, '_blank', 'noopener,noreferrer')
    }
    showToast(isEn.value ? 'Opening payment page' : 'Откроется страница оплаты')
  } catch (e) {
    const msg = e?.body?.detail || e?.message || t('errors.payment_failed')
    showToast(typeof msg === 'string' ? msg : t('errors.payment_failed'))
  } finally {
    payLoadingTestMonths.value = null
  }
}

async function applyPromo() {
  const code = (promoCode.value || '').trim()
  if (!code) {
    showToast(isEn.value ? 'Enter a promo code' : 'Введите промокод')
    return
  }
  promoLoading.value = true
  try {
    await fetchSilent(() => api.promoApply(code))
    showToast(isEn.value ? 'Promo activated' : 'Промокод активирован')
    promoCode.value = ''
    billing.value = await fetchSilent(() => api.billing())
    window.dispatchEvent(new CustomEvent('guard:me-refresh'))
  } catch (e) {
    const msg = e?.body?.detail || e?.message || (isEn.value ? 'Activation failed' : 'Ошибка активации')
    showToast(msg)
  } finally {
    promoLoading.value = false
  }
}

onMounted(async () => {
  if (!hasInitData.value) return
  try {
    billing.value = await fetchSilent(() => api.billing())
  } catch {
    //
  }
  try {
    const m = await fetchSilent(() => api.me())
    if (m?.telegram_id != null) meTelegramId.value = Number(m.telegram_id)
  } catch {
    //
  }
})
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-xl font-semibold text-gray-900 dark:text-white md:text-2xl">{{ t('billing.landing_title') }}</h1>

    <div v-if="!hasInitData" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
      {{ isEn ? 'Open the panel from Telegram.' : 'Откройте панель из Telegram.' }}
    </div>

    <div v-else-if="error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
      {{ error }}
    </div>

    <div v-else-if="billing" class="space-y-6">
      <!-- Текущий тариф -->
      <div class="rounded-2xl border border-white/10 bg-gradient-to-br from-slate-900/90 to-slate-800/85 p-4 shadow-[0_12px_30px_-20px_rgba(16,185,129,0.45)] backdrop-blur-sm dark:border-white/10">
        <dl class="grid gap-2 text-sm sm:grid-cols-3">
          <div class="rounded-xl border border-white/10 bg-white/5 px-3 py-2.5">
            <dt class="text-[11px] uppercase tracking-wide text-slate-400">{{ t('subscription.plan_label') }}</dt>
            <dd class="mt-1 font-semibold text-white">{{ tariffLabel }}</dd>
          </div>
          <div class="rounded-xl border border-white/10 bg-white/5 px-3 py-2.5">
            <dt class="text-[11px] uppercase tracking-wide text-slate-400">{{ isEn ? 'Connected chats' : 'Подключено чатов' }}</dt>
            <dd class="mt-1 font-semibold text-white">{{ billing.chats_count }} / {{ billing.chat_limit }}</dd>
          </div>
          <div class="rounded-xl border border-white/10 bg-white/5 px-3 py-2.5">
            <dt class="text-[11px] uppercase tracking-wide text-slate-400">{{ isEn ? 'Subscription until' : 'Подписка до' }}</dt>
            <dd class="mt-1 font-semibold text-white">{{ subscriptionUntilLabel }}</dd>
          </div>
        </dl>
      </div>

      <!-- Guard Premium: тарифы и промокод -->
      <div class="rounded-xl border border-primary-200 bg-primary-50 p-6 dark:border-primary-800 dark:bg-primary-900/20">
        <div class="mb-4 flex items-center justify-between gap-2">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white">🛡 Guard Premium</h2>
          <button
            type="button"
            class="inline-flex h-8 min-w-8 items-center justify-center rounded-full border border-sky-300 bg-sky-100 px-2 text-sm font-extrabold text-sky-800 shadow-sm hover:bg-sky-200 dark:border-sky-700 dark:bg-sky-900/30 dark:text-sky-200 dark:hover:bg-sky-900/45"
            :aria-label="isEn ? 'Guard Premium info' : 'Информация о Guard Premium'"
            @click="showPremiumInfoModal = true"
          >
            i
          </button>
        </div>

        <div class="mb-4 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
          <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">🎁 {{ isEn ? 'Promo code' : 'Промокод' }}</h3>
          <p class="text-xs text-gray-500 dark:text-gray-400 mb-3">{{ isEn ? 'Enter a code to activate Premium.' : 'Введите промокод для активации Premium.' }}</p>
          <div class="flex flex-wrap gap-2">
            <input
              v-model="promoCode"
              type="text"
              :placeholder="isEn ? 'Promo code' : 'Промокод'"
              class="min-w-0 flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
              :disabled="promoLoading"
              @keydown.enter.prevent="applyPromo()"
            />
            <button
              type="button"
              class="guard-green-soft rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50"
              :disabled="promoLoading || !(promoCode || '').trim()"
              @click="applyPromo()"
            >
              {{ isEn ? 'Activate' : 'Активировать' }}
            </button>
          </div>
        </div>

        <p class="text-sm text-gray-600 dark:text-gray-400 mb-4">{{ isEn ? 'Choose subscription period:' : 'Выберите период подписки:' }}</p>
        <div class="flex flex-col gap-2">
          <button
            v-for="plan in PREMIUM_PLANS"
            :key="plan.months"
            type="button"
            :disabled="payLoadingMonths !== null || payLoadingTestMonths !== null"
            class="flex items-center justify-between rounded-xl border border-primary-300 bg-white px-4 py-3 text-left text-sm font-medium text-gray-800 transition hover:bg-primary-50 dark:border-primary-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-primary-900/20 disabled:cursor-wait disabled:opacity-70"
            @click="startPayment(plan.months)"
          >
            <span class="min-w-0">
              <span class="whitespace-nowrap"><span class="mr-1.5">{{ plan.icon }}</span>{{ plan.label }} — {{ plan.price }}</span>
              <span class="mt-0.5 block text-[11px] text-primary-700 dark:text-primary-300">+{{ subscriptionTokensForPlan(plan) }} ⚡ {{ isEn ? 'AURUM bonus' : 'AURUM в подарок' }}</span>
            </span>
            <span v-if="plan.savings" class="shrink-0 self-start whitespace-nowrap text-xs text-primary-600 dark:text-primary-400">{{ isEn ? `Save ${plan.savings}` : `Экономия ${plan.savings}` }}</span>
          </button>
        </div>
        <p class="mt-3 text-xs text-gray-500 dark:text-gray-400">
          {{ isEn ? 'Payments via YooKassa. After payment the subscription will be extended automatically; refresh the screen if needed.' : 'Оплата через ЮKassa. После оплаты подписка продлится автоматически; при необходимости обновите экран.' }}
        </p>

        <div v-if="billing?.test_tariff_payment_visible" class="mt-5 rounded-xl border border-amber-300 bg-amber-50 p-4 dark:border-amber-700 dark:bg-amber-950/40">
          <h3 class="text-sm font-semibold text-amber-900 dark:text-amber-100">{{ isEn ? 'Test plan payment' : 'Тестовая оплата тарифов' }}</h3>
          <p class="mt-1 text-xs text-amber-800/90 dark:text-amber-200/90">
            {{ isEn ? 'Visible only to you. Currently uses the same YooKassa as above — can be switched to a separate test shop later.' : 'Только для вашего аккаунта. Сейчас тот же YooKassa, что и выше — позже можно переключить на тестовый магазин отдельно от основных кнопок.' }}
          </p>
          <div class="mt-3 flex flex-col gap-2">
            <button
              v-for="plan in PREMIUM_PLANS"
              :key="`test-bill-${plan.months}`"
              type="button"
              :disabled="payLoadingTestMonths !== null || payLoadingMonths !== null"
              class="flex items-center justify-between rounded-xl border border-amber-400 bg-white px-4 py-3 text-left text-sm font-medium text-amber-950 transition hover:bg-amber-100 dark:border-amber-600 dark:bg-amber-950/60 dark:text-amber-50 dark:hover:bg-amber-900/50 disabled:cursor-wait disabled:opacity-70"
              @click="startTestTariffPayment(plan.months)"
            >
              <span class="min-w-0">
                <span class="whitespace-nowrap">
                  <span class="mr-1.5">{{ plan.icon }}</span>{{ plan.label }} — {{ plan.price }}
                  <span class="ml-1 text-[10px] font-bold uppercase text-amber-700 dark:text-amber-300">{{ isEn ? 'test' : 'тест' }}</span>
                </span>
                <span class="mt-0.5 block text-[11px] text-amber-900 dark:text-amber-200">+{{ subscriptionTokensForPlan(plan) }} ⚡</span>
              </span>
              <span v-if="plan.savings" class="shrink-0 self-start whitespace-nowrap text-xs text-amber-800 dark:text-amber-200">{{ isEn ? `Save ${plan.savings}` : `Экономия ${plan.savings}` }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <div
      v-else-if="hasInitData && billing === null && !error"
      class="rounded-xl border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-gray-800"
    >
      <span class="text-gray-500 dark:text-gray-400">{{ t('loading.generic') }}</span>
    </div>

    <div
      v-if="showPremiumInfoModal"
      class="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-3 md:items-center"
      @click.self="showPremiumInfoModal = false"
    >
      <div class="w-full max-w-md rounded-2xl border border-sky-300/50 bg-white p-4 shadow-2xl dark:border-sky-700/60 dark:bg-gray-800">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-base font-semibold text-gray-900 dark:text-white">{{ isEn ? '😈 Guard Premium — what is inside' : '😈 Guard Premium — что внутри' }}</h3>
          <button
            type="button"
            class="rounded-lg px-2 py-1 text-sm text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700"
            @click="showPremiumInfoModal = false"
          >
            ✕
          </button>
        </div>
        <p class="mb-3 text-sm text-gray-700 dark:text-gray-300">
          {{ isEn ? 'Get Premium when you run several chats and want me to take the heat: raids, boosting, bot waves — not your night shift.' : 'Берёшь Premium, когда чатов несколько и хочешь, чтобы я держал удар: рейды, накрутки, волны ботов — не твоя ночная смена.' }}
        </p>
        <ul class="list-disc space-y-1 pl-4 text-sm text-gray-700 dark:text-gray-300">
          <li>{{ isEn ? 'Anti-raid and anti-boost with sane presets' : 'Антирейд и антинакрутка с нормальными пресетами' }}</li>
          <li>{{ isEn ? 'Newcomers mode and silence right after they join' : 'Режим новичков и тишина после входа' }}</li>
          <li>{{ isEn ? 'Filters and punishments are more flexible than in a “bare” chat' : 'Фильтры и наказания гибче, чем в «голом» чате' }}</li>
          <li>{{ isEn ? 'More slots for chats under one cabinet' : 'Больше слотов для подключённых чатов под один кабинет' }}</li>
        </ul>
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

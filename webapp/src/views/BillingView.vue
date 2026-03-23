<script setup>
import { ref, computed, onMounted } from 'vue'
import { useApi } from '../composables/useApi'
import { useToast } from '../composables/useToast'
import { formatDateTimeRu } from '../utils/formatDateTime'

const { api, loading, error, fetch, hasInitData } = useApi()
const { showToast } = useToast()
const billing = ref(null)
const promoCode = ref('')
const promoLoading = ref(false)
const payLoadingMonths = ref(null)

// Тарифы Guardian Premium (кнопки оплаты пока без перехода) + тест 3 дня по промокоду
const PREMIUM_PLANS = [
  { months: 1, icon: '🛡', label: '1 месяц', price: '199 ₽', savings: null },
  { months: 3, icon: '⚡', label: '3 месяца', price: '499 ₽', savings: '98 ₽' },
  { months: 6, icon: '🔥', label: '6 месяцев', price: '899 ₽', savings: '295 ₽' },
  { months: 12, icon: '👑', label: '12 месяцев', price: '1499 ₽', savings: '889 ₽' },
  { months: 24, icon: '💀', label: '24 месяца', price: '2499 ₽', savings: '2277 ₽' },
]

const tariffLabel = computed(() => {
  const t = (billing.value?.tariff || 'free').toLowerCase()
  return ['premium', 'pro', 'business'].includes(t) ? 'PREMIUM' : 'FREE'
})

const subscriptionUntilLabel = computed(() => formatDateTimeRu(billing.value?.subscription_until))

async function startPayment(months) {
  payLoadingMonths.value = months
  try {
    const r = await fetch(() => api.yookassaCreatePayment(months))
    const url = r?.confirmation_url
    if (!url) {
      showToast('Нет ссылки на оплату')
      return
    }
    const tg = window.Telegram?.WebApp
    if (typeof tg?.openLink === 'function') {
      tg.openLink(url, { try_instant_view: false })
    } else {
      window.open(url, '_blank', 'noopener,noreferrer')
    }
    showToast('Откроется страница оплаты')
  } catch (e) {
    const msg = e?.body?.detail || e?.message || 'Ошибка создания платежа'
    showToast(typeof msg === 'string' ? msg : 'Ошибка создания платежа')
  } finally {
    payLoadingMonths.value = null
  }
}

async function applyPromo() {
  const code = (promoCode.value || '').trim()
  if (!code) {
    showToast('Введите промокод')
    return
  }
  promoLoading.value = true
  try {
    await fetch(() => api.promoApply(code))
    showToast('Промокод активирован')
    promoCode.value = ''
    billing.value = await fetch(() => api.billing())
  } catch (e) {
    const msg = e?.body?.detail || e?.message || 'Ошибка активации'
    showToast(msg)
  } finally {
    promoLoading.value = false
  }
}

onMounted(async () => {
  if (!hasInitData.value) return
  try {
    billing.value = await fetch(() => api.billing())
  } catch {
    //
  }
})
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-xl font-semibold text-gray-900 dark:text-white md:text-2xl">Тариф и оплата</h1>

    <div v-if="!hasInitData" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
      Откройте панель из Telegram.
    </div>

    <div v-else-if="error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
      {{ error }}
    </div>

    <div v-else-if="billing" class="space-y-6">
      <!-- Текущий тариф -->
      <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <dl class="grid gap-3 text-sm">
          <div>
            <dt class="text-gray-500 dark:text-gray-400">Тариф</dt>
            <dd class="font-medium text-gray-900 dark:text-white">{{ tariffLabel }}</dd>
          </div>
          <div>
            <dt class="text-gray-500 dark:text-gray-400">Подключено чатов</dt>
            <dd class="font-medium text-gray-900 dark:text-white">{{ billing.chats_count }} / {{ billing.chat_limit }}</dd>
          </div>
          <div>
            <dt class="text-gray-500 dark:text-gray-400">Подписка до</dt>
            <dd class="font-medium text-gray-900 dark:text-white">{{ subscriptionUntilLabel }}</dd>
          </div>
        </dl>
      </div>

      <!-- Guardian Premium: описание и тарифы -->
      <div class="rounded-xl border border-primary-200 bg-primary-50 p-6 dark:border-primary-800 dark:bg-primary-900/20">
        <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">🛡 Guardian Premium</h2>
        <p class="text-sm text-gray-700 dark:text-gray-300 mb-4">
          Базовая защита работает бесплатно. Но если у вас несколько чатов или нужна серьёзная защита — включите Guardian Premium.
        </p>
        <p class="text-sm text-gray-700 dark:text-gray-300 mb-2">Премиум открывает:</p>
        <ul class="text-sm text-gray-700 dark:text-gray-300 list-disc list-inside mb-4 space-y-0.5">
          <li>Анти-рейд защита</li>
          <li>Режим новичков</li>
          <li>Режим тишины</li>
          <li>Расширенные настройки фильтров</li>
          <li>Больше подключённых чатов (до 20)</li>
          <li>Гибкие наказания и контроль спама</li>
        </ul>
        <p class="text-sm text-gray-600 dark:text-gray-400 mb-4">Выберите период подписки:</p>
        <div class="flex flex-col gap-2">
          <button
            v-for="plan in PREMIUM_PLANS"
            :key="plan.months"
            type="button"
            :disabled="payLoadingMonths !== null"
            class="flex items-center justify-between rounded-xl border border-primary-300 bg-white px-4 py-3 text-left text-sm font-medium text-gray-800 transition hover:bg-primary-50 dark:border-primary-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-primary-900/20 disabled:cursor-wait disabled:opacity-70"
            @click="startPayment(plan.months)"
          >
            <span><span class="mr-1.5">{{ plan.icon }}</span>{{ plan.label }} — {{ plan.price }}</span>
            <span v-if="plan.savings" class="text-xs text-primary-600 dark:text-primary-400">Экономия {{ plan.savings }}</span>
          </button>
        </div>
        <p class="mt-3 text-xs text-gray-500 dark:text-gray-400">
          Оплата через ЮKassa. После оплаты подписка продлится автоматически; при необходимости обновите экран.
        </p>

        <div class="mt-6 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
          <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">🎁 Промокод / Premium на 3 дня</h3>
          <p class="text-xs text-gray-500 dark:text-gray-400 mb-3">Введите промокод для активации Premium (например тестовый на 3 дня).</p>
          <div class="flex flex-wrap gap-2">
            <input
              v-model="promoCode"
              type="text"
              placeholder="Промокод"
              class="min-w-0 flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
              :disabled="promoLoading"
              @keydown.enter.prevent="applyPromo()"
            />
            <button
              type="button"
              class="rounded-lg bg-primary-500 px-4 py-2 text-sm font-semibold text-guardian-ink hover:bg-primary-400 disabled:opacity-50"
              :disabled="promoLoading || !(promoCode || '').trim()"
              @click="applyPromo()"
            >
              Активировать
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="loading" class="rounded-xl border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-gray-800">
      <span class="text-gray-500 dark:text-gray-400">Загрузка…</span>
    </div>
  </div>
</template>

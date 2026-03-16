<script setup>
import { ref, computed, onMounted } from 'vue'
import { useApi } from '../composables/useApi'

const { api, loading, error, fetch, hasInitData } = useApi()
const billing = ref(null)

// Тарифы Guardian Premium (как в боте; кнопки пока без перехода)
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
            <dd class="font-medium text-gray-900 dark:text-white">{{ billing.subscription_until || '—' }}</dd>
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
            disabled
            class="flex items-center justify-between rounded-xl border border-primary-300 bg-white px-4 py-3 text-left text-sm font-medium text-gray-800 dark:border-primary-700 dark:bg-gray-800 dark:text-gray-200 disabled:cursor-default disabled:opacity-90"
          >
            <span><span class="mr-1.5">{{ plan.icon }}</span>{{ plan.label }} — {{ plan.price }}</span>
            <span v-if="plan.savings" class="text-xs text-primary-600 dark:text-primary-400">Экономия {{ plan.savings }}</span>
          </button>
        </div>
        <p class="mt-3 text-xs text-gray-500 dark:text-gray-400">Оплата будет подключена в следующей версии.</p>
      </div>
    </div>

    <div v-else-if="loading" class="rounded-xl border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-gray-800">
      <span class="text-gray-500 dark:text-gray-400">Загрузка…</span>
    </div>
  </div>
</template>

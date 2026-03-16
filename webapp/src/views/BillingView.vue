<script setup>
import { ref, computed, onMounted } from 'vue'
import { useApi } from '../composables/useApi'

const { api, loading, error, fetch, hasInitData } = useApi()
const billing = ref(null)

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

    <div v-else-if="billing" class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
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
      <p class="mt-4 text-sm text-gray-500 dark:text-gray-500">Оплата и смена тарифа — в следующих версиях.</p>
    </div>

    <div v-else-if="loading" class="rounded-xl border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-gray-800">
      <span class="text-gray-500 dark:text-gray-400">Загрузка…</span>
    </div>
  </div>
</template>

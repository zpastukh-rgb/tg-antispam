<script setup>
import { ref, onMounted } from 'vue'
import { useApi } from '../composables/useApi'

const { api, loading, error, fetch, hasInitData } = useApi()
const me = ref(null)

onMounted(async () => {
  if (!hasInitData.value) return
  try {
    me.value = await fetch(() => api.me())
  } catch {
    // error already in error ref
  }
})
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-xl font-semibold text-gray-900 dark:text-white md:text-2xl">Главная</h1>

    <div v-if="!hasInitData" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
      Откройте панель из Telegram (бот → команда или кнопка меню), чтобы данные подгрузились.
    </div>

    <div v-else-if="error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
      {{ error }}
    </div>

    <div v-else-if="me" class="space-y-4">
      <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <p class="mb-4 text-gray-600 dark:text-gray-400">
          Добро пожаловать в панель AntiSpam Guardian. Выберите раздел в меню слева.
        </p>
        <dl class="grid gap-2 text-sm sm:grid-cols-2">
          <dt class="text-gray-500 dark:text-gray-400">Тариф</dt>
          <dd class="font-medium text-gray-900 dark:text-white">{{ (me.tariff || 'free').toUpperCase() }}</dd>
          <dt class="text-gray-500 dark:text-gray-400">Подключено чатов</dt>
          <dd class="font-medium text-gray-900 dark:text-white">{{ me.chats_count }} из {{ me.chat_limit }}</dd>
          <dt class="text-gray-500 dark:text-gray-400">Подписка до</dt>
          <dd class="font-medium text-gray-900 dark:text-white">{{ me.subscription_until || '—' }}</dd>
        </dl>
      </div>
    </div>

    <div v-else-if="loading" class="rounded-xl border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-gray-800">
      <span class="text-gray-500 dark:text-gray-400">Загрузка…</span>
    </div>
  </div>
</template>

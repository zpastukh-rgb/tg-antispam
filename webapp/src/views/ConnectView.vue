<script setup>
import { ref, onMounted } from 'vue'
import { useApi } from '../composables/useApi'

const { api, loading, error, fetch, hasInitData } = useApi()
const pending = ref([])

onMounted(async () => {
  if (!hasInitData.value) return
  try {
    const data = await fetch(() => api.connectPending())
    pending.value = data.chats || []
  } catch {
    //
  }
})
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-xl font-semibold text-gray-900 dark:text-white md:text-2xl">Подключить чат</h1>

    <div v-if="!hasInitData" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
      Откройте панель из Telegram.
    </div>

    <div v-else-if="error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
      {{ error }}
    </div>

    <div v-else class="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
      <p class="text-gray-600 dark:text-gray-400">
        Добавьте бота в группу как администратора (с правом удалять сообщения), затем в боте нажмите «Подключить чат» и выберите группу из списка или через кнопку Telegram.
      </p>
      <p v-if="pending.length" class="mt-4 text-sm font-medium text-gray-700 dark:text-gray-300">Чаты, ожидающие подключения:</p>
      <ul v-if="pending.length" class="mt-2 list-inside list-disc text-sm text-gray-600 dark:text-gray-400">
        <li v-for="c in pending" :key="c.id">{{ c.title }}</li>
      </ul>
      <p v-else class="mt-4 text-sm text-gray-500 dark:text-gray-500">
        Пока нет чатов в ожидании. Добавьте бота в новую группу и выберите её в боте.
      </p>
    </div>

    <div v-if="loading && !pending.length" class="rounded-xl border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-gray-800">
      <span class="text-gray-500 dark:text-gray-400">Загрузка…</span>
    </div>
  </div>
</template>

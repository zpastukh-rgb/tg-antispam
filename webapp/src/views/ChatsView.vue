<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi'

const router = useRouter()
const { api, loading, error, fetch, hasInitData } = useApi()
const chats = ref([])
const selectedChatId = ref(null)

onMounted(async () => {
  if (!hasInitData.value) return
  try {
    const data = await fetch(() => api.chats())
    chats.value = data.chats || []
    selectedChatId.value = data.selected_chat_id ?? null
  } catch {
    //
  }
})

async function selectChat(id) {
  if (!hasInitData.value) return
  try {
    await fetch(() => api.selectChat(id))
    selectedChatId.value = id
  } catch {
    //
  }
}

function goToProtection(chatId) {
  selectChat(chatId).then(() => router.push('/protection'))
}

function goToReports(chatId) {
  selectChat(chatId).then(() => router.push('/reports'))
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-xl font-semibold text-gray-900 dark:text-white md:text-2xl">Подключённые чаты</h1>

    <div v-if="!hasInitData" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
      Откройте панель из Telegram.
    </div>

    <div v-else-if="error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
      {{ error }}
    </div>

    <div v-else-if="loading && !chats.length" class="rounded-xl border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-gray-800">
      <span class="text-gray-500 dark:text-gray-400">Загрузка…</span>
    </div>

    <div v-else-if="!chats.length" class="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
      <p class="text-gray-600 dark:text-gray-400">Пока нет подключённых чатов.</p>
      <p class="mt-2 text-sm text-gray-500 dark:text-gray-500">Добавьте бота в группу и подключите чат в разделе «Подключить группу».</p>
    </div>

    <div v-else class="space-y-3">
      <div
        v-for="chat in chats"
        :key="chat.id"
        class="flex flex-col gap-2 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800 sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <p class="font-medium text-gray-900 dark:text-white">{{ chat.title }}</p>
          <p v-if="chat.id === selectedChatId" class="text-xs text-primary-600 dark:text-primary-400">Выбран для настроек</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            class="rounded-lg bg-primary-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-600"
            @click="goToProtection(chat.id)"
          >
            Защита
          </button>
          <button
            type="button"
            class="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
            @click="goToReports(chat.id)"
          >
            Отчёты
          </button>
          <button
            v-if="chat.id !== selectedChatId"
            type="button"
            class="rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 dark:border-gray-600 dark:text-gray-400 dark:hover:bg-gray-700"
            @click="selectChat(chat.id)"
          >
            Выбрать
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

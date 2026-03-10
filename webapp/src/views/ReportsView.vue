<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi'

const router = useRouter()
const { api, loading, error, fetch, hasInitData } = useApi()
const chat = ref(null)

onMounted(async () => {
  if (!hasInitData.value) return
  try {
    const { selected_chat_id } = await fetch(() => api.chats())
    if (!selected_chat_id) {
      chat.value = { noSelection: true }
      return
    }
    const data = await fetch(() => api.chat(selected_chat_id))
    chat.value = data
  } catch {
    chat.value = { noSelection: false, loadError: true }
  }
})
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-xl font-semibold text-gray-900 dark:text-white md:text-2xl">Отчёты</h1>

    <div v-if="!hasInitData" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
      Откройте панель из Telegram.
    </div>

    <div v-else-if="chat?.noSelection" class="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
      <p class="text-gray-600 dark:text-gray-400">Выберите чат в разделе «Подключённые чаты», чтобы настроить чат отчётов.</p>
      <button
        type="button"
        class="mt-4 rounded-lg bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600"
        @click="router.push('/chats')"
      >
        К списку чатов
      </button>
    </div>

    <div v-else-if="chat?.loadError || error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
      {{ error || 'Не удалось загрузить данные' }}
    </div>

    <div v-else-if="chat?.rule" class="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
      <p class="text-gray-600 dark:text-gray-400">Чат: <strong class="text-gray-900 dark:text-white">{{ chat.title }}</strong></p>
      <p class="mt-2 text-sm text-gray-500 dark:text-gray-500">
        Отчёты в чат: {{ chat.rule.log_enabled ? 'ВКЛ' : 'ВЫКЛ' }}. Guardian сообщения: {{ chat.rule.guardian_messages_enabled ? 'ВКЛ' : 'ВЫКЛ' }}.
      </p>
      <p class="mt-1 text-sm text-gray-500 dark:text-gray-500">
        Подключение и смена чата отчётов выполняются в боте (кнопка «Подключить чат отчётов» в разделе Отчёты).
      </p>
    </div>

    <div v-else-if="loading" class="rounded-xl border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-gray-800">
      <span class="text-gray-500 dark:text-gray-400">Загрузка…</span>
    </div>
  </div>
</template>

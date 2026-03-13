<script setup>
import { ref, onMounted } from 'vue'
import { useApi } from '../composables/useApi'

const { api, loading, error, fetch, hasInitData } = useApi()
const pending = ref([])
const addToGroupUrl = ref(null)

onMounted(async () => {
  if (!hasInitData.value) return
  try {
    const [pendingData, botData] = await Promise.all([
      fetch(() => api.connectPending()).catch(() => ({ chats: [] })),
      fetch(() => api.botInfo()).catch(() => null),
    ])
    pending.value = pendingData?.chats ?? []
    addToGroupUrl.value = botData?.add_to_group_url ?? null
  } catch {
    //
  }
})

/** Открыть чат с ботом. На мобильном закрываем мини-приложение, чтобы пользователь увидел чат и кнопку под полем ввода. */
function openAddToGroup() {
  const url = addToGroupUrl.value
  if (!url) return
  if (window.Telegram?.WebApp?.openTelegramLink) {
    window.Telegram.WebApp.openTelegramLink(url)
    // Закрываем мини-приложение, чтобы на телефоне пользователь оказался в чате с ботом и увидел кнопку выбора группы
    setTimeout(() => {
      if (window.Telegram?.WebApp?.close) {
        window.Telegram.WebApp.close()
      }
    }, 400)
  } else {
    window.open(url, '_blank')
  }
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-xl font-semibold text-gray-900 dark:text-white md:text-2xl">Подключить группу</h1>

    <div v-if="!hasInitData" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
      Откройте панель из Telegram.
    </div>

    <div v-else-if="error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
      {{ error }}
    </div>

    <div v-else class="space-y-4">
      <!-- Подсказка для мобильных: что произойдёт после нажатия и что делать в чате с ботом -->
      <div class="rounded-xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-900/20">
        <p class="mb-2 font-medium text-amber-900 dark:text-amber-100">📱 На телефоне</p>
        <ol class="list-decimal list-inside space-y-1 text-sm text-amber-800 dark:text-amber-200">
          <li>Нажмите кнопку ниже — откроется <strong>чат с ботом</strong> (мини-приложение закроется).</li>
          <li>В чате с ботом нажмите <strong>синюю кнопку под полем ввода</strong> «Выбрать группу» и выберите группу.</li>
        </ol>
      </div>

      <div class="rounded-xl border border-primary-200 bg-primary-50 p-6 dark:border-primary-800 dark:bg-primary-900/20">
        <p class="mb-4 text-gray-700 dark:text-gray-300">
          Нажмите кнопку ниже — откроется чат с ботом. Там под полем ввода появится кнопка выбора группы и выдачи прав администратора.
        </p>
        <div v-if="addToGroupUrl" class="flex flex-wrap gap-3">
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-xl bg-primary-500 px-5 py-3 font-medium text-white shadow-sm transition hover:bg-primary-600"
            @click="openAddToGroup"
          >
            Открыть чат с ботом
          </button>
        </div>
        <p v-else class="text-sm text-gray-500 dark:text-gray-400">Загрузка ссылки…</p>
      </div>

      <div class="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
        <p v-if="pending.length" class="text-sm font-medium text-gray-700 dark:text-gray-300">Чаты, ожидающие подключения (добавьте бота и выберите здесь):</p>
        <ul v-if="pending.length" class="mt-2 list-inside list-disc text-sm text-gray-600 dark:text-gray-400">
          <li v-for="c in pending" :key="c.id">{{ c.title }}</li>
        </ul>
        <p v-else class="text-sm text-gray-500 dark:text-gray-500">
          Пока нет чатов в ожидании. Нажмите «Добавить бота в группу» выше, выберите группу и выдайте боту права.
        </p>
      </div>
    </div>

    <div v-if="loading && !pending.length && !addToGroupUrl" class="rounded-xl border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-gray-800">
      <span class="text-gray-500 dark:text-gray-400">Загрузка…</span>
    </div>
  </div>
</template>

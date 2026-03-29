<script setup>
import { ref, onMounted } from 'vue'
import { useApi } from '../composables/useApi'

const { api, loading, fetch, hasInitData } = useApi()
const addToGroupUrl = ref(null)

onMounted(async () => {
  if (!hasInitData.value) return
  try {
    const botData = await fetch(() => api.botInfo()).catch(() => null)
    addToGroupUrl.value = botData?.add_to_group_url ?? null
  } catch { /* */ }
})

function openAddToGroup() {
  const url = addToGroupUrl.value
  if (!url) return
  if (window.Telegram?.WebApp?.openTelegramLink) {
    window.Telegram.WebApp.openTelegramLink(url)
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

    <div v-else class="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
      <button
        v-if="addToGroupUrl"
        type="button"
        class="w-full rounded-xl bg-primary-500 px-5 py-4 text-lg font-semibold text-guardian-ink shadow-sm shadow-primary-500/25 transition hover:bg-primary-400"
        @click="openAddToGroup"
      >
        ➕ Подключить группу
      </button>
      <p v-else class="text-center text-sm text-gray-500 dark:text-gray-400">Загрузка…</p>
    </div>
  </div>
</template>

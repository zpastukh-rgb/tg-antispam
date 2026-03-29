<script setup>
import { ref, onMounted } from 'vue'
import { useApi } from '../composables/useApi'
import { openTelegramDeepLink } from '../utils/openTelegramDeepLink'

const { api, fetch, hasInitData } = useApi()
const addToGroupUrl = ref(null)

const ADMIN_RIGHTS = 'delete_messages+restrict_members+invite_users+pin_messages'

function buildAddUrl(username) {
  const u = (username || '').replace(/^@/, '').trim()
  if (!u) return null
  return `https://t.me/${u}?startgroup=connect&admin=${ADMIN_RIGHTS}`
}

onMounted(async () => {
  if (!hasInitData.value) return
  try {
    const botData = await fetch(() => api.botInfo()).catch(() => null)
    addToGroupUrl.value = botData?.add_to_group_url || buildAddUrl(botData?.username)
  } catch {
    //
  }
})

function openAddToGroup() {
  if (addToGroupUrl.value) openTelegramDeepLink(addToGroupUrl.value)
}
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold text-gray-900 dark:text-white md:text-2xl">Подключить группу</h1>

    <div
      v-if="!hasInitData"
      class="rounded-xl border-2 border-amber-400/80 bg-amber-50 p-4 text-sm text-amber-950 dark:border-amber-600 dark:bg-amber-950/30 dark:text-amber-100"
    >
      Откройте эту панель из Telegram (меню бота или кнопка Mini App).
    </div>

    <template v-else>
      <p class="text-sm leading-relaxed text-gray-600 dark:text-gray-400">
        Одна кнопка — Telegram предложит <strong class="text-gray-800 dark:text-gray-200">выбрать группу</strong> и выдать боту права. Это стандартный сценарий Mini App (
        <code class="rounded bg-gray-100 px-1 text-xs dark:bg-gray-700">startgroup</code>
        ).
      </p>

      <div
        class="rounded-xl border-2 border-sky-500/40 bg-sky-50/90 p-4 text-sm text-sky-950 dark:border-sky-600 dark:bg-sky-950/25 dark:text-sky-100"
      >
        <p class="font-medium">Что будет дальше</p>
        <p class="mt-1.5 text-sky-900/90 dark:text-sky-100/90">
          После выбора группы она появится в «Подключённых чатах». Настраивать фильтры можно там же.
        </p>
      </div>

      <div class="flex justify-center pt-1">
        <button
          v-if="addToGroupUrl"
          type="button"
          class="w-full max-w-sm rounded-xl bg-primary-500 px-6 py-3.5 text-base font-semibold text-guardian-ink shadow-sm shadow-primary-500/25 transition hover:bg-primary-400 active:scale-[0.99]"
          @click="openAddToGroup"
        >
          ➕ Выбрать группу и подключить
        </button>
        <p v-else class="py-4 text-center text-sm text-gray-500 dark:text-gray-400">Загрузка ссылки…</p>
      </div>
    </template>
  </div>
</template>

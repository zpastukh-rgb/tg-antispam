<script setup>
import { ref, onMounted } from 'vue'
import { useApi } from '../composables/useApi'
import { useToast } from '../composables/useToast'
import { openTelegramDeepLink } from '../utils/openTelegramDeepLink'

const { api, fetch, hasInitData } = useApi()
const { showToast } = useToast()
const addToGroupUrl = ref(null)
const pendingChats = ref([])

const ADMIN_RIGHTS = 'delete_messages+restrict_members+invite_users+pin_messages'

function buildAddUrl(username) {
  const u = (username || '').replace(/^@/, '').trim()
  if (!u) return null
  return `https://t.me/${u}?startgroup=connect&admin=${ADMIN_RIGHTS}`
}

onMounted(async () => {
  if (!hasInitData.value) return
  try {
    const [botData, pendingData] = await Promise.all([
      fetch(() => api.botInfo()).catch(() => null),
      fetch(() => api.connectPending()).catch(() => ({ chats: [] })),
    ])
    addToGroupUrl.value = botData?.add_to_group_url || buildAddUrl(botData?.username)
    pendingChats.value = pendingData?.chats || []
  } catch {
    //
  }
})

function openAddToGroup() {
  if (!addToGroupUrl.value) return
  const ok = openTelegramDeepLink(addToGroupUrl.value)
  if (!ok) {
    showToast('Откройте эту кнопку из Telegram-приложения, не из браузера.')
  }
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
      <div class="rounded-xl border-2 border-red-500/60 bg-red-50 p-4 text-sm text-red-950 dark:border-red-700 dark:bg-red-950/30 dark:text-red-100">
        <p class="font-medium">📱 На телефоне</p>
        <p class="mt-2 leading-relaxed">
          1. Нажмите зелёную кнопку ниже — Telegram сразу откроет выбор группы.<br>
          2. Выберите группу и выдайте боту права администратора.
        </p>
      </div>

      <div class="rounded-xl border-2 border-emerald-500/50 bg-emerald-50 p-4 text-sm text-emerald-950 dark:border-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-100">
        <p class="leading-relaxed">
          После выбора группа автоматически добавится в подключённые. Команду <code class="rounded bg-emerald-100 px-1 text-xs dark:bg-emerald-900/40">/check</code> писать не нужно.
        </p>
      </div>

      <div class="flex justify-center pt-1">
        <button
          v-if="addToGroupUrl"
          type="button"
          class="w-full max-w-sm rounded-xl bg-primary-500 px-6 py-3.5 text-base font-semibold text-guardian-ink shadow-sm shadow-primary-500/25 transition hover:bg-primary-400 active:scale-[0.99]"
          @click="openAddToGroup"
        >
          ➕ Выбрать группу
        </button>
        <p v-else class="py-4 text-center text-sm text-gray-500 dark:text-gray-400">Загрузка ссылки…</p>
      </div>

      <div class="rounded-xl border-2 border-sky-500/40 bg-sky-50/90 p-4 text-sm text-sky-950 dark:border-sky-600 dark:bg-sky-950/25 dark:text-sky-100">
        <p class="font-medium">Чаты, ожидающие подключения</p>
        <ul v-if="pendingChats.length" class="mt-2 list-disc space-y-1 pl-5">
          <li v-for="c in pendingChats" :key="c.id">{{ c.title }}</li>
        </ul>
        <p v-else class="mt-2 text-sky-900/85 dark:text-sky-100/85">Пока пусто.</p>
      </div>
    </template>
  </div>
</template>

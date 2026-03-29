<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi'
import { useToast } from '../composables/useToast'

const router = useRouter()
const { api, loading, error, fetch, hasInitData } = useApi()
const { showToast } = useToast()
const chat = ref(null)
const reportsChatUrl = ref(null)
const saving = ref(false)

onMounted(async () => {
  if (!hasInitData.value) return
  try {
    const [chatsData, botData] = await Promise.all([
      fetch(() => api.chats()).catch(() => ({ selected_chat_id: null })),
      fetch(() => api.botInfo()).catch(() => null),
    ])
    const selected_chat_id = chatsData?.selected_chat_id
    if (!selected_chat_id) {
      chat.value = { noSelection: true }
      return
    }
    const data = await fetch(() => api.chat(selected_chat_id))
    chat.value = data
    const tpl = botData?.reports_chat_url_template
    if (tpl && selected_chat_id) {
      reportsChatUrl.value = tpl.replace('{chat_id}', selected_chat_id)
    }
  } catch {
    chat.value = { noSelection: false, loadError: true }
  }
})

function openReportsChat() {
  const url = reportsChatUrl.value
  if (!url) return
  if (window.Telegram?.WebApp?.openTelegramLink) {
    window.Telegram.WebApp.openTelegramLink(url)
  } else {
    window.open(url, '_blank')
  }
}

async function updateRule(patch) {
  if (!chat.value?.id || chat.value.noSelection) return
  saving.value = true
  try {
    const data = await fetch(() => api.updateRule(chat.value.id, patch))
    chat.value.rule = data.rule
    showToast('Сохранено')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-xl font-semibold text-gray-900 dark:text-white md:text-2xl">Отчёты</h1>

    <div v-if="!hasInitData" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
      Откройте панель из Telegram.
    </div>

    <div v-else-if="chat?.noSelection" class="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
      <p class="text-gray-600 dark:text-gray-400">Сначала выберите чат в разделе «Подключённые чаты».</p>
      <button type="button" class="mt-3 rounded-lg bg-primary-500 px-4 py-2 text-sm font-semibold text-guardian-ink hover:bg-primary-400" @click="router.push('/chats')">К списку чатов</button>
    </div>

    <div v-else-if="chat?.loadError || error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
      {{ error || 'Не удалось загрузить данные' }}
    </div>

    <div v-else-if="chat?.rule" class="space-y-5">
      <p class="text-gray-600 dark:text-gray-400">Чат: <strong class="text-gray-900 dark:text-white">{{ chat.title }}</strong></p>

      <!-- Чат отчётов -->
      <section class="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 class="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">Чат отчётов</h2>
        <p v-if="chat.log_chat_id" class="mb-3 text-sm text-green-600 dark:text-green-400">
          ✓ {{ chat.log_chat_title || chat.log_chat_id }}
        </p>
        <p v-else class="mb-3 text-sm text-gray-500 dark:text-gray-400">Не подключён</p>
        <button
          v-if="reportsChatUrl"
          type="button"
          class="w-full rounded-xl bg-primary-500 px-5 py-3 font-semibold text-guardian-ink shadow-sm shadow-primary-500/25 transition hover:bg-primary-400"
          @click="openReportsChat"
        >
          📋 {{ chat.log_chat_id ? 'Сменить чат отчётов' : 'Подключить чат отчётов' }}
        </button>
      </section>

      <!-- Настройки -->
      <section class="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 class="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">Настройки</h2>
        <div class="space-y-3">
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm text-gray-600 dark:text-gray-400">Отчёты в чат</span>
            <button type="button" :class="chat.rule.log_enabled ? 'bg-primary-500 text-guardian-ink' : 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-300'" class="rounded-lg px-3 py-1.5 text-sm" @click="updateRule({ log_enabled: !chat.rule.log_enabled })">{{ chat.rule.log_enabled ? 'ВКЛ' : 'ВЫКЛ' }}</button>
          </div>
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm text-gray-600 dark:text-gray-400">Сообщения Guardian в группе</span>
            <button type="button" :class="chat.rule.guardian_messages_enabled ? 'bg-primary-500 text-guardian-ink' : 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-300'" class="rounded-lg px-3 py-1.5 text-sm" @click="updateRule({ guardian_messages_enabled: !chat.rule.guardian_messages_enabled })">{{ chat.rule.guardian_messages_enabled ? 'ВКЛ' : 'ВЫКЛ' }}</button>
          </div>
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm text-gray-600 dark:text-gray-400">Автоотчёты</span>
            <button type="button" :class="chat.rule.auto_reports_enabled ? 'bg-primary-500 text-guardian-ink' : 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-300'" class="rounded-lg px-3 py-1.5 text-sm" @click="updateRule({ auto_reports_enabled: !chat.rule.auto_reports_enabled })">{{ chat.rule.auto_reports_enabled ? 'ВКЛ' : 'ВЫКЛ' }}</button>
          </div>
        </div>
      </section>
    </div>

    <div v-else-if="loading || hasInitData" class="rounded-xl border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-gray-800">
      <span class="text-gray-500 dark:text-gray-400">Загрузка…</span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi'
import { useToast } from '../composables/useToast'
import { openTelegramDeepLink } from '../utils/openTelegramDeepLink'

const router = useRouter()
const { api, loading, error, fetch, hasInitData } = useApi()
const { showToast } = useToast()
const chat = ref(null)
const reportsChatUrl = ref(null)
const saving = ref(false)
const clearing = ref(false)

let selectedId = null
let stopListen = null

function buildReportsUrl(botData, protectedChatId) {
  const tpl = botData?.reports_chat_url_template
  if (tpl && protectedChatId != null) {
    return tpl.replace(/\{chat_id\}/g, String(protectedChatId))
  }
  const u = (botData?.username || '').replace(/^@/, '').trim()
  if (!u || protectedChatId == null) return null
  return `https://t.me/${u}?startgroup=reportschat_${protectedChatId}`
}

async function reloadChat() {
  if (!selectedId) return
  try {
    const data = await fetch(() => api.chat(selectedId))
    chat.value = data
  } catch {
    //
  }
}

onMounted(async () => {
  if (!hasInitData.value) return
  try {
    const [chatsData, botData] = await Promise.all([
      fetch(() => api.chats()).catch(() => ({ selected_chat_id: null })),
      fetch(() => api.botInfo()).catch(() => ({})),
    ])
    const selected_chat_id = chatsData?.selected_chat_id
    if (!selected_chat_id) {
      chat.value = { noSelection: true }
      return
    }
    selectedId = selected_chat_id
    await reloadChat()
    reportsChatUrl.value = buildReportsUrl(botData, selected_chat_id)
  } catch {
    chat.value = { noSelection: false, loadError: true }
  }

  const onVis = () => {
    if (document.visibilityState === 'visible') reloadChat()
  }
  document.addEventListener('visibilitychange', onVis)
  stopListen = () => document.removeEventListener('visibilitychange', onVis)
})

onUnmounted(() => {
  if (stopListen) stopListen()
})

function openPickReportsGroup() {
  const url = reportsChatUrl.value
  if (!url) {
    showToast('Не удалось получить ссылку. Проверьте API и бота.')
    return
  }
  openTelegramDeepLink(url)
}

async function clearReportsChat() {
  if (!chat.value?.id) return
  clearing.value = true
  try {
    const res = await fetch(() => api.setReportsChat(chat.value.id, null))
    chat.value.log_chat_id = res.log_chat_id
    chat.value.log_chat_title = res.log_chat_title
    showToast('Чат отчётов отключён')
  } catch (e) {
    showToast(e?.body?.detail || 'Ошибка')
  } finally {
    clearing.value = false
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
  <div class="space-y-4">
    <h1 class="text-xl font-semibold text-gray-900 dark:text-white md:text-2xl">Отчёты</h1>

    <div
      v-if="!hasInitData"
      class="rounded-xl border-2 border-amber-400/80 bg-amber-50 p-4 text-sm text-amber-950 dark:border-amber-600 dark:bg-amber-950/30 dark:text-amber-100"
    >
      Откройте панель из Telegram.
    </div>

    <div v-else-if="chat?.noSelection" class="rounded-xl border border-gray-200 bg-white p-6 dark:border-guardian-elevated-hi dark:bg-guardian-elevated">
      <p class="text-gray-600 dark:text-gray-400">Сначала в «Подключённые чаты» выберите группу, для которой настраиваете отчёты.</p>
      <button type="button" class="mt-3 rounded-lg bg-primary-500 px-4 py-2 text-sm font-semibold text-guardian-ink hover:bg-primary-400" @click="router.push('/chats')">
        К списку чатов
      </button>
    </div>

    <div v-else-if="chat?.loadError || error" class="rounded-xl border-2 border-red-400/70 bg-red-50 p-4 text-sm text-red-900 dark:border-red-700 dark:bg-red-950/30 dark:text-red-100">
      {{ error || 'Не удалось загрузить данные' }}
    </div>

    <div v-else-if="chat?.rule" class="space-y-4">
      <p class="text-sm text-gray-600 dark:text-gray-400">
        Настройки для: <strong class="text-gray-900 dark:text-white">{{ chat.title }}</strong>
      </p>

      <div
        class="rounded-xl border-2 border-violet-500/40 bg-violet-50/90 p-4 text-sm text-violet-950 dark:border-violet-600 dark:bg-violet-950/25 dark:text-violet-100"
      >
        <p class="font-medium">Отдельный чат для отчётов</p>
        <p class="mt-1.5 text-violet-900/90 dark:text-violet-100/90">
          Это <strong>другая группа</strong> (например «Логи»), куда бот будет слать журнал — не та, что вы защищаете сверху.
        </p>
      </div>

      <section class="rounded-xl border border-gray-200 bg-white p-4 dark:border-guardian-elevated-hi dark:bg-guardian-elevated">
        <h2 class="mb-2 text-sm font-medium text-gray-800 dark:text-gray-200">Подключение чата отчётов</h2>
        <p class="mb-3 text-xs leading-relaxed text-gray-500 dark:text-gray-400">
          Нажмите кнопку — откроется выбор группы в Telegram; добавьте туда бота. После этого вернитесь в приложение: статус обновится сам.
        </p>
        <div
          v-if="chat.log_chat_id"
          class="mb-3 rounded-lg border border-emerald-300/80 bg-emerald-50 px-3 py-2 text-sm text-emerald-900 dark:border-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-100"
        >
          ✓ Сейчас: <strong>{{ chat.log_chat_title || chat.log_chat_id }}</strong>
        </div>

        <div class="flex flex-col items-center gap-3">
          <button
            v-if="reportsChatUrl"
            type="button"
            class="w-full max-w-sm rounded-xl bg-primary-500 px-6 py-3.5 text-base font-semibold text-guardian-ink shadow-sm shadow-primary-500/25 transition hover:bg-primary-400 active:scale-[0.99]"
            @click="openPickReportsGroup"
          >
            {{ chat.log_chat_id ? '📋 Выбрать другой чат отчётов' : '📋 Выбрать чат отчётов' }}
          </button>
          <p v-else class="text-center text-xs text-gray-500 dark:text-gray-400">Нет ссылки — проверьте переменные API и бота.</p>

          <button
            v-if="chat.log_chat_id"
            type="button"
            class="text-sm font-medium text-gray-600 underline decoration-dashed underline-offset-2 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white"
            :disabled="clearing"
            @click="clearReportsChat"
          >
            {{ clearing ? 'Отключаем…' : 'Отключить чат отчётов' }}
          </button>
        </div>
      </section>

      <section class="rounded-xl border border-gray-200 bg-white p-4 dark:border-guardian-elevated-hi dark:bg-guardian-elevated">
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

    <div v-else-if="loading || hasInitData" class="rounded-xl border border-gray-200 bg-white p-8 text-center dark:border-guardian-elevated-hi dark:bg-guardian-elevated">
      <span class="text-gray-500 dark:text-gray-400">Загрузка…</span>
    </div>
  </div>
</template>

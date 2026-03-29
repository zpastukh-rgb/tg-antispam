<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi'
import { useToast } from '../composables/useToast'

const router = useRouter()
const { api, loading, error, fetch, hasInitData } = useApi()
const { showToast } = useToast()
const chat = ref(null)
const allChats = ref([])
const saving = ref(false)
const selectedLogChatId = ref(null)
const settingReports = ref(false)

onMounted(async () => {
  if (!hasInitData.value) return
  try {
    const chatsData = await fetch(() => api.chats()).catch(() => ({ selected_chat_id: null, chats: [] }))
    allChats.value = chatsData?.chats ?? []
    const selected_chat_id = chatsData?.selected_chat_id
    if (!selected_chat_id) {
      chat.value = { noSelection: true }
    } else {
      const data = await fetch(() => api.chat(selected_chat_id))
      chat.value = data
      selectedLogChatId.value = data.log_chat_id || null
    }
  } catch {
    chat.value = { noSelection: false, loadError: true }
  }
})

async function setReportsChat() {
  if (!chat.value?.id || chat.value.noSelection) return
  settingReports.value = true
  try {
    const targetId = selectedLogChatId.value ? Number(selectedLogChatId.value) : null
    const result = await fetch(() => api.setReportsChat(chat.value.id, targetId))
    chat.value.log_chat_id = result.log_chat_id
    chat.value.log_chat_title = result.log_chat_title
    showToast(targetId ? 'Чат отчётов подключён' : 'Чат отчётов отключён')
  } catch {
    showToast('Не удалось сохранить чат отчётов')
  } finally {
    settingReports.value = false
  }
}

async function clearReportsChat() {
  selectedLogChatId.value = null
  if (!chat.value?.id || chat.value.noSelection) return
  settingReports.value = true
  try {
    await fetch(() => api.setReportsChat(chat.value.id, null))
    chat.value.log_chat_id = null
    chat.value.log_chat_title = null
    showToast('Чат отчётов отключён')
  } catch {
    showToast('Не удалось отключить чат отчётов')
  } finally {
    settingReports.value = false
  }
}

async function updateRule(patch) {
  if (!chat.value?.id || chat.value.noSelection) return
  saving.value = true
  try {
    const data = await fetch(() => api.updateRule(chat.value.id, patch))
    chat.value.rule = data.rule
    showToast('Настройки успешно сохранены')
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
      <p class="text-gray-600 dark:text-gray-400">Выберите чат в разделе «Подключённые чаты», чтобы настроить чат отчётов.</p>
      <button
        type="button"
        class="mt-4 rounded-lg bg-primary-500 px-4 py-2 text-sm font-semibold text-guardian-ink hover:bg-primary-400"
        @click="router.push('/chats')"
      >
        К списку чатов
      </button>
    </div>

    <div v-else-if="chat?.loadError || error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
      {{ error || 'Не удалось загрузить данные' }}
    </div>

    <div v-else-if="chat?.rule" class="space-y-5">
      <p class="text-gray-600 dark:text-gray-400">Чат: <strong class="text-gray-900 dark:text-white">{{ chat.title }}</strong></p>

      <!-- Выбор чата отчётов из списка подключённых групп -->
      <section class="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 class="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">Чат отчётов</h2>
        <p v-if="chat.log_chat_id" class="mb-2 text-sm text-gray-600 dark:text-gray-400">
          Подключён: <strong class="text-gray-900 dark:text-white">{{ chat.log_chat_title || chat.log_chat_id }}</strong>
        </p>
        <p v-else class="mb-2 text-sm text-gray-500 dark:text-gray-400">
          Не подключён. Выберите группу из списка ниже.
        </p>

        <div v-if="allChats.length > 1" class="space-y-3">
          <select
            v-model="selectedLogChatId"
            class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
            :disabled="settingReports"
          >
            <option :value="null">— Не выбран —</option>
            <option
              v-for="c in allChats.filter(c => c.id !== chat.id)"
              :key="c.id"
              :value="c.id"
            >
              {{ c.title }}
            </option>
          </select>
          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              class="rounded-lg bg-primary-500 px-4 py-2 text-sm font-semibold text-guardian-ink hover:bg-primary-400 disabled:opacity-50"
              :disabled="settingReports || selectedLogChatId == chat.log_chat_id"
              @click="setReportsChat"
            >
              {{ settingReports ? 'Сохранение…' : 'Сохранить' }}
            </button>
            <button
              v-if="chat.log_chat_id"
              type="button"
              class="rounded-lg bg-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-300 dark:bg-gray-600 dark:text-gray-200 dark:hover:bg-gray-500 disabled:opacity-50"
              :disabled="settingReports"
              @click="clearReportsChat"
            >
              Отключить
            </button>
          </div>
        </div>

        <div v-else class="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-900/20">
          <p class="text-sm text-amber-800 dark:text-amber-200">
            Для выбора чата отчётов подключите хотя бы ещё одну группу в разделе «Подключить группу».
          </p>
        </div>
      </section>

      <!-- Переключатели -->
      <section class="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 class="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">Настройки</h2>
        <div class="space-y-3">
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm text-gray-600 dark:text-gray-400">Отчёты в чат включены</span>
            <button
              type="button"
              :class="chat.rule.log_enabled ? 'bg-primary-500 text-guardian-ink' : 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
              class="rounded-lg px-3 py-1.5 text-sm"
              @click="updateRule({ log_enabled: !chat.rule.log_enabled })"
            >
              {{ chat.rule.log_enabled ? 'ВКЛ' : 'ВЫКЛ' }}
            </button>
          </div>
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm text-gray-600 dark:text-gray-400">Guardian сообщения в группе</span>
            <button
              type="button"
              :class="chat.rule.guardian_messages_enabled ? 'bg-primary-500 text-guardian-ink' : 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
              class="rounded-lg px-3 py-1.5 text-sm"
              @click="updateRule({ guardian_messages_enabled: !chat.rule.guardian_messages_enabled })"
            >
              {{ chat.rule.guardian_messages_enabled ? 'ВКЛ' : 'ВЫКЛ' }}
            </button>
          </div>
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm text-gray-600 dark:text-gray-400">Автоотчёты (дайджест)</span>
            <button
              type="button"
              :class="chat.rule.auto_reports_enabled ? 'bg-primary-500 text-guardian-ink' : 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
              class="rounded-lg px-3 py-1.5 text-sm"
              @click="updateRule({ auto_reports_enabled: !chat.rule.auto_reports_enabled })"
            >
              {{ chat.rule.auto_reports_enabled ? 'ВКЛ' : 'ВЫКЛ' }}
            </button>
          </div>
        </div>
      </section>

      <p v-if="saving" class="text-sm text-gray-500 dark:text-gray-400">Сохранение…</p>
    </div>

    <div v-else-if="loading" class="rounded-xl border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-gray-800">
      <span class="text-gray-500 dark:text-gray-400">Загрузка…</span>
    </div>

    <div v-else-if="hasInitData" class="rounded-xl border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-gray-800">
      <span class="text-gray-500 dark:text-gray-400">Загрузка…</span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi'

const router = useRouter()
const { api, loading, error, fetch, hasInitData } = useApi()
const chat = ref(null)
const saving = ref(false)

onMounted(async () => {
  if (!hasInitData.value) return
  try {
    const { chats, selected_chat_id } = await fetch(() => api.chats())
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

async function updateRule(patch) {
  if (!chat.value?.id || chat.value.noSelection) return
  saving.value = true
  try {
    const data = await fetch(() => api.updateRule(chat.value.id, patch))
    chat.value.rule = data.rule
  } finally {
    saving.value = false
  }
}

const policyLabels = { allow: 'Разрешено', forbid: 'Запрещено', captcha: 'Капча' }
const actionLabels = { delete: 'Удалить', mute: 'Мут', ban: 'Бан' }
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-xl font-semibold text-gray-900 dark:text-white md:text-2xl">Защита</h1>

    <div v-if="!hasInitData" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
      Откройте панель из Telegram.
    </div>

    <div v-else-if="chat?.noSelection" class="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
      <p class="text-gray-600 dark:text-gray-400">Сначала выберите чат в разделе «Подключённые чаты».</p>
      <button
        type="button"
        class="mt-4 rounded-lg bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600"
        @click="router.push('/chats')"
      >
        К списку чатов
      </button>
    </div>

    <div v-else-if="chat?.loadError || error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
      {{ error || 'Не удалось загрузить настройки' }}
    </div>

    <div v-else-if="chat?.rule" class="space-y-4">
      <p class="text-gray-600 dark:text-gray-400">Чат: <strong class="text-gray-900 dark:text-white">{{ chat.title }}</strong></p>

      <div class="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 class="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">Основное</h2>
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            :class="chat.rule.master_anti_spam ? 'bg-primary-500 text-white' : 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
            class="rounded-lg px-3 py-1.5 text-sm"
            @click="updateRule({ master_anti_spam: !chat.rule.master_anti_spam })"
          >
            Защита от спама: {{ chat.rule.master_anti_spam ? 'ВКЛ' : 'ВЫКЛ' }}
          </button>
          <button
            type="button"
            :class="chat.rule.first_message_captcha_enabled ? 'bg-primary-500 text-white' : 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
            class="rounded-lg px-3 py-1.5 text-sm"
            @click="updateRule({ first_message_captcha_enabled: !chat.rule.first_message_captcha_enabled })"
          >
            Капча на первое сообщение: {{ chat.rule.first_message_captcha_enabled ? 'ВКЛ' : 'ВЫКЛ' }}
          </button>
        </div>
      </div>

      <div class="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 class="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">Фильтры</h2>
        <ul class="space-y-2 text-sm text-gray-600 dark:text-gray-400">
          <li>Ссылки: {{ policyLabels[chat.rule.filter_links_mode] || chat.rule.filter_links_mode }}</li>
          <li>Медиа: {{ policyLabels[chat.rule.filter_media_mode] || chat.rule.filter_media_mode }}</li>
          <li>Кнопки: {{ policyLabels[chat.rule.filter_buttons_mode] || chat.rule.filter_buttons_mode }}</li>
          <li>Сообщения «вступил в группу»: {{ chat.rule.delete_join_messages ? 'Удалять' : 'Оставлять' }}</li>
          <li>Стоп-слов: {{ chat.rule.stopwords_count }}</li>
        </ul>
      </div>

      <div class="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 class="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">Наказания</h2>
        <p class="text-sm text-gray-600 dark:text-gray-400">
          Режим: {{ actionLabels[chat.rule.action_mode] || chat.rule.action_mode }}, мут: {{ chat.rule.mute_minutes }} мин
        </p>
      </div>

      <div class="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 class="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">Новички</h2>
        <p class="text-sm text-gray-600 dark:text-gray-400">
          {{ chat.rule.newbie_enabled ? 'ВКЛ' : 'ВЫКЛ' }}, окно {{ chat.rule.newbie_minutes }} мин
        </p>
      </div>

      <p v-if="saving" class="text-sm text-gray-500 dark:text-gray-400">Сохранение…</p>
    </div>

    <div v-else-if="loading" class="rounded-xl border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-gray-800">
      <span class="text-gray-500 dark:text-gray-400">Загрузка…</span>
    </div>
  </div>
</template>

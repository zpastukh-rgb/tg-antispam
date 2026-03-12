<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi'
import { useToast } from '../composables/useToast'

const router = useRouter()
const { api, loading, error, fetch, hasInitData } = useApi()
const { showToast } = useToast()
const chat = ref(null)
const saving = ref(false)
const newStopword = ref('')
const stopwordLoading = ref(false)

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
    showToast('Настройки успешно сохранены')
  } finally {
    saving.value = false
  }
}

async function addStopword() {
  const word = (newStopword.value || '').trim()
  if (!word || !chat.value?.id || chat.value.noSelection) return
  stopwordLoading.value = true
  try {
    const data = await fetch(() => api.addStopword(chat.value.id, word))
    chat.value.stopwords = data.stopwords || []
    if (chat.value.rule) chat.value.rule.stopwords_count = chat.value.stopwords.length
    newStopword.value = ''
    showToast('Стоп-слово добавлено')
  } finally {
    stopwordLoading.value = false
  }
}

async function removeStopword(word) {
  if (!chat.value?.id || chat.value.noSelection) return
  stopwordLoading.value = true
  try {
    const data = await fetch(() => api.deleteStopword(chat.value.id, word))
    chat.value.stopwords = data.stopwords || []
    if (chat.value.rule) chat.value.rule.stopwords_count = chat.value.stopwords.length
    showToast('Стоп-слово удалено')
  } finally {
    stopwordLoading.value = false
  }
}

const policyOptions = [
  { value: 'allow', label: 'Разрешено' },
  { value: 'forbid', label: 'Запрещено' },
]

const actionOptions = [
  { value: 'delete', label: 'Удалить' },
  { value: 'mute', label: 'Мут' },
  { value: 'ban', label: 'Бан' },
]

const mutePresets = [5, 10, 30, 60, 1440]
const newbiePresets = [5, 10, 15, 30, 60]
const silencePresets = [
  { value: 0, label: 'Выкл' },
  { value: 5, label: '5 мин' },
  { value: 15, label: '15 мин' },
  { value: 60, label: '1 ч' },
  { value: 1440, label: '24 ч' },
]
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

    <div v-else-if="chat?.rule" class="space-y-5">
      <p class="text-gray-600 dark:text-gray-400">Чат: <strong class="text-gray-900 dark:text-white">{{ chat.title }}</strong></p>

      <!-- Основное -->
      <section class="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
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
        </div>
      </section>

      <!-- Фильтры -->
      <section class="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 class="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">Фильтры</h2>
        <div class="space-y-3">
          <div>
            <p class="mb-1 text-xs text-gray-500 dark:text-gray-400">Ссылки</p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="opt in policyOptions"
                :key="opt.value"
                type="button"
                :class="chat.rule.filter_links_mode === opt.value ? 'bg-primary-500 text-white' : 'bg-gray-100 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
                class="rounded-lg px-3 py-1.5 text-sm"
                @click="updateRule({ filter_links_mode: opt.value })"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>
          <div>
            <p class="mb-1 text-xs text-gray-500 dark:text-gray-400">Медиа / стикеры</p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="opt in policyOptions"
                :key="opt.value"
                type="button"
                :class="chat.rule.filter_media_mode === opt.value ? 'bg-primary-500 text-white' : 'bg-gray-100 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
                class="rounded-lg px-3 py-1.5 text-sm"
                @click="updateRule({ filter_media_mode: opt.value })"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>
          <div>
            <p class="mb-1 text-xs text-gray-500 dark:text-gray-400">Сообщения с кнопками</p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="opt in policyOptions"
                :key="opt.value"
                type="button"
                :class="chat.rule.filter_buttons_mode === opt.value ? 'bg-primary-500 text-white' : 'bg-gray-100 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
                class="rounded-lg px-3 py-1.5 text-sm"
                @click="updateRule({ filter_buttons_mode: opt.value })"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>
          <div class="flex items-center justify-between gap-2 pt-1">
            <span class="text-sm text-gray-600 dark:text-gray-400">Удалять сообщения «вступил в группу»</span>
            <button
              type="button"
              :class="chat.rule.delete_join_messages ? 'bg-primary-500 text-white' : 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
              class="rounded-lg px-3 py-1.5 text-sm"
              @click="updateRule({ delete_join_messages: !chat.rule.delete_join_messages })"
            >
              {{ chat.rule.delete_join_messages ? 'Да' : 'Нет' }}
            </button>
          </div>
          <div>
            <p class="mb-1 text-xs text-gray-500 dark:text-gray-400">Режим тишины (мин)</p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="p in silencePresets"
                :key="p.value"
                type="button"
                :class="(chat.rule.silence_minutes || 0) === p.value ? 'bg-primary-500 text-white' : 'bg-gray-100 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
                class="rounded-lg px-3 py-1.5 text-sm"
                @click="updateRule({ silence_minutes: p.value })"
              >
                {{ p.label }}
              </button>
            </div>
          </div>
          <h3 class="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">Стоп-слова</h3>
          <p class="mb-3 text-xs text-gray-500 dark:text-gray-400">
            Сообщения, содержащие эти слова (в тексте, не внутри ссылок), будут удаляться или наказываться по правилам выше.
          </p>
          <div class="mb-3 flex flex-wrap gap-2">
            <input
              v-model="newStopword"
              type="text"
              placeholder="Добавить слово"
              class="min-w-0 flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
              :disabled="stopwordLoading"
              @keydown.enter.prevent="addStopword()"
            />
            <button
              type="button"
              class="rounded-lg bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600 disabled:opacity-50"
              :disabled="stopwordLoading || !(newStopword || '').trim()"
              @click="addStopword()"
            >
              Добавить
            </button>
          </div>
          <ul v-if="(chat.stopwords || []).length" class="space-y-1">
            <li
              v-for="w in (chat.stopwords || [])"
              :key="w"
              class="flex items-center justify-between rounded-lg bg-gray-100 px-3 py-2 text-sm dark:bg-gray-700"
            >
              <span class="text-gray-800 dark:text-gray-200">{{ w }}</span>
              <button
                type="button"
                class="rounded p-1 text-red-600 hover:bg-red-100 dark:text-red-400 dark:hover:bg-red-900/30"
                :disabled="stopwordLoading"
                aria-label="Удалить"
                @click="removeStopword(w)"
              >
                ✕
              </button>
            </li>
          </ul>
          <p v-else class="text-sm text-gray-500 dark:text-gray-400">
            Нет стоп-слов. Добавьте слово выше.
          </p>
        </div>
      </section>

      <!-- Наказания -->
      <section class="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 class="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">Наказания</h2>
        <div class="space-y-3">
          <div>
            <p class="mb-1 text-xs text-gray-500 dark:text-gray-400">Действие</p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="opt in actionOptions"
                :key="opt.value"
                type="button"
                :class="chat.rule.action_mode === opt.value ? 'bg-primary-500 text-white' : 'bg-gray-100 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
                class="rounded-lg px-3 py-1.5 text-sm"
                @click="updateRule({ action_mode: opt.value })"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>
          <div v-if="chat.rule.action_mode === 'mute'">
            <p class="mb-1 text-xs text-gray-500 dark:text-gray-400">Длительность мута (мин)</p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="m in mutePresets"
                :key="m"
                type="button"
                :class="chat.rule.mute_minutes === m ? 'bg-primary-500 text-white' : 'bg-gray-100 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
                class="rounded-lg px-3 py-1.5 text-sm"
                @click="updateRule({ mute_minutes: m })"
              >
                {{ m }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- Новички -->
      <section class="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 class="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">Новички</h2>
        <div class="space-y-3">
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm text-gray-600 dark:text-gray-400">Режим новичков</span>
            <button
              type="button"
              :class="chat.rule.newbie_enabled ? 'bg-primary-500 text-white' : 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
              class="rounded-lg px-3 py-1.5 text-sm"
              @click="updateRule({ newbie_enabled: !chat.rule.newbie_enabled })"
            >
              {{ chat.rule.newbie_enabled ? 'ВКЛ' : 'ВЫКЛ' }}
            </button>
          </div>
          <div v-if="chat.rule.newbie_enabled">
            <p class="mb-1 text-xs text-gray-500 dark:text-gray-400">Окно (мин)</p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="m in newbiePresets"
                :key="m"
                type="button"
                :class="chat.rule.newbie_minutes === m ? 'bg-primary-500 text-white' : 'bg-gray-100 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
                class="rounded-lg px-3 py-1.5 text-sm"
                @click="updateRule({ newbie_minutes: m })"
              >
                {{ m }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <p v-if="saving" class="text-sm text-gray-500 dark:text-gray-400">Сохранение…</p>
    </div>

    <div v-else-if="loading" class="rounded-xl border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-gray-800">
      <span class="text-gray-500 dark:text-gray-400">Загрузка…</span>
    </div>
  </div>
</template>

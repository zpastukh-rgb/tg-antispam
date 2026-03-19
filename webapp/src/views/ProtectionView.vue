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
const chatsList = ref([])
const antispamItems = ref([])
const antispamLoading = ref(false)
const newAntispamUserId = ref('')
const copyTargetId = ref(null)
const copyLoading = ref(false)
const botUsername = ref(null)
const isPremium = ref(false)
const profanityItems = ref([])
const newProfanityWord = ref('')
const profanityLoading = ref(false)

onMounted(async () => {
  if (!hasInitData.value) return
  try {
    const [chatsRes, botData, meData] = await Promise.all([
      fetch(() => api.chats()),
      fetch(() => api.botInfo()).catch(() => null),
      fetch(() => api.me()).catch(() => ({ is_premium: false })),
    ])
    const { chats, selected_chat_id } = chatsRes || {}
    isPremium.value = !!meData?.is_premium
    botUsername.value = botData?.username ?? null
    chatsList.value = chats || []
    if (!selected_chat_id) {
      chat.value = { noSelection: true }
      return
    }
    const data = await fetch(() => api.chat(selected_chat_id))
    chat.value = data
    const [antispam, profanity] = await Promise.all([
      fetch(() => api.globalAntispamList()).catch(() => ({ items: [] })),
      fetch(() => api.profanityList()).catch(() => ({ items: [] })),
    ])
    antispamItems.value = antispam?.items || []
    profanityItems.value = profanity?.items || []
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

async function loadAntispamList() {
  antispamLoading.value = true
  try {
    const data = await fetch(() => api.globalAntispamList())
    antispamItems.value = data?.items || []
  } finally {
    antispamLoading.value = false
  }
}

async function addAntispamUser() {
  const uid = (newAntispamUserId.value || '').trim()
  if (!uid || !/^\d+$/.test(uid)) {
    showToast('Введите числовой user_id')
    return
  }
  antispamLoading.value = true
  try {
    await fetch(() => api.globalAntispamAdd(Number(uid)))
    newAntispamUserId.value = ''
    await loadAntispamList()
    showToast('Добавлено в антиспам базу')
  } finally {
    antispamLoading.value = false
  }
}

async function removeAntispamUser(userId) {
  antispamLoading.value = true
  try {
    await fetch(() => api.globalAntispamRemove(userId))
    antispamItems.value = antispamItems.value.filter((i) => i.user_id !== userId)
    showToast('Удалено из базы')
  } finally {
    antispamLoading.value = false
  }
}

async function addProfanityWord() {
  const word = (newProfanityWord.value || '').trim()
  if (!word) return
  profanityLoading.value = true
  try {
    await fetch(() => api.profanityAdd(word))
    newProfanityWord.value = ''
    const data = await fetch(() => api.profanityList())
    profanityItems.value = data?.items || []
    showToast('Слово добавлено в фильтр мата')
  } finally {
    profanityLoading.value = false
  }
}

async function removeProfanityWord(word) {
  profanityLoading.value = true
  try {
    await fetch(() => api.profanityRemove(word))
    profanityItems.value = profanityItems.value.filter((i) => i.word !== word)
    showToast('Слово удалено из фильтра')
  } finally {
    profanityLoading.value = false
  }
}

/** Открыть бота по deep link для запуска очистки от удалённых (на мобильном — в Telegram, можно закрыть мини-приложение). */
function openCleanDeleted(event) {
  if (!chat.value?.id || !botUsername.value) return
  const url = `https://t.me/${botUsername.value}?start=cleandeleted_${chat.value.id}`
  if (window.Telegram?.WebApp?.openTelegramLink) {
    event?.preventDefault()
    window.Telegram.WebApp.openTelegramLink(url)
    setTimeout(() => {
      if (window.Telegram?.WebApp?.close) window.Telegram.WebApp.close()
    }, 400)
  }
}

async function doCopySettings() {
  if (!chat.value?.id || !copyTargetId.value || chat.value.noSelection) return
  if (Number(copyTargetId.value) === chat.value.id) {
    showToast('Выберите другой чат')
    return
  }
  copyLoading.value = true
  try {
    await fetch(() => api.copySettings(chat.value.id, Number(copyTargetId.value)))
    showToast('Настройки перенесены')
    copyTargetId.value = null
  } finally {
    copyLoading.value = false
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
const antinakrutkaThresholdPresets = [5, 10, 15, 20]
const antinakrutkaWindowPresets = [3, 5, 10]
const antinakrutkaActionOptions = [
  { value: 'alert', label: 'Только оповещение' },
  { value: 'alert_restrict', label: 'Оповещение + мут' },
]
const antinakrutkaRestrictPresets = [15, 30, 60]
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
            <p class="mb-1 text-xs text-gray-500 dark:text-gray-400">Режим тишины (мин) <span v-if="!isPremium" class="text-amber-600 dark:text-amber-400">🔒 Premium</span></p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="p in silencePresets"
                :key="p.value"
                type="button"
                :class="(chat.rule.silence_minutes || 0) === p.value ? 'bg-primary-500 text-white' : 'bg-gray-100 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
                class="rounded-lg px-3 py-1.5 text-sm"
                :disabled="!isPremium"
                @click="isPremium && updateRule({ silence_minutes: p.value })"
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

          <h3 class="mb-2 mt-4 text-sm font-medium text-gray-700 dark:text-gray-300">Фильтр мата</h3>
          <p class="mb-3 text-xs text-gray-500 dark:text-gray-400">
            Сообщения, содержащие слова из списка мата, будут удаляться или наказываться по правилам. Общий список по всем чатам; можно добавлять свои слова.
          </p>
          <div class="flex items-center justify-between gap-2 mb-3">
            <span class="text-sm text-gray-600 dark:text-gray-400">Включить фильтр мата</span>
            <button
              type="button"
              :class="chat.rule.filter_profanity_enabled ? 'bg-primary-500 text-white' : 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
              class="rounded-lg px-3 py-1.5 text-sm"
              @click="updateRule({ filter_profanity_enabled: !chat.rule.filter_profanity_enabled })"
            >
              {{ chat.rule.filter_profanity_enabled ? 'ВКЛ' : 'ВЫКЛ' }}
            </button>
          </div>
          <div class="mb-3 flex flex-wrap gap-2">
            <input
              v-model="newProfanityWord"
              type="text"
              placeholder="Добавить слово"
              class="min-w-0 flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
              :disabled="profanityLoading"
              @keydown.enter.prevent="addProfanityWord()"
            />
            <button
              type="button"
              class="rounded-lg bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600 disabled:opacity-50"
              :disabled="profanityLoading || !(newProfanityWord || '').trim()"
              @click="addProfanityWord()"
            >
              Добавить
            </button>
          </div>
          <ul v-if="(profanityItems || []).length" class="max-h-32 space-y-1 overflow-y-auto">
            <li
              v-for="item in (profanityItems || []).slice(0, 30)"
              :key="item.word"
              class="flex items-center justify-between rounded-lg bg-gray-100 px-3 py-1.5 text-sm dark:bg-gray-700"
            >
              <span class="text-gray-800 dark:text-gray-200">{{ item.word }}</span>
              <button
                type="button"
                class="rounded p-1 text-red-600 hover:bg-red-100 dark:text-red-400 dark:hover:bg-red-900/30"
                :disabled="profanityLoading"
                aria-label="Удалить"
                @click="removeProfanityWord(item.word)"
              >
                ✕
              </button>
            </li>
          </ul>
          <p v-if="(profanityItems || []).length > 30" class="text-xs text-gray-500 dark:text-gray-400">
            Показано 30 из {{ profanityItems.length }}. Остальные в боте.
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

      <!-- Антинакрутка (Premium) -->
      <section class="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 class="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">📈 Антинакрутка <span v-if="!isPremium" class="text-amber-600 dark:text-amber-400">🔒 Premium</span></h2>
        <p class="mb-3 text-xs text-gray-500 dark:text-gray-400">
          Оповещение и реакция на массовый вход в группу или чат комментариев канала.
        </p>
        <div class="space-y-3">
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm text-gray-600 dark:text-gray-400">Включить</span>
            <button
              type="button"
              :class="chat.rule.antinakrutka_enabled ? 'bg-primary-500 text-white' : 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
              class="rounded-lg px-3 py-1.5 text-sm"
              :disabled="!isPremium"
              @click="isPremium && updateRule({ antinakrutka_enabled: !chat.rule.antinakrutka_enabled })"
            >
              {{ chat.rule.antinakrutka_enabled ? 'ВКЛ' : 'ВЫКЛ' }}
            </button>
          </div>
          <div v-if="chat.rule.antinakrutka_enabled && isPremium">
            <p class="mb-1 text-xs text-gray-500 dark:text-gray-400">Порог (участников за окно)</p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="n in antinakrutkaThresholdPresets"
                :key="n"
                type="button"
                :class="(chat.rule.antinakrutka_joins_threshold || 10) === n ? 'bg-primary-500 text-white' : 'bg-gray-100 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
                class="rounded-lg px-3 py-1.5 text-sm"
                @click="updateRule({ antinakrutka_joins_threshold: n })"
              >
                {{ n }}
              </button>
            </div>
            <p class="mb-1 mt-2 text-xs text-gray-500 dark:text-gray-400">Окно (мин)</p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="w in antinakrutkaWindowPresets"
                :key="w"
                type="button"
                :class="(chat.rule.antinakrutka_window_minutes || 5) === w ? 'bg-primary-500 text-white' : 'bg-gray-100 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
                class="rounded-lg px-3 py-1.5 text-sm"
                @click="updateRule({ antinakrutka_window_minutes: w })"
              >
                {{ w }} мин
              </button>
            </div>
            <p class="mb-1 mt-2 text-xs text-gray-500 dark:text-gray-400">Действие</p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="opt in antinakrutkaActionOptions"
                :key="opt.value"
                type="button"
                :class="(chat.rule.antinakrutka_action || 'alert') === opt.value ? 'bg-primary-500 text-white' : 'bg-gray-100 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
                class="rounded-lg px-3 py-1.5 text-sm"
                @click="updateRule({ antinakrutka_action: opt.value })"
              >
                {{ opt.label }}
              </button>
            </div>
            <div v-if="(chat.rule.antinakrutka_action || 'alert') === 'alert_restrict'">
              <p class="mb-1 mt-2 text-xs text-gray-500 dark:text-gray-400">Мут (мин)</p>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="r in antinakrutkaRestrictPresets"
                  :key="r"
                  type="button"
                  :class="(chat.rule.antinakrutka_restrict_minutes || 30) === r ? 'bg-primary-500 text-white' : 'bg-gray-100 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
                  class="rounded-lg px-3 py-1.5 text-sm"
                  @click="updateRule({ antinakrutka_restrict_minutes: r })"
                >
                  {{ r }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Антиспам база (Premium) -->
      <section class="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 class="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">📋 Антиспам база <span v-if="!isPremium" class="text-amber-600 dark:text-amber-400">🔒 Premium</span></h2>
        <p class="mb-3 text-xs text-gray-500 dark:text-gray-400">
          Общая база пользователей по всем группам бота. При включении пользователи из базы будут исключаться при входе в этот чат.
        </p>
        <p class="mb-3 rounded-lg bg-amber-50 p-2 text-xs text-amber-800 dark:bg-amber-900/30 dark:text-amber-200">
          <strong>Откуда взять User ID?</strong> В группе ответьте на сообщение пользователя и отправьте команду <code>/addantispam</code> — бот добавит его в базу. Либо введите числовой ID, если знаете его.
        </p>
        <div class="space-y-3">
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm text-gray-600 dark:text-gray-400">Проверять при входе в этот чат</span>
            <button
              type="button"
              :class="chat.rule.use_global_antispam_db ? 'bg-primary-500 text-white' : 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
              class="rounded-lg px-3 py-1.5 text-sm"
              :disabled="!isPremium"
              @click="isPremium && updateRule({ use_global_antispam_db: !chat.rule.use_global_antispam_db })"
            >
              {{ chat.rule.use_global_antispam_db ? 'ВКЛ' : 'ВЫКЛ' }}
            </button>
          </div>
          <p class="text-xs text-gray-500 dark:text-gray-400">Записей в базе: {{ (antispamItems || []).length }}</p>
          <div class="flex flex-wrap gap-2">
            <input
              v-model="newAntispamUserId"
              type="text"
              placeholder="User ID (число)"
              class="min-w-0 flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
              :disabled="antispamLoading"
              @keydown.enter.prevent="addAntispamUser()"
            />
            <button
              type="button"
              class="rounded-lg bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600 disabled:opacity-50"
              :disabled="antispamLoading || !(newAntispamUserId || '').trim()"
              @click="addAntispamUser()"
            >
              Добавить
            </button>
          </div>
          <p v-if="(antispamItems || []).length" class="text-xs text-gray-500 dark:text-gray-400">
            Чтобы убрать пользователя из базы — нажмите «Удалить» рядом с записью.
          </p>
          <ul v-if="(antispamItems || []).length" class="max-h-48 space-y-2 overflow-y-auto">
            <li
              v-for="item in antispamItems"
              :key="item.user_id"
              class="flex items-center justify-between gap-2 rounded-lg bg-gray-100 px-3 py-2 text-sm dark:bg-gray-700"
            >
              <span class="min-w-0 flex-1 text-gray-800 dark:text-gray-200">{{ item.user_id }}{{ item.reason ? ` — ${item.reason}` : '' }}</span>
              <button
                type="button"
                class="shrink-0 rounded-lg border border-red-300 bg-red-50 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-100 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300 dark:hover:bg-red-900/50"
                :disabled="antispamLoading"
                @click="removeAntispamUser(item.user_id)"
              >
                Удалить
              </button>
            </li>
          </ul>
        </div>
      </section>

      <!-- Очистка от удалённых аккаунтов -->
      <section class="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 class="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">🧹 Очистка от удалённых аккаунтов</h2>
        <p class="mb-3 text-xs text-gray-500 dark:text-gray-400">
          Проверка группы на удалённые аккаунты и исключение их из чата. Нажмите кнопку — откроется чат с ботом, очистка запустится для выбранной группы.
        </p>
        <a
          v-if="chat?.id && botUsername"
          :href="`https://t.me/${botUsername}?start=cleandeleted_${chat.id}`"
          target="_blank"
          rel="noopener noreferrer"
          class="inline-flex items-center gap-2 rounded-xl bg-primary-500 px-4 py-3 font-medium text-white shadow-sm transition hover:bg-primary-600"
          @click="openCleanDeleted"
        >
          Запустить очистку
        </a>
        <p v-else class="text-xs text-gray-500 dark:text-gray-400">
          Выберите чат выше или откройте очистку в боте: Защита → Очистить от удалённых.
        </p>
      </section>

      <!-- Перенести настройки (доступно при нескольких чатах / Premium) -->
      <section class="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 class="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">📤 Перенести настройки <span v-if="!isPremium && (chatsList || []).length > 1" class="text-amber-600 dark:text-amber-400">🔒 Premium</span></h2>
        <p class="mb-3 text-xs text-gray-500 dark:text-gray-400">
          Скопировать все настройки защиты из текущего чата в выбранный.
        </p>
        <div class="flex flex-wrap items-center gap-2">
          <select
            v-model="copyTargetId"
            class="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
          >
            <option :value="null">Выберите чат</option>
            <option
              v-for="c in (chatsList || []).filter((x) => x.id !== chat?.id)"
              :key="c.id"
              :value="String(c.id)"
            >
              {{ c.title || c.id }}
            </option>
          </select>
          <button
            type="button"
            class="rounded-lg bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600 disabled:opacity-50"
            :disabled="copyLoading || !copyTargetId || String(copyTargetId) === String(chat?.id) || (!isPremium && (chatsList || []).length > 1)"
            @click="(isPremium || (chatsList || []).length <= 1) && doCopySettings()"
          >
            Перенести
          </button>
        </div>
      </section>

      <!-- Новички (Premium) -->
      <section class="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 class="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">Новички <span v-if="!isPremium" class="text-amber-600 dark:text-amber-400">🔒 Premium</span></h2>
        <div class="space-y-3">
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm text-gray-600 dark:text-gray-400">Режим новичков</span>
            <button
              type="button"
              :class="chat.rule.newbie_enabled ? 'bg-primary-500 text-white' : 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-300'"
              class="rounded-lg px-3 py-1.5 text-sm"
              :disabled="!isPremium"
              @click="isPremium && updateRule({ newbie_enabled: !chat.rule.newbie_enabled })"
            >
              {{ chat.rule.newbie_enabled ? 'ВКЛ' : 'ВЫКЛ' }}
            </button>
          </div>
          <div v-if="chat.rule.newbie_enabled && isPremium">
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

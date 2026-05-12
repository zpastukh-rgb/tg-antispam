<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useApi } from '../composables/useApi'
import { useToast } from '../composables/useToast'
import { openTelegramDeepLink } from '../utils/openTelegramDeepLink'

const { t } = useI18n()
const isEn = computed(() => t('common.locale_code') === 'en')
const { api, fetchSilent, hasInitData } = useApi()
const { showToast } = useToast()
const route = useRoute()
const router = useRouter()
const addToGroupUrl = ref(null)
const addToChannelUrl = ref(null)
const preparedAddGroupButtonId = ref(null)
const pendingChats = ref([])
const pendingLoading = ref(false)

const ADMIN_RIGHTS = 'delete_messages+restrict_members+invite_users+pin_messages'
const CHANNEL_ADMIN_RIGHTS = 'post_messages+edit_messages+delete_messages+invite_users'
const connectKind = ref('group')
const isGroupKind = computed(() => connectKind.value === 'group')
const pageTitle = computed(() =>
  isGroupKind.value
    ? (isEn.value ? 'Connect group' : 'Подключить группу')
    : (isEn.value ? 'Connect channel' : 'Подключить канал'),
)
const pendingGroups = computed(() => (pendingChats.value || []).filter((c) => String(c?.chat_kind || 'group') !== 'channel'))
const pendingChannels = computed(() => (pendingChats.value || []).filter((c) => String(c?.chat_kind || '') === 'channel'))
const pendingCurrentKind = computed(() => (isGroupKind.value ? pendingGroups.value : pendingChannels.value))

function buildAddUrl(username) {
  const u = (username || '').replace(/^@/, '').trim()
  if (!u) return null
  return `https://t.me/${u}?startgroup=connect&admin=${ADMIN_RIGHTS}`
}

async function loadConnectData() {
  if (!hasInitData.value) return
  pendingLoading.value = true
  try {
    const [botData, pendingData] = await Promise.all([
      fetchSilent(() => api.botInfo()).catch(() => null),
      fetchSilent(() => api.connectPending()).catch(() => ({ chats: [] })),
    ])
    addToGroupUrl.value = botData?.add_to_group_url || buildAddUrl(botData?.username)
    const username = String(botData?.username || '').replace(/^@/, '').trim()
    addToChannelUrl.value = username ? `https://t.me/${username}?startchannel=connect_channel&admin=${CHANNEL_ADMIN_RIGHTS}` : null
    preparedAddGroupButtonId.value = botData?.prepared_add_group_button_id || null
    pendingChats.value = pendingData?.chats || []
  } catch {
    //
  } finally {
    pendingLoading.value = false
  }
}

onMounted(loadConnectData)

watch(
  () => String(route.query.kind || 'group').toLowerCase(),
  (v) => {
    connectKind.value = v === 'channel' ? 'channel' : 'group'
  },
  { immediate: true },
)

function openAddToGroup() {
  const tg = typeof window !== 'undefined' ? window.Telegram?.WebApp : null
  // 1) Стабильно для защиты: t.me/...?startgroup=connect&admin= (не reportschat_* из «Отчёты»).
  if (addToGroupUrl.value) {
    const ok = openTelegramDeepLink(addToGroupUrl.value)
    if (ok) {
      return
    }
  }
  // 2) Фоллбек Mini App: нативный выбор чата
  const prep = preparedAddGroupButtonId.value
  if (prep && typeof tg?.requestChat === 'function') {
    try {
      tg.requestChat(prep, () => {
        loadConnectData()
      })
      return
    } catch {
      //
    }
  }
  showToast(
    isEn.value
      ? 'Open the Mini App from Telegram. If the link did not work, refresh the screen (pull down) and try again.'
      : 'Откройте мини-приложение из Telegram. Если ссылка не сработала, обновите экран (потяните вниз) и повторите.',
  )
}

function openAddToChannel() {
  if (addToChannelUrl.value) {
    const ok = openTelegramDeepLink(addToChannelUrl.value)
    if (ok) return
  }
  showToast(
    isEn.value
      ? 'Open the Mini App from Telegram and try to connect the channel again.'
      : 'Откройте мини-приложение из Telegram и повторите подключение канала.',
  )
}

async function clearAllPendingChats() {
  if (!hasInitData.value) return
  if (!pendingCurrentKind.value.length) {
    showToast(isEn.value ? 'List is already empty' : 'Список уже пуст')
    return
  }
  const kindLabel = isEn.value
    ? (isGroupKind.value ? 'groups' : 'channels')
    : (isGroupKind.value ? 'групп' : 'каналов')
  const ok = window.confirm(
    isEn.value
      ? `Clear pending ${kindLabel} list? Items will be removed from the panel.`
      : `Очистить список ожидающих ${kindLabel}? Записи будут удалены из панели.`,
  )
  if (!ok) return
  pendingLoading.value = true
  try {
    const data = await fetchSilent(() => api.connectClearAllPending())
    await loadConnectData()
    showToast(
      isEn.value
        ? `Removed: ${data?.removed ?? 0}`
        : `Удалено записей: ${data?.removed ?? 0}`,
    )
  } catch {
    showToast(isEn.value ? 'Failed to clear list' : 'Не удалось очистить список')
  } finally {
    pendingLoading.value = false
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between gap-2">
      <h1 class="text-xl font-semibold text-gray-900 dark:text-white md:text-2xl">{{ pageTitle }}</h1>
      <div class="inline-flex rounded-xl border border-white/10 bg-black/25 p-1 text-[11px]">
        <button
          type="button"
          class="rounded-lg px-2 py-1 font-semibold"
          :class="isGroupKind ? 'bg-lime-500/90 text-slate-900' : 'text-slate-200'"
          @click="router.replace({ path: '/connect', query: { kind: 'group' } })"
        >
          {{ isEn ? 'Group' : 'Группа' }}
        </button>
        <button
          type="button"
          class="rounded-lg px-2 py-1 font-semibold"
          :class="!isGroupKind ? 'bg-amber-400/90 text-slate-900' : 'text-slate-200'"
          @click="router.replace({ path: '/connect', query: { kind: 'channel' } })"
        >
          {{ isEn ? 'Channel' : 'Канал' }}
        </button>
      </div>
    </div>

    <div
      v-if="!hasInitData"
      class="rounded-xl border-2 border-amber-400/80 bg-amber-50 p-4 text-sm text-amber-950 dark:border-amber-600 dark:bg-amber-950/30 dark:text-amber-100"
    >
      {{ isEn ? 'Open this panel from Telegram (bot menu or Mini App button).' : 'Откройте эту панель из Telegram (меню бота или кнопка Mini App).' }}
    </div>

    <template v-else>
      <div
        class="rounded-2xl border border-white/12 bg-black/35 p-4 text-sm text-slate-200 shadow-[0_12px_40px_-20px_rgba(0,0,0,0.5)] ring-1 ring-black/30 backdrop-blur-sm dark:border-white/10 dark:bg-black/40 dark:ring-white/5"
      >
        <p class="text-xs font-semibold uppercase tracking-wide text-slate-400">{{ isEn ? 'Connection' : 'Подключение' }}</p>
        <p v-if="isGroupKind" class="mt-2 text-xs leading-relaxed text-slate-300">
          {{ isEn ? 'Pick a group with the button below and grant the bot admin rights: delete messages and restrict members — protection cannot work without that. Then open “Protection”; reports are under the “Reports” menu.' : 'Выберите группу кнопкой ниже и выдайте боту админку: удаление сообщений и ограничение участников — без этого защита не работает. Затем настройте «Защита»; отчёты — в пункте меню «Отчёты».' }}
        </p>
        <p v-else class="mt-2 text-xs leading-relaxed text-slate-300">
          {{ isEn ? 'Connect a channel to run autopost / broadcasts, see channel analytics separately and manage delegate rights per channel. If the channel has a discussion group, stats will be linked to the discussion group.' : 'Подключите канал, чтобы запускать автопост/рассылки, видеть аналитику канала отдельно и управлять правами делегатов по каналу. Если у канала есть обсуждение, статистика будет связана с группой обсуждения.' }}
        </p>
        <p class="mt-2 text-[11px] leading-relaxed text-slate-500">
          {{ isEn ? 'If the chat is missing from the Telegram list — add the bot as admin and open the picker again.' : 'Если объекта нет в списке Telegram — добавьте бота в администраторы и снова откройте выбор.' }}
        </p>
      </div>

      <div class="flex justify-center pt-1">
        <button
          v-if="isGroupKind && (addToGroupUrl || preparedAddGroupButtonId)"
          type="button"
          class="guard-green-soft max-w-[220px] rounded-xl px-4 py-2 text-sm font-semibold transition active:scale-[0.99]"
          @click="openAddToGroup"
        >
          {{ isEn ? 'Pick a group' : 'Выбрать группу' }}
        </button>
        <button
          v-else-if="!isGroupKind && addToChannelUrl"
          type="button"
          class="max-w-[220px] rounded-xl bg-amber-400/95 px-4 py-2 text-sm font-semibold text-slate-900 shadow-[0_10px_30px_-12px_rgba(251,191,36,0.75)] transition active:scale-[0.99]"
          @click="openAddToChannel"
        >
          {{ isEn ? 'Connect channel' : 'Подключить канал' }}
        </button>
        <p v-else class="py-4 text-center text-sm text-gray-500 dark:text-gray-400">{{ isEn ? 'Loading link…' : 'Загрузка ссылки…' }}</p>
      </div>

      <div
        class="rounded-2xl border border-sky-400/25 bg-sky-950/20 p-3.5 text-xs text-sky-100/95 ring-1 ring-sky-500/15 backdrop-blur-sm dark:border-sky-500/25 dark:bg-sky-950/25 dark:text-sky-100"
      >
        <p class="font-medium text-sky-50/95">{{ isEn ? (isGroupKind ? 'Pending groups to connect' : 'Pending channels to connect') : (isGroupKind ? 'Ожидают подключения группы' : 'Ожидают подключения каналы') }}</p>
        <ul v-if="pendingCurrentKind.length" class="mt-1.5 list-disc space-y-0.5 pl-4 text-sky-100/90">
          <li v-for="c in pendingCurrentKind" :key="c.id">
            {{ c.title }}
            <span v-if="c.is_shared" class="ml-1 rounded border border-violet-500/40 bg-violet-500/20 px-1 py-[1px] text-[10px] text-violet-100">{{ isEn ? 'delegated' : 'делегировано' }}</span>
          </li>
        </ul>
        <p v-else class="mt-1.5 text-sky-200/70">{{ isEn ? 'Empty for now.' : 'Пока пусто.' }}</p>
        <div class="mt-3">
          <button
            type="button"
            class="rounded-lg border border-rose-400 px-3 py-1.5 text-xs font-semibold text-rose-900 hover:bg-rose-50 dark:border-rose-600 dark:text-rose-100 dark:hover:bg-rose-950/40 disabled:opacity-50"
            :disabled="pendingLoading"
            @click="clearAllPendingChats"
          >
            {{ isEn ? 'Clear list' : 'Очистить список' }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

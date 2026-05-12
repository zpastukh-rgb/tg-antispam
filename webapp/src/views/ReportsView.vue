<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useApi } from '../composables/useApi'
import { useToast } from '../composables/useToast'
import { openTelegramDeepLink } from '../utils/openTelegramDeepLink'
import GuardBlueLoadingState from '../components/GuardBlueLoadingState.vue'
import { useCabinetMode } from '../composables/useCabinetMode'

const router = useRouter()
const route = useRoute()
const { cabinetMode, setCabinetMode } = useCabinetMode()
const { api, error, fetchSilent, hasInitData } = useApi()
const { showToast } = useToast()
const { t } = useI18n()
const isEn = computed(() => t('common.locale_code') === 'en')
const chat = ref(null)
const chatsList = ref([])
const selectedChatId = ref(null)
const showChatPicker = ref(false)
const reportsChatUrl = ref(null)
const saving = ref(false)
const clearing = ref(false)
const showReportsInfoModal = ref(false)
const botInfo = ref(null)
const meProfile = ref(null)
let stopListen = null

function boolToggleClass(on) {
  return on ? 'guard-green-soft' : 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-300'
}

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
  if (!selectedChatId.value) return
  try {
    const data = await fetchSilent(() => api.chat(selectedChatId.value))
    chat.value = data
  } catch {
    //
  }
}

const selectedChatTitle = computed(() => {
  const current = (chatsList.value || []).find((c) => Number(c.id) === Number(selectedChatId.value))
  return current?.title || chat.value?.title || (isEn.value ? 'No chat selected' : 'Чат не выбран')
})

const chatsListMine = computed(() => (chatsList.value || []).filter((c) => !c.is_shared))
const chatsListDelegated = computed(() => (chatsList.value || []).filter((c) => !!c.is_shared))

const selectedRow = computed(() =>
  (chatsList.value || []).find((c) => Number(c.id) === Number(selectedChatId.value)),
)

async function switchChat(chatId) {
  if (!chatId || Number(chatId) === Number(selectedChatId.value)) return
  try {
    await fetchSilent(() => api.selectChat(Number(chatId)))
    selectedChatId.value = Number(chatId)
    const row = (chatsList.value || []).find((c) => Number(c.id) === Number(chatId))
    if (row?.is_shared) {
      setCabinetMode('delegated')
    } else {
      setCabinetMode('owner')
    }
    await reloadChat()
    reportsChatUrl.value = buildReportsUrl(botInfo.value, selectedChatId.value)
    showChatPicker.value = false
  } catch {
    //
  }
}

onMounted(async () => {
  error.value = null
  if (!hasInitData.value) return
  try {
    const [chatsData, botData, meData] = await Promise.all([
      fetchSilent(() => api.chats('all')).catch(() => ({ selected_chat_id: null, chats: [] })),
      fetchSilent(() => api.botInfo()).catch(() => ({})),
      fetchSilent(() => api.me()).catch(() => null),
    ])
    const requestedChatId = Number(route.query?.chat_id || 0) || null
    let selected_chat_id = chatsData?.selected_chat_id
    if (requestedChatId && (chatsData?.chats || []).some((c) => Number(c.id) === requestedChatId)) {
      selected_chat_id = requestedChatId
      await fetchSilent(() => api.selectChat(requestedChatId)).catch(() => {})
    }
    chatsList.value = chatsData?.chats || []
    botInfo.value = botData || null
    meProfile.value = meData || null
    if (!selected_chat_id) {
      const fallback = (chatsData?.chats || []).find((c) => Number(c?.id || 0) !== 0)
      if (fallback?.id) {
        selected_chat_id = Number(fallback.id)
        await fetchSilent(() => api.selectChat(selected_chat_id)).catch(() => {})
      }
    }
    if (!selected_chat_id) {
      chat.value = { noSelection: true }
      return
    }
    selectedChatId.value = selected_chat_id
    const picked = (chatsData?.chats || []).find((c) => Number(c.id) === Number(selected_chat_id))
    if (picked?.is_shared) {
      setCabinetMode('delegated')
    } else {
      setCabinetMode('owner')
    }
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
    showToast(isEn.value ? 'Could not get the link. Check API and bot.' : 'Не удалось получить ссылку. Проверьте API и бота.')
    return
  }
  openTelegramDeepLink(url)
}

async function clearReportsChat() {
  if (!chat.value?.id) return
  clearing.value = true
  try {
    const res = await fetchSilent(() => api.setReportsChat(chat.value.id, null))
    chat.value.log_chat_id = res.log_chat_id
    chat.value.log_chat_title = res.log_chat_title
    showToast(isEn.value ? 'Reports chat disconnected' : 'Чат отчётов отключён')
  } catch (e) {
    showToast(e?.body?.detail || (isEn.value ? 'Error' : 'Ошибка'))
  } finally {
    clearing.value = false
  }
}

async function refreshReportsStatus() {
  if (!selectedChatId.value) return
  try {
    const chatsData = await fetchSilent(() => api.chats('all')).catch(() => null)
    if (chatsData?.chats) chatsList.value = chatsData.chats
    await reloadChat()
    showToast(isEn.value ? 'Updated' : 'Обновлено')
  } catch {
    showToast(isEn.value ? 'Could not refresh' : 'Не удалось обновить')
  }
}

async function updateRule(patch) {
  if (!chat.value?.id || chat.value.noSelection) return
  saving.value = true
  try {
    const data = await fetchSilent(() => api.updateRule(chat.value.id, patch))
    chat.value.rule = data.rule
    showToast(isEn.value ? 'Saved' : 'Сохранено')
  } finally {
    saving.value = false
  }
}

function goToExtendedStatsReports() {
  if (meProfile.value?.is_premium) {
    router.push({ path: '/admin', query: { tab: 'overview', open: 'stats_reports' } }).catch(() => {})
    return
  }
  showToast(isEn.value ? 'Extended stats require Premium Guard' : 'Расширенная статистика — с Premium Guard')
  router.push({ path: '/admin', query: { tab: 'overview', open: 'stats_reports' } }).catch(() => {})
}

function goPremiumFromReports() {
  router.push({ path: '/', query: { section: 'subscription' } }).catch(() => {})
}
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold text-slate-900 dark:text-white md:text-2xl">{{ t('reports.title') }}</h1>

    <div
      v-if="!hasInitData"
      class="rounded-2xl border border-amber-400/35 bg-amber-500/10 p-4 text-sm text-amber-100 ring-1 ring-amber-400/20 backdrop-blur-xl"
    >
      {{ t('app.init_required') }}
    </div>

    <div
      v-else-if="chat?.noSelection"
      class="rounded-2xl border border-white/12 bg-zinc-950/50 p-6 text-slate-200 ring-1 ring-white/10 backdrop-blur-2xl"
    >
      <p class="text-sm text-slate-300">{{ isEn ? 'Pick a group in "Connected chats" first to configure reports.' : 'Сначала в «Подключённые чаты» выберите группу, для которой настраиваете отчёты.' }}</p>
      <button
        type="button"
        class="guard-green-soft mt-3 rounded-lg px-4 py-2 text-sm font-semibold"
        @click="router.push(cabinetMode === 'delegated' ? { path: '/chats', query: { cabinet: 'delegated' } } : '/chats')"
      >
        {{ isEn ? 'Go to chat list' : 'К списку чатов' }}
      </button>
    </div>

    <div
      v-else-if="chat?.loadError || error"
      class="rounded-2xl border border-red-400/40 bg-red-950/30 p-4 text-sm text-red-100 ring-1 ring-red-500/20 backdrop-blur-xl"
    >
      {{ error || (isEn ? 'Could not load data' : 'Не удалось загрузить данные') }}
    </div>

    <div v-else-if="chat?.rule">
      <div
        v-if="meProfile && !meProfile.is_premium && cabinetMode !== 'delegated'"
        class="mb-3 overflow-hidden rounded-[1.1rem] border border-violet-500/35 bg-gradient-to-br from-violet-950/45 via-[#0c0a12] to-black p-3 text-[12px] leading-snug text-violet-50/95 shadow-[0_0_36px_-12px_rgba(139,92,246,0.4)] ring-1 ring-violet-400/20"
      >
        <p class="font-semibold text-violet-200">{{ isEn ? '😈 Guard · reports' : '😈 Guard · отчёты' }}</p>
        <p class="mt-1 text-[11px] text-slate-300">
          {{ isEn
            ? 'On Free, extended stats and per-chat summaries are not shown (without Premium they would be zeros). Get '
            : 'На Free расширенная статистика и сводки по чатам не показываются (без Premium это были бы нули). Оформите ' }}
          <b class="text-violet-200">Premium Guard</b>
          {{ isEn
            ? ' — charts, reports and "Track" button become unlimited.'
            : ' — откроются графики, отчёты и кнопка «Отслеживать» без ограничений.' }}
        </p>
        <button
          type="button"
          class="mt-2 w-full rounded-xl bg-violet-600 py-2.5 text-xs font-bold text-white shadow-[0_10px_28px_-8px_rgba(124,58,237,0.5)] transition hover:bg-violet-500 active:scale-[0.99]"
          @click="goPremiumFromReports"
        >
          {{ isEn ? 'Get Premium' : 'Оформить Premium' }}
        </button>
      </div>
      <div
        class="relative -mx-4 overflow-hidden rounded-2xl border border-white/[0.1] bg-white/[0.05] shadow-[0_24px_80px_-32px_rgba(0,0,0,0.75),inset_0_1px_0_rgba(255,255,255,0.06)] ring-1 ring-white/[0.06] backdrop-blur-2xl md:-mx-6"
      >
      <div class="relative z-10 space-y-2.5 px-4 py-3 pb-10 md:px-6 md:pb-12">
        <div class="flex flex-wrap items-center gap-2 text-[11px] leading-snug text-slate-300">
          <span>{{ isEn ? 'Group:' : 'Группа:' }} <strong class="text-white">{{ chat.title }}</strong></span>
          <span
            v-if="selectedRow?.is_shared"
            class="rounded-full border border-violet-400/40 bg-violet-500/15 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-violet-100"
          >{{ isEn ? 'Delegated' : 'Делегированный' }}</span>
          <span
            v-else-if="selectedRow && !selectedRow.is_shared"
            class="rounded-full border border-cyan-400/35 bg-cyan-500/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-cyan-100"
          >{{ isEn ? 'My chat' : 'Мой чат' }}</span>
        </div>
        <div
          class="relative overflow-hidden rounded-[1.15rem] border border-slate-700/65 bg-zinc-950/45 p-1.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] ring-1 ring-slate-700/40 backdrop-blur-2xl"
        >
          <div class="flex items-center gap-1.5">
            <div
              class="guard-green-chip min-w-0 flex-1 rounded-lg border border-emerald-400/25 px-2 py-1.5 text-xs font-semibold"
            >
              <span class="block truncate">{{ selectedChatTitle }}</span>
            </div>
            <button
              type="button"
              class="shrink-0 rounded-lg border border-slate-700/70 bg-zinc-900/75 px-2.5 py-1.5 text-[11px] font-semibold text-slate-100 transition hover:bg-zinc-800/80"
              :aria-label="isEn ? 'Pick chat' : 'Выбор чата'"
              @click="showChatPicker = true"
            >
              {{ isEn ? 'Chat' : 'Чат' }}
            </button>
          </div>
        </div>

        <section
          class="overflow-hidden rounded-[1.1rem] border border-slate-700/65 bg-zinc-950/35 p-2.5 ring-1 ring-slate-700/35 backdrop-blur-2xl"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <h2 class="text-[11px] font-semibold uppercase tracking-wide text-slate-100">{{ isEn ? 'Extended statistics and reports' : 'Расширенная статистика и отчёты' }}</h2>
              <p class="mt-1 text-[10px] leading-snug text-slate-400">
                {{ isEn ? 'Per-chat and channel stats + extended reports.' : 'Статистика по чатам и каналам + расширенные отчёты.' }}
              </p>
            </div>
            <span
              v-if="!meProfile?.is_premium"
              class="shrink-0 rounded-full border border-amber-500/35 bg-amber-500/12 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-amber-200"
            >
              Premium
            </span>
          </div>
          <button
            type="button"
            class="mt-2 w-full rounded-lg border border-cyan-500/35 bg-cyan-500/12 px-3 py-2 text-xs font-semibold text-cyan-100 transition hover:bg-cyan-500/20 active:scale-[0.99]"
            @click="goToExtendedStatsReports"
          >
            {{ isEn ? 'Track' : 'Отслеживать' }}
          </button>
        </section>

        <div
          class="overflow-hidden rounded-[1.1rem] border border-violet-400/25 bg-violet-950/20 p-2.5 text-[11px] leading-snug text-violet-50/95 ring-1 ring-violet-500/20 backdrop-blur-2xl"
        >
          <div class="flex items-start justify-between gap-1.5">
            <p class="min-w-0 flex-1 font-medium text-violet-50/95">{{ isEn ? 'Reports log chat' : 'Лог-чат отчётов' }}</p>
            <button
              type="button"
              class="inline-flex h-6 min-w-6 shrink-0 items-center justify-center rounded-full border border-sky-400/35 bg-sky-950/25 px-1.5 text-[10px] font-extrabold text-sky-200 hover:bg-sky-900/35 dark:border-sky-500/35 dark:bg-sky-950/35"
              :aria-label="isEn ? 'About reports chat' : 'Информация о чате отчётов'"
              @click="showReportsInfoModal = true"
            >
              i
            </button>
          </div>
          <p class="mt-1 text-[10px] leading-snug text-violet-200/80">
            {{ isEn ? 'Another group (e.g. "Logs") for the journal — not the main protected chat.' : 'Другая группа (напр. «Логи») для журнала — не основная защищаемая.' }}
          </p>
        </div>

        <section
          class="overflow-hidden rounded-[1.1rem] border border-sky-400/30 bg-sky-950/15 p-2.5 ring-1 ring-sky-500/20 backdrop-blur-2xl"
        >
          <h2 class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-sky-100/90">
            {{ isEn ? 'Connection' : 'Подключение' }}
          </h2>
          <p class="mb-2 text-[10px] leading-snug text-slate-300/90">
            {{ isEn ? 'Button → pick a group in Telegram, the bot goes to the log chat. Come back — status will refresh.' : 'Кнопка → выбор группы в Telegram, бот в лог-чат. Вернитесь сюда — статус обновится.' }}
          </p>
          <div
            v-if="chat.log_chat_id"
            class="mb-2 flex items-center justify-between gap-1.5 rounded-lg border border-emerald-400/40 bg-emerald-950/25 px-2 py-1.5 text-[11px] text-emerald-100 ring-1 ring-emerald-500/15"
          >
            <span class="min-w-0 truncate">✓ {{ chat.log_chat_title || chat.log_chat_id }}</span>
            <button
              type="button"
              class="shrink-0 rounded px-1.5 py-0.5 text-emerald-200 hover:bg-white/10"
              :disabled="clearing"
              :aria-label="isEn ? 'Remove reports chat' : 'Удалить чат отчётов'"
              @click="clearReportsChat"
            >
              ✕
            </button>
          </div>

          <div class="flex flex-col items-stretch gap-1.5">
            <button
              v-if="reportsChatUrl"
              type="button"
              class="guard-green-soft w-full max-w-[240px] self-center rounded-lg px-3 py-2 text-xs font-semibold transition active:scale-[0.99]"
              @click="openPickReportsGroup"
            >
              {{ chat.log_chat_id ? (isEn ? 'Change log chat' : 'Сменить лог-чат') : (isEn ? 'Connect log chat' : 'Подключить лог-чат') }}
            </button>
            <p v-if="!reportsChatUrl" class="text-center text-[10px] text-slate-400">{{ isEn ? 'No link — check the API.' : 'Нет ссылки — проверьте API.' }}</p>
            <button
              type="button"
              class="w-full max-w-[240px] self-center rounded-lg border border-slate-700/70 bg-zinc-900/75 px-3 py-2 text-xs font-semibold text-slate-100 transition hover:bg-zinc-800/80 active:scale-[0.99]"
              @click="refreshReportsStatus"
            >
              {{ isEn ? 'Refresh' : 'Обновить' }}
            </button>
            <span v-if="clearing" class="text-center text-[10px] text-slate-400">{{ isEn ? 'Disconnecting…' : 'Отключаем…' }}</span>
          </div>
        </section>

        <section
          class="overflow-hidden rounded-[1.1rem] border border-slate-700/65 bg-zinc-950/35 p-2.5 ring-1 ring-slate-700/35 backdrop-blur-2xl"
        >
          <h2 class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-200">{{ isEn ? 'Settings' : 'Настройки' }}</h2>
          <div class="space-y-1.5">
            <div class="flex items-center justify-between gap-2 rounded-lg border border-slate-700/65 bg-zinc-900/70 px-2 py-1.5 ring-1 ring-slate-700/35">
              <span class="text-[11px] text-slate-200/90">{{ isEn ? 'To chat' : 'В чат' }}</span>
              <button
                type="button"
                :class="boolToggleClass(chat.rule.log_enabled)"
                class="rounded-md px-2 py-0.5 text-[11px] font-semibold"
                @click="updateRule({ log_enabled: !chat.rule.log_enabled })"
              >
                {{ chat.rule.log_enabled ? (isEn ? 'ON' : 'ВКЛ') : (isEn ? 'OFF' : 'ВЫКЛ') }}
              </button>
            </div>
            <div class="flex items-center justify-between gap-2 rounded-lg border border-slate-700/65 bg-zinc-900/70 px-2 py-1.5 ring-1 ring-slate-700/35">
              <span class="text-[11px] text-slate-200/90">{{ isEn ? 'Guard msgs' : 'Сообщ. Guard' }}</span>
              <button
                type="button"
                :class="boolToggleClass(chat.rule.guardian_messages_enabled)"
                class="rounded-md px-2 py-0.5 text-[11px] font-semibold"
                @click="updateRule({ guardian_messages_enabled: !chat.rule.guardian_messages_enabled })"
              >
                {{ chat.rule.guardian_messages_enabled ? (isEn ? 'ON' : 'ВКЛ') : (isEn ? 'OFF' : 'ВЫКЛ') }}
              </button>
            </div>
            <div class="flex items-center justify-between gap-2 rounded-lg border border-slate-700/65 bg-zinc-900/70 px-2 py-1.5 ring-1 ring-slate-700/35">
              <span class="text-[11px] text-slate-200/90">{{ isEn ? 'Auto reports' : 'Автоотчёты' }}</span>
              <button
                type="button"
                :class="boolToggleClass(chat.rule.auto_reports_enabled)"
                class="rounded-md px-2 py-0.5 text-[11px] font-semibold"
                @click="updateRule({ auto_reports_enabled: !chat.rule.auto_reports_enabled })"
              >
                {{ chat.rule.auto_reports_enabled ? (isEn ? 'ON' : 'ВКЛ') : (isEn ? 'OFF' : 'ВЫКЛ') }}
              </button>
            </div>
          </div>
        </section>
      </div>
      </div>

      <div
        v-if="showChatPicker"
        style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:9999" class="flex items-end justify-center bg-black/65 p-0 pb-[calc(5rem+env(safe-area-inset-bottom,0px))] backdrop-blur-sm md:pb-6"
        @click="showChatPicker = false"
      >
        <div
          class="flex max-h-[min(70vh,32rem)] w-full max-w-lg min-h-0 flex-col rounded-t-2xl border border-white/15 border-b-0 bg-zinc-950/90 px-3 pb-4 pt-2 text-slate-100 shadow-[0_-12px_40px_rgba(0,0,0,0.75)] ring-1 ring-white/10 backdrop-blur-2xl md:mx-2 md:rounded-2xl md:border-b md:pb-3"
          @click.stop
        >
          <div class="mx-auto mb-2 h-1 w-10 shrink-0 rounded-full bg-white/20 md:hidden" aria-hidden="true" />
          <div class="mb-2 flex shrink-0 items-center justify-between gap-2 border-b border-white/10 pb-2">
            <p class="text-sm font-semibold text-white">{{ isEn ? 'Pick chat' : 'Выбор чата' }}</p>
            <button
              type="button"
              class="rounded-lg px-2 py-1 text-xs text-slate-400 hover:bg-white/10 hover:text-white"
              @click="showChatPicker = false"
            >
              {{ t('common.close') }}
            </button>
          </div>
          <template v-if="(chatsList || []).length > 1">
            <div class="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain py-1 [-webkit-overflow-scrolling:touch]">
              <div v-if="chatsListMine.length">
                <p class="mb-1.5 px-1 text-[10px] font-semibold uppercase tracking-wide text-cyan-200/80">{{ isEn ? 'My chats' : 'Мои чаты' }}</p>
                <div class="space-y-1">
                  <button
                    v-for="c in chatsListMine"
                    :key="`pick-own-${c.id}`"
                    type="button"
                    :class="Number(c.id) === Number(selectedChatId) ? 'guard-green-chip' : 'border border-white/10 bg-white/5 text-slate-100 hover:bg-white/10'"
                    class="w-full rounded-xl px-3 py-2.5 text-left text-xs ring-1 ring-white/5"
                    @click="switchChat(c.id)"
                  >
                    {{ c.title }}
                  </button>
                </div>
              </div>
              <div v-if="chatsListDelegated.length" class="pt-1">
                <p class="mb-1.5 px-1 text-[10px] font-semibold uppercase tracking-wide text-violet-200/90">{{ isEn ? 'Delegated' : 'Делегированные' }}</p>
                <div class="space-y-1">
                  <button
                    v-for="c in chatsListDelegated"
                    :key="`pick-del-${c.id}`"
                    type="button"
                    :class="
                      Number(c.id) === Number(selectedChatId)
                        ? 'border border-violet-400/50 bg-violet-500/20 text-violet-50 ring-1 ring-violet-400/30'
                        : 'border border-violet-400/20 bg-violet-950/30 text-violet-100 hover:bg-violet-900/35'
                    "
                    class="w-full rounded-xl px-3 py-2.5 text-left text-xs"
                    @click="switchChat(c.id)"
                  >
                    {{ c.title }}
                  </button>
                </div>
              </div>
            </div>
          </template>
          <p v-else class="px-1 py-4 text-center text-xs text-slate-400">
            {{ isEn ? 'Only one group connected. Add more in "Connected chats".' : 'Подключена только одна группа. Добавьте ещё в «Подключённые чаты».' }}
          </p>
        </div>
      </div>
    </div>

    <div
      v-else-if="hasInitData"
      class="rounded-2xl bg-white/[0.06] py-6 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-xl"
    >
      <GuardBlueLoadingState />
    </div>
    <div
      v-if="showReportsInfoModal"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:9999" class="flex items-end justify-center bg-black/70 p-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] md:items-center md:pb-6"
      @click.self="showReportsInfoModal = false"
    >
      <div
        class="w-full max-w-xl rounded-2xl border border-sky-400/35 bg-zinc-950/90 p-4 text-slate-100 shadow-2xl ring-1 ring-sky-400/20 backdrop-blur-2xl"
        @click.stop
      >
        <div class="mb-3 flex items-center justify-between gap-2 border-b border-white/10 pb-2">
          <h3 class="text-sm font-semibold text-white">{{ isEn ? '😈 Reports chat' : '😈 Чат отчётов' }}</h3>
          <button
            type="button"
            class="rounded-lg px-2 py-1 text-sm text-slate-400 hover:bg-white/10 hover:text-white"
            @click="showReportsInfoModal = false"
          >
            ✕
          </button>
        </div>
        <div class="space-y-2 text-xs leading-relaxed text-slate-300">
          <template v-if="isEn">
            <p>A dedicated log chat: here I post triggers — who broke a rule, why and what I did (removed, muted, banned).</p>
            <p>The main chat stays for people; service noise doesn't interrupt conversation, and history is easier to dig.</p>
            <p><strong class="text-slate-100">Who needs it:</strong> admins and moderators who need to catch raids quickly and resolve disputes.</p>
            <p>
              <strong class="text-slate-100">Bonus:</strong> reports include action buttons like
              <code class="rounded bg-black/50 px-1 py-0.5 text-[11px] text-sky-200 ring-1 ring-white/10">Unban</code>
              and
              <code class="rounded bg-black/50 px-1 py-0.5 text-[11px] text-sky-200 ring-1 ring-white/10">Unmute</code>
              — less bot navigation.
            </p>
          </template>
          <template v-else>
            <p>Отдельный лог-чат: сюда я скидываю срабатывания — кто накосячил, по какой причине и что сделал (удалил, замьютил, забанил).</p>
            <p>Основной чат остаётся для людей; служебный шум не мешает разговору, а тебе проще копать историю.</p>
            <p><strong class="text-slate-100">Кому зайдёт:</strong> админам и модераторам, которым нужно быстро ловить рейды и разбирать спорные кейсы.</p>
            <p>
              <strong class="text-slate-100">Бонус:</strong> прямо в отчётах есть кнопки вроде
              <code class="rounded bg-black/50 px-1 py-0.5 text-[11px] text-sky-200 ring-1 ring-white/10">Разбан</code>
              и
              <code class="rounded bg-black/50 px-1 py-0.5 text-[11px] text-sky-200 ring-1 ring-white/10">Размут</code>
              — меньше беготни по боту.
            </p>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

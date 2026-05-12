<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import NavIcon from './NavIcon.vue'
import { useApi } from '../composables/useApi'
import { canOpenAdminEntry } from '../utils/adminAccess'
import { useCabinetMode } from '../composables/useCabinetMode'
import { useDashboardSection } from '../composables/useDashboardSection'

const router = useRouter()
const route = useRoute()
const { api, fetchSilent, hasInitData } = useApi()
const { dashboardSection, setDashboardSection } = useDashboardSection()
const { t } = useI18n()
const PREMIUM_CACHE_KEY = 'guard.me.is_premium.v1'
const me = ref(null)
const hasDelegated = ref(false)
const { cabinetMode, setCabinetMode } = useCabinetMode()

const props = defineProps({
  sidebarOpen: Boolean,
  /** Экран «Подписка» на главной: назад вместо меню, без кнопок ADM */
  subscriptionScreen: { type: Boolean, default: false },
  /** Скрыть кнопки ADM (например статус подписки в админке). */
  suppressAdmBadges: { type: Boolean, default: false },
})

const emit = defineEmits(['menu-click', 'subscription-back'])

/** Публичные файлы (logo) через BASE_URL (в проде обычно '/') */
const logoSrc = `${import.meta.env.BASE_URL}logo.png`

const showBack = computed(() => props.subscriptionScreen || (route.path !== '/' && route.name !== 'Dashboard'))
const canSeeAdmin = computed(() => canOpenAdminEntry(me.value))
const isBlueAdmActive = computed(() => route.path.startsWith('/admin') && cabinetMode.value !== 'delegated')
const isPurpleAdmActive = computed(() => {
  if (cabinetMode.value !== 'delegated') return false
  if (route.path === '/chats' && String(route.query?.cabinet || '').toLowerCase() === 'delegated') return true
  if (route.path.startsWith('/admin')) return true
  return false
})

/** Малая аватарка в шапке: скрыта на главном аккаунте, партнёрке, оплате токенов и подписки — чтобы не дублировать герой-блоки */
const hideHeaderLogo = computed(() => {
  const name = String(route.name || '')
  if (name === 'Tokens') return true
  if (name === 'Referral') return true
  if (name !== 'Dashboard') return false
  const sec = String(dashboardSection.value || 'account')
  return ['account', 'partner', 'tokens', 'subscription'].includes(sec)
})

async function loadMeProfile() {
  if (!hasInitData.value) return
  try {
    const meData = await fetchSilent(() => api.me())
    me.value = meData
    hasDelegated.value = !!meData?.has_managed_shared_chat
    try {
      localStorage.setItem(PREMIUM_CACHE_KEY, meData?.is_premium ? '1' : '0')
    } catch {
      //
    }
  } catch {
    //
  }
}

function onVisibleRefreshMe() {
  if (document.visibilityState === 'visible') void loadMeProfile()
}

function onCustomRefreshMe() {
  void loadMeProfile()
}

onMounted(async () => {
  await loadMeProfile()
  document.addEventListener('visibilitychange', onVisibleRefreshMe)
  window.addEventListener('guard:me-refresh', onCustomRefreshMe)
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibleRefreshMe)
  window.removeEventListener('guard:me-refresh', onCustomRefreshMe)
})

function openBlueAdm() {
  setCabinetMode('owner')
  const nav = route.path === '/admin' ? router.replace({ path: '/admin' }) : router.push({ path: '/admin' })
  if (nav && typeof nav.catch === 'function') {
    nav.catch(() => {})
  }
}

function openPurpleAdm() {
  setCabinetMode('delegated')
  const nav = router.push({ path: '/chats', query: { cabinet: 'delegated' } })
  if (nav && typeof nav.catch === 'function') {
    nav.catch(() => {})
  }
}

function goDashboardAccount() {
  setDashboardSection('account')
  const nav = router.push({ path: '/', query: { ...route.query, section: 'account' } })
  if (nav && typeof nav.catch === 'function') nav.catch(() => {})
}

function goBack() {
  if (props.subscriptionScreen) {
    emit('subscription-back')
    return
  }
  // Дать активному вью шанс «снять» внутренний шаг (например, AdminView
  // перехватит чтобы сначала свернуть внутренний экран статистики/защиты).
  try {
    const ev = new CustomEvent('guard:header-back', { cancelable: true })
    const accepted = window.dispatchEvent(ev)
    if (accepted === false || ev.defaultPrevented) return
  } catch { /* */ }
  // Иначе — настоящий шаг по истории; на главную уводим только если истории нет.
  try {
    if (window.history && window.history.length > 1) {
      router.back()
      return
    }
  } catch { /* */ }
  goDashboardAccount()
}
</script>

<template>
  <header
    class="sticky top-0 z-30 flex h-11 items-center justify-between border-b border-white/10 bg-zinc-950/55 px-3 shadow-[0_6px_22px_-6px_rgba(0,0,0,0.5)] backdrop-blur-xl md:h-12 md:px-5"
  >
    <div class="flex items-center gap-2 md:gap-2.5">
      <button
        v-if="showBack"
        type="button"
        class="flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-white/[0.06] text-slate-200 hover:bg-white/[0.12] hover:text-white md:h-9 md:w-9"
        :aria-label="t('common.back')"
        @click="goBack"
      >
        <NavIcon name="back" class="h-4 w-4 md:h-5 md:w-5" />
      </button>
      <button
        v-else
        type="button"
        class="flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-white/[0.06] text-slate-200 hover:bg-white/[0.12] hover:text-white md:h-9 md:w-9"
        :aria-label="t('common.menu')"
        @click="emit('menu-click')"
      >
        <NavIcon name="menu" class="h-4 w-4 md:h-5 md:w-5" />
      </button>
      <a href="#" class="flex min-w-0 items-center gap-2" @click.prevent="goDashboardAccount">
        <img
          v-show="!hideHeaderLogo"
          :src="logoSrc"
          alt="AntiSpam Guard"
          width="40"
          height="40"
          draggable="false"
          class="h-8 w-8 shrink-0 object-contain object-center drop-shadow-[0_0_10px_rgba(143,212,26,0.35)] dark:drop-shadow-[0_0_12px_rgba(143,212,26,0.25)]"
          @dragstart.prevent
        />
        <span class="truncate text-sm font-bold leading-tight tracking-tight md:text-[0.95rem]">
          <span class="text-white">AntiSpam </span><span class="text-lime-400">Guard</span>
        </span>
      </a>
    </div>
    <div class="flex items-center gap-1">
      <button
        v-if="canSeeAdmin && !subscriptionScreen && !suppressAdmBadges"
        type="button"
        class="inline-flex h-[22px] shrink-0 items-center justify-center rounded border border-cyan-400/45 px-1.5 text-[9px] font-bold leading-none tracking-wide text-cyan-600 transition-colors hover:bg-cyan-500/10 dark:text-cyan-300 dark:hover:bg-cyan-500/15"
        :class="isBlueAdmActive ? 'bg-cyan-500/15 shadow-[0_0_12px_rgba(34,211,238,0.45)] ring-1 ring-cyan-300/35' : ''"
        :aria-label="t('common.open_admin')"
        @click="openBlueAdm"
      >
        ADM
      </button>
      <button
        v-if="hasDelegated && !subscriptionScreen && !suppressAdmBadges"
        type="button"
        class="inline-flex h-[22px] shrink-0 items-center justify-center rounded border border-violet-400/45 px-1.5 text-[9px] font-bold leading-none tracking-wide text-violet-300 transition-colors hover:bg-violet-500/10"
        :class="isPurpleAdmActive ? 'bg-violet-500/15 shadow-[0_0_12px_rgba(167,139,250,0.5)] ring-1 ring-violet-300/45' : ''"
        :aria-label="t('common.delegated_chats')"
        @click="openPurpleAdm"
      >
        ADM
      </button>
    </div>
  </header>
</template>

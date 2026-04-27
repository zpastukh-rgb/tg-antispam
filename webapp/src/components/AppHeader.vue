<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import NavIcon from './NavIcon.vue'
import { useApi } from '../composables/useApi'
import { canOpenAdminEntry } from '../utils/adminAccess'
import { useCabinetMode } from '../composables/useCabinetMode'

const router = useRouter()
const route = useRoute()
const { api, fetchSilent, hasInitData } = useApi()
const me = ref(null)
const hasDelegated = ref(false)
const { cabinetMode, setCabinetMode } = useCabinetMode()

const props = defineProps({
  sidebarOpen: Boolean,
  /** Экран «Подписка» на главной: назад вместо меню, без кнопок ADM */
  subscriptionScreen: { type: Boolean, default: false },
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

async function loadMeProfile() {
  if (!hasInitData.value) return
  try {
    const meData = await fetchSilent(() => api.me())
    me.value = meData
    hasDelegated.value = !!meData?.has_managed_shared_chat
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

function goBack() {
  if (props.subscriptionScreen) {
    emit('subscription-back')
    return
  }
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/')
  }
}
</script>

<template>
  <header
    class="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-white/10 bg-zinc-950/55 px-4 shadow-[0_8px_28px_-6px_rgba(0,0,0,0.55)] backdrop-blur-xl md:px-6"
  >
    <div class="flex items-center gap-3">
      <button
        v-if="showBack"
        type="button"
        class="flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-white/[0.06] text-slate-200 hover:bg-white/[0.12] hover:text-white"
        aria-label="Назад"
        @click="goBack"
      >
        <NavIcon name="back" class="w-5 h-5" />
      </button>
      <button
        v-else
        type="button"
        class="flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-white/[0.06] text-slate-200 hover:bg-white/[0.12] hover:text-white"
        aria-label="Меню"
        @click="emit('menu-click')"
      >
        <NavIcon name="menu" class="w-5 h-5" />
      </button>
      <a href="#" class="flex min-w-0 items-center gap-2.5" @click.prevent="router.push('/')">
        <img
          :src="logoSrc"
          alt="AntiSpam Guard"
          width="40"
          height="40"
          draggable="false"
          class="h-9 w-9 shrink-0 object-contain object-center drop-shadow-[0_0_10px_rgba(143,212,26,0.35)] dark:drop-shadow-[0_0_12px_rgba(143,212,26,0.25)]"
          @dragstart.prevent
        />
        <span class="truncate text-base font-bold tracking-tight text-white">AntiSpam Guard</span>
      </a>
    </div>
    <div class="flex items-center gap-1">
      <button
        v-if="canSeeAdmin && !subscriptionScreen"
        type="button"
        class="inline-flex h-6 shrink-0 items-center justify-center rounded-md border border-cyan-400/45 px-2.5 text-[10px] font-bold leading-none tracking-wide text-cyan-600 transition-colors hover:bg-cyan-500/10 dark:text-cyan-300 dark:hover:bg-cyan-500/15"
        :class="isBlueAdmActive ? 'bg-cyan-500/15 shadow-[0_0_14px_rgba(34,211,238,0.55)] ring-1 ring-cyan-300/40' : ''"
        aria-label="Открыть админку"
        @click="openBlueAdm"
      >
        ADM
      </button>
      <button
        v-if="hasDelegated && !subscriptionScreen"
        type="button"
        class="inline-flex h-6 shrink-0 items-center justify-center rounded-md border border-violet-400/45 px-2.5 text-[10px] font-bold leading-none tracking-wide text-violet-300 transition-colors hover:bg-violet-500/10"
        :class="isPurpleAdmActive ? 'bg-violet-500/15 shadow-[0_0_14px_rgba(167,139,250,0.6)] ring-1 ring-violet-300/45' : ''"
        aria-label="Делегированные чаты"
        @click="openPurpleAdm"
      >
        ADM
      </button>
    </div>
  </header>
</template>

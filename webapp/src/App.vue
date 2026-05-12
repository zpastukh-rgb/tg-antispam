<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AppHeader from './components/AppHeader.vue'
import AppSidebar from './components/AppSidebar.vue'
import AppToast from './components/AppToast.vue'
import AppBottomNav from './components/AppBottomNav.vue'
import LegalConsentGate from './components/LegalConsentGate.vue'
import GuardBlueLoadingState from './components/GuardBlueLoadingState.vue'
import { useDashboardSection } from './composables/useDashboardSection'
import { routeTransitionOverlayActive } from './composables/useRouteTransitionLoader.js'
import { useToast } from './composables/useToast'
import { api, getInitData, hasConfiguredApiBase } from './api/client'
import { setLocale, getLocale, normalizeLocale } from './i18n'

const route = useRoute()
const router = useRouter()
const { dashboardSection, setDashboardSection } = useDashboardSection()
const { showToast } = useToast()
const { t } = useI18n()

const sidebarOpen = ref(false)
let presenceTimer = null

/** Единый фон мини-приложения (public), только под контентом. В админке — свой фон в AdminView. */
const globalBgSrc = `${import.meta.env.BASE_URL}app-global-bg.png`

const showApiConfigWarning = computed(() => !hasConfiguredApiBase())

const showAppShellBackground = computed(() => String(route.name || '') !== 'Admin')

function onGuardOpenMenu() {
  openMenu()
}
function onGuardSessionTerminated() {
  showToast(t('app.session_terminated'), 4500)
  if (route.path !== '/connect') {
    router.replace({ path: '/connect', query: { terminated: '1' } }).catch(() => {})
  }
}

async function syncLocaleFromProfile() {
  if (!getInitData()) return
  try {
    const me = await api.me()
    if (me?.language) {
      const norm = normalizeLocale(me.language)
      if (getLocale() !== norm) setLocale(norm)
    }
  } catch {
    //
  }
}

onMounted(() => {
  window.addEventListener('guard-open-menu', onGuardOpenMenu)
  window.addEventListener('guard:session-terminated', onGuardSessionTerminated)
  if (getInitData()) {
    api.presencePing().catch(() => {})
    presenceTimer = setInterval(() => {
      api.presencePing().catch(() => {})
    }, 30000)
    void nextTick(() => {
      void syncLocaleFromProfile()
    })
  }
})
onBeforeUnmount(() => {
  window.removeEventListener('guard-open-menu', onGuardOpenMenu)
  window.removeEventListener('guard:session-terminated', onGuardSessionTerminated)
  if (presenceTimer) {
    clearInterval(presenceTimer)
    presenceTimer = null
  }
})

/** Меньше отступ сверху под шапкой на главной и «Защите» (фон на всю ширину) */
const mainContentCompactTop = computed(() =>
  ['Dashboard', 'Protection', 'Settings'].includes(String(route.name || '')),
)

function openMenu() {
  sidebarOpen.value = true
}

function closeSidebar() {
  sidebarOpen.value = false
}

const subscriptionScreenActive = computed(
  () => route.name === 'Dashboard' && dashboardSection.value === 'subscription',
)
/** Скрыть cyan/violet ADM в шапке на экране статуса подписки (главная или вкладка в /admin). */
const suppressAdmBadges = computed(
  () =>
    subscriptionScreenActive.value ||
    (route.path === '/admin' && String(route.query.admin_tab || '') === 'subscription'),
)

function onSubscriptionBackFromHeader() {
  setDashboardSection('account')
  const q = { ...route.query, section: 'account' }
  void router.replace({ path: '/', query: q }).catch(() => {})
}
</script>

<template>
  <div class="relative min-h-[100dvh] min-h-screen">
    <div
      v-if="showAppShellBackground"
      aria-hidden="true"
      class="pointer-events-none fixed inset-0 z-0 bg-zinc-950 bg-cover bg-center bg-no-repeat"
      :style="{ backgroundImage: `url(${globalBgSrc})` }"
    />
    <div
      v-if="showAppShellBackground"
      aria-hidden="true"
      class="pointer-events-none fixed inset-0 z-[1] bg-gradient-to-b from-black/30 via-black/18 to-black/42"
    />
    <div class="relative z-10 flex min-h-[100dvh] min-h-screen flex-col bg-transparent">
      <div
        v-if="showApiConfigWarning"
        class="border-b border-rose-500/40 bg-rose-950/90 px-3 py-2 text-center text-[11px] font-semibold leading-snug text-rose-100"
        role="alert"
      >
        {{ t('app.api_base_missing_runtime') }}
      </div>
      <AppToast />
      <AppHeader
        :sidebar-open="sidebarOpen"
        :subscription-screen="subscriptionScreenActive"
        :suppress-adm-badges="suppressAdmBadges"
        @menu-click="openMenu"
        @subscription-back="onSubscriptionBackFromHeader"
      />
      <AppSidebar :open="sidebarOpen" @close="closeSidebar" />
      <main
        class="min-h-0 flex-1 touch-manipulation scroll-pb-[calc(7.35rem+env(safe-area-inset-bottom,0px))] bg-transparent pb-[calc(7.35rem+env(safe-area-inset-bottom,0px))] md:pb-40 md:pl-64"
      >
        <div
          :class="
            mainContentCompactTop
              ? 'px-4 pb-4 pt-0 md:px-6 md:pb-6 md:pt-1'
              : 'p-4 md:p-6'
          "
        >
          <router-view />
        </div>
        <!-- Контейнер поверх main по z-index; pointer-events-none чтобы пустой слой не «съедал» тапы в Telegram WKWebView -->
        <div id="guard-modal-root" class="pointer-events-none relative z-[850]"></div>
      </main>

      <AppBottomNav />
    </div>
    <!-- Вне z-10 колонки: иначе в Telegram WebView оверлей может оказаться под контентом -->
    <LegalConsentGate />

    <Teleport to="body">
      <Transition name="guard-route-fade">
        <div
          v-if="routeTransitionOverlayActive"
          class="pointer-events-none fixed left-0 right-0 z-[1200] flex items-center justify-center bg-zinc-950/70 px-4 backdrop-blur-[3px] supports-[backdrop-filter]:bg-zinc-950/55 top-11 md:top-12"
          style="bottom: calc(7.35rem + env(safe-area-inset-bottom, 0px))"
          aria-hidden="true"
        >
          <div
            class="pointer-events-auto w-full max-w-sm rounded-2xl bg-white/[0.07] px-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.1),0_12px_40px_-20px_rgba(0,0,0,0.6)] backdrop-blur-xl"
          >
            <GuardBlueLoadingState compact />
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style>
.guard-route-fade-enter-active,
.guard-route-fade-leave-active {
  transition: opacity 0.2s ease;
}
.guard-route-fade-enter-from,
.guard-route-fade-leave-to {
  opacity: 0;
}
</style>

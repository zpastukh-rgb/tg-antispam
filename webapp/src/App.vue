<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppHeader from './components/AppHeader.vue'
import AppSidebar from './components/AppSidebar.vue'
import AppToast from './components/AppToast.vue'
import AppBottomNav from './components/AppBottomNav.vue'
import { useDashboardSection } from './composables/useDashboardSection'
import { api, getInitData } from './api/client'

const route = useRoute()
const router = useRouter()
const { dashboardSection, billingFromGroupStats, setDashboardSection } = useDashboardSection()

const sidebarOpen = ref(false)
let presenceTimer = null

/** Единый фон мини-приложения (public), только под контентом */
const globalBgSrc = `${import.meta.env.BASE_URL}app-global-bg.png`

function onGuardOpenMenu() {
  openMenu()
}
onMounted(() => {
  window.addEventListener('guard-open-menu', onGuardOpenMenu)
  if (getInitData()) {
    api.presencePing().catch(() => {})
    presenceTimer = setInterval(() => {
      api.presencePing().catch(() => {})
    }, 30000)
  }
})
onBeforeUnmount(() => {
  window.removeEventListener('guard-open-menu', onGuardOpenMenu)
  if (presenceTimer) {
    clearInterval(presenceTimer)
    presenceTimer = null
  }
})

/** Плашка «Получить Premium» на главной вкладке «Аккаунт» (как раньше — всегда, без скрытия по /me). */
const showFixedPremiumCta = computed(
  () =>
    route.name === 'Dashboard'
    && dashboardSection.value === 'account',
)

/** Меньше отступ сверху под шапкой на главной и «Защите» (фон на всю ширину) */
const mainContentCompactTop = computed(() =>
  ['Dashboard', 'Protection'].includes(String(route.name || '')),
)

function onFixedPremiumClick() {
  billingFromGroupStats.value = false
  setDashboardSection('billing')
  // Не тянем старый ?scroll= из прошлого визита — иначе тот же «Получить Premium» ведёт на разный кусок лендинга
  const q = { ...route.query, section: 'billing' }
  delete q.scroll
  void router.push({ path: '/', query: q })
}

function openMenu() {
  sidebarOpen.value = true
}

function closeSidebar() {
  sidebarOpen.value = false
}

const subscriptionScreenActive = computed(
  () => route.name === 'Dashboard' && dashboardSection.value === 'subscription',
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
      aria-hidden="true"
      class="pointer-events-none fixed inset-0 z-0 bg-zinc-950 bg-cover bg-center bg-no-repeat"
      :style="{ backgroundImage: `url(${globalBgSrc})` }"
    />
    <div
      aria-hidden="true"
      class="pointer-events-none fixed inset-0 z-[1] bg-gradient-to-b from-black/30 via-black/18 to-black/42"
    />
    <div class="relative z-10 flex min-h-[100dvh] min-h-screen flex-col bg-transparent">
      <AppToast />
      <AppHeader
        :sidebar-open="sidebarOpen"
        :subscription-screen="subscriptionScreenActive"
        @menu-click="openMenu"
        @subscription-back="onSubscriptionBackFromHeader"
      />
      <AppSidebar :open="sidebarOpen" @close="closeSidebar" />
      <main
        class="min-h-0 flex-1 scroll-pb-[calc(7.35rem+env(safe-area-inset-bottom,0px))] bg-transparent md:pl-64"
        :class="
          showFixedPremiumCta
            ? 'pb-[calc(10.25rem+env(safe-area-inset-bottom,0px))] md:pb-44'
            : 'pb-[calc(7.35rem+env(safe-area-inset-bottom,0px))] md:pb-40'
        "
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
      </main>

      <div
        v-if="showFixedPremiumCta"
        class="fixed inset-x-0 z-[45] bg-transparent px-10 py-1.5 sm:px-14 md:left-64 md:px-16"
        style="bottom: calc(5.85rem + env(safe-area-inset-bottom, 0px))"
      >
        <button
          type="button"
          class="premium-cta-bounce relative mx-auto flex w-full max-w-[min(100%,17.5rem)] items-center justify-center gap-1.5 overflow-visible rounded-2xl border border-white/35 bg-amber-400/[0.07] px-2 py-1.5 text-[13px] text-white shadow-[0_0_14px_-2px_rgba(255,255,255,0.18)] backdrop-blur-md transition hover:bg-amber-400/[0.11] active:scale-[0.99] sm:max-w-[min(100%,18.5rem)]"
          @click="onFixedPremiumClick"
        >
          <span
            class="pointer-events-none shrink-0 select-none text-[1.35em] leading-none drop-shadow-[0_0_6px_rgba(255,255,255,0.25)]"
            aria-hidden="true"
          >👑</span>
          <span class="relative z-[1] text-center leading-tight drop-shadow-[0_1px_2px_rgba(0,0,0,0.55)]">
            <span class="font-medium">Получить</span>
            <span class="font-bold"> Premium</span>
          </span>
          <span
            class="pointer-events-none absolute inset-0 rounded-2xl bg-gradient-to-b from-white/6 via-transparent to-white/5"
            aria-hidden="true"
          />
        </button>
      </div>

      <AppBottomNav />
    </div>
  </div>
</template>

<style scoped>
@keyframes premium-cta-bob {
  0%,
  72%,
  100% {
    transform: translateY(0);
  }
  6% {
    transform: translateY(-4px);
  }
  12% {
    transform: translateY(0);
  }
  18% {
    transform: translateY(-3px);
  }
  24% {
    transform: translateY(0);
  }
}
.premium-cta-bounce {
  animation: premium-cta-bob 4s ease-in-out infinite;
}
</style>

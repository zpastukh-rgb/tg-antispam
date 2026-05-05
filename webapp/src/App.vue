<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppHeader from './components/AppHeader.vue'
import AppSidebar from './components/AppSidebar.vue'
import AppToast from './components/AppToast.vue'
import AppBottomNav from './components/AppBottomNav.vue'
import LegalConsentGate from './components/LegalConsentGate.vue'
import { useDashboardSection } from './composables/useDashboardSection'
import { api, getInitData } from './api/client'

const route = useRoute()
const router = useRouter()
const { dashboardSection, setDashboardSection } = useDashboardSection()

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

/** Меньше отступ сверху под шапкой на главной и «Защите» (фон на всю ширину) */
const mainContentCompactTop = computed(() =>
  ['Dashboard', 'Protection'].includes(String(route.name || '')),
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
        class="min-h-0 flex-1 scroll-pb-[calc(7.35rem+env(safe-area-inset-bottom,0px))] bg-transparent pb-[calc(7.35rem+env(safe-area-inset-bottom,0px))] md:pb-40 md:pl-64"
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

      <AppBottomNav />
    </div>
    <!-- Вне z-10 колонки: иначе в Telegram WebView оверлей может оказаться под контентом -->
    <LegalConsentGate />
  </div>
</template>

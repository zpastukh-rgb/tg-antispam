<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import NavIcon from './NavIcon.vue'
import GuardTeleport from './GuardTeleport.vue'
import { useDashboardSection } from '../composables/useDashboardSection'
import { useApi } from '../composables/useApi'
import { useCabinetMode } from '../composables/useCabinetMode'
import { hasFullAdminRights } from '../utils/adminAccess'

const route = useRoute()
const router = useRouter()
const { dashboardSection, setDashboardSection } = useDashboardSection()
const { api, hasInitData } = useApi()
const { setCabinetMode } = useCabinetMode()
const { t } = useI18n()
const PREMIUM_CACHE_KEY = 'guard.me.is_premium.v1'
const DELEGATED_BC_CACHE_KEY = 'guard.me.has_delegated_broadcast.v1'
const BROADCAST_NAV_ALLOWED_KEY = 'guard.me.broadcast_nav_allowed.v1'
const spikeActiveOwner = ref(false)
const spikeActiveShared = ref(false)
let spikeTimer = null
const navGridRef = ref(null)
const itemButtonRefs = ref([])
const navActiveIndicatorStyle = ref({
  left: '0px',
  width: '0px',
  opacity: 0,
  transitionDuration: '320ms',
})
const navActiveIndicatorAnimating = ref(false)
let navIndicatorAnimTimer = null
let navResizeHandler = null

const baseItems = computed(() => [
  { key: 'account', label: t('nav.account'), icon: 'account', to: '/' },
  { key: 'partner', label: t('nav.partner'), icon: 'partner', section: 'partner', to: '/' },
  { key: 'protection', label: t('nav.protection'), icon: 'shield', to: '/protection' },
  { key: 'support', label: t('nav.support'), icon: 'support', to: 'support' },
])
const isPremiumUser = ref(false)
const hasDelegatedBroadcast = ref(false)
const broadcastGateModalOpen = ref(false)
const broadcastNavGateReady = ref(false)
function computeBroadcastNavAllowed(me) {
  if (!me) return false
  if (hasFullAdminRights(me)) return true
  if (!!me.is_premium) return true
  const tf = String(me.tariff || '').toLowerCase()
  if (['premium', 'pro', 'business'].includes(tf)) return true
  if (!!me.has_delegated_broadcast) return true
  if (!!me.has_managed_shared_chat) return true
  return false
}
function _readBoolCache(key) {
  try {
    const raw = localStorage.getItem(key)
    if (raw === '1') return true
    if (raw === '0') return false
  } catch {
    //
  }
  return null
}
function _writeBoolCache(key, v) {
  try {
    localStorage.setItem(key, v ? '1' : '0')
  } catch {
    //
  }
}
function readPremiumCache() { return _readBoolCache(PREMIUM_CACHE_KEY) }
function writePremiumCache(v) { _writeBoolCache(PREMIUM_CACHE_KEY, v) }
function readDelegatedBcCache() { return _readBoolCache(DELEGATED_BC_CACHE_KEY) }
function writeDelegatedBcCache(v) { _writeBoolCache(DELEGATED_BC_CACHE_KEY, v) }
function readBroadcastNavCache() {
  return _readBoolCache(BROADCAST_NAV_ALLOWED_KEY)
}
function writeBroadcastNavCache(v) {
  _writeBoolCache(BROADCAST_NAV_ALLOWED_KEY, v)
}
const cachedPremium = readPremiumCache()
if (cachedPremium !== null) isPremiumUser.value = !!cachedPremium
const cachedDelegatedBc = readDelegatedBcCache()
if (cachedDelegatedBc !== null) hasDelegatedBroadcast.value = !!cachedDelegatedBc
const bNavCached = readBroadcastNavCache()
const broadcastNavAllowed = ref(
  bNavCached !== null ? bNavCached : readPremiumCache() === true || readDelegatedBcCache() === true,
)

/** «Рассылка» в таббаре видна всем авторизованным (маркетинг); реальный доступ в кабинете — Premium / делегирование. */
const canSeeBroadcasts = computed(() => hasInitData.value)

const items = computed(() => {
  const all = baseItems.value
  const base = [all[0], all[1]]
  if (canSeeBroadcasts.value) {
    base.push({ key: 'broadcasts', label: t('nav.broadcast'), icon: 'telegram', to: '/admin', adminTab: 'broadcasts' })
  }
  base.push(all[2], all[3])
  return base
})

function isActive(item) {
  if (item.adminTab) {
    return route.path === '/admin' && String(route.query?.tab || '').toLowerCase() === String(item.adminTab || '').toLowerCase()
  }
  if (item.section) return route.path === '/' && dashboardSection.value === item.section
  if (item.to === '/') {
    return (
      (route.path === '/' && (dashboardSection.value === 'account' || dashboardSection.value === 'subscription'))
      || route.path === '/settings'
    )
  }
  return route.path.startsWith(item.to)
}

function activeItemIndex() {
  const idx = items.value.findIndex((item) => isActive(item))
  return idx >= 0 ? idx : 0
}

function setItemButtonRef(el, index) {
  if (!el) return
  itemButtonRefs.value[index] = el
}

function updateActiveIndicator(withSqueeze = false) {
  nextTick(() => {
    const grid = navGridRef.value
    const idx = activeItemIndex()
    const btn = itemButtonRefs.value[idx]
    if (!grid || !btn) return
    const g = grid.getBoundingClientRect()
    const b = btn.getBoundingClientRect()
    navActiveIndicatorStyle.value = {
      left: `${Math.max(0, b.left - g.left)}px`,
      width: `${Math.max(0, b.width)}px`,
      opacity: 1,
      transitionDuration: '360ms',
    }
    if (!withSqueeze) return
    navActiveIndicatorAnimating.value = false
    requestAnimationFrame(() => {
      navActiveIndicatorAnimating.value = true
      if (navIndicatorAnimTimer) clearTimeout(navIndicatorAnimTimer)
      navIndicatorAnimTimer = setTimeout(() => {
        navActiveIndicatorAnimating.value = false
      }, 520)
    })
  })
}

function goBroadcastGateSubscription() {
  broadcastGateModalOpen.value = false
  setDashboardSection('subscription')
  const nav = router.push({ path: '/', query: { ...route.query, section: 'subscription' } })
  if (nav && typeof nav.catch === 'function') nav.catch(() => {})
}

async function onTap(item) {
  if (item.to === 'support') {
    const url = 'https://t.me/Help_guard'
    const tg = window.Telegram?.WebApp
    if (typeof tg?.openTelegramLink === 'function') {
      tg.openTelegramLink(url)
      return
    }
    if (typeof tg?.openLink === 'function') {
      tg.openLink(url)
      return
    }
    window.open(url, '_blank', 'noopener,noreferrer')
    return
  }
  if (item.to === '/') {
    const section = item.section || 'account'
    setDashboardSection(section)
    // Нельзя сбрасывать query: в Telegram WebView в нём бывают tgWebApp* / initData.
    const nav = router.push({ path: '/', query: { ...route.query, section } })
    if (nav && typeof nav.catch === 'function') nav.catch(() => {})
    return
  }
  if (item.adminTab) {
    if (item.adminTab === 'broadcasts') {
      if (!broadcastNavGateReady.value) {
        await loadPremiumFlag()
      }
      if (!broadcastNavAllowed.value) {
        broadcastGateModalOpen.value = true
        return
      }
    }
    setCabinetMode('owner')
    const nav = router.push({ path: item.to, query: { ...route.query, tab: item.adminTab } })
    if (nav && typeof nav.catch === 'function') nav.catch(() => {})
    return
  }
  const nav = router.push({ path: item.to, query: { ...route.query } })
  if (nav && typeof nav.catch === 'function') nav.catch(() => {})
}

function showSpikeFor(item) {
  if (item.key === 'protection') return !!(spikeActiveOwner.value || spikeActiveShared.value)
  if (item.key === 'partner') return false
  return false
}

async function loadSpikeAlerts() {
  if (!hasInitData.value) return
  try {
    const r = await api.spikeAlerts()
    spikeActiveOwner.value = !!r?.active_owner
    spikeActiveShared.value = !!r?.active_shared
  } catch {
    //
  }
}
async function loadPremiumFlag() {
  if (!hasInitData.value) {
    broadcastNavGateReady.value = true
    return
  }
  try {
    const me = await api.me()
    isPremiumUser.value = !!me?.is_premium
    writePremiumCache(!!me?.is_premium)
    hasDelegatedBroadcast.value = !!me?.has_delegated_broadcast
    writeDelegatedBcCache(!!me?.has_delegated_broadcast)
    const allowed = computeBroadcastNavAllowed(me)
    broadcastNavAllowed.value = allowed
    writeBroadcastNavCache(allowed)
  } catch {
    //
  } finally {
    broadcastNavGateReady.value = true
  }
}

onMounted(async () => {
  void loadSpikeAlerts()
  void loadPremiumFlag()
  spikeTimer = setInterval(loadSpikeAlerts, 30000)
  updateActiveIndicator(false)
  navResizeHandler = () => updateActiveIndicator(false)
  if (typeof window !== 'undefined') {
    window.addEventListener('resize', navResizeHandler, { passive: true })
  }
})

onUnmounted(() => {
  if (spikeTimer) {
    clearInterval(spikeTimer)
    spikeTimer = null
  }
  if (navResizeHandler && typeof window !== 'undefined') {
    window.removeEventListener('resize', navResizeHandler)
  }
  navResizeHandler = null
  if (navIndicatorAnimTimer) clearTimeout(navIndicatorAnimTimer)
  navIndicatorAnimTimer = null
})

watch(
  () => [route.path, dashboardSection.value, items.value.length],
  () => updateActiveIndicator(true),
)
</script>

<template>
  <nav
    class="fixed bottom-3 left-6 right-6 z-40 mx-auto w-auto rounded-[1.65rem] border-0 bg-[linear-gradient(180deg,rgba(18,21,28,0.42),rgba(12,14,18,0.42))] pb-[calc(0.18rem+env(safe-area-inset-bottom,0px))] pt-0 shadow-[0_14px_28px_-14px_rgba(0,0,0,0.62)] backdrop-blur-[14px]"
    :class="items.length > 4 ? 'max-w-[22.4rem]' : 'max-w-[17.8rem]'"
    style="font-family: 'Exo 2', 'Montserrat', sans-serif;"
  >
    <div
      ref="navGridRef"
      class="relative mx-auto grid w-full gap-0 px-0 pt-[0.18rem] pb-[0.06rem]"
      :class="items.length > 4 ? 'max-w-[21.2rem] grid-cols-5' : 'max-w-[16.6rem] grid-cols-4'"
    >
      <!-- Важно: только декорация. Иначе z-[3] + pointerdown.prevent перехватывает тапы над табами в Telegram WebView -->
      <span
        class="nav-active-indicator pointer-events-none absolute bottom-0 top-0 z-[3] rounded-full transition-[left,width,opacity,background-color,box-shadow,backdrop-filter,transform] duration-200 ease-out"
        :class="navActiveIndicatorAnimating ? 'nav-active-indicator-squeeze' : ''"
        :style="navActiveIndicatorStyle"
        aria-hidden="true"
      >
        <span
          class="nav-active-indicator-edge"
          :class="navActiveIndicatorAnimating ? 'nav-active-indicator-edge-run' : ''"
          aria-hidden="true"
        />
      </span>
      <button
        v-for="(item, idx) in items"
        :key="item.key"
        :ref="(el) => setItemButtonRef(el, idx)"
        type="button"
        class="group relative z-[4] flex flex-col items-center justify-center gap-0 rounded-full px-0.5 py-[0.18rem] text-[10.5px] font-semibold tracking-[0.01em] transition-colors duration-200"
        :class="
          isActive(item)
            ? 'text-[#58a9ff]'
            : 'text-zinc-200/95 hover:bg-white/[0.04]'
        "
        @click="onTap(item)"
      >
        <span
          v-if="showSpikeFor(item)"
          class="absolute right-1.5 top-1.5 inline-flex items-center justify-center"
          :title="t('app.chat_under_threat')"
          :aria-label="t('app.chat_under_threat')"
        >
          <span class="absolute inline-flex h-4 w-4 animate-ping rounded-full bg-yellow-400/55" />
          <span class="relative text-[12px] leading-none text-yellow-300">⚠</span>
        </span>
        <span class="inline-flex h-8 w-8 shrink-0 items-center justify-center p-0 transition" :class="isActive(item) ? 'text-[#7cc0ff]' : 'text-zinc-200/95'">
          <NavIcon
            :name="item.icon"
            :class="item.key === 'partner' ? 'h-[1.95rem] w-[1.95rem] text-current' : item.key === 'support' ? 'h-[1.72rem] w-[1.72rem] text-current' : item.key === 'broadcasts' ? 'h-[1.64rem] w-[1.64rem] text-current' : 'h-[1.58rem] w-[1.58rem] text-current'"
          />
        </span>
        <span class="-mt-[1px] max-w-full truncate leading-none" :class="isActive(item) ? 'text-[#7fc3ff]' : 'text-zinc-100/92'">{{ item.label }}</span>
      </button>
    </div>
  </nav>

  <GuardTeleport>
    <div
      v-if="broadcastGateModalOpen"
      class="fixed inset-0 z-[95000] flex items-end justify-center bg-[#0b0d14] p-4 pb-[max(1rem,calc(5.5rem+env(safe-area-inset-bottom,0px)))] pt-[max(0.75rem,env(safe-area-inset-top,0px))] md:items-center md:pb-8"
      role="presentation"
      @click.self="broadcastGateModalOpen = false"
    >
      <div
        class="w-full max-w-sm rounded-2xl border border-white/10 bg-[#141820] p-5 text-center shadow-[0_24px_64px_-24px_rgba(0,0,0,0.92)] ring-1 ring-white/[0.04]"
        role="dialog"
        aria-modal="true"
        :aria-label="t('nav.broadcast_gate_title')"
        @click.stop
      >
        <p class="text-[10px] font-extrabold uppercase tracking-[0.2em] text-amber-300/90">Premium</p>
        <p class="mt-2 text-[18px] font-extrabold text-white">{{ t('nav.broadcast_gate_title') }}</p>
        <p class="mt-2 text-[13px] leading-snug text-zinc-400">{{ t('nav.broadcast_gate_sub') }}</p>
        <button
          type="button"
          class="mt-5 w-full rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 py-3 text-[15px] font-extrabold text-white shadow-[0_14px_36px_-14px_rgba(99,102,241,0.75)] transition hover:brightness-110 active:scale-[0.99]"
          @click="goBroadcastGateSubscription"
        >
          {{ t('nav.broadcast_gate_cta') }}
        </button>
        <button
          type="button"
          class="mt-3 w-full rounded-lg py-2.5 text-[13px] font-semibold text-zinc-500 transition hover:text-zinc-300"
          @click="broadcastGateModalOpen = false"
        >
          {{ t('premium_lock.cta_dismiss') }}
        </button>
      </div>
    </div>
  </GuardTeleport>
</template>

<style scoped>
.nav-active-indicator-squeeze {
  animation: navIndicatorSqueeze 520ms cubic-bezier(0.2, 0.74, 0.2, 1);
}

@keyframes navIndicatorSqueeze {
  0% { transform: scaleY(1); }
  35% { transform: scaleY(1.12); }
  72% { transform: scaleY(0.86); }
  100% { transform: scaleY(1); }
}

.nav-active-indicator {
  top: 4px;
  bottom: 0px;
  transition-duration: 360ms;
  transition-timing-function: cubic-bezier(0.2, 0.78, 0.2, 1);
  background: transparent;
  box-shadow: none;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  overflow: hidden;
}

.nav-active-indicator-edge {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  pointer-events: none;
  opacity: 0.42;
  background:
    linear-gradient(95deg, transparent 0%, rgba(130, 190, 255, 0.08) 10%, rgba(255, 140, 210, 0.12) 16%, rgba(120, 250, 255, 0.12) 20%, rgba(130, 190, 255, 0.08) 26%, transparent 36%) 0 0 / 260% 100% no-repeat;
  box-shadow:
    inset 0 0 0 1px rgba(170, 210, 255, 0.22),
    0 0 0 1px rgba(120, 170, 255, 0.12);
  backdrop-filter: blur(10px) saturate(1.25) contrast(1.04);
  -webkit-backdrop-filter: blur(10px) saturate(1.25) contrast(1.04);
  mask: radial-gradient(closest-side, transparent calc(100% - 2.4px), #000 calc(100% - 1.45px));
  -webkit-mask: radial-gradient(closest-side, transparent calc(100% - 2.4px), #000 calc(100% - 1.45px));
  mix-blend-mode: plus-lighter;
  transition: opacity 180ms ease;
}

.nav-active-indicator-edge-run {
  animation: navEdgeFlow 520ms cubic-bezier(0.2, 0.7, 0.2, 1);
  opacity: 0.92;
}

@keyframes navEdgeFlow {
  0% {
    background-position: 0% 0, 0 0, 0 0;
    opacity: 0.52;
  }
  45% {
    background-position: 58% 0, 0 0, 0 0;
    opacity: 0.9;
  }
  100% {
    background-position: 100% 0, 0 0, 0 0;
    opacity: 0.68;
  }
}
</style>

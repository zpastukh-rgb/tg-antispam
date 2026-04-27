<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import NavIcon from './NavIcon.vue'
import { useDashboardSection } from '../composables/useDashboardSection'
import { useApi } from '../composables/useApi'

const route = useRoute()
const router = useRouter()
const { dashboardSection, setDashboardSection } = useDashboardSection()
const { api, hasInitData } = useApi()
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
const navActiveIndicatorDragging = ref(false)
const navActiveIndicatorSettling = ref(false)
let navIndicatorAnimTimer = null
let navIndicatorSettleTimer = null
let navResizeHandler = null
const navDragState = ref({
  active: false,
  pointerId: null,
  startX: 0,
  startLeft: 0,
})

const items = [
  { key: 'account', label: 'Аккаунт', icon: 'account', to: '/' },
  { key: 'partner', label: 'Партнер', icon: 'partner', section: 'partner', to: '/' },
  { key: 'protection', label: 'Защита', icon: 'shield', to: '/protection' },
  { key: 'support', label: 'Поддержка', icon: 'support', to: 'support' },
]

function isActive(item) {
  if (item.section) return route.path === '/' && dashboardSection.value === item.section
  if (item.to === '/') {
    return (
      route.path === '/'
      && (dashboardSection.value === 'account' || dashboardSection.value === 'subscription')
    )
  }
  return route.path.startsWith(item.to)
}

function activeItemIndex() {
  const idx = items.findIndex((item) => isActive(item))
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
      transitionDuration: navActiveIndicatorDragging.value ? '0ms' : '460ms',
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

function startIndicatorDrag(ev) {
  if (!ev) return
  const grid = navGridRef.value
  if (!grid) return
  const curLeft = Number.parseFloat(String(navActiveIndicatorStyle.value.left || '0').replace('px', '')) || 0
  navDragState.value = {
    active: true,
    pointerId: ev.pointerId ?? null,
    startX: Number(ev.clientX || 0),
    startLeft: curLeft,
  }
  navActiveIndicatorDragging.value = true
  navActiveIndicatorAnimating.value = false
  navActiveIndicatorSettling.value = false
  if (navIndicatorSettleTimer) {
    clearTimeout(navIndicatorSettleTimer)
    navIndicatorSettleTimer = null
  }
  try {
    ev.currentTarget?.setPointerCapture?.(ev.pointerId)
  } catch {
    //
  }
}

function onIndicatorDragMove(ev) {
  if (!navDragState.value.active) return
  if (navDragState.value.pointerId != null && ev.pointerId !== navDragState.value.pointerId) return
  const grid = navGridRef.value
  if (!grid) return
  const dx = Number(ev.clientX || 0) - Number(navDragState.value.startX || 0)
  const next = Number(navDragState.value.startLeft || 0) + dx
  const width = Number.parseFloat(String(navActiveIndicatorStyle.value.width || '0').replace('px', '')) || 0
  const max = Math.max(0, grid.clientWidth - width)
  const clamped = Math.max(0, Math.min(max, next))
  navActiveIndicatorStyle.value = {
    ...navActiveIndicatorStyle.value,
    left: `${clamped}px`,
    opacity: 1,
    transitionDuration: '0ms',
  }
}

function endIndicatorDrag() {
  if (!navDragState.value.active) return
  navDragState.value.active = false
  navActiveIndicatorDragging.value = false
  navActiveIndicatorSettling.value = true
  const grid = navGridRef.value
  const left = Number.parseFloat(String(navActiveIndicatorStyle.value.left || '0').replace('px', '')) || 0
  const width = Number.parseFloat(String(navActiveIndicatorStyle.value.width || '0').replace('px', '')) || 0
  const center = left + width / 2
  if (!grid || !itemButtonRefs.value.length) {
    updateActiveIndicator(true)
    return
  }
  const g = grid.getBoundingClientRect()
  let bestIdx = 0
  let bestDist = Number.POSITIVE_INFINITY
  itemButtonRefs.value.forEach((btn, idx) => {
    if (!btn) return
    const r = btn.getBoundingClientRect()
    const c = (r.left - g.left) + r.width / 2
    const d = Math.abs(c - center)
    if (d < bestDist) {
      bestDist = d
      bestIdx = idx
    }
  })
  const target = items[bestIdx]
  if (target) onTap(target)
  updateActiveIndicator(true)
  if (navIndicatorSettleTimer) clearTimeout(navIndicatorSettleTimer)
  navIndicatorSettleTimer = setTimeout(() => {
    navActiveIndicatorSettling.value = false
  }, 260)
}

function onTap(item) {
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
    setDashboardSection(item.section || 'account')
    router.push('/')
    return
  }
  router.push(item.to)
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

onMounted(async () => {
  await loadSpikeAlerts()
  spikeTimer = setInterval(loadSpikeAlerts, 30000)
  updateActiveIndicator(false)
  navResizeHandler = () => updateActiveIndicator(false)
  if (typeof window !== 'undefined') {
    window.addEventListener('resize', navResizeHandler, { passive: true })
    window.addEventListener('pointermove', onIndicatorDragMove, { passive: true })
    window.addEventListener('pointerup', endIndicatorDrag, { passive: true })
    window.addEventListener('pointercancel', endIndicatorDrag, { passive: true })
  }
})

onUnmounted(() => {
  if (spikeTimer) {
    clearInterval(spikeTimer)
    spikeTimer = null
  }
  if (navResizeHandler && typeof window !== 'undefined') {
    window.removeEventListener('resize', navResizeHandler)
    window.removeEventListener('pointermove', onIndicatorDragMove)
    window.removeEventListener('pointerup', endIndicatorDrag)
    window.removeEventListener('pointercancel', endIndicatorDrag)
  }
  navResizeHandler = null
  if (navIndicatorAnimTimer) clearTimeout(navIndicatorAnimTimer)
  navIndicatorAnimTimer = null
  if (navIndicatorSettleTimer) clearTimeout(navIndicatorSettleTimer)
  navIndicatorSettleTimer = null
})

watch(
  () => [route.path, dashboardSection.value],
  () => updateActiveIndicator(true),
)
</script>

<template>
  <nav
    class="fixed bottom-3 left-4 right-4 z-40 mx-auto w-auto max-w-[20.3rem] rounded-[1.8rem] border border-white/15 bg-[linear-gradient(180deg,rgba(40,44,54,0.55),rgba(19,23,32,0.62))] pb-[calc(0.2rem+env(safe-area-inset-bottom,0px))] pt-0 shadow-[0_16px_34px_-12px_rgba(0,0,0,0.78),inset_0_1px_0_rgba(255,255,255,0.12),inset_0_-10px_18px_rgba(0,0,0,0.24)] backdrop-blur-[18px] [contain:layout_paint] [transform:translateZ(0)]"
    style="font-family: 'Exo 2', 'Montserrat', sans-serif;"
  >
    <div ref="navGridRef" class="relative mx-auto grid w-full max-w-[19rem] grid-cols-4 gap-0 px-0.5 pt-0.5 pb-0">
      <span
        class="nav-active-indicator absolute bottom-0 top-0 z-[3] rounded-full transition-[left,width,opacity,background-color,box-shadow,backdrop-filter,transform] duration-200 ease-out"
        :class="[
          navActiveIndicatorAnimating ? 'nav-active-indicator-squeeze' : '',
          navActiveIndicatorDragging ? 'nav-active-indicator-dragging' : '',
          navActiveIndicatorSettling ? 'nav-active-indicator-settle' : '',
        ]"
        :style="navActiveIndicatorStyle"
        @pointerdown.prevent.stop="startIndicatorDrag"
        aria-hidden="true"
      >
        <span
          class="nav-active-indicator-edge"
          :class="[
            navActiveIndicatorAnimating ? 'nav-active-indicator-edge-run' : '',
            navActiveIndicatorDragging ? 'nav-active-indicator-edge-drag' : '',
            navActiveIndicatorSettling ? 'nav-active-indicator-edge-settle' : '',
          ]"
          aria-hidden="true"
        />
      </span>
      <button
        v-for="item in items"
        :key="item.key"
        :ref="(el) => setItemButtonRef(el, items.findIndex((x) => x.key === item.key))"
        type="button"
        class="group relative z-[2] flex flex-col items-center justify-center gap-0 rounded-full px-1 py-[0.2rem] text-[10.5px] font-semibold tracking-[0.01em] transition-colors duration-200"
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
          title="Чат под угрозой"
          aria-label="Чат под угрозой"
        >
          <span class="absolute inline-flex h-4 w-4 animate-ping rounded-full bg-yellow-400/55" />
          <span class="relative text-[12px] leading-none text-yellow-300">⚠</span>
        </span>
        <span class="inline-flex h-8 w-8 shrink-0 items-center justify-center p-0 transition" :class="isActive(item) ? 'text-[#7cc0ff]' : 'text-zinc-200/95'">
          <NavIcon
            :name="item.icon"
            :class="item.key === 'partner' ? 'h-[1.95rem] w-[1.95rem] text-current' : item.key === 'support' ? 'h-[1.72rem] w-[1.72rem] text-current' : 'h-[1.58rem] w-[1.58rem] text-current'"
          />
        </span>
        <span class="-mt-[1px] max-w-full truncate leading-none" :class="isActive(item) ? 'text-[#7fc3ff]' : 'text-zinc-100/92'">{{ item.label }}</span>
      </button>
    </div>
  </nav>
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
  transition-duration: 460ms;
  transition-timing-function: cubic-bezier(0.2, 0.78, 0.2, 1);
  background: rgba(130, 145, 175, 0.08);
  box-shadow:
    inset 0 0 0 1px rgba(130, 146, 176, 0.12),
    0 8px 18px -14px rgba(40, 60, 95, 0.42);
  backdrop-filter: blur(7px) saturate(1.08);
  -webkit-backdrop-filter: blur(7px) saturate(1.08);
  overflow: hidden;
  cursor: grab;
  touch-action: none;
}

.nav-active-indicator-dragging {
  cursor: grabbing;
  transform: scaleY(1.16);
  background: rgba(130, 145, 175, 0.04);
  box-shadow:
    inset 0 0 0 1px rgba(130, 146, 176, 0.08),
    0 8px 18px -14px rgba(40, 60, 95, 0.3);
}

.nav-active-indicator-settle {
  animation: navIndicatorSettle 260ms cubic-bezier(0.2, 0.75, 0.22, 1);
}

.nav-active-indicator-edge {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  pointer-events: none;
  opacity: 0;
  background:
    linear-gradient(95deg, transparent 0%, rgba(130, 190, 255, 0.12) 8%, rgba(255, 140, 210, 0.2) 14%, rgba(120, 250, 255, 0.2) 18%, rgba(130, 190, 255, 0.12) 22%, transparent 32%) 0 0 / 250% 100% no-repeat,
    conic-gradient(from 215deg at 50% 50%, rgba(255, 120, 195, 0.18), rgba(133, 214, 255, 0.16), rgba(168, 137, 255, 0.18), rgba(255, 120, 195, 0.18));
  box-shadow:
    inset 0 1px 0 rgba(164, 218, 255, 0.26),
    inset 0 -1px 0 rgba(188, 140, 255, 0.26);
  backdrop-filter: blur(14px) saturate(1.46) contrast(1.1);
  -webkit-backdrop-filter: blur(14px) saturate(1.46) contrast(1.1);
  mask: radial-gradient(closest-side, transparent calc(100% - 2.8px), #000 calc(100% - 1.7px));
  -webkit-mask: radial-gradient(closest-side, transparent calc(100% - 2.8px), #000 calc(100% - 1.7px));
  mix-blend-mode: screen;
  transition: opacity 180ms ease;
}

.nav-active-indicator-edge-run {
  animation: navEdgeFlow 520ms cubic-bezier(0.2, 0.7, 0.2, 1);
  opacity: 0.92;
}

.nav-active-indicator-edge-drag {
  animation: navEdgeFlow 900ms linear infinite;
  opacity: 1;
}

.nav-active-indicator-edge-settle {
  animation: navEdgeSettle 260ms ease-out;
  opacity: 0.7;
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

@keyframes navIndicatorSettle {
  0% { transform: scaleY(1.16); }
  100% { transform: scaleY(1); }
}

@keyframes navEdgeSettle {
  0% { opacity: 1; }
  100% { opacity: 0; }
}
</style>


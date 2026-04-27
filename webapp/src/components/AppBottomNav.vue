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
  height: 'auto',
  borderRadius: '999px',
  opacity: 0,
  transitionDuration: '320ms',
})
const navActiveIndicatorAnimating = ref(false)
const navActiveIndicatorDragging = ref(false)
const navActiveIndicatorSettling = ref(false)
const navIndicatorPhase = ref('idle')
const navPrevActiveIndex = ref(0)
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

function waitMs(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function setItemButtonRef(el, index) {
  if (!el) return
  itemButtonRefs.value[index] = el
}

function indicatorMetricsForButton(btn, grid) {
  const g = grid.getBoundingClientRect()
  const b = btn.getBoundingClientRect()
  const left = Math.max(0, b.left - g.left)
  const width = Math.max(0, b.width)
  const height = Math.max(0, b.height)
  const circleSize = Math.max(18, Math.min(width, height))
  return { left, width, height, circleSize }
}

async function animateIndicatorTravel(fromIdx, toIdx) {
  const grid = navGridRef.value
  const fromBtn = itemButtonRefs.value[fromIdx]
  const toBtn = itemButtonRefs.value[toIdx]
  if (!grid || !fromBtn || !toBtn || fromIdx === toIdx) return

  const from = indicatorMetricsForButton(fromBtn, grid)
  const to = indicatorMetricsForButton(toBtn, grid)

  navIndicatorPhase.value = 'travel'
  navActiveIndicatorAnimating.value = false

  const curLeft = Number.parseFloat(String(navActiveIndicatorStyle.value.left || '0').replace('px', '')) || from.left
  const curWidth = Number.parseFloat(String(navActiveIndicatorStyle.value.width || '0').replace('px', '')) || from.width

  const startCenter = curLeft + curWidth / 2
  const endCenter = to.left + to.width / 2
  const travelLeft = Math.max(0, startCenter - from.circleSize / 2)

  navActiveIndicatorStyle.value = {
    ...navActiveIndicatorStyle.value,
    left: `${travelLeft}px`,
    width: `${from.circleSize}px`,
    height: `${from.circleSize}px`,
    borderRadius: '999px',
    opacity: 1,
    transitionDuration: '240ms',
    transitionTimingFunction: 'cubic-bezier(0.2, 0.85, 0.15, 1)',
  }

  await waitMs(240)

  const moveLeft = Math.max(0, endCenter - from.circleSize / 2)
  navActiveIndicatorStyle.value = {
    ...navActiveIndicatorStyle.value,
    left: `${moveLeft}px`,
    transitionDuration: '520ms',
    transitionTimingFunction: 'cubic-bezier(0.18, 0.72, 0.18, 1)',
  }

  await waitMs(520)

  navIndicatorPhase.value = 'land'
  navActiveIndicatorAnimating.value = false
  requestAnimationFrame(() => {
    navActiveIndicatorAnimating.value = true
    if (navIndicatorAnimTimer) clearTimeout(navIndicatorAnimTimer)
    navIndicatorAnimTimer = setTimeout(() => {
      navActiveIndicatorAnimating.value = false
    }, 620)
  })

  navActiveIndicatorStyle.value = {
    ...navActiveIndicatorStyle.value,
    left: `${to.left}px`,
    width: `${to.width}px`,
    height: `${to.height}px`,
    borderRadius: '999px',
    opacity: 1,
    transitionDuration: '380ms',
    transitionTimingFunction: 'cubic-bezier(0.18, 0.78, 0.14, 1)',
  }

  await waitMs(380)
  navIndicatorPhase.value = 'idle'
}

function updateActiveIndicator(withTravel = false) {
  nextTick(async () => {
    const grid = navGridRef.value
    const idx = activeItemIndex()
    const btn = itemButtonRefs.value[idx]
    if (!grid || !btn) return

    const prevIdx = navPrevActiveIndex.value

    const m = indicatorMetricsForButton(btn, grid)

    if (!withTravel || prevIdx === idx || navActiveIndicatorDragging.value) {
      navActiveIndicatorStyle.value = {
        ...navActiveIndicatorStyle.value,
        left: `${m.left}px`,
        width: `${m.width}px`,
        height: `${m.height}px`,
        borderRadius: '999px',
        opacity: 1,
        transitionDuration: navActiveIndicatorDragging.value ? '0ms' : '460ms',
        transitionTimingFunction: 'cubic-bezier(0.2, 0.78, 0.2, 1)',
      }
      navPrevActiveIndex.value = idx
      return
    }

    await animateIndicatorTravel(prevIdx, idx)
    navPrevActiveIndex.value = idx
  })
}

function startIndicatorDrag(ev) {
  if (!ev) return
  const grid = navGridRef.value
  if (!grid) return
  const curLeft = Number.parseFloat(String(navActiveIndicatorStyle.value.left || '0').replace('px', '')) || 0
  navIndicatorPhase.value = 'travel'
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
    height: `${width}px`,
    borderRadius: '999px',
    opacity: 1,
    transitionDuration: '0ms',
  }
}

function endIndicatorDrag() {
  if (!navDragState.value.active) return
  navDragState.value.active = false
  navActiveIndicatorDragging.value = false
  navActiveIndicatorSettling.value = true
  navIndicatorPhase.value = 'land'
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
  updateActiveIndicator(false)
  if (navIndicatorSettleTimer) clearTimeout(navIndicatorSettleTimer)
  navIndicatorSettleTimer = setTimeout(() => {
    navActiveIndicatorSettling.value = false
    navIndicatorPhase.value = 'idle'
  }, 320)
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
  navPrevActiveIndex.value = activeItemIndex()
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
    class="fixed bottom-3 left-6 right-6 z-40 mx-auto w-auto max-w-[17.8rem] rounded-[1.65rem] border-0 bg-[linear-gradient(180deg,rgba(18,21,28,0.42),rgba(12,14,18,0.42))] pb-[calc(0.18rem+env(safe-area-inset-bottom,0px))] pt-0 shadow-[0_14px_28px_-14px_rgba(0,0,0,0.62)] backdrop-blur-[14px] [contain:layout_paint] [transform:translateZ(0)]"
    style="font-family: 'Exo 2', 'Montserrat', sans-serif;"
  >
    <div ref="navGridRef" class="relative mx-auto grid w-full max-w-[16.6rem] grid-cols-4 gap-0 px-0 pt-[0.18rem] pb-[0.06rem]">
      <span
        class="nav-active-indicator absolute bottom-[0.06rem] z-[3] rounded-full transition-[left,width,height,border-radius,opacity,background-color,box-shadow,backdrop-filter,transform] duration-200 ease-out"
        :class="[
          navActiveIndicatorAnimating ? 'nav-active-indicator-squeeze' : '',
          navActiveIndicatorDragging ? 'nav-active-indicator-dragging' : '',
          navActiveIndicatorSettling ? 'nav-active-indicator-settle' : '',
          navIndicatorPhase === 'travel' ? 'nav-active-indicator-travel' : '',
          navIndicatorPhase === 'land' ? 'nav-active-indicator-land' : '',
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
            navIndicatorPhase === 'travel' ? 'nav-active-indicator-edge-travel' : '',
            navIndicatorPhase === 'land' ? 'nav-active-indicator-edge-land' : '',
          ]"
          aria-hidden="true"
        />
      </span>
      <button
        v-for="item in items"
        :key="item.key"
        :ref="(el) => setItemButtonRef(el, items.findIndex((x) => x.key === item.key))"
        type="button"
        class="group relative z-[2] flex flex-col items-center justify-center gap-0 rounded-full px-0.5 py-[0.18rem] text-[10.5px] font-semibold tracking-[0.01em] transition-colors duration-200"
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
  animation: navIndicatorSqueeze 620ms cubic-bezier(0.18, 0.78, 0.14, 1);
}

@keyframes navIndicatorSqueeze {
  0% { transform: scaleY(1); }
  40% { transform: scaleY(1.06); }
  70% { transform: scaleY(0.94); }
  100% { transform: scaleY(1); }
}

.nav-active-indicator {
  transition-duration: 460ms;
  transition-timing-function: cubic-bezier(0.2, 0.78, 0.2, 1);
  background:
    radial-gradient(closest-side, transparent 62%, rgba(115, 175, 255, 0.075) 100%);
  box-shadow: none;
  backdrop-filter: blur(8px) saturate(1.05);
  -webkit-backdrop-filter: blur(8px) saturate(1.05);
  overflow: hidden;
  cursor: grab;
  touch-action: none;
}

.nav-active-indicator-travel {
  backdrop-filter: blur(0px) saturate(1);
  -webkit-backdrop-filter: blur(0px) saturate(1);
  background: transparent;
  box-shadow: none;
}

.nav-active-indicator-land {
  backdrop-filter: blur(11px) saturate(1.18) contrast(1.03);
  -webkit-backdrop-filter: blur(11px) saturate(1.18) contrast(1.03);
}

.nav-active-indicator-dragging {
  cursor: grabbing;
  transform: scaleY(1.06);
  backdrop-filter: blur(0px) saturate(1);
  -webkit-backdrop-filter: blur(0px) saturate(1);
  background: transparent;
}

.nav-active-indicator-settle {
  animation: navIndicatorSettle 320ms cubic-bezier(0.2, 0.75, 0.22, 1);
}

.nav-active-indicator-edge {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  opacity: 0;
  background:
    linear-gradient(
      95deg,
      transparent 0%,
      rgba(120, 200, 255, 0.08) 9%,
      rgba(255, 150, 230, 0.1) 14%,
      rgba(130, 255, 245, 0.1) 18%,
      rgba(120, 200, 255, 0.08) 23%,
      transparent 34%
    ) 0 0 / 280% 100% no-repeat;
  /* edge-only: keep the center fully clear */
  mask: radial-gradient(closest-side, transparent calc(100% - 3px), #000 calc(100% - 2.1px));
  -webkit-mask: radial-gradient(closest-side, transparent calc(100% - 3px), #000 calc(100% - 2.1px));
  backdrop-filter: blur(10px) saturate(1.35) hue-rotate(12deg);
  -webkit-backdrop-filter: blur(10px) saturate(1.35) hue-rotate(12deg);
  mix-blend-mode: soft-light;
  transition: opacity 180ms ease;
}

.nav-active-indicator-edge-run {
  animation: navEdgeFlow 620ms cubic-bezier(0.18, 0.72, 0.14, 1);
  opacity: 0.95;
}

.nav-active-indicator-edge-drag {
  animation: navEdgeFlow 900ms linear infinite;
  opacity: 1;
}

.nav-active-indicator-edge-settle {
  animation: navEdgeSettle 280ms ease-out;
  opacity: 0.65;
}

.nav-active-indicator-edge-travel {
  animation: navEdgeFlow 520ms linear infinite;
  opacity: 1;
}

.nav-active-indicator-edge-land {
  animation: navEdgeRainbow 620ms cubic-bezier(0.18, 0.78, 0.14, 1);
  opacity: 1;
}

@keyframes navEdgeFlow {
  0% {
    background-position: 0% 0;
    opacity: 0.52;
  }
  45% {
    background-position: 58% 0;
    opacity: 0.92;
  }
  100% {
    background-position: 100% 0;
    opacity: 0.72;
  }
}

@keyframes navEdgeRainbow {
  0% {
    background-position: 18% 0;
    opacity: 0.45;
    filter: blur(0.2px) saturate(1.05);
  }
  55% {
    background-position: 72% 0;
    opacity: 0.95;
    filter: blur(0px) saturate(1.22);
  }
  100% {
    background-position: 100% 0;
    opacity: 0.35;
    filter: blur(0px) saturate(1.08);
  }
}

@keyframes navIndicatorSettle {
  0% { transform: scaleY(1.1); }
  100% { transform: scaleY(1); }
}

@keyframes navEdgeSettle {
  0% { opacity: 1; }
  100% { opacity: 0; }
}
</style>


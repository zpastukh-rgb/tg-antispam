<script setup>
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { navItems } from '../config/nav.js'
import NavIcon from './NavIcon.vue'
import { useDashboardSection } from '../composables/useDashboardSection'
import { api } from '../api/client'
import { prefetchReportsView } from '../utils/reportsViewCache.js'
import { navQueryForPath } from '../utils/navQuery.js'

const { t } = useI18n()

const props = defineProps({
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['close'])

const route = useRoute()
const router = useRouter()
const { dashboardSection, setDashboardSection } = useDashboardSection()

const brandBadgeSrc = `${import.meta.env.BASE_URL}panel-brand-badge.png`

const isActive = (item) => {
  if (item.section) {
    return route.path === '/' && dashboardSection.value === item.section
  }
  if (item.path === '/') {
    return (
      route.path === '/'
      && (dashboardSection.value === 'account' || dashboardSection.value === 'subscription')
    )
  }
  const p = item.path || ''
  return route.path === p || (p.length > 1 && route.path.startsWith(`${p}/`))
}

function onNavClick(item) {
  if (item.path === '/reports') {
    void prefetchReportsView(api)
    window.dispatchEvent(new CustomEvent('guard:prefetch-reports'))
  }
  if (item.section) {
    setDashboardSection(item.section)
    router.push({ path: '/', query: { ...route.query, section: item.section } })
  } else if (item.path === '/') {
    setDashboardSection('account')
    router.push({ path: '/', query: { ...route.query, section: 'account' } })
  } else {
    router.push({ path: item.path, query: navQueryForPath(item.path, route.query) })
  }
  emit('close')
}
</script>

<template>
  <div>
    <!-- затемнение + лёгкий blur под стекло -->
    <div
      v-if="open"
      class="fixed inset-0 z-40 bg-black/45 backdrop-blur-[2px] md:hidden"
      aria-hidden="true"
      @click="emit('close')"
    />
    <aside
      :class="[
        'fixed left-0 top-0 z-50 flex h-full w-[17rem] transform flex-col border-r border-white/15 bg-white/[0.08] pt-11 shadow-[8px_0_48px_-12px_rgba(0,0,0,0.65)] backdrop-blur-2xl backdrop-saturate-150 transition-transform duration-300 ease-out dark:bg-zinc-950/35 md:translate-x-0 md:pt-12 md:shadow-none',
        open ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
      ]"
      style="box-shadow: inset 1px 0 0 rgba(255,255,255,0.06)"
    >
      <nav class="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto overscroll-contain p-3 pb-8">
        <div class="mb-3 w-full shrink-0">
          <img
            :src="brandBadgeSrc"
            alt=""
            draggable="false"
            class="pointer-events-none block h-auto w-full max-w-none select-none object-contain object-center drop-shadow-[0_12px_32px_-8px_rgba(132,225,62,0.22)]"
            width="918"
            height="319"
            @dragstart.prevent
          />
        </div>
        <button
          v-for="item in navItems"
          :key="item.path + (item.section || '') + (item.labelKey || item.label || '')"
          type="button"
          class="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200"
          :class="
            isActive(item)
              ? 'border border-lime-400/35 bg-lime-400/14 text-white shadow-[0_0_24px_-8px_rgba(163,230,53,0.45)] dark:bg-lime-400/12'
              : 'border border-transparent text-slate-300 hover:border-white/10 hover:bg-white/[0.06] hover:text-white'
          "
          @click="onNavClick(item)"
        >
          <NavIcon :name="item.icon" class="h-5 w-5 shrink-0 opacity-95" />
          <span class="min-w-0 truncate">{{ item.labelKey ? t(item.labelKey) : item.label }}</span>
        </button>
      </nav>
    </aside>
  </div>
</template>

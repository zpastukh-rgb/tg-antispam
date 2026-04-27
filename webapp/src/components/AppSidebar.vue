<script setup>
import { useRoute, useRouter } from 'vue-router'
import { navItems } from '../config/nav.js'
import NavIcon from './NavIcon.vue'
import { useDashboardSection } from '../composables/useDashboardSection'

const props = defineProps({
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['close'])

const route = useRoute()
const router = useRouter()
const { dashboardSection, setDashboardSection } = useDashboardSection()

const logoSrc = `${import.meta.env.BASE_URL}logo.png`

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
  return route.path.startsWith(item.path)
}

function onNavClick(item) {
  if (item.section) {
    setDashboardSection(item.section)
    router.push('/')
  } else {
    router.push(item.path)
  }
  emit('close')
}
</script>

<template>
  <div>
    <!-- overlay на мобильных -->
    <div
      v-if="open"
      class="fixed inset-0 z-40 bg-black/50 md:hidden"
      aria-hidden="true"
      @click="emit('close')"
    />
    <aside
      :class="[
        'fixed left-0 top-0 z-50 h-full w-64 transform border-r border-gray-200/90 bg-white pt-14 transition-transform duration-200 ease-out dark:border-guardian-elevated-hi dark:bg-guardian-elevated md:translate-x-0 md:pt-14',
        open ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
      ]"
    >
      <nav class="flex flex-col gap-0.5 p-3">
        <div
          class="mb-3 flex flex-col gap-2 rounded-xl border border-primary-500/25 bg-primary-500/8 px-2 py-3 ring-1 ring-primary-500/10 backdrop-blur-sm dark:border-sky-500/30 dark:bg-slate-950/45 dark:ring-sky-500/15"
        >
          <img
            :src="logoSrc"
            alt="AntiSpam Guard"
            width="160"
            height="120"
            draggable="false"
            class="mx-auto h-16 w-auto max-w-full object-contain drop-shadow-[0_0_8px_rgba(143,212,26,0.3)] dark:drop-shadow-[0_0_10px_rgba(143,212,26,0.2)]"
            @dragstart.prevent
          />
          <div class="min-w-0 border-t border-primary-200/50 pt-2 text-center leading-tight dark:border-primary-500/15">
            <p class="text-xs font-semibold uppercase tracking-wide text-primary-800 dark:text-primary-300">Панель</p>
            <p class="text-sm font-bold text-guardian-ink dark:text-white">AntiSpam Guard</p>
          </div>
        </div>
        <button
          v-for="item in navItems"
          :key="item.path"
          type="button"
          class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors"
          :class="
            isActive(item)
              ? 'bg-primary-100 text-primary-900 dark:bg-primary-500/15 dark:text-primary-300'
              : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-guardian-elevated-hi dark:hover:text-gray-200'
          "
          @click="onNavClick(item)"
        >
          <NavIcon :name="item.icon" class="w-5 h-5" />
          <span class="min-w-0 truncate">{{ item.label }}</span>
        </button>
      </nav>
    </aside>
  </div>
</template>

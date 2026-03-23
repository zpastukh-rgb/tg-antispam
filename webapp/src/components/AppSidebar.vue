<script setup>
import { useRoute } from 'vue-router'
import { navItems } from '../config/nav.js'
import NavIcon from './NavIcon.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['close'])

const route = useRoute()

const logoSrc = `${import.meta.env.BASE_URL}avatar.png`

const isActive = (path) => {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
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
        <div class="mb-3 flex items-center gap-2.5 rounded-xl border border-primary-200/60 bg-primary-50/80 px-2.5 py-2 dark:border-primary-500/20 dark:bg-primary-500/10">
          <img
            :src="logoSrc"
            alt=""
            width="40"
            height="40"
            class="h-10 w-10 shrink-0 rounded-lg object-cover ring-1 ring-primary-400/40"
          />
          <div class="min-w-0 leading-tight">
            <p class="truncate text-xs font-semibold uppercase tracking-wide text-primary-800 dark:text-primary-300">Панель</p>
            <p class="truncate text-sm font-bold text-guardian-ink dark:text-white">Guardian</p>
          </div>
        </div>
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors"
          :class="
            isActive(item.path)
              ? 'bg-primary-100 text-primary-900 dark:bg-primary-500/15 dark:text-primary-300'
              : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-guardian-elevated-hi dark:hover:text-gray-200'
          "
          @click="emit('close')"
        >
          <NavIcon :name="item.icon" class="w-5 h-5" />
          <span>{{ item.label }}</span>
        </router-link>
      </nav>
    </aside>
  </div>
</template>

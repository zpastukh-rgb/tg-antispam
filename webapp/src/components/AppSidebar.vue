<script setup>
import { useRoute } from 'vue-router'
import { navItems } from '../config/nav.js'
import NavIcon from './NavIcon.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['close'])

const route = useRoute()

const logoSrc = `${import.meta.env.BASE_URL}logo.png`

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
        <div
          class="mb-3 flex flex-col gap-2 rounded-xl border border-primary-200/60 bg-primary-50/80 px-2 py-3 dark:border-primary-500/20 dark:bg-primary-500/10"
        >
          <img
            :src="logoSrc"
            alt="AntiSpam Guardian"
            width="160"
            height="120"
            class="mx-auto h-16 w-auto max-w-full object-contain drop-shadow-[0_0_8px_rgba(143,212,26,0.3)] dark:drop-shadow-[0_0_10px_rgba(143,212,26,0.2)]"
          />
          <div class="min-w-0 border-t border-primary-200/50 pt-2 text-center leading-tight dark:border-primary-500/15">
            <p class="text-xs font-semibold uppercase tracking-wide text-primary-800 dark:text-primary-300">Панель</p>
            <p class="text-sm font-bold text-guardian-ink dark:text-white">AntiSpam Guardian</p>
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

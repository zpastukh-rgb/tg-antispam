<script setup>
import { useRoute } from 'vue-router'
import { navItems } from '../config/nav.js'
import NavIcon from './NavIcon.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['close'])

const route = useRoute()

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
        'fixed left-0 top-0 z-50 h-full w-64 transform border-r border-gray-200 bg-white pt-14 transition-transform duration-200 ease-out dark:border-gray-700 dark:bg-gray-800 md:translate-x-0 md:pt-14',
        open ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
      ]"
    >
      <nav class="flex flex-col gap-0.5 p-3">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors"
          :class="
            isActive(item.path)
              ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
              : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-200'
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

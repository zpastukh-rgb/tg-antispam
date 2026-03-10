<script setup>
import { useTheme } from '../composables/useTheme'
import NavIcon from './NavIcon.vue'

const { isDark, toggle } = useTheme()

defineProps({
  sidebarOpen: Boolean,
})

const emit = defineEmits(['menu-click'])
</script>

<template>
  <header class="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-gray-200 bg-white px-4 dark:border-gray-700 dark:bg-gray-800 md:px-6">
    <div class="flex items-center gap-3">
      <button
        type="button"
        class="flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-200 md:hidden"
        aria-label="Меню"
        @click="emit('menu-click')"
      >
        <NavIcon name="menu" class="w-5 h-5" />
      </button>
      <a href="#" class="flex items-center gap-2" @click.prevent="$router.push('/')">
        <span class="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-500 text-white shadow-sm">
          <NavIcon name="shield" class="w-5 h-5" />
        </span>
        <span class="text-lg font-semibold tracking-tight text-gray-900 dark:text-white">Guardian</span>
      </a>
    </div>
    <button
      type="button"
      class="flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-200"
      :aria-label="isDark ? 'Светлая тема' : 'Тёмная тема'"
      @click="toggle"
    >
      <NavIcon v-if="isDark" name="sun" class="w-5 h-5" />
      <NavIcon v-else name="moon" class="w-5 h-5" />
    </button>
  </header>
</template>

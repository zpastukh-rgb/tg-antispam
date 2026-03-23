<script setup>
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useTheme } from '../composables/useTheme'
import NavIcon from './NavIcon.vue'

const router = useRouter()
const route = useRoute()
const { isDark, toggle } = useTheme()

defineProps({
  sidebarOpen: Boolean,
})

const emit = defineEmits(['menu-click'])

/** С base: './' в Vite публичные файлы через BASE_URL */
const logoSrc = `${import.meta.env.BASE_URL}logo.png`

const showBack = computed(() => route.path !== '/' && route.path !== '')

function goBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/')
  }
}
</script>

<template>
  <header
    class="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-gray-200/80 bg-white/95 px-4 shadow-sm shadow-primary-500/5 backdrop-blur-sm dark:border-guardian-elevated-hi dark:bg-guardian-elevated/95 md:px-6"
  >
    <div class="flex items-center gap-3">
      <button
        v-if="showBack"
        type="button"
        class="flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-200"
        aria-label="Назад"
        @click="goBack"
      >
        <NavIcon name="back" class="w-5 h-5" />
      </button>
      <button
        v-else
        type="button"
        class="flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-200"
        aria-label="Меню"
        @click="emit('menu-click')"
      >
        <NavIcon name="menu" class="w-5 h-5" />
      </button>
      <a href="#" class="flex min-w-0 items-center gap-2.5" @click.prevent="router.push('/')">
        <img
          :src="logoSrc"
          alt="AntiSpam Guardian"
          width="40"
          height="40"
          class="h-9 w-9 shrink-0 object-contain object-center drop-shadow-[0_0_10px_rgba(143,212,26,0.35)] dark:drop-shadow-[0_0_12px_rgba(143,212,26,0.25)]"
        />
        <span class="truncate text-lg font-bold tracking-tight text-guardian-ink dark:text-white">AntiSpam Guardian</span>
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

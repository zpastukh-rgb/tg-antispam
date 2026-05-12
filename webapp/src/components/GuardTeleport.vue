<script setup>
import { computed } from 'vue'

/**
 * В Telegram Mini App WebView телепорт за пределы дерева страницы часто даёт «пустой» оверлей или модалку без содержимого.
 * В TMA рендерим слот на месте (без Teleport). В браузере — в #guard-modal-root.
 * Не используем Teleport :disabled — в WKWebView это может «съедать» клики по основному контенту.
 */
const disableTeleport = computed(() => {
  if (typeof window === 'undefined') return false
  try {
    return !!window.Telegram?.WebApp
  } catch {
    return false
  }
})
</script>

<template>
  <Teleport v-if="!disableTeleport" to="#guard-modal-root">
    <slot />
  </Teleport>
  <slot v-else />
</template>

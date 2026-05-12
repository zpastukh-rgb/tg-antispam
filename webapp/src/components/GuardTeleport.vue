<script setup>
import { computed } from 'vue'

/**
 * В Telegram Mini App WebView телепорт за пределы дерева страницы часто даёт «пустой» оверлей или модалку без содержимого.
 * В TMA рендерим слот на месте (:disabled), в браузере — в #guard-modal-root.
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
  <Teleport to="#guard-modal-root" :disabled="disableTeleport">
    <slot />
  </Teleport>
</template>

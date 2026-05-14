<script setup>
import { computed } from 'vue'

/** Динамическая цель: при отсутствии #guard-teleport-root (кэш старого HTML, нестандартный shell) — body. */
const teleportTo = computed(() => {
  if (typeof document === 'undefined') return 'body'
  return document.getElementById('guard-teleport-root') ? '#guard-teleport-root' : 'body'
})
</script>

<template>
  <Teleport :to="teleportTo">
    <slot />
  </Teleport>
</template>

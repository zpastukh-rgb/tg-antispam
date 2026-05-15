<script setup>
import { computed } from 'vue'

const props = defineProps({
  /**
   * Не пусто — используется как цель Teleport буквально (например `"body"`).
   * В Telegram Mini App контент в `#guard-teleport-root` иногда не попадает в DOM (зонд: root есть, children 0);
   * модалки «Защита» и тест шлют сюда `body`.
   */
  guardTo: { type: String, default: '' },
})

/** Динамическая цель: при отсутствии #guard-teleport-root — body. Без реактивных deps у `computed` пересчёт только при смене `guardTo`. */
const teleportTo = computed(() => {
  const o = String(props.guardTo || '').trim()
  if (o) return o
  if (typeof document === 'undefined') return 'body'
  return document.getElementById('guard-teleport-root') ? '#guard-teleport-root' : 'body'
})
</script>

<template>
  <Teleport :to="teleportTo">
    <slot />
  </Teleport>
</template>

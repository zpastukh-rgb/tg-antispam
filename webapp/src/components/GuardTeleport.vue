<script setup>
/**
 * Всегда монтируем модалки в #guard-modal-root (внутри #app, над основным контентом).
 * Teleport на document.body в Telegram WebView давал пустые слои; режим «слот на месте»
 * для TMA давал конфликты стекинга/кликов. Единый таргет — предсказуемый z-order.
 */
</script>

<template>
  <Teleport to="#guard-modal-root">
    <slot />
  </Teleport>
</template>

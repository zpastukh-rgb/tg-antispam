<script setup>
/**
 * Всегда монтируем модалки в #guard-modal-root (внутри #app, над основным контентом).
 * Контейнер #guard-modal-root — pointer-events-none (см. App.vue), иначе пустой слой с высоким
 * z-index в Telegram WKWebView перехватывает тапы по странице. Здесь включаем события только для слота.
 */
</script>

<template>
  <Teleport to="#guard-modal-root">
    <div class="pointer-events-auto">
      <slot />
    </div>
  </Teleport>
</template>

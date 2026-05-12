<script setup>
/**
 * Модалки в #guard-modal-root (см. index.html): узел-сосед #app без fixed/inset — иначе WKWebView «ест» тапы.
 * Контейнер pointer-events-none; здесь pointer-events-auto только для содержимого слота.
 */
</script>

<template>
  <Teleport to="#guard-modal-root">
    <div class="pointer-events-auto">
      <slot />
    </div>
  </Teleport>
</template>

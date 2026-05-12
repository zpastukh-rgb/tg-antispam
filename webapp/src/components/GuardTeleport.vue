<script setup>
/**
 * В Telegram Mini App (WKWebView) Vue Teleport на внешний #guard-modal-root давал ситуацию,
 * когда визуально всё есть, но тапы не доходят до кнопок. Рендерим слот на месте —
 * у модалок уже стоят fixed + z-index, поверх контента они поднимаются и без телепорта.
 */
</script>

<template>
  <slot />
</template>

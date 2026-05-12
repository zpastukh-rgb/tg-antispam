<script setup>
import { useI18n } from 'vue-i18n'
/**
 * Общая загрузка: песочные часы + «стекло» на глобальном фоне (без бейджа ADM — он только для шапки).
 */
defineProps({
  /** Меньше отступы — для оверлея при смене маршрута */
  compact: { type: Boolean, default: false },
})
const { t } = useI18n()
</script>

<template>
  <div
    class="flex flex-col items-center justify-center gap-5"
    :class="compact ? 'py-4' : 'min-h-[38dvh] py-10'"
    role="status"
    aria-live="polite"
    aria-busy="true"
  >
    <div
      class="guard-hourglass-scene relative flex h-[4.75rem] w-[4.75rem] items-center justify-center rounded-2xl bg-white/[0.08] shadow-[inset_0_1px_0_rgba(255,255,255,0.12),0_0_28px_-12px_rgba(34,211,238,0.22)] backdrop-blur-xl"
    >
      <svg
        class="guard-hourglass-svg h-11 w-9 text-cyan-100/95"
        viewBox="0 0 36 44"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <path
          d="M6 4h24M6 40h24M8 4v8l10 10 10-10V4M8 40v-8l10-10 10 10v8"
          stroke="currentColor"
          stroke-width="1.65"
          stroke-linecap="round"
          stroke-linejoin="round"
          opacity="0.95"
        />
        <path
          d="M12 22h12"
          stroke="currentColor"
          stroke-width="1.2"
          stroke-linecap="round"
          opacity="0.55"
        />
      </svg>
    </div>
    <p class="text-center text-sm font-medium tracking-tight text-white/82">{{ t('common.loading_pause') }}</p>
  </div>
</template>

<style scoped>
.guard-hourglass-scene {
  perspective: 140px;
}
.guard-hourglass-svg {
  transform-style: preserve-3d;
  animation: guard-hourglass-flip 2.35s cubic-bezier(0.48, 0.06, 0.52, 0.94) infinite;
  filter: drop-shadow(0 0 10px rgba(34, 211, 238, 0.28));
}
@keyframes guard-hourglass-flip {
  0% {
    transform: rotateX(0deg);
  }
  28% {
    transform: rotateX(0deg);
  }
  50% {
    transform: rotateX(180deg);
  }
  78% {
    transform: rotateX(180deg);
  }
  100% {
    transform: rotateX(360deg);
  }
}
</style>

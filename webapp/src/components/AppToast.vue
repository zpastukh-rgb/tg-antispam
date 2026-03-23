<script setup>
import { useToast } from '../composables/useToast'

const { message, visible } = useToast()
</script>

<template>
  <Transition name="toast">
    <div
      v-if="visible && message"
      class="fixed left-0 right-0 top-0 z-[100] flex justify-center px-4 pt-3 md:pt-4"
      role="status"
      aria-live="polite"
    >
      <div
        class="w-full max-w-md rounded-lg px-4 py-3 shadow-lg md:rounded-xl md:py-3.5"
        :class="[
          'border border-guardian-elevated-hi bg-guardian-elevated text-white shadow-glow-cyan dark:bg-guardian-elevated-hi',
        ]"
      >
        <p class="text-center text-sm font-medium text-white md:text-base">
          {{ message }}
        </p>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: transform 0.25s ease-out, opacity 0.2s ease-out;
}
.toast-enter-from,
.toast-leave-to {
  transform: translateY(-100%);
  opacity: 0;
}
</style>

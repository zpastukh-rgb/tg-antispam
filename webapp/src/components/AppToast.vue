<script setup>
import { useToast } from '../composables/useToast'

const { message, visible } = useToast()
</script>

<template>
  <!--
    Teleport в body, чтобы тост не зависел от stacking-context родителей
    (App.vue заворачивает контент в `relative z-10` — без teleport тост стал бы
    ребёнком этого контекста и его z-index 2147483600 оказался бы ограничен,
    оставаясь ВИЗУАЛЬНО позади Vue-модалок из ProtectionView с position:fixed).
  -->
  <Teleport to="body">
    <Transition name="toast">
      <div
        v-if="visible && message"
        style="position:fixed;top:0;left:0;right:0;z-index:2147483600;display:flex;justify-content:center;padding-left:16px;padding-right:16px;padding-top:12px;pointer-events:none"
        class="pointer-events-none"
        role="status"
        aria-live="polite"
      >
        <div
          class="pointer-events-auto w-full max-w-md rounded-lg px-4 py-3 shadow-lg md:rounded-xl md:py-3.5"
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
  </Teleport>
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

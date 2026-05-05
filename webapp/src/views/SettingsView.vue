<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

onMounted(() => {
  try {
    window?.Telegram?.WebApp?.expand?.()
  } catch {
    //
  }
})
</script>

<template>
  <div class="mx-auto max-w-lg space-y-4 pb-8">
    <div class="rounded-2xl border border-white/10 bg-white/[0.04] p-4 backdrop-blur-xl">
      <h1 class="text-lg font-bold text-white">Настройки</h1>
      <p class="mt-2 text-sm text-slate-400">
        Язык и тема управляются в Telegram. Дополнительные пункты появятся здесь по мере обновлений Guard.
      </p>
    </div>
    <button
      type="button"
      class="w-full rounded-xl border border-white/10 bg-white/[0.06] px-4 py-3 text-left text-sm font-medium text-slate-200 transition hover:bg-white/[0.1]"
      @click="router.push('/')"
    >
      ← На главную
    </button>
  </div>
</template>

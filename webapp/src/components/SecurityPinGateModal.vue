<script setup>
defineProps({
  open: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  error: { type: String, default: '' },
  modelValue: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'submit', 'cancel'])
</script>

<template>
  <div
    v-if="open"
    style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:2147483000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-center justify-center bg-black/72 px-4 backdrop-blur-md"
    role="presentation"
    @click.self="emit('cancel')"
  >
    <div
      class="w-full max-w-sm rounded-[20px] bg-gradient-to-b from-slate-900/98 to-slate-950/98 p-4 shadow-[0_24px_60px_-20px_rgba(0,0,0,0.85)] ring-1 ring-cyan-400/20"
      role="dialog"
      aria-modal="true"
      aria-labelledby="pin-gate-title"
    >
      <p id="pin-gate-title" class="text-[17px] font-semibold tracking-tight text-white">Код безопасности</p>
      <p class="mt-1 text-[12px] leading-snug text-white/45">4 цифры из раздела «Настройки → Безопасность»</p>
      <input
        :value="modelValue"
        type="password"
        inputmode="numeric"
        maxlength="4"
        autocomplete="off"
        class="mt-3 w-full rounded-xl border border-white/[0.12] bg-black/35 px-4 py-3.5 text-center text-[22px] font-semibold tracking-[0.35em] text-white outline-none focus:border-emerald-400/35"
        placeholder="••••"
        @input="emit('update:modelValue', String($event.target?.value || '').replace(/\D/g, '').slice(0, 4))"
        @keyup.enter="emit('submit')"
      />
      <p v-if="error" class="mt-2 text-[13px] text-rose-300">{{ error }}</p>
      <div class="mt-4 flex gap-2">
        <button
          type="button"
          class="flex-1 rounded-xl bg-white/[0.08] py-2.5 text-[14px] font-semibold text-white/90 ring-1 ring-white/10 transition hover:bg-white/[0.12]"
          @click="emit('cancel')"
        >
          Отмена
        </button>
        <button
          type="button"
          class="flex-1 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 py-2.5 text-[14px] font-semibold text-white shadow-[0_8px_24px_-8px_rgba(16,185,129,0.55)] transition hover:brightness-110 disabled:opacity-50"
          :disabled="busy"
          @click="emit('submit')"
        >
          Продолжить
        </button>
      </div>
    </div>
  </div>
</template>

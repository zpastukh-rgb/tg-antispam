<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  embedded: { type: Boolean, default: false },
  enabled: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  variant: { type: String, default: 'channel' }, // channel | group
})

const emit = defineEmits(['toggle'])

const { t } = useI18n()

const description = computed(() =>
  props.variant === 'channel'
    ? t('chats.auto_approve.desc_channel')
    : t('chats.auto_approve.desc_group'),
)

function iosSwitchClass(on) {
  return on
    ? 'border-emerald-400/40 bg-emerald-500/[0.32] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.12)]'
    : 'border-white/[0.14] bg-white/[0.09]'
}
</script>

<template>
  <div
    class="rounded-2xl border border-violet-300/20 bg-gradient-to-b from-violet-500/[0.1] via-white/[0.03] to-transparent p-3 ring-1 ring-white/[0.06]"
    :class="embedded ? 'mt-0' : 'mt-2'"
  >
    <div class="flex items-start gap-3">
      <div
        class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-violet-400/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] ring-1 ring-violet-300/35"
        aria-hidden="true"
      >
        <span class="text-[17px] font-bold leading-none text-violet-100">✓</span>
      </div>
      <div class="min-w-0 flex-1">
        <div class="flex items-center justify-between gap-2">
          <p class="text-[13px] font-bold leading-tight text-white">{{ t('chats.auto_approve.title') }}</p>
          <button
            type="button"
            role="switch"
            :aria-checked="enabled"
            :disabled="loading"
            class="relative h-[26px] w-[46px] shrink-0 rounded-full border transition disabled:opacity-50"
            :class="iosSwitchClass(enabled)"
            @click="emit('toggle', !enabled)"
          >
            <span
              class="absolute left-0.5 top-1/2 h-[20px] w-[20px] rounded-full bg-white shadow transition-transform will-change-transform"
              :style="{ transform: enabled ? 'translate3d(20px, -50%, 0)' : 'translate3d(0, -50%, 0)' }"
            />
          </button>
        </div>
        <p class="mt-1.5 text-[11px] leading-snug text-slate-400">{{ description }}</p>
        <p class="mt-1 text-[10px] leading-snug text-slate-500">{{ t('chats.auto_approve.bot_rights_hint') }}</p>
      </div>
    </div>
  </div>
</template>

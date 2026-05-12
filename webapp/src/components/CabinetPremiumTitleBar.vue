<script setup>
/** Полоска 👑 «Кабинет Free/Premium» — текст ближе к короне, справа шеврон. */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import NavIcon from './NavIcon.vue'

const { t } = useI18n()

const props = defineProps({
  profile: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['go-subscription'])

const cabinetPremium = computed(
  () =>
    !!props.profile?.is_premium ||
    ['premium', 'pro', 'business'].includes(String(props.profile?.tariff || '').toLowerCase()),
)

const title = computed(() =>
  cabinetPremium.value ? t('cabinet_stats.hero.title_bar_premium') : t('cabinet_stats.hero.title_bar_free'),
)
</script>

<template>
  <button
    type="button"
    class="flex w-full items-center gap-3 rounded-2xl border border-violet-500/25 bg-gradient-to-r from-violet-950/95 via-indigo-950/90 to-slate-950/95 px-3 py-3 text-left shadow-[0_12px_40px_-20px_rgba(76,29,149,0.65)] ring-1 ring-white/[0.06] transition hover:brightness-[1.03] active:scale-[0.99]"
    @click="emit('go-subscription')"
  >
    <span class="flex h-9 w-9 shrink-0 items-center justify-center text-2xl drop-shadow-[0_0_12px_rgba(250,204,21,0.35)]" aria-hidden="true">👑</span>
    <span class="min-w-0 flex-1 text-left text-[17px] font-extrabold tracking-tight text-white">{{ title }}</span>
    <NavIcon name="chevron-right" class="h-5 w-5 shrink-0 text-white/55" />
  </button>
</template>

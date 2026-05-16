<script setup>
/**
 * Главный экран «синего» кабинета (Free / Premium): шапка + сетка 2×3 как в референсе.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import NavIcon from './NavIcon.vue'

const { t } = useI18n()

const props = defineProps({
  summary: { type: Object, default: () => ({}) },
  profile: { type: Object, default: () => ({}) },
  referralPaidCount: { type: [Number, null], default: null },
  broadcastSpendTokens: { type: [Number, null], default: null },
})

const emit = defineEmits(['open-section', 'open-main'])

const cabinetPremium = computed(
  () =>
    !!props.profile?.is_premium ||
    ['premium', 'pro', 'business'].includes(String(props.profile?.tariff || '').toLowerCase()),
)

/** Золотой бейдж «Premium» только в Free-кабинете (апселл). Внизу слева плитки — не перекрывает заголовок. */
const showPremiumUpsellBadge = computed(() => !cabinetPremium.value)

const premiumCornerBadgeClass =
  'pointer-events-none absolute bottom-2.5 left-2.5 z-10 inline-flex items-center gap-0.5 rounded-md border border-amber-400/40 bg-gradient-to-r from-amber-400/95 via-yellow-300/90 to-amber-500/95 px-1.5 py-0.5 text-[9px] font-extrabold uppercase tracking-wide text-amber-950 shadow-sm'

const protectionActive = computed(() => !!props.summary?.protection_active)
const deletedToday = computed(() => Number(props.summary?.today?.deleted || 0))
const joinsToday = computed(() => Number(props.summary?.today?.joins || 0))
const groups = computed(() => Number((props.summary?.groups_count ?? props.summary?.chats_count) || 0))
const channels = computed(() => Number(props.summary?.channels_count || 0))

const title = computed(() =>
  cabinetPremium.value ? t('owner_cabinet_home.title_premium') : t('owner_cabinet_home.title_free'),
)

function open(key) {
  emit('open-section', key)
}
</script>

<template>
  <div class="space-y-3 font-display">
    <button
      type="button"
      class="flex w-full items-center gap-3 rounded-2xl border border-violet-500/25 bg-gradient-to-r from-violet-950/95 via-indigo-950/90 to-slate-950/95 px-3 py-3 text-left shadow-[0_12px_40px_-20px_rgba(76,29,149,0.65)] ring-1 ring-white/[0.06] transition hover:brightness-[1.03] active:scale-[0.99]"
      @click="emit('open-main')"
    >
      <span class="flex h-9 w-9 shrink-0 items-center justify-center text-2xl drop-shadow-[0_0_12px_rgba(250,204,21,0.35)]" aria-hidden="true">👑</span>
      <span class="min-w-0 flex-1 text-left text-[17px] font-extrabold tracking-tight text-white">{{ title }}</span>
      <NavIcon name="chevron-right" class="h-5 w-5 shrink-0 text-white/55" />
    </button>

    <div class="grid grid-cols-2 gap-2.5">
      <!-- Защита -->
      <button
        type="button"
        class="relative flex h-full w-full flex-col items-start justify-start overflow-hidden rounded-2xl border border-emerald-500/35 bg-gradient-to-br from-emerald-950/80 via-emerald-900/40 to-slate-950/90 p-3.5 pb-11 text-left shadow-[0_0_28px_-14px_rgba(16,185,129,0.55)] ring-1 ring-white/[0.05] transition hover:brightness-105 active:scale-[0.99]"
        @click="open('protection')"
      >
        <span v-if="showPremiumUpsellBadge" :class="premiumCornerBadgeClass">
          <span class="text-[10px]" aria-hidden="true">👑</span> {{ t('owner_cabinet_home.premium_badge') }}
        </span>
        <p class="text-[13px] font-bold leading-tight text-white">{{ t('owner_cabinet_home.protection_heading') }}</p>
        <p class="mt-0.5 text-[11px] font-semibold" :class="protectionActive ? 'text-emerald-300' : 'text-rose-300/90'">
          {{ protectionActive ? t('owner_cabinet_home.protection_on') : t('owner_cabinet_home.protection_off') }}
        </p>
        <p class="mt-3 text-4xl font-black tabular-nums leading-none text-white">{{ deletedToday }}</p>
        <p class="mt-1 text-[11px] text-white/55">{{ t('owner_cabinet_home.deleted_label') }}</p>
        <div class="pointer-events-none absolute bottom-2.5 right-2.5 opacity-95">
          <NavIcon name="shield" class="h-9 w-9 text-emerald-400/90 drop-shadow-[0_0_12px_rgba(52,211,153,0.35)]" />
        </div>
      </button>

      <!-- Статистика -->
      <button
        type="button"
        class="relative flex h-full w-full flex-col items-start justify-start overflow-hidden rounded-2xl border border-indigo-500/35 bg-gradient-to-br from-indigo-950/85 via-violet-950/50 to-slate-950/90 p-3.5 pb-11 text-left shadow-[0_0_28px_-14px_rgba(99,102,241,0.5)] ring-1 ring-white/[0.05] transition hover:brightness-105 active:scale-[0.99]"
        @click="open('stats')"
      >
        <span v-if="showPremiumUpsellBadge" :class="premiumCornerBadgeClass">
          <span class="text-[10px]" aria-hidden="true">👑</span> {{ t('owner_cabinet_home.premium_badge') }}
        </span>
        <p class="text-[13px] font-bold leading-tight text-white">{{ t('owner_cabinet_home.stats_heading') }}</p>
        <p class="mt-0.5 text-[11px] text-white/45">{{ t('owner_cabinet_home.today') }}</p>
        <p class="mt-3 text-4xl font-black tabular-nums leading-none text-white">
          {{ joinsToday >= 0 ? `+${joinsToday}` : joinsToday }}
        </p>
        <p class="mt-1 text-[11px] text-white/55">{{ t('owner_cabinet_home.joined_label') }}</p>
        <div class="pointer-events-none absolute bottom-2.5 right-2.5 opacity-95">
          <NavIcon name="chart-bar" class="h-9 w-9 text-violet-300/95 drop-shadow-[0_0_12px_rgba(167,139,250,0.35)]" />
        </div>
      </button>

      <!-- Обновления -->
      <button
        type="button"
        class="relative flex h-full w-full flex-col items-start justify-start overflow-hidden rounded-2xl border border-sky-500/30 bg-gradient-to-br from-sky-950/75 via-blue-950/40 to-slate-950/90 p-3.5 pb-11 text-left shadow-[0_0_26px_-14px_rgba(14,165,233,0.45)] ring-1 ring-white/[0.05] transition hover:brightness-105 active:scale-[0.99]"
        @click="open('updates')"
      >
        <p class="text-[13px] font-bold leading-tight text-white">{{ t('owner_cabinet_home.updates_heading') }}</p>
        <p class="mt-1.5 text-[11px] leading-snug text-sky-100/75">{{ t('owner_cabinet_home.updates_sub') }}</p>
        <div class="pointer-events-none absolute bottom-2.5 right-2.5 opacity-95">
          <NavIcon name="bolt" class="h-8 w-8 text-sky-300 drop-shadow-[0_0_14px_rgba(56,189,248,0.45)]" />
        </div>
      </button>

      <!-- Партнёрство -->
      <button
        type="button"
        class="relative flex h-full w-full flex-col items-start justify-start overflow-hidden rounded-2xl border border-amber-500/35 bg-gradient-to-br from-amber-950/80 via-orange-950/45 to-slate-950/90 p-3.5 pb-11 text-left shadow-[0_0_26px_-14px_rgba(245,158,11,0.4)] ring-1 ring-white/[0.05] transition hover:brightness-105 active:scale-[0.99]"
        @click="open('partner')"
      >
        <p class="text-[13px] font-bold leading-tight text-white">{{ t('owner_cabinet_home.partner_heading') }}</p>
        <p class="mt-1.5 text-[11px] leading-snug text-amber-100/75">{{ t('owner_cabinet_home.partner_sub') }}</p>
        <p v-if="referralPaidCount != null" class="mt-2 text-xl font-extrabold text-amber-100">{{ referralPaidCount }} {{ t('owner_cabinet_home.paying_suffix') }}</p>
        <div class="pointer-events-none absolute bottom-2.5 right-2.5 opacity-95">
          <NavIcon name="users" class="h-8 w-8 text-amber-300/95 drop-shadow-[0_0_12px_rgba(251,191,36,0.35)]" />
        </div>
      </button>

      <!-- Рассылки -->
      <button
        type="button"
        class="relative flex h-full w-full flex-col items-start justify-start overflow-hidden rounded-2xl border border-fuchsia-500/35 bg-gradient-to-br from-fuchsia-950/80 via-purple-950/45 to-slate-950/90 p-3.5 pb-11 text-left shadow-[0_0_26px_-14px_rgba(217,70,239,0.45)] ring-1 ring-white/[0.05] transition hover:brightness-105 active:scale-[0.99]"
        @click="open('broadcasts')"
      >
        <span v-if="showPremiumUpsellBadge" :class="premiumCornerBadgeClass">
          <span class="text-[10px]" aria-hidden="true">👑</span> {{ t('owner_cabinet_home.premium_badge') }}
        </span>
        <p class="text-[13px] font-bold leading-tight text-white">{{ t('owner_cabinet_home.broadcasts_heading') }}</p>
        <p class="mt-1.5 text-[11px] leading-snug text-fuchsia-100/75">{{ t('owner_cabinet_home.broadcasts_sub') }}</p>
        <p v-if="broadcastSpendTokens != null" class="mt-2 text-lg font-extrabold text-fuchsia-100">{{ Number(broadcastSpendTokens || 0) }} ⚡</p>
        <div class="pointer-events-none absolute bottom-2.5 right-2.5 opacity-95">
          <NavIcon name="send" class="h-8 w-8 text-fuchsia-300/95 drop-shadow-[0_0_12px_rgba(232,121,249,0.35)]" />
        </div>
      </button>

      <!-- Настройки -->
      <button
        type="button"
        class="relative flex h-full w-full flex-col items-start justify-start overflow-hidden rounded-2xl border border-cyan-500/30 bg-gradient-to-br from-cyan-950/75 via-teal-950/40 to-slate-950/90 p-3.5 pb-11 text-left shadow-[0_0_26px_-14px_rgba(34,211,238,0.4)] ring-1 ring-white/[0.05] transition hover:brightness-105 active:scale-[0.99]"
        @click="open('settings')"
      >
        <p class="text-[13px] font-bold leading-tight text-white">{{ t('owner_cabinet_home.settings_heading') }}</p>
        <p class="mt-1.5 text-[11px] leading-snug text-cyan-100/75">{{ t('owner_cabinet_home.settings_sub') }}</p>
        <div class="pointer-events-none absolute bottom-2.5 right-2.5 opacity-95">
          <NavIcon name="settings" class="h-8 w-8 text-cyan-300/95 drop-shadow-[0_0_12px_rgba(103,232,249,0.35)]" />
        </div>
      </button>
    </div>
  </div>
</template>

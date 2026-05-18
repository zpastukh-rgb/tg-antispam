<script setup>
/**
 * Тот же блок статистики, что на главной (Dashboard): актуальная «новая» вёрстка,
 * данные — тот же объект из GET activitySummary() (в ADM это plActivitySummary).
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import NavIcon from './NavIcon.vue'

const { t, locale } = useI18n()

const props = defineProps({
  summary: { type: Object, default: () => ({}) },
  /** как me из /api/me — aurum_tokens, tariff и т.д. */
  profile: { type: Object, default: () => ({}) },
})

const router = useRouter()

const protCheckGradId = `prot-ok-${Math.random().toString(36).slice(2, 11)}`
const protOffGradId = `prot-off-${Math.random().toString(36).slice(2, 11)}`

const activitySummary = computed(() => props.summary || {})

const tariffIsPremium = computed(() =>
  ['premium', 'pro', 'business'].includes(String(activitySummary.value?.tariff || props.profile?.tariff || 'free').toLowerCase()),
)

const dashboardAvatarSrc = computed(() => {
  const base = import.meta.env.BASE_URL
  return tariffIsPremium.value ? `${base}premium-guard-emblem.png` : `${base}avatar-free.png`
})

const activityChatsCount = computed(() => Number(activitySummary.value?.chats_count || 0))
const activityProtectedGroupsCount = computed(() =>
  Math.max(0, Math.round(Number(activitySummary.value?.protected_groups_count ?? 0))),
)
const activityGroupsCount = computed(() =>
  Number((activitySummary.value?.groups_count ?? activitySummary.value?.chats_count) || 0),
)
const activityChannelsCount = computed(() => Number(activitySummary.value?.channels_count || 0))
const activityGroupsLimit = computed(() =>
  Number((activitySummary.value?.groups_limit ?? activitySummary.value?.group_limit ?? activitySummary.value?.chat_limit) || 0),
)
const activityChannelsLimit = computed(() =>
  Number((activitySummary.value?.channels_limit ?? activitySummary.value?.channel_limit) || 0),
)
const activityGroupsProgress = computed(() =>
  Number((activitySummary.value?.groups_usage_progress ?? activitySummary.value?.usage_progress) || 0),
)
const activityChannelsProgress = computed(() => Number(activitySummary.value?.channels_usage_progress || 0))

const protectionStatusOk = computed(() => !!activitySummary.value?.protection_active)
const protectionStatusNoChats = computed(() => activityChatsCount.value === 0)

const dashboardEstimatedSavedRub = computed(() => {
  const d = Math.max(0, Math.round(Number(activitySummary.value?.today?.deleted || 0)))
  return d * 25
})

const dashboardProtectionLevelMeta = computed(() => {
  void locale.value
  const empty = {
    segments: 0,
    score: 0,
    label: '—',
    labelClass: 'text-white/45',
    fillSegmentClass: '',
  }
  const n = activityProtectedGroupsCount.value
  if (n <= 0) return empty

  const del = Math.max(0, Math.round(Number(activitySummary.value?.today?.deleted || 0)))
  const tariffCode = String(activitySummary.value?.tariff || 'free').toLowerCase()
  const premium = ['premium', 'pro', 'business'].includes(tariffCode)
  const protOn = !!activitySummary.value?.protection_active
  const usage = Math.max(0, Math.min(100, activityGroupsProgress.value))

  let score = 0
  score += premium ? 22 : 10
  score += protOn ? 38 : 8
  score += Math.min(18, Math.round(n * 3))
  score += Math.min(14, Math.round(del * 0.35))
  score += Math.min(8, Math.round(usage / 12))

  const s = Math.max(0, Math.min(100, Math.round(score)))

  let segments = 1
  if (s >= 72) segments = 4
  else if (s >= 48) segments = 3
  else if (s >= 24) segments = 2

  const tiers = {
    1: {
      label: t('cabinet_stats.hero.tier_weak'),
      fillSegmentClass: 'bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.35)]',
      labelClass: 'text-rose-400',
    },
    2: {
      label: t('cabinet_stats.hero.tier_basic'),
      fillSegmentClass: 'bg-orange-500 shadow-[0_0_6px_rgba(249,115,22,0.32)]',
      labelClass: 'text-orange-400',
    },
    3: {
      label: t('cabinet_stats.hero.tier_medium'),
      fillSegmentClass: 'bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.38)]',
      labelClass: 'text-amber-300',
    },
    4: {
      label: t('cabinet_stats.hero.tier_strong'),
      fillSegmentClass: 'bg-lime-400 shadow-[0_0_6px_rgba(163,230,53,0.38)]',
      labelClass: 'text-lime-400',
    },
  }

  const meta = tiers[segments]
  return {
    segments,
    score: s,
    label: meta.label,
    labelClass: meta.labelClass,
    fillSegmentClass: meta.fillSegmentClass,
  }
})

function fmtRubInt(n) {
  const v = Math.max(0, Math.round(Number(n) || 0))
  const loc = String(locale.value || 'ru') === 'en' ? 'en-US' : 'ru-RU'
  try {
    return v.toLocaleString(loc)
  } catch {
    return String(v)
  }
}

function fmtAmount(v) {
  const n = Number(v || 0)
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}

function groupsProtectedLabel(count) {
  const n = Math.abs(Math.trunc(Number(count) || 0))
  if (String(locale.value || 'ru') === 'en') {
    return n === 1 ? t('cabinet_stats.hero.groups_one', { n }) : t('cabinet_stats.hero.groups_many', { n })
  }
  const k = n % 100
  const l = n % 10
  if (k > 10 && k < 20) return t('cabinet_stats.hero.groups_many', { n })
  if (l === 1) return t('cabinet_stats.hero.groups_one', { n })
  if (l >= 2 && l <= 4) return t('cabinet_stats.hero.groups_few', { n })
  return t('cabinet_stats.hero.groups_many', { n })
}

function goManageChats() {
  router.push({ path: '/chats' })
}
</script>

<template>
  <div class="relative w-full min-w-0 max-w-full pb-1 pt-0 text-slate-100">
    <div class="pb-1 pl-0 pr-2 pt-0 md:pb-1.5 md:pr-2.5">
      <div class="flex items-start gap-0">
        <div
          class="relative -mt-0.5 -ml-3 flex h-28 w-28 shrink-0 items-center justify-center self-start md:-ml-3.5"
          :class="!tariffIsPremium ? 'overflow-hidden' : ''"
        >
          <img
            :src="dashboardAvatarSrc"
            alt=""
            draggable="false"
            class="block h-28 w-28 max-h-[7rem] max-w-[7rem] object-contain object-top"
            :class="!tariffIsPremium ? 'origin-top scale-[1.07]' : ''"
            @dragstart.prevent
          >
        </div>
        <div class="flex min-h-0 min-w-0 flex-1 flex-col items-stretch pl-0.5 pt-0.5 sm:pl-1">
          <div class="flex flex-wrap items-center gap-0.5">
            <svg
              v-if="protectionStatusOk"
              class="h-3 w-3 shrink-0 [filter:drop-shadow(0_0_4px_rgba(163,230,53,0.45))]"
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden="true"
            >
              <defs>
                <linearGradient :id="protCheckGradId" x1="3" y1="4" x2="21" y2="20" gradientUnits="userSpaceOnUse">
                  <stop stop-color="#d9f99d" />
                  <stop offset="0.5" stop-color="#a3e635" />
                  <stop offset="1" stop-color="#4d7c0f" />
                </linearGradient>
              </defs>
              <circle cx="12" cy="12" r="12" :fill="`url(#${protCheckGradId})`" />
              <path d="M7 12l3 3 7-7" stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            <svg
              v-else-if="protectionStatusNoChats"
              class="h-3 w-3 shrink-0"
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden="true"
            >
              <defs>
                <linearGradient :id="protOffGradId" x1="3" y1="4" x2="21" y2="20" gradientUnits="userSpaceOnUse">
                  <stop stop-color="#fecdd3" />
                  <stop offset="0.5" stop-color="#fb7185" />
                  <stop offset="1" stop-color="#9f1239" />
                </linearGradient>
              </defs>
              <circle cx="12" cy="12" r="12" :fill="`url(#${protOffGradId})`" />
              <path d="M8 8l8 8M16 8L8 16" stroke="white" stroke-width="2.2" stroke-linecap="round" />
            </svg>
            <svg v-else class="h-3 w-3 shrink-0 text-amber-500/90" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle cx="12" cy="12" r="12" fill="currentColor" />
              <path d="M8 12h8" stroke="#0a0a0c" stroke-width="2.2" stroke-linecap="round" />
            </svg>
            <p
              class="text-[11px] font-extrabold leading-tight tracking-tight md:text-[12px]"
              :class="protectionStatusOk ? 'text-lime-400' : protectionStatusNoChats ? 'text-rose-400' : 'text-amber-400'"
            >
              <template v-if="protectionStatusOk">{{ t('cabinet_stats.hero.prot_ok') }}</template>
              <template v-else-if="protectionStatusNoChats">{{ t('cabinet_stats.hero.prot_no_chats') }}</template>
              <template v-else>{{ t('cabinet_stats.hero.prot_warn') }}</template>
            </p>
          </div>

          <div class="mt-2 w-full min-w-0 sm:mt-2.5">
            <div class="relative isolate px-2 py-2.5 sm:px-3 sm:py-3">
              <div
                aria-hidden="true"
                class="pointer-events-none absolute inset-0 rounded-xl bg-black/40 backdrop-blur-[7px]"
                style="
                  -webkit-mask-image: linear-gradient(90deg, transparent 0%, #000 12%, #000 88%, transparent 100%);
                  mask-image: linear-gradient(90deg, transparent 0%, #000 12%, #000 88%, transparent 100%);
                "
              />
              <div class="relative flex w-full min-w-0 items-stretch justify-between divide-x divide-white/[0.09]">
              <div class="flex min-w-0 flex-1 flex-col items-center px-1.5 text-center sm:px-2">
                <p class="w-full text-[9px] font-semibold uppercase tracking-wide text-white sm:text-[10px]">{{ t('cabinet_stats.hero.col_deleted') }}</p>
                <p class="mt-0.5 w-full text-[16px] font-extrabold tabular-nums leading-none text-white sm:text-[17px]">
                  {{ activitySummary?.today?.deleted ?? 0 }}
                </p>
                <p class="mt-0.5 w-full text-[10px] font-medium leading-tight text-lime-400/95 sm:text-[11px]">{{ t('cabinet_stats.hero.col_messages') }}</p>
              </div>
              <div class="flex min-w-0 flex-1 flex-col items-center px-1.5 text-center sm:px-2">
                <p class="w-full text-[9px] font-semibold uppercase tracking-wide text-white sm:text-[10px]">{{ t('cabinet_stats.hero.col_saved') }}</p>
                <p class="mt-0.5 w-full whitespace-nowrap text-center text-[13px] font-extrabold tabular-nums leading-none text-white sm:text-[14px]">
                  ~ {{ fmtRubInt(dashboardEstimatedSavedRub) }} ₽
                </p>
                <p class="mt-0.5 w-full text-[10px] font-medium leading-tight text-lime-400/95 sm:text-[11px]">{{ t('cabinet_stats.hero.col_for_admins') }}</p>
              </div>
              <div class="flex min-w-0 flex-1 flex-col items-center px-1.5 text-center sm:px-2">
                <p class="w-full whitespace-nowrap text-[9px] font-semibold uppercase leading-tight tracking-wide text-white sm:text-[10px]">
                  {{ t('cabinet_stats.hero.col_level') }}
                </p>
                <div class="mt-0.5 flex w-full min-w-0 flex-col items-stretch gap-1">
                  <p
                    class="text-center text-[14px] font-extrabold leading-tight sm:text-[15px]"
                    :class="dashboardProtectionLevelMeta.labelClass"
                  >
                    {{ dashboardProtectionLevelMeta.label }}
                  </p>
                  <div
                    class="flex h-1 w-full min-w-0 gap-1"
                    :title="t('cabinet_stats.hero.score_title', { score: dashboardProtectionLevelMeta.score ?? '—' })"
                  >
                    <span
                      v-for="seg in 4"
                      :key="`prot-seg-${seg}`"
                      class="min-h-[4px] min-w-0 flex-1 rounded-[2px]"
                      :class="
                        seg <= dashboardProtectionLevelMeta.segments && dashboardProtectionLevelMeta.fillSegmentClass
                          ? dashboardProtectionLevelMeta.fillSegmentClass
                          : 'bg-zinc-600/85'
                      "
                    />
                  </div>
                </div>
              </div>
              </div>
            </div>
          </div>

          <button
            type="button"
            class="mt-2 flex w-full items-center gap-1.5 rounded-lg bg-zinc-900/80 px-2 py-1 text-left transition hover:bg-zinc-800/80 active:bg-zinc-800/90 sm:mt-2.5 sm:py-1.5"
            @click="goManageChats"
          >
            <span class="grid h-5 w-5 shrink-0 place-items-center rounded-md bg-lime-500/15 text-lime-300">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
            </span>
            <span class="min-w-0 flex-1 text-[11px] font-semibold leading-tight text-white sm:text-[12px]">
              {{ t('cabinet_stats.hero.protected_today') }} <span class="text-lime-400">{{ groupsProtectedLabel(activityProtectedGroupsCount) }}</span>
            </span>
            <span class="shrink-0 text-sm font-light text-white/40" aria-hidden="true">›</span>
          </button>
        </div>
      </div>
    </div>

    <div class="mt-1 grid min-w-0 grid-cols-[minmax(0,40%)_minmax(0,60%)] gap-1.5 md:grid-cols-[minmax(0,38%)_minmax(0,62%)] md:gap-2">
      <div class="relative min-w-0 rounded-xl border border-amber-400/15 bg-gradient-to-b from-black/45 to-zinc-950/90 px-1 pb-0.5 pt-1 shadow-[0_10px_36px_-18px_rgba(0,0,0,0.65)] backdrop-blur-md md:px-1.5">
        <div class="flex items-start justify-between gap-1.5">
          <div class="min-w-0">
            <p class="flex items-center gap-0.5 text-[8px] font-bold uppercase tracking-wide text-amber-200/90">
              <span aria-hidden="true">⚡</span> {{ t('cabinet_stats.hero.aurum_heading') }}
            </p>
            <p class="mt-0.5 flex items-baseline gap-0.5 text-[18px] font-extrabold tabular-nums leading-none text-white">
              {{ fmtAmount(profile?.aurum_tokens || 0) }}
              <span class="text-sm">✨</span>
            </p>
            <p class="mt-0.5 text-[9px] text-white/45">{{ t('cabinet_stats.hero.balance_label') }}</p>
          </div>
          <div class="relative grid h-9 w-9 shrink-0 place-items-center">
            <span class="absolute inset-0 rounded-full border border-lime-400/25" />
            <span class="absolute inset-[3px] rounded-full border border-lime-400/15" />
            <NavIcon name="bolt" class="relative h-4 w-4 text-lime-400 drop-shadow-[0_0_8px_rgba(163,230,53,0.4)]" />
          </div>
        </div>
        <div class="mt-1 grid grid-cols-2 gap-0.5">
          <button
            type="button"
            class="flex min-w-0 items-center justify-center gap-0.5 rounded-md bg-gradient-to-b from-lime-400 to-lime-600 px-1 py-1.5 text-[9px] font-bold leading-tight text-lime-950 shadow-[0_3px_10px_rgba(132,204,22,0.3)] transition hover:brightness-105 sm:text-[10px]"
            @click="router.push({ path: '/tokens' })"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <circle cx="9" cy="21" r="1" /><circle cx="20" cy="21" r="1" />
              <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
            </svg>
            {{ t('cabinet_stats.hero.buy') }}
          </button>
          <button
            type="button"
            class="flex min-w-0 items-center justify-center gap-0.5 rounded-md border border-white/15 bg-white/[0.06] px-1 py-1.5 text-[9px] font-semibold leading-tight text-white/90 transition hover:bg-white/10 sm:text-[10px]"
            @click="router.push({ path: '/history' })"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 6v6l4 2" />
            </svg>
            {{ t('cabinet_stats.hero.history') }}
          </button>
        </div>
      </div>

      <div class="relative min-w-0 rounded-xl bg-gradient-to-b from-black/40 to-zinc-950/90 px-1.5 pb-0.5 pt-1 shadow-[0_10px_36px_-18px_rgba(0,0,0,0.65)] backdrop-blur-md md:pl-2 md:pr-2">
        <p class="mb-0.5 flex items-center gap-1 text-[8px] font-bold uppercase tracking-wide text-white/85">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-sky-300/90" aria-hidden="true">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          {{ t('cabinet_stats.hero.your_chats') }}
        </p>
        <div class="space-y-1.5">
          <div class="flex min-w-0 items-center gap-1.5">
            <span class="flex h-5 w-5 shrink-0 items-center justify-center" aria-hidden="true">
              <svg
                class="h-[18px] w-[18px] text-lime-300 [filter:drop-shadow(0_0_8px_rgba(132,204,22,0.85))]"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.2"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
              </svg>
            </span>
            <span class="shrink-0 whitespace-nowrap text-[10px] font-semibold leading-tight text-lime-200">
              {{ t('cabinet_stats.hero.groups') }}
              <span class="ml-0.5 tabular-nums font-medium text-white/90">
                {{ activityGroupsCount }} / {{ activityGroupsLimit }}
              </span>
            </span>
            <div class="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-white/10">
              <div
                class="h-full rounded-full bg-gradient-to-r from-lime-400 to-emerald-600 transition-all"
                :style="{ width: `${Math.max(0, Math.min(100, Number(activityGroupsProgress || 0)))}%` }"
              />
            </div>
            <button
              type="button"
              class="grid h-4 w-4 shrink-0 place-items-center rounded-md border border-lime-300/35 bg-gradient-to-b from-lime-400 to-lime-600 text-[10px] font-bold leading-none text-lime-950 shadow-[0_0_10px_rgba(132,204,22,0.45)]"
              :aria-label="t('cabinet_stats.hero.aria_connect_group')"
              @click="router.push({ path: '/connect', query: { kind: 'group' } })"
            >
              +
            </button>
          </div>

          <div class="flex min-w-0 items-center gap-1.5">
            <span class="flex h-5 w-5 shrink-0 items-center justify-center" aria-hidden="true">
              <svg
                class="h-5 w-5 text-cyan-300 [filter:drop-shadow(0_0_10px_rgba(34,211,238,0.95))]"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M11 5L6 9H2v6h4l5 4V5z" />
                <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
              </svg>
            </span>
            <span class="shrink-0 whitespace-nowrap text-[10px] font-semibold leading-tight text-white/95">
              {{ t('cabinet_stats.hero.channels') }}
              <span class="ml-0.5 tabular-nums font-medium text-white/90">
                {{ activityChannelsCount }} / {{ activityChannelsLimit }}
              </span>
            </span>
            <div class="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-white/10">
              <div
                class="h-full rounded-full bg-gradient-to-r from-amber-400 to-orange-600 transition-all"
                :style="{ width: `${Math.max(0, Math.min(100, Number(activityChannelsProgress || 0)))}%` }"
              />
            </div>
            <button
              type="button"
              class="grid h-4 w-4 shrink-0 place-items-center rounded-md border border-amber-300/40 bg-gradient-to-b from-amber-400 to-amber-600 text-[10px] font-bold leading-none text-amber-950 shadow-[0_0_10px_rgba(251,191,36,0.4)]"
              :aria-label="t('cabinet_stats.hero.aria_connect_channel')"
              @click="router.push({ path: '/connect', query: { kind: 'channel' } })"
            >
              +
            </button>
          </div>
        </div>
        <button
          type="button"
          class="mt-1 flex w-full items-center justify-center gap-0.5 rounded-lg bg-black/30 py-1 text-[10px] font-semibold text-white/90 transition hover:bg-black/45"
          @click="goManageChats"
        >
          {{ t('cabinet_stats.hero.manage') }}
          <span class="text-white/40">›</span>
        </button>
      </div>
    </div>
  </div>
</template>

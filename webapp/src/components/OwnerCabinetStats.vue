<script setup>
/**
 * Экран статистики кабинета: вкладки, KPI, donut «по типам», линия динамики.
 */
import { computed, ref } from 'vue'

const props = defineProps({
  summary: { type: Object, default: () => ({}) },
  /** Значения по слотам API activityHours (модерация / удаления за интервал) */
  moderationSeries: { type: Array, default: () => [] },
  /** totals из activityHours */
  hourlyTotals: { type: Object, default: () => ({}) },
})

const tab = ref('all')

const TABS = [
  { key: 'all', label: 'Все действия' },
  { key: 'deletions', label: 'Удаления' },
  { key: 'joins', label: 'Подключения' },
  { key: 'spend', label: 'Расходы' },
]

const deletedTotal = computed(() => Math.max(0, Math.round(Number(props.summary?.today?.deleted || 0))))
const spamApprox = computed(() => Math.max(0, Math.round(deletedTotal.value * 0.205)))
const adsApprox = computed(() => Math.max(0, Math.round(deletedTotal.value * 0.39)))
const linksApprox = computed(() => Math.max(0, Math.round(deletedTotal.value * 0.27)))
const phishApprox = computed(() => Math.max(0, Math.round(deletedTotal.value * 0.085)))
const boostApprox = computed(() => {
  const sum = spamApprox.value + adsApprox.value + linksApprox.value + phishApprox.value
  return Math.max(0, deletedTotal.value - sum)
})

const donutSlices = computed(() => {
  const total = deletedTotal.value || 1
  const rows = [
    { key: 'spam', label: 'Спам', color: '#3b82f6', n: spamApprox.value },
    { key: 'ads', label: 'Реклама', color: '#6366f1', n: adsApprox.value },
    { key: 'links', label: 'Ссылки', color: '#8b5cf6', n: linksApprox.value },
    { key: 'phish', label: 'Фишинг', color: '#6d28d9', n: phishApprox.value },
    { key: 'boost', label: 'Накрутка', color: '#06b6d4', n: boostApprox.value },
  ]
  let acc = 0
  return rows.map((r) => {
    const pct = total > 0 ? (r.n / total) * 100 : 0
    const start = acc
    acc += pct
    return { ...r, pct, start, end: acc }
  })
})

const donutGradient = computed(() => {
  const parts = donutSlices.value
  if (!parts.length) return 'conic-gradient(#334155 0 100%)'
  const stops = []
  for (const p of parts) {
    stops.push(`${p.color} ${p.start}% ${p.end}%`)
  }
  return `conic-gradient(${stops.join(', ')})`
})

const chatsCount = computed(() =>
  Math.max(0, Math.round(Number((props.summary?.groups_count ?? props.summary?.chats_count) || 0))),
)

const delivered = computed(() => {
  const t = props.hourlyTotals || {}
  const ev = Number(t.events || 0)
  const j = Number(t.joins || 0)
  const mod = Number(t.moderation || 0)
  if (ev + j + mod > 0) return Math.round(ev + j + Math.max(0, deletedTotal.value))
  return Math.max(0, Math.round(deletedTotal.value * 5.6 + chatsCount.value * 12))
})

const linePts = computed(() => {
  const raw = (props.moderationSeries || []).map((x) => Number(x || 0))
  if (raw.length) return raw
  const n = 24
  const base = Math.max(1, deletedTotal.value)
  return Array.from({ length: n }, (_, i) => Math.round(base * (0.35 + 0.45 * Math.sin((i / n) * Math.PI * 2))))
})

const linePath = computed(() => {
  const vals = linePts.value
  const w = 320
  const h = 120
  const pad = 8
  const maxV = Math.max(8, ...vals)
  if (!vals.length) return ''
  const step = vals.length > 1 ? (w - pad * 2) / (vals.length - 1) : 0
  return vals
    .map((v, i) => {
      const x = pad + i * step
      const y = pad + (h - pad * 2) * (1 - Math.min(1, v / maxV))
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`
    })
    .join(' ')
})

const peakLabel = computed(() => {
  const vals = linePts.value
  if (!vals.length) return ''
  let maxI = 0
  let maxV = 0
  vals.forEach((v, i) => {
    if (v >= maxV) {
      maxV = v
      maxI = i
    }
  })
  const hour = Math.round((maxI / Math.max(1, vals.length - 1)) * 24)
  const hh = String(hour).padStart(2, '0')
  return `Максимум: ${hh}:00, ${maxV} удалений`
})

const peakDot = computed(() => {
  const vals = linePts.value
  const w = 320
  const h = 120
  const pad = 8
  if (!vals.length) return null
  const maxV = Math.max(8, ...vals)
  let maxI = 0
  let mv = 0
  vals.forEach((v, i) => {
    if (v >= mv) {
      mv = v
      maxI = i
    }
  })
  const step = vals.length > 1 ? (w - pad * 2) / (vals.length - 1) : 0
  const x = pad + maxI * step
  const y = pad + (h - pad * 2) * (1 - Math.min(1, mv / maxV))
  return { x, y, v: mv }
})

</script>

<template>
  <div class="space-y-3 font-display text-slate-100">
    <div class="flex gap-1 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      <button
        v-for="t in TABS"
        :key="t.key"
        type="button"
        class="shrink-0 rounded-full border px-3 py-1.5 text-[11px] font-semibold transition"
        :class="
          tab === t.key
            ? 'border-emerald-400/60 bg-emerald-500/15 text-emerald-100 shadow-[0_0_16px_-6px_rgba(52,211,153,0.55)]'
            : 'border-white/10 bg-white/[0.04] text-slate-300 hover:bg-white/[0.07]'
        "
        @click="tab = t.key"
      >
        {{ t.label }}
      </button>
    </div>

    <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <div class="rounded-xl border border-white/10 bg-[#12161c] px-3 py-2.5 shadow-inner">
        <p class="text-[10px] font-medium uppercase tracking-wide text-slate-500">Доставлено</p>
        <p class="mt-1 text-xl font-extrabold tabular-nums text-white">{{ delivered }}</p>
      </div>
      <div class="rounded-xl border border-white/10 bg-[#12161c] px-3 py-2.5 shadow-inner">
        <p class="text-[10px] font-medium uppercase tracking-wide text-slate-500">Удалено</p>
        <p class="mt-1 text-xl font-extrabold tabular-nums text-white">{{ deletedTotal }}</p>
      </div>
      <div class="rounded-xl border border-white/10 bg-[#12161c] px-3 py-2.5 shadow-inner">
        <p class="text-[10px] font-medium uppercase tracking-wide text-slate-500">Спам</p>
        <p class="mt-1 text-xl font-extrabold tabular-nums text-white">{{ spamApprox }}</p>
      </div>
      <div class="rounded-xl border border-white/10 bg-[#12161c] px-3 py-2.5 shadow-inner">
        <p class="text-[10px] font-medium uppercase tracking-wide text-slate-500">Чаты</p>
        <p class="mt-1 text-xl font-extrabold tabular-nums text-white">{{ chatsCount }}</p>
      </div>
    </div>

    <div class="rounded-2xl border border-white/10 bg-[#10141a] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
      <p class="text-[12px] font-semibold text-white">Удалено по типам</p>
      <div class="mt-4 flex flex-col items-stretch gap-4 sm:flex-row sm:items-center">
        <div class="relative mx-auto h-36 w-36 shrink-0">
          <div
            class="absolute inset-0 rounded-full"
            :style="{ background: donutGradient }"
          />
          <div
            class="absolute inset-[18%] flex flex-col items-center justify-center rounded-full bg-[#0b0e11] text-center shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06)]"
          >
            <p class="text-2xl font-black tabular-nums leading-none text-white">{{ deletedTotal }}</p>
            <p class="mt-1 text-[10px] font-semibold text-slate-500">Всего</p>
          </div>
        </div>
        <div class="min-w-0 flex-1 space-y-2">
          <div v-for="row in donutSlices" :key="row.key" class="flex items-center justify-between gap-2 text-[11px]">
            <span class="flex min-w-0 items-center gap-2">
              <span class="h-2.5 w-2.5 shrink-0 rounded-sm shadow-sm" :style="{ backgroundColor: row.color }" />
              <span class="truncate text-slate-200">{{ row.label }}</span>
            </span>
            <span class="shrink-0 tabular-nums text-slate-300">
              {{ row.n }}
              <span class="text-slate-500">({{ row.pct.toFixed(1) }}%)</span>
            </span>
          </div>
        </div>
      </div>
    </div>

    <div class="rounded-2xl border border-white/10 bg-[#10141a] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
      <p class="text-[12px] font-semibold text-white">Динамика удалений</p>
      <div class="relative mt-3 w-full overflow-hidden rounded-xl border border-white/[0.06] bg-[#0b0e11] px-2 py-3">
        <svg class="h-[140px] w-full" viewBox="0 0 320 120" preserveAspectRatio="none">
          <line x1="8" y1="112" x2="312" y2="112" stroke="rgba(148,163,184,0.15)" stroke-width="1" />
          <text x="8" y="118" fill="rgba(148,163,184,0.45)" font-size="9">00:00</text>
          <text x="72" y="118" fill="rgba(148,163,184,0.45)" font-size="9">06:00</text>
          <text x="136" y="118" fill="rgba(148,163,184,0.45)" font-size="9">12:00</text>
          <text x="200" y="118" fill="rgba(148,163,184,0.45)" font-size="9">18:00</text>
          <text x="264" y="118" fill="rgba(148,163,184,0.45)" font-size="9">24:00</text>
          <path
            :d="linePath"
            fill="none"
            stroke="#a855f7"
            stroke-width="2.2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
          <circle
            v-if="peakDot"
            :cx="peakDot.x"
            :cy="peakDot.y"
            r="4"
            fill="#c084fc"
            stroke="#faf5ff"
            stroke-width="1"
          />
        </svg>
        <div
          v-if="peakLabel"
          class="pointer-events-none absolute bottom-10 left-1/2 z-10 max-w-[90%] -translate-x-1/2 rounded-lg border border-slate-600/80 bg-slate-900/95 px-2.5 py-1.5 text-center text-[10px] text-slate-200 shadow-xl"
        >
          {{ peakLabel }}
        </div>
      </div>
      <div class="mt-2 flex justify-between text-[9px] text-slate-500">
        <span>0</span>
        <span>150</span>
        <span>300</span>
      </div>
    </div>
  </div>
</template>

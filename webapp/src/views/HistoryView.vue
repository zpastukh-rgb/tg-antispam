<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useApi } from '../composables/useApi'
import {
  formatHistoryDateTime,
  mergePaymentHistoryRows,
  paymentProviderLabel,
  paymentStatusLabel,
  tokenReasonLabel,
} from '../utils/historyLabels.js'

const { t } = useI18n()
const { api, fetchSilent, hasInitData } = useApi()
const tab = ref('payments')
const loading = ref(false)
const payments = ref([])
const tokens = ref([])

const isEn = computed(() => t('common.locale_code') === 'en')

function fmtAmount(v) {
  const n = Number(v || 0)
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}

function fmtDate(iso) {
  return formatHistoryDateTime(iso, isEn.value)
}

function fmtProvider(item) {
  return paymentProviderLabel(item, t)
}

function fmtStatus(status) {
  return paymentStatusLabel(status, t)
}

function fmtReason(reason) {
  return tokenReasonLabel(reason, t)
}

function paymentTitle(item) {
  if (String(item?.kind || '').toLowerCase() === 'promo' || String(item?.provider || '').toLowerCase() === 'promo') {
    const parts = []
    const days = Number(item?.period_days || 0)
    const months = Number(item?.months || 0)
    if (days > 0) parts.push(t('history.promo_period_days', { n: days }))
    else if (months > 0) parts.push(isEn.value ? `${months} mo` : `${months} мес.`)
    const ga = Number(item?.grant_aurum || 0)
    const gt = Number(item?.grant_tokens || 0)
    if (ga > 0) parts.push(`${fmtAmount(ga)} AURUM ✨`)
    if (gt > 0) parts.push(`${fmtAmount(gt)} ⚡`)
    return parts.length ? parts.join(' · ') : t('billing.method.promo')
  }
  if (String(item?.tariff || '').toLowerCase() === 'tokens') {
    return `${fmtAmount(item.amount_rub)} ${isEn.value ? 'RUB' : '₽'} · ${item.months} ⚡`
  }
  return `${fmtAmount(item.amount_rub)} ${isEn.value ? 'RUB' : '₽'} · ${isEn.value ? `${item.months} mo` : `${item.months} мес.`}`
}

async function loadAll() {
  if (!hasInitData.value) return
  loading.value = true
  try {
    const [p, tk, sub] = await Promise.all([
      fetchSilent(() => api.historyPayments()),
      fetchSilent(() => api.historyTokens()),
      fetchSilent(() => api.historySubscription()).catch(() => ({ items: [] })),
    ])
    payments.value = mergePaymentHistoryRows(p?.items, sub?.items)
    tokens.value = tk?.items || []
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)
</script>

<template>
  <div class="space-y-3">
    <div class="rounded-2xl border border-slate-200 bg-white p-3 dark:border-white/[0.07] dark:bg-[#050608]">
      <div class="grid grid-cols-2 gap-2">
        <button
          type="button"
          class="rounded-xl px-3 py-2 text-sm font-semibold"
          :class="
            tab === 'payments'
              ? 'bg-sky-100 text-sky-800 dark:bg-[#12151c] dark:text-white dark:ring-1 dark:ring-white/[0.08]'
              : 'bg-slate-100 text-slate-600 dark:bg-black/55 dark:text-white/42 dark:ring-1 dark:ring-inset dark:ring-white/[0.05]'
          "
          @click="tab = 'payments'"
        >
          {{ isEn ? 'Payment history' : 'История платежей' }}
        </button>
        <button
          type="button"
          class="rounded-xl px-3 py-2 text-sm font-semibold"
          :class="
            tab === 'tokens'
              ? 'bg-sky-100 text-sky-800 dark:bg-[#12151c] dark:text-white dark:ring-1 dark:ring-white/[0.08]'
              : 'bg-slate-100 text-slate-600 dark:bg-black/55 dark:text-white/42 dark:ring-1 dark:ring-inset dark:ring-white/[0.05]'
          "
          @click="tab = 'tokens'"
        >
          {{ isEn ? 'AURUM / tokens history' : 'История AURUM/токенов' }}
        </button>
      </div>

      <div v-if="loading" class="py-8 text-center text-sm text-slate-500 dark:text-white/40">{{ t('loading.generic') }}</div>

      <div v-else-if="tab === 'payments'" class="mt-3 space-y-2">
        <div
          v-if="payments.length === 0"
          class="rounded-xl bg-slate-50 p-4 text-center text-sm text-slate-500 dark:bg-[#0a0c12] dark:text-white/45 dark:ring-1 dark:ring-white/[0.05]"
        >
          {{ isEn ? 'No payments yet.' : 'Платежей пока нет.' }}
        </div>
        <div v-for="(item, idx) in payments" :key="'p-' + idx" class="rounded-xl border border-slate-200 p-3 dark:border-white/[0.06] dark:bg-[#080a10]">
          <p class="text-xs text-slate-500 dark:text-white/42">{{ fmtDate(item.created_at) }}</p>
          <p class="mt-1 text-sm font-semibold text-slate-900 dark:text-white">
            {{ paymentTitle(item) }}
          </p>
          <p class="mt-0.5 text-xs text-slate-500 dark:text-white/42">
            {{ fmtProvider(item) }} · {{ fmtStatus(item.status) }}
          </p>
        </div>
      </div>

      <div v-else class="mt-3 space-y-2">
        <div
          v-if="tokens.length === 0"
          class="rounded-xl bg-slate-50 p-4 text-center text-sm text-slate-500 dark:bg-[#0a0c12] dark:text-white/45 dark:ring-1 dark:ring-white/[0.05]"
        >
          {{ isEn ? 'No AURUM / token movements yet.' : 'Движений AURUM/токенов пока нет.' }}
        </div>
        <div v-for="(item, idx) in tokens" :key="'t-' + idx" class="rounded-xl border border-slate-200 p-3 dark:border-white/[0.06] dark:bg-[#080a10]">
          <p class="text-xs text-slate-500 dark:text-white/42">{{ fmtDate(item.created_at) }}</p>
          <p class="mt-1 text-sm font-semibold" :class="item.delta >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'">
            {{ item.delta >= 0 ? '+' : '' }}{{ fmtAmount(item.delta) }} ⚡
          </p>
          <p class="text-xs text-slate-500 dark:text-white/42">{{ fmtReason(item.reason) }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

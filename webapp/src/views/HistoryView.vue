<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useApi } from '../composables/useApi'
import { formatDateTimeRu } from '../utils/formatDateTime'

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

async function loadAll() {
  if (!hasInitData.value) return
  loading.value = true
  try {
    const [p, tk] = await Promise.all([
      fetchSilent(() => api.historyPayments()),
      fetchSilent(() => api.historyTokens()),
    ])
    payments.value = p?.items || []
    tokens.value = tk?.items || []
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)
</script>

<template>
  <div class="space-y-3">
    <div class="rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
      <div class="grid grid-cols-2 gap-2">
        <button
          type="button"
          class="rounded-xl px-3 py-2 text-sm font-semibold"
          :class="tab === 'payments' ? 'bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-200' : 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300'"
          @click="tab = 'payments'"
        >
          {{ isEn ? 'Payment history' : 'История платежей' }}
        </button>
        <button
          type="button"
          class="rounded-xl px-3 py-2 text-sm font-semibold"
          :class="tab === 'tokens' ? 'bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-200' : 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300'"
          @click="tab = 'tokens'"
        >
          {{ isEn ? 'AURUM / tokens history' : 'История AURUM/токенов' }}
        </button>
      </div>

      <div v-if="loading" class="py-8 text-center text-sm text-slate-500 dark:text-slate-400">{{ t('loading.generic') }}</div>

      <div v-else-if="tab === 'payments'" class="mt-3 space-y-2">
        <div v-if="payments.length === 0" class="rounded-xl bg-slate-50 p-4 text-center text-sm text-slate-500 dark:bg-slate-700/40 dark:text-slate-400">
          {{ isEn ? 'No payments yet.' : 'Платежей пока нет.' }}
        </div>
        <div v-for="(item, idx) in payments" :key="`p-${idx}`" class="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
          <p class="text-xs text-slate-500 dark:text-slate-400">{{ formatDateTimeRu(item.created_at) }}</p>
          <p class="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">
            {{ fmtAmount(item.amount_rub) }} {{ isEn ? 'RUB' : '₽' }} · {{ item.months }} {{ isEn ? 'mo' : 'мес.' }} · {{ item.status }}
          </p>
        </div>
      </div>

      <div v-else class="mt-3 space-y-2">
        <div v-if="tokens.length === 0" class="rounded-xl bg-slate-50 p-4 text-center text-sm text-slate-500 dark:bg-slate-700/40 dark:text-slate-400">
          {{ isEn ? 'No AURUM / token movements yet.' : 'Движений AURUM/токенов пока нет.' }}
        </div>
        <div v-for="(item, idx) in tokens" :key="`t-${idx}`" class="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
          <p class="text-xs text-slate-500 dark:text-slate-400">{{ formatDateTimeRu(item.created_at) }}</p>
          <p class="mt-1 text-sm font-semibold" :class="item.delta >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'">
            {{ item.delta >= 0 ? '+' : '' }}{{ fmtAmount(item.delta) }} ⚡
          </p>
          <p class="text-xs text-slate-500 dark:text-slate-400">{{ item.reason }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useApi } from '../composables/useApi'
import { useToast } from '../composables/useToast'
import { api as rawApi } from '../api/client'
import { formatDateRu, formatDateTimeRu } from '../utils/formatDateTime'

const { t } = useI18n()

const props = defineProps({
  /** Объект /api/me */
  profile: { type: Object, default: null },
  /** page — главный экран мини-приложения; embedded — ADM (вкладка или модалка) */
  variant: { type: String, default: 'page' },
  /** Чужой аккаунт: только просмотр, без смены тарифа/автопродления */
  readOnly: { type: Boolean, default: false },
  /** Скрыть серую подсказку «данные по аккаунту…» (модалка просмотра юзера) */
  hideEmbeddedHint: { type: Boolean, default: false },
})

const useDarkShell = computed(() => props.variant === 'page')

const emit = defineEmits(['update:profile', 'open-tariff'])

const { fetchSilent } = useApi()
const { showToast } = useToast()
const autorenewToggleLoading = ref(false)
const subscriptionHistoryLoading = ref(false)
const subscriptionHistoryItems = ref([])
const subscriptionHistoryOpen = ref(false)
const subscriptionHistoryLoadedOnce = ref(false)

const isPremium = computed(() => !!props.profile?.is_premium)

const tariffRowLabel = computed(() => {
  const m = Number(props.profile?.subscription_paid_period_months || 0)
  if (m > 0) return _monthsLabel(m)
  const d = Number(props.profile?.subscription_paid_period_days || 0)
  if (d > 0) return _daysLabel(d)
  if (isPremium.value) return '—'
  return t('subscription.plan_free')
})

/** Первый успешный платёж за подписку (не дата последнего теста/докупа). */
const activationLabel = computed(() =>
  formatDateRu(props.profile?.subscription_activated_at || props.profile?.subscription_current_period_start_at),
)

const nextChargeLabel = computed(() => {
  if (!isPremium.value) return '—'
  return formatDateRu(props.profile?.subscription_until)
})

const nextChargeLabelLong = computed(() => {
  if (!isPremium.value) return '—'
  return formatDateTimeRu(props.profile?.subscription_until)
})

const paymentMethodLabel = computed(() => {
  if (!isPremium.value) {
    if (props.profile?.payment_method_bound) {
      const p = String(props.profile?.payment_method_type || '').toLowerCase()
      if (p.includes('card')) return t('billing.method.yookassa_card')
      if (p.includes('sbp')) return t('billing.method.yookassa_sbp')
      if (p.includes('yoo_money')) return t('billing.method.yookassa')
      if (p) return `${t('billing.method.yookassa')} (${p})`
    }
    return t('subscription.payment_method.none')
  }
  const source = String(props.profile?.subscription_source || '').toLowerCase()
  if (source === 'promo') return t('billing.method.promo')
  const p = String(props.profile?.payment_method_type || '').toLowerCase()
  if (p.includes('card')) return t('billing.method.yookassa_card')
  if (p.includes('sbp')) return t('billing.method.yookassa_sbp')
  if (p.includes('yoo_money')) return t('billing.method.yookassa')
  if (p) return `${t('billing.method.yookassa')} (${p})`
  return t('billing.method.yookassa')
})

const autorenewOn = computed(() => !!props.profile?.payment_method_bound)

/** iOS-стиль: кружок строго по вертикали (translate3d, без «кривого» top) */
const autorenewKnobStyle = computed(() => ({
  top: '50%',
  left: '2px',
  width: '22px',
  height: '22px',
  transform: `translate3d(${autorenewOn.value ? 16 : 0}px, -50%, 0)`,
  transition: 'transform 0.22s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.2s',
}))

function pushProfile(next) {
  emit('update:profile', next)
}

function _monthsLabel(months) {
  const n = Number(months || 0)
  if (n <= 0) return ''
  if (t('common.locale_code') === 'en') {
    return n === 1 ? `${n} month` : `${n} months`
  }
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod100 < 11 || mod100 > 14) {
    if (mod10 === 1) return `${n} месяц`
    if (mod10 >= 2 && mod10 <= 4) return `${n} месяца`
  }
  return `${n} месяцев`
}

function _daysLabel(days) {
  const n = Number(days || 0)
  if (n <= 0) return ''
  if (t('common.locale_code') === 'en') {
    if (n % 365 === 0) {
      const years = Math.floor(n / 365)
      return years === 1 ? `${years} year` : `${years} years`
    }
    if (n % 30 === 0 && n >= 30) {
      const months = Math.floor(n / 30)
      return _monthsLabel(months)
    }
    return n === 1 ? `${n} day` : `${n} days`
  }
  if (n % 365 === 0) {
    const years = Math.floor(n / 365)
    if (years === 1) return '1 год'
    if (years >= 2 && years <= 4) return `${years} года`
    return `${years} лет`
  }
  if (n % 30 === 0 && n >= 30) {
    const months = Math.floor(n / 30)
    return _monthsLabel(months)
  }
  if (n === 1) return '1 день'
  if (n >= 2 && n <= 4) return `${n} дня`
  return `${n} дней`
}

function _shortPromoCode(code, head = 7, tail = 4) {
  const s = String(code || '').trim()
  if (!s) return ''
  if (s.length <= head + tail + 1) return s
  return `${s.slice(0, head)}…${s.slice(-tail)}`
}

const promoDetailsLabelFull = computed(() => {
  const code = String(props.profile?.subscription_promo_code || '').trim()
  if (!code) return ''
  const days = Number(props.profile?.subscription_promo_period_days || 0)
  const isEn = t('common.locale_code') === 'en'
  let period = isEn ? 'forever' : 'бессрочно'
  if (days > 0) {
    if (days % 365 === 0) {
      const years = Math.floor(days / 365)
      period = isEn
        ? years === 1 ? '1 y' : `${years} y`
        : years === 1 ? '1 г' : `${years} г`
    } else if (days % 30 === 0) {
      const months = Math.floor(days / 30)
      period = isEn ? `${months} mo` : `${months} мес`
    } else {
      period = isEn ? `${days} d` : `${days} дн`
    }
  }
  return `${code} · ${period}`
})

const promoDetailsLabel = computed(() => {
  const code = String(props.profile?.subscription_promo_code || '').trim()
  if (!code) return ''
  const full = promoDetailsLabelFull.value
  if (!full) return ''
  const periodPart = full.split(' · ').slice(1).join(' · ')
  const codeShort = _shortPromoCode(code)
  return `${codeShort}${periodPart ? ` · ${periodPart}` : ''}`
})

const subscriptionHistoryView = computed(() =>
  (subscriptionHistoryItems.value || []).map((row) => {
    const kind = String(row?.kind || '')
    const amount = Number(row?.amount_rub || 0)
    const months = Number(row?.period_months || 0)
    const days = Number(row?.period_days || 0)
    const code = String(row?.promo_code || '')
    const bonusTokens = Number(row?.grant_tokens || 0)
    const bonusAurum = Number(row?.grant_aurum || 0)
    const dateLabel = formatDateTimeRu(row?.created_at)
    const isEn = t('common.locale_code') === 'en'
    if (kind === 'payment') {
      const amountLabel = amount ? `${Math.round(amount)} ${isEn ? 'RUB' : '₽'}` : '—'
      const periodLabel = months > 0 ? _monthsLabel(months) : (days > 0 ? _daysLabel(days) : '—')
      return {
        key: `pay:${row?.created_at || ''}:${amountLabel}:${periodLabel}`,
        title: isEn ? `Payment ${amountLabel}` : `Оплата ${amountLabel}`,
        subtitle: isEn ? `Period: ${periodLabel}` : `Период: ${periodLabel}`,
        dateLabel,
      }
    }
    const bonusParts = []
    if (bonusTokens > 0) bonusParts.push(`+${bonusTokens} ⚡`)
    if (bonusAurum > 0) bonusParts.push(`+${bonusAurum} ✨`)
    const periodLabel = days > 0 ? _daysLabel(days) : (isEn ? 'no expiry' : 'без срока')
    return {
      key: `promo:${code}:${row?.created_at || ''}`,
      title: isEn ? `Promo ${code || '—'}` : `Промокод ${code || '—'}`,
      subtitle: (isEn ? 'Period: ' : 'Период: ') + periodLabel + (bonusParts.length ? ` · ${bonusParts.join(', ')}` : ''),
      dateLabel,
    }
  }),
)

async function loadSubscriptionHistory() {
  if (!props.profile?.telegram_id) {
    subscriptionHistoryItems.value = []
    return
  }
  subscriptionHistoryLoading.value = true
  try {
    const data = await fetchSilent(() => rawApi.historySubscription())
    subscriptionHistoryItems.value = Array.isArray(data?.items) ? data.items : []
  } catch {
    subscriptionHistoryItems.value = []
  } finally {
    subscriptionHistoryLoading.value = false
  }
}

function toggleSubscriptionHistory() {
  subscriptionHistoryOpen.value = !subscriptionHistoryOpen.value
  if (subscriptionHistoryOpen.value && !subscriptionHistoryLoadedOnce.value) {
    subscriptionHistoryLoadedOnce.value = true
    void loadSubscriptionHistory()
  }
}

async function toggleAutorenew() {
  if (props.readOnly) return
  if (autorenewToggleLoading.value) return
  if (!autorenewOn.value) {
    showToast(
      t('common.locale_code') === 'en'
        ? 'To enable auto-renew, pay the subscription by card via YooKassa.'
        : 'Чтобы включить автопродление, оплатите подписку картой через ЮKassa.',
    )
    return
  }
  autorenewToggleLoading.value = true
  try {
    await fetchSilent(() => rawApi.disableAutorenew())
    const fresh = await fetchSilent(() => rawApi.me())
    pushProfile(fresh)
    showToast(t('subscription.toasts.autorenew_off_done'))
  } catch (e) {
    showToast(String(e?.body?.detail || e?.message || t('subscription.toasts.autorenew_off_failed')))
  } finally {
    autorenewToggleLoading.value = false
  }
}

function renewSubscriptionButton() {
  if (props.readOnly) return
  emit('open-tariff')
}

watch(
  () => props.profile?.telegram_id,
  () => {
    subscriptionHistoryOpen.value = false
    subscriptionHistoryLoadedOnce.value = false
    subscriptionHistoryItems.value = []
  },
)
</script>

<template>
  <div
    class="text-white"
    :class="variant === 'page' ? '-mx-4 min-h-[calc(100dvh-7.5rem)] px-4 pb-6 pt-1 md:-mx-6 md:px-6' : 'py-0'"
  >
    <div
      class="space-y-4 w-full"
      :class="
        useDarkShell
          ? 'rounded-2xl border border-zinc-800/50 bg-zinc-950/95 p-3.5 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.04)] ring-1 ring-black/60'
          : ''
      "
    >
    <!-- Карточка статуса: тонкая рамка; общая тёмная подложка — родитель с page -->
    <div :class="variant === 'embedded' ? '' : 'rounded-2xl bg-zinc-900/50 p-1.5 ring-1 ring-zinc-800/60'">
      <div
        class="relative overflow-hidden rounded-[0.8rem] border border-lime-500/35 bg-gradient-to-b from-zinc-900/95 via-zinc-950/98 to-black/95 p-4 shadow-inner shadow-black/40"
        :class="isPremium ? 'pb-11' : 'pb-4'"
      >
        <div class="flex items-start gap-3 pr-1">
          <span class="text-3xl leading-none drop-shadow-[0_0_8px_rgba(234,179,8,0.2)]" aria-hidden="true">👑</span>
          <div class="min-w-0 flex-1">
            <p
              class="text-[1.32rem] font-extrabold leading-tight tracking-tight text-lime-400/95 drop-shadow-sm"
            >
              {{ isPremium ? t('billing.active') : t('subscription.plan_free') }}
            </p>
            <p class="mt-1 text-sm text-zinc-300/90">
              {{ t('subscription.next_charge', { date: nextChargeLabel }) }}
            </p>
          </div>
        </div>
        <span
          v-if="isPremium"
          class="absolute bottom-3 right-3 rounded-md border border-lime-500/30 bg-lime-500/10 px-2 py-0.5 text-[9px] font-bold uppercase leading-tight tracking-wide text-lime-200/90"
        >{{ t('subscription.status_active') }}</span>
      </div>
    </div>

    <div>
      <p class="px-0.5 pb-2 text-[12px] font-semibold uppercase tracking-wide text-white/55">{{ t('subscription.status_title') }}</p>
      <div :class="variant === 'embedded' ? 'divide-y divide-white/[0.07] rounded-2xl bg-zinc-900/40' : 'divide-y divide-white/[0.08] rounded-2xl border border-lime-500/10 bg-zinc-900/45'">
        <div class="flex items-center justify-between gap-2 px-3 py-3">
          <span class="text-sm text-white/70">{{ t('subscription.plan_label') }}</span>
          <div class="flex min-w-0 items-center gap-1">
            <span class="truncate text-sm font-semibold text-lime-100/90">{{ tariffRowLabel }}</span>
            <button
              v-if="variant === 'page' && isPremium && !readOnly"
              type="button"
              class="shrink-0 rounded-lg px-1.5 py-0.5 text-lg font-bold leading-none text-lime-400/90 transition hover:bg-white/10 hover:text-lime-300"
              :aria-label="t('subscription.extend')"
              @click="emit('open-tariff')"
            >&gt;</button>
          </div>
        </div>
        <div class="flex items-center justify-between px-3 py-3">
          <span class="text-sm text-white/70">{{ t('subscription.method_label') }}</span>
          <span class="text-sm font-semibold text-white">{{ paymentMethodLabel }}</span>
        </div>
        <div v-if="promoDetailsLabel && isPremium" class="flex items-center justify-between px-3 py-3">
          <span class="text-sm text-white/70">{{ t('subscription.payment_method.promo') }}</span>
          <span class="min-w-0 flex-1 truncate pl-2 text-right text-[12px] font-semibold leading-tight text-lime-200" :title="promoDetailsLabelFull">{{ promoDetailsLabel }}</span>
        </div>
        <div class="flex items-center justify-between px-3 py-3">
          <span class="text-sm text-white/70">{{ t('common.locale_code') === 'en' ? 'Subscriber since' : 'Подписка с' }}</span>
          <span class="text-sm font-semibold text-white tabular-nums">{{ activationLabel || '—' }}</span>
        </div>
        <div class="flex items-center justify-between px-3 py-3">
          <span class="text-sm text-white/70">{{ t('common.locale_code') === 'en' ? 'Next charge' : 'Следующее списание' }}</span>
          <span class="max-w-[min(100%,16rem)] truncate text-right text-sm font-semibold text-white">{{ nextChargeLabelLong }}</span>
        </div>
        <div class="flex min-h-9 items-center justify-between px-3 py-1.5">
          <span class="text-sm leading-5 text-white/70">{{ t('subscription.autorenew') }}</span>
          <div v-if="readOnly" class="text-sm font-semibold leading-5" :class="autorenewOn ? 'text-lime-400' : 'text-white/50'">
            {{ autorenewOn ? t('common.enabled') : t('common.disabled') }}
          </div>
          <div v-else class="flex min-h-7 items-center justify-end gap-2">
            <span class="shrink-0 text-sm font-semibold leading-5" :class="autorenewOn ? 'text-lime-400' : 'text-white/50'">
              {{ autorenewOn ? t('common.enabled') : t('common.disabled') }}
            </span>
            <button
              type="button"
              role="switch"
              :aria-checked="autorenewOn ? 'true' : 'false'"
              class="relative box-border h-[26px] w-[42px] shrink-0 touch-manipulation overflow-hidden rounded-full border transition-[background-color,border-color,opacity] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime-500/50"
              :class="
                autorenewOn
                  ? 'border-lime-500/40 bg-[#34C759] shadow-[inset_0_0_0_0.5px_rgba(0,0,0,0.15)]'
                  : 'border-zinc-500/90 bg-[#3a3a3c] shadow-[inset_0_0_0_0.5px_rgba(255,255,255,0.08)]'
              "
              :disabled="autorenewToggleLoading"
              @click="toggleAutorenew"
            >
              <span
                class="pointer-events-none absolute z-10 block rounded-full border border-white/5 bg-white shadow-[0_1px_2px_rgba(0,0,0,0.28),0_0_0_0.5px_rgba(0,0,0,0.06)]"
                :style="autorenewKnobStyle"
              />
            </button>
          </div>
        </div>
      </div>
    </div>

    <div>
      <button
        type="button"
        :class="variant === 'embedded' ? 'flex w-full items-center justify-between gap-2 rounded-2xl bg-zinc-900/45 px-3 py-3 text-left text-[13px] font-semibold text-lime-100/95 transition hover:bg-zinc-900/70 active:scale-[0.99]' : 'flex w-full items-center justify-between gap-2 rounded-2xl border border-lime-500/20 bg-zinc-900/55 px-3 py-3 text-left text-[13px] font-semibold text-lime-100/95 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] transition hover:border-lime-400/35 hover:bg-zinc-900/80 active:scale-[0.99]'"
        :aria-expanded="subscriptionHistoryOpen ? 'true' : 'false'"
        @click="toggleSubscriptionHistory"
      >
        <span>{{ t('subscription.paid_history') }}</span>
        <span class="shrink-0 text-[11px] font-bold text-lime-300/80 tabular-nums">{{ subscriptionHistoryOpen ? '▲' : '▼' }}</span>
      </button>
      <div v-show="subscriptionHistoryOpen" :class="variant === 'embedded' ? 'mt-2 rounded-2xl bg-zinc-900/40 p-2' : 'mt-2 rounded-2xl border border-lime-500/10 bg-zinc-900/45 p-2'">
        <p v-if="subscriptionHistoryLoading" class="px-2 py-2 text-[12px] text-white/55">{{ t('loading.history') }}</p>
        <p v-else-if="!subscriptionHistoryView.length" class="px-2 py-2 text-[12px] text-white/50">{{ t('history.empty') }}</p>
        <div v-else class="space-y-1.5">
          <div
            v-for="item in subscriptionHistoryView"
            :key="item.key"
            class="rounded-xl border border-white/[0.08] bg-black/20 px-2.5 py-2"
          >
            <p class="text-[13px] font-semibold text-white">{{ item.title }}</p>
            <p class="mt-0.5 text-[12px] text-white/70">{{ item.subtitle }}</p>
            <p class="mt-0.5 text-[11px] text-white/45">{{ item.dateLabel }}</p>
          </div>
        </div>
      </div>
    </div>

    <button
      v-if="!readOnly"
      type="button"
      class="w-full rounded-2xl border border-violet-300/35 bg-violet-500/[0.18] py-3.5 text-[15px] font-bold text-white shadow-[0_16px_40px_-20px_rgba(139,92,246,0.65)] transition hover:bg-violet-500/[0.26] active:scale-[0.99]"
      @click="renewSubscriptionButton"
    >
      {{ isPremium ? t('subscription.extend') : t('dashboard.hero.strengthen_protection') }}
    </button>
    </div>
  </div>
</template>

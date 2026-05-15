<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="lock.isOpen.value"
        style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:100000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.72);padding:16px"
        class="backdrop-blur-md"
        role="presentation"
        @click.self="lock.closeLock()"
      >
        <div
          class="relative w-full max-w-sm overflow-hidden rounded-[22px] bg-gradient-to-b from-zinc-900 to-black p-5 shadow-[0_24px_72px_-20px_rgba(0,0,0,0.9)] ring-1 ring-amber-400/25"
          role="dialog"
          aria-modal="true"
          aria-labelledby="premium-lock-title"
        >
          <!-- Декоративная корона на фоне -->
          <div
            class="pointer-events-none absolute -right-6 -top-6 h-32 w-32 rounded-full bg-[radial-gradient(circle_at_center,rgba(251,191,36,0.18),transparent_65%)] blur-2xl"
            aria-hidden="true"
          />
          <div class="relative z-[1] flex items-start gap-3">
            <div
              class="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-amber-400/25 to-amber-600/10 text-[28px] leading-none ring-1 ring-amber-300/40"
              aria-hidden="true"
            >👑</div>
            <div class="min-w-0 flex-1">
              <h2
                id="premium-lock-title"
                class="text-[17px] font-bold leading-tight text-white"
              >{{ t(lock.titleKey.value || 'premium_lock.title') }}</h2>
              <p class="mt-1 text-[13px] leading-snug text-white/65">
                {{ t(lock.descriptionKey.value || 'premium_lock.feature_desc.generic') }}
              </p>
            </div>
            <button
              type="button"
              class="-mr-1 -mt-1 flex h-8 w-8 items-center justify-center rounded-full text-white/55 transition active:scale-95 hover:bg-white/[0.08]"
              :aria-label="t('common.close')"
              @click="lock.closeLock()"
            >
              <span aria-hidden="true" class="text-[18px] leading-none">✕</span>
            </button>
          </div>

          <!-- Что входит в Premium (короткий перечень) -->
          <ul class="relative z-[1] mt-4 space-y-1.5 text-[12px] leading-snug text-white/75">
            <li class="flex items-start gap-2">
              <span class="shrink-0 font-bold text-amber-300/95" aria-hidden="true">✓</span>
              <span>{{ t('premium_lock.bullets.l1') }}</span>
            </li>
            <li class="flex items-start gap-2">
              <span class="shrink-0 font-bold text-amber-300/95" aria-hidden="true">✓</span>
              <span>{{ t('premium_lock.bullets.l2') }}</span>
            </li>
            <li class="flex items-start gap-2">
              <span class="shrink-0 font-bold text-amber-300/95" aria-hidden="true">✓</span>
              <span>{{ t('premium_lock.bullets.l3') }}</span>
            </li>
            <li class="flex items-start gap-2">
              <span class="shrink-0 font-bold text-amber-300/95" aria-hidden="true">✓</span>
              <span>{{ t('premium_lock.bullets.l4') }}</span>
            </li>
          </ul>

          <!-- CTA: триал если доступен, иначе сразу к биллингу -->
          <div class="relative z-[1] mt-5 space-y-2">
            <button
              v-if="canTrial"
              type="button"
              :disabled="trialActivating"
              class="flex w-full items-center justify-center gap-1.5 rounded-2xl bg-gradient-to-r from-emerald-500 via-emerald-400 to-lime-300 px-3 py-3 text-[14px] font-extrabold text-emerald-950 shadow-[0_10px_30px_-10px_rgba(16,185,129,0.62),inset_0_1px_0_rgba(255,255,255,0.32)] ring-1 ring-emerald-300/45 transition active:scale-[0.99] disabled:opacity-60"
              @click="handleTrialClick"
            >
              <span aria-hidden="true">🚀</span>
              {{ trialActivating ? t('premium_lock.activating') : t('premium_lock.cta_trial') }}
            </button>
            <button
              type="button"
              class="flex w-full items-center justify-center gap-1.5 rounded-2xl px-3 py-3 text-[14px] font-extrabold text-white shadow-[0_10px_30px_-10px_rgba(139,92,246,0.55),inset_0_1px_0_rgba(255,255,255,0.22)] transition active:scale-[0.99]"
              style="background: linear-gradient(90deg, #f39c12 0%, #df5a3b 34%, #b043cc 56%, #5c2dc1 74%, #2a1a83 100%);"
              @click="handleBillingClick"
            >
              <span aria-hidden="true">👑</span>
              {{ t('premium_lock.cta_billing') }}
            </button>
            <button
              type="button"
              class="w-full py-2 text-center text-[12px] font-medium text-white/45 underline decoration-white/15 underline-offset-4 transition hover:text-white/65"
              @click="lock.closeLock()"
            >
              {{ t('premium_lock.cta_dismiss') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { usePremiumLock } from '../composables/usePremiumLock'
import { useToast } from '../composables/useToast'
import { api as rawApi } from '../api/client'
import { useDashboardSection } from '../composables/useDashboardSection'

const { t } = useI18n()
const router = useRouter()
const lock = usePremiumLock()
const toast = useToast()
const { setDashboardSection } = useDashboardSection()

const trialActivating = ref(false)

const canTrial = computed(() => {
  const me = lock.me.value
  return !!me && !!me.trial_eligible && !me.is_premium
})

async function handleTrialClick() {
  if (trialActivating.value) return
  trialActivating.value = true
  try {
    const res = await rawApi.activateTrial()
    if (res?.already_active) {
      toast.showToast(t('dashboard.trial.already_active_toast'))
    } else {
      toast.showToast(t('dashboard.trial.activated_toast', { n: Number(res?.trial_remaining_days || 10) }))
    }
    lock.closeLock()
    // Лёгкий refresh страницы — самый простой способ обновить me и снять блоки.
    try { window.location.reload() } catch (_) { /* noop */ }
  } catch (e) {
    const detail = String(e?.body?.detail || e?.message || '').toLowerCase()
    let key = 'dashboard.trial.error_generic'
    if (detail.includes('already_used')) key = 'dashboard.trial.error_already_used'
    else if (detail.includes('window_closed')) key = 'dashboard.trial.error_window_closed'
    else if (detail.includes('active_subscription')) key = 'dashboard.trial.error_active_subscription'
    else if (detail.includes('no_first_start')) key = 'dashboard.trial.error_no_first_start'
    toast.showToast(t(key))
  } finally {
    trialActivating.value = false
  }
}

function handleBillingClick() {
  lock.closeLock()
  setDashboardSection('billing')
  try {
    router.push({ path: '/', query: { section: 'billing', scroll: 'plans' } })
  } catch (_) { /* noop */ }
}
</script>

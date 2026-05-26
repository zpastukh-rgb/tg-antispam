<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { clearYookassaCheckout, readYookassaCheckout } from '../utils/yookassaCheckout.js'

const router = useRouter()
const { t } = useI18n()
const error = ref('')
const loading = ref(true)
let checkoutWidget = null
let backHandler = null

function loadCheckoutScript() {
  return new Promise((resolve, reject) => {
    if (window.YooMoneyCheckoutWidget) {
      resolve()
      return
    }
    const existing = document.querySelector('script[data-guard-yookassa-widget="1"]')
    if (existing) {
      existing.addEventListener('load', () => resolve(), { once: true })
      existing.addEventListener('error', () => reject(new Error('script_load_failed')), { once: true })
      return
    }
    const script = document.createElement('script')
    script.src = 'https://yookassa.ru/checkout-widget/v1/checkout-widget.js'
    script.async = true
    script.dataset.guardYookassaWidget = '1'
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('script_load_failed'))
    document.head.appendChild(script)
  })
}

function finishAndReturn() {
  clearYookassaCheckout()
  window.dispatchEvent(new CustomEvent('guard:yookassa-return'))
  void router.replace({ path: '/', query: { section: 'billing' } })
}

function goBack() {
  clearYookassaCheckout()
  if (window.history.length > 1) {
    router.back()
    return
  }
  void router.replace({ path: '/', query: { section: 'billing' } })
}

onMounted(async () => {
  const tg = window.Telegram?.WebApp
  try {
    tg?.expand?.()
  } catch {
    //
  }

  backHandler = () => goBack()
  try {
    tg?.BackButton?.show?.()
    tg?.BackButton?.onClick?.(backHandler)
  } catch {
    //
  }

  const payload = readYookassaCheckout()
  const token = String(payload?.confirmation_token || '').trim()
  if (!token) {
    error.value = t('errors.payment_link_missing')
    loading.value = false
    return
  }

  const returnUrl = String(payload?.return_url || '').trim()
    || `${window.location.origin}${window.location.pathname.replace(/\/pay\/yookassa\/?$/, '/')}`.replace(/\/?$/, '/')
    + '?section=billing'

  try {
    await loadCheckoutScript()
    checkoutWidget = new window.YooMoneyCheckoutWidget({
      confirmation_token: token,
      return_url: returnUrl,
      customization: {
        modal: false,
        colors: {
          control_primary: '#84cc16',
          background: '#0b0b10',
        },
      },
      error_callback: (err) => {
        error.value = String(err?.error || err?.message || t('errors.payment_failed'))
      },
    })
    checkoutWidget.on('success', () => {
      finishAndReturn()
    })
    checkoutWidget.on('complete', () => {
      finishAndReturn()
    })
    checkoutWidget.on('fail', () => {
      error.value = t('errors.payment_failed')
    })
    checkoutWidget.render('yookassa-checkout-root')
    loading.value = false
  } catch {
    error.value = t('errors.payment_failed')
    loading.value = false
  }
})

onBeforeUnmount(() => {
  const tg = window.Telegram?.WebApp
  try {
    if (backHandler) tg?.BackButton?.offClick?.(backHandler)
    tg?.BackButton?.hide?.()
  } catch {
    //
  }
  try {
    checkoutWidget?.destroy?.()
  } catch {
    //
  }
})
</script>

<template>
  <div class="yookassa-pay-shell">
    <header class="yookassa-pay-head">
      <button type="button" class="yookassa-pay-back" @click="goBack">
        {{ t('common.back') }}
      </button>
      <p class="yookassa-pay-title">{{ t('billing.checkout.title') }}</p>
    </header>

    <p v-if="loading" class="yookassa-pay-status">{{ t('billing.checkout.loading') }}</p>
    <p v-if="error" class="yookassa-pay-error">{{ error }}</p>
    <div id="yookassa-checkout-root" class="yookassa-pay-root" />
  </div>
</template>

<style scoped>
.yookassa-pay-shell {
  min-height: 100dvh;
  background: #0b0b10;
  color: #f4f4f5;
  padding:
    max(12px, env(safe-area-inset-top))
    max(12px, env(safe-area-inset-right))
    max(16px, env(safe-area-inset-bottom))
    max(12px, env(safe-area-inset-left));
}

.yookassa-pay-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.yookassa-pay-back {
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: #e4e4e7;
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 12px;
}

.yookassa-pay-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
}

.yookassa-pay-status {
  margin: 0 0 12px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.65);
}

.yookassa-pay-error {
  margin: 0 0 12px;
  font-size: 13px;
  color: #fca5a5;
}

.yookassa-pay-root {
  min-height: 420px;
}
</style>

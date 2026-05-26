<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { clearYookassaCheckout, readYookassaCheckout } from '../utils/yookassaCheckout.js'

const YK_WIDGET_COLORS = {
  control_primary: '#84cc16',
  control_primary_content: '#0a0a0a',
  control_secondary: '#52525b',
  background: '#27272a',
  text: '#fafafa',
  border: '#71717a',
}

const router = useRouter()
const { t } = useI18n()
const error = ref('')
const loading = ref(true)
let checkoutWidget = null
let backHandler = null
let scrollResetTimer = null
let checkoutObserver = null
let savedToken = ''
let savedReturnUrl = ''

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

function widgetRootText() {
  const root = document.getElementById('yookassa-checkout-root')
  return String(root?.innerText || '').replace(/\s+/g, ' ').trim()
}

/** Экран выбора способа (SberPay + карта + …) — выходим в billing. Иначе шаг назад внутри виджета. */
function isWidgetMethodListScreen() {
  const text = widgetRootText()
  if (!text) return true
  if (/Отсканируйте QR|Оплатить через пуш|Войти в кошелёк|Зарегистрироваться/i.test(text)) {
    return false
  }
  const markers = [
    /Банковская карта/i.test(text),
    /\bСБП\b/i.test(text),
    /SberPay/i.test(text),
    /ЮMoney|YooMoney/i.test(text),
  ].filter(Boolean).length
  return markers >= 2
}

function scrollCheckoutToTop() {
  try {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  } catch {
    window.scrollTo(0, 0)
  }
  document.documentElement.scrollTop = 0
  document.body.scrollTop = 0
  const main = document.querySelector('main')
  if (main) main.scrollTop = 0
  const head = document.querySelector('.yookassa-pay-head')
  if (head?.scrollIntoView) {
    head.scrollIntoView({ block: 'start', behavior: 'auto' })
  }
}

function scheduleScrollReset() {
  scrollCheckoutToTop()
  if (scrollResetTimer) clearTimeout(scrollResetTimer)
  scrollResetTimer = setTimeout(scrollCheckoutToTop, 120)
  setTimeout(scrollCheckoutToTop, 420)
}

function watchCheckoutMount() {
  const root = document.getElementById('yookassa-checkout-root')
  if (!root || typeof MutationObserver === 'undefined') return
  checkoutObserver = new MutationObserver(() => {
    scheduleScrollReset()
  })
  checkoutObserver.observe(root, { childList: true, subtree: true })
}

function bindCheckoutEvents(widget) {
  widget.on('success', () => {
    finishAndReturn()
  })
  widget.on('complete', () => {
    finishAndReturn()
  })
  widget.on('fail', () => {
    error.value = t('errors.payment_failed')
  })
}

function createCheckoutWidget(token, returnUrl) {
  const widget = new window.YooMoneyCheckoutWidget({
    confirmation_token: token,
    return_url: returnUrl,
    customization: {
      modal: false,
      colors: YK_WIDGET_COLORS,
    },
    error_callback: (err) => {
      error.value = String(err?.error || err?.message || t('errors.payment_failed'))
    },
  })
  bindCheckoutEvents(widget)
  return widget
}

async function mountCheckoutWidget() {
  if (!savedToken) return false
  try {
    checkoutWidget?.destroy?.()
  } catch {
    //
  }
  checkoutWidget = createCheckoutWidget(savedToken, savedReturnUrl)
  await checkoutWidget.render('yookassa-checkout-root')
  return true
}

function finishAndReturn() {
  clearYookassaCheckout()
  window.dispatchEvent(new CustomEvent('guard:yookassa-return'))
  void router.replace({ path: '/', query: { section: 'billing' } })
}

function exitCheckout() {
  clearYookassaCheckout()
  try {
    checkoutWidget?.destroy?.()
  } catch {
    //
  }
  checkoutWidget = null
  if (window.history.length > 1) {
    router.back()
    return
  }
  void router.replace({ path: '/', query: { section: 'billing' } })
}

async function goBack() {
  if (!isWidgetMethodListScreen()) {
    const ok = await mountCheckoutWidget()
    if (ok) {
      scheduleScrollReset()
      return
    }
  }
  exitCheckout()
}

onMounted(async () => {
  scheduleScrollReset()

  const tg = window.Telegram?.WebApp
  try {
    tg?.expand?.()
  } catch {
    //
  }

  backHandler = () => {
    void goBack()
  }
  try {
    tg?.BackButton?.show?.()
    tg?.BackButton?.onClick?.(backHandler)
  } catch {
    //
  }

  const payload = readYookassaCheckout()
  savedToken = String(payload?.confirmation_token || '').trim()
  if (!savedToken) {
    error.value = t('errors.payment_link_missing')
    loading.value = false
    return
  }

  savedReturnUrl = String(payload?.return_url || '').trim()
    || `${window.location.origin}${window.location.pathname.replace(/\/pay\/yookassa\/?$/, '/')}`.replace(/\/?$/, '/')
    + '?section=billing'

  try {
    await loadCheckoutScript()
    watchCheckoutMount()
    await mountCheckoutWidget()
    loading.value = false
    scheduleScrollReset()
  } catch {
    error.value = t('errors.payment_failed')
    loading.value = false
  }
})

onBeforeUnmount(() => {
  if (scrollResetTimer) {
    clearTimeout(scrollResetTimer)
    scrollResetTimer = null
  }
  checkoutObserver?.disconnect?.()
  checkoutObserver = null

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
    max(8px, env(safe-area-inset-top))
    max(12px, env(safe-area-inset-right))
    max(12px, env(safe-area-inset-bottom))
    max(12px, env(safe-area-inset-left));
}

.yookassa-pay-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  scroll-margin-top: 0;
}

.yookassa-pay-back {
  border: 1px solid rgba(132, 204, 22, 0.55);
  background: rgba(132, 204, 22, 0.16);
  color: #ecfccb;
  border-radius: 999px;
  padding: 7px 14px;
  font-size: 13px;
  font-weight: 700;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.yookassa-pay-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
}

.yookassa-pay-status {
  margin: 0 0 12px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.72);
}

.yookassa-pay-error {
  margin: 0 0 12px;
  font-size: 13px;
  color: #fca5a5;
}

.yookassa-pay-root {
  min-height: 360px;
  scroll-margin-top: 0;
}
</style>

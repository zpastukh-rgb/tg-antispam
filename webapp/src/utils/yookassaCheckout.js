const STORAGE_KEY = 'guard_yookassa_checkout'

export function storeYookassaCheckout(payload, meta = {}) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
    confirmation_token: String(payload?.confirmation_token || '').trim(),
    confirmation_url: String(payload?.confirmation_url || '').trim(),
    return_url: String(payload?.return_url || '').trim(),
    kind: String(meta?.kind || '').trim(),
  }))
}

export function readYookassaCheckout() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch {
    return null
  }
}

export function clearYookassaCheckout() {
  sessionStorage.removeItem(STORAGE_KEY)
}

/**
 * Открывает оплату внутри mini app (embedded widget) или в том же WebView (redirect fallback).
 * @returns {'embedded'|'redirect'|null}
 */
export function openYookassaPayment(router, response, { onBeforeNavigate } = {}) {
  const token = String(response?.confirmation_token || '').trim()
  const url = String(response?.confirmation_url || '').trim()

  if (token) {
    storeYookassaCheckout(response)
    onBeforeNavigate?.()
    void router.push({ path: '/pay/yookassa' })
    return 'embedded'
  }

  if (url) {
    onBeforeNavigate?.()
    try {
      window.location.assign(url)
    } catch {
      window.open(url, '_blank', 'noopener,noreferrer')
    }
    return 'redirect'
  }

  return null
}

export function yookassaPaymentReady(response) {
  return Boolean(
    String(response?.confirmation_token || '').trim()
    || String(response?.confirmation_url || '').trim(),
  )
}

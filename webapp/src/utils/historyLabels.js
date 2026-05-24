/**
 * Читаемые подписи для истории платежей и движений AURUM/токенов.
 */

export function formatHistoryDateTime(iso, isEn = false) {
  if (iso == null || iso === '') return '—'
  const d = new Date(typeof iso === 'string' ? iso : String(iso))
  if (Number.isNaN(d.getTime())) return String(iso)
  const loc = isEn ? 'en-GB' : 'ru-RU'
  return new Intl.DateTimeFormat(loc, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(d)
}

/** @param {{ provider?: string, kind?: string, promo_code?: string, payment_method_type?: string }} item */
export function paymentProviderLabel(item, t) {
  const kind = String(item?.kind || '').toLowerCase()
  const provider = String(item?.provider || '').toLowerCase()
  const promoCode = String(item?.promo_code || '').trim()
  const methodType = String(item?.payment_method_type || '').toLowerCase()

  if (kind === 'promo' || provider === 'promo' || provider.includes('promo')) {
    if (promoCode) {
      return t('history.provider.promo_with_code', { code: promoCode })
    }
    return t('billing.method.promo')
  }
  if (methodType.includes('sbp') || provider.includes('sbp')) {
    return t('billing.method.yookassa_sbp')
  }
  if (
    methodType.includes('card')
    || methodType.includes('bank_card')
    || provider.includes('card')
    || provider.includes('bank_card')
  ) {
    return t('billing.method.yookassa_card')
  }
  if (provider.includes('yoomoney') || provider.includes('yoo_money')) {
    return t('billing.method.yookassa')
  }
  if (provider.includes('yookassa') || provider.includes('yoo')) {
    return t('billing.method.yookassa_card')
  }
  if (provider) return provider
  return t('billing.method.none')
}

export function paymentStatusLabel(status, t) {
  const s = String(status || '').trim().toLowerCase()
  if (!s) return '—'
  const key = `history.payment_status.${s}`
  const tr = t(key)
  return tr !== key ? tr : status
}

export function tokenReasonLabel(reason, t) {
  const raw = String(reason || '').trim().toLowerCase()
  if (!raw) return '—'
  const key = `history.kinds.${raw}`
  const tr = t(key)
  return tr !== key ? tr : raw.replace(/_/g, ' ')
}

/** Нормализация promo-строк из /history/subscription для вкладки «Платежи». */
export function mapSubscriptionPromoToPaymentRow(row) {
  if (!row || String(row.kind || '').toLowerCase() !== 'promo') return null
  return {
    kind: 'promo',
    created_at: row.created_at,
    amount_rub: Number(row.amount_rub || 0),
    months: Number(row.period_months || 0),
    period_days: Number(row.period_days || 0),
    tariff: 'premium',
    status: 'succeeded',
    provider: 'promo',
    promo_code: String(row.promo_code || '').trim(),
    grant_tokens: Number(row.grant_tokens || 0),
    grant_aurum: Number(row.grant_aurum || 0),
    receipt_url: '',
  }
}

export function mergePaymentHistoryRows(paymentItems, subscriptionItems) {
  const base = Array.isArray(paymentItems) ? [...paymentItems] : []
  const promos = (Array.isArray(subscriptionItems) ? subscriptionItems : [])
    .map(mapSubscriptionPromoToPaymentRow)
    .filter(Boolean)
  const merged = [...base, ...promos]
  merged.sort((a, b) => {
    const ta = new Date(a?.created_at || 0).getTime()
    const tb = new Date(b?.created_at || 0).getTime()
    return tb - ta
  })
  return merged
}

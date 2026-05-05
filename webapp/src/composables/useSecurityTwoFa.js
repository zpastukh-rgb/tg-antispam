/** Ключи localStorage совпадают с AdminView.vue (настройки безопасности). */

export const SETTINGS_2FA_KEY = 'guard.settings.twofa.v1'
export const SETTINGS_TWOFA_LIST_KEY = 'guard.settings.twofa.list.v1'
export const SETTINGS_TWOFA_CODE_KEY = 'guard.settings.twofa.code.v1'
export const SETTINGS_CONFIRM_LIST_KEY = 'guard.settings.confirmActions.list.v1'

/** Действие: пауза / выключение Guard в чате (совпадает с SECURITY_ACTIONS в AdminView). */
export const SECURITY_ACTION_MASTER_PROTECTION_OFF = 'master_protection_off'

function readBool(key, def) {
  try {
    const raw = localStorage.getItem(key)
    if (raw === '1') return true
    if (raw === '0') return false
  } catch {
    /* ignore */
  }
  return def
}

export function isTwoFaEnabled() {
  return readBool(SETTINGS_2FA_KEY, false)
}

export function isTwoFaPinRequiredForAction(actionKey) {
  if (!isTwoFaEnabled()) return false
  try {
    const raw = localStorage.getItem(SETTINGS_TWOFA_LIST_KEY)
    if (!raw) return false
    const parsed = JSON.parse(raw)
    return !!parsed[actionKey]
  } catch {
    return false
  }
}

/** Как _readActionMap(..., defaultOn: true) в AdminView: неизвестный ключ → подтверждение включено. */
export function isConfirmRequiredForAction(actionKey) {
  try {
    const raw = localStorage.getItem(SETTINGS_CONFIRM_LIST_KEY)
    if (!raw) return true
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return true
    return Object.prototype.hasOwnProperty.call(parsed, actionKey) ? !!parsed[actionKey] : true
  } catch {
    return true
  }
}

export function readStoredPinDigits() {
  try {
    const raw = localStorage.getItem(SETTINGS_TWOFA_CODE_KEY)
    return raw ? String(raw).replace(/\D+/g, '') : ''
  } catch {
    return ''
  }
}

export function verifyPinDigits(entered) {
  const a = String(entered || '').replace(/\D+/g, '')
  const b = readStoredPinDigits()
  return a.length >= 4 && b.length >= 4 && a === b
}

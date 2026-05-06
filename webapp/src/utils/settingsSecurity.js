/**
 * Локальные настройки подтверждений и PIN (4 цифры) для Mini App.
 * Проверки можно вызывать из других экранов перед деструктивными действиями.
 */

export const GUARD_SECURITY_ACTIONS = [
  { id: 'purge_data', label: 'Очистка данных и истории' },
  { id: 'protection_settings', label: 'Пауза / выключение защиты и правила чата' },
  { id: 'chat_remove', label: 'Отключение чата от Guard' },
  { id: 'payments', label: 'Оплата и покупки' },
  { id: 'broadcast', label: 'Запуск и отправка рассылки' },
]

const LS_CONFIRM_MASTER = 'guard.settings.confirm_actions'
const LS_CONFIRM_MAP = 'guard.settings.confirm_actions_map'
const LS_PIN_ON = 'guard.settings.pin_enabled'
const LS_PIN_MAP = 'guard.settings.pin_actions_map'
const LS_PIN_HASH = 'guard.settings.pin_sha_v1'

function readLs(key, fallback = '') {
  try {
    return localStorage.getItem(key) ?? fallback
  } catch {
    return fallback
  }
}
function writeLs(key, val) {
  try {
    localStorage.setItem(key, val)
  } catch {
    //
  }
}

export function defaultActionMap(val = true) {
  const o = {}
  for (const x of GUARD_SECURITY_ACTIONS) o[x.id] = val
  return o
}

export function loadConfirmMaster() {
  return readLs(LS_CONFIRM_MASTER, '1') === '1'
}

export function saveConfirmMaster(on) {
  writeLs(LS_CONFIRM_MASTER, on ? '1' : '0')
}

export function loadConfirmMap() {
  const raw = loadJsonLs(LS_CONFIRM_MAP, null)
  if (raw && typeof raw === 'object') {
    const base = defaultActionMap(true)
    return { ...base, ...raw }
  }
  return defaultActionMap(true)
}

export function saveConfirmMap(map) {
  writeLs(LS_CONFIRM_MAP, JSON.stringify(map || {}))
}

export function loadPinEnabled() {
  return readLs(LS_PIN_ON, '0') === '1'
}

export function savePinEnabled(on) {
  writeLs(LS_PIN_ON, on ? '1' : '0')
}

export function loadPinMap() {
  const raw = loadJsonLs(LS_PIN_MAP, null)
  if (raw && typeof raw === 'object') {
    const base = defaultActionMap(false)
    return { ...base, ...raw }
  }
  return defaultActionMap(false)
}

export function savePinMap(map) {
  writeLs(LS_PIN_MAP, JSON.stringify(map || {}))
}

export function loadPinHash() {
  return readLs(LS_PIN_HASH, '')
}

export function savePinHash(hashB64) {
  writeLs(LS_PIN_HASH, hashB64 || '')
}

export function clearPin() {
  writeLs(LS_PIN_HASH, '')
  savePinEnabled(false)
  savePinMap(defaultActionMap(false))
}

function loadJsonLs(key, fallback) {
  try {
    const r = localStorage.getItem(key)
    if (r == null || r === '') return fallback
    return JSON.parse(r)
  } catch {
    return fallback
  }
}

export async function hashPin(telegramId, pin) {
  const tid = String(telegramId ?? '0')
  const p = String(pin || '')
  const raw = `${tid}:guard:pin:v1:${p}`
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw))
  return btoa(String.fromCharCode(...new Uint8Array(buf)))
}

export async function verifyPin(telegramId, pin, storedHashB64) {
  if (!storedHashB64 || String(pin || '').length !== 4) return false
  const h = await hashPin(telegramId, pin)
  return h === storedHashB64
}

/** Нужно ли показать обычное подтверждение (модалка / confirm) для действия */
export function shouldConfirmForAction(actionId) {
  if (!loadConfirmMaster()) return false
  const m = loadConfirmMap()
  return !!m[actionId]
}

/** Включён ли PIN и запрошен ли он для действия */
export function shouldAskPinForAction(actionId) {
  if (!loadPinEnabled()) return false
  const h = loadPinHash()
  if (!h) return false
  const m = loadPinMap()
  return !!m[actionId]
}

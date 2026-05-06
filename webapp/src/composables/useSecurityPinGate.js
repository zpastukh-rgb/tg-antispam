import { ref } from 'vue'
import { shouldAskPinForAction, verifyPin, loadPinHash } from '../utils/settingsSecurity'

/**
 * Запрос 4-значного кода из «Настройки → Безопасность» перед чувствительными действиями.
 * @param {() => number} getTelegramId
 */
export function useSecurityPinGate(getTelegramId) {
  const pinGateOpen = ref(false)
  const pinGateInput = ref('')
  const pinGateError = ref('')
  const pinGateBusy = ref(false)
  let resolver = null

  function getTid() {
    try {
      const v = typeof getTelegramId === 'function' ? getTelegramId() : getTelegramId
      return Number(v || 0)
    } catch {
      return 0
    }
  }

  function cancelPinGate() {
    pinGateOpen.value = false
    pinGateInput.value = ''
    pinGateError.value = ''
    pinGateBusy.value = false
    const r = resolver
    resolver = null
    r?.(false)
  }

  async function submitPinGate() {
    const tid = getTid()
    const pin = String(pinGateInput.value || '').replace(/\D/g, '').slice(0, 4)
    if (pin.length !== 4) {
      pinGateError.value = 'Введите 4 цифры'
      return
    }
    const hash = loadPinHash()
    if (!hash || !tid) {
      pinGateError.value = 'Сначала задайте код в «Настройки → Безопасность»'
      return
    }
    pinGateBusy.value = true
    pinGateError.value = ''
    try {
      const ok = await verifyPin(tid, pin, hash)
      if (!ok) {
        pinGateError.value = 'Неверный код'
        return
      }
      pinGateOpen.value = false
      pinGateInput.value = ''
      const r = resolver
      resolver = null
      r?.(true)
    } finally {
      pinGateBusy.value = false
    }
  }

  /**
   * @param {string} actionId — ключ из GUARD_SECURITY_ACTIONS
   * @returns {Promise<boolean>} true — можно продолжать; false — отмена или нет кода
   */
  function requestPinIfNeeded(actionId) {
    if (!shouldAskPinForAction(actionId)) {
      return Promise.resolve(true)
    }
    const tid = getTid()
    const hash = loadPinHash()
    if (!hash || !tid) {
      return Promise.resolve(false)
    }
    return new Promise((resolve) => {
      resolver = resolve
      pinGateInput.value = ''
      pinGateError.value = ''
      pinGateOpen.value = true
    })
  }

  return {
    pinGateOpen,
    pinGateInput,
    pinGateError,
    pinGateBusy,
    requestPinIfNeeded,
    submitPinGate,
    cancelPinGate,
  }
}

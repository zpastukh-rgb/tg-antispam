/**
 * Vue i18n инициализация (RU/EN).
 *
 * Источники локали (по убыванию приоритета):
 *   1. localStorage 'guard.settings.lang' (кэш, для мгновенной отрисовки до /api/me).
 *   2. window.Telegram.WebApp.initDataUnsafe.user.language_code (fallback при первом входе).
 *   3. 'ru' (дефолт проекта).
 *
 * После загрузки /api/me компонент App.vue вызовет setLocale(...) с нормализованным языком профиля:
 *   - переключит i18n.global.locale,
 *   - синхронизирует <html lang>,
 *   - запишет значение в localStorage.
 */

import { createI18n } from 'vue-i18n'
import { isRef } from 'vue'
import ru from './ru.js'
import en from './en.js'

const STORAGE_KEY = 'guard.settings.lang'
export const SUPPORTED_LOCALES = ['ru', 'en']
export const DEFAULT_LOCALE = 'ru'

export function normalizeLocale(value) {
  const s = String(value || '').trim().toLowerCase()
  if (!s) return DEFAULT_LOCALE
  if (s.startsWith('en')) return 'en'
  return 'ru'
}

function detectInitialLocale() {
  let stored = null
  try {
    stored = localStorage.getItem(STORAGE_KEY)
  } catch {
    //
  }
  if (stored && SUPPORTED_LOCALES.includes(normalizeLocale(stored))) {
    return normalizeLocale(stored)
  }
  let tgCode = ''
  try {
    tgCode = window?.Telegram?.WebApp?.initDataUnsafe?.user?.language_code || ''
  } catch {
    //
  }
  return normalizeLocale(tgCode || DEFAULT_LOCALE)
}

const initial = detectInitialLocale()

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: initial,
  fallbackLocale: DEFAULT_LOCALE,
  missingWarn: false,
  fallbackWarn: false,
  silentFallbackWarn: true,
  silentTranslationWarn: true,
  messages: {
    ru,
    en,
  },
})

try {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = initial === 'en' ? 'en' : 'ru'
  }
} catch {
  //
}

/** Программная смена локали из приложения. */
export function setLocale(code) {
  const norm = normalizeLocale(code)
  if (!SUPPORTED_LOCALES.includes(norm)) return DEFAULT_LOCALE
  const loc = i18n.global.locale
  try {
    if (isRef(loc)) {
      loc.value = norm
    } else {
      i18n.global.locale = norm
    }
  } catch {
    try {
      i18n.global.locale = norm
    } catch {
      //
    }
  }
  try {
    localStorage.setItem(STORAGE_KEY, norm)
  } catch {
    //
  }
  try {
    if (typeof document !== 'undefined') {
      document.documentElement.lang = norm === 'en' ? 'en' : 'ru'
    }
  } catch {
    //
  }
  return norm
}

export function getLocale() {
  try {
    const loc = i18n.global.locale
    const raw = isRef(loc) ? loc.value : loc
    return normalizeLocale(raw)
  } catch {
    return DEFAULT_LOCALE
  }
}

/** Удобный синхронный helper для не-Vue кода (composables, api errors). */
export function t(key, params) {
  try {
    return i18n.global.t(key, params || {})
  } catch {
    return key
  }
}

export default i18n

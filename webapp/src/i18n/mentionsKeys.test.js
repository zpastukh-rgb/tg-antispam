/**
 * Регрессия: vue-i18n должен компилировать ключи «Упоминания» в обоих локалях.
 *
 * Падало с `SyntaxError: Invalid linked format` из-за `@username` в строке
 * (vue-i18n считал `@` началом linked-message). После escape через `{'@'}`
 * литералом этот тест держит инвариант, чтобы не наступить на грабли снова.
 */

import { describe, it, expect } from 'vitest'
import { createI18n } from 'vue-i18n'
import ru from './ru.js'
import en from './en.js'
import { sanitizeI18nMessages } from './sanitizeMessages.js'

const KEYS = [
  'protection.ui.mentions_modal_title',
  'protection.ui.mentions_modal_body',
  'protection.policy.allow',
  'protection.policy.forbid',
]

function makeI18n(locale, messages) {
  return createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'ru',
    messages: { [locale]: sanitizeI18nMessages(messages[locale]) },
  })
}

describe('vue-i18n: keys для модалки «Упоминания»', () => {
  it('ru: все ключи компилируются и рендерятся непустой строкой', () => {
    const i = makeI18n('ru', { ru })
    for (const key of KEYS) {
      const v = i.global.t(key)
      expect(typeof v).toBe('string')
      expect(v.length).toBeGreaterThan(0)
    }
  })

  it('en: все ключи компилируются и рендерятся непустой строкой', () => {
    const i = makeI18n('en', { en })
    for (const key of KEYS) {
      const v = i.global.t(key)
      expect(typeof v).toBe('string')
      expect(v.length).toBeGreaterThan(0)
    }
  })

  it('ru.mentions_modal_body содержит литеральный @ (санитайзер сработал)', () => {
    const i = makeI18n('ru', { ru })
    const v = i.global.t('protection.ui.mentions_modal_body')
    expect(v).toContain('@username')
  })

  it('en.mentions_modal_body contains literal @ (sanitizer works)', () => {
    const i = makeI18n('en', { en })
    const v = i.global.t('protection.ui.mentions_modal_body')
    expect(v).toContain('@username')
  })
})

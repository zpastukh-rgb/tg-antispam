/**
 * Тесты санитайзера: литеральный `@` экранируется через `{'@'}`,
 * валидный linked `@:foo` и email-подобный `name@host` — НЕ трогаются.
 */

import { describe, it, expect } from 'vitest'
import { createI18n } from 'vue-i18n'
import { sanitizeI18nString, sanitizeI18nMessages } from './sanitizeMessages.js'
import ru from './ru.js'
import en from './en.js'

describe('sanitizeI18nString', () => {
  it('экранирует `@username` в начале строки', () => {
    expect(sanitizeI18nString('@username')).toBe("{'@'}username")
  })

  it('экранирует `@username` в середине строки', () => {
    expect(sanitizeI18nString('Пример: @manager или ID')).toBe("Пример: {'@'}manager или ID")
  })

  it('экранирует несколько вхождений', () => {
    expect(sanitizeI18nString('@a и @b')).toBe("{'@'}a и {'@'}b")
  })

  it('экранирует `@` перед КИРИЛЛИЦЕЙ (placeholders_hint: `@ник`)', () => {
    expect(sanitizeI18nString('{username} — @ник или пусто')).toBe(
      "{username} — {'@'}ник или пусто",
    )
  })

  it('экранирует одиночную `@` в скобках — ломало vue-i18n в hints модалки медиа', () => {
    expect(sanitizeI18nString('других ботов (без @) — их')).toBe("других ботов (без {'@'}) — их")
    expect(sanitizeI18nString('usernames (without @). The')).toBe("usernames (without {'@'}). The")
    expect(sanitizeI18nString('no @)')).toBe("no {'@'})")
  })

  it('экранирует длинную строку placeholders_hint целиком', () => {
    const before =
      'Плейсхолдеры: {first_name} — имя, {full_name} — полное имя, {username} — @ник или пусто, {chat_title} — название чата.'
    const after = sanitizeI18nString(before)
    expect(after).toContain("{'@'}ник")
    expect(after).not.toMatch(/[^\p{L}\p{N}]@[\p{L}]/u)
  })

  it('не трогает email-подобное `name@host`', () => {
    expect(sanitizeI18nString('user@example.com')).toBe('user@example.com')
  })

  it('не трогает валидный linked `@:foo.bar`', () => {
    expect(sanitizeI18nString('see @:common.cancel')).toBe('see @:common.cancel')
  })

  it('не трогает валидный linked с модификатором `@.lower:foo`', () => {
    expect(sanitizeI18nString('see @.lower:foo')).toBe('see @.lower:foo')
  })

  it('не падает на пустой строке / undefined / null', () => {
    expect(sanitizeI18nString('')).toBe('')
    expect(sanitizeI18nString(null)).toBe(null)
    expect(sanitizeI18nString(undefined)).toBe(undefined)
  })

  it('работает в HTML-строке', () => {
    expect(sanitizeI18nString('Add by <strong>@username</strong> or ID')).toBe(
      "Add by <strong>{'@'}username</strong> or ID",
    )
  })

  it('строка без `@` возвращается as-is', () => {
    expect(sanitizeI18nString('Просто текст без собаки')).toBe('Просто текст без собаки')
  })
})

describe('sanitizeI18nMessages', () => {
  it('рекурсивно обходит вложенные объекты', () => {
    const before = {
      a: { b: { c: 'Пример @username тут' } },
      d: 'обычный текст',
    }
    const after = sanitizeI18nMessages(before)
    expect(after.a.b.c).toBe("Пример {'@'}username тут")
    expect(after.d).toBe('обычный текст')
  })

  it('исходный объект не мутируется', () => {
    const before = { a: 'Юзер @manager здесь' }
    const after = sanitizeI18nMessages(before)
    expect(before.a).toBe('Юзер @manager здесь')
    expect(after.a).toBe("Юзер {'@'}manager здесь")
  })

  it('массивы строк тоже санитайзятся', () => {
    const before = { list: ['@x', 'y'] }
    const after = sanitizeI18nMessages(before)
    expect(after.list[0]).toBe("{'@'}x")
    expect(after.list[1]).toBe('y')
  })
})

describe('реальные локали после санитайзера: vue-i18n не падает', () => {
  function makeI18n(locale, messages) {
    return createI18n({
      legacy: false,
      locale,
      fallbackLocale: 'ru',
      messages,
      missingWarn: false,
      fallbackWarn: false,
    })
  }

  function flattenKeys(obj, prefix = '') {
    const out = []
    for (const k of Object.keys(obj)) {
      const v = obj[k]
      const key = prefix ? `${prefix}.${k}` : k
      if (v && typeof v === 'object' && !Array.isArray(v)) out.push(...flattenKeys(v, key))
      else if (typeof v === 'string') out.push(key)
    }
    return out
  }

  it('ru: все строковые ключи рендерятся без throw', () => {
    const sanitized = sanitizeI18nMessages(ru)
    const i = makeI18n('ru', { ru: sanitized })
    const keys = flattenKeys(sanitized)
    expect(keys.length).toBeGreaterThan(100)
    for (const key of keys) {
      expect(() => i.global.t(key)).not.toThrow()
    }
  })

  it('en: все строковые ключи рендерятся без throw', () => {
    const sanitized = sanitizeI18nMessages(en)
    const i = makeI18n('en', { en: sanitized })
    const keys = flattenKeys(sanitized)
    expect(keys.length).toBeGreaterThan(100)
    for (const key of keys) {
      expect(() => i.global.t(key)).not.toThrow()
    }
  })

  it('конкретно ключи модалок упоминаний/каналов остаются с литеральным @', () => {
    const sanitized = sanitizeI18nMessages(ru)
    const i = makeI18n('ru', { ru: sanitized })
    expect(i.global.t('protection.ui.mentions_modal_body')).toContain('@username')
    expect(i.global.t('protection.channel_posts_modal.trusted_senders_title')).toContain('@username')
  })
})

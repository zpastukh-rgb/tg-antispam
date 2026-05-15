/**
 * Рекурсивный санитайзер сообщений vue-i18n.
 *
 * Проблема: vue-i18n 9 при компиляции строки видит `@<буква>` и пытается
 * распарсить её как linked-message (`@:key` или `@.modifier:key`). Если за
 * `@` идёт идентификатор без двоеточия, парсер бросает `SyntaxError: Invalid
 * linked format`. У нас в локалях ~20 строк с `@username`, `@manager` и т.п.
 *
 * Решение: до передачи в `createI18n` пробегаем по дереву сообщений и
 * заменяем литеральные `@<word-char>` на штатный escape vue-i18n
 * `{'@'}<word-char>` (literal interpolation), который рендерится в `@`
 * без триггера linked-парсера.
 *
 * Что НЕ трогаем:
 *  - уже экранированные `{'@'}...`
 *  - валидные linked: `@:foo.bar`, `@.lower:foo.bar`
 *  - email-подобное `name@host` (символ `@` идёт после буквы/цифры)
 */

/**
 * Регексп ловит `@` перед ЛЮБОЙ буквой (включая кириллицу `@ник`, греческую и т.п.)
 * или подчёркиванием — но не после буквы/цифры (так оставляем `name@host` нетронутым).
 *
 * Изначально регексп покрывал только `[A-Za-z_]` — и пропускал `@ник` в
 * `protection.welcome_modal.placeholders_hint` (RU), что валило vue-i18n compiler
 * на render. С `\p{L}` ловим все буквы Unicode.
 */
const AT_RE = /(^|[^\p{L}\p{N}])@([\p{L}_])/gu

/** Не трогаем `@:` и `@.` — это валидный синтаксис vue-i18n linked. */
function isLinkedSyntax(str, atIdx) {
  const next = str[atIdx + 1]
  return next === ':' || next === '.'
}

/** Заменяет проблемные `@<буква>` на `{'@'}<буква>` в одной строке. */
export function sanitizeI18nString(s) {
  if (typeof s !== 'string' || s.length === 0) return s
  if (s.indexOf('@') === -1) return s
  return s.replace(AT_RE, (match, prefix, nextChar, offset) => {
    const atIdx = offset + prefix.length
    if (isLinkedSyntax(s, atIdx)) return match
    return `${prefix}{'@'}${nextChar}`
  })
}

/** Рекурсивный обход объекта сообщений vue-i18n: dict / array / string. */
export function sanitizeI18nMessages(node) {
  if (node == null) return node
  if (typeof node === 'string') return sanitizeI18nString(node)
  if (Array.isArray(node)) return node.map((it) => sanitizeI18nMessages(it))
  if (typeof node === 'object') {
    const out = {}
    for (const k of Object.keys(node)) {
      out[k] = sanitizeI18nMessages(node[k])
    }
    return out
  }
  return node
}

/**
 * Рекурсивный санитайзер сообщений vue-i18n.
 *
 * Проблема: vue-i18n 9 при компиляции строки видит `@` как возможное начало
 * linked-message (`@:key` или `@.modifier:key`). Литералы вроде `@username`,
 * кириллического `@ник`, а также одиночная собака в скобках `(без @)` /
 * `(without @)` дают SyntaxError при компиляции или ломают рендер — модалки
 * (в т.ч. медиа) открываются «пустым экраном».
 *
 * Решение: любой `@`, который не является:
 *   - уже экранированным `{'@'}`,
 *   - валидным linked (`@:` или `@.` сразу после `@`),
 *   - частью email (`буква|цифра` перед `@`),
 * заменяем на штатный escape vue-i18n `{'@'}` (literal).
 */

/** `@:` и `@.` — валидный префикс linked в vue-i18n */
function isLinkedSyntax(str, atIdx) {
  const next = str[atIdx + 1]
  return next === ':' || next === '.'
}

/** Уже записано как литерал `{'@'}` в сообщении */
function isEscapedLiteralAt(s, i) {
  return (
    i >= 2 &&
    i + 2 < s.length &&
    s[i - 2] === '{' &&
    s[i - 1] === "'" &&
    s[i] === '@' &&
    s[i + 1] === "'" &&
    s[i + 2] === '}'
  )
}

/** Заменяет проблемные `@` на `{'@'}` в одной строке. */
export function sanitizeI18nString(s) {
  if (typeof s !== 'string' || s.length === 0) return s
  if (s.indexOf('@') === -1) return s

  let out = ''
  for (let i = 0; i < s.length; i++) {
    const ch = s[i]
    if (ch !== '@') {
      out += ch
      continue
    }
    if (isEscapedLiteralAt(s, i)) {
      out += ch
      continue
    }
    if (isLinkedSyntax(s, i)) {
      out += ch
      continue
    }
    const prev = i > 0 ? s[i - 1] : ''
    if (/\p{L}|\p{N}/u.test(prev)) {
      out += ch
      continue
    }
    out += "{'@'}"
  }
  return out
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

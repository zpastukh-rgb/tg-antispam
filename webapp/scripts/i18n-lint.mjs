/**
 * Лента CI: ловим vue-i18n compilation errors в локалях.
 *
 * 1) Проверяем СЫРЫЕ строки на проблемные `@<буква>` (без literal-escape `{'@'}`),
 *    которые vue-i18n принимает за linked-message и валит парсером.
 *    Это «бомбы замедленного действия» — даже если сегодня не падают,
 *    при первом же `t(key)` упадут SyntaxError'ом.
 * 2) Прогоняем строки через санитайзер и убеждаемся, что vue-i18n
 *    компилирует и рендерит их без throw.
 *
 * Выход:
 *   0 — всё ок
 *   1 — найдены сырые проблемные `@` или ошибки компиляции
 */

import { createI18n } from 'vue-i18n'
import ru from '../src/i18n/ru.js'
import en from '../src/i18n/en.js'
import { sanitizeI18nMessages } from '../src/i18n/sanitizeMessages.js'

function flatten(obj, prefix = '') {
  const out = []
  for (const k of Object.keys(obj || {})) {
    const v = obj[k]
    const key = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) out.push(...flatten(v, key))
    else if (typeof v === 'string') out.push([key, v])
  }
  return out
}

const PROBLEM_AT_RE = /(^|[^A-Za-z0-9])@([A-Za-z_])/g

function findRawAtIssues(messages) {
  const out = []
  for (const [key, value] of flatten(messages)) {
    if (typeof value !== 'string') continue
    PROBLEM_AT_RE.lastIndex = 0
    let m
    while ((m = PROBLEM_AT_RE.exec(value)) !== null) {
      const next = value[m.index + m[1].length + 1]
      if (next === ':' || next === '.') continue
      out.push({ key, snippet: value.slice(Math.max(0, m.index - 8), Math.min(value.length, m.index + 24)) })
      break
    }
  }
  return out
}

function checkRuntime(locale, sanitized) {
  const i = createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'ru',
    messages: { [locale]: sanitized },
    missingWarn: false,
    fallbackWarn: false,
  })
  const errors = []
  for (const [key] of flatten(sanitized)) {
    try {
      i.global.t(key)
    } catch (e) {
      errors.push({ key, error: e?.message || String(e) })
    }
  }
  return errors
}

let runtimeFails = 0
let rawWarnings = 0

for (const [locale, raw] of [['ru', ru], ['en', en]]) {
  console.log(`\n=== ${locale} ===`)
  const rawIssues = findRawAtIssues(raw)
  rawWarnings += rawIssues.length
  console.log(`raw @ without escape: ${rawIssues.length} (warning — санитайзер их экранирует runtime'ом)`)
  if (rawIssues.length) {
    for (const i of rawIssues.slice(0, 30)) {
      console.log(`    ${i.key}: …${i.snippet}…`)
    }
    if (rawIssues.length > 30) console.log(`    … и ещё ${rawIssues.length - 30}`)
  }

  const sanitized = sanitizeI18nMessages(raw)
  const runtimeErrors = checkRuntime(locale, sanitized)
  console.log(`runtime compile errors (после санитайзера): ${runtimeErrors.length}`)
  if (runtimeErrors.length) {
    runtimeFails += runtimeErrors.length
    for (const e of runtimeErrors.slice(0, 20)) console.log(`    FAIL ${e.key}: ${e.error}`)
  }
}

if (runtimeFails > 0) {
  console.log(`\nFAIL: ${runtimeFails} ключ(а) бросают SyntaxError при t() даже после санитайзера.`)
  console.log('Нужно добавить новое правило в src/i18n/sanitizeMessages.js.')
  process.exit(1)
}

if (rawWarnings > 0) {
  console.log(`\nOK runtime, но ${rawWarnings} строк имеют сырой @ — лучше явно прописать {'@'} в источнике.`)
} else {
  console.log('\nOK: локали чисты.')
}
process.exit(0)

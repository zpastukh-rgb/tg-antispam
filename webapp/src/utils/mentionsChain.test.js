/**
 * Интеграционный тест цепочки «Упоминания»: симулирует тап по плитке,
 * проверяет, что гранулярная vanilla-модалка появилась в DOM, что переключение
 * тогглов вызывает onUpdateRule с правильным телом, и что закрытие очищает узел.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { runMentionsChain, MENTION_FILTER_KINDS } from './mentionsChain.js'
import { isMentionsGranularVanillaModalOpen, closeMentionsGranularVanillaModal } from './mentionsGranularVanillaModal.js'

const i18n = {
  'protection.ui.mentions_modal_title': '💬 Упоминания',
  'protection.ui.mentions_modal_hint': 'Выбери что считать упоминанием.',
  'protection.ui.mention_mass_enabled': 'Массовые упоминания',
  'protection.ui.mention_mass_threshold': 'Порог',
}
const t = (key) => i18n[key] ?? ''

function makeRule(overrides = {}) {
  const base = { filter_mentions: false, filter_mention_mass_enabled: false, filter_mention_mass_threshold: 5 }
  for (const k of MENTION_FILTER_KINDS) base[k.field] = false
  return { ...base, ...overrides }
}

describe('mentionsChain (granular)', () => {
  beforeEach(() => {
    closeMentionsGranularVanillaModal()
    document.body.innerHTML = ''
  })
  afterEach(() => {
    closeMentionsGranularVanillaModal()
    document.body.innerHTML = ''
  })

  it('открывает модалку при наличии rule и закрывает по крестику', () => {
    runMentionsChain({ rule: makeRule(), t, onUpdateRule: () => {} })
    expect(isMentionsGranularVanillaModalOpen()).toBe(true)
    const node = document.querySelector('[data-guard-protection-filter-modal="mentions"]')
    expect(node).toBeTruthy()
    document.querySelector('[data-guard-mg-close]').click()
    expect(isMentionsGranularVanillaModalOpen()).toBe(false)
  })

  it('тоггл «bots» вызывает onUpdateRule({ filter_mention_bots: true })', () => {
    const onUpdateRule = vi.fn(() => Promise.resolve())
    runMentionsChain({ rule: makeRule(), t, onUpdateRule })
    const switches = document.querySelectorAll('[role="switch"]')
    // Первые 8 тогглов в порядке MENTION_FILTER_KINDS, последний — массовые.
    const botsIdx = MENTION_FILTER_KINDS.findIndex((k) => k.field === 'filter_mention_bots')
    switches[botsIdx].click()
    expect(onUpdateRule).toHaveBeenCalledWith({ filter_mention_bots: true })
  })

  it('тоггл «mass» вызывает onUpdateRule({ filter_mention_mass_enabled: true })', () => {
    const onUpdateRule = vi.fn(() => Promise.resolve())
    runMentionsChain({ rule: makeRule(), t, onUpdateRule })
    const switches = document.querySelectorAll('[role="switch"]')
    // mass — самый последний тоггл (после 8 типов).
    switches[MENTION_FILTER_KINDS.length].click()
    expect(onUpdateRule).toHaveBeenCalledWith({ filter_mention_mass_enabled: true })
  })

  it('изменение слайдера порога массовых вызывает onUpdateRule с правильным числом', () => {
    const onUpdateRule = vi.fn(() => Promise.resolve())
    runMentionsChain({ rule: makeRule({ filter_mention_mass_enabled: true, filter_mention_mass_threshold: 5 }), t, onUpdateRule })
    const slider = document.querySelector('input[type="range"]')
    expect(slider).toBeTruthy()
    slider.value = '7'
    slider.dispatchEvent(new Event('input', { bubbles: true }))
    expect(onUpdateRule).toHaveBeenCalledWith({ filter_mention_mass_threshold: 7 })
  })

  it('legacy filter_mentions=true и все гранулы false → тихий сброс legacy', () => {
    const onUpdateRule = vi.fn(() => Promise.resolve())
    const rule = makeRule({ filter_mentions: true })
    runMentionsChain({ rule, t, onUpdateRule })
    // Должен сразу запатчить filter_mentions=false.
    expect(onUpdateRule).toHaveBeenCalledWith({ filter_mentions: false })
    expect(rule.filter_mentions).toBe(false)
  })

  it('повторный запуск не плодит дубликаты', () => {
    runMentionsChain({ rule: makeRule(), t, onUpdateRule: () => {} })
    runMentionsChain({ rule: makeRule(), t, onUpdateRule: () => {} })
    runMentionsChain({ rule: makeRule(), t, onUpdateRule: () => {} })
    const nodes = document.querySelectorAll('[data-guard-protection-filter-modal="mentions"]')
    expect(nodes.length).toBe(1)
  })

  it('без rule не открывает модалку', () => {
    runMentionsChain({ rule: null, t, onUpdateRule: () => {} })
    expect(isMentionsGranularVanillaModalOpen()).toBe(false)
  })

  it('бросающий t для одного ключа не валит цепочку — fallback-текст', () => {
    const throwingT = (key) => {
      if (key === 'protection.ui.mentions_modal_hint') throw new SyntaxError('Invalid linked format')
      return i18n[key] ?? ''
    }
    runMentionsChain({ rule: makeRule(), t: throwingT, onUpdateRule: () => {} })
    expect(isMentionsGranularVanillaModalOpen()).toBe(true)
  })

  it('rejected promise от onUpdateRule откатывает локальное значение rule', async () => {
    const onUpdateRule = vi.fn(() => Promise.reject(new Error('network')))
    const rule = makeRule()
    runMentionsChain({ rule, t, onUpdateRule })
    const switches = document.querySelectorAll('[role="switch"]')
    const usersIdx = MENTION_FILTER_KINDS.findIndex((k) => k.field === 'filter_mention_users')
    switches[usersIdx].click()
    expect(rule.filter_mention_users).toBe(true) // оптимистично
    await new Promise((r) => setTimeout(r, 0))
    expect(rule.filter_mention_users).toBe(false) // откат
  })
})

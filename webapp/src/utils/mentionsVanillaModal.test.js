/**
 * Покрывает всю цепочку «Упоминания» на vanilla-модалке, включая:
 *  - реальное добавление в document.body после openMentionsVanillaModal()
 *  - callback onChoose(true/false) при клике allow / forbid
 *  - удаление узла при выборе и при клике по бэкдропу
 *  - повторный open не плодит дубликаты
 *  - стилизация allow/forbid соответствует текущему состоянию currentForbid
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import {
  openMentionsVanillaModal,
  closeMentionsVanillaModal,
  isMentionsVanillaModalOpen,
  buildMentionsModalButtonStyle,
  buildMentionsModalElement,
} from './mentionsVanillaModal.js'

function commonOpts(overrides = {}) {
  return {
    titleText: 'Упоминания',
    bodyText: 'Помечает сообщения с @username',
    allowText: 'Разрешено',
    forbidText: 'Запрещено',
    currentForbid: false,
    onChoose: () => {},
    ...overrides,
  }
}

describe('buildMentionsModalButtonStyle', () => {
  it('allow выделен, когда currentForbid=false', () => {
    const s = buildMentionsModalButtonStyle('allow', false)
    expect(s).toMatch(/linear-gradient/)
    expect(s).toMatch(/#8fd41a/)
  })
  it('allow в idle, когда currentForbid=true', () => {
    const s = buildMentionsModalButtonStyle('allow', true)
    expect(s).not.toMatch(/#8fd41a/)
  })
  it('forbid выделен, когда currentForbid=true', () => {
    const s = buildMentionsModalButtonStyle('forbid', true)
    expect(s).toMatch(/#f43f5e|#dc2626/)
  })
  it('forbid в idle, когда currentForbid=false', () => {
    const s = buildMentionsModalButtonStyle('forbid', false)
    expect(s).not.toMatch(/#f43f5e/)
  })
})

describe('buildMentionsModalElement', () => {
  it('создаёт корень с правильными data-атрибутами и панелью', () => {
    const { root, panel, allowBtn, forbidBtn, title, body, closeBtn } = buildMentionsModalElement(commonOpts())
    expect(root.id).toBe('guard-mentions-vanilla-modal-root')
    expect(root.getAttribute('data-guard-protection-filter-modal')).toBe('mentions')
    expect(root.getAttribute('data-guard-protection-filter-modals-anchor')).toBe('')
    expect(root.getAttribute('role')).toBe('dialog')
    expect(panel.getAttribute('data-guard-protection-filter-modal-panel')).toBe('')
    expect(allowBtn.getAttribute('data-guard-mentions-vanilla-allow')).toBe('')
    expect(forbidBtn.getAttribute('data-guard-mentions-vanilla-forbid')).toBe('')
    expect(title.textContent).toBe('Упоминания')
    expect(body.textContent).toBe('Помечает сообщения с @username')
    expect(closeBtn.textContent).toBe('✕')
  })
})

describe('openMentionsVanillaModal', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('добавляет узел в DOM (в documentElement или body)', () => {
    expect(isMentionsVanillaModalOpen()).toBe(false)
    openMentionsVanillaModal(commonOpts())
    expect(isMentionsVanillaModalOpen()).toBe(true)
    const node = document.querySelector('[data-guard-protection-filter-modal="mentions"]')
    expect(node).toBeTruthy()
    // Приоритет — <html>, fallback — <body>; оба считаются успехом.
    expect([document.documentElement, document.body]).toContain(node.parentNode)
  })

  it('повторный open не плодит дубликаты', () => {
    openMentionsVanillaModal(commonOpts())
    openMentionsVanillaModal(commonOpts())
    openMentionsVanillaModal(commonOpts())
    const nodes = document.querySelectorAll('[data-guard-protection-filter-modal="mentions"]')
    expect(nodes.length).toBe(1)
  })

  it('клик по allow → onChoose(false) и узел удаляется', () => {
    const onChoose = vi.fn()
    openMentionsVanillaModal(commonOpts({ onChoose }))
    const allow = document.querySelector('[data-guard-mentions-vanilla-allow]')
    expect(allow).toBeTruthy()
    allow.click()
    expect(onChoose).toHaveBeenCalledTimes(1)
    expect(onChoose).toHaveBeenCalledWith(false)
    expect(isMentionsVanillaModalOpen()).toBe(false)
  })

  it('клик по forbid → onChoose(true) и узел удаляется', () => {
    const onChoose = vi.fn()
    openMentionsVanillaModal(commonOpts({ onChoose }))
    const forbid = document.querySelector('[data-guard-mentions-vanilla-forbid]')
    expect(forbid).toBeTruthy()
    forbid.click()
    expect(onChoose).toHaveBeenCalledTimes(1)
    expect(onChoose).toHaveBeenCalledWith(true)
    expect(isMentionsVanillaModalOpen()).toBe(false)
  })

  it('клик по крестику закрывает без onChoose', () => {
    const onChoose = vi.fn()
    const onClose = vi.fn()
    openMentionsVanillaModal(commonOpts({ onChoose, onClose }))
    const close = document.querySelector('[data-guard-mentions-vanilla-close]')
    expect(close).toBeTruthy()
    close.click()
    expect(onChoose).not.toHaveBeenCalled()
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(isMentionsVanillaModalOpen()).toBe(false)
  })

  it('клик по бэкдропу (по самому root) закрывает', () => {
    const onChoose = vi.fn()
    const onClose = vi.fn()
    openMentionsVanillaModal(commonOpts({ onChoose, onClose }))
    const root = document.getElementById('guard-mentions-vanilla-modal-root')
    expect(root).toBeTruthy()
    root.click()
    expect(onChoose).not.toHaveBeenCalled()
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(isMentionsVanillaModalOpen()).toBe(false)
  })

  it('клик внутри панели не закрывает', () => {
    openMentionsVanillaModal(commonOpts())
    const panel = document.querySelector('[data-guard-protection-filter-modal-panel]')
    expect(panel).toBeTruthy()
    panel.click()
    expect(isMentionsVanillaModalOpen()).toBe(true)
  })

  it('closeMentionsVanillaModal удаляет узел', () => {
    openMentionsVanillaModal(commonOpts())
    expect(isMentionsVanillaModalOpen()).toBe(true)
    closeMentionsVanillaModal()
    expect(isMentionsVanillaModalOpen()).toBe(false)
  })

  it('начальное состояние currentForbid=true → forbid стилизован, allow idle', () => {
    openMentionsVanillaModal(commonOpts({ currentForbid: true }))
    const allow = document.querySelector('[data-guard-mentions-vanilla-allow]')
    const forbid = document.querySelector('[data-guard-mentions-vanilla-forbid]')
    expect(forbid.style.cssText).toMatch(/#f43f5e|#dc2626/)
    expect(allow.style.cssText).not.toMatch(/#8fd41a/)
  })

  it('начальное состояние currentForbid=false → allow стилизован, forbid idle', () => {
    openMentionsVanillaModal(commonOpts({ currentForbid: false }))
    const allow = document.querySelector('[data-guard-mentions-vanilla-allow]')
    const forbid = document.querySelector('[data-guard-mentions-vanilla-forbid]')
    expect(allow.style.cssText).toMatch(/#8fd41a/)
    expect(forbid.style.cssText).not.toMatch(/#f43f5e/)
  })

  it('переданные пустые тексты не валят рендер', () => {
    openMentionsVanillaModal({
      titleText: '',
      bodyText: '',
      allowText: '',
      forbidText: '',
      currentForbid: false,
      onChoose: () => {},
    })
    expect(isMentionsVanillaModalOpen()).toBe(true)
  })
})

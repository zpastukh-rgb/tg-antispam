/**
 * Тесты vanilla-fallback модалки «Приветствие новичков».
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import {
  openWelcomeFallbackModal,
  closeWelcomeFallbackModal,
  isWelcomeFallbackModalOpen,
} from './welcomeFallbackModal.js'

function commonOpts(overrides = {}) {
  return {
    titleText: 'Приветствие новичков',
    bodyText: 'Текст для новых участников.',
    enableText: 'Включить',
    disableText: 'Выключить',
    cancelText: 'Отмена',
    currentEnabled: false,
    onToggle: () => {},
    ...overrides,
  }
}

describe('welcomeFallbackModal', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    document.documentElement.querySelectorAll('[data-guard-protection-welcome-fallback]').forEach((n) => n.remove())
  })
  afterEach(() => {
    closeWelcomeFallbackModal()
    document.body.innerHTML = ''
  })

  it('добавляет узел в DOM', () => {
    expect(isWelcomeFallbackModalOpen()).toBe(false)
    openWelcomeFallbackModal(commonOpts())
    expect(isWelcomeFallbackModalOpen()).toBe(true)
  })

  it('повторный open не плодит дубликаты', () => {
    openWelcomeFallbackModal(commonOpts())
    openWelcomeFallbackModal(commonOpts())
    openWelcomeFallbackModal(commonOpts())
    const nodes = document.querySelectorAll('[data-guard-protection-welcome-fallback]')
    expect(nodes.length).toBe(1)
  })

  it('клик по enable → onToggle(true) и закрытие', () => {
    const onToggle = vi.fn()
    openWelcomeFallbackModal(commonOpts({ onToggle }))
    document.querySelector('[data-guard-welcome-fallback-enable]').click()
    expect(onToggle).toHaveBeenCalledWith(true)
    expect(isWelcomeFallbackModalOpen()).toBe(false)
  })

  it('клик по disable → onToggle(false) и закрытие', () => {
    const onToggle = vi.fn()
    openWelcomeFallbackModal(commonOpts({ currentEnabled: true, onToggle }))
    document.querySelector('[data-guard-welcome-fallback-disable]').click()
    expect(onToggle).toHaveBeenCalledWith(false)
    expect(isWelcomeFallbackModalOpen()).toBe(false)
  })

  it('клик по × закрывает без onToggle', () => {
    const onToggle = vi.fn()
    const onClose = vi.fn()
    openWelcomeFallbackModal(commonOpts({ onToggle, onClose }))
    document.querySelector('[data-guard-welcome-fallback-close]').click()
    expect(onToggle).not.toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
    expect(isWelcomeFallbackModalOpen()).toBe(false)
  })

  it('клик по бэкдропу закрывает без onToggle', () => {
    const onToggle = vi.fn()
    const onClose = vi.fn()
    openWelcomeFallbackModal(commonOpts({ onToggle, onClose }))
    const root = document.querySelector('[data-guard-protection-welcome-fallback]')
    root.click()
    expect(onToggle).not.toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
    expect(isWelcomeFallbackModalOpen()).toBe(false)
  })

  it('onToggle бросает → модалка всё равно закрывается', () => {
    const onToggle = vi.fn(() => {
      throw new Error('boom')
    })
    openWelcomeFallbackModal(commonOpts({ onToggle }))
    document.querySelector('[data-guard-welcome-fallback-enable]').click()
    expect(onToggle).toHaveBeenCalled()
    expect(isWelcomeFallbackModalOpen()).toBe(false)
  })
})

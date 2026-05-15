/**
 * Vanilla-JS модалка «Упоминания» с гранулярными тогглами.
 *
 * Зачем vanilla, а не Vue: исторически Vue v-if для модалки упоминаний не отрисовывался
 * в TMA (см. mentionsVanillaModal.js). Чтобы не рисковать, делаем гранулярную модалку
 * тоже на vanilla. Стиль — тёмный (#101013), iOS-style тогглы, без backdrop-blur.
 *
 * Контракт opts:
 *   {
 *     titleText, hintText, massEnabledText, massThresholdText, // i18n
 *     kinds: [{key, field, icon, label}],                      // 9 тогглов
 *     values: { [field]: boolean },                            // текущие значения
 *     mass: { enabled: boolean, threshold: number },           // для отдельного блока
 *     onToggleKind: (field, next) => void,                     // переключение тоггла
 *     onMassToggle: (enabled) => void,                          // вкл/выкл массовых
 *     onMassThreshold: (value) => void,                         // изменение порога
 *     onClose?: () => void,
 *   }
 */

import { guardFilterChain } from './guardDebugLog.js'

const ROOT_ID = 'guard-mentions-granular-vanilla-modal-root'
const PANEL_ATTR = 'data-guard-protection-filter-modal'
const ANCHOR_ATTR = 'data-guard-protection-filter-modals-anchor'

function errToObj(e) {
  if (!e) return null
  if (typeof e !== 'object') return { value: String(e) }
  return { name: e.name ?? null, message: e.message ?? null, stack: typeof e.stack === 'string' ? e.stack.slice(0, 500) : null }
}

function removeExistingRoot() {
  try {
    const old = document.getElementById(ROOT_ID)
    if (old?.parentNode) {
      old.parentNode.removeChild(old)
      guardFilterChain('MentionsGranularVanilla', 'removed_existing', { ts: Date.now() })
      return true
    }
  } catch (e) {
    guardFilterChain('MentionsGranularVanilla', 'removed_existing:error', errToObj(e))
  }
  return false
}

/**
 * Создаёт iOS-style тоггл (track + knob). Возвращает { wrap, setOn(value) }.
 * Клик уже навешан на wrap и зовёт onChange(next).
 */
export function buildIosToggle(initialOn, onChange) {
  const wrap = document.createElement('button')
  wrap.type = 'button'
  wrap.setAttribute('role', 'switch')
  wrap.style.cssText = [
    'position:relative',
    'flex-shrink:0',
    'width:51px',
    'height:31px',
    'border-radius:9999px',
    'border:1px solid rgba(255,255,255,0.14)',
    'cursor:pointer',
    'transition:background 200ms ease, border-color 200ms ease',
    'padding:0',
    'background:rgba(255,255,255,0.09)',
  ].join(';')
  const knob = document.createElement('span')
  knob.style.cssText = [
    'position:absolute',
    'left:3px',
    'top:50%',
    'width:25px',
    'height:25px',
    'border-radius:9999px',
    'background:#ffffff',
    'box-shadow:0 2px 6px rgba(0,0,0,0.4)',
    'transition:transform 200ms ease',
    'transform:translate3d(0,-50%,0)',
  ].join(';')
  wrap.appendChild(knob)

  function setOn(on) {
    if (on) {
      wrap.style.background = 'rgba(16,185,129,0.32)'
      wrap.style.borderColor = 'rgba(52,211,153,0.4)'
      knob.style.transform = 'translate3d(20px,-50%,0)'
      wrap.setAttribute('aria-checked', 'true')
    } else {
      wrap.style.background = 'rgba(255,255,255,0.09)'
      wrap.style.borderColor = 'rgba(255,255,255,0.14)'
      knob.style.transform = 'translate3d(0,-50%,0)'
      wrap.setAttribute('aria-checked', 'false')
    }
  }
  setOn(!!initialOn)

  let current = !!initialOn
  wrap.addEventListener('click', () => {
    current = !current
    setOn(current)
    try { onChange?.(current) } catch (e) { guardFilterChain('MentionsGranularVanilla', 'toggle:onChange_throw', errToObj(e)) }
  })

  return { wrap, setOn }
}

/** Создать DOM-узел гранулярной модалки. Чистая функция — удобно для тестов. */
export function buildMentionsGranularModalElement(opts) {
  const root = document.createElement('div')
  root.id = ROOT_ID
  root.setAttribute(PANEL_ATTR, 'mentions')
  root.setAttribute(ANCHOR_ATTR, '')
  root.setAttribute('role', 'dialog')
  root.setAttribute('aria-modal', 'true')
  root.style.cssText = [
    'position:fixed',
    'top:0',
    'left:0',
    'right:0',
    'bottom:0',
    'z-index:2147483000',
    'display:flex',
    'align-items:center',
    'justify-content:center',
    'background:rgba(0,0,0,0.78)',
    'padding:16px',
    'box-sizing:border-box',
    'pointer-events:auto',
  ].join(';')

  const panel = document.createElement('div')
  panel.setAttribute('data-guard-protection-filter-modal-panel', '')
  panel.style.cssText = [
    'width:100%',
    'max-width:28rem',
    'max-height:90vh',
    'overflow-y:auto',
    'background:#101013',
    'border:1px solid rgba(255,255,255,0.10)',
    'border-radius:16px',
    'box-shadow:0 24px 60px -20px rgba(0,0,0,0.9)',
    'padding:16px',
    'color:#e5e7eb',
    'box-sizing:border-box',
    'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif',
  ].join(';')

  const head = document.createElement('div')
  head.style.cssText = 'display:flex;align-items:center;justify-content:space-between;margin-bottom:8px'
  const title = document.createElement('h3')
  title.style.cssText = 'margin:0;font-size:14px;font-weight:600;color:#ffffff'
  title.textContent = String(opts?.titleText || 'Упоминания')
  const closeBtn = document.createElement('button')
  closeBtn.type = 'button'
  closeBtn.setAttribute('data-guard-mg-close', '')
  closeBtn.style.cssText = 'background:transparent;border:0;color:#a1a1aa;font-size:14px;padding:4px 8px;cursor:pointer'
  closeBtn.textContent = '✕'
  closeBtn.setAttribute('aria-label', 'Close')
  head.appendChild(title)
  head.appendChild(closeBtn)

  const hint = document.createElement('p')
  hint.style.cssText = 'margin:0 0 12px;font-size:12px;color:#a1a1aa;line-height:1.45'
  hint.textContent = String(opts?.hintText || '')

  const list = document.createElement('ul')
  list.style.cssText = 'list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:8px'

  const kindToggles = {}
  for (const k of (opts?.kinds || [])) {
    const li = document.createElement('li')
    li.style.cssText = [
      'display:flex',
      'align-items:center',
      'justify-content:space-between',
      'gap:12px',
      'padding:10px 12px',
      'border:1px solid rgba(255,255,255,0.06)',
      'background:rgba(255,255,255,0.025)',
      'border-radius:12px',
    ].join(';')
    const left = document.createElement('div')
    left.style.cssText = 'display:flex;align-items:center;gap:10px;min-width:0;flex:1'
    const icon = document.createElement('span')
    icon.style.cssText = 'font-size:18px;line-height:1'
    icon.textContent = String(k.icon || '•')
    const lbl = document.createElement('span')
    lbl.style.cssText = 'font-size:13px;font-weight:500;color:#ffffff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'
    lbl.textContent = String(k.label || k.key)
    left.appendChild(icon)
    left.appendChild(lbl)

    const initialOn = !!(opts?.values?.[k.field])
    const toggle = buildIosToggle(initialOn, (next) => {
      try { opts?.onToggleKind?.(k.field, next) } catch (e) { guardFilterChain('MentionsGranularVanilla', 'toggleKind:throw', { field: k.field, ...errToObj(e) }) }
    })
    kindToggles[k.field] = toggle
    li.appendChild(left)
    li.appendChild(toggle.wrap)
    list.appendChild(li)
  }

  // Блок «Массовые упоминания» — отдельная карточка с тогглом и слайдером.
  const massCard = document.createElement('div')
  massCard.style.cssText = [
    'margin-top:12px',
    'padding:12px',
    'border:1px solid rgba(255,255,255,0.06)',
    'background:rgba(255,255,255,0.025)',
    'border-radius:12px',
    'display:flex',
    'flex-direction:column',
    'gap:10px',
  ].join(';')
  const massHead = document.createElement('div')
  massHead.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:12px'
  const massLeft = document.createElement('div')
  massLeft.style.cssText = 'display:flex;align-items:center;gap:10px;min-width:0;flex:1'
  const massIcon = document.createElement('span')
  massIcon.style.cssText = 'font-size:18px;line-height:1'
  massIcon.textContent = '💥'
  const massLbl = document.createElement('span')
  massLbl.style.cssText = 'font-size:13px;font-weight:500;color:#ffffff'
  massLbl.textContent = String(opts?.massEnabledText || 'Массовые упоминания')
  massLeft.appendChild(massIcon)
  massLeft.appendChild(massLbl)
  const massToggle = buildIosToggle(!!opts?.mass?.enabled, (next) => {
    try { opts?.onMassToggle?.(next) } catch (e) { guardFilterChain('MentionsGranularVanilla', 'massToggle:throw', errToObj(e)) }
    sliderRow.style.display = next ? 'flex' : 'none'
  })
  massHead.appendChild(massLeft)
  massHead.appendChild(massToggle.wrap)

  const sliderRow = document.createElement('div')
  sliderRow.style.cssText = 'display:flex;align-items:center;gap:10px;font-size:12px;color:#a1a1aa'
  sliderRow.style.display = opts?.mass?.enabled ? 'flex' : 'none'
  const sliderLbl = document.createElement('span')
  sliderLbl.style.cssText = 'flex-shrink:0'
  sliderLbl.textContent = String(opts?.massThresholdText || 'Порог')
  const slider = document.createElement('input')
  slider.type = 'range'
  slider.min = '3'
  slider.max = '20'
  slider.step = '1'
  const initialThreshold = Math.max(3, Math.min(20, Number(opts?.mass?.threshold) || 5))
  slider.value = String(initialThreshold)
  slider.style.cssText = 'flex:1;accent-color:#10b981'
  const valueEl = document.createElement('span')
  valueEl.style.cssText = 'min-width:30px;text-align:right;color:#e5e7eb;font-weight:600'
  valueEl.textContent = `≥${initialThreshold}`
  slider.addEventListener('input', () => {
    const v = Math.max(3, Math.min(20, Number(slider.value) || 5))
    valueEl.textContent = `≥${v}`
    try { opts?.onMassThreshold?.(v) } catch (e) { guardFilterChain('MentionsGranularVanilla', 'massThreshold:throw', errToObj(e)) }
  })
  sliderRow.appendChild(sliderLbl)
  sliderRow.appendChild(slider)
  sliderRow.appendChild(valueEl)

  massCard.appendChild(massHead)
  massCard.appendChild(sliderRow)

  panel.appendChild(head)
  panel.appendChild(hint)
  panel.appendChild(list)
  panel.appendChild(massCard)
  root.appendChild(panel)

  return { root, panel, title, closeBtn, list, kindToggles, massToggle, slider, valueEl }
}

export function openMentionsGranularVanillaModal(opts) {
  guardFilterChain('MentionsGranularVanilla', 'enter', {
    ts: Date.now(),
    hasDocument: typeof document !== 'undefined',
    hasBody: typeof document !== 'undefined' && !!document.body,
    kinds: Array.isArray(opts?.kinds) ? opts.kinds.length : 0,
    massEnabled: !!opts?.mass?.enabled,
    massThreshold: Number(opts?.mass?.threshold) || 0,
  })
  if (typeof document === 'undefined') {
    guardFilterChain('MentionsGranularVanilla', 'abort:no_document', {})
    return null
  }
  if (!document.body && !document.documentElement) {
    guardFilterChain('MentionsGranularVanilla', 'abort:no_body_or_html', {})
    return null
  }
  removeExistingRoot()

  const els = buildMentionsGranularModalElement(opts || {})

  // Блок прокрутки фона (как в правиле webapp-modals.mdc).
  let prevBodyOverflow = ''
  try {
    prevBodyOverflow = document.body?.style?.overflow || ''
    if (document.body?.style) document.body.style.overflow = 'hidden'
  } catch {
    //
  }

  els.panel.addEventListener('click', (e) => e.stopPropagation())
  els.root.addEventListener('click', (e) => {
    if (e.target === els.root) {
      guardFilterChain('MentionsGranularVanilla', 'close_backdrop', { ts: Date.now() })
      closeMentionsGranularVanillaModal()
      try { document.body.style.overflow = prevBodyOverflow } catch { /* */ }
      try { opts?.onClose?.() } catch { /* */ }
    }
  })
  els.closeBtn.addEventListener('click', () => {
    guardFilterChain('MentionsGranularVanilla', 'close_x', { ts: Date.now() })
    closeMentionsGranularVanillaModal()
    try { document.body.style.overflow = prevBodyOverflow } catch { /* */ }
    try { opts?.onClose?.() } catch { /* */ }
  })

  // Приклеиваем в <html>, как и в основной vanilla-модалке.
  const host = document.documentElement || document.body
  try {
    host.appendChild(els.root)
  } catch (e) {
    guardFilterChain('MentionsGranularVanilla', 'append:error_to_documentElement', errToObj(e))
    try {
      document.body.appendChild(els.root)
    } catch (e2) {
      guardFilterChain('MentionsGranularVanilla', 'append:error_to_body', errToObj(e2))
      return null
    }
  }
  guardFilterChain('MentionsGranularVanilla', 'appended', {
    ts: Date.now(),
    parentTag: els.root.parentNode?.tagName ?? null,
  })
  return els.root
}

export function closeMentionsGranularVanillaModal() {
  return removeExistingRoot()
}

export function isMentionsGranularVanillaModalOpen() {
  try {
    return !!document.getElementById(ROOT_ID)
  } catch {
    return false
  }
}

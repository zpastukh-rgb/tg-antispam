/**
 * Vanilla-JS модалка «Упоминания» для экрана Защита.
 *
 * Зачем: в Telegram Mini App (WKWebView) Vue v-if для конкретно этой модалки
 * не добавлял узел в DOM ни через `<Teleport>`, ни in-place, ни `display:none/flex`.
 * Решено полностью обойти Vue и собирать DOM руками через document.createElement.
 *
 * Каждый шаг — лог в Railway (`guardFilterChain` с scope `MentionsVanilla`):
 *   - `enter` — вошли в функцию (опции, локаль, размер body)
 *   - `removed_existing` — удалён старый экземпляр (если был)
 *   - `created_root` — создан корневой div
 *   - `appended_to_body` — appendChild выполнен
 *   - `verify_in_dom` — querySelector видит ли узел
 *   - `delayed_verify` — повторная проверка через 50 / 250 ms (вдруг кто-то удалил)
 *   - `choose` / `close_self_click` / `close_explicit` — закрытия
 *
 * Никаких Vue ref / Teleport / Tailwind — только инлайн-стили.
 */

import { guardFilterChain } from './guardDebugLog.js'

/** Сериализация ошибки для filter-chain (guardWarn в проде не уходит на Railway). */
function errToObj(e) {
  if (!e) return null
  if (typeof e !== 'object') return { value: String(e) }
  return {
    name: e.name ?? null,
    message: e.message ?? null,
    stack: typeof e.stack === 'string' ? e.stack.slice(0, 500) : null,
  }
}

const ROOT_ID = 'guard-mentions-vanilla-modal-root'
const PANEL_ATTR = 'data-guard-protection-filter-modal'
const ANCHOR_ATTR = 'data-guard-protection-filter-modals-anchor'

/** Удалить старый экземпляр (если был): на повторный open не плодим лишних узлов. */
function removeExistingRoot() {
  try {
    const old = document.getElementById(ROOT_ID)
    if (old?.parentNode) {
      old.parentNode.removeChild(old)
      guardFilterChain('MentionsVanilla', 'removed_existing', { ts: Date.now() })
      return true
    }
  } catch (e) {
    guardFilterChain('MentionsVanilla', 'removed_existing:error', errToObj(e))
  }
  return false
}

/** Делает styled <button>; центр логики, чтобы тесты могли проверить корректный класс. */
export function buildMentionsModalButtonStyle(role, currentForbid) {
  const base =
    'min-height:44px;border-radius:12px;padding:10px 12px;font-size:13px;font-weight:600;cursor:pointer;border:1px solid rgba(255,255,255,0.14);transition:transform 80ms ease'
  const idle = `${base};background:rgba(255,255,255,0.06);color:#cbd5e1`
  const allowSelected = `${base};background:linear-gradient(180deg,#8fd41a,#65a30d);color:#0b1220;border-color:rgba(132,204,22,0.55);box-shadow:0 8px 20px -10px rgba(132,204,22,0.55)`
  const forbidSelected = `${base};background:linear-gradient(90deg,#f43f5e,#dc2626);color:#ffffff;border-color:rgba(244,63,94,0.55);box-shadow:0 8px 20px -10px rgba(239,68,68,0.75)`
  if (role === 'allow') return currentForbid ? idle : allowSelected
  if (role === 'forbid') return currentForbid ? forbidSelected : idle
  return idle
}

/** Создать DOM-узел модалки. Чистая функция, удобна для тестов. */
export function buildMentionsModalElement(opts) {
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
    'background:#0f172a',
    'border:1px solid rgba(255,255,255,0.15)',
    'border-radius:16px',
    'box-shadow:0 24px 60px -20px rgba(0,0,0,0.9)',
    'padding:16px',
    'color:#e2e8f0',
    'box-sizing:border-box',
    'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif',
  ].join(';')

  const head = document.createElement('div')
  head.style.cssText = 'display:flex;align-items:center;justify-content:space-between;margin-bottom:12px'
  const title = document.createElement('h3')
  title.setAttribute('data-guard-mentions-vanilla-title', '')
  title.style.cssText = 'margin:0;font-size:14px;font-weight:600;color:#ffffff'
  title.textContent = String(opts?.titleText || '')
  const closeBtn = document.createElement('button')
  closeBtn.type = 'button'
  closeBtn.setAttribute('data-guard-mentions-vanilla-close', '')
  closeBtn.style.cssText = 'background:transparent;border:0;color:#94a3b8;font-size:14px;padding:4px 8px;cursor:pointer'
  closeBtn.textContent = '✕'
  closeBtn.setAttribute('aria-label', 'Close')
  head.appendChild(title)
  head.appendChild(closeBtn)

  const body = document.createElement('p')
  body.setAttribute('data-guard-mentions-vanilla-body', '')
  body.style.cssText = 'margin:0 0 12px;font-size:11px;color:#94a3b8;line-height:1.45'
  body.textContent = String(opts?.bodyText || '')

  const grid = document.createElement('div')
  grid.style.cssText = 'display:grid;grid-template-columns:1fr 1fr;gap:8px'

  const allowBtn = document.createElement('button')
  allowBtn.type = 'button'
  allowBtn.setAttribute('data-guard-mentions-vanilla-allow', '')
  allowBtn.style.cssText = buildMentionsModalButtonStyle('allow', !!opts?.currentForbid)
  allowBtn.textContent = String(opts?.allowText || 'Разрешено')

  const forbidBtn = document.createElement('button')
  forbidBtn.type = 'button'
  forbidBtn.setAttribute('data-guard-mentions-vanilla-forbid', '')
  forbidBtn.style.cssText = buildMentionsModalButtonStyle('forbid', !!opts?.currentForbid)
  forbidBtn.textContent = String(opts?.forbidText || 'Запрещено')

  grid.appendChild(allowBtn)
  grid.appendChild(forbidBtn)

  panel.appendChild(head)
  panel.appendChild(body)
  panel.appendChild(grid)
  root.appendChild(panel)

  return { root, panel, title, closeBtn, body, allowBtn, forbidBtn }
}

/**
 * Открыть vanilla-модалку «Упоминания».
 * @param {{
 *   titleText: string,
 *   bodyText: string,
 *   allowText: string,
 *   forbidText: string,
 *   currentForbid: boolean,
 *   onChoose: (forbid: boolean) => void,
 *   onClose?: () => void,
 * }} opts
 */
export function openMentionsVanillaModal(opts) {
  // Лог САМОЕ первое — даже если document/body отсутствует. guardFilterChain принимает любые extras.
  guardFilterChain('MentionsVanilla', 'enter', {
    ts: Date.now(),
    hasDocument: typeof document !== 'undefined',
    hasBody: typeof document !== 'undefined' && !!document.body,
    hasDocumentElement: typeof document !== 'undefined' && !!document.documentElement,
    titleLen: String(opts?.titleText || '').length,
    bodyLen: String(opts?.bodyText || '').length,
    currentForbid: !!opts?.currentForbid,
    bodyChildCountBefore: typeof document !== 'undefined' && document.body ? document.body.childElementCount : null,
  })
  if (typeof document === 'undefined') {
    guardFilterChain('MentionsVanilla', 'abort:no_document', {})
    return null
  }
  if (!document.body && !document.documentElement) {
    guardFilterChain('MentionsVanilla', 'abort:no_body_or_html', {})
    return null
  }

  removeExistingRoot()

  const els = buildMentionsModalElement(opts || {})
  guardFilterChain('MentionsVanilla', 'created_root', {
    ts: Date.now(),
    hasPanel: !!els.panel,
    hasAllow: !!els.allowBtn,
    hasForbid: !!els.forbidBtn,
  })

  // Слушатели — навешиваем ДО appendChild, чтобы не было гонок.
  els.panel.addEventListener('click', (e) => {
    e.stopPropagation()
  })
  els.root.addEventListener('click', (e) => {
    if (e.target === els.root) {
      guardFilterChain('MentionsVanilla', 'close_backdrop_click', { ts: Date.now() })
      closeMentionsVanillaModal()
      try {
        opts?.onClose?.()
      } catch {
        //
      }
    }
  })
  els.closeBtn.addEventListener('click', () => {
    guardFilterChain('MentionsVanilla', 'close_x', { ts: Date.now() })
    closeMentionsVanillaModal()
    try {
      opts?.onClose?.()
    } catch {
      //
    }
  })
  els.allowBtn.addEventListener('click', () => {
    guardFilterChain('MentionsVanilla', 'choose', { ts: Date.now(), forbid: false })
    try {
      opts?.onChoose?.(false)
    } finally {
      closeMentionsVanillaModal()
    }
  })
  els.forbidBtn.addEventListener('click', () => {
    guardFilterChain('MentionsVanilla', 'choose', { ts: Date.now(), forbid: true })
    try {
      opts?.onChoose?.(true)
    } finally {
      closeMentionsVanillaModal()
    }
  })

  // Приклеиваем в <html>, а не в body — body может быть внутри stacking-контекста экрана Защиты
  // (transform / filter / will-change на предках), и тогда z-index перебивается. <html> вне всего.
  const host = document.documentElement || document.body
  let appendStrategy = 'documentElement'
  try {
    host.appendChild(els.root)
  } catch (e) {
    guardFilterChain('MentionsVanilla', 'append:error_to_documentElement', errToObj(e))
    try {
      document.body.appendChild(els.root)
      appendStrategy = 'body_fallback'
    } catch (e2) {
      guardFilterChain('MentionsVanilla', 'append:error_to_body', errToObj(e2))
      return null
    }
  }
  guardFilterChain('MentionsVanilla', 'appended', {
    ts: Date.now(),
    strategy: appendStrategy,
    parentTag: els.root.parentNode?.tagName ?? null,
    bodyChildCountAfter: document.body?.childElementCount ?? null,
    htmlChildCountAfter: document.documentElement?.childElementCount ?? null,
  })

  // Проверка, что узел реально в DOM, видим ли он, и кто сверху.
  try {
    const probe = document.querySelector(`#${ROOT_ID}`)
    const probeBySel = document.querySelector(`[${PANEL_ATTR}="mentions"]`)
    const rect = els.root.getBoundingClientRect()
    let topElTag = null
    let topElId = null
    let topElIsModal = null
    try {
      const cx = Math.floor((rect.left + rect.right) / 2)
      const cy = Math.floor((rect.top + rect.bottom) / 2)
      const topEl = document.elementFromPoint(cx, cy)
      topElTag = topEl?.tagName ?? null
      topElId = topEl?.id ?? null
      topElIsModal = !!topEl && (topEl === els.root || els.root.contains(topEl))
    } catch {
      //
    }
    let computed = null
    try {
      const cs = window.getComputedStyle(els.root)
      computed = {
        display: cs.display,
        visibility: cs.visibility,
        opacity: cs.opacity,
        zIndex: cs.zIndex,
        position: cs.position,
        pointerEvents: cs.pointerEvents,
      }
    } catch {
      //
    }
    guardFilterChain('MentionsVanilla', 'verify_in_dom', {
      ts: Date.now(),
      byId: !!probe,
      bySelector: !!probeBySel,
      rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
      viewport: { w: window.innerWidth, h: window.innerHeight },
      computed,
      topAtCenter: { tag: topElTag, id: topElId, isOurModal: topElIsModal },
    })
  } catch (e) {
    guardFilterChain('MentionsVanilla', 'verify_in_dom:error', errToObj(e))
  }

  // Задержанные проверки — если кто-то снимет модалку.
  setTimeout(() => {
    try {
      const node = document.getElementById(ROOT_ID)
      guardFilterChain('MentionsVanilla', 'delayed_verify_50ms', {
        ts: Date.now(),
        present: !!node,
      })
    } catch {
      //
    }
  }, 50)
  setTimeout(() => {
    try {
      const node = document.getElementById(ROOT_ID)
      guardFilterChain('MentionsVanilla', 'delayed_verify_250ms', {
        ts: Date.now(),
        present: !!node,
      })
    } catch {
      //
    }
  }, 250)

  return els.root
}

/** Закрыть vanilla-модалку «Упоминания» (если открыта). */
export function closeMentionsVanillaModal() {
  return removeExistingRoot()
}

/** Проверка для отладки/тестов. */
export function isMentionsVanillaModalOpen() {
  try {
    return !!document.getElementById(ROOT_ID)
  } catch {
    return false
  }
}

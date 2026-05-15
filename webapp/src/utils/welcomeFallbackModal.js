/**
 * Vanilla-JS fallback для модалки «Приветствие новичков».
 *
 * Полноценная Vue-модалка приветствия — тяжёлая (200+ строк template, формат-панель,
 * фото-превью, кнопки, raid-блок). В TMA WKWebView её v-if иногда не патчится:
 * флаг становится true, но узел не появляется в DOM (см. лог `welcomeSettings:rAF`
 * `domHasNode: false`). На фоне этого экран Защиты «исчезает» — Vue ронит рендер.
 *
 * Этот fallback — минимально полезный: даёт включить/выключить приветствие,
 * не открывая большую Vue-модалку. Полная настройка — через web-кабинет.
 * Лог каждого шага — `guardFilterChain` со scope `WelcomeFallback`.
 */

import { guardFilterChain } from './guardDebugLog.js'

const ROOT_ID = 'guard-welcome-fallback-modal-root'

function errToObj(e) {
  if (!e) return null
  if (typeof e !== 'object') return { value: String(e) }
  return {
    name: e.name ?? null,
    message: e.message ?? null,
    stack: typeof e.stack === 'string' ? e.stack.slice(0, 400) : null,
  }
}

function removeExistingRoot() {
  try {
    const old = document.getElementById(ROOT_ID)
    if (old?.parentNode) {
      old.parentNode.removeChild(old)
      guardFilterChain('WelcomeFallback', 'removed_existing', { ts: Date.now() })
    }
  } catch (e) {
    guardFilterChain('WelcomeFallback', 'removed_existing:error', errToObj(e))
  }
}

/** @param {{ titleText: string, bodyText: string, enableText: string, disableText: string, cancelText: string, currentEnabled: boolean, onToggle: (enabled: boolean) => void, onClose?: () => void }} opts */
export function openWelcomeFallbackModal(opts) {
  guardFilterChain('WelcomeFallback', 'enter', {
    ts: Date.now(),
    hasDocument: typeof document !== 'undefined',
    hasBody: typeof document !== 'undefined' && !!document.body,
    currentEnabled: !!opts?.currentEnabled,
  })
  if (typeof document === 'undefined') return null
  const host = document.documentElement || document.body
  if (!host) {
    guardFilterChain('WelcomeFallback', 'abort:no_host', {})
    return null
  }
  removeExistingRoot()

  const root = document.createElement('div')
  root.id = ROOT_ID
  root.setAttribute('data-guard-protection-welcome-fallback', '')
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
  ].join(';')

  const panel = document.createElement('div')
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
  title.style.cssText = 'margin:0;font-size:14px;font-weight:600;color:#ffffff'
  title.textContent = String(opts?.titleText || '')
  const closeBtn = document.createElement('button')
  closeBtn.type = 'button'
  closeBtn.setAttribute('data-guard-welcome-fallback-close', '')
  closeBtn.style.cssText =
    'background:transparent;border:0;color:#94a3b8;font-size:14px;padding:4px 8px;cursor:pointer'
  closeBtn.textContent = '✕'
  head.appendChild(title)
  head.appendChild(closeBtn)

  const body = document.createElement('p')
  body.style.cssText = 'margin:0 0 12px;font-size:11px;color:#94a3b8;line-height:1.45'
  body.textContent = String(opts?.bodyText || '')

  const grid = document.createElement('div')
  grid.style.cssText = 'display:grid;grid-template-columns:1fr 1fr;gap:8px'
  const baseBtn =
    'min-height:44px;border-radius:12px;padding:10px 12px;font-size:13px;font-weight:600;cursor:pointer;border:1px solid rgba(255,255,255,0.14)'
  const idle = `${baseBtn};background:rgba(255,255,255,0.06);color:#cbd5e1`
  const enabledSel = `${baseBtn};background:linear-gradient(180deg,#8fd41a,#65a30d);color:#0b1220;border-color:rgba(132,204,22,0.55);box-shadow:0 8px 20px -10px rgba(132,204,22,0.55)`
  const disabledSel = `${baseBtn};background:linear-gradient(90deg,#f43f5e,#dc2626);color:#ffffff;border-color:rgba(244,63,94,0.55);box-shadow:0 8px 20px -10px rgba(239,68,68,0.75)`

  const enableBtn = document.createElement('button')
  enableBtn.type = 'button'
  enableBtn.setAttribute('data-guard-welcome-fallback-enable', '')
  enableBtn.style.cssText = opts?.currentEnabled ? enabledSel : idle
  enableBtn.textContent = String(opts?.enableText || 'Включить')

  const disableBtn = document.createElement('button')
  disableBtn.type = 'button'
  disableBtn.setAttribute('data-guard-welcome-fallback-disable', '')
  disableBtn.style.cssText = opts?.currentEnabled ? idle : disabledSel
  disableBtn.textContent = String(opts?.disableText || 'Выключить')

  grid.appendChild(enableBtn)
  grid.appendChild(disableBtn)

  panel.appendChild(head)
  panel.appendChild(body)
  panel.appendChild(grid)
  root.appendChild(panel)

  panel.addEventListener('click', (e) => e.stopPropagation())
  root.addEventListener('click', (e) => {
    if (e.target === root) {
      guardFilterChain('WelcomeFallback', 'close_backdrop', {})
      closeWelcomeFallbackModal()
      opts?.onClose?.()
    }
  })
  closeBtn.addEventListener('click', () => {
    guardFilterChain('WelcomeFallback', 'close_x', {})
    closeWelcomeFallbackModal()
    opts?.onClose?.()
  })
  enableBtn.addEventListener('click', () => {
    guardFilterChain('WelcomeFallback', 'choose', { enabled: true })
    try {
      opts?.onToggle?.(true)
    } catch (err) {
      guardFilterChain('WelcomeFallback', 'choose:error', errToObj(err))
    } finally {
      closeWelcomeFallbackModal()
    }
  })
  disableBtn.addEventListener('click', () => {
    guardFilterChain('WelcomeFallback', 'choose', { enabled: false })
    try {
      opts?.onToggle?.(false)
    } catch (err) {
      guardFilterChain('WelcomeFallback', 'choose:error', errToObj(err))
    } finally {
      closeWelcomeFallbackModal()
    }
  })

  try {
    host.appendChild(root)
  } catch (e) {
    guardFilterChain('WelcomeFallback', 'append:error', errToObj(e))
    try {
      document.body.appendChild(root)
    } catch (e2) {
      guardFilterChain('WelcomeFallback', 'append:body_error', errToObj(e2))
      return null
    }
  }
  guardFilterChain('WelcomeFallback', 'appended', {
    parentTag: root.parentNode?.tagName ?? null,
  })
  return root
}

export function closeWelcomeFallbackModal() {
  removeExistingRoot()
}

export function isWelcomeFallbackModalOpen() {
  try {
    return !!document.getElementById(ROOT_ID)
  } catch {
    return false
  }
}

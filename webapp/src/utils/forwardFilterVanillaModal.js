/**
 * Vanilla-модалка «Пересылки и цитаты» (TMA-safe).
 */

import { guardFilterChain } from './guardDebugLog.js'

const ROOT_ID = 'guard-forward-filter-vanilla-modal-root'

function btnStyle(selected, variant) {
  const base =
    'min-height:36px;border-radius:12px;padding:8px 10px;font-size:11px;font-weight:600;cursor:pointer;border:1px solid rgba(255,255,255,0.14);flex:1'
  const idle = `${base};background:rgba(255,255,255,0.06);color:#cbd5e1`
  if (!selected) return idle
  if (variant === 'forbid') {
    return `${base};background:linear-gradient(180deg,#f87171,#dc2626);color:#fff;border-color:rgba(248,113,113,0.5)`
  }
  return `${base};background:linear-gradient(180deg,#8fd41a,#65a30d);color:#0b1220;border-color:rgba(132,204,22,0.55)`
}

function forbidAllowRow(label, fieldKey, state, labels, premiumLocked, onPatch) {
  const row = document.createElement('div')
  row.style.cssText =
    'display:flex;flex-direction:column;gap:6px;padding:10px 12px;border-radius:12px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06)'
  const top = document.createElement('div')
  top.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:8px'
  const lbl = document.createElement('span')
  lbl.style.cssText = 'font-size:12px;color:#e2e8f0;line-height:1.35'
  lbl.textContent = String(label || '')
  top.appendChild(lbl)
  if (premiumLocked) {
    const lock = document.createElement('span')
    lock.style.cssText = 'font-size:10px;color:#fbbf24'
    lock.textContent = '🔒 Premium'
    top.appendChild(lock)
  }
  row.appendChild(top)

  const forbidden = !!state[fieldKey]
  const btns = document.createElement('div')
  btns.style.cssText = 'display:flex;gap:8px'
  for (const opt of [
    { v: true, text: labels.forbidden, variant: 'forbid' },
    { v: false, text: labels.allowed, variant: 'allow' },
  ]) {
    const b = document.createElement('button')
    b.type = 'button'
    b.disabled = !!premiumLocked
    b.style.cssText = btnStyle(forbidden === opt.v, opt.variant) + (premiumLocked ? ';opacity:0.45;cursor:not-allowed' : '')
    b.textContent = String(opt.text || '')
    b.addEventListener('click', (e) => {
      e.stopPropagation()
      if (premiumLocked) return
      onPatch({ [fieldKey]: opt.v })
    })
    btns.appendChild(b)
  }
  row.appendChild(btns)
  return row
}

export function openForwardFilterVanillaModal(opts) {
  if (typeof document === 'undefined' || !document.documentElement) return null
  closeForwardFilterVanillaModal()

  let allowBackdropClose = false
  setTimeout(() => {
    allowBackdropClose = true
  }, 650)

  const root = document.createElement('div')
  root.id = ROOT_ID
  root.style.cssText =
    'position:fixed;inset:0;z-index:2147483000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.82);padding:16px;box-sizing:border-box'

  const panel = document.createElement('div')
  panel.style.cssText =
    'width:100%;max-width:32rem;max-height:min(82dvh,calc(100dvh - 24px));overflow:hidden;display:flex;flex-direction:column;background:linear-gradient(180deg,#16161f,#0e0e14);border:1px solid rgba(255,255,255,0.12);border-radius:18px;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,sans-serif'

  const head = document.createElement('div')
  head.style.cssText =
    'flex-shrink:0;display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid rgba(255,255,255,0.08)'
  const title = document.createElement('h3')
  title.style.cssText = 'margin:0;font-size:13px;font-weight:700;text-transform:uppercase;color:#fff'
  title.textContent = String(opts?.labels?.title || '')
  const headBtns = document.createElement('div')
  headBtns.style.cssText = 'display:flex;align-items:center;gap:6px'
  if (typeof opts?.onInfo === 'function') {
    const infoBtn = document.createElement('button')
    infoBtn.type = 'button'
    infoBtn.textContent = 'i'
    infoBtn.setAttribute('aria-label', String(opts?.labels?.infoAria || 'Info'))
    infoBtn.style.cssText =
      'background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.1);border-radius:999px;color:#cbd5e1;font-size:10px;font-weight:700;width:26px;height:26px;padding:0;cursor:pointer'
    infoBtn.addEventListener('click', (e) => {
      e.stopPropagation()
      try {
        opts.onInfo()
      } catch {
        //
      }
    })
    headBtns.appendChild(infoBtn)
  }
  const closeBtn = document.createElement('button')
  closeBtn.type = 'button'
  closeBtn.textContent = '✕'
  closeBtn.style.cssText =
    'background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.1);border-radius:12px;color:#e2e8f0;font-size:12px;padding:6px 10px;cursor:pointer'
  headBtns.appendChild(closeBtn)
  head.appendChild(title)
  head.appendChild(headBtns)

  const body = document.createElement('div')
  body.style.cssText = 'flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px'

  function closeModal() {
    closeForwardFilterVanillaModal()
    try {
      opts?.onClose?.()
    } catch {
      //
    }
  }

  async function applyPatch(patch) {
    try {
      await opts?.onPatch?.(patch)
    } catch {
      //
    }
    renderBody()
  }

  function renderBody() {
    while (body.firstChild) body.removeChild(body.firstChild)
    const s = opts?.getState?.() || {}
    const labels = opts?.labels || {}
    const rows = opts?.rows || []

    if (labels.intro) {
      const intro = document.createElement('p')
      intro.style.cssText = 'margin:0 0 4px;font-size:11px;line-height:1.45;color:#94a3b8'
      intro.textContent = String(labels.intro)
      body.appendChild(intro)
    }
    if (labels.note) {
      const note = document.createElement('p')
      note.style.cssText =
        'margin:0 0 8px;font-size:10px;line-height:1.4;color:#a3e635;background:rgba(163,230,53,0.08);border-radius:10px;padding:8px 10px'
      note.textContent = String(labels.note)
      body.appendChild(note)
    }

    for (const row of rows) {
      const premiumLocked = !!row.premium && !opts?.canPremium
      body.appendChild(
        forbidAllowRow(row.label, row.field, s, labels, premiumLocked, applyPatch),
      )
    }
  }

  panel.addEventListener('click', (e) => e.stopPropagation())
  closeBtn.addEventListener('click', () => closeModal())
  root.addEventListener('click', (e) => {
    if (e.target === root && allowBackdropClose) closeModal()
  })

  panel.appendChild(head)
  panel.appendChild(body)
  root.appendChild(panel)
  renderBody()
  ;(document.documentElement || document.body).appendChild(root)
  guardFilterChain('ForwardFilterVanilla', 'appended', { ts: Date.now() })
  return root
}

export function closeForwardFilterVanillaModal() {
  const old = document.getElementById(ROOT_ID)
  if (old?.parentNode) {
    old.parentNode.removeChild(old)
    return true
  }
  return false
}

export function isForwardFilterVanillaModalOpen() {
  return !!document.getElementById(ROOT_ID)
}

export const FORWARD_FILTER_ROWS = [
  { field: 'filter_forward_block_channels', key: 'channels', premium: false },
  { field: 'filter_forward_block_chats', key: 'chats', premium: false },
  { field: 'filter_forward_block_bots', key: 'bots', premium: true },
  { field: 'filter_forward_block_users', key: 'users', premium: true },
  { field: 'filter_forward_block_with_links', key: 'with_links', premium: true },
  { field: 'filter_forward_block_stories', key: 'stories', premium: true },
  { field: 'filter_forward_block_with_button', key: 'with_button', premium: true },
]

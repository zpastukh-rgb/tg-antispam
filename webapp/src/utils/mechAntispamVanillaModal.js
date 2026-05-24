/**
 * Vanilla-модалка «Механический антиспам» (TMA-safe).
 */

import { guardFilterChain } from './guardDebugLog.js'

const ROOT_ID = 'guard-mech-antispam-vanilla-modal-root'

function btnStyle(on) {
  const base =
    'min-height:36px;border-radius:12px;padding:8px 10px;font-size:11px;font-weight:600;cursor:pointer;border:1px solid rgba(255,255,255,0.14);flex:1'
  const idle = `${base};background:rgba(255,255,255,0.06);color:#cbd5e1`
  const active = `${base};background:linear-gradient(180deg,#8fd41a,#65a30d);color:#0b1220;border-color:rgba(132,204,22,0.55)`
  return on ? active : idle
}

function actionBtnStyle(active) {
  const base =
    'min-width:36px;min-height:32px;border-radius:10px;padding:4px 8px;font-size:14px;cursor:pointer;border:1px solid rgba(255,255,255,0.12)'
  const idle = `${base};background:rgba(255,255,255,0.05);opacity:0.75`
  const on = `${base};background:rgba(132,204,22,0.22);border-color:rgba(132,204,22,0.5);opacity:1`
  return active ? on : idle
}

function toggleRow(label, fieldKey, state, labels, premiumLocked, onPatch) {
  const row = document.createElement('div')
  row.style.cssText =
    'display:flex;flex-direction:column;gap:6px;padding:10px 12px;border-radius:12px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06)'
  const top = document.createElement('div')
  top.style.cssText = 'display:flex;align-items:flex-start;justify-content:space-between;gap:8px'
  const lbl = document.createElement('span')
  lbl.style.cssText = 'font-size:12px;color:#e2e8f0;line-height:1.35'
  lbl.textContent = String(label || '')
  top.appendChild(lbl)
  if (premiumLocked) {
    const lock = document.createElement('span')
    lock.style.cssText = 'font-size:10px;color:#fbbf24;flex-shrink:0'
    lock.textContent = '🔒 Premium'
    top.appendChild(lock)
  }
  row.appendChild(top)

  const on = !!state[fieldKey]
  const btns = document.createElement('div')
  btns.style.cssText = 'display:flex;gap:8px'
  for (const opt of [
    { v: true, text: labels.on },
    { v: false, text: labels.off },
  ]) {
    const b = document.createElement('button')
    b.type = 'button'
    b.disabled = !!premiumLocked
    b.style.cssText = btnStyle(on === opt.v) + (premiumLocked ? ';opacity:0.45;cursor:not-allowed' : '')
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

function actionPickerRow(actionKey, label, state, labels, premiumLocked, onPatch) {
  const row = document.createElement('div')
  row.style.cssText =
    'display:flex;flex-direction:column;gap:6px;padding:8px 12px 10px;border-radius:12px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.04)'
  const top = document.createElement('div')
  top.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:8px'
  const lbl = document.createElement('span')
  lbl.style.cssText = 'font-size:10px;color:#94a3b8'
  lbl.textContent = String(label || '')
  top.appendChild(lbl)
  row.appendChild(top)

  const fa = state.filter_actions || {}
  const cur = fa[actionKey] || ''
  const btns = document.createElement('div')
  btns.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px'
  for (const opt of labels.actionOptions || []) {
    const cell = document.createElement('div')
    cell.style.cssText = 'display:flex;flex-direction:column;align-items:center;gap:3px;min-width:52px'
    const b = document.createElement('button')
    b.type = 'button'
    b.disabled = !!premiumLocked
    const caption = String(opt.title || opt.label || '')
    b.title = caption
    b.setAttribute('aria-label', caption)
    b.style.cssText =
      actionBtnStyle(cur === opt.v) + (premiumLocked ? ';opacity:0.45;cursor:not-allowed' : '')
    b.textContent = String(opt.emoji || opt.label || '')
    b.addEventListener('click', (e) => {
      e.stopPropagation()
      if (premiumLocked) return
      const next = { ...(state.filter_actions || {}) }
      if (!opt.v) {
        delete next[actionKey]
      } else {
        next[actionKey] = opt.v
      }
      onPatch({ filter_actions: next })
    })
    const cap = document.createElement('span')
    cap.style.cssText = 'font-size:9px;color:#64748b;text-align:center;line-height:1.2;max-width:64px'
    cap.textContent = caption
    cell.appendChild(b)
    cell.appendChild(cap)
    btns.appendChild(cell)
  }
  row.appendChild(btns)
  return row
}

export function openMechAntispamVanillaModal(opts) {
  if (typeof document === 'undefined' || !document.documentElement) return null
  closeMechAntispamVanillaModal()

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
    closeMechAntispamVanillaModal()
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
    const canPremium = !!opts?.canPremium
    const globalOff = !!opts?.globalActionOff

    if (labels.intro) {
      const intro = document.createElement('p')
      intro.style.cssText = 'margin:0;font-size:11px;line-height:1.45;color:#94a3b8'
      intro.textContent = String(labels.intro)
      body.appendChild(intro)
    }

    if (globalOff && labels.globalOffHint) {
      const hint = document.createElement('p')
      hint.style.cssText = 'margin:0;font-size:10px;line-height:1.4;color:#fbbf24'
      hint.textContent = String(labels.globalOffHint)
      body.appendChild(hint)
    }

    if (labels.actionsTitle) {
      const h = document.createElement('p')
      h.style.cssText = 'margin:4px 0 0;font-size:10px;font-weight:700;text-transform:uppercase;color:#64748b;letter-spacing:0.04em'
      h.textContent = String(labels.actionsTitle)
      body.appendChild(h)
    }

    for (const row of opts?.rows || []) {
      const locked = !!row.premium && !canPremium
      body.appendChild(
        toggleRow(
          row.label,
          row.field,
          s,
          { on: labels.on, off: labels.off },
          locked,
          (patch) => {
            if (row.premium && !canPremium) {
              opts?.onPremiumLock?.()
              return
            }
            applyPatch(patch)
          },
        ),
      )
      if (row.hint) {
        const hint = document.createElement('p')
        hint.style.cssText = 'margin:-4px 0 0;font-size:10px;color:#64748b;line-height:1.4'
        hint.textContent = String(row.hint)
        body.appendChild(hint)
      }
      if (row.actionKey && s[row.field]) {
        body.appendChild(
          actionPickerRow(
            row.actionKey,
            labels.actionForFilter || '',
            s,
            labels,
            locked,
            (patch) => applyPatch(patch),
          ),
        )
      }
    }

    if (labels.note) {
      const note = document.createElement('p')
      note.style.cssText = 'margin:4px 0 0;font-size:10px;color:#64748b;line-height:1.4'
      note.textContent = String(labels.note)
      body.appendChild(note)
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
  guardFilterChain('MechAntispamVanilla', 'appended', { ts: Date.now() })
  return root
}

export function closeMechAntispamVanillaModal() {
  const old = document.getElementById(ROOT_ID)
  if (old?.parentNode) {
    old.parentNode.removeChild(old)
    return true
  }
  return false
}

export function isMechAntispamVanillaModalOpen() {
  return !!document.getElementById(ROOT_ID)
}

export const MECH_FILTER_ACTION_KEYS = {
  apk: 'mech_apk',
  guest_bots: 'mech_guest_bot',
  symbol_subst: 'mech_symbol_subst',
  text_spam: 'mech_text_spam',
  strict_edit: 'mech_strict_edit',
}

export const MECH_ANTISPAM_ROWS = [
  { field: 'mech_filter_block_apk', key: 'apk', actionKey: 'mech_apk' },
  { field: 'mech_filter_guest_bots', key: 'guest_bots', actionKey: 'mech_guest_bot' },
  { field: 'mech_filter_symbol_subst', key: 'symbol_subst', premium: true, actionKey: 'mech_symbol_subst' },
  { field: 'mech_filter_text_spam', key: 'text_spam', premium: true, actionKey: 'mech_text_spam' },
  { field: 'mech_filter_strict_edit', key: 'strict_edit', premium: true, actionKey: 'mech_strict_edit' },
]

export const MECH_FILTER_ACTION_OPTIONS = [
  { v: '', emoji: '↩️', title: 'inherit' },
  { v: 'delete', emoji: '✂️', title: 'delete' },
  { v: 'mute', emoji: '📢', title: 'mute' },
  { v: 'ban', emoji: '🚫', title: 'ban' },
  { v: 'observe', emoji: '👁', title: 'observe' },
]

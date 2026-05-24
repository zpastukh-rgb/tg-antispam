/**
 * Vanilla-модалка «Система АнтиФлуд» — Guard UI: iOS-тоггл вкл/выкл, чипы режима и наказания.
 */

import { guardFilterChain } from './guardDebugLog.js'
import { buildIosToggle } from './mentionsGranularVanillaModal.js'

const ROOT_ID = 'guard-antiflood-vanilla-modal-root'

const INPUT_STYLE =
  'width:4.25rem;min-height:36px;border-radius:10px;border:1px solid rgba(255,255,255,0.14);background:rgba(0,0,0,0.35);color:#f8fafc;font-size:14px;font-weight:600;text-align:center;padding:6px 8px;box-sizing:border-box;-moz-appearance:textfield'

function sectionTitle(text) {
  const p = document.createElement('p')
  p.style.cssText =
    'margin:0 0 8px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:#a3e635'
  p.textContent = text
  return p
}

function chipStyle(selected) {
  const base =
    'min-height:36px;border-radius:12px;padding:8px 12px;font-size:12px;font-weight:600;cursor:pointer;border:1px solid rgba(255,255,255,0.14);flex:1'
  if (selected) {
    return `${base};background:linear-gradient(180deg,#8fd41a,#65a30d);color:#0b1220;border-color:rgba(132,204,22,0.55)`
  }
  return `${base};background:rgba(255,255,255,0.06);color:#cbd5e1`
}

function switchRow(label, hint, enabled, onChange) {
  const row = document.createElement('div')
  row.style.cssText =
    'display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;border-radius:12px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06)'
  const left = document.createElement('div')
  left.style.cssText = 'flex:1;min-width:0;display:flex;flex-direction:column;gap:2px'
  const lbl = document.createElement('span')
  lbl.style.cssText = 'font-size:12px;color:#e2e8f0;line-height:1.35'
  lbl.textContent = String(label || '')
  left.appendChild(lbl)
  if (hint) {
    const h = document.createElement('span')
    h.style.cssText = 'font-size:10px;color:#64748b;line-height:1.35'
    h.textContent = String(hint)
    left.appendChild(h)
  }
  const { wrap } = buildIosToggle(enabled, onChange)
  row.appendChild(left)
  row.appendChild(wrap)
  return row
}

function chipRow(items, onPick) {
  const row = document.createElement('div')
  row.style.cssText = 'display:flex;gap:8px;width:100%'
  for (const it of items) {
    const b = document.createElement('button')
    b.type = 'button'
    b.style.cssText = chipStyle(!!it.selected)
    b.textContent = String(it.label ?? '')
    b.addEventListener('click', (e) => {
      e.stopPropagation()
      onPick(it)
    })
    row.appendChild(b)
  }
  return row
}

function clampInt(raw, fallback, min, max) {
  const n = parseInt(String(raw ?? ''), 10)
  if (Number.isNaN(n)) return fallback
  return Math.max(min, Math.min(max, n))
}

function numberFieldRow(label, value, { min, max, suffix }, onCommit) {
  const row = document.createElement('div')
  row.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:10px'
  const lbl = document.createElement('span')
  lbl.style.cssText = 'flex:1;font-size:12px;color:#e2e8f0;line-height:1.35'
  lbl.textContent = String(label || '')
  const right = document.createElement('div')
  right.style.cssText = 'display:flex;align-items:center;gap:6px;flex-shrink:0'
  const input = document.createElement('input')
  input.type = 'number'
  input.inputMode = 'numeric'
  input.min = String(min)
  input.max = String(max)
  input.value = String(value)
  input.style.cssText = INPUT_STYLE
  const commit = () => {
    const v = clampInt(input.value, value, min, max)
    input.value = String(v)
    if (v !== value) onCommit(v)
  }
  input.addEventListener('blur', commit)
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      commit()
      input.blur()
    }
  })
  right.appendChild(input)
  if (suffix) {
    const suf = document.createElement('span')
    suf.style.cssText = 'font-size:11px;color:#94a3b8'
    suf.textContent = String(suffix)
    right.appendChild(suf)
  }
  row.appendChild(lbl)
  row.appendChild(right)
  return row
}

function thresholdSettingsBox(state, labels, onPatch) {
  const box = document.createElement('div')
  box.style.cssText =
    'display:flex;flex-direction:column;gap:8px;padding:10px 12px;border-radius:12px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.04)'
  box.appendChild(
    numberFieldRow(
      labels.floodThreshold,
      state.mech_filter_flood_threshold ?? 3,
      { min: 2, max: 20 },
      (v) => onPatch({ mech_filter_flood_threshold: v }),
    ),
  )
  box.appendChild(
    numberFieldRow(
      labels.floodWindow,
      state.mech_filter_flood_window_minutes ?? 5,
      { min: 1, max: 60, suffix: labels.unitMin },
      (v) => onPatch({ mech_filter_flood_window_minutes: v }),
    ),
  )
  return box
}

export function openAntifloodVanillaModal(opts) {
  if (typeof document === 'undefined' || !document.documentElement) return null
  closeAntifloodVanillaModal()

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
  const closeBtn = document.createElement('button')
  closeBtn.type = 'button'
  closeBtn.textContent = '✕'
  closeBtn.style.cssText =
    'background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.1);border-radius:12px;color:#e2e8f0;font-size:12px;padding:6px 10px;cursor:pointer'
  head.appendChild(title)
  head.appendChild(closeBtn)

  const body = document.createElement('div')
  body.style.cssText = 'flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px'

  function closeModal() {
    closeAntifloodVanillaModal()
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
    const enabled = !!s.mech_filter_flood_enabled
    const mode = String(s.mech_filter_flood_mode || 'soft')
    const action = String(s.mech_filter_flood_action || 'mute')

    if (labels.intro) {
      const intro = document.createElement('p')
      intro.style.cssText = 'margin:0;font-size:11px;line-height:1.45;color:#94a3b8'
      intro.textContent = String(labels.intro)
      body.appendChild(intro)
    }

    body.appendChild(sectionTitle(String(labels.mainTitle || labels.statusTitle || '')))
    body.appendChild(
      switchRow(
        labels.enableLabel || labels.on || '',
        labels.enableHint || labels.hint || '',
        enabled,
        (v) => applyPatch({ mech_filter_flood_enabled: v }),
      ),
    )

    const settingsBox = document.createElement('div')
    settingsBox.style.cssText = enabled ? 'display:flex;flex-direction:column;gap:12px' : 'display:none'

    settingsBox.appendChild(sectionTitle(String(labels.modeTitle || '')))
    settingsBox.appendChild(
      chipRow(
        [
          { value: 'soft', label: labels.modeSoft, selected: mode === 'soft' },
          { value: 'strict', label: labels.modeStrict, selected: mode === 'strict' },
        ],
        (it) => applyPatch({ mech_filter_flood_mode: it.value }),
      ),
    )
    if (labels.modeSoftHint || labels.modeStrictHint) {
      const modeHint = document.createElement('p')
      modeHint.style.cssText = 'margin:-4px 0 0;font-size:10px;color:#64748b;line-height:1.4'
      modeHint.textContent =
        mode === 'strict' ? String(labels.modeStrictHint || '') : String(labels.modeSoftHint || '')
      settingsBox.appendChild(modeHint)
    }

    settingsBox.appendChild(sectionTitle(String(labels.actionTitle || '')))
    settingsBox.appendChild(
      chipRow(
        [
          { value: 'mute', label: labels.actionMute, selected: action === 'mute' },
          { value: 'ban', label: labels.actionBan, selected: action === 'ban' },
        ],
        (it) => applyPatch({ mech_filter_flood_action: it.value }),
      ),
    )

    if (labels.floodThreshold || labels.floodWindow) {
      settingsBox.appendChild(sectionTitle(String(labels.thresholdTitle || '')))
      settingsBox.appendChild(thresholdSettingsBox(s, labels, (patch) => applyPatch(patch)))
    }

    body.appendChild(settingsBox)

    if (labels.note) {
      const note = document.createElement('p')
      note.style.cssText = 'margin:0;font-size:10px;color:#64748b;line-height:1.4'
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
  guardFilterChain('AntifloodVanilla', 'appended', { ts: Date.now() })
  return root
}

export function closeAntifloodVanillaModal() {
  const old = document.getElementById(ROOT_ID)
  if (old?.parentNode) {
    old.parentNode.removeChild(old)
    return true
  }
  return false
}

export function isAntifloodVanillaModalOpen() {
  return !!document.getElementById(ROOT_ID)
}

/**
 * Vanilla-JS модалка «Антинакрутка — настройки» для экрана Защита.
 * В TMA Vue/Teleport часто не монтирует узел — остаётся только overflow:hidden на body.
 */

import { guardFilterChain } from './guardDebugLog.js'

const ROOT_ID = 'guard-antinakrutka-vanilla-modal-root'

const INPUT_STYLE =
  'width:4.25rem;min-height:36px;border-radius:10px;border:1px solid rgba(255,255,255,0.14);background:rgba(0,0,0,0.35);color:#f8fafc;font-size:14px;font-weight:600;text-align:center;padding:6px 8px;box-sizing:border-box;-moz-appearance:textfield'

function errToObj(e) {
  if (!e) return null
  if (typeof e !== 'object') return { value: String(e) }
  return {
    name: e.name ?? null,
    message: e.message ?? null,
    stack: typeof e.stack === 'string' ? e.stack.slice(0, 500) : null,
  }
}

function removeExistingRoot() {
  try {
    const old = document.getElementById(ROOT_ID)
    if (old?.parentNode) {
      old.parentNode.removeChild(old)
      return true
    }
  } catch (e) {
    guardFilterChain('AntinakrutkaVanilla', 'removed_existing:error', errToObj(e))
  }
  return false
}

function btnStyle(selected, variant) {
  const base =
    'min-height:40px;border-radius:12px;padding:8px 12px;font-size:12px;font-weight:600;cursor:pointer;border:1px solid rgba(255,255,255,0.14);transition:transform 80ms ease'
  const idle = `${base};background:rgba(255,255,255,0.06);color:#cbd5e1`
  if (!selected) return idle
  if (variant === 'hard') {
    return `${base};background:linear-gradient(90deg,#f43f5e,#dc2626);color:#fff;border-color:rgba(244,63,94,0.55)`
  }
  if (variant === 'standard') {
    return `${base};background:linear-gradient(90deg,#fbbf24,#f97316);color:#0b1220;border-color:rgba(251,191,36,0.55)`
  }
  if (variant === 'soft') {
    return `${base};background:linear-gradient(180deg,#8fd41a,#65a30d);color:#0b1220;border-color:rgba(132,204,22,0.55)`
  }
  return `${base};background:linear-gradient(180deg,#8fd41a,#65a30d);color:#0b1220;border-color:rgba(132,204,22,0.55)`
}

function sectionTitle(text) {
  const p = document.createElement('p')
  p.style.cssText = 'margin:0 0 8px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:#a3e635'
  p.textContent = text
  return p
}

function clampInt(raw, fallback, min, max) {
  const n = parseInt(String(raw ?? ''), 10)
  if (Number.isNaN(n)) return fallback
  return Math.max(min, Math.min(max, n))
}

/** Компактная строка: подпись + поле числа (+ опциональный суффикс). Сохранение на blur / Enter. */
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
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      input.blur()
    }
  })
  input.addEventListener('blur', () => {
    const next = clampInt(input.value, value, min, max)
    input.value = String(next)
    if (next !== value) onCommit(next)
  })
  right.appendChild(input)
  if (suffix) {
    const suf = document.createElement('span')
    suf.style.cssText = 'font-size:11px;color:#94a3b8;min-width:1.5rem'
    suf.textContent = String(suffix)
    right.appendChild(suf)
  }
  row.appendChild(lbl)
  row.appendChild(right)
  return row
}

function toggleRow(label, enabled, onToggle, labels) {
  const row = document.createElement('div')
  row.style.cssText =
    'display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;border-radius:12px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08)'
  const lbl = document.createElement('span')
  lbl.style.cssText = 'font-size:12px;color:#e2e8f0;line-height:1.35'
  lbl.textContent = String(label || '')
  const btn = document.createElement('button')
  btn.type = 'button'
  btn.style.cssText = btnStyle(!!enabled)
  btn.textContent = enabled ? String(labels?.on || 'ON') : String(labels?.off || 'OFF')
  btn.addEventListener('click', (e) => {
    e.stopPropagation()
    onToggle(!enabled)
  })
  row.appendChild(lbl)
  row.appendChild(btn)
  return row
}

function chipRow(items, onPick) {
  const row = document.createElement('div')
  row.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px'
  for (const it of items) {
    const b = document.createElement('button')
    b.type = 'button'
    b.style.cssText = btnStyle(!!it.selected, it.variant)
    b.textContent = String(it.label ?? '')
    b.addEventListener('click', (e) => {
      e.stopPropagation()
      onPick(it)
    })
    row.appendChild(b)
  }
  return row
}

/**
 * @param {{
 *   labels: Record<string, string>,
 *   getState: () => object,
 *   presets: Array<object>,
 *   actionOptions: Array<{ value, label }>,
 *   getActivePresetKey?: () => string | null,
 *   onPatch: (patch: object) => void | Promise<void>,
 *   onClose?: () => void,
 * }} opts
 */
export function openAntinakrutkaVanillaModal(opts) {
  guardFilterChain('AntinakrutkaVanilla', 'enter', { ts: Date.now() })
  if (typeof document === 'undefined' || !document.documentElement) return null

  removeExistingRoot()

  let allowBackdropClose = false
  setTimeout(() => {
    allowBackdropClose = true
  }, 650)

  const root = document.createElement('div')
  root.id = ROOT_ID
  root.setAttribute('data-guard-antinakrutka-settings-modal', '')
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
    'background:rgba(0,0,0,0.82)',
    'padding:16px',
    'box-sizing:border-box',
    'pointer-events:auto',
  ].join(';')

  const panel = document.createElement('div')
  panel.style.cssText = [
    'width:100%',
    'max-width:32rem',
    'max-height:min(82dvh,calc(100dvh - 24px))',
    'overflow:hidden',
    'display:flex',
    'flex-direction:column',
    'background:linear-gradient(180deg,#16161f,#0e0e14 55%,#08080c)',
    'border:1px solid rgba(255,255,255,0.12)',
    'border-radius:18px',
    'box-shadow:0 28px 90px -28px rgba(0,0,0,0.96)',
    'color:#e2e8f0',
    'box-sizing:border-box',
    'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif',
  ].join(';')

  const head = document.createElement('div')
  head.style.cssText =
    'flex-shrink:0;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:14px 16px;border-bottom:1px solid rgba(255,255,255,0.08)'
  const title = document.createElement('h3')
  title.style.cssText = 'margin:0;font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:#fff'
  title.textContent = String(opts?.labels?.title || '')
  const closeBtn = document.createElement('button')
  closeBtn.type = 'button'
  closeBtn.style.cssText =
    'background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.1);border-radius:12px;color:#e2e8f0;font-size:12px;padding:6px 10px;cursor:pointer'
  closeBtn.textContent = '✕'
  head.appendChild(title)
  head.appendChild(closeBtn)

  const body = document.createElement('div')
  body.style.cssText = 'flex:1;overflow-y:auto;overscroll-behavior:contain;padding:16px;display:flex;flex-direction:column;gap:12px'

  function closeModal() {
    closeAntinakrutkaVanillaModal()
    try {
      opts?.onClose?.()
    } catch {
      //
    }
  }

  async function applyPatch(patch) {
    try {
      await opts?.onPatch?.(patch)
    } catch (e) {
      guardFilterChain('AntinakrutkaVanilla', 'onPatch:error', errToObj(e))
    }
    renderBody()
  }

  function renderBody() {
    while (body.firstChild) body.removeChild(body.firstChild)
    const s = opts?.getState?.() || {}
    const labels = opts?.labels || {}
    const unitMin = String(labels.unitMin || 'мин')
    const enabled = !!s.antinakrutka_enabled
    const threshold = Number(s.antinakrutka_joins_threshold || 10)
    const windowMin = Number(s.antinakrutka_window_minutes || 5)
    const action = String(s.antinakrutka_action || 'alert')
    const restrict = Number(s.antinakrutka_restrict_minutes || 30)
    const lockdown = Number(s.antinakrutka_lockdown_minutes || 0)
    const pauseWelcomes = !!s.antinakrutka_pause_welcomes
    const forceCaptcha = !!s.antinakrutka_force_captcha
    const cooldown = Number(s.antinakrutka_cooldown_minutes ?? 5)
    const autoSilence = Number(s.antinakrutka_auto_silence_minutes || 0)
    const activeKey =
      typeof opts?.getActivePresetKey === 'function' ? opts.getActivePresetKey() : null

    const quickBox = document.createElement('div')
    quickBox.style.cssText = 'padding:12px;border-radius:12px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06)'
    quickBox.appendChild(sectionTitle(String(labels.quick || '')))
    const grid = document.createElement('div')
    grid.style.cssText = 'display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px'
    for (const p of opts?.presets || []) {
      const b = document.createElement('button')
      b.type = 'button'
      const selected = activeKey === p.key
      b.style.cssText = `${btnStyle(selected, p.key)};display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;min-height:52px;padding:6px 4px`
      const titleEl = document.createElement('span')
      titleEl.textContent = String(p.label || '')
      b.appendChild(titleEl)
      const subline = String(p.subline || '')
      if (subline) {
        const sub = document.createElement('span')
        sub.style.cssText = 'font-size:10px;font-weight:500;line-height:1.2;opacity:0.88'
        sub.textContent = subline
        b.appendChild(sub)
      }
      b.addEventListener('click', (e) => {
        e.stopPropagation()
        applyPatch({
          antinakrutka_enabled: true,
          antinakrutka_joins_threshold: p.threshold,
          antinakrutka_window_minutes: p.window,
          antinakrutka_action: p.action,
          antinakrutka_restrict_minutes: p.restrict,
          antinakrutka_lockdown_minutes: p.lockdown ?? 0,
          antinakrutka_pause_welcomes: !!p.pauseWelcomes,
          antinakrutka_force_captcha: !!p.forceCaptcha,
          antinakrutka_cooldown_minutes: p.cooldown ?? 5,
          antinakrutka_auto_silence_minutes: p.autoSilence ?? 0,
        })
      })
      grid.appendChild(b)
    }
    quickBox.appendChild(grid)
    body.appendChild(quickBox)

    const enableRow = document.createElement('div')
    enableRow.style.cssText =
      'display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;border-radius:12px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08)'
    const enableLbl = document.createElement('span')
    enableLbl.style.cssText = 'font-size:12px;color:#e2e8f0'
    enableLbl.textContent = String(labels.enable || '')
    const enableBtn = document.createElement('button')
    enableBtn.type = 'button'
    enableBtn.style.cssText = btnStyle(enabled)
    enableBtn.textContent = enabled ? String(labels.on || 'ON') : String(labels.off || 'OFF')
    enableBtn.addEventListener('click', (e) => {
      e.stopPropagation()
      applyPatch({ antinakrutka_enabled: !enabled })
    })
    enableRow.appendChild(enableLbl)
    enableRow.appendChild(enableBtn)
    body.appendChild(enableRow)

    if (!enabled) return

    const detectBox = document.createElement('div')
    detectBox.style.cssText =
      'padding:12px;border-radius:12px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);display:flex;flex-direction:column;gap:10px'
    detectBox.appendChild(sectionTitle(String(labels.detectTitle || labels.threshold || '')))
    detectBox.appendChild(
      numberFieldRow(String(labels.threshold || ''), threshold, { min: 2, max: 100, suffix: '' }, (v) =>
        applyPatch({ antinakrutka_joins_threshold: v }),
      ),
    )
    detectBox.appendChild(
      numberFieldRow(String(labels.window || ''), windowMin, { min: 1, max: 60, suffix: unitMin }, (v) =>
        applyPatch({ antinakrutka_window_minutes: v }),
      ),
    )
    body.appendChild(detectBox)

    const actionBox = document.createElement('div')
    actionBox.style.cssText = 'padding:12px;border-radius:12px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06)'
    actionBox.appendChild(sectionTitle(String(labels.action || '')))
    actionBox.appendChild(
      chipRow(
        (opts?.actionOptions || []).map((o) => ({
          label: String(o.label || ''),
          selected: action === o.value,
          value: o.value,
        })),
        (it) => applyPatch({ antinakrutka_action: it.value }),
      ),
    )
    body.appendChild(actionBox)

    if (action === 'alert_restrict') {
      const muteBox = document.createElement('div')
      muteBox.style.cssText =
        'padding:12px;border-radius:12px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06)'
      muteBox.appendChild(sectionTitle(String(labels.mute || '')))
      muteBox.appendChild(
        numberFieldRow(String(labels.muteField || ''), restrict, { min: 1, max: 1440, suffix: unitMin }, (v) =>
          applyPatch({ antinakrutka_restrict_minutes: v }),
        ),
      )
      body.appendChild(muteBox)
    }

    const defenseBox = document.createElement('div')
    defenseBox.style.cssText =
      'padding:12px;border-radius:12px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);display:flex;flex-direction:column;gap:10px'
    defenseBox.appendChild(sectionTitle(String(labels.defenseTitle || '')))
    defenseBox.appendChild(
      numberFieldRow(String(labels.lockdown || ''), lockdown, { min: 0, max: 120, suffix: unitMin }, (v) =>
        applyPatch({ antinakrutka_lockdown_minutes: v }),
      ),
    )
    defenseBox.appendChild(
      numberFieldRow(String(labels.cooldown || ''), cooldown, { min: 0, max: 60, suffix: unitMin }, (v) =>
        applyPatch({ antinakrutka_cooldown_minutes: v }),
      ),
    )
    defenseBox.appendChild(
      toggleRow(
        String(labels.pauseWelcomes || ''),
        pauseWelcomes,
        (v) => applyPatch({ antinakrutka_pause_welcomes: v }),
        labels,
      ),
    )
    defenseBox.appendChild(
      toggleRow(
        String(labels.forceCaptcha || ''),
        forceCaptcha,
        (v) => applyPatch({ antinakrutka_force_captcha: v }),
        labels,
      ),
    )
    defenseBox.appendChild(
      numberFieldRow(String(labels.autoSilence || ''), autoSilence, { min: 0, max: 120, suffix: unitMin }, (v) =>
        applyPatch({ antinakrutka_auto_silence_minutes: v }),
      ),
    )
    body.appendChild(defenseBox)
  }

  panel.addEventListener('click', (e) => e.stopPropagation())
  closeBtn.addEventListener('click', () => {
    guardFilterChain('AntinakrutkaVanilla', 'close_x', { ts: Date.now() })
    closeModal()
  })
  root.addEventListener('click', (e) => {
    if (e.target !== root || !allowBackdropClose) return
    guardFilterChain('AntinakrutkaVanilla', 'close_backdrop', { ts: Date.now() })
    closeModal()
  })

  panel.appendChild(head)
  panel.appendChild(body)
  root.appendChild(panel)
  renderBody()

  const host = document.documentElement || document.body
  try {
    host.appendChild(root)
  } catch (e) {
    guardFilterChain('AntinakrutkaVanilla', 'append:error', errToObj(e))
    return null
  }

  guardFilterChain('AntinakrutkaVanilla', 'appended', {
    ts: Date.now(),
    inDom: !!document.getElementById(ROOT_ID),
  })
  return root
}

export function closeAntinakrutkaVanillaModal() {
  return removeExistingRoot()
}

export function isAntinakrutkaVanillaModalOpen() {
  try {
    return !!document.getElementById(ROOT_ID)
  } catch {
    return false
  }
}

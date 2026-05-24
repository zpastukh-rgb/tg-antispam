/**
 * Vanilla-модалка «Фильтрация входящих» (TMA-safe).
 */

import { guardFilterChain } from './guardDebugLog.js'

const ROOT_ID = 'guard-join-filter-vanilla-modal-root'

const PREMIUM_PATCH_KEYS = new Set([
  'join_filter_cas',
  'join_filter_network_mass_join',
  'join_filter_network_join_threshold',
  'join_filter_network_join_window_minutes',
  'join_filter_name_stopwords_enabled',
  'join_filter_name_stopwords',
  'join_filter_close_entry',
  'join_filter_close_action',
])

const INPUT_STYLE =
  'width:4.25rem;min-height:36px;border-radius:10px;border:1px solid rgba(255,255,255,0.14);background:rgba(0,0,0,0.35);color:#f8fafc;font-size:14px;font-weight:600;text-align:center;padding:6px 8px;box-sizing:border-box;-moz-appearance:textfield'

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
  if (suffix) {
    const suf = document.createElement('span')
    suf.style.cssText = 'font-size:11px;color:#94a3b8'
    suf.textContent = String(suffix)
    right.appendChild(input)
    right.appendChild(suf)
  } else {
    right.appendChild(input)
  }
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
  row.appendChild(lbl)
  row.appendChild(right)
  return row
}

function btnStyle(selected) {
  const base =
    'min-height:36px;border-radius:12px;padding:8px 12px;font-size:12px;font-weight:600;cursor:pointer;border:1px solid rgba(255,255,255,0.14)'
  const idle = `${base};background:rgba(255,255,255,0.06);color:#cbd5e1`
  const on = `${base};background:linear-gradient(180deg,#8fd41a,#65a30d);color:#0b1220;border-color:rgba(132,204,22,0.55)`
  return selected ? on : idle
}

function sectionTitle(text) {
  const p = document.createElement('p')
  p.style.cssText = 'margin:0 0 8px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:#a3e635'
  p.textContent = text
  return p
}

function toggleRow(label, enabled, labels, onToggle, { premiumLocked = false, onPremiumLock } = {}) {
  const row = document.createElement('div')
  row.style.cssText =
    'display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;border-radius:12px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06)'
  const lblWrap = document.createElement('div')
  lblWrap.style.cssText = 'flex:1;display:flex;align-items:center;gap:6px;min-width:0'
  const lbl = document.createElement('span')
  lbl.style.cssText = 'flex:1;font-size:12px;color:#e2e8f0;line-height:1.35'
  lbl.textContent = String(label || '')
  lblWrap.appendChild(lbl)
  if (premiumLocked) {
    const lock = document.createElement('span')
    lock.style.cssText = 'flex-shrink:0;font-size:10px;color:#fbbf24'
    lock.textContent = '🔒'
    lblWrap.appendChild(lock)
  }
  const btn = document.createElement('button')
  btn.type = 'button'
  btn.style.cssText = btnStyle(!!enabled)
  if (premiumLocked) btn.style.opacity = '0.45'
  btn.textContent = enabled ? String(labels?.on || 'ON') : String(labels?.off || 'OFF')
  btn.addEventListener('click', (e) => {
    e.stopPropagation()
    if (premiumLocked) {
      onPremiumLock?.()
      return
    }
    onToggle(!enabled)
  })
  row.appendChild(lblWrap)
  row.appendChild(btn)
  return row
}

export function openJoinFilterVanillaModal(opts) {
  if (typeof document === 'undefined' || !document.documentElement) return null
  closeJoinFilterVanillaModal()

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
  body.style.cssText = 'flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px'

  function closeModal() {
    closeJoinFilterVanillaModal()
    try {
      opts?.onClose?.()
    } catch {
      //
    }
  }

  function triggerPremiumLock() {
    closeJoinFilterVanillaModal()
    try {
      opts?.onClose?.()
    } catch {
      //
    }
    setTimeout(() => {
      try {
        opts?.onPremiumLock?.()
      } catch {
        //
      }
    }, 0)
  }

  async function applyPatch(patch) {
    const key = Object.keys(patch || {})[0]
    if (key && PREMIUM_PATCH_KEYS.has(key) && !opts?.canPremium) {
      triggerPremiumLock()
      return
    }
    try {
      await opts?.onPatch?.(patch)
    } catch {
      //
    }
    renderBody()
  }

  const premiumOpts = () => ({
    premiumLocked: !opts?.canPremium,
    onPremiumLock: triggerPremiumLock,
  })

  function renderBody() {
    while (body.firstChild) body.removeChild(body.firstChild)
    const s = opts?.getState?.() || {}
    const labels = opts?.labels || {}
    const pOpts = premiumOpts()

    if (labels.intro) {
      const intro = document.createElement('p')
      intro.style.cssText = 'margin:0 0 4px;font-size:11px;line-height:1.45;color:#94a3b8'
      intro.textContent = String(labels.intro)
      body.appendChild(intro)
    }

    const readyBox = document.createElement('div')
    readyBox.style.cssText = 'display:flex;flex-direction:column;gap:8px'
    readyBox.appendChild(sectionTitle(String(labels.readyTitle || '')))
    const readyFields = [
      ['join_filter_arab', labels.arab],
      ['join_filter_cjk', labels.cjk],
      ['join_filter_zalgo', labels.zalgo],
      ['join_filter_spam_nick', labels.spamNick],
      ['join_filter_require_username', labels.requireUsername],
    ]
    for (const [key, lbl] of readyFields) {
      readyBox.appendChild(
        toggleRow(lbl, !!s[key], labels, (v) => applyPatch({ [key]: v })),
      )
    }
    readyBox.appendChild(
      toggleRow(labels.cas, !!s.join_filter_cas, labels, (v) => applyPatch({ join_filter_cas: v }), pOpts),
    )
    if (labels.casHint) {
      const casHint = document.createElement('p')
      casHint.style.cssText = 'margin:-4px 0 0;font-size:10px;color:#94a3b8;line-height:1.4'
      casHint.textContent = String(labels.casHint)
      readyBox.appendChild(casHint)
    }
    body.appendChild(readyBox)

    const netBox = document.createElement('div')
    netBox.style.cssText = 'display:flex;flex-direction:column;gap:8px'
    netBox.appendChild(sectionTitle(String(labels.networkTitle || '')))
    netBox.appendChild(
      toggleRow(labels.networkEnable, !!s.join_filter_network_mass_join, labels, (v) =>
        applyPatch({ join_filter_network_mass_join: v }), pOpts),
    )
    netBox.appendChild(
      numberFieldRow(
        labels.networkThreshold,
        s.join_filter_network_join_threshold ?? 4,
        { min: 2, max: 30, suffix: labels.networkChatsUnit },
        (v) => {
          if (!opts?.canPremium) {
            triggerPremiumLock()
            return
          }
          applyPatch({ join_filter_network_join_threshold: v })
        },
      ),
    )
    netBox.appendChild(
      numberFieldRow(
        labels.networkWindow,
        s.join_filter_network_join_window_minutes ?? 10,
        { min: 1, max: 120, suffix: labels.unitMin },
        (v) => {
          if (!opts?.canPremium) {
            triggerPremiumLock()
            return
          }
          applyPatch({ join_filter_network_join_window_minutes: v })
        },
      ),
    )
    if (labels.networkHint) {
      const netHint = document.createElement('p')
      netHint.style.cssText = 'margin:0;font-size:10px;color:#94a3b8;line-height:1.4'
      netHint.textContent = String(labels.networkHint)
      netBox.appendChild(netHint)
    }
    body.appendChild(netBox)

    const swBox = document.createElement('div')
    swBox.style.cssText = 'display:flex;flex-direction:column;gap:8px'
    swBox.appendChild(sectionTitle(String(labels.stopwordsTitle || '')))
    swBox.appendChild(
      toggleRow(labels.stopwordsEnable, !!s.join_filter_name_stopwords_enabled, labels, (v) =>
        applyPatch({ join_filter_name_stopwords_enabled: v }), pOpts),
    )
    const ta = document.createElement('textarea')
    ta.value = String(s.join_filter_name_stopwords || '')
    ta.placeholder = String(labels.stopwordsPlaceholder || '')
    ta.disabled = !opts?.canPremium
    if (!opts?.canPremium) ta.style.opacity = '0.45'
    ta.style.cssText =
      'width:100%;min-height:72px;border-radius:12px;border:1px solid rgba(255,255,255,0.12);background:rgba(0,0,0,0.35);color:#f1f5f9;font-size:12px;padding:10px;box-sizing:border-box;resize:vertical'
    ta.addEventListener('blur', () => {
      if (!opts?.canPremium) return
      const v = String(ta.value || '').slice(0, 2000)
      if (v !== String(s.join_filter_name_stopwords || '')) {
        applyPatch({ join_filter_name_stopwords: v })
      }
    })
    swBox.appendChild(ta)
    if (labels.stopwordsHint) {
      const hint = document.createElement('p')
      hint.style.cssText = 'margin:0;font-size:10px;color:#94a3b8;line-height:1.4'
      hint.textContent = String(labels.stopwordsHint)
      swBox.appendChild(hint)
    }
    body.appendChild(swBox)

    const closeBox = document.createElement('div')
    closeBox.style.cssText = 'display:flex;flex-direction:column;gap:8px'
    closeBox.appendChild(sectionTitle(String(labels.closeTitle || '')))
    closeBox.appendChild(
      toggleRow(labels.closeEnable, !!s.join_filter_close_entry, labels, (v) =>
        applyPatch({ join_filter_close_entry: v }), pOpts),
    )
    const actRow = document.createElement('div')
    actRow.style.cssText = 'display:flex;gap:8px'
    for (const opt of opts?.closeActions || []) {
      const b = document.createElement('button')
      b.type = 'button'
      b.style.cssText = btnStyle(String(s.join_filter_close_action || 'kick') === opt.value)
      if (!opts?.canPremium) b.style.opacity = '0.45'
      b.textContent = String(opt.label || '')
      b.addEventListener('click', (e) => {
        e.stopPropagation()
        if (!opts?.canPremium) {
          triggerPremiumLock()
          return
        }
        applyPatch({ join_filter_close_action: opt.value })
      })
      actRow.appendChild(b)
    }
    closeBox.appendChild(actRow)
    body.appendChild(closeBox)
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
  guardFilterChain('JoinFilterVanilla', 'appended', { ts: Date.now() })
  return root
}

export function closeJoinFilterVanillaModal() {
  const old = document.getElementById(ROOT_ID)
  if (old?.parentNode) {
    old.parentNode.removeChild(old)
    return true
  }
  return false
}

export function isJoinFilterVanillaModalOpen() {
  return !!document.getElementById(ROOT_ID)
}

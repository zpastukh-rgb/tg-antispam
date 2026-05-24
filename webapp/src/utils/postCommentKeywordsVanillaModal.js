/**
 * Vanilla-модалка «Автоудаление комментариев к постам» (Premium, linked discussion).
 */

import { guardFilterChain } from './guardDebugLog.js'

const ROOT_ID = 'guard-post-comment-kw-vanilla-modal-root'

function btnStyle(on) {
  const base =
    'min-height:36px;border-radius:12px;padding:8px 10px;font-size:11px;font-weight:600;cursor:pointer;border:1px solid rgba(255,255,255,0.14);flex:1'
  const idle = `${base};background:rgba(255,255,255,0.06);color:#cbd5e1`
  const active = `${base};background:linear-gradient(180deg,#8fd41a,#65a30d);color:#0b1220;border-color:rgba(132,204,22,0.55)`
  return on ? active : idle
}

function actionBtnStyle(active) {
  const base =
    'flex:1;min-height:36px;border-radius:12px;padding:8px 6px;font-size:11px;font-weight:600;cursor:pointer;border:1px solid rgba(255,255,255,0.12)'
  const idle = `${base};background:rgba(255,255,255,0.05);color:#cbd5e1`
  const on = `${base};background:rgba(132,204,22,0.22);border-color:rgba(132,204,22,0.5);color:#e2e8f0`
  return active ? on : idle
}

export function openPostCommentKeywordsVanillaModal(opts) {
  if (typeof document === 'undefined' || !document.documentElement) return null
  closePostCommentKeywordsVanillaModal()

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
    closePostCommentKeywordsVanillaModal()
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
    const premiumLocked = !!opts?.premiumLocked
    const linkedOk = !!opts?.linkedOk

    if (labels.intro) {
      const intro = document.createElement('p')
      intro.style.cssText = 'margin:0;font-size:11px;line-height:1.45;color:#94a3b8'
      intro.textContent = String(labels.intro)
      body.appendChild(intro)
    }

    if (s.linkedChannelTitle && labels.linkedChannel) {
      const badge = document.createElement('p')
      badge.style.cssText = 'margin:0;font-size:10px;color:#a5b4fc;line-height:1.4'
      badge.textContent = `${labels.linkedChannel}: ${s.linkedChannelTitle}`
      body.appendChild(badge)
    }

    if (!linkedOk && labels.noLink) {
      const warn = document.createElement('p')
      warn.style.cssText = 'margin:0;font-size:10px;color:#fbbf24;line-height:1.4'
      warn.textContent = String(labels.noLink)
      body.appendChild(warn)
      const recheck = document.createElement('button')
      recheck.type = 'button'
      recheck.textContent = String(labels.recheck || '↻')
      recheck.style.cssText =
        'align-self:flex-start;border-radius:10px;border:1px solid rgba(251,191,36,0.4);background:rgba(251,191,36,0.12);color:#fde68a;padding:6px 12px;font-size:11px;cursor:pointer'
      recheck.addEventListener('click', () => opts?.onRecheckLink?.())
      body.appendChild(recheck)
    }

    if (premiumLocked) {
      const lock = document.createElement('p')
      lock.style.cssText = 'margin:0;font-size:11px;color:#fbbf24'
      lock.textContent = '🔒 Premium'
      body.appendChild(lock)
    }

    const toggleWrap = document.createElement('div')
    toggleWrap.style.cssText = 'display:flex;gap:8px'
    const enabled = !!s.post_comment_keywords_enabled
    for (const opt of [
      { v: true, text: labels.on },
      { v: false, text: labels.off },
    ]) {
      const b = document.createElement('button')
      b.type = 'button'
      b.disabled = premiumLocked || !linkedOk
      b.style.cssText =
        btnStyle(enabled === opt.v) +
        (premiumLocked || !linkedOk ? ';opacity:0.45;cursor:not-allowed' : '')
      b.textContent = String(opt.text || '')
      b.addEventListener('click', () => {
        if (premiumLocked) {
          opts?.onPremiumLock?.()
          return
        }
        if (!linkedOk) return
        applyPatch({ post_comment_keywords_enabled: opt.v })
      })
      toggleWrap.appendChild(b)
    }
    body.appendChild(toggleWrap)

    const kwLabel = document.createElement('label')
    kwLabel.style.cssText = 'display:flex;flex-direction:column;gap:6px'
    const kwLbl = document.createElement('span')
    kwLbl.style.cssText = 'font-size:11px;color:#94a3b8'
    kwLbl.textContent = String(labels.keywordsLabel || '')
    const ta = document.createElement('textarea')
    ta.rows = 3
    ta.value = (s.keywordsText || '').trim()
    ta.placeholder = String(labels.keywordsPlaceholder || '')
    ta.disabled = premiumLocked
    ta.style.cssText =
      'width:100%;box-sizing:border-box;border-radius:12px;border:1px solid rgba(255,255,255,0.12);background:rgba(0,0,0,0.25);color:#e2e8f0;padding:8px 10px;font-size:12px;resize:vertical'
    kwLabel.appendChild(kwLbl)
    kwLabel.appendChild(ta)
    body.appendChild(kwLabel)

    const saveKw = document.createElement('button')
    saveKw.type = 'button'
    saveKw.textContent = String(labels.saveKeywords || 'Save')
    saveKw.disabled = premiumLocked
    saveKw.style.cssText =
      'border-radius:12px;border:1px solid rgba(132,204,22,0.45);background:rgba(132,204,22,0.18);color:#e2e8f0;padding:8px 12px;font-size:11px;font-weight:600;cursor:pointer' +
      (premiumLocked ? ';opacity:0.45;cursor:not-allowed' : '')
    saveKw.addEventListener('click', () => {
      if (premiumLocked) return
      const parts = String(ta.value || '')
        .split(/[,;\n]+/)
        .map((x) => x.trim())
        .filter(Boolean)
      applyPatch({ post_comment_keywords: parts })
    })
    body.appendChild(saveKw)

    if ((s.keywords || []).length) {
      const cur = document.createElement('p')
      cur.style.cssText = 'margin:0;font-size:10px;color:#64748b;line-height:1.4'
      cur.textContent = `${labels.current || ''}: ${(s.keywords || []).join(', ')}`
      body.appendChild(cur)
    }

    if (labels.actionLabel) {
      const al = document.createElement('p')
      al.style.cssText = 'margin:4px 0 0;font-size:10px;font-weight:700;text-transform:uppercase;color:#64748b'
      al.textContent = String(labels.actionLabel)
      body.appendChild(al)
    }
    const actRow = document.createElement('div')
    actRow.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap'
    const curAct = String(s.post_comment_keywords_action || 'delete')
    for (const opt of [
      { v: 'delete', label: labels.actionDelete },
      { v: 'mute', label: labels.actionMute },
      { v: 'ban', label: labels.actionBan },
    ]) {
      const b = document.createElement('button')
      b.type = 'button'
      b.disabled = premiumLocked
      b.style.cssText = actionBtnStyle(curAct === opt.v) + (premiumLocked ? ';opacity:0.45' : '')
      b.textContent = String(opt.label || opt.v)
      b.addEventListener('click', () => {
        if (premiumLocked) {
          opts?.onPremiumLock?.()
          return
        }
        applyPatch({ post_comment_keywords_action: opt.v })
      })
      actRow.appendChild(b)
    }
    body.appendChild(actRow)

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
  guardFilterChain('PostCommentKwVanilla', 'appended', { ts: Date.now() })
  return root
}

export function closePostCommentKeywordsVanillaModal() {
  const old = document.getElementById(ROOT_ID)
  if (old?.parentNode) {
    old.parentNode.removeChild(old)
    return true
  }
  return false
}

export function isPostCommentKeywordsVanillaModalOpen() {
  return !!document.getElementById(ROOT_ID)
}

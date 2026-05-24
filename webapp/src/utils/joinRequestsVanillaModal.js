/**
 * Vanilla-модалка «Заявки на вступление» (TMA-safe).
 */

import { guardFilterChain } from './guardDebugLog.js'
import {
  draftsToParsed,
  emptyQuestionDraft,
  parsedToDrafts,
  parseQuestionsText,
  questionsToText,
} from './joinRequestsQuestionsForm.js'

const ROOT_ID = 'guard-join-requests-vanilla-modal-root'

function btnStyle(selected) {
  const base =
    'min-height:36px;border-radius:12px;padding:8px 10px;font-size:11px;font-weight:600;cursor:pointer;border:1px solid rgba(255,255,255,0.14);flex:1'
  const idle = `${base};background:rgba(255,255,255,0.06);color:#cbd5e1`
  const on = `${base};background:linear-gradient(180deg,#8fd41a,#65a30d);color:#0b1220;border-color:rgba(132,204,22,0.55)`
  return selected ? on : idle
}

const inputStyle =
  'width:100%;box-sizing:border-box;border-radius:10px;border:1px solid rgba(255,255,255,0.12);background:rgba(0,0,0,0.25);color:#e2e8f0;padding:8px 10px;font-size:12px'

export function openJoinRequestsVanillaModal(opts) {
  if (typeof document === 'undefined' || !document.documentElement) return null
  closeJoinRequestsVanillaModal()

  let allowBackdropClose = false
  let draftQuestions = null
  let lastSerialized = null
  let showAdvancedQuestions = false

  setTimeout(() => {
    allowBackdropClose = true
  }, 650)

  const root = document.createElement('div')
  root.id = ROOT_ID
  root.style.cssText =
    'position:fixed;inset:0;z-index:2147483000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.82);padding:16px;box-sizing:border-box'

  const panel = document.createElement('div')
  panel.style.cssText =
    'width:100%;max-width:32rem;max-height:min(85dvh,calc(100dvh - 24px));overflow:hidden;display:flex;flex-direction:column;background:linear-gradient(180deg,#16161f,#0e0e14);border:1px solid rgba(255,255,255,0.12);border-radius:18px;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,sans-serif'

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
    draftQuestions = null
    lastSerialized = null
    closeJoinRequestsVanillaModal()
    try {
      opts?.onClose?.()
    } catch {
      //
    }
  }

  function triggerPremiumLock() {
    closeJoinRequestsVanillaModal()
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
    try {
      await opts?.onPatch?.(patch)
    } catch {
      //
    }
    renderBody()
  }

  function sectionLabel(text) {
    const p = document.createElement('p')
    p.style.cssText =
      'margin:0 0 6px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:#a3e635'
    p.textContent = text
    return p
  }

  function fieldLabel(text) {
    const lbl = document.createElement('span')
    lbl.style.cssText = 'font-size:11px;color:#94a3b8'
    lbl.textContent = text
    return lbl
  }

  function textArea(label, value, placeholder, onBlur, premiumLocked) {
    const box = document.createElement('div')
    box.style.cssText = 'display:flex;flex-direction:column;gap:6px'
    const row = document.createElement('div')
    row.style.cssText = 'display:flex;justify-content:space-between;align-items:center'
    const lbl = document.createElement('span')
    lbl.style.cssText = 'font-size:12px;color:#e2e8f0'
    lbl.textContent = label
    row.appendChild(lbl)
    if (premiumLocked) {
      const lock = document.createElement('span')
      lock.style.cssText = 'font-size:10px;color:#fbbf24'
      lock.textContent = '🔒 Premium'
      row.appendChild(lock)
    }
    box.appendChild(row)
    const ta = document.createElement('textarea')
    ta.value = String(value || '')
    ta.placeholder = String(placeholder || '')
    ta.disabled = !!premiumLocked
    ta.style.cssText =
      'width:100%;min-height:64px;border-radius:12px;border:1px solid rgba(255,255,255,0.12);background:rgba(0,0,0,0.35);color:#f1f5f9;font-size:12px;padding:10px;box-sizing:border-box;resize:vertical'
    ta.addEventListener('blur', () => {
      if (premiumLocked) return
      onBlur(String(ta.value || ''))
    })
    box.appendChild(ta)
    return box
  }

  function ensureDraft() {
    const s = opts?.getState?.() || {}
    const raw = String(s.join_requests_questions_text || '')
    if (draftQuestions === null || (lastSerialized !== null && raw !== lastSerialized)) {
      draftQuestions = parsedToDrafts(parseQuestionsText(raw))
      lastSerialized = raw
    }
    return draftQuestions
  }

  function maxQuestions() {
    return opts?.canPremium ? 5 : 1
  }

  function commitDrafts() {
    const parsed = draftsToParsed(draftQuestions)
    const text = questionsToText(parsed)
    lastSerialized = text
    applyPatch({ join_requests_questions_text: text.slice(0, 8000) })
  }

  function renderQuestionsBuilder(labels) {
    const wrap = document.createElement('div')
    wrap.style.cssText = 'display:flex;flex-direction:column;gap:10px'

    const headRow = document.createElement('div')
    headRow.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:8px'
    headRow.appendChild(fieldLabel(String(labels.questions || '')))
    const advToggle = document.createElement('button')
    advToggle.type = 'button'
    advToggle.textContent = String(labels.advancedToggle || '')
    advToggle.style.cssText =
      'border:none;background:transparent;color:#64748b;font-size:10px;cursor:pointer;text-decoration:underline;padding:0'
    advToggle.addEventListener('click', () => {
      showAdvancedQuestions = !showAdvancedQuestions
      renderBody()
    })
    headRow.appendChild(advToggle)
    wrap.appendChild(headRow)

    if (labels.questionsIntro) {
      const intro = document.createElement('p')
      intro.style.cssText = 'margin:0 0 4px;font-size:10px;color:#64748b;line-height:1.4'
      intro.textContent = String(labels.questionsIntro)
      wrap.appendChild(intro)
    }

    if (showAdvancedQuestions) {
      const s = opts?.getState?.() || {}
      wrap.appendChild(
        textArea('', s.join_requests_questions_text, labels.questionsPlaceholder, (v) => {
          draftQuestions = parsedToDrafts(parseQuestionsText(v))
          lastSerialized = v
          applyPatch({ join_requests_questions_text: v.slice(0, 8000) })
        }, false),
      )
      if (labels.questionsHint) {
        const hint = document.createElement('p')
        hint.style.cssText = 'margin:0;font-size:10px;color:#64748b;line-height:1.4'
        hint.textContent = String(labels.questionsHint)
        wrap.appendChild(hint)
      }
      return wrap
    }

    const drafts = ensureDraft()
    const limit = maxQuestions()

    drafts.forEach((q, qi) => {
      const card = document.createElement('div')
      card.style.cssText =
        'display:flex;flex-direction:column;gap:8px;padding:10px;border-radius:12px;border:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.03)'

      const cardHead = document.createElement('div')
      cardHead.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:8px'
      const cardTitle = document.createElement('span')
      cardTitle.style.cssText = 'font-size:11px;font-weight:600;color:#e2e8f0'
      cardTitle.textContent = String(labels.questionTitle || 'Question').replace('{n}', String(qi + 1))
      cardHead.appendChild(cardTitle)
      if (drafts.length > 1) {
        const rm = document.createElement('button')
        rm.type = 'button'
        rm.textContent = String(labels.removeQuestion || '×')
        rm.style.cssText =
          'border:none;background:transparent;color:#f87171;font-size:10px;cursor:pointer;padding:0'
        rm.addEventListener('click', () => {
          draftQuestions.splice(qi, 1)
          if (!draftQuestions.length) draftQuestions.push(emptyQuestionDraft())
          commitDrafts()
        })
        cardHead.appendChild(rm)
      }
      card.appendChild(cardHead)

      const qWrap = document.createElement('label')
      qWrap.style.cssText = 'display:flex;flex-direction:column;gap:4px'
      qWrap.appendChild(fieldLabel(String(labels.questionText || '')))
      const qInp = document.createElement('input')
      qInp.type = 'text'
      qInp.value = String(q.text || '')
      qInp.placeholder = String(labels.questionTextPh || '')
      qInp.style.cssText = inputStyle
      qInp.addEventListener('change', () => {
        q.text = qInp.value
        commitDrafts()
      })
      qWrap.appendChild(qInp)
      card.appendChild(qWrap)

      const aWrap = document.createElement('label')
      aWrap.style.cssText = 'display:flex;flex-direction:column;gap:4px'
      aWrap.appendChild(fieldLabel(String(labels.answersLabel || '')))
      const aInp = document.createElement('input')
      aInp.type = 'text'
      aInp.value = String(q.answersText || '')
      aInp.placeholder = String(labels.answersPh || '')
      aInp.style.cssText = inputStyle
      aInp.addEventListener('change', () => {
        q.answersText = aInp.value
        commitDrafts()
      })
      aWrap.appendChild(aInp)
      if (labels.answersHint) {
        const ah = document.createElement('span')
        ah.style.cssText = 'font-size:10px;color:#64748b;line-height:1.35'
        ah.textContent = String(labels.answersHint)
        aWrap.appendChild(ah)
      }
      card.appendChild(aWrap)

      if (!q.buttons.length) q.buttons = []
      const btnBlock = document.createElement('div')
      btnBlock.style.cssText = 'display:flex;flex-direction:column;gap:6px'
      btnBlock.appendChild(fieldLabel(String(labels.buttonsLabel || '')))
      q.buttons.forEach((b, bi) => {
        const row = document.createElement('div')
        row.style.cssText = 'display:flex;gap:6px;align-items:center'
        const lblInp = document.createElement('input')
        lblInp.type = 'text'
        lblInp.value = String(b.label || '')
        lblInp.placeholder = String(labels.buttonLabelPh || '')
        lblInp.style.cssText = `${inputStyle};flex:1`
        lblInp.addEventListener('change', () => {
          b.label = lblInp.value
          commitDrafts()
        })
        const urlInp = document.createElement('input')
        urlInp.type = 'text'
        urlInp.value = String(b.url || '')
        urlInp.placeholder = String(labels.buttonUrlPh || '')
        urlInp.style.cssText = `${inputStyle};flex:1.4`
        urlInp.addEventListener('change', () => {
          b.url = urlInp.value
          commitDrafts()
        })
        const rmBtn = document.createElement('button')
        rmBtn.type = 'button'
        rmBtn.textContent = '×'
        rmBtn.style.cssText =
          'flex-shrink:0;width:28px;height:28px;border-radius:8px;border:1px solid rgba(248,113,113,0.35);background:rgba(248,113,113,0.12);color:#fca5a5;cursor:pointer'
        rmBtn.addEventListener('click', () => {
          q.buttons.splice(bi, 1)
          commitDrafts()
        })
        row.appendChild(lblInp)
        row.appendChild(urlInp)
        row.appendChild(rmBtn)
        btnBlock.appendChild(row)
      })
      const addBtn = document.createElement('button')
      addBtn.type = 'button'
      addBtn.textContent = String(labels.addButton || '+')
      addBtn.style.cssText =
        'align-self:flex-start;border-radius:10px;border:1px dashed rgba(255,255,255,0.18);background:transparent;color:#94a3b8;padding:6px 10px;font-size:10px;cursor:pointer'
      addBtn.addEventListener('click', () => {
        if (q.buttons.length >= 6) return
        q.buttons.push({ label: '', url: '' })
        renderBody()
      })
      btnBlock.appendChild(addBtn)
      card.appendChild(btnBlock)

      wrap.appendChild(card)
    })

    const addQ = document.createElement('button')
    addQ.type = 'button'
    addQ.textContent = String(labels.addQuestion || '+')
    addQ.style.cssText =
      'border-radius:12px;border:1px dashed rgba(163,230,53,0.35);background:rgba(163,230,53,0.08);color:#bef264;padding:8px 12px;font-size:11px;font-weight:600;cursor:pointer'
    if (drafts.length >= limit) {
      addQ.disabled = true
      addQ.style.opacity = '0.45'
      addQ.title = String(labels.maxQuestionsHint || '')
    }
    addQ.addEventListener('click', () => {
      if (drafts.length >= limit) {
        if (!opts?.canPremium) triggerPremiumLock()
        return
      }
      draftQuestions.push(emptyQuestionDraft())
      renderBody()
    })
    wrap.appendChild(addQ)

    if (!opts?.canPremium && labels.maxQuestionsHint) {
      const lim = document.createElement('p')
      lim.style.cssText = 'margin:0;font-size:10px;color:#94a3b8'
      lim.textContent = String(labels.maxQuestionsHint)
      wrap.appendChild(lim)
    }

    return wrap
  }

  function renderBody() {
    while (body.firstChild) body.removeChild(body.firstChild)
    const s = opts?.getState?.() || {}
    const labels = opts?.labels || {}
    const canPremium = !!opts?.canPremium

    if (labels.intro) {
      const intro = document.createElement('p')
      intro.style.cssText = 'margin:0;font-size:11px;line-height:1.45;color:#94a3b8'
      intro.textContent = String(labels.intro)
      body.appendChild(intro)
    }

    body.appendChild(sectionLabel(String(labels.modeTitle || '')))
    const modeRow = document.createElement('div')
    modeRow.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px'
    for (const m of opts?.modes || []) {
      const b = document.createElement('button')
      b.type = 'button'
      b.style.cssText = btnStyle(String(s.join_requests_mode || 'off') === m.value)
      b.textContent = String(m.label || '')
      if (m.premium && !canPremium) {
        b.style.opacity = '0.45'
      }
      b.addEventListener('click', (e) => {
        e.stopPropagation()
        if (m.premium && !canPremium) {
          triggerPremiumLock()
          return
        }
        applyPatch({ join_requests_mode: m.value })
      })
      modeRow.appendChild(b)
    }
    body.appendChild(modeRow)

    const mode = String(s.join_requests_mode || 'off')
    if (mode === 'survey_auto' || mode === 'survey_manual') {
      body.appendChild(renderQuestionsBuilder(labels))
      body.appendChild(
        textArea(
          labels.welcome,
          s.join_requests_welcome_text,
          labels.welcomePlaceholder,
          (v) => applyPatch({ join_requests_welcome_text: v.slice(0, 2000) }),
          !canPremium,
        ),
      )
      body.appendChild(
        textArea(
          labels.done,
          s.join_requests_done_text,
          labels.donePlaceholder,
          (v) => applyPatch({ join_requests_done_text: v.slice(0, 2000) }),
          !canPremium,
        ),
      )
    }

    if (mode === 'survey_manual' || mode === 'survey_auto') {
      body.appendChild(sectionLabel(String(labels.reportTitle || '')))
      const repRow = document.createElement('div')
      repRow.style.cssText = 'display:flex;gap:8px'
      for (const r of opts?.reportModes || []) {
        const b = document.createElement('button')
        b.type = 'button'
        b.style.cssText = btnStyle(String(s.join_requests_report_mode || 'full') === r.value)
        b.textContent = String(r.label || '')
        if (r.premium && !canPremium) b.style.opacity = '0.45'
        b.addEventListener('click', (e) => {
          e.stopPropagation()
          if (r.premium && !canPremium) {
            triggerPremiumLock()
            return
          }
          applyPatch({ join_requests_report_mode: r.value })
        })
        repRow.appendChild(b)
      }
      body.appendChild(repRow)
    }

    if (labels.hint) {
      const hint = document.createElement('p')
      hint.style.cssText = 'margin:0;font-size:10px;color:#64748b;line-height:1.4'
      hint.textContent = String(labels.hint)
      body.appendChild(hint)
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
  guardFilterChain('JoinRequestsVanilla', 'appended', { ts: Date.now() })
  return root
}

export function closeJoinRequestsVanillaModal() {
  const old = document.getElementById(ROOT_ID)
  if (old?.parentNode) {
    old.parentNode.removeChild(old)
    return true
  }
  return false
}

export function isJoinRequestsVanillaModalOpen() {
  return !!document.getElementById(ROOT_ID)
}

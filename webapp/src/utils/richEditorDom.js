/**
 * Shared contenteditable helpers (broadcast composer, welcome text, channel post rules).
 */

export function editorFragHasStructuralContent(frag) {
  const t = String(frag?.textContent || '')
  const plain = t.replace(/\u200b/g, '').replace(/\u00a0/g, '')
  if (plain.trim()) return true
  return !!(frag && typeof frag.querySelector === 'function' && frag.querySelector('br,img'))
}

/** Unwrap `<a>`/`code`/etc. replacement for `container` siblings (spoiler-like or block wrappers). */
export function editorWrapResidualFormat(container, frag) {
  if (!(frag instanceof DocumentFragment || frag instanceof Node)) return null
  if (!editorFragHasStructuralContent(frag)) return null
  const doc = container.ownerDocument || document
  const t = String(container.tagName || '').toLowerCase()
  if (t === 'blockquote') {
    const b = doc.createElement('blockquote')
    b.appendChild(frag)
    return b
  }
  if (t === 'pre') {
    const p = doc.createElement('pre')
    p.appendChild(frag)
    return p
  }
  if (t === 'tg-spoiler') {
    const ns = doc.createElement('tg-spoiler')
    ns.appendChild(frag)
    return ns
  }
  const sp = doc.createElement('span')
  sp.setAttribute('data-spoiler', '1')
  sp.appendChild(frag)
  return sp
}

export function editorUnwrapElementFully(container) {
  const parent = container.parentNode
  if (!(parent instanceof Node)) return false
  while (container.firstChild) parent.insertBefore(container.firstChild, container)
  parent.removeChild(container)
  return true
}

/**
 * Split spoiler / quote / pre around selection: before+after remain wrapped where non-empty.
 * @returns {boolean}
 */
export function editorUnwrapRangeInsideContainer(container, range) {
  if (!(container instanceof HTMLElement) || !(range instanceof Range)) return false
  const parent = container.parentNode
  if (!(parent instanceof Node)) return false
  if (!container.contains(range.commonAncestorContainer)) return false
  const doc = container.ownerDocument || document
  const clone = range.cloneRange()
  try {
    const nextSibling = container.nextSibling

    const preRange = doc.createRange()
    preRange.selectNodeContents(container)
    preRange.setEnd(clone.startContainer, clone.startOffset)
    const preFrag = preRange.extractContents()

    const midFrag = clone.extractContents()

    const postRange = doc.createRange()
    postRange.selectNodeContents(container)
    const postFrag = postRange.extractContents()

    parent.removeChild(container)

    const out = doc.createDocumentFragment()
    const wPre = editorWrapResidualFormat(container, preFrag)
    if (wPre) out.appendChild(wPre)
    out.appendChild(midFrag)
    const wPost = editorWrapResidualFormat(container, postFrag)
    if (wPost) out.appendChild(wPost)

    parent.insertBefore(out, nextSibling)
    return true
  } catch {
    return false
  }
}

export function editorPlaceCaretAtEditableStart(el) {
  const sel = window.getSelection?.()
  if (!sel || !(el instanceof HTMLElement)) return
  const nr = el.ownerDocument.createRange()
  if (!el.childNodes.length) {
    nr.setStart(el, 0)
    nr.collapse(true)
  } else {
    const first = el.firstChild
    if (first.nodeType === Node.TEXT_NODE) {
      nr.setStart(first, 0)
      nr.collapse(true)
    } else if (first.nodeType === Node.ELEMENT_NODE && first.nodeName === 'BR') {
      nr.setStartBefore(first)
      nr.collapse(true)
    } else {
      nr.setStart(el, 0)
      nr.collapse(true)
    }
  }
  sel.removeAllRanges()
  sel.addRange(nr)
}

/**
 * Plain Enter exits blockquote to a sibling line (Shift+Enter keeps line inside quote).
 */
export function editorSplitBlockquoteAtCaret(root, placeCaretAtStart = editorPlaceCaretAtEditableStart) {
  const sel = window.getSelection?.()
  if (!sel?.rangeCount) return false
  const range = sel.getRangeAt(0)
  if (!(root instanceof HTMLElement) || !root.contains(range.commonAncestorContainer)) return false

  let anchor = range.commonAncestorContainer
  if (anchor.nodeType === Node.TEXT_NODE) anchor = anchor.parentElement
  const bq = anchor?.closest?.('blockquote')
  if (!bq || !root.contains(bq)) return false

  const headProbe = root.ownerDocument.createRange()
  headProbe.selectNodeContents(bq)
  headProbe.setEnd(range.startContainer, range.startOffset)
  const atQuoteStart = headProbe.toString().replace(/\u200b/g, '').length === 0

  if (atQuoteStart) {
    const spacer = root.ownerDocument.createElement('div')
    spacer.appendChild(root.ownerDocument.createElement('br'))
    bq.parentNode?.insertBefore(spacer, bq)
    placeCaretAtStart(spacer)
    root.focus()
    return true
  }

  const tailRange = root.ownerDocument.createRange()
  tailRange.setStart(range.startContainer, range.startOffset)
  const last = bq.lastChild
  if (last) tailRange.setEndAfter(last)
  else tailRange.setEnd(range.startContainer, range.startOffset)

  const frag = tailRange.extractContents()

  const newDiv = root.ownerDocument.createElement('div')
  if (frag.childNodes.length) {
    newDiv.appendChild(frag)
  }
  const tailPlain = String(newDiv.textContent || '').replace(/\u200b/g, '').trim()
  if (!tailPlain && !newDiv.querySelector('br')) {
    newDiv.appendChild(root.ownerDocument.createElement('br'))
  }

  bq.parentNode?.insertBefore(newDiv, bq.nextSibling)

  const bqPlain = String(bq.textContent || '').replace(/\u200b/g, '').trim()
  if (!bqPlain && !bq.querySelector('img')) {
    bq.remove()
  } else if (!bq.childNodes.length) {
    bq.appendChild(root.ownerDocument.createElement('br'))
  }

  placeCaretAtStart(newDiv)
  root.focus()
  return true
}

/**
 * Shift+Enter внутри цитаты: явно вставляем br, чтобы не плодить второй blockquote
 * в WebView Telegram (поведение по умолчанию там непредсказуемо).
 * @returns {boolean} обработано
 */
export function editorSoftBreakInsideBlockquote(root) {
  const sel = window.getSelection?.()
  if (!sel?.rangeCount) return false
  const range = sel.getRangeAt(0)
  if (!(root instanceof HTMLElement) || !root.contains(range.commonAncestorContainer)) return false
  let n = range.commonAncestorContainer
  if (n.nodeType === Node.TEXT_NODE) n = n.parentElement
  const bq = n?.closest?.('blockquote')
  if (!bq || !root.contains(bq)) return false
  const doc = root.ownerDocument || document
  try {
    range.deleteContents()
    const br = doc.createElement('br')
    range.insertNode(br)
    range.setStartAfter(br)
    range.collapse(true)
    sel.removeAllRanges()
    sel.addRange(range)
  } catch {
    return false
  }
  root.focus()
  return true
}

export function editorResetTypingExecCommands(editorRoot, { coerceUnderlineSpans } = {}) {
  if (!(editorRoot instanceof HTMLElement)) return
  const sel = window.getSelection?.()
  if (!sel?.rangeCount) return
  const r = sel.getRangeAt(0)
  if (!editorRoot.contains(r.commonAncestorContainer)) return
  editorRoot.focus()
  try {
    document.execCommand('styleWithCSS', false, false)
  } catch {
    //
  }
  for (const cmd of ['bold', 'italic', 'underline', 'strikeThrough']) {
    try {
      if (document.queryCommandState(cmd)) document.execCommand(cmd, false, null)
    } catch {
      //
    }
  }
  if (typeof coerceUnderlineSpans === 'function') coerceUnderlineSpans(editorRoot)
}

/**
 * Моноширинный фрагмент для Telegram (`<code>`), без блока `<pre>` (в клиенте — «копировать»).
 * @param {HTMLElement} editorEl
 * @param {Range} range
 * @param {{ onEmpty?: () => void }} [opts]
 * @returns {boolean}
 */
export function editorApplyMonospaceFormat(editorEl, range, opts = {}) {
  if (!editorEl || !range) return false
  editorEl.focus()
  let n = range.commonAncestorContainer
  if (n.nodeType === Node.TEXT_NODE) n = n.parentElement
  const preEl = n?.closest?.('pre')
  const codeEl = n?.closest?.('code')
  const monoEl = preEl && editorEl.contains(preEl) ? preEl : codeEl && editorEl.contains(codeEl) ? codeEl : null
  if (monoEl) {
    if (range.collapsed || !(range.toString() || '').trim()) {
      editorUnwrapElementFully(monoEl)
    } else if (!editorUnwrapRangeInsideContainer(monoEl, range)) {
      editorUnwrapElementFully(monoEl)
    }
    return true
  }
  const text = range.toString() || ''
  if (!text.trim()) {
    if (typeof opts.onEmpty === 'function') opts.onEmpty()
    return false
  }
  const doc = editorEl.ownerDocument || document
  const code = doc.createElement('code')
  code.textContent = text
  try {
    range.deleteContents()
    range.insertNode(code)
    range.setStartAfter(code)
    range.collapse(true)
    const sel = window.getSelection?.()
    sel?.removeAllRanges()
    sel?.addRange(range)
  } catch {
    return false
  }
  return true
}

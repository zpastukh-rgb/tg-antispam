/**
 * Переводит сохранённую строку Telegram HTML в innerHTML редактора:
 * переносы строк в тексте → `<br>` (внутри `<pre>` не трогаем).
 * Без этого `\n` между тегами не даёт отдельную строку в contenteditable.
 * @param {string} stored
 * @returns {string}
 */
export function telegramHtmlToEditorInnerHtml(stored) {
  const raw = String(stored || '')
  if (!raw.trim()) return ''
  const host = document.createElement('div')
  host.innerHTML = raw
  const tw = document.createTreeWalker(host, NodeFilter.SHOW_TEXT, null)
  const textNodes = []
  let node = tw.nextNode()
  while (node) {
    textNodes.push(node)
    node = tw.nextNode()
  }
  for (const tn of textNodes) {
    let el = tn.parentElement
    let inPre = false
    while (el && el !== host) {
      const tag = String(el.tagName || '').toLowerCase()
      if (tag === 'pre') {
        inPre = true
        break
      }
      el = el.parentElement
    }
    if (inPre) continue
    const t = tn.textContent || ''
    if (!t.includes('\n')) continue
    const parts = t.split('\n')
    const frag = document.createDocumentFragment()
    parts.forEach((part, idx) => {
      frag.appendChild(document.createTextNode(part))
      if (idx < parts.length - 1) frag.appendChild(document.createElement('br'))
    })
    tn.parentNode?.replaceChild(frag, tn)
  }
  // В contenteditable кастомный тег <tg-spoiler> часто не получает ожидаемых стилей; в редакторе рассылок используется span[data-spoiler].
  const spoilers = host.querySelectorAll('tg-spoiler')
  for (let i = spoilers.length - 1; i >= 0; i -= 1) {
    const node = spoilers.item(i)
    if (!node?.parentNode) continue
    const span = document.createElement('span')
    span.setAttribute('data-spoiler', '1')
    while (node.firstChild) span.appendChild(node.firstChild)
    node.parentNode.replaceChild(span, node)
  }
  return host.innerHTML
}

/**
 * DOM → подмножество Telegram HTML (как в редакторе рассылок).
 * @param {string} raw
 * @returns {string}
 */
export function normalizeHtmlForTelegram(raw) {
  const esc = (s) =>
    String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
  const host = document.createElement('div')
  host.innerHTML = String(raw || '')
  const walk = (node) => {
    if (!node) return ''
    if (node.nodeType === Node.TEXT_NODE) return esc(node.textContent || '')
    if (node.nodeType !== Node.ELEMENT_NODE) return ''
    const el = node
    const tag = String(el.tagName || '').toLowerCase()
    const inner = Array.from(el.childNodes || [])
      .map((n) => walk(n))
      .join('')
    if (tag === 'br') return '\n'
    if (tag === 'div' || tag === 'p') return `${inner}\n`
    if (tag === 'b' || tag === 'strong') return `<b>${inner}</b>`
    if (tag === 'i' || tag === 'em') return `<i>${inner}</i>`
    if (tag === 'u') return `<u>${inner}</u>`
    if (tag === 's' || tag === 'strike' || tag === 'del') return `<s>${inner}</s>`
    if (tag === 'code') return `<code>${inner}</code>`
    if (tag === 'pre') return `<pre>${inner}</pre>`
    if (tag === 'blockquote') return `<blockquote>${inner}</blockquote>`
    if (tag === 'a') {
      const href = String(el.getAttribute('href') || '')
        .trim()
        .replace(/"/g, '&quot;')
      return href ? `<a href="${href}">${inner}</a>` : inner
    }
    if (tag === 'span' && String(el.getAttribute('data-spoiler') || '') === '1') {
      return `<tg-spoiler>${inner}</tg-spoiler>`
    }
    if (tag === 'span') {
      const style = String(el.getAttribute('style') || '').toLowerCase()
      let out = inner
      // Safari/iOS may output formatting via inline styles instead of semantic tags.
      if (style.includes('font-weight: bold') || style.includes('font-weight:bold') || /font-weight:\s*[6-9]00/.test(style)) {
        out = `<b>${out}</b>`
      }
      if (style.includes('font-style: italic') || style.includes('font-style:italic')) {
        out = `<i>${out}</i>`
      }
      if (style.includes('text-decoration: underline') || style.includes('text-decoration:underline') || style.includes('text-decoration-line: underline')) {
        out = `<u>${out}</u>`
      }
      if (
        style.includes('line-through') ||
        style.includes('text-decoration: line-through') ||
        style.includes('text-decoration-line: line-through')
      ) {
        out = `<s>${out}</s>`
      }
      return out
    }
    if (tag === 'tg-spoiler') return `<tg-spoiler>${inner}</tg-spoiler>`
    if (tag === 'tg-emoji') {
      const id = String(el.getAttribute('emoji-id') || '').trim()
      return id ? `<tg-emoji emoji-id="${id}">${inner || '🙂'}</tg-emoji>` : inner || '🙂'
    }
    return inner
  }
  return walk(host)
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

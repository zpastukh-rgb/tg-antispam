/**
 * Парсинг / сборка текста опросника заявок (совместимо с app/services/join_requests_survey.py).
 */

const MAX_QUESTIONS = 5
const MAX_ANSWERS = 5
const MAX_BUTTONS_PER_ROW = 2
const MAX_BUTTON_ROWS = 3
const MAX_BUTTON_LABEL = 64

export function normalizeButtonUrl(raw) {
  const u = String(raw || '').trim()
  if (!u) return null
  const low = u.toLowerCase()
  if (low.startsWith('http://') || low.startsWith('https://')) return u.slice(0, 512)
  if (low.startsWith('t.me/') || low.startsWith('telegram.me/')) return `https://${u.replace(/^\/+/, '')}`.slice(0, 512)
  if (u.startsWith('tg://')) return u.slice(0, 512)
  return null
}

export function parseButtonRows(rawLines) {
  const rows = []
  for (const line of rawLines || []) {
    const s = String(line || '').trim()
    if (!s) continue
    const row = []
    for (const part of s.split('&&')) {
      const token = String(part || '').trim()
      if (!token.includes('=')) continue
      const eq = token.indexOf('=')
      const label = token.slice(0, eq).trim().slice(0, MAX_BUTTON_LABEL)
      const url = normalizeButtonUrl(token.slice(eq + 1))
      if (label && url) row.push({ text: label, url })
      if (row.length >= MAX_BUTTONS_PER_ROW) break
    }
    if (row.length) rows.push(row)
    if (rows.length >= MAX_BUTTON_ROWS) break
  }
  return rows
}

export function buttonRowsToText(rows) {
  const parts = []
  for (const row of (rows || []).slice(0, MAX_BUTTON_ROWS)) {
    const tokens = []
    for (const btn of (row || []).slice(0, MAX_BUTTONS_PER_ROW)) {
      const text = String(btn?.text || '').trim()
      const url = String(btn?.url || '').trim()
      if (text && url) tokens.push(`${text}=${url}`)
    }
    if (tokens.length) parts.push(tokens.join(' && '))
  }
  return parts.join('\n')
}

export function parseQuestionsText(raw) {
  if (!raw) return []
  const text = String(raw).replace(/\r\n/g, '\n').trim()
  if (!text) return []
  const blocks = text.split(/\n\s*\n+/)
  const out = []
  for (const block of blocks) {
    let qLine = ''
    let aLine = ''
    const bLines = []
    for (const line of block.split('\n')) {
      const s = line.trim()
      if (!s) continue
      const low = s.toLowerCase()
      if (low.startsWith('q:')) qLine = s.slice(2).trim()
      else if (low.startsWith('a:')) aLine = s.slice(2).trim()
      else if (low.startsWith('b:')) bLines.push(s.slice(2).trim())
      else if (!qLine) qLine = s
      else if (!aLine) aLine = s
    }
    if (!qLine) continue
    const answers = aLine
      .split(/[;|]/)
      .map((p) => p.trim().toLowerCase())
      .filter(Boolean)
      .slice(0, MAX_ANSWERS)
    if (!answers.length) continue
    const item = { text: qLine.slice(0, 500), answers }
    const btnRows = parseButtonRows(bLines)
    if (btnRows.length) item.buttons = btnRows
    out.push(item)
  }
  return out.slice(0, MAX_QUESTIONS)
}

export function questionsToText(questions) {
  const parts = []
  for (const q of (questions || []).slice(0, MAX_QUESTIONS)) {
    const text = String(q?.text || '').trim()
    const ans = (q?.answers || []).filter(Boolean)
    if (!text || !ans.length) continue
    let block = `Q: ${text}\nA: ${ans.slice(0, MAX_ANSWERS).join('; ')}`
    const btnText = buttonRowsToText(q?.buttons || [])
    if (btnText) {
      for (const bLine of btnText.split('\n')) {
        if (bLine.trim()) block += `\nB: ${bLine.trim()}`
      }
    }
    parts.push(block)
  }
  return parts.join('\n\n')
}

export function emptyQuestionDraft() {
  return { text: '', answersText: '', buttons: [] }
}

export function parsedToDrafts(parsed) {
  const list = Array.isArray(parsed) ? parsed : []
  if (!list.length) return [emptyQuestionDraft()]
  return list.map((q) => ({
    text: String(q.text || ''),
    answersText: (q.answers || []).join(', '),
    buttons: flattenButtonRows(q.buttons || []),
  }))
}

export function flattenButtonRows(rows) {
  const out = []
  for (const row of rows || []) {
    for (const btn of row || []) {
      out.push({
        label: String(btn?.text || ''),
        url: String(btn?.url || ''),
      })
    }
  }
  return out
}

export function draftsToParsed(drafts) {
  const out = []
  for (const d of drafts || []) {
    const text = String(d?.text || '').trim()
    const answers = String(d?.answersText || '')
      .split(/[;,|]/)
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean)
      .slice(0, MAX_ANSWERS)
    if (!text || !answers.length) continue

    const buttonRows = []
    let row = []
    for (const b of d.buttons || []) {
      const label = String(b?.label || '').trim().slice(0, MAX_BUTTON_LABEL)
      const url = normalizeButtonUrl(b?.url)
      if (!label || !url) continue
      row.push({ text: label, url })
      if (row.length >= MAX_BUTTONS_PER_ROW) {
        buttonRows.push(row)
        row = []
      }
    }
    if (row.length) buttonRows.push(row)

    const item = { text: text.slice(0, 500), answers }
    if (buttonRows.length) item.buttons = buttonRows.slice(0, MAX_BUTTON_ROWS)
    out.push(item)
  }
  return out.slice(0, MAX_QUESTIONS)
}

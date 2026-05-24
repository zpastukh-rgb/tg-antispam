const LINK_REASONS = new Set(['link', 'link_blacklist', 'global_bad_url', 'global_url', 'url'])
const WORD_REASONS = new Set([
  'casino', 'profanity', 'stopword', 'jobs', 'crypto', 'ads', 'insult', 'racism',
  'nazi', 'vulgar', 'politics', 'drugs', 'religion', 'esoteric', 'flood', 'spam',
  'buttons', 'media', 'mention', 'forward', 'silence',
])

function normalizeReasonKey(reason) {
  let base = String(reason || '').trim().toLowerCase()
  if (!base) return ''
  if (base.endsWith('_newbie')) base = base.slice(0, -'_newbie'.length)
  if (base in { link_blacklist: 1, global_bad_url: 1, global_url: 1, url: 1 }) return 'link'
  return base
}

function extractLinkTrigger(message) {
  const msg = String(message || '').trim()
  if (!msg) return ''
  const low = msg.toLowerCase()
  for (const marker of ['https://', 'http://', 'tg://', 't.me/', 'telegram.me/']) {
    const idx = low.indexOf(marker)
    if (idx >= 0) {
      const chunk = msg.slice(idx).split(/\s/)[0] || msg.slice(idx, idx + 120)
      return chunk.slice(0, 120)
    }
  }
  const wwwIdx = low.indexOf('www.')
  if (wwwIdx >= 0) {
    const chunk = msg.slice(wwwIdx).split(/\s/)[0] || msg.slice(wwwIdx, wwwIdx + 120)
    return chunk.slice(0, 120)
  }
  const domain = msg.match(/(?:https?:\/\/)?(?:[\w-]+\.)+[a-z]{2,}(?:\/[^\s]*)?/i)
  if (domain) return domain[0].slice(0, 120)
  const bare = msg.match(/\b[\w.-]*\d[\w.-]*(?:\.[a-z]{2,})?\b/i)
  if (bare) return bare[0].slice(0, 120)
  return ''
}

function extractMentionTrigger(message) {
  const msg = String(message || '').trim()
  const m = msg.match(/@[\w]{2,}/)
  return m ? m[0] : ''
}

function extractQuotedToken(message) {
  const msg = String(message || '').trim()
  const quoted = msg.match(/["«]([^"»\n]{2,48})["»]/)
  if (quoted) return quoted[1].trim()
  return ''
}

function extractWordTrigger(message) {
  const msg = String(message || '').trim()
  if (!msg) return ''
  const quoted = extractQuotedToken(msg)
  if (quoted) return quoted.slice(0, 80)
  const line = msg.split('\n', 1)[0].trim()
  if (line.length <= 80) return line
  const parts = line.split(/\s+/).filter(Boolean)
  return parts[0] ? parts[0].slice(0, 48) : line.slice(0, 48)
}

function extractFromAllLines(message, base) {
  const msg = String(message || '').trim()
  if (!msg) return ''
  const lines = msg.split('\n').map((l) => l.trim()).filter(Boolean)
  for (const line of lines) {
    const link = extractLinkTrigger(line)
    if (link) return link
    const quoted = extractQuotedToken(line)
    if (quoted) return quoted.slice(0, 80)
    if (base === 'casino' || base === 'link') {
      const bare = line.match(/\b[\w.-]*\d[\w.-]*(?:\.[a-z]{2,})?\b/i)
      if (bare) return bare[0].slice(0, 80)
    }
  }
  return ''
}

/** Триггер для UI: detail из лога или вывод из текста/причины. */
export function resolveModerationTrigger(row) {
  const fromApi = String(row?.trigger || '').trim()
  if (fromApi && fromApi !== '—') return fromApi
  const detail = String(row?.detail || '').trim()
  if (detail) return detail
  const msg = String(row?.message_text || '').trim()
  if (!msg) return '—'
  const base = normalizeReasonKey(row?.reason)
  if (!base) return extractWordTrigger(msg) || '—'
  if (LINK_REASONS.has(base) || base.startsWith('link') || base === 'casino' || base === 'crypto') {
    const multi = extractFromAllLines(msg, base)
    if (multi) return multi
    return extractLinkTrigger(msg) || extractWordTrigger(msg) || '—'
  }
  if (base.startsWith('mention_')) {
    return extractMentionTrigger(msg) || extractWordTrigger(msg) || '—'
  }
  if (base.startsWith('media_') || base.startsWith('button_')) {
    return extractWordTrigger(msg) || '—'
  }
  if (WORD_REASONS.has(base)) {
    return extractWordTrigger(msg) || '—'
  }
  return extractWordTrigger(msg) || '—'
}

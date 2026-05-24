/** Цвета аватаров в духе Telegram (градиент по id чата). */
export const CHAT_AVATAR_GRADIENTS = Object.freeze([
  'linear-gradient(135deg, #e17076 0%, #cb5b62 100%)',
  'linear-gradient(135deg, #faa774 0%, #e07b39 100%)',
  'linear-gradient(135deg, #a695e7 0%, #8878d6 100%)',
  'linear-gradient(135deg, #7bc862 0%, #65aadd 100%)',
  'linear-gradient(135deg, #6ec9cb 0%, #47bcd1 100%)',
  'linear-gradient(135deg, #65aadd 0%, #4a95c9 100%)',
  'linear-gradient(135deg, #ee7aae 0%, #d45e96 100%)',
])

function firstMeaningfulChar(title) {
  const t = String(title || '').trim()
  if (!t) return ''
  const m = t.match(/[\p{L}\p{N}]/u)
  return m ? m[0].toUpperCase() : ''
}

/** Буква и фон для заглушки без фото. */
export function chatAvatarFallbackMeta(chatId, title, username) {
  const fromTitle = firstMeaningfulChar(title)
  const fromUser = String(username || '').trim().replace(/^@+/, '')
  const letter = fromTitle || (fromUser ? fromUser[0].toUpperCase() : '?')
  const idNum = Number(chatId || 0)
  const idx = Math.abs(Number.isFinite(idNum) ? idNum : 0) % CHAT_AVATAR_GRADIENTS.length
  return {
    letter: letter.slice(0, 1),
    background: CHAT_AVATAR_GRADIENTS[idx],
  }
}

const avatarBlobCache = new Map()

export function readCachedChatAvatarUrl(chatId) {
  const key = String(chatId || '').trim()
  if (!key) return ''
  return avatarBlobCache.get(key) || ''
}

export function writeCachedChatAvatarUrl(chatId, blobUrl) {
  const key = String(chatId || '').trim()
  if (!key || !blobUrl) return
  avatarBlobCache.set(key, blobUrl)
}

export function forgetCachedChatAvatarUrl(chatId) {
  const key = String(chatId || '').trim()
  if (!key) return
  const prev = avatarBlobCache.get(key)
  if (prev) {
    try {
      URL.revokeObjectURL(prev)
    } catch {
      //
    }
  }
  avatarBlobCache.delete(key)
}

/** Короткий кэш в sessionStorage: мгновенный первый кадр, затем фоновое обновление. */
export function readSessionJson(key, maxAgeMs = 5 * 60 * 1000) {
  if (typeof sessionStorage === 'undefined') return null
  try {
    const raw = sessionStorage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    if (maxAgeMs > 0 && Date.now() - Number(parsed.ts || 0) > maxAgeMs) return null
    return parsed.data ?? null
  } catch {
    return null
  }
}

export function writeSessionJson(key, data) {
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.setItem(key, JSON.stringify({ ts: Date.now(), data }))
  } catch {
    //
  }
}

export function readLocalJson(key, maxAgeMs = 24 * 60 * 60 * 1000) {
  if (typeof localStorage === 'undefined') return null
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    if (maxAgeMs > 0 && Date.now() - Number(parsed.ts || 0) > maxAgeMs) return null
    return parsed.data ?? null
  } catch {
    return null
  }
}

export function writeLocalJson(key, data) {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(key, JSON.stringify({ ts: Date.now(), data }))
  } catch {
    //
  }
}

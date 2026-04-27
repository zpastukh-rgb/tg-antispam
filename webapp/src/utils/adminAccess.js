/**
 * Полный доступ к админке (как на бэке: _is_full_admin_user + /api/me is_admin).
 * Premium без этого флага — только «кабинет Premium» в AdminView.
 */

const DEFAULT_OWNER_USERNAMES = new Set(['pastukh_viscera'])

function ownerTelegramIdsFromEnv() {
  const raw = String(import.meta.env.VITE_OWNER_TELEGRAM_IDS || '').trim()
  const ids = new Set()
  for (const part of raw.split(/[\s,]+/)) {
    const n = Number(part)
    if (Number.isFinite(n) && n > 0) ids.add(n)
  }
  return ids
}

const OWNER_TELEGRAM_IDS = ownerTelegramIdsFromEnv()

/**
 * Полная админка (все вкладки). Должно совпадать с логикой API после фикса /api/me.
 * @param {{ is_admin?: boolean, is_premium?: boolean, username?: string|null, telegram_id?: number }} me
 */
export function hasFullAdminRights(me) {
  if (!me) return false
  if (me.is_admin) return true
  const tid = Number(me.telegram_id || 0)
  if (tid && OWNER_TELEGRAM_IDS.has(tid)) return true
  const u = String(me.username || '')
    .trim()
    .replace(/^@/, '')
    .toLowerCase()
  if (u && DEFAULT_OWNER_USERNAMES.has(u)) return true
  return false
}

/** Кнопка «ADM»: полный админ или Premium (вход в кабинет / упрощённую админку). */
export function canOpenAdminEntry(me) {
  if (!me) return false
  if (hasFullAdminRights(me)) return true
  return !!me.is_premium
}

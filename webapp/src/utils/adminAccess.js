/**
 * Полный доступ к админке (как на бэке: _is_full_admin_user + /api/me is_admin).
 * Premium без этого флага — только «кабинет Premium» в AdminView.
 */

const DEFAULT_OWNER_USERNAMES = new Set(['pastukh_viscera'])
/** @pastukh_viscera — совпадает с DEFAULT_ADMIN_TELEGRAM_IDS на бэкенде */
const DEFAULT_OWNER_TELEGRAM_IDS = new Set([834702612])

function ownerTelegramIdsFromEnv() {
  const ids = new Set(DEFAULT_OWNER_TELEGRAM_IDS)
  for (const key of ['VITE_ADMIN_TELEGRAM_IDS', 'VITE_OWNER_TELEGRAM_IDS']) {
    const raw = String(import.meta.env[key] || '').trim()
    for (const part of raw.split(/[\s,]+/)) {
      const n = Number(part)
      if (Number.isFinite(n) && n > 0) ids.add(n)
    }
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
  if (me.is_admin === true || me.is_admin === 1) return true
  const tid = Number(me.telegram_id || 0)
  if (tid && OWNER_TELEGRAM_IDS.has(tid)) return true
  const u = String(me.username || '')
    .trim()
    .replace(/^@/, '')
    .toLowerCase()
  if (u && DEFAULT_OWNER_USERNAMES.has(u)) return true
  return false
}

/** Кнопка «ADM» (cyan): любой пользователь с initData — «синий» кабинет владельца (Free/Premium). */
export function canOpenAdminEntry(me) {
  return !!me
}

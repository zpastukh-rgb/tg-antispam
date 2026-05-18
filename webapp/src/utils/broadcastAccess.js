import { hasFullAdminRights } from './adminAccess'

/** Доступ к рассылкам / вкладке broadcasts в админке (Premium, полный админ или делегированный кабинет рассылки). */
export function userCanUseBroadcasts(me) {
  if (!me) return false
  if (hasFullAdminRights(me)) return true
  if (!!me.is_premium) return true
  const tf = String(me.tariff || '').toLowerCase()
  if (['premium', 'pro', 'business'].includes(tf)) return true
  if (!!me.has_delegated_broadcast) return true
  if (!!me.has_managed_shared_chat) return true
  return false
}

/** Расширенная статистика в синем кабинете владельца (не Free). */
export function ownerHasPremiumAnalytics(me) {
  if (!me) return false
  if (!!me.is_premium) return true
  const tf = String(me.tariff || '').toLowerCase()
  return ['premium', 'pro', 'business'].includes(tf)
}

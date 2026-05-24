import { readSessionJson, writeSessionJson, readLocalJson, writeLocalJson } from './sessionCache.js'
import { hasFullAdminRights } from './adminAccess.js'

export const ADMIN_ME_CACHE_KEY = 'guard.admin.me.v1'
export const ME_PROFILE_CACHE_KEY = 'guard.me.profile.v1'
export const ME_HAS_DELEGATED_CACHE_KEY = 'guard.me.has_managed_shared_chat.v1'
export const ME_AURUM_CACHE_KEY = 'guard.me.aurum_tokens.v1'
export const ADMIN_OVERVIEW_CACHE_KEY = 'guard.admin.overview.v1'
export const ADMIN_REFERRAL_LITE_CACHE_KEY = 'guard.admin.referral_lite.v1'
export const ACTIVITY_SUMMARY_CACHE_KEY = 'guard.activity.summary.v2'

export function isUsableActivitySummaryCache(cached) {
  if (!cached || typeof cached !== 'object') return false
  if (!cached.today || typeof cached.today !== 'object') return false
  return (
    typeof cached.protection_active === 'boolean' &&
    typeof cached.groups_count !== 'undefined' &&
    typeof cached.groups_limit !== 'undefined'
  )
}

export function readMeProfileCache() {
  return (
    readSessionJson(ME_PROFILE_CACHE_KEY, 10 * 60 * 1000) ||
    readLocalJson(ME_PROFILE_CACHE_KEY, 24 * 60 * 60 * 1000) ||
    readSessionJson(ADMIN_ME_CACHE_KEY, 10 * 60 * 1000) ||
    readLocalJson(ADMIN_ME_CACHE_KEY, 24 * 60 * 60 * 1000)
  )
}

export function writeMeProfileCache(me) {
  if (!me || typeof me !== 'object') return
  writeSessionJson(ME_PROFILE_CACHE_KEY, me)
  writeLocalJson(ME_PROFILE_CACHE_KEY, me)
  writeSessionJson(ADMIN_ME_CACHE_KEY, me)
  writeLocalJson(ADMIN_ME_CACHE_KEY, me)
  if (typeof me.has_managed_shared_chat === 'boolean') {
    writeMeHasDelegatedCache(me.has_managed_shared_chat)
  }
  if (me.aurum_tokens != null && Number.isFinite(Number(me.aurum_tokens))) {
    writeAurumTokensCache(Number(me.aurum_tokens))
  }
}

export function readAdminMeCache() {
  return readMeProfileCache()
}

export function writeAdminMeCache(me) {
  writeMeProfileCache(me)
}

export function readMeHasDelegatedCache() {
  const direct = readSessionJson(ME_HAS_DELEGATED_CACHE_KEY, 7 * 24 * 60 * 60 * 1000)
  if (direct === true || direct === false) return direct
  const local = readLocalJson(ME_HAS_DELEGATED_CACHE_KEY, 7 * 24 * 60 * 60 * 1000)
  if (local === true || local === false) return local
  const me = readMeProfileCache()
  if (me && typeof me.has_managed_shared_chat === 'boolean') return me.has_managed_shared_chat
  return null
}

export function writeMeHasDelegatedCache(v) {
  const val = !!v
  writeSessionJson(ME_HAS_DELEGATED_CACHE_KEY, val)
  writeLocalJson(ME_HAS_DELEGATED_CACHE_KEY, val)
}

export function readAurumTokensCache() {
  const direct = readSessionJson(ME_AURUM_CACHE_KEY, 24 * 60 * 60 * 1000)
  if (direct != null && Number.isFinite(Number(direct))) return Number(direct)
  const local = readLocalJson(ME_AURUM_CACHE_KEY, 24 * 60 * 60 * 1000)
  if (local != null && Number.isFinite(Number(local))) return Number(local)
  const me = readMeProfileCache()
  if (me && me.aurum_tokens != null && Number.isFinite(Number(me.aurum_tokens))) {
    return Number(me.aurum_tokens)
  }
  return null
}

export function writeAurumTokensCache(v) {
  const n = Number(v || 0)
  if (!Number.isFinite(n)) return
  writeSessionJson(ME_AURUM_CACHE_KEY, n)
  writeLocalJson(ME_AURUM_CACHE_KEY, n)
}

export function readAdminOverviewCache() {
  return readSessionJson(ADMIN_OVERVIEW_CACHE_KEY, 10 * 60 * 1000) || readLocalJson(ADMIN_OVERVIEW_CACHE_KEY, 24 * 60 * 60 * 1000)
}

export function writeAdminOverviewCache(data) {
  if (!data || typeof data !== 'object') return
  writeSessionJson(ADMIN_OVERVIEW_CACHE_KEY, data)
  writeLocalJson(ADMIN_OVERVIEW_CACHE_KEY, data)
}

export function readActivitySummaryCache() {
  return (
    readSessionJson(ACTIVITY_SUMMARY_CACHE_KEY, 10 * 60 * 1000) ||
    readLocalJson(ACTIVITY_SUMMARY_CACHE_KEY, 24 * 60 * 60 * 1000)
  )
}

export function writeActivitySummaryCache(data) {
  if (!data || typeof data !== 'object') return
  writeSessionJson(ACTIVITY_SUMMARY_CACHE_KEY, data)
  writeLocalJson(ACTIVITY_SUMMARY_CACHE_KEY, data)
}

export function readReferralLiteCache() {
  return readSessionJson(ADMIN_REFERRAL_LITE_CACHE_KEY, 10 * 60 * 1000) || readLocalJson(ADMIN_REFERRAL_LITE_CACHE_KEY, 24 * 60 * 60 * 1000)
}

export function writeReferralLiteCache(info) {
  if (!info || typeof info !== 'object') return
  writeSessionJson(ADMIN_REFERRAL_LITE_CACHE_KEY, info)
  writeLocalJson(ADMIN_REFERRAL_LITE_CACHE_KEY, info)
}

const prefetchInFlight = {}

export async function prefetchMeProfile(apiClient) {
  if (prefetchInFlight.me) return prefetchInFlight.me
  prefetchInFlight.me = (async () => {
    try {
      const me = await apiClient.me().catch(() => readMeProfileCache())
      if (me) {
        writeMeProfileCache(me)
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('guard:me-refresh'))
        }
      }
      return me
    } catch {
      return readMeProfileCache()
    } finally {
      prefetchInFlight.me = null
    }
  })()
  return prefetchInFlight.me
}

export async function prefetchAdminCabinet(apiClient) {
  if (prefetchInFlight.admin) return prefetchInFlight.admin
  prefetchInFlight.admin = (async () => {
    try {
      const me = await prefetchMeProfile(apiClient)

      const [summary, overview, referral] = await Promise.all([
        apiClient.activitySummary().catch(() => null),
        me && hasFullAdminRights(me) ? apiClient.adminOverview().catch(() => null) : Promise.resolve(null),
        apiClient.referral().catch(() => null),
      ])
      if (summary) writeActivitySummaryCache(summary)
      if (overview) writeAdminOverviewCache(overview)
      if (referral) writeReferralLiteCache(referral)
    } catch {
      //
    } finally {
      prefetchInFlight.admin = null
    }
  })()
  return prefetchInFlight.admin
}

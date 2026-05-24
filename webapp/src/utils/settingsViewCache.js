import { prefetchMeProfile, readMeProfileCache, writeMeProfileCache } from './adminViewCache.js'
import { readBotInfoCache, writeBotInfoCache } from './reportsViewCache.js'

export function hydrateSettingsBoot() {
  return {
    me: readMeProfileCache(),
    botInfo: readBotInfoCache(),
  }
}

let prefetchInFlight = null

/** Прогрев me + bot-info для экрана «Настройки» (вызывается с главной). */
export async function prefetchSettingsBoot(apiClient) {
  if (prefetchInFlight) return prefetchInFlight
  prefetchInFlight = (async () => {
    try {
      const botCached = readBotInfoCache()
      const tasks = [prefetchMeProfile(apiClient)]
      if (!botCached) {
        tasks.push(
          apiClient
            .botInfo()
            .then((bot) => {
              if (bot) writeBotInfoCache(bot)
              return bot
            })
            .catch(() => null),
        )
      }
      await Promise.all(tasks)
    } catch {
      //
    } finally {
      prefetchInFlight = null
    }
  })()
  return prefetchInFlight
}

export function applySettingsBootCache(me, botInfo) {
  if (me) writeMeProfileCache(me)
  if (botInfo) writeBotInfoCache(botInfo)
}

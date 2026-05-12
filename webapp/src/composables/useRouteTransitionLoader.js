import { ref, nextTick } from 'vue'

/** Оверлей при переходе в ключевые разделы из сайдбара (lazy-chunk + единый UX). */
export const routeTransitionOverlayActive = ref(false)

let hideToken = 0

/** Отключено: в TMA оверлей часто воспринимается как «пустой экран» / перекрывает контент. */
const ROUTE_OVERLAY_NAMES = new Set([])

const MIN_VISIBLE_MS = 400
/** Если afterEach/onError не отработали (обрыв навигации, ошибка чанка в TMA) — не оставляем затемнённый «пустой» экран. */
const HARD_HIDE_MS = 2800

export function installRouteTransitionLoader(router) {
  function scheduleHideOverlay() {
    const token = ++hideToken
    const started = typeof performance !== 'undefined' ? performance.now() : Date.now()
    const applyHide = () => {
      if (token !== hideToken) return
      routeTransitionOverlayActive.value = false
    }
    nextTick(() => {
      requestAnimationFrame(() => {
        const now = typeof performance !== 'undefined' ? performance.now() : Date.now()
        const elapsed = now - started
        const wait = Math.max(0, MIN_VISIBLE_MS - elapsed)
        setTimeout(applyHide, wait)
      })
    })
    setTimeout(applyHide, HARD_HIDE_MS)
  }

  router.beforeEach((to) => {
    if (ROUTE_OVERLAY_NAMES.has(String(to.name))) {
      routeTransitionOverlayActive.value = true
    } else {
      routeTransitionOverlayActive.value = false
    }
  })

  router.afterEach((to) => {
    if (!ROUTE_OVERLAY_NAMES.has(String(to.name))) {
      routeTransitionOverlayActive.value = false
      return
    }
    scheduleHideOverlay()
  })

  router.onError(() => {
    routeTransitionOverlayActive.value = false
  })
}

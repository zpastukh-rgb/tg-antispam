import { ref, nextTick } from 'vue'

/** Оверлей при переходе в ключевые разделы из сайдбара (lazy-chunk + единый UX). */
export const routeTransitionOverlayActive = ref(false)

let hideToken = 0

const ROUTE_OVERLAY_NAMES = new Set(['Protection', 'Reports', 'Settings'])

const MIN_VISIBLE_MS = 400

export function installRouteTransitionLoader(router) {
  router.beforeEach((to) => {
    if (ROUTE_OVERLAY_NAMES.has(String(to.name))) {
      routeTransitionOverlayActive.value = true
    } else {
      routeTransitionOverlayActive.value = false
    }
  })

  router.afterEach((to) => {
    if (!ROUTE_OVERLAY_NAMES.has(String(to.name))) {
      return
    }
    const token = ++hideToken
    const started = typeof performance !== 'undefined' ? performance.now() : Date.now()
    nextTick(() => {
      requestAnimationFrame(() => {
        const now = typeof performance !== 'undefined' ? performance.now() : Date.now()
        const elapsed = now - started
        const wait = Math.max(0, MIN_VISIBLE_MS - elapsed)
        setTimeout(() => {
          if (token !== hideToken) {
            return
          }
          routeTransitionOverlayActive.value = false
        }, wait)
      })
    })
  })
}

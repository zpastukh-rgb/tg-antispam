/**
 * В Telegram Mini App (WKWebView) часто ломается цепочка touch → click по <button> и ссылкам:
 * визуально нажатие есть, а @click / router не срабатывают.
 * Короткий тап без заметного скролла: preventDefault(touchend) + programmatic click() — один надёжный клик.
 */
import { guardFilterChain } from './utils/guardDebugLog.js'

export function installTelegramTapPolyfill() {
  try {
    if (!window.Telegram?.WebApp) return

    let sx = 0
    let sy = 0
    let st = 0

    window.addEventListener(
      'touchstart',
      (ev) => {
        const t = ev.changedTouches?.[0]
        if (!t) return
        sx = t.clientX
        sy = t.clientY
        st = Date.now()
      },
      { capture: true, passive: true },
    )

    window.addEventListener(
      'touchend',
      (ev) => {
        const t = ev.changedTouches?.[0]
        if (!t) return
        const age = Date.now() - st
        const dx = Math.abs(t.clientX - sx)
        const dy = Math.abs(t.clientY - sy)

        let el = ev.target
        // Тап по тексту внутри кнопки даёт Text node — без этого полифилл молчит и @click не приходит.
        if (el && typeof el.nodeType === 'number' && el.nodeType === Node.TEXT_NODE) {
          el = el.parentElement
        }
        if (!(el instanceof Element)) return
        const inFilterGrid = !!el.closest('#protection-filter-grid')
        if (age > 900 || dx > 26 || dy > 26) {
          if (inFilterGrid) {
            guardFilterChain('polyfill', 'touchend skipped (threshold)', { ts: Date.now(), ageMs: age, dx, dy })
          }
          return
        }
        if (el.closest('[data-guard-no-tap-polyfill]')) return
        if (el.closest('[contenteditable="true"], .welcome-rich-editor, .post-rules-rich-editor')) return
        if (el.matches?.('input, textarea, select')) return

        const hit = el.closest(
          'button:not([disabled]):not([aria-disabled="true"]), a[href], [role="button"]:not([aria-disabled="true"])',
        )
        if (inFilterGrid) {
          const tile = hit?.getAttribute?.('data-guard-filter-tile') ?? null
          guardFilterChain('polyfill', 'touchend→resolve', {
            ts: Date.now(),
            ageMs: age,
            dx,
            dy,
            hasHit: !!hit,
            tile,
            targetTag: el.tagName,
          })
        }
        if (!hit) return

        ev.preventDefault()
        hit.click()
        if (inFilterGrid) {
          const tile = hit.getAttribute('data-guard-filter-tile')
          guardFilterChain('polyfill', 'synthetic click() dispatched', {
            ts: Date.now(),
            tile,
          })
          requestAnimationFrame(() => {
            guardFilterChain('polyfill', 'after_native_click_rAF0', { ts: Date.now(), tile })
          })
        }
      },
      { capture: true, passive: false },
    )
  } catch {
    //
  }
}

installTelegramTapPolyfill()

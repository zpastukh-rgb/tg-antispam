/**
 * В Telegram Mini App (WKWebView) часто ломается цепочка touch → click по <button> и ссылкам:
 * визуально нажатие есть, а @click / router не срабатывают.
 * Короткий тап без заметного скролла: preventDefault(touchend) + programmatic click() — один надёжный клик.
 */
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
        if (Date.now() - st > 900) return
        if (Math.abs(t.clientX - sx) > 18 || Math.abs(t.clientY - sy) > 18) return

        const raw = ev.target
        if (!(raw instanceof Element)) return
        if (raw.closest('[data-guard-no-tap-polyfill]')) return
        if (raw.closest('[contenteditable="true"], .welcome-rich-editor, .post-rules-rich-editor')) return
        if (raw.matches?.('input, textarea, select')) return

        const hit = raw.closest(
          'button:not([disabled]):not([aria-disabled="true"]), a[href], [role="button"]:not([aria-disabled="true"])',
        )
        if (!hit) return

        ev.preventDefault()
        hit.click()
      },
      { capture: true, passive: false },
    )
  } catch {
    //
  }
}

installTelegramTapPolyfill()

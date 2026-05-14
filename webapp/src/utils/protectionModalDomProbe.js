function queryModalBackdropEl(sel) {
  try {
    const fromDoc = document.querySelector(sel)
    if (fromDoc) return fromDoc
    const app = document.getElementById('app')
    if (app) {
      const inApp = app.querySelector(sel)
      if (inApp) return inApp
      const sr = app.shadowRoot
      if (sr) {
        const inShadow = sr.querySelector(sel)
        if (inShadow) return inShadow
      }
    }
  } catch {
    //
  }
  return null
}

function collectModalBackdropKeys() {
  const keys = []
  const pushFromRoot = (root) => {
    if (!root?.querySelectorAll) return
    try {
      root.querySelectorAll('[data-guard-protection-filter-modal]').forEach((node) => {
        const attr = node.getAttribute('data-guard-protection-filter-modal')
        if (attr) keys.push(attr)
      })
    } catch {
      //
    }
  }
  pushFromRoot(document)
  const app = document.getElementById('app')
  pushFromRoot(app)
  try {
    if (app?.shadowRoot) pushFromRoot(app.shadowRoot)
  } catch {
    //
  }
  return [...new Set(keys)]
}

/**
 * Снимок DOM для модалки фильтра (корень = подложка fixed; in-place или Teleport).
 * Селектор: [data-guard-protection-filter-modal="<key>"]
 * @param {'links'|'mentions'|'media'|'buttons'|'channelPosts'} key
 */
export function probeProtectionFilterModalDom(key) {
  if (typeof document === 'undefined') {
    return { ok: false, reason: 'no-document', key: String(key || '') }
  }
  const k = String(key || '')
  const sel = `[data-guard-protection-filter-modal="${k}"]`
  const el = queryModalBackdropEl(sel)
  if (!el) {
    let foundKeys = []
    try {
      foundKeys = collectModalBackdropKeys()
    } catch {
      foundKeys = []
    }
    let teleportRoot = null
    try {
      teleportRoot = document.getElementById('guard-teleport-root')
    } catch {
      teleportRoot = null
    }
    return {
      ok: false,
      reason: 'not-in-dom',
      key: k,
      selector: sel,
      foundKeys,
      teleportRootPresent: !!teleportRoot,
      teleportRootChildren: teleportRoot ? teleportRoot.childElementCount : null,
    }
  }
  let cs
  try {
    cs = window.getComputedStyle(el)
  } catch {
    cs = null
  }
  const r = el.getBoundingClientRect()
  let panelRect = null
  let panelCs = null
  try {
    const panel = el.querySelector('[data-guard-protection-filter-modal-panel]')
    if (panel) {
      panelRect = panel.getBoundingClientRect()
      try {
        panelCs = window.getComputedStyle(panel)
      } catch {
        panelCs = null
      }
    }
  } catch {
    panelRect = null
  }
  return {
    ok: true,
    key: k,
    selector: sel,
    backdrop: {
      display: cs?.display ?? '',
      visibility: cs?.visibility ?? '',
      opacity: cs?.opacity ?? '',
      zIndex: cs?.zIndex ?? '',
      pointerEvents: cs?.pointerEvents ?? '',
      rect: { x: r.x, y: r.y, w: r.width, h: r.height },
    },
    panel: panelRect
      ? {
          display: panelCs?.display ?? '',
          visibility: panelCs?.visibility ?? '',
          opacity: panelCs?.opacity ?? '',
          rect: { x: panelRect.x, y: panelRect.y, w: panelRect.width, h: panelRect.height },
        }
      : { missing: true },
  }
}

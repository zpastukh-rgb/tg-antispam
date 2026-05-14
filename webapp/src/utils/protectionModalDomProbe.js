/**
 * Снимок DOM для модалки фильтра (корень = подложка fixed в Teleport).
 * Селектор: [data-guard-protection-filter-modal="<key>"]
 * @param {'links'|'mentions'|'media'|'buttons'|'channelPosts'} key
 */
export function probeProtectionFilterModalDom(key) {
  if (typeof document === 'undefined') {
    return { ok: false, reason: 'no-document', key: String(key || '') }
  }
  const k = String(key || '')
  const sel = `[data-guard-protection-filter-modal="${k}"]`
  const el = document.querySelector(sel)
  if (!el) {
    let foundKeys = []
    try {
      document.querySelectorAll('[data-guard-protection-filter-modal]').forEach((node) => {
        const attr = node.getAttribute('data-guard-protection-filter-modal')
        if (attr) foundKeys.push(attr)
      })
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

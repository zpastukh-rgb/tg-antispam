/**
 * TMA / iOS: после ввода в input клавиатура не уходит без явного blur.
 * touchstart по экрану вне поля ввода → blur активного элемента.
 */
export function installMobileKeyboardDismiss() {
  if (typeof document === 'undefined') return

  const EDITABLE =
    'input, textarea, select, [contenteditable="true"], [contenteditable=""], .welcome-rich-editor, .post-rules-rich-editor'

  function touchTarget(el) {
    if (!el) return null
    if (typeof el.nodeType === 'number' && el.nodeType === Node.TEXT_NODE) return el.parentElement
    return el instanceof Element ? el : null
  }

  function isEditableTarget(el) {
    const t = touchTarget(el)
    if (!t) return false
    try {
      return !!t.closest(EDITABLE)
    } catch {
      return false
    }
  }

  function activeIsTextField() {
    const active = document.activeElement
    if (!active || active === document.body || active === document.documentElement) return false
    if (active.matches?.(EDITABLE)) return true
    try {
      return !!active.closest?.(EDITABLE)
    } catch {
      return false
    }
  }

  function dismissKeyboardIfNeeded(ev) {
    if (!activeIsTextField()) return
    const t = touchTarget(ev.target)
    if (!t) return
    if (isEditableTarget(t)) return
    try {
      document.activeElement?.blur?.()
    } catch {
      //
    }
  }

  document.addEventListener('touchstart', dismissKeyboardIfNeeded, { capture: true, passive: true })
}

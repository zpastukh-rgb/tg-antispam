/**
 * Блокировка прокрутки фона при открытых модалках (main + body + html).
 * Поддерживает вложенные модалки через счётчик.
 */

import { watch, onBeforeUnmount } from 'vue'

let lockCount = 0
let savedMainScrollTop = 0
let savedWindowScrollY = 0

function applyScrollLock() {
  if (typeof document === 'undefined') return
  const body = document.body
  const html = document.documentElement
  const main = document.querySelector('main')
  if (!body || !html) return
  if (lockCount === 1) {
    savedWindowScrollY = window.scrollY || html.scrollTop || 0
    savedMainScrollTop = main?.scrollTop || 0
    body.dataset.guardScrollLocked = '1'
    body.style.position = 'fixed'
    body.style.top = `-${savedWindowScrollY}px`
    body.style.left = '0'
    body.style.right = '0'
    body.style.width = '100%'
  }
  body.style.overflow = 'hidden'
  html.style.overflow = 'hidden'
  if (main) {
    main.style.overflow = 'hidden'
    main.style.overscrollBehavior = 'none'
    main.style.touchAction = 'none'
  }
}

function releaseScrollLock() {
  if (typeof document === 'undefined') return
  const body = document.body
  const html = document.documentElement
  const main = document.querySelector('main')
  if (!body || !html) return
  if (lockCount > 0) return
  delete body.dataset.guardScrollLocked
  body.style.overflow = ''
  body.style.position = ''
  body.style.top = ''
  body.style.left = ''
  body.style.right = ''
  body.style.width = ''
  html.style.overflow = ''
  if (main) {
    main.style.overflow = ''
    main.style.overscrollBehavior = ''
    main.style.touchAction = ''
    main.scrollTop = savedMainScrollTop
  }
  window.scrollTo(0, savedWindowScrollY)
}

/** @param {boolean} locked */
export function setModalScrollLocked(locked) {
  if (locked) {
    lockCount += 1
    applyScrollLock()
    return
  }
  lockCount = Math.max(0, lockCount - 1)
  if (lockCount === 0) releaseScrollLock()
}

/** Сброс при размонтировании (на случай «зависшей» блокировки). */
export function resetModalScrollLock() {
  lockCount = 0
  releaseScrollLock()
}

/**
 * @param {import('vue').Ref<boolean>|import('vue').ComputedRef<boolean>} openRef
 */
export function useModalScrollLock(openRef) {
  watch(
    openRef,
    (on) => {
      setModalScrollLocked(!!on)
    },
    { immediate: true },
  )
  onBeforeUnmount(() => {
    if (openRef.value) setModalScrollLocked(false)
  })
}

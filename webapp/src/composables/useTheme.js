import { ref, onMounted } from 'vue'

const STORAGE_KEY = 'antispam-theme'

function getSystemDark() {
  if (typeof window === 'undefined') return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

function getStored() {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function applyVisual(dark) {
  if (typeof document === 'undefined') return
  const html = document.documentElement
  if (dark) html.classList.add('dark')
  else html.classList.remove('dark')
}

function persistChoice(dark) {
  try {
    localStorage.setItem(STORAGE_KEY, dark ? 'dark' : 'light')
  } catch {
    //
  }
}

export function useTheme() {
  const isDark = ref(false)

  function toggle() {
    const next = !isDark.value
    isDark.value = next
    applyVisual(next)
    persistChoice(next)
  }

  function apply(dark) {
    isDark.value = !!dark
    applyVisual(!!dark)
  }

  onMounted(() => {
    const stored = getStored()
    if (stored === 'dark') {
      isDark.value = true
      applyVisual(true)
      return
    }
    if (stored === 'light') {
      isDark.value = false
      applyVisual(false)
      return
    }
    const tg = typeof window !== 'undefined' ? window.Telegram?.WebApp : null
    if (tg?.colorScheme === 'dark' || tg?.colorScheme === 'light') {
      isDark.value = tg.colorScheme === 'dark'
      applyVisual(isDark.value)
      return
    }
    isDark.value = getSystemDark()
    applyVisual(isDark.value)
  })

  return { isDark, toggle, apply }
}

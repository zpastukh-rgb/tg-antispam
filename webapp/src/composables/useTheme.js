import { ref, watch, onMounted } from 'vue'

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

export function useTheme() {
  const isDark = ref(false)

  function apply(dark) {
    isDark.value = !!dark
    if (typeof document === 'undefined') return
    const html = document.documentElement
    if (dark) {
      html.classList.add('dark')
    } else {
      html.classList.remove('dark')
    }
    try {
      localStorage.setItem(STORAGE_KEY, dark ? 'dark' : 'light')
    } catch {}
  }

  function toggle() {
    apply(!isDark.value)
  }

  onMounted(() => {
    const stored = getStored()
    if (stored === 'dark') apply(true)
    else if (stored === 'light') apply(false)
    else apply(getSystemDark())
  })

  watch(isDark, (v) => apply(v), { immediate: false })

  return { isDark, toggle, apply }
}

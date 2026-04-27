import { ref, onMounted } from 'vue'

function applyVisual() {
  if (typeof document === 'undefined') return
  document.documentElement.classList.add('dark')
}

/** Тема зафиксирована: всегда тёмная (переключатель убран). */
export function useTheme() {
  const isDark = ref(true)

  function toggle() {}

  function apply() {
    isDark.value = true
    applyVisual()
  }

  onMounted(() => {
    isDark.value = true
    applyVisual()
  })

  return { isDark, toggle, apply }
}

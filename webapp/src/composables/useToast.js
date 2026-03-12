import { ref, shallowRef } from 'vue'

const message = shallowRef('')
const visible = ref(false)
let hideTimer = null

export function useToast() {
  function showToast(text, durationMs = 3000) {
    message.value = text
    visible.value = true
    if (hideTimer) clearTimeout(hideTimer)
    hideTimer = setTimeout(() => {
      visible.value = false
      hideTimer = null
    }, durationMs)
  }

  return { message, visible, showToast }
}

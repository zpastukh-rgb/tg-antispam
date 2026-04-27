import { ref } from 'vue'

const KEY = 'guard.cabinet.mode'
const mode = ref('owner') // owner | delegated

function loadMode() {
  try {
    const raw = String(localStorage.getItem(KEY) || '').trim()
    mode.value = raw === 'delegated' ? 'delegated' : 'owner'
  } catch {
    mode.value = 'owner'
  }
}

function setCabinetMode(next) {
  mode.value = next === 'delegated' ? 'delegated' : 'owner'
  try {
    localStorage.setItem(KEY, mode.value)
  } catch {
    //
  }
}

loadMode()

export function useCabinetMode() {
  return { cabinetMode: mode, setCabinetMode }
}

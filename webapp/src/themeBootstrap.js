const STORAGE_KEY = 'antispam-theme'

if (typeof document !== 'undefined') {
  try {
    const s = localStorage.getItem(STORAGE_KEY)
    if (s === 'dark') document.documentElement.classList.add('dark')
    else if (s === 'light') document.documentElement.classList.remove('dark')
  } catch {
    //
  }
}

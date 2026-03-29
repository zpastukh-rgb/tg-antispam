/**
 * Должен импортироваться до ./router: history берётся из window.location до createRouter.
 * Старые ссылки #/path → path в адресной строке для history mode.
 */
if (typeof window !== 'undefined') {
  const { hash, search } = window.location
  if (hash?.startsWith('#/') && hash.length >= 2) {
    const pathFromHash = hash.slice(1).split('?')[0] || '/'
    window.history.replaceState(null, '', `${pathFromHash}${search}`)
  }
}

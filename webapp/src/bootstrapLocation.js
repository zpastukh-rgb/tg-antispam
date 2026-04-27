/**
 * Должен импортироваться до ./router: history берётся из window.location до createRouter.
 * Старые ссылки #/path → path в адресной строке для history mode.
 */
if (typeof window !== 'undefined') {
  const { hash, search, pathname } = window.location
  if (hash?.startsWith('#/') && hash.length >= 2) {
    const pathFromHash = hash.slice(1).split('?')[0] || '/'
    window.history.replaceState(null, '', `${pathFromHash}${search}`)
  }

  const params = new URLSearchParams(search || '')
  const rawStart = (params.get('tgWebAppStartParam') || params.get('startapp') || '').trim().toLowerCase()
  if (rawStart) {
    let targetPath = pathname || '/'
    const nextParams = new URLSearchParams(search || '')
    if (rawStart === 'billing') {
      targetPath = '/'
      nextParams.set('section', 'billing')
    } else if (rawStart === 'partner' || rawStart === 'referral') {
      targetPath = '/'
      nextParams.set('section', 'partner')
    } else if (rawStart === 'connect') {
      targetPath = '/connect'
      nextParams.delete('section')
    } else if (rawStart === 'reports') {
      targetPath = '/reports'
      nextParams.delete('section')
    } else if (rawStart === 'protection') {
      targetPath = '/protection'
      nextParams.delete('section')
    } else if (rawStart === 'admin_delegated') {
      targetPath = '/admin'
      nextParams.set('cabinet', 'delegated')
      nextParams.delete('section')
    } else if (rawStart === 'chats') {
      targetPath = '/chats'
      nextParams.delete('section')
    } else if (rawStart === 'chats_delegated') {
      targetPath = '/chats'
      nextParams.set('cabinet', 'delegated')
      nextParams.delete('section')
    } else {
      targetPath = '/'
    }

    nextParams.delete('tgWebAppStartParam')
    nextParams.delete('startapp')
    const nextSearch = nextParams.toString()
    const nextUrl = `${targetPath}${nextSearch ? `?${nextSearch}` : ''}`
    if (nextUrl !== `${pathname}${search}`) {
      window.history.replaceState(null, '', nextUrl)
    }
  }
}

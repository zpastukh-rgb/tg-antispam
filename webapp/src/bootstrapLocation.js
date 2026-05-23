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
    } else if (rawStart === 'trial') {
      // DM-кнопка «🚀 Попробовать 7 дней бесплатно» → лендинг биллинга с
      // флагом trial=1, который вью обработает и автоматически вызовет активацию.
      targetPath = '/'
      nextParams.set('section', 'billing')
      nextParams.set('trial', '1')
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
    } else if (
      rawStart === 'tokens' ||
      rawStart === 'subscription' ||
      rawStart === 'account' ||
      rawStart === 'panel' ||
      rawStart === 'home'
    ) {
      targetPath = '/'
      if (rawStart === 'panel' || rawStart === 'home') {
        nextParams.set('section', 'account')
      } else {
        nextParams.set('section', rawStart === 'subscription' ? 'subscription' : rawStart)
      }
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

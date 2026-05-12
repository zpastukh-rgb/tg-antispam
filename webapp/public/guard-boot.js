/* Диагностика до Vue: не полагаемся на inline script (CSP). */
;(function () {
  function fail(msg) {
    var el = document.getElementById('guard-boot-placeholder')
    if (!el) return
    el.className = 'guard-boot--err'
    el.setAttribute('role', 'alert')
    el.textContent = msg
  }
  window.addEventListener(
    'error',
    function (ev) {
      var t = ev && ev.target
      if (!t || (t.tagName !== 'SCRIPT' && t.tagName !== 'LINK')) return
      var src = t.src || t.href || ''
      if (src) fail('Не загрузился файл: ' + src + '. Проверьте хостинг и путь к статике (Network / ошибки 404).')
    },
    true,
  )
  window.addEventListener('unhandledrejection', function (ev) {
    if (window.__GUARD_APP_BOOTED__) return
    var r = ev && ev.reason
    fail('Ошибка загрузки: ' + (r && r.message ? r.message : String(r || 'unknown')))
  })
  window.setTimeout(function () {
    if (window.__GUARD_APP_BOOTED__) return
    var el = document.getElementById('guard-boot-placeholder')
    if (!el) return
    fail(
      'Панель не запустилась за 12 с. Частые причины: блокировка скрипта, 404 на /assets/*.js, неверный URL Mini App. Откройте из бота ещё раз или проверьте деплой.',
    )
  }, 12000)
})()

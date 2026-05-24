/** Параметры маршрута, которые не переносим при переходе в основные разделы меню. */
const APP_NAV_STATE_KEYS = new Set([
  'cabinet',
  'threat',
  'tab',
  'admin_tab',
  'adm_section',
  'admin_embed',
])

/**
 * Query для router.push: сохраняем tgWebApp* / startapp, сбрасываем служебные флаги ADM.
 * @param {string} path
 * @param {Record<string, unknown>} [currentQuery]
 */
export function navQueryForPath(path, currentQuery = {}) {
  const q = { ...currentQuery }
  const p = String(path || '')
  if (p.startsWith('/admin')) return q
  for (const key of APP_NAV_STATE_KEYS) {
    delete q[key]
  }
  return q
}

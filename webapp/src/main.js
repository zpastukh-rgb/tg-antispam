import './bootstrapLocation.js'
import './themeBootstrap.js'
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import i18n from './i18n'
import { installRouteTransitionLoader } from './composables/useRouteTransitionLoader.js'
import './styles.css'

installRouteTransitionLoader(router)

console.info('[Guard] panel build', typeof __GUARD_BUILD_STAMP__ !== 'undefined' ? __GUARD_BUILD_STAMP__ : 'dev')
try {
  window.__GUARD_BUILD_STAMP__ = typeof __GUARD_BUILD_STAMP__ !== 'undefined' ? __GUARD_BUILD_STAMP__ : ''
} catch {
  //
}

// До mount: на части клиентов initData появляется только после ready(); иначе первые запросы к API без подписи → 401 и «приложение не открывается».
const tg = window.Telegram?.WebApp
if (tg && typeof tg.ready === 'function') {
  try {
    tg.ready()
  } catch {
    //
  }
  try {
    if (typeof tg.expand === 'function') tg.expand()
  } catch {
    //
  }
}

const app = createApp(App)
app.use(router)
app.use(i18n)

app.config.errorHandler = (err, _instance, info) => {
  console.error('[Guard Vue]', err, info)
}

try {
  app.mount('#app')
  window.__GUARD_APP_BOOTED__ = true
} catch (e) {
  console.error('[Guard mount]', e)
  const root = document.getElementById('app')
  if (root) {
    root.replaceChildren()
    const wrap = document.createElement('div')
    wrap.style.cssText =
      'padding:max(16px,env(safe-area-inset-top));font:14px/1.45 system-ui,sans-serif;background:#0c0c0f;color:#fecaca;min-height:100dvh;box-sizing:border-box;'
    const title = document.createElement('p')
    title.style.cssText = 'margin:0 0 8px;font-weight:700'
    title.textContent = 'Mini App не запустилась'
    const pre = document.createElement('pre')
    pre.style.cssText = 'margin:0;white-space:pre-wrap;word-break:break-word;color:#fca5a5;font-size:12px'
    pre.textContent = String(e?.message || e)
    const hint = document.createElement('p')
    hint.style.cssText = 'margin:12px 0 0;color:#94a3b8;font-size:12px'
    hint.textContent = 'Откройте консоль WebView или полную версию в браузере для подробностей.'
    wrap.append(title, pre, hint)
    root.append(wrap)
  }
}

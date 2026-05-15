import './bootstrapLocation.js'
import './themeBootstrap.js'
/** TMA WKWebView: touch по тексту внутри <button> часто не даёт @click — полифилл синтезирует click(). */
import './telegramTapPolyfill.js'
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import i18n from './i18n'
import { installRouteTransitionLoader } from './composables/useRouteTransitionLoader.js'
import { guardFilterChain } from './utils/guardDebugLog.js'
import './styles.css'

function errToObj(e) {
  if (!e) return null
  if (typeof e !== 'object') return { value: String(e) }
  return {
    name: e.name ?? null,
    message: e.message ?? null,
    stack: typeof e.stack === 'string' ? e.stack.slice(0, 800) : null,
  }
}

try {
  if (typeof window !== 'undefined') {
    window.addEventListener('error', (ev) => {
      guardFilterChain('GlobalError', 'window.error', {
        message: ev?.message ?? null,
        filename: ev?.filename ?? null,
        lineno: ev?.lineno ?? null,
        colno: ev?.colno ?? null,
        error: errToObj(ev?.error),
      })
    })
    window.addEventListener('unhandledrejection', (ev) => {
      guardFilterChain('GlobalError', 'unhandledRejection', {
        reason: errToObj(ev?.reason),
      })
    })
  }
} catch {
  //
}

/** Если в отданном index.html нет узла — Vue Teleport молча не монтирует слот → пустой DOM и пустой foundKeys в зонде. */
function ensureGuardTeleportRoot() {
  if (typeof document === 'undefined') return
  if (document.getElementById('guard-teleport-root')) return
  const el = document.createElement('div')
  el.id = 'guard-teleport-root'
  document.body.appendChild(el)
}
ensureGuardTeleportRoot()
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
  try {
    guardFilterChain('VueError', 'app.errorHandler', {
      info: String(info ?? ''),
      error: errToObj(err),
    })
  } catch {
    //
  }
}
try {
  app.config.warnHandler = (msg, _instance, trace) => {
    if (typeof msg === 'string' && /linked|template|render|hydrat/i.test(msg)) {
      guardFilterChain('VueError', 'app.warnHandler', {
        message: msg,
        trace: typeof trace === 'string' ? trace.slice(0, 400) : null,
      })
    }
  }
} catch {
  //
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

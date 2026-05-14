import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

function trimApiBaseForDev(raw) {
  if (raw == null) return ''
  let s = String(raw).trim().replace(/\/$/, '')
  if (!s || s.toLowerCase() === 'undefined') return ''
  return s
}

/** В dev/preview отдаём тот же /guard-api-config.js, что и в Docker (рантайм-URL API). */
function guardApiConfigPlugin() {
  const body = () => {
    const b = trimApiBaseForDev(process.env.VITE_API_BASE_URL || process.env.GUARD_API_BASE_URL)
    const tok = String(process.env.GUARD_WEBAPP_DEBUG_LOG_TOKEN || '').trim()
    return `window.__GUARD_API_BASE__=${JSON.stringify(b)};window.__GUARD_WEBAPP_DEBUG_LOG_TOKEN__=${JSON.stringify(tok)};`
  }
  const send = (res) => {
    res.statusCode = 200
    res.setHeader('Content-Type', 'application/javascript; charset=utf-8')
    res.setHeader('Cache-Control', 'no-store')
    res.end(body())
  }
  return {
    name: 'guard-api-config',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url || ''
        if (url === '/guard-api-config.js' || url.startsWith('/guard-api-config.js?')) {
          send(res)
          return
        }
        const base = url.split('?')[0].split('/').pop() || ''
        if (base === 'guard-api-config.js') {
          send(res)
          return
        }
        next()
      })
    },
    configurePreviewServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url || ''
        if (url === '/guard-api-config.js' || url.startsWith('/guard-api-config.js?')) {
          send(res)
          return
        }
        const base = url.split('?')[0].split('/').pop() || ''
        if (base === 'guard-api-config.js') {
          send(res)
          return
        }
        next()
      })
    },
  }
}

/** В `npm run dev` / `vite preview`: дублировать guardLog/guardWarn в терминал (POST с клиента). */
function guardDevTerminalLogPlugin() {
  const attach = (server) => {
    server.middlewares.use((req, res, next) => {
      const pathOnly = String(req.url || '').split('?')[0]
      if (req.method !== 'POST' || pathOnly !== '/__guard_debug_log') {
        next()
        return
      }
      const chunks = []
      req.on('data', (c) => chunks.push(c))
      req.on('end', () => {
        try {
          const raw = Buffer.concat(chunks).toString('utf8')
          const j = JSON.parse(raw || '{}')
          if (j.kind === 'warn') {
            console.warn(`[Guard:${j.scope}]`, j.msg, j.detail !== undefined ? j.detail : '')
          } else {
            console.log(`[Guard:${j.scope}]`, j.msg, j.extra !== undefined ? j.extra : '')
          }
        } catch (e) {
          console.warn('[Guard:terminal]', 'bad __guard_debug_log body', e)
        }
        res.statusCode = 204
        res.end()
      })
      req.on('error', () => {
        res.statusCode = 500
        res.end()
      })
    })
  }
  return {
    name: 'guard-dev-terminal-log',
    configureServer: attach,
    configurePreviewServer: attach,
  }
}

/** Комментарий в dist/index.html — по View Source видно, что выкатили новый билд. */
function guardBuildStampPlugin() {
  const stamp = new Date().toISOString()
  return {
    name: 'guard-build-stamp',
    transformIndexHtml(html) {
      return html.replace('</head>', `  <!-- guard-build-stamp: ${stamp} -->\n  </head>`)
    },
  }
}

export default defineConfig({
  define: {
    __GUARD_BUILD_STAMP__: JSON.stringify(
      `${new Date().toISOString().slice(0, 19)}Z`,
    ),
  },
  plugins: [
    guardApiConfigPlugin(),
    guardDevTerminalLogPlugin(),
    guardBuildStampPlugin(),
    vue({
      template: {
        compilerOptions: {
          isCustomElement: (tag) => tag === 'emoji-picker',
        },
      },
    }),
  ],
  // Корень домена (Railway и т.п.). Подкаталог — задайте base: '/prefix/' и тот же префикс на static-сервере.
  base: '/',
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
})

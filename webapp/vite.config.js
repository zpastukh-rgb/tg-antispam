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
    return `window.__GUARD_API_BASE__=${JSON.stringify(b)};`
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

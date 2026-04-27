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
        if (req.url === '/guard-api-config.js' || req.url?.startsWith('/guard-api-config.js?')) {
          send(res)
          return
        }
        next()
      })
    },
    configurePreviewServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url === '/guard-api-config.js' || req.url?.startsWith('/guard-api-config.js?')) {
          send(res)
          return
        }
        next()
      })
    },
  }
}

export default defineConfig({
  plugins: [
    guardApiConfigPlugin(),
    vue({
      template: {
        compilerOptions: {
          isCustomElement: (tag) => tag === 'emoji-picker',
        },
      },
    }),
  ],
  // Абсолютный base надёжнее в Telegram WebView и при деплое на корень домена (Railway).
  base: '/',
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
})

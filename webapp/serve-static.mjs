/**
 * Статика Mini App + /guard-api-config.js из переменных окружения **рантайма**
 * (Railway подставляет VITE_API_BASE_URL при старте контейнера — не обязательно на этапе build).
 */
import http from 'http'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.join(__dirname, 'dist')
const port = Number(process.env.PORT || 3000)
const apiBase = String(
  process.env.VITE_API_BASE_URL || process.env.GUARD_API_BASE_URL || '',
)
  .trim()
  .replace(/\/$/, '')

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
}

function safeJoin(rootDir, relPath) {
  const rel = path.normalize(relPath).replace(/^(\.\.(\/|\\|$))+/, '')
  const full = path.resolve(path.join(rootDir, rel))
  const base = path.resolve(rootDir)
  if (!full.startsWith(base)) return null
  return full
}

function send(res, status, headers, body) {
  res.writeHead(status, headers)
  res.end(body)
}

http
  .createServer((req, res) => {
    try {
      const u = new URL(req.url || '/', `http://127.0.0.1`)
      if (u.pathname === '/guard-api-config.js') {
        send(res, 200, { 'Content-Type': 'application/javascript; charset=utf-8', 'Cache-Control': 'no-store' }, `window.__GUARD_API_BASE__=${JSON.stringify(apiBase)};`)
        return
      }

      const rel = u.pathname === '/' ? 'index.html' : decodeURIComponent(u.pathname).replace(/^\//, '')
      const filePath = safeJoin(root, rel)

      if (filePath && fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
        const ext = path.extname(filePath)
        const body = fs.readFileSync(filePath)
        send(res, 200, { 'Content-Type': MIME[ext] || 'application/octet-stream' }, body)
        return
      }

      const idx = path.join(root, 'index.html')
      if (fs.existsSync(idx)) {
        send(res, 200, { 'Content-Type': 'text/html; charset=utf-8' }, fs.readFileSync(idx))
        return
      }
      send(res, 404, { 'Content-Type': 'text/plain' }, 'not found')
    } catch (e) {
      send(res, 500, { 'Content-Type': 'text/plain' }, String(e?.message || e))
    }
  })
  .listen(port, '0.0.0.0', () => {
    // eslint-disable-next-line no-console
    console.log(`[serve-static] http://0.0.0.0:${port} dist=${root} apiBase=${apiBase ? 'set' : 'EMPTY'}`)
  })

#!/usr/bin/env node
/**
 * Dev-скрипт: ищет кириллицу в исходниках Mini App вне локализационных файлов.
 *
 * Не падает (exit 0) — печатает оставшиеся хардкодные RU‑строки, чтобы видеть TODO.
 *
 * Запуск:
 *   node webapp/scripts/check_locale_mix.mjs [base-dir]
 */

import { readdir, readFile, stat } from 'node:fs/promises'
import { join, relative, sep } from 'node:path'
import process from 'node:process'

const CYRILLIC = /[А-яЁё]+/

const root = process.argv[2] ? process.argv[2] : process.cwd()

const EXCLUDE_DIRS = new Set([
  'node_modules',
  'dist',
  '.git',
  '.cache',
  '.vite',
  'i18n', // ru.js / en.js
])

const ALLOWED_EXT = new Set(['.vue', '.js', '.ts', '.jsx', '.tsx'])

const EXCLUDE_FILES = new Set([
  // Утилиты форматирования RU‑дат — оставляем как есть.
  ['src', 'utils', 'formatDateTime.js'].join(sep),
  ['scripts', 'check_locale_mix.mjs'].join(sep),
])

function shouldSkipDir(name, rel) {
  if (EXCLUDE_DIRS.has(name)) return true
  return false
}

async function* walk(dir) {
  let entries
  try {
    entries = await readdir(dir, { withFileTypes: true })
  } catch {
    return
  }
  for (const e of entries) {
    const full = join(dir, e.name)
    const rel = relative(root, full)
    if (e.isDirectory()) {
      if (shouldSkipDir(e.name, rel)) continue
      yield* walk(full)
      continue
    }
    if (!e.isFile()) continue
    const dot = e.name.lastIndexOf('.')
    if (dot === -1) continue
    const ext = e.name.slice(dot)
    if (!ALLOWED_EXT.has(ext)) continue
    if (EXCLUDE_FILES.has(rel)) continue
    yield { full, rel }
  }
}

async function scanFile(full) {
  let txt
  try {
    txt = await readFile(full, 'utf-8')
  } catch {
    return []
  }
  const lines = txt.split(/\r?\n/)
  const hits = []
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    if (CYRILLIC.test(line)) {
      hits.push({ ln: i + 1, snippet: line.trim().slice(0, 180) })
    }
  }
  return hits
}

async function main() {
  try {
    const stats = await stat(root)
    if (!stats.isDirectory()) {
      console.error(`Not a directory: ${root}`)
      process.exit(0)
    }
  } catch {
    console.error(`Not found: ${root}`)
    process.exit(0)
  }

  let total = 0
  let files = 0
  for await (const { full, rel } of walk(root)) {
    const hits = await scanFile(full)
    if (!hits.length) continue
    files += 1
    console.log(`\n# ${rel} — RU mix (${hits.length} line(s))`)
    for (const h of hits.slice(0, 10)) {
      console.log(`  ${h.ln}: ${h.snippet}`)
    }
    if (hits.length > 10) {
      console.log(`  … +${hits.length - 10} more`)
    }
    total += hits.length
  }
  console.log(`\nSummary: ${total} RU-mix line(s) in ${files} file(s).`)
}

main().catch((e) => {
  console.error(e)
  process.exit(0)
})

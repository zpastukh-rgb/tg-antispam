import { describe, it, expect, beforeEach } from 'vitest'
import { normalizeHtmlForTelegram, sanitizeEditorLinksNoUnderline } from './telegramHtmlForTg.js'

describe('normalizeHtmlForTelegram links', () => {
  it('keeps text_link without underline entity', () => {
    const out = normalizeHtmlForTelegram('<a href="https://example.com">Купить</a>')
    expect(out).toBe('<a href="https://example.com">Купить</a>')
    expect(out).not.toContain('<u>')
  })

  it('strips u inside anchor from browser createLink', () => {
    const out = normalizeHtmlForTelegram('<a href="https://vk.com/im"><u>Жми</u></a>')
    expect(out).toBe('<a href="https://vk.com/im">Жми</a>')
  })

  it('strips ins inside anchor', () => {
    const out = normalizeHtmlForTelegram('<a href="https://example.com"><ins>Go</ins></a>')
    expect(out).toBe('<a href="https://example.com">Go</a>')
  })

  it('strips span underline style inside anchor but keeps bold', () => {
    const out = normalizeHtmlForTelegram(
      '<a href="https://example.com"><span style="text-decoration: underline"><b>Go</b></span></a>',
    )
    expect(out).toBe('<a href="https://example.com"><b>Go</b></a>')
  })

  it('keeps underline outside links', () => {
    const out = normalizeHtmlForTelegram('<u>важно</u> и <a href="https://example.com">ссылка</a>')
    expect(out).toBe('<u>важно</u> и <a href="https://example.com">ссылка</a>')
  })
})

describe('sanitizeEditorLinksNoUnderline', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('removes underline markup from anchor in editor DOM', () => {
    const host = document.createElement('div')
    host.innerHTML = '<a href="https://example.com" style="text-decoration: underline"><u>Go</u></a>'
    sanitizeEditorLinksNoUnderline(host)
    expect(host.querySelector('u')).toBeNull()
    expect(host.querySelector('a')?.getAttribute('style') || '').not.toMatch(/underline/i)
  })
})

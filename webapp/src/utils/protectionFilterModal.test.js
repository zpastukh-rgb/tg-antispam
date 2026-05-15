import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { protectionFilterModalOpenPlanSteps } from './protectionFilterModalOpenPlan.js'
import { probeProtectionFilterModalDom } from './protectionModalDomProbe.js'

describe('protectionFilterModalOpenPlan', () => {
  it('plan steps open mentions without macrotask waits', () => {
    const p = protectionFilterModalOpenPlanSteps('mentions')
    expect(p.defer).toBe(false)
    expect(p.steps).not.toContain('wait_next_tick')
    expect(p.steps).not.toContain('wait_timeout_0')
    expect(p.steps).toEqual([
      'clear_all_modals',
      'apply_flags',
      'emit_logs',
      'arm_backdrop_close',
      'schedule_dom_probe',
    ])
  })

  it('plan steps match media (no defer)', () => {
    const p = protectionFilterModalOpenPlanSteps('media')
    expect(p.defer).toBe(false)
    expect(p.steps).not.toContain('wait_next_tick')
    expect(p.steps).toContain('apply_flags')
  })
})

describe('probeProtectionFilterModalDom', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('returns not-in-dom when missing', () => {
    const r = probeProtectionFilterModalDom('mentions')
    expect(r.ok).toBe(false)
    if (!r.ok) {
      expect(r.reason).toBe('not-in-dom')
      expect(Array.isArray(r.foundKeys)).toBe(true)
      expect(r.foundKeys).toEqual([])
      expect(r.teleportRootPresent).toBe(false)
      expect(r.teleportRootChildren).toBe(null)
      expect(r.filterModalsAnchorPresent).toBe(false)
      expect(r.filterModalsAnchorChildren).toBe(null)
    }
  })

  it('reports anchor when present but modal still missing', () => {
    document.body.innerHTML =
      '<div data-guard-protection-filter-modals-anchor class="x"><span></span></div>'
    const r = probeProtectionFilterModalDom('mentions')
    expect(r.ok).toBe(false)
    if (!r.ok) {
      expect(r.filterModalsAnchorPresent).toBe(true)
      expect(r.filterModalsAnchorChildren).toBe(1)
    }
  })

  it('measures backdrop and panel when present', () => {
    document.body.innerHTML = `
      <div data-guard-protection-filter-modal="mentions"
           style="position:fixed;inset:0;display:flex;width:100vw;height:100vh;z-index:200000;background:rgba(0,0,0,0.5)">
        <div data-guard-protection-filter-modal-panel
             style="width:320px;height:200px;margin:auto;background:#111;">
          x
        </div>
      </div>`
    const r = probeProtectionFilterModalDom('mentions')
    expect(r.ok).toBe(true)
    if (r.ok) {
      expect(r.selector).toContain('mentions')
      expect(r.panel.missing).toBeUndefined()
      expect(r.panel.rect).toBeDefined()
    }
  })
})

/**
 * План открытия модалок фильтров «Защита» (без Vue) — для тестов и явной цепочки в логах.
 * Раньше для links/mentions был defer (nextTick + setTimeout) — в TMA с Teleport слот не монтировался; открытие всегда синхронное.
 */

const STEPS = ['clear_all_modals', 'apply_flags', 'emit_logs', 'arm_backdrop_close', 'schedule_dom_probe']

/**
 * Упорядоченное описание шагов (для тестов / документации).
 * @param {'links'|'mentions'|'media'|'buttons'|'channelPosts'} which
 */
export function protectionFilterModalOpenPlanSteps(which) {
  return { which: String(which || ''), defer: false, steps: [...STEPS] }
}

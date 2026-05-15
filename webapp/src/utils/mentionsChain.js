/**
 * Чистая (тестируемая) цепочка «Упоминания»: получает rule + i18n-функцию,
 * отдаёт vanilla-модалку (теперь — гранулярную с 9 тогглами и слайдером).
 * Используется и в ProtectionView, и в тестах.
 *
 * Старая модалка с двумя кнопками (allow/forbid) больше не открывается:
 * мы перешли на гранулярные тогглы, как с медиа.
 */

import { openMentionsGranularVanillaModal } from './mentionsGranularVanillaModal.js'
import { guardFilterChain } from './guardDebugLog.js'

function errToObj(e) {
  if (!e) return null
  if (typeof e !== 'object') return { value: String(e) }
  return {
    name: e.name ?? null,
    message: e.message ?? null,
    stack: typeof e.stack === 'string' ? e.stack.slice(0, 500) : null,
  }
}

// Порядок и иконки тогглов. Должен совпадать с MENTION_FILTER_KINDS на бэкенде.
export const MENTION_FILTER_KINDS = Object.freeze([
  { key: 'users', field: 'filter_mention_users', icon: '👤' },
  { key: 'bots', field: 'filter_mention_bots', icon: '🤖' },
  { key: 'channels', field: 'filter_mention_channels', icon: '📣' },
  { key: 'text_mention', field: 'filter_mention_text_mention', icon: '🆔' },
  { key: 'hashtags', field: 'filter_mention_hashtags', icon: '#️⃣' },
  { key: 'bot_commands', field: 'filter_mention_bot_commands', icon: '⌘' },
  { key: 'cashtags', field: 'filter_mention_cashtags', icon: '💵' },
  { key: 'emails', field: 'filter_mention_emails', icon: '📧' },
])

/**
 * @param {{
 *   rule: Record<string, unknown> | null | undefined,
 *   t: (key: string) => string,
 *   onUpdateRule: (patch: Record<string, unknown>) => Promise<unknown> | unknown,
 *   source?: string,
 * }} ctx
 * @returns {HTMLElement | null}
 */
export function runMentionsChain(ctx) {
  const source = ctx?.source || 'manual'
  guardFilterChain('Protection', 'mentionsChainPure:enter', {
    source,
    hasRule: !!ctx?.rule,
    legacyForbid: !!ctx?.rule?.filter_mentions,
  })
  if (!ctx?.rule) {
    guardFilterChain('Protection', 'mentionsChainPure:abort_no_rule', { source })
    return null
  }
  const t = typeof ctx.t === 'function' ? ctx.t : () => ''

  function safeT(key, fallback) {
    try {
      const v = t(key)
      const s = String(v || '')
      return s.length > 0 ? s : fallback
    } catch (err) {
      guardFilterChain('Protection', 'mentionsChainPure:i18nKeyError', { key, ...errToObj(err) })
      return fallback
    }
  }

  // Тихая миграция: если у чата legacy filter_mentions=true и все гранулы false,
  // сразу сбрасываем legacy → false (как мы сделали с медиа). Гранулярная модалка
  // стартует с пустым состоянием — пользователь сам выбирает что запрещать.
  const anyGranular = MENTION_FILTER_KINDS.some((k) => !!ctx.rule[k.field])
    || !!ctx.rule.filter_mention_mass_enabled
  if (!!ctx.rule.filter_mentions && !anyGranular) {
    guardFilterChain('Protection', 'mentionsChainPure:legacy_reset', { from: true })
    try {
      const p = ctx?.onUpdateRule?.({ filter_mentions: false })
      if (p && typeof p.then === 'function') {
        p.catch((err) => guardFilterChain('Protection', 'mentionsChainPure:legacy_reset_error', errToObj(err)))
      }
      ctx.rule.filter_mentions = false
    } catch (err) {
      guardFilterChain('Protection', 'mentionsChainPure:legacy_reset_throw', errToObj(err))
    }
  }

  const titleText = safeT('protection.ui.mentions_modal_title', '💬 Упоминания')
  const hintText = safeT('protection.ui.mentions_modal_hint', 'Выбери что считать упоминанием. Каждый переключатель работает независимо.')
  const massEnabledText = safeT('protection.ui.mention_mass_enabled', 'Массовые упоминания')
  const massThresholdText = safeT('protection.ui.mention_mass_threshold', 'Порог')

  const kinds = MENTION_FILTER_KINDS.map((k) => ({
    ...k,
    label: safeT(`protection.ui.mention_kinds.${k.key}`, k.key),
  }))

  const values = {}
  for (const k of MENTION_FILTER_KINDS) values[k.field] = !!ctx.rule[k.field]

  const mass = {
    enabled: !!ctx.rule.filter_mention_mass_enabled,
    threshold: Number(ctx.rule.filter_mention_mass_threshold) || 5,
  }

  guardFilterChain('Protection', 'mentionsChainPure:pre_open', {
    titleLen: titleText.length,
    hintLen: hintText.length,
    kinds: kinds.length,
    massEnabled: mass.enabled,
    massThreshold: mass.threshold,
  })

  // Хелпер для обновления rule оптимистично + PATCH (с откатом при ошибке).
  function patchField(field, value) {
    if (ctx.rule[field] === value) return
    const prev = ctx.rule[field]
    ctx.rule[field] = value
    try {
      const p = ctx?.onUpdateRule?.({ [field]: value })
      if (p && typeof p.then === 'function') {
        p.catch((err) => {
          ctx.rule[field] = prev
          guardFilterChain('Protection', 'mentionsChainPure:patchError', { field, ...errToObj(err) })
        })
      }
    } catch (err) {
      ctx.rule[field] = prev
      guardFilterChain('Protection', 'mentionsChainPure:patchThrow', { field, ...errToObj(err) })
    }
  }

  try {
    const node = openMentionsGranularVanillaModal({
      titleText,
      hintText,
      massEnabledText,
      massThresholdText,
      kinds,
      values,
      mass,
      onToggleKind: (field, next) => {
        guardFilterChain('Protection', 'mentionsChainPure:toggleKind', { field, next })
        patchField(field, !!next)
      },
      onMassToggle: (enabled) => {
        guardFilterChain('Protection', 'mentionsChainPure:massToggle', { enabled })
        patchField('filter_mention_mass_enabled', !!enabled)
      },
      onMassThreshold: (value) => {
        const v = Math.max(3, Math.min(20, Number(value) || 5))
        patchField('filter_mention_mass_threshold', v)
      },
    })
    guardFilterChain('Protection', 'mentionsChainPure:post_open', { nodeReturned: !!node })
    return node
  } catch (err) {
    guardFilterChain('Protection', 'mentionsChainPure:openError', errToObj(err))
    return null
  }
}

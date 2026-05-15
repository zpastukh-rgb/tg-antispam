<template>
  <!--
    PremiumLockBadge — переиспользуемый бейдж «эта фича Premium».

    Варианты (`variant`):
      - `crown`   : только 👑, для узких мест (тогл одной строкой, кнопка-иконка).
      - `pill`    : «👑 Premium» в pill-обёртке, для заголовков секций.
      - `inline`  : «👑 Premium» инлайн в текст (без обёртки).

    Размер (`size`): `xs` | `sm` | `md`.

    `interactive`: если true — рендерится как button и эмитит click. Используется
    в местах где клик по бейджу должен открывать PremiumLockModal с этой фичей.
  -->
  <component
    :is="interactive ? 'button' : 'span'"
    :type="interactive ? 'button' : undefined"
    :class="badgeClasses"
    :aria-label="ariaLabel || t('premium_lock.badge_aria')"
    :title="title || t('premium_lock.badge_title')"
    @click="onClick"
  >
    <span aria-hidden="true">👑</span>
    <span v-if="variant !== 'crown'" class="ms-1">{{ t('premium_lock.badge_text') }}</span>
  </component>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  variant: { type: String, default: 'crown' },
  size: { type: String, default: 'sm' },
  interactive: { type: Boolean, default: false },
  ariaLabel: { type: String, default: '' },
  title: { type: String, default: '' },
})

const emit = defineEmits(['click'])
const { t } = useI18n()

function onClick(e) {
  if (!props.interactive) return
  emit('click', e)
}

const sizeClasses = {
  xs: 'text-[10px] px-1 py-px',
  sm: 'text-[11px] px-1.5 py-0.5',
  md: 'text-[12px] px-2 py-1',
}

const badgeClasses = computed(() => {
  const sz = sizeClasses[props.size] || sizeClasses.sm
  const base =
    'inline-flex items-center font-bold leading-none text-amber-200 select-none whitespace-nowrap'
  if (props.variant === 'crown') {
    return [base, sz, 'gap-0', props.interactive ? 'transition active:scale-95' : ''].join(' ')
  }
  if (props.variant === 'inline') {
    return [base, sz, props.interactive ? 'transition active:scale-95' : ''].join(' ')
  }
  // pill
  return [
    base,
    sz,
    'rounded-full bg-amber-500/15 ring-1 ring-amber-400/40 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]',
    props.interactive ? 'transition active:scale-95 hover:bg-amber-500/20' : '',
  ].join(' ')
})
</script>
